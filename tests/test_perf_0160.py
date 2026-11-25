"""Tests de hb-performance 0.16.0: retomar y recuperar (A), compilar, probar y leer la red (B), punto de partida y
prueba (C), sesiones de IA (E), `siguiente` sin callejones (S), costo (F) y reportes (R). Los datos son inventados."""
import datetime
import json
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

from helpers import ENV, ROOT, commit_all, git, init_repo, perf_argv, write
from test_perf import GOOD, DeviceBase, PerfBase, perf
from test_perf_0150 import commands_in, run_shell

SKILL = ROOT / "skills" / "hb-performance"
SCRIPT = SKILL / "scripts" / "perf.py"


def dead_pid():
    """El número de un proceso que ya terminó (el de un comando cortado)."""
    done = subprocess.run(["/bin/sh", "-c", "echo $$"], capture_output=True, text=True)
    return int(done.stdout.strip())


class CaptureBase(DeviceBase):
    """Una investigación con el adb y el trace_processor falsos: un flujo automático de 10 corridas por fase."""

    def setUp(self):
        super().setUp()
        self.folder = self.plan.parent
        self.tp_outputs(GOOD)

    def plan_with(self, **fields):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        flow = fields.pop("flujo", None) or {}
        plan["flujos"]["home"].update(flow)
        plan.update(fields)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        return plan

    def capture(self, *extra, phase="antes", runs=3):
        return self.ok("capturar", "--plan", self.plan, "--fase", phase, "--corridas", runs, "--calentamiento", "0",
                       "--sin-compilar", *extra)

    def csv_runs(self, phase="antes"):
        return perf.csv_runs(self.folder, phase, "home")

    def phases(self):
        return json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))

    def run_pasted(self, command):
        """Corre un comando tal como lo imprime la skill (cd … && python3 -I …)."""
        done = run_shell(command, self.env)
        self.assertEqual(done.returncode, 0, command + "\n" + done.stdout + done.stderr)
        return done.stdout


# ── A · Retomar y recuperar ──────────────────────────────────────────────────

class RecoverCountCase(CaptureBase):
    """A1–A3: tras un corte, `recuperar` cuenta desde metricas.csv y la fase termina con exactamente las del plan."""

    def cut_after(self, valid, record_valid, partial=False, perfetto=None):
        """Simula una tanda de 10 que dejó `valid` corridas en metricas.csv y se cortó: fases.json sin esa tanda y el
        registro de lo que estaba en curso con `record_valid` válidas (0.15.1 lo dejaba atrasado en una)."""
        self.capture(runs=valid)
        phases = self.phases()
        phases.pop("antes")
        (self.folder / "fases.json").write_text(json.dumps(phases), encoding="utf-8")
        trace = self.folder / "antes" / ("home_%d.perfetto-trace" % (valid + 1))
        if partial:
            write(trace, "a medias")
        write(self.folder / ".en-curso.json", json.dumps({
            "comando": "capturar", "fase": "antes", "flujo": "home", "corrida": record_valid + 1, "objetivo": 10,
            "validas": record_valid, "inicio_corridas": 0, "traza": str(trace) if partial else None, "pid": dead_pid(),
            "inicio": "2026-03-02T10:00:00", "registro": {"fecha": "2026-03-02T10:00:00", "corridas": record_valid,
                                                          "skill": perf.VERSION, "commit": None},
            "perfetto": perfetto}))
        return trace

    def finish(self, out_recover):
        self.assertIn("Corridas válidas de antes · home: 3 (las que tienen filas en metricas.csv); el plan pide 10: "
                      "faltan 7", out_recover)
        record = self.phases()["antes"]
        self.assertEqual(record["corridas"], 3)
        self.assertEqual(record["faltan"], {"home": 7})
        out = self.ok("siguiente", "--carpeta", self.folder)
        command = next(line for line in commands_in(out) if "capturar" in line)
        self.assertIn("--fase antes --corridas 7", command)
        out = self.run_pasted(command.replace("--corridas 7", "--corridas 7 --calentamiento 0 --sin-compilar"))
        self.assertIn("corrida 4 de 10", out)
        self.assertIn("corrida 10 de 10", out)
        self.assertNotIn("de 11", out)
        self.assertEqual(self.csv_runs(), list(range(1, 11)))
        record = self.phases()["antes"]
        self.assertEqual(record["corridas"], 10)
        self.assertNotIn("faltan", record)


class RecoverCountTest(RecoverCountCase):
    """0.16.0 · K: la primera mitad de los tests, para que la suite se reparta (la otra mitad está en RecoverCountMoreTest)."""

    def test_corte_entre_corridas_con_el_registro_atrasado(self):
        self.cut_after(3, 2)
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("se interrumpió buscando la corrida 4 (3 válidas en metricas.csv)", out)
        out = self.ok("recuperar", "--carpeta", self.folder)
        self.assertIn("Perfetto: no quedó registrado grabando", out)
        self.assertIn("Traza parcial: no había", out)
        self.assertNotIn("None", out)
        self.finish(out)

    def test_corte_en_medio_de_una_corrida(self):
        trace = self.cut_after(3, 3, partial=True, perfetto={"pid": "4242", "remota": "/data/misc/perfetto-traces/"
                                                             "hbperf-9.perfetto-trace", "serial": "emulator-5554"})
        self.env["FAKE_PERFETTO_VIVA"] = "1"
        out = self.ok("recuperar", "--carpeta", self.folder)
        self.assertIn("Perfetto: detenido (proceso 4242) y traza borrada del dispositivo", out)
        self.assertRegex(out, r"Traza parcial home_4\.perfetto-trace apartada en .*antes-descartada-\d+/")
        self.assertFalse(trace.exists())
        del self.env["FAKE_PERFETTO_VIVA"]
        self.finish(out)

    def test_sin_numero_de_perfetto_lo_busca_por_nombre(self):
        self.cut_after(3, 3, perfetto={"pid": None, "remota": None, "serial": "emulator-5554"})
        out = self.ok("recuperar", "--carpeta", self.folder)
        self.assertIn("el registro no guardó su número de proceso; lo busco por nombre", out)
        self.assertIn("Perfetto: no seguía grabando", out)
        self.assertNotIn("proceso None", out)
        self.assertIn("pidof perfetto", (self.dir / "adb.log").read_text(encoding="utf-8"))

    def test_completar_con_mas_corridas_de_las_que_faltan_se_ajusta_al_plan(self):
        self.cut_after(3, 3)
        self.ok("recuperar", "--carpeta", self.folder)
        out = self.capture(runs=8)
        self.assertIn("mido 7 (no 8), así la fase termina con exactamente las del plan", out)
        self.assertIn("corrida 4 de 10", out)
        self.assertEqual(self.csv_runs(), list(range(1, 11)))


