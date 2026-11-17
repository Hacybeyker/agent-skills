"""Tests de hb-performance 0.13.0: cierre seguro (B), `siguiente` como guía (A), mediciones que dicen lo que miden (C),
setup (D) y la etiqueta de veredicto en gerencia (E). Los datos son inventados."""
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, write
from test_perf import PKG, STATE_COST, PerfBase, perf, rows

HEADER = "fase,flujo,metrica,corrida,valor,unidad,sentido,familia\n"

FRAGMENT = ("class ContactosFragment {\n"
            "    fun onStart() {\n"
            "        cargar()\n"
            "    }\n"
            "\n"
            "    fun uno() = 1\n"
            "    fun dos() = 2\n"
            "    fun tres() = 3\n"
            "    fun cuatro() = 4\n"
            "    fun cinco() = 5\n"
            "    fun seis() = 6\n"
            "    fun siete() = 7\n"
            "    fun ocho() = 8\n"
            "\n"
            "    fun mostrar() {\n"
            "        lista()\n"
            "    }\n"
            "}\n")
WITH_IMPROVEMENT = FRAGMENT.replace("        cargar()\n", "        cargar()\n        precargar()\n")
WITH_MARKS = FRAGMENT.replace("        lista()\n", "        lista()\n        MarkTrace.mark(\"lista_visible\")\n")
BOTH = WITH_IMPROVEMENT.replace("        lista()\n", "        lista()\n        MarkTrace.mark(\"lista_visible\")\n")


