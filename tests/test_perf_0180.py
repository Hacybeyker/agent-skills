"""Tests de hb-performance 0.18.0: rótulos del video en tres capas (V), `siguiente` con el estado de ahora (S),
`decidir` con rastro y vuelta atrás (D), `archivar` y la salida de `pausar` (P) y la línea "Secciones propias" (O). Los
datos son inventados."""
import argparse
import contextlib
import io
import json
import os
import re
import shlex
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, write
from test_perf import AGENT_ENV, perf
from test_perf_0150 import TriageBase, commands_in
from test_perf_0160 import CaptureBase, ReportFixtureBase

SKILL = ROOT / "skills" / "hb-performance"
SCRIPT = SKILL / "scripts" / "perf.py"
MS = 1000000
PARTS = ["video/pedidos/parte1.mp4", "video/pedidos/parte2.mp4"]

# Una traza inventada: la marca `pedidos_vuelta` sale dos veces y el plan usa la última (regla `cual`).
ROWS = [("proceso", 0, 0, 0, "com.example.app"), ("limites", 0, 9000 * MS, 0, "")] + \
    [("frame", 1500 * MS + i * 20 * MS, 16 * MS, 0, "None") for i in range(40)] + \
    [("frame", 2600 * MS, 48 * MS, 0, "App Deadline Missed"), ("frame", 7000 * MS, 40 * MS, 0, "App Deadline Missed"),
     ("hilo", 1600 * MS, 90 * MS, 0, "Choreographer#doFrame"), ("hilo", 7100 * MS, 120 * MS, 0, "inflate"),
     ("seccion", 1500 * MS, 1 * MS, 0, "SCREEN Pedidos onCreate"),
     ("seccion", 1700 * MS, 600 * MS, 0, "HTTP GET pedidos"),
     ("seccion", 2400 * MS, 1 * MS, 0, "MARK pedidos_vuelta"),
     ("seccion", 3000 * MS, 1 * MS, 0, "MARK pedidos_visible"),
     ("seccion", 4200 * MS, 1 * MS, 0, "MARK detalle_tap"),
     ("seccion", 4300 * MS, 900 * MS, 0, "HTTP GET pedidos/{id}"),
     ("seccion", 5600 * MS, 1 * MS, 0, "MARK detalle_visible"),
     ("seccion", 6400 * MS, 1 * MS, 0, "MARK volver_tap"),
     ("seccion", 7600 * MS, 1 * MS, 0, "MARK pedidos_vuelta")]
FLOW = {"titulo": "Pedidos", "preparar": "true",
        "ventana": {"desde": {"marca": "SCREEN Pedidos onCreate"}, "hasta": {"marca": "MARK pedidos_vuelta"}},
        "metricas_usuario": [{"nombre": "lista_visible_ms", "desde": {"marca": "SCREEN Pedidos onCreate"},
                              "hasta": {"marca": "MARK pedidos_visible"}}],
        "segmentos": [
            {"nombre": "cargar_pedidos", "titulo": "Cargar la lista de pedidos",
             "desde": {"marca": "SCREEN Pedidos onCreate"}, "hasta": {"marca": "MARK pedidos_visible"}},
            {"nombre": "abrir_detalle", "titulo": "Abrir el detalle", "desde": {"marca": "MARK detalle_tap"},
             "hasta": {"marca": "MARK detalle_visible"}},
            {"nombre": "volver", "titulo": "Volver a la lista", "desde": {"marca": "MARK volver_tap"},
             "hasta": {"marca": "MARK pedidos_vuelta", "cual": "ultima"}}]}
# La traza empieza a los 1003,0 s del reloj de la computadora; el video, a los 1000,0.
CLOCK_OUTSIDE = {"preparar_inicio": 1000.4, "preparar_fin": 1002.8, "traza": 1003.0, "recorrido_inicio": 1004.5,
                 "recorrido_fin": 1011.2}
CLOCK_INSIDE = {"traza": 1000.6, "preparar_inicio": 1002.1, "preparar_fin": 1004.4, "recorrido_inicio": 1004.5,
                "recorrido_fin": 1011.2}
# Lo que trace_metrics daba para ROWS y FLOW en 0.17.0 (origin/main): las mediciones no cambian.
GOLDEN = [
    ["ventana_ms", 6101.0, "ms", "info"], ["frames", 42, "frames", "info"], ["jank_app_pct", 4.7619, "%", "app"],
    ["jank_total_pct", 4.7619, "%", "info"], ["frame_p50_ms", 16.0, "ms", "app"], ["frame_p90_ms", 16.0, "ms", "app"],
    ["frame_p99_ms", 48.0, "ms", "app"], ["hilo_slices_sobre_presupuesto", 2, "slices", "app"],
    ["hilo_slices_100ms", 1, "slices", "app"], ["hilo_max_ms", 120.0, "ms", "app"],
    ["inflate_cantidad", 1, "inflates", "app"], ["inflate_ms", 120.0, "ms", "app"], ["red_llamadas", 2, "llamadas", "app"],
    ["red_solapadas", 0, "llamadas", "app"], ["red_repetidas_2s", 0, "llamadas", "app"],
    ["red GET pedidos llamadas", 1, "llamadas", "app"], ["red GET pedidos ms", 600.0, "ms", "e2e"],
    ["red GET pedidos/{id} llamadas", 1, "llamadas", "app"], ["red GET pedidos/{id} ms", 900.0, "ms", "e2e"],
    ["lista_visible_ms", 1501.0, "ms", "e2e"], ["cargar_pedidos hilo_max_ms", 90.0, "ms", "app"],
    ["cargar_pedidos frames", 41, "frames", "info"], ["cargar_pedidos jank_app_pct", 2.439, "%", "app"],
    ["cargar_pedidos frame_p90_ms", 16.0, "ms", "app"], ["abrir_detalle hilo_max_ms", 0.0, "ms", "app"],
    ["volver hilo_max_ms", 120.0, "ms", "app"], ["volver frames", 1, "frames", "info"],
    ["volver jank_app_pct", 100.0, "%", "app"], ["volver frame_p90_ms", 40.0, "ms", "app"],
    ["cargar_pedidos red_llamadas", 1, "llamadas", "app"], ["cargar_pedidos red_ms", 600.0, "ms", "e2e"],
    ["cargar_pedidos red_repetidas_2s", 0, "llamadas", "app"], ["cargar_pedidos red_solapadas", 0, "llamadas", "app"],
    ["abrir_detalle red_llamadas", 1, "llamadas", "app"], ["abrir_detalle red_ms", 900.0, "ms", "e2e"],
    ["abrir_detalle red_repetidas_2s", 0, "llamadas", "app"], ["abrir_detalle red_solapadas", 0, "llamadas", "app"],
    ["volver red_llamadas", 0, "llamadas", "app"], ["volver red_repetidas_2s", 0, "llamadas", "app"],
    ["volver red_solapadas", 0, "llamadas", "app"], ["red GET pedidos repetidas_2s", 0, "llamadas", "app"],
    ["red GET pedidos solapadas", 0, "llamadas", "app"], ["red GET pedidos/{id} repetidas_2s", 0, "llamadas", "app"],
    ["red GET pedidos/{id} solapadas", 0, "llamadas", "app"],
    ["cargar_pedidos red GET pedidos llamadas", 1, "llamadas", "info"],
    ["abrir_detalle red GET pedidos/{id} llamadas", 1, "llamadas", "info"],
    ["red GET pedidos inicio_ms", 200.0, "ms", "info"], ["red GET pedidos fin_ms", 800.0, "ms", "info"],
    ["red GET pedidos/{id} inicio_ms", 2800.0, "ms", "info"], ["red GET pedidos/{id} fin_ms", 3700.0, "ms", "info"],
    ["red_en_curso_ms", 1500.0, "ms", "info"], ["cargar_pedidos inicio_ms", 0.0, "ms", "info"],
    ["cargar_pedidos fin_ms", 1501.0, "ms", "info"], ["abrir_detalle inicio_ms", 2700.0, "ms", "info"],
    ["abrir_detalle fin_ms", 4101.0, "ms", "info"], ["volver inicio_ms", 4900.0, "ms", "info"],
    ["volver fin_ms", 6101.0, "ms", "info"], ["cargar_pedidos red GET pedidos repetidas", 0, "llamadas", "app"],
    ["abrir_detalle red GET pedidos/{id} repetidas", 0, "llamadas", "app"]]


