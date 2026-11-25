"""Tests de hb-performance 0.14.0: la skill no instala ni configura nada en la máquina (B), el setup lo maneja la skill
(A), nunca se edita un módulo que el build toma como binario (D) y los fixtures de la versión (C). Los datos son
inventados."""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import ENV, ROOT, commit_all, git, init_repo, perf_argv, write
from test_perf import PerfBase, perf

SKILL = ROOT / "skills" / "hb-performance"
SCRIPT = SKILL / "scripts" / "perf.py"
FIXTURES = ROOT / "tests" / "fixtures" / "hb-performance-0.14.0"
PKG = "com.example.app"
REMOTE = "git@example.com:equipo/app.git"
# Un comando que escribe en un perfil del shell: una redirección, tee o sed -i sobre el archivo de configuración.
PROFILE_FILE = (r"(?:~|\$HOME|\$\{HOME\})/(?:\.zshrc|\.zprofile|\.zshenv|\.zlogin|\.bashrc|\.bash_profile|\.bash_login|"
                r"\.profile|\.config/fish/\S*)")
PROFILE_WRITE = re.compile(r"(?:>>?\s*[\"']?%(f)s|\btee\b[^\n|;&]*%(f)s|\bsed\s+-i[^\n]*%(f)s)" % {"f": PROFILE_FILE})
GLOBAL_ENV = re.compile(r"\blaunchctl\s+setenv\b|\bsetx\b|/etc/(?:profile|environment|paths)|\bdefaults\s+write\b")
PROFILE_NAMES = (".zshrc", ".zprofile", ".zshenv", ".zlogin", ".bashrc", ".bash_profile", ".bash_login", ".profile")


def executable(path, text):
    write(path, text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def tail(text, lines=14):
    return "\n".join([line for line in text.splitlines() if line.strip()][-lines:])


def ends_with_step(text):
    """True si una salida termina diciendo lo que sigue (un comando completo con cd, o un chat nuevo) o, cuando ya no
    queda nada, que no queda ningún paso por ejecutar."""
    last = tail(text)
    return bool(re.search(r"^\s*(?:\d+\.\s.*\n\s*)?cd \S+ && \S", last, re.M) or "Chat nuevo" in last
                or perf.NO_STEPS_LEFT in last)


def pasteable(text):
    """(comandos `cd … && …` de una salida, los que traen un marcador sin resolver)."""
    # (el comando `consumo` trae a propósito el costo por completar: lo da la herramienta de IA al cerrar el chat)
    commands = [line.strip() for line in text.splitlines() if line.strip().startswith("cd ") and " consumo " not in line]
    return commands, [command for command in commands if re.search(r"<[^>\s][^>]*>", command)]


class MachineBase(PerfBase):
    """Un HOME y un PATH temporales: nada de lo que hay instalado en la máquina que corre los tests cuenta."""

    def setUp(self):
        super().setUp()
        self.home = self.dir / "home"
        self.bin = self.dir / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        self.clean = {"HOME": str(self.home), "PATH": str(self.bin)}
        self.removed = ("ADB", "ANDROID_HOME", "ANDROID_SDK_ROOT", "JAVA_HOME", "TRACE_PROCESSOR", "RETRACE")
        perf._TOOLS_SAID.clear()
        perf._JAVA_HOME.clear()
        perf.QUIET_TOOLS["activo"] = False  # otro test pudo dejarlo puesto al correr `teclear` o `nodos` en este proceso

    def environment(self, **extra):
        env = {key: value for key, value in os.environ.items() if key not in self.removed}
        env.update(self.clean)
        env.update(extra)
        return mock.patch.dict(os.environ, env, clear=True)

    def profiles(self):
        return [name for name in PROFILE_NAMES if (self.home / name).exists()] + (
            ["fish"] if (self.home / ".config" / "fish").exists() else [])


class TraceProcessorTest(MachineBase):
    """B1 y B2: trace_processor se encuentra en ~/.local/bin sin el PATH, y si falta, el mensaje no toca la máquina."""

    def test_se_encuentra_en_local_bin_sin_el_path(self):
        target = executable(self.home / ".local" / "bin" / "trace_processor", "#!/bin/sh\necho v1\n")
        with self.environment(), mock.patch("sys.stderr") as err:
            self.assertEqual(perf.find_tp(None), str(target))
            perf.find_tp(None)
        said = "".join(call.args[0] for call in err.write.call_args_list)
        self.assertEqual(said.count("uso trace_processor de %s" % target), 1)  # lo dice una sola vez

    def test_trace_processor_shell_tambien(self):
        target = executable(self.home / ".local" / "bin" / "trace_processor_shell", "#!/bin/sh\necho v1\n")
        with self.environment(), mock.patch("sys.stderr"):
            self.assertEqual(perf.find_tp(None), str(target))

    def test_el_path_y_la_variable_ganan(self):
        executable(self.home / ".local" / "bin" / "trace_processor", "#!/bin/sh\n")
        in_path = executable(self.bin / "trace_processor", "#!/bin/sh\n")
        other = executable(self.dir / "otro" / "tp", "#!/bin/sh\n")
        with self.environment():
            self.assertEqual(perf.find_tp(None), str(in_path))
        with self.environment(TRACE_PROCESSOR=str(other)):
            self.assertEqual(perf.find_tp(None), str(other))

    def test_si_falta_dice_donde_busco_y_no_toca_el_perfil(self):
        with self.environment():
            with self.assertRaises(perf.Precondicion) as raised:
                perf.find_tp(None)
        text = str(raised.exception)
        order = [text.index(part) for part in ("es obligatorio", "Dónde lo busqué", "Cómo obtenerlo", "en el PATH, agrégalo")]
        self.assertEqual(order, sorted(order))
        self.assertIn(str(self.home / ".local" / "bin" / "trace_processor"), text)
        self.assertIn("no edita la configuración de tu shell", text)
        command = raised.exception.seguir[0][1]
        self.assertIn("[ -e ~/.local/bin/trace_processor ] || [ -L ~/.local/bin/trace_processor ] ||", command)
        # (sin la ruta del HOME temporal, que es aleatoria y podría traer una de estas palabras)
        self.assertNotRegex(command + text.replace(str(self.home), "~"), r"zshrc|bashrc|profile|export PATH|sudo")
        self.assertFalse(PROFILE_WRITE.search(command))

    def test_el_comando_de_descarga_no_pisa_ni_toca_perfiles(self):
        # un curl de mentira que escribe lo que le piden en -o
        executable(self.bin / "curl", "#!/bin/sh\nwhile [ $# -gt 0 ]; do if [ \"$1\" = -o ]; then out=\"$2\"; fi; shift; "
                                      "done\nprintf '#!/bin/sh\\necho descargado\\n' > \"$out\"\necho llamado >> \"$HOME/curl.log\"\n")
        env = dict(ENV, HOME=str(self.home), PATH="%s:/usr/bin:/bin" % self.bin)
        command = perf.tp_download_command()
        done = subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        target = self.home / ".local" / "bin" / "trace_processor"
        self.assertEqual(done.stdout.strip(), "descargado")
        self.assertTrue(os.access(str(target), os.X_OK))
        self.assertFalse((target.parent / "trace_processor.descarga").exists())
        # ya existe: no se descarga de nuevo ni se pisa
        write(target, "#!/bin/sh\necho el-mio\n")
        done = subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "el-mio")
        self.assertEqual((self.home / "curl.log").read_text().count("llamado"), 1)
        self.assertEqual(self.profiles(), [])

    def test_un_enlace_roto_no_se_reemplaza(self):
        target = self.home / ".local" / "bin" / "trace_processor"
        target.parent.mkdir(parents=True)
        os.symlink(str(self.dir / "no-existe"), str(target))
        with self.environment():
            with self.assertRaises(perf.Precondicion) as raised:
                perf.find_tp(None)
        self.assertIn("no es un archivo ejecutable (o es un enlace roto)", str(raised.exception))
        executable(self.bin / "curl", "#!/bin/sh\necho llamado >> \"$HOME/curl.log\"\nexit 1\n")
        env = dict(ENV, HOME=str(self.home), PATH="%s:/usr/bin:/bin" % self.bin)
        subprocess.run(["sh", "-c", perf.tp_download_command()], env=env, capture_output=True, text=True)
        self.assertTrue(os.path.islink(str(target)))  # el comando de descarga no lo toca
        self.assertFalse((self.home / "curl.log").exists())

    def test_un_archivo_que_no_se_puede_ejecutar_no_se_reemplaza(self):
        write(self.home / ".local" / "bin" / "trace_processor", "no soy un programa\n")
        with self.environment():
            with self.assertRaises(perf.Precondicion) as raised:
                perf.find_tp(None)
        self.assertIn("no es un archivo ejecutable", str(raised.exception))
        self.assertNotIn("curl", json.dumps(raised.exception.seguir, ensure_ascii=False))

    def test_la_salida_del_comando_termina_con_el_paso(self):
        env = dict(self.env, HOME=str(self.home), PATH="/usr/bin:/bin")
        for name in self.removed:
            env.pop(name, None)
        done = subprocess.run(perf_argv(SCRIPT) + ["consulta", "traza.perfetto-trace", "--sql", "select 1"],
                              cwd=str(self.dir), env=env, capture_output=True, text=True, encoding="utf-8")
        if "falta trace_processor" not in done.stderr:
            self.skipTest("hay un trace_processor en /usr/bin o /bin")
        self.assertEqual(done.returncode, perf.Precondicion.code)
        self.assertIn("Cómo seguir:", done.stderr)
        self.assertTrue(ends_with_step(done.stderr), done.stderr)
        commands, unresolved = pasteable(done.stderr)
        self.assertEqual(unresolved, [])
        self.assertIn("consulta traza.perfetto-trace --sql 'select 1'", commands[-1])
        self.assertEqual(self.profiles(), [])


class AdbAndJavaTest(MachineBase):
    """B2: adb, retrace y Java se encuentran en las rutas por defecto, y lo encontrado va solo al proceso hijo."""

    def test_adb_en_las_rutas_por_defecto_del_sdk(self):
        for parts in (("Library", "Android", "sdk"), ("Android", "Sdk")):
            with self.subTest(sdk="/".join(parts)):
                perf._TOOLS_SAID.clear()
                sdk = self.home.joinpath(*parts)
                adb = executable(sdk / "platform-tools" / "adb", "#!/bin/sh\n")
                with self.environment(), mock.patch("sys.stderr") as err:
                    self.assertEqual(perf.adb_binary(), str(adb))
                    perf.adb_binary()
                    self.assertEqual(perf.adb_shown(), str(adb))  # el comando impreso se puede pegar
                said = "".join(call.args[0] for call in err.write.call_args_list)
                self.assertEqual(said.count("uso adb de %s" % adb), 1)
                shutil.rmtree(str(sdk))

    def test_orden_adb_path_android_home(self):
        home_adb = executable(self.home / "Android" / "Sdk" / "platform-tools" / "adb", "#!/bin/sh\n")
        own = executable(self.dir / "sdk" / "platform-tools" / "adb", "#!/bin/sh\n")
        with self.environment(ANDROID_HOME=str(self.dir / "sdk")), mock.patch("sys.stderr"):
            self.assertEqual(perf.adb_binary(), str(own))
        with self.environment(ANDROID_SDK_ROOT=str(self.dir / "sdk")), mock.patch("sys.stderr"):
            self.assertEqual(perf.adb_binary(), str(own))
        in_path = executable(self.bin / "adb", "#!/bin/sh\n")
        with self.environment(ANDROID_HOME=str(self.dir / "sdk")):
            self.assertEqual(perf.adb_binary(), str(in_path))
            self.assertEqual(perf.adb_shown(), "adb")
        with self.environment(ADB="/otra/ruta/adb"):
            self.assertEqual(perf.adb_binary(), "/otra/ruta/adb")
        self.assertTrue(home_adb.is_file())

    def test_sin_adb_dice_que_falta_y_donde_obtenerlo(self):
        with self.environment():
            with self.assertRaises(perf.Precondicion) as raised:
                perf.adb_binary()
        text = str(raised.exception)
        for part in ("falta adb", "es obligatorio", "Dónde lo busqué", "~/Library/Android/sdk", "~/Android/Sdk",
                     perf.PLATFORM_TOOLS_URL, "ADB=<ruta>", perf.NO_MACHINE_CHANGES):
            self.assertIn(part, text)
        self.assertFalse(PROFILE_WRITE.search(text))
        self.assertTrue(raised.exception.seguir)

    def test_java_del_jbr_solo_para_el_hijo(self):
        jbr = self.dir / "studio" / "jbr"
        executable(jbr / "bin" / "java", "#!/bin/sh\n")
        with self.environment(), mock.patch.object(perf, "STUDIO_JBR", (str(self.dir / "no-existe"), str(jbr))), \
                mock.patch("sys.stderr") as err:
            before = dict(os.environ)
            self.assertEqual(perf.java_home(), (str(jbr), "el JBR de Android Studio", True))
            env = perf.child_env(java=True)
            self.assertEqual(env["JAVA_HOME"], str(jbr))
            self.assertTrue(env["PATH"].startswith(str(self.bin)))  # lo encontrado va al final: no tapa nada
            self.assertTrue(env["PATH"].endswith(str(jbr / "bin")))
            self.assertEqual(dict(os.environ), before)  # el entorno de quien corre perf.py no cambia
            self.assertIsNone(perf.child_env())  # sin Java que pasar y sin adb fuera del PATH: el hijo hereda
        self.assertIn("uso Java de %s" % jbr, "".join(call.args[0] for call in err.write.call_args_list))

    def test_java_home_y_el_path_no_se_cambian(self):
        jdk = self.dir / "jdk"
        executable(jdk / "bin" / "java", "#!/bin/sh\n")
        with self.environment(JAVA_HOME=str(jdk)), mock.patch.object(perf, "STUDIO_JBR", ()):
            self.assertEqual(perf.java_home(), (None, "JAVA_HOME", True))
            self.assertIsNone(perf.child_env(java=True))
        perf._JAVA_HOME.clear()
        with self.environment(), mock.patch.object(perf, "STUDIO_JBR", ()):
            self.assertEqual(perf.java_home(), (None, "", False))

    def test_el_hijo_ve_el_adb_que_encontro_perf(self):
        sdk = self.home / "Android" / "Sdk"
        executable(sdk / "platform-tools" / "adb", "#!/bin/sh\n")
        with self.environment():
            env = perf.child_env({"PATH": str(self.bin), "OTRA": "1"})
            self.assertEqual(env["PATH"], os.pathsep.join([str(self.bin), str(sdk / "platform-tools")]))
            self.assertEqual(env["OTRA"], "1")

    def test_retrace_en_el_sdk_por_defecto(self):
        retrace = executable(self.home / "Library" / "Android" / "sdk" / "cmdline-tools" / "latest" / "bin" / "retrace",
                             "#!/bin/sh\n")
        with self.environment():
            self.assertEqual(perf.find_retrace(), str(retrace))
        shutil.rmtree(str(self.home / "Library"))
        with self.environment():
            self.assertIsNone(perf.find_retrace())
        for part in ("es opcional", "Command-line Tools", perf.CMDLINE_TOOLS_URL, perf.NO_MACHINE_CHANGES):
            self.assertIn(part, perf.RETRACE_INSTALL)
        for part in ("JAVA_HOME", "JBR de Android Studio", "opcional", perf.JDK_URL):
            self.assertIn(part, perf.JAVA_MISSING)

    def test_maestro_que_falta_se_dice_antes_de_medir(self):
        write(self.dir / "preparar.sh", "# maestro test viejo.yaml\nmaestro test flows/login.yaml\n")
        with self.environment():
            self.assertIsNone(perf.missing_maestro("adb shell input tap 1 1", self.dir))
            text = perf.missing_maestro("bash preparar.sh", self.dir)
            for part in ("falta Maestro", "opcional", "Dónde lo busqué", perf.MAESTRO_URL, perf.NO_MACHINE_CHANGES):
                self.assertIn(part, text)
            executable(self.home / ".maestro" / "bin" / "maestro", "#!/bin/sh\n")
            self.assertIsNone(perf.missing_maestro("bash preparar.sh", self.dir))
            with mock.patch.object(perf, "STUDIO_JBR", ()), mock.patch("sys.stderr") as err:
                self.assertTrue(perf.child_env(java=True)["PATH"].endswith(str(self.home / ".maestro" / "bin")))
            self.assertIn("uso Maestro de", "".join(call.args[0] for call in err.write.call_args_list))


