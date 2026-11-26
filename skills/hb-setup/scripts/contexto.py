#!/usr/bin/env python3
"""Prepara dónde vive el contexto de IA de un proyecto (AGENTS.md, CLAUDE.md, docs y reportes) sin pisar nada.

Tres modos, los mismos que "Contexto de IA" en ## Reglas del proyecto:
- versionado: todo en el repo, como cualquier archivo (por defecto).
- local: en el repo, pero fuera de git con .git/info/exclude (nunca editando .gitignore).
- externo: en una carpeta fuera del repo; en el repo quedan enlaces simbólicos (AGENTS.md, CLAUDE.md si aplica y la
  carpeta de contexto) excluidos con .git/info/exclude. Lo que ya haya en la carpeta externa se usa: no se pisa.

El contenido de AGENTS.md lo escribe el agente: este script deja la estructura y dice dónde escribir. Antes de cambiar
algo comprueba todo; si hay un conflicto, no toca nada y lo explica.

También deja fuera de git (en .git/info/exclude) los archivos locales de las herramientas de IA que no están
versionados ni ignorados (.claude/settings.local.json, CLAUDE.local.md, los de aider), y revisa la sección de
rendimiento de AGENTS.md que mantiene hb-performance sin reescribirla.

`producto` lee la sección `## Producto` de AGENTS.md que usa hb-product (se conserva tal cual) y su línea `Carpeta:`
(por defecto product), e imprime la fila de `<carpeta>/04-prd.md` para "Documentos" de ## Estructura. No escribe nada
y nunca crea la sección.

`units` es el inventario de solo lectura para ## Estructura: las unidades candidatas del repo (módulos del build,
paquetes de un espacio de trabajo, carpetas de feature), los repos vecinos clonados y sin clonar que nombra la
configuración, los archivos versionados modificados que nombran a esos vecinos y lo que no coincide con el modelo que
ya tenga AGENTS.md. Suma los archivos que pasan unidades a fuente (archivo de sustitución) con las entradas que no
siguen su patrón, las dependencias del build que no están en ellos, los repos en otro host y los scripts que
sincronizan el espacio de trabajo. No compila ni ejecuta nada.

`fuentes` busca todo contexto de IA previo (AGENTS.md y sus variantes renombradas, CLAUDE.md, las instrucciones de otros
agentes y los .md de la carpeta de contexto con instrucciones para agentes), aunque no exista AGENTS.md: con alguna, el
camino es migrar. Lista los bloques y secciones de otras skills (van tal cual), las skills locales que se solapan con
una hb-* y el inventario de traspaso con un destino sugerido por sección. `verificar` comprueba el traspaso contra ese
inventario: cada sección en AGENTS.md, en un doc con su fila en "Documentos" o descartada con motivo; lo de otras skills
tal cual; "Documentos" sin la fuente que se reemplaza. Ninguno de los dos escribe nada.

Uso:
  python3 -I contexto.py estado [--carpeta contexto] [--repo .]
  python3 -I contexto.py preparar --modo versionado|local|externo [--externa <ruta>] [--carpeta contexto]
                                  [--reportes <ruta>] [--claude auto|si|no] [--module-maps local|versioned] [--repo .]
  python3 -I contexto.py units [--repo .]
  python3 -I contexto.py rendimiento [--carpeta contexto] [--repo .]
  python3 -I contexto.py producto [--carpeta contexto] [--repo .]
  python3 -I contexto.py fuentes [--fuente <archivo>] [--carpeta contexto] [--repo .]
  python3 -I contexto.py verificar --inventario <archivo|-> [--previo <ruta>=<copia>] [--fuente <archivo>]
                                   [--carpeta contexto] [--repo .]
"""
import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import unicodedata

MODES = ("versionado", "local", "externo")
# S4: archivos locales de herramientas de IA (configuración personal, historiales): nunca van al repo
LOCAL_AI = re.compile(r"^(?:(?:.*/)?CLAUDE\.local\.md|(?:.*/)?(\.aider[^/]*)(?:/.*)?|"
                      r"(?:.*/)?\.(?:claude|cursor|gemini|codex|junie|windsurf|continue)/(?:.*/)?[^/]*\.local(?:\.[^/]+)?)$")
# S3: la sección de rendimiento de AGENTS.md y su bloque de estado, que mantiene hb-performance
PERF_HEADING = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(?:\d+[.)][ \t]*)?(?:rendimiento|performance)\b", re.I)
ANY_HEADING = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+\S")
PERF_BLOCK = ("<!-- hb-performance:estado -->", "<!-- /hb-performance:estado -->")
SERIALS = ((re.compile(r"\bANDROID_SERIAL=(?!<)[^\s`'\"]+"), "ANDROID_SERIAL=<serial>"),
           (re.compile(r"\badb\s+-s\s+(?!<)[^\s`'\"]+"), "adb -s <serial>"),
           (re.compile(r"--serial(?:\s+|=)(?!<)[^\s`'\"]+"), "--serial <serial>"),
           (re.compile(r"(?<![\w-])emulator-\d{2,5}(?![\w-])"), "<serial>"))
# La sección ## Producto de hb-product y su línea Carpeta:, leídas igual que producto.py (carpeta_de_agents)
PRODUCT_SECTION = re.compile(r"^## Producto[^\n]*\n(.*?)(?=^## |\Z)", re.M | re.S)
PRODUCT_FOLDER = re.compile(r"^[\s*-]*\**Carpeta:?\**:?\s*`?([^`\n]+?)`?\s*$", re.M)
PRODUCT_DEFAULT = "product"
PRD_FILE = "04-prd.md"
MARKER = re.compile(r"\{(?:fecha|slug)\}")
SIBLING_REF = re.compile(r"\.\./([A-Za-z0-9._-]+)")
# Una ruta relativa que puede salir del repo: uno o más "../" y un nombre (../core-lib, ../../core-lib)
OUTSIDE_REF = re.compile(r"((?:\.\./)+)([A-Za-z0-9_-][A-Za-z0-9._-]*)")
# Archivos de configuración donde se busca un repo vecino sin clonar (el código fuente usa ../ para sus imports)
CONFIG_NAME = re.compile(r"(?:^|/)(?:[^/]*\.(?:json|ya?ml|toml|gradle|kts|properties|xml|mod|work|cfg|ini|conf|txt|lock)"
                         r"|\.env[^/]*|\.gitmodules|Podfile|Package\.swift|Makefile)$")
MAPS_CHOICES = ("local", "versioned")
REPORT_FOLDERS = (("hb-implement", "implementation"), ("hb-performance", "performance"), ("hb-review", "review"))


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def toplevel(path):
    found = git(path, "rev-parse", "--show-toplevel")
    if found.returncode != 0:
        raise RuntimeError(f"{path} no es un repo de git: {found.stderr.strip()}")
    return pathlib.Path(found.stdout.strip())


def tracked(repo, relative):
    return bool(git(repo, "ls-files", "--", relative).stdout.strip())


def ignored(repo, relative):
    return git(repo, "check-ignore", "-q", relative).returncode == 0


def exclude_file(repo):
    found = git(repo, "rev-parse", "--git-path", "info/exclude")
    if found.returncode != 0:
        raise RuntimeError("no encontré .git/info/exclude")
    path = pathlib.Path(found.stdout.strip())
    return path if path.is_absolute() else repo / path


def add_exclude(repo, line):
    """Agrega la línea a .git/info/exclude si falta: es local, así que el repo y su .gitignore no cambian."""
    path = exclude_file(repo)
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if line in current.splitlines():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(("" if not current or current.endswith("\n") else "\n") + line + "\n")
    return True


def exists(path):
    """Si la ruta existe (también un enlace roto). Una carpeta sin permiso de lectura cuenta como que no existe: la
    carpeta padre del proyecto puede tener carpetas ajenas (por ejemplo, /tmp)."""
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return False


def is_directory(path):
    try:
        return path.is_dir()
    except OSError:
        return False


def child_folders(folder):
    """Las carpetas hijas que se pueden listar; [] si la carpeta no se puede leer."""
    try:
        return [child for child in folder.iterdir() if is_directory(child)]
    except OSError:
        return []


def uses_claude(repo, choice):
    """CLAUDE.md solo si el proyecto ya lo usa (CLAUDE.md o .claude/) o el usuario lo confirma."""
    if choice in ("si", "no"):
        return choice == "si"
    return exists(repo / "CLAUDE.md") or (repo / ".claude").is_dir()


def home(path):
    """La ruta con ~ si está dentro de la carpeta personal: más corta y sin el nombre de usuario."""
    text, user = str(path), os.path.expanduser("~")
    return "~" + text[len(user):] if user not in ("", "~") and (text == user or text.startswith(user + "/")) else text


def fixed_part(path):
    """La parte de una ruta antes del primer {fecha} o {slug}: la carpeta que se deja fuera de git."""
    parts = pathlib.PurePosixPath(path).parts
    first = next((i for i, part in enumerate(parts) if MARKER.search(part)), len(parts))
    return pathlib.PurePosixPath(*parts[:first]).as_posix() if first else ""


def describe(repo, name):
    """Cómo está hoy una entrada del contexto en el repo."""
    path = repo / name
    if path.is_symlink():
        state = "excluido" if ignored(repo, name) else "NO excluido"
        return f"enlace simbólico a {home(os.path.realpath(str(path)))} ({state})"
    if not path.exists():
        return "no existe"
    if tracked(repo, name):
        return "versionado"
    return "excluido de git (local)" if ignored(repo, name) else "sin versionar y sin excluir"


def common_dir(path):
    """La carpeta común de git de un repo (la misma para todos sus worktrees), resuelta; None si no es un repo."""
    found = git(path, "rev-parse", "--git-common-dir")
    value = found.stdout.strip()
    if found.returncode != 0 or not value:
        return None
    return os.path.realpath(value if os.path.isabs(value) else os.path.join(str(path), value))


def same_repository(repo, other):
    """Si la otra carpeta es un worktree del mismo repo (no es un repo vecino)."""
    mine = common_dir(repo)
    return mine is not None and mine == common_dir(other)


def siblings(repo):
    """Repos hermanos (en la carpeta padre) que algún archivo versionado del proyecto nombra: por ruta (../<nombre>)
    o por nombre (una dependencia publicada con el mismo nombre que el repo). {nombre: {"ruta": [...], "nombre": [...]}}.
    Por nombre son candidatos: se confirman con el usuario."""
    names = sorted(d.name for d in child_folders(repo.parent) if d != repo and exists(d / ".git")
                   and not same_repository(repo, d))
    found = {}

    def note(name, how, file):
        files = found.setdefault(name, {"ruta": [], "nombre": []})[how]
        if file not in files:
            files.append(file)

    for line in git(repo, "grep", "-I", "-o", "-E", r"\.\./[A-Za-z0-9._-]+").stdout.splitlines():
        file, _, match = line.partition(":")
        for name in SIBLING_REF.findall(match):
            if name in names:
                note(name, "ruta", file)
    words = [name for name in names if len(name) >= 3]
    if words:
        patterns = [arg for name in words for arg in ("-e", name)]
        for line in git(repo, "grep", "-I", "-o", "-w", "-F", *patterns).stdout.splitlines():
            file, _, match = line.partition(":")
            if match in words and file not in found.get(match, {}).get("ruta", []):
                note(match, "nombre", file)
    return found


def clean_url(url):
    """La URL del remoto sin usuario ni credenciales (https://usuario:token@host/... → https://host/...)."""
    return re.sub(r"^([a-z][a-z0-9+.-]*://)[^/@]*@", r"\1", url.strip())


def remote_info(repo):
    """(URL del remoto origin sin credenciales, rama principal) de un repo, con None en lo que no se sepa."""
    url = git(repo, "remote", "get-url", "origin")
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    branch = head.stdout.strip().split("/", 1)[-1] if head.returncode == 0 and head.stdout.strip() else None
    if branch is None:
        for name in ("main", "master"):
            if git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/" + name).returncode == 0:
                branch = name
                break
    return (clean_url(url.stdout) if url.returncode == 0 and url.stdout.strip() else None), branch


def repo_files(repo):
    """Los archivos del repo que git ve (versionados y nuevos, sin los ignorados)."""
    return git(repo, "ls-files", "--cached", "--others", "--exclude-standard").stdout.splitlines()


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", re.sub(r"(?m)//.*$", "", text), flags=re.S)


def gradle_modules(repo):
    """Módulos de Gradle de settings.gradle(.kts): {ruta: evidencia}, con el projectDir propio si lo declara."""
    found = {}
    for name in ("settings.gradle.kts", "settings.gradle"):
        text = strip_comments(read_text(repo / name))
        if not text:
            continue
        dirs = {m.group(1).lstrip(":"): m.group(2) for m in re.finditer(
            r"project\(\s*[\"']([^\"']+)[\"']\s*\)\.projectDir\s*=\s*(?:file\(\s*)?(?:new\s+File\([^,]*,\s*)?"
            r"[\"']([^\"']+)[\"']", text)}
        calls = [m.group(1) for m in re.finditer(r"\binclude\s*\(([^)]*)\)", text, re.S)]
        calls += [m.group(1) for m in re.finditer(r"(?m)^[ \t]*include[ \t]+([^(\n][^\n]*)$", text)]
        for call in calls:
            for module in re.findall(r"[\"'](:?[A-Za-z0-9_.:-]+)[\"']", call):
                key = module.lstrip(":")
                path = dirs.get(key, key.replace(":", "/"))
                found[os.path.normpath(path)] = "módulo de Gradle :%s (%s)" % (key, name)
    return found


