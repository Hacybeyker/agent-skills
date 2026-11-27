#!/usr/bin/env python3
"""Valida las convenciones propias del repo, además de la especificación de Agent Skills.

- Nombre con prefijo hb- y metadata (author, version SemVer, category).
- SKILL.md de 500 líneas como máximo.
- Enlaces relativos entre archivos .md que existan (fuera de assets/, que tiene plantillas).
- Scripts ejecutables y con sintaxis válida (Python, Bash, JavaScript), incluidos install.sh y scripts/.
- README.md y CATALOG.md listan cada skill con su versión actual.

Uso: python3 scripts/check_conventions.py   (necesita el CLI `agentskills` de skills-ref en el PATH)
"""
import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
CATEGORIES = {"flow", "stack", "tool"}
MAX_LINES = 500
errors = []


def error(path, message):
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def properties(skill):
    result = subprocess.run(["agentskills", "read-properties", str(skill)], capture_output=True, text=True)
    if result.returncode != 0:
        error(skill, f"no se pudo leer el frontmatter: {result.stderr.strip()}")
        return None
    return json.loads(result.stdout)


def check_metadata(skill, props):
    name = props.get("name", "")
    meta = props.get("metadata") or {}
    if not name.startswith("hb-"):
        error(skill, f"el nombre '{name}' no tiene el prefijo hb-")
    if meta.get("author") != "hacybeyker":
        error(skill, "metadata.author debe ser 'hacybeyker'")
    if not SEMVER.match(str(meta.get("version", ""))):
        error(skill, f"metadata.version '{meta.get('version')}' no es SemVer")
    category = meta.get("category")
    if category not in CATEGORIES:
        error(skill, f"metadata.category '{category}' no es una de {sorted(CATEGORIES)}")
    if category == "stack" and not name.startswith("hb-stack-"):
        error(skill, "un perfil (category: stack) se llama hb-stack-<familia>")


def check_length(skill):
    lines = (skill / "SKILL.md").read_text(encoding="utf-8").count("\n")
    if lines > MAX_LINES:
        error(skill / "SKILL.md", f"tiene {lines} líneas (máximo {MAX_LINES}); mueve detalle a references/")


def check_links(skill):
    for md in skill.rglob("*.md"):
        if "assets" in md.relative_to(skill).parts:
            continue  # plantillas y ejemplos: sus enlaces son ilustrativos
        text = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        for target in re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", text):
            if re.match(r"^[a-z]+:", target) or target.startswith("<"):
                continue
            if not (md.parent / target).exists():
                error(md, f"enlace roto: {target}")


def check_scripts(skill):
    folder = skill / "scripts"
    if not folder.is_dir():
        return
    for script in folder.iterdir():
        if not script.is_file() or "__pycache__" in script.parts:
            continue
        if not os.access(script, os.X_OK):
            error(script, "no es ejecutable (chmod +x)")
        if script.suffix == ".py":
            try:
                ast.parse(script.read_text(encoding="utf-8"))
            except SyntaxError as e:
                error(script, f"sintaxis de Python inválida: {e}")
        elif script.suffix == ".sh":
            r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            if r.returncode != 0:
                error(script, f"sintaxis de Bash inválida: {r.stderr.strip()}")
        elif script.suffix in {".js", ".mjs"} and shutil.which("node"):
            r = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
            if r.returncode != 0:
                error(script, f"sintaxis de JavaScript inválida: {r.stderr.strip()}")


def check_repo_scripts():
    for script in [ROOT / "install.sh", *sorted((ROOT / "scripts").iterdir())]:
        if script.is_file() and script.suffix in {".sh", ".py"} and not os.access(script, os.X_OK):
            error(script, "no es ejecutable (chmod +x)")


def skill_rows(text):
    """Las filas de las tablas con columnas "Skill" y "Versión": [(skill, versión)]. La skill es lo primero entre
    acentos graves de su celda ([`hb-x`](skills/hb-x) o `hb-x`); las columnas se ubican por la cabecera, en cualquier
    orden. No cuentan las demás tablas ni lo que está en un bloque de código (con cercas o indentado) o en un
    comentario HTML. Un `\\|` dentro de una celda no la corta."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    rows, columns, fence = [], None, None
    for line in text.splitlines():
        opened = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None and opened and not (opened.group(1)[0] == "`" and "`" in opened.group(2)):
            fence, columns = opened.group(1), None
            continue
        if fence is not None:
            closed = re.match(r"^ {0,3}(`{3,}|~{3,})\s*$", line)
            if closed and closed.group(1)[0] == fence[0] and len(closed.group(1)) >= len(fence):
                fence = None
            continue
        if re.match(r"^(?: {4}|\t)", line) or not line.strip().startswith("|"):  # código indentado o fuera de tabla
            columns = None
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if columns is None:
            names = [cell.lower().replace("ó", "o") for cell in cells]
            columns = (names.index("skill"), names.index("version")) if "skill" in names and "version" in names \
                else False
            continue
        if columns is False or all(re.match(r"^:?-+:?$", cell) for cell in cells if cell):
            continue
        name = re.search(r"`([^`]+)`", cells[columns[0]]) if columns[0] < len(cells) else None
        if name:
            rows.append((name.group(1), cells[columns[1]] if columns[1] < len(cells) else ""))
    return rows


def docs_errors(found, readme, catalog):
    """[(archivo, mensaje)]: cada skill con una sola fila y su versión actual en la tabla de README.md y en CATALOG.md."""
    out = []
    for file, text in (("README.md", readme), ("CATALOG.md", catalog)):
        rows = skill_rows(text)
        for name, version in found.items():
            listed = [value for skill, value in rows if skill == name]
            if not listed:
                out.append((file, f"no lista la skill {name} con su versión"))
            elif len(listed) > 1:
                out.append((file, f"lista la skill {name} {len(listed)} veces"))
            elif listed[0] != version:
                out.append((file, f"{name} figura con la versión {listed[0]}, pero la skill está en {version}"))
    return out


def check_docs(found):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    catalog = (ROOT / "CATALOG.md").read_text(encoding="utf-8")
    for file, message in docs_errors(found, readme, catalog):
        error(ROOT / file, message)


def main():
    if not shutil.which("agentskills"):
        sys.exit("✖ Falta el CLI agentskills: pip install skills-ref")
    found = {}
    for skill in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        props = properties(skill)
        if props is None:
            continue
        check_metadata(skill, props)
        check_length(skill)
        check_links(skill)
        check_scripts(skill)
        found[props.get("name", skill.name)] = str((props.get("metadata") or {}).get("version", ""))
    check_repo_scripts()
    check_docs(found)
    if errors:
        print("\n".join(f"✖ {e}" for e in errors))
        sys.exit(1)
    print(f"✔ {len(found)} skills cumplen las convenciones del repo")


if __name__ == "__main__":
    main()
