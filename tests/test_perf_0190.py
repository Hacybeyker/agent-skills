"""Tests de hb-performance 0.19.0: `siguiente --json` para el modo orquestado (O). El orquestador decide con esa salida,
nunca leyendo el texto de `siguiente`: cada paso dice qué es (sesión, terminal, decisión o acción humana), quién lo
hace y, si es una sesión, con qué nivel de modelo, qué alias de subagente y qué referencia. Los datos son inventados."""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, init_repo, commit_all, write
from test_perf import PerfBase, perf
from test_perf_0150 import TriageBase

SCRIPT = ROOT / "skills" / "hb-performance" / "scripts" / "perf.py"
RIGUROSO = {"paquete": "com.example.app", "principales": ["abrir_ms"], "flujos": {"catalogo-lista": {"recorrido": "true"}},
            "mejoras": [{"id": "M1", "titulo": "Una sola llamada al abrir la lista", "estado": "propuesta",
                         "metrica": "abrir_ms"}]}
MEASURED = {"antes": {"fecha": "2026-03-02T10:00:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}},
            "control": {"fecha": "2026-03-02T10:30:00", "corridas": 10, "flujos": {"catalogo-lista": {"corridas": 10}}}}


def perf_cmd(*parts):
    return "cd /p && python3 -I /s/perf.py %s" % " ".join(parts)


class JsonBase(TriageBase):
    """La investigación de triage de 0.15.0, que cada test lleva al estado que necesita."""

    def plan_as(self, plan, phases=None):
        write(self.folder / "plan.json", json.dumps(plan))
        if phases is not None:
            write(self.folder / "fases.json", json.dumps(phases))

    def next_json(self, *extra, code=0):
        result = self.run_in("siguiente", "--json", "--carpeta", self.rel, *extra)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, "la salida estándar es solo una línea de JSON:\n" + result.stdout)
        return json.loads(lines[0])


