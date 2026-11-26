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


# ── 1.6.0: fuentes previas de contexto de IA, inventario de traspaso y estructura más profunda ─────────────────────────
PERF_BLOCK = ("<!-- hb-performance:estado -->\n- Estado del setup (lo mantiene `perf.py`: no lo edites): instrumentación "
              "en el repo: no · hb-performance 0.21.0\n<!-- /hb-performance:estado -->")
PERF_SECTION = "## Rendimiento\n\n- Se mide con la variante `benchmark`.\n\n" + PERF_BLOCK + "\n"
RULE = "- Los textos visibles van en `strings.xml`, nunca en el código: el equipo de traducción solo lee ese archivo."
PUBLISH = "- Desde `develop` se publica la versión `-SNAPSHOT`; desde `main`, la versión final del tag."


def old_agents():
    """Un AGENTS.md antiguo y extenso, con datos inventados: lo que el usuario renombró antes de correr hb-setup."""
    errors = "\n".join("| `Could not resolve com.ejemplo.huerta:modulo-%02d:1.%d` | Falta el repo en Maven local | "
                       "`./gradlew :modulo-%02d:publishToMavenLocal` |" % (n, n, n) for n in range(1, 121))
    protocol = "\n".join("%d. Paso %d del protocolo: reproduce, escribe el test, corrige y verifica." % (n, n)
                         for n in range(1, 16))
    return ("# App Huerta\n\nApp Android para planificar el riego y la cosecha de huertas urbanas.\n\n"
            "## Stack\n\n- Kotlin, Compose, Hilt, Retrofit y Room.\n- minSdk 26.\n\n"
            "## Comandos\n\n- Compilar: `./gradlew :app:assembleDebug`\n- Tests: `./gradlew test`\n\n"
            "## Build\n\nEl build toma las versiones de `gradle/libs.versions.toml`.\n\n"
            "### Errores frecuentes\n\n| Mensaje exacto | Causa | Solución |\n| --- | --- | --- |\n" + errors + "\n\n"
            "## Publicación\n\n" + PUBLISH + "\n\n"
            "## Unidades\n\n- Los módulos `feature-*` viven en `../feature-<nombre>`.\n"
            "- `nucleo` es la excepción: vive en `../nucleo-compartido-android`.\n"
            "- `feature-alertas` no está en `modulos-locales.json`: se consume publicada.\n"
            "- `sdk-sensores` vive en otro host.\n\n"
            "## Sincronización del workspace\n\n`scripts/sincronizar-workspace.sh` clona los repos que faltan, los "
            "pone en `develop` y hace pull.\n- Descarta los cambios locales de `nucleo-compartido-android`.\n\n"
            "## Reglas\n\n" + RULE + "\n\n"
            "## Protocolo de bugfix\n\n" + protocol + "\n\n" + PERF_SECTION + "\n"
            "## Historial\n\n- Hace años se migró de Java a Kotlin.\n")


