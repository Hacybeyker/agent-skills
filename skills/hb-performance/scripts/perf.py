#!/usr/bin/env python3
"""Captura, métricas, diagnóstico, comparación y reporte de hb-performance. Solo librería estándar (Python 3.8+).

Todo lo determinista lo hace este script; el modelo solo lee resúmenes cortos.

Comandos (cada uno con --help):
  nuevo         crea la carpeta de una investigación con plan.json y estado.md (recetas: arranque-frio, flujo)
  capturar      calentamiento, compilación y N corridas: traza, descarga, consultas y filas en metricas.csv
  diagnostico   corre las consultas de diagnóstico sobre la corrida mediana y la peor, y escribe diagnostico.md
  consulta      una consulta SQL acotada sobre una traza, para una pregunta puntual
  resumen       estadísticas por fase y avisos de estabilidad
  comparar      antes contra después, con veredicto por métrica
  har           métricas de red desde los HAR de testigo
  reporte       reporte inicial (diagnóstico y plan) o final (propuesto contra logrado), en markdown y HTML
  decidir       registra qué mejoras se aprueban, se descartan o quedan pendientes (sin chat)
  siguiente     el paso que sigue, con sus comandos completos; también lo escribe en estado.md
  instrumentar  copia la instrumentación genérica (secciones HTTP, QUEUE, CONN, TTFB, SCREEN y NAV) a un módulo

Códigos de salida: 0 bien · 2 uso o datos inválidos · 3 precondición (dispositivo, app o herramientas) ·
4 captura fallida · 5 no se juntaron las corridas válidas pedidas.
"""
import argparse
import csv
import datetime
import fnmatch
import gzip
import html
import json
import math
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

VERSION = "0.3.0"
HERE = pathlib.Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
REQUIRED = ["fase", "flujo", "metrica", "corrida", "valor"]
COLUMNS = REQUIRED + ["unidad", "sentido", "familia"]
FASES = ("antes", "control", "despues")
FAMILIAS = ("app", "e2e", "info")
MIN_RUNS = 5
CV_MAX = 10.0
MAX_ROWS = 30
REMOTE_DIR = "/data/misc/perfetto-traces"
DUPLICATE_WINDOW_NS = 2_000_000_000
MAIN_SLICE_MIN_NS = 5_000_000
LONG_SLICE_NS = 100_000_000
CORE = ["ttid_ms", "ttfd_ms", "bind_application_ms", "jit_ms", "jank_app_pct", "frame_p90_ms", "hilo_slices_sobre_presupuesto",
        "hilo_slices_100ms", "hilo_max_ms", "inflate_cantidad", "inflate_ms", "red_llamadas", "red_solapadas",
        "red_repetidas_2s", "gfx_jank_pct", "gfx_p90_ms", "pss_mb", "java_heap_mb", "activities", "views"]
FRAME_METRICS = ("jank_app_pct", "jank_total_pct", "frame_p50_ms", "frame_p90_ms", "frame_p99_ms")
FRAMES_CHANGE_MAX = 0.5
NOT_JANK = {"", "None", "Unknown", "Unknown Jank", "Buffer Stuffing", "SurfaceFlinger Stuffing"}
COMMON_HZ = (24, 30, 48, 50, 60, 72, 75, 90, 96, 100, 120, 144, 165, 240)
VERDICT_CLASS = {"mejora": "v-better", "regresión": "v-worse", "sin cambio": "v-same", "dentro del ruido": "v-same",
                 "informativa": "v-same", "no comparable": "v-same"}
FICHA_REPORTE = ("alcance", "síntoma", "sintoma", "métricas principales", "metricas principales", "build",
                 "dispositivo", "modos")
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                        r"|[0-9a-fA-F]{16,})$")
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
MARKER = "hbperf_marker"
ESTADOS = ("propuesta", "aprobada", "descartada", "pendiente", "aplicada")
QUERY_TAG = re.compile(r" #[0-9a-f]{4,8}$")
e = html.escape


class PerfError(Exception):
    code = 2


class Precondicion(PerfError):
    code = 3


class CapturaFallida(PerfError):
    code = 4


class CorridasInsuficientes(PerfError):
    code = 5


# ── CSV ──────────────────────────────────────────────────────────────────────

def normalize_phase(value):
    phase = (value or "").strip().lower().replace("é", "e")
    if phase not in FASES:
        raise PerfError("fase '%s' no válida: usa %s" % (value, ", ".join(FASES)))
    return phase


def read_rows(path):
    path = pathlib.Path(path)
    if not path.is_file():
        raise PerfError("no existe %s" % path)
    if path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise PerfError("%s no tiene las columnas: %s" % (path, ", ".join(missing)))
        rows = []
        for line, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                continue
            where = "%s:%d" % (path, line)
            try:
                value = float(row["valor"])
            except (TypeError, ValueError):
                raise PerfError("%s: valor '%s' no es un número" % (where, row["valor"]))
            if math.isnan(value) or math.isinf(value):
                raise PerfError("%s: valor '%s' no es un número finito" % (where, row["valor"]))
            sense = (row.get("sentido") or "menor").strip().lower() or "menor"
            if sense not in ("menor", "mayor"):
                raise PerfError("%s: sentido '%s' no válido: usa menor o mayor" % (where, sense))
            family = (row.get("familia") or "app").strip().lower() or "app"
            if family not in FAMILIAS:
                raise PerfError("%s: familia '%s' no válida: usa %s" % (where, family, ", ".join(FAMILIAS)))
            try:
                phase = normalize_phase(row["fase"])
            except PerfError as error:
                raise PerfError("%s: %s" % (where, error))
            rows.append({"fase": phase, "flujo": (row["flujo"] or "").strip(), "metrica": (row["metrica"] or "").strip(),
                         "corrida": (row["corrida"] or "").strip(), "valor": value,
                         "unidad": (row.get("unidad") or "").strip(), "sentido": sense, "familia": family})
    return rows


def append_rows(path, new_rows):
    path = pathlib.Path(path)
    has_rows = path.is_file() and path.stat().st_size > 0
    fieldnames = COLUMNS
    if has_rows:
        with path.open(newline="", encoding="utf-8") as f:
            fieldnames = next(csv.reader(f))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not has_rows:
            writer.writeheader()
        writer.writerows(new_rows)


def metric_row(phase, flow, run, metric, value, unit, family, sense="menor"):
    return {"fase": phase, "flujo": flow, "metrica": metric, "corrida": str(run), "valor": fmt(value),
            "unidad": unit, "sentido": sense, "familia": family}


def group(rows):
    """{(flujo, metrica): {"unidad", "sentido", "familia", "fases": {fase: [valores]}}}"""
    groups = {}
    for row in rows:
        key = (row["flujo"], row["metrica"])
        entry = groups.setdefault(key, {"unidad": row["unidad"], "sentido": row["sentido"],
                                        "familia": row["familia"], "fases": {}})
        if entry["sentido"] != row["sentido"]:
            raise PerfError("la métrica '%s' del flujo '%s' tiene sentidos distintos" % (key[1], key[0]))
        if row["unidad"] and not entry["unidad"]:
            entry["unidad"] = row["unidad"]
        entry["fases"].setdefault(row["fase"], []).append(row["valor"])
    return groups


# ── Estadística ──────────────────────────────────────────────────────────────

def percentile(values, q):
    """Percentil por rango más cercano: con pocas corridas, el P90 coincide con el máximo."""
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


def cv(values):
    """Coeficiente de variación en %, o None si no se puede calcular."""
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0 if all(v == 0 for v in values) else None
    return statistics.stdev(values) / abs(mean) * 100


def describe(values, cv_max=CV_MAX):
    data = {"n": len(values), "mediana": statistics.median(values), "p90": percentile(values, 0.9),
            "min": min(values), "max": max(values), "cv": cv(values)}
    data["avisos"] = []
    if data["n"] < MIN_RUNS:
        data["avisos"].append("pocas corridas")
    if data["cv"] is not None and data["cv"] > cv_max:
        data["avisos"].append("inestable")
    return data


def verdict(before, after, sense, control=None):
    """Conservador: la mediana de después tiene que salir del rango [mín, máx] de antes.

    Con un bloque de control (prueba A/A), una diferencia no mayor que el ruido es "dentro del ruido".
    """
    mb, ma = statistics.median(before), statistics.median(after)
    delta = ma - mb
    if delta == 0:
        return "sin cambio"
    if control and abs(delta) <= abs(statistics.median(control) - mb):
        return "dentro del ruido"
    lower_is_better = sense == "menor"
    better = delta < 0 if lower_is_better else delta > 0
    outside_better = ma < min(before) if lower_is_better else ma > max(before)
    outside_worse = ma > max(before) if lower_is_better else ma < min(before)
    if better and outside_better:
        return "mejora"
    if not better and outside_worse:
        return "regresión"
    return "sin cambio"


def frames_changed(groups, flow):
    """True si la mediana de frames cambió más de FRAMES_CHANGE_MAX entre antes y después."""
    entry = groups.get((flow, "frames"))
    if not entry or "antes" not in entry["fases"] or "despues" not in entry["fases"]:
        return False
    before = statistics.median(entry["fases"]["antes"])
    after = statistics.median(entry["fases"]["despues"])
    return abs(after - before) > FRAMES_CHANGE_MAX * max(before, 1)


def compare(rows, cv_max=CV_MAX):
    results, unmatched = [], []
    groups = group(rows)
    for (flow, metric), entry in sorted(groups.items()):
        phases = entry["fases"]
        if "antes" not in phases or "despues" not in phases:
            unmatched.append({"flujo": flow, "metrica": metric, "fases": sorted(phases)})
            continue
        before, after = describe(phases["antes"], cv_max), describe(phases["despues"], cv_max)
        control = phases.get("control")
        delta = after["mediana"] - before["mediana"]
        noise = abs(statistics.median(control) - before["mediana"]) if control else None
        warnings = set(before["avisos"] + after["avisos"])
        if entry["familia"] == "info":
            result = "informativa"
        elif metric in FRAME_METRICS and frames_changed(groups, flow):
            result = "no comparable"
            warnings.add("frames distintos")
        else:
            result = verdict(phases["antes"], phases["despues"], entry["sentido"], control)
        results.append({
            "flujo": flow, "metrica": metric, "unidad": entry["unidad"], "sentido": entry["sentido"],
            "familia": entry["familia"], "antes": before, "despues": after,
            "control": describe(control, cv_max) if control else None, "delta": delta,
            "delta_pct": delta / abs(before["mediana"]) * 100 if before["mediana"] else None,
            "ruido": noise,
            "ruido_pct": noise / abs(before["mediana"]) * 100 if noise is not None and before["mediana"] else None,
            "veredicto": result, "avisos": sorted(warnings),
        })
    return results, unmatched


# ── Formato ──────────────────────────────────────────────────────────────────

def fmt(value, unit=""):
    if value is None:
        return "—"
    text = ("%.2f" % value).rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return "%s %s" % (text, unit) if unit else text


def fmt_signed(value, unit=""):
    return "—" if value is None else ("+" if value > 0 else "") + fmt(value, unit)


def fmt_pct(value, signed=True):
    return "—" if value is None else (fmt_signed(value) if signed else fmt(value)) + " %"


def fmt_cell(value):
    """Celdas de trace_processor: números con hasta 2 decimales, NULL como guion."""
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except ValueError:
        return value
    return fmt(number) if math.isfinite(number) else value


def markdown_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return "\n".join(lines)


def load_plan_beside(csv_path):
    plan_path = pathlib.Path(csv_path).parent / "plan.json"
    return load_plan(plan_path) if plan_path.is_file() else {}


def user_metric_names(plan):
    return [m["nombre"] for flow in (plan.get("flujos") or {}).values() for m in flow.get("metricas_usuario", [])]


def priority(metric, plan):
    principales = plan.get("principales") or []
    user = user_metric_names(plan)
    if metric in principales:
        return (0, principales.index(metric), metric)
    if metric in user:
        return (1, user.index(metric), metric)
    if metric in CORE:
        return (2, CORE.index(metric), metric)
    return (3, 0, metric)


def summary_rows(rows, plan, phases=FASES, flows=None, everything=False):
    table, hidden = [], 0
    for (flow, metric), entry in sorted(group(rows).items(), key=lambda kv: (kv[0][0], priority(kv[0][1], plan))):
        if flows and flow not in flows:
            continue
        for phase in phases:
            values = entry["fases"].get(phase)
            if not values:
                continue
            s = describe(values)
            important = priority(metric, plan)[0] < 3 or s["avisos"]
            if not everything and not important:
                hidden += 1
                continue
            unit = entry["unidad"]
            table.append([phase, flow, metric, entry["familia"], s["n"], fmt(s["mediana"], unit), fmt(s["p90"], unit),
                          "%s – %s" % (fmt(s["min"]), fmt(s["max"])), fmt_pct(s["cv"], signed=False),
                          ", ".join(s["avisos"]) or "—"])
    return table, hidden


SUMMARY_HEADERS = ["Fase", "Flujo", "Métrica", "Familia", "n", "Mediana", "P90", "Mín – máx", "CV", "Avisos"]
COMPARE_HEADERS = ["Flujo", "Métrica", "Familia", "Antes (mediana / P90)", "Después (mediana / P90)", "Δ", "Δ %",
                   "Ruido (A/A)", "Veredicto", "Avisos"]


def compare_cells(r):
    unit = r["unidad"]
    return [r["flujo"], r["metrica"], r["familia"],
            "%s / %s" % (fmt(r["antes"]["mediana"], unit), fmt(r["antes"]["p90"], unit)),
            "%s / %s" % (fmt(r["despues"]["mediana"], unit), fmt(r["despues"]["p90"], unit)),
            fmt_signed(r["delta"], unit), fmt_pct(r["delta_pct"]),
            fmt_pct(r["ruido_pct"], signed=False) if r["control"] else "—", r["veredicto"],
            ", ".join(r["avisos"]) or "—"]