class NextJsonInvestigationTest(JsonBase):
    """O1: con --carpeta, los mismos pasos que `siguiente`, en una forma que se lee con código."""

    def test_un_triage_con_mejoras_es_una_decision_del_usuario(self):
        data = self.next_json()
        self.assertEqual((data["formato"], data["tipo"], data["quien"]), (1, "decision", "usuario"))
        self.assertTrue(data["requiere_persona"])
        self.assertEqual(data["clase"], "profundidad")
        self.assertEqual([option["nombre"] for option in data["pasos"][0]["opciones"]],
                         ["Aplicar ahora", "Pausar para después", "Cerrar del todo"])
        self.assertEqual(data["corre_ahora"], [])
        self.assertTrue(data["archivos"][0]["ruta"].endswith("reporte-inicial-dev.md"))
        # estado.md queda igual que con `siguiente`
        self.assertIn("**Elige uno de los caminos (no van en orden):**",
                      (self.folder / "estado.md").read_text(encoding="utf-8"))

    def test_la_decision_de_mejoras_la_corre_el_usuario_en_su_terminal(self):
        self.plan_as(RIGUROSO, MEASURED)
        data = self.next_json()
        self.assertEqual((data["tipo"], data["clase"], data["donde"]), ("decision", "mejoras", "terminal"))
        self.assertIn("continúa", data["motivo"])
        decide = data["pasos"][0]["opciones"][0]
        self.assertIn(" decidir --carpeta %s --aprobar M1" % self.rel, decide["comando"])
        self.assertEqual(decide["clase"], "mejoras")

    def test_una_mejora_aprobada_es_la_sesion_3_con_su_subagente(self):
        plan = dict(RIGUROSO, mejoras=[dict(RIGUROSO["mejoras"][0], estado="aprobada")])
        self.plan_as(plan, MEASURED)
        data = self.next_json()
        self.assertEqual((data["tipo"], data["quien"], data["sesion"]), ("sesion", "subagente", "3 · M1"))
        self.assertEqual((data["nivel"], data["modelo"], data["esfuerzo"]), ("intermedio", "Sonnet 5.5", "medio"))
        self.assertEqual(data["subagente"], {"modelo": "sonnet", "esfuerzo": "medium"})
        self.assertEqual(data["referencia"], "references/mejoras.md")
        self.assertTrue((Path(data["carpeta_skill"]) / data["referencia"]).is_file())
        self.assertIn("sesión 3, aplica M1", data["texto"])
        self.assertTrue(data["texto"].endswith("No hagas commit ni push."))
        self.assertFalse(data["requiere_persona"])

    def test_el_diagnostico_usa_el_nivel_diagnostico_del_plan(self):
        plan = dict(RIGUROSO, mejoras=[], modelos={"diagnostico": "Opus 5.5"})
        self.plan_as(plan, MEASURED)
        (self.folder / "reporte-inicial-dev.md").unlink()
        data = self.next_json()
        self.assertEqual((data["tipo"], data["sesion"], data["referencia"]),
                         ("sesion", "2 · diagnóstico", "references/diagnostico.md"))
        self.assertEqual(data["subagente"], {"modelo": "opus", "esfuerzo": "high"})

    def test_con_recorrido_automatico_el_orquestador_captura_y_se_detiene_tras_la_prueba(self):
        plan = dict(RIGUROSO, mejoras=[])
        self.plan_as(plan, {})
        for name in ("diagnostico.md", "reporte-inicial-dev.md"):
            (self.folder / name).unlink()
        data = self.next_json()
        self.assertEqual((data["tipo"], data["quien"], data["clase"]), ("terminal", "orquestador", "captura"))
        self.assertEqual([paso.get("fase") for paso in data["pasos"][:3]], ["prueba", "antes", "control"])
        self.assertEqual(len(data["corre_ahora"]), 1, "después de la prueba se vuelve a pedir el paso")
        self.assertTrue(data["corre_ahora"][0].endswith("capturar --plan %s/plan.json --prueba" % self.rel))
        self.assertEqual(data["pasos"][3]["clase"], "diagnostico")
        self.assertEqual(data["pasos"][-1]["sesion"], "2 · diagnóstico")

    def test_con_recorrido_manual_la_captura_es_del_usuario(self):
        plan = dict(RIGUROSO, mejoras=[], flujos={"catalogo-lista": {"recorrido": "manual"}})
        self.plan_as(plan, {})
        for name in ("diagnostico.md", "reporte-inicial-dev.md"):
            (self.folder / name).unlink()
        data = self.next_json()
        self.assertEqual((data["tipo"], data["quien"], data["clase"], data["donde"]),
                         ("humano", "usuario", "captura", "terminal"))
        self.assertIn("recorrido manual", data["motivo"])
        self.assertEqual(data["corre_ahora"], [])
        self.assertTrue(all(command.startswith("cd ") for command in data["comandos"]))

    def test_el_costo_del_orquestador_sale_listo_para_anotar(self):
        data = self.next_json("--modelo", "Haiku 5.5")
        cost = data["costo"]
        self.assertIn("consumo --carpeta %s --sesion orquestado --modelo 'Haiku 5.5'" % self.rel, cost["comando"])
        self.assertIn("2 · diagnóstico", cost["sesiones"])
        low, high = cost["esperado_usd"]
        self.assertLess(0, low)
        self.assertLessEqual(low, high)
        self.assertIsNone(cost["anotado"])

    def test_los_avisos_van_en_notas_y_no_rompen_el_json(self):
        data = self.next_json()
        self.assertTrue(any("sin completar" in line for line in data["notas"]), data["notas"])

    def test_un_error_tambien_sale_en_json(self):
        result = self.run_in("siguiente", "--json", "--carpeta", "reports/perf/no-existe/1")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual((data["tipo"], data["quien"], data["codigo"]), ("error", "usuario", 2))
        self.assertTrue(data["requiere_persona"])
        self.assertIn("✖", result.stderr)

    def test_sin_json_la_carpeta_sigue_siendo_obligatoria(self):
        result = self.run_in("siguiente")
        self.assertEqual(result.returncode, 2)
        self.assertIn("falta --carpeta", result.stderr)
        self.assertIn(" estado", result.stderr)


class OrchestratedCostTest(JsonBase):
    """O6: el total del orquestador va en una sola fila "orquestado", que se compara con lo esperado para las sesiones
    hechas; con ella, `siguiente` ya no pide el costo de cada sesión."""

    def note(self, cost):
        result = self.run_in("consumo", "--carpeta", self.rel, "--sesion", "orquestado", "--modelo", "Haiku 5.5",
                             "--costo", cost)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_avisa_si_se_paso_y_nunca_detiene_nada(self):
        self.note("9 USD")
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("el modo orquestado costó 9 USD", state)
        data = self.next_json()
        self.assertTrue(data["costo"]["se_paso"])
        self.assertEqual(data["tipo"], "decision")

    def test_dentro_de_lo_esperado_no_avisa(self):
        self.note("0.30 USD")
        self.assertNotIn("modo orquestado costó", (self.folder / "estado.md").read_text(encoding="utf-8"))
        self.assertFalse(self.next_json()["costo"]["se_paso"])

    def test_el_transcript_del_orquestador_es_la_fila_orquestado(self):
        state = self.folder / "estado.md"
        found = {"pedido": "Sigue hb-performance con %s en modo orquestado. No hagas commit ni push." % state}
        self.assertEqual(perf.transcript_session(found, None, None)[1], "orquestado")
        plain = {"pedido": "Sigue hb-performance con %s. No hagas commit ni push." % state}
        self.assertNotEqual(perf.transcript_session(plain, None, None)[1], "orquestado")

    def test_con_la_fila_del_orquestador_no_pide_el_costo_de_cada_sesion(self):
        self.assertTrue(perf.missing_costs(self.folder, self.plan()))
        self.note("1 USD")
        self.assertEqual(perf.missing_costs(self.folder, self.plan()), [])
        self.assertNotIn("sin anotar", self.run_in("siguiente", "--carpeta", self.rel).stdout)


