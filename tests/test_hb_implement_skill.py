"""hb-implement · los textos. 1.6.0: modelo de estructura y mapa del módulo (párrafos comunes a las skills), flujo por
unidades, DoD por unidad, previews que se omiten fuera de Android y KMP, y la carpeta de la tarea en la base común.
1.7.0: la foto inicial al empezar, --unit en el momento, la rama en una sola pregunta (sin crearla por su cuenta ni
hacer pull) y los datos de análisis que el flujo completa siempre que puede sostenerlos."""
import re
import unittest

from helpers import ROOT

SKILL_DIR = ROOT / "skills" / "hb-implement"
# Párrafos comunes: los mismos, palabra por palabra, en las skills que leen el modelo.
MODEL = (
    "**Modelo de estructura.** Lee `## Estructura` de `AGENTS.md` y, si no existe, `### Repos relacionados` de "
    "`## Arquitectura` (el formato anterior). De ahí salen las unidades (su identificador, dónde está su fuente, cómo se "
    "consume, cómo pasarla a fuente y volver, su DoD, su repo y rama principal, y quién la publica y versiona), las "
    "variantes y entornos, el cliente HTTP, la configuración local modificada a propósito (no es un cambio ajeno, no se "
    "revisa como hallazgo y nunca se propone para commit), la línea `Repos vecinos` y la tabla \"Documentos\": lee solo "
    "los documentos cuya fila \"Léelo cuando…\" corresponde a la tarea, por su ruta exacta. Si lo que encuentras no "
    "coincide con el modelo, dilo en la entrega con la corrección; `hb-implement` y `hb-performance` la aplican en "
    "`## Estructura`, sobre la ruta real de `AGENTS.md` (`realpath AGENTS.md`). Sin modelo, sigue con lo que haya y "
    "ofrece `hb-setup`."
)
MODULE_MAP = (
    "**Mapa del módulo.** Antes de tocar o revisar una unidad, lee su mapa en la carpeta que dice la línea \"Mapas del "
    "módulo\" de `## Estructura` (`<carpeta de contexto>/modules/<identificador>.md`, con las subcarpetas del "
    "identificador). Si su `Commit analizado` no es el `HEAD` del repo de la unidad, mira solo "
    "`git -C <repo> diff <commit>..HEAD -- <ruta de la unidad>`. Si el mapa no existe o quedó atrás, créalo o "
    "actualízalo con lo que ya leíste, en su ruta real: arriba, `Commit analizado: <sha>` y la ruta de la unidad; "
    "después, Qué hace, Puntos de entrada, Flujos principales, Servicios que llama, Datos y persistencia, Patrones y "
    "convenciones, DoD de la unidad y Cuidado con. `hb-review` solo lo lee."
)
NOT_AGNOSTIC = re.compile(r"(?i)dispositivo|compose|gradle")


class TextBase(unittest.TestCase):
    """Los textos de la skill, sin tests propios."""

    def setUp(self):
        self.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.units = (SKILL_DIR / "references" / "unidades.md").read_text(encoding="utf-8")
        self.report = (SKILL_DIR / "references" / "reporte.md").read_text(encoding="utf-8")

    def section(self, title):
        start = self.skill.index(title)
        end = self.skill.find("\n## ", start + 1)
        return self.skill[start:end if end != -1 else len(self.skill)]


