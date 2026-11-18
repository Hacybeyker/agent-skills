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

from helpers import ENV, ROOT, commit_all, git, init_repo, write
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
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "consulta", "traza.perfetto-trace", "--sql", "select 1"],
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


if __name__ == "__main__":
    unittest.main()
