"""Tests de hb-performance 0.15.0: migración del setup de versiones anteriores (A), `siguiente` guía sola (B),
medición (C), ficha y pedido (E), costo (F), cierre (P), reportes (H y G) y la aceptación de punta a punta siguiendo solo
lo que imprime la skill (T). Los datos son inventados."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from helpers import ENV, ROOT, commit_all, git, init_repo, perf_argv, write
from test_perf import GOOD, HEADER, DeviceBase, PerfBase, perf, rows
from test_perf_0140 import AGENTS, PKG, WIRING, SetupBase, ends_with_step, executable, pasteable

SKILL = ROOT / "skills" / "hb-performance"
SCRIPT = SKILL / "scripts" / "perf.py"
ACTIVITY = "app/src/main/kotlin/com/example/app/MainActivity.kt"
ACTIVITY_CODE = ("package com.example.app\n\nclass MainActivity {\n    fun onCreate() {\n        cargar()\n    }\n\n"
                 "    fun cargar() = Unit\n}\n")
# Lo que la sesión 0 cablea a mano y perf.py no reconoce como setup: un reportFullyDrawn() en la pantalla de inicio.
ACTIVITY_WIRED = ACTIVITY_CODE.replace("        cargar()\n", "        cargar()\n        reportFullyDrawn()\n")
LEGACY_LINE = "- Setup listo, en parche: `git apply %s` antes de medir\n"


def commands_in(text):
    """Los comandos `cd … && …` de una salida, en orden."""
    return [line.strip() for line in text.splitlines() if line.strip().startswith("cd ")]


def run_shell(command, env):
    """Corre un comando tal como lo pegaría el usuario en su terminal."""
    return subprocess.run(["/bin/sh", "-c", command], env=env, capture_output=True, text=True, encoding="utf-8")


class MigrationBase(SetupBase):
    """Un proyecto con el setup guardado en un parche de una versión anterior, sin ficha, que además trae un archivo
    cableado a mano (que perf.py no reconoce como del setup) y la línea vieja en AGENTS.md."""

    def setUp(self):
        super().setUp()
        write(self.root / ACTIVITY, ACTIVITY_CODE)
        commit_all(self.root, "pantalla")

    def legacy(self, where=None):
        """Arma el parche viejo con el setup y el archivo cableado a mano, lo saca del árbol y deja la línea vieja."""
        self.instrument()
        write(self.root / ACTIVITY, ACTIVITY_WIRED)
        git(self.root, "add", "-N", ".")
        legacy = where or (self.root / "herramientas" / "perf-setup-viejo.patch")
        data = git(self.root, "diff", "--binary")
        git(self.root, "reset", "-q")
        tmp = self.dir / "legacy.patch"
        write(tmp, data)
        git(self.root, "apply", "-R", str(tmp))
        write(legacy, data)
        exclude = self.root / ".git" / "info" / "exclude"
        write(exclude, (exclude.read_text(encoding="utf-8") if exclude.is_file() else "") + "/herramientas/\n/reports/\n")
        shown = os.path.relpath(str(legacy), str(self.root)) if str(legacy).startswith(str(self.root)) else str(legacy)
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", LEGACY_LINE % shown))
        self.assertEqual(self.status(), [])
        return legacy


class LegacyMigrationTest(MigrationBase):
    """A1, A4 y A6: de la línea vieja y un parche sin ficha con un archivo cableado a mano hasta el setup con ficha."""

    def test_migracion_de_punta_a_punta(self):
        legacy = self.legacy()
        before = self.tree()
        # --reponer lo rechaza y propone el comando exacto con el archivo que no reconoció (no la sesión 0 ni --estado)
        error = self.bad("setup", "--reponer", "--simular")
        self.assertIn("toca archivos que no reconozco como del setup: %s" % ACTIVITY, error)
        proposed = commands_in(error)
        self.assertEqual(len(proposed), 1, error)
        self.assertTrue(proposed[0].endswith("setup --reponer --simular --archivos %s" % ACTIVITY), proposed)
        self.assertNotIn("sesión 0", error.split("Cómo seguir")[1])
        self.assertEqual(self.tree(), before)
        # --estado da el mismo camino (sin dar vueltas entre --estado y la sesión 0)
        state = self.good("setup", "--estado")
        self.assertEqual([command for command in commands_in(state) if "perf.py " in command],
                         [proposed[0].replace(" --simular", "")])
        self.assertNotIn("Chat nuevo", state)
        # el comando propuesto, pegado tal cual (sin --simular)
        command = proposed[0].replace(" --simular", "")
        done = run_shell(command, self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("los declaraste cableados a mano (%s)" % ACTIVITY, done.stdout)
        ficha = json.loads(Path(str(legacy) + ".json").read_text(encoding="utf-8"))
        self.assertEqual(ficha["cableados_a_mano"], [ACTIVITY])
        self.assertEqual(ficha["applicationId"], PKG)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("- Setup: en parche `herramientas/perf-setup-viejo.patch`", agents)
        self.assertNotIn("git apply herramientas", agents)  # A4: la línea vieja la quitó perf.py
        backups = list((self.patches / "respaldos").glob("AGENTS.md-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertIn("git apply herramientas", backups[0].read_text(encoding="utf-8"))
        state = self.good("setup", "--estado")
        self.assertIn("Setup de medición · setup en parche, puesto", state)
        self.assertIn("Cableados a mano (anotados en la ficha): %s" % ACTIVITY, state)
        self.good("setup", "--quitar")
        self.assertEqual(self.status(), [])
        out = self.good("setup", "--reponer")  # sin --archivos: ya no lo vuelve a pedir
        self.assertIn("Setup repuesto con su parche", out)
        self.assertEqual((self.root / ACTIVITY).read_text(encoding="utf-8"), ACTIVITY_WIRED)

    def test_archivos_que_no_son_del_parche_detienen(self):
        self.legacy()
        error = self.bad("setup", "--reponer", "--archivos", "app/otra.kt")
        self.assertIn("--archivos nombra app/otra.kt, que no está en el parche", error)

    def test_guardar_con_el_mismo_contenido_escribe_la_ficha(self):
        legacy = self.legacy()
        tmp = self.dir / "aplicar.patch"
        write(tmp, legacy.read_text(encoding="utf-8"))
        git(self.root, "apply", str(tmp))  # el contorno de antes: el parche viejo aplicado a mano
        out = self.good("setup", "--guardar", "--archivos", ACTIVITY)
        self.assertIn("Ya estaba guardado en %s (mismo contenido): no guardé otro parche; le agregué la ficha"
                      % legacy.resolve(), out)
        self.assertNotIn("Setup guardado como parche", out)
        self.assertIn("el setup ya estaba guardado y ahora tiene su ficha", out)
        ficha = json.loads(Path(str(legacy) + ".json").read_text(encoding="utf-8"))
        self.assertEqual((ficha["cableados_a_mano"], ficha["applicationId"], ficha["estado"]), ([ACTIVITY], PKG, "vigente"))
        self.assertEqual(list(self.patches.glob("perf-setup-*.patch")), [])  # ningún parche nuevo
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("- Setup: en parche `herramientas/perf-setup-viejo.patch`", agents)
        self.assertNotIn("git apply herramientas", agents)
        # otra vez: la ficha queda comprobada con esta versión; y la siguiente, no había nada nuevo, y lo dice
        self.assertIn("le completé la ficha: la versión de la skill", self.good("setup", "--guardar"))
        self.assertIn("no guardé otro parche (no había nada nuevo)", self.good("setup", "--guardar"))


class ReviewFixesATest(MigrationBase):
    """Lo que encontró el doble check del grupo A."""

    def test_la_linea_vieja_duplicada_junto_al_bloque_se_quita(self):
        self.legacy()
        self.good("setup", "--reponer", "--archivos", ACTIVITY)
        agents = self.root / "AGENTS.md"
        text = agents.read_text(encoding="utf-8")
        write(agents, text.replace("## DoD", LEGACY_LINE % "herramientas/perf-setup-viejo.patch" + "\n## DoD"))
        self.assertIn("tiene además la línea de una versión anterior", self.good("setup", "--estado"))
        self.good("setup", "--guardar")
        self.assertNotIn("git apply herramientas", agents.read_text(encoding="utf-8"))

    def test_el_plan_con_sufijo_no_contradice_la_ficha(self):
        legacy = self.legacy()
        self.good("setup", "--reponer", "--archivos", ACTIVITY)
        self.good("setup", "--quitar")
        folder = self.investigation(plan={"paquete": PKG + ".profiling", "flujos": {"a": {"recorrido": "true"}}})
        out = self.good("setup", "--reponer", "--carpeta", folder)
        self.assertIn("Setup repuesto con su parche (%s)" % legacy.resolve(), out)

    def test_sin_circulo_despues_de_migrar(self):
        # ronda 2: tras migrar un parche viejo, actualizar sin cambios y guardar deja la ficha con esta versión
        self.legacy()
        self.good("setup", "--reponer", "--archivos", ACTIVITY)
        first = self.good("setup", "--estado")
        self.assertIn("instrumentar --modulo app", first)  # la ficha de un parche viejo no tiene versión
        self.good("setup", "--guardar")
        second = self.good("setup", "--estado")
        self.assertNotIn("instrumentar --modulo app", second)
        self.assertIn("el setup está listo para medir", second)

    def test_guardar_sin_archivos_no_avala_lo_que_no_reconoce(self):
        legacy = self.legacy()
        tmp = self.dir / "aplicar.patch"
        write(tmp, legacy.read_text(encoding="utf-8"))
        git(self.root, "apply", str(tmp))
        error = self.bad("setup", "--guardar")
        self.assertIn("toca archivos que no reconozco como del setup: %s" % ACTIVITY, error)
        self.assertIn("setup --guardar --archivos %s" % ACTIVITY, error)
        self.assertFalse(Path(str(legacy) + ".json").exists())


class AgentsSymlinkTest(MigrationBase):
    """A4: un AGENTS.md que es un enlace simbólico sigue siéndolo después de migrar la línea vieja."""

    def test_el_enlace_se_mantiene(self):
        self.legacy()
        real = self.root / "docs" / "agentes.md"
        write(real, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        (self.root / "AGENTS.md").unlink()
        os.symlink(os.path.join("docs", "agentes.md"), str(self.root / "AGENTS.md"))
        self.good("setup", "--reponer", "--archivos", ACTIVITY)
        self.assertTrue((self.root / "AGENTS.md").is_symlink())
        text = real.read_text(encoding="utf-8")
        self.assertIn("- Setup: en parche `herramientas/perf-setup-viejo.patch`", text)
        self.assertNotIn("git apply herramientas", text)


class AppIdTest(SetupBase):
    """A3: el applicationId de la ficha, en orden: --paquete, el plan, AGENTS.md y el build.gradle de la variante medida.
    Si no lo encuentra, lo dice y da el comando con --paquete."""

    def no_app_in_agents(self):
        write(self.root / "AGENTS.md", AGENTS.replace("- applicationId: %s\n" % PKG, ""))

    def test_del_build_gradle_con_el_sufijo_de_la_variante(self):
        self.no_app_in_agents()
        self.instrument()
        gradle = self.root / "app" / "build.gradle.kts"
        write(gradle, gradle.read_text(encoding="utf-8").replace(
            "android {\n", "android {\n    defaultConfig {\n        applicationId = \"com.example.app\"\n    }\n").replace(
            "initWith(getByName(\"release\"))\n", "initWith(getByName(\"release\"))\n            applicationIdSuffix = \".perf\"\n"))
        out = self.good("setup", "--guardar", *WIRING)
        self.assertIn("app com.example.app.perf (de app/build.gradle.kts: applicationId + applicationIdSuffix de profiling)",
                      out)
        self.assertEqual(self.saved()[1]["applicationId"], "com.example.app.perf")

    def test_del_plan_de_la_investigacion(self):
        self.no_app_in_agents()
        folder = self.investigation(plan={"paquete": "com.example.app.dev", "flujos": {"a": {"recorrido": "true"}}})
        self.instrument()
        out = self.good("setup", "--guardar", "--carpeta", folder, *WIRING)
        self.assertIn("(de el plan de la investigación)", out)
        self.assertEqual(self.saved()[1]["applicationId"], "com.example.app.dev")

    def test_sin_dato_lo_dice_y_da_el_comando(self):
        self.no_app_in_agents()
        self.instrument()
        out = self.good("setup", "--guardar", *WIRING)
        self.assertIn("No encontré el applicationId medido", out)
        self.assertRegex(out, r"setup --vigente \S+perf-setup-\S+\.patch --paquete`")
        patch, ficha = self.saved()
        self.assertIsNone(ficha["applicationId"])
        result = self.run_perf("setup", "--vigente", patch, "--paquete", PKG)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Completé la ficha del parche: applicationId %s (de --paquete)" % PKG, result.stdout)
        self.assertEqual(self.saved()[1]["applicationId"], PKG)


class OldPatchTest(MigrationBase):
    """A5: después de la primera `--reponer` correcta con el parche nuevo, `setup --estado` dice que el viejo ya no hace
    falta y da el `mv -n` a respaldos/ (nunca lo borra)."""

    def test_el_parche_viejo_se_ofrece_mover(self):
        legacy = self.legacy()
        self.good("setup", "--reponer", "--archivos", ACTIVITY)
        mark = self.root / "app" / "src" / "perf" / "kotlin" / "com" / "example" / "app" / "perf" / "MarkTrace.kt"
        write(mark, mark.read_text(encoding="utf-8") + "// plantilla nueva\n")  # como `instrumentar --actualizar`
        self.good("setup", "--guardar", "--quitar")
        loose = self.patches / "perf-setup-antiguo.patch.sin-ficha"
        write(loose, "viejo\n")
        state = self.good("setup", "--estado")
        self.assertNotIn("Ya no hace falta", state)  # todavía no se repuso el nuevo: el viejo es el respaldo
        self.good("setup", "--reponer")
        state = self.good("setup", "--estado")
        self.assertIn("Ya no hace falta: %s" % legacy.resolve(), state)
        self.assertIn("Ya no hace falta: %s (apartado como .sin-ficha" % loose.resolve(), state)
        moves = [command for command in commands_in(state) if " mv -n " in command]
        self.assertEqual(len(moves), 2, state)
        for command in moves:
            done = run_shell(command, self.env)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.patches / "respaldos" / legacy.name).is_file())
        self.assertTrue((self.patches / "respaldos" / (legacy.name + ".json")).is_file())
        self.assertTrue((self.patches / "respaldos" / loose.name).is_file())
        self.assertFalse(legacy.exists())
        self.assertNotIn("Ya no hace falta", self.good("setup", "--estado"))



# ── B · `siguiente` guía sola ────────────────────────────────────────────────
TWO_FLOWS = {"paquete": "com.example.app", "hz": 60, "principales": ["abrir_ms"], "profundidad": "triage",
             "flujos": {
                 "catalogo-lista": {"recorrido": "true", "titulo": "Abrir la lista del catálogo",
                                    "metricas_usuario": [{"nombre": "abrir_ms", "desde": {"marca": "MARK abrir"},
                                                          "hasta": {"marca": "MARK lista_visible"}}]},
                 "catalogo-repeticion": {"recorrido": "true", "tipo": "repeticion", "ciclos": 5,
                                         "proposito": "repetición para memoria: abre y cierra el detalle ×5 a propósito"}},
             "mejoras": []}


def flows_record(**flows):
    return {name: {"corridas": runs, "fecha": "2026-11-05T10:0%d:00" % index}
            for index, (name, runs) in enumerate(sorted(flows.items()))}


class PlanOptionsTest(PerfBase):
    """B1 y B2: las opciones del plan en todos los comandos y todos los flujos en cada fase, en orden."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = json.loads(json.dumps(TWO_FLOWS))
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))

    def phases(self, record):
        write(self.folder / "fases.json", json.dumps(record))

    def captures(self):
        title, steps = perf.next_steps(self.folder, self.plan)
        return title, steps, [step["texto"] for step in steps if step["tipo"] == "terminal" and " capturar " in step["texto"]]

    def test_todos_los_flujos_con_memoria_en_cada_comando(self):
        self.plan["memoria"] = True
        _, steps, captures = self.captures()
        order = next(step for step in steps if step["tipo"] == "avisos" and step["titulo"] == "Flujos del plan, en este orden")
        self.assertIn("2. catalogo-repeticion: repetición para memoria: abre y cierra el detalle ×5 a propósito",
                      order["lineas"])
        flows = [re.search(r"--flujo (\S+)", text).group(1) for text in captures]
        kinds = ["prueba" if "--prueba" in text else re.search(r"--fase (\S+)", text).group(1) for text in captures]
        self.assertEqual(list(zip(flows, kinds)), [("catalogo-lista", "prueba"), ("catalogo-repeticion", "prueba"),
                                                   ("catalogo-lista", "antes"), ("catalogo-repeticion", "antes")])
        self.assertTrue(all(text.endswith(" --memoria") for text in captures), captures)
        self.assertTrue(all("--corridas 3" in text for text in captures if "--fase" in text))

    def test_un_flujo_de_repeticion_lleva_memoria_aunque_el_plan_no_la_diga(self):
        _, _, captures = self.captures()
        self.assertTrue(all(text.endswith("--memoria") for text in captures if "catalogo-repeticion" in text))
        self.assertFalse(any(text.endswith("--memoria") for text in captures if "catalogo-lista" in text))

    def test_corridas_del_plan(self):
        self.plan["profundidad"] = "riguroso"
        self.plan["corridas"] = 7
        _, _, captures = self.captures()
        self.assertTrue(all("--corridas 7" in text for text in captures if "--fase" in text), captures)

    def test_da_igual_que_flujo_se_midio_ultimo(self):
        # riguroso: el control del segundo flujo ya está y su antes no; `siguiente` lo pide, venga de donde venga
        self.plan["profundidad"] = "riguroso"
        self.plan["mejoras"] = [{"id": "M1", "titulo": "x", "estado": "propuesta"}]
        write(self.folder / "plan.json", json.dumps(self.plan))
        tests = {"catalogo-lista": {"fecha": "2026-11-05T09:00:00", "marcas_ok": True},
                 "catalogo-repeticion": {"fecha": "2026-11-05T09:01:00", "marcas_ok": True}}
        self.phases({"prueba": {"flujos": tests},
                     "antes": {"fecha": "2026-11-05T10:00:00", "corridas": 10,
                               "flujos": flows_record(**{"catalogo-lista": 10})},
                     "control": {"fecha": "2026-11-05T11:00:00", "corridas": 20,
                                 "flujos": flows_record(**{"catalogo-lista": 10, "catalogo-repeticion": 10})}})
        for flow in ("catalogo-lista", "catalogo-repeticion", None):
            _, steps = perf.next_steps(self.folder, self.plan, flow)
            texts = [step.get("texto", "") for step in steps if step["tipo"] == "terminal"]
            self.assertTrue(any("--flujo catalogo-repeticion --fase antes" in text for text in texts), (flow, texts))

    def test_la_prueba_del_otro_flujo_aunque_la_del_primero_ya_corrio(self):
        self.phases({"prueba": {"flujos": {"catalogo-lista": {"fecha": "2026-11-05T09:00:00", "marcas_ok": True}}}})
        _, steps, captures = self.captures()
        texts = [step.get("texto", "") for step in steps if step["tipo"] == "terminal"]
        test = next(index for index, text in enumerate(texts) if "--flujo catalogo-repeticion --prueba" in text)
        before = next(index for index, text in enumerate(texts) if "--flujo catalogo-repeticion --fase antes" in text)
        self.assertLess(test, before)

    def test_el_segundo_flujo_que_falta_va_antes_del_diagnostico(self):
        write(self.folder / "prueba" / "catalogo-lista_1.perfetto-trace.gz", "x")
        self.phases({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 3,
                               "flujos": flows_record(**{"catalogo-lista": 3})},
                     "prueba": {"flujos": {"catalogo-lista": {"fecha": "2026-11-05T09:00:00", "marcas_ok": True},
                                           "catalogo-repeticion": {"fecha": "2026-11-05T09:01:00", "marcas_ok": True}}}})
        title, steps, captures = self.captures()
        texts = [step.get("texto", "") for step in steps]
        at = next(index for index, text in enumerate(texts) if "--flujo catalogo-repeticion --fase antes" in text)
        diagnosis = next(index for index, text in enumerate(texts) if " diagnostico " in text)
        self.assertLess(at, diagnosis)
        self.assertNotIn("--flujo catalogo-lista --fase antes", " ".join(captures))
        self.assertIn("el flujo catalogo-lista ya midió esta fase", steps[at]["que"])

    def test_capturar_usa_la_memoria_del_plan(self):
        # sin dispositivo: la línea sale antes de tocar nada
        self.plan["memoria"] = True
        write(self.folder / "plan.json", json.dumps(self.plan))
        result = self.perf("capturar", "--plan", self.folder / "plan.json", "--flujo", "catalogo-lista", "--prueba")
        self.assertIn("--memoria: el plan la pide para el flujo catalogo-lista", result.stdout)
        self.plan["memoria"] = False
        write(self.folder / "plan.json", json.dumps(self.plan))
        result = self.perf("capturar", "--plan", self.folder / "plan.json", "--flujo", "catalogo-lista", "--prueba",
                           "--memoria")
        self.assertIn("⚠ --memoria va en contra del plan", result.stdout)


