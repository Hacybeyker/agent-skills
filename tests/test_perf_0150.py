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

from helpers import ENV, ROOT, commit_all, git, init_repo, write
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
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "marcas", "--carpeta",
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
        return subprocess.run([sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args], cwd=str(self.root),
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
        self.assertIn("2. Marcas: repuestas en .", out)
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
                                    "attached\\nemulator-5554\\tdevice\\n' ;;\n  *'echo viva'*) echo viva ;;\nesac\n"
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
        self.assertIn("quedó algo a medias: la captura de antes del flujo catalogo-lista se interrumpió en la corrida 2", out)
        self.assertIn("Interrumpir es seguro", out)
        self.assertTrue(commands_in(out)[0].endswith("recuperar --carpeta %s" % self.rel))
        out = self.ok_in("recuperar", "--carpeta", self.rel)
        self.assertIn("Detuve la traza que seguía grabando en el dispositivo", out)
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
        video = self.plan.parent / "prueba-home.mp4"
        self.assertTrue(video.is_file())
        self.assertIn("Video de la prueba: %s" % video, out)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn('"screenrecord", "--time-limit", "180", "/sdcard/hbperf-prueba.mp4"', log)
        # (el screenrecord falso termina solo: el pkill -INT de verdad se valida en dispositivo)
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
        self.assertIn("Las coordenadas de ese botón, del volcado de esa pantalla: cd /p && python3 -I perf.py nodos "
                      "logs/x.xml --texto Continuar", " ".join(lines))



# ── E, F, H: costo, velocidad del reporte y textos ───────────────────────────
if __name__ == "__main__":
    unittest.main()