def ago(minutes):
    return (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


class MixedFileBase(PerfBase):
    """Un proyecto con una mejora (M1, en onStart) y una marca temporal (en mostrar) en el mismo archivo, en hunks
    separados."""

    def setUp(self):
        super().setUp()
        self.root = self.dir / "proyecto"
        self.root.mkdir()
        init_repo(self.root)
        self.file = self.root / "app" / "ContactosFragment.kt"
        write(self.file, FRAGMENT)
        commit_all(self.root)
        self.folder = self.root / "reports" / "perf" / "contactos" / "2026-03-02"
        self.plan = {"paquete": PKG, "principales": ["lista_visible_ms"],
                     "flujos": {"contactos": {"recorrido": "true", "metricas_usuario": [
                         {"nombre": "lista_visible_ms", "desde": {"marca": "abrir_lista"},
                          "hasta": {"marca": "lista_visible"}}]}},
                     "mejoras": [{"id": "M1", "titulo": "Precargar la lista", "estado": "aprobada",
                                  "metrica": "lista_visible_ms"}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", STATE_COST % "| `app/ContactosFragment.kt` | . | marca lista_visible | — | no |\n")
        write(self.folder / "reporte-inicial-dev.md", "x")
        write(self.folder / "fases.json", json.dumps({n: {"fecha": "2026-03-02T10:00:00"} for n in ("antes", "control")}))
        # la mejora se aplica y se guarda su diff; después se ponen las marcas
        write(self.file, WITH_IMPROVEMENT)
        self.ok_in("decidir", "--carpeta", self.rel(), "--aplicada", "M1", "--archivos", "app/ContactosFragment.kt")
        os.chdir(str(self.root))
        self.addCleanup(os.chdir, str(ROOT))

    def rel(self):
        return self.folder.relative_to(self.root)

    def run_in(self, *args):
        return subprocess.run([__import__("sys").executable, "-I", str(perf.HERE / "perf.py")] + [str(a) for a in args],
                              cwd=str(self.root), env=self.env, capture_output=True, text=True, encoding="utf-8")

    def ok_in(self, *args):
        result = self.run_in(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def marks_patch(self, name="contactos-marcas-20260302.patch", content=None):
        """Un parche con solo las marcas (contra HEAD): se arma con el archivo sin la mejora."""
        write(self.file, content or WITH_MARKS)
        data = git(self.root, "diff", "--binary", "--", "app/ContactosFragment.kt")
        path = self.folder / "parches" / name
        write(path, data)
        write(self.file, BOTH)
        return path


class CloseMixedFileTest(MixedFileBase):
    """B1: `cerrar` nunca revierte entero un archivo que también tiene una mejora."""

    def test_quita_solo_las_marcas_con_el_parche_vigente(self):
        patch = self.marks_patch()
        out = self.ok_in("cerrar", "--carpeta", self.rel(), "--simular")
        self.assertIn("app/ContactosFragment.kt: solo marcas, con %s" % patch.resolve(), out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)  # la simulación no toca nada
        out = self.ok_in("cerrar", "--carpeta", self.rel())
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_IMPROVEMENT)  # la mejora se queda
        self.assertIn("Respaldo de todo el diff", out)
        self.assertIn("El código de las mejoras sigue completo", out)
        backup = next((self.folder / "parches" / "respaldos").glob("*-respaldo-*.patch"))
        self.assertIn(b"precargar()", backup.read_bytes())
        self.assertNotIn(b"reports/perf", backup.read_bytes())  # la evidencia no es código del repo
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("solo las marcas, con", state)
        self.assertTrue(all(row["revertido"] for row in perf.temp_changes(state)))

    def test_sin_parche_de_marcas_se_detiene(self):
        write(self.file, BOTH)
        out = self.ok_in("cerrar", "--carpeta", self.rel(), "--simular")
        self.assertIn("se detiene: también tiene código de M1 y no hay parche de marcas vigente", out)
        self.assertIn("marcas --carpeta reports/perf/contactos/2026-03-02 --separar", out)
        result = self.run_in("cerrar", "--carpeta", self.rel())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no toqué nada", result.stderr)
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)
        self.assertFalse(list((self.folder / "parches").glob("*.patch")) if (self.folder / "parches").is_dir() else [])

    def test_parche_que_no_revierte_limpio_se_detiene(self):
        self.marks_patch(content=FRAGMENT.replace("        lista()\n", "        lista()\n        MarkTrace.mark(\"otra\")\n"))
        result = self.run_in("cerrar", "--carpeta", self.rel())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app/ContactosFragment.kt: el parche de marcas vigente (contactos-marcas-20260302.patch) no",
                      result.stderr)  # no revierte limpio o no coincide: se detiene igual
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)

    def test_un_parche_de_marcas_con_la_mejora_dentro_vuelve_todo_atras(self):
        # el "parche de marcas" se armó con el diff del archivo entero: lleva la mejora
        write(self.file, BOTH)
        path = self.folder / "parches" / "contactos-marcas-mal.patch"
        write(path, git(self.root, "diff", "--binary", "--", "app/ContactosFragment.kt"))
        result = self.run_in("cerrar", "--carpeta", self.rel())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lleva en este archivo líneas que no parecen marcas (precargar())", result.stderr)
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)  # nada tocado

    def test_la_comprobacion_por_lineas(self):
        checks = {("r", "a.kt"): [("M1", b"+", b"precargar()"), ("M1", b"-", b"viejo()")]}
        before = {("r", "a.kt"): {b"precargar()": 1}}
        self.assertEqual(perf.lost_lines(checks, before, {("r", "a.kt"): {b"precargar()": 1}}), [])
        self.assertEqual(perf.lost_lines(checks, before, {("r", "a.kt"): {}}), ["M1"])  # se perdió una línea agregada
        self.assertEqual(perf.lost_lines(checks, before, {("r", "a.kt"): {b"precargar()": 1, b"viejo()": 1}}),
                         ["M1"])  # volvió una línea que la mejora quitó

    def test_la_fila_que_nombra_la_mejora_cuenta_como_mixta(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["cambios"] = []  # sin diff ni archivos registrados
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "estado.md", STATE_COST % "| `app/ContactosFragment.kt` | . | marca; lleva además una línea de "
                                                      "M1 | — | no |\n")
        write(self.file, BOTH)
        out = self.ok_in("cerrar", "--carpeta", self.rel(), "--simular")
        self.assertIn("se detiene: también tiene código de M1", out)

    def test_dos_parches_sin_vigente_preguntan_cual(self):
        first = self.marks_patch("contactos-marcas-1.patch")
        second = self.marks_patch("contactos-marcas-2.patch")
        out = self.ok_in("cerrar", "--carpeta", self.rel(), "--simular")
        self.assertIn("estado.md no dice cuál es el vigente", out)
        self.assertIn("marcas --carpeta reports/perf/contactos/2026-03-02 --vigente %s" % perf.q(str(second.resolve())),
                      out)
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertEqual(steps[0]["titulo"], "¿Cuál es el parche de marcas vigente?")
        self.ok_in("marcas", "--carpeta", self.rel(), "--vigente", second)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("Parche de marcas vigente: `%s`" % second.resolve(), state)
        self.assertIn("Parche de marcas reemplazado: `%s`" % first.resolve(), state)
        marks = perf.marks_patches(self.folder, self.root.resolve())
        self.assertEqual(marks["vigente"], {self.root.resolve(): second.resolve()})
        self.assertEqual(marks["dudosos"], {})
        # fijar el otro reemplaza al de ahora: siempre uno solo
        self.ok_in("marcas", "--carpeta", self.rel(), "--vigente", first)
        marks = perf.marks_patches(self.folder, self.root.resolve())
        self.assertEqual(marks["vigente"], {self.root.resolve(): first.resolve()})
        out = self.ok_in("cerrar", "--carpeta", self.rel())
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_IMPROVEMENT)

    def test_separar_arma_el_parche_de_marcas(self):
        write(self.file, BOTH)
        out = self.ok_in("marcas", "--carpeta", self.rel(), "--separar")
        self.assertIn("Parche de marcas de . (solo las marcas", out)
        patch = next((self.folder / "parches").glob("*-marcas-*.patch"))
        self.assertIn(b"MarkTrace", patch.read_bytes())
        self.assertNotIn(b"precargar", patch.read_bytes())
        self.ok_in("cerrar", "--carpeta", self.rel())
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_IMPROVEMENT)