class DiagnoseAllFlowsTest(DeviceBase):
    """B3: `diagnostico` procesa la mediana y la peor de cada flujo medido y dice cuáles cubrió."""

    def test_los_dos_flujos(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["lista"] = {"inicio": "MainActivity", "recorrido": "true"}
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.tp_outputs(GOOD)
        for flow in ("home", "lista"):
            self.ok("capturar", "--plan", self.plan, "--flujo", flow, "--fase", "antes", "--corridas", "2",
                    "--calentamiento", "0", "--sin-compilar")
        out = self.ok("diagnostico", "--carpeta", self.plan.parent)
        self.assertRegex(out, r"flujos cubiertos: home \(corrida \d, mediana[^)]*\); lista \(corrida \d, mediana")
        text = (self.plan.parent / "diagnostico.md").read_text(encoding="utf-8")
        self.assertIn("# Diagnóstico · home · antes", text)
        self.assertIn("# Diagnóstico · lista · antes", text)
        self.assertIn("_Flujos cubiertos: home", text)
        only = self.ok("diagnostico", "--carpeta", self.plan.parent, "--flujo", "lista")
        self.assertIn("Sin cubrir (pediste --flujo): home", only)


class MarksPerInvestigationTest(PerfBase):
    """B4 y B5: el parche de marcas vigente es de la investigación y de sus repos; las rutas se comparan resueltas."""

    def setUp(self):
        super().setUp()
        for name in ("proyecto", "modulo-pagos"):
            (self.dir / name).mkdir()
        self.root = init_repo(self.dir / "proyecto")
        write(self.root / "app" / "Lista.kt", "class Lista {\n    fun a() = 1\n}\n")
        self.sibling = init_repo(self.dir / "modulo-pagos")
        write(self.sibling / "pagos" / "Pago.kt", "class Pago {\n    fun b() = 2\n}\n")
        commit_all(self.root)
        commit_all(self.sibling)
        parches = self.root / "reports" / "perf" / "parches"
        write(self.root / "AGENTS.md", "# P\n\n## Rendimiento\n\n- Carpeta de parches: `reports/perf/parches`\n")
        commit_all(self.root, "agents")
        write(self.root / ".git" / "info" / "exclude", "/reports/\n")
        self.parches = parches
        self.folder = self.root / "reports" / "perf" / "catalogo-lista" / "2026-03-02"
        write(self.folder / "plan.json", json.dumps(TWO_FLOWS))
        state = (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8").replace(
            "| --- | --- | --- | --- | --- |\n\n\"Altera\"",
            "| --- | --- | --- | --- | --- |\n| `pagos/Pago.kt` | ../modulo-pagos | marca | — | no |\n\n\"Altera\"", 1)
        write(self.folder / "estado.md", state)

    def marks(self, repo, rel, name):
        path = repo / rel
        original = path.read_text(encoding="utf-8")
        write(path, original.replace("fun b() = 2\n", "fun b() = 2\n    // MarkTrace.mark(\"pago\")\n"))
        data = git(repo, "diff")
        write(path, original)
        patch = self.parches / name
        write(patch, data)
        return patch

    def test_no_ofrece_parches_de_otra_investigacion(self):
        mine = self.marks(self.sibling, "pagos/Pago.kt", "catalogo-lista-2026-03-02-marcas-modulo-pagos-20261101-1000.patch")
        other = self.marks(self.sibling, "pagos/Pago.kt", "detalle-2026-02-01-marcas-modulo-pagos-20261102-1000.patch")
        found = perf.marks_patches(self.folder, self.root.resolve(), TWO_FLOWS)
        self.assertEqual(list(found["vigente"].values()), [Path(os.path.realpath(str(mine)))])
        self.assertEqual(found["elegidos"], {})
        self.assertNotIn(str(other), json.dumps({str(k): str(v) for k, v in found["vigente"].items()}))

    def test_con_varios_de_la_misma_investigacion_elige_el_ultimo(self):
        first = self.marks(self.sibling, "pagos/Pago.kt", "catalogo-lista-2026-03-02-marcas-modulo-pagos-20261101-1000.patch")
        last = self.marks(self.sibling, "pagos/Pago.kt", "catalogo-lista-2026-03-02-marcas-modulo-pagos-20261103-0900.patch")
        found = perf.marks_patches(self.folder, self.root.resolve(), TWO_FLOWS)
        top = Path(os.path.realpath(str(self.sibling)))
        self.assertEqual(found["vigente"], {top: Path(os.path.realpath(str(last)))})
        self.assertEqual(found["elegidos"][top][1], [Path(os.path.realpath(str(first)))])

    def test_repo_hermano_y_carpeta_enlazada(self):
        # el parche registrado como vigente en estado.md, con una ruta que pasa por un enlace simbólico
        patch = self.marks(self.sibling, "pagos/Pago.kt", "catalogo-lista-2026-03-02-marcas-modulo-pagos-20261101-1000.patch")
        os.symlink(str(self.root / "reports"), str(self.root / "informes"))
        linked = self.root / "informes" / "perf" / "parches" / patch.name
        result = subprocess.run(perf_argv(SCRIPT) + ["marcas", "--carpeta",
                                 os.path.relpath(str(self.folder), str(self.root)), "--vigente", str(linked)],
                                cwd=str(self.root), env=dict(ENV, HOME=str(self.dir)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("parche de marcas vigente de %s" % os.path.realpath(str(self.sibling)), result.stdout)
        self.assertNotIn("no existe o no es de ningún repo", result.stdout)
        found = perf.marks_patches(self.folder, self.root.resolve(), TWO_FLOWS)
        self.assertEqual(found["sin_repo"], [])
        self.assertEqual(list(found["vigente"].values()), [Path(os.path.realpath(str(patch)))])



LISTA = ("package com.example.app\n\nimport com.example.app.red.Red\n\nclass Lista {\n    fun a() = 1\n    fun b() = 2\n"
         "    fun c() = 3\n    fun d() = 4\n    fun e() = 5\n    fun f() = 6\n    fun g() = 7\n}\n")
# la marca va en medio del archivo (un hunk que no empieza en la línea 1: git lo aplica con desplazamiento)
LISTA_MARKED = LISTA.replace("    fun e() = 5\n", "    fun e() = 5\n    // MarkTrace.mark(\"lista_visible\")\n")
TRIAGE_PLAN = {"paquete": "com.example.app", "profundidad": "triage", "principales": ["abrir_ms"],
               "flujos": {"catalogo-lista": {"recorrido": "true"}},
               "mejoras": [{"id": "M1", "titulo": "Una sola llamada al abrir la lista", "estado": "propuesta",
                            "metrica": "abrir_ms"}]}


class TriageBase(PerfBase):
    """Un proyecto con una investigación de triage terminada: reporte inicial, una mejora propuesta y una marca puesta
    en app/Lista.kt (fila de "Cambios temporales")."""

    def setUp(self):
        super().setUp()
        (self.dir / "proyecto").mkdir()
        self.root = init_repo(self.dir / "proyecto")
        write(self.root / "app" / "Lista.kt", LISTA)
        write(self.root / "AGENTS.md", "# P\n\n## Rendimiento\n\n- applicationId: com.example.app\n\n## DoD\n\n1. `true`\n")
        commit_all(self.root, "base")
        write(self.root / ".git" / "info" / "exclude", "/reports/\n")
        self.folder = self.root / "reports" / "perf" / "catalogo-lista" / "2026-03-02"
        self.rel = os.path.relpath(str(self.folder), str(self.root))
        write(self.folder / "plan.json", json.dumps(TRIAGE_PLAN))
        state = (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8").replace(
            "| --- | --- | --- | --- | --- |\n\n\"Altera\"",
            "| --- | --- | --- | --- | --- |\n| `app/Lista.kt` | . | marca | — | no |\n\n\"Altera\"", 1).replace(
            "| --- | --- | --- | --- | --- | --- |\n",
            "| --- | --- | --- | --- | --- | --- |\n| H1 | la lista tarda | abrir_ms + `app/Lista.kt:7` | dos llamadas | bug | — |\n",
            1)
        write(self.folder / "estado.md", state)
        write(self.folder / "fases.json", json.dumps({"antes": {"fecha": "2026-03-02T10:00:00", "corridas": 3,
                                                                 "commit": git(self.root, "rev-parse", "HEAD").strip(),
                                                                 "flujos": {"catalogo-lista": {"corridas": 3}}}}))
        write(self.folder / "diagnostico.md", "x\n")
        write(self.folder / "reporte-inicial-dev.md", "# reporte\n")
        write(self.root / "app" / "Lista.kt", LISTA_MARKED)
        self.env = dict(ENV, HOME=str(self.dir))

    def run_in(self, *args):
        return subprocess.run(perf_argv(SCRIPT) + [str(a) for a in args], cwd=str(self.root),
                              env=self.env, capture_output=True, text=True, encoding="utf-8")

    def ok_in(self, *args):
        result = self.run_in(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(ends_with_step(result.stdout), "sin paso al final:\n" + result.stdout)
        self.assertEqual(pasteable(result.stdout)[1], [], result.stdout)
        return result.stdout

    def plan(self):
        return perf.load_plan(self.folder / "plan.json")


class TriageChoiceTest(TriageBase):
    """B6: un triage con mejoras termina en tres caminos excluyentes, nunca con `cerrar` como paso 1."""

    def test_elige_uno(self):
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("triage terminado · elige qué hacer con las mejoras", out)
        self.assertIn("Elige uno (son caminos distintos", out)
        options = re.findall(r"^\s+([ABC])\. (.+?) · cuándo conviene", out, re.M)
        self.assertEqual([name for _, name in options], ["Aplicar ahora", "Pausar para después", "Cerrar del todo"])
        commands = commands_in(out)
        self.assertTrue(commands[0].endswith("decidir --carpeta %s --profundidad riguroso" % self.rel), commands)
        self.assertTrue(commands[1].endswith("pausar --carpeta %s" % self.rel))
        self.assertTrue(commands[2].endswith("cerrar --carpeta %s" % self.rel))
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("**Elige uno de los caminos (no van en orden):**", state)

    def test_cerrar_del_todo(self):
        self.ok_in("cerrar", "--carpeta", self.rel, "--dod")
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("triage cerrado", out)
        self.assertIn(perf.NO_STEPS_LEFT, out)


class PauseResumeTest(TriageBase):
    """B7 y B8: pausar quita las marcas con su parche y anota los commits; reanudar las repone, revisa el código citado y
    la línea base y da la decisión."""

    def test_pausar_y_reanudar(self):
        report = (self.folder / "reporte-inicial-dev.md").read_text(encoding="utf-8")
        out = self.ok_in("pausar", "--carpeta", self.rel)
        self.assertIn("En pausa: triage terminado, lista para pasar a riguroso", out)
        self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), LISTA)  # marca quitada
        self.assertEqual(git(self.root, "status", "--short").strip(), "")
        pause = json.loads((self.folder / "pausa.json").read_text(encoding="utf-8"))
        self.assertEqual(list(pause["commits"].values()), [git(self.root, "rev-parse", "HEAD").strip()])
        self.assertIn("sí · perf.py pausar", (self.folder / "estado.md").read_text(encoding="utf-8"))
        self.assertEqual((self.folder / "reporte-inicial-dev.md").read_text(encoding="utf-8"), report)
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("en pausa: triage terminado", out)
        self.assertTrue(commands_in(out)[0].endswith("reanudar --carpeta %s" % self.rel))
        # el código citado por un hallazgo cambia mientras está en pausa
        write(self.root / "app" / "Lista.kt", "// cabecera\n// otra\n" + LISTA)
        commit_all(self.root, "cambio del equipo")
        simulated = self.ok_in("reanudar", "--carpeta", self.rel, "--simular")
        self.assertIn("app/Lista.kt:7 se movió a ~9 (+2 líneas)", simulated)
        self.assertNotIn("MarkTrace", (self.root / "app" / "Lista.kt").read_text(encoding="utf-8"))
        out = self.ok_in("reanudar", "--carpeta", self.rel)
        self.assertIn("2. Marcas: repuestas en proyecto con ", out)  # 0.18.0 · P3: el repo, por su carpeta
        self.assertIn("MarkTrace", (self.root / "app" / "Lista.kt").read_text(encoding="utf-8"))
        self.assertIn("4. La línea base no sirve", out)
        self.assertIn("rehacer antes", out)
        self.assertTrue(commands_in(out)[-1].endswith("decidir --carpeta %s --profundidad riguroso" % self.rel))
        rows = perf.temp_changes((self.folder / "estado.md").read_text(encoding="utf-8"))
        self.assertFalse(rows[0]["revertido"])
        self.assertTrue(json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))["antes"]["rehacer"])

    def test_cerrada_con_sin_setup_en_0140_se_reanuda(self):
        # como la dejaba `cerrar --sin-setup` de 0.14.0: marcas quitadas con su parche, setup "puesto (--sin-setup)"
        patch = self.folder / "parches" / "catalogo-lista-2026-03-02-temporales-proyecto-20261101-1000.patch"
        write(patch, git(self.root, "diff"))
        write(self.root / "app" / "Lista.kt", LISTA)
        state = (self.folder / "estado.md").read_text(encoding="utf-8").replace(
            "| marca | — | no |", "| marca | — | sí · perf.py cerrar 2026-11-01 · parche: %s |" % patch)
        write(self.folder / "estado.md", state)
        write(self.folder / "cierre-setup.json", json.dumps({"setup": "puesto (--sin-setup)", "fecha": "2026-11-01T10:00:00"}))
        write(self.folder / "cierre.json", json.dumps({"quitados": 1, "dod": "ok"}))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("en pausa", out)
        self.assertIn("Se cerró con `cerrar --sin-setup` en una versión anterior", out)
        self.ok_in("reanudar", "--carpeta", self.rel)
        self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), LISTA_MARKED)