def demo_events(clock=None, flow=None, rows=None):
    """Los eventos de una prueba inventada: la traza de ROWS con el plan de FLOW, en dos tramos de video."""
    spans, marks = perf.video_trace_events(rows or ROWS, flow or FLOW, "pedidos", lambda ns: 1003.0 + ns / 1e9)
    return perf.video_events("pedidos", "screenrecord", PARTS, [1000.0, 1006.0], 1012.0, clock or CLOCK_OUTSIDE, spans,
                             marks, {"marcas": "ok", "detalle": ""}, "Pedidos")


def as_version_1(events):
    """Los mismos eventos como los dejaba 0.17.0: versión 1, sin leyenda, sin el inicio de la traza, las marcas sin
    `papel` ni `usada` y los rótulos de entonces."""
    old = json.loads(json.dumps(events))
    old["version"] = 1
    for key in ("leyenda", "traza", "papeles"):
        old.pop(key, None)
    old["marcas"] = [{"t": mark["t"], "nombre": mark["nombre"]} for mark in old["marcas"]]
    names = {perf.VIDEO_PREP: perf.VIDEO_OLD_PREP, perf.VIDEO_PREP_TRACED: perf.VIDEO_OLD_PREP,
             perf.VIDEO_BETWEEN: perf.VIDEO_OLD_BETWEEN}
    for phase in old["fases"]:
        phase["rotulo"] = names.get(phase["rotulo"], phase["rotulo"])
    return old


# ── Las mediciones no cambian ────────────────────────────────────────────────

class MeasurementsUnchangedTest(unittest.TestCase):
    def test_las_metricas_de_una_traza_son_las_de_0170(self):
        metrics, invalid, _ = perf.trace_metrics(ROWS, 60, FLOW, set(), 34)
        self.assertIsNone(invalid)
        self.assertEqual([[m[0], round(m[1], 4), m[2], m[3]] for m in metrics], GOLDEN)

    def test_las_fases_de_0170_se_completan_sin_repetirlas(self):
        self.assertEqual(perf.VERSION, "0.18.0")
        for version in ("0.16.0", "0.17.0", perf.VERSION):
            self.assertTrue(perf.same_capture(version), version)

    def test_el_video_no_cambia_que_ocurrencia_usa_cada_tramo(self):
        markers = perf.video_markers(ROWS, FLOW)
        before = [bounds for _, bounds in perf.segment_windows(markers, FLOW["segmentos"])]
        perf.video_mark_roles(markers, FLOW, "pedidos")
        self.assertEqual([bounds for _, bounds in perf.segment_windows(markers, FLOW["segmentos"])], before)
        self.assertEqual(before[2], (6400 * MS, 7601 * MS))  # la última `pedidos_vuelta`, no la primera


# ── V1 · Los textos de las fases dicen si la traza graba y si se mide ────────

class PhaseLabelsTest(unittest.TestCase):
    def labels(self, events):
        return [(phase["desde"], phase["rotulo"], phase["tipo"]) for phase in events["fases"]]

    def test_preparacion_fuera_de_la_traza(self):
        self.assertEqual(self.labels(demo_events()), [
            (0.0, "Preparación · sin traza, no se mide", "prep"), (3.0, "Sin medir · traza grabando", "rec"),
            (4.5, "Medición · Cargar la lista de pedidos", "med"), (6.0, "Sin medir · traza grabando", "rec"),
            (7.2, "Medición · Abrir el detalle", "med"), (8.6, "Sin medir · traza grabando", "rec"),
            (9.4, "Medición · Volver a la lista", "med"), (10.6, "Sin medir · traza grabando", "rec"),
            (11.2, "Fin de la prueba", "fin")])

    def test_preparacion_dentro_de_la_traza(self):
        labels = self.labels(demo_events(CLOCK_INSIDE))
        self.assertEqual(labels[:3], [(0.0, "Preparación · sin traza, no se mide", "prep"),
                                      (0.6, "Preparación · traza grabando, no se mide", "prep"),
                                      (4.5, "Medición · Cargar la lista de pedidos", "med")])

    def test_ninguna_fase_dice_recorrido_sola(self):
        for clock in (CLOCK_OUTSIDE, CLOCK_INSIDE, {"preparar_inicio": 1000.4, "preparar_fin": 1002.8}):
            events = demo_events(clock)
            for phase in events["fases"]:
                self.assertNotIn("Recorrido", phase["rotulo"])
                self.assertNotIn("entre tramos", phase["rotulo"])
                said = phase["rotulo"].startswith(("Medición · ", "Fin de la prueba")) or (
                    "traza" in phase["rotulo"] and ("no se mide" in phase["rotulo"] or "Sin medir" in phase["rotulo"]))
                self.assertTrue(said, phase["rotulo"])  # cada parte dice si la traza graba y si se mide
            self.assertEqual(events["fases"][0]["desde"], 0.0)
            self.assertEqual(events["fases"][-1]["hasta"], events["duracion"])
            for before, after in zip(events["fases"], events["fases"][1:]):
                self.assertEqual(before["hasta"], after["desde"])

    def test_sin_la_hora_de_la_traza_la_preparacion_va_sin_traza(self):
        phases = perf.video_phases(10.0, (4.0, 9.0), [("A", 5.0, 6.0)], "Pedidos")
        self.assertEqual([(f["desde"], f["rotulo"]) for f in phases], [
            (0.0, "Preparación · sin traza, no se mide"), (4.0, "Sin medir · traza grabando"), (5.0, "Medición · A"),
            (6.0, "Sin medir · traza grabando"), (9.0, "Fin de la prueba")])

    def test_preparar_que_falla_dentro_de_la_traza(self):
        events = demo_events({"traza": 1000.6, "preparar_inicio": 1002.1, "preparar_fin": 1004.4})
        self.assertEqual([(f["desde"], f["rotulo"]) for f in events["fases"]], [
            (0.0, "Preparación · sin traza, no se mide"), (0.6, "Preparación · traza grabando, no se mide")])

    def test_los_rotulos_largos_entran_en_el_ancho(self):
        text, size = perf.fit_text("Preparación · traza grabando, no se mide", 28, 16, 0.62)
        self.assertEqual(text, "Preparación · traza grabando, no se mide")
        self.assertLess(size, 28)
        self.assertLessEqual(len(text) * size * 0.62, perf.VIDEO_BASE_W - 40)
        text, size = perf.fit_text("Medición · " + "un tramo con un título muy largo " * 4, 28, 16, 0.62)
        self.assertEqual(size, 16)
        self.assertTrue(text.endswith("…"))
        self.assertLessEqual(len(text) * size * 0.62, perf.VIDEO_BASE_W - 40)
        self.assertEqual(perf.fit_text("Fin de la prueba", 28, 16, 0.62), ("Fin de la prueba", 28))
        self.assertEqual(perf.font_widths(("/x/Arial.ttf", "/x/Arial Bold.ttf")), (0.55, 0.5))
        self.assertGreater(perf.font_widths(("/x/DejaVuSans.ttf", "/x/DejaVuSans-Bold.ttf"))[0], 0.62)
        self.assertEqual(perf.font_widths(None), perf.FONT_WIDTHS)


