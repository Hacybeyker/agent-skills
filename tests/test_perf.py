"""Tests de hb-performance (skills/hb-performance/scripts/perf.py): estadística, métricas de traza, red,
captura con un adb y un trace_processor falsos, reporte e instrumentación."""
import contextlib
import csv
import datetime
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import zipfile
from pathlib import Path

from helpers import ROOT, write

SCRIPT = ROOT / "skills" / "hb-performance" / "scripts" / "perf.py"
HEADER = "fase,flujo,metrica,corrida,valor,unidad,sentido,familia\n"
PKG = "com.ejemplo.app"

spec = importlib.util.spec_from_file_location("perf", str(SCRIPT))
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


def inspect_source():
    return SCRIPT.read_text(encoding="utf-8")


def rows(phase, flow, metric, values, unit="ms", sense="menor", family="app"):
    return "".join("%s,%s,%s,%d,%s,%s,%s,%s\n" % (phase, flow, metric, i, v, unit, sense, family)
                   for i, v in enumerate(values, start=1))


def entry(method, url, started, time):
    return {"request": {"method": method, "url": url}, "startedDateTime": started, "time": time}


MS = 1_000_000


def without_new(record):
    """Un registro de fases.json sin los campos opcionales que agrega 0.9.0 (la versión de la skill y la configuración)."""
    return {key: value for key, value in record.items() if key not in ("skill", "configs")}


class PerfBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.csv = self.dir / "metricas.csv"
        self.env = dict(os.environ)

    def tearDown(self):
        self.tmp.cleanup()

    def perf(self, *args, stdin=None, interruptible=False):
        # interruptible: el proceso recibe SIGINT con su manejo por defecto aunque quien corre los tests lo ignore (un
        # trabajo en segundo plano, algunos CI); sin eso, Python no levanta KeyboardInterrupt.
        default_sigint = (lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)) if interruptible else None
        return subprocess.run([sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args], cwd=str(self.dir),
                              env=self.env, input=stdin, capture_output=True, text=True, encoding="utf-8",
                              preexec_fn=default_sigint)

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
    if os.environ.get("FAKE_LISTA"):  # la lista tal cual, para estados que no son "device" (unauthorized, offline)
        print("List of devices attached\n" + os.environ["FAKE_LISTA"])
        sys.exit(0)
    print("List of devices attached\n" + "".join("%s\tdevice\n" % d for d in os.environ.get("FAKE_DEVICES", "emulator-5554").split(",")))
    sys.exit(0)
if os.environ.get("FAKE_DESCONECTA") and os.environ["FAKE_DESCONECTA"] in " ".join(args):
    sys.stderr.write("adb: device 'emulator-5554' not found\n")  # el cable se soltó a mitad del comando
    sys.exit(1)
if args[0] == "pull":
    if os.environ.get("FAKE_PULL_FALLA"):
        sys.stderr.write("adb: error: failed to stat remote object '%s': No such file or directory\n" % args[1])
        sys.exit(1)
    pathlib.Path(args[2]).write_bytes(os.environ["FAKE_PULL"].encode("utf-8") if os.environ.get("FAKE_PULL") else b"x" * 4096)
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
elif cmd.startswith("dumpsys package dexopt"):
    print(os.environ.get("FAKE_DEXOPT", ""))
elif cmd.startswith("dumpsys input_method"):
    print("  mShowRequested=true mShowExplicitlyRequested=false mShowForced=false mInputShown="
          + os.environ.get("FAKE_TECLADO", "false"))
elif cmd.startswith("dumpsys package"):
    print("    versionCode=7 minSdk=26 targetSdk=36\n    versionName=1.0\n    flags=[ HAS_CODE ALLOW_BACKUP ]\n"
          "    lastUpdateTime=" + os.environ.get("FAKE_UPDATED", "2026-11-05 10:00:00"))
elif cmd.startswith("dumpsys thermalservice"):
    print("Thermal Status: " + os.environ.get("FAKE_THERMAL", "0"))
elif cmd.startswith("dumpsys battery"):
    print("  level: 90")
elif cmd.startswith("date '+hora="):
    # la foto de salidas de capturar: hora del dispositivo, pid y exit-info. El reloj avanza un segundo por llamada y
    # el volcado solo sale en la foto de después de cada corrida (llamadas impares)
    counter = os.environ["FAKE_LOG"] + ".salidas"
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    open(counter, "w").write(str(n + 1))
    print("hora=2026-11-05 10:00:%02d" % min(n, 59))
    print("pid=" + ("" if os.environ.get("FAKE_DEAD") else "1234"))
    if os.environ.get("FAKE_EXIT_INFO") and n % 2 == 1:
        print(open(os.environ["FAKE_EXIT_INFO"]).read())
elif cmd.startswith("dumpsys activity exit-info"):
    if os.environ.get("FAKE_EXIT_INFO"):
        print(open(os.environ["FAKE_EXIT_INFO"]).read())
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
    for frame in filter(None, os.environ.get("FAKE_CRASH_FRAMES", "").split("|")):
        print("11-05 10:00:01.000  1234  1234 E AndroidRuntime: " + frame)
elif cmd.startswith("perfetto"):
    config = sys.stdin.read()
    if os.environ.get("FAKE_PERFETTO_CONFIG"):
        pathlib.Path(os.environ["FAKE_PERFETTO_CONFIG"]).write_text(config)
    print("4242")
elif cmd.startswith("[ -d /proc/"):
    # con "echo": ¿sigue Perfetto antes de detenerlo? (sin respuesta por defecto, como un adb que no contesta);
    # sin "echo": la espera después de detenerlo, y aquí el proceso ya terminó
    if "echo" not in cmd:
        sys.exit(1)
    if os.environ.get("FAKE_TRAZA_CORTADA"):
        print("terminada")
elif cmd.startswith("dumpsys meminfo"):
    print("  Java Heap:  2048\n  TOTAL PSS:  51200   TOTAL RSS: 1\n  Views:  10\n  Activities:  1")
elif cmd.startswith("uiautomator dump") and os.environ.get("FAKE_PULL_FALLA"):
    sys.stderr.write("ERROR: could not get idle state.\n")  # uiautomator falla así, con código 0
elif cmd.startswith("settings get system min_refresh_rate"):
    print(os.environ.get("FAKE_MIN_HZ", "null"))
elif cmd.startswith("settings get system peak_refresh_rate"):
    print(os.environ.get("FAKE_PEAK_HZ", "null"))
elif cmd.startswith('echo "q='):
    emulator = os.environ.get("FAKE_EMULATOR")
    print("q=%s\nb=\nh=%s\nm=%s\nc=\ng=%s" % ("1" if emulator else "", "ranchu" if emulator else "qcom",
          "sdk_gphone64_arm64" if emulator else "Pixel Test", os.environ.get("FAKE_GLES", "")))
'''

FAKE_TP = r'''#!{python}
import json, os, re, sys
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
if os.environ.get("FAKE_TP_FALLA") in names:
    sys.stderr.write("no such column: blocked_function\n")
    sys.exit(1)
if not names:
    sys.stdout.write(out)
else:
    chunks = []
    for name in names:
        chunks.append('"hbperf_marker"\n"%s"\n' % name)
        own = json.loads(os.environ.get("FAKE_TP_POR_CONSULTA", "{{}}"))
        chunks.append(out if name == "metricas" else own[name] if name in own
                      else os.environ.get("FAKE_TP_OTRA", '"nombre","valor"\n"x",1\n'))
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
        results = self.verdicts(("baja", "emulador (render: Translator)"))
        self.assertEqual(results["jank_app_pct"]["veredicto"], "mejora")
        self.assertTrue(any(a.startswith("frames orientativos") for a in results["jank_app_pct"]["avisos"]))

    def test_trust_lee_el_peor_entorno_de_las_fases(self):
        self.assertEqual(perf.frames_trust(self.dir), ("ok", ""))
        write(self.dir / "fases.json", json.dumps({
            "antes": {"entorno": {"emulador": True, "software": False, "frames": "baja"}},
            "despues": {"entorno": {"emulador": True, "software": True, "frames": "no"}}}))
        self.assertEqual(perf.frames_trust(self.dir), ("no", "emulador, render por software"))

    def test_el_motivo_de_la_confianza_baja_dice_el_render_y_no_que_falta_la_gpu(self):
        host = {"emulador": True, "software": False, "render": "Android Emulator OpenGL ES Translator (Apple M2 Pro)",
                "frames": "baja"}
        write(self.dir / "fases.json", json.dumps({"antes": {"entorno": host}}))
        level, motive = perf.frames_trust(self.dir)
        self.assertEqual(level, "baja")
        self.assertEqual(motive, "emulador (render: Android Emulator OpenGL ES Translator (Apple M2 Pro))")
        self.assertNotIn("sin GPU del host", motive)
        write(self.dir / "fases.json", json.dumps({"antes": {"entorno": dict(host, render="")}}))
        self.assertEqual(perf.frames_trust(self.dir), ("baja", "emulador (render: sin dato)"))

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

    def test_otra_tanda_de_la_misma_fase_con_gpu_del_host_conserva_el_nivel_no_confiable(self):
        self.tp_outputs(GOOD)
        self.env.update({"FAKE_EMULATOR": "1", "FAKE_GLES": GLES_SOFT})
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        self.env["FAKE_GLES"] = GLES_HOST  # se relanzó el emulador con -gpu host
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["corridas"], 2)
        self.assertEqual(phases["antes"]["entorno"]["frames"], "no")
        self.assertTrue(phases["antes"]["entorno"]["software"])
        self.assertEqual(perf.frames_trust(self.plan.parent), ("no", "emulador, render por software"))

    def test_write_phase_conserva_el_peor_entorno_de_la_fase(self):
        soft = {"emulador": True, "software": True, "render": "SwiftShader", "frames": "no"}
        host = {"emulador": True, "software": False, "render": "Apple M2", "frames": "baja"}
        for first, second, expected in ((soft, host, "no"), (host, soft, "no"), (host, None, "baja"), (None, host, "baja"),
                                        (soft, None, "no")):
            folder = self.dir / ("fase-%s-%s" % (first and first["frames"], second and second["frames"]))
            folder.mkdir()
            for env in (first, second):
                perf.write_phase(folder, "antes", dict({"fecha": "2026-11-09T10:00:00", "corridas": 1}, **({"entorno": env} if env else {})))
            self.assertEqual(perf.read_phases(folder)["antes"]["corridas"], 2)
            self.assertEqual(perf.frames_trust(folder)[0], expected, (first, second))
        folder = self.dir / "fase-real"
        folder.mkdir()
        perf.write_phase(folder, "antes", {"fecha": "2026-11-09T10:00:00", "corridas": 1})
        perf.write_phase(folder, "antes", {"fecha": "2026-11-09T11:00:00", "corridas": 1})
        self.assertNotIn("entorno", perf.read_phases(folder)["antes"])

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
        # detienen la captura con el motivo, sin gastar los 15 intentos.
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

    def test_el_tope_de_intentos_crece_con_las_corridas_pedidas(self):
        self.assertEqual([perf.max_attempts(n) for n in (1, 5, 6, 10, 20)], [4, 8, 9, 15, 30])

    def test_invalidas_sueltas_no_cortan_una_captura_de_diez_corridas(self):
        # cuatro inválidas sin dos seguidas: el tope viejo (corridas + 3 = 13) las cortaba con 9 válidas
        self.tp_outputs(GOOD, LOGIN, GOOD, LOGIN, GOOD, LOGIN, GOOD, LOGIN, GOOD, GOOD, GOOD, GOOD, GOOD, GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "10",
                      "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(out.count("✖ corrida"), 4)
        self.assertIn("corrida 10/10", out)

    def test_con_pocas_corridas_el_tope_sigue_siendo_tres_intentos_de_mas(self):
        self.tp_outputs(LOGIN, GOOD, LOGIN, GOOD, LOGIN, GOOD, LOGIN)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "4",
                           "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("solo 3 de 4 corridas válidas en 7 intentos", result.stderr)

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
        self.assertIn("· Solo si lo que quieres medir es el arranque en frío (receta, sin sesión 1) · Terminal (sin chat):", out)
        self.assertIn("nuevo --receta arranque-frio --paquete %s --serial emulator-5554 --carpeta reports/perf/arranque-frio/" % PKG, out)
        self.assertIn('--instalar "./gradlew app:installProfiling"', out)
        self.assertIn("· Una pantalla o un flujo · Chat nuevo · Modelo: Sonnet 5.5 · Esfuerzo: medio", out)
        self.assertIn("Dispositivo emulator-5554", out)
        self.assertLess(out.index("Una pantalla o un flujo"), out.index("arranque en frío (receta"))  # el flujo, primero
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
        self.assertEqual(plan["modelos"], {"economico": "Haiku 5.5", "intermedio": "Sonnet 5.5", "diagnostico": "Sonnet 5.5", "alto": "Opus 5.5"})

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


class RecorridoSinTestigoTest(DeviceBase):
    """Maestro y testigo solo llevan la app al punto de partida (`preparar`): nunca son el recorrido medido."""

    def test_estado_md_no_ofrece_testigo_como_recorrido(self):
        folder = self.dir / "r"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "x")
        modes = next(l for l in (folder / "estado.md").read_text(encoding="utf-8").splitlines() if l.startswith("| Modos"))
        self.assertIn("recorrido manual, comando o arranque-frio", modes)
        self.assertNotIn("testigo", modes)

    def test_la_ayuda_de_recorrido_no_menciona_testigo(self):
        out = self.ok("capturar", "--help")
        recorrido = out[out.index("\n  --recorrido"):out.index("\n  --preparar")]
        self.assertNotIn("testigo", recorrido.lower())
        self.assertIn("adb", recorrido)


class ModelLevelsTest(unittest.TestCase):
    """Los nombres de modelo salen de model_name y las referencias hablan de niveles."""

    def text(self, *parts):
        return (ROOT.joinpath("skills", "hb-performance", *parts)).read_text(encoding="utf-8")

    def test_ningun_texto_del_script_fija_un_modelo_fuera_de_model_name(self):
        import inspect
        self.assertEqual(inspect.getsource(perf).count("MODELOS["), 1)  # el de model_name
        self.assertNotIn("MODELOS[", inspect.getsource(perf.cmd_humo))
        self.assertIn("model_name(", inspect.getsource(perf.cmd_humo))

    def test_la_plantilla_del_plan_trae_los_mismos_modelos_que_el_script(self):
        template = json.loads(self.text("assets", "plantillas", "plan.json"))
        self.assertEqual(template["modelos"], perf.MODELOS)

    def test_prompts_habla_de_niveles_y_no_de_nombres_fijos_de_modelo(self):
        prompts = self.text("references", "prompts.md")
        intro, cases = prompts.split("## Empezar", 1)
        self.assertIn("`modelos`", intro)
        for level in ("económico", "intermedio", "diagnóstico", "alto"):
            self.assertIn(level, intro)
        where = [line for line in cases.splitlines() if line.startswith("**Dónde:**")]
        self.assertGreater(len(where), 15)
        for line in where:  # dónde va cada caso: un nivel, nunca un nombre de modelo
            self.assertNotRegex(line, r"(Haiku|Sonnet|Opus) \d", line)
        for level in ("Intermedio · medio", "Económico · bajo", "Diagnóstico · alto"):
            self.assertIn("**Dónde:** chat nuevo · " + level, where)

    def test_cada_prompt_va_solo_en_su_bloque_y_la_descripcion_queda_afuera(self):
        cases = self.text("references", "prompts.md").split("## Empezar", 1)[1].split("## Reglas que te ahorran dinero")[0]
        repo = (ROOT / "PROMPTS.md").read_text(encoding="utf-8")
        repo = repo[repo.index("## hb-performance"):repo.index("## hb-coach")]
        for text in (cases, repo):
            blocks = re.findall(r"```\w*\n(.*?)```", text, re.S)
            self.assertTrue(blocks)
            for body in blocks:
                self.assertEqual(len(body.strip().splitlines()), 1, body)  # solo el texto para pegar
                self.assertNotIn("→", body)
            outside = re.sub(r"```.*?```", "", text, flags=re.S)
            self.assertNotIn("Usa hb-performance", outside)  # ningún prompt mezclado con su explicación
            self.assertNotIn("Sigue hb-performance con", outside)
            self.assertNotIn("| Caso |", outside)
        for case in cases.split("\n### ")[1:]:
            self.assertLessEqual(case.count("```"), 2, case[:60])  # un bloque por caso, como mucho
            self.assertIn("\n**Dónde:** ", case, case[:60])
        self.assertIn("El mismo texto sirve para empezar", self.text("references", "prompts.md"))
        self.assertIn("claude --resume", cases)
        self.assertIn("copilot --resume", cases)
        self.assertNotIn("/cost>", inspect_source())

    def test_modelos_y_ficha_describen_el_nivel_diagnostico(self):
        models = self.text("references", "modelos.md")
        self.assertIn("`diagnostico`", models)
        self.assertRegex(models, r"\| 2 · Diagnóstico \| Diagnóstico \(por defecto el intermedio\)")
        self.assertIn("sin `diagnostico`", models)
        self.assertIn("`diagnostico`", self.text("references", "ficha.md"))
        self.assertNotRegex(models, r"Sonnet 5(?!\.5)")


class NoLeerTest(DeviceBase):
    def test_une_flags_plan_y_agents_md_sin_duplicados(self):
        write(self.dir / "AGENTS.md", "# P\n\n## Performance\n\n- **No leer:** docs/ALCANCE-*, `secretos/`; ~/otro/proyecto\n"
              "- Otra línea: x\n")
        found = perf.read_no_leer(self.dir, plan={"no_leer": ["docs/ALCANCE-*", "tmp/"]}, extra=["casos/"])
        self.assertEqual(found, ["casos/", "docs/ALCANCE-*", "tmp/", "secretos/", "~/otro/proyecto"])

    def read_agents(self, text):
        write(self.dir / "AGENTS.md", text)
        return perf.read_no_leer(self.dir)

    def test_la_lista_en_las_lineas_siguientes_se_lee_como_viñetas(self):
        self.assertEqual(self.read_agents("## Performance\n\nNo leer:\n- docs/ALCANCE-*\n- `casos/`\n* secretos/, tmp/\n\n- Otra: x\n"),
                         ["docs/ALCANCE-*", "casos/", "secretos/", "tmp/"])
        self.assertEqual(self.read_agents("## Performance\n- **No leer:**\n  - docs/ALCANCE-*\n  - `casos/`\n- Otra línea: x\n"),
                         ["docs/ALCANCE-*", "casos/"])
        self.assertEqual(self.read_agents("**No leer:**\n- casos/\n"), ["casos/"])

    def test_no_leer_sin_lista_no_se_come_la_linea_siguiente(self):
        self.assertEqual(self.read_agents("No leer:\nTexto normal sin viñeta\n"), [])
        self.assertEqual(self.read_agents("- No leer:\n- Otra línea: x\n"), [])
        self.assertEqual(self.read_agents("No leer:\n\n- Otra: x\n"), [])
        self.assertEqual(self.read_agents("No leer: casos/\n- Otra: x\nTexto\n"), ["casos/"])
        self.assertEqual(self.read_agents("**No leer**: casos/, `tmp/`\n"), ["casos/", "tmp/"])

    def test_los_patrones_se_comparan_desde_la_raiz_del_proyecto(self):
        denied = lambda pattern, rel: perf.is_denied(self.dir / rel, self.dir, [pattern])  # noqa: E731
        self.assertFalse(denied("ALCANCE-*", "docs/ALCANCE-x.md"))  # sin carpeta solo cubre la raíz
        self.assertTrue(denied("ALCANCE-*", "ALCANCE-x.md"))
        self.assertTrue(denied("docs/ALCANCE-*", "docs/ALCANCE-x.md"))
        self.assertTrue(denied("**/ALCANCE-*", "docs/ALCANCE-x.md"))
        self.assertTrue(denied("**/ALCANCE-*", "ALCANCE-x.md"))

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
        self.assertEqual((steps[4]["modelo"], steps[4]["esfuerzo"]), ("Sonnet 5.5", "alto"))
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

    def test_el_diagnostico_es_un_nivel_propio_y_por_defecto_igual_al_intermedio(self):
        self.assertEqual(perf.MODELOS, {"economico": "Haiku 5.5", "intermedio": "Sonnet 5.5", "diagnostico": "Sonnet 5.5",
                                        "alto": "Opus 5.5"})
        write(self.folder / "diagnostico.md", "x")
        title, steps = self.step()
        self.assertEqual(title, "sesión 2 · diagnóstico")
        self.assertEqual((steps[0]["modelo"], steps[0]["esfuerzo"]), ("Sonnet 5.5", "alto"))

    def test_un_plan_anterior_sin_diagnostico_usa_su_intermedio(self):
        write(self.folder / "diagnostico.md", "x")
        self.plan["modelos"] = {"economico": "Haiku 5.5", "intermedio": "Sonnet 5", "alto": "Opus 5.5"}
        self.save()
        self.assertEqual(perf.load_plan(self.folder / "plan.json")["modelos"]["intermedio"], "Sonnet 5")  # sigue siendo válido
        chat = self.step()[1][0]
        self.assertEqual((chat["modelo"], chat["esfuerzo"]), ("Sonnet 5", "alto"))
        out = self.ok("siguiente", "--carpeta", self.folder)  # el comando real lee el plan.json viejo sin quejarse
        self.assertIn("Chat nuevo · Modelo: Sonnet 5 · Esfuerzo: alto", out)
        self.plan["modelos"] = {"economico": "GPT-5 mini"}  # ni intermedio ni diagnostico: los de fábrica
        self.assertEqual(self.step()[1][0]["modelo"], "Sonnet 5.5")

    def test_cambiar_el_diagnostico_no_toca_la_sesion_3_y_cambiar_el_intermedio_no_toca_el_diagnostico(self):
        write(self.folder / "diagnostico.md", "x")
        self.plan["modelos"] = {"intermedio": "Haiku 5.5", "diagnostico": "Opus 5.5"}
        self.assertEqual(self.step()[1][0]["modelo"], "Opus 5.5")  # sesión 2
        self.plan["mejoras"] = [{"id": "M1", "titulo": "x", "estado": "aprobada"}]
        title, steps = self.step()
        self.assertEqual((title, steps[0]["modelo"]), ("sesión 3 · M1", "Haiku 5.5"))  # sesión 3

    def test_modelos_tiene_que_ser_un_objeto_y_el_mensaje_nombra_el_diagnostico(self):
        self.plan["modelos"] = "Sonnet"
        self.save()
        result = self.perf("siguiente", "--carpeta", self.folder)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("'modelos' es un objeto con economico, intermedio, alto y, si quieres, diagnostico", result.stderr)

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
        self.assertEqual(len(steps), 1)  # sin mejoras propuestas no hay nada que pasar a riguroso
        self.plan["profundidad"] = "riguroso"
        self.assertEqual(self.step()[0], "sesión 4 · cierre sin mejoras")  # sin mejoras, la sesión 2 no se repite
        self.plan["mejoras"] = [{"id": "M1", "titulo": "a"}]
        # con mejoras ya no cierra; y antes de decidir, riguroso pide la línea base completa y el control
        self.assertEqual(self.step()[0], "completar la línea base de riguroso (sin chat)")
        self.plan["mejoras"] = []
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
        self.assertIn("**Chat nuevo** · Modelo: Sonnet 5.5 · Esfuerzo: alto", state)
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
        # actualizar: pisa lo que generó una versión anterior de la skill (su huella coincide), respeta lo del proyecto
        # y los manifests existentes
        own = main / "PerfHooks.kt"
        own.write_text("package com.ejemplo.perf\nobject PerfHooks\n", encoding="utf-8")
        old = (perf_dir / "MarkTrace.kt").read_text(encoding="utf-8") + "// viejo\n"
        (perf_dir / "MarkTrace.kt").write_text(perf.stamp(old), encoding="utf-8")
        out = self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments", "--actualizar")
        self.assertIn("~ actualizado: %s" % (perf_dir / "MarkTrace.kt"), out)
        self.assertNotIn("// viejo", (perf_dir / "MarkTrace.kt").read_text(encoding="utf-8"))
        self.assertEqual(own.read_text(encoding="utf-8"), "package com.ejemplo.perf\nobject PerfHooks\n")
        self.assertIn("no lo generó la skill", out)
        self.assertIn("= al día: %s" % (perf_dir / "SectionTracer.kt"), out)  # lo que no cambió no se reescribe
        self.assertNotIn("no se actualiza", out)

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
        self.assertIn("fun onScreenVisible(name: String, durationMs: Long)", out)
        self.assertIn("@IntoSet", out)
        self.assertIn("override fun onScreenVisible(name: String, durationMs: Long) { PerfHooks.mark(name) }", out)
        self.assertNotIn("= 0", out)  # un override no puede repetir el valor por defecto
        self.assertIn("com.ejemplo.core.analytics.ScreenTracker", out)
        self.assertIn("release queda igual", out)
        self.assertNotIn("{{", out)
        self.assertNotIn("ScreenViewModel", out)

    def test_el_override_lleva_el_tipo_de_retorno_suspend_y_parametros_de_tipo_funcion(self):
        contract = ("package com.ejemplo.core\n\ninterface ContentReady {\n"
                    "    suspend fun onReady(screen: String, done: (Int) -> Unit, tags: Map<String, Int> = emptyMap(),\n"
                    "                        later: () -> Unit = { }): Boolean\n"
                    "    fun withBody(): Int = 1\n    fun other() { }\n}\n")
        module = "package com.ejemplo.core\n@Module\nabstract class M { @Multibinds abstract fun a(): Set<ContentReady> }\n"
        self.project(**{"core__src__main__kotlin__ContentReady.kt": contract, "core__src__main__kotlin__M.kt": module})
        out = self.instrument()
        signature = "screen: String, done: (Int) -> Unit, tags: Map<String, Int>, later: () -> Unit"
        self.assertIn("suspend fun onReady(%s): Boolean" % signature, out)
        self.assertIn("override suspend fun onReady(%s): Boolean { PerfHooks.mark(screen); TODO(" % signature, out)
        self.assertNotIn("emptyMap", out)
        self.assertNotIn("= { }", out)
        self.assertIn("(más los tipos de los parámetros)", out)
        self.assertNotIn("withBody", out)

    def test_lee_las_firmas_con_parentesis_anidados_y_sin_cuerpo(self):
        text = ("interface Gancho {\n    fun a(x: String, f: (Int, String) -> Unit)\n    fun b(): Boolean\n"
                "    fun c() = Unit\n    fun d(y: Int = 3) {}\n    suspend fun e(z: List<Pair<A, B>>,)\n}\n")
        methods = perf.hook_methods(text, perf.INTERFACE_DECL.search(text))
        self.assertEqual([(m[0], m[1], m[2]) for m in methods],
                         [("a", "x: String, f: (Int, String) -> Unit", ""), ("b", "", "Boolean"),
                          ("e", "z: List<Pair<A, B>>", "")])
        self.assertEqual([m[3] for m in methods], [False, False, True])

    def test_una_interfaz_java_con_multibinding_no_dice_que_no_hay_multibinding(self):
        self.project(**{"core__src__main__java__ScreenReady.java": "package a;\npublic interface ScreenReady {\n void onReady(String name);\n}\n",
                        "core__src__main__kotlin__M.kt": "package a\n@Module\nabstract class M { @Multibinds abstract fun a(): Set<ScreenReady> }\n"})
        out = self.instrument()
        self.assertIn("interfaz ScreenReady (core/src/main/java/ScreenReady.java:2) · con multibinding", out)
        self.assertNotIn("Sin multibinding que lo reciba", out)
        self.assertIn("ScreenReady tiene un multibinding pero no pude leer sus métodos", out)
        self.assertIn("@IntoSet", out)
        self.assertIn("PerfHooks.mark(<nombre>)", out)

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


AJENOS = ('"tipo","nombre","llamada","id","hilos","cpu_ms"\n'
          '"hilo","ktor-nio-1","","",1,100\n"hilo","ktor-nio-2","","",1,50.5\n"hilo","pool-1","","",1,30\n'
          '"red","ktor-nio-1","HTTP GET items/{id} #ab12",7,1,40\n"red","ktor-nio-2","HTTP GET items/{id} #ab12",7,1,10\n'
          '"llamada","","HTTP GET items/{id} #ab12",7,0,0\n"llamada","","HTTP GET items/{id}",8,0,0\n')
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
        # la llamada 7 usó 40 + 10 ms del grupo y la 8 nada: la mediana por llamada es 25 (el total de la corrida sería 50)
        self.assertEqual(metrics["red GET items/{id} servidor_cpu_ms"][1:], (25.0, "ms", "e2e"))

    def test_la_cpu_de_red_es_la_mediana_por_llamada_y_no_el_total_del_endpoint(self):
        rows = ['"tipo","nombre","llamada","id","hilos","cpu_ms"']
        for call, cpu in ((1, 10), (2, 20), (3, 90)):
            rows.append('"red","ktor-nio-1","HTTP GET lista",%d,1,%d' % (call, cpu))
            rows.append('"llamada","","HTTP GET lista",%d,0,0' % call)
        rows.append('"llamada","","HTTP GET lista",4,0,0')  # una llamada sin CPU del grupo cuenta como 0
        rows.append('"llamada","","HTTP POST otra",5,0,0')
        metrics = {m[0]: m for m in perf.foreign_thread_metrics(self.sets("\n".join(rows)), GROUPS)}
        self.assertEqual(metrics["red GET lista servidor_cpu_ms"][1:], (15.0, "ms", "e2e"))  # mediana de 10, 20, 90, 0
        self.assertEqual(metrics["red POST otra servidor_cpu_ms"][1], 0.0)

    def test_sin_filas_emite_ceros_y_la_familia_se_puede_elegir(self):
        metrics = {m[0]: m for m in perf.foreign_thread_metrics(
            [], [{"nombre": "bd", "patron": "room", "familia": "info"}], known={"red GET x bd_cpu_ms"})}
        self.assertEqual(metrics["hilos_bd_cpu_ms"][1:], (0.0, "ms", "info"))
        self.assertEqual(metrics["red GET x bd_cpu_ms"][1], 0.0)
        self.assertEqual(metrics["hilos_app_cpu_ms"][1], 0.0)

    def test_la_consulta_agrupa_por_llamada_y_lista_las_llamadas_sin_cpu(self):
        import sqlite3
        db = sqlite3.connect(":memory:")
        db.executescript("""
            CREATE TABLE process (upid INT, pid INT, name TEXT, start_ts INT);
            CREATE TABLE thread (utid INT, upid INT, tid INT, name TEXT);
            CREATE TABLE thread_state (utid INT, ts INT, dur INT, state TEXT);
            CREATE TABLE trace_bounds (start_ts INT);
            CREATE TABLE slice (id INT, name TEXT, ts INT, dur INT);
            INSERT INTO process VALUES (1, 100, 'com.ejemplo.app', 0);
            INSERT INTO trace_bounds VALUES (0);
            INSERT INTO thread VALUES (1, 1, 100, 'main'), (2, 1, 101, 'ktor-nio-1'), (3, 1, 102, 'pool-1');
            INSERT INTO thread_state VALUES (1, 0, 900000000, 'Running'),
                (2, 20000000, 30000000, 'Running'), (2, 210000000, 10000000, 'Running'), (2, 500000000, 5000000, 'Running'),
                (3, 420000000, 10000000, 'Running');
            INSERT INTO slice VALUES (10, 'HTTP GET a', 0, 100000000), (11, 'HTTP GET a', 200000000, 100000000),
                (12, 'HTTP GET b', 400000000, 50000000), (13, 'HTTP GET a', 600000000, 0);
        """)
        sql = perf.fill_sql((ROOT / "skills/hb-performance/assets/queries/hilos_ajenos.sql").read_text(encoding="utf-8"),
                            PKG, {"DESDE": 0, "HASTA": 10 ** 10})
        cursor = db.execute(sql)
        header = [d[0] for d in cursor.description]
        rows = [dict(zip(header, r)) for r in cursor.fetchall()]
        self.assertEqual(header, ["tipo", "nombre", "llamada", "id", "hilos", "cpu_ms"])
        by_kind = lambda kind: sorted((r["nombre"], r["id"], r["cpu_ms"]) for r in rows if r["tipo"] == kind)  # noqa: E731
        self.assertEqual(by_kind("hilo"), [("ktor-nio-1", 0, 45.0), ("pool-1", 0, 10.0)])
        self.assertEqual(by_kind("red"), [("ktor-nio-1", 10, 30.0), ("ktor-nio-1", 11, 10.0), ("pool-1", 12, 10.0)])
        self.assertEqual(sorted(r["id"] for r in rows if r["tipo"] == "llamada"), [10, 11, 12])  # la de dur 0 no cuenta
        metrics = {m[0]: m[1] for m in perf.foreign_thread_metrics([(header, [[str(v) for v in r.values()] for r in rows])], GROUPS)}
        self.assertEqual(metrics["red GET a servidor_cpu_ms"], 20.0)  # mediana de 30 y 10, no su suma (40)
        self.assertEqual(metrics["red GET b servidor_cpu_ms"], 0.0)

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
        self.assertEqual(data[("control", "red GET items/{id} servidor_cpu_ms", "1")]["valor"], "25")
        sql = (self.dir / "tp.sql").read_text(encoding="utf-8")
        self.assertIn("thread_state", sql)
        self.assertNotIn("{{", sql)
        # la ventana del flujo (si la hay) acota la consulta; sin ventana, toda la traza
        self.assertRegex(sql, r"ts\.ts < 4000000000000000000")



class SegmentsTest(PerfBase):
    """Métricas por tramo (`segmentos`): el pico de una pantalla no se diluye en la ventana del flujo."""

    def flow(self):
        return {"ventana": {"desde": {"marca": "NAV lista"}, "hasta": {"marca": "MARK detalle"}},
                "segmentos": [{"nombre": "detalle", "desde": {"marca": "NAV detalle"}, "hasta": {"marca": "MARK detalle"}}]}

    def trace(self, peak_ms=72):
        frames = [("frame", i * 20 * MS, 16 * MS, 0, "None") for i in range(50)]  # la lista, de 0 a 1000 ms, sin jank
        frames += [("frame", 1100 * MS, peak_ms * MS, 0, "App Deadline Missed"),  # el pico al entrar al detalle
                   ("frame", 1200 * MS, 16 * MS, 0, "None"), ("frame", 1220 * MS, 16 * MS, 0, "None")]
        main = [("hilo", 100 * MS, 8 * MS, 0, "Choreographer#doFrame"), ("hilo", 1100 * MS, peak_ms * MS, 0, "Choreographer#doFrame"),
                ("hilo", 1105 * MS, 30 * MS, 1, "traversal")]
        marks = [("seccion", 0, 0, 0, "NAV lista"), ("seccion", 1090 * MS, 0, 0, "NAV detalle"),
                 ("seccion", 1250 * MS, 0, 0, "MARK detalle")]
        return [("proceso", 0, 0, 0, PKG), ("limites", 0, 5000 * MS, 0, "")] + frames + main + marks

    def metrics(self, rows, flow):
        out, invalid, info = perf.trace_metrics(rows, 60, flow, set(), 34)
        self.assertIsNone(invalid)
        return {m[0]: m for m in out}, info

    def test_el_tramo_aisla_el_pico_que_la_ventana_diluye(self):
        m, info = self.metrics(self.trace(), self.flow())
        self.assertEqual(m["frame_p90_ms"][1], 16)  # 53 frames en la ventana: el pico no mueve el P90
        self.assertAlmostEqual(m["jank_app_pct"][1], 100 / 53)
        self.assertEqual(m["detalle hilo_max_ms"][1:], (72, "ms", "app"))
        self.assertEqual(m["detalle frame_p90_ms"][1:], (72, "ms", "app"))
        self.assertAlmostEqual(m["detalle jank_app_pct"][1], 100 / 3)
        self.assertEqual(m["detalle frames"][1:], (3, "frames", "info"))
        self.assertEqual(info["faltantes"], [])

    def test_declarar_tramos_no_cambia_las_metricas_de_la_ventana(self):
        with_segments, _ = self.metrics(self.trace(), self.flow())
        flow = self.flow()
        del flow["segmentos"]
        without, _ = self.metrics(self.trace(), flow)
        self.assertEqual({k: v for k, v in with_segments.items() if not k.startswith("detalle ")}, without)

    def test_cuenta_lo_que_se_solapa_con_el_tramo_aunque_empiece_antes_y_lo_que_queda_fuera_de_la_ventana(self):
        rows = self.trace() + [("hilo", 1080 * MS, 90 * MS, 0, "deliverInputEvent"),  # empezó antes del NAV y sigue
                               ("hilo", 2000 * MS, 300 * MS, 0, "tarde")]  # después del tramo: no cuenta
        flow = self.flow()
        flow["ventana"] = {"desde": {"marca": "NAV lista"}, "hasta": {"marca": "NAV detalle"}}  # el tramo queda fuera
        m, _ = self.metrics(rows, flow)
        self.assertEqual(m["detalle hilo_max_ms"][1], 90)
        self.assertEqual(m["hilo_max_ms"][1], 90)  # la ventana sigue contando por inicio: el slice de 1080 ms entra
        flow["segmentos"][0]["margen_ms"] = 800
        self.assertEqual(self.metrics(rows, flow)[0]["detalle hilo_max_ms"][1], 300)

    def test_un_tramo_sin_marcas_no_trae_metricas_y_queda_en_faltantes(self):
        flow = self.flow()
        flow["segmentos"].append({"nombre": "reparto", "desde": {"marca": "NAV reparto"}, "hasta": {"marca": "MARK reparto"}})
        m, info = self.metrics(self.trace(), flow)
        self.assertEqual(info["faltantes"], ["tramo reparto"])
        self.assertIn("detalle hilo_max_ms", m)
        self.assertFalse([k for k in m if k.startswith("reparto ")])

    def test_un_tramo_sin_frames_solo_trae_el_hilo(self):
        rows = [r for r in self.trace() if not (r[0] == "frame" and r[1] >= 1000 * MS)]
        m, _ = self.metrics(rows, self.flow())
        self.assertEqual(m["detalle hilo_max_ms"][1], 72)
        self.assertNotIn("detalle frame_p90_ms", m)
        self.assertNotIn("detalle jank_app_pct", m)

    def test_las_familias_del_flujo_tambien_valen_para_un_tramo(self):
        flow = self.flow()
        flow["familias"] = {"detalle jank_app_pct": "info"}
        self.assertEqual(self.metrics(self.trace(), flow)[0]["detalle jank_app_pct"][3], "info")

    def test_el_plan_valida_los_tramos(self):
        base = {"paquete": PKG, "flujos": {"f": self.flow()}}
        path = self.dir / "plan.json"
        write(path, json.dumps(base))
        self.assertEqual(perf.user_metric_names(perf.load_plan(path)),
                         ["detalle hilo_max_ms", "detalle frame_p90_ms", "detalle jank_app_pct"])
        good = base["flujos"]["f"]["segmentos"][0]
        for bad in ([dict(good, nombre="con espacio")], [dict(good, nombre="red")], [good, good], [{"nombre": "x"}],
                    [dict(good, nombre=None)], [dict(good, nombre=True)], [dict(good, margen_ms="mucho")],
                    [dict(good, margen_ms=float("inf"))],
                    [dict(good, hasta={"marca": "MARK x", "punto": "medio"})], {"nombre": "detalle"}, ["detalle"]):
            base["flujos"]["f"]["segmentos"] = bad
            write(path, json.dumps(base))
            with self.assertRaises(perf.PerfError, msg=str(bad)) as caught:
                perf.load_plan(path)
            self.assertIn("'f.segmentos' es una lista de tramos", str(caught.exception))
        base["flujos"]["f"]["segmentos"] = [dict(good, margen_ms="250")]  # lo que int() lee, vale: como en la ventana
        base["flujos"]["f"]["ventana"]["margen_ms"] = "mucho"
        write(path, json.dumps(base))
        with self.assertRaises(perf.PerfError) as caught:
            perf.load_plan(path)
        self.assertIn("flujos.f.ventana.margen_ms es un número", str(caught.exception))

    def test_comparar_da_veredicto_por_tramo_y_no_compara_si_cambian_sus_frames(self):
        text = rows("antes", "f", "detalle hilo_max_ms", [70, 71, 69, 70, 72]) \
            + rows("despues", "f", "detalle hilo_max_ms", [20, 21, 19, 20, 22]) \
            + rows("antes", "f", "detalle frames", [10] * 5, "frames", family="info") \
            + rows("despues", "f", "detalle frames", [30] * 5, "frames", family="info") \
            + rows("antes", "f", "detalle frame_p90_ms", [40, 41, 39, 40, 42]) \
            + rows("despues", "f", "detalle frame_p90_ms", [20] * 5) \
            + rows("antes", "f", "frames", [100] * 5, "frames", family="info") \
            + rows("despues", "f", "frames", [100] * 5, "frames", family="info") \
            + rows("antes", "f", "frame_p90_ms", [40, 41, 39, 40, 42]) + rows("despues", "f", "frame_p90_ms", [20] * 5)
        verdicts = {r["metrica"]: r for r in perf.compare(read_rows_from(text))[0]}
        self.assertEqual(verdicts["detalle hilo_max_ms"]["veredicto"], "mejora")
        self.assertEqual(verdicts["detalle frame_p90_ms"]["veredicto"], "no comparable")  # sus frames pasaron de 10 a 30
        self.assertEqual(verdicts["frame_p90_ms"]["veredicto"], "mejora")  # los de la ventana no cambiaron
        software = {r["metrica"]: r for r in perf.compare(read_rows_from(text), trust=("no", "render por software"))[0]}
        self.assertEqual(software["detalle frame_p90_ms"]["veredicto"], "no confiable")
        self.assertEqual(software["detalle hilo_max_ms"]["veredicto"], "mejora")

    def test_las_metricas_por_tramo_salen_en_la_salida_compacta(self):
        plan = {"flujos": {"f": self.flow()}}
        self.assertEqual(perf.priority("detalle hilo_max_ms", plan)[0], 1)
        self.assertEqual(perf.priority("otra cosa", plan)[0], 3)


class SegmentsCaptureTest(DeviceBase):
    def test_capturar_guarda_las_metricas_del_tramo_en_todas_las_corridas_y_repite_la_que_no_lo_recorrio(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["principales"] = ["detalle hilo_max_ms"]
        plan["flujos"]["home"]["segmentos"] = [{"nombre": "detalle", "desde": {"marca": "NAV detalle"},
                                                 "hasta": {"marca": "MARK detalle"}}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marks = GOOD + '"seccion",5000000,0,0,"NAV detalle"\n"seccion",250000000,0,0,"MARK detalle"\n'
        self.tp_outputs(GOOD, marks, marks)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertIn("sin marcas para detalle hilo_max_ms: el recorrido no completó el flujo", out)
        self.assertIn("corrida 2/2", out)
        data = self.read_csv_at(self.plan.parent / "metricas.csv")
        values = sorted((k[2], v["valor"], v["familia"]) for k, v in data.items() if k[1] == "detalle hilo_max_ms")
        self.assertEqual(values, [("2", "30", "app"), ("3", "30", "app")])
        self.assertEqual(len([k for k in data if k[1] == "detalle frame_p90_ms"]), 2)
        self.assertIn("detalle hilo_max_ms", out[out.index("| Fase |"):])  # en el resumen compacto de la fase

    def test_un_tramo_con_marcas_pero_sin_frames_no_sirve_para_una_principal_de_frames_y_lo_dice(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["principales"] = ["detalle frame_p90_ms"]
        plan["flujos"]["home"]["segmentos"] = [{"nombre": "detalle", "desde": {"marca": "NAV detalle"},
                                                 "hasta": {"marca": "MARK detalle"}}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        late = GOOD + '"seccion",3000000000,0,0,"NAV detalle"\n"seccion",3100000000,0,0,"MARK detalle"\n'  # sin frames ahí
        self.tp_outputs(late)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2",
                           "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("inválida: sin frames en el tramo para detalle frame_p90_ms", result.stdout)
        self.assertNotIn("sin marcas para", result.stdout)
        self.assertIn("usa '<tramo> hilo_max_ms' como principal", result.stderr)

    def read_csv_at(self, path):
        with path.open(newline="", encoding="utf-8") as f:
            return {(r["fase"], r["metrica"], r["corrida"]): r for r in csv.DictReader(f)}


FINDINGS = "# Rendimiento · Detalle · 2026-11-09\n\n## Resumen ejecutivo\n\nTexto.\n\n## Hallazgos\n\n" \
           "| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n" \
           "| H1 | Carga lenta | 131 ms | Red en el hilo | bug |\n" \
           "| H2 | Frame largo al abrir el detalle | 44 ms en las 10 corridas | sin probar | sin confirmar |\n" \
           "| H3 | Frame largo al cerrar el detalle | 37 ms en las 10 corridas | sin probar | sin confirmar |\n\n" \
           "## Plan de mejoras\n\n<!-- perf:mejoras -->\n<!-- /perf:mejoras -->\n\n## Decisiones\n\n"


class TrialImprovementTest(PerfBase):
    """Mejora a prueba: un síntoma estable sin causa probada; la medición de después confirma o refuta la hipótesis."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = {"paquete": PKG, "principales": ["carga_ms"], "flujos": {"f": {}}, "mejoras": [
            {"id": "M1", "titulo": "Caché", "hallazgo": "H1", "metrica": "carga_ms", "estado": "propuesta"},
            {"id": "M2", "titulo": "Decodificar la imagen fuera del hilo principal", "hallazgo": "H2", "a_prueba": True,
             "hipotesis": "el pico es la decodificación de la imagen de cabecera", "metrica": "detalle hilo_max_ms", "esperado": "≤ 16 ms",
             "estado": "propuesta"},
            {"id": "M3", "titulo": "Precalcular el layout del texto", "hallazgo": "H3", "a_prueba": True,
             "hipotesis": "el pico es el layout del texto largo", "metrica": "cierre hilo_max_ms", "esperado": "≤ 16 ms",
             "estado": "propuesta"}]}
        write(self.folder / "estado.md", FINDINGS)
        self.save()
        self.before = rows("antes", "f", "carga_ms", [131, 130, 132, 129, 131]) \
            + rows("antes", "f", "detalle hilo_max_ms", [44, 45, 43, 44, 46]) \
            + rows("antes", "f", "cierre hilo_max_ms", [37, 38, 36, 37, 39])
        write(self.folder / "metricas.csv", HEADER + self.before)

    def save(self):
        write(self.folder / "plan.json", json.dumps(self.plan))

    def test_el_plan_exige_hipotesis_metrica_y_esperado_en_una_mejora_a_prueba(self):
        for missing in ("hipotesis", "metrica", "esperado"):
            plan = json.loads(json.dumps(self.plan))
            del plan["mejoras"][1][missing]
            write(self.folder / "plan.json", json.dumps(plan))
            result = self.perf("siguiente", "--carpeta", self.folder)
            self.assertEqual(result.returncode, 2, missing)
            self.assertIn("la mejora a prueba M2 necesita 'hipotesis', 'metrica' y 'esperado'", result.stderr)
        self.plan["mejoras"][1]["a_prueba"] = "sí"
        self.save()
        self.assertIn("'a_prueba' de la mejora M2 es true o false", self.perf("siguiente", "--carpeta", self.folder).stderr)

    def test_el_reporte_inicial_la_propone_con_su_hipotesis_y_el_usuario_la_decide_como_cualquier_otra(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial")
        initial = (self.folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("| M1 | Caché | H1 | carga_ms | 131 ms |", initial)
        self.assertIn("| M2 | Decodificar la imagen fuera del hilo principal (a prueba) | H2 | detalle hilo_max_ms | 44 ms | ≤ 16 ms |", initial)
        self.assertIn("| propuesta |\n\n**Mejoras a prueba**", initial)  # con línea en blanco: no es una fila de la tabla
        self.assertIn("- **M2** · hipótesis: el pico es la decodificación de la imagen de cabecera · se confirma si `detalle hilo_max_ms` mejora "
                      "(esperado: ≤ 16 ms)", initial)
        self.assertIn("| H2 | Frame largo al abrir el detalle | 44 ms en las 10 corridas | sin probar | sin confirmar | M2 (propuesta) |",
                      initial)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("- **M3** · hipótesis: el pico es el layout del texto largo", state)
        out = self.ok("decidir", "--carpeta", self.folder, "--aprobar", "M2,M3", "--pendiente", "M1")
        self.assertIn("sesión 3, aplica M2", out)
        self.assertIn("aplica M2 (a prueba: la medición de después confirma o refuta su hipótesis)", out)
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual([m["estado"] for m in plan["mejoras"]], ["pendiente", "aprobada", "aprobada"])
        self.assertTrue(plan["mejoras"][1]["a_prueba"])
        self.assertIn("| M2 | Decodificar la imagen fuera del hilo principal (a prueba) |", (self.folder / "estado.md").read_text(encoding="utf-8"))

    def test_el_reporte_final_dice_si_la_hipotesis_se_confirmo_o_se_refuto(self):
        for item in self.plan["mejoras"]:
            item["estado"] = "aplicada"
        self.save()
        write(self.folder / "metricas.csv", HEADER + self.before
              + rows("despues", "f", "carga_ms", [46, 45, 47, 46, 44])
              + rows("despues", "f", "detalle hilo_max_ms", [11, 12, 10, 11, 13])
              + rows("despues", "f", "cierre hilo_max_ms", [37, 38, 36, 37, 38]))
        self.ok("reporte", "--carpeta", self.folder, "--html")
        final = (self.folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("| M1 | Caché | H1 | ✔ funcionó | carga_ms: 131 ms → 46 ms", final)
        self.assertIn("| M2 | Decodificar la imagen fuera del hilo principal (a prueba) | H2 | ✔ hipótesis confirmada | hipótesis: el pico es la "
                      "decodificación de la imagen de cabecera · detalle hilo_max_ms: 44 ms → 11 ms (-75 %)", final)
        self.assertIn("| M3 | Precalcular el layout del texto (a prueba) | H3 | ✖ hipótesis refutada | hipótesis: el pico es el layout del texto largo · "
                      "cierre hilo_max_ms: 37 ms → 37 ms", final)
        self.assertIn("| sin confirmar | ✔ M2: hipótesis confirmada (detalle hilo_max_ms mejora) |", final)
        self.assertIn("| sin confirmar | ✖ M3: hipótesis refutada (cierre hilo_max_ms sin cambio) |", final)
        self.assertIn("3 hallazgos → 3 mejoras propuestas → 3 aplicadas → 2 funcionaron", final)
        self.assertIn("| ≤ 16 ms | 11 ms | -75 % | mejora | aplicada | ✔ hipótesis confirmada |", final)
        page = (self.folder / "reporte-final.html").read_text(encoding="utf-8")
        self.assertIn('<td class="ok">✔ hipótesis confirmada</td>', page)
        self.assertIn('<td class="ko">✖ hipótesis refutada</td>', page)
        self.assertIn("Mejora a prueba:", final)  # el glosario la explica
        out = self.ok("comparar", self.folder / "metricas.csv")
        self.assertIn("estado.md actualizado (Plan de mejoras", out)
        self.assertIn("✖ hipótesis refutada", (self.folder / "estado.md").read_text(encoding="utf-8"))

    def test_una_regresion_refuta_la_hipotesis_y_sin_medicion_no_hay_resultado(self):
        trial = {"a_prueba": True, "estado": "aplicada"}
        self.assertEqual(perf.improvement_result(trial, {"veredicto": "regresión"}), "✖ hipótesis refutada (empeoró)")
        self.assertEqual(perf.improvement_result(trial, {"veredicto": "dentro del ruido"}), "✖ hipótesis refutada")
        self.assertEqual(perf.improvement_result(trial, {"veredicto": "no confiable"}), "— sin veredicto")
        self.assertEqual(perf.improvement_result(trial, None), "— sin medir")
        self.assertEqual(perf.improvement_result(dict(trial, estado="aprobada"), {"veredicto": "mejora"}), "— no aplicada")
        self.assertEqual(perf.improvement_result({"estado": "aplicada"}, {"veredicto": "mejora"}), "✔ funcionó")


STATE_BLOCKS = "# Rendimiento · Home · 2026-11-09\n\n## Siguiente paso\n\n- x\n\n## Métricas\n\n<!-- perf:metricas -->\n" \
               "<!-- /perf:metricas -->\n\n## Comparación\n\n<!-- perf:comparacion -->\n<!-- /perf:comparacion -->\n"
HZ_90 = GOOD + '"vsync",0,11111111,0,""\n'


class RefreshRateTest(DeviceBase):
    """El `hz` del plan contra la tasa que midió la traza, y la tasa que el dispositivo ya tiene fijada."""

    def test_el_aviso_depende_de_la_tolerancia_y_de_si_hay_hz_en_el_plan(self):
        self.assertEqual(perf.hz_warning(60, [60, 60]), "")
        self.assertEqual(perf.hz_warning(60, [None]), "")
        self.assertEqual(perf.hz_warning(90, [88]), "")  # 2 %: dentro de la tolerancia
        self.assertIn("el plan dice 60 Hz y la traza midió 90 Hz", perf.hz_warning(60, [90, 90]))
        self.assertIn("el plan dice 120 Hz y la traza midió 60/90 Hz", perf.hz_warning(120, [90, 60, None]))
        self.assertEqual(perf.hz_warning(None, [90, 90]), "")
        self.assertIn("cambió entre corridas (60/90 Hz)", perf.hz_warning(None, [60, 90]))

    def test_la_prueba_avisa_si_el_hz_del_plan_no_es_el_de_la_traza(self):
        self.tp_outputs(HZ_90)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("Tasa de refresco: 60 Hz (plan)", out)
        self.assertIn("⚠ TASA DE REFRESCO: el plan dice 60 Hz y la traza midió 90 Hz", out)
        self.tp_outputs(GOOD + '"vsync",0,16666666,0,""\n')
        self.assertNotIn("TASA DE REFRESCO", self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba"))

    def test_capturar_deja_el_aviso_en_la_salida_en_estado_y_en_fases_y_guarda_la_tasa_de_cada_corrida(self):
        write(self.plan.parent / "estado.md", STATE_BLOCKS)
        self.tp_outputs(HZ_90)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertIn("⚠ TASA DE REFRESCO: el plan dice 60 Hz y la traza midió 90 Hz", out)
        phase = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))["antes"]
        self.assertEqual(phase["hz_corridas"], [90, 90])
        self.assertEqual(phase["hz"], 60)
        self.assertEqual(len(phase["avisos"]), 1)
        self.assertIn("repite lo medido así con --rehacer", phase["avisos"][0])
        state = (self.plan.parent / "estado.md").read_text(encoding="utf-8")
        self.assertIn("> ⚠ antes: TASA DE REFRESCO: el plan dice 60 Hz y la traza midió 90 Hz", state)
        write(self.plan.parent / "metricas.csv", (self.plan.parent / "metricas.csv").read_text(encoding="utf-8")
              + rows("despues", "home", "jank_app_pct", [5] * 5, "%"))
        self.assertIn("⚠ antes: TASA DE REFRESCO", self.ok("comparar", self.plan.parent / "metricas.csv"))
        # otra tanda de la misma fase no repite el aviso y suma las tasas
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        phase = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))["antes"]
        self.assertEqual((phase["hz_corridas"], len(phase["avisos"])), ([90, 90, 90], 1))

    def test_con_el_hz_correcto_o_sin_hz_no_hay_aviso_y_la_tasa_queda_igual(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        del plan["hz"]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.tp_outputs(HZ_90)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertNotIn("TASA DE REFRESCO", out)
        phase = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))["antes"]
        self.assertEqual((phase["hz"], phase["hz_corridas"]), (90, [90, 90]))
        self.assertNotIn("avisos", phase)
        self.tp_outputs(HZ_90, GOOD + '"vsync",0,16666666,0,""\n')
        (self.dir / "tp.count").unlink()  # el trace_processor falso vuelve a empezar por la primera salida
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "2",
                      "--calentamiento", "0")
        self.assertIn("⚠ TASA DE REFRESCO: cambió entre corridas (60/90 Hz)", out)

    def test_nuevo_pone_en_el_plan_la_tasa_que_el_dispositivo_ya_tiene_fija(self):
        self.env.update({"FAKE_MIN_HZ": "90.0", "FAKE_PEAK_HZ": "90.0"})
        out = self.ok("nuevo", "--carpeta", self.dir / "fija", "--paquete", PKG, "--flujo", "x")
        self.assertIn("✔ Tasa de refresco ya fija en el dispositivo: 90 Hz (min_refresh_rate=90, peak_refresh_rate=90)", out)
        self.assertNotIn("settings put", out)
        self.assertEqual(json.loads((self.dir / "fija" / "plan.json").read_text(encoding="utf-8"))["hz"], 90)
        device = next(l for l in (self.dir / "fija" / "estado.md").read_text(encoding="utf-8").splitlines()
                      if l.startswith("| Dispositivo"))
        self.assertEqual(device, "| Dispositivo | Pixel Test · Android 14 (API 34) · 90 Hz fijos |")

    def test_si_no_esta_fija_da_el_comando_que_la_fija_y_el_que_la_restaura(self):
        self.env.update({"FAKE_MIN_HZ": "null", "FAKE_PEAK_HZ": "120.0"})
        out = self.ok("nuevo", "--carpeta", self.dir / "adaptativa", "--paquete", PKG, "--flujo", "x", "--serial", "emulator-5554")
        self.assertIn("⚠ La tasa de refresco no está fija en el dispositivo (min_refresh_rate=sin poner, peak_refresh_rate=120.0)", out)
        self.assertIn("Fijarla antes de medir:  adb -s emulator-5554 shell settings put system min_refresh_rate 120 && "
                      "adb -s emulator-5554 shell settings put system peak_refresh_rate 120", out)
        self.assertIn("Restaurarla al cerrar:   adb -s emulator-5554 shell settings delete system min_refresh_rate && "
                      "adb -s emulator-5554 shell settings put system peak_refresh_rate 120.0\n", out)  # lo que había, tal cual
        self.assertNotIn("hz", json.loads((self.dir / "adaptativa" / "plan.json").read_text(encoding="utf-8")))
        self.assertIn("tasa de refresco sin fijar", (self.dir / "adaptativa" / "estado.md").read_text(encoding="utf-8"))
        self.env.update({"FAKE_MIN_HZ": "", "FAKE_PEAK_HZ": "Infinity"})  # ajustes que no existen o no son una tasa
        out = self.ok("nuevo", "--carpeta", self.dir / "sin-ajustes", "--paquete", PKG, "--flujo", "x")
        self.assertIn("adb shell settings put system min_refresh_rate <hz>", out)
        self.assertIn("adb shell settings delete system min_refresh_rate && adb shell settings put system peak_refresh_rate "
                      "Infinity", out)  # Infinity no es una tasa, pero es lo que había: se restaura, no se borra
        out = self.ok("nuevo", "--carpeta", self.dir / "con-hz", "--paquete", PKG, "--flujo", "x", "--hz", "120")
        self.assertEqual(json.loads((self.dir / "con-hz" / "plan.json").read_text(encoding="utf-8"))["hz"], 120)


class RouteChecksTest(DeviceBase):
    """La corrida de prueba avisa si una métrica de usuario abarca toques del recorrido o si una marca se repite."""

    def flow(self):
        return {"metricas_usuario": [
            {"nombre": "lista_a_reparto_ms", "desde": {"marca": "NAV lista"}, "hasta": {"marca": "MARK reparto"}},
            {"nombre": "detalle_a_reparto_ms", "desde": {"marca": "NAV reparto"}, "hasta": {"marca": "MARK reparto"}}]}

    def trace(self):
        return [("proceso", 0, 0, 0, PKG), ("frame", 0, 16 * MS, 0, "None"),
                ("input", 90 * MS, 2 * MS, 0, "deliverInputEvent src=0x1002 eventTimeNano=1 id=0x1"),  # el toque que abre la lista
                ("seccion", 100 * MS, 0, 0, "NAV lista"),
                ("input", 105 * MS, 2 * MS, 0, "deliverInputEvent src=0x1002 eventTimeNano=2 id=0x2"),  # el ACTION_UP del mismo toque
                ("input", 4000 * MS, 2 * MS, 0, "deliverInputEvent src=0x1002 eventTimeNano=3 id=0x3"),  # otro paso del recorrido
                ("input", 4010 * MS, 2 * MS, 0, "deliverInputEvent src=0x1002 eventTimeNano=4 id=0x4"),
                ("seccion", 4020 * MS, 0, 0, "NAV reparto"), ("seccion", 4400 * MS, 0, 0, "MARK reparto")]

    def test_una_metrica_que_contiene_otros_toques_mide_el_script(self):
        out, invalid, info = perf.trace_metrics(self.trace(), 60, self.flow(), set(), 34)
        self.assertIsNone(invalid)
        self.assertEqual(info["con_input"], {"lista_a_reparto_ms": 2})  # la de un solo salto no los contiene
        self.assertEqual(info["input"], 4)
        self.assertEqual({m[0]: m[1] for m in out}["lista_a_reparto_ms"], 4300)  # la métrica no cambia: solo se avisa

    def test_el_gesto_que_dispara_la_metrica_no_cuenta_aunque_dure_mas_que_la_gracia(self):
        # un swipe de 300 ms: sus MOVE siguen llegando cada 20 ms después de la marca de inicio del scroll
        swipe = [("input", (1000 + i * 20) * MS, MS, 0, "deliverInputEvent src=0x1002") for i in range(16)]
        rows = [("proceso", 0, 0, 0, PKG), ("frame", 0, 16 * MS, 0, "None"), ("seccion", 1010 * MS, 0, 0, "MARK scroll_inicio"),
                ("seccion", 2000 * MS, 0, 0, "MARK scroll_fin")] + swipe
        flow = {"metricas_usuario": [{"nombre": "scroll_ms", "desde": {"marca": "MARK scroll_inicio"},
                                      "hasta": {"marca": "MARK scroll_fin"}}]}
        self.assertEqual(perf.trace_metrics(rows, 60, flow, set(), 34)[2]["con_input"], {})
        late = rows + [("input", 1700 * MS, MS, 0, "deliverInputEvent src=0x1002")]  # otro gesto, 400 ms después del swipe
        self.assertEqual(perf.trace_metrics(late, 60, flow, set(), 34)[2]["con_input"], {"scroll_ms": 1})

    def test_sin_slices_de_input_no_hay_nada_que_avisar(self):
        rows = [r for r in self.trace() if r[0] != "input"]
        info = perf.trace_metrics(rows, 60, self.flow(), set(), 34)[2]
        self.assertEqual((info["con_input"], info["input"]), ({}, 0))

    def test_la_prueba_lo_avisa_y_la_consulta_usa_el_patron_del_plan(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(self.flow())
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marks = '"seccion",100000000,0,0,"NAV lista"\n"seccion",4020000000,0,0,"NAV reparto"\n' \
                '"seccion",4400000000,0,0,"MARK reparto"\n'
        self.tp_outputs(GOOD + marks + '"input",4000000000,2000000,0,"deliverInputEvent src=0x1002"\n')
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("⚠ lista_a_reparto_ms incluye pasos del recorrido (1 eventos de input entre sus marcas): mide el "
                      "script, no la app", out)
        self.assertNotIn("detalle_a_reparto_ms incluye", out)
        self.assertNotIn("Sin slices de input", out)
        self.assertIn("WHERE s.name GLOB 'deliverInputEvent*'", (self.dir / "tp.sql").read_text(encoding="utf-8"))
        self.tp_outputs(GOOD + marks)
        plan["input_slices"] = "dispatchInput*"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("Sin slices de input ('dispatchInput*') en la traza", out)
        self.assertIn("WHERE s.name GLOB 'dispatchInput*'", (self.dir / "tp.sql").read_text(encoding="utf-8"))
        plan["input_slices"] = "x' OR 1=1 --"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 2)
        self.assertIn("'input_slices' es un patrón GLOB", result.stderr)

    def test_una_marca_repetida_en_la_misma_carga_se_detecta_y_una_por_carga_no(self):
        once = [("seccion", 0, 0, 0, "NAV home"), ("seccion", 10, 0, 0, "MARK home"), ("seccion", 20, 0, 0, "NAV detalle"),
                ("seccion", 30, 0, 0, "MARK detalle"), ("seccion", 40, 0, 0, "NAV home"), ("seccion", 50, 0, 0, "MARK home")]
        self.assertEqual(perf.repeated_marks(once), {})  # home se cargó dos veces: una marca por carga
        # el gancho avisa en cada paso del ciclo de vida de la misma pantalla: tres marcas para una sola carga
        thrice = [("seccion", 0, 5, 0, "SCREEN MainActivity onCreate"), ("seccion", 10, 0, 0, "MARK login"),
                  ("seccion", 15, 5, 0, "SCREEN MainActivity onStart"), ("seccion", 20, 0, 0, "MARK login"),
                  ("seccion", 25, 5, 0, "SCREEN MainActivity onResume"), ("seccion", 30, 0, 0, "MARK login")]
        self.assertEqual(perf.repeated_marks(thrice), {"MARK login": 3})
        # otra pantalla, otra marca o una llamada de red entre las dos apariciones: es una carga nueva, no un duplicado
        for between in ("SCREEN DetalleActivity onCreate", "MARK busqueda_inicio", "HTTP GET items", "NAV lista"):
            reload = [("seccion", 0, 5, 0, "SCREEN MainActivity onResume"), ("seccion", 10, 0, 0, "MARK lista"),
                      ("seccion", 20, 5, 0, between), ("seccion", 30, 0, 0, "MARK lista")]
            self.assertEqual(perf.repeated_marks(reload), {}, between)

    def test_humo_avisa_de_la_marca_repetida(self):
        self.tp_outputs(GOOD + '"seccion",20,0,0,"MARK login"\n"seccion",30,0,0,"MARK login"\n"seccion",40,0,0,"MARK login"\n')
        out = self.ok("humo", "--paquete", PKG)
        self.assertIn("⚠ 'MARK login' salió 3 veces en una misma carga (sin navegación ni otra carga entre ellas)", out)
        self.assertIn("una vez por carga", out)
        self.tp_outputs(GOOD + '"seccion",20,0,0,"MARK login"\n')
        self.assertNotIn("veces en una misma carga", self.ok("humo", "--paquete", PKG, "--carpeta", self.dir / "otra"))


class RedoFlowTest(DeviceBase):
    """--rehacer quita solo lo del flujo que se rehace: el registro, las filas y las trazas de los otros flujos siguen."""

    def setUp(self):
        super().setUp()
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["detalle"] = dict(plan["flujos"]["home"])
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.folder = self.plan.parent
        self.common = ["capturar", "--plan", self.plan, "--fase", "antes", "--calentamiento", "0", "--sin-compilar"]

    def phase(self):
        return json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))["antes"]

    def runs(self, flow):
        with (self.folder / "metricas.csv").open(newline="", encoding="utf-8") as f:
            return sorted({r["corrida"] for r in csv.DictReader(f) if r["flujo"] == flow})

    def test_rehacer_un_flujo_conserva_el_registro_y_las_trazas_del_otro(self):
        self.tp_outputs(HZ_90)
        self.env.update({"FAKE_EMULATOR": "1", "FAKE_GLES": GLES_SOFT})  # 'detalle' se mide con render por software
        self.ok(*(self.common + ["--flujo", "detalle", "--corridas", "3"]))
        self.env.pop("FAKE_EMULATOR")
        self.env["FAKE_GLES"] = GLES_REAL
        self.ok(*(self.common + ["--flujo", "home", "--corridas", "2"]))
        phase = self.phase()
        self.assertEqual((phase["corridas"], phase["flujos"]["home"]["corridas"], phase["flujos"]["detalle"]["corridas"]), (5, 2, 3))
        out = self.ok(*(self.common + ["--flujo", "home", "--corridas", "1", "--rehacer"]))
        self.assertIn("filas de 'antes' fuera del CSV", out)
        phase = self.phase()
        self.assertEqual(phase["corridas"], 4)  # 3 de detalle + la nueva de home
        self.assertEqual(without_new(phase["flujos"]["detalle"]), {"corridas": 3, "hz_corridas": [90, 90, 90], "avisos": phase["avisos"],
                                                       "entorno": phase["entorno"]})
        self.assertEqual(phase["flujos"]["home"]["corridas"], 1)
        self.assertEqual(phase["entorno"]["frames"], "no")  # el entorno de 'detalle' no se pierde
        self.assertEqual(len(phase["hz_corridas"]), 4)
        self.assertEqual((self.runs("detalle"), self.runs("home")), (["1", "2", "3"], ["1"]))
        kept = sorted(p.name for p in (self.folder / "antes").iterdir() if p.name != perf.CONFIG_FILE)
        self.assertEqual(kept, ["detalle_1.perfetto-trace.gz", "detalle_2.perfetto-trace.gz", "detalle_3.perfetto-trace.gz",
                                "home_1.perfetto-trace.gz"])
        discarded = next(p for p in self.folder.iterdir() if p.name.startswith("antes-descartada-"))
        self.assertEqual(sorted(p.name for p in discarded.iterdir()), ["home_1.perfetto-trace.gz", "home_2.perfetto-trace.gz"])

    def test_rehacer_despues_con_dos_flujos_renueva_la_fecha_y_siguiente_no_vuelve_a_pedirlo(self):
        self.tp_outputs(GOOD)
        common = ["capturar", "--plan", self.plan, "--calentamiento", "0", "--sin-compilar", "--corridas", "1"]
        for flow in ("home", "detalle"):
            self.ok(*(common + ["--fase", "antes", "--flujo", flow]))
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"  # el build con la mejora
        for flow in ("home", "detalle"):
            self.ok(*(common + ["--fase", "despues", "--flujo", flow]))
        phases = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))
        phases["despues"]["fecha"] = "2026-11-06T10:00:00"  # se midió antes de aplicar la segunda mejora
        write(self.folder / "fases.json", json.dumps(phases))
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["mejoras"] = [{"id": "M1", "titulo": "a", "estado": "aplicada", "aplicada_en": "2026-11-07T10:00:00"}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.assertEqual(perf.next_steps(self.folder, plan)[0], "medición después (sin chat)")
        self.env["FAKE_UPDATED"] = "2026-11-08 09:00:00"
        out = self.ok(*(common + ["--fase", "despues", "--flujo", "home", "--rehacer"]))
        self.assertIn("sesión 4 · cierre", out)  # con la fecha nueva, la fase ya no está vieja
        despues = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))["despues"]
        self.assertGreater(despues["fecha"], "2026-11-07T10:00:00")
        self.assertEqual((despues["corridas"], sorted(despues["flujos"])), (2, ["detalle", "home"]))

    def test_un_registro_por_flujo_incompleto_no_se_usa_para_recalcular(self):
        # la fase empezó con una versión anterior (sin 'flujos') y 'detalle' sumó después una tanda con su registro
        soft = {"emulador": True, "software": True, "render": "SwiftShader", "frames": "no"}
        write(self.folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-09T10:00:00", "corridas": 5, "entorno": soft,
                                                                 "flujos": {"detalle": {"corridas": 1}}}}))
        write(self.folder / "metricas.csv", HEADER + rows("antes", "home", "jank_app_pct", [1, 2], "%")
              + rows("antes", "detalle", "jank_app_pct", [1, 2, 3], "%"))
        perf.forget_flow(self.folder, self.folder / "metricas.csv", "antes", "home")
        phase = self.phase()
        self.assertEqual(phase["corridas"], 3)
        self.assertEqual(phase["entorno"], soft)  # 'detalle' tiene 3 corridas y su registro solo 1: no alcanza para saberlo

    def test_rehacer_el_unico_flujo_medido_borra_el_registro_de_la_fase_como_antes(self):
        self.tp_outputs(GOOD)
        self.ok(*(self.common + ["--flujo", "home", "--corridas", "2"]))
        self.assertEqual(without_new(self.phase()["flujos"]["home"]), {"corridas": 2})
        perf.forget_flow(self.folder, self.folder / "metricas.csv", "control", "home")  # una fase sin medir: no hace nada
        self.assertEqual(self.phase()["corridas"], 2)
        perf.forget_flow(self.folder, self.folder / "metricas.csv", "antes", "home")  # no hay filas de otros flujos
        self.assertNotIn("antes", perf.read_phases(self.folder))

    def test_un_registro_sin_datos_por_flujo_conserva_los_de_la_fase(self):
        # fases.json de una versión anterior: sin 'flujos'. No se puede saber de qué flujo era el entorno: se conserva.
        soft = {"emulador": True, "software": True, "render": "SwiftShader", "frames": "no"}
        write(self.folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-09T10:00:00", "commit": "abc1234",
                                                                 "corridas": 4, "hz": 60, "entorno": soft}}))
        write(self.folder / "metricas.csv", HEADER + rows("antes", "home", "jank_app_pct", [1, 2], "%")
              + rows("antes", "detalle", "jank_app_pct", [1, 2], "%"))
        with contextlib.redirect_stdout(io.StringIO()):
            perf.discard_phase(self.folder, self.folder / "metricas.csv", "antes", "home")
        phase = self.phase()
        self.assertEqual((phase["corridas"], phase["commit"], phase["entorno"]), (2, "abc1234", soft))
        self.assertNotIn("flujos", phase)
        self.assertEqual((self.runs("detalle"), self.runs("home")), (["1", "2"], []))


class PrepareSecretsTest(DeviceBase):
    """`requiere_env`: las variables que `preparar` necesita se comprueban antes de empezar y nunca se muestran."""

    def plan_with(self, prepare, env=("PERF_USUARIO", "PERF_CLAVE")):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update({"preparar": prepare, "requiere_env": list(env)})
        self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def test_si_falta_una_variable_se_detiene_antes_de_tocar_el_dispositivo_y_dice_cual(self):
        self.plan_with("true")
        self.env["PERF_USUARIO"] = "usuario.demo"
        self.env.pop("PERF_CLAVE", None)
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("faltan variables de entorno que el flujo 'home' necesita (requiere_env): PERF_CLAVE.", result.stderr)
        self.assertIn("antes de abrir el agente", result.stderr)
        self.assertNotIn("usuario.demo", result.stdout + result.stderr)
        self.assertFalse((self.dir / "adb.log").exists())  # ni calentamiento ni corridas: falla antes de empezar
        self.env["PERF_CLAVE"] = ""  # vacía es lo mismo que no estar
        self.assertEqual(self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba").returncode, 3)

    def test_si_preparar_falla_muestra_su_cola_enmascarada_una_vez_y_deja_el_log(self):
        self.plan_with('echo "escribiendo $PERF_USUARIO con $PERF_CLAVE"; echo "FAILED: no aparece Inicio" >&2; exit 7')
        self.env.update({"PERF_USUARIO": "usuario.demo", "PERF_CLAVE": "clave-de-mentira"})
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "5")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        everything = result.stdout + result.stderr
        self.assertNotIn("clave-de-mentira", everything)
        self.assertNotIn("usuario.demo", everything)
        self.assertEqual(result.stdout.count("✖ 'preparar' falló (código 7). Sus últimas líneas"), 1)
        self.assertIn("    escribiendo *** con ***", result.stdout)
        self.assertIn("    FAILED: no aparece Inicio", result.stdout)
        self.assertEqual(result.stdout.count("inválida: 'preparar' terminó con código 7 (se repite)"), 3)
        log = (self.plan.parent / "logs" / "preparar.log").read_text(encoding="utf-8")
        self.assertEqual(log, "escribiendo *** con ***\nFAILED: no aparece Inicio\n")
        self.assertIn(str(self.plan.parent / "logs" / "preparar.log"), result.stdout)

    def test_un_preparar_que_falla_sin_salida_lo_dice(self):
        self.plan_with("exit 1 > /dev/null 2>&1", env=())
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("✖ 'preparar' falló (código 1) sin dejar salida: si el comando la manda a /dev/null", result.stdout)
        self.assertIn("'preparar' terminó con código 1", result.stderr)

    def test_un_preparar_que_funciona_no_muestra_su_salida(self):
        self.plan_with('echo "tipeando $PERF_CLAVE"')
        self.env.update({"PERF_USUARIO": "usuario.demo", "PERF_CLAVE": "clave-de-mentira"})
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        self.assertNotIn("tipeando", out)
        self.assertNotIn("clave-de-mentira", out)
        self.assertFalse((self.plan.parent / "logs" / "preparar.log").exists())  # si funciona, no queda nada en disco

    def test_sin_requiere_env_la_salida_estandar_se_descarta_como_siempre_y_solo_se_lee_la_de_error(self):
        # lo que el comando escribe ("clave-sin-2") no es el texto del comando, que sí se muestra para correrlo a mano
        self.plan_with('echo "Input text clave-sin-$((1+1))"; echo "no aparece Inicio" >&2; exit 1', env=())
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("    no aparece Inicio", result.stdout)
        self.assertNotIn("clave-sin-2", result.stdout + result.stderr)
        self.assertNotIn("clave-sin-2", (self.plan.parent / "logs" / "preparar.log").read_text(encoding="utf-8"))

    def test_enmascara_primero_el_valor_mas_largo(self):
        os.environ.update({"HBPERF_T1": "abc", "HBPERF_T2": "abc123"})
        try:
            self.assertEqual(perf.mask_secrets("x abc123 y abc z", ["HBPERF_T1", "HBPERF_T2", "HBPERF_NO"]), "x *** y *** z")
            self.assertEqual(perf.missing_env(["HBPERF_T1", "HBPERF_NO"]), ["HBPERF_NO"])
        finally:
            del os.environ["HBPERF_T1"], os.environ["HBPERF_T2"]

    def test_el_plan_valida_requiere_env(self):
        for bad in ("PERF_CLAVE", ["PERF CLAVE"], [1], ["clave=secreta"]):
            plan = json.loads(self.plan.read_text(encoding="utf-8"))
            plan["flujos"]["home"]["requiere_env"] = bad
            self.plan.write_text(json.dumps(plan), encoding="utf-8")
            result = self.perf("siguiente", "--carpeta", self.plan.parent)
            self.assertEqual(result.returncode, 2, str(bad))
            self.assertIn("flujos.home.requiere_env es una lista de nombres de variables de entorno", result.stderr)


UI_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.ejemplo.app" content-desc="" clickable="false" enabled="true" bounds="[0,0][1080,2400]">
    <node text="Catálogo" resource-id="com.ejemplo.app:id/tab_catalogo" class="android.widget.TextView" content-desc="" clickable="true" enabled="true" bounds="[540,2200][1080,2400]" />
    <node text="" resource-id="com.ejemplo.app:id/lista" class="androidx.recyclerview.widget.RecyclerView" content-desc="" clickable="false" enabled="true" bounds="[0,200][1080,1800]">
      <node text="" resource-id="" class="android.view.ViewGroup" content-desc="" clickable="true" enabled="true" bounds="[0,200][1080,400]">
        <node text="Película de prueba uno" resource-id="com.ejemplo.app:id/titulo" class="android.widget.TextView" content-desc="" clickable="false" enabled="true" bounds="[40,220][700,300]" />
      </node>
      <node text="" resource-id="" class="android.view.ViewGroup" content-desc="" clickable="true" enabled="true" bounds="[0,400][1080,600]">
        <node text="Película de prueba dos" resource-id="com.ejemplo.app:id/titulo" class="android.widget.TextView" content-desc="" clickable="false" enabled="true" bounds="[40,420][700,500]" />
      </node>
    </node>
    <node text="" resource-id="com.ejemplo.app:id/fab" class="android.widget.ImageButton" content-desc="Agregar a favoritos" clickable="true" enabled="true" bounds="[800,1900][1040,2140]" />
    <node text="Ver reparto" resource-id="" class="android.widget.Button" content-desc="" clickable="true" enabled="true" bounds="[700,1950][1000,2100]" />
    <node text="Continuar" resource-id="" class="android.widget.Button" content-desc="" clickable="true" enabled="false" bounds="[100,1820][500,1880]" />
    <node text="Estrenos" resource-id="" class="android.widget.TextView" content-desc="" clickable="false" enabled="true" bounds="[40,40][300,120]" />
    <node text="Usuario.demo" resource-id="com.ejemplo.app:id/campo_usuario" class="android.widget.EditText" content-desc="" clickable="true" enabled="true" bounds="[540,40][780,120]" />
    <node text="Fuera de pantalla" resource-id="" class="android.widget.TextView" content-desc="" clickable="true" enabled="true" bounds="[0,0][0,0]" />
  </node>
</hierarchy>
"""


class NodesTest(DeviceBase):
    """`perf.py nodos`: del volcado de uiautomator al centro de los bounds, con los avisos que evitan un toque equivocado."""

    def setUp(self):
        super().setUp()
        self.xml = self.dir / "ui.xml"
        write(self.xml, UI_XML)

    def test_busca_por_texto_id_o_descripcion_y_da_el_centro_como_comando(self):
        out = self.ok("nodos", self.xml, "--texto", "película de prueba uno")
        self.assertIn('1. "Película de prueba uno" · id titulo · TextView · bounds [40,220][700,300]', out)
        self.assertIn("Toque (centro): adb shell input tap 370 260", out)
        self.assertNotIn("⚠", out)  # su contenedor es clickeable y nada más recibe ese punto
        out = self.ok("nodos", self.xml, "--id", "tab_catalogo", "--serial", "emulator-5554")
        self.assertIn("Toque (centro): adb -s emulator-5554 shell input tap 810 2300", out)
        self.assertIn("tap 810 2300", self.ok("nodos", self.xml, "--id", "com.ejemplo.app:id/tab_catalogo", "--exacto"))
        self.assertIn("tap 920 2020", self.ok("nodos", self.xml, "--desc", "favoritos"))

    def test_varios_nodos_que_coinciden_se_listan_y_exacto_o_limite_los_acotan(self):
        out = self.ok("nodos", self.xml, "--texto", "Película de prueba")
        self.assertIn("2 nodos coinciden", out)
        self.assertIn("tap 370 260", out)
        self.assertIn("tap 370 460", out)
        out = self.ok("nodos", self.xml, "--id", "titulo", "--limite", "1")
        self.assertIn("… 1 más (sube --limite)", out)
        self.assertNotIn("2. ", out)
        out = self.ok("nodos", self.xml, "--texto", "Película de prueba dos", "--exacto", "--id", "titulo")
        self.assertNotIn("nodos coinciden", out)
        self.assertIn("tap 370 460", out)

    def test_avisa_si_el_centro_cae_en_otro_nodo_clickeable_si_esta_deshabilitado_o_no_es_clickeable(self):
        out = self.ok("nodos", self.xml, "--texto", "Ver reparto")
        self.assertIn("tap 850 2025", out)
        self.assertIn('⚠ el centro también cae dentro de otro nodo clickeable (desc "Agregar a favoritos" · id fab · ImageButton, '
                      "bounds [800,1900][1040,2140])", out)
        self.assertIn("⚠ el nodo está deshabilitado", self.ok("nodos", self.xml, "--texto", "Continuar"))
        self.assertIn("⚠ ni el nodo ni sus contenedores son clickeables", self.ok("nodos", self.xml, "--texto", "Estrenos"))
        out = self.ok("nodos", self.xml, "--texto", "Fuera de pantalla")
        self.assertIn("⚠ sin bounds visibles", out)
        self.assertNotIn("Toque", out)

    def test_avisa_si_la_pantalla_todavia_muestra_un_cargando(self):
        self.assertNotIn("cargando", self.ok("nodos", self.xml, "--texto", "Estrenos"))
        for loading in ('<node text="" resource-id="" class="android.widget.ProgressBar" content-desc="" bounds="[490,1100][590,1200]" />',
                        '<node text="" resource-id="com.ejemplo.app:id/shimmer_lista" class="android.view.View" bounds="[0,200][1080,900]" />',
                        '<node text="Cargando…" resource-id="" class="android.widget.TextView" bounds="[0,200][1080,300]" />'):
            write(self.xml, UI_XML.replace("  </node>\n</hierarchy>", "    %s\n  </node>\n</hierarchy>" % loading))
            out = self.ok("nodos", self.xml, "--texto", "Estrenos")
            self.assertIn("⚠ La pantalla todavía muestra un cargando", out, loading)
            self.assertIn("vuelve a volcar", out)
        hidden = '<node text="" class="android.widget.ProgressBar" bounds="[0,0][0,0]" />'  # sin tamaño: no está a la vista
        write(self.xml, UI_XML.replace("  </node>\n</hierarchy>", "    %s\n  </node>\n</hierarchy>" % hidden))
        self.assertNotIn("cargando", self.ok("nodos", self.xml, "--texto", "Estrenos"))

    def test_sin_coincidencias_dice_lo_que_hay_a_la_vista_y_exige_un_criterio(self):
        result = self.perf("nodos", self.xml, "--texto", "Reproducir")
        self.assertEqual(result.returncode, 2)
        self.assertIn('ningún nodo coincide', result.stderr)
        self.assertIn('A la vista: "Catálogo", "Película de prueba uno"', result.stderr)
        result = self.perf("nodos", self.xml)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--texto, --id o --desc", result.stderr)
        write(self.xml, "esto no es xml")
        result = self.perf("nodos", self.xml, "--texto", "x")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no es un volcado de uiautomator", result.stderr)
        self.assertEqual(self.perf("nodos", self.dir / "no-existe.xml", "--texto", "x").returncode, 2)

    def test_exacto_distingue_mayusculas_para_comprobar_lo_que_se_escribio(self):
        self.assertIn("tap 660 80", self.ok("nodos", self.xml, "--texto", "usuario.demo"))  # contiene, sin distinguir
        result = self.perf("nodos", self.xml, "--texto", "usuario.demo", "--exacto")
        self.assertEqual(result.returncode, 2)  # en pantalla dice "Usuario.demo": el teclado puso la mayúscula
        self.assertIn('"Usuario.demo"', result.stderr)

    def test_un_volcado_que_falla_no_deja_leer_el_de_la_pantalla_anterior(self):
        target = self.dir / "inv" / "logs" / "ui.xml"
        write(target, UI_XML)  # el volcado de la pantalla anterior, todavía en disco
        self.env["FAKE_PULL_FALLA"] = "1"
        result = self.perf("nodos", target, "--volcar", "--texto", "Catálogo")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("no se pudo volcar la pantalla con uiautomator", result.stderr)
        self.assertIn("could not get idle state", result.stderr)
        self.assertNotIn("Toque", result.stdout)
        self.assertFalse(target.exists())
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertLess(log.index("rm -f /sdcard/hbperf-ui.xml"), log.index("uiautomator dump /sdcard/hbperf-ui.xml"))

    def test_volcar_toma_la_pantalla_del_dispositivo_antes_de_buscar(self):
        self.env["FAKE_PULL"] = UI_XML
        target = self.dir / "inv" / "logs" / "ui.xml"
        out = self.ok("nodos", target, "--volcar", "--texto", "Catálogo")
        self.assertIn("Toque (centro): adb -s emulator-5554 shell input tap 810 2300", out)
        self.assertTrue(target.is_file())
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("uiautomator dump /sdcard/hbperf-ui.xml", log)
        self.assertIn('"pull", "/sdcard/hbperf-ui.xml"', log)


class NoImprovementsTest(PerfBase):
    """Con el reporte inicial entregado y sin mejoras, `siguiente` ofrece el cierre: nunca repite la sesión 2."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = {"paquete": PKG, "principales": ["ttid_ms"], "flujos": {"arranque-frio": {
            "recorrido": {"tipo": "arranque-frio", "actividad": PKG + "/.Main", "espera_s": 5}}}, "mejoras": []}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        write(self.folder / "fases.json", json.dumps({n: {"fecha": "2026-11-05"} for n in ("antes", "control")}))
        write(self.folder / "diagnostico.md", "x")

    def test_antes_del_reporte_inicial_toca_la_sesion_2_y_despues_el_cierre_corto(self):
        self.assertEqual(perf.next_steps(self.folder, self.plan)[0], "sesión 2 · diagnóstico")
        write(self.folder / "reporte-inicial.md", "x")
        title, steps = perf.next_steps(self.folder, self.plan)
        self.assertEqual(title, "sesión 4 · cierre sin mejoras")
        self.assertEqual([s["tipo"] for s in steps], ["chat"])
        self.assertEqual((steps[0]["modelo"], steps[0]["esfuerzo"]), ("Haiku 5.5", "bajo"))
        self.assertTrue(steps[0]["texto"].endswith("estado.md: cierra la investigación sin fase después. No hagas commit ni push."))
        self.assertIn("sesión 4 corta", steps[0]["que"])
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Siguiente · sesión 4 · cierre sin mejoras", out)
        self.assertNotIn("sesión 2", out[out.index("Siguiente ·"):])
        self.assertIn('--costo "<lo que muestre tu herramienta>"', out)
        write(self.folder / "reporte-final.md", "x")
        self.assertEqual(perf.next_steps(self.folder, self.plan)[0], "investigación cerrada")

    def test_una_captura_pendiente_de_estado_md_sale_como_comando_antes_del_cierre(self):
        write(self.folder / "reporte-inicial.md", "x")
        state = self.folder / "estado.md"
        text = state.read_text(encoding="utf-8")
        pendientes = "## Pendientes\n\n- **H2** · frame largo al cerrar el detalle, estable · falta saber qué función lo ocupa · una corrida · " \
                     "Captura pendiente: `capturar --plan inv/plan.json --prueba --config cpu`\n" \
                     "- Captura pendiente: `<comando sin completar>`\n"
        state.write_text(re.sub(r"## Pendientes\n.*?(?=\n## )", lambda m: pendientes, text, flags=re.S), encoding="utf-8")
        title, steps = perf.next_steps(self.folder, self.plan)
        self.assertEqual(title, "sesión 4 · cierre sin mejoras")
        self.assertEqual([s["tipo"] for s in steps], ["terminal", "chat"])
        self.assertRegex(steps[0]["texto"], r"^cd .* && python3 -I .*perf\.py capturar --plan inv/plan\.json --prueba --config cpu$")
        self.assertIn("opcional", steps[0]["que"])
        self.assertEqual(perf.pending_captures(self.folder / "no-existe.md"), [])
        template = perf.DEVICE_PLACEHOLDER  # una línea que sigue con relleno de la plantilla no es una captura pendiente
        state.write_text(state.read_text(encoding="utf-8") + "- %s Captura pendiente: `capturar --plan x`\n" % template,
                         encoding="utf-8")
        self.assertEqual(perf.pending_captures(state), ["capturar --plan inv/plan.json --prueba --config cpu"])
        expected = steps[0]["texto"]
        for other in ("consulta inv/prueba/x_1.perfetto-trace.gz cpu_por_libreria", "perf.py diagnostico --carpeta inv"):
            state.write_text(state.read_text(encoding="utf-8").replace(
                "`capturar --plan inv/plan.json --prueba --config cpu`", "`%s`" % other), encoding="utf-8")
            self.assertRegex(perf.next_steps(self.folder, self.plan)[1][0]["texto"],
                             r"^cd .* && python3 -I .*perf\.py %s$" % re.escape(other.replace("perf.py ", "")))
            state.write_text(state.read_text(encoding="utf-8").replace("`%s`" % other,
                             "`capturar --plan inv/plan.json --prueba --config cpu`"), encoding="utf-8")
        for written in ("perf.py capturar --plan inv/plan.json --prueba --config cpu",
                        "python3 -I <skill>/scripts/perf.py capturar --plan inv/plan.json --prueba --config cpu".replace("<skill>", "x")):
            state.write_text(state.read_text(encoding="utf-8").replace(
                "`capturar --plan inv/plan.json --prueba --config cpu`", "`%s`" % written), encoding="utf-8")
            self.assertEqual(perf.next_steps(self.folder, self.plan)[1][0]["texto"], expected, written)
            state.write_text(state.read_text(encoding="utf-8").replace("`%s`" % written,
                             "`capturar --plan inv/plan.json --prueba --config cpu`"), encoding="utf-8")

    def test_con_mejoras_el_camino_no_cambia(self):
        write(self.folder / "reporte-inicial.md", "x")
        self.plan["mejoras"] = [{"id": "M1", "titulo": "a"}]
        self.assertEqual(perf.next_steps(self.folder, self.plan)[0], "decisión del usuario (sin chat)")
        self.plan["mejoras"][0]["estado"] = "descartada"
        self.assertEqual(perf.next_steps(self.folder, self.plan)[0], "sesión 4 · cierre sin mejoras aplicadas")


class SmokeNextStepTest(DeviceBase):
    """`humo` termina con el chat de la sesión 1 del flujo que se pidió en el setup, no con la receta del arranque."""

    def request(self, **data):
        write(self.dir / "reports/perf/setup/pedido.json", json.dumps(data, ensure_ascii=False))

    def test_con_el_pedido_guardado_imprime_el_prompt_exacto_de_la_sesion_1(self):
        self.request(flujo="de la lista de películas al detalle de la primera, hasta ver el reparto.", llegar="")
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG, "--instalar", "./gradlew app:installProfiling")
        self.assertIn("Siguiente · sesión 1 (ficha y plan) del flujo que pediste en el setup · Chat nuevo · Modelo: Sonnet 5.5 · "
                      "Esfuerzo: medio", out)
        self.assertIn('Texto: "Usa hb-performance: medir de la lista de películas al detalle de la primera, hasta ver el '
                      'reparto. Dispositivo emulator-5554. No hagas commit ni push."', out)
        self.assertIn("ábrelo en un chat nuevo, no en el del setup", out)
        recipe = out.index("Solo si lo que quieres medir es el arranque en frío (receta, sin sesión 1) · Terminal (sin chat):")
        self.assertLess(out.index("Siguiente · sesión 1"), recipe)
        self.assertIn("nuevo --receta arranque-frio --paquete %s" % PKG, out[recipe:])
        self.assertNotIn("Maestro", out)

    def test_si_hay_login_o_pantallas_antes_usa_el_prompt_de_flujo_largo(self):
        self.request(flujo="de la lista al detalle", llegar="iniciar sesión, aceptar términos e ir al tab Catálogo")
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        self.assertIn('Texto: "Usa hb-performance: medir de la lista al detalle. Para llegar ahí hay que iniciar sesión, aceptar '
                      'términos e ir al tab Catálogo. Dispositivo emulator-5554. No hagas commit ni push."', out)
        self.assertNotIn("Maestro", out)  # el prompt no fija cómo se recorre: lo pregunta la sesión 1

    def test_un_pedido_mal_formado_se_ignora_con_aviso_y_la_ruta_se_puede_cambiar(self):
        write(self.dir / "reports/perf/setup/pedido.json", '{"flujo": ""}')
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        self.assertIn('⚠ reports/perf/setup/pedido.json no tiene la forma {"flujo": "...", "llegar": "..."}', out)
        self.assertIn("Siguiente, según lo que se va a investigar:", out)
        write(self.dir / "reports/perf/setup/pedido.json", "esto no es JSON")
        self.assertIn("pedido.json no tiene la forma", self.ok("humo", "--paquete", PKG, "--carpeta", self.dir / "h3"))
        (self.dir / "reports/perf/setup/pedido.json").write_bytes(b"\xff\xfe no es UTF-8")
        self.assertIn("pedido.json no tiene la forma", self.ok("humo", "--paquete", PKG, "--carpeta", self.dir / "h4"))
        write(self.dir / "otro.json", json.dumps({"flujo": "abrir el buscador"}))
        out = self.ok("humo", "--paquete", PKG, "--pedido", self.dir / "otro.json", "--carpeta", self.dir / "h2")
        self.assertIn("medir abrir el buscador. Dispositivo", out)
        self.assertEqual(perf.read_request(self.dir / "no-existe.json"), None)


class RouteFileTest(DeviceBase):
    """El recorrido vive en un archivo comentado y `estado.md` dice cómo se recorre."""

    def test_nuevo_deja_recorrido_sh_ejecutable_con_el_flujo_y_el_serial(self):
        folder = self.dir / "reports" / "perf" / "detalle"
        out = self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "detalle", "--serial", "emulator-5554")
        route = folder / "recorrido.sh"
        self.assertTrue(os.access(str(route), os.X_OK))
        text = route.read_text(encoding="utf-8")
        self.assertIn('Recorrido medido del flujo "detalle"', text)
        self.assertIn('SERIAL="${ANDROID_SERIAL:-emulator-5554}"', text)
        self.assertIn("# Paso 1:", text)
        self.assertNotIn("{{", text)
        self.assertIn('"recorrido": "bash %s"' % route, out)
        self.assertEqual(subprocess.run(["bash", "-n", str(route)]).returncode, 0)  # el esqueleto es bash válido
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["flujos"]["detalle"]["recorrido"], "manual")  # hasta que la ficha elija el recorrido
        startup = self.dir / "arranque"
        self.ok("nuevo", "--carpeta", startup, "--paquete", PKG, "--receta", "arranque-frio")
        self.assertFalse((startup / "recorrido.sh").exists())
        reused = self.dir / "reutilizado"
        write(reused / "recorrido.sh", "# el recorrido archivado de otra investigación\n")
        out = self.ok("nuevo", "--carpeta", reused, "--paquete", PKG, "--flujo", "detalle")
        self.assertIn("recorrido.sh ya existe, no se toca", out)
        self.assertEqual((reused / "recorrido.sh").read_text(encoding="utf-8"), "# el recorrido archivado de otra investigación\n")

    def test_estado_dice_como_se_recorre_cada_flujo_y_como_verlo_a_mano(self):
        folder = self.dir / "ruta"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "detalle")
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["flujos"]["detalle"].update({"preparar": "bash inv/preparar.sh", "recorrido": "bash inv/recorrido.sh",
                                          "requiere_env": ["PERF_CLAVE"]})
        plan["flujos"]["lista"] = {"recorrido": "manual"}
        plan["flujos"]["inicio"] = {"recorrido": {"tipo": "arranque-frio", "actividad": "", "espera_s": 5}}
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self.ok("siguiente", "--carpeta", folder)
        state = (folder / "estado.md").read_text(encoding="utf-8")
        block = state[state.index("<!-- perf:recorrido -->"):state.index("<!-- /perf:recorrido -->")]
        self.assertIn("**detalle**\n- `preparar` (antes de cada corrida, fuera de la traza): `bash inv/preparar.sh`\n"
                      "- `recorrido` (el tramo medido): `bash inv/recorrido.sh`\n", block)
        self.assertRegex(block, r"- Para verlo correr a mano, sin medir: `cd \S+ && bash inv/preparar\.sh && bash inv/recorrido\.sh`")
        self.assertIn("- Variables de entorno que necesita (expórtalas antes): `PERF_CLAVE`", block)
        self.assertIn("**lista**\n- `preparar` (antes de cada corrida, fuera de la traza): no tiene\n- `recorrido`: manual", block)
        self.assertIn("**inicio**", block)
        self.assertIn("arranque en frío", block)
        self.assertIn("archívalos fuera de `reports/`", block)
        self.assertIn("## Cambios temporales por revertir", state)

    def test_un_comando_con_acento_grave_no_rompe_el_markdown(self):
        self.assertEqual(perf.code_span("adb shell input tap 1 2"), "`adb shell input tap 1 2`")
        self.assertEqual(perf.code_span("echo `date`"), "`` echo `date` ``")

    def test_un_estado_sin_la_seccion_como_el_de_una_version_anterior_no_falla(self):
        folder = self.dir / "inv"
        write(folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {"recorrido": "true"}}}))
        write(folder / "estado.md", "# Rendimiento · X · 2026-11-01\n\n## Siguiente paso\n\n- x\n\n## Ficha\n\n| Campo | Valor |\n")
        self.ok("siguiente", "--carpeta", folder)
        self.assertNotIn("Cómo se recorre", (folder / "estado.md").read_text(encoding="utf-8"))


class UnfilledTemplateTest(DeviceBase):
    """`reporte` y `siguiente` avisan de lo que sigue con el texto de la plantilla y no lo publican."""

    def new(self, *extra):
        folder = self.dir / "reports" / "perf" / "x"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "x", *extra)
        return folder

    def test_siguiente_avisa_de_las_filas_de_la_ficha_sin_completar_y_despues_del_reporte_tambien_del_resumen(self):
        folder = self.new()
        out = self.ok("siguiente", "--carpeta", folder)
        self.assertIn("tiene partes sin completar: Ficha (Síntoma, Métricas principales y objetivo, Build y ambiente, "
                      "Modos).", out)  # Stack también está sin llenar, pero no va al reporte
        self.assertNotIn("Resumen ejecutivo", out)  # todavía no toca: lo escribe la sesión 2
        state = folder / "estado.md"
        text = state.read_text(encoding="utf-8")
        for marker in perf.TEMPLATE_MARKER.findall(text[text.index("## Ficha"):text.index("## Cómo se recorre")]):
            text = text.replace(marker, "listo")
        state.write_text(text, encoding="utf-8")
        self.assertNotIn("sin completar", self.ok("siguiente", "--carpeta", folder))
        write(folder / "reporte-inicial.md", "x")
        out = self.ok("siguiente", "--carpeta", folder)
        self.assertIn("tiene partes sin completar: Resumen ejecutivo (de 3 a 5 líneas); Hallazgos (la tabla está vacía).", out)
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"] = [{"id": "M1", "titulo": "a", "estado": "aprobada"}]
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self.assertNotIn("sin completar", self.ok("siguiente", "--carpeta", folder))  # en la sesión 3 todavía no toca

    def test_el_reporte_no_publica_el_texto_de_la_plantilla(self):
        folder = self.new()
        state = folder / "estado.md"
        text = state.read_text(encoding="utf-8").replace('<lo que nota el usuario, o "exploratoria">', "El detalle tarda")
        text = text.replace("| --- | --- | --- | --- | --- | --- |\n",
                            "| --- | --- | --- | --- | --- | --- |\n| H1 | Frame largo | 48 ms | — | sin confirmar | "
                            "<3 a 5 líneas. Para el reporte inicial (sesión 2): qué se midió, qué se encontró y qué se "
                            "propone, o por qué no hay mejoras. Para el final (sesión 4): estado inicial → estado final con "
                            "las métricas principales, la causa en una frase y qué depende del backend> |\n", 1)
        state.write_text(text, encoding="utf-8")
        out = self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
        self.assertIn("tiene partes sin completar: Ficha (Métricas principales y objetivo, Build y ambiente, Modos); "
                      "Resumen ejecutivo", out)
        self.assertIn("Hallazgos (H1)", out)
        for name in ("reporte-inicial.md", "reporte-inicial.html"):
            report = (folder / name).read_text(encoding="utf-8")
            self.assertNotIn("3 a 5 líneas", report, name)
            self.assertNotIn("guiado o autónomo", report, name)
            self.assertNotIn("backend real o mocks", report, name)
            self.assertNotIn("qué falta para cerrarlo", report, name)  # el renglón de ejemplo de Pendientes
        md = (folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertNotIn("## Resumen\n", md)  # sin resumen escrito, la sección se omite
        self.assertNotIn("## Pendientes", md)
        self.assertIn("| Síntoma | El detalle tarda |", md)
        self.assertIn("| Modos | sin completar |", md)
        self.assertIn("| Build y ambiente | sin completar |", md)
        self.assertIn("| H1 | Frame largo | 48 ms | — | sin confirmar | sin completar |", md)
        self.ok("reporte", "--carpeta", folder)
        final = (folder / "reporte-final.md").read_text(encoding="utf-8")
        for leftover in ("3 a 5 líneas", "qué dice cada métrica principal", "test que la fija", "guiado o autónomo"):
            self.assertNotIn(leftover, final)
        self.assertNotIn("## Resumen ejecutivo", final)
        self.assertNotIn("## Mejoras aplicadas", final)
        self.assertNotIn("## Lectura de la comparación", final)

    def test_un_texto_entre_angulos_que_no_es_de_la_plantilla_se_publica(self):
        folder = self.dir / "inv2"
        write(folder / "estado.md", "# Rendimiento · <Home> · 2026-01-02\n\n## Resumen ejecutivo\n\nLa lista usa List<Item> y "
                                    "<carpeta> propia.\n\n## Hallazgos\n\n| # | Síntoma | Tipo |\n| --- | --- | --- |\n"
                                    "| H1 | Doble <carga> en <profileable> | bug |\n")
        out = self.ok("reporte", "--carpeta", folder, "--inicial")
        self.assertNotIn("sin completar", out)
        md = (folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("La lista usa List<Item> y <carpeta> propia.", md)
        self.assertIn("| H1 | Doble <carga> en <profileable> | bug |", md)

    def test_con_la_receta_de_arranque_la_ficha_sale_completa_porque_no_hay_sesion_1(self):
        folder = self.dir / "arranque"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--receta", "arranque-frio", "--red", "--triage")
        state = (folder / "estado.md").read_text(encoding="utf-8")
        sections = perf.state_sections(state)[1]
        self.assertEqual(perf.unfilled_parts(sections), [])  # el Stack lo ve la sesión 2 y no va al reporte
        self.assertEqual(perf.ficha_subset(sections["ficha"]).count(perf.UNFILLED), 0)
        self.assertIn("| Modos | guiado · recorrido arranque-frio · triage |", state)
        self.assertIn("| Síntoma | exploratoria (receta de arranque en frío) |", state)
        self.assertIn("· la primera pantalla carga de la red |", state)

    def test_los_marcadores_salen_de_la_plantilla_y_los_de_una_palabra_no_cuentan(self):
        self.assertTrue(perf.has_placeholder("| Stack | <UI · asincronía · listas · red> |"))
        self.assertTrue(perf.has_placeholder("| Modos | guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage |"))
        self.assertTrue(perf.has_placeholder("| Dispositivo | <modelo · Android · Hz> |"))
        self.assertFalse(perf.has_placeholder("usa <carpeta>/plan.json y List<Item>"))
        # los rellenos de 0.6.0 sin <> y <alcance> solo cuentan si son la celda entera: con datos agregados es contenido real
        self.assertTrue(perf.has_placeholder("| Alcance | <alcance> |"))
        self.assertFalse(perf.has_placeholder("| Alcance | el <alcance> del pedido |"))
        self.assertFalse(perf.has_placeholder("| Métricas principales y objetivo | las de `principales` en plan.json, y el "
                                              "objetivo: `ttid_ms` ≤ 500 ms |"))
        self.assertEqual(perf.without_placeholders("Texto real.\n- <M1 · archivos · test que la fija · DoD · commit propuesto: "
                                                   "perf(alcance): ...>\nOtra línea."), "Texto real.\nOtra línea.")


class ResultBoxTest(PerfBase):
    """El reporte inicial abre con el recuadro "Resultado": las mejoras, o por qué no hay ninguna."""

    HEAD = "# Rendimiento · Detalle · 2026-11-09\n\n## Resumen ejecutivo\n\nTexto.\n\n## Hallazgos\n\n"

    def report(self, table, mejoras):
        folder = self.dir / "inv"
        write(folder / "estado.md", self.HEAD + table + "\n## Pendientes\n\n- **H2** · frame largo, estable en 10 corridas · "
                                                        "falta saber qué función lo ocupa · una captura con muestreo · medirla\n")
        write(folder / "plan.json", json.dumps({"paquete": PKG, "principales": ["carga_ms"], "flujos": {"f": {}},
                                                "mejoras": mejoras}))
        self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
        return (folder / "reporte-inicial.md").read_text(encoding="utf-8"), \
            (folder / "reporte-inicial.html").read_text(encoding="utf-8")

    def test_sin_mejoras_dice_por_que_con_una_linea_por_hallazgo(self):
        table = "| # | Síntoma | Evidencia | Causa raíz | Tipo | Qué falta para decidir |\n| --- | --- | --- | --- | --- | --- |\n" \
                "| H1 | Jank en la lista | 2 % | El camino lento no corrió: 0 slices | descartado | — |\n" \
                "| H2 | Frame largo al cerrar el detalle | 37 ms en 10 corridas | sin probar | sin confirmar | una captura con muestreo de CPU |\n" \
                "| H3 | Red solapada | n=3 | — | sin veredicto estadístico | |\n"
        md, page = self.report(table, [])
        self.assertTrue(md.index("## Resultado") < md.index("## Resumen") < md.index("## Hallazgos"))
        self.assertIn("**Sin mejoras aplicables.** 3 hallazgos (`descartado`: 1, `sin confirmar`: 2). Por qué, uno por uno:", md)
        self.assertIn("- **H1** · Jank en la lista · `descartado` · El camino lento no corrió: 0 slices", md)
        self.assertIn("- **H2** · Frame largo al cerrar el detalle · `sin confirmar` · falta: una captura con muestreo de CPU", md)
        self.assertIn("- **H3** · Red solapada · `sin confirmar` · no se pudo confirmar ni descartar con estos datos; sin acción", md)
        self.assertIn('<section id="s0" class="resultado"><h2>Resultado</h2>', page)
        self.assertIn("section.resultado", page)
        # la columna opcional se conserva en la tabla de hallazgos, y el rótulo anterior se sigue leyendo
        self.assertIn("| # | Síntoma | Evidencia | Causa raíz | Tipo | Qué falta para decidir | Qué pasa con él |", md)
        self.assertIn("| sin confirmar | una captura con muestreo de CPU | no se pudo confirmar ni descartar con estos datos; "
                      "sin acción |", md)
        self.assertIn("| H3 | Red solapada | n=3 | — | sin veredicto estadístico | — | no se pudo confirmar ni descartar", md)
        self.assertIn("## Pendientes (no son mejoras)", md)
        self.assertNotIn("Queda abierto", md)
        self.assertIn("qué falta para cerrarlo, cuánto cuesta y la acción sugerida", md)
        self.assertIn("`sin confirmar` no quiere decir que falten trazas ni que la captura fallara", md)  # el glosario

    def test_con_mejoras_dice_cuantas_y_cuales(self):
        table = "| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n" \
                "| H1 | Carga lenta | 131 ms | Red en el hilo | bug |\n| H2 | Frame largo | 37 ms | sin probar | sin confirmar |\n"
        md, _ = self.report(table, [
            {"id": "M1", "titulo": "Caché", "hallazgo": "H1", "metrica": "carga_ms", "esperado": "-30 %"},
            {"id": "M2", "titulo": "Decodificar la imagen fuera del hilo principal", "hallazgo": "H2", "a_prueba": True, "hipotesis": "es la imagen de cabecera",
             "metrica": "detalle hilo_max_ms", "esperado": "≤ 16 ms"}])
        self.assertIn("## Resultado\n\n**2 mejoras propuestas** para 2 hallazgos (1 a prueba: la causa no está probada y la "
                      "medición de después la confirma o la refuta). Tú decides cuáles se aplican.", md)
        self.assertIn("- **M1** · Caché · ataca H1 · mide `carga_ms` · esperado: -30 %", md)
        self.assertIn("- **M2** · Decodificar la imagen fuera del hilo principal (a prueba) · ataca H2 · mide `detalle hilo_max_ms` · esperado: ≤ 16 ms", md)
        self.assertIn("| H1 | Carga lenta | 131 ms | Red en el hilo | bug | M1 (propuesta) |", md)  # tabla de 0.6.0: igual que antes

    def test_sin_tabla_de_hallazgos_lo_dice(self):
        self.assertEqual(perf.result_md("", {"mejoras": []}),
                         "**Sin mejoras aplicables.** El diagnóstico no dejó hallazgos en `estado.md`.")
        self.assertEqual(perf.finding_kind("Sin veredicto estadístico"), "sin confirmar")
        self.assertEqual(perf.finding_kind("consecuencia de H1"), "consecuencia")
        self.assertEqual(perf.finding_kind(""), "sin tipo")
        self.assertIn("**1 mejora propuesta**. Tú decides", perf.result_md("", {"mejoras": [{"id": "M1", "titulo": "a"}]}))
        untyped = "| # | Síntoma |\n| --- | --- |\n| H1 | Carga lenta |\n"  # una tabla sin la columna Tipo
        raw = perf.findings_md(untyped + "| H2 | %s |\n" % perf.DEVICE_PLACEHOLDER, {"mejoras": []})
        self.assertIn("| H1 | Carga lenta |", raw)
        self.assertNotIn("H2", raw)  # sin columna Tipo la tabla sale tal cual, menos las filas con relleno
        self.assertIn("**Sin mejoras aplicables.** 1 hallazgo (`sin tipo`: 1).", perf.result_md(untyped, {"mejoras": []}))
        self.assertIn("- **H1** · Carga lenta · `sin tipo` · sin mejora asociada", perf.result_md(untyped, {"mejoras": []}))


FIXTURE_060 = ROOT / "tests" / "fixtures" / "hb-performance-0.6.0"


class Compat060Test(PerfBase):
    """Una investigación en curso creada con 0.6.0 (plan.json, estado.md y fases.json de esa versión) sigue funcionando."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "reports" / "perf" / "detalle"
        self.folder.mkdir(parents=True)
        for name in ("plan.json", "estado.md", "metricas.csv", "fases.json"):
            write(self.folder / name, (FIXTURE_060 / name).read_text(encoding="utf-8"))

    def test_el_plan_de_0_6_0_no_trae_ningun_campo_nuevo_y_carga_igual(self):
        plan = perf.load_plan(self.folder / "plan.json")
        text = json.dumps(plan)
        for field in ("segmentos", "a_prueba", "hipotesis", "requiere_env", "input_slices"):
            self.assertNotIn(field, text)
        self.assertEqual(perf.user_metric_names(plan), ["lista_a_detalle_ms"])

    def test_siguiente_reporte_inicial_y_comparar_corren_sin_errores(self):
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Siguiente · sesión 4 · cierre", out)  # mejora aplicada y fase después medida
        self.assertIn("Ficha (Métricas principales y objetivo, Build y ambiente, Modos)", out)  # relleno de 0.6.0
        self.assertNotIn("Resumen ejecutivo", out)  # hay una mejora aplicada: el resumen es del cierre, todavía no toca
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        initial = (self.folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("| H2 | Frame largo al entrar | 48 ms en la corrida mediana · `hilo_principal_top` | — | sin veredicto "
                      "estadístico | no se pudo confirmar ni descartar con estos datos; sin acción |", initial)
        self.assertIn("| H3 | Jank en la lista | `jank_app_pct` 2 % | — | descartado | descartado: se investigó y no es la causa", initial)
        self.assertIn("| M1 | Una sola carga del detalle | H1 | red_solapadas | 1 llamadas | 0 llamadas | alta | bajo | bajo | "
                      "aplicada |", initial)
        self.assertIn("- **H2** · causa sin verificar · falta una captura con muestreo de CPU", initial)
        self.assertNotIn("<3 a 5 líneas", initial)
        self.assertNotIn("backend real o mocks", initial)
        out = self.ok("comparar", self.folder / "metricas.csv")
        self.assertIn("| detalle | lista_a_detalle_ms | e2e | 412 ms / 420 ms | 300 ms / 305 ms | -112 ms | -27.18 % | 0.24 % | "
                      "mejora |", out)
        self.assertIn("| detalle | red_solapadas | app | 1 llamadas / 1 llamadas | 0 llamadas / 0 llamadas | -1 llamadas | "
                      "-100 % | 0 % | mejora |", out)
        self.assertIn("| detalle | hilo_max_ms | app | 48 ms / 50 ms | 48 ms / 49 ms | 0 ms | 0 % | 0 % | sin cambio |", out)
        self.assertNotIn("⚠", out)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("| M1 | Una sola carga del detalle | red_solapadas | 1 llamadas | 0 llamadas | 0 llamadas | -100 % | mejora | "
                      "aplicada | ✔ funcionó |", state)
        self.assertNotIn("Cómo se recorre", state)  # el estado de 0.6.0 no tiene esa sección: no se agrega ni falla
        self.ok("reporte", "--carpeta", self.folder, "--html")
        final = (self.folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("3 hallazgos → 1 mejoras propuestas → 1 aplicadas → 1 funcionaron", final)
        for filler in ("test que la fija", "qué dice cada métrica principal", "3 a 5 líneas", "backend real o mocks"):
            self.assertNotIn(filler, final)  # el relleno de la plantilla de 0.6.0 tampoco llega al reporte final
        self.assertEqual(perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))[0], "investigación cerrada")

    def test_las_fases_de_0_6_0_sin_datos_por_flujo_se_leen_igual(self):
        phases = perf.read_phases(self.folder)
        self.assertNotIn("flujos", phases["antes"])
        self.assertEqual(perf.frames_trust(self.folder), ("ok", ""))
        self.assertEqual(perf.phase_warnings(self.folder), [])
        table, notes = perf.builds_table(self.folder)
        self.assertIn("| antes | 2026-01-15T10:00:00 | abc1234 | 1.0 (7) | 2026-01-15 09:00:00 | 60 | completa (speed) | 5 |", table)
        self.assertEqual(notes, [])


GRADLE_PROFILEABLE = """
plugins { id("com.android.application") }
android {
    buildTypes {
        release { isMinifyEnabled = true }
        create("demo") {
            initWith(getByName("release"))
            isProfileable = true
            signingConfig = signingConfigs.getByName("debug")
        }
        create("interno") {
            initWith(getByName("debug"))
            isProfileable = true
        }
    }
}
"""


class SetupDetectionTest(PerfBase):
    """Lo que `instrumentar` mira antes de proponer el build de medición."""

    def module(self, gradle=GRADLE_KTS, **files):
        module = self.dir / "app"
        write(module / "build.gradle.kts", gradle)
        for path, text in files.items():
            write(module / path, text)
        return module

    def instrument(self, module, *extra):
        return self.perf("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf", "--sin-fragments", *extra)

    def test_una_variante_profileable_declarada_en_gradle_se_reutiliza_aunque_su_manifest_no_lo_diga(self):
        module = self.module(GRADLE_PROFILEABLE)
        found = {c["nombre"]: c for c in perf.find_profileable_variants(module, self.dir, [])}
        self.assertEqual({name: c["estado"] for name, c in found.items()}, {"demo": "ok", "interno": "depurable"})
        self.assertTrue(found["demo"]["gradle"])
        out = self.instrument(module).stdout
        self.assertIn("Variante: demo (existente: profileable y no depurable, no se crea otro build type)", out)
        self.assertIn("interno también declara que es profileable pero es depurable: no se usa", out)
        self.assertNotIn('create("profiling")', out)
        manifest = (module / "src/demo/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:name="com.ejemplo.perf.PerfInstaller"', manifest)
        self.assertNotIn("<profileable", manifest)  # Gradle ya lo declara: el manifest solo lleva el provider
        self.assertFalse((module / "src/profiling").exists())

    def test_un_build_type_que_solo_es_profileable_con_una_propiedad_no_es_una_variante_existente(self):
        # el fragmento "-Pperf" ya pegado: sin la propiedad, qa no es profileable ni lleva la instrumentación
        gradle = """
val perf = providers.gradleProperty("perf").isPresent
android {
    buildTypes {
        release { isMinifyEnabled = true }
        create("qa") {
            initWith(getByName("release"))
            if (perf) {
                isDebuggable = false
                isProfileable = true
            }
        }
    }
}
"""
        module = self.module(gradle)
        self.assertEqual(perf.find_profileable_variants(module, self.dir, []), [])
        self.assertFalse(perf.always_profileable(perf.build_types(gradle)["qa"]))
        out = self.instrument(module).stdout
        self.assertIn("Variante: profiling (nueva)", out)
        self.assertFalse((module / "src/qa").exists())  # nada que qa cargue sin -Pperf
        self.assertNotIn('getByName("qa").kotlin.directories', out)

    def test_con_groovy_y_con_un_manifest_propio_no_pide_agregar_profileable(self):
        gradle = "android { buildTypes {\n  release { minifyEnabled true }\n  demo { initWith release\n    profileable true }\n} }"
        module = self.dir / "app"
        write(module / "build.gradle", gradle)
        write(module / "src/demo/AndroidManifest.xml", "<manifest><application/></manifest>")
        out = self.instrument(module).stdout
        self.assertIn("Variante: demo (existente", out)
        hint = next(line for line in out.splitlines() if "src/demo/AndroidManifest.xml" in line)
        self.assertIn("agrega el <provider> de abajo)", hint)
        self.assertNotIn("<profileable", hint)

    def test_release_y_debug_con_sabores_tampoco_son_candidatas_ni_se_aceptan_con_variante(self):
        for name, expected in (("release", True), ("Release", True), ("demoRelease", True), ("freeDebug", True),
                               ("qa2Release", True), ("PRODRelease", True), ("UATDebug", True), ("profiling", False), ("benchmark", False), ("prerelease", False),
                               ("releaseLike", False), ("demo", False)):
            self.assertEqual(perf.is_production(name), expected, name)
        module = self.module(GRADLE_KTS, **{"src/demoRelease/AndroidManifest.xml": PROFILEABLE,
                                            "src/freeDebug/AndroidManifest.xml": PROFILEABLE})
        self.assertEqual(perf.find_profileable_variants(module, self.dir, []), [])
        out = self.instrument(module).stdout
        self.assertIn("Variante: profiling (nueva)", out)
        self.assertNotIn("demoRelease", out)
        for name in ("demoRelease", "freeDebug"):
            result = self.instrument(module, "--variante", name)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("variante '%s' no válida: release y debug (también con sabores" % name, result.stderr)
        self.assertEqual((module / "src/demoRelease/AndroidManifest.xml").read_text(encoding="utf-8"), PROFILEABLE)
        # un build type propio que el módulo declara con un nombre así no es un sabor de release: sí se puede usar
        own = GRADLE_KTS.replace('create("benchmark")', 'create("preRelease")')
        module = self.module(own, **{"src/preRelease/AndroidManifest.xml": PROFILEABLE})
        self.assertTrue(perf.is_production("preRelease"))
        self.assertFalse(perf.is_production("preRelease", perf.build_types(own)))
        self.assertTrue(perf.is_production("release", perf.build_types(own)))
        self.assertIn("Variante: preRelease (existente", self.instrument(module, "--variante", "preRelease").stdout)

    def test_si_el_proyecto_depende_del_nombre_del_build_type_recomienda_no_crear_otro(self):
        gradle = GRADLE_KTS + 'android.buildTypes.all { if (name.endsWith("qa")) { buildConfigField("String", "AMBIENTE", "\\"qa\\"") } }\n' \
                              'if (project.name == "app") { println("no cuenta: es el nombre del proyecto") }\n'
        module = self.module(gradle, **{
            "src/main/kotlin/com/ejemplo/app/Toggles.kt": "package com.ejemplo.app\n\nval ambiente = BuildConfig.BUILD_TYPE\n",
            "src/main/kotlin/com/ejemplo/app/Sabor.kt": "package com.ejemplo.app\nval sabor = BuildConfig.FLAVOR_ambiente\n"})
        out = self.instrument(module).stdout
        self.assertIn("⚠ El proyecto parece decidir cosas por el nombre del build type o del sabor (BuildConfig.BUILD_TYPE o FLAVOR en "
                      "app/src/main/kotlin/com/ejemplo/app/Toggles.kt:3, app/src/main/kotlin/com/ejemplo/app/Sabor.kt:2; lógica de "
                      "Gradle por nombre en app/build.gradle.kts:18)", out)
        self.assertIn('Un build type nuevo ("profiling") tiene otro nombre', out)
        self.assertIn("Alternativa recomendada: medir sobre un build type que ya existe, con -Pperf", out)
        self.assertIn('val perf = providers.gradleProperty("perf").isPresent', out)
        self.assertIn("isProfileable = true", out)
        self.assertIn('getByName("<buildType>").manifest.srcFile("src/profiling/AndroidManifest.xml")', out)
        self.assertNotIn("{{", out)
        self.assertEqual(len(perf.scan_gradle(self.dir, [])), 1)  # project.name no cuenta
        self.assertIn("confirma que cada línea decide por un build type, un sabor o una variante", out)
        write(self.dir / "otro" / "build.gradle.kts", 'tasks.matching { it.name.contains("Test") }.configureEach { enabled = false }\n'
              'configurations.all { resolutionStrategy.eachDependency { if (requested.name == "kotlin-stdlib") useVersion("2.0") } }\n'
              'subprojects { if (name == "app") apply(plugin = "x") }\n'
              'val jars = fileTree("libs").filter { it.name.endsWith(".jar") }\n')
        self.assertEqual(len(perf.scan_gradle(self.dir, [])), 1)  # tareas, dependencias, archivos y proyectos tampoco
        write(self.dir / "otro" / "build.gradle.kts", 'androidComponents.onVariants { v -> if (v.name.lowercase().contains("release")) {} }\n'
              "android.applicationVariants.all { if (getName().endsWith('Qa')) {} }\n")
        self.assertEqual([found[1] for found in perf.scan_gradle(self.dir / "otro", [])], [1, 2])  # con llamadas en medio
        # con una variante existente no se crea ningún build type: no hay nada que advertir
        write(module / "src/benchmark/AndroidManifest.xml", PROFILEABLE)
        out = self.instrument(module).stdout
        self.assertIn("Variante: benchmark (existente", out)
        self.assertNotIn("decidir cosas por el nombre", out)
        self.assertNotIn("-Pperf", out)

    def test_un_proyecto_que_no_depende_del_nombre_no_recibe_la_alternativa(self):
        out = self.instrument(self.module()).stdout
        self.assertNotIn("decidir cosas por el nombre", out)
        self.assertNotIn("-Pperf", out)

    def test_al_crear_un_build_type_dice_lo_que_initwith_no_copia(self):
        module = self.module(GRADLE_KTS, **{"src/release/AndroidManifest.xml": "<manifest/>",
                                            "src/release/res/xml/network_security_config.xml": "<network-security-config/>",
                                            "src/release/google-services.json": "{}"})
        out = self.instrument(module).stdout
        self.assertIn('⚠ initWith(release) copia la configuración del build type, no su source set: lo que hay en src/release/ '
                      'no llega a "profiling" (AndroidManifest.xml, google-services.json, res/xml/network_security_config.xml)', out)
        write(module / "src/benchmark/AndroidManifest.xml", PROFILEABLE)
        self.assertNotIn("initWith(release) copia", self.instrument(module).stdout)

    def test_avisa_de_debug_overrides_y_de_buildconfig_debug(self):
        config = '<network-security-config>\n  <debug-overrides><trust-anchors><certificates src="user"/></trust-anchors>' \
                 '</debug-overrides>\n</network-security-config>'
        module = self.module(GRADLE_KTS, **{
            "src/main/res/xml/network_security_config.xml": config,
            "src/main/res/xml/otro.xml": "<paths/>",
            "src/main/kotlin/com/ejemplo/app/Log.kt": "package com.ejemplo.app\nval verbose = BuildConfig.DEBUG\n"})
        out = self.instrument(module).stdout
        self.assertIn("⚠ app/src/main/res/xml/network_security_config.xml usa <debug-overrides>: ese bloque solo aplica en "
                      "builds depurables, y la variante medida no lo es.", out)
        self.assertIn("propón una copia solo para la variante medida (src/profiling/res/xml/network_security_config.xml, con "
                      "esas reglas en <base-config>), nunca en release", out)
        self.assertNotIn("otro.xml usa", out)
        self.assertIn("BuildConfig.DEBUG se lee en 1 lugar (app/src/main/kotlin/com/ejemplo/app/Log.kt:2): en la variante "
                      "medida vale false", out)

    def test_busca_los_puntos_de_extension_en_los_modulos_que_settings_incluye_desde_fuera_de_la_raiz(self):
        with tempfile.TemporaryDirectory() as outside:
            sibling = Path(outside).resolve() / "analitica"
            write(sibling / "build.gradle.kts", 'plugins { id("com.android.library") }')
            write(sibling / "src/main/kotlin/com/ejemplo/core/ScreenTracker.kt", TRACKER)
            write(sibling / "src/main/kotlin/com/ejemplo/core/AnalyticsModule.kt", TRACKER_MODULE)
            write(sibling / "src/main/kotlin/com/ejemplo/core/Http.kt", "val cliente = OkHttpClient.Builder().build()\n")
            relative = os.path.relpath(str(sibling), str(self.dir.resolve()))
            write(self.dir / "settings.gradle.kts", 'include(":app", ":analitica", ":otra")\n'
                  'project(":analitica").projectDir = file("%s")\n'
                  'project(":otra").projectDir = File(rootDir, "$carpetaExterna/otra")\n'
                  'project(":mas").projectDir = File(settingsDir.parentFile, "mas")\n'
                  '// project(":vieja").projectDir = file("../comentada")\n'
                  'includeBuild("../no-existe-hbperf")\n' % relative)
            module = self.module("dependencies { implementation(libs.hilt.android); implementation(libs.okhttp) }")
            roots, unresolved = perf.external_roots(self.dir, [])
            self.assertEqual(([str(r) for r in roots], unresolved), (
                [str(sibling)], ["$carpetaExterna/otra", 'project(":mas").projectDir = File(settingsDir.parentFile, "mas")',
                                 "../no-existe-hbperf"]))
            out = self.instrument(module).stdout
            self.assertIn("También busqué en lo que settings.gradle incluye desde fuera de la raíz: %s." % relative, out)
            self.assertIn("interfaz ScreenTracker (%s/src/main/kotlin/com/ejemplo/core/ScreenTracker.kt:3) · con multibinding"
                          % relative, out)
            self.assertIn("⚠ No pude seguir estas rutas de settings.gradle ($carpetaExterna/otra, project(\":mas\").projectDir = "
                          "File(settingsDir.parentFile, \"mas\"), ../no-existe-hbperf)", out)
            self.assertIn("⚠ OkHttpClient se arma fuera del módulo app (%s/src/main/kotlin/com/ejemplo/core/Http.kt:1)" % relative, out)
            self.assertNotIn("no encontré dónde se arma el OkHttpClient", out)
            # una ruta prohibida tampoco se lee fuera de la raíz: absoluta, o relativa a la raíz con sus '..'
            self.assertEqual(perf.external_roots(self.dir, [str(sibling)])[0], [])
            self.assertEqual(perf.external_roots(self.dir, [relative])[0], [])
            inside = relative + "/src/main/kotlin/com/ejemplo/core/"
            self.assertEqual(perf.scan_sources(self.dir, [inside], [sibling])["ganchos"], [])
            self.assertEqual(len(perf.scan_sources(self.dir, [], [sibling])["ganchos"]), 1)

    def test_las_rutas_de_settings_dentro_de_la_raiz_o_que_la_contienen_no_se_siguen_ni_se_avisan(self):
        (self.dir / "libs" / "x").mkdir(parents=True)
        (self.dir / "build-logic").mkdir()
        write(self.dir / "settings.gradle.kts", 'project(":x").projectDir = file("$rootDir/libs/x")\n'
              'includeBuild("${rootDir}/build-logic")\nincludeBuild("..")\n')
        self.assertEqual(perf.external_roots(self.dir, []), ([], []))

    def test_avisa_si_el_proyecto_usa_okhttp_pero_no_arma_el_cliente(self):
        module = self.module("dependencies { implementation(libs.okhttp) }")
        out = self.instrument(module).stdout
        self.assertIn("⚠ El proyecto usa OkHttp pero no encontré dónde se arma el OkHttpClient", out)
        self.assertIn("las métricas de red serán solo de punta a punta", out)
        write(module / "src/main/kotlin/com/ejemplo/app/Red.kt", "val cliente = OkHttpClient.Builder().build()\n")
        self.assertNotIn("no encontré dónde se arma", self.instrument(module, "--actualizar").stdout)
        self.assertNotIn("no encontré dónde se arma", self.instrument(self.module("dependencies { }")).stdout)  # sin OkHttp


class SetupPresentTest(DeviceBase):
    """"Setup listo" en AGENTS.md no alcanza: `humo` y `nuevo` comprueban que la instrumentación esté en el repo."""

    def test_el_aviso_depende_de_agents_md_y_de_lo_que_hay_en_el_repo(self):
        self.assertIn("no encontré la instrumentación en el repo (ni PerfHooks.kt ni un source set src/perf", perf.setup_warning(self.dir))
        self.assertIn("falta la sesión 0 (setup)", perf.setup_warning(self.dir))
        write(self.dir / "AGENTS.md", "# Proyecto\n\n## Rendimiento\n\n- applicationId: com.ejemplo.app\n- setup listo\n")
        warning = perf.setup_warning(self.dir)
        self.assertIn('AGENTS.md dice "setup listo" pero no encontré la instrumentación en el repo', warning)
        self.assertIn("si el setup se guarda como parche, aplícalo (git apply <parche>)", warning)
        write(self.dir / "AGENTS.md", "## Reglas\n\n- Nunca despliegues con parches manuales.\n\n## Rendimiento\n\n"
                                      "- Setup listo, en parche: `git apply herramientas/perf-setup.patch` antes de medir\n")
        self.assertIn('Reaplícala antes de seguir: según AGENTS.md: "Setup listo, en parche: `git apply '
                      'herramientas/perf-setup.patch` antes de medir"', perf.setup_warning(self.dir))
        write(self.dir / "AGENTS.md", "## Reglas\n\n- Nunca despliegues con parches manuales.\n\n## Rendimiento\n\n- setup listo\n")
        self.assertIn("si el setup se guarda como parche, aplícalo", perf.setup_warning(self.dir))  # esa línea ajena no se cita
        self.assertNotIn("despliegues", perf.setup_warning(self.dir))
        (self.dir / "app/src/perf/kotlin").mkdir(parents=True)  # el source set solo, sin PerfHooks: sigue faltando
        self.assertIn("(ni PerfHooks.kt, bajo", perf.setup_warning(self.dir))
        write(self.dir / "app/src/main/kotlin/com/ejemplo/perf/PerfHooks.kt", "object PerfHooks")
        self.assertEqual(perf.setup_warning(self.dir), "")
        write(self.dir / "otra/build/generated/PerfHooks.kt", "x")  # lo que hay en build/ no cuenta
        self.assertEqual(perf.find_instrumentation(self.dir / "otra"), (False, False))

    def test_nuevo_y_humo_lo_dicen_antes_de_seguir(self):
        write(self.dir / "AGENTS.md", "## Rendimiento\n\n- setup listo (parche: git apply herramientas/perf.patch)\n")
        out = self.ok("nuevo", "--carpeta", self.dir / "reports/perf/x", "--paquete", PKG, "--flujo", "x")
        self.assertIn('⚠ AGENTS.md dice "setup listo" pero no encontré la instrumentación en el repo', out)
        self.assertIn("git apply herramientas/perf.patch", out)
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        self.assertEqual(out.count('AGENTS.md dice "setup listo" pero no encontré la instrumentación'), 2)  # al empezar y al final
        self.assertLess(out.index("⚠ Antes de seguir:"), out.index("Siguiente, según lo que se va a investigar:"))
        write(self.dir / "app/src/perf/kotlin/x/PerfInstaller.kt", "x")
        write(self.dir / "app/src/main/kotlin/x/PerfHooks.kt", "object PerfHooks")
        out = self.ok("humo", "--paquete", PKG, "--carpeta", self.dir / "reports/perf/humo2")
        self.assertNotIn("no encontré la instrumentación", out)
        out = self.ok("nuevo", "--carpeta", self.dir / "reports/perf/y", "--paquete", PKG, "--flujo", "y")
        self.assertNotIn("no encontré la instrumentación", out)


NO_HTTP = "".join(line + "\n" for line in GOOD.splitlines() if '"HTTP ' not in line)
CLIENT_KT = """package com.ejemplo.red

import okhttp3.OkHttpClient

fun cliente(): OkHttpClient = OkHttpClient.Builder()
    .build()
"""
CLIENT_JAVA = """package com.ejemplo.red;

import okhttp3.OkHttpClient;

class ModuloRed {
    OkHttpClient cliente() {
        OkHttpClient.Builder builder = new OkHttpClient.Builder();
        return builder.build();
    }

    OkHttpClient corto(OkHttpClient base) {
        return base.newBuilder().build();
    }
}
"""


class NetworkWiringTest(DeviceBase):
    """El cableado de red lo aplica la sesión 0 y lo comprueban `instrumentar`, `humo` y la corrida de prueba."""

    def project(self, gradle="dependencies { implementation(libs.hilt.android); implementation(libs.okhttp) }", **files):
        write(self.dir / "app/build.gradle.kts", gradle)
        for path, text in files.items():
            write(self.dir / path, text)
        return self.dir / "app"

    def instrument(self, *extra):
        return self.ok("instrumentar", "--modulo", self.dir / "app", "--paquete", "com.ejemplo.perf", "--sin-fragments", *extra)

    def test_perfhooks_trae_el_helper_estatico_y_su_test_segun_el_stack(self):
        module = self.project()
        self.instrument()
        hooks = (module / "src/main/kotlin/com/ejemplo/perf/PerfHooks.kt").read_text(encoding="utf-8")
        self.assertIn("@JvmStatic\n    fun applyEventListener(", hooks)
        self.assertIn("factories.firstOrNull()?.let { builder.eventListenerFactory(it) }", hooks)
        self.assertIn("import okhttp3.EventListener\nimport okhttp3.OkHttpClient\n", hooks)
        self.assertNotIn("applyOkHttp", hooks)  # con Hilt no hay PerfHooks.okHttp
        test = (module / "src/testDebug/kotlin/com/ejemplo/perf/PerfHooksTest.kt").read_text(encoding="utf-8")
        self.assertIn("applyEventListenerLeavesTheBuilderAsIsWithAnEmptySet", test)
        self.assertNotIn("applyOkHttp", test)
        self.assertNotIn("org.junit.After", test)
        self.assertNotIn("hb-perf:", test)
        self.assertNotIn("\n\n\n", test)

    def test_sin_hilt_el_helper_tambien_sirve_desde_java_y_sin_red_no_hay_ninguno(self):
        module = self.project(gradle="dependencies { implementation(libs.okhttp) }")
        out = self.instrument()
        hooks = (module / "src/main/kotlin/com/ejemplo/perf/PerfHooks.kt").read_text(encoding="utf-8")
        self.assertIn("@JvmStatic\n    fun applyOkHttp(builder: OkHttpClient.Builder): OkHttpClient.Builder = builder.also(okHttp)", hooks)
        self.assertIn("fun applyEventListener(", hooks)
        self.assertNotIn("\n\n\n", hooks)
        self.assertIn("PerfHooks.applyOkHttp(builder); // Java", out)
        test = (module / "src/testDebug/kotlin/com/ejemplo/perf/PerfHooksTest.kt").read_text(encoding="utf-8")
        self.assertIn("applyOkHttpRunsTheHookAndReturnsTheSameBuilder", test)
        self.assertIn("import org.junit.After\n", test)
        other = self.dir / "otro"
        write(other / "app/build.gradle.kts", "dependencies { implementation(libs.androidx.fragment) }")
        self.ok("instrumentar", "--modulo", other / "app", "--paquete", "com.ejemplo.perf")
        plain = (other / "app/src/main/kotlin/com/ejemplo/perf/PerfHooks.kt").read_text(encoding="utf-8")
        self.assertNotIn("JvmStatic", plain)
        self.assertNotIn("okhttp3", plain)
        self.assertFalse((other / "app/src/testDebug/kotlin/com/ejemplo/perf/PerfHooksTest.kt").exists())

    def test_el_fragmento_de_red_cubre_un_modulo_de_di_en_java_y_el_comodin(self):
        self.project()
        out = self.instrument()
        self.assertIn("PerfHooks.applyEventListener(OkHttpClient.Builder(), factories)", out)
        self.assertIn("@Provides OkHttpClient okHttp(@PerfEventListeners Set<EventListener.Factory> factories) {", out)
        self.assertIn("PerfHooks.applyEventListener(builder, factories);", out)
        self.assertIn("@JvmSuppressWildcards", out)
        self.assertIn("Set<? extends EventListener.Factory>", out)
        module_text = (self.dir / "app/src/main/kotlin/com/ejemplo/perf/PerfHooksModule.kt").read_text(encoding="utf-8")
        self.assertIn("PerfHooks.applyEventListener(builder, factories)", module_text)

    def test_instrumentar_lista_los_builders_que_no_llaman_al_gancho_en_kotlin_y_en_java(self):
        self.project(**{"app/src/main/kotlin/com/ejemplo/red/Cliente.kt": CLIENT_KT,
                        "app/src/main/java/com/ejemplo/red/ModuloRed.java": CLIENT_JAVA})
        out = self.instrument()
        self.assertIn("// Builders que todavía no llaman al gancho (2): app/src/main/java/com/ejemplo/red/ModuloRed.java:7, "
                      "app/src/main/kotlin/com/ejemplo/red/Cliente.kt:5", out)
        self.assertIn("// Clientes derivados con .newBuilder() (heredan el listener de su cliente base: cablea el base): "
                      "app/src/main/java/com/ejemplo/red/ModuloRed.java:12", out)
        self.assertIn("la prueba de humo falla", out)
        write(self.dir / "app/src/main/kotlin/com/ejemplo/red/Cliente.kt", CLIENT_KT.replace(
            "OkHttpClient.Builder()\n", "PerfHooks.applyEventListener(OkHttpClient.Builder(), factories)\n"))
        write(self.dir / "app/src/main/java/com/ejemplo/red/ModuloRed.java", CLIENT_JAVA.replace(
            "return builder.build();", "PerfHooks.applyEventListener(builder, factories);\n        return builder.build();"))
        out = self.instrument()
        self.assertIn("// No quedan builders sin cablear en el código que pude leer.", out)
        self.assertNotIn("Clientes derivados", out)  # su archivo ya llama al gancho

    def test_un_builder_cuenta_como_cableado_solo_si_su_archivo_llama_al_gancho_tantas_veces_como_builders_tiene(self):
        two = {"archivo": "a/Red.kt", "builders": [5, 9], "derivados": [20], "llamadas": 1}
        self.assertEqual(perf.unwired_builders([two]), (["a/Red.kt:5", "a/Red.kt:9"], []))
        self.assertEqual(perf.unwired_builders([dict(two, llamadas=2)]), ([], []))
        self.assertEqual(perf.unwired_builders([dict(two, builders=[], llamadas=0)]), ([], ["a/Red.kt:20"]))
        for wired in ("PerfHooks.okHttp(builder)", "PerfHooks.applyOkHttp(builder);", "PerfHooks.INSTANCE.getOkHttp().invoke(b);",
                      "PerfHooks.applyEventListener(builder, factories)"):
            self.assertTrue(perf.OKHTTP_WIRED.search(wired), wired)
        for plain in ("import com.ejemplo.perf.PerfHooks", "PerfHooks.mark(\"detalle\")", "OkHttpClient.Builder()"):
            self.assertFalse(perf.OKHTTP_WIRED.search(plain), plain)
        # la factory puesta a mano cuenta solo si el archivo recibe el set de la skill o nombra su listener (el
        # fragmento de versiones anteriores); otra factory del proyecto no es el gancho
        builder = "val c = OkHttpClient.Builder()\n"
        for name, text, calls in (
                ("Viejo.kt", "fun c(@PerfEventListeners f: Set<F>) =\n" + builder + ".apply { f.firstOrNull()?.let(::eventListenerFactory) }\n", 1),
                ("Directo.kt", builder + ".eventListenerFactory(TraceEventListener.FACTORY)\n", 1),
                ("Ajeno.kt", builder + ".eventListenerFactory(MetricasPropias.FACTORY)\n", 0)):
            write(self.dir / "wired" / name, text)
            found = perf.scan_sources(self.dir / "wired", [])["cableado"]
            self.assertEqual(next(item["llamadas"] for item in found if item["archivo"] == name), calls, name)
        write(self.dir / "app/src/testDebug/kotlin/ApiTest.kt", builder)  # los tests por variante no se listan
        write(self.dir / "app/src/androidTestDemoDebug/kotlin/UiTest.kt", builder)
        self.assertEqual(perf.scan_sources(self.dir / "app", [])["cableado"], [])
        derived = "import okhttp3.OkHttpClient\nval a = base.newBuilder().build()\nval r = chain.request().newBuilder().build()\n" \
                  "val u = request.url.newBuilder().build()\n"
        write(self.dir / "src/Derivado.kt", derived)
        write(self.dir / "src/Interceptor.kt", "val r = original.newBuilder().build()\n")  # no nombra OkHttpClient: no cuenta
        self.assertEqual(perf.scan_sources(self.dir / "src", [])["cableado"],
                         [{"archivo": "Derivado.kt", "builders": [], "derivados": [2], "llamadas": 0}])

    def generated(self):
        """Un proyecto con la instrumentación de red generada y un builder sin cablear."""
        self.project(**{"app/src/main/kotlin/com/ejemplo/red/Cliente.kt": CLIENT_KT})
        self.instrument()

    def test_la_prueba_avisa_si_hay_instrumentacion_de_red_y_ninguna_seccion_http(self):
        self.generated()
        self.tp_outputs(NO_HTTP)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("⚠ RED SIN MEDIR: la corrida no tiene ninguna sección HTTP y el proyecto tiene la instrumentación de red "
                      "generada. Causa probable: el listener no está conectado a ningún OkHttpClient.Builder.", out)
        self.assertIn("Builders que no llaman al gancho de PerfHooks (1): app/src/main/kotlin/com/ejemplo/red/Cliente.kt:5.", out)
        self.assertLess(out.index("RED SIN MEDIR"), out.index("Traza:"))
        self.tp_outputs(GOOD)  # con secciones HTTP no hay nada que avisar
        (self.dir / "tp.count").unlink()
        self.assertNotIn("RED SIN MEDIR", self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba"))

    def test_la_prueba_tambien_avisa_si_el_plan_declara_la_red_y_no_si_nada_la_espera(self):
        self.tp_outputs(NO_HTTP)
        self.assertNotIn("RED SIN MEDIR", self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba"))
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["principales"] = ["red_llamadas"]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("⚠ RED SIN MEDIR: la corrida no tiene ninguna sección HTTP y el plan usa métricas o marcas de red.", out)
        self.assertIn("No encontré builders sin conectar en el código que pude leer", out)

    def test_el_plan_declara_la_red_con_metricas_marcas_o_un_tramo_solo_de_red(self):
        mark = {"desde": {"marca": "NAV a"}, "hasta": {"marca": "MARK a"}}
        self.assertFalse(perf.plan_expects_network({"principales": ["hilo_max_ms"]}, {"ventana": mark, "segmentos": [dict(mark, nombre="a")]}))
        self.assertTrue(perf.plan_expects_network({"principales": ["red GET /items cliente_ms"]}, {}))
        self.assertTrue(perf.plan_expects_network({"principales": ["pago red_llamadas"]}, {}))
        self.assertTrue(perf.plan_expects_network({"mejoras": [{"id": "M1", "metrica": "red_solapadas"}]}, {}))
        self.assertTrue(perf.plan_expects_network({}, {"metricas_usuario": [dict(mark, nombre="m", hasta={"marca": "HTTP GET /items"})]}))
        self.assertTrue(perf.plan_expects_network({}, {"segmentos": [dict(mark, nombre="a", solo_red=True)]}))

    def test_humo_falla_si_la_red_esta_generada_y_no_sale_ninguna_seccion_http(self):
        self.generated()
        self.tp_outputs(NO_HTTP)
        result = self.perf("humo", "--paquete", PKG)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("✖ RED SIN MEDIR", result.stderr)
        self.assertIn("el listener no está conectado a ningún OkHttpClient.Builder", result.stderr)
        self.assertIn("app/src/main/kotlin/com/ejemplo/red/Cliente.kt:5", result.stderr)
        self.assertIn("repite con --sin-red", result.stderr)
        self.assertIn("Secciones propias:", result.stdout)  # las métricas y las secciones salen igual, antes del error
        self.assertNotIn("Siguiente", result.stdout)  # el setup no está listo: no ofrece la sesión 1
        (self.dir / "tp.count").unlink()
        out = self.ok("humo", "--paquete", PKG, "--sin-red")
        self.assertNotIn("RED SIN MEDIR", out)
        self.assertIn("Siguiente", out)


class GeneratedFilesTest(PerfBase):
    """`instrumentar --actualizar` no pisa un archivo generado que alguien editó a mano."""

    def setUp(self):
        super().setUp()
        self.module = self.dir / "app"
        write(self.module / "build.gradle.kts", "dependencies { implementation(libs.okhttp) }")
        self.out = self.instrument()
        self.target = self.module / "src/perf/kotlin/com/ejemplo/perf/HttpSectionName.kt"

    def instrument(self, *extra):
        return self.perf("instrumentar", "--modulo", self.module, "--paquete", "com.ejemplo.perf", "--sin-fragments", *extra)

    def test_cada_archivo_generado_guarda_su_huella_tambien_los_manifests(self):
        text = self.target.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertIn("Generated by hb-performance", lines[0])
        self.assertRegex(lines[1], r"^// hb-performance fingerprint: [0-9a-f]{16}$")
        self.assertEqual(lines[2], "package com.ejemplo.perf")
        self.assertEqual(perf.FINGERPRINT.search(text).group(1), perf.fingerprint(text))
        manifest = (self.module / "src/debug/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertRegex(manifest.splitlines()[2], r"^<!-- hb-performance fingerprint: [0-9a-f]{16} -->$")
        self.assertTrue(perf.is_generated(self.target))
        self.assertEqual(perf.stamp(perf.stamp(text)), text)  # volver a sellar no agrega otra línea

    def test_la_huella_no_cambia_con_el_formato_y_si_con_una_edicion(self):
        text = self.target.read_text(encoding="utf-8")
        formatted = text.replace("request: Request)", "\n        request: Request,\n    )").replace("    ", "\t")
        self.assertNotEqual(formatted, text)
        self.assertEqual(perf.fingerprint(formatted), perf.fingerprint(text))
        self.assertEqual(perf.fingerprint("// x\nimport z.Ultimo\nimport a.Primero\n"),
                         perf.fingerprint("// x\nimport a.Primero\nimport z.Ultimo\n"))
        self.assertNotEqual(perf.fingerprint(text.replace("{6,}", "{8,}")), perf.fingerprint(text))
        # una edición que solo reordena código, o que solo cambia espacios o comas dentro de un literal, también cuenta
        other = text + "// otra versión\n"
        for before, after in (("padStart(HASH_LENGTH, '0')", "padStart('0', HASH_LENGTH)"), ('" #"', '"#"'), ("{6,}", "{6}"),
                              ('"/{id}"', '"/ {id}"')):
            self.assertIn(before, text)
            self.assertEqual(perf.generated_state(text.replace(before, after), other), "editado", (before, after))
        listener = self.target.with_name("TraceEventListener.kt").read_text(encoding="utf-8")
        swapped = listener.replace("http.begin()\n        queue.begin()", "queue.begin()\n        http.begin()")
        self.assertNotEqual(swapped, listener)
        self.assertEqual(perf.generated_state(swapped, listener + "// otra versión\n"), "editado")
        self.assertEqual(perf.generated_state(formatted, text), "igual")
        self.assertEqual(perf.generated_state(text.replace("{6,}", "{8,}"), text), "editado")
        old = perf.stamp(text.replace("{6,}", "{9,}"))  # otra versión de la plantilla, sin tocar
        self.assertEqual(perf.generated_state(old, text), "intacto")
        self.assertEqual(perf.generated_state(perf.FINGERPRINT.sub("", old), text), "sin huella")

    def test_un_archivo_editado_a_mano_no_se_pisa_sin_forzar_y_forzado_deja_la_copia(self):
        edited = self.target.read_text(encoding="utf-8").replace('"/{id}"', '"/{numero}"')
        self.target.write_text(edited, encoding="utf-8")
        result = self.instrument("--actualizar")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("✖ no se actualiza: %s (lo editaron a mano después de generarlo)" % self.target, result.stdout)
        self.assertIn("⚠ 1 archivo no se actualizó: difiere de lo que generó la skill", result.stdout)
        self.assertIn("--actualizar --forzar", result.stdout)
        self.assertEqual(self.target.read_text(encoding="utf-8"), edited)
        self.assertFalse(self.target.with_name("HttpSectionName.kt.orig").exists())
        result = self.instrument("--actualizar", "--forzar")
        copy = self.target.with_name("HttpSectionName.kt.orig")
        self.assertIn("~ actualizado con --forzar: %s (lo que había quedó en %s)" % (self.target, copy), result.stdout)
        self.assertEqual(copy.read_text(encoding="utf-8"), edited)
        self.assertIn('"/{id}"', self.target.read_text(encoding="utf-8"))
        self.assertNotIn("no se actualiza", result.stdout)
        self.target.write_text(edited, encoding="utf-8")  # otra edición: la copia anterior no se pierde
        self.instrument("--actualizar", "--forzar")
        self.assertTrue(self.target.with_name("HttpSectionName.kt.orig2").is_file())
        self.assertEqual(copy.read_text(encoding="utf-8"), edited)

    def test_un_archivo_de_una_version_sin_huella_solo_se_pisa_si_no_cambio_o_con_forzar(self):
        current = self.target.read_text(encoding="utf-8")
        legacy = perf.FINGERPRINT.sub("", current)  # lo que dejaba una versión anterior: el encabezado, sin huella
        self.target.write_text(legacy, encoding="utf-8")
        result = self.instrument("--actualizar")
        self.assertIn("= al día: %s" % self.target, result.stdout)  # igual a la plantilla: solo gana su huella
        self.assertEqual(self.target.read_text(encoding="utf-8"), current)
        changed = legacy.replace("{6,}", "{7,}")  # otra plantilla, o una edición: sin huella no se distinguen
        self.target.write_text(changed, encoding="utf-8")
        result = self.instrument("--actualizar")
        self.assertIn("✖ no se actualiza: %s (lo generó una versión anterior, sin huella" % self.target, result.stdout)
        self.assertEqual(self.target.read_text(encoding="utf-8"), changed)
        result = self.instrument("--actualizar", "--forzar")
        self.assertEqual(self.target.read_text(encoding="utf-8"), current)
        self.assertEqual(self.target.with_name("HttpSectionName.kt.orig").read_text(encoding="utf-8"), changed)

    def test_al_actualizar_un_archivo_nuevo_no_se_crea_mientras_otro_quede_sin_actualizar(self):
        hooks_test = self.module / "src/testDebug/kotlin/com/ejemplo/perf/PerfHooksTest.kt"
        hooks_test.unlink()  # como en un proyecto instrumentado con una versión que no lo traía
        self.target.write_text(self.target.read_text(encoding="utf-8").replace('"/{id}"', '"/{numero}"'), encoding="utf-8")
        result = self.instrument("--actualizar")
        self.assertIn("· sin crear todavía: %s (es nuevo en esta versión y puede usar lo que falta actualizar)" % hooks_test,
                      result.stdout)
        self.assertFalse(hooks_test.exists())
        self.assertIn("Hasta entonces la instrumentación queda a medias", result.stdout)
        result = self.instrument("--actualizar", "--forzar")
        self.assertIn("+ %s" % hooks_test, result.stdout)
        self.assertTrue(hooks_test.is_file())

    def test_unir_codigo_a_un_comentario_de_linea_tambien_cuenta_como_edicion(self):
        text = "// Generated by hb-performance\npackage a\n\n// nota\nregistrar()\n"
        self.assertNotEqual(perf.fingerprint(text), perf.fingerprint(text.replace("// nota\nregistrar()", "// nota registrar()")))
        self.assertEqual(perf.fingerprint(text), perf.fingerprint(text.replace("// nota\n", "// nota   \n\n")))
        self.assertEqual(perf.fingerprint('val u = "https://api.test/a"  // x\n'), perf.fingerprint('val u =\n    "https://api.test/a" // x\n'))

    def test_sin_actualizar_nada_cambia_y_un_archivo_del_proyecto_nunca_se_pisa(self):
        edited = self.target.read_text(encoding="utf-8") + "// nota\n"
        self.target.write_text(edited, encoding="utf-8")
        own = self.module / "src/perf/kotlin/com/ejemplo/perf/MarkTrace.kt"
        own.write_text("package com.ejemplo.perf\n", encoding="utf-8")
        result = self.instrument()
        self.assertIn("= ya existe, no se toca: %s" % self.target, result.stdout)
        result = self.instrument("--actualizar", "--forzar")
        self.assertEqual(own.read_text(encoding="utf-8"), "package com.ejemplo.perf\n")
        self.assertIn("no lo generó la skill", result.stdout)


class IdSegmentsTest(unittest.TestCase):
    """Los segmentos de la ruta que parecen un id se normalizan igual en las dos plantillas de Kotlin."""

    CASES = (("/clientes/1234-5678-90/cuentas/00-123-456789-0", "/clientes/{id}/cuentas/{id}"),
             ("/clientes/AB-123.456.789", "/clientes/{id}"), ("/pagos/ORD-2026-000123/detalle", "/pagos/{id}/detalle"),
             ("/v3.7/items/pagina-12", "/v3.7/items/pagina-12"), ("/api/v2/lotes/a1b2c3", "/api/v2/lotes/a1b2c3"),
             ("/a/123/b/123e4567-e89b-12d3-a456-426614174000", "/a/{id}/b/{id}"), ("/items/0123456789abcdef", "/items/{id}"))

    def kotlin_regex(self, name):
        text = (SCRIPT.parent.parent / "assets" / "instrumentacion" / name).read_text(encoding="utf-8")
        body = re.search(r"ID_SEGMENT = Regex\(\s*((?:\"[^\n]*\"\s*\+?\s*)+)\)", text).group(1)
        return re.compile("".join(re.findall(r'"([^"\n]*)"', body)).replace("\\\\", "\\"))

    def test_las_dos_plantillas_normalizan_los_segmentos_con_seis_o_mas_digitos(self):
        for name in ("HttpSectionName.okhttp.kt", "HttpSectionName.retrofit.kt"):
            pattern = self.kotlin_regex(name)
            for path, expected in self.CASES:
                self.assertEqual(pattern.sub("/{id}", path), expected, (name, path))

    def test_har_conserva_su_regla_para_no_renombrar_metricas_de_una_investigacion_en_curso(self):
        self.assertEqual(perf.har_endpoint("get", "https://api.test/items/42/b/123e4567-e89b-12d3-a456-426614174000"),
                         "GET api.test/items/{id}/b/{id}")
        self.assertEqual(perf.har_endpoint("get", "https://api.test/pagos/ORD-2026-000123"), "GET api.test/pagos/ORD-2026-000123")

    def test_la_plantilla_trae_sus_tests_de_normalizacion(self):
        text = (SCRIPT.parent.parent / "assets" / "instrumentacion" / "test" / "TraceEventListenerTest.kt").read_text(encoding="utf-8")
        self.assertIn("sanitizeReplacesSegmentsWithSixOrMoreDigitsEvenWithHyphensOrDots", text)
        self.assertIn("sanitizeKeepsShortVersionsAndPages", text)


DEXOPT_SPEED = """Dexopt state:
  [com.otra.app]
    path: /data/app/~~aa==/com.otra.app-bb==/base.apk
      arm64: [status=verify] [reason=install] [primary-abi]
        [location is /data/app/~~aa==/com.otra.app-bb==/oat/arm64]
  [com.ejemplo.app]
    path: /data/app/~~cc==/com.ejemplo.app-dd==/base.apk
      arm64: [status=speed] [reason=cmdline] [primary-abi]
        [location is /data/app/~~cc==/com.ejemplo.app-dd==/oat/arm64]
    path: /data/app/~~cc==/com.ejemplo.app-dd==/split_config.es.apk
      arm64: [status=speed] [reason=cmdline] [primary-abi]
  [com.tercera.app]
    path: /data/app/~~ee==/com.tercera.app-ff==/base.apk
      arm64: [status=speed-profile] [reason=bg-dexopt] [primary-abi]
"""


class CaptureFeedbackTest(DeviceBase):
    """La captura no parece colgada (avisos de progreso), no compila cuando no hace falta y la prueba dice qué falta."""

    def capture(self, *extra):
        return self.perf("capturar", "--plan", self.plan, "--flujo", "home", *extra)

    def compiles(self):
        log = (self.dir / "adb.log").read_text(encoding="utf-8") if (self.dir / "adb.log").exists() else ""
        return log.count("cmd package compile -f -m speed %s" % PKG)

    def update_flow(self, **fields):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(fields)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def test_avisa_antes_de_compilar_cuanto_tardo_y_cada_traza_que_procesa(self):
        self.tp_outputs(GOOD)
        out = self.capture("--fase", "antes", "--corridas", "2").stdout
        before = out.index("… fijando la compilación de ART (completa: speed) de %s. En una app grande puede tardar varios "
                           "minutos" % PKG)
        done = re.search(r"✔ compilación de ART fijada: completa \(speed\), igual en todas las fases \(tardó \d+ s\)", out)
        self.assertLess(before, done.start())
        self.assertLess(done.start(), out.index("… calentamiento 1 de 1 (no cuenta)"))
        self.assertLess(out.index("… procesando la traza 1 de 2"), out.index("corrida 1/2"))
        self.assertLess(out.index("corrida 1/2"), out.index("… procesando la traza 2 de 2"))
        self.assertEqual(perf.elapsed_text(42.4), "42 s")
        self.assertEqual(perf.elapsed_text(185), "3 min 05 s")
        out = self.ok("diagnostico", "--carpeta", self.plan.parent, "--flujo", "home")
        self.assertIn("… procesando la traza 1 de ", out)
        out = self.capture("--fase", "control", "--corridas", "1", "--compilacion", "perfil").stdout
        self.assertIn("… fijando la compilación de ART (perfil: Baseline Profile + speed-profile)", out)
        self.assertRegex(out, r"Baseline Profile instalado y speed-profile \(tardó \d+ s\)")

    def test_la_prueba_no_compila_salvo_con_compilar_y_sin_compilar_se_sigue_aceptando(self):
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("· Corrida de prueba: no fija la compilación de ART (sus números no se guardan ni se comparan); con "
                      "--compilar se fija igual que en una fase", out)
        self.assertEqual(self.compiles(), 0)
        self.assertNotIn("am force-stop", (self.dir / "adb.log").read_text(encoding="utf-8"))  # tampoco cierra la app
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba", "--sin-compilar")
        self.assertNotIn("Corrida de prueba: no fija", out)  # pedido explícito: nada que explicar
        self.assertEqual(self.compiles(), 0)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba", "--compilar")
        self.assertIn("✔ compilación de ART fijada: completa (speed)", out)
        self.assertEqual(self.compiles(), 1)
        result = self.capture("--prueba", "--compilar", "--sin-compilar")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--sin-compilar y --compilar se contradicen", result.stderr)
        fresh = self.dir / "otra" / "plan.json"  # sin corrida de prueba todavía: el paso siguiente la ofrece y lo dice
        write(fresh, self.plan.read_text(encoding="utf-8"))
        self.assertIn("sin guardar nada ni fijar la compilación de ART", self.ok("siguiente", "--carpeta", fresh.parent))

    def test_humo_tampoco_compila(self):
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        self.assertIn("Corrida de prueba: no fija la compilación de ART", out)
        self.assertEqual(self.compiles(), 0)

    def test_lee_el_filtro_de_compilacion_del_paquete_en_dumpsys_package_dexopt(self):
        self.assertEqual(perf.dexopt_filters(DEXOPT_SPEED, PKG), ["speed", "speed"])
        self.assertEqual(perf.dexopt_filters(DEXOPT_SPEED, "com.tercera.app"), ["speed-profile"])
        self.assertEqual(perf.dexopt_filters(DEXOPT_SPEED, "com.no.esta"), [])
        self.assertEqual(perf.dexopt_filters("", PKG), [])
        self.assertEqual(perf.dexopt_filters("    versionCode=7\n    flags=[ HAS_CODE ]\n", PKG), [])

    def test_no_recompila_si_la_app_ya_tiene_speed_y_es_la_misma_instalacion(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_DEXOPT"] = DEXOPT_SPEED
        common = ["--corridas", "1", "--calentamiento", "0"]
        out = self.capture("--fase", "antes", *common).stdout
        self.assertIn("✔ compilación de ART fijada: completa (speed)", out)  # la primera vez no hay registro: compila
        self.assertEqual(self.compiles(), 1)
        record = json.loads((self.plan.parent / "compilacion.json").read_text(encoding="utf-8"))
        self.assertEqual(record, {"paquete": PKG, "filtro": "speed", "version": "1.0 (7)", "instalada": "2026-11-05 10:00:00"})
        out = self.capture("--fase", "control", *common).stdout
        self.assertIn("✔ compilación de ART ya fijada: completa (speed) en esta misma instalación (1.0 (7), instalada "
                      "2026-11-05 10:00:00): no se recompila; --recompilar la fuerza", out)
        self.assertEqual(self.compiles(), 1)
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["control"]["compilacion"], phases["antes"]["compilacion"])  # comparar no ve diferencia
        self.assertEqual((self.dir / "adb.log").read_text(encoding="utf-8").count("am force-stop %s" % PKG), 2)  # la cierra igual
        self.capture("--fase", "control", "--rehacer", "--recompilar", *common)
        self.assertEqual(self.compiles(), 2)  # --recompilar la fuerza

    def test_recompila_si_cambio_la_instalacion_o_el_filtro_o_no_se_pudo_leer(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_DEXOPT"] = DEXOPT_SPEED
        common = ["--corridas", "1", "--calentamiento", "0"]
        self.capture("--fase", "antes", *common)
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"  # se instaló otro build: la compilación anterior no vale
        out = self.capture("--fase", "despues", *common).stdout
        self.assertNotIn("ya fijada", out)
        self.assertEqual(self.compiles(), 2)
        self.env["FAKE_DEXOPT"] = DEXOPT_SPEED.replace("[status=speed] [reason=cmdline] [primary-abi]\n        [location",
                                                       "[status=speed-profile] [reason=bg-dexopt] [primary-abi]\n        [location")
        self.capture("--fase", "despues", "--rehacer", *common)  # misma instalación, pero un APK ya no está en speed
        self.assertEqual(self.compiles(), 3)
        self.env["FAKE_DEXOPT"] = "Dexopt state:\n  (sin datos)\n"  # no se pudo leer: no se asume nada
        self.capture("--fase", "despues", "--rehacer", *common)
        self.assertEqual(self.compiles(), 4)
        self.env["FAKE_DEXOPT"] = DEXOPT_SPEED
        log_before = (self.dir / "adb.log").read_text(encoding="utf-8").count("compile -f -m speed-profile")
        self.capture("--fase", "despues", "--rehacer", "--compilacion", "perfil", *common)  # el modo perfil nunca reutiliza
        self.assertEqual((self.dir / "adb.log").read_text(encoding="utf-8").count("compile -f -m speed-profile"), log_before + 1)

    def marks_plan(self):
        self.update_flow(ventana={"desde": {"marca": "NAV detalle"}, "hasta": {"marca": "MARK detalle"}},
                         metricas_usuario=[{"nombre": "detalle_ms", "desde": {"marca": "NAV detalle"},
                                            "hasta": {"marca": "MARK detalle"}}],
                         segmentos=[{"nombre": "pago", "desde": {"marca": "MARK operacion_inicio"},
                                     "hasta": {"marca": "MARK operacion_fin"}}])

    def test_la_prueba_dice_que_marcas_del_plan_salieron_la_ultima_vista_y_cuanto_dura_la_traza(self):
        self.marks_plan()
        self.tp_outputs(GOOD + '"seccion",50000000,0,0,"NAV detalle"\n"seccion",2500000000,0,0,"MARK detalle"\n')
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("Marcas del plan:\n"
                      "  ✔ NAV detalle (ventana.desde, detalle_ms.desde)\n"
                      "  ✔ MARK detalle (ventana.hasta, detalle_ms.hasta)\n"
                      "  ✖ MARK operacion_inicio (tramo pago.desde) · no salió en la traza\n"
                      "  ✖ MARK operacion_fin (tramo pago.hasta) · no salió en la traza\n"
                      "  ✔ invalidar_si SCREEN *Login* · no apareció\n"
                      "Recorrido: última marca vista: MARK detalle a los 2.5 s · la traza dura 5 s · secciones HTTP: 2", out)

    def test_una_prueba_cortada_dice_hasta_donde_llego_el_recorrido(self):
        self.marks_plan()
        self.update_flow(recorrido="exit 1")  # el recorrido se cortó a la mitad
        self.tp_outputs(NO_HTTP + '"seccion",50000000,0,0,"NAV detalle"\n"seccion",4200000000,0,0,"SCREEN FormularioActivity onResume"\n')
        result = self.capture("--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("la corrida de prueba fue inválida: el recorrido terminó con código 1", result.stderr)
        self.assertIn("  ✔ NAV detalle (ventana.desde, detalle_ms.desde)", result.stdout)
        self.assertIn("  ✖ MARK detalle (ventana.hasta, detalle_ms.hasta) · no salió en la traza", result.stdout)
        self.assertIn("Recorrido: última marca vista: SCREEN FormularioActivity onResume a los 4.2 s · la traza dura 5 s · "
                      "secciones HTTP: 0", result.stdout)
        self.tp_outputs(LOGIN)  # una pantalla que invalida: lo dice junto a su patrón
        (self.dir / "tp.count").unlink()
        self.update_flow(recorrido="true")
        result = self.capture("--prueba")
        self.assertIn("  ✖ invalidar_si SCREEN *Login* · apareció 'SCREEN LoginActivity onCreate': la corrida no vale", result.stdout)

    def test_sin_marcas_en_el_plan_solo_informa_el_recorrido(self):
        info = perf.trace_metrics([("proceso", 0, 0, 0, PKG), ("limites", 1000 * MS, 4000 * MS, 0, ""),
                                   ("frame", 1500 * MS, 16 * MS, 0, "None")], 60, {}, set(), 34)[2]
        self.assertEqual(perf.marks_report(info), ["Recorrido: ninguna marca propia (SCREEN, NAV, MARK) en la traza · la traza "
                                                   "dura 4 s · secciones HTTP: 0"])
        info = perf.trace_metrics([("proceso", 0, 0, 0, PKG), ("limites", 1000 * MS, 4000 * MS, 0, ""),
                                   ("seccion", 3000 * MS, 0, 0, "MARK lista"), ("frame", 1500 * MS, 16 * MS, 0, "None")],
                                  60, {"pausas": [{"desde": {"marca": "MARK a"}, "hasta": {"marca": "MARK lista"}}]}, set(), 34)[2]
        self.assertEqual(perf.marks_report(info)[1:], ["  ✖ MARK a (pausa 1.desde) · no salió en la traza",
                                                       "  ✔ MARK lista (pausa 1.hasta)",
                                                       "Recorrido: última marca vista: MARK lista a los 2 s · la traza dura 4 s · "
                                                       "secciones HTTP: 0"])  # el tiempo se cuenta desde que empieza la traza

    def test_el_tope_de_la_traza_se_configura_en_el_flujo(self):
        base = "buffers { size_kb: 1 }\nwrite_into_file: true\nduration_ms: 600000\n"
        self.assertEqual(perf.with_trace_cap(base, None), base)
        self.assertEqual(perf.with_trace_cap(base, 900), base.replace("600000", "900000"))
        self.assertEqual(perf.with_trace_cap("buffers { size_kb: 1 }\n", 90.5), "buffers { size_kb: 1 }\nduration_ms: 90500\n")
        own = "data_sources {\n  config {\n    duration_ms: 5\n  }\n}\nduration_ms: 30000  # tope propio\n"
        self.assertEqual(perf.with_trace_cap(own, 120),  # solo el de primer nivel, y el comentario se conserva
                         own.replace("duration_ms: 30000", "duration_ms: 120000"))
        self.assertEqual(perf.trace_cap_s(own), 30)
        self.assertEqual(perf.trace_cap_s(base), 600)
        for name in ("base", "completa", "cpu"):  # las de la skill traen el tope que reemplaza with_trace_cap
            text = (SCRIPT.parent.parent / "assets" / "perfetto" / ("%s.pbtx" % name)).read_text(encoding="utf-8")
            self.assertEqual(perf.trace_cap_s(text), 600, name)
        self.tp_outputs(GOOD)
        self.env["FAKE_PERFETTO_CONFIG"] = str(self.dir / "config.pbtx")
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("duration_ms: 600000", (self.dir / "config.pbtx").read_text(encoding="utf-8"))
        self.update_flow(duracion_max_s=1200)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        config = (self.dir / "config.pbtx").read_text(encoding="utf-8")
        self.assertIn("duration_ms: 1200000", config)
        self.assertNotIn("600000", config)
        for bad in (0, -5, "600", True, 100000):
            self.update_flow(duracion_max_s=bad)
            result = self.perf("siguiente", "--carpeta", self.plan.parent)
            self.assertEqual(result.returncode, 2, str(bad))
            self.assertIn("flujos.home.duracion_max_s es el tope de la traza en segundos", result.stderr)

    def test_si_la_traza_termina_antes_que_el_recorrido_la_corrida_es_invalida(self):
        self.tp_outputs(GOOD)
        self.update_flow(duracion_max_s=30)
        self.env["FAKE_TRAZA_CORTADA"] = "1"
        result = self.capture("--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("la traza terminó antes que el recorrido: llegó a su tope de duración (30 s) o al tamaño máximo del "
                      "archivo, y le falta el final. Sube 'duracion_max_s' en el flujo del plan", result.stderr)
        result = self.capture("--fase", "antes", "--corridas", "2", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5)
        self.assertEqual(result.stdout.count("inválida: la traza terminó antes que el recorrido"), 3)
        del self.env["FAKE_TRAZA_CORTADA"]
        self.assertEqual(self.capture("--prueba").returncode, 0)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("[ -d /proc/4242 ] && echo viva || echo terminada", log)  # sin señales: mira si el proceso existe
        self.assertLess(log.rindex("[ -d /proc/4242 ] && echo"), log.rindex("kill -TERM 4242"))  # antes de detener Perfetto
        self.assertLess(log.rindex("kill -TERM 4242"), log.rindex('"[ -d /proc/4242 ]"'))  # y después espera a que termine
        self.assertNotIn("kill -0", log)

    def test_en_un_emulador_dice_que_los_tiempos_no_representan_un_telefono_y_que_la_red_si_sirve(self):
        self.tp_outputs(GOOD)
        self.env.update({"FAKE_EMULATOR": "1", "FAKE_GLES": GLES_HOST})
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("⚠ es un emulador (render: Google (Apple), Android Emulator OpenGL ES Translator (Apple M2 Pro), OpenGL ES "
                      "3.0 (4.1 Metal)): sus tiempos de frames, de hilo principal y de carga no representan un teléfono (son "
                      "orientativos); sí sirve para el comportamiento de la red (qué llamadas hace, cuántas y en qué orden)", out)
        self.env["FAKE_GLES"] = GLES_SOFT
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("⚠ el dispositivo renderiza por software", out)
        self.assertIn("⚠ es un emulador: sus tiempos de frames, de hilo principal y de carga no representan un teléfono; sí "
                      "sirve para el comportamiento de la red", out)
        for text in (environment_text(hardware="goldfish"), environment_text(hardware="ranchu"), environment_text(qemu="1")):
            self.assertIn("no representan un teléfono", perf.environment_warnings(perf.classify_environment(text))[0])
        self.assertEqual(perf.environment_warnings(perf.classify_environment(environment_text())), [])


class PrepareEnvTest(DeviceBase):
    """Las variables de entorno que usa `preparar` se detectan aunque el plan no las declare en `requiere_env`."""

    def set_prepare(self, command, **fields):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(dict(fields, preparar=command))
        self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def test_lee_las_variables_del_comando_con_y_sin_llaves_y_las_que_pasa_con_e(self):
        names = perf.prepare_env_names('maestro --device emulator-5554 test -e PERF_USUARIO="$PERF_USUARIO" '
                                       '-e PERF_CLAVE="${PERF_CLAVE}" flujo.yaml > /dev/null 2>&1 && sleep $ESPERA', self.dir)
        self.assertEqual(names, ["ESPERA", "PERF_CLAVE", "PERF_USUARIO"])
        self.assertEqual(perf.prepare_env_names("", self.dir), [])
        self.assertEqual(perf.prepare_env_names("adb -s emulator-5554 shell input keyevent KEYCODE_BACK && sleep 1", self.dir), [])

    def test_no_cuenta_las_que_tienen_valor_por_defecto_las_asignadas_las_del_shell_ni_los_parametros(self):
        script = """#!/usr/bin/env bash
set -euo pipefail
S="${ANDROID_SERIAL:-emulator-5554}"
INTENTOS=3
for i in 1 2 3; do echo "$i de $INTENTOS en $S desde $HOME con $1 y $?"; done
read -r respuesta < /dev/tty
echo "$respuesta ${OPCIONAL:-} ${OBLIGATORIA:?falta}"
adb -s "$S" shell input text "$PERF_USUARIO"
"""
        self.assertEqual(perf.shell_env_names(script), {"OBLIGATORIA", "PERF_USUARIO"})

    def test_lee_el_script_y_el_flow_que_nombra_el_comando(self):
        folder = self.plan.parent
        write(folder / "preparar.sh", '#!/usr/bin/env bash\nadb shell input text "$PERF_USUARIO"\n')
        self.assertEqual(perf.prepare_env_names("bash %s" % (folder / "preparar.sh"), folder), ["PERF_USUARIO"])
        self.assertEqual(perf.prepare_env_names("bash preparar.sh && sleep 2", folder), ["PERF_USUARIO"])  # relativo a la carpeta
        self.assertEqual(perf.prepare_env_names("bash no-existe.sh", folder), [])
        write(folder / "preparar.yaml", "appId: com.example.app\nenv:\n    IDIOMA: es\n---\n- inputText:\n    text: ${PERF_USUARIO}\n"
                                        "- inputText: ${PERF_CLAVE}\n- inputText: ${IDIOMA}\n- inputText: ${PERF_OTRA}\n"
                                        "- assertTrue: ${maestro.copiedText == PERF_USUARIO}\n")
        command = 'maestro test -e PERF_USUARIO="$USUARIO_QA" -e PERF_CLAVE=fija %s > /dev/null' % (folder / "preparar.yaml")
        # PERF_USUARIO y PERF_CLAVE llegan por -e (lo que hay que tener es USUARIO_QA); IDIOMA lo define el flow
        self.assertEqual(perf.prepare_env_names(command, folder), ["PERF_OTRA", "USUARIO_QA"])
        for flag in ("--env PERF_USUARIO=", "--env=PERF_USUARIO="):  # las otras formas de pasarle una variable a Maestro
            self.assertEqual(perf.prepare_env_names(command.replace("-e PERF_USUARIO=", flag), folder),
                             ["PERF_OTRA", "USUARIO_QA"], flag)

    def test_el_shell_corriente_de_un_script_no_se_confunde_con_variables_de_entorno(self):
        script = """#!/usr/bin/env bash
# exporta $PERF_COMENTADA antes de correr
set -euo pipefail
tocar() { local x=$1 y=$2; adb shell input tap "$x" "$y"; }
ultimo() { adb devices | awk '{print $NF, $NR}'; }
adb shell 'pid=$(pidof com.example.app); kill $pid; ls $EXTERNAL_STORAGE'
while read -r serial state; do echo "$serial $state"; done < <(adb devices)
while read -r SERIAL ESTADO; do echo "$SERIAL $ESTADO"; done < <(adb devices)
if out=$(adb shell getprop ro.build.version.sdk); then echo "$out"; fi
TOTAL=0; TOTAL+=1; (( INTENTOS += 1 )); A=1 B=2 true; echo "$TOTAL $INTENTOS $A $B"
case "${1:-}" in a) MODO=rapido;; *) MODO=lento;; esac; echo "$MODO"
for PASO in 1 2; do echo "$PASO"; done
getopts "s:" OPCION; printf -v NOMBRE '%s' x; echo "$OPCION $NOMBRE $opt $Mixta"
echo "$PERF_DE_VERDAD"
"""
        self.assertEqual(perf.shell_env_names(script), {"PERF_DE_VERDAD"})
        for name, body in (
                ("guarda con valor por defecto", 'if [ -n "${ANDROID_SERIAL:-}" ]; then ADB="adb -s $ANDROID_SERIAL"; fi\n$ADB devices\n'),
                ("asignación por defecto", ': "${SERIAL:=emulator-5554}"\nadb -s "$SERIAL" devices\n'),
                ("archivo incluido", 'source "$(dirname "$0")/comun.sh"\nadb -s "$SERIAL" shell input text "$PERF_USUARIO"\n'),
                ("incluido con punto", '. ./comun.sh; adb -s "$SERIAL" devices\n'),
                ("variables del shell", 'echo "$EPOCHSECONDS $BASHPID $COLUMNS"\n'),
                ("escapada para el dispositivo", 'adb shell "echo \\$EPOCHREALTIME \\$ANDROID_DATA"\n'),
                ("comillas simples de varias líneas", "adb devices | awk '\n  { print $NF, $CAMPO }\n'\nadb shell '\n  ls $DIRECTORIO\n'\n"),
                ("heredoc sin expansión", "cat <<'EOF'\nusa $PERF_CLAVE\nEOF\n"),
                ("carga un .env", "export $(grep -v '^#' .env | xargs)\nadb shell input text \"$PERF_USUARIO\"\n"),
                ("evalúa lo que carga", 'eval "$(cat credenciales)"\nadb shell input text "$PERF_USUARIO"\n'),
                ("bandera opcional", '[ -n "$DETALLE" ] && set -x\nif [[ -z $MODO_LENTO ]]; then sleep 1; fi\necho "$DETALLE"\n'),
                ("apóstrofo entre comillas dobles", "echo \"can't open\"\nadb shell 'ls $EXTERNAL_STORAGE'\n"),
                ("# entre comillas simples", "adb shell 'echo # $ANDROID_DATA'\nadb shell 'ls $EXTERNAL_STORAGE'\n"),
                ("variables de las herramientas", 'adb -s $ANDROID_SERIAL devices; ls $ANDROID_HOME; [ "$CI" = true ]\n'),
                ("comillas simples dentro de una sustitución", 'SD="$(adb shell \'echo $EXTERNAL_STORAGE\')"\n'
                                                              'N="$(adb shell \'ls $EXTERNAL_STORAGE/Download | wc -l\')"\n'),
                ("comilla doble entre simples en una sustitución", 'L="$(echo "$linea" | sed \'s/"//g\')"\n'
                                                                  "adb shell 'ls $EXTERNAL_STORAGE'\n"),
                ("aritmética y sustituciones anidadas", 'T="$(( $(date +%s) - 5 ))"; U="$(basename "$(dirname \'$NO\')")"\n'
                                                        "adb shell 'ls $EXTERNAL_STORAGE'\n"),
                ("comillas simples entre acentos graves", 'SD="`adb shell \'echo $EXTERNAL_STORAGE\'`"\n'
                                                         'echo "sdk: `adb shell \'getprop ro.build.version.sdk; echo $ANDROID_ROOT\'`"\n'
                                                         "adb shell 'ls $EXTERNAL_STORAGE'\n"),
                ("variables de Maestro", 'echo "$MAESTRO_DRIVER_STARTUP_TIMEOUT"\n')):
            self.assertEqual(perf.shell_env_names(body), set(), name)
        self.assertEqual(perf.shell_env_names("echo \"no es un comentario # $PERF_CLAVE\"  # sí lo es: $PERF_OTRA\n"), {"PERF_CLAVE"})
        self.assertEqual(perf.prepare_env_names("dotenv run -- bash preparar.sh $PERF_USUARIO", self.plan.parent), [])
        self.assertEqual(perf.shell_env_names('CLAVE="$(printf %s "$PERF_CLAVE")"; adb shell input text "$(echo "$PERF_USUARIO")"'),
                         {"PERF_CLAVE", "PERF_USUARIO"})  # dentro de una sustitución entre comillas dobles se sigue viendo
        self.assertEqual(perf.shell_env_names('adb shell input text "`echo "$PERF_USUARIO"`"; echo "$PERF_CLAVE"'),
                         {"PERF_CLAVE", "PERF_USUARIO"})
        self.assertEqual(perf.shell_env_names('test -n "${PERF_CLAVE:?falta}" && echo "${PERF_USUARIO}"'), {"PERF_CLAVE", "PERF_USUARIO"})
        flow = self.plan.parent / "comentado.yaml"
        write(flow, "appId: com.example.app\nenv: {USUARIO: demo, IDIOMA: es}\n---\n# - inputText: ${PERF_OTP}\n"
                    "- inputText: ${USUARIO}\n- inputText: ${usuario}\n- takeScreenshot: ${MAESTRO_FILENAME}\n"
                    "- inputText: ${PERF_CLAVE}  # la clave\n")
        self.assertEqual(perf.prepare_env_names("maestro test %s" % flow, self.plan.parent), ["PERF_CLAVE"])
        # los ejemplos de la guía: el script de preparar con adb y el comando con Maestro
        guide = (SCRIPT.parent.parent / "references" / "ficha.md").read_text(encoding="utf-8")
        example = guide[guide.index("#!/usr/bin/env bash\n   # preparar.sh"):guide.index("hay \"Inicio\"")]
        self.assertEqual(perf.shell_env_names(example), set())
        self.assertEqual(perf.prepare_env_names('maestro --device <serial> test -e PERF_USUARIO="$PERF_USUARIO" -e '
                                                'PERF_CLAVE="$PERF_CLAVE" <carpeta>/preparar.yaml > /dev/null 2>&1 && sleep 2',
                                                self.dir), ["PERF_CLAVE", "PERF_USUARIO"])

    def test_capturar_trata_como_requeridas_las_que_el_plan_no_declara_y_se_detiene_si_faltan(self):
        self.set_prepare('echo "$PERF_USUARIO $PERF_CLAVE" > /dev/null', requiere_env=["PERF_USUARIO"])
        self.env["PERF_USUARIO"] = "usuario.demo"
        self.env.pop("PERF_CLAVE", None)
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("⚠ 'preparar' del flujo 'home' usa variables de entorno que el plan no declara: PERF_CLAVE. Las trato "
                      "como requeridas;", result.stdout)
        self.assertIn('decláralas en el flujo: "requiere_env": ["PERF_CLAVE"]', result.stdout)
        self.assertIn("faltan variables de entorno que el flujo 'home' necesita (requiere_env, o las usa 'preparar' sin que el "
                      "plan las declare): PERF_CLAVE.", result.stderr)
        self.assertIn("o usa --forzar", result.stderr)
        self.assertFalse((self.dir / "adb.log").exists())  # antes de compilar y de tocar el dispositivo
        self.assertNotIn("usuario.demo", result.stdout + result.stderr)

    def test_con_la_variable_presente_avisa_sigue_y_enmascara_su_valor(self):
        self.set_prepare('echo "tipeando $PERF_CLAVE"; echo "falla con $PERF_CLAVE tras $ESPERA intentos" >&2; exit 7')
        self.env.update({"PERF_CLAVE": "clave-de-mentira", "ESPERA": "3"})
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)  # 'preparar' falla: se ve su cola enmascarada
        self.assertIn("usa variables de entorno que el plan no declara: ESPERA, PERF_CLAVE", result.stdout)
        self.assertIn("    falla con *** tras 3 intentos", result.stdout)  # un valor de un carácter no se enmascara
        self.assertNotIn("tipeando", result.stdout)  # sin requiere_env la salida estándar se sigue descartando
        self.assertNotIn("clave-de-mentira", result.stdout + result.stderr)
        self.assertNotIn("clave-de-mentira", (self.plan.parent / "logs" / "preparar.log").read_text(encoding="utf-8"))

    def test_forzar_sigue_si_solo_faltan_las_no_declaradas_y_siguiente_lo_avisa(self):
        self.set_prepare('echo "${NO_HACE_FALTA}" > /dev/null')
        self.env.pop("NO_HACE_FALTA", None)
        self.tp_outputs(GOOD)
        self.assertEqual(self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba").returncode, 3)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba", "--forzar")
        self.assertIn("⚠ faltan en el entorno NO_HACE_FALTA, que 'preparar' usa sin declarar: sigo por --forzar", out)
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertIn("⚠ 'preparar' del flujo 'home' usa variables de entorno que el plan no declara: NO_HACE_FALTA", out)
        self.set_prepare('echo "${NO_HACE_FALTA}" > /dev/null', requiere_env=["NO_HACE_FALTA"])
        self.assertNotIn("no declara", self.ok("siguiente", "--carpeta", self.plan.parent))
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba", "--forzar")
        self.assertEqual(result.returncode, 3)  # declarada y ausente: --forzar no la salta
        self.assertIn("necesita (requiere_env): NO_HACE_FALTA.", result.stderr)


class HumanPauseTest(DeviceBase):
    """`perf.py pausa`: un paso humano dentro del recorrido se ve y se responde en la terminal, y sin terminal falla enseguida."""

    def run_pause(self, answer, *words):
        class Terminal(io.StringIO):
            def close(self):  # `pausa` cierra la terminal al terminar: aquí se conserva para leer lo que mostró
                pass

        reader, writer = Terminal(answer), Terminal()
        original, perf.open_tty = perf.open_tty, lambda: (reader, writer)
        try:
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                code = perf.main(["pausa"] + list(words))
        finally:
            perf.open_tty = original
        return code, writer.getvalue(), errors.getvalue()

    def test_muestra_el_texto_con_un_pitido_y_sigue_con_enter(self):
        code, shown, errors = self.run_pause("\n", "Autoriza la operación en la otra app y vuelve")
        self.assertEqual(code, 0)
        self.assertIn("\a", shown)
        self.assertIn("▶ PAUSA · Autoriza la operación en la otra app y vuelve", shown)
        self.assertIn("x + Enter si esta corrida no vale", shown)
        self.assertNotIn("✖", errors)  # sin error propio (otro test puede dejar un ResourceWarning en stderr)
        self.assertEqual(self.run_pause("listo\n", "varias", "palabras")[0], 0)
        self.assertIn("▶ PAUSA · varias palabras", self.run_pause("\n", "varias", "palabras")[1])
        self.assertIn("▶ PAUSA · haz el paso que te toca", self.run_pause("\n")[1])  # sin texto, uno por defecto

    def test_con_x_sale_con_codigo_1_para_que_la_corrida_se_repita(self):
        for answer in ("x\n", " X \n"):
            code, _, errors = self.run_pause(answer, "Autoriza")
            self.assertEqual(code, 1, answer)
            self.assertIn("corrida descartada por la persona", errors)

    def test_sin_terminal_falla_enseguida_con_codigo_3_y_un_mensaje_claro(self):
        self.env["HB_PERF_TTY"] = str(self.dir / "no" / "existe")
        result = self.perf("pausa", "Autoriza")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("pausa: no hay una terminal interactiva donde mostrar la pausa y esperar la respuesta", result.stderr)
        self.assertIn("lo corre la persona, en su terminal", result.stderr)
        code, _, errors = self.run_pause("", "Autoriza")  # la terminal se cerró: tampoco se queda esperando
        self.assertEqual(code, 3)
        self.assertIn("no hay una terminal interactiva", errors)

    def route(self, body="pausa \"Autoriza la operación\"\n"):
        script = self.plan.parent / "recorrido.sh"
        write(script, "#!/usr/bin/env bash\nset -euo pipefail\n"
                      "pausa() { %s -I \"%s\" pausa \"$1\" || exit $?; }\n%s" % (sys.executable, SCRIPT, body))
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["recorrido"] = "bash %s" % script
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        return script

    def test_capturar_y_la_prueba_esperan_a_la_persona_aunque_la_salida_del_recorrido_no_se_vea(self):
        self.route()
        tty = self.dir / "terminal.txt"
        self.env["HB_PERF_TTY"] = str(tty)
        self.tp_outputs(GOOD)
        write(tty, "\n")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("corrida de prueba", out)
        self.assertIn("▶ PAUSA · Autoriza la operación", tty.read_text(encoding="utf-8"))  # se escribió en la terminal
        self.assertNotIn("PAUSA", out)  # y no en la salida del comando
        write(tty, "\n\n")  # una respuesta por corrida
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2",
                      "--calentamiento", "0", "--sin-compilar")
        self.assertIn("corrida 2/2", out)
        self.assertEqual(tty.read_text(encoding="utf-8").count("▶ PAUSA"), 2)

    def test_una_x_en_la_pausa_invalida_la_corrida_y_se_repite(self):
        self.route()
        tty = self.dir / "terminal.txt"
        self.env["HB_PERF_TTY"] = str(tty)
        self.tp_outputs(GOOD)
        write(tty, "x\n")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("la corrida de prueba fue inválida: el recorrido terminó con código 1", result.stderr)

    def test_sin_terminal_la_captura_se_detiene_antes_de_compilar_y_de_tocar_el_dispositivo(self):
        script = self.route()
        self.env["HB_PERF_TTY"] = str(self.dir / "no" / "existe")
        self.tp_outputs(GOOD)
        for extra in (["--prueba"], ["--fase", "antes", "--corridas", "5"]):
            result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", *extra)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertIn("el recorrido del flujo 'home' tiene una pausa humana (perf.py pausa) y no hay una terminal "
                          "interactiva", result.stderr)
        self.assertFalse((self.dir / "adb.log").exists())
        self.assertTrue(perf.uses_pause("bash %s" % script, self.plan.parent))
        self.assertTrue(perf.uses_pause('python3 -I "/ruta con espacios/perf.py" pausa "Autoriza"', self.plan.parent))
        self.assertFalse(perf.uses_pause("adb shell input tap 1 2 && sleep 3", self.plan.parent))

    def test_con_un_paso_humano_siguiente_pide_cinco_corridas_y_el_estado_cuenta_los_recorridos(self):
        folder = self.dir / "reports" / "perf" / "pago"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "pago", "--serial", "emulator-5554")
        script = folder / "recorrido.sh"
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["flujos"]["pago"]["recorrido"] = "bash %s" % script
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("siguiente", "--carpeta", folder)
        self.assertIn("--fase antes --corridas 10", out)  # la pausa de la plantilla está comentada: es automático
        self.assertNotIn("Paso humano", (folder / "estado.md").read_text(encoding="utf-8"))
        script.write_text(script.read_text(encoding="utf-8").replace("# pausa()", "pausa()").replace('# pausa "', 'pausa "'),
                          encoding="utf-8")
        out = self.ok("siguiente", "--carpeta", folder)
        self.assertIn("--fase antes --corridas 5", out)
        self.assertIn("Tú: atiende la pausa del recorrido en tu terminal (haz el paso que pide y presiona Enter) en cada una "
                      "de las 5 corridas (más 1 de calentamiento).", out)
        state = (folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("- Paso humano: el recorrido tiene una pausa (`perf.py pausa`)", state)
        self.assertIn("Hasta el cierre son **19 recorridos** (1 de prueba + 3 fases × (1 de calentamiento + 5 corridas))", state)
        self.assertIn('o usa triage (`"profundidad": "triage"`)', state)
        plan["profundidad"] = "triage"
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("siguiente", "--carpeta", folder)
        self.assertIn("--fase antes --corridas 3", out)
        self.assertIn("**5 recorridos** (1 de prueba + 1 fase × (1 de calentamiento + 3 corridas))",
                      (folder / "estado.md").read_text(encoding="utf-8"))

    def test_la_plantilla_del_recorrido_trae_la_pausa_comentada_y_asi_no_cuenta(self):
        folder = self.dir / "reports" / "perf" / "pago"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "pago", "--serial", "emulator-5554")
        script = folder / "recorrido.sh"
        text = script.read_text(encoding="utf-8")
        self.assertIn('# pausa() { python3 -I "%s" pausa "$1" || exit $?; }' % SCRIPT, text)
        self.assertIn('# pausa "Autoriza la operación en la otra app, vuelve a esta y presiona Enter"', text)
        self.assertIn('declárala en "pausas" del plan', text)
        self.assertFalse(perf.uses_pause("bash %s" % script, folder))  # comentada: el recorrido no tiene pausa
        self.assertEqual(subprocess.run(["bash", "-n", str(script)]).returncode, 0)
        script.write_text(text.replace("# pausa()", "pausa()").replace('# pausa "', 'pausa "'), encoding="utf-8")
        self.assertTrue(perf.uses_pause("bash %s" % script, folder))
        self.assertEqual(subprocess.run(["bash", "-n", str(script)]).returncode, 0)


def pause_flow(**extra):
    flow = {"pausas": [{"desde": {"marca": "MARK autorizacion_salida"}, "hasta": {"marca": "MARK autorizacion_regreso"}}]}
    flow.update(extra)
    return flow


def pause_trace(mark_ns=3000):
    """Una operación con un paso humano: la app llega a la salida (1 s), la persona autoriza (1 a 61 s) y la app termina.
    Cada marca dura algo, como en un dispositivo (un beginSection y un endSection)."""
    frames = [("frame", i * 20 * MS, 16 * MS, 0, "None") for i in range(50)] \
        + [("frame", 61000 * MS + i * 20 * MS, 16 * MS, 0, "None") for i in range(50)]
    marks = [("seccion", 100 * MS, mark_ns, 0, "MARK operacion_inicio"), ("seccion", 1000 * MS, mark_ns, 0, "MARK autorizacion_salida"),
             ("seccion", 61000 * MS, mark_ns, 0, "MARK autorizacion_regreso"), ("seccion", 62000 * MS, mark_ns, 0, "MARK operacion_fin")]
    return [("proceso", 0, 0, 0, PKG), ("limites", 0, 70000 * MS, 0, "")] + frames + marks


class PausesTest(DeviceBase):
    """`pausas` del plan: nada se mide a través del tiempo que pone una persona."""

    def load(self, flow):
        path = self.dir / "plan-pausas.json"
        write(path, json.dumps({"paquete": PKG, "flujos": {"pago": flow}}))
        return perf.load_plan(path)

    def test_el_plan_valida_la_forma_de_las_pausas(self):
        self.load(pause_flow())
        for bad in ("MARK a", [{"desde": {"marca": "MARK a"}}], [["MARK a", "MARK b"]],
                    [{"desde": {"marca": "MARK a"}, "hasta": {"marca": "MARK b", "punto": "medio"}}]):
            with self.assertRaises(perf.PerfError, msg=str(bad)) as caught:
                self.load({"pausas": bad})
            self.assertIn("'pago.pausas' es una lista de {\"desde\", \"hasta\"}", str(caught.exception))

    def test_rechaza_lo_que_empieza_donde_empieza_la_pausa_o_termina_donde_termina(self):
        out, back = {"marca": "MARK autorizacion_salida"}, {"marca": "MARK autorizacion_regreso"}
        start, end = {"marca": "MARK operacion_inicio"}, {"marca": "MARK operacion_fin"}
        for extra, label in (
                ({"metricas_usuario": [{"nombre": "espera_ms", "desde": out, "hasta": back}]}, "la métrica 'espera_ms'"),
                ({"metricas_usuario": [{"nombre": "total_ms", "desde": start, "hasta": back}]}, "la métrica 'total_ms'"),
                ({"segmentos": [{"nombre": "fuera", "desde": out, "hasta": end}]}, "el tramo 'fuera'"),
                ({"segmentos": [{"nombre": "fuera", "desde": out, "hasta": end, "solo_red": True}]}, "el tramo 'fuera'"),
                ({"ventana": {"desde": start, "hasta": back}}, "la ventana")):
            with self.assertRaises(perf.PerfError, msg=label) as caught:
                self.load(pause_flow(**extra))
            self.assertIn("%s cruza la pausa de 'MARK autorizacion_salida' a 'MARK autorizacion_regreso'" % label,
                          str(caught.exception))
            self.assertIn("tiempo de una persona", str(caught.exception))
        # a cada lado de la pausa sí: hasta la salida, y desde el regreso
        plan = self.load(pause_flow(
            ventana={"desde": back, "hasta": end},
            metricas_usuario=[{"nombre": "hasta_salida_ms", "desde": start, "hasta": out},
                              {"nombre": "desde_regreso_ms", "desde": back, "hasta": end}],
            segmentos=[{"nombre": "cierre", "desde": back, "hasta": end, "solo_red": True}]))
        self.assertEqual(perf.static_pause_conflicts(plan["flujos"]["pago"]), [])
        # una métrica sobre una sola sección (la llamada que precede a la salida) no se rechaza por su nombre
        call = {"marca": "HTTP POST /autorizaciones"}
        self.load({"pausas": [{"desde": call, "hasta": back}],
                   "metricas_usuario": [{"nombre": "autorizar_ms", "desde": call, "hasta": call}]})

    def test_sobre_la_traza_detecta_cualquier_medicion_que_se_solape_con_la_pausa(self):
        start, end = {"marca": "MARK operacion_inicio"}, {"marca": "MARK operacion_fin"}
        out, back = {"marca": "MARK autorizacion_salida"}, {"marca": "MARK autorizacion_regreso"}
        flow = pause_flow(ventana={"desde": start, "hasta": end},
                          metricas_usuario=[{"nombre": "total_ms", "desde": start, "hasta": end},
                                            {"nombre": "hasta_salida_ms", "desde": start, "hasta": out}],
                          segmentos=[{"nombre": "cierre", "desde": back, "hasta": end}])
        self.load(flow)  # por los nombres de las marcas no se ve: solo con la traza
        info = perf.trace_metrics(pause_trace(), 60, flow, set(), 34)[2]
        self.assertEqual(info["cruzan_pausa"], [
            "la ventana cruza la pausa de 'MARK autorizacion_salida' a 'MARK autorizacion_regreso'",
            "la métrica 'total_ms' cruza la pausa de 'MARK autorizacion_salida' a 'MARK autorizacion_regreso'"])
        # el plan que recomienda la guía: una métrica hasta la salida, otra desde el regreso, la ventana (con su margen)
        # y un tramo a cada lado. Las marcas de borde se comparten con la pausa y no cuentan como cruce.
        flow["ventana"] = {"desde": start, "hasta": out, "margen_ms": 500}
        flow["metricas_usuario"] = [flow["metricas_usuario"][1], {"nombre": "desde_regreso_ms", "desde": back, "hasta": end}]
        for mark_ns in (0, 3000, 2 * MS):
            metrics, invalid, info = perf.trace_metrics(pause_trace(mark_ns), 60, flow, set(), 34)
            self.assertEqual(info["cruzan_pausa"], [], mark_ns)
            self.assertIsNone(invalid)
            self.assertEqual({m[0]: m[1] for m in metrics}["hasta_salida_ms"], 900 + mark_ns / 1e6)
        self.assertEqual(perf.pause_bounds(pause_trace(), flow["pausas"][0]), (1000 * MS + 3000, 61000 * MS))
        self.assertEqual(perf.trace_metrics(pause_trace(), 60, {"ventana": {"desde": start, "hasta": end}}, set(), 34)[2]
                         ["cruzan_pausa"], [])  # sin pausas declaradas no hay nada que cruzar

    def test_capturar_y_la_prueba_se_detienen_con_el_motivo_si_el_plan_mide_tiempo_humano(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(pause_flow(ventana={"desde": {"marca": "MARK operacion_inicio"},
                                                          "hasta": {"marca": "MARK operacion_fin"}}))
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marks = "".join('"seccion",%d,2000,0,"%s"\n' % (ts * MS, name) for ts, name in (
            (10, "MARK operacion_inicio"), (100, "MARK autorizacion_salida"), (300, "MARK autorizacion_regreso"),
            (400, "MARK operacion_fin")))
        self.tp_outputs(GOOD + marks)
        for extra in (["--prueba"], ["--fase", "antes", "--corridas", "3", "--calentamiento", "0", "--sin-compilar"]):
            result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", *extra)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("✖ el plan mide tiempo humano: la ventana cruza la pausa de 'MARK autorizacion_salida' a "
                          "'MARK autorizacion_regreso'", result.stderr)
            self.assertNotIn("inválida", result.stdout)  # no es una corrida mala: no se repite
        self.assertFalse((self.plan.parent / "metricas.csv").exists())


def network_trace():
    """Dos tramos con llamadas: en `consulta` una carga duplicada (solapada y repetida); en `pago`, dos llamadas distintas."""
    frames = [("frame", i * 20 * MS, 16 * MS, 0, "None") for i in range(200)]
    marks = [("seccion", 100 * MS, 0, 0, "NAV consulta"), ("seccion", 1000 * MS, 0, 0, "MARK consulta"),
             ("seccion", 2000 * MS, 0, 0, "MARK operacion_inicio"), ("seccion", 3000 * MS, 0, 0, "MARK operacion_fin")]
    calls = [("seccion", 200 * MS, 300 * MS, 0, "HTTP GET /catalogo #1a2b"), ("seccion", 260 * MS, 100 * MS, 0, "TTFB GET /catalogo #1a2b"),
             ("seccion", 250 * MS, 500 * MS, 0, "HTTP GET /catalogo #1a2b"), ("seccion", 300 * MS, 200 * MS, 0, "TTFB GET /catalogo #1a2b"),
             ("seccion", 990 * MS, 2000 * MS, 0, "HTTP POST /pagos"),  # empieza en `consulta` y termina después: es de `consulta`
             ("seccion", 2100 * MS, 400 * MS, 0, "HTTP POST /autorizaciones"), ("seccion", 2150 * MS, 80 * MS, 0, "TTFB POST /autorizaciones"),
             ("seccion", 2600 * MS, 200 * MS, 0, "HTTP GET /estado"),
             ("seccion", 3500 * MS, 100 * MS, 0, "HTTP GET /novedades")]  # después del último tramo: fuera
    return [("proceso", 0, 0, 0, PKG), ("limites", 0, 5000 * MS, 0, "")] + frames + marks + calls


def network_flow(**extra):
    flow = {"segmentos": [
        {"nombre": "consulta", "desde": {"marca": "NAV consulta"}, "hasta": {"marca": "MARK consulta"}},
        {"nombre": "pago", "desde": {"marca": "MARK operacion_inicio"}, "hasta": {"marca": "MARK operacion_fin"}, "solo_red": True}]}
    flow.update(extra)
    return flow


class SegmentNetworkTest(DeviceBase):
    """Red por tramo y tramos `solo_red`: cada llamada HTTP se asigna al tramo donde empieza."""

    def metrics(self, rows, flow, known=()):
        out, invalid, info = perf.trace_metrics(rows, 60, flow, set(known), 34)
        self.assertIsNone(invalid)
        return {m[0]: m for m in out}, info

    def test_cada_llamada_va_al_tramo_donde_empieza_con_su_mediana_ttfb_repetidas_y_solapadas(self):
        m, info = self.metrics(network_trace(), network_flow())
        self.assertEqual(m["consulta red_llamadas"][1:], (3, "llamadas", "app"))
        self.assertEqual(m["consulta red_ms"][1:], (500, "ms", "e2e"))  # mediana de 300, 500 y 2000
        self.assertEqual(m["consulta red_ttfb_ms"][1:], (150, "ms", "e2e"))  # mediana de 100 y 200
        self.assertEqual(m["consulta red_repetidas_2s"][1:], (1, "llamadas", "app"))
        self.assertEqual(m["consulta red_solapadas"][1:], (1, "llamadas", "app"))
        self.assertEqual(m["pago red_llamadas"][1], 2)
        self.assertEqual(m["pago red_ms"][1], 300)
        self.assertEqual(m["pago red_ttfb_ms"][1], 80)
        self.assertEqual((m["pago red_repetidas_2s"][1], m["pago red_solapadas"][1]), (0, 0))
        self.assertEqual(m["red_llamadas"][1], 6)  # las de la corrida entera no cambian: 3 + 2 + 1 fuera de los tramos
        self.assertEqual((m["red_solapadas"][1], m["red_repetidas_2s"][1]), (1, 1))
        self.assertEqual(info["red_fuera"], {"GET /novedades": 1})
        self.assertEqual(info["red_por_tramo"][0]["endpoints"], {"GET /catalogo": 2, "POST /pagos": 1})

    def test_un_tramo_solo_red_no_trae_frames_ni_hilo_y_los_demas_no_cambian(self):
        m, _ = self.metrics(network_trace(), network_flow())
        self.assertIn("consulta hilo_max_ms", m)
        self.assertIn("consulta frame_p90_ms", m)
        self.assertEqual(sorted(k for k in m if k.startswith("pago ")),
                         ["pago red_llamadas", "pago red_ms", "pago red_repetidas_2s", "pago red_solapadas", "pago red_ttfb_ms"])
        flow = network_flow()
        self.assertEqual(perf.segment_metric_names(flow), ["consulta hilo_max_ms", "consulta frame_p90_ms", "consulta jank_app_pct"])
        self.assertIn("pago red_llamadas", perf.segment_network_names(flow))
        without = {k: v for k, v in self.metrics(network_trace(), {})[0].items()}
        self.assertEqual({k: v for k, v in m.items() if not k.startswith(("consulta ", "pago "))}, without)  # sin tramos, como hoy

    def test_sin_llamadas_solo_el_tramo_solo_red_trae_su_conteo_en_cero(self):
        rows = [r for r in network_trace() if not r[4].startswith(("HTTP ", "TTFB "))]
        m, _ = self.metrics(rows, network_flow())
        self.assertEqual(m["pago red_llamadas"][1], 0)
        self.assertNotIn("pago red_ms", m)
        self.assertNotIn("consulta red_llamadas", m)  # sin red en la corrida, un tramo normal queda como antes
        self.assertNotIn("red_llamadas", m)
        m, _ = self.metrics(rows, network_flow(), known=["red_llamadas"])  # la investigación ya mide red: sale en cero
        self.assertEqual(m["consulta red_llamadas"][1], 0)

    def test_si_dos_tramos_se_solapan_la_llamada_va_al_primero_del_plan(self):
        flow = network_flow()
        flow["segmentos"].append({"nombre": "todo", "desde": {"marca": "NAV consulta"}, "hasta": {"marca": "MARK operacion_fin"}})
        m, info = self.metrics(network_trace(), flow)
        self.assertEqual((m["consulta red_llamadas"][1], m["pago red_llamadas"][1], m["todo red_llamadas"][1]), (3, 2, 0))

    def test_el_plan_valida_solo_red_y_una_principal_de_red_sin_las_marcas_del_tramo_invalida_la_corrida(self):
        path = self.dir / "plan-red.json"
        flow = network_flow()
        flow["segmentos"][1]["solo_red"] = "si"
        write(path, json.dumps({"paquete": PKG, "flujos": {"f": flow}}))
        with self.assertRaises(perf.PerfError) as caught:
            perf.load_plan(path)
        self.assertIn("'solo_red' (true o false)", str(caught.exception))
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["principales"] = ["pago red_llamadas"]
        plan["flujos"]["home"]["segmentos"] = network_flow()["segmentos"][1:]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marks = GOOD + '"seccion",5000000,0,0,"MARK operacion_inicio"\n"seccion",250000000,0,0,"MARK operacion_fin"\n'
        self.tp_outputs(GOOD, marks, marks)
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2",
                      "--calentamiento", "0", "--sin-compilar")
        self.assertIn("sin marcas para pago red_llamadas: el recorrido no completó el flujo", out)
        data = self.read_csv_at(self.plan.parent / "metricas.csv")
        self.assertEqual(sorted((k[2], v["valor"]) for k, v in data.items() if k[1] == "pago red_llamadas"), [("2", "1"), ("3", "1")])
        self.assertFalse([k for k in data if k[1].startswith("pago hilo") or k[1].startswith("pago frame")])

    def read_csv_at(self, path):
        with path.open(newline="", encoding="utf-8") as f:
            return {(r["fase"], r["metrica"], r["corrida"]): r for r in csv.DictReader(f)}

    def csv_text(self, rows):
        header = '"tipo","ts","dur","prof","nombre"\n'
        return header + "".join('"%s",%d,%d,%d,"%s"\n' % row for row in rows)

    def test_el_diagnostico_trae_la_tabla_de_red_por_tramo_de_la_corrida(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["principales"] = ["hilo_max_ms"]
        plan["flujos"]["home"]["segmentos"] = network_flow()["segmentos"]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.tp_outputs(self.csv_text(network_trace()))
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                "--calentamiento", "0", "--sin-compilar")
        self.ok("diagnostico", "--carpeta", self.plan.parent, "--flujo", "home")
        text = (self.plan.parent / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("## Red por tramo: las llamadas que empiezan en cada tramo del plan · `segmentos`", text)
        self.assertIn("| consulta | 3 | GET /catalogo ×2, POST /pagos | 500 | 150 | 1 | 1 |", text)
        self.assertIn("| pago | 2 | GET /estado, POST /autorizaciones | 300 | 80 | 0 | 0 |", text)
        self.assertIn("| (fuera de los tramos) | 1 | GET /novedades | — | — | — | — |", text)
        self.assertIn("sin veredicto estadístico", text)
        self.assertEqual(perf.segment_network_table([], network_flow()["segmentos"]), "")
        plan["flujos"]["home"].pop("segmentos")  # sin tramos, el diagnóstico queda como hoy
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.ok("diagnostico", "--carpeta", self.plan.parent, "--flujo", "home")
        self.assertNotIn("Red por tramo", (self.plan.parent / "diagnostico.md").read_text(encoding="utf-8"))

    def test_el_reporte_inicial_y_el_final_traen_la_red_por_tramo_y_sin_tramos_no_cambia(self):
        folder = self.dir / "reports" / "perf" / "pago"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "pago")
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["principales"] = ["hilo_max_ms"]
        plan["flujos"]["pago"]["segmentos"] = network_flow()["segmentos"]
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        text = rows("antes", "pago", "hilo_max_ms", [30, 31, 29, 30, 32]) + rows("despues", "pago", "hilo_max_ms", [20] * 5)
        for phase, calls, repeated in (("antes", [3, 3, 3, 4, 3], [1] * 5), ("despues", [2] * 5, [0] * 5)):
            text += rows(phase, "pago", "consulta red_llamadas", calls, "llamadas") \
                + rows(phase, "pago", "consulta red_ms", [500, 480, 520, 510, 490], family="e2e") \
                + rows(phase, "pago", "consulta red_ttfb_ms", [150] * 5, family="e2e") \
                + rows(phase, "pago", "consulta red_repetidas_2s", repeated, "llamadas") \
                + rows(phase, "pago", "consulta red_solapadas", repeated, "llamadas")
        write(folder / "metricas.csv", HEADER + text)
        self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
        initial = (folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("## Red por tramo", initial)
        self.assertIn("| pago | consulta | antes | 3 llamadas | 500 ms | 150 ms | 1 llamadas | 1 llamadas |", initial)
        self.assertNotIn("| pago | pago |", initial)  # el tramo sin métricas de red medidas no sale
        self.assertIn("Red por tramo", (folder / "reporte-inicial.html").read_text(encoding="utf-8"))
        self.ok("reporte", "--carpeta", folder)
        final = (folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("| pago | consulta | antes | 3 llamadas | 500 ms | 150 ms | 1 llamadas | 1 llamadas |", final)
        self.assertIn("| pago | consulta | despues | 2 llamadas | 500 ms | 150 ms | 0 llamadas | 0 llamadas |", final)
        self.assertIn("**Red por tramo (`<tramo> red_…`):**", final)
        self.assertEqual(perf.segment_network_md(perf.read_rows(folder / "metricas.csv"), {"flujos": {"pago": {}}}), "")


BACKGROUND_MARK = ('"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.example.app"\n"limites",1000000,89000000,0,""\n'
                   '"vsync",0,0,0,""\n"hilo",1000000,30000000,0,"Choreographer#doFrame"\n'
                   '"seccion",2000000,10000,1,"NAV detalle"\n"seccion",45000000,5000,1,"MARK operacion_inicio"\n"jit",0,0,0,""\n')


class MarksOnAnyThreadTest(unittest.TestCase):
    """Las marcas propias se leen de todos los hilos del proceso, no solo del principal."""

    SPEC = {"metricas_usuario": [{"nombre": "hasta_inicio_ms", "desde": {"marca": "NAV detalle"},
                                  "hasta": {"marca": "MARK operacion_inicio"}, "familia": "app"}]}

    def test_la_consulta_de_secciones_no_filtra_por_hilo(self):
        sql = (SCRIPT.parent.parent / "assets" / "queries" / "metricas.sql").read_text(encoding="utf-8")
        block = next(part for part in sql.split("UNION ALL") if "SELECT 'seccion'" in part)
        self.assertIn("FROM slice\n", block)
        self.assertNotIn("JOIN", block)  # sin thread_track ni thread: cualquier hilo
        self.assertIn("name GLOB 'MARK *'", block)
        main = next(part for part in sql.split("UNION ALL") if "SELECT 'hilo'" in part)
        self.assertIn("t.tid = app.pid", main)  # el hilo principal sí se filtra, y solo ahí

    def test_una_marca_emitida_en_otro_hilo_sirve_de_extremo_de_una_metrica(self):
        # Salida de metricas.sql sobre una traza donde MARK operacion_inicio la emite un hilo de fondo, dentro de otro
        # slice (profundidad 1): llega como 'seccion' y no como 'hilo', y la métrica la encuentra igual.
        header, body = perf.parse_result_sets(BACKGROUND_MARK)[-1]
        metrics, invalid, info = perf.trace_metrics(perf.trace_rows(header, body), 60, self.SPEC, set(), 30)
        self.assertIsNone(invalid)
        self.assertEqual({m[0]: m[1] for m in metrics}["hasta_inicio_ms"], 43.005)
        self.assertEqual(info["faltantes"], [])
        self.assertEqual(info["ultima_marca"][0], "MARK operacion_inicio")

    def test_con_trace_processor_instalado_la_consulta_real_devuelve_la_marca_de_un_hilo_de_fondo(self):
        try:
            tp = perf.find_tp(None)
        except perf.PerfError:
            self.skipTest("trace_processor no está instalado")
        events = [{"name": "process_name", "ph": "M", "pid": 100, "tid": 100, "args": {"name": "com.example.app"}},
                  {"name": "thread_name", "ph": "M", "pid": 100, "tid": 207, "args": {"name": "fondo-1"}},
                  {"name": "Choreographer#doFrame", "ph": "X", "ts": 1000, "dur": 30000, "pid": 100, "tid": 100},
                  {"name": "NAV detalle", "ph": "X", "ts": 2000, "dur": 10, "pid": 100, "tid": 100},
                  {"name": "trabajo", "ph": "X", "ts": 40000, "dur": 50000, "pid": 100, "tid": 207},
                  {"name": "MARK operacion_inicio", "ph": "X", "ts": 45000, "dur": 5, "pid": 100, "tid": 207}]
        sql = perf.fill_sql((SCRIPT.parent.parent / "assets" / "queries" / "metricas.sql").read_text(encoding="utf-8"),
                            "com.example.app", {"INPUT_GLOB": perf.INPUT_SLICES})
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "traza.json"
            trace.write_text(json.dumps({"traceEvents": events}), encoding="utf-8")
            try:
                sets = perf.run_tp(tp, trace, sql)
            except (perf.PerfError, OSError, subprocess.SubprocessError) as error:
                self.skipTest("trace_processor no pudo abrir la traza de prueba: %s" % error)
        if not sets:
            self.skipTest("trace_processor no devolvió filas para la traza de prueba")
        rows = perf.trace_rows(*sets[-1])
        self.assertIn(("seccion", 45000000, 5000, 1, "MARK operacion_inicio"), rows)
        self.assertNotIn("trabajo", [r[4] for r in rows if r[0] == "hilo"])  # 'hilo' es solo el principal
        metrics = perf.trace_metrics(rows, 60, self.SPEC, set(), 30)[0]
        self.assertEqual({m[0]: m[1] for m in metrics}["hasta_inicio_ms"], 43.005)


class KeyboardTest(DeviceBase):
    """`nodos --volcar` avisa si el teclado estaba abierto: las coordenadas cambian con él."""

    def test_avisa_solo_si_el_teclado_estaba_abierto_al_volcar(self):
        self.env["FAKE_PULL"] = UI_XML
        target = self.dir / "inv" / "logs" / "ui.xml"
        out = self.ok("nodos", target, "--volcar", "--texto", "Catálogo")
        self.assertNotIn("teclado", out)
        self.env["FAKE_TECLADO"] = "true"
        out = self.ok("nodos", target, "--volcar", "--texto", "Catálogo")
        self.assertIn("⚠ El teclado estaba abierto al volcar", out)
        self.assertIn("con el teclado en el mismo estado que tendrá el recorrido", out)
        self.assertIn("Toque (centro): adb -s emulator-5554 shell input tap 810 2300", out)  # avisa y sigue
        self.assertIn("dumpsys input_method", (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.assertNotIn("teclado", self.ok("nodos", target, "--texto", "Catálogo"))  # sin --volcar no consulta el dispositivo

    def test_la_plantilla_del_recorrido_cierra_el_teclado_solo_si_esta_abierto_y_sin_cortar_la_corrida(self):
        folder = self.dir / "reports" / "perf" / "pago"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "pago", "--serial", "emulator-5554")
        text = (folder / "recorrido.sh").read_text(encoding="utf-8")
        self.assertIn("# teclado=\"$(adb -s \"$SERIAL\" shell dumpsys input_method | grep -c 'mInputShown=true' || true)\"", text)
        self.assertIn('# if [ "$teclado" != "0" ]; then adb -s "$SERIAL" shell input keyevent 4 && sleep 1; fi', text)
        script = folder / "teclado.sh"  # el bloque, descomentado, con un adb falso: cerrado no falla ni manda BACK
        lines = [line[2:] for line in text.splitlines() if line.startswith(("# teclado=", "# if [ \"$teclado\""))]
        script.write_text("set -euo pipefail\nSERIAL=emulator-5554\n" + "\n".join(lines) + "\n", encoding="utf-8")
        for shown, backs in (("false", 0), ("true", 1)):
            self.env["FAKE_TECLADO"] = shown
            (self.dir / "adb.log").unlink()
            result = subprocess.run(["bash", str(script)], env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.dir / "adb.log").read_text(encoding="utf-8").count('"keyevent", "4"'), backs, shown)

    def test_la_plantilla_de_estado_trae_el_inventario_con_el_cableado_y_los_comandos_del_parche(self):
        folder = self.dir / "reports" / "perf" / "pago"
        self.ok("nuevo", "--carpeta", folder, "--paquete", PKG, "--flujo", "pago")
        state = (folder / "estado.md").read_text(encoding="utf-8")
        section = state[state.index("## Cambios temporales por revertir"):state.index("## Mapa del alcance")]
        self.assertIn("las ediciones de cableado en código de `main`", section)
        self.assertIn("`cd <repo> && git diff --binary -- <archivos> > <parche> && git apply --check -R <parche>`", section)
        self.assertIn("Quitar: `cd <repo> && git apply -R <parche>`", section)
        self.assertIn("Volver a aplicar: `cd <repo> && git apply <parche>`", section)
        for marker in ("<repo>", "<archivos>", "<parche>"):  # de una sola palabra: no cuentan como relleno de la plantilla
            self.assertNotIn(marker, perf.placeholders())


FIXTURE_070 = ROOT / "tests" / "fixtures" / "hb-performance-0.7.0"


class Compat070Test(PerfBase):
    """Una investigación en curso creada con 0.7.0 (plan.json con tramos, una mejora a prueba y `requiere_env`; el
    estado.md de su plantilla; fases.json con datos por flujo) sigue funcionando igual."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "reports" / "perf" / "detalle"
        self.folder.mkdir(parents=True)
        for name in ("plan.json", "estado.md", "metricas.csv", "fases.json"):
            write(self.folder / name, (FIXTURE_070 / name).read_text(encoding="utf-8"))
        for name in ("PERF_USUARIO", "PERF_CLAVE"):  # `siguiente`, `reporte` y `comparar` no necesitan las credenciales
            self.env.pop(name, None)

    def test_el_plan_de_0_7_0_no_trae_ningun_campo_nuevo_y_carga_igual(self):
        plan = perf.load_plan(self.folder / "plan.json")
        text = json.dumps(plan)
        for field in ("pausas", "solo_red", "duracion_max_s"):
            self.assertNotIn(field, text)
        self.assertEqual(perf.user_metric_names(plan), ["lista_a_detalle_ms", "detalle hilo_max_ms", "detalle frame_p90_ms",
                                                         "detalle jank_app_pct"])
        flow = plan["flujos"]["detalle"]
        self.assertEqual(perf.required_env(flow, flow["preparar"], self.folder), (["PERF_USUARIO", "PERF_CLAVE"], []))
        self.assertFalse(perf.has_human_pause(flow, self.folder))
        self.assertFalse(perf.plan_expects_network({"principales": plan["principales"]}, flow))

    def test_siguiente_reporte_inicial_y_comparar_corren_sin_errores(self):
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Siguiente · sesión 4 · cierre", out)  # M1 aplicada y la fase después medida
        self.assertNotIn("no declara", out)  # las variables de `preparar` ya están en requiere_env
        self.assertIn("Ficha (Métricas principales y objetivo, Build y ambiente, Modos)", out)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("- Variables de entorno que necesita (expórtalas antes): `PERF_USUARIO`, `PERF_CLAVE`", state)
        self.assertNotIn("Paso humano", state)
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        initial = (self.folder / "reporte-inicial.md").read_text(encoding="utf-8")
        self.assertIn("| H2 | Frame largo al entrar al detalle, estable en las 5 corridas |", initial)
        self.assertIn("Una captura con muestreo de CPU o probar el cambio", initial)
        self.assertIn("| M1 | Una sola carga del detalle | H1 | red_solapadas | 1 llamadas | 0 llamadas | alta | bajo | bajo | "
                      "aplicada |", initial)
        self.assertIn("Decodificar la imagen de cabecera fuera del hilo principal", initial)
        self.assertNotIn("Red por tramo", initial.split("## Cómo leer este reporte")[0])  # el CSV de 0.7.0 no la trae
        out = self.ok("comparar", self.folder / "metricas.csv")
        self.assertIn("| detalle | lista_a_detalle_ms | e2e | 412 ms / 420 ms | 300 ms / 305 ms | -112 ms | -27.18 % | 0.24 % | "
                      "mejora |", out)
        self.assertIn("| detalle | detalle hilo_max_ms | app | 48 ms / 50 ms | 48 ms / 49 ms | 0 ms | 0 % | 0 % | sin cambio |", out)
        self.assertIn("| detalle | red_solapadas | app | 1 llamadas / 1 llamadas | 0 llamadas / 0 llamadas | -1 llamadas | "
                      "-100 % | 0 % | mejora |", out)
        self.assertNotIn("⚠", out)
        self.ok("reporte", "--carpeta", self.folder, "--html")
        final = (self.folder / "reporte-final.md").read_text(encoding="utf-8")
        self.assertIn("3 hallazgos → 2 mejoras propuestas → 1 aplicadas → 1 funcionaron", final)
        self.assertNotIn("## Red por tramo", final)
        self.assertEqual(perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"))[0], "investigación cerrada")

    def test_las_fases_de_0_7_0_con_datos_por_flujo_se_leen_igual(self):
        phases = perf.read_phases(self.folder)
        self.assertEqual(phases["antes"]["flujos"]["detalle"]["corridas"], 5)
        self.assertEqual(perf.frames_trust(self.folder), ("ok", ""))
        self.assertEqual(perf.phase_warnings(self.folder), [])
        table, notes = perf.builds_table(self.folder)
        self.assertIn("| antes | 2026-03-10T10:00:00 | abc1234 | 1.0 (7) | 2026-03-10 09:00:00 | 60 | completa (speed) | 5 |", table)
        self.assertEqual(notes, [])

    def test_las_metricas_que_calculaba_0_7_0_no_cambian_de_nombre_ni_de_valor(self):
        # traza.json guarda las filas de una traza y lo que 0.7.0 calculó con ellas para el flujo de este plan
        data = json.loads((FIXTURE_070 / "traza.json").read_text(encoding="utf-8"))
        flow = perf.load_plan(self.folder / "plan.json")["flujos"]["detalle"]
        metrics, invalid, _ = perf.trace_metrics([tuple(row) for row in data["filas"]], 60, flow, set(), 34)
        self.assertIsNone(invalid)
        now = {m[0]: list(m) for m in metrics}
        before = {m[0]: m for m in data["metricas"]}
        self.assertEqual(len(before), 30)
        for name, expected in before.items():
            self.assertEqual(now.get(name), expected, name)
        # lo único nuevo es la red por tramo, y va después de lo que ya había
        extra = [m[0] for m in metrics if m[0] not in before]
        self.assertEqual(extra, ["detalle red_llamadas", "detalle red_ms", "detalle red_ttfb_ms", "detalle red_repetidas_2s",
                                 "detalle red_solapadas"])
        self.assertEqual([m[0] for m in metrics][:len(before)], [m[0] for m in data["metricas"]])


class TriageToRigorousTest(PerfBase):
    """De triage a riguroso: `decidir --profundidad`, y `siguiente` pide la línea base completa y el control antes de
    ofrecer la decisión."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = {"paquete": "com.example.app", "principales": ["hilo_max_ms"], "profundidad": "triage",
                     "flujos": {"detalle": {"inicio": "MainActivity", "recorrido": "adb shell input tap 1 1"}},
                     "mejoras": [{"id": "M1", "titulo": "a"}]}
        self.save()
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        write(self.folder / "diagnostico.md", "x")
        write(self.folder / "reporte-inicial.md", "x")

    def save(self):
        write(self.folder / "plan.json", json.dumps(self.plan))

    def measured(self, antes, control=None, skill=perf.VERSION):
        phases, text = {}, HEADER
        for phase, count in (("antes", antes), ("control", control)):
            if count:
                phases[phase] = {"fecha": "2026-11-05T10:00:00", "corridas": count, "version": "1.0 (7)",
                                 "instalada": "2026-11-05 09:00:00"}
                if skill:
                    phases[phase]["skill"] = skill
                text += rows(phase, "detalle", "hilo_max_ms", [40 + i for i in range(count)])
        write(self.folder / "fases.json", json.dumps(phases))
        write(self.folder / "metricas.csv", text)

    def step(self):
        return perf.next_steps(self.folder, self.plan)

    def test_triage_cerrado_dice_como_seguir_y_no_pide_capturas(self):
        self.measured(3)
        title, steps = self.step()
        self.assertEqual(title, "triage cerrado")
        self.assertEqual([s["tipo"] for s in steps], ["archivo", "terminal"])
        self.assertIn("decidir --carpeta", steps[1]["texto"])
        self.assertTrue(steps[1]["texto"].endswith("--profundidad riguroso"))
        self.assertIn("solo si quieres aplicar una mejora", steps[1]["que"])

    def test_un_triage_abierto_con_mejoras_y_sin_reporte_sigue_como_antes(self):
        self.measured(3, skill=None)
        (self.folder / "reporte-inicial.md").unlink()  # la sesión 2 escribió las mejoras y todavía no generó el reporte
        self.assertEqual(self.step()[0], "decisión del usuario (sin chat)")

    def test_riguroso_con_antes_incompleto_pide_las_corridas_que_faltan_antes_de_decidir(self):
        self.plan["profundidad"] = "riguroso"
        self.measured(3, control=10)
        title, steps = self.step()
        self.assertEqual(title, "completar la línea base de riguroso (sin chat)")
        self.assertEqual(len(steps), 2)
        self.assertIn("--fase antes --corridas 7", steps[0]["texto"])
        self.assertNotIn("--rehacer", steps[0]["texto"])
        self.assertIn("tiene 3", steps[0]["que"])
        self.assertIn("agrega --rehacer y pide --corridas 10", steps[0]["tu"])
        self.assertIn("decidir --carpeta", steps[1]["texto"])

    def test_riguroso_sin_control_lo_pide_y_con_recorrido_manual_la_linea_base_es_de_5(self):
        self.plan["profundidad"] = "riguroso"
        self.measured(10)
        title, steps = self.step()
        self.assertEqual(title, "completar la línea base de riguroso (sin chat)")
        self.assertEqual(len(steps), 2)
        self.assertIn("--fase control --corridas 10", steps[0]["texto"])
        self.assertIn("decidir --carpeta", steps[1]["texto"])
        self.plan["flujos"]["detalle"]["recorrido"] = "manual"
        self.measured(3)
        steps = self.step()[1]
        self.assertIn("--fase antes --corridas 2", steps[0]["texto"])
        self.assertIn("--fase control --corridas 5", steps[1]["texto"])
        self.assertIn("decidir --carpeta", steps[2]["texto"])

    def test_riguroso_completo_ofrece_la_decision(self):
        self.plan["profundidad"] = "riguroso"
        self.measured(10, control=10)
        title, steps = self.step()
        self.assertEqual(title, "decisión del usuario (sin chat)")
        self.assertIn("--aprobar M1", steps[0]["texto"])
        self.measured(12, control=5, skill=None)  # de sobra, y de una versión anterior: completa también
        self.assertEqual(self.step()[0], "decisión del usuario (sin chat)")

    def test_con_otra_version_de_la_skill_recomienda_rehacer_en_lugar_de_completar(self):
        self.plan["profundidad"] = "riguroso"
        self.measured(3, skill=None)  # sin el dato: lo midió una versión anterior a 0.9.0
        steps = self.step()[1]
        self.assertIn("--fase antes --corridas 10 --rehacer", steps[0]["texto"])
        self.assertIn("otra versión de hb-performance (anterior a 0.9.0)", steps[0]["que"])
        self.assertIn("--fase control --corridas 10", steps[1]["texto"])
        self.assertNotIn("--rehacer", steps[1]["texto"])
        self.measured(5, control=5, skill=None)  # con control de esa versión: se repite junto con el antes
        steps = self.step()[1]
        self.assertIn("--fase antes --corridas 10 --rehacer", steps[0]["texto"])
        self.assertIn("--fase control --corridas 10 --rehacer", steps[1]["texto"])

    def test_la_version_de_la_skill_se_guarda_por_flujo(self):
        folder = self.dir / "fases"
        folder.mkdir()
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 5,
                                                         "flujos": {"lista": {"corridas": 5}}}}))
        perf.write_phase(folder, "antes", {"fecha": "2026-11-06T10:00:00", "corridas": 3, "skill": perf.VERSION}, "detalle")
        perf.write_phase(folder, "antes", {"fecha": "2026-11-06T11:00:00", "corridas": 1, "skill": perf.VERSION}, "lista")
        record = perf.read_phases(folder)["antes"]
        self.assertEqual(perf.phase_skill(record, "detalle"), perf.VERSION)  # flujo nuevo: la versión que lo midió
        self.assertEqual(perf.phase_skill(record, "lista"), "anterior a 0.9.0")  # ya tenía corridas sin el dato

    def test_una_mejora_ya_aprobada_sin_control_tambien_lo_pide_antes_de_la_sesion_3(self):
        self.plan["profundidad"] = "riguroso"
        self.plan["mejoras"][0]["estado"] = "aprobada"
        self.measured(10)
        title, steps = self.step()
        self.assertEqual(title, "completar la línea base de riguroso (sin chat)")
        self.assertEqual(len(steps), 1)
        self.assertIn("--fase control", steps[0]["texto"])
        self.measured(5, control=5)  # una investigación rigurosa ya decidida sigue igual, tenga las corridas que tenga
        self.assertEqual(self.step()[0], "sesión 3 · M1")

    def test_aprobar_en_el_triage_y_pasar_a_riguroso_tambien_completa_antes(self):
        self.plan["mejoras"][0]["estado"] = "aprobada"
        self.save()
        self.measured(3)
        out = self.ok("decidir", "--carpeta", self.folder, "--profundidad", "riguroso")
        self.assertTrue(json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["desde_triage"])
        self.assertIn("--fase antes --corridas 7", out)
        self.assertIn("--fase control --corridas 10", out)
        self.assertNotIn("sesión 3", out)

    def test_un_triage_sin_mejoras_no_ofrece_pasar_a_riguroso_y_decidir_no_falla_sin_la_clave(self):
        del self.plan["mejoras"]
        self.save()
        self.measured(3)
        title, steps = self.step()
        self.assertEqual((title, [s["tipo"] for s in steps]), ("triage cerrado", ["archivo"]))
        out = self.ok("decidir", "--carpeta", self.folder, "--profundidad", "riguroso")
        self.assertIn("profundidad riguroso (era triage)", out)

    def test_decidir_profundidad_cambia_el_plan_lo_anota_y_da_las_capturas(self):
        self.measured(3)
        out = self.ok("decidir", "--carpeta", self.folder, "--profundidad", "riguroso")
        self.assertEqual(json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["profundidad"], "riguroso")
        self.assertIn("profundidad riguroso (era triage)", out)
        self.assertIn("Siguiente · completar la línea base de riguroso (sin chat)", out)
        self.assertIn("--fase antes --corridas 7", out)
        self.assertIn("--fase control --corridas 10", out)
        self.assertIn("profundidad riguroso (era triage) (perf.py decidir)", (self.folder / "estado.md").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["mejoras"][0].get("estado", "propuesta"),
                         "propuesta")
        result = self.perf("decidir", "--carpeta", self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--profundidad", result.stderr)


class OrphanTraceTest(DeviceBase):
    """Una traza que quedó sin fila en el CSV (captura cortada) no se pisa: se aparta y se avisa."""

    def test_la_traza_huerfana_se_aparta_y_la_corrida_usa_su_numero(self):
        self.tp_outputs(GOOD)
        folder = self.plan.parent
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                "--calentamiento", "0", "--sin-compilar")
        write(folder / "antes" / "home_2.perfetto-trace.gz", "huerfana")
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                      "--calentamiento", "0", "--sin-compilar")
        self.assertRegex(out, r"⚠ había una traza de la corrida 2 sin fila en metricas.csv .*antes-descartada-\d{6}/")
        aside = [d for d in folder.iterdir() if d.name.startswith("antes-descartada-")]
        self.assertEqual(len(aside), 1)
        self.assertEqual((aside[0] / "home_2.perfetto-trace.gz").read_text(encoding="utf-8"), "huerfana")
        self.assertNotEqual((folder / "antes" / "home_2.perfetto-trace.gz").read_bytes(), b"huerfana")
        self.assertEqual(out.count("⚠ había una traza"), 1)

    def test_sin_huerfana_no_avisa_y_una_traza_con_fila_no_se_toca(self):
        folder = self.dir / "inv"
        (folder / "antes").mkdir(parents=True, exist_ok=True)
        csv_path = folder / "metricas.csv"
        self.assertIsNone(perf.set_aside_orphan(folder, folder / "antes", "antes", "home", 1, csv_path))
        write(csv_path, HEADER + rows("antes", "home", "hilo_max_ms", [40]))
        write(folder / "antes" / "home_1.perfetto-trace.gz", "con fila")
        self.assertIsNone(perf.set_aside_orphan(folder, folder / "antes", "antes", "home", 1, csv_path))
        self.assertTrue((folder / "antes" / "home_1.perfetto-trace.gz").is_file())

    def test_completar_antes_con_otro_build_o_con_otra_version_avisa_y_recomienda_rehacer(self):
        self.tp_outputs(GOOD)
        common = ("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1",
                  "--calentamiento", "0", "--sin-compilar")
        self.ok(*common)
        self.assertNotIn("--rehacer", self.ok(*common))  # mismo build y misma versión: se suman sin aviso
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["skill"], perf.VERSION)
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"
        out = self.ok(*common)
        self.assertIn("no es el que midió las corridas que 'antes' ya tiene", out)
        self.assertIn("repite la fase con --rehacer", out)
        self.assertNotIn("no es el que midió", self.ok(*(common + ("--rehacer",))))
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        del phases["antes"]["skill"]  # como la deja una versión anterior
        del phases["antes"]["flujos"]["home"]["skill"]
        write(self.plan.parent / "fases.json", json.dumps(phases))
        out = self.ok(*common)
        self.assertIn("otra versión de hb-performance (anterior a 0.9.0", out)
        self.assertEqual(json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))["antes"]["skill"],
                         "anterior a 0.9.0")


EMPTY_TABLE = '"a"\n'
FIXTURE_TRACES = ROOT / "tests" / "fixtures" / "hb-performance-trazas"
REAL_TP = shutil.which("trace_processor") or shutil.which("trace_processor_shell")


def skill_config(name):
    return perf.config_record(perf.ASSETS / "perfetto" / ("%s.pbtx" % name))


class QueryRequirementsTest(unittest.TestCase):
    """Cada consulta declara qué fuentes necesita y las configuraciones de su grupo las capturan: una consulta no puede
    salir vacía solo porque la configuración no graba su dato."""

    def test_las_fuentes_de_una_configuracion_se_leen_del_pbtx_sin_los_comentarios(self):
        sources = perf.config_sources('data_sources { config { name: "linux.ftrace"\n  ftrace_config {\n'
                                      '  ftrace_events: "sched/sched_switch"  # comentario: "x/y"\n'
                                      '  # ftrace_events: "binder/binder_transaction"\n  atrace_categories: "view"\n'
                                      '  atrace_apps: "com.example.app"\n}}}\n'
                                      'data_sources { config { name: "android.surfaceflinger.frametimeline" } }\n')
        self.assertEqual(sources, ["atrace:view", "atrace_apps", "ds:android.surfaceflinger.frametimeline", "ds:linux.ftrace",
                                   "ftrace:sched/sched_switch"])

    def test_base_y_cpu_capturan_binder_y_completa_la_razon_de_bloqueo(self):
        binder = {"ftrace:binder/binder_transaction", "ftrace:binder/binder_transaction_received"}
        for name in ("base", "cpu", "completa"):
            self.assertLessEqual(binder, set(skill_config(name)["fuentes"]), name)
        self.assertIn("ftrace:sched/sched_blocked_reason", skill_config("completa")["fuentes"])
        self.assertIn("ftrace:sched/sched_waking", skill_config("completa")["fuentes"])
        for name in ("base", "cpu"):  # nada pesado en base: la razón de bloqueo y los wakeups son solo de completa
            self.assertNotIn("ftrace:sched/sched_blocked_reason", skill_config(name)["fuentes"])
            self.assertNotIn("ftrace:sched/sched_waking", skill_config(name)["fuentes"])

    def test_lo_unico_que_cambia_en_base_son_los_dos_eventos_de_binder(self):
        events = [s for s in skill_config("base")["fuentes"] if s.startswith("ftrace:")]
        self.assertEqual(events, ["ftrace:binder/binder_transaction", "ftrace:binder/binder_transaction_received",
                                  "ftrace:sched/sched_process_exit", "ftrace:sched/sched_process_free",
                                  "ftrace:sched/sched_switch", "ftrace:task/task_newtask", "ftrace:task/task_rename"])
        self.assertEqual([s for s in skill_config("base")["fuentes"] if s.startswith("ds:")],
                         ["ds:android.surfaceflinger.frametimeline", "ds:linux.ftrace", "ds:linux.process_stats"])

    def test_cada_consulta_declara_sus_fuentes_y_las_configuraciones_de_su_grupo_las_capturan(self):
        configs = {name: set(skill_config(name)["fuentes"]) for name in perf.SKILL_CONFIGS}
        catalog = perf.query_catalog()
        self.assertGreaterEqual(len(catalog), 18)
        for name, _, groups, sql in catalog:
            requires = perf.query_requires(sql)
            self.assertTrue(requires, "%s no declara '-- requiere:'" % name)
            # cpu y completa son capturas de diagnóstico; el resto corre sobre las trazas de las fases, que se miden
            # con base (y cpu y completa capturan todo lo de base)
            needed = [g for g in groups if g in ("cpu", "completa")] or ["base", "cpu", "completa"]
            for config in needed:
                self.assertEqual([s for s in requires if s not in configs[config]], [],
                                 "%s (grupos %s) pide fuentes que %s.pbtx no captura" % (name, groups, config))
        signal = (perf.ASSETS / "queries" / "senal_bloqueo.sql").read_text(encoding="utf-8")
        self.assertEqual([s for s in perf.query_requires(signal) if s not in configs["base"]], [])

    def test_cpu_y_completa_capturan_todo_lo_de_base(self):
        base = set(skill_config("base")["fuentes"])
        for name in ("cpu", "completa"):
            self.assertLessEqual(base, set(skill_config(name)["fuentes"]), name)

    def test_que_configuraciones_capturan_una_fuente(self):
        self.assertEqual(perf.configs_with(["ds:linux.perf"]), ["cpu"])
        self.assertEqual(perf.configs_with(["ftrace:sched/sched_blocked_reason"]), ["completa"])
        self.assertEqual(perf.configs_with(["ftrace:no/existe"]), [])


class TraceConfigTest(DeviceBase):
    """La configuración con la que se grabó cada traza queda registrada, y las consultas se validan contra ella."""

    def capture(self, *extra):
        return self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--calentamiento", "0", "--sin-compilar", *extra)

    def test_capturar_registra_la_configuracion_junto_a_la_traza_y_en_fases_json(self):
        self.tp_outputs(GOOD)
        self.capture("--fase", "antes", "--corridas", "2")
        folder = self.plan.parent
        base = skill_config("base")
        for run in (1, 2):
            config = perf.trace_config(folder / "antes" / ("home_%d.perfetto-trace.gz" % run))
            self.assertEqual((config["nombre"], config["hash"], config["fuentes"]), ("base", base["hash"], base["fuentes"]))
            self.assertEqual(config["instalada"], "2026-11-05 10:00:00")
        phases = perf.read_phases(folder)
        self.assertEqual(phases["antes"]["configs"], ["base@%s" % base["hash"]])
        self.assertEqual(phases["antes"]["flujos"]["home"]["configs"], ["base@%s" % base["hash"]])
        self.capture("--prueba", "--config", "cpu")
        self.assertEqual(perf.trace_config(folder / "prueba" / "home_1.perfetto-trace.gz")["nombre"], "cpu")
        self.assertIsNone(perf.trace_config(folder / "antes" / "home_9.perfetto-trace.gz"))  # sin registro: desconocida
        self.assertIsNone(perf.trace_config(self.dir / "suelta.perfetto-trace"))

    def test_una_configuracion_propia_se_registra_con_su_nombre_y_sus_fuentes(self):
        self.tp_outputs(GOOD)
        write(self.plan.parent / "mia.pbtx", 'data_sources { config { name: "linux.ftrace" ftrace_config {\n'
                                             '  ftrace_events: "sched/sched_switch"\n  atrace_apps: "{{PAQUETE}}"\n} } }\n')
        self.capture("--prueba", "--config", "mia.pbtx")
        config = perf.trace_config(self.plan.parent / "prueba" / "home_1.perfetto-trace.gz")
        self.assertEqual((config["nombre"], config["fuentes"]),
                         ("mia.pbtx", ["atrace_apps", "ds:linux.ftrace", "ftrace:sched/sched_switch"]))

    def test_en_android_11_la_configuracion_va_sin_los_campos_que_no_conoce_y_frametimeline_es_no_medido(self):
        completa = (perf.ASSETS / "perfetto" / "completa.pbtx").read_text(encoding="utf-8")
        self.assertIn("symbolize_ksyms: true", perf.config_for_sdk(completa, 31))
        self.assertNotIn("symbolize_ksyms:", perf.config_for_sdk(completa, 30))
        self.assertIn("sched/sched_blocked_reason", perf.config_for_sdk(completa, 29))
        self.tp_outputs(GOOD)
        sent = self.dir / "enviada.pbtx"
        self.env.update({"FAKE_SDK": "30", "FAKE_PERFETTO_CONFIG": str(sent)})
        self.capture("--prueba", "--config", "completa")
        self.assertNotIn("symbolize_ksyms:", sent.read_text(encoding="utf-8"))
        self.assertIn("sched/sched_blocked_reason", sent.read_text(encoding="utf-8"))
        trace = self.plan.parent / "prueba" / "home_1.perfetto-trace.gz"
        self.assertEqual(perf.trace_config(trace)["no_disponibles"],
                         {"ds:android.surfaceflinger.frametimeline": "FrameTimeline es de Android 12 o superior"})
        out = self.ok("consulta", trace, "jank_por_tipo")
        self.assertIn("no medido: el dispositivo no entrega ds:android.surfaceflinger.frametimeline (FrameTimeline es de "
                      "Android 12 o superior)", out)
        self.assertNotIn("--config", out)  # ninguna configuración lo arregla
        self.env["FAKE_SDK"] = "34"
        self.capture("--prueba", "--config", "completa")
        self.assertIn("symbolize_ksyms: true", sent.read_text(encoding="utf-8"))
        self.assertEqual(perf.trace_config(trace)["no_disponibles"], {})

    def test_consulta_dice_no_medido_sin_correr_la_consulta_si_la_configuracion_no_captura_la_fuente(self):
        self.tp_outputs(GOOD)
        self.capture("--prueba")
        trace = self.plan.parent / "prueba" / "home_1.perfetto-trace.gz"
        (self.dir / "tp.sql").unlink()
        out = self.ok("consulta", trace, "cpu_por_libreria")
        self.assertIn("no medido: la configuración base no captura ds:linux.perf", out)
        self.assertIn("No quiere decir que no ocurra", out)
        self.assertIn("--config cpu", out)
        self.assertFalse((self.dir / "tp.sql").exists())  # ni siquiera se corrió
        out = self.ok("consulta", trace, "bloqueo_hilo_principal")
        self.assertIn("no medido: la configuración base no captura ftrace:sched/sched_waking, "
                      "ftrace:sched/sched_blocked_reason", out)
        self.assertIn("--config completa", out)

    def test_consulta_distingue_medido_sin_casos_de_configuracion_desconocida(self):
        self.tp_outputs(GOOD)
        self.capture("--prueba")
        trace = self.plan.parent / "prueba" / "home_1.perfetto-trace.gz"
        self.tp_outputs(EMPTY_TABLE)
        (self.dir / "tp.count").unlink()
        out = self.ok("consulta", trace, "binder_hilo_principal")
        self.assertIn("Medido y sin casos: la configuración base captura lo que pide la consulta "
                      "(ftrace:binder/binder_transaction, ftrace:binder/binder_transaction_received)", out)
        (self.plan.parent / "prueba" / perf.CONFIG_FILE).unlink()  # como una traza de una versión anterior
        out = self.ok("consulta", trace, "binder_hilo_principal")
        self.assertIn("configuración desconocida", out)
        self.assertIn("no se puede afirmar que no ocurra", out)
        self.assertNotIn("Medido y sin casos", out)
        out = self.ok("consulta", trace, "--sql", "SELECT 1 AS a WHERE 0")  # una consulta propia no declara fuentes
        self.assertNotIn("configuración", out)

    def startup_folder(self, registered=True, config="base"):
        folder = self.plan.parent
        write(self.plan, json.dumps({"paquete": PKG, "hz": 60, "principales": ["hilo_max_ms"], "flujos": {
            "home": {"inicio": "MainActivity", "recorrido": "true"}}}))
        write(folder / "metricas.csv", HEADER + rows("antes", "home", "hilo_max_ms", [40, 50, 45]))
        for run in (1, 2, 3):
            name = "home_%d.perfetto-trace.gz" % run
            write(folder / "antes" / name, "x")
            if registered:
                perf.save_trace_config(folder / "antes", name, skill_config(config), "2026-11-05 10:00:00")
        return folder

    def test_diagnostico_separa_medido_sin_casos_de_no_medido(self):
        folder = self.startup_folder()
        self.env["FAKE_TP_OTRA"] = EMPTY_TABLE
        self.tp_outputs('"x"\n1\n')
        self.ok("diagnostico", "--carpeta", folder)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("_Medido y sin casos (la configuración de la traza captura lo que la consulta necesita y no hubo "
                      "filas): ", md)
        measured = md.split("_Medido y sin casos")[1].split("\n")[0]
        self.assertIn("binder_hilo_principal", measured)
        self.assertIn("contencion_locks", measured)
        self.assertNotIn("cpu_por_libreria", measured)
        self.assertNotIn("bloqueo_hilo_principal", measured)
        self.assertIn("_`cpu_por_libreria`: no medido: la configuración base no captura ds:linux.perf. No quiere decir que no "
                      "ocurra._", md)
        self.assertNotIn("bloqueo_hilo_principal", md)  # sin señal de espera, la captura completa ni se menciona
        self.assertIn("capturar --prueba --config cpu", md)  # la pista de siempre para atribuir el CPU a funciones
        self.assertNotIn("configuración desconocida", md)
        sql = (self.dir / "tp.sql").read_text(encoding="utf-8")
        self.assertNotIn("perf_sample", sql)  # lo no medido no se corre
        self.assertNotIn("blocked_function", sql)
        self.assertIn("binder transaction", sql)

    def test_diagnostico_con_solo_consultas_no_medidas_no_llama_a_trace_processor_y_lo_dice(self):
        folder = self.startup_folder()
        self.tp_outputs('"x"\n1\n')
        out = self.ok("diagnostico", "--carpeta", folder, "--consultas", "cpu_por_libreria,bloqueo_hilo_principal")
        self.assertFalse((self.dir / "tp.sql").exists())  # un lote vacío haría fallar a trace_processor
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("_`cpu_por_libreria`: no medido: la configuración base no captura ds:linux.perf.", md)
        self.assertIn("_`bloqueo_hilo_principal`: no medido: la configuración base no captura ftrace:sched/sched_waking, "
                      "ftrace:sched/sched_blocked_reason.", md)  # pedida a propósito: se dice por qué no hay tabla
        self.assertNotIn("completa)", out)

    def test_diagnostico_con_trazas_sin_registro_dice_configuracion_desconocida_y_no_afirma_ausencia(self):
        folder = self.startup_folder(registered=False)
        self.env["FAKE_TP_OTRA"] = EMPTY_TABLE
        self.tp_outputs('"x"\n1\n')
        self.ok("diagnostico", "--carpeta", folder)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertNotIn("Medido y sin casos", md)
        self.assertNotIn("no medido:", md)
        unknown = md.split("_Sin tabla, con configuración desconocida")[1].split("\n")[0]
        for name in ("binder_hilo_principal", "contencion_locks", "cpu_por_libreria", "bloqueo_hilo_principal"):
            self.assertIn(name, unknown)
        self.assertIn("no se afirma que no ocurra", unknown)
        self.assertNotIn("blocked_function", (self.dir / "tp.sql").read_text(encoding="utf-8"))  # la de completa no se corre a ciegas

    def test_diagnostico_sobre_una_captura_completa_corre_la_consulta_de_bloqueo(self):
        folder = self.startup_folder(config="completa")
        self.env["FAKE_TP_OTRA"] = '"estado","bloqueado_en"\n"D","filemap_fault (E/S)"\n'
        self.tp_outputs('"x"\n1\n')
        self.ok("diagnostico", "--carpeta", folder)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("`bloqueo_hilo_principal`", md)
        self.assertIn("| D | filemap_fault (E/S) |", md)
        self.assertIn("_`cpu_por_libreria`: no medido: la configuración completa no captura ds:linux.perf.", md)
        self.assertNotIn("Captura pendiente", md)  # ya es la captura completa

    def test_comparar_avisa_sin_bloquear_si_las_fases_no_usaron_la_misma_configuracion(self):
        folder = self.dir / "cmp"
        write(folder / "plan.json", json.dumps({"paquete": PKG, "principales": ["hilo_max_ms"], "flujos": {"home": {}}}))
        write(folder / "metricas.csv", HEADER + rows("antes", "home", "hilo_max_ms", [40, 41, 42, 43, 44])
              + rows("despues", "home", "hilo_max_ms", [30, 31, 32, 33, 34]))

        def phases(antes, despues):
            write(folder / "fases.json", json.dumps({
                "antes": dict({"fecha": "2026-11-05T10:00:00", "corridas": 5}, **({"configs": antes} if antes else {})),
                "despues": dict({"fecha": "2026-11-06T10:00:00", "corridas": 5}, **({"configs": despues} if despues else {}))}))
            return self.ok("comparar", folder / "metricas.csv")

        self.assertNotIn("configuración de Perfetto", phases(["base@aaa"], ["base@aaa"]))
        self.assertNotIn("configuración de Perfetto", phases(None, None))  # versiones anteriores: sin el dato, sin aviso
        out = phases(["base@aaa"], ["completa@bbb"])
        self.assertIn("⚠ home: las fases no se midieron con la misma configuración de Perfetto (antes: base@aaa; despues: "
                      "completa@bbb)", out)
        self.assertIn("--rehacer", out)
        self.assertIn("| home | hilo_max_ms |", out)  # no bloquea: la comparación sale igual
        out = phases(None, ["base@aaa"])
        self.assertIn("antes: desconocida; despues: base@aaa", out)
        self.assertIn("medida con una versión anterior", out)

    def test_sumar_corridas_a_una_fase_de_una_version_anterior_deja_la_configuracion_desconocida_a_la_vista(self):
        folder = self.dir / "mezcla"
        folder.mkdir()
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 3}}))
        perf.write_phase(folder, "antes", {"fecha": "2026-11-06T10:00:00", "corridas": 2, "configs": ["base@aaa"]})
        self.assertEqual(perf.read_phases(folder)["antes"]["configs"], ["desconocida", "base@aaa"])
        perf.write_phase(folder, "antes", {"fecha": "2026-11-06T11:00:00", "corridas": 1, "configs": ["base@aaa"]})
        self.assertEqual(perf.read_phases(folder)["antes"]["configs"], ["desconocida", "base@aaa"])


class BlockedMainThreadTest(DeviceBase):
    """La captura con --config completa se pide solo cuando el hilo principal espera dentro de sus frames más largos."""

    def folder_with(self, signal_row):
        folder = self.plan.parent
        write(self.plan, json.dumps({"paquete": PKG, "hz": 60, "principales": ["hilo_max_ms"], "flujos": {
            "home": {"inicio": "MainActivity", "recorrido": "true"}}}))
        write(folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        write(folder / "metricas.csv", HEADER + rows("antes", "home", "hilo_max_ms", [40]))
        write(folder / "antes" / "home_1.perfetto-trace.gz", "x")
        perf.save_trace_config(folder / "antes", "home_1.perfetto-trace.gz", skill_config("base"))
        self.env["FAKE_TP_POR_CONSULTA"] = json.dumps({
            "senal_bloqueo": '"frames","frames_ms","espera_ms","max_d_ms"\n' + signal_row + "\n"})
        self.env["FAKE_TP_OTRA"] = '"slice","ms"\n"Choreographer#doFrame 1",12.5\n'
        self.tp_outputs('"x"\n1\n')
        return folder

    def test_la_senal_lee_la_fila_y_aplica_los_umbrales(self):
        header = ["frames", "frames_ms", "espera_ms", "max_d_ms"]
        self.assertEqual(perf.blocked_signal([(header, [["3", "100.0", "30.0", "2.5"]])]), (0.3, 2.5, 100.0))
        self.assertIsNone(perf.blocked_signal([(header, [["0", "0.0", "0.0", "0.0"]])]))  # sin frames no hay señal
        self.assertIsNone(perf.blocked_signal([]))
        self.assertIsNone(perf.blocked_signal([(["otra"], [["1"]])]))
        self.assertEqual((perf.BLOCKED_SHARE_MIN, perf.BLOCKED_D_MIN_MS), (0.25, 4.0))

    def test_con_espera_importante_deja_la_captura_pendiente_y_siguiente_la_ofrece(self):
        folder = self.folder_with("3,100.0,30.0,2.5")
        out = self.ok("diagnostico", "--carpeta", folder)
        self.assertIn("deja una captura pendiente con --config completa", out)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("el 30 % del tiempo de sus 3 frames más largos", md)
        self.assertIn("Captura pendiente: `capturar --plan %s --prueba --config completa`" % (folder / "plan.json"), md)
        self.assertIn("bloqueo_hilo_principal", md)
        self.assertEqual(perf.diagnostic_captures(folder),
                         ["capturar --plan %s --prueba --config completa" % (folder / "plan.json")])
        self.assertIn("Siguiente · sesión 2 · diagnóstico", out)
        step = out.split("Siguiente · sesión 2 · diagnóstico")[1]
        self.assertRegex(step, r"1\. Terminal \(sin chat\) · captura opcional que pide diagnostico.md")
        self.assertRegex(step, r"perf\.py capturar --plan \S+ --prueba --config completa\n")
        self.assertIn("2. Chat nuevo", step)
        # hecha la captura completa, ya no se ofrece
        (folder / "prueba").mkdir()
        perf.save_trace_config(folder / "prueba", "home_1.perfetto-trace.gz", skill_config("completa"))
        self.assertEqual(len(perf.diagnostic_captures(folder)), 1)  # registrada, pero la traza no está: se sigue ofreciendo
        write(folder / "prueba" / "home_1.perfetto-trace.gz", "x")
        self.assertEqual(perf.diagnostic_captures(folder), [])
        self.assertNotIn("captura opcional", self.ok("siguiente", "--carpeta", folder))

    def test_el_cierre_sin_mejoras_tambien_ofrece_la_captura_y_una_prueba_con_base_no_la_da_por_hecha(self):
        folder = self.folder_with("3,100.0,30.0,2.5")
        self.ok("diagnostico", "--carpeta", folder)
        write(folder / "reporte-inicial.md", "x")
        out = self.ok("siguiente", "--carpeta", folder)
        self.assertIn("Siguiente · sesión 4 · cierre sin mejoras", out)
        self.assertIn("la captura que el diagnóstico dejó pendiente", out)
        self.assertIn("--prueba --config completa", out)
        (folder / "prueba").mkdir()
        write(folder / "prueba" / "home_1.perfetto-trace.gz", "x")
        perf.save_trace_config(folder / "prueba", "home_1.perfetto-trace.gz", skill_config("completa"))
        perf.save_trace_config(folder / "prueba", "home_1.perfetto-trace.gz", skill_config("base"))  # otra prueba la pisó
        self.assertEqual(len(perf.diagnostic_captures(folder)), 1)

    def test_si_trace_processor_no_puede_con_la_consulta_de_bloqueo_el_resto_del_diagnostico_sale(self):
        folder = self.folder_with("3,100.0,30.0,2.5")
        perf.save_trace_config(folder / "antes", "home_1.perfetto-trace.gz", skill_config("completa"))
        self.env["FAKE_TP_FALLA"] = "bloqueo_hilo_principal"
        self.ok("diagnostico", "--carpeta", folder)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("_`bloqueo_hilo_principal`: no disponible: trace_processor no pudo correr la consulta (no such column: "
                      "blocked_function). Actualiza trace_processor._", md)
        self.assertIn("| Choreographer#doFrame 1 | 12.5 |", md)

    def test_una_espera_larga_en_d_tambien_la_pide_y_sin_senal_no_aparece_nada(self):
        folder = self.folder_with("3,100.0,6.0,4.5")  # 6 % del tiempo, pero una espera de 4,5 ms en D
        self.ok("diagnostico", "--carpeta", folder)
        self.assertIn("Captura pendiente:", (folder / "diagnostico.md").read_text(encoding="utf-8"))
        folder = self.folder_with("3,100.0,10.0,1.0")  # 10 % y 1 ms: el hilo principal casi no espera
        out = self.ok("diagnostico", "--carpeta", folder)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertNotIn("Captura pendiente", md)
        self.assertNotIn("falta una captura", md)
        self.assertNotIn("captura opcional", out)

    def test_estado_hilo_principal_no_se_usa_para_la_senal(self):
        signal = (perf.ASSETS / "queries" / "senal_bloqueo.sql").read_text(encoding="utf-8")
        self.assertIn("Choreographer#doFrame", signal)  # mira solo dentro de los frames largos
        self.assertIn("LIMIT 3", signal)


@unittest.skipUnless(REAL_TP, "necesita trace_processor instalado: valida las consultas contra una traza de texto inventada")
class RealTraceProcessorTest(unittest.TestCase):
    """Las consultas nuevas, sobre una traza de ftrace en texto (inventada) y con trace_processor de verdad: los slices de
    binder se arman con los dos eventos que ahora captura base, y la razón de bloqueo y quién despierta al hilo salen de
    sched_blocked_reason y sched_waking."""

    def query(self, sql):
        # la traza de texto no trae el nombre del proceso: se elige por pid
        sql = sql.replace("WHERE name = '{{PAQUETE}}'", "WHERE pid = 1000")
        return perf.run_tp(REAL_TP, FIXTURE_TRACES / "bloqueo.systrace", perf.fill_sql(sql, None, {}))

    def diagnostic(self, name):
        return self.query((perf.ASSETS / "queries" / "diagnostico" / (name + ".sql")).read_text(encoding="utf-8"))

    def test_binder_hilo_principal_encuentra_la_transaccion(self):
        header, body = self.diagnostic("binder_hilo_principal")[-1]
        self.assertEqual(header, ["dentro_de", "veces", "total_ms", "max_ms"])
        self.assertEqual(body[0][0], "cargar")
        self.assertAlmostEqual(float(body[0][2]), 6.6)

    def test_bloqueo_hilo_principal_dice_la_funcion_y_quien_lo_desperto(self):
        header, body = self.diagnostic("bloqueo_hilo_principal")[-1]
        self.assertEqual(header, ["frame_t_ms", "frame_ms", "estado", "ms", "bloqueado_en", "lo_desperto", "dentro_de"])
        rows_by_state = {row[2]: row for row in body}
        self.assertEqual(rows_by_state["D"][4], "filemap_fault+0x1c/0x40 (E/S)")
        self.assertTrue(rows_by_state["D"][5].startswith("Binder:2000_1"))
        self.assertEqual(rows_by_state["S"][4], "—")
        self.assertTrue(rows_by_state["S"][5].startswith("Binder:2000_1"))

    def test_sin_el_evento_dice_no_disponible_en_este_dispositivo(self):
        text = (FIXTURE_TRACES / "bloqueo.systrace").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "sin-razon.systrace"
            trace.write_text("".join(line + "\n" for line in text.splitlines() if "sched_blocked_reason" not in line),
                             encoding="utf-8")
            sql = (perf.ASSETS / "queries" / "diagnostico" / "bloqueo_hilo_principal.sql").read_text(encoding="utf-8")
            header, body = perf.run_tp(REAL_TP, trace, perf.fill_sql(
                sql.replace("WHERE name = '{{PAQUETE}}'", "WHERE pid = 1000"), None, {}))[-1]
        blocked = [row for row in body if row[2] == "D"]
        self.assertEqual(blocked[0][4], "no disponible en este dispositivo")

    def test_la_senal_de_espera_mide_solo_dentro_de_los_frames_largos(self):
        found = perf.blocked_signal(self.query((perf.ASSETS / "queries" / "senal_bloqueo.sql").read_text(encoding="utf-8")))
        self.assertAlmostEqual(found[0], 10.5 / 29.0, places=3)
        self.assertAlmostEqual(found[1], 5.5)
        self.assertGreaterEqual(found[0], perf.BLOCKED_SHARE_MIN)


class CompatVersionsTest(DeviceBase):
    """Una investigación en curso de 0.6.0, 0.7.0, 0.8.0 o 0.9.0 (su plan.json, su fases.json y su estado.md, sin
    ningún campo posterior) carga y corre `siguiente`, `diagnostico`, `reporte --inicial` y `comparar` sin errores."""

    VERSIONS = ("0.6.0", "0.7.0", "0.8.0", "0.9.0")
    BEFORE_090 = ("0.6.0", "0.7.0", "0.8.0")  # sin la versión de la skill ni la configuración en fases.json

    def investigation(self, version):
        fixture = ROOT / "tests" / "fixtures" / ("hb-performance-%s" % version)
        folder = self.dir / version / "reports" / "perf" / "caso"
        folder.mkdir(parents=True)
        for name in ("plan.json", "estado.md", "metricas.csv", "fases.json"):
            write(folder / name, (fixture / name).read_text(encoding="utf-8"))
        return fixture, folder

    def test_los_planes_y_las_fases_anteriores_no_traen_campos_nuevos_y_cargan(self):
        for version in self.VERSIONS:
            fixture, folder = self.investigation(version)
            plan = perf.load_plan(folder / "plan.json")
            for field in ("mapping", "desde_triage"):
                self.assertNotIn(field, plan, version)
            phases = perf.read_phases(folder)
            self.assertTrue(phases, version)
            for record in phases.values():
                self.assertNotIn("faltan", record, version)
                if version in self.BEFORE_090:
                    self.assertNotIn("skill", record, version)
                    self.assertNotIn("configs", record, version)
                else:
                    self.assertEqual((record["skill"], len(record["configs"])), (version, 1), version)
            flow = next(iter(plan["flujos"]))
            self.assertEqual(perf.phase_skill(phases.get("antes"), flow), None if version in self.BEFORE_090 else version)
            self.assertFalse((folder / perf.NOTES_FILE).exists(), version)
            self.assertNotIn("perf:advertencias", (folder / "estado.md").read_text(encoding="utf-8"), version)
            self.assertEqual(perf.config_notes(folder, [flow]), [], version)  # sin el dato en ninguna fase, sin aviso
            self.assertEqual(perf.diagnostic_captures(folder), [], version)

    def test_siguiente_diagnostico_reporte_inicial_y_comparar_corren_sin_errores(self):
        for name in ("PERF_USUARIO", "PERF_CLAVE"):
            self.env.pop(name, None)
        for version in self.VERSIONS:
            fixture, folder = self.investigation(version)
            plan = perf.load_plan(folder / "plan.json")
            flow = next(iter(plan["flujos"]))
            before = perf.next_steps(folder, plan)[0]
            out = self.ok("siguiente", "--carpeta", folder)
            self.assertIn("Siguiente · %s" % before, out, version)
            self.assertNotIn("completar la línea base", out, version)  # una investigación ya decidida sigue donde estaba
            if (fixture / "traza.json").is_file():
                # la traza reducida del fixture: sus filas son lo que devuelve metricas.sql
                data = json.loads((fixture / "traza.json").read_text(encoding="utf-8"))
                table = '"tipo","ts","dur","prof","nombre"\n' + "".join(
                    '"%s",%d,%d,%d,"%s"\n' % tuple(row) for row in data["filas"])
                self.tp_outputs(table)
                if (self.dir / "tp.count").exists():
                    (self.dir / "tp.count").unlink()
                runs = sorted({r["corrida"] for r in perf.read_rows(folder / "metricas.csv")
                               if r["fase"] == "antes" and r["flujo"] == flow})
                for run in runs:
                    write(folder / "antes" / ("%s_%s.perfetto-trace.gz" % (flow, run)), "x")
                if (fixture / "configuracion.json").is_file():  # 0.9.0 ya anota con qué configuración grabó cada traza
                    write(folder / "antes" / "configuracion.json", (fixture / "configuracion.json").read_text(encoding="utf-8"))
                self.env["FAKE_TP_OTRA"] = '"a"\n'
                out = self.ok("diagnostico", "--carpeta", folder)
                md = (folder / "diagnostico.md").read_text(encoding="utf-8")
                if version in self.BEFORE_090:
                    # trazas de una versión anterior: no se sabe qué capturaron, así que no se afirma ausencia
                    self.assertIn("configuración desconocida", md, version)
                    self.assertNotIn("Medido y sin casos", md, version)
                    self.assertNotIn("no medido:", md, version)
                else:
                    self.assertNotIn("configuración desconocida", md, version)
                    self.assertIn("Medido y sin casos", md, version)  # se sabe qué capturó: la ausencia se puede afirmar
                self.assertIn("Red por tramo", md, version)
                (folder / "diagnostico.md").unlink()  # el fixture no lo trae: el paso siguiente no debe cambiar por él
            self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
            self.assertTrue((folder / "reporte-inicial.md").is_file(), version)
            out = self.ok("comparar", folder / "metricas.csv")
            self.assertIn("Veredictos:", out, version)
            self.assertNotIn("configuración de Perfetto", out, version)
            self.assertNotIn("otra versión de hb-performance", out, version)

    def test_las_metricas_que_calculaban_0_8_0_y_0_9_0_no_cambian_de_nombre_ni_de_valor(self):
        for version in ("0.8.0", "0.9.0"):
            fixture, folder = self.investigation(version)
            data = json.loads((fixture / "traza.json").read_text(encoding="utf-8"))
            plan = perf.load_plan(folder / "plan.json")
            flow = plan["flujos"]["detalle"]
            self.assertEqual((flow["duracion_max_s"], len(flow["pausas"]), flow["segmentos"][1]["solo_red"]), (1200, 1, True))
            metrics, invalid, _ = perf.trace_metrics([tuple(row) for row in data["filas"]], 60, flow, set(), 34)
            self.assertIsNone(invalid, version)
            self.assertEqual([list(m) for m in metrics], data["metricas"], version)  # las mismas, con el mismo valor y orden
            self.assertEqual(len(data["metricas"]), 35, version)

    def test_las_corridas_de_0_9_0_se_completan_sin_repetir_la_fase_y_las_anteriores_no(self):
        self.assertTrue(perf.same_capture("0.9.0") and perf.same_capture(perf.VERSION))
        self.assertFalse(perf.same_capture("0.8.0") or perf.same_capture(None))
        fixture, folder = self.investigation("0.9.0")
        build = {"version": "1.0 (7)", "instalada": "2026-04-14 09:00:00"}
        self.assertEqual(perf.check_build(folder, "antes", build, "abc1234", False, "detalle"), [])
        phases = perf.read_phases(folder)
        phases["antes"]["skill"] = phases["antes"]["flujos"]["detalle"]["skill"] = "0.8.0"
        perf.save_phases(folder, phases)
        self.assertIn("otra versión de hb-performance (0.8.0; esta es %s)" % perf.VERSION,
                      perf.check_build(folder, "antes", build, "abc1234", False, "detalle")[0])


MAPPING = (FIXTURE_TRACES / "mapping.txt")
REAL_RETRACE = perf.find_retrace()
FAKE_RETRACE = r'''#!{python}
import re, sys
mapping, stack = sys.argv[1], sys.argv[2]
assert "pg_map_id" in open(mapping).read() or "->" in open(mapping).read()
names = {{"a.b.a": ["com.example.app.data.Repo.load", "com.example.app.data.Repo.save"],
         "a.b.b": ["com.example.app.data.Repo.refresh"]}}
for line in open(stack).read().splitlines():
    found = re.search(r"at ([\w.$]+)\(([^)]*)\)", line)
    if not found or found.group(1) not in names:
        print(line)
        continue
    options = names[found.group(1)]
    if found.group(2) != "Unknown Source":
        options = options[:1]
    for i, option in enumerate(options):
        text = line.replace(found.group(0), "at %s(Repo.kt)" % option)
        print(text if i == 0 else "\t<OR> " + text.strip())
'''
CPU_TABLE = ('"hilo","libreria","funcion","muestras"\n"main","base.odex","a.b.a",40\n"main","base.odex","a.b.b",12\n'
             '"main","boot-framework.oat","android.os.Handler.dispatchMessage",9\n"main","libexample.so","?",7\n'
             '"main","base.odex","x.y.z",3\n"main","libexample.so","render.cold",2\n')


class MappingTest(PerfBase):
    """Ubicar el mapping de la variante medida y verificar que corresponde al APK medido."""

    def mapping_at(self, relative, text=None):
        path = self.dir / relative
        write(path, text if text is not None else MAPPING.read_text(encoding="utf-8"))
        return path

    def test_la_variante_sale_del_comando_instalar(self):
        self.assertEqual(perf.install_variant("./gradlew :app:installDemoProfiling"), ("app", "demoProfiling"))
        self.assertEqual(perf.install_variant("ANDROID_SERIAL=emulator-5554 ./gradlew installProfiling -Pperf"),
                         (None, "profiling"))
        self.assertEqual(perf.install_variant("./gradlew :feature:app:installProfiling"), ("feature/app", "profiling"))
        self.assertEqual(perf.install_variant("adb install -r app.apk"), (None, None))
        self.assertEqual(perf.install_variant(None), (None, None))

    def test_ubica_el_mapping_del_plan_de_la_variante_instalada_o_el_unico(self):
        profiling = self.mapping_at("app/build/outputs/mapping/profiling/mapping.txt")
        self.mapping_at("app/build/outputs/mapping/release/mapping.txt")
        self.assertEqual(perf.locate_mapping({}, self.dir), (profiling, False, ""))  # el único que no es debug ni release
        demo = self.mapping_at("app/build/outputs/mapping/demoProfiling/mapping.txt")
        path, explicit, warning = perf.locate_mapping({}, self.dir)
        self.assertIsNone(path)
        self.assertIn("hay 2 mappings", warning)
        self.assertIn('"mapping" de plan.json o con --mapping', warning)
        self.assertEqual(perf.locate_mapping({"instalar": "./gradlew :app:installDemoProfiling"}, self.dir)[0], demo)
        self.assertEqual(perf.locate_mapping({"instalar": "./gradlew installProfiling"}, self.dir)[0], profiling)
        self.assertEqual(perf.locate_mapping({"instalar": "./gradlew :app:installDemoProfiling",
                                              "mapping": "app/build/outputs/mapping/release/mapping.txt"}, self.dir)[0],
                         self.dir / "app/build/outputs/mapping/release/mapping.txt")  # el del plan manda
        other = self.mapping_at("otro/mapping.txt")
        self.assertEqual(perf.locate_mapping({"instalar": "./gradlew :app:installDemoProfiling"}, self.dir, str(other)),
                         (other, True, ""))  # --mapping manda sobre todo, y es explícito

    def test_sin_mapping_lo_dice_y_no_falla_salvo_un_mapping_explicito_que_no_existe(self):
        path, _, warning = perf.locate_mapping({}, self.dir)
        self.assertIsNone(path)
        self.assertIn("no encontré ningún mapping.txt", warning)
        path, _, warning = perf.locate_mapping({"instalar": "./gradlew :app:installProfiling"}, self.dir)
        self.assertIsNone(path)
        self.assertIn("no encontré el mapping de la variante profiling", warning)
        path, _, warning = perf.locate_mapping({"mapping": "app/no-existe.txt"}, self.dir)
        self.assertIsNone(path)
        self.assertIn("no existe", warning)
        with self.assertRaises(perf.PerfError):
            perf.locate_mapping({}, self.dir, str(self.dir / "no-existe.txt"))

    def test_lee_el_identificador_del_mapping_y_reconoce_uno_que_no_es_de_proguard(self):
        mapping = perf.read_mapping(MAPPING)
        self.assertEqual((mapping["id"], mapping["valido"]), ("1a2b3c4", True))
        plain = perf.read_mapping(self.mapping_at("m/mapping.txt", "com.example.app.data.Repo -> a.b:\n    int count -> a\n"))
        self.assertEqual((plain["id"], plain["valido"]), (None, True))
        other = perf.read_mapping(self.mapping_at("o/mapping.txt", "<?xml version='1.0'?>\n<mapa cifrado='si'/>\n"))
        self.assertEqual((other["id"], other["valido"]), (None, False))

    def test_lee_el_identificador_que_r8_deja_en_el_apk(self):
        apk = self.dir / "app.apk"
        with zipfile.ZipFile(str(apk), "w") as archive:
            archive.writestr("classes.dex", b'dex\n035\x00~~R8{"backend":"dex","compilation-mode":"release","min-api":24,'
                                            b'"pg-map-id":"1a2b3c4","r8-mode":"full","version":"8.5.35"}\x00')
            archive.writestr("classes2.dex", b"dex\n035\x00sin marcador")
            archive.writestr("lib/arm64-v8a/libexample.so", b'"pg-map-id":"no-es-un-dex"')
        self.assertEqual(perf.apk_map_ids(apk), {"1a2b3c4"})
        with zipfile.ZipFile(str(apk), "w") as archive:
            archive.writestr("classes.dex", b"dex\n035\x00sin R8")
        self.assertEqual(perf.apk_map_ids(apk), set())

    def test_verifica_por_identificador_y_si_no_coincide_no_se_usa_ni_con_mapping_explicito(self):
        mapping = perf.read_mapping(MAPPING)
        self.assertEqual(perf.verify_mapping(mapping, None, False, {"1a2b3c4"})[0], True)
        self.assertIn("pg_map_id (1a2b3c4) es el del APK instalado", perf.verify_mapping(mapping, None, False, {"1a2b3c4"})[1])
        for explicit in (False, True):
            use, note = perf.verify_mapping(mapping, None, explicit, {"9z9z9z9"})
            self.assertFalse(use)
            self.assertIn("no es el del APK instalado", note)

    def test_sin_identificador_verifica_por_fechas_de_forma_conservadora(self):
        path = self.mapping_at("app/build/outputs/mapping/profiling/mapping.txt")
        mapping = dict(perf.read_mapping(path), id=None)
        stamp = lambda delta: datetime.datetime.fromtimestamp(mapping["mtime"] + delta).strftime("%Y-%m-%d %H:%M:%S")
        use, note = perf.verify_mapping(mapping, stamp(600), False)  # la app se instaló después de generar el mapping
        self.assertTrue(use)
        self.assertIn("verificado solo por fecha", note)
        use, note = perf.verify_mapping(mapping, stamp(-3600), False)  # el mapping es posterior a la instalación
        self.assertFalse(use)
        self.assertIn("se generó después de instalar la app", note)
        use, note = perf.verify_mapping(mapping, None, False)  # sin fecha de instalación no se puede verificar
        self.assertFalse(use)
        self.assertIn("no se pudo verificar", note)
        self.assertIn("--mapping", note)
        use, note = perf.verify_mapping(mapping, None, True)  # pero un --mapping explícito se usa, y lo dice
        self.assertTrue(use)
        self.assertIn("sin verificar contra el APK instalado", note)
        # el APK de salida de esa variante, más nuevo que la instalación: es otro build
        apk = self.dir / "app/build/outputs/apk/profiling/app-profiling.apk"
        write(apk, "x")
        os.utime(str(apk), (mapping["mtime"] + 7200, mapping["mtime"] + 7200))
        use, note = perf.verify_mapping(mapping, stamp(600), False)
        self.assertFalse(use)
        self.assertIn("APK de salida", note)
        os.utime(str(apk), (mapping["mtime"] + 60, mapping["mtime"] + 60))
        self.assertTrue(perf.verify_mapping(mapping, stamp(600), False)[0])

    def test_el_plan_valida_el_campo_mapping_y_sin_el_carga_igual(self):
        write(self.dir / "plan.json", json.dumps({"paquete": "com.example.app", "flujos": {"home": {}}, "mapping": 7}))
        with self.assertRaises(perf.PerfError):
            perf.load_plan(self.dir / "plan.json")
        write(self.dir / "plan.json", json.dumps({"paquete": "com.example.app", "flujos": {"home": {}},
                                                  "mapping": "app/build/outputs/mapping/profiling/mapping.txt"}))
        self.assertIn("mapping", perf.load_plan(self.dir / "plan.json"))


class DeobfuscateTest(DeviceBase):
    """La desofuscación con `retrace` (simulado) donde hay nombres de métodos: cpu_por_libreria y la pila de un crash."""

    def setUp(self):
        super().setUp()
        self.env.pop("ANDROID_HOME", None)
        self.env.pop("ANDROID_SDK_ROOT", None)
        self.env.pop("RETRACE", None)
        # solo las herramientas simuladas y las del sistema: un retrace real en el PATH de la máquina no cuenta
        self.env["PATH"] = os.pathsep.join([str(self.dir / "bin"), "/usr/bin", "/bin"])
        self.mapping = self.dir / "app" / "build" / "outputs" / "mapping" / "profiling" / "mapping.txt"
        write(self.mapping, MAPPING.read_text(encoding="utf-8"))
        old = time.time() - 30 * 24 * 3600  # generado mucho antes de la instalación simulada (2026-11-05 10:00:00)
        os.utime(str(self.mapping), (old, old))
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["instalar"] = "./gradlew :app:installProfiling"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.trace = self.plan.parent / "prueba" / "home_1.perfetto-trace.gz"
        write(self.trace, "x")
        perf.save_trace_config(self.trace.parent, self.trace.name, skill_config("cpu"), "2099-01-01 10:00:00")
        self.tp_outputs(CPU_TABLE)

    def install_retrace(self):
        path = self.dir / "bin" / "retrace"
        path.write_text(textwrap.dedent(FAKE_RETRACE).replace("{python}", sys.executable).replace("{{", "{")
                        .replace("}}", "}"), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def consulta(self, *extra):
        if (self.dir / "tp.count").exists():
            (self.dir / "tp.count").unlink()
        return self.ok("consulta", self.trace, "cpu_por_libreria", "--ancho", "120", *extra)

    def test_cpu_por_libreria_sale_con_los_nombres_reales_y_avisa_lo_que_no_pudo(self):
        self.install_retrace()
        out = self.consulta()
        self.assertIn("✔ Desofuscado con app/build/outputs/mapping/profiling/mapping.txt (verificado solo por fecha", out)
        self.assertIn("| main | base.odex | com.example.app.data.Repo.load o com.example.app.data.Repo.save | 40 |", out)
        self.assertIn("| main | base.odex | com.example.app.data.Repo.refresh | 12 |", out)
        self.assertIn("| main | boot-framework.oat | android.os.Handler.dispatchMessage | 9 |", out)  # lo que no es de la app, igual
        self.assertIn("⚠ 1 nombre sigue ofuscado después de aplicar el mapping (x.y.z)", out)  # render.cold es nativo: no cuenta
        self.assertIn("| main | libexample.so | render.cold | 2 |", out)
        self.assertIn("mide con una variante sin cifrado de clases", out)
        self.assertIn("· Código nativo sin símbolos: se muestra la librería, no la función", out)
        self.assertNotIn("| a.b.a |", out)

    def test_un_mapping_posterior_a_la_instalacion_no_se_usa_salvo_que_se_pase_con_mapping(self):
        self.install_retrace()
        perf.save_trace_config(self.trace.parent, self.trace.name, skill_config("cpu"), "2020-01-01 10:00:00")
        out = self.consulta()
        self.assertIn("⚠ Sin desofuscar: el mapping se generó después de instalar la app", out)
        self.assertIn("| main | base.odex | a.b.a | 40 |", out)  # los nombres quedan como estaban
        out = self.consulta("--mapping", self.mapping)
        self.assertIn("sin verificar contra el APK instalado: se usa porque lo pasaste con --mapping", out)
        self.assertIn("com.example.app.data.Repo.refresh", out)

    def test_sin_retrace_dice_como_instalarlo_y_sigue_sin_desofuscar(self):
        out = self.consulta()
        self.assertIn("· Sin desofuscar: falta `retrace`", out)
        self.assertIn("cmdline-tools;latest", out)
        self.assertIn("| main | base.odex | a.b.a | 40 |", out)

    def test_sin_mapping_o_con_uno_de_otro_ofuscador_avisa_y_nunca_falla(self):
        self.install_retrace()
        self.mapping.unlink()
        out = self.consulta()
        self.assertIn("· Sin desofuscar: no encontré el mapping de la variante profiling", out)
        self.assertIn("| main | base.odex | a.b.a | 40 |", out)
        write(self.mapping, "<?xml version='1.0'?>\n<mapa cifrado='si'/>\n")
        out = self.consulta()
        self.assertIn("no tiene el formato de un mapping de ProGuard/R8", out)
        self.assertIn("mide con una variante sin cifrado de clases", out)

    def test_sin_nombres_ofuscados_no_busca_el_mapping_ni_imprime_nada(self):
        self.tp_outputs('"hilo","libreria","funcion","muestras"\n"main","base.odex","com.example.app.data.Repo.load",40\n')
        out = self.consulta()
        self.assertNotIn("esofusc", out)
        self.assertIn("com.example.app.data.Repo.load", out)

    def test_la_pila_de_un_crash_en_capturar_sale_desofuscada(self):
        self.install_retrace()
        self.tp_outputs(GOOD)
        self.env["FAKE_DEAD"] = "1"
        self.env["FAKE_CRASH_FRAMES"] = "\tat a.b.b(SourceFile:7)|\tat com.example.app.MainActivity.onCreate(SourceFile:20)"
        self.env["FAKE_UPDATED"] = "2099-01-01 10:00:00"
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("IllegalStateException: boom", result.stdout)
        self.assertIn("at com.example.app.data.Repo.refresh(Repo.kt)", result.stdout)
        self.assertNotIn("at a.b.b(", result.stdout)
        self.assertIn("✔ Desofuscado con", result.stdout)

    def test_salidas_desofusca_la_pila_del_crash(self):
        self.install_retrace()
        write(self.dir / "exit-info.txt", EXIT_ANDROID_11)
        self.env.update({"FAKE_EXIT_INFO": str(self.dir / "exit-info.txt"), "FAKE_UPDATED": "2099-01-01 10:00:00",
                         "FAKE_CRASH_FRAMES": "\tat a.b.b(SourceFile:7)"})
        out = self.ok("salidas", "--carpeta", self.plan.parent)
        self.assertIn("Crash de las 10:00:01 (pid 1234), inicio de la pila (logcat -b crash):", out)
        self.assertIn("at com.example.app.data.Repo.refresh(Repo.kt)", out)
        self.assertNotIn("at a.b.b(", out)
        result = self.perf("salidas", "--carpeta", self.plan.parent, "--mapping", self.dir / "no-existe.txt")
        self.assertEqual(result.returncode, 2)  # un --mapping que no existe se dice al empezar
        self.assertIn("no existe el mapping", result.stderr)

    def test_diagnostico_desofusca_la_tabla_y_deja_la_nota_en_el_archivo(self):
        self.install_retrace()
        folder = self.plan.parent
        write(folder / "metricas.csv", HEADER + rows("antes", "home", "jank_app_pct", [10]))
        write(folder / "antes" / "home_1.perfetto-trace.gz", "x")
        perf.save_trace_config(folder / "antes", "home_1.perfetto-trace.gz", skill_config("cpu"))
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 1,
                                                         "instalada": "2099-01-01 10:00:00"}}))
        self.env["FAKE_TP_POR_CONSULTA"] = json.dumps({"cpu_por_libreria": CPU_TABLE})
        self.env["FAKE_TP_OTRA"] = '"a"\n'
        self.tp_outputs('"x"\n1\n')
        self.ok("diagnostico", "--carpeta", folder)
        md = (folder / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("| main | base.odex | com.example.app.data.Repo.refresh | 12 |", md)
        self.assertIn("_Desofuscado con", md)
        self.assertIn("nombre sigue ofuscado después de aplicar el mapping (x.y.z)", md)


@unittest.skipUnless(REAL_RETRACE and not os.environ.get("CI"),
                     "validación local con retrace (cmdline-tools del SDK) y un mapping inventado; en el CI no corre")
class RealRetraceTest(PerfBase):
    def deobfuscator(self):
        return perf.Deobfuscator({"paquete": "com.example.app"}, self.dir, str(MAPPING))

    def test_nombres_sueltos_y_una_pila_con_lineas(self):
        with contextlib.redirect_stdout(io.StringIO()):
            tool = self.deobfuscator()
            names = tool.names(["a.b.a", "a.b.b", "android.os.Handler.dispatchMessage", "?"])
            stack = tool.stack(["E AndroidRuntime: java.lang.IllegalStateException: boom",
                                "E AndroidRuntime: \tat a.b.b(SourceFile:7)", "E AndroidRuntime: \tat a.b.a(SourceFile:3)"])
        # sin depender de la versión de retrace: ni el orden de los candidatos ni el formato exacto de la línea
        self.assertEqual(set(names), {"a.b.a", "a.b.b"})
        self.assertEqual(set(names["a.b.a"].split(" o ")), {"com.example.app.data.Repo.load", "com.example.app.data.Repo.save"})
        self.assertIn("com.example.app.data.Repo.refresh", names["a.b.b"])
        text = "\n".join(stack)
        self.assertIn("com.example.app.data.Repo.refresh(", text)
        self.assertIn("com.example.app.data.Repo.load(", text)
        self.assertNotIn("at a.b.", text)


EXIT_HEAD = ("ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\n"
             "Last Timestamp of Persistence Into Persistent Storage: 2026-11-05 10:00:05.000\n"
             "  package: com.example.app\n    Historical Process Exit for uid=10234\n")


def exit_entry(index, stamp, pid, reason, extra="", description="crash", trace="null", memory="pss=118MB rss=201MB"):
    return ("        ApplicationExitInfo #%d:\n          timestamp=%s pid=%d realUid=10234 packageUid=10234 definingUid=10234 "
            "user=0 process=com.example.app reason=%s %sstatus=0 importance=100 %s description=%s state=empty trace=%s\n"
            % (index, stamp, pid, reason, extra, memory, description, trace))


# Muestras inventadas con la forma que imprime la plataforma en cada versión.
EXIT_ANDROID_11 = EXIT_HEAD + exit_entry(0, "2026-11-05 10:00:01.120", 1234, "4 (APP CRASH(EXCEPTION))") + \
    exit_entry(1, "2026-11-05 09:50:00.000", 4000, "10 (USER REQUESTED)", memory="pss=0.00 rss=0.00",
               description="stop com.example.app due to from pid 999")
EXIT_ANDROID_13 = EXIT_HEAD + \
    exit_entry(0, "2026-11-05 10:00:01.500", 1234, "3 (LOW_MEMORY)", "subreason=3 (MEMORY PRESSURE) ", description="null") + \
    exit_entry(1, "2026-11-05 09:40:00.000", 3900, "6 (ANR)", "subreason=0 (UNKNOWN) ",
               description="user request after error: Input dispatching timed out", trace="/data/system/procexitstore/anr_1.gz") + \
    exit_entry(2, "2026-11-05 09:30:00.000", 3800, "5 (APP CRASH(NATIVE))", "subreason=0 (UNKNOWN) ", description="null")
EXIT_ANDROID_16 = EXIT_HEAD + \
    exit_entry(0, "2026-11-05 10:00:01.900", 1234, "9 (EXCESSIVE RESOURCE USAGE)", "subreason=7 (EXCESSIVE CPU USAGE) ",
               description="excessive cpu 12000 during 300000 dur=600000 limit=2") + \
    exit_entry(1, "2026-11-05 09:20:00.000", 3700, "16 (PACKAGE UPDATED)", "subreason=0 (UNKNOWN) ", description="null") + \
    exit_entry(2, "2026-11-05 09:10:00.000", 3600, "14 (FREEZER)", "subreason=0 (UNKNOWN) ", description="null") + \
    exit_entry(3, "2026-11-05 09:00:00.000", 3500, "2 (SIGNALED)", "subreason=0 (UNKNOWN) ", description="null")


class ExitInfoTest(DeviceBase):
    """Por qué se cerró la app: el parser de exit-info, `perf.py salidas` y la detección por corrida en `capturar`."""

    def exit_info(self, text):
        # el proceso principal se llama como el paquete del plan de estos tests
        write(self.dir / "exit-info.txt", text.replace("process=com.example.app ", "process=%s " % PKG))
        self.env["FAKE_EXIT_INFO"] = str(self.dir / "exit-info.txt")

    def test_lee_las_salidas_de_android_11_sin_submotivo(self):
        first, second = perf.parse_exit_info(EXIT_ANDROID_11)
        self.assertEqual(first, {"hora": "2026-11-05 10:00:01.120", "proceso": "com.example.app", "pid": 1234, "motivo": 4, "motivo_texto": "crash",
                                 "submotivo": "", "estado": "0", "importancia": "100", "pss": "118MB", "rss": "201MB",
                                 "descripcion": "crash", "traza": ""})
        self.assertEqual((second["motivo"], second["descripcion"], second["pid"]),
                         (10, "stop com.example.app due to from pid 999", 4000))
        self.assertIn("detenida a pedido del usuario", second["motivo_texto"])

    def test_lee_submotivo_traza_y_los_motivos_de_versiones_mas_nuevas(self):
        memory, anr, native = perf.parse_exit_info(EXIT_ANDROID_13)
        self.assertEqual((memory["motivo_texto"], memory["submotivo"], memory["descripcion"]),
                         ("poca memoria (la cerró el sistema)", "MEMORY PRESSURE", ""))
        self.assertEqual((anr["motivo_texto"], anr["submotivo"], anr["traza"]),
                         ("ANR", "", "/data/system/procexitstore/anr_1.gz"))
        self.assertIn("Input dispatching timed out", anr["descripcion"])
        self.assertEqual(native["motivo_texto"], "crash nativo")
        texts = [entry["motivo_texto"] for entry in perf.parse_exit_info(EXIT_ANDROID_16)]
        self.assertEqual(texts, ["uso excesivo de recursos", "paquete actualizado", "detenida por el freezer",
                                 "señal del sistema operativo"])
        self.assertEqual(perf.exit_text(perf.parse_exit_info(EXIT_ANDROID_16)[0]),
                         "uso excesivo de recursos · excessive cpu usage (excessive cpu 12000 during 300000 dur=600000 limit=2)")

    def test_un_campo_que_falta_queda_vacio_y_uno_que_no_conoce_no_rompe(self):
        self.assertEqual(perf.parse_exit_info(""), [])
        self.assertEqual(perf.parse_exit_info(EXIT_HEAD), [])
        entry, = perf.parse_exit_info("ApplicationExitInfo #0:\n  timestamp=2026-11-05 10:00:01.120 campoNuevo=7 "
                                      "reason=99 (ALGO NUEVO) otroNuevo=x\n")
        self.assertEqual((entry["hora"], entry["pid"], entry["motivo"], entry["pss"], entry["descripcion"]),
                         ("2026-11-05 10:00:01.120", None, 99, "", ""))
        self.assertIn("motivo 99", entry["motivo_texto"])
        entry, = perf.parse_exit_info("ApplicationExitInfo #0:\n  pid=12\n")
        self.assertEqual((entry["hora"], entry["motivo"], entry["motivo_texto"]), ("", None, "sin dato"))

    def test_las_salidas_de_una_corrida_filtran_por_ventana_por_pid_y_por_lo_que_ya_estaba(self):
        entries = perf.parse_exit_info(EXIT_ANDROID_11)
        before = ("2026-11-05 10:00:00", 1234, entries[1:])
        after = ("2026-11-05 10:00:02", None, entries)
        self.assertEqual([e["pid"] for e in perf.run_exits(before, after, 1234)], [1234])
        self.assertEqual(perf.run_exits(before, after, 5555), [])  # no es el proceso medido
        self.assertEqual(perf.run_exits(before, after, None, killed=(1234,)), [])  # el que detiene la propia skill
        self.assertEqual(perf.run_exits(("2026-11-05 10:00:02", 1234, entries[1:]), ("2026-11-05 10:00:03", None, entries), 1234),
                         [])  # pasó antes de que empezara la corrida
        self.assertEqual(perf.run_exits(("2026-11-05 10:00:00", 1234, entries), after, 1234), [])  # ya estaba registrada
        self.assertEqual(perf.run_exits(("", None, []), after, 1234), [])  # sin hora del dispositivo no se afirma nada
        # un proceso secundario de la app (un servicio en otro proceso) no es el que se mide
        other = perf.parse_exit_info(EXIT_ANDROID_11.replace("process=com.example.app reason=4", "process=com.example.app:push reason=4"))
        self.assertEqual(perf.run_exits(before, ("2026-11-05 10:00:02", None, other), None, package="com.example.app"), [])
        self.assertEqual(len(perf.run_exits(before, after, None, package="com.example.app")), 1)

    def test_salidas_imprime_la_tabla_en_espanol_y_acota_con_desde_y_limite(self):
        self.exit_info(EXIT_ANDROID_13)
        out = self.ok("salidas", "--paquete", "com.example.app")
        self.assertIn("| Hora | pid | Motivo | Descripción | PSS | RSS |", out)
        self.assertIn("| 2026-11-05 10:00:01.500 | 1234 | poca memoria (la cerró el sistema) · memory pressure | — | 118MB | 201MB |",
                      out)
        self.assertIn("| ANR |", out)
        self.assertIn("| crash nativo |", out)
        self.assertIn("Con traza del sistema (ANR o crash nativo): 09:40:00 ANR", out)
        out = self.ok("salidas", "--paquete", "com.example.app", "--limite", "1")
        self.assertNotIn("| ANR |", out)
        self.assertIn("… 2 salidas más", out)
        out = self.ok("salidas", "--paquete", "com.example.app", "--desde", "2026-11-05 09:35")
        self.assertIn("| ANR |", out)
        self.assertNotIn("| crash nativo |", out)
        out = self.ok("salidas", "--paquete", "com.example.app", "--desde", "2026-11-06")
        self.assertIn("Sin salidas registradas de com.example.app desde 2026-11-06", out)
        self.assertIn("no cubre lo que pasó antes", out)

    def test_salidas_muestra_la_pila_del_crash_y_toma_el_paquete_del_plan(self):
        self.exit_info(EXIT_ANDROID_11)
        out = self.ok("salidas", "--carpeta", self.plan.parent)  # el paquete del plan es com.ejemplo.app
        self.assertIn("| 2026-11-05 10:00:01.120 | 1234 | crash | crash | 118MB | 201MB |", out)
        self.assertIn("Crash de las 10:00:01 (pid 1234), inicio de la pila (logcat -b crash):", out)
        self.assertIn("IllegalStateException: boom", out)
        result = self.perf("salidas")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--paquete", result.stderr)

    def test_en_android_10_dice_que_no_esta_disponible(self):
        self.env["FAKE_SDK"] = "29"
        out = self.ok("salidas", "--paquete", "com.example.app")
        self.assertIn("no disponible (Android 11 o superior; el dispositivo tiene API 29)", out)
        self.assertIn("No quiere decir que la app no se haya cerrado", out)

    def capture(self, *extra):
        return self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--calentamiento", "0", "--sin-compilar", *extra)

    def test_una_salida_del_proceso_medido_dentro_de_la_corrida_la_invalida_con_el_motivo(self):
        self.tp_outputs(GOOD)
        self.exit_info(EXIT_ANDROID_13)  # poca memoria a las 10:00:01, pid 1234: dentro de la primera corrida
        result = self.capture("--fase", "antes", "--corridas", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("✖ corrida 1 inválida: la app salió: poca memoria (la cerró el sistema) · memory pressure", result.stdout)
        self.assertIn("corrida 2/2", result.stdout)  # se repite con las reglas de siempre
        folder = self.plan.parent
        self.assertTrue(any("_invalida_la-app-sali" in f.name for f in (folder / "antes").iterdir()))
        runs = {r["corrida"] for r in perf.read_rows(folder / "metricas.csv")}
        self.assertEqual(len(runs), 2)

    def test_el_force_stop_y_las_salidas_de_otro_proceso_o_de_antes_no_invalidan(self):
        self.tp_outputs(GOOD)
        self.exit_info(EXIT_HEAD + exit_entry(0, "2026-11-05 10:00:01.000", 1234, "10 (USER REQUESTED)",
                                              description="stop com.example.app due to from pid 999"))
        result = self.capture("--fase", "antes", "--corridas", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("inválida", result.stdout)
        self.exit_info(EXIT_HEAD + exit_entry(0, "2026-11-05 10:00:01.000", 777, "4 (APP CRASH(EXCEPTION))")
                       + exit_entry(1, "2026-11-05 09:00:00.000", 1234, "4 (APP CRASH(EXCEPTION))"))
        result = self.capture("--fase", "control", "--corridas", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("inválida", result.stdout)

    def test_en_un_arranque_en_frio_ignora_el_proceso_que_detiene_la_skill_y_ve_el_del_proceso_nuevo(self):
        write(self.plan, json.dumps({"paquete": PKG, "hz": 60, "principales": ["ttid_ms"], "flujos": {"arranque": {
            "recorrido": {"tipo": "arranque-frio", "actividad": PKG + "/.MainActivity", "espera_s": 0}}}}))
        self.tp_outputs(GOOD)
        self.exit_info(EXIT_HEAD + exit_entry(0, "2026-11-05 10:00:01.000", 1234, "10 (USER REQUESTED)",
                                              description="stop com.example.app due to from pid 999"))
        result = self.perf("capturar", "--plan", self.plan, "--prueba")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Salida de la app", result.stdout)  # era el proceso anterior, que detuvo perf.py
        self.exit_info(EXIT_HEAD + exit_entry(0, "2026-11-05 10:00:01.000", 4321, "4 (APP CRASH(EXCEPTION))"))
        (self.dir / "adb.log.salidas").unlink()
        result = self.perf("capturar", "--plan", self.plan, "--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("✖ Salida de la app durante la corrida (10:00:01, pid 4321): crash (crash)", result.stdout)
        self.assertIn("la corrida de prueba fue inválida: la app salió: crash", result.stderr)

    def test_si_la_app_se_cayo_el_motivo_es_el_de_exit_info_y_se_mantiene_el_aviso_de_crash(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_DEAD"] = "1"
        self.exit_info(EXIT_ANDROID_11)
        result = self.capture("--prueba")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("✖ La app se cayó durante la corrida. Inicio del crash (logcat -b crash):", result.stdout)
        self.assertIn("IllegalStateException: boom", result.stdout)
        self.assertIn("la app salió: crash", result.stderr)

    def test_en_android_10_avisa_una_vez_que_no_hay_registro_de_salidas(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_SDK"] = "29"
        self.exit_info(EXIT_ANDROID_11)
        result = self.capture("--fase", "antes", "--corridas", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("sin registro de salidas de la app por corrida"), 1)
        self.assertNotIn("inválida", result.stdout)


class GuidedFailureTest(DeviceBase):
    """Todo fallo termina con qué pasó, qué quedó guardado y el comando para seguir, que empieza con cd."""

    def capture(self, *extra, interruptible=False):
        return self.perf("capturar", "--plan", self.plan, "--flujo", "home", *extra, interruptible=interruptible)

    def update_flow(self, **fields):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(fields)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def assert_guided(self, result, saved, *commands):
        """La salida de error termina con las tres partes, en orden, y cada comando empieza con cd."""
        text = result.stderr
        self.assertIn("✖ ", text)
        self.assertLess(text.index("✖ "), text.index("  Qué quedó guardado: "), text)
        self.assertLess(text.index("  Qué quedó guardado: "), text.index("  Cómo seguir:"), text)
        self.assertIn(saved, text.split("  Qué quedó guardado: ")[1].split("\n")[0])
        steps = [line.strip() for line in text.split("  Cómo seguir:")[1].splitlines() if line.startswith("     ")]
        self.assertTrue(steps, text)
        for line in steps:
            self.assertTrue(line.startswith("cd "), line)
        for command in commands:
            self.assertTrue(any(command in line for line in steps), (command, steps))
        return steps

    def phases(self):
        return json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))

    def test_ctrl_c_dice_cuantas_corridas_quedaron_y_como_completar_la_fase(self):
        counter = self.dir / "vueltas.txt"
        # el recorrido interrumpe a perf.py (Ctrl+C) en la tercera corrida
        self.update_flow(recorrido='n=$(cat %s 2>/dev/null || echo 0); echo $((n+1)) > %s; [ "$n" -lt 2 ] || kill -INT $PPID; '
                                   'sleep 0.3' % (counter, counter))
        self.tp_outputs(GOOD)
        result = self.capture("--fase", "antes", "--corridas", "5", "--calentamiento", "0", "--sin-compilar",
                              interruptible=True)
        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        self.assertIn("✖ interrumpido (Ctrl+C)", result.stderr)
        steps = self.assert_guided(result, "2 de 5 corridas válidas de antes en ", "--corridas 3")
        self.assertIn("capturar --plan", steps[0])
        self.assertNotIn("--corridas 5", steps[0])
        self.assertIn("--rehacer", steps[1])  # la otra salida: repetir la fase entera
        self.assertEqual(self.phases()["antes"]["corridas"], 2)  # las válidas quedan con su registro
        self.assertEqual(self.phases()["antes"]["faltan"], {"home": 3})
        out = self.ok("siguiente", "--carpeta", self.plan.parent)  # la fase no se da por medida a medias
        self.assertIn("Siguiente · completar la fase antes, que se cortó (sin chat)", out)
        self.assertIn("--fase antes --corridas 3", out)
        self.assertNotIn("--fase control", out)
        self.assertIn("kill -TERM 4242", (self.dir / "adb.log").read_text(encoding="utf-8"))  # Perfetto no queda grabando
        counter.unlink()
        self.update_flow(recorrido="true")
        self.capture("--fase", "antes", "--corridas", "3", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(self.phases()["antes"]["corridas"], 5)
        self.assertNotIn("faltan", self.phases()["antes"])
        self.assertNotIn("completar la fase", self.ok("siguiente", "--carpeta", self.plan.parent))
        self.assertEqual(len({k[2] for k in self.read_csv_at(self.plan.parent / "metricas.csv")}), 5)

    def read_csv_at(self, path):
        with path.open(newline="", encoding="utf-8") as f:
            return {(r["fase"], r["metrica"], r["corrida"]): r for r in csv.DictReader(f)}

    def test_ctrl_c_sin_corridas_validas_no_guarda_nada_y_da_el_mismo_comando(self):
        self.update_flow(recorrido="kill -INT $PPID; sleep 0.3")
        self.tp_outputs(GOOD)
        result = self.capture("--fase", "antes", "--corridas", "5", "--calentamiento", "0", "--sin-compilar",
                              interruptible=True)
        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        self.assert_guided(result, "ninguna corrida de esta tanda (0 de 5 válidas de antes)", "--corridas 5")
        self.assertIn("ya tenía sigue igual", result.stderr)
        self.assertFalse((self.plan.parent / "fases.json").exists())
        result = self.capture("--fase", "antes", "--corridas", "5", "--calentamiento", "0", "--sin-compilar", "--rehacer",
                              interruptible=True)
        self.assertIn("sigue igual", result.stderr)  # --rehacer sin nada medido antes: no hubo nada que descartar
        self.update_flow(recorrido="true")
        self.capture("--fase", "antes", "--corridas", "1", "--calentamiento", "0", "--sin-compilar")
        self.update_flow(recorrido="kill -INT $PPID; sleep 0.3")
        result = self.capture("--fase", "antes", "--corridas", "5", "--calentamiento", "0", "--sin-compilar", "--rehacer",
                              interruptible=True)
        self.assertIn("ya se descartaron por --rehacer", result.stderr)  # con --rehacer lo anterior ya no está
        self.assertNotIn("sigue igual", result.stderr)

    def test_lo_que_falta_de_una_tanda_cortada_se_guarda_por_flujo(self):
        folder = self.dir / "fases"
        folder.mkdir()
        base = {"fecha": "2026-11-09T10:00:00", "corridas": 3}
        perf.write_phase(folder, "antes", dict(base, faltan={"a": 7}), "a")
        perf.write_phase(folder, "antes", dict(base, corridas=10), "b")  # otro flujo completo: lo de 'a' sigue pendiente
        self.assertEqual(perf.read_phases(folder)["antes"]["faltan"], {"a": 7})
        perf.write_phase(folder, "antes", dict(base, faltan={"b": 2}), "b")
        self.assertEqual(perf.read_phases(folder)["antes"]["faltan"], {"a": 7, "b": 2})
        plan = {"paquete": PKG, "flujos": {"a": {"recorrido": "true"}, "b": {"recorrido": "true"}}}
        self.assertIn("completar la fase antes", perf.next_steps(folder, plan, "a")[0])
        self.assertIn("--corridas 2", perf.next_steps(folder, plan, "b")[1][0]["texto"])
        perf.write_phase(folder, "antes", dict(base, corridas=7), "a")  # 'a' termina: solo queda lo de 'b'
        self.assertEqual(perf.read_phases(folder)["antes"]["faltan"], {"b": 2})
        write(folder / "metricas.csv", HEADER + rows("antes", "a", "m", [1] * 10) + rows("antes", "b", "m", [1] * 8))
        perf.forget_flow(folder, folder / "metricas.csv", "antes", "b")  # --rehacer de 'b': lo que le faltaba ya no vale
        self.assertNotIn("faltan", perf.read_phases(folder)["antes"])

    def test_tres_invalidas_seguidas_y_corridas_insuficientes_dan_el_comando_para_completar(self):
        self.tp_outputs(GOOD, LOGIN, LOGIN, LOGIN)
        result = self.capture("--fase", "antes", "--corridas", "10", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("3 corridas inválidas seguidas", result.stderr)
        self.assert_guided(result, "1 de 10 corridas válidas de antes en ", "--corridas 9")
        self.assertEqual(self.phases()["antes"]["corridas"], 1)
        notes = perf.read_notes(self.plan.parent)
        self.assertEqual(notes["invalidas"]["antes"]["home"], {"apareció 'SCREEN LoginActivity onCreate'": 3})
        (self.dir / "tp.count").unlink()
        self.tp_outputs(LOGIN, GOOD, LOGIN, GOOD, LOGIN, GOOD, LOGIN)
        result = self.capture("--fase", "control", "--corridas", "4", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("solo 3 de 4 corridas válidas en 7 intentos", result.stderr)
        self.assert_guided(result, "3 de 4 corridas válidas de control en ", "--corridas 1")

    def test_variables_faltantes_dan_el_comando_para_cargarlas_y_el_mismo_comando(self):
        self.update_flow(preparar="true", requiere_env=["PERF_USUARIO", "PERF_CLAVE", "PERF_TOKEN_API"])
        for name in ("PERF_USUARIO", "PERF_CLAVE", "PERF_TOKEN_API"):
            self.env.pop(name, None)
        result = self.capture("--fase", "antes", "--corridas", "5")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        steps = self.assert_guided(result, "nada", "capturar --plan")
        self.assertIn("printf 'PERF_USUARIO: ' && read -r PERF_USUARIO && export PERF_USUARIO", steps[0])  # lectura normal
        self.assertIn("printf 'PERF_CLAVE: ' && read -r -s PERF_CLAVE && echo && export PERF_CLAVE", steps[1])  # oculta
        self.assertIn("read -r -s PERF_TOKEN_API && echo && export PERF_TOKEN_API", steps[2])
        self.assertIn("--fase antes --corridas 5", steps[3])  # y el mismo comando que se estaba corriendo
        self.assertIn("lectura oculta", result.stderr)

    def test_el_comando_para_cargar_una_variable_funciona_en_bash_y_en_zsh(self):
        command = perf.env_steps(["PERF_CLAVE"])[0][1].split(" && ", 1)[1] + ' && printf "%s" "[$PERF_CLAVE]"'
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            result = subprocess.run([shell, "-c", command], input="secreta\n", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, shell + result.stderr)
            self.assertTrue(result.stdout.endswith("[secreta]"), (shell, result.stdout))
        self.assertEqual([bool(perf.SECRET_NAME.search(name)) for name in
                          ("PERF_CLAVE", "APP_PASSWORD", "PIN_TARJETA", "API_TOKEN", "CLIENT_SECRET", "API_KEY", "PERF_USUARIO",
                           "AMBIENTE")], [True, True, True, True, True, True, False, False])

    def test_un_preparar_que_falla_sin_salida_da_el_comando_para_correrlo_a_mano(self):
        self.update_flow(preparar="exit 1 > /dev/null 2>&1")
        self.tp_outputs(GOOD)
        result = self.capture("--prueba")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("córrelo a mano en tu terminal para ver el error:", result.stdout)
        self.assertRegex(result.stdout, r"\n    cd \S+ && \( exit 1 > /dev/null 2>&1 \)\n")
        steps = self.assert_guided(result, "nada", "( exit 1 > /dev/null 2>&1 )", "--prueba")
        self.assertIn("( exit 1", steps[0])  # primero 'preparar' a mano; después, repetir
        self.assertIn("no dejó la app en el punto de partida", result.stderr)
        self.assertEqual(perf.test_warnings(self.plan.parent, "home")[0]["tipo"], "preparar")

    def test_preparar_a_mano_lleva_los_valores_enmascarados(self):
        self.update_flow(preparar="echo clave-de-mentira > /dev/null; exit 3", requiere_env=["PERF_CLAVE"])
        self.env["PERF_CLAVE"] = "clave-de-mentira"
        self.tp_outputs(GOOD)
        result = self.capture("--fase", "antes", "--corridas", "5", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertNotIn("clave-de-mentira", result.stdout + result.stderr)
        self.assert_guided(result, "ninguna corrida de esta tanda", "( echo *** > /dev/null; exit 3 )", "--corridas 5")
        # un 'preparar' que falla una vez y después funciona: el corte posterior ya no pide correrlo a mano
        counter = self.dir / "preparos.txt"
        self.update_flow(preparar='n=$(cat %s 2>/dev/null || echo 0); echo $((n+1)) > %s; [ "$n" -gt 0 ]' % (counter, counter))
        self.tp_outputs(GOOD, LOGIN, LOGIN, LOGIN)
        (self.dir / "tp.count").unlink() if (self.dir / "tp.count").exists() else None
        result = self.capture("--fase", "control", "--corridas", "5", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertNotIn("a mano", result.stderr.split("Cómo seguir:")[1])
        self.assertEqual(perf.read_notes(self.plan.parent)["invalidas"]["antes"]["home"],
                         {"'preparar' terminó con código 3": 3})

    def test_despues_del_calentamiento_hay_un_respiro_antes_del_primer_preparar(self):
        self.assertGreaterEqual(perf.WARMUP_SETTLE_S, 1)
        source = inspect_source()
        self.assertIn("settle(WARMUP_SETTLE_S)", source.split("def cmd_capturar")[1].split("while valid < target")[0])

    def test_sin_dispositivo_sin_autorizar_o_desconectado_a_mitad_explica_y_da_el_comando(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_LISTA"] = "\n"  # adb devices sin ningún dispositivo
        result = self.capture("--prueba")
        self.assertEqual(result.returncode, 3)
        self.assertIn("no hay ningún dispositivo conectado", result.stderr)
        self.assert_guided(result, "nada", "--prueba")
        self.env["FAKE_LISTA"] = "emulator-5554\tunauthorized\n"
        result = self.capture("--prueba")
        self.assertEqual(result.returncode, 3)
        self.assertIn("el dispositivo emulator-5554 está conectado pero sin autorizar: acepta en su pantalla", result.stderr)
        self.assert_guided(result, "nada", "--prueba")
        self.env["FAKE_LISTA"] = "emulator-5554\toffline\n"
        self.assertIn("sin responder (offline)", self.capture("--prueba", "--serial", "emulator-5554").stderr)
        del self.env["FAKE_LISTA"]
        self.env["FAKE_DESCONECTA"] = "dumpsys activity activities"  # se suelta antes de empezar una prueba
        self.assertEqual(self.capture("--prueba").returncode, 3)
        self.assertEqual(perf.test_warnings(self.plan.parent, "home"), [])  # no es un aviso de 'preparar' que corregir
        self.env["FAKE_DESCONECTA"] = "pidof"  # el cable se suelta en medio de la primera corrida
        result = self.capture("--fase", "control", "--corridas", "3", "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("el dispositivo dejó de estar disponible para adb (adb: device 'emulator-5554' not found)", result.stderr)
        self.assert_guided(result, "ninguna corrida de esta tanda", "--corridas 3")

    def test_una_traza_que_no_se_procesa_dice_lo_guardado_y_como_seguir(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_TP_FALLA"] = "metricas"
        result = self.capture("--fase", "antes", "--corridas", "2", "--calentamiento", "0", "--sin-compilar")
        self.assertNotEqual(result.returncode, 0)
        self.assert_guided(result, "ninguna corrida de esta tanda", "--corridas 2")

    def test_build_repetido_en_despues_da_el_comando_de_instalar_y_el_de_medir(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["instalar"] = "./gradlew :app:installProfiling"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        result = self.capture("--fase", "despues", "--corridas", "5")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("el build instalado es el mismo que midió antes", result.stderr)
        steps = self.assert_guided(result, "ninguna corrida de esta tanda", "./gradlew :app:installProfiling",
                                   "--fase despues --corridas 5")
        self.assertIn("installProfiling", steps[0])

    def test_un_plan_invalido_y_un_error_inesperado_tambien_terminan_con_el_comando(self):
        self.plan.write_text("{no es json", encoding="utf-8")
        result = self.perf("siguiente", "--carpeta", self.plan.parent)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no se pudo leer", result.stderr)
        self.assert_guided(result, "nada", "siguiente --carpeta")
        self.plan.write_text(json.dumps({"paquete": PKG, "flujos": {"home": {"recorrido": "true"}}}), encoding="utf-8")
        write(self.plan.parent / "fases.json", "[1, 2]")  # un archivo de la carpeta con una forma que perf.py no espera
        result = self.perf("siguiente", "--carpeta", self.plan.parent)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("✖ error inesperado en perf.py (", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assert_guided(result, "nada", "siguiente --carpeta")
        self.env["HB_PERF_DEBUG"] = "1"
        self.assertIn("Traceback", self.perf("siguiente", "--carpeta", self.plan.parent).stderr)

    def test_pausa_no_imprime_la_guia_porque_corre_dentro_de_un_recorrido(self):
        self.env["HB_PERF_TTY"] = str(self.dir / "no-existe" / "tty")
        result = self.perf("pausa", "autoriza en la otra app")
        self.assertEqual(result.returncode, 3)
        self.assertNotIn("Cómo seguir", result.stderr)

    def test_el_mismo_comando_cambia_corridas_y_quita_rehacer(self):
        argv = ["capturar", "--plan", "reports/perf/x y/plan.json", "--fase", "antes", "--corridas=10", "--rehacer"]
        command = perf.same_command(corridas=4, sin=("--rehacer",), argv=argv)
        self.assertTrue(command.startswith("cd "))
        self.assertTrue(command.endswith("capturar --plan 'reports/perf/x y/plan.json' --fase antes --corridas 4"), command)
        self.assertIn("--corridas 10 --rehacer", perf.same_command(argv=["capturar", "--corridas", "10", "--rehacer"]))


class TestRunWarningsTest(DeviceBase):
    """Los avisos de la corrida de prueba se guardan y, mientras sigan vigentes, `siguiente` no ofrece medir antes."""

    REPEATED = GOOD.replace('"seccion",10,5,0,"SCREEN MainActivity onResume"\n', "") + \
        '"seccion",400000000,0,0,"MARK reparto"\n"seccion",450000000,0,0,"MARK reparto"\n'

    def setUp(self):
        super().setUp()
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["instalar"] = "./gradlew :app:installProfiling"
        plan["flujos"]["home"]["metricas_usuario"] = [{"nombre": "reparto_ms", "desde": {"marca": "HTTP GET items/{id}"},
                                                       "hasta": {"marca": "MARK reparto"}}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        write(self.dir / "app/src/main/kotlin/com/example/app/RepartoScreen.kt",
              "package com.example.app\n\nfun cargado() {\n    PerfHooks.mark(\"reparto\")\n}\n")

    def test_la_prueba_guarda_sus_avisos_y_siguiente_pide_corregir_antes_de_medir(self):
        self.tp_outputs(self.REPEATED)
        out = self.ok("capturar", "--plan", self.plan, "--prueba")
        self.assertIn("⚠ 'MARK reparto' salió 2 veces en una misma carga", out)
        self.assertIn("⚠ 1 avisos por corregir antes de medir", out)
        self.assertIn("Siguiente · corrige antes de medir (avisos de la corrida de prueba)", out)
        saved = perf.test_warnings(self.plan.parent, "home")
        self.assertEqual([item["tipo"] for item in saved], ["repetida"])
        self.assertEqual(saved[0]["donde"], ["app/src/main/kotlin/com/example/app/RepartoScreen.kt:4"])
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        lines = out.splitlines()
        head = next(i for i, line in enumerate(lines) if line.strip() == "Corrige antes de medir:")
        self.assertIn("- la marca 'MARK reparto' salió 2 veces en una misma carga", lines[head + 1])
        self.assertIn("RepartoScreen.kt:4", lines[head + 1])
        chat = next(line for line in lines if "Texto:" in line)
        self.assertIn("corrige los avisos de la corrida de prueba del flujo 'home', sin compilar, instalar ni capturar", chat)
        self.assertIn("1) la marca 'MARK reparto' sale 2 veces por carga", chat)
        self.assertIn("(app/src/main/kotlin/com/example/app/RepartoScreen.kt:4)", chat)
        self.assertRegex(out, r"1\. Chat nuevo · Modelo: Sonnet 5\.5 · Esfuerzo: medio")
        self.assertRegex(out, r"2\. Terminal \(sin chat\) · compila e instala")
        self.assertIn("./gradlew :app:installProfiling", out)
        self.assertRegex(out, r"3\. Terminal \(sin chat\) · repite la corrida de prueba")
        self.assertRegex(out, r"4\. Terminal \(sin chat\) · OPCIÓN, solo si decides medir igual")
        option = lines[next(i for i, line in enumerate(lines) if "OPCIÓN" in line) + 1]
        self.assertIn("--fase antes --corridas 10", option)
        self.assertTrue(option.strip().startswith("cd "))
        state_title = perf.next_steps(self.plan.parent, perf.load_plan(self.plan))[0]
        self.assertEqual(state_title, "corrige antes de medir (avisos de la corrida de prueba)")

    def test_una_prueba_sin_avisos_los_da_por_resueltos_y_medir_igual_tambien_sigue(self):
        self.tp_outputs(self.REPEATED)
        self.ok("capturar", "--plan", self.plan, "--prueba")
        clean = GOOD + '"seccion",400000000,0,0,"MARK reparto"\n'
        self.tp_outputs(clean)
        (self.dir / "tp.count").unlink()
        out = self.ok("capturar", "--plan", self.plan, "--prueba")
        self.assertNotIn("avisos por corregir", out)
        self.assertEqual(perf.test_warnings(self.plan.parent, "home"), [])
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertNotIn("Corrige antes de medir", out)
        self.assertIn("Siguiente · medición antes y control (sin chat)", out)
        # con avisos vigentes, medir igual es una decisión del usuario: con antes medido, el flujo sigue su curso
        self.tp_outputs(self.REPEATED)
        (self.dir / "tp.count").unlink()
        self.ok("capturar", "--plan", self.plan, "--prueba")
        self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "1", "--calentamiento", "0", "--sin-compilar")
        self.assertNotIn("Corrige antes de medir", self.ok("siguiente", "--carpeta", self.plan.parent))

    def test_sin_avisos_guardados_siguiente_es_el_de_siempre(self):
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertNotIn("Corrige antes de medir", out)
        self.assertIn("--prueba", out)
        self.assertFalse((self.plan.parent / perf.NOTES_FILE).exists())

    def test_cada_tipo_de_aviso_queda_en_una_linea_con_su_texto_corto(self):
        info = {"hz_traza": 120, "marcas_plan": [("MARK reparto", ["reparto_ms.hasta"], False),
                                                 ("NAV lista", ["ventana.desde"], True)],
                "faltantes": ["reparto_ms"], "con_input": {"lista_a_reparto_ms": 2}, "marcas_repetidas": {"MARK lista": 3},
                "nombres": {"HTTP GET " + "a" * 118: 1, "HTTP GET corta": 2}}
        found = perf.test_run_warnings(self.dir, 60, info, "RED SIN MEDIR: ...", ["app/Red.kt:10"])
        self.assertEqual([item["tipo"] for item in found], ["hz", "marca", "input", "repetida", "red", "nombre"])
        for item in found:
            self.assertNotIn("\n", item["texto"])
            self.assertLessEqual(len(item["texto"]), perf.NOTE_MAX)
            self.assertTrue(item["corto"])
        self.assertEqual(found[1]["donde"], ["app/src/main/kotlin/com/example/app/RepartoScreen.kt:4"])
        self.assertEqual(found[4]["donde"], ["app/Red.kt:10"])
        self.assertIn("127 caracteres", found[5]["texto"])
        self.assertEqual(perf.test_run_warnings(self.dir, 60, {"hz_traza": 60, "nombres": {"HTTP GET x": 1}}, "", []), [])

    def test_una_prueba_invalida_tambien_frena_la_medicion(self):
        self.tp_outputs(LOGIN)
        result = self.perf("capturar", "--plan", self.plan, "--prueba")
        self.assertEqual(result.returncode, 5)
        saved = perf.test_warnings(self.plan.parent, "home")
        self.assertEqual(saved[0]["tipo"], "invalida")
        self.assertIn("apareció 'SCREEN LoginActivity onCreate'", saved[0]["texto"])
        self.assertIn("Corrige antes de medir", self.ok("siguiente", "--carpeta", self.plan.parent))

    def test_busca_la_marca_en_el_codigo_sin_leer_las_rutas_prohibidas(self):
        self.assertEqual(perf.find_mark_sources(self.dir, "MARK reparto"),
                         ["app/src/main/kotlin/com/example/app/RepartoScreen.kt:4"])
        self.assertEqual(perf.find_mark_sources(self.dir, "MARK reparto", ["app/src/main/kotlin/com/example/app/Reparto*"]), [])
        self.assertEqual(perf.find_mark_sources(self.dir, "MARK otra"), [])
        self.assertEqual(perf.find_mark_sources(self.dir, "SCREEN MainActivity onResume"), [])  # no es una marca de código
        self.assertEqual(perf.find_mark_sources(self.dir, "MARK rep*"), [])  # un patrón no se busca como texto


class SummaryWritesTest(PerfBase):
    def test_resumen_dice_lo_que_escribe_y_solo_imprimir_no_escribe_nada(self):
        help_text = self.ok("resumen", "--help")
        self.assertIn("resumen.md", help_text)
        self.assertIn("estado.md", help_text)
        self.assertIn("--solo-imprimir", help_text)
        write(self.csv, HEADER + rows("antes", "f", "jank_app_pct", [9] * 5, "%"))
        state = "# E\n\n## Métricas\n<!-- perf:metricas -->\nviejo\n<!-- /perf:metricas -->\n"
        write(self.dir / "estado.md", state)
        out = self.ok("resumen", self.csv, "--solo-imprimir")
        self.assertIn("| antes | f | jank_app_pct |", out)
        self.assertIn("no se escribió resumen.md", out)
        self.assertFalse((self.dir / "resumen.md").exists())
        self.assertEqual((self.dir / "estado.md").read_text(encoding="utf-8"), state)
        out = self.ok("resumen", self.csv)
        self.assertTrue((self.dir / "resumen.md").is_file())
        self.assertIn("resumen.md escrito", out)
        self.assertNotIn("viejo", (self.dir / "estado.md").read_text(encoding="utf-8"))


class DiagnosisWarningsTest(DeviceBase):
    """ "Advertencias para el diagnóstico": perf.py escribe en estado.md lo que observó en los comandos de la terminal."""

    def setUp(self):
        super().setUp()
        write(self.plan.parent / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))

    def block(self, folder=None):
        text = ((folder or self.plan.parent) / "estado.md").read_text(encoding="utf-8")
        return text.split("<!-- perf:advertencias -->")[1].split("<!-- /perf:advertencias -->")[0].strip()

    def test_la_plantilla_trae_la_seccion_antes_de_hallazgos_y_sin_advertencias_lo_dice_sin_afirmar_ausencia(self):
        template = (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8")
        self.assertLess(template.index("## Métricas"), template.index("## Advertencias para el diagnóstico"))
        self.assertLess(template.index("## Advertencias para el diagnóstico"), template.index("## Hallazgos"))
        self.assertIn("| Archivo | Repo o módulo | Qué es | Altera | ¿Revertido? |", template)
        self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertEqual(self.block(), "- " + perf.NO_WARNINGS)
        self.assertIn("no prueba que no haya nada que advertir", self.block())

    def test_junta_los_avisos_de_la_prueba_las_invalidas_y_los_avisos_de_la_captura_una_por_linea(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["metricas_usuario"] = [{"nombre": "reparto_ms", "desde": {"marca": "HTTP GET items/{id}"},
                                                       "hasta": {"marca": "MARK reparto"}}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marks = '"seccion",400000000,0,0,"MARK reparto"\n'
        self.tp_outputs(GOOD + marks + '"seccion",450000000,0,0,"MARK reparto"\n')
        self.ok("capturar", "--plan", self.plan, "--prueba")
        self.assertIn("- Corrida de prueba (home): la marca 'MARK reparto' salió 2 veces en una misma carga", self.block())
        (self.dir / "tp.count").unlink()
        self.tp_outputs(LOGIN, GOOD + marks, LOGIN, GOOD + marks)
        self.env["FAKE_THERMAL"] = "1"
        self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "2", "--calentamiento", "0", "--sin-compilar")
        block = self.block()
        self.assertIn("- Corridas inválidas en antes (home): 2 · 2 × apareció 'SCREEN LoginActivity onCreate'", block)
        self.assertIn("- Captura de antes (home): el dispositivo está tibio (Thermal Status 1)", block)
        self.assertIn("- Fase antes: compilación de ART sin fijar (--sin-compilar)", block)
        self.assertIn("- Ruido de `jank_app_pct` (home): sin fase control, el ruido no está medido.", block)
        for line in block.splitlines():
            self.assertTrue(line.startswith("- "), line)  # una línea por advertencia, sin volcar salidas
            self.assertLessEqual(len(line), perf.NOTE_MAX + 80, line)
        # --rehacer descarta esas corridas: lo anotado de ellas ya no vale
        (self.dir / "tp.count").unlink()
        self.tp_outputs(GOOD + marks)
        del self.env["FAKE_THERMAL"]
        self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "1", "--calentamiento", "0", "--rehacer")
        block = self.block()
        self.assertNotIn("Corridas inválidas", block)
        self.assertNotIn("tibio", block)
        self.assertNotIn("sin fijar", block)

    def test_los_fallos_de_preparar_cuentan_como_corridas_invalidas_con_su_motivo(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["preparar"] = "exit 4"
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "5", "--calentamiento", "0",
                           "--sin-compilar")
        self.assertEqual(result.returncode, 5)
        self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertIn("- Corridas inválidas en antes (home): 3 · 3 × 'preparar' terminó con código 4", self.block())

    def test_el_ruido_y_la_mejora_minima_usan_el_criterio_del_veredicto_de_comparar(self):
        plan = {"principales": ["m", "fps", "frames", "sin_antes"]}
        content = HEADER + rows("antes", "f", "m", [100, 104, 98, 101, 102]) + rows("control", "f", "m", [104, 106, 105, 104, 107]) \
            + rows("antes", "f", "fps", [50, 52, 51, 50, 52], "fps", "mayor") \
            + rows("antes", "f", "frames", [100] * 5, "frames", family="info") + rows("antes", "f", "otra", [1] * 5)
        write(self.csv, content)
        lines = perf.noise_lines(perf.read_rows(self.csv), plan)
        self.assertEqual(len(lines), 3)  # las principales con antes; "otra" no es principal
        noisy = next(line for line in lines if "`m`" in line)
        # mediana de antes 101, de control 105: ruido 4; hay que bajar de min(98, 101 - 4) = 97
        self.assertIn("antes y control difieren en 4 ms (3.96 %) sin ningún cambio", noisy)
        self.assertIn("la mediana de después tiene que quedar por debajo de 97 ms (más de 4 ms, 3.96 % respecto de la mediana "
                      "de antes, 101 ms)", noisy)
        before, control = [100, 104, 98, 101, 102], [104, 106, 105, 104, 107]
        self.assertEqual(perf.verdict(before, [96.9] * 5, "menor", control), "mejora")  # justo por debajo del límite
        self.assertNotEqual(perf.verdict(before, [97] * 5, "menor", control), "mejora")  # en el límite todavía no
        higher = next(line for line in lines if "`fps`" in line)
        self.assertIn("sin fase control, el ruido no está medido", higher)
        self.assertIn("por encima de 52 fps", higher)
        self.assertEqual(perf.verdict([50, 52, 51, 50, 52], [52.1] * 5, "mayor"), "mejora")
        self.assertNotEqual(perf.verdict([50, 52, 51, 50, 52], [52] * 5, "mayor"), "mejora")
        self.assertIn("`frames` (f): es informativa", next(line for line in lines if "`frames`" in line))
        soft = perf.noise_lines(perf.read_rows(self.csv), {"principales": ["jank_app_pct"]}, ("no", "emulador"))
        self.assertEqual(soft, [])
        write(self.csv, HEADER + rows("antes", "f", "jank_app_pct", [9] * 5, "%"))
        self.assertIn("frames no confiables (emulador)",
                      perf.noise_lines(perf.read_rows(self.csv), {"principales": ["jank_app_pct"]}, ("no", "emulador"))[0])

    def test_copia_los_cambios_temporales_que_alteran_la_app_con_las_metricas_que_afectan(self):
        state = self.plan.parent / "estado.md"
        text = state.read_text(encoding="utf-8")
        head = "| Archivo | Repo o módulo | Qué es | Altera | ¿Revertido? |\n| --- | --- | --- | --- | --- |\n"
        self.assertIn(head, text)
        state.write_text(text.replace(head, head
                                      + "| `feature/busqueda/Buscador.kt` | feature/busqueda | espera de 300 ms antes de la "
                                        "búsqueda medida | `busqueda_ms`, `red_llamadas` | no |\n"
                                      + "| `feature/detalle/Detalle.kt` | feature/detalle | `MARK detalle` | — | no |\n"),
                         encoding="utf-8")
        self.ok("siguiente", "--carpeta", self.plan.parent)
        block = self.block()
        self.assertIn("- Cambio temporal que altera la app: `feature/busqueda/Buscador.kt` · espera de 300 ms antes de la "
                      "búsqueda medida → altera `busqueda_ms`, `red_llamadas` (¿revertido?: no)", block)
        self.assertNotIn("Detalle.kt", block)  # solo emite una marca: no altera nada
        old = "## Cambios temporales por revertir\n\n| Archivo | Repo o módulo | Qué es | ¿Revertido? |\n| --- | --- | --- | --- |\n" \
              "| `a/B.kt` | a | una marca | no |\n"
        self.assertEqual(perf.altering_changes(old), [])  # la tabla de una versión anterior, sin la columna, se sigue leyendo

    def test_lo_que_el_diagnostico_no_midio_queda_como_advertencia_y_no_como_ausencia(self):
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "1", "--calentamiento", "0")
        self.env["FAKE_TP_OTRA"] = '"a"\n'
        self.ok("diagnostico", "--carpeta", self.plan.parent)
        block = self.block()
        self.assertIn("- Diagnóstico de antes (home): `cpu_por_libreria`: no medido: la configuración base no captura "
                      "ds:linux.perf (no quiere decir que no ocurra)", block)
        notes = perf.read_notes(self.plan.parent)
        self.assertIn("home", notes["diagnostico"]["antes"])
        # una consulta puntual no reemplaza lo que anotó el diagnóstico entero
        self.ok("diagnostico", "--carpeta", self.plan.parent, "--consultas", "hilo_principal_top")
        self.assertEqual(perf.read_notes(self.plan.parent)["diagnostico"], notes["diagnostico"])

    def test_una_investigacion_anterior_sin_la_seccion_la_recibe_antes_de_hallazgos_una_sola_vez(self):
        for version in ("0.6.0", "0.7.0", "0.8.0"):
            fixture = ROOT / "tests" / "fixtures" / ("hb-performance-%s" % version)
            folder = self.dir / version / "reports" / "perf" / "caso"
            for name in ("plan.json", "estado.md", "metricas.csv", "fases.json"):
                write(folder / name, (fixture / name).read_text(encoding="utf-8"))
            for name in ("PERF_USUARIO", "PERF_CLAVE"):
                self.env.pop(name, None)
            self.assertNotIn("perf:advertencias", (folder / "estado.md").read_text(encoding="utf-8"), version)
            self.ok("siguiente", "--carpeta", folder)
            self.ok("siguiente", "--carpeta", folder)
            state = (folder / "estado.md").read_text(encoding="utf-8")
            self.assertEqual(state.count("## Advertencias para el diagnóstico"), 1, version)
            self.assertLess(state.index("## Advertencias para el diagnóstico"), state.index("## Hallazgos"), version)
            self.assertIn("- Ruido de `", self.block(folder), version)  # antes y control ya medidos: sale el ruido
            before = (fixture / "estado.md").read_text(encoding="utf-8")
            self.assertEqual(before.split("## Hallazgos")[1].split("## Decisiones")[0],
                             state.split("## Hallazgos")[1].split("## Decisiones")[0], version)  # el resto no se toca
        bare = self.dir / "sin-secciones"
        write(bare / "plan.json", self.plan.read_text(encoding="utf-8"))
        write(bare / "estado.md", "# Rendimiento\n\n## Siguiente paso\n\n- nada\n\n## Ficha\n\ntexto\n")
        self.ok("siguiente", "--carpeta", bare)
        self.assertTrue((bare / "estado.md").read_text(encoding="utf-8").rstrip().endswith("<!-- /perf:advertencias -->"))


class NoCommitLineTest(DeviceBase):
    """Todo texto de chat que imprime perf.py termina con "No hagas commit ni push."."""

    LINE = "No hagas commit ni push."

    def test_chat_text_la_pone_al_final_tambien_con_rutas_que_no_se_leen(self):
        self.assertEqual(perf.chat_text("Sigue hb-performance con /x/estado.md"),
                         "Sigue hb-performance con /x/estado.md. No hagas commit ni push.")
        self.assertEqual(perf.chat_text("Listo.", {"no_leer": ["docs/ALCANCE-*", "casos/"]}),
                         "Listo. No leas ni busques en: docs/ALCANCE-*, casos/. No hagas commit ni push.")
        self.assertTrue(perf.chat("x", "intermedio", "medio", "y", {})["texto"].endswith(self.LINE))

    def chat_texts(self, out):
        return re.findall(r'Texto: "(.*)"', out)

    def test_siguiente_decidir_reporte_y_humo_terminan_cada_chat_con_la_linea(self):
        folder = self.plan.parent
        write(folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        outputs = {"siguiente (sesión 2)": self.ok("siguiente", "--carpeta", folder)}
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["mejoras"] = [{"id": "M1", "titulo": "Una sola carga", "metrica": "red_solapadas", "esperado": "0"}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        write(folder / "metricas.csv", HEADER + rows("antes", "home", "jank_app_pct", [9] * 5, "%")
              + rows("control", "home", "jank_app_pct", [9] * 5, "%"))
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 5, "skill": perf.VERSION},
                                                 "control": {"fecha": "2026-11-05T10:20:00", "corridas": 5}}))
        outputs["decidir (sesión 3)"] = self.ok("decidir", "--carpeta", folder, "--aprobar", "M1")
        outputs["decidir --aplicada (sesión 4)"] = self.ok("decidir", "--carpeta", folder, "--aplicada", "M1")
        outputs["reporte --inicial"] = self.ok("reporte", "--carpeta", folder, "--inicial")
        self.tp_outputs(GOOD)
        write(self.dir / "reports/perf/setup/pedido.json", json.dumps({"flujo": "de la lista al detalle", "llegar": ""}))
        outputs["humo con pedido"] = self.ok("humo", "--paquete", PKG)
        (self.dir / "reports/perf/setup/pedido.json").unlink()
        outputs["humo sin pedido"] = self.ok("humo", "--paquete", PKG)
        for name, out in outputs.items():
            texts = self.chat_texts(out)
            self.assertTrue(texts, name)
            for text in texts:
                self.assertTrue(text.endswith(self.LINE), (name, text))
                self.assertEqual(text.count(self.LINE), 1, (name, text))
        state = (folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn(self.LINE, state.split("## Siguiente paso")[1].split("## Ficha")[0])  # también en estado.md

    def test_los_prompts_documentados_tambien_la_llevan(self):
        for path in (SCRIPT.parent.parent / "references" / "prompts.md", ROOT / "PROMPTS.md"):
            text = path.read_text(encoding="utf-8")
            if path.name == "PROMPTS.md":
                text = text.split("## hb-performance")[1].split("\n## ")[0]
            blocks = re.findall(r"```text\n(.*?)```", text, re.S)
            self.assertTrue(blocks, path)
            for body in blocks:
                self.assertTrue(body.strip().endswith(self.LINE), (path.name, body))


class ProjectAgentsTest(DeviceBase):
    """El AGENTS.md del proyecto: `siguiente` avisa si falta `## DoD` antes de una sesión 3, y perf.py mantiene un
    bloque corto con el estado del setup dentro de la sección de rendimiento, sin tocar nada más."""

    AGENTS = ("# Proyecto\n\n## Comandos\n\n- `./gradlew test`\n\n## Rendimiento\n\n- applicationId: `com.ejemplo.app`\n"
              "- setup listo\n\n## Git\n\n- Conventional Commits\n")

    def approved(self, **extra):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan.update(extra)
        plan["mejoras"] = [{"id": "M1", "titulo": "Una sola carga", "estado": "aprobada"}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        write(self.plan.parent / "fases.json", json.dumps({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 5},
                                                            "control": {"fecha": "2026-11-05T10:20:00", "corridas": 5}}))

    def test_antes_de_la_sesion_3_avisa_si_falta_dod_e_imprime_una_plantilla(self):
        self.approved(instalar="./gradlew :app:installProfiling")
        write(self.dir / "AGENTS.md", self.AGENTS)
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertIn("Siguiente · sesión 3 · M1", out)
        self.assertIn("AGENTS.md no tiene `## DoD`: la sesión 3 corre", out)
        self.assertIn("\n  ## DoD\n", out)
        template = "".join(line + "\n" for line in out.splitlines() if line.startswith(("  ## DoD", "  1. `", "  2. `")))
        write(self.dir / "AGENTS.md", self.AGENTS + "\n" + template)  # pegada tal cual, con su sangría, el aviso se va
        self.assertNotIn("no tiene `## DoD`", self.ok("siguiente", "--carpeta", self.plan.parent))
        write(self.dir / "AGENTS.md", self.AGENTS)
        self.assertIn("./gradlew :<módulo>:tasks --all | grep UnitTest", out)
        self.assertIn("`./gradlew -q :app:assembleProfiling`: compila la variante medida", out)  # del 'instalar' del plan
        for tool in ("ktlint", "detekt", "sonar"):
            self.assertNotIn(tool, out.lower())  # nunca agrega herramientas
        self.assertLess(out.index("AGENTS.md no tiene `## DoD`"), out.index("1. Chat nuevo"))  # el aviso va antes del chat
        self.assertIn("sesión 3, aplica M1", out)

    def test_con_dod_no_avisa_y_sin_agents_lo_dice(self):
        self.approved()
        write(self.dir / "AGENTS.md", self.AGENTS + "\n## DoD\n\n1. `./gradlew test`\n")
        self.assertNotIn("## DoD", self.ok("siguiente", "--carpeta", self.plan.parent))
        (self.dir / "AGENTS.md").unlink()
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertIn("No hay AGENTS.md en ", out)
        self.assertIn("./gradlew -q :<módulo-de-la-app>:assemble<VarianteMedida>", out)  # sin 'instalar', la plantilla genérica
        self.assertIsNone(perf.dod_notice(self.dir, {}) if (self.dir / "AGENTS.md").exists() else None)
        for heading in ("## DoD", "### Definition of Done", "## Definición de hecho", "## 5. DoD"):
            write(self.dir / "AGENTS.md", "# P\n\n%s\n\n- algo\n" % heading)
            self.assertIsNone(perf.dod_notice(self.dir, {}), heading)
        write(self.dir / "AGENTS.md", "\ufeff## DoD\n\n- algo\n")  # con BOM, como los demás encabezados
        self.assertIsNone(perf.dod_notice(self.dir, {}))
        write(self.dir / "AGENTS.md", "# P\n\n```markdown\n## DoD\n```\n")  # dentro de un bloque de código no cuenta
        self.assertIsNotNone(perf.dod_notice(self.dir, {}))

    def test_fuera_de_la_sesion_3_no_avisa(self):
        write(self.dir / "AGENTS.md", self.AGENTS)
        self.assertNotIn("## DoD", self.ok("siguiente", "--carpeta", self.plan.parent))

    def test_humo_deja_el_estado_del_setup_en_la_seccion_de_rendimiento_y_nada_mas(self):
        write(self.dir / "AGENTS.md", self.AGENTS)
        write(self.dir / "app/src/main/kotlin/PerfHooks.kt", "object PerfHooks\n")
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        today = datetime.date.today().isoformat()
        self.assertIn("✔ AGENTS.md: estado del setup actualizado en la sección de rendimiento", out)
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        line = ("- Estado del setup (lo mantiene `perf.py`: no lo edites): instrumentación en el repo: sí · prueba de humo: "
                "pasó el %s · secciones HTTP: sí (prueba de humo, %s) · hb-performance %s" % (today, today, perf.VERSION))
        self.assertIn("<!-- hb-performance:estado -->\n%s\n<!-- /hb-performance:estado -->\n" % line, text)
        before, after = self.AGENTS.split("## Git")
        self.assertTrue(text.startswith(before.rstrip("\n")))  # lo de antes de la sección y la sección misma, intactos
        self.assertTrue(text.endswith("## Git" + after))  # lo que sigue a la sección, intacto
        self.assertLess(text.index("hb-performance:estado"), text.index("## Git"))
        self.ok("humo", "--paquete", PKG)  # otra vez: un solo bloque, el mismo
        again = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(again, text)
        self.assertEqual(again.count("<!-- hb-performance:estado -->"), 1)

    def test_un_humo_que_falla_o_sin_red_no_deja_un_estado_viejo(self):
        write(self.dir / "AGENTS.md", self.AGENTS)
        self.tp_outputs(GOOD)
        self.ok("humo", "--paquete", PKG)
        self.tp_outputs(LOGIN.replace('"frame",0,16000000,0,"None"\n', ""))  # una corrida que no vale
        (self.dir / "tp.count").unlink()
        result = self.perf("humo", "--paquete", PKG)
        self.assertNotEqual(result.returncode, 0)
        today = datetime.date.today().isoformat()
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("prueba de humo: falló el %s" % today, text)
        self.assertNotIn("pasó el", text)
        no_http = GOOD.replace('"seccion",0,300000000,0,"HTTP GET items/{id}"\n', "").replace(
            '"seccion",100000000,300000000,0,"HTTP GET items/{id}"\n', "")
        self.tp_outputs(no_http)
        (self.dir / "tp.count").unlink()
        write(self.dir / "AGENTS.md", self.AGENTS)  # un proyecto donde ninguna corrida vio la red
        self.ok("humo", "--paquete", PKG, "--sin-red")
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("prueba de humo: pasó el %s · secciones HTTP: no exigidas (humo --sin-red, %s)" % (today, today), text)

    def test_sin_seccion_de_rendimiento_no_la_crea_y_lo_dice(self):
        original = "# Proyecto\n\n## Comandos\n\n- `./gradlew test`\n"
        write(self.dir / "AGENTS.md", original)
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        self.assertIn("AGENTS.md no tiene una sección de rendimiento (## Rendimiento o ## Performance): no la creo", out)
        self.assertEqual((self.dir / "AGENTS.md").read_text(encoding="utf-8"), original)
        (self.dir / "AGENTS.md").unlink()
        self.assertIn("No hay AGENTS.md en ", self.ok("humo", "--paquete", PKG))
        self.assertFalse((self.dir / "AGENTS.md").exists())

    def test_la_corrida_de_prueba_anota_la_red_una_vez_y_conserva_lo_demas_del_bloque(self):
        english = self.AGENTS.replace("## Rendimiento", "## Performance")
        write(self.dir / "AGENTS.md", english + "\n")
        self.assertEqual(perf.update_agents_state(self.dir, humo="pasó el 2026-11-01", http="sin dato"),
                         "✔ AGENTS.md: estado del setup actualizado en la sección de rendimiento (instrumentación en el repo: "
                         "no (no encontré PerfHooks.kt) · prueba de humo: pasó el 2026-11-01 · secciones HTTP: sin dato)")
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--prueba")
        self.assertIn("✔ AGENTS.md: estado del setup actualizado", out)
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        today = datetime.date.today().isoformat()
        self.assertIn("prueba de humo: pasó el 2026-11-01 · secciones HTTP: sí (corrida de prueba, %s)" % today, text)
        out = self.ok("capturar", "--plan", self.plan, "--prueba")  # ya dice que sí: no se reescribe en cada prueba
        self.assertNotIn("AGENTS.md", out)
        self.assertEqual((self.dir / "AGENTS.md").read_text(encoding="utf-8"), text)

    def test_no_toca_nada_fuera_del_bloque_con_fences_encabezados_ajenos_ni_crlf(self):
        fenced = ("# P\n\n## Reglas\n\n### No degradar el rendimiento\n\n- regla\n\n## Rendimiento\n\n```bash\n"
                  "# instala el build\n./gradlew :app:installProfiling\n```\n\n## Git\n\n- c\n")
        write(self.dir / "AGENTS.md", fenced)
        self.assertIn("✔", perf.update_agents_state(self.dir, humo="pasó el 2026-11-01"))
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        block_at = text.index("<!-- hb-performance:estado -->")
        self.assertLess(text.index("```\n\n<!--"), block_at)  # después del bloque de código, no dentro
        self.assertLess(text.index("## Rendimiento"), block_at)  # en la sección que se llama así, no en la regla que la menciona
        self.assertLess(block_at, text.index("## Git"))
        self.assertEqual(text.replace(text[block_at:text.index("## Git")], ""), fenced)  # lo demás, byte por byte
        self.assertIsNone(perf.performance_section("# P\n\n## Reglas\n\n### No degradar el rendimiento\n\n- regla\n"))
        crlf = self.AGENTS.replace("\n", "\r\n")
        with open(str(self.dir / "AGENTS.md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(crlf)
        self.assertIn("✔", perf.update_agents_state(self.dir, humo="pasó el 2026-11-01"))
        with open(str(self.dir / "AGENTS.md"), encoding="utf-8", newline="") as handle:
            text = handle.read()
        self.assertNotIn("\n", text.replace("\r\n", ""))  # el archivo sigue entero en CRLF, también el bloque
        self.assertTrue(text.endswith("## Git\r\n\r\n- Conventional Commits\r\n"))
        self.assertEqual(perf.update_agents_state(self.dir, humo="pasó el 2026-11-01"), "")  # idempotente
        loose = "# P\n\n## Rendimiento\n\n- a\n<!-- hb-performance:estado -->\n"  # un marcador de apertura suelto
        write(self.dir / "AGENTS.md", loose)
        perf.update_agents_state(self.dir, humo="pasó el 2026-11-01")
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual((text.count("<!-- hb-performance:estado -->"), text.count("<!-- /hb-performance:estado -->")), (1, 1))

    def test_un_agents_que_no_se_puede_escribir_no_rompe_humo_ni_tapa_su_resultado(self):
        write(self.dir / "AGENTS.md", self.AGENTS)
        (self.dir / "AGENTS.md").chmod(0o444)
        if os.access(str(self.dir / "AGENTS.md"), os.W_OK):
            self.skipTest("este usuario escribe aunque el archivo sea de solo lectura")
        write(self.dir / "reports/perf/setup/pedido.json", json.dumps({"flujo": "de la lista al detalle", "llegar": ""}))
        self.tp_outputs(GOOD)
        out = self.ok("humo", "--paquete", PKG)
        self.assertIn("⚠ No pude escribir ", out)
        self.assertIn("Usa hb-performance: medir de la lista al detalle", out)  # el paso siguiente sale igual
        self.assertEqual((self.dir / "AGENTS.md").read_text(encoding="utf-8"), self.AGENTS)

    def test_un_humo_sin_red_no_pisa_la_red_que_ya_vio_otra_corrida_y_una_precondicion_no_es_un_humo_fallido(self):
        write(self.dir / "AGENTS.md", self.AGENTS)
        perf.update_agents_state(self.dir, humo="pasó el 2026-11-01", http="sí (corrida de prueba, 2026-11-02)")
        no_http = GOOD.replace('"seccion",0,300000000,0,"HTTP GET items/{id}"\n', "").replace(
            '"seccion",100000000,300000000,0,"HTTP GET items/{id}"\n', "")
        self.tp_outputs(no_http)
        self.ok("humo", "--paquete", PKG, "--sin-red")
        self.assertIn("secciones HTTP: sí (corrida de prueba, 2026-11-02)", (self.dir / "AGENTS.md").read_text(encoding="utf-8"))
        self.env["FAKE_THERMAL"] = "3"  # el dispositivo está caliente: el humo no llegó a correr
        self.assertEqual(self.perf("humo", "--paquete", PKG).returncode, 3)
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("prueba de humo: pasó el %s" % datetime.date.today().isoformat(), text)  # lo anotado sigue valiendo
        self.assertNotIn("falló", text)

    def test_la_seccion_termina_en_el_siguiente_encabezado_de_su_nivel_o_superior(self):
        text = "# P\n\n## Rendimiento\n\n- a\n\n### Detalle\n\n- b\n\n## Git\n\n- c\n"
        start, end = perf.performance_section(text)
        self.assertEqual(text[start:end], "\n- a\n\n### Detalle\n\n- b\n\n")
        self.assertIsNone(perf.performance_section("# P\n\n## Comandos\n"))
        last = "# P\n\n## Performance\n\n- a\n"
        self.assertEqual(perf.performance_section(last), (last.index("\n- a"), len(last)))
        self.assertEqual(perf.agents_state("x <!-- hb-performance:estado -->\n- Estado: prueba de humo: pasó · secciones HTTP: sí "
                                           "(x) · hb-performance 0.10.0\n<!-- /hb-performance:estado -->"),
                         {"prueba de humo": "pasó", "secciones HTTP": "sí (x)"})
        self.assertIsNone(perf.http_state("sí (prueba de humo, 2026-11-01)", True, "corrida de prueba"))
        self.assertIsNone(perf.http_state("sí (x)", False, "corrida de prueba"))  # un flujo sin llamadas no lo desmiente
        self.assertIn("sin medir", perf.http_state("sin dato", False, "corrida de prueba"))
        nested = "## Rendimiento\n\n````\n```\n# no es un encabezado\n```\n````\n\n~~~\n```\n# tampoco\n~~~\n\n## Git\n"
        start, end = perf.performance_section(nested)
        self.assertEqual(nested[end:], "## Git\n")  # los fences anidados o mezclados no cortan la sección
        self.assertIsNotNone(perf.performance_section("  ## Rendimiento\n\n- a\n"))  # con sangría, como DoD
        self.assertIn("`./gradlew -q assembleProfiling`", " ".join(perf.dod_notice(self.dir / "no-hay", {
            "instalar": "./gradlew installProfiling"})["lineas"]))  # sin módulo en 'instalar', la tarea va sin ':' 


class LastBeforeTest(unittest.TestCase):
    """`"cual": "ultima_antes"` en `desde`: la última ocurrencia de la marca antes de la marca `hasta` elegida. Sirve
    cuando la marca de inicio sale varias veces (cada letra de una búsqueda) y se elige en el plan, sin tocar la app."""

    START = {"marca": "MARK busqueda_inicio", "cual": "ultima_antes"}

    def trace(self):
        # una búsqueda que carga con cada letra: tres inicios, dos resultados intermedios y el resultado final
        return [("proceso", 0, 0, 0, PKG), ("limites", 0, 5000 * MS, 0, "")] \
            + [("frame", i * 20 * MS, 16 * MS, 0, "None") for i in range(150)] \
            + [("hilo", 2050 * MS, 30 * MS, 0, "Choreographer#doFrame"), ("hilo", 1010 * MS, 80 * MS, 0, "Choreographer#doFrame"),
               ("seccion", 1000 * MS, 0, 0, "MARK busqueda_inicio"), ("seccion", 1300 * MS, 0, 0, "MARK busqueda_inicio"),
               ("seccion", 1500 * MS, 0, 0, "MARK resultados"), ("seccion", 2000 * MS, 0, 0, "MARK busqueda_inicio"),
               ("seccion", 2100 * MS, 0, 0, "MARK resultados"), ("seccion", 2400 * MS, 0, 0, "MARK resultados"),
               ("seccion", 3000 * MS, 0, 0, "MARK busqueda_inicio"),  # otra búsqueda, después del último resultado
               ("seccion", 2010 * MS, 200 * MS, 0, "HTTP GET api/v1/clientes"), ("seccion", 1010 * MS, 100 * MS, 0, "HTTP GET api/v1/clientes")]

    def metrics(self, flow):
        out, invalid, info = perf.trace_metrics(self.trace(), 60, flow, set(), 34)
        self.assertIsNone(invalid)
        return {m[0]: m[1] for m in out}, info

    def test_en_una_metrica_de_usuario_elige_el_inicio_que_precede_al_resultado(self):
        def flow(start, end):
            return {"metricas_usuario": [{"nombre": "busqueda_ms", "desde": start, "hasta": end}]}

        last = self.metrics(flow(self.START, {"marca": "MARK resultados"}))[0]
        self.assertEqual(last["busqueda_ms"], 400)  # del inicio de los 2000 ms al último resultado (2400)
        first = self.metrics(flow(self.START, {"marca": "MARK resultados", "cual": "primera"}))[0]
        self.assertEqual(first["busqueda_ms"], 200)  # del inicio de los 1300 ms al primer resultado (1500)
        # lo de siempre no cambia: 'primera' toma el primer inicio y 'ultima', el último de toda la traza
        self.assertEqual(self.metrics(flow({"marca": "MARK busqueda_inicio"}, {"marca": "MARK resultados"}))[0]["busqueda_ms"],
                         1400)
        _, info = self.metrics(flow({"marca": "MARK busqueda_inicio", "cual": "ultima"}, {"marca": "MARK resultados"}))
        self.assertEqual(info["faltantes"], ["busqueda_ms"])  # el último inicio queda después de todo resultado

    def test_funciona_igual_en_la_ventana_y_en_los_tramos(self):
        span = {"desde": self.START, "hasta": {"marca": "MARK resultados"}}
        flow = {"ventana": dict(span), "segmentos": [dict(span, nombre="busqueda")]}
        out, info = self.metrics(flow)
        self.assertEqual(info["ventana_ns"], (2000 * MS, 2400 * MS))
        self.assertEqual(out["ventana_ms"], 400)
        self.assertEqual(out["hilo_max_ms"], 30)  # el slice de 80 ms es de una búsqueda anterior: queda fuera
        self.assertEqual(out["busqueda hilo_max_ms"], 30)
        self.assertEqual(out["busqueda red_llamadas"], 1)  # solo la llamada que empieza en el tramo
        self.assertEqual(perf.span_bounds(sorted(self.trace(), key=lambda r: r[1]), span), (2000 * MS, 2400 * MS))

    def test_el_nombre_de_la_marca_se_compara_exacto_o_como_patron_y_un_prefijo_no_se_confunde(self):
        rows = [("seccion", 100 * MS, 0, 0, "MARK busqueda_inicio lista"), ("seccion", 200 * MS, 0, 0, "MARK busqueda_inicio"),
                ("seccion", 300 * MS, 0, 0, "MARK busqueda_inicio lista"), ("seccion", 500 * MS, 0, 0, "MARK resultados")]
        exact = {"desde": self.START, "hasta": {"marca": "MARK resultados"}}
        self.assertEqual(perf.resolve_span(rows, exact), (200 * MS, 500 * MS))  # exacto: el nombre más largo no cuenta
        pattern = {"desde": {"marca": "MARK busqueda_inicio*", "cual": "ultima_antes"}, "hasta": {"marca": "MARK resultados"}}
        self.assertEqual(perf.resolve_span(rows, pattern), (300 * MS, 500 * MS))  # con * entran las dos
        self.assertEqual(perf.resolve_span(rows, {"desde": self.START, "hasta": {"marca": "MARK no_esta"}}), (None, None))
        early = [("seccion", 100 * MS, 0, 0, "MARK resultados"), ("seccion", 200 * MS, 0, 0, "MARK busqueda_inicio")]
        self.assertEqual(perf.resolve_span(early, exact), (None, 100 * MS))  # ningún inicio antes del resultado: falta, no se inventa

    def test_una_marca_elegida_con_ultima_antes_no_cuenta_como_marca_repetida(self):
        rows = [("proceso", 0, 0, 0, PKG), ("frame", 0, 16 * MS, 0, "None")] \
            + [("seccion", t * MS, 0, 0, "MARK busqueda_inicio") for t in (100, 200, 300)] \
            + [("seccion", 500 * MS, 0, 0, "MARK resultados"), ("seccion", 600 * MS, 0, 0, "MARK resultados")]
        flow = {"metricas_usuario": [{"nombre": "busqueda_ms", "desde": self.START, "hasta": {"marca": "MARK resultados"}}]}
        info = perf.trace_metrics(rows, 60, flow, set(), 34)[2]
        self.assertEqual(info["marcas_repetidas"], {"MARK resultados": 2})  # la de inicio se repite a propósito
        plain = {"metricas_usuario": [{"nombre": "busqueda_ms", "desde": {"marca": "MARK busqueda_inicio"},
                                       "hasta": {"marca": "MARK resultados"}}]}
        self.assertEqual(perf.trace_metrics(rows, 60, plain, set(), 34)[2]["marcas_repetidas"],
                         {"MARK busqueda_inicio": 3, "MARK resultados": 2})  # sin ultima_antes, el aviso de siempre

    def test_el_plan_la_acepta_en_desde_y_la_rechaza_en_hasta_y_en_las_pausas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"

            def load(flow):
                path.write_text(json.dumps({"paquete": PKG, "flujos": {"f": flow}}), encoding="utf-8")
                return perf.load_plan(path)

            end = {"marca": "MARK resultados"}
            load({"metricas_usuario": [{"nombre": "m", "desde": self.START, "hasta": end}],
                  "segmentos": [{"nombre": "t", "desde": self.START, "hasta": end}],
                  "ventana": {"desde": self.START, "hasta": end}})
            for bad in ({"metricas_usuario": [{"nombre": "m", "desde": {"marca": "NAV x"}, "hasta": dict(end, cual="ultima_antes")}]},
                        {"segmentos": [{"nombre": "t", "desde": {"marca": "NAV x"}, "hasta": dict(end, cual="ultima_antes")}]},
                        {"ventana": {"desde": {"marca": "NAV x"}, "hasta": dict(end, cual="ultima_antes")}},
                        {"pausas": [{"desde": self.START, "hasta": end}]}):
                with self.assertRaises(perf.PerfError, msg=str(bad)):
                    load(bad)
            with self.assertRaises(perf.PerfError) as raised:
                load({"metricas_usuario": [{"nombre": "m", "desde": {"marca": "NAV x", "cual": "penultima"}, "hasta": end}]})
            self.assertIn("ultima_antes", str(raised.exception))


class SectionNameLimitTest(DeviceBase):
    """Nombres de endpoint largos: la plantilla acorta desde la izquierda y la corrida de prueba avisa de los cortados."""

    @staticmethod
    def shorten(method, path, tag, limit=120):
        """La misma regla que HttpSectionName.shorten de la plantilla Kotlin (hashCode de Java), para comprobar sus
        propiedades sin compilar Kotlin."""
        def short_hash(text):
            code = 0
            for char in text:
                code = (31 * code + ord(char)) & 0xFFFFFFFF
            return "%04x" % (code & 0xFFFF)

        room = limit - len(method) - 1 - len(tag)
        if len(path) <= room:
            return "%s %s%s" % (method, path, tag)
        kept = path[len(path) - max(room - 5, 0):] if room - 5 > 0 else ""
        tail = kept[max(kept.find("/"), 0):]
        return "%s ~%s%s%s" % (method, short_hash(path[:len(path) - len(tail)]), tail, tag)

    def test_las_dos_plantillas_acortan_desde_la_izquierda_dentro_del_limite(self):
        base = SCRIPT.parent.parent / "assets" / "instrumentacion"
        for name in ("HttpSectionName.okhttp.kt", "HttpSectionName.retrofit.kt"):
            text = (base / name).read_text(encoding="utf-8")
            self.assertIn("const val MAX_ENDPOINT_NAME = MAX_SECTION_NAME - LONGEST_PREFIX_LENGTH - 1", text, name)
            self.assertIn("fun shorten(method: String, path: String, tag: String): String", text, name)
            self.assertIn('return "$method ~${shortHash(path.dropLast(tail.length))}$tail$tag"', text, name)
            self.assertRegex(text, r"fun endpoint\(request: Request\): String =\s+shorten\(request\.method, ", name)
            self.assertLessEqual(max(len(line) for line in text.splitlines()), 120, name)  # el estilo que ya cumplen
        tracer = (base / "SectionTracer.kt").read_text(encoding="utf-8")
        self.assertIn("const val MAX_SECTION_NAME = %d" % perf.SECTION_NAME_MAX, tracer)  # el mismo límite en los dos lados
        tests = (base / "test" / "TraceEventListenerTest.kt").read_text(encoding="utf-8")
        self.assertIn("fun aLongPathIsShortenedFromTheLeftAndFitsInASectionName()", tests)
        self.assertIn("fun aPathThatFitsKeepsItsNameAndAHugeSegmentIsStillCapped()", tests)

    def test_la_regla_conserva_el_final_de_la_ruta_y_distingue_prefijos(self):
        gateway = "/gateway/" + "segmento-largo/" * 12
        orders = self.shorten("GET", gateway + "clientes/{id}/pedidos", " #1a2b")
        self.assertLess(len("QUEUE " + orders), perf.SECTION_NAME_MAX)  # nunca llega al límite: no dispara el aviso
        self.assertRegex(orders, r"^GET ~[0-9a-f]{4}/.*clientes/\{id\}/pedidos #1a2b$")
        self.assertNotEqual(orders, self.shorten("GET", gateway + "clientes/{id}/facturas", " #1a2b"))
        self.assertNotEqual(orders, self.shorten("GET", "/otro" + gateway + "clientes/{id}/pedidos", " #1a2b"))
        self.assertEqual(self.shorten("GET", "/items/{id}", ""), "GET /items/{id}")  # un nombre que cabe no cambia
        self.assertEqual(perf.endpoint_of("HTTP " + orders), orders[:-len(" #1a2b")])  # perf.py lo lee como cualquier otro
        self.assertEqual(perf.at_limit({"HTTP " + orders: 1, "HTTP GET " + "a" * 118: 2, "MARK x": 1}),
                         ["HTTP GET " + "a" * 118])

    def test_la_corrida_de_prueba_avisa_si_un_nombre_de_seccion_llega_al_limite(self):
        long_name = ("HTTP GET /gateway/" + "segmento-largo/" * 10)[:perf.SECTION_NAME_MAX]
        self.assertEqual(len(long_name), 127)
        self.tp_outputs(GOOD + '"seccion",200000000,100000000,0,"%s"\n' % long_name)
        out = self.ok("capturar", "--plan", self.plan, "--prueba")
        self.assertIn("⚠ 1 nombres de sección llegan al límite de 127 caracteres de android.os.Trace y están cortados", out)
        self.assertIn("perf.py instrumentar --actualizar", out)
        self.assertEqual([item["tipo"] for item in perf.test_warnings(self.plan.parent, "home")], ["nombre"])
        self.assertIn("Corrige antes de medir", self.ok("siguiente", "--carpeta", self.plan.parent))
        (self.dir / "tp.count").unlink()
        self.tp_outputs(GOOD)
        self.assertNotIn("llegan al límite", self.ok("capturar", "--plan", self.plan, "--prueba"))


class WarningShapesTest(PerfBase):
    def test_formas_inesperadas_en_advertencias_json_no_rompen_ni_se_parten_en_caracteres(self):
        write(self.dir / "advertencias.json", json.dumps({
            "prueba": {"home": {"avisos": [{"tipo": "x", "texto": "dos\nlíneas", "donde": "app/Red.kt:10"}]}},
            "capturar": {"antes": {"home": "un texto suelto"}}, "diagnostico": {"antes": {"home": 5}},
            "invalidas": {"antes": {"home": {"motivo": "tres"}}}}))
        lines = perf.warnings_lines(self.dir, {"flujos": {"home": {}}})
        self.assertEqual(lines, ["Corrida de prueba (home): dos líneas", "Corridas inválidas en antes (home): 0 · 0 × motivo"])
        write(self.dir / "advertencias.json", json.dumps({"diagnostico": {"antes": {"home": ["`x`: no medido"]}},
                                                          "invalidas": {"antes": {"home": {"m": 1}}}}))
        perf.forget_notes(self.dir, "antes", "home")  # --rehacer también olvida lo que el diagnóstico anotó de esas corridas
        self.assertEqual(perf.warnings_lines(self.dir, {"flujos": {"home": {}}}), [])