def expand(repo, patterns, marker, label):
    """Las carpetas que cumplen los patrones de un espacio de trabajo y tienen su archivo de paquete."""
    found = {}
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        for match in glob.glob(str(repo / pattern.rstrip("/")), recursive=True):
            path = pathlib.Path(match)
            if path.is_dir() and (path / marker).is_file() and "node_modules" not in path.parts:
                found[os.path.relpath(str(path), str(repo))] = label
    return found


def workspace_units(repo):
    """Paquetes de espacios de trabajo y módulos de otros builds: {ruta: evidencia}."""
    found = {}
    pnpm = read_text(repo / "pnpm-workspace.yaml")
    block = re.search(r"(?ms)^packages:[ \t]*\n((?:[ \t]+-[^\n]*\n?)+)", pnpm)
    if block:
        patterns = [item.strip().strip("'\"") for item in re.findall(r"-[ \t]*([^\n#]+)", block.group(1))]
        found.update(expand(repo, patterns, "package.json", "paquete del espacio de trabajo (pnpm-workspace.yaml)"))
    try:
        package = json.loads(read_text(repo / "package.json") or "{}")
    except ValueError:
        package = {}
    spaces = package.get("workspaces") if isinstance(package, dict) else None
    if isinstance(spaces, dict):
        spaces = spaces.get("packages")
    if isinstance(spaces, list):
        found.update(expand(repo, [str(s) for s in spaces], "package.json",
                            "paquete del espacio de trabajo (workspaces de package.json)"))
    work = read_text(repo / "go.work")
    for group in re.findall(r"(?ms)^use\s*\((.*?)\)", work) + re.findall(r"(?m)^use\s+([^(\s][^\n]*)$", work):
        for item in group.split():
            if item != ".":
                found[os.path.normpath(item)] = "módulo de Go (go.work)"
    cargo = re.search(r"(?ms)^\[workspace\][^\[]*?members\s*=\s*\[(.*?)\]", read_text(repo / "Cargo.toml"))
    if cargo:
        found.update(expand(repo, re.findall(r"[\"']([^\"']+)[\"']", cargo.group(1)), "Cargo.toml",
                            "crate del espacio de trabajo (Cargo.toml)"))
    for module in re.findall(r"<module>\s*([^<\s]+)\s*</module>", read_text(repo / "pom.xml")):
        found[os.path.normpath(module)] = "módulo de Maven (pom.xml)"
    return {path: why for path, why in found.items() if not path.startswith("..")}


def feature_folders(files, modules):
    """Carpetas de feature (…/features/<nombre> o …/feature/<nombre>) que no contienen un módulo ya detectado. Los .md no
    cuentan: una carpeta de mapas del módulo (modules/<…>/features/<nombre>.md) no es código."""
    found = set()
    for path in files:
        if path.endswith(".md"):
            continue
        match = re.match(r"^((?:[^/]+/)*?(?:features?)/[^/]+)/", path)
        if match:
            found.add(match.group(1))
    return sorted(f for f in found if not any(m == f or m.startswith(f + "/") for m in modules))


def outside_refs(repo, files):
    """Repos vecinos que nombran los archivos de configuración con una ruta que sale del repo:
    {nombre: [archivos]}. Se resuelve cada ../ desde la carpeta del archivo, así que los imports del código no cuentan."""
    root = os.path.normpath(str(repo))
    parent = os.path.dirname(root)
    configs = [f for f in files if CONFIG_NAME.search(f)]
    found = {}
    for file in configs:
        text = read_text(repo / file)
        if not text:
            continue
        here = os.path.dirname(os.path.join(root, file))
        for ups, name in OUTSIDE_REF.findall(text):
            target = os.path.normpath(os.path.join(here, ups, name))
            if os.path.dirname(target) == parent and target != root:
                files_found = found.setdefault(os.path.basename(target), [])
                if file not in files_found:
                    files_found.append(file)
    return found


def modified_naming(repo, names):
    """Archivos versionados que hoy están modificados y nombran a un repo vecino: candidatos a "Configuración local
    modificada a propósito"."""
    out = []
    for line in git(repo, "status", "--porcelain", "--untracked-files=no").stdout.splitlines():
        if len(line) < 4 or "M" not in line[:2]:
            continue
        path = line[3:].strip().strip('"')
        text = read_text(repo / path)
        if any(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(name) + r"(?![A-Za-z0-9_-])", text) for name in names):
            out.append(path)
    return sorted(out)


def section_text(text, title, level):
    """El cuerpo de la primera sección "<# * level> <title>" de un Markdown, o None. Un # dentro de un bloque de código
    no es un título."""
    lines, body, inside, fence = text.splitlines(), [], False, None
    for line in lines:
        fence, marked = next_fence(fence, line)
        heading = re.match(r"^(#{1,6})[ \t]+(.*?)[ \t#]*$", line) if fence is None and not marked else None
        if inside and heading and len(heading.group(1)) <= level:
            break
        if inside:
            body.append(line)
        elif heading and len(heading.group(1)) == level and heading.group(2).strip().lower() == title.lower():
            inside = True
    return "\n".join(body) if inside else None


def table_rows(text):
    """Las filas de la primera tabla de un texto, sin la cabecera ni el separador: [[celda, ...]]."""
    rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]
    return [row for row in cells[2:] if row and any(row)]


def bare(cell):
    """El primer valor entre acentos graves de una celda, o la celda sin adornos."""
    quoted = re.search(r"`([^`]+)`", cell)
    return (quoted.group(1) if quoted else cell).strip()


def model_local_config(repo):
    """Las rutas de "### Configuración local modificada a propósito" de ## Estructura (lo primero entre acentos graves de
    cada viñeta)."""
    structure = section_text(read_text(repo / "AGENTS.md"), "Estructura", 2)
    block = section_text(structure, "Configuración local modificada a propósito", 3) if structure is not None else None
    found = []
    for line in (block or "").splitlines():
        quoted = re.match(r"^[ \t]*[-*][ \t]+`([^`]+)`", line)
        if quoted and not quoted.group(1).startswith("<"):
            found.append(norm(quoted.group(1)))
    return found


def covered(path, sources):
    """Si una ruta candidata cae dentro de la fuente de alguna unidad del modelo ("." cubre todo el repo)."""
    path = norm(path)
    return any(path == source or (source == "." and not path.startswith("..")) or path.startswith(source + "/")
               for source in sources)


def norm(path):
    path = path.strip().rstrip("/")
    return os.path.normpath(path) if path else "."


def model_units(repo):
    """Lo que dice AGENTS.md: ("estructura" | "repos relacionados" | None, [(identificador, fuente)])."""
    text = read_text(repo / "AGENTS.md")
    structure = section_text(text, "Estructura", 2)
    if structure is not None:
        units = section_text(structure, "Unidades", 3)
        rows = table_rows(units if units is not None else structure)
        return "estructura", [(bare(row[0]), norm(bare(row[1]))) for row in rows if len(row) >= 2]
    related = section_text(text, "Repos relacionados", 3)
    if related is not None:
        return "repos relacionados", [(bare(row[0]), norm(bare(row[1]))) for row in table_rows(related) if len(row) >= 2]
    return None, []


def units(args):
    """Inventario de solo lectura para ## Estructura: no cambia nada ni compila."""
    repo = toplevel(args.repo)
    files = repo_files(repo)
    url, branch = remote_info(repo)
    print("Repo principal: %s (remoto: %s; rama principal: %s)" % (repo.name, url or "sin remoto origin",
                                                                    branch or "sin determinar"))
    modules = dict(gradle_modules(repo))
    modules.update(workspace_units(repo))
    print("Unidades candidatas en este repo:")
    if modules:
        for path in sorted(modules):
            state = "" if (repo / path).is_dir() else "  ⚠ la carpeta no existe"
            print("  %s  (%s)%s" % (path, modules[path], state))
    else:
        print("  ninguna declarada por el build: la unidad es el repo entero, o las carpetas de feature")
    features = feature_folders(files, modules)
    if features:
        more = " y %d más" % (len(features) - 30) if len(features) > 30 else ""
        print("Carpetas de feature (candidatas a unidad en un proyecto de un solo módulo): " + ", ".join(features[:30])
              + more)
    cloned = siblings(repo)
    refs = {name: found for name, found in outside_refs(repo, files).items()
            if not (exists(repo.parent / name / ".git") and same_repository(repo, repo.parent / name))}
    names = sorted(set(cloned) | set(refs))
    print("Repos vecinos que nombra el proyecto:" + ("" if names else " ninguno"))
    sibling_urls = {}
    for name in names:
        path = repo.parent / name
        if name in refs:  # una ruta de un archivo de configuración que, resuelta, sale del repo
            evidence, how = refs[name], "como ruta"
        elif cloned[name]["ruta"]:  # ../<nombre> en cualquier archivo, también en el código: puede ser un import
            evidence, how = cloned[name]["ruta"], "nombrado como ../%s, candidato a confirmar" % name
        else:
            evidence, how = cloned[name]["nombre"], "por nombre, candidato a confirmar"
        more = " y %d más" % (len(evidence) - 3) if len(evidence) > 3 else ""
        if exists(path / ".git"):
            sibling_url, sibling_branch = remote_info(path)
            sibling_urls[name] = sibling_url
            state = "clonado; remoto: %s; rama principal: %s" % (sibling_url or "sin remoto origin",
                                                                  sibling_branch or "sin determinar")
        elif exists(path):
            state = "la carpeta existe pero no es un repo de git"
        else:
            state = "SIN CLONAR: pregunta la URL de su remoto"
        print("  ../%s  %s  (%s: %s%s)" % (name, state, how, ", ".join(evidence[:3]), more))
    structure_details(repo, files, sibling_urls)
    registered = model_local_config(repo)
    candidates = modified_naming(repo, names)
    new = [path for path in candidates if norm(path) not in registered]
    if new:
        print("Archivos versionados modificados que nombran repos vecinos (candidatos a «Configuración local "
              "modificada a propósito»: confírmalos con el usuario): " + ", ".join(new))
    if registered:
        print("Configuración local modificada a propósito (ya en el modelo): " + ", ".join(registered))
    kind, listed = model_units(repo)
    if kind is None:
        print("AGENTS.md sin ## Estructura: escríbela con estos candidatos y las respuestas del usuario")
        return 0
    if kind == "repos relacionados":
        print("AGENTS.md tiene ### Repos relacionados (formato anterior): pasa sus filas a ## Estructura")
    print("En el modelo (%s): %s" % (kind, ", ".join(ident for ident, _ in listed) or "sin filas"))
    sources = {source for _, source in listed}
    warnings = 0
    for ident, source in listed:
        if not exists(repo / source):
            warnings += 1
            print("  ⚠ %s: la fuente %s no existe en disco (¿sin clonar o ruta equivocada?)" % (ident, source))
    found = set(modules) | {os.path.join("..", name) for name in refs}
    missing = sorted(path for path in found if not covered(path, sources))
    if missing:
        print("  Candidatos que no están en el modelo: " + ", ".join(missing))
    # Las carpetas de feature se comparan solo si el modelo ya usa carpetas de feature como unidades.
    lost = [f for f in features if not covered(f, sources)] if any(norm(f) in sources for f in features) else []
    if lost:
        print("  Carpetas de feature que no están en el modelo: " + ", ".join(lost))
    if not (warnings or missing or lost):
        print("  ✔ El modelo cubre todos los candidatos")
    return 0


def worktree_links(repo, names):
    """En un worktree enlazado: lo del contexto que el worktree principal tiene y este no (los enlaces y los archivos
    locales no están en git, así que un worktree nuevo no los trae). [(nombre, "enlace" | "archivo local", destino)]."""
    git_dir = git(repo, "rev-parse", "--absolute-git-dir").stdout.strip()
    common = git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    if not git_dir or not common:
        return None, []
    common_path = pathlib.Path(common) if os.path.isabs(common) else repo / common
    if os.path.realpath(git_dir) == os.path.realpath(str(common_path)):
        return None, []
    main = None
    for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            main = pathlib.Path(line[len("worktree "):])
            break
    if main is None or os.path.realpath(str(main)) == os.path.realpath(str(repo)):
        return None, []
    missing = []
    for name in names:
        there = main / name
        if exists(repo / name) or not exists(there):
            continue
        missing.append((name, "enlace" if there.is_symlink() else "archivo local", os.path.realpath(str(there))))
    return main, missing


def local_ai_files(repo):
    """S4: los archivos locales de herramientas de IA sin versionar y sin ignorar, como línea de .git/info/exclude
    (una carpeta de aider, entera)."""
    out = []
    for path in git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines():
        found = LOCAL_AI.match(path)
        if not found:
            continue
        if found.group(1) and path != found.group(1) and not path.endswith(found.group(1)):
            head = path[:path.index(found.group(1)) + len(found.group(1))]
            line = "/" + head + "/"
        else:
            line = "/" + path
        if line not in out:
            out.append(line)
    return out


def exclude_local_ai(repo):
    """S4: agrega a .git/info/exclude (local, no toca .gitignore) los archivos locales de herramientas de IA."""
    return [line for line in local_ai_files(repo) if add_exclude(repo, line)]


def perf_section(text):
    """(inicio, fin) de la sección de rendimiento de un AGENTS.md (la primera), o None."""
    lines = text.splitlines(True)
    position, start, level = 0, None, None
    for line in lines:
        heading = ANY_HEADING.match(line)
        if start is None:
            own = PERF_HEADING.match(line)
            if own:
                start, level = position + len(line), len(own.group(1))
        elif heading and len(heading.group(1)) <= level:
            return start, position
        position += len(line)
    return (start, len(text)) if start is not None else None


