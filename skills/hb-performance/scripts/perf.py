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
  humo          prueba de humo del setup: una corrida de arranque, sin crear una investigación
  decidir       registra qué mejoras se aprueban, se descartan o quedan pendientes (sin chat)
  siguiente     el paso que sigue, con sus comandos completos; también lo escribe en estado.md
  consumo       anota el costo de una sesión en estado.md (sin chat)
  instrumentar  copia la instrumentación genérica (secciones HTTP, QUEUE, CONN, TTFB, SCREEN y NAV) a un módulo
  nodos         busca un nodo en un volcado de uiautomator y da el centro de sus bounds para tocarlo con adb

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
import textwrap
import time
import xml.etree.ElementTree as ElementTree
from urllib.parse import urlsplit

VERSION = "0.7.0"
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
# Métricas por tramo (segmentos del flujo): "<tramo> <métrica>", entre dos marcas y con lo que se solapa con el tramo.
SEGMENT_METRICS = ("hilo_max_ms", "frame_p90_ms", "jank_app_pct")
SEGMENT_FRAME_SUFFIXES = (" frame_p90_ms", " jank_app_pct")
SEGMENT_NAME = re.compile(r"[A-Za-z][\w-]*")
FRAMES_LEVEL = {"ok": 0, "baja": 1, "no": 2}
SOFTWARE_RENDERER = re.compile(r"swiftshader|llvmpipe|softpipe|swrast|subzero|software", re.I)
FRAMES_CHANGE_MAX = 0.5
NOT_JANK = {"", "None", "Unknown", "Unknown Jank", "Buffer Stuffing", "SurfaceFlinger Stuffing"}
COMMON_HZ = (24, 30, 48, 50, 60, 72, 75, 90, 96, 100, 120, 144, 165, 240)
HZ_TOLERANCE = 0.06  # la tasa del plan y la de la traza son "la misma" si difieren menos que esto
# Slices con los que la plataforma entrega un evento de input a la app (toques, swipes), como GLOB de trace_processor.
# Es una heurística: el nombre depende de la versión de Android; el plan lo cambia con 'input_slices'.
INPUT_SLICES = "deliverInputEvent*"
INPUT_GLOB = re.compile(r"[\w .:=#()\[\]*?-]+")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INPUT_GRACE_NS = 100_000_000  # los eventos del mismo gesto que dispara una métrica no cuentan como "pasos del recorrido"
VERDICT_CLASS = {"mejora": "v-better", "regresión": "v-worse", "sin cambio": "v-same", "dentro del ruido": "v-same",
                 "informativa": "v-same", "no comparable": "v-same", "no confiable": "v-same"}
FICHA_REPORTE = ("alcance", "síntoma", "sintoma", "métricas principales", "metricas principales", "build",
                 "dispositivo", "modos")
FAMILY_LABEL = {"app": "solo la app", "e2e": "app + backend", "info": "informativa"}
VERDICT_TEXT = {"mejora": "funcionó: mejoró más que el ruido de medición",
                "regresión": "empeoró más que el ruido de medición",
                "sin cambio": "no cambió: la mediana de después queda dentro del rango de antes",
                "dentro del ruido": "la diferencia no supera el ruido de medición",
                "no comparable": "no comparable: cambió la cantidad de frames y el porcentaje mide otra cosa",
                "no confiable": "no confiable: los frames se midieron con render por software, no dicen cómo se ve en un dispositivo real",
                "informativa": "informativa: sin veredicto"}
STATE_TEXT = {"propuesta": "propuesta · esperando tu decisión", "aprobada": "aprobada · se aplica en la sesión 3",
              "aplicada": "aplicada · implementada; se mide en la fase después", "descartada": "descartada · no se aplica",
              "pendiente": "pendiente · queda para más adelante"}
GLOSSARY = """- **Mediana:** el valor del medio de las corridas; una corrida rara no la mueve. Es el número que se compara.
- **P90:** 9 de cada 10 corridas quedaron por debajo de este valor; muestra los peores casos habituales.
- **Corridas:** cuántas veces se repitió el flujo para esa fase. Menos de 5 es poca evidencia.
- **Ruido de medición:** cuánto cambia la métrica entre dos mediciones **sin ningún cambio** en la app (antes contra control). Una diferencia menor que esto no prueba nada.
- **Varía mucho (CV):** las corridas difieren entre sí más de un 10 %; suele ser el backend (red) o el dispositivo. El número sirve, pero con menos confianza.
- **Depende de:** `solo la app` se puede mejorar desde el código; `app + backend` incluye el servidor y la red, así que sus veredictos son orientativos; `informativa` no tiene veredicto.
- **Veredictos:** `mejora` o `regresión` solo cuando la mediana de después sale del rango de antes y supera el ruido; `sin cambio` y `dentro del ruido` significan que no se puede afirmar nada; `no comparable`, que la métrica mide otra cosa (cambió la cantidad de frames); `no confiable`, que los frames se midieron en un dispositivo que renderiza por software (emulador sin GPU del host) y no valen.
- **Hallazgos:** una causa posible encontrada en el código o en las trazas. Los marcados como `bug` o `mejorable` generan una mejora; `descartado` quiere decir que se investigó y la traza muestra que **no** es la causa (no hay nada que hacer); `sin confirmar` (antes `sin veredicto estadístico`), que no se pudo confirmar ni descartar.
- **`sin confirmar` no quiere decir que falten trazas ni que la captura fallara.** Separa dos cosas: el **síntoma** puede ser estable (tiene su métrica, medida en todas las corridas) y aun así la **causa** no estar probada, porque nada une ese síntoma con una línea de código. Repetir las mismas corridas no lo cambia: la columna "Qué falta para decidir" dice qué sí (una métrica propia del tramo, otra clase de captura o probar un cambio). Si el síntoma es estable y está fuera de presupuesto, puede ir como mejora a prueba.
- **Mejoras (M1, M2…):** los cambios concretos que atacan un hallazgo. Su estado dice en qué punto están: propuesta, aprobada, aplicada, descartada o pendiente.
- **Mejora a prueba:** el síntoma está medido y es estable, pero su causa no se pudo probar. Se aplica el cambio más probable y la medición de después dice si la hipótesis era cierta (`✔ hipótesis confirmada`) o no (`✖ hipótesis refutada`).
- **Métricas por tramo (`<tramo> …`):** el hilo principal y los frames solo entre dos marcas del flujo (una pantalla, un salto), contando lo que se solapa con ese tramo, para que un pico no se diluya en el recorrido completo."""
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                        r"|[0-9a-fA-F]{16,})$")
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
MARKER = "hbperf_marker"
ESTADOS = ("propuesta", "aprobada", "descartada", "pendiente", "aplicada")
# Niveles de modelo que recomienda `siguiente`. 'diagnostico' (la sesión 2) es opcional en plan.json: sin él usa el
# 'intermedio' del plan, así que un plan anterior no cambia.
MODELOS = {"economico": "Haiku 5.5", "intermedio": "Sonnet 5.5", "diagnostico": "Sonnet 5.5", "alto": "Opus 5.5"}
MODEL_FALLBACK = {"diagnostico": "intermedio"}
SECTION_PREFIXES = ("HTTP", "QUEUE", "CONN", "TTFB", "SCREEN", "NAV", "MARK")
QUERY_TAG = re.compile(r" #[0-9a-f]{4,8}$")
e = html.escape


MAX_CONSECUTIVE_INVALID = 3


def max_attempts(target):
    """Intentos totales de una captura: las corridas pedidas más una reserva de 3 como mínimo y de la mitad de las pedidas
    si son más (5 → 8, 10 → 15, 20 → 30). Así las inválidas sueltas de un backend inestable no cortan una captura larga;
    las seguidas ya las corta MAX_CONSECUTIVE_INVALID."""
    return target + max(3, target // 2)


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


def human_warnings(avisos, cv=None, n=None):
    """Los avisos del script en palabras: qué pasa y por qué."""
    out = []
    for aviso in avisos:
        if aviso == "pocas corridas":
            out.append("pocas corridas (%s de %d): menos evidencia" % (n if n is not None else "menos", MIN_RUNS))
        elif aviso == "inestable":
            out.append("varía mucho entre corridas" + (" (CV %.0f %%)" % cv if cv is not None else ""))
        else:
            out.append(aviso)
    return "; ".join(out) or "—"


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


def frames_key(metric):
    """La métrica que cuenta los frames sobre los que se calcula `metric` ("frames", o "<tramo> frames"); None si
    `metric` no es un porcentaje ni un percentil de frames."""
    if metric in FRAME_METRICS:
        return "frames"
    for suffix in SEGMENT_FRAME_SUFFIXES:
        if metric.endswith(suffix):
            return metric[:-len(suffix)] + " frames"
    return None


def frames_changed(groups, flow, key="frames"):
    """True si la mediana de frames cambió más de FRAMES_CHANGE_MAX entre antes y después."""
    entry = groups.get((flow, key))
    if not entry or "antes" not in entry["fases"] or "despues" not in entry["fases"]:
        return False
    before = statistics.median(entry["fases"]["antes"])
    after = statistics.median(entry["fases"]["despues"])
    return abs(after - before) > FRAMES_CHANGE_MAX * max(before, 1)


def frame_metric(name):
    return name in FRAME_METRICS or name.startswith("gfx_") or name.endswith(SEGMENT_FRAME_SUFFIXES)


def frames_note(trust):
    """Aviso para las métricas de frame según la confianza del dispositivo que las midió."""
    level, motive = trust
    if level == "no":
        return "frames no confiables (%s)" % motive
    if level == "baja":
        return "frames orientativos (%s)" % motive
    return ""


def compare(rows, cv_max=CV_MAX, trust=("ok", "")):
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
        note = frames_note(trust) if frame_metric(metric) else ""
        if note:
            warnings.add(note)
        if entry["familia"] == "info":
            result = "informativa"
        elif note and trust[0] == "no":
            result = "no confiable"
        elif frames_key(metric) and frames_changed(groups, flow, frames_key(metric)):
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


def segment_metric_names(flow):
    return ["%s %s" % (s["nombre"], m) for s in flow.get("segmentos") or [] for m in SEGMENT_METRICS]


def user_metric_names(plan):
    """Las métricas que define el plan: las de usuario y las de cada tramo (segmentos)."""
    flows = list((plan.get("flujos") or {}).values())
    return [m["nombre"] for flow in flows for m in flow.get("metricas_usuario", [])] \
        + [name for flow in flows for name in segment_metric_names(flow)]


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


def summary_rows(rows, plan, phases=FASES, flows=None, everything=False, trust=("ok", "")):
    table, hidden = [], 0
    note = frames_note(trust)
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
                          ", ".join(s["avisos"] + ([note] if note and frame_metric(metric) else [])) or "—"])
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

def check_marker(marker):
    return bool(marker.get("marca")) and marker.get("punto", "inicio") in ("inicio", "fin") \
        and marker.get("cual", "primera") in ("primera", "ultima")


def check_margin(spec):
    """True si 'margen_ms' falta o es un número (lo que después lee int())."""
    try:
        int(spec.get("margen_ms", 0))
        return True
    except (TypeError, ValueError, OverflowError):
        return False


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
                if not check_marker(spec[side]):
                    raise PerfError("'%s.%s' en '%s': usa marca, punto (inicio|fin) y cual (primera|ultima)"
                                    % (spec["nombre"], side, name))
        segments = flow.get("segmentos") or []
        seen = set()
        for spec in segments if isinstance(segments, list) else [None]:
            if not isinstance(spec, dict) or not isinstance(spec.get("nombre"), str) \
                    or not SEGMENT_NAME.fullmatch(spec["nombre"]) or spec["nombre"] == "red" or spec["nombre"] in seen \
                    or not all(isinstance(spec.get(side), dict) and check_marker(spec[side]) for side in ("desde", "hasta")) \
                    or not check_margin(spec):
                raise PerfError("'%s.segmentos' es una lista de tramos: cada uno con 'nombre' (letras, números, _ o -; sin "
                                "repetir y distinto de 'red'), 'desde' y 'hasta' (marcas, como en metricas_usuario) y, si "
                                "quieres, 'margen_ms' (un número)" % name)
            seen.add(spec["nombre"])
    for item in plan.get("mejoras", []):
        if not isinstance(item, dict) or not item.get("id") or not item.get("titulo"):
            raise PerfError("%s: cada mejora necesita al menos 'id' y 'titulo'" % path)
        if item.get("estado", "propuesta") not in ESTADOS:
            raise PerfError("%s: la mejora %s tiene estado '%s': usa %s" % (path, item["id"], item.get("estado"),
                                                                           ", ".join(ESTADOS)))
        if not isinstance(item.get("a_prueba", False), bool):
            raise PerfError("%s: 'a_prueba' de la mejora %s es true o false" % (path, item["id"]))
        if item.get("a_prueba") and not all(str(item.get(key) or "").strip() for key in ("hipotesis", "metrica", "esperado")):
            raise PerfError("%s: la mejora a prueba %s necesita 'hipotesis', 'metrica' y 'esperado': la medición de después "
                            "confirma o refuta la hipótesis con esa métrica" % (path, item["id"]))
    if plan.get("instalar") is not None and not isinstance(plan["instalar"], str):
        raise PerfError("%s: 'instalar' es el comando que compila e instala el build de profiling (texto)" % path)
    if plan.get("profundidad", "riguroso") not in ("riguroso", "triage"):
        raise PerfError("%s: 'profundidad' es riguroso o triage" % path)
    for name, flow in plan["flujos"].items():
        if flow.get("preparar") is not None and not isinstance(flow["preparar"], str):
            raise PerfError("%s: flujos.%s.preparar es un comando (texto) que deja la app en el punto de partida" % (path, name))
        needed = flow.get("requiere_env", [])
        if not isinstance(needed, list) or any(not isinstance(v, str) or not ENV_NAME.fullmatch(v) for v in needed):
            raise PerfError("%s: flujos.%s.requiere_env es una lista de nombres de variables de entorno, por ejemplo "
                            "[\"PERF_USUARIO\", \"PERF_CLAVE\"] (los nombres, nunca los valores)" % (path, name))
        window = flow.get("ventana")
        if window is not None and not (isinstance(window, dict) and "desde" in window and "hasta" in window):
            raise PerfError("%s: flujos.%s.ventana necesita 'desde' y 'hasta' (marcas, como metricas_usuario)" % (path, name))
        if window is not None and not check_margin(window):
            raise PerfError("%s: flujos.%s.ventana.margen_ms es un número de milisegundos" % (path, name))
    if plan.get("input_slices") is not None and not (isinstance(plan["input_slices"], str)
                                                     and INPUT_GLOB.fullmatch(plan["input_slices"])):
        raise PerfError("%s: 'input_slices' es un patrón GLOB con el nombre de los slices de input (por defecto %s)"
                        % (path, INPUT_SLICES))
    if not isinstance(plan.get("modelos", {}), dict):
        raise PerfError("%s: 'modelos' es un objeto con economico, intermedio, alto y, si quieres, diagnostico" % path)
    foreign = plan.get("hilos_ajenos", [])
    if not isinstance(foreign, list):
        raise PerfError("%s: 'hilos_ajenos' es una lista de {\"nombre\", \"patron\"}" % path)
    names = set()
    for group_spec in foreign:
        if not isinstance(group_spec, dict) or not re.fullmatch(r"[A-Za-z][\w-]*", str(group_spec.get("nombre", ""))) \
                or not group_spec.get("patron"):
            raise PerfError("%s: cada entrada de 'hilos_ajenos' necesita 'nombre' (letras, números, _ o -) y 'patron' "
                            "(expresión regular del nombre del hilo)" % path)
        try:
            re.compile(group_spec["patron"])
        except (re.error, TypeError):
            raise PerfError("%s: 'hilos_ajenos' %s: la expresión regular %r no es válida" % (
                path, group_spec["nombre"], group_spec["patron"]))
        if group_spec.get("familia", "e2e") not in FAMILIAS or group_spec["nombre"] in names:
            raise PerfError("%s: 'hilos_ajenos' %s: nombre repetido o familia fuera de %s" % (
                path, group_spec["nombre"], ", ".join(FAMILIAS)))
        names.add(group_spec["nombre"])
    if not isinstance(plan.get("no_leer", []), list) or any(not isinstance(x, str) or not x.strip() for x in plan.get("no_leer", [])):
        raise PerfError("%s: 'no_leer' es una lista de rutas o patrones que el agente no debe leer (texto)" % path)
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


def user_metric_bounds(sections, spec):
    """(inicio, fin) en ns de una métrica de usuario; None en el que no tenga su marca."""
    start = resolve_marker(sections, spec["desde"], "inicio", "primera")
    end = resolve_marker(sections, spec["hasta"], "fin", "ultima", after=start) if start is not None else None
    return start, end


def metrics_spanning_input(sections, specs, inputs):
    """{métrica de usuario: eventos de input entre sus marcas}. Una métrica que contiene toques o swipes del recorrido
    mide el script (sus toques y sus esperas), no la app. No cuentan los eventos de los primeros INPUT_GRACE_NS: son
    del mismo gesto que dispara la métrica."""
    out = {}
    for spec in specs:
        start, end = user_metric_bounds(sections, spec)
        if start is None or end is None:
            continue
        count, previous = 0, start
        for ts in inputs:
            if not start < ts < end:
                continue
            if count == 0 and ts - previous < INPUT_GRACE_NS:
                previous = ts  # sigue el gesto que disparó la métrica (el ACTION_UP de un toque, los MOVE de un swipe)
                continue
            count += 1
        if count:
            out[spec["nombre"]] = count
    return out


def repeated_marks(sections):
    """{marca: veces} de las marcas MARK que salieron más de una vez en una misma carga: apariciones seguidas de la
    misma marca sin nada entre ellas que indique una carga nueva (una navegación NAV, el ciclo de vida de otra pantalla
    en SCREEN, otra marca o una llamada de red que empieza). Es una heurística: no avisa de una recarga legítima de la
    misma pantalla (un filtro, un pull-to-refresh) y puede no ver un duplicado con una llamada de red en medio."""
    out, last, streak, screen = {}, None, 0, None
    for section in sorted(sections, key=lambda r: r[1]):
        name = section[4]
        if name.startswith("MARK "):
            streak = streak + 1 if name == last else 1
            last = name
            if streak > 1:
                out[name] = max(out.get(name, 0), streak)
        elif name.startswith("SCREEN "):
            current = (name.split(" ") + [""])[1]
            if screen is not None and current != screen:
                last, streak = None, 0
            screen = current
        elif name.startswith(("NAV ", "HTTP ")):
            last, streak = None, 0
    return out


def user_metrics(sections, specs):
    out, missing = [], []
    for spec in specs:
        start, end = user_metric_bounds(sections, spec)
        if start is None or end is None:
            missing.append(spec["nombre"])
            continue
        out.append((spec["nombre"], (end - start) / 1e6, "ms", spec.get("familia", "e2e")))
        if spec["hasta"].get("marca", "").startswith("HTTP "):
            # Si la métrica termina en una llamada, guarda también hasta dónde llega la última llamada: si una mejora
            # reordena las llamadas, la marca de fin deja de ser la última y la métrica cambia de significado.
            last = max((s[1] + max(s[2], 0) for s in sections if s[4].startswith("HTTP ") and s[1] >= start), default=None)
            if last is not None:
                out.append((spec["nombre"] + " hasta_ultima_red_ms", (last - start) / 1e6, "ms", "info"))
    return out, missing


def resolve_window(markers, spec):
    """(inicio, fin) en ns de la ventana del flujo, o None si falta alguna marca."""
    if not spec:
        return None
    start = resolve_marker(markers, spec["desde"], "inicio", "primera")
    end = resolve_marker(markers, spec["hasta"], "fin", "ultima", after=start) if start is not None else None
    if start is None or end is None or end <= start:
        return None
    return start, end + int(spec.get("margen_ms", 0)) * 1_000_000


def segment_metrics(markers, frames, main, specs):
    """Métricas por tramo (segmentos del flujo): el slice más largo del hilo principal, el P90 de frame y el jank de la
    app entre dos marcas, con los slices y los frames que se solapan con el tramo. Así un pico de una sola pantalla no
    se diluye en la ventana del flujo. `frames` y `main` son los de toda la traza. Devuelve (métricas, tramos sin marcas)."""
    out, missing = [], []
    for spec in specs:
        bounds = resolve_window(markers, spec)
        if not bounds:
            missing.append(spec["nombre"])
            continue
        start, end = bounds
        name = spec["nombre"]
        top = [r for r in main if r[3] == 0 and r[2] >= MAIN_SLICE_MIN_NS and r[1] <= end and r[1] + r[2] >= start]
        out.append(("%s hilo_max_ms" % name, max((r[2] for r in top), default=0) / 1e6, "ms", "app"))
        inside = [f for f in frames if f[1] <= end and f[1] + max(f[2], 0) >= start]
        if not inside:
            continue
        out += [("%s frames" % name, len(inside), "frames", "info"),
                ("%s jank_app_pct" % name, sum(1 for f in inside if "App Deadline Missed" in f[4]) / len(inside) * 100,
                 "%", "app")]
        durations = [f[2] / 1e6 for f in inside if f[2] > 0]
        if durations:
            out.append(("%s frame_p90_ms" % name, percentile(durations, 0.9), "ms", "app"))
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


