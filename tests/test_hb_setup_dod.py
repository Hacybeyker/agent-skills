"""hb-setup 1.3.0: el DoD refleja lo que corre el CI o, sin CI, lo que el build tiene (S1), con la forma que `perf.py
cerrar --dod` sabe correr (S2); la sección de rendimiento de hb-performance se conserva y se revisa sin reescribirla
(S3), y los archivos locales de las herramientas de IA quedan fuera de git sin tocar .gitignore (S4). Datos inventados."""
import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ENV, ROOT, commit_all, init_repo, run, write

SKILL = ROOT / "skills" / "hb-setup"
DOD = SKILL / "scripts" / "dod.py"
CONTEXTO = SKILL / "scripts" / "contexto.py"
PERF = ROOT / "skills" / "hb-performance" / "scripts" / "perf.py"

CI = """name: CI
on: [pull_request]
jobs:
  verificar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/verificar
      - name: Tests
        run: ./gradlew testDebugUnitTest --stacktrace
      - name: Cobertura
        run: ./gradlew koverXmlReport koverVerify
      - name: Análisis externo
        run: ./gradlew sonar
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
  build:
    uses: ./.github/workflows/build.yml
"""
ACTION = """name: Verificar
runs:
  using: composite
  steps:
    - name: Lint
      shell: bash
      run: |
        ./gradlew ktlintCheck detekt \\
          :app:lintDebug
"""
REUSABLE = """on:
  workflow_call:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: ./gradlew :app:assembleDebug
      - run: ./gradlew publishToMavenLocal
"""
APP_BUILD = ('plugins {\n    id("com.android.application")\n    id("org.jlleitschuh.gradle.ktlint")\n'
             '    id("org.jetbrains.kotlinx.kover")\n}\n\nkover { reports { verify { rule { minBound(0) } } } }\n')