def with_section(repo, folder, has, owner):
    """(ruta, texto) del AGENTS.md si tiene la sección; si no, (ruta, texto de la sección) de la primera fuente previa
    donde esa sección es de la skill `owner`, con el mismo criterio que `fuentes` y `verificar`; (None, "") si ninguna."""
    agents = repo / "AGENTS.md"
    text = read_text(agents) if is_file(agents) else ""
    if text and has(text):
        return "AGENTS.md", text
    for source in previous_sources(repo, folder)[0]:
        if source["kind"] == "actual":
            continue
        for skill, _, section in owned_sections(source["text"], source["kind"] not in LOOSE):
            if skill == owner:
                return source["path"], section
    return None, ""


def perf_audit(repo, text=None):
    """S3: lo que hb-setup señala de la sección de rendimiento, sin reescribirla: [(línea, propuesta)] de las líneas
    fuera del bloque de estado que traen un serial de dispositivo o que contradicen el estado del bloque."""
    if text is None:
        path = repo / "AGENTS.md"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    section = perf_section(text) if text else None
    if section is None:
        return None, []
    body = text[section[0]:section[1]]
    block = re.search(re.escape(PERF_BLOCK[0]) + r".*?" + re.escape(PERF_BLOCK[1]), body, re.S)
    in_patch = bool(block and re.search(r"setup\s*:\s*en\s+parche", block.group(0), re.I))
    outside = body[:block.start()] + body[block.end():] if block else body
    found = []
    for line in outside.splitlines():
        fixed = line
        for pattern, value in SERIALS:
            fixed = pattern.sub(value, fixed)
        if fixed != line:
            found.append((line.strip(), "sin el serial del dispositivo: «%s» (el serial va en el plan de cada "
                                        "investigación)" % fixed.strip()))
        if in_patch and re.search(r"setup\s+listo", line, re.I):
            found.append((line.strip(), "quitarla: el setup está en un parche y su estado lo dice el bloque de "
                                        "hb-performance"))
    return block.group(0) if block else "", found


def performance(args):
    """S3: muestra el bloque de estado de hb-performance (para conservarlo tal cual al regenerar AGENTS.md) y las líneas
    de la sección de rendimiento que conviene cambiar, con la propuesta. No escribe nada."""
    repo = toplevel(args.repo)
    where, text = with_section(repo, args.carpeta.strip("/"), lambda text: perf_section(text) is not None,
                               "hb-performance")
    if where is None:
        print("AGENTS.md no tiene sección de rendimiento: no hay nada de hb-performance que conservar")
        return 0
    block, found = perf_audit(repo, text)
    if where != "AGENTS.md":
        print("La sección de rendimiento está en `%s` (fuente previa): llévala al AGENTS.md nuevo tal cual, con su "
              "título, su contenido y el bloque" % where)
    if block:
        print("Bloque de estado de hb-performance (consérvalo tal cual al regenerar AGENTS.md):")
        print("\n".join("  " + line for line in block.splitlines()))
    else:
        print("La sección de rendimiento no tiene el bloque de estado de hb-performance (lo agrega perf.py)")
    if not found:
        print("✔ La sección de rendimiento no trae seriales ni líneas que contradigan el bloque")
        return 0
    print("Para el resumen (propón el cambio; no reescribas la sección por tu cuenta):")
    for line, proposal in found:
        print("  - «%s» → %s" % (line[:120], proposal))
    return 0


def product_section(text):
    """La carpeta de producto de la sección `## Producto` de un AGENTS.md: (carpeta, tiene línea `Carpeta:`), o None
    si no hay sección. Sin la línea, la carpeta es la de hb-product por defecto (product)."""
    section = PRODUCT_SECTION.search(text)
    if not section:
        return None
    line = PRODUCT_FOLDER.search(section.group(1))
    return (line.group(1).strip(), True) if line else (PRODUCT_DEFAULT, False)


def product(args):
    """La sección `## Producto` de hb-product: se conserva tal cual al migrar AGENTS.md, y su PRD va como fila de
    "Documentos" en ## Estructura. No escribe nada; sin la sección no propone crearla."""
    repo = toplevel(args.repo)
    where, text = with_section(repo, args.carpeta.strip("/"), lambda text: product_section(text) is not None,
                               "hb-product")
    found = product_section(text) if where else None
    if where not in (None, "AGENTS.md"):
        print("`## Producto` está en `%s` (fuente previa): va al AGENTS.md nuevo tal cual" % where)
    if found is None:
        print("AGENTS.md no tiene `## Producto`: no hay nada de hb-product que conservar ni fila que agregar "
              "(hb-setup no crea esa sección)")
        return 0
    folder, own = found
    print("`## Producto` es de hb-product: consérvala tal cual al migrar AGENTS.md, con su título y su contenido "
          "(hb-product lee de ahí su carpeta)")
    print("Carpeta de producto: `%s` (%s)" % (folder, "de la línea `Carpeta:`" if own
                                              else "por defecto: la sección no tiene línea `Carpeta:`"))
    if os.path.isabs(os.path.expanduser(folder)):
        print("⚠ Es una ruta de la máquina, y AGENTS.md no lleva rutas de la máquina. Para el resumen: propón cambiarla "
              "por una relativa a la raíz del proyecto (no reescribas la sección); mientras tanto, la fila del PRD no va "
              "en \"Documentos\"")
        return 0
    prd = os.path.normpath(os.path.join(folder, PRD_FILE)).replace(os.sep, "/")
    if (repo / prd).is_file():
        print("PRD: `%s` existe" % prd)
    else:
        print("PRD: `%s` todavía no existe (lo escribe la sesión 4 de hb-product); la fila va igual: solo se usa "
              "cuando hay funcionalidades `F-…`, y así no hace falta volver a correr hb-setup" % prd)
    print("Para ## Estructura, en ### Documentos (la fila tal cual):")
    print("  | `%s` | Vayas a implementar una funcionalidad `F-…` del producto o a cambiar su alcance |" % prd)
    return 0


# ── Fuentes previas de contexto de IA: fuentes y verificar ───────────────────────────────────────────────────────────
# Todo contexto de IA que ya tenga el proyecto, aunque no exista AGENTS.md. Si hay alguna, el camino es migrar: cada
# sección termina en AGENTS.md, en un doc con su fila en "Documentos" o descartada con motivo. Nada se pierde en silencio.
# Copias de AGENTS.md o CLAUDE.md: AGENTS-old.md, AGENTS.bak.md, AGENTS.v1.md, AGENTS-2024-05-01.md, AGENTS copy.md,
# AGENTS.md.orig, AGENTS.md~. Un nombre con otra palabra (claude-api.md, AGENTS.override.md) no es una copia.
COPY_WORD = (r"(?:old|bak|backup|orig|original|prev|previo|previous|viejo|vieja|antiguo|antigua|anterior|copia|copy|"
             r"save|saved|respaldo|v\d+(?:[._]\d+)*|\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d+)")
RENAMED = re.compile(r"^(?:agents|claude)(?:\.md)?(?:[-_. ]+" + COPY_WORD + r")+(?:\.md)?~?$|^(?:agents|claude)\.md~$",
                     re.I)
# Instrucciones de otros agentes: (ruta desde la raíz, qué es)
OTHER_AGENTS = ((r"\.github/copilot-instructions\.md", "instrucciones de GitHub Copilot"),
                (r"\.github/instructions/(?:.+/)?[^/]+\.instructions\.md", "instrucciones de GitHub Copilot por ruta"),
                (r"\.cursorrules", "reglas de Cursor"),
                (r"\.cursor/rules/(?:.+/)?[^/]+\.mdc?", "reglas de Cursor"),
                (r"GEMINI\.md", "instrucciones de Gemini CLI"),
                (r"\.junie/guidelines\.md", "guías de Junie"),
                (r"\.windsurfrules", "reglas de Windsurf"),
                (r"\.windsurf/rules/(?:.+/)?[^/]+\.md", "reglas de Windsurf"),
                (r"\.clinerules", "reglas de Cline"),
                (r"\.clinerules/(?:.+/)?[^/]+\.md", "reglas de Cline"))
AGENT_FILES = (".github/copilot-instructions.md", ".cursorrules", "GEMINI.md", ".junie/guidelines.md", ".windsurfrules",
               ".clinerules")
AGENT_DIRS = (".github/instructions", ".cursor/rules", ".windsurf/rules", ".clinerules")
CLAUDE_FILES = ("CLAUDE.md", ".claude/CLAUDE.md")
# Skills, comandos y prompts del proyecto: no son fuentes que se reemplazan, pero pueden solaparse con una skill hb-*
LOCAL_SKILLS = (".claude/skills/*/SKILL.md", ".agents/skills/*/SKILL.md", ".claude/commands/**/*.md",
                ".github/prompts/*.prompt.md")
IMPORT_ONLY = re.compile(r"^\s*@\.?/?AGENTS\.md\s*$", re.I)
# Subcarpetas que son salidas de las skills o del build, no instrucciones
CONTEXT_SKIP = {"reports", "modules", "implementation", "performance", "perf", "review", "product", "node_modules",
                ".git", "build", "dist", "out", "target", "vendor"}
AGENT_WORDS = re.compile(r"(?i)\b(?:agentes?|agents?|llms?|claude|copilot|cursor|gemini|codex|junie|windsurf|"
                         r"asistentes?|assistants?|prompts?|skills?|ia|ai)\b")
INSTRUCTION_NAME = re.compile(r"(?i)reglas|rules|instruc|guidelines|convenc|convention|protocol|plantilla|template|"
                              r"checklist|playbook|prompt|skill")
# Las líneas que dicen dónde escriben otras skills: lo de ahí son salidas, no fuentes
OUTPUT_LINE = re.compile(r"(?im)^[\s*-]*\**Carpeta de (?:reportes|investigaciones):?\**:?\s*`?([^`\n]+?)`?\s*$")
NOT_IN_DOCUMENTS = ("renombrada", "agente", "claude")  # "Documentos" nunca las referencia
DELETED_BY_DEFAULT = ("renombrada",)  # se propone borrarlas después de migrar
POINTERS = ("agente", "claude")  # quedan como puntero a AGENTS.md (esa herramienta las sigue leyendo)
INVENTORIED = ("actual", "renombrada", "agente", "claude", "carpeta")  # cada sección suya va al inventario
LOOSE = ("actual", "renombrada")  # su ## Rendimiento y su ## Producto son de hb-performance y hb-product, como en AGENTS.md
KINDS = {"actual": "se reescribe en su lugar: antes, guarda una copia fuera del repo",
         "renombrada": "se reemplaza: por defecto, propón borrarla después de migrar",
         "agente": "su contenido pasa al estándar y el archivo queda como puntero a AGENTS.md (esa herramienta lo sigue "
                   "leyendo): no lo borres",
         "claude": "queda con `@AGENTS.md` y solo lo propio de Claude Code",
         "carpeta": "se traspasa o se queda como doc con su fila en \"Documentos\""}
LONG_SECTION = 40
AGENTS_TARGET = 150
HEADING = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t#]*$")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
HB_BLOCK = re.compile(r"<!--[ \t]*(hb-[a-z0-9-]+:[a-z0-9-]+)[ \t]*-->.*?<!--[ \t]*/\1[ \t]*-->", re.S)
WHOLE_FILE = "(todo el archivo)"
PLACEHOLDER = re.compile(r"<[^<>\n]+>")
# Palabras del título de una sección → la sección del estándar donde suele ir
STANDARD = ((r"\b(?:stack|tecnologias?|tech|dependencias)\b", "## Stack"),
            (r"\b(?:comandos?|commands?)\b", "## Comandos"),
            (r"\bdod\b|definition of done|definicion de hecho|antes de (?:terminar|dar)", "## DoD"),
            (r"\b(?:arquitectura|architecture|capas|layers)\b", "## Arquitectura"),
            (r"\b(?:estructura|structure|unidades|units|modulos|modules|repos relacionados|repos vecinos)\b",
             "## Estructura"),
            (r"\b(?:modernizacion|migracion|migraciones|migrations?)\b", "## Modernización"),
            (r"\b(?:reglas|rules|convenciones|conventions|normas|lineamientos|guidelines|excepciones)\b",
             "## Reglas del proyecto"),
            (r"\b(?:git|commits?|ramas|branches|branching)\b", "## Git"),
            (r"\b(?:versionado|versiones|version|releases?|publicacion|publicar|changelog|despliegue|deploy)\b",
             "## Versionado y release"),
            (r"\b(?:seguridad|security|secretos|secrets|sensibles|privacidad)\b", "## Seguridad"))
# Temas que suelen ir a un doc propio: (palabras del título, nombre del doc o None para tomarlo del título)
DOC_TOPICS = ((r"\b(?:errores|errors?|troubleshooting|problemas|fallos|faq|solucion de problemas)\b", "troubleshooting"),
              (r"\b(?:sincronizacion|sincronizar|sync|bootstrap|workspace|espacio de trabajo)\b", "sincronizacion"),
              (r"\b(?:deep ?links?|rutas|routes|endpoints|urls?|catalogo|catalog)\b", None))
# Lo que ya cubre una skill hb-*: (skill, tema, palabras)
OVERLAPS = (("hb-implement", "bugfix", r"\b(?:bugs?|bugfix\w*|fix|fixes|hotfix\w*|corregir|correccion\w*|incidencias?)\b"),
            ("hb-implement", "reporte de cambios", r"\b(?:reportes?|reports?|informes?)\b"),
            ("hb-implement", "implementación", r"\b(?:implementa\w*|implement\w*|features?|funcionalidad\w*)\b"),
            ("hb-review", "code review", r"\b(?:review\w*|revision\w*|revisa\w*)\b"),
            ("hb-commit", "commits y PR", r"\b(?:commits?|pull requests?|prs?|merge requests?)\b"),
            ("hb-release", "release y changelog", r"\b(?:releases?|changelog|publicar)\b"),
            ("hb-performance", "rendimiento", r"\b(?:performance|rendimiento|jank)\b"))