class NoMachineChangesTest(unittest.TestCase):
    """B3 y la regla de la sección 2: nada de lo que la skill corre, imprime o documenta escribe en un perfil del shell,
    cambia variables globales ni pide permisos de administrador."""

    def texts(self):
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                try:
                    yield path, path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
        for name in ("README.md", "PROMPTS.md", "CATALOG.md"):
            yield ROOT / name, (ROOT / name).read_text(encoding="utf-8")

    def test_ningun_archivo_escribe_en_un_perfil_del_shell(self):
        for path, text in self.texts():
            with self.subTest(archivo=str(path.relative_to(ROOT))):
                self.assertIsNone(PROFILE_WRITE.search(text))
                self.assertIsNone(GLOBAL_ENV.search(text))
                if SKILL in path.parents:
                    self.assertNotRegex(text, r"\bsudo\b")
                    self.assertNotRegex(text, r"export PATH=")

    def test_el_detector_reconoce_lo_que_busca(self):
        for bad in ("echo 'export PATH=x' >> ~/.zshrc", "echo x > $HOME/.bash_profile", "sed -i '' 's/a/b/' ~/.bashrc",
                    "echo x | tee -a ~/.profile", "echo x >> ~/.config/fish/config.fish", 'echo x >> "${HOME}/.zprofile"'):
            self.assertIsNotNone(PROFILE_WRITE.search(bad), bad)
        for fine in ("cd ~ && mkdir -p ~/.local/bin", "no edita ~/.zshrc", "git diff > parche.patch"):
            self.assertIsNone(PROFILE_WRITE.search(fine), fine)

    def test_requisitos_documentados(self):
        setup = (SKILL / "references" / "setup.md").read_text(encoding="utf-8")
        section = setup.split("## Requisitos de la máquina")[1].split("\n## ")[0]
        for part in ("no instala ni configura nada", "Python 3.8", "git", "`adb`", "`trace_processor`", "Java 17",
                     "`retrace`", "Maestro", "solo lectura"):
            self.assertIn(part, section)
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        compatibility = next(line for line in skill.splitlines() if line.startswith("compatibility:"))
        for part in ("no instala ni configura nada", "adb", "trace_processor", "Python 3.8", "git", "Java 17"):
            self.assertIn(part, compatibility)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme, r"hb-performance[^\n]*no las instala")



# ── A · El setup lo maneja la skill ──────────────────────────────────────────
AGENTS = ("# Proyecto\n\n## Rendimiento\n\n- applicationId: %s\n- Instalar: `./gradlew :app:installProfiling`\n- setup listo\n\n"
          "## DoD\n\n1. `true`\n\n## Git\n\n- Conventional Commits\n" % PKG)
BUILD = ('plugins { id("com.android.application") }\n\nandroid {\n    buildTypes {\n        release { isMinifyEnabled = true }\n'
         '    }\n}\n\ndependencies {\n    implementation("com.squareup.okhttp3:okhttp:4.12.0")\n}\n')
CLIENT = ("package com.example.app.red\n\nimport okhttp3.OkHttpClient\n\nobject Red {\n    fun cliente(): OkHttpClient {\n"
          "        val builder = OkHttpClient.Builder()\n        builder.retryOnConnectionFailure(true)\n"
          "        builder.followRedirects(true)\n        return builder.build()\n    }\n\n    fun uno() = 1\n    fun dos() = 2\n"
          "    fun tres() = 3\n    fun cuatro() = 4\n    fun cinco() = 5\n    fun seis() = 6\n    fun siete() = 7\n"
          "    fun ocho() = 8\n\n    fun version() = \"1\"\n}\n")
WIRED_BUILD = BUILD.replace("        release { isMinifyEnabled = true }\n",
                            "        release { isMinifyEnabled = true }\n        create(\"profiling\") {\n"
                            "            initWith(getByName(\"release\"))\n        }\n")
WIRED_CLIENT = CLIENT.replace("        val builder = OkHttpClient.Builder()\n",
                              "        val builder = OkHttpClient.Builder()\n        PerfHooks.okHttp(builder)\n")
HOOKS = "app/src/main/kotlin/com/example/app/perf/PerfHooks.kt"
RED = "app/src/main/kotlin/com/example/app/red/Red.kt"
# El build type lo cablea la sesión 0 a mano y no es inequívoco (un `initWith(...)` no dice "setup"): se pasa con --archivos.
WIRING = ("--archivos", "app/build.gradle.kts")
STATE = ("# Rendimiento · Pagos · 2099-01-01\n\n## Siguiente paso\n\n- x\n\n## Mapa del alcance\n\n- `app/Pagos.kt:1`: la pantalla\n\n"
         "## Cambios temporales por revertir\n\n| Archivo | Repo o módulo | Qué es | Altera | ¿Revertido? |\n"
         "| --- | --- | --- | --- | --- |\n%s\n## Advertencias para el diagnóstico\n\n<!-- perf:advertencias -->\n"
         "<!-- /perf:advertencias -->\n\n## Hallazgos\n\n| # | Síntoma | Evidencia | Causa raíz | Tipo |\n"
         "| --- | --- | --- | --- | --- |\n\n## Decisiones\n\n- x\n\n## Consumo\n\n| Sesión | Modelo | Costo o tokens | Pasos |\n"
         "| --- | --- | --- | --- |\n")
PATCH_NAME = re.compile(r"perf-setup-%s-\d{8}-\d{4}(?:-\d+)?\.patch" % re.escape(perf.VERSION))


