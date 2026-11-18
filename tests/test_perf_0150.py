"""Tests de hb-performance 0.15.0: migración del setup de versiones anteriores (A), `siguiente` guía sola (B),
medición (C), ficha y pedido (E), costo (F), cierre (P), reportes (H y G) y la aceptación de punta a punta siguiendo solo
lo que imprime la skill (T). Los datos son inventados."""
import json
import os
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import ENV, ROOT, commit_all, git, init_repo, write
from test_perf import GOOD, DeviceBase, PerfBase, perf
from test_perf_0140 import (AGENTS, HOOKS, PKG, REMOTE, WIRING, SetupBase, ends_with_step, executable, make_project,
                            pasteable)

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


if __name__ == "__main__":
    unittest.main()
