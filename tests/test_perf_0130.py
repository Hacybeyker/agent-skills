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
        # 0.15.0 · B4: con varios parches de marcas de la misma investigación, usa el más nuevo y lo dice (antes
        # preguntaba cuál); `marcas --vigente` sigue eligiendo otro.
        first = self.marks_patch("contactos-marcas-1.patch")
        second = self.marks_patch("contactos-marcas-2.patch")
        out = self.ok_in("cerrar", "--carpeta", self.rel(), "--simular")
        self.assertIn("hay 2 parches de marcas de esta investigación y uso el más nuevo, contactos-marcas-2.patch", out)
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertEqual(steps[0]["titulo"], "Parche de marcas")
        self.assertIn("uso el parche de marcas más nuevo de esta investigación, contactos-marcas-2.patch",
                      steps[0]["lineas"][0])
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


class ReportsAfterCloseTest(MixedFileBase):
    """B5: después de `cerrar`, `siguiente` ofrece regenerar los reportes, que dicen la hora y si el cierre está hecho."""

    def test_regenerar_despues_de_cerrar(self):
        self.marks_patch()
        write(self.folder / "reporte-final-dev.md", "# x\n\n_Reporte final · cierre pendiente: 1 cambio temporal sin "
                                                     "quitar_\n")
        old = (datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp()
        os.utime(str(self.folder / "reporte-final-dev.md"), (old, old))
        plan = perf.load_plan(self.folder / "plan.json")
        self.assertIn("faltan quitar los cambios temporales", perf.next_steps(self.folder, plan)[0])
        self.ok_in("cerrar", "--carpeta", self.rel())
        title, steps = perf.next_steps(self.folder, plan)
        self.assertEqual(title, "investigación cerrada · regenera los reportes con el cierre hecho (sin chat)")
        command = next(step["texto"] for step in steps if step["tipo"] == "terminal")
        self.assertTrue(command.endswith("reporte --carpeta reports/perf/contactos/2026-03-02 --html"), command)
        self.assertEqual(steps[-1]["tipo"], "fin")
        self.ok_in("reporte", "--carpeta", self.rel(), "--html")
        dev = (self.folder / "reporte-final-dev.md").read_text(encoding="utf-8")
        self.assertRegex(dev, r"Generado el \d{4}-\d{2}-\d{2} \d{2}:\d{2}")  # 0.16.0 · R1: en el Resumen, sin depender del reloj
        self.assertIn("cierre hecho: cambios temporales quitados", dev)
        self.assertEqual(perf.next_steps(self.folder, plan)[0], "investigación cerrada")


class BaselineHunksTest(MixedFileBase):
    """B2: `lineabase --quitar-mejoras` quita solo los hunks de la mejora si no se tocan con los de las marcas."""

    def test_quita_solo_los_hunks_de_la_mejora_y_los_reaplica(self):
        write(self.file, BOTH)
        out = self.ok_in("lineabase", "--carpeta", self.rel(), "--quitar-mejoras", "--simular")
        self.assertIn("quitaría solo los de la mejora", out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)
        out = self.ok_in("lineabase", "--carpeta", self.rel(), "--quitar-mejoras")
        self.assertIn("solo los hunks de la mejora", out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_MARKS)  # las marcas se quedan
        self.ok_in("lineabase", "--carpeta", self.rel(), "--reaplicar-mejoras")
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)

    def test_con_el_diff_de_la_mejora_guardado_con_las_marcas(self):
        write(self.file, BOTH)
        self.ok_in("decidir", "--carpeta", self.rel(), "--aplicada", "M1", "--archivos", "app/ContactosFragment.kt")
        self.ok_in("lineabase", "--carpeta", self.rel(), "--quitar-mejoras")
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_MARKS)  # la marca se queda aunque el diff la lleve
        self.ok_in("lineabase", "--carpeta", self.rel(), "--reaplicar-mejoras")
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)

    def test_hunks_que_se_tocan_se_detiene(self):
        touching = WITH_IMPROVEMENT.replace("        precargar()\n", "        precargar()\n        MarkTrace.mark(\"abrir_lista\")\n")
        write(self.file, touching)
        result = self.run_in("lineabase", "--carpeta", self.rel(), "--quitar-mejoras")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hunks que se tocan", result.stderr)
        self.assertIn("--registrar", result.stdout + result.stderr)
        self.assertEqual(self.file.read_text(encoding="utf-8"), touching)


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

    def test_una_carpeta_sin_permiso_junto_a_la_raiz_no_rompe(self):
        locked = self.dir / "sin-permiso"
        locked.mkdir()
        os.chmod(str(locked), 0)
        try:
            self.assertEqual(perf.sibling_matches(self.root, "pagos/PagosFragment.kt"), ["../modulo-pagos"])
            self.assertEqual(perf.sibling_matches(self.root, ".../PagosFragment.kt"), [])  # incompleta: no se busca
        finally:
            os.chmod(str(locked), 0o755)

    def test_los_repos_de_lineabase_cuentan(self):
        write(self.folder / "lineabase.json", json.dumps({"estado": "reaplicadas", "parches": [
            {"mejora": "M1", "repo": str(self.sibling.resolve()), "parche": "/no/existe.patch"}]}))
        self.assertIn(self.sibling.resolve(), perf.project_repos(self.folder, self.root.resolve(), {}))


if __name__ == "__main__":
    unittest.main()


# ── A · `siguiente` como guía confiable ────────────────────────────────────────

