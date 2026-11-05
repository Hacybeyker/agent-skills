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
        self.assertEqual(m["jank_total_pct"][1], 30)
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
    print("List of devices attached\nemulator-5554\tdevice\n")
    sys.exit(0)
if args[0] == "pull":
    pathlib.Path(args[2]).write_bytes(b"x" * 4096)
    sys.exit(0)
cmd = " ".join(args[1:])
if cmd.startswith("getprop"):
    print(os.environ.get("FAKE_SDK", "34"))
elif cmd.startswith("pm path"):
    print("package:/data/app/base.apk")
elif cmd.startswith("dumpsys package"):
    print("    flags=[ HAS_CODE ALLOW_BACKUP ]")
elif cmd.startswith("dumpsys thermalservice"):
    print("Thermal Status: " + os.environ.get("FAKE_THERMAL", "0"))
elif cmd.startswith("dumpsys battery"):
    print("  level: 90")
elif cmd.startswith("dumpsys activity activities"):
    print("  topResumedActivity=ActivityRecord{{1 u0 com.ejemplo.app/.MainActivity t5}}")
elif cmd.startswith("cmd package compile"):
    print("Success")
elif cmd.startswith("perfetto"):
    sys.stdin.read()
    print("4242")
elif cmd.startswith("kill -0"):
    sys.exit(1)
elif cmd.startswith("dumpsys meminfo"):
    print("  Java Heap:  2048\n  TOTAL PSS:  51200   TOTAL RSS: 1\n  Views:  10\n  Activities:  1")
'''

FAKE_TP = r'''#!{python}
import os, sys
assert sys.argv[1:3] == ["query", "-f"], sys.argv
path = os.environ["FAKE_TP_OUT"]
counter = os.environ["FAKE_TP_COUNTER"]
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
outputs = open(path).read().split("===\n")
sys.stdout.write(outputs[min(n, len(outputs) - 1)])
'''

GOOD = '"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.ejemplo.app"\n"limites",0,5000000000,0,""\n' + \
    "".join('"frame",%d,16000000,0,"None"\n' % (i * 20000000) for i in range(9)) + \
    '"frame",500000000,40000000,0,"App Deadline Missed"\n"hilo",0,30000000,0,"Choreographer#doFrame"\n' \
    '"seccion",0,300000000,0,"HTTP GET items/{id}"\n"seccion",100000000,300000000,0,"HTTP GET items/{id}"\n' \
    '"seccion",10,5,0,"SCREEN MainActivity onResume"\n'
LOGIN = '"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.ejemplo.app"\n"frame",0,16000000,0,"None"\n' \
    '"seccion",0,1000,0,"SCREEN LoginActivity onCreate"\n'


class CaptureTest(PerfBase):
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
                         "FAKE_TP_COUNTER": str(self.dir / "tp.count"), "HB_PERF_ESPERA": "0"})
        self.env.pop("TRACE_PROCESSOR", None)
        self.env.pop("ADB", None)
        self.plan = self.dir / "inv" / "plan.json"
        write(self.plan, json.dumps({"paquete": PKG, "hz": 60, "principales": ["jank_app_pct"], "flujos": {
            "home": {"inicio": "MainActivity", "invalidar_si": ["SCREEN *Login*"], "recorrido": "true"}}}))

    def tp_outputs(self, *outputs):
        write(self.dir / "tp.txt", "===\n".join(outputs))

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
        self.assertIn("cmd package compile -f -m speed-profile %s" % PKG, log)
        self.assertIn("kill -TERM 4242", log)

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
        self.assertIn("HTTP GET items/{id} ×2", out)
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
        md = (folder / "reporte.md").read_text(encoding="utf-8")
        self.assertIn("## Métricas principales", md)
        self.assertIn("El jank bajó **mucho**.", md)
        page = (folder / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("<title>Rendimiento · &lt;Home&gt; · 2026-01-02</title>", page)
        self.assertIn("Doble &lt;carga&gt;", page)
        self.assertIn("<strong>mucho</strong>", page)
        self.assertIn('class="verdict v-better">mejora', page)
        self.assertIn("<svg", page)
        self.assertNotIn("{{", page)

    def test_reporte_exige_estado(self):
        self.assertEqual(self.perf("reporte", "--carpeta", self.dir).returncode, 2)


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

    def test_sin_red_no_copia_lo_de_okhttp_y_valida_el_paquete(self):
        module = self.dir / "app"
        write(module / "build.gradle.kts", "dependencies { implementation(libs.androidx.fragment) }")
        self.ok("instrumentar", "--modulo", module, "--paquete", "com.ejemplo.perf")
        base = module / "src/perf/kotlin/com/ejemplo/perf"
        self.assertFalse((base / "TraceEventListener.kt").exists())
        self.assertIn("FragmentManager", (base / "ScreenTraceCallbacks.kt").read_text(encoding="utf-8"))
        self.assertEqual(self.perf("instrumentar", "--modulo", module, "--paquete", "Com.Malo").returncode, 2)
        self.assertEqual(self.perf("instrumentar", "--modulo", self.dir, "--paquete", "com.a.b").returncode, 2)


if __name__ == "__main__":
    unittest.main()