def load_perf():
    spec = importlib.util.spec_from_file_location("perf_para_s2", str(PERF))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DodBase(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.repo), True)

    def dod(self):
        result = run([sys.executable, "-I", DOD, "--repo", self.repo], self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def commands(self, text):
        prefix = "cd %s && " % self.repo.resolve()
        out = []
        for line in text.splitlines():
            if line[:3] in ("1. ", "2. ", "3. "):
                command = line.split("`", 1)[1].rsplit("`", 1)[0]
                self.assertTrue(command.startswith(prefix), command)  # S2: todos empiezan con cd a la ruta
                out.append(command[len(prefix):])
        return out


class DodFromCiTest(DodBase):
    """S1: con CI, el DoD junta lo que corren los workflows, las acciones compuestas locales y los workflow_call."""

    def setUp(self):
        super().setUp()
        write(self.repo / ".github" / "workflows" / "ci.yml", CI)
        write(self.repo / ".github" / "workflows" / "build.yml", REUSABLE)
        write(self.repo / ".github" / "actions" / "verificar" / "action.yml", ACTION)
        write(self.repo / "app" / "build.gradle.kts", APP_BUILD)
        write(self.repo / "gradlew", "#!/bin/sh\n")

    def test_lee_la_accion_compuesta_y_el_workflow_reutilizable(self):
        text = self.dod()
        commands = self.commands(text)
        self.assertEqual(commands[0], "./gradlew ktlintFormat")  # S2: el formateador, en su propia invocación
        self.assertEqual(commands[1], "./gradlew ktlintCheck detekt :app:lintDebug testDebugUnitTest :app:assembleDebug")
        self.assertEqual(len(commands), 2)  # S2: una sola invocación con checks, tests y build
        self.assertNotIn("publishToMavenLocal", text)
        self.assertIn(".github/actions/verificar/action.yml", text)
        self.assertIn(".github/workflows/build.yml", text)

    def test_lo_que_no_puede_hacer_fallar_un_pr_va_aparte_con_el_motivo(self):
        text = self.dod()
        outside = next(line for line in text.splitlines() if line.startswith("Fuera del DoD:"))
        self.assertIn("`koverVerify` (la cobertura mínima configurada es 0", outside)
        self.assertIn("`sonar` (necesita SONAR_TOKEN", outside)
        self.assertIn("`koverXmlReport` (genera un reporte", outside)
        self.assertNotIn("koverVerify", self.commands(text)[1])

    def test_una_cobertura_con_minimo_real_entra_al_dod(self):
        write(self.repo / "app" / "build.gradle.kts", APP_BUILD.replace("minBound(0)", "minBound(80)"))
        self.assertIn("koverVerify", self.commands(self.dod())[1])

    def test_perf_cerrar_dod_lo_corre_tal_cual(self):
        """S2 ↔ P2: el DoD que escribe hb-setup es el que `perf.py cerrar --dod` lee: el formateador primero y solo, y
        después una sola invocación."""
        write(self.repo / "AGENTS.md", "# Demo\n\n%s\n## Git\n\n- Conventional Commits\n" % self.dod())
        steps, skipped, applied, unresolved = load_perf().dod_plan(self.repo)
        self.assertEqual([step["formato"] for step in steps], [True, False])
        self.assertTrue(steps[1]["comando"].endswith(":app:lintDebug testDebugUnitTest :app:assembleDebug"))
        self.assertEqual((skipped, applied, unresolved), ([], [], []))  # "Fuera del DoD" y "Origen" solo informan


class DodWithoutCiTest(DodBase):
    """S1: sin CI, el DoD nunca queda vacío: sale del build, con su línea de origen, sin agregar nada."""

    def test_con_formateador_y_tests(self):
        write(self.repo / "gradlew", "#!/bin/sh\n")
        write(self.repo / "app" / "build.gradle.kts", APP_BUILD)
        write(self.repo / "app" / "src" / "test" / "kotlin" / "AppTest.kt", "class AppTest\n")
        text = self.dod()
        self.assertEqual(self.commands(text), ["./gradlew ktlintFormat",
                                               "./gradlew ktlintCheck testDebugUnitTest :app:assembleDebug"])
        self.assertIn("Origen: DoD derivado del build; el proyecto no tiene CI.", text)

    def test_sin_tests_el_dod_es_compilar(self):
        write(self.repo / "gradlew", "#!/bin/sh\n")
        write(self.repo / "app" / "build.gradle.kts", 'plugins { id("com.android.application") }\n')
        text = self.dod()
        self.assertEqual(self.commands(text), ["./gradlew :app:assembleDebug"])
        self.assertIn("Origen: DoD derivado del build; el proyecto no tiene CI ni tests.", text)

    def test_un_script_sin_build_valida_la_sintaxis(self):
        write(self.repo / "instalar.sh", "#!/bin/sh\necho hola\n")
        text = self.dod()
        self.assertEqual(self.commands(text), ["bash -n instalar.sh"])
        self.assertIn("valida la sintaxis", text)

    def test_node_con_el_gestor_del_lockfile(self):
        write(self.repo / "package.json", '{"scripts": {"format": "prettier -w .", "lint": "eslint .", '
                                          '"test": "vitest", "build": "vite build"}}')
        write(self.repo / "pnpm-lock.yaml", "lockfileVersion: 9\n")
        self.assertEqual(self.commands(self.dod()), ["pnpm format", "pnpm lint && pnpm test && pnpm build"])


class PerformanceSectionAuditTest(unittest.TestCase):
    """S3: hb-setup conserva el bloque de hb-performance y señala, sin reescribirlas, las líneas de la sección de
    rendimiento que traen un serial o contradicen el bloque."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = init_repo(pathlib.Path(self.tmp.name))
        self.agents = ("# Demo\n\n## Rendimiento\n\n- Setup listo.\n- Instalar: `ANDROID_SERIAL=emulator-5554 ./gradlew "
                       ":app:installProfiling`\n\n<!-- hb-performance:estado -->\n- Estado del setup (lo mantiene "
                       "`perf.py`: no lo edites): instrumentación en el repo: no · hb-performance 0.19.0\n- Setup: en "
                       "parche `reports/perf/setup/parches/perf-setup-1.patch`\n<!-- /hb-performance:estado -->\n\n"
                       "## DoD\n\n1. `true`\n")
        write(self.repo / "AGENTS.md", self.agents)
        commit_all(self.repo, "base")

    def tearDown(self):
        self.tmp.cleanup()

    def test_senala_sin_reescribir(self):
        result = run([sys.executable, "-I", CONTEXTO, "rendimiento", "--repo", self.repo], self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<!-- hb-performance:estado -->", result.stdout)  # el bloque, para conservarlo tal cual
        self.assertIn("ANDROID_SERIAL=<serial> ./gradlew :app:installProfiling", result.stdout)
        self.assertIn("«- Setup listo.» → quitarla", result.stdout)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), self.agents)  # no escribe nada


class LocalAiFilesTest(unittest.TestCase):
    """S4: los archivos locales de las herramientas de IA, sin versionar ni ignorar, van a .git/info/exclude."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        (pathlib.Path(self.tmp.name) / "repo").mkdir()
        self.repo = init_repo(pathlib.Path(self.tmp.name) / "repo")
        # sin el ignore global de la máquina (~/.config/git/ignore), que puede ignorar ya estos archivos
        self.env = dict(ENV, XDG_CONFIG_HOME=str(pathlib.Path(self.tmp.name) / "xdg"))
        write(self.repo / ".gitignore", "build/\n")
        write(self.repo / ".claude" / "settings.json", "{}\n")
        commit_all(self.repo, "base")
        write(self.repo / ".claude" / "settings.local.json", "{}\n")
        write(self.repo / "CLAUDE.local.md", "notas\n")
        write(self.repo / ".aider.tags.cache.v4" / "cache.db", "x")
        write(self.repo / "src" / "Nuevo.kt", "class Nuevo\n")  # trabajo del usuario: no se toca

    def tearDown(self):
        self.tmp.cleanup()

    def contexto(self, *args):
        return subprocess.run([sys.executable, "-I", str(CONTEXTO)] + [str(a) for a in args] + ["--repo", str(self.repo)],
                              cwd=str(self.repo), env=self.env, capture_output=True, text=True, encoding="utf-8")

    def test_preparar_los_excluye_y_lo_dice(self):
        result = self.contexto("preparar", "--modo", "versionado")
        self.assertEqual(result.returncode, 0, result.stderr)
        exclude = (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        for line in ("/.claude/settings.local.json", "/CLAUDE.local.md", "/.aider.tags.cache.v4/"):
            self.assertIn(line, exclude.splitlines())
            self.assertIn("%s (archivo local de una herramienta de IA)" % line, result.stdout)
        self.assertNotIn("Nuevo.kt", exclude)
        self.assertEqual((self.repo / ".gitignore").read_text(encoding="utf-8"), "build/\n")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=str(self.repo),
                                env=self.env, capture_output=True, text=True).stdout
        self.assertNotIn("settings.local.json", status)
        self.assertIn("src/Nuevo.kt", status)

    def test_estado_los_lista(self):
        result = self.contexto("estado")
        self.assertIn("/.claude/settings.local.json", result.stdout)
        self.assertNotIn("/.claude/settings.json", result.stdout)


if __name__ == "__main__":
    unittest.main()