def make_project(root, agents=AGENTS, remote=REMOTE):
    """Un proyecto Android mínimo en un repo de git, con un remoto inventado."""
    root.mkdir(parents=True, exist_ok=True)
    init_repo(root)
    if remote:
        git(root, "remote", "add", "origin", remote)
    write(root / "settings.gradle.kts", 'include(":app")\n')
    write(root / "app" / "build.gradle.kts", BUILD)
    write(root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt", CLIENT)
    if agents is not None:
        write(root / "AGENTS.md", agents)
    commit_all(root, "base")
    return root


class SetupBase(PerfBase):
    """Un proyecto en un repo de git temporal y un HOME temporal: el setup lo genera `instrumentar` de verdad."""

    def setUp(self):
        super().setUp()
        self.root = make_project(self.dir / "proyecto")
        self.home = self.dir / "home"
        self.home.mkdir()
        # un adb de mentira sin dispositivos: ningún test llama al adb real de la máquina (que arranca su servidor y
        # escribe en la carpeta del usuario)
        fake_adb = executable(self.dir / "bin" / "adb", "#!/bin/sh\necho 'List of devices attached'\n")
        self.env = dict(ENV, HOME=str(self.home), ADB=str(fake_adb))
        self.patches = self.root / "reports" / "performance" / "setup" / "parches"

    def run_perf(self, *args, cwd=None):
        return subprocess.run(perf_argv(SCRIPT) + [str(a) for a in args], cwd=str(cwd or self.root),
                              env=self.env, capture_output=True, text=True, encoding="utf-8")

    def good(self, *args):
        result = self.run_perf(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(ends_with_step(result.stdout), "sin paso al final:\n" + result.stdout)
        self.assertEqual(pasteable(result.stdout)[1], [], result.stdout)
        return result.stdout

    def bad(self, *args, code=2):
        result = self.run_perf(*args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertTrue(ends_with_step(result.stderr), "sin paso al final:\n" + result.stderr)
        self.assertEqual(pasteable(result.stderr)[1], [], result.stderr)
        return result.stderr

    def instrument(self):
        """La sesión 0: `instrumentar` y el cableado a mano (el build type y el gancho de red)."""
        done = self.run_perf("instrumentar", "--modulo", "app", "--paquete", PKG + ".perf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        write(self.root / "app" / "build.gradle.kts", WIRED_BUILD)
        write(self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt", WIRED_CLIENT)

    def tree(self):
        """El contenido de todo lo que hay bajo app/ (lo que el setup toca)."""
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in sorted((self.root / "app").rglob("*")) if path.is_file()}

    def status(self):
        return [line for line in git(self.root, "status", "--short").splitlines() if not line.endswith("AGENTS.md")]

    def saved(self):
        """(parche vigente, ficha) según lo que quedó en la carpeta de parches."""
        found = [path for path in sorted(self.patches.glob("perf-setup-*.patch"))
                 if json.loads((path.parent / (path.name + ".json")).read_text(encoding="utf-8"))["estado"] == "vigente"]
        self.assertEqual(len(found), 1, found)
        return found[0], json.loads((found[0].parent / (found[0].name + ".json")).read_text(encoding="utf-8"))

    def in_patch(self):
        """Deja el setup guardado en su parche y quitado del árbol."""
        self.instrument()
        self.good("setup", "--guardar", "--quitar", *WIRING)
        return self.saved()

    def investigation(self, name="pagos", rows="", plan=None, closed=False):
        folder = self.root / "reports" / "perf" / name / "2099-01-01"
        plan = plan or {"paquete": PKG, "principales": ["pago_ms"], "instalar": "./gradlew :app:installProfiling",
                        "flujos": {name: {"recorrido": "true", "metricas_usuario": [
                            {"nombre": "pago_ms", "desde": {"marca": "MARK pago_inicio"},
                             "hasta": {"marca": "MARK pago_visible"}}]}}, "mejoras": []}
        write(folder / "plan.json", json.dumps(plan))
        write(folder / "estado.md", STATE % rows)
        exclude = self.root / ".git" / "info" / "exclude"  # como `nuevo`: la evidencia queda fuera de git
        ignored = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        if "/reports/" not in ignored.splitlines():
            write(exclude, ignored + "/reports/\n")
        if closed:
            write(folder / "fases.json", json.dumps({phase: {"fecha": "2020-01-01T10:0%d:00" % index, "corridas": 10,
                                                              "skill": perf.VERSION, "flujos": {name: {"corridas": 10}}}
                                                     for index, phase in enumerate(("antes", "control", "despues"))}))
            for report in ("reporte-inicial-dev.md", "reporte-final-dev.md"):
                write(folder / report, "x")
                # fecha fija, posterior a cualquier cierre: que los reportes sean "anteriores al cierre" no puede depender
                # de cuánto tarde la máquina entre escribirlos y cerrar
                os.utime(str(folder / report), (4102444800, 4102444800))  # 2100-01-01
        return folder


class SetupCaseTest(SetupBase):
    """A1: los tres casos y los raros, cada uno con su paso."""

    def test_sin_setup(self):
        write(self.root / "AGENTS.md", (FIXTURES / "sin-setup" / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(perf.setup_case(self.root)["caso"], "sin")
        out = self.good("setup", "--estado")
        self.assertIn("Setup de medición · sin setup", out)
        self.assertIn("Siguiente · falta la sesión 0 (setup)", out)
        self.assertIn("Chat nuevo", out)
        self.assertIn("sesión 0 (setup)", out)
        self.assertIn("Herramientas de la máquina (solo lectura", out)

    def test_versionado(self):
        self.instrument()
        write(self.root / "AGENTS.md", (FIXTURES / "versionado" / "AGENTS.md").read_text(encoding="utf-8"))
        commit_all(self.root, "build(perf): setup")
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"]), ("versionado", True))
        out = self.good("setup", "--estado")
        self.assertIn("Setup de medición · setup versionado", out)
        self.assertIn("el setup está listo para medir", out)
        before = self.tree()
        self.assertIn("no hay nada que guardar en un parche", self.good("setup", "--guardar"))
        out = self.good("setup", "--quitar")
        self.assertIn("El setup está versionado (en git): no se quita nada", out)
        self.assertIn(perf.NO_STEPS_LEFT, out)
        self.assertEqual(self.tree(), before)

    def test_en_el_arbol_sin_decidir(self):
        self.instrument()
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"]), ("sin_decidir", True))
        out = self.good("setup", "--estado")
        self.assertIn("decide si se versiona (su propio commit o PR) o va en un parche", out)
        self.assertIn("setup --guardar --quitar", out)
        before = self.tree()
        error = self.bad("setup", "--quitar")  # quitarlo sin guardarlo lo perdería
        self.assertIn("no está guardado en ningún parche: si lo quito, se pierde", error)
        self.assertEqual(self.tree(), before)

    def test_en_parche_puesto_y_ausente(self):
        patch, _ = self.in_patch()
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"], case["parche"]), ("parche", False, patch))
        self.assertEqual(perf.setup_label(case), "setup en parche, sin reponer")
        out = self.good("setup", "--estado")
        self.assertIn("Caso: en parche · el código no está en el árbol", out)
        self.assertIn("setup --reponer", pasteable(out)[0][0])
        self.good("setup", "--reponer")
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"]), ("parche", True))
        self.assertEqual(perf.setup_label(case), "setup en parche, puesto")
        self.assertIsNone(perf.setup_missing(self.root))

    def test_la_linea_de_versiones_anteriores_se_reconoce(self):
        for line in ("- Setup listo, en parche: `git apply herramientas/perf-setup.patch` antes de medir",
                     "- setup listo, en parche: `git apply herramientas/perf-setup.patch`",
                     "- Setup listo, en parche: `git -C . apply herramientas/perf-setup.patch` antes de medir; `git -C . "
                     "apply -R herramientas/perf-setup.patch` al terminar (lo escribió `perf.py cerrar`)."):
            with self.subTest(linea=line):
                write(self.root / "AGENTS.md", "## Rendimiento\n\n- applicationId: %s\n%s\n" % (PKG, line))
                said = perf.agents_setup(self.root)
                self.assertTrue(said["en_parche"] and said["antigua"])
                self.assertEqual(said["parches"], [self.root / "herramientas" / "perf-setup.patch"])
        # con el fixture de 0.13.0: la línea vieja, el bloque de estado de 0.13.0 y un parche sin ficha
        shutil.copytree(str(FIXTURES / "linea-vieja" / "herramientas"), str(self.root / "herramientas"))
        write(self.root / "AGENTS.md", (FIXTURES / "linea-vieja" / "AGENTS.md").read_text(encoding="utf-8"))
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"], case["ficha"]), ("parche", False, None))
        self.assertIn("línea de una versión anterior: se reconoce", self.good("setup", "--estado"))

    def test_setup_listo_sin_codigo_ni_parche(self):
        out = self.good("setup", "--estado")
        self.assertIn("setup perdido: AGENTS.md lo da por hecho y no está", out)
        self.assertIn("se perdió o lo quitaron a mano", out)
        self.assertIn("setup --vigente", out)
        self.assertIn("sesión 0 (setup)", out)
        error = self.bad("setup", "--reponer")
        self.assertIn("no hay nada que reponer: AGENTS.md dice que el setup está, pero no hay código ni parche", error)
        self.assertIn("Chat nuevo", error)

    def test_un_parche_sin_confirmar_se_pregunta(self):
        patch, _ = self.in_patch()
        write(self.root / "AGENTS.md", AGENTS)  # alguien descartó la línea del parche: queda "setup listo" y un parche
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["candidatos"]), ("duda", [patch]))
        out = self.good("setup", "--estado")
        self.assertIn("encontré un parche de setup que nadie confirmó (%s)" % patch.name, out)
        self.assertIn("setup --vigente %s" % patch.resolve(), out)
        before = self.tree()
        self.bad("setup", "--reponer")  # nunca adivina
        self.assertEqual(self.tree(), before)
        out = self.good("setup", "--vigente", patch)
        self.assertIn("✔ Parche de setup vigente: %s" % patch, out)
        self.assertEqual(perf.setup_case(self.root)["caso"], "parche")

    def test_el_codigo_en_el_arbol_manda_sobre_un_parche_que_no_existe(self):
        self.instrument()
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", "- Setup listo, en parche: `git apply "
                                                      "../parches/perf-setup.patch` antes de medir\n"))
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"]), ("sin_decidir", True))
        out = self.good("setup", "--estado")
        self.assertIn("setup en el árbol; AGENTS.md nombra un parche que no existe", out)
        self.assertNotIn("setup perdido", out)
        self.assertIn("setup --guardar --quitar", out)

    def test_la_linea_de_cerrar_de_0130_con_espacios(self):
        root = make_project(self.dir / "mi proyecto")
        patch = root / "reports" / "perf" / "x" / "parches" / "perf-setup-proyecto-20990101-1200.patch"
        write(patch, "x")
        line = "- Setup listo, en parche: `git -C %s apply %s` antes de medir; `git -C %s apply -R %s` al terminar (lo " \
               "escribió `perf.py cerrar`)." % ((perf.q(root), perf.q(patch)) * 2)
        write(root / "AGENTS.md", "## Rendimiento\n\n%s\n" % line)
        self.assertEqual(perf.agents_setup(root)["parches"], [patch])

    def test_parches_sin_ninguna_linea_en_agents(self):
        patch, _ = self.in_patch()
        write(self.root / "AGENTS.md", (FIXTURES / "sin-setup" / "AGENTS.md").read_text(encoding="utf-8"))
        case = perf.setup_case(self.root)  # AGENTS.md perdió la sección: hay un parche y nadie dice si vale
        self.assertEqual((case["caso"], case["candidatos"]), ("duda", [patch]))
        out = self.good("setup", "--estado")
        self.assertIn("AGENTS.md no dice nada del setup", out)
        self.assertIn("setup --vigente", out)
        error = self.bad("setup", "--vigente", patch)  # sin sección de rendimiento no hay dónde anotarlo: se detiene
        self.assertIn("no hay dónde anotar el parche vigente: AGENTS.md no tiene una sección de rendimiento", error)
        self.assertEqual(json.loads((patch.parent / (patch.name + ".json")).read_text(encoding="utf-8"))["estado"], "vigente")

    def test_dos_parches_sin_vigente(self):
        patch, _ = self.in_patch()
        other = self.patches / "perf-setup-0.13.0-20990101-0900.patch"
        shutil.copyfile(str(patch), str(other))
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", "- Setup listo, en parche: `git apply "
                                                      "<ruta>/perf-setup.patch` antes de medir\n"))
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], len(case["candidatos"])), ("duda", 2))
        out = self.good("setup", "--estado")
        self.assertIn("hay 2 parches de setup sin uno vigente", out)
        self.assertEqual(len([command for command in pasteable(out)[0] if "setup --vigente" in command]), 2)
        before = self.tree()
        self.assertIn("falta decir cuál es el vigente", self.bad("setup", "--reponer"))
        self.assertEqual(self.tree(), before)
        self.good("setup", "--vigente", patch)
        self.assertEqual(json.loads((other.parent / (other.name + ".json")).read_text(encoding="utf-8"))["estado"],
                         "reemplazado")
        self.assertTrue(other.is_file())  # el viejo no se borra


class SetupSaveTest(SetupBase):
    """A2: guardar el setup como parche, con su ficha."""

    def test_guarda_solo_el_setup_con_su_ficha(self):
        self.instrument()
        write(self.root / "docs" / "notas.md", "trabajo mío\n")
        write(self.root / "settings.gradle.kts", 'include(":app")\n// otro cambio mío\n')
        out = self.good("setup", "--guardar", *WIRING)
        patch, ficha = self.saved()
        self.assertTrue(PATCH_NAME.fullmatch(patch.name), patch.name)
        self.assertEqual(patch.parent, self.patches)
        self.assertEqual(ficha["remoto"], REMOTE)
        self.assertEqual(ficha["applicationId"], PKG)
        self.assertEqual(ficha["skill"], perf.VERSION)
        self.assertEqual(ficha["commit_base"], git(self.root, "rev-parse", "HEAD").strip())
        self.assertEqual(ficha["sha256"], perf.sha256_of(patch))
        self.assertIn(HOOKS, ficha["archivos"])
        self.assertIn("app/build.gradle.kts", ficha["archivos"])
        self.assertIn("app/src/main/kotlin/com/example/app/red/Red.kt", ficha["archivos"])
        self.assertNotIn("docs/notas.md", ficha["archivos"])
        self.assertNotIn("settings.gradle.kts", ficha["archivos"])
        self.assertNotIn("AGENTS.md", ficha["archivos"])  # ahí se anota el caso: no es parte del setup
        self.assertIn("No entran en el parche del setup (no son del setup; se quedan como están): docs/notas.md, "
                      "settings.gradle.kts", out)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("- Setup: en parche `reports/performance/setup/parches/%s`" % patch.name, agents)
        self.assertLess(agents.index("<!-- hb-performance:estado -->"), agents.index("- Setup: en parche"))
        self.assertLess(agents.index("- Setup: en parche"), agents.index("<!-- /hb-performance:estado -->"))
        self.assertIn("## DoD\n\n1. `true`", agents)  # nada fuera del bloque cambia
        self.assertEqual(git(self.root, "apply", "--check", "-R", str(patch)), "")
        self.assertIn("/reports/performance/setup/parches/", (self.root / ".git" / "info" / "exclude").read_text())
        self.assertIn("sigue puesto en el árbol", out)
        self.assertTrue((self.root / HOOKS).is_file())

    def test_no_pisa_y_reemplaza_el_anterior(self):
        self.instrument()
        self.good("setup", "--guardar", *WIRING)
        first, _ = self.saved()
        data = first.read_bytes()
        # 0.15.0 · A2: con el mismo contenido nunca dice "guardado": dice qué hizo
        self.assertIn("Ya estaba guardado en", self.good("setup", "--guardar", *WIRING))
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)
        mark = self.root / "app" / "src" / "perf" / "kotlin" / "com" / "example" / "app" / "perf" / "MarkTrace.kt"
        write(mark, mark.read_text(encoding="utf-8") + "// actualizado\n")
        out = self.good("setup", "--guardar")
        second, _ = self.saved()
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), data)  # el viejo sigue intacto
        old = json.loads((first.parent / (first.name + ".json")).read_text(encoding="utf-8"))
        self.assertEqual((old["estado"], old["reemplazado_por"]), ("reemplazado", second.name))
        self.assertIn("Reemplazado (queda guardado, ya no se usa", out)
        self.assertIn(b"// actualizado", second.read_bytes())

    def test_un_archivo_con_cambios_que_no_son_del_setup_detiene(self):
        self.instrument()
        client = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt"
        write(client, WIRED_CLIENT.replace('fun version() = "1"', 'fun version() = "2"'))  # otro hunk, lejos del gancho
        error = self.bad("setup", "--guardar", "--quitar", *WIRING)
        self.assertIn("no guardé nada", error)
        self.assertIn("app/src/main/kotlin/com/example/app/red/Red.kt (por ejemplo: fun version() = \"1\")", error)
        self.assertIn("haz primero el commit de ese trabajo", error)
        commands = pasteable(error)[0]  # un solo --archivos con todos: repetir la opción dejaría solo los últimos
        self.assertTrue(commands[0].endswith("setup --guardar --quitar --archivos app/build.gradle.kts %s" % RED), commands)
        self.assertTrue(commands[1].endswith("setup --guardar --quitar --archivos app/build.gradle.kts"), commands)
        self.assertFalse(self.patches.exists())
        self.assertTrue((self.root / HOOKS).is_file())  # --quitar no llegó a correr
        self.assertNotIn("Setup: en parche", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.good("setup", "--guardar", "--archivos", "app/build.gradle.kts", RED)
        self.assertIn(b'fun version() = "2"', self.saved()[0].read_bytes())

    def test_el_trabajo_del_usuario_no_viaja_en_el_parche(self):
        self.instrument()
        # un archivo nuevo del usuario que llama a una API estándar de Android: no es del setup
        screen = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "nuevo" / "PantallaNueva.kt"
        write(screen, "class PantallaNueva {\n    fun listo() { reportFullyDrawn() }\n    val etiqueta = \"perf\"\n}\n")
        out = self.good("setup", "--guardar", "--quitar", *WIRING)
        self.assertTrue(screen.is_file())
        self.assertIn("No entran en el parche del setup", out)
        self.assertNotIn("PantallaNueva", "\n".join(self.saved()[1]["archivos"]))
        # un cambio del usuario pegado al gancho de red (mismo hunk): se detiene, no se lo lleva
        self.good("setup", "--reponer")
        client = self.root / RED
        changed = WIRED_CLIENT.replace("builder.retryOnConnectionFailure(true)", "builder.retryOnConnectionFailure(false)")
        write(client, changed)
        mark = self.root / "app" / "src" / "perf" / "kotlin" / "com" / "example" / "app" / "perf" / "MarkTrace.kt"
        write(mark, mark.read_text(encoding="utf-8") + "// plantilla nueva\n")  # hay setup nuevo que guardar
        before = self.tree()
        error = self.bad("setup", "--guardar")
        self.assertIn("no guardé nada", error)
        self.assertIn("%s (por ejemplo: builder.retryOnConnectionFailure(true))" % RED, error)
        self.assertEqual(self.tree(), before)
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)

    def test_un_archivo_del_parche_con_una_marca_de_una_investigacion(self):
        patch, _ = self.in_patch()
        self.good("setup", "--reponer")
        write(self.root / RED, WIRED_CLIENT.replace("    fun uno() = 1\n", "    fun uno() = 1.also { PerfHooks.mark(\"x\") }\n"))
        self.investigation(rows="| `%s` | . | marca pago_inicio | — | no |\n" % RED)
        mark = self.root / "app" / "src" / "perf" / "kotlin" / "com" / "example" / "app" / "perf" / "MarkTrace.kt"
        write(mark, mark.read_text(encoding="utf-8") + "// plantilla nueva\n")
        error = self.bad("setup", "--guardar")  # no arma un parche sin el gancho de red, ni se lleva la marca
        self.assertIn("declara ahí un cambio temporal: ciérrala primero", error)
        self.assertEqual(self.saved()[0], patch)  # el parche completo sigue siendo el vigente
        self.assertIn(RED, self.saved()[1]["archivos"])

    def test_rutas_con_espacios_y_sin_cambios(self):
        self.instrument()
        agents = AGENTS.replace("- setup listo\n", "- Carpeta de parches: `../parches de medición`\n- setup listo\n")
        write(self.root / "AGENTS.md", agents)
        error = self.bad("setup", "--guardar", "--archivos", "app/build.gradle.kts", "no/existe.kt", "settings.gradle.kts")
        self.assertIn("--archivos nombra no/existe.kt, settings.gradle.kts que no tienen cambios sin commitear", error)
        self.good("setup", "--guardar", "--quitar", *WIRING)
        folder = self.dir / "parches de medición"
        patch = next(folder.glob("perf-setup-*.patch"))
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("- Setup: en parche `../parches de medición/%s`" % patch.name, text)
        case = perf.setup_case(self.root)  # perf.py lee su propia línea aunque la ruta tenga espacios
        self.assertEqual((case["caso"], case["presente"], case["parche"]), ("parche", False, patch))
        self.good("setup", "--reponer")
        self.assertTrue((self.root / HOOKS).is_file())

    def test_el_remoto_se_guarda_sin_credenciales(self):
        git(self.root, "remote", "set-url", "origin", "https://usuario:tok_SECRETO123@example.com/equipo/app.git")
        self.instrument()
        out = self.good("setup", "--guardar", *WIRING)
        ficha = self.saved()[1]
        self.assertEqual(ficha["remoto"], "https://example.com/equipo/app.git")
        self.assertNotIn("SECRETO", out + json.dumps(ficha) + self.good("setup", "--estado"))
        for same in ("git@example.com:equipo/app.git", "ssh://git@example.com:22/equipo/app.git",
                     "https://example.com:8443/equipo/app", "example.com:equipo/app.git", "HTTPS://Example.com/Equipo/App/"):
            self.assertTrue(perf.same_remote(ficha["remoto"], same), same)
        for other in ("git@example.com:equipo/otra.git", "git@otro.example.com:equipo/app.git"):
            self.assertFalse(perf.same_remote(ficha["remoto"], other), other)

    def test_nombres_con_caracteres_no_ascii(self):
        write(self.root / "app" / "di" / "Inyección.kt", "object Inyección { val medir = false }\n")
        commit_all(self.root, "di")
        self.instrument()
        write(self.root / "app" / "di" / "Inyección.kt", "object Inyección { val medir = true }\n")
        self.good("setup", "--guardar", "--archivos", "app/build.gradle.kts", "app/di/Inyección.kt")
        self.assertIn("app/di/Inyección.kt", self.saved()[1]["archivos"])
        out = self.good("setup", "--quitar")
        self.assertNotIn("lo guardo antes de quitar", out)  # el setup es el del parche: lo reconoce por su nombre
        write(self.root / "app" / "di" / "Inyección.kt", "object Inyección { val medir = false } // mío\n")
        self.assertIn("app/di/Inyección.kt", self.bad("setup", "--reponer"))  # y ve el cambio del usuario encima

    def test_los_cambios_temporales_de_una_investigacion_no_entran(self):
        self.instrument()
        screen = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "Pagos.kt"
        write(screen, "class Pagos {\n    fun ver() { PerfHooks.mark(\"pago_visible\") }\n}\n")
        self.investigation(rows="| `app/src/main/kotlin/com/example/app/Pagos.kt` | . | marca pago_visible | — | no |\n")
        out = self.good("setup", "--guardar", *WIRING)
        self.assertIn("No entra en el parche del setup: app/src/main/kotlin/com/example/app/Pagos.kt (cambio temporal de la "
                      "investigación reports/perf/pagos/2099-01-01", out)
        self.assertNotIn("Pagos.kt", "\n".join(self.saved()[1]["archivos"]))

    def test_guardar_y_quitar(self):
        self.instrument()
        before = self.tree()
        out = self.good("setup", "--guardar", "--quitar", *WIRING)
        self.assertIn("Respaldo de todo el diff", out)
        self.assertIn("No quedó ningún archivo del setup en el árbol", out)
        self.assertIn("Setup quitado y guardado en su parche: %s" % perf.NO_STEPS_LEFT, out)
        self.assertEqual(self.status(), [])
        self.assertFalse((self.root / HOOKS).exists())
        self.assertFalse((self.root / "app" / "src" / "perf").exists())
        backup = list((self.patches / "respaldos").glob("perf-setup-respaldo-*.patch"))
        self.assertEqual(len(backup), 1)
        self.assertIn(b"PerfHooks", backup[0].read_bytes())
        self.assertIn("instrumentación en el repo: no (está en el parche", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.good("setup", "--reponer")
        self.assertEqual(self.tree(), before)  # vuelve exactamente lo que había

    def test_el_mismo_setup_deja_la_ficha_al_dia(self):
        patch, ficha = self.in_patch()
        path = patch.parent / (patch.name + ".json")
        write(path, json.dumps(dict(ficha, skill="0.13.0")))
        out = self.good("setup", "--reponer")
        self.assertIn("El parche del setup es de hb-performance 0.13.0 y esta es la %s" % perf.VERSION, out)
        out = self.good("setup", "--guardar")  # `instrumentar --actualizar` no cambió nada: no hace falta otro parche
        self.assertIn("le completé la ficha: la versión de la skill", out)  # 0.15.0 · A2
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["skill"], perf.VERSION)
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)
        self.assertNotIn("conviene actualizar", self.good("setup", "--estado"))

    def test_sin_el_setup_en_el_arbol_no_se_guarda_un_parche_parcial(self):
        patch, _ = self.in_patch()
        screen = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "Pagos.kt"
        write(screen, "class Pagos {\n    fun ver() { PerfHooks.mark(\"pago_visible\") }\n}\n")  # una marca suelta
        out = self.good("setup", "--guardar")
        self.assertIn("No hay nada que guardar: el setup no está en el árbol", out)
        self.assertIn("Hay cambios sueltos con aspecto de setup que no guardé (app/src/main/kotlin/com/example/app/Pagos.kt)",
                      out)
        self.assertEqual(self.saved()[0], patch)  # el parche completo sigue siendo el vigente
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", ""))
        for path in list(self.patches.glob("perf-setup-*")):
            path.unlink()
        error = self.bad("setup", "--guardar")  # sin parche ni PerfHooks.kt: no arma uno con lo suelto
        self.assertIn("no hay un setup que guardar: no encuentro PerfHooks.kt en el árbol", error)
        self.assertFalse(list(self.patches.glob("perf-setup-*.patch")))

    def test_simular_no_toca_nada(self):
        self.instrument()
        before = self.tree()
        out = self.good("setup", "--guardar", "--simular", *WIRING)
        self.assertIn("Simulación: guardaría", out)
        self.assertFalse(self.patches.exists())
        self.assertEqual(self.tree(), before)
        self.assertNotIn("Setup: en parche", (self.root / "AGENTS.md").read_text(encoding="utf-8"))


