#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coach.py — herramienta de hb-coach (Python 3.8+, sin dependencias).

Gestiona el espacio de aprendizaje (por defecto ./aprendizaje): plan por módulos con
exámenes, notas de lección, glosario, dudas, huecos, calendario de repasos, acuerdo de
método y el cuaderno HTML. Lo determinista lo hace este script; el coach escribe el
contenido pedagógico.

Ejemplos:
  python3 coach.py siguiente
  python3 coach.py init hilt --tema "Hilt: inyección de dependencias en Android" --area android
  python3 coach.py leccion hilt 1.1
  python3 coach.py nota hilt 1.1 --desde bloque.md
  python3 coach.py completar hilt 1.1
  python3 coach.py sesion hilt --logros "Construyó el contenedor manual"
Ejecuta `python3 coach.py ayuda` para ver todos los comandos.
"""

import json
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = "3.1.0"
# Formato de aprendizaje/: 1 = hb-coach 3.0.x (implícito); 2 = exámenes por módulo y calendario de repasos.
FORMATO = 2
# Días entre repasos de una lección completada: intervalos crecientes (Cepeda et al., 2008).
LESSON_INTERVALS = (3, 7, 14, 30, 60)
# Un hueco ya falló una vez: se repasa al día siguiente y el intervalo crece más despacio.
GAP_INTERVALS = (1, 3, 7, 14, 30)
GAP_CLOSE_STREAK = 3      # repasos bien seguidos a partir de los que se propone cerrar un hueco
EXAM_PASS = 80            # % mínimo para aprobar un examen de módulo (aprendizaje para el dominio)
REVIEW_LIMIT = 6          # elementos por repaso: caben en 5 a 10 minutos
STDIN_WAIT = 1.0          # segundos que se espera contenido en stdin (un heredoc ya está en el búfer)

SCRIPT = Path(__file__).resolve()
SKILL_DIR = SCRIPT.parent.parent
ASSETS = SKILL_DIR / "assets"
TEMPLATES = ASSETS / "plantillas"
VIEWER = ASSETS / "cuaderno.html"
DATA_PLACEHOLDER = '"__COACH_DATA__"'
BOOL_FLAGS = {"json", "no-build", "convalidada", "force", "forzar", "versionar", "gitignore", "help",
              "bien", "mal", "cerrar", "dry-run", "mapa"}
NOTE_STATES = ("en-curso", "completada", "convalidada")
EXAM_STATES = ("pendiente", "aprobado", "repetir")

AYUDA = """hb-coach — herramienta del espacio de aprendizaje (v{v})

Uso: coach <comando> [argumentos] [--root DIR]

Empezar
  siguiente [slug] [--json]        Meta de hoy, el paso que toca y sus comandos exactos.
  init <slug> --tema "Título" [--area A] [--nivel-objetivo N] [--playground URL] [--mapa]
                                   Crea <raíz>/<slug>/ (PLAN, GLOSARIO, DUDAS, lecciones/) y, en la
                                   raíz, README.md y METODO.md. Excluye la carpeta de git con
                                   .git/info/exclude (--versionar no la excluye; --gitignore usa .gitignore).
  metodo [--<clave> "valor" ...] [--motivo "..."]
                                   Muestra o actualiza METODO.md. Claves: {claves}.

Durante la lección
  leccion <slug> <id>              Crea la nota de la lección y la marca como actual.
  nota <slug> <id|Mn> [--desde ARCHIVO] [--seccion objetivos|resumen|fuentes] [--historial "texto"]
                                   Sin --seccion, añade el Markdown (stdin o --desde) antes del cierre
                                   de la nota; con --seccion, reemplaza esa sección; --historial añade
                                   una fila fechada. Mn es la nota del examen del módulo n.
  glosario <slug> "Término" "Definición" ["Término" "Definición" ...] [--leccion ID]
  duda <slug> "Pregunta" --respuesta "..." [--contexto ...] [--explicacion ...] [--leccion ID]
                                   [--fuente "[Título](https://...)"]
  hueco <slug> "Descripción" [--leccion ID]    Abre un hueco; se repasa mañana.
  hueco <slug> Hn --bien|--mal|--cerrar        Registra el repaso del hueco y lo reprograma.
  completar <slug> <id> [--convalidada] [--forzar]
  reabrir <slug> <id>

Repasar y evaluar
  repaso <slug> [--json]           Lo que vence hoy (lecciones y huecos), mezclado y con sus preguntas.
  repaso <slug> <id|Hn> --bien|--mal
  examen <slug> <módulo>           Prepara el examen del módulo: alcance y nota en examenes/.
  examen <slug> <módulo> --resultado 5/6 [--tarea si|no]

Cerrar y consultar
  sesion <slug> --logros "..." [--lecciones "1.2, 1.3"] [--siguiente "..."]
                                   Fila de bitácora, cuaderno, check y siguiente paso.
  estado [slug] [--json]           Progreso, exámenes, huecos y repasos.
  build                            Regenera <raíz>/cuaderno.html.
  check [slug]                     Valida formato, enlaces, anclas, diagramas y legibilidad.
  vendor [--force]                 Descarga las librerías del cuaderno a <raíz>/.vendor (sin conexión).
  migrar [--dry-run]               Pasa un espacio de hb-coach 3.0.x al formato {formato}, con copia de seguridad.
  version                          Muestra la versión.

Opciones comunes
  --root DIR    Carpeta de aprendizaje (por defecto ./aprendizaje o $COACH_ROOT).
  --no-build    No regenerar el cuaderno después de un cambio.
"""


# --------------------------------------------------------------------------- utilidades

class CoachError(Exception):
    pass


def out(msg=""):
    sys.stdout.write(msg + "\n")


def read_text(p):
    with open(str(p), "r", encoding="utf-8", errors="replace", newline="") as f:
        s = f.read()
    if s.startswith("\ufeff"):
        s = s[1:]
    return s.replace("\r\n", "\n")


def write_text(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def rel(p):
    try:
        return os.path.relpath(str(p), os.getcwd())
    except ValueError:
        return str(p)


def now():
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde and sde.strip().isdigit():
        return datetime.fromtimestamp(int(sde), tz=timezone.utc)
    return datetime.now().astimezone()


def today_date():
    return now().date()


def today():
    return today_date().isoformat()


def iso_now():
    d = now()
    off = d.utcoffset()
    total = int(off.total_seconds()) if off is not None else 0
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + "%s%02d:%02d" % (sign, total // 3600, (total % 3600) // 60)


DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_date(s):
    m = DATE_RE.search(str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def in_days(n):
    return (today_date() + timedelta(days=n)).isoformat()


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return re.sub("[\u0300-\u036f]", "", s).lower()


def slugify(s, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", fold(s)).strip("-")
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


def plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def read_stdin():
    """Lee el contenido de stdin si llega algo (heredoc o tubería) sin quedarse esperando."""
    try:
        if sys.stdin is None or sys.stdin.closed or sys.stdin.isatty():
            return ""
        if os.name == "posix":
            import select
            ready, _, _ = select.select([sys.stdin], [], [], STDIN_WAIT)
            if not ready:
                return ""
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def content_arg(opts):
    src = opts.get("desde")
    if src:
        p = Path(src)
        if not p.is_file():
            raise CoachError("No existe el archivo %s (--desde)." % src)
        text = read_text(p)
    else:
        text = read_stdin()
    text = text.replace("\r\n", "\n").strip("\n")
    return text


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


def fm_int(fm, key, default=0):
    try:
        return int(fm_str(fm, key))
    except ValueError:
        return default


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


def set_fm_raw(text, key, raw):
    """Como set_fm, pero escribe el valor tal cual (para números)."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                for j in range(1, i):
                    m = FM_KEY_RE.match(lines[j])
                    if m and m.group(1) == key:
                        lines[j] = "%s: %s" % (key, raw)
                        return "\n".join(lines)
                lines.insert(i, "%s: %s" % (key, raw))
                return "\n".join(lines)
    return "---\n%s: %s\n---\n%s" % (key, raw, text)


# --------------------------------------------------------------------------- Markdown: secciones y tablas

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def find_section(lines, rx, level=2, start=0):
    """(línea del encabezado, línea donde termina) de la primera sección ## que coincide con rx."""
    in_fence = False
    head = None
    for i in range(start, len(lines)):
        line = lines[i]
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        h = HEADING_RE.match(line)
        if h and len(h.group(1)) <= level:
            if head is not None:
                return head, i
            if len(h.group(1)) == level and rx.search(h.group(2)):
                head = i
    if head is not None:
        return head, len(lines)
    return None


def split_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def is_separator(cells):
    return any(cells) and all(re.match(r"^:?-{2,}:?$", c) for c in cells if c)


def fmt_row(cells):
    return "| " + " | ".join(cells) + " |"


def cell(s):
    return str(s).replace("\n", " ").replace("|", "\\|").strip()


def first_table(lines, start, end):
    """Primera tabla entre start y end: {'header', 'sep', 'rows': [(i, celdas)], 'last'}."""
    header = None
    i = start
    in_fence = False
    while i < end:
        line = lines[i]
        if FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence and line.strip().startswith("|"):
            if header is None:
                header = i
                if i + 1 < end and is_separator(split_cells(lines[i + 1])):
                    rows = []
                    j = i + 2
                    while j < end and lines[j].strip().startswith("|"):
                        rows.append((j, split_cells(lines[j])))
                        j += 1
                    return {"header": i, "sep": i + 1, "rows": rows, "last": j - 1}
                header = None
        i += 1
    return None


def insert_lines(lines, at, new):
    return lines[:at] + list(new) + lines[at:]


CLOSING_RE = re.compile(r"^##\s+(?:resumen con tus palabras|fuentes|historial|resultado)\b", re.I)


def insert_before_closing(text, content):
    """Inserta un bloque de Markdown antes de las secciones de cierre (o al final)."""
    lines = text.split("\n")
    in_fence = False
    block = content.split("\n")
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and CLOSING_RE.match(line.strip()):
            head = lines[:i]
            while head and head[-1].strip() == "":
                head.pop()
            return "\n".join(head + [""] + block + [""] + lines[i:])
    body = text.rstrip("\n")
    return body + "\n\n" + content + "\n"