# ── V2 · La leyenda fija, con las tres capas ─────────────────────────────────

class LegendTest(unittest.TestCase):
    def test_nombra_las_tres_capas(self):
        legend = demo_events()["leyenda"]
        self.assertEqual(legend, ["Video: toda la prueba · Traza: desde el fin de la preparación",
                                  "Métrica: solo cuenta lo marcado Medición"])
        for layer in ("Video:", "Traza:", "Métrica:"):
            self.assertIn(layer, " ".join(legend))

    def test_es_coherente_con_la_preparacion_dentro_de_la_traza(self):
        self.assertEqual(demo_events(CLOCK_INSIDE)["leyenda"][0], "Video: toda la prueba · Traza: desde la preparación")
        self.assertEqual(perf.video_legend(None, False)[0], "Video: toda la prueba · Traza: no hay en esta prueba")

    def test_va_en_la_banda_de_abajo_del_video(self):
        events = demo_events()
        width, height = 1080, 2340
        graph, texts = perf.video_filter(events, width, height)
        head, foot = perf.even(perf.VIDEO_HEAD * 2), perf.even(perf.VIDEO_FOOT * 2)
        self.assertEqual([texts["leyenda-1.txt"], texts["leyenda-2.txt"]], events["leyenda"])
        for name in ("leyenda-1.txt", "leyenda-2.txt"):
            draw = re.search(r"drawtext=[^,;]*textfile=%s[^,;]*" % re.escape(name), graph).group(0)
            self.assertNotIn("enable=", draw)  # siempre a la vista
            y = int(re.search(r":y=(\d+)", draw).group(1))
            self.assertGreaterEqual(y, head + height)
            self.assertLess(y, head + height + foot)
        # nada cae sobre la imagen del teléfono
        for kind, y in re.findall(r"(drawbox|drawtext)=[^,;]*?:y=(\d+)", graph):
            self.assertTrue(int(y) < head or int(y) >= head + height, "%s en y=%s cae sobre la imagen" % (kind, y))

    def test_va_igual_en_el_visor(self):
        events = demo_events(CLOCK_INSIDE)
        page = perf.video_page_html(events, "App de pedidos", "2026-11-20")
        self.assertEqual(perf.embedded_events(page)["leyenda"], events["leyenda"])
        self.assertIn('id="leyenda"', page)
        self.assertIn("EV.leyenda", page)
        for layer in ("<strong>Video:</strong>", "<strong>Traza:</strong>", "<strong>Métrica:</strong>"):
            self.assertIn(layer, page)

    def test_unos_eventos_de_0170_usan_la_leyenda_por_defecto(self):
        self.assertEqual(perf.video_legend_lines(as_version_1(demo_events())), perf.video_legend(0.0, False))


# ── V3 · Las marcas son instantes, con su papel ──────────────────────────────

class MarkRolesTest(unittest.TestCase):
    def marks(self, **kwargs):
        return [(m["t"], m["nombre"], m["papel"], m["usada"]) for m in demo_events(**kwargs)["marcas"]]

    def test_papel_y_usada_con_una_marca_que_sale_dos_veces(self):
        self.assertEqual(self.marks(), [
            (4.5, "SCREEN Pedidos onCreate", "inicio de Cargar la lista de pedidos", True),
            (5.4, "MARK pedidos_vuelta", "", False),  # la primera: el plan usa la última
            (6.0, "MARK pedidos_visible", "fin de Cargar la lista de pedidos", True),
            (7.2, "MARK detalle_tap", "inicio de Abrir el detalle", True),
            (8.6, "MARK detalle_visible", "fin de Abrir el detalle", True),
            (9.4, "MARK volver_tap", "inicio de Volver a la lista", True),
            (10.6, "MARK pedidos_vuelta", "fin de Volver a la lista", True)])

    def test_una_marca_que_cierra_un_tramo_y_abre_otro(self):
        flow = dict(FLOW, segmentos=[
            {"nombre": "cargar_pedidos", "titulo": "Cargar la lista", "desde": {"marca": "SCREEN Pedidos onCreate"},
             "hasta": {"marca": "MARK detalle_tap", "punto": "inicio"}},
            {"nombre": "abrir_detalle", "titulo": "Abrir el detalle", "desde": {"marca": "MARK detalle_tap"},
             "hasta": {"marca": "MARK detalle_visible"}}])
        both = [mark for mark in self.marks(flow=flow) if mark[1] == "MARK detalle_tap"]
        self.assertEqual(both, [(7.2, "MARK detalle_tap", "fin de Cargar la lista · inicio de Abrir el detalle", True)])

    def test_la_regla_cual_decide_la_ocurrencia_usada(self):
        first = dict(FLOW, ventana=None, metricas_usuario=[], segmentos=[
            {"nombre": "volver", "titulo": "Volver", "desde": {"marca": "SCREEN Pedidos onCreate"},
             "hasta": {"marca": "MARK pedidos_vuelta", "cual": "primera"}}])
        marks = [mark for mark in self.marks(flow=first) if mark[1] == "MARK pedidos_vuelta"]
        self.assertEqual(marks, [(5.4, "MARK pedidos_vuelta", "fin de Volver", True),
                                 (10.6, "MARK pedidos_vuelta", "", False)])

    def test_la_marca_de_una_metrica_de_usuario_cuenta_como_usada(self):
        flow = {"metricas_usuario": [{"nombre": "detalle_ms", "desde": {"marca": "MARK detalle_tap"},
                                      "hasta": {"marca": "MARK detalle_visible"}}]}
        self.assertEqual(self.marks(flow=flow), [(7.2, "MARK detalle_tap", "", True),
                                                 (8.6, "MARK detalle_visible", "", True)])

    def test_sin_tramos_el_papel_es_el_de_la_ventana_del_flujo(self):
        flow = {"titulo": "Pedidos", "ventana": FLOW["ventana"]}
        self.assertEqual(self.marks(flow=flow), [(4.5, "SCREEN Pedidos onCreate", "inicio de Pedidos", True),
                                                 (5.4, "MARK pedidos_vuelta", "", False),
                                                 (10.6, "MARK pedidos_vuelta", "fin de Pedidos", True)])

    def test_la_version_del_formato_es_2(self):
        events = demo_events()
        self.assertEqual(events["version"], 2)
        self.assertEqual(events["traza"], 3.0)
        self.assertFalse(perf.old_events(events))
        self.assertTrue(perf.old_events(as_version_1(events)))
        self.assertTrue(perf.old_events({"fases": []}))  # sin versión: de 0.17.0


