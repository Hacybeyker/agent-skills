#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coach.py — herramienta del Software Coach (Python 3.8+, sin dependencias).

Gestiona el espacio de aprendizaje de un proyecto (por defecto ./aprendizaje):
plan de estudio, notas de lecciones, glosario, dudas y el cuaderno HTML.
Existe una versión equivalente para Node 18+: coach.mjs (misma salida).

Ejemplos:
  python3 coach.py init hilt --tema "Hilt: inyección de dependencias en Android" --area android
  python3 coach.py leccion hilt 1.1
  python3 coach.py completar hilt 1.1
  python3 coach.py estado
  python3 coach.py build
Ejecuta `python3 coach.py ayuda` para ver todos los comandos.
"""

import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2.0.1"
SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
TEMPLATES = ASSETS / "plantillas"
VIEWER = ASSETS / "cuaderno.html"
DATA_PLACEHOLDER = '"__COACH_DATA__"'
BOOL_FLAGS = {"json", "no-build", "convalidada", "force", "versionar", "gitignore", "help"}
NOTE_STATES = ("en-curso", "completada", "convalidada")

AYUDA = """Software Coach — herramienta del espacio de aprendizaje (v{v})

Uso: coach <comando> [argumentos] [--root DIR]

Comandos:
  init <slug> --tema "Título" [--area A] [--nivel-objetivo N] [--versionar | --gitignore]
        Crea aprendizaje/<slug>/ con PLAN.md, GLOSARIO.md, DUDAS.md y lecciones/, más
        README.md y METODO.md en la raíz. Excluye aprendizaje/ de git con
        .git/info/exclude (salvo --versionar).
  leccion <slug> <id>          Crea (si falta) la nota de la lección y la marca como actual.
  completar <slug> <id> [--convalidada]
                               Marca la lección como hecha en PLAN.md y en su nota.
  reabrir <slug> <id>          Vuelve a dejar la lección pendiente y actual.
  estado [slug] [--json]       Progreso, huecos abiertos y sesión previa (detalle con un tema).
  build                        Regenera aprendizaje/cuaderno.html.
  check [slug]                 Valida formato, enlaces, anclas, diagramas y legibilidad.
  vendor [--force]             Descarga las librerías del cuaderno a aprendizaje/.vendor (modo offline).
  version                      Muestra la versión.

Opciones:
  --root DIR    Carpeta de aprendizaje (por defecto ./aprendizaje o $COACH_ROOT).
  --no-build    No regenerar el cuaderno después de un cambio.
