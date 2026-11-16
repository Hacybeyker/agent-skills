"""Tests de hb-performance 0.12.0: igual contra igual (A), cada mejora como una decisión (B), cierre (C) y los
pendientes de 0.11.0 (D). Reusa las bases y los datos de test_perf.py."""
import datetime
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, write
from test_perf import PKG, STATE_COST, PerfBase, perf, rows

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
                               "(preparar.sh) son los mismos en antes, control, despues")
        self.ok("siguiente", "--carpeta", self.folder.relative_to(self.dir))
        self.assertIn(line, (self.folder / "estado.md").read_text(encoding="utf-8"))

    def test_fases_de_0110_sin_huella_de_archivos_no_avisan(self):
        old = {"recorrido": self.prints["recorrido"], "metricas": self.prints["metricas"]}
        write(self.folder / "preparar.sh", "sleep 5\n")
        self.phases(old, old)
        self.assertEqual(perf.route_change_notes(self.folder, perf.load_plan(self.folder / "plan.json")), {})
        self.assertEqual(perf.baseline_changes(self.folder, perf.load_plan(self.folder / "plan.json"), "home",
                                               perf.read_phases(self.folder))[1:], (False, False, []))
        self.assertIn("sin la huella de los archivos del recorrido en antes, control, despues",
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
        self.ok("reporte", "--carpeta", self.folder.relative_to(self.dir))
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
        self.assertIn("**Cargar la lista por adelantado**\n\n- Qué gana el usuario: abrir la pestaña pasó de 2.4 s a 41 "
                      "milisegundos (98 % menos): mejora clara.", part)
        self.assertIn("- Qué cuesta: consultar al servidor 1 vez más cada vez que se recorre (contactos); una consulta "
                      "más al abrir la app, aunque no se abra la pestaña.", part)
        self.assertIn("- Cuándo se nota: se nota si se abre la pestaña 4 s o más después de entrar. Según el escenario, "
                      "tras 4 s: mejora clara", part)
        self.assertIn("abrir la pestaña (enseguida)", business)  # el escenario por su título, no por el nombre interno
        self.assertNotIn("_", part)

    def test_siguiente_pide_medir_cada_escenario(self):
        write(self.folder / "fases.json", json.dumps({"antes": {"fecha": "2026-03-02T10:00:00", "corridas": 10, "flujos": {
            "abrir": {"corridas": 10}}}}))
        title, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))
        texts = [step["texto"] for step in steps if step["tipo"] == "terminal"]
        self.assertTrue(any("--flujo abrir_enseguida --fase antes --corridas 10" in text for text in texts), texts)

    def test_como_se_recorre_dice_el_escenario_y_sus_variables(self):
        block = perf.route_block(perf.load_plan(self.folder / "plan.json"), self.dir, self.folder)
        self.assertIn("Escenario de `abrir`: el mismo recorrido con `PERF_ESPERA_S=0`", block)
        self.assertIn("export PERF_ESPERA_S=0 && bash {{CARPETA}}/recorrido.sh", block)
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


if __name__ == "__main__":
    unittest.main()