class SkillTextTest(TextBase):
    def test_version(self):
        self.assertRegex(self.skill, r'(?m)^  version: "1\.7\.0"$')

    def test_la_seccion_0_trae_los_parrafos_comunes_tal_cual(self):
        context = self.section("## 0. Contexto")
        self.assertIn(MODEL, context)
        self.assertIn(MODULE_MAP, context)

    def test_la_seccion_0_resume_el_flujo_por_unidades_y_enlaza_el_detalle(self):
        context = self.section("## 0. Contexto")
        self.assertIn("](references/unidades.md)", context)
        for phrase in ("entra en el build", "sin preguntar", "**pregunta**", "rama de trabajo",
                       "`sin mecanismo`", "Repos vecinos: no clonar ni crear ramas", "versión que fija la app",
                       "Configuración local modificada a propósito"):
            self.assertIn(phrase, context)
        self.assertNotRegex(context, NOT_AGNOSTIC)

    def test_varios_repos_redirige_a_unidades(self):
        old = (SKILL_DIR / "references" / "varios-repos.md").read_text(encoding="utf-8")
        self.assertEqual(len(old.strip().splitlines()), 1)
        self.assertIn("[unidades.md](unidades.md)", old)
        self.assertNotIn("varios-repos.md", self.skill)

    def test_unidades_cubre_el_flujo_completo_sin_supuestos_de_un_stack(self):
        for phrase in ("Confirma que el código entra en el build", "`git clone <URL> <fuente>`",
                       "**Pregunta**", "**Detente**", "`Repos vecinos: no clonar ni crear ramas`", "**sin preguntar**",
                       "Compila", "**temporal**", "### Sin mecanismo", "llega a la app cuando se publique",
                       "`pinned_version`", "`main_branch`", "`merge-base`", "la misma en cada repo",
                       "DoD de cada unidad que cambiaste", "PR del módulo", "`hb-release`", "PR de bump",
                       "**nunca se commitea**", "`realpath AGENTS.md`"):
            self.assertIn(phrase, self.units)
        self.assertNotRegex(self.units, NOT_AGNOSTIC)

    def test_el_dod_es_el_de_cada_unidad_tocada(self):
        dod = self.section("## 4. Autorrevisión y Definition of Done")
        self.assertIn("el DoD de cada unidad que tocaste", dod)
        self.assertIn('"DoD de la unidad"', dod)

    def test_los_previews_se_omiten_sin_fila_fuera_de_android_y_compose(self):
        previews = self.section("## 5. Previews de UI")
        self.assertIn("`## Stack` dice Android o KMP **y** el cambio toca UI de Compose", previews)
        self.assertIn("sin agregar ninguna fila al DoD del reporte", previews)
        self.assertIn("**Solo si aplica y no se pudo**", previews)
        self.assertIn("-o <la ruta previews: que imprimió report.py --folder>", previews)
        self.assertNotIn("reports/previews", self.skill)
        self.assertIn('"image": "<la ruta previews: que imprimió report.py --folder>/', self.skill)

    def test_el_reporte_va_a_la_carpeta_de_la_tarea_con_indice_y_base_por_repo(self):
        report = self.section("## 6. Reporte HTML")
        for phrase in ("<base>/implementation/<fecha>-<slug>/", "<base>/INDEX.md", "**Usa esas rutas tal cual.**",
                       "formato plano", "--main-branch", "`merge-base`", "`ln -s`"):
            self.assertIn(phrase, report)
        for phrase in ("   previews: <ruta>", "   índice: <ruta de INDEX.md>", "| Fecha | Skill | Slug | Tipo | Estado |",
                       '"pinned_version"', '"source_version"', '"main_branch"'):
            self.assertIn(phrase, self.report)

    def test_la_entrega_trae_el_orden_de_integracion_y_la_rama_de_cada_repo(self):
        delivery = self.section("## 7. Entrega")
        self.assertIn("PR del módulo → release del módulo (con `hb-release` en su repo) → PR de bump", delivery)
        self.assertIn("**rama de trabajo** de cada repo", delivery)
        self.assertIn("nunca se commitea", delivery)

    def test_el_checklist_esta_al_dia(self):
        checklist = self.section("## Checklist")
        for phrase in ("modelo de estructura", "mapa del módulo", "rama de trabajo", "DoD de cada unidad tocada",
                       "sin fila en el DoD", "índice", "PR del módulo → release → bump", "`report.py --folder`",
                       "`--unit`", "una sola pregunta", "nunca un reporte vacío", "Datos de análisis completos"):
            self.assertIn(phrase, checklist)


class BranchRuleTest(TextBase):
    """1.7.0, punto 8: hb-implement ya no crea ramas por su cuenta ni hace pull para preparar la rama."""

    def test_el_flujo_ya_no_ordena_crear_ramas_sin_preguntar(self):
        for text in (self.skill, self.units):
            for order in ("Crea la **rama de trabajo**", "crea la rama de trabajo desde", "`pull --ff-only`",
                          "`git pull", "Si el repo ya está en una rama que no es la principal, sigue en ella",
                          "si ya estás en una rama que no es la principal, sigue en ella"):
                self.assertNotIn(order, text)
        self.assertNotRegex(self.skill + self.units, r"(?i)<tipo>/<slug>")  # la IA no inventa el nombre

    def test_una_sola_pregunta_y_sin_respuesta_la_rama_actual(self):
        context = self.section("## 0. Contexto")
        for phrase in ("**La rama de trabajo, en una sola pregunta**", "(a) seguir en esa rama", "(b) crear una rama "
                       "nueva con el nombre que dé el usuario", "no lo inventes", "si elige (b) sin dar el nombre, "
                       "pregúntaselo", "**Si nadie responde**", "sigue en la rama actual de cada repo, sin crear ni "
                       "cambiar ramas, y dilo en la entrega y en el reporte (`branch_note`)",
                       "Nunca hagas `pull`, `merge` ni `rebase` para preparar la rama"):
            self.assertIn(phrase, context)
        branch = self.units[self.units.index("## 5. Rama de trabajo"):self.units.index("## 6.")]
        for phrase in ("no crea ramas por su cuenta", "**una sola pregunta**", "**no los inventes**",
                       "**Si nadie responde**", "**Nunca** hagas `pull`, `merge` ni `rebase`", "`branch_note`"):
            self.assertIn(phrase, branch)
        self.assertIn("si nadie respondió, la actual de cada uno", self.section("## 7. Entrega"))


