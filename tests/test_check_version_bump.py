"""Tests de scripts/check_version_bump.py en un repo git temporal."""
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, run, write

SCRIPT = ROOT / "scripts" / "check_version_bump.py"


def skill_md(name, version):
    return ('---\nname: %s\ndescription: prueba\nmetadata:\n  author: hacybeyker\n  version: "%s"\n---\n\n# %s\n'
            % (name, version, name))


class CheckVersionBumpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = init_repo(Path(self.tmp.name))
        write(self.repo / "skills/hb-uno/SKILL.md", skill_md("hb-uno", "1.0.0"))
        write(self.repo / "skills/hb-uno/references/a.md", "a\n")
        commit_all(self.repo, "base")
        git(self.repo, "checkout", "-q", "-b", "cambio")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, base="main"):
        return run([sys.executable, SCRIPT, base], self.repo)

    def test_sin_cambios_pasa(self):
        self.assertEqual(self.check().returncode, 0)

    def test_cambio_sin_subir_la_version_falla(self):
        write(self.repo / "skills/hb-uno/references/a.md", "b\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("hb-uno cambió, pero su versión sigue en 1.0.0", result.stdout)

    def test_cambio_commiteado_sin_subir_la_version_falla(self):
        write(self.repo / "skills/hb-uno/references/a.md", "b\n")
        commit_all(self.repo)
        self.assertEqual(self.check().returncode, 1)

    def test_archivo_nuevo_sin_registrar_cuenta_como_cambio(self):
        write(self.repo / "skills/hb-uno/references/nuevo.md", "n\n")
        self.assertEqual(self.check().returncode, 1)

    def test_cambio_con_version_mayor_pasa(self):
        write(self.repo / "skills/hb-uno/references/a.md", "b\n")
        write(self.repo / "skills/hb-uno/SKILL.md", skill_md("hb-uno", "1.0.1"))
        self.assertEqual(self.check().returncode, 0)

    def test_version_menor_falla(self):
        write(self.repo / "skills/hb-uno/SKILL.md", skill_md("hb-uno", "0.9.0"))
        self.assertEqual(self.check().returncode, 1)

    def test_skill_nueva_no_necesita_subir_version(self):
        write(self.repo / "skills/hb-dos/SKILL.md", skill_md("hb-dos", "1.0.0"))
        self.assertEqual(self.check().returncode, 0)

    def test_skill_eliminada_no_falla(self):
        git(self.repo, "rm", "-q", "-r", "skills/hb-uno")
        self.assertEqual(self.check().returncode, 0)

    def test_cambios_fuera_de_skills_no_cuentan(self):
        write(self.repo / "README.md", "otro\n")
        self.assertEqual(self.check().returncode, 0)

    def test_base_inexistente_termina_con_codigo_2(self):
        result = self.check("no-existe")
        self.assertEqual(result.returncode, 2)
        self.assertIn("✖", result.stderr)


if __name__ == "__main__":
    unittest.main()
