"""Tests de hb-performance 0.19.0 · V: la red de la corrida de prueba, sincronizada con su video. Los datos son
inventados."""
import json
import types
import unittest

from helpers import write
from test_perf import GOOD, HEADER, PKG, CaptureCase, PerfBase, perf, rows

MS = 1_000_000
FASES = [{"desde": 0.0, "hasta": 1.0, "rotulo": "Preparación · sin traza, no se mide", "tipo": "prep"},
         {"desde": 1.0, "hasta": 4.0, "rotulo": "Medición · Lista", "tipo": "med"},
         {"desde": 4.0, "hasta": 5.0, "rotulo": "Fin de la prueba", "tipo": "fin"}]
# La traza: dos llamadas al mismo servicio (la segunda reusa la conexión), una marca conocida y un toque.
TRAZA = [("limites", 100 * 10 ** 9, 5 * 10 ** 9, 0, ""),
         ("seccion", 101_500 * MS, 2 * MS, 0, "MARK lista"), ("input", 101_200 * MS, 0, 0, ""),
         ("seccion", 101_300 * MS, 400 * MS, 0, "HTTP GET items/{id} #1a2b"),
         ("seccion", 101_300 * MS, 20 * MS, 0, "QUEUE GET items/{id} #1a2b"),
         ("seccion", 101_320 * MS, 180 * MS, 0, "CONN GET items/{id} #1a2b"),
         ("seccion", 101_500 * MS, 150 * MS, 0, "TTFB GET items/{id} #1a2b"),
         ("seccion", 102_000 * MS, 200 * MS, 0, "HTTP GET items/{id} #1a2b"),
         ("seccion", 102_000 * MS, 5 * MS, 0, "QUEUE GET items/{id} #1a2b"),
         ("seccion", 102_010 * MS, 160 * MS, 0, "TTFB GET items/{id} #1a2b")]


def record(ident, start, query, code=200, body='{"items": []}', section="HTTP GET items/{id} #1a2b"):
    request = {"id": ident, "seccion": section, "inicio_ns": start, "metodo": "GET",
               "url": "https://api.ejemplo.test/v1/items/42?%s" % query,
               "headers": [["Authorization", "Bearer token-de-prueba"], ["Cookie", "sesion=abc"]], "cuerpo": None}
    response = {"id": ident, "seccion": section, "inicio_ns": start, "fin_ns": start + 380 * MS, "codigo": code,
                "headers": [["Content-Type", "application/json"]], "bytes_red": 2048, "cuerpo": body,
                "cuerpo_tipo": "application/json", "cuerpo_bytes": len(body or "")}
    return {"request": request, "response": response}


class SyncTest(unittest.TestCase):
    """V2: el uptime del dispositivo al armar el primer tramo lleva la traza al reloj del video; el otro camino (hora del
    dispositivo y ClockSnapshot) lo valida en una marca conocida, con ±100 ms de tolerancia."""

    def video(self, gap_s, uptime=100.0, convert=True):
        origin = 5000.0  # la hora de la computadora del primer cuadro
        return types.SimpleNamespace(
            starts=[origin], recorder=types.SimpleNamespace(uptimes=[uptime]), rows=TRAZA,
            convert=(lambda ns: origin + ns / 1e9 - 100.0 - gap_s) if convert else None)

    def test_validada_dentro_de_la_tolerancia(self):
        to_video, sync = perf.test_sync(self.video(0.038))
        self.assertAlmostEqual(to_video(101_500 * MS), 1.5)  # la marca, 1,5 s después del primer cuadro
        self.assertEqual((sync["estado"], sync["desfase_ms"], sync["marca"]), ("validada", 38, "MARK lista"))
        self.assertEqual(sync["tolerancia_ms"], 100)

    def test_fuera_de_tolerancia_lo_dice(self):
        self.assertEqual(perf.test_sync(self.video(0.4))[1]["estado"], "fuera de tolerancia")

    def test_sin_el_otro_reloj_queda_sin_validar_y_lo_dice(self):
        to_video, sync = perf.test_sync(self.video(0, convert=False))
        self.assertIsNotNone(to_video)
        self.assertEqual(sync["estado"], "sin validar")
        self.assertIn("falta el otro reloj", sync["detalle"])
        to_video, sync = perf.test_sync(self.video(0, uptime=None, convert=False))
        self.assertIsNone(to_video)
        self.assertEqual(sync["estado"], "sin sincronía")