def compact_compare(results, plan, everything=False):
    chosen = [r for r in results if everything or priority(r["metrica"], plan)[0] < 3
              or r["veredicto"] in ("mejora", "regresión")]
    chosen.sort(key=lambda r: (r["flujo"], priority(r["metrica"], plan)))
    return chosen


def update_block(folder, name, content):
    """Reemplaza el bloque <!-- perf:name --> ... <!-- /perf:name --> de estado.md, si existe."""
    state = pathlib.Path(folder) / "estado.md"
    if not state.is_file():
        return False
    text = state.read_text(encoding="utf-8")
    pattern = re.compile(r"(<!-- perf:%s -->)(.*?)(<!-- /perf:%s -->)" % (name, name), re.S)
    if not pattern.search(text):
        return False
    state.write_text(pattern.sub(lambda m: m.group(1) + "\n" + content.strip() + "\n" + m.group(3), text, count=1),
                     encoding="utf-8")
    return True


# ── Plan ─────────────────────────────────────────────────────────────────────

def load_plan(path):
    path = pathlib.Path(path)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PerfError("no se pudo leer %s: %s" % (path, error))
    if not isinstance(plan, dict) or not plan.get("paquete") or not isinstance(plan.get("flujos"), dict):
        raise PerfError("%s necesita 'paquete' y 'flujos'" % path)
    for name, flow in plan["flujos"].items():
        if not isinstance(flow, dict):
            raise PerfError("el flujo '%s' de %s debe ser un objeto" % (name, path))
        route = flow.get("recorrido")
        if isinstance(route, dict) and route.get("tipo") != "arranque-frio":
            raise PerfError("'%s.recorrido': como objeto solo admite {\"tipo\": \"arranque-frio\", \"actividad\", "
                            "\"espera_s\"}" % name)
        families = flow.get("familias") or {}
        if not isinstance(families, dict) or any(v not in FAMILIAS for v in families.values()):
            raise PerfError("'%s.familias' debe mapear métricas a %s" % (name, ", ".join(FAMILIAS)))
        for spec in flow.get("metricas_sql", []):
            if not isinstance(spec, dict) or not spec.get("archivo"):
                raise PerfError("'%s.metricas_sql': cada entrada necesita 'archivo'" % name)
        for spec in flow.get("metricas_usuario", []):
            if not isinstance(spec, dict) or not spec.get("nombre") or not isinstance(spec.get("desde"), dict) \
                    or not isinstance(spec.get("hasta"), dict):
                raise PerfError("métrica de usuario inválida en '%s': necesita nombre, desde y hasta" % name)
            for side in ("desde", "hasta"):
                marker = spec[side]
                if not marker.get("marca") or marker.get("punto", "inicio") not in ("inicio", "fin") \
                        or marker.get("cual", "primera") not in ("primera", "ultima"):
                    raise PerfError("'%s.%s' en '%s': usa marca, punto (inicio|fin) y cual (primera|ultima)"
                                    % (spec["nombre"], side, name))
    for item in plan.get("mejoras", []):
        if not isinstance(item, dict) or not item.get("id") or not item.get("titulo"):
            raise PerfError("%s: cada mejora necesita al menos 'id' y 'titulo'" % path)
        if item.get("estado", "propuesta") not in ESTADOS:
            raise PerfError("%s: la mejora %s tiene estado '%s': usa %s" % (path, item["id"], item.get("estado"),
                                                                           ", ".join(ESTADOS)))
    if plan.get("instalar") is not None and not isinstance(plan["instalar"], str):
        raise PerfError("%s: 'instalar' es el comando que compila e instala el build de profiling (texto)" % path)
    return plan


def startup_spec(flow):
    route = flow.get("recorrido")
    return route if isinstance(route, dict) and route.get("tipo") == "arranque-frio" else None


# ── Métricas de una traza ────────────────────────────────────────────────────

def parse_markdown_sets(text):
    """Salida markdown de trace_processor (modo agente sin --format): tablas separadas por líneas en blanco."""
    sets, current = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                current.append(cells)
        elif current:
            sets.append((current[0], [[None if c in ("[NULL]", "NULL") else c for c in row] for row in current[1:]]))
            current = []
    return sets


def parse_result_sets(text):
    """Salida CSV de trace_processor: un bloque por consulta, separados por una línea en blanco."""
    if text.lstrip().startswith("|"):
        return parse_markdown_sets(text)
    sets, current = [], []
    for line in text.splitlines():
        if not line.strip():
            if current:
                sets.append(current)
                current = []
            continue
        current.append(line)
    if current:
        sets.append(current)
    parsed = []
    for block in sets:
        reader = list(csv.reader(block))
        header, body = reader[0], reader[1:]
        parsed.append((header, [[None if c == "[NULL]" else c for c in row] for row in body]))
    return parsed


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def trace_rows(header, body):
    """Filas (tipo, ts, dur, prof, nombre) de la consulta de metricas.sql."""
    index = {name: i for i, name in enumerate(header)}
    for column in ("tipo", "ts", "dur", "prof", "nombre"):
        if column not in index:
            raise PerfError("la consulta de métricas no devolvió la columna '%s'" % column)
    return [(row[index["tipo"]], to_int(row[index["ts"]]), to_int(row[index["dur"]], -1), to_int(row[index["prof"]]),
             row[index["nombre"]] or "") for row in body]


def call_key(section_name):
    """Lo que sigue al prefijo (HTTP, TTFB, QUEUE, CONN): método, plantilla y la marca de la query si la hay."""
    return section_name.split(" ", 1)[1] if " " in section_name else section_name


def endpoint_of(section_name):
    """Método y plantilla, sin la marca de la query: la clave de las métricas por endpoint."""
    return QUERY_TAG.sub("", call_key(section_name))


def assign(calls, subs):
    """Duración de las sub-secciones (TTFB, QUEUE, CONN) por llamada. Cada una va a una llamada con la misma clave
    que la contiene: primero a la más antigua que todavía no tiene una; si todas tienen (redirección o reintento),
    se suma a la que empezó más recientemente."""
    owned, taken = [0] * len(calls), [False] * len(calls)
    for sub in sorted(subs, key=lambda s: s[1]):
        if sub[2] <= 0:
            continue
        owners = [i for i, c in enumerate(calls) if call_key(c[4]) == call_key(sub[4]) and c[2] > 0
                  and c[1] <= sub[1] <= c[1] + c[2]]
        if not owners:
            continue
        free = [i for i in owners if not taken[i]]
        chosen = min(free, key=lambda i: calls[i][1]) if free else max(owners, key=lambda i: calls[i][1])
        owned[chosen] += sub[2]
        taken[chosen] = True
    return owned


def network_metrics(sections, known_endpoints, force):
    """Llamadas, solapadas, repetidas, conexiones y, por endpoint: llamadas, duración, TTFB, cola y cliente."""
    calls = [s for s in sections if s[4].startswith("HTTP ")]
    if not calls and not known_endpoints and not force:
        return []
    subs = {kind: [s for s in sections if s[4].startswith(kind + " ")] for kind in ("TTFB", "QUEUE", "CONN")}
    out = [("red_llamadas", len(calls), "llamadas", "app")]
    by_key = {}
    for s in calls:
        by_key.setdefault(call_key(s[4]), []).append(s)
    overlapped = repeated = 0
    for items in by_key.values():  # la misma plantilla y la misma query: una carga duplicada
        items.sort(key=lambda s: s[1])
        for i, s in enumerate(items):
            if any(p[2] > 0 and p[1] < s[1] < p[1] + p[2] for p in items[:i]):
                overlapped += 1
            if i > 0 and s[1] - items[i - 1][1] < DUPLICATE_WINDOW_NS:
                repeated += 1
    out.append(("red_solapadas", overlapped, "llamadas", "app"))
    out.append(("red_repetidas_2s", repeated, "llamadas", "app"))
    if subs["CONN"]:
        out.append(("red_conexiones", len(subs["CONN"]), "conexiones", "app"))
        out.append(("red_conexion_ms", sum(max(c[2], 0) for c in subs["CONN"]) / 1e6, "ms", "e2e"))
    owned = {kind: assign(calls, items) for kind, items in subs.items()}
    by_endpoint = {}
    for i, s in enumerate(calls):
        by_endpoint.setdefault(endpoint_of(s[4]), []).append(i)
    for endpoint in sorted(set(by_endpoint) | set(known_endpoints)):
        indexes = [i for i in by_endpoint.get(endpoint, []) if calls[i][2] > 0]
        out.append(("red %s llamadas" % endpoint, len(by_endpoint.get(endpoint, [])), "llamadas", "app"))
        if not indexes:
            continue
        out.append(("red %s ms" % endpoint, statistics.median(calls[i][2] / 1e6 for i in indexes), "ms", "e2e"))
        with_ttfb = [i for i in indexes if owned["TTFB"][i]]
        if with_ttfb:
            out.append(("red %s ttfb_ms" % endpoint, statistics.median(owned["TTFB"][i] / 1e6 for i in with_ttfb),
                        "ms", "e2e"))
            client = [max(0.0, (calls[i][2] - owned["TTFB"][i] - owned["QUEUE"][i] - owned["CONN"][i]) / 1e6)
                      for i in with_ttfb]
            out.append(("red %s cliente_ms" % endpoint, statistics.median(client), "ms", "app"))
            if subs["QUEUE"]:  # solo las que llegaron al servidor: con un hit de caché, QUEUE dura toda la llamada
                out.append(("red %s cola_ms" % endpoint, statistics.median(owned["QUEUE"][i] / 1e6 for i in with_ttfb),
                            "ms", "app"))
    return out


def resolve_marker(sections, marker, default_point, default_which, after=None):
    point = marker.get("punto", default_point)
    which = marker.get("cual", default_which)
    times = [s[1] if point == "inicio" else s[1] + max(s[2], 0) for s in sections
             if fnmatch.fnmatchcase(s[4], marker["marca"])]
    if after is not None:
        times = [t for t in times if t >= after]
    if not times:
        return None
    return min(times) if which == "primera" else max(times)


def user_metrics(sections, specs):
    out, missing = [], []
    for spec in specs:
        start = resolve_marker(sections, spec["desde"], "inicio", "primera")
        end = resolve_marker(sections, spec["hasta"], "fin", "ultima", after=start) if start is not None else None
        if start is None or end is None:
            missing.append(spec["nombre"])
            continue
        out.append((spec["nombre"], (end - start) / 1e6, "ms", spec.get("familia", "e2e")))
    return out, missing


def merged_top_level(intervals):
    """Intervalos que no están dentro de otro (para no contar dos veces un inflate anidado)."""
    top, end = [], -1
    for ts, dur in sorted(intervals):
        if ts >= end:
            top.append((ts, dur))
            end = ts + max(dur, 0)
    return top


def hz_from_vsync(period_ns):
    """Tasa de refresco a partir del período esperado de los frames (FrameTimeline), redondeada a una común."""
    if not period_ns or period_ns <= 0:
        return None
    raw = 1e9 / period_ns
    near = min(COMMON_HZ, key=lambda hz: abs(hz - raw))
    return near if abs(near - raw) <= near * 0.06 else int(round(raw))


def with_families(metrics, overrides):
    """Aplica 'familias' del flujo: nombre exacto o patrón fnmatch → familia."""
    if not overrides:
        return metrics
    out = []
    for name, value, unit, family in metrics:
        chosen = overrides.get(name)
        if chosen is None:
            chosen = next((v for k, v in overrides.items() if fnmatch.fnmatchcase(name, k)), family)
        out.append((name, value, unit, chosen))
    return out


def trace_metrics(rows, hz, flow_spec, known, sdk):
    """Devuelve (métricas [(nombre, valor, unidad, familia)], motivo de invalidez o None, info)."""
    process = [r for r in rows if r[0] == "proceso"]
    frames = [r for r in rows if r[0] == "frame"]
    main = sorted((r for r in rows if r[0] == "hilo"), key=lambda r: r[1])
    sections = sorted((r for r in rows if r[0] == "seccion"), key=lambda r: r[1])
    launches = sorted((r for r in rows if r[0] == "lanzamiento"), key=lambda r: r[1])
    bounds = [r for r in rows if r[0] == "limites"]
    vsync = next((r[2] for r in rows if r[0] == "vsync" and r[2] > 0), 0)
    jit = next((r for r in rows if r[0] == "jit"), None)
    info = {"frames": len(frames), "secciones": len(sections),
            "duracion_s": bounds[0][2] / 1e9 if bounds and bounds[0][2] > 0 else None,
            "nombres": {}, "hz_traza": hz_from_vsync(vsync), "arranque": bool(launches)}
    hz = hz or info["hz_traza"] or 60
    info["hz"] = hz
    budget = 1e9 / hz
    for s in sections:
        info["nombres"][s[4]] = info["nombres"].get(s[4], 0) + 1
    if not process:
        return [], "la app no aparece en la traza", info
    for pattern in flow_spec.get("invalidar_si", []):
        hit = next((s[4] for s in sections if fnmatch.fnmatchcase(s[4], pattern)), None)
        if hit:
            return [], "apareció '%s'" % hit, info
    if sdk >= 31 and not frames:
        return [], "no hay frames de la app (¿estaba visible?)", info
    out = []
    if launches:
        launch_row = launches[0]
        if launch_row[2] > 0:
            out.append(("ttid_ms", launch_row[2] / 1e6, "ms", "app"))
        drawn = next((s for s in sections if s[4].startswith("reportFullyDrawn") and s[1] >= launch_row[1]), None)
        if drawn:
            out.append(("ttfd_ms", (drawn[1] - launch_row[1]) / 1e6, "ms", "app"))
        bind = next((r for r in main if r[4] == "bindApplication" and r[1] >= launch_row[1]), None)
        if bind:
            out.append(("bind_application_ms", bind[2] / 1e6, "ms", "app"))
    if frames:
        durations = [f[2] / 1e6 for f in frames if f[2] > 0]
        app_jank = sum(1 for f in frames if "App Deadline Missed" in f[4])
        any_jank = sum(1 for f in frames if {t.strip() for t in f[4].split(",")} - NOT_JANK)
        out += [("frames", len(frames), "frames", "info"),
                ("jank_app_pct", app_jank / len(frames) * 100, "%", "app"),
                ("jank_total_pct", any_jank / len(frames) * 100, "%", "info")]
        if durations:
            out += [("frame_p50_ms", percentile(durations, 0.5), "ms", "app"),
                    ("frame_p90_ms", percentile(durations, 0.9), "ms", "app"),
                    ("frame_p99_ms", percentile(durations, 0.99), "ms", "app")]
    top = [r for r in main if r[3] == 0 and r[2] >= MAIN_SLICE_MIN_NS]
    out += [("hilo_slices_sobre_presupuesto", sum(1 for r in top if r[2] > budget), "slices", "app"),
            ("hilo_slices_100ms", sum(1 for r in top if r[2] > LONG_SLICE_NS), "slices", "app"),
            ("hilo_max_ms", max((r[2] for r in top), default=0) / 1e6, "ms", "app")]
    if jit is not None:
        out.append(("jit_ms", max(jit[2], 0) / 1e6, "ms", "info"))
    inflates = merged_top_level([(r[1], r[2]) for r in main if r[4] == "inflate"])
    if inflates or "inflate_cantidad" in known:
        out += [("inflate_cantidad", len(inflates), "inflates", "app"),
                ("inflate_ms", sum(max(d, 0) for _, d in inflates) / 1e6, "ms", "app")]
    known_endpoints = {m[4:-9] for m in known if m.startswith("red ") and m.endswith(" llamadas")}
    out += network_metrics(sections, known_endpoints, force="red_llamadas" in known)
    markers = sorted(sections + main + launches, key=lambda r: r[1])
    users, missing = user_metrics(markers, flow_spec.get("metricas_usuario", []))
    out += users
    info["faltantes"] = missing
    return with_families(out, flow_spec.get("familias")), None, info