class RecoverCountMoreTest(RecoverCountCase):
    """0.16.0 · K: la segunda mitad de los tests, para que la suite se reparta (la otra mitad está en RecoverCountTest)."""

    def test_el_registro_se_actualiza_al_empezar_y_al_terminar_cada_corrida(self):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("        attempts += 1\n        failure = None\n")
        self.assertLess(start, source.index("mark_running(folder, comando=\"capturar\"", start))
        self.assertLess(source.index("mark_running(folder, comando=\"capturar\"", start),
                        source.index("                timed_prepare()\n", start))  # 0.17.0: 'preparar' con su hora
        self.assertIn("perfetto={\"pid\": pid, \"remota\": remote, \"serial\": serial}\n"
                      "                                                   if pid else None", source)

    def test_faltan_viejo_con_la_fase_completa_no_mide_de_mas(self):
        self.capture(runs=10)
        phases = self.phases()
        phases["antes"]["faltan"] = {"home": 1}  # un registro atrasado (el recuperar de 0.15.1)
        (self.folder / "fases.json").write_text(json.dumps(phases), encoding="utf-8")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertNotIn("--fase antes --corridas 1", out)
        out = self.capture(runs=1)
        self.assertIn("ya tiene las 10 corridas válidas del plan en metricas.csv (10): no mido más", out)
        self.assertEqual(self.csv_runs(), list(range(1, 11)))
        self.assertNotIn("faltan", self.phases()["antes"])

    def test_simular_dice_que_haria_sin_tocar_nada(self):
        trace = self.cut_after(3, 3, partial=True, perfetto={"pid": "4242", "remota": "/data/misc/perfetto-traces/"
                                                             "hbperf-9.perfetto-trace", "serial": "emulator-5554"})
        self.env["FAKE_PERFETTO_VIVA"] = "1"
        (self.dir / "adb.log").write_text("", encoding="utf-8")  # solo lo que hace `recuperar`
        out = self.ok("recuperar", "--carpeta", self.folder, "--simular")
        self.assertIn("Qué haría (simulación, sin tocar nada):", out)
        self.assertIn("Perfetto: lo detendría (proceso 4242) y borraría su traza del dispositivo", out)
        self.assertIn("Traza parcial: la apartaría en", out)
        self.assertTrue(trace.exists())
        self.assertNotIn("kill -TERM", (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.assertTrue(commands_in(out)[-1].endswith("recuperar --carpeta %s" % self.folder), out)

    def test_registro_viejo_sin_numero_ni_dispositivo_sigue_y_cuenta(self):
        self.cut_after(3, 2, perfetto={"pid": None, "remota": None, "serial": "emulator-5554"})
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("Perfetto pudo quedar grabando en el dispositivo, sin número de proceso registrado", out)
        self.env["FAKE_LISTA"] = " "
        out = self.ok("recuperar", "--carpeta", self.folder)
        self.assertIn("no hay dispositivo para buscarlo", out)
        self.assertIn("Corridas válidas de antes · home: 3", out)
        self.assertEqual(self.phases()["antes"]["faltan"], {"home": 7})


class ModulePrintTest(CaptureBase):
    """A4: la huella de los módulos por fase, el aviso entre fases y el mapa del plan."""

    GRADLE = ("#!/bin/sh\necho \"$@\" >> \"$GRADLE_LOG\"\ncat \"$GRADLE_DEPS\"\n")
    DEPS_BINARY = ("releaseRuntimeClasspath - Runtime classpath\n+--- project :feature:pedidos\n"
                   "\\--- com.example:pagos:1.2.0\n")
    DEPS_CODE = ("releaseRuntimeClasspath - Runtime classpath\n+--- project :feature:pedidos\n"
                 "\\--- com.example:pagos:1.2.0 -> project :pagos\n")

    def setUp(self):
        super().setUp()
        gradlew = self.dir / "gradlew"
        write(gradlew, self.GRADLE)
        gradlew.chmod(0o755)
        self.deps = self.dir / "deps.txt"
        write(self.deps, self.DEPS_BINARY)
        self.env.update(GRADLE_LOG=str(self.dir / "gradle.log"), GRADLE_DEPS=str(self.deps))
        self.plan_with(instalar="./gradlew :app:installRelease", modulos=[
            {"nombre": ":pagos", "tipo": "binario", "proyecto": ":pagos", "motivo": "aquí está el toque de Pagar"}])

    def test_la_huella_queda_por_fase_sin_red_y_comparar_avisa_si_cambia(self):
        self.capture(runs=3)
        record = self.phases()["antes"][perf.MODULE_PRINT]
        self.assertEqual(record["fuente"], "gradle")
        self.assertEqual(record["proyectos"], [":feature:pedidos"])
        self.assertIn("--offline", (self.dir / "gradle.log").read_text(encoding="utf-8"))
        write(self.deps, self.DEPS_CODE)
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"  # el build nuevo, instalado después de medir antes
        out = self.capture(phase="despues", runs=3)
        self.assertIn("la huella de los módulos cambió desde la fase antes (:pagos pasó a compilarse desde código)", out)
        out = self.ok("comparar", self.folder / "metricas.csv")
        self.assertIn("la huella de los módulos cambió entre antes y despues (:pagos pasó a compilarse desde código): "
                      "la comparación deja de ser igual contra igual", out)

    def test_sin_gradle_usa_el_mapa_del_plan(self):
        (self.dir / "gradlew").unlink()
        self.capture(runs=3)
        self.assertEqual(self.phases()["antes"][perf.MODULE_PRINT],
                         {"fuente": "plan", "modulos": [":pagos=binario"]})

    def test_antes_de_medir_un_cambio_solo_propone_actualizar_el_mapa(self):
        write(self.deps, self.DEPS_CODE)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("El mapa de módulos del plan quedó viejo: :pagos ahora es código (el plan dice binario (llega "
                      "compilado))", out)
        self.assertEqual(self.phases()["prueba"]["mapa_viejo"], [[":pagos", "binario", "codigo"]])
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("--comprobar-modulos", out)

    def test_sin_red_la_huella_sale_del_mapa_y_no_se_compara_con_otra_fuente(self):
        self.capture(runs=3)
        write(self.dir / "gradlew", "#!/bin/sh\necho 'Could not resolve' >&2\nexit 1\n")
        self.env["FAKE_UPDATED"] = "2026-11-06 09:00:00"
        out = self.capture(phase="despues", runs=3)
        self.assertIn("Gradle no respondió sin red: la huella de los módulos sale del mapa del plan", out)
        self.assertIn("no se puede comparar: una huella salió de Gradle y la otra del mapa del plan", out)

    def test_el_modulo_app_y_lo_que_no_sale_en_el_classpath_no_cambian_de_tipo(self):
        plan = {"instalar": "./gradlew :app:installRelease", "modulos": [
            {"nombre": ":app", "tipo": "codigo", "proyecto": ":app"},
            {"nombre": ":feature:pedidos", "tipo": "codigo", "proyecto": ":feature:pedidos"},
            {"nombre": ":pagos", "tipo": "codigo", "proyecto": ":pagos"}]}
        current = {"fuente": "gradle", "proyectos": [":feature:pedidos"], "binarios": []}
        self.assertEqual(perf.map_outdated(plan, current), [])
        current["binarios"] = [":pagos"]
        self.assertEqual(perf.map_outdated(plan, current), [(":pagos", "codigo", "binario")])

    def test_huella_apagada_en_el_plan(self):
        self.plan_with(huella_modulos=False)
        self.capture(runs=3)
        self.assertNotIn(perf.MODULE_PRINT, self.phases()["antes"])
        self.assertFalse((self.dir / "gradle.log").exists())



# ── B · Compilar, probar y leer la red ───────────────────────────────────────

class BuildAndApkTest(CaptureBase):
    """B1 y B2: un build que no compiló y un APK anterior a las marcas nunca mandan a revisar el código."""

    def setUp(self):
        super().setUp()
        self.source = self.dir / "app" / "src" / "main" / "kotlin" / "Pedidos.kt"
        write(self.source, "class Pedidos {\n    fun abrir() { MarkTrace.mark(\"pedidos_visibles\") }\n}\n")
        self.plan_with(instalar="./instalar.sh", flujo={"metricas_usuario": [
            {"nombre": "abrir_ms", "desde": {"marca": "SCREEN MainActivity"},
             "hasta": {"marca": "MARK pedidos_visibles"}}]})

    def installer(self, code, output):
        script = self.dir / "instalar.sh"
        write(script, "#!/bin/sh\necho 'Starting a Gradle Daemon'\nprintf '%s'\nexit %d\n" % (output, code))
        script.chmod(0o755)

    def test_build_fallido_registra_la_primera_linea_y_siguiente_pide_compilar(self):
        self.installer(1, "FAILURE: Build failed with an exception.\\n\\n* What went wrong:\\nCould not resolve "
                          "com.example:pagos:1.2.0 (repositorio de artefactos inaccesible)\\n")
        result = self.perf("instalar", "--carpeta", self.folder)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compilación fallida: Could not resolve com.example:pagos:1.2.0 (repositorio de artefactos "
                      "inaccesible)", result.stdout + result.stderr)
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("compilación fallida: Could not resolve com.example:pagos:1.2.0", out)
        first = commands_in(out)[0]
        self.assertIn("instalar --carpeta", first)
        self.assertNotIn("Chat nuevo", out.split("2.")[0])
        self.assertNotIn("revisa dónde se emite", out)
        result = self.perf("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("la última compilación falló", result.stdout + result.stderr)
        self.installer(0, "BUILD SUCCESSFUL\\n")
        self.env["FAKE_UPDATED"] = "2099-01-01 10:00:00"
        out = self.ok("instalar", "--carpeta", self.folder)
        self.assertIn("✔ Compiló e instaló", out)
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertNotIn("compilación fallida", out)

    def test_apk_anterior_a_las_marcas_no_propone_un_chat(self):
        os.utime(str(self.source), (4102444800, 4102444800))  # 2100-01-01: la marca es posterior al APK instalado
        self.tp_outputs(GOOD)  # GOOD no trae MARK pedidos_visibles: la marca falta
        result = self.perf("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        out = result.stdout + result.stderr
        self.assertIn("el APK instalado es anterior a las marcas: compila e instala antes", out)
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("el APK instalado es anterior a las marcas", out)
        self.assertNotIn("Chat nuevo", out)
        self.assertNotIn("revisa dónde se emite", out)
        self.assertIn("instalar --carpeta", commands_in(out)[0])

    def test_con_una_mejora_aplicada_un_apk_viejo_pide_instalar_y_no_ajustar_marcas(self):
        plan = self.plan_with()
        plan["mejoras"] = [{"id": "M1", "titulo": "Pedir antes", "estado": "aplicada", "aplicada_en": "2000-01-01T00:00:00",
                           "metrica": "abrir_ms"}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        os.utime(str(self.source), (946684800, 946684800))
        self.capture(runs=3)
        os.utime(str(self.source), (4102444800, 4102444800))  # la marca (o la mejora) cambió después de instalar
        self.perf("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("el APK instalado es anterior", out)
        self.assertNotIn("Chat nuevo", out)
        self.assertIn("instalar --carpeta", commands_in(out)[0])

    def test_con_todas_las_marcas_y_el_apk_viejo_no_ofrece_medir_despues(self):
        plan = self.plan_with()
        plan["mejoras"] = [{"id": "M1", "titulo": "Pedir antes", "estado": "aplicada", "aplicada_en": "2000-01-01T00:00:00",
                            "metrica": "abrir_ms"}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        os.utime(str(self.source), (946684800, 946684800))
        self.capture(runs=3)
        os.utime(str(self.source), (4102444800, 4102444800))
        self.tp_outputs(GOOD + '"seccion",600000000,0,0,"MARK pedidos_visibles"\n')  # todas las marcas salen
        self.perf("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertNotIn("--fase despues", out)
        self.assertIn("instalar --carpeta", commands_in(out)[0])

    def test_instalar_con_fallo_externo_y_sin_comando_en_el_plan(self):
        out = self.perf("instalar", "--carpeta", self.folder, "--fallo", "Could not resolve com.example:pagos:1.2.0")
        self.assertIn("Anotado: compilación fallida: Could not resolve", out.stdout)
        plan = self.plan_with()
        plan.pop("instalar")
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        out = self.ok("siguiente", "--carpeta", self.folder)
        self.assertIn("plan.json no tiene \"instalar\"", out)
        self.assertFalse(any("instalar --carpeta" in command for command in commands_in(out)))
        self.env["FAKE_UPDATED"] = "2099-01-01 10:00:00"  # instalado después del fallo, por otro camino
        self.perf("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertEqual(perf.last_build(self.folder).get("estado"), "ok")

    def test_apk_al_dia_no_avisa(self):
        os.utime(str(self.source), (946684800, 946684800))  # 2000-01-01: anterior al APK
        self.tp_outputs(GOOD)
        result = self.perf("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertNotIn("anterior a las marcas", result.stdout + result.stderr)


LISTENER_NEW = ("// Generated by hb-performance (perf.py instrumentar); `instrumentar --actualizar` overwrites this file.\n"
                "package com.example.app.perf\n\nclass TraceEventListener {\n    companion object {\n"
                "        const val LOG_TAG = \"hb-perf\"\n    }\n}\n")
LISTENER_OLD = ("// Generated by hb-performance (perf.py instrumentar); `instrumentar --actualizar` overwrites this file.\n"
                "package com.example.app.perf\n\nclass TraceEventListener\n")
LOG_LINE = "11-05 10:00:00.000  1234  1234 I hb-perf : servicio\tGET\tGET items/{id}\thttps://api.example.com/ms-items/v1.2/items/7"


class NetworkLogTest(CaptureBase):
    """B3–B6: el log de rutas sin depender del buffer de logcat y avisos con la causa real."""

    def listener(self, text):
        write(self.dir / "app" / "src" / "perf" / "kotlin" / "TraceEventListener.kt", text)
        write(self.dir / "app" / "src" / "perf" / "kotlin" / "PerfHooks.kt",
              "// Generated by hb-performance (perf.py instrumentar)\npackage com.example.app.perf\n")

    def test_instrumentacion_al_dia_sin_rutas_dice_las_causas(self):
        self.listener(LISTENER_NEW)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertNotIn("anterior a 0.11.0", out)
        self.assertIn("la instrumentación de red está al día", out)
        self.assertIn("buffer de logcat", out)
        self.assertIn("assumenosideeffects", out)
        self.assertIn("otro listener", out)

    def test_reglas_de_r8_que_quitan_log(self):
        self.listener(LISTENER_NEW)
        write(self.dir / "app" / "proguard-rules.pro", "-assumenosideeffects class android.util.Log {\n"
                                                      "    public static int i(...);\n}\n")
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("app/proguard-rules.pro", out)

    def test_instrumentacion_vieja_antes_de_medir_es_un_paso(self):
        self.listener(LISTENER_OLD)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("anterior a 0.11.0", out)
        out = self.ok("siguiente", "--carpeta", self.folder)
        commands = commands_in(out)
        self.assertIn("instrumentar", commands[0])
        self.assertIn("--actualizar", commands[0])
        self.assertTrue(any("--prueba" in command for command in commands), out)

    def test_limpia_el_buffer_antes_de_cada_corrida_y_acumula_las_rutas(self):
        self.env["FAKE_LOGCAT_PERF"] = LOG_LINE
        self.capture(runs=2)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertEqual(log.count('"logcat", "-b", "main", "-c"]'), 2)  # solo el buffer main
        self.assertLess(log.index('"logcat", "-d", "-s", "hb-perf"]'), log.index('"logcat", "-b", "main", "-c"]'))
        urls = perf.service_urls(self.folder)
        self.assertEqual(urls["GET items/{id}"], "https://api.example.com/ms-items/v1.2/items/7")
        self.env["FAKE_LOGCAT_PERF"] = ""
        self.capture(phase="control", runs=1)
        self.assertIn("GET items/{id}", perf.service_urls(self.folder))  # se acumulan, no se pisan

    def test_buffer_chico_se_sube_y_queda_para_revertir(self):
        self.env["FAKE_LOGCAT_G"] = "main: ring buffer is 256 KiB (250 KiB consumed), max entry is 5120 B, max " \
                                    "payload is 4068 B\nsystem: ring buffer is 256 KiB (10 KiB consumed)"
        state = (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8")
        write(self.folder / "estado.md", state)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("buffer de logcat de 256 KiB", out)
        self.assertIn('"logcat", "-b", "main", "-G", "16M"]', (self.dir / "adb.log").read_text(encoding="utf-8"))
        text = (self.folder / "estado.md").read_text(encoding="utf-8")
        cambios = text.split("## Cambios temporales por revertir")[1].split("\n## ")[0]
        self.assertIn("logcat -b main -G 256K", cambios)
        self.assertEqual(perf.temp_changes(text), [])  # no es una fila de archivo: `cerrar` no la toca

    def test_buffer_chico_sin_tocarlo_da_el_comando_y_la_opcion(self):
        self.env["FAKE_LOGCAT_G"] = "main: ring buffer is 256 KiB (250 KiB consumed)"
        self.plan_with(buffer_logcat=False)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertNotIn('"-G"', (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.assertIn("logcat -b main -G 16M", out)
        self.assertIn("Tamaño del búfer del registrador", out)



# ── C · Punto de partida, prueba y lectura de resultados ─────────────────────

NODES_XML = ('<?xml version="1.0"?><hierarchy><node index="0" text="Pedidos" resource-id="" class="android.widget.TextView" '
             'content-desc="" clickable="true" enabled="true" bounds="[0,0][100,100]" /></hierarchy>')


class StartingPointTest(CaptureBase):
    """C1–C5: pantallas que salen solo a veces, tope de intentos, pantalla saltada, pantalla de partida y tabla de la
    prueba."""

    def flaky_prepare(self, expected="Aviso de novedades"):
        """Un 'preparar' que falla en los intentos pares, como una pantalla con límite de frecuencia."""
        counter = self.dir / "intentos.txt"
        script = self.dir / "preparar.sh"
        write(script, "#!/bin/sh\nn=$(cat %s 2>/dev/null || echo 0)\necho $((n+1)) > %s\n"
                      "if [ $((n %% 2)) -eq 1 ]; then echo \"se saltó '%s': la app llegó a 'Pedidos'\" >&2; exit 1; fi\n"
                      % (counter, counter, expected))
        script.chmod(0o755)
        self.plan_with(flujo={"preparar": "sh %s" % script})

    def test_preparar_que_falla_la_mitad_de_las_veces_completa_la_fase_y_dice_que_se_salto(self):
        self.flaky_prepare()
        out = self.capture(runs=5)
        self.assertIn("el tope sube de 8 a 15 intentos", out)
        self.assertEqual(self.csv_runs(), [1, 2, 3, 4, 5])
        self.assertIn("Se saltó 'Aviso de novedades': la app llegó directo a 'Pedidos'", out)
        self.assertNotIn("toca el botón", out)
        logs = sorted(path.name for path in (self.folder / "logs").glob("preparar-antes-intento*.log"))
        self.assertGreaterEqual(len(logs), 4)
        self.assertIn("se saltó 'Aviso de novedades'", (self.folder / "logs" / logs[0]).read_text(encoding="utf-8"))

    def test_una_app_de_una_sola_actividad_trabada_no_se_toma_por_saltada(self):
        script = self.dir / "preparar.sh"
        write(script, "#!/bin/sh\necho \"no apareció 'Aviso de novedades'\" >&2\nexit 1\n")
        script.chmod(0o755)
        self.plan_with(flujo={"preparar": "sh %s" % script})
        result = self.perf("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "3", "--calentamiento", "0",
                           "--sin-compilar")
        self.assertNotIn("Se saltó", result.stdout + result.stderr)  # la actividad es la misma: no se decide por ella
        self.assertIn("'preparar' falló 3 veces dejando la app en la misma pantalla", result.stdout + result.stderr)

    def test_con_otro_motivo_el_tope_no_cambia(self):
        self.assertEqual(perf.max_attempts(10), 15)
        self.assertEqual(perf.max_attempts(10, only_prepare=True), 30)

    def test_trabada_en_otra_pantalla_si_propone_el_toque(self):
        failures = [("'preparar' terminó con código 1", ())] * 2
        lines = perf.invalid_summary(failures, 4, {"LoginActivity": ["Ingresar"]}, ["LoginActivity"] * 2)
        self.assertTrue(any("toca el botón con el texto que se ve en esa pantalla ('Ingresar')" in line for line in lines))
        lines = perf.invalid_summary(failures, 4, {}, [], skipped={("Aviso de novedades", "Pedidos"): 2})
        self.assertTrue(any(line.startswith("⚠ Se saltó 'Aviso de novedades': la app llegó directo a 'Pedidos' (2 veces")
                            for line in lines), lines)
        self.assertFalse(any("toca" in line for line in lines))

    def test_recorrido_comprueba_la_pantalla_de_partida(self):
        self.ok("nuevo", "--carpeta", self.dir / "otra", "--paquete", "com.example.app", "--flujo", "catalogo-lista",
                "--serial", "emulator-5554")
        route = (self.dir / "otra" / "recorrido.sh").read_text(encoding="utf-8")
        first = next(line for line in route.splitlines() if line and not line.startswith(("#", "set ", "SERIAL")))
        self.assertIn("nodos", first)
        self.assertIn("--partida", first)
        self.assertFalse(perf.route_dumps("bash %s" % (self.dir / "otra" / "recorrido.sh"), self.dir / "otra"))
        xml = self.dir / "ui.xml"
        self.env["FAKE_PULL"] = NODES_XML
        result = self.perf("nodos", xml, "--partida", "--texto", "Inicio")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)  # no está: no toca a ciegas
        self.assertIn("no está la pantalla de partida", result.stderr)
        self.assertIn("Pantalla de partida a la vista", self.ok("nodos", xml, "--partida", "--texto", "Pedidos"))
        self.env[perf.CAPTURE_ENV] = "1"  # dentro de una captura no vuelca nada
        (self.dir / "adb.log").write_text("", encoding="utf-8")
        self.ok("nodos", xml, "--partida", "--texto", "Inicio")
        self.assertNotIn("uiautomator", (self.dir / "adb.log").read_text(encoding="utf-8"))

    def test_tabla_de_la_prueba_con_las_del_plan_primero_y_sin_cortar_en_silencio(self):
        flow = {"metricas_usuario": [{"nombre": "abrir_ms"}], "segmentos": [{"nombre": "cargar"}]}
        metrics = [("generica_%02d" % i, i, "ms", "app") for i in range(40)] + [
            ("cargar hilo_max_ms", 5, "ms", "app"), ("abrir_ms", 900, "ms", "e2e")]
        path = self.dir / "prueba" / "home-metricas.md"
        lines = perf.test_table_lines(metrics, flow, path)
        self.assertTrue(lines[2].startswith("| abrir_ms | 900 ms"), lines[:4])
        self.assertTrue(lines[3].startswith("| cargar hilo_max_ms"), lines[:4])
        self.assertEqual(lines[-1], "… 12 filas más en %s" % path)
        self.assertIn("generica_39", path.read_text(encoding="utf-8"))


class FakeAdb:
    """Un adb mínimo para probar lo que corre en el dispositivo sin uno: registra los comandos y baja archivos falsos."""

    def __init__(self, base=None):
        self.base = base or ["true"]
        self.calls = []

    def shell(self, command, stdin=None, timeout=120):
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    def run(self, *args, stdin=None, timeout=120):
        self.calls.append(" ".join(args))
        if args[0] == "pull":
            Path(args[2]).write_bytes(b"x" * 2048)
        return subprocess.CompletedProcess(args, 0, "", "")


class TraceEndAndReadingTest(PerfBase):
    """C6–C10: la traza termina cerca de la última marca, marcas repetidas sin `cual`, lectura del resumen, inicio en un
    toque y video y capturas."""

    def test_la_cola_se_aprende_de_la_prueba_y_queda_fija_para_todas_las_fases(self):
        folder = self.dir / "inv"
        write(folder / "advertencias.json", json.dumps({"cola": {"home": {"ultima_marca_s": 20.0, "traza_s": 45.0}}}))
        flow, prepare = {"recorrido": "bash recorrido.sh"}, "bash preparar.sh"
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "bash recorrido.sh", False, prepare), [30.0, 20.0])
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "bash recorrido.sh", False), [])  # sin 'preparar'
        self.assertEqual(perf.trace_tail(folder, dict(flow, cola_s=0), "home", None, "bash recorrido.sh", False,
                                         prepare), [])
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "manual", False, prepare), [])
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "bash recorrido.sh", True, prepare), [])
        # con una fase medida, vale su corte aunque la prueba nueva aprenda otro
        write(folder / "fases.json", json.dumps({"antes": {"corridas": 3, "flujos": {"home": {"corridas": 3,
                                                                                           "corte_s": 30.0}}}}))
        write(folder / "advertencias.json", json.dumps({"cola": {"home": {"ultima_marca_s": 10.0, "traza_s": 45.0}}}))
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "bash recorrido.sh", False, prepare, "despues"),
                         [30.0, 30.0])
        # una fase medida sin corte (de una versión anterior, o con cola_s 0): ninguna corta
        write(folder / "fases.json", json.dumps({"antes": {"corridas": 3, "flujos": {"home": {"corridas": 3}}}}))
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "bash recorrido.sh", False, prepare, "despues"), [])
        write(folder / "fases.json", "{}")
        write(folder / "advertencias.json", json.dumps({"cola": {"home": {"ultima_marca_s": 20.0, "traza_s": 31.0}}}))
        self.assertEqual(perf.trace_tail(folder, flow, "home", None, "bash recorrido.sh", False, prepare), [])

    def test_drive_corta_el_recorrido_al_llegar_al_limite_y_la_corrida_vale(self):
        started = time.time()
        self.assertEqual(perf.drive("sleep 30", "corrida", deadline=time.time() + 0.5), perf.TAIL_CUT)
        self.assertLess(time.time() - started, 10)
        self.assertIsNone(perf.drive("true", "corrida", deadline=time.time() + 30))

    def test_marca_repetida_sin_cual_dice_cual_se_usa(self):
        flow = {"metricas_usuario": [{"nombre": "volver_ms", "desde": {"marca": "MARK volver"},
                                      "hasta": {"marca": "MARK lista_visible"}},
                                     {"nombre": "abrir_ms", "desde": {"marca": "MARK abrir"},
                                      "hasta": {"marca": "MARK lista_visible", "cual": "primera"}}]}
        sections = [("seccion", ts, 0, 0, name) for ts, name in ((1, "MARK abrir"), (2, "MARK lista_visible"),
                                                                 (3, "MARK volver"), (4, "MARK lista_visible"))]
        found = perf.repeated_without_which(sections, flow)
        self.assertEqual(found, ["la marca MARK lista_visible salió 2 veces; se usa la última después de MARK volver "
                                 "(`cual` no está en el plan, en la métrica 'volver_ms'.hasta)"])

    def test_resumen_sin_instantes_con_pocos_frames_y_grupos_contados(self):
        plan = {"paquete": "com.example.app", "flujos": {"home": {}}}
        rows = []
        for metric, values in (("volver frames", [5] * 6), ("volver jank_app_pct", [100] * 6),
                               ("volver inicio_ms", [900, 1500, 1200, 1100, 1700, 1300]),
                               ("cargar jank_app_pct", [9, 10, 11, 90, 91, 92])):
            for run, value in enumerate(values, start=1):
                rows.append({"fase": "antes", "flujo": "home", "metrica": metric, "corrida": run, "valor": value,
                             "unidad": "ms" if metric.endswith("_ms") else "%" if metric.endswith("pct") else "frames",
                             "sentido": "menor", "familia": "app"})
        table, _ = perf.summary_rows(rows, plan, phases=("antes",), everything=True)
        by_metric = {row[2]: row for row in table}
        self.assertNotIn("volver inicio_ms", by_metric)
        self.assertEqual(by_metric["volver jank_app_pct"][5], "pocos frames")  # 5 frames: menos de 30
        self.assertIn("frame_p90_ms y hilo_max_ms", by_metric["volver jank_app_pct"][9])
        self.assertIn("dos grupos (3 corridas en ~10 y 3 en ~91)", by_metric["cargar jank_app_pct"][9])
        groups = {("home", "medio frames"): {"fases": {"antes": [20] * 6}}}
        self.assertTrue(perf.few_segment_frames(groups, "home", "medio jank_app_pct", plan, perf.SUMMARY_MIN_FRAMES))
        results = [{"metrica": "volver inicio_ms", "flujo": "home", "veredicto": "mejora"},
                   {"metrica": "volver hilo_max_ms", "flujo": "home", "veredicto": "mejora"}]
        self.assertEqual([r["metrica"] for r in perf.compact_compare(results, plan, everything=True)],
                         ["volver hilo_max_ms"])

    def test_un_tramo_puede_empezar_en_el_toque(self):
        plan_path = self.dir / "inv" / "plan.json"
        write(plan_path, json.dumps({"paquete": "com.example.app", "flujos": {"home": {"metricas_usuario": [
            {"nombre": "toque_a_inicio_ms", "desde": {"entrada": "toque"}, "hasta": {"marca": "SCREEN Inicio*"}}]}}}))
        plan = perf.load_plan(plan_path)
        spec = plan["flujos"]["home"]["metricas_usuario"][0]["desde"]
        self.assertEqual((spec["marca"], spec["cual"]), (perf.INPUT_MARK, perf.LAST_BEFORE))
        ms = 1000000
        rows = [("proceso", 0, 0, 0, "com.example.app"), ("limites", 0, 5000 * ms, 0, ""),
                ("input", 50 * ms, 2 * ms, 0, "deliverInputEvent src=0x1002"),
                ("input", 100 * ms, 2 * ms, 0, "deliverInputEvent src=0x1002"),
                ("seccion", 300 * ms, 0, 0, "SCREEN InicioActivity onResume"),
                ("frame", 310 * ms, 16 * ms, 0, "None")]
        metrics, invalid, info = perf.trace_metrics(rows, 60, plan["flujos"]["home"], set(), 34)
        self.assertIsNone(invalid)
        self.assertEqual(dict((m[0], m[1]) for m in metrics)["toque_a_inicio_ms"], 200)
        write(plan_path, json.dumps({"paquete": "com.example.app", "flujos": {"home": {"metricas_usuario": [
            {"nombre": "x_ms", "desde": {"entrada": "swipe"}, "hasta": {"marca": "SCREEN Inicio*"}}]}}}))
        with self.assertRaises(perf.PerfError):
            perf.load_plan(plan_path)

    def test_video_encadena_segmentos_y_los_baja_todos(self):
        adb = FakeAdb(["sh", "-c", "sleep 1.2", "x"])
        chain = perf.VideoChain(adb, 6).start()  # cada segmento "llega a su tope" (6 − 5 s) y empieza el siguiente
        waited = 0.0
        while len(chain.remotes) < 2 and waited < 15:  # espera a que empiece el segundo segmento, sin depender del reloj
            time.sleep(0.2)
            waited += 0.2
        shots = chain.stop(self.dir / "prueba-home.mp4")
        self.assertGreaterEqual(len(shots), 2)
        self.assertEqual(shots[0], self.dir / "prueba-home.mp4")
        self.assertEqual(shots[1], self.dir / "prueba-home-2.mp4")
        self.assertIn("rm -f /sdcard/hbperf-prueba-2.mp4", adb.calls)
        adb = FakeAdb(["sh", "-c", "exit 0", "x"])  # screenrecord que termina enseguida: no se encadena
        chain = perf.VideoChain(adb, 180).start()
        time.sleep(1)
        self.assertEqual(len(chain.remotes), 1)
        chain.stop(self.dir / "otra.mp4")

    def test_captura_de_pantalla_de_una_corrida_invalida(self):
        adb = FakeAdb()
        trace = self.dir / "antes" / "home_3_intento4_invalida_sin-marcas.perfetto-trace"
        trace.parent.mkdir(parents=True)
        shot = perf.invalid_screenshot(adb, trace)
        self.assertEqual(shot, self.dir / "antes" / "home_3_intento4_invalida_sin-marcas.png")
        self.assertTrue(shot.is_file())
        self.assertIn("screencap -p /sdcard/hbperf-invalida.png", adb.calls)