class CoverageFlowTest(TextBase):
    """1.7.0, puntos 1, 2, 4 y 9: el flujo pide la foto al empezar, registra cada unidad en el momento, no entrega un
    reporte vacío y completa los datos de análisis."""

    def test_la_foto_se_pide_antes_de_cambiar_nada(self):
        context = self.section("## 0. Contexto")
        step = context[context.index("7. **Antes de cambiar nada**"):context.index("8. **Unidades**")]
        self.assertIn("`report.py --folder <slug>`", step)
        self.assertIn("**foto inicial**", step)
        self.assertIn("   foto inicial: <ruta de snapshot.json>", self.report)

    def test_cada_unidad_se_registra_al_pasarla_a_fuente_y_al_correr_su_dod(self):
        command = "report.py --unit <su fuente> --folder <slug>"
        self.assertIn("En cuanto la pasas a fuente, **regístrala**: `%s`" % command, self.section("## 0. Contexto"))
        self.assertIn("Antes de correr el DoD de una unidad de otro repo, regístrala",
                      self.section("## 4. Autorrevisión y Definition of Done"))
        self.assertIn(command, self.section("## 4. Autorrevisión y Definition of Done"))
        self.assertIn("2. **Regístrala en ese momento**", self.units)
        self.assertIn("Antes de correr el DoD de una unidad, regístrala", self.units)
        report = self.section("## 6. Reporte HTML")
        self.assertIn("python3 -I <carpeta-de-la-skill>/scripts/report.py --unit <ruta> --folder <slug>", report)
        self.assertIn("**conserva `repos`**", report)

    def test_otros_repos_y_reporte_vacio(self):
        report = self.section("## 6. Reporte HTML")
        for phrase in ("**Otros repos que cambiaron:**", "pregúntale al usuario si es de la tarea",
                       "**Sin archivos de la tarea no hay reporte:**", "`--ignore-snapshot`",
                       "**posible migración de lenguaje**"):
            self.assertIn(phrase, report)
        for phrase in ("## Foto inicial: `snapshot.json`", "## Registrar una unidad: `--unit`", "## Qué entra al reporte",
                       "## Sin reportes vacíos", "## Aviso de migración de lenguaje", "**Tema claro y oscuro:**",
                       "Cambios no atribuidos"):
            self.assertIn(phrase, self.report)

    def test_los_datos_de_analisis_se_completan_siempre_que_se_puedan_sostener(self):
        report = self.section("## 6. Reporte HTML")
        self.assertIn("**Datos de análisis: complétalos siempre que puedas sostenerlos con lo que viste en el código.**",
                      report)
        for field in ("`why`", "`risk`", "`pros`", "`cons`", "`layer`", "`diagrams`", "`impact`", "`severity`",
                      "`root_cause`", "`ticket`"):
            self.assertIn(field, report)
        self.assertIn("**los completa siempre que pueda sostenerlos con lo que vio en el código**", self.report)
        for old in ("Todo es opcional", "Úsalo cuando ayude", "**Análisis del cambio**, opcional",
                    "termina con un error claro y sin escribir el reporte"):
            self.assertNotIn(old, self.skill + self.report)
        # ausente no es lo mismo que vacío: "cons": [] dice que se analizó y no hubo contras
        self.assertIn('`"cons": []`', report)
        self.assertIn("**Ausente no es lo mismo que vacío en `cons`.**", self.report)
        self.assertIn('"Sin contras identificados"', self.report)
        for field in ("| `layer` | Por archivo |", "| `ticket` | Reporte |", "se ignora con un aviso en la salida"):
            self.assertIn(field, self.report)


if __name__ == "__main__":
    unittest.main()