def hz_warning(hz, seen):
    """Aviso si la tasa de refresco del plan (o de --hz) no es la que midió la traza, o si cambió entre corridas."""
    seen = sorted({h for h in seen if h})
    measured = "/".join(str(h) for h in seen)
    if hz and any(abs(h - hz) > hz * HZ_TOLERANCE for h in seen):
        return ("TASA DE REFRESCO: el plan dice %s Hz y la traza midió %s Hz. El presupuesto de frame "
                "(hilo_slices_sobre_presupuesto) se calculó con %s Hz: corrige 'hz' en plan.json (o quítalo, y se lee de "
                "cada traza) y repite lo medido así con --rehacer" % (hz, measured, hz))
    if not hz and len(seen) > 1:
        return ("TASA DE REFRESCO: cambió entre corridas (%s Hz): el dispositivo no la tiene fija. Fíjala (ficha.md · "
                "Dispositivo), pon 'hz' en plan.json y repite lo medido así con --rehacer" % measured)
    return ""


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
    inputs = sorted(r[1] for r in rows if r[0] == "input")
    info = {"frames": len(frames), "secciones": len(sections), "input": len(inputs),
            "marcas_repetidas": repeated_marks(sections),
            "duracion_s": bounds[0][2] / 1e9 if bounds and bounds[0][2] > 0 else None,
            "nombres": {}, "hz_traza": hz_from_vsync(vsync), "arranque": bool(launches)}
    hz = hz or info["hz_traza"] or 60
    info["hz"] = hz
    budget = 1e9 / hz
    for s in sections:
        info["nombres"][s[4]] = info["nombres"].get(s[4], 0) + 1
    if not process:
        return [], "la app no aparece en la traza", info
    markers = sorted(sections + main + launches, key=lambda r: r[1])
    all_frames, all_main = frames, main
    window = resolve_window(markers, flow_spec.get("ventana"))
    info["ventana_ns"] = window
    if window:  # frames e hilo solo dentro de la ventana: lo que pasa antes o después (esperar, dar Enter) no cuenta
        frames = [f for f in frames if window[0] <= f[1] <= window[1]]
        main = [r for r in main if window[0] <= r[1] <= window[1]]
    elif flow_spec.get("ventana"):
        info["ventana_faltante"] = True
    for pattern in flow_spec.get("invalidar_si", []):
        hit = next((s[4] for s in sections if fnmatch.fnmatchcase(s[4], pattern)), None)
        if hit:
            return [], "apareció '%s'" % hit, info
    if sdk >= 31 and not frames:
        return [], "no hay frames de la app%s" % (" en la ventana del flujo" if window else " (¿estaba visible?)"), info
    out = []
    if window:
        out.append(("ventana_ms", (window[1] - window[0]) / 1e6, "ms", "info"))
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
    users, missing = user_metrics(markers, flow_spec.get("metricas_usuario", []))
    out += users
    info["con_input"] = metrics_spanning_input(markers, flow_spec.get("metricas_usuario", []), inputs)
    segments, missing_segments = segment_metrics(markers, all_frames, all_main, flow_spec.get("segmentos") or [])
    out += segments
    info["faltantes"] = missing + ["tramo %s" % name for name in missing_segments] \
        + (["ventana"] if info.get("ventana_faltante") else [])
    return with_families(out, flow_spec.get("familias")), None, info


def sections_summary(names):
    """Las secciones propias agrupadas por tipo y, en la red, por endpoint sin la marca de la query."""
    groups = {}
    for name, count in names.items():
        prefix, _, rest = name.partition(" ")
        if prefix in SECTION_PREFIXES:
            detail = endpoint_of(name) if prefix in ("HTTP", "QUEUE", "CONN", "TTFB") else rest
        else:
            prefix, detail = "otras", name
        bucket = groups.setdefault(prefix, {})
        bucket[detail] = bucket.get(detail, 0) + count
    parts = []
    for prefix in SECTION_PREFIXES + ("otras",):
        if prefix not in groups:
            continue
        items = sorted(groups[prefix].items(), key=lambda kv: (-kv[1], kv[0]))
        detail = ", ".join("%s ×%d" % kv if kv[1] > 1 else kv[0] for kv in items[:6])
        if len(items) > 6:
            detail += ", …"
        parts.append("%s ×%d (%s)" % (prefix, sum(groups[prefix].values()), detail))
    return "; ".join(parts) or "ninguna"


def foreign_thread_metrics(sets, groups, known=()):
    """Métricas de los hilos que el plan declara ajenos a la app (hilos_ajenos: un servidor en el mismo proceso, por
    ejemplo), a partir de assets/queries/hilos_ajenos.sql. Por grupo: CPU y cantidad de hilos; el resto de los hilos de
    la app (menos el principal) en hilos_app_cpu_ms; y, por endpoint, la mediana por llamada de la CPU del grupo
    mientras esa llamada estaba en vuelo (las que no tuvieron cuentan 0; la CPU de un momento con dos llamadas en vuelo
    cuenta en las dos), igual que `red <endpoint> ms`. Siempre se emiten los mismos nombres, con 0 si no hubo."""
    compiled = [(g["nombre"], re.compile(g["patron"]), g.get("familia", "e2e")) for g in groups]
    header, body = sets[-1] if sets else ([], [])
    index = {name: i for i, name in enumerate(header)}
    for column in ("tipo", "nombre", "llamada", "id", "hilos", "cpu_ms"):
        if body and column not in index:
            raise PerfError("hilos_ajenos.sql no devolvió la columna '%s'" % column)
    cpu = {name: 0.0 for name, _, _ in compiled}
    count = {name: 0 for name, _, _ in compiled}
    call_endpoint, call_cpu, other = {}, {}, 0.0  # id de la llamada → endpoint; (grupo, id) → CPU del grupo en la llamada
    for row in body:
        kind = row[index["tipo"]]
        thread = row[index["nombre"]] or ""
        owner = next((name for name, pattern, _ in compiled if pattern.search(thread)), None)
        try:
            value = float(row[index["cpu_ms"]])
        except (TypeError, ValueError):
            continue
        if kind == "hilo":
            if owner:
                cpu[owner] += value
                count[owner] += to_int(row[index["hilos"]])
            else:
                other += value
        elif kind in ("red", "llamada"):
            call = row[index["id"]]
            call_endpoint[call] = endpoint_of(row[index["llamada"]] or "")
            if kind == "red" and owner:
                call_cpu[(owner, call)] = call_cpu.get((owner, call), 0.0) + value
    out = []
    for name, _, family in compiled:
        out += [("hilos_%s_cpu_ms" % name, cpu[name], "ms", family), ("hilos_%s_cantidad" % name, count[name], "hilos", "info")]
        suffix = " %s_cpu_ms" % name
        per_endpoint = {}
        for call, endpoint in call_endpoint.items():
            per_endpoint.setdefault(endpoint, []).append(call_cpu.get((name, call), 0.0))
        endpoints = set(per_endpoint) | {m[4:-len(suffix)] for m in known if m.startswith("red ") and m.endswith(suffix)}
        out += [("red %s%s" % (endpoint, suffix), statistics.median(per_endpoint[endpoint]) if endpoint in per_endpoint else 0.0,
                 "ms", family) for endpoint in sorted(endpoints)]
    out.append(("hilos_app_cpu_ms", other, "ms", "app"))
    return out


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

TP_INSTALL = ('cd ~ && mkdir -p ~/.local/bin && curl -fsSL https://get.perfetto.dev/trace_processor '
              '-o ~/.local/bin/trace_processor && chmod +x ~/.local/bin/trace_processor && '
              '{ grep -qs \'.local/bin\' ~/.zshrc || echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.zshrc; } && '
              'export PATH="$HOME/.local/bin:$PATH" && trace_processor --version')


def find_tp(option):
    for candidate in (option, os.environ.get("TRACE_PROCESSOR"), shutil.which("trace_processor"),
                      shutil.which("trace_processor_shell")):
        if candidate and (shutil.which(candidate) or pathlib.Path(candidate).is_file()):
            return candidate
    raise Precondicion("falta trace_processor de Perfetto (lee las trazas y las consulta con SQL). "
                       "Instálalo sin root, en tu usuario, y vuelve a correr este comando:\n  %s\n"
                       "Si ya lo tienes en otra ruta, pásalo con --tp o con TRACE_PROCESSOR=<ruta>." % TP_INSTALL)


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


def classify_environment(text):
    """Emulador y render por software a partir de la salida de device_environment. 'frames' es la confianza en las
    métricas de frame: 'no' con render por software, 'baja' en un emulador con GPU del host, 'ok' en un dispositivo real."""
    values = dict(re.findall(r"^([qbhmcg])=(.*)$", text, re.M))
    hardware, model = values.get("h", "").strip().lower(), values.get("m", "").strip().lower()
    emulator = values.get("q", "").strip() == "1" or values.get("b", "").strip() == "1" \
        or hardware in ("ranchu", "goldfish") or "emulator" in values.get("c", "").lower() \
        or "emulator" in model or model.startswith("sdk_gphone") or "android sdk built for" in model
    render = values.get("g", "").replace("GLES:", "").strip()
    software = bool(SOFTWARE_RENDERER.search(render))
    return {"emulador": emulator, "render": render, "software": software,
            "frames": "no" if software else "baja" if emulator else "ok"}


def device_environment(adb):
    """Una sola llamada a adb: ro.kernel.qemu y afines, y el renderer de GLES que reporta SurfaceFlinger."""
    out = adb.shell('echo "q=$(getprop ro.kernel.qemu)"; echo "b=$(getprop ro.boot.qemu)"; echo "h=$(getprop ro.hardware)"; '
                    'echo "m=$(getprop ro.product.model)"; echo "c=$(getprop ro.build.characteristics)"; '
                    'echo "g=$(dumpsys SurfaceFlinger | grep -m1 GLES)"').stdout
    return classify_environment(out)


def environment_warnings(env):
    gpu = "reinicia el emulador con -gpu host (AVD: Graphics = Hardware) o usa un dispositivo físico"
    if env["software"]:
        return ["el dispositivo renderiza por software (%s): los frames (jank_*, frame_*, gfx_*) no son confiables y los "
                "reportes los marcan; %s" % (env["render"] or "sin dato", gpu)]
    if env["emulador"]:
        return ["es un emulador%s: valen los conteos (red, inflates) y las fugas; los tiempos y los frames son orientativos. "
                "Para decidir con frames, %s" % (" (render: %s)" % env["render"] if env["render"] else "", gpu)]
    return []


def frames_trust(folder):
    """(nivel, motivo) más bajo de confianza en los frames entre las fases registradas en fases.json."""
    level, motive = "ok", ""
    for data in read_phases(folder).values():
        env = data.get("entorno") or {}
        value = env.get("frames", "ok")
        if FRAMES_LEVEL.get(value, 0) > FRAMES_LEVEL[level]:
            level = value
            motive = ("%srender por software" % ("emulador, " if env.get("emulador") else "") if env.get("software")
                      else "emulador (render: %s)" % (env.get("render") or "sin dato"))
    return level, motive


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

def missing_env(names):
    """Las variables de 'requiere_env' que no están en el entorno o están vacías. Solo nombres: nunca valores."""
    return [name for name in names if not os.environ.get(name)]


def mask_secrets(text, names):
    """El texto con el valor de cada variable de 'requiere_env' reemplazado por ***."""
    for value in sorted({os.environ.get(name, "") for name in names}, key=len, reverse=True):
        if value:
            text = text.replace(value, "***")
    return text


def run_prepare(command, folder, secret_names):
    """Corre 'preparar' y devuelve (código, últimas líneas de su salida, ruta del log). Si funciona, su salida no se
    muestra ni se guarda. Si falla, queda su cola en <carpeta>/logs/preparar.log después de pasar por mask_secrets. La
    salida estándar solo se mira cuando el flujo declara 'requiere_env' (y se enmascaran sus valores); sin esa lista se
    descarta, como siempre, porque puede traer lo que el comando escribe, y solo se lee la salida de error."""
    with tempfile.TemporaryFile() as raw:
        result = subprocess.run(command, shell=True, stdout=raw if secret_names else subprocess.DEVNULL,
                                stderr=subprocess.STDOUT if secret_names else raw)
        raw.seek(0)
        text = mask_secrets(raw.read().decode("utf-8", "replace"), secret_names)
    lines = [line.rstrip()[:200] for line in text.splitlines() if line.strip()][-40:]
    log = pathlib.Path(folder) / "logs" / "preparar.log"
    if result.returncode != 0:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    elif log.is_file():
        log.unlink()  # el de un fallo anterior ya no dice nada
    return result.returncode, lines[-8:], log


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
    found = sorted(f for f in pathlib.Path(".").glob("*/build/outputs/mapping/*/mapping.txt")
                   if f.parent.name not in ("release", "debug"))
    target = str(found[0]) if found else "<módulo>/build/outputs/mapping/<variante>/mapping.txt"
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


def worst_environment(environments):
    """El entorno con menos confianza en los frames; con empate, el primero. None si no hay ninguno."""
    environments = [e for e in environments if e]
    return max(environments, key=lambda e: FRAMES_LEVEL.get(e.get("frames", "ok"), 0)) if environments else None


def merge_run_data(previous, data):
    """Lo que se acumula entre tandas de una fase (o de un flujo): corridas, tasa de cada corrida, avisos y el peor
    entorno."""
    out = {"corridas": previous.get("corridas", 0) + data.get("corridas", 0)}
    rates = list(previous.get("hz_corridas") or []) + list(data.get("hz_corridas") or [])
    if rates:
        out["hz_corridas"] = rates
    warnings = list(previous.get("avisos") or [])
    warnings += [w for w in data.get("avisos") or [] if w not in warnings]
    if warnings:
        out["avisos"] = warnings
    environment = worst_environment([previous.get("entorno"), data.get("entorno")])
    if environment:
        out["entorno"] = environment
    return out