class MarkChipsTest(unittest.TestCase):
    def test_el_chip_dura_un_segundo_y_medio_desde_su_instante(self):
        self.assertEqual(perf.VIDEO_MARK_S, 1.5)
        windows = perf.mark_windows({"duracion": 20.0, "marcas": [{"t": 1.0, "nombre": "a", "usada": True},
                                                                  {"t": 9.0, "nombre": "b", "usada": True}]})
        self.assertEqual([(start, end) for start, end, _ in windows], [(1.0, 2.5), (9.0, 10.5)])  # no hasta la siguiente

    def test_una_no_usada_nunca_tapa_a_una_usada(self):
        marks = [{"t": 1.0, "nombre": "usada", "usada": True}, {"t": 1.4, "nombre": "suelta", "usada": False},
                 {"t": 6.0, "nombre": "sola", "usada": False}, {"t": 8.0, "nombre": "otra", "usada": True},
                 {"t": 7.5, "nombre": "antes", "usada": False}]
        marks.sort(key=lambda mark: mark["t"])
        windows = [(round(start, 2), round(end, 2), mark["nombre"])
                   for start, end, mark in perf.mark_windows({"duracion": 20.0, "marcas": marks})]
        self.assertEqual(windows, [(1.0, 2.5, "usada"), (2.5, 2.9, "suelta"), (6.0, 7.5, "sola"), (7.5, 8.0, "antes"),
                                   (8.0, 9.5, "otra")])

    def test_la_que_no_cabe_queda_fuera_del_video(self):
        events = demo_events()
        shown = [mark["nombre"] for _, _, mark in perf.mark_windows(events) if not mark["usada"]]
        self.assertEqual(shown, [])  # entre dos usadas seguidas no le queda lugar; el visor la lista como "(no usada)"
        self.assertEqual(len([mark for mark in events["marcas"] if not mark["usada"]]), 1)

    def test_el_texto_del_chip(self):
        self.assertEqual(perf.chip_texts({"nombre": "MARK volver_tap", "papel": "inicio de Volver", "usada": True}),
                         ("● inicio de Volver", "MARK volver_tap"))
        self.assertEqual(perf.chip_texts({"nombre": "MARK pedidos_vuelta", "papel": "", "usada": False}),
                         ("MARK pedidos_vuelta (no usada)", ""))
        self.assertEqual(perf.chip_texts({"nombre": "MARK suelta", "papel": "", "usada": True}), ("● MARK suelta", ""))
        self.assertEqual(perf.chip_texts({"nombre": "MARK de_0170"}), ("● MARK de_0170", ""))  # sin los campos nuevos

    def test_en_el_video_la_no_usada_va_atenuada(self):
        events = {"duracion": 12.0, "fases": [{"desde": 0.0, "hasta": 12.0, "rotulo": "Medición · Pedidos", "tipo": "med"}],
                  "marcas": [{"t": 2.0, "nombre": "MARK volver_tap", "papel": "inicio de Volver a la lista", "usada": True},
                             {"t": 6.0, "nombre": "MARK pedidos_vuelta", "papel": "", "usada": False}]}
        graph, texts = perf.video_filter(events, 540, 1170)
        self.assertEqual(texts["rotulo-marca-1.txt"], "● inicio de Volver a la lista")
        self.assertEqual(texts["rotulo-marca-1-nombre.txt"], "MARK volver_tap")  # el nombre técnico, en letra menor
        self.assertEqual(texts["rotulo-marca-2.txt"], "MARK pedidos_vuelta (no usada)")
        self.assertNotIn("rotulo-marca-2-nombre.txt", texts)
        used = re.search(r"drawtext=[^,;]*textfile=rotulo-marca-1\.txt[^,;]*", graph).group(0)
        unused = re.search(r"drawtext=[^,;]*textfile=rotulo-marca-2\.txt[^,;]*", graph).group(0)
        small = re.search(r"drawtext=[^,;]*textfile=rotulo-marca-1-nombre\.txt[^,;]*", graph).group(0)
        self.assertIn("boxcolor=0xfff3d6", used)
        self.assertIn("textfile=rotulo-marca-1.txt:expansion=none:fontsize=21:fontcolor=0x9a6400:box=1:boxcolor=0xfff3d6:"
                      "boxborderw=6:x=20:y=84:enable='between(t,2,3.499)'", graph)  # un segundo y medio desde su instante
        self.assertNotIn("0xfff3d6", unused)
        self.assertIn("fontcolor=0x9ca2ad", unused)
        self.assertLess(int(re.search(r"fontsize=(\d+)", small).group(1)), int(re.search(r"fontsize=(\d+)", used).group(1)))

    def test_si_hay_demasiadas_quedan_fuera_primero_las_no_usadas(self):
        marks = [(1000.5 + i * 0.01, "MARK m%d" % i, "", i % 2 == 0) for i in range(200)]
        events = perf.video_events("pedidos", "screenrecord", PARTS, [1000.0, 1006.0], 1012.0, CLOCK_OUTSIDE, [], marks)
        self.assertEqual(len(events["marcas"]), perf.VIDEO_MARKS_MAX)
        self.assertEqual(len([mark for mark in events["marcas"] if mark["usada"]]), 100)
        self.assertIn("se muestran 150 marcas de 200 (quedaron fuera 50 que el plan no usa)", events["alineacion"]["detalle"])


class ViewerRolesTest(unittest.TestCase):
    def test_el_visor_lleva_los_campos_nuevos(self):
        events = demo_events()
        page = perf.video_page_html(events, "App de pedidos", "2026-11-20")
        embedded = perf.embedded_events(page)
        self.assertEqual(embedded, events)
        self.assertEqual(embedded["marcas"][1], {"t": 5.4, "nombre": "MARK pedidos_vuelta", "papel": "", "usada": False})
        self.assertIn("var MARK_S = %s," % perf.VIDEO_MARK_S, page)  # la misma duración del chip que en el video
        self.assertIn('var NO_USADA = "%s";' % perf.VIDEO_UNUSED, page)
        self.assertIn("<th>Papel</th>", page)
        self.assertIn(".marca.no span", page)  # la que el plan no usa, atenuada
        self.assertNotIn("Recorrido", page)
        self.assertNotIn("{{", page)
        self.assertNotRegex(page, r'(?:src|href)="(?:https?:)?//')

    def test_el_visor_lee_unos_eventos_de_0170(self):
        old = as_version_1(demo_events())
        page = perf.video_page_html(old, "App de pedidos", "2026-11-20")
        self.assertEqual(perf.embedded_events(page), old)
        self.assertIn("m.usada !== false", page)  # sin `usada`, la marca cuenta como usada
        self.assertIn("m.papel || m.nombre", page)  # sin `papel`, su nombre
        self.assertEqual(perf.events_problem(old), "")
        self.assertEqual(len(perf.mark_windows(old)), len(old["marcas"]))


# ── V4 · `video` rearma una prueba de 0.17.0 y `siguiente` lo ofrece ─────────

class UpgradeEventsTest(unittest.TestCase):
    def test_con_las_marcas_de_la_traza_quedan_papel_y_usada(self):
        events = demo_events()
        rebuilt = perf.old_marks_roles(as_version_1(events), ROWS, FLOW, "pedidos")
        self.assertEqual(rebuilt, events["marcas"])

    def test_una_traza_de_otra_corrida_no_sirve(self):
        other = [row if row[4] != "MARK detalle_tap" else ("seccion", 4900 * MS, 1 * MS, 0, "MARK detalle_tap")
                 for row in ROWS]
        self.assertIsNone(perf.old_marks_roles(as_version_1(demo_events()), other, FLOW, "pedidos"))
        self.assertEqual(perf.old_marks_roles({"marcas": []}, ROWS, FLOW, "pedidos"), [])

    def test_una_marca_de_borde_con_duracion_va_en_el_instante_de_su_papel(self):
        flow = {"segmentos": [{"nombre": "cargar_pedidos", "titulo": "Cargar la lista",
                               "desde": {"marca": "SCREEN Pedidos onCreate"}, "hasta": {"marca": "HTTP GET pedidos"}}]}
        events = demo_events(flow=flow)
        self.assertEqual([(m["t"], m["nombre"], m["papel"]) for m in events["marcas"]], [
            (4.5, "SCREEN Pedidos onCreate", "inicio de Cargar la lista"),
            (5.3, "HTTP GET pedidos", "fin de Cargar la lista")])  # cuando termina la llamada (4,7 + 0,6 s), no al empezar
        self.assertEqual([f["hasta"] for f in events["fases"] if f["rotulo"] == "Medición · Cargar la lista"], [5.3])
        old = as_version_1(events)
        old["marcas"][1]["t"] = 4.7  # 0.17.0 la ponía en el inicio de su sección
        self.assertEqual(perf.old_marks_roles(old, ROWS, flow, "pedidos"), events["marcas"])

    def test_los_de_esta_version_quedan_igual(self):
        events = demo_events()
        self.assertEqual(perf.upgrade_events(Path("/no/existe"), events, {}, FLOW, "pedidos"), (events, []))