PROTOCOL = re.compile(r"\b(?:protocol\w*|plantilla\w*|templates?|checklists?|playbooks?|flujos?|workflows?|procesos?|"
                      r"process\w*|pasos|steps|guias?|guides?|skills?|prompts?)\b")
# Líneas de ## Reglas del proyecto y ## Modernización que escribe el setup (no son reglas propias del proyecto)
STANDARD_RULES = re.compile(r"^(?:contexto de ia|carpeta de reportes|carpeta de investigaciones|ninguna decidida|"
                            r"los agentes no migran)")
RULE_TITLES = re.compile(r"\b(?:reglas|rules|convenciones|conventions|normas|excepciones|exceptions|modernizacion|"
                         r"migracion|migraciones|decisiones)\b")


def is_file(path):
    """Si la ruta es un archivo; una carpeta sin permiso de lectura cuenta como que no lo es (en Python 3.8,
    pathlib.is_file lanza el error)."""
    try:
        return path.is_file()
    except OSError:
        return False


def next_fence(fence, line):
    """(bloque de código abierto después de la línea, si la línea abre o cierra un bloque). El cierre usa el mismo
    carácter, al menos tan largo y sin texto después, como en CommonMark."""
    mark = FENCE.match(line)
    if not mark:
        return fence, False
    run, rest = mark.group(1), mark.group(2)
    if fence is None:
        return (fence, False) if run[0] == "`" and "`" in rest else (run, True)
    if run[0] == fence[0] and len(run) >= len(fence) and not rest.strip():
        return None, True
    return fence, False


def plain(text):
    """Texto para comparar: sin acentos, sin adornos de Markdown, en minúsculas y con los espacios juntos."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[`*]", "", text).replace(" > ", " › ")
    return re.sub(r"\s+", " ", text).strip().lower()


def words(text):
    """Texto para buscar palabras: plano y con guiones, barras y puntos como espacios (protocolo-bugfix → protocolo
    bugfix)."""
    return re.sub(r"[-_/.]+", " ", plain(text))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", plain(text)).strip("-") or "doc"


def rel(repo, path):
    return os.path.relpath(str(path), str(repo)).replace(os.sep, "/")


def line_count(text):
    return text.count("\n") + (0 if not text or text.endswith("\n") else 1)


def frontmatter(text):
    """Los campos de un frontmatter YAML simple ({campo: valor}) y la línea donde termina (0 si no hay)."""
    match = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.S)
    if not match:
        return {}, 0
    found = {}
    for line in match.group(1).splitlines():
        pair = re.match(r"^([A-Za-z_-]+):[ \t]*(.*)$", line)
        if pair:
            found[pair.group(1).lower()] = pair.group(2).strip().strip("'\"")
    return found, match.group(0).count("\n")


def headings(text):
    """Los títulos de un Markdown fuera de los bloques de código y del frontmatter: [(índice de línea, nivel, título)]."""
    found, fence = [], None
    skip = frontmatter(text)[1]
    for index, line in enumerate(text.splitlines()):
        if index < skip:
            continue
        fence, marked = next_fence(fence, line)
        heading = HEADING.match(line) if fence is None and not marked else None
        if heading:
            found.append((index, len(heading.group(1)), heading.group(2).strip()))
    return found


def sections(text):
    """Las secciones de un Markdown para el inventario, con líneas desde 1: [{"label", "title", "start", "end",
    "parts"}]. Primero "(inicio)", lo que hay antes de la primera sección si tiene algo más que el título del documento.
    Un archivo sin secciones es una sola: "(todo el archivo)". "parts" son el "(inicio)" de la sección y sus
    subsecciones: en el inventario va entera o por partes."""
    lines = text.splitlines()
    marks = headings(text)
    if not any(line.strip() for line in lines):
        return []
    top = 2 if any(level == 2 for _, level, _ in marks) else 1
    first = next((index for index, level, _ in marks if level == 2), None) if top == 2 else None
    titles = {index for index, level, _ in marks if top == 2 and level == 1 and index < first}
    cuts = [mark for mark in marks if mark[1] <= top and mark[0] not in titles]
    if not cuts:
        return [{"label": WHOLE_FILE, "title": WHOLE_FILE, "start": 1, "end": len(lines), "parts": []}]
    out, counts = [], {}

    def label(title, seen):
        seen[title] = seen.get(title, 0) + 1
        return title if seen[title] == 1 else "%s (%d)" % (title, seen[title])

    if any(line.strip() for index, line in enumerate(lines[:cuts[0][0]]) if index not in titles):
        out.append({"label": "(inicio)", "title": "(inicio)", "start": 1, "end": cuts[0][0], "parts": []})
    for position, (index, level, title) in enumerate(cuts):
        end = cuts[position + 1][0] if position + 1 < len(cuts) else len(lines)
        while end > index + 1 and not lines[end - 1].strip():
            end -= 1
        name = label(title, counts)
        subs = [mark for mark in marks if index < mark[0] < end and mark[1] == level + 1]
        parts, sub_counts = [], {}
        if subs:
            if any(line.strip() for line in lines[index + 1:subs[0][0]]):
                parts.append({"label": name + " › (inicio)", "title": title, "start": index + 1, "end": subs[0][0]})
            for number, (sub_index, _, sub_title) in enumerate(subs):
                sub_end = subs[number + 1][0] if number + 1 < len(subs) else end
                parts.append({"label": name + " › " + label(sub_title, sub_counts), "title": sub_title,
                              "start": sub_index + 1, "end": sub_end})
        out.append({"label": name, "title": title, "start": index + 1, "end": end, "parts": parts})
    return out


def body(text, item):
    return "\n".join(text.splitlines()[item["start"] - 1:item["end"]])


def hb_blocks(text):
    """Los bloques que mantiene otra skill (<!-- hb-<skill>:<nombre> --> … <!-- /hb-<skill>:<nombre> -->):
    [(clave, texto exacto, línea)]."""
    return [(found.group(1), found.group(0), text.count("\n", 0, found.start()) + 1) for found in HB_BLOCK.finditer(text)]


def owned_sections(text, strict=False):
    """Las secciones propias de otras skills: [(skill, título, texto de la sección con su título)]. En AGENTS.md y sus
    copias, la primera sección de rendimiento (como la busca perf.py) es de hb-performance y `## Producto…` es de
    hb-product. En las demás fuentes (strict), una sección de rendimiento es de hb-performance solo si trae su bloque, y
    ninguna es de hb-product: esas skills solo escriben en AGENTS.md."""
    lines, marks, found = text.splitlines(), headings(text), []
    for position, (index, level, title) in enumerate(marks):
        end = next((other for other, other_level, _ in marks[position + 1:] if other_level <= level), len(lines))
        section = "\n".join(lines[index:end])
        owners = [skill for skill, _, _ in found]
        if "hb-performance" not in owners and PERF_HEADING.match(lines[index]) and \
                (not strict or PERF_BLOCK[0] in section):
            found.append(("hb-performance", title, section))
        elif "hb-product" not in owners and not strict and level == 2 and title.startswith("Producto"):
            found.append(("hb-product", title, section))
    return found


def same_text(one, other):
    """Igual salvo los espacios al final de cada línea y las líneas en blanco del principio y del final."""
    def clean(text):
        return "\n".join(line.rstrip() for line in text.strip("\n").splitlines()).strip("\n")
    return clean(one) == clean(other)


def overlaps(text):
    """Las skills hb-* que ya cubren lo que dice un texto (nombre, descripción o título): [(skill, tema)]."""
    found, text = [], words(text)
    for skill, topic, pattern in OVERLAPS:
        if re.search(pattern, text) and (skill, topic) not in found:
            found.append((skill, topic))
    return found


def protocol_overlaps(path, text, invocable=False):
    """Si un archivo es un protocolo, una plantilla, una skill, un comando o un prompt, las skills hb-* con las que se
    solapa, por su nombre, su descripción y su título; si no, []."""
    fields, _ = frontmatter(text)
    name = pathlib.PurePosixPath(path)
    stem = name.parent.name if name.name.upper() == "SKILL.MD" else re.sub(r"(?:\.prompt)?\.md$", "", name.name)
    first = next((title for _, _, title in headings(text)), "")
    if not (invocable or fields.get("description") or PROTOCOL.search(words(stem))):
        return []
    return overlaps(" ".join((stem, fields.get("name", ""), fields.get("description", ""), first)))


def only_pointer(text):
    """Si el archivo solo remite a AGENTS.md (un import, o hasta tres líneas que lo nombran): ya no es una fuente."""
    lines = [line for line in text.splitlines()[frontmatter(text)[1]:] if line.strip()]
    return all(IMPORT_ONLY.match(line) for line in lines) or (len(lines) <= 3 and
                                                             all("AGENTS.md" in line for line in lines))


def doc_path(cell):
    """La ruta de una celda de "Documentos": entre acentos graves, el destino de un enlace o la celda tal cual."""
    if "`" in cell:
        return bare(cell)
    link = re.search(r"\]\(([^)\s]+)\)", cell)
    return link.group(1) if link else cell.strip()


def documented(text):
    """Las filas de "Documentos" de ## Estructura: [[ruta, léelo cuando…]]."""
    structure = section_text(text, "Estructura", 2)
    block = section_text(structure, "Documentos", 3) if structure is not None else None
    return table_rows(block) if block else []


def source_kind(path, folder):
    """El tipo de fuente de una ruta del repo (actual, claude, agente o renombrada) con qué es, o (None, None)."""
    name = pathlib.PurePosixPath(path)
    if path == "AGENTS.md":
        return "actual", "el AGENTS.md actual"
    if path in CLAUDE_FILES:
        return "claude", "instrucciones de Claude Code"
    for pattern, what in OTHER_AGENTS:
        if re.fullmatch(pattern, path):
            return "agente", what
    inside = path.startswith(folder + "/")
    if RENAMED.match(name.name) and (str(name.parent) in (".", "docs", ".claude") or inside):
        return "renombrada", "copia de %s" % ("AGENTS.md" if name.name.lower().startswith("a") else "CLAUDE.md")
    if inside and name.name.upper() in ("AGENTS.MD", "CLAUDE.MD"):  # el de la carpeta de contexto no es el que se usa
        return "renombrada", "copia de %s en la carpeta de contexto" % name.name
    return None, None


def output_folders(repo, texts):
    """Las rutas reales de las carpetas donde escriben otras skills (Carpeta de reportes, Carpeta de investigaciones y la
    Carpeta de ## Producto), según los textos dados: lo de ahí son salidas, no fuentes."""
    found = set()
    for text in texts:
        for value in OUTPUT_LINE.findall(text):
            found.add(fixed_part(value.strip()))
        product = product_section(text)
        if product:
            found.add(product[0])
    real = set()
    for value in found:
        if value:
            path = pathlib.Path(os.path.expanduser(value))
            real.add(os.path.realpath(str(path if path.is_absolute() else repo / path)))
    return real