class CloseRealOrderTest(MixedFileBase):
    """B1 en el orden real: las marcas ya estaban cuando se guardó el diff de la mejora (lo lleva), o están pegadas a la
    mejora, o se movieron después de guardar el parche de marcas."""

    def setUp(self):
        super().setUp()
        # rehace el diff de M1 con las marcas ya puestas: cambios/M1.diff lleva la mejora y la marca
        write(self.file, BOTH)
        self.ok_in("decidir", "--carpeta", self.rel(), "--aplicada", "M1", "--archivos", "app/ContactosFragment.kt")
        self.assertIn(b"MarkTrace", (self.folder / "cambios" / "M1.diff").read_bytes())

    def test_el_diff_de_la_mejora_con_marcas_no_da_falsa_alarma(self):
        self.marks_patch()
        out = self.ok_in("cerrar", "--carpeta", self.rel())
        self.assertIn("El código de las mejoras sigue completo", out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_IMPROVEMENT)

    def test_separar_con_el_diff_que_lleva_las_marcas(self):
        write(self.file, BOTH)
        self.ok_in("marcas", "--carpeta", self.rel(), "--separar")
        patch = next((self.folder / "parches").glob("*-marcas-*.patch"))
        self.assertNotIn(b"precargar", patch.read_bytes())
        self.ok_in("cerrar", "--carpeta", self.rel())
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_IMPROVEMENT)

    def test_marca_pegada_a_la_mejora(self):
        near = WITH_IMPROVEMENT.replace("        precargar()\n", "        precargar()\n        MarkTrace.mark(\"abrir_lista\")\n")
        self.marks_patch(content=FRAGMENT.replace("        cargar()\n", "        cargar()\n        MarkTrace.mark(\"abrir_lista\")\n"))
        write(self.file, near)
        result = self.run_in("cerrar", "--carpeta", self.rel())  # el hunk de la marca no revierte sin la mejora al lado
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("se detiene", result.stdout)
        self.assertEqual(self.file.read_text(encoding="utf-8"), near)  # nada tocado

    def test_marcas_movidas_se_detiene(self):
        self.marks_patch()
        moved = WITH_IMPROVEMENT.replace("    fun uno() = 1\n", "    fun uno() = 1\n    init { MarkTrace.mark(\"lista_visible\") }\n")
        write(self.file, moved)
        result = self.run_in("cerrar", "--carpeta", self.rel())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no coincide con las marcas que hay en el archivo", result.stdout)
        self.assertEqual(self.file.read_text(encoding="utf-8"), moved)
        self.assertFalse(perf.temp_changes((self.folder / "estado.md").read_text(encoding="utf-8"))[0]["revertido"])

    def test_los_parches_que_arma_la_skill_no_son_de_marcas(self):
        self.marks_patch()
        write(self.folder / "parches" / "marcas-2026-temporales-x-1.patch", "x")
        self.assertEqual(perf.marks_patches(self.folder, self.root.resolve())["dudosos"], {})


