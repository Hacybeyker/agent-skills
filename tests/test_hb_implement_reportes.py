"""hb-implement 1.6.0 · report.py: carpeta por tarea bajo la base común, compatibilidad con el formato plano, INDEX.md,
base de comparación por repo (merge-base con la rama principal), versiones fijada y del fuente, carpeta de contexto
enlazada (escritura sobre la ruta real y rutas relativas) y worktrees a los que les faltan los enlaces."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, run, write

SCRIPT = ROOT / "skills" / "hb-implement" / "scripts" / "report.py"
META = {
    "title": "Prueba x",
    "type": "bugfix",
    "date": "2026-01-02",
    "description": "Descripción",
    "files": {"a.txt": {"why": "x"}, "b.txt": {"why": "y"}},
    "dod": [{"name": "Tests", "command": "make test", "status": "pass"}],
}
HEADER = ("# Índice de reportes\n\n"
          "Una fila por tarea. Cada skill agrega o actualiza solo sus filas (clave: Skill + Slug).\n\n"
          "| Fecha | Skill | Slug | Tipo | Estado | Ruta |\n"
          "| --- | --- | --- | --- | --- | --- |\n")
PNG = b"\x89PNG\r\n\x1a\nfalso"


class Base(unittest.TestCase):
    """Un repo con un archivo modificado y uno nuevo, y el meta fuera del repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(os.path.realpath(self.tmp.name))
        self.repo = init_repo(self.mkdir("app-shell"))
        write(self.repo / "a.txt", "uno\n")
        commit_all(self.repo, "base")
        write(self.repo / "a.txt", "dos\n")
        write(self.repo / "b.txt", "nuevo\n")
        self.meta = self.base / "meta.json"
        self.with_meta()

    def tearDown(self):
        self.tmp.cleanup()

    def mkdir(self, name):
        path = self.base / name
        path.mkdir(parents=True)
        return path

    def with_meta(self, path=None, **extra):
        meta = dict(META)
        meta.update(extra)
        write(path or self.meta, json.dumps(meta))

    def agents(self, line, repo=None):
        """Commitea solo el AGENTS.md: los cambios de la tarea siguen pendientes."""
        repo = repo or self.repo
        write(repo / "AGENTS.md", "# Proyecto\n\n## Reglas del proyecto\n\n%s\n" % line)
        git(repo, "add", "AGENTS.md")
        git(repo, "commit", "-q", "-m", "agents")

    def generate(self, *extra, meta=None, repo=None):
        repo = repo or self.repo
        return run([sys.executable, "-I", SCRIPT, "--meta", meta or self.meta, "--repo", repo, *extra], repo)

    def ok(self, *extra, meta=None, repo=None):
        result = self.generate(*extra, meta=meta, repo=repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def folder(self, *extra, repo=None):
        repo = repo or self.repo
        return run([sys.executable, "-I", SCRIPT, "--repo", repo, "--folder", *extra], repo)

    def folder_ok(self, *extra, repo=None):
        result = self.folder(*extra, repo=repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def printed(self, result, label):
        """La ruta que --folder imprimió en la línea "<label>: <ruta>"."""
        return re.search(r"^\s*%s: (.+)$" % re.escape(label), result.stdout, re.M).group(1).split(" (")[0]

    def index(self, folder=None):
        return ((folder or self.repo / "reports") / "INDEX.md").read_text(encoding="utf-8")

    def rows(self, text):
        return [line for line in text.splitlines() if line.startswith("| ") and "hb-" in line]

    def stat(self, html, label):
        return re.search(r"%s</div><div class=\"stat-value[^\"]*\"[^>]*>([^<]+)<" % label, html).group(1)


class TaskFolderTest(Base):
    """Sin marcadores, la línea es la base: la tarea va en <base>/implementation/<fecha>-<slug>/."""

    def test_folder_y_reporte_quedan_juntos_en_la_carpeta_de_la_tarea(self):
        result = self.folder_ok("prueba-x", "--date", "2026-01-02")
        task = self.repo / "reports" / "implementation" / "2026-01-02-prueba-x"
        self.assertEqual(self.printed(result, "meta"), "reports/implementation/2026-01-02-prueba-x/meta.json")
        self.with_meta(task / "meta.json")
        generated = self.ok(meta=task / "meta.json")
        self.assertIn("reports/implementation/2026-01-02-prueba-x/report.html", generated.stdout)
        html = (task / "report.html").read_text(encoding="utf-8")
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "1")  # b.txt: ni el meta ni el índice cuentan
        self.assertNotIn("el meta va en", generated.stderr)
        self.assertEqual(sorted(p.name for p in (self.repo / "reports").iterdir()), ["INDEX.md", "implementation"])

    def test_la_tarea_vieja_en_formato_plano_se_retoma_plana(self):
        write(self.repo / "reports" / "2026-01-01-pagos.meta.json", json.dumps(dict(META, slug="pagos")))
        write(self.repo / "reports" / "2026-01-01-otra.meta.json", "{}")
        result = self.folder_ok("pagos", "--date", "2026-01-05")
        self.assertIn("📁 Carpeta de la tarea: reports (la tarea ya existía: sigue ahí)\n", result.stdout)
        self.assertEqual(self.printed(result, "meta"), "reports/2026-01-01-pagos.meta.json")
        self.assertEqual(self.printed(result, "bitácora, si hace falta"), "reports/2026-01-01-pagos.bitacora.md")
        self.assertEqual(self.printed(result, "previews"), "reports/previews")
        self.assertEqual(self.printed(result, "índice"), "reports/INDEX.md")
        self.assertFalse((self.repo / "reports" / "implementation").exists())
        self.with_meta(slug="pagos", date="2026-01-05")  # el meta fuera del repo, otro día
        generated = self.ok()
        self.assertTrue((self.repo / "reports" / "2026-01-01-pagos.html").is_file())
        self.assertIn("formato plano", generated.stdout)
        self.assertFalse((self.repo / "reports" / "implementation").exists())
        self.assertEqual(self.rows(self.index()),
                         ["| 2026-01-01 | hb-implement | pagos | bugfix | DoD PASS | "
                          "[2026-01-01-pagos.html](2026-01-01-pagos.html) |"])

    def test_el_meta_plano_que_se_pasa_sigue_plano_con_su_fecha(self):
        meta = self.repo / "reports" / "2026-01-01-pagos.meta.json"
        self.with_meta(meta, slug="pagos", date="2026-01-01")
        self.ok(meta=meta)
        self.assertTrue((self.repo / "reports" / "2026-01-01-pagos.html").is_file())
        self.assertFalse((self.repo / "reports" / "implementation").exists())

    def test_una_tarea_plana_con_solo_la_bitacora_tambien_se_retoma(self):
        write(self.repo / "reports" / "2026-01-01-pagos.bitacora.md", "# Bitácora\n")
        result = self.folder_ok("pagos", "--date", "2026-01-05")
        self.assertEqual(self.printed(result, "bitácora, si hace falta"), "reports/2026-01-01-pagos.bitacora.md")

    def test_si_existen_las_dos_manda_la_carpeta_nueva(self):
        write(self.repo / "reports" / "2026-01-01-pagos.meta.json", "{}")
        write(self.repo / "reports" / "implementation" / "2026-01-03-pagos" / "meta.json", "{}")
        result = self.folder_ok("pagos", "--date", "2026-01-05")
        self.assertEqual(self.printed(result, "meta"), "reports/implementation/2026-01-03-pagos/meta.json")
        self.assertIn("ya existía", result.stdout)

    def test_una_tarea_nueva_va_a_su_carpeta_aunque_haya_tareas_planas(self):
        write(self.repo / "reports" / "2026-01-01-viejo.meta.json", "{}")
        result = self.folder_ok("nuevo", "--date", "2026-01-02")
        self.assertEqual(self.printed(result, "meta"), "reports/implementation/2026-01-02-nuevo/meta.json")
        self.assertNotIn("ya existía", result.stdout)

    def test_el_meta_en_la_carpeta_de_otra_fecha_genera_ahi_y_conserva_la_fecha_de_la_tarea(self):
        meta = self.repo / "reports" / "implementation" / "2026-01-01-pagos" / "meta.json"
        self.with_meta(meta, slug="otro-slug", date="2026-01-05")
        self.ok(meta=meta)
        self.assertTrue((meta.parent / "report.html").is_file())
        self.assertFalse((self.repo / "reports" / "implementation" / "2026-01-05-otro-slug").exists())
        self.assertIn("| 2026-01-01 | hb-implement | pagos | bugfix | DoD PASS |", self.index())

    def test_una_fecha_que_no_es_aaaa_mm_dd_falla_con_un_error_claro(self):
        self.with_meta(date="hoy")
        result = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no es AAAA-MM-DD", result.stderr)
        self.assertFalse((self.repo / "reports").exists())

    def test_folder_no_crea_la_carpeta_de_previews(self):
        result = self.folder_ok("pagos", "--date", "2026-01-02")
        self.assertFalse((self.repo / self.printed(result, "previews")).exists())


class IndexTest(Base):
    """<base>/INDEX.md: una fila por tarea, clave hb-implement + slug; las demás filas y líneas no se tocan."""

    def test_folder_crea_el_indice_con_la_fila_en_curso(self):
        self.folder_ok("perfil-de-usuario", "--date", "2026-11-25")
        self.assertEqual(self.index(), HEADER + (
            "| 2026-11-25 | hb-implement | perfil-de-usuario | — | en curso | "
            "[implementation/2026-11-25-perfil-de-usuario/report.html]"
            "(implementation/2026-11-25-perfil-de-usuario/report.html) |\n"))

    def test_el_reporte_reemplaza_la_misma_fila_con_el_tipo_y_el_dod(self):
        self.folder_ok("prueba-x", "--date", "2026-01-02")
        self.ok()
        self.assertEqual(self.rows(self.index()), [
            "| 2026-01-02 | hb-implement | prueba-x | bugfix | DoD PASS | "
            "[implementation/2026-01-02-prueba-x/report.html](implementation/2026-01-02-prueba-x/report.html) |"])

    def test_estado_del_dod(self):
        cases = (([{"status": "pass"}, {"status": "fail"}], "DoD FAIL"),
                 ([{"status": "pass"}, {"status": "skipped"}], "DoD PARTIAL"),
                 ([], "sin DoD"))
        for dod, state in cases:
            self.with_meta(dod=dod)
            self.ok()
            self.assertIn("| bugfix | %s |" % state, self.index())
            self.assertEqual(len(self.rows(self.index())), 1)

    def test_al_volver_a_pedir_la_carpeta_queda_en_curso_y_conserva_el_tipo(self):
        self.ok()
        self.folder_ok("prueba-x", "--date", "2026-01-09")
        self.assertEqual(self.rows(self.index()), [
            "| 2026-01-02 | hb-implement | prueba-x | bugfix | en curso | "
            "[implementation/2026-01-02-prueba-x/report.html](implementation/2026-01-02-prueba-x/report.html) |"])

    def test_no_toca_otras_filas_ni_otras_lineas(self):
        others = ("| 2026-11-01 | hb-performance | arranque/2026-11-01 | investigación | sesión 1 | "
                  "[performance/arranque/2026-11-01/estado.md](performance/arranque/2026-11-01/estado.md) |\n"
                  "| 2026-11-02 | hb-review | prueba-x | review | aprobado | "
                  "[review/2026-11-02-prueba-x/review.md](review/2026-11-02-prueba-x/review.md) |\n"
                  "| 2026-11-03 | hb-implement | otra | feature | DoD PASS | [x](x) |\n")
        before = HEADER + others + "\nNotas a mano que no son de la tabla.\n"
        write(self.repo / "reports" / "INDEX.md", before)
        self.ok()
        after = self.index()
        row = ("| 2026-01-02 | hb-implement | prueba-x | bugfix | DoD PASS | "
               "[implementation/2026-01-02-prueba-x/report.html](implementation/2026-01-02-prueba-x/report.html) |\n")
        self.assertEqual(after, HEADER + others + row + "\nNotas a mano que no son de la tabla.\n")

    def test_reemplaza_su_fila_donde_esta(self):
        first = "| 2026-01-02 | hb-implement | prueba-x | bugfix | en curso | [viejo](viejo) |\n"
        last = "| 2026-11-02 | hb-review | prueba-x | review | aprobado | [r](r) |\n"
        write(self.repo / "reports" / "INDEX.md", HEADER + first + last)
        self.ok()
        lines = self.index().splitlines()
        self.assertIn("| prueba-x | bugfix | DoD PASS | [implementation/", lines[-2])
        self.assertEqual(lines[-1] + "\n", last)

    def test_un_indice_sin_la_cabecera_recibe_la_tabla_al_final_sin_borrar_nada(self):
        write(self.repo / "reports" / "INDEX.md", "# Mis notas\n\nalgo")
        self.ok()
        text = self.index()
        self.assertTrue(text.startswith("# Mis notas\n\nalgo\n\n| Fecha | Skill | Slug | Tipo | Estado | Ruta |\n"))
        self.ok()  # la segunda vez ya encuentra su tabla
        self.assertEqual(len(self.rows(self.index())), 1)

    def test_escapa_las_celdas_y_codifica_los_espacios_de_la_ruta(self):
        self.with_meta(type="bug|fix\nraro")
        self.ok("--out", "reports/{fecha} tareas/{slug}")
        self.assertIn("| bug\\|fix raro | DoD PASS | [2026-01-02 tareas/prueba-x/report.html]"
                      "(2026-01-02%20tareas/prueba-x/report.html) |", self.index())
        self.assertTrue((self.repo / "reports" / "2026-01-02 tareas" / "prueba-x" / "report.html").is_file())

    def test_el_indice_no_cuenta_como_cambio_ni_entra_a_git(self):
        self.ok()
        html = (self.repo / "reports" / "implementation" / "2026-01-02-prueba-x" / "report.html").read_text("utf-8")
        self.assertNotIn("INDEX.md", html)
        status = run(["git", "status", "--porcelain", "--untracked-files=all"], self.repo).stdout
        self.assertNotIn("reports", status)


class BaseBranchTest(Base):
    """A1: sin --base, cada repo se compara con el merge-base de HEAD y su rama principal."""

    def report(self):
        return (self.repo / "reports" / "implementation" / "2026-01-02-prueba-x" / "report.html").read_text("utf-8")

    def branch_with_commit(self, repo, name="feat/prueba-x"):
        git(repo, "checkout", "-q", "-b", name)
        write(repo / "rama.txt", "commiteado en la rama\n")
        git(repo, "add", "rama.txt")
        git(repo, "commit", "-q", "-m", "en la rama")

    def test_en_una_rama_de_trabajo_incluye_lo_commiteado_en_la_rama(self):
        self.branch_with_commit(self.repo)
        result = self.ok()
        html = self.report()
        self.assertIn("commiteado en la rama", html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")  # b.txt y rama.txt
        sha = git(self.repo, "rev-parse", "--short", "main").strip()
        self.assertIn('<p class="hero-base">Comparado con merge-base con <code>main</code> · <code>%s</code></p>' % sha,
                      html)
        self.assertIn("🔀 Base de app-shell: merge-base con main (%s)" % sha, result.stdout)

    def test_base_explicita_manda(self):
        self.branch_with_commit(self.repo)
        self.ok("--base", "HEAD")
        html = self.report()
        self.assertNotIn("commiteado en la rama", html)
        self.assertIn('<p class="hero-base">Comparado con <code>HEAD</code></p>', html)

    def clone(self):
        """Un remoto bare con main y un clon (con origin/HEAD); en el clon, un commit en main sin publicar."""
        remote = self.base / "remoto.git"
        git(self.base, "init", "-q", "--bare", str(remote))
        git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        git(self.repo, "push", "-q", str(remote), "main")  # solo lo commiteado
        git(self.base, "clone", "-q", str(remote), "clon")
        clone = self.base / "clon"
        write(clone / "local.txt", "en main, sin publicar\n")
        git(clone, "add", "local.txt")
        git(clone, "commit", "-q", "-m", "local")
        return remote, clone

    def test_prefiere_la_rama_remota_de_origin_head(self):
        _, clone = self.clone()
        self.branch_with_commit(clone)
        result = self.ok(repo=clone)
        sha = git(clone, "rev-parse", "--short", "origin/main").strip()
        self.assertIn("🔀 Base de clon: merge-base con origin/main (%s)" % sha, result.stdout)
        html = (clone / "reports" / "implementation" / "2026-01-02-prueba-x" / "report.html").read_text("utf-8")
        self.assertIn("en main, sin publicar", html)  # lo local de main todavía no está integrado

    def test_main_branch_del_modelo_manda_sobre_origin_head(self):
        remote, clone = self.clone()
        git(clone, "push", "-q", "origin", "main:develop")
        self.branch_with_commit(clone)
        result = self.ok("--main-branch", "develop", repo=clone)
        self.assertIn("merge-base con origin/develop", result.stdout)
        html = (clone / "reports" / "implementation" / "2026-01-02-prueba-x" / "report.html").read_text("utf-8")
        self.assertNotIn("en main, sin publicar", html)  # ya está en develop

    def test_una_main_branch_que_no_existe_avisa_y_sigue_con_las_conocidas(self):
        result = self.ok("--main-branch", "no-existe")
        self.assertIn('la rama principal "no-existe" no existe', result.stderr)
        self.assertIn("merge-base con main", result.stdout)

    def test_sin_rama_principal_compara_contra_head_y_avisa(self):
        git(self.repo, "branch", "-m", "trunk")
        result = self.ok()
        self.assertIn("comparo contra HEAD", result.stderr)
        self.assertIn("--main-branch", result.stderr)
        self.assertIn('<p class="hero-base">Comparado con <code>HEAD</code> · sin rama principal</p>', self.report())

    def test_cada_vecino_usa_su_rama_principal(self):
        neighbor = init_repo(self.mkdir("core-lib"))
        write(neighbor / "x.txt", "base\n")
        commit_all(neighbor, "base")
        git(neighbor, "branch", "develop")
        self.branch_with_commit(neighbor, "feat/prueba-x")
        self.with_meta(repos=[{"path": "../core-lib", "main_branch": "develop"}])
        result = self.ok()
        sha = git(neighbor, "rev-parse", "--short", "develop").strip()
        self.assertIn("🔀 Base de core-lib: merge-base con develop (%s)" % sha, result.stdout)
        html = self.report()
        self.assertIn("<td>merge-base con <code>develop</code> · <code>%s</code></td>" % sha, html)
        self.assertIn("commiteado en la rama", html)
        self.assertNotIn('class="hero-base"', html)  # con varios repos, la base va en la tabla


class VersionTest(Base):
    """Hallazgo 13: la versión que fija la app frente a lo que hay en el fuente del vecino."""

    def setUp(self):
        super().setUp()
        self.neighbor = init_repo(self.mkdir("core-lib"))
        write(self.neighbor / "x.txt", "base\n")
        commit_all(self.neighbor, "base")
        git(self.neighbor, "tag", "v2.3.1")

    def report(self):
        return (self.repo / "reports" / "implementation" / "2026-01-02-prueba-x" / "report.html").read_text("utf-8")

    def test_avisa_si_el_fuente_no_coincide_con_la_version_fijada(self):
        write(self.neighbor / "x.txt", "más nuevo que el tag\n")
        commit_all(self.neighbor, "después del tag")
        git(self.neighbor, "checkout", "-q", "-b", "feat/prueba-x")
        self.with_meta(repos=[{"path": "../core-lib", "pinned_version": "2.3.1"}])
        result = self.ok()
        source = git(self.neighbor, "describe", "--tags", "--always", "main").strip()
        self.assertTrue(source.startswith("v2.3.1-1-g"), source)
        self.assertIn("core-lib: el fuente (%s) no coincide con la versión que fija la app (2.3.1)" % source,
                      result.stderr)
        html = self.report()
        self.assertIn("version-warning", html)
        self.assertIn("fijada <code>2.3.1</code> · fuente <code>%s</code>" % source, html)
        self.assertIn("⚠️ no coinciden", html)

    def test_coinciden_aunque_el_tag_lleve_v_y_no_avisa(self):
        git(self.neighbor, "checkout", "-q", "-b", "feat/prueba-x")
        write(self.neighbor / "x.txt", "cambio de la tarea\n")
        commit_all(self.neighbor, "cambio de la tarea")  # lo de la tarea no cuenta: se describe la base
        self.with_meta(repos=[{"path": "../core-lib", "pinned_version": "2.3.1"}])
        result = self.ok()
        self.assertNotIn("no coincide", result.stderr)
        html = self.report()
        self.assertIn("fijada <code>2.3.1</code> · fuente <code>v2.3.1</code>", html)
        self.assertNotIn("version-warning", html.split("</style>", 1)[1])

    def test_source_version_explicita_manda(self):
        self.with_meta(repos=[{"path": "../core-lib", "pinned_version": "2.3.1", "source_version": "2.4.0"}])
        result = self.ok()
        self.assertIn("el fuente (2.4.0) no coincide", result.stderr)

    def test_sin_versiones_no_hay_columna(self):
        self.with_meta(repos=[{"path": "../core-lib"}])
        self.ok()
        self.assertNotIn("<th>Versión</th>", self.report())

    def test_campos_que_no_son_texto_fallan_sin_escribir(self):
        for field in ("pinned_version", "source_version", "main_branch", "base"):
            self.with_meta(repos=[{"path": "../core-lib", field: 1}])
            result = self.generate()
            self.assertEqual(result.returncode, 1, field)
            self.assertIn('"%s" de "repos" debe ser un texto' % field, result.stderr)
            self.assertFalse((self.repo / "reports").exists())


class LinkedContextTest(Base):
    """A2 (H7 y H9): la carpeta de contexto es un enlace simbólico a una carpeta fuera del repo."""

    def setUp(self):
        super().setUp()
        self.outside = self.mkdir("fuera/contexto")
        (self.repo / "contexto").symlink_to(Path("..") / "fuera" / "contexto", target_is_directory=True)
        write(self.repo / ".git" / "info" / "exclude", "/contexto\n")
        self.agents("- Carpeta de reportes: `contexto/reports`")
        self.reports = self.outside / "reports"

    def test_folder_previews_e_indice_a_traves_del_enlace(self):
        result = self.folder_ok("prueba-x", "--date", "2026-01-02")
        task = "contexto/reports/implementation/2026-01-02-prueba-x"
        self.assertEqual(self.printed(result, "previews"), task + "/previews")
        self.assertEqual(self.printed(result, "índice"), "contexto/reports/INDEX.md")
        meta = self.repo / self.printed(result, "meta")
        self.with_meta(meta, previews=[{"name": "Home", "image": self.printed(result, "previews") + "/home.png"}])
        image = self.repo / self.printed(result, "previews") / "home.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(PNG)
        generated = self.ok(meta=meta)
        self.assertNotIn("Preview sin imagen", generated.stderr)
        self.assertTrue((self.repo / "contexto").is_symlink())  # H7: el enlace sigue siendo enlace
        report = self.reports / "implementation" / "2026-01-02-prueba-x" / "report.html"
        self.assertIn("data:image/png;base64,", report.read_text(encoding="utf-8"))
        # H9: el enlace del índice funciona desde la carpeta real del índice.
        index = os.path.realpath(str(self.repo / "contexto" / "reports" / "INDEX.md"))
        self.assertEqual(index, str(self.reports / "INDEX.md"))
        target = re.search(r"\]\(([^)]+)\) \|$", self.rows(self.index(self.reports))[0]).group(1)
        self.assertEqual(target, "implementation/2026-01-02-prueba-x/report.html")
        self.assertTrue((Path(index).parent / target).is_file())
        self.assertNotIn("contexto", run(["git", "status", "--porcelain"], self.repo).stdout)

    def test_un_preview_relativo_a_la_carpeta_de_la_tarea_tambien_se_incrusta(self):
        task = self.reports / "implementation" / "2026-01-02-prueba-x"
        (task / "previews").mkdir(parents=True)
        (task / "previews" / "home.png").write_bytes(PNG)
        self.with_meta(task / "meta.json", previews=[{"name": "Home", "image": "previews/home.png"}])
        result = self.ok(meta=self.repo / "contexto" / "reports" / "implementation" / "2026-01-02-prueba-x" /
                         "meta.json")
        self.assertNotIn("Preview sin imagen", result.stderr)
        self.assertIn("data:image/png;base64,", (task / "report.html").read_text(encoding="utf-8"))

    def test_un_indice_que_es_enlace_sigue_siendo_enlace(self):
        notes = self.base / "notas" / "INDEX.md"
        write(notes, HEADER)
        self.reports.mkdir()
        (self.reports / "INDEX.md").symlink_to(notes)
        self.ok()
        self.assertTrue((self.reports / "INDEX.md").is_symlink())
        self.assertIn("| hb-implement | prueba-x | bugfix | DoD PASS |", notes.read_text(encoding="utf-8"))

    def test_el_meta_pasado_por_la_ruta_real_tambien_encuentra_su_carpeta(self):
        meta = self.reports / "implementation" / "2026-01-01-pagos" / "meta.json"
        self.with_meta(meta, slug="pagos")
        self.ok(meta=meta)
        self.assertTrue((meta.parent / "report.html").is_file())
        self.assertIn("| 2026-01-01 | hb-implement | pagos |", self.index(self.reports))


class WorktreeTest(Base):
    """H10: un worktree enlazado no trae AGENTS.md ni la carpeta de contexto que el principal tiene fuera de git."""

    def setUp(self):
        super().setUp()
        commit_all(self.repo, "cambios")
        self.outside = self.mkdir("fuera")
        write(self.outside / "AGENTS.md", "# Proyecto\n\n- Carpeta de reportes: `contexto/reports`\n")
        (self.outside / "contexto").mkdir()
        self.tree = self.base / "arbol"

    def link_context(self, agents=True):
        if agents:
            (self.repo / "AGENTS.md").symlink_to(self.outside / "AGENTS.md")
        (self.repo / "contexto").symlink_to(self.outside / "contexto", target_is_directory=True)
        write(self.repo / ".git" / "info" / "exclude", "/AGENTS.md\n/contexto\n")

    def add_tree(self):
        git(self.repo, "worktree", "add", "-q", "-b", "otra", str(self.tree))
        write(self.tree / "nuevo.txt", "x\n")

    def nothing_written(self):
        self.assertFalse(os.path.lexists(str(self.tree / "reports")))
        self.assertFalse(os.path.lexists(str(self.tree / "contexto")))
        self.assertFalse(os.path.lexists(str(self.tree / "AGENTS.md")))
        self.assertFalse((self.outside / "contexto" / "reports").exists())

    def test_sin_los_enlaces_se_detiene_y_dice_como_recrearlos(self):
        self.link_context()
        self.add_tree()
        for result in (self.folder("prueba-x", repo=self.tree), self.generate(repo=self.tree)):
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("ln -s %s AGENTS.md" % (self.outside / "AGENTS.md"), result.stderr)
            self.assertIn("ln -s %s contexto" % (self.outside / "contexto"), result.stderr)
            self.assertIn("cd %s &&" % self.tree, result.stderr)
            self.assertIn("git ya lo ignora", result.stderr)
            self.assertIn("en el principal es un enlace", result.stderr)
            self.assertIn("No escribo nada", result.stderr)
            self.nothing_written()

    def test_con_agents_versionado_solo_falta_la_carpeta_de_contexto(self):
        self.agents("- Carpeta de reportes: `contexto/reports`")
        self.link_context(agents=False)
        self.add_tree()
        result = self.folder("prueba-x", repo=self.tree)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ln -s %s contexto" % (self.outside / "contexto"), result.stderr)
        self.assertNotIn("AGENTS.md:", result.stderr)
        self.assertFalse(os.path.lexists(str(self.tree / "contexto")))

    def test_con_los_enlaces_recreados_escribe_en_la_carpeta_real(self):
        self.link_context()
        self.add_tree()
        os.symlink(str(self.outside / "AGENTS.md"), str(self.tree / "AGENTS.md"))
        os.symlink(str(self.outside / "contexto"), str(self.tree / "contexto"))
        result = self.folder_ok("prueba-x", "--date", "2026-01-02", repo=self.tree)
        self.assertEqual(self.printed(result, "índice"), "contexto/reports/INDEX.md")
        self.assertTrue((self.outside / "contexto" / "reports" / "implementation" / "2026-01-02-prueba-x").is_dir())
        self.assertIn("| hb-implement | prueba-x |", self.index(self.outside / "contexto" / "reports"))
        self.assertTrue((self.tree / "contexto").is_symlink())

    def test_una_carpeta_de_reportes_local_en_el_principal_no_detiene(self):
        """Lo que ya funcionaba: cada worktree tiene su reports/ local (git lo ignora en todos los worktrees)."""
        write(self.repo / "reports" / "2026-01-01-vieja.meta.json", "{}")
        write(self.repo / ".git" / "info" / "exclude", "/reports/\n")
        self.add_tree()
        result = self.folder_ok("prueba-x", "--date", "2026-01-02", repo=self.tree)
        self.assertNotIn("ln -s", result.stderr)
        self.assertTrue((self.tree / "reports" / "implementation" / "2026-01-02-prueba-x").is_dir())
        self.assertFalse((self.tree / "reports").is_symlink())

    def test_un_archivo_versionado_que_falta_en_la_rama_no_detiene(self):
        self.agents("- Carpeta de reportes: `reports`")
        git(self.repo, "worktree", "add", "-q", "-b", "vieja", str(self.tree), "HEAD~1")  # antes del AGENTS.md
        self.folder_ok("prueba-x", repo=self.tree)

    def test_out_explicito_fuera_del_repo_no_necesita_los_enlaces(self):
        self.link_context()
        self.add_tree()
        elsewhere = self.base / "otros-reportes"
        result = self.folder_ok("prueba-x", "--out", str(elsewhere), repo=self.tree)
        self.assertTrue((elsewhere / "INDEX.md").is_file())
        self.assertIn("previews:", result.stdout)

    def test_en_el_principal_no_cambia_nada(self):
        self.link_context()
        self.add_tree()
        self.folder_ok("prueba-x")
        self.assertTrue((self.outside / "contexto" / "reports" / "INDEX.md").is_file())


if __name__ == "__main__":
    unittest.main()
