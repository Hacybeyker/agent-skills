"""hb-implement · report.py. 1.6.0: carpeta por tarea bajo la base común, compatibilidad con el formato plano,
INDEX.md, base de comparación por repo (merge-base con la rama principal), versiones fijada y del fuente, carpeta de
contexto enlazada (escritura sobre la ruta real y rutas relativas) y worktrees a los que les faltan los enlaces.
Los casos de 1.7.0 (foto inicial, --unit, detección contra la foto, reporte por unidad y tema) van al final."""
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import ENV, ROOT, commit_all, git, init_repo, run, write

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
        """El número de una tarjeta del resumen ("Archivos Nuevos", "DoD"…)."""
        return re.search(r'<div class="stat-value[^"]*">([^<]+)</div><div class="stat-label">%s</div>' % label, html,
                         re.I).group(1)

    def start(self, *folder_args, repo=None):
        """Como el flujo: pide la carpeta (y toma la foto) con el árbol limpio, y después hace los cambios de la tarea."""
        git(self.repo, "checkout", "-q", "--", "a.txt")
        (self.repo / "b.txt").unlink()
        result = self.folder_ok(*folder_args, repo=repo)
        write(self.repo / "a.txt", "dos\n")
        write(self.repo / "b.txt", "nuevo\n")
        return result


class TaskFolderTest(Base):
    """Sin marcadores, la línea es la base: la tarea va en <base>/implementation/<fecha>-<slug>/."""

    def test_folder_y_reporte_quedan_juntos_en_la_carpeta_de_la_tarea(self):
        result = self.start("prueba-x", "--date", "2026-01-02")
        task = self.repo / "reports" / "implementation" / "2026-01-02-prueba-x"
        self.assertEqual(self.printed(result, "meta"), "reports/implementation/2026-01-02-prueba-x/meta.json")
        self.with_meta(task / "meta.json")
        generated = self.ok(meta=task / "meta.json")
        self.assertIn("reports/implementation/2026-01-02-prueba-x/report.html", generated.stdout)
        html = (task / "report.html").read_text(encoding="utf-8")
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "1")  # b.txt: ni el meta ni el índice ni la foto cuentan
        self.assertNotIn("el meta va en", generated.stderr)
        self.assertTrue((task / "snapshot.json").is_file())
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


class LocalConfigTest(Base):
    """V1: la configuración local registrada en ## Estructura no es un cambio de la tarea, aunque el meta no la nombre."""

    def setUp(self):
        super().setUp()
        write(self.repo / "local-modules.json", '{"core-lib": false}\n')
        write(self.repo / "AGENTS.md", "# P\n\n## Estructura\n\n### Unidades\n\n(tabla)\n\n"
              "### Configuración local modificada a propósito\n\n"
              "- `local-modules.json`: dice qué unidades van en fuente. No se commitea.\n\n## Git\n\n- x\n")
        git(self.repo, "add", "local-modules.json", "AGENTS.md")
        git(self.repo, "commit", "-q", "-m", "config")
        write(self.repo / "local-modules.json", '{"core-lib": true}\n')

    def test_queda_fuera_de_los_cambios_y_sale_en_cambios_temporales(self):
        result = self.ok("--out", "reports")
        html = next((self.repo / "reports").rglob("report.html")).read_text(encoding="utf-8")
        self.assertNotIn("local-modules.json", result.stderr)
        self.assertEqual(self.stat(html, "Archivos Modificados"), "1")  # solo a.txt
        self.assertIn("Cambios temporales", html)
        self.assertIn("local-modules.json", html)
        self.assertIn("Configuración local modificada a propósito", html)

    def test_si_el_meta_ya_la_trae_en_temporary_no_se_duplica(self):
        self.with_meta(temporary=[{"path": "local-modules.json", "why": "Pasa core-lib a fuente.",
                                   "revert": '"core-lib": false'}])
        self.ok("--out", "reports")
        html = next((self.repo / "reports").rglob("report.html")).read_text(encoding="utf-8")
        self.assertEqual(html.count('<div class="file-path">local-modules.json</div>'), 1)
        self.assertIn("Pasa core-lib a fuente.", html)


class IndexTest(Base):
    """<base>/INDEX.md: una fila por tarea, clave hb-implement + slug; las demás filas y líneas no se tocan."""

    def test_folder_crea_el_indice_con_la_fila_en_curso(self):
        self.folder_ok("perfil-de-usuario", "--date", "2026-11-25")
        self.assertEqual(self.index(), HEADER + (
            "| 2026-11-25 | hb-implement | perfil-de-usuario | — | en curso | "
            "[implementation/2026-11-25-perfil-de-usuario/report.html]"
            "(implementation/2026-11-25-perfil-de-usuario/report.html) |\n"))

    def test_el_reporte_reemplaza_la_misma_fila_con_el_tipo_y_el_dod(self):
        self.start("prueba-x", "--date", "2026-01-02")
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
        self.assertIn("<td>merge-base con <code>main</code> · <code>%s</code></td>" % sha, html)
        self.assertIn("🔀 Base de app-shell: merge-base con main (%s)" % sha, result.stdout)

    def test_base_explicita_manda(self):
        self.branch_with_commit(self.repo)
        self.ok("--base", "HEAD")
        html = self.report()
        self.assertNotIn("commiteado en la rama", html)
        self.assertIn('<div class="k">Base</div><div class="x"><code>HEAD</code></div>', html)

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
        self.assertIn("<td><code>HEAD</code> · sin rama principal</td>", self.report())

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
        self.assertIn('<section id="unidad-core-lib" class="unit">', html)  # cada repo, su sección


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
        self.assertIn("core-lib: el fuente no coincide con la versión que fija la app", html)
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
        self.assertNotIn("no coinciden", html.split("</style>", 1)[1])

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
        result = self.start("prueba-x", "--date", "2026-01-02")
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


# ── hb-implement 1.7.0 ───────────────────────────────────────────────────────
# Un proyecto "cascarón" con módulos en repos hermanos, con nombres inventados: app-shell (el principal), shop-auth
# (una unidad del modelo, publicada y ya pasada a fuente desde antes) y billing-tools (un proyecto ajeno que vive en la
# misma carpeta padre).
SHELL_AGENTS = (
    "# Tienda\n\n## Arquitectura\n\nCapas: dominio, datos y presentación.\n\n## Estructura\n\n### Unidades\n\n"
    "| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal | "
    "Publica y versiona |\n| --- | --- | --- | --- | --- | --- | --- |\n"
    "| `app-shell` | `.` | Es la app | — | `make check` | este repo, `main` | con la app |\n"
    "| `shop-auth` | `../shop-auth` | Publicada: `com.example:shop-auth`, versión fijada en `versions.toml` | "
    "A fuente: `\"shop-auth\": true` en `local-modules.json`; volver: `false` | `cd ../shop-auth && make check` | "
    "`https://git.example.com/shop/shop-auth.git`, `main` | su repo, con `hb-release` |\n\n"
    "- Repos vecinos: clonar los que falten y preguntar la rama de trabajo.\n\n"
    "### Configuración local modificada a propósito\n\n"
    "- `local-modules.json`: dice qué unidades van en fuente. No se commitea.\n\n"
    "## Git\n\n- Ramas: `<tipo>/<ticket>-<slug>`.\n")
SHELL_AGENTS_WITHOUT_AUTH = re.sub(r"(?m)^\| `shop-auth`.*\n", "", SHELL_AGENTS)
LOGIN_KT = ("package com.example.auth\n\nclass Login {\n    fun accepts(user: String, password: String): Boolean =\n"
            "        user.isNotBlank()\n}\n")
LOGIN_KT_FIXED = ("package com.example.auth\n\nclass Login {\n    fun accepts(user: String, password: String): Boolean =\n"
                  "        user.isNotBlank() && password.isNotBlank()\n}\n")
LOGIN_TEST_JAVA = ("package com.example.auth;\n\nimport org.junit.Test;\nimport static org.junit.Assert.assertFalse;\n\n"
                   "public class LoginTest {\n    @Test\n    public void rejectsEmptyPassword() {\n"
                   "        assertFalse(new Login().accepts(\"ana\", \"\"));\n    }\n}\n")
LOGIN_TEST_KT = ("package com.example.auth\n\nimport org.junit.Assert.assertFalse\nimport org.junit.Test\n\n"
                 "class LoginTest {\n    @Test\n    fun `rechaza la clave vacia`() {\n"
                 "        assertFalse(Login().accepts(\"ana\", \"\"))\n    }\n}\n")
JAVA_TEST = "src/test/java/com/example/auth/LoginTest.java"
KOTLIN_TEST = "src/test/kotlin/com/example/auth/LoginTest.kt"
LOGIN = "src/main/kotlin/com/example/auth/Login.kt"
CHECKOUT = "src/main/kotlin/com/example/shop/Checkout.kt"
FULL_ANALYSIS = {
    "ticket": "SHOP-1234",
    "severity": "alto",
    "root_cause": "Login.accepts no validaba la clave: solo miraba el usuario.",
    "impact": [{"label": "Usuarios afectados", "value": "Todos los que entran con usuario y clave"},
               {"label": "Pantallas", "value": 2}],
    "diagrams": [{"title": "Validación del login", "mermaid": "flowchart LR\n  A[Pantalla] --> B[Login.accepts]\n"
                  "  B --> C{¿Usuario y clave?}", "description": "La clave vacía ahora se rechaza."}],
    "branch_note": "El usuario eligió seguir en la rama actual de cada repo.",
}


