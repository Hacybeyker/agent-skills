"""scripts/check_conventions.py: cada skill figura con su versión actual en la tabla del README y en el catálogo."""
import importlib.util
import re
import unittest

from helpers import ROOT

SCRIPT = ROOT / "scripts" / "check_conventions.py"


def load():
    spec = importlib.util.spec_from_file_location("check_conventions", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


conventions = load()
README = ("| Skill | Tipo | Versión | Qué hace |\n| --- | --- | --- | --- |\n"
          "| [`hb-uno`](skills/hb-uno) | Flujo | 1.2.0 | Hace una cosa |\n"
          "| [`hb-dos`](skills/hb-dos) | Perfil | 0.3.1 | Hace otra |\n")
CATALOG = "| Skill | Tipo | Versión |\n| --- | --- | --- |\n| `hb-uno` | Flujo | 1.2.0 |\n| `hb-dos` | Perfil | 0.3.1 |\n"


class DocsTest(unittest.TestCase):
    def test_con_las_versiones_al_dia_no_hay_errores(self):
        self.assertEqual(conventions.docs_errors({"hb-uno": "1.2.0", "hb-dos": "0.3.1"}, README, CATALOG), [])

    def test_una_version_vieja_en_el_readme_o_en_el_catalogo_es_un_error(self):
        errors = conventions.docs_errors({"hb-uno": "1.3.0", "hb-dos": "0.3.1"}, README, CATALOG)
        self.assertEqual(errors, [("README.md", "hb-uno figura con la versión 1.2.0, pero la skill está en 1.3.0"),
                                  ("CATALOG.md", "hb-uno figura con la versión 1.2.0, pero la skill está en 1.3.0")])

    def test_una_skill_sin_fila_o_sin_columna_de_version_es_un_error(self):
        old_readme = "| Skill | Tipo | Qué hace |\n| --- | --- | --- |\n| [`hb-uno`](skills/hb-uno) | Flujo | Hace una cosa |\n"
        errors = conventions.docs_errors({"hb-uno": "1.2.0", "hb-tres": "1.0.0"}, old_readme, CATALOG)
        self.assertIn(("README.md", "no lista la skill hb-uno con su versión"), errors)  # la tabla sin la columna
        self.assertIn(("README.md", "no lista la skill hb-tres con su versión"), errors)
        self.assertIn(("CATALOG.md", "no lista la skill hb-tres con su versión"), errors)

    def test_el_readme_y_el_catalogo_del_repo_tienen_la_version_de_cada_skill(self):
        found = {}
        for skill in sorted((ROOT / "skills").iterdir()):
            text = (skill / "SKILL.md").read_text(encoding="utf-8") if (skill / "SKILL.md").is_file() else ""
            version = re.search(r'(?m)^  version: "([^"]+)"$', text)
            if version:
                found[skill.name] = version.group(1)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        catalog = (ROOT / "CATALOG.md").read_text(encoding="utf-8")
        self.assertTrue(found)
        self.assertEqual(conventions.docs_errors(found, readme, catalog), [])
        self.assertIn("| Skill | Tipo | Versión | Qué hace |", readme)


if __name__ == "__main__":
    unittest.main()