def stamp(minutes):
    """Una fecha de fases.json relativa a ahora (minutos, negativos hacia atrás)."""
    return (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


class SequenceBase(PerfBase):
    """Un flujo base y dos escenarios, con M1 aplicada: lo que comparten los tests de la secuencia."""

    FAMILY = ("contactos", "contactos_enseguida", "contactos_6s")

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "reports" / "perf" / "contactos" / "2026-03-02"
        self.plan = {"paquete": PKG, "principales": ["lista_visible_ms"], "instalar": "./gradlew :app:installProfiling",
                     "flujos": {"contactos": {"recorrido": "true", "variables": {"PERF_ESPERA_S": "4"}},
                                "contactos_enseguida": {"escenario_de": "contactos", "variables": {"PERF_ESPERA_S": "0"},
                                                        "titulo": "enseguida"},
                                "contactos_6s": {"escenario_de": "contactos", "variables": {"PERF_ESPERA_S": "6"},
                                                 "titulo": "tras 6 s"}},
                     "mejoras": [{"id": "M1", "titulo": "Precargar la lista", "estado": "aplicada", "flujo": "contactos",
                                  "metrica": "lista_visible_ms", "aplicada_en": stamp(-300)}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", STATE_COST % "")
        os.chdir(str(self.dir))
        self.addCleanup(os.chdir, str(ROOT))
        self.phases = {}

    def measure(self, phase, flow, minutes, installed="2026-03-02 09:00:00"):
        record = self.phases.setdefault(phase, {"fecha": stamp(minutes), "corridas": 0, "instalada": installed,
                                                "flujos": {}})
        record["corridas"] += 10
        record["flujos"][flow] = {"corridas": 10, "fecha": stamp(minutes), "instalada": installed}

    def probe(self, minutes, installed="2026-03-02 11:00:00", ok=True):
        self.phases["prueba"] = {"flujos": {"contactos": {"fecha": stamp(minutes), "marcas_ok": ok, "instalada": installed}}}

    def save(self, lineabase=None):
        write(self.folder / "fases.json", json.dumps(self.phases))
        if lineabase is not None:
            write(self.folder / "lineabase.json", json.dumps(lineabase))

    def state(self):
        plan = perf.load_plan(self.folder / "plan.json")
        return perf.sequence_state(self.folder, plan, "contactos")["estado"], perf.next_steps(self.folder, plan)

    def commands(self, steps):
        return [step["texto"] for step in steps if step["tipo"] == "terminal"]

    def removed(self, minutes=-120):
        return {"estado": "quitadas", "fecha": stamp(minutes), "mejoras": ["M1"],
                "parches": [{"mejora": "M1", "repo": str(self.dir), "parche": "/tmp/no-existe-m1.patch"}]}

    def old_baseline(self):
        for flow in self.FAMILY:
            self.measure("antes", flow, -400)
        self.measure("control", "contactos", -390)

    def assert_order(self, texts, *needles):
        positions = []
        for needle in needles:
            found = [i for i, text in enumerate(texts) if needle in text]
            self.assertTrue(found, "%s no está en %s" % (needle, texts))
            positions.append(found[0])
        self.assertEqual(positions, sorted(positions), texts)



class SequenceTest(SequenceBase):
    """A1–A5: la secuencia canónica con un flujo base y dos escenarios, como una tabla de estados."""

    def test_tabla_de_estados(self):
        # línea base recién iniciada
        self.old_baseline()
        self.save(self.removed())
        status, (title, steps) = self.state()
        self.assertEqual(status, "linea_base_iniciada")
        texts = self.commands(steps)
        self.assertFalse([text for text in texts if "--fase despues" in text], texts)
        self.assert_order(texts, "installProfiling", "--flujo contactos --fase antes", "--flujo contactos_enseguida --fase antes",
                          "--flujo contactos_6s --fase antes", "--flujo contactos --fase control", "--reaplicar-mejoras",
                          "--flujo contactos --prueba")
        self.assertFalse([text for text in texts if "contactos_enseguida --fase control" in text])  # A3: solo el base
        # antes a medias
        self.measure("antes", "contactos", -100)
        self.phases["antes"]["flujos"]["contactos"]["fecha"] = stamp(-100)
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "antes_a_medias")
        texts = self.commands(steps)
        self.assertNotIn("--flujo contactos --fase antes", " ".join(texts))
        self.assert_order(texts, "contactos_enseguida --fase antes", "contactos_6s --fase antes",
                          "--flujo contactos --fase control", "--reaplicar-mejoras", "--prueba")
        # antes completo
        for flow in self.FAMILY[1:]:
            self.phases["antes"]["flujos"][flow]["fecha"] = stamp(-90)
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "antes_completo")
        self.assert_order(self.commands(steps), "--flujo contactos --fase control --corridas 10 --rehacer",
                          "--reaplicar-mejoras", "installProfiling", "--prueba")
        # control a medias (con control en cada escenario)
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["escenarios"] = {"control": "todos"}
        write(self.folder / "plan.json", json.dumps(plan))
        self.phases["control"]["flujos"]["contactos"]["fecha"] = stamp(-80)
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "control_a_medias")
        self.assert_order(self.commands(steps), "contactos_enseguida --fase control", "contactos_6s --fase control",
                          "--reaplicar-mejoras")
        plan.pop("escenarios")
        write(self.folder / "plan.json", json.dumps(plan))
        # línea base lista
        status, (title, steps) = self.state()
        self.assertEqual(status, "linea_base_lista")
        self.assert_order(self.commands(steps), "--reaplicar-mejoras", "installProfiling", "--prueba")
        # mejoras reaplicadas sin instalar: nunca después antes de instalar y probar
        self.save(dict(self.removed(), estado="reaplicadas", reaplicadas=stamp(-60)))
        status, (title, steps) = self.state()
        self.assertEqual(status, "mejoras_sin_instalar")
        texts = self.commands(steps)
        self.assertFalse([text for text in texts if "--fase despues" in text], texts)
        self.assert_order(texts, "installProfiling", "--prueba")
        # instalado sin prueba
        self.phases["instalacion"] = {"instalada": "2026-03-02 11:00:00", "version": "1.0 (2)", "vista": stamp(-50)}
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "instalado_sin_prueba")
        self.assertEqual([text for text in self.commands(steps) if "installProfiling" in text], [])
        self.assertTrue(self.commands(steps)[0].endswith("--flujo contactos --prueba"))
        # prueba hecha: después del flujo base y de cada escenario, en ese orden; sin adelantar el nivel de la sesión 4
        self.probe(-40)
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "prueba_hecha")
        self.assertEqual(title, "medición después (sin chat)")
        self.assert_order(self.commands(steps), "--flujo contactos --fase despues", "contactos_enseguida --fase despues",
                          "contactos_6s --fase despues")
        self.assertFalse([step for step in steps if step["tipo"] == "chat"])
        self.assertIn("el nivel se decide al medir después", json.dumps(steps, ensure_ascii=False))
        self.assertNotIn("resultado mixto", json.dumps(steps, ensure_ascii=False))
        # después a medias
        self.measure("despues", "contactos", -30, installed="2026-03-02 11:00:00")
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "despues_a_medias")
        texts = self.commands(steps)
        self.assertNotIn("--flujo contactos --fase despues", " ".join(texts))
        self.assert_order(texts, "contactos_enseguida --fase despues", "contactos_6s --fase despues")
        # después completo: sesión 4 completa (A4), con el modelo intermedio y sin "de nuevo"
        for flow in self.FAMILY[1:]:
            self.measure("despues", flow, -20, installed="2026-03-02 11:00:00")
        self.save()
        status, (title, steps) = self.state()
        self.assertEqual(status, "despues_completo")
        self.assertEqual(title, "sesión 4 completa · línea base nueva")
        session = next(step for step in steps if step["tipo"] == "chat")
        self.assertEqual((session["modelo"], session["esfuerzo"]), ("Sonnet 5.5", "medio"))
        self.assertIn("desde cero", session["texto"])
        self.assertNotIn("actualiza la lectura", session["texto"])

    def test_el_control_es_del_flujo_base(self):
        """A2: tras medir un escenario, el control de nuevo es el del flujo base, y no desaparece."""
        self.old_baseline()
        self.measure("antes", "contactos", -100)
        self.phases["antes"]["flujos"]["contactos"]["fecha"] = self.phases["antes"]["flujos"]["contactos_enseguida"]["fecha"] = stamp(-100)
        self.save(self.removed())
        plan = perf.load_plan(self.folder / "plan.json")
        title, steps = perf.next_steps(self.folder, plan, "contactos_enseguida")
        texts = self.commands(steps)
        self.assertTrue([text for text in texts if "--flujo contactos --fase control" in text], texts)
        self.assertFalse([text for text in texts if "contactos_enseguida --fase control" in text], texts)

    def test_costo_de_los_escenarios_y_la_opcion(self):
        """A3: el costo estimado y las dos formas de bajarlo, con su consecuencia; decidir guarda la elección."""
        self.old_baseline()
        self.save(self.removed())
        status, (title, steps) = self.state()
        text = json.dumps(steps, ensure_ascii=False)
        self.assertIn("Costo de los escenarios (estimado, 90 s por corrida)", text)
        self.assertIn("control solo del flujo base: los escenarios usan su ruido", text)
        option = next(step for step in steps if step["tipo"] == "terminal" and "--corridas-escenario 5" in step["texto"])
        self.assertIn("solo distingue cambios más grandes", option["que"])
        self.ok("decidir", "--carpeta", self.folder.relative_to(self.dir), "--corridas-escenario", "5")
        plan = perf.load_plan(self.folder / "plan.json")
        self.assertEqual(plan["escenarios"], {"corridas": 5})
        self.assertEqual(perf.flow_runs(plan, "contactos_enseguida", self.folder)[0], 5)
        self.assertEqual(perf.flow_runs(plan, "contactos", self.folder)[0], 10)
        status, (title, steps) = self.state()
        self.assertTrue([t for t in self.commands(steps) if "contactos_enseguida --fase antes --corridas 5" in t])
        result = self.perf("decidir", "--carpeta", self.folder.relative_to(self.dir), "--corridas-escenario", "2")
        self.assertNotEqual(result.returncode, 0)

    def test_compuerta_de_despues(self):
        """A1 (2): `capturar --fase despues` no mide sin una prueba posterior a las mejoras con el build instalado."""
        self.old_baseline()
        self.save(dict(self.removed(), estado="reaplicadas", reaplicadas=stamp(-60)))
        plan = perf.load_plan(self.folder / "plan.json")
        build = {"instalada": "2026-03-02 11:00:00", "version": "1.0 (2)"}
        self.assertIn("no hay una corrida de prueba", perf.despues_gate(self.folder, plan, "contactos_6s", build))
        self.probe(-40, installed="2026-03-02 10:00:00")
        self.save()
        self.assertIn("no es el de la última corrida de prueba", perf.despues_gate(self.folder, plan, "contactos", build))
        self.probe(-40)
        self.save()
        self.assertIsNone(perf.despues_gate(self.folder, plan, "contactos_6s", build))
        self.save(self.removed())
        self.assertIn("las mejoras están quitadas", perf.despues_gate(self.folder, plan, "contactos", build))

    def test_costo_por_ronda(self):
        """A5: la sesión 4 de la ronda anterior se ofrece una sola vez, aparte; la nueva lleva su modelo."""
        self.old_baseline()
        self.save(self.removed())
        write(self.folder / "reporte-final-dev.md", "x")
        old = (datetime.datetime.now() - datetime.timedelta(hours=5)).timestamp()
        os.utime(str(self.folder / "reporte-final-dev.md"), (old, old))
        plan = perf.load_plan(self.folder / "plan.json")
        lines = perf.cost_lines(self.folder, plan)
        text = "\n".join(lines)
        self.assertIn("Costo de la ronda anterior a la línea base nueva (opcional; se ofrece esta vez", text)
        self.assertIn("4 · cierre (ronda anterior)", text)
        self.assertNotIn("4 · cierre (ronda anterior)", "\n".join(perf.cost_lines(self.folder, plan)))  # una sola vez
        os.utime(str(self.folder / "reporte-final-dev.md"), None)  # la sesión 4 nueva
        missing = perf.missing_costs(self.folder, plan)
        self.assertIn(("4 · cierre (línea base nueva)", "Sonnet 5.5", "medio"), missing)