def save_phases(folder, phases):
    (pathlib.Path(folder) / "fases.json").write_text(json.dumps(phases, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")


def write_phase(folder, phase, data, flow=None):
    """Registra la fase sumando las corridas de otra tanda. El 'entorno' conserva el peor nivel de frames de las tandas:
    relanzar el emulador con la GPU del host o seguir en un dispositivo real no vuelve confiables las corridas de antes.
    Con `flow`, guarda también lo de ese flujo en 'flujos', para poder rehacer un flujo sin perder lo de los demás."""
    phases = read_phases(folder)
    previous = phases.get(phase) or {}
    flows = dict(previous.get("flujos") or {})
    if flow:
        flows[flow] = merge_run_data(flows.get(flow) or {}, data)
    merged = merge_run_data(previous, data)
    for key in ("hz_corridas", "avisos", "entorno"):
        data.pop(key, None)
    data.update(merged)
    data["fecha"] = previous.get("fecha") or data["fecha"]
    if flows:
        data["flujos"] = flows
    phases[phase] = data
    save_phases(folder, phases)


def forget_flow(folder, csv_path, phase, flow):
    """--rehacer: quita de fases.json solo lo del flujo que se rehace. Si la fase tiene corridas de otros flujos, su
    registro sigue (commit, build), sin la fecha, que la pone la tanda nueva; las corridas salen del CSV y el entorno,
    los avisos y las tasas, de lo guardado por flujo. Un registro sin datos por flujo (de una versión anterior), o con
    datos incompletos, conserva los de la fase."""
    phases = read_phases(folder)
    record = phases.get(phase)
    if record is None:
        return
    others = {}
    if csv_path.is_file():
        for row in read_rows(csv_path):
            if row["fase"] == phase and row["flujo"] != flow:
                others.setdefault(row["flujo"], set()).add(row["corrida"])
    if not others:
        phases.pop(phase)
    else:
        tracked = {name: data for name, data in (record.get("flujos") or {}).items() if name in others}
        record["corridas"] = sum(len(runs) for runs in others.values())
        # La tanda que viene pone su fecha: `siguiente` compara la fecha de 'despues' con la de la última mejora
        # aplicada, y con la fecha vieja seguiría pidiendo rehacer la fase.
        record.pop("fecha", None)
        complete = set(tracked) == set(others) and all(tracked[name].get("corridas") == len(others[name]) for name in others)
        if complete:  # lo que queda tiene su registro entero: se recalcula sin el flujo que se rehace
            for key in ("hz_corridas", "avisos", "entorno"):
                record.pop(key, None)
            rest = {}
            for data in tracked.values():
                rest = merge_run_data(rest, dict(data, corridas=0))
            record.update({k: v for k, v in rest.items() if k != "corridas"})
        record.pop("flujos", None)
        if tracked:
            record["flujos"] = tracked
    save_phases(folder, phases)


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
    """--rehacer: saca del CSV las filas del flujo en esa fase, aparta sus trazas y olvida su registro, para medirlo de
    nuevo desde cero. Lo de los otros flujos de la fase no se toca."""
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
    mine = re.compile(r"%s_\d+(?:_invalida_.*)?\.perfetto-trace(?:\.gz)?" % re.escape(flow))
    traces = sorted(f for f in old.iterdir() if mine.fullmatch(f.name)) if old.is_dir() else []
    if traces:
        target = folder / ("%s-descartada-%s" % (phase, stamp))
        target.mkdir(parents=True, exist_ok=True)
        for trace in traces:
            trace.rename(target / trace.name)
        print("✔ --rehacer: trazas anteriores en %s-descartada-%s/" % (phase, stamp))
    old.mkdir(parents=True, exist_ok=True)
    forget_flow(folder, csv_path, phase, flow)


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


NO_LEER_LINE = re.compile(r"^(?P<indent>[ \t]*)(?P<bullet>(?:[-*][ \t]+)|(?:-(?=\*)))?\**[ \t]*(?:no leer|do not read)[ \t]*\**[ \t]*:"
                          r"[ \t]*\**[ \t]*(?P<rest>.*?)[ \t]*$", re.I)
BULLET_LINE = re.compile(r"^(?P<indent>[ \t]*)[-*][ \t]+(?P<item>.+?)[ \t]*$")


def no_leer_in(text):
    """Patrones de la línea 'No leer:' de un AGENTS.md: en la misma línea, separados por coma o punto y coma, o uno por
    viñeta en las líneas siguientes (sin línea en blanco en medio; si la línea es ella misma una viñeta, solo cuentan las
    viñetas más indentadas)."""
    lines = text.splitlines()
    found = []
    for index, line in enumerate(lines):
        head = NO_LEER_LINE.match(line)
        if not head:
            continue
        items = [head.group("rest")] if head.group("rest") else []
        if not items:
            depth = len(head.group("indent").expandtabs(4))
            for following in lines[index + 1:]:
                bullet = BULLET_LINE.match(following)
                if not bullet or (head.group("bullet") and len(bullet.group("indent").expandtabs(4)) <= depth):
                    break
                items.append(bullet.group("item"))
        for item in items:
            found += [part.strip().strip("`'\"") for part in re.split(r"[,;]", item)]
    return found


def read_no_leer(root, plan=None, extra=()):
    """Rutas que el agente no debe leer (pruebas a ciegas): los --no-leer, 'no_leer' del plan y la línea 'No leer:' de
    la sección Performance de AGENTS.md. Sin duplicados y en ese orden. Los patrones se comparan con la ruta desde la
    raíz del proyecto (is_denied)."""
    patterns = list(extra) + list((plan or {}).get("no_leer") or [])
    try:
        text = (pathlib.Path(root) / "AGENTS.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    patterns += no_leer_in(text)
    out = []
    for pattern in patterns:
        if pattern and pattern not in out:
            out.append(pattern)
    return out


def is_denied(path, root, patterns):
    """True si la ruta cae en alguna de las prohibidas. Un patrón relativo (docs/ALCANCE-*, secretos/) se compara con la
    ruta desde la raíz del proyecto; uno absoluto o con ~, con la ruta completa. Una carpeta cubre todo lo que tiene dentro."""
    if not patterns:
        return False
    absolute = pathlib.Path(path).resolve()
    try:
        relative = absolute.relative_to(pathlib.Path(root).resolve()).as_posix()
    except ValueError:  # fuera de la raíz (un módulo incluido desde otra carpeta): la ruta relativa, con sus '..'
        try:
            relative = pathlib.Path(os.path.relpath(str(absolute), str(pathlib.Path(root).resolve()))).as_posix()
        except ValueError:
            relative = None
    for raw in patterns:
        pattern = os.path.expanduser(raw.strip())
        if os.path.isabs(pattern):  # con y sin enlaces simbólicos (en macOS /var es /private/var)
            targets, bases = {absolute.as_posix(), os.path.abspath(str(path))}, {pattern, os.path.realpath(pattern)}
        elif relative is not None:
            targets, bases = {relative}, {pattern}
        else:
            continue
        for target in targets:
            for base in {b.rstrip("/") for b in bases if b.rstrip("/")}:
                for candidate in (target, "/" + target):
                    if fnmatch.fnmatchcase(candidate, base) or fnmatch.fnmatchcase(candidate, base + "/*"):
                        return True
    return False


def model_name(plan, tier):
    """El modelo del nivel según plan.json; un nivel sin nombre en el plan toma el de su nivel base (MODEL_FALLBACK) y, si
    tampoco está, el de fábrica."""
    named = (plan.get("modelos") or {}).get(tier)
    if named:
        return named
    return model_name(plan, MODEL_FALLBACK[tier]) if tier in MODEL_FALLBACK else MODELOS[tier]


def install_command(plan, root):
    """El comando de instalación del plan, con el serial del plan si el comando no lo lleva."""
    install = plan.get("instalar")
    if not install:
        return "cd %s && <compila e instala el build de profiling; guárdalo como 'instalar' en plan.json>" % root
    serial = plan.get("serial")
    if serial and serial not in install and "ANDROID_SERIAL" not in install:
        install = "ANDROID_SERIAL=%s %s" % (serial, install)
    return "cd %s && %s" % (root, install)


def terminal(command, what, you):
    return {"tipo": "terminal", "texto": command, "que": what, "tu": you}


def chat(text, tier, effort, what, plan):
    if plan.get("no_leer"):
        text += " No leas ni busques en: %s." % ", ".join(plan["no_leer"])
    return {"tipo": "chat", "texto": text, "modelo": model_name(plan, tier), "esfuerzo": effort, "que": what}


def next_steps(folder, plan, flow=None):
    """(título, [pasos]) del paso que sigue según fases.json, plan.json y los archivos de la carpeta.

    Cada paso es un dict: tipo terminal (comando completo, empieza con cd), chat (texto, modelo y esfuerzo) o archivo.
    Es la única fuente de los comandos de entrega: los agentes la copian en vez de inventarlos.
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

    flows = plan["flujos"]
    flow = flow if flow in flows else next(iter(flows))
    spec = flows[flow]
    automatic = bool(startup_spec(spec)) or spec.get("recorrido", "manual") != "manual"
    runs = 10 if automatic else 5
    you_run = ("nada: el script detiene y abre la app %d veces" % runs if startup_spec(spec) else
               "nada: el recorrido es automático (%d corridas)" % runs if automatic else
               "recorre el flujo en el dispositivo y presiona Enter en cada una de las %d corridas (más 1 de calentamiento)"
               % runs)
    capture = ["capturar", "--plan", folder / "plan.json"] + (["--flujo", flow] if len(flows) > 1 else [])
    phases = read_phases(root / folder)
    mejoras = plan.get("mejoras", [])
    estados = [m.get("estado", "propuesta") for m in mejoras]
    resume = "Sigue hb-performance con %s" % state
    session2 = chat(resume, "diagnostico", "alto", "sesión 2: lee diagnostico.md y el código, escribe los hallazgos y el "
                    "plan de mejoras; termina con el comando para que decidas", plan)
    session4 = chat(resume, "economico", "bajo", "sesión 4: compara, escribe la lectura y el resumen y genera el reporte", plan)
    triage = plan.get("profundidad") == "triage"
    # Una mejora aplicada después de medir "después" deja esa fase vieja: hay que medirla de nuevo (--rehacer).
    measured = phases.get("despues", {}).get("fecha", "")
    stale = "despues" in phases and any(m.get("estado") == "aplicada" and m.get("aplicada_en", "") > measured for m in mejoras)
    report = next((state.parent / n for n in ("reporte-final.html", "reporte-final.md", "reporte.html", "reporte.md")
                   if (state.parent / n).is_file()), state.parent / "reporte-final.md")
    if report.is_file() and "aprobada" not in estados and not stale:
        return "investigación cerrada", [{"tipo": "archivo", "texto": str(report), "que": "el reporte final; se puede compartir"}]
    initial = state.parent / ("reporte-inicial.html" if (state.parent / "reporte-inicial.html").is_file() else "reporte-inicial.md")
    if triage and initial.is_file():
        return "triage cerrado", [{"tipo": "archivo", "texto": str(initial),
                                   "que": "el reporte del triage (diagnóstico y plan, sin línea base ni medición después); "
                                          "para aplicar mejoras, cambia profundidad a riguroso y mide control y después"}]
    if "aprobada" in estados:
        first = next(m for m in mejoras if m.get("estado") == "aprobada")
        return "sesión 3 · %s" % first["id"], [
            chat("%s: sesión 3, aplica %s" % (resume, first["id"]), "intermedio", "medio",
                 "sesión 3: aplica %s%s con su test y el DoD, propone el commit y marca la mejora aplicada" % (
                     first["id"], " (a prueba: la medición de después confirma o refuta su hipótesis)"
                     if first.get("a_prueba") else ""), plan)]
    if "despues" in phases and not stale:
        return "sesión 4 · cierre", [session4]
    if "aplicada" in estados and "aprobada" not in estados:
        return "medición después (sin chat)", [
            terminal(install_command(plan, root), "compila e instala el build de profiling con la mejora",
                     "espera; si la mejora migra datos, abre la app una vez antes de medir"),
            terminal(command(*(capture + ["--fase", "despues", "--corridas", runs] + (["--rehacer"] if stale else []))),
                     "mide la fase después con las mismas condiciones que antes"
                     + (" (de nuevo: hay una mejora aplicada después de la medición anterior)" if stale else ""), you_run),
            session4]
    if "propuesta" in estados:
        ids = ",".join(m["id"] for m in mejoras if m.get("estado", "propuesta") == "propuesta")
        return "decisión del usuario (sin chat)", [
            terminal(command("decidir", "--carpeta", folder, "--aprobar", ids, "--descartar", "-", "--pendiente", "-"),
                     "registra qué mejoras se aplican y da el chat de la sesión 3",
                     "deja en cada lista los ids que correspondan (- es ninguno); mira las mejoras en estado.md")]
    if mejoras:
        return "sesión 4 · cierre sin mejoras aplicadas", [session4]
    if initial.is_file():
        # La sesión 2 ya entregó su reporte y no propuso mejoras: no se repite. Queda el cierre corto y, si el
        # diagnóstico dejó una captura pendiente en estado.md, esa captura como comando.
        steps = []
        for pending in pending_captures(state):
            own = re.search(r"(?:^|\s)(?:\S*perf\.py\s+)?((?:capturar|consulta|diagnostico)\s.*)$", pending)
            if pending.startswith("cd "):
                pass  # ya es un comando completo
            elif own:  # un comando de perf.py, con o sin "python3 -I .../perf.py" delante: se arma con la ruta de este script
                pending = command(own.group(1))
            else:
                pending = "cd %s && %s" % (root, pending)
            steps.append(terminal(pending, "la captura que el diagnóstico dejó pendiente (opcional: cierra un pendiente)",
                                  "córrela solo si quieres cerrar ese pendiente antes de terminar; lo que salga se "
                                  "analiza en un chat aparte (prompts.md · Una pregunta sobre una traza)"))
        steps.append(chat("%s: cierra la investigación sin fase después" % resume, "economico", "bajo",
                          "sesión 4 corta: no hay mejoras que medir; escribe el resumen con el estado inicial y genera "
                          "el reporte final", plan))
        return "sesión 4 · cierre sin mejoras", steps
    if (state.parent / "diagnostico.md").is_file():
        return "sesión 2 · diagnóstico", [session2]
    steps = []
    if triage:
        you_run = you_run.replace(str(runs), "3")
        runs = 3
    if "antes" not in phases:
        if not any((state.parent / "prueba").glob("*.perfetto-trace*")):
            steps.append(terminal(command(*(capture + ["--prueba"])),
                                  "una corrida de prueba: imprime las métricas y las marcas, sin guardar nada",
                                  "lo mismo que en una corrida, una sola vez; revisa que estén las marcas del plan"))
        steps.append(terminal(command(*(capture + ["--fase", "antes", "--corridas", runs])),
                              "mide el estado inicial" + (" (triage: 3 corridas, sin control)" if triage else ""), you_run))
    if "control" not in phases and not triage:
        steps.append(terminal(command(*(capture + ["--fase", "control", "--corridas", runs])),
                              "repite la medición sin cambiar nada: mide el ruido", you_run))
    steps += [terminal(command("diagnostico", "--carpeta", folder),
                       "corre las consultas de diagnóstico sobre las trazas y deja diagnostico.md", "espera"), session2]
    return ("medición antes (sin chat)" if triage and "antes" not in phases else
            "medición antes y control (sin chat)" if "antes" not in phases else
            "control y diagnóstico (sin chat)" if "control" not in phases and not triage else "diagnóstico (sin chat)"), steps


PENDING_CAPTURE = re.compile(r"captura pendiente[^`\n]*`([^`\n]+)`", re.I)


def pending_captures(state):
    """Los comandos que la sección Pendientes de estado.md deja como "Captura pendiente: `<comando>`"."""
    try:
        _, sections = state_sections(pathlib.Path(state).read_text(encoding="utf-8"))
    except OSError:
        return []
    text = next((body for title, body in sections.items() if title.startswith("pendientes")), "")
    return [found.strip() for found in PENDING_CAPTURE.findall(without_placeholders(text)) if "<" not in found]


def code_span(text):
    """El texto como código en línea de markdown, también si trae un acento grave."""
    return "`` %s ``" % text if "`" in text else "`%s`" % text


def route_block(plan, root):
    """La sección "Cómo se recorre" de estado.md: 'preparar' y 'recorrido' de cada flujo y el comando para verlos
    correr a mano, fuera de una captura."""
    lines = []
    for name, flow in plan["flujos"].items():
        prepare = (flow.get("preparar") or "").strip()
        route = flow.get("recorrido") or "manual"
        lines.append("**%s**" % name)
        lines.append("- `preparar` (antes de cada corrida, fuera de la traza): %s" % (code_span(prepare) if prepare else "no tiene"))
        if startup_spec(flow):
            lines.append("- `recorrido`: arranque en frío; `perf.py` detiene la app y la abre (`am start -W`)")
        elif route == "manual":
            lines.append("- `recorrido`: manual; lo recorres tú en el dispositivo, con los pasos del plan")
        else:
            lines.append("- `recorrido` (el tramo medido): %s" % code_span(route))
            lines.append("- Para verlo correr a mano, sin medir: %s" % code_span(
                "cd %s && %s" % (root, " && ".join(part for part in (prepare, route) if part))))
        if flow.get("requiere_env"):
            lines.append("- Variables de entorno que necesita (expórtalas antes): %s"
                         % ", ".join("`%s`" % v for v in flow["requiere_env"]))
    lines.append("")
    lines.append("Los archivos del recorrido (`recorrido.sh`, `preparar.sh`, `preparar.yaml`) viven en esta carpeta, que git "
                 "ignora y que se borra al limpiar: si los vas a reutilizar, archívalos fuera de `reports/`.")
    return "\n".join(lines)


def render_steps(steps, markdown):
    """Los pasos como texto: para la terminal (markdown=False) o para estado.md."""
    code = (lambda s: "`%s`" % s) if markdown else (lambda s: s)
    lines = []
    for i, step in enumerate(steps, start=1):
        if step["tipo"] == "terminal":
            lines.append("%d. **Terminal** (sin chat) · %s" % (i, step["que"]) if markdown else
                         "%d. Terminal (sin chat) · %s" % (i, step["que"]))
            lines.append("   %s" % code(step["texto"]))
            lines.append("   Tú: %s." % step["tu"])
        elif step["tipo"] == "chat":
            lines.append("%d. **Chat nuevo** · Modelo: %s · Esfuerzo: %s" % (i, step["modelo"], step["esfuerzo"]) if markdown
                         else "%d. Chat nuevo · Modelo: %s · Esfuerzo: %s" % (i, step["modelo"], step["esfuerzo"]))
            lines.append("   Texto: \"%s\"" % step["texto"])
            lines.append("   Qué hace: %s." % step["que"])
        else:
            lines.append("%d. %s: %s" % (i, step["que"][0].upper() + step["que"][1:], step["texto"]))
    return lines


def cost_command(folder):
    """El comando para anotar el costo de un chat, con la carpeta relativa a la raíz del proyecto."""
    folder = pathlib.Path(folder).resolve()
    root = project_root(folder).resolve()
    try:
        folder = folder.relative_to(root)
    except ValueError:
        pass
    return ("cd %s && python3 -I %s consumo --carpeta %s --sesion \"<sesión>\" --costo \"<lo que muestre tu "
            "herramienta>\" --modelo \"<modelo>\"" % (root, HERE / "perf.py", folder))


def write_next(folder, title, steps):
    """Reescribe "## Siguiente paso" de estado.md con lo que dice next_steps."""
    state = pathlib.Path(folder) / "estado.md"
    if not state.is_file():
        return
    body = "\n".join(["- **Paso:** %s" % title, "- **En orden, uno a la vez:**"]
                     + ["  " + line for line in render_steps(steps, markdown=True)]
                     + ["- **Costo de cada chat** (terminal, al cerrarlo): `%s`" % cost_command(folder),
                        "- _Lo escribe `perf.py siguiente`: si algo cambió, vuelve a correrlo._", ""])
    text = state.read_text(encoding="utf-8")
    new, count = re.subn(r"(## Siguiente paso\n\n).*?(?=\n## )", lambda m: m.group(1) + body, text, count=1, flags=re.S)
    if count:
        state.write_text(new, encoding="utf-8")


def print_next(folder, plan, flow=None):
    title, steps = next_steps(pathlib.Path(folder), plan, flow)
    print("Siguiente · %s (también en estado.md):" % title)
    for line in render_steps(steps, markdown=False):
        print("  " + line)
    if any(step["tipo"] == "chat" for step in steps):
        print("  Al cerrar cada chat, anota su costo (terminal): %s" % cost_command(folder))
    write_next(folder, title, steps)
    update_block(folder, "recorrido", route_block(plan, project_root(pathlib.Path(folder).resolve()).resolve()))


def cmd_siguiente(args):
    folder = pathlib.Path(args.carpeta)
    plan = load_plan(folder / "plan.json")
    state = folder / "estado.md"
    if state.is_file():
        # La Ficha se completa en la sesión 1; el Resumen y los Hallazgos, desde que la sesión 2 entrega su reporte.
        # Con mejoras aprobadas o aplicadas (sesión 3 y medición después), el resumen que falta es el del cierre: no
        # se avisa todavía.
        delivered = any((folder / name).is_file() for name in ("reporte-inicial.md", "reporte-final.md", "reporte.md"))
        in_progress = any(m.get("estado") in ("aprobada", "aplicada") for m in plan.get("mejoras", []))
        warn_unfilled(folder, state_sections(state.read_text(encoding="utf-8"))[1], findings=delivered and not in_progress)
    print_next(folder, plan, args.flujo)


def cmd_consumo(args):
    folder = pathlib.Path(args.carpeta)
    state = folder / "estado.md"
    if not state.is_file():
        raise PerfError("no existe %s" % state)
    text = state.read_text(encoding="utf-8")
    if any("<" in str(v) for v in (args.sesion, args.costo, args.modelo, args.pasos) if v):
        raise PerfError("reemplaza los <...> por el valor real antes de anotar (por ejemplo --costo \"1.05 USD\")")
    row = "| %s | %s | %s | %s |" % (args.sesion, args.modelo or "—", args.costo, args.pasos or "—")

    def append(match):
        body = [line for line in match.group(2).rstrip("\n").split("\n") if line.strip() and "<" not in line]
        return match.group(1) + "\n".join(body + [row]) + "\n"

    new, count = re.subn(r"(## Consumo\n\n)(.*?)(?=\n## |\Z)", append, text, count=1, flags=re.S)
    if not count:
        raise PerfError("%s no tiene la sección '## Consumo'" % state)
    state.write_text(new, encoding="utf-8")
    print("✔ Consumo: %s" % row)


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
            if choices[item["id"]] == "aplicada":
                item["aplicada_en"] = datetime.datetime.now().isoformat(timespec="seconds")
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
    update_block(folder, "mejoras", plan_table_md(plan, rows))
    print("✔ %s" % line[2:])
    print_next(folder, plan)


def cmd_capturar(args, plan=None):
    if args.plan:
        plan = load_plan(args.plan)
        folder = pathlib.Path(args.plan).parent
    elif args.prueba and args.paquete and args.carpeta:
        plan = plan or {"paquete": args.paquete, "flujos": {args.flujo or "humo": {}}}
        folder = pathlib.Path(args.carpeta)
    else:
        raise PerfError("usa --plan <carpeta>/plan.json (o --prueba con --paquete y --carpeta)")
    flow_name = args.flujo or ("humo" if args.prueba and not args.plan else None)
    if flow_name is None and len(plan["flujos"]) == 1:
        flow_name = next(iter(plan["flujos"]))
    if flow_name not in plan["flujos"]:
        raise PerfError("el flujo '%s' no está en el plan (flujos: %s)" % (flow_name, ", ".join(plan["flujos"])))
    flow = plan["flujos"][flow_name]
    secret_names = flow.get("requiere_env") or []
    if missing_env(secret_names):
        raise Precondicion("faltan variables de entorno que el flujo '%s' necesita (requiere_env): %s. Expórtalas en esta "
                           "terminal antes de correr el comando; si lo corre un agente, antes de abrir el agente (solo ve "
                           "las de la terminal donde se abrió)" % (flow_name, ", ".join(missing_env(secret_names))))
    phase = "antes" if args.prueba else normalize_phase(args.fase)
    package = plan["paquete"]
    hz = args.hz or (plan.get("hz") if isinstance(plan.get("hz"), int) else None)
    startup = None if args.recorrido else startup_spec(flow)
    recorrido = args.recorrido or (flow.get("recorrido") if not startup else None) or "manual"
    tp = find_tp(args.tp)
    serial = select_device(args.serial or plan.get("serial"))
    adb = Adb(serial)
    sdk, warnings, build = preflight(adb, package, args.forzar)
    environment = device_environment(adb)
    warnings += environment_warnings(environment)
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
    input_glob = plan.get("input_slices") or INPUT_SLICES
    queries = [("metricas", fill_sql((ASSETS / "queries" / "metricas.sql").read_text(encoding="utf-8"), package,
                                     {"INPUT_GLOB": input_glob}))]
    queries += custom_queries(flow, folder, package)
    csv_path = folder / "metricas.csv"
    out_dir = folder / ("prueba" if args.prueba else phase)
    out_dir.mkdir(parents=True, exist_ok=True)
    known = known_metrics(csv_path, flow_name)
    start_screen = None if startup else flow.get("inicio")
    prepare_command = (args.preparar or flow.get("preparar") or "").strip() or None

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

    prepare_shown = []

    def prepare():
        """Deja la app en el punto de partida antes de cada corrida: el comando 'preparar' del plan o, si la app no
        está al frente (la compilación de ART o una corrida anterior la cerraron), la relanza."""
        if startup:
            return
        if prepare_command:
            code, tail, log = run_prepare(prepare_command, folder, secret_names)
            if code != 0:
                if not prepare_shown:  # una vez por captura: las corridas siguientes fallan igual
                    prepare_shown.append(True)
                    if tail:
                        print("✖ 'preparar' falló (código %d). Sus últimas líneas, con los valores de requiere_env "
                              "enmascarados (más en %s):" % (code, log))
                        print("\n".join("    " + line for line in tail))
                    else:
                        print("✖ 'preparar' falló (código %d) sin dejar salida: si el comando la manda a /dev/null (o el "
                              "flujo no declara requiere_env, y entonces solo se lee su salida de error), córrelo a "
                              "mano en tu terminal para ver el error" % code)
                raise Precondicion("'preparar' terminó con código %d" % code)
        elif start_screen and start_screen not in resumed_activity(adb) and recorrido != "manual":
            component = launcher_activity(adb, package)
            if component:
                adb.shell("am start -n %s" % component)
                settle(3)
        check_start()

    if not startup and recorrido != "manual" and not prepare_command and not args.prueba:
        print("⚠ el flujo no tiene 'preparar': entre corridas la app queda donde terminó el recorrido. Si la app es de "
              "una sola actividad, 'inicio' no distingue pantallas: pon en el plan un comando que la devuelva al inicio.")
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
            try:
                prepare()
            except Precondicion as error:
                if not prepare_command:
                    raise
                print("⚠ calentamiento: %s" % error)
                continue
            reason = drive(recorrido, "calentamiento %d/%d (no cuenta)" % (i + 1, warmups))
        if reason:
            print("⚠ calentamiento: %s" % reason)

    target = 1 if args.prueba else args.corridas
    valid, attempts, run_hz = 0, 0, []
    consecutive, last_invalid = 0, ""
    n = next_run_number(csv_path, phase, flow_name) if not args.prueba else 1
    while valid < target:
        if consecutive >= MAX_CONSECUTIVE_INVALID:
            raise CorridasInsuficientes("%d corridas inválidas seguidas (última: %s): algo del entorno falla, no la "
                                        "suerte. Revisa el recorrido, 'preparar' o el backend y vuelve a correr; las "
                                        "%d válidas quedan guardadas" % (consecutive, last_invalid, valid))
        if attempts >= max_attempts(target):
            raise CorridasInsuficientes("solo %d de %d corridas válidas en %d intentos: revisa las condiciones"
                                        % (valid, target, attempts))
        attempts += 1
        try:
            prepare()
        except Precondicion as error:
            if not prepare_command or args.prueba:
                raise
            # 'preparar' falló (un login que no entró, un backend caído): la corrida no vale, se repite y cuenta
            # para el tope de inválidas seguidas.
            consecutive, last_invalid = consecutive + 1, str(error)
            print("✖ corrida %d inválida: %s (se repite)" % (n, error))
            n += 1
            continue
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
            if not invalid and not args.prueba:
                # Sin la ventana o sin una métrica principal, el recorrido no llegó a donde debía (un tap que no
                # navegó, la pantalla que no cargó a tiempo): la corrida no vale y se repite.
                principales = plan.get("principales") or []
                measured = {m[0] for m in metrics}
                absent = [m for m in segment_metric_names(flow) if m in principales and m not in measured]
                unmarked = [m for m in absent if "tramo %s" % m.rsplit(" ", 1)[0] in info.get("faltantes", [])]
                essential = [m for m in info.get("faltantes", []) if m == "ventana" or m in principales] + unmarked
                if essential:
                    invalid = "sin marcas para %s: el recorrido no completó el flujo" % ", ".join(essential)
                elif absent:  # el tramo tiene sus marcas pero ningún frame: no hay porcentaje ni percentil que calcular
                    invalid = ("sin frames en el tramo para %s: en un tramo sin frames (o sin FrameTimeline, Android 11 o "
                               "anterior) usa '<tramo> hilo_max_ms' como principal" % ", ".join(absent))
            if not invalid and plan.get("hilos_ajenos"):
                window = info.get("ventana_ns")
                foreign_sql = fill_sql((ASSETS / "queries" / "hilos_ajenos.sql").read_text(encoding="utf-8"), package,
                                       {"DESDE": window[0] if window else 0, "HASTA": window[1] if window else 4 * 10 ** 18})
                metrics += with_families(foreign_thread_metrics(run_tp_batch(tp, local, [("ajenos", foreign_sql)])["ajenos"],
                                                                plan["hilos_ajenos"], known), flow.get("familias"))
            names = {m[0] for m in metrics}
            metrics += [m for m in with_families(extra, flow.get("familias")) if m[0] not in names]
            for name, _ in queries[1:]:
                for header, body in results[name]:
                    metrics += sql_metrics(header, body, name)
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
            print("Secciones propias: %s" % sections_summary(info.get("nombres", {})))
            raise CorridasInsuficientes("la corrida de prueba fue inválida: %s (traza en %s)" % (invalid, local))
        if invalid:
            target_name = local.with_name("%s_%d_invalida_%s.perfetto-trace" % (flow_name, n, slug(invalid)))
            local.rename(target_name)
            if not args.sin_comprimir:
                compress(target_name)
            print("✖ corrida %d inválida: %s (traza guardada para auditoría)" % (n, invalid))
            consecutive, last_invalid = consecutive + 1, invalid
            n += 1
            continue
        consecutive = 0
        saved = local if args.sin_comprimir else compress(local)
        if args.prueba:
            print(run_line("de prueba", size_mb, metrics))
            print(markdown_table(["Métrica", "Valor", "Familia"],
                                 [[m[0], fmt(m[1], m[2]), m[3]] for m in metrics[:MAX_ROWS]]))
            print("Secciones propias: %s" % sections_summary(info["nombres"]))
            print("Tasa de refresco: %s Hz (%s)" % (
                info["hz"], "plan" if hz else "traza" if info.get("hz_traza") else "60 por defecto"))
            rate_warning = hz_warning(hz, [info.get("hz_traza")])
            if rate_warning:
                print("⚠ " + rate_warning)
            if info.get("faltantes"):
                print("⚠ Sin marcas en la traza para: %s" % ", ".join(info["faltantes"]))
            for name, count in sorted(info.get("con_input", {}).items()):
                print("⚠ %s incluye pasos del recorrido (%d eventos de input entre sus marcas): mide el script, no la "
                      "app. Acórtala a un solo salto, de la marca de la acción a la de su contenido" % (name, count))
            if flow.get("metricas_usuario") and not startup and not info.get("input"):
                print("  Sin slices de input ('%s') en la traza: si el recorrido da toques, no se pudo comprobar si una "
                      "métrica de usuario los incluye (el nombre cambia con la versión de Android: 'input_slices' en el "
                      "plan)" % input_glob)
            for name, count in sorted(info.get("marcas_repetidas", {}).items()):
                print("⚠ '%s' salió %d veces en una misma carga (sin navegación ni otra carga entre ellas): el gancho que la emite se "
                      "llama más de una vez por carga y una métrica con 'cual: ultima' terminaría en la última. Déjalo "
                      "en una vez por carga (setup.md · Contenido visible)" % (name, count))
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
        run_hz.append(info.get("hz_traza"))
        valid += 1
        n += 1
    seen_hz = {h for h in run_hz if h}
    record = {"fecha": datetime.datetime.now().replace(microsecond=0).isoformat(), "commit": commit, "sucio": dirty,
              "corridas": valid, "hz": hz or min(seen_hz, default=None), "compilacion": compilation}
    if seen_hz:
        record["hz_corridas"] = run_hz
    rate_warning = hz_warning(hz, seen_hz)
    if rate_warning:
        record["avisos"] = [rate_warning]
        print("⚠ " + rate_warning)
    if environment["emulador"] or environment["software"]:
        record["entorno"] = environment
    record.update(build)
    write_phase(folder, phase, record, flow_name)
    rows = read_rows(csv_path)
    table, hidden = summary_rows(rows, plan, phases=(phase,), flows=(flow_name,), trust=frames_trust(folder))
    print(markdown_table(SUMMARY_HEADERS, table[:MAX_ROWS]))
    write_summary(csv_path, rows, plan)
    print("✔ Listo. No hace falta pegar esta salida en el chat: quedó en metricas.csv, resumen.md y estado.md.")
    if args.plan:
        print_next(folder, plan, flow_name)


def phase_warnings(folder):
    """Los avisos que las capturas dejaron en fases.json, como "fase: aviso"."""
    phases = read_phases(folder)
    return ["%s: %s" % (phase, warning) for phase in FASES for warning in (phases.get(phase) or {}).get("avisos") or []]


def write_summary(csv_path, rows, plan):
    trust = frames_trust(pathlib.Path(csv_path).parent)
    full, _ = summary_rows(rows, plan, everything=True, trust=trust)
    pathlib.Path(csv_path).with_name("resumen.md").write_text(
        "# Resumen de métricas\n\n" + markdown_table(SUMMARY_HEADERS, full) + "\n", encoding="utf-8")
    compact, hidden = summary_rows(rows, plan, trust=trust)
    block = markdown_table(SUMMARY_HEADERS, compact[:MAX_ROWS])
    if hidden or len(compact) > MAX_ROWS:
        block += "\n\nDetalle completo en `resumen.md`."
    notes = phase_warnings(pathlib.Path(csv_path).parent)
    if notes:
        block += "\n\n" + "\n".join("> ⚠ %s" % note for note in notes)
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
    table, hidden = summary_rows(rows, plan, everything=args.todo, trust=frames_trust(pathlib.Path(args.csv).parent))
    print(markdown_table(SUMMARY_HEADERS, table[:MAX_ROWS] if not args.todo else table))
    if hidden or (not args.todo and len(table) > MAX_ROWS):
        print("… %d métricas más en resumen.md (o usa --todo)" % (hidden + max(0, len(table) - MAX_ROWS)))
    flagged = [r for r in table if r[-1] != "—"]
    if flagged:
        print("⚠ %d con avisos: con 'pocas corridas' suma corridas; con 'inestable' (CV > %s %%) estabiliza las "
              "condiciones antes de comparar." % (len(flagged), fmt(CV_MAX)))
    write_summary(args.csv, rows, plan)


def definition_notes(results):
    """Métricas de usuario cuya marca de fin (una llamada) dejó de ser la última llamada en alguna fase: la mejora
    reordenó las llamadas y la métrica ya no mide lo mismo."""
    by_key = {(r["flujo"], r["metrica"]): r for r in results}
    notes = []
    for (flow, metric), r in by_key.items():
        last = by_key.get((flow, metric + " hasta_ultima_red_ms"))
        if not last or r["veredicto"] in ("informativa", "sin cambio"):
            continue
        for phase in ("antes", "despues"):
            gap = last[phase]["mediana"] - r[phase]["mediana"]
            if gap > max(r[phase]["mediana"] * 0.1, 5):
                notes.append("%s · %s: en %s la marca de fin termina %s antes que la última llamada de red. La métrica "
                             "cambió de definición y su veredicto no prueba la mejora: usa una marca de contenido visible "
                             "(PerfHooks.mark) o termina en la última llamada." % (flow, metric, phase, fmt(gap, "ms")))
                break
    return notes


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
    notes += phase_warnings(folder)
    level, motive = frames_trust(folder)
    if level != "ok":
        notes.append("las fases se midieron en un entorno con frames %s (%s): %s" % (
            "no confiables" if level == "no" else "orientativos", motive,
            "no uses jank_* ni frame_* para decidir; repite en un dispositivo físico o con -gpu host" if level == "no"
            else "valen los conteos y las fugas; para decidir con frames, usa un dispositivo físico"))
    return table, notes


def logrado_rows(plan, results):
    by_metric = {(r["flujo"], r["metrica"]): r for r in results}
    default_flow = next(iter(plan.get("flujos") or {"": None}))
    out = []
    for item in plan.get("mejoras", []):
        r = by_metric.get((item.get("flujo") or default_flow, item.get("metrica")))
        unit = r["unidad"] if r else ""
        out.append([item["id"], improvement_title(item), item.get("metrica", "—"),
                    fmt(r["antes"]["mediana"], unit) if r else "—", item.get("esperado", "—"),
                    fmt(r["despues"]["mediana"], unit) if r else "—", fmt_pct(r["delta_pct"]) if r else "—",
                    r["veredicto"] if r else "—", item.get("estado", "—"), improvement_result(item, r)])
    return out


def improvement_result(item, r):
    """✔ funcionó / ✖ no funcionó / — según el estado de la mejora y el veredicto de su métrica. En una mejora a prueba
    (a_prueba), la medición de después confirma o refuta su hipótesis."""
    trial = bool(item.get("a_prueba"))
    if item.get("estado") != "aplicada":
        return "— no aplicada"
    if r is None:
        return "— sin medir"
    if r["veredicto"] == "mejora":
        return "✔ hipótesis confirmada" if trial else "✔ funcionó"
    if r["veredicto"] == "regresión":
        return "✖ hipótesis refutada (empeoró)" if trial else "✖ empeoró"
    if r["veredicto"] in ("informativa", "no comparable", "no confiable"):
        return "— sin veredicto"
    return "✖ hipótesis refutada" if trial else "✖ no funcionó"


def improvement_title(item):
    return item["titulo"] + (" (a prueba)" if item.get("a_prueba") else "")


def trial_md(plan):
    """Las mejoras a prueba del plan, con su hipótesis y lo que la confirma: van debajo de la tabla del plan."""
    items = [m for m in plan.get("mejoras", []) if m.get("a_prueba")]
    if not items:
        return ""
    lines = ["", "", "**Mejoras a prueba** (la causa no está probada: el cambio se aplica y la medición de después confirma o "
                 "refuta la hipótesis):", ""]
    lines += ["- **%s** · hipótesis: %s · se confirma si `%s` mejora (esperado: %s)" % (
        m["id"], m["hipotesis"], m["metrica"], m["esperado"]) for m in items]
    return "\n".join(lines)


LOGRADO_HEADERS = ["#", "Mejora", "Métrica", "Antes", "Esperado", "Después", "Δ %", "Veredicto", "Estado", "Resultado"]


def cmd_comparar(args):
    rows = read_rows(args.csv)
    plan = load_plan_beside(args.csv)
    folder = pathlib.Path(args.csv).parent
    trust = frames_trust(folder)
    results, unmatched = compare(rows, trust=trust)
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
    if counts.get("no confiable"):
        print("no confiable = los frames se midieron con render por software (emulador sin GPU del host): no dicen cómo "
              "se ve en un dispositivo real.")
    if len(chosen) < len(results):
        print("… %d métricas sin cambios relevantes en comparacion.md" % (len(results) - len(chosen)))
    for u in unmatched[:5]:
        print("⚠ Sin comparar: %s · %s (solo en: %s)" % (u["flujo"], u["metrica"], ", ".join(u["fases"])))
    regressions = [r for r in results if r["veredicto"] == "regresión"]
    if regressions:
        print("✖ %d regresiones: repórtalas aunque no sean métricas principales." % len(regressions))
    builds, notes = builds_table(folder)
    notes += jit_note(rows) + definition_notes(results)
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

DEVICE_PLACEHOLDER = "<modelo · Android · Hz fijos>"
UNFILLED = "sin completar"
TEMPLATE_MARKER = re.compile(r"<[^<>\n!/][^<>\n]*>")
# Marcadores <…> de la plantilla de estado.md de versiones anteriores que ya no están en la actual.
LEGACY_MARKERS = (
    "<modelo · Android · Hz>",
    "<3 a 5 líneas: estado inicial → estado final con las métricas principales, la causa en una frase y qué depende del "
    "backend>",
    '<qué dice cada métrica principal, cada regresión y cada "no comparable"; la evidencia de consultas, rotulada "sin '
    'veredicto estadístico">',
)
# Textos de relleno que esa plantilla traía sin <>, y <alcance>, que deja `nuevo` sin --alcance: son "sin completar"
# solo si son la celda o la línea entera (dentro de un texto más largo pueden ser contenido real).
WHOLE_PLACEHOLDERS = (
    "<alcance>",
    "las de `principales` en plan.json, y el objetivo",
    "build de profiling (R8, no debuggable, profileable) · backend real o mocks",
    "guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage",
    "UI · asincronía · listas · red",
    "- `ruta/al/Archivo.kt:línea`: qué es, en una línea.",
    "- **M1** · `archivos` · test que la fija · DoD · commit propuesto: `perf(<scope>): ...`",
    "- **H3** · causa verificada · `archivo:línea` · cambio propuesto · test · métrica que lo mide · commit sugerido",
)
_PLACEHOLDERS = []


def placeholders():
    """Los marcadores <…> de relleno de la plantilla de estado.md: los de más de una palabra (uno de una sola, como
    <carpeta>, puede ser texto legítimo) y los de versiones anteriores."""
    if not _PLACEHOLDERS:
        template = (ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8")
        found = {m for m in TEMPLATE_MARKER.findall(template) if " " in m}
        _PLACEHOLDERS.extend(sorted(found | set(LEGACY_MARKERS) | {DEVICE_PLACEHOLDER}, key=len, reverse=True))
    return _PLACEHOLDERS


def has_placeholder(text):
    """True si el texto (una línea o una celda) sigue con el relleno de la plantilla."""
    if any(marker in text for marker in placeholders()):
        return True
    pieces = {text.strip()} | {cell.strip() for cell in text.split("|")}
    return any(whole in pieces for whole in WHOLE_PLACEHOLDERS)


def without_placeholders(text):
    """El texto de una sección sin las líneas que siguen siendo relleno de la plantilla."""
    return "\n".join(line for line in text.splitlines() if not has_placeholder(line)).strip()


def unfilled_parts(sections, findings=False):
    """Lo que estado.md todavía tiene sin completar, para avisarlo: filas de la Ficha con el texto de la plantilla y,
    con `findings` (desde que existe el diagnóstico), el Resumen y los Hallazgos."""
    def pick(*names):
        return next((sections[k] for k in sections for n in names if k.startswith(n)), None)

    out = []
    ficha = pick("ficha")
    if ficha:
        rows = [row[0] for row in parse_table(ficha)[1] if len(row) > 1 and row[0].strip().lower().startswith(FICHA_REPORTE)
                and has_placeholder(" | ".join(row[1:]))]
        if rows:
            out.append("Ficha (%s)" % ", ".join(rows))
    if findings:
        summary = pick("resumen ejecutivo", "resumen")
        if summary is not None and not without_placeholders(summary):
            out.append("Resumen ejecutivo (de 3 a 5 líneas)")
        table = pick("hallazgos")
        if table is not None:
            rows = parse_table(table)[1]
            if not rows:
                out.append("Hallazgos (la tabla está vacía)")
            elif any(has_placeholder(" | ".join(row)) for row in rows):
                out.append("Hallazgos (%s)" % ", ".join(row[0] for row in rows if has_placeholder(" | ".join(row))))
    return out


def warn_unfilled(folder, sections, findings):
    parts = unfilled_parts(sections, findings)
    if parts:
        print("⚠ %s tiene partes sin completar: %s. El reporte no las publica (las omite o dice \"%s\"): complétalas y "
              "vuelve a generar." % (pathlib.Path(folder) / "estado.md", "; ".join(parts), UNFILLED))
    return parts

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
            cells = line.strip().strip("|").split("|")
            first = cells[0].strip().lower()
            if first in ("campo", "") or re.fullmatch(r":?-{3,}:?", first) or first.startswith(FICHA_REPORTE):
                if has_placeholder(line):  # la fila sigue con el texto de la plantilla: no se publica
                    line = "| %s | %s |" % (cells[0].strip(), UNFILLED)
                out.append(line)
        elif in_table:
            break
    return "\n".join(out) if len(out) > 2 else ""


def inline_md(text):
    text = e(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)


NUMERIC_CELL = re.compile(r"[-+−]?[\d.,]+ ?[a-zA-Z%]{0,3}( \([-+−]?[\d.,]+ ?%?\))?( ?[–/] ?[-+−]?[\d.,]+ ?[a-zA-Z%]{0,3})?|—")


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
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            out.append('<p class="hint">%s</p>' % inline_md(" ".join(quote)))
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
            body = "".join("<tr>%s</tr>" % "".join(
                '<td class="num">%s</td>' % inline_md(c) if NUMERIC_CELL.fullmatch(c) else "<td>%s</td>" % inline_md(c)
                for c in r) for r in rows[1:])
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
            while i < len(lines) and lines[i].strip() and not re.match(r"\s*(#|>|\||```|[-*]\s|\d+\.\s)", lines[i]):
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


def initial_md(rows, plan, trust=("ok", "")):
    """Estado inicial de las métricas principales (antes y, si existe, el ruido del bloque de control)."""
    principales = plan.get("principales") or []
    note = frames_note(trust)
    table = []
    for (flow, metric), entry in sorted(group(rows).items(), key=lambda kv: (kv[0][0], priority(kv[0][1], plan))):
        if metric not in principales or "antes" not in entry["fases"]:
            continue
        s = describe(entry["fases"]["antes"])
        control = entry["fases"].get("control")
        noise = abs(statistics.median(control) - s["mediana"]) / abs(s["mediana"]) * 100 \
            if control and s["mediana"] else None
        table.append([flow, metric, FAMILY_LABEL.get(entry["familia"], entry["familia"]), fmt(s["mediana"], entry["unidad"]),
                      fmt(s["p90"], entry["unidad"]), "%s – %s" % (fmt(s["min"]), fmt(s["max"])), s["n"],
                      fmt_pct(noise, signed=False),
                      human_warnings(s["avisos"] + ([note] if note and frame_metric(metric) else []), s["cv"], s["n"])])
    if not table:
        return ""
    intro = ("> Lo que midió la app antes de cambiar nada, por métrica principal. La **mediana** es el número que se "
             "compara después; el **ruido de medición** es cuánto cambió la métrica al medir dos veces sin tocar nada.\n\n")
    return intro + markdown_table(["Flujo", "Métrica", "Depende de", "Mediana", "P90", "Mín – máx", "Corridas",
                                   "Ruido de medición", "Avisos"], table)


def plan_rows(plan, rows):
    medians = {(k[0], k[1]): (statistics.median(v["fases"]["antes"]), v["unidad"])
               for k, v in group(rows).items() if "antes" in v["fases"]}
    default_flow = next(iter(plan.get("flujos") or {"": None}))
    out = []
    for item in plan.get("mejoras", []):
        before = medians.get((item.get("flujo") or default_flow, item.get("metrica")))
        out.append([item["id"], improvement_title(item), item.get("hallazgo", "—"), item.get("metrica", "—"),
                    fmt(before[0], before[1]) if before else "—", item.get("esperado", "—"),
                    item.get("prioridad", "—"), item.get("esfuerzo", "—"), item.get("riesgo", "—"),
                    item.get("estado", "propuesta")])
    return out


PLAN_HEADERS = ["#", "Mejora", "Hallazgo", "Métrica", "Antes", "Esperado", "Prioridad", "Esfuerzo", "Riesgo", "Estado"]


def plan_table_md(plan, rows):
    return markdown_table(PLAN_HEADERS, plan_rows(plan, rows)) + trial_md(plan)


def parse_table(md):
    """(encabezados, filas) de la primera tabla markdown del texto; ([], []) si no hay."""
    rows = []
    for line in md.splitlines():
        if not line.lstrip().startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        rows.append([c.replace("\\|", "|") for c in cells])
    return (rows[0], rows[1:]) if rows else ([], [])


def finding_outcome(finding_id, tipo, plan, results=None):
    """Qué pasa con un hallazgo: a qué mejora dio lugar y, con resultados, si esa mejora funcionó."""
    mejoras = [m for m in plan.get("mejoras", []) if m.get("hallazgo") == finding_id]
    low = tipo.lower()
    if mejoras:
        parts = []
        for m in mejoras:
            estado = m.get("estado", "propuesta")
            text = "%s (%s)" % (m["id"], STATE_TEXT.get(estado, estado).split(" · ")[0])
            if results is not None:
                r = results.get(m.get("metrica"))
                if estado != "aplicada":
                    text = "%s: no se aplicó (%s)" % (m["id"], estado)
                elif r is None:
                    text = "%s: aplicada, sin medición de su métrica" % m["id"]
                elif m.get("a_prueba") and r["veredicto"] not in ("informativa", "no comparable", "no confiable"):
                    confirmed = r["veredicto"] == "mejora"
                    text = "%s %s: hipótesis %s (%s %s)" % ("✔" if confirmed else "✖", m["id"],
                                                             "confirmada" if confirmed else "refutada",
                                                             m.get("metrica"), r["veredicto"])
                elif r["veredicto"] == "mejora":
                    text = "✔ %s funcionó: %s" % (m["id"], m.get("metrica"))
                elif r["veredicto"] == "regresión":
                    text = "✖ %s empeoró: %s" % (m["id"], m.get("metrica"))
                else:
                    text = "✖ %s no funcionó: %s %s" % (m["id"], m.get("metrica"), r["veredicto"])
            parts.append(text)
        return "; ".join(parts)
    if "descart" in low:
        return "descartado: se investigó y no es la causa; no hay nada que hacer"
    if "sin veredicto" in low or "confirmar" in low:
        return "no se pudo confirmar ni descartar con estos datos; sin acción"
    if "consecuencia" in low:
        return "lo resuelve la mejora del hallazgo del que depende"
    return "sin mejora asociada"


def findings_md(text, plan, results=None):
    """La tabla de hallazgos de estado.md con una columna que dice qué pasa con cada uno (y el resultado, si lo hay)."""
    headers, rows = parse_table(text)
    if not headers:
        return text
    tipo_index = next((i for i, h in enumerate(headers) if h.lower().startswith("tipo")), None)
    if tipo_index is None:
        return without_placeholders(text)
    # Las columnas que siguen a Tipo (la opcional "Qué falta para decidir") se conservan; al final va qué pasa con él.
    new_headers = headers[:tipo_index] + ["Tipo"] + headers[tipo_index + 1:] \
        + ["Resultado" if results is not None else "Qué pasa con él"]
    new_rows = []
    for row in rows:
        if not row:
            continue
        row = [UNFILLED if has_placeholder(cell) else cell for cell in row] + ["—"] * (len(headers) - len(row))
        row = row[:tipo_index + 1] + [cell or "—" for cell in row[tipo_index + 1:len(headers)]]
        new_rows.append(row + [finding_outcome(row[0], row[tipo_index], plan, results)])
    intro = ("> Un hallazgo es una causa posible. **No todos se convierten en mejoras:** los de tipo `bug` o `mejorable` "
             "sí; `descartado` significa que se investigó y la traza muestra que no es la causa; `sin confirmar` (antes "
             "`sin veredicto estadístico`), que el síntoma puede estar bien medido pero su causa no se pudo probar: no "
             "faltan trazas ni falló la captura, y solo genera una mejora si va a prueba.\n\n")
    return intro + markdown_table(new_headers, new_rows)


def finding_kind(tipo):
    """El tipo de un hallazgo, normalizado; el rótulo anterior `sin veredicto estadístico` es `sin confirmar`."""
    low = tipo.lower()
    for kind, words in (("descartado", ("descart",)), ("sin confirmar", ("sin veredicto", "confirmar")),
                        ("consecuencia", ("consecuencia",)), ("bug", ("bug",)), ("mejorable", ("mejorable",))):
        if any(word in low for word in words):
            return kind
    return tipo.strip() or "sin tipo"


def result_md(findings_text, plan):
    """El recuadro "Resultado" del reporte inicial, antes de todo: con mejoras, cuántas y cuáles; sin mejoras, "Sin
    mejoras aplicables" con una línea de razón por hallazgo, tomada de la tabla de hallazgos."""
    headers, rows = parse_table(findings_text)
    lower = [h.lower() for h in headers]

    def column(prefix):
        return next((i for i, h in enumerate(lower) if h.startswith(prefix)), None)

    tipo_i, symptom_i, cause_i, missing_i = column("tipo"), column("síntoma"), column("causa"), column("qué falta")
    if symptom_i is None:
        symptom_i = column("sintoma")

    def cell(row, index):
        value = row[index].strip() if index is not None and index < len(row) else ""
        return "" if value in ("", "—", "-") or has_placeholder(value) else value

    rows = [row for row in rows if row and row[0].strip()]
    mejoras = plan.get("mejoras", [])
    if mejoras:
        trial = sum(1 for m in mejoras if m.get("a_prueba"))
        lines = ["**%d %s**%s%s. Tú decides cuáles se aplican." % (
            len(mejoras), "mejora propuesta" if len(mejoras) == 1 else "mejoras propuestas",
            " para %d %s" % (len(rows), "hallazgo" if len(rows) == 1 else "hallazgos") if rows else "",
            " (%d a prueba: la causa no está probada y la medición de después la confirma o la refuta)" % trial
            if trial else ""), ""]
        for m in mejoras:
            detail = [improvement_title(m)]
            if m.get("hallazgo"):
                detail.append("ataca %s" % m["hallazgo"])
            if m.get("metrica"):
                detail.append("mide `%s`" % m["metrica"])
            if m.get("esperado"):
                detail.append("esperado: %s" % m["esperado"])
            lines.append("- **%s** · %s" % (m["id"], " · ".join(detail)))
        return "\n".join(lines)
    if not rows:
        return "**Sin mejoras aplicables.** El diagnóstico no dejó hallazgos en `estado.md`."
    kinds = [finding_kind(cell(row, tipo_i)) for row in rows]
    counts = ", ".join("`%s`: %d" % (kind, kinds.count(kind)) for kind in sorted(set(kinds), key=kinds.index))
    lines = ["**Sin mejoras aplicables.** %d %s (%s). Por qué, uno por uno:" % (
        len(rows), "hallazgo" if len(rows) == 1 else "hallazgos", counts), ""]
    for row, kind in zip(rows, kinds):
        reason = cell(row, missing_i)
        reason = "falta: %s" % reason if reason else cell(row, cause_i) or finding_outcome(row[0], cell(row, tipo_i), plan)
        lines.append("- **%s** · %s · `%s` · %s" % (row[0], cell(row, symptom_i) or "—", kind, reason))
    return "\n".join(lines)


def improvements_summary(plan, results, n_findings=None):
    """Para el reporte final: de los hallazgos a las mejoras y su resultado, en una tabla corta."""
    by_metric = {r["metrica"]: r for r in results}
    rows = []
    for m in plan.get("mejoras", []):
        r = by_metric.get(m.get("metrica"))
        estado = m.get("estado", "propuesta")
        result = improvement_result(m, r)
        if estado != "aplicada":
            why = STATE_TEXT.get(estado, estado)
        elif r is None:
            why = "su métrica no tiene antes y después"
        else:
            why = "%s: %s → %s (%s) · %s" % (m.get("metrica"), fmt(r["antes"]["mediana"], r["unidad"]),
                                            fmt(r["despues"]["mediana"], r["unidad"]), fmt_pct(r["delta_pct"]),
                                            VERDICT_TEXT.get(r["veredicto"], r["veredicto"]))
        if m.get("a_prueba"):
            why = "hipótesis: %s · %s" % (m["hipotesis"], why)
        rows.append([m["id"], improvement_title(m), m.get("hallazgo", "—"), result, why])
    if not rows:
        return ""
    counts = flow_counts(plan, rows, n_findings)
    intro = ("> **%(hallazgos)d hallazgos → %(mejoras)d mejoras propuestas → %(aplicadas)d aplicadas → %(ok)d funcionaron.** "
             "Una mejora que no funcionó no se descarta sola: la lectura de la comparación dice por qué y qué sigue.\n\n"
             % counts)
    return intro + markdown_table(["#", "Mejora", "Hallazgo", "Resultado", "Detalle"], rows)


def flow_counts(plan, rows, n_findings=None):
    mejoras = plan.get("mejoras", [])
    linked = len({m.get("hallazgo") for m in mejoras if m.get("hallazgo")})
    return {"hallazgos": n_findings if n_findings else linked or len(mejoras),
            "mejoras": len(mejoras), "aplicadas": sum(1 for m in mejoras if m.get("estado") == "aplicada"),
            "ok": sum(1 for row in rows if row[3].startswith("✔")),
            "ko": sum(1 for row in rows if row[3].startswith("✖"))}


def flow_html(counts):
    """Franja con el recorrido hallazgos → mejoras → aplicadas → resultado, para el HTML."""
    steps = [("Hallazgos", counts["hallazgos"], ""), ("Mejoras propuestas", counts["mejoras"], ""),
             ("Aplicadas y medidas", counts["aplicadas"], ""),
             ("Funcionaron", counts["ok"], " ok" if counts["ok"] else " end"),
             ("No funcionaron", counts["ko"], " ko" if counts["ko"] else "")]
    return '<div class="flow">%s</div>' % "".join(
        '<div class="step%s"><b>%d</b><span>%s</span></div>' % (css, n, e(label)) for label, n, css in steps)


def render_report(folder, name, title, subtitle, parts, charts="", extras=None):
    """Escribe <name>.md y devuelve el HTML. `extras`: HTML propio por sección (gráficos, franjas) que va antes del texto."""
    md = "# %s\n\n_%s_\n" % (title, subtitle)
    md += "".join("\n## %s\n\n%s\n" % (section, body) for section, body in parts if body)
    (folder / ("%s.md" % name)).write_text(md, encoding="utf-8")
    extras = dict(extras or {})
    if charts:
        extras["Métricas principales"] = '<div class="charts">%s</div>' % charts
    shown = [(section, content) for section, content in parts if content]
    nav = "".join('<a href="#s%d">%s</a>' % (i, e(section)) for i, (section, _) in enumerate(shown))
    body = '<nav class="toc">%s</nav>' % nav
    for i, (section, content) in enumerate(shown):
        body += '<section id="s%d"%s><h2>%s</h2>%s%s</section>' % (
            i, ' class="resultado"' if section == "Resultado" else "", e(section), extras.get(section, ""),
            md_to_html(content))
    body = re.sub(r"<td>(mejora|regresión|sin cambio|dentro del ruido|informativa|no comparable|no confiable)( \(backend\))?</td>",
                  lambda m: '<td><span class="verdict %s">%s</span>%s</td>' % (
                      VERDICT_CLASS[m.group(1)], m.group(1), m.group(2) or ""), body)
    body = re.sub(r"<td>(propuesta|aprobada|aplicada|descartada|pendiente)</td>",
                  lambda m: '<td><span class="state s-%s" title="%s">%s</span></td>'
                  % (m.group(1), e(STATE_TEXT[m.group(1)]), m.group(1)), body)
    body = re.sub(r"<td>(✔[^<]*)</td>", r'<td class="ok">\1</td>', body)
    body = re.sub(r"<td>(✖[^<]*)</td>", r'<td class="ko">\1</td>', body)
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

    def filled(*names):
        """La sección sin las líneas que siguen siendo relleno de la plantilla ('' si no queda nada)."""
        return without_placeholders(pick(*names))

    warn_unfilled(folder, sections, findings=True)
    pending_intro = ("> No son mejoras ni tareas obligatorias: es lo que esta investigación no pudo cerrar. De cada uno "
                     "importa el síntoma y qué tan estable es, qué falta para cerrarlo, cuánto cuesta y la acción "
                     "sugerida.\n\n")
    if args.inicial:
        plan_md = plan_table_md(plan, rows) if plan.get("mejoras") else ""
        if plan_md and update_block(folder, "mejoras", plan_md):
            print("✔ estado.md actualizado (Plan de mejoras)")
        plan_intro = ("> Lo que se propone cambiar, una mejora por hallazgo. **Tú decides** cuáles se aplican "
                      "(`perf.py decidir`); las aprobadas se implementan en la fase siguiente y se vuelven a medir.\n\n")
        parts = [("Resultado", result_md(pick("hallazgos"), plan)),
                 ("Resumen", filled("resumen ejecutivo", "resumen")),
                 ("Estado inicial", initial_md(rows, plan, frames_trust(folder))),
                 ("Hallazgos", findings_md(pick("hallazgos"), plan)),
                 ("Plan de mejoras", plan_intro + plan_md if plan_md else ""),
                 ("Ficha y condiciones", ficha_subset(pick("ficha"))),
                 ("Pendientes (no son mejoras)", pending_intro + filled("pendientes") if filled("pendientes") else ""),
                 ("Cómo leer este reporte", GLOSSARY)]
        subtitle = "Reporte inicial · %s · hb-performance %s" % (date, VERSION)
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

    results, unmatched = compare(rows, trust=frames_trust(folder))
    principales = plan.get("principales") or []
    primary = sorted([r for r in results if r["metrica"] in principales], key=lambda r: priority(r["metrica"], plan))
    missing = [m for m in principales if m not in {r["metrica"] for r in results}]
    chosen = compact_compare(results, plan)
    primary_intro = ("> Las métricas que se fijaron antes de medir, antes y después de las mejoras aplicadas. El "
                     "veredicto lo calcula el script comparando con el rango de antes y con el ruido de medición.\n\n")
    primary_md = primary_intro + markdown_table(["Flujo", "Métrica", "Depende de", "Antes", "Después", "Cambio", "Veredicto",
                                                 "Qué significa"], [
        [r["flujo"], r["metrica"], FAMILY_LABEL.get(r["familia"], r["familia"]), fmt(r["antes"]["mediana"], r["unidad"]),
         fmt(r["despues"]["mediana"], r["unidad"]), "%s (%s)" % (fmt_signed(r["delta"], r["unidad"]), fmt_pct(r["delta_pct"])),
         r["veredicto"], VERDICT_TEXT.get(r["veredicto"], "") + (" · depende del backend" if r["familia"] == "e2e" else "")]
        for r in primary]) if primary else ""
    results_by_metric = {r["metrica"]: r for r in results}
    n_findings = len(parse_table(pick("hallazgos"))[1])
    logrado_md = markdown_table(LOGRADO_HEADERS, logrado_rows(plan, results)) if plan.get("mejoras") else ""
    comparison_md = ("> La tabla técnica, igual a `comparacion.md`: todas las métricas medidas, con mediana y P90 por fase. "
                     "Familia `app` = solo la app, `e2e` = app + backend; Ruido (A/A) = antes contra control.\n\n"
                     + markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen])) if chosen else \
        "No hay métricas con antes y después."
    parts = [("Resumen ejecutivo", filled("resumen ejecutivo")),
             ("De los hallazgos al resultado", improvements_summary(plan, results, n_findings)),
             ("Métricas principales", primary_md),
             ("Mejoras: esperado contra logrado", logrado_md),
             ("Hallazgos", findings_md(pick("hallazgos"), plan, results_by_metric)),
             ("Mejoras aplicadas", filled("mejoras aplicadas")),
             ("Lectura de la comparación", filled("lectura de la comparación", "lectura de la comparacion")),
             ("Comparación completa", comparison_md), ("Ficha y condiciones", ficha_subset(pick("ficha"))),
             ("Pendientes (no son mejoras)", pending_intro + filled("pendientes") if filled("pendientes") else ""),
             ("Cómo leer este reporte", GLOSSARY)]
    charts = "".join('<figure class="chart"><figcaption>%s · %s <span class="verdict %s">%s</span></figcaption>%s</figure>'
                     % (e(r["metrica"]), e(r["flujo"]), VERDICT_CLASS[r["veredicto"]], e(r["veredicto"]), bars_svg(r))
                     for r in primary)
    subtitle = "Reporte final · %s · hb-performance %s" % (date, VERSION)
    summary_rows = parse_table(improvements_summary(plan, results, n_findings))[1]
    extras = {"De los hallazgos al resultado": flow_html(flow_counts(plan, summary_rows, n_findings))} if summary_rows else {}
    page = render_report(folder, "reporte-final", title, subtitle, parts, charts, extras)
    print("✔ Reporte final: %s" % (folder / "reporte-final.md"))
    if args.html:
        (folder / "reporte-final.html").write_text(page, encoding="utf-8")
        print("✔ Reporte HTML: %s" % (folder / "reporte-final.html"))
    for m in missing:
        print("⚠ La métrica principal '%s' no tiene antes y después en el CSV." % m)
    if unmatched:
        print("⚠ %d métricas sin las dos fases (ver comparacion.md)." % len(unmatched))
    if plan:
        print_next(folder, plan)


# ── nodos ────────────────────────────────────────────────────────────────────

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# Heurística de "la pantalla todavía carga": la clase estándar de las barras de progreso, o un id, texto o descripción
# con las palabras usuales. No reconoce un cargando hecho a mano sin ninguna de esas pistas.
LOADING_CLASS = re.compile(r"ProgressBar$")
LOADING_WORDS = re.compile(r"progress|loading|spinner|shimmer|skeleton|cargando", re.I)


def ui_nodes(text):
    """Los nodos de un volcado de uiautomator, en orden de documento: [{"attrs", "bounds", "ancestros"}], con los
    bounds como (x1, y1, x2, y2) o None y los ancestros como índices de la misma lista."""
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise PerfError("no es un volcado de uiautomator (XML) válido: %s" % error)
    nodes = []

    def walk(element, ancestors):
        index = len(nodes)
        match = BOUNDS.fullmatch(element.get("bounds", ""))
        nodes.append({"attrs": dict(element.attrib), "bounds": tuple(int(v) for v in match.groups()) if match else None,
                      "ancestros": ancestors})
        for child in element:
            walk(child, ancestors + [index])

    for child in root:
        walk(child, [])
    return nodes


def node_label(node):
    attrs = node["attrs"]
    parts = ['"%s"' % attrs["text"]] if attrs.get("text") else []
    if attrs.get("content-desc"):
        parts.append('desc "%s"' % attrs["content-desc"])
    if attrs.get("resource-id"):
        parts.append("id %s" % attrs["resource-id"].split("/")[-1])
    parts.append(attrs.get("class", "nodo").split(".")[-1])
    return " · ".join(parts)


def node_matches(attrs, text=None, rid=None, desc=None, exact=False):
    def hit(value, wanted):
        value, wanted = (value or "").strip(), wanted.strip()
        return value == wanted if exact else wanted.lower() in value.lower()

    checks = []
    if text is not None:
        checks.append(hit(attrs.get("text"), text))
    if desc is not None:
        checks.append(hit(attrs.get("content-desc"), desc))
    if rid is not None:
        value = attrs.get("resource-id") or ""
        checks.append(value == rid or value.endswith("/" + rid) or (not exact and rid.lower() in value.lower()))
    return bool(checks) and all(checks)


def node_report(nodes, index):
    """(centro o None, avisos) de un nodo: si no se ve, si está deshabilitado, si nada recibe el toque y si el centro
    cae también dentro de otro nodo clickeable que no es su contenedor ni su contenido."""
    node = nodes[index]
    if not node["bounds"] or node["bounds"][2] <= node["bounds"][0] or node["bounds"][3] <= node["bounds"][1]:
        return None, ["sin bounds visibles: el nodo no está a la vista (¿hace falta scroll?)"]
    x1, y1, x2, y2 = node["bounds"]
    center = ((x1 + x2) // 2, (y1 + y2) // 2)
    warnings = []
    if node["attrs"].get("enabled") == "false":
        warnings.append("el nodo está deshabilitado: el toque no va a hacer nada")
    family = [index] + node["ancestros"]
    if not any(nodes[i]["attrs"].get("clickable") == "true" for i in family):
        warnings.append("ni el nodo ni sus contenedores son clickeables: puede que el toque no haga nada")
    for other_index, other in enumerate(nodes):
        box = other["bounds"]
        if other_index in family or index in other["ancestros"] or other["attrs"].get("clickable") != "true" or not box:
            continue
        if box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]:
            warnings.append("el centro también cae dentro de otro nodo clickeable (%s, bounds [%d,%d][%d,%d]): si está "
                            "encima, el toque va a ese; confirma con otro volcado o toca otro punto del nodo"
                            % ((node_label(other),) + box))
    return center, warnings


def loading_nodes(nodes):
    """Los nodos que parecen un cargando a la vista (barra de progreso, shimmer, "Cargando…")."""
    found = []
    for node in nodes:
        attrs, box = node["attrs"], node["bounds"]
        if not box or box[2] <= box[0] or box[3] <= box[1]:
            continue
        if LOADING_CLASS.search(attrs.get("class", "")) or any(
                LOADING_WORDS.search(attrs.get(key) or "") for key in ("resource-id", "text", "content-desc")):
            found.append(node)
    return found


def cmd_nodos(args):
    path = pathlib.Path(args.xml)
    if args.texto is None and args.id is None and args.desc is None:
        raise PerfError("indica qué nodo buscar con --texto, --id o --desc")
    serial = None
    if args.volcar:
        serial = select_device(args.serial)
        adb = Adb(serial)
        # uiautomator puede fallar con código 0 (una animación que no termina, un cargando): sin borrar antes, el pull
        # traería el volcado de la pantalla anterior y el toque iría a un nodo que ya no está.
        adb.shell("rm -f /sdcard/hbperf-ui.xml")
        dumped = adb.shell("uiautomator dump /sdcard/hbperf-ui.xml")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        pulled = adb.run("pull", "/sdcard/hbperf-ui.xml", str(path))
        if dumped.returncode != 0 or pulled.returncode != 0 or not path.is_file():
            raise Precondicion("no se pudo volcar la pantalla con uiautomator (¿una animación o un cargando que no "
                               "termina?): %s. Espera a que la pantalla se quede quieta y vuelve a intentarlo"
                               % ((dumped.stderr or dumped.stdout or pulled.stderr or pulled.stdout).strip()[-200:] or "sin salida"))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise PerfError("no se pudo leer %s: %s (usa --volcar para tomarlo del dispositivo)" % (path, error))
    nodes = ui_nodes(text)
    loading = loading_nodes(nodes)
    if loading:
        print("⚠ La pantalla todavía muestra un cargando (%s): espera a que termine y vuelve a volcar; el contenido y las "
              "coordenadas pueden cambiar." % node_label(loading[0]))
    matches = [i for i, node in enumerate(nodes) if node_matches(node["attrs"], args.texto, args.id, args.desc, args.exacto)]
    if not matches:
        seen = []
        for node in nodes:
            label = node["attrs"].get("text") or node["attrs"].get("content-desc")
            if label and label not in seen:
                seen.append(label)
        raise PerfError("ningún nodo coincide en %s (%d nodos). A la vista: %s" % (
            path, len(nodes), ", ".join('"%s"' % label[:40] for label in seen[:12]) or "ningún texto"))
    if len(matches) > 1:
        print("%d nodos coinciden: afina con --exacto, --id o --desc, o elige por sus bounds." % len(matches))
    tap = "adb%s shell input tap" % (" -s %s" % (serial or args.serial) if (serial or args.serial) else "")
    for position, index in enumerate(matches[:args.limite], start=1):
        center, warnings = node_report(nodes, index)
        box = nodes[index]["bounds"]
        print("%d. %s · bounds %s" % (position, node_label(nodes[index]), "[%d,%d][%d,%d]" % box if box else "—"))
        if center:
            print("   Toque (centro): %s %d %d" % ((tap,) + center))
        for warning in warnings:
            print("   ⚠ " + warning)
    if len(matches) > args.limite:
        print("… %d más (sube --limite)" % (len(matches) - args.limite))


# ── nuevo ────────────────────────────────────────────────────────────────────

ROUTE_TEMPLATE = """#!/usr/bin/env bash
# Recorrido medido del flujo "{{FLUJO}}": solo los toques del tramo que se mide, con adb (nunca Maestro).
# Un comentario por paso, con el elemento que toca. Las coordenadas salen de `perf.py nodos` (centro de los bounds).
# Las esperas (sleep) no entran en las métricas: la ventana va de marca a marca; calíbralas con la corrida de prueba.
# El plan apunta aquí: "recorrido": "bash {{CARPETA}}/recorrido.sh". Para verlo correr a mano: bash {{CARPETA}}/recorrido.sh
set -euo pipefail
SERIAL="${ANDROID_SERIAL:-{{SERIAL}}}"

# Paso 1: <qué elemento toca y qué debe abrirse>
# adb -s "$SERIAL" shell input tap <x> <y> && sleep 3

# Paso 2: <qué elemento toca y qué debe abrirse>
# adb -s "$SERIAL" shell input tap <x> <y> && sleep 3
"""
STARTUP_FAMILIES = {"jank_app_pct": "info", "frame_p50_ms": "info", "frame_p90_ms": "info", "frame_p99_ms": "info"}


REFRESH_SETTINGS = ("min_refresh_rate", "peak_refresh_rate")


def refresh_settings(adb):
    """Los ajustes del sistema que fijan la tasa de refresco, como [(nombre, valor, crudo)]. `valor` es un número, o None
    si el ajuste no está puesto ('null'), no existe o no es una tasa (Infinity, 0); `crudo` es lo que había, tal cual,
    para poder restaurarlo ('' si no había nada)."""
    out = []
    for name in REFRESH_SETTINGS:
        raw = adb.shell("settings get system %s" % name).stdout.strip()
        try:
            value = float(raw)
        except ValueError:
            value = None
        value = value if value is not None and math.isfinite(value) and value > 0 else None
        out.append((name, value, raw if raw != "null" and re.fullmatch(r"[\w.+-]+", raw) else ""))
    return out


def fixed_refresh_rate(settings):
    """Los Hz si la mínima y la máxima están puestas y coinciden (la tasa ya está fija); si no, None."""
    values = [value for _, value, _ in settings]
    if len(values) == 2 and all(values) and abs(values[0] - values[1]) < 1:
        return int(round(values[0]))
    return None


def refresh_commands(settings, serial):
    """(comando que fija la tasa, comando que la restaura a lo que había, Hz que fija) para un dispositivo sin tasa
    fija. Fija la más alta de las que estén puestas; si no hay ninguna, deja <hz> para completar."""
    adb = "adb%s shell settings" % (" -s %s" % serial if serial else "")
    top = max((value for _, value, _ in settings if value), default=None)
    target = fmt(top) if top else "<hz>"
    fix = " && ".join("%s put system %s %s" % (adb, name, target) for name, _, _ in settings)
    restore = " && ".join("%s put system %s %s" % (adb, name, raw) if raw else "%s delete system %s" % (adb, name)
                          for name, _, raw in settings)
    return fix, restore, target


def device_summary(serial, package, need_activity):
    """(texto del dispositivo, actividad de inicio, ajustes de la tasa de refresco) si hay un dispositivo; ('', '', [])
    si no, con el motivo."""
    try:
        chosen = select_device(serial)
        adb = Adb(chosen)
    except PerfError as error:
        print("⚠ Sin dispositivo para completar la ficha y la actividad de inicio: %s" % error)
        return "", "", []
    model = adb.shell("getprop ro.product.model").stdout.strip()
    release = adb.shell("getprop ro.build.version.release").stdout.strip()
    sdk = adb.shell("getprop ro.build.version.sdk").stdout.strip()
    activity = launcher_activity(adb, package) if need_activity else ""
    environment = device_environment(adb)
    kind = " · emulador%s" % (" con render por software" if environment["software"] else "") if environment["emulador"] or environment["software"] else ""
    return "%s · Android %s (API %s)%s" % (model or "?", release or "?", sdk or "?", kind), activity, refresh_settings(adb)


def ensure_ignored(folder):
    """Si git no ignora la carpeta, la agrega a .git/info/exclude (local, no toca el repo) y lo dice."""
    try:
        ignored = subprocess.run(["git", "check-ignore", "-q", str(folder)], capture_output=True, timeout=30)
        if ignored.returncode != 1:
            return
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30)
        if root.returncode != 0:
            return
        relative = pathlib.Path(folder).resolve().relative_to(pathlib.Path(root.stdout.strip()).resolve())
        exclude = pathlib.Path(root.stdout.strip()) / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as handle:
            handle.write("/%s/\n" % relative.as_posix())
        print("✔ git ignora %s (en .git/info/exclude, local: el repo no cambia)" % relative.as_posix())
    except (OSError, ValueError, subprocess.SubprocessError):
        print("⚠ no pude comprobar si git ignora %s: que la evidencia no entre a un commit" % folder)