def sql_metrics(header, body, source):
    """Métricas propias de una consulta: columnas nombre y valor, y opcionales unidad y familia."""
    index = {name: i for i, name in enumerate(header)}
    if "nombre" not in index or "valor" not in index:
        raise PerfError("%s tiene que devolver las columnas 'nombre' y 'valor'" % source)
    out = []
    for row in body:
        try:
            value = float(row[index["valor"]])
        except (TypeError, ValueError):
            continue
        unit = (row[index["unidad"]] or "") if "unidad" in index else ""
        family = row[index["familia"]] if "familia" in index and row[index["familia"]] in FAMILIAS else "app"
        out.append((row[index["nombre"]], value, unit, family))
    return out


def parse_gfxinfo(text):
    out = []
    jank = re.search(r"Janky frames:\s*\d+\s*\(([\d.]+)%\)", text)
    p90 = re.search(r"90th percentile:\s*([\d.]+)ms", text)
    if jank:
        out.append(("gfx_jank_pct", float(jank.group(1)), "%", "app"))
    if p90:
        out.append(("gfx_p90_ms", float(p90.group(1)), "ms", "app"))
    return out


def parse_meminfo(text):
    out = []
    for name, pattern, unit in (("pss_mb", r"TOTAL PSS:\s*(\d+)", "MB"), ("java_heap_mb", r"Java Heap:\s*(\d+)", "MB"),
                                ("native_heap_mb", r"Native Heap:\s*(\d+)", "MB"),
                                ("activities", r"Activities:\s*(\d+)", "activities"),
                                ("views", r"Views:\s*(\d+)", "views")):
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            out.append((name, value / 1024 if unit == "MB" else value, unit, "app"))
    return out


# ── Herramientas externas ────────────────────────────────────────────────────

def find_tp(option):
    for candidate in (option, os.environ.get("TRACE_PROCESSOR"), shutil.which("trace_processor"),
                      shutil.which("trace_processor_shell")):
        if candidate and (shutil.which(candidate) or pathlib.Path(candidate).is_file()):
            return candidate
    raise Precondicion("falta trace_processor de Perfetto. Instálalo con la guía oficial "
                       "(curl -LO https://get.perfetto.dev/trace_processor && chmod +x trace_processor), "
                       "déjalo en el PATH o pásalo con --tp")


_TP_STYLE = {}


def tp_style(tp):
    """'csv' (v59+: --format csv, también dentro de un agente), 'query' (query -f) o 'legacy' (-q)."""
    if tp not in _TP_STYLE:
        try:
            result = subprocess.run([tp, "query", "--help"], capture_output=True, text=True, timeout=120)
            text = result.stdout + result.stderr
            _TP_STYLE[tp] = "csv" if "--format" in text else ("query" if result.returncode == 0 else "legacy")
        except (OSError, subprocess.SubprocessError):
            _TP_STYLE[tp] = "legacy"
    return _TP_STYLE[tp]


def run_tp(tp, trace, sql):
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
        query = f.name
    try:
        style = tp_style(tp)
        command = {"csv": [tp, "query", "--format", "csv", "-f", query, str(trace)],
                   "query": [tp, "query", "-f", query, str(trace)],
                   "legacy": [tp, "-q", query, str(trace)]}[style]
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        if result.returncode != 0 and style != "legacy":
            legacy = subprocess.run([tp, "-q", query, str(trace)], capture_output=True, text=True, timeout=900)
            if legacy.returncode == 0:
                result = legacy
        if result.returncode != 0:
            tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-5:])
            raise PerfError("trace_processor falló con %s:\n%s" % (pathlib.Path(trace).name, tail))
        return parse_result_sets(result.stdout)
    finally:
        os.unlink(query)


def run_tp_batch(tp, trace, queries):
    """Varias consultas en una sola pasada por la traza: {nombre: [(header, body), ...]}."""
    text = "".join("SELECT '%s' AS %s;\n%s\n;\n" % (name, MARKER, sql.strip()) for name, sql in queries)
    results, current = {name: [] for name, _ in queries}, None
    for header, body in run_tp(tp, trace, text):
        if header == [MARKER]:
            current = body[0][0] if body else None
        elif current in results:
            results[current].append((header, body))
    return results


def fill_sql(sql, package, params):
    """Reemplaza {{PAQUETE}}, {{TRAMO_MS}} (250 por defecto), {{HILO}} ('*') y los --param CLAVE=valor."""
    values = {"TRAMO_MS": "250", "HILO": "*"}
    values.update(params)
    if "{{PAQUETE}}" in sql:
        if not package:
            raise PerfError("esta consulta necesita --paquete (o un plan.json junto a la traza)")
        values["PAQUETE"] = package
    for key, value in values.items():
        sql = sql.replace("{{%s}}" % key, str(value))
    missing = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", sql)))
    if missing:
        raise PerfError("falta el valor de %s: pásalo con --param %s=..." % (", ".join(missing), missing[0]))
    return sql


def adb_binary():
    for candidate in (os.environ.get("ADB"), shutil.which("adb")):
        if candidate:
            return candidate
    home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if home and (pathlib.Path(home) / "platform-tools" / "adb").is_file():
        return str(pathlib.Path(home) / "platform-tools" / "adb")
    raise Precondicion("falta adb: instala las platform-tools del SDK de Android o déjalo en el PATH")


class Adb:
    def __init__(self, serial):
        self.base = [adb_binary()] + (["-s", serial] if serial else [])

    def run(self, *args, stdin=None, timeout=120):
        return subprocess.run(self.base + list(args), input=stdin, capture_output=True, text=True, timeout=timeout)

    def shell(self, command, stdin=None, timeout=120):
        return self.run("shell", command, stdin=stdin, timeout=timeout)


def select_device(serial):
    """--serial, el 'serial' del plan o ANDROID_SERIAL; si no, el único dispositivo conectado."""
    serial = serial or os.environ.get("ANDROID_SERIAL")
    result = subprocess.run([adb_binary(), "devices"], capture_output=True, text=True, timeout=60)
    devices = [line.split("\t")[0] for line in result.stdout.splitlines()[1:] if line.endswith("\tdevice")]
    if serial:
        if serial not in devices:
            raise Precondicion("el dispositivo %s no está conectado (conectados: %s)" % (serial, ", ".join(devices) or "ninguno"))
        return serial
    if not devices:
        raise Precondicion("no hay ningún dispositivo conectado con depuración USB autorizada (adb devices)")
    if len(devices) > 1:
        raise Precondicion("hay %d dispositivos conectados (%s): elige uno con --serial, o guárdalo en el plan con "
                           "'nuevo --serial'" % (len(devices), ", ".join(devices)))
    return devices[0]


def package_build(dump):
    """versionName, versionCode y lastUpdateTime de dumpsys package."""
    name = re.search(r"versionName=(\S+)", dump)
    code = re.search(r"versionCode=(\d+)", dump)
    updated = re.search(r"lastUpdateTime=([\d-]+ [\d:]+)", dump)
    return {"version": "%s (%s)" % (name.group(1) if name else "?", code.group(1) if code else "?"),
            "instalada": updated.group(1) if updated else None}


def preflight(adb, package, force):
    """Comprueba el dispositivo y la app. Devuelve (sdk, avisos, build instalado)."""
    warnings = []
    sdk = to_int(adb.shell("getprop ro.build.version.sdk").stdout.strip())
    if sdk < 29:
        raise Precondicion("el dispositivo tiene API %d: hace falta Android 10 (API 29) o superior" % sdk)
    if "package:" not in adb.shell("pm path %s" % package).stdout:
        raise Precondicion("la app %s no está instalada en el dispositivo" % package)
    dump = adb.shell("dumpsys package %s" % package).stdout
    flags = re.search(r"flags=\[([^\]]*)\]", dump)
    if flags and "DEBUGGABLE" in flags.group(1):
        warnings.append("el build instalado es debuggable: valen los conteos de red y las fugas, no los tiempos ni los frames")
    thermal = re.search(r"Thermal Status:\s*(\d+)", adb.shell("dumpsys thermalservice").stdout)
    if thermal and int(thermal.group(1)) > 0:
        if int(thermal.group(1)) >= 3 and not force:
            raise Precondicion("el dispositivo está caliente (Thermal Status %s): espera a que se enfríe o usa --forzar"
                               % thermal.group(1))
        warnings.append("el dispositivo está tibio (Thermal Status %s)" % thermal.group(1))
    battery = re.search(r"level:\s*(\d+)", adb.shell("dumpsys battery").stdout)
    if battery and int(battery.group(1)) < 50:
        warnings.append("batería al %s %%: cárgala sobre 50 %%" % battery.group(1))
    if sdk < 31:
        warnings.append("Android %s no tiene FrameTimeline: los frames salen de gfxinfo (gfx_*)" % sdk)
    return sdk, warnings, package_build(dump)


def resumed_activity(adb):
    text = adb.shell("dumpsys activity activities").stdout
    match = re.search(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)[=:]\s*ActivityRecord\{[^}]*?\s(\S+/\S+)", text)
    return match.group(1) if match else ""


def launcher_activity(adb, package):
    out = adb.shell("cmd package resolve-activity --brief -a android.intent.action.MAIN "
                    "-c android.intent.category.LAUNCHER %s" % package).stdout
    return next((line.strip() for line in reversed(out.splitlines()) if "/" in line), "")


