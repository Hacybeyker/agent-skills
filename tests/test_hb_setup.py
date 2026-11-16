"""hb-setup: contexto.py (modos del contexto de IA y CLAUDE.md solo si corresponde) y la plantilla de AGENTS.md."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, git, init_repo, run, write

SKILL = ROOT / "skills" / "hb-setup"
SCRIPT = SKILL / "scripts" / "contexto.py"
TEMPLATE = SKILL / "assets" / "AGENTS.template.md"
REPORT = ROOT / "skills" / "hb-implement" / "scripts" / "report.py"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "repo-principal").mkdir()
        self.repo = init_repo(self.base / "repo-principal")
        write(self.repo / "src" / "principal.txt", "codigo\n")
        write(self.repo / ".gitignore", "build/\n")
        commit_all(self.repo, "base")

    def tearDown(self):
        self.tmp.cleanup()

    def contexto(self, *args):
        return run([sys.executable, "-I", SCRIPT, *args, "--repo", self.repo], self.repo)

    def prepare(self, *args):
        result = self.contexto("preparar", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def exclude(self):
        path = self.repo / ".git" / "info" / "exclude"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def status(self):
        return run(["git", "status", "--porcelain", "--untracked-files=all"], self.repo).stdout

    def assert_gitignore_intact(self):
        self.assertEqual((self.repo / ".gitignore").read_text(encoding="utf-8"), "build/\n")


class ClaudeMdTest(Base):
    def test_sin_claude_md_ni_carpeta_claude_no_crea_claude_md(self):
        for mode in ("versionado", "local"):
            result = self.prepare("--modo", mode)
            self.assertFalse((self.repo / "CLAUDE.md").exists(), mode)
            self.assertIn("CLAUDE.md: no", result.stdout)

    def test_con_la_carpeta_claude_crea_claude_md_que_importa_agents(self):
        (self.repo / ".claude").mkdir()
        result = self.prepare("--modo", "versionado")
        self.assertEqual((self.repo / "CLAUDE.md").read_text(encoding="utf-8"), "@AGENTS.md\n")
        self.assertIn("CLAUDE.md creado", result.stdout)

    def test_un_claude_md_existente_no_se_pisa_y_avisa_si_no_importa_agents(self):
        write(self.repo / "CLAUDE.md", "Instrucciones propias\n")
        result = self.prepare("--modo", "versionado")
        self.assertEqual((self.repo / "CLAUDE.md").read_text(encoding="utf-8"), "Instrucciones propias\n")
        self.assertIn("no importa @AGENTS.md", result.stdout)

    def test_el_usuario_puede_confirmarlo_o_negarlo(self):
        self.prepare("--modo", "versionado", "--claude", "si")
        self.assertTrue((self.repo / "CLAUDE.md").is_file())
        (self.repo / "CLAUDE.md").unlink()
        (self.repo / ".claude").mkdir()
        self.prepare("--modo", "versionado", "--claude", "no")
        self.assertFalse((self.repo / "CLAUDE.md").exists())

    def test_en_modo_externo_sin_senales_no_hay_enlace_de_claude_md(self):
        self.prepare("--modo", "externo", "--externa", str(self.base / "fuera"))
        self.assertFalse(os.path.lexists(str(self.repo / "CLAUDE.md")))
        self.assertFalse((self.base / "fuera" / "CLAUDE.md").exists())


class ModesTest(Base):
    def test_versionado_no_excluye_el_contexto_y_deja_reports_fuera_de_git(self):
        result = self.prepare("--modo", "versionado")
        self.assertEqual(self.exclude().count("AGENTS.md"), 0)
        self.assertIn("/reports/\n", self.exclude())
        self.assertIn("Lo extenso, enlazado desde AGENTS.md, en docs/", result.stdout)
        self.assertIn("Contexto de IA: versionado", result.stdout)
        self.assertIn("Carpeta de reportes: `reports`", result.stdout)
        self.assert_gitignore_intact()

    def test_local_excluye_agents_y_la_carpeta_solo_con_info_exclude(self):
        (self.repo / ".claude").mkdir()
        result = self.prepare("--modo", "local")
        for line in ("/AGENTS.md\n", "/CLAUDE.md\n", "/contexto/\n"):
            self.assertIn(line, self.exclude())
        self.assertNotIn("/reports/", self.exclude())  # contexto/reports ya está cubierta
        write(self.repo / "AGENTS.md", "# Proyecto\n")
        write(self.repo / "contexto" / "docs" / "arquitectura.md", "detalle\n")
        write(self.repo / "contexto" / "reports" / "r.html", "x\n")
        self.assertEqual(self.status(), "")  # .claude/ vacía no cuenta para git
        self.assertIn("contexto/docs/", result.stdout)
        self.assertIn("Carpeta de reportes: `contexto/reports`", result.stdout)
        self.assert_gitignore_intact()

    def test_local_con_agents_versionado_se_detiene_sin_cambiar_nada(self):
        write(self.repo / "AGENTS.md", "# Proyecto\n")
        commit_all(self.repo, "agents")
        result = self.contexto("preparar", "--modo", "local")
        self.assertEqual(result.returncode, 1)
        self.assertIn("AGENTS.md está versionado", result.stderr)
        self.assertEqual(self.exclude().count("AGENTS.md"), 0)
        self.assertFalse((self.repo / "contexto").exists())

    def test_externo_crea_enlaces_excluidos_y_no_toca_gitignore(self):
        external = self.base / "fuera"
        result = self.prepare("--modo", "externo", "--externa", str(external),
                              "--reportes", "contexto/reports/{fecha}/{slug}")
        self.assertTrue((self.repo / "AGENTS.md").is_symlink())
        self.assertTrue((self.repo / "contexto").is_symlink())
        self.assertFalse(os.path.isabs(os.readlink(str(self.repo / "contexto"))))  # relativo
        self.assertEqual(os.path.realpath(str(self.repo / "contexto")), os.path.realpath(str(external / "contexto")))
        self.assertIn("/AGENTS.md\n", self.exclude())
        self.assertIn("/contexto\n", self.exclude())  # sin barra: git ve el enlace como archivo
        self.assertNotIn("/contexto/\n", self.exclude())
        (external / "AGENTS.md").write_text("# Proyecto\n", encoding="utf-8")
        write(self.repo / "contexto" / "docs" / "detalle.md", "x\n")  # a través del enlace
        self.assertTrue((external / "contexto" / "docs" / "detalle.md").is_file())
        self.assertEqual(self.status(), "")
        self.assertRegex(result.stdout, r"AGENTS\.md en \S*fuera/AGENTS\.md")  # se escribe en la carpeta externa
        self.assertIn("Carpeta de reportes: `contexto/reports/{fecha}/{slug}`", result.stdout)
        self.assert_gitignore_intact()

    def test_externo_no_pisa_lo_que_ya_hay_en_la_carpeta_externa(self):
        external = self.base / "fuera"
        write(external / "AGENTS.md", "# Contexto propio\n")
        write(external / "contexto" / "docs" / "previo.md", "previo\n")
        result = self.prepare("--modo", "externo", "--externa", str(external))
        self.assertEqual((external / "AGENTS.md").read_text(encoding="utf-8"), "# Contexto propio\n")
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), "# Contexto propio\n")
        self.assertEqual((external / "contexto" / "docs" / "previo.md").read_text(encoding="utf-8"), "previo\n")
        self.assertIn("ya existe: lo uso tal cual", result.stdout)
        self.assertIn("ya tiene contenido", result.stdout)

    def test_externo_con_un_agents_real_en_el_repo_se_detiene_sin_tocar_nada(self):
        write(self.repo / "AGENTS.md", "# Local\n")
        external = self.base / "fuera"
        result = self.contexto("preparar", "--modo", "externo", "--externa", str(external))
        self.assertEqual(result.returncode, 1)
        self.assertIn("AGENTS.md ya existe en el repo", result.stderr)
        self.assertFalse((self.repo / "AGENTS.md").is_symlink())
        self.assertFalse(os.path.lexists(str(self.repo / "contexto")))
        self.assertFalse(external.exists())
        self.assertEqual(self.exclude().count("contexto"), 0)

    def test_externo_con_un_archivo_donde_va_la_carpeta_se_detiene_sin_tocar_nada(self):
        external = self.base / "fuera"
        write(external / "contexto", "soy un archivo\n")
        result = self.contexto("preparar", "--modo", "externo", "--externa", str(external))
        self.assertEqual(result.returncode, 1)
        self.assertIn("ya existe y es un archivo", result.stderr)
        self.assertFalse(os.path.lexists(str(self.repo / "AGENTS.md")))
        self.assertEqual(self.exclude().count("AGENTS.md"), 0)
        self.assertEqual((external / "contexto").read_text(encoding="utf-8"), "soy un archivo\n")

    def test_externo_repetido_no_duplica_ni_cambia_nada(self):
        external = self.base / "fuera"
        self.prepare("--modo", "externo", "--externa", str(external))
        before = (self.exclude(), os.readlink(str(self.repo / "contexto")))
        result = self.prepare("--modo", "externo", "--externa", str(external))
        self.assertEqual((self.exclude(), os.readlink(str(self.repo / "contexto"))), before)
        self.assertIn("ya enlazado", result.stdout)

    def test_externo_dentro_del_repo_falla(self):
        result = self.contexto("preparar", "--modo", "externo", "--externa", str(self.repo / "adentro"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no puede estar dentro del repo", result.stderr)


class StatusTest(Base):
    def test_detecta_el_modo_los_submodulos_y_los_repos_hermanos_que_nombra(self):
        (self.base / "modulo-a").mkdir()
        init_repo(self.base / "modulo-a")
        (self.base / "otro-sin-uso").mkdir()
        init_repo(self.base / "otro-sin-uso")
        (self.base / "catalogo").mkdir()
        init_repo(self.base / "catalogo")
        write(self.repo / "config" / "dependencias.conf", "modulo-a = local:../modulo-a\n")
        write(self.repo / "versiones.txt", "catalogo = 3.1.0\n")  # una dependencia publicada con el nombre del repo
        write(self.repo / ".gitmodules", '[submodule "libs/comun"]\n\tpath = libs/comun\n\turl = ../comun\n')
        commit_all(self.repo, "config")
        self.prepare("--modo", "externo", "--externa", str(self.base / "fuera"))
        result = self.contexto("estado")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Modo del contexto: externo", result.stdout)
        self.assertIn("Submódulos: libs/comun", result.stdout)
        self.assertIn("../modulo-a  (como ruta: config/dependencias.conf)", result.stdout)
        self.assertIn("../catalogo  (por nombre, candidato a confirmar: versiones.txt)", result.stdout)
        self.assertNotIn("otro-sin-uso", result.stdout)
        self.assertIn("Claude Code por defecto: no", result.stdout)


class TemplateTest(unittest.TestCase):
    """La plantilla de hb-setup escribe lo que hb-implement lee."""

    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    def section(self, title):
        start = self.text.index(title)
        end = self.text.find("\n## ", start + 1)
        return self.text[start:end if end != -1 else len(self.text)]

    def test_reglas_trae_la_carpeta_de_reportes_por_defecto_y_el_contexto(self):
        rules = self.section("## Reglas del proyecto")
        self.assertIn("- Carpeta de reportes: `reports`", rules)
        self.assertIn("Contexto de IA:", rules)

    def test_arquitectura_trae_repos_relacionados_con_acceso_y_como_volver(self):
        architecture = self.section("## Arquitectura")
        self.assertIn("### Repos relacionados", architecture)
        self.assertIn("acceso", architecture)
        self.assertIn("volver", architecture)

    def test_report_py_lee_la_carpeta_de_la_plantilla(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write(repo / "a.txt", "uno\n")
            for value, expected in (("reports", "reports/2026-01-02-x.html"),
                                    ("contexto/reports/{fecha}/{slug}", "contexto/reports/2026-01-02/x/report.html")):
                write(repo / "AGENTS.md", self.text.replace("- Carpeta de reportes: `reports`",
                                                            "- Carpeta de reportes: `%s`" % value))
                commit_all(repo, value)
                meta = Path(tmp) / "fuera.json"
                meta.write_text(json.dumps({"title": "x", "date": "2026-01-02"}), encoding="utf-8")
                result = run([sys.executable, "-I", REPORT, "--meta", meta, "--repo", repo], repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((repo / expected).is_file(), result.stdout)
                meta.unlink()

    def test_la_skill_no_crea_claude_md_siempre(self):
        self.assertNotIn("más el CLAUDE.md que lo importa", self.skill)
        self.assertRegex(self.skill, r"`CLAUDE\.md`[^\n]*solo si")
        self.assertIn("contexto.py", self.skill)

    def test_la_skill_pide_el_modo_del_contexto_y_nunca_edita_gitignore(self):
        self.assertIn("versionado", self.skill)
        self.assertIn(".git/info/exclude", self.skill)
        for phrase in re.findall(r"[^\n]*\.gitignore[^\n]*", self.skill):
            self.assertNotRegex(phrase, r"(?i)\b(agrega|edita|escribe)\b[^.]*\.gitignore")


if __name__ == "__main__":
    unittest.main()
