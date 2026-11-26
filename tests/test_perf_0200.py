"""Tests de hb-performance 0.20.0: la base común de reportes (`<base>/performance`, con las carpetas de antes), el índice
`<base>/INDEX.md`, la rama y el commit de cada unidad en fuente por fase, el paso a fuente de la sesión 1 desde el tag
de la versión fijada y la carpeta de contexto enlazada (escribir sobre la ruta real, rutas relativas y worktrees). Los
datos son inventados."""
import contextlib
import datetime
import io
import json
import os
import unittest
from pathlib import Path

from helpers import commit_all, git, init_repo, write
from test_perf import PKG, DeviceBase, PerfBase, perf
from test_perf_0140 import ModulesBase
from test_perf_0150 import TriageBase
from test_perf_0160 import CaptureBase

TODAY = datetime.date.today().isoformat()
INDEX_TOP = ("# Índice de reportes\n\nUna fila por tarea. Cada skill agrega o actualiza solo sus filas (clave: Skill + "
             "Slug).\n\n| Fecha | Skill | Slug | Tipo | Estado | Ruta |\n| --- | --- | --- | --- | --- | --- |\n")
OTHER_ROW = ("| 2026-11-20 | hb-implement | perfil-de-usuario | feature | DoD PASS | "
             "[implementation/2026-11-20-perfil-de-usuario/report.html](implementation/2026-11-20-perfil-de-usuario/report.html) |")


