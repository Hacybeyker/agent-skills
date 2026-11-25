#!/usr/bin/env python3
"""Genera el reporte HTML de hb-implement a partir de git y de un meta.json.

El código (antes, después y diff) sale de git: el agente solo escribe el meta.json
con el contexto que git no sabe (título, tipo, por qué de cada archivo, resultado del DoD).

Carpeta de reportes: --out o, sin él, la línea "Carpeta de reportes: <ruta>" del AGENTS.md del repo; si no hay,
reports. Es la base común de las skills (hb-performance y hb-review escriben en sus propias subcarpetas).
- Sin marcadores: una carpeta por tarea, <base>/implementation/<fecha>-<slug>/, con meta.json, report.html,
  bitacora.md y previews/. Una tarea vieja en formato plano (<base>/<fecha>-<slug>.meta.json) sigue ahí, plana.
- Con {fecha} y {slug} en la ruta: la ruta tal cual, con los mismos archivos; la base es la parte fija.
Si ya hay una carpeta con ese slug en otra fecha, la tarea sigue ahí.
Cada tarea tiene su fila en <base>/INDEX.md (clave: hb-implement + slug): "en curso" con --folder y el resultado del DoD
al generar el reporte. Las demás filas y líneas del índice no se tocan; se escribe sobre la ruta real (un enlace
simbólico sigue siendo enlace).
Base de comparación de cada repo: --base (o "base" en "repos"); sin ella, el merge-base de HEAD con su rama principal
(--main-branch o "main_branch"; si no, origin/HEAD, origin/main, origin/master, main o master).
Los archivos masivos o generados (goldens, fixtures) se explican en grupo, por carpeta o patrón,
con "groups"; un archivo con su propia entrada en "files" se muestra aparte.
Con "repos" en el meta, el mismo reporte cubre los repos relacionados (sus claves son "<nombre>:<ruta>"), y
"temporary" deja fuera los cambios de configuración que no son de la tarea.
En un worktree enlazado al que le faltan AGENTS.md (fuera de git en el principal) o el enlace simbólico por el que
pasa la carpeta de reportes, se detiene y dice cómo recrearlos, sin escribir nada.

Uso:
  python3 -I report.py --meta <meta.json> [--base <ref> | --main-branch <rama>] [--out <carpeta>] [--repo .]
  python3 -I report.py --folder <slug> [--date AAAA-MM-DD] [--out <carpeta>] [--repo .]
      (imprime y crea la carpeta de la tarea, sin generar el reporte)
"""
import argparse
import base64
import datetime
import difflib
import fnmatch
import glob
import html
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "report-template.html"
TYPES = {
    "feature": ("badge-feature", "✨ Feature"),
    "bugfix": ("badge-bugfix", "🐛 Bug Fix"),
    "enhancement": ("badge-enhancement", "⚡ Enhancement"),
    "refactor": ("badge-refactor", "♻️ Refactor"),
}
PILLS = {
    "pass": ("pill-pass", "✅ PASS"),
    "fail": ("pill-fail", "❌ FAIL"),
    "skipped": ("pill-skipped", "⏭️ SKIPPED"),
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
MAIN_BRANCHES = ("origin/main", "origin/master", "main", "master")
MARKER = re.compile(r"(\{fecha\}|\{slug\})")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# "Carpeta de reportes: <ruta>" en AGENTS.md, con o sin viñeta, negrita o acentos graves (también en inglés).
FOLDER_KEY = re.compile(r"carpeta\s+de\s+(?:los\s+)?reportes|reports?\s+folder", re.I)
FOLDER_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?[*_]*(?P<key>[^:*_`]+?)[*_]*[ \t]*:[*_]*[ \t]*(?P<value>\S.*?)[ \t]*$")
e = html.escape


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def decode(data):
    if data is None:
        return None
    if b"\0" in data[:8000]:
        return False  # binario
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return False


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


class Task:
    """La carpeta de una tarea y sus archivos. flat: el formato plano de antes, <base>/<fecha>-<slug>.<extensión>,
    que se conserva para las tareas que ya estaban así."""
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
                           and re.fullmatch(r"\s*\|(\s*:?-+:?\s*\|)+\s*", lines[i + 1])), None)
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


def load_repos(main, main_base, main_branch, entries):
    """El repo principal primero y después los relacionados de "repos" del meta:
    [{root, name, base, base_label, main, pinned, source, warnings}]. Una entrada que apunta al principal solo le pone
    nombre, base o rama principal (--base y --main-branch mandan sobre ella)."""
    repos = [{"root": main, "name": main.name, "base": main_base, "main_branch": main_branch, "main": True,
              "pinned": None, "source": None}]
    for entry in entries:
        path = pathlib.Path(os.path.expanduser(str(entry["path"])))
        path = path if path.is_absolute() else main / path
        try:
            root = toplevel(path)
        except (RuntimeError, OSError) as err:
            raise RuntimeError(
                f'No puedo leer el repo relacionado "{entry.get("name") or entry["path"]}" ({path}): si existe, '
                f'dale al agente acceso a esa carpeta; si no, corrige "path" en "repos" del meta. Detalle: {err}')
        name = str(entry.get("name") or root.name)
        if root.resolve() == main.resolve():
            repos[0]["name"] = name
            repos[0]["base"] = repos[0]["base"] or entry.get("base")
            repos[0]["main_branch"] = repos[0]["main_branch"] or entry.get("main_branch")
            continue
        repos.append({"root": root, "name": name, "base": entry.get("base"), "main_branch": entry.get("main_branch"),
                      "main": False, "pinned": entry.get("pinned_version"), "source": entry.get("source_version")})
    names = [r["name"] for r in repos]
    for name in names:
        if not name or ":" in name or "/" in name:
            raise ValueError(f'el nombre de repo "{name}" no sirve como prefijo: sin ":" ni "/"')
        if names.count(name) > 1:
            raise ValueError(f'dos repos se llaman "{name}": ponles "name" distintos en "repos" del meta')
    for repo in repos:
        resolve_base(repo)
        if repo["pinned"] and not repo["source"]:  # lo que había en el fuente al empezar: la base, no lo de la tarea
            repo["source"] = describe(repo["root"], repo["base"])
        repo["version_mismatch"] = bool(repo["pinned"] and repo["source"]
                                        and not same_version(repo["pinned"], repo["source"]))
        if repo["version_mismatch"]:
            repo["warnings"].append(
                f'⚠️  {repo["name"]}: el fuente ({repo["source"]}) no coincide con la versión que fija la app '
                f'({repo["pinned"]}): lo probado en fuente puede no compilar o comportarse distinto con lo publicado.')
    return repos


def changed_files(repo, base, layout):
    files = []
    try:
        listing = git(repo["root"], "diff", "--name-status", "-M", base).decode()
    except RuntimeError as err:
        raise RuntimeError(f'{repo["name"]}: no pude comparar contra {base}: {err}')
    for line in listing.splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            files.append({"status": "M", "path": parts[2], "old": parts[1]})
        elif status in "AMD":
            files.append({"status": status, "path": parts[1], "old": parts[1]})
    for path in git(repo["root"], "ls-files", "--others", "--exclude-standard").decode().splitlines():
        files.append({"status": "A", "path": path.rstrip("/"), "old": None})
    return [f for f in files if not layout.is_output(repo["root"] / f["path"])]


def read_before(repo, base, path):
    if path is None:
        return None
    try:
        return git(repo, "show", f"{base}:{path}")
    except RuntimeError:
        return None


def read_after(repo, path):
    p = repo / path
    if p.is_symlink():
        return os.readlink(str(p)).encode("utf-8")  # git guarda el destino del enlace
    return p.read_bytes() if p.is_file() else None


# ── Validación del meta ──────────────────────────────────────────────────────
def level(value, what):
    normalized = str(value).strip().lower().replace("í", "i")
    if normalized not in LEVELS:
        raise ValueError(f'{what} debe ser critico, alto, medio o bajo (llegó "{value}")')
    return normalized


def texts(value, what):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{what} debe ser una lista de textos")
    return value


def entries(meta, key, required):
    value = meta.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f'"{key}" debe ser una lista de objetos')
    for item in value:
        missing = [field for field in required if not str(item.get(field) or "").strip()]
        if missing:
            raise ValueError(f'cada entrada de "{key}" necesita {", ".join(missing)}')
    return value


def validate(meta):
    """Falla antes de escribir nada si un campo opcional viene con un valor que no sirve."""
    if not isinstance(meta, dict):
        raise ValueError("el meta debe ser un objeto JSON")
    files = meta.get("files", {})
    if not isinstance(files, dict) or not all(isinstance(info, dict) for info in files.values()):
        raise ValueError('"files" debe ser un objeto con un objeto por archivo')
    for key, info in files.items():
        if "risk" in info:
            info["risk"] = level(info["risk"], f'"risk" de {key}')
        for field in ("pros", "cons"):
            if field in info:
                texts(info[field], f'"{field}" de {key}')
    if "severity" in meta:
        meta["severity"] = level(meta["severity"], '"severity"')
    if "root_cause" in meta and not isinstance(meta["root_cause"], str):
        raise ValueError('"root_cause" debe ser un texto')
    if "slug" in meta and not isinstance(meta["slug"], str):
        raise ValueError('"slug" debe ser un texto')
    entries(meta, "impact", ("label",))
    entries(meta, "diagrams", ("mermaid",))
    for repo in entries(meta, "repos", ("path",)):
        for field in ("base", "main_branch", "pinned_version", "source_version"):
            if field in repo and repo[field] is not None and not isinstance(repo[field], str):
                raise ValueError(f'"{field}" de "repos" debe ser un texto')
    entries(meta, "temporary", ("path",))


# ── HTML ─────────────────────────────────────────────────────────────────────
def code_block(text, dim=False):
    if text is False:
        return '<div class="empty-state">Archivo binario: no se muestra el contenido.</div>'
    if text is None:
        return '<div class="empty-state">Sin contenido para mostrar.</div>'
    lines = text.splitlines()
    cut = len(lines) > MAX_LINES
    body = "\n".join(f'<span class="line-num">{i}</span>{e(l)}' for i, l in enumerate(lines[:MAX_LINES], 1))
    if cut:
        body += f'\n<span class="line-num">…</span>(recortado: {len(lines) - MAX_LINES} líneas más)'
    style = ' style="opacity:.6"' if dim else ""
    return f'<pre class="code-block"{style}>{body}</pre>'


def diff_block(before, after):
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
    html_rows = "".join(
        f'<div class="diff-line {cls}"><div class="gutter">{g}</div><div class="content">{e(c)}</div></div>'
        for cls, g, c in rows
    )
    return f'<div class="diff-block">{html_rows}</div>'


def summary(items):
    cells = "".join(
        f'<div class="change-summary-item change-summary-{kind}"><div class="change-summary-label">{label}</div>{e(text)}</div>'
        for kind, label, text in items if text
    )
    return f'<div class="change-summary">{cells}</div>' if cells else ""


STATUS = {"A": ("status-new", "New"), "M": ("status-modified", "Modified"), "D": ("status-deleted", "Deleted")}


def status_summary(status, info):
    if status == "A":
        return summary([("after", "✅ Por qué se crea", info.get("why"))])
    if status == "D":
        return summary([("before", "🗑️ Por qué se elimina", info.get("why"))])
    return summary([("before", "⚠️ Antes", info.get("before")), ("after", "✅ Después", info.get("after") or info.get("why"))])


def analysis(info):
    """Pros y contras del cambio, solo si el meta los trae. Una lista de contras vacía también dice algo."""
    columns = []
    if "pros" in info:
        items = "".join(f"<li>{e(item)}</li>" for item in info["pros"]) or "<li>—</li>"
        columns.append(f'<div class="analysis-item analysis-pros"><div class="change-summary-label">👍 Pros</div>'
                       f'<ul>{items}</ul></div>')
    if "cons" in info:
        items = ("<ul>" + "".join(f"<li>{e(item)}</li>" for item in info["cons"]) + "</ul>" if info["cons"]
                 else '<p class="analysis-none">Sin contras identificados</p>')
        columns.append(f'<div class="analysis-item analysis-cons"><div class="change-summary-label">👎 Contras</div>'
                       f'{items}</div>')
    return f'<div class="analysis">{"".join(columns)}</div>' if columns else ""


def risk_pill(info):
    risk = info.get("risk")
    return f'<span class="risk risk-{risk}">{RISK_LABELS[risk]}</span>' if risk else ""


def repo_tag(f):
    return f'<span class="repo-tag">{e(f["repo"]["name"])}</span>' if f.get("show_repo") else ""


def file_entry(index, f, info):
    status = STATUS[f["status"]]
    path = f["path"] if f["status"] != "M" or f["old"] in (None, f["path"]) else f'{f["old"]} → {f["path"]}'
    head = (f'<div class="file-header" onclick="toggleFile(this)"><span class="file-status {status[0]}">{status[1]}</span>'
            f'{repo_tag(f)}<span class="file-path">{e(path)}</span>{risk_pill(info)}<span class="file-toggle">▼</span></div>')
    if f["status"] == "A":
        body = status_summary("A", info) + analysis(info) + code_block(f["after"])
    elif f["status"] == "D":
        body = status_summary("D", info) + analysis(info) + code_block(f["before"], dim=True)
    else:
        fid = f"f{index}"
        tabs = "".join(
            f'<div class="panel-tab{" active" if t == "diff" else ""}" onclick="switchTab(\'{fid}\',\'{t}\')">{label}</div>'
            for t, label in (("before", "Antes"), ("after", "Después"), ("diff", "Diff"))
        )
        panels = (f'<div class="panel-content" id="{fid}-before">{code_block(f["before"])}</div>'
                  f'<div class="panel-content" id="{fid}-after">{code_block(f["after"])}</div>'
                  f'<div class="panel-content active" id="{fid}-diff">{diff_block(f["before"], f["after"])}</div>')
        body = status_summary("M", info) + analysis(info) + f'<div class="panel-tabs" id="tabs-{fid}">{tabs}</div>{panels}'
    return f'<div class="file-entry open">{head}<div class="file-body">{body}</div></div>'


def group_for(path, groups):
    """El primer grupo cuyo "match" cubre la ruta: una carpeta (termina en /) o un patrón fnmatch."""
    for group in groups:
        pattern = group.get("match") or ""
        if pattern.endswith("/") and path.startswith(pattern):
            return group
        if pattern and not pattern.endswith("/") and fnmatch.fnmatchcase(path, pattern):
            return group
    return None


def group_entry(group, status, paths):
    label = STATUS[status]
    total = f"{len(paths)} archivo" + ("" if len(paths) == 1 else "s")
    head = (f'<div class="file-header" onclick="toggleFile(this)"><span class="file-status {label[0]}">{label[1]}</span>'
            f'<span class="file-path">{e(group["match"])} · {total}</span><span class="file-toggle">▼</span></div>')
    listing = '<pre class="code-block">' + e("\n".join(paths)) + "</pre>"
    return f'<div class="file-entry open">{head}<div class="file-body">{status_summary(status, group)}{listing}</div></div>'


def section(icon, title, entries, empty, count=None):
    content = "".join(entries) or f'<div class="empty-state">{empty}</div>'
    count = len(entries) if count is None else count
    return (f'<div class="section"><div class="section-header"><span class="section-icon">{icon}</span>'
            f'<span class="section-title">{title}</span><span class="section-count">{count}</span></div>{content}</div>')


def plain_section(icon, title, content, count=None):
    badge = f'<span class="section-count">{count}</span>' if count is not None else ""
    return (f'<div class="section"><div class="section-header"><span class="section-icon">{icon}</span>'
            f'<span class="section-title">{title}</span>{badge}</div>{content}</div>')


def dod_section(steps):
    if not steps:
        return ""
    rows = ['<div class="dod-row dod-header"><div></div><div>Tarea</div><div>Comando</div><div>Resultado</div></div>']
    outputs = []
    for s in steps:
        cls, label = PILLS.get(s.get("status", "skipped"), PILLS["skipped"])
        note = f' · {e(s["note"])}' if s.get("note") else ""
        rows.append(f'<div class="dod-row"><div>{e(s.get("icon", "•"))}</div><div>{e(s.get("name", ""))}</div>'
                    f'<div>{e(s.get("command", ""))}</div><div><span class="pill {cls}">{label}</span>{note}</div></div>')
        if s.get("output"):
            outputs.append(f'<p style="margin:20px 0 8px"><strong>{e(s.get("name", ""))}</strong></p>{code_block(s["output"])}')
    return (f'<div class="section"><div class="section-header"><span class="section-icon">✅</span>'
            f'<span class="section-title">Definition of Done</span></div><div class="dod-grid">{"".join(rows)}</div>'
            f'{"".join(outputs)}</div>')


def preview_path(repo, task, image):
    """La imagen de un preview: absoluta, relativa al repo (la ruta previews: que imprime --folder, aunque pase por un
    enlace simbólico) o relativa a la carpeta de la tarea (previews/<archivo>)."""
    path = pathlib.Path(os.path.expanduser(str(image)))
    if path.is_absolute():
        return path
    candidates = [repo / path] + ([task.folder / path] if task is not None else [])
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


def preview_figure(repo, preview, missing, task=None):
    path = preview_path(repo, task, preview.get("image", ""))
    name, note = e(preview.get("name", path.stem)), e(preview.get("note", ""))
    caption = f'<figcaption style="margin-top:8px;color:var(--text-secondary)"><strong>{name}</strong>{" · " + note if note else ""}</figcaption>'
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime and path.is_file():
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        body = (f'<img src="data:{mime};base64,{data}" alt="{name}" '
                f'style="width:100%;max-width:360px;border:1px solid var(--border);border-radius:var(--radius-md)">')
    else:
        missing.append(str(path))
        body = f'<div class="empty-state">No se encontró la imagen: {e(str(path))}</div>'
    return f'<figure style="margin:0">{body}{caption}</figure>'


def previews_section(repo, previews, missing, task=None):
    """Imágenes incrustadas en base64: el reporte sigue siendo un solo archivo que se puede compartir."""
    if not previews:
        return ""
    figures = "".join(preview_figure(repo, p, missing, task) for p in previews)
    return (f'<div class="section"><div class="section-header"><span class="section-icon">🖼️</span>'
            f'<span class="section-title">Previews de UI</span><span class="section-count">{len(previews)}</span></div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:20px">{figures}</div></div>')


def version_cell(repo):
    """La versión que fija la app frente a la del fuente, con un aviso si no coinciden."""
    parts = []
    if repo["pinned"]:
        parts.append(f'fijada <code>{e(repo["pinned"])}</code>')
    if repo["source"]:
        parts.append(f'fuente <code>{e(repo["source"])}</code>')
    flag = ' <span class="version-mismatch">⚠️ no coinciden</span>' if repo["version_mismatch"] else ""
    return " · ".join(parts) + flag if parts else "—"


def repos_section(repos, files):
    """Con más de un repo: nombre, rama, base usada y conteos de cada uno; si alguno trae versiones, la fijada y la
    del fuente, con un aviso arriba cuando no coinciden."""
    if len(repos) < 2:
        return ""
    versions = any(repo["pinned"] or repo["source"] for repo in repos)
    rows = ['<tr><th>Repo</th><th>Rama</th><th>Base</th>' + ("<th>Versión</th>" if versions else "") +
            '<th>Nuevos</th><th>Modificados</th><th>Eliminados</th></tr>']
    for repo in repos:
        counts = [sum(1 for f in files if f["repo"] is repo and f["status"] == k) for k in "AMD"]
        rows.append(f'<tr><td><span class="repo-tag">{e(repo["name"])}</span></td><td>{e(repo["branch"])}</td>'
                    f'<td>{base_html(repo)}</td>' + (f"<td>{version_cell(repo)}</td>" if versions else "") +
                    "".join(f"<td>{n}</td>" for n in counts) + "</tr>")
    warnings = "".join(
        f'<div class="note-block version-warning">⚠️ {e(repo["name"])}: el fuente ({e(repo["source"])}) no coincide '
        f'con la versión que fija la app ({e(repo["pinned"])}). Lo probado en fuente puede no compilar o comportarse '
        "distinto con lo publicado: revísalo antes de publicar.</div>"
        for repo in repos if repo["version_mismatch"])
    return plain_section("🗂️", "Repositorios", warnings + f'<div class="table-wrap"><table class="repos-table">'
                         f'{"".join(rows)}</table></div>', len(repos))


def base_line(repos):
    """Con un solo repo no hay tabla de repositorios: la base usada va bajo la descripción."""
    if len(repos) > 1:
        return ""
    return f'<p class="hero-base">Comparado con {base_html(repos[0])}</p>'


def root_cause_section(meta):
    text = meta.get("root_cause", "").strip()
    return plain_section("🎯", "Causa raíz", f'<div class="note-block">{e(text)}</div>') if text else ""


def impact_section(items):
    if not items:
        return ""
    cards = "".join(f'<div class="stat-card"><div class="stat-label">{e(str(item["label"]))}</div>'
                    f'<div class="impact-value">{e(str(item.get("value", "")))}</div></div>' for item in items)
    return plain_section("📊", "Impacto", f'<div class="impact-grid">{cards}</div>', len(items))


def diagrams_section(items):
    """El código Mermaid va escapado en <pre class="mermaid">: sin conexión se lee como texto."""
    if not items:
        return ""
    figures = []
    for item in items:
        title = f'<figcaption class="diagram-title">{e(str(item.get("title", "")))}</figcaption>' if item.get("title") else ""
        desc = f'<p class="diagram-desc">{e(str(item["description"]))}</p>' if item.get("description") else ""
        figures.append(f'<figure class="diagram">{title}<div class="diagram-body"><pre class="mermaid">'
                       f'{e(item["mermaid"])}</pre></div>{desc}</figure>')
    return plain_section("🧭", "Diagramas", "".join(figures), len(items))


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
    intro = '<p class="temp-intro">No son parte de la tarea: no se cuentan, no se commitean y se revierten al terminar.</p>'
    return plain_section("🔧", "Cambios temporales", intro + "".join(rows), len(items))


def mermaid_scripts(items):
    if not items:
        return ""
    return (f'<script src="{MERMAID_URL}" integrity="{MERMAID_SRI}" crossorigin="anonymous"></script>\n'
            "<script>if (window.mermaid) { mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', "
            "theme: 'dark' }); mermaid.run({ querySelector: 'pre.mermaid' }); }</script>")


def dod_stat(steps):
    statuses = {s.get("status") for s in steps}
    if not steps:
        return "—", ""
    if "fail" in statuses:
        return "FAIL", "red"
    if statuses == {"pass"}:
        return "PASS", "green"
    return "PARTIAL", "orange"


# ── Main ─────────────────────────────────────────────────────────────────────
def meta_type(path):
    """El "type" de un meta que ya existe, o None."""
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    kind = meta.get("type") if isinstance(meta, dict) else None
    return kind if isinstance(kind, str) and kind.strip() else None


def print_folder(repo, layout, args):
    task_slug = safe_slug(args.folder)
    date = args.date or datetime.date.today().isoformat()
    task = layout.task(task_slug, date)
    real(task.folder).mkdir(parents=True, exist_ok=True)
    meta_file = task.file("meta")
    warnings = [ensure_ignored(repo, layout.root, meta_file),
                update_index(layout, task, meta_type(real(meta_file)), "en curso")]
    print(f"📁 Carpeta de la tarea: {shown(task.folder, repo)}" + (" (la tarea ya existía: sigue ahí)" if task.reused else ""))
    print(f"   meta: {shown(meta_file, repo)}")
    print(f"   bitácora, si hace falta: {shown(task.file('bitacora'), repo)}")
    print(f"   previews: {shown(task.previews, repo)}")
    print(f"   índice: {shown(layout.index, repo)}")
    for warning in warnings:
        if warning:
            print(warning, file=sys.stderr)


def dod_state(steps):
    value = dod_stat(steps)[0]
    return "sin DoD" if value == "—" else "DoD " + value


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    task_group = ap.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--meta", help="JSON con título, tipo, explicaciones por archivo y DoD")
    task_group.add_argument("--folder", metavar="SLUG",
                            help="imprime y crea la carpeta de la tarea, sin generar el reporte")
    ap.add_argument("--base", help="ref del repo principal contra la que se compara (manda sobre --main-branch; por "
                                   "defecto, el merge-base de HEAD con la rama principal)")
    ap.add_argument("--main-branch", help="la rama principal del repo principal, la del modelo de AGENTS.md (por "
                                          "defecto, origin/HEAD, origin/main, origin/master, main o master)")
    ap.add_argument("--out", help="carpeta de reportes, relativa al repo; puede usar {fecha} y {slug} "
                                  "(por defecto, la de AGENTS.md o reports)")
    ap.add_argument("--repo", default=".", help="raíz del repositorio principal")
    ap.add_argument("--date", help="con --folder: la fecha AAAA-MM-DD (por defecto, hoy)")
    args = ap.parse_args()

    repo = toplevel(args.repo)
    layout = Layout(repo, args.out or agents_out(repo) or DEFAULT_OUT)
    check_worktree(repo, layout, with_agents=not args.out)
    if args.folder:
        print_folder(repo, layout, args)
        return

    meta_path = lexical(args.meta)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    validate(meta)
    date = meta.get("date") or datetime.date.today().isoformat()
    task_slug = safe_slug(meta["slug"]) if meta.get("slug") else slug(meta.get("title", "reporte"))
    task = layout.task(task_slug, date, meta_path)
    out = task.file("report")
    repos = load_repos(repo, args.base, args.main_branch, meta.get("repos", []))
    template = TEMPLATE.read_text(encoding="utf-8")
    # Los bloques que empiezan una línea: una mención en un comentario de la plantilla no cuenta.
    style = re.search(r"^[ \t]*(<style>.*?</style>)", template, re.S | re.M).group(1)
    script = re.search(r"^[ \t]*(<script>.*?</script>)", template, re.S | re.M).group(1)

    infos = meta.get("files", {})
    group_defs = meta.get("groups", [])
    temporary = meta.get("temporary", [])
    temporary_keys = {str(item["path"]) for item in temporary}
    multi = len(repos) > 1
    files, temporary_found = [], set()
    for r in repos:
        r["branch"] = branch(r["root"])
        for f in changed_files(r, r["base"], layout):
            f["repo"], f["show_repo"] = r, multi
            f["key"] = f["path"] if r["main"] else f'{r["name"]}:{f["path"]}'
            aliases = (f["key"], f'{r["name"]}:{f["path"]}')
            if any(alias in temporary_keys for alias in aliases):
                temporary_found.update(aliases)
                continue
            f["info"] = next((infos[alias] for alias in aliases if alias in infos), None)
            f["before"] = decode(read_before(r["root"], r["base"], f["old"])) if f["status"] != "A" else None
            f["after"] = decode(read_after(r["root"], f["path"])) if f["status"] != "D" else None
            # Un archivo con su propia entrada en "files" se muestra aparte, aunque un grupo lo cubra.
            f["group"] = None if f["info"] is not None else group_for(f["key"], group_defs)
            files.append(f)

    groups = {k: [] for k in "AMD"}
    counts = {k: sum(1 for f in files if f["status"] == k) for k in "AMD"}
    for k in "AMD":
        grouped = {}
        for i, f in enumerate(files):
            if f["status"] != k:
                continue
            if f["group"] is None:
                groups[k].append(file_entry(i, f, f["info"] or {}))
            else:
                grouped.setdefault(id(f["group"]), (f["group"], []))[1].append(f["key"])
        groups[k].extend(group_entry(group, k, paths) for group, paths in grouped.values())
    project = meta.get("project") or repo.name
    badge_cls, badge_label = TYPES.get(meta.get("type", "feature"), TYPES["feature"])
    dod = meta.get("dod", [])
    dod_value, dod_color = dod_stat(dod)
    scope = f'<span class="tag">{e(meta["scope"])}</span>' if meta.get("scope") else ""
    severity = (f'<span class="badge severity severity-{meta["severity"]}">{SEVERITY_LABELS[meta["severity"]]}</span>'
                if meta.get("severity") else "")
    missing_previews = []
    previews = previews_section(repo, meta.get("previews", []), missing_previews, task)
    diagrams = meta.get("diagrams", [])

    page = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(project)} · {e(meta.get("title", "Reporte"))}</title>
{style}
</head><body>
<div class="topbar"><span class="topbar-logo">{e(project)}</span><span class="topbar-sep">/</span>
<span class="topbar-title">Implementation Report</span><div class="topbar-spacer"></div><span class="topbar-date">{e(date)}</span></div>
<div class="container">
<div class="hero"><div class="hero-eyebrow"><span class="badge {badge_cls}">{badge_label}</span>{severity}{scope}</div>
<h1 class="hero-title">{e(meta.get("title", ""))}</h1><p class="hero-desc">{e(meta.get("description", ""))}</p>
{base_line(repos)}
<div class="stats-row">
<div class="stat-card"><div class="stat-label">Archivos Nuevos</div><div class="stat-value green">{counts["A"]}</div></div>
<div class="stat-card"><div class="stat-label">Archivos Modificados</div><div class="stat-value" style="color:var(--accent-blue)">{counts["M"]}</div></div>
<div class="stat-card"><div class="stat-label">Archivos Eliminados</div><div class="stat-value red">{counts["D"]}</div></div>
<div class="stat-card"><div class="stat-label">DoD</div><div class="stat-value {dod_color}">{dod_value}</div></div>
</div></div>
{repos_section(repos, files)}
{root_cause_section(meta)}
{impact_section(meta.get("impact", []))}
{diagrams_section(diagrams)}
{previews}
{section("🆕", "Archivos Nuevos", groups["A"], "No hay archivos nuevos.", counts["A"])}
{section("✏️", "Archivos Modificados", groups["M"], "No hay archivos modificados.", counts["M"])}
{section("🗑️", "Archivos Eliminados", groups["D"], "Ningún archivo fue eliminado.", counts["D"])}
{temporary_section(temporary)}
{dod_section(dod)}
<div class="footer"><div><span class="footer-brand">{e(project)}</span> &nbsp;·&nbsp; Generado el {e(date)}</div>
<div>Generado con <strong>hb-implement</strong> · No hacer commit sin revisión manual</div></div>
</div>
{script}
{mermaid_scripts(diagrams)}
</body></html>
"""
    real(out.parent).mkdir(parents=True, exist_ok=True)
    real(out).write_text(page, encoding="utf-8")
    print(f"📄 Reporte generado: {shown(out, repo)}")
    if task.reused:
        print(f"ℹ️  Ya había una carpeta para «{task.slug}»: la tarea sigue en {shown(task.folder, repo)}"
              + (" (formato plano de antes)" if task.flat else ""))
    for r in repos:
        print(f"🔀 Base de {r['name']}: {base_text(r)}")
    warnings = [ensure_ignored(repo, layout.root, out), update_index(layout, task, meta.get("type") or "feature",
                                                                     dod_state(dod))]
    print(f"🗂️  Índice: {shown(layout.index, repo)}")
    for warning in warnings + [w for r in repos for w in r["warnings"]]:
        if warning:
            print(warning, file=sys.stderr)
    for path in missing_previews:
        print(f"⚠️  Preview sin imagen: {path}", file=sys.stderr)
    missing = [f["key"] for f in files if f["info"] is None and f["group"] is None]
    if missing:
        print("ℹ️  Archivos sin explicación en meta.json: " + ", ".join(missing), file=sys.stderr)
        if len(missing) > 5:
            print('ℹ️  Si son archivos generados o masivos (goldens, fixtures), explícalos en grupo con "groups".',
                  file=sys.stderr)
    for group in group_defs:
        if not any(f["group"] is group for f in files):
            print(f'ℹ️  El grupo "{group.get("match", "")}" no cubre ningún archivo cambiado.', file=sys.stderr)
    for key in sorted(temporary_keys - temporary_found):
        print(f'ℹ️  El cambio temporal "{key}" no aparece entre los cambios de git (si git lo ignora, está bien).',
              file=sys.stderr)
    if not task.flat and real(task.folder) != real(meta_path.parent):
        print(f"ℹ️  Con una carpeta por tarea, el meta va en {shown(task.file('meta'), repo)} "
              f"(report.py --folder {task.slug} te la da).", file=sys.stderr)
    if task.flat and meta_path.name == "meta.json" and real(meta_path.parent) == real(layout.root):
        print(f"ℹ️  {shown(meta_path, repo)} lo pisa la siguiente tarea: usa un meta por tarea, en la carpeta que da "
              f"report.py --folder <slug> ({shown(layout.root / SUBFOLDER, repo)}/<fecha>-<slug>/meta.json).",
              file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, ValueError) as err:
        print(f"✖ {err}", file=sys.stderr)
        sys.exit(1)