def load_report_module():
    spec = importlib.util.spec_from_file_location("hb_implement_report", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report_module = load_report_module()


class Workspace:
    """La carpeta padre con los tres repos. La tarea arregla el login en shop-auth: vacía el test en Java y crea uno en
    Kotlin (la migración que nadie pidió), y corrige Login.kt."""

    def __init__(self, base, agents=SHELL_AGENTS, slug="fix-login", date="2026-03-10"):
        self.parent = base / "workspace"
        self.slug, self.date = slug, date
        self.app = init_repo(self.mkdir("app-shell"))
        write(self.app / "AGENTS.md", agents)
        write(self.app / "local-modules.json", '{"shop-auth": false}\n')
        write(self.app / CHECKOUT, "package com.example.shop\n\nclass Checkout\n")
        commit_all(self.app, "base")
        write(self.app / "local-modules.json", '{"shop-auth": true}\n')  # ya estaba en fuente antes de la tarea
        self.auth = init_repo(self.mkdir("shop-auth"))
        write(self.auth / LOGIN, LOGIN_KT)
        write(self.auth / JAVA_TEST, LOGIN_TEST_JAVA)
        commit_all(self.auth, "base")
        self.billing = init_repo(self.mkdir("billing-tools"))
        write(self.billing / "README.md", "# Facturación\n")
        commit_all(self.billing, "base")
        self.task = self.app / "reports" / "implementation" / ("%s-%s" % (date, slug))

    def mkdir(self, name):
        path = self.parent / name
        path.mkdir(parents=True)
        return path

    def script(self, *args, env=None):
        command = [sys.executable, "-I", str(SCRIPT), "--repo", str(self.app)] + [str(a) for a in args]
        return subprocess.run(command, cwd=str(self.app), env=env or ENV, capture_output=True, text=True,
                              encoding="utf-8")

    def folder(self, env=None):
        return self.script("--folder", self.slug, "--date", self.date, env=env)

    def unit(self, path):
        return self.script("--unit", path, "--folder", self.slug, "--date", self.date)

    def fix_login(self):
        write(self.auth / JAVA_TEST, "")
        write(self.auth / KOTLIN_TEST, LOGIN_TEST_KT)
        write(self.auth / LOGIN, LOGIN_KT_FIXED)

    def write_meta(self, **extra):
        meta = {"title": "Corrige el login con clave vacía", "type": "bugfix", "date": self.date, "slug": self.slug,
                "description": "El login aceptaba una clave vacía.",
                "dod": [{"icon": "🧪", "name": "shop-auth · Tests", "command": "cd ../shop-auth && make check",
                         "status": "pass"}]}
        meta.update(extra)
        write(self.task / "meta.json", json.dumps(meta, ensure_ascii=False))

    def generate(self, *extra, env=None):
        return self.script("--meta", self.task / "meta.json", *extra, env=env)

    def html(self):
        return (self.task / "report.html").read_text(encoding="utf-8")

    def snapshot(self):
        return json.loads((self.task / "snapshot.json").read_text(encoding="utf-8"))


class WorkspaceTest(unittest.TestCase):
    agents = SHELL_AGENTS

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(os.path.realpath(self.tmp.name)), agents=self.agents)

    def tearDown(self):
        self.tmp.cleanup()

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def stat(self, html, label):
        return re.search(r'<div class="stat-value[^"]*">([^<]+)</div><div class="stat-label">%s</div>' % label, html,
                         re.I).group(1)

    def body(self, html):
        return html.split("</style>", 1)[1]