def context_folders(repo, folder):
    """La carpeta de contexto y las que pueden serlo con otro nombre: las carpetas de la raíz que son enlaces
    simbólicos o que .git/info/exclude deja fuera de git."""
    names, excluded = [folder], set()
    try:
        for line in read_text(exclude_file(repo)).splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "!")) and "*" not in line and "/" not in line.strip("/"):
                excluded.add(line.strip("/"))
    except RuntimeError:
        pass
    try:
        entries = sorted(repo.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if entry.name in names or entry.name.startswith(".") or entry.name in CONTEXT_SKIP:
            continue
        if is_directory(entry) and (entry.is_symlink() or entry.name in excluded):
            names.append(entry.name)
    return names


def previous_sources(repo, folder, extra=None):
    """El contexto de IA que ya tiene el proyecto: (fuentes, otros .md de las carpetas de contexto, skills locales).
    Cada una es {"path", "kind", "what", "text"}; kind: actual, renombrada, claude, agente o carpeta. Solo lee."""
    found, others, local, seen, candidates = [], [], [], set(), []

    def add(path, kind, what, bucket):
        key = os.path.realpath(str(path))
        if key in seen or not is_file(path):
            return
        seen.add(key)
        label = rel(repo, path) if not os.path.relpath(str(path), str(repo)).startswith("..") else str(path)
        bucket.append({"path": label, "kind": kind, "what": what, "text": read_text(path)})

    agents = repo / "AGENTS.md"
    if is_file(agents) and read_text(agents).strip():
        add(agents, "actual", "el AGENTS.md actual", found)
    for parent in (repo, repo / "docs", repo / ".claude"):
        try:
            children = sorted(parent.iterdir()) if is_directory(parent) else []
        except OSError:
            children = []
        for child in children:
            kind, what = source_kind(rel(repo, child), folder)
            if kind == "renombrada":
                add(child, kind, what, found)
    for name in CLAUDE_FILES + AGENT_FILES:
        path = repo / name
        if is_file(path) and not only_pointer(read_text(path)):
            kind, what = source_kind(name, folder)
            add(path, kind, what, found)
    for directory in AGENT_DIRS:
        if not is_directory(repo / directory):
            continue
        for top, dirs, files in os.walk(str(repo / directory)):
            dirs.sort()
            for name in sorted(files):
                path = pathlib.Path(top) / name
                kind, what = source_kind(rel(repo, path), folder)
                if kind == "agente" and not only_pointer(read_text(path)):
                    add(path, kind, what, found)
    for name in context_folders(repo, folder):
        base = repo / name
        if not is_directory(base):
            continue
        for top, dirs, files in os.walk(str(base), followlinks=True):
            depth = len(pathlib.Path(top).relative_to(base).parts)
            dirs[:] = [] if depth >= 4 else sorted(d for d in dirs if d not in CONTEXT_SKIP and not d.startswith("."))
            for file in sorted(files):
                path = pathlib.Path(top) / file
                kind, what = source_kind(rel(repo, path), name)
                if kind == "renombrada":
                    add(path, kind, what, found)
                elif file.lower().endswith(".md"):
                    candidates.append(path)
    texts = [source["text"] for source in found if source["kind"] in LOOSE]
    skipped = output_folders(repo, texts)
    listed = {norm(doc_path(row[0])) for row in documented(read_text(agents)) if row} if is_file(agents) else set()
    for path in candidates:
        real = os.path.realpath(str(path))
        if any(real == out or real.startswith(out + os.sep) for out in skipped) or norm(rel(repo, path)) in listed:
            continue
        text = read_text(path)
        instructions = (INSTRUCTION_NAME.search(path.name) or frontmatter(text)[0].get("description")
                        or len(AGENT_WORDS.findall(text)) >= 2)
        if instructions:
            add(path, "carpeta", "de la carpeta de contexto, con instrucciones para agentes", found)
        else:
            add(path, "otro", "de la carpeta de contexto", others)
    for path in extra or []:
        source = pathlib.Path(os.path.expanduser(path))
        if not is_file(source):
            raise ValueError("--fuente %s no es un archivo" % path)
        add(source if source.is_absolute() else pathlib.Path(os.path.abspath(str(source))), "carpeta",
            "fuente indicada con --fuente", found)
    for pattern in LOCAL_SKILLS:
        for match in sorted(glob.glob(str(repo / pattern), recursive=True)):
            path = pathlib.Path(match)
            if not any(part.startswith("hb-") for part in path.relative_to(repo).parts):
                add(path, "skill", "skill, comando o prompt del proyecto", local)
    return found, others, local


def suggest(item, text, strict=False):
    """El destino sugerido de una sección (el agente decide): AGENTS.md, un doc o descartada."""
    title, size = item["title"], item["end"] - item["start"] + 1
    content = body(text, item)
    blocks = [key for key, _, _ in hb_blocks(content)]
    owner = [skill for skill, _, _ in owned_sections(content, strict)]
    if owner or blocks:
        return "AGENTS.md, tal cual (es de %s)" % ", ".join(owner + [key for key in blocks
                                                                       if key.split(":")[0] not in owner])
    if title == "(inicio)":
        return "AGENTS.md: el título y la descripción"
    if title == WHOLE_FILE:
        return "AGENTS.md o doc: decide (o descartada con motivo)"
    name = words(title)
    for pattern, doc in DOC_TOPICS:
        if re.search(pattern, name):
            return "doc: `<docs>/%s.md`, con su fila en \"Documentos\"" % (doc or slug(title))
    if PROTOCOL.search(name):
        covered = overlaps(title)
        if covered:
            return "descartada si ya la cubre %s; lo propio del proyecto, a AGENTS.md o a un doc" % ", ".join(
                "`%s` (%s)" % pair for pair in covered)
    for pattern, section in STANDARD:
        if re.search(pattern, name):
            if size > LONG_SECTION:
                return "AGENTS.md › %s, lo esencial, y el resto a `<docs>/%s.md`: decide" % (section, slug(title))
            return "AGENTS.md › %s" % section
    if size > LONG_SECTION:
        return "doc: `<docs>/%s.md` (es extensa: %d líneas)" % (slug(title), size)
    return "AGENTS.md o doc: decide (o descartada con motivo)"


def inventory_items(source):
    """Las filas del inventario de una fuente: [(etiqueta, sección o parte)]. Una sección larga con subsecciones va por
    partes; las demás, enteras."""
    items = []
    for item in sections(source["text"]):
        if item["parts"] and item["end"] - item["start"] + 1 > LONG_SECTION:
            items.extend((part["label"], part) for part in item["parts"])
        else:
            items.append((item["label"], item))
    return items


def sources_command(args):
    """Las fuentes previas de contexto de IA y el inventario de traspaso sugerido. No escribe nada."""
    repo = toplevel(args.repo)
    folder = args.carpeta.strip("/")
    found, others, local = previous_sources(repo, folder, args.fuente)
    if not found:
        print("Fuentes previas de contexto de IA: ninguna")
        print("Camino: plantilla (crea AGENTS.md desde assets/AGENTS.template.md)")
    else:
        print("Fuentes previas de contexto de IA: %d" % len(found))
        print("Camino: migrar%s: cada sección termina en AGENTS.md, en un doc con su fila en \"Documentos\" o descartada "
              "con motivo. Nada se pierde en silencio." % ("" if any(s["kind"] == "actual" for s in found)
                                                           else ", aunque no exista AGENTS.md"))
        for source in found:
            print("  - %s (%s, %d líneas): %s" % (source["path"], source["what"], line_count(source["text"]),
                                                  KINDS[source["kind"]]))
        rewritten = [source["path"] for source in found if source["kind"] in ("actual",) + POINTERS]
        if rewritten:
            print("  Antes de reescribir %s, guarda una copia de cada uno fuera del repo y pásala a `verificar` con "
                  "`--previo <ruta>=<copia>` (si está en git y cambió, verificar usa la de HEAD). Los punteros a "
                  "AGENTS.md, mejor después de verificar." % ", ".join(rewritten))
    kept = [(source["path"], key, line) for source in found for key, _, line in hb_blocks(source["text"])]
    owned = [(source["path"], skill, title) for source in found
             for skill, title, _ in owned_sections(source["text"], source["kind"] not in LOOSE)]
    if kept or owned:
        print("De otras skills (van al AGENTS.md nuevo tal cual, con su título y su contenido):")
        for path, key, line in kept:
            print("  - %s: bloque <!-- %s --> (línea %d)" % (path, key, line))
        for path, skill, title in owned:
            command = "rendimiento" if skill == "hb-performance" else "producto"
            print("  - %s: ## %s (%s; corre `contexto.py %s`)" % (path, title, skill, command))
    shared = [(source, protocol_overlaps(source["path"], source["text"], source["kind"] == "skill"))
              for source in found + local]
    shared = [(source, covered) for source, covered in shared if covered]
    if shared:
        print("Se solapan con skills hb-* (dilo en el resumen: qué cubre ya la skill, qué es propio del proyecto —eso va "
              "a AGENTS.md o a docs— y propón retirarlas; no las borres):")
        for source, covered in shared:
            print("  - %s ↔ %s" % (source["path"], ", ".join("`%s` (%s)" % pair for pair in covered)))
    others_local = [source for source in local if not protocol_overlaps(source["path"], source["text"], True)]
    if others_local:
        print("Skills, comandos o prompts del proyecto sin solape con skills hb-* (no son fuentes: se quedan): "
              + ", ".join(source["path"] for source in others_local))
    if others:
        print("Otros .md de la carpeta de contexto (no parecen instrucciones para agentes; si alguno lo es, pásalo con "
              "--fuente): " + ", ".join(source["path"] for source in others))
    inventoried = [source for source in found if source["kind"] in INVENTORIED]
    if not inventoried:
        return 0
    print("Inventario de traspaso: completa Destino y Motivo, guárdalo fuera del repo y pásalo a `contexto.py verificar "
          "--inventario <archivo>`. Destino: AGENTS.md, la ruta real de un doc (con su fila en \"Documentos\") o "
          "descartada (con su motivo: obsoleta, contradice el código, ya la cubre un perfil hb-stack-* o una skill "
          "hb-*); lo propio de una herramienta puede quedar en su archivo (destino: su ruta). Ninguna fila puede quedar "
          "con \"decide\" ni con `<docs>`, que es la carpeta de docs del modo (la imprime `preparar`). Una fila \"%s\" "
          "cubre la fuente entera." % WHOLE_FILE)
    print("")
    print("| Fuente | Sección | Líneas | Destino | Motivo o \"Léelo cuando…\" |")
    print("| --- | --- | --- | --- | --- |")
    for source in inventoried:
        covered = protocol_overlaps(source["path"], source["text"]) if source["kind"] == "carpeta" else []
        if covered:  # un protocolo o una plantilla que ya cubre una skill hb-*: va entero
            print("| `%s` | %s | 1-%d | descartada si ya la cubre %s; lo propio del proyecto, a AGENTS.md o a un doc |  |"
                  % (source["path"], WHOLE_FILE, line_count(source["text"]),
                     ", ".join("`%s` (%s)" % pair for pair in covered)))
            continue
        for label, item in inventory_items(source):
            print("| `%s` | %s | %d-%d | %s |  |" % (source["path"], label.replace("|", "\\|"), item["start"],
                                                    item["end"], suggest(item, source["text"],
                                                                         source["kind"] not in LOOSE)))
    return 0


def explicit_previous(values):
    """{ruta: texto} de --previo: "<ruta>=<copia>", o solo "<copia>" para AGENTS.md."""
    out = {}
    for value in values or []:
        path, copy = ("AGENTS.md", value)
        if "=" in value and not os.path.exists(os.path.expanduser(value)):
            path, copy = value.split("=", 1)
        file = pathlib.Path(os.path.expanduser(copy))
        if not is_file(file):
            raise ValueError("--previo %s: %s no es un archivo" % (value, copy))
        out[norm(path)] = read_text(file)
    return out


def head_versions(repo, folder):
    """Las fuentes previas versionadas que cambiaron o se borraron desde HEAD: {ruta: texto en HEAD}. AGENTS.md, si
    está en HEAD, siempre: es la fuente del inventario aunque todavía no se haya reescrito."""
    listing = git(repo, "ls-tree", "-r", "-z", "--name-only", "HEAD")
    out = {}
    if listing.returncode != 0:
        return out
    for path in listing.stdout.split("\0"):
        if not path or source_kind(path, folder)[0] is None:
            continue
        if path == "AGENTS.md" or git(repo, "diff", "--quiet", "HEAD", "--", path).returncode == 1:
            shown = git(repo, "show", "HEAD:" + path)
            if shown.returncode == 0:
                out[path] = shown.stdout
    return out


def inventory_rows(text):
    """Las filas de la tabla del inventario (la que tiene las columnas Fuente, Sección y Destino):
    [{"fuente", "seccion", "destino", "motivo"}]."""
    rows, columns = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            columns = None
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
        if columns is None:
            names = [plain(cell) for cell in cells]
            if any("fuente" in n for n in names) and any("destino" in n for n in names):
                columns = {key: next((i for i, n in enumerate(names) if word in n), None)
                           for key, word in (("fuente", "fuente"), ("seccion", "seccion"), ("destino", "destino"),
                                             ("motivo", "motivo"))}
                if columns["motivo"] is None:
                    columns["motivo"] = next((i for i, n in enumerate(names) if "leelo" in n), None)
            continue
        if all(re.match(r"^:?-+:?$", cell) for cell in cells if cell):
            continue

        def cell(key):
            index = columns.get(key)
            return cells[index].replace("\\|", "|").strip() if index is not None and index < len(cells) else ""

        rows.append({"fuente": cell("fuente"), "seccion": cell("seccion"), "destino": cell("destino"),
                     "motivo": cell("motivo")})
    return rows


def destination(value):
    """("agents" | "doc" | "descartada" | None, ruta del doc). Una sugerencia sin decidir ("decide" o un `<docs>` sin
    reemplazar) no es un destino."""
    text = plain(value)
    if not text or "decide" in text or PLACEHOLDER.search(value):
        return None, None
    if text.startswith("agents.md"):
        return "agents", None
    if text.startswith("descartad"):
        return "descartada", None
    quoted = re.search(r"`([^`]+)`", value)
    rest = re.sub(r"(?i)^doc:\s*", "", value.strip())
    path = quoted.group(1) if quoted else (rest.split()[0] if rest.split() else "")
    if "/" in path or path.endswith(".md") or re.fullmatch(r"\.?[\w.-]+", path):
        return "doc", norm(path)
    return None, None


def empty(value):
    return plain(value) in ("", "-", "—", "–", "n/a", "ninguno", "ninguna")


def has_heading(text, title):
    wanted = plain(re.sub(r" \(\d+\)$", "", title))
    return any(plain(found) == wanted for _, _, found in headings(text))


def verify(args):
    """Comprueba el traspaso a AGENTS.md. Errores (sale con 1): una sección de una fuente sin destino, una fuente del
    inventario que ya no está (reescrita sin copia), un doc sin su fila en "Documentos" o sin escribir, una descartada
    sin motivo, un bloque o una sección de otra skill que no quedó tal cual, o "Documentos" que referencia una fuente que
    se reemplaza. Avisos: reglas que no vienen de ninguna fuente previa, reglas de las fuentes que no quedaron tal cual y
    un AGENTS.md de 150 líneas o más. No escribe nada."""
    repo = toplevel(args.repo)
    folder = args.carpeta.strip("/")
    agents = repo / "AGENTS.md"
    if not is_file(agents):
        raise RuntimeError("no hay AGENTS.md que verificar: escríbelo antes (en la ruta que imprimió `preparar`)")
    new = read_text(agents)
    found, _, local = previous_sources(repo, folder, args.fuente)
    before = head_versions(repo, folder)
    before.update(explicit_previous(args.previo))
    sources = []
    for source in found:
        if source["kind"] == "actual":
            continue  # el AGENTS.md de ahora es el resultado: su versión de antes viene de --previo o de HEAD
        path = norm(source["path"])
        sources.append(dict(source, text=before.pop(path)) if path in before else source)
    for path, text in sorted(before.items(), key=lambda item: item[0] != "AGENTS.md"):
        kind, what = source_kind(path, folder)
        if text.strip() and not only_pointer(text):
            sources.insert(0 if kind == "actual" else len(sources),
                           {"path": path, "kind": kind or "carpeta", "what": (what or "fuente") + ", la de antes",
                            "text": text})
    errors, warnings = [], []
    new_plain = plain(new)

    # Bloques y secciones de otras skills: tal cual. Si el AGENTS.md de antes los tenía, mandan los suyos.
    blocks = {}
    for source in sources:
        for key, text, _ in hb_blocks(source["text"]):
            blocks.setdefault(key, []).append((source, text))
    for key, versions in sorted(blocks.items()):
        own = [text for source, text in versions if source["kind"] == "actual"]
        if not any(text in new for text in own or [text for _, text in versions]):
            where = ", ".join(sorted({"`%s`" % source["path"] for source, _ in versions}))
            errors.append("falta el bloque <!-- %s --> tal cual (está en %s): consérvalo sin cambios" % (key, where))
    owned = {}
    for source in sources:
        for skill, title, text in owned_sections(source["text"], source["kind"] not in LOOSE):
            owned.setdefault(skill, []).append((source, title, text))
    mine = {skill: text for skill, _, text in owned_sections(new)}
    for skill, versions in sorted(owned.items()):
        own = [text for source, _, text in versions if source["kind"] == "actual"]
        title = versions[0][1]
        where = ", ".join(sorted({"`%s`" % source["path"] for source, _, _ in versions}))
        if skill not in mine:
            errors.append("falta la sección ## %s de %s (está en %s): va tal cual, con su título y su contenido"
                          % (title, skill, where))
        elif not any(same_text(mine[skill], text) for text in own or [text for _, _, text in versions]):
            errors.append("## %s (de %s) no quedó tal cual (está en %s): consérvala sin cambios; lo que convenga "
                          "cambiar, propónlo en el resumen" % (title, skill, where))

    # "Documentos" nunca referencia una fuente que se reemplaza
    replaced = {norm(source["path"]): source for source in sources if source["kind"] in NOT_IN_DOCUMENTS}
    listed = {}
    for row in documented(new):
        if not row:
            continue
        path = norm(doc_path(row[0]))
        listed[path] = row[1] if len(row) > 1 else ""
        if path in replaced:
            errors.append("\"Documentos\" referencia `%s`, una fuente que se reemplaza: traspasa su contenido y quita "
                          "la fila" % replaced[path]["path"])
        elif empty(listed[path]) or PLACEHOLDER.fullmatch(listed[path].strip()):
            errors.append("la fila de `%s` en \"Documentos\" no dice cuándo leerlo" % path)
    for source in sources:
        name = pathlib.PurePosixPath(source["path"]).name
        if source["kind"] == "renombrada" and name in new:
            errors.append("AGENTS.md nombra `%s`, una fuente que se reemplaza: lo que sirva de ella va en AGENTS.md o en "
                          "un doc" % name)

    # El inventario: cada sección de cada fuente con su destino
    inventoried = [source for source in sources if source["kind"] in INVENTORIED]
    known_sources = sources + local
    destinations, rows = {}, []
    if args.inventario:
        text = sys.stdin.read() if args.inventario == "-" else read_text(pathlib.Path(os.path.expanduser(args.inventario)))
        rows = inventory_rows(text)
        if not rows:
            errors.append("el inventario no tiene la tabla con las columnas Fuente, Sección y Destino")
    elif inventoried:
        errors.append("falta el inventario de traspaso: pásalo con --inventario <archivo> (la tabla de "
                      "`contexto.py fuentes`, con Destino completo)")
    by_source = {}
    for row in rows:
        name = norm(bare(row["fuente"])) if row["fuente"] else ""
        match = [s for s in known_sources if norm(s["path"]) == name] or \
            [s for s in known_sources if pathlib.PurePosixPath(s["path"]).name == name]
        if len(match) != 1:
            errors.append("el inventario trae «%s», que no encuentro como fuente: si la reescribiste, pasa la copia de "
                          "antes con --previo %s=<copia> (si está en git, uso la de HEAD); si no la detecté, pásala con "
                          "--fuente" % (row["fuente"], bare(row["fuente"]) or "<ruta>"))
            continue
        by_source.setdefault(match[0]["path"], []).append(row)
    for source in known_sources if args.inventario else []:  # sin inventario ya hay un error que lo dice
        mine_rows = by_source.get(source["path"], [])
        labels = {plain(row["seccion"]): row for row in mine_rows}
        whole = labels.get(plain(WHOLE_FILE))
        items = sections(source["text"])
        known = {plain(WHOLE_FILE)}
        required = source["kind"] in INVENTORIED
        for item in items:
            known.add(plain(item["label"]))
            known.update(plain(part["label"]) for part in item["parts"])
            if whole is not None:
                destinations[(source["path"], item["label"])] = whole
                continue
            if plain(item["label"]) in labels:
                destinations[(source["path"], item["label"])] = labels[plain(item["label"])]
                continue
            missing = [part for part in item["parts"] if plain(part["label"]) not in labels]
            if item["parts"] and not missing:
                for part in item["parts"]:
                    destinations[(source["path"], part["label"])] = labels[plain(part["label"])]
                continue
            if required:
                pieces = ", ".join(part["label"] for part in missing) if item["parts"] else item["label"]
                errors.append("sin destino en el inventario: `%s` › %s (líneas %d-%d)" % (source["path"], pieces,
                                                                                         item["start"], item["end"]))
        for label in labels:
            if label not in known:
                warnings.append("fila del inventario con una sección que `%s` no tiene: «%s»" % (source["path"], label))
        for row in mine_rows:
            kind, path = destination(row["destino"])
            where = "`%s` › %s" % (source["path"], row["seccion"])
            part = section_of(source["text"], row["seccion"])
            own = [skill for skill, _, _ in owned_sections(part, source["kind"] not in LOOSE)] + \
                [key for key, _, _ in hb_blocks(part)]
            if kind == "doc" and path == norm(source["path"]) and source["kind"] in POINTERS:
                kind = "queda"  # lo propio de esa herramienta se queda en su archivo
            if kind is None:
                errors.append("%s: decide el destino (AGENTS.md, la ruta real de un doc o descartada); llegó «%s»"
                              % (where, row["destino"]))
            elif own and kind != "agents":
                errors.append("%s: es de %s y va en AGENTS.md tal cual" % (where, ", ".join(own)))
            elif kind == "descartada" and empty(row["motivo"]):
                errors.append("%s: descartada sin motivo" % where)
            elif kind == "queda":
                now = read_text(repo / source["path"])
                title = row["seccion"].split(" › ")[-1]
                if only_pointer(now) or (title not in ("(inicio)", WHOLE_FILE) and not has_heading(now, title)):
                    errors.append("%s: dice que se queda en `%s`, pero ese archivo ya no la tiene" % (where,
                                                                                                      source["path"]))
            elif kind == "doc":
                if path in replaced:
                    errors.append("%s: el destino es `%s`, la fuente que se reemplaza" % (where, path))
                elif path not in listed:
                    errors.append("%s: `%s` no tiene su fila en \"Documentos\"" % (where, path))
                if not exists(repo / path):
                    errors.append("%s: el doc `%s` no existe: escríbelo" % (where, path))

    # Nada inventado: las reglas propias vienen de las fuentes previas (o del usuario)
    everything = " ".join(plain(source["text"]) for source in sources)
    for title in ("Reglas del proyecto", "Modernización"):
        block = section_text(new, title, 2) or ""
        for line in block.splitlines():
            item = re.match(r"^[ \t]*[-*+][ \t]+(.+)$", line)
            if not item:
                continue
            rule = plain(item.group(1))
            if STANDARD_RULES.match(rule) or rule in everything:
                continue
            warnings.append("«%s» (## %s) no viene de ninguna fuente previa: si no la pidió el usuario, quítala "
                            "(hb-setup no agrega reglas propias del proyecto)" % (item.group(1).strip()[:100], title))
    for source in sources:
        for item in sections(source["text"]):
            for part in item["parts"] or [item]:
                if not (RULE_TITLES.search(words(part["title"])) or RULE_TITLES.search(words(item["title"]))):
                    continue
                row = destinations.get((source["path"], part["label"])) or destinations.get((source["path"],
                                                                                              item["label"]))
                kind, path = destination(row["destino"]) if row else ("agents", None)
                if kind in ("descartada", None):
                    continue
                if kind == "doc":  # un doc, o el archivo de esa herramienta si lo propio se queda ahí
                    target, shown = plain(read_text(repo / path)), "`%s`" % path
                else:
                    target, shown = new_plain, "AGENTS.md"
                for line in body(source["text"], part).splitlines():
                    rule = re.match(r"^[ \t]*[-*+][ \t]+(.+)$", line)
                    if rule and plain(rule.group(1)) not in target:
                        warnings.append("regla de `%s` › %s que no quedó tal cual en %s: «%s»" % (
                            source["path"], part["label"], shown, rule.group(1).strip()[:100]))
    lines = line_count(new)
    if lines >= AGENTS_TARGET:
        warnings.append("AGENTS.md tiene %d líneas (objetivo: menos de %d): lo que no entra va a docs referenciados en "
                        "\"Documentos\", nunca se omite" % (lines, AGENTS_TARGET))

    print("Fuentes previas verificadas: " + (", ".join("`%s`" % source["path"] for source in sources) or "ninguna"))
    for message in errors:
        print("  ✖ " + message)
    for message in warnings:
        print("  ⚠ " + message)
    if errors:
        print("✖ El traspaso no está completo: corrige lo marcado y vuelve a correr `contexto.py verificar`.")
        return 1
    print("✔ Nada se pierde: cada sección de las fuentes tiene destino, lo de otras skills quedó tal cual y "
          "\"Documentos\" no referencia ninguna fuente que se reemplaza.")
    gone = [source["path"] for source in sources if source["kind"] in DELETED_BY_DEFAULT and exists(repo /
                                                                                                    source["path"])]
    if gone:
        print("Pregunta si se conservan (por defecto, borrarlas después de migrar): " + ", ".join(gone) + ".")
    pointers = [source["path"] for source in sources if source["kind"] in POINTERS
                and not only_pointer(read_text(repo / source["path"]))]
    if pointers:
        print("Deja como puntero a AGENTS.md (`@AGENTS.md` donde la herramienta importa archivos; si no, una línea que "
              "remita a él), con lo propio de esa herramienta que quedó en su archivo: " + ", ".join(pointers) + ".")
    if gone or pointers:
        print("Las skills locales solapadas no se borran: se propone retirarlas.")
    return 0


def section_of(text, label):
    """El texto de la sección o la parte de una fuente con esa etiqueta del inventario (todo, si es el archivo entero)."""
    if plain(label) == plain(WHOLE_FILE):
        return text
    for item in sections(text):
        for part in [item] + item["parts"]:
            if plain(part["label"]) == plain(label):
                return body(text, part)
    return ""


# ── Estructura: el archivo de sustitución, sus excepciones, otros hosts y los scripts de sincronización ──────────────
GENERIC_KEYS = {"path", "paths", "dir", "directory", "ruta", "rutas", "source", "src", "location", "folder", "localpath",
                "local_path", "projectdir", "carpeta"}
NAME_KEYS = ("name", "nombre", "id", "module", "modulo", "key", "artifact", "artifactid", "package")
LOCAL_VALUE = re.compile(r"^(?:file:|link:|portal:)?((?:\.\./)+)([A-Za-z0-9_-][A-Za-z0-9._-]*)/?$")
KEYED_LINE = re.compile(r"""["']?([@A-Za-z0-9_.:/-]+?)["']?\s*(?:[:=]|=>)\s*["']?(?:file:|link:|portal:)?((?:\.\./)+)"""
                        r"""([A-Za-z0-9_-][A-Za-z0-9._-]*)""")
GRADLE_PROJECT = re.compile(r"""project\(\s*["']:?([^"']+)["']\s*\)\.projectDir\s*=\s*(?:file\(\s*)?"""
                            r"""(?:new\s+File\([^,]*,\s*)?["']((?:\.\./)+)([A-Za-z0-9_-][A-Za-z0-9._-]*)""")
LOCK_FILE = re.compile(r"(?:^|/)(?:[^/]*\.lock|[^/]*-lock\.[^/]+|[^/]*\.lockfile|go\.sum)$")
BUILD_FILE = re.compile(r"(?:^|/)(?:[^/]*\.gradle(?:\.kts)?|[^/]*\.versions\.toml|pom\.xml|package\.json)$")
COORDINATE = re.compile(r"""["']([A-Za-z][\w-]*(?:\.[\w-]+)+):([A-Za-z][\w.-]*)(?::[^"'\s]*)?["']""")
TOML_GROUP_NAME = re.compile(r"""group\s*=\s*["']([^"']+)["']\s*,\s*name\s*=\s*["']([^"']+)["']""")
POM_DEPENDENCY = re.compile(r"<groupId>\s*([^<\s]+)\s*</groupId>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>")
NPM_SCOPED = re.compile(r'"(@[a-z0-9][\w.-]*)/([a-z0-9][\w.-]*)"\s*:')
SCRIPT_FILE = re.compile(r"(?:\.(?:sh|bash|zsh|py|js|mjs|cjs|ts|rb|ps1|kts|gradle)|(?:^|/)Makefile)$")
TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__|specs?|fixtures?)/|(?:^|/)test_[^/]*$|_test\.[^/]+$|"
                       r"\.(?:test|spec)\.[^/]+$")