def new_agents(extra_rules="", documents="", perf=PERF_SECTION, publish=PUBLISH):
    """El AGENTS.md que escribiría el agente al migrar: corto, con lo esencial y el resto en docs referenciados."""
    return ("# App Huerta\n\nApp Android para planificar el riego y la cosecha de huertas urbanas.\n\n"
            "## Stack\n\n- Perfil: hb-stack-mobile-kotlin\n- Variante: android\n- Kotlin, Compose, Hilt, Retrofit y "
            "Room; minSdk 26. Versiones en `gradle/libs.versions.toml`.\n\n"
            "## Comandos\n\n| Para | Comando |\n| --- | --- |\n| Compilar | `cd <ruta del proyecto> && ./gradlew "
            ":app:assembleDebug` |\n| Tests | `cd <ruta del proyecto> && ./gradlew test` |\n\n"
            "## DoD\n\n1. `cd <ruta del proyecto> && ./gradlew test :app:assembleDebug`\n\nOrigen: DoD derivado del "
            "build; el proyecto no tiene CI.\n\n"
            "## Arquitectura\n\nUn módulo `app` y las features en repos vecinos.\n\n"
            "## Estructura\n\n### Unidades\n\n| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la "
            "unidad | Repo y rama principal | Publica y versiona |\n| --- | --- | --- | --- | --- | --- | --- |\n"
            "| `app` | `.` | Es la app | — | `cd <ruta del proyecto> && ./gradlew test` | este repo, `main` | la "
            "persona, con `hb-release` |\n"
            "| `nucleo` | `../nucleo-compartido-android` | Publicada: `com.ejemplo.huerta:nucleo`, versión fijada en "
            "`gradle/libs.versions.toml` | A fuente: `true` en `modulos-locales.json`; volver: `false` | `cd <ruta del "
            "proyecto>/../nucleo-compartido-android && ./gradlew check` | `https://git.ejemplo.com/huerta/nucleo.git`, "
            "`main` | su repo |\n\n- Excepciones: `nucleo` vive en `../nucleo-compartido-android`, fuera del patrón "
            "`../{clave}`.\n- Repos vecinos: clonar los que falten y preguntar la rama de trabajo.\n\n"
            "### Documentos\n\n| Documento | Léelo cuando… |\n| --- | --- |\n"
            "| `contexto/docs/troubleshooting.md` | El build falle: trae los mensajes exactos y su solución |\n"
            "| `contexto/docs/sincronizacion.md` | Vayas a correr el script de sincronización del espacio de trabajo |\n"
            + documents + "\n## Modernización\n\n- ninguna decidida\n- Los agentes no migran ni proponen migrar fuera "
            "de lo decidido aquí.\n\n"
            "## Reglas del proyecto\n\n- Contexto de IA: fuera del repo, con enlaces simbólicos.\n"
            "- Carpeta de reportes: `contexto/reports`\n" + RULE + "\n" + extra_rules + "\n"
            "## Git\n\n- Commits: Conventional Commits, en español, sin emoji.\n\n"
            "## Versionado y release\n\n" + publish + "\n\n" + perf + "\n## Seguridad\n\n- Nada sensible.\n")


INVENTORY = """| Fuente | Sección | Destino | Motivo o "Léelo cuando…" |
| --- | --- | --- | --- |
| `contexto/AGENTS-old.md` | (inicio) | AGENTS.md | título y descripción |
| `contexto/AGENTS-old.md` | Stack | AGENTS.md | ## Stack |
| `contexto/AGENTS-old.md` | Comandos | AGENTS.md | ## Comandos |
| `contexto/AGENTS-old.md` | Build › (inicio) | AGENTS.md | ## Stack |
| `contexto/AGENTS-old.md` | Build › Errores frecuentes | `contexto/docs/troubleshooting.md` | El build falle |
| `contexto/AGENTS-old.md` | Publicación | AGENTS.md | ## Versionado y release |
| `contexto/AGENTS-old.md` | Unidades | AGENTS.md | ## Estructura |
| `contexto/AGENTS-old.md` | Sincronización del workspace | `contexto/docs/sincronizacion.md` | Antes de sincronizar |
| `contexto/AGENTS-old.md` | Reglas | AGENTS.md | ## Reglas del proyecto |
| `contexto/AGENTS-old.md` | Protocolo de bugfix | descartada | ya la cubre hb-implement |
| `contexto/AGENTS-old.md` | Rendimiento | AGENTS.md | tal cual |
| `contexto/AGENTS-old.md` | Historial | descartada | obsoleta: describe una migración terminada |
| `contexto/protocolo-bugfix.md` | (todo el archivo) | descartada | ya lo cubre hb-implement |
| `contexto/plantilla-reporte.md` | (todo el archivo) | descartada | ya la cubre el reporte de hb-implement |
"""