# La traza de la capa falsa para la prueba de punta a punta: `lista_visible` sale dos veces y el tramo termina en la
# última. Las marcas van entre 1,5 y 1,9 s de la traza: caen dentro del video aunque la máquina tarde hasta 1,5 s en
# empezar a grabar (después de leer la hora del dispositivo), y antes de los 2 s de cola del video.
E2E_ROWS = '"tipo","ts","dur","prof","nombre"\n"proceso",0,0,0,"com.ejemplo.app"\n"limites",0,5000000000,0,""\n' + \
    "".join('"frame",%d,16000000,0,"None"\n' % (1500000000 + i * 20000000) for i in range(9)) + \
    '"hilo",1500000000,30000000,0,"Choreographer#doFrame"\n"seccion",1500000000,5,0,"SCREEN MainActivity onResume"\n' \
    '"seccion",1550000000,100000000,0,"HTTP GET items/{id}"\n"seccion",1700000000,5,0,"MARK lista_visible"\n' \
    '"seccion",1900000000,5,0,"MARK lista_visible"\n'
E2E_SEGMENTS = [{"nombre": "cargar_lista", "titulo": "Cargar la lista", "desde": {"marca": "SCREEN MainActivity*"},
                 "hasta": {"marca": "MARK lista_visible", "cual": "ultima"}}]


class VideoRunBase(CaptureBase):
    """Una corrida de prueba con la capa falsa de adb y su video; `make_old` deja sus eventos como los dejaba 0.17.0."""
    tail = 0

    def setUp(self):
        super().setUp()
        self.plan_with(flujo={"video_cola_s": self.tail, "segmentos": E2E_SEGMENTS})
        self.tp_outputs(E2E_ROWS)
        self.env["FAKE_DATE"] = "1700000000.000000000"
        self.env["FAKE_TP_POR_CONSULTA"] = json.dumps({"reloj": '"ts","clock_name","clock_value"\n0,"REALTIME",%d\n'
                                                                % (1700000000 * 10 ** 9)})
        self.out = self.ok("capturar", "--plan", self.plan, "--prueba")
        self.events_path = self.folder / "video" / "home" / "eventos.json"
        self.new = json.loads(self.events_path.read_text(encoding="utf-8"))

    def make_old(self):
        old = as_version_1(self.new)
        self.events_path.write_text(json.dumps(old), encoding="utf-8")
        return old

    def rebuilt(self):
        return json.loads(self.events_path.read_text(encoding="utf-8"))


class RebuildOldVideoTest(VideoRunBase):
    """De punta a punta: una prueba con una marca que sale dos veces, sus eventos pasados a 0.17.0, y `video`."""
    tail = 2  # el video sigue 2 s después del recorrido: las marcas de la traza caen dentro

    def test_video_rearma_una_prueba_de_0170_sin_repetirla(self):
        self.assertEqual(self.new["version"], 2)
        self.assertEqual(self.new["fases"][0]["rotulo"], "Preparación · sin traza, no se mide")
        self.assertEqual([(m["nombre"], m["papel"], m["usada"]) for m in self.new["marcas"]], [
            ("SCREEN MainActivity onResume", "inicio de Cargar la lista", True),
            ("MARK lista_visible", "", False),  # la primera: el tramo termina en la última
            ("MARK lista_visible", "fin de Cargar la lista", True)])
        self.assertEqual(self.new["leyenda"][1], "Métrica: solo cuenta lo marcado Medición")
        self.assertIn("solo cuenta lo marcado «Medición»", self.out)
        self.assertNotIn("es de hb-performance 0.17.0", self.ok("siguiente", "--carpeta", self.folder))
        # los mismos eventos, como los dejaba 0.17.0
        self.make_old()
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("El video de la prueba de home es de hb-performance 0.17.0", out)
        command = next(line for line in out.splitlines() if "video --carpeta" in line)
        self.assertRegex(command, r"`cd \S+ && python3 -I \S+perf\.py video --carpeta inv --flujo home`")
        log_before = (self.dir / "adb.log").read_text(encoding="utf-8")
        out = self.ok("video", "--carpeta", self.folder)
        self.assertEqual((self.dir / "adb.log").read_text(encoding="utf-8"), log_before)  # sin tocar el dispositivo
        self.assertIn("era de una prueba de hb-performance 0.17.0", out)
        self.assertNotIn("quedan sin su papel", out)
        rebuilt = self.rebuilt()
        self.assertEqual(rebuilt["version"], 2)
        self.assertEqual(rebuilt["marcas"], self.new["marcas"])
        self.assertNotIn("Recorrido", json.dumps(rebuilt, ensure_ascii=False))
        self.assertEqual(rebuilt["leyenda"], perf.video_legend(0.0, False))
        page = (self.folder / "prueba-home.html").read_text(encoding="utf-8")
        self.assertEqual(perf.embedded_events(page), rebuilt)
        self.assertLess(out.index("era de una prueba"), out.rindex("Siguiente"))  # el paso siguiente va al final
        self.assertNotIn("es de hb-performance 0.17.0", self.ok("siguiente", "--carpeta", self.folder))


    def test_si_la_traza_no_se_pudo_leer_otro_video_lo_reintenta(self):
        self.make_old()
        self.env["FAKE_TP_FALLA"] = "metricas"  # trace_processor falla esta vez
        out = self.ok("video", "--carpeta", self.folder)
        self.assertIn("no pude leer", out)
        self.assertIn("La traza sigue ahí", out)
        self.assertNotIn("Para tenerlos, repite", out)
        self.assertEqual(self.rebuilt()["papeles"], "traza sin leer")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("a sus marcas les falta el papel", out)  # `siguiente` lo sigue ofreciendo
        self.assertLess(out.index("1. "), out.index("a sus marcas les falta el papel"))  # después de los pasos
        del self.env["FAKE_TP_FALLA"]
        out = self.ok("video", "--carpeta", self.folder)
        self.assertNotIn("quedan sin su papel", out)
        self.assertIn("ya tienen su papel", out)
        rebuilt = self.rebuilt()
        self.assertNotIn("papeles", rebuilt)
        self.assertEqual(rebuilt["marcas"], self.new["marcas"])
        self.assertNotIn("es de hb-performance 0.17.0", self.ok("siguiente", "--carpeta", self.folder))