def read_request(path):
    """El flujo que el usuario pidió en la sesión 0 (reports/perf/setup/pedido.json): {"flujo", "llegar"}, o None."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except OSError:
        return None  # no hay pedido guardado
    except ValueError:  # no es JSON, o no es UTF-8
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("flujo"), str) or not data["flujo"].strip() \
            or not isinstance(data.get("llegar", ""), str):
        print("⚠ %s no tiene la forma {\"flujo\": \"...\", \"llegar\": \"...\"}: no lo uso" % path)
        return None
    return data


def session1_prompt(request, serial):
    """El texto del chat de la sesión 1: el de "flujo largo" si para llegar al tramo hay login u otras pantallas."""
    flow = request["flujo"].strip().rstrip(".")
    reach = (request.get("llegar") or "").strip().rstrip(".")
    if reach:
        return ("Usa hb-performance: medir %s. Para llegar ahí hay que %s: usa un flow de Maestro en preparar y adb para "
                "el tramo medido. Dispositivo %s." % (flow, reach, serial))
    return "Usa hb-performance: medir %s. Dispositivo %s." % (flow, serial)


def cmd_humo(args):
    """Prueba de humo del setup: una corrida de arranque en frío, sin crear una investigación."""
    folder = pathlib.Path(args.carpeta)
    serial = select_device(args.serial)
    adb = Adb(serial)
    activity = args.actividad or launcher_activity(adb, args.paquete)
    if not activity:
        raise Precondicion("no encontré la actividad de inicio de %s: ¿está instalado el build de profiling? (o pasa "
                           "--actividad)" % args.paquete)
    plan = {"paquete": args.paquete, "serial": serial, "compilacion": "completa", "flujos": {"humo": {
        "recorrido": {"tipo": "arranque-frio", "actividad": activity, "espera_s": args.espera},
        "familias": dict(STARTUP_FAMILIES)}}}
    missing_setup = setup_warning(project_root(pathlib.Path.cwd()).resolve())
    if missing_setup:
        print("⚠ " + missing_setup)
    folder.mkdir(parents=True, exist_ok=True)
    ensure_ignored(folder)
    capture = argparse.Namespace(plan=None, prueba=True, paquete=args.paquete, carpeta=str(folder), flujo="humo", fase=None,
                                 hz=args.hz, recorrido=None, tp=args.tp, serial=serial, forzar=args.forzar, config=None,
                                 memoria=False, sin_compilar=False, compilacion=None, rehacer=False, calentamiento=0, preparar=None,
                                 corridas=1, sin_comprimir=False)
    cmd_capturar(capture, plan)
    root = project_root(folder).resolve()
    nuevo = ["nuevo", "--receta", "arranque-frio", "--paquete", args.paquete, "--serial", serial, "--carpeta",
             "reports/perf/arranque-frio/%s" % datetime.date.today().isoformat()]
    if args.instalar:
        nuevo += ["--instalar", json.dumps(args.instalar, ensure_ascii=False)]
    recipe = "cd %s && python3 -I %s %s%s" % (root, HERE / "perf.py", " ".join(nuevo),
                                              " [--red si la primera pantalla carga de la red]")
    request = read_request(args.pedido)
    chat_line = "Chat nuevo · Modelo: %s · Esfuerzo: medio" % model_name(plan, "intermedio")
    if missing_setup:
        print("⚠ Antes de seguir: %s" % missing_setup)
    if request:
        print("Siguiente · sesión 1 (ficha y plan) del flujo que pediste en el setup · %s" % chat_line)
        print("  Texto: \"%s\"" % session1_prompt(request, serial))
        print("  (el flujo sale de %s; ábrelo en un chat nuevo, no en el del setup)" % args.pedido)
        print("Solo si lo que quieres medir es el arranque en frío (receta, sin sesión 1) · Terminal (sin chat):")
        print("  %s" % recipe)
    else:
        print("Siguiente, según lo que se va a investigar:")
        print("  · Una pantalla o un flujo · %s" % chat_line)
        print("    Texto: \"%s\"" % session1_prompt({"flujo": "<flujo: de dónde a dónde y qué debe verse al final>"}, serial))
        print("  · Solo si lo que quieres medir es el arranque en frío (receta, sin sesión 1) · Terminal (sin chat):")
        print("    %s" % recipe)


def cmd_nuevo(args):
    folder = pathlib.Path(args.carpeta)
    if (folder / "plan.json").exists() or (folder / "estado.md").exists():
        raise PerfError("%s ya tiene una investigación: usa otra carpeta" % folder)
    if not re.fullmatch(r"[A-Za-z]\w*(\.[A-Za-z]\w*)+", args.paquete):
        raise PerfError("paquete '%s' no válido: usa el applicationId instalado" % args.paquete)
    startup = args.receta == "arranque-frio"
    device, activity, refresh = device_summary(args.serial, args.paquete, startup and not args.actividad)
    activity = args.actividad or activity
    fixed_hz = fixed_refresh_rate(refresh)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "logs").mkdir(exist_ok=True)
    plan = {"paquete": args.paquete}
    if args.serial:
        plan["serial"] = args.serial
    if args.hz or fixed_hz:
        plan["hz"] = args.hz or fixed_hz
    plan["config"] = "base"
    plan["compilacion"] = "completa"
    if args.instalar:
        plan["instalar"] = args.instalar
    if args.triage:
        plan["profundidad"] = "triage"
    no_leer = read_no_leer(project_root(folder), extra=args.no_leer)
    if no_leer:
        plan["no_leer"] = no_leer
    plan["modelos"] = dict(MODELOS)
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
        scope = args.alcance or "flujo %s" % args.flujo
    (folder / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = (ASSETS / "plantillas" / "estado.md").read_text(encoding="utf-8")
    if startup:
        for marker, value in (
                ('<lo que nota el usuario, o "exploratoria">', "exploratoria (receta de arranque en frío)"),
                ("<las de `principales` en plan.json, y el objetivo de cada una>",
                 "`ttid_ms`, `ttfd_ms` y `hilo_max_ms` · el objetivo lo fija el diagnóstico"),
                ("<variante medida (R8, no depurable, profileable) · backend real o mocks>",
                 "variante medida (R8, no depurable, profileable)%s" % (" · la primera pantalla carga de la red" if args.red else "")),
                ("<guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage>",
                 "guiado · recorrido arranque-frio · %s" % ("triage" if args.triage else "riguroso"))):
            state = state.replace(marker, value)
    rate = ("%d Hz fijos" % fixed_hz if fixed_hz else "%d Hz (del plan; sin fijar en el dispositivo)" % args.hz if args.hz
            else "tasa de refresco sin fijar: la corrida de prueba dice la que midió")
    state = state.replace("{{ALCANCE}}", scope).replace("{{FECHA}}", datetime.date.today().isoformat()) \
        .replace("{{PAQUETE}}", args.paquete) \
        .replace("{{DISPOSITIVO}}", "%s · %s" % (device, rate) if device else DEVICE_PLACEHOLDER) \
        .replace("{{NO_LEER}}", ", ".join("`%s`" % x for x in no_leer) or "ninguna")
    (folder / "estado.md").write_text(state, encoding="utf-8")
    print("✔ %s y %s" % (folder / "plan.json", folder / "estado.md"))
    if not startup:
        route = folder / "recorrido.sh"
        if route.exists():
            print("= %s ya existe, no se toca: el plan apunta a él con \"recorrido\": \"bash %s\"" % (route, route))
        else:
            route.write_text(ROUTE_TEMPLATE.replace("{{FLUJO}}", args.flujo).replace("{{SERIAL}}", args.serial or "<serial>")
                             .replace("{{CARPETA}}", str(folder)), encoding="utf-8")
            route.chmod(route.stat().st_mode | 0o111)
            print("✔ %s: el recorrido medido va ahí, un comentario por paso; cuando esté, el plan apunta a él con "
                  "\"recorrido\": \"bash %s\"" % (route, route))
    ensure_ignored(folder)
    missing_setup = setup_warning(project_root(folder).resolve())
    if missing_setup:
        print("⚠ " + missing_setup)
    if fixed_hz:
        print("✔ Tasa de refresco ya fija en el dispositivo: %d Hz (%s). Queda en 'hz' del plan: no hace falta cambiarla."
              % (fixed_hz, ", ".join("%s=%s" % (name, fmt(value)) for name, value, _ in refresh)))
        if args.hz and abs(args.hz - fixed_hz) > fixed_hz * HZ_TOLERANCE:
            print("⚠ --hz %d no coincide con los %d Hz fijados en el dispositivo: el plan lleva %d; corrígelo si no es a "
                  "propósito" % (args.hz, fixed_hz, args.hz))
    elif device:
        fix, restore, target = refresh_commands(refresh, args.serial)
        print("⚠ La tasa de refresco no está fija en el dispositivo (%s). Si la pantalla tiene una sola tasa, no hace "
              "falta nada; si es adaptativa, cambia entre corridas y con ella el presupuesto de frame:"
              % ", ".join("%s=%s" % (name, raw or "sin poner") for name, _, raw in refresh))
        print("    Fijarla antes de medir:  %s" % fix)
        print("    Restaurarla al cerrar:   %s" % restore)
        print("    Después, \"hz\": %s en plan.json. La corrida de prueba imprime la tasa que midió la traza." % target)
    if startup:
        print_next(folder, plan)
    else:
        print("Siguiente: la sesión 1 completa los pasos, las marcas, la ventana y las métricas principales del plan; al "
              "terminar, perf.py siguiente da los comandos para medir.")


# ── instrumentar ─────────────────────────────────────────────────────────────

BLOCK = re.compile(r"[ \t]*// hb-perf:(\w+)>\n(.*?)[ \t]*// <hb-perf:\1\n", re.S)
GENERATED = "Generated by hb-performance"


def detect(module, words):
    texts = []
    for candidate in (module / "build.gradle.kts", module / "build.gradle", module.parent / "gradle" / "libs.versions.toml",
                      module.parent.parent / "gradle" / "libs.versions.toml"):
        if candidate.is_file():
            texts.append(candidate.read_text(encoding="utf-8", errors="ignore").lower())
    return any(w in t for t in texts for w in words)


def choose(flag, detected):
    return detected if flag is None else flag


def render_template(text, package, tags):
    """Deja los bloques // hb-perf:<tag>> ... // <hb-perf:<tag> cuyo tag está activo (sin las marcas), quita el resto
    y pone el paquete."""
    text = BLOCK.sub(lambda m: m.group(2) if m.group(1) in tags else "", text)
    return re.sub(r"\n{3,}", "\n\n", text.replace("{{PAQUETE}}", package))


def main_source_dir(module, override):
    if override:
        return pathlib.Path(override)
    for candidate in ("src/main/kotlin", "src/main/java"):
        if (module / candidate).is_dir():
            return pathlib.Path(candidate)
    return pathlib.Path("src/main/kotlin")


def is_generated(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return GENERATED in handle.read(400)
    except OSError:
        return False


SNIPPETS = {
    "gradle_existente": """android {
    // La variante "{{VARIANTE}}" {{ESTADO}}: no se crea otro build type.
    sourceSets {
        getByName("debug").kotlin.directories += "{{FUENTE}}" // AGP 9+; en AGP 8: .java.srcDir("{{FUENTE}}")
        getByName("{{VARIANTE}}").kotlin.directories += "{{FUENTE}}"
    }
}
// Dependencias que solo existen para release (releaseImplementation, p. ej. una librería no-op): si la variante no las
// recibe ya, repítelas como "{{VARIANTE}}Implementation"(...). Cobertura (Kover, JaCoCo, Sonar): excluye "**/perf/**".""",
    "gradle": """android {
    buildTypes {
        create("{{VARIANTE}}") {
            initWith(getByName("release"))
            signingConfig = signingConfigs.getByName("debug")
            applicationIdSuffix = ".{{VARIANTE}}" // opcional: convive con el build instalado; el paquete del plan lleva el sufijo
            matchingFallbacks += listOf("release") // solo con módulos de librería
        }
    }
    sourceSets {
        getByName("debug").kotlin.directories += "{{FUENTE}}" // AGP 9+; en AGP 8: .java.srcDir("{{FUENTE}}")
        getByName("{{VARIANTE}}").kotlin.directories += "{{FUENTE}}"
    }
}
// Dependencias que solo existen para release (releaseImplementation, p. ej. una librería no-op): repítelas como
// "{{VARIANTE}}Implementation"(...). Cobertura (Kover, JaCoCo, Sonar): excluye "**/perf/**".""",
    "gradle_propiedad": """// Para un proyecto que decide cosas por el nombre del build type: en vez de crear otro, mide sobre el que ya usas
// para probar ("<buildType>") solo cuando se pasa -Pperf. Sin -Pperf, ese build type no cambia.
// Es un ejemplo: ajústalo a tu proyecto y a tu versión de AGP.
val perf = providers.gradleProperty("perf").isPresent
android {
    buildTypes {
        getByName("<buildType>") {
            if (perf) {
                isDebuggable = false
                isProfileable = true
            }
        }
    }
    sourceSets {
        getByName("debug").kotlin.directories += "{{FUENTE}}" // AGP 9+; en AGP 8: .java.srcDir("{{FUENTE}}")
        if (perf) {
            getByName("<buildType>").kotlin.directories += "{{FUENTE}}"
            // El <provider> de PerfInstaller está en el manifest que generó la skill. srcFile reemplaza el manifest de
            // ese source set: si src/<buildType>/AndroidManifest.xml ya existe, copia antes su contenido a este.
            getByName("<buildType>").manifest.srcFile("src/{{VARIANTE}}/AndroidManifest.xml")
        }
    }
}
// Instalar: ./gradlew :<módulo>:install<BuildType> -Pperf. El `paquete` del plan es el applicationId de ese build type.
// Con -Pperf el build deja de ser depurable: mira los avisos de <debug-overrides> y de BuildConfig.DEBUG.""",
    "red_hilt": """// Donde se arma el OkHttpClient (Hilt): inyecta el set y aplica la primera factory.
@Provides fun okHttp(@PerfEventListeners factories: Set<@JvmSuppressWildcards EventListener.Factory>): OkHttpClient =
    OkHttpClient.Builder()
        .apply { factories.firstOrNull()?.let(::eventListenerFactory) }
        .build()
// imports: {{PAQUETE}}.PerfEventListeners, okhttp3.EventListener""",
    "red_sinhilt": """// En cada OkHttpClient.Builder del alcance, antes de build():
PerfHooks.okHttp(builder) // import {{PAQUETE}}.PerfHooks""",
    "nav": """// Navigation Compose (la ruta es la plantilla, movie/{id}): junto al NavHost
remember(navController) {
    navController.addOnDestinationChangedListener { _, destination, _ -> destination.route?.let(PerfHooks.navigation) }
}
// Navigation 3: LaunchedEffect(backStack) { snapshotFlow { backStack.lastOrNull() }.collect { it?.let(PerfHooks.navigation) } }
// import {{PAQUETE}}.PerfHooks""",
    "contenido": """// Primera pantalla (TTFD, también para Android vitals), Compose: ReportDrawnWhen { !uiState.isLoading }
// Views: reportFullyDrawn() cuando el adapter recibe los datos.
// Cualquier otra pantalla que se vaya a medir, cuando su contenido real está a la vista (una vez por carga):
LaunchedEffect(uiState.isLoading) { if (!uiState.isLoading) PerfHooks.mark("<pantalla>") } // marca MARK <pantalla>""",
}