class SetupRestoreTest(SetupBase):
    """A3: reponer el setup correcto, o detenerse sin tocar nada."""

    def test_ficha_con_otro_remoto(self):
        shutil.copytree(str(FIXTURES / "otro-repo" / "herramientas"), str(self.root / "herramientas"))
        write(self.root / "AGENTS.md", (FIXTURES / "otro-repo" / "AGENTS.md").read_text(encoding="utf-8"))
        before = self.tree()
        error = self.bad("setup", "--reponer")
        self.assertIn("el parche es de otro repo: git@example.com:otro-equipo/otra-app.git (este repo es %s)" % REMOTE, error)
        self.assertIn("No lo aplico", error)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.status(), ["?? herramientas/"])

    def test_el_mismo_repo_por_https(self):
        patch, _ = self.in_patch()
        git(self.root, "remote", "set-url", "origin", "https://example.com/equipo/app")
        self.good("setup", "--reponer")
        self.assertTrue((self.root / HOOKS).is_file())

    def test_hash_app_y_raiz_que_no_coinciden(self):
        patch, ficha = self.in_patch()
        path = patch.parent / (patch.name + ".json")
        before = self.tree()
        write(path, json.dumps(dict(ficha, sha256="0" * 64)))
        self.assertIn("cambió desde que se guardó (su SHA-256 no es el de la ficha)", self.bad("setup", "--reponer"))
        write(path, json.dumps(dict(ficha, applicationId="com.example.otra")))
        self.assertIn("el parche es de otra app: su ficha dice el applicationId com.example.otra y este proyecto mide %s" % PKG,
                      self.bad("setup", "--reponer"))
        write(path, json.dumps(dict(ficha, remoto="sin remoto", raiz="otro-proyecto")))
        self.assertIn("el parche es de otro proyecto: su ficha dice la raíz 'otro-proyecto' y esta es 'proyecto'",
                      self.bad("setup", "--reponer"))
        git(self.root, "remote", "remove", "origin")
        write(path, json.dumps(ficha))
        self.assertIn("es de un repo con remoto (%s) y este repo no tiene remoto" % REMOTE, self.bad("setup", "--reponer"))
        self.assertEqual(self.tree(), before)
        write(path, json.dumps(dict(ficha, remoto="sin remoto")))  # sin remoto: valen la raíz y el applicationId
        self.good("setup", "--reponer")
        self.assertTrue((self.root / HOOKS).is_file())

    def test_cambios_del_usuario_en_los_archivos_del_parche(self):
        self.in_patch()
        write(self.root / "app" / "build.gradle.kts", BUILD + "// trabajo mío sin commitear\n")
        before = self.tree()
        error = self.bad("setup", "--reponer")
        self.assertIn("hay cambios tuyos sin commitear en archivos que el parche del setup toca:\n  - app/build.gradle.kts",
                      error)
        self.assertIn("No apliqué nada", error)
        self.assertEqual(self.tree(), before)

    def test_tres_vias_solo_sin_conflictos(self):
        self.in_patch()
        client = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt"
        # el proyecto cambió cerca del gancho (dentro del contexto del parche), sin tocar la misma línea
        write(client, CLIENT.replace("builder.followRedirects(true)", "builder.followRedirects(false)"))
        commit_all(self.root, "cambio del equipo")
        out = self.good("setup", "--reponer")
        self.assertIn("lo apliqué con --3way, sin conflictos", out)
        text = client.read_text(encoding="utf-8")
        self.assertIn("PerfHooks.okHttp(builder)", text)
        self.assertIn("builder.followRedirects(false)", text)
        self.assertNotIn("<<<<<<<", text)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")  # el índice del usuario no se toca

    def test_tres_vias_con_conflicto_se_detiene(self):
        self.in_patch()
        client = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt"
        write(client, CLIENT.replace("        val builder = OkHttpClient.Builder()\n",
                                     "        val builder = OkHttpClient.Builder().cache(null)\n        builder.pingInterval(1)\n"))
        commit_all(self.root, "cambio del equipo en la misma línea")
        before = self.tree()
        error = self.bad("setup", "--reponer")
        self.assertIn("probado con --3way, tiene conflictos", error)
        self.assertIn("No apliqué nada", error)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.status(), [])

    def test_parche_sin_ficha_de_una_version_anterior(self):
        shutil.copytree(str(FIXTURES / "linea-vieja" / "herramientas"), str(self.root / "herramientas"))
        write(self.root / "AGENTS.md", (FIXTURES / "linea-vieja" / "AGENTS.md").read_text(encoding="utf-8"))
        patch = self.root / "herramientas" / "perf-setup.patch"
        out = self.good("setup", "--reponer")
        self.assertIn("El parche no tenía ficha completa (es de una versión anterior)", out)
        self.assertTrue((self.root / HOOKS).is_file())
        ficha = json.loads((patch.parent / "perf-setup.patch.json").read_text(encoding="utf-8"))
        self.assertEqual((ficha["remoto"], ficha["applicationId"], ficha["skill"], ficha["sha256"]),
                         (REMOTE, PKG, None, perf.sha256_of(patch)))
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("- Setup: en parche `herramientas/perf-setup.patch`", agents)  # desde ahora manda el bloque
        # 0.15.0 · A4: la línea vieja la quita perf.py, con un respaldo de AGENTS.md antes
        self.assertIn("quité la línea de una versión anterior", out)
        self.assertNotIn("git apply herramientas/perf-setup.patch", agents)
        # la skill es más nueva que el parche: lo que sigue es actualizar, humo y guardar
        commands = pasteable(out)[0]
        self.assertIn("instrumentar --modulo app --paquete %s.perf --actualizar" % PKG, commands[0])
        self.assertIn("humo --paquete %s" % PKG, commands[1])
        self.assertTrue(commands[2].endswith("setup --guardar"))

    def test_parche_sin_ficha_con_archivos_ajenos_no_se_usa(self):
        self.instrument()
        write(self.root / "docs" / "ajeno.md", "no es del setup\n")
        git(self.root, "add", "-N", ".")
        legacy = self.root.parent / "viejo" / "perf-setup.patch"
        write(legacy, git(self.root, "diff", "--binary"))
        git(self.root, "reset", "-q")
        git(self.root, "apply", "-R", str(legacy))
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", "- Setup listo, en parche: `git apply %s` antes "
                                                      "de medir\n" % legacy))
        before = self.tree()
        error = self.bad("setup", "--reponer")
        # 0.15.0 · A1: el rechazo da el comando exacto con los archivos que no reconoció
        self.assertIn("es de una versión anterior (sin ficha) y toca archivos que no reconozco como del setup: "
                      "docs/ajeno.md", error)
        self.assertIn("setup --reponer --archivos docs/ajeno.md", error)
        self.assertEqual(self.tree(), before)
        self.assertFalse((legacy.parent / "perf-setup.patch.json").exists())

    def test_una_ficha_ilegible_o_incompleta_no_baja_la_comprobacion(self):
        patch, ficha = self.in_patch()
        path = patch.parent / (patch.name + ".json")
        before = self.tree()
        write(path, "{ esto no es json")
        self.assertIn("existe pero no se puede leer", self.bad("setup", "--reponer"))
        self.assertEqual(self.tree(), before)
        # sin los campos que se comparan vale la regla de los parches sin ficha: se completa con lo que se encuentra
        write(path, json.dumps({"parche": patch.name, "estado": "vigente"}))
        self.assertIn("no tenía ficha completa", self.good("setup", "--reponer"))
        completed = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((completed["sha256"], completed["remoto"]), (perf.sha256_of(patch), REMOTE))

    def test_parche_sin_ficha_con_ajenos_que_nombran_debug(self):
        self.instrument()
        write(self.root / "docs" / "ajeno.md", "notas del modo debug del servidor\n")
        write(self.root / "app" / "src" / "debug" / "kotlin" / "Herramienta.kt", "object Herramienta\n")
        git(self.root, "add", "-N", ".")
        legacy = self.root.parent / "viejo" / "perf-setup.patch"
        write(legacy, git(self.root, "diff", "--binary"))
        git(self.root, "reset", "-q")
        git(self.root, "apply", "-R", str(legacy))
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", "- Setup listo, en parche: `git apply %s` antes "
                                                      "de medir\n" % legacy))
        error = self.bad("setup", "--reponer")
        self.assertIn("docs/ajeno.md", error)
        self.assertIn("app/src/debug/kotlin/Herramienta.kt", error)
        self.assertFalse((self.root / HOOKS).exists())

    def test_no_actualizar_a_mitad_de_una_investigacion_medida(self):
        patch, ficha = self.in_patch()
        write(patch.parent / (patch.name + ".json"), json.dumps(dict(ficha, skill="0.13.0")))
        folder = self.investigation()
        write(folder / "fases.json", json.dumps({"antes": {"fecha": "2020-01-01T10:00:00", "corridas": 10}}))
        for extra in ((), ("--carpeta", folder.relative_to(self.root))):
            with self.subTest(carpeta=bool(extra)):
                out = self.good("setup", "--reponer", *extra) if extra else self.good("setup", "--reponer", "--simular")
        out = self.good("setup", "--estado")  # también sin --carpeta: mira las investigaciones abiertas del proyecto
        self.assertIn("No lo actualices ahora: hay una investigación que ya midió", out)
        self.assertRegex(out, r"- reports/perf/pagos/2099-01-01: abierta; su última medición fue hace \d+ días \(2020-01-01\)")
        self.assertNotIn("--actualizar", "\n".join(pasteable(out)[0]))

    def test_ya_puesto_y_simular(self):
        self.in_patch()
        before = self.tree()
        self.assertIn("Simulación: repondría el setup", self.good("setup", "--reponer", "--simular"))
        self.assertEqual(self.tree(), before)
        self.good("setup", "--reponer")
        self.assertIn("El setup ya está en el árbol", self.good("setup", "--reponer"))