class RebuildWithoutTraceTest(VideoRunBase):
    def test_sin_la_traza_sale_con_los_rotulos_y_lo_dice(self):
        old = self.make_old()
        old["marcas"] = [{"t": 0.1, "nombre": "MARK lista_visible"}]  # una marca dentro del video, sin su papel
        self.events_path.write_text(json.dumps(old), encoding="utf-8")
        for trace in (self.folder / "prueba").glob("*.perfetto-trace*"):
            trace.unlink()
        out = self.ok("video", "--carpeta", self.folder)
        self.assertIn("Las marcas quedan sin su papel", out)
        self.assertIn("no está la traza de esa prueba", out)
        self.assertIn("--prueba", out)  # el paso para tenerlos
        rebuilt = self.rebuilt()
        self.assertEqual((rebuilt["version"], rebuilt["papeles"]), (2, "sin traza"))
        self.assertNotIn("es de hb-performance 0.17.0", self.ok("siguiente", "--carpeta", self.folder))  # no hay con qué
        self.assertEqual(rebuilt["fases"][0]["rotulo"], "Preparación · sin traza, no se mide")
        self.assertEqual(rebuilt["leyenda"], perf.video_legend(0.0, False))
        self.assertEqual(rebuilt["marcas"], [{"t": 0.1, "nombre": "MARK lista_visible"}])
        self.assertIn("Siguiente", out)

    def test_preparar_dentro_de_la_traza_en_una_prueba_de_0170(self):
        old = self.make_old()
        self.plan_with(flujo={"traza_desde_preparar": True, "preparar": "true"})
        self.ok("video", "--carpeta", self.folder)
        rebuilt = self.rebuilt()
        self.assertEqual(old["fases"][0]["rotulo"], "Preparación · no se mide")
        self.assertEqual(rebuilt["fases"][0]["rotulo"], "Preparación · traza grabando, no se mide")
        self.assertEqual(rebuilt["leyenda"][0], "Video: toda la prueba · Traza: desde la preparación")


# ── S · `siguiente` con el estado de ahora y con versiones anteriores ────────

M2 = {"id": "M2", "titulo": "Guardar la lista en memoria", "estado": "propuesta", "metrica": "abrir_ms"}
DATE_TIME = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}"


def clean_env():
    """El entorno sin las variables con las que un agente marca sus shells (los tests corren igual en todos lados)."""
    return {name: value for name, value in os.environ.items() if name not in AGENT_ENV}


