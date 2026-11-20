"""Tests de hb-performance 0.16.0: retomar y recuperar (A), compilar, probar y leer la red (B), punto de partida y
prueba (C), sesiones de IA (E), `siguiente` sin callejones (S), costo (F) y reportes (R). Los datos son inventados."""
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

class RecoverCountTest(CaptureBase):
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

    def test_el_registro_se_actualiza_al_empezar_y_al_terminar_cada_corrida(self):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("        attempts += 1\n        failure = None\n")
        self.assertLess(start, source.index("mark_running(folder, comando=\"capturar\"", start))
        self.assertLess(source.index("mark_running(folder, comando=\"capturar\"", start),
                        source.index("                prepare()\n", start))
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


if __name__ == "__main__":
    unittest.main()