class AllInvestigationsTest(TriageBase):
    """B9: `estado` sin --carpeta lista todas las investigaciones; `nuevo` avisa de las marcas de otra."""

    def test_estado_y_nuevo(self):
        other = self.root / "reports" / "perf" / "detalle" / "2026-03-05"
        write(other / "plan.json", json.dumps(dict(TRIAGE_PLAN, profundidad="riguroso", mejoras=[])))
        write(other / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        out = self.ok_in("estado")
        self.assertIn("- %s · abierta · triage terminado" % self.rel, out)
        self.assertIn("Marcas puestas: .: app/Lista.kt", out)
        self.assertIn("Mejoras aplicadas: ninguna · pendientes: M1", out)
        self.assertIn("- reports/perf/detalle/2026-03-05 · abierta", out)
        self.assertEqual(len([c for c in commands_in(out) if " siguiente --carpeta " in c]), 2)
        self.ok_in("pausar", "--carpeta", self.rel)
        self.assertIn("- %s · en pausa" % self.rel, self.ok_in("estado"))
        # nuevo, con otra investigación con marcas puestas: avisa y ofrece pausarla
        self.ok_in("reanudar", "--carpeta", self.rel)
        result = self.run_in("nuevo", "--paquete", "com.example.app", "--flujo", "otro", "--carpeta",
                             "reports/perf/otro/2026-03-09")
        self.assertIn("La investigación %s tiene marcas puestas (app/Lista.kt)" % self.rel, result.stdout)
        self.assertIn("pausar --carpeta %s" % self.rel, result.stdout)


class InterruptedTest(TriageBase):
    """B10: una captura, una traza en el dispositivo y un reporte que se cortaron sin terminar."""

    def dead_pid(self):
        done = subprocess.run(["/bin/sh", "-c", "echo $$"], capture_output=True, text=True)
        return int(done.stdout.strip())

    def test_captura_y_traza_en_el_dispositivo(self):
        bin_dir = self.dir / "bin"
        executable(bin_dir / "adb", "#!/bin/sh\necho \"$@\" >> %s\ncase \"$*\" in\n  *devices*) printf 'List of devices "
                                    "attached\\nemulator-5554\\tdevice\\n' ;;\n  *'echo viva'*) echo viva ;;\n"
                                    # tras el kill -TERM, Perfetto ya no está (sin esto, wait_perfetto espera 30 s)
                                    "  *'[ -d /proc/'*) exit 1 ;;\nesac\n"
                   % (self.dir / "adb.log"))
        self.env = dict(self.env, PATH="%s:%s" % (bin_dir, os.environ["PATH"]))
        partial = self.folder / "antes" / "catalogo-lista_2.perfetto-trace"
        write(partial, "a medias")
        write(self.folder / ".en-curso.json", json.dumps({
            "comando": "capturar", "fase": "antes", "flujo": "catalogo-lista", "corrida": 2, "objetivo": 3, "validas": 1,
            "inicio_corridas": 0, "traza": str(partial), "pid": self.dead_pid(), "inicio": "2026-03-02T10:00:00",
            "registro": {"fecha": "2026-03-02T10:00:00", "corridas": 1, "skill": perf.VERSION},
            "perfetto": {"pid": "4242", "remota": "/data/misc/perfetto-traces/hbperf-1.perfetto-trace",
                         "serial": "emulator-5554"}}))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("quedó algo a medias: la captura de antes del flujo catalogo-lista se interrumpió buscando la "
                      "corrida 1 (ninguna válida en metricas.csv todavía)", out)  # 0.16.0: el número sale de los datos
        self.assertIn("Interrumpir es seguro", out)
        self.assertTrue(commands_in(out)[0].endswith("recuperar --carpeta %s" % self.rel))
        out = self.ok_in("recuperar", "--carpeta", self.rel)
        self.assertIn("Perfetto: detenido (proceso 4242) y traza borrada del dispositivo", out)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("kill -TERM 4242", log)
        self.assertIn("rm -f /data/misc/perfetto-traces/hbperf-1.perfetto-trace", log)
        self.assertFalse(partial.exists())
        self.assertEqual(len(list(self.folder.glob("antes-descartada-*/catalogo-lista_2.perfetto-trace"))), 1)
        self.assertFalse((self.folder / ".en-curso.json").exists())

    def test_reporte_cortado(self):
        write(self.folder / ".en-curso.json", json.dumps({"comando": "reporte", "pid": self.dead_pid(),
                                                          "argv": ["reporte", "--carpeta", self.rel, "--inicial", "--html"]}))
        out = self.ok_in("siguiente", "--carpeta", self.rel)
        self.assertIn("el reporte se interrumpió antes de terminar", out)
        out = self.ok_in("recuperar", "--carpeta", self.rel)
        self.assertTrue(commands_in(out)[-1].endswith("reporte --carpeta %s --inicial --html" % self.rel), out)



# ── C · Medición ─────────────────────────────────────────────────────────────
MS = 1_000_000
SEGMENTS = [{"nombre": "abrir", "desde": {"marca": "MARK tab"}, "hasta": {"marca": "MARK lista_visible"}},
            {"nombre": "lista", "desde": {"marca": "MARK lista_visible"}, "hasta": {"marca": "MARK detalle"}}]


def section(ts, name, dur=0):
    return ("seccion", ts * MS, dur * MS, 0, name)


def slice_(ts, dur):
    return ("hilo", ts * MS, dur * MS, 0, "Choreographer#doFrame")


class BorderRuleTest(unittest.TestCase):
    """C1 y C2: cada slice y cada frame cuentan solo donde empiezan; los avisos distinguen un slice que cruza el borde de
    tramos que se solapan de verdad, y dan el cambio exacto del plan."""

    markers = sorted([section(0, "MARK tab"), section(100, "MARK lista_visible"), section(300, "MARK detalle")],
                     key=lambda r: r[1])

    def test_un_slice_que_cruza_el_borde_cuenta_solo_donde_empieza(self):
        main = [slice_(80, 143), slice_(150, 20)]  # el largo empieza en "abrir" y termina dentro de "lista"
        frames = [("frame", 90 * MS, 16 * MS, 0, "None"), ("frame", 110 * MS, 16 * MS, 0, "None")]
        values = {name: value for name, value, _, _ in perf.segment_metrics(self.markers, frames, main, SEGMENTS)[0]}
        self.assertEqual(values["abrir hilo_max_ms"], 143)
        self.assertEqual(values["lista hilo_max_ms"], 20)
        self.assertEqual((values["abrir frames"], values["lista frames"]), (1, 1))
        warnings = perf.segment_overlap_warnings(self.markers, SEGMENTS, sorted(main, key=lambda r: r[1]))
        self.assertTrue(any("cruza el borde entre 'abrir' y 'lista'" in line and "no un solapamiento" in line
                            and "cuenta solo en 'abrir'" in line for line in warnings), warnings)

    def test_tramos_que_se_solapan_de_verdad_dicen_cual_cubre_a_cual_y_el_cambio(self):
        markers = sorted(self.markers + [section(250, "MARK lista_visible")], key=lambda r: r[1])
        warnings = perf.segment_overlap_warnings(markers, SEGMENTS)
        text = " ".join(warnings)
        self.assertIn("se solapan de verdad", text)
        self.assertIn("'abrir' termina 150 ms después de que empieza 'lista'", text)
        self.assertIn("agrega \"cual\": \"primera\" en segmentos[0].hasta (la marca 'MARK lista_visible' sale 2 veces",
                      text)

    def test_metricas_identicas_segun_la_regla_de_la_fase(self):
        rows = []
        for run, value in ((1, 143), (2, 147), (3, 145)):
            for segment in ("abrir", "lista"):
                rows.append({"fase": "antes", "flujo": "f", "metrica": "%s hilo_max_ms" % segment, "corrida": str(run),
                             "valor": value})
        plan = {"flujos": {"f": {"segmentos": SEGMENTS}}}
        old = perf.identical_segment_notes(rows, {"antes": {"corridas": 3}}, plan)
        self.assertIn("puede ser el mismo slice que cruza el borde. `recalcular` aplica la regla del borde", old[0])
        new = perf.identical_segment_notes(rows, {"antes": {"corridas": 3, "reglas": perf.CALC_RULES}}, plan)
        self.assertIn("se solapan de verdad", new[0])
        self.assertIn("cambia segmentos[0].hasta", new[0]) if "cual" in json.dumps(SEGMENTS[0]["hasta"]) else \
            self.assertIn("agrega \"cual\": \"primera\" en segmentos[0].hasta", new[0])

    def test_fases_con_reglas_distintas_piden_recalcular(self):
        plan = {"flujos": {"f": {"segmentos": SEGMENTS}}}
        phases = {"antes": {"corridas": 3}, "control": {"corridas": 3, "reglas": perf.CALC_RULES}}
        self.assertEqual(perf.mixed_rules(phases, plan), (["antes"], ["control"]))
        self.assertIsNone(perf.mixed_rules({"antes": {"corridas": 3}}, plan))


class MeasurementCaptureTest(DeviceBase):
    """C3, C4, C5, C7 y C8 en la captura, con el adb y el trace_processor falsos."""

    def plan_with(self, **flow):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(flow)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        return plan

    def test_servicio_declarado_que_no_aparecio(self):
        self.plan_with(servicios=["GET items/{id}", "GET entregados"])
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("El servicio declarado 'GET entregados' del flujo home no apareció en ninguna llamada: ¿viene "
                      "dentro de la respuesta de otro servicio?", out)
        self.assertIn("quítalo de `servicios`", out)
        state = perf.warnings_lines(self.plan.parent, perf.load_plan(self.plan))
        self.assertTrue(any("'GET entregados'" in line for line in state), state)

    def test_memoria_sin_views_dice_por_que(self):
        self.env["FAKE_MEMINFO"] = "  Java Heap:  2048\n  TOTAL PSS:  51200   TOTAL RSS: 1\n  Activities:  1"
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "1", "--memoria",
                      "--calentamiento", "0", "--sin-compilar")
        self.assertIn("--memoria no leyó las vistas vivas", out)

    def test_recorrido_en_palabras_y_video_de_la_prueba(self):
        script = self.plan.parent / "recorrido.sh"
        write(script, "#!/bin/sh\n# paso: toca la pestaña Pedidos\nadb shell input tap 100 200\n\n"
                      "# paso: baja la lista (vertical, 5 swipes lentos)\nadb shell input swipe 1 2 3 4 900\n\n"
                      "adb shell input tap 5 6\n")
        self.plan_with(recorrido="sh %s" % script, proposito="abrir los pedidos y bajar la lista")
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--prueba")
        self.assertIn("Recorrido en palabras (home):", out)
        self.assertIn("1. toca la pestaña Pedidos", out)
        self.assertIn("2. baja la lista (vertical, 5 swipes lentos)", out)
        self.assertIn("1 paso del recorrido sin `# paso:` (recorrido.sh:8)", out)
        # 0.17.0: el tramo queda en video/<flujo>/ y, sin ffmpeg, se mira con el visor prueba-<flujo>.html
        self.assertTrue((self.plan.parent / "video" / "home" / "parte1.mp4").is_file())
        page = self.plan.parent / "prueba-home.html"
        self.assertTrue(page.is_file())
        self.assertIn("Video de la prueba: %s" % page, out)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        # 0.19.0 · V2: el mismo shell imprime el uptime del dispositivo cuando screenrecord arma la pantalla
        self.assertIn('"screenrecord --verbose --time-limit 180 /sdcard/hbperf-prueba.mp4 | while IFS= read -r l', log)
        # (el screenrecord falso termina solo: VIDEO_STOP lo prueba Fixes0151HelpersTest y en dispositivo se valida)
        self.assertIn("rm -f /sdcard/hbperf-prueba.mp4", log)
        ficha = (self.plan.parent / "ficha.md").read_text(encoding="utf-8")
        self.assertIn("Propósito: abrir los pedidos y bajar la lista", ficha)
        self.assertIn("1. toca la pestaña Pedidos", ficha)
        out = self.ok("siguiente", "--carpeta", self.plan.parent)
        self.assertIn("Mira el video de la corrida de prueba", out)

    def test_uiautomator_en_el_recorrido_se_detiene(self):
        script = self.plan.parent / "recorrido.sh"
        write(script, "#!/bin/sh\nadb shell uiautomator dump /sdcard/x.xml\nadb shell input tap 1 2\n")
        self.plan_with(recorrido="sh %s" % script)
        result = self.perf("capturar", "--plan", self.plan, "--prueba")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("el recorrido vuelca la pantalla dentro de la parte medida (recorrido.sh:2", result.stderr)
        self.assertFalse((self.dir / "adb.log").exists() and "perfetto" in (self.dir / "adb.log").read_text())

    def repetition(self, trace, cycles=5):
        loop = "for i in %s; do python3 -I %s ciclo; done" % (" ".join(str(i) for i in range(cycles)), SCRIPT)
        self.plan_with(recorrido=loop, tipo="repeticion", ciclos=cycles, traza=trace, invalidar_si=[])

    def test_repeticion_sin_traza_mide_la_memoria_entre_ciclos(self):
        self.repetition("sin")
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("corrida de prueba (repetición sin traza)", out)
        self.assertIn("Memoria entre ciclos (prueba): sin evidencia de fuga", out)
        self.assertNotIn("perfetto", (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.env["FAKE_MEMINFO_CRECE"] = "1"
        out = self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "2", "--calentamiento", "0",
                      "--sin-compilar")
        self.assertIn("memoria entre ciclos: sospecha de fuga", out)
        data = {(r["fase"], r["metrica"], str(r["corrida"])): r["valor"]
                for r in perf.read_rows(self.plan.parent / "metricas.csv")}
        self.assertEqual(data[("antes", "ciclos", "1")], 5)
        self.assertEqual(data[("antes", "activities_crecimiento", "1")], 6)

    def test_repeticion_con_traza_liviana_estima_los_ciclos(self):
        self.repetition("liviana")
        self.env["FAKE_PERFETTO_CONFIG"] = str(self.dir / "config.txt")
        self.tp_outputs(GOOD)
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("Captura liviana de hb-performance", (self.dir / "config.txt").read_text(encoding="utf-8"))
        self.assertRegex(out, r"(?i)la traza de la prueba pesa [\d,.]+ MB en 5 ciclos \(~[\d,.]+ MB por ciclo\): bajo el "
                              r"tope de 1000 MB caben unos \d+ ciclos")


class MeasurementHelpersTest(unittest.TestCase):
    """C5 y C6 por unidad: el veredicto de memoria, el corte por tope y el ajuste de 'preparar'."""

    def snapshots(self, activities, views=None):
        views = views or [10] * len(activities)
        items = [{"etiqueta": "inicio", "memoria": {"activities": activities[0], "views": views[0], "java_heap_mb": 20}}]
        items += [{"etiqueta": "ciclo %d" % i, "memoria": {"activities": a, "views": v, "java_heap_mb": 20}}
                  for i, (a, v) in enumerate(zip(activities[1:], views[1:]), start=1)]
        return items

    def test_veredicto_de_memoria(self):
        self.assertEqual(perf.leak_verdict(self.snapshots([1, 1, 1, 1, 1, 1]))[0], "sin evidencia de fuga")
        verdict, why = perf.leak_verdict(self.snapshots([1, 2, 3, 4, 5, 6]))
        self.assertEqual(verdict, "sospecha de fuga")
        self.assertIn("las actividades vivas pasan de 1 a 6 en 5 ciclos", why)
        self.assertEqual(perf.leak_verdict(self.snapshots([1, 1, 1]))[0], "ciclos insuficientes para decirlo")

    def test_corte_por_tope_en_una_linea(self):
        text = perf.cap_reason({"tipo": "repeticion", "ciclos": 12}, 1000, 1_000_000_000, 90)
        self.assertEqual(text, "la traza llegó a 1 GB en el ciclo ~11: baja `ciclos` a 8 o usa \"traza\": \"sin\" en el "
                               "flujo (la memoria se mide igual, entre ciclos)")
        # con pantallas protegidas, "sin" se mide igual con la liviana: no se ofrece
        text = perf.cap_reason({"tipo": "repeticion", "ciclos": 12, "invalidar_si": ["SCREEN *Pago*"]}, 1000,
                               1_000_000_000, 90)
        self.assertNotIn("\"sin\"", text)
        self.assertIn("baja `ciclos` a 8", text)
        self.assertIn("usa el tipo repetición", perf.cap_reason({}, 1000, 1_000_000_000, None))

    def test_preparar_que_falla_igual_propone_el_ajuste(self):
        failures = [("'preparar' terminó con código 1", ())] * 3
        lines = perf.invalid_summary(failures, 5, {".Pedidos": ["Continuar"]}, [".Pedidos"] * 3)
        text = " ".join(lines)
        self.assertIn("'preparar' falló 3 veces dejando la app en la misma pantalla (.Pedidos)", text)
        self.assertIn("espera 3 s más", text)
        self.assertIn("toca el botón con el texto que se ve en esa pantalla ('Continuar')", text)
        self.assertNotIn("<carpeta>", text)
        self.assertNotIn("no cambia lo que se mide", text)
        lines = perf.invalid_summary(failures, 5, {".Pedidos": ["Continuar"]}, [".Pedidos"] * 3,
                                     lambda label: "cd /p && python3 -I perf.py nodos logs/x.xml --texto %s" % label)
        self.assertIn("  Las coordenadas de ese botón, del volcado de esa pantalla:", lines)
        self.assertIn("    cd /p && python3 -I perf.py nodos logs/x.xml --texto Continuar", lines)  # en su propia línea



# ── P · Cierre ───────────────────────────────────────────────────────────────
class DodFormatsTest(PerfBase):
    """P1: `## DoD` con viñetas que nombran el comando, bloques de código y `cd ../repo && …`; lo que no se puede usar se
    cita con su motivo."""

    def test_formatos_y_motivos(self):
        write(self.dir / "AGENTS.md", "# P\n\n## DoD\n\n- Tests unitarios: `./gradlew :app:testDebugUnitTest`\n"
                                      "1. **Compilar**: `./gradlew :app:assembleProfiling`\n"
                                      "- Módulos de otros repos: `cd ../modulo-pagos && ./gradlew test`\n"
                                      "- Y el del módulo: `./gradlew :<módulo>:test`\n- Revisa el diff a mano\n\n"
                                      "```bash\n./gradlew lint\n```\n\n## Git\n\n- x\n")
        commands, skipped = perf.dod_entries(self.dir)
        root = perf.q(self.dir)
        self.assertEqual(commands, ["cd %s && ./gradlew :app:testDebugUnitTest" % root,
                                    "cd %s && ./gradlew :app:assembleProfiling" % root,
                                    "cd %s && cd ../modulo-pagos && ./gradlew test" % root,
                                    "cd %s && ./gradlew lint" % root])
        reasons = dict(skipped)
        self.assertIn("tiene un marcador sin resolver (<módulo>)", reasons["- Y el del módulo: `./gradlew :<módulo>:test`"])
        self.assertIn("no tiene un comando entre acentos graves", reasons["- Revisa el diff a mano"])
        self.assertIn("\"- Y el del módulo: `./gradlew :<módulo>:test`\" (tiene un marcador sin resolver",
                      perf.dod_skipped_text(self.dir))

    def test_el_formato_de_siempre_sigue(self):
        write(self.dir / "AGENTS.md", "# P\n\n## DoD\n\n1. `true`\n2. `./gradlew test`\n")
        self.assertEqual(perf.dod_commands(self.dir), ["cd %s && true" % perf.q(self.dir),
                                                       "cd %s && ./gradlew test" % perf.q(self.dir)])



# ── T · Aceptación de punta a punta: solo lo que imprime la skill ────────────
# Cada caso arranca después de la sesión 1 (que arma el plan) y sigue solo los comandos que imprime `siguiente` (o el
# comando anterior). Las sesiones de chat se simulan escribiendo lo que escribiría la IA; los pasos de terminal se
# ejecutan tal cual. Si un paso necesitara un comando que no salió de la skill, el test no tiene cómo darlo y falla.
T_TRACE = GOOD + '"seccion",100000000,0,0,"MARK abrir"\n"seccion",600000000,0,0,"MARK lista_visible"\n' \
    '"seccion",650000000,0,0,"MARK detalle"\n'
T_AGENTS = ("# Proyecto de ejemplo\n\n## Rendimiento\n\n- applicationId: com.ejemplo.app\n- setup listo\n\n"
            "## DoD\n\n1. `true`\n")


def step_commands(output):
    """[(tipo, comando)] de los pasos que imprimió un comando de perf.py: los numerados ("1. Terminal") y las opciones
    de "Elige uno" ("A. …"), en orden. Solo lo que la skill imprimió: nada se arma a mano."""
    out, pending = [], None
    for line in output.splitlines():
        stripped = line.strip()
        option = re.match(r"^([A-G])\. (.+?) · cuándo conviene", stripped)
        if re.match(r"^\d+\. Terminal \(sin chat\)", stripped):
            pending = "paso"
        elif option:
            pending = "opción " + option.group(2)
        elif pending and stripped.startswith("Terminal (sin chat)"):
            continue
        elif pending and stripped.startswith("cd "):
            out.append((pending, stripped))
            pending = None
        elif pending and stripped.startswith("Tú:"):
            pending = None
    return out


class AcceptanceBase(DeviceBase):
    """Un proyecto con el setup versionado, el adb y el trace_processor falsos y una investigación recién planeada."""

    def setUp(self):
        super().setUp()
        self.root = self.dir / "proyecto"
        self.root.mkdir()
        init_repo(self.root)
        write(self.root / "AGENTS.md", T_AGENTS)
        write(self.root / "app" / "src" / "main" / "kotlin" / "com" / "ejemplo" / "app" / "perf" / "PerfHooks.kt",
              "// Generated by hb-performance\nobject PerfHooks\n")
        write(self.root / "app" / "Lista.kt", LISTA)
        commit_all(self.root, "base")
        write(self.root / ".git" / "info" / "exclude", "/reports/\n")
        self.folder = self.root / "reports" / "perf" / "catalogo" / "2026-03-02"
        self.rel = "reports/perf/catalogo/2026-03-02"
        self.tp_outputs(T_TRACE)
        write(self.root / "recorrido-lista.sh", ROUTE_LISTA)
        (self.dir / "home").mkdir()
        # un HOME vacío y sin la configuración global de git de la máquina
        self.env = dict(self.env, HOME=str(self.dir / "home"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.ran = []

    def perf_in_root(self, *args):
        result = subprocess.run(perf_argv(SCRIPT) + [str(a) for a in args], cwd=str(self.root),
                                env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def run_step(self, command):
        """Ejecuta un comando tal como lo imprimió la skill (en sh, como lo pegaría el usuario)."""
        self.assertTrue(command.startswith("cd "), command)
        self.assertIsNone(re.search(r"<[^>\s][^>]*>", command), command)  # nada sin resolver
        done = subprocess.run(["/bin/sh", "-c", command], env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, command + "\n" + done.stdout + done.stderr)
        self.ran.append(command)
        return done.stdout

    def next_out(self):
        return self.perf_in_root("siguiente", "--carpeta", self.rel)

    def follow(self, output, stop=lambda command: False, choose=None):
        """Corre, en orden, los pasos de terminal de una salida; con opciones, solo la elegida. Devuelve la salida del
        último comando que corrió (o la que recibió, si no había nada que correr)."""
        last = output
        for kind, command in step_commands(output):
            if kind.startswith("opción ") and kind != "opción " + (choose or ""):
                continue
            if stop(command):
                break
            last = self.run_step(command)
        return last

    def session1(self):
        """La sesión 1, simulada: la IA completa la Ficha de estado.md (lo demás lo escribe `nuevo`)."""
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        for placeholder, value in (('<lo que nota el usuario, o "exploratoria">', "la lista tarda en aparecer"),
                                   ("<las de `principales` en plan.json, y el objetivo de cada una>",
                                    "abrir la lista: bajar de 0,5 s"),
                                   ("<variante medida (R8, no depurable, profileable) · backend real o mocks>",
                                    "profileable con R8 · backend de pruebas"),
                                   ("<guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage>",
                                    "guiado · comando · triage"),
                                   ("<UI · asincronía · listas · red>", "Compose · corrutinas · LazyColumn · Retrofit")):
            state = state.replace(placeholder, value)
        write(self.folder / "estado.md", state)

    def make_plan(self, flows, triage=True, **extra):
        self.perf_in_root("nuevo", "--paquete", "com.ejemplo.app", "--flujo", next(iter(flows)), "--carpeta", self.rel,
                          *(["--triage"] if triage else []))
        plan = perf.load_plan(self.folder / "plan.json")
        plan["flujos"] = flows
        plan["principales"] = ["abrir_ms"]
        plan.update(extra)
        write(self.folder / "plan.json", json.dumps(plan))
        self.session1()

    def session2(self, finding="| H1 | La lista tarda | abrir_ms + `app/Lista.kt:7` | pide la lista dos veces | bug | — |"):
        """La sesión 2, simulada: hallazgos, una mejora de un hallazgo confirmado, resúmenes y el reporte inicial."""
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        head, tail = state.split("## Hallazgos", 1)  # el diagnóstico llena antes otras tablas de seis columnas
        state = head + "## Hallazgos" + tail.replace("| --- | --- | --- | --- | --- | --- |\n",
                                                     "| --- | --- | --- | --- | --- | --- |\n%s\n" % finding, 1)
        state = re.sub(r"(## Resumen ejecutivo\n\n).*?(?=\n## )", r"\1Abrir la lista tarda 0,5 s; la causa es una "
                       r"llamada repetida.\n", state, flags=re.S)
        state = re.sub(r"(## Resumen para gerencia\n\n).*?(?=\n## )", r"\1Abrir la lista tarda medio segundo porque "
                       r"se pide dos veces.\n", state, flags=re.S)
        write(self.folder / "estado.md", state)
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"] = [{"id": "M1", "hallazgo": "H1", "titulo": "Pedir la lista una sola vez", "flujo": "catalogo-lista",
                            "metrica": "abrir_ms", "esperado": "la lista aparece antes", "riesgo": "bajo: toca solo la "
                            "carga de la lista", "estado": "propuesta"}]
        write(self.folder / "plan.json", json.dumps(plan))
        return self.perf_in_root("reporte", "--carpeta", self.rel, "--inicial", "--html")


ROUTE_LISTA = "#!/bin/sh\n# paso: toca Pedidos en la barra de abajo; se abre la lista\ntrue\n"
TWO_FLOW_PLAN = {
    "catalogo-lista": {"recorrido": "sh recorrido-lista.sh", "titulo": "Abrir la lista",
                       "ventana": {"desde": {"marca": "MARK abrir"}, "hasta": {"marca": "MARK lista_visible"}},
                       "metricas_usuario": [{"nombre": "abrir_ms", "desde": {"marca": "MARK abrir"},
                                             "hasta": {"marca": "MARK lista_visible"}}]},
    "catalogo-lista-espera": {"escenario_de": "catalogo-lista", "titulo": "tras 3 s", "variables": {"PERF_ESPERA_S": "3"}},
    "catalogo-repeticion": {"tipo": "repeticion", "ciclos": 5, "traza": "liviana",
                            "proposito": "repetición para memoria: abre y cierra el detalle ×5 a propósito",
                            "recorrido": "for i in 1 2 3 4 5; do python3 -I %s ciclo; done" % SCRIPT}}


class AcceptanceT1Test(AcceptanceBase):
    """T1: triage con dos flujos (uno con escenarios y otro de repetición con memoria): ficha → prueba con el recorrido en
    palabras → antes de los dos con memoria → diagnóstico de los dos → "Elige uno" → pausar."""

    def test_t1(self):
        self.make_plan(json.loads(json.dumps(TWO_FLOW_PLAN)))
        out = self.next_out()
        self.assertNotIn("partes sin completar: Ficha", out)  # la sesión 1 la completó
        self.assertIn("Flujos del plan, en este orden:", out)
        prueba = self.run_step(next(c for _, c in step_commands(out) if "--flujo catalogo-lista --prueba" in c))
        self.assertIn("Recorrido en palabras (catalogo-lista):", prueba)
        self.assertIn("1. toca Pedidos en la barra de abajo; se abre la lista", prueba)
        self.assertTrue(any("--flujo catalogo-repeticion --prueba" in c for _, c in step_commands(self.next_out())))
        commands = [command for _, command in step_commands(out)]
        self.assertTrue(any("--flujo catalogo-repeticion --fase antes --corridas 3 --memoria" in c for c in commands), out)
        self.follow(out, stop=lambda command: " diagnostico " in command)
        phases = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(phases["antes"]["flujos"]), ["catalogo-lista", "catalogo-lista-espera", "catalogo-repeticion"])
        rows = perf.read_rows(self.folder / "metricas.csv")
        self.assertTrue(any(r["flujo"] == "catalogo-repeticion" and r["metrica"] == "pss_crecimiento_mb" for r in rows))
        out = self.follow(self.next_out())  # el diagnóstico, de todos los flujos
        self.assertIn("flujos cubiertos: catalogo-lista", out)
        self.assertIn("catalogo-repeticion", out)
        out = self.session2()
        self.assertIn("triage terminado · elige qué hacer con las mejoras", out)
        self.assertNotRegex(out, r"1\. Terminal \(sin chat\) · quita")  # nunca `cerrar` como paso 1
        self.follow(out, choose="Pausar para después")
        out = self.next_out()
        self.assertIn("en pausa: triage terminado", out)
        self.assertTrue(step_commands(out)[0][1].endswith("reanudar --carpeta %s" % self.rel))
        self.assertTrue(all(perf.capture_words(c) is None or "--memoria" in c
                            for c in self.ran if "catalogo-repeticion" in c))


class AcceptanceT2Test(AcceptanceBase):
    """T2: pestañas anidadas con scroll vertical hasta el final y el último ítem, más un flujo de repetición con traza
    liviana, protección de pantallas de pago, un servicio declarado que no aparece y un slice que cruza el borde."""

    def test_t2(self):
        script = self.folder.parent / "recorrido-detalle.sh"
        write(script, "#!/bin/sh\n# paso: toca la pestaña Pendientes (arriba)\nadb shell input tap 300 200\n\n"
                      "# paso: baja la lista del detalle hasta el final (vertical, 5 + 2 swipes lentos)\n"
                      "for i in 1 2 3 4 5 6 7; do adb shell input swipe 540 1600 540 900 900; done\n\n"
                      "# paso: abre el último pedido de la lista\nadb shell input tap 540 1500\n")
        flows = {"detalle": {"recorrido": "sh %s" % script, "invalidar_si": ["SCREEN *Pago*"],
                             "servicios": ["GET items/{id}", "GET pedidos/entregados"],
                             "ventana": {"desde": {"marca": "MARK abrir"}, "hasta": {"marca": "MARK detalle"}},
                             "metricas_usuario": [{"nombre": "abrir_ms", "desde": {"marca": "MARK abrir"},
                                                   "hasta": {"marca": "MARK lista_visible"}}],
                             "segmentos": [{"nombre": "pestana", "titulo": "abrir la pestaña",
                                            "desde": {"marca": "MARK abrir"}, "hasta": {"marca": "MARK lista_visible"}},
                                           {"nombre": "lista", "titulo": "abrir el último pedido",
                                            "desde": {"marca": "MARK lista_visible"}, "hasta": {"marca": "MARK detalle"}}]},
                 "detalle-repeticion": {"tipo": "repeticion", "ciclos": 5, "traza": "liviana",
                                        "invalidar_si": ["SCREEN *Pago*"],
                                        "recorrido": "for i in 1 2 3 4 5; do python3 -I %s ciclo; done" % SCRIPT}}
        self.make_plan(flows)
        # un slice largo del hilo principal que empieza en "pestana" y cruza la marca de corte (600 ms)
        self.tp_outputs(T_TRACE + '"hilo",550000000,143000000,0,"Choreographer#doFrame"\n')
        out = self.next_out()
        prueba = self.run_step(next(c for _, c in step_commands(out) if "--flujo detalle --prueba" in c))
        self.assertIn("Recorrido en palabras (detalle):", prueba)
        self.assertIn("2. baja la lista del detalle hasta el final (vertical, 5 + 2 swipes lentos)", prueba)
        self.assertIn("El servicio declarado 'GET pedidos/entregados' del flujo detalle no apareció", prueba)
        self.assertIn("cruza el borde entre 'pestana' y 'lista'", prueba)
        self.assertIn("no un solapamiento", prueba)
        self.assertTrue((self.folder / "prueba-detalle.html").is_file())  # 0.17.0: sin ffmpeg, el visor del video
        self.follow(self.next_out(), stop=lambda command: " diagnostico " in command)
        rows = perf.read_rows(self.folder / "metricas.csv")
        values = {(r["flujo"], r["metrica"]) for r in rows}
        self.assertIn(("detalle-repeticion", "ciclos"), values)
        lista = [r["valor"] for r in rows if r["metrica"] == "lista hilo_max_ms"]
        pestana = [r["valor"] for r in rows if r["metrica"] == "pestana hilo_max_ms"]
        self.assertEqual(set(pestana), {143})  # el slice cuenta solo donde empieza
        self.assertNotIn(143, lista)
        out = self.follow(self.next_out())
        out = self.session2()
        self.follow(out, choose="Cerrar del todo")
        out = self.follow(self.next_out())  # el DoD después de quitar, si hace falta
        self.assertIn(perf.NO_STEPS_LEFT, self.next_out())


class AcceptanceT3Test(AcceptanceBase):
    """T3: triage → pausar → cambia el código citado por un hallazgo → `reanudar` lo avisa y propone rehacer antes →
    `decidir --profundidad riguroso`. Y una investigación cerrada con `cerrar --sin-setup` en 0.14.0 que se reanuda."""

    def test_t3(self):
        flows = {"catalogo-lista": json.loads(json.dumps(TWO_FLOW_PLAN["catalogo-lista"]))}
        self.make_plan(flows)
        write(self.root / "app" / "Lista.kt", LISTA_MARKED)  # la marca que puso la sesión 1
        state = (self.folder / "estado.md").read_text(encoding="utf-8").replace(
            "| --- | --- | --- | --- | --- |\n\n\"Altera\"",
            "| --- | --- | --- | --- | --- |\n| `app/Lista.kt` | . | marca | — | no |\n\n\"Altera\"", 1)
        write(self.folder / "estado.md", state)
        self.follow(self.next_out(), stop=lambda command: " diagnostico " in command)
        self.follow(self.next_out())
        out = self.session2()
        self.follow(out, choose="Pausar para después")
        self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), LISTA)
        write(self.root / "app" / "Lista.kt", "// cabecera\n// otra\n" + LISTA)
        commit_all(self.root, "cambio del equipo")
        out = self.follow(self.next_out())  # reanudar
        self.assertIn("app/Lista.kt:7 se movió a ~9", out)
        self.assertIn("4. La línea base no sirve", out)
        out = self.follow(out)  # decidir --profundidad riguroso
        self.assertIn("--fase antes --corridas 10 --rehacer", out)

    def test_t3_cerrada_con_sin_setup_en_0140(self):
        # Lo que deja `cerrar --sin-setup` de 0.14.0: la marca quitada con su parche (fila "sí · perf.py cerrar … ·
        # parche: …"), cierre.json con el DoD pendiente, cierre-setup.json y fases.json medido con 0.14.0.
        flows = {"catalogo-lista": json.loads(json.dumps(TWO_FLOW_PLAN["catalogo-lista"]))}
        self.make_plan(flows)
        write(self.root / "app" / "Lista.kt", LISTA_MARKED)
        patch = self.folder / "parches" / "catalogo-2026-03-02-temporales-proyecto-20261101-1000.patch"
        write(patch, git(self.root, "diff"))
        write(self.root / "app" / "Lista.kt", LISTA)
        state = (self.folder / "estado.md").read_text(encoding="utf-8").replace(
            "| --- | --- | --- | --- | --- |\n\n\"Altera\"",
            "| --- | --- | --- | --- | --- |\n| `app/Lista.kt` | . | marca | — | sí · perf.py cerrar 2026-11-01 · parche: "
            "%s |\n\n\"Altera\"" % patch, 1)
        write(self.folder / "estado.md", state)
        write(self.folder / "fases.json", json.dumps({"antes": {
            "fecha": "2026-11-01T09:00:00", "corridas": 3, "skill": "0.14.0", "commit": git(self.root, "rev-parse",
                                                                                            "HEAD").strip(),
            "flujos": {"catalogo-lista": {"corridas": 3, "skill": "0.14.0", "fecha": "2026-11-01T09:00:00"}}}}))
        write(self.folder / "reporte-inicial-dev.md", "x")
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        plan["mejoras"] = [{"id": "M1", "hallazgo": "H1", "titulo": "Pedir la lista una sola vez", "estado": "propuesta"}]
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.folder / "cierre.json", json.dumps({"fecha": "2026-11-01T10:00:00", "quitados": 1,
                                                       "repos": [str(self.root)], "dod": "pendiente"}))
        # lo que escribe `cerrar --sin-setup` de 0.14.0 cuando el setup va en un parche y queda puesto (con el setup
        # versionado no escribe nada del setup: ese cierre no se distingue de un `cerrar` sin la opción)
        write(self.folder / "cierre-setup.json", json.dumps({"setup": "puesto (--sin-setup)",
                                                             "fecha": "2026-11-01T10:00:00"}))
        out = self.next_out()
        self.assertIn("en pausa", out)
        out = self.follow(out)  # reanudar
        self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), LISTA_MARKED)
        self.assertTrue(step_commands(out)[-1][1].endswith("--profundidad riguroso"))
        out = self.follow(out)  # decidir --profundidad riguroso
        self.assertNotIn("otra versión de hb-performance", out)  # 0.14.0 mide igual: se completa, no se rehace
        self.assertIn("--fase antes --corridas 7", out)