class SiblingRepoTest(PerfBase):
    """B3: un repo hermano que settings.gradle no declara se encuentra por su nombre, y el error propone la corrección."""

    def setUp(self):
        super().setUp()
        self.root = self.dir / "proyecto"
        self.sibling = self.dir / "modulo-pagos"
        for repo in (self.root, self.sibling):
            repo.mkdir()
            init_repo(repo)
        write(self.root / "settings.gradle.kts", 'include(":app")\n')
        write(self.sibling / "pagos" / "PagosFragment.kt", "class PagosFragment\n")
        commit_all(self.root)
        commit_all(self.sibling)
        write(self.sibling / "pagos" / "PagosFragment.kt", "class PagosFragment\n// MARK pagos\n")
        self.folder = self.root / "reports" / "perf" / "pagos" / "2026-03-02"
        write(self.folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"pagos": {"recorrido": "true"}},
                                                     "mejoras": []}))
        os.chdir(str(self.root))
        self.addCleanup(os.chdir, str(ROOT))

    def run_in(self, *args):
        return subprocess.run([__import__("sys").executable, "-I", str(perf.HERE / "perf.py")] + [str(a) for a in args],
                              cwd=str(self.root), env=self.env, capture_output=True, text=True, encoding="utf-8")

    def test_el_nombre_del_repo_hermano_se_encuentra(self):
        write(self.folder / "estado.md", STATE_COST % "| `pagos/PagosFragment.kt` | modulo-pagos | marca | — | no |\n")
        top, rel = perf.resolve_repo_file(self.root.resolve(), "pagos/PagosFragment.kt", "modulo-pagos", [])
        self.assertEqual((top, rel), (self.sibling.resolve(), "pagos/PagosFragment.kt"))
        result = self.run_in("cerrar", "--carpeta", "reports/perf/pagos/2026-03-02", "--simular")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pagos/PagosFragment.kt: archivo entero (solo temporal)", result.stdout)
        self.assertIn("--corregir-repo modulo-pagos=../modulo-pagos", result.stdout)
        out = self.run_in("cerrar", "--carpeta", "reports/perf/pagos/2026-03-02", "--corregir-repo",
                          "modulo-pagos=../modulo-pagos").stdout
        self.assertIn("1 fila", out)
        self.assertEqual(perf.temp_changes((self.folder / "estado.md").read_text(encoding="utf-8"))[0]["repo"],
                         "../modulo-pagos")
        self.assertEqual(self.run_in("cerrar", "--carpeta", "reports/perf/pagos/2026-03-02").returncode, 0)
        self.assertNotIn("MARK", (self.sibling / "pagos" / "PagosFragment.kt").read_text(encoding="utf-8"))

    def test_con_otro_nombre_el_error_trae_el_comando(self):
        write(self.folder / "estado.md", STATE_COST % "| `pagos/PagosFragment.kt` | pagos-viejo | marca | — | no |\n")
        result = self.run_in("cerrar", "--carpeta", "reports/perf/pagos/2026-03-02")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("está en ../modulo-pagos", result.stderr + result.stdout)
        self.assertIn("--corregir-repo pagos-viejo=../modulo-pagos", result.stderr + result.stdout)
        self.assertIn("MARK", (self.sibling / "pagos" / "PagosFragment.kt").read_text(encoding="utf-8"))

    def test_los_repos_de_lineabase_cuentan(self):
        write(self.folder / "lineabase.json", json.dumps({"estado": "reaplicadas", "parches": [
            {"mejora": "M1", "repo": str(self.sibling.resolve()), "parche": "/no/existe.patch"}]}))
        self.assertIn(self.sibling.resolve(), perf.project_repos(self.folder, self.root.resolve(), {}))


if __name__ == "__main__":
    unittest.main()