class OldVersionTest(PerfBase):
    """A6: una investigación de 0.10.0 cuyo recorrido cambió entre fases no se da por cerrada sin más."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        shutil.copytree(str(ROOT / "tests" / "fixtures" / "hb-performance-0.10.0"), str(self.folder))
        script = self.dir / "reports" / "perf" / "detalle" / "recorrido.sh"
        write(script, "adb shell input tap 100 200\nsleep 6\n")
        between = datetime.datetime(2026, 4, 15, 9, 0).timestamp()
        os.utime(str(script), (between, between))
        write(self.folder / "reporte-final-dev.md", "x")
        os.chdir(str(self.dir))
        self.addCleanup(os.chdir, str(ROOT))

    def test_ofrece_el_camino_guiado(self):
        plan = perf.load_plan(self.folder / "plan.json")
        title, steps = perf.next_steps(self.folder, plan)
        self.assertEqual(title, "investigación de una versión anterior: no se puede afirmar igual contra igual")
        lines = steps[0]["lineas"]
        self.assertIn("recorrido.sh cambió entre antes y despues", lines[0])
        chat = next(step for step in steps if step["tipo"] == "chat")
        self.assertIn("instrumentar --actualizar", chat["texto"])
        self.assertTrue([step for step in steps if step["tipo"] == "terminal" and "--quitar-mejoras" in step["texto"]])
        self.assertNotIn(perf.DONE, json.dumps(steps, ensure_ascii=False))

    def test_sin_cambios_sigue_cerrada(self):
        script = self.dir / "reports" / "perf" / "detalle" / "recorrido.sh"
        before = datetime.datetime(2026, 4, 13, 9, 0).timestamp()
        os.utime(str(script), (before, before))
        plan = perf.load_plan(self.folder / "plan.json")
        title, steps = perf.next_steps(self.folder, plan)
        self.assertTrue(title.startswith("investigación cerrada"))
        # sin cierre.json (0.10.0 no lo escribía) y con los cambios temporales quitados: sugiere el DoD después de cerrar
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        write(self.folder / "estado.md", state.replace("| no |", "| sí |"))
        title, steps = perf.next_steps(self.folder, plan)
        self.assertTrue([step for step in steps if step["tipo"] == "terminal" and step["texto"].endswith("cerrar --carpeta "
                                                                                                        "inv --dod")], steps)


# ── C · Mediciones que dicen lo que miden ─────────────────────────────────────

MS = 1_000_000


def sec(ts_ms, name, dur_ms=0):
    return ("seccion", int(ts_ms * MS), int(dur_ms * MS), 0, name)


class SegmentOverlapTest(unittest.TestCase):
    """C1: tramos que se solapan, uno que contiene a otro y la marca de fin repetida sin `cual`."""

    SEGMENTS = [{"nombre": "abrir", "desde": {"marca": "NAV contactos"}, "hasta": {"marca": "MARK lista_visible"}},
                {"nombre": "detalle", "desde": {"marca": "MARK abrir_detalle"}, "hasta": {"marca": "MARK detalle"}}]

    def test_en_la_traza(self):
        markers = [sec(0, "NAV contactos"), sec(1000, "MARK lista_visible"), sec(5000, "MARK abrir_detalle"),
                   sec(6000, "MARK detalle"), sec(9000, "MARK lista_visible")]
        lines = perf.segment_overlap_warnings(markers, self.SEGMENTS)
        self.assertTrue(any("'MARK lista_visible') sale 2 veces" in line and '"cual": "primera" en segmentos[0].hasta'
                            in line and "recalcular" in line for line in lines), lines)
        # 0.15.0 · C2: dice que se solapan de verdad y el cambio exacto del plan
        self.assertTrue(any(line.startswith("el tramo 'abrir' contiene al tramo 'detalle' (se solapan de verdad): sus "
                                            "métricas de hilo y frames incluyen las del otro. Para corregirlo, ")
                            for line in lines), lines)
        segments = [dict(self.SEGMENTS[0], hasta={"marca": "MARK lista_visible", "cual": "primera"}), self.SEGMENTS[1]]
        self.assertEqual(perf.segment_overlap_warnings(markers, segments), [])

    def test_en_el_plan(self):
        plan = {"flujos": {"contactos": {"segmentos": [
            {"nombre": "abrir", "desde": {"marca": "NAV contactos"}, "hasta": {"marca": "MARK lista_visible"}},
            {"nombre": "volver", "desde": {"marca": "NAV volver"}, "hasta": {"marca": "MARK lista_visible"}}]}}}
        lines = perf.segment_plan_warnings(plan)
        self.assertEqual(len(lines), 1)
        self.assertIn('agrega "cual": "primera" en segmentos[0].hasta, segmentos[1].hasta', lines[0])

    def test_metricas_identicas_corrida_a_corrida(self):
        data = HEADER + rows("antes", "contactos", "abrir hilo_max_ms", [97, 92, 128]) + \
            rows("antes", "contactos", "detalle hilo_max_ms", [97, 92, 128]) + \
            rows("antes", "contactos", "volver hilo_max_ms", [40, 41, 39])
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        path = Path(holder.name) / "metricas.csv"
        write(path, data)
        notes = perf.identical_segment_notes(perf.read_rows(path))
        self.assertEqual(len(notes), 1)
        self.assertIn("'abrir hilo_max_ms' y 'detalle hilo_max_ms' son idénticas en las 3 corridas de antes", notes[0])


class RepeatedServiceTest(unittest.TestCase):
    """C2: el mismo servicio más de una vez en una misma acción (un tramo), aunque la segunda llamada sea 3 s después."""

    SEGMENTS = [{"nombre": "abrir", "desde": {"marca": "NAV contactos"}, "hasta": {"marca": "MARK lista_visible",
                                                                                   "cual": "ultima"}},
                {"nombre": "volver", "desde": {"marca": "NAV volver"}, "hasta": {"marca": "MARK volver_visible"}}]

    def test_mismo_tramo_y_tramos_distintos(self):
        sections = [sec(0, "NAV contactos"), sec(50, "SCREEN ContactosFragment onStart"),
                    sec(100, "HTTP GET api/v1/contactos", 200), sec(3000, "SCREEN ContactosFragment onResume"),
                    sec(3100, "HTTP GET api/v1/contactos", 200), sec(4000, "MARK lista_visible"),
                    sec(6000, "NAV volver"), sec(6100, "HTTP GET api/v1/contactos", 200), sec(7000, "MARK volver_visible")]
        metrics, detail = perf.repeated_metrics(sections, sections, self.SEGMENTS)
        values = {name: value for name, value, _, _ in metrics}
        self.assertEqual(values["abrir red GET api/v1/contactos repetidas"], 1)
        self.assertEqual(values["volver red GET api/v1/contactos repetidas"], 0)  # entre tramos no es problema
        lines = perf.repeated_lines(detail)
        self.assertEqual(lines, ["GET api/v1/contactos se pidió 2 veces en el tramo abrir (antes de cada una: SCREEN "
                                 "ContactosFragment onStart, SCREEN ContactosFragment onResume): hallazgo candidato de la "
                                 "sesión 2"])
        # con una ventana de 2 s en el plan, la segunda (3 s después) ya no cuenta
        segments = [dict(self.SEGMENTS[0], repetidas_ventana_s=2), self.SEGMENTS[1]]
        values = {name: value for name, value, _, _ in perf.repeated_metrics(sections, sections, segments)[0]}
        self.assertEqual(values["abrir red GET api/v1/contactos repetidas"], 0)

    def test_al_terminar_la_fase(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        path = Path(holder.name) / "metricas.csv"
        write(path, HEADER + rows("antes", "contactos", "abrir red GET api/v1/contactos repetidas", [1, 1, 0], "llamadas"))
        lines = perf.repeated_phase_lines(perf.read_rows(path), "antes", "contactos")
        self.assertEqual(lines, ["GET api/v1/contactos se pidió más de una vez en el tramo abrir (mediana: 1 llamada de más "
                                 "por corrida, en 2 de 3 corridas): hallazgo candidato de la sesión 2"])


class ScenarioWindowTest(PerfBase):
    """C3 y C4: un escenario que no cambia lo que entra en la ventana, y de dónde sale el dato de una precarga."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = {"paquete": PKG, "flujos": {
            "contactos": {"recorrido": "true", "variables": {"PERF_ESPERA_S": "4"}, "servicios": ["contactos"]},
            "contactos_enseguida": {"escenario_de": "contactos", "variables": {"PERF_ESPERA_S": "0"}}},
            "mejoras": [{"id": "M1", "titulo": "Precargar", "estado": "aplicada", "flujo": "contactos",
                         "metrica": "lista_visible_ms", "servicios": ["contactos"]}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        data = HEADER
        for flow in ("contactos", "contactos_enseguida"):
            for phase in ("antes", "despues"):
                data += rows(phase, flow, "red GET api/v1/contactos llamadas", [1, 1, 1], "llamadas")
        write(self.folder / "metricas.csv", data)

    def timeline(self, phase, flow, run, calls):
        write(self.folder / phase / ("%s_%d.linea.json" % (flow, run)), json.dumps(
            {"llamadas": calls, "marcas": [["NAV contactos", 0.0], ["MARK lista_visible", 30.0]]}))

    def test_escenario_sin_efecto(self):
        for flow in ("contactos", "contactos_enseguida"):
            for run in (1, 2, 3):
                self.timeline("despues", flow, run, [["GET api/v1/contactos", -2700.0, -10.0]])
        plan = perf.load_plan(self.folder / "plan.json")
        notes = perf.scenario_effect_notes(self.folder, plan, "despues", "contactos_enseguida")
        self.assertEqual(len(notes), 1)
        self.assertIn("el escenario contactos_enseguida no cambió lo que pasa dentro de la ventana", notes[0])
        self.assertIn("la variable PERF_ESPERA_S no tiene efecto con este `preparar`", notes[0])
        self.assertIn('"traza_desde_preparar": true', notes[0])
        # si en un escenario la llamada entra en la ventana, sí cambió algo
        self.timeline("despues", "contactos_enseguida", 2, [["GET api/v1/contactos", 5.0, 2700.0]])
        self.assertEqual(perf.scenario_effect_notes(self.folder, plan, "despues", "contactos_enseguida"), [])

    def test_origen_del_dato(self):
        self.timeline("despues", "contactos", 1, [["GET api/v1/contactos", -2700.0, -10.0]])
        self.timeline("despues", "contactos", 2, [["GET api/v1/contactos", 5.0, 2700.0]])
        self.timeline("despues", "contactos", 3, [])
        plan = perf.load_plan(self.folder / "plan.json")
        found = perf.data_origin(self.folder, plan, "despues", "contactos", plan["mejoras"][0])
        self.assertEqual(found["conteo"], {"precarga": 1, "red en el tramo": 1, "sin llamada": 1})
        # lo que imprime `capturar` al terminar la fase queda en las advertencias que leen las sesiones 2 y 4
        notes = perf.phase_notes(self.folder, plan, perf.read_rows(self.folder / "metricas.csv"), "despues", "contactos")
        perf.save_phase_notes(self.folder, "despues", "contactos", [line[2:] for line in notes])
        lines = perf.warnings_lines(self.folder, plan)
        self.assertTrue([line for line in lines if "Origen del dato de M1" in line and "precarga 1" in line], lines)
        # otra vez, con otro resultado: reemplaza, no suma; sin avisos, no queda ninguno
        perf.save_phase_notes(self.folder, "despues", "contactos", ["Origen del dato de M1 (contactos, despues): precarga 3"])
        lines = [line for line in perf.warnings_lines(self.folder, plan) if "Origen del dato" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn("precarga 3", lines[0])
        perf.save_phase_notes(self.folder, "despues", "contactos", [])
        self.assertFalse([line for line in perf.warnings_lines(self.folder, plan) if "Origen del dato" in line])
        self.assertEqual(perf.origin_lines(self.folder, plan, "despues", "contactos"),
                         ["Origen del dato de M1 (contactos, despues): GET api/v1/contactos en la ventana: precarga 1 · red "
                          "en el tramo 1 · sin llamada 1 (de 3 corridas)"])

    def test_traza_desde_preparar_entra_en_la_huella(self):
        spec = dict(self.plan["flujos"]["contactos"], preparar="bash preparar.sh")
        first = perf.flow_fingerprints(spec)
        second = perf.flow_fingerprints(dict(spec, traza_desde_preparar=True))
        self.assertNotEqual(first["recorrido"], second["recorrido"])
        self.assertEqual(perf.changed_fields(first, second), ["traza_desde_preparar"])


class ForeignAndPlanFieldsTest(PerfBase):
    """C5: un servicio ajeno no mejora ni empeora el flujo, ni en `capturar`; C6: los campos de presentación no avisan."""

    def test_ajeno_sin_veredicto_en_los_dos_sentidos(self):
        folder = self.dir / "inv"
        plan = {"paquete": PKG, "flujos": {"contactos": {"recorrido": "true", "servicios": ["contactos"]}}, "mejoras": []}
        write(folder / "plan.json", json.dumps(plan))
        data = HEADER
        for phase, home in (("antes", [900, 905, 910, 899, 902]), ("despues", [300, 305, 310, 299, 302])):
            data += rows(phase, "contactos", "red GET api/v1/contactos llamadas", [1] * 5, "llamadas")
            data += rows(phase, "contactos", "red GET api/v1/home llamadas", [1] * 5, "llamadas")
            data += rows(phase, "contactos", "red GET api/v1/home ms", home, family="e2e")
        write(folder / "metricas.csv", data)
        rows_ = perf.read_rows(folder / "metricas.csv")
        plan = perf.load_plan(folder / "plan.json")
        results = perf.compare(rows_, plan=plan)[0]
        before = next(r for r in results if r["metrica"] == "red GET api/v1/home ms")["veredicto"]
        self.assertEqual(before, "mejora")
        perf.attribute_network(results, rows_, plan, folder)
        self.assertEqual(next(r for r in results if r["metrica"] == "red GET api/v1/home ms")["veredicto"],
                         perf.FOREIGN_VERDICT)
        table, _ = perf.summary_rows(rows_, plan, phases=("antes",), everything=True, folder=folder)
        home = next(row for row in table if row[2] == "red GET api/v1/home ms")
        self.assertIn("ajeno · sin veredicto", home[-1])
        own = next(row for row in table if row[2] == "red GET api/v1/contactos llamadas")
        self.assertNotIn("ajeno", own[-1])
        out = self.ok("comparar", folder / "metricas.csv")
        self.assertIn("ajeno · sin veredicto (2 métricas, aparte", out)  # sus llamadas y su tiempo
        self.assertNotIn("✖", out)  # ninguna regresión

    def test_campos_de_presentacion_no_cuentan(self):
        spec = {"recorrido": "true", "preparar": "bash preparar.sh", "titulo": "tras 4 s",
                "segmentos": [{"nombre": "abrir", "titulo": "Abrir", "desde": {"marca": "A"}, "hasta": {"marca": "B"}}]}
        first = perf.flow_fingerprints(spec)
        retitled = dict(spec, titulo="otro", etiquetas={"x": "y"},
                        segmentos=[dict(spec["segmentos"][0], titulo="Abrir la lista")])
        self.assertEqual(perf.flow_fingerprints(retitled), first)
        self.assertEqual(perf.changed_fields(first, perf.flow_fingerprints(dict(spec, preparar="bash otro.sh"))),
                         ["preparar"])
        self.assertEqual(perf.changed_fields({"recorrido": "x"}, first), [])  # una fase de 0.12.0: sin el dato
        self.assertTrue(set(perf.MEASURE_FIELDS).isdisjoint(perf.PRESENTATION_FIELDS))

    def test_version_at_least(self):
        self.assertTrue(perf.version_at_least("0.13.0", "0.12.0"))
        self.assertTrue(perf.version_at_least("0.14.1", "0.12.0"))
        self.assertFalse(perf.version_at_least("0.10.0", "0.12.0"))
        self.assertFalse(perf.version_at_least(None, "0.12.0"))


# ── D · Herramientas de setup ─────────────────────────────────────────────────

class PropertySetupTest(PerfBase):
    """D1: `instrumentar --actualizar` en un proyecto que mide con -Pperf no crea la variante `profiling`."""

    def test_actualizar_con_pperf(self):
        from test_perf import GRADLE_KTS
        gradle = 'val perf = providers.gradleProperty("perf").isPresent\n' + GRADLE_KTS
        write(self.dir / "app" / "build.gradle.kts", gradle)
        self.ok("instrumentar", "--modulo", self.dir / "app", "--paquete", "com.ejemplo.perf", "--sin-fragments")
        shutil.rmtree(str(self.dir / "app" / "src" / "profiling"), ignore_errors=True)
        self.assertTrue(perf.perf_property_setup(self.dir / "app", self.dir))
        out = self.ok("instrumentar", "--modulo", self.dir / "app", "--paquete", "com.ejemplo.perf", "--sin-fragments",
                      "--actualizar")
        self.assertFalse((self.dir / "app" / "src" / "profiling").exists())
        self.assertIn("Setup con la propiedad de Gradle -Pperf", out)
        self.assertIn("Falta: nada.", out)
        self.assertNotIn("Falta pegar", out)
        self.assertNotIn("(nueva)", out)

    def test_por_la_linea_de_agents(self):
        from test_perf import GRADLE_KTS
        write(self.dir / "app" / "build.gradle.kts", GRADLE_KTS)
        self.assertFalse(perf.perf_property_setup(self.dir / "app", self.dir))
        write(self.dir / "AGENTS.md", "# x\n\n## Rendimiento\n\n- Instalar: `./gradlew :app:installDebug -Pperf`\n")
        self.assertTrue(perf.perf_property_setup(self.dir / "app", self.dir))


class RequestUsedTest(PerfBase):
    """D2: el pedido del setup que ya tiene una investigación no se ofrece como sesión 1 nueva."""

    def test_pedido_con_investigacion(self):
        request = self.dir / "reports" / "perf" / "setup" / "pedido.json"
        write(request, json.dumps({"texto": "medir la lista", "flujo": "lista"}))
        old = (datetime.datetime.now() - datetime.timedelta(days=1)).timestamp()
        os.utime(str(request), (old, old))
        self.assertEqual(perf.request_investigations(self.dir, request), [])
        write(self.dir / "reports" / "perf" / "lista" / "2026-03-02" / "estado.md", "# x\n")
        found = perf.request_investigations(self.dir, request)
        self.assertEqual([(path.name, closed) for path, closed in found], [("2026-03-02", False)])
        write(self.dir / "reports" / "perf" / "lista" / "2026-03-02" / "reporte-final-dev.md", "x")
        self.assertTrue(perf.request_investigations(self.dir, request)[0][1])


# ── E · Reporte de gerencia ───────────────────────────────────────────────────

class VerdictLabelTest(PerfBase):
    """E1: la misma etiqueta de veredicto, con texto, en el técnico y en "Resultado" de gerencia, con su leyenda."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        plan = {"paquete": PKG, "principales": ["lista_visible_ms", "abrir hilo_max_ms", "volver_ms"],
                "etiquetas": {"lista_visible_ms": "mostrar la lista", "volver_ms": "volver a la lista"},
                "flujos": {"contactos": {"recorrido": "true"}},
                "mejoras": [{"id": "M1", "titulo": "Precargar la lista", "estado": "aplicada", "metrica": "lista_visible_ms"}]}
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "estado.md", STATE_COST % "" + "\n## Resumen para gerencia\n\nMostrar la lista es más rápido.\n")
        data = HEADER
        data += rows("antes", "contactos", "lista_visible_ms", [2400, 2350, 2500, 2450, 2380])
        data += rows("control", "contactos", "lista_visible_ms", [2390, 2360, 2490, 2460, 2370])
        data += rows("despues", "contactos", "lista_visible_ms", [400, 420, 380, 410, 440])
        data += rows("antes", "contactos", "abrir hilo_max_ms", [90, 91, 92, 93, 94])
        data += rows("control", "contactos", "abrir hilo_max_ms", [90, 92, 91, 94, 93])
        data += rows("despues", "contactos", "abrir hilo_max_ms", [91, 92, 90, 93, 94])
        data += rows("antes", "contactos", "volver_ms", [100, 400, 120, 380, 110])
        data += rows("control", "contactos", "volver_ms", [110, 390, 100, 400, 120])
        data += rows("despues", "contactos", "volver_ms", [30, 35, 32, 31, 33])
        write(self.folder / "metricas.csv", data)

    def test_misma_etiqueta_en_los_dos_reportes(self):
        self.ok("reporte", "--carpeta", self.folder, "--html")
        dev = (self.folder / "reporte-final-dev.md").read_text(encoding="utf-8")
        business = (self.folder / "reporte-final-gerencia.md").read_text(encoding="utf-8")
        plan = perf.load_plan(self.folder / "plan.json")
        results = perf.compare(perf.read_rows(self.folder / "metricas.csv"), plan=plan)[0]
        for metric in plan["principales"]:
            r = next(item for item in results if item["metrica"] == metric)
            label = perf.verdict_label(r)
            # 0.15.0 · H3: la comparación completa (en el anexo) nombra cada medida en palabras
            row = next(line for line in dev.splitlines() if line.startswith("| contactos | %s |" % perf.plain_metric(
                metric, plan)))
            self.assertTrue(row.rstrip(" |").endswith("[%s]" % label), row)
            line = next(line for line in business.split("## Resultado")[1].splitlines()
                        if line.startswith(perf.plain_metric(metric, plan)))
            self.assertTrue(line.endswith("[%s]" % label), line)  # 0.16.0 · R5: el título del gráfico con su etiqueta
        result = business[business.index("## Resultado"):]
        self.assertIn("Qué significa cada etiqueta:", result)
        self.assertIn("- [Mejora] el cambio es mayor que la variación normal entre mediciones", result)
        html = (self.folder / "reporte-final-gerencia.html").read_text(encoding="utf-8")
        self.assertIn('<span class="chip c-ok">Mejora</span>', html)  # 0.16.0 · R1: la etiqueta como chip
        self.assertNotIn("[Mejora]</", html)  # en el HTML va con texto y color, no con corchetes
        dev_html = (self.folder / "reporte-final-dev.html").read_text(encoding="utf-8")
        self.assertIn('<span class="chip c-ok">Mejora</span>', dev_html)

    def test_orientativo_y_los_demas(self):
        r = {"veredicto": "mejora", "avisos": [perf.MARK_CHANGED]}
        self.assertEqual(perf.verdict_label(r), "Orientativo")
        self.assertEqual(perf.verdict_label({"veredicto": "mejora", "avisos": ["inestable"]}), "Orientativo")
        self.assertEqual(perf.verdict_label({"veredicto": "dentro del ruido", "avisos": []}),
                         "Dentro de la variación normal")  # 0.16.0 · R5: en palabras
        self.assertEqual(perf.verdict_label({"veredicto": perf.COST_VERDICT, "avisos": []}), "Costo conocido")
        self.assertEqual(perf.verdict_label({"veredicto": perf.FOREIGN_VERDICT, "avisos": []}), "Ajeno · sin veredicto")
        legend = perf.label_legend({"Dentro de la variación normal"})
        self.assertEqual(legend, "- [Dentro de la variación normal] la diferencia es menor que la variación normal entre mediciones; no "
                                 "se puede afirmar que cambió.")
        for label in set(perf.VERDICT_LABELS.values()) | {"Orientativo"}:
            self.assertIn(label, perf.LABEL_LEGEND)  # cada etiqueta tiene su línea para un lector no técnico


# ── Ensayo de punta a punta, sin dispositivo ──────────────────────────────────

class EndToEndRehearsalTest(PerfBase):
    """Flujo base + dos escenarios, línea base rehecha, una mejora en un archivo que también tiene marcas, en un repo
    hermano que settings.gradle no declara: cada paso de `siguiente` es el correcto, y `cerrar` deja la mejora intacta."""

    def setUp(self):
        super().setUp()
        self.root = self.dir / "proyecto"
        self.sibling = self.dir / "modulo-pagos"
        for repo in (self.root, self.sibling):
            repo.mkdir()
            init_repo(repo)
        write(self.root / "settings.gradle.kts", 'include(":app")\n')
        commit_all(self.root)
        self.file = self.sibling / "app" / "ContactosFragment.kt"
        write(self.file, FRAGMENT)
        commit_all(self.sibling)
        self.folder = self.root / "reports" / "perf" / "contactos" / "2026-03-02"
        self.rel = "reports/perf/contactos/2026-03-02"
        plan = {"paquete": PKG, "principales": ["lista_visible_ms"], "instalar": "./gradlew :app:installProfiling",
                "flujos": {"contactos": {"recorrido": "true", "variables": {"PERF_ESPERA_S": "4"}},
                           "contactos_enseguida": {"escenario_de": "contactos", "variables": {"PERF_ESPERA_S": "0"}},
                           "contactos_6s": {"escenario_de": "contactos", "variables": {"PERF_ESPERA_S": "6"}}},
                "mejoras": [{"id": "M1", "titulo": "Precargar la lista", "estado": "aprobada", "flujo": "contactos",
                             "metrica": "lista_visible_ms"}]}
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "estado.md", STATE_COST % "| `app/ContactosFragment.kt` | modulo-pagos | marca lista_visible | "
                                                      "— | no |\n")
        write(self.folder / "reporte-inicial-dev.md", "x")
        write(self.file, WITH_MARKS)  # las marcas primero, como en una investigación real
        os.chdir(str(self.root))
        self.addCleanup(os.chdir, str(ROOT))
        self.run_ok("marcas", "--carpeta", self.rel, "--separar")
        write(self.file, BOTH)  # la sesión 3 aplica la mejora
        self.run_ok("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "app/ContactosFragment.kt",
                    "--repo", "../modulo-pagos")

    def run_ok(self, *args):
        result = subprocess.run([__import__("sys").executable, "-I", str(perf.HERE / "perf.py")] + [str(a) for a in args],
                                cwd=str(self.root), env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def phases(self, data):
        write(self.folder / "fases.json", json.dumps(data))

    def steps(self):
        plan = perf.load_plan(self.folder / "plan.json")
        title, steps = perf.next_steps(self.folder, plan)
        return title, [step["texto"] for step in steps if step["tipo"] == "terminal"], steps

    def test_ensayo(self):
        family = ("contactos", "contactos_enseguida", "contactos_6s")

        def phase(minutes, flows):
            return {"fecha": stamp(minutes), "corridas": 10 * len(flows), "instalada": "2026-03-02 09:00:00",
                    "flujos": {flow: {"corridas": 10, "fecha": stamp(minutes)} for flow in flows}}

        # una línea base vieja; las marcas cambiaron: la línea base se rehace sin la mejora
        self.phases({"antes": phase(-500, family), "control": phase(-490, ["contactos"])})
        out = self.run_ok("lineabase", "--carpeta", self.rel, "--quitar-mejoras")
        self.assertIn("solo los hunks de la mejora", out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_MARKS)  # sin la mejora, con las marcas
        title, texts, _ = self.steps()
        self.assertEqual(title, "rehacer la línea base sin las mejoras (sin chat)")
        self.assertFalse([text for text in texts if "--fase despues" in text])
        # antes y control medidos de nuevo
        record = json.loads((self.folder / "lineabase.json").read_text(encoding="utf-8"))
        record["fecha"] = stamp(-200)
        write(self.folder / "lineabase.json", json.dumps(record))
        self.phases({"antes": phase(-100, family), "control": phase(-90, ["contactos"])})
        title, texts, _ = self.steps()
        self.assertTrue(texts[0].endswith("lineabase --carpeta %s --reaplicar-mejoras" % self.rel), texts)
        self.run_ok("lineabase", "--carpeta", self.rel, "--reaplicar-mejoras")
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)
        # reaplicadas: instalar y probar antes de cualquier después
        title, texts, _ = self.steps()
        self.assertEqual(title, "instala y prueba con las mejoras (sin chat)")
        self.assertFalse([text for text in texts if "--fase despues" in text])
        data = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))
        data["prueba"] = {"flujos": {"contactos": {"fecha": stamp(5), "marcas_ok": True, "instalada": "2026-03-02 11:00:00"}}}
        self.phases(data)
        title, texts, _ = self.steps()
        self.assertEqual(title, "medición después (sin chat)")
        self.assertEqual([text.split("--flujo ")[1].split(" ")[0] for text in texts], list(family))
        for flow in family:
            data["despues"] = data.get("despues") or {"fecha": stamp(10), "corridas": 0, "flujos": {}}
            data["despues"]["flujos"][flow] = {"corridas": 10, "fecha": stamp(10)}
            data["despues"]["corridas"] += 10
        self.phases(data)
        title, _, steps = self.steps()
        self.assertEqual(title, "sesión 4 completa · línea base nueva")
        # el cierre: solo las marcas, en el repo hermano, y la mejora queda intacta
        out = self.run_ok("cerrar", "--carpeta", self.rel, "--simular")
        self.assertIn("app/ContactosFragment.kt: solo marcas, con", out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), BOTH)
        self.run_ok("cerrar", "--carpeta", self.rel)
        self.assertEqual(self.file.read_text(encoding="utf-8"), WITH_IMPROVEMENT)



class ReviewFixesTest(SequenceBase):
    """Lo que encontró la revisión del commit de código: la secuencia no se salta una mejora aprobada ni una línea base
    que cambió, el escenario sin control usa el ruido del base, y dos avisos sin falsos positivos."""

    def test_una_mejora_aprobada_va_antes_que_despues(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"].append({"id": "M2", "titulo": "Otra", "estado": "aprobada", "metrica": "lista_visible_ms"})
        write(self.folder / "plan.json", json.dumps(plan))
        self.old_baseline()
        self.probe(-40)
        self.save()
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertEqual(title, "sesión 3 · M2")

    def test_un_recorrido_que_cambio_pide_la_linea_base(self):
        spec = perf.load_plan(self.folder / "plan.json")["flujos"]["contactos"]
        self.old_baseline()
        prints = perf.flow_fingerprints(spec)
        prints["recorrido"] = "otro"
        self.phases["antes"]["flujos"]["contactos"]["plan"] = prints
        self.probe(-40)
        self.save()
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertTrue(title.startswith("rehacer la línea base"), title)
        texts = self.commands(steps)
        self.assertEqual(len(texts), 1)  # con escenarios, solo quitar las mejoras: después sigue la secuencia completa
        self.assertTrue(texts[0].endswith("--quitar-mejoras"), texts)
        self.assertFalse([text for text in texts if "--fase despues" in text])
        # sin mejoras aplicadas, el antes de cada escenario también se rehace
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["estado"] = "propuesta"
        write(self.folder / "plan.json", json.dumps(plan))
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        texts = self.commands(steps)
        self.assert_order(texts, "--flujo contactos --fase antes", "contactos_enseguida --fase antes",
                          "contactos_6s --fase antes")

    def test_el_escenario_usa_el_ruido_del_base(self):
        data = HEADER
        for flow in ("contactos", "contactos_enseguida"):
            data += rows("antes", flow, "lista_visible_ms", [1000, 1010, 990, 1005, 995])
            data += rows("despues", flow, "lista_visible_ms", [985, 990, 980, 988, 983])
        data += rows("control", "contactos", "lista_visible_ms", [1020, 1025, 1015, 1022, 1018])
        write(self.folder / "metricas.csv", data)
        results = perf.compare(perf.read_rows(self.folder / "metricas.csv"),
                               plan=perf.load_plan(self.folder / "plan.json"))[0]
        verdicts = {r["flujo"]: r for r in results}
        self.assertEqual(verdicts["contactos"]["veredicto"], verdicts["contactos_enseguida"]["veredicto"])
        self.assertIn(perf.BASE_NOISE, verdicts["contactos_enseguida"]["avisos"])

    def test_series_constantes_no_son_tramos_solapados(self):
        data = HEADER + rows("antes", "contactos", "abrir jank_app_pct", [0, 0, 0]) + \
            rows("antes", "contactos", "volver jank_app_pct", [0, 0, 0])
        write(self.folder / "metricas.csv", data)
        self.assertEqual(perf.identical_segment_notes(perf.read_rows(self.folder / "metricas.csv")), [])

    def test_sin_mejora_no_hay_aviso_de_escenario_sin_efecto(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"] = []
        write(self.folder / "plan.json", json.dumps(plan))
        for flow in self.FAMILY:
            write(self.folder / "antes" / ("%s_1.linea.json" % flow), json.dumps(
                {"llamadas": [["GET api/v1/contactos", 10.0, 900.0]], "marcas": [["MARK lista_visible", 950.0]]}))
        self.assertEqual(perf.scenario_effect_notes(self.folder, perf.load_plan(self.folder / "plan.json"), "antes",
                                                    "contactos"), [])
