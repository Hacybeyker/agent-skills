#!/usr/bin/env python3
"""Captura, métricas, comparación y reporte de hb-performance. Solo librería estándar (Python 3.8+).

Todo lo determinista lo hace este script; el modelo solo lee resúmenes cortos.

Comandos (cada uno con --help):
  capturar      calentamiento, compilación y N corridas: traza, descarga, consultas y filas en metricas.csv
  consulta      una consulta SQL acotada sobre una traza, para el diagnóstico
  resumen       estadísticas por fase y avisos de estabilidad
  comparar      antes contra después, con veredicto por métrica
  har           métricas de red desde los HAR de testigo
  reporte       reporte en markdown (y HTML opcional) desde estado.md y metricas.csv
  instrumentar  copia la instrumentación genérica (secciones HTTP, TTFB, SCREEN y NAV) a un módulo Android

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
CORE = ["jank_app_pct", "jank_total_pct", "frame_p90_ms", "hilo_slices_sobre_presupuesto", "hilo_slices_100ms",
        "hilo_max_ms", "inflate_cantidad", "inflate_ms", "red_llamadas", "red_solapadas", "red_repetidas_2s",
        "gfx_jank_pct", "gfx_p90_ms", "pss_mb", "java_heap_mb", "activities", "views"]
VERDICT_CLASS = {"mejora": "v-better", "regresión": "v-worse", "sin cambio": "v-same", "dentro del ruido": "v-same",
                 "informativa": "v-same"}
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                        r"|[0-9a-fA-F]{16,})$")
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
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


def compare(rows, cv_max=CV_MAX):
    results, unmatched = [], []
    for (flow, metric), entry in sorted(group(rows).items()):
        phases = entry["fases"]
        if "antes" not in phases or "despues" not in phases:
            unmatched.append({"flujo": flow, "metrica": metric, "fases": sorted(phases)})
            continue
        before, after = describe(phases["antes"], cv_max), describe(phases["despues"], cv_max)
        control = phases.get("control")
        delta = after["mediana"] - before["mediana"]
        noise = abs(statistics.median(control) - before["mediana"]) if control else None
        results.append({
            "flujo": flow, "metrica": metric, "unidad": entry["unidad"], "sentido": entry["sentido"],
            "familia": entry["familia"], "antes": before, "despues": after,
            "control": describe(control, cv_max) if control else None, "delta": delta,
            "delta_pct": delta / abs(before["mediana"]) * 100 if before["mediana"] else None,
            "ruido": noise,
            "ruido_pct": noise / abs(before["mediana"]) * 100 if noise is not None and before["mediana"] else None,
            "veredicto": "informativa" if entry["familia"] == "info" else verdict(
                phases["antes"], phases["despues"], entry["sentido"], control),
            "avisos": sorted(set(before["avisos"] + after["avisos"])),
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
    return plan


# ── Métricas de una traza ────────────────────────────────────────────────────

def parse_result_sets(text):
    """Salida CSV de trace_processor: un bloque por consulta, separados por una línea en blanco."""
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


def endpoint_of(section_name):
    return section_name.split(" ", 1)[1] if " " in section_name else section_name


def network_metrics(sections, known_endpoints, force):
    """Llamadas, solapadas, repetidas y, por endpoint: llamadas, duración, TTFB y tiempo de cliente."""
    calls = [s for s in sections if s[4].startswith("HTTP ")]
    ttfbs = [s for s in sections if s[4].startswith("TTFB ")]
    if not calls and not known_endpoints and not force:
        return []
    out = [("red_llamadas", len(calls), "llamadas", "app")]
    by_endpoint = {}
    for s in calls:
        by_endpoint.setdefault(endpoint_of(s[4]), []).append(s)
    overlapped = repeated = 0
    for items in by_endpoint.values():
        items.sort(key=lambda s: s[1])
        for i, s in enumerate(items):
            if any(p[2] > 0 and p[1] < s[1] < p[1] + p[2] for p in items[:i]):
                overlapped += 1
            if i > 0 and s[1] - items[i - 1][1] < DUPLICATE_WINDOW_NS:
                repeated += 1
    out.append(("red_solapadas", overlapped, "llamadas", "app"))
    out.append(("red_repetidas_2s", repeated, "llamadas", "app"))
    for endpoint in sorted(set(by_endpoint) | set(known_endpoints)):
        items = by_endpoint.get(endpoint, [])
        out.append(("red %s llamadas" % endpoint, len(items), "llamadas", "app"))
        # Cada TTFB pertenece a la llamada del mismo endpoint que lo contiene y empezó más recientemente.
        owned = [0] * len(items)
        for t in ttfbs:
            if endpoint_of(t[4]) != endpoint or t[2] <= 0:
                continue
            owners = [i for i, s in enumerate(items) if s[2] > 0 and s[1] <= t[1] <= s[1] + s[2]]
            if owners:
                owned[max(owners, key=lambda i: items[i][1])] += t[2]
        durations, ttfb_values, client = [], [], []
        for s, ttfb in zip(items, owned):
            if s[2] <= 0:
                continue
            durations.append(s[2] / 1e6)
            if ttfb:
                ttfb_values.append(ttfb / 1e6)
                client.append(max(0.0, (s[2] - ttfb) / 1e6))
        if durations:
            out.append(("red %s ms" % endpoint, statistics.median(durations), "ms", "e2e"))
        if ttfb_values:
            out.append(("red %s ttfb_ms" % endpoint, statistics.median(ttfb_values), "ms", "e2e"))
            out.append(("red %s cliente_ms" % endpoint, statistics.median(client), "ms", "app"))
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


def trace_metrics(rows, hz, flow_spec, known, sdk):
    """Devuelve (métricas [(nombre, valor, unidad, familia)], motivo de invalidez o None, info)."""
    budget = 1e9 / (hz or 60)
    process = [r for r in rows if r[0] == "proceso"]
    frames = [r for r in rows if r[0] == "frame"]
    main = [r for r in rows if r[0] == "hilo"]
    sections = sorted((r for r in rows if r[0] == "seccion"), key=lambda r: r[1])
    bounds = [r for r in rows if r[0] == "limites"]
    info = {"frames": len(frames), "secciones": len(sections),
            "duracion_s": bounds[0][2] / 1e9 if bounds and bounds[0][2] > 0 else None,
            "nombres": {}}
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
    if frames:
        durations = [f[2] / 1e6 for f in frames if f[2] > 0]
        app_jank = sum(1 for f in frames if "App Deadline Missed" in f[4])
        any_jank = sum(1 for f in frames if f[4] not in ("None", "", "Unknown"))
        out += [("frames", len(frames), "frames", "info"),
                ("jank_app_pct", app_jank / len(frames) * 100, "%", "app"),
                ("jank_total_pct", any_jank / len(frames) * 100, "%", "app")]
        if durations:
            out += [("frame_p50_ms", percentile(durations, 0.5), "ms", "app"),
                    ("frame_p90_ms", percentile(durations, 0.9), "ms", "app"),
                    ("frame_p99_ms", percentile(durations, 0.99), "ms", "app")]
    top = [r for r in main if r[3] == 0 and r[2] >= MAIN_SLICE_MIN_NS]
    out += [("hilo_slices_sobre_presupuesto", sum(1 for r in top if r[2] > budget), "slices", "app"),
            ("hilo_slices_100ms", sum(1 for r in top if r[2] > LONG_SLICE_NS), "slices", "app"),
            ("hilo_max_ms", max((r[2] for r in top), default=0) / 1e6, "ms", "app")]
    inflates = merged_top_level([(r[1], r[2]) for r in main if r[4] == "inflate"])
    if inflates or "inflate_cantidad" in known:
        out += [("inflate_cantidad", len(inflates), "inflates", "app"),
                ("inflate_ms", sum(max(d, 0) for _, d in inflates) / 1e6, "ms", "app")]
    known_endpoints = {m[4:-9] for m in known if m.startswith("red ") and m.endswith(" llamadas")}
    out += network_metrics(sections, known_endpoints, force="red_llamadas" in known)
    users, missing = user_metrics(sections, flow_spec.get("metricas_usuario", []))
    out += users
    info["faltantes"] = missing
    return out, None, info


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


def run_tp(tp, trace, sql):
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
        query = f.name
    try:
        result = subprocess.run([tp, "query", "-f", query, str(trace)], capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            legacy = subprocess.run([tp, "-q", query, str(trace)], capture_output=True, text=True, timeout=900)
            if legacy.returncode == 0:
                result = legacy
        if result.returncode != 0:
            tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-5:])
            raise PerfError("trace_processor falló con %s:\n%s" % (pathlib.Path(trace).name, tail))
        return parse_result_sets(result.stdout)
    finally:
        os.unlink(query)


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
    result = subprocess.run([adb_binary(), "devices"], capture_output=True, text=True, timeout=60)
    devices = [line.split("\t")[0] for line in result.stdout.splitlines()[1:] if line.endswith("\tdevice")]
    if serial:
        if serial not in devices:
            raise Precondicion("el dispositivo %s no está conectado (conectados: %s)" % (serial, ", ".join(devices) or "ninguno"))
        return serial
    if not devices:
        raise Precondicion("no hay ningún dispositivo conectado con depuración USB autorizada (adb devices)")
    if len(devices) > 1:
        raise Precondicion("hay %d dispositivos conectados: elige uno con --serial (%s)" % (len(devices), ", ".join(devices)))
    return devices[0]


def preflight(adb, package, force):
    """Comprueba el dispositivo y la app. Devuelve (sdk, avisos)."""
    warnings = []
    sdk = to_int(adb.shell("getprop ro.build.version.sdk").stdout.strip())
    if sdk < 29:
        raise Precondicion("el dispositivo tiene API %d: hace falta Android 10 (API 29) o superior" % sdk)
    if "package:" not in adb.shell("pm path %s" % package).stdout:
        raise Precondicion("la app %s no está instalada en el dispositivo" % package)
    flags = re.search(r"flags=\[([^\]]*)\]", adb.shell("dumpsys package %s" % package).stdout)
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
    return sdk, warnings


def resumed_activity(adb):
    text = adb.shell("dumpsys activity activities").stdout
    match = re.search(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)[=:]\s*ActivityRecord\{[^}]*?\s(\S+/\S+)", text)
    return match.group(1) if match else ""


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


def drive(recorrido, label):
    """Recorre el flujo. Devuelve un motivo de invalidez o None."""
    if recorrido == "manual":
        answer = wait_enter("▶ %s: recorre el flujo y presiona Enter (x + Enter para descartarla) " % label)
        return "descartada por el usuario" if answer == "x" else None
    result = subprocess.run(recorrido, shell=True)
    return None if result.returncode == 0 else "el recorrido terminó con código %d" % result.returncode


def record_run(adb, config, recorrido, label, local):
    remote = "%s/hbperf-%d.perfetto-trace" % (REMOTE_DIR, os.getpid())
    started = adb.shell("perfetto --background --txt -c - -o %s" % remote, stdin=config)
    pid = (re.findall(r"\d+", started.stdout) or [None])[-1]
    if started.returncode != 0 or not pid:
        raise CapturaFallida("no se pudo iniciar Perfetto: %s" % (started.stderr or started.stdout).strip()[-300:])
    time.sleep(float(os.environ.get("HB_PERF_ESPERA", "1.5")))  # Perfetto tarda en arrancar sus fuentes
    reason = drive(recorrido, label)
    adb.shell("kill -TERM %s" % pid)
    for _ in range(60):
        if adb.shell("kill -0 %s" % pid).returncode != 0:
            break
        time.sleep(0.5)
    pulled = adb.run("pull", remote, str(local), timeout=600)
    adb.shell("rm -f %s" % remote)
    if pulled.returncode != 0 or not local.is_file() or local.stat().st_size < 1024:
        raise CapturaFallida("no se pudo descargar la traza: %s" % (pulled.stderr or pulled.stdout).strip()[-300:])
    return reason


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
    for name, label in (("jank_app_pct", "jank app"), ("frame_p90_ms", "P90 frame"),
                        ("hilo_slices_sobre_presupuesto", "hilo > presupuesto"), ("inflate_cantidad", "inflates"),
                        ("red_llamadas", "red"), ("red_solapadas", "solapadas"), ("gfx_jank_pct", "jank gfx"),
                        ("pss_mb", "PSS")):
        if name in values:
            parts.append("%s %s" % (label, fmt(values[name][1], values[name][2] if values[name][2] in ("%", "ms", "MB") else "")))
    return "✔ " + " · ".join(parts)


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
    if flow_name not in plan["flujos"]:
        raise PerfError("el flujo '%s' no está en el plan (flujos: %s)" % (flow_name, ", ".join(plan["flujos"])))
    flow = plan["flujos"][flow_name]
    phase = "antes" if args.prueba else normalize_phase(args.fase)
    package = plan["paquete"]
    hz = args.hz or plan.get("hz") or 60
    recorrido = args.recorrido or flow.get("recorrido") or "manual"
    tp = find_tp(args.tp)
    adb = Adb(select_device(args.serial))
    sdk, warnings = preflight(adb, package, args.forzar)
    for warning in warnings:
        print("⚠ " + warning)
    free_gb = shutil.disk_usage(str(folder if folder.exists() else folder.parent)).free / 1e9
    if free_gb < 3:
        print("⚠ quedan %.1f GB libres: cada traza puede pesar decenas o cientos de MB" % free_gb)
    config_name = plan.get("config", "base")
    config_path = ASSETS / "perfetto" / ("%s.pbtx" % config_name)
    if not config_path.is_file():
        config_path = (folder / config_name) if not pathlib.Path(config_name).is_absolute() else pathlib.Path(config_name)
    if not config_path.is_file():
        raise PerfError("no existe la configuración de Perfetto '%s'" % config_name)
    config = config_path.read_text(encoding="utf-8").replace("{{PAQUETE}}", package)
    sql = (ASSETS / "queries" / "metricas.sql").read_text(encoding="utf-8").replace("{{PAQUETE}}", package)
    csv_path = folder / "metricas.csv"
    out_dir = folder / ("prueba" if args.prueba else phase)
    out_dir.mkdir(parents=True, exist_ok=True)
    known = known_metrics(csv_path, flow_name)
    start_screen = flow.get("inicio")

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

    if not args.sin_compilar:
        compiled = adb.shell("cmd package compile -f -m speed-profile %s" % package, timeout=600)
        if "Success" in compiled.stdout:
            print("✔ compilación de ART fijada (speed-profile)")
        else:
            print("⚠ no se pudo fijar la compilación de ART: %s" % (compiled.stdout + compiled.stderr).strip()[-200:])
    warmups = 0 if args.prueba else args.calentamiento
    for i in range(warmups):
        check_start()
        reason = drive(recorrido, "calentamiento %d/%d (no cuenta)" % (i + 1, warmups))
        if reason:
            print("⚠ calentamiento: %s" % reason)

    target = 1 if args.prueba else args.corridas
    valid, attempts = 0, 0
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
        reason = record_run(adb, config, recorrido, label, local)
        metrics, invalid, info = [], reason, {}
        if not invalid:
            header, body = run_tp(tp, local, sql)[-1]
            metrics, invalid, info = trace_metrics(trace_rows(header, body), hz, flow, known, sdk)
        if not invalid and sdk < 31:
            metrics += parse_gfxinfo(adb.shell("dumpsys gfxinfo %s" % package).stdout)
        if not invalid and args.memoria:
            metrics += parse_meminfo(adb.shell("dumpsys meminfo %s" % package).stdout)
        size_mb = local.stat().st_size / 1e6
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
        if not args.sin_comprimir:
            compress(local)
        if args.prueba:
            print(run_line("de prueba", size_mb, metrics))
            print(markdown_table(["Métrica", "Valor", "Familia"],
                                 [[m[0], fmt(m[1], m[2]), m[3]] for m in metrics[:MAX_ROWS]]))
            names = sorted(info["nombres"].items(), key=lambda kv: -kv[1])[:15]
            print("Secciones propias: %s" % (", ".join("%s ×%d" % kv for kv in names) or "ninguna"))
            if info.get("faltantes"):
                print("⚠ Métricas de usuario sin marcas en la traza: %s" % ", ".join(info["faltantes"]))
            return
        append_rows(csv_path, [metric_row(phase, flow_name, n, m[0], m[1], m[2], m[3]) for m in metrics])
        known |= {m[0] for m in metrics}
        print(run_line("%d/%d" % (valid + 1, target), size_mb, metrics))
        if info.get("faltantes"):
            print("  ⚠ sin marcas para: %s" % ", ".join(info["faltantes"]))
        valid += 1
        n += 1
    rows = read_rows(csv_path)
    table, hidden = summary_rows(rows, plan, phases=(phase,), flows=(flow_name,))
    print(markdown_table(SUMMARY_HEADERS, table[:MAX_ROWS]))
    write_summary(csv_path, rows, plan)


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


# ── consulta ─────────────────────────────────────────────────────────────────

def cmd_consulta(args):
    tp = find_tp(args.tp)
    if args.sql:
        sql = args.sql
    elif args.archivo:
        path = pathlib.Path(args.archivo)
        if not path.is_file():
            path = ASSETS / "queries" / "diagnostico" / args.archivo
        if not path.is_file():
            raise PerfError("no existe la consulta %s" % args.archivo)
        sql = path.read_text(encoding="utf-8")
    else:
        raise PerfError("pasa un archivo .sql o --sql")
    if "{{PAQUETE}}" in sql:
        if not args.paquete:
            raise PerfError("esta consulta necesita --paquete")
        sql = sql.replace("{{PAQUETE}}", args.paquete)
    for header, body in run_tp(tp, args.traza, sql):
        rows = [[(c or "—")[:args.ancho] for c in row] for row in body[:args.limite]]
        print(markdown_table(header, rows))
        if len(body) > args.limite:
            print("… %d filas más (sube --limite o filtra la consulta)" % (len(body) - args.limite))


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
    if len(chosen) < len(results):
        print("… %d métricas sin cambios relevantes en comparacion.md" % (len(results) - len(chosen)))
    for u in unmatched[:5]:
        print("⚠ Sin comparar: %s · %s (solo en: %s)" % (u["flujo"], u["metrica"], ", ".join(u["fases"])))
    regressions = [r for r in results if r["veredicto"] == "regresión"]
    if regressions:
        print("✖ %d regresiones: repórtalas aunque no sean métricas principales." % len(regressions))
    folder = pathlib.Path(args.csv).parent
    (folder / "comparacion.md").write_text("# Comparación\n\n" + markdown_table(
        COMPARE_HEADERS, [compare_cells(r) for r in compact_compare(results, plan, everything=True)]) + "\n",
        encoding="utf-8")
    if update_block(folder, "comparacion", markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen[:MAX_ROWS]])):
        print("✔ estado.md actualizado (Comparación)")
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


def cmd_reporte(args):
    folder = pathlib.Path(args.carpeta)
    state_path, csv_path = folder / "estado.md", folder / "metricas.csv"
    if not state_path.is_file():
        raise PerfError("no existe %s" % state_path)
    title, sections = state_sections(state_path.read_text(encoding="utf-8"))
    plan = load_plan(folder / "plan.json") if (folder / "plan.json").is_file() else {}
    results, unmatched = compare(read_rows(csv_path)) if csv_path.is_file() else ([], [])
    principales = plan.get("principales") or []
    primary = sorted([r for r in results if r["metrica"] in principales], key=lambda r: priority(r["metrica"], plan))
    missing = [m for m in principales if m not in {r["metrica"] for r in results}]
    chosen = compact_compare(results, plan)

    def pick(*names):
        return next((sections[k] for k in sections for n in names if k.startswith(n)), "")

    primary_md = markdown_table(["Flujo", "Métrica", "Antes", "Después", "Δ %", "Veredicto"], [
        [r["flujo"], r["metrica"], fmt(r["antes"]["mediana"], r["unidad"]), fmt(r["despues"]["mediana"], r["unidad"]),
         fmt_pct(r["delta_pct"]), r["veredicto"] + (" (backend)" if r["familia"] == "e2e" else "")] for r in primary]
    ) if primary else ""
    comparison_md = markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen]) if chosen else \
        "No hay métricas con antes y después."
    parts = [("Resumen ejecutivo", pick("resumen ejecutivo")), ("Métricas principales", primary_md),
             ("Hallazgos", pick("hallazgos")), ("Mejoras aplicadas", pick("mejoras aplicadas")),
             ("Comparación", comparison_md), ("Ficha y condiciones", pick("ficha")),
             ("Pendientes", pick("pendientes"))]
    date = datetime.date.today().isoformat()
    md = "# %s\n\n_Generado el %s · e2e = depende del backend_\n" % (title, date)
    md += "".join("\n## %s\n\n%s\n" % (name, body) for name, body in parts if body)
    (folder / "reporte.md").write_text(md, encoding="utf-8")
    print("✔ Reporte: %s" % (folder / "reporte.md"))
    if args.html:
        charts = "".join('<figure class="chart"><figcaption>%s · %s</figcaption>%s</figure>'
                         % (e(r["metrica"]), e(r["flujo"]), bars_svg(r)) for r in primary)
        body = ""
        for name, content in parts:
            if not content:
                continue
            extra = '<div class="charts">%s</div>' % charts if name == "Métricas principales" and charts else ""
            body += "<section><h2>%s</h2>%s%s</section>" % (e(name), extra, md_to_html(content))
        body = re.sub(r"<td>(mejora|regresión|sin cambio|dentro del ruido|informativa)( \(backend\))?</td>",
                      lambda m: '<td><span class="verdict %s">%s</span>%s</td>' % (
                          VERDICT_CLASS[m.group(1)], m.group(1), m.group(2) or ""), body)
        page = (ASSETS / "plantillas" / "reporte.html").read_text(encoding="utf-8")
        page = page.replace("{{TITLE}}", e(title)).replace("{{SUBTITLE}}", e(date)).replace("{{BODY}}", body)
        (folder / "reporte.html").write_text(page, encoding="utf-8")
        print("✔ Reporte HTML: %s" % (folder / "reporte.html"))
    for m in missing:
        print("⚠ La métrica principal '%s' no tiene antes y después en el CSV." % m)
    if unmatched:
        print("⚠ %d métricas sin las dos fases (ver comparacion.md)." % len(unmatched))


# ── instrumentar ─────────────────────────────────────────────────────────────

def detect(module, words):
    texts = []
    for candidate in (module / "build.gradle.kts", module / "build.gradle", module.parent / "gradle" / "libs.versions.toml",
                      module.parent.parent / "gradle" / "libs.versions.toml"):
        if candidate.is_file():
            texts.append(candidate.read_text(encoding="utf-8", errors="ignore").lower())
    return any(w in t for t in texts for w in words)


def choose(flag, detected):
    return detected if flag is None else flag


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
        target.write_text(source.read_text(encoding="utf-8").replace("{{PAQUETE}}", args.paquete), encoding="utf-8")
        print("+ %s" % target)
    print("Red: %s · Retrofit: %s · Fragments: %s" % (
        "sí" if network else "no", "sí" if retrofit else "no", "sí" if fragments else "no"))
    print("Falta el cableado (references/setup.md): source set '%s' en debug y profiling, PerfInstaller en los "
          "manifests de debug y profiling%s, y el DoD." % (
              args.fuente, ", TraceEventListener.FACTORY en cada OkHttpClient" if network else ""))


# ── Entrada ──────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="Captura, métricas, comparación y reporte de hb-performance.")
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("capturar", help="calentamiento, compilación y N corridas con traza, consultas y CSV")
    p.add_argument("--plan", help="<carpeta>/plan.json")
    p.add_argument("--flujo")
    p.add_argument("--fase", help="antes, control o despues")
    p.add_argument("--corridas", type=int, default=MIN_RUNS)
    p.add_argument("--calentamiento", type=int, default=1)
    p.add_argument("--recorrido", help="'manual' (Enter entre corridas) o un comando que recorre el flujo (testigo)")
    p.add_argument("--serial")
    p.add_argument("--tp", help="ruta de trace_processor")
    p.add_argument("--hz", type=int, help="tasa de refresco del dispositivo (si no, la del plan o 60)")
    p.add_argument("--memoria", action="store_true", help="agrega dumpsys meminfo después de cada corrida")
    p.add_argument("--sin-compilar", action="store_true", help="no fija la compilación de ART")
    p.add_argument("--sin-comprimir", action="store_true", help="deja las trazas sin gzip")
    p.add_argument("--prueba", action="store_true", help="una corrida que imprime las métricas y no escribe el CSV")
    p.add_argument("--forzar", action="store_true", help="sigue aunque el dispositivo esté caliente")
    p.add_argument("--paquete", help="con --prueba y sin plan")
    p.add_argument("--carpeta", help="con --prueba y sin plan")
    p.set_defaults(func=cmd_capturar)

    p = sub.add_parser("consulta", help="consulta SQL acotada sobre una traza")
    p.add_argument("traza")
    p.add_argument("archivo", nargs="?", help="archivo .sql (o el nombre de una consulta de assets/queries/diagnostico)")
    p.add_argument("--sql")
    p.add_argument("--paquete")
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

    p = sub.add_parser("reporte", help="reporte.md (y reporte.html) desde estado.md y metricas.csv")
    p.add_argument("--carpeta", required=True)
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