def index_rows(path):
    """Las filas de la tabla del índice, como listas de celdas."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and not line.startswith(("| Fecha", "| ---")):
            rows.append([cell.strip() for cell in line.strip().strip("|").split(" | ")])
    return rows


def perf_rows(path):
    return [row for row in index_rows(path) if row[1] == "hb-performance"]


# ── Base común de reportes (hallazgo 19) ─────────────────────────────────────

class ReportsBaseTest(PerfBase):
    """`Carpeta de reportes:` es la base de todas las skills; sin `Carpeta de investigaciones:`, las investigaciones
    nuevas van en `<base>/performance` y las de antes se siguen buscando en reports/perf y en <base>/perf."""

    def test_la_base_sale_de_la_linea_de_agents_md(self):
        self.assertEqual(perf.reports_base(self.dir), self.dir / "reports")  # sin AGENTS.md
        for line, expected in (("- Carpeta de reportes: `contexto/reports`", "contexto/reports"),
                               ("Carpeta de los reportes: `contexto/reports/{fecha}/{slug}`", "contexto/reports"),
                               ("- **Reports folder:** `reports/{fecha}-{slug}`", "reports"),
                               ("- Carpeta de reportes: docs/informes.", "docs/informes")):
            write(self.dir / "AGENTS.md", "# P\n\n## Reglas del proyecto\n\n%s\n" % line)
            self.assertEqual(perf.reports_base(self.dir), self.dir / expected, line)
        write(self.dir / "AGENTS.md", "# P\n\n```\nCarpeta de reportes: `dentro/de/un/bloque`\n```\n")
        self.assertEqual(perf.reports_base(self.dir), self.dir / "reports")  # un bloque de código no cuenta
        write(self.dir / "AGENTS.md", "- Carpeta de reportes: `~/ia/reports`\n")
        self.assertEqual(perf.reports_base(self.dir), Path(os.path.expanduser("~/ia/reports")))

    def test_investigaciones_nuevas_en_performance_y_las_de_antes_se_buscan(self):
        self.assertEqual(perf.investigations_base(self.dir), self.dir / "reports" / "performance")
        self.assertEqual(perf.legacy_investigation_bases(self.dir), [self.dir / "reports" / "perf"])
        write(self.dir / "AGENTS.md", "## Reglas del proyecto\n\n- Carpeta de reportes: `contexto/reports`\n")
        self.assertEqual(perf.investigations_base(self.dir), self.dir / "contexto" / "reports" / "performance")
        self.assertEqual(perf.legacy_investigation_bases(self.dir),
                         [self.dir / "reports" / "perf", self.dir / "contexto" / "reports" / "perf"])
        # con la línea propia de rendimiento, manda ella y no se busca en otro lado
        write(self.dir / "AGENTS.md", "## Reglas del proyecto\n\n- Carpeta de reportes: `contexto/reports`\n\n"
                                      "## Rendimiento\n\n- Carpeta de investigaciones: `ctx/perf/investigaciones`\n")
        self.assertEqual(perf.investigations_base(self.dir), self.dir / "ctx" / "perf" / "investigaciones")
        self.assertEqual(perf.legacy_investigation_bases(self.dir), [])
        self.assertEqual(perf.investigation_bases(self.dir), [self.dir / "ctx" / "perf" / "investigaciones"])

    def test_el_pedido_del_setup_se_busca_tambien_donde_quedaba_antes(self):
        write(self.dir / "AGENTS.md", "- Carpeta de reportes: `contexto/reports`\n")
        self.assertEqual(perf.request_candidates(self.dir), [
            self.dir / "contexto/reports/performance/setup/pedido.json", self.dir / "reports/perf/setup/pedido.json",
            self.dir / "contexto/reports/perf/setup/pedido.json"])

    def test_los_parches_del_setup_que_ya_estaban_siguen_ahi(self):
        self.assertEqual(perf.setup_patches_dir(self.dir), self.dir / "reports/performance/setup/parches")
        (self.dir / "reports/perf/setup/parches").mkdir(parents=True)
        self.assertEqual(perf.setup_patches_dir(self.dir), self.dir / "reports/perf/setup/parches")
        (self.dir / "reports/performance/setup/parches").mkdir(parents=True)  # la nueva, si ya existe, gana
        self.assertEqual(perf.setup_patches_dir(self.dir), self.dir / "reports/performance/setup/parches")


class NewFolderTest(DeviceBase):
    """`nuevo` sin --carpeta: la investigación va a `<base>/performance/<flujo>/<fecha>` y deja su fila en el índice."""

    def test_sin_lineas_va_a_reports_performance(self):
        out = self.ok("nuevo", "--paquete", PKG, "--flujo", "Lista de clientes", "--serial", "emulator-5554")
        self.assertIn("✔ Carpeta de la investigación: reports/performance/lista-de-clientes/%s (por defecto)" % TODAY, out)
        self.assertTrue((self.dir / "reports/performance/lista-de-clientes" / TODAY / "plan.json").is_file())
        self.assertIn("✔ Índice de reportes: reports/INDEX.md (lista-de-clientes/%s · en curso)" % TODAY, out)
        text = (self.dir / "reports" / "INDEX.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(INDEX_TOP), text)
        self.assertEqual(perf_rows(self.dir / "reports/INDEX.md"), [[
            TODAY, "hb-performance", "lista-de-clientes/%s" % TODAY, "investigación", "en curso",
            "[performance/lista-de-clientes/{0}/estado.md](performance/lista-de-clientes/{0}/estado.md)".format(TODAY)]])

    def test_con_carpeta_de_reportes_va_a_su_base(self):
        write(self.dir / "AGENTS.md", "# P\n\n## Reglas del proyecto\n\n- Carpeta de reportes: `ctx/reports`\n")
        out = self.ok("nuevo", "--paquete", PKG, "--receta", "arranque-frio", "--serial", "emulator-5554")
        folder = self.dir / "ctx/reports/performance/arranque-frio" / TODAY
        self.assertIn("✔ Carpeta de la investigación: ctx/reports/performance/arranque-frio/%s (la carpeta de reportes "
                      "de AGENTS.md (ctx/reports))" % TODAY, out)
        self.assertTrue((folder / "estado.md").is_file())
        self.assertEqual(perf_rows(self.dir / "ctx/reports/INDEX.md")[0][2:5],
                         ["arranque-frio/%s" % TODAY, "investigación", "en curso"])

    def test_con_carpeta_de_investigaciones_y_sin_base_no_crea_reports_solo_para_el_indice(self):
        write(self.dir / "AGENTS.md", "# P\n\n## Rendimiento\n\n- Carpeta de investigaciones: `ctx/perf/investigaciones`\n")
        self.ok("nuevo", "--paquete", PKG, "--flujo", "detalle", "--serial", "emulator-5554")
        self.assertTrue((self.dir / "ctx/perf/investigaciones/detalle" / TODAY / "plan.json").is_file())
        self.assertFalse((self.dir / "reports").exists())

    def test_con_carpeta_de_investigaciones_no_se_mueve_y_el_indice_va_en_la_base(self):
        (self.dir / "reports").mkdir()  # la base ya existe (por ejemplo, la creó hb-implement)
        write(self.dir / "AGENTS.md", "# P\n\n## Rendimiento\n\n- Carpeta de investigaciones: `ctx/perf/investigaciones`\n")
        self.ok("nuevo", "--paquete", PKG, "--flujo", "detalle", "--serial", "emulator-5554")
        self.assertTrue((self.dir / "ctx/perf/investigaciones/detalle" / TODAY / "plan.json").is_file())
        self.assertFalse((self.dir / "reports/performance").exists())
        row = perf_rows(self.dir / "reports/INDEX.md")[0]
        self.assertEqual(row[2], "detalle/%s" % TODAY)
        self.assertEqual(row[5], "[../ctx/perf/investigaciones/detalle/{0}/estado.md](../ctx/perf/investigaciones/"
                                 "detalle/{0}/estado.md)".format(TODAY))


# ── Índice de reportes (hallazgo 20) ─────────────────────────────────────────

class ReportsIndexTest(PerfBase):
    """Las reglas del contrato: clave Skill + Slug, nunca otras filas ni otras líneas, la tabla al final si falta, la
    ruta real del archivo y el enlace relativo a la carpeta del índice."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "reports" / "performance" / "catalogo-lista" / "2026-03-02"
        write(self.folder / "estado.md", "# estado\n")

    def update(self, status, plan=None):
        return perf.update_reports_index(self.dir, self.folder, plan or {}, status)

    def test_agrega_y_actualiza_solo_su_fila(self):
        after_table = "\nNotas del equipo: no borrar.\n"
        write(self.dir / "reports" / "INDEX.md", INDEX_TOP + OTHER_ROW + "\n" + after_table)
        self.assertIn("✔ Índice de reportes", self.update("en curso"))
        self.assertIn("· en pausa", self.update("en pausa", {"profundidad": "triage"}))
        text = (self.dir / "reports" / "INDEX.md").read_text(encoding="utf-8")
        self.assertEqual(text, INDEX_TOP + OTHER_ROW + "\n" + "| 2026-03-02 | hb-performance | catalogo-lista/2026-03-02 | "
                         "investigación (triage) | en pausa | [performance/catalogo-lista/2026-03-02/estado.md]"
                         "(performance/catalogo-lista/2026-03-02/estado.md) |\n" + after_table)
        self.assertEqual(self.update("en pausa", {"profundidad": "triage"}), "")  # nada cambió: no reescribe

    def test_sin_la_tabla_la_agrega_al_final_sin_borrar_nada(self):
        write(self.dir / "reports" / "INDEX.md", "# Mis reportes\n\nTexto del equipo.\n")
        self.update("cerrada")
        text = (self.dir / "reports" / "INDEX.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Mis reportes\n\nTexto del equipo.\n\n| Fecha | Skill | Slug |"), text)
        self.assertEqual(perf_rows(self.dir / "reports/INDEX.md")[0][4], "cerrada")

    def test_celdas_escapadas_y_espacios_en_el_enlace(self):
        self.folder = self.dir / "reports" / "performance" / "lista con espacios" / "2026-03-02"
        write(self.folder / "estado.md", "x\n")
        self.update("sesión 1 | ficha\ny plan")
        line = next(line for line in (self.dir / "reports/INDEX.md").read_text(encoding="utf-8").splitlines()
                    if "hb-performance" in line)
        self.assertIn("| sesión 1 \\| ficha y plan |", line)
        self.assertIn("(performance/lista%20con%20espacios/2026-03-02/estado.md)", line)

    def test_escribe_sobre_la_ruta_real_y_el_enlace_sigue_siendo_enlace(self):
        real = self.dir / "fuera" / "INDEX.md"
        write(real, INDEX_TOP + OTHER_ROW + "\n")
        (self.dir / "reports").mkdir(exist_ok=True)
        os.symlink(str(real), str(self.dir / "reports" / "INDEX.md"))
        self.update("en curso")
        self.assertTrue((self.dir / "reports" / "INDEX.md").is_symlink())
        self.assertEqual(len(index_rows(real)), 2)
        self.assertEqual(perf_rows(real)[0][4], "en curso")

    def test_con_la_carpeta_de_reportes_enlazada_el_enlace_es_relativo_a_la_base(self):
        """A2 · H9: la base pasa por un enlace a una carpeta de fuera: el enlace se calcula por la ruta léxica de las
        dos, no con una resuelta y la otra no."""
        outside = self.dir / "contexto-real"
        (outside / "reports").mkdir(parents=True)
        os.symlink(str(outside), str(self.dir / "contexto"))
        write(self.dir / "AGENTS.md", "- Carpeta de reportes: `contexto/reports`\n")
        self.folder = self.dir / "contexto" / "reports" / "performance" / "detalle" / "2026-03-02"
        write(self.folder / "estado.md", "x\n")
        perf.update_reports_index(self.dir, self.folder, {}, "en curso")
        self.assertTrue((self.dir / "contexto").is_symlink())
        row = perf_rows(outside / "reports" / "INDEX.md")[0]
        self.assertEqual(row[5], "[performance/detalle/2026-03-02/estado.md](performance/detalle/2026-03-02/estado.md)")
        target = outside / "reports" / "performance" / "detalle" / "2026-03-02" / "estado.md"
        self.assertTrue(target.is_file())

    def test_por_la_ruta_real_del_enlace_el_enlace_del_indice_tambien_sirve(self):
        """Revisión B2: --carpeta con la ruta real (el destino del enlace) se rearma bajo la base tal como se escribió."""
        outside = self.dir / "contexto-real"
        (outside / "reports").mkdir(parents=True)
        os.symlink(str(outside), str(self.dir / "contexto"))
        write(self.dir / "AGENTS.md", "- Carpeta de reportes: `contexto/reports`\n")
        real_folder = outside / "reports" / "performance" / "detalle" / "2026-03-02"
        write(real_folder / "estado.md", "x\n")
        perf.update_reports_index(self.dir, real_folder, {}, "en curso")
        row = perf_rows(outside / "reports" / "INDEX.md")[0]
        self.assertEqual(row[2], "detalle/2026-03-02")
        self.assertEqual(row[5], "[performance/detalle/2026-03-02/estado.md](performance/detalle/2026-03-02/estado.md)")