# ── Escaneo del proyecto: puntos de extensión de contenido visible ───────────

SCAN_SKIP = {"build", "node_modules", "reports", "test", "androidTest", "testFixtures", "out"}
SCAN_MAX_FILES = 5000
SCAN_MAX_BYTES = 400_000
HOOK_TOKENS = ("VisibleContent", "ContentVisible", "ContentReady", "ScreenReady", "ScreenLoaded", "ContentLoaded",
               "FullyDrawn", "ReportDrawn", "ScreenDrawn", "ContentShown", "ScreenShown", "ScreenDisplayed",
               "ScreenImpression", "ScreenViewed", "ScreenTracker", "ScreenTracking")
INTERFACE_DECL = re.compile(r"\binterface\s+(\w+)")
COMPOSITION_LOCAL = re.compile(r"\bval\s+(\w+)\s*(?::[^=\n]+)?=\s*(?:static)?[cC]ompositionLocalOf\b")
SET_OF = re.compile(r"\bSet<\s*(?:@\w+(?:\([^)]*\))?\s+)*(\w+)")
INTO_BINDING = re.compile(r"@(?:IntoSet|IntoMap)\b[\s\S]{0,300}?\bfun\s+\w+\s*\([^)]*\)\s*:\s*(?:@\w+\s+)*(\w+)")
PACKAGE_DECL = re.compile(r"^\s*package\s+([\w.]+)", re.M)
OKHTTP_BUILDER = re.compile(r"\bOkHttpClient\s*\.\s*Builder\s*\(\s*\)|\bOkHttpClient\s*\(\s*\)")
MODULE_PLUGINS = (("aplicación", re.compile(r"android[._-]?application|com\.android\.application", re.I)),
                  ("librería", re.compile(r"android[._-]?library|com\.android\.library", re.I)))
