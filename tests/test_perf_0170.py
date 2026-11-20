"""Tests de hb-performance 0.17.0: el video de evidencia de la corrida de prueba (V1–V8), completo, unido y rotulado
fuera de la imagen. Los datos son inventados. Los que necesitan ffmpeg de verdad se saltan si no está (en el CI de
Ubuntu sí está)."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, write
from test_perf import GOOD, PerfBase, perf
from test_perf_0160 import CaptureBase, FakeAdb, ReportFixtureBase

SCRIPT = ROOT / "skills" / "hb-performance" / "scripts" / "perf.py"
PARTS = ["video/home/parte1.mp4", "video/home/parte2.mp4", "video/home/parte3.mp4"]


def prototype_events(**overrides):
    """Los eventos del prototipo aprobado (datos inventados): tres tramos, preparación, tres tramos medidos y el fin."""
    clock = {"preparar_inicio": 1000.3, "preparar_fin": 1003.9, "traza": 1003.95, "recorrido_inicio": 1004.0,
             "recorrido_fin": 1009.4}
    spans = [("Cargar Inicio", 1004.0, 1006.8), ("Abrir Ver detalle", 1006.8, 1008.6), ("Volver a Inicio", 1008.6, 1009.4)]
    marks = [(1004.05, "SCREEN Inicio onCreate"), (1005.9, "MARK pedidos_visible"), (1006.8, "MARK ver_detalle_tap"),
             (1008.1, "MARK detalle_visible"), (1008.6, "MARK volver_tap"), (1009.35, "MARK pedidos_vuelta")]
    args = dict(flow_name="home", recorder="screenrecord", parts=PARTS, starts=[1000.0, 1004.2, 1007.5], ended=1010.0,
                clock=clock, spans=spans, marks=marks, alignment={"marcas": "ok", "detalle": ""}, label="Inicio")
    args.update(overrides)
    return perf.video_events(**args)


def wait_until(condition, tries=100):
    """Espera a que algo pase, por intentos (sin depender de cuánto tarda la máquina)."""
    for _ in range(tries):
        if condition():
            return True
        time.sleep(0.1)
    return condition()


# ── V2 · Eventos con un solo reloj ───────────────────────────────────────────

class VideoEventsTest(unittest.TestCase):
    def test_los_eventos_del_prototipo_salen_iguales(self):
        events = prototype_events()
        self.assertEqual([(f["desde"], f["hasta"], f["rotulo"], f["tipo"]) for f in events["fases"]], [
            (0.0, 4.0, "Preparación · no se mide", "prep"), (4.0, 6.8, "Medición · Cargar Inicio", "med"),
            (6.8, 8.6, "Medición · Abrir Ver detalle", "med"), (8.6, 9.4, "Medición · Volver a Inicio", "med"),
            (9.4, 10.0, "Fin de la prueba", "fin")])
        self.assertEqual(events["tramos_video"], [{"archivo": PARTS[0], "inicio": 0.0}, {"archivo": PARTS[1], "inicio": 4.2},
                                                  {"archivo": PARTS[2], "inicio": 7.5}])
        self.assertEqual(events["marcas"][0], {"t": 4.05, "nombre": "SCREEN Inicio onCreate"})
        self.assertEqual(events["duracion"], 10.0)
        self.assertEqual(events["preparar"], [0.3, 3.9])

    def test_las_fases_cubren_todo_el_video_sin_huecos(self):
        events = prototype_events(spans=[("A", 1005.0, 1006.0), ("B", 1007.0, 1008.0)])
        phases = events["fases"]
        self.assertEqual(phases[0]["desde"], 0.0)
        self.assertEqual(phases[-1]["hasta"], events["duracion"])
        for before, after in zip(phases, phases[1:]):
            self.assertEqual(before["hasta"], after["desde"])
        self.assertIn(("Recorrido · entre tramos", "rec"), [(f["rotulo"], f["tipo"]) for f in phases])

    def test_sin_tramos_ubicados_todo_el_recorrido_es_medicion(self):
        events = prototype_events(spans=[], marks=[], alignment={"marcas": "falló", "detalle": "x"})
        self.assertEqual([f["rotulo"] for f in events["fases"]],
                         ["Preparación · no se mide", "Medición · Inicio", "Fin de la prueba"])
        self.assertEqual(events["marcas"], [])

    def test_si_preparar_fallo_todo_es_preparacion(self):
        events = prototype_events(clock={"preparar_inicio": 1000.3, "preparar_fin": 1003.9}, spans=[], marks=[])
        self.assertEqual([(f["rotulo"], f["desde"], f["hasta"]) for f in events["fases"]],
                         [("Preparación · no se mide", 0.0, 10.0)])

    def test_las_marcas_fuera_del_video_no_van_y_hay_tope(self):
        marks = [(990.0, "MARK antes"), (1011.0, "MARK despues")] + [(1004.0 + i * 0.01, "MARK m%d" % i) for i in range(160)]
        events = prototype_events(marks=marks)
        self.assertEqual(len(events["marcas"]), perf.VIDEO_MARKS_MAX)
        self.assertNotIn("MARK antes", [m["nombre"] for m in events["marcas"]])
        self.assertIn("se muestran las primeras %d marcas de 160" % perf.VIDEO_MARKS_MAX, events["alineacion"]["detalle"])

    def test_cada_marca_se_ve_hasta_la_siguiente_o_un_rato(self):
        windows = perf.mark_windows({"duracion": 10.0, "marcas": [{"t": 1.0, "nombre": "a"}, {"t": 1.5, "nombre": "b"},
                                                                  {"t": 5.0, "nombre": "c"}]})
        self.assertEqual([(round(a, 2), round(b, 2)) for a, b, _ in windows], [(1.0, 1.5), (1.5, 2.7), (5.0, 6.2)])

    def test_la_cola_del_video_es_del_flujo_o_del_plan(self):
        self.assertEqual(perf.video_tail({}, {}), 2.0)
        self.assertEqual(perf.video_tail({"video_cola_s": 5}, {"video_cola_s": 1}), 5.0)
        self.assertEqual(perf.video_tail({}, {"video_cola_s": 0}), 0.0)
        self.assertEqual(perf.video_tail({"video_cola_s": "x"}, {}), 2.0)
        self.assertEqual(perf.video_tail({"video_cola_s": 999}, {}), 2.0)


class VideoClockTest(unittest.TestCase):
    """V2: hora de la traza → hora del dispositivo (ClockSnapshot) → hora de la computadora (adb shell date)."""

    def test_la_hora_del_dispositivo(self):
        self.assertEqual(perf.parse_device_time("1700000000.250000000\n"), (1700000000.25, True))
        self.assertEqual(perf.parse_device_time("1700000000"), (1700000000.5, False))
        self.assertIsNone(perf.parse_device_time("1700000000.%N"))
        self.assertIsNone(perf.parse_device_time(""))

    def test_la_diferencia_de_relojes_usa_date(self):
        class DateAdb(FakeAdb):
            def shell(self, command, stdin=None, timeout=120):
                self.calls.append(command)
                return subprocess.CompletedProcess(command, 0, "%.6f\n" % (time.time() - 100), "")

        offset, precision = perf.device_clock_offset(DateAdb())
        self.assertAlmostEqual(offset, 100, delta=1)
        self.assertLess(precision, 1)
        self.assertIsNone(perf.device_clock_offset(FakeAdb()))  # un dispositivo que no da su hora

    def test_el_reloj_realtime_de_la_traza(self):
        for name in ("REALTIME", "CLOCK_REALTIME", "BUILTIN_CLOCK_REALTIME"):
            self.assertEqual(perf.realtime_snapshot([{"ts": "5", "clock_name": "BOOTTIME", "clock_value": "5"},
                                                     {"ts": "10", "clock_name": name, "clock_value": "70"}]), (10, 70))
        self.assertIsNone(perf.realtime_snapshot([{"ts": "10", "clock_name": "REALTIME_COARSE", "clock_value": "7"}]))
        self.assertEqual(perf.realtime_snapshot([{"ts": "0", "clock_name": "REALTIME", "clock_value": "9"}]), (0, 9))
        self.assertIsNone(perf.realtime_snapshot([{"ts": "", "clock_name": "REALTIME", "clock_value": "9"}]))

    def rows(self):
        ms = 1000000
        return [("limites", 1000 * ms, 9000 * ms, 0, ""), ("seccion", 2000 * ms, 1 * ms, 0, "MARK lista_visible")]

    def test_alineacion_exacta(self):
        clock_rows = [{"ts": 1000 * 1000000, "clock_name": "REALTIME", "clock_value": 1700000000 * 10 ** 9}]
        convert, state, _ = perf.trace_clock(self.rows(), clock_rows, (300.0, 0.02), 1700000300.4)
        self.assertEqual(state, "ok")
        self.assertAlmostEqual(convert(2000 * 1000000), 1700000301.0, places=3)

    def test_relojes_que_no_coinciden_se_aproximan_por_el_inicio_de_la_traza(self):
        clock_rows = [{"ts": 1000 * 1000000, "clock_name": "REALTIME", "clock_value": 1700000000 * 10 ** 9}]
        convert, state, detail = perf.trace_clock(self.rows(), clock_rows, (300.0, 0.02), 1700000900.0)
        self.assertEqual(state, "aproximada")
        self.assertIn("los relojes no coinciden", detail)
        self.assertAlmostEqual(convert(2000 * 1000000), 1700000901.0, places=3)

    def test_sin_clocksnapshot_ni_date(self):
        _, state, detail = perf.trace_clock(self.rows(), [], None, 50.0)
        self.assertEqual(state, "aproximada")
        self.assertIn("ClockSnapshot", detail)
        convert, state, _ = perf.trace_clock([], [], None, None)
        self.assertEqual((convert, state), (None, "falló"))

    def test_tramos_y_marcas_del_plan_desde_la_traza(self):
        ms = 1000000
        rows = [("limites", 0, 9000 * ms, 0, ""), ("seccion", 1000 * ms, 1, 0, "NAV detalle"),
                ("seccion", 2500 * ms, 1, 0, "MARK detalle"), ("seccion", 3000 * ms, 1, 0, "MARK otra_cosa"),
                ("seccion", 2600 * ms, 1, 0, "HTTP GET pedidos")]
        flow = {"segmentos": [{"nombre": "abrir_detalle", "titulo": "Abrir el detalle", "desde": {"marca": "NAV detalle"},
                               "hasta": {"marca": "MARK detalle"}},
                              {"nombre": "sin_marcas", "desde": {"marca": "NAV nada"}, "hasta": {"marca": "MARK nada"}}]}
        spans, marks = perf.video_trace_events(rows, flow, "home", lambda ns: 100 + ns / 1e9)
        self.assertEqual([(text, round(first, 3), round(last, 3)) for text, first, last in spans],
                         [("Abrir el detalle", 101.0, 102.5)])
        self.assertEqual([name for _, name in marks], ["NAV detalle", "MARK detalle"])
        flow = {"ventana": {"desde": {"marca": "NAV detalle"}, "hasta": {"marca": "MARK detalle"}}, "titulo": "Pedidos"}
        spans, _ = perf.video_trace_events(rows, flow, "pedidos_lista", lambda ns: ns / 1e9)
        self.assertEqual([(text, round(first, 3), round(last, 3)) for text, first, last in spans], [("Pedidos", 1.0, 2.5)])
        spans, _ = perf.video_trace_events(rows, {"ventana": flow["ventana"]}, "pedidos_lista", lambda ns: ns / 1e9)
        self.assertEqual(spans[0][0], "pedidos lista")  # sin título, el nombre del flujo en palabras

    def test_las_fases_empiezan_en_cero_y_terminan_con_el_video(self):
        phases = perf.video_phases(5.0, (0.02, 4.98), [], "home")  # trozos de menos de 0,05 s al principio y al final
        self.assertEqual([(f["desde"], f["hasta"], f["tipo"]) for f in phases], [(0.0, 5.0, "med")])


# ── V4 · El visor HTML ───────────────────────────────────────────────────────

class VideoPageTest(unittest.TestCase):
    def test_el_visor_lleva_los_eventos_incrustados_y_salta_a_un_segundo(self):
        events = prototype_events()
        events["marcas"].append({"t": 9.9, "nombre": "MARK </script><b>x"})  # nada cierra el script de los eventos
        page = perf.video_page_html(events, "App de pedidos", "2026-11-20")
        self.assertEqual(perf.embedded_events(page), events)
        self.assertEqual(page.count("</script>"), 2)  # el de los eventos y el del tema y el reproductor
        self.assertIn('new URLSearchParams(location.search).get("t")', page)
        self.assertIn('v.addEventListener("ended"', page)  # pasa al tramo siguiente al terminar uno
        self.assertIn("Desde el inicio", page)
        self.assertIn("Reproducir", page)
        self.assertIn("App de pedidos", page)
        self.assertIn("theme-btn", page)
        self.assertNotRegex(page, r'(?:src|href)="(?:https?:)?//')  # sin recursos externos
        self.assertNotIn("{{", page)

    def test_lo_que_hay_que_mirar_de_cada_prueba(self):
        with mock.patch.dict(os.environ, {}), TempDir() as folder:
            write(folder / "prueba-home.html", "x")
            write(folder / "prueba-pedidos.mp4", "x")
            write(folder / "prueba-pedidos.html", "x")
            write(folder / "prueba-pedidos-2.mp4", "x")  # un segmento suelto de 0.16.0
            self.assertEqual(perf.test_videos(folder), [folder / "prueba-home.html", folder / "prueba-pedidos.mp4"])


class TempDir:
    def __enter__(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        return Path(self.tmp.name)

    def __exit__(self, *exc):
        self.tmp.cleanup()


# ── V3 · Los comandos de ffmpeg (como texto, sin correrlos) ─────────────────

class FfmpegCommandTest(unittest.TestCase):
    def test_las_bandas_van_fuera_de_la_imagen_del_telefono(self):
        events = prototype_events()
        width, height = 1080, 2340
        graph, texts = perf.video_filter(events, width, height)
        head, foot = perf.even(perf.VIDEO_HEAD * 2), perf.even(perf.VIDEO_FOOT * 2)
        self.assertIn("pad=iw:ih+%d:0:%d:color=0x121317" % (head + foot, head), graph)
        for kind, y in re.findall(r"(drawbox|drawtext)=[^,;]*?:y=(\d+)", graph):
            self.assertTrue(int(y) < head or int(y) >= head + height, "%s en y=%s cae sobre la imagen" % (kind, y))
        overlay = re.search(r"overlay=x='t/10\*1080':y=(\d+)", graph)
        self.assertTrue(overlay and int(overlay.group(1)) >= head + height)
        for draw in re.findall(r"drawtext=[^,;]*", graph):  # sin textos en el filtro: nada que escapar
            self.assertTrue("textfile=" in draw or "%{pts" in draw, draw)
            self.assertIn("fontfile=fuente", draw)
        self.assertEqual(texts["rotulo-fase-2.txt"], "Medición · Cargar Inicio")
        self.assertEqual(texts["rotulo-marca-1.txt"], "● SCREEN Inicio onCreate")
        self.assertIn("enable='between(t,4,6.799)'", graph)
        self.assertIn("color=0x3657d6", graph)  # medición en azul, preparación en gris, fin oscuro
        self.assertIn("color=0x6b7380", graph)
        self.assertIn("color=0x3a3d45", graph)

    def test_sin_rotulos_solo_une(self):
        graph, texts = perf.video_filter(prototype_events(), 0, 0, labels=False)
        self.assertEqual((graph, texts), ("[0:v]fps=30,format=yuv420p[out]", {}))

    def test_la_lista_de_concat_respeta_el_inicio_de_cada_tramo(self):
        self.assertEqual(perf.concat_list(prototype_events()),
                         "file 'parte1.mp4'\nduration 4.2\nfile 'parte2.mp4'\nduration 3.3\nfile 'parte3.mp4'\n"
                         "duration 2.5\n")

    def test_el_comando_de_ffmpeg(self):
        events = prototype_events()
        command = perf.ffmpeg_command("/x/ffmpeg", events, "G", "libx264", Path("/x/salida.mp4"))
        text = " ".join(command)
        for piece in ("-f concat -safe 0 -i lista.txt", "-filter_complex G", "-c:v libx264 -preset veryfast",
                      "-movflags +faststart", "-t 10", "-an"):
            self.assertIn(piece, text)
        text = " ".join(perf.ffmpeg_command("/x/ffmpeg", events, "G", "h264_videotoolbox", Path("/x/s.mp4")))
        self.assertIn("-c:v h264_videotoolbox", text)
        self.assertNotIn("-preset", text)

    def test_que_trae_ese_ffmpeg(self):
        filters = " T.. drawbox           V->V       Draw a colored box on the input video.\n" \
                  " T.C drawtext          V->V       Draw text on top of video frames using libfreetype library.\n"
        self.assertTrue(perf.listed(filters, "drawtext"))
        self.assertFalse(perf.listed(filters, "drawgrid"))
        self.assertFalse(perf.listed(" ... Draw text drawtext", "drawtext"))
        with TempDir() as folder:
            fake = folder / "ffmpeg"
            write(fake, "#!/bin/sh\ncase \"$2\" in -filters) printf '%s\\n' ' T.C drawtext   V->V  x';;\n"
                        "-encoders) printf '%s\\n' ' V....D h264_videotoolbox  VideoToolbox H.264';; esac\n")
            fake.chmod(0o755)
            self.assertEqual(perf.ffmpeg_features(str(fake)), {"drawtext": True, "codificador": "h264_videotoolbox"})
            with mock.patch.dict(os.environ, {"FFMPEG": str(fake)}):
                self.assertEqual(perf.ffmpeg_binary(), str(fake))
            with mock.patch.dict(os.environ, {"FFMPEG": ""}):
                self.assertIsNone(perf.ffmpeg_binary())

    def test_la_fuente_del_plan_o_una_del_sistema(self):
        with TempDir() as folder:
            font = folder / "mi fuente.ttf"
            write(font, "x")
            self.assertEqual(perf.video_font({}, {"video_fuente": str(font)}), (str(font.resolve()), str(font.resolve())))
            self.assertIsNone(perf.video_font({"video_fuente": str(folder / "no.ttf")}, {}))
            perf.link_font(str(font), folder / "fuente.ttf")
            perf.link_font(str(font), folder / "fuente.ttf")  # dos veces: no falla
            self.assertEqual((folder / "fuente.ttf").read_text(encoding="utf-8"), "x")


# ── V1 · Grabadores ──────────────────────────────────────────────────────────

class RecorderChoiceTest(unittest.TestCase):
    def test_screenrecord_por_defecto(self):
        self.assertEqual(perf.video_recorder_choice({}, {}), ("screenrecord", ""))

    def test_scrcpy_solo_si_esta_y_acepta_los_flags(self):
        self.assertEqual(perf.video_recorder_choice({"video_grabador": "scrcpy"}, {}, "/x/scrcpy", True), ("scrcpy", ""))
        self.assertEqual(perf.video_recorder_choice({}, {"video_grabador": "auto"}, "/x/scrcpy", True), ("scrcpy", ""))
        self.assertEqual(perf.video_recorder_choice({}, {"video_grabador": "auto"}, "", False), ("screenrecord", ""))
        kind, note = perf.video_recorder_choice({"video_grabador": "scrcpy"}, {}, "", False)
        self.assertEqual(kind, "screenrecord")
        self.assertIn("no está instalado", note)
        kind, note = perf.video_recorder_choice({"video_grabador": "scrcpy"}, {}, "/x/scrcpy", False)
        self.assertIn("no acepta --no-playback, --no-window y --record", note)
        kind, note = perf.video_recorder_choice({"video_grabador": "camara"}, {})
        self.assertEqual(kind, "screenrecord")
        self.assertIn("no es screenrecord, scrcpy ni auto", note)

    def test_el_comando_de_scrcpy(self):
        recorder = perf.ScrcpyRecorder("/x/scrcpy", "emulator-5554", Path("/x/grabando-scrcpy.mp4"))
        self.assertEqual(recorder.command(), ["/x/scrcpy", "--serial=emulator-5554", "--no-playback", "--no-window",
                                              "--no-audio", "--record=/x/grabando-scrcpy.mp4"])


class VideoChainStartTest(unittest.TestCase):
    def test_cada_tramo_anota_cuando_empezo(self):
        adb = FakeAdb(["sh", "-c", "echo 'Content area is 1080x2400 at offset x=0 y=0'; sleep 0.3", "x"])
        chain = perf.VideoChain(adb, 180).start()
        self.assertTrue(wait_until(lambda: chain.exact[0] is not None))
        with TempDir() as folder:
            parts = chain.stop(names=lambda number: folder / ("parte%d.mp4" % number))
            self.assertEqual(parts, [folder / "parte1.mp4"])
        starts, precise = chain.starts()
        self.assertTrue(precise)
        self.assertGreaterEqual(starts[0], chain.launched[0])
        self.assertTrue(adb.calls[0].startswith("rm -f /sdcard/hbperf-prueba.mp4 /sdcard/hbperf-prueba-2.mp4"))

    def test_sin_la_linea_de_inicio_vale_cuando_se_lanzo(self):
        chain = perf.VideoChain(FakeAdb(["sh", "-c", "exit 0", "x"]), 180).start()
        with TempDir() as folder:
            chain.stop(names=lambda number: folder / ("parte%d.mp4" % number))
        starts, precise = chain.starts()
        self.assertFalse(precise)
        self.assertEqual(starts, chain.launched)

    def test_se_detiene_sola_despues_de_la_cola(self):
        adb = FakeAdb(["sh", "-c", "sleep 1", "x"])
        chain = perf.VideoChain(adb, 180).start()
        chain.stop_later(0)
        stop = perf.video_stop_command("/sdcard/hbperf-prueba.mp4")
        self.assertTrue(wait_until(lambda: stop in adb.calls, tries=200))
        with TempDir() as folder:
            chain.stop(names=lambda number: folder / ("parte%d.mp4" % number))
        self.assertEqual(adb.calls.count(stop), 1)  # una sola vez


class ScrcpyRecorderTest(unittest.TestCase):
    def test_graba_un_solo_archivo_y_lo_cierra_con_sigint(self):
        with TempDir() as folder:
            fake = folder / "scrcpy"
            write(fake, "#!/bin/sh\nfor a in \"$@\"; do case \"$a\" in --record=*) out=\"${a#--record=}\";; "
                        "--help) echo '--no-playback --no-window --record=FILE'; exit 0;; esac; done\n"
                        "trap 'printf video > \"$out\"; exit 0' INT\n"
                        "echo \"INFO: Recording started to mp4 file: $out\"\nwhile :; do sleep 0.1; done\n")
            fake.chmod(0o755)
            self.assertTrue(perf.scrcpy_ready(str(fake)))
            recorder = perf.ScrcpyRecorder(str(fake), "", folder / "video" / "home" / "grabando-scrcpy.mp4").start()
            self.assertTrue(wait_until(lambda: recorder.exact[0] is not None))
            parts = recorder.stop(names=lambda number: folder / "video" / "home" / ("parte%d.mp4" % number))
            self.assertEqual(parts, [folder / "video" / "home" / "parte1.mp4"])
            self.assertEqual(parts[0].read_text(encoding="utf-8"), "video")
            self.assertEqual(recorder.starts(), ([recorder.exact[0]], True))
            self.assertFalse((folder / "video" / "home" / "grabando-scrcpy.mp4").exists())


# ── Mediciones intactas: una fase medida nunca graba ─────────────────────────

class MeasuredPhaseNeverRecordsTest(CaptureBase):
    def test_una_fase_medida_no_lanza_ninguna_grabacion(self):
        self.capture(runs=2)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertNotIn("screenrecord", log)
        self.assertNotIn("date +%s", log)
        self.assertFalse((self.folder / "video").exists())

    def test_solo_la_prueba_crea_el_video(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count("TestVideo(folder, plan, flow, flow_name, adb, serial)"), 1)
        start = source.index("TestVideo(folder, plan, flow, flow_name, adb, serial)")
        guard = source.rindex("if args.prueba and args.plan and not getattr(args, \"sin_video\", False)", 0, start)
        self.assertLess(start - guard, 400)
        self.assertEqual(source.count("on_route=route_moment"), 1)  # record_run solo avisa con el video en curso


# ── V1–V5 · La prueba completa con la capa falsa de adb ──────────────────────

class TestRunVideoTest(CaptureBase):
    def setUp(self):
        super().setUp()
        self.plan_with(flujo={"video_cola_s": 0, "segmentos": [
            {"nombre": "cargar_lista", "titulo": "Cargar la lista", "desde": {"marca": "SCREEN MainActivity*"},
             "hasta": {"marca": "HTTP GET items/*", "punto": "fin"}}]})
        self.env["FAKE_DATE"] = "1700000000.000000000"
        self.env["FAKE_TP_POR_CONSULTA"] = json.dumps({"reloj": '"ts","clock_name","clock_value"\n0,"REALTIME",%d\n'
                                                                % (1700000000 * 10 ** 9)})

    def test_la_prueba_deja_el_video_en_tramos_con_su_visor(self):
        out = self.ok("capturar", "--plan", self.plan, "--prueba")
        work = self.folder / "video" / "home"
        self.assertTrue((work / "parte1.mp4").is_file())
        events = json.loads((work / "eventos.json").read_text(encoding="utf-8"))
        self.assertEqual(events["tramos_video"], [{"archivo": "video/home/parte1.mp4", "inicio": 0.0}])
        self.assertEqual(events["grabador"], "screenrecord")
        self.assertEqual(events["fases"][0]["rotulo"], "Preparación · no se mide")
        self.assertEqual(events["fases"][-1]["hasta"], events["duracion"])
        # con la hora del dispositivo y el ClockSnapshot de la traza; "aproximada" solo si la máquina tardó más de 2 s
        # entre `date` y el inicio de Perfetto (un CI muy cargado)
        self.assertIn(events["alineacion"]["marcas"], ("ok", "aproximada"))
        self.assertNotIn("ClockSnapshot", events["alineacion"]["detalle"])
        page = self.folder / "prueba-home.html"
        self.assertEqual(perf.embedded_events(page.read_text(encoding="utf-8")), events)
        self.assertIn("Video de la prueba: %s (visor" % page, out)
        self.assertIn("· Sin ffmpeg (opcional)", out)
        self.assertIn("video --carpeta", out)
        self.assertLess(out.index("Video de la prueba"), out.rindex("Siguiente"))  # el paso siguiente va al final
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn('"date +%s.%N"', log)
        self.assertLess(log.index("date +%s.%N"), log.index("screenrecord"))  # la hora, antes de grabar
        self.assertLess(log.index("screenrecord"), log.index("perfetto"))  # el video empieza antes de la traza
        sql = (self.dir / "tp.sql").read_text(encoding="utf-8")
        self.assertIn("FROM clock_snapshot", sql)

    def test_siguiente_y_el_comando_video(self):
        self.ok("capturar", "--plan", self.plan, "--prueba")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Mira el video de la corrida de prueba (%s)" % (self.folder / "prueba-home.html"), out)
        again = self.ok("video", "--carpeta", self.folder)
        self.assertIn("Video de la prueba: %s" % (self.folder / "prueba-home.html"), again)
        write(self.folder / "prueba-home.mp4", "video de otra prueba")  # sin "unido" en eventos.json: no se muestra
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Mira el video de la corrida de prueba (%s)" % (self.folder / "prueba-home.html"), out)
        events_path = self.folder / "video" / "home" / "eventos.json"
        events = json.loads(events_path.read_text(encoding="utf-8"))
        events["unido"] = {"archivo": "prueba-home.mp4", "rotulado": True}  # como lo deja ffmpeg al unirlo
        events_path.write_text(json.dumps(events), encoding="utf-8")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Mira el video de la corrida de prueba (%s)" % (self.folder / "prueba-home.mp4"), out)

    def test_sin_video_no_graba(self):
        self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertNotIn("screenrecord", (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.assertFalse((self.folder / "video").exists())

    def test_video_sin_ninguna_prueba_da_el_paso(self):
        result = self.perf("video", "--carpeta", self.folder)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lo graba la corrida de prueba", result.stderr + result.stdout)
        self.assertIn("siguiente --carpeta", result.stderr + result.stdout)


# ── V5 · El reporte técnico enlaza el video; el de gerencia, no ──────────────

class ReportVideoLinkTest(ReportFixtureBase):
    def test_que_se_midio_enlaza_el_video(self):
        write(self.folder / "prueba-detalle.html", "visor")
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        dev = (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        business = (self.folder / "reporte-inicial-gerencia.html").read_text(encoding="utf-8")
        self.assertIn('<a href="prueba-detalle.html">prueba-detalle.html</a>', dev)
        self.assertNotIn("prueba-detalle", business)
        self.assertNotIn("<video", dev)  # solo el enlace: nunca se incrusta


# ── V6 · Requisitos ──────────────────────────────────────────────────────────

class VideoToolsTest(unittest.TestCase):
    def test_instalar_ffmpeg_sin_root_ni_dev_setup(self):
        steps = perf.ffmpeg_install_steps("darwin", "arm64", "/opt/homebrew/bin/brew")
        self.assertEqual(steps[0][1], "cd ~ && brew install ffmpeg-full")
        static = steps[1][1]
        for piece in ("macos/arm64/release/ffmpeg.zip", "%{redirect_url}", '"$url.sha256"',
                      "shasum -a 256 -c ffmpeg.zip.sha256", "test ! -e ~/.local/bin/ffmpeg", "cp ffmpeg ~/.local/bin/ffmpeg"):
            self.assertIn(piece, static)
        self.assertTrue(static.startswith('cd "$(mktemp -d)" && '))
        linux = perf.ffmpeg_install_steps("linux", "x86_64", "")
        self.assertEqual(len(linux), 1)
        self.assertIn("linux/amd64/release/ffmpeg.zip", linux[0][1])
        self.assertIn("sha256sum -c ffmpeg.zip.sha256", linux[0][1])
        for _, command in steps + linux:
            for forbidden in ("sudo", ">>", "export PATH", ".zshrc", ".bashrc", ".profile"):
                self.assertNotIn(forbidden, command)

    def test_setup_estado_los_muestra_como_opcionales(self):
        with mock.patch.dict(os.environ, {"FFMPEG": "", "SCRCPY": ""}):
            lines = perf.optional_video_tools()
        text = "\n".join(lines)
        self.assertIn("· ffmpeg (opcional", text)
        self.assertIn("ffmpeg -hide_banner -filters", text)
        self.assertIn("command -v ffmpeg", text)
        self.assertIn("· scrcpy (opcional", text)
        self.assertIn("brew install scrcpy", text)

    def test_la_prueba_sin_ffmpeg_da_el_paso(self):
        with TempDir() as folder:
            lines = perf.ffmpeg_hint(folder, folder / "inv", "home")
        self.assertTrue(lines[0].startswith("· Sin ffmpeg (opcional)"))
        self.assertIn("cd ", lines[1])
        self.assertTrue(lines[2].endswith("video --carpeta inv --flujo home"))


# ── Hallazgos del doble check: rutas relativas, videos viejos y errores del video ──

FAKE_FFMPEG = """#!/bin/sh
case "$2" in
  -filters) printf '%s\\n' ' T.. drawbox    V->V  Draw a box.' {drawtext}; exit 0;;
  -encoders) printf '%s\\n' ' V....D libx264   libx264 H.264'; exit 0;;
  -i) echo '  Stream #0:0[0x1](und): Video: h264 (High), yuv420p(tv, bt709, progressive), 1080x2400, 60 fps' >&2; exit 1;;
