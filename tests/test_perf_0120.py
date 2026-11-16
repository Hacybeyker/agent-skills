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
        write(self.folder / "flujo.yaml", "appId: com.example.app\n---\n- tapOn: Contactos\n")
        self.spec = {"preparar": "bash {{CARPETA}}/preparar.sh",
                     "recorrido": "bash %s" % (self.folder.relative_to(self.dir) / "recorrido.sh")}
        os.chdir(str(self.dir))
        self.addCleanup(os.chdir, str(ROOT))

    def test_encuentra_los_scripts_y_el_flow_que_nombran(self):
        names = [name for name, _ in perf.route_files(self.spec, self.folder)]
        self.assertEqual(names, ["recorrido.sh", "preparar.sh", "flujo.yaml"])  # el comentario no cuenta

    def test_la_huella_cambia_con_la_espera_y_no_con_los_finales_de_linea(self):
        first = perf.flow_fingerprints(self.spec, self.folder)
        self.assertEqual(sorted(first["archivos"]), ["flujo.yaml", "preparar.sh", "recorrido.sh"])
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
        self.assertIn("preparar.sh cambió entre antes y despues: la espera o los pasos pueden no ser los mismos", out)
        self.assertIn("orientativas", out)
        plan = perf.load_plan(self.folder / "plan.json")
        results = perf.compare(perf.read_rows(self.folder / "metricas.csv"), plan=plan)[0]
        perf.flag_route_changes(results, self.folder, plan)
        self.assertIn(perf.ROUTE_CHANGED, results[0]["avisos"])
        self.assertIn("el recorrido no fue el mismo antes y después", perf.plain_verdict(results[0]))
        line = perf.same_route_line(self.folder, "home")
        self.assertIn("**no**", line)
        self.assertIn("preparar.sh cambió entre antes y despues", line)

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


if __name__ == "__main__":
    unittest.main()