class AcceptanceT4Test(PerfBase):
    """T4: los reportes de una investigación de una versión anterior (las dos de fixture más nuevas), regenerados: parte
    principal corta, diffs completos, sin nombres internos, rutas MÉTODO https://… y gerencia con exactamente sus siete
    secciones, sin costo, sin descartados y sin "Un punto técnico"."""

    def regenerate(self, fixture):
        folder = self.dir / fixture
        shutil.copytree(str(ROOT / "tests" / "fixtures" / fixture), str(folder))
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        diff = "".join("+    val linea%d = cargar(%d)\n" % (i, i) for i in range(120))
        write(folder / "cambios" / "M1.diff", "diff --git a/app/Detalle.kt b/app/Detalle.kt\n--- a/app/Detalle.kt\n"
                                               "+++ b/app/Detalle.kt\n@@ -1,0 +1,120 @@\n" + diff)
        applied = next(item for item in plan.get("mejoras") or [] if item.get("estado") == "aplicada")
        applied["cambios"] = [{"diff": "cambios/M1.diff", "repo": ".", "archivos": ["app/Detalle.kt"]}]
        write(folder / "plan.json", json.dumps(plan))
        flow = next(iter(plan["flujos"]))
        extra = "".join("%s,%s,%s,%d,%s,%s,menor,%s\n" % (phase, flow, metric, run, value, unit, family)
                        for phase in ("antes", "despues") for run in range(1, 6)
                        for metric, value, unit, family in (("red GET pedidos/{id} llamadas", 2 if phase == "antes" else 1,
                                                             "llamadas", "app"),
                                                            ("red GET pedidos/{id} ms", 300, "ms", "info")))
        with (folder / "metricas.csv").open("a", encoding="utf-8") as handle:
            handle.write(extra)
        write(folder / "servicios.json", json.dumps({"servicios": {
            "GET pedidos/{id}": "https://api.example.com/v2/pedidos/42"}}))
        self.ok("reporte", "--carpeta", folder, "--html")
        return folder

    def test_t4(self):
        for fixture in ("hb-performance-0.9.0", "hb-performance-0.10.0"):
            with self.subTest(fixture=fixture):
                folder = self.regenerate(fixture)
                dev = (folder / "reporte-final-dev.md").read_text(encoding="utf-8")
                main = dev  # 0.16.0 · R10: sin anexo y sin el tope de 1 500 palabras (el usuario aprobó la estructura)
                page = (folder / "reporte-final-dev.html").read_text(encoding="utf-8")
                self.assertIn("+    val linea119 = cargar(119)", dev)  # el diff completo
                self.assertNotRegex(dev, r"y \d+ líneas más")  # ningún diff truncado
                visible = re.sub(r"```.*?```", "", dev, flags=re.S)
                visible = re.sub(r"`[^`\n]*`", "", visible)  # el código citado entre comillas invertidas
                self.assertNotRegex(visible, r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:ms|pct|mb)\b")
                self.assertIn("GET https://api.example.com/v2/pedidos/42", main)
                self.assertNotIn("pedidos/{id}", main)
                business = (folder / "reporte-final-gerencia.md").read_text(encoding="utf-8")
                self.assertEqual(re.findall(r"^## (.+)$", business, re.M), list(perf.BUSINESS_SECTIONS))
                for word in ("## Costo", "Costo de la investigación", "USD", "Más detalle", "Un punto técnico",
                             "descart", "sin confirmar"):
                    self.assertNotIn(word, business)
                self.assertNotRegex(page, r"<script[^>]*\bsrc=")  # R1: solo el script corto del tema, en la página
                self.assertNotIn('class="anexo"', page)