def git_info():
    """Commit corto y si hay cambios sin commitear en el directorio actual, o (None, None) fuera de git."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=30)
        if head.returncode != 0:
            return None, None
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                               text=True, timeout=60)
        return head.stdout.strip(), bool(dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None


def git_is_ancestor(commit):
    try:
        return subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return True


# ── capturar ─────────────────────────────────────────────────────────────────

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "motivo"


def compress(path):
    target = path.with_name(path.name + ".gz")
    with path.open("rb") as source, gzip.open(str(target), "wb", compresslevel=6) as dest:
        shutil.copyfileobj(source, dest)
    path.unlink()
    return target


def wait_enter(message):
    try:
        return input(message).strip().lower()
    except EOFError:
        raise PerfError("el modo manual necesita una terminal para esperar Enter: usa --recorrido con un comando")


def settle(seconds):
    """Pausa para que el dispositivo se asiente; HB_PERF_ESPERA=0 la anula (tests)."""
    if os.environ.get("HB_PERF_ESPERA") != "0":
        time.sleep(seconds)


def drive(recorrido, label):
    """Recorre el flujo. Devuelve un motivo de invalidez o None."""
    if recorrido == "manual":
        answer = wait_enter("▶ %s: recorre el flujo y presiona Enter (x + Enter para descartarla) " % label)
        return "descartada por el usuario" if answer == "x" else None
    result = subprocess.run(recorrido, shell=True)
    return None if result.returncode == 0 else "el recorrido terminó con código %d" % result.returncode


def component_of(package, activity):
    """paquete/clase para am start -n: acepta "paquete/.Clase", "paquete/clase", ".Clase" o el nombre completo."""
    activity = (activity or "").strip()
    if not activity or "/" in activity:
        return activity
    return "%s/%s" % (package, activity)


def launch(adb, package, spec):
    """Arranque en frío con am start -W (la app ya está detenida). Devuelve (motivo de invalidez o None, métricas)."""
    component = component_of(package, spec.get("actividad")) or launcher_activity(adb, package)
    if not component:
        return "no se encontró la actividad de inicio de %s: ponla en recorrido.actividad" % package, []
    result = adb.shell("am start -W -n %s" % component, timeout=180)
    text = result.stdout + result.stderr
    time.sleep(float(spec.get("espera_s", 5)))
    if result.returncode != 0 or re.search(r"^Error", text, re.M):
        return "am start falló: %s" % (text.strip().splitlines() or ["sin salida"])[-1][:160], []
    state = re.search(r"LaunchState:\s*(\w+)", text)
    if state and state.group(1).upper() != "COLD":
        return ("el arranque fue %s y no en frío: algo despertó la app antes de lanzarla (widget, WorkManager, push)"
                % state.group(1)), []
    total = re.search(r"TotalTime:\s*(\d+)", text)
    return None, ([("ttid_ms", int(total.group(1)), "ms", "app")] if total else [])


def record_run(adb, config, recorrido, label, local, startup=None, package=None):
    """Graba una corrida. Devuelve (motivo de invalidez o None, métricas del recorrido)."""
    if startup:
        adb.shell("am force-stop %s" % package)
        settle(1)
    remote = "%s/hbperf-%d.perfetto-trace" % (REMOTE_DIR, os.getpid())
    started = adb.shell("perfetto --background --txt -c - -o %s" % remote, stdin=config)
    pid = (re.findall(r"\d+", started.stdout) or [None])[-1]
    if started.returncode != 0 or not pid:
        raise CapturaFallida("no se pudo iniciar Perfetto: %s" % (started.stderr or started.stdout).strip()[-300:])
    time.sleep(float(os.environ.get("HB_PERF_ESPERA", "1.5")))  # Perfetto tarda en arrancar sus fuentes
    if startup:
        reason, extra = launch(adb, package, startup)
    else:
        reason, extra = drive(recorrido, label), []
    adb.shell("kill -TERM %s" % pid)
    for _ in range(60):
        if adb.shell("kill -0 %s" % pid).returncode != 0:
            break
        time.sleep(0.5)
    pulled = adb.run("pull", remote, str(local), timeout=600)
    adb.shell("rm -f %s" % remote)
    if pulled.returncode != 0 or not local.is_file() or local.stat().st_size < 1024:
        raise CapturaFallida("no se pudo descargar la traza: %s" % (pulled.stderr or pulled.stdout).strip()[-300:])
    return reason, extra


def app_died(adb, package):
    """True solo si pidof respondió que la app no corre (un pidof que no existe no cuenta como caída)."""
    result = adb.shell("pidof %s" % package)
    return result.returncode == 1 and not result.stdout.strip()


def crash_excerpt(adb, package):
    """Primeras líneas del último crash de la app en logcat -b crash."""
    lines = adb.shell("logcat -b crash -d -t 400").stdout.splitlines()
    starts = [i for i, line in enumerate(lines) if "FATAL EXCEPTION" in line]
    for start in reversed(starts):
        block = lines[start:start + 14]
        if any(package in line for line in block):
            return block
    return []


def mapping_hint():
    found = sorted(pathlib.Path(".").glob("*/build/outputs/mapping/profiling/mapping.txt"))
    target = str(found[0]) if found else "<módulo>/build/outputs/mapping/profiling/mapping.txt"
    return "desofusca la pila con: retrace %s <archivo-con-la-pila> (cmdline-tools del SDK)" % target


def known_metrics(csv_path, flow):
    if not csv_path.is_file():
        return set()
    return {r["metrica"] for r in read_rows(csv_path) if r["flujo"] == flow}


def next_run_number(csv_path, phase, flow):
    if not csv_path.is_file():
        return 1
    runs = [to_int(r["corrida"]) for r in read_rows(csv_path) if r["fase"] == phase and r["flujo"] == flow]
    return max(runs, default=0) + 1


def run_line(n, size_mb, metrics):
    values = {m[0]: m for m in metrics}
    parts = ["corrida %s" % n, "%.0f MB" % size_mb]
    for name, label in (("ttid_ms", "TTID"), ("ttfd_ms", "TTFD"), ("jank_app_pct", "jank app"),
                        ("frame_p90_ms", "P90 frame"), ("hilo_slices_sobre_presupuesto", "hilo > presupuesto"),
                        ("hilo_max_ms", "hilo máx"), ("inflate_cantidad", "inflates"), ("red_llamadas", "red"),
                        ("red_solapadas", "solapadas"), ("gfx_jank_pct", "jank gfx"), ("pss_mb", "PSS")):
        if name in values:
            parts.append("%s %s" % (label, fmt(values[name][1], values[name][2] if values[name][2] in ("%", "ms", "MB") else "")))
    return "✔ " + " · ".join(parts)


def read_phases(folder):
    path = pathlib.Path(folder) / "fases.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return {}


def write_phase(folder, phase, data):
    phases = read_phases(folder)
    previous = phases.get(phase) or {}
    data["corridas"] = previous.get("corridas", 0) + data.get("corridas", 0)
    data["fecha"] = previous.get("fecha") or data["fecha"]
    phases[phase] = data
    (pathlib.Path(folder) / "fases.json").write_text(json.dumps(phases, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")


def check_build(folder, phase, build, commit, force):
    """Avisos (o un error) según el build y el commit que midió antes."""
    before = read_phases(folder).get("antes")
    if not before or phase == "antes":
        return []
    same = bool(before.get("instalada")) and before.get("instalada") == build.get("instalada") \
        and before.get("version") == build.get("version")
    notes = []
    if phase == "despues" and same and not force:
        raise Precondicion("el build instalado es el mismo que midió antes (instalado %s): instala el build con la "
                           "mejora, o usa --forzar si es a propósito" % before["instalada"])
    if phase == "control" and not same:
        notes.append("control no usa el mismo build que antes: el bloque A/A tiene que repetir el estado inicial")
    if phase == "despues":
        if before.get("commit") and commit and not git_is_ancestor(before["commit"]):
            notes.append("el commit de antes (%s) no es ancestro del actual: la línea base puede no representar "
                         "este código" % before["commit"])
        try:
            days = (datetime.datetime.now() - datetime.datetime.fromisoformat(before["fecha"])).days
        except (KeyError, TypeError, ValueError):
            days = 0
        if days > 14:
            notes.append("la línea base es de hace %d días: si cambió algo más que la mejora, vuelve a medir antes" % days)
    return notes


PROFILE_RESULTS = {"0": "no recibido", "1": "instalado", "2": "ya estaba instalado",
                   "6": "el APK no trae Baseline Profile"}
COMPILATIONS = ("completa", "perfil")


def install_baseline_profile(adb, package):
    command = ("am broadcast -a androidx.profileinstaller.action.INSTALL_PROFILE "
               "%s/androidx.profileinstaller.ProfileInstallReceiver" % package)
    code = "?"
    for attempt in range(2):
        code = (re.findall(r"result=(-?\d+)", adb.shell(command, timeout=120).stdout) or ["?"])[-1]
        if code in ("1", "2"):
            break
        settle(2)
    return code


def fix_compilation(adb, package, mode):
    """Compilación de ART igual en todas las fases. Devuelve la descripción que queda en fases.json.

    - completa: todo el código compilado antes de correr (Macrobenchmark CompilationMode.Full). No depende de
      perfiles ni de librerías: es la opción para comparar un cambio de código.
    - perfil: perfiles borrados, Baseline Profile del APK instalado con profileinstaller y speed-profile
      (CompilationMode.Partial). Más parecido a una instalación de Play; para medir un Baseline Profile.

    Sin esto, el resultado depende de la historia del dispositivo: un build recién instalado corre con JIT y uno
    que ya se abrió varias veces, compilado con su perfil de uso.
    """
    adb.shell("am force-stop %s" % package)
    if mode == "completa":
        compiled = adb.shell("cmd package compile -f -m speed %s" % package, timeout=900)
        if "Success" not in compiled.stdout:
            raise Precondicion("no se pudo compilar la app (speed): %s" % (compiled.stdout + compiled.stderr).strip()[-200:])
        print("✔ compilación de ART fijada: completa (speed), igual en todas las fases")
        return "completa (speed)"
    adb.shell("cmd package compile --reset %s" % package, timeout=600)
    code = install_baseline_profile(adb, package)
    adb.shell("am force-stop %s" % package)
    if code not in ("1", "2"):
        raise Precondicion("no se pudo instalar el Baseline Profile (%s): mide todas las fases con "
                           "--compilacion completa" % PROFILE_RESULTS.get(code, "resultado %s" % code))
    compiled = adb.shell("cmd package compile -f -m speed-profile %s" % package, timeout=600)
    if "Success" not in compiled.stdout:
        raise Precondicion("no se pudo compilar la app (speed-profile): %s"
                           % (compiled.stdout + compiled.stderr).strip()[-200:])
    print("✔ compilación de ART fijada: perfiles borrados, Baseline Profile instalado y speed-profile")
    return "perfil (Baseline Profile + speed-profile)"


def discard_phase(folder, csv_path, phase, flow):
    """--rehacer: saca del CSV las filas de la fase y aparta sus trazas, para medirla de nuevo desde cero."""
    stamp = datetime.datetime.now().strftime("%H%M%S")
    if csv_path.is_file():
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames, kept, dropped = reader.fieldnames, [], 0
            for row in reader:
                if normalize_phase(row["fase"]) == phase and (row["flujo"] or "").strip() == flow:
                    dropped += 1
                else:
                    kept.append(row)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept)
        print("✔ --rehacer: %d filas de '%s' fuera del CSV" % (dropped, phase))
    old = folder / phase
    if old.is_dir() and any(old.iterdir()):
        old.rename(folder / ("%s-descartada-%s" % (phase, stamp)))
        print("✔ --rehacer: trazas anteriores en %s-descartada-%s/" % (phase, stamp))
    (folder / phase).mkdir(parents=True, exist_ok=True)
    phases = read_phases(folder)
    if phases.pop(phase, None) is not None:
        (folder / "fases.json").write_text(json.dumps(phases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_config(plan, folder, override):
    name = override or plan.get("config", "base")
    path = ASSETS / "perfetto" / ("%s.pbtx" % name)
    if not path.is_file():
        path = pathlib.Path(name) if pathlib.Path(name).is_absolute() else folder / name
    if not path.is_file():
        raise PerfError("no existe la configuración de Perfetto '%s' (las de la skill: base, completa, cpu)" % name)
    return path


def custom_queries(flow, folder, package):
    queries = []
    for spec in flow.get("metricas_sql", []):
        path = folder / spec["archivo"]
        if not path.is_file():
            raise PerfError("no existe la consulta de métricas %s" % path)
        queries.append((spec["archivo"], fill_sql(path.read_text(encoding="utf-8"), package, {})))
    return queries


def project_root(folder):
    try:
        result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True,
                                text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return pathlib.Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return pathlib.Path.cwd()


def next_steps(folder, plan, flow=None):
    """(título, [pasos]) del paso que sigue según fases.json, plan.json y los archivos de la carpeta.

    Cada paso es un comando completo para la terminal (empieza con cd) o el texto para un chat nuevo. Es la única
    fuente de los comandos de entrega: los agentes la copian en vez de inventarlos.
    """
    folder = folder.resolve()
    root = project_root(folder).resolve()
    state = folder / "estado.md"
    try:  # cada comando empieza con cd a la raíz: dentro de ella, rutas relativas y más cortas
        folder = folder.relative_to(root)
    except ValueError:
        pass

    def command(*parts):
        return "cd %s && python3 -I %s %s" % (root, HERE / "perf.py", " ".join(str(part) for part in parts))

    def chat(text, model):
        return "Chat nuevo (%s): \"%s\"" % (model, text)

    flows = plan["flujos"]
    flow = flow if flow in flows else next(iter(flows))
    automatic = bool(startup_spec(flows[flow])) or flows[flow].get("recorrido", "manual") != "manual"
    runs = 10 if automatic else 5
    capture = ["capturar", "--plan", folder / "plan.json"] + (["--flujo", flow] if len(flows) > 1 else [])
    phases = read_phases(root / folder)
    mejoras = plan.get("mejoras", [])
    estados = [m.get("estado", "propuesta") for m in mejoras]
    session2 = chat("Sigue hb-performance con %s" % state, "intermedio, razonamiento alto")
    session4 = chat("Sigue hb-performance con %s" % state, "económico, razonamiento bajo")
    report = state.parent / ("reporte.html" if (state.parent / "reporte.html").is_file() else "reporte.md")
    if report.is_file():
        return "investigación cerrada", ["Reporte: %s" % report]
    if "despues" in phases:
        return "sesión 4 · cierre", [session4]
    if "aplicada" in estados and "aprobada" not in estados:
        install = plan.get("instalar")
        return "medición después (sin chat)", [
            "cd %s && %s" % (root, install) if install else
            "cd %s && <compila e instala el build de profiling (guarda el comando como 'instalar' en plan.json)>" % root,
            command(*(capture + ["--fase", "despues", "--corridas", runs])), session4]
    if "aprobada" in estados:
        first = next(m for m in mejoras if m.get("estado") == "aprobada")
        return "sesión 3 · %s" % first["id"], [
            chat("Sigue hb-performance con %s: sesión 3, aplica %s" % (state, first["id"]), "intermedio, razonamiento medio")]
    if "propuesta" in estados:
        ids = ",".join(m["id"] for m in mejoras if m.get("estado", "propuesta") == "propuesta")
        return "decisión del usuario (sin chat)", [
            command("decidir", "--carpeta", folder, "--aprobar", ids, "--descartar", "-", "--pendiente", "-")
            + "   # deja en cada lista los ids que correspondan; - es ninguno"]
    if mejoras:
        return "sesión 4 · cierre sin mejoras aplicadas", [session4]
    if (state.parent / "diagnostico.md").is_file():
        return "sesión 2 · diagnóstico", [session2]
    steps = []
    if "antes" not in phases:
        if not any((state.parent / "prueba").glob("*.perfetto-trace*")):
            steps.append(command(*(capture + ["--prueba"])))
        steps.append(command(*(capture + ["--fase", "antes", "--corridas", runs])))
    if "control" not in phases:
        steps.append(command(*(capture + ["--fase", "control", "--corridas", runs])))
    steps += [command("diagnostico", "--carpeta", folder), session2]
    return ("medición antes y control (sin chat)" if "antes" not in phases else
            "control y diagnóstico (sin chat)" if "control" not in phases else "diagnóstico (sin chat)"), steps


def write_next(folder, title, steps):
    """Reescribe "## Siguiente paso" de estado.md con lo que dice next_steps."""
    state = pathlib.Path(folder) / "estado.md"
    if not state.is_file():
        return
    body = "\n".join(["- **Paso:** %s" % title, "- **En orden, uno a la vez** (los comandos van en la terminal):"]
                     + ["  %d. %s" % (i, s if s.startswith("Chat nuevo") or s.startswith("Reporte") else "`%s`" % s)
                        for i, s in enumerate(steps, start=1)]
                     + ["- _Lo escribe `perf.py siguiente`: si algo cambió, vuelve a correrlo._", ""])
    text = state.read_text(encoding="utf-8")
    new, count = re.subn(r"(## Siguiente paso\n\n).*?(?=\n## )", lambda m: m.group(1) + body, text, count=1, flags=re.S)
    if count:
        state.write_text(new, encoding="utf-8")


def print_next(folder, plan, flow=None):
    title, steps = next_steps(pathlib.Path(folder), plan, flow)
    print("Siguiente · %s (también en estado.md):" % title)
    for i, step in enumerate(steps, start=1):
        print("  %d. %s" % (i, step))
    write_next(folder, title, steps)


def cmd_siguiente(args):
    folder = pathlib.Path(args.carpeta)
    print_next(folder, load_plan(folder / "plan.json"), args.flujo)


DECISIONS = (("aprobar", "aprobada", "aprobadas"), ("descartar", "descartada", "descartadas"),
             ("pendiente", "pendiente", "pendientes"), ("aplicada", "aplicada", "aplicadas"))


def cmd_decidir(args):
    folder = pathlib.Path(args.carpeta)
    plan_path = folder / "plan.json"
    plan = load_plan(plan_path)
    choices = {}
    for option, estado, _ in DECISIONS:
        for item in (getattr(args, option) or "").split(","):
            if item.strip() and item.strip() != "-":
                choices[item.strip()] = estado
    if not choices:
        raise PerfError("indica al menos una mejora con --aprobar, --descartar, --pendiente o --aplicada")
    known = [m["id"] for m in plan.get("mejoras", [])]
    unknown = sorted(set(choices) - set(known))
    if unknown:
        raise PerfError("plan.json no tiene las mejoras %s (tiene: %s)" % (", ".join(unknown), ", ".join(known) or "ninguna"))
    for item in plan["mejoras"]:
        if item["id"] in choices:
            item["estado"] = choices[item["id"]]
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    parts = ["%s %s" % (label, ", ".join(k for k in known if choices.get(k) == estado))
             for _, estado, label in DECISIONS if estado in choices.values()]
    line = "- %s: %s (perf.py decidir)" % (datetime.date.today().isoformat(), "; ".join(parts))
    state = folder / "estado.md"
    if state.is_file():
        text = state.read_text(encoding="utf-8")

        def append(match):
            body = re.sub(r"- <AAAA-MM-DD:[^\n]*>\n?", "", match.group(2)).strip("\n")
            return match.group(1) + (body + "\n" if body else "") + line + "\n"

        state.write_text(re.sub(r"(## Decisiones\n\n)(.*?)(?=\n## |\Z)", append, text, count=1, flags=re.S),
                         encoding="utf-8")
    rows = read_rows(folder / "metricas.csv") if (folder / "metricas.csv").is_file() else []
    update_block(folder, "mejoras", markdown_table(PLAN_HEADERS, plan_rows(plan, rows)))
    print("✔ %s" % line[2:])
    print_next(folder, plan)


def cmd_capturar(args):
    if args.plan:
        plan = load_plan(args.plan)
        folder = pathlib.Path(args.plan).parent
    elif args.prueba and args.paquete and args.carpeta:
        plan = {"paquete": args.paquete, "flujos": {args.flujo or "humo": {}}}
        folder = pathlib.Path(args.carpeta)
    else:
        raise PerfError("usa --plan <carpeta>/plan.json (o --prueba con --paquete y --carpeta)")
    flow_name = args.flujo or ("humo" if args.prueba and not args.plan else None)
    if flow_name is None and len(plan["flujos"]) == 1:
        flow_name = next(iter(plan["flujos"]))
    if flow_name not in plan["flujos"]:
        raise PerfError("el flujo '%s' no está en el plan (flujos: %s)" % (flow_name, ", ".join(plan["flujos"])))
    flow = plan["flujos"][flow_name]
    phase = "antes" if args.prueba else normalize_phase(args.fase)
    package = plan["paquete"]
    hz = args.hz or (plan.get("hz") if isinstance(plan.get("hz"), int) else None)
    startup = None if args.recorrido else startup_spec(flow)
    recorrido = args.recorrido or (flow.get("recorrido") if not startup else None) or "manual"
    tp = find_tp(args.tp)
    serial = select_device(args.serial or plan.get("serial"))
    adb = Adb(serial)
    sdk, warnings, build = preflight(adb, package, args.forzar)
    commit, dirty = git_info()
    if not args.prueba:
        warnings += check_build(folder, phase, build, commit, args.forzar)
    for warning in warnings:
        print("⚠ " + warning)
    folder.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(str(folder)).free / 1e9
    if free_gb < 3:
        print("⚠ quedan %.1f GB libres: cada traza puede pesar decenas o cientos de MB" % free_gb)
    config = resolve_config(plan, folder, args.config).read_text(encoding="utf-8").replace("{{PAQUETE}}", package)
    queries = [("metricas", fill_sql((ASSETS / "queries" / "metricas.sql").read_text(encoding="utf-8"), package, {}))]
    queries += custom_queries(flow, folder, package)
    csv_path = folder / "metricas.csv"
    out_dir = folder / ("prueba" if args.prueba else phase)
    out_dir.mkdir(parents=True, exist_ok=True)
    known = known_metrics(csv_path, flow_name)
    start_screen = None if startup else flow.get("inicio")

    def check_start():
        if not start_screen:
            return
        current = resumed_activity(adb)
        if start_screen in current:
            return
        if recorrido == "manual":
            wait_enter("⚠ la pantalla activa es '%s'; lleva la app a '%s' y presiona Enter " % (current or "?", start_screen))
            current = resumed_activity(adb)
            if start_screen in current:
                return
        raise Precondicion("la pantalla activa es '%s' y el flujo empieza en '%s'" % (current or "?", start_screen))

    compilation = "sin fijar (--sin-compilar)"
    if not args.sin_compilar:
        compilation = fix_compilation(adb, package, args.compilacion or plan.get("compilacion", "completa"))
    if args.rehacer and not args.prueba:
        discard_phase(folder, csv_path, phase, flow_name)
        known = known_metrics(csv_path, flow_name)
    warmups = 0 if args.prueba else args.calentamiento
    for i in range(warmups):
        if startup:
            adb.shell("am force-stop %s" % package)
            settle(1)
            reason, _ = launch(adb, package, startup)
        else:
            check_start()
            reason = drive(recorrido, "calentamiento %d/%d (no cuenta)" % (i + 1, warmups))
        if reason:
            print("⚠ calentamiento: %s" % reason)

    target = 1 if args.prueba else args.corridas
    valid, attempts, seen_hz = 0, 0, set()
    n = next_run_number(csv_path, phase, flow_name) if not args.prueba else 1
    while valid < target:
        if attempts >= target + 3:
            raise CorridasInsuficientes("solo %d de %d corridas válidas en %d intentos: revisa las condiciones"
                                        % (valid, target, attempts))
        attempts += 1
        check_start()
        if sdk < 31:
            adb.shell("dumpsys gfxinfo %s reset" % package)
        local = out_dir / ("%s_%d.perfetto-trace" % (flow_name, n))
        label = "prueba" if args.prueba else "corrida %d de %d (%s, %s)" % (valid + 1, target, flow_name, phase)
        reason, extra = record_run(adb, config, recorrido, label, local, startup, package)
        metrics, invalid, info, crash = [], reason, {}, []
        if not invalid and app_died(adb, package):
            invalid = "la app no estaba viva al terminar la corrida (¿se cayó?)"
            crash = crash_excerpt(adb, package)
        if not invalid:
            results = run_tp_batch(tp, local, queries)
            if not results["metricas"]:
                raise PerfError("trace_processor no devolvió las filas de metricas.sql")
            metrics, invalid, info = trace_metrics(trace_rows(*results["metricas"][-1]), hz, flow, known, sdk)
            names = {m[0] for m in metrics}
            metrics += [m for m in with_families(extra, flow.get("familias")) if m[0] not in names]
            for name, _ in queries[1:]:
                for header, body in results[name]:
                    metrics += sql_metrics(header, body, name)
            if info.get("hz_traza"):
                seen_hz.add(info["hz_traza"])
        if not invalid and sdk < 31:
            metrics += parse_gfxinfo(adb.shell("dumpsys gfxinfo %s" % package).stdout)
        if not invalid and args.memoria:
            metrics += parse_meminfo(adb.shell("dumpsys meminfo %s" % package).stdout)
        size_mb = local.stat().st_size / 1e6
        if crash:
            print("✖ La app se cayó durante la corrida. Inicio del crash (logcat -b crash):")
            print("\n".join("  " + line for line in crash))
            print("  " + mapping_hint())
        if invalid and args.prueba:
            names = sorted(info.get("nombres", {}).items(), key=lambda kv: -kv[1])[:15]
            print("Secciones propias: %s" % (", ".join("%s ×%d" % kv for kv in names) or "ninguna"))
            raise CorridasInsuficientes("la corrida de prueba fue inválida: %s (traza en %s)" % (invalid, local))
        if invalid:
            target_name = local.with_name("%s_%d_invalida_%s.perfetto-trace" % (flow_name, n, slug(invalid)))
            local.rename(target_name)
            if not args.sin_comprimir:
                compress(target_name)
            print("✖ corrida %d inválida: %s (traza guardada para auditoría)" % (n, invalid))
            n += 1
            continue
        saved = local if args.sin_comprimir else compress(local)
        if args.prueba:
            print(run_line("de prueba", size_mb, metrics))
            print(markdown_table(["Métrica", "Valor", "Familia"],
                                 [[m[0], fmt(m[1], m[2]), m[3]] for m in metrics[:MAX_ROWS]]))
            names = sorted(info["nombres"].items(), key=lambda kv: -kv[1])[:15]
            print("Secciones propias: %s" % (", ".join("%s ×%d" % kv for kv in names) or "ninguna"))
            print("Tasa de refresco: %s Hz (%s)" % (
                info["hz"], "plan" if hz else "traza" if info.get("hz_traza") else "60 por defecto"))
            if info.get("faltantes"):
                print("⚠ Métricas de usuario sin marcas en la traza: %s" % ", ".join(info["faltantes"]))
            if startup and "ttfd_ms" not in {m[0] for m in metrics}:
                print("⚠ Sin ttfd_ms: la app no llama a reportFullyDrawn() (ver setup.md · Contenido visible)")
            print("Traza: %s" % saved)
            if args.plan:
                print_next(folder, plan, flow_name)
            return
        append_rows(csv_path, [metric_row(phase, flow_name, n, m[0], m[1], m[2], m[3]) for m in metrics])
        known |= {m[0] for m in metrics}
        print(run_line("%d/%d" % (valid + 1, target), size_mb, metrics))
        if info.get("faltantes"):
            print("  ⚠ sin marcas para: %s" % ", ".join(info["faltantes"]))
        valid += 1
        n += 1
    if hz and seen_hz and any(abs(h - hz) > hz * 0.05 for h in seen_hz):
        print("⚠ La traza indica %s Hz y el plan dice %s: corrige 'hz' en plan.json (fija el presupuesto de frame)"
              % ("/".join(str(h) for h in sorted(seen_hz)), hz))
    elif not hz and len(seen_hz) > 1:
        print("⚠ La tasa de refresco cambió entre corridas (%s Hz): fíjala en el dispositivo o pon 'hz' en el plan"
              % "/".join(str(h) for h in sorted(seen_hz)))
    record = {"fecha": datetime.datetime.now().replace(microsecond=0).isoformat(), "commit": commit, "sucio": dirty,
              "corridas": valid, "hz": hz or min(seen_hz, default=None), "compilacion": compilation}
    record.update(build)
    write_phase(folder, phase, record)
    rows = read_rows(csv_path)
    table, hidden = summary_rows(rows, plan, phases=(phase,), flows=(flow_name,))
    print(markdown_table(SUMMARY_HEADERS, table[:MAX_ROWS]))
    write_summary(csv_path, rows, plan)
    print("✔ Listo. No hace falta pegar esta salida en el chat: quedó en metricas.csv, resumen.md y estado.md.")
    if args.plan:
        print_next(folder, plan, flow_name)


def write_summary(csv_path, rows, plan):
    full, _ = summary_rows(rows, plan, everything=True)
    pathlib.Path(csv_path).with_name("resumen.md").write_text(
        "# Resumen de métricas\n\n" + markdown_table(SUMMARY_HEADERS, full) + "\n", encoding="utf-8")
    compact, hidden = summary_rows(rows, plan)
    block = markdown_table(SUMMARY_HEADERS, compact[:MAX_ROWS])
    if hidden or len(compact) > MAX_ROWS:
        block += "\n\nDetalle completo en `resumen.md`."
    if update_block(pathlib.Path(csv_path).parent, "metricas", block):
        print("✔ estado.md actualizado (Métricas)")


# ── consulta y diagnostico ───────────────────────────────────────────────────

def parse_params(items):
    params = {}
    for item in items or []:
        if "=" not in item:
            raise PerfError("--param espera CLAVE=valor (recibí '%s')" % item)
        key, value = item.split("=", 1)
        params[key.strip().upper()] = value
    return params


def package_near(trace):
    for folder in list(pathlib.Path(trace).resolve().parents)[:3]:
        if (folder / "plan.json").is_file():
            try:
                return json.loads((folder / "plan.json").read_text(encoding="utf-8")).get("paquete")
            except ValueError:
                return None
    return None


def query_path(name):
    path = pathlib.Path(name)
    if not path.is_file():
        path = ASSETS / "queries" / "diagnostico" / name
    if not path.is_file() and not name.endswith(".sql"):
        path = ASSETS / "queries" / "diagnostico" / (name + ".sql")
    if not path.is_file():
        raise PerfError("no existe la consulta %s" % name)
    return path


def print_sets(sets, limit, width):
    for header, body in sets:
        rows = [[fmt_cell(c)[:width] for c in row] for row in body[:limit]]
        print(markdown_table(header, rows))
        if len(body) > limit:
            print("… %d filas más (sube --limite o filtra la consulta)" % (len(body) - limit))


def cmd_consulta(args):
    tp = find_tp(args.tp)
    if args.sql:
        sql = args.sql
    elif args.archivo:
        sql = query_path(args.archivo).read_text(encoding="utf-8")
    else:
        raise PerfError("pasa un archivo .sql (o el nombre de una consulta de la skill) o --sql")
    sql = fill_sql(sql, args.paquete or package_near(args.traza), parse_params(args.param))
    print_sets(run_tp(tp, args.traza, sql), args.limite, args.ancho)


DIAG_ORDER = ["arranque_hitos", "linea_hilo_principal", "hilo_principal_top", "estado_hilo_principal",
              "hijos_mas_largos", "dormido_en_frames_largos", "estado_primeros_frames", "frames_por_tramo",
              "cpu_por_tramo", "cpu_por_hilo", "contencion_locks", "binder_hilo_principal", "jank_por_tipo",
              "linea_de_tiempo", "llamadas_solapadas", "inflate_tras_http", "cpu_por_libreria"]


def query_catalog():
    """[(nombre, título, grupos, sql)] de assets/queries/diagnostico, en orden de lectura."""
    catalog = []
    paths = sorted((ASSETS / "queries" / "diagnostico").glob("*.sql"),
                   key=lambda p: (DIAG_ORDER.index(p.stem) if p.stem in DIAG_ORDER else len(DIAG_ORDER), p.stem))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = lines[0].lstrip("- ").strip() if lines else path.stem
        groups = next((line.split(":", 1)[1].split() for line in lines if line.startswith("-- grupos:")), ["base"])
        catalog.append((path.stem, title, groups, text))
    return catalog


def representative_runs(rows, plan, flow, phase):
    """(métrica, [(etiqueta, corrida, valor)]) con la corrida mediana y la peor de la primera principal."""
    for metric in (plan.get("principales") or []) + ["ttid_ms", "hilo_max_ms"]:
        values = [(r["corrida"], r["valor"], r["sentido"]) for r in rows
                  if r["flujo"] == flow and r["fase"] == phase and r["metrica"] == metric]
        if values:
            ordered = sorted(values, key=lambda v: v[1])
            median = ordered[(len(ordered) - 1) // 2]
            worst = ordered[-1] if values[0][2] == "menor" else ordered[0]
            runs = [("mediana", median[0], median[1])]
            if worst[0] != median[0]:
                runs.append(("peor", worst[0], worst[1]))
            return metric, runs
    raise PerfError("no hay corridas de la fase '%s' del flujo '%s' en metricas.csv" % (phase, flow))


def trace_of(folder, phase, flow, run):
    for name in ("%s_%s.perfetto-trace.gz" % (flow, run), "%s_%s.perfetto-trace" % (flow, run)):
        if (folder / phase / name).is_file():
            return folder / phase / name
    raise PerfError("no encuentro la traza de la corrida %s en %s" % (run, folder / phase))


def cmd_diagnostico(args):
    folder = pathlib.Path(args.carpeta)
    plan = load_plan(folder / "plan.json")
    flow_name = args.flujo or next(iter(plan["flujos"]))
    if flow_name not in plan["flujos"]:
        raise PerfError("el flujo '%s' no está en el plan" % flow_name)
    flow = plan["flujos"][flow_name]
    phase = normalize_phase(args.fase)
    rows = read_rows(folder / "metricas.csv")
    tp = find_tp(args.tp)
    metric, runs = representative_runs(rows, plan, flow_name, phase)
    if args.corrida:
        value = next((r["valor"] for r in rows if r["corrida"] == args.corrida and r["metrica"] == metric
                      and r["fase"] == phase and r["flujo"] == flow_name), None)
        runs = [("elegida", args.corrida, value)]
    flow_metrics = {r["metrica"] for r in rows if r["flujo"] == flow_name}
    startup = bool(startup_spec(flow)) or "ttid_ms" in flow_metrics
    network = any(r["metrica"] == "red_llamadas" and r["valor"] > 0 for r in rows if r["flujo"] == flow_name)
    groups = {"base", "cpu"} | ({"arranque"} if startup else set()) | ({"red"} if network else set())
    wanted = set(args.consultas.split(",")) if args.consultas else None
    params = {"TRAMO_MS": str(args.tramo_ms or (250 if startup else 500))}
    catalog = [q for q in query_catalog() if (q[0] in wanted if wanted else set(q[2]) & groups)]
    unit = next((r["unidad"] for r in rows if r["metrica"] == metric), "")
    md = ["# Diagnóstico · %s · %s" % (flow_name, phase), "",
          "_Corridas: %s. `t_ms` y `desde_ms`: ms desde que nace el proceso (arranque) o desde el inicio de la "
          "traza. Generado por hb-performance %s._" % (", ".join("%s = %s (%s %s)" % (label, run, metric, fmt(value, unit))
                                                                 for label, run, value in runs), VERSION)]
    printed, empty = [], []
    for index, (label, run, _) in enumerate(runs):
        chosen = [q for q in catalog if index == 0 or "peor" in q[2]]
        if not chosen:
            continue
        trace = trace_of(folder, phase, flow_name, run)
        results = run_tp_batch(tp, trace, [(q[0], fill_sql(q[3], plan["paquete"], params)) for q in chosen])
        if index:
            md += ["", "## Corrida %s (%s)" % (run, label)]
        for name, title, _, _ in chosen:
            sets = [s for s in results[name] if s[1]]
            if not sets:
                empty.append(name)
                continue
            md += ["", "%s %s · `%s`" % ("###" if index else "##", title.replace("{{TRAMO_MS}}", params["TRAMO_MS"]),
                                         name), ""]
            for header, body in sets:
                md.append(markdown_table(header, [[fmt_cell(c)[:args.ancho] for c in row] for row in body[:args.limite]]))
            printed.append("%s (%s)" % (name, label))
    if empty:
        md += ["", "_Sin filas: %s._" % ", ".join(sorted(set(empty)))]
    if "cpu_por_libreria" in empty:
        md += ["", "_Sin muestras de CPU: para atribuir el CPU a funciones, captura una corrida con "
                   "`capturar --prueba --config cpu` y consulta `cpu_por_libreria` sobre esa traza._"]
    target = folder / ("diagnostico.md" if phase == "antes" else "diagnostico-%s.md" % phase)
    target.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("✔ %s: %d tablas de %s (%s)." % (target, len(printed), ", ".join("corrida %s" % r[1] for r in runs),
                                          ", ".join(sorted(groups - {"cpu"}))))
    print_next(folder, plan, flow_name)


# ── resumen y comparar ───────────────────────────────────────────────────────

def cmd_resumen(args):
    rows = read_rows(args.csv)
    plan = load_plan_beside(args.csv)
    table, hidden = summary_rows(rows, plan, everything=args.todo)
    print(markdown_table(SUMMARY_HEADERS, table[:MAX_ROWS] if not args.todo else table))
    if hidden or (not args.todo and len(table) > MAX_ROWS):
        print("… %d métricas más en resumen.md (o usa --todo)" % (hidden + max(0, len(table) - MAX_ROWS)))
    flagged = [r for r in table if r[-1] != "—"]
    if flagged:
        print("⚠ %d con avisos: con 'pocas corridas' suma corridas; con 'inestable' (CV > %s %%) estabiliza las "
              "condiciones antes de comparar." % (len(flagged), fmt(CV_MAX)))
    write_summary(args.csv, rows, plan)


def jit_note(rows):
    """Aviso si una fase compiló con JIT mucho más que la otra: la compilación de ART no fue la misma."""
    notes = []
    for (flow, metric), entry in group(rows).items():
        phases = entry["fases"]
        if metric != "jit_ms" or "antes" not in phases or "despues" not in phases:
            continue
        before, after = statistics.median(phases["antes"]), statistics.median(phases["despues"])
        if abs(after - before) > max(50.0, 2 * min(before, after)):
            notes.append("%s: JIT de %s ms en antes y %s ms en después: la compilación de ART no fue la misma y los "
                         "tiempos no son comparables; repite las fases con --rehacer" % (flow, fmt(before), fmt(after)))
    return notes


def builds_table(folder):
    phases = read_phases(folder)
    if not phases:
        return "", []
    table = markdown_table(["Fase", "Fecha", "Commit", "Versión", "Instalada", "Hz", "Compilación", "Corridas"], [
        [p, phases[p].get("fecha", "—"),
         (phases[p].get("commit") or "—") + (" (con cambios)" if phases[p].get("sucio") else ""),
         phases[p].get("version", "—"), phases[p].get("instalada") or "—", phases[p].get("hz") or "—",
         phases[p].get("compilacion") or "—", phases[p].get("corridas", "—")] for p in FASES if p in phases])
    notes = []
    before, after = phases.get("antes"), phases.get("despues")
    if before and after and before.get("instalada") and before.get("instalada") == after.get("instalada"):
        notes.append("antes y después midieron el mismo build instalado: la comparación no prueba la mejora")
    if before and after and before.get("hz") and after.get("hz") and before["hz"] != after["hz"]:
        notes.append("antes y después se midieron a distinta tasa de refresco (%s y %s Hz)" % (before["hz"], after["hz"]))
    if before and after and before.get("compilacion") != after.get("compilacion"):
        notes.append("antes y después se midieron con distinta compilación de ART (%s · %s): los tiempos no son "
                     "comparables; repite las fases con --rehacer" % (before.get("compilacion") or "sin registrar",
                                                                      after.get("compilacion") or "sin registrar"))
    return table, notes


def logrado_rows(plan, results):
    by_metric = {(r["flujo"], r["metrica"]): r for r in results}
    default_flow = next(iter(plan.get("flujos") or {"": None}))
    out = []
    for item in plan.get("mejoras", []):
        r = by_metric.get((item.get("flujo") or default_flow, item.get("metrica")))
        unit = r["unidad"] if r else ""
        out.append([item["id"], item["titulo"], item.get("metrica", "—"),
                    fmt(r["antes"]["mediana"], unit) if r else "—", item.get("esperado", "—"),
                    fmt(r["despues"]["mediana"], unit) if r else "—", fmt_pct(r["delta_pct"]) if r else "—",
                    r["veredicto"] if r else "—", item.get("estado", "—")])
    return out


LOGRADO_HEADERS = ["#", "Mejora", "Métrica", "Antes", "Esperado", "Después", "Δ %", "Veredicto", "Estado"]


def cmd_comparar(args):
    rows = read_rows(args.csv)
    plan = load_plan_beside(args.csv)
    results, unmatched = compare(rows)
    chosen = compact_compare(results, plan, everything=args.todo)
    table = markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen[:None if args.todo else MAX_ROWS]])
    print(table)
    counts = {}
    for r in results:
        counts[r["veredicto"]] = counts.get(r["veredicto"], 0) + 1
    print("Veredictos: %s" % (", ".join("%s %d" % kv for kv in sorted(counts.items())) or "ninguno"))
    if any(r["familia"] == "e2e" for r in chosen):
        print("e2e = depende del backend: con pocas corridas, tómalo como orientativo.")
    if counts.get("no comparable"):
        print("no comparable = la cantidad de frames cambió más de %d %%: los porcentajes y percentiles de frame "
              "miden otra cosa." % (FRAMES_CHANGE_MAX * 100))
    if len(chosen) < len(results):
        print("… %d métricas sin cambios relevantes en comparacion.md" % (len(results) - len(chosen)))
    for u in unmatched[:5]:
        print("⚠ Sin comparar: %s · %s (solo en: %s)" % (u["flujo"], u["metrica"], ", ".join(u["fases"])))
    regressions = [r for r in results if r["veredicto"] == "regresión"]
    if regressions:
        print("✖ %d regresiones: repórtalas aunque no sean métricas principales." % len(regressions))
    folder = pathlib.Path(args.csv).parent
    builds, notes = builds_table(folder)
    notes += jit_note(rows)
    for note in notes:
        print("⚠ " + note)
    text = "# Comparación\n\n" + markdown_table(
        COMPARE_HEADERS, [compare_cells(r) for r in compact_compare(results, plan, everything=True)]) + "\n"
    if builds:
        text += "\n## Builds medidos\n\n" + builds + "\n"
    (folder / "comparacion.md").write_text(text, encoding="utf-8")
    if update_block(folder, "comparacion", markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen[:MAX_ROWS]])):
        print("✔ estado.md actualizado (Comparación)")
    if plan.get("mejoras") and update_block(folder, "mejoras", markdown_table(LOGRADO_HEADERS, logrado_rows(plan, results))):
        print("✔ estado.md actualizado (Plan de mejoras: propuesto contra logrado)")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({"resultados": results, "sin_comparar": unmatched},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")


# ── har ──────────────────────────────────────────────────────────────────────

def parse_time(text):
    match = ISO.match((text or "").strip())
    if not match:
        return None
    base, fraction, zone = match.groups()
    micro = int(((fraction or ".0")[1:] + "000000")[:6])
    stamp = datetime.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(microsecond=micro)
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        stamp -= sign * datetime.timedelta(hours=int(zone[1:3]), minutes=int(zone[-2:]))
    return stamp


def har_endpoint(method, url):
    parts = urlsplit(url)
    segments = ["{id}" if ID_SEGMENT.match(s) else s for s in parts.path.split("/")]
    return "%s %s%s" % (method.upper(), parts.netloc, "/".join(segments) or "/")


def har_sections(entries):
    """Convierte las entradas de un HAR en secciones HTTP (tipo, ts, dur, prof, nombre), en nanosegundos."""
    sections, complete = [], True
    for item in entries:
        request = item.get("request") or {}
        name = "HTTP " + har_endpoint(request.get("method") or "GET", request.get("url") or "")
        stamp = parse_time(item.get("startedDateTime"))
        elapsed = item.get("time")
        if stamp is None:
            complete = False
        ts = int((stamp - datetime.datetime(1970, 1, 1)).total_seconds() * 1e9) if stamp else len(sections)
        dur = int(float(elapsed) * 1e6) if isinstance(elapsed, (int, float)) and elapsed >= 0 else -1
        sections.append(("seccion", ts, dur, 0, name))
    return sections, complete


def cmd_har(args):
    phase = normalize_phase(args.fase)
    csv_path = pathlib.Path(args.csv)
    existing = read_rows(csv_path) if csv_path.is_file() else []
    known = {r["metrica"] for r in existing if r["flujo"] == args.flujo}
    runs = []
    for index, name in enumerate(args.har, start=1):
        path = pathlib.Path(name)
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))["log"]["entries"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise PerfError("%s no es un HAR válido: %s" % (path, error))
        run = path.parent.name if path.parent.name.isdigit() else str(index)
        runs.append((run, har_sections(entries)))
    if len({run for run, _ in runs}) != len(runs):
        raise PerfError("hay rondas repetidas: pasa un HAR por ronda")
    taken = {(r["fase"], r["corrida"]) for r in existing if r["flujo"] == args.flujo}
    for run, _ in runs:
        if (phase, run) in taken:
            raise PerfError("ya hay filas de la fase '%s', flujo '%s' y corrida %s en %s: bórralas antes de volver "
                            "a importar" % (phase, args.flujo, run, csv_path))
    endpoints = {m[4:-9] for m in known if m.startswith("red ") and m.endswith(" llamadas")}
    for _, (sections, _) in runs:
        endpoints |= {endpoint_of(s[4]) for s in sections}
    new_rows, incomplete = [], False
    for run, (sections, complete) in sorted(runs, key=lambda r: (len(r[0]), r[0])):
        metrics = network_metrics(sections, endpoints, force=True)
        if not complete:
            incomplete = True
            metrics = [m for m in metrics if m[0] not in ("red_solapadas", "red_repetidas_2s")]
        new_rows += [metric_row(phase, args.flujo, run, m[0], m[1], m[2], m[3]) for m in metrics]
    append_rows(csv_path, new_rows)
    print("✔ %d filas agregadas a %s (%d rondas, %d endpoints)" % (len(new_rows), csv_path, len(runs), len(endpoints)))
    if incomplete:
        print("⚠ Algún HAR no trae startedDateTime en todas las llamadas: no se calcularon solapadas ni repetidas.")


# ── reporte ──────────────────────────────────────────────────────────────────

def state_sections(text):
    """{título en minúsculas: contenido} de los ## de estado.md, sin los bloques que escribe el script."""
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "Rendimiento")
    sections, current, buffer = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current, buffer = line[3:].strip().lower(), []
        elif current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    clean = {k: re.sub(r"<!-- /?perf:\w+ -->", "", v).strip() for k, v in sections.items()}
    return title, clean