def replace_section(text, rx, content, title):
    lines = text.split("\n")
    sec = find_section(lines, rx)
    block = content.split("\n")
    if sec is None:
        return insert_before_closing(text, "## %s\n\n%s" % (title, content))
    head, end = sec
    tail = lines[end:]
    return "\n".join(lines[:head + 1] + [""] + block + [""] + tail)


def append_table_row(text, rx, title, header, row):
    """Añade una fila al final de la primera tabla de la sección; crea sección y tabla si faltan."""
    lines = text.split("\n")
    sec = find_section(lines, rx)
    if sec is None:
        body = text.rstrip("\n")
        return body + "\n\n## %s\n\n%s\n%s\n%s\n" % (
            title, fmt_row(header), fmt_row(["---"] * len(header)), fmt_row(row))
    tbl = first_table(lines, sec[0] + 1, sec[1])
    if tbl is None:
        at = sec[1]
        while at > sec[0] + 1 and lines[at - 1].strip() == "":
            at -= 1
        new = ["", fmt_row(header), fmt_row(["---"] * len(header)), fmt_row(row)]
        return "\n".join(insert_lines(lines, at, new))
    return "\n".join(insert_lines(lines, tbl["last"] + 1, [fmt_row(row)]))


# --------------------------------------------------------------------------- plan

LESSON_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+\*\*([0-9]+(?:\.[0-9]+)+)\.?\s+(.+?)\*\*(.*)$")
# Examen de módulo: «- [ ] **Examen M2** — …». No empieza por un id numérico, así que el
# parser de hb-coach 3.0.x lo ignora (compatibilidad hacia atrás).
EXAM_RE = re.compile(r"^(\s*[-*+]\s+)\[([ xX])\](\s+\*\*Examen\s+M?([0-9]+)[^*]*\*\*)(.*)$", re.I)
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
PROJECT_RE = re.compile(r"\bproyecto\b|\bproject\b", re.I)
HUECOS_RE = re.compile(r"huecos", re.I)
BITACORA_RE = re.compile(r"bit[a\u00e1]cora", re.I)
CLOSED_RE = re.compile(r"^(cerrad|resuelt)", re.I)
PENDING_RE = re.compile(r"\[\[COMPLETAR")


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
            cells = split_cells(line)
            if is_separator(cells):
                continue
            tables[table_target].append(cells)
            continue
        em = EXAM_RE.match(line)
        if em:
            if modules and heading_used:
                modules[-1]["examen"] = {
                    "hecho": em.group(2) in ("x", "X"),
                    "linea": n,
                    "detalle": DESC_LEAD_RE.sub("", em.group(5)).strip(),
                }
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
            titulo = clean_module_title(htext)
            modules.append({
                "id": module_id,
                "titulo": titulo,
                "encabezado": htext,
                "nivel": detect_level(htext),
                "lecciones": [],
                "examen": None,
                "proyecto": bool(PROJECT_RE.search(titulo)),
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
    return re.sub(r"[\s_]+", "-", fold(s).strip())


# --------------------------------------------------------------------------- huecos

GAP_HEADER = ["Hueco", "Detectado", "Intentos", "Próximo repaso", "Estado"]


def gap_rows(text):
    """Huecos de la sección «Huecos abiertos» con su id (H1, H2…), en orden de la tabla."""
    lines = text.split("\n")
    sec = find_section(lines, HUECOS_RE)
    if sec is None:
        return lines, None, []
    tbl = first_table(lines, sec[0] + 1, sec[1])
    rows = []
    if tbl is None:
        return lines, None, rows
    hoy = today_date()
    for idx, cells in tbl["rows"]:
        name = cells[0] if cells else ""
        if not name or name.startswith("[["):
            continue
        cells = (cells + [""] * 5)[:max(5, len(cells))]
        estado = cells[4].strip()
        abierto = not CLOSED_RE.match(estado)
        proximo = parse_date(cells[3])
        rows.append({
            "id": "H%d" % (len(rows) + 1),
            "hueco": name,
            "detectado": cells[1],
            "intentos": cells[2],
            "proximo_repaso": cells[3],
            "estado": estado,
            "abierto": abierto,
            "racha": estado.count("\u2714"),
            "vence": proximo.isoformat() if proximo else "",
            "vencido": bool(abierto and proximo and proximo <= hoy),
            "linea": idx,
            "celdas": cells,
        })
    return lines, tbl, rows


# --------------------------------------------------------------------------- espacio

def root_dir(opts):
    return Path(opts.get("root") or os.environ.get("COACH_ROOT") or "aprendizaje")


NOTE_ID_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)+)(?=[-_ .])")
EXAM_FILE_RE = re.compile(r"^m([0-9]+)(?=[-_ .])", re.I)


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


def load_exams(topic_dir):
    exams = {}
    d = topic_dir / "examenes"
    if not d.is_dir():
        return exams
    for p in sorted(d.iterdir(), key=lambda x: x.name):
        m = EXAM_FILE_RE.match(p.name)
        if p.is_file() and p.name.endswith(".md") and m and m.group(1) not in exams:
            text = read_text(p)
            fm, _ = parse_frontmatter(text)
            exams[m.group(1)] = {"path": p, "fm": fm or {}, "text": text}
    return exams


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
    return {"slug": slug, "dir": tdir, "plan_path": plan_path, "text": text, "plan": plan,
            "notes": notes, "exams": load_exams(tdir)}


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


def find_module(topic, mid):
    mid = re.sub(r"^[mM]", "", str(mid))
    for i, mod in enumerate(topic["plan"]["modulos"]):
        if mod["id"] == mid:
            return i, mod
    ids = ", ".join(m["id"] for m in topic["plan"]["modulos"]) or "ninguno"
    raise CoachError("El módulo %s no existe en %s (módulos: %s)." % (mid, rel(topic["plan_path"]), ids))


def module_label(topic, lesson):
    mod = topic["plan"]["modulos"][lesson["modulo"]]
    return "M%s \u00b7 %s" % (mod["id"], mod["titulo"])


def open_gaps(plan_text):
    _, _, rows = gap_rows(plan_text)
    return [{"id": g["id"], "hueco": g["hueco"], "detectado": g["detectado"], "intentos": g["intentos"],
             "proximo_repaso": g["proximo_repaso"], "vencido": g["vencido"]} for g in rows if g["abierto"]]


def lesson_reviews(topic):
    """Repasos programados de las lecciones completadas (fecha en el frontmatter de su nota)."""
    hoy = today_date()
    items = []
    titles = {l["id"]: l for l in topic["plan"]["lecciones"]}
    for nid, note in topic["notes"].items():
        l = titles.get(nid)
        if not l or not l["hecha"] or l["convalidada"]:
            continue
        d = parse_date(fm_str(note["fm"], "repaso"))
        if not d:
            continue
        items.append({"tipo": "leccion", "id": nid, "titulo": l["titulo"], "fecha": d.isoformat(),
                      "vencido": d <= hoy, "repasos": fm_int(note["fm"], "repasos")})
    items.sort(key=lambda x: (x["fecha"], id_key(x["id"])))
    return items


def review_state(topic):
    gaps = [g for g in gap_rows(topic["text"])[2] if g["abierto"] and g["vence"]]
    lessons = lesson_reviews(topic)
    due = [{"tipo": "hueco", "id": g["id"], "titulo": g["hueco"], "fecha": g["vence"]} for g in gaps if g["vencido"]]
    due += [{"tipo": "leccion", "id": x["id"], "titulo": x["titulo"], "fecha": x["fecha"]} for x in lessons if x["vencido"]]
    future = [(g["vence"], g["id"]) for g in gaps if not g["vencido"]]
    future += [(x["fecha"], x["id"]) for x in lessons if not x["vencido"]]
    future.sort()
    nxt = {"fecha": future[0][0], "id": future[0][1]} if future else None
    return due, nxt


def root_pending(root):
    metodo = root / "METODO.md"
    return bool(metodo.is_file() and PENDING_RE.search(prose_only(read_text(metodo))))