class AcceptanceT5Test(AcceptanceBase):
    """T5: varias investigaciones abiertas: `estado` sin --carpeta y el aviso de `nuevo`."""

    def test_t5(self):
        flows = {"catalogo-lista": json.loads(json.dumps(TWO_FLOW_PLAN["catalogo-lista"]))}
        self.make_plan(flows)
        write(self.root / "app" / "Lista.kt", LISTA_MARKED)
        state = (self.folder / "estado.md").read_text(encoding="utf-8").replace(
            "| --- | --- | --- | --- | --- |\n\n\"Altera\"",
            "| --- | --- | --- | --- | --- |\n| `app/Lista.kt` | . | marca | — | no |\n\n\"Altera\"", 1)
        write(self.folder / "estado.md", state)
        out = self.perf_in_root("nuevo", "--paquete", PKG, "--flujo", "otro", "--carpeta", "reports/perf/otro/2026-03-09")
        self.assertIn("La investigación %s tiene marcas puestas (app/Lista.kt)" % self.rel, out)
        pause = next(line.strip() for line in out.splitlines() if line.strip().startswith("cd ") and " pausar " in line)
        listing = self.perf_in_root("estado")
        self.assertIn("- %s · abierta" % self.rel, listing)
        self.assertIn("- reports/perf/otro/2026-03-09 · abierta", listing)
        self.assertEqual(len(step_commands(listing)), 2)
        self.run_step(pause)  # el comando que ofreció `nuevo`
        self.assertIn("- %s · en pausa" % self.rel, self.perf_in_root("estado"))


class AcceptanceT6Test(AcceptanceBase):
    """T6: una sesión interrumpida en cada punto (la captura, la traza en el dispositivo y el reporte): `siguiente` da
    `recuperar` y, después, el paso de siempre."""

    def test_t6(self):
        flows = {"catalogo-lista": json.loads(json.dumps(TWO_FLOW_PLAN["catalogo-lista"]))}
        self.make_plan(flows)
        self.follow(self.next_out(), stop=lambda command: " diagnostico " in command)
        dead = int(subprocess.run(["/bin/sh", "-c", "echo $$"], capture_output=True, text=True).stdout)
        partial = self.folder / "antes" / "catalogo-lista_9.perfetto-trace"
        write(partial, "a medias")
        write(self.folder / ".en-curso.json", json.dumps({
            "comando": "capturar", "fase": "antes", "flujo": "catalogo-lista", "corrida": 4, "objetivo": 3, "validas": 0,
            "traza": str(partial), "pid": dead, "perfetto": {"pid": "4242", "remota": "/data/misc/perfetto-traces/x",
                                                              "serial": "emulator-5554"}}))
        self.env["FAKE_PERFETTO_VIVA"] = "1"
        out = self.next_out()
        self.assertIn("quedó algo a medias", out)
        self.follow(out)
        self.assertIn("kill -TERM 4242", (self.dir / "adb.log").read_text(encoding="utf-8"))
        self.assertFalse(partial.exists())
        self.assertIn("diagnostico --carpeta", self.next_out())  # sigue donde iba
        write(self.folder / ".en-curso.json", json.dumps({"comando": "reporte", "pid": dead,
                                                          "argv": ["reporte", "--carpeta", self.rel, "--inicial", "--html"]}))
        out = self.follow(self.next_out())  # recuperar da el comando del reporte
        self.assertTrue(step_commands(out)[-1][1].endswith("reporte --carpeta %s --inicial --html" % self.rel))



# ── E, F, H: costo, velocidad del reporte y textos ───────────────────────────
class PortableShellTest(unittest.TestCase):
    """Nada de lo que la skill genera o recomienda usa comandos que no existen en macOS por defecto (`timeout`)."""

    def test_sin_timeout_ni_comandos_de_linux(self):
        texts = [path for path in (SKILL / "references").rglob("*.md")] + [SKILL / "SKILL.md", SCRIPT,
                                                                           ROOT / "PROMPTS.md"]
        texts += [path for path in (SKILL / "assets").rglob("*") if path.is_file() and path.suffix in (".sh", ".md", ".json")]
        command = re.compile(r"(?:^|&&|;|\||`|\$\(|\bdo\s)\s*(?:g?timeout|sha256sum|readlink\s+-f|sed\s+-i\s+[\"']?s)\s", re.M)
        for path in texts:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(command.search(text), (path, command.search(text) and command.search(text).group(0)))