class StepClassificationTest(unittest.TestCase):
    """O2: quién hace cada paso, sin interpretar el texto que lee una persona."""

    PLAN = {"flujos": {"auto": {"recorrido": "bash recorrido.sh"}, "manual": {"recorrido": "manual"},
                       "arranque": {"recorrido": {"tipo": "arranque-frio", "actividad": "a/.B"}}}}

    def classify(self, text, **extra):
        return perf.json_step(dict(perf.terminal(text, "qué", "tú"), **extra), self.PLAN, None)

    def test_quien_corre_cada_comando(self):
        cases = [
            (perf_cmd("capturar", "--plan", "x/plan.json", "--flujo", "auto", "--fase", "antes"), "orquestador", "captura"),
            (perf_cmd("capturar", "--plan", "x/plan.json", "--flujo", "arranque", "--fase", "antes"), "orquestador",
             "captura"),
            (perf_cmd("capturar", "--plan", "x/plan.json", "--flujo", "manual", "--prueba"), "usuario", "captura"),
            (perf_cmd("diagnostico", "--carpeta", "x"), "orquestador", "diagnostico"),
            (perf_cmd("setup", "--reponer"), "orquestador", "perf"),
            (perf_cmd("cerrar", "--carpeta", "x", "--dod"), "orquestador", "perf"),
            (perf_cmd("decidir", "--carpeta", "x", "--aprobar", "M1"), "usuario", "mejoras"),
            (perf_cmd("decidir", "--carpeta", "x", "--profundidad", "riguroso"), "usuario", "profundidad"),
            (perf_cmd("aprobar", "--carpeta", "x"), "usuario", "aprobacion"),
            (perf_cmd("reanudar", "--carpeta", "x"), "usuario", "pausa"),
            (perf_cmd("lineabase", "--carpeta", "x", "--quitar-mejoras"), "usuario", "linea_base"),
            (perf_cmd("setup", "--vigente", "p.patch"), "usuario", "setup"),
            (perf_cmd("instrumentar", "--actualizar"), "usuario", "perf"),
            ("cd /p && ./gradlew :app:installProfiling", "usuario", "comando"),
        ]
        for text, who, kind in cases:
            with self.subTest(text=text):
                step = self.classify(text)
                self.assertEqual((step["quien"], step["clase"]), (who, kind))
                if who == "usuario":
                    self.assertTrue(step["motivo"])

    def test_la_instalacion_del_plan_la_corre_el_orquestador(self):
        step = self.classify("cd /p && ./gradlew :app:installProfiling", instala=True)
        self.assertEqual((step["quien"], step["clase"]), ("orquestador", "instalar"))

    def test_la_aprobacion_se_responde_en_el_chat(self):
        self.assertEqual(self.classify(perf_cmd("aprobar", "--carpeta", "x"))["donde"], "chat")

    def test_cargar_una_clave_es_una_entrada_sensible(self):
        step = self.classify("cd /p && printf 'APP_CLAVE: ' && read -r -s APP_CLAVE && echo && export APP_CLAVE")
        self.assertEqual((step["tipo"], step["quien"], step["clase"], step["env"]),
                         ("humano", "usuario", "entorno", ["APP_CLAVE"]))

    def test_una_accion_sin_comando_es_del_usuario(self):
        step = perf.json_step({"tipo": "accion", "que": "instala", "tu": "usa tu comando"}, self.PLAN, None)
        self.assertEqual((step["tipo"], step["quien"]), ("humano", "usuario"))

    def test_una_sesion_con_variables_que_faltan_espera_al_usuario(self):
        step = dict(perf.chat("Sigue hb-performance con /x/estado.md: sesión 3, aplica M1", "intermedio", "medio",
                              "sesión 3: aplica M1", {}), env=["APP_CLAVE"])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APP_CLAVE", None)
            waiting = perf.json_step(step, {"mejoras": [{"id": "M1"}]}, None)
        self.assertEqual((waiting["tipo"], waiting["quien"], waiting["clase"]), ("sesion", "usuario", "entorno"))
        self.assertEqual(waiting["env_faltan"], ["APP_CLAVE"])
        with mock.patch.dict(os.environ, {"APP_CLAVE": "x"}):
            ready = perf.json_step(step, {"mejoras": [{"id": "M1"}]}, None)
        self.assertEqual((ready["quien"], ready["sesion"]), ("subagente", "3 · M1"))

    def test_cerrada_es_fin(self):
        data = perf.steps_payload("investigación cerrada", [
            {"tipo": "archivo", "texto": "/x/reporte-final-dev.html", "que": "el reporte"},
            {"tipo": "fin", "texto": perf.DONE}], {}, None, "/p")
        self.assertEqual((data["tipo"], data["quien"], data["requiere_persona"]), ("fin", "nadie", False))
        self.assertEqual(data["archivos"][0]["ruta"], "/x/reporte-final-dev.html")

    def test_el_alias_del_subagente_sale_de_los_modelos_del_plan(self):
        self.assertEqual(perf.subagent_model({}, "economico"), "haiku")
        self.assertEqual(perf.subagent_model({}, "alto"), "opus")
        self.assertEqual(perf.subagent_model({"modelos": {"intermedio": "GPT 5.3 Codex"}}, "intermedio"), None)
        self.assertEqual(perf.subagent_model({"modelos_cli": {"claude": {"intermedio": "claude-opus-5-5"}}},
                                             "intermedio"), "opus")