class IndexLifecycleTest(TriageBase):
    """La fila cambia al pausar, archivar, reanudar y cerrar; una investigación de antes (reports/perf) se sigue
    listando y anotando."""

    def index(self):
        return perf_rows(self.root / "reports" / "INDEX.md")

    def test_pausar_archivar_reanudar(self):
        self.ok_in("pausar", "--carpeta", self.rel)
        self.assertEqual(self.index()[0][:5], ["2026-03-02", "hb-performance", "catalogo-lista/2026-03-02",
                                               "investigación (triage)", "en pausa"])
        self.assertEqual(self.index()[0][5], "[perf/catalogo-lista/2026-03-02/estado.md]"
                                             "(perf/catalogo-lista/2026-03-02/estado.md)")
        self.ok_in("archivar", "--carpeta", self.rel)
        self.assertEqual([row[4] for row in self.index()], ["archivada"])
        self.ok_in("reanudar", "--carpeta", self.rel)
        self.assertEqual([row[4] for row in self.index()], ["en curso"])
        self.assertNotIn("INDEX.md", git(self.root, "status", "--short", "--untracked-files=all"))  # fuera de git

    def test_cerrar_la_deja_cerrada(self):
        self.ok_in("cerrar", "--carpeta", self.rel, "--dod")
        self.assertEqual([row[4] for row in self.index()], ["cerrada"])

    def test_estado_lista_las_de_antes_y_las_nuevas(self):
        new = self.root / "reports" / "performance" / "detalle" / "2026-03-05"
        write(new / "plan.json", (self.folder / "plan.json").read_text(encoding="utf-8"))
        write(new / "estado.md", (self.folder / "estado.md").read_text(encoding="utf-8"))
        out = self.ok_in("estado")
        self.assertIn("- reports/perf/catalogo-lista/2026-03-02 ·", out)
        self.assertIn("- reports/performance/detalle/2026-03-05 ·", out)
        found = [folder.relative_to(self.root).as_posix() for folder, _ in perf.project_investigations(self.root)]
        self.assertEqual(sorted(found), ["reports/perf/catalogo-lista/2026-03-02", "reports/performance/detalle/2026-03-05"])