class CostWarningTest(PerfBase):
    """F1: `consumo` compara cada sesión con la referencia de modelos.md según el tipo de sesión y el tamaño del
    proyecto; si se pasó, lo dice (también en estado.md y en el anexo de costo) y nunca detiene nada."""

    def test_aviso_y_tabla(self):
        folder = self.dir / "inv"
        write(self.dir / "AGENTS.md", "# P\n\n## Rendimiento\n\n- Tamaño del proyecto: mediano\n")
        write(folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {}}}))
        write(folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        out = self.ok("consumo", "--carpeta", folder, "--sesion", "2 · diagnóstico", "--costo", "2.4 USD")
        self.assertIn("⚠ La sesión 2 · diagnóstico costó 2,4 USD; lo esperado es 0,5–1,5 (proyecto mediano: AGENTS.md): "
                      "consumió más de lo que debía", out)
        state = (folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("- ⚠ Costo: la sesión 2 · diagnóstico costó 2,4 USD", state)
        self.assertIn("consumió más de lo que debía", perf.cost_md(folder, {}))
        quiet = self.ok("consumo", "--carpeta", folder, "--sesion", "1 · ficha", "--costo", "1.2 USD")
        self.assertNotIn("1 · ficha costó", quiet)
        self.assertEqual(perf.cost_type("0 · pedido"), "0p")

    def test_el_tamano_por_los_modulos(self):
        write(self.dir / "settings.gradle.kts", "\n".join('include(":m%d")' % i for i in range(30)) + "\n")
        self.assertEqual(perf.project_size(self.dir), ("grande", "30 módulos en settings.gradle"))

    def test_modelos_md_dice_lo_mismo_que_el_script(self):
        text = (SKILL / "references" / "modelos.md").read_text(encoding="utf-8")
        table = text.split("## Costo esperado por sesión")[1].split("\n## ")[0]
        rows = {line.split("|")[1].strip(): [cell.strip() for cell in line.split("|")[2:5]]
                for line in table.splitlines() if line.startswith("| ") and "USD" in line}

        def usd(value):
            return ("%.2f" % value).rstrip("0").rstrip(".").replace(".", ",")

        for kind, name in perf.COST_SESSION_NAMES.items():
            expected = ["%s–%s USD" % (usd(low), usd(high)) for low, high in
                        (perf.COST_REFERENCE[kind][size] for size in ("pequeño", "mediano", "grande"))]
            self.assertEqual(rows[name], expected, name)


class ReportSpeedTest(DeviceBase):
    """F3: `reporte` lee metricas.csv y la línea de tiempo de cada corrida; no vuelve a abrir las trazas. Las corridas viejas sin
    resumen se procesan una sola vez y quedan en caché."""

    def setUp(self):
        super().setUp()
        self.folder = self.plan.parent
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--fase", "antes", "--corridas", "3", "--calentamiento", "0",
                "--sin-compilar")
        self.assertTrue(list((self.folder / "antes").glob("*.resumen.json")))

    def calls(self):
        counter = self.dir / "tp.count"
        return int(counter.read_text()) if counter.is_file() else 0

    def test_no_abre_trazas_y_cachea_las_viejas(self):
        before = self.calls()
        started = time.time()
        out = self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertLess(time.time() - started, 60)
        self.assertEqual(self.calls(), before)  # ninguna traza abierta
        self.assertIn("no vuelve a abrir las trazas", out)
        for path in (self.folder / "antes").glob("*%s" % perf.TIMELINE_SUFFIX):  # una corrida de una versión anterior
            path.unlink()
        out = self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertIn("procesando la traza 1 de 1", out)
        self.assertEqual(self.calls(), before + 1)
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertEqual(self.calls(), before + 1)  # quedó en caché


class ImprovementTextsTest(PerfBase):
    """E5, H2 y H6: una mejora sale de un hallazgo confirmado, su panel trae el diff completo y la explicación por
    archivo, y los textos de la IA tienen tope."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        state = (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8").replace(
            "| --- | --- | --- | --- | --- | --- |\n",
            "| --- | --- | --- | --- | --- | --- |\n| H1 | La lista tarda | 1 s · `app/Lista.kt:7` | dos llamadas | bug | — |\n"
            "| H2 | Un tirón | 1 | — | sin confirmar | una captura |\n", 1)
        state = state.replace("<3 a 5 líneas. Para el reporte inicial", "uno\ndos\ntres\ncuatro\ncinco\nseis\n<x", 1)
        write(self.folder / "estado.md", state)
        self.plan = {"paquete": PKG, "principales": ["abrir_ms"], "flujos": {"f": {}}, "etiquetas": {"abrir_ms": "Abrir"},
                     "mejoras": [{"id": "M1", "hallazgo": "H1", "titulo": "Una sola llamada", "metrica": "abrir_ms",
                                  "estado": "aplicada", "riesgo": "medio: toca la carga de la lista",
                                  "cambios": [{"diff": "cambios/M1.diff", "repo": ".", "archivos": ["app/Lista.kt"]}],
                                  "archivos": [{"ruta": "app/Lista.kt", "riesgo": "medio", "antes": "pedía dos veces",
                                                "despues": "pide una vez", "pros": "más rápido",
                                                "contras": " ".join(["palabra"] * 50)}]},
                                 {"id": "M2", "hallazgo": "H2", "titulo": "Otra cosa", "estado": "propuesta"}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        diff = "".join("+    fun f%d() = %d\n" % (i, i) for i in range(150))
        write(self.folder / "cambios" / "M1.diff", "diff --git a/app/Lista.kt b/app/Lista.kt\n--- a/app/Lista.kt\n"
                                                  "+++ b/app/Lista.kt\n@@ -1,0 +1,150 @@\n" + diff)
        write(self.folder / "metricas.csv", HEADER + rows("antes", "f", "abrir_ms", [1000, 1010, 990, 1005, 995])
              + rows("despues", "f", "abrir_ms", [500, 505, 495, 502, 498]))

    def test_paneles_topes_y_hallazgos(self):
        out = self.ok("reporte", "--carpeta", self.folder, "--html")
        dev = (self.folder / "reporte-final-dev.md").read_text(encoding="utf-8")
        self.assertIn("M1 Una sola llamada [Mejora] [aplicada] [riesgo medio]", dev)  # 0.16.0 · R3: la card
        self.assertIn("app/Lista.kt · riesgo medio", dev)
        self.assertIn("Antes: pedía dos veces", dev)
        self.assertIn("+    fun f149() = 149", dev)  # el diff completo
        self.assertIn("| H1 · La lista tarda |", dev)
        self.assertIn("La mejora M2: su hallazgo H2 está sin confirmar. Solo los hallazgos confirmados", out)  # E5
        self.assertIn("Resumen ejecutivo pasa su tope: 2 líneas de más (tiene 7; el tope es 5)", out)  # H6
        self.assertIn("M1 · app/Lista.kt · contras pasa su tope: 10 palabras de más", out)
        business = (self.folder / "reporte-final-gerencia.md").read_text(encoding="utf-8")
        self.assertIn("| M1 · Una sola llamada | [medio] | toca la carga de la lista |", business)  # 0.16.0 · R5
        self.assertNotIn("Un tirón", business)

    def test_decidir_aplicada_pide_la_explicacion_de_cada_archivo(self):
        root = init_repo(self.dir)
        write(self.dir / "app" / "Lista.kt", "a\n")
        write(self.dir / "app" / "Otro.kt", "b\n")
        commit_all(root, "base")
        write(self.dir / "app" / "Lista.kt", "a\nc\n")
        write(self.dir / "app" / "Otro.kt", "b\nd\n")
        self.plan["mejoras"][0]["estado"] = "aprobada"
        self.plan["mejoras"][0].pop("cambios")
        write(self.folder / "plan.json", json.dumps(self.plan))
        out = self.ok("decidir", "--carpeta", self.folder, "--aplicada", "M1", "--archivos", "app/Lista.kt,app/Otro.kt")
        self.assertIn("⚠ Falta la explicación por archivo de M1 para app/Otro.kt", out)
        self.assertIn("decidir --carpeta", out.split("Falta la explicación")[1])


# ── Lo que encontró el doble chequeo: cada arreglo con su test ───────────────
class DodSafetyTest(PerfBase):
    """P1: del DoD solo se corre el código con que empieza una viñeta o el de "Etiqueta: `comando`"; lo que se prohíbe,
    se condiciona, integra o publica no se corre y se cita con su motivo."""

    def test_no_corre_lo_prohibido_ni_lo_condicional(self):
        write(self.dir / "AGENTS.md", "# P\n\n## DoD\n\n- No publiques: `./gradlew publish` solo lo hace el CI\n"
                                      "- Nunca `gh pr merge --squash` sin aprobación\n"
                                      "- Si cambia la API, `./gradlew apiDump`\n"
                                      "- Solo lo corre el CI: `./gradlew connectedCheck`\n"
                                      "- Mensajes en `Conventional Commits`\n"
                                      "- `git merge main`\n- `adb uninstall com.example.app`\n"
                                      "- Lint y tests: `./gradlew lint` y `./gradlew test`\n"
                                      "1. Tests:\n\n    ```bash\n    $ ./gradlew check\n    $ANDROID_HOME/platform-tools/adb devices\n"
                                      "    ```\n")
        commands, skipped = perf.dod_entries(self.dir)
        root = perf.q(self.dir)
        self.assertEqual(commands, ["cd %s && ./gradlew lint" % root, "cd %s && ./gradlew test" % root,  # 0.16.0 · Q
                                    "cd %s && ./gradlew check" % root,
                                    "cd %s && $ANDROID_HOME/platform-tools/adb devices" % root])
        reasons = dict(skipped)
        self.assertIn("lo prohíbe o lo pone como condición",
                      reasons["- No publiques: `./gradlew publish` solo lo hace el CI"])
        self.assertIn("no tiene un comando", reasons["- Si cambia la API, `./gradlew apiDump`"])  # no se corre
        self.assertIn("lo prohíbe o lo pone como condición", reasons["- Solo lo corre el CI: `./gradlew connectedCheck`"])
        self.assertIn("no tiene un comando", reasons["- Nunca `gh pr merge --squash` sin aprobación"])
        self.assertIn("no tiene un comando", reasons["- Mensajes en `Conventional Commits`"])
        self.assertIn("integra o publica", reasons["- `git merge main`"])
        self.assertIn("integra o publica", reasons["- `adb uninstall com.example.app`"])
        self.assertNotIn("1. Tests:", reasons)  # presenta el bloque que sigue

    def test_no_pierde_comandos_validos_ni_corre_lo_condicional_en_ingles(self):
        write(self.dir / "AGENTS.md", "# P\n\n## Definition of Done\n\n"
                                      "- Tests unitarios (sin emulador): `./gradlew testDebugUnitTest`\n"
                                      "- Lint (no bloquea): `./gradlew lint`\n"
                                      "- Unit tests (no device needed): `./gradlew test`\n"
                                      "- Only on CI: `./gradlew connectedAndroidTest`\n"
                                      "- If the public API changed: `./gradlew apiDump`\n"
                                      "- Nunca en local:\n\n  ```bash\n  ./gradlew connectedCheck\n  ```\n"
                                      "- Después de `./gradlew test`, `git fetch`: `./gradlew check`\n")
        commands, skipped = perf.dod_entries(self.dir)
        root = perf.q(self.dir)
        self.assertEqual(commands, ["cd %s && ./gradlew testDebugUnitTest" % root, "cd %s && ./gradlew lint" % root,
                                    "cd %s && ./gradlew test" % root])
        reasons = dict(skipped)
        self.assertIn("lo prohíbe o lo pone como condición", reasons["- Only on CI: `./gradlew connectedAndroidTest`"])
        self.assertIn("lo prohíbe o lo pone como condición", reasons["- If the public API changed: `./gradlew apiDump`"])
        self.assertIn("que lo prohíbe o lo pone como condición", reasons["./gradlew connectedCheck"])
        self.assertFalse(any("más de un comando" in why for why in reasons.values()))


class ReviewFixesTest(PerfBase):
    """Arreglos de la revisión que se prueban sin dispositivo."""

    def test_versiones_que_miden_igual(self):
        self.assertTrue(perf.same_capture("0.14.0"))
        self.assertTrue(perf.same_capture(perf.VERSION))

    def test_sesion_0_pedido_no_es_la_del_setup(self):
        self.assertEqual(perf.session_key("0 · pedido"), ("0p", ""))
        self.assertEqual(perf.session_key("0 · setup"), ("0", ""))

    def test_tamano_con_include_de_varias_lineas(self):
        write(self.dir / "settings.gradle.kts", "include(\n" + "".join('    ":m%d",\n' % i for i in range(30)) + ")\n"
                                                "include(\"app\")\n// include(\":comentado\")\n")
        self.assertEqual(perf.project_size(self.dir), ("grande", "31 módulos en settings.gradle"))
        write(self.dir / "settings.gradle.kts", "include ':app', ':lib'\n")
        self.assertEqual(perf.project_size(self.dir)[0], "pequeño")
        write(self.dir / "settings.gradle.kts", "include ':m0',\n" + ",\n".join("    ':m%d'" % i for i in range(1, 8))
                                                + "\n/* include(':comentado') */\n")
        self.assertEqual(perf.project_size(self.dir), ("mediano", "8 módulos en settings.gradle"))

    def test_marca_de_borde_con_duracion(self):
        # beginSection + endSection: la marca de corte dura 20 µs; los tramos contiguos no se solapan
        specs = [{"nombre": "abrir", "desde": {"marca": "NAV a"}, "hasta": {"marca": "MARK corte"}},
                 {"nombre": "lista", "desde": {"marca": "MARK corte"}, "hasta": {"marca": "MARK fin"}}]
        markers = [(1, 0, 0, 0, "NAV a"), (2, 100 * MS, 20_000, 0, "MARK corte"), (3, 300 * MS, 0, 0, "MARK fin")]
        windows = dict((spec["nombre"], bounds) for spec, bounds in perf.segment_windows(markers, specs))
        self.assertEqual(windows["abrir"][1], windows["lista"][0])
        main = [(9, 90 * MS, 30 * MS, 0, "doFrame")]
        lines = perf.segment_overlap_warnings(markers, specs, main)
        self.assertFalse(any("se solapan de verdad" in line for line in lines), lines)
        self.assertTrue(any("cruza el borde" in line for line in lines), lines)

    def test_tramos_identicos_en_el_orden_del_plan(self):
        specs = [{"nombre": "lista", "desde": {"marca": "NAV a"}, "hasta": {"marca": "MARK c"}},
                 {"nombre": "detalle", "desde": {"marca": "MARK b"}, "hasta": {"marca": "MARK d"}}]
        rows = [{"fase": "antes", "flujo": "f", "metrica": "%s hilo_max_ms" % name, "corrida": str(run), "valor": value}
                for run, value in ((1, 41), (2, 47)) for name in ("lista", "detalle")]
        notes = perf.identical_segment_notes(rows, {"antes": {"corridas": 2, "reglas": perf.CALC_RULES}},
                                             {"flujos": {"f": {"segmentos": specs}}})
        self.assertIn("segmentos[0].hasta", notes[0])  # 'lista' va primero en el plan: es la que cubre
        self.assertIn("si la marca 'MARK c' sale más de una vez", notes[0])  # sin traza, como hipótesis

    def test_la_regla_es_de_cada_flujo(self):
        folder = self.dir / "inv"
        old = {"corridas": 3, "flujos": {"a": {"corridas": 3}}}
        write(folder / "fases.json", json.dumps({"antes": old}))
        perf.write_phase(folder, "antes", {"fecha": "2026-03-02T10:00:00", "corridas": 3, "reglas": perf.CALC_RULES},
                         flow="b")
        phase = perf.read_phases(folder)["antes"]
        self.assertNotIn("reglas", phase)  # 'a' sigue con la regla anterior: la fase no dice la de ahora
        self.assertEqual(phase["flujos"]["b"]["reglas"], perf.CALC_RULES)
        self.assertFalse(perf.rules_complete(phase))
        phase["flujos"]["a"]["reglas"] = perf.CALC_RULES
        self.assertTrue(perf.rules_complete(phase))

    def test_veredicto_de_memoria_en_estado(self):
        folder = self.dir / "inv"
        folder.mkdir()
        for run in (1, 2, 3):
            perf.note_leak(folder, "catalogo-repeticion", "antes", run, "sospecha de fuga", "las actividades suben")
        lines = perf.memory_verdict_lines(folder, {"flujos": {}})
        self.assertEqual(lines, ["Memoria entre ciclos (catalogo repeticion, antes): sospecha de fuga en las 3 corridas: "
                                 "las actividades suben."])
        perf.note_leak(folder, "catalogo-repeticion", "despues", 1, "sin evidencia de fuga", "estable")
        self.assertIn("hacen falta 3 o más con el mismo resultado", perf.memory_verdict_lines(folder, {})[1])
        self.assertEqual(perf.leak_verdict([{"etiqueta": "ciclo %d" % i, "memoria": {}} for i in range(6)])[0],
                         "sin datos para decirlo")

    def test_ciclos_del_plan_llegan_al_recorrido(self):
        plan = {"flujos": {"r": {"tipo": "repeticion", "ciclos": 7}}}
        self.assertEqual(perf.scenario_env(plan, "r", self.dir / "plan.json")["PERF_CICLOS"], "7")
        self.assertIn('$(seq "${PERF_CICLOS:-5}")', perf.ROUTE_TEMPLATE)

    def test_sin_traza_con_pantallas_protegidas_usa_la_liviana(self):
        spec = {"tipo": "repeticion", "traza": "sin", "invalidar_si": ["SCREEN *Pago*"]}
        self.assertEqual(perf.flow_config_name({}, spec, None), "liviana")
        self.assertEqual(perf.flow_config_name({}, dict(spec, invalidar_si=[]), None), "base")

    def test_umbral_de_orientativo(self):
        def result(before, after, noise, warnings):
            return {"metrica": "abrir_ms", "flujo": "f", "unidad": "ms", "familia": "app", "veredicto": "mejora",
                    "delta": after[1] - before[1], "ruido": noise, "avisos": warnings,
                    "antes": {"mediana": before[1], "min": before[0], "max": before[2]},
                    "despues": {"mediana": after[1], "min": after[0], "max": after[2]}}

        clear = result((2700, 2800, 2900), (20, 30, 60), 50, ["inestable"])
        self.assertTrue(perf.clear_change(clear))
        self.assertEqual(perf.verdict_label(clear), "Mejora")
        self.assertNotIn("orientativo", perf.plain_verdict(clear))
        touching = result((900, 1000, 1100), (700, 800, 950), 50, ["inestable"])  # los rangos se tocan
        self.assertFalse(perf.clear_change(touching))
        self.assertEqual(perf.verdict_label(touching), "Orientativo")
        small = result((990, 1000, 1050), (900, 950, 960), 10, ["inestable"])  # separados, pero 50 < 2 × 60
        self.assertFalse(perf.clear_change(small))
        self.assertEqual(perf.verdict_label(small), "Orientativo")
        noisy = result((1000, 1010, 1020), (900, 910, 920), 50, ["inestable"])  # separados, pero 100 < 3 × 50
        self.assertFalse(perf.clear_change(noisy))

    def test_pie_del_grafico_coherente_con_el_chip(self):
        same = {"metrica": "abrir_ms", "flujo": "f", "unidad": "ms", "familia": "app", "veredicto": "sin cambio",
                "delta": 0, "ruido": 0.4, "avisos": [], "antes": {"mediana": 48, "min": 47, "max": 49},
                "despues": {"mediana": 48, "min": 47, "max": 49}}
        text = perf.chart_caption(same, {})
        self.assertIn("ahora 48 milisegundos. El valor de después queda dentro del rango de antes: no cambió", text)
        close = dict(same, antes={"mediana": 1000, "min": 900, "max": 1100}, despues={"mediana": 950, "min": 920, "max": 990})
        self.assertNotIn("% más rápido", perf.chart_caption(close, {}))
        self.assertNotIn("tómalo como una señal", text)
        self.assertNotIn("unos 0 milisegundos", text)

    def test_equal_line_con_reglas_distintas(self):
        folder = self.dir / "inv"
        write(folder / "fases.json", json.dumps({"antes": {"corridas": 3}, "despues": {"corridas": 3,
                                                                                         "reglas": perf.CALC_RULES}}))
        plan = {"flujos": {"f": {"segmentos": [{"nombre": "a"}]}}}
        self.assertIn("**no** del todo", perf.equal_line(folder, plan, []))

    def test_lo_descartado_dice_por_que(self):
        findings = perf.findings_rows("| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n"
                                      "| H1 | Jank | 2 % | El camino lento no corrió | descartado |\n"
                                      "| H2 | Doble carga | 2 llamadas | se pide dos veces | bug |\n")
        self.assertEqual(perf.reviewed_md(findings), "- H1 · descartado · Jank: El camino lento no corrió. 2 %.")
        self.assertEqual(perf.unimproved_md(findings, {"mejoras": []}), "- H2 · bug · Doble carga: se pide dos veces.")
        self.assertEqual(perf.unimproved_md(findings, {"mejoras": [{"hallazgo": "H2"}]}), "")

    def test_red_por_tramo_en_palabras(self):
        rows = [{"fase": fase, "flujo": "catalogo-lista", "metrica": "detalle red_llamadas", "corrida": "1", "valor": 2,
                 "unidad": "llamadas", "sentido": "menor", "familia": "app"} for fase in ("antes", "despues")]
        md = perf.segment_network_md(rows, {"flujos": {"catalogo-lista": {"segmentos": [{"nombre": "detalle"}]}}},
                                     ("antes", "despues"))
        self.assertIn("| catalogo lista | detalle | después |", md)
        self.assertNotIn("despues |", md)

    def test_gerencia_no_niega_lo_que_omite(self):
        # 0.19.0 · P1: "hilo principal" tiene traducción; un nombre de código no
        plan = {"mejoras": [{"id": "M2", "titulo": "Sacar `leerDisco()` de la carga", "estado": "pendiente"}]}
        text = perf.pending_improvements(plan, True, plain=True, problems=[])
        self.assertNotIn("No queda nada pendiente", text)
        self.assertIn("un cambio propuesto (M2), sin descripción en palabras todavía", text)


class ReviewDeviceTest(DeviceBase):
    """Arreglos de la revisión que pasan por `capturar` y `siguiente`."""

    def test_empeoramiento_secundario_en_porcentaje(self):
        results = [{"metrica": "jank_app_pct", "flujo": "f", "veredicto": "regresión", "familia": "app", "unidad": "%",
                    "delta": 6, "antes": {"mediana": 2}, "despues": {"mediana": 8}}]
        text = perf.secondary_changes({"principales": ["abrir_ms"], "etiquetas": {"jank_app_pct": "Cuadros trabados"}},
                                      results, [])
        self.assertIn("empeoró: 2 % → 8 %", text)


class ReviewTriageTest(TriageBase):
    """B7 y B4 con el proyecto de ejemplo."""

    def test_pausar_simular_no_escribe_nada(self):
        before = (self.root / "app" / "Lista.kt").read_text(encoding="utf-8")
        write(self.root / "app" / "Lista.kt", LISTA)  # sin marcas que quitar
        out = self.ok_in("pausar", "--carpeta", self.rel, "--simular", "--quitar-setup")
        self.assertIn("--quitar-setup: no quitaría nada: el setup no está en un parche", out)
        self.assertIn("pausar --carpeta %s --quitar-setup" % self.rel, out)
        self.assertFalse((self.folder / "pausa.json").exists())
        self.assertNotIn("En pausa", (self.folder / "estado.md").read_text(encoding="utf-8").split("## Ficha")[0])
        write(self.root / "app" / "Lista.kt", before)

    def test_parche_de_otra_investigacion_del_mismo_dia(self):
        parches = self.root / "reports" / "perf" / "parches"
        write(self.root / "AGENTS.md", self.root.joinpath("AGENTS.md").read_text(encoding="utf-8").replace(
            "## DoD", "- Carpeta de parches: `reports/perf/parches`\n\n## DoD"))
        write(parches / "catalogo-lista-2026-03-02-2-marcas-proyecto-20261101-1000.patch", git(self.root, "diff"))
        found = perf.marks_patches(self.folder, self.root.resolve(), self.plan())
        self.assertEqual(found["vigente"], {})


class ReviewRound2Test(PerfBase):
    """Arreglos de la segunda ronda del doble chequeo."""

    def test_memoria_registrada_sin_memoria_en_el_plan(self):
        folder = self.dir / "inv"
        write(folder / "fases.json", json.dumps({"antes": {"corridas": 3, "flujos": {"f": {"corridas": 3,
                                                                                            "memoria": True}}}}))
        self.assertTrue(perf.plan_memory({"flujos": {"f": {}}}, "f", folder))
        self.assertFalse(perf.plan_memory({"flujos": {"f": {}}}, "f"))
        self.assertFalse(perf.plan_memory({"memoria": False, "flujos": {"f": {}}}, "f", folder))

    def test_servicios_ausentes_solo_con_red_por_servicio(self):
        plan = {"flujos": {"f": {"servicios": ["GET pedidos"]}, "f-espera": {"servicios": ["GET pedidos"]}}}
        rows = [{"fase": "antes", "flujo": "f", "metrica": "red GET items llamadas", "corrida": "1", "valor": 1}]
        self.assertEqual(perf.absent_from_rows(plan, rows, "f"), ["GET pedidos"])
        self.assertEqual(perf.absent_from_rows(plan, rows, "f-espera"), [])  # sin corridas: no se dice nada

    def test_sin_datos_por_servicio_no_afirma_nada(self):
        rows = [{"fase": "antes", "flujo": "f", "metrica": "red_llamadas", "corrida": "1", "valor": 2, "unidad": "llamadas",
                 "sentido": "menor", "familia": "app"}]
        text = perf.changed_services_md(rows, {"flujos": {"f": {}}}, ("antes",), {})
        self.assertIn("no traen datos por servicio", text)
        self.assertNotIn("Ningún servicio cambió", text)

    def test_riesgo_con_titulo_tecnico(self):
        text = perf.risk_md({}, [{"id": "M1", "titulo": "Usar LazyColumn con key", "riesgo": "bajo"}], [])
        self.assertEqual(text, "- Un cambio (M1), todavía sin descripción en palabras: riesgo bajo.")

    def test_accion_sin_tramos_va_de_la_marca_de_inicio_a_la_de_fin(self):
        plan = {"flujos": {"f": {"titulo": "abrir los pedidos", "ventana": {"desde": {"marca": "NAV pedidos"},
                                                                             "hasta": {"marca": "MARK pedidos"}}}}}
        timeline = {"marcas": [["NAV pedidos", 100.0], ["MARK pedidos", 1000.0], ["MARK otra", 7000.0]],
                    "llamadas": [["GET pedidos", 200.0, 600.0], ["GET analitica", 6900.0, 7300.0]]}
        self.assertEqual(perf.action_spans(plan, "f", timeline), [("abrir los pedidos", 100.0, 1000.0)])

    def test_cerrada_no_pide_medir_otro_flujo(self):
        folder = self.dir / "inv"
        plan = json.loads(json.dumps(TWO_FLOWS))
        write(folder / "plan.json", json.dumps(plan))
        write(folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 3,
                                                            "flujos": flows_record(**{"catalogo-lista": 3})}}))
        write(folder / "reporte-inicial-dev.md", "x")
        title, steps = perf.next_steps(folder, perf.load_plan(folder / "plan.json"))
        self.assertTrue(title.startswith("triage cerrado"), title)
        self.assertFalse(any(" capturar " in step.get("texto", "") for step in steps))


class ReviewRound2TriageTest(TriageBase):
    """`reanudar` con trabajo del usuario sin commitear y con un parche que ya no aplica."""

    def pause(self):
        self.ok_in("pausar", "--carpeta", self.rel)
        self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), LISTA)

    def test_se_detiene_con_cambios_sin_commitear(self):
        self.pause()
        write(self.root / "app" / "Lista.kt", LISTA + "// trabajo sin commitear\n")
        result = self.run_in("reanudar", "--carpeta", self.rel)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hay cambios sin commitear en los archivos donde van", result.stdout + result.stderr)
        self.assertIn("reanudar --carpeta", result.stdout + result.stderr)
        self.assertEqual((self.root / "app" / "Lista.kt").read_text(encoding="utf-8"), LISTA + "// trabajo sin commitear\n")

    def test_marcas_a_mano_cuando_el_parche_no_aplica(self):
        self.pause()
        write(self.root / "app" / "Lista.kt", LISTA.replace("    fun e() = 5\n", "    fun e() = 50\n"))
        commit_all(self.root, "el equipo cambió el contexto de la marca")
        result = self.run_in("reanudar", "--carpeta", self.rel)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reanudar --carpeta %s --marcas-a-mano" % self.rel, result.stdout + result.stderr)
        out = self.ok_in("reanudar", "--carpeta", self.rel, "--marcas-a-mano")
        self.assertIn("2. Marcas: las repuso la sesión a mano", out)
        self.assertNotIn("en pausa", self.ok_in("siguiente", "--carpeta", self.rel).split("\n")[0])


# ── 0.15.1 · B2 y B8 ─────────────────────────────────────────────────────────
def flows_at(when, skill=perf.VERSION, **flows):
    return {name: {"corridas": runs, "fecha": when, "skill": skill} for name, runs in flows.items()}


class SecondFlowTest(PerfBase):
    """B2: el segundo flujo del plan recibe el mismo trato que el primero (completar, rehacer)."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = json.loads(json.dumps(TWO_FLOWS))
        self.plan["profundidad"] = "riguroso"
        write(self.folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        self.tests = {"prueba": {"flujos": {"catalogo-lista": {"fecha": "2026-11-05T09:00:00", "marcas_ok": True},
                                            "catalogo-repeticion": {"fecha": "2026-11-05T09:01:00", "marcas_ok": True}}}}

    def texts(self, phases, flow=None):
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "fases.json", json.dumps(dict(self.tests, **phases)))
        _, steps = perf.next_steps(self.folder, perf.load_plan(self.folder / "plan.json"), flow)
        return [step.get("texto", "") for step in steps if step["tipo"] == "terminal"]

    def test_riguroso_desde_un_triage_completa_los_dos_flujos(self):
        self.plan.update(desde_triage=True, mejoras=[{"id": "M1", "titulo": "x", "estado": "propuesta"}])
        both = {"catalogo-lista": 3, "catalogo-repeticion": 3}
        texts = self.texts({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 6, "skill": perf.VERSION,
                                      "flujos": flows_at("2026-11-05T10:00:00", **both)}})
        joined = "\n".join(texts)
        self.assertIn("--flujo catalogo-lista --fase antes --corridas 7", joined)
        self.assertIn("--flujo catalogo-repeticion --fase antes --corridas 7", joined)
        self.assertNotIn("--rehacer", joined)
        self.assertIn("--flujo catalogo-repeticion --fase control --corridas 10", joined)

    def test_un_despues_viejo_se_mide_de_nuevo_en_los_dos(self):
        self.plan["mejoras"] = [{"id": "M1", "titulo": "x", "estado": "aplicada", "aplicada_en": "2026-11-05T09:30:00"},
                                {"id": "M2", "titulo": "y", "estado": "aplicada", "aplicada_en": "2026-11-05T14:00:00"}]
        both = {"catalogo-lista": 10, "catalogo-repeticion": 10}
        self.tests["prueba"]["flujos"] = {name: {"fecha": "2026-11-05T14:30:00", "marcas_ok": True} for name in both}
        texts = self.texts({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 20, "skill": perf.VERSION,
                                      "flujos": flows_at("2026-11-05T10:00:00", **both)},
                            "control": {"fecha": "2026-11-05T11:00:00", "corridas": 20,
                                        "flujos": flows_at("2026-11-05T11:00:00", **both)},
                            "despues": {"fecha": "2026-11-05T12:00:00", "corridas": 20,
                                        "flujos": flows_at("2026-11-05T12:00:00", **both)}})
        joined = "\n".join(texts)
        self.assertIn("--flujo catalogo-repeticion --fase despues --corridas 10 --rehacer", joined)

    def test_con_las_mejoras_quitadas_el_segundo_flujo_se_rehace(self):
        self.plan["mejoras"] = [{"id": "M1", "titulo": "x", "estado": "aplicada", "aplicada_en": "2026-11-05T09:30:00"}]
        write(self.folder / "lineabase.json", json.dumps({"estado": "quitadas", "fecha": "2026-11-05T13:00:00",
                                                          "mejoras": ["M1"], "parches": []}))
        both = {"catalogo-lista": 10, "catalogo-repeticion": 10}
        texts = self.texts({"antes": {"fecha": "2026-11-05T10:00:00", "corridas": 20, "skill": perf.VERSION,
                                      "flujos": flows_at("2026-11-05T10:00:00", **both)},
                            "control": {"fecha": "2026-11-05T11:00:00", "corridas": 20,
                                        "flujos": flows_at("2026-11-05T11:00:00", **both)}})
        joined = "\n".join(texts)
        self.assertIn("--flujo catalogo-repeticion --fase antes --corridas 10 --rehacer", joined)
        self.assertIn("--flujo catalogo-repeticion --fase control --corridas 10 --rehacer", joined)