SYNC_NAME = re.compile(r"(?i)sync|sincroniz|workspace|bootstrap|clon|actualiz|update|repos\b|checkout|pull")
GIT_ACTION = r"\bgit\s+(?:-C\s+\S+\s+)?"
GIT_ANY = re.compile(GIT_ACTION + r"(?:clone|pull|fetch|checkout|switch|rebase|merge|reset|clean)\b")
SYNC_ACTIONS = (("clona", GIT_ACTION + r"clone\b", False),
                ("actualiza con pull", GIT_ACTION + r"pull\b", False),
                ("descarga con fetch", GIT_ACTION + r"fetch\b", False),
                ("cambia de rama", GIT_ACTION + r"(?:checkout|switch)\b", False),
                ("hace rebase", GIT_ACTION + r"rebase\b", False),
                ("hace merge", GIT_ACTION + r"merge\b", False),
                ("guarda cambios con stash", GIT_ACTION + r"stash\b", False),
                ("hace push", GIT_ACTION + r"push\b", False),
                ("descarta cambios con reset --hard", GIT_ACTION + r"reset\s+--hard\b", True),
                ("borra archivos sin seguimiento con clean", GIT_ACTION + r"clean\b", True),
                ("borra carpetas con rm -rf", r"\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\b", True),
                ("crea enlaces simbólicos", r"\bln\s+-[a-zA-Z]*s", False))
