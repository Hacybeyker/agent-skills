"""hb-release: lee el modelo de estructura común, toma de él qué unidad se publica y quién la publica, y al terminar
propone el bump de la versión fijada en quien la consume, sin tocar la configuración local."""
import unittest

from helpers import ROOT
from test_hb_review import MODEL_PARAGRAPH, common_paragraph, section

SKILL = ROOT / "skills" / "hb-release" / "SKILL.md"


class StructureModelTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.rules = section(self.text, "## 1. Lee las reglas del proyecto", "## 2. Junta la información")

    def test_las_reglas_traen_el_parrafo_comun_del_modelo(self):
        self.assertEqual(common_paragraph(self.rules, "**Modelo de estructura.**"), MODEL_PARAGRAPH)

    def test_toma_del_modelo_que_unidad_publica_donde_vive_su_version_y_quien_la_publica(self):
        unit = section(self.rules, "### Qué unidad publicas")
        for expected in ("**Cuál:**", "**Dónde se corta:**", '"Repo y rama principal"',
                         '**Quién la publica y versiona** ("Publica y versiona")', "**Dónde vive su versión:**",
                         "`con la app`", "`el workflow <nombre> al crear el tag`", "No lo reemplaces"):
            self.assertIn(expected, unit)

    def test_el_commit_del_release_no_lleva_la_configuracion_local_ni_los_temporales(self):
        commit = section(self.text, "## 6. Commit y tag", "## 7. Publica")
        self.assertIn("nunca la configuración local modificada a propósito ni los cambios temporales", commit)

    def test_propone_el_bump_en_los_consumidores_sin_tocar_la_configuracion_local(self):
        bump = section(self.text, "## 9. Bump en los consumidores", "## Al terminar")
        self.assertIn("**propón** subir la versión fijada en cada unidad que la consume", bump)
        self.assertIn('"Cómo se consume"', bump)
        self.assertIn("Nunca la configuración local de sustitución", bump)
        self.assertIn("Hazlo solo con confirmación", bump)
        self.assertIn("`hb-commit`", bump)
        closing = section(self.text, "## Al terminar", "## Seguridad")
        self.assertIn("el bump propuesto en cada consumidor", closing)


if __name__ == "__main__":
    unittest.main()
