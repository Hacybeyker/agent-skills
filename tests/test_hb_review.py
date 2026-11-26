"""hb-review: qué revisa (cada repo de la tarea contra su base, con los archivos nuevos que todavía no están en git),
el modelo de estructura común, el DoD por unidad y dónde guarda su reporte."""
import os
import pathlib
import re
import shlex
import tempfile
import unittest

from helpers import ROOT, commit_all, git, init_repo, run, write

SKILL = ROOT / "skills" / "hb-review" / "SKILL.md"
SAVED = ROOT / "skills" / "hb-review" / "references" / "donde-se-guarda.md"
UNTRACKED = "git ls-files --others --exclude-standard"

# Los párrafos comunes del contrato de estructura: van idénticos en las skills que leen el modelo (el del modelo, en
# hb-implement, hb-performance, hb-review, hb-commit y hb-release; el del mapa, en las tres primeras).
MODEL_PARAGRAPH = (
    '**Modelo de estructura.** Lee `## Estructura` de `AGENTS.md` y, si no existe, `### Repos '
    'relacionados` de `## Arquitectura` (el formato anterior). De ahí salen las unidades (su '
    'identificador, dónde está su fuente, cómo se consume, cómo pasarla a fuente y volver, su DoD, su '
    'repo y rama principal, y quién la publica y versiona), las variantes y entornos, el cliente HTTP, la '
    'configuración local modificada a propósito (no es un cambio ajeno, no se revisa como hallazgo y '
    'nunca se propone para commit), la línea `Repos vecinos` y la tabla "Documentos": lee solo los '
    'documentos cuya fila "Léelo cuando…" corresponde a la tarea, por su ruta exacta. Si lo que '
    'encuentras no coincide con el modelo, dilo en la entrega con la corrección; `hb-implement` y '
    '`hb-performance` la aplican en `## Estructura`, sobre la ruta real de `AGENTS.md` (`realpath '
    'AGENTS.md`). Sin modelo, sigue con lo que haya y ofrece `hb-setup`.'
)

MAP_PARAGRAPH = (
    '**Mapa del módulo.** Antes de tocar o revisar una unidad, lee su mapa en la carpeta que dice la '
    'línea "Mapas del módulo" de `## Estructura` (`<carpeta de contexto>/modules/<identificador>.md`, con '
    'las subcarpetas del identificador). Si su `Commit analizado` no es el `HEAD` del repo de la unidad, '
    'mira solo `git -C <repo> diff <commit>..HEAD -- <ruta de la unidad>`. Si el mapa no existe o quedó '
    'atrás, créalo o actualízalo con lo que ya leíste, en su ruta real: arriba, `Commit analizado: <sha>` '
    'y la ruta de la unidad; después, Qué hace, Puntos de entrada, Flujos principales, Servicios que '
    'llama, Datos y persistencia, Patrones y convenciones, DoD de la unidad y Cuidado con. `hb-review` '
    'solo lo lee.'
)

