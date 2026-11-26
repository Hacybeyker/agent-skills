#!/usr/bin/env python3
"""Genera el reporte HTML de hb-implement a partir de git y de un meta.json.

El código (antes, después y diff) sale de git: el agente solo escribe el meta.json
con el contexto que git no sabe (título, tipo, por qué de cada archivo, resultado del DoD).

Carpeta de reportes: --out o, sin él, la línea "Carpeta de reportes: <ruta>" del AGENTS.md del repo; si no hay,
reports. Es la base común de las skills (hb-performance y hb-review escriben en sus propias subcarpetas).
- Sin marcadores: una carpeta por tarea, <base>/implementation/<fecha>-<slug>/, con meta.json, report.html,
  snapshot.json, bitacora.md y previews/. Una tarea vieja en formato plano (<base>/<fecha>-<slug>.meta.json) sigue ahí.
- Con {fecha} y {slug} en la ruta: la ruta tal cual, con los mismos archivos; la base es la parte fija.
Si ya hay una carpeta con ese slug en otra fecha, la tarea sigue ahí.
Cada tarea tiene su fila en <base>/INDEX.md (clave: hb-implement + slug): "en curso" con --folder y el resultado del DoD
al generar el reporte. Las demás filas y líneas del índice no se tocan; se escribe sobre la ruta real (un enlace
simbólico sigue siendo enlace).

Foto inicial: --folder, al empezar la tarea, guarda snapshot.json con la rama, el HEAD y los archivos sucios del repo
principal y de las fuentes de las unidades de ## Estructura (con su hash de contenido, el mismo que da `git hash-object
--no-filters`) y de cada repo git hermano (las subcarpetas directas, no ocultas, de la carpeta padre del principal,
salvo que sea la carpeta personal; de ellos solo tamaño y fecha, "st:<tamaño>:<fecha>"). Un submódulo o repo anidado
que es unidad tiene su propia entrada; el repo de afuera solo mira su puntero. Un solo `git status` por repo, en
paralelo; una carpeta que no se puede leer queda anotada y no detiene nada.
--unit <ruta> --folder <slug> registra una unidad en "repos" del meta (y en la foto) en cuanto se pasa a fuente o se
corre su DoD.

Al generar, cada repo se compara con la foto. Entran el principal, las unidades de ## Estructura y las registradas
(con --unit o en "repos"), si cambiaron después de la foto. Otro repo hermano que cambió no entra: se lista en la
salida para que el flujo pregunte si es de la tarea. Un archivo que ya estaba sucio antes y no cambió va a "Cambios no
atribuidos", fuera de los conteos; si además cambió, entra con un aviso. Sin foto (una tarea vieja), entran el
principal y "repos" del meta; las unidades del modelo con cambios salen como no atribuidas, y los repos hermanos que no
son unidades solo se nombran en la salida, nunca en el HTML. Un repo de la tarea que git no lee queda fuera con un
aviso (en la salida y en el HTML), salvo el principal o uno con base explícita, que cortan el reporte.
Sin ningún archivo de la tarea no escribe el reporte: dice la causa probable y el siguiente paso.
Avisa de un archivo de código borrado o vaciado cuyo equivalente (mismo nombre base) aparece con otra extensión de
código: una migración de lenguaje que nadie pidió.

Base de comparación de cada repo: --base (o "base" en "repos"); sin ella, el merge-base de HEAD con su rama principal
(--main-branch, "main_branch" o la de ## Estructura; si no, origin/HEAD, origin/main, origin/master, main o master).
Los archivos masivos o generados (goldens, fixtures) se explican en grupo, por carpeta o patrón, con "groups"; un
archivo con su propia entrada en "files" se muestra aparte. "temporary" deja fuera los cambios de configuración que no
son de la tarea, y los archivos de "### Configuración local modificada a propósito" quedan fuera solos.
Los datos de análisis (why, before, after, risk, pros, cons, layer, severity, root_cause, impact, diagrams, ticket)
nunca detienen el reporte: lo que falta o viene vacío no se muestra, y un valor con formato inválido se ignora con un
aviso. La excepción es "cons": [], que se analizó y no tuvo contras: muestra "Sin contras identificados".
En un worktree enlazado al que le faltan AGENTS.md (fuera de git en el principal) o el enlace simbólico por el que
pasa la carpeta de reportes, se detiene y dice cómo recrearlos, sin escribir nada.

Uso:
  python3 -I report.py --folder <slug> [--date AAAA-MM-DD] [--out <carpeta>] [--repo .]
      (al empezar: crea la carpeta de la tarea y toma la foto inicial, sin generar el reporte)
  python3 -I report.py --unit <ruta> --folder <slug> [--out <carpeta>] [--repo .]
      (registra una unidad: la ruta de su fuente, relativa a la raíz del repo principal, o su identificador)
  python3 -I report.py --meta <meta.json> [--base <ref> | --main-branch <rama>] [--out <carpeta>] [--repo .]
  python3 -I report.py --meta <meta.json> --attribution [--base <ref> | --main-branch <rama>] [--repo .]
      (qué es de la tarea, repo por repo, en JSON y sin escribir nada: lo usa hb-review. El meta puede no existir
      todavía si su carpeta ya tiene la foto)
"""
import argparse
import base64
import concurrent.futures
import contextlib
import datetime
import difflib
import fnmatch
import glob
import hashlib
import html
import json
import os
import pathlib
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "report-template.html"
TYPES = {
    "feature": "✨ Feature",
    "bugfix": "🐛 Bugfix",
    "enhancement": "⚡ Mejora",
    "refactor": "♻️ Refactor",
}
PILLS = {
    "pass": ("c-ok", "✅ PASS"),
    "fail": ("c-ko", "❌ FAIL"),
    "skipped": ("c-same", "⏭️ SKIPPED"),
}
LEVELS = ("critico", "alto", "medio", "bajo")
RISK_LABELS = {"critico": "Riesgo crítico", "alto": "Riesgo alto", "medio": "Riesgo medio", "bajo": "Riesgo bajo"}
SEVERITY_LABELS = {"critico": "Severidad crítica", "alto": "Severidad alta", "medio": "Severidad media",
                   "bajo": "Severidad baja"}
# Mermaid solo se carga si el meta trae "diagrams": versión exacta e integridad fijas, y modo estricto.
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.17.2/dist/mermaid.min.js"
MERMAID_SRI = "sha384-EOXBFmc3gx5mb+vn0vPvvGqACToJD24hhacX5Yx+8NUUQrHIle/Qi5Bg9o3zKwW2"
MAX_LINES = 2000
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
DEFAULT_OUT = "reports"
SKILL = "hb-implement"
SUBFOLDER = "implementation"  # la subcarpeta de esta skill dentro de la base común
INDEX_COLUMNS = ["Fecha", "Skill", "Slug", "Tipo", "Estado", "Ruta"]
INDEX_INTRO = ("# Índice de reportes\n\n"
               "Una fila por tarea. Cada skill agrega o actualiza solo sus filas (clave: Skill + Slug).\n\n")