class NetworkPanelTest(unittest.TestCase):
    """V3 y V4: cada sección HTTP de la traza con sus tiempos y su request y su response (cero huérfanos); lo capturado
    fuera de la traza va aparte."""

    def panel(self, records):
        events = {"fases": FASES, "duracion": 5.0}
        return perf.network_panel(TRAZA, lambda ns: ns / 1e9 - 100.0, records, events)

    def test_cada_seccion_http_tiene_su_request_y_su_response(self):
        records = {"0001": record("0001", 101_310 * MS, "page=1"), "0002": record("0002", 102_002 * MS, "page=2"),
                   "0003": record("0003", 99_000 * MS, "precarga=1", section="HTTP GET config")}
        calls, summary = self.panel(records)
        self.assertEqual(summary["secciones"], 2)
        self.assertEqual(summary["con_captura"], 2)  # cero huérfanos
        self.assertEqual(summary["sin_captura"], 0)
        first, second = [call for call in calls if not call.get("fuera_traza")]
        self.assertEqual((first["id"], first["inicio"], first["dur"]), ("0001", 1.3, 400.0))
        self.assertEqual((first["cola"], first["con"], first["ttfb"], first["desc"]), (20.0, 180.0, 150.0, 50.0))
        self.assertEqual(first["url"], "https://api.ejemplo.test/v1/items/42?page=1")  # la ruta completa, con la query
        self.assertEqual(first["ruta"], "/v1/items/42?page=1")
        self.assertEqual((first["codigo"], first["bytes"], first["tramo"]), (200, 2048, "Medición · Lista"))
        self.assertEqual(first["req"]["headers"][0], ["Authorization", "Bearer token-de-prueba"])  # tal cual
        self.assertEqual((second["id"], second["con"]), ("0002", 0))  # reusó la conexión
        outside = [call for call in calls if call.get("fuera_traza")]
        self.assertEqual([call["id"] for call in outside], ["0003"])
        self.assertEqual(summary["fuera_traza"], 1)

    def test_sin_captura_salen_los_tiempos_de_la_traza(self):
        calls, summary = self.panel({})
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0]["url"])
        self.assertEqual(calls[0]["ruta"], "items/{id} #1a2b")
        self.assertFalse(summary["captura"])

    def test_un_cuerpo_grande_va_recortado_y_un_binario_no_va_en_linea(self):
        big = record("0001", 101_310 * MS, "page=1", body="x" * (perf.BODY_EMBED_MAX + 10))
        big["response"]["cuerpo_archivo"] = None
        calls, _ = self.panel({"0001": big})
        response = calls[0]["res"]
        self.assertTrue(response["truncado"])
        self.assertEqual(len(response["cuerpo"]), perf.BODY_EMBED_MAX)
        binary = record("0001", 101_310 * MS, "page=1", body=None)
        binary["response"].update(cuerpo=None, cuerpo_archivo="0001-response.bin")
        calls, _ = self.panel({"0001": binary})
        self.assertEqual(calls[0]["res"]["binario"], "red/prueba/0001-response.bin")
        self.assertNotIn("cuerpo", calls[0]["res"])

    def test_los_toques_y_las_marcas_en_el_reloj_del_video(self):
        events = perf.trace_events(TRAZA, lambda ns: ns / 1e9 - 100.0, 5.0)
        self.assertEqual(events, [{"t": 1.2, "tipo": "TAP", "nombre": ""}, {"t": 1.5, "tipo": "MARK", "nombre": "lista"}])

    def test_la_pagina_lleva_el_aviso_y_el_panel(self):
        calls, summary = self.panel({"0001": record("0001", 101_310 * MS, "page=1")})
        events = {"version": 2, "flujo": "lista", "grabador": "screenrecord", "duracion": 5.0, "fases": FASES,
                  "marcas": [], "tramos_video": [{"archivo": "video/lista/parte1.mp4", "inicio": 0.0}],
                  "red": calls, "red_resumen": summary, "sincronia": {"estado": "validada", "desfase_ms": 38}}
        page = perf.video_page_html(events, "demo", "2026-11-23")
        self.assertIn("Contiene credenciales y datos reales de la prueba: no compartir fuera del equipo.", page)
        self.assertIn('id="panel-red"', page)
        self.assertEqual(perf.embedded_events(page)["red"][0]["url"], "https://api.ejemplo.test/v1/items/42?page=1")


def generated_capture(root):
    write(root / "app" / "src" / "perf" / "kotlin" / "com" / "ejemplo" / "TestNetworkCapture.kt",
          "// Generated by hb-performance (perf.py instrumentar); `instrumentar --actualizar` overwrites this file.\n")