class HuertaBase(unittest.TestCase):
    """Un proyecto sintético con un AGENTS-old.md extenso en una carpeta de contexto enlazada, sin AGENTS.md, con un
    archivo de sustitución, un repo vecino en otro host, un script de sincronización y skills locales."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        (self.base / "app-huerta").mkdir()
        self.repo = init_repo(self.base / "app-huerta")
        git(self.repo, "remote", "add", "origin", "https://git.ejemplo.com/huerta/app-huerta.git")
        write(self.repo / "settings.gradle.kts", 'include(":app")\n')
        write(self.repo / "app" / "build.gradle.kts", "dependencies { implementation(libs.feature.riego) }\n")
        write(self.repo / "gradle" / "libs.versions.toml", "[libraries]\n" + "".join(
            '%s = { module = "com.ejemplo.huerta:%s", version.ref = "huerta" }\n' % (name, name)
            for name in ("feature-riego", "feature-clima", "feature-cosecha", "nucleo", "feature-alertas"))
            + 'sensores = { module = "com.terceros.sensores:sdk-sensores", version = "2.1.0" }\n')
        write(self.repo / "modulos-locales.json", json.dumps({"modulos": [
            {"nombre": "feature-riego", "ruta": "../feature-riego"},
            {"nombre": "feature-clima", "ruta": "../feature-clima"},
            {"nombre": "feature-cosecha", "ruta": "../feature-cosecha"},
            {"nombre": "nucleo", "ruta": "../nucleo-compartido-android"}]}, indent=2) + "\n")
        write(self.repo / "scripts" / "sincronizar-workspace.sh", "#!/bin/sh\n"
              "for repo in feature-riego feature-clima feature-cosecha; do\n"
              "  [ -d ../$repo ] || git clone https://git.ejemplo.com/huerta/$repo.git ../$repo\n"
              "  git -C ../$repo checkout develop\n  git -C ../$repo pull --rebase\ndone\n"
              "[ -d ../sdk-sensores ] || git clone https://otro-host.ejemplo.org/terceros/sdk-sensores.git "
              "../sdk-sensores\ngit -C ../nucleo-compartido-android reset --hard origin/develop\n")
        write(self.repo / ".claude" / "skills" / "revision-huerta" / "SKILL.md",
              "---\nname: revision-huerta\ndescription: Checklist de revisión de código de la huerta\n---\n\n"
              "# Revisión\n\n- Revisa los textos en `strings.xml`.\n")
        commit_all(self.repo, "base")
        for name, url in (("feature-riego", "https://git.ejemplo.com/huerta/feature-riego.git"),
                          ("sdk-sensores", "https://otro-host.ejemplo.org/terceros/sdk-sensores.git")):
            (self.base / name).mkdir()
            sibling = init_repo(self.base / name)
            write(sibling / "README.md", "x\n")
            commit_all(sibling)
            git(sibling, "remote", "add", "origin", url)
        self.outside = self.base / "fuera"
        context = self.outside / "contexto"
        write(context / "AGENTS-old.md", old_agents())
        write(context / "protocolo-bugfix.md", "---\nname: protocolo-bugfix\ndescription: Cómo corregir un bug en la "
              "huerta\n---\n\n# Protocolo de bugfix\n\n1. Reproduce.\n2. Corrige con un test.\n")
        write(context / "plantilla-reporte.md", "# Plantilla de reporte\n\n- Qué cambió y por qué.\n")
        write(context / "docs" / "glosario.md", "# Glosario\n\n- Bancal: la unidad de cultivo.\n")
        write(context / "reports" / "INDEX.md", "# Índice\n\nEl agente dejó un reporte.\n")
        os.symlink(os.path.join("..", "fuera", "contexto"), str(self.repo / "contexto"))
        with open(str(self.repo / ".git" / "info" / "exclude"), "a", encoding="utf-8") as handle:
            handle.write("/contexto\n")

    def tearDown(self):
        self.tmp.cleanup()

    def contexto(self, *args, code=0):
        result = run([sys.executable, "-I", SCRIPT, *args, "--repo", self.repo], self.repo)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def status(self):
        return run(["git", "status", "--porcelain", "--untracked-files=all"], self.repo).stdout

    def migrate(self, agents=None, inventory=INVENTORY):
        """Lo que haría el agente: prepara el modo externo, escribe AGENTS.md (en la ruta real), los docs y el
        inventario fuera del repo."""
        self.contexto("preparar", "--modo", "externo", "--externa", str(self.outside))
        write(self.outside / "AGENTS.md", agents if agents is not None else new_agents())
        old = old_agents()
        errors = old[old.index("### Errores frecuentes"):old.index("## Publicación")]
        write(self.outside / "contexto" / "docs" / "troubleshooting.md", "# Errores frecuentes del build\n\n"
              + errors.split("\n", 2)[2])
        write(self.outside / "contexto" / "docs" / "sincronizacion.md", "# Sincronización del espacio de trabajo\n\n"
              "- `scripts/sincronizar-workspace.sh` clona, pasa a `develop` y hace pull.\n- Descarta los cambios "
              "locales de `nucleo-compartido-android` (reset --hard).\n")
        self.inventory = self.base / "inventario.md"
        write(self.inventory, inventory)

    def verificar(self, code=0):
        return self.contexto("verificar", "--inventario", str(self.inventory), code=code)


class PreviousSourcesTest(HuertaBase):
    def test_una_fuente_renombrada_sin_agents_md_lleva_a_migrar(self):
        self.assertFalse(os.path.lexists(str(self.repo / "AGENTS.md")))
        out = self.contexto("fuentes")
        self.assertIn("Camino: migrar, aunque no exista AGENTS.md", out)
        self.assertIn("contexto/AGENTS-old.md (variante renombrada de AGENTS.md", out)
        self.assertIn("se reemplaza: por defecto, propón borrarla después de migrar", out)
        self.assertNotIn("glosario.md (", out)  # no trae instrucciones para agentes: solo se nombra
        self.assertIn("Otros .md de la carpeta de contexto", out)
        self.assertNotIn("reports/INDEX.md", out)  # salidas de las skills, no fuentes
        state = self.contexto("estado")
        self.assertIn("Fuentes previas de contexto de IA: contexto/AGENTS-old.md", state)
        self.assertIn("camino: migrar", state)

    def test_sin_fuentes_el_camino_es_la_plantilla(self):
        os.unlink(str(self.repo / "contexto"))
        self.assertIn("Camino: plantilla", self.contexto("fuentes"))
        self.assertIn("ninguna → camino: plantilla", self.contexto("estado"))

    def test_encuentra_las_variantes_y_los_archivos_de_otros_agentes(self):
        write(self.repo / "AGENTS.bak.md", "# Viejo\n\n- x\n")
        write(self.repo / "AGENTS.md.orig", "# Más viejo\n")
        write(self.repo / ".github" / "copilot-instructions.md", "- Usa Compose.\n")
        write(self.repo / ".cursorrules", "Responde en español.\n")
        write(self.repo / ".cursor" / "rules" / "estilo.mdc", "---\nalwaysApply: true\n---\n- Sin emoji.\n")
        write(self.repo / "CLAUDE.md", "@AGENTS.md\n")  # solo importa AGENTS.md: no es una fuente
        write(self.repo / "CLAUDE.local.md", "notas personales\n")
        out = self.contexto("fuentes")
        for path in ("AGENTS.bak.md", "AGENTS.md.orig", ".github/copilot-instructions.md", ".cursorrules",
                     ".cursor/rules/estilo.mdc"):
            self.assertIn("  - %s (" % path, out)
        self.assertNotIn("  - CLAUDE.md (", out)
        self.assertNotIn("CLAUDE.local.md", out)
        write(self.repo / "CLAUDE.md", "@AGENTS.md\n\n- Usa el modo plan antes de tocar Gradle.\n")
        self.assertIn("  - CLAUDE.md (instrucciones de Claude Code", self.contexto("fuentes"))

    def test_el_inventario_sugiere_los_tres_destinos_y_parte_lo_extenso(self):
        out = self.contexto("fuentes")
        table = [line for line in out.splitlines() if line.startswith("| `contexto/AGENTS-old.md`")]
        rows = {line.split(" | ")[1]: line for line in table}
        self.assertIn("AGENTS.md › ## Stack", rows["Stack"])
        self.assertIn("doc: `<docs>/troubleshooting.md`", rows["Build › Errores frecuentes"])
        self.assertIn("Build › (inicio)", rows)  # la sección larga va por partes
        self.assertIn("AGENTS.md › ## Versionado y release", rows["Publicación"])
        self.assertIn("doc: `<docs>/sincronizacion.md`", rows["Sincronización del workspace"])
        self.assertIn("descartada si ya la cubre `hb-implement` (bugfix)", rows["Protocolo de bugfix"])
        self.assertIn("AGENTS.md, tal cual (es de hb-performance)", rows["Rendimiento"])
        self.assertIn("| (todo el archivo) |", out)

    def test_bloque_de_hb_performance_en_una_fuente_renombrada(self):
        out = self.contexto("fuentes")
        self.assertIn("contexto/AGENTS-old.md: bloque <!-- hb-performance:estado -->", out)
        self.assertIn("## Rendimiento (hb-performance; corre `contexto.py rendimiento`)", out)
        perf = self.contexto("rendimiento")
        self.assertIn("La sección de rendimiento está en `contexto/AGENTS-old.md` (fuente previa)", perf)
        self.assertIn(PERF_BLOCK.splitlines()[1], perf)  # el bloque, para conservarlo tal cual
        self.assertIn("AGENTS.md no tiene `## Producto`", self.contexto("producto"))

    def test_producto_en_una_fuente_renombrada(self):
        write(self.outside / "contexto" / "AGENTS-old.md", old_agents() + "\n## Producto\n\n- Carpeta: `producto`\n")
        out = self.contexto("producto")
        self.assertIn("`## Producto` está en `contexto/AGENTS-old.md` (fuente previa)", out)
        self.assertIn("  | `producto/04-prd.md` |", out)

    def test_skill_local_solapada_se_informa_y_no_se_borra(self):
        before = self.status()
        out = self.contexto("fuentes")
        self.assertIn("Se solapan con skills hb-*", out)
        self.assertIn("propón retirarlas; no las borres", out)
        self.assertIn("contexto/protocolo-bugfix.md ↔ `hb-implement` (bugfix)", out)
        self.assertIn("contexto/plantilla-reporte.md ↔ `hb-implement` (reporte de cambios)", out)
        self.assertIn(".claude/skills/revision-huerta/SKILL.md ↔ `hb-review` (code review)", out)
        self.assertTrue((self.repo / ".claude" / "skills" / "revision-huerta" / "SKILL.md").is_file())
        self.assertTrue((self.outside / "contexto" / "protocolo-bugfix.md").is_file())
        self.assertEqual(self.status(), before)

    def test_fuentes_no_cambia_nada(self):
        before, excluded = self.status(), (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        for command in ("fuentes", "rendimiento", "producto", "units", "estado"):
            self.contexto(command)
        self.assertEqual(self.status(), before)
        self.assertEqual((self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8"), excluded)
        self.assertFalse(os.path.lexists(str(self.repo / "AGENTS.md")))


class StructureDetailsTest(HuertaBase):
    def test_excepciones_de_carpeta_del_archivo_de_sustitucion(self):
        out = self.contexto("units")
        self.assertIn("  modulos-locales.json: 4 entradas; patrón dominante: ../{clave}", out)
        line = next(l for l in out.splitlines() if "Fuera del patrón" in l)
        self.assertIn("nucleo → ../nucleo-compartido-android", line)
        self.assertNotIn("feature-riego", line)

    def test_dependencias_del_build_fuera_del_archivo_de_sustitucion(self):
        line = next(l for l in self.contexto("units").splitlines() if "Dependencias del build" in l)
        self.assertIn("com.ejemplo.huerta:feature-alertas (gradle/libs.versions.toml)", line)
        self.assertNotIn("feature-riego", line)
        self.assertNotIn("sdk-sensores", line)  # otro grupo: no es de las unidades sustituibles

    def test_repos_en_otro_host_y_scripts_de_sincronizacion(self):
        out = self.contexto("units")
        hosts = next(l for l in out.splitlines() if l.startswith("Repos en otro host"))
        self.assertIn("(git.ejemplo.com)", hosts)
        self.assertIn("../sdk-sensores (https://otro-host.ejemplo.org/terceros/sdk-sensores.git)", hosts)
        self.assertNotIn("feature-riego", hosts)
        self.assertIn("  scripts/sincronizar-workspace.sh: clona (2), actualiza con pull (1), cambia de rama (1), "
                      "descarta cambios con reset --hard (1)", out)
        self.assertIn("ramas: develop", out)
        self.assertIn("⚠ Puede descartar o borrar cambios locales (descarta cambios con reset --hard)", out)
        self.assertIn("con su fila en «Documentos»", out)

    def test_un_proyecto_sin_sustitucion_ni_scripts_no_imprime_nada_de_eso(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write(repo / "settings.gradle.kts", 'include(":app")\n')
            commit_all(repo)
            result = run([sys.executable, "-I", SCRIPT, "units", "--repo", repo], repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ("sustitución", "otro host", "sincronización"):
            self.assertNotIn(text, result.stdout)


class VerifyTest(HuertaBase):
    """De punta a punta: el proyecto con AGENTS-old.md extenso y sin AGENTS.md, migrado como lo haría el agente."""

    def test_de_punta_a_punta_nada_se_pierde(self):
        self.migrate()
        out = self.verificar()
        self.assertIn("✔ Nada se pierde", out)
        self.assertNotIn("✖", out)
        self.assertNotIn("no viene de ninguna fuente previa", out)
        self.assertNotIn("no quedó tal cual", out)
        self.assertIn("Pregunta si se conservan (por defecto, borrarlas después de migrar): contexto/AGENTS-old.md", out)
        agents = (self.outside / "AGENTS.md").read_text(encoding="utf-8")
        self.assertLess(agents.count("\n"), 150)
        self.assertIn(PERF_BLOCK, agents)
        self.assertNotIn("AGENTS-old.md", agents)
        rules = agents.split("## Reglas del proyecto", 1)[1].split("\n## ", 1)[0]
        self.assertIn(RULE, rules)  # la regla propia, tal cual y en su sección
        self.assertTrue((self.outside / "contexto" / "AGENTS-old.md").is_file())  # se borra solo si el usuario lo aprueba

    def test_documentos_nunca_referencia_la_fuente_reemplazada(self):
        self.migrate(new_agents(documents="| `contexto/AGENTS-old.md` | Necesites el detalle de antes |\n"))
        out = self.verificar(code=1)
        self.assertIn("\"Documentos\" referencia `contexto/AGENTS-old.md`, una fuente que se reemplaza", out)
        self.assertIn("AGENTS.md nombra `AGENTS-old.md`", out)
        inventory = INVENTORY.replace("| Historial | descartada |", "| Historial | `contexto/AGENTS-old.md` |")
        self.migrate(inventory=inventory)
        self.assertIn("el destino es `contexto/AGENTS-old.md`, la fuente que se reemplaza", self.verificar(code=1))

    def test_el_inventario_con_los_tres_destinos_se_valida(self):
        cases = (
            (INVENTORY.replace("| `contexto/AGENTS-old.md` | Historial | descartada | obsoleta: describe una "
                               "migración terminada |\n", ""),
             "sin destino en el inventario: `contexto/AGENTS-old.md` › Historial"),
            (INVENTORY.replace("| Historial | descartada | obsoleta: describe una migración terminada |",
                               "| Historial | descartada |  |"), "› Historial: descartada sin motivo"),
            (INVENTORY.replace("| Historial | descartada | obsoleta: describe una migración terminada |",
                               "| Historial | AGENTS.md o doc: decide (o descartada con motivo) |  |"),
             "› Historial: decide el destino"),
            (INVENTORY.replace("`contexto/docs/sincronizacion.md` | Antes", "`contexto/docs/sync.md` | Antes"),
             "`contexto/docs/sync.md` no tiene su fila en \"Documentos\""),
            (INVENTORY.replace("| Rendimiento | AGENTS.md | tal cual |", "| Rendimiento | descartada | ya no se usa |"),
             "› Rendimiento: es de hb-performance, hb-performance:estado y va en AGENTS.md tal cual"),
            (INVENTORY.replace("| Build › (inicio) | AGENTS.md | ## Stack |\n", ""),
             "sin destino en el inventario: `contexto/AGENTS-old.md` › Build › (inicio)"),
        )
        for inventory, message in cases:
            self.migrate(inventory=inventory)
            self.assertIn(message, self.verificar(code=1), message)
        self.migrate()
        (self.outside / "contexto" / "docs" / "troubleshooting.md").unlink()
        self.assertIn("el doc `contexto/docs/troubleshooting.md` no existe", self.verificar(code=1))
        self.migrate()
        self.assertIn("falta el inventario", self.contexto("verificar", code=1))

    def test_una_fila_entera_cubre_la_fuente(self):
        self.migrate(inventory=INVENTORY.split("| `contexto/protocolo-bugfix.md`")[0]
                     + "| `contexto/protocolo-bugfix.md` | (todo el archivo) | descartada | lo cubre hb-implement |\n"
                     "| `plantilla-reporte.md` | (todo el archivo) | descartada | lo cubre hb-implement |\n")
        self.assertIn("✔ Nada se pierde", self.verificar())

    def test_lo_de_otras_skills_queda_tal_cual(self):
        self.migrate(new_agents(perf="## Rendimiento\n\n- Se mide con la variante `benchmark`.\n"))
        out = self.verificar(code=1)
        self.assertIn("falta el bloque <!-- hb-performance:estado --> tal cual (está en `contexto/AGENTS-old.md`)", out)
        self.assertIn("## Rendimiento (de hb-performance) no quedó tal cual", out)
        self.migrate(new_agents(perf=""))
        self.assertIn("falta la sección ## Rendimiento de hb-performance", self.verificar(code=1))

    def test_una_regla_que_no_quedo_tal_cual_se_avisa(self):
        self.migrate(new_agents().replace(RULE, "- Los textos van en recursos."))
        out = self.verificar()
        self.assertIn("regla de `contexto/AGENTS-old.md` › Reglas que no quedó tal cual en AGENTS.md", out)
        self.assertIn("«- Los textos van en recursos.» (## Reglas del proyecto) no viene de ninguna fuente previa"
                      .replace("«- ", "«"), out)

    def test_un_agents_largo_se_avisa(self):
        self.migrate(new_agents() + "\n".join("- línea %d" % n for n in range(120)) + "\n")
        self.assertIn("AGENTS.md tiene", self.verificar())
        self.assertIn("menos de 150", self.verificar())


class NothingInventedTest(Base):
    """hb-setup no agrega reglas propias del proyecto: solo conserva las que ya están escritas en sus fuentes."""

    def agents(self, rules, modernization="- ninguna decidida\n"):
        write(self.repo / "AGENTS.md", "# Proyecto\n\n## Modernización\n\n" + modernization + "- Los agentes no migran "
              "ni proponen migrar fuera de lo decidido aquí.\n\n## Reglas del proyecto\n\n- Contexto de IA: versionado "
              "con el código.\n- Carpeta de reportes: `reports`\n" + rules + "\n## Git\n\n- x\n")
        result = self.contexto("verificar")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_sin_fuentes_no_aparece_ninguna_regla_inventada(self):
        out = self.agents("")
        self.assertIn("Fuentes previas verificadas: ninguna", out)
        self.assertNotIn("⚠", out)

    def test_una_regla_o_una_migracion_que_no_esta_en_ninguna_fuente_se_avisa(self):
        out = self.agents("- Toda pantalla nueva va en Compose.\n",
                          modernization="- Rx se reemplaza por corrutinas al tocar una clase.\n")
        self.assertIn("«Toda pantalla nueva va en Compose.» (## Reglas del proyecto) no viene de ninguna fuente previa",
                      out)
        self.assertIn("«Rx se reemplaza por corrutinas al tocar una clase.» (## Modernización)", out)

    def test_la_regla_de_una_fuente_se_conserva_y_no_se_avisa(self):
        write(self.repo / ".cursorrules", "## Reglas\n\n" + RULE + "\n")
        inventory = self.base / "inventario.md"
        write(inventory, "| Fuente | Sección | Destino | Motivo |\n| --- | --- | --- | --- |\n"
                         "| `.cursorrules` | Reglas | AGENTS.md | ## Reglas del proyecto |\n")
        write(self.repo / "AGENTS.md", "# Proyecto\n\n## Modernización\n\n- ninguna decidida\n\n## Reglas del "
                                       "proyecto\n\n- Contexto de IA: versionado con el código.\n" + RULE + "\n")
        result = self.contexto("verificar", "--inventario", str(inventory))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("⚠", result.stdout)

    def test_al_reescribir_un_agents_versionado_compara_con_el_de_head(self):
        write(self.repo / "AGENTS.md", "# Proyecto\n\n## Stack\n\n- Kotlin\n\n" + PERF_SECTION)
        commit_all(self.repo, "agents")
        inventory = self.base / "inventario.md"
        write(inventory, "| Fuente | Sección | Destino | Motivo |\n| --- | --- | --- | --- |\n"
                         "| `AGENTS.md` | Stack | AGENTS.md | ## Stack |\n"
                         "| `AGENTS.md` | Rendimiento | AGENTS.md | tal cual |\n")
        write(self.repo / "AGENTS.md", "# Proyecto\n\n## Stack\n\n- Kotlin\n")
        result = self.contexto("verificar", "--inventario", str(inventory))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("falta el bloque <!-- hb-performance:estado --> tal cual (está en `AGENTS.md`)", result.stdout)
        write(self.repo / "AGENTS.md", "# Proyecto\n\n## Stack\n\n- Kotlin\n\n" + PERF_SECTION)
        self.assertEqual(self.contexto("verificar", "--inventario", str(inventory)).returncode, 0)
        copy = self.base / "AGENTS.previo.md"
        write(copy, "# Proyecto\n\n## Stack\n\n- Kotlin\n\n## Seguridad\n\n- Sin datos de clientes.\n")
        result = self.contexto("verificar", "--inventario", str(inventory), "--previo", str(copy))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("sin destino en el inventario: `AGENTS.md` › Seguridad", result.stdout)


class MigrationSkillTextTest(unittest.TestCase):
    """Lo que la skill dice del camino migrar, en SKILL.md y en su referencia."""

    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.migration = (SKILL / "references" / "migracion.md").read_text(encoding="utf-8")

    def test_la_skill_busca_fuentes_previas_y_verifica_el_traspaso(self):
        for text in ("contexto.py fuentes", "contexto.py verificar", "references/migracion.md"):
            self.assertIn(text, self.skill)
        self.assertIn("aunque no exista `AGENTS.md`", self.skill)
        self.assertNotIn("**Proyecto con `AGENTS.md`:**", self.skill)

    def test_nada_inventado_y_nada_omitido(self):
        self.assertIn("Nada inventado", self.skill)
        self.assertIn("ninguna decidida", self.skill)
        self.assertIn("nunca se omite", self.skill)
        for text in ("AGENTS.md", "doc", "descartada", "Documentos", "Léelo cuando", "tal cual", "No la borres"):
            self.assertIn(text, self.migration)
        self.assertLess(self.skill.count("\n"), 500)


if __name__ == "__main__":
    unittest.main()