INDEX_TABLE = "| " + " | ".join(INDEX_COLUMNS) + " |\n|" + " --- |" * len(INDEX_COLUMNS) + "\n"
TABLE_SEPARATOR = re.compile(r"\s*\|(\s*:?-+:?\s*\|)+\s*")
MAIN_BRANCHES = ("origin/main", "origin/master", "main", "master")
MARKER = re.compile(r"(\{fecha\}|\{slug\})")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# "Carpeta de reportes: <ruta>" en AGENTS.md, con o sin viñeta, negrita o acentos graves (también en inglés).
FOLDER_KEY = re.compile(r"carpeta\s+de\s+(?:los\s+)?reportes|reports?\s+folder", re.I)
FOLDER_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?[*_]*(?P<key>[^:*_`]+?)[*_]*[ \t]*:[*_]*[ \t]*(?P<value>\S.*?)[ \t]*$")
FENCE = re.compile(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$")
BRANCH_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
SNAPSHOT = "snapshot.json"
SNAPSHOT_FORMAT = 1
STATUS_TIMEOUT_S = 120
MAX_WORKERS = 16
LIST_LIMIT = 50  # rutas por repo en "Cambios no atribuidos"
ABSENT = object()  # una ruta que no está en un mapa de archivos sucios (None ahí es "borrado")
# Extensiones de código fuente, para el aviso de migración de lenguaje. Sin cabeceras (.h, .hpp): conviven con su
# implementación con el mismo nombre base.
SOURCE_EXTENSIONS = {
    ".java", ".kt", ".kts", ".scala", ".groovy", ".swift", ".m", ".mm", ".c", ".cc", ".cpp", ".cxx", ".cs", ".fs",
    ".vb", ".go", ".rs", ".py", ".rb", ".php", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".dart", ".lua", ".pl",
    ".r", ".jl", ".ex", ".exs", ".erl", ".clj", ".hs", ".ml", ".elm", ".vue", ".svelte",
}
NOT_CODE = re.compile(r"(?:package|import|using|namespace|module)\b")
# Carpetas que solo dicen el lenguaje dentro de un source set (src/main/java frente a src/main/kotlin): para el aviso
# de migración, el mismo lugar.
LANGUAGE_DIRS = {"java", "kotlin", "groovy", "scala", "swift", "objc", "js", "javascript", "ts", "typescript",
                 "python", "py", "go", "golang", "rust", "dart", "ruby", "php", "csharp", "cs", "cpp"}
# Extensiones del mismo lenguaje: pasar de una a otra no es una migración de lenguaje.
SAME_LANGUAGE = ({".js", ".jsx", ".mjs", ".cjs"}, {".ts", ".tsx"}, {".kt", ".kts"}, {".cc", ".cpp", ".cxx"},
                 {".m", ".mm"}, {".ex", ".exs"})
MIXED_COMMITTED_WARNING = ("Ya tenía cambios commiteados en la rama antes de la tarea: el diff contra la base mezcla "
                           "esos cambios con los de la tarea.")
MIXED_WARNING = ("Ya tenía cambios sin commit antes de la tarea: el diff contra la base mezcla esos cambios con los de "
                 "la tarea.")
def printable(text):
    """El texto listo para mostrar: un nombre de archivo que no es UTF-8 (llega con surrogateescape) sale con el
    carácter de reemplazo en vez de cortar la escritura del HTML."""
    text = str(text)
    try:
        return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except UnicodeEncodeError:
        return text.encode("utf-8", "replace").decode("utf-8")


def e(text, quote=True):
    return html.escape(printable(text), quote)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def decode(data):
    if data is None or data is NO_PERMISSION:
        return data
    if b"\0" in data[:8000]:
        return False  # binario
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return False


def plural(count, word, many=None):
    return "%d %s" % (count, word if count == 1 else (many or word + "s"))


# ── Rutas ────────────────────────────────────────────────────────────────────
def lexical(path):
    """La ruta absoluta y normalizada sin seguir enlaces: un enlace simbólico se usa por su nombre."""
    return pathlib.Path(os.path.normpath(os.path.abspath(str(path))))


def under(path, folder):
    return path == folder or folder in path.parents


def relative_in(path, repo):
    """La ruta relativa al repo sin seguir enlaces, o None si queda fuera."""
    path = lexical(path)
    real_repo = pathlib.Path(os.path.realpath(str(repo)))
    for base in (lexical(repo), real_repo):
        if under(path, base):
            return path.relative_to(base)
    # La misma carpeta escrita por otro camino (/var frente a /private/var en macOS): se compara la ruta real.
    real_path = pathlib.Path(os.path.realpath(str(path)))
    return real_path.relative_to(real_repo) if under(real_path, real_repo) else None


def shown(path, repo):
    """Relativa al repo si está dentro; absoluta si no."""
    relative = relative_in(path, repo)
    return relative.as_posix() if relative is not None else str(path)


def display_path(path, main):
    """La ruta de un repo o carpeta tal como la escribe el modelo: relativa a la raíz del repo principal (".",
    "../core-lib")."""
    return pathlib.Path(os.path.relpath(str(path), str(main))).as_posix()


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "reporte"


def safe_slug(text):
    """El slug que da el usuario o el meta, sin cambiarle las mayúsculas: solo letras, números, '.', '_' y '-'."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-.")
    return s[:80] or "reporte"


def agents_out(repo):
    """La ruta de "Carpeta de reportes: <ruta>" en el AGENTS.md del repo, o None."""
    try:
        text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        found = None if fenced else FOLDER_LINE.match(line)
        if not found or not FOLDER_KEY.fullmatch(found.group("key").strip()):
            continue
        quoted = re.search(r"`([^`]+)`", found.group("value"))
        value = (quoted.group(1) if quoted else found.group("value")).strip().rstrip(".").strip()
        if value and not value.startswith("<"):
            return value
    return None


LOCAL_CONFIG_WHY = "Configuración local modificada a propósito (## Estructura de AGENTS.md): no es de la tarea."


def markdown_section(text, title, level):
    """El cuerpo de la primera sección "<# * level> <title>" de un Markdown, o None."""
    body, inside = [], False
    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})[ \t]+(.*?)[ \t#]*$", line)
        if inside and heading and len(heading.group(1)) <= level:
            break
        if inside:
            body.append(line)
        elif heading and len(heading.group(1)) == level and heading.group(2).strip().lower() == title.lower():
            inside = True
    return "\n".join(body) if inside else None


def local_config(repo):
    """Las rutas (relativas al repo principal, también ../<vecino>/…) de "### Configuración local modificada a
    propósito" de ## Estructura: lo primero entre acentos graves de cada viñeta."""
    try:
        text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    structure = markdown_section(text, "Estructura", 2)
    block = markdown_section(structure, "Configuración local modificada a propósito", 3) if structure else None
    found = []
    for line in (block or "").splitlines():
        quoted = re.match(r"^[ \t]*[-*][ \t]+`([^`]+)`", line)
        if quoted and not quoted.group(1).startswith("<"):
            found.append(quoted.group(1).strip())
    return found


def markdown_tables(block):
    """Las tablas Markdown de un bloque: [(celdas de la cabecera, [celdas de cada fila])]."""
    lines, tables, i = block.splitlines(), [], 0
    while i < len(lines) - 1:
        header = index_cells(lines[i])
        if header is None or not TABLE_SEPARATOR.fullmatch(lines[i + 1]):
            i += 1
            continue
        rows, i = [], i + 2
        while i < len(lines):
            cells = index_cells(lines[i])
            if cells is None:
                break
            rows.append(cells)
            i += 1
        tables.append((header, rows))
    return tables


def cell_value(cell):
    """Lo primero entre acentos graves de una celda (o la celda entera); None si es un marcador o está vacía."""
    quoted = re.findall(r"`([^`]+)`", cell)
    value = (quoted[0] if quoted else re.sub(r"[*_]", "", cell)).strip()
    return None if not value or value.startswith("<") or value in ("—", "–", "-") else value


def cell_branch(cell):
    """La rama principal de la celda "Repo y rama principal": lo último entre acentos graves que no es una URL."""
    for value in reversed(re.findall(r"`([^`]+)`", cell)):
        value = value.strip()
        if BRANCH_NAME.fullmatch(value) and not value.endswith(".git"):
            return value
    return None


def structure_units(repo):
    """Las unidades del modelo de AGENTS.md: [{"id", "source", "main_branch"}]. Salen de la tabla "### Unidades" de
    ## Estructura (columna "Fuente") o, en el formato anterior, de "### Repos relacionados" de ## Arquitectura
    (columna "Ruta"). Sin modelo, []."""
    try:
        text = FENCE.sub("", (repo / "AGENTS.md").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    structure = markdown_section(text, "Estructura", 2)
    if structure is not None:
        block, keys = markdown_section(structure, "Unidades", 3) or structure, ("fuente",)
    else:
        architecture = markdown_section(text, "Arquitectura", 2) or ""
        block, keys = markdown_section(architecture, "Repos relacionados", 3) or "", ("ruta", "fuente")
    for header, rows in markdown_tables(block):
        names = [re.sub(r"[*_`]", "", cell).strip().lower() for cell in header]
        source = next((i for i, name in enumerate(names) if name in keys), None)
        if source is None:
            continue
        branch = next((i for i, name in enumerate(names) if "rama" in name), None)
        units = []
        for row in rows:
            ident = cell_value(row[0]) if row else None
            path = cell_value(row[source]) if source < len(row) else None
            if ident and path:
                units.append({"id": ident, "source": path,
                              "main_branch": cell_branch(row[branch]) if branch is not None and branch < len(row)
                              else None})
        return units
    return []


class Task:
    """La carpeta de una tarea y sus archivos. flat: el formato plano de antes, <base>/<fecha>-<slug>.<extensión>,
    que se conserva para las tareas que ya estaban así (sin foto inicial)."""
    NAMES = {"report": "report.html", "meta": "meta.json", "bitacora": "bitacora.md"}
    SUFFIXES = {"report": ".html", "meta": ".meta.json", "bitacora": ".bitacora.md"}

    def __init__(self, folder, date, task_slug, flat=False, reused=False):
        self.folder, self.date, self.slug, self.flat, self.reused = folder, date, task_slug, flat, reused

    def file(self, kind):
        """kind: "report", "meta" o "bitacora"."""
        if self.flat:
            return self.folder / f"{self.date}-{self.slug}{self.SUFFIXES[kind]}"
        return self.folder / self.NAMES[kind]

    @property
    def previews(self):
        return self.folder / "previews"

    @property
    def snapshot(self):
        return None if self.flat else self.folder / SNAPSHOT


class Layout:
    """Dónde van el meta, el reporte, la bitácora y los previews de una tarea, según la carpeta de reportes configurada.
    root es la base: la parte fija de la ruta, la que se deja fuera de git y donde va INDEX.md."""

    def __init__(self, repo, spec):
        expanded = os.path.expanduser(spec)
        parts = pathlib.PurePosixPath(expanded.replace("\\", "/")).parts
        first = next((i for i, part in enumerate(parts) if MARKER.search(part)), None)
        self.marked = first is not None
        if self.marked and "{slug}" not in expanded:
            raise ValueError("la carpeta de reportes %r usa marcadores sin {slug}: dos tareas del mismo día se "
                             "pisarían (por ejemplo, <carpeta>/{fecha}/{slug})" % spec)
        if self.marked and first == 0:
            raise ValueError("la carpeta de reportes %r necesita una carpeta fija antes de los marcadores "
                             "(por ejemplo, reports/{fecha}/{slug})" % spec)
        fixed = pathlib.Path(*parts[:first]) if self.marked else pathlib.Path(expanded)
        self.root = lexical(fixed if fixed.is_absolute() else repo / fixed)
        # Sin marcadores, la línea es la base común: esta skill escribe en <base>/implementation/<fecha>-<slug>/.
        self.rest = parts[first:] if self.marked else (SUBFOLDER, "{fecha}-{slug}")
        self.index = self.root / "INDEX.md"

    def _regex(self, task_slug=None):
        """La ruta de una carpeta de tarea relativa a la base; la primera aparición de cada marcador queda como grupo
        con nombre (fecha, slug) para saber de qué fecha y slug es una carpeta existente."""
        seen = set()

        def piece_regex(piece):
            if piece not in ("{fecha}", "{slug}"):
                return re.escape(piece)
            name = piece[1:-1]
            body = r"\d{4}-\d{2}-\d{2}" if name == "fecha" else (re.escape(task_slug) if task_slug else r"[^/]+")
            if name in seen:
                return body
            seen.add(name)
            return "(?P<%s>%s)" % (name, body)
        return re.compile("/".join("".join(piece_regex(piece) for piece in MARKER.split(part)) for part in self.rest))

    def _fill(self, date, task_slug):
        return self.root.joinpath(*(p.replace("{fecha}", date).replace("{slug}", task_slug) for p in self.rest))

    def existing(self, task_slug):
        """Carpetas de la tarea que ya existen con ese slug, en cualquier fecha, de la más vieja a la más nueva."""
        def component(part):
            return "".join("*" if piece == "{fecha}" else glob.escape(task_slug) if piece == "{slug}"
                           else glob.escape(piece) for piece in MARKER.split(part))
        pattern = os.path.join(glob.escape(str(self.root)), *(component(p) for p in self.rest))
        regex = self._regex(task_slug)
        found = []
        for candidate in glob.glob(pattern):
            path = pathlib.Path(candidate)
            if path.is_dir() and regex.fullmatch(path.relative_to(self.root).as_posix()):
                found.append(path)
        return sorted(found)

    def flat_dates(self, task_slug):
        """Fechas de una tarea vieja en formato plano (<base>/<fecha>-<slug>.meta.json, .html o .bitacora.md)."""
        pattern = re.compile(r"(\d{4}-\d{2}-\d{2})-%s(?:\.meta\.json|\.html|\.bitacora\.md)" % re.escape(task_slug))
        dates = set()
        for candidate in glob.glob(os.path.join(glob.escape(str(self.root)), "*-%s.*" % glob.escape(task_slug))):
            found = pattern.fullmatch(os.path.basename(candidate))
            if found and os.path.isfile(candidate):
                dates.add(found.group(1))
        return sorted(dates)

    def task(self, task_slug, date, meta_path=None):
        """La tarea, en este orden: (1) la carpeta de tarea donde ya vive el meta (sin marcadores, un meta suelto en la
        base es del formato plano); (2) una carpeta existente con el mismo slug, aunque sea de otra fecha; (3) sin
        marcadores, una tarea vieja en formato plano con ese slug, que sigue plana; (4) la carpeta nueva de hoy."""
        if meta_path is not None:
            real_root = pathlib.Path(os.path.realpath(str(self.root)))
            real_parent = pathlib.Path(os.path.realpath(str(meta_path.parent)))
            for base, candidate in ((self.root, lexical(meta_path.parent)), (real_root, real_parent)):
                if candidate == base and not self.marked:
                    return Task(self.root, date, task_slug, flat=True)
                if under(candidate, base) and candidate != base:
                    found = self._regex().fullmatch(candidate.relative_to(base).as_posix())
                    if found:
                        groups = found.groupdict()
                        return Task(self.root / candidate.relative_to(base), groups.get("fecha") or date,
                                    groups.get("slug") or task_slug)
        today = self._fill(date, task_slug)
        found = self.existing(task_slug)
        if found:
            groups = self._regex(task_slug).fullmatch(found[-1].relative_to(self.root).as_posix()).groupdict()
            return Task(found[-1], groups.get("fecha") or date, task_slug, reused=found[-1] != today)
        if not self.marked:
            dates = self.flat_dates(task_slug)
            if dates:
                return Task(self.root, dates[-1], task_slug, flat=True, reused=True)
        if any("{fecha}" in part for part in self.rest) and not DATE.match(date):
            raise ValueError("la fecha %r no es AAAA-MM-DD: va en el nombre de la carpeta de la tarea" % date)
        return Task(today, date, task_slug)

    def is_output(self, path):
        """Si la ruta de un archivo cambiado pertenece a la carpeta de reportes (o es el enlace que la contiene)."""
        path = lexical(path)
        if under(path, self.root) or under(self.root, path):
            return True
        try:
            return under(path.resolve(), self.root.resolve())
        except OSError:
            return False


def check_ignore(repo, relative):
    return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", relative],
                          capture_output=True).returncode == 0


def ensure_ignored(repo, root, target):
    """Si git no ignora la carpeta de reportes, la deja en .git/info/exclude: local, el repo y su .gitignore no cambian.
    Si la ruta pasa por un enlace simbólico, git no mira más allá: se comprueba el enlace, que el usuario ignora a su
    manera, y no se escribe nada. Fuera del repo no hay nada que ignorar. Devuelve un aviso para stderr, o None."""
    relative = relative_in(root, repo)
    if relative is None:
        return None
    current = lexical(repo)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            link = relative_in(current, repo).as_posix()
            if check_ignore(repo, link):
                return None
            return (f"⚠️  {link} es un enlace simbólico que git no ignora: agrega /{link} (sin barra final) a "
                    f".git/info/exclude para que no entre a un commit")
    target_relative = relative_in(target, repo)
    if target_relative is not None and check_ignore(repo, target_relative.as_posix()):
        return None
    try:
        found = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"],
                               capture_output=True, text=True)
        if found.returncode != 0 or relative.as_posix() in ("", "."):
            raise OSError("sin ruta de exclude")
        exclude = repo / found.stdout.strip()
        exclude.parent.mkdir(parents=True, exist_ok=True)
        current_text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write(("" if not current_text or current_text.endswith("\n") else "\n") + f"/{relative.as_posix()}/\n")
        print(f"✔ git ignora {relative.as_posix()} (en .git/info/exclude, local: el repo no cambia)")
    except (OSError, ValueError):
        return f"⚠️  {root.name}/ no está ignorada por git y no pude agregarla a .git/info/exclude: que no entre a un commit"
    return None


def real(path):
    """La ruta real donde se escribe: así un enlace simbólico (AGENTS.md, la carpeta de contexto, INDEX.md) sigue
    siendo enlace después de escribir."""
    return pathlib.Path(os.path.realpath(str(path)))


def write_text(path, text):
    """Escribe el archivo entero o nada: un temporal único al lado (dos procesos a la vez no comparten temporal) y
    después lo reemplaza. Si algo falla, el archivo anterior queda como estaba."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temporary, 0o666 & ~umask)  # los permisos de un archivo nuevo, no los 0600 de mkstemp
        with os.fdopen(handle, "w", encoding="utf-8", errors="replace") as stream:
            stream.write(text)
        os.replace(temporary, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def write_json(path, data, ascii_only=False):
    """Escribe el JSON entero o nada (write_text)."""
    write_text(path, json.dumps(data, ensure_ascii=ascii_only, indent=2) + "\n")


@contextlib.contextmanager
def task_lock(folder):
    """Bloquea la carpeta de la tarea mientras se lee, se cambia y se escribe el meta o la foto: varios --unit en
    paralelo no pierden registros. El bloqueo es sobre la carpeta misma, sin archivo de bloqueo que git pueda ver. Si no
    se puede bloquear (sin fcntl, como en Windows, o un disco de red que no lo admite), sigue sin bloqueo y lo avisa."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:
        fcntl = None
    handle = None
    if fcntl is not None:
        try:
            handle = os.open(str(folder), os.O_RDONLY)
            fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError as err:
            if handle is not None:
                os.close(handle)
            handle = None
            reason = err.strerror or str(err)
            print(f"⚠️  No pude bloquear la carpeta de la tarea ({reason}): sigo sin bloqueo; no corras varios --unit "
                  "a la vez.", file=sys.stderr)
    else:
        print("⚠️  Este sistema no permite bloquear la carpeta de la tarea: sigo sin bloqueo; no corras varios --unit "
              "a la vez.", file=sys.stderr)
    try:
        yield
    finally:
        if handle is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(handle, fcntl.LOCK_UN)
            os.close(handle)


# ── Índice de reportes (<base>/INDEX.md) ─────────────────────────────────────
def index_cell(text):
    return re.sub(r"[\r\n]+", " ", str(text)).replace("|", "\\|").strip()


def index_cells(line):
    """Las celdas de una fila de tabla Markdown, sin espacios alrededor (un \\| no separa), o None si no es fila."""
    body = line.strip()
    if not body.startswith("|"):
        return None
    body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def index_row(layout, task, kind, state):
    """La fila de la tarea. La ruta es relativa a la carpeta del índice y se calcula con las dos rutas en la misma
    forma léxica (bajo la base tal como se escribió), para que sirva aunque la carpeta pase por un enlace."""
    report = task.file("report")
    try:
        relative = report.relative_to(layout.root).as_posix()
    except ValueError:
        relative = pathlib.Path(os.path.relpath(str(report), str(layout.root))).as_posix()
    link = "[%s](%s)" % (index_cell(relative).replace("[", "\\[").replace("]", "\\]"),
                         urllib.parse.quote(relative, safe="/"))
    cells = [task.date, SKILL, task.slug, kind, state]
    return "| " + " | ".join(index_cell(cell) for cell in cells) + " | " + link + " |"


def update_index(layout, task, kind, state):
    """Agrega la fila de la tarea a <base>/INDEX.md o reemplaza la que ya tiene (clave: hb-implement + slug), sin
    tocar otras filas ni otras líneas. kind None conserva el tipo de la fila que ya estaba. Escribe sobre la ruta real.
    Devuelve un aviso para stderr, o None."""
    target = real(layout.index)
    try:
        text = target.read_text(encoding="utf-8") if target.is_file() else None
        if text is None:
            row = index_row(layout, task, kind or "—", state)
            new = INDEX_INTRO + INDEX_TABLE + row + "\n"
        else:
            lines = text.splitlines(keepends=True)
            header = next((i for i in range(len(lines) - 1) if index_cells(lines[i]) == INDEX_COLUMNS
                           and TABLE_SEPARATOR.fullmatch(lines[i + 1])), None)
            if header is None:  # sin la cabecera exacta: la tabla va al final, sin borrar nada
                row = index_row(layout, task, kind or "—", state)
                new = text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + \
                    INDEX_TABLE + row + "\n"
            else:
                end, position = header + 2, None
                while end < len(lines) and lines[end].lstrip().startswith("|"):
                    cells = index_cells(lines[end]) or []
                    if position is None and len(cells) >= 3 and cells[1] == SKILL and cells[2] == index_cell(task.slug):
                        position = end
                    end += 1
                if position is not None:
                    cells = index_cells(lines[position])
                    keep = kind or (cells[3] if len(cells) > 3 and cells[3] else "—")
                    lines[position] = index_row(layout, task, keep, state) + \
                        ("\n" if lines[position].endswith("\n") else "")
                else:
                    if not lines[end - 1].endswith("\n"):
                        lines[end - 1] += "\n"
                    lines.insert(end, index_row(layout, task, kind or "—", state) + "\n")
                new = "".join(lines)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
    except (OSError, ValueError) as err:
        return f"⚠️  No pude actualizar el índice {target}: {err}"
    return None


# ── Worktrees enlazados (lo que el principal tiene fuera de git) ─────────────
def home(path):
    """La ruta con ~ si está dentro de la carpeta personal (más corta y sin el nombre de usuario), lista para un shell."""
    text, user = str(path), os.path.expanduser("~")
    if user not in ("", "~") and (text == user or text.startswith(user + "/")):
        rest = text[len(user):]
        return "~" + (rest if shlex.quote(rest) == rest else "'" + rest.replace("'", "'\\''") + "'")
    return shlex.quote(text)


def tracked(repo, name):
    result = subprocess.run(["git", "-C", str(repo), "ls-files", "--", name], capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip())


def worktree_roots(repo):
    """Las carpetas (rutas reales) de todos los worktrees del repo: no son repos hermanos, son el mismo repo."""
    try:
        listing = git(repo, "worktree", "list", "--porcelain").decode("utf-8", "replace")
    except RuntimeError:
        return set()
    return {os.path.realpath(line[len("worktree "):]) for line in listing.splitlines() if line.startswith("worktree ")}


def main_worktree(repo):
    """La carpeta del worktree principal si el repo es un worktree enlazado; si no, None."""
    try:
        git_dir = git(repo, "rev-parse", "--absolute-git-dir").decode().strip()
        common = git(repo, "rev-parse", "--git-common-dir").decode().strip()
        listing = git(repo, "worktree", "list", "--porcelain").decode()
    except RuntimeError:
        return None
    common = common if os.path.isabs(common) else os.path.join(str(repo), common)
    if not git_dir or os.path.realpath(git_dir) == os.path.realpath(common):
        return None
    main = next((pathlib.Path(line[len("worktree "):]) for line in listing.splitlines()
                 if line.startswith("worktree ")), None)
    if main is None or os.path.realpath(str(main)) == os.path.realpath(str(repo)):
        return None
    return main


def gap(repo, main, name, links_only=False):
    """(nombre, qué es en el principal, destino) si el principal lo tiene fuera de git (un enlace o un archivo o
    carpeta local) y este worktree no; si no, None. Lo versionado lo trae el checkout: no es un hueco. Con links_only,
    solo cuenta un enlace: una carpeta de reportes local (reports/) se crea en el worktree, como siempre."""
    there = main / name
    if os.path.lexists(str(repo / name)) or not os.path.lexists(str(there)) or tracked(main, name):
        return None
    if links_only and not there.is_symlink():
        return None
    kind = "un enlace" if there.is_symlink() else "una carpeta local" if there.is_dir() else "un archivo local"
    return name, kind, os.path.realpath(str(there))


def base_prefixes(repo, root):
    """Las carpetas de la base dentro del repo, de la de más arriba a la base, hasta la primera que falta aquí."""
    relative = relative_in(root, repo)
    names, current = [], pathlib.PurePosixPath()
    for part in relative.parts if relative is not None else ():
        current = current / part
        names.append(current.as_posix())
        if not os.path.lexists(str(repo / current)):
            break
    return names


def check_worktree(repo, layout, with_agents):
    """H10: en un worktree enlazado, si faltan AGENTS.md (cuando no se pasó --out) o la carpeta de reportes que el
    principal tiene fuera de git, se detiene antes de escribir: no crea un reports/ nuevo que se perdería con el
    worktree, ni el enlace por su cuenta."""
    main = main_worktree(repo)
    if main is None:
        return
    agents = gap(repo, main, "AGENTS.md") if with_agents else None
    root = layout.root
    if agents:  # sin AGENTS.md aquí, la base que vale es la del AGENTS.md del principal
        try:
            root = Layout(repo, agents_out(main) or DEFAULT_OUT).root
        except ValueError:
            pass
    missing = [agents] if agents else []
    missing += [found for found in (gap(repo, main, name, links_only=True) for name in base_prefixes(repo, root))
                if found]
    if not missing:
        return
    lines = [f"Este worktree no tiene lo que el worktree principal ({home(main)}) guarda fuera de git, y un worktree "
             "nuevo no lo trae:"]
    for name, kind, target in missing:
        covered = ("git ya lo ignora: .git/info/exclude es común a los worktrees" if check_ignore(repo, name)
                   else f"agrega /{name} a .git/info/exclude")
        lines.append(f"  - {name}: en el principal es {kind} ({home(target)}). Para recrearlo: "
                     f"cd {home(repo)} && ln -s {home(target)} {shlex.quote(name)} ({covered}).")
    lines.append("No escribo nada para no crear aquí una carpeta de reportes nueva, que se perdería al borrar el "
                 "worktree. Recréalo solo si el usuario o el proyecto lo piden, o pasa --out con la carpeta de "
                 "reportes del proyecto.")
    raise RuntimeError("\n".join(lines))


# ── Foto inicial: estado de cada repo ────────────────────────────────────────
def content_hash(path):
    """El hash de contenido de un archivo, el mismo que da `git hash-object --no-filters` (de un enlace simbólico, el de
    su destino, como lo guarda git). None si no existe, "dir" si es una carpeta (un repo anidado) y "unreadable" si no
    se puede leer. Sin procesos: se calcula aquí."""
    path = str(path)
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return "unreadable"
    try:
        if stat.S_ISLNK(info.st_mode):
            data = os.fsencode(os.readlink(path))
            return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        if stat.S_ISDIR(info.st_mode):
            return nested_head(path)
        digest = hashlib.sha1(b"blob %d\0" % info.st_size)
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return "unreadable"


def nested_head(path, with_changes=True):
    """El "hash" de una carpeta: el HEAD de un repo anidado (un submódulo), así un cambio de su puntero se ve, más un
    resumen de sus cambios sin commit, así también se ve un cambio dentro; "dir" en cualquier otra carpeta. Sin
    with_changes (la raíz de una unidad anidada, que tiene su propia foto), solo el HEAD. Con tiempo límite."""
    if not os.path.lexists(os.path.join(path, ".git")):
        return "dir"
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-C", path, "rev-parse", "-q", "--verify", "HEAD"],
                                capture_output=True, text=True, timeout=STATUS_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return "unreadable"
    head = result.stdout.strip() if result.returncode == 0 else ""
    if not head:
        return "dir"
    if not with_changes:
        return head
    try:
        status = subprocess.run(["git", "--no-optional-locks", "-C", path, "status", "--porcelain", "-z",
                                 "--untracked-files=all"], capture_output=True, timeout=STATUS_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return head + "+?"
    if status.returncode != 0 or not status.stdout:
        return head
    digest = hashlib.sha1(status.stdout)
    for entry in status.stdout.split(b"\0"):
        name = entry[3:]
        if name:
            digest.update(str(signature(os.path.join(path, os.fsdecode(name)))).encode())
    return head + "+" + digest.hexdigest()[:12]


def signature(path):
    """La firma barata de un archivo de un repo hermano ajeno: tamaño y fecha de modificación, sin leerlo ("st:…").
    None si no existe."""
    try:
        info = os.lstat(str(path))
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return "unreadable"
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    return "st:%d:%d" % (info.st_size, info.st_mtime_ns)


def current_value(root, path, before):
    """El valor de hoy de una ruta, calculado igual que el de la foto: firma barata si la foto la guardó así."""
    full = os.path.join(str(root), path)
    return signature(full) if isinstance(before, str) and before.startswith("st:") else content_hash(full)


def repo_state(root, exclude=None, cheap=False, nested=()):
    """La rama, el HEAD y los archivos sucios (modificados, borrados o sin rastrear, con su hash de contenido; con
    cheap, de un repo hermano ajeno, solo tamaño y fecha) de un repo, con un solo `git status` que no toma locks ni
    reescribe el índice. `nested`: las raíces de las unidades anidadas (submódulos o repos dentro de este), que tienen su
    propia foto: de ellas solo cuenta su HEAD (el puntero) y nada de lo que tienen dentro. Si git falla, {"error":
    motivo}."""
    command = ["git", "--no-optional-locks", "-C", str(root), "status", "--porcelain=v2", "--branch", "-z",
               "--untracked-files=all"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=STATUS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"error": "git status tardó más de %d s" % STATUS_TIMEOUT_S}
    except OSError as err:
        return {"error": str(err)}
    if result.returncode != 0:
        lines = result.stderr.decode("utf-8", "replace").strip().splitlines()
        return {"error": lines[-1] if lines else "git status falló"}
    branch_name = head = None
    paths = []
    fields = result.stdout.split(b"\0")
    index = 0
    while index < len(fields):
        entry = fields[index].decode("utf-8", "surrogateescape")
        index += 1
        if entry.startswith("# branch.oid "):
            value = entry[len("# branch.oid "):]
            head = None if value == "(initial)" else value
        elif entry.startswith("# branch.head "):
            value = entry[len("# branch.head "):]
            branch_name = None if value == "(detached)" else value
        elif entry[:2] == "1 ":
            parts = entry.split(" ", 8)
            paths += parts[8:]
        elif entry[:2] == "2 ":
            parts = entry.split(" ", 9)
            paths += parts[9:]
            if index < len(fields):  # con -z, la ruta de origen del renombre viene en el campo siguiente
                paths.append(fields[index].decode("utf-8", "surrogateescape"))
                index += 1
        elif entry[:2] == "u ":
            paths += entry.split(" ", 10)[10:]
        elif entry[:2] == "? ":
            paths.append(entry[2:])
    dirty = {}
    for path in paths:
        path = path.rstrip("/")
        if not path or (exclude and exclude(path)):
            continue
        full = os.path.join(str(root), path)
        if path in nested:
            dirty[path] = nested_head(full, with_changes=False)
        elif any(path.startswith(inner + "/") for inner in nested):
            continue
        else:
            dirty[path] = signature(full) if cheap else content_hash(full)
    return {"branch": branch_name, "head": head, "dirty": dirty}


def nested_paths(key, keys):
    """Las rutas (relativas, con /) de los repos de `keys` que viven dentro del repo `key`: sus unidades anidadas."""
    prefix = key.rstrip(os.sep) + os.sep
    return {pathlib.Path(os.path.relpath(other, key)).as_posix() for other in keys
            if other != key and other.startswith(prefix)}


def states(roots, layout=None, cheap=()):
    """{clave: estado} de cada repo, en paralelo (hasta MAX_WORKERS a la vez). Sin los archivos de la carpeta de
    reportes, en cualquier repo (también si vive en un repo hermano); los de `cheap`, con la firma barata; de una unidad
    anidada en otro repo de la lista, el repo de afuera solo mira su puntero."""
    if not roots:
        return {}

    def excluder(root):
        return (lambda path: layout.is_output(pathlib.Path(root) / path)) if layout is not None else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(roots)))) as pool:
        futures = {key: pool.submit(repo_state, path, excluder(path), key in cheap, nested_paths(key, roots))
                   for key, path in roots.items()}
    return {key: future.result() for key, future in futures.items()}