class StaleBaselineWithImprovementTest(PerfBase):
    """B8: con una mejora aplicada, si `reanudar` dijo que la línea base no sirve, `siguiente` la rehace quitando la
    mejora con su parche (y la vuelve a poner al final)."""

    def test_rehace_la_linea_base_quitando_la_mejora(self):
        folder = self.dir / "inv"
        plan = {"paquete": PKG, "principales": ["abrir_ms"], "flujos": {"f": {"recorrido": "true"}},
                "mejoras": [{"id": "M1", "titulo": "x", "estado": "aplicada", "aplicada_en": "2026-11-05T12:00:00"}]}
        write(folder / "plan.json", json.dumps(plan))
        write(folder / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        write(folder / "fases.json", json.dumps({
            "antes": {"fecha": "2026-11-05T10:00:00", "corridas": 10, "skill": perf.VERSION,
                      "rehacer": "el código que citan los hallazgos cambió desde la pausa",
                      "rehacer_desde": "2026-11-06T09:00:00", "flujos": flows_at("2026-11-05T10:00:00", f=10)},
            "control": {"fecha": "2026-11-05T11:00:00", "corridas": 10, "flujos": flows_at("2026-11-05T11:00:00", f=10)}}))
        title, steps = perf.next_steps(folder, perf.load_plan(folder / "plan.json"))
        self.assertEqual(title, "rehacer la línea base: el código cambió desde la pausa (sin chat)")
        texts = [step.get("texto", "") for step in steps if step["tipo"] == "terminal"]
        self.assertIn("lineabase --carpeta", texts[0])
        self.assertTrue(texts[0].endswith("--quitar-mejoras"))
        self.assertTrue(any("--reaplicar-mejoras" in text for text in texts))



class Fixes0151Test(PerfBase):
    """0.15.1: los arreglos chicos que encontró la revisión de 0.15.0."""

    def test_un_proceso_que_no_es_perf_no_cuenta_como_corriendo(self):
        folder = self.dir / "inv"
        sleeper = subprocess.Popen(["sleep", "30"])  # vivo, pero no es perf.py (un número reutilizado)
        try:
            write(folder / ".en-curso.json", json.dumps({"comando": "capturar", "pid": sleeper.pid}))
            self.assertFalse(perf.interrupted(folder)["viva"])
        finally:
            sleeper.kill()
            sleeper.wait()

    def test_el_dod_no_corre_lo_que_borra_datos_o_desinstala(self):
        for command in ("fastlane beta", "./gradlew uninstallAll", "./gradlew :app:uninstallDebug",
                        "adb shell pm clear com.example.app", "git switch --discard-changes main", "rm --recursive x"):
            self.assertTrue(perf.DISCARDING.search(command), command)
        for command in ("./gradlew test", "adb devices", "./gradlew :app:installProfiling"):
            self.assertFalse(perf.DISCARDING.search(command), command)

    def test_memoria_en_palabras(self):
        for metric in ("pss_crecimiento_mb", "activities_crecimiento", "views_crecimiento", "ciclos", "activities", "views"):
            self.assertNotIn("_", perf.plain_metric(metric, {}))
            self.assertNotIn('"', perf.plain_metric(metric, {}))

    def test_variacion_normal_sin_unos_0(self):
        self.assertEqual(perf.noise_sentence(0, "llamadas"), "Medir dos veces sin cambiar nada da el mismo valor")
        self.assertIn("menos de 1 milisegundo", perf.noise_sentence(0.4, "ms"))
        self.assertIn("unos 12 milisegundos", perf.noise_sentence(12, "ms"))

    def test_titulo_del_grafico_escapado(self):
        r = {"metrica": "abrir_ms", "flujo": "f", "veredicto": "mejora", "avisos": [], "delta": -10, "ruido": 1,
             "antes": {"mediana": 100, "min": 90, "max": 110}, "despues": {"mediana": 50, "min": 45, "max": 55}}
        title = perf.chart_title(r, {"etiquetas": {"abrir_ms": "Lista < 2 s & <i>rápida</i>"}})
        self.assertNotIn("<i>", title)
        self.assertIn("&lt;i&gt;", title)

    def test_pasos_de_la_plantilla_de_0140(self):
        self.assertEqual(perf.STEP_COMMENT.match("# Paso 1: toca Pedidos").group(1), "toca Pedidos")
        self.assertEqual(perf.STEP_COMMENT.match("# paso: toca Pedidos").group(1), "toca Pedidos")

    def test_tramos_identicos_con_la_regla_del_flujo(self):
        specs = [{"nombre": "lista", "desde": {"marca": "NAV a"}, "hasta": {"marca": "MARK c"}},
                 {"nombre": "detalle", "desde": {"marca": "MARK b"}, "hasta": {"marca": "MARK d"}}]
        rows = [{"fase": "antes", "flujo": "f", "metrica": "%s hilo_max_ms" % name, "corrida": str(run), "valor": value}
                for run, value in ((1, 41), (2, 47)) for name in ("lista", "detalle")]
        notes = perf.identical_segment_notes(rows, {"antes": {"corridas": 4, "flujos": {
            "f": {"corridas": 2, "reglas": perf.CALC_RULES}, "g": {"corridas": 2}}}}, {"flujos": {"f": {"segmentos": specs}}})
        self.assertNotIn("medidas con la regla anterior", notes[0])  # la regla de este flujo es la de ahora
        self.assertIn("con la regla del borde (cada slice y cada frame cuentan solo donde empiezan)", notes[0])

    def test_panel_sin_diff_y_riesgo_con_tilde(self):
        item = {"id": "M1", "titulo": "x", "estado": "aplicada", "metrica": "abrir_ms",
                "archivos": [{"ruta": "app/Lista.kt", "riesgo": "Crítico", "antes": "a"}]}
        card = perf.improvement_card(self.dir, {"mejoras": [item]}, item, [], [], "")
        self.assertIn("- **Código:** sin diff guardado", card)
        self.assertIn("<summary>app/Lista.kt · riesgo critico</summary>", card)

    def test_la_misma_ruta_en_dos_repos_tiene_su_propia_explicacion(self):
        diff = "diff --git a/app/X.kt b/app/X.kt\nindex 1..2 100644\n--- a/app/X.kt\n+++ b/app/X.kt\n@@ -1 +1 @@\n-%s\n+%s\n"
        write(self.dir / "cambios" / "M1.diff", diff % ("uno", "dos"))
        write(self.dir / "cambios" / "M1-1.diff", diff % ("tres", "cuatro"))
        item = {"id": "M1", "titulo": "x", "estado": "aplicada", "metrica": "abrir_ms",
                "cambios": [{"diff": "cambios/M1.diff", "repo": "."}, {"diff": "cambios/M1-1.diff", "repo": "../otro"}],
                "archivos": [{"ruta": "app/X.kt", "riesgo": "bajo", "antes": "en este repo"}]}
        self.assertEqual(perf.missing_file_notes(self.dir, item), ["app/X.kt (../otro)"])
        card = perf.improvement_card(self.dir, {"mejoras": [item]}, item, [], [], "")
        self.assertIn("<summary>app/X.kt · riesgo bajo</summary>", card)
        self.assertIn("<summary>app/X.kt (../otro) · riesgo sin evaluar</summary>", card)
        self.assertIn("necesita \"repo\" (el mismo de `decidir --repo`)", card)
        item["archivos"].append({"ruta": "app/X.kt", "repo": "../otro/", "riesgo": "alto", "antes": "en el otro repo"})
        self.assertEqual(perf.missing_file_notes(self.dir, item), [])
        card = perf.improvement_card(self.dir, {"mejoras": [item]}, item, [], [], "")
        self.assertIn("<summary>app/X.kt (../otro) · riesgo alto</summary>", card)
        self.assertLess(card.index("en este repo"), card.index("+dos"))
        self.assertLess(card.index("+dos"), card.index("en el otro repo"))
        self.assertLess(card.index("en el otro repo"), card.index("+cuatro"))
        self.assertEqual(card.count('<details class="file">'), 2)  # ninguna explicación repetida aparte

    def test_el_tope_por_archivo_nombra_el_repo(self):
        long_text = " ".join(["palabra"] * (perf.FILE_FIELD_WORDS + 2))
        plan = {"mejoras": [{"id": "M1", "archivos": [{"ruta": "app/X.kt", "antes": long_text},
                                                      {"ruta": "app/X.kt", "repo": "../otro", "antes": long_text}]}]}
        names = [name for name, _ in perf.text_cap_problems({}, plan)]
        self.assertEqual(names, ["M1 · app/X.kt · antes", "M1 · app/X.kt (../otro) · antes"])

    def test_dispositivo_de_cada_flujo_en_reanudar(self):
        one = {"serial": "emulator-5554", "modelo": "Pixel Test"}
        other = {"serial": "emulator-5556", "modelo": "Pixel Test"}
        plan = {"flujos": {"a": {}, "b": {}, "c": {}}}
        phases = {"antes": {"dispositivo": other, "flujos": {"a": {"corridas": 3, "dispositivo": one},
                                                             "b": {"corridas": 3, "dispositivo": one}}}}
        self.assertEqual(perf.baseline_devices(phases, plan), [("Pixel Test (emulator-5554)", [])])
        phases["antes"]["flujos"]["c"] = {"corridas": 3, "dispositivo": other}
        self.assertEqual(perf.baseline_devices(phases, plan), [("Pixel Test (emulator-5554)", ["a", "b"]),
                                                               ("Pixel Test (emulator-5556)", ["c"])])
        old = {"antes": {"dispositivo": one, "flujos": {"a": {"corridas": 3}}}}  # de antes de 0.15.1: el de la fase
        self.assertEqual(perf.baseline_devices(old, plan), [("Pixel Test (emulator-5554)", [])])
        self.assertEqual(perf.baseline_devices({}, plan), [])

    def test_una_mejora_aplicada_no_se_manda_quitar_del_plan(self):
        findings = "| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n| H1 | x | y | z | sin confirmar |\n"
        plan = {"mejoras": [{"id": "M1", "hallazgo": "H1", "estado": "aplicada"},
                            {"id": "M2", "hallazgo": "H1", "estado": "propuesta"}]}
        self.assertEqual([ident for ident, _ in perf.unconfirmed_improvements(plan, findings)], ["M2"])

    def test_la_linea_del_presupuesto_no_va_al_reporte(self):
        folder = self.dir / "inv"
        state = (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8")
        state = state.replace("## Pendientes\n\n", "## Pendientes\n\n- 80 % del presupuesto de pasos: queda el plan.\n"
                                                     "- Falta medir el arranque en frío.\n", 1)
        write(folder / "estado.md", state)
        write(folder / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {}}}))
        write(folder / "metricas.csv", HEADER + rows("antes", "f", "abrir_ms", [100, 110, 105]))
        self.ok("reporte", "--carpeta", folder, "--inicial")
        md = (folder / "reporte-inicial-dev.md").read_text(encoding="utf-8")
        self.assertIn("Falta medir el arranque en frío", md)
        self.assertNotIn("presupuesto de pasos", md)

    def test_ciclo_fuera_de_una_captura_da_el_paso(self):
        result = subprocess.run(perf_argv(SCRIPT) + ["ciclo"], cwd=str(self.dir), capture_output=True,
                                text=True, env=dict(ENV, HOME=str(self.dir)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("perf.py estado", result.stdout)
        self.assertTrue(result.stdout.strip().splitlines()[-1].strip().startswith("cd "))


class Fixes0151TriageTest(TriageBase):
    """0.15.1: `capturar` sobre algo a medias, `estado` con varias investigaciones y fechas de otras investigaciones."""

    def test_capturar_no_pisa_lo_que_quedo_a_medias(self):
        dead = int(subprocess.run(["/bin/sh", "-c", "echo $$"], capture_output=True, text=True).stdout)
        write(self.folder / ".en-curso.json", json.dumps({"comando": "capturar", "pid": dead, "fase": "antes"}))
        result = self.run_in("capturar", "--plan", self.folder / "plan.json", "--fase", "antes", "--corridas", "3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recuperar --carpeta %s" % self.rel, result.stdout + result.stderr)

    def test_estado_con_varias_es_elige_uno(self):
        other = self.root / "reports" / "perf" / "catalogo-lista" / "2026-03-09"
        write(other / "plan.json", json.dumps(TRIAGE_PLAN))
        write(other / "estado.md", (perf.ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8"))
        out = self.ok_in("estado")
        self.assertIn("Elige uno (una investigación por vez", out)

    def test_otra_investigacion_con_solo_la_fecha_del_mismo_dia(self):
        other = self.root / "reports" / "perf" / "otra" / "2026-03-09"
        write(other / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {"recorrido": "true"}}, "mejoras": [
            {"id": "M9", "titulo": "otra", "estado": "aplicada", "aplicada_en": "2026-11-05",
             "cambios": [{"archivos": ["app/Lista.kt"]}]}]}))
        write(other / "estado.md", "# otra\n")
        lines = perf.other_applied(self.folder, self.root.resolve(), self.plan(), "2026-11-05T15:00:00")
        self.assertTrue(any("M9" in line for line in lines), lines)
        self.assertEqual(perf.other_applied(self.folder, self.root.resolve(), self.plan(), "2026-11-07T15:00:00"), [])

    def test_otra_investigacion_sin_fecha_de_aplicada_cuenta(self):
        # sin `aplicada_en` no se sabe si fue antes o después de la pausa: avisa de más, no de menos
        other = self.root / "reports" / "perf" / "otra" / "2026-03-09"
        write(other / "plan.json", json.dumps({"paquete": PKG, "flujos": {"f": {"recorrido": "true"}}, "mejoras": [
            {"id": "M9", "titulo": "otra", "estado": "aplicada", "cambios": [{"archivos": ["app/Lista.kt"]}]}]}))
        write(other / "estado.md", "# otra\n")
        lines = perf.other_applied(self.folder, self.root.resolve(), self.plan(), "2026-11-07T15:00:00")
        self.assertTrue(any("M9" in line for line in lines), lines)

    def test_reanudar_dice_en_que_dispositivo_se_midio(self):
        phases = json.loads((self.folder / "fases.json").read_text(encoding="utf-8"))
        phases["antes"]["dispositivo"] = {"serial": "emulator-5554", "modelo": "Pixel Test"}
        write(self.folder / "fases.json", json.dumps(phases))
        self.ok_in("pausar", "--carpeta", self.rel)
        out = self.ok_in("reanudar", "--carpeta", self.rel)
        self.assertIn("4. La línea base sirve: las mismas reglas de cálculo y el código del flujo sin cambios; se midió "
                      "en Pixel Test (emulator-5554): mide en ese mismo dispositivo (`capturar` lo comprueba).", out)
        self.assertNotIn("mismo dispositivo y tasa de refresco", out)


class Fixes0151DeviceTest(DeviceBase):
    """0.15.1, con el adb y el trace_processor falsos: la red sin instrumentar y las fases de dos dispositivos."""

    def plan_with(self, **flow):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"].update(flow)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def test_sin_ninguna_llamada_http_no_manda_quitar_los_servicios(self):
        self.plan_with(servicios=["GET items/{id}", "GET entregados"])
        self.tp_outputs("\n".join(line for line in GOOD.splitlines() if "HTTP " not in line) + "\n")
        out = self.ok("capturar", "--plan", self.plan, "--prueba", "--sin-video")
        self.assertIn("pero la traza no trae ninguna llamada HTTP: la red no está instrumentada en el build instalado", out)
        self.assertIn("No quites `servicios` del plan", out)
        self.assertNotIn("quítalo de `servicios`", out)
        self.assertNotIn("quítalos de `servicios`", out)

    def test_las_fases_de_dos_dispositivos_no_se_comparan(self):
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["dispositivo"], {"serial": "emulator-5554", "modelo": "Pixel Test"})
        self.assertEqual(phases["antes"]["flujos"]["home"]["dispositivo"]["serial"], "emulator-5554")  # por flujo
        self.env["FAKE_DEVICES"] = "emulator-5556"  # tras una pausa, otro teléfono conectado
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "1")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("la línea base (antes) del flujo home se midió en Pixel Test (emulator-5554) y el dispositivo "
                      "conectado es Pixel Test (emulator-5556)", result.stderr)
        self.assertIn("--serial emulator-5554", result.stderr)
        self.assertIn("--flujo home --fase antes --corridas 10 --rehacer", result.stderr)  # las del plan, no 5
        self.assertNotIn("control", json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8")))
        # rehacer antes en el teléfono nuevo no se detiene, y después el control ya se compara con ese
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1", "--rehacer")
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(phases["antes"]["flujos"]["home"]["dispositivo"]["serial"], "emulator-5556")
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "1")

    def test_el_primer_antes_de_otro_flujo_en_otro_dispositivo_avisa(self):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["lista"] = dict(plan["flujos"]["home"])
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.tp_outputs(GOOD)
        self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "1")
        self.env["FAKE_DEVICES"] = "emulator-5556"
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "lista", "--fase", "antes", "--corridas", "1")
        self.assertIn("la línea base de los otros flujos se midió en Pixel Test (emulator-5554) y este flujo se mide en "
                      "Pixel Test (emulator-5556)", out)
        self.ok("capturar", "--plan", self.plan, "--flujo", "lista", "--fase", "control", "--corridas", "1")  # su línea base
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "control", "--corridas", "1")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)  # la de home sigue en el otro
        self.assertIn("se midió en Pixel Test (emulator-5554)", result.stderr)
        phases = json.loads((self.plan.parent / "fases.json").read_text(encoding="utf-8"))
        self.assertEqual(perf.baseline_devices(phases, plan), [("Pixel Test (emulator-5554)", ["home"]),
                                                               ("Pixel Test (emulator-5556)", ["lista"])])


