"""hb-commit: lee el modelo de estructura común, commitea por repo sin la configuración local ni los temporales de la
tarea, y ordena los PR entre repos (módulo, release, bump en la app)."""
import pathlib
import shlex
import tempfile
import unittest

from helpers import ROOT, commit_all, git, init_repo, run, write
from test_hb_review import MODEL_PARAGRAPH, common_paragraph, section

SKILL = ROOT / "skills" / "hb-commit" / "SKILL.md"
STAGED = "git diff --staged --name-only"


class StructureModelTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.rules = section(self.text, "## 1. Lee las reglas del proyecto", "## 2. Formato del mensaje")
        self.commit = section(self.text, "## 3. Hacer el commit", "## 4. Entrada en `[Unreleased]`")
        self.push = section(self.text, "## 5. Push y pull request", "## 6. Limpiar ramas")

    def test_las_reglas_traen_el_parrafo_comun_del_modelo(self):
        self.assertEqual(common_paragraph(self.rules, "**Modelo de estructura.**"), MODEL_PARAGRAPH)

    def test_junta_los_repos_de_la_tarea_y_lo_que_nunca_entra(self):
        self.assertIn("**Los repos de la tarea:**", self.rules)
        self.assertIn("**Lo que nunca entra en un commit**", self.rules)
        self.assertIn("configuración local modificada a propósito", self.rules)
        self.assertIn("`temporary` del meta de `hb-implement`", self.rules)
        self.assertIn("`<base>/implementation/<fecha>-<slug>/meta.json`", self.rules)
        self.assertIn("No son cambios ajenos", self.rules)

    def test_commitea_por_repo_y_nunca_agrega_la_configuracion_local_ni_los_temporales(self):
        self.assertIn("**cada repo de la tarea**", self.commit)
        self.assertIn("**Cada repo lleva sus propios commits:**", self.commit)
        never = self.commit[self.commit.index("**Nunca**"):]
        self.assertIn("la configuración local modificada a propósito ni los cambios temporales", never)
        for blind in ("`git add -A`", "`git add .`", "`git commit -a`"):
            self.assertIn(blind, never)
        self.assertIn("`%s`" % STAGED, never)

    def test_la_comprobacion_que_cita_ve_la_configuracion_local_si_se_agrego_por_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(pathlib.Path(tmp))
            write(repo / "Pago.kt", "class Pago\n")
            write(repo / "local-modules.json", '{"core-lib": false}\n')
            commit_all(repo)
            write(repo / "Pago.kt", "class Pago { val reintentos = 3 }\n")
            write(repo / "local-modules.json", '{"core-lib": true}\n')
            git(repo, "add", "-A")  # lo que la skill prohíbe sin revisar
            blind = run(shlex.split(STAGED), repo).stdout.split()
            git(repo, "reset", "-q")
            git(repo, "add", "Pago.kt")  # archivos concretos
            careful = run(shlex.split(STAGED), repo).stdout.split()
        self.assertEqual(blind, ["Pago.kt", "local-modules.json"])
        self.assertEqual(careful, ["Pago.kt"])

    def test_las_ramas_siguen_git_y_la_linea_de_repos_vecinos(self):
        self.assertIn("**Rama:** la convención de `## Git`", self.push)
        self.assertIn("la misma rama en cada repo que la tarea modifica", self.push)
        self.assertIn("`Repos vecinos: no clonar ni crear ramas`", self.push)
        self.assertIn("no crees ninguna en ningún repo de la tarea", self.push)

    def test_los_pr_entre_repos_van_en_orden_modulo_release_bump(self):
        order = section(self.push, "### Varios repos")
        steps = ["**PR del módulo**", "**Release del módulo**", "**PR de bump en la app:**"]
        positions = [order.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("con `hb-release` en su repo", order)
        self.assertIn("**La configuración que pasa a fuente no se commitea**", order)


class BranchRuleTest(unittest.TestCase):
    """1.1.1: ninguna skill crea una rama por su cuenta ni inventa su nombre; hb-commit la propone con el push."""

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.push = section(self.text, "## 5. Push y pull request", "## 6. Limpiar ramas")

    def test_version(self):
        self.assertRegex(self.text, r'(?m)^  version: "1\.2\.0"$')

    def test_propone_la_rama_y_la_crea_solo_con_confirmacion(self):
        self.assertIn("en la misma confirmación del push, y créala solo cuando el usuario la confirme o te dé el nombre",
                      self.push)
        self.assertIn("El código de la tarea no lo inventes", self.push)
        self.assertIn("la que eligió el usuario al empezar con `hb-implement`", self.push)
        self.assertNotIn("la que creó `hb-implement`", self.push)
        self.assertIn("si fija un formato de nombre, manda sobre el de aquí", self.push)
        self.assertIn("la rama nueva se confirma igual", self.push)


class AttributionTest(unittest.TestCase):
    """1.2.0: los repos y los archivos de la tarea salen de la misma atribución que usa hb-review."""

    def setUp(self):
        self.rules = section(SKILL.read_text(encoding="utf-8"), "## 1. Lee las reglas del proyecto",
                             "## 2. Formato del mensaje")

    def test_usa_la_atribucion_de_hb_implement(self):
        self.assertIn("report.py --meta <carpeta de la tarea>/meta.json --attribution", self.rules)
        self.assertIn("la misma que usa `hb-review`", self.rules)
        self.assertIn("los de `repos` en su meta y cada unidad del modelo con cambios", self.rules)

    def test_lo_que_ya_estaba_sin_commit_no_entra_con_la_tarea(self):
        self.assertIn('lo de `unattributed` con el motivo "sin commit desde antes de la tarea"', self.rules)
        self.assertIn("no lo commitees con ella salvo que el usuario lo pida; pregúntale", self.rules)
        self.assertIn("en un archivo `mixed`", self.rules)
        self.assertIn("no lo agregues entero", self.rules)
        self.assertIn("los repos de `others`", self.rules)

    def test_la_atribucion_con_su_base_y_la_ubicacion_del_script(self):
        self.assertIn("cd <raíz-del-proyecto> && python3 -I <carpeta de hb-implement>/scripts/report.py", self.rules)
        self.assertIn("[--base <ref> | --main-branch <rama>]", self.rules)
        self.assertIn("`<carpeta-de-esta-skill>/../hb-implement`", self.rules)
        self.assertIn("sin foto (`photo: false`)", self.rules)

    def test_lo_que_nunca_entra_no_mezcla_lo_ajeno(self):
        never = self.rules.split("- **Lo que nunca entra en un commit**", 1)[1]
        self.assertNotIn("unattributed", never)  # lo ajeno se pregunta; esto otro no es ajeno


if __name__ == "__main__":
    unittest.main()
