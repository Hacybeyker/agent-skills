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


if __name__ == "__main__":
    unittest.main()