class RegressionTest(WorkspaceTest):
    """El caso real: la tarea cambió solo un repo vecino ya pasado a fuente, el agente corrió su DoD pero no lo anotó
    en "repos", y 1.6.0 generó un reporte con 0 archivos sin avisar."""

    def test_la_unidad_del_modelo_que_cambio_entra_aunque_no_este_en_repos(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta()  # sin "repos", sin análisis: como en el caso real
        result = self.ok(self.ws.generate())
        html = self.ws.html()
        self.assertIn('<section id="unidad-shop-auth" class="unit">', html)
        self.assertEqual(self.stat(html, "Archivos nuevos"), "1")  # LoginTest.kt
        self.assertEqual(self.stat(html, "Archivos modificados"), "2")  # LoginTest.java (vaciado) y Login.kt
        self.assertIn("🧩 Unidades en el reporte: shop-auth (3 archivos)", result.stdout)
        # El principal no cambió después de la foto: su configuración local es temporal, no de la tarea.
        self.assertNotIn('id="unidad-app-shell"', html)
        self.assertIn("Sin cambios desde la foto inicial", html)
        self.assertIn('<div class="file-path">local-modules.json</div>', html)
        # La migración de lenguaje que nadie pidió: en el reporte y en la salida.
        migration = "%s (vaciado) → %s" % (JAVA_TEST, KOTLIN_TEST)
        self.assertIn("Posible migración de lenguaje que nadie pidió", html)
        self.assertIn(migration, html)
        self.assertIn(migration, result.stderr)
        # El DoD de la unidad va en su sección.
        unit = html.split('<section id="unidad-shop-auth"', 1)[1].split("</section>", 1)[0]
        self.assertIn("shop-auth · Tests", unit)
        self.assertEqual(self.stat(html, "DoD"), "PASS")
        self.assertIn("| fix-login | bugfix | DoD PASS |", (self.ws.app / "reports" / "INDEX.md").read_text("utf-8"))

    def test_sin_foto_1_6_0_daba_cero_archivos_y_ahora_no_escribe_y_explica(self):
        """Sin foto (como en 1.6.0) y sin "repos", el principal no tiene cambios: no hay reporte vacío."""
        self.ws.fix_login()
        self.ws.write_meta()
        git(self.ws.app, "checkout", "-q", "--", "local-modules.json")
        result = self.ws.generate()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("No genero el reporte", result.stderr)
        self.assertIn("../shop-auth", result.stderr)
        self.assertIn("--unit ../shop-auth --folder fix-login", result.stderr)
        self.assertFalse((self.ws.task / "report.html").exists())


class SnapshotTest(WorkspaceTest):
    """Punto 1: --folder guarda la foto inicial con el principal, los repos hermanos y las fuentes del modelo."""

    def test_la_foto_trae_cada_repo_con_rama_head_y_archivos_sucios_con_su_hash(self):
        write(self.ws.billing / "notas.txt", "pendiente\n")
        result = self.ok(self.ws.folder())
        self.assertIn("   foto inicial: reports/implementation/2026-03-10-fix-login/snapshot.json (3 repos: el "
                      "principal, 1 unidad y 1 repo hermano)", result.stdout)
        snapshot = self.ws.snapshot()
        repos = {entry["path"]: entry for entry in snapshot["repos"]}
        self.assertEqual(sorted(repos), [".", "../billing-tools", "../shop-auth"])
        self.assertEqual((repos["."]["role"], repos["."]["units"]), ("main", ["app-shell"]))
        self.assertEqual((repos["../shop-auth"]["role"], repos["../shop-auth"]["units"]), ("unit", ["shop-auth"]))
        self.assertEqual(repos["../billing-tools"]["role"], "sibling")
        for path, entry in repos.items():
            repo = self.ws.app / path
            self.assertEqual(entry["branch"], "main")
            self.assertEqual(entry["head"], git(repo, "rev-parse", "HEAD").strip())
        info = os.lstat(str(self.ws.billing / "notas.txt"))  # un hermano ajeno: tamaño y fecha, sin leerlo
        self.assertEqual(repos["../billing-tools"]["dirty"],
                         {"notas.txt": "st:%d:%d" % (info.st_size, info.st_mtime_ns)})
        expected = git(self.ws.app, "hash-object", "--no-filters", "local-modules.json").strip()
        self.assertEqual(repos["."]["dirty"], {"local-modules.json": expected})  # la foto no se ve a sí misma
        self.assertEqual(snapshot["registered"], [])

    def test_volver_a_pedir_la_carpeta_conserva_la_foto_del_inicio(self):
        self.ok(self.ws.folder())
        before = (self.ws.task / "snapshot.json").read_bytes()
        self.ws.fix_login()
        again = self.ok(self.ws.folder())
        self.assertIn("ya existía: se conserva la del inicio de la tarea", again.stdout)
        self.assertEqual((self.ws.task / "snapshot.json").read_bytes(), before)

    def test_avisa_si_la_foto_ya_encuentra_cambios_en_el_principal_o_las_unidades(self):
        write(self.ws.app / "notas.txt", "x\n")
        write(self.ws.auth / LOGIN, LOGIN_KT_FIXED)
        result = self.ok(self.ws.folder())
        self.assertIn("La foto inicial ya encuentra cambios sin commit en app-shell: 1 archivo (notas.txt); "
                      "shop-auth: 1 archivo (%s)" % LOGIN, result.stderr)
        self.assertNotIn("local-modules.json", result.stderr)  # la configuración local no es un cambio ajeno

    def test_una_unidad_sin_clonar_queda_anotada_sin_fallar(self):
        write(self.ws.app / "AGENTS.md", SHELL_AGENTS.replace("`../shop-auth`", "`../core-lib`"))
        self.ok(self.ws.folder())
        snapshot = self.ws.snapshot()
        self.assertEqual(snapshot["missing_units"], [{"unit": "shop-auth", "path": "../core-lib"}])

    def test_el_hash_es_el_de_git_hash_object(self):
        folder = self.ws.parent / "hashes"
        folder.mkdir()
        init_repo(folder)
        write(folder / "texto.txt", "línea\r\n")
        (folder / "binario.bin").write_bytes(b"\x00\x01\xff")
        os.symlink("texto.txt", str(folder / "enlace"))
        for name in ("texto.txt", "binario.bin"):
            expected = git(folder, "hash-object", "--no-filters", name).strip()
            self.assertEqual(report_module.content_hash(folder / name), expected, name)
        git(folder, "add", "enlace")
        self.assertEqual(report_module.content_hash(folder / "enlace"),
                         git(folder, "ls-files", "-s", "enlace").split()[1])
        self.assertIsNone(report_module.content_hash(folder / "no-existe"))
        self.assertEqual(report_module.content_hash(folder / ".git"), "dir")

    def test_una_tarea_empezada_sin_foto_no_la_toma_tarde(self):
        write(self.ws.task / "meta.json", json.dumps({"title": "x"}))
        result = self.ok(self.ws.folder())
        self.assertIn("La tarea empezó sin foto inicial", result.stderr)
        self.assertFalse((self.ws.task / "snapshot.json").exists())
        self.assertNotIn("foto inicial:", result.stdout)


class ManySiblingsTest(WorkspaceTest):
    """Más de 50 repos hermanos: un solo `git status` por repo, en paralelo, y sin pasos por archivo."""

    SIBLINGS = 60

    def setUp(self):
        super().setUp()
        for number in range(self.SIBLINGS):
            folder = self.ws.mkdir("proyecto-%02d" % number)
            git(folder, "init", "-q")
        write(self.ws.parent / "proyecto-07" / "borrador.txt", "x\n")
        bin_dir = self.ws.parent.parent / "bin"
        bin_dir.mkdir()
        self.log = self.ws.parent.parent / "git.log"
        real_git = shutil.which("git", path=ENV.get("PATH"))
        (bin_dir / "git").write_text('#!/bin/sh\nprintf "%%s\\n" "$*" >> %s\nexec %s "$@"\n' % (
            shlex.quote(str(self.log)), shlex.quote(real_git)), encoding="utf-8")
        (bin_dir / "git").chmod(0o755)
        self.env = dict(ENV, PATH=str(bin_dir) + os.pathsep + ENV.get("PATH", ""))

    def calls(self):
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        self.log.write_text("", encoding="utf-8")
        return lines

    def test_la_foto_y_el_reporte_con_60_hermanos(self):
        start = time.monotonic()
        self.ok(self.ws.folder(env=self.env))
        elapsed = time.monotonic() - start
        calls = self.calls()
        repos = self.SIBLINGS + 3  # los 60, el principal, shop-auth y billing-tools
        self.assertEqual(sum(1 for line in calls if "status --porcelain=v2" in line), repos)
        self.assertLess(len(calls), repos + 15, "\n".join(calls))  # nada por archivo ni por repo fuera del status
        self.assertLess(elapsed, 60)
        self.assertEqual(len(self.ws.snapshot()["repos"]), repos)
        self.ws.fix_login()
        write(self.ws.parent / "proyecto-33" / "nuevo.txt", "x\n")  # un proyecto ajeno cambia durante la tarea
        self.ws.write_meta()
        result = self.ok(self.ws.generate(env=self.env))
        calls = self.calls()
        self.assertEqual(sum(1 for line in calls if "status --porcelain=v2" in line), repos)
        self.assertIn("../proyecto-33: 1 archivo sin commit", result.stderr)
        self.assertNotIn("proyecto-07", result.stderr)  # estaba sucio antes y no cambió: no es noticia
        self.assertNotIn("proyecto-33", self.ws.html())


class UnreadableFolderTest(WorkspaceTest):
    """Una carpeta sin permiso en la carpeta padre no detiene ni la foto ni el reporte."""

    def setUp(self):
        super().setUp()
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("como root, una carpeta sin permiso se lee igual")
        self.secret = self.ws.mkdir("secreto")
        git(self.secret, "init", "-q")
        self.secret.chmod(0)

    def tearDown(self):
        self.secret.chmod(0o755)
        super().tearDown()

    def test_queda_anotada_y_sigue(self):
        result = self.ok(self.ws.folder())
        self.assertIn("No pude leer 1 carpeta: ../secreto (sin permiso)", result.stderr)
        self.assertEqual(self.ws.snapshot()["unreadable"], [{"path": "../secreto", "reason": "sin permiso"}])
        self.ws.fix_login()
        self.ws.write_meta()
        self.ok(self.ws.generate())
        self.assertIn('id="unidad-shop-auth"', self.ws.html())


class ForeignSiblingTest(WorkspaceTest):
    """Punto 3: un repo hermano que cambió durante la tarea y no es unidad no entra: se lista para preguntar."""

    def test_no_entra_y_se_lista_con_el_comando_para_registrarlo(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        write(self.ws.billing / "README.md", "# Facturación\n\nOtro proyecto, otra persona.\n")
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        self.assertNotIn("billing-tools", self.ws.html())
        self.assertIn("Otros repos cambiaron durante la tarea y no son unidades del modelo ni están registrados",
                      result.stderr)
        self.assertIn("../billing-tools: 1 archivo sin commit", result.stderr)
        self.assertIn("--unit ../billing-tools --folder fix-login", result.stderr)

    def test_si_el_usuario_dice_que_es_de_la_tarea_se_registra_y_entra(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        write(self.ws.billing / "README.md", "# Facturación\n\nCambio de la tarea.\n")
        self.ws.write_meta()
        self.ok(self.ws.generate())
        registered = self.ok(self.ws.unit("../billing-tools"))
        self.assertIn("✔ Unidad registrada: billing-tools (../billing-tools)", registered.stdout)
        result = self.ok(self.ws.generate())
        self.assertIn('id="unidad-billing-tools"', self.ws.html())
        self.assertNotIn("Otros repos cambiaron", result.stderr)

    def test_un_hermano_sucio_desde_antes_que_no_cambia_no_se_nombra(self):
        write(self.ws.billing / "borrador.txt", "x\n")
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        self.assertNotIn("billing-tools", result.stderr + self.ws.html())


class RegisterUnitTest(WorkspaceTest):
    """Punto 2: --unit anota la unidad en "repos" del meta (lo crea si falta) y en la foto, en el momento."""

    agents = SHELL_AGENTS_WITHOUT_AUTH  # shop-auth no está en el modelo: solo entra si se registra

    def meta(self):
        return json.loads((self.ws.task / "meta.json").read_text(encoding="utf-8"))

    def test_crea_el_meta_si_falta_y_no_duplica(self):
        self.ok(self.ws.folder())
        first = self.ok(self.ws.unit("../shop-auth"))
        self.assertIn("✔ Unidad registrada: shop-auth (../shop-auth)", first.stdout)
        self.assertEqual(self.meta(), {"repos": [{"path": "../shop-auth", "name": "shop-auth"}]})
        again = self.ok(self.ws.unit("../shop-auth/src"))
        self.assertIn("ya estaba registrada", again.stdout)
        self.assertEqual(len(self.meta()["repos"]), 1)
        self.assertEqual(self.ws.snapshot()["registered"], ["../shop-auth"])

    def test_conserva_lo_que_el_meta_ya_tiene(self):
        self.ok(self.ws.folder())
        self.ws.write_meta(files={"x": {"why": "y"}})
        self.ok(self.ws.unit("../shop-auth"))
        meta = self.meta()
        self.assertEqual(meta["files"], {"x": {"why": "y"}})
        self.assertEqual(meta["title"], "Corrige el login con clave vacía")
        self.assertEqual(meta["repos"], [{"path": "../shop-auth", "name": "shop-auth"}])

    def test_la_registrada_entra_aunque_el_meta_se_reescriba_sin_repos(self):
        self.ok(self.ws.folder())
        self.ok(self.ws.unit("../shop-auth"))  # al pasarla a fuente o al correr su DoD
        self.ws.fix_login()
        self.ws.write_meta()  # el agente escribe el meta entero al final, sin "repos"
        self.ok(self.ws.generate())
        self.assertIn('id="unidad-shop-auth"', self.ws.html())

    def test_sin_registrar_no_entra_y_el_reporte_vacio_dice_como_registrarla(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta()
        result = self.ws.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("../shop-auth (3 archivos sin commit)", result.stderr)
        self.assertIn("--unit ../shop-auth --folder fix-login", result.stderr)

    def test_acepta_el_identificador_del_modelo(self):
        write(self.ws.app / "AGENTS.md", SHELL_AGENTS)
        self.ok(self.ws.folder())
        self.ok(self.ws.unit("shop-auth"))
        self.assertEqual(self.meta()["repos"], [{"path": "../shop-auth", "name": "shop-auth", "main_branch": "main"}])

    def test_una_unidad_del_principal_no_se_registra(self):
        self.ok(self.ws.folder())
        result = self.ok(self.ws.unit("src"))
        self.assertIn("es del repo principal: ya entra al reporte", result.stdout)
        self.assertFalse((self.ws.task / "meta.json").exists())

    def test_errores_claros_sin_traceback(self):
        self.ok(self.ws.folder())
        missing = self.ws.unit("../no-existe")
        self.assertEqual(missing.returncode, 1)
        self.assertIn('No encuentro la unidad "../no-existe"', missing.stderr)
        write(self.ws.task / "meta.json", "{roto")
        broken = self.ws.unit("../shop-auth")
        self.assertEqual(broken.returncode, 1)
        self.assertIn("no es un JSON válido", broken.stderr)
        self.assertEqual((self.ws.task / "meta.json").read_text(encoding="utf-8"), "{roto")
        alone = self.ws.script("--unit", "../shop-auth")
        self.assertEqual(alone.returncode, 2)
        self.assertIn("--unit va con --folder", alone.stderr)
        for result in (missing, broken):
            self.assertNotIn("Traceback", result.stderr)


class PreviousChangesTest(WorkspaceTest):
    """Punto 3: lo que ya estaba antes de la foto, en un repo de la tarea."""

    def report_with(self, before, during):
        before()
        self.ok(self.ws.folder())
        during()
        self.ws.fix_login()
        self.ws.write_meta()
        return self.ok(self.ws.generate())

    def test_sucio_antes_y_sin_cambios_va_a_no_atribuidos_fuera_de_los_conteos(self):
        self.report_with(lambda: write(self.ws.auth / "NOTAS.md", "borrador\n"), lambda: None)
        html = self.ws.html()
        self.assertIn("Cambios no atribuidos", html)
        self.assertRegex(html, r'<code class="file-path">NOTAS.md</code> <span class="muted">· sin commit desde antes')
        self.assertEqual(self.stat(html, "Archivos nuevos"), "1")  # solo LoginTest.kt
        self.assertIn('<details class="block">', html)  # colapsado

    def test_sucio_antes_y_que_ademas_cambio_entra_con_un_aviso(self):
        self.report_with(lambda: write(self.ws.auth / LOGIN, LOGIN_KT + "// a medias\n"), lambda: None)
        html = self.ws.html()
        self.assertEqual(self.stat(html, "Archivos modificados"), "2")
        self.assertIn("Ya tenía cambios sin commit antes de la tarea", html)
        self.assertIn("Archivos que ya tenían cambios antes de la tarea", html)

    def test_lo_commiteado_en_la_rama_antes_de_la_foto_no_es_de_la_tarea(self):
        def before():
            git(self.ws.auth, "checkout", "-q", "-b", "feat/otra-cosa")
            write(self.ws.auth / "VIEJO.md", "de antes\n")
            commit_all(self.ws.auth, "antes de la tarea")
        self.report_with(before, lambda: None)
        html = self.ws.html()
        self.assertRegex(html, r"VIEJO.md</code> <span class=\"muted\">· commiteado en la rama antes de la tarea")
        self.assertEqual(self.stat(html, "Archivos nuevos"), "1")

    def test_el_meta_que_explica_un_archivo_previo_avisa_de_la_foto_tardia(self):
        write(self.ws.auth / "NOTAS.md", "borrador\n")
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta(files={"shop-auth:NOTAS.md": {"why": "Notas de la tarea."}})
        result = self.ok(self.ws.generate())
        self.assertIn("El meta explica archivos que ya estaban así en la foto inicial", result.stderr)
        self.assertIn("--ignore-snapshot", result.stderr)

    def test_la_rama_del_inicio_y_la_actual(self):
        self.ok(self.ws.folder())
        git(self.ws.auth, "checkout", "-q", "-b", "fix/SHOP-1234-login")
        self.ws.fix_login()
        self.ws.write_meta()
        self.ok(self.ws.generate())
        self.assertIn("<code>fix/SHOP-1234-login</code> <span class=\"muted\">· al empezar: <code>main</code>",
                      self.ws.html())


class EmptyReportTest(WorkspaceTest):
    """Punto 4: sin ningún archivo de la tarea no hay reporte; la salida dice la causa probable y el siguiente paso."""

    def assert_empty(self, result):
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("No genero el reporte", result.stderr)
        self.assertIn("Causa probable:", result.stderr)
        self.assertIn("Siguiente paso:", result.stderr)
        self.assertFalse((self.ws.task / "report.html").exists())
        self.assertIn("| fix-login | — | en curso |", (self.ws.app / "reports" / "INDEX.md").read_text("utf-8"))

    def test_nada_cambio_despues_de_la_foto(self):
        self.ok(self.ws.folder())
        self.ws.write_meta()
        result = self.ws.generate()
        self.assert_empty(result)
        self.assertIn("Todo lo que cambió es temporal o configuración local", result.stderr)

    def test_foto_tomada_tarde(self):
        self.ws.fix_login()
        self.ok(self.ws.folder())
        self.ws.write_meta()
        result = self.ws.generate()
        self.assert_empty(result)
        self.assertIn("ya estaban antes de la foto inicial", result.stderr)
        self.assertIn("--ignore-snapshot", result.stderr)
        self.ok(self.ws.unit("../shop-auth"))
        recovered = self.ok(self.ws.generate("--ignore-snapshot"))
        self.assertIn("Genero sin la foto inicial", recovered.stderr)
        self.assertIn('id="unidad-shop-auth"', self.ws.html())

    def test_ningun_repo_cambio_despues_de_la_foto(self):
        git(self.ws.app, "checkout", "-q", "--", "local-modules.json")
        self.ok(self.ws.folder())
        self.ws.write_meta()
        result = self.ws.generate()
        self.assert_empty(result)
        self.assertIn("Ningún repo de la tarea cambió después de la foto inicial (app-shell, shop-auth)", result.stderr)

    def test_sin_foto_ningun_repo_con_cambios_contra_su_base(self):
        git(self.ws.app, "checkout", "-q", "--", "local-modules.json")
        self.ws.write_meta()
        result = self.ws.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Ningún repo de la tarea tiene cambios contra su base (app-shell: merge-base con main", result.stderr)
        self.assertIn("pasa la base con --base", result.stderr)
        self.assertFalse((self.ws.task / "report.html").exists())


class OldTaskWithoutPhotoTest(WorkspaceTest):
    """Punto 3, sin foto: una tarea vieja usa "repos" del meta y lista los repos sucios como no atribuidos."""

    def test_usa_repos_del_meta_y_lista_los_hermanos_sucios(self):
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        self.ws.fix_login()
        write(self.ws.billing / "borrador.txt", "x\n")
        self.ws.write_meta()  # sin snapshot.json: la tarea empezó con 1.6.0
        result = self.ok(self.ws.generate())
        html = self.ws.html()
        self.assertIn("La tarea no tiene foto inicial", result.stderr)
        self.assertIn("La tarea no tiene foto inicial", html)
        self.assertIn('id="unidad-app-shell"', html)
        self.assertNotIn('id="unidad-shop-auth"', html)
        unattributed = html.split('id="no-atribuidos"', 1)[1].split("</section>", 1)[0]
        for path in ("../shop-auth", KOTLIN_TEST):  # una unidad del modelo
            self.assertIn(path, unattributed)
        for path in ("billing-tools", "borrador.txt"):  # un repo hermano ajeno: solo en la salida, nunca en el HTML
            self.assertNotIn(path, html)
        self.assertIn("Unidades del modelo con cambios sin commit que no están en \"repos\" del meta (van a «Cambios "
                      "no atribuidos»): ../shop-auth", result.stderr)
        self.assertIn("Repos hermanos con cambios sin commit que no son unidades del modelo (no entran al reporte; solo "
                      "se nombran aquí): ../billing-tools", result.stderr)
        self.assertIn("--unit ../shop-auth --folder fix-login", result.stderr)
        self.assertEqual(self.stat(html, "Archivos nuevos"), "1")  # src/Nuevo.kt

    def test_con_repos_en_el_meta_entra_como_antes(self):
        self.ws.fix_login()
        self.ws.write_meta(repos=[{"path": "../shop-auth"}])
        self.ok(self.ws.generate())
        self.assertIn('id="unidad-shop-auth"', self.ws.html())


class LanguageMigrationTest(unittest.TestCase):
    """Punto 5: un archivo de código borrado, vaciado o reducido a comentarios cuyo equivalente con el mismo nombre
    base aparece en otra extensión de código."""

    REPO = {"real": "/repo"}

    def entry(self, status, path, before=None, after=None, old=None):
        return {"status": status, "path": path, "old": old if old is not None else (None if status == "A" else path),
                "before": before, "after": after, "repo": self.REPO}

    def found(self, *files):
        return [(f["path"], other["path"], how) for f, other, how in report_module.language_migrations(list(files))]

    def test_borrado_vaciado_y_reducido_a_comentarios(self):
        kotlin = self.entry("A", "kotlin/LoginTest.kt", after=LOGIN_TEST_KT)
        cases = (
            (self.entry("D", "java/LoginTest.java", before=LOGIN_TEST_JAVA), "borrado"),
            (self.entry("M", "java/LoginTest.java", before=LOGIN_TEST_JAVA, after=""), "vaciado"),
            (self.entry("M", "java/LoginTest.java", before=LOGIN_TEST_JAVA, after="// migrado a Kotlin\n"),
             "reducido a comentarios"),
            (self.entry("M", "java/LoginTest.java", before=LOGIN_TEST_JAVA,
                        after="package com.example.auth;\n\n/* migrado */\n"), "reducido a comentarios"),
        )
        for java, how in cases:
            self.assertEqual(self.found(java, kotlin), [("java/LoginTest.java", "kotlin/LoginTest.kt", how)], how)

    def test_renombrado_a_otra_extension(self):
        moved = self.entry("M", "kotlin/LoginTest.kt", before=LOGIN_TEST_JAVA, after=LOGIN_TEST_KT,
                           old="java/LoginTest.java")
        self.assertEqual(self.found(moved), [("kotlin/LoginTest.kt", "kotlin/LoginTest.kt", "renombrado")])

    def test_sin_aviso(self):
        kotlin = self.entry("A", "kotlin/LoginTest.kt", after=LOGIN_TEST_KT)
        cases = (
            [self.entry("M", "java/LoginTest.java", before=LOGIN_TEST_JAVA, after=LOGIN_TEST_JAVA + "// x\n"), kotlin],
            [self.entry("D", "docs/LoginTest.md", before="# x\n"), self.entry("A", "docs/LoginTest.txt", after="x")],
            [self.entry("D", "java/LoginTest.java", before=LOGIN_TEST_JAVA), self.entry("A", "LoginTest.md", after="x")],
            [self.entry("D", "java/LoginTest.java", before=LOGIN_TEST_JAVA), self.entry("A", "Otro.kt", after="x")],
            [self.entry("D", "a/Login.java", before=LOGIN_TEST_JAVA), self.entry("A", "b/Login.java", after="x")],
            [self.entry("M", "x/Vacio.java", before="", after=""), self.entry("A", "x/Vacio.kt", after="x")],
        )
        for files in cases:
            self.assertEqual(self.found(*files), [], files)

    def test_en_otro_repo_no_es_equivalente(self):
        java = self.entry("D", "LoginTest.java", before=LOGIN_TEST_JAVA)
        kotlin = dict(self.entry("A", "LoginTest.kt", after=LOGIN_TEST_KT), repo={"real": "/otro"})
        self.assertEqual(self.found(java, kotlin), [])


class GroupedReportTest(WorkspaceTest):
    """Punto 6: resumen global y una sección por unidad, con rama, base, conteos y DoD de esa unidad."""

    def setUp(self):
        super().setUp()
        self.ok(self.ws.folder())
        self.ws.fix_login()
        write(self.ws.app / "src" / "main" / "kotlin" / "com" / "example" / "shop" / "LoginScreen.kt", "class LoginScreen\n")
        self.ws.write_meta(dod=[
            {"icon": "🧪", "name": "Tests", "command": "cd ../shop-auth && make check", "status": "pass",
             "unit": "shop-auth"},
            {"icon": "🧪", "name": "app-shell · Tests", "command": "make check", "status": "fail", "output": "1 fallo"},
            {"icon": "🏗️", "name": "Build de la app", "command": "make build", "status": "pass"},
        ], groups=[{"match": "shop-auth:src/test/", "why": "Tests del login."}])
        self.result = self.ok(self.ws.generate())
        self.html = self.ws.html()

    def unit(self, name):
        return self.html.split('<section id="unidad-%s"' % name, 1)[1].split("</section>", 1)[0]

    def test_resumen_global_y_una_seccion_por_unidad(self):
        summary = self.html.split('<section id="resumen">', 1)[1].split("</section>", 1)[0]
        self.assertEqual(self.stat(summary, "Archivos nuevos"), "2")
        self.assertEqual(self.stat(summary, "Unidades"), "2")
        self.assertEqual(self.stat(summary, "DoD"), "FAIL")
        self.assertLess(self.html.index('id="resumen"'), self.html.index('id="unidad-app-shell"'))
        self.assertLess(self.html.index('id="unidad-app-shell"'), self.html.index('id="unidad-shop-auth"'))
        for name in ("app-shell", "shop-auth"):
            self.assertIn('<a href="#unidad-%s">' % name, self.html)  # índice y tabla de unidades
            unit = self.unit(name)
            for label in ("Rama", "Base", "Cambios", "DoD de la unidad"):
                self.assertIn('<div class="k">%s</div>' % label, unit)
        self.assertIn("1 nuevo · 2 modificados · 0 eliminados", self.unit("shop-auth"))
        self.assertIn("1 nuevo · 0 modificados · 0 eliminados", self.unit("app-shell"))

    def test_el_dod_de_cada_unidad_en_su_seccion_y_el_del_proyecto_aparte(self):
        self.assertIn("cd ../shop-auth &amp;&amp; make check", self.unit("shop-auth"))
        self.assertIn("app-shell · Tests", self.unit("app-shell"))
        self.assertIn("1 fallo", self.unit("app-shell"))
        project = self.html.split('<section id="dod">', 1)[1].split("</section>", 1)[0]
        self.assertIn("Build de la app", project)
        self.assertNotIn("app-shell · Tests", project)

    def test_grupos_por_unidad_e_ids_unicos(self):
        self.assertEqual(self.unit("shop-auth").count("shop-auth:src/test/ · 1 archivo<"), 2)  # uno por estado
        ids = re.findall(r'<details class="file" open id="(f\d+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)))


class AnalysisDataTest(WorkspaceTest):
    """Punto 9: el flujo completa los datos de análisis; el script nunca falla por ellos."""

    def generate(self, **extra):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta(**extra)
        result = self.ok(self.ws.generate())
        return result, self.body(self.ws.html())

    def test_sin_datos_de_analisis_el_reporte_sale_completo_sin_esas_secciones(self):
        result, body = self.generate()
        for text in ("Causa raíz", "Impacto", "Diagramas", "👍 Pros", "👎 Contras", "Riesgo ", "Severidad", "Capa:",
                     "🎫", "Rama de trabajo", "<script src=", "Sin contras"):
            self.assertNotIn(text, body)
        for text in ('id="resumen"', 'id="unidad-shop-auth"', "Archivos nuevos", "DoD de la unidad", "Diff"):
            self.assertIn(text, body)
        self.assertNotRegex(body, r"<section[^>]*><h2>[^<]*</h2></section>")  # ninguna sección vacía
        self.assertIn("Datos de análisis que faltan", result.stderr)
        self.assertIn("diagrams, impact, severity, root_cause", result.stderr)

    def test_con_todos_los_datos_se_ven_todos(self):
        files = {"shop-auth:" + LOGIN: {"before": "Aceptaba la clave vacía.", "after": "La rechaza.",
                                        "risk": "alto", "layer": "dominio", "pros": ["Un solo lugar valida"],
                                        "cons": ["Cambia un contrato que usa la app"]},
                 "shop-auth:" + KOTLIN_TEST: {"why": "Test del bug.", "risk": "bajo", "layer": "tests",
                                              "pros": ["Reproduce el bug"], "cons": ["Duplica el de Java"]},
                 "shop-auth:" + JAVA_TEST: {"before": "Test en Java.", "after": "Vacío.", "risk": "medio",
                                            "pros": ["x"], "cons": ["Migración no pedida"]}}
        result, body = self.generate(files=files, **FULL_ANALYSIS)
        for text in ("🎫 SHOP-1234", "Severidad alta", "Causa raíz", "Impacto", "Diagramas", "Riesgo alto",
                     "Capa: dominio", "👍 Pros", "👎 Contras", "Cambia un contrato que usa la app",
                     "Rama de trabajo", "El usuario eligió seguir en la rama actual", "<pre class=\"mermaid\">"):
            self.assertIn(text, body)
        self.assertNotIn("Datos de análisis que faltan", result.stderr)

    def test_un_valor_vacio_no_se_muestra_y_uno_invalido_se_ignora_con_aviso(self):
        files = {"shop-auth:" + LOGIN: {"why": "", "risk": "", "pros": [], "cons": [" "], "layer": ""},
                 "shop-auth:" + KOTLIN_TEST: {"risk": "enorme", "pros": "no es lista", "layer": 3}}
        result, body = self.generate(files=files, ticket="", root_cause=None, impact=[], diagrams=[{"title": "x"}],
                                     severity="grave")
        for text in ("Riesgo ", "👍 Pros", "👎 Contras", "Capa:", "🎫", "Causa raíz", "Impacto", "Diagramas",
                     "Severidad"):
            self.assertNotIn(text, body)
        for warning in ('"risk" de shop-auth:%s debe ser critico, alto, medio o bajo (llegó "enorme")' % KOTLIN_TEST,
                        '"pros" de shop-auth:%s debe ser una lista de textos' % KOTLIN_TEST,
                        '"layer" de shop-auth:%s debe ser un texto' % KOTLIN_TEST,
                        'La entrada 1 de "diagrams" no trae mermaid', '"severity" debe ser critico'):
            self.assertIn(warning, result.stderr)

    def entry(self, body, path):
        """El bloque del archivo en el HTML, desde su ruta hasta el siguiente archivo."""
        start = body.index('<code class="file-path">%s</code>' % path)
        end = body.find('<details class="file"', start)
        return body[start:end if end != -1 else len(body)]

    def test_cons_ausente_no_se_muestra_y_cuenta_como_faltante(self):
        files = {"shop-auth:" + LOGIN: {"why": "Rechaza la clave vacía.", "risk": "alto", "pros": ["Un solo lugar"]}}
        result, body = self.generate(files=files)
        entry = self.entry(body, LOGIN)
        self.assertIn("👍 Pros", entry)
        self.assertNotIn("👎 Contras", entry)
        self.assertNotIn("Sin contras identificados", body)
        self.assertIn("risk, pros o cons de shop-auth:" + LOGIN, result.stderr)

    def test_cons_vacio_dice_sin_contras_identificados_y_no_falta(self):
        files = {"shop-auth:" + LOGIN: {"why": "Rechaza la clave vacía.", "risk": "alto", "pros": ["Un solo lugar"],
                                        "cons": []}}
        result, body = self.generate(files=files)
        entry = self.entry(body, LOGIN)
        self.assertIn("👎 Contras", entry)
        self.assertIn("Sin contras identificados", entry)
        self.assertNotIn("<li>", entry.split("👎 Contras", 1)[1].split("</div></div>", 1)[0])
        self.assertNotIn("pros o cons de shop-auth:" + LOGIN, result.stderr)

    def test_pros_vacio_sigue_sin_mostrarse(self):
        """pros no tenía un texto para "se analizó y no hubo": vacío o ausente, no se muestra."""
        files = {"shop-auth:" + LOGIN: {"why": "Rechaza la clave vacía.", "risk": "bajo", "pros": [], "cons": []}}
        _, body = self.generate(files=files)
        entry = self.entry(body, LOGIN)
        self.assertNotIn("👍 Pros", entry)
        self.assertNotIn("Sin pros", body)
        self.assertIn("Sin contras identificados", entry)


class ThemeTest(WorkspaceTest):
    """Punto 7: el sistema de tema de hb-performance, copiado: mismos tokens, el del sistema por defecto, un botón y la
    preferencia en localStorage dentro de try/catch; al imprimir, claro. Un HTML autónomo."""

    PERF = ROOT / "skills" / "hb-performance" / "assets" / "plantillas" / "reporte.html"

    @staticmethod
    def tokens(css, selector):
        start = css.index(selector + " {")
        block = css[start:css.index("}", start)]
        return dict(re.findall(r"(--[\w-]+):\s*([^;]+?)\s*;", block))

    def setUp(self):
        super().setUp()
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta()
        self.ok(self.ws.generate())
        self.page = self.ws.html()
        self.perf = self.PERF.read_text(encoding="utf-8")

    def test_los_mismos_tokens_que_hb_performance(self):
        light = self.tokens(self.page, ":root")
        dark = self.tokens(self.page, ':root:not([data-theme="light"])')
        self.assertEqual(light, self.tokens(self.perf, ":root"))
        self.assertEqual(dark, self.tokens(self.perf, ':root:not([data-theme="light"])'))
        self.assertEqual(self.tokens(self.page, ':root[data-theme="dark"]'), dark)
        printed = ':root, :root[data-theme], :root:not([data-theme="light"])'
        self.assertEqual(self.tokens(self.page, printed), self.tokens(self.perf, printed))
        self.assertEqual(len(light), 18)

    def test_tema_del_sistema_boton_y_preferencia_recordada(self):
        self.assertIn("@media (prefers-color-scheme: dark) {\n    :root:not([data-theme=\"light\"]) {", self.page)
        self.assertIn('<button class="theme-btn" id="theme-btn" type="button">', self.page)
        uses = [line for line in self.page.splitlines() if "localStorage" in line and "/*" not in line]
        self.assertGreaterEqual(len(uses), 3)
        for line in uses:
            self.assertRegex(line, r"try \{.*localStorage.*\} catch \(e\) \{\}")
        self.assertRegex(self.page.split("<style>", 1)[0], r'<script id="theme-early">')  # antes de pintar

    def test_imprime_en_claro_y_no_carga_nada_de_fuera(self):
        self.assertIn("@media print", self.page)
        self.assertIn(".theme-btn, .toc, .tabs { display: none; }", self.page)
        for remote in ("<link", "@import", "url(http", "<script src="):
            self.assertNotIn(remote, self.page)


class ExampleReportTest(WorkspaceTest):
    """Los reportes de ejemplo para revisar a ojo, en tema claro y oscuro: con todos los datos de análisis y sin ellos.
    Con HB_IMPLEMENT_EJEMPLOS=<carpeta>, los deja ahí."""

    def build(self, analysis):
        git(self.ws.auth, "checkout", "-q", "-b", "fix/SHOP-1234-login")
        self.ok(self.ws.folder())
        self.ws.fix_login()
        write(self.ws.app / "src" / "main" / "kotlin" / "com" / "example" / "shop" / "LoginScreen.kt",
              "package com.example.shop\n\nclass LoginScreen(private val login: Login) {\n"
              "    fun submit(user: String, password: String) = login.accepts(user, password)\n}\n")
        write(self.ws.app / CHECKOUT, "package com.example.shop\n\nclass Checkout(val total: Long)\n")
        extra = {}
        if analysis:
            extra = dict(FULL_ANALYSIS, files={
                CHECKOUT: {"before": "Checkout sin total.", "after": "Lleva el total en centavos.", "risk": "medio",
                           "layer": "dominio", "pros": ["El total viaja tipado"], "cons": ["Rompe a quien lo construía"]},
                "src/main/kotlin/com/example/shop/LoginScreen.kt": {
                    "why": "La pantalla delega la validación en shop-auth.", "risk": "bajo", "layer": "presentación",
                    "pros": ["Sin lógica en la vista"], "cons": []},
                "shop-auth:" + LOGIN: {"before": "Aceptaba la clave vacía.", "after": "Exige usuario y clave.",
                                       "risk": "alto", "layer": "dominio",
                                       "pros": ["Un solo lugar valida", "Cubierto por test"],
                                       "cons": ["Cambia el contrato de accepts"]},
                "shop-auth:" + KOTLIN_TEST: {"why": "Reproduce el bug de la clave vacía.", "risk": "bajo",
                                             "layer": "tests", "pros": ["Falla sin la corrección"],
                                             "cons": ["Duplica el test en Java"]},
                "shop-auth:" + JAVA_TEST: {"before": "El test en Java.", "after": "Vacío: se migró a Kotlin.",
                                           "risk": "medio", "layer": "tests", "pros": ["Un solo lenguaje"],
                                           "cons": ["Nadie pidió migrarlo"]}})
        self.ws.write_meta(dod=[
            {"icon": "🧪", "name": "shop-auth · Tests", "command": "cd ../shop-auth && make check", "status": "pass"},
            {"icon": "🧹", "name": "shop-auth · Lint", "command": "cd ../shop-auth && make lint", "status": "pass"},
            {"icon": "🧪", "name": "app-shell · Tests", "command": "make check", "status": "pass"},
            {"icon": "🏗️", "name": "Build de la app con shop-auth en fuente", "command": "make build",
             "status": "skipped", "note": "sin el SDK en este entorno"}], **extra)
        self.ok(self.ws.generate())
        target = os.environ.get("HB_IMPLEMENT_EJEMPLOS")
        if target:
            name = "con-analisis" if analysis else "sin-analisis"
            Path(target).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(self.ws.task / "report.html"), os.path.join(target, "reporte-%s.html" % name))
        return self.ws.html()

    def test_con_todos_los_datos_de_analisis(self):
        html = self.build(analysis=True)
        self.assertEqual(self.stat(html, "Unidades"), "2")
        self.assertIn("🎫 SHOP-1234", html)

    def test_sin_datos_de_analisis(self):
        html = self.build(analysis=False)
        self.assertEqual(self.stat(html, "Unidades"), "2")
        self.assertNotIn("👍 Pros", self.body(html))



class GitEdgeCasesTest(WorkspaceTest):
    """Lo que encontró la revisión: estados de git poco comunes que no deben perder archivos de la tarea ni cortar el
    reporte."""

    def generate(self, **extra):
        self.ws.write_meta(**extra)
        result = self.ok(self.ws.generate())
        return result, self.ws.html()

    def unit_html(self, html, name):
        return html.split('<section id="unidad-%s"' % name, 1)[1].split("</section>", 1)[0]

    def test_un_nombre_con_acentos_y_espacios_es_de_la_tarea(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        write(self.ws.auth / "docs" / "notas de diseño.md", "# Diseño\n")
        write(self.ws.auth / "README.md", "# Autenticación\n")
        result, html = self.generate()
        unit = self.unit_html(html, "shop-auth")
        self.assertIn("docs/notas de diseño.md", unit)
        self.assertIn("README.md", unit)
        self.assertNotIn("Cambios no atribuidos", html)
        self.assertNotIn("\\303", html + result.stderr)  # sin las comillas de core.quotePath

    def test_un_grupo_con_campos_invalidos_se_ignora_con_aviso(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        result, html = self.generate(groups=[{"match": "shop-auth:src/test/", "why": 123, "before": ["x"]}])
        self.assertIn('"why" del grupo shop-auth:src/test/ debe ser un texto', result.stderr)
        self.assertIn('"before" del grupo shop-auth:src/test/ debe ser un texto', result.stderr)
        self.assertIn("shop-auth:src/test/ · 1 archivo", html)

    def test_el_cambio_de_puntero_de_un_submodulo_es_de_la_tarea(self):
        library = self.ws.mkdir("auth-vendor")
        init_repo(library)
        write(library / "lib.txt", "v1\n")
        commit_all(library, "v1")
        git(self.ws.auth, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(library), "vendor/lib")
        commit_all(self.ws.auth, "submódulo")
        self.ok(self.ws.folder())
        submodule = self.ws.auth / "vendor" / "lib"
        write(submodule / "lib.txt", "v2\n")
        commit_all(submodule, "v2")
        result, html = self.generate()
        unit = self.unit_html(html, "shop-auth")
        self.assertIn('<code class="file-path">vendor/lib</code>', unit)
        self.assertNotIn("Cambios no atribuidos", html)

    def test_una_unidad_sin_commits_no_corta_el_reporte(self):
        write(self.ws.app / "AGENTS.md", SHELL_AGENTS.replace(
            "\n\n- Repos vecinos:", "\n| `shop-docs` | `../shop-docs` | En fuente (módulo del build) | — | `make docs` | "
            "`https://git.example.com/shop/shop-docs.git`, `main` | con la app |\n\n- Repos vecinos:", 1))
        docs = self.ws.mkdir("shop-docs")
        git(docs, "init", "-q")
        self.ok(self.ws.folder())
        write(docs / "guia.md", "# Guía\n")
        result, html = self.generate()
        unit = self.unit_html(html, "shop-docs")
        self.assertIn("guia.md", unit)
        self.assertIn("repo sin commits: todo es nuevo", unit)

    def test_un_enlace_que_pasa_a_archivo_es_una_modificacion(self):
        os.symlink("Login.kt", str(self.ws.auth / "src" / "main" / "kotlin" / "com" / "example" / "auth" / "Alias.kt"))
        commit_all(self.ws.auth, "enlace")
        self.ok(self.ws.folder())
        alias = self.ws.auth / "src" / "main" / "kotlin" / "com" / "example" / "auth" / "Alias.kt"
        alias.unlink()
        write(alias, "package com.example.auth\n\ntypealias Alias = Login\n")
        result, html = self.generate()
        self.assertIn('<span class="chip st-modified">Modificado</span><code class="file-path">'
                      'src/main/kotlin/com/example/auth/Alias.kt</code>', html)

    def test_una_fecha_que_no_es_aaaa_mm_dd_no_escribe_fuera_de_la_carpeta(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        reports = self.ws.app / "reports"
        meta = reports / "meta.json"  # un meta suelto en la base: el formato plano usa la fecha en el nombre
        write(meta, json.dumps({"title": "x", "date": "../../fuera"}))
        result = self.ws.script("--meta", meta)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no es AAAA-MM-DD", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(list(self.ws.parent.parent.glob("fuera*")), [])


# ── Revisión de 1.7.0: casos que encontró la revisión independiente ──────────
def add_unit_row(ws, row):
    """Agrega una fila a la tabla de unidades del AGENTS.md del principal y la commitea."""
    text = (ws.app / "AGENTS.md").read_text(encoding="utf-8").replace("\n\n- Repos vecinos:", "\n" + row +
                                                                       "\n\n- Repos vecinos:", 1)
    write(ws.app / "AGENTS.md", text)
    git(ws.app, "add", "AGENTS.md")
    git(ws.app, "commit", "-q", "-m", "modelo")


def raw_git(repo, *args, data=None):
    """git con argumentos en bytes (nombres que no son UTF-8)."""
    command = [b"git", b"-C", os.fsencode(str(repo))] + [a if isinstance(a, bytes) else a.encode() for a in args]
    result = subprocess.run(command, env=ENV, capture_output=True, input=data)
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", "replace"))
    return result.stdout


class ReviewFindingsTest(WorkspaceTest):
    def unit_html(self, html, name):
        return html.split('<section id="unidad-%s"' % name, 1)[1].split("</section>", 1)[0]

    def test_01_un_submodulo_que_es_unidad_entra_con_su_foto(self):
        library = self.ws.mkdir("core-src")
        init_repo(library)
        write(library / "README.md", "# Núcleo\n")
        commit_all(library, "v1")
        git(self.ws.app, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(library), "core")
        commit_all(self.ws.app, "submódulo")
        add_unit_row(self.ws, "| `core` | `core` | En fuente (módulo del build) | — | `make core` | este repo, `main` | "
                              "con la app |")
        self.ok(self.ws.folder())
        write(self.ws.app / "core" / "README.md", "# Núcleo compartido\n")
        write(self.ws.app / "core" / "C.kt", "class C\n")
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        unit = self.unit_html(self.ws.html(), "core")
        self.assertIn("C.kt", unit)
        self.assertIn("README.md", unit)
        self.assertNotIn("ya estaban antes de la foto", result.stderr)

    def test_02_una_unidad_con_git_ilegible_que_la_tarea_no_toco_no_corta_el_reporte(self):
        self.ok(self.ws.folder())
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        shutil.move(str(self.ws.auth / ".git"), str(self.ws.parent / "auth-git-movido"))
        write(self.ws.auth / ".git", "gitdir: /no/existe/x\n")
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        self.assertIn("shop-auth", result.stderr)
        self.assertIn('id="unidad-app-shell"', self.ws.html())

    def test_03_varios_unit_en_paralelo_no_pierden_registros(self):
        names = ["lib-%d" % n for n in range(8)]
        for name in names:
            path = init_repo(self.ws.mkdir(name))
            write(path / "a.txt", "a\n")
            commit_all(path)
        self.ok(self.ws.folder())
        command = [sys.executable, "-I", str(SCRIPT), "--repo", str(self.ws.app)]
        processes = [subprocess.Popen(command + ["--unit", "../" + name, "--folder", self.ws.slug, "--date",
                                                 self.ws.date], cwd=str(self.ws.app), env=ENV,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for name in names]
        outputs = [process.communicate() for process in processes]
        self.assertEqual([process.returncode for process in processes], [0] * len(names),
                         [err.decode("utf-8", "replace") for _, err in outputs])
        meta = json.loads((self.ws.task / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(entry["path"] for entry in meta["repos"]), sorted("../" + n for n in names))
        self.assertEqual(sorted(self.ws.snapshot()["registered"]), sorted("../" + n for n in names))
        self.assertEqual([p.name for p in self.ws.task.iterdir() if p.name.endswith(".tmp")], [])

    def test_04_un_nombre_que_no_es_utf8_no_corta_ni_vacia_el_reporte(self):
        blob = raw_git(self.ws.app, "hash-object", "-w", "--stdin", data=b"x\n").strip()
        raw_git(self.ws.app, "update-index", "--add", "--cacheinfo", b"100644," + blob + b",raro\xff.txt")
        raw_git(self.ws.app, "commit", "-q", "-m", "raro")
        raw_git(self.ws.app, "rm", "--cached", "-q", b"raro\xff.txt")  # en macOS ese nombre no puede estar en disco
        self.ws.write_meta()
        write(self.ws.task / "report.html", "el reporte anterior\n")
        result = self.ok(self.ws.generate("--ignore-snapshot"))
        html = self.ws.html()
        self.assertIn("raro�.txt", html)
        self.assertGreater(len(html), 1000)
        self.assertNotIn("Traceback", result.stderr)

    def test_05_la_carpeta_de_reportes_en_un_repo_hermano_no_es_otro_repo_que_cambio(self):
        context = init_repo(self.ws.mkdir("app-contexto"))
        write(context / "README.md", "# Contexto\n")
        commit_all(context)
        os.symlink("../app-contexto", str(self.ws.app / "contexto"))
        with open(str(self.ws.app / ".git" / "info" / "exclude"), "a", encoding="utf-8") as handle:
            handle.write("/contexto\n")
        write(self.ws.app / "AGENTS.md", SHELL_AGENTS + "\n## Reglas del proyecto\n\n- Carpeta de reportes: "
                                                        "`contexto/reports`\n")
        commit_all(self.ws.app, "reportes")
        self.ok(self.ws.folder())
        self.ws.task = self.ws.app / "contexto" / "reports" / "implementation" / ("%s-%s" % (self.ws.date, self.ws.slug))
        self.ws.fix_login()
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        self.assertNotIn("app-contexto", result.stderr)
        self.assertNotIn("Otros repos cambiaron", result.stderr)

    def test_06_sin_foto_el_html_no_lista_repos_hermanos_ajenos(self):
        write(self.ws.billing / "contrato-privado.txt", "x\n")
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        self.ws.fix_login()
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        html = self.ws.html()
        self.assertNotIn("billing-tools", html)
        self.assertNotIn("contrato-privado.txt", html)
        self.assertIn("../billing-tools", result.stderr)  # en la salida sí, con el comando para registrarlo
        self.assertIn(KOTLIN_TEST, html)  # shop-auth es unidad del modelo: sus cambios sí van a "no atribuidos"

    def test_07_con_eol_crlf_lo_commiteado_antes_de_la_foto_no_es_de_la_tarea(self):
        write(self.ws.app / ".gitattributes", "*.txt text eol=crlf\n")
        commit_all(self.ws.app, "atributos")
        git(self.ws.app, "checkout", "-q", "-b", "feat/previo")
        write(self.ws.app / "previo.txt", "uno\ndos\n")
        git(self.ws.app, "add", "previo.txt")
        git(self.ws.app, "commit", "-q", "-m", "previo")
        (self.ws.app / "previo.txt").unlink()
        git(self.ws.app, "checkout", "-q", "--", "previo.txt")  # git lo escribe con CRLF: limpio para git
        self.assertIn(b"\r\n", (self.ws.app / "previo.txt").read_bytes())
        self.ok(self.ws.folder())
        write(self.ws.app / "src" / "A.kt", "class A\n")
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        html = self.ws.html()
        app = self.unit_html(html, "app-shell")
        self.assertIn("src/A.kt", app)
        self.assertNotIn("previo.txt", app)
        self.assertIn("previo.txt", html.split('id="no-atribuidos"', 1)[1])
        self.assertIn("app-shell (1 archivo)", result.stdout)

    def test_08_la_version_fijada_se_avisa_aunque_la_unidad_no_cambie(self):
        git(self.ws.auth, "tag", "v2.0.0")
        self.ok(self.ws.folder())
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        self.ws.write_meta(repos=[{"path": "../shop-auth", "pinned_version": "1.0.0"}])
        result = self.ok(self.ws.generate())
        self.assertIn("no coincide con la versión que fija la app", result.stderr)
        self.assertIn("no coincide con la versión que fija la app", self.ws.html())

    def test_10_la_rama_principal_del_modelo_vale_para_una_unidad_en_subcarpeta(self):
        write(self.ws.app / "AGENTS.md", SHELL_AGENTS.replace("| `shop-auth` | `../shop-auth` |",
                                                              "| `shop-auth` | `../shop-auth/src/main` |").replace(
            "`https://git.example.com/shop/shop-auth.git`, `main`", "`https://git.example.com/shop/shop-auth.git`, "
                                                                     "`develop`"))
        commit_all(self.ws.app, "modelo")
        git(self.ws.auth, "checkout", "-q", "-b", "develop")
        write(self.ws.auth / "d1.kt", "class D1\n")
        commit_all(self.ws.auth, "develop")
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        self.assertIn("Base de shop-auth: merge-base con develop", result.stdout)
        self.assertNotIn("d1.kt", self.ws.html())

    def test_11_unit_antes_de_folder_no_deja_la_tarea_sin_foto(self):
        self.ok(self.ws.unit("../billing-tools"))
        self.assertEqual(run(["git", "check-ignore", "-q", "reports/x"], self.ws.app).returncode, 0)
        result = self.ok(self.ws.folder())
        self.assertNotIn("empezó sin foto", result.stderr)
        self.assertTrue((self.ws.task / "snapshot.json").is_file())
        meta = json.loads((self.ws.task / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["path"] for entry in meta["repos"]], ["../billing-tools"])

    def test_12_lo_commiteado_antes_de_la_foto_y_cambiado_por_la_tarea_se_avisa(self):
        git(self.ws.app, "checkout", "-q", "-b", "feat/pago")
        write(self.ws.app / "src" / "Pago.kt", "class Pago\n")
        commit_all(self.ws.app, "pago")
        self.ok(self.ws.folder())
        write(self.ws.app / "src" / "Pago.kt", "class Pago(val total: Long)\n")
        self.ws.write_meta()
        self.ok(self.ws.generate())
        entry = self.unit_html(self.ws.html(), "app-shell")
        self.assertIn("src/Pago.kt", entry)
        self.assertIn("commiteados en la rama antes de la tarea", entry)

    def test_13_un_status_del_dod_que_no_es_texto_no_corta_el_reporte(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        self.ws.write_meta(dod=[{"name": "Tests", "status": ["pass"]}])
        result = self.ok(self.ws.generate())
        self.assertIn('El paso del DoD "Tests" trae "status"', result.stderr)

    def test_14_el_identificador_del_modelo_manda_sobre_una_carpeta_del_principal(self):
        write(self.ws.app / "shop-auth" / "build.gradle.kts", "\n")
        commit_all(self.ws.app, "módulo con el mismo nombre")
        self.ok(self.ws.folder())
        result = self.ok(self.ws.unit("shop-auth"))
        self.assertNotIn("es del repo principal", result.stdout)
        meta = json.loads((self.ws.task / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["path"] for entry in meta["repos"]], ["../shop-auth"])

    def test_15_ids_unicos_en_el_html(self):
        for name in ("core-lib", "core_lib"):
            path = init_repo(self.ws.mkdir(name))
            write(path / "a.txt", "a\n")
            commit_all(path)
        self.ok(self.ws.folder())
        for name in ("core-lib", "core_lib"):
            self.ok(self.ws.unit("../" + name))
            write(self.ws.parent / name / "b.txt", "b\n")
        self.ws.write_meta()
        self.ok(self.ws.generate())
        ids = re.findall(r'id="([^"]+)"', self.ws.html())
        self.assertEqual(len(ids), len(set(ids)), [i for i in ids if ids.count(i) > 1])

    def test_16_los_hermanos_ocultos_no_se_miran_y_los_ajenos_no_se_hashean(self):
        hidden = init_repo(self.ws.mkdir(".oculto"))
        write(hidden / "a.txt", "a\n")
        commit_all(hidden)
        write(self.ws.billing / "grande.bin", "x" * 4096)
        self.ok(self.ws.folder())
        repos = {entry["path"]: entry for entry in self.ws.snapshot()["repos"]}
        self.assertNotIn("../.oculto", repos)
        self.assertTrue(all(not value or value.startswith("st:")
                            for value in repos["../billing-tools"]["dirty"].values()))
        self.assertFalse(repos["../shop-auth"]["dirty"])  # una unidad del modelo: con su hash de contenido
        # registrado después, lo que ya estaba sucio y no cambió sigue siendo previo
        self.ok(self.ws.unit("../billing-tools"))
        self.ws.fix_login()
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        self.assertIn("grande.bin", self.ws.html().split('id="no-atribuidos"', 1)[1])
        self.assertNotIn("MIXED", result.stderr)

    def test_16b_con_la_carpeta_padre_en_home_no_se_miran_los_hermanos(self):
        env = dict(ENV, HOME=str(self.ws.parent))
        self.ok(self.ws.folder(env=env))
        roles = [entry["role"] for entry in self.ws.snapshot()["repos"]]
        self.assertNotIn("sibling", roles)
        self.assertIn("unit", roles)  # las unidades del modelo sí

    def test_17_concordancia_con_un_solo_cambio_previo(self):
        write(self.ws.app / "src" / "Previo.kt", "class Previo\n")
        self.ok(self.ws.folder())
        self.ws.write_meta()
        result = self.ws.generate()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Los 1 cambio", result.stderr)
        self.assertIn("El cambio que hay ya estaba antes de la foto inicial", result.stderr)

    def test_a13_pros_vacio_cuenta_como_analizado(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        files = {"shop-auth:" + LOGIN: {"why": "x", "risk": "bajo", "pros": [], "cons": []}}
        self.ws.write_meta(files=files)
        result = self.ok(self.ws.generate())
        self.assertNotIn("pros o cons de shop-auth:" + LOGIN, result.stderr)
        self.assertNotIn("👍 Pros", self.unit_html(self.ws.html(), "shop-auth").split(LOGIN, 1)[1].split("<details", 1)[0])


class MigrationFalsePositivesTest(LanguageMigrationTest):
    """09: el mismo nombre en otra carpeta o en la misma familia de lenguaje no es una migración."""

    def test_09_otra_carpeta_u_otra_extension_del_mismo_lenguaje(self):
        cases = (
            [self.entry("D", "tools/index.js", before="run()\n"), self.entry("A", "b/index.ts", after="run()\n")],
            [self.entry("D", "tools/main.py", before="run()\n"), self.entry("A", "cmd/main.go", after="run()\n")],
            [self.entry("D", "src/index.js", before="run()\n"), self.entry("A", "src/index.mjs", after="run()\n")],
            [self.entry("D", "build.kt", before="run()\n"), self.entry("A", "build.kts", after="run()\n")],
        )
        for files in cases:
            self.assertEqual(self.found(*files), [], files)

    def test_09_el_mismo_lugar_en_otro_source_set_si_es_migracion(self):
        java = self.entry("D", JAVA_TEST, before=LOGIN_TEST_JAVA)
        kotlin = self.entry("A", KOTLIN_TEST, after=LOGIN_TEST_KT)
        self.assertEqual(self.found(java, kotlin), [(JAVA_TEST, KOTLIN_TEST, "borrado")])
        js = self.entry("D", "src/app/index.js", before="run()\n")
        ts = self.entry("A", "src/app/index.ts", after="run()\n")
        self.assertEqual(self.found(js, ts), [("src/app/index.js", "src/app/index.ts", "borrado")])


class VerificationFindingsTest(WorkspaceTest):
    """Lo que dejó la verificación de las correcciones de 1.7.0."""

    def unit_html(self, html, name):
        return html.split('<section id="unidad-%s"' % name, 1)[1].split("</section>", 1)[0]

    def break_git(self, repo):
        """El repo queda con un .git que git no puede leer (un worktree huérfano)."""
        shutil.move(str(repo / ".git"), str(self.ws.parent / (repo.name + "-git-movido")))
        write(repo / ".git", "gitdir: /no/existe/x\n")

    def submodule(self):
        library = self.ws.mkdir("core-src")
        init_repo(library)
        write(library / "README.md", "# Núcleo\n")
        commit_all(library, "v1")
        git(self.ws.app, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(library), "core")
        commit_all(self.ws.app, "submódulo")
        add_unit_row(self.ws, "| `core` | `core` | En fuente (módulo del build) | — | `make core` | este repo, `main` | "
                              "con la app |")

    def test_v1_una_base_invalida_del_principal_corta_el_reporte_y_la_nombra(self):
        self.ok(self.ws.folder())
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        self.ws.write_meta()
        result = self.ws.generate("--base", "origin/no-existe")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("app-shell", result.stderr)
        self.assertIn("origin/no-existe", result.stderr)
        self.assertFalse((self.ws.task / "report.html").exists())

    def test_v1_una_base_explicita_invalida_de_una_unidad_tambien_corta(self):
        self.ok(self.ws.folder())
        self.ws.fix_login()
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        self.ws.write_meta(repos=[{"path": "../shop-auth", "base": "no-existe"}])
        result = self.ws.generate()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("shop-auth", result.stderr)
        self.assertIn("no-existe", result.stderr)

    def test_v1_y_v3_lo_que_queda_fuera_sale_en_el_html_y_en_el_mensaje_sin_reporte(self):
        self.ok(self.ws.folder())
        self.ok(self.ws.unit("../shop-auth"))
        self.ws.fix_login()
        write(self.ws.app / "src" / "Nuevo.kt", "class Nuevo\n")
        self.break_git(self.ws.auth)
        self.ws.write_meta(repos=json.loads((self.ws.task / "meta.json").read_text(encoding="utf-8"))["repos"])
        result = self.ok(self.ws.generate())  # una unidad registrada que git no lee no corta el reporte
        self.assertIn('No puedo leer el repo de la unidad registrada "shop-auth"', result.stderr)
        summary = self.ws.html().split('id="resumen"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Repos de la tarea que quedaron fuera del reporte", summary)
        self.assertIn("shop-auth", summary)
        (self.ws.app / "src" / "Nuevo.kt").unlink()
        result = self.ws.generate()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Quedaron fuera del reporte: shop-auth (git no lo pudo leer", result.stderr)
        self.assertNotIn("Ningún repo de la tarea cambió después de la foto inicial", result.stderr)

    def test_v2_el_puntero_de_un_submodulo_sin_cambio_no_sale_en_el_principal(self):
        self.submodule()
        self.ok(self.ws.folder())
        write(self.ws.app / "core" / "README.md", "# Núcleo compartido\n")
        write(self.ws.app / "core" / "C.kt", "class C\n")
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        html = self.ws.html()
        self.assertNotIn('class="file-path">core</code>', html)
        self.assertIn("C.kt", self.unit_html(html, "core"))
        line = next(l for l in result.stdout.splitlines() if l.startswith("🧩 Unidades en el reporte"))
        self.assertNotIn("app-shell", line)
        self.assertNotIn("core", self.ws.snapshot()["repos"][0].get("dirty", {}))

    def test_v2_un_cambio_real_del_puntero_si_sale_en_el_principal(self):
        self.submodule()
        self.ok(self.ws.folder())
        write(self.ws.app / "core" / "C.kt", "class C\n")
        commit_all(self.ws.app / "core", "nuevo commit del núcleo")
        self.ws.write_meta()
        self.ok(self.ws.generate())
        self.assertIn('class="file-path">core</code>', self.unit_html(self.ws.html(), "app-shell"))

    def test_v2_un_repo_anidado_sin_rastrear_que_es_unidad_no_es_un_archivo_del_principal(self):
        nested = self.ws.app / "libs" / "nucleo"
        nested.mkdir(parents=True)
        init_repo(nested)
        write(nested / "a.txt", "a\n")
        commit_all(nested)
        add_unit_row(self.ws, "| `libs/nucleo` | `libs/nucleo` | En fuente (módulo del build) | — | `make` | este "
                              "repo, `main` | con la app |")
        folder = self.ok(self.ws.folder())
        self.assertNotIn("libs/nucleo)", folder.stdout + folder.stderr)
        write(nested / "b.txt", "b\n")
        self.ws.write_meta()
        result = self.ok(self.ws.generate())
        html = self.ws.html()
        self.assertNotIn('class="file-path">libs/nucleo</code>', html)
        self.assertIn("b.txt", self.unit_html(html, "nucleo"))
        line = next(l for l in result.stdout.splitlines() if l.startswith("🧩 Unidades en el reporte"))
        self.assertNotIn("app-shell", line)

    def test_v5_un_enlace_con_destino_que_no_es_utf8_no_corta(self):
        self.ok(self.ws.folder())
        try:
            os.symlink(b"destino\xff", os.fsencode(str(self.ws.app / "enlace")))
        except OSError as err:
            self.skipTest("el sistema no admite ese destino: %s" % err)
        self.ws.write_meta()
        self.ok(self.ws.generate())
        self.assertIn('class="file-path">enlace</code>', self.ws.html())

    def test_v6_unit_en_paralelo_antes_de_folder_no_repite_el_exclude_ni_deja_lock(self):
        names = ["lib-%d" % n for n in range(8)]
        for name in names:
            path = init_repo(self.ws.mkdir(name))
            write(path / "a.txt", "a\n")
            commit_all(path)
        command = [sys.executable, "-I", str(SCRIPT), "--repo", str(self.ws.app)]
        processes = [subprocess.Popen(command + ["--unit", "../" + name, "--folder", self.ws.slug, "--date",
                                                 self.ws.date], cwd=str(self.ws.app), env=ENV,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for name in names]
        outputs = [process.communicate() for process in processes]
        self.assertEqual([process.returncode for process in processes], [0] * len(names),
                         [err.decode("utf-8", "replace") for _, err in outputs])
        exclude = (self.ws.app / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.splitlines().count("/reports/"), 1)
        self.assertEqual([p for p in (self.ws.app / "reports").rglob("*") if p.name.endswith(".lock")], [])
        self.assertNotIn("reports", run(["git", "status", "--porcelain"], self.ws.app).stdout)

    def test_v7_si_no_se_puede_bloquear_sigue_con_un_aviso(self):
        import contextlib
        import errno
        import io
        import types
        fake = types.ModuleType("fcntl")
        fake.LOCK_EX, fake.LOCK_UN = 2, 8

        def flock(*_):
            raise OSError(errno.ENOLCK, "No locks available")
        fake.flock = flock
        saved = sys.modules.get("fcntl")
        sys.modules["fcntl"] = fake
        err, ran = io.StringIO(), []
        try:
            with contextlib.redirect_stderr(err):
                with report_module.task_lock(Path(self.tmp.name) / "tarea"):
                    ran.append(True)
        finally:
            if saved is None:
                sys.modules.pop("fcntl", None)
            else:
                sys.modules["fcntl"] = saved
        self.assertEqual(ran, [True])
        self.assertIn("No pude bloquear la carpeta de la tarea (No locks available): sigo sin bloqueo", err.getvalue())

    def test_v8_nested_head_tiene_tiempo_limite(self):
        from unittest import mock
        nested = init_repo(self.ws.mkdir("anidado"))
        write(nested / "a.txt", "a\n")
        commit_all(nested)
        head = git(nested, "rev-parse", "HEAD").strip()
        self.assertEqual(report_module.nested_head(str(nested), with_changes=False), head)
        calls = []
        real_run = subprocess.run

        def spy(*args, **kwargs):
            calls.append(kwargs.get("timeout"))
            return real_run(*args, **kwargs)
        with mock.patch.object(report_module.subprocess, "run", side_effect=spy):
            report_module.nested_head(str(nested))
        self.assertTrue(calls and all(timeout == report_module.STATUS_TIMEOUT_S for timeout in calls), calls)
        with mock.patch.object(report_module.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("git", report_module.STATUS_TIMEOUT_S)):
            self.assertEqual(report_module.nested_head(str(nested)), "unreadable")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "como root se puede leer todo")
    def test_v9_un_archivo_sin_permiso_no_corta_el_reporte(self):
        self.ok(self.ws.folder())
        secret = self.ws.app / "src" / "Secreto.kt"
        write(secret, "class Secreto\n")
        os.chmod(str(secret), 0)
        try:
            self.ws.write_meta()
            self.ok(self.ws.generate())
            self.assertIn("Sin permiso de lectura", self.unit_html(self.ws.html(), "app-shell"))
        finally:
            os.chmod(str(secret), 0o644)


if __name__ == "__main__":
    unittest.main()