def find_root(path):
    """La raíz del repo git que contiene la ruta, buscando .git hacia arriba sin llamar a git; None si no hay."""
    current = pathlib.Path(os.path.abspath(str(path)))
    for candidate in [current] + list(current.parents):
        if os.path.lexists(str(candidate / ".git")):
            return candidate
    return None


def unreadable_reason(err):
    return "sin permiso" if isinstance(err, PermissionError) else (err.strerror or str(err))


def git_children(folder, skip, main):
    """Las subcarpetas directas de folder que son repos git, y las que no se pudieron leer ([{"path", "reason"}])."""
    try:
        names = sorted(os.listdir(str(folder)))
    except OSError as err:
        return [], [{"path": display_path(folder, main), "reason": unreadable_reason(err)}]
    repos, unreadable = [], []
    for name in names:
        path = folder / name
        if name.startswith(".") or not os.path.isdir(str(path)) or os.path.realpath(str(path)) in skip:
            continue  # las carpetas ocultas no son repos del espacio de trabajo
        if not os.access(str(path), os.R_OK | os.X_OK):
            unreadable.append({"path": display_path(path, main), "reason": "sin permiso"})
        elif os.path.lexists(str(path / ".git")):
            repos.append(path)
    return repos, unreadable


def discover(main, units):
    """Los repos que mira la foto: el principal, los de las fuentes de las unidades del modelo y los repos git hermanos.
    Devuelve ({ruta real: {"root", "role", "units", "main_branch"}}, unidades sin clonar, carpetas sin leer)."""
    real_main = os.path.realpath(str(main))
    found = {real_main: {"root": main, "role": "main", "units": [], "main_branch": None}}
    missing, unreadable = [], []
    for unit in units:
        target = pathlib.Path(os.path.normpath(os.path.join(str(main), os.path.expanduser(unit["source"]))))
        real_target = os.path.realpath(str(target))
        inside = real_target == real_main or real_target.startswith(real_main.rstrip(os.sep) + os.sep)
        nested = find_root(target) if inside and os.path.lexists(str(target)) else None
        if nested is not None and os.path.realpath(str(nested)) != real_main:  # un submódulo o un repo anidado
            entry = found.setdefault(os.path.realpath(str(nested)),
                                     {"root": nested, "role": "unit", "units": [], "main_branch": None})
        elif inside:
            entry = found[real_main]
        elif not os.path.lexists(str(target)):
            missing.append({"unit": unit["id"], "path": unit["source"]})
            continue
        elif not os.access(str(target), os.R_OK | os.X_OK):
            unreadable.append({"path": unit["source"], "reason": "sin permiso"})
            continue
        else:
            root = find_root(target)
            if root is None:
                unreadable.append({"path": unit["source"], "reason": "no es un repo git"})
                continue
            entry = found.setdefault(os.path.realpath(str(root)),
                                     {"root": root, "role": "unit", "units": [], "main_branch": None})
        entry["units"].append(unit["id"])
        if not entry["main_branch"] and (entry is not found[real_main] or real_target == real_main):
            entry["main_branch"] = unit.get("main_branch")  # también si la fuente es una subcarpeta del vecino
    siblings, blocked = [], []
    if os.path.realpath(str(main.parent)) != os.path.realpath(os.path.expanduser("~")):  # en $HOME no hay vecinos
        siblings, blocked = git_children(main.parent, worktree_roots(main) | {real_main}, main)
    for path in siblings:
        found.setdefault(os.path.realpath(str(path)), {"root": path, "role": "sibling", "units": [], "main_branch": None})
    unique = {}
    for item in unreadable + blocked:  # una unidad hermana sin permiso sale de los dos lados: una sola vez
        unique.setdefault(os.path.normpath(item["path"]), item)
    return found, missing, list(unique.values())


def take_snapshot(main, layout, units):
    """La foto inicial de la tarea: el estado de cada repo que mira (principal, unidades y hermanos)."""
    found, missing, unreadable = discover(main, units)
    now = states({key: info["root"] for key, info in found.items()}, layout,
                 {key for key, info in found.items() if info["role"] == "sibling"})
    repos = []
    for key, info in found.items():
        entry = {"path": display_path(info["root"], main), "real": key, "role": info["role"], "units": info["units"]}
        entry.update(now[key])
        repos.append(entry)
    return {"skill": SKILL, "format": SNAPSHOT_FORMAT, "taken": datetime.datetime.now().isoformat(timespec="seconds"),
            "root": str(main), "repos": repos, "missing_units": missing, "unreadable": unreadable, "registered": []}


def photo_summary(snapshot):
    roles = [entry.get("role") for entry in snapshot["repos"]]
    units, siblings = roles.count("unit"), roles.count("sibling")
    parts = ["el principal"] + ([plural(units, "unidad", "unidades")] if units else []) + \
        ([plural(siblings, "repo hermano", "repos hermanos")] if siblings else [])
    text = ", ".join(parts[:-1]) + " y " + parts[-1] if len(parts) > 1 else parts[0]
    return "%s: %s" % (plural(len(roles), "repo"), text)