BUILD_CONFIG_USE = re.compile(r"\bBuildConfig\s*\.\s*(BUILD_TYPE|FLAVOR\w*|DEBUG)\b")  # FLAVOR_<dimensión> también
# Lógica de Gradle que depende del nombre de un build type, un sabor o una variante. No cuenta el nombre de un proyecto.
GRADLE_NAME_LOGIC = re.compile(r"(?<![pP]roject\.)\b(?:name|getName\(\))\s*(?:\.\s*\w+\(\)\s*)*"
                               r"(?:(?:==|!=)\s*[\"']\w|\.\s*(?:endsWith|startsWith|contains|equals|matches)\s*\()")
# Líneas que miran el nombre de otra cosa (tareas, dependencias, archivos, proyectos): no deciden por build type.
GRADLE_TASK_LINE = re.compile(r"\btasks?\b|Task\b|\brequested\b|\b(?:sub|all)projects\b|\.(?:jar|aar)\b")
SETTINGS_HINT = re.compile(r"\bprojectDir\s*=|\bincludeBuild\b")
SETTINGS_PATH = re.compile(r"projectDir\s*=\s*(?:new\s+)?[fF]ile\s*\(\s*(?:\w+\s*,\s*)?[\"']([^\"']+)[\"']"
                           r"|includeBuild\s*\(?\s*[\"']([^\"']+)[\"']")
FUN_HEAD = re.compile(r"\bfun\s+(\w+)\s*\(")
FUN_TAIL = re.compile(r"\s*(?::\s*([^{=]*))?([{=])?")
PRIMITIVE_TYPES = ("String", "Int", "Long", "Boolean", "Float", "Double", "Unit")

def walk_files(root, patterns, suffixes, project=None):
    """Archivos con esas extensiones bajo root, en orden, sin carpetas de build, ocultas ni de tests y sin las rutas
    prohibidas; los que generó la skill tampoco. `project` es la raíz del proyecto contra la que se comparan las rutas
    prohibidas cuando root es otra carpeta (un módulo que settings.gradle incluye desde fuera)."""
    count, project = 0, project or root
    for current, dirs, files in os.walk(str(root)):
        dirs[:] = sorted(d for d in dirs if d not in SCAN_SKIP and not d.startswith(".")
                         and not is_denied(os.path.join(current, d), project, patterns))
        for name in sorted(files):
            path = pathlib.Path(current) / name
            if name.endswith(suffixes) and not is_denied(path, project, patterns) and not is_generated(path):
                count += 1
                if count > SCAN_MAX_FILES:
                    return
                yield path