esac
for a; do last=$a; done
printf 'video unido' > "$last"
"""


def fake_ffmpeg(folder, drawtext=True):
    path = Path(folder) / ("ffmpeg" if drawtext else "ffmpeg-sin-drawtext")
    write(path, FAKE_FFMPEG.replace("{drawtext}", "' T.C drawtext   V->V  Draw text.'" if drawtext else ""))
    path.chmod(0o755)
    return str(path)


class JoinRelativeFolderTest(CaptureBase):
    """`capturar --plan <rel>/plan.json` y `video --carpeta <rel>`: ffmpeg corre en la carpeta de los tramos y la salida
    tiene que ir con su ruta absoluta."""

    def setUp(self):
        super().setUp()
        write(self.dir / "fuente.ttf", "fuente")
        self.plan_with(flujo={"video_cola_s": 0, "video_fuente": str(self.dir / "fuente.ttf")})
        self.ok("capturar", "--plan", self.plan, "--prueba")

    def test_une_con_la_carpeta_relativa(self):
        self.env["FFMPEG"] = fake_ffmpeg(self.dir)
        out = self.ok("video", "--carpeta", "inv")
        self.assertEqual((self.folder / "prueba-home.mp4").read_text(encoding="utf-8"), "video unido")
        self.assertIn("Video de la prueba: inv/prueba-home.mp4", out)
        events = json.loads((self.folder / "video" / "home" / "eventos.json").read_text(encoding="utf-8"))
        self.assertEqual(events["unido"], {"archivo": "prueba-home.mp4", "rotulado": True})
        self.assertEqual(perf.embedded_events((self.folder / "prueba-home.html").read_text(encoding="utf-8")), events)
        self.assertEqual(perf.test_videos(self.folder), [self.folder / "prueba-home.mp4"])
        self.assertIn("Siguiente", out)

    def test_sin_drawtext_da_el_paso_para_los_rotulos(self):
        self.env["FFMPEG"] = fake_ffmpeg(self.dir, drawtext=False)
        out = self.ok("video", "--carpeta", "inv")
        self.assertIn("Video de la prueba: inv/prueba-home.html (visor", out)
        self.assertIn("quedó sin rótulos: ese ffmpeg no trae drawtext", out)
        self.assertIn("instala un ffmpeg con drawtext", out)
        self.assertIn("y únelo de nuevo, sin repetir la prueba:", out)
        self.assertEqual(perf.test_videos(self.folder), [self.folder / "prueba-home.html"])  # el visor sí tiene rótulos


class StaleVideoTest(unittest.TestCase):
    def test_un_mp4_de_una_prueba_anterior_no_se_muestra(self):
        with TempDir() as folder:
            write(folder / "prueba-home.mp4", "de la prueba anterior")
            write(folder / "prueba-home.html", "visor")
            write(folder / "video" / "home" / "eventos.json", json.dumps({"duracion": 3}))  # la de ahora no unió
            self.assertEqual(perf.test_videos(folder), [folder / "prueba-home.html"])
            write(folder / "video" / "home" / "eventos.json", json.dumps({"unido": {"rotulado": True}}))
            self.assertEqual(perf.test_videos(folder), [folder / "prueba-home.mp4"])
            write(folder / "prueba-viejo.mp4", "0.16.0")  # una prueba de 0.16.0, sin eventos.json
            self.assertIn(folder / "prueba-viejo.mp4", perf.test_videos(folder))

    def test_las_fases_de_0160_se_completan_sin_repetirlas(self):
        for version in ("0.15.1", "0.16.0", perf.VERSION):
            self.assertTrue(perf.same_capture(version), version)


class StubRecorder:
    kind, cut, limit = "screenrecord", False, 180

    def __init__(self, pulled, starts, fail=False):
        self.pulled, self.starts_, self.fail, self.ended, self.stopped = pulled, starts, fail, 1100.0, False

    def stop(self, target=None, names=None):
        if self.fail:
            raise RuntimeError("adb se desconectó")
        return [names(number) for number in self.pulled if write(names(number), "x") is None]

    def starts(self):
        return self.starts_, True

    def stop_recording(self):
        self.stopped = True


class CollectAndErrorsTest(unittest.TestCase):
    def video(self, folder, recorder):
        video = perf.TestVideo(folder, {}, {}, "home", FakeAdb(), "")
        video.recorder = recorder
        return video

    def test_cada_tramo_conserva_su_inicio_aunque_falte_uno_del_medio(self):
        with TempDir() as folder:
            video = self.video(folder, StubRecorder([1, 3], [1000.0, 1180.5, 1361.0]))
            video.collect()
            self.assertEqual([part.name for part in video.parts], ["parte1.mp4", "parte3.mp4"])
            self.assertEqual(video.starts, [1000.0, 1361.0])

    def test_un_error_del_video_no_detiene_la_prueba(self):
        import contextlib
        import io
        with TempDir() as folder:
            video = self.video(folder, StubRecorder([1], [1000.0], fail=True))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                video.assemble()  # no levanta la excepción
            self.assertIn("No pude armar el video de la prueba (adb se desconectó)", out.getvalue())

    def test_scrcpy_que_no_arranca_pasa_a_screenrecord(self):
        import contextlib
        import io
        with TempDir() as folder:
            fake = folder / "scrcpy"
            write(fake, "#!/bin/sh\ncase \"$1\" in --help) echo '--no-playback --no-window --record'; exit 0;; esac\n"
                        "echo 'ERROR: Could not find any ADB device'; exit 1\n")
            fake.chmod(0o755)
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"SCRCPY": str(fake)}), contextlib.redirect_stdout(out):
                video = perf.TestVideo(folder, {}, {"video_grabador": "scrcpy"}, "home",
                                       FakeAdb(["sh", "-c", "exit 0", "x"]), "").start()
            self.assertEqual(video.recorder.kind, "screenrecord")
            self.assertIn("scrcpy no empezó a grabar", out.getvalue())
            video.collect()


class VideoCommandErrorsTest(CaptureBase):
    def test_un_eventos_json_incompleto_da_el_paso(self):
        write(self.folder / "video" / "home" / "eventos.json", json.dumps({"fases": []}))
        result = self.perf("video", "--carpeta", self.folder)
        self.assertNotEqual(result.returncode, 0)
        text = result.stdout + result.stderr
        self.assertIn("no trae los tramos de video", text)
        self.assertIn("--prueba", text)
        self.assertNotIn("Traceback", text)


# ── V3 · Con ffmpeg de verdad (se salta sin él) ──────────────────────────────

FFMPEG = shutil.which("ffmpeg")
FFMPEG_OK = bool(FFMPEG) and bool(perf.ffmpeg_features(FFMPEG)["codificador"])
SKIP = "sin ffmpeg con un codificador H.264 en esta máquina: estos tests corren en el CI de Ubuntu"


def make_part(path, color, seconds, size="270x480"):
    encoder = perf.ffmpeg_features(FFMPEG)["codificador"]
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=%s:s=%s:r=30:d=%s" % (color, size, seconds)] + perf.encoder_args(encoder) +
                   ["-pix_fmt", "yuv420p", str(path)], check=True)


def probe(path):
    """(ancho, alto, duración) con ffprobe si está; si no, con lo que imprime ffmpeg -i."""
    if shutil.which("ffprobe"):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height:format=duration", "-of", "json", str(path)],
                             capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
        return data["streams"][0]["width"], data["streams"][0]["height"], float(data["format"]["duration"])
    width, height = perf.video_size(FFMPEG, path)
    found = re.search(r"Duration: (\d+):(\d+):([\d.]+)", subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                                                                         capture_output=True, text=True).stderr)
    return width, height, int(found.group(1)) * 3600 + int(found.group(2)) * 60 + float(found.group(3))


def pixel(path, seconds, x, y):
    """El color (r, g, b) de un punto de un cuadro del video."""
    width = probe(path)[0]
    raw = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(path),
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True,
                         check=True).stdout
    start = (y * width + x) * 3
    return tuple(raw[start:start + 3])


def close(color, hex_color, tolerance=40):
    expected = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return all(abs(a - b) <= tolerance for a, b in zip(color, expected))


@unittest.skipUnless(FFMPEG_OK, SKIP)
class FfmpegRealTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        work = self.folder / "video" / "home"
        work.mkdir(parents=True)
        make_part(work / "parte1.mp4", "0x20a050", 2)
        make_part(work / "parte2.mp4", "0x8030c0", 2)
        self.events = {"version": 1, "flujo": "home", "grabador": "screenrecord", "duracion": 4.0,
                       "tramos_video": [{"archivo": "video/home/parte1.mp4", "inicio": 0.0},
                                        {"archivo": "video/home/parte2.mp4", "inicio": 2.0}],
                       "fases": [{"desde": 0.0, "hasta": 1.5, "rotulo": "Preparación · no se mide", "tipo": "prep"},
                                 {"desde": 1.5, "hasta": 3.5, "rotulo": "Medición · Pedidos", "tipo": "med"},
                                 {"desde": 3.5, "hasta": 4.0, "rotulo": "Fin de la prueba", "tipo": "fin"}],
                       "marcas": [{"t": 1.6, "nombre": "MARK pedidos_visible"}], "alineacion": {"marcas": "ok"}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_une_y_rotula_sin_tocar_la_imagen(self):
        if perf.video_font({}, {}) is None or not perf.ffmpeg_features(FFMPEG)["drawtext"]:
            self.skipTest("ffmpeg sin drawtext o sin una fuente del sistema")
        result = perf.join_test_video(self.folder, self.events, {}, {}, FFMPEG)
        self.assertTrue(result["rotulado"], result)
        video = self.folder / "prueba-home.mp4"
        self.assertEqual(result["video"], video)
        head, foot = perf.even(perf.VIDEO_HEAD * 0.5), perf.even(perf.VIDEO_FOOT * 0.5)
        width, height, duration = probe(video)
        self.assertEqual((width, height), (270, 480 + head + foot))
        self.assertAlmostEqual(duration, 4.0, delta=0.3)
        self.assertTrue(close(pixel(video, 1.0, 135, 300), "20a050"))  # la imagen del teléfono, tal cual
        self.assertTrue(close(pixel(video, 2.6, 135, 300), "8030c0"))
        self.assertTrue(close(pixel(video, 1.0, 250, 5), "6b7380"))  # la banda de arriba: preparación en gris
        self.assertTrue(close(pixel(video, 2.6, 250, 5), "3657d6"))  # medición en azul
        self.assertTrue((self.folder / "video" / "home" / "parte1.mp4").is_file())  # los tramos originales quedan

    def test_sin_fuente_une_los_tramos_sin_rotulos(self):
        result = perf.join_test_video(self.folder, self.events, {}, {"video_fuente": str(self.folder / "no.ttf")}, FFMPEG)
        self.assertFalse(result["rotulado"])
        self.assertIn("video_fuente", result["motivo"])
        width, height, duration = probe(result["video"])
        self.assertEqual((width, height), (270, 480))
        self.assertAlmostEqual(duration, 4.0, delta=0.3)

    def test_el_comando_video_arma_el_mp4_sin_repetir_la_prueba(self):
        work = self.folder / "video" / "home"
        (work / "eventos.json").write_text(json.dumps(self.events), encoding="utf-8")
        write(self.folder / "plan.json", json.dumps({"paquete": "com.example.app", "flujos": {"home": {}}}))
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "video", "--carpeta", str(self.folder)],
                              cwd=str(self.folder), env=dict(os.environ, FFMPEG=FFMPEG), capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Video de la prueba: %s" % (self.folder / "prueba-home.mp4"), done.stdout)
        self.assertTrue((self.folder / "prueba-home.html").is_file())


if __name__ == "__main__":
    unittest.main()