class ProjectNextJsonTest(PerfBase):
    """O1: sin --carpeta, lo que sigue en el proyecto antes de una investigación."""

    READY = {"caso": "versionado", "presente": True, "dice": {"listo": True, "en_parche": False}}

    def setUp(self):
        super().setUp()
        (self.dir / "proyecto").mkdir()
        self.root = init_repo(self.dir / "proyecto")
        write(self.root / "AGENTS.md", "# P\n\n## Rendimiento\n\n- applicationId: com.example.app\n")
        commit_all(self.root, "base")

    def payload(self):
        with mock.patch.object(perf, "setup_case", return_value=dict(self.READY, raiz=self.root)):
            return perf.project_next_json(self.root)

    def test_sin_setup_es_la_sesion_0(self):
        result = self.perf("siguiente", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = perf.project_next_json(self.root)
        self.assertEqual((result["tipo"], result["sesion"], result["referencia"]),
                         ("sesion", "0 · setup", "references/setup.md"))
        self.assertIsNone(result["carpeta"])

    def test_con_el_setup_listo_y_el_pedido_guardado_es_la_sesion_1_con_el_pedido(self):
        write(self.root / "reports" / "perf" / "setup" / "pedido.json", json.dumps({
            "texto": "medir de la lista al detalle con ids rv_items", "modo": "triage", "flujo": "lista a detalle",
            "requiere_env": ["APP_CLAVE_PRUEBA"]}))
        data = self.payload()
        self.assertEqual((data["tipo"], data["sesion"], data["referencia"]),
                         ("sesion", "1 · ficha", "references/ficha.md"))
        self.assertIn("en modo triage", data["texto"])
        self.assertIn("medir de la lista al detalle con ids rv_items", data["texto"])
        self.assertEqual(data["pasos"][0]["env"], ["APP_CLAVE_PRUEBA"])

    def test_con_investigaciones_abiertas_el_usuario_elige(self):
        folder = self.root / "reports" / "perf" / "lista" / "2026-03-02"
        write(folder / "plan.json", json.dumps({"paquete": "com.example.app", "flujos": {"lista": {}}}))
        write(folder / "estado.md", "# x\n")
        data = self.payload()
        self.assertEqual((data["tipo"], data["clase"], data["quien"]), ("decision", "investigacion", "usuario"))
        options = data["pasos"][0]["opciones"]
        self.assertTrue(options[0]["carpeta"].endswith("reports/perf/lista/2026-03-02"))
        self.assertIn("siguiente --json --carpeta", options[0]["comando"])
        self.assertEqual((options[-1]["nombre"], options[-1]["sesion"]), ("Empezar otra", "1 · ficha"))


if __name__ == "__main__":
    unittest.main()