class SetupRemoveCase(SetupBase):
    """A4: quitar el setup, solo o como último paso de `cerrar`."""


class SetupRemoveTest(SetupRemoveCase):
    """0.16.0 · K: la primera mitad de los tests, para que la suite se reparta (la otra mitad está en SetupRemoveMoreTest)."""

    def test_tras_actualizar_guarda_antes_de_quitar(self):
        first, _ = self.in_patch()
        self.good("setup", "--reponer")
        mark = self.root / "app" / "src" / "perf" / "kotlin" / "com" / "example" / "app" / "perf" / "MarkTrace.kt"
        write(mark, mark.read_text(encoding="utf-8") + "// plantilla nueva\n")  # como `instrumentar --actualizar`
        new_file = mark.parent / "Nuevo.kt"
        write(new_file, "// Generated by hb-performance\npackage com.example.app.perf\n")
        out = self.good("setup", "--quitar")
        self.assertIn("El setup del árbol no es igual al del parche vigente (%s): lo guardo antes de quitar" % first.name, out)
        second, ficha = self.saved()
        self.assertNotEqual(first, second)
        self.assertIn("app/src/perf/kotlin/com/example/app/perf/Nuevo.kt", ficha["archivos"])
        self.assertEqual(self.status(), [])
        self.good("setup", "--reponer")
        self.assertIn("// plantilla nueva", mark.read_text(encoding="utf-8"))  # el setup actualizado no se perdió
        self.assertTrue(new_file.is_file())

    def test_una_mejora_en_el_mismo_archivo_se_queda(self):
        patch, _ = self.in_patch()
        self.good("setup", "--reponer")
        client = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt"
        improved = WIRED_CLIENT.replace('fun version() = "1"', 'fun version() = "2" // mejora del usuario, sin commitear')
        write(client, improved)
        out = self.good("setup", "--quitar")
        self.assertNotIn("lo guardo antes de quitar", out)  # el setup es el del parche: no hace falta otro
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)
        self.assertEqual(client.read_text(encoding="utf-8"), CLIENT.replace(
            'fun version() = "1"', 'fun version() = "2" // mejora del usuario, sin commitear'))  # sin el gancho, con la mejora
        self.assertIn("No quedó ningún archivo del setup en el árbol", out)
        backups = [path.read_bytes() for path in (self.patches / "respaldos").glob("*.patch")]  # el de antes y este
        self.assertTrue(any(b"mejora del usuario" in data for data in backups))

    def test_setup_nuevo_mezclado_con_cambios_del_usuario_detiene(self):
        self.in_patch()
        self.good("setup", "--reponer")
        client = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt"
        write(client, WIRED_CLIENT.replace("    fun uno() = 1\n", "    fun uno() = 1\n    fun marca() = PerfHooks.mark(\"x\")\n")
              .replace('fun version() = "1"', 'fun version() = "2"'))
        before = self.tree()
        error = self.bad("setup", "--quitar")  # hay setup nuevo que guardar, y no se puede separar de lo del usuario
        self.assertIn("no guardé nada", error)
        self.assertEqual(self.tree(), before)

    def test_una_mejora_pegada_al_gancho_detiene_sin_llevarsela(self):
        self.in_patch()
        self.good("setup", "--reponer")
        client = self.root / RED
        write(client, WIRED_CLIENT.replace("builder.retryOnConnectionFailure(true)",
                                           "builder.retryOnConnectionFailure(false) // MEJORA"))
        folder = self.investigation(closed=True)
        before = self.tree()
        for command in (("setup", "--quitar"), ("cerrar", "--carpeta", folder.relative_to(self.root))):
            with self.subTest(comando=command[0]):
                error = self.bad(*command)
                self.assertIn("no guardé nada", error)
                self.assertEqual(self.tree(), before)  # la mejora y el setup siguen en el árbol
                self.assertNotIn("cerrar --carpeta reports/perf/pagos/2099-01-01 --archivos", error)  # comando pegable
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)

    def test_una_marca_en_un_archivo_del_setup_se_quita_sin_tocar_el_cableado(self):
        self.in_patch()
        self.good("setup", "--reponer")
        client = self.root / RED
        marked = WIRED_CLIENT.replace('    fun version() = "1"\n', '    fun version() = "1"\n'
                                      '    fun marca() = android.os.Trace.beginSection("MARK x")\n')
        write(client, marked)
        folder = self.investigation(rows="| `%s` | . | marca temporal | — | no |\n" % RED, closed=True)
        rel = folder.relative_to(self.root)
        out = self.good("cerrar", "--carpeta", rel)
        self.assertIn("%s: solo lo temporal (el cableado del setup se queda hasta el paso del setup)" % RED, out)
        self.assertEqual(client.read_text(encoding="utf-8"), WIRED_CLIENT)  # sin la marca, con el gancho
        self.assertTrue((self.root / HOOKS).is_file())  # el setup espera al DoD
        self.good("cerrar", "--carpeta", rel, "--dod")
        self.assertEqual(client.read_text(encoding="utf-8"), CLIENT)
        self.assertEqual(self.status(), [])
        self.assertEqual(len(list(self.patches.glob("perf-setup-*.patch"))), 1)  # la marca no entró al parche del setup

    def test_una_marca_pegada_al_cableado_detiene(self):
        self.in_patch()
        self.good("setup", "--reponer")
        client = self.root / RED
        write(client, WIRED_CLIENT.replace("        PerfHooks.okHttp(builder)\n", "        PerfHooks.okHttp(builder)\n"
                                           "        android.os.Trace.beginSection(\"MARK x\")\n"))
        folder = self.investigation(rows="| `%s` | . | marca temporal | — | no |\n" % RED, closed=True)
        before = self.tree()
        error = self.bad("cerrar", "--carpeta", folder.relative_to(self.root))
        self.assertIn("pegado al cableado del setup (mismo hunk)", error)
        self.assertEqual(self.tree(), before)

    def test_filas_de_setup_de_0130_guardan_el_setup_entero(self):
        # 0.13.0 anotaba el cableado como filas "setup"; los archivos generados están sin commitear y sin parche
        self.instrument()
        folder = self.investigation(rows="| `%s` | . | cableado del setup | — | no |\n"
                                         "| `app/build.gradle.kts` | . | setup: build type | — | no |\n" % RED, closed=True)
        rel = folder.relative_to(self.root)
        with_setup = self.tree()
        out = self.good("cerrar", "--carpeta", rel)
        self.assertIn("Setup guardado como parche", out)
        patch, ficha = self.saved()
        for name in (HOOKS, RED, "app/build.gradle.kts", "app/src/profiling/AndroidManifest.xml"):
            self.assertIn(name, ficha["archivos"])  # un solo parche con todo: los generados y el cableado
        self.assertEqual(self.status(), [])
        self.assertTrue(all(row["revertido"] for row in perf.temp_changes((folder / "estado.md").read_text(encoding="utf-8"))))
        self.good("setup", "--reponer")
        self.assertEqual(self.tree(), with_setup)

    def test_una_fila_de_setup_con_una_mejora_no_va_entera_al_parche(self):
        # el archivo del cableado también lleva una mejora aplicada: como en 0.13.0, no se da entero por setup
        self.instrument()
        client = self.root / RED
        write(client, WIRED_CLIENT.replace('fun version() = "1"', 'fun version() = "2" // MEJORA M1'))
        folder = self.investigation(rows="| `%s` | . | cableado del setup | — | no |\n" % RED, closed=True, plan={
            "paquete": PKG, "principales": ["pago_ms"], "instalar": "./gradlew :app:installProfiling",
            "flujos": {"pagos": {"recorrido": "true"}},
            "mejoras": [{"id": "M1", "titulo": "Otra versión", "estado": "aplicada", "metrica": "pago_ms",
                         "cambios": [{"archivos": [RED]}]}]})
        before = self.tree()
        result = self.run_perf("cerrar", "--carpeta", folder.relative_to(self.root))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("también tiene código de M1", result.stderr)
        self.assertEqual(self.tree(), before)
        self.assertFalse(self.patches.exists())  # ningún parche de setup con la mejora dentro

    def test_una_fila_de_setup_que_el_parche_no_trae_entra_al_setup(self):
        self.instrument()
        write(self.root / RED, CLIENT)  # el setup se guardó sin el gancho de red
        self.good("setup", "--guardar", "--quitar", *WIRING)
        self.good("setup", "--reponer")
        write(self.root / "app" / "Config.kt", "object Config { val medir = true }\n")  # cableado nuevo, sin tokens
        folder = self.investigation(rows="| `app/Config.kt` | . | cableado del setup | — | no |\n", closed=True)
        out = self.good("cerrar", "--carpeta", folder.relative_to(self.root))
        self.assertIn("lo guardo antes de quitar", out)
        self.assertIn("app/Config.kt", self.saved()[1]["archivos"])
        self.assertEqual(self.status(), [])
        self.good("setup", "--reponer")
        self.assertTrue((self.root / "app" / "Config.kt").is_file())  # vuelve con el setup

    def test_el_setup_versionado_no_pasa_a_parche_con_archivos(self):
        self.instrument()
        git(self.root, "add", "app/src")
        git(self.root, "commit", "-q", "-m", "build(perf): instrumentación")
        out = self.good("setup", "--guardar", "--quitar", *WIRING)
        self.assertIn("El cableado sin commitear de app/build.gradle.kts es parte de ese setup: va en su commit", out)
        self.assertEqual(perf.setup_case(self.root)["caso"], "versionado")
        self.assertEqual((self.root / "app" / "build.gradle.kts").read_text(encoding="utf-8"), WIRED_BUILD)
        self.assertFalse(self.patches.exists())

    def test_el_setup_versionado_con_cableado_en_filas_sigue_versionado(self):
        self.instrument()
        git(self.root, "add", "app/src")  # los generados están en git; el cableado de build.gradle queda sin commitear
        git(self.root, "commit", "-q", "-m", "build(perf): instrumentación")
        folder = self.investigation(rows="| `app/build.gradle.kts` | . | setup: build type | — | no |\n", closed=True)
        out = self.good("cerrar", "--carpeta", folder.relative_to(self.root))
        self.assertIn("Quita (cambios temporales): app/build.gradle.kts", out)
        self.assertEqual(perf.setup_case(self.root)["caso"], "versionado")  # no pasa a "en parche"
        self.assertNotIn("Setup: en parche", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "app" / "build.gradle.kts").read_text(encoding="utf-8"), BUILD)