def match_paren(text, start):
    """Índice justo después del paréntesis que cierra el que está en text[start]."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def split_params(params):
    """Parámetros de primer nivel de una lista de Kotlin, sin partir las comas de genéricos ni de tipos función."""
    parts, depth, start, previous = [], 0, 0, ""
    for i, char in enumerate(params):
        if char in "([{<":
            depth += 1
        elif char in ")]}" or (char == ">" and previous != "-"):  # el > de "->" no cierra nada
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(params[start:i])
            start = i + 1
        previous = char
    parts.append(params[start:])
    return [part.strip() for part in parts if part.strip()]


def without_default(param):
    """El parámetro sin su valor por defecto: un override no puede repetirlo."""
    depth, previous = 0, ""
    for i, char in enumerate(param):
        if char in "([{<":
            depth += 1
        elif char in ")]}" or (char == ">" and previous != "-"):
            depth -= 1
        elif char == "=" and depth == 0:
            return param[:i].strip()
        previous = char
    return param


def hook_methods(text, declaration):
    """Funciones abstractas (sin cuerpo) de la interfaz Kotlin que empieza en declaration: [(nombre, parámetros sin valores
    por defecto, retorno, suspend)]. Una interfaz Java no da métodos."""
    start = text.find("{", declaration.end())
    # entre el nombre y la llave solo van genéricos y supertipos; si aparece otra declaración, la interfaz no tiene cuerpo
    if start < 0 or re.search(r"\b(?:class|interface|object|fun|val|var)\b", text[declaration.end():start]):
        return []
    body = text[start:match_brace(text, start)]
    methods = []
    for head in FUN_HEAD.finditer(body):
        close = match_paren(body, head.end() - 1)
        tail = FUN_TAIL.match(body[close:].split("\n", 1)[0].split("//", 1)[0])
        if tail and not tail.group(2):
            params = ", ".join(without_default(p) for p in split_params(body[head.end():close - 1]))
            methods.append((head.group(1), params, (tail.group(1) or "").strip(),
                            bool(re.search(r"\bsuspend\s+$", body[:head.start()]))))
    return methods


def relative_to_root(path, root):
    """La ruta desde la raíz del proyecto, con '..' si está fuera (un módulo incluido desde otra carpeta)."""
    return pathlib.Path(os.path.relpath(os.path.realpath(str(path)), os.path.realpath(str(root)))).as_posix()


def external_roots(root, patterns):
    """(carpetas fuera de la raíz que settings.gradle(.kts) incluye, rutas que no se pudieron seguir). Mira los
    `projectDir = file("...")` (o File(dir, "...")) y los `includeBuild("...")`; una ruta con variables no se resuelve."""
    root = pathlib.Path(root).resolve()
    found, unresolved = [], []
    for name in ("settings.gradle.kts", "settings.gradle"):
        settings = root / name
        if not settings.is_file() or is_denied(settings, root, patterns):
            continue
        for line in settings.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not SETTINGS_HINT.search(line) or line.lstrip().startswith(("//", "*", "/*")):
                continue
            match = SETTINGS_PATH.search(line)
            if not match:  # una ruta armada con variables u otra forma que no se sabe leer: se avisa, no se ignora
                unresolved.append(line.strip()[:100])
                continue
            raw = match.group(1) or match.group(2)
            for variable in ("${rootDir}", "$rootDir", "${settingsDir}", "$settingsDir"):
                raw = raw.replace(variable, str(root))
            if "$" in raw:
                unresolved.append(raw)
                continue
            path = pathlib.Path(os.path.normpath(str(root / raw)))
            # dentro de la raíz ya se recorre; una carpeta que contiene a la raíz (includeBuild("..")) la repetiría entera
            if is_under(path, root) or is_under(root, path) or is_denied(path, root, patterns):
                continue
            if path.is_dir() and path not in found:
                found.append(path)
            elif not path.is_dir() and raw not in unresolved:
                unresolved.append(raw)
    return found, unresolved


def scan_gradle(root, patterns, extra=()):
    """Líneas de los build.gradle(.kts) que deciden algo por el nombre de un build type, un sabor o una variante
    (`name == "qa"`, `name.endsWith("Release")`): [(archivo, línea, texto)]."""
    root = pathlib.Path(root)
    found = []
    for base in [root] + list(extra):
        for path in walk_files(base, patterns, (".gradle", ".gradle.kts"), root):
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            found += [(relative_to_root(path, root), number, line.strip()[:120])
                      for number, line in enumerate(lines, start=1)
                      if GRADLE_NAME_LOGIC.search(line) and not GRADLE_TASK_LINE.search(line)]
    return found


def scan_sources(root, patterns, extra=()):
    """Un solo recorrido de los .kt y .java (los de la raíz y los de las carpetas de `extra`, los módulos que
    settings.gradle incluye desde fuera): interfaces y CompositionLocal con un nombre de 'contenido visible'
    (HOOK_TOKENS) y, de cada interfaz, si algún multibinding la recibe. También dónde se arma un OkHttpClient, cuántos
    archivos usan WebView, RecyclerView o RxJava y dónde se lee BuildConfig.BUILD_TYPE, FLAVOR o DEBUG.
    Devuelve {"ganchos", "archivos", "okhttp", "vistas", "buildconfig"}."""
    hooks, multi, files, builders = [], set(), 0, []
    views = {"WebView": 0, "RecyclerView": 0, "RxJava": 0}
    build_config = {"BUILD_TYPE": [], "FLAVOR": [], "DEBUG": []}
    root = pathlib.Path(root)
    paths = [path for base in [root] + list(extra) for path in walk_files(base, patterns, (".kt", ".java"), root)]
    for path in paths:
        try:
            if path.stat().st_size > SCAN_MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files += 1
        relative = relative_to_root(path, root)
        for name, found in (("WebView", "WebView" in text), ("RecyclerView", "RecyclerView" in text),
                            ("RxJava", "io.reactivex" in text or "rxjava" in text.lower())):
            views[name] += 1 if found else 0
        for builder in OKHTTP_BUILDER.finditer(text):
            builders.append((relative, text.count("\n", 0, builder.start()) + 1))
        for use in BUILD_CONFIG_USE.finditer(text):
            build_config["FLAVOR" if use.group(1).startswith("FLAVOR") else use.group(1)].append(
                (relative, text.count("\n", 0, use.start()) + 1))
        multi.update(SET_OF.findall(text))
        multi.update(INTO_BINDING.findall(text))
        package_match = PACKAGE_DECL.search(text)
        package = package_match.group(1) if package_match else ""
        for declaration in INTERFACE_DECL.finditer(text):
            if any(token in declaration.group(1) for token in HOOK_TOKENS):
                hooks.append({"tipo": "interfaz", "nombre": declaration.group(1), "archivo": relative, "paquete": package,
                              "linea": text.count("\n", 0, declaration.start()) + 1,
                              "metodos": hook_methods(text, declaration)})
        for local in COMPOSITION_LOCAL.finditer(text):
            if any(token in local.group(1) for token in HOOK_TOKENS):
                hooks.append({"tipo": "compositionlocal", "nombre": local.group(1), "archivo": relative, "paquete": package,
                              "linea": text.count("\n", 0, local.start()) + 1, "metodos": []})
    for hook in hooks:
        hook["multibinding"] = hook["tipo"] == "interfaz" and hook["nombre"] in multi
    return {"ganchos": hooks, "archivos": files, "okhttp": builders, "vistas": views, "buildconfig": build_config}


def is_under(path, folder):
    try:
        pathlib.Path(path).resolve().relative_to(pathlib.Path(folder).resolve())
        return True
    except ValueError:
        return False


def list_modules(root, patterns, max_depth=5):
    """[(carpeta relativa, tipo)] de los módulos Gradle bajo root: 'aplicación', 'librería' u 'otro'."""
    root = pathlib.Path(root)
    modules = []
    for current, dirs, files in os.walk(str(root)):
        depth = len(pathlib.Path(current).relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if depth < max_depth and d not in SCAN_SKIP and d not in ("src", "gradle")
                         and not d.startswith(".") and not is_denied(os.path.join(current, d), root, patterns))
        gradle = next((n for n in ("build.gradle.kts", "build.gradle") if n in files), None)
        if gradle and current != str(root):
            text = (pathlib.Path(current) / gradle).read_text(encoding="utf-8", errors="ignore")
            kind = next((label for label, pattern in MODULE_PLUGINS if pattern.search(text)), "otro")
            modules.append((pathlib.Path(current).relative_to(root).as_posix(), kind))
    return modules


def hook_snippet(hooks, variant):
    """Cómo conectar PerfHooks.mark al punto de extensión que el proyecto ya tiene, en lugar de editar pantallas."""
    lines = ["// El proyecto ya tiene un punto de extensión de contenido visible: conecta ahí las marcas, no en las pantallas.",
             "// Candidatos (verifica leyendo la interfaz y quién la llama; el nombre de la marca es lo que reciba el gancho):"]
    for hook in hooks[:6]:
        extra = ""
        if hook["metodos"]:
            extra = " · " + "; ".join("%sfun %s(%s)%s" % ("suspend " if m[3] else "", m[0], m[1], ": %s" % m[2] if m[2] else "")
                                      for m in hook["metodos"][:2])
        lines.append("//  - %s %s (%s:%d)%s%s" % (
            "interfaz" if hook["tipo"] == "interfaz" else "CompositionLocal", hook["nombre"], hook["archivo"], hook["linea"],
            " · con multibinding" if hook["multibinding"] else "", extra))
    chosen = next((h for h in hooks if h["tipo"] == "interfaz" and h["multibinding"] and h["metodos"]), None)
    unreadable = next((h for h in hooks if h["tipo"] == "interfaz" and h["multibinding"] and not h["metodos"]), None)
    target = chosen or unreadable
    if target:
        method = target["metodos"][0] if chosen else None
        types = []
        if method:
            types = [p.split(":", 1)[1].strip().rstrip("?") for p in split_params(method[1]) if ":" in p]
            types += [method[2].rstrip("?")] if method[2] else []
        lines += [
            "//",
            "// Binding en el source set perf (debug y %s; release queda igual, el multibinding ya existe):" % variant]
        if not method:
            lines += ["// %s tiene un multibinding pero no pude leer sus métodos (¿interfaz Java o una firma que no reconozco?): "
                      "ábrela," % target["nombre"],
                      "// implementa cada método y, en el que avisa que el contenido está a la vista, llama a PerfHooks.mark(<nombre>)."]
        lines += [
            "@Module",
            "@InstallIn(SingletonComponent::class)",
            "object PerfVisibleContentModule {",
            "    @Provides",
            "    @IntoSet",
            "    fun perf%s(): %s = object : %s {" % (target["nombre"], target["nombre"], target["nombre"])]
        if method:
            name_param = next(iter(re.findall(r"(\w+)\s*:\s*String\b", method[1])), None)
            returns = method[2] and method[2] != "Unit"
            mark = "PerfHooks.mark(%s)" % (name_param or '"<pantalla>" /* arma el nombre con los parámetros */')
            lines += ["        override %sfun %s(%s)%s { %s%s }" % (
                "suspend " if method[3] else "", method[0], method[1], ": %s" % method[2] if returns else "", mark,
                '; TODO("devuelve lo que espera quien lo llama")' if returns else "")]
            if returns:
                lines.insert(len(lines) - 1, "        // %s devuelve %s: reemplaza el TODO por el valor que el proyecto espera." % (method[0], method[2]))
        else:
            lines.append("        // PerfHooks.mark(<nombre>) en el método que avisa que el contenido está a la vista")
        lines += [
            "    }",
            "}",
            "// imports: %s.%s, {{PAQUETE}}.PerfHooks, dagger.Module, dagger.Provides, dagger.hilt.InstallIn, "
            "dagger.hilt.components.SingletonComponent, dagger.multibindings.IntoSet%s" % (
                target["paquete"] or "<paquete>", target["nombre"],
                " (más los tipos de los parámetros)" if any(t not in PRIMITIVE_TYPES for t in types) else ""),
            "// Con un Map usa @IntoMap y la clave del proyecto; con Dagger 2 sin Hilt, agrega el módulo a la lista del componente.",
            "// Si el componente no es Singleton (retained, activity), cambia @InstallIn."]
    else:
        lines += [
            "//",
            "// Sin multibinding que lo reciba: no hay dónde sumar un binding sin tocar el código principal. Pon la marca en la",
            "// implementación que atiende el gancho (PerfHooks.mark(<nombre>) en un solo archivo) o, con CompositionLocal, en",
            "// el CompositionLocalProvider que lo provee. Si hay pantallas sin pasar por él, una línea por pantalla como último recurso."]
    lines.append("// Primera pantalla (TTFD, también para Android vitals), Compose: ReportDrawnWhen { !uiState.isLoading }; "
                 "Views: reportFullyDrawn().")
    return "\n".join(lines)


BRIDGE_SNIPPET = """// Las librerías no ven PerfHooks (vive en el módulo app): una pantalla de un módulo library emite la marca por una
// interfaz que SÍ ven. Es código de producción (sin efecto en release): propónselo al usuario antes de agregarlo.
// 1. En un módulo del que dependan las librerías con pantallas (core, common...):
object ContentVisible {
    @Volatile var onVisible: (String) -> Unit = {} // no-op hasta que la app lo apunta
    fun mark(screen: String) = onVisible(screen)
}
// 2. En las pantallas medidas, de cualquier módulo, una vez por carga: ContentVisible.mark("<pantalla>")
// 3. En el módulo app, una sola línea en Application.onCreate (PerfHooks.mark no hace nada en release):
ContentVisible.onVisible = { PerfHooks.mark(it) } // import {{PAQUETE}}.PerfHooks"""

VIEWS_SNIPPET = """// Marca = el contenido real ya está a la vista, una vez por carga (no por navegación ni por cada bind).
// WebView: tras onPageFinished, cuando el DOM ya se pintó (API 23+):
override fun onPageFinished(view: WebView, url: String) {
    view.postVisualStateCallback(0L, object : WebView.VisualStateCallback() {
        override fun onComplete(requestId: Long) { if (!marked) { marked = true; PerfHooks.mark("<pantalla>") } }
    })
}
// RecyclerView: tras entregar la lista y antes de pintarla (androidx.core.view.doOnPreDraw):
adapter.submitList(items) { recyclerView.doOnPreDraw { PerfHooks.mark("<pantalla>") } }
//   adapter sin submitList: notifyDataSetChanged() seguido de recyclerView.doOnPreDraw { PerfHooks.mark("<pantalla>") }
// RxJava / MVP: en el onSuccess/onNext que ya corre en el hilo principal (observeOn(AndroidSchedulers.mainThread())),
//   después de entregar los datos al adapter o a la vista, no en un doOnNext de la capa de red; vuelve `marked` a false
//   cuando empieza una carga nueva."""

VARIANT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*")
PRODUCTION_VARIANTS = ("debug", "release")  # build types del proyecto: jamás llevan el source set ni el provider de perf
FLAVORED_PRODUCTION = re.compile(r"[A-Za-z0-9](?:Release|Debug)$")  # una variante con sabores: <sabor>Release, <sabor>Debug
PROFILEABLE_ON = re.compile(r"\b(?:isProfileable|profileable)\s*(?:=\s*|\s+)true\b")


def outer_level(body):
    """El cuerpo de un build type sin sus bloques anidados: lo que declara siempre, no dentro de un `if (...) { }`."""
    out, depth = [], 0
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return "".join(out)


def always_profileable(body):
    """True si el build type se declara profileable sin condiciones. Uno que lo es solo con una propiedad (dentro de
    `if (perf) { }`) no es una variante existente: sin esa propiedad no es profileable ni lleva la instrumentación."""
    return bool(PROFILEABLE_ON.search(outer_level(body)))


def is_production(name, declared=()):
    """True si la variante es release o debug, sola o con sabores (demoRelease, freeDebug): nunca lleva la
    instrumentación, porque es el build que se publica o el depurable del día a día. `declared` son los build types que
    el módulo declara: uno propio con un nombre así (preRelease) no es un sabor de release."""
    if name.lower() in PRODUCTION_VARIANTS:
        return True
    return name not in declared and bool(FLAVORED_PRODUCTION.search(name))


def module_build_types(module, root, patterns):
    """{nombre: cuerpo} de los build types del build.gradle(.kts) del módulo ({} si no se puede leer)."""
    gradle = next((module / n for n in ("build.gradle.kts", "build.gradle") if (module / n).is_file()), None)
    if not gradle or is_denied(gradle, root, patterns):
        return {}
    return build_types(gradle.read_text(encoding="utf-8", errors="ignore"))
DEBUGGABLE_ON = re.compile(r"\b(?:isDebuggable|debuggable)\s*(?:=\s*|\s+)true\b")
DEBUGGABLE_OFF = re.compile(r"\b(?:isDebuggable|debuggable)\s*(?:=\s*|\s+)false\b")
BUILD_TYPE_HEADER = re.compile(r"(?:(?:create|register|getByName|maybeCreate)\s*\(\s*[\"'](\w+)[\"']\s*\)"
                               r"|(?:val\s+)?(\w+)\s+by\s+(?:creating|getting)|(?<![\w.\"'])(\w+))\s*\{")


