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


class ModuleMapsTest(Base):
    def test_versionado_deja_los_mapas_fuera_de_git_por_defecto_y_lo_dice(self):
        result = self.prepare("--modo", "versionado")
        self.assertIn("/docs/modules/", self.exclude())
        self.assertIn("en ### Mapas del módulo (la línea tal cual):\n  - En `docs/modules/<identificador>.md`, fuera de git",
                      result.stdout)
        self.assert_gitignore_intact()

    def test_versionado_con_mapas_versionados_no_los_excluye(self):
        result = self.prepare("--modo", "versionado", "--module-maps", "versioned")
        self.assertNotIn("docs/modules", self.exclude())
        self.assertIn("versionados con el código", result.stdout)

    def test_local_los_deja_dentro_de_la_carpeta_de_contexto(self):
        result = self.prepare("--modo", "local")
        self.assertIn("En `contexto/modules/<identificador>.md`, fuera de git (dentro de `contexto/`)", result.stdout)
        self.assertNotIn("modules", self.exclude())

    def test_mapas_versionados_sin_contexto_versionado_falla_sin_cambiar_nada(self):
        result = self.contexto("preparar", "--modo", "local", "--module-maps", "versioned")
        self.assertEqual(result.returncode, 1)
        self.assertIn("solo se versionan si el contexto se versiona", result.stderr)
        self.assertFalse((self.repo / "contexto").exists())

    def test_mapas_ya_versionados_y_pedidos_locales_se_detiene(self):
        write(self.repo / "docs" / "modules" / "app.md", "# app\n")
        commit_all(self.repo, "mapas")
        result = self.contexto("preparar", "--modo", "versionado")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/modules/ tiene archivos versionados", result.stderr)
        self.assertNotIn("docs/modules", self.exclude())

    def test_imprime_la_base_comun_de_reportes_y_la_fila_de_documentos(self):
        result = self.prepare("--modo", "local")
        self.assertIn("hb-implement en `contexto/reports/implementation/`", result.stdout)
        self.assertIn("hb-performance en `contexto/reports/performance/`", result.stdout)
        self.assertIn("hb-review en `contexto/reports/review/`", result.stdout)
        self.assertIn("`contexto/reports/INDEX.md`", result.stdout)
        self.assertIn("| `contexto/docs/arquitectura.md` |", result.stdout)

    def test_con_marcadores_la_base_es_la_parte_fija(self):
        result = self.prepare("--modo", "versionado", "--reportes", "reports/{fecha}/{slug}")
        self.assertIn("hb-review en `reports/review/`", result.stdout)
        self.assertIn("hb-implement usa la línea tal cual (`reports/{fecha}/{slug}`)", result.stdout)
        self.assertNotIn("hb-implement en", result.stdout)


