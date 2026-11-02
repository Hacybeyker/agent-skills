"""Tests de la herramienta de hb-coach (skills/hb-coach/scripts/coach.py) en un proyecto temporal."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, init_repo, run

SKILL = ROOT / "skills" / "hb-coach"
SCRIPT = SKILL / "scripts" / "coach.py"


class CoachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = init_repo(Path(self.tmp.name))
        self.space = self.project / "aprendizaje"
        self.plan = self.space / "hilt" / "PLAN.md"

    def tearDown(self):
        self.tmp.cleanup()

    def coach(self, *args):
        return run([sys.executable, SCRIPT, *args], self.project)

    def ok(self, *args):
        result = self.coach(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def init_topic(self):
        """Crea el tema 'hilt' y deja un plan con dos lecciones en un módulo."""
        self.ok("init", "hilt", "--tema", "Hilt", "--area", "android")
        text = self.plan.read_text(encoding="utf-8")
        lessons = "- [ ] **1.1 Primera** — a\n- [ ] **1.2 Segunda** — b\n\n"
        new = re.sub(r"^- \[ \] \*\*1\.1 .*?(?=^## Proyecto final)", lessons, text, flags=re.S | re.M)
        self.assertNotEqual(new, text, "la plantilla de PLAN.md cambió de formato")
        self.plan.write_text(new, encoding="utf-8")

    def estado(self):
        return json.loads(self.ok("estado", "hilt", "--json").stdout)["temas"][0]

    def lesson_line(self, lesson_id):
        return next(l for l in self.plan.read_text(encoding="utf-8").splitlines() if "**%s " % lesson_id in l)

    def test_la_version_coincide_con_la_de_la_skill(self):
        version = re.search(r'^\s+version:\s*"([^"]+)"', (SKILL / "SKILL.md").read_text(encoding="utf-8"), re.M).group(1)
        self.assertEqual(self.ok("version").stdout.strip(), "hb-coach %s" % version)

    def test_init_crea_el_espacio_y_lo_excluye_de_git(self):
        self.init_topic()
        for name in ("hilt/PLAN.md", "hilt/GLOSARIO.md", "hilt/DUDAS.md", "hilt/lecciones", "METODO.md", "README.md"):
            self.assertTrue((self.space / name).exists(), name)
        self.assertIn("/aprendizaje/", (self.project / ".git/info/exclude").read_text(encoding="utf-8"))

    def test_leccion_crea_la_nota_y_la_marca_como_actual(self):
        self.init_topic()
        self.ok("leccion", "hilt", "1.2")
        self.assertTrue(list((self.space / "hilt/lecciones").glob("1.2-*.md")))
        self.assertEqual(self.estado()["actual"]["id"], "1.2")

    def test_completar_marca_la_leccion_y_avanza_a_la_siguiente(self):
        self.init_topic()
        self.ok("completar", "hilt", "1.1")
        estado = self.estado()
        self.assertEqual((estado["hechas"], estado["total"]), (1, 2))
        self.assertEqual(estado["actual"]["id"], "1.2")
        self.assertTrue(self.lesson_line("1.1").startswith("- [x]"))

    def test_convalidar_y_reabrir(self):
        self.init_topic()
        self.ok("completar", "hilt", "1.2", "--convalidada")
        self.assertIn("(convalidada)", self.lesson_line("1.2"))
        self.ok("reabrir", "hilt", "1.2")
        line = self.lesson_line("1.2")
        self.assertTrue(line.startswith("- [ ]"))
        self.assertNotIn("convalidada", line)
        self.assertEqual(self.estado()["actual"]["id"], "1.2")

    def test_build_genera_el_cuaderno(self):
        self.init_topic()
        self.ok("build")
        self.assertIn("Hilt", (self.space / "cuaderno.html").read_text(encoding="utf-8"))

    def test_check_avisa_los_enlaces_rotos_sin_fallar(self):
        self.init_topic()
        with open(self.space / "hilt/GLOSARIO.md", "a", encoding="utf-8") as f:
            f.write("\n[roto](no-existe.md)\n")
        result = self.ok("check", "hilt")
        self.assertIn("enlace roto a no-existe.md", result.stdout)

    def test_una_leccion_inexistente_termina_con_codigo_2(self):
        self.init_topic()
        result = self.coach("completar", "hilt", "9.9")
        self.assertEqual(result.returncode, 2)
        self.assertIn("La lección 9.9 no existe", result.stderr)

    def test_un_comando_desconocido_termina_con_codigo_2(self):
        result = self.coach("nada")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Comando desconocido", result.stderr)


if __name__ == "__main__":
    unittest.main()
