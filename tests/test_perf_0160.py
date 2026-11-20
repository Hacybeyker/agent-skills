"""Tests de hb-performance 0.16.0: retomar y recuperar (A), compilar, probar y leer la red (B), punto de partida y
prueba (C), sesiones de IA (E), `siguiente` sin callejones (S), costo (F) y reportes (R). Los datos son inventados."""
import json
import os
import re
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
