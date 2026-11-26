"""Tests de hb-performance 0.21.0: la rama del repo de una unidad que la sesión 1 pasa a fuente ya no la crea la skill
por su cuenta. Una sola pregunta (seguir en la rama actual o crear una nueva, desde el tag de la versión fijada, con el
nombre que dé el usuario); sin respuesta, la rama actual, anotada en "Precondiciones". Los datos son inventados."""
import re
import unittest

from helpers import ROOT, git
from test_perf import perf
from test_perf_0140 import ModulesBase

SKILL_DIR = ROOT / "skills" / "hb-performance"


class BranchQuestionTest(ModulesBase):
    """perf.py da la pregunta y el comando sin inventar el nombre de la rama, y no cambia de rama."""

    def test_pregunta_con_la_rama_actual_y_no_inventa_el_nombre(self):
        git(self.sibling, "tag", "v1.2.0")
        git(self.sibling, "switch", "-q", "-c", "fix/PAY-77-pago-lento")  # la rama que ya tenía el repo
        out = self.register(self.binary, "com.example:modulo-pagos")
        self.assertIn("pregúntale al usuario, en una sola pregunta para todos los repos, si sigue en la rama actual de "
                      "../modulo-pagos (`fix/PAY-77-pago-lento`) o crea una nueva desde el tag de la versión fijada con "
                      "el nombre que él dé (`git -C ../modulo-pagos switch -c <rama que elija el usuario> v1.2.0`; no lo "
                      "inventes)", out)
        self.assertIn("Sin respuesta, sigue en la rama actual, sin crear ni cambiar ramas. Si sigue en la rama actual "
                      "(elegida o sin respuesta) y no está en el tag, anótalo en \"Precondiciones\"", out)
        self.assertNotRegex(out, r"switch -c perf/")
        self.assertEqual(git(self.sibling, "branch", "--show-current").strip(), "fix/PAY-77-pago-lento")
        self.assertFalse(hasattr(perf, "work_branch"))

    def test_dos_modulos_del_mismo_repo_dan_una_sola_pregunta_de_rama(self):
        git(self.sibling, "tag", "v1.2.0")
        (self.sibling / "ui").mkdir()
        item = {"tipo": "binario", "nombre": ":pagos", "artefacto": "com.example:modulo-pagos:1.2.0",
                "carpeta": str(self.sibling)}
        steps = perf.source_steps(self.root, item)
        self.assertEqual(len(steps), 1)
        self.assertIn("switch -c <rama que elija el usuario> v1.2.0", steps[0])
        other = perf.source_steps(self.root, dict(item, nombre=":pagos-ui", carpeta=str(self.sibling / "ui")))
        self.assertEqual(other, steps)  # la misma pregunta: los llamadores la muestran una sola vez

    def test_las_fases_de_0200_se_completan_sin_repetirlas(self):
        """0.21.0 solo cambia cómo se elige la rama: mide igual que 0.20.0."""
        for version in ("0.17.0", "0.20.0", perf.VERSION):
            self.assertTrue(perf.same_capture(version), version)

    def test_la_opcion_de_pasarlo_a_codigo_tampoco_impone_una_rama(self):
        self.assertIn("en la rama que elija el usuario", perf.PASS_TO_SOURCE)
        self.assertNotIn("una rama de trabajo en el repo de la unidad", perf.PASS_TO_SOURCE)


class BranchRuleTextTest(unittest.TestCase):
    """Los textos: la regla de Git y la receta de la sesión 1 dicen lo mismo que hb-implement."""

    def setUp(self):
        self.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.ficha = (SKILL_DIR / "references" / "ficha.md").read_text(encoding="utf-8")

    def test_version(self):
        self.assertRegex(self.skill, r'(?m)^  version: "0\.21\.0"$')

    def test_la_regla_de_git_pregunta_una_vez_y_sin_respuesta_sigue_en_la_actual(self):
        rule = re.search(r"(?m)^10\. \*\*Git:\*\*.*$", self.skill).group(0)
        for phrase in ("**La rama no la creas por tu cuenta:**", "una sola pregunta", "no lo inventes",
                       "Si nadie responde, sigue en la rama actual, sin crear ni cambiar ramas",
                       "commit, push, pull, merge, rebase"):
            self.assertIn(phrase, rule)
        self.assertNotIn("La excepción es la rama de trabajo", rule)

    def test_la_receta_de_la_sesion_1_no_ordena_crear_la_rama(self):
        self.assertNotIn("switch -c perf/<flujo>", self.ficha)
        self.assertNotIn("**Una rama de trabajo desde el tag de la versión fijada**", self.ficha)
        for phrase in ("**La rama, en una sola pregunta**", "<rama que elija el usuario>", "**Si nadie responde**",
                       "Nunca `pull`, `merge` ni `rebase`"):
            self.assertIn(phrase, self.ficha)


if __name__ == "__main__":
    unittest.main()
