"""Tests de scripts/run_tests.py (la suite en paralelo) y de tests/perf_rapido.py (perf.py sin compilarlo cada vez)."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import ROOT, perf_argv

RUNNER = ROOT / "scripts" / "run_tests.py"
PASSING = """
import unittest


class Uno(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)

    def test_b(self):
        self.assertEqual(1 + 1, 2)


class Dos(unittest.TestCase):
    def test_c(self):
        self.assertIn("a", "abc")
"""
FAILING = """
import unittest


class Tres(unittest.TestCase):
    def test_falla(self):
        self.assertEqual("esperado", "obtenido")

    @unittest.skip("a propósito")
    def test_omitido(self):
        pass
"""


class RunTestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        (self.dir / name).write_text(textwrap.dedent(text), encoding="utf-8")

    def run_tests(self, *args):
        return subprocess.run([sys.executable, str(RUNNER), "-s", str(self.dir)] + list(args), capture_output=True,
                              text=True, encoding="utf-8", timeout=300)

    def test_todo_en_verde(self):
        self.write("test_uno.py", PASSING)
        result = self.run_tests("-j", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 3 tests in", result.stdout)
        self.assertIn("(2 procesos)", result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("OK"), result.stdout)
        self.assertIn("· test_uno.Uno (2 tests,", result.stdout)

    def test_un_fallo_sale_completo_y_el_codigo_es_1(self):
        self.write("test_uno.py", PASSING)
        self.write("test_tres.py", FAILING)
        result = self.run_tests()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Ran 5 tests in", result.stdout)
        self.assertIn("FAIL: test_falla (test_tres.Tres", result.stdout)
        self.assertIn("AssertionError: 'esperado' != 'obtenido'", result.stdout)
        self.assertIn("FAILED (failures=1, skipped=1)", result.stdout)
        self.assertIn("✖ test_tres.Tres", result.stdout)

    def test_un_modulo_que_no_importa_es_un_error(self):
        self.write("test_uno.py", PASSING)
        self.write("test_roto.py", "import modulo_que_no_existe\n")
        result = self.run_tests()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("modulo_que_no_existe", result.stdout)
        self.assertIn("FAILED (errors=1)", result.stdout)

    def test_solo_las_clases_pedidas(self):
        self.write("test_uno.py", PASSING)
        self.write("test_tres.py", FAILING)
        result = self.run_tests("-v", "test_uno.Dos")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 1 test", result.stdout)
        self.assertIn("test_c", result.stdout)
        self.assertNotIn("Tres", result.stdout)

    def test_sin_tests(self):
        result = self.run_tests()
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("NO TESTS RAN", result.stdout)


class PerfRapidoTest(unittest.TestCase):
    """perf_rapido.py corre el script como `python3 -I <script>`: mismo __main__, __file__, argumentos, salida y código
    de salida; la segunda vez, del bytecode guardado."""

    def test_igual_que_correrlo_directo(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "eco.py"
            script.write_text(textwrap.dedent("""
                import os
                import sys
                print(__name__, os.path.basename(__file__), sys.argv[1:], sys.modules["__main__"].__file__ == __file__)
                sys.exit(int(sys.argv[1]))
            """), encoding="utf-8")
            direct = subprocess.run([sys.executable, "-I", str(script), "3", "b c"], capture_output=True, text=True)
            for _ in range(2):  # la primera compila y guarda; la segunda usa lo guardado
                fast = subprocess.run(perf_argv(script) + ["3", "b c"], capture_output=True, text=True)
                self.assertEqual((fast.returncode, fast.stdout, fast.stderr),
                                 (direct.returncode, direct.stdout, direct.stderr))
            self.assertEqual(direct.stdout, "__main__ eco.py ['3', 'b c'] True\n")
            script.write_text("print('otro')\n", encoding="utf-8")  # el archivo cambió: no usa lo guardado
            self.assertEqual(subprocess.run(perf_argv(script), capture_output=True, text=True).stdout, "otro\n")

    def test_un_error_muestra_el_archivo_y_la_linea_del_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "roto.py"
            script.write_text("x = 1\nraise ValueError('mal')\n", encoding="utf-8")
            fast = subprocess.run(perf_argv(script), capture_output=True, text=True)
            self.assertEqual(fast.returncode, 1)
            self.assertIn("line 2", fast.stderr)
            self.assertIn(str(script), fast.stderr)
            self.assertIn("ValueError: mal", fast.stderr)


if __name__ == "__main__":
    unittest.main()