class TestRunCaptureTest(CaptureCase):
    """V1 y V4 de punta a punta, con adb simulado: la prueba activa la captura antes de 'preparar', la apaga, baja
    red/prueba/ y arma el panel; una fase medida nunca la activa (y sus métricas no cambian con el interceptor
    presente)."""

    def setUp(self):
        super().setUp()
        generated_capture(self.dir)
        red = self.dir / "fake-red"
        records = {"0001": record("0001", 1 * MS, "page=1"), "0002": record("0002", 101 * MS, "page=2")}
        for key, pair in records.items():
            for side in ("request", "response"):
                pair[side]["seccion"] = "HTTP GET items/{id}"
                write(red / ("%s-%s.json" % (key, side)), json.dumps(pair[side]))
        self.env.update(FAKE_RED_DIR=str(red), FAKE_UPTIME="0.00")
        self.tp_outputs(GOOD)

    def adb_shell(self):
        return [" ".join(json.loads(line)[3:]) for line in (self.dir / "adb.log").read_text(encoding="utf-8").splitlines()
                if json.loads(line)[:1] == ["-s"]]

    def test_la_prueba_captura_y_arma_el_panel(self):
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba")
        self.assertIn("Red de la prueba: guardo el request y el response completos", out)
        commands = self.adb_shell()
        remote = perf.net_remote(PKG)
        on = next(i for i, c in enumerate(commands) if c.startswith("mkdir -p %s" % remote))
        off = commands.index("rm -f %s/ACTIVA" % remote)
        trace = next(i for i, c in enumerate(commands) if c.startswith("perfetto"))
        self.assertLess(on, trace)
        self.assertLess(trace, off)
        folder = self.plan.parent
        self.assertTrue((folder / "red" / "prueba" / "0001-request.json").is_file())
        events = json.loads((folder / "video" / "home" / "eventos.json").read_text(encoding="utf-8"))
        self.assertEqual(events["red_resumen"]["secciones"], 2)
        self.assertEqual(events["red_resumen"]["con_captura"], 2)  # cero huérfanos
        self.assertTrue((folder / "video" / "home" / perf.SYNC_FILE).is_file())
        page = (folder / "prueba-home.html").read_text(encoding="utf-8")
        self.assertIn("Bearer token-de-prueba", page)  # tal cual, sin ofuscar

    def test_una_fase_medida_nunca_activa_la_captura(self):
        csv_with = self.capture_phase()
        commands = self.adb_shell()
        self.assertIn("rm -f %s/ACTIVA" % perf.net_remote(PKG), commands)  # por si una prueba la dejó
        self.assertFalse(any("touch" in c and "ACTIVA" in c for c in commands))
        self.assertFalse((self.plan.parent / "red").exists())
        # A/A simulado: sin el interceptor en el proyecto, las mismas corridas dan las mismas métricas
        (self.dir / "app").rename(self.dir / "sin-captura")
        (self.plan.parent / "metricas.csv").unlink()
        self.assertEqual(self.capture_phase(), csv_with)

    def capture_phase(self):
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "2",
                "--calentamiento", "0", "--sin-compilar", "--rehacer")
        with (self.plan.parent / "metricas.csv").open(encoding="utf-8") as handle:
            return sorted((row.split(",")[2], row.split(",")[4]) for row in handle.read().splitlines()[1:])


class ReportsLinkTest(PerfBase):
    """V1 y V6: el reporte dev enlaza la página de la prueba (no el .mp4 suelto); los de gerencia no la incluyen ni la
    enlazan, ni nada de la red de la prueba."""

    def test_dev_enlaza_la_pagina_y_gerencia_nada(self):
        folder = self.dir / "inv"
        write(folder / "plan.json", json.dumps({"paquete": PKG, "principales": ["lista_ms"],
                                                "flujos": {"lista": {"recorrido": "true"}}, "mejoras": []}))
        write(folder / "metricas.csv", HEADER + rows("antes", "lista", "lista_ms", [900] * 5))
        write(folder / "estado.md", "# Rendimiento · Lista\n\n## Ficha\n\n| Campo | Valor |\n| --- | --- |\n| Síntoma | La "
                                    "lista tarda |\n\n## Consumo\n\n| Sesión | Modelo | Costo o tokens | Pasos |\n| --- "
                                    "| --- | --- | --- |\n")
        write(folder / "prueba-lista.html", "<p>visor</p>")
        write(folder / "prueba-lista.mp4", "x")
        write(folder / "video" / "lista" / "eventos.json", json.dumps({"unido": {"archivo": "prueba-lista.mp4",
                                                                                "rotulado": True}}))
        write(folder / "red" / "prueba" / "0001-request.json", json.dumps(record("0001", 1, "a=1")["request"]))
        self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
        dev = (folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        self.assertIn('href="prueba-lista.html"', dev)
        self.assertNotIn('href="prueba-lista.mp4"', dev)
        for name in ("reporte-inicial-gerencia.html", "reporte-inicial-gerencia.md"):
            text = (folder / name).read_text(encoding="utf-8")
            for needle in ("prueba-lista", "red/prueba", "Bearer", "credenciales", "video"):
                self.assertNotIn(needle, text, name)


if __name__ == "__main__":
    unittest.main()
