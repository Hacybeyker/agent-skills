"""Tests de hb-performance (skills/hb-performance/scripts/perf.py): estadística, métricas de traza, red,
captura con un adb y un trace_processor falsos, reporte e instrumentación."""
import csv
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import ROOT, write

SCRIPT = ROOT / "skills" / "hb-performance" / "scripts" / "perf.py"
HEADER = "fase,flujo,metrica,corrida,valor,unidad,sentido,familia\n"
PKG = "com.ejemplo.app"

spec = importlib.util.spec_from_file_location("perf", str(SCRIPT))
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


def rows(phase, flow, metric, values, unit="ms", sense="menor", family="app"):
    return "".join("%s,%s,%s,%d,%s,%s,%s,%s\n" % (phase, flow, metric, i, v, unit, sense, family)
                   for i, v in enumerate(values, start=1))


def entry(method, url, started, time):
    return {"request": {"method": method, "url": url}, "startedDateTime": started, "time": time}


MS = 1_000_000


class PerfBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.csv = self.dir / "metricas.csv"
        self.env = dict(os.environ)

    def tearDown(self):
        self.tmp.cleanup()

    def perf(self, *args, stdin=None):
        return subprocess.run([sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args], cwd=str(self.dir),
                              env=self.env, input=stdin, capture_output=True, text=True, encoding="utf-8")

    def ok(self, *args, stdin=None):
        result = self.perf(*args, stdin=stdin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def read_csv(self):
        with self.csv.open(newline="", encoding="utf-8") as f:
            return {(r["fase"], r["metrica"], r["corrida"]): r for r in csv.DictReader(f)}


class CompareTest(PerfBase):
    def comparison(self, content):
        write(self.csv, HEADER + content)
        out = self.dir / "r.json"
        self.ok("comparar", self.csv, "--json", out)
        return json.loads(out.read_text(encoding="utf-8"))

    def only(self, content):
        data = self.comparison(content)
        self.assertEqual(len(data["resultados"]), 1)
        return data["resultados"][0]

    def test_mejora_cuando_la_mediana_sale_del_rango_de_antes(self):
        r = self.only(rows("antes", "f", "frame_p90_ms", [20, 21, 22, 21, 20]) +
                      rows("despues", "f", "frame_p90_ms", [14, 15, 14, 13, 14]))
        self.assertEqual(r["veredicto"], "mejora")
        self.assertAlmostEqual(r["delta_pct"], -100 / 3)

    def test_sin_cambio_dentro_del_rango_y_regresion_fuera(self):
        same = self.only(rows("antes", "f", "m", [10, 14, 12, 11, 13]) + rows("despues", "f", "m", [11, 11, 12, 10, 11]))
        self.assertEqual(same["veredicto"], "sin cambio")
        worse = self.only(rows("antes", "f", "m", [10, 11, 10, 11, 10]) + rows("despues", "f", "m", [15, 16, 15, 15, 16]))
        self.assertEqual(worse["veredicto"], "regresión")

    def test_sentido_mayor_invierte_el_veredicto(self):
        r = self.only(rows("antes", "f", "fps", [50, 52, 51, 50, 52], "fps", "mayor") +
                      rows("despues", "f", "fps", [60, 59, 60, 61, 60], "fps", "mayor"))
        self.assertEqual(r["veredicto"], "mejora")

    def test_dentro_del_ruido_con_bloque_de_control(self):
        r = self.only(rows("antes", "f", "m", [20] * 5) + rows("control", "f", "m", [17] * 5) + rows("despues", "f", "m", [18] * 5))
        self.assertEqual(r["veredicto"], "dentro del ruido")
        self.assertEqual(r["ruido"], 3)

    def test_familia_info_no_lleva_veredicto(self):
        r = self.only(rows("antes", "f", "frames", [100] * 5, "frames", family="info") +
                      rows("despues", "f", "frames", [50] * 5, "frames", family="info"))
        self.assertEqual(r["veredicto"], "informativa")

    def test_avisa_pocas_corridas_e_inestable(self):
        r = self.only(rows("antes", "f", "m", [10, 30, 12]) + rows("despues", "f", "m", [5, 5, 5]))
        self.assertIn("pocas corridas", r["avisos"])
        self.assertIn("inestable", r["avisos"])

    def test_salida_compacta_muestra_las_centrales_y_deja_el_detalle_en_archivo(self):
        content = rows("antes", "f", "jank_app_pct", [9] * 5, "%") + rows("despues", "f", "jank_app_pct", [3] * 5, "%")
        content += rows("antes", "f", "red GET a llamadas", [1] * 5, "llamadas") + \
            rows("despues", "f", "red GET a llamadas", [1] * 5, "llamadas")
        write(self.csv, HEADER + content)
        out = self.ok("comparar", self.csv)
        self.assertIn("jank_app_pct", out)
        self.assertNotIn("red GET a llamadas", out)
        self.assertIn("red GET a llamadas", (self.dir / "comparacion.md").read_text(encoding="utf-8"))

    def test_actualiza_los_bloques_de_estado(self):
        write(self.dir / "estado.md", "# E\n\n## Métricas\n<!-- perf:metricas -->\nviejo\n<!-- /perf:metricas -->\n"
                                      "## Comparación\n<!-- perf:comparacion -->\n<!-- /perf:comparacion -->\n")
        write(self.csv, HEADER + rows("antes", "f", "jank_app_pct", [9] * 5, "%") + rows("despues", "f", "jank_app_pct", [3] * 5, "%"))
        self.ok("resumen", self.csv)
        self.ok("comparar", self.csv)
        state = (self.dir / "estado.md").read_text(encoding="utf-8")
        self.assertNotIn("viejo", state)
        self.assertIn("| antes | f | jank_app_pct |", state)
        self.assertIn("mejora", state)

    def test_frames_distintos_vuelven_no_comparables_las_metricas_de_frame(self):
        data = self.comparison(rows("antes", "f", "frames", [220, 230, 210, 225, 221], "frames", family="info")
                               + rows("despues", "f", "frames", [8, 7, 8, 7, 8], "frames", family="info")
                               + rows("antes", "f", "frame_p90_ms", [30, 31, 30, 29, 30])
                               + rows("despues", "f", "frame_p90_ms", [118, 120, 119, 117, 118])
                               + rows("antes", "f", "ttid_ms", [400, 410, 405, 395, 402])
                               + rows("despues", "f", "ttid_ms", [300, 310, 305, 295, 302]))
        by = {r["metrica"]: r for r in data["resultados"]}
        self.assertEqual(by["frame_p90_ms"]["veredicto"], "no comparable")
        self.assertIn("frames distintos", by["frame_p90_ms"]["avisos"])
        self.assertEqual(by["ttid_ms"]["veredicto"], "mejora")

    def test_validaciones_del_csv(self):
        write(self.csv, "fase,flujo,valor\nantes,f,1\n")
        self.assertEqual(self.perf("resumen", self.csv).returncode, 2)
        write(self.csv, HEADER + "antes,f,m,1,abc,ms,menor,app\n")
        self.assertIn(":2:", self.perf("resumen", self.csv).stderr)
        write(self.csv, HEADER + "durante,f,m,1,3,ms,menor,app\n")
        self.assertIn("fase 'durante'", self.perf("resumen", self.csv).stderr)
        write(self.csv, HEADER + "antes,f,m,1,3,ms,menor,app\ndespues,f,m,1,2,ms,mayor,app\n")
        self.assertIn("sentidos distintos", self.perf("comparar", self.csv).stderr)
        write(self.csv, HEADER + "antes,f,m,1,3,ms,menor,otra\n")
        self.assertIn("familia 'otra'", self.perf("resumen", self.csv).stderr)


class TraceMetricsTest(unittest.TestCase):
    def base_rows(self):
        return [("proceso", 0, 0, 0, PKG), ("limites", 0, 10_000 * MS, 0, "")]

    def metrics(self, extra, flow=None, known=(), sdk=34, hz=60):
        out, invalid, info = perf.trace_metrics(self.base_rows() + extra, hz, flow or {}, set(known), sdk)
        return {m[0]: m for m in out}, invalid, info

    def test_frames_jank_de_la_app_separado_del_total(self):
        frames = [("frame", i * 20 * MS, 16 * MS, 0, "None") for i in range(6)]
        frames += [("frame", 200 * MS, 40 * MS, 0, "App Deadline Missed"),
                   ("frame", 300 * MS, 33 * MS, 0, "Buffer Stuffing"),
                   ("frame", 400 * MS, 50 * MS, 0, "App Deadline Missed, Buffer Stuffing"),
                   ("frame", 500 * MS, 16 * MS, 0, "None")]
        m, invalid, _ = self.metrics(frames)
        self.assertIsNone(invalid)
        self.assertEqual(m["jank_app_pct"][1], 20)
        self.assertEqual(m["jank_total_pct"][1], 20)  # Buffer Stuffing solo no cuenta
        self.assertEqual(m["jank_total_pct"][3], "info")
        self.assertEqual(m["frames"][3], "info")

    def test_hilo_principal_cuenta_solo_slices_de_nivel_superior(self):
        main = [("hilo", 0, 20 * MS, 0, "Choreographer#doFrame"), ("hilo", 1 * MS, 18 * MS, 1, "traversal"),
                ("hilo", 100 * MS, 150 * MS, 0, "onCreate"), ("hilo", 400 * MS, 10 * MS, 0, "corto")]
        m, _, _ = self.metrics(main + [("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["hilo_slices_sobre_presupuesto"][1], 2)
        self.assertEqual(m["hilo_slices_100ms"][1], 1)
        self.assertEqual(m["hilo_max_ms"][1], 150)

    def test_inflates_anidados_cuentan_una_vez(self):
        main = [("hilo", 0, 10 * MS, 3, "inflate"), ("hilo", 1 * MS, 2 * MS, 4, "inflate"),
                ("hilo", 50 * MS, 4 * MS, 3, "inflate")]
        m, _, _ = self.metrics(main + [("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["inflate_cantidad"][1], 2)
        self.assertEqual(m["inflate_ms"][1], 14)

    def test_red_solapadas_repetidas_ttfb_y_cliente(self):
        secs = [("seccion", 0, 300 * MS, 0, "HTTP GET items/{id}"), ("seccion", 10 * MS, 200 * MS, 0, "TTFB GET items/{id}"),
                ("seccion", 100 * MS, 300 * MS, 0, "HTTP GET items/{id}"), ("seccion", 110 * MS, 250 * MS, 0, "TTFB GET items/{id}"),
                ("seccion", 5000 * MS, 100 * MS, 0, "HTTP POST login")]
        m, _, _ = self.metrics(secs + [("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["red_llamadas"][1], 3)
        self.assertEqual(m["red_solapadas"][1], 1)
        self.assertEqual(m["red_repetidas_2s"][1], 1)
        self.assertEqual(m["red GET items/{id} llamadas"][1], 2)
        self.assertEqual(m["red GET items/{id} ms"][1], 300)
        self.assertEqual(m["red GET items/{id} ttfb_ms"][1], 225)
        self.assertEqual(m["red GET items/{id} cliente_ms"][1], 75)
        self.assertEqual(m["red GET items/{id} ms"][3], "e2e")
        self.assertEqual(m["red GET items/{id} cliente_ms"][3], "app")

    def test_la_marca_de_la_query_separa_cargas_distintas_del_mismo_endpoint(self):
        secs = [("seccion", 0, 300 * MS, 0, "HTTP GET discover/movie #1a2b"),
                ("seccion", 10 * MS, 300 * MS, 0, "HTTP GET discover/movie #3c4d"),
                ("seccion", 20 * MS, 300 * MS, 0, "HTTP GET discover/movie #3c4d")]
        m, _, _ = self.metrics(secs + [("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["red_solapadas"][1], 1)  # solo las dos con la misma query
        self.assertEqual(m["red_repetidas_2s"][1], 1)
        self.assertEqual(m["red GET discover/movie llamadas"][1], 3)
        self.assertNotIn("red GET discover/movie #1a2b llamadas", m)

    def test_ttfb_se_asigna_uno_a_uno_entre_llamadas_concurrentes(self):
        secs = [("seccion", 0, 300 * MS, 0, "HTTP GET a"), ("seccion", 50 * MS, 350 * MS, 0, "HTTP GET a"),
                ("seccion", 60 * MS, 100 * MS, 0, "TTFB GET a"), ("seccion", 70 * MS, 200 * MS, 0, "TTFB GET a")]
        m, _, _ = self.metrics(secs + [("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["red GET a ttfb_ms"][1], 150)
        self.assertEqual(m["red GET a cliente_ms"][1], 175)

    def test_cola_y_conexion_salen_del_cliente(self):
        secs = [("seccion", 0, 500 * MS, 0, "HTTP GET a #00ff"), ("seccion", 0, 100 * MS, 0, "QUEUE GET a #00ff"),
                ("seccion", 100 * MS, 150 * MS, 0, "CONN GET a #00ff"), ("seccion", 260 * MS, 200 * MS, 0, "TTFB GET a #00ff")]
        m, _, _ = self.metrics(secs + [("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["red GET a cliente_ms"][1], 50)
        self.assertEqual(m["red GET a cola_ms"][1], 100)
        self.assertEqual(m["red GET a cola_ms"][3], "app")
        self.assertEqual(m["red_conexiones"][1], 1)
        self.assertEqual(m["red_conexion_ms"][1], 150)
        self.assertEqual(m["red_conexion_ms"][3], "e2e")
        self.assertEqual(m["red_llamadas"][1], 1)

    def test_la_ventana_acota_frames_e_hilo_y_la_metrica_guarda_la_ultima_llamada(self):
        rows = [("frame", 0, 16 * MS, 0, "None"), ("frame", 100 * MS, 40 * MS, 0, "App Deadline Missed"),
                ("frame", 900 * MS, 60 * MS, 0, "App Deadline Missed"),
                ("hilo", 150 * MS, 30 * MS, 0, "Choreographer#doFrame"), ("hilo", 950 * MS, 200 * MS, 0, "Choreographer#doFrame"),
                ("seccion", 100 * MS, 0, 0, "NAV detalle"), ("seccion", 120 * MS, 200 * MS, 0, "HTTP GET movie/{id}"),
                ("seccion", 130 * MS, 100 * MS, 0, "HTTP GET movie/{id}/providers"), ("seccion", 400 * MS, 0, 0, "MARK detalle")]
        spec = {"ventana": {"desde": {"marca": "NAV detalle"}, "hasta": {"marca": "MARK detalle"}, "margen_ms": 100},
                "metricas_usuario": [{"nombre": "detalle_ms", "desde": {"marca": "NAV detalle"},
                                      "hasta": {"marca": "HTTP GET movie/{id}/providers"}}]}
        metrics, invalid, info = perf.trace_metrics([("proceso", 0, 0, 1, "app"), ("limites", 0, 2000 * MS, 0, "")] + rows,
                                                    60, spec, set(), 34)
        m = {x[0]: x for x in metrics}
        self.assertIsNone(invalid)
        self.assertEqual(m["ventana_ms"][1], 400)
        self.assertEqual(m["frames"][1], 1)  # solo el frame de t=100 ms: el de 900 ms queda fuera
        self.assertEqual(m["hilo_max_ms"][1], 30)
        self.assertEqual(m["detalle_ms"][1], 130)  # NAV 100 → fin de providers 230
        self.assertEqual(m["detalle_ms hasta_ultima_red_ms"][1], 220)  # movie termina en 320
        self.assertEqual(m["detalle_ms hasta_ultima_red_ms"][3], "info")
        spec["ventana"]["hasta"]["marca"] = "MARK otra"
        metrics, _, info = perf.trace_metrics([("proceso", 0, 0, 1, "app")] + rows, 60, spec, set(), 34)
        self.assertIn("ventana", info["faltantes"])
        self.assertEqual({x[0]: x for x in metrics}["frames"][1], 3)

    def test_las_secciones_se_resumen_por_tipo_sin_la_marca_de_la_query(self):
        names = {"HTTP GET discover/movie #fe9d": 1, "HTTP GET discover/movie #fe7c": 1, "QUEUE GET discover/movie #fe9d": 1,
                 "TTFB GET discover/movie #fe9d": 1, "NAV home": 1, "SCREEN MainActivity onCreate": 1, "reportFullyDrawn": 1}
        summary = perf.sections_summary(names)
        self.assertEqual(summary, "HTTP ×2 (GET discover/movie ×2); QUEUE ×1 (GET discover/movie); TTFB ×1 (GET discover/movie); "
                                  "SCREEN ×1 (MainActivity onCreate); NAV ×1 (home); otras ×1 (reportFullyDrawn)")

    def test_comparar_avisa_si_la_marca_de_fin_dejo_de_ser_la_ultima_llamada(self):
        results = [
            {"flujo": "f", "metrica": "detalle_ms", "veredicto": "mejora", "antes": {"mediana": 276}, "despues": {"mediana": 205}},
            {"flujo": "f", "metrica": "detalle_ms hasta_ultima_red_ms", "veredicto": "informativa",
             "antes": {"mediana": 276}, "despues": {"mediana": 260}},
        ]
        notes = perf.definition_notes(results)
        self.assertEqual(len(notes), 1)
        self.assertIn("en despues la marca de fin termina 55 ms antes", notes[0])
        results[1]["despues"]["mediana"] = 207
        self.assertEqual(perf.definition_notes(results), [])

    def test_sin_red_no_escribe_metricas_de_red_salvo_que_ya_existan(self):
        m, _, _ = self.metrics([("frame", 0, 16 * MS, 0, "None")])
        self.assertNotIn("red_llamadas", m)
        m, _, _ = self.metrics([("frame", 0, 16 * MS, 0, "None")], known={"red_llamadas", "red GET a llamadas"})
        self.assertEqual(m["red_llamadas"][1], 0)
        self.assertEqual(m["red GET a llamadas"][1], 0)

    def test_metrica_de_usuario_entre_dos_marcas(self):
        secs = [("seccion", 100 * MS, 5 * MS, 0, "SCREEN MainActivity onResume"),
                ("seccion", 900 * MS, 5 * MS, 0, "SCREEN MainActivity onResume"),
                ("seccion", 1000 * MS, 400 * MS, 0, "HTTP GET api/home"),
                ("seccion", 1200 * MS, 600 * MS, 0, "HTTP GET api/home")]
        flow = {"metricas_usuario": [{"nombre": "home_ms", "desde": {"marca": "SCREEN MainActivity onResume",
                                                                     "cual": "ultima"},
                                      "hasta": {"marca": "HTTP GET */home"}},
                                     {"nombre": "falta_ms", "desde": {"marca": "NAV X"}, "hasta": {"marca": "NAV Y"}}]}
        m, _, info = self.metrics(secs + [("frame", 0, 16 * MS, 0, "None")], flow=flow)
        self.assertEqual(m["home_ms"][1], 900)
        self.assertEqual(m["home_ms"][3], "e2e")
        self.assertEqual(info["faltantes"], ["falta_ms"])

    def test_invalida_sin_proceso_con_patron_o_sin_frames(self):
        _, invalid, _ = perf.trace_metrics([("limites", 0, 1, 0, "")], 60, {}, set(), 34)
        self.assertIn("no aparece", invalid)
        _, invalid, _ = self.metrics([("seccion", 0, MS, 0, "SCREEN LoginActivity onCreate")],
                                     flow={"invalidar_si": ["SCREEN *Login*"]})
        self.assertIn("LoginActivity", invalid)
        _, invalid, _ = self.metrics([])
        self.assertIn("frames", invalid)
        _, invalid, _ = self.metrics([], sdk=30)
        self.assertIsNone(invalid)

    def test_parsea_la_salida_csv_de_trace_processor(self):
        text = '"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.ejemplo.app"\n' \
               '"frame",10,20,0,"App Deadline Missed, Buffer Stuffing"\n"seccion",5,"[NULL]",0,"HTTP GET a"\n\n' \
               '"x"\n1\n'
        sets = perf.parse_result_sets(text)
        self.assertEqual(len(sets), 2)
        parsed = perf.trace_rows(*sets[0])
        self.assertEqual(parsed[1], ("frame", 10, 20, 0, "App Deadline Missed, Buffer Stuffing"))
        self.assertEqual(parsed[2][2], -1)

    def test_arranque_ttid_ttfd_bind_y_hz_de_la_traza(self):
        rows = [("vsync", 0, 11_000_000, 0, ""), ("lanzamiento", 1000 * MS, 400 * MS, 0, "launching: " + PKG),
                ("hilo", 1050 * MS, 80 * MS, 0, "bindApplication"), ("hilo", 1300 * MS, 12 * MS, 0, "doFrame"),
                ("seccion", 1900 * MS, 1 * MS, 2, "reportFullyDrawn() for {%s/.Main}" % PKG),
                ("frame", 1300 * MS, 30 * MS, 0, "App Deadline Missed")]
        flow = {"familias": {"frame_p*": "info", "ttfd_ms": "e2e"}}
        m, invalid, info = self.metrics(rows, flow=flow, hz=None)
        self.assertIsNone(invalid)
        self.assertEqual(info["hz"], 90)
        self.assertEqual(m["ttid_ms"][1], 400)
        self.assertEqual(m["ttfd_ms"][1], 900)
        self.assertEqual(m["ttfd_ms"][3], "e2e")
        self.assertEqual(m["bind_application_ms"][1], 80)
        self.assertEqual(m["frame_p90_ms"][3], "info")
        self.assertEqual(m["hilo_slices_sobre_presupuesto"][1], 2)  # 12 ms supera los 11,1 ms de 90 Hz

    def test_marcas_de_usuario_aceptan_slices_del_hilo_y_el_lanzamiento(self):
        rows = [("lanzamiento", 0, 300 * MS, 0, "launching: " + PKG), ("hilo", 500 * MS, 20 * MS, 0, "Choreographer#doFrame 1"),
                ("frame", 0, 16 * MS, 0, "None")]
        flow = {"metricas_usuario": [{"nombre": "hasta_primer_frame_ms", "desde": {"marca": "launching: *"},
                                      "hasta": {"marca": "Choreographer#doFrame*", "cual": "primera"}, "familia": "app"}]}
        m, _, _ = self.metrics(rows, flow=flow)
        self.assertEqual(m["hasta_primer_frame_ms"][1], 520)

    def test_parsea_la_salida_markdown_del_modo_agente(self):
        sets = perf.parse_result_sets("| tipo | ts |\n|---|---|\n| proceso | 0 |\n| hilo | [NULL] |\n\n| x |\n|---|\n| 1 |\n")
        self.assertEqual(sets[0], (["tipo", "ts"], [["proceso", "0"], ["hilo", None]]))
        self.assertEqual(sets[1][1], [["1"]])

    def test_jit_de_la_app_es_informativo(self):
        m, _, _ = self.metrics([("jit", 0, 450 * MS, 107, ""), ("frame", 0, 16 * MS, 0, "None")])
        self.assertEqual(m["jit_ms"][1:], (450, "ms", "info"))

    def test_hz_desde_el_periodo_esperado(self):
        self.assertEqual(perf.hz_from_vsync(16_666_666), 60)
        self.assertEqual(perf.hz_from_vsync(8_333_333), 120)
        self.assertIsNone(perf.hz_from_vsync(0))

    def test_parsea_gfxinfo_y_meminfo(self):
        gfx = dict((m[0], m[1]) for m in perf.parse_gfxinfo("Janky frames: 12 (5.43%)\n90th percentile: 19ms\n"))
        self.assertEqual(gfx, {"gfx_jank_pct": 5.43, "gfx_p90_ms": 19.0})
        mem = dict((m[0], m[1]) for m in perf.parse_meminfo(
            "  Java Heap:    20480\n  Native Heap:  10240\n  TOTAL PSS:   102400   TOTAL RSS: 1\n"
            "  Views:  120   ViewRootImpl: 1\n  AppContexts: 4   Activities:  2\n"))
        self.assertEqual(mem, {"pss_mb": 100, "java_heap_mb": 20, "native_heap_mb": 10, "activities": 2, "views": 120})


FAKE_ADB = r'''#!{python}
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
if args[:1] == ["-s"]:
    args = args[2:]
if args == ["devices"]:
    print("List of devices attached\n" + "".join("%s\tdevice\n" % d for d in os.environ.get("FAKE_DEVICES", "emulator-5554").split(",")))
    sys.exit(0)
if args[0] == "pull":
    pathlib.Path(args[2]).write_bytes(b"x" * 4096)
    sys.exit(0)
cmd = " ".join(args[1:])
if cmd.startswith("getprop ro.build.version.sdk"):
    print(os.environ.get("FAKE_SDK", "34"))
elif cmd.startswith("getprop ro.product.model"):
    print("Pixel Test")
elif cmd.startswith("getprop ro.build.version.release"):
    print("14")
elif cmd.startswith("pm path"):
    print("package:/data/app/base.apk")
elif cmd.startswith("dumpsys package"):
    print("    versionCode=7 minSdk=26 targetSdk=36\n    versionName=1.0\n    flags=[ HAS_CODE ALLOW_BACKUP ]\n"
          "    lastUpdateTime=" + os.environ.get("FAKE_UPDATED", "2026-11-05 10:00:00"))
elif cmd.startswith("dumpsys thermalservice"):
    print("Thermal Status: " + os.environ.get("FAKE_THERMAL", "0"))
elif cmd.startswith("dumpsys battery"):
    print("  level: 90")
elif cmd.startswith("dumpsys activity activities"):
    print("  topResumedActivity=ActivityRecord{{1 u0 %s t5}}" % os.environ.get("FAKE_RESUMED", "com.ejemplo.app/.MainActivity"))
elif cmd.startswith("cmd package compile"):
    print("Success")
elif cmd.startswith("am broadcast"):
    print("Broadcasting: Intent {{ act=androidx.profileinstaller.action.INSTALL_PROFILE }}\nBroadcast completed: result="
          + os.environ.get("FAKE_PROFILE", "1"))
elif cmd.startswith("cmd package resolve-activity"):
    print("priority=0 preferredOrder=0 match=0x108000\ncom.ejemplo.app/.MainActivity")
elif cmd.startswith("am start"):
    print("Starting: Intent {{ cmp=com.ejemplo.app/.MainActivity }}\nStatus: ok\nLaunchState: "
          + os.environ.get("FAKE_LAUNCH", "COLD") + "\nActivity: com.ejemplo.app/.MainActivity\nTotalTime: 456\nComplete")
elif cmd.startswith("pidof"):
    if os.environ.get("FAKE_DEAD"):
        sys.exit(1)
    print("1234")
elif cmd.startswith("logcat -b crash"):
    print("11-05 10:00:01.000  1234  1234 E AndroidRuntime: FATAL EXCEPTION: main\n"
          "11-05 10:00:01.000  1234  1234 E AndroidRuntime: Process: com.ejemplo.app, PID: 1234\n"
          "11-05 10:00:01.000  1234  1234 E AndroidRuntime: java.lang.IllegalStateException: boom")
elif cmd.startswith("perfetto"):
    sys.stdin.read()
    print("4242")
elif cmd.startswith("kill -0"):
    sys.exit(1)
elif cmd.startswith("dumpsys meminfo"):
    print("  Java Heap:  2048\n  TOTAL PSS:  51200   TOTAL RSS: 1\n  Views:  10\n  Activities:  1")
elif cmd.startswith('echo "q='):
    emulator = os.environ.get("FAKE_EMULATOR")
    print("q=%s\nb=\nh=%s\nm=%s\nc=\ng=%s" % ("1" if emulator else "", "ranchu" if emulator else "qcom",
          "sdk_gphone64_arm64" if emulator else "Pixel Test", os.environ.get("FAKE_GLES", "")))
'''

FAKE_TP = r'''#!{python}
import os, re, sys
args = sys.argv[1:]
if args[:2] == ["query", "--help"]:
    print("Usage: trace_processor query -f FILE TRACE" if os.environ.get("FAKE_TP_VIEJO") else
          "Usage: trace_processor query [--format csv|markdown] -f FILE TRACE")
    sys.exit(0)
if args[:3] == ["query", "--format", "csv"]:
    args = ["query"] + args[3:]
assert args[:2] == ["query", "-f"], sys.argv
sql = open(args[2]).read()
open(os.environ["FAKE_TP_SQL"], "a").write(sql + "\n-----\n")
counter = os.environ["FAKE_TP_COUNTER"]
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
outputs = open(os.environ["FAKE_TP_OUT"]).read().split("===\n")
out = outputs[min(n, len(outputs) - 1)]
names = re.findall(r"SELECT '([^']+)' AS hbperf_marker;", sql)
if not names:
    sys.stdout.write(out)
else:
    chunks = []
    for name in names:
        chunks.append('"hbperf_marker"\n"%s"\n' % name)
        chunks.append(out if name == "metricas" else os.environ.get("FAKE_TP_OTRA", '"nombre","valor"\n"x",1\n'))
    sys.stdout.write("\n".join(c.rstrip("\n") + "\n" for c in chunks))
'''

GOOD = '"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.ejemplo.app"\n"limites",0,5000000000,0,""\n' + \
    "".join('"frame",%d,16000000,0,"None"\n' % (i * 20000000) for i in range(9)) + \
    '"frame",500000000,40000000,0,"App Deadline Missed"\n"hilo",0,30000000,0,"Choreographer#doFrame"\n' \
    '"seccion",0,300000000,0,"HTTP GET items/{id}"\n"seccion",100000000,300000000,0,"HTTP GET items/{id}"\n' \
    '"seccion",10,5,0,"SCREEN MainActivity onResume"\n'
LOGIN = '"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.ejemplo.app"\n"frame",0,16000000,0,"None"\n' \
    '"seccion",0,1000,0,"SCREEN LoginActivity onCreate"\n'


class DeviceBase(PerfBase):
    def setUp(self):
        super().setUp()
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        for name, body in (("adb", FAKE_ADB), ("trace_processor", FAKE_TP)):
            path = bin_dir / name
            path.write_text(textwrap.dedent(body).replace("{python}", sys.executable).replace("{{", "{")
                            .replace("}}", "}"), encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.env.update({"PATH": "%s%s%s" % (bin_dir, os.pathsep, os.environ.get("PATH", "")),
                         "FAKE_LOG": str(self.dir / "adb.log"), "FAKE_TP_OUT": str(self.dir / "tp.txt"),
                         "FAKE_TP_COUNTER": str(self.dir / "tp.count"), "FAKE_TP_SQL": str(self.dir / "tp.sql"),
                         "HB_PERF_ESPERA": "0"})
        self.env.pop("TRACE_PROCESSOR", None)
        self.env.pop("ADB", None)
        self.env.pop("ANDROID_SERIAL", None)
        self.plan = self.dir / "inv" / "plan.json"
        write(self.plan, json.dumps({"paquete": PKG, "hz": 60, "principales": ["jank_app_pct"], "flujos": {
            "home": {"inicio": "MainActivity", "invalidar_si": ["SCREEN *Login*"], "recorrido": "true"}}}))

    def tp_outputs(self, *outputs):
        write(self.dir / "tp.txt", "===\n".join(outputs))


GLES_REAL = "GLES: Qualcomm, Adreno (TM) 740, OpenGL ES 3.2 V@0615.0"
GLES_HOST = "GLES: Google (Apple), Android Emulator OpenGL ES Translator (Apple M2 Pro), OpenGL ES 3.0 (4.1 Metal)"
GLES_SOFT = "GLES: Google (Google Inc.), Android Emulator OpenGL ES Translator (Google SwiftShader), OpenGL ES 3.0"


def environment_text(qemu="", hardware="qcom", model="Pixel Test", characteristics="", gles=GLES_REAL):
    return "q=%s\nb=\nh=%s\nm=%s\nc=%s\ng=%s\n" % (qemu, hardware, model, characteristics, gles)


class EnvironmentTest(unittest.TestCase):
    def test_un_dispositivo_real_es_confiable(self):
        env = perf.classify_environment(environment_text())
        self.assertEqual((env["emulador"], env["software"], env["frames"]), (False, False, "ok"))
        self.assertEqual(perf.environment_warnings(env), [])

    def test_la_salida_vacia_no_inventa_un_emulador(self):
        self.assertEqual(perf.classify_environment("")["frames"], "ok")

    def test_emulador_con_gpu_del_host_da_frames_orientativos(self):
        env = perf.classify_environment(environment_text(qemu="1", hardware="ranchu", gles=GLES_HOST))
        self.assertEqual((env["emulador"], env["software"], env["frames"]), (True, False, "baja"))
        self.assertIn("es un emulador", perf.environment_warnings(env)[0])
        self.assertIn("-gpu host", perf.environment_warnings(env)[0])

    def test_emulador_con_swiftshader_no_es_confiable(self):
        env = perf.classify_environment(environment_text(qemu="1", hardware="ranchu", gles=GLES_SOFT))
        self.assertEqual((env["emulador"], env["software"], env["frames"]), (True, True, "no"))
        warning = perf.environment_warnings(env)[0]
        self.assertIn("renderiza por software", warning)
        self.assertIn("-gpu host", warning)
        self.assertIn("dispositivo físico", warning)

    def test_se_reconoce_el_emulador_por_cualquiera_de_sus_senales(self):
        for kwargs in ({"qemu": "1"}, {"hardware": "goldfish"}, {"characteristics": "emulator"},
                       {"model": "sdk_gphone64_arm64"}, {"model": "Android SDK built for x86"}):
            self.assertTrue(perf.classify_environment(environment_text(**kwargs))["emulador"], kwargs)

    def test_render_por_software_en_un_dispositivo_fisico_tampoco_es_confiable(self):
        env = perf.classify_environment(environment_text(gles="GLES: Mesa, llvmpipe (LLVM 15.0.7), OpenGL ES 3.2"))
        self.assertEqual((env["emulador"], env["frames"]), (False, "no"))


class FramesTrustTest(PerfBase):
    def rows(self):
        return read_rows_from(rows("antes", "home", "jank_app_pct", [10, 11, 10, 12, 10], unit="%")
                              + rows("despues", "home", "jank_app_pct", [2, 3, 2, 2, 3], unit="%")
                              + rows("antes", "home", "red_llamadas", [4, 4, 4, 4, 4], unit="llamadas")
                              + rows("despues", "home", "red_llamadas", [2, 2, 2, 2, 2], unit="llamadas"))

    def verdicts(self, trust):
        results, _ = perf.compare(self.rows(), trust=trust)
        return {r["metrica"]: r for r in results}

    def test_sin_aviso_el_veredicto_no_cambia(self):
        results = self.verdicts(("ok", ""))
        self.assertEqual(results["jank_app_pct"]["veredicto"], "mejora")
        self.assertFalse([a for a in results["jank_app_pct"]["avisos"] if a.startswith("frames")])

    def test_con_render_por_software_los_frames_no_tienen_veredicto_y_los_conteos_si(self):
        results = self.verdicts(("no", "emulador, render por software"))
        self.assertEqual(results["jank_app_pct"]["veredicto"], "no confiable")
        self.assertIn("frames no confiables (emulador, render por software)", results["jank_app_pct"]["avisos"])
        self.assertEqual(results["red_llamadas"]["veredicto"], "mejora")
        self.assertEqual(results["red_llamadas"]["avisos"], [])

    def test_con_gpu_del_host_el_veredicto_se_conserva_con_aviso(self):
        results = self.verdicts(("baja", "emulador, sin GPU del host verificada"))
        self.assertEqual(results["jank_app_pct"]["veredicto"], "mejora")
        self.assertTrue(any(a.startswith("frames orientativos") for a in results["jank_app_pct"]["avisos"]))

    def test_trust_lee_el_peor_entorno_de_las_fases(self):
        self.assertEqual(perf.frames_trust(self.dir), ("ok", ""))
        write(self.dir / "fases.json", json.dumps({
            "antes": {"entorno": {"emulador": True, "software": False, "frames": "baja"}},
            "despues": {"entorno": {"emulador": True, "software": True, "frames": "no"}}}))
        self.assertEqual(perf.frames_trust(self.dir), ("no", "emulador, render por software"))

    def test_comparar_y_resumen_marcan_los_frames_de_las_fases_medidas_en_software(self):
        write(self.csv, HEADER + rows("antes", "home", "jank_app_pct", [10, 11, 10, 12, 10], unit="%")
              + rows("despues", "home", "jank_app_pct", [2, 3, 2, 2, 3], unit="%")
              + rows("antes", "home", "red_llamadas", [4] * 5, unit="llamadas")
              + rows("despues", "home", "red_llamadas", [2] * 5, unit="llamadas"))
        write(self.dir / "fases.json", json.dumps({
            "antes": {"entorno": {"emulador": True, "software": True, "frames": "no"}},
            "despues": {"entorno": {"emulador": True, "software": True, "frames": "no"}}}))
        out = self.ok("comparar", self.csv)
        self.assertRegex(out, r"jank_app_pct.*no confiable")
        self.assertRegex(out, r"red_llamadas.*mejora")
        self.assertIn("no confiable = los frames se midieron con render por software", out)
        self.assertIn("frames no confiables", out)
        comparison = (self.dir / "comparacion.md").read_text(encoding="utf-8")
        self.assertRegex(comparison, r"jank_app_pct.*no confiable")
        self.ok("resumen", self.csv)
        self.assertIn("frames no confiables (emulador, render por software)", (self.dir / "resumen.md").read_text(encoding="utf-8"))


def read_rows_from(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "metricas.csv"
        path.write_text(HEADER + text, encoding="utf-8")
        return perf.read_rows(path)


class CaptureTest(DeviceBase):
    def test_captura_corridas_validas_escribe_csv_comprime_y_resume(self):
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertIn("compilación de ART fijada", out)
        self.assertIn("corrida 2/2", out)
        data = {(k[0], k[1], k[2]): v for k, v in self.read_csv_at(self.plan.parent / "metricas.csv").items()}
        self.assertEqual(data[("antes", "jank_app_pct", "1")]["valor"], "10")
        self.assertEqual(data[("antes", "red_solapadas", "2")]["valor"], "1")
        self.assertTrue((self.plan.parent / "antes" / "home_1.perfetto-trace.gz").is_file())
        self.assertTrue((self.plan.parent / "resumen.md").is_file())
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("cmd package compile -f -m speed %s" % PKG, log)
        self.assertIn("kill -TERM 4242", log)

    def test_en_un_emulador_con_render_por_software_avisa_recomienda_y_lo_registra_en_la_fase(self):
        self.tp_outputs(GOOD)
        self.env.update({"FAKE_EMULATOR": "1", "FAKE_GLES": GLES_SOFT})
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertIn("⚠ el dispositivo renderiza por software", out)
        self.assertIn("-gpu host", out)
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["entorno"]["frames"], "no")
        self.assertTrue(phases["antes"]["entorno"]["emulador"])
        self.assertRegex(out, r"jank_app_pct.*frames no confiables")
        self.assertIn("frames no confiables", (self.plan.parent / "resumen.md").read_text(encoding="utf-8"))

    def test_en_un_dispositivo_real_no_avisa_ni_agrega_entorno(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_GLES"] = GLES_REAL
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertNotIn("emulador", out)
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertNotIn("entorno", phases["antes"])

    def test_preparar_corre_antes_de_cada_corrida_y_del_calentamiento(self):
        self.tp_outputs(GOOD)
        marker = self.dir / "preparado.txt"
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["preparar"] = "echo x >> %s" % marker
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertNotIn("no tiene 'preparar'", out)
        self.assertEqual(marker.read_text(encoding="utf-8").count("x"), 3)  # calentamiento + 2 corridas
        plan["flujos"]["home"]["preparar"] = "false"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "10")
        # Un 'preparar' que falla (login que no entra, backend caído) invalida la corrida y se repite; tres seguidas
        # detienen la captura con el motivo, sin gastar los 13 intentos.
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("⚠ calentamiento: 'preparar' terminó con código 1", result.stdout)
        self.assertEqual(result.stdout.count("inválida: 'preparar' terminó con código 1 (se repite)"), 3)
        self.assertIn("3 corridas inválidas seguidas (última: 'preparar' terminó con código 1)", result.stderr)

    def test_tres_corridas_invalidas_seguidas_detienen_la_captura(self):
        self.tp_outputs(LOGIN, LOGIN, LOGIN, GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "10",
                           "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("inválida"), 3)
        self.assertIn("3 corridas inválidas seguidas", result.stderr)
        self.assertIn("las 0 válidas quedan guardadas", result.stderr)
        self.tp_outputs(GOOD, LOGIN, LOGIN, GOOD, LOGIN, GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "3",
                      "--calentamiento", "0", "--sin-compilar", "--rehacer")
        self.assertIn("corrida 3/3", out)  # dos inválidas seguidas no detienen: el contador se reinicia con una válida

    def test_una_corrida_sin_la_ventana_o_sin_la_metrica_principal_es_invalida(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["principales"] = ["detalle_ms"]
        plan["flujos"]["home"]["ventana"] = {"desde": {"marca": "NAV detalle"}, "hasta": {"marca": "MARK detalle"}}
        plan["flujos"]["home"]["metricas_usuario"] = [{"nombre": "detalle_ms", "desde": {"marca": "NAV detalle"},
                                                       "hasta": {"marca": "MARK detalle"}}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marks = GOOD + '"seccion",50000000,0,0,"NAV detalle"\n"seccion",250000000,0,0,"MARK detalle"\n'
        self.tp_outputs(GOOD, marks, marks)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertIn("sin marcas para detalle_ms, ventana: el recorrido no completó el flujo", out)
        self.assertIn("corrida 2/2", out)
        self.assertTrue(list((self.plan.parent / "antes").glob("*_invalida_*")))
        data = self.read_csv_at(self.plan.parent / "metricas.csv")
        self.assertEqual(len({k[2] for k in data}), 2)  # la inválida no entra al CSV
        self.assertEqual(len([k for k in data if k[1] == "detalle_ms"]), 2)

    def test_sin_preparar_avisa_y_relanza_la_app_si_no_esta_al_frente(self):
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        self.assertIn("el flujo no tiene 'preparar'", out)
        self.assertNotIn("am start -n", (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.env["FAKE_RESUMED"] = "com.miui.home/.launcher.Launcher"
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "1")
        self.assertEqual(result.returncode, 3)  # relanzó, pero el fake sigue en el launcher: se detiene con claridad
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("am start -n %s/.MainActivity" % PKG, log)
        self.assertIn("la pantalla activa es 'com.miui.home/.launcher.Launcher'", result.stderr)

    def test_corrida_invalida_se_guarda_aparte_y_se_repite(self):
        self.tp_outputs(LOGIN, GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                      "--calentamiento", "0", "--sin-compilar")
        self.assertIn("inválida", out)
        files = sorted(p.name for p in (self.plan.parent / "antes").iterdir())
        self.assertTrue(any("invalida" in f for f in files), files)
        self.assertEqual({k[2] for k in self.read_csv_at(self.plan.parent / "metricas.csv")}, {"2"})

    def test_sin_corridas_validas_sale_con_codigo_5(self):
        self.tp_outputs(LOGIN)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                           "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)

    def test_prueba_imprime_metricas_y_no_escribe_csv(self):
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba", "--memoria")
        self.assertIn("jank_app_pct", out)
        self.assertIn("HTTP ×2 (GET items/{id} ×2)", out)
        self.assertIn("pss_mb", out)
        self.assertFalse((self.plan.parent / "metricas.csv").exists())

    def test_precondiciones_salen_con_codigo_3(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_SDK"] = "28"
        self.assertEqual(self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes").returncode, 3)
        self.env["FAKE_SDK"] = "34"
        self.env["FAKE_THERMAL"] = "4"
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes")
        self.assertEqual(result.returncode, 3)
        self.assertIn("caliente", result.stderr)

    def test_pantalla_de_inicio_distinta_en_modo_comando_no_graba(self):
        self.tp_outputs(GOOD)
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["inicio"] = "DetailActivity"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--sin-compilar",
                           "--calentamiento", "0")
        self.assertEqual(result.returncode, 3)
        self.assertIn("DetailActivity", result.stderr)

    def test_modo_manual_espera_enter_y_permite_descartar(self):
        self.tp_outputs(GOOD)
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["recorrido"] = "manual"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                      "--calentamiento", "0", "--sin-compilar", stdin="x\n\n")
        self.assertIn("descartada por el usuario", out)
        self.assertEqual({k[2] for k in self.read_csv_at(self.plan.parent / "metricas.csv")}, {"2"})

    def test_falta_trace_processor(self):
        (self.dir / "bin" / "trace_processor").unlink()
        self.env["PATH"] = str(self.dir / "bin")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes")
        self.assertEqual(result.returncode, 3)
        self.assertIn("trace_processor", result.stderr)

    def test_consulta_acota_filas_y_ancho(self):
        self.tp_outputs('"nombre","ms"\n' + "".join('"%s",%d\n' % ("x" * 100, i) for i in range(30)))
        trace = self.dir / "t.perfetto-trace"
        trace.write_bytes(b"x")
        out = self.ok("consulta", trace, "--sql", "SELECT 1", "--limite", "5", "--ancho", "10")
        self.assertIn("| xxxxxxxxxx | 0 |", out)
        self.assertIn("25 filas más", out)

    def startup_plan(self, **extra):
        flow = {"recorrido": {"tipo": "arranque-frio", "actividad": PKG + "/.MainActivity", "espera_s": 0}}
        flow.update(extra)
        write(self.plan, json.dumps({"paquete": PKG, "principales": ["ttid_ms"], "flujos": {"arranque-frio": flow}}))

    def test_arranque_en_frio_detiene_la_app_antes_de_grabar_y_valida_el_estado(self):
        self.startup_plan()
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "1", "--calentamiento", "0",
                      "--sin-compilar")
        self.assertIn("TTID 456 ms", out)  # sin lanzamiento en la traza, el TTID sale de am start -W
        self.assertIn("No hace falta pegar", out)
        log = [json.loads(line) for line in (self.dir / "adb.log").read_text(encoding="utf-8").splitlines()]
        commands = [" ".join(a[3:]) if a[:1] == ["-s"] else " ".join(a[1:]) for a in log]
        stop = commands.index("am force-stop " + PKG)
        trace = next(i for i, c in enumerate(commands) if c.startswith("perfetto"))
        start = commands.index("am start -W -n %s/.MainActivity" % PKG)
        self.assertLess(stop, trace)
        self.assertLess(trace, start)
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["instalada"], "2026-11-05 10:00:00")
        self.assertEqual(phases["antes"]["version"], "1.0 (7)")

    def test_humo_prueba_el_arranque_sin_crear_una_investigacion(self):
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG, "--instalar", "./gradlew app:installProfiling")
        self.assertIn("corrida de prueba", out)
        self.assertIn("TTID 456 ms", out)
        self.assertIn("Secciones propias: HTTP ×2", out)
        self.assertIn("Arranque en frío (receta, sin sesión 1) · Terminal (sin chat):", out)
        self.assertIn("nuevo --receta arranque-frio --paquete %s --serial emulator-5554 --carpeta reports/perf/arranque-frio/" % PKG, out)
        self.assertIn('--instalar "./gradlew app:installProfiling"', out)
        self.assertIn("Otra pantalla o flujo · Chat nuevo · Modelo: Sonnet 5 · Esfuerzo: medio", out)
        self.assertIn("Dispositivo emulator-5554", out)
        self.assertTrue(any((self.dir / "reports/perf/humo/prueba").glob("humo_1.perfetto-trace*")))
        self.assertFalse((self.dir / "reports/perf/humo/plan.json").exists())
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("am start -W -n %s/.MainActivity" % PKG, log)

    def test_actividad_sin_paquete_se_completa_con_el_paquete_instalado(self):
        self.assertEqual(perf.component_of("com.a.profiling", "com.a.MainActivity"), "com.a.profiling/com.a.MainActivity")
        self.assertEqual(perf.component_of("com.a", ".Main"), "com.a/.Main")
        self.assertEqual(perf.component_of("com.a", "com.b/.Main"), "com.b/.Main")
        self.assertEqual(perf.component_of("com.a", ""), "")

    def test_varios_dispositivos_usan_el_serial_del_plan_o_android_serial(self):
        self.env["FAKE_DEVICES"] = "emulator-5554,NJ4"
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 3)
        self.assertIn("nuevo --serial", result.stderr)
        self.env["ANDROID_SERIAL"] = "NJ4"
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        del self.env["ANDROID_SERIAL"]
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["serial"] = "NJ4"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn('["-s", "NJ4", "shell", "perfetto', (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.assertIn("--fase antes --corridas 10", out)

    def test_cada_fase_indica_el_paso_siguiente(self):
        self.startup_plan()
        self.tp_outputs(GOOD)
        common = ["capturar", "--plan", self.plan, "--corridas", "1", "--calentamiento", "0", "--sin-compilar"]
        self.assertIn("--fase control --corridas 10", self.ok(*(common + ["--fase", "antes"])))
        self.assertIn("diagnostico --carpeta", self.ok(*(common + ["--fase", "control"])))
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"
        out = self.ok(*(common + ["--fase", "despues"]))
        self.assertIn("sesión 4 · cierre", out)
        self.assertIn("Chat nuevo · Modelo: Haiku 5.5 · Esfuerzo: bajo", out)
        self.assertIn('Texto: "Sigue hb-performance con ', out)

    def commands(self):
        return [" ".join(json.loads(line)[3:]) for line in (self.dir / "adb.log").read_text(encoding="utf-8").splitlines()
                if json.loads(line)[:1] == ["-s"]]

    def test_compilacion_completa_por_defecto_y_registrada(self):
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                      "--calentamiento", "0")
        self.assertIn("completa (speed)", out)
        self.assertIn("cmd package compile -f -m speed " + PKG, self.commands())
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["compilacion"], "completa (speed)")

    def test_compilacion_con_perfil_instala_el_baseline_profile_o_se_detiene(self):
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                "--calentamiento", "0", "--compilacion", "perfil")
        log = self.commands()
        reset = log.index("cmd package compile --reset " + PKG)
        install = next(i for i, c in enumerate(log) if c.startswith("am broadcast -a androidx.profileinstaller"))
        self.assertLess(reset, install)
        self.assertLess(install, log.index("cmd package compile -f -m speed-profile " + PKG))
        self.env["FAKE_PROFILE"] = "0"
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "1",
                           "--calentamiento", "0", "--compilacion", "perfil")
        self.assertEqual(result.returncode, 3)
        self.assertIn("--compilacion completa", result.stderr)

    def test_comparar_avisa_si_cambia_la_compilacion_o_el_jit(self):
        write(self.plan.parent / "metricas.csv", HEADER + rows("antes", "f", "jit_ms", [25, 26, 24, 25, 27], family="info")
              + rows("despues", "f", "jit_ms", [450, 460, 440, 455, 470], family="info"))
        write(self.plan.parent / "fases.json", json.dumps({"antes": {"compilacion": "completa (speed)"},
                                                           "despues": {"compilacion": "perfil (Baseline Profile + speed-profile)"}}))
        out = self.ok("comparar", self.plan.parent / "metricas.csv")
        self.assertIn("JIT de 25 ms en antes y 455 ms en después", out)
        self.assertIn("distinta compilación de ART", out)

    def test_rehacer_descarta_la_fase_y_la_mide_de_nuevo(self):
        self.tp_outputs(GOOD)
        common = ["capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--calentamiento", "0",
                  "--sin-compilar"]
        self.ok(*(common + ["--corridas", "2"]))
        out = self.ok(*(common + ["--corridas", "1", "--rehacer"]))
        self.assertIn("filas de 'antes' fuera del CSV", out)
        runs = {k[2] for k in self.read_csv_at(self.plan.parent / "metricas.csv")}
        self.assertEqual(runs, {"1"})
        self.assertTrue(any(p.name.startswith("antes-descartada-") for p in self.plan.parent.iterdir()))
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["corridas"], 1)

    def test_arranque_tibio_invalida_la_corrida(self):
        self.startup_plan()
        self.tp_outputs(GOOD)
        self.env["FAKE_LAUNCH"] = "WARM"
        result = self.perf("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "1", "--calentamiento", "0",
                           "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("WARM", result.stdout)

    def test_app_caida_invalida_la_corrida_y_muestra_el_crash(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_DEAD"] = "1"
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("IllegalStateException: boom", result.stdout)
        self.assertIn("retrace", result.stdout)

    def test_despues_con_el_mismo_build_de_antes_se_detiene(self):
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                "--calentamiento", "0", "--sin-compilar")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "despues", "--corridas", "1",
                           "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 3)
        self.assertIn("mismo que midió antes", result.stderr)
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "despues", "--corridas", "1",
                "--calentamiento", "0", "--sin-compilar")
        self.ok("comparar", self.plan.parent / "metricas.csv")
        self.assertIn("## Builds medidos", (self.plan.parent / "comparacion.md").read_text(encoding="utf-8"))

    def test_metricas_propias_desde_sql(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["metricas_sql"] = [{"archivo": "datos.sql"}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        write(self.plan.parent / "datos.sql", "SELECT 'datos_ms' AS nombre, 812 AS valor, 'ms' AS unidad -- {{PAQUETE}}")
        self.env["FAKE_TP_OTRA"] = '"nombre","valor","unidad","familia"\n"datos_ms",812,"ms","e2e"\n'
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                "--calentamiento", "0", "--sin-compilar")
        row = self.read_csv_at(self.plan.parent / "metricas.csv")[("antes", "datos_ms", "1")]
        self.assertEqual((row["valor"], row["unidad"], row["familia"]), ("812", "ms", "e2e"))
        self.assertIn("-- " + PKG, (self.dir / "tp.sql").read_text(encoding="utf-8"))

    def test_trace_processor_viejo_usa_query_sin_format(self):
        self.env["FAKE_TP_VIEJO"] = "1"
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")

    def test_consulta_completa_parametros_y_toma_el_paquete_del_plan(self):
        self.tp_outputs('"a"\n1\n')
        trace = self.plan.parent / "antes" / "home_1.perfetto-trace.gz"
        write(trace, "x")
        query = self.dir / "q.sql"
        write(query, "SELECT 1 AS a FROM process WHERE name = '{{PAQUETE}}' AND x > {{UMBRAL}} -- {{TRAMO_MS}}")
        self.ok("consulta", trace, query, "--param", "UMBRAL=5")
        sql = (self.dir / "tp.sql").read_text(encoding="utf-8")
        self.assertIn("name = '%s' AND x > 5 -- 250" % PKG, sql)
        result = self.perf("consulta", trace, query)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--param UMBRAL", result.stderr)

    def test_diagnostico_escribe_mediana_y_peor_con_las_consultas_del_escenario(self):
        self.startup_plan()
        folder = self.plan.parent
        write(folder / "metricas.csv", HEADER + rows("antes", "arranque-frio", "ttid_ms", [400, 500, 450, 420, 480]))
        for run in range(1, 6):
            write(folder / "antes" / ("arranque-frio_%d.perfetto-trace.gz" % run), "x")
        self.env["FAKE_TP_OTRA"] = '"slice","ms"\n"Choreographer#doFrame 1",12.500000\n'
        self.tp_outputs('"x"\n1\n')
        out = self.ok("diagnostico", "--carpeta", folder)
        self.assertIn("corrida 3, corrida 2", out)  # mediana 450 (corrida 3) y peor 500 (corrida 2)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("arranque_hitos", md)
        self.assertIn("## Corrida 2 (peor)", md)
        self.assertIn("| Choreographer#doFrame 1 | 12.5 |", md)
        self.assertNotIn("llamadas_solapadas", md)  # sin red no corre el grupo red
        self.assertNotIn("{{", (self.dir / "tp.sql").read_text(encoding="utf-8"))

    def read_csv_at(self, path):
        with Path(path).open(newline="", encoding="utf-8") as f:
            return {(r["fase"], r["metrica"], r["corrida"]): r for r in csv.DictReader(f)}


class HarTest(PerfBase):
    def write_har(self, path, entries):
        write(self.dir / path, json.dumps({"log": {"entries": entries}}))
        return self.dir / path

    def test_har_cuenta_llamadas_solapadas_repetidas_y_tiempos_por_ronda(self):
        first = self.write_har("red/1/network.har", [
            entry("GET", "https://api.test/items/123?x=1", "2026-01-01T10:00:00.000Z", 100),
            entry("GET", "https://api.test/items/456", "2026-01-01T10:00:00.050Z", 300),
            entry("POST", "https://api.test/login", "2026-01-01T10:00:05Z", 50)])
        second = self.write_har("red/2/network.har", [entry("GET", "https://api.test/items/9", "2026-01-01T10:01:00Z", 120)])
        self.ok("har", "--fase", "antes", "--flujo", "f", "--csv", self.csv, first, second)
        data = self.read_csv()
        self.assertEqual(data[("antes", "red_llamadas", "1")]["valor"], "3")
        self.assertEqual(data[("antes", "red_solapadas", "1")]["valor"], "1")
        self.assertEqual(data[("antes", "red_repetidas_2s", "1")]["valor"], "1")
        self.assertEqual(data[("antes", "red GET api.test/items/{id} llamadas", "1")]["valor"], "2")
        self.assertEqual(data[("antes", "red GET api.test/items/{id} ms", "1")]["familia"], "e2e")
        self.assertEqual(data[("antes", "red POST api.test/login llamadas", "2")]["valor"], "0")

    def test_har_completa_con_cero_los_endpoints_que_desaparecen_y_no_duplica(self):
        before = self.write_har("a/1/network.har", [entry("GET", "https://api.test/config", "2026-01-01T10:00:00Z", 10)])
        after = self.write_har("d/1/network.har", [entry("GET", "https://api.test/items", "2026-01-01T11:00:00Z", 10)])
        self.ok("har", "--fase", "antes", "--flujo", "f", "--csv", self.csv, before)
        self.ok("har", "--fase", "despues", "--flujo", "f", "--csv", self.csv, after)
        self.assertEqual(self.read_csv()[("despues", "red GET api.test/config llamadas", "1")]["valor"], "0")
        result = self.perf("har", "--fase", "antes", "--flujo", "f", "--csv", self.csv, before)
        self.assertEqual(result.returncode, 2)
        self.assertIn("ya hay filas", result.stderr)

    def test_har_sin_fechas_no_calcula_solapadas(self):
        path = self.write_har("x/network.har", [{"request": {"method": "GET", "url": "https://api.test/a"}}])
        self.assertIn("no se calcularon", self.ok("har", "--fase", "antes", "--flujo", "f", "--csv", self.csv, path))
        self.assertNotIn(("antes", "red_solapadas", "1"), self.read_csv())


class ReportTest(PerfBase):
    def test_reporte_markdown_y_html_desde_estado_y_csv(self):
        folder = self.dir / "inv"
        write(folder / "estado.md", "# Rendimiento · <Home> · 2026-01-02\n\n## Resumen ejecutivo\n\nEl jank bajó **mucho**.\n\n"
                                    "## Hallazgos\n\n| # | Síntoma |\n| --- | --- |\n| H1 | Doble <carga> |\n\n"
                                    "## Métricas\n<!-- perf:metricas -->\ntabla\n<!-- /perf:metricas -->\n")
        write(folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {}}, "principales": ["jank_app_pct", "no_existe"]}))
        write(folder / "metricas.csv", HEADER + rows("antes", "f", "jank_app_pct", [9, 10, 9, 10, 9], "%") +
              rows("despues", "f", "jank_app_pct", [3] * 5, "%"))
        out = self.ok("reporte", "--carpeta", folder, "--html")
        self.assertIn("no_existe", out)
        md = (folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("## Métricas principales", md)
        self.assertIn("| Depende de | Antes | Después | Cambio | Veredicto | Qué significa |", md)
        self.assertIn("| solo la app | 9 % | 3 % | -6 % (-66.67 %) | mejora | funcionó", md)
        self.assertIn("## Cómo leer este reporte", md)
        self.assertIn("El jank bajó **mucho**.", md)
        self.assertFalse((folder / "reporte.md").exists())
        page = (folder / "reporte-final.html").read_text(encoding="utf-8")
        self.assertIn("<title>Rendimiento · &lt;Home&gt; · 2026-01-02</title>", page)
        self.assertIn("Doble &lt;carga&gt;", page)
        self.assertIn("<strong>mucho</strong>", page)
        self.assertIn('class="verdict v-better">mejora', page)
        self.assertIn('<nav class="toc"><a href="#s0">', page)
        self.assertIn("<svg", page)
        self.assertNotIn("{{", page)

    def test_reporte_marca_no_confiable_una_principal_de_frames_medida_con_render_por_software(self):
        folder = self.dir / "inv"
        write(folder / "estado.md", "# Rendimiento · Home · 2026-11-09\n\n## Resumen ejecutivo\n\nTexto.\n")
        write(folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {}}, "principales": ["jank_app_pct"],
                                                "mejoras": [{"id": "M1", "titulo": "Menos jank", "flujo": "f",
                                                             "metrica": "jank_app_pct", "estado": "aplicada"}]}))
        write(folder / "metricas.csv", HEADER + rows("antes", "f", "jank_app_pct", [9, 10, 9, 10, 9], "%") +
              rows("despues", "f", "jank_app_pct", [3] * 5, "%"))
        write(folder / "fases.json", json.dumps({"antes": {"entorno": {"emulador": True, "software": True, "frames": "no"}},
                                                  "despues": {"entorno": {"emulador": True, "software": True, "frames": "no"}}}))
        self.ok("reporte", "--carpeta", folder, "--html")
        md = (folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("| no confiable | no confiable: los frames se midieron con render por software", md)
        self.assertNotIn("| mejora |", md)
        self.assertIn("— sin veredicto", md)  # la mejora no se declara lograda con frames que no valen
        page = (folder / "reporte-final.html").read_text(encoding="utf-8")
        self.assertIn('class="verdict v-same">no confiable', page)

    def test_reporte_inicial_con_plan_y_final_con_propuesto_contra_logrado(self):
        folder = self.dir / "inv"
        write(folder / "estado.md", "# Rendimiento · Arranque · 2026-11-05\n\n## Ficha\n\n| Campo | Valor |\n| --- | --- |\n"
                                    "| Alcance | Arranque en frío |\n| Precondiciones | set fijo secreto |\n"
                                    "| Dispositivo | Pixel |\n\n### Set fijo\n\n| # | dato |\n| --- | --- |\n| 1 | x |\n\n"
                                    "## Plan de mejoras\n\n<!-- perf:mejoras -->\n<!-- /perf:mejoras -->\n\n"
                                    "## Lectura de la comparación\n\nEl TTID bajó.\n")
        write(folder / "plan.json", json.dumps({"paquete": PKG, "principales": ["ttid_ms"], "flujos": {"a": {}},
                                                "mejoras": [{"id": "M1", "titulo": "Clave raw", "hallazgo": "H0",
                                                             "metrica": "ttid_ms", "esperado": "-20 %",
                                                             "prioridad": "alta", "estado": "aprobada"}]}))
        write(folder / "metricas.csv", HEADER + rows("antes", "a", "ttid_ms", [400, 410, 405, 395, 402]))
        self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
        initial = (folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("## Plan de mejoras", initial)
        self.assertIn("> Lo que se propone cambiar", initial)
        self.assertIn("| M1 | Clave raw | H0 | ttid_ms | 402 ms | -20 % | alta |", initial)
        self.assertIn("| Depende de | Mediana | P90 | Mín – máx | Corridas | Ruido de medición | Avisos |", initial)
        self.assertIn("| a | ttid_ms | solo la app | 402 ms | 410 ms | 395 – 410 | 5 | — | — |", initial)
        self.assertIn("## Cómo leer este reporte", initial)
        self.assertIn("Arranque en frío", initial)
        self.assertNotIn("secreto", initial)
        self.assertNotIn("Set fijo", initial)
        self.assertIn("| M1 | Clave raw |", (folder / "estado.md").read_text(encoding="utf-8"))
        self.assertTrue((folder / "reporte-inicial.html").is_file())
        write(folder / "metricas.csv", HEADER + rows("antes", "a", "ttid_ms", [400, 410, 405, 395, 402])
              + rows("despues", "a", "ttid_ms", [300, 310, 305, 295, 302]))
        self.ok("reporte", "--carpeta", folder)
        final = (folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("## Mejoras: esperado contra logrado", final)
        self.assertIn("| M1 | Clave raw | ttid_ms | 402 ms | -20 % | 302 ms | -24.88 % | mejora | aprobada | — no aplicada |", final)
        self.assertIn("## De los hallazgos al resultado", final)
        self.assertIn("1 hallazgos → 1 mejoras propuestas → 0 aplicadas → 0 funcionaron", final)
        self.assertIn("El TTID bajó.", final)
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["estado"] = "aplicada"
        write(folder / "plan.json", json.dumps(plan))
        self.ok("reporte", "--carpeta", folder, "--html")
        final = (folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("| M1 | Clave raw | H0 | ✔ funcionó | ttid_ms: 402 ms → 302 ms (-24.88 %) · funcionó", final)
        page = (folder / "reporte-final.html").read_text(encoding="utf-8")
        self.assertIn('<div class="step ok"><b>1</b><span>Funcionaron</span></div>', page)
        self.assertIn('<td class="ok">✔ funcionó</td>', page)
        self.assertIn('<span class="state s-aplicada" title="aplicada · implementada; se mide en la fase después">aplicada</span>', page)

    def test_hallazgos_dicen_que_pasa_con_cada_uno_y_su_resultado(self):
        folder = self.dir / "inv"
        write(folder / "estado.md", "# Rendimiento · Favoritos · 2026-11-06\n\n## Hallazgos\n\n"
                                    "| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n"
                                    "| H1 | Carga lenta | 131 ms | Red en el hilo | bug |\n"
                                    "| H2 | Jank | 2 % | — | descartado |\n"
                                    "| H3 | Red solapada | n=3 | — | sin veredicto estadístico |\n"
                                    "| H4 | GC | 1 | Lista | mejorable |\n")
        write(folder / "plan.json", json.dumps({"paquete": PKG, "principales": ["carga_ms"], "flujos": {"f": {}},
                                                "mejoras": [{"id": "M1", "titulo": "Caché", "hallazgo": "H1",
                                                             "metrica": "carga_ms", "estado": "propuesta"},
                                                            {"id": "M2", "titulo": "Lista", "hallazgo": "H4",
                                                             "metrica": "gc_count", "estado": "propuesta"}]}))
        write(folder / "metricas.csv", HEADER + rows("antes", "f", "carga_ms", [131, 130, 132, 129, 131]))
        self.ok("reporte", "--carpeta", folder, "--inicial")
        initial = (folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("| # | Síntoma | Evidencia | Causa raíz | Tipo | Qué pasa con él |", initial)
        self.assertIn("| H1 | Carga lenta | 131 ms | Red en el hilo | bug | M1 (propuesta) |", initial)
        self.assertIn("| H2 | Jank | 2 % | — | descartado | descartado: se investigó y no es la causa; no hay nada que hacer |", initial)
        self.assertIn("| H3 | Red solapada | n=3 | — | sin veredicto estadístico | no se pudo confirmar ni descartar con estos datos; sin acción |", initial)
        self.assertIn("No todos se convierten en mejoras", initial)
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["estado"] = "aplicada"
        plan["mejoras"][1]["estado"] = "descartada"
        write(folder / "plan.json", json.dumps(plan))
        write(folder / "metricas.csv", HEADER + rows("antes", "f", "carga_ms", [131, 130, 132, 129, 131])
              + rows("despues", "f", "carga_ms", [46, 45, 47, 46, 44]))
        self.ok("reporte", "--carpeta", folder)
        final = (folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("| # | Síntoma | Evidencia | Causa raíz | Tipo | Resultado |", final)
        self.assertIn("| H1 | Carga lenta | 131 ms | Red en el hilo | bug | ✔ M1 funcionó: carga_ms |", final)
        self.assertIn("| H4 | GC | 1 | Lista | mejorable | M2: no se aplicó (descartada) |", final)
        self.assertIn("4 hallazgos → 2 mejoras propuestas → 1 aplicadas → 1 funcionaron", final)
        self.assertIn("| M2 | Lista | H4 | — no aplicada | descartada · no se aplica |", final)

    def test_reporte_exige_estado(self):
        self.assertEqual(self.perf("reporte", "--carpeta", self.dir).returncode, 2)


class NuevoTest(DeviceBase):
    def test_nuevo_ignora_la_carpeta_en_git_info_exclude(self):
        subprocess.run(["git", "init", "-q", str(self.dir)], check=True)
        out = self.ok("nuevo", "--carpeta", self.dir / "reports/perf/x/2026-11-06", "--paquete", PKG, "--flujo", "x")
        self.assertIn("✔ git ignora reports/perf/x/2026-11-06 (en .git/info/exclude", out)
        self.assertIn("/reports/perf/x/2026-11-06/\n", (self.dir / ".git/info/exclude").read_text(encoding="utf-8"))
        out = self.ok("nuevo", "--carpeta", self.dir / "reports/perf/x/2026-11-07", "--paquete", PKG, "--flujo", "x")
        self.assertIn("git ignora", out)
        plan = json.loads((self.dir / "reports/perf/x/2026-11-07/plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["modelos"]["intermedio"], "Sonnet 5")

    def test_receta_arranque_frio_arma_plan_y_estado_listos_para_medir(self):
        folder = self.dir / "reports" / "perf" / "arranque" / "2026-11-05"
        out = self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--receta", "arranque-frio", "--red")
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        flow = plan["flujos"]["arranque-frio"]
        self.assertEqual(flow["recorrido"], {"tipo": "arranque-frio", "actividad": PKG + "/.MainActivity", "espera_s": 5})
        self.assertEqual(flow["familias"]["ttfd_ms"], "e2e")
        self.assertEqual(plan["principales"], ["ttid_ms", "ttfd_ms", "hilo_max_ms"])
        self.assertEqual(plan["compilacion"], "completa")
        self.assertNotIn("hz", plan)
        state = (folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("arranque en frío", state)
        self.assertIn("Pixel Test · Android 14 (API 34)", state)
        self.assertNotIn("{{", state)
        self.assertIn("--fase control --corridas 10", out)
        self.assertIn("1. **Terminal** (sin chat)", state)
        self.assertIn("`cd ", state)
        self.assertIn("diagnostico --carpeta", state)
        self.assertEqual(self.perf("nuevo", "--carpeta", folder, "--paquete", PKG).returncode, 2)
        other = self.dir / "otra"
        out = self.ok("nuevo", "--carpeta", other, "--paquete", PKG, "--flujo", "detalle",
                      "--instalar", "./gradlew :app:installProfiling")
        self.assertEqual(json.loads((other / "plan.json").read_text(encoding="utf-8"))["instalar"],
                         "./gradlew :app:installProfiling")
        self.assertIn("perf.py siguiente", out)
        out = self.ok("nuevo", "--carpeta", self.dir / "triage", "--paquete", PKG, "--flujo", "x", "--triage")
        self.assertEqual(json.loads((self.dir / "triage" / "plan.json").read_text(encoding="utf-8"))["profundidad"], "triage")

    def test_con_varios_dispositivos_avisa_y_guarda_el_serial_elegido(self):
        self.env["FAKE_DEVICES"] = "emulator-5554,NJ4"
        out = self.ok("nuevo", "--carpeta", self.dir / "a", "--paquete", PKG, "--receta", "arranque-frio")
        self.assertIn("Sin dispositivo", out)
        self.assertEqual(json.loads((self.dir / "a" / "plan.json").read_text(encoding="utf-8"))
                         ["flujos"]["arranque-frio"]["recorrido"]["actividad"], "")
        self.ok("nuevo", "--carpeta", self.dir / "b", "--paquete", PKG, "--receta", "arranque-frio", "--serial", "NJ4")
        plan = json.loads((self.dir / "b" / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["serial"], "NJ4")
        self.assertEqual(plan["flujos"]["arranque-frio"]["recorrido"]["actividad"], PKG + "/.MainActivity")


class NoLeerTest(DeviceBase):
    def test_une_flags_plan_y_agents_md_sin_duplicados(self):
        write(self.dir / "AGENTS.md", "# P\n\n## Performance\n\n- **No leer:** docs/ALCANCE-*, `secretos/`; ~/otro/proyecto\n"
              "- Otra línea: x\n")
        found = perf.read_no_leer(self.dir, plan={"no_leer": ["docs/ALCANCE-*", "tmp/"]}, extra=["casos/"])
        self.assertEqual(found, ["casos/", "docs/ALCANCE-*", "tmp/", "secretos/", "~/otro/proyecto"])

    def test_sin_agents_md_ni_lista_no_hay_rutas(self):
        self.assertEqual(perf.read_no_leer(self.dir), [])
        write(self.dir / "AGENTS.md", "# P\nno hay nada\n")
        self.assertEqual(perf.read_no_leer(self.dir), [])

    def test_rutas_relativas_carpetas_y_absolutas(self):
        patterns = ["docs/ALCANCE-*", "secretos/", "**/golden/**", str(self.dir / "fuera" / "aparte")]
        denied = lambda rel: perf.is_denied(self.dir / rel, self.dir, patterns)  # noqa: E731
        self.assertTrue(denied("docs/ALCANCE-1.md"))
        self.assertTrue(denied("secretos/a/b.kt"))
        self.assertTrue(denied("app/src/golden/x.png"))
        self.assertFalse(denied("docs/README.md"))
        self.assertFalse(denied("app/src/main/Secretos.kt"))
        self.assertTrue(perf.is_denied(self.dir / "fuera" / "aparte" / "x.md", self.dir, patterns))
        self.assertFalse(perf.is_denied(self.dir / "fuera" / "otra" / "x.md", self.dir, patterns))
        self.assertTrue(perf.is_denied(Path(os.path.expanduser("~/otro/proyecto/x")), self.dir, ["~/otro/proyecto"]))

    def test_nuevo_guarda_la_lista_en_el_plan_y_en_estado_md(self):
        write(self.dir / "AGENTS.md", "## Rendimiento\n- No leer: docs/ALCANCE-*\n")
        folder = self.dir / "reports" / "perf" / "x"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "x", "--no-leer", "casos/")
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["no_leer"], ["casos/", "docs/ALCANCE-*"])
        self.assertIn("| No leer | `casos/`, `docs/ALCANCE-*` |", (folder / "estado.md").read_text(encoding="utf-8"))
        other = self.dir / "reports" / "perf" / "y"
        self.ok("nuevo", "--carpeta", other, "--paquete", PKG, "--flujo", "x")
        self.assertIn("docs/ALCANCE-*", json.loads((other / "plan.json").read_text(encoding="utf-8"))["no_leer"])

    def test_sin_lista_el_estado_dice_ninguna_y_el_plan_no_la_trae(self):
        folder = self.dir / "reports" / "perf" / "z"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "x")
        self.assertNotIn("no_leer", json.loads((folder / "plan.json").read_text(encoding="utf-8")))
        self.assertIn("| No leer | ninguna |", (folder / "estado.md").read_text(encoding="utf-8"))

    def test_los_textos_de_los_chats_nuevos_repiten_la_lista(self):
        step = perf.chat("Usa hb-performance con estado.md", "intermedio", "medio", "sesión 2", {"no_leer": ["docs/ALCANCE-*", "casos/"]})
        self.assertIn("No leas ni busques en: docs/ALCANCE-*, casos/.", step["texto"])
        self.assertNotIn("No leas", perf.chat("x", "intermedio", "medio", "y", {})["texto"])

    def test_un_plan_con_no_leer_mal_formado_se_rechaza(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["no_leer"] = "docs/"
        write(self.plan, json.dumps(plan))
        result = self.perf("capturar", "--plan", self.plan, "--prueba", "--paquete", PKG, "--carpeta", self.dir / "p")
        self.assertEqual(result.returncode, 2)
        self.assertIn("'no_leer' es una lista", result.stderr)


class NextStepTest(PerfBase):
    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = {"paquete": PKG, "principales": ["ttid_ms"], "flujos": {"arranque-frio": {
            "recorrido": {"tipo": "arranque-frio", "actividad": PKG + "/.Main", "espera_s": 5}}}, "mejoras": []}
        self.save()
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))

    def save(self):
        write(self.folder / "plan.json", json.dumps(self.plan))

    def phases(self, *names):
        write(self.folder / "fases.json", json.dumps({n: {"fecha": "2026-11-05"} for n in names}))

    def step(self):
        return perf.next_steps(self.folder, self.plan)

    def test_recorre_las_fases_desde_la_ultima_hacia_atras(self):
        title, steps = self.step()
        self.assertEqual(title, "medición antes y control (sin chat)")
        self.assertEqual(len(steps), 5)  # prueba, antes, control, diagnostico y el chat de la sesión 2
        self.assertTrue(all(s["tipo"] == "terminal" and s["texto"].startswith("cd ") for s in steps[:4]))
        self.assertEqual(steps[4]["tipo"], "chat")
        self.assertEqual((steps[4]["modelo"], steps[4]["esfuerzo"]), ("Sonnet 5", "alto"))
        self.assertIn("--prueba", steps[0]["texto"])
        self.assertIn("abre la app 10 veces", steps[1]["tu"])
        write(self.folder / "prueba" / "arranque-frio_1.perfetto-trace.gz", "x")
        self.assertIn("--fase antes --corridas 10", self.step()[1][0]["texto"])
        self.phases("antes")
        self.assertIn("--fase control", self.step()[1][0]["texto"])
        self.phases("antes", "control")
        self.assertIn("diagnostico --carpeta", self.step()[1][0]["texto"])
        write(self.folder / "diagnostico.md", "x")
        self.assertEqual(self.step()[0], "sesión 2 · diagnóstico")
        self.plan["mejoras"] = [{"id": "M1", "titulo": "a"}, {"id": "M2", "titulo": "b", "estado": "propuesta"}]
        title, steps = self.step()
        self.assertEqual(title, "decisión del usuario (sin chat)")
        self.assertIn("decidir --carpeta", steps[0]["texto"])
        self.assertIn("--aprobar M1,M2", steps[0]["texto"])
        self.plan["mejoras"][1]["estado"] = "aprobada"
        step = self.step()[1][0]
        self.assertIn("sesión 3, aplica M2", step["texto"])
        self.assertEqual(step["esfuerzo"], "medio")
        self.plan["mejoras"][1]["estado"] = "aplicada"
        title, steps = self.step()
        self.assertEqual(title, "medición después (sin chat)")
        self.assertIn("guárdalo como 'instalar'", steps[0]["texto"])
        self.plan["instalar"] = "./gradlew :app:installProfiling"
        self.plan["serial"] = "ABC123"
        steps = self.step()[1]
        self.assertTrue(steps[0]["texto"].endswith("&& ANDROID_SERIAL=ABC123 ./gradlew :app:installProfiling"))
        self.assertIn("--fase despues --corridas 10", steps[1]["texto"])
        self.plan["instalar"] = "adb -s ABC123 install -r app.apk"
        self.assertNotIn("ANDROID_SERIAL", self.step()[1][0]["texto"])
        self.plan["modelos"] = {"economico": "GPT-5 mini"}
        self.phases("antes", "control", "despues")
        title, steps = self.step()
        self.assertEqual(title, "sesión 4 · cierre")
        self.assertEqual(steps[0]["modelo"], "GPT-5 mini")
        write(self.folder / "reporte-final.md", "x")
        self.assertEqual(self.step()[0], "investigación cerrada")

    def test_triage_mide_tres_corridas_sin_control_y_cierra_con_el_reporte_inicial(self):
        self.plan["profundidad"] = "triage"
        self.plan["flujos"] = {"detalle": {"inicio": "MainActivity", "recorrido": "adb shell input tap 1 1"}}
        write(self.folder / "prueba" / "detalle_1.perfetto-trace.gz", "x")
        title, steps = self.step()
        self.assertEqual(title, "medición antes (sin chat)")
        self.assertIn("--fase antes --corridas 3", steps[0]["texto"])
        self.assertIn("triage: 3 corridas, sin control", steps[0]["que"])
        self.assertIn("(3 corridas)", steps[0]["tu"])
        self.assertFalse(any("--fase control" in s["texto"] for s in steps))
        self.phases("antes")
        title, steps = self.step()
        self.assertEqual(title, "diagnóstico (sin chat)")
        self.assertIn("diagnostico --carpeta", steps[0]["texto"])
        write(self.folder / "diagnostico.md", "x")
        self.assertEqual(self.step()[0], "sesión 2 · diagnóstico")
        write(self.folder / "reporte-inicial.md", "x")
        title, steps = self.step()
        self.assertEqual(title, "triage cerrado")
        self.assertEqual(steps[0]["tipo"], "archivo")
        self.plan["profundidad"] = "riguroso"
        self.assertEqual(self.step()[0], "sesión 2 · diagnóstico")  # ya no cierra: sigue con el plan de mejoras
        self.plan["profundidad"] = "ligero"
        self.save()
        self.assertEqual(self.perf("siguiente", "--carpeta", self.folder).returncode, 2)

    def test_una_mejora_aprobada_o_aplicada_despues_del_cierre_reabre_la_investigacion(self):
        self.phases("antes", "control", "despues")
        self.plan["mejoras"] = [{"id": "M1", "titulo": "a", "estado": "aplicada", "aplicada_en": "2026-11-04T10:00:00"},
                                {"id": "M2", "titulo": "b", "estado": "pendiente"}]
        write(self.folder / "reporte-final.html", "x")
        self.assertEqual(self.step()[0], "investigación cerrada")
        self.plan["mejoras"][1]["estado"] = "aprobada"
        self.assertIn("sesión 3, aplica M2", self.step()[1][0]["texto"])
        self.plan["mejoras"][1]["estado"] = "aplicada"
        self.plan["mejoras"][1]["aplicada_en"] = "2026-11-06T12:00:00"  # después de fases.despues (2026-11-05)
        self.plan["instalar"] = "./gradlew app:installProfiling"
        title, steps = self.step()
        self.assertEqual(title, "medición después (sin chat)")
        self.assertIn("--fase despues --corridas 10 --rehacer", steps[1]["texto"])
        self.assertIn("de nuevo", steps[1]["que"])
        self.save()
        self.ok("decidir", "--carpeta", self.folder, "--aplicada", "M2")
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        self.assertTrue(plan["mejoras"][1]["aplicada_en"].startswith("20"))

    def test_sin_mejoras_aprobadas_va_al_cierre(self):
        self.phases("antes", "control")
        write(self.folder / "diagnostico.md", "x")
        self.plan["mejoras"] = [{"id": "M1", "titulo": "a", "estado": "descartada"},
                                {"id": "M2", "titulo": "b", "estado": "pendiente"}]
        self.assertEqual(self.step()[0], "sesión 4 · cierre sin mejoras aplicadas")
        write(self.folder / "reporte.html", "x")
        title, steps = self.step()
        self.assertEqual((title, steps[0]["tipo"], steps[0]["texto"]),
                         ("investigación cerrada", "archivo", str((self.folder / "reporte.html").resolve())))

    def test_siguiente_escribe_el_paso_en_estado(self):
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Siguiente · medición antes y control", out)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("- **Paso:** medición antes y control (sin chat)", state)
        self.assertIn("  1. **Terminal** (sin chat) · una corrida de prueba", state)
        self.assertIn("     `cd ", state)
        self.assertIn("     Tú: ", state)
        self.assertIn("**Chat nuevo** · Modelo: Sonnet 5 · Esfuerzo: alto", state)
        self.assertIn("## Ficha", state)
        self.phases("antes", "control")
        self.ok("siguiente", "--carpeta", self.folder)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertNotIn("--prueba", state)
        self.assertEqual(state.count("- **Paso:**"), 1)

    def test_decidir_registra_la_decision_y_la_aplicacion(self):
        self.phases("antes", "control")
        self.plan["mejoras"] = [{"id": i, "titulo": i, "estado": "propuesta"} for i in ("M1", "M2", "M3")]
        self.save()
        out = self.ok("decidir", "--carpeta", self.folder, "--aprobar", "M1", "--descartar", "M2", "--pendiente", "M3")
        self.assertIn("sesión 3, aplica M1", out)
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual([m["estado"] for m in plan["mejoras"]], ["aprobada", "descartada", "pendiente"])
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("aprobadas M1; descartadas M2; pendientes M3 (perf.py decidir)", state)
        self.assertNotIn("<AAAA-MM-DD", state)
        self.assertIn("| M2 | M2 |", state)
        out = self.ok("decidir", "--carpeta", self.folder, "--aplicada", "M1")
        self.assertIn("medición después", out)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertLess(state.index("aprobadas M1"), state.index("aplicadas M1"))
        result = self.perf("decidir", "--carpeta", self.folder, "--aprobar", "M9")
        self.assertEqual(result.returncode, 2)
        self.assertIn("M9", result.stderr)
        self.assertEqual(self.perf("decidir", "--carpeta", self.folder, "--aprobar", "-").returncode, 2)

    def test_consumo_agrega_filas_a_la_tabla(self):
        out = self.ok("consumo", "--carpeta", self.folder, "--sesion", "0 · setup", "--costo", "2.03 USD",
                      "--modelo", "Sonnet 5", "--pasos", "66")
        self.assertIn("✔ Consumo: | 0 · setup | Sonnet 5 | 2.03 USD | 66 |", out)
        self.ok("consumo", "--carpeta", self.folder, "--sesion", "4 · cierre", "--costo", "0.016 USD")
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        tail = state[state.index("## Consumo"):]
        self.assertIn("| 0 · setup | Sonnet 5 | 2.03 USD | 66 |\n| 4 · cierre | — | 0.016 USD | — |", tail)
        self.assertEqual(tail.count("| Sesión |"), 1)
        result = self.perf("consumo", "--carpeta", self.folder, "--sesion", "3", "--costo", "<lo que muestre /cost>")
        self.assertEqual(result.returncode, 2)
        self.assertIn("reemplaza los <...>", result.stderr)

    def test_plan_valida_estados_e_instalar(self):
        self.plan["mejoras"] = [{"id": "M1", "titulo": "a", "estado": "lista"}]
        self.save()
        result = self.perf("siguiente", "--carpeta", self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("propuesta, aprobada", result.stderr)
        self.plan["mejoras"] = []
        self.plan["instalar"] = ["./gradlew"]
        self.save()
        self.assertEqual(self.perf("siguiente", "--carpeta", self.folder).returncode, 2)


class InstrumentTest(PerfBase):
    def test_copia_las_plantillas_segun_el_stack_sin_pisar_nada(self):
        module = self.dir / "app"
        write(module / "build.gradle.kts", "dependencies { implementation(libs.retrofit); implementation(libs.okhttp) }")
        existing = module / "src/perf/kotlin/com/ejemplo/app/perf/SectionTracer.kt"
        write(existing, "// propio")
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.app.perf", "--sin-fragments")
        base = module / "src/perf/kotlin/com/ejemplo/app/perf"
        self.assertEqual(existing.read_text(encoding="utf-8"), "// propio")
        self.assertIn("ya existe", out)
        self.assertIn("retrofit2.Invocation", (base / "HttpSectionName.kt").read_text(encoding="utf-8"))
        self.assertNotIn("Fragment", (base / "ScreenTraceCallbacks.kt").read_text(encoding="utf-8"))
        listener = (base / "TraceEventListener.kt").read_text(encoding="utf-8")
        self.assertIn("package com.ejemplo.app.perf", listener)
        self.assertNotIn("{{PAQUETE}}", listener)
        self.assertTrue((module / "src/testDebug/kotlin/com/ejemplo/app/perf/TraceEventListenerTest.kt").is_file())
        tracer_test = (module / "src/testDebug/kotlin/com/ejemplo/app/perf/SectionTracerTest.kt").read_text(encoding="utf-8")
        self.assertIn("beginAsyncSection", tracer_test)
        self.assertNotIn("hb-perf:red", tracer_test)

    def test_genera_el_cableado_segun_hilt_y_actualiza_solo_lo_suyo(self):
        module = self.dir / "app"
        write(module / "build.gradle.kts", "dependencies { implementation(libs.hilt.android); implementation(libs.okhttp) }")
        (module / "src/main/java").mkdir(parents=True)
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments")
        self.assertIn("Hilt: sí", out)
        self.assertIn("código principal en src/main/java", out)
        main = module / "src/main/java/com/ejemplo/perf"
        perf_dir = module / "src/perf/kotlin/com/ejemplo/perf"
        hooks = (main / "PerfHooks.kt").read_text(encoding="utf-8")
        self.assertIn("var mark: (String) -> Unit", hooks)
        self.assertNotIn("okHttp", hooks)  # con Hilt la red va por el multibinding
        self.assertNotIn("hb-perf:", hooks)
        self.assertIn("@Multibinds", (main / "PerfHooksModule.kt").read_text(encoding="utf-8"))
        self.assertIn("@IntoSet", (perf_dir / "PerfNetworkModule.kt").read_text(encoding="utf-8"))
        installer = (perf_dir / "PerfInstaller.kt").read_text(encoding="utf-8")
        self.assertIn("PerfHooks.mark = MarkTrace::mark", installer)
        self.assertNotIn("PerfHooks.okHttp", installer)
        self.assertIn('"MARK $name"', (perf_dir / "MarkTrace.kt").read_text(encoding="utf-8"))
        manifest = (module / "src/profiling/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('<profileable android:shell="true" />', manifest)
        self.assertIn('android:name="com.ejemplo.perf.PerfInstaller"', manifest)
        self.assertNotIn("profileable", (module / "src/debug/AndroidManifest.xml").read_text(encoding="utf-8"))
        self.assertIn("@PerfEventListeners factories", out)  # fragmento de red para Hilt
        self.assertIn("PerfHooks.mark(", out)
        self.assertNotIn("{{", out)
        # actualizar: pisa lo generado, respeta lo del proyecto y los manifests existentes
        own = main / "PerfHooks.kt"
        own.write_text("package com.ejemplo.perf\nobject PerfHooks\n", encoding="utf-8")
        (perf_dir / "MarkTrace.kt").write_text((perf_dir / "MarkTrace.kt").read_text(encoding="utf-8") + "// viejo\n",
                                               encoding="utf-8")
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments", "--actualizar")
        self.assertIn("~ actualizado", out)
        self.assertNotIn("// viejo", (perf_dir / "MarkTrace.kt").read_text(encoding="utf-8"))
        self.assertEqual(own.read_text(encoding="utf-8"), "package com.ejemplo.perf\nobject PerfHooks\n")
        self.assertIn("no lo generó la skill", out)

    def test_sin_hilt_la_red_pasa_por_perfhooks(self):
        module = self.dir / "app"
        write(module / "build.gradle.kts", "dependencies { implementation(libs.okhttp); implementation(libs.koin) }")
        write(module / "src/debug/AndroidManifest.xml", "<manifest/>")
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments")
        hooks = (module / "src/main/kotlin/com/ejemplo/perf/PerfHooks.kt").read_text(encoding="utf-8")
        self.assertIn("var okHttp: (OkHttpClient.Builder) -> Unit", hooks)
        self.assertIn("import okhttp3.OkHttpClient", hooks)
        self.assertFalse((module / "src/main/kotlin/com/ejemplo/perf/PerfHooksModule.kt").exists())
        self.assertIn("PerfHooks.okHttp = {", (module / "src/perf/kotlin/com/ejemplo/perf/PerfInstaller.kt").read_text(encoding="utf-8"))
        self.assertIn("PerfHooks.okHttp(builder)", out)
        self.assertIn("Manifest existente", out)
        self.assertEqual((module / "src/debug/AndroidManifest.xml").read_text(encoding="utf-8"), "<manifest/>")

    def test_sin_red_no_copia_lo_de_okhttp_y_valida_el_paquete(self):
        module = self.dir / "app"
        write(module / "build.gradle.kts", "dependencies { implementation(libs.androidx.fragment) }")
        self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf")
        base = module / "src/perf/kotlin/com/ejemplo/perf"
        self.assertFalse((base / "TraceEventListener.kt").exists())
        self.assertFalse((base / "PerfNetworkModule.kt").exists())
        hooks = (module / "src/main/kotlin/com/ejemplo/perf/PerfHooks.kt").read_text(encoding="utf-8")
        self.assertNotIn("okHttp", hooks)
        self.assertNotIn("\n\n\n", hooks)
        self.assertIn("FragmentManager", (base / "ScreenTraceCallbacks.kt").read_text(encoding="utf-8"))
        tracer = (base / "SectionTracer.kt").read_text(encoding="utf-8")
        self.assertNotIn("beginAsyncSection", tracer)
        self.assertNotIn("android.os.Build", tracer)
        self.assertNotIn("hb-perf:red", tracer)
        self.assertNotIn("\n\n\n", tracer)
        self.assertEqual(self.perf("instrumentar", "--modulo", module, "--paquete", "Com.Malo").returncode, 2)
        self.assertEqual(self.perf("instrumentar", "--modulo", self.dir, "--paquete", "com.a.b").returncode, 2)


if __name__ == "__main__":
    unittest.main()


GRADLE_KTS = """
plugins { id("com.android.application") }
android {
    buildTypes {
        release { isMinifyEnabled = true }
        create("benchmark") {
            initWith(getByName("release"))
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
        create("staging") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".staging"
        }
    }
}
dependencies { implementation(libs.okhttp) }
"""
PROFILEABLE = '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application>' \
              '<profileable android:shell="true" /></application></manifest>'


class VariantTest(PerfBase):
    def module(self, gradle=GRADLE_KTS, **manifests):
        module = self.dir / "app"
        write(module / "build.gradle.kts", gradle)
        for name, text in manifests.items():
            write(module / "src" / name / "AndroidManifest.xml", text)
        return module

    def instrument(self, module, *extra):
        return self.perf("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments", *extra)

    def test_lee_los_build_types_de_kotlin_y_groovy_y_si_son_depurables(self):
        kotlin = perf.build_types(GRADLE_KTS)
        self.assertEqual(sorted(kotlin), ["benchmark", "release", "staging"])
        self.assertFalse(perf.is_debuggable("benchmark", kotlin["benchmark"]))
        self.assertTrue(perf.is_debuggable("staging", kotlin["staging"]))  # hereda de debug
        groovy = perf.build_types("""android { buildTypes {
            release { minifyEnabled true; proguardFiles getDefaultProguardFile('x') }
            benchmark { initWith release; debuggable false; matchingFallbacks = ['release'] }
            qa { initWith debug }
            lab { debuggable true }
        } }""")
        self.assertEqual(sorted(groovy), ["benchmark", "lab", "qa", "release"])
        self.assertFalse(perf.is_debuggable("benchmark", groovy["benchmark"]))
        self.assertTrue(perf.is_debuggable("qa", groovy["qa"]))
        self.assertTrue(perf.is_debuggable("lab", groovy["lab"]))
        self.assertEqual(perf.build_types("android { }"), {})

    def test_sin_variante_profileable_crea_profiling_como_antes(self):
        module = self.module()
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments")
        self.assertIn("Variante: profiling (nueva)", out)
        self.assertIn('create("profiling")', out)
        self.assertIn("assembleProfiling", out)
        self.assertTrue((module / "src/profiling/AndroidManifest.xml").is_file())

    def test_reutiliza_la_variante_profileable_y_no_depurable_que_ya_existe(self):
        module = self.module(benchmark=PROFILEABLE)
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments")
        self.assertIn("Variante: benchmark (existente: profileable y no depurable, no se crea otro build type)", out)
        self.assertFalse((module / "src/profiling").exists())
        self.assertEqual((module / "src/benchmark/AndroidManifest.xml").read_text(encoding="utf-8"), PROFILEABLE)
        self.assertIn("= ya existe, no se toca", out)
        self.assertNotIn('create("profiling")', out)
        self.assertNotIn('create("benchmark")', out)
        self.assertIn('getByName("benchmark").kotlin.directories', out)
        self.assertIn('"benchmarkImplementation"', out)
        self.assertIn("installBenchmark", out)
        self.assertIn("assembleBenchmark", out)
        hint = out[out.index("Manifest existente"):]
        self.assertNotIn("<profileable", hint.split("\n\n")[0])  # ya la tiene: solo falta el <provider>
        self.assertTrue((module / "src/perf/kotlin/com/ejemplo/perf/PerfInstaller.kt").is_file())

    def test_una_variante_depurable_o_sin_verificar_no_se_reutiliza(self):
        module = self.module(staging=PROFILEABLE, otra=PROFILEABLE)
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments")
        self.assertIn("Variante: profiling (nueva)", out)
        self.assertIn("staging también declara <profileable> pero es depurable", out)
        self.assertIn("otra también declara <profileable> pero no pude verificar su build type", out)

    def test_una_profileable_con_enabled_false_no_cuenta(self):
        off = PROFILEABLE.replace("<profileable ", '<profileable android:enabled="false" ')
        out = self.ok("instrumentar", "--modulo", self.module(benchmark=off), "--paquete", "com.ejemplo.perf", "--sin-fragments")
        self.assertIn("Variante: profiling (nueva)", out)

    def test_dos_variantes_validas_obligan_a_elegir_con_variante(self):
        gradle = GRADLE_KTS.replace('create("staging") {\n            initWith(getByName("debug"))',
                                    'create("macro") {\n            initWith(getByName("release"))')
        module = self.module(gradle, benchmark=PROFILEABLE, macro=PROFILEABLE)
        result = self.instrument(module)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("2 variantes profileable y no depurables (benchmark, macro)", result.stderr)
        out = self.instrument(module, "--variante", "macro").stdout
        self.assertIn("Variante: macro (existente", out)
        self.assertIn("Variante: profiling (nueva)", self.instrument(module, "--variante", "profiling").stdout)

    def test_la_que_creo_la_skill_gana_si_hay_otra(self):
        gradle = GRADLE_KTS.replace('create("staging") {\n            initWith(getByName("debug"))',
                                    'create("profiling") {\n            initWith(getByName("release"))')
        module = self.module(gradle, benchmark=PROFILEABLE,
                             profiling="<!-- Generated by hb-performance -->" + PROFILEABLE)
        self.assertIn("Variante: profiling (existente", self.instrument(module).stdout)

    def test_variante_con_nombre_invalido_se_rechaza(self):
        result = self.instrument(self.module(), "--variante", "../x")
        self.assertEqual(result.returncode, 2)
        self.assertIn("variante '../x' no válida", result.stderr)

    def test_release_y_debug_nunca_son_candidatas_aunque_declaren_profileable(self):
        module = self.module(release=PROFILEABLE, debug=PROFILEABLE)
        found = perf.find_profileable_variants(module, self.dir, [])
        self.assertEqual([c["nombre"] for c in found], [])
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments")
        self.assertIn("Variante: profiling (nueva)", out)
        self.assertNotIn('getByName("release").kotlin.directories', out)
        self.assertNotIn("Variante: release", out)
        self.assertEqual((module / "src/release/AndroidManifest.xml").read_text(encoding="utf-8"), PROFILEABLE)
        self.assertNotIn("PerfInstaller", (module / "src/release/AndroidManifest.xml").read_text(encoding="utf-8"))

    def test_variante_release_o_debug_se_rechaza_porque_instrumentarian_produccion(self):
        module = self.module(release=PROFILEABLE)
        for name in ("release", "debug", "Release"):
            result = self.instrument(module, "--variante", name)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("variante '%s' no válida" % name, result.stderr)
            self.assertIn("release y debug", result.stderr)
        self.assertFalse((module / "src/perf").exists())

    def test_variante_pedida_sin_build_type_legible_se_trata_como_existente_y_avisa(self):
        module = self.module(otra=PROFILEABLE)
        out = self.instrument(module, "--variante", "otra").stdout
        self.assertIn("Variante: otra (existente: declara <profileable>, sin verificar que no sea depurable", out)
        self.assertIn("⚠ otra declara <profileable> pero no pude verificar su build type", out)
        self.assertIn('getByName("otra").kotlin.directories', out)
        self.assertNotIn('create("otra")', out)
        self.assertNotIn("initWith", out)
        self.assertNotIn("ya es profileable y no depurable", out)
        self.assertFalse((module / "src/profiling").exists())
        self.assertEqual((module / "src/otra/AndroidManifest.xml").read_text(encoding="utf-8"), PROFILEABLE)

    def test_variante_pedida_depurable_se_rechaza(self):
        module = self.module(staging=PROFILEABLE)
        result = self.instrument(module, "--variante", "staging")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("variante 'staging' es depurable", result.stderr)
        self.assertNotIn('create("staging")', result.stdout)
        self.assertFalse((module / "src/perf").exists())

    def test_las_rutas_prohibidas_no_se_leen_al_buscar_la_variante(self):
        module = self.module(benchmark=PROFILEABLE)
        out = self.instrument(module, "--no-leer", "app/src/benchmark/").stdout
        self.assertIn("Variante: profiling (nueva)", out)


TRACKER = """package com.ejemplo.core.analytics

fun interface ScreenTracker {
    fun onScreenVisible(name: String, durationMs: Long = 0)
}
"""
TRACKER_MODULE = """package com.ejemplo.core.analytics

@Module
@InstallIn(SingletonComponent::class)
abstract class AnalyticsModule {
    @Multibinds
    abstract fun screenTrackers(): Set<@JvmSuppressWildcards ScreenTracker>
}
"""
LOCAL_ONLY = """package com.ejemplo.ui

val LocalContentReady = staticCompositionLocalOf<() -> Unit> { {} }
interface ScreenViewModel { fun load() }
"""


class ContentHooksTest(PerfBase):
    def project(self, **files):
        write(self.dir / "app" / "build.gradle.kts", 'plugins { id("com.android.application") }\ndependencies { implementation(libs.hilt.android) }')
        for name, text in files.items():
            write(self.dir / name.replace("__", "/"), text)
        return self.dir / "app"

    def instrument(self, *extra):
        return self.ok("instrumentar", "--modulo", self.dir / "app", "--paquete", "com.ejemplo.perf", "--sin-fragments",
                       "--sin-red", *extra)

    def test_detecta_la_interfaz_con_multibinding_en_otro_modulo_y_arma_el_binding(self):
        self.project(**{"core__src__main__kotlin__ScreenTracker.kt": TRACKER,
                        "core__src__main__kotlin__AnalyticsModule.kt": TRACKER_MODULE,
                        "feature__src__main__kotlin__Otra.kt": "package x\ninterface ScreenViewModel { fun load() }\n"})
        out = self.instrument()
        self.assertIn("el proyecto ya tiene un punto de extensión (1 candidato)", out)
        self.assertIn("interfaz ScreenTracker (core/src/main/kotlin/ScreenTracker.kt:3) · con multibinding", out)
        self.assertIn("fun onScreenVisible(name: String, durationMs: Long = 0)", out)
        self.assertIn("@IntoSet", out)
        self.assertIn("override fun onScreenVisible(name: String, durationMs: Long = 0) { PerfHooks.mark(name) }", out)
        self.assertIn("com.ejemplo.core.analytics.ScreenTracker", out)
        self.assertIn("release queda igual", out)
        self.assertNotIn("{{", out)
        self.assertNotIn("ScreenViewModel", out)

    def test_compositionlocal_sin_multibinding_indica_donde_poner_la_marca(self):
        self.project(**{"app__src__main__kotlin__Locals.kt": LOCAL_ONLY})
        out = self.instrument()
        self.assertIn("CompositionLocal LocalContentReady (app/src/main/kotlin/Locals.kt:3)", out)
        self.assertIn("Sin multibinding que lo reciba", out)
        self.assertNotIn("@IntoSet", out)

    def test_sin_puntos_de_extension_queda_el_fragmento_de_siempre(self):
        self.project(**{"app__src__main__kotlin__Otra.kt": "package x\nclass Home\ninterface Repo { fun all() }\n"})
        out = self.instrument()
        self.assertIn("Contenido visible: reportFullyDrawn en la primera pantalla", out)
        self.assertNotIn("ya tiene un punto de extensión", out)

    def test_respeta_las_rutas_prohibidas_y_no_mira_tests_ni_codigo_generado(self):
        self.project(**{"core__src__main__kotlin__ScreenTracker.kt": TRACKER,
                        "core__src__test__kotlin__ScreenReadyFake.kt": "package t\ninterface ScreenReadyFake { fun a() }\n",
                        "app__src__perf__kotlin__Gen.kt": "// Generated by hb-performance\ninterface ScreenReadyGen { fun a() }\n"})
        self.assertIn("ya tiene un punto de extensión (1 candidato)", self.instrument())
        denied = self.instrument("--no-leer", "core/")
        self.assertNotIn("ya tiene un punto de extensión", denied)
        self.assertNotIn("ScreenTracker", denied)

    def test_interfaz_marcadora_sin_cuerpo_no_toma_los_metodos_de_la_siguiente(self):
        scan = perf.scan_sources  # sin multibinding ni métodos: no inventa una firma
        write(self.dir / "m" / "A.kt", "package a\ninterface ScreenReady\nclass Otra { fun load() {} }\n")
        hooks = scan(self.dir, [])["ganchos"]
        self.assertEqual([(h["nombre"], h["metodos"], h["multibinding"]) for h in hooks], [("ScreenReady", [], False)])


class MultiModuleTest(PerfBase):
    def project(self, **files):
        write(self.dir / "settings.gradle.kts", 'include(":app", ":core", ":feature:home")')
        write(self.dir / "app" / "build.gradle.kts", 'plugins { id("com.android.application") }\ndependencies { implementation(libs.okhttp) }')
        write(self.dir / "core" / "build.gradle.kts", 'plugins { alias(libs.plugins.android.library) }')
        write(self.dir / "feature" / "home" / "build.gradle.kts", 'plugins { id("com.android.library") }')
        for name, text in files.items():
            write(self.dir / name.replace("__", "/"), text)

    def instrument(self, *extra):
        return self.perf("instrumentar", "--modulo", self.dir / "app", "--paquete", "com.ejemplo.perf", "--sin-fragments",
                         "--sin-hilt", *extra)

    def test_lista_los_modulos_y_dice_donde_va_la_instrumentacion(self):
        self.project()
        modules = perf.list_modules(self.dir, [])
        self.assertEqual(modules, [("app", "aplicación"), ("core", "librería"), ("feature/home", "librería")])
        out = self.instrument().stdout
        self.assertIn("Módulos: app (aplicación) · core (librería) · feature/home (librería)", out)
        self.assertIn("La instrumentación va en el módulo app", out)

    def test_un_proyecto_de_un_modulo_no_agrega_nada(self):
        write(self.dir / "app" / "build.gradle.kts", 'plugins { id("com.android.application") }')
        out = self.instrument().stdout
        self.assertNotIn("Módulos:", out)
        self.assertNotIn("módulos library", out)

    def test_sin_punto_de_extension_ofrece_el_puente_por_interfaz_para_las_librerias(self):
        self.project()
        out = self.instrument().stdout
        self.assertIn("Pantallas en módulos library", out)
        self.assertIn("object ContentVisible", out)
        self.assertIn("ContentVisible.onVisible = { PerfHooks.mark(it) }", out)
        self.assertIn("import com.ejemplo.perf.PerfHooks", out)

    def test_con_punto_de_extension_no_ofrece_el_puente(self):
        self.project(**{"core__src__main__kotlin__T.kt": TRACKER, "core__src__main__kotlin__M.kt": TRACKER_MODULE})
        out = self.instrument().stdout
        self.assertIn("ya tiene un punto de extensión", out)
        self.assertNotIn("object ContentVisible", out)

    def test_avisa_si_el_cliente_okhttp_se_arma_en_una_libreria(self):
        self.project(**{"core__src__main__kotlin__Net.kt": "package n\nval c = OkHttpClient.Builder().build()\n"})
        out = self.instrument().stdout
        self.assertIn("OkHttpClient se arma fuera del módulo app (core/src/main/kotlin/Net.kt:2)", out)
        self.project(**{"app__src__main__kotlin__Net.kt": "package n\nval c = OkHttpClient.Builder().build()\n"})
        write(self.dir / "core" / "src" / "main" / "kotlin" / "Net.kt", "package n\n")
        self.assertNotIn("se arma fuera", self.instrument().stdout)

    def test_recetas_de_views_y_rxjava_solo_si_el_proyecto_las_usa(self):
        self.project(**{"feature__home__src__main__kotlin__Web.kt": "import android.webkit.WebView\nclass W : WebView()\n",
                        "feature__home__src__main__kotlin__List.kt": "import io.reactivex.rxjava3.core.Single\nclass L(val r: RecyclerView)\n"})
        out = self.instrument().stdout
        self.assertIn("Pantallas con Views y RxJava (WebView, RecyclerView, RxJava en el proyecto)", out)
        self.assertIn("postVisualStateCallback", out)
        self.assertIn("doOnPreDraw", out)
        self.project()
        self.assertNotIn("Pantallas con Views", self.perf("instrumentar", "--modulo", self.dir / "app", "--paquete",
                                                           "com.ejemplo.perf", "--sin-fragments", "--sin-hilt",
                                                           "--no-leer", "feature/").stdout)


AJENOS = ('"tipo","nombre","llamada","hilos","cpu_ms"\n'
          '"hilo","ktor-nio-1","",1,100\n"hilo","ktor-nio-2","",1,50.5\n"hilo","pool-1","",1,30\n'
          '"red","ktor-nio-1","HTTP GET items/{id} #ab12",1,40\n"red","ktor-nio-2","HTTP GET items/{id}",1,10\n')
GROUPS = [{"nombre": "servidor", "patron": "^ktor-"}]


class ForeignThreadsTest(DeviceBase):
    def read_csv_at(self, path):
        with Path(path).open(newline="", encoding="utf-8") as f:
            return {(r["fase"], r["metrica"], r["corrida"]): r for r in csv.DictReader(f)}

    def sets(self, text=AJENOS):
        lines = [[c.strip('"') for c in line.split(",")] for line in text.strip().splitlines()]
        return [(lines[0], lines[1:])]

    def test_clasifica_los_hilos_por_regex_y_separa_la_cpu_de_la_app(self):
        metrics = {m[0]: m for m in perf.foreign_thread_metrics(self.sets(), GROUPS)}
        self.assertEqual(metrics["hilos_servidor_cpu_ms"][1:], (150.5, "ms", "e2e"))
        self.assertEqual(metrics["hilos_servidor_cantidad"][1:], (2, "hilos", "info"))
        self.assertEqual(metrics["hilos_app_cpu_ms"][1:], (30.0, "ms", "app"))
        self.assertEqual(metrics["red GET items/{id} servidor_cpu_ms"][1:], (50.0, "ms", "e2e"))

    def test_sin_filas_emite_ceros_y_la_familia_se_puede_elegir(self):
        metrics = {m[0]: m for m in perf.foreign_thread_metrics(
            [], [{"nombre": "bd", "patron": "room", "familia": "info"}], known={"red GET x bd_cpu_ms"})}
        self.assertEqual(metrics["hilos_bd_cpu_ms"][1:], (0.0, "ms", "info"))
        self.assertEqual(metrics["red GET x bd_cpu_ms"][1], 0.0)
        self.assertEqual(metrics["hilos_app_cpu_ms"][1], 0.0)

    def test_el_primer_grupo_que_calza_se_queda_el_hilo(self):
        groups = [{"nombre": "a", "patron": "ktor"}, {"nombre": "b", "patron": "ktor-nio"}]
        metrics = {m[0]: m[1] for m in perf.foreign_thread_metrics(self.sets(), groups)}
        self.assertEqual((metrics["hilos_a_cpu_ms"], metrics["hilos_b_cpu_ms"]), (150.5, 0.0))

    def test_la_consulta_recibe_la_ventana_y_el_paquete(self):
        sql = (ROOT / "skills/hb-performance/assets/queries/hilos_ajenos.sql").read_text(encoding="utf-8")
        filled = perf.fill_sql(sql, PKG, {"DESDE": 5, "HASTA": 10})
        self.assertNotIn("{{", filled)
        self.assertIn("name = 'com.ejemplo.app'", filled)

    def test_el_plan_valida_los_hilos_ajenos(self):
        for bad, message in (("x", "es una lista"), ([{"nombre": "s"}], "necesita 'nombre'"),
                             ([{"nombre": "s", "patron": "(["}], "no es válida"),
                             ([{"nombre": "s", "patron": "a", "familia": "zzz"}], "familia fuera de"),
                             ([{"nombre": "s", "patron": "a"}, {"nombre": "s", "patron": "b"}], "nombre repetido")):
            plan = json.loads(self.plan.read_text(encoding="utf-8"))
            plan["hilos_ajenos"] = bad
            write(self.plan, json.dumps(plan))
            result = self.perf("capturar", "--plan", self.plan, "--prueba", "--paquete", PKG, "--carpeta", self.dir / "p")
            self.assertEqual(result.returncode, 2, bad)
            self.assertIn(message, result.stderr)

    def test_capturar_agrega_las_metricas_de_hilos_ajenos_solo_si_el_plan_las_declara(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_TP_OTRA"] = AJENOS
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertNotIn("hilos_servidor_cpu_ms", {k[1] for k in self.read_csv_at(self.plan.parent / "metricas.csv")})
        self.assertNotIn("ajenos", (self.dir / "tp.sql").read_text(encoding="utf-8") if (self.dir / "tp.sql").exists() else "")
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["hilos_ajenos"] = GROUPS
        write(self.plan, json.dumps(plan))
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "2")
        data = self.read_csv_at(self.plan.parent / "metricas.csv")
        self.assertEqual(data[("control", "hilos_servidor_cpu_ms", "1")]["valor"], "150.5")
        self.assertEqual(data[("control", "hilos_servidor_cpu_ms", "1")]["familia"], "e2e")
        self.assertEqual(data[("control", "hilos_app_cpu_ms", "2")]["valor"], "30")
        self.assertEqual(data[("control", "red GET items/{id} servidor_cpu_ms", "1")]["valor"], "50")
        sql = (self.dir / "tp.sql").read_text(encoding="utf-8")
        self.assertIn("thread_state", sql)
        self.assertNotIn("{{", sql)
        # la ventana del flujo (si la hay) acota la consulta; sin ventana, toda la traza
        self.assertRegex(sql, r"ts\.ts < 4000000000000000000")