class UnitsTest(Base):
    """contexto.py units: el inventario de solo lectura para ## Estructura."""

    def setUp(self):
        super().setUp()
        (self.base / "feature-payments").mkdir()
        self.payments = init_repo(self.base / "feature-payments")
        write(self.payments / "a.txt", "a\n")
        commit_all(self.payments)
        git(self.payments, "remote", "add", "origin", "https://usuario:secreto@git.example.com/team/feature-payments.git")
        write(self.repo / "settings.gradle.kts", 'include(":app")\ninclude(\n  ":features:payments:impl",\n)\n'
                                                   '// include(":comentado")\n')
        write(self.repo / "app" / "build.gradle.kts", "\n")
        write(self.repo / "features" / "payments" / "impl" / "build.gradle.kts", "\n")
        write(self.repo / "local-modules.json",
              '{"feature-payments": false, "core-lib": false, "paths": ["../feature-payments", "../core-lib"]}\n')
        write(self.repo / "src" / "web" / "pantalla.ts", 'import { x } from "../comun"\n')
        commit_all(self.repo, "modulos")

    def units(self):
        result = self.contexto("units")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_lista_los_modulos_y_los_repos_vecinos_clonados_y_sin_clonar(self):
        out = self.units()
        self.assertIn("  app  (módulo de Gradle :app", out)
        self.assertIn("  features/payments/impl  (módulo de Gradle :features:payments:impl", out)
        self.assertNotIn("comentado", out)
        self.assertIn("../core-lib  SIN CLONAR: pregunta la URL de su remoto  (como ruta: local-modules.json)", out)
        self.assertIn("../feature-payments  clonado; remoto: https://git.example.com/team/feature-payments.git; "
                      "rama principal: main", out)
        self.assertNotIn("secreto", out)
        self.assertNotIn("../comun", out)  # un import del código no es un repo vecino

    def test_el_archivo_modificado_que_nombra_vecinos_es_candidato_a_configuracion_local(self):
        write(self.repo / "local-modules.json", '{"feature-payments": true, "paths": ["../feature-payments"]}\n')
        write(self.repo / "app" / "build.gradle.kts", "// otro cambio\n")
        out = self.units()
        self.assertIn("«Configuración local modificada a propósito»", out)
        line = next(l for l in out.splitlines() if "Configuración local" in l)
        self.assertIn("local-modules.json", line)
        self.assertNotIn("build.gradle.kts", line)

    def test_no_cambia_nada(self):
        before, excluded = self.status(), self.exclude()
        self.units()
        self.assertEqual(self.status(), before)
        self.assertEqual(self.exclude(), excluded)

    def test_compara_con_el_modelo_de_agents(self):
        write(self.repo / "AGENTS.md", "# X\n\n## Estructura\n\n### Unidades\n\n"
              "| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal "
              "| Publica y versiona |\n| --- | --- | --- | --- | --- | --- | --- |\n"
              "| `app` | `app/` | Es la app | — | `cd x && ./gradlew :app:check` | este repo, `main` | con la app |\n"
              "| `core-lib` | `../core-lib` | Publicada | A fuente: x; volver: y | `cd x && make` | `u`, `main` | su repo |\n"
              "\n## Modernización\n")
        out = self.units()
        self.assertIn("En el modelo (estructura): app, core-lib", out)
        self.assertIn("⚠ core-lib: la fuente ../core-lib no existe en disco", out)
        missing = next(l for l in out.splitlines() if "Candidatos que no están en el modelo" in l)
        self.assertIn("features/payments/impl", missing)
        self.assertIn("../feature-payments", missing)
        self.assertNotIn("app,", missing)

    def test_lee_repos_relacionados_como_respaldo(self):
        write(self.repo / "AGENTS.md", "## Arquitectura\n\n### Repos relacionados\n\n| Repo | Ruta | Qué contiene | "
              "Cómo se incluye en local |\n| --- | --- | --- | --- |\n| feature-payments | `../feature-payments` | x | y |\n")
        out = self.units()
        self.assertIn("### Repos relacionados (formato anterior)", out)
        self.assertIn("En el modelo (repos relacionados): feature-payments", out)

    def test_espacio_de_trabajo_pnpm_y_carpetas_de_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write(repo / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n  - '!packages/ignorado'\n")
            write(repo / "packages" / "web" / "package.json", "{}\n")
            write(repo / "packages" / "web" / "src" / "features" / "payments" / "index.ts", "\n")
            write(repo / "packages" / "web" / "src" / "features" / "profile" / "index.ts", "\n")
            write(repo / "packages" / "sin-paquete" / "README.md", "\n")
            commit_all(repo)
            result = run([sys.executable, "-I", SCRIPT, "units", "--repo", repo], repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  packages/web  (paquete del espacio de trabajo (pnpm-workspace.yaml))", result.stdout)
        self.assertNotIn("sin-paquete", result.stdout)
        self.assertIn("packages/web/src/features/payments, packages/web/src/features/profile", result.stdout)


class UnitsModelTest(UnitsTest):
    """Arreglos de la validación: unidades anidadas, carpetas de feature, falsos vecinos y configuración registrada."""

    def model(self, rows, local=""):
        head = ("| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal "
                "| Publica y versiona |\n| --- | --- | --- | --- | --- | --- | --- |\n")
        body = "".join("| `%s` | `%s` | x | — | `x` | este repo, `main` | con la app |\n" % row for row in rows)
        extra = ("\n### Configuración local modificada a propósito\n\n- `%s`: motivo.\n" % local) if local else ""
        write(self.repo / "AGENTS.md", "# X\n\n## Estructura\n\n### Unidades\n\n" + head + body + extra
              + "\n## Modernización\n")

    def test_una_unidad_con_fuente_punto_cubre_los_modulos_del_repo(self):
        self.model([("app-shell", "."), ("feature-payments", "../feature-payments"), ("core-lib", "../core-lib")])
        out = self.units()
        self.assertNotIn("Candidatos que no están en el modelo", out)

    def test_si_todo_coincide_lo_confirma(self):
        (self.base / "core-lib").mkdir()
        init_repo(self.base / "core-lib")
        self.model([("app", "app/"), ("features/payments/impl", "features/payments/impl"),
                    ("feature-payments", "../feature-payments"), ("core-lib", "../core-lib")])
        out = self.units()
        self.assertIn("✔ El modelo cubre todos los candidatos", out)

    def test_la_configuracion_ya_registrada_no_vuelve_a_proponerse(self):
        write(self.repo / "local-modules.json", '{"feature-payments": true, "paths": ["../feature-payments"]}\n')
        self.model([("app-shell", ".")], local="local-modules.json")
        out = self.units()
        self.assertNotIn("confírmalos con el usuario): local-modules.json", out)
        self.assertIn("Configuración local modificada a propósito (ya en el modelo): local-modules.json", out)

    def test_un_worktree_del_mismo_repo_no_es_un_repo_vecino(self):
        git(self.repo, "worktree", "add", "-q", str(self.base / "repo-principal-wt"), "-b", "otra")
        write(self.repo / "notas.txt", "ver ../repo-principal-wt\n")
        commit_all(self.repo, "notas")
        self.assertNotIn("repo-principal-wt", self.units())

    def test_un_import_del_codigo_con_el_nombre_de_un_vecino_es_solo_candidato(self):
        (self.base / "comun").mkdir()
        init_repo(self.base / "comun")
        out = self.units()
        line = next(l for l in out.splitlines() if "../comun" in l)
        self.assertIn("candidato a confirmar", line)
        self.assertNotIn("../comun", "".join(l for l in out.splitlines() if "no están en el modelo" in l))

    def test_carpetas_de_feature_que_faltan_si_el_modelo_las_usa(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            for feature in ("payments", "profile"):
                write(repo / "src" / "features" / feature / "index.ts", "\n")
            write(repo / "docs" / "modules" / "src" / "features" / "payments" / "checkout.md", "# mapa\n")
            write(repo / "AGENTS.md", "## Estructura\n\n### Unidades\n\n| Unidad | Fuente |\n| --- | --- |\n"
                  "| `src/features/payments` | `src/features/payments` |\n")
            commit_all(repo)
            result = run([sys.executable, "-I", SCRIPT, "units", "--repo", repo], repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Carpetas de feature que no están en el modelo: src/features/profile", result.stdout)
        self.assertNotIn("docs/modules", result.stdout)


class UnreadableSiblingTest(Base):
    """CI: la carpeta padre del proyecto puede tener carpetas ajenas sin permiso (como /tmp en Linux)."""

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "como root no hay carpetas sin permiso")
    def test_estado_y_units_siguen_con_una_carpeta_hermana_sin_permiso(self):
        locked = self.base / "ajena"
        (locked / "dentro").mkdir(parents=True)
        os.chmod(str(locked), 0)
        try:
            for command in ("estado", "units"):
                result = self.contexto(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("ajena", result.stdout)
        finally:
            os.chmod(str(locked), 0o755)


class WorktreeTest(Base):
    """H10: en un worktree enlazado, los enlaces del contexto (que no están en git) faltan; estado lo dice."""

    def test_estado_dice_como_recrear_los_enlaces_que_faltan_sin_crearlos(self):
        self.prepare("--modo", "externo", "--externa", str(self.base / "fuera"))
        write(self.base / "fuera" / "AGENTS.md", "# X\n")
        worktree = self.base / "otro-worktree"
        git(self.repo, "worktree", "add", "-q", str(worktree), "-b", "trabajo")
        result = run([sys.executable, "-I", SCRIPT, "estado", "--repo", worktree], worktree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Worktree enlazado", result.stdout)
        self.assertIn("⚠ Falta AGENTS.md: en el principal es un enlace", result.stdout)
        self.assertIn("⚠ Falta contexto: en el principal es un enlace", result.stdout)
        self.assertIn("ln -s", result.stdout)
        self.assertIn("git ya lo ignora", result.stdout)
        self.assertFalse(os.path.lexists(str(worktree / "AGENTS.md")))
        self.assertFalse(os.path.lexists(str(worktree / "contexto")))

    def test_en_el_worktree_principal_no_dice_nada(self):
        self.prepare("--modo", "externo", "--externa", str(self.base / "fuera"))
        result = self.contexto("estado")
        self.assertNotIn("Worktree enlazado", result.stdout)


def load_script(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductTest(Base):
    """La sección ## Producto de hb-product: se conserva tal cual y su PRD va como fila de "Documentos"."""

    PRODUCT_LINE = "| Vayas a implementar una funcionalidad `F-…` del producto o a cambiar su alcance |"

    def producto(self, agents):
        write(self.repo / "AGENTS.md", agents)
        commit_all(self.repo, "agents")
        result = self.contexto("producto")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), agents)  # no escribe nada
        self.assertEqual(self.status(), "")
        return result.stdout

    def test_con_carpeta_da_la_fila_del_prd_de_esa_carpeta(self):
        write(self.repo / "docs" / "producto" / "04-prd.md", "# PRD de prueba\n")
        out = self.producto("# Riego\n\n## Producto\n\n- **Carpeta:** `./docs/producto/`\n\n## Git\n\n- nada\n")
        self.assertIn("consérvala tal cual", out)
        self.assertIn("Carpeta de producto: `./docs/producto/` (de la línea `Carpeta:`)", out)
        self.assertIn("PRD: `docs/producto/04-prd.md` existe", out)
        self.assertIn("  | `docs/producto/04-prd.md` " + self.PRODUCT_LINE, out)
        self.assertNotIn("product/04-prd.md", out)

    def test_sin_carpeta_usa_product_y_la_fila_va_aunque_el_prd_no_exista(self):
        out = self.producto("# Riego\n\n## Producto\n\nIdea de riego por turnos.\n\n## Git\n\n- Carpeta: otra\n")
        self.assertIn("Carpeta de producto: `product` (por defecto", out)
        self.assertIn("`product/04-prd.md` todavía no existe", out)
        self.assertIn("la fila va igual", out)
        self.assertIn("  | `product/04-prd.md` " + self.PRODUCT_LINE, out)
        self.assertFalse((self.repo / "product").exists())

    def test_sin_la_seccion_no_propone_nada_ni_la_crea(self):
        for agents in ("# Riego\n\n## Stack\n\n- Carpeta: docs/producto\n", "# Riego\n\n### Producto\n\n- x\n"):
            out = self.producto(agents)
            self.assertIn("AGENTS.md no tiene `## Producto`", out)
            self.assertIn("hb-setup no crea esa sección", out)
            self.assertNotIn("04-prd.md", out)
        (self.repo / "AGENTS.md").unlink()
        commit_all(self.repo, "sin agents")
        result = self.contexto("producto")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no tiene `## Producto`", result.stdout)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_una_carpeta_con_ruta_de_la_maquina_no_va_a_documentos(self):
        out = self.producto("# Riego\n\n## Producto\n\nCarpeta: /ruta/inventada/producto\n")
        self.assertIn("⚠ Es una ruta de la máquina", out)
        self.assertNotIn("04-prd.md", out)

    def test_lee_la_carpeta_igual_que_hb_product(self):
        contexto = load_script("contexto_hb_setup", SCRIPT)
        producto = load_script("producto_hb_product", ROOT / "skills" / "hb-product" / "scripts" / "producto.py")
        for line in ("Carpeta: docs/producto", "- **Carpeta:** `docs/producto`", "* Carpeta: docs/producto"):
            agents = "## Stack\n\n- x\n\n## Producto\n\n%s\n\n## Git\n" % line
            write(self.base / "lectura" / "AGENTS.md", agents)
            expected = producto.carpeta_de_agents(self.base / "lectura")
            self.assertEqual(self.base / "lectura" / contexto.product_section(agents)[0], expected, line)
        self.assertEqual(contexto.product_section("## Producto\n\n- x\n"), ("product", False))
        self.assertIsNone(contexto.product_section("## Stack\n\n- Carpeta: otra\n"))

    def test_los_demas_comandos_no_cambian_con_la_seccion(self):
        outputs = []
        for name, agents in (("sin", "# Riego\n\n## Stack\n\n- x\n"),
                             ("con", "# Riego\n\n## Stack\n\n- x\n\n## Producto\n\n- Carpeta: `docs/producto`\n")):
            parent = self.base / name
            (parent / "proyecto").mkdir(parents=True)
            repo = init_repo(parent / "proyecto")
            write(repo / "src" / "principal.txt", "codigo\n")
            write(repo / "AGENTS.md", agents)
            commit_all(repo, "base")
            found = []
            for command in (["estado"], ["units"], ["rendimiento"], ["preparar", "--modo", "versionado"]):
                result = run([sys.executable, "-I", SCRIPT, *command, "--repo", repo], repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                text = result.stdout
                for prefix in (str(parent.resolve()), str(parent)):
                    text = text.replace(prefix, "<base>")
                found.append(text)
            found.append((repo / "AGENTS.md").read_text(encoding="utf-8") == agents)
            outputs.append(found)
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(outputs[1][-1])


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

    def test_estructura_trae_las_unidades_con_acceso_y_como_volver(self):
        structure = self.section("## Estructura")
        self.assertNotIn("### Repos relacionados", self.text)
        self.assertIn("| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | "
                      "Repo y rama principal | Publica y versiona |", structure)
        self.assertIn("acceso", structure)
        self.assertIn("volver", structure)
        for title in ("### Unidades", "### Variantes y entornos", "### Cliente HTTP",
                      "### Configuración local modificada a propósito", "### Documentos", "### Mapas del módulo"):
            self.assertIn(title, structure)
        self.assertIn("- Repos vecinos: <clonar los que falten y preguntar la rama de trabajo | no clonar ni crear ramas>",
                      structure)
        self.assertIn("| Documento | Léelo cuando… |", structure)
        self.assertIn("| Variante o entorno | Para qué sirve | Servicios funcionales | Para probar y medir |", structure)

    def test_por_defecto_ninguna_skill_crea_ramas_sin_preguntar(self):
        """hb-setup 1.6.0: la línea por defecto ya no autoriza a crear ramas; la rama se pregunta una vez."""
        estructura = (SKILL / "references" / "estructura.md").read_text(encoding="utf-8")
        relacionados = (SKILL / "references" / "repos-relacionados.md").read_text(encoding="utf-8")
        self.assertRegex(self.skill, r'(?m)^  version: "1\.6\.0"$')
        for text in (self.text, estructura, relacionados, self.skill):
            self.assertNotIn("clonar los que falten y crear ramas de trabajo`", text.replace(
                "(`clonar los que falten y crear ramas de trabajo`)", ""))  # solo se nombra para migrarla
            self.assertNotIn("clonar los que falten y crear ramas de trabajo.", text)
            self.assertNotIn("crear ramas de trabajo?", text)
        self.assertIn("- Repos vecinos: clonar los que falten y preguntar la rama de trabajo.", estructura)
        self.assertIn("ninguna skill crea una rama por su cuenta", estructura)
        self.assertIn("si nadie responde, sigue en la actual", estructura)
        self.assertIn("`pull`, `merge` ni `rebase`", estructura)
        self.assertIn("Al actualizar un `AGENTS.md` con la línea de antes", estructura)
        self.assertIn("La rama de trabajo nunca la crea por su cuenta", self.skill)

    def test_estructura_va_entre_arquitectura_y_modernizacion(self):
        headings = re.findall(r"(?m)^## (.+)$", self.text)
        self.assertEqual(headings.index("Estructura"), headings.index("Arquitectura") + 1)
        self.assertEqual(headings.index("Modernización"), headings.index("Estructura") + 1)

    def test_las_tablas_de_la_plantilla_tienen_las_columnas_de_su_cabecera(self):
        for block in re.findall(r"(?m)((?:^\|.*\n)+)", self.text):
            rows = [line for line in block.splitlines() if line.strip()]
            widths = {len(re.sub(r"`[^`]*`", "x", row).strip().strip("|").split("|")) for row in rows}
            self.assertEqual(len(widths), 1, block)

    def test_la_plantilla_del_mapa_del_modulo_trae_el_commit_analizado(self):
        module_map = (SKILL / "assets" / "module-map.md").read_text(encoding="utf-8")
        self.assertIn("Commit analizado: `<sha completo>`", module_map)
        self.assertIn("git -C <repo> diff <commit analizado>..HEAD -- <ruta de la unidad>", module_map)
        self.assertTrue("references/estructura.md" in self.skill, "SKILL.md enlaza estructura.md")
        self.assertTrue("contexto.py units" in self.skill, "SKILL.md usa contexto.py units")

    def test_report_py_lee_la_carpeta_de_la_plantilla(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write(repo / "a.txt", "uno\n")
            for value, expected in (("reports", "reports/implementation/2026-01-02-x/report.html"),
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