def plan_pending(topic):
    return bool(PENDING_RE.search(prose_only(topic["text"])))


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
    mods, exams = [], []
    for mi, mod in enumerate(plan["modulos"]):
        ls = [l for l in lessons if l["modulo"] == mi]
        hechas = sum(1 for l in ls if l["hecha"])
        mods.append({"id": mod["id"], "titulo": mod["titulo"], "nivel": mod["nivel"],
                     "hechas": hechas, "total": len(ls), "proyecto": mod["proyecto"]})
        if mod["examen"] is not None:
            note = topic["exams"].get(mod["id"])
            exams.append({"modulo": mod["id"], "titulo": mod["titulo"], "hecho": mod["examen"]["hecho"],
                          "detalle": mod["examen"]["detalle"], "listo": bool(ls) and hechas == len(ls),
                          "nota": rel(note["path"]) if note else ""})
    due, nxt = review_state(topic)
    gaps = [{k: g[k] for k in ("id", "hueco", "detectado", "intentos", "proximo_repaso", "estado", "abierto",
                                "racha", "vencido")} for g in gap_rows(topic["text"])[2]]
    return {
        "slug": topic["slug"],
        "tema": fm_str(fm, "tema") or topic["slug"],
        "area": fm_str(fm, "area"),
        "formato": fm_int(fm, "formato", 1),
        "playground": fm_str(fm, "playground"),
        "nivel_actual": fm_str(fm, "nivel_actual"),
        "nivel_objetivo": fm_str(fm, "nivel_objetivo"),
        "actualizado": fm_str(fm, "actualizado"),
        "hechas": done,
        "total": total,
        "porcentaje": (done * 100 // total) if total else 0,
        "actual": {"id": cur["id"], "titulo": cur["titulo"], "estado": cur["estado"]} if cur else None,
        "proximas": upcoming,
        "modulos": mods,
        "examenes": exams,
        "lecciones": [
            {"id": l["id"], "titulo": l["titulo"], "estado": l["estado"],
             "modulo": plan["modulos"][l["modulo"]]["id"], "nota": l["nota"]}
            for l in lessons
        ],
        "ultima_sesion": plan["bitacora"][-1] if plan["bitacora"] else None,
        "sesiones": len([r for r in plan["bitacora"] if any(r)]),
        "huecos_abiertos": open_gaps(topic["text"]),
        "huecos": gaps,
        "repasos": {"vencidos": due, "proximo": nxt},
        "pendiente": {"plan": plan_pending(topic)},
        "notas": len(topic["notes"]),
    }


def sorted_summaries(root, only=None):
    sums = []
    for slug in list_topics(root):
        if only and slug != only:
            continue
        sums.append(summarize(load_topic(root, slug)))
    sums.sort(key=lambda s: s["slug"])
    sums.sort(key=lambda s: s["actualizado"], reverse=True)
    return sums


def pick_topic(root, slug):
    """El tema pedido o, si no se indica, el más reciente."""
    slugs = list_topics(root)
    if slug:
        if slug not in slugs:
            raise CoachError("No existe el tema '%s' en %s." % (slug, rel(root)))
        return load_topic(root, slug)
    if not slugs:
        return None
    return load_topic(root, sorted_summaries(root)[0]["slug"])


# --------------------------------------------------------------------------- git

def _git(args, cwd):
    try:
        r = subprocess.run(["git"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, cwd=str(cwd))
    except (FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def git_paths(cwd):
    top = _git(["rev-parse", "--show-toplevel"], cwd)
    if top is None:
        cur = Path(cwd).resolve()
        for d in [cur] + list(cur.parents):
            if (d / ".git").is_dir():
                return d, d / ".git" / "info" / "exclude"
        return None, None
    if not top:
        return None, None
    gp = _git(["rev-parse", "--git-path", "info/exclude"], cwd)
    if not gp:
        return None, None
    p = Path(gp)
    if not p.is_absolute():
        p = Path(cwd).resolve() / p
    return Path(top), p


def exclude_from_git(root, opts):
    if opts.get("versionar"):
        out("\u2139 La carpeta %s se versionará con git (--versionar)." % rel(root))
        return
    top, exclude = git_paths(root)
    if top is None:
        out("\u2139 %s no está dentro de un repositorio git: no hace falta excluirla." % rel(root))
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
                files.append(full.relative_to(root).as_posix())
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
        "version": FORMATO,
        "coach": VERSION,
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
    if quiet:
        out("\U0001F4D3 Cuaderno actualizado: %s" % rel(target))
    else:
        out("\U0001F4D3 Cuaderno actualizado: %s (%d archivos)" % (rel(target), len(files)))
        out("   Abrir: %s" % target.resolve().as_uri())
    return target


def maybe_build(root, opts):
    if not opts.get("no-build"):
        build(root, quiet=True)


# --------------------------------------------------------------------------- comandos: crear y método

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
        out("\U0001F91D Acuerdo de método: %s (acuérdalo en la primera sesión con coach metodo)" % rel(metodo))
    exclude_from_git(root, opts)
    tdir = root / slug
    values = {
        "TEMA_YAML": yaml_quote(tema),
        "TEMA": tema,
        "SLUG": slug,
        "AREA_YAML": fmt_value((opts.get("area") or "general").strip()),
        "NIVEL_OBJETIVO_YAML": fmt_value((opts.get("nivel-objetivo") or "avanzado").strip()),
        "PLAYGROUND_YAML": fmt_value((opts.get("playground") or "").strip()),
        "FECHA": today(),
        "EXAMEN_UMBRAL": str(EXAM_PASS),
    }
    plan = tdir / "PLAN.md"
    if plan.is_file() and not opts.get("force"):
        out("\u2139 %s ya existe: no se sobrescribe (usa --force para reemplazarlo)." % rel(plan))
    else:
        write_text(plan, render_template("PLAN.md", values))
        out("\U0001F5FA Plan creado: %s" % rel(plan))
    names = ["GLOSARIO.md", "DUDAS.md"] + (["MAPA.md"] if opts.get("mapa") else [])
    for name in names:
        p = tdir / name
        if not p.is_file():
            write_text(p, render_template(name, values))
            if name == "MAPA.md":
                out("\U0001F9ED Mapa del tema: %s" % rel(p))
    (tdir / "lecciones").mkdir(parents=True, exist_ok=True)
    out("\u2714 Tema '%s' listo en %s" % (slug, rel(tdir)))
    if not opts.get("no-build"):
        build(root)


METODO_KEYS = [
    ("orden", "Orden de cada bloque"),
    ("pasos", "Pasos"),
    ("preguntas", "Preguntas"),
    ("correccion", "Corrección"),
    ("mensajes", "Mensajes"),
    ("ejemplos", "Ejemplos"),
    ("practica", "Práctica"),
    ("verificacion", "Verificación"),
    ("ritmo", "Ritmo"),
    ("profundidad", "Profundidad"),
    ("calentamiento", "Calentamiento"),
    ("repasos", "Repasos"),
    ("idioma", "Idioma"),
]
METODO_LABEL = dict(METODO_KEYS)
METODO_RE = re.compile(r"acuerdo|m[eé]todo", re.I)
CAMBIOS_RE = re.compile(r"cambios", re.I)


def metodo_rows(text):
    lines = text.split("\n")
    tbl = first_table(lines, 0, len(lines))
    rows = {}
    if tbl:
        for idx, cells in tbl["rows"]:
            if cells and cells[0]:
                rows[fold(cells[0])] = (idx, cells)
    return lines, tbl, rows


def cmd_metodo(pos, opts):
    root = root_dir(opts)
    path = root / "METODO.md"
    if not path.is_file():
        if not root.is_dir():
            raise CoachError("No existe %s. Crea un tema primero con coach init." % rel(root))
        write_text(path, render_template("METODO.md", {"FECHA": today()}))
    text = read_text(path)
    changes = [(k, opts[k]) for k, _ in METODO_KEYS if k in opts]
    unknown = [k for k in opts if k not in METODO_LABEL and k not in ("root", "motivo", "no-build", "json")]
    if unknown:
        raise CoachError("Clave(s) de método desconocida(s): %s. Usa: %s." % (
            ", ".join(unknown), ", ".join(k for k, _ in METODO_KEYS)))
    if not changes:
        lines, tbl, rows = metodo_rows(text)
        if opts.get("json"):
            data = {k: (rows[fold(lbl)][1][1] if fold(lbl) in rows and len(rows[fold(lbl)][1]) > 1 else "")
                    for k, lbl in METODO_KEYS}
            out(json.dumps({"metodo": data, "pendiente": root_pending(root)}, ensure_ascii=False, indent=2))
            return
        out("\U0001F91D Acuerdo de método (%s)" % rel(path))
        for k, lbl in METODO_KEYS:
            row = rows.get(fold(lbl))
            val = row[1][1] if row and len(row[1]) > 1 else "—"
            out("  %-13s %s" % (k, val))
        if root_pending(root):
            out("\u26A0 Quedan puntos por acordar: pregúntalos (3 o 4 a la vez) y guárdalos con "
                "coach metodo --<clave> \"valor\".")
        return
    was_pending = root_pending(root)
    lines, tbl, rows = metodo_rows(text)
    if tbl is None:
        raise CoachError("%s no tiene la tabla de acuerdos. Regenera la plantilla o edítala a mano." % rel(path))
    added = []
    for key, value in changes:
        label = METODO_LABEL[key]
        row = rows.get(fold(label))
        if row:
            idx, cells = row
            cells = (cells + [""])[:max(2, len(cells))]
            cells[1] = cell(value)
            lines[idx] = fmt_row(cells)
        else:
            added.append(fmt_row([label, cell(value)]))
    if added:
        tbl2 = first_table(lines, 0, len(lines))
        lines = insert_lines(lines, tbl2["last"] + 1, added)
    text = "\n".join(lines)
    text = set_fm(text, "actualizado", today())
    resumen = "; ".join("%s: %s" % (METODO_LABEL[k], v) for k, v in changes)
    motivo = opts.get("motivo") or ("Primera sesión" if was_pending else "A petición del estudiante")
    cambio = "Acuerdo inicial: " + resumen if was_pending else resumen
    text = append_table_row(text, CAMBIOS_RE, "Cambios acordados", ["Fecha", "Cambio", "Motivo"],
                            [today(), cell(cambio), cell(motivo)])
    write_text(path, text)
    out("\U0001F91D Método actualizado: %s" % resumen)
    if root_pending(root):
        out("\u26A0 Aún quedan puntos por acordar en %s (coach metodo sin argumentos los muestra)." % rel(path))
    maybe_build(root, opts)


# --------------------------------------------------------------------------- comandos: lección y notas

def cmd_leccion(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach leccion <slug> <id>")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    lesson = find_lesson(topic, pos[1])
    if PENDING_RE.search(lesson["titulo"]):
        raise CoachError("La lección %s aún tiene el título de la plantilla. Termina el plan (sin marcadores "
                         "[[COMPLETAR]] en la ruta) antes de empezar a dar lecciones." % lesson["id"])
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
            "DESCRIPCION": strip_links(lesson["descripcion"]) or "[[COMPLETAR: resultado de aprendizaje]]",
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
    maybe_build(root, opts)


OBJETIVOS_RE = re.compile(r"^(?:objetivos|resumen)\s*$", re.I)
SECCIONES = {
    "objetivos": (OBJETIVOS_RE, "Objetivos"),
    "resumen": (re.compile(r"resumen con tus palabras", re.I), "Resumen con tus palabras"),
    "fuentes": (re.compile(r"^fuentes\b", re.I), "Fuentes"),
    "pregunta": (re.compile(r"^preguntas\b", re.I), "Preguntas"),
    "tarea": (re.compile(r"tarea", re.I), "Tarea práctica"),
    "resultado": (re.compile(r"^resultado\b", re.I), "Resultado"),
}
HISTORIAL_RE = re.compile(r"^historial\b", re.I)


def note_target(topic, ident):
    """Ruta y texto de la nota de una lección (1.2) o de un examen (M1)."""
    if re.match(r"^[mM][0-9]+$", ident):
        _, mod = find_module(topic, ident)
        exam = topic["exams"].get(mod["id"])
        if not exam:
            raise CoachError("El examen M%s aún no tiene nota. Créala con: coach examen %s %s"
                             % (mod["id"], topic["slug"], mod["id"]))
        return exam["path"], "examen M%s" % mod["id"]
    lesson = find_lesson(topic, ident)
    note = topic["notes"].get(lesson["id"])
    if not note:
        raise CoachError("La lección %s aún no tiene nota. Créala con: coach leccion %s %s"
                         % (lesson["id"], topic["slug"], lesson["id"]))
    return note["path"], "lección %s" % lesson["id"]


def lint_snippet(label, content):
    """Avisos inmediatos sobre el Markdown que se acaba de añadir (sin esperar a check)."""
    msgs = []

    def report(kind, where, msg):
        msgs.append(msg)

    lint_markdown(label, content, Path("."), report, check_links=False)
    for m in msgs:
        out("  \u26A0 %s" % m)


def cmd_nota(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach nota <slug> <id|Mn> [--desde ARCHIVO] [--seccion objetivos|resumen|fuentes] "
                         "[--historial \"texto\"]  (el Markdown llega por stdin o con --desde)")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    path, label = note_target(topic, pos[1])
    seccion = opts.get("seccion")
    historial = opts.get("historial")
    content = content_arg(opts)
    if not content and not historial:
        raise CoachError("Falta el contenido: pásalo por stdin (heredoc) o con --desde <archivo>.")
    text = read_text(path)
    did = []
    if content:
        if seccion:
            if seccion not in SECCIONES:
                raise CoachError("Sección desconocida: %s. Usa: %s." % (seccion, ", ".join(sorted(SECCIONES))))
            rx, title = SECCIONES[seccion]
            text = replace_section(text, rx, content, title)
            did.append("sección «%s» reemplazada" % title)
        else:
            text = insert_before_closing(text, content)
            heads = [HEADING_RE.match(l).group(2) for l in content.split("\n") if HEADING_RE.match(l)]
            did.append("bloque añadido" + (" (%s)" % heads[0] if heads else ""))
    if historial:
        text = append_table_row(text, HISTORIAL_RE, "Historial", ["Fecha", "Qué pasó"], [today(), cell(historial)])
        did.append("fila en Historial")
    write_text(path, text)
    blocks = len(re.findall("^## (?:\U0001F4D6|\U0001F6E0|\u2753)", text, re.M))
    out("\u270D %s: %s \u00b7 %s" % (label[:1].upper() + label[1:], ", ".join(did), plural(blocks, "bloque", "bloques")))
    if content:
        lint_snippet(rel(path), content)
    pending = len(PENDING_RE.findall(prose_only(text)))
    if pending:
        out("  \u2139 Quedan %d marcador(es) [[COMPLETAR]] en la nota." % pending)
    maybe_build(root, opts)


def _set_line(text, line_no, fn):
    lines = text.split("\n")
    lines[line_no] = fn(lines[line_no])
    return "\n".join(lines)


REQUIRED_NOTE_SECTIONS = [
    ("Resumen con tus palabras", re.compile(r"^#{2,3}\s+.*resumen con tus palabras", re.I | re.M)),
    ("Fuentes", re.compile(r"^#{2,3}\s+.*fuentes", re.I | re.M)),
]


def note_gaps(text):
    """Lo que le falta a una nota para darla por completada."""
    _, body = parse_frontmatter(text)
    missing = [t for t, rx in REQUIRED_NOTE_SECTIONS if not rx.search(body)]
    pending = len(PENDING_RE.findall(prose_only(body)))
    problems = []
    if missing:
        problems.append("faltan las secciones %s" % ", ".join("«%s»" % m for m in missing))
    if pending:
        problems.append("quedan %d marcador(es) [[COMPLETAR]]" % pending)
    return problems


def cmd_completar(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach completar <slug> <id> [--convalidada] [--forzar]")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    lesson = find_lesson(topic, pos[1])
    conv = bool(opts.get("convalidada"))
    note = topic["notes"].get(lesson["id"])
    if not conv and not opts.get("forzar"):
        if note is None:
            raise CoachError("La lección %s no tiene nota. Escríbela durante la lección (coach leccion / coach nota); "
                             "si el estudiante ya lo demostró, usa --convalidada." % lesson["id"])
        problems = note_gaps(note["text"])
        if problems:
            raise CoachError("La nota de la lección %s no está lista: %s. Complétala (coach nota … --seccion resumen "
                             "| fuentes) o, si de verdad está hecha, usa --forzar." % (lesson["id"], "; ".join(problems)))
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
    first_review = None
    if note:
        ntext = set_fm(note["text"], "estado", "convalidada" if conv else "completada")
        ntext = set_fm(ntext, "fin", today())
        if not conv and not was_done:
            first_review = in_days(LESSON_INTERVALS[0])
            ntext = set_fm(ntext, "repaso", first_review)
            ntext = set_fm_raw(ntext, "repasos", "0")
        write_text(note["path"], ntext)
    done = sum(1 for l in lessons if l["hecha"])
    total = len(lessons)
    pct = done * 100 // total if total else 0
    if was_done:
        out("\u2139 La lección %s ya estaba completada." % lesson["id"])
    label = "convalidada" if conv else "completada"
    out("\u2714 Lección %s %s \u00b7 %s %d/%d (%d%%)" % (lesson["id"], label, topic["slug"], done, total, pct))
    if first_review:
        out("\U0001F5D3 Primer repaso: %s" % first_review)
    mod_after = all(l["hecha"] for l in lessons if l["modulo"] == mod_index)
    mod = topic["plan"]["modulos"][mod_index]
    if mod_after and not mod_before:
        out("\U0001F389 Módulo %s completado: %s" % (mod["id"], mod["titulo"]))
        if mod["examen"] is not None and not mod["examen"]["hecho"]:
            out("\U0001F4DD Toca el examen del módulo: coach examen %s %s" % (topic["slug"], mod["id"]))
    if nxt:
        out("\u25B6 Siguiente: %s %s" % (nxt["id"], nxt["titulo"]))
    else:
        out("\U0001F3C1 Lecciones terminadas. Quedan el proyecto final y un repaso general.")
    maybe_build(root, opts)


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
        ntext = set_fm(note["text"], "estado", "en-curso")
        if fm_str(note["fm"], "repaso"):
            ntext = set_fm(ntext, "repaso", "")
        write_text(note["path"], ntext)
    out("\u21BA Lección %s reabierta y marcada como actual." % lesson["id"])
    maybe_build(root, opts)


# --------------------------------------------------------------------------- comandos: glosario y dudas

GLOSARIO_HEADER = ["Término", "Definición", "Lección"]


def lesson_ref(topic, lid, from_dir):
    """Enlace relativo a la nota de una lección, o su id si no tiene nota."""
    if not lid:
        return "—"
    note = topic["notes"].get(lid)
    if not note:
        return lid
    target = os.path.relpath(str(note["path"]), str(from_dir)).replace(os.sep, "/")
    return "[%s](%s)" % (lid, target)


def term_key(cell_text):
    return fold(re.sub(r"[*_`]", "", cell_text)).strip()


def cmd_glosario(pos, opts):
    if len(pos) < 3 or len(pos[1:]) % 2:
        raise CoachError("Uso: coach glosario <slug> \"Término\" \"Definición\" [\"Término\" \"Definición\" ...] "
                         "[--leccion ID]")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    path = topic["dir"] / "GLOSARIO.md"
    if not path.is_file():
        fm = topic["plan"]["fm"] or {}
        tema = fm_str(fm, "tema") or topic["slug"]
        write_text(path, render_template("GLOSARIO.md", {"TEMA_YAML": yaml_quote(tema), "TEMA": tema,
                                                         "SLUG": topic["slug"]}))
    lid = opts.get("leccion") or fm_str(topic["plan"]["fm"], "leccion_actual")
    if lid:
        find_lesson(topic, lid)
    ref = lesson_ref(topic, lid, topic["dir"])
    text = read_text(path)
    lines = text.split("\n")
    tbl = first_table(lines, 0, len(lines))
    if tbl is None:
        lines += ["", fmt_row(GLOSARIO_HEADER), fmt_row(["---"] * 3)]
        tbl = first_table(lines, 0, len(lines))
    added, updated = [], []
    pairs = list(zip(pos[1::2], pos[2::2]))
    for term, definition in pairs:
        term = term.strip().strip("*").strip()
        if not term or not definition.strip():
            raise CoachError("Cada término necesita una definición.")
        row = fmt_row(["**%s**" % cell(term), cell(definition), ref])
        key = term_key(term)
        tbl = first_table(lines, 0, len(lines))
        hit = next((idx for idx, cells in tbl["rows"] if cells and term_key(cells[0]) == key), None)
        if hit is not None:
            lines[hit] = row
            updated.append(term)
            continue
        at = tbl["last"] + 1
        for idx, cells in tbl["rows"]:
            if cells and term_key(cells[0]) > key:
                at = idx
                break
        lines = insert_lines(lines, at, [row])
        added.append(term)
    write_text(path, "\n".join(lines))
    parts = []
    if added:
        parts.append("añadido(s): " + ", ".join(added))
    if updated:
        parts.append("actualizado(s): " + ", ".join(updated))
    out("\U0001F4D6 Glosario de %s: %s" % (topic["slug"], "; ".join(parts)))
    maybe_build(root, opts)


DUDAS_EMPTY_RE = re.compile(r"^_A[uú]n no hay dudas registradas.*_\s*$", re.I)


def cmd_duda(pos, opts):
    if len(pos) < 2 or not opts.get("respuesta"):
        raise CoachError("Uso: coach duda <slug> \"Pregunta\" --respuesta \"respuesta corta\" [--contexto ...] "
                         "[--explicacion ...] [--leccion ID] [--fuente \"[Título](https://...)\"]")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    path = topic["dir"] / "DUDAS.md"
    if not path.is_file():
        fm = topic["plan"]["fm"] or {}
        tema = fm_str(fm, "tema") or topic["slug"]
        write_text(path, render_template("DUDAS.md", {"TEMA_YAML": yaml_quote(tema), "TEMA": tema,
                                                      "SLUG": topic["slug"]}))
    lid = opts.get("leccion") or ""
    if lid:
        find_lesson(topic, lid)
    entry = ["## %s \u00b7 %s" % (today(), pos[1].strip()), ""]
    if opts.get("contexto"):
        entry.append("- **Contexto:** %s" % opts["contexto"].strip())
    entry.append("- **Respuesta corta:** %s" % opts["respuesta"].strip())
    explicacion = opts.get("explicacion") or (read_text(opts["desde"]).strip() if opts.get("desde") else "")
    if explicacion:
        exp_lines = explicacion.strip().split("\n")
        entry.append("- **Explicación:** %s" % exp_lines[0])
        entry.extend(("  " + l) if l.strip() else "" for l in exp_lines[1:])
    if lid:
        entry.append("- **Relacionado:** lección %s" % lesson_ref(topic, lid, topic["dir"]))
    if opts.get("fuente"):
        entry.append("- **Fuente:** %s" % opts["fuente"].strip())
    text = read_text(path)
    lines = [l for l in text.split("\n") if not DUDAS_EMPTY_RE.match(l.strip())]
    # Debajo del comentario de la plantilla si existe; si no, debajo del título.
    at = None
    in_comment = False
    for i, l in enumerate(lines):
        if in_comment:
            if "-->" in l:
                at = i + 1
                break
            continue
        if "<!--" in l:
            if "-->" in l:
                at = i + 1
                break
            in_comment = True
            continue
        if l.startswith("## "):
            break
    if at is None:
        at = next((i + 1 for i, l in enumerate(lines) if l.startswith("# ")), len(lines))
    new_lines = lines[:at] + [""] + entry + lines[at:]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(new_lines)).rstrip("\n") + "\n"
    write_text(path, text)
    out("\u2753 Duda registrada en %s: %s" % (rel(path), pos[1].strip()))
    maybe_build(root, opts)


# --------------------------------------------------------------------------- comandos: huecos y repasos

def update_gap(topic, gid, opts, quiet=False):
    text = topic["text"]
    lines, tbl, rows = gap_rows(text)
    gap = next((g for g in rows if g["id"].lower() == gid.lower()), None)
    if gap is None:
        ids = ", ".join(g["id"] for g in rows) or "ninguno"
        raise CoachError("No existe el hueco %s en %s (huecos: %s)." % (gid, rel(topic["plan_path"]), ids))
    actions = [a for a in ("bien", "mal", "cerrar") if opts.get(a)]
    if len(actions) != 1:
        raise CoachError("Indica uno: --bien, --mal o --cerrar.")
    action = actions[0]
    cells = list(gap["celdas"])
    try:
        intentos = int(re.sub(r"[^0-9]", "", cells[2]) or "0")
    except ValueError:
        intentos = 0
    if action == "cerrar":
        cells[3] = "—"
        cells[4] = "cerrado %s" % today()
        msg = "\U0001F389 Hueco %s cerrado: %s" % (gap["id"], gap["hueco"])
    elif action == "bien":
        racha = gap["racha"] + 1
        nxt = in_days(GAP_INTERVALS[min(racha, len(GAP_INTERVALS) - 1)])
        cells[3] = nxt
        cells[4] = "abierto " + "\u2714" * racha
        msg = "\u2714 Hueco %s bien repasado (%s) \u00b7 próximo repaso: %s" % (gap["id"], plural(racha, "seguido", "seguidos"), nxt)
        if racha >= GAP_CLOSE_STREAK:
            msg += "\n\u2139 Lleva %d repasos bien seguidos: si lo resolvió sin ayuda, ciérralo con --cerrar." % racha
    else:
        nxt = in_days(GAP_INTERVALS[0])
        cells[2] = str(intentos + 1)
        cells[3] = nxt
        cells[4] = "abierto"
        msg = "\u21BA Hueco %s fallado: vuelve al primer intervalo \u00b7 próximo repaso: %s" % (gap["id"], nxt)
    lines[gap["linea"]] = fmt_row(cells)
    text = set_fm("\n".join(lines), "actualizado", today())
    write_text(topic["plan_path"], text)
    if not quiet:
        out(msg)
    return msg


def cmd_hueco(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach hueco <slug> \"Descripción\" [--leccion ID]  ·  coach hueco <slug> Hn --bien|--mal|--cerrar")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    if re.match(r"^[hH][0-9]+$", pos[1].strip()):
        update_gap(topic, pos[1].strip(), opts)
        maybe_build(root, opts)
        return
    desc = pos[1].strip()
    lid = opts.get("leccion") or fm_str(topic["plan"]["fm"], "leccion_actual")
    if opts.get("leccion"):
        find_lesson(topic, lid)
    detectado = "%s (%s)" % (lid, today()) if lid else "Repaso (%s)" % today()
    nxt = in_days(GAP_INTERVALS[0])
    row = [cell(desc), detectado, "1", nxt, "abierto"]
    text = topic["text"]
    lines = text.split("\n")
    if find_section(lines, HUECOS_RE) is None:
        sec = find_section(lines, BITACORA_RE)
        block = ["## Huecos abiertos", "", fmt_row(GAP_HEADER), fmt_row(["---"] * 5), fmt_row(row), ""]
        lines = insert_lines(lines, sec[0], block) if sec else lines + [""] + block
        text = "\n".join(lines)
    else:
        text = append_table_row(text, HUECOS_RE, "Huecos abiertos", GAP_HEADER, row)
    text = set_fm(text, "actualizado", today())
    write_text(topic["plan_path"], text)
    gid = gap_rows(text)[2][-1]["id"]
    out("\U0001F573 Hueco %s abierto: %s \u00b7 próximo repaso: %s" % (gid, desc, nxt))
    maybe_build(root, opts)


Q_RE = re.compile(r"^\*\*(P[0-9]+)\.?\*\*\s*(.+)$")


def note_questions(text, limit=3):
    """Preguntas de recuperación (**Pn.**) de una nota, con el inicio de su respuesta modelo."""
    _, body = parse_frontmatter(text)
    lines = body.split("\n")
    qs = []
    for i, line in enumerate(lines):
        m = Q_RE.match(line.strip())
        if not m:
            continue
        q = re.split(r"\s+\u2014\s+tu respuesta", m.group(2), flags=re.I)[0].strip()
        answer = []
        for j in range(i + 1, min(i + 40, len(lines))):
            s = lines[j].strip()
            if Q_RE.match(s) or s.startswith("#"):
                break
            if s.startswith("</details>"):
                break
            if s and not s.startswith("<details") and not s.startswith("<summary"):
                if any(x.startswith("<details") for x in lines[i + 1:j + 1]):
                    answer.append(s)
        ans = re.sub(r"\s+", " ", " ".join(answer)).strip()
        qs.append({"id": m.group(1), "pregunta": q, "respuesta": ans[:240] + ("…" if len(ans) > 240 else "")})
    return qs[:limit] if limit else qs


def cmd_repaso(pos, opts):
    if not pos:
        raise CoachError("Uso: coach repaso <slug> [--json]  ·  coach repaso <slug> <id|Hn> --bien|--mal")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    if len(pos) >= 2:
        ident = pos[1].strip()
        if re.match(r"^[hH][0-9]+$", ident):
            update_gap(topic, ident, opts)
        else:
            review_lesson(topic, ident, opts)
        maybe_build(root, opts)
        return
    due, nxt = review_state(topic)
    gaps = sorted([d for d in due if d["tipo"] == "hueco"], key=lambda d: d["fecha"])
    lessons = sorted([d for d in due if d["tipo"] == "leccion"], key=lambda d: d["fecha"])
    chosen = (gaps + lessons)[:REVIEW_LIMIT]
    # Intercalado: el orden se mezcla entre módulos con una semilla estable para el día y el tema.
    random.Random("%s:%s" % (today(), topic["slug"])).shuffle(chosen)
    items = []
    gap_by_id = {g["id"]: g for g in gap_rows(topic["text"])[2]}
    for d in chosen:
        item = dict(d)
        if d["tipo"] == "leccion":
            note = topic["notes"][d["id"]]
            item["nota"] = rel(note["path"])
            item["preguntas"] = note_questions(note["text"])
            item["modulo"] = d["id"].split(".")[0]
        else:
            g = gap_by_id[d["id"]]
            item["detectado"] = g["detectado"]
            item["intentos"] = g["intentos"]
        items.append(item)
    if opts.get("json"):
        out(json.dumps({"tema": topic["slug"], "hoy": today(), "elementos": items, "pendientes": len(due),
                        "proximo": nxt}, ensure_ascii=False, indent=2))
        return
    if not items:
        out("\u2714 Nada vence hoy en %s." % topic["slug"])
        if nxt:
            out("   Próximo repaso: %s (%s)" % (nxt["fecha"], nxt["id"]))
        return
    extra = (" (de %d vencidos; el resto, otro día)" % len(due)) if len(due) > len(items) else ""
    out("\U0001F501 Repaso de hoy \u00b7 %s \u00b7 %s%s, mezclados" % (topic["slug"], plural(len(items), "elemento", "elementos"), extra))
    for it in items:
        if it["tipo"] == "hueco":
            out("  \u2022 %s hueco: %s (detectado en %s, %s intento(s), vencía %s)"
                % (it["id"], it["titulo"], it["detectado"], it["intentos"], it["fecha"]))
        else:
            out("  \u2022 %s lección: %s (vencía %s) \u00b7 %s" % (it["id"], it["titulo"], it["fecha"], it["nota"]))
            for q in it["preguntas"]:
                out("      %s. %s" % (q["id"], q["pregunta"][:160]))
    out("Pregunta uno a uno con preguntas nuevas sobre esas ideas (no repitas las de la nota tal cual) y registra cada "
        "resultado: coach repaso %s <id|Hn> --bien|--mal" % topic["slug"])


def review_lesson(topic, lid, opts):
    lesson = find_lesson(topic, lid)
    note = topic["notes"].get(lesson["id"])
    if note is None:
        raise CoachError("La lección %s no tiene nota: no hay repaso que programar." % lesson["id"])
    actions = [a for a in ("bien", "mal") if opts.get(a)]
    if len(actions) != 1:
        raise CoachError("Indica uno: --bien o --mal.")
    text = note["text"]
    n = fm_int(note["fm"], "repasos")
    if actions[0] == "bien":
        n += 1
        if n >= len(LESSON_INTERVALS):
            text = set_fm(text, "repaso", "")
            msg = "\U0001F3C5 Lección %s consolidada: %d repasos bien, ya no se programan más." % (lesson["id"], n)
        else:
            nxt = in_days(LESSON_INTERVALS[n])
            text = set_fm(text, "repaso", nxt)
            msg = "\u2714 Lección %s repasada (%d) \u00b7 próximo repaso: %s" % (lesson["id"], n, nxt)
        hist = "Repaso espaciado: bien (%d)" % n
    else:
        n = 0
        nxt = in_days(1)
        text = set_fm(text, "repaso", nxt)
        msg = ("\u21BA Lección %s: repaso fallado, vuelve mañana (%s). Si falló un concepto concreto, ábrelo como hueco: "
               "coach hueco %s \"…\" --leccion %s" % (lesson["id"], nxt, topic["slug"], lesson["id"]))
        hist = "Repaso espaciado: a reforzar"
    text = set_fm_raw(text, "repasos", str(n))
    text = append_table_row(text, HISTORIAL_RE, "Historial", ["Fecha", "Qué pasó"], [today(), hist])
    write_text(note["path"], text)
    out(msg)


# --------------------------------------------------------------------------- comandos: exámenes

def exam_line(mid):
    return "- [ ] **Examen M%s** — 6 a 10 preguntas y una tarea \u00b7 aprueba con %d %%" % (mid, EXAM_PASS)


def module_insert_at(topic, mod_index):
    """Línea tras la última lección del módulo (y su sublista de detalles)."""
    lines = topic["text"].split("\n")
    ids = set(topic["plan"]["modulos"][mod_index]["lecciones"])
    last = max(l["linea"] for l in topic["plan"]["lecciones"] if l["id"] in ids)
    at = last + 1
    while at < len(lines) and lines[at].strip() and re.match(r"^(\s{2,}|\t)", lines[at]):
        at += 1
    return lines, at


def cmd_examen(pos, opts):
    if len(pos) < 2:
        raise CoachError("Uso: coach examen <slug> <módulo>  ·  coach examen <slug> <módulo> --resultado 5/6 [--tarea si|no]")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    mi, mod = find_module(topic, pos[1])
    text = topic["text"]
    if mod["examen"] is None:
        lines, at = module_insert_at(topic, mi)
        text = "\n".join(insert_lines(lines, at, [exam_line(mod["id"])]))
        write_text(topic["plan_path"], text)
        out("\u2795 Añadida la línea del examen M%s al plan." % mod["id"])
        topic = load_topic(root, topic["slug"])
        mi, mod = find_module(topic, mod["id"])
        text = topic["text"]
    lessons = [l for l in topic["plan"]["lecciones"] if l["modulo"] == mi]
    note = topic["exams"].get(mod["id"])
    if not opts.get("resultado"):
        if note is None:
            path = topic["dir"] / "examenes" / ("m%s-%s.md" % (mod["id"], slugify(mod["titulo"]) or "examen"))
            cubre = "\n".join("- %s %s" % (l["id"], l["titulo"]) for l in lessons)
            fm = topic["plan"]["fm"] or {}
            write_text(path, render_template("EXAMEN.md", {
                "MODULO": mod["id"],
                "MODULO_YAML": yaml_quote("M%s \u00b7 %s" % (mod["id"], mod["titulo"])),
                "TITULO": mod["titulo"],
                "SLUG": topic["slug"],
                "TEMA": fm_str(fm, "tema") or topic["slug"],
                "CUBRE": cubre or "- (sin lecciones)",
                "UMBRAL": str(EXAM_PASS),
                "FECHA": today(),
            }))
            out("\U0001F4DD Nota del examen creada: %s" % rel(path))
        else:
            out("\U0001F4DD Nota del examen: %s" % rel(note["path"]))
        pend = [l["id"] for l in lessons if not l["hecha"]]
        out("Examen M%s \u00b7 %s \u00b7 cubre %s" % (mod["id"], mod["titulo"], ", ".join(l["id"] for l in lessons)))
        out("  6 a 10 preguntas de nivel variado (encontrar el error, elegir entre alternativas, explicar, aplicar a un "
            "caso nuevo) y una tarea práctica corta. Aprueba con %d %% y la tarea hecha." % EXAM_PASS)
        out("  Escribe las preguntas en la nota con: coach nota %s M%s (una por mensaje en el chat)."
            % (topic["slug"], mod["id"]))
        if pend:
            out("  \u26A0 Lecciones del módulo sin completar: %s." % ", ".join(pend))
        maybe_build(root, opts)
        return
    m = re.match(r"^\s*([0-9]+)\s*/\s*([0-9]+)\s*$", opts["resultado"])
    if not m or int(m.group(2)) == 0 or int(m.group(1)) > int(m.group(2)):
        raise CoachError("--resultado debe tener la forma aciertos/total, por ejemplo 5/6.")
    ok, total = int(m.group(1)), int(m.group(2))
    pct = ok * 100 // total
    tarea = fold(opts.get("tarea") or "").strip()
    if tarea and tarea not in ("si", "no"):
        raise CoachError("--tarea admite si o no.")
    passed = pct >= EXAM_PASS and tarea != "no"
    lines = text.split("\n")
    ln = mod["examen"]["linea"]
    em = EXAM_RE.match(lines[ln])
    tarea_txt = " \u00b7 tarea %s" % ("hecha" if tarea == "si" else "pendiente") if tarea else ""
    if passed:
        lines[ln] = "%s[x]%s — %d/%d (%d %%)%s \u00b7 aprobado el %s" % (em.group(1), em.group(3), ok, total, pct, tarea_txt, today())
    else:
        lines[ln] = "%s[ ]%s — %d/%d (%d %%)%s el %s \u00b7 repetir" % (em.group(1), em.group(3), ok, total, pct, tarea_txt, today())
    text = set_fm("\n".join(lines), "actualizado", today())
    write_text(topic["plan_path"], text)
    if note:
        ntext = set_fm(note["text"], "estado", "aprobado" if passed else "repetir")
        ntext = set_fm(ntext, "resultado", "%d/%d" % (ok, total))
        ntext = set_fm(ntext, "fecha", today())
        write_text(note["path"], ntext)
    if passed:
        out("\U0001F389 Examen M%s aprobado: %d/%d (%d %%)." % (mod["id"], ok, total, pct))
    else:
        out("\u21BA Examen M%s: %d/%d (%d %%)%s. No llega al %d %%: abre un hueco por cada concepto fallado "
            "(coach hueco %s \"…\") y repítelo cuando los repases." % (mod["id"], ok, total, pct,
                                                                     " y tarea pendiente" if tarea == "no" else "",
                                                                     EXAM_PASS, topic["slug"]))
    maybe_build(root, opts)


# --------------------------------------------------------------------------- siguiente, sesión y estado

def cmd_prefix(opts):
    parts = ["python3", str(SCRIPT)]
    return " ".join(parts)


def root_flag(opts):
    r = opts.get("root") or os.environ.get("COACH_ROOT")
    return (" --root %s" % shell_quote(str(Path(r).resolve()))) if r else ""


def shell_quote(s):
    return s if re.match(r"^[\w@%+=:,./-]+$", s) else "'" + s.replace("'", "'\\''") + "'"


def note_block_count(note):
    return len(re.findall("^## (?:\U0001F4D6|\U0001F6E0|\u2753)", note["text"], re.M)) if note else 0


def next_step(root, topic, opts):
    """Lo que toca ahora, con sus comandos. Única fuente del siguiente paso."""
    base = cmd_prefix(opts)
    rf = root_flag(opts)

    def c(*parts):
        return "%s %s%s" % (base, " ".join(parts), rf)

    if topic is None:
        return {"tipo": "nuevo", "texto": "Crear un plan: acuerda el método, haz el diagnóstico y crea el tema.",
                "comandos": [c("init", "<slug>", "--tema", "\"Título\"", "--area", "<área>")],
                "lee": ["references/plan-de-estudio.md"], "meta": []}
    s = summarize(topic)
    slug = topic["slug"]
    meta = []
    due = s["repasos"]["vencidos"]
    if due:
        ids = ", ".join(d["id"] for d in due[:REVIEW_LIMIT])
        meta.append("Repaso (5–10 min): %s vencido(s) — %s" % (len(due), ids))
    if root_pending(root):
        return {"tipo": "metodo", "texto": "Acordar el método: 3 o 4 preguntas con opciones y guardarlo.",
                "comandos": [c("metodo"), c("metodo", "--practica", "\"…\"", "--ritmo", "\"…\"", "--profundidad",
                                            "\"…\"", "--calentamiento", "\"…\"")],
                "lee": [], "meta": meta}
    if s["pendiente"]["plan"]:
        return {"tipo": "plan", "texto": "Terminar el plan: diagnóstico, ruta por módulos con examen, proyecto final y "
                                        "recursos, sin marcadores [[COMPLETAR]].",
                "comandos": [c("check", slug)], "lee": ["references/plan-de-estudio.md"], "meta": meta}
    if due:
        main = {"tipo": "repaso", "texto": "Repasar lo que vence hoy (calentamiento) y después seguir.",
                "comandos": [c("repaso", slug)], "lee": [], "meta": meta}
    else:
        main = None
    for mi, mod in enumerate(topic["plan"]["modulos"]):
        ls = [l for l in topic["plan"]["lecciones"] if l["modulo"] == mi]
        if ls and all(l["hecha"] for l in ls) and mod["examen"] is not None and not mod["examen"]["hecho"]:
            step = {"tipo": "examen", "texto": "Examen del módulo %s · %s." % (mod["id"], mod["titulo"]),
                    "comandos": [c("examen", slug, mod["id"])], "lee": ["references/pedagogia.md (§ Exámenes)"],
                    "meta": meta + ["Examen M%s (20–30 min)" % mod["id"]]}
            return main and dict(main, meta=step["meta"]) or step
    cur = current_lesson(topic)
    if cur is None:
        step = {"tipo": "final", "texto": "Proyecto final y repaso general: todas las lecciones están hechas.",
                "comandos": [c("estado", slug)], "lee": ["references/plan-de-estudio.md (§ Proyecto final)"],
                "meta": meta + ["Proyecto final"]}
        return main and dict(main, meta=step["meta"]) or step
    note = topic["notes"].get(cur["id"])
    if note and norm_state(fm_str(note["fm"], "estado")) == "en-curso" and note_block_count(note):
        texto = "Seguir la lección %s · %s (lleva %s escritos)." % (cur["id"], cur["titulo"],
                                                                   plural(note_block_count(note), "bloque", "bloques"))
        cmds = [c("nota", slug, cur["id"], "<<'EOF'"), c("completar", slug, cur["id"])]
    else:
        texto = "Empezar la lección %s · %s." % (cur["id"], cur["titulo"])
        cmds = [c("leccion", slug, cur["id"]), c("nota", slug, cur["id"], "<<'EOF'")]
    step = {"tipo": "leccion", "texto": texto, "comandos": cmds, "lee": ["references/pedagogia.md"],
            "meta": meta + ["Lección %s · %s (20–45 min)" % (cur["id"], cur["titulo"])],
            "leccion": cur["id"]}
    return main and dict(main, meta=step["meta"]) or step


def cmd_siguiente(pos, opts):
    root = root_dir(opts)
    topic = pick_topic(root, pos[0] if pos else None) if root.is_dir() else None
    step = next_step(root, topic, opts)
    tema = fm_str(topic["plan"]["fm"], "tema") if topic else ""
    if opts.get("json"):
        out(json.dumps(dict(step, tema=tema, slug=topic["slug"] if topic else "", raiz=rel(root)),
                       ensure_ascii=False, indent=2))
        return
    if step["meta"]:
        out("\U0001F3AF Meta de hoy \u00b7 %s" % (tema or "nuevo tema"))
        for i, m in enumerate(step["meta"], 1):
            out("  %d. %s" % (i, m))
        out("")
    out("\u25B6 Ahora: %s" % step["texto"])
    for cmd in step["comandos"]:
        out("  $ %s" % cmd)
    if step["lee"]:
        out("  Lee (si aún no lo hiciste en esta sesión): %s" % ", ".join(step["lee"]))
    if topic:
        out("")
        out("\u21A9 Para retomar en otro chat: «Sigamos con mi plan de %s»" % (tema or topic["slug"]))
        out("\U0001F4D3 Cuaderno: %s" % (root / "cuaderno.html").resolve())


def run_check(root, only, report):
    counts = {"error": 0, "aviso": 0}

    def rep(kind, where, msg):
        counts[kind] += 1
        report(kind, where, msg)

    if not root.is_dir():
        rep("error", rel(root), "no existe; crea un tema con coach init")
        return counts
    slugs = list_topics(root)
    if only and only not in slugs:
        rep("error", only, "no existe %s" % rel(root / only / "PLAN.md"))
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.is_dir() and not p.name.startswith(".") and p.name not in slugs and (not only or p.name == only):
            if any(f.endswith(".md") for f in os.listdir(str(p))):
                rep("aviso", p.name + "/", "carpeta con notas pero sin PLAN.md")
    newest = 0.0
    for slug in slugs:
        if only and slug != only:
            continue
        check_topic(load_topic(root, slug), rep)
    for relp in collect_files(root):
        if only and not relp.startswith(only + "/"):
            continue
        full = root / relp
        newest = max(newest, full.stat().st_mtime)
        lint_markdown(relp, read_text(full), root, rep)
    nb = root / "cuaderno.html"
    if not nb.is_file():
        rep("aviso", "cuaderno.html", "no existe; ejecuta coach build")
    elif nb.stat().st_mtime + 1 < newest:
        rep("aviso", "cuaderno.html", "desactualizado; ejecuta coach build")
    return counts


def check_topic(topic, rep):
    slug = topic["slug"]
    plan = topic["plan"]
    where = slug + "/PLAN.md"
    fm = plan["fm"]
    if fm is None:
        rep("error", where, "falta el frontmatter (bloque --- al inicio)")
        fm = {}
    else:
        if not fm_str(fm, "tema"):
            rep("error", where, "falta el campo 'tema' en el frontmatter")
        if fm_str(fm, "slug") and fm_str(fm, "slug") != slug:
            rep("aviso", where, "el slug '%s' no coincide con la carpeta '%s'" % (fm_str(fm, "slug"), slug))
    lessons = plan["lecciones"]
    if not lessons:
        rep("error", where, "no hay lecciones con el formato `- [ ] **1.1 Título** — descripción`")
    seen = set()
    for l in lessons:
        if l["id"] in seen:
            rep("error", where, "id de lección duplicado: %s" % l["id"])
        seen.add(l["id"])
    for a, b in zip(lessons, lessons[1:]):
        if id_key(b["id"]) <= id_key(a["id"]):
            rep("aviso", where, "orden de ids inesperado: %s después de %s" % (b["id"], a["id"]))
    cur = fm_str(fm, "leccion_actual")
    if cur and cur not in seen:
        rep("aviso", where, "leccion_actual '%s' no existe en el plan" % cur)
    if plan["modulos"] and not any(m["nivel"] for m in plan["modulos"]):
        rep("aviso", where, "ningún módulo indica nivel (Básico/Intermedio/Avanzado/Experto)")
    if fm_int(fm, "formato", 1) >= 2:
        sin_examen = [m["id"] for m in plan["modulos"] if m["examen"] is None and not m["proyecto"]]
        if sin_examen:
            rep("aviso", where, "módulo(s) sin línea de examen: %s (coach examen %s <n> la añade)"
                % (", ".join(sin_examen), slug))
    if not re.search(r"^#{2,3}\s+.*huecos", topic["text"], re.I | re.M):
        rep("aviso", where, "falta la sección «Huecos abiertos» (aunque esté vacía)")
    for g in gap_rows(topic["text"])[2]:
        if g["abierto"] and not g["vence"] and g["proximo_repaso"].strip() not in ("", "—", "-"):
            rep("aviso", where, "hueco %s con «Próximo repaso» sin fecha (AAAA-MM-DD): usa coach hueco %s %s --bien|--mal"
                % (g["id"], slug, g["id"]))
    for name in ("GLOSARIO.md", "DUDAS.md"):
        if not (topic["dir"] / name).is_file():
            rep("aviso", slug + "/" + name, "no existe")
    ldir = topic["dir"] / "lecciones"
    if ldir.is_dir():
        for f in sorted(ldir.iterdir(), key=lambda x: x.name):
            if not f.name.endswith(".md"):
                continue
            w = "%s/lecciones/%s" % (slug, f.name)
            m = NOTE_ID_RE.match(f.name)
            if not m:
                rep("aviso", w, "el nombre debe empezar con el id de la lección (p. ej. 1.2-titulo.md)")
                continue
            if m.group(1) not in seen:
                rep("aviso", w, "la lección %s no existe en el plan" % m.group(1))
            ntext = read_text(f)
            nfm, nbody = parse_frontmatter(ntext)
            if nfm is None:
                rep("aviso", w, "falta el frontmatter")
                continue
            state = norm_state(fm_str(nfm, "estado"))
            if state not in NOTE_STATES:
                rep("aviso", w, "estado '%s' no válido (usa en-curso, completada o convalidada)" % fm_str(nfm, "estado"))
            if state == "completada":
                missing = [t for t, rx in REQUIRED_NOTE_SECTIONS if not rx.search(nbody)]
                if missing:
                    rep("aviso", w, "la nota está completada pero le faltan secciones: %s" % ", ".join(missing))
            if fm_str(nfm, "repaso") and not parse_date(fm_str(nfm, "repaso")):
                rep("aviso", w, "'repaso' debe ser una fecha AAAA-MM-DD")
            check_challenges(w, nbody, state, rep)
    edir = topic["dir"] / "examenes"
    if edir.is_dir():
        ids = {m["id"] for m in plan["modulos"]}
        for f in sorted(edir.iterdir(), key=lambda x: x.name):
            if not f.name.endswith(".md"):
                continue
            w = "%s/examenes/%s" % (slug, f.name)
            m = EXAM_FILE_RE.match(f.name)
            if not m:
                rep("aviso", w, "el nombre debe empezar por m<módulo>- (p. ej. m1-fundamentos.md)")
                continue
            if m.group(1) not in ids:
                rep("aviso", w, "el módulo %s no existe en el plan" % m.group(1))
            efm, _ = parse_frontmatter(read_text(f))
            if efm is not None and norm_state(fm_str(efm, "estado")) not in EXAM_STATES:
                rep("aviso", w, "estado '%s' no válido (usa pendiente, aprobado o repetir)" % fm_str(efm, "estado"))


RETO_RE = re.compile(r"^###\s+(?:\U0001F9E9\s*)?reto\b", re.I)


def check_challenges(where, body, state, rep):
    """Cada reto tiene resultado esperado; con la nota completada, también el intento del estudiante."""
    lines = body.split("\n")
    in_fence = False
    starts = []
    for i, l in enumerate(lines):
        if FENCE_RE.match(l):
            in_fence = not in_fence
            continue
        if not in_fence and (RETO_RE.match(l) or re.match(r"^#{1,2}\s", l)):
            starts.append((i, bool(RETO_RE.match(l))))
    starts.append((len(lines), False))
    for (a, is_reto), (b, _) in zip(starts, starts[1:]):
        if not is_reto:
            continue
        chunk = "\n".join(lines[a:b])
        title = lines[a].lstrip("#").strip()
        if not re.search(r"resultado esperado", chunk, re.I):
            rep("aviso", where, "«%s» no tiene **Resultado esperado**" % title[:50])
        if state == "completada" and not re.search(r"tu intento|veredicto", chunk, re.I):
            rep("aviso", where, "«%s» no registra el intento ni el veredicto del estudiante" % title[:50])


def cmd_sesion(pos, opts):
    if not pos or not opts.get("logros"):
        raise CoachError("Uso: coach sesion <slug> --logros \"…\" [--lecciones \"1.2, 1.3\"] [--siguiente \"…\"]")
    root = root_dir(opts)
    topic = load_topic(root, pos[0])
    lecciones = opts.get("lecciones") or "—"
    step = next_step(root, topic, opts)
    siguiente = opts.get("siguiente") or step["texto"]
    text = append_table_row(topic["text"], BITACORA_RE, "Bitácora", ["Fecha", "Lecciones", "Logros", "Próximo paso"],
                            [today(), cell(lecciones), cell(opts["logros"]), cell(siguiente)])
    text = set_fm(text, "actualizado", today())
    write_text(topic["plan_path"], text)
    out("\U0001F4D2 Sesión registrada en la bitácora de %s." % topic["slug"])
    if not opts.get("no-build"):
        build(root, quiet=True)
    lines = []
    counts = run_check(root, topic["slug"], lambda k, w, m: lines.append("  %s %s: %s" % (
        "\u2716" if k == "error" else "\u26A0", w, m)))
    for l in lines[:12]:
        out(l)
    if len(lines) > 12:
        out("  … y %d más (coach check %s)" % (len(lines) - 12, topic["slug"]))
    if counts["error"]:
        out("\u2716 check: %d error(es), %d aviso(s)" % (counts["error"], counts["aviso"]))
    else:
        out("\u2714 check: sin errores (%s)" % plural(counts["aviso"], "aviso", "avisos"))
    out("\u25B6 Siguiente paso: %s" % siguiente)
    out("\U0001F4D3 Cuaderno: %s" % (root / "cuaderno.html").resolve())
    return 1 if counts["error"] else 0


STATE_ICON = {"completada": "\u2714", "convalidada": "\u23ED", "en-curso": "\u25B6", "pendiente": "\u00b7"}
LEVEL_LABEL = {"basico": "B\u00e1sico", "intermedio": "Intermedio", "avanzado": "Avanzado", "experto": "Experto"}


def cmd_estado(pos, opts):
    root = root_dir(opts)
    only = pos[0] if pos else None
    if only and not (root / only / "PLAN.md").is_file():
        raise CoachError("No existe el tema '%s' en %s." % (only, rel(root)))
    sums = sorted_summaries(root, only)
    if opts.get("json"):
        out(json.dumps({"raiz": rel(root), "metodo_pendiente": root_pending(root), "temas": sums},
                       ensure_ascii=False, indent=2))
        return
    if not root.is_dir() or not sums:
        out("\U0001F4DA Aún no hay temas en %s." % rel(root))
        out("   Crea uno con: coach init <slug> --tema \"Título del tema\"")
        return
    n = len(sums)
    out("\U0001F4DA Aprendizaje \u00b7 %d tema%s \u00b7 raíz: %s" % (n, "" if n == 1 else "s", rel(root)))
    if root_pending(root):
        out("\u26A0 El acuerdo de método tiene puntos sin acordar (coach metodo).")
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
        if s["examenes"]:
            out("  Exámenes  " + " \u00b7 ".join("M%s %s" % (e["modulo"], "\u2714" if e["hecho"] else
                                                             ("toca" if e["listo"] else "\u00b7")) for e in s["examenes"]))
        rv = s["repasos"]
        if rv["vencidos"]:
            out("  Repasos   %d vencido(s): %s" % (len(rv["vencidos"]), ", ".join(d["id"] for d in rv["vencidos"])))
        elif rv["proximo"]:
            out("  Repasos   próximo: %s (%s)" % (rv["proximo"]["fecha"], rv["proximo"]["id"]))
        if s["huecos_abiertos"]:
            g = s["huecos_abiertos"]
            out("  Huecos    %d abierto%s: %s" % (len(g), "" if len(g) == 1 else "s",
                                                  " \u00b7 ".join("%s %s%s" % (x["id"], x["hueco"],
                                                                               " (vencido)" if x["vencido"] else "")
                                                                  for x in g[:4])))
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
                for e in s["examenes"]:
                    if e["modulo"] == m["id"]:
                        out("    %s Examen M%s %s" % ("\u2714" if e["hecho"] else "\u00b7", e["modulo"], e["detalle"]))
    out("")
    out("\U0001F4D3 Cuaderno: %s" % rel(root / "cuaderno.html"))


# --------------------------------------------------------------------------- check

MERMAID_TYPES = {
    "flowchart", "graph", "sequencediagram", "classdiagram", "classdiagram-v2", "statediagram",
    "statediagram-v2", "erdiagram", "journey", "gantt", "pie", "quadrantchart", "requirementdiagram",
    "gitgraph", "c4context", "c4container", "c4component", "c4dynamic", "c4deployment", "mindmap",
    "timeline", "zenuml", "sankey", "sankey-beta", "xychart", "xychart-beta", "block", "block-beta",
    "packet", "packet-beta", "kanban", "architecture", "architecture-beta", "radar", "radar-beta",
    "treemap", "treemap-beta",
}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


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


def lint_markdown(relp, text, root, report, check_links=True):
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
                for c in split_cells(line):
                    for code in re.findall(r"`([^`]+)`", c):
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
    if not check_links:
        return
    pending = len(PENDING_RE.findall(prose))
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
    lines = list(block)
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
        longest_part = max((len(p) for p in re.split(r"<br\s*/?>", label)), default=0)
        if longest_part > 24:
            long_labels.append(label)
    if long_labels:
        longest = max(long_labels, key=len)
        report("aviso", relp, "%d etiqueta(s) de Mermaid de más de 24 caracteres («%s»): acorta o usa <br/>"
               % (len(long_labels), longest[:40]))


def cmd_check(pos, opts):
    root = root_dir(opts)
    only = pos[0] if pos else None

    def report(kind, where, msg):
        icon = "\u2716" if kind == "error" else "\u26A0"
        out("  %s %s: %s" % (icon, where, msg))

    out("\U0001F50E Revisando %s" % rel(root))
    counts = run_check(root, only, report)
    if counts["error"]:
        out("\u2716 %d error(es), %d aviso(s)" % (counts["error"], counts["aviso"]))
        return 1
    out("\u2714 Sin errores (%d aviso%s)" % (counts["aviso"], "" if counts["aviso"] == 1 else "s"))
    return 0


# --------------------------------------------------------------------------- migración

METODO_NUEVAS = [
    ("Pasos", "Uno a la vez: el coach espera tu resultado antes del siguiente"),
    ("Repasos", "Calendario de coach: lecciones a 3, 7, 14, 30 y 60 días; huecos a 1, 3, 7, 14 y 30"),
]


def migrate_topic(topic, changes):
    text = topic["text"]
    fm = topic["plan"]["fm"] or {}
    if fm_int(fm, "formato", 1) >= FORMATO:
        return None, []
    lines = text.split("\n")
    inserts = []
    for mi, mod in enumerate(topic["plan"]["modulos"]):
        if mod["examen"] is None and not mod["proyecto"] and mod["lecciones"]:
            _, at = module_insert_at(topic, mi)
            inserts.append((at, exam_line(mod["id"])))
            changes.append("%s: examen M%s añadido al plan" % (topic["slug"], mod["id"]))
    for at, line in sorted(inserts, reverse=True):
        lines = insert_lines(lines, at, [line])
    text = set_fm_raw("\n".join(lines), "formato", str(FORMATO))
    changes.append("%s: PLAN.md con formato: %d" % (topic["slug"], FORMATO))
    notes = []
    titles = {l["id"]: l for l in topic["plan"]["lecciones"]}
    for nid, note in topic["notes"].items():
        l = titles.get(nid)
        if not l or not l["hecha"] or l["convalidada"] or fm_str(note["fm"], "repaso"):
            continue
        if norm_state(fm_str(note["fm"], "estado")) != "completada":
            continue
        fin = parse_date(fm_str(note["fm"], "fin")) or today_date()
        nxt = (fin + timedelta(days=LESSON_INTERVALS[0])).isoformat()
        ntext = set_fm(note["text"], "repaso", nxt)
        ntext = set_fm_raw(ntext, "repasos", "0")
        notes.append((note["path"], ntext))
        changes.append("%s: lección %s con primer repaso el %s" % (topic["slug"], nid, nxt))
    return text, notes


def cmd_migrar(pos, opts):
    root = root_dir(opts)
    if not root.is_dir():
        raise CoachError("No existe %s." % rel(root))
    changes = []
    writes = []
    for slug in list_topics(root):
        topic = load_topic(root, slug)
        text, notes = migrate_topic(topic, changes)
        if text is not None:
            writes.append((topic["plan_path"], text))
            writes.extend(notes)
    metodo = root / "METODO.md"
    if metodo.is_file():
        mtext = read_text(metodo)
        lines, tbl, rows = metodo_rows(mtext)
        missing = [r for r in METODO_NUEVAS if fold(r[0]) not in rows]
        if tbl and missing and writes:
            lines = insert_lines(lines, tbl["last"] + 1, [fmt_row(list(r)) for r in missing])
            writes.append((metodo, "\n".join(lines)))
            changes.append("METODO.md: fila(s) nueva(s) %s" % ", ".join(r[0] for r in missing))
    if not writes:
        out("\u2714 %s ya está en el formato %d: no hay nada que migrar." % (rel(root), FORMATO))
        return 0
    if opts.get("dry-run"):
        out("\U0001F50D Migración de %s (simulación, no se escribe nada):" % rel(root))
        for c in changes:
            out("  \u2022 %s" % c)
        return 0
    stamp = now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".respaldos" / ("3.0-%s" % stamp)
    n = 2
    while backup.exists():
        backup = root / ".respaldos" / ("3.0-%s-%d" % (stamp, n))
        n += 1
    for relp in collect_files(root):
        dest = backup / relp
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(root / relp), str(dest))
    out("\U0001F4BE Copia de seguridad: %s" % rel(backup))
    for path, text in writes:
        write_text(path, text)
    out("\u2714 Migrado %s al formato %d:" % (rel(root), FORMATO))
    for c in changes:
        out("  \u2022 %s" % c)
    out("Nada se borró: solo se añadieron líneas y campos. Para deshacer, copia el respaldo encima.")
    maybe_build(root, opts)
    return 0


# --------------------------------------------------------------------------- vendor

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
        out("\u2716 %d descarga(s) fallaron. Revisa tu conexión y vuelve a intentarlo." % failures)
        return 1
    out("\u2714 Librerías en %s: el cuaderno funciona sin conexión." % rel(vdir))
    return 0


# --------------------------------------------------------------------------- CLI

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
    "metodo": cmd_metodo,
    "leccion": cmd_leccion,
    "nota": cmd_nota,
    "completar": cmd_completar,
    "reabrir": cmd_reabrir,
    "glosario": cmd_glosario,
    "duda": cmd_duda,
    "hueco": cmd_hueco,
    "repaso": cmd_repaso,
    "examen": cmd_examen,
    "siguiente": cmd_siguiente,
    "sesion": cmd_sesion,
    "estado": cmd_estado,
    "check": cmd_check,
    "vendor": cmd_vendor,
    "migrar": cmd_migrar,
}


def main(argv):
    try:
        pos, opts = parse_args(argv)
        if not pos or opts.get("help") or pos[0] in ("ayuda", "help"):
            out(AYUDA.format(v=VERSION, formato=FORMATO, claves=", ".join(k for k, _ in METODO_KEYS)))
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