# ── Código de cada unidad en fuente, por fase (hallazgo 27) ──────────────────

class UnitReposTest(CaptureBase):
    """Antes de 0.20.0 cada fase guardaba solo `commit` y `sucio` del repo desde el que se corre `capturar`; ahora guarda
    además la rama, el commit y la versión del fuente de cada repo en fuente de la investigación."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        write(self.dir / ".git" / "info" / "exclude", "/inv/\n/bin/\n/libs/\n/*.txt\n/*.log\n/*.count\n/*.sql\n")
        write(self.dir / "README.md", "app\n")
        commit_all(self.dir, "app")
        self.lib = self.dir / "libs" / "core-lib"
        self.lib.mkdir(parents=True)
        init_repo(self.lib)
        write(self.lib / "src" / "Core.kt", "object Core\n")
        commit_all(self.lib, "core")
        git(self.lib, "tag", "v1.2.0")
        git(self.lib, "switch", "-q", "-c", "medir-login")
        self.plan_with(modulos=[{"nombre": "com.example:core-lib", "tipo": "codigo", "carpeta": "libs/core-lib",
                                 "artefacto": "com.example:core-lib:1.2.0"}])

    def test_cada_fase_registra_rama_y_commit_de_cada_unidad(self):
        self.capture(runs=3)
        repos = self.phases()["antes"][perf.UNIT_REPOS]
        head = git(self.lib, "rev-parse", "HEAD").strip()
        self.assertEqual(repos["libs/core-lib"], {"rama": "medir-login", "commit": head, "sucio": False,
                                                  "version_fuente": "v1.2.0"})
        self.assertEqual(repos["."]["rama"], "main")
        self.assertEqual(repos["."]["commit"], git(self.dir, "rev-parse", "HEAD").strip())
        # el control con otro commit en la unidad avisa: control repite el estado inicial
        write(self.lib / "src" / "Core.kt", "object Core { val x = 1 }\n")
        commit_all(self.lib, "otro")
        out = self.capture(phase="control", runs=3)
        self.assertIn("el código de libs/core-lib cambió entre antes y control", out)
        out = self.ok("comparar", self.folder / "metricas.csv")
        self.assertIn("el código de libs/core-lib cambió entre antes y control", out)
        table = (self.folder / "comparacion.md").read_text(encoding="utf-8")
        self.assertIn("Código de las unidades en fuente, por fase:", table)
        self.assertIn("| antes | libs/core-lib | medir-login | %s | v1.2.0 | no |" % head[:12], table)

    def test_una_segunda_tanda_conserva_el_codigo_de_la_primera_y_avisa(self):
        self.capture(runs=2)
        first = self.phases()["antes"][perf.UNIT_REPOS]["libs/core-lib"]["commit"]
        write(self.lib / "src" / "Core.kt", "object Core { val y = 2 }\n")
        commit_all(self.lib, "otro")
        self.capture(runs=1)
        record = self.phases()["antes"]
        self.assertEqual(record[perf.UNIT_REPOS]["libs/core-lib"]["commit"], first)
        self.assertTrue(any("el código de las unidades en fuente cambió entre tandas de la fase" in note
                            for note in record.get("avisos") or []), record.get("avisos"))

    def test_despues_avisa_si_cambio_la_rama(self):
        self.capture(runs=3)
        git(self.lib, "switch", "-q", "-c", "otra-rama")
        notes = perf.unit_phase_notes(self.phases(), self.dir, perf.units_state(self.folder, self.dir, perf.load_plan(
            self.plan)), "despues")
        self.assertEqual(notes, ["la rama de libs/core-lib cambió entre antes y después (medir-login → otra-rama): después "
                                 "mide otro código que el de la línea base"])

    def test_el_reporte_tecnico_lo_muestra_como_codigo_medido(self):
        self.capture(runs=3)
        plan = perf.load_plan(self.plan)
        data = perf.ReportData(self.folder, plan, perf.read_rows(self.folder / "metricas.csv"), {}, None)
        rows = dict(perf.conditions_rows(data))
        self.assertIn("Código medido", rows)
        self.assertIn("libs/core-lib medir-login @ %s" % git(self.lib, "rev-parse", "HEAD").strip()[:12], rows["Código medido"])


# ── Decisión 2: pasar a fuente en la sesión 1, desde el tag de la versión fijada (hallazgo 26) ──

class PassToSourceTest(ModulesBase):
    """La sesión 1 pasa una unidad publicada a fuente antes de medir, en una rama desde el tag de la versión fijada;
    perf.py dice el comando, comprueba si quedó en el tag y avisa si ya había fases medidas. perf.py no edita nada."""

    def test_la_version_y_los_tags(self):
        self.assertEqual(perf.pinned_version({"artefacto": "com.example:modulo-pagos:1.2.0"}), "1.2.0")
        self.assertEqual(perf.pinned_version({"artefacto": "com.example:modulo-pagos"}), "")
        for tag in ("v1.2.0", "modulo-pagos-1.2.0", "1.2.0-rc1", "v1.2.01"):
            git(self.sibling, "tag", tag)
        self.assertEqual(perf.version_tags(self.sibling, "1.2.0"), ["v1.2.0", "modulo-pagos-1.2.0"])
        self.assertEqual(perf.version_tags(self.sibling, "9.9.9"), [])

    def test_el_registro_da_el_comando_desde_el_tag_y_nunca_edita(self):
        git(self.sibling, "tag", "v1.2.0")
        before = {name: (self.root / name).read_bytes() for name in ("settings.gradle.kts", "modulos-locales.json")}
        out = self.register(self.binary, "com.example:modulo-pagos")
        self.assertIn("perf.py nunca lo edita: lo pasa a fuente la sesión 1, antes de medir, con el mecanismo del modelo", out)
        self.assertIn("`git -C ../modulo-pagos switch -c <rama que elija el usuario> v1.2.0`", out)  # 0.21.0
        self.assertEqual({name: (self.root / name).read_bytes() for name in before}, before)
        self.assertEqual(git(self.sibling, "branch", "--show-current").strip(), "main")  # perf.py no cambia de rama

    def test_sin_tag_lo_dice_para_registrarlo_y_avisar(self):
        out = self.register(self.binary, "com.example:modulo-pagos")
        self.assertIn("../modulo-pagos no tiene un tag de la versión fijada (1.2.0): si se pasa a fuente, la línea base "
                      "mide otro código que el publicado", out)
        # 0.21.0: sin tag, la pregunta de la rama igual se hace, desde la rama actual y sin inventar el nombre
        self.assertIn("sigue en la rama actual de ../modulo-pagos (`main`) o crea una nueva desde ella con el nombre que "
                      "dé el usuario (`git -C ../modulo-pagos switch -c <rama que elija el usuario>`; no lo inventes)", out)
        self.assertIn("Después, el cambio del modelo (`## Estructura` · Pasar a fuente y volver)", out)

    def test_al_pasar_a_fuente_comprueba_el_tag(self):
        git(self.sibling, "tag", "v1.2.0")
        self.register(self.binary, "com.example:modulo-pagos")
        git(self.sibling, "switch", "-q", "-c", "medir-pagos", "v1.2.0")  # lo que hace la sesión 1
        out = self.register(self.code, "com.example:modulo-pagos")
        head = git(self.sibling, "rev-parse", "HEAD").strip()[:12]
        self.assertIn("✔ com.example:modulo-pagos quedó en fuente en ../modulo-pagos medir-pagos @ %s, en el tag v1.2.0 de "
                      "la versión fijada" % head, out)
        item = self.modules()["com.example:modulo-pagos"]
        self.assertEqual((item["tipo"], item["version_fijada"], item["tag_fijado"]), ("codigo", "1.2.0", "v1.2.0"))

    def test_fuera_del_tag_o_con_fases_medidas_avisa(self):
        git(self.sibling, "tag", "v1.2.0")
        write(self.sibling / "src" / "Pagos.kt", SIBLING_NEWER)
        commit_all(self.sibling, "más nuevo que lo publicado")
        self.register(self.binary, "com.example:modulo-pagos")
        write(self.folder / "fases.json", json.dumps({"antes": {"fecha": "2099-01-01T10:00:00", "corridas": 10,
                                                                "flujos": {"pagos": {"corridas": 10}}}}))
        out = self.register(self.code, "com.example:modulo-pagos")
        self.assertIn("que no es el tag de la versión fijada (1.2.0): la línea base mide otro código que el publicado", out)
        self.assertIn("cambió de binario (llega compilado) a código con fases ya medidas (antes): el estado de sustitución "
                      "queda fijo en antes, control y después", out)
        self.assertIsNone(self.modules()["com.example:modulo-pagos"]["tag_fijado"])


SIBLING_NEWER = "class Pagos {\n    fun pagar() {\n        cobrarRapido()\n    }\n}\n"


# ── A2: AGENTS.md y el contexto enlazados, y worktrees ───────────────────────

class LinkedContextTest(PerfBase):
    """H7: perf.py escribe en AGENTS.md por su ruta real; un enlace sigue siendo enlace."""

    AGENTS = "# P\n\n## Rendimiento\n\n- applicationId: com.example.app\n\n## Git\n\n- Conventional Commits\n"

    def test_el_bloque_de_estado_se_escribe_en_el_destino_del_enlace(self):
        real = self.dir / "contexto-real" / "AGENTS.md"
        write(real, self.AGENTS)
        os.symlink(str(real), str(self.dir / "AGENTS.md"))
        self.assertIn("✔", perf.update_agents_state(self.dir, humo="pasó el 2026-11-01"))
        self.assertTrue((self.dir / "AGENTS.md").is_symlink())
        self.assertIn("prueba de humo: pasó el 2026-11-01", real.read_text(encoding="utf-8"))


class WorktreeTest(PerfBase):
    """H10: en un worktree sin el enlace del contexto, `nuevo` sin --carpeta lo dice y no crea un reports/ nuevo."""

    def setUp(self):
        super().setUp()
        self.main = self.dir / "app"
        self.main.mkdir()
        init_repo(self.main)
        write(self.main / "README.md", "app\n")
        commit_all(self.main, "base")
        context = self.dir / "contexto-externo"
        write(context / "AGENTS.md", "# P\n\n## Reglas del proyecto\n\n- Carpeta de reportes: `contexto/reports`\n")
        os.symlink(str(context / "AGENTS.md"), str(self.main / "AGENTS.md"))
        os.symlink(str(context), str(self.main / "contexto"))
        write(self.main / ".git" / "info" / "exclude", "/AGENTS.md\n/contexto\n")
        git(self.main, "worktree", "add", "-q", str(self.dir / "app-wt"), "-b", "otra")
        self.tree = self.dir / "app-wt"

    def run_here(self, cwd, *args):
        import subprocess
        from helpers import perf_argv
        from test_perf import SCRIPT
        return subprocess.run(perf_argv(SCRIPT) + [str(a) for a in args], cwd=str(cwd), env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def test_sin_el_enlace_no_crea_nada_y_dice_como_recrearlo(self):
        result = self.run_here(self.tree, "nuevo", "--paquete", PKG, "--flujo", "detalle")
        self.assertNotEqual(result.returncode, 0)
        text = result.stdout + result.stderr
        self.assertIn("este worktree no tiene lo que el principal sí tiene", text)
        self.assertIn("AGENTS.md: en el principal", text)
        self.assertIn("ln -s", text)
        self.assertFalse((self.tree / "reports").exists())
        self.assertNotIn("Traceback", text)
        main, missing = perf.worktree_missing(self.tree)
        self.assertEqual([name for name, _, _ in missing], ["AGENTS.md"])
        os.symlink(os.path.realpath(str(self.main / "AGENTS.md")), str(self.tree / "AGENTS.md"))
        main, missing = perf.worktree_missing(self.tree)
        self.assertEqual([(name, kind) for name, kind, _ in missing], [("contexto", "enlace")])

    def test_en_el_principal_no_se_detiene(self):
        self.assertEqual(perf.worktree_missing(self.main), (None, []))

    def test_el_indice_no_se_escribe_en_un_worktree_sin_el_enlace(self):
        """Revisión B3: pausar, archivar, reanudar y cerrar también pasan por el índice: sin el enlace, avisa y no crea
        un reports/ en el worktree."""
        folder = self.tree / "inv" / "detalle" / "2026-03-02"
        write(folder / "estado.md", "x\n")
        message = perf.update_reports_index(self.tree, folder, {}, "en pausa")
        self.assertIn("No anoté la investigación en el índice", message)
        self.assertIn("ln -s", message)
        self.assertFalse((self.tree / "reports").exists())

    def test_ensure_ignored_en_un_worktree_usa_el_exclude_comun(self):
        """Revisión B4: en un worktree .git es un archivo; la ruta de exclude la da git."""
        os.symlink(os.path.realpath(str(self.main / "AGENTS.md")), str(self.tree / "AGENTS.md"))
        folder = self.tree / "evidencia"
        folder.mkdir()
        previous = os.getcwd()
        os.chdir(str(self.tree))
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                perf.ensure_ignored(folder)
        finally:
            os.chdir(previous)
        self.assertIn("✔ git ignora evidencia", out.getvalue())
        exclude = (self.main / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertIn("/evidencia/", exclude)

    def test_una_carpeta_de_reportes_local_en_el_principal_no_detiene(self):
        """Lo que ya funcionaba: con reports/ local (sin enlace), cada worktree tiene la suya."""
        main = self.dir / "local"
        main.mkdir()
        init_repo(main)
        write(main / "AGENTS.md", "# P\n\n## Reglas del proyecto\n\n- Carpeta de reportes: `reports`\n")
        commit_all(main, "base")
        write(main / "reports" / "INDEX.md", "# Índice\n")
        write(main / ".git" / "info" / "exclude", "/reports/\n")
        git(main, "worktree", "add", "-q", str(self.dir / "local-wt"), "-b", "otra")
        self.assertEqual(perf.worktree_missing(self.dir / "local-wt")[1], [])


if __name__ == "__main__":
    unittest.main()