def quiet(function, *args, **kwargs):
    """Corre una función de perf.py en este proceso y devuelve lo que imprime."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, clean_env(), clear=True):
        function(*args, **kwargs)
    return out.getvalue()


class DecisionBase(TriageBase):
    """Riguroso con antes y control medidos y dos mejoras propuestas: el paso es la decisión del usuario."""
    skill = None  # la versión que midió antes y control (None: fases.json no la guarda)
    flow = None  # campos extra del flujo

    def setUp(self):
        super().setUp()
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan.pop("profundidad", None)
        plan["mejoras"].append(dict(M2))
        plan["flujos"]["catalogo-lista"].update(self.flow or {})
        write(self.folder / "plan.json", json.dumps(plan))
        record = {"corridas": 10}
        record.update({"skill": self.skill} if self.skill else {})
        write(self.folder / "fases.json", json.dumps({
            "antes": dict(record, fecha="2026-03-02T10:00:00", flujos={"catalogo-lista": dict(record)}),
            "control": dict(record, fecha="2026-03-02T11:00:00", flujos={"catalogo-lista": dict(record)})}))

    def plan_json(self):
        return json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))

    def state(self):
        return (self.folder / "estado.md").read_text(encoding="utf-8")

    def decisions(self):
        return self.state().split("## Decisiones\n\n")[1].split("\n## ")[0]


class NextReadsDiskTest(DecisionBase):
    """S1: el paso siguiente sale del plan.json de ahora, no del que el comando cargó al empezar."""

    def test_print_next_relee_el_plan(self):
        stale = self.plan()
        self.ok_in("decidir", "--carpeta", self.rel, "--aprobar", "M1")  # otra terminal, mientras el comando corría
        out = quiet(perf.print_next, self.folder, stale)
        self.assertIn("Siguiente · sesión 3 · M1", out)
        self.assertNotIn("decisión del usuario", out)
        self.assertIn("**Paso:** sesión 3 · M1", self.state())

    def test_un_reporte_largo_termina_con_el_estado_de_ahora(self):
        real = perf.write_report_pair

        def slow_report(*args, **kwargs):  # mientras se arma el reporte, alguien corre `decidir` en otra terminal
            self.ok_in("decidir", "--carpeta", self.rel, "--aprobar", "M1")
            return real(*args, **kwargs)

        args = argparse.Namespace(carpeta=str(self.folder), inicial=True, html=False, gerencia_unificado=False)
        with mock.patch.object(perf, "write_report_pair", slow_report):
            out = quiet(perf.cmd_reporte, args)
        self.assertIn("Siguiente · sesión 3 · M1", out)
        self.assertNotIn("Siguiente · decisión del usuario", out)

    def test_pausar_y_recuperar_releen_el_plan(self):
        source = SCRIPT.read_text(encoding="utf-8")
        body = source[source.index("def print_next(folder, plan, flow=None):"):]
        self.assertLess(body.index("plan = fresh_plan(folder, plan)"), body.index("next_steps("))  # antes de armar el paso
        for command in ("cmd_pausar", "cmd_recuperar", "cmd_reporte", "capture_batch", "cmd_reanudar"):
            start = source.index("def %s(" % command)
            end = source.index("\ndef ", start + 1)
            self.assertIn("print_next(folder, plan", source[start:end], command)
        # sin plan.json en la carpeta (o ilegible), vale el que el comando ya tenía
        self.assertEqual(perf.fresh_plan(self.dir / "no-existe", {"a": 1}), {"a": 1})
        write(self.dir / "roto" / "plan.json", "{")
        self.assertEqual(perf.fresh_plan(self.dir / "roto", {"a": 1}), {"a": 1})


class CaptureEndsWithFreshPlanTest(CaptureBase):
    """S1 de punta a punta: mientras corre la prueba, `decidir --aprobar` cambia plan.json; la prueba termina con la
    sesión 3, no con la decisión que ya se tomó."""

    def test_la_prueba_termina_con_el_paso_de_ahora(self):
        decide = "%s -I %s decidir --carpeta %s --aprobar M1 > /dev/null" % tuple(
            shlex.quote(str(part)) for part in (sys.executable, SCRIPT, self.folder))
        self.plan_with(flujo={"recorrido": decide}, mejoras=[
            {"id": "M1", "titulo": "Una sola llamada al abrir la lista", "estado": "propuesta", "metrica": "jank_app_pct"}])
        record = {"corridas": 10, "skill": perf.VERSION}
        write(self.folder / "fases.json", json.dumps({
            "antes": dict(record, fecha="2026-03-02T10:00:00", flujos={"home": dict(record)}),
            "control": dict(record, fecha="2026-03-02T11:00:00", flujos={"home": dict(record)})}))
        write(self.folder / "diagnostico.md", "x\n")
        write(self.folder / "reporte-inicial-dev.md", "# reporte\n")
        self.assertIn("decisión del usuario", self.ok("siguiente", "--carpeta", self.folder))
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("Siguiente · sesión 3 · M1", out)
        self.assertNotIn("Siguiente · decisión del usuario", out)
        self.assertRegex(out, r"M1 aprobada el %s; si no fue tu decisión: `cd " % DATE_TIME)


class UncutBaselineTest(DecisionBase):
    """S2: antes y control medidos con una versión que no cortaba la traza (sin `corte_s`): se dice una sola vez."""
    skill = "0.14.0"
    flow = {"preparar": "true"}

    def test_lo_dice_una_sola_vez_y_queda_en_estado(self):
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        line = next(line for line in out.splitlines() if "Línea base de una versión anterior" in line)
        self.assertIn("Flujo catalogo-lista: antes y control se midieron con hb-performance 0.14.0", line)
        self.assertIn("ninguna fase de este flujo la corta y el después se compara igual contra igual", line)
        self.assertIn("no hace falta rehacer la línea base", line)
        self.assertRegex(self.decisions(), r"- %s: flujo catalogo-lista: antes y control se midieron con hb-performance "
                                           r"0\.14\.0.*\(perf\.py\)" % DATE_TIME)
        again = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertNotIn("Línea base de una versión anterior", again)
        self.assertEqual(self.decisions().count("no hace falta rehacer la línea base"), 1)
        self.assertIn("decisión del usuario", again)  # el paso no cambia

    def test_no_cambia_el_corte_de_ninguna_fase(self):
        flow = self.plan()["flujos"]["catalogo-lista"]
        before = perf.trace_tail(self.folder, flow, "catalogo-lista", None, "true", False, "true", "despues")
        self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertEqual(perf.trace_tail(self.folder, flow, "catalogo-lista", None, "true", False, "true", "despues"),
                         before)
        self.assertEqual(before, [])  # ninguna fase del flujo corta


class UncutBaselineNotNeededTest(DecisionBase):
    skill = "0.14.0"

    def lines(self):
        return perf.uncut_baseline_lines(self.folder, self.plan())

    def set_flow(self, **fields):
        plan = self.plan_json()
        plan["flujos"]["catalogo-lista"].update(fields)
        write(self.folder / "plan.json", json.dumps(plan))

    def set_phases(self, **fields):
        phases = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))
        for phase in ("antes", "control"):
            phases[phase]["flujos"]["catalogo-lista"].update(fields)
        write(self.folder / "fases.json", json.dumps(phases))
        return phases

    def test_solo_donde_esta_version_cortaria(self):
        self.assertEqual(self.lines(), [])  # sin 'preparar', ninguna versión corta: no hay nada que aclarar
        self.set_flow(preparar="true")
        self.assertEqual(len(self.lines()), 1)
        self.set_flow(cola_s=0)
        self.assertEqual(self.lines(), [])
        self.set_flow(cola_s=5, traza_desde_preparar=True)
        self.assertEqual(self.lines(), [])

    def test_no_con_una_linea_base_de_esta_version_ni_con_el_despues_medido(self):
        self.set_flow(preparar="true")
        self.set_phases(skill="0.16.0")
        self.assertEqual(self.lines(), [])
        self.set_phases(skill="0.14.0", corte_s=12.5)
        self.assertEqual(self.lines(), [])
        phases = self.set_phases(corte_s=None)
        self.assertEqual(len(self.lines()), 1)
        phases["despues"] = {"fecha": "2026-03-03T10:00:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}}
        write(self.folder / "fases.json", json.dumps(phases))
        self.assertEqual(self.lines(), [])

    def test_con_una_sola_fase_medida_no_afirma_nada(self):
        self.set_flow(preparar="true")
        phases = self.set_phases()
        self.assertEqual(len(self.lines()), 1)
        phases.pop("control")  # solo antes: completarlo o rehacerlo con esta versión sí podría cortar la traza
        write(self.folder / "fases.json", json.dumps(phases))
        self.assertEqual(self.lines(), [])
        write(self.folder / "advertencias.json", json.dumps({"cola": {"catalogo-lista": {"ultima_marca_s": 4.0,
                                                                                         "traza_s": 30.0}}}))
        flow = self.plan()["flujos"]["catalogo-lista"]
        self.assertNotEqual(perf.trace_tail(self.folder, flow, "catalogo-lista", None, "true", False, "true", "antes"), [])

    def test_no_en_triage_ni_sin_decisiones_en_estado(self):
        self.set_flow(preparar="true")
        plan = self.plan_json()
        plan["profundidad"] = "triage"
        write(self.folder / "plan.json", json.dumps(plan))
        self.assertEqual(self.lines(), [])
        plan.pop("profundidad")
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "estado.md", self.state().replace("## Decisiones", "## Otra cosa"))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        line = next(line for line in out.splitlines() if "Línea base de una versión anterior" in line)
        self.assertIn("(no se repite)", line)  # sin la sección, no dice que quedó en estado.md
        self.assertNotIn("Línea base de una versión anterior", self.ok_in("siguiente", "--carpeta", self.rel))


OLD_REPORT = "<!doctype html><html><head><title>Reporte</title></head><body><h1>Reporte inicial</h1></body></html>"


class OldReportOfferTest(DecisionBase):
    """S3: un reporte inicial de una estructura anterior: `siguiente` ofrece generarlo de nuevo, como paso opcional."""

    def test_lo_ofrece_dentro_de_la_decision(self):
        write(self.folder / "reporte-inicial-dev.html", OLD_REPORT)
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("decisión del usuario", out)
        self.assertIn("Opcional, antes de decidir:", out)
        self.assertRegex(out, r"`cd \S+ && python3 -I \S+perf\.py reporte --carpeta %s --inicial --html`" % re.escape(self.rel))
        self.assertIn("reporte-inicial-dev.estructura-anterior.html", out)
        self.assertLess(out.index("Opcional, antes de decidir:"), out.index("Elige uno"))
        commands = commands_in(out)
        self.assertIn(" decidir --carpeta", commands[0])  # el primer comando para pegar sigue siendo la decisión
        self.assertIn("**Elige uno de los caminos (no van en orden):**", self.state())

    def test_no_lo_ofrece_con_la_estructura_de_ahora(self):
        page = perf.report_page("App de pedidos", "Performance · Pedidos", "Reporte técnico dev", "dev",
                                [("resumen", "Resumen", "<p>x</p>")], "2026-11-20")
        write(self.folder / "reporte-inicial-dev.html", page)
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertNotIn("Opcional, antes de decidir", out)
        self.assertTrue(commands_in(out)[0].split(" decidir ")[1].startswith("--carpeta"))

    def test_la_estructura_sale_de_la_marca_de_la_pagina(self):
        page = perf.report_page("App de pedidos", "Performance · Pedidos", "", "gerencia",
                                [("resumen", "Resumen", "<p>x</p>")], "2026-11-20")
        self.assertIn('<meta name="hb-perf-reporte" content="estructura-2">', page)
        self.assertNotIn(perf.VERSION, page)  # la versión de la skill no va en los HTML
        self.assertNotIn("{{", page)
        current, old, unmarked = self.dir / "a.html", self.dir / "b.html", self.dir / "c.html"
        write(current, page)
        write(old, OLD_REPORT)
        # generado antes de que existiera la marca, ya con la estructura de ahora (el público en <body> y el índice)
        write(unmarked, page.replace('<meta name="hb-perf-reporte" content="estructura-2">\n', ""))
        self.assertEqual([perf.report_structure(path) for path in (current, old, unmarked)], [2, 1, 2])
        self.assertIsNone(perf.report_structure(self.folder / "reporte-inicial-dev.md"))
        self.assertIsNone(perf.report_structure(self.dir / "no-existe.html"))
        newer = self.dir / "d.html"
        write(newer, page.replace("estructura-2", "estructura-3"))  # de una versión más nueva: no es "anterior"
        self.assertEqual([perf.old_structure(path) for path in (current, old, unmarked, newer)], [False, True, False, False])
        self.assertIsNone(perf.backup_old_report(newer))


class OldReportBackupTest(ReportFixtureBase):
    """S3: `reporte` guarda una copia del HTML de una estructura anterior antes de sobrescribirlo, sin pisar otra."""

    def test_respalda_antes_de_sobrescribir(self):
        target = self.folder / "reporte-inicial-dev.html"
        write(target, OLD_REPORT)
        out = self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        copy = self.folder / "reporte-inicial-dev.estructura-anterior.html"
        self.assertEqual(copy.read_text(encoding="utf-8"), OLD_REPORT)
        self.assertIn("guardé una copia en %s" % copy, out)
        self.assertEqual(perf.report_structure(target), perf.REPORT_STRUCTURE)
        self.assertIn("Siguiente", out)
        # generarlo de nuevo no hace otra copia: el que hay ya es de la estructura de ahora
        again = self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertNotIn("guardé una copia", again)
        self.assertEqual(sorted(path.name for path in self.folder.glob("*estructura-anterior*")),
                         ["reporte-inicial-dev.estructura-anterior.html"])
        # otro viejo en el mismo lugar: la copia nueva no pisa la que ya estaba
        write(target, OLD_REPORT + "<!-- otro -->")
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertEqual(copy.read_text(encoding="utf-8"), OLD_REPORT)
        self.assertEqual((self.folder / "reporte-inicial-dev.estructura-anterior-2.html").read_text(encoding="utf-8"),
                         OLD_REPORT + "<!-- otro -->")


# ── D · `decidir` con rastro y con vuelta atrás ──────────────────────────────

class DecideTraceTest(DecisionBase):
    def test_la_linea_lleva_la_fecha_y_la_hora(self):
        out = self.ok_in("decidir", "--carpeta", self.rel, "--aprobar", "M1", "--descartar", "M2")
        self.assertRegex(out, r"✔ %s: aprobadas M1; descartadas M2 \(perf\.py decidir\)" % DATE_TIME)
        self.assertRegex(self.decisions(), r"^- %s: aprobadas M1; descartadas M2 \(perf\.py decidir\)$" % DATE_TIME)
        self.assertNotIn("<AAAA-MM-DD", self.decisions())
        for item in self.plan_json()["mejoras"]:
            self.assertRegex(item["decidida_en"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
            self.assertNotIn("decidida_desde", item)  # sin terminal ni variable de un agente: solo la hora

    def test_el_origen_solo_cuando_consta(self):
        with mock.patch.dict(os.environ, dict(clean_env(), CLAUDECODE="1"), clear=True):
            self.assertEqual(perf.command_origin(), "chat de Claude Code")
        with mock.patch.dict(os.environ, dict(clean_env(), AI_AGENT="otro-agente_1.2\n(x)"), clear=True):
            self.assertEqual(perf.command_origin(), "chat (otro-agente_1.2 x)")
        terminal = mock.Mock()
        terminal.isatty.return_value = True
        with mock.patch.dict(os.environ, clean_env(), clear=True), mock.patch.object(perf.sys, "stdin", terminal):
            self.assertEqual(perf.command_origin(), "")  # una terminal no se distingue de un agente sin variable

    def test_el_origen_queda_en_estado_y_en_el_plan(self):
        self.env["CLAUDECODE"] = "1"
        out = self.ok_in("decidir", "--carpeta", self.rel, "--aprobar", "M1")
        self.assertRegex(out, r"✔ %s \(chat de Claude Code\): aprobadas M1 \(perf\.py decidir\)" % DATE_TIME)
        self.assertRegex(self.decisions(), r"- %s \(chat de Claude Code\): aprobadas M1" % DATE_TIME)
        self.assertEqual(self.plan_json()["mejoras"][0]["decidida_desde"], "chat de Claude Code")
        self.assertNotIn("decidida_en", self.plan_json()["mejoras"][1])  # M2 no se decidió

    def test_siguiente_dice_cuando_se_aprobo_antes_de_la_sesion_3(self):
        self.env["CLAUDECODE"] = "1"
        self.ok_in("decidir", "--carpeta", self.rel, "--aprobar", "M1,M2")
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("sesión 3 · M1", out)
        for name in ("M1", "M2"):
            self.assertRegex(out, r"%s aprobada el %s \(chat de Claude Code\); si no fue tu decisión: `cd \S+ && python3 -I "
                                  r"\S+perf\.py decidir --carpeta %s --reabrir %s`" % (name, DATE_TIME, re.escape(self.rel),
                                                                                       name))
        self.assertLess(out.index("M1 aprobada el"), out.index("Chat nuevo"))  # antes de dar el chat
        self.assertIn("aprobada el", self.state())  # también en "Siguiente paso" de estado.md

    def test_una_aprobada_con_una_version_anterior_no_tiene_hora(self):
        plan = self.plan_json()
        plan["mejoras"][0]["estado"] = "aprobada"  # como la dejaba 0.17.0: sin `decidida_en`
        write(self.folder / "plan.json", json.dumps(plan))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("M1 aprobada sin fecha (la registró una versión anterior, que no guardaba la hora); si no fue tu "
                      "decisión:", out)


class ReopenTest(DecisionBase):
    def test_reabrir_vuelve_a_propuesta_desde_cada_estado(self):
        for option, state in (("--aprobar", "aprobada"), ("--pendiente", "pendiente"), ("--descartar", "descartada")):
            self.ok_in("decidir", "--carpeta", self.rel, option, "M1")
            self.assertEqual(self.plan_json()["mejoras"][0]["estado"], state)
            code = (self.root / "app" / "Lista.kt").read_text(encoding="utf-8")
            out = self.ok_in("decidir", "--carpeta", self.rel, "--reabrir", "M1")
            self.assertRegex(out, r"✔ %s: reabiertas \(vuelven a propuesta\) M1 \(perf\.py decidir\)" % DATE_TIME)
            self.assertEqual(self.plan_json()["mejoras"][0]["estado"], "propuesta")
            self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), code)  # no toca código
            self.assertIn("decisión del usuario", out)  # el paso vuelve a ser decidir
        self.assertEqual(self.decisions().count("reabiertas (vuelven a propuesta) M1"), 3)

    def test_una_aplicada_no_se_reabre_y_dice_que_hacer(self):
        plan = self.plan_json()
        plan["mejoras"][0].update(estado="aplicada", aplicada_en="2026-03-03T09:00:00")
        write(self.folder / "plan.json", json.dumps(plan))
        before = (self.folder / "plan.json").read_text(encoding="utf-8"), self.state()
        result = self.run_in("decidir", "--carpeta", self.rel, "--reabrir", "M1")
        self.assertNotEqual(result.returncode, 0)
        text = result.stdout + result.stderr
        self.assertIn("M1 ya está aplicada: su código está en el árbol, y `--reabrir` solo cambia el plan", text)
        self.assertIn("lineabase --carpeta %s --quitar-mejoras" % self.rel, text)
        self.assertIn("siguiente --carpeta %s" % self.rel, text)
        self.assertNotIn("Traceback", text)
        self.assertEqual(((self.folder / "plan.json").read_text(encoding="utf-8"), self.state()), before)

    def test_reabrir_y_decidir_la_misma_a_la_vez_se_rechaza(self):
        before = (self.folder / "plan.json").read_text(encoding="utf-8"), self.state()
        result = self.run_in("decidir", "--carpeta", self.rel, "--reabrir", "M1", "--aprobar", "M1,M2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("M1 está en --reabrir y en otra lista a la vez: elige una", result.stdout + result.stderr)
        self.assertEqual(((self.folder / "plan.json").read_text(encoding="utf-8"), self.state()), before)

    def test_reabrir_una_propuesta_no_cambia_nada(self):
        before = self.decisions()
        out = self.ok_in("decidir", "--carpeta", self.rel, "--reabrir", "M1")
        self.assertIn("M1 ya está como propuesta: no cambié nada", out)
        self.assertEqual(self.decisions(), before)
        self.assertNotIn("decidida_en", self.plan_json()["mejoras"][0])

    def test_la_ayuda_distingue_pendiente_de_reabrir(self):
        result = self.run_in("decidir", "--help")
        text = re.sub(r"\s+", " ", result.stdout)
        self.assertIn("decididas para más adelante", text)
        self.assertIn("no es \"sin decidir\": para eso, --reabrir", text)
        self.assertIn("vuelven a \"propuesta\" (sin decidir)", text)
        self.assertIn("no toca código", text)


if __name__ == "__main__":
    unittest.main()