"""


# --------------------------------------------------------------------------- utilidades

class CoachError(Exception):
    pass


def out(msg=""):
    sys.stdout.write(msg + "\n")


def read_text(p):
    with open(p, "r", encoding="utf-8", errors="replace", newline="") as f:
        s = f.read()
    if s.startswith("\ufeff"):
        s = s[1:]
    return s.replace("\r\n", "\n")


def write_text(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def rel(p):
    try:
        r = os.path.relpath(str(p), os.getcwd())
    except ValueError:
        return str(p)
    return r


def now():
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde and sde.strip().isdigit():
        return datetime.fromtimestamp(int(sde), tz=timezone.utc)
    return datetime.now().astimezone()


def today():
    return now().strftime("%Y-%m-%d")


def iso_now():
    d = now()
    off = d.utcoffset()
    total = int(off.total_seconds()) if off is not None else 0
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + "%s%02d:%02d" % (sign, total // 3600, (total % 3600) // 60)


def slugify(s, limit=48):
    s = unicodedata.normalize("NFKD", s)
    s = re.sub("[\u0300-\u036f]", "", s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if limit and len(s) > limit:
        cut = s[:limit]
        if s[limit] != "-" and "-" in cut:
            cut = cut[:cut.rfind("-")]
        s = cut.rstrip("-")
    return s


def id_key(i):
    return [int(x) for x in i.split(".") if re.match(r"^[0-9]+$", x)]


def fmt_kb(n):
    return "%d KB" % ((n + 512) // 1024)


def bar(done, total, width=20):
    filled = (done * width // total) if total else 0
    return "[" + "\u25a0" * filled + "\u25a1" * (width - filled) + "]"


def strip_links(s):
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)


# --------------------------------------------------------------------------- frontmatter

FM_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")


def split_frontmatter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def _split_list(inner):
    items, cur, q = [], "", None
    for ch in inner:
        if q:
            if ch == q:
                q = None
            else:
                cur += ch
        elif ch in "\"'":
            q = ch
        elif ch == ",":
            items.append(cur.strip())
            cur = ""
        else:
            cur += ch
    items.append(cur.strip())
    return [x for x in items if x != ""]


def parse_value(raw):
    v = raw.strip()
    if v[:1] in ("\"", "'"):
        q = v[0]
        end = v.rfind(q)
        if end > 0:
            inner = v[1:end]
            if q == "\"":
                inner = inner.replace("\\\"", "\"").replace("\\\\", "\\")
            return inner
    v = re.sub(r"\s+#.*$", "", v)
    if v.startswith("[") and v.endswith("]"):
        return _split_list(v[1:-1])
    return v


def parse_frontmatter(text):
    lines, body = split_frontmatter(text)
    fm = {}
    if lines is None:
        return None, body
    for line in lines:
        m = FM_KEY_RE.match(line)
        if m:
            fm[m.group(1)] = parse_value(m.group(2))
    return fm, body


def fm_str(fm, key):
    v = (fm or {}).get(key, "")
    if isinstance(v, list):
        return ", ".join(v)
    return str(v).strip()


YAML_WORDS = {"yes", "no", "on", "off", "true", "false", "null", "~"}


def yaml_quote(s):
    return "\"" + str(s).replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def fmt_value(value):
    s = str(value)
    if (s == "" or re.search(r"^[0-9.]+$", s) or re.search(r"[:#\[\]{}\",]|^\s|\s$", s)
            or re.search(r"^[!&*|>'%@`?\-]", s) or s.lower() in YAML_WORDS):
        return yaml_quote(s)
    return s


def set_fm(text, key, value):
    lines = text.split("\n")
    end = None
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                end = i
                break
    new_line = "%s: %s" % (key, fmt_value(value))
    if end is None:
        return "---\n" + new_line + "\n---\n" + text
    for i in range(1, end):
        m = FM_KEY_RE.match(lines[i])
        if m and m.group(1) == key:
            lines[i] = new_line
            return "\n".join(lines)
    lines.insert(end, new_line)
    return "\n".join(lines)


# --------------------------------------------------------------------------- plan

LESSON_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+\*\*([0-9]+(?:\.[0-9]+)+)\.?\s+(.+?)\*\*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
CONV_RE = re.compile("\\(convalidada\\)|\u23ed\ufe0f?", re.I)
MOD_ID_RE = re.compile(r"(?:m[o\u00f3]dulo|module|unidad|unit)\s+([0-9]+)", re.I)
MOD_NUM_RE = re.compile(r"^([0-9]+)\s*[.):\u00b7\-\u2014\u2013]")
MOD_PREFIX_RE = re.compile(r"^(?:(?:m[o\u00f3]dulo|module|unidad|unit)\s+[0-9]+|[0-9]+)\s*[.):\u00b7\-\u2014\u2013]*\s*", re.I)
LEVEL_TAIL_RE = re.compile(
    "[\\s\u00b7|\\-\u2014\u2013]*(?:\U0001F7E2|\U0001F7E1|\U0001F7E0|\U0001F534)?\\s*"
    "(?:b[a\u00e1]sico|intermedio|avanzado|experto|basic|beginner|intermediate|advanced|expert)?\\s*$", re.I)
LEVEL_EMOJI = [("basico", "\U0001F7E2"), ("intermedio", "\U0001F7E1"), ("avanzado", "\U0001F7E0"), ("experto", "\U0001F534")]
LEVEL_WORDS = [
    ("basico", re.compile(r"\bb[a\u00e1]sico\b|\bbasic\b|\bbeginner\b", re.I)),
    ("intermedio", re.compile(r"\bintermedio\b|\bintermediate\b", re.I)),
    ("avanzado", re.compile(r"\bavanzado\b|\badvanced\b", re.I)),
    ("experto", re.compile(r"\bexperto\b|\bexpert\b", re.I)),
]
DESC_LEAD_RE = re.compile("^[\\s\u2014\u2013\\-:\u00b7|]+")
TITLE_LEAD_RE = re.compile("^[\u00b7:\\-\u2014\u2013]\\s*")


def detect_level(text):
    for key, emo in LEVEL_EMOJI:
        if emo in text:
            return key
    for key, rx in LEVEL_WORDS:
        if rx.search(text):
            return key
    return ""


def clean_module_title(text):
    t = MOD_PREFIX_RE.sub("", text.strip())
    t = LEVEL_TAIL_RE.sub("", t).strip()
    return t or text.strip()


HUECOS_RE = re.compile(r"huecos", re.I)
BITACORA_RE = re.compile(r"bit[a\u00e1]cora", re.I)
CLOSED_RE = re.compile(r"^(cerrad|resuelt)", re.I)


def heading_table_target(text):
    if BITACORA_RE.search(text):
        return "bitacora"
    if HUECOS_RE.search(text):
        return "huecos"
    return None


def parse_plan(text):
    fm, _ = parse_frontmatter(text)
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                start = i + 1
                break
    modules, lessons = [], []
    tables = {"bitacora": [], "huecos": []}
    heading = None
    heading_used = False
    in_fence = False
    table_target = None
    for n in range(start, len(lines)):
        line = lines[n]
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        h = HEADING_RE.match(line)
        if h:
            level = len(h.group(1))
            if level >= 2:
                heading = h.group(2)
                heading_used = False
            table_target = heading_table_target(h.group(2))
            continue
        if table_target and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c) and any(cells):
                continue
            tables[table_target].append(cells)
            continue
        m = LESSON_RE.match(line)
        if not m:
            continue
        if not heading_used:
            htext = heading if heading is not None else "Plan"
            mid = MOD_ID_RE.search(htext)
            if mid:
                module_id = mid.group(1)
            else:
                mn = MOD_NUM_RE.match(htext.strip())
                module_id = mn.group(1) if mn else str(len(modules) + 1)
            modules.append({
                "id": module_id,
                "titulo": clean_module_title(htext),
                "encabezado": htext,
                "nivel": detect_level(htext),
                "lecciones": [],
            })
            heading_used = True
        rest = m.group(4)
        conv = bool(CONV_RE.search(rest))
        desc = DESC_LEAD_RE.sub("", CONV_RE.sub("", rest)).strip()
        lesson = {
            "id": m.group(2),
            "titulo": TITLE_LEAD_RE.sub("", m.group(3).strip()),
            "descripcion": desc,
            "hecha": m.group(1) in ("x", "X"),
            "convalidada": conv,
            "modulo": len(modules) - 1,
            "linea": n,
        }
        modules[-1]["lecciones"].append(lesson["id"])
        lessons.append(lesson)
    return {
        "fm": fm,
        "modulos": modules,
        "lecciones": lessons,
        "bitacora": tables["bitacora"][1:] if tables["bitacora"] else [],
        "huecos": tables["huecos"][1:] if tables["huecos"] else [],
    }


def norm_state(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = re.sub("[\u0300-\u036f]", "", s).strip().lower()
    return re.sub(r"[\s_]+", "-", s)


# --------------------------------------------------------------------------- espacio

def root_dir(opts):
    return Path(opts.get("root") or os.environ.get("COACH_ROOT") or "aprendizaje")


NOTE_ID_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)+)(?=[-_ .])")


def load_notes(topic_dir):
    notes = {}
    d = topic_dir / "lecciones"
    if not d.is_dir():
        return notes
    for p in sorted(d.iterdir(), key=lambda x: x.name):
        if not p.is_file() or not p.name.endswith(".md"):
            continue
        text = read_text(p)
        fm, body = parse_frontmatter(text)
        m = NOTE_ID_RE.match(p.name)
        nid = m.group(1) if m else fm_str(fm, "leccion")
        if not nid:
            continue
        if nid not in notes:
            notes[nid] = {"path": p, "fm": fm or {}, "text": text}
    return notes


def load_topic(root, slug):
    tdir = root / slug
    plan_path = tdir / "PLAN.md"
    if not plan_path.is_file():
        raise CoachError("No existe %s. Crea el tema con: coach init %s --tema \"...\"" % (rel(plan_path), slug))
    text = read_text(plan_path)
    plan = parse_plan(text)
    notes = load_notes(tdir)
    fm = plan["fm"] or {}
    actual_id = fm_str(fm, "leccion_actual")
    for l in plan["lecciones"]:
        note = notes.get(l["id"])
        note_state = norm_state(fm_str(note["fm"], "estado")) if note else ""
        if l["hecha"]:
            l["estado"] = "convalidada" if l["convalidada"] else "completada"
        elif l["id"] == actual_id or note_state == "en-curso":
            l["estado"] = "en-curso"
        else:
            l["estado"] = "pendiente"
        l["nota"] = rel(note["path"]) if note else ""
    return {"slug": slug, "dir": tdir, "plan_path": plan_path, "text": text, "plan": plan, "notes": notes}


def list_topics(root):
    if not root.is_dir():
        return []
    slugs = []
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.is_dir() and not p.name.startswith(".") and (p / "PLAN.md").is_file():
            slugs.append(p.name)
    return slugs


def current_lesson(topic):
    fm = topic["plan"]["fm"] or {}
    actual_id = fm_str(fm, "leccion_actual")
    lessons = topic["plan"]["lecciones"]
    for l in lessons:
        if not l["hecha"] and l["id"] == actual_id:
            return l
    for l in lessons:
        if l["estado"] == "en-curso":
            return l
    for l in lessons:
        if not l["hecha"]:
            return l
    return None


def find_lesson(topic, lid):
    for l in topic["plan"]["lecciones"]:
        if l["id"] == lid:
            return l
    raise CoachError("La lección %s no existe en %s. Añádela primero al plan con el formato "
                     "`- [ ] **%s Título** — descripción`." % (lid, rel(topic["plan_path"]), lid))


def module_label(topic, lesson):
    mod = topic["plan"]["modulos"][lesson["modulo"]]
    return "M%s \u00b7 %s" % (mod["id"], mod["titulo"])


def open_gaps(plan):
    gaps = []
    for cells in plan.get("huecos", []):
        if not any(cells):
            continue
        name = cells[0] if cells else ""
        if not name or name.startswith("[["):
            continue
        estado = cells[4].strip() if len(cells) > 4 else ""
        if CLOSED_RE.match(estado):
            continue
        gaps.append({
            "hueco": name,
            "detectado": cells[1] if len(cells) > 1 else "",
            "intentos": cells[2] if len(cells) > 2 else "",
            "proximo_repaso": cells[3] if len(cells) > 3 else "",
        })
    return gaps


def summarize(topic):
    plan = topic["plan"]
    fm = plan["fm"] or {}
    lessons = plan["lecciones"]
    done = sum(1 for l in lessons if l["hecha"])
    total = len(lessons)
    cur = current_lesson(topic)
    upcoming = []
    if cur is not None:
        idx = next(i for i, l in enumerate(lessons) if l is cur)
        for l in lessons[idx + 1:]:
            if not l["hecha"]:
                upcoming.append({"id": l["id"], "titulo": l["titulo"]})
            if len(upcoming) == 3:
                break
    mods = []
    for mi, mod in enumerate(plan["modulos"]):
        ls = [l for l in lessons if l["modulo"] == mi]
        mods.append({
            "id": mod["id"],
            "titulo": mod["titulo"],
            "nivel": mod["nivel"],
            "hechas": sum(1 for l in ls if l["hecha"]),
            "total": len(ls),
        })
    return {
        "slug": topic["slug"],
        "tema": fm_str(fm, "tema") or topic["slug"],
        "area": fm_str(fm, "area"),
        "nivel_actual": fm_str(fm, "nivel_actual"),
        "nivel_objetivo": fm_str(fm, "nivel_objetivo"),
        "actualizado": fm_str(fm, "actualizado"),
        "hechas": done,
        "total": total,
        "porcentaje": (done * 100 // total) if total else 0,
        "actual": {"id": cur["id"], "titulo": cur["titulo"], "estado": cur["estado"]} if cur else None,
        "proximas": upcoming,
        "modulos": mods,
        "lecciones": [
            {"id": l["id"], "titulo": l["titulo"], "estado": l["estado"],
             "modulo": plan["modulos"][l["modulo"]]["id"], "nota": l["nota"]}
            for l in lessons
        ],
        "ultima_sesion": plan["bitacora"][-1] if plan["bitacora"] else None,
        "huecos_abiertos": open_gaps(plan),
        "notas": len(topic["notes"]),
    }


def sorted_summaries(root, only=None):
    topics = []
    for slug in list_topics(root):
        if only and slug != only:
            continue
        topics.append(load_topic(root, slug))
    sums = [summarize(t) for t in topics]
    sums.sort(key=lambda s: s["slug"])
    sums.sort(key=lambda s: s["actualizado"], reverse=True)
    return sums


# --------------------------------------------------------------------------- git

def _git(args):
    try:
        r = subprocess.run(["git"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
    except (FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def git_paths():
    top = _git(["rev-parse", "--show-toplevel"])
    if top is None:
        cur = Path.cwd().resolve()
        for d in [cur] + list(cur.parents):
            if (d / ".git").is_dir():
                return d, d / ".git" / "info" / "exclude"
        return None, None
    if not top:
        return None, None
    gp = _git(["rev-parse", "--git-path", "info/exclude"])
    if not gp:
        return None, None
    p = Path(gp)
    if not p.is_absolute():
        p = Path.cwd() / p
    return Path(top), p


def exclude_from_git(root, opts):
    if opts.get("versionar"):
        out("\u2139 La carpeta %s se versionará con git (--versionar)." % rel(root))
        return
    top, exclude = git_paths()
    if top is None:
        out("\u2139 No es un repositorio git: no hace falta excluir %s." % rel(root))
        return
    try:
        rp = os.path.relpath(str(root.resolve()), str(top.resolve()))
    except ValueError:
        return
    if rp.startswith(".."):
        return
    entry = "/" + rp.replace(os.sep, "/").strip("/") + "/"
    target = (top / ".gitignore") if opts.get("gitignore") else exclude
    existing = read_text(target) if target.is_file() else ""
    variants = {entry, entry.rstrip("/"), entry.lstrip("/"), entry.strip("/")}
    if any(l.strip() in variants for l in existing.split("\n")):
        out("\U0001F648 Git: '%s' ya estaba excluido en %s." % (entry, rel(target)))
        return
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing += "# hb-coach: espacio de aprendizaje local\n" + entry + "\n"
    write_text(target, existing)
    if opts.get("gitignore"):
        out("\U0001F648 Git: añadido '%s' a %s." % (entry, rel(target)))
    else:
        out("\U0001F648 Git: añadido '%s' a %s (no se versiona y no modifica .gitignore)." % (entry, rel(target)))


# --------------------------------------------------------------------------- plantillas

def render_template(name, values):
    p = TEMPLATES / name
    if not p.is_file():
        raise CoachError("Falta la plantilla %s" % p)
    s = read_text(p)
    for k, v in values.items():
        s = s.replace("{{%s}}" % k, v)
    return s


# --------------------------------------------------------------------------- build

def collect_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in filenames:
            full = Path(dirpath) / fn
            if fn.endswith(".md") and not fn.startswith(".") and full.is_file():
                relp = full.relative_to(root).as_posix()
                files.append(relp)
    files.sort()
    return files


def json_for_html(obj):
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def build(root, quiet=False):
    if not VIEWER.is_file():
        raise CoachError("No se encuentra la plantilla del cuaderno: %s" % VIEWER)
    if not root.is_dir():
        raise CoachError("No existe %s. Crea un tema con: coach init <slug> --tema \"...\"" % rel(root))
    files = collect_files(root)
    data = {
        "version": 1,
        "generado": iso_now(),
        "raiz": root.resolve().name,
        "archivos": {f: read_text(root / f) for f in files},
    }
    template = read_text(VIEWER)
    if DATA_PLACEHOLDER not in template:
        raise CoachError("La plantilla del cuaderno no contiene el marcador de datos.")
    html = template.replace(DATA_PLACEHOLDER, json_for_html(data), 1)
    target = root / "cuaderno.html"
    write_text(target, html)
    if not quiet:
        out("\U0001F4D3 Cuaderno actualizado: %s (%d archivos)" % (rel(target), len(files)))
        out("   Abrir: %s" % target.resolve().as_uri())
    return target


# --------------------------------------------------------------------------- comandos

def cmd_init(pos, opts):
    if not pos:
        raise CoachError("Uso: coach init <slug> --tema \"Título del tema\" [--area android]")
    raw = pos[0]
    slug = slugify(raw, 0)
    if not slug:
        raise CoachError("Slug inválido: %s" % raw)
    if slug != raw:
        out("\u2139 Slug normalizado: '%s' -> '%s'" % (raw, slug))
    tema = (opts.get("tema") or raw).strip()
    root = root_dir(opts)
    created_root = not root.is_dir()
    root.mkdir(parents=True, exist_ok=True)
    if created_root:
        out("\U0001F4C1 Creada la carpeta %s" % rel(root))
    readme = root / "README.md"
    if not readme.is_file():
        write_text(readme, render_template("README-aprendizaje.md", {"FECHA": today()}))
    metodo = root / "METODO.md"
    if not metodo.is_file():
        write_text(metodo, render_template("METODO.md", {"FECHA": today()}))
        out("\U0001F91D Acuerdo de método: %s (complétalo en la primera sesión)" % rel(metodo))
    exclude_from_git(root, opts)
    tdir = root / slug
    values = {
        "TEMA_YAML": yaml_quote(tema),
        "TEMA": tema,
        "SLUG": slug,
        "AREA_YAML": fmt_value((opts.get("area") or "general").strip()),
        "NIVEL_OBJETIVO_YAML": fmt_value((opts.get("nivel-objetivo") or "avanzado").strip()),
        "FECHA": today(),
    }
    plan = tdir / "PLAN.md"
    if plan.is_file() and not opts.get("force"):
        out("\u2139 %s ya existe: no se sobrescribe (usa --force para reemplazarlo)." % rel(plan))
    else:
        write_text(plan, render_template("PLAN.md", values))
        out("\U0001F5FA Plan creado: %s" % rel(plan))
    for name in ("GLOSARIO.md", "DUDAS.md"):
        p = tdir / name
        if not p.is_file():
            write_text(p, render_template(name, values))
    (tdir / "lecciones").mkdir(parents=True, exist_ok=True)
    out("\u2714 Tema '%s' listo en %s" % (slug, rel(tdir)))
    if not opts.get("no-build"):
        build(root)


def cmd_leccion(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach leccion <slug> <id>")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    lesson = find_lesson(topic, pos[1])
    note = topic["notes"].get(lesson["id"])
    if note:
        path = note["path"]
        out("\U0001F4DD Nota existente de la lección %s: %s" % (lesson["id"], rel(path)))
    else:
        name = "%s-%s.md" % (lesson["id"], slugify(lesson["titulo"]) or "leccion")
        path = topic["dir"] / "lecciones" / name
        fm = topic["plan"]["fm"] or {}
        write_text(path, render_template("LECCION.md", {
            "LECCION": lesson["id"],
            "TITULO_YAML": yaml_quote(lesson["titulo"]),
            "TITULO": lesson["titulo"],
            "MODULO_YAML": yaml_quote(module_label(topic, lesson)),
            "DESCRIPCION": strip_links(lesson["descripcion"]),
            "TEMA": fm_str(fm, "tema") or topic["slug"],
            "SLUG": topic["slug"],
            "FECHA": today(),
        }))
        out("\U0001F4DD Nota creada para la lección %s: %s" % (lesson["id"], rel(path)))
    if lesson["hecha"]:
        out("\u2139 La lección %s ya estaba completada: se usa como repaso (el progreso no cambia)." % lesson["id"])
    else:
        text = set_fm(topic["text"], "leccion_actual", lesson["id"])
        text = set_fm(text, "actualizado", today())
        write_text(topic["plan_path"], text)
        if note is None or norm_state(fm_str(note["fm"], "estado")) != "en-curso":
            ntext = read_text(path)
            write_text(path, set_fm(ntext, "estado", "en-curso"))
        out("\u25B6 Lección actual: %s %s" % (lesson["id"], lesson["titulo"]))
    if not opts.get("no-build"):
        build(root)


def _set_line(text, line_no, fn):
    lines = text.split("\n")
    lines[line_no] = fn(lines[line_no])
    return "\n".join(lines)


def cmd_completar(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach completar <slug> <id> [--convalidada]")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    lesson = find_lesson(topic, pos[1])
    conv = bool(opts.get("convalidada"))
    lessons = topic["plan"]["lecciones"]
    mod_index = lesson["modulo"]
    mod_before = all(l["hecha"] for l in lessons if l["modulo"] == mod_index)
    was_done = lesson["hecha"]

    def mark(line):
        line = re.sub(r"\[[ xX]\]", "[x]", line, count=1)
        if conv and not CONV_RE.search(line):
            line = line.rstrip() + " (convalidada)"
        return line

    text = _set_line(topic["text"], lesson["linea"], mark)
    text = set_fm(text, "actualizado", today())
    lesson["hecha"] = True
    idx = next(i for i, l in enumerate(lessons) if l is lesson)
    nxt = None
    for l in lessons[idx + 1:] + lessons[:idx]:
        if not l["hecha"]:
            nxt = l
            break
    fm = topic["plan"]["fm"] or {}
    cur_id = fm_str(fm, "leccion_actual")
    cur_obj = next((l for l in lessons if l["id"] == cur_id), None)
    if cur_id == lesson["id"] or not cur_id or cur_obj is None or cur_obj["hecha"]:
        text = set_fm(text, "leccion_actual", nxt["id"] if nxt else "")
    write_text(topic["plan_path"], text)
    note = topic["notes"].get(lesson["id"])
    if note:
        ntext = set_fm(note["text"], "estado", "convalidada" if conv else "completada")
        ntext = set_fm(ntext, "fin", today())
        write_text(note["path"], ntext)
    done = sum(1 for l in lessons if l["hecha"])
    total = len(lessons)
    pct = done * 100 // total if total else 0
    if was_done:
        out("\u2139 La lección %s ya estaba completada." % lesson["id"])
    label = "convalidada" if conv else "completada"
    out("\u2714 Lección %s %s \u00b7 %s %d/%d (%d%%)" % (lesson["id"], label, topic["slug"], done, total, pct))
    mod_after = all(l["hecha"] for l in lessons if l["modulo"] == mod_index)
    if mod_after and not mod_before:
        mod = topic["plan"]["modulos"][mod_index]
        out("\U0001F389 Módulo %s completado: %s" % (mod["id"], mod["titulo"]))
    if nxt:
        out("\u25B6 Siguiente: %s %s" % (nxt["id"], nxt["titulo"]))
    else:
        out("\U0001F3C1 Plan completado. Hora del proyecto final y de un repaso general.")
    if not opts.get("no-build"):
        build(root)


def cmd_reabrir(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach reabrir <slug> <id>")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    lesson = find_lesson(topic, pos[1])

    def unmark(line):
        line = re.sub(r"\[[ xX]\]", "[ ]", line, count=1)
        line = re.sub("\\s*\\(convalidada\\)|\\s*\u23ed\ufe0f?", "", line, flags=re.I)
        return line

    text = _set_line(topic["text"], lesson["linea"], unmark)
    text = set_fm(text, "leccion_actual", lesson["id"])
    text = set_fm(text, "actualizado", today())
    write_text(topic["plan_path"], text)
    note = topic["notes"].get(lesson["id"])
    if note:
        write_text(note["path"], set_fm(note["text"], "estado", "en-curso"))
    out("\u21BA Lección %s reabierta y marcada como actual." % lesson["id"])
    if not opts.get("no-build"):
        build(root)


STATE_ICON = {"completada": "\u2714", "convalidada": "\u23ED", "en-curso": "\u25B6", "pendiente": "\u00b7"}
LEVEL_LABEL = {"basico": "B\u00e1sico", "intermedio": "Intermedio", "avanzado": "Avanzado", "experto": "Experto"}


def cmd_estado(pos, opts):
    root = root_dir(opts)
    only = pos[0] if pos else None
    if only and not (root / only / "PLAN.md").is_file():
        raise CoachError("No existe el tema '%s' en %s." % (only, rel(root)))
    sums = sorted_summaries(root, only)
    if opts.get("json"):
        out(json.dumps({"raiz": rel(root), "temas": sums}, ensure_ascii=False, indent=2))
        return
    if not root.is_dir() or not sums:
        out("\U0001F4DA Aún no hay temas en %s." % rel(root))
        out("   Crea uno con: coach init <slug> --tema \"Título del tema\"")
        return
    n = len(sums)
    out("\U0001F4DA Aprendizaje \u00b7 %d tema%s \u00b7 raíz: %s" % (n, "" if n == 1 else "s", rel(root)))
    for s in sums:
        out("")
        out("\u25A0 %s \u2014 %s" % (s["slug"], s["tema"]))
        out("  Progreso  %s %d/%d \u00b7 %d%%" % (bar(s["hechas"], s["total"]), s["hechas"], s["total"], s["porcentaje"]))
        niv = "%s \u2192 %s" % (s["nivel_actual"] or "?", s["nivel_objetivo"] or "?")
        out("  Nivel     %s \u00b7 área: %s \u00b7 actualizado: %s" % (niv, s["area"] or "-", s["actualizado"] or "-"))
        if s["actual"]:
            a = s["actual"]
            out("  Actual    %s %s (%s)" % (a["id"], a["titulo"], a["estado"]))
        else:
            out("  Actual    \u2014 (todas las lecciones están hechas)")
        if s["proximas"]:
            out("  Próximas  " + " \u00b7 ".join("%s %s" % (p["id"], p["titulo"]) for p in s["proximas"]))
        out("  Módulos   " + " \u00b7 ".join("M%s %d/%d" % (m["id"], m["hechas"], m["total"]) for m in s["modulos"]))
        if s["huecos_abiertos"]:
            g = s["huecos_abiertos"]
            fechas = sorted(x["proximo_repaso"] for x in g if x["proximo_repaso"].strip())
            extra = (" \u00b7 próximo repaso: %s" % fechas[0]) if fechas else ""
            out("  Huecos    %d abierto%s%s \u00b7 %s" % (len(g), "" if len(g) == 1 else "s", extra, g[0]["hueco"]))
        if s["ultima_sesion"]:
            out("  Sesión    " + " \u00b7 ".join(c for c in s["ultima_sesion"] if c))
        out("  Notas     %d en %s" % (s["notas"], rel(root / s["slug"] / "lecciones")))
        if only:
            for m in s["modulos"]:
                nivel = (" [%s]" % LEVEL_LABEL.get(m["nivel"], m["nivel"])) if m["nivel"] else ""
                out("")
                out("  M%s \u00b7 %s%s %d/%d" % (m["id"], m["titulo"], nivel, m["hechas"], m["total"]))
                for l in s["lecciones"]:
                    if l["modulo"] == m["id"]:
                        extra = "" if l["estado"] in ("pendiente", "completada") else " (%s)" % l["estado"]
                        out("    %s %s %s%s" % (STATE_ICON[l["estado"]], l["id"], l["titulo"], extra))
    out("")
    out("\U0001F4D3 Cuaderno: %s" % rel(root / "cuaderno.html"))


MERMAID_TYPES = {
    "flowchart", "graph", "sequencediagram", "classdiagram", "classdiagram-v2", "statediagram",
    "statediagram-v2", "erdiagram", "journey", "gantt", "pie", "quadrantchart", "requirementdiagram",
    "gitgraph", "c4context", "c4container", "c4component", "c4dynamic", "c4deployment", "mindmap",
    "timeline", "zenuml", "sankey", "sankey-beta", "xychart", "xychart-beta", "block", "block-beta",
    "packet", "packet-beta", "kanban", "architecture", "architecture-beta", "radar", "radar-beta",
    "treemap", "treemap-beta",
}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REQUIRED_NOTE_SECTIONS = [
    ("Resumen con tus palabras", re.compile(r"^#{2,3}\s+.*resumen con tus palabras", re.I | re.M)),
    ("Fuentes", re.compile(r"^#{2,3}\s+.*fuentes", re.I | re.M)),
]


def prose_only(text):
    t = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    keep, fence = [], None
    for line in t.split("\n"):
        m = re.match(r"^\s*(```+|~~~+)", line)
        if fence is None:
            if m:
                fence = m.group(1)[:3]
                continue
            keep.append(re.sub(r"`[^`]*`", "", line))
        elif line.strip().startswith(fence) and line.strip().strip(fence[0]) == "":
            fence = None
    return "\n".join(keep)


def slug_text(value):
    return slugify(value, 0)


def lint_markdown(relp, text, root, report):
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    fence = None
    block = []
    long_code = 0
    longest = 0
    table_code = 0
    headings = set()
    for line in body.split("\n"):
        m = re.match(r"^\s*(```+|~~~+)\s*([\w-]*)", line)
        if fence is None:
            if m:
                fence = {"mark": m.group(1)[:3], "lang": m.group(2).lower()}
                block = []
                continue
            hm = HEADING_RE.match(line)
            if hm:
                headings.add(slug_text(hm.group(2)))
                continue
            if line.strip().startswith("|"):
                for cell in line.strip().strip("|").split("|"):
                    for code in re.findall(r"`([^`]+)`", cell):
                        if len(code) > 40:
                            table_code += 1
            continue
        if line.strip().startswith(fence["mark"]) and line.strip().strip(fence["mark"][0]) == "":
            if fence["lang"] == "mermaid":
                lint_mermaid(relp, block, report)
            else:
                for code_line in block:
                    if len(code_line) > 80:
                        long_code += 1
                        longest = max(longest, len(code_line))
            fence = None
            continue
        block.append(line)
    if fence is not None:
        report("error", relp, "bloque de código sin cerrar (falta ``` final)")
    if long_code:
        report("aviso", relp, "%d línea(s) de código de más de 80 caracteres (la más larga: %d): se desbordan en el cuaderno"
               % (long_code, longest))
    if table_code:
        report("aviso", relp, "%d celda(s) de tabla con código largo: muévelo a un bloque de código" % table_code)
    prose = prose_only(text)
    pending = len(re.findall(r"\[\[COMPLETAR", prose))
    if pending:
        report("aviso", relp, "quedan %d marcador(es) [[COMPLETAR]] sin rellenar" % pending)
    base = (root / relp).parent
    for href in LINK_RE.findall(prose):
        if href.startswith("#"):
            anchor = slug_text(href[1:])
            if anchor and anchor not in headings and not (anchor.startswith("s-") and anchor[2:] in headings):
                report("aviso", relp, "enlace interno «%s» sin encabezado que coincida" % href)
            continue
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith("/"):
            continue
        target = href.split("#", 1)[0]
        if not target.endswith(".md"):
            continue
        target = target.replace("%20", " ")
        if not (base / target).is_file():
            report("aviso", relp, "enlace roto a %s" % href)


def lint_mermaid(relp, block, report):
    lines = [l for l in block]
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    first = ""
    for l in lines[i:]:
        s = l.strip()
        if s and not s.startswith("%%"):
            first = s
            break
    if not first:
        report("error", relp, "diagrama mermaid vacío")
        return
    kind = first.split()[0].lower()
    if kind not in MERMAID_TYPES:
        report("aviso", relp, "tipo de diagrama mermaid desconocido: '%s'" % first.split()[0])
    long_labels = []
    for m in re.finditer(r"\[([^\[\]]+)\]|\(([^()]+)\)|\{([^{}]+)\}", "\n".join(lines)):
        label = next(g for g in m.groups() if g is not None)
        label = label.strip().strip('"').strip("'").strip()
        if len(label) > 24:
            long_labels.append(label)
    if long_labels:
        longest = max(long_labels, key=len)
        report("aviso", relp, "%d etiqueta(s) de Mermaid de más de 24 caracteres («%s»): acorta o usa <br/>"
               % (len(long_labels), longest[:40]))


def cmd_check(pos, opts):
    root = root_dir(opts)
    only = pos[0] if pos else None
    counts = {"error": 0, "aviso": 0}

    def report(kind, where, msg):
        counts[kind] += 1
        icon = "\u2716" if kind == "error" else "\u26A0"
        out("  %s %s: %s" % (icon, where, msg))

    out("\U0001F50E Revisando %s" % rel(root))
    if not root.is_dir():
        report("error", rel(root), "no existe; crea un tema con coach init")
        out("\u2716 %d error(es)" % counts["error"])
        return 1
    slugs = list_topics(root)
    if only and only not in slugs:
        report("error", only, "no existe %s" % rel(root / only / "PLAN.md"))
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.is_dir() and not p.name.startswith(".") and p.name not in slugs and (not only or p.name == only):
            if any(f.endswith(".md") for f in os.listdir(str(p))):
                report("aviso", p.name + "/", "carpeta con notas pero sin PLAN.md")
    newest = 0.0
    for slug in slugs:
        if only and slug != only:
            continue
        topic = load_topic(root, slug)
        plan = topic["plan"]
        where = slug + "/PLAN.md"
        fm = plan["fm"]
        if fm is None:
            report("error", where, "falta el frontmatter (bloque --- al inicio)")
            fm = {}
        else:
            if not fm_str(fm, "tema"):
                report("error", where, "falta el campo 'tema' en el frontmatter")
            if fm_str(fm, "slug") and fm_str(fm, "slug") != slug:
                report("aviso", where, "el slug '%s' no coincide con la carpeta '%s'" % (fm_str(fm, "slug"), slug))
        lessons = plan["lecciones"]
        if not lessons:
            report("error", where, "no hay lecciones con el formato `- [ ] **1.1 Título** — descripción`")
        seen = set()
        for l in lessons:
            if l["id"] in seen:
                report("error", where, "id de lección duplicado: %s" % l["id"])
            seen.add(l["id"])
        for a, b in zip(lessons, lessons[1:]):
            if id_key(b["id"]) <= id_key(a["id"]):
                report("aviso", where, "orden de ids inesperado: %s después de %s" % (b["id"], a["id"]))
        cur = fm_str(fm, "leccion_actual")
        if cur and cur not in seen:
            report("aviso", where, "leccion_actual '%s' no existe en el plan" % cur)
        if plan["modulos"] and not any(m["nivel"] for m in plan["modulos"]):
            report("aviso", where, "ningún módulo indica nivel (Básico/Intermedio/Avanzado/Experto)")
        if not re.search(r"^#{2,3}\s+.*huecos", topic["text"], re.I | re.M):
            report("aviso", where, "falta la sección «Huecos abiertos» (aunque esté vacía)")
        for name in ("GLOSARIO.md", "DUDAS.md"):
            if not (topic["dir"] / name).is_file():
                report("aviso", slug + "/" + name, "no existe")
        ldir = topic["dir"] / "lecciones"
        if ldir.is_dir():
            for f in sorted(ldir.iterdir(), key=lambda x: x.name):
                if not f.name.endswith(".md"):
                    continue
                w = "%s/lecciones/%s" % (slug, f.name)
                m = NOTE_ID_RE.match(f.name)
                if not m:
                    report("aviso", w, "el nombre debe empezar con el id de la lección (p. ej. 1.2-titulo.md)")
                    continue
                if m.group(1) not in seen:
                    report("aviso", w, "la lección %s no existe en el plan" % m.group(1))
                ntext = read_text(f)
                nfm, nbody = parse_frontmatter(ntext)
                if nfm is None:
                    report("aviso", w, "falta el frontmatter")
                elif norm_state(fm_str(nfm, "estado")) not in NOTE_STATES:
                    report("aviso", w, "estado '%s' no válido (usa en-curso, completada o convalidada)" % fm_str(nfm, "estado"))
                if nfm is not None and norm_state(fm_str(nfm, "estado")) == "completada":
                    missing = [t for t, rx in REQUIRED_NOTE_SECTIONS if not rx.search(nbody)]
                    if missing:
                        report("aviso", w, "la nota está completada pero le faltan secciones: %s" % ", ".join(missing))
    for relp in collect_files(root):
        if only and not relp.startswith(only + "/"):
            continue
        full = root / relp
        newest = max(newest, full.stat().st_mtime)
        lint_markdown(relp, read_text(full), root, report)
    nb = root / "cuaderno.html"
    if not nb.is_file():
        report("aviso", "cuaderno.html", "no existe; ejecuta coach build")
    elif nb.stat().st_mtime + 1 < newest:
        report("aviso", "cuaderno.html", "desactualizado; ejecuta coach build")
    if counts["error"]:
        out("\u2716 %d error(es), %d aviso(s)" % (counts["error"], counts["aviso"]))
        return 1
    out("\u2714 Sin errores (%d aviso%s)" % (counts["aviso"], "" if counts["aviso"] == 1 else "s"))
    return 0


def read_libs():
    template = read_text(VIEWER)
    m = re.search(r"<script id=\"coach-libs\" type=\"application/json\">(.*?)</script>", template, re.S)
    if not m:
        raise CoachError("La plantilla del cuaderno no declara sus librerías (coach-libs).")
    return json.loads(m.group(1))


def cmd_vendor(pos, opts):
    root = root_dir(opts)
    if not root.is_dir():
        raise CoachError("No existe %s. Crea un tema primero con coach init." % rel(root))
    libs = read_libs()
    base = (os.environ.get("COACH_CDN") or libs["jsdelivr"]).rstrip("/")
    vdir = root / ".vendor"
    vdir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for lib in libs["scripts"]:
        dest = vdir / lib["file"]
        if dest.is_file() and dest.stat().st_size > 0 and not opts.get("force"):
            out("  = %s (ya descargado)" % lib["file"])
            continue
        url = "%s/%s" % (base, lib["npm"])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hb-coach/" + VERSION})
            with urllib.request.urlopen(req, timeout=90) as resp:
                content = resp.read()
            with open(str(dest), "wb") as f:
                f.write(content)
            out("  \u2193 %s (%s)" % (lib["file"], fmt_kb(len(content))))
        except Exception as e:  # noqa: BLE001
            failures += 1
            out("  \u2716 %s: %s" % (lib["file"], e))
    if failures:
        out("\u2716 %d descarga(s) fallaron. Revisa tu conexión o prueba con la otra versión del script (coach.py / coach.mjs)." % failures)
        return 1
    out("\u2714 Librerías en %s: el cuaderno funciona sin conexión." % rel(vdir))
    return 0


def parse_args(argv):
    pos, opts = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and len(a) > 2:
            key = a[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                opts[k] = v
            elif key in BOOL_FLAGS:
                opts[key] = True
            else:
                if i + 1 >= len(argv):
                    raise CoachError("Falta el valor de --%s" % key)
                opts[key] = argv[i + 1]
                i += 1
        elif a == "-h":
            opts["help"] = True
        else:
            pos.append(a)
        i += 1
    return pos, opts


COMMANDS = {
    "init": cmd_init,
    "leccion": cmd_leccion,
    "completar": cmd_completar,
    "reabrir": cmd_reabrir,
    "estado": cmd_estado,
    "check": cmd_check,
    "vendor": cmd_vendor,
}


def main(argv):
    try:
        pos, opts = parse_args(argv)
        if not pos or opts.get("help") or pos[0] in ("ayuda", "help"):
            out(AYUDA.format(v=VERSION))
            return 0
        cmd, rest = pos[0], pos[1:]
        if cmd == "version":
            out("hb-coach %s" % VERSION)
            return 0
        if cmd == "build":
            build(root_dir(opts))
            return 0
        fn = COMMANDS.get(cmd)
        if fn is None:
            raise CoachError("Comando desconocido: %s. Usa 'ayuda' para ver los comandos." % cmd)
        code = fn(rest, opts)
        return code or 0
    except CoachError as e:
        sys.stdout.flush()
        sys.stderr.write("\u2716 %s\n" % e)
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    try:
        code = main(sys.argv[1:])
        sys.stdout.flush()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        code = 0
    sys.exit(code)