class Fixes0151HelpersTest(unittest.TestCase):
    """0.15.1 por unidad: el veredicto de memoria, el diff del panel, el video y los presupuestos de pasos."""

    def test_sin_evidencia_de_fuga_nombra_solo_lo_que_se_leyo(self):
        cycles = [{"etiqueta": "inicio", "memoria": {"java_heap_mb": 20}}] + \
            [{"etiqueta": "ciclo %d" % i, "memoria": {"java_heap_mb": 20}} for i in range(1, 6)]
        verdict, why = perf.leak_verdict(cycles)
        self.assertEqual(verdict, "sin evidencia de fuga")
        self.assertNotIn("vuelven a su nivel", why)
        self.assertIn("el heap de Java no crece en cada ciclo", why)
        self.assertIn("sin datos de actividades ni de vistas entre ciclos", why)
        full = [{"etiqueta": "ciclo %d" % i, "memoria": {"activities": 1, "views": 10, "java_heap_mb": 20}}
                for i in range(6)]
        self.assertEqual(perf.leak_verdict(full)[1], "las actividades y las vistas vuelven a su nivel entre ciclos; el "
                                                     "heap de Java no crece en cada ciclo")

    def test_diff_binario_sin_base85(self):
        text = ("diff --git a/app/logo.png b/app/logo.png\nindex 1111111..2222222 100644\nGIT binary patch\nliteral 12\n"
                "zcmV-K0Jfb5i0x\n\nliteral 0\nHcmV?d00001\n")
        shown = perf.readable_diff(text, "cambios/M1.diff")
        self.assertIn("diff --git a/app/logo.png b/app/logo.png", shown)
        self.assertIn("# archivo binario: su contenido no se muestra (el diff completo está en `cambios/M1.diff`)", shown)
        self.assertNotIn("zcmV", shown)
        self.assertEqual(perf.readable_diff("@@ -1 +1 @@\n-a\n+b", "x"), "@@ -1 +1 @@\n-a\n+b")

    def test_diff_con_tres_acentos_graves_no_cierra_el_bloque(self):
        diff = "# README.md\n@@ -1,3 +1,3 @@\n ```kotlin\n-val ttid_ms = 1\n+val ttid_ms = 2\n ```\n después"
        block = perf.fenced(diff, "diff")
        self.assertEqual(block[0], "````diff")
        self.assertEqual(block[-1], "````")
        text = "Antes: ttid_ms.\n\n" + "\n".join(block) + "\n\nDespués: ttid_ms."
        page = perf.md_to_html(text)
        self.assertEqual(page.count('<pre class="diff">'), 1)
        self.assertIn('<span class="ctx"> después</span>', page)
        self.assertEqual([code for code, _ in perf.split_code(text)], [False, True, False])
        human = perf.humanize_metrics(text, ["ttid_ms"], {})
        self.assertIn("val ttid_ms = 2", human)  # dentro del diff no se toca
        self.assertNotIn("Después: ttid_ms.", human)
        self.assertEqual(perf.words_count(text), perf.words_count("Antes: ttid_ms.\n\nDespués: ttid_ms."))

    def test_el_video_se_detiene_solo_con_su_archivo(self):
        pattern = re.search(r"'(.+)'", perf.VIDEO_STOP).group(1)
        self.assertIn("-f", perf.VIDEO_STOP.split())
        self.assertTrue(re.search(pattern, "screenrecord --time-limit 180 /sdcard/hbperf-prueba.mp4"))
        self.assertFalse(re.search(pattern, "screenrecord /sdcard/mi-grabacion.mp4"))
        self.assertFalse(re.search(pattern, "sh -c " + perf.VIDEO_STOP))  # ni el propio shell que corre pkill

        class Process:
            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        class FakeAdb:
            def __init__(self):
                self.calls = []

            def shell(self, command, timeout=None):
                self.calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            def run(self, *args, timeout=None):
                return subprocess.CompletedProcess(args, 1, "", "")

        adb = FakeAdb()
        os.environ["HB_PERF_ESPERA"], saved = "0", os.environ.get("HB_PERF_ESPERA")
        try:
            perf.stop_video(adb, Process(), Path(os.devnull))
        finally:
            os.environ.pop("HB_PERF_ESPERA") if saved is None else os.environ.update(HB_PERF_ESPERA=saved)
        self.assertEqual(adb.calls[0], perf.VIDEO_STOP)

    def test_mismo_dispositivo(self):
        self.assertTrue(perf.same_device({"serial": "a", "modelo": "X"}, {"serial": "a", "modelo": "X"}))
        self.assertFalse(perf.same_device({"serial": "a", "modelo": "X"}, {"serial": "b", "modelo": "X"}))
        self.assertTrue(perf.same_device({"serial": None, "modelo": "X"}, {"serial": "b", "modelo": "X"}))
        self.assertFalse(perf.same_device({"modelo": "X"}, {"serial": "b", "modelo": "Y"}))
        self.assertEqual(perf.device_label({"serial": "b", "modelo": None}), "b")

    def test_presupuestos_de_pasos_iguales_en_todas_las_referencias(self):
        refs = SKILL / "references"
        models = (refs / "modelos.md").read_text(encoding="utf-8")
        table = models.split("## Presupuesto de pasos")[1].split("\n## ")[0]
        budget = {line.split("|")[1].strip(): (line.split("|")[2].strip(), line.split("|")[3].strip())
                  for line in table.splitlines() if re.match(r"\| \d · ", line)}
        self.assertEqual(budget["1 · Ficha y plan"], ("15", "25"))
        self.assertEqual(budget["2 · Diagnóstico"], ("20", "25 (30 con trazas pesadas o varios flujos)"))
        self.assertEqual(budget["3 · Mejora"], ("30", "30"))
        self.assertIn("| 1 · Ficha y plan (si no hay receta) | Intermedio | Medio | 15 (25 en flujos largos) |", models)
        self.assertIn("| Alto | 20 (25 en flujos largos; 30 con trazas pesadas o varios flujos) |", models)
        self.assertEqual(models.count("**Flujo largo:**"), 1)
        ficha = (refs / "ficha.md").read_text(encoding="utf-8")
        definition = re.search(r"\*\*Flujo largo:\*\* (.+?)\. Lo demás", models).group(1)
        self.assertIn("**Presupuesto y tareas (sesión 1).** 15 pasos (25 en un flujo largo: %s;" % definition, ficha)
        self.assertIn("Presupuesto: 15 pasos, o 25 en un flujo largo ([modelos.md](modelos.md) · Presupuesto de pasos)",
                      ficha)
        self.assertIn("**Presupuesto y tareas (sesión 2).** 20 pasos en un flujo corto, 25 en uno largo y 30 con trazas "
                      "pesadas o varios flujos", (refs / "diagnostico.md").read_text(encoding="utf-8"))
        self.assertIn("**Presupuesto y tareas (sesión 3).** 30 pasos", (refs / "mejoras.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