INDEX_HEADER = (
    "# Índice de reportes\n"
    "\n"
    "Una fila por tarea. Cada skill agrega o actualiza solo sus filas (clave: Skill + Slug).\n"
    "\n"
    "| Fecha | Skill | Slug | Tipo | Estado | Ruta |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)


def section(text, start, end=None):
    first = text.index(start)
    return text[first:text.index(end, first) if end else len(text)]


def common_paragraph(text, title):
    """El párrafo común que empieza con `title`, sin la sangría, la viñeta o el `> ` que lo precedan. Falla si no está
    o si aparece más de una vez."""
    lines = [line for line in text.splitlines() if title in line]
    if len(lines) != 1:
        raise AssertionError("%s aparece %d veces" % (title, len(lines)))
    return lines[0][lines[0].index(title):].rstrip()


def command(text, prefix):
    """El único comando entre acentos graves que empieza con `prefix`."""
    found = sorted(set(re.findall(r"`(%s[^`]*)`" % re.escape(prefix), text)))
    if len(found) != 1:
        raise AssertionError("se esperaba un comando %r y hay %r" % (prefix, found))
    return found[0]


class UntrackedFilesTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_el_alcance_por_defecto_suma_los_archivos_sin_trackear(self):
        scope = section(self.text, "## 1. Alcance y contexto", "## 2. Qué revisar")
        self.assertIn("`%s`" % UNTRACKED, scope)
        self.assertIn("léelos completos", scope)

    def test_el_modo_rapido_suma_los_archivos_sin_trackear(self):
        quick = section(self.text, "## Modo rápido")
        self.assertIn("`%s`" % UNTRACKED, quick)
        self.assertIn("completos", quick[quick.index(UNTRACKED):])

    def test_el_comando_que_cita_lista_lo_que_git_diff_no_muestra(self):
        commands = set(re.findall(r"`(git ls-files [^`]+)`", self.text))
        self.assertEqual(commands, {UNTRACKED})
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(pathlib.Path(tmp))
            write(repo / "Viejo.kt", "class Viejo\n")
            write(repo / ".gitignore", "build/\n")
            commit_all(repo)
            write(repo / "Viejo.kt", "class Viejo { val x = 1 }\n")
            write(repo / "feature/Nuevo.kt", "class Nuevo\n")
            write(repo / "build/Generado.kt", "class Generado\n")
            diff = git(repo, "diff", "HEAD", "--name-only").split()
            untracked = run(shlex.split(UNTRACKED), repo).stdout.split()
        self.assertEqual(diff, ["Viejo.kt"])  # la clase nueva no aparece en el diff
        self.assertEqual(untracked, ["feature/Nuevo.kt"])  # y el comando sí la lista, sin lo ignorado


class StructureModelTest(unittest.TestCase):
    """Con el modelo de estructura revisa cada repo de la tarea, sin la configuración local ni los temporales."""

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.scope = section(self.text, "## 1. Alcance y contexto", "## 2. Qué revisar")

    def test_el_contexto_trae_el_parrafo_comun_del_modelo(self):
        self.assertEqual(common_paragraph(self.scope, "**Modelo de estructura.**"), MODEL_PARAGRAPH)

    def test_el_contexto_trae_el_parrafo_comun_del_mapa_y_solo_lo_lee(self):
        self.assertEqual(common_paragraph(self.scope, "**Mapa del módulo.**"), MAP_PARAGRAPH)
        self.assertIn("no lo escribas", self.scope)

    def test_revisa_cada_repo_de_la_tarea_contra_su_merge_base(self):
        self.assertIn("cada repo de la tarea", self.scope)
        self.assertIn("Repo y rama principal", self.scope)
        self.assertIn("Si revisas una tarea de `hb-implement`, los que dice su atribución", self.scope)

    def test_la_configuracion_local_y_los_temporales_no_son_hallazgo(self):
        self.assertIn("configuración local modificada a propósito", self.scope)
        self.assertIn("`temporary` del meta de `hb-implement`", self.scope)
        self.assertIn("`<base>/implementation/<fecha>-<slug>/meta.json`", self.scope)
        self.assertIn("No son hallazgo ni cambio ajeno", self.scope)
        quick = section(self.text, "## Modo rápido")
        self.assertIn("configuración local modificada a propósito", quick)
        self.assertIn("cambios temporales", quick)

    def test_los_comandos_que_cita_cubren_la_rama_y_dejan_fuera_la_configuracion_local(self):
        merge_base = command(self.scope, "git -C <repo> merge-base")
        diff = command(self.scope, "git -C <repo> diff <base de comparación>")
        excluded = command(self.scope, "git diff <base de comparación> -- ")
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(pathlib.Path(tmp))
            write(repo / "Pago.kt", "class Pago\n")
            write(repo / "local-modules.json", '{"core-lib": false}\n')
            commit_all(repo)
            git(repo, "checkout", "-q", "-b", "feat/reintentos")
            write(repo / "Reintento.kt", "class Reintento\n")
            commit_all(repo, "ya commiteado en la rama")
            write(repo / "Pago.kt", "class Pago { val reintentos = 3 }\n")
            write(repo / "local-modules.json", '{"core-lib": true}\n')

            def run_cited(template, **values):
                for name, value in values.items():
                    template = template.replace("<%s>" % name, value)
                result = run(shlex.split(template), repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            base = run_cited(merge_base, repo=".", **{"rama principal": "main"}).strip()
            changed = run_cited(diff + " --name-only", repo=".", **{"base de comparación": base}).split()
            reviewed = run_cited(excluded.replace(" -- ", " --name-only -- "),
                                 **{"base de comparación": base, "ruta": "local-modules.json"}).split()
            only_uncommitted = git(repo, "diff", "HEAD", "--name-only").split()
        self.assertEqual(only_uncommitted, ["Pago.kt", "local-modules.json"])  # git diff HEAD no ve lo commiteado
        self.assertEqual(changed, ["Pago.kt", "Reintento.kt", "local-modules.json"])  # contra la base, toda la rama
        self.assertEqual(reviewed, ["Pago.kt", "Reintento.kt"])  # sin la configuración local

    def test_corre_el_dod_de_cada_unidad_tocada(self):
        verification = section(self.text, "## 3. Verificación automática", "## 4. Reporte")
        self.assertIn("cada unidad que toca el cambio", verification)
        self.assertIn('"DoD de la unidad"', verification)
        self.assertIn("el `## DoD` del `AGENTS.md` del repo de la unidad", verification)
        self.assertIn("lo salta siempre", verification)


class SavedReviewTest(unittest.TestCase):
    """El reporte va a <base>/review/<fecha>-<slug>/review.md, con su fila en <base>/INDEX.md, fuera de git."""

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.saved = SAVED.read_text(encoding="utf-8")

    def test_la_skill_dice_donde_se_guarda_y_enlaza_el_detalle(self):
        report = section(self.text, "## 4. Reporte", "## 5. Después del review")
        for expected in ("`<base>/review/<fecha>-<slug>/review.md`", "`<base>/INDEX.md`", "`Carpeta de reportes:`",
                         "`reports`", "Skill `hb-review`", "`review rápido`", "`aprobado`", "`cambios requeridos`",
                         "`.git/info/exclude`", "nunca a `.gitignore`", "`realpath`",
                         "(references/donde-se-guarda.md)"):
            self.assertIn(expected, report)

    def test_escribir_su_reporte_no_es_modificar_codigo(self):
        after = section(self.text, "## 5. Después del review", "## Modo rápido")
        self.assertIn("**no modifica código**", after)
        self.assertIn("no es modificar código", after)

    def test_en_el_modo_rapido_el_archivo_es_opcional(self):
        quick = section(self.text, "## Modo rápido")
        self.assertIn("**El archivo es opcional:**", quick)
        self.assertIn("solo si el orquestador lo pide", quick)
        self.assertIn("`review rápido`", quick)

    def test_el_indice_de_ejemplo_tiene_el_encabezado_del_contrato_y_una_fila_valida(self):
        self.assertIn(INDEX_HEADER, self.saved)
        rows = [line for line in self.saved.splitlines() if line.startswith("| ") and "| hb-review |" in line]
        self.assertEqual(len(rows), 1)
        cells = [cell.strip() for cell in rows[0].strip("|").split(" | ")]
        self.assertEqual(len(cells), 6)
        date, skill, slug, kind, state, link = cells
        self.assertRegex(date, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(skill, "hb-review")
        self.assertIn(kind, ("review", "review rápido"))
        self.assertIn(state, ("aprobado", "cambios requeridos"))
        target = "review/%s-%s/review.md" % (date, slug)
        self.assertEqual(link, "[%s](%s)" % (target, target))  # relativo a la carpeta de INDEX.md

    def test_la_plantilla_de_review_trae_alcance_dod_hallazgos_y_veredicto(self):
        template = section(self.saved, "```markdown\n# Review:", "\n```\n")
        headings = re.findall(r"^## (.+)$", template, re.M)
        self.assertEqual(headings, ["Alcance", "DoD", "Hallazgos", "Veredicto"])

    def test_la_exclusion_que_describe_deja_el_reporte_fuera_de_git_tambien_en_un_worktree(self):
        self.assertIn("`git rev-parse --git-path info/exclude`", self.saved)
        self.assertIn("`git check-ignore -q contexto`", self.saved)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            repos = []
            for name in ("app-shell", "core-lib"):
                (tmp / name).mkdir()
                repos.append(init_repo(tmp / name))
                write(repos[-1] / "README.md", "%s\n" % name)
                commit_all(repos[-1])
            repo = repos[0]
            # info/exclude es común a los worktrees de un repo: el segundo caso usa un worktree de otro repo.
            git(repos[1], "worktree", "add", "-q", str(tmp / "worktree"))
            outside = tmp / "contexto-real"
            outside.mkdir()
            for checkout in (repo, tmp / "worktree"):
                review = checkout / "reports" / "review" / "2026-11-25-payments-retry" / "review.md"
                write(review, "# Review\n")
                relative = review.relative_to(checkout).as_posix()
                self.assertEqual(run(["git", "check-ignore", "-q", relative], checkout).returncode, 1)
                exclude = pathlib.Path(git(checkout, "rev-parse", "--git-path", "info/exclude").strip())
                exclude = exclude if exclude.is_absolute() else checkout / exclude
                with exclude.open("a", encoding="utf-8") as handle:
                    handle.write("/reports/\n")
                self.assertEqual(run(["git", "check-ignore", "-q", relative], checkout).returncode, 0)
                self.assertEqual(git(checkout, "status", "--porcelain"), "")
            # A través de un enlace simbólico git no mira dentro: por eso se comprueba el enlace mismo.
            os.symlink(str(outside), str(repo / "contexto"))
            write(repo / "contexto" / "reports" / "review" / "2026-11-25-x" / "review.md", "# Review\n")
            inside = run(["git", "check-ignore", "-q", "contexto/reports/review/2026-11-25-x/review.md"], repo)
            self.assertNotIn(inside.returncode, (0, 1))
            self.assertEqual(run(["git", "check-ignore", "-q", "contexto"], repo).returncode, 1)


class AttributionTest(unittest.TestCase):
    """1.3.0: al revisar una tarea de hb-implement, solo lo que es de la tarea, según su atribución."""

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.reference = (SKILL.parent / "references" / "atribucion.md").read_text(encoding="utf-8")
        self.scope = section(self.text, "## 1. Alcance y contexto", "## 2. Qué revisar")

    def test_version(self):
        self.assertRegex(self.text, r'(?m)^  version: "1\.3\.0"$')

    def test_usa_la_atribucion_del_script_de_hb_implement(self):
        command = "<carpeta de hb-implement>/scripts/report.py --meta <carpeta de la tarea>/meta.json --attribution " \
                  "[--base <ref> | --main-branch <rama>]"
        self.assertIn(command, self.scope)
        self.assertIn(command, self.reference)
        self.assertIn("junto a esta skill (`<carpeta-de-esta-skill>/../hb-implement`)", self.scope)
        self.assertIn("`~/.claude/skills/hb-implement`, `~/.agents/skills/hb-implement`", self.scope)
        script = SKILL.parent / ".." / "hb-implement" / "scripts" / "report.py"
        self.assertTrue(script.resolve().is_file())  # instaladas una al lado de la otra, como en el repo
        self.assertIn('"--attribution"', script.read_text(encoding="utf-8"))
        self.assertIn("`--base` si `AGENTS.md` fija una", self.scope)

    def test_elige_la_tarea_sin_adivinar(self):
        self.assertIn("cuando el usuario o el orquestador nombran la tarea", self.scope)
        self.assertIn("cuya foto (`snapshot.json`, en su carpeta) tiene en el repo principal la rama actual", self.scope)
        self.assertIn("con varias, o sin forma de saberlo, pregunta cuál", self.scope)
        self.assertIn("`<base>/` más la carpeta de la columna Ruta de esa fila", self.scope)

    def test_lo_que_ya_estaba_no_es_hallazgo(self):
        self.assertIn("**No es hallazgo de la tarea:**", self.scope)
        self.assertIn("avísalo para que no se commitee con ella", self.scope)
        self.assertIn("\"entra al PR sin revisar\"", self.scope)
        for field in ("`photo`", "`repos[]`", "`unattributed[]`", "`excluded[]`", "`skipped[]`", "`others[]`",
                      "`empty`", "`task_diff_from`", "`repos[].path`", "`untracked`", "`repo_path`"):
            self.assertIn(field, self.reference)
        self.assertIn("git -C <repo> diff -M <task_diff_from> -- <ruta>", self.scope)
        self.assertIn("pregúntalo con `question`", self.scope)
        self.assertIn("salvo los cambios de la tarea que el archivo traiga además del temporal", self.scope)
        self.assertIn("**`empty`** (solo con foto", self.scope)
        self.assertNotIn("corre de nuevo con `--ignore-snapshot`", self.scope + self.reference)
        self.assertIn("pregunta con `question` si son de la tarea", self.scope)

    def test_sin_foto_sin_nada_o_sin_hb_implement(self):
        self.assertIn("**Sin foto** (`photo: false`", self.scope)
        self.assertIn("`repos` y `unattributed` no separan nada. Revisa como sin tarea", self.scope)
        self.assertIn("Sin nada revisado no hay veredicto ✅", self.scope)
        self.assertIn("Sin ningún archivo revisado no hay aprobación", self.text)
        self.assertIn("Si el script falla, no está o es anterior a 1.8.0", self.scope)

    def test_el_modo_rapido_tambien_la_usa_si_tiene_la_carpeta(self):
        quick = section(self.text, "## Modo rápido (para orquestadores)", None)
        self.assertIn("Si el orquestador te pasa la carpeta de la tarea de `hb-implement`, usa su atribución", quick)


if __name__ == "__main__":
    unittest.main()