class SetupRemoveMoreTest(SetupRemoveCase):
    """0.16.0 · K: la segunda mitad de los tests, para que la suite se reparta (la otra mitad está en SetupRemoveTest)."""

    def test_con_el_dod_fallido_no_se_quita(self):
        self.in_patch()
        self.good("setup", "--reponer")
        write(self.root / "AGENTS.md", (self.root / "AGENTS.md").read_text(encoding="utf-8").replace("1. `true`", "1. `false`"))
        folder = self.investigation(closed=True)
        rel = folder.relative_to(self.root)
        self.assertNotEqual(self.run_perf("cerrar", "--carpeta", rel, "--dod").returncode, 0)
        out = self.good("cerrar", "--carpeta", rel)
        self.assertIn("El setup se quita después del DoD", out)
        self.assertTrue((self.root / HOOKS).is_file())

    def test_sin_parche_y_sin_codigo_no_dice_que_quedo_guardado(self):
        out = self.good("setup", "--quitar")  # AGENTS.md dice "setup listo" y no hay código ni parche
        self.assertIn("no hay nada que quitar", out)
        self.assertNotIn("guardado en su parche", out)
        self.assertIn("sesión 0", out)

    def test_la_ficha_que_no_coincide_se_rehace_antes_de_quitar(self):
        patch, ficha = self.in_patch()
        self.good("setup", "--reponer")
        write(patch.parent / (patch.name + ".json"), json.dumps(dict(ficha, sha256="0" * 64)))
        out = self.good("setup", "--quitar")
        self.assertIn("lo guardo antes de quitar", out)
        self.good("setup", "--reponer")  # lo que quitó, lo puede reponer
        self.assertTrue((self.root / HOOKS).is_file())

    def test_guardar_quitar_simular(self):
        self.instrument()
        before = self.tree()
        out = self.good("setup", "--guardar", "--quitar", "--simular", *WIRING)
        self.assertIn("Simulación: después lo quitaría del árbol con ese parche", out)
        self.assertTrue(pasteable(out)[0][-1].endswith("setup --guardar --quitar --archivos app/build.gradle.kts"))
        self.assertEqual(self.tree(), before)

    def test_archivos_en_el_indice_detienen(self):
        self.in_patch()
        self.good("setup", "--reponer")
        git(self.root, "add", HOOKS)
        before = self.tree()
        error = self.bad("setup", "--quitar")
        self.assertIn("hay archivos del setup en el índice de git (git add): %s" % HOOKS, error)
        self.assertIn("git reset -q -- %s" % HOOKS, error)
        self.assertEqual(self.tree(), before)

    def test_cerrar_quita_el_setup_al_final(self):
        self.in_patch()
        self.good("setup", "--reponer")
        folder = self.investigation(closed=True)
        rel = folder.relative_to(self.root)
        out = self.good("siguiente", "--carpeta", rel)
        self.assertIn("investigación cerrada · falta quitar el setup", out)
        self.assertIn("setup --quitar --carpeta %s" % rel, out)
        self.assertNotIn(perf.NO_STEPS_LEFT, out)
        before = self.tree()
        out = self.good("cerrar", "--carpeta", rel, "--simular")
        self.assertIn("Simulación: al final, después del DoD, quitaría el setup de medición con su parche", out)
        self.assertEqual(self.tree(), before)
        out = self.good("cerrar", "--carpeta", rel)
        self.assertIn("Setup quitado con su parche", out)
        self.assertFalse((self.root / HOOKS).exists())
        self.assertEqual(self.status(), [])
        self.assertEqual(json.loads((folder / "cierre-setup.json").read_text(encoding="utf-8"))["setup"], "quitado")
        self.assertFalse((folder / "cierre.json").exists())  # el cierre del setup no envejece los reportes
        self.assertIn("Investigación cerrada: %s" % perf.NO_STEPS_LEFT, out)
        self.assertIn("El setup quedó quitado y guardado en su parche", out)
        self.assertIn("Investigación cerrada: %s" % perf.NO_STEPS_LEFT, (folder / "estado.md").read_text(encoding="utf-8"))

    def test_el_orden_marcas_dod_setup(self):
        self.in_patch()
        self.good("setup", "--reponer")
        screen = self.root / "app" / "Pagos.kt"
        write(screen, "class Pagos\n")
        commit_all(self.root, "pantalla")
        write(screen, "class Pagos\n// TEMPORAL (hb-performance)\n")
        folder = self.investigation(rows="| `app/Pagos.kt` | . | marca temporal | — | no |\n", closed=True)
        rel = folder.relative_to(self.root)
        out = self.good("cerrar", "--carpeta", rel)
        self.assertEqual(screen.read_text(encoding="utf-8"), "class Pagos\n")  # primero, los cambios temporales
        self.assertIn("El setup se quita después del DoD", out)
        self.assertTrue((self.root / HOOKS).is_file())
        self.assertLess(out.index("Quita (cambios temporales): app/Pagos.kt"), out.index("El setup se quita después del DoD"))
        out = self.good("cerrar", "--carpeta", rel, "--dod")
        self.assertLess(out.index("✔ DoD en verde"), out.index("Setup quitado con su parche"))
        self.assertFalse((self.root / HOOKS).exists())
        self.assertIn("Investigación cerrada: %s" % perf.NO_STEPS_LEFT, out)

    def test_sin_setup_lo_deja_puesto(self):
        self.in_patch()
        self.good("setup", "--reponer")
        folder = self.investigation(closed=True)
        rel = folder.relative_to(self.root)
        out = self.good("cerrar", "--carpeta", rel, "--sin-setup")
        self.assertIn("El setup de medición queda puesto (--sin-setup)", out)
        self.assertTrue((self.root / HOOKS).is_file())
        self.assertIn("Investigación cerrada: %s" % perf.NO_STEPS_LEFT, out)
        self.assertIn("sigue puesto porque lo pediste (--sin-setup)", out)

    def test_versionado_no_se_quita(self):
        self.instrument()
        commit_all(self.root, "build(perf): setup")
        folder = self.investigation(closed=True)
        before = self.tree()
        out = self.good("cerrar", "--carpeta", folder.relative_to(self.root))
        self.assertIn("Setup versionado (en git): queda en el repo; `cerrar` no quita nada del setup", out)
        self.assertEqual(self.tree(), before)
        self.assertIn("Investigación cerrada: %s" % perf.NO_STEPS_LEFT, out)

    def test_otra_investigacion_abierta_lo_necesita(self):
        self.in_patch()
        self.good("setup", "--reponer")
        folder = self.investigation(closed=True)
        other = self.investigation(name="inicio")
        rel = folder.relative_to(self.root)
        out = self.good("cerrar", "--carpeta", rel)
        self.assertIn("No quité el setup: reports/perf/inicio/2099-01-01 sigue abierta y lo necesita", out)
        self.assertIn("cerrar --carpeta %s --sin-setup" % rel, out)
        self.assertTrue((self.root / HOOKS).is_file())
        self.assertIn("Otra investigación necesita el setup", out)
        out = self.good("setup", "--quitar", "--carpeta", rel)  # quitarlo igual es una decisión del usuario
        self.assertIn("Hay otra investigación abierta que necesita el setup: reports/perf/inicio/2099-01-01", out)
        self.assertFalse((self.root / HOOKS).exists())
        out = self.good("siguiente", "--carpeta", other.relative_to(self.root))  # la otra pide reponerlo primero
        self.assertIn("setup --reponer --carpeta reports/perf/inicio/2099-01-01", pasteable(out)[0][0])

    def test_una_fila_de_setup_de_una_investigacion_anterior(self):
        # 0.13.0 anotaba el cableado como cambio temporal "setup": su parche pasa a ser el vigente, con ficha
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", "- Instrumentación: PerfHooks\n"))
        commit_all(self.root, "agents")
        write(self.root / HOOKS, "// Generated by hb-performance\nobject PerfHooks\n")
        folder = self.investigation(rows="| `%s` | . | setup de medición | — | no |\n" % HOOKS, closed=True)
        out = self.good("cerrar", "--carpeta", folder.relative_to(self.root))
        self.assertIn("Del setup (no son cambios temporales; los guarda y los quita el paso del setup, al final)", out)
        self.assertIn("Setup guardado como parche", out)
        self.assertFalse((self.root / HOOKS).exists())
        case = perf.setup_case(self.root)
        self.assertEqual((case["caso"], case["presente"]), ("parche", False))
        self.assertEqual(case["ficha"]["remoto"], REMOTE)
        self.assertEqual(case["parche"].parent, self.patches)  # en la carpeta de parches del setup, con su nombre
        self.assertNotIn("git apply", (self.root / "AGENTS.md").read_text(encoding="utf-8"))  # nada que aplicar a mano


class SetupGateTest(SetupBase):
    """A5: `siguiente` y los controles previos, con el setup en un parche y fuera del árbol."""

    def test_siguiente_pone_reponer_primero(self):
        self.in_patch()
        folder = self.investigation()
        rel = folder.relative_to(self.root)
        out = self.good("siguiente", "--carpeta", rel)
        commands = pasteable(out)[0]
        self.assertTrue(commands[0].endswith("setup --reponer --carpeta %s" % rel), commands)
        self.assertIn(" capturar ", "\n".join(commands[1:]))
        state = (folder / "estado.md").read_text(encoding="utf-8")
        self.assertLess(state.index("setup --reponer"), state.index(" capturar "))  # también en "Siguiente paso"
        out = self.good("setup", "--reponer", "--carpeta", rel)
        self.assertIn("Setup repuesto con su parche", out)
        self.assertNotIn("setup --reponer", "\n".join(pasteable(out)[0]))  # ya está: sigue con lo de la investigación
        self.assertIn(" capturar ", "\n".join(pasteable(out)[0]))

    def test_capturar_se_detiene_antes_de_tocar_el_dispositivo(self):
        self.in_patch()
        folder = self.investigation()
        rel = folder.relative_to(self.root)
        error = self.bad("capturar", "--plan", rel / "plan.json", "--fase", "antes", code=perf.Precondicion.code)
        self.assertIn("el setup de medición no está en el árbol (setup en parche, sin reponer)", error)
        self.assertIn("No compilé ni toqué el dispositivo", error)
        commands = pasteable(error)[0]
        self.assertTrue(commands[0].endswith("setup --reponer --carpeta %s" % rel), commands)
        self.assertIn("./gradlew :app:installProfiling", commands[1])
        self.assertIn("capturar --plan", commands[2])

    def test_humo_se_detiene_y_nuevo_lo_dice(self):
        self.in_patch()
        error = self.bad("humo", "--paquete", PKG, code=perf.Precondicion.code)
        self.assertIn("el setup de medición no está en el árbol", error)
        self.assertTrue(pasteable(error)[0][0].endswith("setup --reponer"))
        result = self.run_perf("nuevo", "--carpeta", "reports/perf/inicio/2099-01-02", "--paquete", PKG, "--flujo", "inicio")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("⚠ Setup: setup en parche, sin reponer", result.stdout)
        self.assertIn("setup --reponer --carpeta reports/perf/inicio/2099-01-02", result.stdout)
        self.assertIn("siguiente --carpeta reports/perf/inicio/2099-01-02", pasteable(result.stdout)[0][-1])

    def test_sin_la_linea_en_agents_no_se_recorre_el_proyecto(self):
        with mock.patch.object(perf, "find_hooks", side_effect=AssertionError("no debe recorrer el proyecto")):
            self.assertIsNone(perf.setup_missing(self.root))


class SetupOutputsTest(SetupBase):
    """Regla de la versión: cada salida nueva termina con el paso que sigue o con el cierre explícito, y sus comandos se
    pueden pegar tal cual (lo comprueban `good` y `bad` en cada llamada)."""

    def test_recorrido_de_las_salidas(self):
        self.assertTrue(ends_with_step(self.good("setup")))  # sin opciones es --estado
        self.instrument()
        self.good("setup", "--estado")
        self.good("setup", "--guardar", "--simular", *WIRING)
        self.good("setup", "--guardar", *WIRING)
        self.good("setup", "--quitar", "--simular")
        self.assertIn(perf.NO_STEPS_LEFT, self.good("setup", "--quitar"))
        self.assertIn(perf.NO_STEPS_LEFT, self.good("setup", "--quitar"))  # ya quitado: también lo dice
        self.good("setup", "--estado")
        self.good("setup", "--reponer", "--simular")
        self.good("setup", "--reponer")
        self.good("setup", "--vigente", self.saved()[0])
        self.bad("setup", "--vigente", "no-existe.patch")
        self.bad("setup", "--reponer", "--quitar")
        folder = self.investigation()
        self.good("setup", "--estado", "--carpeta", folder.relative_to(self.root))
        self.assertIn("Siguiente paso", (folder / "estado.md").read_text(encoding="utf-8"))

    def test_las_rutas_con_espacios_van_citadas(self):
        root = make_project(self.dir / "mi proyecto")
        done = self.run_perf("instrumentar", "--modulo", "app", "--paquete", PKG + ".perf", cwd=root)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = self.run_perf("setup", "--guardar", "--quitar", cwd=root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_perf("setup", "--estado", cwd=root)
        command = pasteable(result.stdout)[0][0]
        self.assertTrue(command.startswith("cd '%s' && python3 -I " % root.resolve()), command)
        done = subprocess.run(["sh", "-c", command.replace("python3 -I", "%s -I" % sys.executable)], env=self.env,
                              capture_output=True, text=True)  # pegado tal cual, repone
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((root / HOOKS).is_file())

    def test_nada_escribe_en_el_perfil_del_shell(self):
        self.in_patch()
        self.good("setup", "--reponer")
        self.good("setup", "--quitar")
        self.assertEqual([path.name for path in self.home.iterdir()], [])  # el HOME temporal sigue vacío



# ── D · Nunca tocar un módulo que el build toma como binario ─────────────────
DEPS_BINARY = ("\n------------------------------------------------------------\nProject ':app'\n"
               "------------------------------------------------------------\n\n"
               "profilingRuntimeClasspath - Runtime classpath of /profiling.\n"
               "+--- project :core\n"
               "|    \\--- com.squareup.okhttp3:okhttp:4.12.0\n"
               "+--- com.example:modulo-pagos:1.2.0\n"
               "|    \\--- org.jetbrains.kotlin:kotlin-stdlib:2.0.0 -> 2.0.21 (*)\n"
               "+--- com.example:util:{strictly 1.0} -> 1.0 (c)\n"
               "\\--- project :feature:inicio (*)\n\n(c) - A dependency constraint, not a dependency.\n"
               "(*) - Indicates repeated occurrences of a transitive dependency subtree.\n")
DEPS_CODE = DEPS_BINARY.replace("+--- com.example:modulo-pagos:1.2.0\n",
                                "+--- com.example:modulo-pagos:1.2.0 -> project :modulo-pagos\n")
SETTINGS = ('include(":app", ":core", ":feature:inicio")\n'
            'val locales = groovy.json.JsonSlurper().parse(file("modulos-locales.json")) as Map<String, Boolean>\n'
            'if (locales["modulo-pagos"] == true) {\n'
            '    includeBuild("../modulo-pagos") {\n'
            '        dependencySubstitution { substitute(module("com.example:modulo-pagos")).using(project(":")) }\n'
            '    }\n}\n')
SWITCH = '{\n  "modulo-pagos": false,\n  "otro-modulo": true\n}\n'
SIBLING_FILE = "class Pagos {\n    fun pagar() {\n        cobrar()\n    }\n}\n"


class ModulesBase(SetupBase):
    """Un proyecto cascarón: la app, un módulo en la raíz (:core) y un módulo de otro repo (../modulo-pagos) que el build
    toma como binario o como código según un archivo propio del proyecto."""

    def setUp(self):
        super().setUp()
        write(self.root / "settings.gradle.kts", SETTINGS)
        write(self.root / "modulos-locales.json", SWITCH)
        write(self.root / "core" / "build.gradle.kts", 'plugins { id("com.android.library") }\n')
        write(self.root / "core" / "src" / "main" / "kotlin" / "Core.kt", "object Core\n")
        self.instrument()
        commit_all(self.root, "setup versionado y módulos")
        self.sibling = self.dir / "modulo-pagos"
        self.sibling.mkdir()
        init_repo(self.sibling)
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE)
        commit_all(self.sibling, "base")
        self.folder = self.investigation(plan={
            "paquete": PKG, "principales": ["pago_ms"], "instalar": "./gradlew :app:installProfiling",
            "flujos": {"pagos": {"recorrido": "true", "metricas_usuario": [
                {"nombre": "pago_ms", "desde": {"marca": "MARK pago_inicio"}, "hasta": {"marca": "MARK pago_visible"}}]}},
            "mejoras": [{"id": "M1", "titulo": "Precargar el pago", "estado": "aprobada", "metrica": "pago_ms"}]})
        self.rel = self.folder.relative_to(self.root)
        self.binary = self.dir / "dependencias-binario.txt"
        self.code = self.dir / "dependencias-codigo.txt"
        write(self.binary, DEPS_BINARY)
        write(self.code, DEPS_CODE)

    def modules(self):
        return {item["nombre"]: item for item in json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["modulos"]}

    def register(self, deps, *names):
        return self.good("setup", "--estado", "--carpeta", self.rel, "--modulos", *names, "--dependencias", deps)


