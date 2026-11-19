"""Tests de hb-performance 0.12.0: igual contra igual (A), cada mejora como una decisión (B), cierre (C) y los
pendientes de 0.11.0 (D). Reusa las bases y los datos de test_perf.py."""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, write
from test_perf import GRADLE_KTS, PKG, STATE_COST, PerfBase, perf, rows

HEADER = "fase,flujo,metrica,corrida,valor,unidad,sentido,familia\n"


def later(minutes):
    return (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


class RouteFilesTest(PerfBase):
    """A1: la huella del recorrido incluye el contenido de los scripts y flows que nombran `recorrido` y `preparar`."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        self.folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        write(self.folder / "preparar.sh", "#!/usr/bin/env bash\nadb shell am start -n com.example.app/.Main\nsleep 2\n")
        write(self.folder / "recorrido.sh", "#!/usr/bin/env bash\nCARPETA=\"$(dirname \"$0\")\"\n"
                                            "maestro test \"$CARPETA/flujo.yaml\"\n# comentario: otro.yaml\n")
        write(self.folder / "flujo.yaml", "appId: com.example.app\n---\n- tapOn: Contactos\n- runFlow: sub.yaml\n")
        write(self.folder / "sub.yaml", "appId: com.example.app\n---\n- tapOn: Lista\n")
        self.spec = {"preparar": "bash {{CARPETA}}/preparar.sh",
                     "recorrido": "bash %s" % (self.folder.relative_to(self.dir) / "recorrido.sh")}
        os.chdir(str(self.dir))
        self.addCleanup(os.chdir, str(ROOT))

    def test_encuentra_los_scripts_y_el_flow_que_nombran(self):
        names = [name for name, _ in perf.route_files(self.spec, self.folder)]
        self.assertEqual(names, ["recorrido.sh", "preparar.sh", "flujo.yaml", "sub.yaml"])  # el comentario no cuenta

    def test_la_huella_cambia_con_la_espera_y_no_con_los_finales_de_linea(self):
        first = perf.flow_fingerprints(self.spec, self.folder)
        self.assertEqual(sorted(first["archivos"]), ["flujo.yaml", "preparar.sh", "recorrido.sh", "sub.yaml"])
        text = (self.folder / "preparar.sh").read_text(encoding="utf-8")
        (self.folder / "preparar.sh").write_bytes(text.replace("\n", "  \r\n").encode("utf-8"))
        self.assertEqual(perf.flow_fingerprints(self.spec, self.folder), first)
        write(self.folder / "preparar.sh", text.replace("sleep 2", "sleep 5"))
        second = perf.flow_fingerprints(self.spec, self.folder)
        self.assertEqual(second["recorrido"], first["recorrido"])  # el texto del plan es el mismo
        self.assertEqual(perf.route_changes(first, second), ["preparar.sh"])
        # sin la huella de los archivos en una de las dos (una fase de 0.11.0), no hay aviso
        self.assertEqual(perf.route_changes({"recorrido": first["recorrido"]}, second), [])
        self.assertEqual(perf.flow_fingerprints(self.spec), {k: v for k, v in first.items() if k != "archivos"})

    def test_otra_tanda_con_otro_script_lo_avisa(self):
        first = perf.flow_fingerprints(self.spec, self.folder)
        perf.write_phase(self.folder, "antes", {"fecha": "2026-03-02T10:00:00", "corridas": 5, "plan": first}, "home")
        write(self.folder / "preparar.sh", "sleep 5\n")
        data = {"fecha": "2026-03-02T10:30:00", "corridas": 5, "plan": perf.flow_fingerprints(self.spec, self.folder)}
        perf.write_phase(self.folder, "antes", data, "home")
        warnings = perf.read_phases(self.folder)["antes"]["avisos"]
        self.assertTrue(any("preparar.sh cambió entre la primera tanda de la fase y esta" in w and "--rehacer" in w
                            for w in warnings), warnings)


class SameRouteTest(PerfBase):
    """A1 y A2: `comparar` avisa con el archivo que cambió y deja orientativas las métricas del flujo; `siguiente` ofrece
    rehacer la línea base; la condición "igual contra igual" la escribe perf.py en estado.md."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        write(self.dir / "app" / "Home.kt", "class Home\n")
        commit_all(self.dir)
        self.folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        write(self.folder / "preparar.sh", "adb shell am start -n com.example.app/.Main\nsleep 2\n")
        self.plan = {"paquete": PKG, "principales": ["tab_visible_ms"], "instalar": "./gradlew :app:installProfiling",
                     "flujos": {"home": {"preparar": "bash {{CARPETA}}/preparar.sh", "recorrido": "true"}},
                     "mejoras": [{"id": "M1", "titulo": "Cargar antes", "estado": "aplicada", "metrica": "tab_visible_ms",
                                  "aplicada_en": "2026-03-02T09:00:00"}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", STATE_COST % "")
        os.chdir(str(self.dir))
        self.addCleanup(os.chdir, str(ROOT))
        self.prints = perf.flow_fingerprints(self.plan["flujos"]["home"], self.folder)

    def phases(self, after_prints, before_prints=None):
        before_prints = before_prints or self.prints
        write(self.folder / "fases.json", json.dumps({
            "antes": {"fecha": "2026-03-02T10:00:00", "corridas": 5,
                      "flujos": {"home": {"corridas": 5, "plan": before_prints}}},
            "control": {"fecha": "2026-03-02T10:30:00", "corridas": 5,
                        "flujos": {"home": {"corridas": 5, "plan": before_prints}}},
            "despues": {"fecha": later(1), "corridas": 5, "flujos": {"home": {"corridas": 5, "plan": after_prints}}}}))
        write(self.folder / "metricas.csv", HEADER + rows("antes", "home", "tab_visible_ms", [2400, 2350, 2500, 2450, 2380])
              + rows("control", "home", "tab_visible_ms", [2390, 2360, 2490, 2460, 2370])
              + rows("despues", "home", "tab_visible_ms", [40, 42, 38, 41, 44]))

    def test_comparar_avisa_con_el_archivo_y_deja_orientativo(self):
        write(self.folder / "preparar.sh", "adb shell am start -n com.example.app/.Main\nsleep 5\n")
        self.phases(perf.flow_fingerprints(self.plan["flujos"]["home"], self.folder))
        out = self.ok("comparar", self.folder / "metricas.csv")
        self.assertIn("preparar.sh cambió entre antes y después: la espera o los pasos pueden no ser los mismos", out)
        self.assertIn("orientativas", out)
        plan = perf.load_plan(self.folder / "plan.json")
        results = perf.compare(perf.read_rows(self.folder / "metricas.csv"), plan=plan)[0]
        perf.flag_route_changes(results, self.folder, plan)
        self.assertIn(perf.ROUTE_CHANGED, results[0]["avisos"])
        self.assertIn("el recorrido no fue el mismo antes y después", perf.plain_verdict(results[0]))
        line = perf.same_route_line(self.folder, "home")
        self.assertIn("**no**", line)
        self.assertIn("preparar.sh cambió entre antes y después", line)

    def test_sin_cambios_la_condicion_la_escribe_perf(self):
        self.phases(self.prints)
        write(self.folder / "estado.md", STATE_COST % "" + "\n## Cómo se recorre\n\n<!-- perf:recorrido -->\nx\n"
                                                          "<!-- /perf:recorrido -->\n")
        self.assertEqual(perf.route_change_notes(self.folder, perf.load_plan(self.folder / "plan.json")), {})
        line = perf.same_route_line(self.folder, "home")
        self.assertEqual(line, "- Igual contra igual (lo calcula perf.py): el recorrido del plan y sus archivos "
                               "(preparar.sh) son los mismos en antes, control, después")
        self.ok("siguiente", "--carpeta", self.folder.relative_to(self.dir))
        self.assertIn(line, (self.folder / "estado.md").read_text(encoding="utf-8"))

    def test_fases_de_0110_sin_huella_de_archivos_no_avisan(self):
        old = {"recorrido": self.prints["recorrido"], "metricas": self.prints["metricas"]}
        write(self.folder / "preparar.sh", "sleep 5\n")
        self.phases(old, old)
        self.assertEqual(perf.route_change_notes(self.folder, perf.load_plan(self.folder / "plan.json")), {})
        self.assertEqual(perf.baseline_changes(self.folder, perf.load_plan(self.folder / "plan.json"), "home",
                                               perf.read_phases(self.folder))[1:], (False, False, []))
        self.assertIn("sin la huella de los archivos del recorrido en antes, control, después",
                      perf.same_route_line(self.folder, "home"))

    def test_siguiente_ofrece_rehacer_la_linea_base_si_preparar_cambio(self):
        write(self.folder / "fases.json", json.dumps({
            "antes": {"fecha": "2026-03-02T10:00:00", "corridas": 5, "flujos": {"home": {"corridas": 5, "plan": self.prints}}},
            "control": {"fecha": "2026-03-02T10:30:00", "corridas": 5}}))
        write(self.folder / "preparar.sh", "adb shell am start -n com.example.app/.Main\nsleep 5\n")
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertEqual(title, "rehacer la línea base: cambió preparar.sh (sin chat)")
        self.assertIn("preparar.sh cambió después de medir antes", steps[0]["lineas"][0])
        texts = [step["texto"] for step in steps if step["tipo"] == "terminal"]
        self.assertIn("lineabase --carpeta reports/perf/home/2026-03-02 --quitar-mejoras", texts[0])
        self.assertTrue(any("--fase antes" in text and "--rehacer" in text for text in texts))


class RedoBeforeWithImprovementsTest(PerfBase):
    """A3: `capturar --fase antes --rehacer` con las mejoras todavía en el código se detiene antes de compilar y ofrece
    `lineabase --quitar-mejoras`."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        write(self.dir / "app" / "Home.kt", "class Home {\n    fun cargar() = lista()\n}\n")
        commit_all(self.dir)
        self.folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        write(self.folder / "plan.json", json.dumps({
            "paquete": PKG, "flujos": {"home": {"recorrido": "true"}},
            "mejoras": [{"id": "M1", "titulo": "Cargar antes", "estado": "aprobada"}]}))
        write(self.folder / "estado.md", STATE_COST % "")
        write(self.dir / "app" / "Home.kt", "class Home {\n    fun cargar() = guardada ?: lista()\n}\n")
        self.ok("decidir", "--carpeta", self.folder.relative_to(self.dir), "--aplicada", "M1", "--archivos", "app/Home.kt")

    def test_se_detiene_y_ofrece_quitar_las_mejoras(self):
        result = self.perf("capturar", "--plan", self.folder.relative_to(self.dir) / "plan.json", "--fase", "antes",
                           "--corridas", "10", "--rehacer")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("las mejoras M1 siguen en el código", result.stderr)
        self.assertIn("lineabase --carpeta reports/perf/home/2026-03-02 --quitar-mejoras", result.stderr)
        self.assertIn("--rehacer --forzar", result.stderr)

    def test_commiteada_tambien_cuenta_y_quitada_no(self):
        plan = perf.load_plan(self.folder / "plan.json")
        self.assertEqual(perf.improvements_in_tree(self.folder, plan), ["M1"])
        git(self.dir, "add", "app/Home.kt")
        git(self.dir, "commit", "-q", "-m", "M1")
        self.assertEqual(perf.improvements_in_tree(self.folder, plan), ["M1"])  # el diff guardado revierte limpio
        self.ok("lineabase", "--carpeta", self.folder.relative_to(self.dir), "--quitar-mejoras")
        self.assertEqual(perf.improvements_in_tree(self.folder, perf.load_plan(self.folder / "plan.json")), [])

    def test_un_diff_que_ya_no_revierte_mira_los_archivos(self):
        write(self.dir / "app" / "Home.kt", "class Home {\n    fun cargar() = guardada ?: lista() // MARK home\n}\n")
        self.assertEqual(perf.improvements_in_tree(self.folder, perf.load_plan(self.folder / "plan.json")), ["M1"])


# ── B · Cada mejora como una decisión ─────────────────────────────────────────

def network_rows(phase, flow, services, total=None, runs=5, extra=""):
    """Filas de red de una fase: `services` es {servicio: llamadas por corrida}; red_llamadas es la suma (o `total`)."""
    out = rows(phase, flow, "red_llamadas", [total if total is not None else sum(services.values())] * runs,
               "llamadas")
    for service, calls in services.items():
        out += rows(phase, flow, "red %s llamadas" % service, [calls] * runs, "llamadas")
        out += rows(phase, flow, "red %s ms" % service, [300 + 10 * i for i in range(runs)], family="e2e")
    return out + extra


class NetworkAttributionTest(PerfBase):
    """B2: el aumento de `red_llamadas` que viene de servicios ajenos al flujo no es regresión; el que viene de los
    servicios que toca una mejora es su costo conocido (B1)."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        write(self.dir / "app" / "Api.kt", "interface Api\n")
        commit_all(self.dir)
        self.folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        self.plan = {"paquete": PKG, "principales": ["tab_visible_ms"],
                     "flujos": {"home": {"recorrido": "true", "servicios": ["GET api/v1/contactos"]}},
                     "mejoras": [{"id": "M1", "titulo": "Cargar la lista por adelantado", "estado": "aprobada",
                                  "metrica": "tab_visible_ms"}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", STATE_COST % "")
        write(self.dir / "app" / "Api.kt", 'interface Api {\n    @GET("api/v1/contactos")\n    fun contactos()\n}\n')
        self.ok("decidir", "--carpeta", self.folder.relative_to(self.dir), "--aplicada", "M1", "--archivos", "app/Api.kt")
        self.base = (rows("antes", "home", "tab_visible_ms", [2400, 2350, 2500, 2450, 2380])
                     + rows("despues", "home", "tab_visible_ms", [40, 42, 38, 41, 44]))

    def results(self, csv_text):
        write(self.folder / "metricas.csv", HEADER + self.base + csv_text)
        plan = perf.load_plan(self.folder / "plan.json")
        csv_rows = perf.read_rows(self.folder / "metricas.csv")
        results = perf.compare(csv_rows, plan=plan)[0]
        notes = perf.attribute_network(results, csv_rows, plan, self.folder)
        return {r["metrica"]: r for r in results}, notes

    def test_el_diff_de_la_mejora_atribuye_el_servicio(self):
        self.assertEqual(perf.diff_services('+    @GET("api/v1/contactos")\n', ["GET api/v1/contactos",
                                                                              "GET api/v1/perfil"]),
                         {"GET api/v1/contactos"})
        self.assertEqual(perf.diff_services('+ val ruta = "contactos"\n', ["GET api/v1/contactos"]), set())  # suelto
        self.assertEqual(perf.diff_services('+ @GET("v1/contactos/{id}")\n', ["GET api/v1/contactos/{id}"]),
                         {"GET api/v1/contactos/{id}"})
        self.assertEqual(perf.diff_services(' @GET("api/v1/contactos")\n', ["GET api/v1/contactos"]), set())  # contexto

    def test_aumento_de_servicios_ajenos_no_es_regresion(self):
        by_metric, notes = self.results(
            network_rows("antes", "home", {"GET api/v1/contactos": 1, "GET api/v1/novedades": 2})
            + network_rows("despues", "home", {"GET api/v1/contactos": 1, "GET api/v1/novedades": 3}))
        self.assertEqual(by_metric["red_llamadas"]["veredicto"], perf.FOREIGN_VERDICT)
        self.assertTrue(any("servicios ajenos al flujo" in a and "GET api/v1/novedades (2 → 3)" in a
                            for a in by_metric["red_llamadas"]["avisos"]), by_metric["red_llamadas"]["avisos"])
        self.assertEqual(by_metric["red GET api/v1/novedades llamadas"]["veredicto"], perf.FOREIGN_VERDICT)
        self.assertTrue(any("GET api/v1/novedades" in note and "no son una regresión" in note for note in notes), notes)

    def test_aumento_de_la_propia_mejora_es_costo_conocido(self):
        by_metric, _ = self.results(
            network_rows("antes", "home", {"GET api/v1/contactos": 1, "GET api/v1/novedades": 2})
            + network_rows("despues", "home", {"GET api/v1/contactos": 2, "GET api/v1/novedades": 2}))
        self.assertEqual(by_metric["red_llamadas"]["veredicto"], perf.COST_VERDICT)
        self.assertIn("costo conocido de M1: GET api/v1/contactos (1 → 2)", by_metric["red_llamadas"]["avisos"])
        self.assertEqual(by_metric["red GET api/v1/contactos llamadas"]["veredicto"], perf.COST_VERDICT)
        self.assertEqual(perf.closing_level(self.folder, perf.load_plan(self.folder / "plan.json"))[0], "economico")

    def test_sin_servicios_declarados_ni_diff_no_atribuye(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["flujos"]["home"].pop("servicios")
        plan["mejoras"][0]["cambios"] = []
        write(self.folder / "plan.json", json.dumps(plan))
        by_metric, notes = self.results(
            network_rows("antes", "home", {"GET api/v1/contactos": 1, "GET api/v1/novedades": 2})
            + network_rows("despues", "home", {"GET api/v1/contactos": 2, "GET api/v1/novedades": 3}))
        self.assertEqual(by_metric["red_llamadas"]["veredicto"], "regresión")
        self.assertEqual(notes, [])

    def test_un_servicio_del_flujo_que_sube_sin_mejora_sigue_siendo_regresion(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["flujos"]["home"]["servicios"] = ["GET api/v1/contactos", "novedades"]
        write(self.folder / "plan.json", json.dumps(plan))
        by_metric, _ = self.results(
            network_rows("antes", "home", {"GET api/v1/contactos": 1, "GET api/v1/novedades": 2})
            + network_rows("despues", "home", {"GET api/v1/contactos": 1, "GET api/v1/novedades": 3}))
        self.assertEqual(by_metric["red_llamadas"]["veredicto"], "regresión")


class TradeoffsReportTest(PerfBase):
    """B1 y B3: el reporte final (dev y gerencia) presenta cada mejora como una decisión: qué gana, qué cuesta y en qué
    condición, con el rango por escenario."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        write(self.dir / "app" / "Api.kt", "interface Api\n")
        commit_all(self.dir)
        self.folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        write(self.folder / "plan.json", json.dumps({
            "paquete": PKG, "principales": ["tab_visible_ms"], "etiquetas": {"tab_visible_ms": "abrir la pestaña"},
            "flujos": {"abrir": {"recorrido": "bash {{CARPETA}}/recorrido.sh", "variables": {"PERF_ESPERA_S": "4"},
                                 "titulo": "tras 4 s", "servicios": ["contactos"]},
                       "abrir_enseguida": {"escenario_de": "abrir", "variables": {"PERF_ESPERA_S": "0"},
                                           "titulo": "enseguida"}},
            "mejoras": [{"id": "M1", "titulo": "Cargar la lista por adelantado", "estado": "aprobada", "flujo": "abrir",
                         "metrica": "tab_visible_ms", "costo": "una consulta más al entrar",
                         "condicion": "si se abre la pestaña 4 s o más después de entrar"}]}))
        write(self.folder / "estado.md", STATE_COST % "" + "\n## Mejoras aplicadas\n\n- M1 · `app/Api.kt` · DoD ok\n"
                                                           "  - Costo: una consulta más al abrir la app, aunque no se "
                                                           "abra la pestaña\n"
                                                           "  - Condición: se nota si se abre la pestaña 4 s o más "
                                                           "después de entrar\n\n## Resumen para gerencia\n\nAbrir la "
                                                           "pestaña es más rápido.\n")
        write(self.dir / "app" / "Api.kt", 'interface Api {\n    @GET("api/v1/contactos")\n    fun contactos()\n}\n')
        self.ok("decidir", "--carpeta", self.folder.relative_to(self.dir), "--aplicada", "M1", "--archivos", "app/Api.kt")
        csv_text = HEADER
        for flow, after in (("abrir", [40, 42, 38, 41, 44]), ("abrir_enseguida", [2390, 2420, 2360, 2440, 2410])):
            csv_text += rows("antes", flow, "tab_visible_ms", [2400, 2350, 2500, 2450, 2380])
            csv_text += rows("despues", flow, "tab_visible_ms", after)
            csv_text += network_rows("antes", flow, {"GET api/v1/contactos": 1, "GET api/v1/novedades": 2})
            csv_text += network_rows("despues", flow, {"GET api/v1/contactos": 2, "GET api/v1/novedades": 2})
        write(self.folder / "metricas.csv", csv_text)

    def test_el_escenario_se_completa_con_el_flujo_base_y_el_plan_no_se_reescribe(self):
        plan = perf.load_plan(self.folder / "plan.json")
        self.assertEqual(plan["flujos"]["abrir_enseguida"]["recorrido"], "bash {{CARPETA}}/recorrido.sh")
        self.assertEqual(plan["flujos"]["abrir_enseguida"]["variables"], {"PERF_ESPERA_S": "0"})
        raw = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(set(raw["flujos"]["abrir_enseguida"]), {"escenario_de", "variables", "titulo"})  # decidir no la copió
        bad = dict(raw, flujos=dict(raw["flujos"], otro={"escenario_de": "abrir", "variables": {"X": "1"},
                                                          "recorrido": "true"}))
        write(self.dir / "malo" / "plan.json", json.dumps(bad))
        with self.assertRaises(perf.PerfError) as error:
            perf.load_plan(self.dir / "malo" / "plan.json")
        self.assertIn("solo cambia 'variables'", str(error.exception))
        prints = [perf.flow_fingerprints(plan["flujos"][name]) for name in ("abrir", "abrir_enseguida")]
        self.assertEqual(prints[0]["metricas"], prints[1]["metricas"])  # misma huella salvo el parámetro
        self.assertNotEqual(prints[0]["recorrido"], prints[1]["recorrido"])

    def test_pros_y_contras_en_dev_y_en_gerencia(self):
        self.ok("reporte", "--carpeta", self.folder.relative_to(self.dir), "--html")
        dev = (self.folder / "reporte-final-dev.md").read_text(encoding="utf-8")
        section = dev[dev.index("## Pros y contras de cada mejora"):dev.index("\n## Hallazgos")]
        self.assertIn("**Qué gana el usuario:** tab_visible_ms (tras 4 s · PERF_ESPERA_S=4): pasó de 2.4 s a 41 ms "
                      "(−98 %) · mejora", section)
        self.assertIn("+1 llamada por corrida a GET api/v1/contactos (1 → 2)", section)
        self.assertIn("una consulta más al abrir la app, aunque no se abra la pestaña (confirmado)", section)
        self.assertIn("por escenario: tras 4 s: mejora", section)
        self.assertIn("enseguida: sin cambio", section)
        self.assertNotIn("regresión", section)
        business = (self.folder / "reporte-final-gerencia.md").read_text(encoding="utf-8")
        part = business[business.index("## Qué gana y qué cuesta cada cambio"):business.index("\n## Servicios")]
        self.assertIn("**Cargar la lista por adelantado**\n\n- Qué gana el usuario: abrir la pestaña (tras 4 s) pasó de 2.4 "
                      "s a 41 milisegundos (98 % menos): mejora clara.", part)
        self.assertIn("- Qué cuesta: consultar al servidor 1 vez más cada vez que el usuario hace este recorrido "
                      "(contactos); según la investigación, una consulta más al abrir la app, aunque no se abra la pestaña.",
                      part)
        self.assertIn("**enseguida:**", business)  # "Servicios" por el título del escenario
        self.assertNotIn("**abrir_enseguida:**", business)
        html = (self.folder / "reporte-final-gerencia.html").read_text(encoding="utf-8")
        self.assertIn("abrir la pestaña (enseguida)", html)  # el gráfico dice de qué escenario es
        self.assertIn("- Cuándo se nota: se nota si se abre la pestaña 4 s o más después de entrar. Según el escenario, "
                      "tras 4 s: mejora clara", part)
        self.assertIn("abrir la pestaña (enseguida)", business)  # el escenario por su título, no por el nombre interno
        # con escenarios, el resultado de la mejora es el de su flujo, no el del último escenario
        self.assertIn("1 aplicadas → 1 funcionaron", dev)
        self.assertIn("✔ funcionó", dev)
        self.assertIn("**Qué mejoró:** `tab_visible_ms` pasó de 2.4 s a 41 ms", dev)
        self.assertNotIn("no dio el resultado esperado", business)
        self.assertNotIn("_", part)

    def test_siguiente_pide_medir_cada_escenario(self):
        write(self.folder / "fases.json", json.dumps({"antes": {"fecha": "2026-03-02T10:00:00", "corridas": 10, "flujos": {
            "abrir": {"corridas": 10}}}}))
        # con la mejora aplicada, el antes del escenario no se mide así: primero se quita con su parche
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        texts = [step["texto"] for step in steps if step["tipo"] == "terminal"]
        self.assertEqual(len(texts), 1)
        self.assertIn("lineabase --carpeta reports/perf/home/2026-03-02 --quitar-mejoras", texts[0])
        self.assertIn("antes de abrir_enseguida", steps[0]["lineas"][0])
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["estado"] = "propuesta"
        write(self.folder / "plan.json", json.dumps(plan))
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        texts = [step["texto"] for step in steps if step["tipo"] == "terminal"]
        self.assertTrue(any("--flujo abrir_enseguida --fase antes --corridas 10" in text for text in texts), texts)
        control = next(i for i, text in enumerate(texts) if "--flujo abrir --fase control" in text)
        self.assertLess(next(i for i, text in enumerate(texts) if "abrir_enseguida --fase antes" in text), control)

    def test_como_se_recorre_dice_el_escenario_y_sus_variables(self):
        block = perf.route_block(perf.load_plan(self.folder / "plan.json"), self.dir, self.folder)
        self.assertIn("Escenario de `abrir`: el mismo recorrido con `PERF_ESPERA_S=0`", block)
        self.assertIn("( export PERF_ESPERA_S=0 && bash %s/recorrido.sh )" % perf.q(str(self.folder.resolve())),
                      block)  # sin dejarla puesta en la terminal, y con la carpeta real
        self.assertNotIn("{{CARPETA}}/recorrido.sh )", block)
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["costo"] = 3
        write(self.dir / "malo" / "plan.json", json.dumps(plan))
        with self.assertRaises(perf.PerfError):
            perf.load_plan(self.dir / "malo" / "plan.json")

    def test_capturar_pasa_las_variables_al_recorrido(self):
        env = perf.scenario_env(perf.load_plan(self.folder / "plan.json"), "abrir_enseguida", self.folder / "plan.json")
        self.assertEqual(env["PERF_ESPERA_S"], "0")
        self.assertEqual(env["HB_PERF_FLUJO"], "abrir_enseguida")
        self.assertTrue(env["HB_PERF_PLAN"].endswith("plan.json"))


# ── C · Cierre ────────────────────────────────────────────────────────────────

class CloseRowsTest(PerfBase):
    """C1: `cerrar` lee las filas como las escriben las sesiones (varios archivos separados por comas, con o sin acentos
    graves) y se detiene solo con `...`, rutas ambiguas o archivos que no encuentra. C2: después de quitar, el DoD."""

    def setUp(self):
        super().setUp()
        init_repo(self.dir)
        for name in ("Home.kt", "Lista.kt", "Detalle.kt"):
            write(self.dir / "app" / name, "class %s\n" % name[:-3])
        commit_all(self.dir)
        self.folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        self.plan = {"paquete": PKG, "principales": ["tab_visible_ms"], "flujos": {"home": {"recorrido": "true"}},
                     "mejoras": []}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "fases.json", json.dumps({n: {"fecha": "2026-03-02"} for n in ("antes", "control")}))
        write(self.folder / "reporte-inicial-dev.md", "x")
        for name in ("Home.kt", "Lista.kt", "Detalle.kt"):
            write(self.dir / "app" / name, "class %s\n// MARK %s\n" % (name[:-3], name[:-3].lower()))

    def state(self, rows):
        write(self.folder / "estado.md", STATE_COST % rows)

    def test_filas_de_0100_y_0110_con_varios_archivos(self):
        self.assertEqual(perf.row_files("`app/Home.kt`, `app/Lista.kt:12`"), ["app/Home.kt", "app/Lista.kt"])  # 0.11.0
        self.assertEqual(perf.row_files("app/Home.kt, app/Lista.kt"), ["app/Home.kt", "app/Lista.kt"])  # 0.10.0
        self.assertEqual(perf.row_files("`app/Home.kt` y `app/Lista.kt`"), ["app/Home.kt", "app/Lista.kt"])
        self.assertEqual(perf.row_files("`app/Home.kt:3-9`"), ["app/Home.kt"])
        self.state("| `app/Home.kt`, `app/Lista.kt` | app | marcas | — | no |\n| app/Detalle.kt | app | marca | — | no |\n")
        out = self.ok("cerrar", "--carpeta", self.folder.relative_to(self.dir))
        self.assertIn("Quita (cambios temporales): app/Home.kt, app/Lista.kt, app/Detalle.kt", out)
        for name in ("Home", "Lista", "Detalle"):
            self.assertNotIn("MARK", (self.dir / "app" / ("%s.kt" % name)).read_text(encoding="utf-8"))
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertEqual([row["revertido"] for row in perf.temp_changes(state)], [True, True, True])
        self.assertEqual(state.count("sí · perf.py cerrar"), 2)  # una por fila

    def test_se_detiene_con_puntos_suspensivos_o_un_archivo_que_no_existe(self):
        self.state("| `app/Home.kt`, `.../Lista.kt` | app | marcas | — | no |\n")
        result = self.perf("cerrar", "--carpeta", self.folder.relative_to(self.dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no es una ruta completa", result.stderr)
        self.assertIn("MARK", (self.dir / "app" / "Home.kt").read_text(encoding="utf-8"))  # nada tocado
        self.state("| `app/Home.kt`, `otra/NoExiste.kt` | app | marcas | — | no |\n")
        result = self.perf("cerrar", "--carpeta", self.folder.relative_to(self.dir))
        self.assertIn("no encuentro 'otra/NoExiste.kt'", result.stderr)
        self.assertIn("MARK", (self.dir / "app" / "Home.kt").read_text(encoding="utf-8"))

    def test_una_ruta_que_esta_en_dos_repos_es_ambigua(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        other = Path(holder.name)
        init_repo(other)
        write(other / "app" / "Home.kt", "class Home\n")
        commit_all(other)
        top, why = perf.resolve_repo_file(self.dir.resolve(), "app/Home.kt", "", [other.resolve()])
        self.assertIsNone(top)
        self.assertIn("existe en más de un repo", why)
        top, rel = perf.resolve_repo_file(self.dir.resolve(), "app/Home.kt", str(other), [other.resolve()])
        self.assertEqual((top, rel), (other.resolve(), "app/Home.kt"))  # el repo de la fila manda
        top, rel = perf.resolve_repo_file(self.dir.resolve(), "app/Home.kt", ".", [other.resolve()])
        self.assertEqual((top, rel), (self.dir.resolve(), "app/Home.kt"))  # "." es la raíz: también manda

    def test_el_dod_solo_toma_comandos(self):
        write(self.dir / "AGENTS.md", "# x\n\n## DoD\n\n1. `./gradlew -q test`: los tests\n- Sin warnings de `lint`\n"
                                      "- `git reset --hard`: nunca\n\n```bash\n./gradlew -q \\\n  :app:assembleProfiling\n```\n")
        root = perf.q(str(self.dir))
        self.assertEqual(perf.dod_commands(self.dir), ["cd %s && ./gradlew -q test" % root,
                                                       "cd %s && ./gradlew -q :app:assembleProfiling" % root])

    def test_despues_de_quitar_el_dod_y_siguiente_lo_pide(self):
        write(self.dir / "AGENTS.md", "# x\n\n## DoD\n\n1. `true`: los tests\n2. `./gradlew -q :<módulo>:test`: "
                                      "plantilla\n\n## Git\n\n- nada\n")
        commit_all(self.dir)
        write(self.dir / "app" / "Home.kt", "class Home\n// MARK home temporal\n")
        self.state("| `app/Home.kt` | app | marca | — | no |\n")
        write(self.folder / "reporte-final-dev.md", "x")
        self.assertEqual(perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))[0],
                         "investigación cerrada · faltan quitar los cambios temporales y el DoD")
        out = self.ok("cerrar", "--carpeta", self.folder.relative_to(self.dir))
        self.assertIn("DoD después de quitar", out)
        self.assertIn("--dod", out)
        self.assertIn("· cd %s && true" % perf.q(str(self.dir.resolve())), out)
        self.assertNotIn("<módulo>", out.split("DoD después de quitar")[1].split("Siguiente")[0])
        self.assertIn("falta el DoD después de quitar los cambios temporales", out)
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertIn("cerrar --carpeta reports/perf/home/2026-03-02 --dod", steps[0]["texto"])
        out = self.ok("cerrar", "--carpeta", self.folder.relative_to(self.dir), "--dod")
        self.assertIn("✔ cd", out)
        self.assertIn("DoD en verde", out)
        self.assertEqual(perf.read_close(self.folder)["dod"], "ok")
        # 0.13.0 (B5): el reporte es anterior al cierre, así que `siguiente` ofrece regenerarlo; con el reporte al
        # día (más nuevo que cierre.json), la investigación queda cerrada. Las fechas se fijan: no depende del reloj.
        closed = (self.folder / perf.CLOSE_FILE).stat().st_mtime
        os.utime(str(self.folder / "reporte-final-dev.md"), (closed - 60, closed - 60))
        self.assertEqual(perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))[0],
                         "investigación cerrada · regenera los reportes con el cierre hecho (sin chat)")
        os.utime(str(self.folder / "reporte-final-dev.md"), (closed + 60, closed + 60))
        self.assertEqual(perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))[0],
                         "investigación cerrada")

    def test_un_dod_que_falla_lo_dice_y_no_cierra(self):
        write(self.dir / "AGENTS.md", "# x\n\n## DoD\n\n```bash\necho probando && false\n```\n")
        commit_all(self.dir)
        write(self.dir / "app" / "Home.kt", "class Home\n// MARK home temporal\n")
        self.state("| `app/Home.kt` | app | marca | — | no |\n")
        write(self.folder / "reporte-final-dev.md", "x")
        result = self.perf("cerrar", "--carpeta", self.folder.relative_to(self.dir), "--dod")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("✖ cd", result.stdout)
        self.assertIn("probando", result.stdout)  # las últimas líneas del log
        self.assertIn("el DoD falló", result.stderr)
        self.assertEqual(perf.read_close(self.folder)["dod"], "falló")
        self.assertNotIn("temporal", (self.dir / "app" / "Home.kt").read_text(encoding="utf-8"))  # quitado igual
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        self.assertIn("la vez anterior falló", steps[0]["que"])


# ── D · Pendientes de 0.11.0 ──────────────────────────────────────────────────

class CrlfImprovementTest(PerfBase):
    """D1: una mejora ya commiteada en un archivo con CRLF se quita con el diff que guardó `decidir --aplicada`."""

    def test_lineabase_quita_una_mejora_commiteada_en_crlf(self):
        init_repo(self.dir)
        (self.dir / "app").mkdir()
        (self.dir / "app" / "Home.kt").write_bytes(b"class Home {\r\n    fun cargar() = lista()\r\n}\r\n")
        commit_all(self.dir)
        folder = self.dir / "reports" / "perf" / "home" / "2026-03-02"
        write(folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"home": {"recorrido": "true"}},
                                                "mejoras": [{"id": "M1", "titulo": "Cargar antes", "estado": "aprobada"}]}))
        write(folder / "estado.md", STATE_COST % "")
        (self.dir / "app" / "Home.kt").write_bytes(b"class Home {\r\n    fun cargar() = guardada ?: lista()\r\n}\r\n")
        self.ok("decidir", "--carpeta", folder.relative_to(self.dir), "--aplicada", "M1", "--archivos", "app/Home.kt")
        self.assertIn(b"\r\n", (folder / "cambios" / "M1.diff").read_bytes())
        commit_all(self.dir, "M1")
        out = self.ok("lineabase", "--carpeta", folder.relative_to(self.dir), "--quitar-mejoras")
        self.assertIn("Mejora M1 quitada", out)
        self.assertEqual((self.dir / "app" / "Home.kt").read_bytes(), b"class Home {\r\n    fun cargar() = lista()\r\n}\r\n")


class TypingPauseTest(PerfBase):
    """D2: `teclear` sin --pausa lee `tecleo.pausa_ms` del plan (el de --plan o el de la captura en curso)."""

    def test_la_pausa_sale_del_plan(self):
        write(self.dir / "inv" / "plan.json", json.dumps({"paquete": PKG, "flujos": {
            "buscar": {"recorrido": "true", "tecleo": {"marca": "MARK tecla*", "pausa_ms": [300, 400]}},
            "otro": {"recorrido": "true"}}}))
        plan = str(self.dir / "inv" / "plan.json")
        self.assertEqual(perf.typing_pause(plan, "buscar"), [300, 400])
        self.assertEqual(perf.typing_pause(plan, "otro"), perf.TYPING_PAUSE)
        self.assertEqual(perf.typing_pause(), perf.TYPING_PAUSE) if not os.environ.get("HB_PERF_PLAN") else None
        env = perf.scenario_env(perf.load_plan(plan), "buscar", plan)
        old = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            self.assertEqual(perf.typing_pause(), [300, 400])
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class FlavorsAndUpdateTest(PerfBase):
    """D3: la alternativa -Pperf en un módulo con sabores trae la nota de sabores, y el aviso de actualizar la
    instrumentación da el comando completo."""

    def test_gradle_propiedad_con_sabores(self):
        gradle = GRADLE_KTS.replace("android {", 'android {\n    flavorDimensions += "marca"\n    productFlavors { '
                                                 'create("demo") { dimension = "marca" } }', 1)
        write(self.dir / "app" / "build.gradle.kts", gradle)
        write(self.dir / "app" / "src/main/kotlin/com/ejemplo/app/Toggles.kt",
              "package com.ejemplo.app\n\nval ambiente = BuildConfig.BUILD_TYPE\n")
        out = self.ok("instrumentar", "--modulo", self.dir / "app", "--paquete", "com.ejemplo.perf", "--sin-fragments")
        alternative = out[out.index("Alternativa recomendada"):]
        self.assertIn('val perf = providers.gradleProperty("perf").isPresent', alternative)
        self.assertIn("El módulo tiene sabores (productFlavors)", alternative)
        self.assertIn("install<Sabor><BuildType> (con -Pperf en la alternativa)", alternative)

    def test_actualizar_da_el_comando_completo(self):
        write(self.dir / "app" / "src" / "perf" / "kotlin" / "com" / "ejemplo" / "perf" / "PerfHooks.kt",
              "package com.ejemplo.perf\n\nobject PerfHooks\n")
        command = perf.update_instrumentation_command(self.dir)
        self.assertEqual(command, "cd %s && python3 -I %s instrumentar --modulo app --paquete com.ejemplo.perf --actualizar"
                         % (perf.q(str(self.dir)), perf.q(str(perf.HERE / "perf.py"))))
        warnings = perf.test_run_warnings(self.dir, None, {"nombres": {"HTTP GET " + "a" * 140: 1}, "http": 1}, "", [])
        self.assertEqual(warnings[0]["comandos"][0][1], command)


class DodOtherReposTest(PerfBase):
    """D4: con `## DoD` ya escrito, la sesión 0 (`humo`) y `siguiente` detectan que le faltan los módulos de otros repos."""

    def test_detecta_el_modulo_de_otro_repo(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        other = Path(holder.name) / "pagos"
        write(other / "build.gradle.kts", "plugins { }\n")
        write(self.dir / "settings.gradle.kts", 'include(":pagos")\nproject(":pagos").projectDir = file("%s")\n' % other)
        write(self.dir / "AGENTS.md", "# x\n\n## DoD\n\n1. `./gradlew -q :app:testDebugUnitTest`\n")
        found = perf.dod_missing_external(self.dir)
        self.assertEqual([name for name, _ in found], ["pagos"])
        self.assertIn("los tests de pagos, que viene de otro repo", found[0][1])
        notice = perf.dod_notice(self.dir, {"flujos": {}})
        self.assertIn("no trae los módulos de otros repos", notice["titulo"])
        write(self.dir / "AGENTS.md", "# x\n\n## DoD\n\n1. `./gradlew -q :app:testDebugUnitTest`\n"
                                      "2. `cd %s && ./gradlew -q test`: pagos\n" % other)
        self.assertEqual(perf.dod_missing_external(self.dir), [])
        self.assertIsNone(perf.dod_notice(self.dir, {"flujos": {}}))


class BusinessTextTest(PerfBase):
    """D5: gerencia sin "_sin completar_", con las sesiones sin anotar por un nombre legible y diciendo cuál quedó sin
    confirmar."""

    def test_textos_de_gerencia(self):
        folder = self.dir / "inv"
        write(folder / "plan.json", json.dumps({"paquete": PKG, "principales": ["lista_ms"],
                                                "flujos": {"lista": {"recorrido": "true"}}}))
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2026-03-02T10:00:00"}}))
        write(folder / "estado.md", "# Rendimiento · Lista · 2026-03-02\n\n## Siguiente paso\n\n- x\n\n## Ficha\n\n"
              "| Campo | Valor |\n| --- | --- |\n| Síntoma | <lo que nota el usuario, o \"exploratoria\"> |\n\n## Hallazgos\n\n"
              "| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n"
              "| H1 | La lista aparece tarde a veces | x | sin probar | sin confirmar |\n\n## Consumo\n\n"
              "| Sesión | Modelo | Costo o tokens |\n| --- | --- | --- |\n")
        write(folder / "metricas.csv", HEADER + rows("antes", "lista", "lista_ms", [900, 950, 1000, 980, 940]))
        write(folder / "reporte-inicial-dev.md", "x")
        self.ok("reporte", "--carpeta", folder, "--inicial")
        text = (folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8")
        self.assertNotIn("_sin completar_", text)
        self.assertNotIn("_Sin completar", text)
        self.assertIn("Sin completar todavía: la investigación no lo anotó.", text)
        self.assertIn("1 quedó sin confirmar (la lista aparece tarde a veces)", text)
        self.assertIn("la ficha y el plan", text)
        self.assertNotIn("1 · ficha", text)
        self.assertEqual(perf.session_words("3 · M1"), "la mejora M1")


class UnitsEdgesTest(unittest.TestCase):
    """D6: unidades en singular y redondeo en los bordes de escala."""

    def test_singular_y_bordes(self):
        self.assertEqual(perf.fmt(1, "llamadas"), "1 llamada")
        self.assertEqual(perf.fmt_signed(1, "llamadas"), "+1 llamada")
        self.assertEqual(perf.fmt(2, "llamadas"), "2 llamadas")
        self.assertEqual(perf.plain_time(1), "1 milisegundo")
        self.assertEqual(perf.nice(999.7, "ms"), "1 s")
        self.assertEqual(perf.nice(999.4, "ms"), "999 ms")
        self.assertEqual(perf.nice(9999.7, "ms"), "10 s")
        self.assertEqual(perf.plain_time(99.7), "0.1 s")
        self.assertEqual(perf.change_pct(4000, 20), "−99.5 %")
        phrase = perf.change_phrase({"antes": {"mediana": 0.8}, "despues": {"mediana": 0.3}, "unidad": "ms",
                                     "veredicto": "mejora"}, plain=True)
        self.assertEqual(phrase.count("menos de 1 milisegundo"), 0, phrase)
        steady = perf.change_phrase({"antes": {"mediana": 0.8}, "despues": {"mediana": 0.7}, "unidad": "ms",
                                     "veredicto": "sin cambio"}, plain=True)
        self.assertEqual(steady, "se mantuvo en menos de 1 milisegundo")
        self.assertEqual(perf.plain_time(0.04, extra=1), "0.04 milisegundos")


class PrintAndLabelsTest(unittest.TestCase):
    """D7 y D8: al imprimir, los encabezados no se cortan con guion; dos variantes del mismo servicio se distinguen en
    la etiqueta de la línea de tiempo."""

    def test_encabezados_al_imprimir(self):
        css = (perf.ASSETS / "plantillas" / "reporte.html").read_text(encoding="utf-8")
        printing = css[css.index("@media print"):]
        rule = printing[printing.index("    th {"):].split("\n", 1)[0]
        self.assertIn("hyphens: none", rule)
        self.assertIn("overflow-wrap: normal", rule)
        self.assertNotIn("hyphens: auto", printing)

    def test_variantes_de_la_misma_ruta(self):
        labels = perf.lane_labels(["GET api/v1/contactos/{id}/detalle #ab12", "GET api/v1/contactos/{id}/detalle #cd34",
                                   "GET api/v1/perfil"])
        self.assertNotEqual(labels["GET api/v1/contactos/{id}/detalle #ab12"],
                            labels["GET api/v1/contactos/{id}/detalle #cd34"])
        self.assertTrue(labels["GET api/v1/contactos/{id}/detalle #ab12"].endswith("#ab12"))
        self.assertTrue(all(len(label) <= 30 for label in labels.values()), labels)
        self.assertEqual(labels["GET api/v1/perfil"], "GET …/v1/perfil")


if __name__ == "__main__":
    unittest.main()