GIT_URL = re.compile(r"(?:(?:https?|ssh|git)://[^\s\"'<>()]+|\b[\w.-]+@[\w.-]+:[\w./~-]+)")


def sibling_folder(repo, file, ups, name):
    """El nombre del repo vecino al que apunta ../<nombre> desde un archivo del repo, o None si no sale a la carpeta
    padre."""
    root = os.path.normpath(str(repo))
    target = os.path.normpath(os.path.join(os.path.dirname(os.path.join(root, file)), ups, name))
    return os.path.basename(target) if os.path.dirname(target) == os.path.dirname(root) and target != root else None


def clean_key(key):
    key = (key or "").strip().strip(":")
    return None if not key or key.lower().replace("-", "").replace("_", "") in GENERIC_KEYS else key


def json_entries(value, key=None, owner=None):
    """(clave, ../, nombre) de cada valor de un JSON que apunta a un repo vecino. Con una clave genérica (path, dir),
    la clave es el nombre del objeto (name, id, module)."""
    if isinstance(value, dict):
        for child_key, child in value.items():
            for entry in json_entries(child, child_key, value):
                yield entry
    elif isinstance(value, list):
        for item in value:
            for entry in json_entries(item):
                yield entry
    elif isinstance(value, str):
        local = LOCAL_VALUE.match(value.strip())
        if local:
            name = clean_key(key)
            if name is None and owner:
                name = next((str(owner[field]) for field in owner if field.lower() in NAME_KEYS
                             and isinstance(owner[field], str)), None)
            yield name, local.group(1), local.group(2)


def substitution_entries(repo, file):
    """Las entradas de un archivo de configuración que apuntan a repos vecinos: [(clave o None, carpeta)]."""
    text, entries = read_text(repo / file), []
    candidates = []
    if file.endswith(".json"):
        try:
            candidates = list(json_entries(json.loads(text)))
        except ValueError:
            candidates = []
    if not candidates:
        for line in text.splitlines():
            found = GRADLE_PROJECT.search(line) or KEYED_LINE.search(line)
            if found:
                candidates.append((clean_key(found.group(1)), found.group(2), found.group(3)))
            else:
                candidates.extend((None, ups, name) for ups, name in OUTSIDE_REF.findall(line))
    for key, ups, name in candidates:
        folder = sibling_folder(repo, file, ups, name)
        if folder and (key, folder) not in entries:
            entries.append((key, folder))
    return entries