# ── E · Sesiones de IA, S · `siguiente` sin callejones, F · Costo ────────────

from test_perf_0150 import TriageBase  # noqa: E402  (después de las clases de arriba, que no la usan)


class SessionsTest(TriageBase):
    """E2–E6, S1, S2 y F1 sobre una investigación con su proyecto y su repo."""

    def rigorous(self, **extra):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan.pop("profundidad", None)
        plan.update(extra)
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "fases.json", json.dumps({
            "antes": {"fecha": "2026-03-02T10:00:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}},
            "control": {"fecha": "2026-03-02T11:00:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}}}))

    def before_measuring(self):
        """La investigación antes de medir: sin fases, diagnóstico, reporte ni mejoras."""
        write(self.folder / "fases.json", "{}")
        os.remove(str(self.folder / "diagnostico.md"))
        os.remove(str(self.folder / "reporte-inicial-dev.md"))
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"] = []
        write(self.folder / "plan.json", json.dumps(plan))

    def test_costo_del_pedido_mejorado_sale_en_sin_anotar(self):
        self.rigorous(pedido_mejorado=True)
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("--sesion '0 · pedido' --modelo", out)
        line = next(line for line in out.splitlines() if "--sesion '0 · pedido'" in line)
        self.assertTrue(line.strip().startswith("cd "))

    def test_nuevo_registra_el_pedido_mejorado(self):
        self.ok_in("nuevo", "--carpeta", "reports/perf/otra", "--paquete", "com.example.app", "--flujo",
                   "catalogo-lista", "--pedido-mejorado")
        self.assertTrue(json.loads((self.root / "reports/perf/otra/plan.json").read_text(encoding="utf-8"))
                        ["pedido_mejorado"])

    def test_riguroso_sin_decision_da_elige_uno(self):
        self.rigorous()
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("Elige uno", out)
        commands = commands_in(out)
        self.assertTrue(any("decidir --carpeta" in command for command in commands))
        self.assertTrue(any(command.endswith("pausar --carpeta %s" % self.rel) for command in commands))
        self.assertTrue(any(command.endswith("cerrar --carpeta %s" % self.rel) for command in commands))

    def test_aprobacion_pendiente_da_que_revisar_y_como_aprobar(self):
        self.before_measuring()
        out = self.ok_in("aprobar", "--carpeta", self.rel, "--pendiente")
        self.assertIn("Falta tu aprobación", out)
        self.assertIn("plan.json", out)
        self.assertTrue(any(command.endswith("aprobar --carpeta %s" % self.rel) for command in commands_in(out)))
        self.assertIn("pregúntame qué hay que cambiar", out)
        out = self.ok_in("aprobar", "--carpeta", self.rel)
        self.assertIn("Ficha y plan aprobados", out)
        self.assertNotIn("Falta tu aprobación", out)

    def test_avisos_de_una_prueba_anterior_a_la_compilacion_piden_repetir_la_prueba(self):
        self.before_measuring()
        write(self.folder / "advertencias.json", json.dumps({
            "prueba": {"catalogo-lista": {"fecha": "2026-03-02T10:00:00", "avisos": [
                {"tipo": "marca", "texto": "la marca 'MARK lista' no salió", "corto": "revisa dónde se emite"}]}},
            "compilacion": {"estado": "ok", "fecha": "2026-03-02T11:00:00"}}))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("anterior a la última compilación", out)
        self.assertNotIn("Chat nuevo", out)
        self.assertIn("--prueba", commands_in(out)[0])

    def test_tamano_del_proyecto_cuenta_los_modulos_de_la_investigacion(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        write(self.folder / "logs" / "dependencias.txt", "releaseRuntimeClasspath - Runtime classpath\n" + "".join(
            "+--- com.example:modulo%02d:1.0.0\n" % i for i in range(40)))
        self.assertEqual(perf.project_size(self.root, self.folder, plan),
                         ("grande", "40 módulos según :app:dependencies (proyectos y artefactos internos del grupo "
                                    "com.example)"))
        self.assertEqual(perf.project_size(self.root)[1], "0 módulos en settings.gradle")

    def test_una_lista_donde_va_un_texto_se_une(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["alternativas"] = ["bajar el límite de páginas", "crearlas al abrirlas"]
        write(self.folder / "plan.json", json.dumps(plan))
        self.assertEqual(perf.load_plan(self.folder / "plan.json")["mejoras"][0]["alternativas"],
                         "bajar el límite de páginas; crearlas al abrirlas")

    def test_una_prueba_sin_avisos_cierra_el_pendiente_de_la_prueba(self):
        text = (self.folder / "estado.md").read_text(encoding="utf-8")
        text = text.replace("## Pedido al equipo dueño", "- Bloqueo de la corrida de prueba: la marca no salió porque "
                                                           "no compiló\n- H3 · otra cosa pendiente\n\n## Pedido al equipo dueño")
        write(self.folder / "estado.md", text)
        self.assertEqual(perf.close_test_pendings(self.folder), 1)
        text = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("no compiló · ✔ resuelto por perf.py", text)
        self.assertNotIn("otra cosa pendiente · ✔", text)
        self.assertEqual(perf.close_test_pendings(self.folder), 0)


class ConnectionsTest(unittest.TestCase):
    """E6: conexiones nuevas por servicio y el candidato "conexiones ≈ llamadas"."""

    def test_tabla_y_candidato(self):
        rows = []
        for run in range(1, 5):
            for service in ("GET pedidos/{id}", "GET catalogo/destacados"):
                for metric, value in (("conexion_ms", 240), ("conexiones_nuevas", 2), ("llamadas", 2)):
                    rows.append({"fase": "antes", "flujo": "home", "corrida": run, "metrica": "red %s %s" % (service, metric),
                                 "valor": value})
        urls = {"GET pedidos/{id}": "https://api.example.com/ms-pedidos/v2.1/pedidos/42",
                "GET catalogo/destacados": "https://api.example.com/ms-catalogo/v3.0/destacados"}
        md = "\n".join(perf.connections_md(rows, "home", "antes", urls))
        self.assertIn("| GET https://api.example.com/ms-pedidos/v2.1/pedidos/42 | 4 de 4 | 240 ms | 2 | 2 |", md)
        self.assertIn("Candidato · conexiones nuevas ≈ llamadas** (api.example.com)", md)


from test_perf_0140 import ModulesBase  # noqa: E402


class BinaryModulesTest(ModulesBase):
    """E4: el módulo binario con el toque que lo pidió, "Elige uno" y el paso cuando pasa a código."""

    def test_binario_con_motivo_elige_uno_y_cuando_pasa_a_codigo_da_el_chat(self):
        self.good("setup", "--estado", "--carpeta", self.rel, "--modulos", "com.example:modulo-pagos", "--dependencias",
                  self.binary, "--para", "com.example:modulo-pagos=aquí está el toque de Pagar", "--pierde",
                  "com.example:modulo-pagos=la métrica del toque a la confirmación")
        module = self.modules()["com.example:modulo-pagos"]
        self.assertEqual(module["para"], "aquí está el toque de Pagar")
        out = self.good("siguiente", "--carpeta", self.rel)
        self.assertIn("lo pidió aquí está el toque de Pagar; si sigue binario, se pierde la métrica del toque", out)
        self.assertIn("Elige uno", out)
        self.assertIn("A. Pasarlo a código", out)
        self.assertIn("B. Dejarlo binario", out)
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--dependencias", self.code)
        self.assertIn("com.example:modulo-pagos cambió de binario (llega compilado) a código desde la sesión 1: ahora se "
                      "puede poner la marca (aquí está el toque de Pagar)", out)
        self.assertEqual(self.modules()["com.example:modulo-pagos"]["para"], "aquí está el toque de Pagar")
        out = self.good("siguiente", "--carpeta", self.rel)
        self.assertIn("Un módulo pasó a código", out)
        self.assertIn("pon la marca o el tramo que faltaba", out)


class ReviewETest(TriageBase):
    """E: lo que pidió la revisión: textos viejos que no detienen un plan, conexiones nuevas con la mediana en 0, los
    bloqueos de la prueba con su prefijo y el encabezado de estado.md."""

    def test_un_numero_donde_va_un_texto_no_detiene_un_plan_anterior(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0].update(esperado=500, minimo=-30, titulo_gerencia={"a": 1})
        write(self.folder / "plan.json", json.dumps(plan))
        item = perf.load_plan(self.folder / "plan.json")["mejoras"][0]
        self.assertEqual((item["esperado"], item["minimo"], item["titulo_gerencia"]), ("500", "-30", None))
        plan["mejoras"][0]["costo"] = {"x": 1}  # los que ya se validaban así siguen igual
        write(self.folder / "plan.json", json.dumps(plan))
        with self.assertRaises(perf.PerfError):
            perf.load_plan(self.folder / "plan.json")

    def test_solo_cierra_las_lineas_con_el_prefijo_y_del_flujo(self):
        text = (self.folder / "estado.md").read_text(encoding="utf-8").replace(
            "## Pedido al equipo dueño", "- H2: falta una corrida de prueba con --config cpu\n"
            "- Bloqueo de la corrida de prueba (otro-flujo): la marca no salió\n"
            "- Bloqueo de la corrida de prueba (catalogo-lista): avisos sin corregir\n\n## Pedido al equipo dueño")
        write(self.folder / "estado.md", text)
        self.assertEqual(perf.close_test_pendings(self.folder, "catalogo-lista"), 1)
        text = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("avisos sin corregir · ✔ resuelto por perf.py", text)
        self.assertNotIn("--config cpu · ✔", text)
        self.assertNotIn("la marca no salió · ✔", text)

    def test_encabezado_de_estado_con_opciones_y_pasos_en_orden(self):
        option = ("Uno", "cuando", perf.terminal("true", "nada", "nada"))
        perf.write_next(self.folder, "x", [{"tipo": "opciones", "titulo": "Elige uno", "opciones": [option, option]},
                                           perf.terminal("true", "después", "nada")])
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("**En orden, uno a la vez (en «Elige uno», corre solo uno de sus caminos):**", state)
        perf.write_next(self.folder, "x", [{"tipo": "avisos", "titulo": "t", "lineas": ["a"]},
                                           {"tipo": "opciones", "titulo": "Elige uno", "opciones": [option, option]}])
        self.assertIn("**Elige uno de los caminos (no van en orden):**",
                      (self.folder / "estado.md").read_text(encoding="utf-8"))


class ConnectionsReviewTest(unittest.TestCase):
    """E6: las corridas con conexión nueva salen de conexiones_nuevas (la mediana por llamada da 0 si la mayoría reusa)."""

    def test_mediana_en_cero_con_una_conexion_nueva_por_corrida(self):
        rows = [{"fase": "antes", "flujo": "home", "corrida": run, "metrica": "red GET pedidos %s" % metric, "valor": value}
                for run in range(1, 5) for metric, value in (("conexion_ms", 0), ("conexiones_nuevas", 1),
                                                             ("llamadas", 3))]
        self.assertEqual(perf.connection_stats(rows, "home", "antes"), {"GET pedidos": (4, 4, None, 3, 1)})
        self.assertIn("| GET pedidos | 4 de 4 | — | 3 | 1 |", "\n".join(perf.connections_md(rows, "home", "antes", {})))

    def test_las_corridas_sin_conexion_nueva_cuentan_como_cero(self):
        rows = [{"fase": "antes", "flujo": "home", "corrida": run, "metrica": "red GET pedidos llamadas", "valor": 3}
                for run in range(1, 11)]
        rows += [{"fase": "antes", "flujo": "home", "corrida": run, "metrica": "red GET pedidos %s" % metric, "valor": value}
                 for run in (1, 2) for metric, value in (("conexion_ms", 100), ("conexiones_nuevas", 3))]
        self.assertEqual(perf.connection_stats(rows, "home", "antes"), {"GET pedidos": (2, 10, 100, 3, 0)})
        md = "\n".join(perf.connections_md(rows, "home", "antes", {}))
        self.assertIn("| GET pedidos | 2 de 10 | 100 ms | 3 | 0 |", md)
        self.assertNotIn("Candidato", md)

    def test_servicios_sin_ruta_real_no_se_juntan_en_un_host(self):
        rows = [{"fase": "antes", "flujo": "home", "corrida": 1, "metrica": "red %s %s" % (service, metric), "valor": value}
                for service in ("GET a", "GET b") for metric, value in (("conexion_ms", 100), ("conexiones_nuevas", 2),
                                                                         ("llamadas", 2))]
        self.assertNotIn("Candidato", "\n".join(perf.connections_md(rows, "home", "antes", {})))

    def test_service_metrics_cuenta_las_conexiones_nuevas(self):
        ms = 1000000
        sections = [(1, 10 * ms, 50 * ms, 1, "HTTP GET pedidos"), (1, 10 * ms, 20 * ms, 2, "CONN GET pedidos"),
                    (1, 40 * ms, 10 * ms, 2, "TTFB GET pedidos"), (1, 100 * ms, 30 * ms, 1, "HTTP GET pedidos"),
                    (1, 110 * ms, 10 * ms, 2, "TTFB GET pedidos")]
        out = {name: value for name, value, _, _ in perf.service_metrics(sections, [], [])}
        self.assertEqual(out["red GET pedidos conexiones_nuevas"], 1)


class ModulesReviewTest(ModulesBase):
    """E4: --para con formato y junto a un comando de módulos; un módulo de código que pasa a binario lo dice."""

    def test_para_sin_igual_o_sin_comando_de_modulos(self):
        err = self.bad("setup", "--estado", "--carpeta", self.rel, "--modulos", "com.example:modulo-pagos",
                       "--dependencias", self.binary, "--para", "sin-igual")
        self.assertIn("--para va como MÓDULO=TEXTO", err)
        err = self.bad("setup", "--estado", "--carpeta", self.rel, "--para", "com.example:modulo-pagos=el toque")
        self.assertIn("--para y --pierde se guardan junto con el mapa de módulos", err)

    def test_de_codigo_a_binario(self):
        self.good("setup", "--estado", "--carpeta", self.rel, "--modulos", "com.example:modulo-pagos", "--dependencias",
                  self.code)
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--dependencias", self.binary)
        self.assertIn("com.example:modulo-pagos cambió de código a binario (llega compilado) desde la sesión 1: ya no se "
                      "edita", out)


from test_perf_0140 import AGENTS, PKG, WIRING, SetupBase  # noqa: E402


class PatchAppIdTest(SetupBase):
    """E5: `setup --estado` con una ficha "app sin dato" da el comando que la completa."""

    def test_ficha_sin_applicationid(self):
        write(self.root / "AGENTS.md", AGENTS.replace("- applicationId: %s\n" % PKG, ""))
        self.instrument()
        self.good("setup", "--guardar", *WIRING)
        out = self.good("setup", "--estado")
        self.assertIn("La ficha del parche no tiene el applicationId", out)
        self.assertRegex(out, r"setup --vigente \S+perf-setup-\S+\.patch --paquete\n")
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")  # con el bloque de estado que dejó --guardar
        write(self.root / "AGENTS.md", agents.replace("## Rendimiento\n\n", "## Rendimiento\n\n- applicationId: %s\n" % PKG, 1))
        out = self.good("setup", "--estado")
        self.assertIn("Complétala con el que encontré (%s, de la sección de rendimiento de AGENTS.md)" % PKG, out)
        self.assertRegex(out, r"setup --vigente \S+perf-setup-\S+\.patch --paquete %s" % re.escape(PKG))


class ReviewSTest(TriageBase):
    """S1 y S2: cerrar y pausar desde el "Elige uno" de riguroso, y la compilación registrada antes de medir después."""

    def rigorous(self, mejoras=None):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan.pop("profundidad", None)
        if mejoras is not None:
            plan["mejoras"] = mejoras
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "fases.json", json.dumps({
            "antes": {"fecha": "2026-03-02T10:00:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}},
            "control": {"fecha": "2026-03-02T11:00:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}}}))

    def test_cerrar_sin_aplicar_termina_la_investigacion(self):
        self.rigorous()
        self.ok_in("cerrar", "--carpeta", self.rel, "--dod")
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("investigación cerrada · sin aplicar las mejoras propuestas", out)
        self.assertIn("reporte-inicial-dev.md", out)
        self.assertFalse(any("decidir --carpeta" in command for command in commands_in(out)), out)
        self.assertIn(perf.NO_STEPS_LEFT, out)

    def test_cerrar_sin_dod_y_sin_marcas_no_pide_el_dod_de_una_version_anterior(self):
        from test_perf_0150 import LISTA
        self.rigorous()
        write(self.root / "app" / "Lista.kt", LISTA)  # sin cambios temporales: un arranque sin marcas
        state = (self.folder / "estado.md").read_text(encoding="utf-8").replace("| `app/Lista.kt` | . | marca | — | no |\n", "")
        write(self.folder / "estado.md", state)
        self.ok_in("cerrar", "--carpeta", self.rel)
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("investigación cerrada · sin aplicar las mejoras propuestas", out)
        self.assertNotIn("versión anterior", out)
        self.assertIn(perf.NO_STEPS_LEFT, out)

    def test_avisos_de_configuracion_y_de_marca_con_una_compilacion_nueva_no_dan_el_chat(self):
        pending = [{"tipo": "ajustes", "texto": "animaciones en 0.5", "comandos": [["deja las animaciones normales",
                                                                                "adb shell settings put global x 1"]]},
                   {"tipo": "marca", "texto": "la marca 'MARK lista' no salió", "corto": "revisa dónde se emite"}]
        write(self.folder / "advertencias.json", json.dumps({
            "prueba": {"catalogo-lista": {"fecha": "2026-03-02T10:00:00", "avisos": pending}},
            "compilacion": {"estado": "ok", "fecha": "2026-03-02T11:00:00"}}))
        steps = perf.test_warning_steps(self.folder, self.root, {"instalar": "./instalar.sh"}, "catalogo-lista", pending,
                                        "Sigue", "cd . && capturar --prueba", "cd . && capturar --fase antes", "nada")
        self.assertEqual([step["tipo"] for step in steps], ["avisos", "terminal", "terminal", "terminal"])
        self.assertIn("anterior a la última compilación", steps[0]["lineas"][-1])

    def test_pausar_y_reanudar_vuelven_a_la_decision(self):
        self.rigorous()
        out = self.ok_in("pausar", "--carpeta", self.rel)
        self.assertIn("lista para decidir qué mejoras aplicar (`decidir`)", out)
        self.assertNotIn("lista para seguir con: decisión del usuario", out)
        self.ok_in("reanudar", "--carpeta", self.rel)
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("Elige uno", out)
        self.assertTrue(any("decidir --carpeta" in command for command in commands_in(out)))

    def test_apk_viejo_antes_de_despues_con_una_compilacion_nueva_solo_repite_la_prueba(self):
        mejora = dict(json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["mejoras"][0],
                      estado="aplicada", aplicada_en="2026-03-03T09:00:00")
        self.rigorous([mejora])
        phases = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))
        phases["prueba"] = {"fecha": "2026-03-03T10:00:00", "marcas_ok": False,
                            "flujos": {"catalogo-lista": {"fecha": "2026-03-03T10:00:00", "marcas_ok": False}}}
        write(self.folder / "fases.json", json.dumps(phases))
        write(self.folder / "advertencias.json", json.dumps({
            "prueba": {"catalogo-lista": {"fecha": "2026-03-03T10:00:00", "avisos": [
                {"tipo": "apk_viejo", "texto": "el APK instalado es anterior a la mejora"}]}}}))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("Compila e instala antes de probar", out)
        notes = json.loads((self.folder / "advertencias.json").read_text(encoding="utf-8"))
        notes["compilacion"] = {"estado": "ok", "fecha": "2026-03-03T11:00:00"}
        write(self.folder / "advertencias.json", json.dumps(notes))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("repite la corrida de prueba con el build nuevo (antes de medir después)", out)
        self.assertNotIn("Compila e instala antes de probar", out)
        self.assertIn("--prueba", commands_in(out)[0])

    def test_s2_sale_en_setup_estado_y_en_recuperar(self):
        self.rigorous([])
        write(self.folder / "fases.json", "{}")  # antes de medir: sin fases, diagnóstico ni reporte
        os.remove(str(self.folder / "diagnostico.md"))
        os.remove(str(self.folder / "reporte-inicial-dev.md"))
        write(self.folder / "advertencias.json", json.dumps({
            "prueba": {"catalogo-lista": {"fecha": "2026-03-02T10:00:00", "avisos": [
                {"tipo": "marca", "texto": "la marca 'MARK lista' no salió", "corto": "revisa dónde se emite"}]}},
            "compilacion": {"estado": "ok", "fecha": "2026-03-02T11:00:00"}}))
        for args in (("setup", "--estado", "--carpeta", self.rel), ("recuperar", "--carpeta", self.rel)):
            out = self.ok_in(*args)
            self.assertIn("anterior a la última compilación", out, args)
            self.assertNotIn("Chat nuevo", out, args)


class ProjectSizeTest(unittest.TestCase):
    """F1: de dónde sale el tamaño del proyecto y qué cuenta como módulo interno."""

    def setUp(self):
        self.dir = Path(__import__("tempfile").mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, str(self.dir), True)
        self.folder = self.dir / "reports" / "perf" / "f" / "2026-03-02"
        self.plan = {"paquete": "com.example.app", "flujos": {"f": {}}}

    def deps(self, name, lines):
        write(self.folder / "logs" / name, "profilingRuntimeClasspath - Runtime classpath\n" + "".join(
            "+--- %s\n" % line for line in lines))

    def test_huella_de_modulos_sin_terceros_ni_doble_conteo(self):
        self.deps("huella-modulos.log", ["project :pedidos", "project :pagos -> com.example:pagos:1.0",
                                         "com.example:pagos:1.0", "com.example.core:red:2.0", "androidx.core:core:1.12.0",
                                         "com.exampleotra:x:1.0"])
        self.assertEqual(perf.investigation_module_counts(self.folder, self.plan)[0][0], 3)  # :pedidos, :pagos, red

    def test_un_grupo_publico_no_cuenta_artefactos_internos(self):
        self.deps("dependencias.txt", ["io.github.otro:lib:1.0", "io.github.alguien:app-core:1.0"])
        self.assertEqual(perf.investigation_module_counts(self.folder, dict(self.plan, paquete="io.github.alguien.app")),
                         [])

    def test_huella_de_fases_y_mapa_del_plan(self):
        write(self.folder / "fases.json", json.dumps({"antes": {perf.MODULE_PRINT: {
            "fuente": "gradle", "proyectos": [":a", ":b"], "binarios": ["com.example:c"]}}}))
        plan = dict(self.plan, modulos=[{"nombre": ":a", "tipo": "codigo"}])
        self.assertEqual(perf.investigation_module_counts(self.folder, plan),
                         [(3, "la huella de módulos de :app:dependencies"), (1, "el mapa de módulos del plan")])
        write(self.folder / "fases.json", "[]")  # un fases.json raro no detiene `consumo`
        self.assertEqual(perf.investigation_module_counts(self.folder, plan), [(1, "el mapa de módulos del plan")])

    def test_agents_md_manda_aunque_haya_carpeta(self):
        self.deps("dependencias.txt", ["com.example:m%02d:1.0" % i for i in range(40)])
        write(self.dir / "AGENTS.md", "# P\n\n## Rendimiento\n\n- Tamaño del proyecto: pequeño\n")
        self.assertEqual(perf.project_size(self.dir, self.folder, self.plan), ("pequeño", "AGENTS.md"))

    def test_el_aviso_de_consumo_dice_el_tamano_y_de_donde_salio(self):
        self.deps("dependencias.txt", ["com.example:m%02d:1.0" % i for i in range(40)])
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        result = subprocess.run(perf_argv(SCRIPT) + ["consumo", "--carpeta", str(self.folder), "--sesion",
                                                     "2 · diagnóstico", "--costo", "9 USD"],
                                cwd=str(self.dir), env=dict(ENV, HOME=str(self.dir)), capture_output=True, text=True,
                                encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("(proyecto grande: 40 módulos según :app:dependencies", result.stdout)
        self.assertIn("proyecto grande: 40 módulos según", (self.folder / "estado.md").read_text(encoding="utf-8"))


# ── R · Reportes con la estructura y el diseño aprobados ─────────────────────

import shutil  # noqa: E402

PEDIDOS_URL = "https://api.example.com/ms-pedidos/v2.1/pedidos/42"


class ReportStructureTest(PerfBase):
    """Los reportes de 0.16.0 (R) sobre una investigación de fixture: encabezado y pie, orden de secciones, sin anexo y
    servicios con su versión."""

    def investigation(self, fixture="hb-performance-0.10.0", name="detalle"):
        folder = self.dir / "reports" / "perf" / name / "2026-03-02"
        shutil.copytree(str(ROOT / "tests" / "fixtures" / fixture), str(folder))
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        flow = next(iter(plan["flujos"]))
        with (folder / "metricas.csv").open("a", encoding="utf-8") as handle:
            handle.write("".join("%s,%s,%s,%d,%s,%s,menor,%s\n" % (phase, flow, metric, run, value, unit, family)
                                 for phase in ("antes", "control") for run in range(1, 6)
                                 for metric, value, unit, family in (
                                     ("red GET pedidos/{id} llamadas", 2, "llamadas", "app"),
                                     ("red GET pedidos/{id} ms", 300, "ms", "info"))))
        write(folder / "servicios.json", json.dumps({"servicios": {"GET pedidos/{id}": PEDIDOS_URL}}))
        return folder

    def setUp(self):
        super().setUp()
        write(self.dir / "AGENTS.md", "# App de pedidos\n\n## Rendimiento\n\n- applicationId: com.example.app\n")
        self.folder = self.investigation()

    def test_encabezado_pie_y_tema(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        dev = (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        business = (self.folder / "reporte-inicial-gerencia.html").read_text(encoding="utf-8")
        for page in (dev, business):
            self.assertIn("App de pedidos", page)  # R1: el nombre del proyecto, de AGENTS.md
            self.assertIn("Performance · Detalle de un ítem</h1>", page)  # sin fecha
            self.assertNotIn("2026-03-02</h1>", page)
            self.assertIn("Los números son medianas de varias mediciones", page)
            self.assertRegex(page.split("Los números son medianas")[1], r"\d{4}-\d{2}-\d{2}")  # la fecha de generación
            self.assertIn("prefers-color-scheme", page)
            self.assertIn("localStorage", page)
            self.assertIn("try {", page)
            self.assertNotIn("Generado por hb-performance", page)
            self.assertNotIn("Anexo", page)  # R10
            self.assertNotIn("Cómo leer", page)
        self.assertIn("Reporte técnico dev", dev)
        self.assertNotIn("Reporte técnico dev", business)

    def test_nombre_del_proyecto_por_orden(self):
        root = self.dir / "otro"
        write(root / "settings.gradle.kts", 'rootProject.name = "pedidos-android"\ninclude(":app")\n')
        self.assertEqual(perf.project_name(root), "pedidos-android")
        write(root / "AGENTS.md", "# AGENTS.md\n\n- Proyecto: App de ejemplo\n")
        self.assertEqual(perf.project_name(root), "App de ejemplo")
        self.assertEqual(perf.project_name(self.dir / "sin-nada"), "sin-nada")
        self.assertEqual(perf.report_scope("Rendimiento · Pedidos · 2026-03-02"), "Pedidos")

    def test_orden_de_secciones(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.ok("reporte", "--carpeta", self.folder, "--html")
        order = lambda name: re.findall(r'<section id="([\w-]+)"', (self.folder / name).read_text(encoding="utf-8"))
        self.assertEqual(order("reporte-inicial-dev.html"), ["resumen", "usuario", "medicion", "metricas", "hallazgos",
                                                              "mejoras", "servicios", "costo"])
        self.assertEqual(order("reporte-inicial-gerencia.html"), ["resumen", "usuario", "medido", "estado", "encontro",
                                                                   "cambios", "riesgos"])
        self.assertEqual(order("reporte-final-dev.html"), ["resumen", "usuario", "medicion", "resultado", "hallazgos",
                                                            "mejoras", "servicios", "costo"])
        self.assertEqual(order("reporte-final-gerencia.html"), ["resumen", "usuario", "medido", "resultado", "encontro",
                                                                 "cambios", "riesgos", "pendiente"])
        final = (self.folder / "reporte-final-dev.html").read_text(encoding="utf-8")
        self.assertIn("<summary>Comparación completa", final)  # R10: plegable, solo en el final
        self.assertNotIn("Comparación completa", (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8"))

    def test_al_imprimir_siempre_claro(self):
        page = (perf.ASSETS / "plantillas" / "reporte.html").read_text(encoding="utf-8")
        dark = page.index(':root[data-theme="dark"]')
        printing = page.rindex("@media print")
        self.assertGreater(printing, dark)  # va después del tema oscuro y pesa lo mismo: gana al imprimir
        self.assertIn(':root, :root[data-theme], :root:not([data-theme="light"]) { --bg: #ffffff;', page[printing:])

    def test_gerencia_cuenta_los_confirmados_sin_palabras(self):
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        write(self.folder / "estado.md", state.replace("| H1 | Dos cargas del detalle |", "| H1 | El ViewModel llama a cargar() dos veces |"))
        out = self.ok("reporte", "--carpeta", self.folder, "--inicial")
        business = (self.folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8")
        self.assertIn("1 causa confirmada [se puede corregir]", business)  # un bug, del color de su tipo; sin "más": es la única
        self.assertNotIn("Ninguna causa confirmada", business)
        self.assertIn("⚠ Gerencia:", out)

    def test_markdown_con_celdas_de_una_linea_y_diffs_con_acentos(self):
        text = perf.html_to_text('<table><tr><td>Tramos</td><td>a<br>b</td></tr></table>'
                                 '<pre class="diff"><code><span class="add">+ ``` dentro</span></code></pre>')
        self.assertIn("| Tramos | a · b |", text)
        self.assertIn("````diff\n+ ``` dentro\n````", text)

    def test_lo_capturado_los_servicios_y_su_version(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        dev = (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        self.assertIn("<summary>Qué se capturó en cada medición</summary>", dev)  # R4
        self.assertIn("System trace</b> (Perfetto)", dev)
        self.assertIn("sin correr: se puede pedir para el diagnóstico", dev)
        self.assertNotIn("Ningún servicio cambió entre fases", dev)  # R5
        self.assertIn("llamadas por medición (1 servicio)", dev)
        self.assertIn("Servicios que más tiempo suman", dev)
        self.assertIn("ms-pedidos · v2.1", dev)  # R6: la versión debajo del servicio
        self.assertIn("…/ms-pedidos/v2.1/pedidos/42", dev)
        self.assertNotIn("{version}", dev)
        self.assertEqual(perf.versioned_route("GET otro", {}), "GET otro (sin versión: falta la ruta real)")

    def test_colores_de_hallazgos_y_etiqueta_de_variacion(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        dev = (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        self.assertIn('<div class="card t-bug">', dev)  # R8: la esquina del color de su tipo
        self.assertIn('<div class="card t-descartado">', dev)
        self.assertIn('<span class="chip c-ko">bug</span>', dev)
        self.assertEqual(perf.verdict_label({"veredicto": "dentro del ruido", "avisos": []}),
                         "Dentro de la variación normal")  # R9

    def test_barra_de_en_que_se_va_el_tiempo(self):
        calls = [("GET a", 0, 100), ("GET b", 50, 300), ("GET c", 350, 500)]
        self.assertEqual(perf.key_call(calls, 0, 320), ("GET b", 50, 300))  # R7: la que termina última antes del fin
        self.assertIsNone(perf.key_call([("GET c", 350, 500)], 0, 320))  # sin ninguna, no hay barra

    def test_barra_solo_con_las_marcas_de_la_corrida(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial")
        self.assertNotIn("¿En qué se van", (self.folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8"))
        line = {"llamadas": [["GET pedidos/{id}", 100.0, 400.0]], "marcas": [["NAV detalle", 0.0], ["MARK detalle", 500.0]]}
        (self.folder / "antes").mkdir()  # la carpeta de la fase, donde capturar deja las trazas
        for run in range(1, 6):
            perf.save_timeline(self.folder / "antes", "detalle", run, line)
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        business = (self.folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8")
        self.assertIn("¿En qué se van los 0.5 segundos?", business)  # R7: la app 0.1 s, el servicio 0.3 s, el resto 0.1 s
        self.assertIn("se puede mejorar en la app (0.1 s)", business)
        self.assertIn("depende del servidor (0.3 s)", business)

    def test_unificado_con_una_sola_repetida_o_sin_datos(self):
        result = self.perf("reporte", "--gerencia-unificado", "--carpetas", self.folder, self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("encontré 1", result.stderr)  # la misma carpeta dos veces es una sola
        result = self.perf("reporte", "--gerencia-unificado", "--todas")
        self.assertIn("encontré 1", result.stderr)
        empty = self.dir / "reports" / "perf" / "vacia" / "2026-03-05"
        write(empty / "plan.json", json.dumps({"paquete": "com.example.app", "flujos": {"vacia": {"recorrido": "true"}}}))
        write(empty / "estado.md", "# Rendimiento · Vacía · 2026-03-05\n\n## Ficha\n\n")
        broken = self.investigation(name="rota")
        write(broken / "fases.json", "[]")
        self.ok("reporte", "--gerencia-unificado", "--todas")
        page = (self.dir / "reports" / "performance" / "reporte-gerencia-unificado.html").read_text(encoding="utf-8")
        self.assertIn("Resumen de 3 investigaciones", page)
        self.assertIn("Todavía sin mediciones", page)

    def test_gerencia_unificado(self):
        other = self.investigation("hb-performance-0.9.0", "lista")
        for folder in (self.folder, other):
            self.ok("reporte", "--carpeta", folder, "--inicial")
        out = self.ok("estado")
        self.assertIn("reporte --gerencia-unificado --todas", out)  # R12: `estado` lo ofrece
        out = self.ok("reporte", "--gerencia-unificado", "--todas")
        page = (self.dir / "reports" / "performance" / "reporte-gerencia-unificado.html").read_text(encoding="utf-8")
        self.assertIn("reporte-gerencia-unificado.html", out)
        self.assertIn("Performance · Resumen de 2 investigaciones", page)
        self.assertIn("App de pedidos", page)
        self.assertEqual(len(re.findall(r'<section id="inv\d"', page)), 2)
        self.assertIn('href="#inv1"', page)
        self.assertNotIn("USD", page)
        self.assertNotIn("Costo", page)
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", page), r"\b\w+_ms\b")
        out = self.ok("reporte", "--gerencia-unificado", "--carpetas", self.folder, other, "--salida", self.dir / "salida")
        self.assertTrue((self.dir / "salida" / "reporte-gerencia-unificado.html").is_file())
        result = self.perf("reporte", "--gerencia-unificado", "--carpetas", self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("dos o más investigaciones", result.stderr)


# ── T · Aceptación de punta a punta (solo los comandos que imprime `siguiente`) ──

from test_perf_0150 import T_TRACE, TWO_FLOW_PLAN, AcceptanceBase, step_commands  # noqa: E402

FAILING_BUILD = ("#!/bin/sh\nif [ -f \"$(dirname \"$0\")/compila-bien\" ]; then echo 'BUILD SUCCESSFUL'; exit 0; fi\n"
                 "echo 'FAILURE: Build failed with an exception.'\necho '* What went wrong:'\n"
                 "echo 'Could not resolve com.example:pagos:1.2.0 (repositorio de artefactos inaccesible)'\nexit 1\n")


class AcceptanceT1Riguroso(AcceptanceBase):
    """T1: riguroso desde cero, ejecutando solo lo que imprime `siguiente`: pedido mejorado → APK viejo → compilación
    fallida → compila → prueba con el buffer chico subido y las rutas leídas → antes con un 'preparar' que se salta
    una pantalla en los intentos pares → corte en medio del control y `recuperar` → diagnóstico → sesión 2 → "Elige
    uno" sin decisión → pausar."""

    def last(self, output, words):
        return next(command for _, command in step_commands(output) if words in command)

    def test_t1(self):
        build = self.root / "compilar.sh"
        write(build, FAILING_BUILD)
        build.chmod(0o755)
        counter = self.dir / "intentos.txt"
        prepare = self.root / "preparar.sh"
        # desde que se mide, la pantalla con límite de frecuencia no sale en los intentos pares (las pruebas, antes)
        write(prepare, "#!/bin/sh\n[ -f %s ] || exit 0\nn=$(cat %s 2>/dev/null || echo 0)\necho $((n+1)) > %s\n"
                       "if [ $((n %% 2)) -eq 1 ]; then echo \"se saltó 'Aviso de novedades': la app llegó a 'Pedidos'\" >&2; "
                       "exit 1; fi\n" % (self.dir / "midiendo", counter, counter))
        self.perf_in_root("nuevo", "--paquete", "com.ejemplo.app", "--flujo", "catalogo-lista", "--carpeta", self.rel,
                          "--pedido-mejorado")
        plan = perf.load_plan(self.folder / "plan.json")
        flow = json.loads(json.dumps(TWO_FLOW_PLAN["catalogo-lista"]))
        flow["preparar"] = "sh preparar.sh"
        plan.update(flujos={"catalogo-lista": flow}, principales=["abrir_ms"], instalar="sh compilar.sh", corridas=5)
        write(self.folder / "plan.json", json.dumps(plan))
        self.session1()
        out = self.next_out()
        self.assertIn("--sesion '0 · pedido'", out)  # E2: el costo del pedido mejorado, entre las sin anotar
        # B2: la marca está en el código, pero el APK instalado es anterior: la traza no la trae y `siguiente` pide
        # compilar e instalar, nunca revisar el código
        source = self.root / "app" / "ListaPantalla.kt"
        write(source, "class ListaPantalla {\n    fun mostrar() { MarkTrace.mark(\"lista_visible\") }\n}\n")
        os.utime(str(source), (4102444800, 4102444800))
        self.env["FAKE_UPDATED"] = "2001-01-01 10:00:00"
        self.tp_outputs(T_TRACE.replace('"seccion",600000000,0,0,"MARK lista_visible"\n', ""))
        prueba = self.run_step(self.last(out, "--prueba"))
        self.assertIn("anterior a las marcas", prueba)
        out = self.next_out()
        self.assertNotIn("Chat nuevo", out.split("Costo")[0])
        install = self.last(out, " instalar --carpeta")
        # B1: la compilación falla: `siguiente` da la primera línea útil y pide compilar de nuevo, nunca un chat
        done = run_shell(install, self.env)
        self.assertNotEqual(done.returncode, 0)
        out = self.next_out()
        self.assertIn("compilación fallida: Could not resolve com.example:pagos:1.2.0", out)
        self.assertNotIn("Chat nuevo", out.split("Costo")[0])  # compilar, nunca un chat que revise el código
        write(self.root / "compila-bien", "")
        self.env["FAKE_UPDATED"] = "2100-06-01 10:00:00"
        self.tp_outputs(T_TRACE)  # el build nuevo emite la marca
        self.run_step(self.last(out, " instalar --carpeta"))
        out = self.next_out()
        self.assertNotIn("compilación fallida", out)
        # B6 y B5: el buffer chico se sube (y queda para revertir) y las rutas se leen
        self.env["FAKE_LOGCAT_G"] = "main: ring buffer is 256 KiB (250 KiB consumed)"
        self.env["FAKE_LOGCAT_PERF"] = ("11-05 10:00:00.000  1234  1234 I hb-perf : servicio\tGET\tpedidos/{id}\t"
                                        "https://api.example.com/ms-pedidos/v2.1/pedidos/42")
        prueba = self.run_step(self.last(out, "--prueba"))
        self.assertIn("buffer de logcat de 256 KiB", prueba)
        self.assertIn("-G 256K", (self.folder / "estado.md").read_text(encoding="utf-8"))  # para revertirlo
        self.assertTrue(any("pedidos/{id}" in key for key in perf.service_urls(self.folder)))  # B5: rutas leídas
        # C1–C3: antes con un 'preparar' que se salta la pantalla en los intentos pares
        out = self.next_out()
        write(self.dir / "midiendo", "")
        before = self.run_step(self.last(out, "--fase antes"))
        self.assertIn("Se saltó 'Aviso de novedades': la app llegó directo a 'Pedidos'", before)
        self.assertEqual(perf.csv_runs(self.folder, "antes", "catalogo-lista"), list(range(1, 6)))
        # A1–A3: la terminal se cierra en medio del control; `siguiente` da `recuperar` y la fase termina con 10
        out = self.next_out()
        control = self.last(out, "--fase control")
        self.env["FAKE_MATA"] = "pidof:5"
        killed = run_shell(control, self.env)
        self.assertNotEqual(killed.returncode, 0)
        del self.env["FAKE_MATA"]
        out = self.next_out()
        recover = self.run_step(self.last(out, "recuperar --carpeta"))
        self.assertIn("Corridas válidas de control", recover)
        out = self.next_out()
        rest = self.last(out, "--fase control")
        valid = len(perf.csv_runs(self.folder, "control", "catalogo-lista"))
        self.assertGreaterEqual(valid, 1)  # el corte dejó corridas válidas: se cuentan, no se repiten
        self.assertIn("--corridas %d" % (5 - valid), rest)
        self.run_step(rest)
        self.assertEqual(perf.csv_runs(self.folder, "control", "catalogo-lista"), list(range(1, 6)))
        self.assertEqual(json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))["control"]["corridas"], 5)
        # diagnóstico, sesión 2 y "Elige uno" sin decisión (S1) → pausar
        out = self.next_out()
        self.run_step(self.last(out, " diagnostico --carpeta"))
        out = self.session2()
        out = self.next_out()
        self.assertIn("Elige uno", out)
        self.follow(out, choose="Pausar para después")
        out = self.next_out()
        self.assertIn("en pausa", out)
        self.assertTrue(step_commands(out)[0][1].endswith("reanudar --carpeta %s" % self.rel))
        self.assertIn("--sesion '0 · pedido'", out)  # E2: sigue entre las sin anotar
        self.assertTrue(all(command.startswith("cd ") for command in self.ran))


T2_DEPS_BINARY = ("profilingRuntimeClasspath - Runtime classpath\n+--- project :feature:pedidos\n"
                  "\\--- com.example:pagos:1.2.0\n")
T2_DEPS_CODE = ("profilingRuntimeClasspath - Runtime classpath\n+--- project :feature:pedidos\n"
                "\\--- com.example:pagos:1.2.0 -> project :pagos\n")


class AcceptanceT2ModuloBinario(AcceptanceBase):
    """T2: la marca que se quiere cae en un módulo binario → "Elige uno" → el usuario lo pasa a código y
    `--comprobar-modulos` lo detecta y da el paso → la huella de módulos cambia entre fases y se avisa."""

    def last(self, output, words):
        return next(command for _, command in step_commands(output) if words in command)

    def test_t2(self):
        gradlew = self.root / "gradlew"
        write(gradlew, "#!/bin/sh\ncat \"$GRADLE_DEPS\"\n")  # el Gradle de mentira: la salida de :app:dependencies
        gradlew.chmod(0o755)
        deps = self.dir / "deps.txt"
        write(deps, T2_DEPS_BINARY)
        self.env["GRADLE_DEPS"] = str(deps)
        flows = {"catalogo-lista": json.loads(json.dumps(TWO_FLOW_PLAN["catalogo-lista"]))}
        self.make_plan(flows, triage=False, instalar="./gradlew :app:installProfiling")
        # la sesión 1 registra el módulo del alcance y para qué hacía falta
        self.perf_in_root("setup", "--estado", "--carpeta", self.rel, "--modulos", "com.example:pagos", "--para",
                          "com.example:pagos=aquí está el toque de Pagar")
        out = self.next_out()
        self.assertIn("lo pidió aquí está el toque de Pagar", out)
        self.assertIn("A. Pasarlo a código", out)
        self.assertIn("B. Dejarlo binario", out)
        prueba = self.last(out, "--prueba")
        write(deps, T2_DEPS_CODE)  # el usuario cambia el interruptor del proyecto y sincroniza Gradle
        recheck = self.follow(out, stop=lambda command: "--prueba" in command or "--fase" in command,
                              choose="Pasarlo a código")
        self.assertIn("com.example:pagos cambió de binario (llega compilado) a código desde la sesión 1: ahora se "
                      "puede poner la marca (aquí está el toque de Pagar)", recheck)
        out = self.next_out()
        self.assertIn("Un módulo pasó a código", out)
        self.assertIn("pon la marca o el tramo que faltaba", out)
        self.run_step(prueba)  # la sesión 1 corta pone la marca y repite la prueba, como dice el chat
        out = self.next_out()
        self.assertNotIn("Un módulo pasó a código", out)
        self.run_step(self.last(out, "--fase antes"))
        write(deps, T2_DEPS_BINARY)  # alguien vuelve el interruptor: el control se mide con el módulo binario
        control = self.run_step(self.last(self.next_out(), "--fase control"))
        self.assertIn("la huella de los módulos cambió desde la fase antes", control)
        comparison = self.perf_in_root("comparar", self.folder / "metricas.csv")  # el cierre compara (cierre.md)
        self.assertIn("huella de los módulos", comparison)


# ── Q · Lo que quedaba pendiente de 0.15.x ───────────────────────────────────

class PendingQTest(TriageBase):
    """Q: respaldo con fecha antes de que `reanudar` reponga las marcas."""

    def test_reanudar_respalda_los_archivos_antes_de_reponer_las_marcas(self):
        from test_perf_0150 import LISTA
        self.ok_in("pausar", "--carpeta", self.rel)
        out = self.ok_in("reanudar", "--carpeta", self.rel)
        self.assertIn("Respaldo antes de reponer las marcas: 1 archivo", out)
        backups = list((self.folder / "parches" / "respaldos").glob("reanudar-*/*/app/Lista.kt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), LISTA)  # tal como estaba, sin la marca
        self.assertRegex(backups[0].parent.parent.parent.name, r"^reanudar-.+-\d{8}-\d{6}$")  # con fecha


class DodLooseLinesTest(PerfBase):
    """Q: del `## DoD` también se leen las casillas, un comando de una palabra con etiqueta, dos comandos en una viñeta,
    las tablas y los párrafos que empiezan con un comando; un párrafo que cita un comando en medio del texto se cita."""

    def test_parrafos_tablas_casillas_y_dos_comandos(self):
        write(self.dir / "AGENTS.md", "# P\n\n## DoD\n\n- [ ] `./gradlew lint`\n- Tests: `pytest`\n"
                                      "- `./gradlew test` y `./gradlew detekt`\n\n"
                                      "`./gradlew assembleDebug` compila la variante de pruebas.\n\n"
                                      "Antes de abrir el PR corre `./gradlew check` en la rama.\n\n"
                                      "| Paso | Comando |\n| --- | --- |\n| Formato | `./gradlew ktlintCheck` |\n"
                                      "| No publiques | `./gradlew publish` |\n")
        commands, skipped = perf.dod_entries(self.dir)
        root = perf.q(self.dir)
        self.assertEqual(commands, ["cd %s && %s" % (root, command) for command in (
            "./gradlew lint", "pytest", "./gradlew test", "./gradlew detekt", "./gradlew assembleDebug",
            "./gradlew ktlintCheck")])
        reasons = dict(skipped)
        self.assertIn("párrafo que cita un comando", reasons["Antes de abrir el PR corre `./gradlew check` en la rama."])
        self.assertIn("lo prohíbe", reasons["| No publiques | `./gradlew publish` |"])

    def test_lo_condicionado_en_tablas_y_parrafos_no_se_corre(self):
        write(self.dir / "AGENTS.md", "# P\n\n## DoD\n\n| Paso | Comando | Nota |\n| --- | --- | --- |\n"
                                      "| Instrumentados | `./gradlew connectedCheck` | Solo con dispositivo |\n"
                                      "| `./gradlew lintRelease` | solo en CI |\n"
                                      "| Publicar (no lo hagas) | `./gradlew assembleRelease` |\n\n"
                                      "`./gradlew connectedAndroidTest` solo en CI.\n\nSolo en CI:\n\n"
                                      "| `./gradlew uploadArchives` |\n\n- Rama base: `main`\n- `./gradlew build` y `lint`\n")
        commands, skipped = perf.dod_entries(self.dir)
        self.assertEqual(commands, ["cd %s && ./gradlew build" % perf.q(self.dir)])  # ni `main` ni `lint` sueltos
        reasons = dict(skipped)
        for line in ("| Instrumentados | `./gradlew connectedCheck` | Solo con dispositivo |",
                     "| `./gradlew lintRelease` | solo en CI |", "| Publicar (no lo hagas) | `./gradlew assembleRelease` |",
                     "`./gradlew connectedAndroidTest` solo en CI."):
            self.assertIn("no lo corro", reasons[line], line)
        self.assertIn("lo presenta \"Solo en CI:\"", reasons["| `./gradlew uploadArchives` |"])

    def test_nada_que_antes_no_se_corria_y_no_debe(self):
        write(self.dir / "AGENTS.md", "# P\n\n## DoD\n\n"
                                      "- No lo corras en local: `./gradlew connectedCheck` ni\n  `./gradlew connectedAndroidTest`\n"
                                      "- `./gradlew test` y `./gradlew connectedAndroidTest` si hay un dispositivo\n"
                                      "- `./gradlew assembleDebug`, `./gradlew assembleRelease` o `./gradlew bundle` según la variante\n"
                                      "- Framework de tests: `JUnit5`\n- Build variant: `release`\n- Lint: `ktlint`\n\n"
                                      "Solo en CI:\n\n```bash\n./gradlew uploadArchives\n```\n\nSolo en CI:\n\n"
                                      "- `./gradlew publishToMavenLocal`\n\n| Paso | Comando | Solo en CI |\n| --- | --- | --- |\n"
                                      "| Firma | `./gradlew signRelease` | Sí |\n\nEsto corre solo con un dispositivo\n"
                                      "`./gradlew connectedCheck`\n\n| Commits | `Conventional Commits` |\n")
        commands, skipped = perf.dod_entries(self.dir)
        root = perf.q(self.dir)
        self.assertEqual(commands, ["cd %s && %s" % (root, command) for command in (
            "./gradlew test", "./gradlew assembleDebug", "ktlint")])  # el primero de cada viñeta, como antes
        reasons = dict(skipped)
        self.assertIn("lo presenta", reasons["./gradlew uploadArchives"])
        self.assertIn("lo presenta", reasons["- `./gradlew publishToMavenLocal`"])
        self.assertIn("no lo corro", reasons["| Firma | `./gradlew signRelease` | Sí |"])
        self.assertIn("no lo corro", reasons["`./gradlew connectedCheck`"])


class ReportFollowUpTest(PerfBase):
    """Q: lo que dejó la revisión de los reportes: `que_gana` en lugar de `esperado`, el inicial con una mejora ya
    aplicada, sin "(0 servicios)" y los servicios sin ruta real por nombre."""

    def folder_copy(self):
        import shutil
        folder = self.dir / "reports" / "perf" / "detalle" / "2026-03-02"
        shutil.copytree(str(ROOT / "tests" / "fixtures" / "hb-performance-0.10.0"), str(folder))
        return folder

    def test_que_gana_y_el_inicial_con_una_mejora_aplicada(self):
        folder = self.folder_copy()
        out = self.ok("reporte", "--carpeta", folder, "--inicial")
        business = (folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8")
        changes = business.split("## Cambios propuestos")[1].split("## ")[0]
        self.assertIn("Qué gana el usuario\nsin completar", changes)  # `esperado` es técnico: no se publica
        self.assertNotIn("0 llamadas", changes)
        self.assertIn("M1, M2 no tienen `que_gana` en plan.json", out)  # el aviso nombra el campo
        self.assertIn("Los que ya se aplicaron lo dicen en su estado", changes)
        self.assertIn("Se midió el recorrido tal como estaba antes de los cambios", business)
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"][0]["que_gana"] = "El detalle aparece antes"
        write(folder / "plan.json", json.dumps(plan))
        self.ok("reporte", "--carpeta", folder, "--inicial")
        self.assertIn("Qué gana el usuario\nEl detalle aparece antes",
                      (folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8"))

    def test_sin_filas_por_servicio_y_rutas_que_faltan(self):
        folder = self.folder_copy()
        self.ok("reporte", "--carpeta", folder, "--inicial")
        dev = (folder / "reporte-inicial-dev.md").read_text(encoding="utf-8")
        self.assertIn("llamadas por medición\n", dev)
        self.assertNotIn("(0 servicios)", dev)
        self.assertEqual(perf.names_and_more(list("abcdefg"), 5), "a, b, c, d, e y 2 más")
        self.assertEqual(perf.names_and_more(["GET a"], 5), "GET a")


# ── T3, T3b y T4 · Reportes de punta a punta ─────────────────────────────────

class ReportFixtureBase(PerfBase):
    """Una investigación de fixture en un proyecto con AGENTS.md (como ReportStructureTest, sin repetir sus tests)."""

    investigation = ReportStructureTest.investigation

    def setUp(self):
        super().setUp()
        (self.dir / "home").mkdir()  # un HOME vacío y git sin la configuración de la máquina
        self.env.update(HOME=str(self.dir / "home"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        write(self.dir / "AGENTS.md", "# App de pedidos\n\n## Rendimiento\n\n- applicationId: com.example.app\n")
        self.folder = self.investigation()


class AcceptanceT3Reportes(ReportFixtureBase):
    """T3: los reportes inicial y final de una investigación con todo lo que pide R (datos inventados): una métrica
    dentro de la variación normal, un servicio con su versión y otro sin ruta real, y un hallazgo del servidor."""

    def test_t3(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        flow = next(iter(plan["flujos"]))
        noise = {"antes": [100, 101, 102, 100, 101], "control": [104, 105, 103, 104, 105], "despues": [98, 98, 97, 98, 98]}
        with (self.folder / "metricas.csv").open("a", encoding="utf-8") as handle:
            for phase, values in noise.items():
                handle.write("".join("%s,%s,volver_ms,%d,%d,ms,menor,app\n" % (phase, flow, run, value)
                                     for run, value in enumerate(values, 1)))
            handle.write("".join("%s,%s,red GET catalogo/destacados llamadas,%d,1,llamadas,menor,app\n" % (phase, flow, run)
                                 for phase in ("antes", "control") for run in range(1, 6)))
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        write(self.folder / "estado.md", state.replace(
            "| H1 |", "| H4 | El catálogo responde lento | TTFB 0,9 s en las 5 corridas | el servidor tarda en responder | "
                     "sin confirmar | — |\n| H1 |", 1))
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.ok("reporte", "--carpeta", self.folder, "--html")
        initial_dev = (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        initial_business = (self.folder / "reporte-inicial-gerencia.html").read_text(encoding="utf-8")
        final_dev = (self.folder / "reporte-final-dev.html").read_text(encoding="utf-8")
        final_business = (self.folder / "reporte-final-gerencia.html").read_text(encoding="utf-8")
        self.assertIn("Sin la ruta real (y su versión) de 1 servicio (GET catalogo/destacados)", initial_dev)  # R6
        self.assertIn("ms-pedidos · v2.1", initial_dev)
        self.assertIn("Servicios que más tiempo suman", initial_dev)  # R5: con gráficos también en el inicial
        self.assertIn('<span class="chip c-same">Dentro de la variación normal</span>', final_dev)  # R9
        self.assertIn("del servidor", initial_business)  # el hallazgo que no depende de la app
        for page in (initial_business, final_business):
            self.assertNotIn("USD", page)
            self.assertNotIn("Costo", page)
        self.assertNotIn('id="pendiente"', initial_business)
        self.assertIn('id="pendiente"', final_business)
        for page in (initial_dev, initial_business, final_dev, final_business):
            self.assertIn("App de pedidos", page)  # R1: el nombre del proyecto, el título sin fecha y el pie con la fecha
            self.assertIn("Performance · Detalle de un ítem</h1>", page)
            self.assertRegex(page.split("Los números son medianas")[1], r"\d{4}-\d{2}-\d{2}")
            self.assertEqual("Reporte técnico dev" in page, page in (initial_dev, final_dev))
            self.assertEqual(len(re.findall(r"<script", page)), 1)  # solo el del botón de tema
            self.assertNotRegex(page, r'(?:src|href)="(?:https?:)?//')
            self.assertIn("theme-btn", page)


class AcceptanceT3bUnificado(ReportFixtureBase):
    """T3b: el reporte de gerencia unificado con tres investigaciones inventadas: un triage con su reporte inicial, un
    riguroso cerrado con una mejora aplicada después, en código que citan las otras, y una en pausa."""

    def dated(self, folder, day):
        phases = json.loads((folder / "fases.json").read_text(encoding="utf-8"))
        for record in phases.values():  # el mismo orden y la misma hora de cada fase, otro día
            record["fecha"] = "2026-04-%02d%s" % (day, record["fecha"][10:])
        write(folder / "fases.json", json.dumps(phases))

    def test_t3b(self):
        triage = self.folder
        plan = json.loads((triage / "plan.json").read_text(encoding="utf-8"))
        plan["profundidad"] = "triage"
        write(triage / "plan.json", json.dumps(plan))
        self.dated(triage, 10)
        closed = self.investigation(name="cierre")
        plan = json.loads((closed / "plan.json").read_text(encoding="utf-8"))
        applied = next(item for item in plan["mejoras"] if item.get("estado") == "aplicada")
        applied["archivos"] = [{"ruta": "feature/detalle/src/main/kotlin/com/example/detalle/DetalleViewModel.kt"}]
        write(closed / "plan.json", json.dumps(plan))
        paused = self.investigation(name="pausa")
        write(paused / "pausa.json", json.dumps({"estado": "en pausa", "fecha": "2026-03-04T10:00:00",
                                                 "fase": "decisión del usuario", "lista_para": "decidir"}))
        self.dated(paused, 12)
        for folder in (triage, closed, paused):
            self.ok("reporte", "--carpeta", folder, "--inicial")
        self.ok("reporte", "--carpeta", closed)
        state = (closed / "estado.md").read_text(encoding="utf-8")  # cerrada: la marca quitada y el DoD hecho
        write(closed / "estado.md", state.replace("con `android.os.Trace` | — | no |",
                                                  "con `android.os.Trace` | — | sí · perf.py cerrar 2026-03-05 |"))
        write(closed / "cierre.json", json.dumps({"quitados": 1, "dod": "ok", "fecha": "2026-03-05T10:00:00"}))
        self.ok("reporte", "--carpeta", closed)
        out = self.ok("estado")
        self.assertIn("reporte --gerencia-unificado --todas", out)
        self.ok("reporte", "--gerencia-unificado", "--todas")
        page = (self.dir / "reports" / "performance" / "reporte-gerencia-unificado.html").read_text(encoding="utf-8")
        sections = re.findall(r'<section id="(inv\d)">\s*<h2>[^<]*</h2>\s*<p class="sub">([^<]*) · <span class="chip '
                              r'[^"]*">([^<]+)</span>', page)
        self.assertEqual([(date, label) for _, date, label in sections],
                         [("2026-04-10", "triage"), ("2026-04-12", "en pausa"), ("2026-04-14", "cerrada")])
        self.assertIn("Resumen de 3 investigaciones", page)
        self.assertIn('<div class="v">3</div><div class="l">investigaciones</div>', page)
        self.assertIn('<div class="l">cambios aplicados</div>', page)
        self.assertIn('<div class="l">flujos medidos</div>', page)
        self.assertIn("A tener en cuenta", page)
        self.assertIn("se aplicó en código que pasa por lo que mide", page)  # después del estado inicial de las otras
        self.assertIn("ese estado inicial puede no servir", page)
        self.assertNotIn("USD", page)
        self.assertNotIn("GET pedidos", re.sub(r"<svg.*?</svg>", "", page, flags=re.S))  # sin rutas sueltas en gerencia
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"<(svg|style|script)\b.*?</\1>", " ", page, flags=re.S))
        self.assertEqual(perf.TECH_TERMS.findall(visible), [])


class AcceptanceT4Viejas(PerfBase):
    """T4: los reportes de investigaciones de versiones anteriores (0.10.0 y una hecha con 0.15.1, con sus reportes de
    entonces) se regeneran con el formato nuevo, sin error."""

    def test_t4(self):
        from test_perf_0150 import AcceptanceT4Test
        (self.dir / "home").mkdir()  # un HOME vacío y git sin la configuración de la máquina
        self.env.update(HOME=str(self.dir / "home"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for fixture in ("hb-performance-0.10.0", "hb-performance-0.15.1"):
            with self.subTest(fixture=fixture):
                folder = AcceptanceT4Test.regenerate(self, fixture)
                self.ok("reporte", "--carpeta", folder, "--inicial", "--html")
                for name in ("reporte-inicial-dev", "reporte-inicial-gerencia", "reporte-final-dev",
                             "reporte-final-gerencia"):
                    page = (folder / (name + ".html")).read_text(encoding="utf-8")
                    text = (folder / (name + ".md")).read_text(encoding="utf-8")
                    self.assertIn('<section id="resumen">', page)
                    self.assertNotIn("Anexo", text)
                    self.assertNotIn("Cómo leer", text)
                    self.assertIn("Los números son medianas", text)
                if fixture.endswith("0.15.1"):  # la línea de tiempo y el resumen que dejó 0.15.x se usan sin abrir trazas
                    business = (folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8")
                    self.assertIn("¿En qué se van los", business)


if __name__ == "__main__":
    unittest.main()