class DependenciesParseTest(unittest.TestCase):
    """D1: lo que dice Gradle de cada módulo."""

    def test_proyectos_artefactos_y_sustituciones(self):
        deps = perf.parse_dependencies(DEPS_BINARY)
        self.assertEqual(deps["proyectos"], {":core", ":feature:inicio"})
        self.assertEqual(deps["artefactos"]["com.example:modulo-pagos"], {"version": "1.2.0", "proyecto": None})
        self.assertEqual(deps["artefactos"]["com.example:util"]["version"], "1.0")
        self.assertEqual(deps["artefactos"]["org.jetbrains.kotlin:kotlin-stdlib"]["version"], "2.0.21")
        deps = perf.parse_dependencies(DEPS_CODE)
        self.assertEqual(deps["artefactos"]["com.example:modulo-pagos"]["proyecto"], ":modulo-pagos")
        self.assertIn(":modulo-pagos", deps["proyectos"])
        self.assertEqual(perf.parse_dependencies("No dependencies\n"),
                         {"proyectos": set(), "artefactos": {}, "sustituidos": {}})

    def test_un_proyecto_cambiado_por_un_binario_no_es_codigo(self):
        text = ("profilingRuntimeClasspath - Runtime classpath of /profiling.\n"
                "+--- project :feature:pagos -> com.example.feature:pagos:3.1.0\n"
                "+--- project :feature:inicio:impl\n"
                "+--- com.example.cobros:impl:1.0.0\n"
                "+--- project :sin-resolver (n)\n"
                "\\--- com.example:viejo:1.0 -> com.example:nuevo:2.0\n")
        deps = perf.parse_dependencies(text)
        self.assertEqual(deps["sustituidos"], {":feature:pagos": "com.example.feature:pagos:3.1.0"})
        self.assertEqual(deps["proyectos"], {":feature:inicio:impl"})  # ni el sustituido ni el que no se resolvió
        self.assertEqual(deps["artefactos"]["com.example:viejo"]["version"], "2.0")
        root = Path("/no/existe")
        kinds = {item["nombre"]: item for item in perf.classify_modules(root, [
            ":feature:pagos", "com.example.cobros:impl", ":feature:cobros:impl", ":feature:inicio:impl", "impl", ":app"],
            deps, app="app")}
        self.assertEqual(kinds[":feature:pagos"]["tipo"], "binario")
        self.assertEqual(kinds[":feature:pagos"]["artefacto"], "com.example.feature:pagos:3.1.0")
        self.assertEqual(kinds["com.example.cobros:impl"]["tipo"], "binario")  # la coincidencia exacta gana
        self.assertEqual(kinds[":feature:cobros:impl"]["tipo"], "sin confirmar")  # el nombre corto no se adivina
        self.assertIn("coincide con varios módulos", kinds[":feature:cobros:impl"]["motivo"])
        self.assertEqual(kinds[":feature:inicio:impl"]["tipo"], "codigo")
        self.assertEqual(kinds["impl"]["tipo"], "sin confirmar")
        self.assertEqual(kinds[":app"]["tipo"], "codigo")  # el módulo que se compila no aparece como dependencia

    def test_una_salida_con_varias_configuraciones(self):
        text = ("debugRuntimeClasspath - Runtime classpath of /debug.\n+--- project :pagos\n\n"
                "profilingRuntimeClasspath - Runtime classpath of /profiling.\n+--- com.example:pagos:1.0.0\n")
        block, name, why = perf.dependencies_block(text, "profilingRuntimeClasspath")
        self.assertEqual((name, why), ("profilingRuntimeClasspath", ""))
        self.assertEqual(perf.parse_dependencies(block)["proyectos"], set())  # lo de debug no cuenta
        self.assertIn("y no qaRuntimeClasspath", perf.dependencies_block(text, "qaRuntimeClasspath")[2])
        self.assertIn("2 configuraciones", perf.dependencies_block(text, None)[2])
        self.assertEqual(perf.dependencies_block("+--- project :a\n", "x")[1], None)  # sin encabezado: se usa tal cual

    def test_la_configuracion_sale_del_instalar_del_plan(self):
        args = unittest.mock.Mock(app=None, configuracion=None)
        self.assertEqual(perf.measured_configuration({"instalar": "./gradlew :app:installProfiling"}, args),
                         ("app", "profilingRuntimeClasspath"))
        self.assertEqual(perf.measured_configuration({"instalar": "./gradlew :movil:app:installDemoProfiling -Pperf"}, args),
                         ("movil/app", "demoProfilingRuntimeClasspath"))
        self.assertEqual(perf.measured_configuration({}, args), ("app", None))
        args = unittest.mock.Mock(app="movil", configuracion="qaRuntimeClasspath")
        self.assertEqual(perf.measured_configuration({"instalar": "./gradlew :app:installProfiling"}, args),
                         ("movil", "qaRuntimeClasspath"))


class ModulesMapTest(ModulesBase):
    """D1 y D2: el mapa código/binario en el plan y en la ficha, y el interruptor del proyecto, sin tocarlo."""

    def test_el_mapa_queda_en_el_plan_y_en_la_ficha(self):
        out = self.register(self.binary, ":core", "com.example:modulo-pagos", ":feature:inicio", "com.example:no-existe")
        modules = self.modules()
        self.assertEqual((modules[":core"]["tipo"], modules[":core"]["carpeta"]), ("codigo", "core"))
        self.assertEqual(modules["com.example:modulo-pagos"]["tipo"], "binario")
        self.assertEqual(modules["com.example:modulo-pagos"]["artefacto"], "com.example:modulo-pagos:1.2.0")
        self.assertEqual(modules["com.example:modulo-pagos"]["carpeta"], "../modulo-pagos")  # su código está en disco
        self.assertEqual(modules[":feature:inicio"]["tipo"], "codigo")
        self.assertEqual(modules["com.example:no-existe"]["tipo"], "sin confirmar")  # nunca se da por código
        self.assertIn("Módulos del alcance, según la salida guardada en", out)
        self.assertIn(":app:dependencies --configuration profilingRuntimeClasspath", out)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        self.assertIn("<!-- perf:modulos -->", state)
        self.assertIn("| `com.example:modulo-pagos` | binario (llega compilado) | `../modulo-pagos` | "
                      "com.example:modulo-pagos:1.2.0 | no se edita |", state)
        self.assertLess(state.index("## Mapa del alcance"), state.index("<!-- perf:modulos -->"))
        self.assertLess(state.index("<!-- perf:modulos -->"), state.index("## Cambios temporales"))
        self.assertIn("Módulo com.example:modulo-pagos: el build lo toma como binario (com.example:modulo-pagos:1.2.0)", state)
        self.assertIn("no cites `archivo:línea` de ese módulo como evidencia confirmada", state)

    def test_el_interruptor_se_nombra_y_nunca_se_edita(self):
        before = {name: (self.root / name).read_bytes() for name in ("settings.gradle.kts", "modulos-locales.json")}
        out = self.register(self.binary, "com.example:modulo-pagos")
        self.assertIn("el proyecto lo controla en `modulos-locales.json`, clave `modulo-pagos` (hoy: false)", out)
        self.assertIn("perf.py nunca lo edita: lo pasa a fuente la sesión 1, antes de medir", out)
        self.assertIn("settings.gradle.kts:5 (dependencySubstitution)", out)
        commands = pasteable(out)[0]
        self.assertTrue(commands[0].endswith("setup --estado --comprobar-modulos --carpeta %s" % self.rel), commands)
        self.assertIn("--confirmar com.example:modulo-pagos=binario", commands[1])
        self.good("siguiente", "--carpeta", self.rel)
        self.good("setup", "--estado", "--carpeta", self.rel)
        self.assertEqual({name: (self.root / name).read_bytes() for name in before}, before)
        self.assertEqual(git(self.root, "status", "--short", "--", *before), "")

    def test_interruptor_en_properties_y_sin_mecanismo(self):
        module = {"nombre": "com.example:modulo-pagos", "artefacto": "com.example:modulo-pagos:1.2.0", "tipo": "binario"}
        write(self.root / "settings.gradle.kts", 'include(":app")\n')
        (self.root / "modulos-locales.json").unlink()
        text = perf.switch_text(perf.substitution_switch(self.root, module), module)
        self.assertIn("no encontré ningún mecanismo de sustitución en settings.gradle(.kts)", text)
        self.assertIn("llega solo compilado", text)
        write(self.root / "gradle.properties", "org.gradle.jvmargs=-Xmx2g\nusarModuloPagosLocal=false\nclaveSecreta=abc123\n")
        switch = perf.substitution_switch(self.root, module)
        self.assertEqual((switch["archivo"], switch["clave"], switch["valor"]), ("gradle.properties", "usarModuloPagosLocal",
                                                                                 "false"))
        self.assertNotIn("abc123", json.dumps(switch))  # solo la clave del módulo; ningún otro valor

    def test_sin_gradle_no_se_da_por_codigo(self):
        result = self.run_perf("setup", "--estado", "--carpeta", self.rel, "--modulos", ":core")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no pude preguntarle a Gradle (no hay ./gradlew en", result.stdout)
        self.assertIn("Ninguno se da por código", result.stdout)
        self.assertEqual(self.modules()[":core"]["tipo"], "sin confirmar")
        self.assertIn("--confirmar :core=codigo o --confirmar :core=binario", result.stdout)
        out = self.good("siguiente", "--carpeta", self.rel)
        self.assertIn(":core está sin confirmar", out)
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", ":core=codigo")
        self.assertEqual((self.modules()[":core"]["tipo"], self.modules()[":core"]["origen"]), ("codigo", "usuario"))
        self.assertNotIn("sin confirmar", "\n".join(pasteable(out)[0]))

    def test_gradle_de_verdad_recibe_la_configuracion(self):
        # un gradlew de mentira que deja registrado cómo lo llamaron y responde como Gradle
        executable(self.root / "gradlew", "#!/bin/sh\necho \"$@\" > \"%s\"\ncat \"%s\"\n" % (self.dir / "gradle.args", self.code))
        self.good("setup", "--estado", "--carpeta", self.rel, "--modulos", "com.example:modulo-pagos")
        self.assertEqual((self.dir / "gradle.args").read_text().strip(),
                         "-q :app:dependencies --configuration profilingRuntimeClasspath")
        self.assertEqual(self.modules()["com.example:modulo-pagos"]["tipo"], "codigo")
        self.assertTrue((self.folder / "logs" / "dependencias.txt").is_file())
        write(self.root / "gradlew", "#!/bin/sh\necho 'FAILURE: Build failed' >&2\nexit 1\n")
        result = self.run_perf("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--configuracion",
                               "qaRuntimeClasspath")
        self.assertIn("Gradle terminó con código 1", result.stdout)
        self.assertEqual(self.modules()["com.example:modulo-pagos"]["tipo"], "sin confirmar")


class ModulesGateTest(ModulesBase):
    """D3: ninguna sesión edita un archivo de un módulo que el build toma como binario."""

    def setUp(self):
        super().setUp()
        self.register(self.binary, ":core", "com.example:modulo-pagos")

    def test_decidir_aplicada_se_detiene_y_sigue_tras_cambiar_el_interruptor(self):
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE.replace("        cobrar()\n", "        precargar()\n        cobrar()\n"))
        error = self.bad("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "src/Pagos.kt", "--repo",
                         "../modulo-pagos")
        self.assertIn("la mejora M1 toca un módulo binario: no se edita un módulo que la app consume compilado", error)
        self.assertIn("el build lo toma como binario (com.example:modulo-pagos:1.2.0): lo que edites ahí no llega al APK", error)
        self.assertIn("`modulos-locales.json`, clave `modulo-pagos` (hoy: false)", error)
        self.assertTrue(pasteable(error)[0][0].endswith("setup --estado --comprobar-modulos --carpeta %s" % self.rel))
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["mejoras"][0]["estado"], "aprobada")  # no registró nada
        self.assertFalse((self.folder / "cambios").exists())
        # una mejora del lado de la app sí se puede aplicar
        write(self.root / "core" / "src" / "main" / "kotlin" / "Core.kt", "object Core { val listo = true }\n")
        self.good("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "core/src/main/kotlin/Core.kt")
        # el usuario cambia el interruptor (él: perf.py no lo toca) y Gradle ahora lo compila desde código
        write(self.root / "modulos-locales.json", SWITCH.replace('"modulo-pagos": false', '"modulo-pagos": true'))
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--dependencias", self.code)
        self.assertEqual(self.modules()["com.example:modulo-pagos"]["tipo"], "codigo")
        self.assertIn("com.example:modulo-pagos:1.2.0 -> project :modulo-pagos", out)
        self.good("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "src/Pagos.kt", "--repo",
                  "../modulo-pagos")
        self.assertTrue((self.folder / "cambios").is_dir())

    def test_las_marcas_y_la_prueba_se_detienen(self):
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE.replace(
            "        cobrar()\n", "        cobrar()\n        android.os.Trace.beginSection(\"MARK pago_visible\")\n"))
        write(self.folder / "estado.md", STATE % "| `src/Pagos.kt` | ../modulo-pagos | marca pago_visible | — | no |\n")
        before = (self.sibling / "src" / "Pagos.kt").read_bytes()
        error = self.bad("marcas", "--carpeta", self.rel, "--separar")
        self.assertIn("las marcas no pueden ir en un módulo binario", error)
        self.assertIn("src/Pagos.kt · el build lo toma como binario", error)
        self.assertFalse((self.folder / "parches").exists())
        error = self.bad("capturar", "--plan", self.rel / "plan.json", "--prueba", code=perf.Precondicion.code)
        self.assertIn("una marca del plan o un cambio temporal está en un módulo binario", error)
        self.assertIn("../modulo-pagos/src/Pagos.kt (MARK pago_visible)", error)
        self.assertEqual((self.sibling / "src" / "Pagos.kt").read_bytes(), before)
        # con el módulo compilado desde código, las dos siguen (la prueba pasa a pedir el dispositivo)
        self.good("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--dependencias", self.code)
        self.good("marcas", "--carpeta", self.rel, "--separar")
        result = self.run_perf("capturar", "--plan", self.rel / "plan.json", "--prueba")
        self.assertNotIn("módulo binario", result.stderr)

    def test_una_marca_en_el_modulo_app_sin_filas_tambien_se_revisa(self):
        # la marca está en el repo hermano, sin fila en "Cambios temporales": la prueba la encuentra por su nombre
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE + "// PerfHooks.mark(\"pago_inicio\")\n")
        error = self.bad("capturar", "--plan", self.rel / "plan.json", "--prueba", code=perf.Precondicion.code)
        self.assertIn("../modulo-pagos/src/Pagos.kt (MARK pago_inicio)", error)

    def test_aceptar_el_binario_mide_desde_la_app_y_sigue_sin_editarlo(self):
        out = self.good("siguiente", "--carpeta", self.rel)
        self.assertIn("Módulos del alcance que la app consume compilados (no se editan)", out)
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", "com.example:modulo-pagos=binario")
        self.assertTrue(self.modules()["com.example:modulo-pagos"]["aceptado"])
        self.assertNotIn("consume compilados", out)  # `siguiente` deja de preguntar
        self.assertIn("no se edita; se mide desde el módulo app", (self.folder / "estado.md").read_text(encoding="utf-8"))
        self.bad("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "src/Pagos.kt", "--repo",
                 "../modulo-pagos")  # aceptado no quiere decir editable
        self.good("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--dependencias", self.binary)
        self.assertTrue(self.modules()["com.example:modulo-pagos"]["aceptado"])  # comprobar de nuevo no lo olvida

    def test_el_pedido_al_equipo_dueno_sale_en_el_reporte_tecnico(self):
        self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", "com.example:modulo-pagos=binario")
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        write(self.folder / "metricas.csv", "fase,flujo,metrica,corrida,valor,unidad,sentido,familia\n" + "".join(
            "antes,pagos,pago_ms,%d,%d,ms,menor,app\n" % (index, value) for index, value in enumerate((900, 910, 905, 915, 920), 1)))
        self.assertEqual(self.run_perf("reporte", "--carpeta", self.rel, "--inicial").returncode, 0)
        self.assertNotIn("Pedido al equipo dueño", (self.folder / "reporte-inicial-dev.md").read_text(encoding="utf-8"))
        write(self.folder / "estado.md", state + "\n## Pedido al equipo dueño del módulo\n\n- Se midió el pago: 900 ms antes de "
              "mostrar el resultado; la traza muestra 600 ms dentro del módulo de pagos. Se propone precargar el catálogo.\n")
        self.assertEqual(self.run_perf("reporte", "--carpeta", self.rel, "--inicial").returncode, 0)
        dev = (self.folder / "reporte-inicial-dev.md").read_text(encoding="utf-8")
        self.assertIn("Pedido al equipo dueño del módulo", dev)
        self.assertIn("Para enviar al equipo dueño de un módulo que la app consume compilado", dev)
        self.assertIn("Se propone precargar el catálogo", dev)
        self.assertNotIn("Pedido al equipo dueño", (self.folder / "reporte-inicial-gerencia.md").read_text(encoding="utf-8"))
        template = (SKILL / "assets" / "plantillas" / "estado.md").read_text(encoding="utf-8")
        section = template.split("## Pedido al equipo dueño del módulo")[1].split("\n## ")[0]
        self.assertEqual(perf.without_placeholders(section), "")  # sin completar, la sección no se publica

    def test_un_modulo_sin_confirmar_no_se_edita(self):
        # sin Gradle, :core queda sin confirmar; su carpeta se conoce igual y la compuerta lo protege
        result = self.run_perf("setup", "--estado", "--carpeta", self.rel, "--modulos", ":core")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.modules()[":core"]["tipo"], self.modules()[":core"]["carpeta"]), ("sin confirmar", "core"))
        write(self.root / "core" / "src" / "main" / "kotlin" / "Core.kt", "object Core { val listo = true }\n")
        error = self.bad("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "core/src/main/kotlin/Core.kt")
        self.assertIn("el módulo :core está sin confirmar", error)
        out = self.good("siguiente", "--carpeta", self.rel)
        self.assertIn("--confirmar :core=codigo", "\n".join(pasteable(out)[0]))
        self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", ":core=codigo")
        self.good("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "core/src/main/kotlin/Core.kt")

    def test_el_nombre_del_repo_no_bloquea_un_archivo_del_modulo_app(self):
        marked = WIRED_CLIENT.replace('    fun version() = "1"\n', '    fun version() = "1" // marca\n')
        write(self.root / RED, marked)
        write(self.folder / "estado.md", STATE % ("| `%s` | app (alrededor de modulo-pagos) | marca | — | no |\n" % RED))
        self.good("marcas", "--carpeta", self.rel, "--separar")  # medir desde el módulo app es justo lo recomendado

    def test_un_modulo_bloqueado_sin_carpeta_conocida(self):
        # por coordenada y sin Gradle no hay forma de saber dónde está su código: se pide, y mientras tanto se reconoce
        # por el nombre de la carpeta del módulo (no por un paquete del módulo app que se llame igual)
        write(self.root / "features" / "cobros" / "src" / "Cobros.kt", "class Cobros\n")
        write(self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "cobros" / "Vista.kt", "class Vista\n")
        commit_all(self.root, "cobros")
        result = self.run_perf("setup", "--estado", "--carpeta", self.rel, "--modulos", "com.example:cobros")
        self.assertIn("com.example:cobros no se edita (sin confirmar) y no sé dónde está su código en disco", result.stdout)
        self.assertIn("--modulos com.example:cobros=RUTA", result.stdout)
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", "com.example:cobros=binario")
        self.assertIn("no sé dónde está su código en disco", out)
        self.assertNotIn("carpeta", self.modules()["com.example:cobros"])
        write(self.root / "features" / "cobros" / "src" / "Cobros.kt", "class Cobros { val nuevo = 1 }\n")
        error = self.bad("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "features/cobros/src/Cobros.kt")
        self.assertIn("la mejora M1 toca un módulo binario", error)
        write(self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "cobros" / "Vista.kt",
              "class Vista { val nuevo = 1 }\n")
        self.good("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos",
                  "app/src/main/kotlin/com/example/app/cobros/Vista.kt")  # el lado de la app sí se puede

    def test_corregir_lo_que_respondio_el_usuario(self):
        self.run_perf("setup", "--estado", "--carpeta", self.rel, "--modulos", ":core")  # sin Gradle: sin confirmar
        self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", ":core=codigo")
        self.good("setup", "--estado", "--carpeta", self.rel, "--confirmar", ":core=binario")  # se equivocó: lo corrige
        self.assertEqual((self.modules()[":core"]["tipo"], self.modules()[":core"]["origen"]), ("binario", "usuario"))
        self.register(self.binary, ":core")  # ahora lo dice Gradle: una respuesta ya no lo cambia
        self.assertIn("Gradle dijo que :core es código", self.bad("setup", "--estado", "--carpeta", self.rel,
                                                                 "--confirmar", ":core=binario"))

    def test_modulos_sin_carpeta_o_sin_plan(self):
        self.assertIn("van con --carpeta", self.bad("setup", "--estado", "--modulos", ":core"))
        (self.folder / "plan.json").unlink()
        self.assertIn("el mapa de módulos se guarda en el plan", self.bad("setup", "--estado", "--carpeta", self.rel,
                                                                       "--modulos", ":core"))

    def test_un_plan_sin_modulos_sigue_como_antes(self):
        plan = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))
        del plan["modulos"]
        write(self.folder / "plan.json", json.dumps(plan))
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE.replace("cobrar()", "cobrar(); precargar()"))
        self.good("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "src/Pagos.kt", "--repo",
                  "../modulo-pagos")