def ficha_subset(text):
    """Solo las filas de la Ficha que sirven al lector del reporte (sin datos de prueba ni precondiciones)."""
    out, in_table = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            in_table = True
            first = line.strip().strip("|").split("|")[0].strip().lower()
            if first in ("campo", "") or re.fullmatch(r":?-{3,}:?", first) or first.startswith(FICHA_REPORTE):
                out.append(line)
        elif in_table:
            break
    return "\n".join(out) if len(out) > 2 else ""


def inline_md(text):
    text = e(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)


def md_to_html(text):
    """Markdown mínimo: títulos, párrafos, listas, tablas y bloques de código."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % e("\n".join(block)))
        elif line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")) + 2, 6)
            out.append("<h%d>%s</h%d>" % (level, inline_md(line.lstrip("#").strip()), level))
            i += 1
        elif line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                    rows.append([c.replace("\\|", "|") for c in cells])
                i += 1
            head = "".join("<th>%s</th>" % inline_md(c) for c in rows[0]) if rows else ""
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline_md(c) for c in r) for r in rows[1:])
            out.append('<div class="table-wrap"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                       % (head, body))
        elif re.match(r"\s*([-*]|\d+\.)\s", line):
            ordered = bool(re.match(r"\s*\d+\.", line))
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.)\s", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline_md(it) for it in items), tag))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"\s*(#|\||```|[-*]\s|\d+\.\s)", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>%s</p>" % inline_md(" ".join(para)))
    return "\n".join(out)


def bars_svg(result):
    unit, before, after = result["unidad"], result["antes"]["mediana"], result["despues"]["mediana"]
    top = max(abs(before), abs(after)) or 1
    width, label_w, rows = 360, 70, []
    for i, (label, value, css) in enumerate((("Antes", before, "bar-before"), ("Después", after, "bar-after"))):
        y = 6 + i * 26
        w = max(2, abs(value) / top * (width - label_w - 90))
        rows.append('<text x="0" y="%d" class="bar-label">%s</text>' % (y + 14, label))
        rows.append('<rect x="%d" y="%d" width="%.1f" height="18" rx="3" class="%s"/>' % (label_w, y, w, css))
        rows.append('<text x="%.1f" y="%d" class="bar-value">%s</text>' % (label_w + w + 6, y + 14, e(fmt(value, unit))))
    return ('<svg viewBox="0 0 %d 60" role="img" aria-label="%s: antes %s, después %s">%s</svg>'
            % (width, e(result["metrica"]), e(fmt(before, unit)), e(fmt(after, unit)), "".join(rows)))


def initial_md(rows, plan):
    """Estado inicial de las métricas principales (antes y, si existe, el ruido del bloque de control)."""
    principales = plan.get("principales") or []
    table = []
    for (flow, metric), entry in sorted(group(rows).items(), key=lambda kv: (kv[0][0], priority(kv[0][1], plan))):
        if metric not in principales or "antes" not in entry["fases"]:
            continue
        s = describe(entry["fases"]["antes"])
        control = entry["fases"].get("control")
        noise = abs(statistics.median(control) - s["mediana"]) / abs(s["mediana"]) * 100 \
            if control and s["mediana"] else None
        table.append([flow, metric, entry["familia"], fmt(s["mediana"], entry["unidad"]), fmt(s["p90"], entry["unidad"]),
                      "%s – %s" % (fmt(s["min"]), fmt(s["max"])), s["n"], fmt_pct(noise, signed=False),
                      ", ".join(s["avisos"]) or "—"])
    if not table:
        return ""
    return markdown_table(["Flujo", "Métrica", "Familia", "Mediana", "P90", "Mín – máx", "n", "Ruido (A/A)", "Avisos"],
                          table)


def plan_rows(plan, rows):
    medians = {(k[0], k[1]): (statistics.median(v["fases"]["antes"]), v["unidad"])
               for k, v in group(rows).items() if "antes" in v["fases"]}
    default_flow = next(iter(plan.get("flujos") or {"": None}))
    out = []
    for item in plan.get("mejoras", []):
        before = medians.get((item.get("flujo") or default_flow, item.get("metrica")))
        out.append([item["id"], item["titulo"], item.get("hallazgo", "—"), item.get("metrica", "—"),
                    fmt(before[0], before[1]) if before else "—", item.get("esperado", "—"),
                    item.get("prioridad", "—"), item.get("esfuerzo", "—"), item.get("riesgo", "—"),
                    item.get("estado", "propuesta")])
    return out


PLAN_HEADERS = ["#", "Mejora", "Hallazgo", "Métrica", "Antes", "Esperado", "Prioridad", "Esfuerzo", "Riesgo", "Estado"]


def render_report(folder, name, title, subtitle, parts, charts=""):
    md = "# %s\n\n_%s_\n" % (title, subtitle)
    md += "".join("\n## %s\n\n%s\n" % (section, body) for section, body in parts if body)
    (folder / ("%s.md" % name)).write_text(md, encoding="utf-8")
    body = ""
    for section, content in parts:
        if not content:
            continue
        extra = '<div class="charts">%s</div>' % charts if section == "Métricas principales" and charts else ""
        body += "<section><h2>%s</h2>%s%s</section>" % (e(section), extra, md_to_html(content))
    body = re.sub(r"<td>(mejora|regresión|sin cambio|dentro del ruido|informativa|no comparable)( \(backend\))?</td>",
                  lambda m: '<td><span class="verdict %s">%s</span>%s</td>' % (
                      VERDICT_CLASS[m.group(1)], m.group(1), m.group(2) or ""), body)
    page = (ASSETS / "plantillas" / "reporte.html").read_text(encoding="utf-8")
    return page.replace("{{TITLE}}", e(title)).replace("{{SUBTITLE}}", e(subtitle)).replace("{{BODY}}", body)


def cmd_reporte(args):
    folder = pathlib.Path(args.carpeta)
    state_path, csv_path = folder / "estado.md", folder / "metricas.csv"
    if not state_path.is_file():
        raise PerfError("no existe %s" % state_path)
    title, sections = state_sections(state_path.read_text(encoding="utf-8"))
    plan = load_plan(folder / "plan.json") if (folder / "plan.json").is_file() else {}
    rows = read_rows(csv_path) if csv_path.is_file() else []
    date = datetime.date.today().isoformat()

    def pick(*names):
        return next((sections[k] for k in sections for n in names if k.startswith(n)), "")

    if args.inicial:
        plan_md = markdown_table(PLAN_HEADERS, plan_rows(plan, rows)) if plan.get("mejoras") else ""
        if plan_md and update_block(folder, "mejoras", plan_md):
            print("✔ estado.md actualizado (Plan de mejoras)")
        parts = [("Resumen", pick("resumen ejecutivo", "resumen")), ("Estado inicial", initial_md(rows, plan)),
                 ("Hallazgos", pick("hallazgos")), ("Plan de mejoras", plan_md),
                 ("Ficha y condiciones", ficha_subset(pick("ficha"))), ("Pendientes", pick("pendientes"))]
        subtitle = "Reporte inicial · %s · hb-performance %s · e2e = depende del backend" % (date, VERSION)
        page = render_report(folder, "reporte-inicial", title, subtitle, parts)
        print("✔ Reporte inicial: %s" % (folder / "reporte-inicial.md"))
        if args.html:
            (folder / "reporte-inicial.html").write_text(page, encoding="utf-8")
            print("✔ Reporte HTML: %s" % (folder / "reporte-inicial.html"))
        if not plan.get("mejoras"):
            print("⚠ plan.json no tiene 'mejoras': el reporte sale sin el plan de mejoras.")
        if plan:
            print_next(folder, plan)
        return

    results, unmatched = compare(rows)
    principales = plan.get("principales") or []
    primary = sorted([r for r in results if r["metrica"] in principales], key=lambda r: priority(r["metrica"], plan))
    missing = [m for m in principales if m not in {r["metrica"] for r in results}]
    chosen = compact_compare(results, plan)
    primary_md = markdown_table(["Flujo", "Métrica", "Antes", "Después", "Δ %", "Veredicto"], [
        [r["flujo"], r["metrica"], fmt(r["antes"]["mediana"], r["unidad"]), fmt(r["despues"]["mediana"], r["unidad"]),
         fmt_pct(r["delta_pct"]), r["veredicto"] + (" (backend)" if r["familia"] == "e2e" else "")] for r in primary]
    ) if primary else ""
    logrado_md = markdown_table(LOGRADO_HEADERS, logrado_rows(plan, results)) if plan.get("mejoras") else ""
    comparison_md = markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen]) if chosen else \
        "No hay métricas con antes y después."
    parts = [("Resumen ejecutivo", pick("resumen ejecutivo")), ("Métricas principales", primary_md),
             ("Propuesto contra logrado", logrado_md), ("Hallazgos", pick("hallazgos")),
             ("Mejoras aplicadas", pick("mejoras aplicadas")),
             ("Lectura de la comparación", pick("lectura de la comparación", "lectura de la comparacion")),
             ("Comparación", comparison_md), ("Ficha y condiciones", ficha_subset(pick("ficha"))),
             ("Pendientes", pick("pendientes"))]
    charts = "".join('<figure class="chart"><figcaption>%s · %s</figcaption>%s</figure>'
                     % (e(r["metrica"]), e(r["flujo"]), bars_svg(r)) for r in primary)
    subtitle = "%s · hb-performance %s · e2e = depende del backend" % (date, VERSION)
    page = render_report(folder, "reporte", title, subtitle, parts, charts)
    print("✔ Reporte: %s" % (folder / "reporte.md"))
    if args.html:
        (folder / "reporte.html").write_text(page, encoding="utf-8")
        print("✔ Reporte HTML: %s" % (folder / "reporte.html"))
    for m in missing:
        print("⚠ La métrica principal '%s' no tiene antes y después en el CSV." % m)
    if unmatched:
        print("⚠ %d métricas sin las dos fases (ver comparacion.md)." % len(unmatched))
    if plan:
        print_next(folder, plan)


# ── nuevo ────────────────────────────────────────────────────────────────────

STARTUP_FAMILIES = {"jank_app_pct": "info", "frame_p50_ms": "info", "frame_p90_ms": "info", "frame_p99_ms": "info"}


def device_summary(serial, package, need_activity):
    """(texto del dispositivo, actividad de inicio) si hay un dispositivo; ('', '') si no, con el motivo."""
    try:
        adb = Adb(select_device(serial))
    except PerfError as error:
        print("⚠ Sin dispositivo para completar la ficha y la actividad de inicio: %s" % error)
        return "", ""
    model = adb.shell("getprop ro.product.model").stdout.strip()
    release = adb.shell("getprop ro.build.version.release").stdout.strip()
    sdk = adb.shell("getprop ro.build.version.sdk").stdout.strip()
    activity = launcher_activity(adb, package) if need_activity else ""
    return "%s · Android %s (API %s)" % (model or "?", release or "?", sdk or "?"), activity


def cmd_nuevo(args):
    folder = pathlib.Path(args.carpeta)
    if (folder / "plan.json").exists() or (folder / "estado.md").exists():
        raise PerfError("%s ya tiene una investigación: usa otra carpeta" % folder)
    if not re.fullmatch(r"[A-Za-z]\w*(\.[A-Za-z]\w*)+", args.paquete):
        raise PerfError("paquete '%s' no válido: usa el applicationId instalado" % args.paquete)
    startup = args.receta == "arranque-frio"
    device, activity = device_summary(args.serial, args.paquete, startup and not args.actividad)
    activity = args.actividad or activity
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "logs").mkdir(exist_ok=True)
    plan = {"paquete": args.paquete}
    if args.serial:
        plan["serial"] = args.serial
    if args.hz:
        plan["hz"] = args.hz
    plan["config"] = "base"
    plan["compilacion"] = "completa"
    if args.instalar:
        plan["instalar"] = args.instalar
    if startup:
        families = dict(STARTUP_FAMILIES)
        if args.red:
            families["ttfd_ms"] = "e2e"
        flow = {"pasos": ["perf.py detiene la app (am force-stop), inicia la traza y la abre con am start -W",
                          "Espera %s s con la primera pantalla y su contenido cargados" % fmt(args.espera)],
                "recorrido": {"tipo": "arranque-frio", "actividad": activity, "espera_s": args.espera},
                "invalidar_si": [], "familias": families}
        if not activity:
            print("⚠ No encontré la actividad de inicio (¿sin dispositivo?): completa recorrido.actividad en plan.json")
        plan.update({"principales": ["ttid_ms", "ttfd_ms", "hilo_max_ms"], "flujos": {"arranque-frio": flow},
                     "mejoras": []})
        scope = args.alcance or "arranque en frío hasta el contenido visible"
    else:
        plan.update({"principales": [], "flujos": {args.flujo: {
            "pasos": ["<paso exacto 1 en el dispositivo>"], "inicio": "<parte del nombre de la actividad>",
            "invalidar_si": [], "recorrido": "manual", "metricas_usuario": []}}, "mejoras": []})
        scope = args.alcance or "<alcance>"
    (folder / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = (ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8")
    state = state.replace("{{ALCANCE}}", scope).replace("{{FECHA}}", datetime.date.today().isoformat()) \
        .replace("{{PAQUETE}}", args.paquete).replace("{{DISPOSITIVO}}", device or "<modelo · Android · Hz>")
    (folder / "estado.md").write_text(state, encoding="utf-8")
    print("✔ %s y %s" % (folder / "plan.json", folder / "estado.md"))
    try:
        ignored = subprocess.run(["git", "check-ignore", "-q", str(folder)], capture_output=True, timeout=30)
        if ignored.returncode == 1:
            print("⚠ git no ignora %s: agrégala a .gitignore (o a .git/info/exclude) antes de capturar" % folder)
    except (OSError, subprocess.SubprocessError):
        pass
    if startup:
        print_next(folder, plan)
    else:
        print("Siguiente: la sesión 1 completa los pasos, las marcas y las métricas principales del plan; al terminar, "
              "perf.py siguiente da los comandos para medir.")


# ── instrumentar ─────────────────────────────────────────────────────────────

NETWORK_BLOCK = re.compile(r"[ \t]*// hb-perf:red>\n(.*?)[ \t]*// <hb-perf:red\n", re.S)


def detect(module, words):
    texts = []
    for candidate in (module / "build.gradle.kts", module / "build.gradle", module.parent / "gradle" / "libs.versions.toml",
                      module.parent.parent / "gradle" / "libs.versions.toml"):
        if candidate.is_file():
            texts.append(candidate.read_text(encoding="utf-8", errors="ignore").lower())
    return any(w in t for t in texts for w in words)


def choose(flag, detected):
    return detected if flag is None else flag


def render_template(text, package, network):
    """Quita los bloques de red si no hay red (o solo sus marcas si la hay) y pone el paquete."""
    text = NETWORK_BLOCK.sub(lambda m: m.group(1) if network else "", text)
    return re.sub(r"\n{3,}", "\n\n", text.replace("{{PAQUETE}}", package))


def cmd_instrumentar(args):
    module = pathlib.Path(args.modulo)
    if not (module / "build.gradle.kts").is_file() and not (module / "build.gradle").is_file():
        raise PerfError("%s no parece un módulo Gradle (falta build.gradle o build.gradle.kts)" % module)
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", args.paquete):
        raise PerfError("paquete '%s' no válido: usa algo como com.ejemplo.app.perf" % args.paquete)
    network = choose(args.red, detect(module, ["okhttp", "retrofit"]))
    retrofit = network and choose(args.retrofit, detect(module, ["retrofit"]))
    fragments = choose(args.fragments, detect(module, ["fragment", "appcompat"]))
    templates = ASSETS / "instrumentacion"
    files = [("SectionTracer.kt", "SectionTracer.kt"), ("NavigationTrace.kt", "NavigationTrace.kt"),
             ("ScreenTraceCallbacks.fragments.kt" if fragments else "ScreenTraceCallbacks.activities.kt",
              "ScreenTraceCallbacks.kt"), ("PerfInstaller.kt", "PerfInstaller.kt")]
    tests = [("SectionTracerTest.kt", "SectionTracerTest.kt")]
    if network:
        files += [("HttpSectionName.retrofit.kt" if retrofit else "HttpSectionName.okhttp.kt", "HttpSectionName.kt"),
                  ("TraceEventListener.kt", "TraceEventListener.kt")]
        tests += [("TraceEventListenerTest.kt", "TraceEventListenerTest.kt")]
    package_path = pathlib.Path(*args.paquete.split("."))
    plan = [(templates / src, module / args.fuente / package_path / dst) for src, dst in files]
    if not args.sin_tests:
        plan += [(templates / "test" / src, module / args.tests / package_path / dst) for src, dst in tests]
    for source, target in plan:
        if target.exists():
            print("= ya existe, no se toca: %s" % target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_template(source.read_text(encoding="utf-8"), args.paquete, network), encoding="utf-8")
        print("+ %s" % target)
    print("Red: %s · Retrofit: %s · Fragments: %s" % (
        "sí" if network else "no", "sí" if retrofit else "no", "sí" if fragments else "no"))
    print("Falta el cableado (references/setup.md): source set '%s' en debug y profiling, PerfInstaller en los "
          "manifests de debug y profiling%s, reportFullyDrawn en la primera pantalla y el DoD." % (
              args.fuente, ", TraceEventListener.FACTORY en cada OkHttpClient" if network else ""))


# ── Entrada ──────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="Captura, métricas, diagnóstico, comparación y reporte de hb-performance.")
    parser.add_argument("--version", action="version", version="hb-performance %s" % VERSION)
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("nuevo", help="crea la carpeta de una investigación con plan.json y estado.md")
    p.add_argument("--carpeta", required=True, help="por ejemplo reports/perf/arranque-frio/AAAA-MM-DD")
    p.add_argument("--paquete", required=True, help="applicationId instalado")
    p.add_argument("--receta", choices=["arranque-frio", "flujo"], default="flujo")
    p.add_argument("--flujo", default="flujo", help="nombre del flujo (receta flujo)")
    p.add_argument("--alcance", help="texto del alcance para el título de estado.md")
    p.add_argument("--actividad", help="actividad de inicio (paquete/.Actividad); si no, la del launcher")
    p.add_argument("--espera", type=float, default=5, help="segundos de espera tras el arranque (receta arranque-frio)")
    p.add_argument("--red", action="store_true", help="la primera pantalla carga datos de la red: ttfd_ms pasa a e2e")
    p.add_argument("--hz", type=int, help="tasa de refresco fija del dispositivo (si no, se lee de cada traza)")
    p.add_argument("--serial", help="dispositivo de medición; queda en el plan y lo usan todas las capturas")
    p.add_argument("--instalar", help="comando que compila e instala el build de profiling (queda en el plan)")
    p.set_defaults(func=cmd_nuevo)

    p = sub.add_parser("siguiente", help="el paso que sigue, con sus comandos completos (también en estado.md)")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--flujo")
    p.set_defaults(func=cmd_siguiente)

    p = sub.add_parser("decidir", help="registra la decisión del usuario sobre las mejoras del plan")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--aprobar", help="ids separados por coma (- es ninguno)")
    p.add_argument("--descartar", help="ids separados por coma (- es ninguno)")
    p.add_argument("--pendiente", help="ids separados por coma (- es ninguno)")
    p.add_argument("--aplicada", help="ids que la sesión 3 ya aplicó (la usa el agente al terminar la mejora)")
    p.set_defaults(func=cmd_decidir)

    p = sub.add_parser("capturar", help="calentamiento, compilación y N corridas con traza, consultas y CSV")
    p.add_argument("--plan", help="<carpeta>/plan.json")
    p.add_argument("--flujo", help="obligatorio si el plan tiene más de un flujo")
    p.add_argument("--fase", help="antes, control o despues")
    p.add_argument("--corridas", type=int, default=MIN_RUNS)
    p.add_argument("--calentamiento", type=int, default=1)
    p.add_argument("--recorrido", help="'manual' (Enter entre corridas) o un comando que recorre el flujo (testigo)")
    p.add_argument("--config", help="configuración de Perfetto para esta captura (base, completa, cpu o una ruta)")
    p.add_argument("--serial")
    p.add_argument("--tp", help="ruta de trace_processor")
    p.add_argument("--hz", type=int, help="tasa de refresco del dispositivo (si no, la del plan o la de la traza)")
    p.add_argument("--memoria", action="store_true", help="agrega dumpsys meminfo después de cada corrida")
    p.add_argument("--sin-compilar", action="store_true", help="no fija la compilación de ART")
    p.add_argument("--sin-comprimir", action="store_true", help="deja las trazas sin gzip")
    p.add_argument("--prueba", action="store_true", help="una corrida que imprime las métricas y no escribe el CSV")
    p.add_argument("--forzar", action="store_true", help="sigue aunque el dispositivo esté caliente o el build no cambie")
    p.add_argument("--rehacer", action="store_true", help="descarta lo medido en esta fase y la mide de nuevo")
    p.add_argument("--compilacion", choices=COMPILATIONS,
                   help="completa (por defecto: todo compilado, para comparar cambios de código) o perfil (Baseline "
                        "Profile + speed-profile); si no, la del plan")
    p.add_argument("--paquete", help="con --prueba y sin plan")
    p.add_argument("--carpeta", help="con --prueba y sin plan")
    p.set_defaults(func=cmd_capturar)

    p = sub.add_parser("diagnostico", help="consultas de diagnóstico sobre la corrida mediana y la peor")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--flujo")
    p.add_argument("--fase", default="antes")
    p.add_argument("--corrida", help="una corrida concreta en vez de la mediana y la peor")
    p.add_argument("--consultas", help="solo estas consultas, separadas por coma")
    p.add_argument("--tramo-ms", type=int, help="ancho de los tramos (250 en arranque, 500 en flujos)")
    p.add_argument("--limite", type=int, default=25)
    p.add_argument("--ancho", type=int, default=80)
    p.add_argument("--tp")
    p.set_defaults(func=cmd_diagnostico)

    p = sub.add_parser("consulta", help="consulta SQL acotada sobre una traza")
    p.add_argument("traza")
    p.add_argument("archivo", nargs="?", help="archivo .sql (o el nombre de una consulta de assets/queries/diagnostico)")
    p.add_argument("--sql")
    p.add_argument("--paquete", help="si no, el del plan.json junto a la traza")
    p.add_argument("--param", action="append", help="CLAVE=valor para {{CLAVE}} en la consulta (repetible)")
    p.add_argument("--limite", type=int, default=20)
    p.add_argument("--ancho", type=int, default=80)
    p.add_argument("--tp")
    p.set_defaults(func=cmd_consulta)

    p = sub.add_parser("resumen", help="estadísticas por fase y avisos")
    p.add_argument("csv")
    p.add_argument("--todo", action="store_true", help="todas las métricas, no solo las principales")
    p.set_defaults(func=cmd_resumen)

    p = sub.add_parser("comparar", help="antes contra después, con veredicto")
    p.add_argument("csv")
    p.add_argument("--todo", action="store_true")
    p.add_argument("--json", help="guarda también los resultados en JSON")
    p.set_defaults(func=cmd_comparar)

    p = sub.add_parser("har", help="agrega al CSV las métricas de red de uno o más HAR (una ronda cada uno)")
    p.add_argument("--fase", required=True)
    p.add_argument("--flujo", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("har", nargs="+")
    p.set_defaults(func=cmd_har)

    p = sub.add_parser("reporte", help="reporte inicial (--inicial) o final, en markdown y, con --html, en HTML")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--inicial", action="store_true", help="después del diagnóstico: estado inicial y plan de mejoras")
    p.add_argument("--html", action="store_true")
    p.set_defaults(func=cmd_reporte)

    p = sub.add_parser("instrumentar", help="copia la instrumentación genérica a un módulo Android")
    p.add_argument("--modulo", required=True, help="carpeta del módulo de la app (el de com.android.application)")
    p.add_argument("--paquete", required=True, help="paquete Kotlin para las clases, por ejemplo com.ejemplo.app.perf")
    p.add_argument("--fuente", default="src/perf/kotlin")
    p.add_argument("--tests", default="src/testDebug/kotlin")
    p.add_argument("--red", dest="red", action="store_true", default=None)
    p.add_argument("--sin-red", dest="red", action="store_false")
    p.add_argument("--retrofit", dest="retrofit", action="store_true", default=None)
    p.add_argument("--sin-retrofit", dest="retrofit", action="store_false")
    p.add_argument("--fragments", dest="fragments", action="store_true", default=None)
    p.add_argument("--sin-fragments", dest="fragments", action="store_false")
    p.add_argument("--sin-tests", action="store_true")
    p.set_defaults(func=cmd_instrumentar)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PerfError as error:
        print("✖ %s" % error, file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        print("\n✖ interrumpido", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