def key_names(key):
    """Las formas de una clave que pueden aparecer en el nombre de una carpeta: la clave, su última parte (después de
    `:`, `/` o `.`) y cada una en minúsculas con guiones (designSystem → design-system)."""
    out = []
    for value in (key, re.split(r"[:/]", key)[-1], key.rsplit(".", 1)[-1]):
        for form in (value, re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", value).lower().replace("_", "-")):
            if form and form not in out:
                out.append(form)
    return out


def key_template(key, folder):
    """La carpeta con la clave reemplazada por {clave} (feature-{clave}), o None si la carpeta no contiene la clave."""
    for candidate in key_names(key):
        index = folder.lower().find(candidate.lower())
        if index >= 0:
            return folder[:index] + "{clave}" + folder[index + len(candidate):]
    return None


def folder_pattern(entries):
    """El patrón dominante de las carpetas de un archivo de sustitución y las entradas que no lo siguen:
    (patrón, [(clave, carpeta)]) o (None, [])."""
    keyed = [(key, folder) for key, folder in entries if key]
    if len(keyed) >= 2:
        templates = [key_template(key, folder) for key, folder in keyed]
        counts = {}
        for template in templates:
            if template:
                counts[template] = counts.get(template, 0) + 1
        if counts:
            best = max(sorted(counts), key=lambda item: counts[item])
            if counts[best] >= 2 and counts[best] * 2 > len(keyed):
                return "../" + best, [entry for entry, template in zip(keyed, templates) if template != best]
    folders = [folder for _, folder in entries]
    prefixes = {}
    for folder in folders:
        found = re.match(r"^([A-Za-z0-9]+[-_.])", folder)
        if found:
            prefixes[found.group(1)] = prefixes.get(found.group(1), 0) + 1
    if len(folders) >= 3 and prefixes:
        best = max(sorted(prefixes), key=lambda item: prefixes[item])
        if prefixes[best] >= 2 and prefixes[best] * 2 > len(folders):
            return "../%s*" % best, [(key, folder) for key, folder in entries if not folder.startswith(best)]
    return None, []


def build_coordinates(repo, files):
    """Las dependencias que nombran los archivos de build: {(grupo o scope, artefacto): [archivos]}."""
    found = {}
    for file in files:
        if not BUILD_FILE.search(file) or "node_modules/" in file:
            continue
        text = read_text(repo / file)
        pairs = COORDINATE.findall(text) + TOML_GROUP_NAME.findall(text) + POM_DEPENDENCY.findall(text)
        if file.endswith("package.json"):
            pairs += NPM_SCOPED.findall(text)
        for group, artifact in pairs:
            where = found.setdefault((group, artifact), [])
            if file not in where:
                where.append(file)
    return found


def url_host(url):
    found = re.match(r"^[a-z][a-z0-9+.-]*://(?:[^/@]*@)?([^/:]+)", url) or re.match(r"^[^@/\s]+@([^:/\s]+):", url)
    return found.group(1).lower() if found else None


def sync_scripts(repo, files):
    """Los scripts que sincronizan el espacio de trabajo (clonan, actualizan o cambian de rama en los repos vecinos):
    [(archivo, [(acción, veces, destructiva)], repos, ramas, urls)]. Los tests no cuentan."""
    out = []
    for file in files:
        if not SCRIPT_FILE.search(file) or "node_modules/" in file or TEST_PATH.search(file):
            continue
        text = read_text(repo / file)
        git_commands = len(GIT_ANY.findall(text))
        named = sorted({folder for ups, name in OUTSIDE_REF.findall(text)
                        for folder in [sibling_folder(repo, file, ups, name)] if folder})
        urls = sorted({clean_url(url).rstrip(".,;") for url in GIT_URL.findall(text)
                       if url.rstrip(".,;").endswith(".git") or "@" in url.split("/")[0]})
        outside = bool(named or urls or re.search(r"\.\./\$", text))
        name_hint = SYNC_NAME.search(pathlib.PurePosixPath(file).name)
        if not ((name_hint and git_commands) or (git_commands >= 2 and outside)):
            continue
        actions = [(label, len(re.findall(pattern, text)), harmful) for label, pattern, harmful in SYNC_ACTIONS]
        branches = sorted({branch for branch in re.findall(GIT_ACTION + r"(?:checkout|switch)\s+(?:-[bBc]\s+)?"
                                                           r"([A-Za-z0-9][\w./-]*)", text) if branch != "--"})
        out.append((file, [action for action in actions if action[1]], named, branches, urls))
    return out


def structure_details(repo, files, sibling_urls):
    """Lo que el inventario de ## Estructura suma al análisis básico: archivos de sustitución con sus excepciones al
    patrón, dependencias del build fuera de ellos, repos en otro host y scripts de sincronización. Solo lee."""
    substitution = [(file, substitution_entries(repo, file)) for file in files
                    if CONFIG_NAME.search(file) and not LOCK_FILE.search(file)]
    substitution = [(file, entries) for file, entries in substitution if len(entries) >= 2]
    if substitution:
        print("Archivos que pasan unidades a fuente (candidatos a archivo de sustitución):")
    names = set()
    for file, entries in substitution:
        pattern, exceptions = folder_pattern(entries)
        print("  %s: %d entradas%s" % (file, len(entries), "; patrón dominante: %s" % pattern if pattern else ""))
        if exceptions:
            print("    ⚠ Fuera del patrón (anótalas en ## Estructura como excepciones: la Fuente real de su unidad): "
                  + ", ".join("%s → ../%s" % (key or "(sin clave)", folder) for key, folder in exceptions))
        for key, folder in entries:
            names.add(folder.lower())
            if key:
                names.update(form.lower() for form in key_names(key))
    if names:
        coordinates = build_coordinates(repo, files)
        matched = {}
        for group, artifact in coordinates:
            if artifact.lower() in names:
                matched.setdefault(group, set()).add(artifact.lower())
        groups = {group for group, artifacts in matched.items() if len(artifacts) >= 2}  # un nombre suelto no basta
        outside = sorted((group, artifact) for group, artifact in coordinates
                         if group in groups and artifact.lower() not in names)
        if outside:
            print("  Dependencias del build del mismo grupo que las unidades sustituibles que no están en el archivo de "
                  "sustitución (pregunta si son unidades: publicadas sin mecanismo, en otro host o ajenas): "
                  + ", ".join("%s%s%s (%s)" % (group, "/" if group.startswith("@") else ":", artifact,
                                                ", ".join(coordinates[(group, artifact)][:2]))
                              for group, artifact in outside))
    scripts = sync_scripts(repo, files)
    main_url, _ = remote_info(repo)
    main_host = url_host(main_url) if main_url else None
    foreign = []
    for name, url in sorted(sibling_urls.items()):
        host = url_host(url) if url else None
        if main_host and host and host != main_host:
            foreign.append("../%s (%s)" % (name, url))
    for file, _, _, _, urls in scripts:
        for url in urls:
            host = url_host(url)
            if main_host and host and host != main_host and not any(url in item for item in foreign):
                foreign.append("%s (en %s)" % (url, file))
    if foreign:
        print("Repos en otro host que el principal (%s): %s. Anótalo en «Repo y rama principal» con su URL: puede pedir "
              "otras credenciales o permisos." % (main_host, ", ".join(foreign)))
    if scripts:
        print("Scripts de sincronización del espacio de trabajo (resume cada uno en un doc —qué hace, cuándo se corre, "
              "sus reglas y qué puede borrar o pisar— con su fila en «Documentos»):")
        for file, actions, named, branches, _ in scripts:
            detail = ", ".join("%s (%d)" % (label, count) for label, count, _ in actions)
            extra = ("; repos: " + ", ".join("../" + name for name in named) if named else "") + \
                ("; ramas: " + ", ".join(branches) if branches else "")
            print("  %s: %s%s" % (file, detail or "sin acciones de git reconocidas", extra))
            harmful = [label for label, _, risky in actions if risky]
            if harmful:
                print("    ⚠ Puede descartar o borrar cambios locales (%s): anótalo en el doc como regla. Ninguna skill "
                      "lo corre para preparar la rama de trabajo." % ", ".join(harmful))


def submodules(repo):
    listing = git(repo, "config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$")
    return [line.split(" ", 1)[1] for line in listing.stdout.splitlines() if " " in line]


def status(args):
    repo = toplevel(args.repo)
    folder = args.carpeta.strip("/")
    agents, claude_md = describe(repo, "AGENTS.md"), describe(repo, "CLAUDE.md")
    print(f"AGENTS.md: {agents}")
    print(f"CLAUDE.md: {claude_md} · .claude/: {'sí' if (repo / '.claude').is_dir() else 'no'}"
          f" → Claude Code por defecto: {'sí' if uses_claude(repo, 'auto') else 'no'}")
    print(f"{folder}/: {describe(repo, folder)}")
    if agents.startswith("enlace"):
        mode = "externo"
    elif agents.startswith("excluido"):
        mode = "local"
    elif agents == "versionado":
        mode = "versionado"
    else:
        mode = "sin definir (" + agents + ")"
    print(f"Modo del contexto: {mode}")
    found = previous_sources(repo, folder)[0]
    if found:
        print("Fuentes previas de contexto de IA: " + ", ".join(source["path"] for source in found)
              + " → camino: migrar (`contexto.py fuentes` da el inventario de traspaso)")
    else:
        print("Fuentes previas de contexto de IA: ninguna → camino: plantilla")
    main, missing = worktree_links(repo, ("AGENTS.md", "CLAUDE.md", folder))
    if main is not None:
        print(f"Worktree enlazado: el principal es {home(main)}.")
        for name, kind, target in missing:
            covered = "git ya lo ignora (.git/info/exclude es común a los worktrees)" if ignored(repo, name) else \
                f"agrega /{name} a .git/info/exclude"
            print(f"  ⚠ Falta {name}: en el principal es un {kind} ({home(target)}). Para recrearlo: "
                  f"cd {home(repo)} && ln -s {home(target)} {name} ({covered}). Hazlo solo si el usuario o el "
                  f"proyecto lo piden.")
    local = local_ai_files(repo)
    print("Archivos locales de IA sin versionar ni excluir: " + (", ".join(local) if local else "ninguno")
          + (" (preparar los deja en .git/info/exclude)" if local else ""))
    subs = submodules(repo)
    print("Submódulos: " + (", ".join(subs) if subs else "ninguno"))
    related = siblings(repo)
    if not related:
        print("Repos hermanos que nombra el proyecto: ninguno")
        return
    print("Repos hermanos que nombra el proyecto:")
    for name, hows in sorted(related.items()):
        for how, label in (("ruta", "como ruta"), ("nombre", "por nombre, candidato a confirmar")):
            files = hows[how]
            if files:
                more = f" y {len(files) - 3} más" if len(files) > 3 else ""
                print(f"  ../{name}  ({label}: {', '.join(files[:3])}{more})")


def conflicts(repo, mode, entries, external):
    """Lo que impide preparar el modo sin pisar ni borrar nada. Se revisa todo antes de tocar algo."""
    problems = []
    for name, kind in entries:
        path = repo / name
        if mode != "versionado" and tracked(repo, name):
            problems.append(f"{name} está versionado: excluirlo no lo saca de git. Si quieres este modo, sácalo tú "
                            f"(git rm --cached{' -r' if kind == 'dir' else ''} {name}) y vuelve a correr.")
            continue
        if mode != "externo":
            continue
        target = external / name
        if target.exists() and target.is_dir() != (kind == "dir"):
            problems.append(f"{home(target)} ya existe y es {'una carpeta' if target.is_dir() else 'un archivo'}: "
                            f"ahí va {'una carpeta' if kind == 'dir' else 'un archivo'}. No lo toco.")
            continue
        if not exists(path):
            continue
        if path.is_symlink():
            if os.path.realpath(str(path)) != os.path.realpath(str(target)):
                problems.append(f"{name} ya es un enlace a {home(os.path.realpath(str(path)))}, no a "
                                f"{home(target)}: no lo cambio.")
        else:
            problems.append(f"{name} ya existe en el repo: no lo muevo ni lo borro. Muévelo tú a {home(target)} "
                            f"(si ahí ya hay uno, decide cuál queda) y vuelve a correr.")
    return problems


def link(repo, name, target):
    """El enlace del repo a la carpeta externa, relativo para que sobreviva a mover las dos carpetas juntas."""
    path = repo / name
    if path.is_symlink():
        return "ya enlazado"
    relative = os.path.relpath(os.path.realpath(str(target)), os.path.realpath(str(repo)))
    os.symlink(relative, str(path), target_is_directory=target.is_dir())
    return f"enlace a {relative}"


def prepare(args):
    repo = toplevel(args.repo)
    folder = args.carpeta.strip("/")
    if not folder or "/" in folder or folder in (".", ".."):
        raise ValueError(f"--carpeta debe ser el nombre de una carpeta en la raíz del repo (llegó {args.carpeta!r})")
    mode = args.modo
    if mode == "externo" and not args.externa:
        raise ValueError("el modo externo necesita --externa <carpeta fuera del repo>")
    external = pathlib.Path(os.path.abspath(os.path.expanduser(args.externa))) if mode == "externo" else None
    if external is not None:
        inside = os.path.realpath(str(external)) + "/"
        if inside.startswith(os.path.realpath(str(repo)) + "/"):
            raise ValueError("la carpeta externa no puede estar dentro del repo")
    claude = uses_claude(repo, args.claude)
    reports = args.reportes or ("reports" if mode == "versionado" else f"{folder}/reports")
    entries = [("AGENTS.md", "file")] + ([("CLAUDE.md", "file")] if claude else [])
    if mode != "versionado":
        entries.append((folder, "dir"))
    if args.module_maps == "versioned" and mode != "versionado":
        raise ValueError("los mapas del módulo solo se versionan si el contexto se versiona (--modo versionado)")
    maps = ("docs" if mode == "versionado" else folder) + "/modules"
    problems = conflicts(repo, mode, entries, external)
    if mode == "versionado" and args.module_maps == "local" and tracked(repo, maps):
        problems.append(f"{maps}/ tiene archivos versionados: excluirla no los saca de git. Usa --module-maps "
                        f"versioned o sácalos tú (git rm --cached -r {maps}) y vuelve a correr.")
    if problems:
        print("✖ No cambié nada:\n" + "\n".join(f"  - {p}" for p in problems), file=sys.stderr)
        return 1

    done, write_agents = [], repo / "AGENTS.md"
    if mode == "externo":
        external.mkdir(parents=True, exist_ok=True)
        for name, kind in entries:
            target = external / name
            if kind == "dir":
                had = target.is_dir() and any(target.iterdir())
                target.mkdir(parents=True, exist_ok=True)
                note = "ya tiene contenido: lo uso tal cual" if had else "creada"
            elif target.exists():
                note = "ya existe: lo uso tal cual, no lo piso"
            elif name == "CLAUDE.md":
                target.write_text("@AGENTS.md\n", encoding="utf-8")
                note = "creado con @AGENTS.md"
            else:
                note = "todavía no existe: escríbelo ahí"
            done.append(f"{home(target)}: {note}")
            done.append(f"{name} en el repo: {link(repo, name, target)}")
            line = "/" + name  # sin barra final: git ve el enlace como archivo, no como carpeta
            if not ignored(repo, name) and add_exclude(repo, line):
                done.append(f"{line} agregado a .git/info/exclude")
        write_agents = external / "AGENTS.md"
    else:
        if mode == "local":
            (repo / folder).mkdir(exist_ok=True)
        if claude and not exists(repo / "CLAUDE.md"):
            (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
            done.append("CLAUDE.md creado con @AGENTS.md")
        if mode == "local":
            for name, kind in entries:
                line = "/" + name + ("/" if kind == "dir" else "")
                if not ignored(repo, name) and add_exclude(repo, line):
                    done.append(f"{line} agregado a .git/info/exclude")

    if claude and exists(repo / "CLAUDE.md"):
        text = (repo / "CLAUDE.md").read_text(encoding="utf-8") if (repo / "CLAUDE.md").is_file() else ""
        if "@AGENTS.md" not in text:
            done.append("CLAUDE.md ya existía y no importa @AGENTS.md: agrega esa línea y conserva lo propio")
    reports_root = fixed_part(reports)
    covered = mode != "versionado" and (reports_root == folder or reports_root.startswith(folder + "/"))
    if reports_root and not covered and not ignored(repo, reports_root + "/"):
        line = "/" + reports_root + "/"
        if add_exclude(repo, line):
            done.append(f"{line} agregado a .git/info/exclude")

    if mode == "versionado" and args.module_maps == "local" and not ignored(repo, maps + "/"):
        if add_exclude(repo, "/" + maps + "/"):
            done.append(f"/{maps}/ (mapas del módulo) agregado a .git/info/exclude")

    for line in exclude_local_ai(repo):  # S4
        done.append(f"{line} (archivo local de una herramienta de IA) agregado a .git/info/exclude")

    docs = "docs/" if mode == "versionado" else f"{folder}/docs/"
    print(f"✔ Contexto de IA en modo {mode}" + (f" ({home(external)})" if external else ""))
    for item in done:
        print(f"  - {item}")
    print("Escribe:")
    print(f"  - AGENTS.md en {home(write_agents) if mode == 'externo' else 'AGENTS.md'}")
    print(f"  - CLAUDE.md: {'sí, con @AGENTS.md' if claude else 'no (el proyecto no muestra señales de Claude Code)'}")
    print(f"  - Lo extenso, enlazado desde AGENTS.md, en {docs}")
    print("Para ## Reglas del proyecto:")
    files = "AGENTS.md" + (", CLAUDE.md" if claude else "")
    if mode == "versionado":
        print(f"  - Contexto de IA: versionado con el código ({files} y `{docs}`).")
    elif mode == "local":
        print(f"  - Contexto de IA: local, no se versiona: {files} y `{folder}/` están en `.git/info/exclude`. "
              f"Lo extenso, en `{docs}`.")
    else:
        print(f"  - Contexto de IA: fuera del repo, en `{home(external)}`; en el repo son enlaces simbólicos "
              f"({files} y `{folder}`) excluidos en `.git/info/exclude`. Lo extenso, en `{docs}`.")
    print(f"  - Carpeta de reportes: `{reports}`")
    base = fixed_part(reports) if MARKER.search(reports) else reports
    marked = bool(MARKER.search(reports))
    print("    Es la base común de los reportes: " + ", ".join(f"{skill} en `{base}/{sub}/`"
                                                             for skill, sub in REPORT_FOLDERS
                                                             if not (marked and skill == "hb-implement"))
          + f", con el índice en `{base}/INDEX.md`."
          + (f" Con {{fecha}} y {{slug}}, hb-implement usa la línea tal cual (`{reports}`)." if marked else ""))
    where = "versionados con el código" if args.module_maps == "versioned" else (
        "fuera de git (en `.git/info/exclude`)" if mode == "versionado" else f"fuera de git (dentro de `{folder}/`)")
    print("Para ## Estructura, en ### Mapas del módulo (la línea tal cual):")
    print(f"  - En `{maps}/<identificador>.md`, {where}. Antes de tocar una unidad, lee su mapa; "
          f"si no existe, créalo; si su `Commit analizado` quedó atrás, actualízalo solo con el diff desde ese commit.")
    print(f"Para ## Estructura, en ### Documentos: una fila por cada documento extenso de `{docs}`, con su ruta y "
          f"cuándo leerlo. Por ejemplo: | `{docs}arquitectura.md` | Vayas a crear una feature o un módulo nuevo |")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command")
    sub.required = True
    state = sub.add_parser("estado", help="muestra cómo está hoy el contexto de IA y qué repos relacionados nombra")
    state.add_argument("--carpeta", default="contexto", help="carpeta de contexto en la raíz (por defecto contexto)")
    state.add_argument("--repo", default=".", help="raíz del repositorio")
    prep = sub.add_parser("preparar", help="deja la estructura del modo elegido, sin pisar nada")
    prep.add_argument("--modo", required=True, choices=MODES)
    prep.add_argument("--externa", help="modo externo: carpeta fuera del repo donde viven los archivos")
    prep.add_argument("--carpeta", default="contexto", help="carpeta de contexto en la raíz (por defecto contexto)")
    prep.add_argument("--reportes", help="carpeta de reportes, puede usar {fecha} y {slug} "
                                         "(por defecto reports, o <carpeta>/reports fuera del modo versionado)")
    prep.add_argument("--claude", default="auto", choices=("auto", "si", "no"),
                      help="crear CLAUDE.md: auto = solo si ya hay CLAUDE.md o .claude/")
    prep.add_argument("--module-maps", default="local", choices=MAPS_CHOICES,
                      help="modo versionado: los mapas del módulo (docs/modules/) quedan fuera de git (local, por "
                           "defecto) o se versionan (versioned)")
    prep.add_argument("--repo", default=".", help="raíz del repositorio")
    inventory = sub.add_parser("units", help="inventario de solo lectura para ## Estructura: unidades candidatas, repos "
                                             "vecinos clonados y sin clonar, y lo que no coincide con el modelo")
    inventory.add_argument("--repo", default=".", help="raíz del repositorio")
    perf = sub.add_parser("rendimiento", help="el bloque de hb-performance que se conserva y lo que conviene cambiar en "
                                              "la sección de rendimiento (no escribe nada)")
    prod = sub.add_parser("producto", help="la sección ## Producto de hb-product que se conserva y la fila de su PRD "
                                           "para Documentos (no escribe nada)")
    for parser in (perf, prod):
        parser.add_argument("--carpeta", default="contexto", help="carpeta de contexto en la raíz (por defecto contexto)")
        parser.add_argument("--repo", default=".", help="raíz del repositorio")
    found = sub.add_parser("fuentes", help="las fuentes previas de contexto de IA (aunque no haya AGENTS.md) y el "
                                           "inventario de traspaso sugerido (no escribe nada)")
    check = sub.add_parser("verificar", help="comprueba el traspaso a AGENTS.md contra el inventario: nada se pierde "
                                             "(no escribe nada)")
    check.add_argument("--inventario", help="el inventario completo (la tabla de `fuentes`); - lo lee de la entrada")
    check.add_argument("--previo", action="append", help="la copia de una fuente de antes de reescribirla: "
                       "<ruta>=<copia> (solo <copia> es la de AGENTS.md); se repite. Sin ella, la de HEAD si está en git")
    for parser in (found, check):
        parser.add_argument("--fuente", action="append", help="otra fuente previa que el script no encontró (se repite)")
        parser.add_argument("--carpeta", default="contexto", help="carpeta de contexto en la raíz (por defecto contexto)")
        parser.add_argument("--repo", default=".", help="raíz del repositorio")
    args = ap.parse_args(argv)
    if args.command == "estado":
        status(args)
        return 0
    if args.command == "rendimiento":
        return performance(args)
    if args.command == "producto":
        return product(args)
    if args.command == "units":
        return units(args)
    if args.command == "fuentes":
        return sources_command(args)
    if args.command == "verificar":
        return verify(args)
    return prepare(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError) as err:
        print(f"✖ {err}", file=sys.stderr)
        sys.exit(1)