def match_brace(text, start):
    """Índice justo después de la llave que cierra la que está en text[start]."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def build_types(text):
    """{nombre: cuerpo} de los build types de un build.gradle(.kts); solo los de primer nivel de buildTypes { }."""
    found = re.search(r"\bbuildTypes\s*\{", text)
    if not found:
        return {}
    start = found.end() - 1
    body = text[start + 1:match_brace(text, start) - 1]
    types, pos = {}, 0
    while True:
        header = BUILD_TYPE_HEADER.search(body, pos)
        if not header:
            return types
        brace = header.end() - 1
        end = match_brace(body, brace)
        types[header.group(1) or header.group(2) or header.group(3)] = body[brace + 1:end - 1]
        pos = end


def is_debuggable(name, body):
    """True si el build type es depurable: lo declara, o hereda de debug con initWith y no lo apaga."""
    if DEBUGGABLE_ON.search(body):
        return True
    if DEBUGGABLE_OFF.search(body):
        return False
    base = re.search(r"initWith\s*\(?([^)\n;]*)", body)  # initWith(getByName("debug")) o, en Groovy, initWith debug
    if base:
        words = re.findall(r"\w+", base.group(1))
        return bool(words) and words[-1] == "debug"
    return name == "debug"


def find_profileable_variants(module, root, patterns):
    """Variantes profileable del módulo: las que lo declaran en su manifest (<profileable>) y los build types que lo
    declaran en Gradle (isProfileable = true, o `profileable true`): [{nombre, manifest, estado, generada, gradle}].
    'estado': 'ok' (build type no depurable), 'depurable' o 'sin build type' (no se pudo verificar: sabores, otro
    plugin). release y debug, solos o con sabores, nunca son candidatas."""
    types = module_build_types(module, root, patterns)
    found = []
    for manifest in sorted((module / "src").glob("*/AndroidManifest.xml")):
        name = manifest.parent.name
        if name == "main" or is_production(name, types) or is_denied(manifest, root, patterns):
            continue
        text = manifest.read_text(encoding="utf-8", errors="ignore")
        profileable = re.search(r"<profileable\b[^>]*>", text)
        if not profileable or re.search(r"android:enabled\s*=\s*[\"']false[\"']", profileable.group(0)):
            continue
        state = "sin build type" if name not in types else "depurable" if is_debuggable(name, types[name]) else "ok"
        found.append({"nombre": name, "manifest": manifest, "estado": state, "generada": GENERATED in text[:400],
                      "gradle": always_profileable(types.get(name, ""))})
    for name, body in types.items():  # los que lo declaran solo en Gradle, sin <profileable> en su manifest
        if is_production(name, types) or any(c["nombre"] == name for c in found) or not always_profileable(body):
            continue
        manifest = module / "src" / name / "AndroidManifest.xml"
        if manifest.is_file() and is_denied(manifest, root, patterns):
            continue
        found.append({"nombre": name, "manifest": manifest if manifest.is_file() else None, "gradle": True,
                      "estado": "depurable" if is_debuggable(name, body) else "ok", "generada": False})
    return found


def source_set_files(module, name, limit=10):
    """Los archivos del source set de un build type (src/<nombre>/), para decir qué no copia initWith."""
    base = module / "src" / name
    if not base.is_dir():
        return []
    files = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
    return files[:limit] + (["…"] if len(files) > limit else [])


def debug_overrides(module, root, patterns):
    """Los XML de res/xml del módulo que usan <debug-overrides> (network security config): ese bloque solo aplica en
    builds depurables, así que la variante medida lo pierde."""
    found = []
    for path in sorted((module / "src").glob("*/res/xml*/*.xml")):
        if is_denied(path, root, patterns):
            continue
        try:
            if "<debug-overrides" in path.read_text(encoding="utf-8", errors="ignore"):
                found.append(path)
        except OSError:
            continue
    return found


def find_instrumentation(root):
    """(hay un source set `perf`, hay PerfHooks.kt) bajo la raíz del proyecto: lo que deja `instrumentar`."""
    perf_set = hooks = False
    for current, dirs, files in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d not in ("build", "node_modules", "reports", "out") and not d.startswith(".")]
        perf_set = perf_set or (os.path.basename(current) == "src" and "perf" in dirs)
        hooks = hooks or "PerfHooks.kt" in files
        if perf_set and hooks:
            break
    return perf_set, hooks


REAPPLY_HINT = re.compile(r"git apply|parche|\.patch\b", re.I)


def setup_warning(root):
    """Aviso si la instrumentación del setup no está en el repo ('' si está). Si AGENTS.md dice "setup listo" y el
    código no está (el setup se guarda como parche, o se revirtió), dice cómo reaplicarlo."""
    perf_set, hooks = find_instrumentation(root)
    if hooks:
        return ""  # con PerfHooks.kt alcanza: el source set puede tener otro nombre (instrumentar --fuente)
    try:
        agents = (pathlib.Path(root) / "AGENTS.md").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        agents = ""
    missing = "no encontré la instrumentación en el repo (ni PerfHooks.kt%s, bajo %s)" % (
        "" if perf_set else " ni un source set src/perf", root)
    if not re.search(r"setup\s+listo", agents, re.I):
        return "%s: falta la sesión 0 (setup) antes de medir; sin ella no salen las marcas ni las secciones" % missing
    # La línea que dice cómo reaplicarlo: la de "setup listo" si lo dice ahí; si no, una de la sección de rendimiento.
    hint, section = "", False
    for line in agents.splitlines():
        if line.startswith("#"):
            section = bool(re.search(r"rendimiento|performance", line, re.I))
        elif REAPPLY_HINT.search(line) and (re.search(r"setup\s+listo", line, re.I) or (section and not hint)):
            hint = line.strip(" -*\t")[:200]
            if re.search(r"setup\s+listo", line, re.I):
                break
    how = ('según AGENTS.md: "%s"' % hint if hint else
           "si el setup se guarda como parche, aplícalo (git apply <parche>); si se perdió, repite la sesión 0 "
           "(perf.py instrumentar no pisa lo que exista)")
    return ('AGENTS.md dice "setup listo" pero %s: las marcas no van a salir y la variante medida puede no compilar. '
            "Reaplícala antes de seguir: %s" % (missing, how))


def resolve_variant(found, requested):
    """(variante, existente): la pedida con --variante; si no, la única profileable y no depurable del módulo (la que
    creó la skill gana si hay varias); si no hay ninguna, 'profiling' nueva. Una pedida que declara <profileable> es
    existente aunque no se pueda verificar su build type (sabores, otro plugin): crear otro la duplicaría; si es
    depurable, se rechaza."""
    if requested:
        asked = next((c for c in found if c["nombre"] == requested), None)
        if asked and asked["estado"] == "depurable":
            raise PerfError("variante '%s' es depurable (declara isDebuggable o hereda de debug): las trazas no reflejan "
                            "el rendimiento real. Usa otra, o --variante profiling para crear una propia" % requested)
        return requested, asked is not None
    valid = [c for c in found if c["estado"] == "ok"]
    chosen = [c for c in valid if c["generada"]] or valid
    if len(chosen) > 1:
        raise PerfError("hay %d variantes profileable y no depurables (%s): elige una con --variante, o --variante "
                        "profiling para crear una propia" % (len(chosen), ", ".join(c["nombre"] for c in chosen)))
    return (chosen[0]["nombre"], True) if chosen else ("profiling", False)


def cmd_instrumentar(args):
    module = pathlib.Path(args.modulo)
    if not (module / "build.gradle.kts").is_file() and not (module / "build.gradle").is_file():
        raise PerfError("%s no parece un módulo Gradle (falta build.gradle o build.gradle.kts)" % module)
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", args.paquete):
        raise PerfError("paquete '%s' no válido: usa algo como com.ejemplo.app.perf" % args.paquete)
    if args.variante and not VARIANT_NAME.fullmatch(args.variante):
        raise PerfError("variante '%s' no válida: usa el nombre del build type (profiling, benchmark, releaseLike)" % args.variante)
    root = project_root(module)
    denied = read_no_leer(root, extra=args.no_leer)
    if args.variante and is_production(args.variante, module_build_types(module, root, denied)):
        raise PerfError("variante '%s' no válida: release y debug (también con sabores, como demoRelease) son los build "
                        "types del proyecto y la instrumentación no puede entrar en el release que se publica; usa otra "
                        "variante o deja que se cree `profiling`. Un nombre que termina en Release o Debug solo se acepta "
                        "si el build.gradle del módulo lo declara como build type propio" % args.variante)
    found_variants = find_profileable_variants(module, root, denied)
    variant, existing = resolve_variant(found_variants, args.variante)
    unverified = any(c["nombre"] == variant and c["estado"] == "sin build type" for c in found_variants)
    in_gradle = any(c["nombre"] == variant and c.get("gradle") for c in found_variants)
    modules = list_modules(root, denied)
    outside_roots, unresolved_roots = external_roots(root, denied)
    scan = scan_sources(root, denied, outside_roots)
    name_logic = scan_gradle(root, denied, outside_roots)
    network = choose(args.red, detect(module, ["okhttp", "retrofit"]))
    retrofit = network and choose(args.retrofit, detect(module, ["retrofit"]))
    fragments = choose(args.fragments, detect(module, ["fragment", "appcompat"]))
    hilt = choose(args.hilt, detect(module, ["hilt"]))
    tags = set()
    if network:
        tags.add("red")
        if not hilt:
            tags.add("sinhilt")
    templates = ASSETS / "instrumentacion"
    package_path = pathlib.Path(*args.paquete.split("."))
    main_dir = main_source_dir(module, args.principal)
    files = [("SectionTracer.kt", "SectionTracer.kt"), ("NavigationTrace.kt", "NavigationTrace.kt"),
             ("MarkTrace.kt", "MarkTrace.kt"), ("PerfInstaller.kt", "PerfInstaller.kt"),
             ("ScreenTraceCallbacks.fragments.kt" if fragments else "ScreenTraceCallbacks.activities.kt",
              "ScreenTraceCallbacks.kt")]
    tests = [("SectionTracerTest.kt", "SectionTracerTest.kt")]
    mains = [("PerfHooks.kt", "PerfHooks.kt")]
    if network:
        files += [("HttpSectionName.retrofit.kt" if retrofit else "HttpSectionName.okhttp.kt", "HttpSectionName.kt"),
                  ("TraceEventListener.kt", "TraceEventListener.kt")]
        tests += [("TraceEventListenerTest.kt", "TraceEventListenerTest.kt")]
        if hilt:
            files.append(("PerfNetworkModule.kt", "PerfNetworkModule.kt"))
            mains.append(("PerfHooksModule.kt", "PerfHooksModule.kt"))
    plan = [(templates / src, module / args.fuente / package_path / dst) for src, dst in files]
    plan += [(templates / "main" / src, module / main_dir / package_path / dst) for src, dst in mains]
    # Si Gradle ya declara la variante profileable, su manifest solo necesita el <provider>.
    plan += [(templates / "manifests" / ("%s.xml" % kind), module / "src" / folder / "AndroidManifest.xml")
             for kind, folder in (("debug", "debug"), ("debug" if in_gradle else "profiling", variant))]
    if not args.sin_tests:
        plan += [(templates / "test" / src, module / args.tests / package_path / dst) for src, dst in tests]
    pending = []
    for source, target in plan:
        if target.exists():
            if args.actualizar and is_generated(target):
                target.write_text(render_template(source.read_text(encoding="utf-8"), args.paquete, tags), encoding="utf-8")
                print("~ actualizado: %s" % target)
            elif target.suffix == ".xml":
                lacks = target.parent.name == variant and not in_gradle \
                    and "<profileable" not in target.read_text(encoding="utf-8", errors="ignore")
                print("= ya existe, no se toca: %s (agrega el <provider> de abajo%s)" % (
                    target, " y <profileable android:shell=\"true\" />" if lacks else ""))
                pending.append("manifest")
            else:
                print("= ya existe, no se toca: %s%s" % (target, "" if is_generated(target) else " (no lo generó la skill)"))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_template(source.read_text(encoding="utf-8"), args.paquete, tags), encoding="utf-8")
        print("+ %s" % target)
    yes_no = lambda flag: "sí" if flag else "no"  # noqa: E731
    kind = "nueva"
    if existing:
        kind = ("existente: declara <profileable>, sin verificar que no sea depurable, no se crea otro build type"
                if unverified else "existente: profileable y no depurable, no se crea otro build type")
    print("Variante: %s (%s) · Red: %s · Retrofit: %s · Fragments: %s · Hilt: %s · código principal en %s" % (
        variant, kind, yes_no(network), yes_no(retrofit), yes_no(fragments), yes_no(hilt), main_dir))
    if unverified:
        print("⚠ %s declara <profileable> pero no pude verificar su build type (sabores u otro plugin): confirma que no "
              "sea depurable (isDebuggable) antes de medir" % variant)
    if len(modules) > 1:
        shown = ["%s (%s)" % m for m in modules[:12]]
        print("Módulos: %s%s. La instrumentación va en el módulo app (--modulo %s); las librerías emiten marcas por una interfaz." % (
            " · ".join(shown), " …" if len(modules) > 12 else "", module.as_posix()))
    if outside_roots:
        print("También busqué en lo que settings.gradle incluye desde fuera de la raíz: %s." % ", ".join(
            relative_to_root(path, root) for path in outside_roots))
    if unresolved_roots:
        print("⚠ No pude seguir estas rutas de settings.gradle (%s): si el punto de extensión de contenido visible o el "
              "OkHttpClient viven ahí, búscalos a mano en esas carpetas (una interfaz de pantalla o de contenido con "
              "multibinding; `OkHttpClient.Builder()`)." % ", ".join(unresolved_roots[:5]))
    if network and not scan["okhttp"]:
        print("⚠ El proyecto usa OkHttp pero no encontré dónde se arma el OkHttpClient: puede venir de una librería ya "
              "compilada. Sin acceso a su Builder no hay dónde poner el gancho: las métricas de red serán solo de punta "
              "a punta (sin secciones HTTP, QUEUE, CONN ni TTFB). Díselo al usuario; las alternativas están en setup.md "
              "· OkHttp dentro de una librería publicada.")
    outside = [(f, n) for f, n in scan["okhttp"] if not is_under(root / f, module)]
    if outside:
        print("⚠ OkHttpClient se arma fuera del módulo app (%s%s): PerfHooks y el multibinding de red viven en el código "
              "principal de la app y esos módulos no los ven, así que esas llamadas quedan sin secciones HTTP. Díselo al "
              "usuario: mide sin ellas, usa `perf.py har` con Chucker (medicion.md) o decidan mover el gancho a ese módulo."
              % (", ".join("%s:%d" % o for o in outside[:3]), " …" if len(outside) > 3 else ""))
    for other in found_variants:
        if other["nombre"] != variant and other["estado"] != "ok":
            print("  · %s también declara %s pero %s: no se usa" % (
                other["nombre"], "<profileable>" if other.get("manifest") and not other.get("gradle") else "que es profileable",
                "es depurable" if other["estado"] == "depurable" else "no pude verificar su build type"))
    by_name = scan["buildconfig"]["BUILD_TYPE"] + scan["buildconfig"]["FLAVOR"]
    depends_on_name = bool(by_name or name_logic) and not existing
    if depends_on_name:
        where = ["BuildConfig.BUILD_TYPE o FLAVOR en %s" % ", ".join("%s:%d" % use for use in by_name[:3])] if by_name else []
        where += ["lógica de Gradle por nombre en %s" % ", ".join("%s:%d" % (f, n) for f, n, _ in name_logic[:3])] if name_logic else []
        print("⚠ El proyecto parece decidir cosas por el nombre del build type o del sabor (%s). Un build type nuevo (\"%s\") "
              "tiene otro nombre: lo que dependa de él (configuración por ambiente, toggles, endpoints) puede quedar sin "
              "valor y romper el arranque o el login. Recomendado: no crees otro build type; mide sobre el que ya usas "
              "con una propiedad (-Pperf), el fragmento \"Alternativa\" de abajo. Si lo creas igual, revisa cada uno de "
              "esos puntos. La búsqueda es por texto: confirma que cada línea decide por un build type, un sabor o una "
              "variante (y no por otra cosa que también tenga nombre)." % ("; ".join(where), variant))
    if not existing:
        inherited = source_set_files(module, "release")
        if inherited:
            print("⚠ initWith(release) copia la configuración del build type, no su source set: lo que hay en "
                  "src/release/ no llega a \"%s\" (%s). Cópialo a src/%s/ o haz que ese source set lo incluya; lo mismo "
                  "con src/<otro>/ si heredas de otro build type." % (variant, ", ".join(inherited), variant))
    for path in debug_overrides(module, root, denied):
        print("⚠ %s usa <debug-overrides>: ese bloque solo aplica en builds depurables, y la variante medida no lo es. "
              "Lo que dependa de él (la CA de usuario de un proxy de pruebas, un certificado propio) deja de valer y la "
              "app puede no conectarse. Si las pruebas lo necesitan, propón una copia solo para la variante medida "
              "(src/%s/res/xml/%s, con esas reglas en <base-config>), nunca en release (setup.md · Lo que cambia al no "
              "ser depurable)." % (relative_to_root(path, root), variant, path.name))
    debug_uses = scan["buildconfig"]["DEBUG"]
    if debug_uses:
        print("BuildConfig.DEBUG se lee en %d lugar%s (%s%s): en la variante medida vale false. Revisa lo que dependa de él "
              "o del flag de depurable (logs, herramientas de depuración, endpoints o proxies de prueba)." % (
                  len(debug_uses), "" if len(debug_uses) == 1 else "es", ", ".join("%s:%d" % use for use in debug_uses[:3]),
                  ", …" if len(debug_uses) > 3 else ""))
    print("\nFalta pegar, con el paquete ya puesto (references/setup.md explica cada pieza):\n")
    snippets = [("1. %s (build.gradle.kts del módulo)" % ("Source set y cobertura de la variante %s" % variant if existing
                                                           else "Build type %s, source set y cobertura" % variant),
                 SNIPPETS["gradle_existente" if existing else "gradle"])]
    if depends_on_name:
        snippets.append(("Alternativa recomendada: medir sobre un build type que ya existe, con -Pperf (sin crear \"%s\")"
                         % variant, SNIPPETS["gradle_propiedad"]))
    if network:
        snippets.append(("2. Red: cada OkHttpClient pasa por el gancho", SNIPPETS["red_hilt" if hilt else "red_sinhilt"]))
    snippets.append(("%d. Navegación sin cambio de actividad (Compose, Navigation 3)" % (3 if network else 2), SNIPPETS["nav"]))
    hooks = scan["ganchos"]
    if hooks:
        snippets.append(("%d. Contenido visible: el proyecto ya tiene un punto de extensión (%d candidato%s): conecta ahí las "
                         "marcas" % (4 if network else 3, len(hooks), "" if len(hooks) == 1 else "s"),
                         hook_snippet(hooks, variant)))
    else:
        snippets.append(("%d. Contenido visible: reportFullyDrawn en la primera pantalla y PerfHooks.mark en las demás"
                         % (4 if network else 3), SNIPPETS["contenido"]))
        if len(modules) > 1:
            snippets.append(("Pantallas en módulos library: la marca sale por una interfaz que ellas sí ven", BRIDGE_SNIPPET))
    if any(scan["vistas"][name] for name in ("WebView", "RecyclerView")) or scan["vistas"]["RxJava"]:
        used = [name for name in ("WebView", "RecyclerView", "RxJava") if scan["vistas"][name]]
        snippets.append(("Pantallas con Views y RxJava (%s en %s): dónde va la marca" % (
            ", ".join(used), "el proyecto"), VIEWS_SNIPPET))
    if "manifest" in pending:
        snippets.append(("Manifest existente: agrega dentro de <application>",
                         '<provider android:name="{{PAQUETE}}.PerfInstaller" android:authorities="${applicationId}.perf-installer" '
                         'android:exported="false" />'))
    for title, body in snippets:
        print(title)
        print(textwrap.indent(body.replace("{{PAQUETE}}", args.paquete).replace("{{FUENTE}}", args.fuente)
                              .replace("{{VARIANTE}}", variant)
                              .replace("{{ESTADO}}", "declara <profileable> y no pude verificar que no sea depurable: confírmalo"
                                       if unverified else "ya es profileable y no depurable"), "   "))
        print()
    print("El `paquete` del plan es el applicationId de la variante %s (con su sufijo, si lo tiene); se instala con "
          "install%s." % (variant, variant[:1].upper() + variant[1:]))
    print("Después: el formateador del proyecto en una invocación de Gradle aparte y, en otra, el DoD más assemble%s "
          "con el log en un archivo (setup.md · DoD)." % (variant[:1].upper() + variant[1:]))


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
    p.add_argument("--triage", action="store_true", help="profundidad triage: 3 corridas, sin control, termina en el diagnóstico")
    p.add_argument("--no-leer", dest="no_leer", action="append", default=[], metavar="RUTA",
                   help="ruta o patrón que el agente no debe leer (pruebas a ciegas); se repite. Se suma a la línea "
                        "'No leer:' de AGENTS.md")
    p.set_defaults(func=cmd_nuevo)

    p = sub.add_parser("humo", help="prueba de humo del setup: una corrida de arranque que imprime métricas y marcas")
    p.add_argument("--paquete", required=True, help="applicationId del build de profiling instalado")
    p.add_argument("--serial", help="dispositivo (obligatorio con más de uno conectado)")
    p.add_argument("--carpeta", default="reports/perf/humo", help="dónde queda la traza de prueba")
    p.add_argument("--actividad", help="actividad de inicio (paquete/.Actividad); si no, la del launcher")
    p.add_argument("--espera", type=float, default=5)
    p.add_argument("--instalar", help="comando que compila e instala el build de profiling (se repite en el paso siguiente)")
    p.add_argument("--pedido", default="reports/perf/setup/pedido.json",
                   help="el flujo que se pidió en el setup ({\"flujo\", \"llegar\"}): con él, el paso siguiente es el chat "
                        "de la sesión 1 ya escrito")
    p.add_argument("--hz", type=int)
    p.add_argument("--tp")
    p.add_argument("--forzar", action="store_true")
    p.set_defaults(func=cmd_humo)

    p = sub.add_parser("siguiente", help="el paso que sigue, con sus comandos completos (también en estado.md)")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--flujo")
    p.set_defaults(func=cmd_siguiente)

    p = sub.add_parser("consumo", help="anota el costo de una sesión en la tabla Consumo de estado.md")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--sesion", required=True, help="por ejemplo '0 · setup' o '3 · M1'")
    p.add_argument("--costo", required=True, help="lo que muestre tu herramienta: '1.05 USD', '38k tokens', '12 créditos'")
    p.add_argument("--modelo", help="modelo usado en ese chat")
    p.add_argument("--pasos", help="requests o pasos del agente, si tu herramienta los muestra")
    p.set_defaults(func=cmd_consumo)

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
    p.add_argument("--recorrido", help="'manual' (Enter entre corridas) o un comando adb con los toques medidos (nunca Maestro)")
    p.add_argument("--preparar", help="comando que deja la app en el punto de partida antes de cada corrida (en vez del del plan)")
    p.add_argument("--config", help="configuración de Perfetto para esta captura (base, completa, cpu o una ruta)")
    p.add_argument("--serial")
    p.add_argument("--tp", help="ruta de trace_processor")
    p.add_argument("--hz", type=int, help="tasa de refresco del dispositivo (si no, la del plan o la de la traza)")
    p.add_argument("--memoria", action="store_true", help="agrega dumpsys meminfo después de cada corrida")
    p.add_argument("--sin-compilar", action="store_true", help="no fija la compilación de ART")
    p.add_argument("--sin-comprimir", action="store_true", help="deja las trazas sin gzip")
    p.add_argument("--prueba", action="store_true", help="una corrida que imprime las métricas y no escribe el CSV")
    p.add_argument("--forzar", action="store_true", help="sigue aunque el dispositivo esté caliente o el build no cambie")
    p.add_argument("--rehacer", action="store_true",
                   help="descarta lo medido de este flujo en esta fase y lo mide de nuevo (lo de otros flujos no se toca)")
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

    p = sub.add_parser("nodos", help="busca un nodo en un volcado de uiautomator y da el centro de sus bounds para tocarlo")
    p.add_argument("xml", help="archivo del volcado (uiautomator dump), por ejemplo <carpeta>/logs/ui.xml")
    p.add_argument("--texto", help="texto del nodo (contiene, sin distinguir mayúsculas)")
    p.add_argument("--id", help="resource-id del nodo, completo o solo lo que sigue a ':id/'")
    p.add_argument("--desc", help="content-desc del nodo (contiene, sin distinguir mayúsculas)")
    p.add_argument("--exacto", action="store_true",
                   help="el texto, el id o la descripción tienen que ser iguales (también en mayúsculas y minúsculas), no contener")
    p.add_argument("--volcar", action="store_true", help="vuelca primero la pantalla del dispositivo a ese archivo")
    p.add_argument("--serial", help="dispositivo para --volcar y para el comando de toque que imprime")
    p.add_argument("--limite", type=int, default=5)
    p.set_defaults(func=cmd_nodos)

    p = sub.add_parser("instrumentar", help="copia la instrumentación y el cableado genéricos a un módulo Android")
    p.add_argument("--modulo", required=True,
                   help="carpeta del módulo que genera el APK (el de com.android.application; normalmente app)")
    p.add_argument("--paquete", required=True, help="paquete Kotlin para las clases, por ejemplo com.ejemplo.app.perf")
    p.add_argument("--fuente", default="src/perf/kotlin")
    p.add_argument("--tests", default="src/testDebug/kotlin")
    p.add_argument("--red", dest="red", action="store_true", default=None)
    p.add_argument("--sin-red", dest="red", action="store_false")
    p.add_argument("--retrofit", dest="retrofit", action="store_true", default=None)
    p.add_argument("--sin-retrofit", dest="retrofit", action="store_false")
    p.add_argument("--fragments", dest="fragments", action="store_true", default=None)
    p.add_argument("--sin-fragments", dest="fragments", action="store_false")
    p.add_argument("--hilt", dest="hilt", action="store_true", default=None, help="gancho de red con un multibinding de Hilt")
    p.add_argument("--sin-hilt", dest="hilt", action="store_false", help="gancho de red con PerfHooks.okHttp")
    p.add_argument("--principal", help="carpeta del código principal (src/main/kotlin o src/main/java; si no, se detecta)")
    p.add_argument("--sin-tests", action="store_true")
    p.add_argument("--variante", help="build type que lleva la instrumentación (profileable y no depurable). Por defecto se "
                                      "reutiliza el que el módulo ya tenga; si no hay ninguno, se crea 'profiling'")
    p.add_argument("--no-leer", dest="no_leer", action="append", default=[], metavar="RUTA",
                   help="ruta o patrón que el escaneo no debe leer; se repite (se suma a la línea 'No leer:' de AGENTS.md)")
    p.add_argument("--actualizar", action="store_true",
                   help="sobrescribe los archivos que generó la skill (los que llevan su encabezado); nunca los del proyecto")
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
