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

Uso:
  python3 -I contexto.py estado [--carpeta contexto] [--repo .]
  python3 -I contexto.py preparar --modo versionado|local|externo [--externa <ruta>] [--carpeta contexto]
                                  [--reportes <ruta>] [--claude auto|si|no] [--repo .]
  python3 -I contexto.py rendimiento [--repo .]
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys

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
MARKER = re.compile(r"\{(?:fecha|slug)\}")
SIBLING_REF = re.compile(r"\.\./([A-Za-z0-9._-]+)")


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
    return path.exists() or path.is_symlink()


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


def siblings(repo):
    """Repos hermanos (en la carpeta padre) que algún archivo versionado del proyecto nombra: por ruta (../<nombre>)
    o por nombre (una dependencia publicada con el mismo nombre que el repo). {nombre: {"ruta": [...], "nombre": [...]}}.
    Por nombre son candidatos: se confirman con el usuario."""
    names = sorted(d.name for d in repo.parent.iterdir() if d != repo and d.is_dir() and exists(d / ".git")) \
        if repo.parent.is_dir() else []
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


def perf_audit(repo):
    """S3: lo que hb-setup señala de la sección de rendimiento, sin reescribirla: [(línea, propuesta)] de las líneas
    fuera del bloque de estado que traen un serial de dispositivo o que contradicen el estado del bloque."""
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
    block, found = perf_audit(repo)
    if block is None:
        print("AGENTS.md no tiene sección de rendimiento: no hay nada de hb-performance que conservar")
        return 0
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
    problems = conflicts(repo, mode, entries, external)
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
    prep.add_argument("--repo", default=".", help="raíz del repositorio")
    perf = sub.add_parser("rendimiento", help="el bloque de hb-performance que se conserva y lo que conviene cambiar en "
                                              "la sección de rendimiento (no escribe nada)")
    perf.add_argument("--repo", default=".", help="raíz del repositorio")
    args = ap.parse_args(argv)
    if args.command == "estado":
        status(args)
        return 0
    if args.command == "rendimiento":
        return performance(args)
    return prepare(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError) as err:
        print(f"✖ {err}", file=sys.stderr)
        sys.exit(1)
