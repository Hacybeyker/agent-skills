"""Tests del reporte HTML de hb-implement (skills/hb-implement/scripts/report.py)."""
import base64
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, run, write

SCRIPT = ROOT / "skills" / "hb-implement" / "scripts" / "report.py"
META = {
    "title": "Prueba <x>",
    "type": "bugfix",
    "date": "2026-01-02",
    "description": "Descripción",
    "files": {"a.txt": {"before": "antes", "after": "después"}},
    "dod": [
        {"name": "Tests", "command": "make test", "status": "pass"},
        {"name": "Lint", "command": "make lint", "status": "fail", "output": "error <1>"},
    ],
}


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "repo").mkdir()
        self.repo = init_repo(base / "repo")
        write(self.repo / "a.txt", "uno\n")
        write(self.repo / "c.txt", "borrar\n")
        commit_all(self.repo, "base")
        write(self.repo / "a.txt", "dos <b>\n")  # modificado
        write(self.repo / "b.txt", "nuevo\n")  # nuevo
        (self.repo / "bin.dat").write_bytes(b"\x00\x01\x02")  # nuevo y binario
        (self.repo / "c.txt").unlink()  # eliminado
        self.meta = base / "meta.json"  # fuera del repo, para que no cuente como cambio
        self.meta.write_text(json.dumps(META), encoding="utf-8")
        self.out = self.repo / "reports" / "2026-01-02-prueba-x.html"

    def tearDown(self):
        self.tmp.cleanup()

    def generate(self):
        return run([sys.executable, "-I", SCRIPT, "--meta", self.meta, "--repo", self.repo], self.repo)

    def html(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.out.read_text(encoding="utf-8")

    def stat(self, html, label):
        return re.search(r"%s</div><div class=\"stat-value[^\"]*\"[^>]*>([^<]+)<" % label, html).group(1)

    def test_genera_el_reporte_con_la_fecha_y_el_titulo_en_el_nombre(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.out.is_file())
        self.assertIn("reports/2026-01-02-prueba-x.html", result.stdout)

    def test_cuenta_los_archivos_por_estado(self):
        html = self.html()
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")
        self.assertEqual(self.stat(html, "Archivos Modificados"), "1")
        self.assertEqual(self.stat(html, "Archivos Eliminados"), "1")

    def test_escapa_el_html_del_titulo_y_del_codigo(self):
        html = self.html()
        self.assertIn("Prueba &lt;x&gt;", html)
        self.assertIn("dos &lt;b&gt;", html)
        self.assertNotIn("Prueba <x>", html)

    def test_muestra_el_tipo_y_las_explicaciones(self):
        html = self.html()
        self.assertIn("🐛 Bug Fix", html)
        self.assertIn("después", html)

    def test_un_paso_del_dod_fallido_deja_el_resultado_en_fail(self):
        html = self.html()
        self.assertEqual(self.stat(html, "DoD"), "FAIL")
        self.assertIn("✅ PASS", html)
        self.assertIn("error &lt;1&gt;", html)

    def test_no_muestra_el_contenido_de_un_binario(self):
        self.assertIn("Archivo binario", self.html())

    def test_avisa_los_archivos_sin_explicacion(self):
        result = self.generate()
        self.assertIn("Archivos sin explicación en meta.json", result.stderr)
        self.assertIn("b.txt", result.stderr)

    def exclude(self):
        path = self.repo / ".git" / "info" / "exclude"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def status(self, repo=None):
        return run(["git", "status", "--porcelain", "--untracked-files=all"], repo or self.repo).stdout

    def test_deja_la_carpeta_fuera_de_git_con_info_exclude_y_no_toca_gitignore(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/reports/\n", self.exclude())
        self.assertIn("git ignora reports (en .git/info/exclude", result.stdout)
        self.assertNotIn(".gitignore", result.stderr)
        self.assertFalse((self.repo / ".gitignore").exists())
        self.assertNotIn("reports", self.status())

    def test_no_modifica_un_gitignore_existente(self):
        write(self.repo / ".gitignore", "build/\n")
        self.generate()
        self.assertEqual((self.repo / ".gitignore").read_text(encoding="utf-8"), "build/\n")
        self.assertIn("/reports/\n", self.exclude())

    def test_si_el_proyecto_ya_la_ignora_no_escribe_nada_y_al_repetir_no_duplica(self):
        write(self.repo / ".gitignore", "reports/\n")
        result = self.generate()
        self.assertNotIn("git ignora", result.stdout)
        self.assertNotIn("/reports/", self.exclude())
        (self.repo / ".gitignore").unlink()
        self.generate()
        self.generate()
        self.assertEqual(self.exclude().count("/reports/\n"), 1)

    def test_agrega_la_entrada_en_otra_linea_si_exclude_no_termina_en_salto(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text("*.tmp", encoding="utf-8")
        self.generate()
        self.assertEqual(self.exclude(), "*.tmp\n/reports/\n")

    def test_la_skill_no_pide_editar_el_gitignore(self):
        text = (ROOT / "skills" / "hb-implement" / "SKILL.md").read_text(encoding="utf-8")
        step = text[text.index("## 6. Reporte HTML"):]
        step = step[:step.index("\n2. ")]
        self.assertIn(".git/info/exclude", step)
        self.assertIn("sin tocar el `.gitignore`", step)
        self.assertNotIn("esté en `.gitignore`", text)
        self.assertNotIn("agrégalo", step)

    def test_en_un_worktree_usa_el_exclude_comun_y_no_falla(self):
        commit_all(self.repo, "cambios")
        tree = Path(self.tmp.name) / "arbol"
        run(["git", "worktree", "add", "-q", "-b", "otra", tree], self.repo)
        write(tree / "nuevo.txt", "x\n")
        result = run([sys.executable, "-I", SCRIPT, "--meta", self.meta, "--repo", tree], tree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("reports", self.status(tree))
        self.assertIn("/reports/\n", self.exclude())

    def test_al_regenerar_no_se_incluye_a_si_mismo(self):
        self.html()
        self.assertEqual(self.stat(self.html(), "Archivos Nuevos"), "2")

    def with_previews(self, previews):
        self.meta.write_text(json.dumps(dict(META, previews=previews)), encoding="utf-8")

    def test_sin_previews_no_hay_seccion_de_previews(self):
        self.assertNotIn("Previews de UI", self.html())

    def test_incrusta_los_previews_y_no_los_cuenta_como_archivos(self):
        png = b"\x89PNG\r\n\x1a\nfalso"
        image = self.repo / "reports" / "previews" / "home.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(png)
        absolute = Path(self.tmp.name) / "fuera.png"
        absolute.write_bytes(png)
        self.with_previews([
            {"name": "HomeContentPreview", "image": "reports/previews/home.png", "note": "Saludo <inicial>"},
            {"name": "Otra", "image": str(absolute)},
        ])
        html = self.html()
        self.assertIn("Previews de UI", html)
        self.assertEqual(html.count("data:image/png;base64,%s" % base64.b64encode(png).decode("ascii")), 2)
        self.assertIn("Saludo &lt;inicial&gt;", html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")

    def test_un_preview_sin_imagen_avisa_sin_fallar(self):
        self.with_previews([{"name": "Falta", "image": "reports/previews/no-existe.png"}])
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preview sin imagen", result.stderr)
        self.assertIn("No se encontró la imagen", self.out.read_text(encoding="utf-8"))

    def with_meta(self, **extra):
        self.meta.write_text(json.dumps(dict(META, **extra)), encoding="utf-8")

    def add_shots(self, folder="shots", names=("g0.png", "g1.png", "g2.png")):
        for name in names:
            image = self.repo / folder / name
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"\x89PNG\x00" + name.encode("ascii"))

    def count(self, html, title):
        return re.search(r"%s</span><span class=\"section-count\">(\d+)<" % title, html).group(1)

    def test_agrupa_los_archivos_de_una_carpeta_sin_exigir_una_explicacion_cada_uno(self):
        self.add_shots()
        self.with_meta(groups=[{"match": "shots/", "why": "Goldens <nuevos>"}])
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = self.out.read_text(encoding="utf-8")
        self.assertIn("shots/ · 3 archivos", html)
        self.assertIn("Goldens &lt;nuevos&gt;", html)
        self.assertIn("shots/g1.png", html)  # la lista de rutas del grupo
        self.assertEqual(html.count('class="file-path">shots/g'), 0)  # y ninguna entrada propia
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "5")  # 2 de siempre + 3 del grupo
        self.assertEqual(self.count(html, "Archivos Nuevos"), "5")
        self.assertNotIn("g0.png", result.stderr)
        self.assertIn("b.txt", result.stderr)  # los demás siguen pidiendo su explicación

    def test_agrupa_por_patron(self):
        self.add_shots(folder="a/b", names=("x.png", "y.png"))
        self.add_shots(folder="otro", names=("z.png",))
        self.with_meta(groups=[{"match": "*.png", "why": "Imágenes"}])
        result = self.generate()
        html = self.out.read_text(encoding="utf-8")
        self.assertIn("*.png · 3 archivos", html)
        self.assertNotIn("x.png", result.stderr)

    def test_un_archivo_con_su_propia_entrada_se_muestra_aparte_del_grupo(self):
        self.add_shots()
        self.with_meta(groups=[{"match": "shots/", "why": "Goldens"}],
                       files={"a.txt": {"why": "x"}, "shots/g0.png": {"why": "El golden clave"}})
        html = self.html()
        self.assertIn("shots/ · 2 archivos", html)
        self.assertIn('class="file-path">shots/g0.png', html)
        self.assertIn("El golden clave", html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "5")

    def test_el_grupo_se_arma_por_estado_y_respeta_a_los_archivos_con_entrada_propia(self):
        self.with_meta(groups=[{"match": "*.txt", "why": "Textos"}])
        html = self.html()
        # b.txt (nuevo) y c.txt (eliminado) caen en el grupo, cada uno en su sección; a.txt tiene entrada propia.
        self.assertEqual(html.count("*.txt · 1 archivo<"), 2)
        self.assertIn('class="file-path">a.txt', html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")
        self.assertEqual(self.stat(html, "Archivos Modificados"), "1")
        self.assertEqual(self.stat(html, "Archivos Eliminados"), "1")

    def test_avisa_de_un_grupo_que_no_cubre_nada_y_sugiere_agrupar_si_faltan_muchos(self):
        self.add_shots(names=tuple("g%d.png" % i for i in range(8)))
        self.with_meta(groups=[{"match": "no-existe/", "why": "x"}])
        result = self.generate()
        self.assertIn('El grupo "no-existe/" no cubre ningún archivo', result.stderr)
        self.assertIn('"groups"', result.stderr)  # 8 goldens + b.txt + bin.dat sin explicación

    def test_el_meta_por_tarea_dentro_de_reports_no_cuenta_como_cambio_y_no_se_pisan(self):
        reports = self.repo / "reports"
        reports.mkdir()
        primero = reports / "2026-01-02-uno.meta.json"
        segundo = reports / "2026-01-02-dos.meta.json"
        primero.write_text(json.dumps(dict(META, title="Uno")), encoding="utf-8")
        segundo.write_text(json.dumps(dict(META, title="Dos")), encoding="utf-8")
        for meta in (primero, segundo):
            result = run([sys.executable, "-I", SCRIPT, "--meta", meta, "--repo", self.repo], self.repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("compartido", result.stderr)
            self.assertNotIn("reports/meta.json", result.stderr)
        self.assertTrue((reports / "2026-01-02-uno.html").is_file())
        self.assertTrue((reports / "2026-01-02-dos.html").is_file())
        html = (reports / "2026-01-02-dos.html").read_text(encoding="utf-8")
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")  # los .meta.json de reports/ no cuentan

    def test_el_meta_compartido_de_antes_sigue_funcionando_y_avisa(self):
        reports = self.repo / "reports"
        reports.mkdir()
        shared = reports / "meta.json"
        shared.write_text(json.dumps(META), encoding="utf-8")
        result = run([sys.executable, "-I", SCRIPT, "--meta", shared, "--repo", self.repo], self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.out.is_file())
        self.assertIn("reports/<fecha>-<slug>.meta.json", result.stderr)

    def test_un_meta_invalido_termina_con_error(self):
        self.meta.write_text("{no es json", encoding="utf-8")
        result = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("✖", result.stderr)

    def test_un_meta_de_antes_no_agrega_secciones_nuevas_ni_carga_nada_remoto(self):
        html = self.html()
        for text in ("Repositorios", "Causa raíz", "Impacto", "Diagramas", "Cambios temporales", "Riesgo ",
                     "Severidad", "repo-tag", 'class="analysis"'):
            self.assertNotIn(text, html.split("</style>", 1)[1])
        self.assertNotIn("<script src=", html)
        self.assertNotIn("mermaid", html.split("</style>", 1)[1])


class Base(unittest.TestCase):
    """Un repo con un cambio de cada tipo y un meta fuera del repo, como ReportTest, para los casos nuevos."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "repo-principal").mkdir()
        self.repo = init_repo(self.base / "repo-principal")
        write(self.repo / "a.txt", "uno\n")
        commit_all(self.repo, "base")
        write(self.repo / "a.txt", "dos\n")
        write(self.repo / "b.txt", "nuevo\n")
        self.meta = self.base / "meta.json"
        self.with_meta()

    def tearDown(self):
        self.tmp.cleanup()

    def with_meta(self, path=None, **extra):
        meta = dict(META, files={"a.txt": {"why": "x"}, "b.txt": {"why": "y"}})
        meta.update(extra)
        write(path or self.meta, json.dumps(meta))

    def agents(self, line):
        """Commitea solo el AGENTS.md: los cambios de la tarea siguen pendientes."""
        write(self.repo / "AGENTS.md", "# Proyecto\n\n## Reglas del proyecto\n\n%s\n" % line)
        git(self.repo, "add", "AGENTS.md")
        git(self.repo, "commit", "-q", "-m", "agents")

    def generate(self, *extra, meta=None):
        return run([sys.executable, "-I", SCRIPT, "--meta", meta or self.meta, "--repo", self.repo, *extra], self.repo)

    def ok(self, *extra, meta=None):
        result = self.generate(*extra, meta=meta)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def folder(self, *extra):
        return run([sys.executable, "-I", SCRIPT, "--repo", self.repo, "--folder", *extra], self.repo)

    def exclude(self):
        path = self.repo / ".git" / "info" / "exclude"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def status(self):
        return run(["git", "status", "--porcelain", "--untracked-files=all"], self.repo).stdout

    def stat(self, html, label):
        return re.search(r"%s</div><div class=\"stat-value[^\"]*\"[^>]*>([^<]+)<" % label, html).group(1)


class ReportFolderTest(Base):
    """La carpeta de salida sale de AGENTS.md ("Carpeta de reportes: <ruta>"), con o sin {fecha} y {slug}."""

    def test_toma_la_carpeta_de_agents_sin_marcadores(self):
        self.agents("- Carpeta de reportes: `salidas/ia`")
        result = self.ok()
        self.assertTrue((self.repo / "salidas" / "ia" / "2026-01-02-prueba-x.html").is_file())
        self.assertIn("salidas/ia/2026-01-02-prueba-x.html", result.stdout)
        self.assertIn("/salidas/ia/\n", self.exclude())
        self.assertFalse((self.repo / "reports").exists())

    def test_lee_la_linea_sin_acentos_graves_y_en_negrita(self):
        self.agents("**Carpeta de reportes:** salidas.")
        self.ok()
        self.assertTrue((self.repo / "salidas" / "2026-01-02-prueba-x.html").is_file())

    def test_ignora_la_linea_dentro_de_un_bloque_de_codigo_y_los_placeholders(self):
        self.agents("```\nCarpeta de reportes: `codigo`\n```\n- Carpeta de reportes: `<ruta>`")
        self.ok()
        self.assertTrue((self.repo / "reports" / "2026-01-02-prueba-x.html").is_file())

    def test_out_manda_sobre_agents(self):
        self.agents("- Carpeta de reportes: `salidas`")
        self.ok("--out", "otra")
        self.assertTrue((self.repo / "otra" / "2026-01-02-prueba-x.html").is_file())

    def test_con_marcadores_crea_una_carpeta_por_tarea_e_ignora_la_parte_fija(self):
        self.agents("- Carpeta de reportes: `reports/{fecha}/{slug}`")
        result = self.ok()
        self.assertTrue((self.repo / "reports" / "2026-01-02" / "prueba-x" / "report.html").is_file())
        self.assertIn("reports/2026-01-02/prueba-x/report.html", result.stdout)
        self.assertIn("/reports/\n", self.exclude())
        self.assertIn("reports/2026-01-02/prueba-x/meta.json", result.stderr)  # dónde va el meta
        self.assertEqual(self.status().count("reports"), 0)

    def test_el_slug_del_meta_manda_y_conserva_las_mayusculas(self):
        self.agents("- Carpeta de reportes: `reports/{fecha}/{slug}`")
        self.with_meta(slug="TICKET-1 pagos")
        self.ok()
        self.assertTrue((self.repo / "reports" / "2026-01-02" / "TICKET-1-pagos" / "report.html").is_file())

    def test_el_slug_del_meta_tambien_vale_sin_marcadores(self):
        self.with_meta(slug="TICKET-1")
        self.ok()
        self.assertTrue((self.repo / "reports" / "2026-01-02-TICKET-1.html").is_file())

    def test_el_meta_dentro_de_la_carpeta_de_la_tarea_no_cuenta_ni_avisa(self):
        self.agents("- Carpeta de reportes: `reports/{fecha}/{slug}`")
        meta = self.repo / "reports" / "2026-01-02" / "pagos" / "meta.json"
        self.with_meta(meta, slug="pagos")
        result = self.ok(meta=meta)
        html = (meta.parent / "report.html").read_text(encoding="utf-8")
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "1")  # b.txt, no el meta
        self.assertNotIn("lo pisa", result.stderr)
        self.assertNotIn("el meta va en", result.stderr)

    def test_reutiliza_la_carpeta_del_mismo_slug_de_otra_fecha(self):
        self.agents("- Carpeta de reportes: `contexto/reports/{fecha}/{slug}`")
        earlier = self.repo / "contexto" / "reports" / "2026-01-01" / "pagos"
        write(earlier / "bitacora.md", "# Bitácora\n")
        write(self.repo / "contexto" / "reports" / "2026-01-01" / "otra-pagos" / "x.md", "x\n")
        self.with_meta(slug="pagos")  # date 2026-01-02
        result = self.ok()
        self.assertTrue((earlier / "report.html").is_file())
        self.assertFalse((self.repo / "contexto" / "reports" / "2026-01-02").exists())
        self.assertIn("sigue en contexto/reports/2026-01-01/pagos", result.stdout)

    def test_el_meta_que_vive_en_la_carpeta_de_otra_fecha_genera_ahi(self):
        self.agents("- Carpeta de reportes: `reports/{fecha}/{slug}`")
        meta = self.repo / "reports" / "2026-01-01" / "pagos" / "meta.json"
        self.with_meta(meta, slug="pagos", date="2026-01-05")
        self.ok(meta=meta)
        self.assertTrue((meta.parent / "report.html").is_file())
        self.assertFalse((self.repo / "reports" / "2026-01-05").exists())

    def test_folder_imprime_y_crea_la_carpeta_y_al_otro_dia_la_reutiliza(self):
        self.agents("- Carpeta de reportes: `reports/{fecha}/{slug}`")
        first = self.folder("pagos", "--date", "2026-01-03")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("reports/2026-01-03/pagos", first.stdout)
        self.assertIn("reports/2026-01-03/pagos/meta.json", first.stdout)
        self.assertIn("reports/2026-01-03/pagos/bitacora.md", first.stdout)
        self.assertTrue((self.repo / "reports" / "2026-01-03" / "pagos").is_dir())
        self.assertIn("/reports/\n", self.exclude())
        later = self.folder("pagos", "--date", "2026-01-09")
        self.assertIn("reports/2026-01-03/pagos/meta.json", later.stdout)
        self.assertIn("ya existía", later.stdout)
        self.assertFalse((self.repo / "reports" / "2026-01-09").exists())

    def test_folder_sin_marcadores_da_el_meta_con_fecha_y_slug(self):
        result = self.folder("pagos", "--date", "2026-01-03")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reports/2026-01-03-pagos.meta.json", result.stdout)
        self.assertIn("reports/2026-01-03-pagos.bitacora.md", result.stdout)

    def test_marcadores_sin_slug_o_sin_carpeta_fija_fallan_con_un_error_claro(self):
        for spec, message in (("reports/{fecha}", "sin {slug}"), ("{fecha}/{slug}", "carpeta fija")):
            result = self.generate("--out", spec)
            self.assertEqual(result.returncode, 1, spec)
            self.assertIn(message, result.stderr)


class SymlinkOutputTest(Base):
    """La salida pasa por un enlace simbólico (contexto/ → carpeta de fuera): git no mira más allá del enlace."""

    def setUp(self):
        super().setUp()
        outside = self.base / "fuera" / "contexto"
        outside.mkdir(parents=True)
        (self.repo / "contexto").symlink_to(Path("..") / "fuera" / "contexto", target_is_directory=True)
        self.agents("- Carpeta de reportes: `contexto/reports/{fecha}/{slug}`")
        self.report = outside / "reports" / "2026-01-02" / "prueba-x" / "report.html"

    def set_exclude(self, text):
        path = self.repo / ".git" / "info" / "exclude"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_git_falla_con_check_ignore_mas_alla_del_enlace(self):
        result = run(["git", "check-ignore", "-q", "contexto/reports/x.html"], self.repo)
        self.assertNotIn(result.returncode, (0, 1))  # el error que provocaba el aviso falso
        self.assertIn("symbolic link", result.stderr)

    def test_enlace_ignorado_no_avisa_ni_escribe(self):
        self.set_exclude("/contexto\n")
        result = self.ok()
        self.assertTrue(self.report.is_file())
        self.assertEqual(self.exclude(), "/contexto\n")
        self.assertNotIn("⚠️", result.stderr)
        self.assertNotIn("git ignora", result.stdout)
        self.assertEqual(self.status().count("contexto"), 0)

    def test_enlace_ignorado_sin_marcadores_tampoco_avisa(self):
        self.set_exclude("/contexto\n")
        result = self.ok("--out", "contexto/reports")
        self.assertTrue((self.base / "fuera" / "contexto" / "reports" / "2026-01-02-prueba-x.html").is_file())
        self.assertNotIn("⚠️", result.stderr)
        self.assertEqual(self.exclude(), "/contexto\n")

    def test_enlace_no_ignorado_avisa_sin_romper_ni_escribir_y_no_cuenta_el_enlace(self):
        result = self.ok()
        self.assertTrue(self.report.is_file())
        self.assertIn("contexto es un enlace simbólico que git no ignora", result.stderr)
        self.assertIn("/contexto (sin barra final)", result.stderr)
        self.assertEqual(self.exclude().count("contexto"), 0)
        html = self.report.read_text(encoding="utf-8")
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "1")  # b.txt; el enlace no es un cambio de la tarea
        self.assertNotIn('class="file-path">contexto', html)

    def test_una_carpeta_fuera_del_repo_no_necesita_ignorarse(self):
        result = self.ok("--out", str(self.base / "notas" / "{fecha}" / "{slug}"))
        self.assertTrue((self.base / "notas" / "2026-01-02" / "prueba-x" / "report.html").is_file())
        self.assertNotIn("⚠️", result.stderr)
        self.assertEqual(self.exclude().count("notas"), 0)


class MultiRepoTest(Base):
    """Un solo reporte para el repo principal y sus repos relacionados, cada uno con su base."""

    def setUp(self):
        super().setUp()
        (self.base / "modulo-a").mkdir()
        self.related = init_repo(self.base / "modulo-a")
        write(self.related / "x.txt", "base\n")
        write(self.related / "config.txt", "a=1\n")
        commit_all(self.related, "base")
        run(["git", "checkout", "-q", "-b", "trabajo"], self.related)
        write(self.related / "x.txt", "commit de la rama\n")
        commit_all(self.related, "en la rama")
        write(self.related / "config.txt", "a=2\n")  # sin commitear
        write(self.related / "y.txt", "sin rastrear\n")
        self.repos = [{"path": "../modulo-a", "base": "main", "name": "modulo-a"}]

    def test_dos_repos_con_bases_distintas_y_archivos_sin_rastrear(self):
        self.with_meta(repos=self.repos, files={"a.txt": {"why": "principal"}, "modulo-a:x.txt": {"why": "del modulo"}})
        result = self.ok()
        html = (self.repo / "reports" / "2026-01-02-prueba-x.html").read_text(encoding="utf-8")
        self.assertIn("Repositorios", html)
        self.assertIn('<td><span class="repo-tag">modulo-a</span></td><td>trabajo</td><td><code>main</code></td>'
                      "<td>1</td><td>2</td><td>0</td>", html)
        self.assertIn('<td><span class="repo-tag">repo-principal</span></td><td>main</td><td><code>HEAD</code></td>'
                      "<td>1</td><td>1</td><td>0</td>", html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")  # b.txt y modulo-a:y.txt
        self.assertEqual(self.stat(html, "Archivos Modificados"), "3")  # a.txt, x.txt (commit) y config.txt
        self.assertIn("commit de la rama", html)  # el diff contra main incluye lo commiteado en la rama
        self.assertIn("del modulo", html)
        self.assertIn("modulo-a:y.txt", result.stderr)  # sin explicación, con su prefijo
        self.assertIn("modulo-a:config.txt", result.stderr)
        self.assertNotIn(" x.txt", result.stderr)

    def test_el_mismo_archivo_en_dos_repos_no_se_confunde(self):
        write(self.repo / "config.txt", "b=1\n")
        self.with_meta(repos=self.repos, files={"config.txt": {"why": "nuevo en el principal"},
                                                "modulo-a:config.txt": {"why": "cambia en el modulo"}})
        self.ok()
        html = (self.repo / "reports" / "2026-01-02-prueba-x.html").read_text(encoding="utf-8")
        self.assertIn("nuevo en el principal", html)
        self.assertIn("cambia en el modulo", html)
        self.assertEqual(html.count('class="file-path">config.txt'), 2)

    def test_repo_relacionado_inaccesible_termina_y_dice_que_carpeta_hace_falta(self):
        self.with_meta(repos=[{"path": "../no-esta", "name": "pagos"}])
        result = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('No puedo leer el repo relacionado "pagos"', result.stderr)
        self.assertIn("no-esta", result.stderr)
        self.assertIn("acceso a esa carpeta", result.stderr)
        self.assertFalse((self.repo / "reports").exists())

    def test_el_cambio_que_pasa_una_dependencia_a_local_queda_fuera_como_temporal(self):
        write(self.repo / "dependencias.conf", "modulo-a = publicado:1.2.0\n")
        git(self.repo, "add", "dependencias.conf")
        git(self.repo, "commit", "-q", "-m", "dependencias")
        write(self.repo / "dependencias.conf", "modulo-a = local:../modulo-a\n")
        temporary = [{"path": "dependencias.conf", "why": "Usa el código local de modulo-a",
                      "revert": "modulo-a = publicado:1.2.0 <de nuevo>"}]
        self.with_meta(repos=self.repos, temporary=temporary)
        result = self.ok()
        html = (self.repo / "reports" / "2026-01-02-prueba-x.html").read_text(encoding="utf-8")
        self.assertIn("Cambios temporales", html)
        self.assertIn("modulo-a = publicado:1.2.0 &lt;de nuevo&gt;", html)
        self.assertNotIn("local:../modulo-a", html)  # sin diff: no es un cambio de la tarea
        self.assertEqual(self.stat(html, "Archivos Modificados"), "3")  # a.txt, modulo-a:x.txt y modulo-a:config.txt
        self.assertNotIn("dependencias.conf", result.stderr)

    def test_un_temporal_que_git_no_ve_solo_informa(self):
        self.with_meta(temporary=[{"path": "local.properties", "revert": "borrar la línea"}])
        result = self.ok()
        self.assertIn('"local.properties" no aparece entre los cambios', result.stderr)

    def test_una_entrada_que_apunta_al_principal_le_pone_nombre_y_base(self):
        commit_all(self.repo, "todo")
        write(self.repo / "a.txt", "tres\n")
        self.with_meta(repos=[{"path": ".", "name": "principal", "base": "HEAD~1"}] + self.repos)
        self.ok()
        html = (self.repo / "reports" / "2026-01-02-prueba-x.html").read_text(encoding="utf-8")
        self.assertIn('<span class="repo-tag">principal</span></td><td>main</td><td><code>HEAD~1</code>', html)
        self.assertIn("b.txt", html)  # commiteado después de HEAD~1: entra por la base

    def test_dos_repos_con_el_mismo_nombre_fallan(self):
        self.with_meta(repos=[{"path": "../modulo-a", "name": "repo-principal"}])
        result = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('dos repos se llaman "repo-principal"', result.stderr)


class AnalysisTest(Base):
    """Campos opcionales del análisis: pros, contras y riesgo por archivo; severidad, impacto, causa y diagramas."""

    FULL = {
        "severity": "alto",
        "impact": [{"label": "Usuarios <afectados>", "value": "Todos los que pagan <b>"}],
        "root_cause": "El valor <nulo> llegaba sin validar.",
        "diagrams": [{"title": "Flujo <pago>", "description": "Antes y después <ok>",
                      "mermaid": 'flowchart LR\n  A["<img src=x onerror=alert(1)>"] --> B & C'}],
        "files": {
            "a.txt": {"before": "x", "after": "y", "risk": "medio", "pros": ["Más simple <sí>"],
                      "cons": ["Un caso <raro>"]},
            "b.txt": {"why": "nuevo", "risk": "crítico", "cons": []},
        },
    }

    def html(self):
        return (self.repo / "reports" / "2026-01-02-prueba-x.html").read_text(encoding="utf-8")

    def test_muestra_los_campos_nuevos(self):
        self.with_meta(**self.FULL)
        self.ok()
        html = self.html()
        self.assertIn("Severidad alta", html)
        self.assertIn("Riesgo medio", html)
        self.assertIn("Riesgo crítico", html)  # acepta la tilde
        self.assertIn("Impacto", html)
        self.assertIn("Causa raíz", html)
        self.assertIn("Diagramas", html)
        self.assertIn("Sin contras identificados", html)  # b.txt trae "cons": []
        self.assertEqual(html.count("Sin contras identificados"), 1)  # a.txt sí tiene contras

    def test_escapa_el_html_de_todos_los_campos_nuevos_incluido_mermaid(self):
        self.with_meta(**self.FULL)
        self.ok()
        body = self.html().split("</style>", 1)[1]
        for raw in ("<afectados>", "<b>", "<nulo>", "<pago>", "<ok>", "<sí>", "<raro>", "<img"):
            self.assertNotIn(raw, body)
        self.assertIn("Usuarios &lt;afectados&gt;", body)
        self.assertIn('<pre class="mermaid">flowchart LR\n  A[&quot;&lt;img src=x onerror=alert(1)&gt;&quot;] '
                      "--&gt; B &amp; C</pre>", body)

    def test_con_diagramas_carga_mermaid_con_version_exacta_integridad_y_modo_estricto(self):
        self.with_meta(**self.FULL)
        self.ok()
        scripts = re.findall(r'<script src="([^"]+)" integrity="(sha384-[^"]+)" crossorigin="anonymous">', self.html())
        self.assertEqual(len(scripts), 1)
        self.assertRegex(scripts[0][0], r"^https://cdn\.jsdelivr\.net/npm/mermaid@11\.\d+\.\d+/dist/mermaid\.min\.js$")
        self.assertIn("securityLevel: 'strict'", self.html())

    def test_sin_diagramas_no_hay_script_remoto(self):
        self.with_meta(**dict(self.FULL, diagrams=[]))
        self.ok()
        self.assertNotIn("<script src=", self.html())
        self.assertNotIn("Diagramas", self.html())

    def test_cons_ausente_no_muestra_el_bloque(self):
        self.with_meta(files={"a.txt": {"why": "x", "pros": ["uno"]}})
        self.ok()
        self.assertIn("👍 Pros", self.html())
        self.assertNotIn("Contras", self.html())

    def test_valores_invalidos_fallan_con_un_error_claro_y_sin_escribir(self):
        cases = (
            {"files": {"a.txt": {"risk": "grave"}}},
            {"severity": "urgente"},
            {"files": {"a.txt": {"pros": "no es lista"}}},
            {"impact": [{"value": "sin label"}]},
            {"diagrams": [{"title": "sin código"}]},
            {"repos": [{"name": "sin path"}]},
        )
        for extra in cases:
            self.with_meta(**extra)
            result = self.generate()
            self.assertEqual(result.returncode, 1, extra)
            self.assertIn("✖", result.stderr)
            self.assertFalse((self.repo / "reports").exists(), extra)
        self.with_meta(severity="urgente")
        self.assertIn('critico, alto, medio o bajo (llegó "urgente")', self.generate().stderr)


if __name__ == "__main__":
    unittest.main()