def load_snapshot(task, notes):
    path = task.snapshot
    if path is None or not real(path).is_file():
        return None
    try:
        data = json.loads(real(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        notes.append(f"⚠️  No pude leer la foto inicial ({path.name}: {err}): sigo como si la tarea no tuviera foto.")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("repos"), list):
        notes.append(f"⚠️  La foto inicial ({path.name}) no tiene el formato esperado: sigo como si no la hubiera.")
        return None
    return data


# ── Registro de unidades (--unit) ────────────────────────────────────────────
def unit_repo(repo, unit):
    """La ruta real de la raíz del repo donde vive la fuente de una unidad del modelo, o None si no está en disco."""
    source = unit_source(repo, unit)
    root = find_root(source) if os.path.lexists(str(source)) else None
    return os.path.realpath(str(root)) if root is not None else None


def unit_source(repo, unit):
    """La ruta (sin seguir enlaces) de la fuente de una unidad del modelo."""
    return pathlib.Path(os.path.normpath(os.path.join(str(repo), os.path.expanduser(unit["source"]))))


def unit_root(repo, value):
    """La raíz del repo de una unidad: el identificador de una unidad de ## Estructura (manda sobre una carpeta del
    principal con el mismo nombre) o la ruta de su fuente (relativa a la raíz del repo principal, o absoluta)."""
    unit = next((u for u in structure_units(repo) if u["id"] == value), None)
    if unit:
        path = unit_source(repo, unit)
    else:
        path = pathlib.Path(os.path.expanduser(value))
        path = pathlib.Path(os.path.normpath(str(path if path.is_absolute() else repo / path)))
    if not os.path.lexists(str(path)):
        raise RuntimeError(f'No encuentro la unidad "{value}" ({path}): pasa la ruta de su fuente, relativa a la raíz '
                           "del repo principal (por ejemplo ../core-lib), o su identificador de ## Estructura.")
    if os.path.isdir(str(path)) and not os.access(str(path), os.R_OK | os.X_OK):
        raise RuntimeError(f"No puedo leer {path}: dale al agente acceso a esa carpeta y vuelve a registrarla.")
    root = find_root(path)
    if root is None:
        raise RuntimeError(f"{path} no está dentro de un repo git: una unidad registrada necesita su repo.")
    return root


def register_unit(repo, layout, args):
    """Anota la unidad en "repos" del meta de la tarea (lo crea si falta) y en la foto, sin tocar nada más. Con la
    carpeta de la tarea bloqueada: varios --unit en paralelo no pierden registros."""
    task = layout.task(safe_slug(args.folder), args.date or datetime.date.today().isoformat())
    root = unit_root(repo, args.unit)
    if os.path.realpath(str(root)) == os.path.realpath(str(repo)):
        print(f"ℹ️  {args.unit} es del repo principal: ya entra al reporte, no hace falta registrarla.")
        return
    with task_lock(real(task.folder)):  # también .git/info/exclude: sin líneas repetidas con --unit en paralelo
        warning = ensure_ignored(repo, layout.root, task.file("meta"))
        if warning:
            print(warning, file=sys.stderr)
        record_unit(repo, task, root, args)


def record_unit(repo, task, root, args):
    relative = display_path(root, repo)
    real_root = os.path.realpath(str(root))
    meta_file = real(task.file("meta"))
    meta = {}
    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except ValueError as err:
            raise ValueError(f"{shown(task.file('meta'), repo)} no es un JSON válido ({err}): corrígelo y vuelve a "
                             "registrar la unidad (no lo toco, para no perder lo que tiene)")
        if not isinstance(meta, dict):
            raise ValueError(f"{shown(task.file('meta'), repo)} no es un objeto JSON: corrígelo y vuelve a registrar "
                             "la unidad")
    entries = meta.setdefault("repos", [])
    if not isinstance(entries, list):
        raise ValueError('"repos" del meta debe ser una lista: corrígelo y vuelve a registrar la unidad')

    def same(entry):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            return False
        path = os.path.normpath(os.path.join(str(repo), os.path.expanduser(entry["path"])))
        found = find_root(path) if os.path.lexists(path) else None
        return found is not None and os.path.realpath(str(found)) == real_root
    already = any(same(entry) for entry in entries)
    if not already:
        entry = {"path": relative, "name": root.name}
        branch_name = next((u["main_branch"] for u in structure_units(repo) if u.get("main_branch")
                            and unit_repo(repo, u) == real_root), None)  # también si la fuente es una subcarpeta
        if branch_name:
            entry["main_branch"] = branch_name
        entries.append(entry)
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(meta_file, meta)
    photo = task.snapshot
    if photo is not None and real(photo).is_file():
        try:
            data = json.loads(real(photo).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            registered = data.setdefault("registered", [])
            if isinstance(registered, list) and relative not in registered:
                registered.append(relative)
                write_json(real(photo), data, ascii_only=True)
    else:
        print("⚠️  La tarea no tiene foto inicial: el reporte usará \"repos\" del meta. Al empezar una tarea, pide la "
              "carpeta con --folder: así toma la foto.", file=sys.stderr)
    state = "ya estaba registrada" if already else "registrada"
    print(f"✔ Unidad {state}: {root.name} ({relative}) en \"repos\" de {shown(task.file('meta'), repo)}")


# ── Repos y archivos cambiados ───────────────────────────────────────────────
def toplevel(path):
    return pathlib.Path(git(path, "rev-parse", "--show-toplevel").decode().strip())


def branch(repo):
    name = git(repo, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    if name == "HEAD":
        return git(repo, "rev-parse", "--short", "HEAD").decode().strip() + " (detached)"
    return name


def ref_exists(root, ref):
    return subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", ref + "^{commit}"],
                          capture_output=True).returncode == 0


def main_branch_ref(root, preferred):
    """La ref de la rama principal del repo, o None: la del modelo (mejor origin/<rama> que <rama>), si no origin/HEAD,
    origin/main, origin/master, main o master."""
    candidates = ["origin/" + preferred, preferred] if preferred else []
    head = subprocess.run(["git", "-C", str(root), "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"],
                          capture_output=True, text=True)
    if head.returncode == 0 and head.stdout.strip():
        candidates.append(head.stdout.strip())
    return next((ref for ref in candidates + list(MAIN_BRANCHES) if ref_exists(root, ref)), None)


def resolve_base(repo):
    """Fija la base de comparación del repo: la explícita (--base o "base") manda; si no, el merge-base de HEAD con su
    rama principal; sin rama principal, HEAD con un aviso. Deja en el repo base (la ref para git), base_label (None si
    es explícita, (rama, commit corto) si es el merge-base o ("HEAD", motivo)) y warnings."""
    repo["warnings"] = []
    if repo["base"]:
        repo["base"], repo["base_label"] = str(repo["base"]), None
        return
    if not ref_exists(repo["root"], "HEAD"):  # un repo sin commits: todo lo que tiene es nuevo
        empty = subprocess.run(["git", "-C", str(repo["root"]), "hash-object", "-t", "tree", os.devnull],
                               capture_output=True, text=True).stdout.strip()
        repo["base"], repo["base_label"] = empty, ("HEAD", "repo sin commits: todo es nuevo")
        return
    preferred = repo.get("main_branch")
    if preferred and not (ref_exists(repo["root"], "origin/" + preferred) or ref_exists(repo["root"], preferred)):
        repo["warnings"].append(f'⚠️  {repo["name"]}: la rama principal "{preferred}" no existe (ni origin/{preferred}): '
                                "busco origin/HEAD, origin/main, origin/master, main y master.")
    ref = main_branch_ref(repo["root"], preferred)
    sha = None
    if ref:
        try:
            sha = git(repo["root"], "merge-base", "HEAD", ref).decode().strip()
        except RuntimeError:
            sha = None
    if not sha:
        repo["base"], repo["base_label"] = "HEAD", ("HEAD", "sin merge-base con " + ref if ref else "sin rama principal")
        repo["warnings"].append(
            f'⚠️  {repo["name"]}: ' + (f"HEAD no tiene historia en común con {ref}" if ref else
                                       "no encontré su rama principal (origin/HEAD, origin/main, origin/master, main "
                                       "ni master)") +
            ": comparo contra HEAD, así que lo ya commiteado en la rama no sale en el reporte. Pasa la rama principal "
            '(--main-branch, o "main_branch" en "repos") o la base (--base, o "base").')
        return
    short = git(repo["root"], "rev-parse", "--short", sha).decode().strip()
    repo["base"], repo["base_label"] = sha, (ref, short)


def base_text(repo):
    """La base usada, en palabras: la ref explícita, "merge-base con <rama> (<commit>)" o "HEAD (<motivo>)"."""
    label = repo["base_label"]
    if label is None:
        return repo["base"]
    if label[0] == "HEAD":
        return f"HEAD ({label[1]})"
    return f"merge-base con {label[0]} ({label[1]})"


def base_html(repo):
    label = repo["base_label"]
    if label is None:
        return f'<code>{e(repo["base"])}</code>'
    if label[0] == "HEAD":
        return f"<code>HEAD</code> · {e(label[1])}"
    return f"merge-base con <code>{e(label[0])}</code> · <code>{e(label[1])}</code>"


def describe(root, ref):
    try:
        return git(root, "describe", "--tags", "--always", ref).decode().strip()
    except RuntimeError:
        return None


def same_version(pinned, source):
    def clean(version):
        version = str(version).strip()
        return version[1:] if version[:1] in ("v", "V") and version[1:2].isdigit() else version
    return clean(pinned) == clean(source)


def new_repo(root, name, role, main=False, base=None, main_branch=None, units=()):
    return {"root": pathlib.Path(root), "real": os.path.realpath(str(root)), "name": name, "role": role, "main": main,
            "base": base, "main_branch": main_branch, "pinned": None, "source": None, "units": list(units),
            "explicit": False, "photo": None, "state": None}


def candidates(main, args, meta, snapshot, found, notes, skipped):
    """Los repos que pueden entrar al reporte, el principal primero: el principal, los de "repos" del meta, los
    registrados con --unit y, con foto, los de las unidades del modelo. {ruta real: repo}."""
    real_main = os.path.realpath(str(main))
    info = found[real_main]
    ordered = {real_main: new_repo(main, main.name, "main", True, args.base, args.main_branch or info["main_branch"],
                                   info["units"])}
    for entry in meta.get("repos", []):
        path = pathlib.Path(os.path.expanduser(str(entry["path"])))
        path = path if path.is_absolute() else main / path
        label = entry.get("name") or entry["path"]
        if not os.path.lexists(str(path)):
            raise RuntimeError(
                f'No puedo leer el repo relacionado "{label}" ({path}): no existe. Si está en otra carpeta, dale al '
                f'agente acceso a esa carpeta o corrige "path" en "repos" del meta.')
        try:
            root = toplevel(path)
        except (RuntimeError, OSError) as err:  # existe pero git no lo lee: queda fuera, sin cortar el reporte
            reason = str(err).strip().splitlines()[-1] if str(err).strip() else "git no lo pudo leer"
            skipped.append({"name": str(label), "reason": "git no lo pudo leer (%s)" % reason})
            notes.append(f'⚠️  No puedo leer el repo de la unidad registrada "{label}" ({path}): {reason}. Queda fuera '
                         "del reporte; si la tarea lo cambió, dale al agente acceso a esa carpeta y vuelve a generar.")
            continue
        key = os.path.realpath(str(root))
        name = str(entry.get("name") or root.name)
        if key == real_main:
            repo = ordered[real_main]
            repo["name"] = name
            repo["base"] = repo["base"] or entry.get("base")
            repo["main_branch"] = args.main_branch or entry.get("main_branch") or repo["main_branch"]
            continue
        unit = found.get(key, {})
        repo = ordered.setdefault(key, new_repo(root, name, "registered", units=unit.get("units", [])))
        repo.update(name=name, base=entry.get("base"), pinned=entry.get("pinned_version"),
                    source=entry.get("source_version"), explicit=True,
                    main_branch=entry.get("main_branch") or unit.get("main_branch"))
    if snapshot is None:
        return ordered
    for relative in snapshot.get("registered") or []:
        if not isinstance(relative, str):
            continue
        path = os.path.normpath(os.path.join(str(main), os.path.expanduser(relative)))
        root = find_root(path) if os.path.lexists(path) else None
        if root is None:
            notes.append(f"⚠️  La unidad registrada {relative} ya no está en disco: no entra al reporte.")
            continue
        key = os.path.realpath(str(root))
        if key not in ordered:
            unit = found.get(key, {})
            ordered[key] = new_repo(root, root.name, "registered", main_branch=unit.get("main_branch"),
                                    units=unit.get("units", []))
    for key, unit in found.items():
        if unit["role"] == "unit" and key not in ordered:
            ordered[key] = new_repo(unit["root"], unit["root"].name, "unit", main_branch=unit["main_branch"],
                                    units=unit["units"])
    return ordered


def nested_units(repo, repos):
    """{ruta: se salta} de los repos de la tarea que viven dentro de este (un submódulo o un repo anidado que es
    unidad). Se salta si no tiene puntero en la base (un repo anidado sin rastrear nunca es un archivo de este) o si su
    HEAD es el commit que guarda la base: el cambio está solo dentro y lo muestra su propia sección. Un puntero que sí
    cambió entra como un cambio del repo de afuera."""
    inside = {}
    root = os.path.realpath(str(repo["root"])).rstrip(os.sep) + os.sep
    for other in repos:
        if other["real"] != repo["real"] and other["real"].startswith(root):
            path = pathlib.Path(os.path.relpath(other["real"], root.rstrip(os.sep))).as_posix()
            recorded = blobs_at(repo["root"], repo.get("base"), [path]).get(path)
            head = subprocess.run(["git", "-C", str(other["root"]), "rev-parse", "-q", "--verify", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            inside[path] = recorded is None or recorded == "dir" or (bool(head) and recorded == head)
    return inside


def check_names(repos):
    """Nombres que sirven de prefijo y no se repiten. Uno que puso el meta y choca falla; uno automático se desambigua."""
    taken = set()
    for repo in repos:
        name = repo["name"]
        if not name or ":" in name or "/" in name:
            raise ValueError(f'el nombre de repo "{name}" no sirve como prefijo: sin ":" ni "/"')
        if name in taken:
            if repo["main"] or repo["explicit"]:
                raise ValueError(f'dos repos se llaman "{name}": ponles "name" distintos en "repos" del meta')
            number = 2
            while f"{name}-{number}" in taken:
                number += 1
            repo["name"] = name = f"{name}-{number}"
        taken.add(name)
    for repo in repos:
        repo["aliases"] = {repo["name"], repo["root"].name} | {unit for unit in repo["units"]
                                                              if ":" not in unit and "/" not in unit}


def finish_repo(repo):
    """La base, la rama y las versiones de un repo que entra al reporte."""
    resolve_base(repo)
    check_version(repo)
    state = repo.get("state") or {}
    if "branch" in state:
        repo["branch"] = state["branch"] or ((state.get("head") or "")[:7] + " (detached)")
    else:
        repo["branch"] = branch(repo["root"])
    photo = repo.get("photo") or {}
    repo["branch_before"] = photo.get("branch") if "branch" in photo else None


def check_version(repo):
    """Si el fuente no coincide con la versión que fija la app (necesita la base)."""
    if repo["pinned"] and not repo["source"]:  # lo que había en el fuente al empezar: la base, no lo de la tarea
        repo["source"] = describe(repo["root"], repo["base"])
    repo["version_mismatch"] = bool(repo["pinned"] and repo["source"]
                                    and not same_version(repo["pinned"], repo["source"]))
    if repo["version_mismatch"]:
        repo["warnings"].append(
            f'⚠️  {repo["name"]}: el fuente ({repo["source"]}) no coincide con la versión que fija la app '
            f'({repo["pinned"]}): lo probado en fuente puede no compilar o comportarse distinto con lo publicado.')


def changed_files(repo, base, layout):
    """Los archivos cambiados contra la base, con -z: un nombre con acentos, comillas o tabuladores llega tal cual (sin
    las comillas de core.quotePath), igual que en la foto. Un cambio de tipo (T: un enlace que pasa a archivo) es una
    modificación."""
    files = []
    try:
        fields = git(repo["root"], "diff", "--name-status", "-z", "-M", base).decode("utf-8", "surrogateescape")
    except RuntimeError as err:
        raise RuntimeError(f'{repo["name"]}: no pude comparar contra {base}: {err}')
    fields, index = fields.split("\0"), 0
    while index < len(fields) - 1:
        status, index = fields[index][:1], index + 1
        if status in ("R", "C"):
            old, path, index = fields[index], fields[index + 1], index + 2
            files.append({"status": "M" if status == "R" else "A", "path": path,
                          "old": old if status == "R" else None})
        elif status in ("A", "M", "D", "T"):
            path, index = fields[index], index + 1
            files.append({"status": "M" if status == "T" else status, "path": path, "old": path})
        elif status:
            index += 1  # U (sin resolver) u otro: no es un cambio del árbol de trabajo
    untracked = git(repo["root"], "ls-files", "-z", "--others", "--exclude-standard").decode("utf-8", "surrogateescape")
    for path in untracked.split("\0"):
        if path:
            files.append({"status": "A", "path": path.rstrip("/"), "old": None, "untracked": True})
    return [f for f in files if not layout.is_output(repo["root"] / f["path"])]


def read_before(repo, base, path):
    if path is None:
        return None
    try:
        return git(repo, "show", f"{base}:{path}")
    except RuntimeError:
        return None


NO_PERMISSION = object()  # un archivo que no se puede leer: se muestra así, sin cortar el reporte


def read_after(repo, path):
    p = repo / path
    try:
        if p.is_symlink():
            return os.fsencode(os.readlink(str(p)))  # git guarda el destino del enlace, en bytes
        return p.read_bytes() if p.is_file() else None
    except PermissionError:
        return NO_PERMISSION


# ── Qué es de la tarea: comparación con la foto ──────────────────────────────
def changed_since(state, before):
    """Si el repo cambió después de la foto: otro HEAD u otros archivos sucios (o el mismo con otro contenido)."""
    if not isinstance(before, dict) or "error" in before or "error" in state:
        return True
    return state.get("head") != before.get("head") or (state.get("dirty") or {}) != (before.get("dirty") or {})


def change_detail(state, before):
    """Qué cambió en un repo desde la foto, en palabras; "" si nada."""
    now = state.get("dirty") or {}
    if before is None:
        return f"apareció después de la foto, con {plural(len(now), 'archivo')} sin commit" if now else ""
    if not isinstance(before, dict) or "error" in before:
        return ""
    old = before.get("dirty") or {}
    files = [path for path in set(now) | set(old) if now.get(path, ABSENT) != old.get(path, ABSENT)]
    parts = [plural(len(files), "archivo") + " sin commit"] if files else []
    if state.get("head") != before.get("head"):
        parts.append("commits nuevos")
    return " y ".join(parts)


def blobs_at(root, head, paths):
    """El hash de cada ruta en un commit, con un solo `git cat-file --batch-check`; las que no estaban no salen."""
    if not head or not paths:
        return {}
    data = "".join("%s:%s\n" % (head, path) for path in paths).encode("utf-8", "surrogateescape")
    try:
        result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                                input=data, capture_output=True, timeout=STATUS_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    found = {}
    for path, line in zip(paths, result.stdout.decode("utf-8", "replace").splitlines()):
        parts = line.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in ("blob", "commit", "submodule"):  # el puntero de un submódulo
            found[path] = parts[0]
        elif len(parts) == 2 and parts[1] == "tree":
            found[path] = "dir"
    return found


def merge_base(root, one, other):
    """El merge-base de dos refs, o None si falta alguna o git no lo encuentra."""
    if not one or not other:
        return None
    try:
        return git(root, "merge-base", one, other).decode().strip() or None
    except RuntimeError:
        return None


def isolated_since(root, head):
    """Si el diff desde `head` es solo de la rama: `head` es ancestro de HEAD y no hay merges en medio (sin rebase ni
    merge de la rama principal después)."""
    if not head:
        return False
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", head, "HEAD"],
                      capture_output=True).returncode != 0:
        return False
    merges = subprocess.run(["git", "-C", str(root), "rev-list", "--merges", head + "..HEAD"], capture_output=True,
                            text=True)
    return merges.returncode == 0 and not merges.stdout.strip()


def attribute(repo, files):
    """Para cada archivo cambiado contra la base: "task" (cambió después de la foto), "mixed" (ya estaba sucio y además
    cambió), "mixed-committed" (ya tenía cambios commiteados en la rama antes de la foto y además cambió) o "previous"
    (está como en la foto: ya estaba antes de la tarea), con el motivo. Lo que estaba limpio en la foto y sigue limpio
    se compara commit contra commit, no contra el árbol de trabajo: con filtros de git (eol=crlf, LFS) el contenido del
    disco no es el que guarda git."""
    photo = repo.get("photo")
    if not isinstance(photo, dict) or "error" in photo:
        return {id(f): ("task", None) for f in files}
    dirty = photo.get("dirty") or {}
    state = repo.get("state") if isinstance(repo.get("state"), dict) and "error" not in repo["state"] else None
    dirty_now = state.get("dirty") or {} if state is not None else None
    names = sorted({name for f in files for name in (f["path"], f["old"]) if name and name not in dirty})
    at_photo = blobs_at(repo["root"], photo.get("head"), names)
    at_now = blobs_at(repo["root"], state.get("head"), names) if state is not None else {}
    # Lo que la rama ya tenía commiteado en la foto se mide contra la base de entonces, no la de ahora: tras un rebase o
    # un merge de la rama principal, la base actual trae cambios ajenos. Sin commits en la foto, no había nada previo.
    photo_base = merge_base(repo["root"], photo.get("head"), repo.get("base"))
    at_photo_base = blobs_at(repo["root"], photo_base, names) if photo_base else at_photo
    verdicts = {}
    for f in files:
        paths = [f["path"]] + ([f["old"]] if f["old"] and f["old"] != f["path"] else [])
        if any(path in dirty for path in paths):
            before = {path: dirty[path] if path in dirty else at_photo.get(path) for path in paths}
            now = {path: current_value(repo["root"], path, before[path]) for path in paths}
            verdicts[id(f)] = ("previous", "sin commit desde antes de la tarea") if before == now else ("mixed", None)
            continue
        clean_now = dirty_now is not None and not any(path in dirty_now for path in paths)
        before = {path: at_photo.get(path) for path in paths}
        if clean_now:
            changed = before != {path: at_now.get(path) for path in paths}
        else:
            changed = before != {path: content_hash(repo["root"] / path) for path in paths}
        if not changed:
            verdicts[id(f)] = ("previous", "commiteado en la rama antes de la tarea")
        elif any(at_photo_base.get(path) != at_photo.get(path) for path in paths):
            verdicts[id(f)] = ("mixed-committed", None)
        else:
            verdicts[id(f)] = ("task", None)
    return verdicts


class Coverage:
    """Qué entra al reporte y qué queda fuera."""

    def __init__(self):
        self.repos = []         # los repos que cambiaron después de la foto (o todos los candidatos, sin foto)
        self.unchanged = []     # candidatos que no cambiaron después de la foto
        self.others = []        # [{"path", "detail"}]: repos hermanos que cambiaron y no son de la tarea
        self.unattributed = []  # [{"repo", "path", "reason"}]: cambios que ya estaban o que no se sabe de quién son
        self.dirty_without_photo = []  # sin foto: repos (unidades y hermanos) con cambios sin commit, para la salida
        self.dirty_units_without_photo = []  # sin foto: solo las unidades del modelo (van al HTML)
        self.dirty_siblings_without_photo = []  # sin foto: repos hermanos que no son unidades (solo en la salida)
        self.claimed = []       # archivos que el meta explica y que ya estaban así en la foto
        self.notes = []
        self.unreadable = []
        self.skipped = []       # [{"name", "reason"}]: repos de la tarea que quedaron fuera porque git no los leyó
        self.nested = []        # los repos de la tarea, para saber cuáles viven dentro de otro
        self.photo = False


def coverage(main, layout, args, meta, snapshot, units):
    cov = Coverage()
    cov.photo = snapshot is not None
    found, _missing, cov.unreadable = discover(main, units)
    ordered = candidates(main, args, meta, snapshot, found, cov.notes, cov.skipped)
    cov.nested = [{"real": key, "root": info["root"]} for key, info in found.items() if info["role"] == "unit"] + \
        list(ordered.values())  # las unidades que pueden vivir dentro de otro repo de la tarea
    check_names(list(ordered.values()))
    if snapshot is not None:
        photo = {entry["real"]: entry for entry in snapshot.get("repos", [])
                 if isinstance(entry, dict) and isinstance(entry.get("real"), str)}
        roots = {key: repo["root"] for key, repo in ordered.items()}
        roots.update({key: info["root"] for key, info in found.items() if key not in roots})
        # el mismo modo que la foto: un repo que era hermano ajeno se compara con su firma barata
        cheap = {key for key in roots if (photo.get(key) or {}).get("role", (found.get(key) or {}).get("role"))
                 == "sibling"}
        now = states(roots, layout, cheap)
        for key, repo in ordered.items():
            repo["photo"], repo["state"] = photo.get(key), now[key]
            if "error" in now[key]:
                if repo["role"] == "unit":  # del modelo y sin registrar: si git no la lee, no corta el reporte
                    cov.skipped.append({"name": repo["name"], "reason": "git no lo pudo leer (%s)" % now[key]["error"]})
                    cov.notes.append(f'⚠️  No pude leer {repo["name"]} ({now[key]["error"]}): es una unidad del modelo '
                                     "que no está registrada y queda fuera del reporte. Si la tarea la cambió, dale al "
                                     "agente acceso a esa carpeta y vuelve a generar.")
                    continue
                cov.notes.append(f'⚠️  No pude leer el estado de {repo["name"]} ({now[key]["error"]}): lo comparo '
                                 "contra su base, sin la foto.")
            (cov.repos if changed_since(now[key], photo.get(key)) else cov.unchanged).append(repo)
        for key, path in roots.items():
            if key in ordered or "error" in now[key]:
                continue
            detail = change_detail(now[key], photo.get(key))
            if detail:
                cov.others.append({"path": display_path(path, main), "detail": detail})
    else:
        if not args.ignore_snapshot:  # con --ignore-snapshot ya lo dice su propio aviso
            cov.notes.append("ℹ️  La tarea no tiene foto inicial (empezó antes de hb-implement 1.7.0, o sin report.py "
                             "--folder al empezar): entran el repo principal y \"repos\" del meta.")
        cov.repos = list(ordered.values())
        rest = {key: info["root"] for key, info in found.items() if key not in ordered}
        now = states(rest, layout, {key for key in rest if found[key]["role"] == "sibling"})
        for key, path in rest.items():
            dirty = now[key].get("dirty") or {}
            if not dirty:
                continue
            where = display_path(path, main)
            cov.dirty_without_photo.append(where)
            if found[key]["role"] != "unit":  # un repo hermano ajeno: solo en la salida, nunca en el HTML
                cov.dirty_siblings_without_photo.append(where)
                continue
            cov.dirty_units_without_photo.append(where)
            for relative in sorted(dirty):
                cov.unattributed.append({"repo": where, "path": relative,
                                         "reason": "sin foto inicial: no se sabe si es de la tarea"})
    return cov


# ── Migración de lenguaje ────────────────────────────────────────────────────
def suffix(path):
    return pathlib.PurePosixPath(path).suffix.lower()


def stem(path):
    return pathlib.PurePosixPath(path).stem.lower()


def has_code(text):
    """Si el texto tiene código: algo más que comentarios, líneas vacías y declaraciones de paquete o imports. Un archivo
    sin permiso de lectura cuenta como código: no se sabe que esté vacío."""
    if text is NO_PERMISSION:
        return True
    if not isinstance(text, str):
        return text is False  # un binario no es código fuente, pero tampoco está vacío
    body = re.sub(r"(?s)/\*.*?\*/|<!--.*?-->", "", text)
    body = re.sub(r'(?s)^\s*(?:"""|\'\'\').*?(?:"""|\'\'\')', "", body)
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("//", "#", "--", ";", "*")) or NOT_CODE.match(line):
            continue
        return True
    return False


def place(path):
    """La carpeta de un archivo, con las carpetas de lenguaje de un source set como comodín."""
    return tuple("*" if part.lower() in LANGUAGE_DIRS else part for part in pathlib.PurePosixPath(path).parent.parts)


def same_language(one, other):
    return suffix(one) == suffix(other) or any(suffix(one) in family and suffix(other) in family
                                               for family in SAME_LANGUAGE)


def language_migrations(files):
    """[(archivo, equivalente, cómo)]: un archivo de código borrado, vaciado o reducido a comentarios cuyo equivalente
    del mismo repo, en el mismo lugar y con el mismo nombre base, aparece en otro lenguaje."""
    by_stem = {}
    for f in files:
        if suffix(f["path"]) in SOURCE_EXTENSIONS and f["status"] != "D":
            by_stem.setdefault((f["repo"]["real"], place(f["path"]), stem(f["path"])), []).append(f)
    found = []
    for f in files:
        renamed = f["status"] == "M" and f["old"] not in (None, f["path"])
        source = f["old"] if renamed else f["path"]
        if suffix(source) not in SOURCE_EXTENSIONS:
            continue
        if renamed and not same_language(f["path"], source) and suffix(f["path"]) in SOURCE_EXTENSIONS \
                and stem(f["path"]) == stem(source) and place(f["path"]) == place(source):
            found.append((f, f, "renombrado"))
            continue
        if f["status"] == "D":
            how = "borrado"
        elif f["status"] == "M" and isinstance(f["before"], str) and has_code(f["before"]) and not has_code(f["after"]):
            how = "vaciado" if not (f["after"] or "").strip() else "reducido a comentarios"
        else:
            continue
        for other in by_stem.get((f["repo"]["real"], place(source), stem(source)), []):
            if other is not f and not same_language(other["path"], source):
                found.append((f, other, how))
    return found


def migration_text(f, other, how):
    if f is other:
        return f'{f["old"]} → {f["path"]} (renombrado a otra extensión)'
    return f'{f["path"]} ({how}) → {other["path"]}'


# ── Validación del meta ──────────────────────────────────────────────────────
def strict_entries(meta, key, required):
    """Las listas que deciden qué entra al reporte ("repos", "temporary"): si no sirven, falla antes de escribir."""
    value = meta.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f'"{key}" debe ser una lista de objetos')
    for item in value:
        missing = [field for field in required if not str(item.get(field) or "").strip()]
        if missing:
            raise ValueError(f'cada entrada de "{key}" necesita {", ".join(missing)}')
    return value


def keep_text(container, key, what, notes, numbers=False):
    """Un campo de texto: vacío se quita sin avisar; de otro tipo, se quita con un aviso."""
    value = container.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        container.pop(key, None)
    elif numbers and isinstance(value, (int, float)) and not isinstance(value, bool):
        container[key] = str(value)
    elif not isinstance(value, str):
        notes.append(f"⚠️  {what} debe ser un texto: lo ignoro.")
        container.pop(key)


def keep_texts(container, key, what, notes, analyzed_empty=False):
    """Una lista de textos: sin textos se quita. Con analyzed_empty, una lista vacía ([]) se conserva: se analizó y no
    hubo ninguno (por ejemplo, "cons": [] es "Sin contras identificados")."""
    value = container.get(key)
    if value is None:
        container.pop(key, None)
    elif analyzed_empty and value == []:
        container[key] = []
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        items = [item for item in value if item.strip()]
        if items:
            container[key] = items
        else:
            container.pop(key)
    else:
        notes.append(f"⚠️  {what} debe ser una lista de textos: lo ignoro.")
        container.pop(key)


def keep_level(container, key, what, notes):
    value = container.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        container.pop(key, None)
        return
    normalized = value.strip().lower().replace("í", "i") if isinstance(value, str) else None
    if normalized in LEVELS:
        container[key] = normalized
    else:
        notes.append(f'⚠️  {what} debe ser critico, alto, medio o bajo (llegó "{value}"): lo ignoro.')
        container.pop(key)


def keep_objects(meta, key, notes, required=()):
    value = meta.get(key)
    if value is None:
        meta[key] = []
        return []
    if not isinstance(value, list):
        notes.append(f'⚠️  "{key}" debe ser una lista: lo ignoro.')
        meta[key] = []
        return []
    kept = []
    for number, item in enumerate(value, 1):
        if not isinstance(item, dict):
            notes.append(f'⚠️  La entrada {number} de "{key}" no es un objeto: la ignoro.')
            continue
        missing = [field for field in required if not (isinstance(item.get(field), str) and item[field].strip())]
        if missing:
            notes.append(f'⚠️  La entrada {number} de "{key}" no trae {", ".join(missing)}: la ignoro.')
            continue
        kept.append(item)
    meta[key] = kept
    return kept


def clean_meta(meta, notes):
    """Lo que decide qué entra al reporte ("repos", "temporary", "slug", "date") falla antes de escribir si no sirve.
    Los datos de análisis y de presentación nunca detienen el reporte: lo que falta o viene vacío no se muestra y un
    valor con formato inválido se ignora con un aviso en notes."""
    if not isinstance(meta, dict):
        raise ValueError("el meta debe ser un objeto JSON")
    if "slug" in meta and not isinstance(meta["slug"], str):
        raise ValueError('"slug" debe ser un texto')
    if meta.get("date") is not None and not (isinstance(meta["date"], str) and DATE.match(meta["date"])):
        raise ValueError("la fecha %r no es AAAA-MM-DD: va en el nombre de la carpeta de la tarea" % (meta["date"],))
    for repo in strict_entries(meta, "repos", ("path",)):
        for field in ("base", "main_branch", "pinned_version", "source_version"):
            if field in repo and repo[field] is not None and not isinstance(repo[field], str):
                raise ValueError(f'"{field}" de "repos" debe ser un texto')
    strict_entries(meta, "temporary", ("path",))
    for key in ("project", "title", "description", "scope", "root_cause", "branch_note"):
        keep_text(meta, key, f'"{key}"', notes)
    keep_text(meta, "ticket", '"ticket"', notes, numbers=True)
    if "type" in meta and not isinstance(meta["type"], str):
        notes.append('⚠️  "type" debe ser un texto: uso feature.')
        meta["type"] = "feature"
    elif meta.get("type") and meta["type"] not in TYPES:
        notes.append(f'⚠️  "type" debe ser feature, bugfix, enhancement o refactor (llegó "{meta["type"]}"): el '
                     "reporte lo muestra como feature.")
    keep_level(meta, "severity", '"severity"', notes)
    files = meta.get("files")
    if files is not None and not isinstance(files, dict):
        notes.append('⚠️  "files" debe ser un objeto con un objeto por archivo: lo ignoro.')
        files = None
    meta["files"] = {}
    for key, info in (files or {}).items():
        if not isinstance(info, dict):
            notes.append(f"⚠️  La entrada de {key} en \"files\" no es un objeto: la ignoro.")
            continue
        for field in ("why", "before", "after", "layer"):
            keep_text(info, field, f'"{field}" de {key}', notes)
        keep_level(info, "risk", f'"risk" de {key}', notes)
        keep_texts(info, "pros", f'"pros" de {key}', notes, analyzed_empty=True)
        keep_texts(info, "cons", f'"cons" de {key}', notes, analyzed_empty=True)
        meta["files"][key] = info
    for item in keep_objects(meta, "impact", notes, ("label",)):
        keep_text(item, "value", '"value" de "impact"', notes, numbers=True)
    for item in keep_objects(meta, "diagrams", notes, ("mermaid",)):
        for field in ("title", "description"):
            keep_text(item, field, f'"{field}" de "diagrams"', notes)
    for group in keep_objects(meta, "groups", notes, ("match",)):
        for field in ("why", "before", "after"):
            keep_text(group, field, f'"{field}" del grupo {group["match"]}', notes)
    keep_objects(meta, "previews", notes, ("image",))
    for step in keep_objects(meta, "dod", notes):
        for field in ("icon", "name", "command", "note", "output", "unit"):
            keep_text(step, field, f'"{field}" de un paso del DoD', notes)
        if not isinstance(step.get("status"), str) or step["status"] not in PILLS:
            if "status" in step:
                notes.append(f'⚠️  El paso del DoD "{step.get("name", "")}" trae "status" {step["status"]!r}: lo '
                             "muestro como skipped.")
            step["status"] = "skipped"
    return meta


def explained(info):
    return bool(info) and any(info.get(field) for field in ("why", "before", "after"))


def analyzed(info, field):
    """Si el flujo completó el campo. "pros": [] y "cons": [] cuentan: se analizó y no hubo (los pros vacíos no se
    muestran; los contras vacíos dicen "Sin contras identificados")."""
    return field in info if field in ("pros", "cons") else bool(info.get(field))


def missing_analysis(meta, files):
    """Los datos de análisis que el flujo debería completar y no vinieron (solo para avisar: no son obligatorios)."""
    report = [field for field in ("diagrams", "impact") if not meta.get(field)]
    if meta.get("type") == "bugfix":
        report += [field for field in ("severity", "root_cause") if not meta.get(field)]
    per_file = [f["key"] for f in files if f["group"] is None and explained(f["info"])
                and not all(analyzed(f["info"], field) for field in ("risk", "pros", "cons"))]
    return report, per_file


# ── HTML ─────────────────────────────────────────────────────────────────────
def chip(text, kind):
    return f'<span class="chip {kind}">{e(text)}</span>'


def code_block(text, dim=False):
    if text is NO_PERMISSION:
        return '<div class="empty-state">Sin permiso de lectura: no se muestra el contenido.</div>'
    if text is False:
        return '<div class="empty-state">Archivo binario: no se muestra el contenido.</div>'
    if text is None:
        return '<div class="empty-state">Sin contenido para mostrar.</div>'
    lines = text.splitlines()
    if not lines:
        return '<div class="empty-state">Archivo vacío.</div>'
    body = "\n".join(f'<span class="ln">{i}</span>{e(line)}' for i, line in enumerate(lines[:MAX_LINES], 1))
    if len(lines) > MAX_LINES:
        body += f'\n<span class="ln">…</span>(recortado: {len(lines) - MAX_LINES} líneas más)'
    return f'<pre class="code{" dim" if dim else ""}">{body}</pre>'


def diff_block(before, after):
    if before is NO_PERMISSION or after is NO_PERMISSION:
        return '<div class="empty-state">Sin permiso de lectura: no se muestra el diff.</div>'
    if before is False or after is False:
        return '<div class="empty-state">Archivo binario: no se muestra el diff.</div>'
    rows, new_no = [], 0
    lines = difflib.unified_diff((before or "").splitlines(), (after or "").splitlines(), lineterm="", n=3)
    for line in list(lines)[2:]:
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_no = int(m.group(1)) - 1 if m else new_no
            rows.append(("hunk", "···", line))
        elif line.startswith("+"):
            new_no += 1
            rows.append(("add", "+", line))
        elif line.startswith("-"):
            rows.append(("del", "−", line))
        else:
            new_no += 1
            rows.append(("", str(new_no), line))
    if not rows:
        return '<div class="empty-state">Sin cambios de contenido (solo renombre o permisos).</div>'
    body = "".join(f'<div class="dl {kind}"><span class="g">{gutter}</span><span class="c">{e(text)}</span></div>'
                   for kind, gutter, text in rows)
    return f'<div class="diff"><div class="diff-inner">{body}</div></div>'


def explain(status, info):
    if status == "A":
        items = [("ex-after", "✅ Por qué se crea", info.get("why"))]
    elif status == "D":
        items = [("ex-before", "🗑️ Por qué se elimina", info.get("why"))]
    else:
        items = [("ex-before", "⚠️ Antes", info.get("before")),
                 ("ex-after", "✅ Después", info.get("after") or info.get("why"))]
    cells = "".join(f'<div class="ex {kind}"><div class="k">{label}</div><p>{e(text)}</p></div>'
                    for kind, label, text in items if text)
    return f'<div class="explain">{cells}</div>' if cells else ""


def pros_cons(info):
    """Pros y contras del cambio. Un campo ausente no se muestra; "cons": [] dice "Sin contras identificados" (se
    analizó y no hubo contras). "pros" vacío no se muestra."""
    cells = ""
    for key, kind, label in (("pros", "ex-pros", "👍 Pros"), ("cons", "ex-cons", "👎 Contras")):
        if info.get(key):
            items = "".join(f"<li>{e(item)}</li>" for item in info[key])
            cells += f'<div class="ex {kind}"><div class="k">{label}</div><ul>{items}</ul></div>'
        elif key == "cons" and info.get(key) == []:
            cells += f'<div class="ex {kind}"><div class="k">{label}</div><p class="none">Sin contras identificados</p></div>'
    return f'<div class="proscons">{cells}</div>' if cells else ""


STATUS = {"A": ("st-new", "Nuevo"), "M": ("st-modified", "Modificado"), "D": ("st-deleted", "Eliminado")}


def file_entry(fid, f, info):
    kind, label = STATUS[f["status"]]
    path = f["path"] if f["status"] != "M" or f["old"] in (None, f["path"]) else f'{f["old"]} → {f["path"]}'
    chips = chip(label, kind) + f'<code class="file-path">{e(path)}</code>'
    if info.get("layer"):
        chips += chip("Capa: " + info["layer"], "c-same")
    if info.get("risk"):
        chips += chip(RISK_LABELS[info["risk"]], "risk-" + info["risk"])
    if f["warnings"]:
        chips += chip("⚠️ " + plural(len(f["warnings"]), "aviso"), "c-warn")
    notes = "".join(f'<div class="note warn">{e(text)}</div>' for text in f["warnings"])
    body = explain(f["status"], info) + pros_cons(info) + (f'<div class="file-notes">{notes}</div>' if notes else "")
    if f["status"] == "A":
        body += code_block(f["after"])
    elif f["status"] == "D":
        body += code_block(f["before"], dim=True)
    else:
        tabs = "".join(
            f'<button type="button" class="tab{" active" if name == "diff" else ""}" id="{fid}-tab-{name}" '
            f'role="tab" aria-selected="{"true" if name == "diff" else "false"}" '
            f'onclick="switchTab(\'{fid}\',\'{name}\')">{title}</button>'
            for name, title in (("before", "Antes"), ("after", "Después"), ("diff", "Diff")))
        body += (f'<div class="tabs" role="tablist">{tabs}</div>'
                 f'<div class="panel" id="{fid}-before">{code_block(f["before"])}</div>'
                 f'<div class="panel" id="{fid}-after">{code_block(f["after"])}</div>'
                 f'<div class="panel active" id="{fid}-diff">{diff_block(f["before"], f["after"])}</div>')
    return (f'<details class="file" open id="{fid}"><summary>{chips}</summary>'
            f'<div class="file-body">{body}</div></details>')


def group_for(path, groups):
    """El primer grupo cuyo "match" cubre la ruta: una carpeta (termina en /) o un patrón fnmatch."""
    for group in groups:
        pattern = group.get("match") or ""
        if pattern.endswith("/") and path.startswith(pattern):
            return group
        if pattern and not pattern.endswith("/") and fnmatch.fnmatchcase(path, pattern):
            return group
    return None


def group_entry(fid, group, status, paths):
    kind, label = STATUS[status]
    total = plural(len(paths), "archivo")
    chips = chip(label, kind) + f'<code class="file-path">{e(group["match"])} · {total}</code>'
    listing = '<pre class="code">' + e("\n".join(paths)) + "</pre>"
    return (f'<details class="file" open id="{fid}"><summary>{chips}</summary>'
            f'<div class="file-body">{explain(status, group)}{listing}</div></details>')


def dod_table(steps):
    if not steps:
        return ""
    rows, outputs = [], []
    for step in steps:
        kind, label = PILLS[step["status"]]
        note = f' <span class="muted">· {e(step["note"])}</span>' if step.get("note") else ""
        command = f'<code>{e(step["command"])}</code>' if step.get("command") else ""
        rows.append(f'<tr><td>{e(step.get("icon", "•"))}</td><td>{e(step.get("name", ""))}</td><td>{command}</td>'
                    f"<td>{chip(label, kind)}{note}</td></tr>")
        if step.get("output"):
            outputs.append(f'<details class="file" open><summary><code class="file-path">Salida de '
                           f'{e(step.get("name", ""))}</code></summary>{code_block(step["output"])}</details>')
    return ('<div class="table-wrap"><table class="dod"><thead><tr><th></th><th>Paso</th><th>Comando</th>'
            f'<th>Resultado</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>{"".join(outputs)}')


def dod_stat(steps):
    statuses = {s.get("status") for s in steps}
    if not steps:
        return "—", ""
    if "fail" in statuses:
        return "FAIL", "red"
    if statuses == {"pass"}:
        return "PASS", "green"
    return "PARTIAL", "orange"


def dod_chip(steps):
    value, color = dod_stat(steps)
    kinds = {"green": "c-ok", "red": "c-ko", "orange": "c-warn"}
    return chip(value, kinds[color]) if steps else '<span class="muted">—</span>'


def dod_owner(step, repos):
    """La unidad de un paso del DoD: su "unit" o el prefijo del nombre ("core-lib · Tests"); None si es del proyecto."""
    label = step.get("unit")
    if not label:
        found = re.match(r"^\s*(.+?)\s+·\s+\S", step.get("name") or "")
        label = found.group(1) if found else None
    return next((repo for repo in repos if label and label.strip() in repo["aliases"]), None)


def preview_path(repo, task, image):
    """La imagen de un preview: absoluta, relativa al repo (la ruta previews: que imprime --folder, aunque pase por un
    enlace simbólico) o relativa a la carpeta de la tarea (previews/<archivo>)."""
    path = pathlib.Path(os.path.expanduser(str(image)))
    if path.is_absolute():
        return path
    candidates_found = [repo / path] + ([task.folder / path] if task is not None else [])
    return next((candidate for candidate in candidates_found if candidate.is_file()), candidates_found[0])


def preview_figure(repo, preview, missing, task=None):
    path = preview_path(repo, task, preview.get("image", ""))
    name = e(str(preview.get("name") or path.stem))
    note = e(str(preview.get("note") or ""))
    caption = f'<figcaption><strong>{name}</strong>{" · " + note if note else ""}</figcaption>'
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime and path.is_file():
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        body = f'<img src="data:{mime};base64,{data}" alt="{name}">'
    else:
        missing.append(str(path))
        body = f'<div class="empty-state">No se encontró la imagen: {e(str(path))}</div>'
    return f"<figure>{body}{caption}</figure>"


def previews_section(repo, previews, missing, task=None):
    """Imágenes incrustadas en base64: el reporte sigue siendo un solo archivo que se puede compartir."""
    if not previews:
        return ""
    figures = "".join(preview_figure(repo, p, missing, task) for p in previews)
    return section("previews", "🖼️ Previews de UI", f'<div class="previews">{figures}</div>', len(previews))


def section(anchor, title, content, count=None, extra=""):
    badge = f' <span class="count">{count}</span>' if count is not None else ""
    return f'<section id="{anchor}"{extra}><h2>{title}{badge}</h2>{content}</section>'


def version_cell(repo):
    """La versión que fija la app frente a la del fuente, con un aviso si no coinciden."""
    parts = []
    if repo["pinned"]:
        parts.append(f'fijada <code>{e(repo["pinned"])}</code>')
    if repo["source"]:
        parts.append(f'fuente <code>{e(repo["source"])}</code>')
    flag = " " + chip("⚠️ no coinciden", "c-warn") if repo["version_mismatch"] else ""
    return " · ".join(parts) + flag if parts else "—"


def branch_html(repo):
    text = f'<code>{e(repo["branch"])}</code>'
    before = repo.get("branch_before")
    if repo.get("photo") is None or "branch" not in (repo.get("photo") or {}):
        return text
    if before == repo["branch"]:
        return text + ' <span class="muted">· la misma del inicio</span>'
    start = f"<code>{e(before)}</code>" if before else "otro commit (detached)"
    return text + f' <span class="muted">· al empezar: {start}</span>'


def counts_of(files):
    return {k: sum(1 for f in files if f["status"] == k) for k in "AMD"}


def unit_anchor(repo):
    return repo.get("anchor") or "unidad-" + slug(repo["name"])


def assign_anchors(repos):
    """Un ancla por unidad, sin repetir: core-lib y core_lib dan unidad-core-lib y unidad-core-lib-2."""
    taken = set()
    for repo in repos:
        base = "unidad-" + slug(repo["name"])
        anchor, number = base, 2
        while anchor in taken:
            anchor, number = "%s-%d" % (base, number), number + 1
        repo["anchor"] = anchor
        taken.add(anchor)


def units_table(repos, by_repo, steps_by_repo):
    versions = any(repo["pinned"] or repo["source"] for repo in repos)
    head = ("<tr><th>Unidad</th><th>Rama</th><th>Base</th>" + ("<th>Versión</th>" if versions else "") +
            "<th>Nuevos</th><th>Modificados</th><th>Eliminados</th><th>DoD</th></tr>")
    rows = []
    for repo in repos:
        counts = counts_of(by_repo[repo["real"]])
        tag = f'<span class="repo-tag">{e(repo["name"])}</span>'
        name = f'<a href="#{unit_anchor(repo)}">{tag}</a>' if by_repo[repo["real"]] else tag  # sin archivos, sin sección
        rows.append(f"<tr><td>{name}</td>"
                    f'<td><code>{e(repo["branch"])}</code></td><td>{base_html(repo)}</td>' +
                    (f"<td>{version_cell(repo)}</td>" if versions else "") +
                    "".join(f'<td class="num">{counts[k]}</td>' for k in "AMD") +
                    f"<td>{dod_chip(steps_by_repo.get(repo['real'], []))}</td></tr>")
    return f'<div class="table-wrap"><table class="units"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def unit_section(repo, files, steps, group_defs, next_id):
    counts = counts_of(files)
    role = "principal" if repo["main"] else "vecino"
    where = ("la raíz del proyecto" if repo["main"] else
             f'<code>{e(display_path(repo["root"], repo["main_root"]))}</code>')
    models = (" · unidades del modelo: " + ", ".join(f"<code>{e(u)}</code>" for u in repo["units"])
              if repo["units"] else "")
    fields = [("Rama", branch_html(repo)), ("Base", base_html(repo))]
    if repo["pinned"] or repo["source"]:
        fields.append(("Versión", version_cell(repo)))
    fields.append(("Cambios", f'{plural(counts["A"], "nuevo")} · {plural(counts["M"], "modificado")} · '
                              f'{plural(counts["D"], "eliminado")}'))
    fields.append(("DoD de la unidad", dod_chip(steps)))
    content = (f'<p class="sub">{where}{models}</p><div class="fields">' +
               "".join(f'<div class="field"><div class="k">{k}</div><div class="x">{v}</div></div>' for k, v in fields) +
               "</div>")
    if repo["version_mismatch"]:
        content += (f'<div class="note warn"><b>⚠️ El fuente no coincide con la versión que fija la app</b>'
                    f'El fuente ({e(repo["source"])}) y la versión fijada ({e(repo["pinned"])}) no coinciden: lo '
                    "probado en fuente puede no compilar o comportarse distinto con lo publicado. Revísalo antes de "
                    "publicar.</div>")
    if steps:
        content += "<h3>✅ DoD de la unidad</h3>" + dod_table(steps)
    for status, icon, title in (("A", "🆕", "Archivos nuevos"), ("M", "✏️", "Archivos modificados"),
                                ("D", "🗑️", "Archivos eliminados")):
        entries, grouped = [], {}
        for f in files:
            if f["status"] != status:
                continue
            if f["group"] is None:
                entries.append(file_entry(next_id(), f, f["info"] or {}))
            else:
                grouped.setdefault(id(f["group"]), (f["group"], []))[1].append(f["path"])
        entries += [group_entry(next_id(), group, status, paths) for group, paths in grouped.values()]
        if entries:
            content += f'<h3>{icon} {title} <span class="count">{counts[status]}</span></h3>' + "".join(entries)
    title = f'<span class="repo-tag">{e(repo["name"])}</span> {chip(role, "c-same")}'
    return section(unit_anchor(repo), title, content, extra=' class="unit"')


def unattributed_section(items):
    if not items:
        return ""
    by_repo = {}
    for item in items:
        by_repo.setdefault(item["repo"], []).append(item)
    blocks = []
    for name, entries in by_repo.items():
        rows = "".join(f'<li><code class="file-path">{e(item["path"])}</code> <span class="muted">· '
                       f'{e(item["reason"])}</span></li>' for item in entries[:LIST_LIMIT])
        more = (f'<li class="muted">y {len(entries) - LIST_LIMIT} más</li>' if len(entries) > LIST_LIMIT else "")
        blocks.append(f'<h3><span class="repo-tag">{e(name)}</span> <span class="count">{len(entries)}</span></h3>'
                      f'<ul class="plain-list">{rows}{more}</ul>')
    intro = ('<p class="sub">Ya estaban antes de la tarea, o están en repos que no se sabe si son de ella: no entran en '
             "los conteos ni se proponen para commit con la tarea.</p>")
    return (f'<section id="no-atribuidos"><details class="block"><summary><h2>🧾 Cambios no atribuidos '
            f'<span class="count">{len(items)}</span></h2></summary>{intro}{"".join(blocks)}</details></section>')


def temporary_section(items):
    """Cambios de configuración que la tarea necesitó (por ejemplo, usar el código local de una dependencia):
    no cuentan como cambios, no se commitean y dicen cómo revertirlos."""
    if not items:
        return ""
    rows = []
    for item in items:
        why = f'<div>{e(str(item["why"]))}</div>' if item.get("why") else ""
        revert = (f'<div class="temp-revert">Cómo revertirlo: <code>{e(str(item["revert"]))}</code></div>'
                  if item.get("revert") else "")
        rows.append(f'<div class="temp-item"><div class="file-path">{e(str(item["path"]))}</div>{why}{revert}</div>')
    intro = ('<p class="sub">No son parte de la tarea: no se cuentan ni se commitean. Los que la tarea hizo dicen cómo '
             "revertirlos.</p>")
    return section("temporales", "🔧 Cambios temporales", intro + "".join(rows), len(items))


def root_cause_section(meta):
    text = meta.get("root_cause")
    return section("causa", "🎯 Causa raíz", f'<div class="note-block">{e(text)}</div>') if text else ""


def impact_section(items):
    if not items:
        return ""
    cards = "".join(f'<div class="kpi"><div class="stat-label">{e(item["label"])}</div>'
                    f'<div class="impact-value">{e(item.get("value", ""))}</div></div>' for item in items)
    return section("impacto", "📊 Impacto", f'<div class="impact-grid">{cards}</div>', len(items))


def diagrams_section(items):
    """El código Mermaid va escapado en <pre class="mermaid">: sin conexión se lee como texto."""
    if not items:
        return ""
    figures = []
    for item in items:
        title = f'<figcaption class="diagram-title">{e(item["title"])}</figcaption>' if item.get("title") else ""
        desc = f'<p class="diagram-desc">{e(item["description"])}</p>' if item.get("description") else ""
        figures.append(f'<figure class="diagram">{title}<div class="diagram-body"><pre class="mermaid">'
                       f'{e(item["mermaid"])}</pre></div>{desc}</figure>')
    return section("diagramas", "🧭 Diagramas", "".join(figures), len(items))


def mermaid_scripts(items):
    """Cada diagrama se dibuja dos veces, claro y oscuro: el tema elige cuál se ve y al imprimir sale el claro."""
    if not items:
        return ""
    return (f'<script src="{MERMAID_URL}" integrity="{MERMAID_SRI}" crossorigin="anonymous"></script>\n'
            "<script>\n"
            "(async function () {\n"
            "  if (!window.mermaid) return;\n"
            "  var blocks = document.querySelectorAll('pre.mermaid');\n"
            "  for (var i = 0; i < blocks.length; i++) {\n"
            "    var block = blocks[i], code = block.textContent, boxes = [];\n"
            "    for (var theme of ['default', 'dark']) {\n"
            "      var id = 'hb-diagrama-' + i + '-' + theme;\n"
            "      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: theme });\n"
            "      try {\n"
            "        var out = await mermaid.render(id, code);\n"
            "        var box = document.createElement('div');\n"
            "        box.className = 'diagram-svg ' + (theme === 'dark' ? 'diagram-dark' : 'diagram-light');\n"
            "        box.innerHTML = out.svg;\n"
            "        block.parentNode.insertBefore(box, block);\n"
            "        boxes.push(box);\n"
            "      } catch (err) {\n"
            "        ['d' + id, id].forEach(function (left) { var node = document.getElementById(left); "
            "if (node) node.remove(); });\n"
            "      }\n"
            "    }\n"
            "    if (boxes.length === 2) block.classList.add('rendered');\n"
            "    else boxes.forEach(function (box) { box.remove(); });\n"
            "  }\n"
            "})();\n"
            "</script>")


def skill_version():
    try:
        text = (HERE.parent / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    found = re.search(r'^\s+version:\s*"?([^"\s]+)"?\s*$', text, re.M)
    return found.group(1) if found else ""


def template_parts():
    """Los bloques de la plantilla que empiezan una línea: una mención en un comentario no cuenta."""
    template = TEMPLATE.read_text(encoding="utf-8")
    early = re.search(r'^[ \t]*(<script id="theme-early">.*?</script>)', template, re.S | re.M).group(1)
    style = re.search(r"^[ \t]*(<style>.*?</style>)", template, re.S | re.M).group(1)
    script = re.search(r'^[ \t]*(<script id="behavior">.*?</script>)', template, re.S | re.M).group(1)
    return early, style, script


def summary_section(meta, cov, shown_repos, by_repo, steps_by_repo, all_files, dod, migrations, empty_repos):
    counts = counts_of(all_files)
    dod_value, dod_color = dod_stat(dod)
    kpis = [("Archivos nuevos", counts["A"], "green"), ("Archivos modificados", counts["M"], "blue"),
            ("Archivos eliminados", counts["D"], "red"), ("Unidades", len(shown_repos), ""),
            ("DoD", dod_value, dod_color)]
    content = '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="stat-value {color}">{e(str(value))}</div><div class="stat-label">{label}</div>'
        "</div>" for label, value, color in kpis) + "</div>"
    if meta.get("branch_note"):
        content += f'<div class="note"><b>🌿 Rama de trabajo</b>{e(meta["branch_note"])}</div>'
    warnings = []
    if not cov.photo:
        warnings.append("La tarea no tiene foto inicial (empezó antes de hb-implement 1.7.0, o sin "
                        "<code>report.py --folder</code> al empezar): entran el repo principal y <code>repos</code> del "
                        "meta." + (" Las unidades del modelo con cambios sin commit que no están ahí salen en «Cambios "
                                   "no atribuidos»: " + ", ".join(f"<code>{e(p)}</code>"
                                                                  for p in cov.dirty_units_without_photo)
                                   if cov.dirty_units_without_photo else ""))
    if migrations:
        items = "".join(f"<li><code>{e(migration_text(*m))}</code></li>" for m in migrations)
        warnings.append("<b>⚠️ Posible migración de lenguaje que nadie pidió</b>Un archivo de código se borró o se "
                        "vació y aparece otro con el mismo nombre en otro lenguaje. Confirma que el cambio de lenguaje "
                        f"se pidió:<ul>{items}</ul>")
    mixed = [f["key"] for f in all_files if {MIXED_WARNING, MIXED_COMMITTED_WARNING} & set(f["warnings"])]
    if mixed:
        warnings.append("<b>⚠️ Archivos que ya tenían cambios antes de la tarea</b>Su diff mezcla esos cambios con los "
                        "de la tarea: " + ", ".join(f"<code>{e(key)}</code>" for key in mixed))
    if cov.skipped:
        warnings.append("<b>⚠️ Repos de la tarea que quedaron fuera del reporte</b>" + "; ".join(
            f'<code>{e(item["name"])}</code>: {e(item["reason"])}' for item in cov.skipped))
    for repo in cov.repos + cov.unchanged:  # también sin archivos de la tarea: lo probado puede no ser lo publicado
        if repo.get("version_mismatch"):
            warnings.append(f'<b>⚠️ {e(repo["name"])}: el fuente no coincide con la versión que fija la app</b>El '
                            f'fuente ({e(repo["source"])}) y la versión fijada ({e(repo["pinned"])}) no coinciden: lo '
                            "probado en fuente puede no compilar o comportarse distinto con lo publicado.")
    content += "".join(f'<div class="note warn">{text}</div>' for text in warnings)
    content += "<h3>🧩 Unidades</h3>" + units_table(cov.repos, by_repo, steps_by_repo)
    if empty_repos:
        content += ('<p class="sub" style="margin-top:8px">Sin archivos de la tarea (sus cambios son temporales o ya '
                    "estaban antes): " + ", ".join(f'<span class="repo-tag">{e(r["name"])}</span>' for r in empty_repos)
                    + "</p>")
    if cov.unchanged:
        content += ('<p class="sub" style="margin-top:8px">Sin cambios desde la foto inicial: ' +
                    ", ".join(f'<span class="repo-tag">{e(r["name"])}</span>' for r in cov.unchanged) + "</p>")
    return section("resumen", "📋 Resumen", content)


def header_html(meta, project, date):
    kind = meta.get("type") or "feature"
    chips = [f'<span class="hchip">{e(TYPES.get(kind, TYPES["feature"]))}</span>']
    if meta.get("severity"):
        chips.append(f'<span class="hchip sev-{meta["severity"]}">{SEVERITY_LABELS[meta["severity"]]}</span>')
    if meta.get("ticket"):
        chips.append(f'<span class="hchip">🎫 {e(meta["ticket"])}</span>')
    if meta.get("scope"):
        chips.append(f'<span class="hchip"><code>{e(meta["scope"])}</code></span>')
    lead = f'<p class="lead">{e(meta["description"])}</p>' if meta.get("description") else ""
    return (f'<header><div class="inner"><button class="theme-btn" id="theme-btn" type="button">Tema</button>'
            f'<p class="kicker">{e(project)} · Reporte de implementación · {e(date)}</p>'
            f'<h1>{e(meta.get("title") or "Reporte")}</h1>{lead}<div class="badges">{"".join(chips)}</div></div></header>')


def toc_html(entries):
    links = "".join(f'<a href="#{anchor}">{e(label)}</a>' for anchor, label in entries)
    return f'<nav class="toc" aria-label="Contenido">{links}</nav>'


# ── Main ─────────────────────────────────────────────────────────────────────
class EmptyReport(RuntimeError):
    """No hay archivos de la tarea: el reporte no se escribe y el mensaje dice por qué y qué hacer."""


def meta_type(path):
    """El "type" de un meta que ya existe, o None."""
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    kind = meta.get("type") if isinstance(meta, dict) else None
    return kind if isinstance(kind, str) and kind.strip() else None


def unit_command(repo, args, task_slug, path):
    """El comando para registrar una unidad, con la ruta real del script, listo para copiar."""
    shown_path = path if path.startswith("<") else shlex.quote(path)
    command = f"python3 -I {home(os.path.abspath(__file__))} --unit {shown_path} --folder {shlex.quote(task_slug)}"
    if args.out:
        command += f" --out {shlex.quote(args.out)}"
    if os.path.realpath(os.getcwd()) != os.path.realpath(str(repo)):
        command += f" --repo {home(repo)}"
    return command


def meta_started(path):
    """Si el meta dice que la tarea ya empezó: existe y trae algo más que "repos" (el meta que crea --unit antes de
    --folder no cuenta)."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not (isinstance(data, dict) and set(data) <= {"repos"})


def print_folder(repo, layout, args):
    task_slug = safe_slug(args.folder)
    date = args.date or datetime.date.today().isoformat()
    task = layout.task(task_slug, date)
    folder = real(task.folder)
    started = folder.is_dir() and (any(real(task.file(kind)).exists() for kind in ("report", "bitacora"))
                                   or meta_started(real(task.file("meta"))))
    folder.mkdir(parents=True, exist_ok=True)
    meta_file = task.file("meta")
    warnings = [ensure_ignored(repo, layout.root, meta_file),
                update_index(layout, task, meta_type(real(meta_file)), "en curso")]
    photo_line, notes = None, []
    if task.flat:
        notes.append('ℹ️  La tarea está en el formato plano de antes: sin foto inicial, el reporte usa "repos" del meta.')
    elif real(task.snapshot).is_file():
        photo_line = "(ya existía: se conserva la del inicio de la tarea)"
    elif started:
        notes.append("ℹ️  La tarea empezó sin foto inicial (antes de hb-implement 1.7.0): no la tomo ahora, porque "
                     "contaría sus propios cambios como previos. El reporte usa el repo principal y \"repos\" del "
                     "meta: registra cada unidad que cambie con --unit.")
    else:
        snapshot = take_snapshot(repo, layout, structure_units(repo))
        with task_lock(folder):
            write_json(real(task.snapshot), snapshot, ascii_only=True)
        photo_line = "(%s)" % photo_summary(snapshot)
        if snapshot["unreadable"]:
            listing = ", ".join("%s (%s)" % (item["path"], item["reason"]) for item in snapshot["unreadable"])
            notes.append(f"ℹ️  No pude leer {plural(len(snapshot['unreadable']), 'carpeta')}: {listing}. Quedan fuera "
                         "de la foto; si una es de la tarea, dale al agente acceso y vuelve a pedir la carpeta.")
        failed = [entry for entry in snapshot["repos"] if "error" in entry]
        if failed:
            notes.append("ℹ️  No pude leer el estado de " + ", ".join(
                "%s (%s)" % (entry["path"], entry["error"]) for entry in failed) + ".")
        dirty = dirty_at_start(repo, snapshot)
        if dirty:
            notes.append("ℹ️  La foto inicial ya encuentra cambios sin commit en " + "; ".join(dirty) + ". Quedan "
                         "como previos a la tarea: si no cambian, van a «Cambios no atribuidos». Si no son de esta "
                         "tarea, avísale al usuario antes de empezar.")
    print(f"📁 Carpeta de la tarea: {shown(task.folder, repo)}" + (" (la tarea ya existía: sigue ahí)" if task.reused else ""))
    print(f"   meta: {shown(meta_file, repo)}")
    print(f"   bitácora, si hace falta: {shown(task.file('bitacora'), repo)}")
    print(f"   previews: {shown(task.previews, repo)}")
    print(f"   índice: {shown(layout.index, repo)}")
    if photo_line:
        print(f"   foto inicial: {shown(task.snapshot, repo)} {photo_line}")
    for warning in warnings + notes:
        if warning:
            print(warning, file=sys.stderr)


def dirty_at_start(repo, snapshot):
    """Los repos de la tarea (el principal y las unidades) que ya tienen cambios sin commit en la foto, sin contar la
    configuración local modificada a propósito: ["app-shell: 2 archivos (a.txt, b.txt)"]."""
    local = {os.path.realpath(os.path.join(str(repo), path)) for path in local_config(repo)}
    keys = [entry["real"] for entry in snapshot["repos"] if isinstance(entry.get("real"), str)]
    found = []
    for entry in snapshot["repos"]:
        if entry.get("role") not in ("main", "unit"):
            continue
        inner = nested_paths(entry["real"], keys)  # una unidad anidada tiene su propia línea
        paths = [path for path in sorted(entry.get("dirty") or {})
                 if os.path.realpath(os.path.join(entry["real"], path)) not in local and path not in inner]
        if paths:
            name = os.path.basename(entry["real"])
            shown_paths = ", ".join(paths[:5]) + (", …" if len(paths) > 5 else "")
            found.append(f"{name}: {plural(len(paths), 'archivo')} ({shown_paths})")
    return found


def dod_state(steps):
    value = dod_stat(steps)[0]
    return "sin DoD" if value == "—" else "DoD " + value


def empty_message(cov, temporary_count, previous_count, repo, args, task_slug):
    causes, steps = [], []
    if cov.skipped:
        causes.append("Quedaron fuera del reporte: " + "; ".join(f'{item["name"]} ({item["reason"]})'
                                                                for item in cov.skipped) + ".")
        steps.append("Arregla lo que dejó fuera a esos repos (el acceso a su carpeta, o su rama principal o su base en "
                     "\"repos\") y vuelve a generar el reporte.")
    if cov.others:
        causes.append("Los cambios están en repos que no son unidades del modelo ni están registrados: " +
                      ", ".join(f'{other["path"]} ({other["detail"]})' for other in cov.others) + ".")
        steps.append("Pregúntale al usuario si alguno es de la tarea; si lo es, regístralo y vuelve a generar el "
                     "reporte: " + "; ".join(unit_command(repo, args, task_slug, other["path"])
                                             for other in cov.others[:5]))
    if cov.dirty_without_photo:
        causes.append("La tarea no tiene foto inicial y hay repos con cambios sin commit que no están en \"repos\" del "
                      "meta: " + ", ".join(cov.dirty_without_photo) + ".")
        steps.append("Si alguno es de la tarea, regístralo y vuelve a generar el reporte: " +
                     "; ".join(unit_command(repo, args, task_slug, path) for path in cov.dirty_without_photo[:5]))
    if previous_count:
        causes.append(("El cambio que hay ya estaba antes de la foto inicial (sin commit, o commiteado en la rama "
                       "antes de empezar)" if previous_count == 1 else
                       f"Los {previous_count} cambios que hay ya estaban antes de la foto inicial (sin commit, o "
                       "commiteados en la rama antes de empezar)") + ": la tarea no cambió nada después.")
        steps.append("Si la carpeta (y con ella la foto) se pidió después de empezar a cambiar, esos cambios sí son de "
                     "la tarea: vuelve a generar con --ignore-snapshot (entran el principal y \"repos\" del meta; "
                     "registra con --unit cada repo vecino que cambió).")
    if temporary_count and not causes:
        causes.append(f"Todo lo que cambió es temporal o configuración local ({plural(temporary_count, 'archivo')}).")
    if not cov.skipped and not causes and cov.photo and not cov.repos:
        causes.append("Ningún repo de la tarea cambió después de la foto inicial (" +
                      ", ".join(r["name"] for r in cov.unchanged) + ").")
        steps.append("Si la tarea cambió un repo que no es unidad del modelo, regístralo y vuelve a generar el reporte: "
                     + unit_command(repo, args, task_slug, "<ruta>"))
    if not causes or (cov.skipped and len(causes) == 1 and cov.repos):
        bases = "; ".join(f'{r["name"]}: {base_text(r)}' for r in cov.repos if "base_label" in r)
        causes.append("Ningún repo de la tarea tiene cambios contra su base" + (f" ({bases})" if bases else "") + ".")
        steps.append("Si la tarea ya está commiteada en la rama principal o en otra rama, pasa la base con --base (o "
                      "\"base\" en \"repos\"). Si cambió un repo vecino, regístralo y vuelve a generar el reporte: " +
                      unit_command(repo, args, task_slug, "<ruta>"))
    if not steps:
        steps.append("Si la tarea sí cambió archivos, revisa que estén en un repo de la tarea y vuelve a generar el "
                     "reporte; si no cambió nada, no hace falta reporte.")
    unchanged = [r["name"] for r in cov.unchanged]
    lines = ["No genero el reporte: no encontré ningún archivo de la tarea, así que no escribí nada.",
             "  Causa probable:"] + [f"    - {text}" for text in causes] + ["  Siguiente paso:"] + \
        [f"    - {text}" for text in steps]
    if unchanged:
        lines.append("  Sin cambios desde la foto inicial: " + ", ".join(unchanged) + ".")
    return "\n".join(lines)


class Collected:
    """Qué es de la tarea, repo por repo, sin escribir nada: lo que usan el reporte y --attribution."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def task_and_snapshot(repo, layout, args, meta, meta_path, notes, verb="Genero"):
    """La tarea del meta y su foto inicial (None sin foto o con --ignore-snapshot)."""
    date = meta.get("date") or datetime.date.today().isoformat()
    task_slug = safe_slug(meta["slug"]) if meta.get("slug") else slug(meta.get("title", "reporte"))
    task = layout.task(task_slug, date, meta_path)
    snapshot = None if args.ignore_snapshot else load_snapshot(task, notes)
    if args.ignore_snapshot:
        notes.append("ℹ️  %s sin la foto inicial (--ignore-snapshot): entran el repo principal y \"repos\" del meta."
                     % verb)
    return task, snapshot


def collect(repo, layout, args, meta, snapshot):
    """Los archivos de la tarea, los no atribuidos y lo excluido (temporales y configuración local), como los decide el
    reporte. Solo lee: ni el contenido de los archivos ni nada en disco."""
    cov = coverage(repo, layout, args, meta, snapshot, structure_units(repo))
    infos, group_defs = meta["files"], meta["groups"]
    temporary = list(meta.get("temporary", []))
    temporary_keys = {str(item["path"]) for item in temporary}
    local = {os.path.realpath(os.path.join(str(repo), path)) for path in local_config(repo)}
    files, temporary_found, temporary_count, previous_count = [], set(), 0, 0
    main_root = repo

    def keys_for(r, path):
        if r["main"]:
            return [path] + [f"{alias}:{path}" for alias in sorted(r["aliases"])]
        return [f'{r["name"]}:{path}'] + [f"{alias}:{path}" for alias in sorted(r["aliases"] - {r["name"]})]

    def temporary_or_local(r, path, key, aliases):
        """True si el archivo es un cambio temporal del meta o configuración local (y lo anota)."""
        nonlocal temporary_count
        if any(alias in temporary_keys for alias in aliases):
            temporary_found.update(aliases)
            temporary_count += 1
            return True
        if os.path.realpath(os.path.join(str(r["root"]), path)) in local:
            temporary.append({"path": key, "why": LOCAL_CONFIG_WHY})
            temporary_count += 1
            return True
        return False

    readable = []
    for r in cov.repos:
        r["main_root"] = main_root
        explicit_base = bool(r["base"])
        try:
            finish_repo(r)
            changed = changed_files(r, r["base"], layout)
        except RuntimeError as err:
            if r["main"] or explicit_base:  # el principal o una base pedida: sin ellos el reporte no sirve
                raise RuntimeError(f'{err}' if str(err).startswith(r["name"] + ":") else f'{r["name"]}: {err}')
            # una unidad que git no lee no corta el reporte de los demás: queda fuera con su causa
            text = str(err)
            base_problem = "no pude comparar contra" in text
            reason = ("no pude compararlo contra su base (%s)" % r.get("base") if base_problem
                      else "git no lo pudo leer (%s)" % (text.splitlines()[-1] if text else "sin detalle"))
            cov.skipped.append({"name": r["name"], "reason": reason})
            cov.notes.append(f'⚠️  {r["name"]} ({display_path(r["root"], repo)}) queda fuera del reporte: {reason}. ' +
                             ('Pasa su rama principal o su base ("main_branch" o "base" en "repos") y vuelve a generar.'
                              if base_problem else "Si la tarea lo cambió, dale al agente acceso a esa carpeta y vuelve "
                              "a generar."))
            continue
        readable.append(r)
        nested = nested_units(r, cov.nested)
        pending = []
        for f in changed:
            if f["path"] in nested and nested[f["path"]]:
                continue  # solo cambió dentro del submódulo, que tiene su propia sección
            f["repo"] = r
            f["key"] = f["path"] if r["main"] else f'{r["name"]}:{f["path"]}'
            if not temporary_or_local(r, f["path"], f["key"], keys_for(r, f["path"])):
                pending.append(f)
        verdicts = attribute(r, pending)
        for f in pending:
            verdict, reason = verdicts[id(f)]
            if verdict == "previous":
                previous_count += 1
                cov.unattributed.append({"repo": r["name"], "path": f["path"], "reason": reason})
                if any(explained(infos.get(alias)) for alias in keys_for(r, f["path"])):
                    cov.claimed.append(f["key"])
                continue
            f["warnings"] = {"mixed": [MIXED_WARNING], "mixed-committed": [MIXED_COMMITTED_WARNING]}.get(verdict, [])
            f["info"] = next((infos[alias] for alias in keys_for(r, f["path"]) if alias in infos), None)
            # Un archivo con su propia entrada en "files" se muestra aparte, aunque un grupo lo cubra.
            f["group"] = None if f["info"] is not None else group_for(f["key"], group_defs)
            files.append(f)
    cov.repos = readable
    for r in cov.unchanged:  # lo que ya estaba sucio y no cambió: no es de la tarea
        r["main_root"] = main_root
        if r["pinned"]:  # en fuente sin cambios: igual se avisa si no es la versión que fija la app
            try:
                resolve_base(r)
                check_version(r)
            except RuntimeError:
                pass
        inner = nested_paths(r["real"], [other["real"] for other in cov.nested])  # tienen su propia sección
        for path in sorted((r.get("state") or {}).get("dirty") or {}):
            if path in inner:
                continue
            key = path if r["main"] else f'{r["name"]}:{path}'
            if not temporary_or_local(r, path, key, keys_for(r, path)):
                previous_count += 1
                cov.unattributed.append({"repo": r["name"], "path": path,
                                         "reason": "sin commit desde antes de la tarea; el repo no cambió después"})
                if any(explained(infos.get(alias)) for alias in keys_for(r, path)):
                    cov.claimed.append(key)

    return Collected(cov=cov, files=files, temporary=temporary, temporary_keys=temporary_keys,
                     temporary_found=temporary_found, temporary_count=temporary_count, previous_count=previous_count,
                     infos=infos, group_defs=group_defs)


def generate(repo, layout, args):
    meta_path = lexical(args.meta)
    notes = []
    meta = clean_meta(json.loads(meta_path.read_text(encoding="utf-8")), notes)
    date = meta.get("date") or datetime.date.today().isoformat()
    task, snapshot = task_and_snapshot(repo, layout, args, meta, meta_path, notes)
    out = task.file("report")
    found = collect(repo, layout, args, meta, snapshot)
    cov, files, temporary = found.cov, found.files, found.temporary
    temporary_keys, temporary_found, group_defs = found.temporary_keys, found.temporary_found, found.group_defs
    early, style, script = template_parts()
    for f in files:
        r = f["repo"]
        f["before"] = decode(read_before(r["root"], r["base"], f["old"])) if f["status"] != "A" else None
        f["after"] = decode(read_after(r["root"], f["path"])) if f["status"] != "D" else None

    if not files:
        raise EmptyReport(empty_message(cov, found.temporary_count, found.previous_count, repo, args, task.slug))

    migrations = language_migrations(files)
    for f, other, how in migrations:
        text = "Posible migración de lenguaje que nadie pidió: " + migration_text(f, other, how) + \
            ". Confirma que el cambio de lenguaje se pidió."
        for target in {id(f): f, id(other): other}.values():
            if text not in target["warnings"]:
                target["warnings"].append(text)

    assign_anchors(cov.repos)
    by_repo = {r["real"]: [f for f in files if f["repo"] is r] for r in cov.repos}
    shown_repos = [r for r in cov.repos if by_repo[r["real"]]]
    empty_repos = [r for r in cov.repos if not by_repo[r["real"]]]
    dod = meta["dod"]
    steps_by_repo, project_steps = {}, []
    for step in dod:
        owner = dod_owner(step, shown_repos)
        if owner is None:
            project_steps.append(step)
        else:
            steps_by_repo.setdefault(owner["real"], []).append(step)
    project = meta.get("project") or repo.name
    missing_previews = []
    previews = previews_section(repo, meta["previews"], missing_previews, task)
    diagrams = meta["diagrams"]
    counter = iter(range(1, 1 << 30))

    def next_id():
        return "f%d" % next(counter)

    units_html = "".join(unit_section(r, by_repo[r["real"]], steps_by_repo.get(r["real"], []), group_defs, next_id)
                         for r in shown_repos)
    project_dod = ""
    if project_steps:
        sub = ('<p class="sub">Los pasos del proyecto; los de cada unidad están en su sección.</p>'
               if steps_by_repo else "")
        project_dod = section("dod", "✅ Definition of Done", sub + dod_table(project_steps))
    toc = [("resumen", "Resumen")]
    toc += [(anchor, label) for anchor, label, present in (
        ("causa", "Causa raíz", meta.get("root_cause")), ("impacto", "Impacto", meta["impact"]),
        ("diagramas", "Diagramas", diagrams), ("previews", "Previews", previews)) if present]
    toc += [(unit_anchor(r), r["name"]) for r in shown_repos]
    toc += [(anchor, label) for anchor, label, present in (
        ("no-atribuidos", "No atribuidos", cov.unattributed), ("temporales", "Temporales", temporary),
        ("dod", "DoD", project_dod)) if present]
    version = skill_version()
    page = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(project)} · {e(meta.get("title") or "Reporte")}</title>
{early}
{style}
</head><body>
{header_html(meta, project, date)}
<main>
{toc_html(toc)}
{summary_section(meta, cov, shown_repos, by_repo, steps_by_repo, files, dod, migrations, empty_repos)}
{root_cause_section(meta)}
{impact_section(meta["impact"])}
{diagrams_section(diagrams)}
{previews}
{units_html}
{unattributed_section(cov.unattributed)}
{temporary_section(temporary)}
{project_dod}
</main>
<footer><div><strong>{e(project)}</strong> · Generado el {e(date)}</div>
<div>Generado con <strong>hb-implement{" " + e(version) if version else ""}</strong> · No hacer commit sin revisión manual</div></footer>
{script}
{mermaid_scripts(diagrams)}
</body></html>
"""
    write_text(real(out), page)  # entero o nada: un error no deja el reporte anterior vacío
    print(f"📄 Reporte generado: {shown(out, repo)}")
    print("🧩 Unidades en el reporte: " + ", ".join(f'{r["name"]} ({plural(len(by_repo[r["real"]]), "archivo")})'
                                                   for r in shown_repos))
    if task.reused:
        print(f"ℹ️  Ya había una carpeta para «{task.slug}»: la tarea sigue en {shown(task.folder, repo)}"
              + (" (formato plano de antes)" if task.flat else ""))
    for r in cov.repos:
        print(f"🔀 Base de {r['name']}: {base_text(r)}")
    warnings = [ensure_ignored(repo, layout.root, out), update_index(layout, task, meta.get("type") or "feature",
                                                                     dod_state(dod))]
    print(f"🗂️  Índice: {shown(layout.index, repo)}")
    report_notes(cov, files, meta, notes, warnings, missing_previews, group_defs, temporary_keys, temporary_found,
                 migrations, repo, args, task, meta_path, layout)


ATTRIBUTION_NOTE = {
    "mixed": "ya tenía cambios sin commit al empezar la tarea: el diff contra la base mezcla esos cambios con los de la "
             "tarea, y la foto no guarda el contenido previo (solo su hash)",
    "mixed-committed": "ya tenía cambios commiteados en la rama antes de la tarea: lo de la tarea es el diff desde "
                       "task_diff_from (el HEAD de la foto)",
}
ATTRIBUTION_NOT_ISOLATED = ("ya tenía cambios commiteados en la rama antes de la tarea, y la rama se rebasó o recibió un "
                            "merge después de la foto: no se puede aislar el diff de la tarea (trátalo como mixed)")


def attribution(repo, layout, args):
    """--attribution: qué es de la tarea, repo por repo, en JSON, con la misma lógica del reporte. No escribe archivos
    (git solo refresca la caché de stat de .git/index, como cualquier git status). El meta puede no existir todavía si
    su carpeta ya tiene la foto. La salida es ASCII: un nombre que no es UTF-8 sale con escapes \\udcXX."""
    meta_path = lexical(args.meta)
    notes = []
    own = meta_path.parent
    if real(meta_path).is_file():
        meta = clean_meta(json.loads(real(meta_path).read_text(encoding="utf-8")), notes)
    elif real(own / SNAPSHOT).is_file():
        meta = clean_meta({}, notes)  # la tarea empezó (tiene foto) y todavía no escribió su meta
    else:
        raise RuntimeError(f"no encuentro {shown(meta_path, repo)} ni la foto inicial en su carpeta: pasa el meta.json "
                           "de la tarea (report.py --folder <slug> dice su ruta)")
    task, snapshot = task_and_snapshot(repo, layout, args, meta, meta_path, notes, verb="Atribuyo")
    if real(own / SNAPSHOT).is_file() and real(task.folder) != real(own):
        # la carpeta del meta tiene su foto (por ejemplo, con otra carpeta de reportes): manda esa
        named = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", own.name)
        task = Task(own, named.group(1) if named else task.date, named.group(2) if named else task.slug)
        snapshot = None if args.ignore_snapshot else load_snapshot(task, notes)
    found = collect(repo, layout, args, meta, snapshot)
    cov = found.cov
    paths = {r["name"]: display_path(r["root"], repo) for r in cov.repos + cov.unchanged}
    repos = []
    for r in cov.repos:
        photo = r.get("photo") if isinstance(r.get("photo"), dict) and "error" not in r["photo"] else {}
        in_photo = bool(photo)
        isolated = isolated_since(r["root"], photo.get("head"))
        if cov.photo and not in_photo:
            notes.append(f'⚠️  {r["name"]} no estaba en la foto inicial: todo su diff cuenta como de la tarea.')
        files = []
        for f in sorted((f for f in found.files if f["repo"] is r), key=lambda item: item["path"]):
            verdict = "mixed" if MIXED_WARNING in f["warnings"] else (
                "mixed-committed" if MIXED_COMMITTED_WARNING in f["warnings"] else "task")
            entry = {"path": f["path"], "status": f["status"], "old": f["old"] if f["old"] != f["path"] else None,
                     "untracked": bool(f.get("untracked")), "attribution": verdict}
            if verdict == "mixed":
                entry["note"] = ATTRIBUTION_NOTE["mixed"]
            elif verdict == "mixed-committed":
                entry["task_diff_from"] = photo.get("head") if isolated else None
                entry["note"] = ATTRIBUTION_NOTE["mixed-committed"] if isolated else ATTRIBUTION_NOT_ISOLATED
            files.append(entry)
        repos.append({"name": r["name"], "path": display_path(r["root"], repo), "main": bool(r["main"]),
                      "units": list(r["units"]), "branch": r.get("branch"), "branch_before": r.get("branch_before"),
                      "base": r["base"], "base_text": base_text(r), "in_photo": in_photo,
                      "photo_head": photo.get("head"), "files": files})
    claimed = set(cov.claimed)
    if claimed:
        notes.append("⚠️  El meta explica archivos que ya estaban así en la foto inicial (van a «Cambios no "
                     "atribuidos»): " + ", ".join(cov.claimed) + ". Si la foto se tomó después de empezar a cambiar, "
                     "vuelve a correr con --ignore-snapshot.")
    unattributed = []
    for item in cov.unattributed:
        repo_path = paths.get(item["repo"], item["repo"])
        keys = {item["path"], "%s:%s" % (item["repo"], item["path"])}
        unattributed.append({"repo": item["repo"], "repo_path": repo_path, "path": item["path"],
                             "reason": item["reason"], "claimed_by_meta": bool(keys & claimed)})
    others = list(cov.others) + [{"path": where, "detail": "cambios sin commit (sin foto: no se sabe si son de la "
                                                           "tarea)"} for where in cov.dirty_siblings_without_photo]
    empty = None
    if not found.files:
        empty = empty_message(cov, found.temporary_count, found.previous_count, repo, args, task.slug).replace(
            "No genero el reporte: no encontré ningún archivo de la tarea, así que no escribí nada.",
            "No hay ningún archivo de la tarea.")
    data = {
        "task": {"slug": task.slug, "folder": shown(task.folder, repo), "meta": shown(meta_path, repo)},
        "photo": cov.photo,
        "repos": repos,
        "unattributed": unattributed,
        "claimed": list(cov.claimed),
        "excluded": [{"path": str(item.get("path")), "why": item.get("why") or "cambio temporal de la tarea"}
                     for item in found.temporary],
        "unchanged": [r["name"] for r in cov.unchanged],
        "skipped": list(cov.skipped),
        "others": others,
        "notes": [text for text in notes + cov.notes + [w for r in cov.repos + cov.unchanged
                                                         for w in r.get("warnings", [])] if text],
        "empty": empty,
    }
    print(json.dumps(data, ensure_ascii=True, indent=2))


def report_notes(cov, files, meta, notes, warnings, missing_previews, group_defs, temporary_keys, temporary_found,
                 migrations, repo, args, task, meta_path, layout):
    """Los avisos de la salida, después del reporte: primero lo que cambia qué entra, después lo que falta completar."""
    def say(text):
        print(text, file=sys.stderr)
    for text in warnings + cov.notes + notes + [w for r in cov.repos + cov.unchanged for w in r.get("warnings", [])]:
        if text:
            say(text)
    if cov.others:
        say("⚠️  Otros repos cambiaron durante la tarea y no son unidades del modelo ni están registrados (no entran al "
            "reporte):")
        for other in cov.others:
            say(f'   - {other["path"]}: {other["detail"]}')
        say("   Pregúntale al usuario si alguno es de la tarea; si lo es, regístralo y vuelve a generar el reporte: " +
            "; ".join(unit_command(repo, args, task.slug, other["path"]) for other in cov.others[:5]))
    if cov.dirty_units_without_photo:
        say("⚠️  Unidades del modelo con cambios sin commit que no están en \"repos\" del meta (van a «Cambios no "
            "atribuidos»): " + ", ".join(cov.dirty_units_without_photo) + ".")
    if cov.dirty_siblings_without_photo:
        say("⚠️  Repos hermanos con cambios sin commit que no son unidades del modelo (no entran al reporte; solo se "
            "nombran aquí): " + ", ".join(cov.dirty_siblings_without_photo) + ".")
    if cov.dirty_without_photo:
        say("   Si alguno es de la tarea, regístralo y vuelve a generar el reporte: " +
            "; ".join(unit_command(repo, args, task.slug, path) for path in cov.dirty_without_photo[:5]))
    if cov.claimed:
        say("⚠️  El meta explica archivos que ya estaban así en la foto inicial (van a «Cambios no atribuidos»): " +
            ", ".join(cov.claimed) + ". Si la foto se tomó después de empezar a cambiar, vuelve a generar con "
            "--ignore-snapshot.")
    quiet = [r["name"] for r in cov.unchanged if not r["main"]]
    if quiet:
        say("ℹ️  Sin cambios desde la foto inicial (no entran): " + ", ".join(quiet))
    for f, other, how in migrations:
        say(f"⚠️  Posible migración de lenguaje que nadie pidió: {migration_text(f, other, how)} "
            f'({f["repo"]["name"]}). Confirma que se pidió.')
    for path in missing_previews:
        say(f"⚠️  Preview sin imagen: {path}")
    missing = [f["key"] for f in files if not explained(f["info"]) and f["group"] is None]
    if missing:
        say("ℹ️  Archivos sin explicación en meta.json: " + ", ".join(missing))
        if len(missing) > 5:
            say('ℹ️  Si son archivos generados o masivos (goldens, fixtures), explícalos en grupo con "groups".')
    report_fields, per_file = missing_analysis(meta, files)
    if report_fields or per_file:
        parts = ([", ".join(report_fields)] if report_fields else []) + \
            (["risk, pros o cons de " + ", ".join(per_file)] if per_file else [])
        say("ℹ️  Datos de análisis que faltan (complétalos si puedes sostenerlos con lo que viste en el código): " +
            "; ".join(parts))
    for group in group_defs:
        if not any(f["group"] is group for f in files):
            say(f'ℹ️  El grupo "{group.get("match", "")}" no cubre ningún archivo cambiado.')
    for key in sorted(temporary_keys - temporary_found):
        say(f'ℹ️  El cambio temporal "{key}" no aparece entre los cambios de git (si git lo ignora, está bien).')
    if not task.flat and real(task.folder) != real(meta_path.parent):
        say(f"ℹ️  Con una carpeta por tarea, el meta va en {shown(task.file('meta'), repo)} "
            f"(report.py --folder {task.slug} te la da).")
    if task.flat and meta_path.name == "meta.json" and real(meta_path.parent) == real(layout.root):
        say(f"ℹ️  {shown(meta_path, repo)} lo pisa la siguiente tarea: usa un meta por tarea, en la carpeta que da "
            f"report.py --folder <slug> ({shown(layout.root / SUBFOLDER, repo)}/<fecha>-<slug>/meta.json).")


def main():
    with contextlib.suppress(AttributeError, ValueError):  # un nombre que no es UTF-8 no corta la salida
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    task_group = ap.add_mutually_exclusive_group()
    task_group.add_argument("--meta", help="JSON con título, tipo, explicaciones por archivo y DoD")
    task_group.add_argument("--folder", metavar="SLUG",
                            help="crea la carpeta de la tarea y toma la foto inicial, sin generar el reporte")
    ap.add_argument("--unit", metavar="RUTA",
                    help="con --folder: registra una unidad (la ruta de su fuente, relativa a la raíz del repo "
                         "principal, o su identificador de ## Estructura) en \"repos\" del meta y en la foto")
    ap.add_argument("--base", help="ref del repo principal contra la que se compara (manda sobre --main-branch; por "
                                   "defecto, el merge-base de HEAD con la rama principal)")
    ap.add_argument("--main-branch", help="la rama principal del repo principal, la del modelo de AGENTS.md (por "
                                          "defecto, origin/HEAD, origin/main, origin/master, main o master)")
    ap.add_argument("--out", help="carpeta de reportes, relativa al repo; puede usar {fecha} y {slug} "
                                  "(por defecto, la de AGENTS.md o reports)")
    ap.add_argument("--repo", default=".", help="raíz del repositorio principal")
    ap.add_argument("--date", help="con --folder: la fecha AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--ignore-snapshot", action="store_true",
                    help="con --meta: genera sin la foto inicial (solo si se tomó después de empezar a cambiar)")
    ap.add_argument("--attribution", action="store_true",
                    help="con --meta: imprime en JSON qué es de la tarea, repo por repo (la misma lógica del reporte), "
                         "sin escribir nada; lo usa hb-review")
    args = ap.parse_args()
    if args.unit and not args.folder:
        ap.error("--unit va con --folder <slug>: la tarea en la que se registra la unidad")
    if not (args.meta or args.folder):
        ap.error("falta --meta <meta.json> (generar el reporte) o --folder <slug> (la carpeta de la tarea)")
    if args.ignore_snapshot and not args.meta:
        ap.error("--ignore-snapshot va con --meta: es para generar el reporte")
    if args.attribution and not args.meta:
        ap.error("--attribution va con --meta <meta.json>: el de la tarea que se revisa")

    repo = toplevel(args.repo)
    layout = Layout(repo, args.out or agents_out(repo) or DEFAULT_OUT)
    check_worktree(repo, layout, with_agents=not args.out)
    if args.unit:
        register_unit(repo, layout, args)
    elif args.folder:
        print_folder(repo, layout, args)
    elif args.attribution:
        attribution(repo, layout, args)
    else:
        generate(repo, layout, args)


if __name__ == "__main__":
    try:
        main()
    except EmptyReport as err:
        print(f"✖ {err}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, OSError, KeyError, ValueError) as err:
        print(f"✖ {err}", file=sys.stderr)
        sys.exit(1)