# ── Ensayo de punta a punta, sin dispositivo ─────────────────────────────────
class EndToEndSetupTest(ModulesBase):
    """Sin setup → instrumentar → guardar y quitar → `siguiente` pide reponer → reponer → se detiene con cambios del usuario
    y con un parche de otro remoto → `instrumentar --actualizar` → `cerrar` guarda el parche nuevo y quita el setup. Un
    módulo del alcance binario detiene la mejora y la prueba hasta que se compila desde código. Nada toca el HOME."""

    def setUp(self):
        SetupBase.setUp(self)  # sin el setup versionado de ModulesBase: aquí se recorre desde cero
        write(self.root / "settings.gradle.kts", SETTINGS)
        write(self.root / "modulos-locales.json", SWITCH)
        write(self.root / "core" / "build.gradle.kts", 'plugins { id("com.android.library") }\n')
        write(self.root / "core" / "src" / "main" / "kotlin" / "Core.kt", "object Core\n")
        write(self.root / "AGENTS.md", AGENTS.replace("- setup listo\n", ""))
        commit_all(self.root, "proyecto")
        self.sibling = self.dir / "modulo-pagos"
        self.sibling.mkdir()
        init_repo(self.sibling)
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE)
        commit_all(self.sibling, "base")
        self.binary = self.dir / "dependencias-binario.txt"
        self.code = self.dir / "dependencias-codigo.txt"
        write(self.binary, DEPS_BINARY)
        write(self.code, DEPS_CODE)

    def test_ensayo(self):
        client = self.root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "red" / "Red.kt"
        # 1. sin setup: la sesión 0
        out = self.good("setup", "--estado")
        self.assertIn("Siguiente · falta la sesión 0 (setup)", out)
        # 2. la sesión 0 genera, cablea y anota "setup listo"; el equipo no lo versiona: va en parche
        self.instrument()
        write(self.root / "AGENTS.md", AGENTS)
        git(self.root, "add", "AGENTS.md")
        git(self.root, "commit", "-q", "-m", "docs: rendimiento")
        with_setup = self.tree()
        self.good("setup", "--guardar", "--quitar", *WIRING)
        first, ficha = self.saved()
        self.assertEqual((ficha["remoto"], ficha["applicationId"]), (REMOTE, PKG))
        self.assertEqual(self.status(), [])
        # 3. una investigación: `siguiente` pide reponer antes de medir, y `capturar` no arranca sin el setup
        self.folder = self.investigation(plan={
            "paquete": PKG, "principales": ["pago_ms"], "instalar": "./gradlew :app:installProfiling",
            "flujos": {"pagos": {"recorrido": "true", "metricas_usuario": [
                {"nombre": "pago_ms", "desde": {"marca": "MARK pago_inicio"}, "hasta": {"marca": "MARK pago_visible"}}]}},
            "mejoras": [{"id": "M1", "titulo": "Precargar el pago", "estado": "aprobada", "metrica": "pago_ms"}]})
        self.rel = self.folder.relative_to(self.root)
        out = self.good("siguiente", "--carpeta", self.rel)
        self.assertTrue(pasteable(out)[0][0].endswith("setup --reponer --carpeta %s" % self.rel))
        self.bad("capturar", "--plan", self.rel / "plan.json", "--fase", "antes", code=perf.Precondicion.code)
        # 4. cambios del usuario sin commitear en un archivo del setup: se detiene sin tocar nada
        write(client, CLIENT + "// trabajo mío\n")
        before = self.tree()
        self.assertIn("hay cambios tuyos sin commitear", self.bad("setup", "--reponer", "--carpeta", self.rel))
        self.assertEqual(self.tree(), before)
        write(client, CLIENT)
        # 5. un parche de otro remoto: se detiene
        path = first.parent / (first.name + ".json")
        write(path, json.dumps(dict(ficha, remoto="git@example.com:otro-equipo/otra-app.git")))
        self.assertIn("el parche es de otro repo: git@example.com:otro-equipo/otra-app.git", self.bad("setup", "--reponer"))
        self.assertEqual(self.status(), [])
        write(path, json.dumps(ficha))
        # 6. reponer: vuelve exactamente el setup
        out = self.good("setup", "--reponer", "--carpeta", self.rel)
        self.assertEqual(self.tree(), with_setup)
        self.assertNotIn("setup --reponer", "\n".join(pasteable(out)[0]))
        # 7. un módulo del alcance llega como binario: la ficha lo marca y nadie lo edita
        out = self.good("setup", "--estado", "--carpeta", self.rel, "--modulos", ":core", "com.example:modulo-pagos",
                        "--dependencias", self.binary)
        self.assertIn("`modulos-locales.json`, clave `modulo-pagos` (hoy: false)", out)
        write(self.sibling / "src" / "Pagos.kt", SIBLING_FILE.replace(
            "        cobrar()\n", "        precargar()\n        cobrar()\n        android.os.Trace.beginSection(\"MARK pago_visible\")\n"))
        self.assertIn("la mejora M1 toca un módulo binario", self.bad(
            "decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "src/Pagos.kt", "--repo", "../modulo-pagos"))
        self.assertIn("está en un módulo binario", self.bad("capturar", "--plan", self.rel / "plan.json", "--prueba",
                                                             code=perf.Precondicion.code))
        # 8. el usuario cambia el interruptor: Gradle lo compila desde código y todo sigue
        write(self.root / "modulos-locales.json", SWITCH.replace('"modulo-pagos": false', '"modulo-pagos": true'))
        git(self.root, "commit", "-q", "-am", "chore: módulo de pagos desde código")
        self.good("setup", "--estado", "--carpeta", self.rel, "--comprobar-modulos", "--dependencias", self.code)
        self.good("decidir", "--carpeta", self.rel, "--aplicada", "M1", "--archivos", "src/Pagos.kt", "--repo",
                  "../modulo-pagos")
        self.assertNotIn("módulo binario", self.run_perf("capturar", "--plan", self.rel / "plan.json", "--prueba").stderr)
        # 9. entre medio, `instrumentar --actualizar` cambió el setup (simulado: una plantilla nueva y un archivo nuevo)
        mark = self.root / "app" / "src" / "perf" / "kotlin" / "com" / "example" / "app" / "perf" / "MarkTrace.kt"
        write(mark, mark.read_text(encoding="utf-8") + "// plantilla de la versión nueva\n")
        # 10. el cierre: guarda el parche nuevo (el viejo queda reemplazado) y quita el setup
        # (fechas fijas, sin depender del reloj: se midió después de aplicar la mejora y los reportes son posteriores)
        write(self.folder / "fases.json", json.dumps({phase: {"fecha": "2099-06-01T10:0%d:00" % index, "corridas": 10,
                                                               "flujos": {"pagos": {"corridas": 10}}}
                                                      for index, phase in enumerate(("antes", "control", "despues"))}))
        for name in ("reporte-inicial-dev.md", "reporte-final-dev.md"):
            write(self.folder / name, "x")
            os.utime(str(self.folder / name), (4102444800, 4102444800))  # 2100-01-01
        out = self.good("cerrar", "--carpeta", self.rel, "--dod")
        self.assertIn("lo guardo antes de quitar", out)
        second, _ = self.saved()
        self.assertNotEqual(first, second)
        self.assertIn(b"// plantilla de la versi", second.read_bytes())
        self.assertTrue(first.is_file())  # el viejo no se borra
        self.assertEqual(self.status(), [])  # git status sin archivos del setup
        self.assertIsNone(perf.find_hooks(self.root))
        self.assertIn("Investigación cerrada: %s" % perf.NO_STEPS_LEFT, out)
        self.assertIn("precargar()", (self.sibling / "src" / "Pagos.kt").read_text(encoding="utf-8"))  # la mejora se queda
        # 11. nada escribió en el HOME (ni perfiles del shell ni otra cosa)
        self.assertEqual([path.name for path in self.home.iterdir()], [])


if __name__ == "__main__":
    unittest.main()
