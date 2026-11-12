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
  pausa         desde un recorrido: muestra un texto en la terminal y espera a la persona (un paso humano)
  salidas       por qué se cerró la app: sus últimas salidas según el sistema (Android 11+), con el motivo en claro

Códigos de salida: 0 bien · 2 uso o datos inválidos · 3 precondición (dispositivo, app o herramientas) ·
4 captura fallida · 5 no se juntaron las corridas válidas pedidas.
"""
import argparse
import csv
import datetime
import fnmatch
import gzip
import hashlib
import html
import json
import math
import os
import pathlib
import re
import select
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import uuid
import xml.etree.ElementTree as ElementTree
import zipfile
from urllib.parse import urlsplit

VERSION = "0.10.0"
# Versiones que capturan lo mismo que esta (las mismas configuraciones de Perfetto y las mismas definiciones de
# métricas): sus corridas se pueden completar sin repetir la fase.
SAME_CAPTURE = ("0.9.0", VERSION)
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
# Red por tramo: las llamadas HTTP que empiezan dentro de cada tramo, "<tramo> <métrica>".
SEGMENT_NETWORK = ("red_llamadas", "red_ms", "red_ttfb_ms", "red_repetidas_2s", "red_solapadas")
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
- **Métricas por tramo (`<tramo> …`):** el hilo principal y los frames solo entre dos marcas del flujo (una pantalla, un salto), contando lo que se solapa con ese tramo, para que un pico no se diluya en el recorrido completo.
- **Red por tramo (`<tramo> red_…`):** las llamadas de red que empiezan dentro de cada tramo: cuántas son, cuánto duran, cuánto tarda el servidor en responder (TTFB) y cuántas se repiten o se solapan.
- **Gráficos:** la barra es la mediana y la línea fina va de la corrida más rápida a la más lenta; la franja punteada marca el ruido de medición alrededor de antes. Debajo de cada gráfico, una frase dice qué muestra y qué significa.
- **Unidades:** los tiempos de un segundo o más van en segundos (`1.81 s`) y los más cortos en milisegundos (`450 ms`); el cambio, en porcentaje respecto de antes (`−39 %` es un 39 % menos).
- **Espera de servicios:** el tiempo del flujo en que hay al menos una llamada a un servicio en curso (lo que se solapa cuenta una vez). Depende del backend y de la red del momento: es informativa.
- **Servidor (TTFB) y en la app:** el servidor es la espera hasta el primer byte de la respuesta; en la app, la cola antes de salir, la conexión nueva y la lectura de la respuesta. Una mejora de la app mueve lo segundo, no lo primero.
- **Línea de tiempo:** una corrida representativa (la de duración mediana), con cada llamada a un servicio como una barra y las marcas de pantalla como líneas verticales; una llamada que empieza cuando terminaron todas las anteriores va en serie."""
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
# android.os.Trace.beginSection: el nombre de una sección admite hasta 127 unidades de código (documentación de la API).
SECTION_NAME_MAX = 127
e = html.escape


MAX_CONSECUTIVE_INVALID = 3
WARMUP_SETTLE_S = 2  # respiro después del calentamiento, antes del primer 'preparar' medido


def max_attempts(target):
    """Intentos totales de una captura: las corridas pedidas más una reserva de 3 como mínimo y de la mitad de las pedidas
    si son más (5 → 8, 10 → 15, 20 → 30). Así las inválidas sueltas de un backend inestable no cortan una captura larga;
    las seguidas ya las corta MAX_CONSECUTIVE_INVALID."""
    return target + max(3, target // 2)


class PerfError(Exception):
    """Un error con salida guiada: el manejador de main() imprime qué pasó (el mensaje), qué quedó guardado y el comando
    para seguir. `guardado` y `seguir` ([(para qué, comando)]) son opcionales: sin ellos valen los de GUIA."""
    code = 2
    guardado = None
    seguir = None

    def con(self, guardado=None, seguir=None):
        if guardado is not None:
            self.guardado = guardado
        if seguir is not None:
            self.seguir = list(seguir)
        return self


class Precondicion(PerfError):
    code = 3


class CapturaFallida(PerfError):
    code = 4


class CorridasInsuficientes(PerfError):
    code = 5


class CorridaDescartada(PerfError):
    """`perf.py pausa`: la persona respondió que la corrida no vale. El recorrido termina con 1 y la corrida se repite."""
    code = 1


# ── Salida guiada de los fallos ──────────────────────────────────────────────
# Todo comando que falla, se detiene o se interrumpe termina con tres cosas, en este orden: qué pasó, qué quedó guardado
# y el comando exacto para seguir. Se arma en un solo lugar (main), con lo que cada comando va dejando aquí mientras
# avanza: así ningún camino de error queda sin su comando.
GUIA = {"argv": [], "guardado": None, "seguir": None, "previos": [], "omitir": False, "al_fallar": None}
RETRY = "cuando lo corrijas, repite el comando"


def reset_guide(argv):
    GUIA.update({"argv": list(argv), "guardado": None, "seguir": None, "previos": [], "omitir": False, "al_fallar": None})


def same_command(corridas=None, sin=(), argv=None):
    """El comando que se está corriendo, listo para pegar: empieza con cd a la carpeta desde la que se corrió (las rutas
    relativas de sus argumentos parten de ahí; es la raíz del proyecto en los comandos que entrega la skill). `corridas`
    cambia --corridas y `sin` quita opciones sin valor (--rehacer)."""
    args, out, skip = list(GUIA["argv"] if argv is None else argv), [], False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in sin:
            continue
        if corridas is not None and (arg == "--corridas" or arg.startswith("--corridas=")):
            skip = arg == "--corridas"
            continue
        out.append(arg)
    if corridas is not None:
        out += ["--corridas", str(corridas)]
    return "cd %s && python3 -I %s %s" % (shlex.quote(os.getcwd()), shlex.quote(str(HERE / "perf.py")),
                                          " ".join(shlex.quote(arg) for arg in out))


def guide_lines(error=None):
    """Las líneas que cierran un fallo: qué quedó guardado y cómo seguir. Lo que trae el error gana a lo que dejó el
    comando en GUIA; sin nada, no quedó nada guardado y se repite el mismo comando. Antes corre lo que el comando dejó
    para un corte (`al_fallar`: guardar el registro de las corridas válidas), sin que un fallo ahí tape el original."""
    hook, GUIA["al_fallar"] = GUIA["al_fallar"], None
    if hook:
        try:
            hook()
        except Exception:  # lo que falle al guardar no puede tapar el fallo original ni dejarlo sin guía
            pass
    if GUIA["omitir"]:
        return []
    saved = getattr(error, "guardado", None) or GUIA["guardado"] or "nada"
    steps = getattr(error, "seguir", None) or GUIA["seguir"] or [(RETRY, same_command())]
    steps = list(GUIA["previos"]) + [step for step in steps if step not in GUIA["previos"]]
    lines = ["  Qué quedó guardado: %s." % saved.rstrip("."), "  Cómo seguir:"]
    for index, (what, command) in enumerate(steps, start=1):
        lines += ["  %d. Terminal · %s:" % (index, what[0].upper() + what[1:]), "     %s" % command]
    return lines


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
    """Las métricas de frames y de hilo de los tramos del flujo; un tramo `solo_red` no las tiene."""
    return ["%s %s" % (s["nombre"], m) for s in flow.get("segmentos") or [] if not s.get("solo_red")
            for m in SEGMENT_METRICS]


def segment_network_names(flow):
    return ["%s %s" % (s["nombre"], m) for s in flow.get("segmentos") or [] for m in SEGMENT_NETWORK]


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

LAST_BEFORE = "ultima_antes"  # en `desde`: la última ocurrencia de la marca antes de la marca `hasta` elegida


def check_marker(marker, start=False):
    """True si la marca es válida. `ultima_antes` solo vale en `desde` (start) de una ventana, una métrica de usuario o
    un tramo: en `hasta` y en las pausas no tiene sentido."""
    return bool(marker.get("marca")) and marker.get("punto", "inicio") in ("inicio", "fin") \
        and marker.get("cual", "primera") in (("primera", "ultima", LAST_BEFORE) if start else ("primera", "ultima"))


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
                if not check_marker(spec[side], start=side == "desde"):
                    raise PerfError("'%s.%s' en '%s': usa marca, punto (inicio|fin) y cual (primera|ultima; en 'desde', "
                                    "también ultima_antes: la última antes de la marca 'hasta')"
                                    % (spec["nombre"], side, name))
        segments = flow.get("segmentos") or []
        seen = set()
        for spec in segments if isinstance(segments, list) else [None]:
            if not isinstance(spec, dict) or not isinstance(spec.get("nombre"), str) \
                    or not SEGMENT_NAME.fullmatch(spec["nombre"]) or spec["nombre"] == "red" or spec["nombre"] in seen \
                    or not all(isinstance(spec.get(side), dict) and check_marker(spec[side], start=side == "desde")
                               for side in ("desde", "hasta")) \
                    or not check_margin(spec) or not isinstance(spec.get("solo_red", False), bool):
                raise PerfError("'%s.segmentos' es una lista de tramos: cada uno con 'nombre' (letras, números, _ o -; sin "
                                "repetir y distinto de 'red'), 'desde' y 'hasta' (marcas, como en metricas_usuario) y, si "
                                "quieres, 'margen_ms' (un número) y 'solo_red' (true o false)" % name)
            seen.add(spec["nombre"])
        pauses = flow.get("pausas") or []
        if not isinstance(pauses, list) or any(
                not isinstance(spec, dict) or not all(isinstance(spec.get(side), dict) and check_marker(spec[side])
                                                      for side in ("desde", "hasta")) for spec in pauses):
            raise PerfError("'%s.pausas' es una lista de {\"desde\", \"hasta\"} (marcas, como en metricas_usuario): el tiempo "
                            "entre las dos es de una persona (autorizar en otra app, resolver un desafío) y no se mide"
                            % name)
        crossing = static_pause_conflicts(flow)
        if crossing:
            raise PerfError("'%s': %s. Lo que pasa entre las dos marcas de una pausa es tiempo de una persona, no de la app: "
                            "termina la medición en la marca donde empieza la pausa o empiézala en la marca donde termina"
                            % (name, "; ".join(crossing)))
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
    if plan.get("mapping") is not None and not (isinstance(plan["mapping"], str) and plan["mapping"].strip()):
        raise PerfError("%s: 'mapping' es la ruta del mapping.txt de R8 de la variante medida (texto), por ejemplo "
                        "app/build/outputs/mapping/profiling/mapping.txt" % path)
    if plan.get("profundidad", "riguroso") not in ("riguroso", "triage"):
        raise PerfError("%s: 'profundidad' es riguroso o triage" % path)
    for name, flow in plan["flujos"].items():
        if flow.get("preparar") is not None and not isinstance(flow["preparar"], str):
            raise PerfError("%s: flujos.%s.preparar es un comando (texto) que deja la app en el punto de partida" % (path, name))
        needed = flow.get("requiere_env", [])
        if not isinstance(needed, list) or any(not isinstance(v, str) or not ENV_NAME.fullmatch(v) for v in needed):
            raise PerfError("%s: flujos.%s.requiere_env es una lista de nombres de variables de entorno, por ejemplo "
                            "[\"PERF_USUARIO\", \"PERF_CLAVE\"] (los nombres, nunca los valores)" % (path, name))
        cap = flow.get("duracion_max_s")
        if cap is not None and not (isinstance(cap, (int, float)) and not isinstance(cap, bool) and 1 <= cap <= 86400):
            raise PerfError("%s: flujos.%s.duracion_max_s es el tope de la traza en segundos (un número entre 1 y 86400; "
                            "sin él, 600): súbelo si el recorrido tiene pausas humanas" % (path, name))
        window = flow.get("ventana")
        if window is not None and not (isinstance(window, dict) and "desde" in window and "hasta" in window):
            raise PerfError("%s: flujos.%s.ventana necesita 'desde' y 'hasta' (marcas, como metricas_usuario)" % (path, name))
        if window is not None and not check_margin(window):
            raise PerfError("%s: flujos.%s.ventana.margen_ms es un número de milisegundos" % (path, name))
        if window is not None and isinstance(window.get("hasta"), dict) and window["hasta"].get("cual") == LAST_BEFORE:
            raise PerfError("%s: flujos.%s.ventana.hasta: 'cual': 'ultima_antes' solo vale en 'desde' (la última ocurrencia "
                            "antes de la marca 'hasta')" % (path, name))
    if plan.get("input_slices") is not None and not (isinstance(plan["input_slices"], str)
                                                     and INPUT_GLOB.fullmatch(plan["input_slices"])):
        raise PerfError("%s: 'input_slices' es un patrón GLOB con el nombre de los slices de input (por defecto %s)"
                        % (path, INPUT_SLICES))
    labels = plan.get("etiquetas", {})
    if not isinstance(labels, dict) or any(not isinstance(v, str) or not v.strip() for v in labels.values()):
        raise PerfError("%s: 'etiquetas' es un objeto {\"<métrica>\": \"<cómo se llama para un lector no técnico>\"}: "
                        "lo usa el reporte para gerencia en vez del nombre de la métrica" % path)
    if not isinstance(plan.get("modelos", {}), dict):
        raise PerfError("%s: 'modelos' es un objeto con economico, intermedio, alto y, si quieres, diagnostico" % path)
    cli = plan.get("modelos_cli", {})
    if not isinstance(cli, dict) or any(not isinstance(ids, dict) for ids in cli.values()):
        raise PerfError("%s: 'modelos_cli' es un objeto por herramienta (claude, copilot) con el id de cada nivel: "
                        "{\"copilot\": {\"intermedio\": \"claude-sonnet-5.5\"}}" % path)
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


def measured_spans(flow):
    """[(cómo se llama en los mensajes, spec)] de lo que el flujo mide entre dos marcas: la ventana, las métricas de
    usuario y los tramos."""
    spans = [("la ventana", flow["ventana"])] if isinstance(flow.get("ventana"), dict) else []
    spans += [("la métrica '%s'" % spec.get("nombre"), spec) for spec in flow.get("metricas_usuario") or []
              if isinstance(spec, dict)]
    spans += [("el tramo '%s'" % spec.get("nombre"), spec) for spec in flow.get("segmentos") or [] if isinstance(spec, dict)]
    return [(label, spec) for label, spec in spans
            if isinstance(spec.get("desde"), dict) and isinstance(spec.get("hasta"), dict)]


def static_pause_conflicts(flow):
    """Lo que se sabe sin una traza: una ventana, una métrica o un tramo que empieza en la marca donde empieza una
    pausa, o que termina en la marca donde termina, mide tiempo humano. El resto de los cruces solo se ven con las
    marcas en orden: los detecta pause_conflicts sobre cada traza."""
    found = []
    for pause in flow.get("pausas") or []:
        for label, spec in measured_spans(flow):
            if spec["desde"].get("marca") == spec["hasta"].get("marca"):
                continue  # mide una sola sección (una llamada, por ejemplo): si cruza la pausa lo dice la traza
            if spec["desde"].get("marca") == pause["desde"].get("marca") \
                    or spec["hasta"].get("marca") == pause["hasta"].get("marca"):
                found.append("%s cruza la pausa de '%s' a '%s'" % (label, pause["desde"]["marca"], pause["hasta"]["marca"]))
    return found


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


def call_flags(calls):
    """[(solapada, repetida)] por llamada, en el orden de `calls`: solapada si empieza mientras otra con la misma
    plantilla y la misma query sigue en vuelo; repetida si empieza menos de 2 s después de la anterior igual."""
    flags = [[False, False] for _ in calls]
    by_key = {}
    for index, call in enumerate(calls):
        by_key.setdefault(call_key(call[4]), []).append(index)
    for indexes in by_key.values():  # la misma plantilla y la misma query: una carga duplicada
        indexes.sort(key=lambda i: calls[i][1])
        for position, i in enumerate(indexes):
            start = calls[i][1]
            if any(calls[p][2] > 0 and calls[p][1] < start < calls[p][1] + calls[p][2] for p in indexes[:position]):
                flags[i][0] = True
            if position > 0 and start - calls[indexes[position - 1]][1] < DUPLICATE_WINDOW_NS:
                flags[i][1] = True
    return [tuple(flag) for flag in flags]


def segment_network(markers, sections, specs, always=False):
    """Red por tramo. Cada llamada HTTP va al tramo donde empieza (si dos tramos se solapan, al primero del plan). Por
    tramo: cuántas llamadas, la mediana de su duración y de su TTFB, y cuántas son repetidas o solapadas (las mismas que
    cuenta la corrida entera). Las métricas salen para todos los tramos si `always` (la corrida tiene red) y siempre
    para los `solo_red`. Devuelve (métricas, detalle por tramo para el diagnóstico, llamadas fuera de los tramos)."""
    calls = sorted((s for s in sections if s[4].startswith("HTTP ")), key=lambda s: s[1])
    flags = call_flags(calls)
    ttfb = assign(calls, [s for s in sections if s[4].startswith("TTFB ")])
    bounds = [(spec, resolve_window(markers, spec)) for spec in specs]
    owner = {}
    for index, call in enumerate(calls):
        owner[index] = next((spec["nombre"] for spec, limits in bounds if limits and limits[0] <= call[1] <= limits[1]), None)
    out, detail = [], []
    for spec, limits in bounds:
        name = spec["nombre"]
        if not limits:
            continue
        mine = [i for i in range(len(calls)) if owner[i] == name]
        durations = [calls[i][2] / 1e6 for i in mine if calls[i][2] > 0]
        waits = [ttfb[i] / 1e6 for i in mine if ttfb[i]]
        endpoints = {}
        for i in mine:
            endpoints[endpoint_of(calls[i][4])] = endpoints.get(endpoint_of(calls[i][4]), 0) + 1
        row = {"tramo": name, "llamadas": len(mine), "endpoints": endpoints, "limites": limits,
               "ms": statistics.median(durations) if durations else None,
               "ttfb_ms": statistics.median(waits) if waits else None,
               "repetidas": sum(1 for i in mine if flags[i][1]), "solapadas": sum(1 for i in mine if flags[i][0])}
        detail.append(row)
        if not (always or spec.get("solo_red")):
            continue
        out.append(("%s red_llamadas" % name, row["llamadas"], "llamadas", "app"))
        if durations:
            out.append(("%s red_ms" % name, row["ms"], "ms", "e2e"))
        if waits:
            out.append(("%s red_ttfb_ms" % name, row["ttfb_ms"], "ms", "e2e"))
        out += [("%s red_repetidas_2s" % name, row["repetidas"], "llamadas", "app"),
                ("%s red_solapadas" % name, row["solapadas"], "llamadas", "app")]
    outside = {}
    for index, call in enumerate(calls):
        if owner[index] is None:
            outside[endpoint_of(call[4])] = outside.get(endpoint_of(call[4]), 0) + 1
    return out, detail, outside


def network_metrics(sections, known_endpoints, force):
    """Llamadas, solapadas, repetidas, conexiones y, por endpoint: llamadas, duración, TTFB, cola y cliente."""
    calls = [s for s in sections if s[4].startswith("HTTP ")]
    if not calls and not known_endpoints and not force:
        return []
    subs = {kind: [s for s in sections if s[4].startswith(kind + " ")] for kind in ("TTFB", "QUEUE", "CONN")}
    out = [("red_llamadas", len(calls), "llamadas", "app")]
    flags = call_flags(calls)
    out.append(("red_solapadas", sum(1 for overlapped, _ in flags if overlapped), "llamadas", "app"))
    out.append(("red_repetidas_2s", sum(1 for _, repeated in flags if repeated), "llamadas", "app"))
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


def service_metrics(sections, known_endpoints, by_segment, origin=None):
    """Lo que el reporte "Servicios del flujo" necesita de cada servicio y las métricas de red de siempre no traen: sus
    llamadas repetidas y solapadas (las mismas que cuenta la corrida entera, por endpoint), su conexión nueva y en qué
    tramo se llama (`<tramo> red <servicio> llamadas`, informativa). Con `origin` (el inicio de la ventana del flujo o,
    sin ventana, el de la traza, en ns), también cuándo se llama: el inicio de su primera llamada y el fin de la última
    (`red <servicio> inicio_ms` y `fin_ms`), el tiempo con al menos una llamada en curso (`red_en_curso_ms`) y dónde
    empieza y termina cada tramo (`<tramo> inicio_ms` y `fin_ms`), para ordenar los servicios por invocación y dibujar
    la línea de tiempo. Todo es informativo y va al final de las métricas de la corrida: las que ya existían no
    cambian de nombre, de valor ni de orden."""
    calls = [s for s in sections if s[4].startswith("HTTP ")]
    if not calls and not known_endpoints:
        return []
    flags = call_flags(calls)
    connections = [s for s in sections if s[4].startswith("CONN ")]
    owned = assign(calls, connections)
    waits = assign(calls, [s for s in sections if s[4].startswith("TTFB ")])
    by_endpoint = {}
    for i, call in enumerate(calls):
        by_endpoint.setdefault(endpoint_of(call[4]), []).append(i)
    out = []
    for endpoint in sorted(set(by_endpoint) | set(known_endpoints)):
        indexes = by_endpoint.get(endpoint, [])
        out.append(("red %s repetidas_2s" % endpoint, sum(1 for i in indexes if flags[i][1]), "llamadas", "app"))
        out.append(("red %s solapadas" % endpoint, sum(1 for i in indexes if flags[i][0]), "llamadas", "app"))
        served = [i for i in indexes if calls[i][2] > 0 and waits[i]]  # las mismas llamadas que miden cola y lectura
        if connections and served:  # 0 si la llamada reutilizó una conexión
            out.append(("red %s conexion_ms" % endpoint, statistics.median(owned[i] / 1e6 for i in served), "ms", "e2e"))
    for row in by_segment:
        out += [("%s red %s llamadas" % (row["tramo"], endpoint), count, "llamadas", "info")
                for endpoint, count in sorted(row["endpoints"].items())]
    if origin is None:
        return out
    timed = sorted((call[1], call[1] + call[2]) for call in calls if call[2] > 0)
    for endpoint in sorted(by_endpoint):
        spans = [(calls[i][1], calls[i][1] + max(calls[i][2], 0)) for i in by_endpoint[endpoint]]
        out.append(("red %s inicio_ms" % endpoint, (min(start for start, _ in spans) - origin) / 1e6, "ms", "info"))
        out.append(("red %s fin_ms" % endpoint, (max(end for _, end in spans) - origin) / 1e6, "ms", "info"))
    if timed:
        busy, current = 0, None
        for start, end in timed:  # la unión de las llamadas: lo que se solapa cuenta una vez
            if current is None or start > current[1]:
                busy += (current[1] - current[0]) if current else 0
                current = [start, end]
            else:
                current[1] = max(current[1], end)
        busy += current[1] - current[0]
        out.append(("red_en_curso_ms", busy / 1e6, "ms", "info"))
    for row in by_segment:
        if row.get("limites"):
            out += [("%s inicio_ms" % row["tramo"], (row["limites"][0] - origin) / 1e6, "ms", "info"),
                    ("%s fin_ms" % row["tramo"], (row["limites"][1] - origin) / 1e6, "ms", "info")]
    return out


TIMELINE_CALLS_MAX = 80
TIMELINE_MARKS_MAX = 25
TIMELINE_SUFFIX = ".linea.json"


def run_timeline(sections, origin):
    """La línea de tiempo de una corrida para el reporte: cada llamada HTTP (servicio, inicio y fin en ms desde el inicio
    de la ventana del flujo o, sin ventana, de la traza) y la primera vez que sale cada marca de pantalla (SCREEN, NAV y
    MARK). Va a un archivo aparte, no a metricas.csv: no es una métrica."""
    calls = [[endpoint_of(s[4]), round((s[1] - origin) / 1e6, 1), round((s[1] + max(s[2], 0) - origin) / 1e6, 1)]
             for s in sections if s[4].startswith("HTTP ")]
    marks, seen = [], set()
    for s in sections:
        if s[4].startswith(("SCREEN ", "NAV ", "MARK ")) and s[4] not in seen and s[1] >= origin:
            seen.add(s[4])
            marks.append([s[4], round((s[1] - origin) / 1e6, 1)])
    return {"llamadas": sorted(calls, key=lambda c: c[1])[:TIMELINE_CALLS_MAX], "marcas": marks[:TIMELINE_MARKS_MAX]}


def save_timeline(out_dir, flow, run, timeline):
    """Guarda la línea de tiempo de una corrida junto a su traza (<flujo>_<n>.linea.json). Si falla, no frena la captura."""
    if not timeline:
        return
    try:
        (pathlib.Path(out_dir) / ("%s_%s%s" % (flow, run, TIMELINE_SUFFIX))).write_text(
            json.dumps(timeline, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_timeline(folder, phase, flow, run):
    try:
        data = json.loads((pathlib.Path(folder) / phase / ("%s_%s%s" % (flow, run, TIMELINE_SUFFIX))).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("llamadas"), list) else None


def resolve_marker(sections, marker, default_point, default_which, after=None, before=None):
    """El momento (ns) de la ocurrencia elegida de una marca, o None si no está. El nombre de la marca se compara con
    fnmatch (exacto, o un patrón con * y ?, distinguiendo mayúsculas). `after` y `before` acotan las ocurrencias."""
    point = marker.get("punto", default_point)
    which = marker.get("cual", default_which)
    times = [s[1] if point == "inicio" else s[1] + max(s[2], 0) for s in sections
             if fnmatch.fnmatchcase(s[4], marker["marca"])]
    if after is not None:
        times = [t for t in times if t >= after]
    if before is not None:
        times = [t for t in times if t <= before]
    if not times:
        return None
    return min(times) if which == "primera" else max(times)


def resolve_span(sections, spec):
    """(inicio, fin) en ns de lo que se mide entre dos marcas (una ventana, una métrica de usuario o un tramo); None en
    el que no tenga su marca. Lo normal: se elige `desde` (por defecto la primera ocurrencia) y `hasta` se busca después
    de él (por defecto la última). Con `"cual": "ultima_antes"` en `desde` es al revés: primero `hasta`, entre todas sus
    ocurrencias, y `desde` es la última ocurrencia de su marca que no queda después de ese momento. Sirve cuando la
    marca de inicio sale varias veces (cada letra de una búsqueda) y la que importa es la que precede al resultado: se
    elige en el plan, sin tocar la app."""
    if spec["desde"].get("cual") == LAST_BEFORE:
        end = resolve_marker(sections, spec["hasta"], "fin", "ultima")
        start = resolve_marker(sections, spec["desde"], "inicio", LAST_BEFORE, before=end) if end is not None else None
        return start, end
    start = resolve_marker(sections, spec["desde"], "inicio", "primera")
    end = resolve_marker(sections, spec["hasta"], "fin", "ultima", after=start) if start is not None else None
    return start, end


def user_metric_bounds(sections, spec):
    """(inicio, fin) en ns de una métrica de usuario; None en el que no tenga su marca."""
    return resolve_span(sections, spec)


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
    start, end = resolve_span(markers, spec)
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
        if spec.get("solo_red"):  # solo agrupa llamadas de red (segment_network): sin frames, hilo ni jank
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


def pause_bounds(markers, pause):
    """(inicio, fin) en ns del tiempo humano de una pausa: del fin de la marca donde empieza al inicio de la marca
    donde termina. Las dos marcas quedan fuera, así que una medición puede terminar en la primera y otra empezar en la
    segunda (una marca real dura algo: son un beginSection y un endSection). None si falta alguna."""
    start = resolve_marker(markers, pause["desde"], "fin", "primera")
    end = resolve_marker(markers, pause["hasta"], "inicio", "primera", after=start) if start is not None else None
    return (start, end) if start is not None and end is not None and end > start else None


def span_bounds(markers, spec):
    """(inicio, fin) en ns de una ventana, una métrica de usuario o un tramo, de marca a marca y sin su `margen_ms`."""
    start, end = resolve_span(markers, spec)
    return (start, end) if start is not None and end is not None and end > start else None


def pause_conflicts(markers, flow_spec):
    """Lo que el flujo mide (la ventana, una métrica de usuario, un tramo) y que en esta traza se solapa con una pausa
    declarada en `pausas`: incluye tiempo de una persona. Se compara de marca a marca: el `margen_ms` no cuenta, y
    compartir una marca de borde con la pausa tampoco. Textos para el mensaje de error; vacío si no hay ninguno."""
    found = []
    for pause in flow_spec.get("pausas") or []:
        limits = pause_bounds(markers, pause)
        if not limits:
            continue
        for label, spec in measured_spans(flow_spec):
            span = span_bounds(markers, spec)
            if span and span[0] < limits[1] and span[1] > limits[0]:
                found.append("%s cruza la pausa de '%s' a '%s'" % (label, pause["desde"]["marca"], pause["hasta"]["marca"]))
    return found


def plan_marks(flow_spec):
    """[(marca, [dónde la usa el plan])] de las marcas de la ventana, las métricas de usuario, los tramos y las pausas
    del flujo, sin repetir y en el orden del plan."""
    uses = {}

    def add(marker, where):
        if isinstance(marker, dict) and marker.get("marca"):
            uses.setdefault(marker["marca"], []).append(where)

    for label, specs in (("ventana", [flow_spec.get("ventana")]), (None, flow_spec.get("metricas_usuario") or []),
                         ("tramo %s", flow_spec.get("segmentos") or []), ("pausa %d", flow_spec.get("pausas") or [])):
        for number, spec in enumerate(specs, start=1):
            if not isinstance(spec, dict):
                continue
            name = spec.get("nombre") if label is None else label % spec.get("nombre") if label == "tramo %s" else \
                label % number if "%d" in label else label
            for side in ("desde", "hasta"):
                add(spec.get(side), "%s.%s" % (name, side))
    return list(uses.items())


def marks_report(info):
    """Las líneas con las que la corrida de prueba dice qué marcas del plan salieron (✔) y cuáles no (✖), hasta dónde
    llegó el recorrido (la última marca propia y su momento), cuánto dura la traza y cuántas secciones HTTP trae."""
    lines = []
    for mark, where, seen in info.get("marcas_plan") or []:
        lines.append("  %s %s (%s)%s" % ("✔" if seen else "✖", mark, ", ".join(where), "" if seen else " · no salió en la traza"))
    for pattern, hit in info.get("invalidan") or []:
        lines.append("  %s invalidar_si %s · %s" % ("✖" if hit else "✔", pattern,
                                                    "apareció '%s': la corrida no vale" % hit if hit else "no apareció"))
    if lines:
        lines.insert(0, "Marcas del plan:")
    last = info.get("ultima_marca")
    tail = ["última marca vista: %s a los %s s" % (last[0], fmt(last[1])) if last else
            "ninguna marca propia (SCREEN, NAV, MARK) en la traza"]
    if info.get("duracion_s"):
        tail.append("la traza dura %s s" % fmt(info["duracion_s"]))
    tail.append("secciones HTTP: %d" % info.get("http", 0))
    lines.append("Recorrido: " + " · ".join(tail))
    return lines


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
    # Una marca de inicio que el plan elige con `ultima_antes` sale varias veces a propósito: no es un gancho mal puesto.
    chosen = [spec["desde"]["marca"] for _, spec in measured_spans(flow_spec) if spec["desde"].get("cual") == LAST_BEFORE]
    info = {"frames": len(frames), "secciones": len(sections), "input": len(inputs),
            "marcas_repetidas": {name: count for name, count in repeated_marks(sections).items()
                                 if not any(fnmatch.fnmatchcase(name, str(pattern)) for pattern in chosen)},
            "duracion_s": bounds[0][2] / 1e9 if bounds and bounds[0][2] > 0 else None,
            "nombres": {}, "hz_traza": hz_from_vsync(vsync), "arranque": bool(launches)}
    hz = hz or info["hz_traza"] or 60
    info["hz"] = hz
    budget = 1e9 / hz
    for s in sections:
        info["nombres"][s[4]] = info["nombres"].get(s[4], 0) + 1
    markers = sorted(sections + main + launches, key=lambda r: r[1])
    # Lo que la corrida de prueba informa aunque la corrida no valga: qué marcas del plan salieron y hasta dónde llegó.
    info["marcas_plan"] = [(mark, where, any(fnmatch.fnmatchcase(m[4], mark) for m in markers))
                           for mark, where in plan_marks(flow_spec)]
    info["invalidan"] = [(pattern, next((s[4] for s in sections if fnmatch.fnmatchcase(s[4], pattern)), None))
                         for pattern in flow_spec.get("invalidar_si", [])]
    own = [s for s in sections if s[4].startswith(("SCREEN ", "NAV ", "MARK ", "reportFullyDrawn"))]
    origin = bounds[0][1] if bounds else min((r[1] for r in rows if r[0] in ("seccion", "hilo", "frame")), default=0)
    info["ultima_marca"] = (own[-1][4], (own[-1][1] - origin) / 1e9) if own else None
    info["http"] = sum(1 for s in sections if s[4].startswith("HTTP "))
    info["cruzan_pausa"] = pause_conflicts(markers, flow_spec)
    if not process:
        return [], "la app no aparece en la traza", info
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
    specs = flow_spec.get("segmentos") or []
    segments, missing_segments = segment_metrics(markers, all_frames, all_main, specs)
    out += segments
    has_network = any(s[4].startswith("HTTP ") for s in sections) or "red_llamadas" in known
    by_segment, info["red_por_tramo"], info["red_fuera"] = segment_network(markers, sections, specs, always=has_network)
    out += by_segment
    # al final: lo anterior no cambia de orden. El origen de los momentos es el inicio de la ventana o, sin ella, de la traza.
    out += service_metrics(sections, known_endpoints, info["red_por_tramo"], window[0] if window else origin)
    info["linea"] = run_timeline(sections, window[0] if window else origin)
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
        result = subprocess.run(self.base + list(args), input=stdin, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0 and ADB_GONE.search(result.stderr or ""):
            raise Precondicion(device_gone(result.stderr))
        return result

    def shell(self, command, stdin=None, timeout=120):
        return self.run("shell", command, stdin=stdin, timeout=timeout)


# Lo que adb escribe cuando el dispositivo dejó de estar disponible a mitad de un comando.
ADB_GONE = re.compile(r"device '[^']*' not found|device offline|device unauthorized|no devices/emulators found|"
                      r"device still authorizing")
ADB_STATES = {"unauthorized": "sin autorizar: acepta en su pantalla el diálogo \"¿Permitir depuración USB?\" (si no "
                              "aparece, desconecta y conecta el cable, o revoca las autorizaciones en Opciones de desarrollador)",
              "offline": "sin responder (offline): desconecta y conecta el cable, o reinicia adb con `adb kill-server`",
              "authorizing": "esperando la autorización: acepta el diálogo de depuración USB en su pantalla"}


def device_gone(stderr):
    """El mensaje de un dispositivo que dejó de responder a adb en medio de un comando."""
    detail = (stderr or "").strip().splitlines()[-1][:160] if (stderr or "").strip() else "sin detalle"
    return ("el dispositivo dejó de estar disponible para adb (%s): se desconectó el cable, se apagó o perdió la "
            "autorización de depuración USB. Comprueba que `adb devices` lo liste como 'device'" % detail)


def unavailable_devices(listing):
    """{serial: por qué no sirve} de los dispositivos que `adb devices` lista sin estar listos (sin autorizar, offline)."""
    out = {}
    for line in listing.splitlines()[1:]:
        serial, _, state = line.partition("\t")
        if serial.strip() and state.strip() in ADB_STATES:
            out[serial.strip()] = ADB_STATES[state.strip()]
    return out


def select_device(serial):
    """--serial, el 'serial' del plan o ANDROID_SERIAL; si no, el único dispositivo conectado."""
    serial = serial or os.environ.get("ANDROID_SERIAL")
    result = subprocess.run([adb_binary(), "devices"], capture_output=True, text=True, timeout=60)
    devices = [line.split("\t")[0] for line in result.stdout.splitlines()[1:] if line.endswith("\tdevice")]
    unavailable = unavailable_devices(result.stdout)
    if serial:
        if serial in unavailable:
            raise Precondicion("el dispositivo %s está conectado pero %s" % (serial, unavailable[serial]))
        if serial not in devices:
            raise Precondicion("el dispositivo %s no está conectado (conectados: %s): revisa el cable y la depuración USB"
                               % (serial, ", ".join(devices) or "ninguno"))
        return serial
    if not devices and unavailable:
        raise Precondicion("; ".join("el dispositivo %s está conectado pero %s" % item for item in unavailable.items()))
    if not devices:
        raise Precondicion("no hay ningún dispositivo conectado con depuración USB autorizada (adb devices)")
    if len(devices) > 1:
        raise Precondicion("hay %d dispositivos conectados (%s): elige uno con --serial, o guárdalo en el plan con "
                           "'nuevo --serial'" % (len(devices), ", ".join(devices))).con(seguir=[
            ("mira cuál es cuál (el serial es la primera columna)", "cd %s && adb devices -l" % shlex.quote(os.getcwd())),
            ("repite el comando con el serial que corresponda", same_command() + " --serial <serial>")])
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
    build = package_build(dump)
    if flags:  # sin la línea de flags no se sabe: el dato no se guarda (ausente no es "no depurable")
        build["depurable"] = "DEBUGGABLE" in flags.group(1)
    if build.get("depurable"):
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
    return sdk, warnings, build


def debuggable_stop(folder, phase, flow, build, plan, redo=False):
    """El motivo para no medir una fase con un build depurable, o None. Detiene si las fases que ese flujo ya tiene
    medidas usaron un build no depurable, o si el plan instala otra variante (`instalar` con una tarea install<Variante>
    que no es la de depuración): mezclar los dos builds da tiempos que no se comparan. Un registro sin el dato (de una
    versión anterior) no cuenta como "no depurable"."""
    if not build.get("depurable"):
        return None
    earlier = None
    for name, record in read_phases(folder).items():
        if name not in FASES or not isinstance(record, dict) or (name == phase and redo):
            continue
        tracked = record.get("flujos")
        if flow and tracked and flow not in tracked:
            continue
        # El build de ese flujo si el registro lo guarda por flujo; si no, el de la fase.
        own = (tracked or {}).get(flow) if isinstance(tracked, dict) else None
        source = own if isinstance(own, dict) and "depurable" in own else record
        if source.get("depurable") is False:
            earlier = (name, record)
            break
    variant = install_variant((plan or {}).get("instalar"))[1]
    declared = bool(variant) and "debug" not in variant.lower()
    if not earlier and not declared:
        return None
    installed = "%s, instalado %s" % (build.get("version") or "?", build.get("instalada") or "sin fecha")
    against = ("la fase %s de este flujo se midió con un build no depurable (%s, instalado %s)"
               % (earlier[0], earlier[1].get("version") or "?", earlier[1].get("instalada") or "sin fecha")) if earlier \
        else "el plan mide la variante '%s' (su comando 'instalar')" % variant
    return ("el build instalado es depurable (%s) y %s: con un build depurable los tiempos y los frames no valen ni se "
            "comparan con los de otra fase. Causa típica: el botón de ejecutar del IDE instala la variante de depuración, "
            "sin la propiedad de medición que lleva el comando 'instalar' del plan. Instala de nuevo el build de medición; "
            "con --forzar se mide igual (solo valen los conteos de red y las fugas)" % (installed, against))


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
    network = ("sí sirve para el comportamiento de la red (qué llamadas hace, cuántas y en qué orden), los conteos "
               "(inflates) y las fugas")
    if env["software"]:
        return ["el dispositivo renderiza por software (%s): los frames (jank_*, frame_*, gfx_*) no son confiables y los "
                "reportes los marcan; %s" % (env["render"] or "sin dato", gpu)] + (
            ["es un emulador: sus tiempos de frames, de hilo principal y de carga no representan un teléfono; %s" % network]
            if env["emulador"] else [])
    if env["emulador"]:
        return ["es un emulador%s: sus tiempos de frames, de hilo principal y de carga no representan un teléfono (son "
                "orientativos); %s. Para decidir con tiempos o con frames, %s"
                % (" (render: %s)" % env["render"] if env["render"] else "", network, gpu)]
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


# Opciones de desarrollador que cambian lo que se mide (Settings.Global): "No conservar actividades" destruye cada
# actividad al salir de ella y las escalas de animación alargan o acortan las transiciones. Sin valor ("null") rige el
# de fábrica, que es el normal: 0 y 1.
DEV_SETTINGS = (("always_finish_activities", "No conservar actividades", "0"),
                ("window_animation_scale", "Escala de animación de ventana", "1"),
                ("transition_animation_scale", "Escala de transición-animación", "1"),
                ("animator_duration_scale", "Escala de duración de animador", "1"))


# "No conservar actividades" lo aplica el interruptor de Opciones de desarrollador: un valor escrito con `settings put`
# puede no aplicarse hasta reiniciar, y volver a leerlo con `settings get` no lo detecta. Por eso el paso pide también
# el interruptor (o reiniciar).
ALWAYS_FINISH_NOTE = ("si \"No conservar actividades\" estaba activa, desactívala también desde Ajustes > Opciones de "
                      "desarrollador (o reinicia el dispositivo): el sistema puede no aplicar el cambio hasta entonces")
DEV_SETTINGS_WHY = ("'No conservar actividades' recrea cada pantalla al volver a ella y las escalas de animación cambian "
                    "la duración de las transiciones: los tiempos no son los de un usuario")


def read_dev_settings(adb):
    """{ajuste: valor} de las opciones de desarrollador que cambian la medición, en una sola llamada a adb y fuera de
    toda traza. Un ajuste sin valor queda como "null"; si adb no contesta, {}."""
    script = "; ".join('echo "%s=$(settings get global %s)"' % (name, name) for name, _, _ in DEV_SETTINGS)
    try:
        out = adb.shell(script, timeout=30).stdout or ""
    except (subprocess.SubprocessError, OSError):
        return {}
    return parse_dev_settings(out)


def parse_dev_settings(text):
    known = {name for name, _, _ in DEV_SETTINGS}
    found = {}
    for key, value in re.findall(r"^([a-z_]+)=(.*)$", text or "", re.M):
        if key in known:
            found[key] = value.strip() or "null"
    return found


def dev_setting_normal(name, value):
    """True si el ajuste tiene el valor de fábrica (o no tiene valor, que es lo mismo)."""
    normal = next(default for key, _, default in DEV_SETTINGS if key == name)
    if value in (None, "", "null"):
        return True
    try:
        return float(value) == float(normal)
    except ValueError:
        return False


def dev_settings_off(settings):
    """[(ajuste, rótulo, valor, normal)] de los ajustes que no están en su valor normal."""
    return [(name, label, settings[name], normal) for name, label, normal in DEV_SETTINGS
            if name in (settings or {}) and not dev_setting_normal(name, settings[name])]


def dev_settings_text(settings):
    """Los ajustes como texto corto: "No conservar actividades = 1, Escala de animación de ventana = 0.5"."""
    return ", ".join("%s = %s" % (label, value) for _, label, value, _ in dev_settings_off(settings))


def dev_settings_commands(settings, serial, root):
    """(dejarlos normales, volverlos a como estaban): los dos comandos completos para los ajustes fuera de lo normal."""
    off = dev_settings_off(settings)
    target = "adb%s shell" % (" -s %s" % shlex.quote(serial) if serial else "")
    fix = " && ".join("%s settings put global %s %s" % (target, name, normal) for name, _, _, normal in off)
    back = " && ".join("%s settings put global %s %s" % (target, name, shlex.quote(value)) for name, _, value, _ in off)
    where = "cd %s && " % shlex.quote(str(root))
    return where + fix, where + back


def dev_settings_notes(folder):
    """Para `comparar` y las advertencias: las fases medidas con una opción de desarrollador fuera de lo normal y los
    ajustes que cambiaron de una fase a otra. Sin el dato (fases de una versión anterior) no dice nada."""
    phases = read_phases(folder)
    notes, seen = [], {}
    for phase in FASES:
        record = phases.get(phase) if isinstance(phases.get(phase), dict) else None
        settings = record.get("ajustes") if record else None
        if not isinstance(settings, dict) or not settings:
            continue
        seen[phase] = settings
        if dev_settings_off(settings):
            notes.append("%s se midió con opciones de desarrollador fuera de lo normal (%s): 'No conservar actividades' "
                         "recrea cada pantalla al volver a ella y las escalas de animación cambian la duración de las "
                         "transiciones" % (phase, dev_settings_text(settings)))
    changed = [label for name, label, _ in DEV_SETTINGS
               if len({str(settings.get(name, "null")) if not dev_setting_normal(name, settings.get(name)) else "normal"
                       for settings in seen.values()}) > 1]
    if len(seen) > 1 and changed:
        notes.append("las opciones de desarrollador cambiaron entre fases (%s): %s. Los tiempos de esas fases no se "
                     "comparan; repite con --rehacer la que no corresponda" % (", ".join(changed), "; ".join(
                         "%s: %s" % (phase, dev_settings_text(settings) or "normales") for phase, settings in seen.items())))
    return notes


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


# Variables que pone el shell o el sistema: usarlas en 'preparar' no las vuelve credenciales ni hace falta declararlas.
SHELL_VARIABLES = frozenset((
    "HOME", "PATH", "PWD", "OLDPWD", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG", "HOSTNAME", "RANDOM", "SECONDS",
    "LINENO", "IFS", "PPID", "UID", "EUID", "OSTYPE", "REPLY", "OPTARG", "OPTIND", "FUNCNAME", "PIPESTATUS", "BASH",
    "EPOCHSECONDS", "EPOCHREALTIME", "BASHPID", "SRANDOM", "COLUMNS", "LINES", "HOSTTYPE", "MACHTYPE", "SHLVL", "DISPLAY",
    "NF", "NR", "FS", "OFS",  # de awk: llegan aquí si su programa no va entre comillas simples
    # de las herramientas y del entorno de trabajo, no del flujo: si faltan, falla la herramienta y lo dice ella
    "ANDROID_SERIAL", "ANDROID_HOME", "ANDROID_SDK_ROOT", "JAVA_HOME", "ADB", "CI", "DEBUG", "VERBOSE", "TRACE"))
# Solo cuentan los nombres con forma de variable de entorno (en mayúsculas): los demás son variables del propio script.
# Un `\$VAR` escapado no lo expande este shell.
ENV_REFERENCE = re.compile(r"(?<!\\)\$(?:\{([A-Z][A-Z0-9_]*)\}|\{([A-Z][A-Z0-9_]*):?\?[^}]*\}|([A-Z][A-Z0-9_]*)\b)")
# `${VAR:-x}`, `${VAR-x}`, `${VAR:=x}`, `${VAR=x}`, `${VAR:+x}`: el script ya contempla que la variable falte.
ENV_OPTIONAL = re.compile(r"\$\{([A-Z][A-Z0-9_]*):?[-=+]")
# `-e NOMBRE=valor`, `--env NOMBRE=valor` y `--env=NOMBRE=valor`: una variable que el comando le pasa a Maestro.
ENV_PASSED = re.compile(r"((?:^|\s)(?:-e|--env)(?:[ \t]+|=)[\"']?)([A-Za-z_][A-Za-z0-9_]*)=")
ENV_ASSIGNED = re.compile(r"(?:^|[\s;&|(){}!])([A-Z][A-Z0-9_]*)[ \t]*\+?=(?!=)|\bfor[ \t]+([A-Z][A-Z0-9_]*)[ \t]+in\b"
                          r"|\b(?:getopts[ \t]+\S+|printf[ \t]+-v)[ \t]+([A-Z][A-Z0-9_]*)\b", re.M)
ENV_READ = re.compile(r"\bread\b([^\n;|&<)]*)")
# `[ -n "$VAR" ]`, `[[ -z $VAR ]]`: el script pregunta si la variable está: ya contempla que falte.
ENV_TESTED = re.compile(r"-[nz][ \t]+\"?\$(?:\{([A-Z][A-Z0-9_]*)\}|([A-Z][A-Z0-9_]*)\b)")
SHELL_HEREDOC = re.compile(r"<<-?[ \t]*(['\"])(\w+)\1.*?^[ \t]*\2[ \t]*$", re.S | re.M)
SHELL_COMMENT = re.compile(r"(?:^|(?<=\s))#.*$", re.M)
# El script recibe variables por otro camino (incluye otro archivo, carga un .env, las evalúa o las inyecta un
# envoltorio): lo que lee puede venir de ahí y no del entorno.
SHELL_SOURCED = re.compile(r"(?:^|[;&|(){}]|\b(?:then|do|else)\b)[ \t]*(?:source|\.)[ \t]+\S|\beval\b|\bexport[ \t]+\$\("
                           r"|\bset[ \t]+-a\b|\bdotenv\b|\.env\b", re.M)


def shell_expanded(text):
    """El texto de un script sin lo que el shell no expande ni ejecuta: lo que va entre comillas simples y los
    comentarios. Sigue las comillas dobles (un apóstrofo o un # dentro de ellas es texto), las barras de escape y las
    sustituciones de comando: dentro de `$(…)` o de dos acentos graves las comillas vuelven a empezar, aunque la
    sustitución esté entre comillas dobles."""
    out, index, size = [], 0, len(text)
    # por nivel de sustitución: las comillas abiertas y los paréntesis que faltan cerrar (None si es de acentos graves)
    stack = [["", 0]]
    while index < size:
        char, state = text[index], stack[-1]
        if state[0] == "'":
            state[0] = "" if char == "'" else "'"
        elif char == "\\" and index + 1 < size:
            out.append(text[index:index + 2])
            index += 1
        elif char == "$" and text[index + 1:index + 2] == "(":
            stack.append(["", 1])
            out.append("$(")
            index += 1
        elif char == "`":
            if state[1] is None:
                stack.pop()
            else:
                stack.append(["", None])
            out.append(char)
        elif state[0] == '"':
            state[0] = "" if char == '"' else '"'
            out.append(char)
        elif char == "'":
            state[0] = "'"
            out.append("''")
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            while index + 1 < size and text[index + 1] != "\n":
                index += 1
        else:
            if char == '"':
                state[0] = '"'
            elif char == "(" and state[1]:
                state[1] += 1
            elif char == ")" and state[1]:
                state[1] -= 1
                if state[1] == 0:
                    stack.pop()
            out.append(char)
        index += 1
    return "".join(out)


YAML_REFERENCE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
SCRIPT_SUFFIXES = (".sh", ".bash", ".yaml", ".yml")
SCRIPT_MAX_BYTES = 200_000


def shell_env_names(text):
    """Las variables de entorno que un comando o un script de shell lee sin darles un valor: `$VAR` y `${VAR}`, con
    nombre en mayúsculas. No cuentan las que el propio texto asigna (`VAR=…`, `for VAR in`, `read VAR`), las que en
    algún lugar traen un valor por defecto (`${VAR:-x}`, `${VAR:=x}`: el script ya contempla que falten), las del shell
    (HOME, PATH…) o de las herramientas (ANDROID_SERIAL…), las que el script pregunta si están (`[ -n "$VAR" ]`), lo que
    está en un comentario, entre comillas simples o en un heredoc con el delimitador entre comillas (ahí el shell no
    expande: es texto para `awk` o para el shell del dispositivo) ni los parámetros (`$1`). Un script que recibe
    variables por otro camino (`source`, `.`, `eval`, un `.env`) no aporta ninguna. Ante la duda, no cuenta: una
    variable de más detendría una captura que funciona."""
    text = shell_expanded(SHELL_HEREDOC.sub("", text))
    if SHELL_SOURCED.search(text):
        return set()
    text = ENV_PASSED.sub(r"\1", text)  # en `-e NOMBRE="$VAR"` NOMBRE no es una asignación del shell
    skipped = {name for groups in ENV_ASSIGNED.findall(text) for name in groups if name} \
        | set(ENV_OPTIONAL.findall(text)) | {name for groups in ENV_TESTED.findall(text) for name in groups if name}
    for words in ENV_READ.findall(text):
        skipped.update(re.findall(r"\b[A-Z][A-Z0-9_]*\b", words))
    names = set()
    for groups in ENV_REFERENCE.findall(text):
        name = next(group for group in groups if group)
        if name not in skipped and name not in SHELL_VARIABLES and not name.startswith(("BASH_", "LC_", "MAESTRO_")):
            names.add(name)
    return names


def named_scripts(command, folder):
    """Los scripts y flows (.sh, .yaml…) que el comando nombra y que existen, buscados desde el directorio actual y
    desde la carpeta de la investigación."""
    try:
        words = shlex.split(command)
    except ValueError:  # comillas sin cerrar: se parte por espacios, que alcanza para encontrar rutas
        words = command.split()
    found = []
    for word in words:
        if not word.endswith(SCRIPT_SUFFIXES):
            continue
        for base in (pathlib.Path.cwd(), pathlib.Path(folder)):
            path = base / os.path.expanduser(word)
            try:
                if path.is_file() and path.stat().st_size <= SCRIPT_MAX_BYTES and path not in found:
                    found.append(path)
                    break
            except OSError:
                continue
    return found


def prepare_env_names(command, folder):
    """Las variables de entorno que 'preparar' necesita, leídas del comando y del script o del flow que nombra: `$VAR`,
    `${VAR}` y `-e NOMBRE="$VAR"` en el comando o en un script de shell; `${VAR}` en un flow de Maestro (YAML), salvo
    las que el flow define en su `env:`, las que el comando le pasa con `-e` o `--env` (esas ya se leen del comando),
    las `MAESTRO_*` y lo que esté en un comentario. Solo nombres en mayúsculas.
    Solo nombres, en orden: nunca valores."""
    if not command or SHELL_SOURCED.search(shell_expanded(command)):
        return []  # sin comando, o con uno que carga las variables por su cuenta (un envoltorio, un .env)
    names = shell_env_names(command)
    passed = {name for _, name in ENV_PASSED.findall(command)}
    for path in named_scripts(command, folder):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if path.suffix in (".yaml", ".yml"):
            text = SHELL_COMMENT.sub("", text)
            defined = set(re.findall(r"(?:^|[\s{,])([A-Z][A-Z0-9_]*)[ \t]*:", text, re.M))  # en su `env:`, en bloque o en línea
            # las MAESTRO_* son de Maestro (algunas las pone él mismo): no se exigen
            names |= {name for name in YAML_REFERENCE.findall(text)
                      if name not in passed and name not in defined and not name.startswith("MAESTRO_")}
        else:
            names |= shell_env_names(text)
    return sorted(names)


def required_env(flow, command, folder):
    """(variables que el flujo necesita, las que 'preparar' usa y el plan no declara en requiere_env). Las segundas se
    tratan como requeridas."""
    declared = list(flow.get("requiere_env") or [])
    undeclared = [name for name in prepare_env_names(command, folder) if name not in declared]
    return declared + undeclared, undeclared


def undeclared_warning(flow_name, undeclared):
    return ("'preparar' del flujo '%s' usa variables de entorno que el plan no declara: %s. Las trato como requeridas; "
            "decláralas en el flujo: \"requiere_env\": [%s]"
            % (flow_name, ", ".join(undeclared), ", ".join('"%s"' % name for name in undeclared)))


def mask_secrets(text, names):
    """El texto con el valor de cada variable de 'requiere_env' reemplazado por ***."""
    for value in sorted({os.environ.get(name, "") for name in names}, key=len, reverse=True):
        if value:
            text = text.replace(value, "***")
    return text


def run_prepare(command, folder, secret_names, capture=None):
    """Corre 'preparar' y devuelve (código, últimas líneas de su salida, ruta del log). Si funciona, su salida no se
    muestra ni se guarda. Si falla, queda su cola en <carpeta>/logs/preparar.log después de pasar por mask_secrets. La
    salida estándar solo se mira cuando el flujo declara 'requiere_env' (y se enmascaran sus valores); sin esa lista se
    descarta, como siempre, porque puede traer lo que el comando escribe, y solo se lee la salida de error. `capture`
    decide si se mira la salida estándar cuando no coincide con "hay nombres que enmascarar"."""
    capture = bool(secret_names) if capture is None else capture
    with tempfile.TemporaryFile() as raw:
        result = subprocess.run(command, shell=True, stdout=raw if capture else subprocess.DEVNULL,
                                stderr=subprocess.STDOUT if capture else raw)
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


PAUSE_CALL = re.compile(r"perf\.py[\"']?[ \t]+pausa\b")


def open_tty():
    """(lectura, escritura) sobre la terminal de quien corre el comando, o None si no hay una terminal interactiva (lo
    corre un agente, una tarea programada, CI). Va por /dev/tty y no por la entrada y la salida estándar: así el texto
    se ve y la respuesta llega aunque quien llama capture o redirija la salida del recorrido. HB_PERF_TTY cambia la
    ruta (tests)."""
    path = os.environ.get("HB_PERF_TTY") or "/dev/tty"
    try:
        reader = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        return reader, open(path, "a", encoding="utf-8")
    except OSError:
        reader.close()
        return None


def has_tty():
    tty = open_tty()
    if tty is None:
        return False
    for stream in tty:
        stream.close()
    return True


NO_TTY = ("no hay una terminal interactiva donde mostrar la pausa y esperar la respuesta (¿lo corre un agente o una tarea "
          "sin terminal?). Un recorrido con un paso humano lo corre la persona, en su terminal")


def human_pause(message, tty):
    """Muestra el mensaje en la terminal, con un pitido, y espera la respuesta. True si la corrida sigue; False si la
    persona respondió x (la corrida no vale)."""
    reader, writer = tty
    writer.write("\a\n▶ PAUSA · %s\n  Enter cuando esté listo · x + Enter si esta corrida no vale (se descarta y se repite): "
                 % message)
    writer.flush()
    answer = reader.readline()
    if answer == "":  # la terminal se cerró: nadie va a responder
        raise Precondicion("pausa: " + NO_TTY)
    return answer.strip().lower() != "x"


def cmd_pausa(args):
    GUIA["omitir"] = True  # corre dentro de un recorrido: cómo seguir lo dice la captura que lo llama
    tty = open_tty()
    if tty is None:
        raise Precondicion("pausa: " + NO_TTY)
    # Mientras dura la pausa, la terminal es suya: la captura que la llamó deja de leerla (RunCutter) hasta que termina.
    flag = os.environ.get(PAUSE_FLAG_ENV)
    try:
        if flag:
            try:
                pathlib.Path(flag).write_text(str(os.getpid()), encoding="utf-8")
            except OSError:
                pass
        if not human_pause(" ".join(args.mensaje) or "haz el paso que te toca en el dispositivo", tty):
            raise CorridaDescartada("pausa: corrida descartada por la persona")
    finally:
        if flag:
            try:
                os.unlink(flag)
            except OSError:
                pass
        for stream in tty:
            stream.close()


# ── Cortar una corrida desviada ──────────────────────────────────────────────
CUT_REASON = "cortada a mano"
CUT_POLL_S = 0.2
PAUSE_FLAG_ENV = "HB_PERF_PAUSA_ACTIVA"
CUT_HINT = ("· Si una corrida se desvía (otra pantalla, un toque que no entró), x + Enter la corta: se descarta sin "
            "procesar su traza y se repite. Durante una pausa del recorrido, la tecla la atiende la pausa.")


class RunCutter:
    """`x` + Enter en la terminal corta la corrida en curso. Lee la terminal de quien corre la captura sin bloquear y
    solo mientras ninguna pausa del recorrido (`perf.py pausa`) la está usando: la pausa deja una bandera (un archivo,
    en PAUSE_FLAG_ENV) mientras espera su respuesta, y con la bandera puesta aquí no se lee nada. Sin una terminal
    interactiva (un agente, CI, la salida redirigida a un archivo que no es una terminal) no existe: `abrir` da None."""

    def __init__(self, fd):
        self.fd = fd
        # La bandera vive en una carpeta propia y privada (no en un nombre predecible del directorio temporal).
        self.folder = tempfile.mkdtemp(prefix="hbperf-pausa-")
        self.flag = os.path.join(self.folder, "activa")

    @classmethod
    def abrir(cls):
        try:
            fd = os.open(os.environ.get("HB_PERF_TTY") or "/dev/tty", os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except (OSError, AttributeError):  # sin terminal, o una plataforma sin esas banderas
            return None
        cutter = cls(fd)
        if not os.isatty(fd) or not cutter.foreground():
            cutter.cerrar()
            return None
        return cutter

    def foreground(self):
        """True si este proceso está en primer plano en esa terminal: uno en segundo plano que la lee queda detenido."""
        try:
            return os.tcgetpgrp(self.fd) == os.getpgrp()
        except OSError:
            return False

    def entorno(self):
        return dict(os.environ, **{PAUSE_FLAG_ENV: self.flag})

    def empezar(self):
        """Antes de cada recorrido: sin bandera vieja (una pausa que se cortó) y sin lo que se tecleó antes de empezar."""
        try:
            os.unlink(self.flag)
        except OSError:
            pass
        try:
            import termios
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:  # sin termios, o una terminal que no lo admite: solo se pierde el vaciado
            pass

    def pedido(self):
        """True si la persona escribió x + Enter desde la última vez que se miró."""
        if self.fd is None or os.path.exists(self.flag) or not self.foreground():
            return False
        try:
            if not select.select([self.fd], [], [], 0)[0]:
                return False
            data = os.read(self.fd, 4096)
        except (OSError, ValueError):
            return False
        return any(line.strip().lower() == "x" for line in data.decode("utf-8", "replace").splitlines())

    def cerrar(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None

    def __del__(self):
        self.cerrar()


def kill_tree(pid):
    """Termina un proceso y sus descendientes (el recorrido y lo que tenga en curso: una espera, un comando de adb),
    del proceso hacia sus hijos para que no alcance a lanzar el paso siguiente. No cambia el grupo de procesos del
    recorrido: así Ctrl+C le sigue llegando y `perf.py pausa` puede seguir leyendo la terminal."""
    try:
        listing = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        listing = ""
    children = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    order, queue = [], [pid]
    while queue:
        current = queue.pop(0)
        if current in order:
            continue
        order.append(current)
        queue += children.get(current, [])
    for target in order:
        try:
            os.kill(target, signal.SIGTERM)
        except OSError:
            pass


def uses_pause(command, folder):
    """True si el recorrido (el comando, o el script que nombra) llama a `perf.py pausa` fuera de un comentario."""
    texts = [command]
    for path in named_scripts(command, folder):
        try:
            texts.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return any(PAUSE_CALL.search(line) for text in texts for line in text.splitlines() if not line.lstrip().startswith("#"))


def settle(seconds):
    """Pausa para que el dispositivo se asiente; HB_PERF_ESPERA=0 la anula (tests)."""
    if os.environ.get("HB_PERF_ESPERA") != "0":
        time.sleep(seconds)


def drive(recorrido, label, cutter=None):
    """Recorre el flujo. Devuelve un motivo de invalidez o None. Con `cutter` (hay una terminal interactiva), x + Enter
    corta el recorrido en el momento y el motivo es CUT_REASON."""
    if recorrido == "manual":
        answer = wait_enter("▶ %s: recorre el flujo y presiona Enter (x + Enter para descartarla) " % label)
        return "descartada por el usuario" if answer == "x" else None
    if cutter is None:
        result = subprocess.run(recorrido, shell=True)
        return None if result.returncode == 0 else "el recorrido terminó con código %d" % result.returncode
    cutter.empezar()
    process = subprocess.Popen(recorrido, shell=True, env=cutter.entorno())
    try:
        while True:
            try:
                code = process.wait(timeout=CUT_POLL_S)
                break
            except subprocess.TimeoutExpired:
                if cutter.pedido():
                    kill_tree(process.pid)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    return CUT_REASON
    except BaseException:  # Ctrl+C o un fallo: el recorrido no queda corriendo, igual que con subprocess.run
        process.kill()
        process.wait()
        raise
    return None if code == 0 else "el recorrido terminó con código %d" % code


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


TRACE_CAP = re.compile(r"^duration_ms:[ \t]*(\d+)(?=[ \t]*(?:#.*)?$)", re.M)  # el de primer nivel, sin sangría


def with_trace_cap(config, seconds):
    """La configuración de Perfetto con el tope de duración de la traza (`duration_ms`) que pide el flujo
    (`duracion_max_s`); sin él, queda la de la configuración (10 minutos en las de la skill)."""
    if not seconds:
        return config
    line = "duration_ms: %d" % int(round(float(seconds) * 1000))
    if TRACE_CAP.search(config):
        return TRACE_CAP.sub(line, config, count=1)
    return config.rstrip("\n") + "\n" + line + "\n"


def trace_cap_s(config):
    found = TRACE_CAP.search(config)
    return int(found.group(1)) / 1000 if found else None


def wait_perfetto(adb, pid):
    """Espera a que Perfetto cierre el archivo: hasta que su proceso ya no esté (30 s como mucho)."""
    for _ in range(60):
        if adb.shell("[ -d /proc/%s ]" % pid).returncode != 0:
            break
        time.sleep(0.5)


def record_run(adb, config, recorrido, label, local, startup=None, package=None, cutter=None):
    """Graba una corrida. Devuelve (motivo de invalidez o None, métricas del recorrido). Una corrida cortada a mano
    (CUT_REASON) no baja su traza: se detiene Perfetto y se borra en el dispositivo."""
    if startup:
        adb.shell("am force-stop %s" % package)
        settle(1)
    remote = "%s/hbperf-%d.perfetto-trace" % (REMOTE_DIR, os.getpid())
    started = adb.shell("perfetto --background --txt -c - -o %s" % remote, stdin=config)
    pid = (re.findall(r"\d+", started.stdout) or [None])[-1]
    if started.returncode != 0 or not pid:
        raise CapturaFallida("no se pudo iniciar Perfetto: %s" % (started.stderr or started.stdout).strip()[-300:])
    time.sleep(float(os.environ.get("HB_PERF_ESPERA", "1.5")))  # Perfetto tarda en arrancar sus fuentes
    try:
        if startup:
            reason, extra = launch(adb, package, startup)
        else:
            reason, extra = drive(recorrido, label, cutter), []
    except KeyboardInterrupt:  # Ctrl+C en medio de la corrida: Perfetto no queda grabando en el dispositivo
        try:
            adb.shell("kill -TERM %s; rm -f %s" % (pid, remote), timeout=20)
        except (PerfError, OSError, subprocess.SubprocessError):
            pass
        raise
    if reason == CUT_REASON:  # la persona la cortó: la traza se descarta sin bajarla ni procesarla
        adb.shell("kill -TERM %s" % pid, timeout=20)
        wait_perfetto(adb, pid)  # la corrida siguiente no arranca con este Perfetto todavía cerrando
        adb.shell("rm -f %s" % remote, timeout=20)
        return reason, extra
    # Si Perfetto ya no corre, la traza llegó a su tope (duration_ms o el tamaño máximo) antes de que terminara el
    # recorrido: le falta el final. Solo cuenta una respuesta explícita: un adb que no contesta no invalida la corrida.
    # Se mira /proc/<pid>, como hace el script oficial de Perfetto para saber si su proceso sigue: no depende de que el
    # shell de adb tenga permiso para mandarle señales.
    if "terminada" in adb.shell("[ -d /proc/%s ] && echo viva || echo terminada" % pid).stdout:
        cap = trace_cap_s(config)
        reason = reason or ("la traza terminó antes que el recorrido: llegó a su tope de duración (%s) o al tamaño máximo "
                            "del archivo, y le falta el final. Sube 'duracion_max_s' en el flujo del plan (segundos; "
                            "contempla las pausas humanas) y repite"
                            % ("%s s" % fmt(cap) if cap else "duration_ms de la configuración de Perfetto"))
    adb.shell("kill -TERM %s" % pid)
    wait_perfetto(adb, pid)
    pulled = adb.run("pull", remote, str(local), timeout=600)
    adb.shell("rm -f %s" % remote)
    if pulled.returncode != 0 or not local.is_file() or local.stat().st_size < 1024:
        raise CapturaFallida("no se pudo descargar la traza: %s" % (pulled.stderr or pulled.stdout).strip()[-300:])
    return reason, extra


def partial_info(tp, local, queries, hz, flow, known, sdk):
    """Lo que la traza de una corrida que no valió dice igual (marcas del plan, última marca vista): el `info` de
    trace_metrics, o {} si la traza no se puede procesar."""
    try:
        partial = run_tp_batch(tp, local, queries[:1])["metricas"]
        return trace_metrics(trace_rows(*partial[-1]), hz, flow, known, sdk)[2] if partial else {}
    except (PerfError, OSError, subprocess.SubprocessError, ValueError, IndexError):
        return {}  # una traza cortada puede no procesarse: la corrida se repite igual, sin ese dato


def reach_text(info):
    """Hasta dónde llegó una corrida inválida: la última marca propia que se vio y su momento, como en la corrida de
    prueba. Sin `info`, lo dice: no saberlo no es lo mismo que no haber llegado a ninguna parte."""
    if not info:
        return "no se pudo leer la traza para saberlo"
    last = info.get("ultima_marca")
    unseen = [mark for mark, _, seen in info.get("marcas_plan") or [] if not seen]
    text = "última marca vista: %s a los %s s" % (last[0], fmt(last[1])) if last else \
        "ninguna marca propia (SCREEN, NAV, MARK) en la traza"
    return text + (" · marcas del plan que no salieron: %s" % ", ".join(unseen) if unseen else "")


def app_died(adb, package):
    """True solo si pidof respondió que la app no corre (un pidof que no existe no cuenta como caída)."""
    result = adb.shell("pidof %s" % package)
    return result.returncode == 1 and not result.stdout.strip()


def crash_excerpt(adb, package):
    """Primeras líneas del último crash de la app en logcat -b crash."""
    return crash_block(adb.shell("logcat -b crash -d -t 400").stdout.splitlines(), package=package)


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


def set_aside_orphan(folder, out_dir, phase, flow, n, csv_path):
    """Una traza `<flujo>_<n>` que quedó sin fila en el CSV (una captura cortada entre bajar la traza y escribir la
    métrica) no se pisa: se aparta en `<fase>-descartada-<hora>/`, como hace --rehacer. Devuelve la carpeta, o None."""
    found = [out_dir / ("%s_%d.perfetto-trace%s" % (flow, n, suffix)) for suffix in ("", ".gz")]
    found = [path for path in found if path.is_file()]
    if not found:
        return None
    if csv_path.is_file() and any(r["fase"] == phase and r["flujo"] == flow and to_int(r["corrida"]) == n
                                  for r in read_rows(csv_path)):
        return None  # tiene su fila: no es huérfana (no debería pasar: n es el número que sigue al último del CSV)
    target = folder / ("%s-descartada-%s" % (phase, datetime.datetime.now().strftime("%H%M%S")))
    target.mkdir(parents=True, exist_ok=True)
    for path in found:
        destination = target / path.name
        if destination.exists():
            destination = target / ("%s-%s" % (uuid.uuid4().hex[:6], path.name))
        path.rename(destination)
    print("⚠ había una traza de la corrida %d sin fila en metricas.csv (una captura que se cortó): no se pisa, quedó en %s/"
          % (n, target.name))
    return target


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


UNKNOWN_CONFIG = "desconocida"


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
    configs = list(previous.get("configs") or [])
    if previous.get("corridas") and not configs and data.get("configs"):
        configs.append(UNKNOWN_CONFIG)  # las corridas que ya había son de una versión que no lo registraba
    configs += [c for c in data.get("configs") or [] if c not in configs]
    if configs:
        out["configs"] = configs
    environment = worst_environment([previous.get("entorno"), data.get("entorno")])
    if environment:
        out["entorno"] = environment
    # Las opciones de desarrollador de la primera tanda que las registró; si otra tanda las trae distintas, lo avisa.
    settings, later = previous.get("ajustes"), data.get("ajustes")
    if isinstance(settings, dict) and isinstance(later, dict) and dev_settings_text(settings) != dev_settings_text(later):
        note = "las opciones de desarrollador cambiaron entre tandas de la fase (primera tanda: %s; esta: %s)" % (
            dev_settings_text(settings) or "normales", dev_settings_text(later) or "normales")
        if note not in warnings:
            warnings.append(note)
            out["avisos"] = warnings
    if isinstance(settings, dict) or isinstance(later, dict):
        out["ajustes"] = settings if isinstance(settings, dict) else later
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
        before_flow = flows.get(flow) or {}
        flows[flow] = merge_run_data(before_flow, data)
        if "depurable" in data:  # si el build con que se midió este flujo (su última tanda) era depurable
            flows[flow]["depurable"] = data["depurable"]
        if "skill" in data:
            # Si el flujo ya tenía corridas, vale la versión que las midió (sin dato, una anterior a 0.9.0).
            flows[flow]["skill"] = (phase_skill(previous, flow) or "anterior a 0.9.0") if before_flow.get("corridas") \
                else data["skill"]
    # `faltan` ({flujo: corridas}): lo que dejó pendiente una tanda cortada. Esta tanda reemplaza lo de su flujo (o lo
    # quita, si terminó) y conserva lo de los demás.
    earlier = previous.get("faltan") if isinstance(previous.get("faltan"), dict) else {}
    pending = {name: count for name, count in earlier.items() if name != flow and to_int(count) > 0}
    pending.update(data.pop("faltan", None) or {})
    if pending:
        data["faltan"] = pending
    merged = merge_run_data(previous, data)
    for key in ("hz_corridas", "avisos", "entorno", "configs", "ajustes"):
        data.pop(key, None)
    data.update(merged)
    data["fecha"] = previous.get("fecha") or data["fecha"]
    if previous.get("corridas") and "skill" in data:
        # La fase ya tenía corridas: vale la versión que las midió (sin dato, una anterior a 0.9.0), no la de esta tanda.
        data["skill"] = previous.get("skill") or "anterior a 0.9.0"
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
            for key in ("hz_corridas", "avisos", "entorno", "configs", "ajustes"):
                record.pop(key, None)
            rest = {}
            for data in tracked.values():
                rest = merge_run_data(rest, dict(data, corridas=0))
            record.update({k: v for k, v in rest.items() if k != "corridas"})
        record.pop("flujos", None)
        if tracked:
            record["flujos"] = tracked
        if isinstance(record.get("faltan"), dict):  # lo que faltaba del flujo que se rehace ya no vale
            record["faltan"].pop(flow, None)
            if not record["faltan"]:
                record.pop("faltan")
    save_phases(folder, phases)


def check_build(folder, phase, build, commit, force, flow=None, redo=False):
    """Avisos (o un error) según el build y el commit que midió antes. En `antes`, si la fase ya tiene corridas de ese
    flujo y se van a sumar más (sin --rehacer), avisa cuando el build instalado o la versión de la skill no son los de
    esas corridas: mezclarlas da una línea base de dos estados distintos."""
    before = read_phases(folder).get("antes")
    if not before:
        return []
    same = bool(before.get("instalada")) and before.get("instalada") == build.get("instalada") \
        and before.get("version") == build.get("version")
    if phase == "antes":
        tracked = before.get("flujos")
        if redo or (flow and tracked and flow not in tracked):
            return []
        notes = []
        if before.get("instalada") and not same:
            notes.append("el build instalado (%s, instalado %s) no es el que midió las corridas que 'antes' ya tiene (%s, "
                         "instalado %s): no las completes, repite la fase con --rehacer"
                         % (build.get("version"), build.get("instalada"), before.get("version"), before.get("instalada")))
        if not same_capture(phase_skill(before, flow)):
            notes.append("las corridas que 'antes' ya tiene se midieron con otra versión de hb-performance (%s; esta es "
                         "%s): la configuración de la traza puede no ser la misma; repite la fase con --rehacer"
                         % (phase_skill(before, flow) or "anterior a 0.9.0", VERSION))
        return notes
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


DEXOPT_STATUS = re.compile(r"\[status=([\w-]+)\]")


def dexopt_filters(text, package):
    """Los filtros de compilación de ART del paquete (uno por APK y por ABI) en la salida de `dumpsys package dexopt`:
    el bloque que empieza en `[<paquete>]` y sus líneas `arm64: [status=speed] [reason=…]`. Vacío si el paquete no
    aparece o la salida no tiene esa forma: entonces no se sabe, y se compila."""
    found, inside = [], False
    for line in text.splitlines():
        header = re.match(r"^\s*\[([\w.]+)\]\s*$", line)
        if header:
            inside = header.group(1) == package
        elif inside:
            found += DEXOPT_STATUS.findall(line)
    return found


def compilation_record(folder):
    path = pathlib.Path(folder) / "compilacion.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def already_compiled(adb, package, folder, build):
    """True si la app ya tiene el filtro `speed` en todo su código y es la misma instalación (versión y fecha de
    instalación) en la que esta investigación fijó la compilación completa la última vez: no hace falta recompilar."""
    record = compilation_record(folder)
    if not build.get("instalada") or record.get("paquete") != package or record.get("filtro") != "speed" \
            or record.get("version") != build.get("version") or record.get("instalada") != build.get("instalada"):
        return False
    filters = dexopt_filters(adb.shell("dumpsys package dexopt", timeout=120).stdout, package)
    return bool(filters) and all(name == "speed" for name in filters)


def elapsed_text(seconds):
    return "%d s" % round(seconds) if seconds < 90 else "%d min %02d s" % divmod(round(seconds), 60)


def fix_compilation(adb, package, mode, folder=None, build=None, force=False):
    """Compilación de ART igual en todas las fases. Devuelve la descripción que queda en fases.json.

    - completa: todo el código compilado antes de correr (Macrobenchmark CompilationMode.Full). No depende de
      perfiles ni de librerías: es la opción para comparar un cambio de código.
    - perfil: perfiles borrados, Baseline Profile del APK instalado con profileinstaller y speed-profile
      (CompilationMode.Partial). Más parecido a una instalación de Play; para medir un Baseline Profile.

    Sin esto, el resultado depende de la historia del dispositivo: un build recién instalado corre con JIT y uno
    que ya se abrió varias veces, compilado con su perfil de uso.
    """
    adb.shell("am force-stop %s" % package)
    started = time.monotonic()
    if mode == "completa":
        if folder is not None and build and not force and already_compiled(adb, package, folder, build):
            print("✔ compilación de ART ya fijada: completa (speed) en esta misma instalación (%s, instalada %s): no se "
                  "recompila; --recompilar la fuerza" % (build.get("version"), build.get("instalada")))
            return "completa (speed)"
        print("… fijando la compilación de ART (completa: speed) de %s. En una app grande puede tardar varios minutos: "
              "no es un cuelgue, no interrumpas" % package, flush=True)
        compiled = adb.shell("cmd package compile -f -m speed %s" % package, timeout=1800)
        if "Success" not in compiled.stdout:
            raise Precondicion("no se pudo compilar la app (speed): %s" % (compiled.stdout + compiled.stderr).strip()[-200:])
        print("✔ compilación de ART fijada: completa (speed), igual en todas las fases (tardó %s)"
              % elapsed_text(time.monotonic() - started))
        if folder is not None and build and build.get("instalada"):
            (pathlib.Path(folder) / "compilacion.json").write_text(json.dumps(
                {"paquete": package, "filtro": "speed", "version": build.get("version"), "instalada": build["instalada"]},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return "completa (speed)"
    print("… fijando la compilación de ART (perfil: Baseline Profile + speed-profile) de %s. En una app grande puede tardar "
          "varios minutos: no es un cuelgue, no interrumpas" % package, flush=True)
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
    print("✔ compilación de ART fijada: perfiles borrados, Baseline Profile instalado y speed-profile (tardó %s)"
          % elapsed_text(time.monotonic() - started))
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
    mine = re.compile(r"%s_\d+(?:(?:_invalida_.*)?\.perfetto-trace(?:\.gz)?|\.linea\.json)" % re.escape(flow))
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


CONFIG_SOURCE = re.compile(r'\b(ftrace_events|atrace_categories|atrace_apps|name)[ \t]*:[ \t]*"([^"]*)"')
CONFIG_PREFIX = {"ftrace_events": "ftrace:", "atrace_categories": "atrace:", "name": "ds:"}
TRACE_KEY = re.compile(r"^(.+?_\d+)(?:_invalida_.*)?\.perfetto-trace(?:\.gz)?$")
CONFIG_FILE = "configuracion.json"
SKILL_CONFIGS = ("base", "cpu", "completa")


def config_sources(text):
    """Las fuentes que captura una configuración de Perfetto (.pbtx), con los nombres que usan las consultas en su línea
    `-- requiere:`: `ftrace:<grupo>/<evento>`, `atrace:<categoría>`, `atrace_apps` (las secciones de la app) y
    `ds:<fuente de datos>`."""
    sources = set()
    for line in text.splitlines():
        for key, value in CONFIG_SOURCE.findall(line.split("#", 1)[0]):
            sources.add("atrace_apps" if key == "atrace_apps" else CONFIG_PREFIX[key] + value)
    return sorted(sources)


def config_record(path):
    """Nombre, huella del contenido y fuentes de una configuración. La huella sale del archivo tal cual (sin el paquete
    ni el tope de duración), así que es la misma en todas las investigaciones que usan esa configuración."""
    path = pathlib.Path(path)
    text = path.read_text(encoding="utf-8")
    name = path.stem if path.parent == ASSETS / "perfetto" else path.name
    return {"nombre": name, "hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], "fuentes": config_sources(text)}


# Campos de la configuración que el `perfetto` de un Android anterior no conoce: su lector de texto rechaza la
# configuración entera si los encuentra, así que se quitan antes de enviarla. (campo, API mínima)
CONFIG_FIELDS_SINCE = (("symbolize_ksyms", 31),)
# Fuentes que la configuración pide y un Android anterior no entrega: (fuente, API mínima, motivo)
SOURCES_SINCE = (("ds:android.surfaceflinger.frametimeline", 31, "FrameTimeline es de Android 12 o superior"),)


def config_for_sdk(text, sdk):
    """La configuración sin los campos que ese Android no conoce."""
    for field, since in CONFIG_FIELDS_SINCE:
        if sdk < since:
            text = re.sub(r"^[ \t]*%s[ \t]*:[^\n]*\n" % field, "", text, flags=re.M)
    return text


def device_sources(record, sdk):
    """El registro de la configuración con lo que ese dispositivo no entrega aunque la configuración lo pida
    (`no_disponibles`: {fuente: motivo}): para una consulta que lo necesita es "no medido", no "sin casos"."""
    missing = {source: reason for source, since, reason in SOURCES_SINCE if sdk < since and source in record["fuentes"]}
    return dict(record, no_disponibles=missing) if missing else record


def config_label(record):
    return "%s@%s" % (record["nombre"], record["hash"])


def save_trace_config(out_dir, trace_name, record, installed=None):
    """Anota con qué configuración se grabó una traza (y la fecha de instalación del build medido, para verificar el
    mapping al desofuscar) en `<carpeta de la fase>/configuracion.json`. Va junto a las trazas (y no solo en
    fases.json) porque también lo necesitan las de `--prueba`, que no son de ninguna fase, y porque `consulta` recibe
    una traza suelta."""
    found = TRACE_KEY.match(trace_name)
    if not found:
        return
    path = pathlib.Path(out_dir) / CONFIG_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get("configuraciones"), dict) \
            or not isinstance(data.get("trazas"), dict):
        data = {"configuraciones": {}, "trazas": {}}
    data["configuraciones"][record["hash"]] = {"nombre": record["nombre"], "fuentes": record["fuentes"]}
    if record.get("no_disponibles"):
        data["configuraciones"][record["hash"]]["no_disponibles"] = record["no_disponibles"]
    data["trazas"][found.group(1)] = record["hash"]
    if installed:
        if not isinstance(data.get("instaladas"), dict):
            data["instaladas"] = {}
        data["instaladas"][found.group(1)] = installed
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def trace_config(trace):
    """La configuración con la que se grabó la traza ({"nombre", "hash", "fuentes", "instalada"}), o None si no se sabe:
    una traza de una versión anterior de la skill, o una que se movió de su carpeta."""
    trace = pathlib.Path(trace)
    found = TRACE_KEY.match(trace.name)
    try:
        data = json.loads((trace.parent / CONFIG_FILE).read_text(encoding="utf-8"))
        digest = data["trazas"][found.group(1)]
        saved = data["configuraciones"][digest]
        installed = (data.get("instaladas") or {}).get(found.group(1))
        absent = saved.get("no_disponibles")
        return {"nombre": str(saved["nombre"]), "hash": str(digest), "fuentes": [str(x) for x in saved["fuentes"]],
                "no_disponibles": {str(k): str(v) for k, v in absent.items()} if isinstance(absent, dict) else {},
                "instalada": installed if isinstance(installed, str) else None}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def query_requires(sql):
    """Las fuentes que una consulta declara en su cabecera (`-- requiere: ftrace:sched/sched_switch atrace:view`)."""
    for line in sql.splitlines():
        if line.startswith("-- requiere:"):
            return line.split(":", 1)[1].split()
    return []


def missing_sources(requires, config):
    """Las fuentes que la consulta necesita y la traza no tiene: las que su configuración no captura y las que ese
    dispositivo no entrega."""
    absent = config.get("no_disponibles") or {}
    return [source for source in requires if source not in config["fuentes"] or source in absent]


def configs_with(requires):
    """Las configuraciones de la skill que capturan todas esas fuentes."""
    found = []
    for name in SKILL_CONFIGS:
        path = ASSETS / "perfetto" / ("%s.pbtx" % name)
        if path.is_file() and not missing_sources(requires, config_record(path)):
            found.append(name)
    return found


def unmeasured(config, missing):
    """El texto de una consulta que no se puede responder con esa traza: no es lo mismo que "no hubo casos"."""
    absent = config.get("no_disponibles") or {}
    device = [source for source in missing if source in absent]
    if device:
        return "no medido: el dispositivo no entrega %s (%s)" % (", ".join(device), "; ".join(absent[s] for s in device))
    return "no medido: la configuración %s no captura %s" % (config["nombre"], ", ".join(missing))


def custom_queries(flow, folder, package):
    queries = []
    for spec in flow.get("metricas_sql", []):
        path = folder / spec["archivo"]
        if not path.is_file():
            raise PerfError("no existe la consulta de métricas %s" % path)
        queries.append((spec["archivo"], fill_sql(path.read_text(encoding="utf-8"), package, {})))
    return queries


def git_toplevel(folder):
    try:
        result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True,
                                text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return pathlib.Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def lexical(path):
    """La ruta absoluta sin resolver enlaces simbólicos: por dónde se llega a la carpeta, no dónde está en el disco."""
    return pathlib.Path(os.path.abspath(str(path)))


def under(path, base):
    """La ruta relativa de `path` dentro de `base`, o None si no está dentro."""
    try:
        return pathlib.Path(path).relative_to(base)
    except ValueError:
        return None


def project_root(folder):
    """La raíz del proyecto de una carpeta de investigación. Si se llega a la carpeta por dentro del repo desde el que
    se corre el comando, vale ese repo aunque la carpeta sea un enlace a otra de fuera (una carpeta de contexto
    compartida, que puede ser otro repo): la investigación es del proyecto, no de donde se guardan sus archivos. Si
    no, el repo que contiene la carpeta (también uno anidado dentro del actual); sin git, la carpeta actual."""
    own = git_toplevel(folder)
    here = git_toplevel(pathlib.Path.cwd()) if own is not None else None
    if here is not None and under(own.resolve(), here.resolve()) is None:
        # La carpeta está en otro repo que no es parte de este (no es un repo anidado): si se llega a ella por dentro
        # de este, es un enlace a una carpeta de fuera.
        target = lexical(folder)
        if any(under(target, base) is not None for base in (here, lexical(here), lexical(pathlib.Path.cwd()))):
            return here
    return own or pathlib.Path.cwd()


def relative_folder(folder, root):
    """La carpeta como ruta relativa a la raíz (por donde se llega a ella o, si no, por donde está en el disco); si
    queda fuera, absoluta."""
    folder = pathlib.Path(folder)
    for candidate, base in ((lexical(folder), pathlib.Path(root)), (lexical(folder), lexical(root)),
                            (folder.resolve(), pathlib.Path(root).resolve())):
        inside = under(candidate, base)
        if inside is not None:
            return inside
    return lexical(folder)


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


def q(path):
    """Una ruta o un argumento para un comando que se pega en la terminal: entre comillas si tiene espacios o
    caracteres que el shell interpreta."""
    return shlex.quote(str(path))


def q_repo(repo):
    """El repo de un comando del cierre: entre comillas si es una ruta; un marcador <…> queda tal cual."""
    return repo if str(repo).startswith("<") else q(repo)


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
        return "cd %s && <compila e instala el build de profiling; guárdalo como 'instalar' en plan.json>" % q(root)
    serial = plan.get("serial")
    if serial and serial not in install and "ANDROID_SERIAL" not in install:
        install = "ANDROID_SERIAL=%s %s" % (serial, install)
    return "cd %s && %s" % (q(root), install)


def terminal(command, what, you):
    return {"tipo": "terminal", "texto": command, "que": what, "tu": you}


NO_COMMIT = "No hagas commit ni push."


def chat_text(text, plan=None):
    """El texto de un chat tal como se entrega: con las rutas que no se leen y, siempre al final, NO_COMMIT. La skill
    ya dice que el agente solo propone el commit; la línea explícita evita que una herramienta o un modelo lo haga igual."""
    text = text.rstrip()
    if (plan or {}).get("no_leer"):
        if not text.endswith((".", "!", "?")):
            text += "."
        text += " No leas ni busques en: %s." % ", ".join(plan["no_leer"])
    if not text.endswith((".", "!", "?")):
        text += "."
    return "%s %s" % (text, NO_COMMIT)


def chat(text, tier, effort, what, plan):
    return {"tipo": "chat", "texto": chat_text(text, plan), "modelo": model_name(plan, tier), "esfuerzo": effort, "que": what,
            "nivel": tier}


# ── Abrir un chat con el modelo y el esfuerzo (modelos.md · Abrir el chat con el modelo y el esfuerzo) ─────────
# Las herramientas que `siguiente` sabe abrir desde la terminal: (clave, nombre, comando). {modelo} es el id del modelo en
# esa herramienta y {esfuerzo}, el nivel en inglés. Los flags de Claude Code (--model y --effort) son los de su referencia
# de la línea de comandos; la de GitHub Copilot CLI documenta --model y no un flag de esfuerzo: se elige con /model. Una
# línea "Comando del chat:" en la sección de rendimiento de AGENTS.md reemplaza el comando de la herramienta del proyecto.
CHAT_TOOLS = (("claude", "Claude Code", "claude --model {modelo} --effort {esfuerzo}"),
              ("copilot", "GitHub Copilot CLI", "copilot --model {modelo}"))
EFFORT_CLI = {"bajo": "low", "medio": "medium", "alto": "high"}
CLAUDE_FAMILIES = ("haiku", "sonnet", "opus", "fable")
TOOL_KEY = re.compile(r"herramienta(?:\s+de\s+(?:la\s+)?ia)?|ai\s+tool", re.I)
CHAT_COMMAND_KEY = re.compile(r"comando\s+(?:del|para\s+abrir\s+el)\s+chat|chat\s+command", re.I)


def performance_lines(root):
    """[(clave, valor)] de las líneas "Clave: valor" de la sección de rendimiento del AGENTS.md del proyecto, fuera de
    los bloques de código. [] sin AGENTS.md o sin sección."""
    agents = read_agents(root) if root is not None else None
    section = performance_section(agents) if agents is not None else None
    if not section:
        return []
    out = []
    for _, line in prose_lines(agents[section[0]:section[1]]):
        found = FOLDER_LINE.match(line.rstrip("\r\n"))
        if found:
            quoted = re.search(r"`([^`]+)`", found.group("value"))
            value = (quoted.group(1) if quoted else found.group("value")).strip().rstrip(".").strip()
            out.append((found.group("key").strip(), value))
    return out


def ai_tool(root):
    """(clave, nombre, comando propio) de la herramienta de IA que anota la sección de rendimiento de AGENTS.md:
    clave 'claude', 'copilot', 'otra' (una que la skill no conoce) o None (sin anotar). El comando propio sale de la
    línea "Comando del chat:", o None."""
    tool = template = None
    for key, value in performance_lines(root):
        if tool is None and TOOL_KEY.fullmatch(key) and value and not value.startswith("<"):
            tool = value
        elif template is None and CHAT_COMMAND_KEY.fullmatch(key) and "{modelo}" in value:
            template = value
    if tool is None:
        return None, None, template
    low = tool.lower()
    found = next(((code, name) for code, name, _ in CHAT_TOOLS if code in low), None)
    return (found[0], found[1], template) if found else ("otra", tool, template)


def cli_model_id(plan, tier, tool):
    """El id del modelo de un nivel en una herramienta: el de `modelos_cli` del plan o, si no, el que sale del nombre
    de `modelos` ("Sonnet 5.5" → claude-sonnet-5-5 en Claude Code y claude-sonnet-5.5 en GitHub Copilot CLI). Un nombre
    que ya es un id (sin espacios ni mayúsculas) va tal cual."""
    custom = plan.get("modelos_cli") if isinstance(plan.get("modelos_cli"), dict) else {}
    custom = custom.get(tool) if isinstance(custom.get(tool), dict) else {}
    if custom.get(tier):
        return str(custom[tier])
    if tier in MODEL_FALLBACK and not (plan.get("modelos") or {}).get(tier) and custom.get(MODEL_FALLBACK[tier]):
        return str(custom[MODEL_FALLBACK[tier]])
    name = model_name(plan, tier).strip()
    if re.fullmatch(r"[a-z0-9][\w.:\[\]-]*", name):
        return name
    words = name.lower().split()
    if words and words[0] in CLAUDE_FAMILIES:
        words = ["claude"] + words
    text = "-".join(words)
    return text.replace(".", "-") if tool == "claude" else text


def chat_openers(plan, root, tier, effort):
    """[(herramienta, comando, nota)] para abrir un chat nuevo con el modelo y el esfuerzo del nivel: el de la
    herramienta de AGENTS.md o, si no está anotada (o es una que la skill no conoce y no trae su comando), los de todas
    las que conoce. Cada comando empieza con cd a la raíz del proyecto."""
    tool, name, template = ai_tool(root)
    level = EFFORT_CLI.get(effort, effort)
    where = "cd %s && " % shlex.quote(str(root))
    out = []
    if tool == "otra" and template:
        command = template.replace("{modelo}", shlex.quote(model_name(plan, tier))).replace("{esfuerzo}", level)
        return [(name, where + command, "" if "{esfuerzo}" in template else "elige el esfuerzo %s al abrirlo" % level)]
    for key, label, default in CHAT_TOOLS:
        if tool in ("claude", "copilot") and key != tool:
            continue
        own = template if template and tool == key else default
        command = own.replace("{modelo}", shlex.quote(cli_model_id(plan, tier, key))).replace("{esfuerzo}", level)
        out.append((label, where + command, "" if "{esfuerzo}" in own else "elige el esfuerzo %s con /model al abrirlo"
                                                                       % level))
    return out


def next_steps(folder, plan, flow=None):
    """(título, [pasos]) del paso que sigue. En el cierre (y con la investigación cerrada), si quedan cambios
    temporales sin revertir, agrega cómo quitarlos sin perderlos (revert_notice)."""
    title, steps = plan_steps(folder, plan, flow)
    steps = before_capture(folder, plan, flow, steps)
    # Solo en el cierre: antes de medir "después" los cambios temporales tienen que seguir puestos.
    if title.startswith(("sesión 4", "investigación cerrada", "triage cerrado")):
        notice = revert_notice(folder, project_root(folder).resolve())
        if notice:
            steps = steps + [notice]
    return title, steps


def before_capture(folder, plan, flow, steps):
    """Si los pasos capturan, lo que la captura va a necesitar y la skill no puede deducir va primero: las variables de
    entorno del flujo (requiere_env y las que usa 'preparar'), con el comando para cargarlas en la misma terminal donde
    se mide, o una línea si ya están cargadas en esta; y, si el plan no fija el serial, cómo ver los dispositivos. Nunca
    imprime ni guarda los valores."""
    captures = [step for step in steps if step["tipo"] == "terminal" and " capturar " in step["texto"]]
    if not captures:
        return steps
    root = project_root(folder).resolve()
    flows = plan.get("flujos") or {}
    name = flow if flow in flows else next(iter(flows), None)
    spec = flows.get(name) or {}
    prepare = None if startup_spec(spec) else (spec.get("preparar") or "").strip() or None
    try:
        names = required_env(spec, prepare, pathlib.Path(folder))[0]
    except (OSError, ValueError, PerfError):
        names = list(spec.get("requiere_env") or [])
    names = [env for env in dict.fromkeys(names) if ENV_NAME.fullmatch(str(env))]
    missing = [env for env in names if not os.environ.get(env)]
    notes, first = [], []
    if names and not missing:
        notes.append("%s ya %s cargada%s en esta terminal: mide en esta misma (el valor no se muestra)" % (
            ", ".join(names), "está" if len(names) == 1 else "están", "" if len(names) == 1 else "s"))
    elif missing:
        first.append(terminal(
            " && ".join([env_steps(missing, root)[0][1]] + [command.split(" && ", 1)[1]
                                                           for _, command in env_steps(missing, root)[1:]]),
            "carga en esta terminal %s, que el flujo necesita para medir (%s)" % (
                ", ".join(missing), "lectura oculta para las que parecen claves: lo que escribes no se ve"
                if any(SECRET_NAME.search(env) for env in missing) else "lectura normal"),
            "escribe cada valor cuando te lo pida, en la misma terminal donde vas a medir: no queda en el historial ni "
            "en ningún archivo, y se pierde al cerrarla"))
    steps = list(steps)
    if not plan.get("serial"):
        # Sin el serial en el plan, con más de un dispositivo la captura se detiene: lo dice en la primera, con el comando.
        index = steps.index(captures[0])
        steps[index] = dict(captures[0], tu="%s; con más de un dispositivo conectado, mira cuál es con `cd %s && adb "
                                            "devices -l` y agrega --serial <serial> al comando" % (
                                                captures[0]["tu"].rstrip("."), shlex.quote(str(root))))
    lead = [{"tipo": "avisos", "titulo": "Antes de medir", "lineas": notes}] if notes else []
    return lead + first + steps


def plan_steps(folder, plan, flow=None):
    """(título, [pasos]) del paso que sigue según fases.json, plan.json y los archivos de la carpeta.

    Cada paso es un dict: tipo terminal (comando completo, empieza con cd), chat (texto, modelo y esfuerzo) o archivo.
    Es la única fuente de los comandos de entrega: los agentes la copian en vez de inventarlos.
    """
    root = project_root(folder).resolve()
    state = folder.resolve() / "estado.md"
    folder = relative_folder(folder, root)  # cada comando empieza con cd a la raíz: dentro de ella, rutas relativas

    def command(*parts):
        return "cd %s && python3 -I %s %s" % (q(root), q(HERE / "perf.py"), " ".join(q(part) for part in parts))

    def full_command(pending):
        """Una "Captura pendiente" como comando completo: tal cual si ya empieza con cd; con la ruta de este script si
        es un comando de perf.py (con o sin "python3 -I .../perf.py" delante); si no, con cd a la raíz."""
        own = re.search(r"(?:^|\s)(?:\S*perf\.py\s+)?((?:capturar|consulta|diagnostico)\s.*)$", pending)
        if pending.startswith("cd "):
            return pending
        return "cd %s && python3 -I %s %s" % (q(root), q(HERE / "perf.py"), own.group(1)) if own else \
            "cd %s && %s" % (q(root), pending)

    flows = plan["flujos"]
    flow = flow if flow in flows else next(iter(flows))
    spec = flows[flow]
    paused = has_human_pause(spec, root / folder)  # un recorrido con un paso humano no es automático: lo atiende alguien
    automatic = (bool(startup_spec(spec)) or spec.get("recorrido", "manual") != "manual") and not paused
    runs = 10 if automatic else 5
    you_run = ("nada: el script detiene y abre la app %d veces" % runs if startup_spec(spec) else
               "nada: el recorrido es automático (%d corridas)" % runs if automatic else
               "atiende la pausa del recorrido en tu terminal (haz el paso que pide y presiona Enter) en cada una de las %d "
               "corridas (más 1 de calentamiento)" % runs if paused else
               "recorre el flujo en el dispositivo y presiona Enter en cada una de las %d corridas (más 1 de calentamiento)"
               % runs)
    capture = ["capturar", "--plan", folder / "plan.json"] + (["--flujo", flow] if len(flows) > 1 else [])
    phases = read_phases(root / folder)
    mejoras = plan.get("mejoras", [])
    estados = [m.get("estado", "propuesta") for m in mejoras]
    for phase in FASES:
        # Una tanda que se cortó (Ctrl+C, inválidas seguidas) dejó sus corridas válidas y cuántas faltan: la fase no se
        # da por medida hasta completarla.
        cut = (phases.get(phase) or {}).get("faltan") if isinstance(phases.get(phase), dict) else None
        if isinstance(cut, dict) and to_int(cut.get(flow)) > 0:
            missing = to_int(cut[flow])
            return "completar la fase %s, que se cortó (sin chat)" % phase, [
                terminal(command(*(capture + ["--fase", phase, "--corridas", missing])),
                         "completa la fase %s con las %d corridas que faltan: la tanda anterior se cortó y las válidas ya "
                         "están guardadas" % (phase, missing),
                         "lo mismo que en la tanda anterior; si cambió el build o las condiciones, agrega --rehacer y pide "
                         "las corridas completas")]
    resume = "Sigue hb-performance con %s" % state
    session2 = chat(resume, "diagnostico", "alto", "sesión 2: lee diagnostico.md y el código, escribe los hallazgos y el "
                    "plan de mejoras; termina con el comando para que decidas", plan)
    session4 = chat(resume, "economico", "bajo", "sesión 4: compara, escribe la lectura y el resumen y genera el reporte", plan)
    triage = plan.get("profundidad") == "triage"
    # Una mejora aplicada después de medir "después" deja esa fase vieja: hay que medirla de nuevo (--rehacer).
    measured = phases.get("despues", {}).get("fecha", "")
    stale = "despues" in phases and any(m.get("estado") == "aplicada" and m.get("aplicada_en", "") > measured for m in mejoras)
    # Los reportes con el nombre de esta versión (reporte-<tipo>-dev y -gerencia) o de las anteriores.
    report = report_file(state.parent, "final")
    if report is not None and "aprobada" not in estados and not stale:
        try:
            internal = "interno: contiene código" in report.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            internal = False
        closed = [{"tipo": "archivo", "texto": str(report), "que": "el reporte final técnico%s" % (
            " (interno: contiene código; fuera del equipo, comparte el de gerencia)" if internal else
            "; se puede compartir: lleva solo métricas agregadas")}]
        business = audience_file(state.parent, "final", "gerencia")
        if business is not None:
            closed.append({"tipo": "archivo", "texto": str(business),
                           "que": "el mismo reporte para un público no técnico (gerencia)"})
        return "investigación cerrada", closed
    initial = report_file(state.parent, "inicial") or state.parent / "reporte-inicial-dev.md"
    if triage and initial.is_file():
        closed = [{"tipo": "archivo", "texto": str(initial),
                   "que": "el reporte del triage (diagnóstico y plan, sin línea base ni medición después)"}]
        if not mejoras:  # sin mejoras propuestas no hay nada que pasar a riguroso
            return "triage cerrado", closed
        return "triage cerrado", closed + [
            terminal(command("decidir", "--carpeta", folder, "--profundidad", "riguroso"),
                     "solo si quieres aplicar una mejora: pasa la investigación a riguroso y te da, en orden, las capturas "
                     "que faltan (completar antes y medir control) y la decisión",
                     "córrelo solo si vas a aplicar una mejora; si no, el triage termina aquí")]
    # Riguroso pide, antes de decidir, la línea base completa (10 corridas de antes con recorrido automático, 5 con
    # recorrido manual o con pausa humana) y el control. Falta cuando la investigación viene de un triage.
    undecided = "propuesta" in estados and "aprobada" not in estados
    # Con una mejora ya aprobada solo se pide el control que falta de un antes medido (aprobar y pasar a riguroso en el
    # mismo comando): una investigación rigurosa ya decidida sigue como estaba.
    if not triage and (undecided or ("aprobada" in estados and "antes" in phases)) and "aplicada" not in estados \
            and "despues" not in phases:
        have = measured_runs(root / folder, phases, "antes", flow)
        missing = 0 if not (undecided or plan.get("desde_triage")) else runs if "antes" not in phases \
            else max(0, runs - have) if have is not None else 0
        if missing or "control" not in phases:
            # Con otra versión de la skill (o sin el dato: una anterior a 0.9.0) la configuración de la traza pudo
            # cambiar: las corridas que hay no se completan, se repiten.
            measured_with = phase_skill(phases.get("antes"), flow)
            redo = "antes" in phases and not same_capture(measured_with)
            steps = []
            if redo:
                steps.append(terminal(command(*(capture + ["--fase", "antes", "--corridas", runs, "--rehacer"])),
                                      "repite la fase antes completa: las corridas que hay se midieron con otra versión de "
                                      "hb-performance (%s) y no se mezclan con las nuevas"
                                      % (measured_with or "anterior a 0.9.0"), you_run))
            elif missing:
                steps.append(terminal(command(*(capture + ["--fase", "antes", "--corridas", missing])),
                                      "completa la fase antes hasta las %d corridas que pide riguroso (tiene %d: las que ya "
                                      "hay cuentan si nada cambió)" % (runs, runs - missing),
                                      you_run.replace(str(runs), str(missing)) + "; si reinstalaste la app o cambió el build "
                                      "desde esas corridas, agrega --rehacer y pide --corridas %d: las anteriores ya no "
                                      "cuentan (capturar lo avisa)" % runs))
            if "control" not in phases or redo:
                again = "control" in phases  # el control que había midió el ruido del antes que se repite: va de nuevo
                steps.append(terminal(command(*(capture + ["--fase", "control", "--corridas", runs]
                                                + (["--rehacer"] if again else []))),
                                      "repite la medición sin cambiar nada, con el mismo build de antes: mide el ruido"
                                      + (" (de nuevo: el control anterior era del antes que se repite)" if again else ""),
                                      you_run))
            if undecided:
                ids = ",".join(m["id"] for m in mejoras if m.get("estado", "propuesta") == "propuesta")
                steps.append(terminal(
                    command("decidir", "--carpeta", folder, "--aprobar", ids, "--descartar", "-", "--pendiente", "-"),
                    "registra qué mejoras se aplican y da el chat de la sesión 3",
                    "deja en cada lista los ids que correspondan (- es ninguno); mira las mejoras en estado.md"))
            return "completar la línea base de riguroso (sin chat)", steps
    if "aprobada" in estados:
        first = next(m for m in mejoras if m.get("estado") == "aprobada")
        missing_dod = dod_notice(root, plan)  # sin `## DoD` en AGENTS.md, la sesión 3 no sabría qué validar
        return "sesión 3 · %s" % first["id"], [
            chat("%s: sesión 3, aplica %s" % (resume, first["id"]), "intermedio", "medio",
                 "sesión 3: aplica %s%s con su test y el DoD, propone el commit y marca la mejora aplicada con sus "
                 "archivos (perf.py guarda el diff para el reporte)" % (
                     first["id"], " (a prueba: la medición de después confirma o refuta su hipótesis)"
                     if first.get("a_prueba") else ""), plan)] + ([missing_dod] if missing_dod else [])
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
        listed = pending_captures(state)
        for pending in listed + [extra for extra in diagnostic_captures(state.parent) if extra not in listed]:
            steps.append(terminal(full_command(pending),
                                  "la captura que el diagnóstico dejó pendiente (opcional: cierra un pendiente)",
                                  "córrela solo si quieres cerrar ese pendiente antes de terminar; lo que salga se "
                                  "analiza en un chat aparte (prompts.md · Una pregunta sobre una traza)"))
        steps.append(chat("%s: cierra la investigación sin fase después" % resume, "economico", "bajo",
                          "sesión 4 corta: no hay mejoras que medir; escribe el resumen con el estado inicial y genera "
                          "el reporte final", plan))
        return "sesión 4 · cierre sin mejoras", steps
    if (state.parent / "diagnostico.md").is_file():
        # Si el diagnóstico pidió una captura (el hilo principal espera en sus frames largos), va antes del chat y es
        # opcional: con ella, la sesión 2 puede decir por qué espera en vez de dejarlo sin confirmar.
        steps = [terminal(full_command(pending),
                          "captura opcional que pide diagnostico.md: una corrida con la configuración completa, para saber "
                          "por qué espera el hilo principal en sus frames más largos (no cuenta como medición)",
                          "córrela si quieres ese dato antes del diagnóstico; después, la consulta que indica diagnostico.md")
                 for pending in diagnostic_captures(state.parent)]
        return "sesión 2 · diagnóstico", steps + [session2]
    steps = []
    if triage:
        you_run = you_run.replace(str(runs), "3")
        runs = 3
    pending = test_warnings(root / folder, flow) if "antes" not in phases else []
    if pending:
        # La última corrida de prueba dejó avisos: medir así da un antes sin red o que mide el recorrido. Primero se
        # corrigen; medir igual queda como opción.
        return "corrige antes de medir (avisos de la corrida de prueba)", test_warning_steps(
            root / folder, root, plan, flow, pending, resume, command(*(capture + ["--prueba"])),
            command(*(capture + ["--fase", "antes", "--corridas", runs])), you_run)
    if "antes" not in phases:
        if not any((state.parent / "prueba").glob("*.perfetto-trace*")):
            steps.append(terminal(command(*(capture + ["--prueba"])),
                                  "una corrida de prueba: imprime las métricas y qué marcas del plan salieron, sin guardar "
                                  "nada ni fijar la compilación de ART (tarda lo que el recorrido)",
                                  "lo mismo que en una corrida, una sola vez; revisa que todas las marcas del plan salgan con ✔"))
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


def same_capture(version):
    """True si las corridas medidas con esa versión de la skill se pueden mezclar con las de esta."""
    return version in SAME_CAPTURE


def phase_skill(record, flow=None):
    """La versión de hb-performance que midió las corridas de un flujo en una fase (la del flujo si fases.json la guarda
    por flujo; si no, la de la fase). None si no hay dato: la midió una versión anterior a 0.9.0."""
    record = record or {}
    tracked = (record.get("flujos") or {}).get(flow) or {}
    return tracked.get("skill") or record.get("skill")


def measured_runs(folder, phases, phase, flow):
    """Cuántas corridas válidas tiene el flujo en esa fase: las de metricas.csv o, sin CSV, las de fases.json. None si
    no se sabe."""
    path = pathlib.Path(folder) / "metricas.csv"
    if path.is_file():
        try:
            found = {r["corrida"] for r in read_rows(path) if r["fase"] == phase and r["flujo"] == flow}
        except PerfError:
            found = set()
        if found:
            return len(found)
    record = phases.get(phase) or {}
    tracked = record.get("flujos") or {}
    value = (tracked.get(flow) or {}).get("corridas") if tracked else record.get("corridas")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


PENDING_CAPTURE = re.compile(r"captura pendiente[^`\n]*`([^`\n]+)`", re.I)


def pending_captures(state):
    """Los comandos que la sección Pendientes de estado.md deja como "Captura pendiente: `<comando>`"."""
    try:
        _, sections = state_sections(pathlib.Path(state).read_text(encoding="utf-8"))
    except OSError:
        return []
    text = next((body for title, body in sections.items() if title.startswith("pendientes")), "")
    return [found.strip() for found in PENDING_CAPTURE.findall(without_placeholders(text)) if "<" not in found]


def diagnostic_captures(folder):
    """Las capturas que `perf.py diagnostico` dejó pendientes en diagnostico.md (o diagnostico-<fase>.md) como "Captura
    pendiente: `<comando>`". Vacío si la corrida de prueba que hay en la carpeta ya es una captura con la razón de
    bloqueo (la captura completa ya se hizo)."""
    folder = pathlib.Path(folder)
    found = []
    for path in sorted(folder.glob("diagnostico*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found += [item.strip() for item in PENDING_CAPTURE.findall(text) if "<" not in item and item.strip() not in found]
    if not found:
        return []
    try:
        data = json.loads((folder / "prueba" / CONFIG_FILE).read_text(encoding="utf-8"))
        saved = data["configuraciones"]
        done = any(BLOCKED_SOURCE in saved[digest]["fuentes"] and any((folder / "prueba").glob(key + ".perfetto-trace*"))
                   for key, digest in data["trazas"].items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        done = False
    return [] if done else found


def has_human_pause(flow, folder):
    """True si el recorrido del flujo es un comando con un paso humano (`perf.py pausa`)."""
    route = flow.get("recorrido")
    return isinstance(route, str) and route != "manual" and uses_pause(route, folder)


def human_runs(plan):
    """(total, detalle) de las veces que una persona recorre el flujo hasta el cierre: la corrida de prueba más, por
    fase, el calentamiento y las corridas (5 con un paso humano; 3 y una sola fase en triage)."""
    triage = plan.get("profundidad") == "triage"
    phases, runs = (1, 3) if triage else (3, 5)
    return 1 + phases * (1 + runs), "1 de prueba + %d fase%s × (1 de calentamiento + %d corridas)" % (
        phases, "" if phases == 1 else "s", runs)


def code_span(text):
    """El texto como código en línea de markdown, también si trae un acento grave."""
    return "`` %s ``" % text if "`" in text else "`%s`" % text


def route_block(plan, root, folder=None):
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
                "cd %s && %s" % (q(root), " && ".join(part for part in (prepare, route) if part))))
        if flow.get("requiere_env"):
            names = [str(v) for v in flow["requiere_env"] if ENV_NAME.fullmatch(str(v))]
            lines.append("- Variables de entorno que necesita: %s. Cárgalas en la terminal donde mides, antes de medir (las "
                         "claves, con lectura oculta; el valor no se guarda): %s"
                         % (", ".join("`%s`" % v for v in flow["requiere_env"]),
                            "; ".join(code_span(command) for _, command in env_steps(names, root)) or "—"))
        if folder is not None and has_human_pause(flow, folder):
            total, detail = human_runs(plan)
            lines.append("- Paso humano: el recorrido tiene una pausa (`perf.py pausa`), así que cada corrida la atiende una "
                         "persona en su terminal. Hasta el cierre son **%d recorridos** (%s): si cada uno es una operación "
                         "real en el ambiente, cuéntalos antes de aprobar%s." % (
                             total, detail, "" if plan.get("profundidad") == "triage"
                             else " o usa triage (`\"profundidad\": \"triage\"`)"))
    lines.append("")
    lines.append("Los archivos del recorrido (`recorrido.sh`, `preparar.sh`, `preparar.yaml`) viven en esta carpeta, que git "
                 "ignora y que se borra al limpiar: si los vas a reutilizar, archívalos fuera de `reports/`.")
    return "\n".join(lines)


CHAT_YOU = ("abre el chat con ese comando, pega el texto tal cual y espera a que termine; al final te da el paso "
            "siguiente")


def render_steps(steps, markdown, root=None, plan=None):
    """Los pasos como texto: para la terminal (markdown=False) o para estado.md. Cada uno dice dónde va (Terminal o
    Chat nuevo), el comando completo, qué hace y qué te toca; un chat, con `root` y `plan`, también el comando que lo
    abre con su modelo y su esfuerzo (chat_openers)."""
    code = (lambda s: "`%s`" % s) if markdown else (lambda s: s)
    lines, i = [], 0
    # Los avisos van primero aunque estén al final de la lista: es lo que hay que saber antes de dar los pasos.
    for step in sorted(steps, key=lambda item: item["tipo"] != "avisos"):
        if step["tipo"] == "avisos":  # sin número: no es un paso, es lo que hay que saber antes de los pasos
            lines.append(("**%s:**" if markdown else "%s:") % step["titulo"])
            # `crudo`: un texto para copiar tal cual (una plantilla), sin viñetas
            lines += [("%s" if step.get("crudo") else "   - %s") % line for line in step["lineas"]]
            continue
        i += 1
        if step["tipo"] == "terminal":
            lines.append("%d. **Terminal** (sin chat) · %s" % (i, step["que"]) if markdown else
                         "%d. Terminal (sin chat) · %s" % (i, step["que"]))
            lines.append("   %s" % code(step["texto"]))
            lines.append("   Tú: %s." % step["tu"])
        elif step["tipo"] == "chat":
            lines.append("%d. **Chat nuevo** · Modelo: %s · Esfuerzo: %s" % (i, step["modelo"], step["esfuerzo"]) if markdown
                         else "%d. Chat nuevo · Modelo: %s · Esfuerzo: %s" % (i, step["modelo"], step["esfuerzo"]))
            if root is not None and step.get("nivel"):
                for tool, command, note in chat_openers(plan or {}, root, step["nivel"], step["esfuerzo"]):
                    lines.append("   Abrir (Terminal, %s): %s%s" % (tool, code(command), " · %s" % note if note else ""))
            lines.append("   Texto: \"%s\"" % step["texto"])
            lines.append("   Qué hace: %s." % step["que"])
            lines.append("   Tú: %s." % (step.get("tu") or CHAT_YOU))
        else:
            lines.append("%d. %s: %s" % (i, step["que"][0].upper() + step["que"][1:], step["texto"]))
    return lines


# ── Consumo ──────────────────────────────────────────────────────────────────
# GitHub Copilot factura el uso en AI Credits: 1 AI Credit = 0,01 USD (documentación de facturación de GitHub Copilot,
# "Usage-based billing"). Si GitHub cambia el valor, cambia esta constante.
AI_CREDIT_USD = 0.01
COST_PLACEHOLDER = "<costo>"
COST_WHERE = ("lo muestra tu herramienta al cerrar el chat: /cost en Claude Code; /usage en GitHub Copilot CLI, que "
              "informa AI Credits y tokens (con ellos, --creditos <n> y --tokens-entrada, --tokens-cache, "
              "--tokens-salida en vez de --costo)")
# Nivel de modelo y esfuerzo que `siguiente` recomienda para cada sesión: con ellos sale el comando ya completo.
SESSIONS = {"0": ("0 · setup", "intermedio", "medio"), "1": ("1 · ficha", "intermedio", "medio"), "2": ("2 · diagnóstico", "diagnostico", "alto"),
            "3": ("3 · %s", "intermedio", "medio"), "4": ("4 · cierre", "economico", "bajo")}
COST_TOTAL = "**Total de la investigación:**"
USD_AMOUNT = re.compile(r"(?:US\$|USD|\$)[ \t]*(\d[\d.,]*)|(\d[\d.,]*)[ \t]*(?:USD|US\$|\$|dólares|dolares)", re.I)
# Solo los AI Credits de GitHub Copilot tienen una conversión documentada: "12 créditos" de otra herramienta no se suma.
CREDIT_AMOUNT = re.compile(r"(\d[\d.,]*)[ \t]*AI[ \t]+(?:credits?|cr[eé]ditos?)", re.I)
TOKEN_PART = re.compile(r"(\d[\d.,]*[ \t]*[kKmM]?)[ \t]*(?:tokens[ \t]+)?(?:de[ \t]+)?(entrada|cach[eé]|salida)", re.I)
TOKEN_TOTAL = re.compile(r"(\d[\d.,]*[ \t]*[kKmM]?)[ \t]*tokens(?![ \t]+(?:de[ \t]+)?(?:entrada|cach[eé]|salida))", re.I)


def amount(text, whole=False):
    """Un número escrito por una persona: "1.05", "1,05", "38k", "1.2M", "12.000". Con `whole` (tokens, créditos) un
    separador seguido de tres cifras es de miles; si no, el último separador es el decimal. None si no es un número."""
    text = (text or "").strip().replace(" ", "").rstrip(".,")  # una coma o un punto de la frase no son del número
    factor = 1
    if text[-1:].lower() in ("k", "m"):
        factor = 1000 if text[-1].lower() == "k" else 1000000
        text = text[:-1]
    if not re.fullmatch(r"\d[\d.,]*", text):
        return None
    if whole and factor == 1 and re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        text = text.replace(".", "").replace(",", "")
    elif "." in text and "," in text:
        decimal = max(text.rfind("."), text.rfind(","))
        text = re.sub(r"[.,]", "", text[:decimal]) + "." + text[decimal + 1:]
    else:
        text = text.replace(",", ".")
    try:
        return float(text.rstrip(".")) * factor
    except ValueError:
        return None


def short_count(value):
    """Una cantidad de tokens para leer: 950, 45 k, 1,2 M."""
    if value >= 1000000:
        return ("%.1f" % (value / 1000000)).rstrip("0").rstrip(".").replace(".", ",") + " M"
    if value >= 1000:
        return "%d k" % round(value / 1000)
    return "%d" % value


def cost_rows(state_text):
    """Las filas de la tabla "Consumo" de estado.md: [{"sesion", "modelo", "costo", "pasos"}]."""
    _, sections = state_sections(state_text)
    body = next((text for title, text in sections.items() if title.startswith("consumo")), "")
    out = []
    for row in parse_table(body)[1]:
        if not row or not row[0].strip() or any("<" in cell for cell in row):
            continue
        cells = [cell.strip() for cell in row] + [""] * 4
        out.append({"sesion": cells[0], "modelo": cells[1], "costo": cells[2], "pasos": cells[3]})
    return out


def cost_of(cell):
    """Lo que se puede sumar de una celda "Costo o tokens": {"usd" o None, "tokens": {entrada, caché, salida, sin
    desglose}}. Un monto en USD escrito vale tal cual; si solo hay AI Credits, se convierten con AI_CREDIT_USD."""
    usd = None
    found = USD_AMOUNT.search(cell)
    if found:
        usd = amount(found.group(1) or found.group(2))
    if usd is None:
        credits = CREDIT_AMOUNT.search(cell)
        value = amount(credits.group(1)) if credits else None
        usd = value * AI_CREDIT_USD if value is not None else None
    tokens = {}
    for number, kind in TOKEN_PART.findall(cell):
        value = amount(number, whole=True)
        if value is not None:
            key = "caché" if kind.lower().startswith("cach") else kind.lower()
            tokens[key] = tokens.get(key, 0) + value
    if not tokens:
        whole = TOKEN_TOTAL.search(cell)
        value = amount(whole.group(1), whole=True) if whole else None
        if value is not None:
            tokens["sin desglose"] = value
    return {"usd": usd, "tokens": tokens}


def session_key(text, ids=()):
    """(número de sesión, id de la mejora o '') de una celda "Sesión": "3 · M1" → ("3", "M1")."""
    number = re.match(r"\s*(?:sesi[oó]n\s+)?(\d+)(?!\d|-)", text or "", re.I)
    improvement = next((item for item in ids if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(item), text or "")), "")
    return (number.group(1) if number else ""), improvement


RECIPE_MARK = "receta de arranque en frío"


def from_recipe(folder, plan):
    """True si la investigación la armó `nuevo --receta arranque-frio` (sin sesión 1): lo dice el plan (`receta`) o,
    en una creada antes de que el plan lo guardara, la Ficha que deja la receta."""
    if plan.get("receta") == "arranque-frio":
        return True
    try:
        return RECIPE_MARK in (pathlib.Path(folder) / "estado.md").read_text(encoding="utf-8")
    except OSError:
        return False


def setup_session_pending(folder):
    """True si la sesión 0 (el setup del proyecto) está hecha y ninguna investigación del proyecto anotó su costo:
    AGENTS.md tiene el bloque de estado del setup y ningún estado.md de la carpeta de investigaciones (ni de esta)
    tiene una fila de la sesión 0 en "Consumo"."""
    root = project_root(pathlib.Path(folder)).resolve()
    agents = read_agents(root)
    section = performance_section(agents) if agents is not None else None
    if not section or AGENTS_BLOCK[0] not in agents[section[0]:section[1]]:
        return False
    states = [pathlib.Path(folder) / "estado.md"]
    base = investigations_base(root)
    try:
        states += sorted(base.glob("**/estado.md"))[:500] if base.is_dir() else []
    except OSError:
        pass
    for state in states:
        try:
            noted = cost_rows(state.read_text(encoding="utf-8"))
        except OSError:
            continue
        if any(session_key(row["sesion"])[0] == "0" for row in noted):
            return False
    return True


def done_sessions(folder, plan):
    """Las sesiones de IA que esta investigación ya hizo, en orden: [(rótulo, nivel de modelo, esfuerzo)]. Sale de lo
    que cada una deja: el setup del proyecto (sesión 0, si AGENTS.md lo registra y ninguna investigación del proyecto
    anotó su costo), la corrida de prueba o una fase medida (sesión 1, salvo en un plan armado por la receta de
    arranque), el reporte inicial o las mejoras del plan (2), cada mejora aplicada (3) y el reporte final (4)."""
    folder = pathlib.Path(folder)
    mejoras = plan.get("mejoras") or []
    out = []
    if setup_session_pending(folder):
        out.append(SESSIONS["0"])
    tested = (folder / "prueba").is_dir() and any((folder / "prueba").glob("*.perfetto-trace*"))
    flows = (plan.get("flujos") or {}).values()
    by_hand = any(not startup_spec(flow) for flow in flows) or (bool(flows) and not from_recipe(folder, plan))
    if by_hand and (tested or read_phases(folder)):
        out.append(SESSIONS["1"])
    if report_file(folder, "inicial") or mejoras or report_file(folder, "final"):
        out.append(SESSIONS["2"])
    for item in mejoras:
        if item.get("estado") == "aplicada":
            label, tier, effort = SESSIONS["3"]
            out.append((label % item["id"], tier, effort))
    if report_file(folder, "final"):
        out.append(SESSIONS["4"])
    return out


def missing_costs(folder, plan):
    """Las sesiones hechas que no tienen fila en "Consumo": [(rótulo, modelo, esfuerzo)], con el nombre del modelo."""
    try:
        rows = cost_rows((pathlib.Path(folder) / "estado.md").read_text(encoding="utf-8"))
    except OSError:
        return []
    ids = [item["id"] for item in plan.get("mejoras") or []]
    noted = [session_key(row["sesion"], ids) for row in rows]
    applied = [item["id"] for item in plan.get("mejoras") or [] if item.get("estado") == "aplicada"]
    out = []
    for label, tier, effort in done_sessions(folder, plan):
        number, improvement = session_key(label, ids)
        covered = any(n == number and (number != "3" or i == improvement or (not i and len(applied) == 1))
                      for n, i in noted)
        if not covered:
            out.append((label, model_name(plan, tier), effort))
    return out


def cost_command(folder, session=None, model=None, effort=None):
    """El comando para anotar el costo de una sesión, con la carpeta relativa a la raíz del proyecto. Con la sesión,
    el modelo y el esfuerzo sale completo: solo queda el costo por llenar."""
    root = project_root(folder).resolve()
    folder = relative_folder(folder, root)
    return "cd %s && python3 -I %s consumo --carpeta %s --sesion \"%s\" --modelo \"%s\"%s --costo \"%s\"" % (
        q(root), q(HERE / "perf.py"), q(folder), session or "<sesión>", model or "<modelo>",
        " --esfuerzo %s" % effort if effort else "", COST_PLACEHOLDER)


def cost_total(folder, plan):
    """El total de la investigación en una línea: USD y tokens de las filas de "Consumo" que traen el dato, cuántas no
    lo traen y qué sesiones hechas faltan anotar. Un dato que falta se dice: no cuenta como cero."""
    try:
        rows = cost_rows((pathlib.Path(folder) / "estado.md").read_text(encoding="utf-8"))
    except OSError:
        rows = []
    costs = [cost_of(row["costo"]) for row in rows]
    priced = [cost["usd"] for cost in costs if cost["usd"] is not None]
    tokens = {}
    for cost in costs:
        for kind, value in cost["tokens"].items():
            tokens[kind] = tokens.get(kind, 0) + value
    parts = []
    if priced:
        parts.append("%.2f USD (%d de %d sesiones anotadas traen un monto)" % (sum(priced), len(priced), len(rows))
                     if len(priced) < len(rows) else "%.2f USD en %d %s" % (
                         sum(priced), len(rows), "sesión anotada" if len(rows) == 1 else "sesiones anotadas"))
    elif rows:
        parts.append("sin un monto en USD en las %d sesiones anotadas" % len(rows))
    if tokens:
        counted = sum(1 for cost in costs if cost["tokens"])
        parts.append("tokens: " + ", ".join("%s %s" % (short_count(tokens[kind]), kind)
                                            for kind in ("entrada", "caché", "salida", "sin desglose") if kind in tokens)
                     + (" (solo %d de %d sesiones anotadas los traen)" % (counted, len(rows)) if counted < len(rows) else ""))
    missing = missing_costs(folder, plan) if plan else []
    if missing:
        parts.append("faltan anotar %d %s (%s): el total es parcial" % (
            len(missing), "sesión hecha" if len(missing) == 1 else "sesiones hechas",
            ", ".join(label for label, _, _ in missing)))
    if not rows and not missing:
        return "sin sesiones anotadas"
    return " · ".join(parts)


def update_cost_total(folder, plan):
    """Deja al día la línea del total debajo de la tabla "Consumo" de estado.md."""
    state = pathlib.Path(folder) / "estado.md"
    if not state.is_file():
        return
    text = state.read_text(encoding="utf-8")
    line = "%s %s" % (COST_TOTAL, cost_total(folder, plan))

    def rewrite(match):
        body = [row for row in match.group(2).rstrip("\n").split("\n") if not row.startswith(COST_TOTAL)]
        while body and not body[-1].strip():
            body.pop()
        return match.group(1) + "\n".join(body + ["", line]) + "\n"

    new, count = re.subn(r"(## Consumo\n\n)(.*?)(?=\n## |\Z)", rewrite, text, count=1, flags=re.S)
    if count and new != text:
        state.write_text(new, encoding="utf-8")


def cost_md(folder, plan):
    """La sección "Costo de la investigación" de los reportes: las sesiones anotadas y el total, con lo que falta."""
    try:
        rows = cost_rows((pathlib.Path(folder) / "estado.md").read_text(encoding="utf-8"))
    except OSError:
        rows = []
    intro = ("> Lo que costó cada sesión de IA, según lo anotó quien la corrió (`perf.py consumo`). Las mediciones "
             "corren en la terminal, sin chat, y no cuestan tokens.\n\n")
    table = markdown_table(["Sesión", "Modelo", "Costo o tokens", "Pasos"],
                           [[row["sesion"], row["modelo"] or "—", row["costo"] or "—", row["pasos"] or "—"]
                            for row in rows]) + "\n\n" if rows else ""
    return "%s%s**Total:** %s" % (intro, table, cost_total(folder, plan))


def cost_lines(folder, plan):
    """Las líneas con las que `siguiente` lista las sesiones hechas sin fila en "Consumo": un comando listo por cada
    una. Es informativo: nada se bloquea si no se anota."""
    missing = missing_costs(folder, plan)
    if not missing:
        return []
    lines = ["Costo (opcional, Terminal): %s sin anotar. Un comando por cada una; solo falta el costo, que %s:" % (
        "1 sesión hecha" if len(missing) == 1 else "%d sesiones hechas" % len(missing), COST_WHERE)]
    return lines + ["  %s" % cost_command(folder, label, model, effort) for label, model, effort in missing]


def write_next(folder, title, steps, missing=(), plan=None):
    """Reescribe "## Siguiente paso" de estado.md con lo que dice next_steps. `missing`: las sesiones sin anotar."""
    state = pathlib.Path(folder) / "estado.md"
    if not state.is_file():
        return
    body = "\n".join(["- **Paso:** %s" % title, "- **En orden, uno a la vez:**"]
                     + ["  " + line for line in render_steps(steps, markdown=True, root=project_root(
                         pathlib.Path(folder)).resolve(), plan=plan)]
                     + (["- **Costo (opcional, terminal):** faltan anotar %s. `perf.py siguiente` imprime un comando "
                         "listo por cada una; solo falta el costo." % ", ".join(label for label, _, _ in missing)]
                        if missing else
                        ["- **Costo de cada chat** (opcional, terminal, al cerrarlo): `perf.py siguiente` imprime el "
                         "comando `consumo` ya completo de cada sesión hecha; solo falta el costo."])
                     + ["- _Lo escribe `perf.py siguiente`: si algo cambió, vuelve a correrlo._", ""])
    text = state.read_text(encoding="utf-8")
    new, count = re.subn(r"(## Siguiente paso\n\n).*?(?=\n## )", lambda m: m.group(1) + body, text, count=1, flags=re.S)
    if count:
        state.write_text(new, encoding="utf-8")


def print_next(folder, plan, flow=None):
    title, steps = next_steps(pathlib.Path(folder), plan, flow)
    print("Siguiente · %s (también en estado.md):" % title)
    for line in render_steps(steps, markdown=False, root=project_root(pathlib.Path(folder)).resolve(), plan=plan):
        print("  " + line)
    for line in cost_lines(folder, plan):
        print("  " + line)
    write_next(folder, title, steps, missing_costs(folder, plan), plan)
    update_cost_total(folder, plan)
    update_block(folder, "recorrido", route_block(plan, project_root(pathlib.Path(folder)).resolve(),
                                                  pathlib.Path(folder)))
    update_warnings(folder, plan)


def cmd_siguiente(args):
    folder = pathlib.Path(args.carpeta)
    plan = load_plan(folder / "plan.json")
    state = folder / "estado.md"
    if state.is_file():
        # La Ficha se completa en la sesión 1; el Resumen y los Hallazgos, desde que la sesión 2 entrega su reporte.
        # Con mejoras aprobadas o aplicadas (sesión 3 y medición después), el resumen que falta es el del cierre: no
        # se avisa todavía.
        delivered = bool(report_file(folder, "inicial") or report_file(folder, "final"))
        in_progress = any(m.get("estado") in ("aprobada", "aplicada") for m in plan.get("mejoras", []))
        warn_unfilled(folder, state_sections(state.read_text(encoding="utf-8"))[1], findings=delivered and not in_progress)
    for name, flow in plan["flujos"].items():
        undeclared = required_env(flow, (flow.get("preparar") or "").strip(), folder)[1]
        if undeclared:
            print("⚠ " + undeclared_warning(name, undeclared))
    print_next(folder, plan, args.flujo)


def cmd_consumo(args):
    folder = pathlib.Path(args.carpeta)
    state = folder / "estado.md"
    if not state.is_file():
        raise PerfError("no existe %s" % state)
    text = state.read_text(encoding="utf-8")
    if any("<" in str(v) for v in (args.sesion, args.costo, args.modelo, args.pasos) if v):
        raise PerfError("reemplaza los <...> por el valor real antes de anotar (por ejemplo --costo \"1.05 USD\", o "
                        "--creditos 120 si tu herramienta informa AI Credits)")
    tokens = [(label, getattr(args, name, None)) for label, name in (
        ("entrada", "tokens_entrada"), ("caché", "tokens_cache"), ("salida", "tokens_salida"))]
    numbers = {}
    for label, raw in tokens + [("créditos", getattr(args, "creditos", None))]:
        if raw is None:
            continue
        if label == "créditos" and re.fullmatch(r"[1-9]\d{0,2}(?:[.,]\d{3})+", raw.strip()):
            raise PerfError("'%s' AI Credits puede leerse como miles o como decimales: escríbelo sin separador de miles "
                            "(1200) o con los decimales que no sean tres cifras (1.2)" % raw)
        numbers[label] = amount(raw, whole=label != "créditos")  # los créditos pueden traer decimales
        if numbers[label] is None:
            raise PerfError("'%s' no es una cantidad: usa un número (120, 45000, 45k, 1.2M)" % raw)
    if not args.costo and not numbers:
        raise PerfError("falta el costo: usa --costo \"<lo que muestre tu herramienta>\" (por ejemplo \"1.05 USD\"), "
                        "--creditos <AI Credits> o --tokens-entrada, --tokens-cache y --tokens-salida")
    parts = [args.costo] if args.costo else []
    if "créditos" in numbers:
        credits = numbers["créditos"]
        # La conversión solo se anota si el costo escrito no trae ya un monto en USD.
        usd = "" if args.costo and USD_AMOUNT.search(args.costo) else " (%.2f USD)" % (credits * AI_CREDIT_USD)
        parts.append("%s AI Credits%s" % (("%.4f" % credits).rstrip("0").rstrip("."), usd))
    listed = ["%d %s" % (numbers[label], label) for label, _ in tokens if label in numbers]
    if listed:
        parts.append("tokens: " + ", ".join(listed))
    effort = getattr(args, "esfuerzo", None)
    model = " · ".join(part for part in (args.modelo, effort) if part)
    row = "| %s | %s | %s | %s |" % (args.sesion, model or "—", " · ".join(parts), args.pasos or "—")

    def append(match):
        body = [line for line in match.group(2).rstrip("\n").split("\n")
                if line.strip() and "<" not in line and not line.startswith(COST_TOTAL)]
        table = [line for line in body if line.lstrip().startswith("|")]
        return match.group(1) + "\n".join(table + [row] + [line for line in body if line not in table]) + "\n"

    new, count = re.subn(r"(## Consumo\n\n)(.*?)(?=\n## |\Z)", append, text, count=1, flags=re.S)
    if not count:
        raise PerfError("%s no tiene la sección '## Consumo'" % state)
    state.write_text(new, encoding="utf-8")
    print("✔ Consumo: %s" % row)
    try:
        plan = load_plan(folder / "plan.json")
    except PerfError:
        plan = {}
    update_cost_total(folder, plan)
    print("  Total de la investigación: %s" % cost_total(folder, plan))


DECISIONS = (("aprobar", "aprobada", "aprobadas"), ("descartar", "descartada", "descartadas"),
             ("pendiente", "pendiente", "pendientes"), ("aplicada", "aplicada", "aplicadas"))


CHANGES_DIR = "cambios"
DIFF_EXCERPT_LINES = 60  # lo que el reporte muestra de cada mejora; el diff completo queda en cambios/


def save_change_diff(folder, improvement, files, repo=None, index=0):
    """Guarda en <carpeta>/cambios/<id>.diff (o <id>-<n>.diff para otro repo) el diff de los archivos de una mejora
    contra HEAD de su repo: el código antes y después, con los archivos nuevos (que git todavía no sigue) completos. No
    toca el índice ni el árbol de trabajo. Devuelve lo que plan.json guarda de ese diff."""
    folder = pathlib.Path(folder)
    root = project_root(folder).resolve()
    base = pathlib.Path(os.path.expanduser(repo)) if repo else root
    base = base if base.is_absolute() else (pathlib.Path.cwd() / base)
    top = git_toplevel(base)
    if top is None:
        raise PerfError("%s no es un repo de git: el diff de la mejora se toma con git (usa --repo con la carpeta del "
                        "repo donde están los archivos)" % base)
    chunks = []
    for name in files:
        path = (base / name).resolve()
        inside = under(path, top.resolve())
        if inside is None:
            raise PerfError("%s no está dentro del repo %s: pasa --repo con el repo de ese archivo" % (name, top))
        tracked = subprocess.run(["git", "-C", str(top), "ls-files", "--error-unmatch", "--", str(inside)],
                                 capture_output=True, text=True).returncode == 0
        if tracked:
            done = subprocess.run(["git", "-C", str(top), "diff", "--no-color", "HEAD", "--", str(inside)],
                                  capture_output=True, text=True)
        elif path.is_file():
            done = subprocess.run(["git", "-C", str(top), "diff", "--no-color", "--no-index", "--", "/dev/null",
                                   str(inside)], capture_output=True, text=True)
        else:
            raise PerfError("%s no existe ni está en git: revisa la ruta (es relativa a %s)" % (name, base))
        if done.returncode not in (0, 1):
            raise PerfError("git diff falló con %s: %s" % (name, (done.stderr or "").strip()[:200]))
        chunks.append(done.stdout)
    text = "".join(chunks)
    safe = re.sub(r"[^\w.-]+", "-", str(improvement)).strip("-.") or "mejora"
    target = folder / CHANGES_DIR / ("%s%s.diff" % (safe, "-%d" % (index + 1) if index else ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    lines = text.splitlines()
    return {"diff": "%s/%s" % (CHANGES_DIR, target.name), "repo": shown_path(top, root) if top.resolve() != root else ".",
            "archivos": list(files), "fecha": datetime.date.today().isoformat(),
            "agregadas": sum(1 for line in lines if line.startswith("+") and not line.startswith("+++")),
            "quitadas": sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))}


def diff_excerpt(text, limit=DIFF_EXCERPT_LINES):
    """Lo esencial de un diff para el reporte: por archivo, su nombre y los fragmentos con lo agregado y lo quitado,
    sin las cabeceras de git; corta en `limit` líneas. (texto, líneas que quedaron fuera)."""
    out, skipped, header = [], 0, False
    for line in text.splitlines():
        if line.startswith("diff --git"):
            header = True  # hasta el primer @@: cabeceras de git, no código
            continue
        if line.startswith("@@"):
            header = False
        if header and line.startswith(("index ", "new file mode", "deleted file mode", "similarity", "rename ", "--- ",
                                       "Binary files")):
            if line.startswith("Binary files"):
                out.append("# binario: %s" % line)
            continue
        if header and line.startswith("+++ "):
            name = line[4:].strip()
            line = "# %s" % (name[2:] if name.startswith(("a/", "b/")) else name)
        if len(out) >= limit:
            skipped += 1
            continue
        out.append(line)
    return "\n".join(out), skipped


def changes_md(folder, plan, results, findings_text):
    """La sección "Cambios de código" del reporte final dev: por cada mejora aplicada, por qué se cambió (el hallazgo y
    su evidencia), qué mejoró (su métrica con el veredicto), los archivos y el código antes y después (un extracto del
    diff que guardó `decidir --aplicada`; el completo queda en cambios/). '' sin mejoras aplicadas."""
    folder = pathlib.Path(folder)
    applied = [m for m in plan.get("mejoras") or [] if m.get("estado") == "aplicada"]
    if not applied:
        return ""
    headers, rows = parse_table(findings_text)
    lower = [h.lower() for h in headers]

    def column(*prefixes):
        return next((i for i, h in enumerate(lower) if h.startswith(prefixes)), None)

    symptom_i, cause_i, evidence_i = column("síntoma", "sintoma"), column("causa"), column("evidencia")
    by_id = {row[0].strip(): row for row in rows if row}
    by_metric = {r["metrica"]: r for r in results}
    blocks = ["> **Interno: contiene código.** Lo que cambió cada mejora aplicada, por qué y qué mejoró. El extracto "
              "muestra lo esencial (en verde lo agregado, en rojo lo quitado); el diff completo queda en la carpeta "
              "`cambios/` de la investigación. No va en el reporte para gerencia."]
    for item in applied:
        lines = ["### %s · %s" % (item["id"], improvement_title(item)), ""]
        finding = by_id.get(str(item.get("hallazgo") or "").strip())

        def cell(index):
            value = finding[index].strip() if finding and index is not None and index < len(finding) else ""
            return "" if has_placeholder(value) or value in ("—", "-") else value

        why = "; ".join(part for part in (cell(symptom_i), cell(cause_i)) if part)
        lines.append("- **Por qué:** %s%s" % ("%s: %s" % (item["hallazgo"], why) if finding and why else
                                               "sin hallazgo asociado en estado.md",
                                               ". Evidencia: %s" % cell(evidence_i) if cell(evidence_i) else ""))
        if item.get("a_prueba") and item.get("hipotesis"):
            lines.append("- **Hipótesis que pone a prueba:** %s" % item["hipotesis"])
        r = by_metric.get(item.get("metrica"))
        lines.append("- **Qué mejoró:** %s" % (
            "`%s` pasó de %s a %s (%s): %s" % (r["metrica"], nice(r["antes"]["mediana"], r["unidad"]),
                                              nice(r["despues"]["mediana"], r["unidad"]),
                                              change_pct(r["antes"]["mediana"], r["despues"]["mediana"]) or "—",
                                              verdict_words(r)) if r else
            "su métrica (`%s`) no tiene antes y después" % item.get("metrica", "—")))
        entries = [entry for entry in item.get("cambios") or [] if isinstance(entry, dict) and entry.get("diff")]
        if not entries:
            lines += ["- **Código:** sin diff guardado (la mejora se marcó aplicada sin `--archivos`, o con una versión "
                      "anterior de la skill).", ""]
            blocks.append("\n".join(lines))
            continue
        for entry in entries:
            where = " (repo `%s`)" % entry["repo"] if entry.get("repo") not in (None, ".") else ""
            lines.append("- **Archivos%s:** %s · +%s −%s líneas · diff completo: `%s`" % (
                where, ", ".join("`%s`" % name for name in entry.get("archivos") or []), entry.get("agregadas", "—"),
                entry.get("quitadas", "—"), entry["diff"]))
            try:
                text = (folder / entry["diff"]).read_text(encoding="utf-8")
            except OSError:
                lines.append("- El diff guardado no está en la carpeta (`%s`): sin diff guardado." % entry["diff"])
                continue
            excerpt, skipped = diff_excerpt(text)
            if not excerpt.strip():
                lines.append("- El diff está vacío: los archivos no tenían cambios contra el último commit al marcarla.")
                continue
            lines += ["", "```diff", excerpt, "```"]
            if skipped:
                lines.append("_… y %d líneas más en `%s`._" % (skipped, entry["diff"]))
        lines.append("")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def cmd_decidir(args):
    folder = pathlib.Path(args.carpeta)
    plan_path = folder / "plan.json"
    plan = load_plan(plan_path)
    choices = {}
    for option, estado, _ in DECISIONS:
        for item in (getattr(args, option) or "").split(","):
            if item.strip() and item.strip() != "-":
                choices[item.strip()] = estado
    depth = getattr(args, "profundidad", None)
    if not choices and not depth:
        raise PerfError("indica al menos una mejora con --aprobar, --descartar, --pendiente o --aplicada (o cambia la "
                        "profundidad con --profundidad)")
    known = [m["id"] for m in plan.get("mejoras", [])]
    unknown = sorted(set(choices) - set(known))
    if unknown:
        raise PerfError("plan.json no tiene las mejoras %s (tiene: %s)" % (", ".join(unknown), ", ".join(known) or "ninguna"))
    files = [name.strip() for name in (getattr(args, "archivos", None) or "").split(",") if name.strip()]
    applied = [key for key, estado in choices.items() if estado == "aplicada"]
    if (files or getattr(args, "repo", None)) and len(applied) != 1:
        raise PerfError("--archivos y --repo van con --aplicada y una sola mejora: el diff es de esa mejora")
    if getattr(args, "repo", None) and not files:
        raise PerfError("--repo va con --archivos: los archivos de la mejora en ese repo")
    for item in plan.get("mejoras", []):
        if item["id"] in choices:
            item["estado"] = choices[item["id"]]
            if choices[item["id"]] == "aplicada":
                item["aplicada_en"] = datetime.datetime.now().isoformat(timespec="seconds")
                if files:
                    # Otro repo suma un diff; el mismo repo reemplaza el que tenía (repetir el comando no lo duplica).
                    before = [entry for entry in item.get("cambios") or [] if isinstance(entry, dict)]
                    entry = save_change_diff(folder, item["id"], files, getattr(args, "repo", None), len(before))
                    same = [old for old in before if old.get("repo") == entry["repo"]]
                    if same:
                        (folder / entry["diff"]).replace(folder / same[0]["diff"])
                        entry["diff"] = same[0]["diff"]
                    item["cambios"] = [old for old in before if old.get("repo") != entry["repo"]] + [entry]
                    print("✔ Diff de %s guardado: %s (%d %s, +%d −%d líneas)" % (
                        item["id"], folder / entry["diff"], len(entry["archivos"]),
                        "archivo" if len(entry["archivos"]) == 1 else "archivos", entry["agregadas"], entry["quitadas"]))
                elif not item.get("cambios"):
                    print("· %s quedó aplicada sin diff guardado: el reporte final dirá \"sin diff guardado\" en sus "
                          "cambios de código. Para guardarlo, repite con --archivos <archivos de la mejora> (y --repo "
                          "si están en otro repo)." % item["id"])
    parts = []
    if depth and depth != plan.get("profundidad", "riguroso"):
        parts.append("profundidad %s (era %s)" % (depth, plan.get("profundidad", "riguroso")))
        if depth == "riguroso":
            plan["desde_triage"] = True  # la línea base es la de un triage: `siguiente` pide completarla aunque ya haya una mejora aprobada
        else:
            plan.pop("desde_triage", None)
        plan["profundidad"] = depth
    elif depth:
        parts.append("profundidad %s (ya lo era)" % depth)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    parts += ["%s %s" % (label, ", ".join(k for k in known if choices.get(k) == estado))
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


# ── Carpetas de la investigación y de los parches ────────────────────────────
# En la sección de rendimiento de AGENTS.md: "Carpeta de investigaciones: <ruta>" y "Carpeta de parches: <ruta>" (con o
# sin viñeta, negrita o acentos graves; las rutas relativas parten de la raíz del proyecto). Sin esas líneas, las
# investigaciones van en reports/perf y los parches no tienen una carpeta por defecto.
DEFAULT_INVESTIGATIONS = "reports/perf"
FOLDER_KEYS = (("investigaciones", re.compile(r"carpeta\s+de\s+(?:las\s+)?(?:investigaciones|evidencia)|"
                                              r"(?:investigations|evidence)\s+folder", re.I)),
               ("parches", re.compile(r"carpeta\s+de\s+(?:los\s+)?parches|patch(?:es)?\s+folder", re.I)))
FOLDER_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?[*_]*(?P<key>[^:*_`]+?)[*_]*[ \t]*:[*_]*[ \t]*(?P<value>\S.*?)[ \t]*$")


def perf_folders(root):
    """{"investigaciones": ruta o None, "parches": ruta o None} según la sección de rendimiento del AGENTS.md del
    proyecto. None es "sin configurar", no una ruta por defecto. Las rutas no se resuelven: una carpeta enlazada se
    usa por su enlace."""
    out = {"investigaciones": None, "parches": None}
    agents = read_agents(root)
    section = performance_section(agents) if agents is not None else None
    if not section:
        return out
    for _, line in prose_lines(agents[section[0]:section[1]]):
        found = FOLDER_LINE.match(line.rstrip("\r\n"))
        if not found:
            continue
        name = next((name for name, pattern in FOLDER_KEYS if pattern.fullmatch(found.group("key").strip())), None)
        if not name or out[name] is not None:
            continue
        quoted = re.search(r"`([^`]+)`", found.group("value"))
        value = (quoted.group(1) if quoted else found.group("value")).strip().rstrip(".").strip()
        if not value or value.startswith("<"):
            continue
        path = pathlib.Path(os.path.expanduser(value))
        out[name] = path if path.is_absolute() else pathlib.Path(root) / path
    return out


def investigations_base(root):
    """La carpeta donde van las investigaciones del proyecto: la de AGENTS.md o, sin ella, reports/perf."""
    return perf_folders(root)["investigaciones"] or pathlib.Path(root) / DEFAULT_INVESTIGATIONS


def shown_path(path, root):
    """Una ruta para un comando que empieza con cd a la raíz: relativa si está dentro, absoluta si no."""
    inside = under(lexical(path), lexical(root)) or under(lexical(path), pathlib.Path(root))
    return str(inside) if inside is not None else str(path)


# ── Cambios temporales: quitar sin perder ────────────────────────────────────
REVERTED = re.compile(r"^(?:s[ií]|yes|hecho|revertido|✔)(?![a-záéíóúñ])", re.I)
NEVER_DISCARD = ("Nunca quites un cambio temporal con `git checkout`, `git restore`, `git reset --hard` ni `git clean`: "
                 "borran el archivo entero sin guardarlo, también lo que no es de esta investigación")


def temp_changes(state_text):
    """Las filas de "Cambios temporales por revertir" de estado.md: [{"archivo", "repo", "que", "revertido"}], sin las
    que siguen con el relleno de la plantilla."""
    _, sections = state_sections(state_text)
    body = next((text for title, text in sections.items() if title.startswith("cambios temporales")), "")
    headers, rows = parse_table(body)
    names = [header.strip().lower() for header in headers]

    def column(prefix):
        return next((index for index, name in enumerate(names) if name.lstrip("¿").startswith(prefix)), None)

    where, repo, what, reverted = column("archivo"), column("repo"), column("qué es"), column("revertido")
    if where is None:
        return []
    out = []
    for row in rows:
        def cell(index):
            return row[index].strip() if index is not None and index < len(row) else ""

        path = re.sub(r":\d+(?:-\d+)?$", "", cell(where).strip("`").strip())
        if not path or path in ("—", "-") or has_placeholder(cell(where)):
            continue
        out.append({"archivo": path, "repo": cell(repo).strip("`").strip(), "que": cell(what),
                    "revertido": bool(REVERTED.match(cell(reverted)))})
    return out


def final_report(folder):
    """El reporte final de una investigación (con el nombre de esta versión o de las anteriores), o None."""
    return report_file(folder, "final")


def open_investigations(folder, root):
    """Las otras investigaciones del mismo proyecto que siguen abiertas (con estado.md y sin reporte final): las que
    están junto a esta y las de la carpeta de investigaciones del proyecto. Solo busca dentro del proyecto."""
    folder = pathlib.Path(folder)
    own = folder.resolve()
    limits = (lexical(root), pathlib.Path(root).resolve())
    bases = [lexical(folder).parent, lexical(folder).parent.parent, investigations_base(root)]
    configured = perf_folders(root)["investigaciones"]
    seen, out = {own}, []
    for base in bases:
        inside = any(under(lexical(base), limit) is not None or under(base.resolve(), limit) is not None for limit in limits)
        if not inside and base != configured:
            continue
        for pattern in ("*/estado.md", "*/*/estado.md"):
            for state in sorted(base.glob(pattern)):
                other = state.parent.resolve()
                if other in seen:
                    continue
                seen.add(other)
                if not final_report(state.parent):
                    out.append(state.parent)
    return out


def untracked(root, path):
    """True si el archivo existe en el repo de la raíz y es nuevo para git: todavía no lo sigue, o solo está anotado
    con `git add -N` (así el paso de quitar sigue trayendo su `git reset` aunque el de guardar ya se haya corrido)."""
    if not (pathlib.Path(root) / path).is_file():
        return False
    try:
        status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", path], capture_output=True,
                                text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return status.returncode == 0 and status.stdout[:2] in ("??", " A")


def revert_notice(folder, root):
    """En el cierre: cómo quitar los cambios temporales que siguen puestos sin perderlos. Primero el parche fuera del
    repo, comprobado, y después `git apply -R`; nunca un comando que descarte el archivo. Si otra investigación
    abierta del proyecto declara el mismo archivo, va en un parche aparte y no se quita entero. None si no queda
    ninguno."""
    folder = pathlib.Path(folder)
    try:
        pending = [change for change in temp_changes((folder / "estado.md").read_text(encoding="utf-8"))
                   if not change["revertido"]]
    except OSError:
        return None
    if not pending:
        return None
    shared = {}
    mine = {change["archivo"] for change in pending}
    for other in open_investigations(folder, root):
        try:
            theirs = temp_changes((other / "estado.md").read_text(encoding="utf-8"))
        except OSError:
            continue
        for change in theirs:
            if not change["revertido"] and change["archivo"] in mine:
                shared.setdefault(change["archivo"], []).append(shown_path(other, root))
    patches = perf_folders(root)["parches"]
    name = slug("-".join(lexical(folder).parts[-2:]))

    def patch_path(suffix, at_root):
        """(ruta del parche para el comando, `mkdir` previo): relativa a la raíz si el comando corre ahí; si corre en
        otro repo, absoluta, para que el parche no quede dentro de ese repo."""
        if not patches:
            return "<carpeta-fuera-del-repo>/%s%s.patch" % (name, suffix), ""
        base = shown_path(patches, root) if at_root else str(lexical(patches))
        return shlex.quote("%s/%s%s.patch" % (base, name, suffix)), "mkdir -p %s && " % shlex.quote(base)

    names = ["`%s`" % change["archivo"] for change in pending]
    lines = ["Sin revertir (%d): %s%s" % (len(pending), ", ".join(names[:6]),
                                         " y %d más (en estado.md)" % (len(names) - 6) if len(names) > 6 else "")]
    groups = {}
    for change in pending:
        if change["archivo"] in shared:
            continue
        # En la raíz si el archivo (o su carpeta: un archivo nuevo ya quitado no existe) está en el repo de la raíz.
        here = (pathlib.Path(root) / change["archivo"]).exists() or (pathlib.Path(root) / change["archivo"]).parent.is_dir()
        groups.setdefault(str(root) if here else "<repo de %s>" % (change["repo"] or change["archivo"]), []).append(
            change["archivo"])
    for index, (repo, files) in enumerate(groups.items(), start=1):
        patch, ready = patch_path("" if len(groups) == 1 else "-%d" % index, repo == str(root))
        new = [path for path in files if repo == str(root) and untracked(root, path)]
        quoted = " ".join(shlex.quote(path) for path in files)
        added = " ".join(shlex.quote(path) for path in new)
        # `[ -s parche ] ||`: un parche que ya existe no se pisa. Repetir el paso después de quitar lo dejaría vacío.
        lines.append("Primero guarda el parche fuera del repo y comprueba que revierte limpio (si el parche ya existe no "
                     "lo pisa): `cd %s && %s%s{ [ -s %s ] || git diff --binary -- %s > %s; } && git apply --check -R %s`%s"
                     % (q_repo(repo), ready, "git add -N -- %s && " % added if new else "", patch, quoted, patch, patch,
                        "" if new or repo == str(root) else " (un archivo nuevo entra en el parche después de `git add "
                                                            "-N <archivo>`)"))
        lines.append("Después quítalos con el parche: `cd %s && git apply -R %s%s`%s" % (
            q_repo(repo), patch, " && git reset -q -- %s" % added if new else "",
            "" if new or repo == str(root) else " (y `git reset -q -- <archivo>` por cada archivo nuevo)"))
    for path, others in sorted(shared.items()):
        here = (pathlib.Path(root) / path).exists()
        patch, ready = patch_path("-compartido-%s" % slug(pathlib.PurePath(path).name), here)
        lines.append("`%s` también es un cambio temporal de otra investigación abierta (%s): guárdalo en un parche "
                     "aparte (`cd %s && %s{ [ -s %s ] || git diff --binary -- %s > %s; } && git apply --check -R %s`) y "
                     "no lo quites entero: quita a mano solo lo de esta investigación, o déjalo hasta que cierre la otra"
                     % (path, ", ".join(others), q(root) if here else "<su repo>", ready, patch, shlex.quote(path), patch,
                        patch))
    lines.append(NEVER_DISCARD)
    lines.append("Marca cada fila como revertida en estado.md cuando `git status --short` lo confirme")
    return {"tipo": "avisos", "titulo": "Cambios temporales por revertir (primero el parche, después quitar)",
            "lineas": lines}


def report_file(folder, kind):
    """El reporte `inicial` o `final` que hay en la carpeta, o None: primero el de desarrollo de esta versión
    (`reporte-<tipo>-dev`), después los nombres de las versiones anteriores (`reporte-<tipo>` y, para el final,
    `reporte`). HTML antes que markdown."""
    folder = pathlib.Path(folder)
    stems = ["reporte-%s-dev" % kind, "reporte-%s" % kind] + (["reporte"] if kind == "final" else [])
    return next((folder / (stem + suffix) for stem in stems for suffix in (".html", ".md")
                 if (folder / (stem + suffix)).is_file()), None)


def audience_file(folder, kind, audience):
    """El reporte `inicial` o `final` para un público (`dev` o `gerencia`), HTML antes que markdown, o None."""
    folder = pathlib.Path(folder)
    return next((folder / ("reporte-%s-%s%s" % (kind, audience, suffix)) for suffix in (".html", ".md")
                 if (folder / ("reporte-%s-%s%s" % (kind, audience, suffix))).is_file()), None)


# ── avisos que frenan o acompañan la medición ────────────────────────────────

SECRET_NAME = re.compile(r"CLAVE|PASS|PIN|TOKEN|SECRET|KEY", re.I)


def env_steps(names, where=None):
    """[(para qué, comando)] para cargar en la terminal cada variable de entorno que falta: lectura oculta si el nombre
    parece un secreto (SECRET_NAME) y normal si no. Usa printf y read sin -p para que sirva igual en bash y en zsh (en
    zsh, `read -p` no es el texto de la pregunta). Cada comando empieza con cd a `where` (por defecto, la carpeta
    actual)."""
    steps = []
    for name in names:
        hidden = bool(SECRET_NAME.search(name))
        steps.append(("carga %s en esta terminal (%s)" % (name, "lectura oculta: lo que escribas no se ve" if hidden
                                                          else "lectura normal"),
                      "cd %s && printf '%s: ' && read -r %s%s && export %s"
                      % (shlex.quote(str(where or os.getcwd())), name, "-s " if hidden else "",
                         name + (" && echo" if hidden else ""), name)))
    return steps


NOTES_FILE = "advertencias.json"
NOTE_MAX = 300


def read_notes(folder):
    """Lo que perf.py observó en los comandos de esta investigación y todavía importa (advertencias.json): los avisos
    de la última corrida de prueba, las corridas inválidas, los avisos de cada captura y lo que el diagnóstico no midió."""
    try:
        data = json.loads((pathlib.Path(folder) / NOTES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_notes(folder, data):
    path = pathlib.Path(folder) / NOTES_FILE
    data = {key: value for key, value in data.items() if value}
    if not data and not path.is_file():
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def note_bucket(data, *keys):
    """El diccionario anidado data[k1][k2]…, creado si falta (o si lo guardado no tiene esa forma)."""
    for key in keys:
        if not isinstance(data.get(key), dict):
            data[key] = {}
        data = data[key]
    return data


def one_line(text):
    text = " ".join(str(text).split())
    return text if len(text) <= NOTE_MAX else text[:NOTE_MAX - 1].rstrip() + "…"


def save_dev_restore(folder, settings, command):
    """Guarda, la primera vez que se ven fuera de lo normal, cómo estaban las opciones de desarrollador y el comando
    para volverlas a ese estado: queda en "Advertencias para el diagnóstico" aunque después se dejen normales, para
    devolverlas al terminar. Una vez guardado no se pisa."""
    try:
        data = read_notes(folder)
        if isinstance(data.get("ajustes_originales"), dict):
            return
        data["ajustes_originales"] = {"fecha": datetime.date.today().isoformat(), "valores": dev_settings_text(settings),
                                      "comando": command}
        save_notes(folder, data)
    except OSError:
        pass  # sin carpeta donde guardarlo (un humo sin investigación): el comando ya se imprimió


def save_test_warnings(folder, flow, warnings):
    """Guarda los avisos de la corrida de prueba de un flujo; una corrida sin avisos los da por resueltos."""
    data = read_notes(folder)
    tests = note_bucket(data, "prueba")
    if warnings:
        tests[flow] = {"fecha": datetime.datetime.now().replace(microsecond=0).isoformat(), "skill": VERSION,
                       "avisos": warnings}
    elif flow in tests:
        tests.pop(flow)
    else:
        return
    save_notes(folder, data)


def test_warnings(folder, flow):
    """Los avisos vigentes de la última corrida de prueba del flujo: [{"tipo", "texto", "corto", "donde"}, y
    "comandos" ([para qué, comando]) si se resuelven en la terminal]."""
    record = (read_notes(folder).get("prueba") or {}).get(flow) or {}
    found = record.get("avisos") if isinstance(record, dict) else None
    return [item for item in found or [] if isinstance(item, dict) and item.get("texto")]


def count_invalid(folder, phase, flow, reason):
    """Suma una corrida inválida (con su motivo) a lo que la sección de advertencias cuenta de esa fase y ese flujo."""
    data = read_notes(folder)
    bucket = note_bucket(data, "invalidas", phase, flow)
    key = one_line(reason)[:160]
    bucket[key] = to_int(bucket.get(key)) + 1
    save_notes(folder, data)


def save_capture_warnings(folder, phase, flow, warnings):
    """Los avisos con los que arrancó una captura de esa fase y ese flujo (build depurable, dispositivo tibio, batería,
    build o versión distintos), sin repetir."""
    if not warnings:
        return
    data = read_notes(folder)
    bucket = note_bucket(data, "capturar", phase)
    known = [text for text in bucket.get(flow) or [] if isinstance(text, str)]
    bucket[flow] = known + [text for text in (one_line(w) for w in warnings) if text not in known]
    save_notes(folder, data)


def forget_notes(folder, phase, flow):
    """--rehacer: lo que se anotó de las corridas que se descartan ya no vale."""
    data = read_notes(folder)
    changed = False
    for kind in ("invalidas", "capturar", "diagnostico"):
        bucket = (data.get(kind) or {}).get(phase) if isinstance(data.get(kind), dict) else None
        if isinstance(bucket, dict) and flow in bucket:
            bucket.pop(flow)
            changed = True
    if changed:
        save_notes(folder, data)


MARK_LITERAL = re.compile(r"MARK ([\w.:-]+)")
MARK_SOURCES_MAX = 3


def find_mark_sources(root, mark, patterns=None):
    """Dónde emite el código una marca `MARK <nombre>`: los "archivo:línea" (hasta MARK_SOURCES_MAX) donde aparece su
    nombre como texto entre comillas, en los .kt y .java del proyecto y de los módulos que settings.gradle incluye desde
    fuera. Es una búsqueda por texto, sin leer las rutas prohibidas; vacío si la marca no es una MARK con nombre fijo."""
    found = MARK_LITERAL.fullmatch(mark or "")
    if not found:
        return []
    needle, root = '"%s"' % found.group(1), pathlib.Path(root)
    patterns = read_no_leer(root) if patterns is None else patterns
    out = []
    for base in [root] + list(external_roots(root, patterns)[0]):
        for path in walk_files(base, patterns, (".kt", ".java"), root):
            try:
                if path.stat().st_size > SCAN_MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            start = text.find(needle)
            while start != -1 and len(out) < MARK_SOURCES_MAX:
                out.append("%s:%d" % (relative_to_root(path, root), text.count("\n", 0, start) + 1))
                start = text.find(needle, start + 1)
            if len(out) >= MARK_SOURCES_MAX:
                return out
    return out


def warning(kind, text, short, where=(), commands=()):
    """Un aviso de la corrida de prueba. `commands` ([(para qué, comando)]): lo que el usuario corre en su terminal para
    resolverlo, sin chat (por ejemplo, dejar normales las opciones de desarrollador)."""
    item = {"tipo": kind, "texto": one_line(text), "corto": one_line(short), "donde": list(where)[:5]}
    if commands:
        item["comandos"] = [[what, command] for what, command in commands]
    return item


def at_limit(names):
    """Los nombres de sección que llegan al límite de android.os.Trace (127 caracteres): están cortados, y dos endpoints
    con el mismo comienzo pueden contar como uno."""
    return sorted(name for name in names if len(name) >= SECTION_NAME_MAX)


def test_run_warnings(root, plan_rate, info, gap, missing_builders, startup=False, settings=None, serial=None):
    """Los avisos de una corrida de prueba válida que conviene corregir antes de medir, como los guarda
    save_test_warnings: las opciones de desarrollador fuera de lo normal, la tasa de refresco, las marcas del plan que
    no salieron, las métricas que incluyen pasos del recorrido, las marcas repetidas en una carga, la red sin medir y
    los nombres de sección cortados."""
    out = []
    if dev_settings_text(settings):
        fix, back = dev_settings_commands(settings, serial, root)
        out.append(warning(
            "ajustes", "opciones de desarrollador fuera de lo normal: %s. %s" % (dev_settings_text(settings), DEV_SETTINGS_WHY),
            "opciones de desarrollador fuera de lo normal (%s): déjalas normales antes de medir; si quieres medir con "
            "ellas a propósito, es otra investigación (ficha.md · Opciones de desarrollador)" % dev_settings_text(settings),
            commands=[("deja normales las opciones de desarrollador (sin chat)%s" % (
                "; %s" % ALWAYS_FINISH_NOTE if not dev_setting_normal("always_finish_activities",
                                                                      settings.get("always_finish_activities")) else ""),
                       fix),
                      ("al terminar la investigación, si quieres, vuélvelas a como estaban", back)]))
    rate = hz_warning(plan_rate, [info.get("hz_traza")])
    if rate:
        out.append(warning("hz", rate, "la tasa de refresco del plan no es la que midió la traza: corrige 'hz' en plan.json"))
    unseen = [(mark, where) for mark, where, seen in info.get("marcas_plan") or [] if not seen]
    for mark, where in unseen:
        out.append(warning("marca", "la marca '%s' del plan (%s) no salió en la traza" % (mark, ", ".join(where)),
                           "la marca '%s' del plan no salió en la traza: revisa dónde se emite, o el plan" % mark,
                           find_mark_sources(root, mark)))
    if info.get("faltantes") and not unseen:
        out.append(warning("sin_marcas", "sin marcas en orden para: %s" % ", ".join(info["faltantes"]),
                           "sin marcas en orden para %s: revisa 'desde' y 'hasta' en plan.json" % ", ".join(info["faltantes"])))
    for name, count in sorted((info.get("con_input") or {}).items()):
        out.append(warning("input", "la métrica %s incluye pasos del recorrido (%d eventos de input entre sus marcas): "
                                    "mide el script, no la app" % (name, count),
                           "la métrica %s incluye pasos del recorrido: acórtala en plan.json a un solo salto, de la marca de "
                           "la acción a la de su contenido" % name))
    for name, count in sorted((info.get("marcas_repetidas") or {}).items()):
        out.append(warning("repetida", "la marca '%s' salió %d veces en una misma carga: el gancho que la emite se llama "
                                       "más de una vez por carga" % (name, count),
                           "la marca '%s' sale %d veces por carga: que se emita una sola vez por carga" % (name, count),
                           find_mark_sources(root, name)))
    if gap:
        out.append(warning("red", "red sin medir: la corrida no tiene ninguna sección HTTP y el proyecto o el plan la "
                                  "esperan", "red sin medir: conecta el gancho de red de PerfHooks en cada "
                                             "OkHttpClient.Builder (setup.md · Red: conectar cada builder)",
                           missing_builders))
    cut = at_limit(info.get("nombres") or {})
    if cut:
        out.append(warning("nombre", "%d nombres de sección llegan al límite de %d caracteres de android.os.Trace y están "
                                     "cortados (por ejemplo '…%s'): dos endpoints con el mismo comienzo pueden contar como uno"
                           % (len(cut), SECTION_NAME_MAX, cut[0][-40:]),
                           "hay nombres de sección cortados en %d caracteres: actualiza la instrumentación (perf.py "
                           "instrumentar --actualizar) para que HttpSectionName acorte desde la izquierda"
                           % SECTION_NAME_MAX))
    return out


def test_warning_steps(folder, root, plan, flow, pending, resume, capture_test, capture_before, you_run):
    """Los pasos de `siguiente` mientras la última corrida de prueba tenga avisos: no ofrece medir antes como paso
    normal. Primero los avisos, uno por línea; después lo que corre el usuario en su terminal para los avisos que se
    resuelven sin código (las opciones de desarrollador), el chat que corrige el resto (sin compilar, instalar ni
    capturar), instalar y repetir la prueba y, como opción, medir igual."""
    in_code = [item for item in pending if not item.get("comandos")]
    listed = []
    for index, item in enumerate(in_code, start=1):
        where = " (%s)" % ", ".join(item.get("donde") or []) if item.get("donde") else ""
        listed.append("%d) %s%s" % (index, (item.get("corto") or item["texto"]).rstrip("."), where))
    lines = []
    for item in pending:
        lines.append(item["texto"] + (" · %s" % ", ".join(item["donde"]) if item.get("donde") else ""))
        commands = [pair for pair in item.get("comandos") or [] if isinstance(pair, list) and len(pair) == 2]
        lines += ["%s: %s" % (what[0].upper() + what[1:], command) for what, command in commands[1:]]
    steps = [{"tipo": "avisos", "titulo": "Corrige antes de medir", "lineas": lines}]
    for item in pending:
        commands = [pair for pair in item.get("comandos") or [] if isinstance(pair, list) and len(pair) == 2]
        if commands:
            steps.append(terminal(commands[0][1], commands[0][0], "córrelo en la terminal donde mides; no cambia el código "
                                  "ni la app"))
    if in_code:
        prompt = ("%s: corrige los avisos de la corrida de prueba del flujo '%s', sin compilar, instalar ni capturar (eso "
                  "lo hago yo en mi terminal): %s." % (resume, flow, "; ".join(listed)))
        steps += [chat(prompt, "intermedio", "medio", "corrige en el código o en plan.json lo que dicen los avisos; no "
                       "compila, no instala y no captura", plan),
                  terminal(install_command(plan, root), "compila e instala el build de profiling con las correcciones",
                           "espera; si solo cambió plan.json, salta este paso")]
    return steps + [
        terminal(capture_test, "repite la corrida de prueba: si sale sin avisos, quedan resueltos y el paso siguiente pasa "
                 "a ser medir antes", "lo mismo que en una corrida, una sola vez"),
        terminal(capture_before, "OPCIÓN, solo si decides medir igual con estos avisos: lo que se mida así puede salir sin "
                 "red, midiendo el recorrido o con otras condiciones, y habría que repetirlo con --rehacer", you_run)]


# ── advertencias para el diagnóstico (estado.md) ─────────────────────────────

WARNINGS_TITLE = "Advertencias para el diagnóstico"
WARNINGS_INTRO = ("Lo que `perf.py` observó en los comandos de la terminal y que la sesión 2 lee antes que las métricas. Si "
                  "una mejora toca algo que una advertencia menciona, la mejora lo dice. Lo escribe y lo mantiene `perf.py`: "
                  "no lo edites.")
NO_WARNINGS = ("Ninguna registrada hasta ahora. `perf.py` solo ve lo que pasa en sus comandos: que no haya advertencias no "
               "prueba que no haya nada que advertir.")
NOT_ALTERING = ("", "—", "-", "no", "nada", "ninguna", "ninguno", "n/a")


def altering_changes(state_text):
    """Las filas de "Cambios temporales por revertir" de estado.md que dicen qué métricas alteran (columna "Altera"):
    un cambio puesto para la investigación que cambia el comportamiento de la app mientras se mide."""
    _, sections = state_sections(state_text)
    body = next((text for title, text in sections.items() if title.startswith("cambios temporales")), "")
    headers, rows = parse_table(body)
    names = [header.strip().lower() for header in headers]

    def column(prefix):
        return next((index for index, name in enumerate(names) if name.lstrip("¿").startswith(prefix)), None)

    altered, where, what, reverted = column("altera"), column("archivo"), column("qué es"), column("revertido")
    if altered is None:
        return []
    out = []
    for row in rows:
        def cell(index):
            return row[index].strip() if index is not None and index < len(row) else ""

        if cell(altered).lower() in NOT_ALTERING or has_placeholder(cell(altered)):
            continue
        label = " · ".join(part for part in (cell(where), cell(what)) if part) or "sin detalle"
        out.append("Cambio temporal que altera la app: %s → altera %s%s" % (
            label, cell(altered), " (¿revertido?: %s)" % cell(reverted) if cell(reverted) else ""))
    return out


def noise_lines(rows, plan, trust=("ok", "")):
    """El ruido entre antes y control de cada métrica principal y la mejora mínima que se podría demostrar, con el
    criterio de `verdict`: la mediana de después tiene que salir del rango de antes y diferir de la de antes más que
    el ruido."""
    principales = plan.get("principales") or []
    out = []
    for (flow, metric), entry in sorted(group(rows).items(), key=lambda kv: (kv[0][0], priority(kv[0][1], plan))):
        before, control = entry["fases"].get("antes"), entry["fases"].get("control")
        if metric not in principales or not before:
            continue
        unit, head = entry["unidad"], "Ruido de `%s` (%s)" % (metric, flow)
        if entry["familia"] == "info":
            out.append("%s: es informativa, `comparar` no le da veredicto" % head)
            continue
        if frame_metric(metric) and trust[0] == "no":
            out.append("%s: frames no confiables (%s), `comparar` no le da veredicto" % (head, trust[1]))
            continue
        middle = statistics.median(before)
        lower = entry["sentido"] == "menor"
        noise = abs(statistics.median(control) - middle) if control else None
        if lower:
            limit = min(min(before), middle - noise) if control else min(before)
        else:
            limit = max(max(before), middle + noise) if control else max(before)
        gap = abs(middle - limit)
        need = "la mediana de después tiene que quedar %s %s (más de %s%s respecto de la mediana de antes, %s)" % (
            "por debajo de" if lower else "por encima de", fmt(limit, unit), fmt(gap, unit),
            ", %s" % fmt_pct(gap / abs(middle) * 100, signed=False) if middle else "", fmt(middle, unit))
        if control:
            out.append("%s: antes y control difieren en %s%s sin ningún cambio. Mejora mínima demostrable: %s" % (
                head, fmt(noise, unit), " (%s)" % fmt_pct(noise / abs(middle) * 100, signed=False) if middle else "", need))
        else:
            out.append("%s: sin fase control, el ruido no está medido. Para que `comparar` diga mejora, %s" % (head, need))
    return out


def warnings_lines(folder, plan):
    """Las advertencias vigentes de la investigación, una por línea y sin repetir: avisos de la última corrida de
    prueba, corridas inválidas por fase (con los fallos de 'preparar'), avisos de las capturas, lo que el diagnóstico
    no midió, el ruido entre antes y control de cada principal y los cambios temporales que alteran la app."""
    folder = pathlib.Path(folder)
    notes = read_notes(folder)
    lines = []

    def by_flow(kind, phase):
        bucket = (notes.get(kind) or {}).get(phase) if isinstance(notes.get(kind), dict) else None
        return sorted(bucket.items()) if isinstance(bucket, dict) else []

    original = notes.get("ajustes_originales") if isinstance(notes.get("ajustes_originales"), dict) else {}
    if original.get("comando"):
        lines.append(" ".join(("Opciones de desarrollador: el %s, algunas estaban fuera de lo normal (%s). Para volverlas a como "
                              "estaban al terminar la investigación: %s" % (original.get("fecha", "—"),
                                                                              original.get("valores", "—"),
                                                                              original["comando"])).split()))
    tests = notes.get("prueba") if isinstance(notes.get("prueba"), dict) else {}
    for flow in sorted(tests):
        for item in test_warnings(folder, flow):
            where = item.get("donde") if isinstance(item.get("donde"), list) else []
            lines.append(one_line("Corrida de prueba (%s): %s%s" % (
                flow, item["texto"], " · %s" % ", ".join(str(place) for place in where) if where else "")))
    for phase in FASES:
        for flow, reasons in by_flow("invalidas", phase):
            if isinstance(reasons, dict) and reasons:
                lines.append("Corridas inválidas en %s (%s): %d · %s" % (
                    phase, flow, sum(to_int(n) for n in reasons.values()),
                    "; ".join("%d × %s" % (to_int(n), reason) for reason, n in sorted(reasons.items()))))
    for phase in FASES:
        for flow, texts in by_flow("capturar", phase):
            lines += ["Captura de %s (%s): %s" % (phase, flow, one_line(text))
                      for text in (texts if isinstance(texts, list) else []) if isinstance(text, str)]
    phases = read_phases(folder)
    if isinstance(phases, dict):
        lines += ["Fases: %s" % one_line(note) for note in builds_table(folder)[1]]
        lines += ["Fase %s: compilación de ART %s, sus tiempos no se comparan con los de otra fase" % (
            phase, phases[phase]["compilacion"]) for phase in FASES
            if str((phases.get(phase) or {}).get("compilacion") or "").startswith("sin fijar")]
        lines += ["Fases: %s" % one_line(note) for note in config_notes(folder, list(plan.get("flujos") or {}))]
    for phase in FASES:
        for flow, texts in by_flow("diagnostico", phase):
            lines += ["Diagnóstico de %s (%s): %s" % (phase, flow, one_line(text))
                      for text in (texts if isinstance(texts, list) else []) if isinstance(text, str)]
    try:
        rows = read_rows(folder / "metricas.csv") if (folder / "metricas.csv").is_file() else []
    except PerfError:
        rows = []
    lines += noise_lines(rows, plan, frames_trust(folder) if isinstance(phases, dict) else ("ok", ""))
    try:
        lines += altering_changes((folder / "estado.md").read_text(encoding="utf-8"))
    except OSError:
        pass
    out = []
    for line in lines:
        if line not in out:
            out.append(line)
    return out


def update_warnings(folder, plan):
    """Escribe el bloque "Advertencias para el diagnóstico" de estado.md. Un estado.md de una versión anterior no trae
    la sección: se agrega antes de "Hallazgos" (o, si no está, antes del plan de mejoras o al final)."""
    state = pathlib.Path(folder) / "estado.md"
    if not state.is_file():
        return False
    lines = warnings_lines(folder, plan)
    content = "\n".join("- %s" % line for line in lines) if lines else "- %s" % NO_WARNINGS
    if update_block(folder, "advertencias", content):
        return True
    text = state.read_text(encoding="utf-8")
    section = "## %s\n\n%s\n\n<!-- perf:advertencias -->\n%s\n<!-- /perf:advertencias -->\n" % (
        WARNINGS_TITLE, WARNINGS_INTRO, content)
    for anchor in ("## Hallazgos", "## Plan de mejoras", "## Decisiones"):
        found = re.search(r"^%s[ \t]*$" % re.escape(anchor), text, re.M)
        if found:
            text = text[:found.start()] + section + "\n" + text[found.start():]
            break
    else:
        text = text.rstrip("\n") + "\n\n" + section
    state.write_text(text, encoding="utf-8")
    return True


# ── AGENTS.md del proyecto: DoD y estado del setup ───────────────────────────

# Encabezados de un AGENTS.md: se aceptan numerados ("## 5. DoD") y con hasta 3 espacios de sangría, como en Markdown.
DOD_HEADING = re.compile(r"^\ufeff?[ \t]{0,3}#{1,6}[ \t]*(?:\d+[.)][ \t]*)?(?:DoD|Definition of Done|Definición de "
                         r"(?:hecho|terminado))\b", re.I)
# La sección de rendimiento es la que se llama así: el título empieza con la palabra, no basta con que la mencione.
PERF_HEADING = re.compile(r"^\ufeff?[ \t]{0,3}(#{1,6})[ \t]+(?:\d+[.)][ \t]*)?(?:rendimiento|performance)\b", re.I)
ANY_HEADING = re.compile(r"^\ufeff?[ \t]{0,3}(#{1,6})[ \t]+\S")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
AGENTS_BLOCK = ("<!-- hb-performance:estado -->", "<!-- /hb-performance:estado -->")
AGENTS_FIELDS = ("instrumentación en el repo", "prueba de humo", "secciones HTTP")
AGENTS_LEAD = "Estado del setup (lo mantiene `perf.py`: no lo edites)"


def read_agents(root):
    """El AGENTS.md del proyecto con sus saltos de línea tal cual (un archivo con CRLF no se normaliza), o None."""
    try:
        with open(str(pathlib.Path(root) / "AGENTS.md"), encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, ValueError):
        return None


def prose_lines(text):
    """(posición, línea) de las líneas que no están dentro de un bloque de código: un `#` de un comando no es un
    encabezado."""
    position, fence = 0, None
    for line in text.splitlines(keepends=True):
        mark = FENCE.match(line)
        if fence is None and mark:
            fence = mark.group(1)  # abre un bloque: lo cierra una línea con el mismo carácter y al menos igual de larga
        elif fence is not None:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) \
                    and not line[mark.end():].strip():
                fence = None
        else:
            yield position, line
        position += len(line)


def has_dod(text):
    return any(DOD_HEADING.match(line) for _, line in prose_lines(text))


def dod_notice(root, plan):
    """Antes de una sesión 3: None si AGENTS.md tiene `## DoD`; si no, el aviso con una plantilla mínima para
    completarla con lo que el proyecto ya tiene (los tests unitarios del módulo que cambie y la compilación de la
    variante medida), sin agregar herramientas."""
    agents = read_agents(root)
    if agents is not None and has_dod(agents):
        return None
    found = INSTALL_TASK.search(plan.get("instalar") or "")
    assemble = "./gradlew -q :<módulo-de-la-app>:assemble<VarianteMedida>"
    if found:  # del 'instalar' del plan: con su módulo si lo trae; sin módulo, la tarea sin ':' (la busca en todos)
        assemble = "./gradlew -q %sassemble%s" % (":" + found.group(1) if found.group(1) else "", found.group(2))
    return {"tipo": "avisos", "crudo": True,
            "titulo": "%s: la sesión 3 corre \"los comandos de ## DoD\" y sin esa sección tendría que adivinar qué validar. "
                      "Agrégala a AGENTS.md antes de abrir el chat, con lo que el proyecto ya tiene (sin herramientas "
                      "nuevas). Plantilla" % ("AGENTS.md no tiene `## DoD`" if agents is not None else
                                              "No hay AGENTS.md en %s (o no se pudo leer)" % root),
            "lineas": ["## DoD", "",
                       "1. `./gradlew -q :<módulo>:test<Variante>UnitTest`: los tests unitarios del módulo que cambie (la "
                       "tarea real: `./gradlew :<módulo>:tasks --all | grep UnitTest`)",
                       "2. `%s`: compila la variante medida" % assemble]}


def performance_section(text):
    """(inicio, fin) de la sección de rendimiento de un AGENTS.md: desde la línea que sigue a su encabezado hasta el
    próximo encabezado de su nivel o superior (o el final), sin contar lo que está dentro de un bloque de código. Si
    hay más de una, la que ya tiene el bloque de estado; si no, la primera. None si no hay sección."""
    headings = [(position, line, ANY_HEADING.match(line)) for position, line in prose_lines(text)]
    headings = [(position, line, found) for position, line, found in headings if found]
    sections = []
    for index, (position, line, _) in enumerate(headings):
        own = PERF_HEADING.match(line)
        if not own:
            continue
        level = len(own.group(1))
        end = next((later for later, _, found in headings[index + 1:] if len(found.group(1)) <= level), len(text))
        sections.append((position + len(line), end))
    if not sections:
        return None
    return next((section for section in sections if AGENTS_BLOCK[0] in text[section[0]:section[1]]), sections[0])


def agents_state(body):
    """{campo: valor} del bloque de estado que perf.py mantiene en la sección de rendimiento."""
    found = re.search(re.escape(AGENTS_BLOCK[0]) + r"(.*?)" + re.escape(AGENTS_BLOCK[1]), body, re.S)
    inner = " ".join((found.group(1) if found else "").split())
    fields = {}
    for key in AGENTS_FIELDS:
        value = re.search(r"%s: (.*?)(?= · |$)" % re.escape(key), inner)
        if value and value.group(1).strip():
            fields[key] = value.group(1).strip()
    return fields


def update_agents_state(root, humo=None, http=None):
    """Mantiene, dentro de la sección de rendimiento del AGENTS.md del proyecto, un bloque corto entre marcadores con
    el estado del setup: si la instrumentación está en el repo, cómo salió la prueba de humo, si hay secciones HTTP y
    con qué versión de la skill. Solo cambia los campos que recibe; no toca nada fuera del bloque ni fuera de la
    sección, y si no hay sección no la crea. Devuelve la línea que se le dice al usuario ('' si nada cambió)."""
    path = pathlib.Path(root) / "AGENTS.md"
    text = read_agents(root)
    if text is None:
        return "· No hay AGENTS.md en %s (o no se pudo leer): el estado del setup no queda anotado" % root
    section = performance_section(text)
    if section is None:
        return ("· AGENTS.md no tiene una sección de rendimiento (## Rendimiento o ## Performance): no la creo, así que el "
                "estado del setup no queda anotado ahí (la escribe la sesión 0: setup.md · Cierre del setup)")
    start, end = section
    body = text[start:end]
    fields = agents_state(body)
    fields["instrumentación en el repo"] = "sí" if find_instrumentation(root)[1] else "no (no encontré PerfHooks.kt)"
    if humo:
        fields["prueba de humo"] = humo
    if http:
        fields["secciones HTTP"] = http
    fields.setdefault("prueba de humo", "sin correr")
    fields.setdefault("secciones HTTP", "sin dato")
    line = "- %s: %s · hb-performance %s" % (AGENTS_LEAD, " · ".join("%s: %s" % (key, fields[key]) for key in AGENTS_FIELDS),
                                             VERSION)
    eol = "\r\n" if "\r\n" in text else "\n"  # el salto de línea que ya usa el archivo
    block = eol.join((AGENTS_BLOCK[0], line, AGENTS_BLOCK[1]))
    pattern = re.compile(re.escape(AGENTS_BLOCK[0]) + r".*?" + re.escape(AGENTS_BLOCK[1]), re.S)
    if pattern.search(body):
        new_body = pattern.sub(lambda _: block, body, count=1)
    elif AGENTS_BLOCK[0] in body:  # un marcador de apertura suelto: el bloque va en su lugar
        new_body = body.replace(AGENTS_BLOCK[0], block, 1)
    else:
        stripped = body.rstrip("\r\n")
        new_body = (stripped + eol * 2 if stripped.strip() else eol) + block + eol + (eol if end < len(text) else "")
    if new_body == body:
        return ""
    try:
        with open(str(path), "w", encoding="utf-8", newline="") as handle:
            handle.write(text[:start] + new_body + text[end:])
    except OSError as error:  # no poder anotarlo no puede romper la prueba de humo ni la corrida de prueba
        return "⚠ No pude escribir %s (%s): el estado del setup no quedó anotado ahí" % (path, error.strerror or error)
    return "✔ AGENTS.md: estado del setup actualizado en la sección de rendimiento (%s)" % " · ".join(
        "%s: %s" % (key, fields[key]) for key in AGENTS_FIELDS)


def http_state(current, seen, source):
    """El valor de "secciones HTTP" después de una corrida de prueba: None si no hay nada nuevo que anotar. Una
    corrida que las ve las anota una vez (no cambia la fecha en cada prueba). Una que las esperaba y no las vio lo dice
    solo si nadie las vio antes: un flujo que no hace llamadas no desmiente la red que ya se comprobó (su aviso queda
    en advertencias.json)."""
    today = datetime.date.today().isoformat()
    if (current or "").startswith("sí"):
        return None
    return "sí (%s, %s)" % (source, today) if seen else "sin medir: la %s del %s no trajo ninguna" % (source, today)


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
    if args.sin_compilar and getattr(args, "compilar", False):
        raise PerfError("--sin-compilar y --compilar se contradicen: elige una")
    startup = None if args.recorrido else startup_spec(flow)
    prepare_command = None if startup else (args.preparar or flow.get("preparar") or "").strip() or None
    secret_names, undeclared = required_env(flow, prepare_command, folder)
    declared = [name for name in secret_names if name not in undeclared]
    # La salida estándar de 'preparar' solo se mira si el plan declara requiere_env, como siempre. De las detectadas sin
    # declarar se enmascara el valor en lo que se muestre, salvo los muy cortos (un "1" o un "3" no son un secreto, y
    # enmascararlos dejaría ilegible la salida).
    mask_names = declared + [name for name in undeclared if len(os.environ.get(name, "")) >= 4]
    if undeclared:
        print("⚠ " + undeclared_warning(flow_name, undeclared))
    absent = missing_env(secret_names)
    if absent and set(absent) <= set(undeclared) and args.forzar:
        print("⚠ faltan en el entorno %s, que 'preparar' usa sin declarar: sigo por --forzar" % ", ".join(absent))
    elif absent:
        origin = "requiere_env" if not set(absent) & set(undeclared) else \
            "requiere_env, o las usa 'preparar' sin que el plan las declare"
        hint = "" if not set(absent) & set(undeclared) else \
            ". Si alguna no hace falta de verdad, dale un valor por defecto en el script (${VAR:-}) o usa --forzar"
        raise Precondicion("faltan variables de entorno que el flujo '%s' necesita (%s): %s. Expórtalas en esta "
                           "terminal antes de correr el comando; si lo corre un agente, antes de abrir el agente (solo ve "
                           "las de la terminal donde se abrió)%s" % (flow_name, origin, ", ".join(absent), hint)).con(
            seguir=env_steps(absent) + [("corre de nuevo el comando, en esta misma terminal", same_command())])
    phase = "antes" if args.prueba else normalize_phase(args.fase)
    csv_path = folder / "metricas.csv"
    target = 1 if args.prueba else args.corridas
    progress = {"validas": 0}

    def guide():
        """Deja en GUIA qué quedó guardado y el comando para seguir, según las corridas válidas de esta tanda."""
        if args.prueba:
            GUIA.update(guardado="nada: la corrida de prueba no guarda métricas", seguir=[(RETRY, same_command())])
            return
        done = progress["validas"]
        if not done:
            kept = ("las corridas anteriores de %s ya se descartaron por --rehacer (sus trazas quedaron en "
                    "%s-descartada-<hora>/)" % (phase, phase) if progress.get("descartada")
                    else "lo que %s ya tenía sigue igual" % csv_path)
            GUIA.update(guardado="ninguna corrida de esta tanda (0 de %d válidas de %s); %s" % (target, phase, kept),
                        seguir=[(RETRY, same_command())])
            return
        GUIA.update(
            guardado="%d de %d corridas válidas de %s en %s (y su registro en fases.json)" % (done, target, phase, csv_path),
            seguir=[("completa la fase con las %d corridas que faltan (las %d guardadas cuentan si nada cambió)"
                     % (target - done, done), same_command(corridas=target - done, sin=("--rehacer",))),
                    ("o, si cambió el build o las condiciones, repite la fase entera",
                     same_command(corridas=target, sin=("--rehacer",)) + " --rehacer")])

    guide()
    package = plan["paquete"]
    hz = args.hz or (plan.get("hz") if isinstance(plan.get("hz"), int) else None)
    route = None if startup else args.recorrido or flow.get("recorrido")
    if isinstance(route, str) and route != "manual" and uses_pause(route, folder) and not has_tty():
        raise Precondicion("el recorrido del flujo '%s' tiene una pausa humana (perf.py pausa) y %s"
                           % (flow_name, NO_TTY[0].lower() + NO_TTY[1:]))
    recorrido = args.recorrido or (flow.get("recorrido") if not startup else None) or "manual"
    tp = find_tp(args.tp)
    serial = select_device(args.serial or plan.get("serial"))
    adb = Adb(serial)
    sdk, warnings, build = preflight(adb, package, args.forzar)
    if not args.prueba and not args.forzar:
        # Antes de compilar y de tocar nada: medir una fase con un build depurable cuando lo demás se midió (o se va a
        # medir) con el de medición hace perder la fase entera.
        stop = debuggable_stop(folder, phase, flow_name, build, plan, args.rehacer)
        if stop:
            raise Precondicion(stop).con(
                seguir=[("instala el build de medición", install_command(plan, project_root(folder).resolve())),
                        ("y repite la medición", same_command())])
    environment = device_environment(adb)
    warnings += environment_warnings(environment)
    # Antes de la traza y de compilar: las opciones de desarrollador que cambian lo que se mide quedan en fases.json.
    dev_settings = read_dev_settings(adb)
    if dev_settings_text(dev_settings):
        fix, back = dev_settings_commands(dev_settings, serial, project_root(folder).resolve())
        print("⚠ Opciones de desarrollador fuera de lo normal: %s. %s" % (dev_settings_text(dev_settings), DEV_SETTINGS_WHY))
        print("    Dejarlas normales:            %s" % fix)
        print("    Volverlas a como estaban:     %s" % back)
        if not dev_setting_normal("always_finish_activities", dev_settings.get("always_finish_activities")):
            print("    Además, %s." % ALWAYS_FINISH_NOTE)
        save_dev_restore(folder, dev_settings, back)
    commit, dirty = git_info()
    build_warnings = []
    if not args.prueba:
        try:
            build_warnings = check_build(folder, phase, build, commit, args.forzar, flow_name, args.rehacer)
        except Precondicion as error:
            raise error.con(seguir=[("instala el build con la mejora", install_command(plan, project_root(folder).resolve())),
                                    ("y repite la medición", same_command())])
    for text in warnings + build_warnings:
        print("⚠ " + text)
    folder.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(str(folder)).free / 1e9
    if free_gb < 3:
        print("⚠ quedan %.1f GB libres: cada traza puede pesar decenas o cientos de MB" % free_gb)
    config_path = resolve_config(plan, folder, args.config)
    used_config = device_sources(config_record(config_path), sdk)
    config = with_trace_cap(config_for_sdk(config_path.read_text(encoding="utf-8"), sdk).replace("{{PAQUETE}}", package),
                            flow.get("duracion_max_s"))
    input_glob = plan.get("input_slices") or INPUT_SLICES
    queries = [("metricas", fill_sql((ASSETS / "queries" / "metricas.sql").read_text(encoding="utf-8"), package,
                                     {"INPUT_GLOB": input_glob}))]
    queries += custom_queries(flow, folder, package)
    out_dir = folder / ("prueba" if args.prueba else phase)
    out_dir.mkdir(parents=True, exist_ok=True)
    known = known_metrics(csv_path, flow_name)
    deobfuscator = Deobfuscator(plan, project_root(folder).resolve(), getattr(args, "mapping", None), build.get("instalada"),
                                adb)
    if sdk < EXIT_MIN_SDK:
        print("· Android %s: sin registro de salidas de la app por corrida (exit-info es de Android 11 o superior). Solo "
              "queda el aviso de crash; un cierre por memoria o un ANR no se detectan aquí." % ("10" if sdk == 29 else sdk))
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

    prepare_shown = []

    def prepare():
        """Deja la app en el punto de partida antes de cada corrida: el comando 'preparar' del plan o, si la app no
        está al frente (la compilación de ART o una corrida anterior la cerraron), la relanza."""
        if startup:
            return
        if prepare_command:
            print("… dejando la app en el punto de partida ('preparar')", flush=True)
            code, tail, log = run_prepare(prepare_command, folder, mask_names, capture=bool(declared))
            if code != 0:
                # Entre paréntesis: un `exit` o un `;` del comando no cierran ni desordenan la terminal de quien lo pega.
                by_hand = "cd %s && ( %s )" % (shlex.quote(os.getcwd()), mask_secrets(prepare_command, mask_names))
                if not prepare_shown:  # una vez por captura: las corridas siguientes fallan igual
                    prepare_shown.append(True)
                    if tail:
                        print("✖ 'preparar' falló (código %d). Sus últimas líneas, con los valores de requiere_env "
                              "enmascarados (más en %s):" % (code, log))
                        print("\n".join("    " + line for line in tail))
                    else:
                        print("✖ 'preparar' falló (código %d) sin dejar salida: si el comando la manda a /dev/null (o el "
                              "flujo no declara requiere_env, y entonces solo se lee su salida de error), córrelo a "
                              "mano en tu terminal para ver el error:" % code)
                        print("    %s" % by_hand)
                # En cada fallo, no solo en el primero: un 'preparar' intermitente puede volver a fallar después de funcionar.
                GUIA["previos"] = [("corre 'preparar' a mano para ver por qué falla (si manda su salida a /dev/null, "
                                    "quítale esa parte para verla)", by_hand)]
                failure = Precondicion("'preparar' terminó con código %d: no dejó la app en el punto de partida (un "
                                       "login que no entró, una pantalla que no cargó a tiempo o el backend caído)" % code)
                failure.corto = "'preparar' terminó con código %d" % code
                raise failure
            GUIA["previos"] = []  # este 'preparar' funcionó: un corte posterior ya no pide correrlo a mano
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
    if args.prueba and not args.sin_compilar and not getattr(args, "compilar", False):
        # La corrida de prueba valida marcas y red: sus números no se guardan ni se comparan, así que no compila.
        compilation = "sin fijar (corrida de prueba)"
        print("· Corrida de prueba: no fija la compilación de ART (sus números no se guardan ni se comparan); con "
              "--compilar se fija igual que en una fase")
    elif not args.sin_compilar:
        compilation = fix_compilation(adb, package, args.compilacion or plan.get("compilacion", "completa"), folder, build,
                                      force=getattr(args, "recompilar", False))
        if prepare_command:
            # Fijar la compilación deja la app detenida: un respiro antes del primer 'preparar' (el del calentamiento
            # o, con --calentamiento 0, el de la primera corrida). Fuera de toda traza.
            settle(WARMUP_SETTLE_S)
    if args.rehacer and not args.prueba:
        had_runs = measured_runs(folder, read_phases(folder) if isinstance(read_phases(folder), dict) else {}, phase,
                                 flow_name)
        discard_phase(folder, csv_path, phase, flow_name)
        forget_notes(folder, phase, flow_name)
        progress["descartada"] = bool(had_runs)
        guide()
        known = known_metrics(csv_path, flow_name)
    # x + Enter corta la corrida en curso: solo con un recorrido que es un comando y una terminal interactiva.
    cutter = RunCutter.abrir() if not startup and recorrido != "manual" else None
    if cutter is not None:
        print(CUT_HINT)
    warmups = 0 if args.prueba else args.calentamiento
    for i in range(warmups):
        if recorrido != "manual":
            print("… calentamiento %d de %d (no cuenta)" % (i + 1, warmups), flush=True)
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
                print("⚠ calentamiento: %s" % getattr(error, "corto", error))
                continue
            reason = drive(recorrido, "calentamiento %d/%d (no cuenta)" % (i + 1, warmups), cutter)
            # Entre dos corridas pasan varios segundos (cerrar la traza, descargarla, procesarla) antes del 'preparar'
            # siguiente; después del calentamiento no pasaba ninguno, y el primer 'preparar' medido encontraba la app
            # todavía terminando el recorrido. Va fuera de toda traza: no cambia lo que se mide.
            settle(WARMUP_SETTLE_S)
        if reason:
            print("⚠ calentamiento: %s" % reason)

    valid, attempts, run_hz = 0, 0, []
    consecutive, last_invalid = 0, ""
    n = next_run_number(csv_path, phase, flow_name) if not args.prueba else 1
    if not args.prueba:
        save_capture_warnings(folder, phase, flow_name, warnings + build_warnings)

    def save_record(partial=False):
        """El registro de la fase en fases.json con las corridas válidas de esta tanda. También cuando la tanda se
        corta (Ctrl+C, inválidas seguidas): lo que ya está en el CSV queda con su build, su commit y su configuración."""
        seen_hz = {h for h in run_hz if h}
        record = {"fecha": datetime.datetime.now().replace(microsecond=0).isoformat(), "commit": commit, "sucio": dirty,
                  "corridas": valid, "hz": hz or min(seen_hz, default=None), "compilacion": compilation, "skill": VERSION,
                  "configs": [config_label(used_config)]}
        if seen_hz:
            record["hz_corridas"] = run_hz
        rate_warning = hz_warning(hz, seen_hz)
        if rate_warning:
            record["avisos"] = [rate_warning]
            print("⚠ " + rate_warning)
        if environment["emulador"] or environment["software"]:
            record["entorno"] = environment
        if dev_settings:
            record["ajustes"] = dev_settings
        record.update(build)
        if partial:  # la tanda se cortó: `siguiente` ofrece completar la fase antes de darla por medida
            record["faltan"] = {flow_name: target - valid}
        write_phase(folder, phase, record, flow_name)

    def mark_invalid(reason):
        if not args.prueba:
            count_invalid(folder, phase, flow_name, reason)

    def on_failure():
        if valid and not args.prueba:
            save_record(partial=True)

    GUIA["al_fallar"] = on_failure  # lo llama main() si la tanda se corta: las válidas no quedan sin su registro
    while valid < target:
        if consecutive >= MAX_CONSECUTIVE_INVALID:
            raise CorridasInsuficientes("%d corridas inválidas seguidas (última: %s): algo del entorno falla, no la "
                                        "suerte. Revisa el recorrido, 'preparar' o el backend y vuelve a correr; las "
                                        "%d válidas quedan guardadas" % (consecutive, last_invalid, valid))
        if attempts >= max_attempts(target):
            raise CorridasInsuficientes("solo %d de %d corridas válidas en %d intentos: revisa las condiciones (el "
                                        "recorrido, 'preparar', el backend); los motivos de cada corrida inválida están "
                                        "más arriba" % (valid, target, attempts))
        attempts += 1
        try:
            prepare()
        except Precondicion as error:
            if not prepare_command or args.prueba:
                if args.prueba and args.plan and prepare_command and hasattr(error, "corto"):
                    save_test_warnings(folder, flow_name, [warning(
                        "preparar", "la corrida de prueba no empezó: %s" % error,
                        "'preparar' falla: corrige el comando o el flow que deja la app en el punto de partida")])
                raise
            # 'preparar' falló (un login que no entró, un backend caído): la corrida no vale, se repite y cuenta
            # para el tope de inválidas seguidas.
            consecutive, last_invalid = consecutive + 1, getattr(error, "corto", str(error))
            mark_invalid(last_invalid)
            print("✖ corrida %d inválida: %s (se repite)" % (n, last_invalid))
            n += 1
            continue
        if sdk < 31:
            adb.shell("dumpsys gfxinfo %s reset" % package)
        local = out_dir / ("%s_%d.perfetto-trace" % (flow_name, n))
        if not args.prueba:
            set_aside_orphan(folder, out_dir, phase, flow_name, n, csv_path)
        label = "prueba" if args.prueba else "corrida %d de %d (%s, %s)" % (valid + 1, target, flow_name, phase)
        # Foto de las salidas de la app (exit-info) antes y después de la corrida, fuera de la traza: una salida nueva
        # del proceso medido dentro de la corrida la invalida.
        exits_before = exit_snapshot(adb, package) if sdk >= EXIT_MIN_SDK else None
        reason, extra = record_run(adb, config, recorrido, label, local, startup, package, cutter)
        if reason == CUT_REASON:
            if args.prueba:
                raise CorridasInsuficientes("la corrida de prueba se cortó a mano (x + Enter): su traza se descartó sin "
                                            "procesarla")
            print("✖ corrida %d inválida: %s (x + Enter): su traza se descartó sin procesarla; se repite" % (n, CUT_REASON))
            mark_invalid(CUT_REASON)
            consecutive, last_invalid = consecutive + 1, CUT_REASON
            n += 1
            continue
        save_trace_config(out_dir, local.name, used_config, build.get("instalada"))
        metrics, invalid, info, crash = [], reason, {}, []
        died = not invalid and app_died(adb, package)
        if died:
            invalid = "la app no estaba viva al terminar la corrida (¿se cayó?)"
            crash = crash_excerpt(adb, package)
        exits = []
        if exits_before is not None:
            # En un arranque en frío el proceso nace en la corrida (no se sabe su pid antes) y el que había lo detiene
            # la propia skill: ese pid se ignora. En los demás flujos, cuenta solo el proceso que estaba al empezar.
            old_pid = exits_before[1]
            exits = run_exits(exits_before, exit_snapshot(adb, package), None if startup else old_pid,
                              (old_pid,) if startup and old_pid else (), package)
        unexpected = [entry for entry in exits if entry["motivo"] not in EXIT_DELIBERATE]
        if unexpected:
            if not invalid or died:
                invalid = "la app salió: %s" % exit_text(unexpected[0])
            if not crash and unexpected[0]["motivo"] == 4:
                crash = crash_block(adb.shell("logcat -b crash -d -t 400").stdout.splitlines(), pid=unexpected[0]["pid"])
        if args.prueba:
            for entry in exits:
                print("%s Salida de la app durante la corrida (%s, pid %s): %s" % (
                    "✖" if entry in unexpected else "·", entry["hora"][11:19], entry["pid"], exit_text(entry)))
        if not invalid:
            print("… procesando la traza %s (%.0f MB)" % (
                "de prueba" if args.prueba else "%d de %d" % (valid + 1, target), local.stat().st_size / 1e6), flush=True)
            results = run_tp_batch(tp, local, queries)
            if not results["metricas"]:
                raise PerfError("trace_processor no devolvió las filas de metricas.sql")
            metrics, invalid, info = trace_metrics(trace_rows(*results["metricas"][-1]), hz, flow, known, sdk)
            if info.get("cruzan_pausa"):
                # No es una corrida mala: es el plan el que mide tiempo de una persona. Repetir no lo arregla.
                raise PerfError("el plan mide tiempo humano: %s. Lo que pasa entre las dos marcas de una pausa no es de la "
                                "app: termina esa medición en la marca donde empieza la pausa o empiézala donde termina, "
                                "y vuelve a correr (traza en %s)" % ("; ".join(info["cruzan_pausa"]), local))
            if not invalid and not args.prueba:
                # Sin la ventana o sin una métrica principal, el recorrido no llegó a donde debía (un tap que no
                # navegó, la pantalla que no cargó a tiempo): la corrida no vale y se repite.
                principales = plan.get("principales") or []
                measured = {m[0] for m in metrics}
                absent = [m for m in segment_metric_names(flow) if m in principales and m not in measured]
                absent_network = [m for m in segment_network_names(flow) if m in principales and m not in measured]
                unmarked = [m for m in absent + absent_network
                            if "tramo %s" % m.rsplit(" ", 1)[0] in info.get("faltantes", [])]
                absent = [m for m in absent if m not in unmarked]
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
            print("\n".join("  " + line for line in deobfuscator.stack(crash)))
            if deobfuscator.mapping is None:
                print("  " + mapping_hint())
        if invalid and args.prueba:
            if not info:  # el recorrido se cortó (o la app se cayó): la traza igual dice hasta dónde llegó
                info = partial_info(tp, local, queries, hz, flow, known, sdk)
            print("Secciones propias: %s" % sections_summary(info.get("nombres", {})))
            if info:
                print("\n".join(marks_report(info)))
            if args.plan:
                unseen = [mark for mark, _, seen in info.get("marcas_plan") or [] if not seen]
                save_test_warnings(folder, flow_name, [warning(
                    "invalida", "la corrida de prueba fue inválida: %s%s" % (
                        invalid, " (marcas del plan que no salieron: %s)" % ", ".join(unseen) if unseen else ""),
                    "la corrida de prueba fue inválida (%s): corrige el recorrido, 'preparar' o las marcas del plan"
                    % invalid, [place for mark in unseen for place in find_mark_sources(project_root(folder).resolve(), mark)])])
            raise CorridasInsuficientes("la corrida de prueba fue inválida: %s (traza en %s)" % (invalid, local))
        if invalid:
            if not info:  # el recorrido terminó mal (o la app se cayó): la traza igual dice hasta dónde llegó
                info = partial_info(tp, local, queries, hz, flow, known, sdk)
            reached = reach_text(info)
            target_name = local.with_name("%s_%d_invalida_%s.perfetto-trace" % (flow_name, n, slug(invalid)))
            local.rename(target_name)
            if not args.sin_comprimir:
                compress(target_name)
            print("✖ corrida %d inválida: %s (traza guardada para auditoría)" % (n, invalid))
            print("  Hasta dónde llegó: %s" % reached)
            mark_invalid(invalid)
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
            print("\n".join(marks_report(info)))
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
            root = project_root(folder).resolve()
            gap, unwired = ("", []) if getattr(args, "sin_red", False) else network_gap(root, plan, flow, info["nombres"],
                                                                                        detail=True)
            if gap and not getattr(args, "red_obligatoria", False):
                print("⚠ " + gap)
            cut = at_limit(info["nombres"])
            if cut:
                print("⚠ %d nombres de sección llegan al límite de %d caracteres de android.os.Trace y están cortados (por "
                      "ejemplo '…%s'): dos endpoints con el mismo comienzo pueden contar como uno. Actualiza la "
                      "instrumentación entre investigaciones (perf.py instrumentar --actualizar): HttpSectionName acorta "
                      "desde la izquierda y conserva el final de la ruta (setup.md · Nombres de endpoint largos)"
                      % (len(cut), SECTION_NAME_MAX, cut[0][-40:]))
            args.resultado = {"http": info.get("http", 0), "sin_red": bool(gap)}  # lo lee humo
            if args.plan:
                seen = info.get("http", 0) > 0
                if seen or gap:  # una prueba que ve la red, o que la esperaba y no la vio, deja el estado al día
                    agents = read_agents(root)
                    section = performance_section(agents) if agents is not None else None
                    current = agents_state(agents[section[0]:section[1]]).get("secciones HTTP") if section else None
                    state = http_state(current, seen, "corrida de prueba")
                    note = update_agents_state(root, http=state) if state else ""
                    if note:
                        print(note)
                pending = test_run_warnings(root, hz, info, gap, unwired, settings=dev_settings, serial=serial)
                save_test_warnings(folder, flow_name, pending)
                if pending:
                    print("⚠ %d avisos por corregir antes de medir: quedan en %s y `siguiente` los lista con el texto para "
                          "un chat; una corrida de prueba sin avisos los da por resueltos" % (len(pending), folder / NOTES_FILE))
            print("Traza: %s" % saved)
            if gap and getattr(args, "red_obligatoria", False):
                raise Precondicion(gap + " Si el arranque de esta app no hace ninguna llamada de red, repite con --sin-red.")
            if args.plan:
                print_next(folder, plan, flow_name)
            return
        append_rows(csv_path, [metric_row(phase, flow_name, n, m[0], m[1], m[2], m[3]) for m in metrics])
        save_timeline(out_dir, flow_name, n, info.get("linea"))
        known |= {m[0] for m in metrics}
        print(run_line("%d/%d" % (valid + 1, target), size_mb, metrics))
        if info.get("faltantes"):
            print("  ⚠ sin marcas para: %s" % ", ".join(info["faltantes"]))
        run_hz.append(info.get("hz_traza"))
        valid += 1
        n += 1
        progress["validas"] = valid
        guide()
    GUIA["al_fallar"] = None
    save_record()
    GUIA.update(guardado="las %d corridas válidas de %s en %s y su registro en fases.json" % (valid, phase, csv_path),
                seguir=[("pide el paso siguiente", "cd %s && python3 -I %s siguiente --carpeta %s"
                         % (shlex.quote(os.getcwd()), shlex.quote(str(HERE / "perf.py")), shlex.quote(str(folder))))])
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


# ── desofuscación (R8) ───────────────────────────────────────────────────────

RETRACE_INSTALL = ("instala las Command-line Tools del SDK de Android (Android Studio · SDK Manager · SDK Tools · \"Android SDK "
                   "Command-line Tools\", o `sdkmanager \"cmdline-tools;latest\"`): traen `retrace` en "
                   "<sdk>/cmdline-tools/latest/bin. Necesita Java. Si está en otra ruta, pásala con RETRACE=<ruta>")
MAPPING_ID = re.compile(r"^#[ \t]*pg_map_id:[ \t]*(\S+)", re.M)
MAPPING_CLASS = re.compile(r"^[^\s#][^\n]* -> [^\s:]+:[ \t]*$", re.M)
APK_MAP_ID = re.compile(br'"pg-map-id":"([^"]+)"')  # el marcador que R8 deja en cada classes.dex: ~~R8{...,"pg-map-id":"<id>",...}
INSTALL_TASK = re.compile(r"(?:^|[\s:])((?:[\w.-]+:)*)install([A-Z]\w*)")
JAVA_NAME = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$<][\w$<>]*)+")
# Un nombre `paquete.Clase.método` parece ofuscado si su clase tiene 1 o 2 caracteres o empieza con minúscula (a.b.c,
# com.example.app.data.a.b, o.aB.d): R8 puede conservar los paquetes y renombrar solo la clase y el método.
OBFUSCATED_NAME = re.compile(r"(?:[\w$]+\.)*(?:[a-z_$][\w$]*|[A-Za-z_$][\w$]?)\.[A-Za-z_$<][\w$<>]*")
STACK_FRAME = re.compile(r"\bat[ \t]+([\w$.<>]+)\(")
RETRACED = re.compile(r"^\s*(<OR>\s+)?at\s+(.+?)\(")
CLOCK_MARGIN_S = 120  # el reloj del dispositivo y el de la máquina no van al segundo
ENCRYPTED_HINT = ("la app puede usar cifrado de clases u otro ofuscador (ofuscadores comerciales con cifrado de clases), que "
                  "este mapping no deshace: mide con una variante sin cifrado de clases")


def find_retrace():
    """La ruta de `retrace` (cmdline-tools del SDK), o None."""
    candidates = [os.environ.get("RETRACE"), shutil.which("retrace")]
    homes = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    adb = shutil.which("adb")
    if adb:
        homes.append(str(pathlib.Path(adb).resolve().parent.parent))
    for home in homes:
        if home:
            candidates += [str(path) for path in sorted(pathlib.Path(home).glob("cmdline-tools/*/bin/retrace"), reverse=True)]
    for candidate in candidates:
        if candidate and (shutil.which(candidate) or pathlib.Path(candidate).is_file()):
            return candidate
    return None


def read_mapping(path):
    """{"ruta", "id" (pg_map_id de la cabecera, o None), "valido" (tiene líneas de clase de ProGuard/R8), "mtime"}."""
    path = pathlib.Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        head = f.read(2_000_000)
    found = MAPPING_ID.search(head[:20_000])
    return {"ruta": path, "id": found.group(1) if found else None, "valido": bool(MAPPING_CLASS.search(head)),
            "mtime": path.stat().st_mtime}


def install_variant(install):
    """(módulo como ruta, variante) de un comando con `:app:installDemoProfiling`: ("app", "demoProfiling"). (None, None)
    si el comando no instala con una tarea install<Variante> de Gradle."""
    found = INSTALL_TASK.search(install or "")
    if not found:
        return None, None
    variant = found.group(2)
    return found.group(1).strip(":").replace(":", "/") or None, variant[0].lower() + variant[1:]


def mapping_candidates(root, variant="*"):
    found = []
    for pattern in ("build/outputs/mapping/%s/mapping.txt", "*/build/outputs/mapping/%s/mapping.txt",
                    "*/*/build/outputs/mapping/%s/mapping.txt"):
        found += sorted(pathlib.Path(root).glob(pattern % variant))
    return found


def locate_mapping(plan, root, override=None):
    """(ruta o None, explícito, aviso) del mapping.txt de la variante medida. Con R8 hay uno por variante, en el módulo
    de la app. Orden: --mapping; `mapping` de plan.json; la variante del comando `instalar` del plan; y, si en el
    proyecto hay un solo mapping que no sea de debug ni de release, ese."""
    root = pathlib.Path(root)
    if override:
        path = pathlib.Path(override)
        if not path.is_file():
            raise PerfError("no existe el mapping %s" % path)
        return path, True, ""
    if plan.get("mapping"):
        path = pathlib.Path(plan["mapping"])
        path = path if path.is_absolute() else root / path
        if path.is_file():
            return path, False, ""
        return None, False, "el 'mapping' de plan.json (%s) no existe: ¿falta compilar esa variante?" % plan["mapping"]
    module, variant = install_variant(plan.get("instalar"))
    if variant:
        found = [root / module / "build" / "outputs" / "mapping" / variant / "mapping.txt"] if module else \
            mapping_candidates(root, variant)
        found = [path for path in found if path.is_file()]
        if len(found) == 1:
            return found[0], False, ""
        if not found:
            return None, False, ("no encontré el mapping de la variante %s (la del comando 'instalar' del plan): ¿la variante "
                                 "usa R8 (minifyEnabled)? Si está en otra ruta, ponla en \"mapping\" de plan.json o pásala "
                                 "con --mapping" % variant)
    else:
        found = [path for path in mapping_candidates(root) if path.parent.name not in ("release", "debug")]
        if len(found) == 1:
            return found[0], False, ""
        if not found:
            return None, False, ("no encontré ningún mapping.txt (<módulo>/build/outputs/mapping/<variante>/): indica el de "
                                 "la variante medida en \"mapping\" de plan.json o con --mapping")
    return None, False, ("hay %d mappings (%s) y no sé cuál es el de la variante medida: indícalo en \"mapping\" de "
                         "plan.json o con --mapping" % (len(found), ", ".join(str(path.parent.name) for path in found[:4])))


def apk_map_ids(apk):
    """Los pg_map_id que R8 dejó en los classes*.dex de un APK. Vacío si el APK no los trae (sin R8, u otro ofuscador)."""
    ids = set()
    with zipfile.ZipFile(str(apk)) as archive:
        for name in archive.namelist():
            if re.fullmatch(r"classes\d*\.dex", name):
                ids |= {found.decode("ascii", "replace") for found in APK_MAP_ID.findall(archive.read(name))}
    return ids


def installed_map_ids(adb, package):
    """Los pg_map_id del APK instalado (baja base.apk a una carpeta temporal y la borra). None si no se pudo leer."""
    paths = re.findall(r"^package:(\S+)", adb.shell("pm path %s" % package).stdout, re.M)
    base = next((path for path in paths if path.endswith("base.apk")), paths[0] if paths else None)
    if not base:
        return None
    work = tempfile.mkdtemp(prefix="hbperf-apk-")
    try:
        local = pathlib.Path(work) / "base.apk"
        pulled = adb.run("pull", base, str(local), timeout=600)
        if pulled.returncode != 0 or not local.is_file():
            return None
        return apk_map_ids(local)
    except (OSError, zipfile.BadZipFile, subprocess.SubprocessError):
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def parse_installed(text):
    try:
        return datetime.datetime.strptime(text or "", "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def output_apk_mtime(mapping_path):
    """La fecha del APK de salida de la variante del mapping (<módulo>/build/outputs/apk/**/<variante>/*.apk), o None."""
    mapping_path = pathlib.Path(mapping_path)
    variant, outputs = mapping_path.parent.name, mapping_path.parent.parent.parent
    apks = [path for path in (outputs / "apk").glob("**/*.apk")
            if "".join(path.relative_to(outputs / "apk").parts[:-1]).lower() == variant.lower()] \
        if (outputs / "apk").is_dir() else []
    return max((path.stat().st_mtime for path in apks), default=None)


def verify_mapping(mapping, installed, explicit, apk_ids=None):
    """(se usa, nota). Un mapping de otro build da nombres equivocados sin ningún error, así que solo se usa si
    corresponde al APK medido:

    - con el pg_map_id del mapping y los del APK instalado, se comparan: si no coinciden, no se usa nunca;
    - sin esos identificadores, por fechas y de forma conservadora: el mapping (y el APK de salida de su variante) no
      pueden ser posteriores a la instalación de la app, ni el mapping posterior a ese APK;
    - si no se puede verificar, no se usa, salvo que se haya pasado con --mapping.
    """
    if mapping["id"] and apk_ids:
        if mapping["id"] in apk_ids:
            return True, "verificado: su pg_map_id (%s) es el del APK instalado" % mapping["id"]
        return False, ("el mapping no es el del APK instalado (pg_map_id %s; el APK tiene %s): daría nombres equivocados. "
                       "Compila e instala de nuevo esa variante, o indica el mapping correcto"
                       % (mapping["id"], ", ".join(sorted(apk_ids))))
    if explicit:
        return True, "sin verificar contra el APK instalado: se usa porque lo pasaste con --mapping"
    moment = parse_installed(installed)
    if moment is None:
        return False, ("no se pudo verificar que el mapping corresponda al APK medido (sin pg_map_id comparable ni fecha de "
                       "instalación): no se desofusca. Si estás seguro de que es el de ese build, pásalo con --mapping")
    if mapping["mtime"] > moment + CLOCK_MARGIN_S:
        return False, ("el mapping se generó después de instalar la app (instalada %s): es de otro build y daría nombres "
                       "equivocados. Instala de nuevo esa variante, o pasa con --mapping el del build medido" % installed)
    apk = output_apk_mtime(mapping["ruta"])
    if apk is not None and (apk > moment + CLOCK_MARGIN_S or mapping["mtime"] > apk + CLOCK_MARGIN_S):
        return False, ("el APK de salida de esa variante no corresponde con la instalación (instalada %s) o con el mapping: "
                       "puede ser de otro build. Instala de nuevo esa variante, o pasa con --mapping el del build medido"
                       % installed)
    return True, ("verificado solo por fecha (el mapping%s no es posterior a la instalación, %s): sin pg_map_id comparable"
                  % (" y el APK de salida" if apk is not None else "", installed))


class Deobfuscator:
    """Desofusca con `retrace` y el mapping de la variante medida, solo cuando hace falta: lo que tarda (ubicar el
    mapping, verificarlo contra el APK) se hace la primera vez que aparece un nombre ofuscado. Nunca falla por no tener
    mapping ni `retrace`: lo dice una vez y deja los nombres como están."""

    def __init__(self, plan, root, override=None, installed=None, adb=None):
        self.plan, self.root, self.override, self.installed, self.adb = plan or {}, root, override, installed, adb
        if override and not pathlib.Path(override).is_file():
            raise PerfError("no existe el mapping %s" % override)  # al empezar el comando, no a mitad de una captura
        self.ready, self.retrace, self.mapping, self.notes = False, None, None, []

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)
            print(text)

    def prepare(self):
        if self.ready:
            return self.mapping is not None
        self.ready = True
        path, explicit, warning = locate_mapping(self.plan, self.root, self.override)
        if path is None:
            self.note("· Sin desofuscar: %s." % warning)
            return False
        mapping = read_mapping(path)
        if not mapping["valido"]:
            self.note("⚠ Sin desofuscar: %s no tiene el formato de un mapping de ProGuard/R8 (¿lo generó otro ofuscador?); %s."
                      % (path, ENCRYPTED_HINT))
            return False
        adb = self.adb() if callable(self.adb) else self.adb
        ids = installed_map_ids(adb, self.plan.get("paquete")) if adb and mapping["id"] and self.plan.get("paquete") else None
        use, detail = verify_mapping(mapping, self.installed, explicit, ids)
        if not use:
            self.note("⚠ Sin desofuscar: %s." % detail)
            return False
        self.retrace = find_retrace()
        if not self.retrace:
            self.note("· Sin desofuscar: falta `retrace`; %s." % RETRACE_INSTALL)
            return False
        self.mapping = mapping
        try:  # relativa a la raíz: esta nota también queda en diagnostico.md
            shown = pathlib.Path(path).resolve().relative_to(pathlib.Path(self.root).resolve())
        except ValueError:
            shown = path
        self.note("✔ Desofuscado con %s (%s)." % (shown, detail))
        return True

    def run(self, lines):
        """Las líneas pasadas por retrace, o None si falló."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            source = f.name
        try:
            result = subprocess.run([self.retrace, str(self.mapping["ruta"]), source], capture_output=True, text=True,
                                    timeout=300)
        except (OSError, subprocess.SubprocessError) as error:
            self.note("⚠ Sin desofuscar: retrace no corrió (%s)." % str(error)[:120])
            return None
        finally:
            os.unlink(source)
        if result.returncode != 0:
            self.note("⚠ Sin desofuscar: retrace falló (%s)." % ((result.stderr or result.stdout).strip().splitlines() or ["sin salida"])[-1][:160])
            return None
        return result.stdout.splitlines()

    def stack(self, lines):
        """Una pila (logcat, una traza de salida) con los nombres reales. Sin frames ofuscados, o sin mapping, igual."""
        if not any(OBFUSCATED_NAME.fullmatch(name) for line in lines for name in STACK_FRAME.findall(line)):
            return lines
        if not self.prepare():
            return lines
        out = self.run(lines)
        if out is None:
            return lines
        self.leftover([name for line in out for name in STACK_FRAME.findall(line)])
        return out

    def names(self, names):
        """{nombre ofuscado: nombre real} para nombres `clase.método` sueltos (sin número de línea, retrace puede
        devolver varios candidatos: van separados por ' o ')."""
        if not any(OBFUSCATED_NAME.fullmatch(name or "") for name in names) or not self.prepare():
            return {}
        # Con un nombre que parece ofuscado ya vale la pena: van todos los que tienen forma de `clase.método`, porque
        # una clase ofuscada también puede llamarse Ab0 o ABc.
        wanted = sorted({name for name in names if JAVA_NAME.fullmatch(name or "")})
        out = self.run(["\tat %s(Unknown Source)" % name for name in wanted])
        if out is None:
            return {}
        groups = []
        for line in out:
            found = RETRACED.match(line)
            if not found:
                continue
            if found.group(1) and groups:
                groups[-1].append(found.group(2))
            else:
                groups.append([found.group(2)])
        if len(groups) != len(wanted):  # la salida no tiene la forma esperada: mejor sin tocar que con nombres corridos
            self.note("⚠ Sin desofuscar: la salida de retrace no se pudo emparejar con los nombres.")
            return {}
        mapped = {}
        for name, options in zip(wanted, groups):
            unique = [option for i, option in enumerate(options) if option not in options[:i]]
            mapped[name] = " o ".join(unique[:3]) + (" o …" if len(unique) > 3 else "")
        self.leftover([value for name, value in mapped.items() if value == name])
        return {name: value for name, value in mapped.items() if value != name}

    def leftover(self, names):
        still = sorted({name for name in names if OBFUSCATED_NAME.fullmatch(name)})
        if still:
            self.note("⚠ %d nombre%s ofuscado%s después de aplicar el mapping (%s): el mapping no los trae; %s."
                      % (len(still), " sigue" if len(still) == 1 else "s siguen", "" if len(still) == 1 else "s",
                         ", ".join(still[:3]) + ("…" if len(still) > 3 else ""), ENCRYPTED_HINT))


def query_deobfuscate(sql):
    """Las columnas con nombres de métodos que una consulta declara en su cabecera (`-- desofuscar: funcion`)."""
    for line in sql.splitlines():
        if line.startswith("-- desofuscar:"):
            return line.split(":", 1)[1].split()
    return []


def deobfuscate_sets(sets, columns, deobfuscator):
    """Los resultados de una consulta con las columnas de nombres de métodos desofuscadas. Avisa también del código
    nativo sin símbolos, que se muestra como librería."""
    if not columns or deobfuscator is None:
        return sets
    out, native = [], False
    for header, body in sets:
        indexes = [i for i, name in enumerate(header) if name in columns]
        library = header.index("libreria") if "libreria" in header else None

        def managed(row):  # el código nativo y el del kernel no pasan por el mapping de R8
            origin = str(row[library]) if library is not None and library < len(row) else ""
            return ".so" not in origin and not origin.startswith("[kernel")

        names = deobfuscator.names([row[i] for row in body if managed(row) for i in indexes if i < len(row)]) \
            if indexes else {}
        native = native or any(i < len(row) and row[i] in ("?", "") and library is not None and library < len(row)
                               and ".so" in str(row[library]) for row in body for i in indexes)
        out.append((header, [[names.get(cell, cell) if i in indexes and managed(row) else cell
                              for i, cell in enumerate(row)] for row in body] if names else body))
    if native:
        deobfuscator.note("· Código nativo sin símbolos: se muestra la librería, no la función (hacen falta los símbolos de "
                          "esa librería; el mapping de R8 no los trae).")
    return out


# ── salidas de la app (ApplicationExitInfo) ──────────────────────────────────

EXIT_REASONS = {0: "desconocido", 1: "la app terminó sola (exit)", 2: "señal del sistema operativo",
                3: "poca memoria (la cerró el sistema)", 4: "crash", 5: "crash nativo", 6: "ANR",
                7: "falló al iniciar", 8: "cambio de permisos", 9: "uso excesivo de recursos",
                10: "detenida a pedido del usuario (o force-stop)", 11: "usuario del dispositivo detenido",
                12: "murió un proceso del que dependía", 13: "detenida por el sistema", 14: "detenida por el freezer",
                15: "cambio de estado del paquete", 16: "paquete actualizado"}
# Cierres que pide alguien (un force-stop del recorrido o de la propia skill, una reinstalación): no son fallas de la app.
EXIT_DELIBERATE = (8, 10, 11, 15, 16)
EXIT_KEYS = ("timestamp", "pid", "realUid", "packageUid", "definingUid", "user", "process", "reason", "subreason",
             "status", "importance", "pss", "rss", "description", "state", "trace")
EXIT_ENTRY = re.compile(r"ApplicationExitInfo #\d+:")
EXIT_END = re.compile(r"^\s*(?:package:|Historical Process Exit|ACTIVITY MANAGER|Last Timestamp)", re.M)
EXIT_MIN_SDK = 30


def parse_exit_info(text):
    """Las salidas de `dumpsys activity exit-info <paquete>` (Android 11+), de la más reciente a la más vieja. Cada una:
    hora ('AAAA-MM-DD HH:MM:SS.mmm', hora del dispositivo), proceso, pid, motivo (código), motivo_texto, submotivo, estado,
    importancia, pss, rss, descripcion y traza. Tolerante a las diferencias entre versiones: un campo que no está queda
    vacío (None en pid y motivo), y los que no conoce se ignoran."""
    entries = []
    for block in EXIT_ENTRY.split(text or "")[1:]:
        end = EXIT_END.search(block)
        body = " ".join((block[:end.start()] if end else block).split())
        marks = []
        for key in EXIT_KEYS:
            # 'state' y 'trace' van después de la descripción, que es texto libre: se toma la última vez que salen
            found = list(re.finditer(r"(?:^|\s)%s=" % key, body))
            if found:
                marks.append((found[-1] if key in ("state", "trace") else found[0], key))
        marks.sort(key=lambda item: item[0].start())
        values = {}
        for index, (found, key) in enumerate(marks):
            stop = marks[index + 1][0].start() if index + 1 < len(marks) else len(body)
            values.setdefault(key, body[found.end():stop].strip())
        code = re.match(r"\d+", values.get("reason", ""))
        code = int(code.group(0)) if code else None
        sub = re.match(r"\d+\s*\((.*)\)\s*$", values.get("subreason", ""))
        pid = re.match(r"\d+", values.get("pid", ""))
        described = values.get("description", "")
        stamp = re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?", values.get("timestamp", ""))
        entries.append({
            "hora": stamp.group(0) if stamp else "", "proceso": values.get("process", ""), "pid": int(pid.group(0)) if pid else None, "motivo": code,
            "motivo_texto": EXIT_REASONS.get(code, "motivo %s" % values.get("reason", "sin dato") if values.get("reason")
                                             else "sin dato"),
            "submotivo": "" if not sub or sub.group(1).upper() == "UNKNOWN" else sub.group(1),
            "estado": values.get("status", ""), "importancia": values.get("importance", ""),
            "pss": values.get("pss", ""), "rss": values.get("rss", ""),
            "descripcion": "" if described == "null" else described,
            "traza": "" if values.get("trace", "null") == "null" else values.get("trace", "")})
    return entries


def exit_text(entry):
    """El motivo de una salida, en una línea."""
    text = entry["motivo_texto"]
    if entry["submotivo"]:
        text += " · %s" % entry["submotivo"].lower()
    if entry["descripcion"]:
        text += " (%s)" % entry["descripcion"][:80]
    return text


def exit_snapshot(adb, package):
    """(hora del dispositivo 'AAAA-MM-DD HH:MM:SS', pid de la app o None, salidas registradas), en una sola llamada a adb.
    La hora sale del mismo reloj y con la misma zona que las de exit-info: se comparan como texto."""
    out = adb.shell("date '+hora=%%Y-%%m-%%d %%H:%%M:%%S'; echo \"pid=$(pidof %s)\"; dumpsys activity exit-info %s"
                    % (package, package)).stdout
    moment = re.search(r"^hora=(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*$", out, re.M)
    pid = re.search(r"^pid=(\d+)", out, re.M)
    return moment.group(1) if moment else "", int(pid.group(1)) if pid else None, parse_exit_info(out)


def run_exits(before, after, measured_pid=None, killed=(), package=None):
    """Las salidas de la app que pasaron dentro de una corrida: las que aparecen en `after` (foto al terminar) y no
    estaban en `before` (foto al empezar), con hora dentro de la ventana y, si se conoce, del pid medido. Deja fuera
    las que provoca la propia skill: los pids de `killed` (el proceso que detiene antes de un arranque en frío) y todo
    lo que está fuera de la ventana (el force-stop de `preparar` y el de la compilación de ART). Con `package`, tampoco
    cuentan los procesos secundarios de la app (`<paquete>:servicio`): el que se mide es el principal."""
    start, _, known = before
    end, _, entries = after
    if not start or not end:
        return []
    seen = {(entry["hora"], entry["pid"]) for entry in known}
    found = []
    for entry in entries:
        moment = entry["hora"][:19]
        if (entry["hora"], entry["pid"]) in seen or not start <= moment <= end or entry["pid"] in killed:
            continue
        if measured_pid is not None and entry["pid"] != measured_pid:
            continue
        if package and entry.get("proceso") and entry["proceso"] != package:
            continue
        found.append(entry)
    return found


def crash_block(lines, package=None, pid=None, size=14):
    """El último bloque FATAL EXCEPTION de logcat -b crash que es de ese pid (o, sin pid, de ese paquete)."""
    starts = [i for i, line in enumerate(lines) if "FATAL EXCEPTION" in line]
    for start in reversed(starts):
        block = lines[start:start + size]
        if pid is not None and any(re.search(r"\bPID: %d\b" % pid, line) for line in block):
            return block
        if pid is None and package and any(package in line for line in block):
            return block
    return []


def cmd_salidas(args):
    plan, folder = {}, None
    if args.carpeta:
        folder = pathlib.Path(args.carpeta)
        plan = load_plan(folder / "plan.json")
    package = args.paquete or plan.get("paquete")
    if not package:
        raise PerfError("indica la app con --paquete (o --carpeta, para tomarla del plan)")
    serial = select_device(args.serial or plan.get("serial"))
    adb = Adb(serial)
    sdk = to_int(adb.shell("getprop ro.build.version.sdk").stdout.strip())
    if sdk < EXIT_MIN_SDK:
        print("Salidas de la app: no disponible (Android 11 o superior; el dispositivo tiene API %d). No quiere decir que "
              "la app no se haya cerrado: en este dispositivo solo queda el aviso de crash de `capturar`." % sdk)
        return
    dump = adb.shell("dumpsys activity exit-info %s" % package).stdout
    entries = parse_exit_info(dump)
    if args.desde:
        entries = [entry for entry in entries if entry["hora"] >= args.desde]
    since = " desde %s" % args.desde if args.desde else ""
    if not entries:
        print("Sin salidas registradas de %s%s. El sistema guarda un historial acotado por paquete y lo borra al "
              "desinstalar: una lista vacía no cubre lo que pasó antes." % (package, since))
        return
    shown = entries[:args.limite]
    print(markdown_table(["Hora", "pid", "Motivo", "Descripción", "PSS", "RSS"],
                         [[entry["hora"], entry["pid"] if entry["pid"] is not None else "—",
                           entry["motivo_texto"] + (" · %s" % entry["submotivo"].lower() if entry["submotivo"] else ""),
                           entry["descripcion"][:60] or "—", entry["pss"] or "—", entry["rss"] or "—"] for entry in shown]))
    if len(entries) > len(shown):
        print("… %d salidas más (sube --limite o acota con --desde)" % (len(entries) - len(shown)))
    print("Hora del dispositivo. Los cierres a pedido (force-stop, reinstalar) también quedan registrados: no son fallas.")
    crashes = [entry for entry in shown if entry["motivo"] == 4 and entry["pid"] is not None]
    if crashes:
        root = project_root(folder if folder is not None else pathlib.Path.cwd()).resolve()
        build = package_build(adb.shell("dumpsys package %s" % package).stdout)
        deobfuscator = Deobfuscator(dict(plan, paquete=package), root, args.mapping, build.get("instalada"), adb)
        lines = adb.shell("logcat -b crash -d -t 2000").stdout.splitlines()
        for entry in crashes[:3]:
            block = crash_block(lines, pid=entry["pid"])
            if block:
                print("Crash de las %s (pid %d), inicio de la pila (logcat -b crash):" % (entry["hora"][11:19], entry["pid"]))
                print("\n".join("  " + line for line in deobfuscator.stack(block)))
            else:
                print("Crash de las %s (pid %d): su pila ya no está en logcat -b crash." % (entry["hora"][11:19], entry["pid"]))
    traced = [entry for entry in shown if entry["traza"]]
    if traced:
        print("Con traza del sistema (ANR o crash nativo): %s. Para leerlas, `anr-audit-and-fix` o `android-profiler`."
              % ", ".join("%s %s" % (entry["hora"][11:19], entry["motivo_texto"]) for entry in traced[:3]))


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


def trace_plan(trace):
    """(raíz del proyecto, plan.json de la investigación de esa traza, o {} si no hay)."""
    for folder in list(pathlib.Path(trace).resolve().parents)[:3]:
        if (folder / "plan.json").is_file():
            try:
                plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
            except ValueError:
                plan = {}
            return project_root(folder).resolve(), plan if isinstance(plan, dict) else {}
    return project_root(pathlib.Path.cwd()).resolve(), {}


def measured_device(plan, installed):
    """El dispositivo, solo si está conectado y todavía tiene instalado el build que se midió (misma fecha de
    instalación): con él se compara el pg_map_id del mapping con el del APK. None si no: se verifica por fechas."""
    package = plan.get("paquete")
    if not package or not installed:
        return None
    try:
        adb = Adb(select_device(plan.get("serial")))
        current = package_build(adb.shell("dumpsys package %s" % package).stdout)
    except (PerfError, OSError, subprocess.SubprocessError):
        return None
    return adb if current.get("instalada") == installed else None


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
    requires = query_requires(sql)
    config = trace_config(args.traza)
    missing = missing_sources(requires, config) if config else []
    if missing:
        capture = configs_with(requires)
        print("✖ %s. No quiere decir que no ocurra: esta traza no lo puede responder.%s" % (
            unmeasured(config, missing), " Captura una corrida con --config %s y consulta esa traza." % " o ".join(capture)
            if capture and not any(source in (config.get("no_disponibles") or {}) for source in missing) else ""))
        return
    sql = fill_sql(sql, args.paquete or package_near(args.traza), parse_params(args.param))
    sets = run_tp(tp, args.traza, sql)
    columns = query_deobfuscate(sql)
    if columns:
        root, near = trace_plan(args.traza)
        sets = deobfuscate_sets(sets, columns, Deobfuscator(
            near, root, args.mapping, (config or {}).get("instalada"),
            lambda: measured_device(near, (config or {}).get("instalada"))))
    print_sets(sets, args.limite, args.ancho)
    if requires and not config:
        print("⚠ %s: no se sabe con qué configuración se grabó esta traza (es de una versión anterior o "
              "se movió de su carpeta), así que %s. La consulta necesita: %s."
              % ("Con configuración desconocida" if any(body for _, body in sets) else "Sin filas, con configuración "
                 "desconocida", "lo que falte puede no haberse medido" if any(body for _, body in sets)
                 else "no se puede afirmar que no ocurra", ", ".join(requires)))
    elif requires and not any(body for _, body in sets):
        print("Medido y sin casos: la configuración %s captura lo que pide la consulta (%s) y no hubo filas. Vale como "
              "ausencia si el dispositivo emite ese dato: si nunca sale nada, comprueba que la traza lo traiga."
              % (config["nombre"], ", ".join(requires)))


DIAG_ORDER = ["arranque_hitos", "linea_hilo_principal", "hilo_principal_top", "estado_hilo_principal",
              "hijos_mas_largos", "dormido_en_frames_largos", "bloqueo_hilo_principal", "estado_primeros_frames", "frames_por_tramo",
              "cpu_por_tramo", "cpu_por_hilo", "contencion_locks", "binder_hilo_principal", "jank_por_tipo",
              "linea_de_tiempo", "llamadas_solapadas", "inflate_tras_http", "cpu_por_libreria"]


# Cuándo vale la pena una captura con --config completa para saber por qué espera el hilo principal: si pasa dormido o
# bloqueado al menos esta parte del tiempo de sus 3 frames más largos, o si tiene ahí una espera en D de al menos estos
# milisegundos (un cuarto del presupuesto de un frame a 60 Hz). Punto de partida, sin calibrar con datos de campo.
BLOCKED_SHARE_MIN = 0.25
BLOCKED_D_MIN_MS = 4.0
BLOCKED_SOURCE = "ftrace:sched/sched_blocked_reason"


def blocked_signal(sets):
    """(parte del tiempo de los frames largos en S o D, espera más larga en D en ms, ms de los frames) a partir del
    resultado de senal_bloqueo.sql; None si no hay frames o la consulta no devolvió su fila."""
    for header, body in sets or []:
        if body and all(name in header for name in ("frames_ms", "espera_ms", "max_d_ms")):
            row = dict(zip(header, body[0]))
            try:
                frames, waiting, longest = float(row["frames_ms"]), float(row["espera_ms"]), float(row["max_d_ms"])
            except (TypeError, ValueError):
                return None
            return (waiting / frames, longest, frames) if frames > 0 else None
    return None


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


def segment_network_table(sets, segments):
    """La tabla "Red por tramo" de una corrida para diagnostico.md, a partir de las filas de metricas.sql. '' si la
    corrida no tiene llamadas o el flujo no tiene tramos."""
    if not sets or not segments:
        return ""
    rows = trace_rows(*sets[-1])
    sections = sorted((r for r in rows if r[0] == "seccion"), key=lambda r: r[1])
    if not any(s[4].startswith("HTTP ") for s in sections):
        return ""
    markers = sorted(sections + [r for r in rows if r[0] in ("hilo", "lanzamiento")], key=lambda r: r[1])
    _, detail, outside = segment_network(markers, sections, segments)

    def names(endpoints):
        items = sorted(endpoints.items(), key=lambda kv: (-kv[1], kv[0]))
        return ", ".join("%s ×%d" % kv if kv[1] > 1 else kv[0] for kv in items[:6]) + (", …" if len(items) > 6 else "") or "—"

    table = [[row["tramo"], row["llamadas"], names(row["endpoints"]), fmt(row["ms"]), fmt(row["ttfb_ms"]), row["repetidas"],
              row["solapadas"]] for row in detail]
    found = {row["tramo"] for row in detail}
    table += [[spec["nombre"], "—", "sin las marcas del tramo en esta corrida", "—", "—", "—", "—"]
              for spec in segments if spec["nombre"] not in found]
    if outside:
        table.append(["(fuera de los tramos)", sum(outside.values()), names(outside), "—", "—", "—", "—"])
    return markdown_table(["Tramo", "Llamadas", "Endpoints", "Duración mediana (ms)", "TTFB mediano (ms)", "Repetidas (2 s)",
                           "Solapadas"], table)


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
    groups = {"base", "cpu", "completa"} | ({"arranque"} if startup else set()) | ({"red"} if network else set())
    wanted = set(args.consultas.split(",")) if args.consultas else None
    params = {"TRAMO_MS": str(args.tramo_ms or (250 if startup else 500))}
    catalog = [q for q in query_catalog() if (q[0] in wanted if wanted else set(q[2]) & groups)]
    unit = next((r["unidad"] for r in rows if r["metrica"] == metric), "")
    md = ["# Diagnóstico · %s · %s" % (flow_name, phase), "",
          "_Corridas: %s. `t_ms` y `desde_ms`: ms desde que nace el proceso (arranque) o desde el inicio de la "
          "traza. Generado por hb-performance %s._" % (", ".join("%s = %s (%s %s)" % (label, run, metric, fmt(value, unit))
                                                                 for label, run, value in runs), VERSION)]
    printed, empty, unknown, not_measured, failed = [], [], [], {}, {}
    installed = (read_phases(folder).get(phase) or {}).get("instalada")
    deobfuscator = Deobfuscator(plan, project_root(folder).resolve(), args.mapping, installed,
                                lambda: measured_device(plan, installed))
    signal_sql = (ASSETS / "queries" / "senal_bloqueo.sql").read_text(encoding="utf-8")
    blocked = None  # (parte, espera más larga en D, ms de los frames, corrida) de la corrida donde más pesa la espera
    segments = flow.get("segmentos") or []
    for index, (label, run, _) in enumerate(runs):
        chosen = [q for q in catalog if index == 0 or "peor" in q[2]]
        if not chosen:
            continue
        trace = trace_of(folder, phase, flow_name, run)
        print("… procesando la traza %d de %d (corrida %s, %s)" % (index + 1, len(runs), run, label), flush=True)
        # Cada consulta declara qué fuentes necesita (`-- requiere:`) y se valida contra la configuración con la que se
        # grabó esta traza: sin la fuente, es "no medido", que no es lo mismo que "sin casos".
        config = trace_config(trace)
        runnable = []
        for q in chosen:
            requires = query_requires(q[3])
            missing = missing_sources(requires, config) if config else []
            if missing and "completa" in q[2] and not wanted:
                pass  # una captura especial: si hace falta, la pide la señal de espera ("Captura pendiente"), más abajo
            elif missing:
                not_measured.setdefault(q[0], unmeasured(config, missing))
            elif not config and set(q[2]) & {"completa"}:
                unknown.append(q[0])  # pide una captura especial y no se sabe si esta traza lo es: no se corre
            else:
                runnable.append(q)
        chosen = runnable
        batch = [(q[0], fill_sql(q[3], plan["paquete"], params)) for q in chosen if "completa" not in q[2]]
        if segments and not wanted:  # la red por tramo sale de las mismas filas que las métricas de la corrida
            batch.append(("metricas", fill_sql((ASSETS / "queries" / "metricas.sql").read_text(encoding="utf-8"),
                                               plan["paquete"], {"INPUT_GLOB": plan.get("input_slices") or INPUT_SLICES})))
        # La señal de espera solo tiene sentido si la traza no trae ya la razón de bloqueo (una captura completa).
        watch = not wanted and not (config and (BLOCKED_SOURCE in config["fuentes"]
                                                or missing_sources(query_requires(signal_sql), config)))
        if watch:
            batch.append(("senal_bloqueo", fill_sql(signal_sql, plan["paquete"], params)))
        results = run_tp_batch(tp, trace, batch) if batch else {}  # trace_processor no acepta un archivo sin consultas
        found = blocked_signal(results.get("senal_bloqueo")) if watch else None
        if found and (found[0] >= BLOCKED_SHARE_MIN or found[1] >= BLOCKED_D_MIN_MS) and (blocked is None or found[0] > blocked[0]):
            blocked = found + (run,)
        for q in chosen:
            if "completa" in q[2]:
                # Aparte: usan columnas que una versión antigua de trace_processor puede no tener, y un error ahí no
                # debe tumbar el resto del diagnóstico.
                try:
                    results.update(run_tp_batch(tp, trace, [(q[0], fill_sql(q[3], plan["paquete"], params))]))
                except PerfError as error:
                    results[q[0]] = []
                    failed.setdefault(q[0], str(error).strip().splitlines()[-1][:160])
        if index:
            md += ["", "## Corrida %s (%s)" % (run, label)]
        network_table = segment_network_table(results.get("metricas") or [], segments)
        if network_table:
            md += ["", "%s Red por tramo: las llamadas que empiezan en cada tramo del plan · `segmentos`"
                   % ("###" if index else "##"), "", network_table,
                   "", "_De esta corrida, sin veredicto estadístico: los valores con veredicto son las métricas "
                       "`<tramo> red_*` de todas las corridas._"]
            printed.append("red por tramo (%s)" % label)
        for name, title, _, sql in chosen:
            sets = deobfuscate_sets([s for s in results[name] if s[1]], query_deobfuscate(sql), deobfuscator)
            if name in failed:
                continue
            if not sets:
                (empty if config else unknown).append(name)
                continue
            md += ["", "%s %s · `%s`" % ("###" if index else "##", title.replace("{{TRAMO_MS}}", params["TRAMO_MS"]),
                                         name), ""]
            for header, body in sets:
                md.append(markdown_table(header, [[fmt_cell(c)[:args.ancho] for c in row] for row in body[:args.limite]]))
            printed.append("%s (%s)" % (name, label))
    if empty:
        md += ["", "_Medido y sin casos (la configuración de la traza captura lo que la consulta necesita y no hubo "
                   "filas): %s._" % ", ".join(sorted(set(empty)))]
    for name in sorted(not_measured):
        md += ["", "_`%s`: %s. No quiere decir que no ocurra._" % (name, not_measured[name])]
    if unknown:
        md += ["", "_Sin tabla, con configuración desconocida (trazas de una versión anterior: no se sabe qué fuentes "
                   "capturaron, así que no se afirma que no ocurra): %s._" % ", ".join(sorted(set(unknown)))]
    for name in sorted(failed):
        md += ["", "_`%s`: no disponible: trace_processor no pudo correr la consulta (%s). Actualiza trace_processor._"
               % (name, failed[name])]
    if "cpu_por_libreria" in set(empty) | set(unknown) | set(not_measured):
        md += ["", "_Sin muestras de CPU: para atribuir el CPU a funciones, captura una corrida con "
                   "`capturar --prueba --config cpu` y consulta `cpu_por_libreria` sobre esa traza._"]
    for note in deobfuscator.notes:
        md += ["", "_%s_" % note.lstrip("·⚠✔ ")]
    if blocked:
        capture = "capturar --plan %s%s --prueba --config completa" % (
            folder / "plan.json", " --flujo %s" % flow_name if len(plan["flujos"]) > 1 else "")
        md += ["", "## Por qué espera el hilo principal: falta una captura", "",
               "En la corrida %s, el hilo principal pasó dormido o bloqueado el %s %% del tiempo de sus 3 frames más largos "
               "(%s ms en total; su espera más larga en D fue de %s ms). Esta traza dice dónde espera "
               "(`dormido_en_frames_largos`), no quién lo bloquea ni quién lo despierta. Captura pendiente: `%s` y, sobre "
               "esa traza, `consulta %s bloqueo_hilo_principal`."
               % (blocked[3], fmt(round(blocked[0] * 100, 1)), fmt(round(blocked[2], 1)), fmt(round(blocked[1], 1)), capture,
                  folder / "prueba" / ("%s_1.perfetto-trace.gz" % flow_name)),
               "", "_Umbral: %d %% o más del tiempo de los frames largos en S o D, o una espera de %s ms o más en D. Es una "
                   "captura de diagnóstico: pesa varias veces más que la base y sus tiempos no se comparan._"
               % (BLOCKED_SHARE_MIN * 100, fmt(BLOCKED_D_MIN_MS))]
    target = folder / ("diagnostico.md" if phase == "antes" else "diagnostico-%s.md" % phase)
    target.write_text("\n".join(md) + "\n", encoding="utf-8")
    if not wanted:  # el diagnóstico entero: lo que no midió va a "Advertencias para el diagnóstico" de estado.md
        gaps = ["`%s`: %s (no quiere decir que no ocurra)" % (name, not_measured[name]) for name in sorted(not_measured)]
        if unknown:
            gaps.append("sin tabla y con configuración desconocida (trazas de una versión anterior: no se afirma que no "
                        "ocurra): %s" % ", ".join(sorted(set(unknown))))
        gaps += ["`%s`: no disponible, trace_processor no pudo correr la consulta" % name for name in sorted(failed)]
        notes = read_notes(folder)
        bucket = note_bucket(notes, "diagnostico", phase)
        if gaps:
            bucket[flow_name] = [one_line(text) for text in gaps]
        else:
            bucket.pop(flow_name, None)
        if not bucket:
            notes["diagnostico"].pop(phase)
        save_notes(folder, notes)
    if blocked:
        print("· El hilo principal espera dentro de sus frames más largos (%s %% del tiempo): %s deja una captura pendiente "
              "con --config completa para saber por qué." % (fmt(round(blocked[0] * 100, 1)), target.name))
    print("✔ %s: %d tablas de %s (%s)." % (target, len(printed), ", ".join("corrida %s" % r[1] for r in runs),
                                          ", ".join(sorted(groups - {"cpu", "completa"}))))
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
    if getattr(args, "solo_imprimir", False):
        print("· --solo-imprimir: no se escribió resumen.md ni la sección Métricas de estado.md")
        return
    write_summary(args.csv, rows, plan)
    print("✔ %s escrito" % pathlib.Path(args.csv).with_name("resumen.md"))


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
    notes += dev_settings_notes(folder)
    level, motive = frames_trust(folder)
    if level != "ok":
        notes.append("las fases se midieron en un entorno con frames %s (%s): %s" % (
            "no confiables" if level == "no" else "orientativos", motive,
            "no uses jank_* ni frame_* para decidir; repite en un dispositivo físico o con -gpu host" if level == "no"
            else "valen los conteos y las fugas; para decidir con frames, usa un dispositivo físico"))
    return table, notes


def logrado_rows(plan, results, readable=False):
    by_metric = {(r["flujo"], r["metrica"]): r for r in results}
    default_flow = next(iter(plan.get("flujos") or {"": None}))
    out = []
    for item in plan.get("mejoras", []):
        r = by_metric.get((item.get("flujo") or default_flow, item.get("metrica")))
        unit = r["unidad"] if r else ""
        show = nice if readable else fmt  # estado.md conserva el formato de siempre; el reporte, el legible
        change = "—" if r is None else (change_pct(r["antes"]["mediana"], r["despues"]["mediana"]) or "—") \
            if readable else fmt_pct(r["delta_pct"])
        out.append([item["id"], improvement_title(item), item.get("metrica", "—"),
                    show(r["antes"]["mediana"], unit) if r else "—", item.get("esperado", "—"),
                    show(r["despues"]["mediana"], unit) if r else "—", change if r else "—",
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


def config_notes(folder, flows):
    """Avisos de `comparar`: las fases de un flujo que no se midieron con la misma configuración de Perfetto. No
    bloquea. Sin el dato en ninguna fase (investigaciones de versiones anteriores) no dice nada."""
    phases = read_phases(folder)
    notes = []
    for flow in flows:
        used = {}
        for phase in FASES:
            record = phases.get(phase)
            if not record:
                continue
            tracked = record.get("flujos") or {}
            if tracked and flow not in tracked:
                continue
            used[phase] = list((tracked.get(flow) or {}).get("configs") or record.get("configs") or [UNKNOWN_CONFIG])
        distinct = {label for labels in used.values() for label in labels}
        if len(used) > 1 and len(distinct) > 1:
            notes.append("%s: las fases no se midieron con la misma configuración de Perfetto (%s): lo que cada una "
                         "captura y su costo pueden diferir, y las métricas no ser comparables. Repite con --rehacer las "
                         "fases que no correspondan%s" % (
                             flow, "; ".join("%s: %s" % (phase, ", ".join(labels)) for phase, labels in used.items()),
                             " ('desconocida': medida con una versión anterior, que no lo registraba)"
                             if UNKNOWN_CONFIG in distinct else ""))
    return notes


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
    notes += config_notes(folder, sorted({r["flujo"] for r in rows}))
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
        business = pick(MANAGEMENT_SECTION)
        if business is not None and not without_placeholders(business):
            out.append("Resumen para gerencia (de 3 a 5 líneas, sin términos técnicos)")
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


RAW_HTML = re.compile(r"^\s*(?:<details(?: open)?>|</details>|<summary>[^<>]*</summary>)\s*$")


def md_to_html(text):
    """Markdown mínimo: títulos, párrafos, listas, tablas y bloques de código."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif RAW_HTML.match(line):  # el bloque desplegable de una tabla larga: HTML sin scripts
            out.append(line.strip())
            i += 1
        elif line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            if line.strip() == "```diff":
                kind = (lambda row: "add" if row.startswith("+") else "del" if row.startswith("-") else
                        "file" if row.startswith("# ") else "hunk" if row.startswith("@@") else "ctx")
                out.append('<pre class="diff"><code>%s</code></pre>' % "".join(
                    '<span class="%s">%s</span>' % (kind(row), e(row) or " ") for row in block))
            else:
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
            while i < len(lines) and lines[i].strip() and not re.match(r"\s*(#|>|\||```|[-*]\s|\d+\.\s)", lines[i]) \
                    and not RAW_HTML.match(lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>%s</p>" % inline_md(" ".join(para)))
    return "\n".join(out)


# ── Medidas legibles y gráficos en línea (SVG) ───────────────────────────────
# Los reportes se leen solos: cada número con su unidad y en la escala que se entiende, los gráficos dibujados aquí
# (sin scripts ni recursos externos: el HTML se abre sin conexión y se adjunta a un correo) y, debajo de cada uno, una
# frase que dice qué muestra y qué significa. Los gráficos no dependen solo del color: cada barra lleva su rótulo y las
# series que se comparan tienen trama.

def trim(value, decimals):
    text = ("%%.%df" % decimals) % value
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def nice(value, unit=""):
    """Un valor con su unidad, en la escala que se entiende y redondeado con criterio: 1.81 s, 450 ms, 4.2 ms, 12.5 %,
    3 llamadas. 'sin dato' si no hay valor."""
    if value is None:
        return "sin dato"
    if unit == "ms":
        size = abs(value)
        if size >= 10000:
            return "%s s" % trim(value / 1000, 1)
        if size >= 1000:
            return "%s s" % trim(value / 1000, 2)
        if size >= 10:
            return "%s ms" % trim(value, 0)
        return "%s ms" % trim(value, 1)
    if unit in ("%", "MB"):
        return "%s %s" % (trim(value, 1), unit)
    text = trim(value, 0) if float(value).is_integer() or abs(value) >= 100 else trim(value, 1)
    return "%s %s" % (text, unit) if unit else text


def nice_signed(value, unit=""):
    """Una diferencia legible y con signo: +120 ms, −0.7 s."""
    if value is None:
        return "—"
    return ("+" if value > 0 else "−" if value < 0 else "") + nice(abs(value), unit)


def change_pct(before, after):
    """La variación en porcentaje, con signo ("−39 %"), o '' si no se puede calcular."""
    if before in (None, 0) or after is None:
        return ""
    value = (after - before) / abs(before) * 100
    return "%s%s %%" % ("+" if value > 0 else "−" if value < 0 else "", trim(abs(value), 0 if abs(value) >= 10 else 1))


def axis_scale(top, unit):
    """(divisor, unidad del eje, paso) para un eje de 0 a `top`: los tiempos de un segundo o más, en segundos."""
    divisor, label = (1000.0, "s") if unit == "ms" and top >= 1000 else (1.0, unit)
    span = (top / divisor) or 1
    raw = span / 4
    power = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
    return divisor, label, step


def svg_axis(x0, width, y, top, unit, plain=False):
    """El eje horizontal con 3 a 6 marcas y la unidad. Devuelve (partes del SVG, función valor → x)."""
    top = top or 1
    divisor, label, step = axis_scale(top, unit)
    ticks, value = [], 0.0
    while value * divisor <= top * 1.0001 and len(ticks) < 8:
        ticks.append(value)
        value += step
    end = max(ticks[-1] + step if ticks[-1] * divisor < top else ticks[-1], step) * divisor
    scale = (lambda v: x0 + max(0.0, v) / end * width)
    parts = ['<line x1="%d" y1="%d" x2="%d" y2="%d" class="axis"/>' % (x0, y, x0 + width, y)]
    for tick in ticks + ([end / divisor] if ticks[-1] * divisor < end else []):
        x = scale(tick * divisor)
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="tick"/>' % (x, y, x, y + 4))
        parts.append('<text x="%.1f" y="%d" class="axis-label" text-anchor="middle">%s</text>'
                     % (x, y + 16, e(trim(tick, 2))))
    parts.append('<text x="%d" y="%d" class="axis-label" text-anchor="end">%s</text>' % (x0 + width, y + 30, e(
        {"s": "segundos", "ms": "milisegundos"}.get(label, (PLAIN_UNITS.get(label, label) if plain else label) or "valor"))))
    return parts, scale


CHART_IDS = {"n": 0}


def chart_id():
    CHART_IDS["n"] += 1
    return "c%d" % CHART_IDS["n"]


def hatch_defs(uid):
    return ('<defs><pattern id="%s-h" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">'
            '<rect width="6" height="6" class="hatch-bg"/><line x1="0" y1="0" x2="0" y2="6" class="hatch"/></pattern></defs>'
            % uid)


def range_chart(series, unit, label, noise=None, plain=False):
    """Barras horizontales, una por serie (Antes, Control, Después u Hoy): el largo es la mediana, la línea fina el
    rango de las corridas (más rápida a más lenta) y el valor va escrito. `noise` (opcional): el ruido de medición,
    marcado como una franja alrededor de la mediana de la primera serie. series: [(rótulo, mediana, mín, máx, estilo)],
    con estilo 'before', 'control' (con trama) o 'after'."""
    series = [item for item in series if item[1] is not None]
    if not series:
        return ""
    uid = chart_id()
    top = max(max(item[3] if item[3] is not None else item[1], item[1]) for item in series)
    x0, width, row = 86, 300, 30
    pad = 14 if noise else 0  # lugar para el rótulo del ruido, arriba
    height = 14 + pad + row * len(series) + 36
    axis, scale = svg_axis(x0, width, 10 + pad + row * len(series), top, unit, plain)
    show = (lambda value: plain_value(value, unit)) if plain else (lambda value: nice(value, unit))
    parts = [hatch_defs(uid)]
    if noise:
        first = series[0][1]
        left, right = scale(first - noise), min(scale(first + noise), x0 + width)
        parts.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" class="noise"><title>ruido de medición</title></rect>'
                     % (left, pad + 4, max(right - left, 1.5), row * len(series)))
        parts.append('<text x="%.1f" y="11" class="axis-label" text-anchor="middle">ruido</text>' % ((left + right) / 2))
    for index, (name, middle, low, high, style) in enumerate(series):
        y = 8 + pad + index * row
        fill = 'fill="url(#%s-h)"' % uid if style == "control" else 'class="bar-%s"' % style
        parts.append('<text x="0" y="%d" class="bar-label">%s</text>' % (y + 13, e(name)))
        parts.append('<rect x="%d" y="%d" width="%.1f" height="18" rx="3" %s/>' % (
            x0, y, max(scale(middle) - x0, 2), fill))
        if low is not None and high is not None and high > low:
            parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="whisker"/>' % (scale(low), y + 9, scale(high), y + 9))
            parts += ['<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="whisker"/>' % (scale(v), y + 4, scale(v), y + 14)
                      for v in (low, high)]
        parts.append('<text x="%.1f" y="%d" class="bar-value">%s</text>' % (
            max(scale(middle), scale(high) if high is not None else 0) + 6, y + 13, e(show(middle))))
    parts += axis
    text = "%s: %s" % (label, ", ".join("%s %s" % (name, show(middle)) for name, middle, _, _, _ in series))
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (x0 + width + 80, height, e(text), "".join(parts))


def runs_chart(phases, unit, label):
    """La distribución de las corridas: un punto por corrida y una raya en la mediana, una fila por fase (Antes y,
    si está, Control). phases: [(rótulo, valores)]."""
    phases = [(name, values) for name, values in phases if values]
    if not phases:
        return ""
    x0, width, row = 86, 300, 30
    top = max(max(values) for _, values in phases)
    axis, scale = svg_axis(x0, width, 10 + row * len(phases), top, unit)
    parts = []
    for index, (name, values) in enumerate(phases):
        y = 8 + index * row + 9
        parts.append('<text x="0" y="%d" class="bar-label">%s</text>' % (y + 4, e(name)))
        parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="lane"/>' % (x0, y, x0 + width, y))
        parts += ['<circle cx="%.1f" cy="%d" r="4" class="%s"/>' % (scale(v), y, "dot-before" if index == 0 else "dot-control")
                  for v in values]
        middle = statistics.median(values)
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="median"/>' % (scale(middle), y - 9, scale(middle), y + 9))
        parts.append('<text x="%.1f" y="%d" class="bar-value">mediana %s</text>' % (
            scale(max(values)) + 8, y + 4, e(nice(middle, unit))))
    parts += axis
    height = 14 + row * len(phases) + 36
    text = "%s: %s" % (label, "; ".join("%s, %d corridas, mediana %s" % (name, len(values), nice(statistics.median(values), unit))
                                        for name, values in phases))
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (x0 + width + 120, height, e(text), "".join(parts))


def figure(svg, caption, title=""):
    """Un gráfico con su título y, debajo, la frase que explica qué muestra y qué significa."""
    if not svg:
        return ""
    head = "<figcaption>%s</figcaption>" % title if title else ""
    return '<figure class="chart">%s%s<p class="chart-note">%s</p></figure>' % (head, svg, inline_md(caption))


def final_chart(r, plain=False, plan=None):
    """(svg, frase) de una métrica principal en el reporte final: antes, control y después con su rango y el ruido."""
    unit = r["unidad"]
    series = [("Antes", r["antes"]["mediana"], r["antes"]["min"], r["antes"]["max"], "before")]
    if r.get("control") and not plain:
        series.append(("Control", r["control"]["mediana"], r["control"]["min"], r["control"]["max"], "control"))
    series.append(("Después", r["despues"]["mediana"], r["despues"]["min"], r["despues"]["max"], "after"))
    name = plain_metric(r["metrica"], plan or {}) if plain else "`%s`" % r["metrica"]
    svg = range_chart(series, unit, plain_metric(r["metrica"], plan or {}) if plain else r["metrica"],
                      None if plain else r.get("ruido"), plain=plain)
    pct = plain_pct(r["antes"]["mediana"], r["despues"]["mediana"]).strip()[1:-1] if plain else \
        change_pct(r["antes"]["mediana"], r["despues"]["mediana"])
    words = plain_verdict(r)
    text = "%s pasó de %s a %s%s: %s." % (name, plain_value(r["antes"]["mediana"], unit) if plain else
                                          nice(r["antes"]["mediana"], unit),
                                          plain_value(r["despues"]["mediana"], unit) if plain else
                                          nice(r["despues"]["mediana"], unit),
                                          " (%s)" % pct if pct else "", words)
    if not plain:
        if r.get("control"):
            text += " El control (medir de nuevo sin cambiar nada) quedó en %s: el ruido de medición es %s%s." % (
                nice(r["control"]["mediana"], unit), nice(r.get("ruido"), unit),
                " (%s %%)" % trim(r["ruido_pct"], 1) if r.get("ruido_pct") is not None else "")
        text += " La barra es la mediana y la línea fina va de la corrida más rápida a la más lenta."
    return svg, text


def initial_chart(flow, metric, entry, plain=False, plan=None):
    """(svg, frase) de una métrica principal en el reporte inicial: cómo se reparten las corridas de antes (y del
    control, si está)."""
    unit = entry["unidad"]
    before = entry["fases"].get("antes") or []
    control = entry["fases"].get("control") or []
    stats = describe(before)
    if plain:
        svg = range_chart([("Hoy", stats["mediana"], stats["min"], stats["max"], "before")], unit,
                          plain_metric(metric, plan or {}), plain=True)
        text = ("%s: %s en todas las mediciones." % (plain_metric(metric, plan or {}), plain_value(stats["mediana"], unit))
                if stats["min"] == stats["max"] else
                "%s: lo habitual es %s; según la medición, entre %s y %s." % (
                    plain_metric(metric, plan or {}), plain_value(stats["mediana"], unit), plain_value(stats["min"], unit),
                    plain_value(stats["max"], unit)))
        return svg, text
    svg = runs_chart([("Antes", before), ("Control", control)], unit, metric)
    spread = "varía mucho entre corridas (más de %d %%): tómalo como orientativo" % CV_MAX \
        if "inestable" in stats["avisos"] else "es estable entre corridas"
    text = "`%s` (%s): cada punto es una corrida; la raya, la mediana (%s, la que se compara después). Las %d corridas " \
           "van de %s a %s y %s." % (metric, flow, nice(stats["mediana"], unit), stats["n"], nice(stats["min"], unit),
                                     nice(stats["max"], unit), spread)
    if control and stats["mediana"]:
        noise = abs(statistics.median(control) - stats["mediana"])
        text += " El control, sin cambiar nada, quedó a %s (%s %%): una mejora tiene que mover la mediana más que eso." % (
            nice(noise, unit), trim(noise / abs(stats["mediana"]) * 100, 1))
    return svg, text


# Unidades en palabras para un lector no técnico.
PLAIN_UNITS = {"slices": "bloqueos", "llamadas": "llamadas", "frames": "cuadros", "inflates": "veces",
               "conexiones": "conexiones"}


def plain_pct(before, after):
    """La variación en palabras para gerencia: " (39 % menos)", " (20 % más)" o '' si no se puede calcular."""
    if before in (None, 0) or after is None or after == before:
        return ""
    value = abs(after - before) / abs(before) * 100
    return " (%s %% %s)" % (trim(value, 0 if value >= 10 else 1), "menos" if after < before else "más")


def plain_value(value, unit="ms"):
    """Un valor para un lector no técnico: los tiempos en segundos (o milisegundos si son cortos) y las cantidades con
    su unidad en palabras."""
    if unit == "ms" or value is None:
        return plain_time(value, unit)
    return nice(value, PLAIN_UNITS.get(unit, unit))


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
        table.append([flow, metric, FAMILY_LABEL.get(entry["familia"], entry["familia"]), nice(s["mediana"], entry["unidad"]),
                      nice(s["p90"], entry["unidad"]), "%s – %s" % (nice(s["min"], entry["unidad"]),
                                                                  nice(s["max"], entry["unidad"])), s["n"],
                      fmt_pct(noise, signed=False),
                      human_warnings(s["avisos"] + ([note] if note and frame_metric(metric) else []), s["cv"], s["n"])])
    if not table:
        return ""
    intro = ("> Lo que midió la app antes de cambiar nada, por métrica principal. La **mediana** es el número que se "
             "compara después; el **ruido de medición** es cuánto cambió la métrica al medir dos veces sin tocar nada.\n\n")
    return intro + markdown_table(["Flujo", "Métrica", "Depende de", "Mediana", "P90", "Mín – máx", "Corridas",
                                   "Ruido de medición", "Avisos"], table)


def segment_network_md(rows, plan, phases=("antes",)):
    """La sección "Red por tramo" del reporte: por tramo y por fase, la mediana entre corridas de las llamadas que
    empiezan en el tramo, su duración, su TTFB, las repetidas y las solapadas. '' si el plan no tiene tramos o no hay
    métricas de red por tramo en el CSV."""
    groups = group(rows)
    table = []
    for flow_name, flow in (plan.get("flujos") or {}).items():
        for spec in flow.get("segmentos") or []:
            for phase in phases:
                cells = []
                for metric in SEGMENT_NETWORK:
                    entry = groups.get((flow_name, "%s %s" % (spec["nombre"], metric)))
                    values = entry["fases"].get(phase) if entry else None
                    cells.append(fmt(statistics.median(values), entry["unidad"]) if values else "—")
                if cells[0] != "—":
                    table.append([flow_name, spec["nombre"], phase] + cells)
    if not table:
        return ""
    intro = ("> Las llamadas de red que empiezan dentro de cada tramo del flujo (mediana entre corridas). La duración y el "
             "TTFB incluyen el backend; las repetidas y las solapadas son de la app.\n\n")
    return intro + markdown_table(["Flujo", "Tramo", "Fase", "Llamadas", "Duración mediana", "TTFB mediano",
                                   "Repetidas (2 s)", "Solapadas"], table)


SERVICE_ROW = re.compile(r"red (.+) llamadas")
# Las filas que service_metrics agrega al final de cada corrida.
SERVICE_EXTRA = re.compile(r"red .+ (?:repetidas_2s|solapadas|conexion_ms|inicio_ms|fin_ms)|[A-Za-z][\w-]* red .+ llamadas|"
                           r"red_en_curso_ms|[A-Za-z][\w-]* (?:inicio_ms|fin_ms)")
SERVICES_TOP = 5
SERVICES_NOTE = ("> **Informativa.** Los tiempos de un servicio dependen del backend y de la red del momento y varían "
                 "entre corridas: sirven para ver qué se llama, en qué orden, cuántas veces y dónde se va el tiempo, y a "
                 "quién reportarlo, no para decidir una mejora de la app. Un cambio solo de la app no debería mover el "
                 "tiempo del servidor: si se mueve entre fases, es variación del backend, no efecto de la mejora. "
                 "Servidor (TTFB) es la espera hasta el primer byte; \"en la app\" es la cola antes de salir, la conexión "
                 "nueva y la lectura de la respuesta. `sin dato` no es cero: esa parte no se midió (sin esa sección en la "
                 "traza, o medida con una versión anterior).\n\n")
# Una diferencia del servidor entre fases que ya no es ruido: más de un 20 % y más de 50 ms.
BACKEND_SHIFT = (0.2, 50.0)


def flow_services(rows, flow, phase):
    """Los servicios (endpoints) que el flujo consume en una fase, ordenados por el tiempo que suman por corrida:
    [{"servicio", "llamadas", "ms", "p90", "ttfb", "cola", "conexion", "cliente", "repetidas", "solapadas", "tramos",
    "por_tramo", "inicio", "fin", "suma"}], con None donde el CSV no trae el dato. Sale de las filas `red <servicio> …`
    de metricas.csv; `inicio` es la mediana entre corridas del momento en que empieza su primera llamada."""
    groups = group(rows)

    def values(metric):
        entry = groups.get((flow, metric))
        return entry["fases"].get(phase) if entry else None

    def middle(metric):
        found = values(metric)
        return statistics.median(found) if found else None

    out = []
    for (name, metric), entry in groups.items():
        found = SERVICE_ROW.fullmatch(metric)
        if name != flow or not found or phase not in entry["fases"]:
            continue
        service = found.group(1)
        calls = statistics.median(entry["fases"][phase])
        if not calls:
            continue  # en esta fase el flujo no lo llama
        durations = values("red %s ms" % service)
        item = {"servicio": service, "llamadas": calls,
                "ms": statistics.median(durations) if durations else None,
                "p90": percentile(durations, 0.9) if durations else None}
        for key, suffix in (("ttfb", "ttfb_ms"), ("cola", "cola_ms"), ("conexion", "conexion_ms"),
                            ("cliente", "cliente_ms"), ("repetidas", "repetidas_2s"), ("solapadas", "solapadas"),
                            ("inicio", "inicio_ms"), ("fin", "fin_ms")):
            item[key] = middle("red %s %s" % (service, suffix))
        tail = " red %s llamadas" % service
        item["por_tramo"] = {other[:-len(tail)]: statistics.median(data["fases"][phase])
                             for (owner, other), data in groups.items()
                             if owner == flow and other.endswith(tail) and not other.startswith("red ")
                             and SEGMENT_NAME.fullmatch(other[:-len(tail)]) and phase in data["fases"]
                             and statistics.median(data["fases"][phase])}
        item["tramos"] = sorted(item["por_tramo"])
        item["suma"] = calls * item["ms"] if item["ms"] is not None else None
        out.append(item)
    return sorted(out, key=lambda item: (-(item["suma"] or 0), item["servicio"]))


def invocation_order(items):
    """Los servicios en el orden en que se invocan (la mediana del inicio de su primera llamada); los que no traen el
    dato (medidos con una versión anterior) van al final, por el tiempo que suman."""
    return sorted(items, key=lambda item: (item["inicio"] is None, item["inicio"] if item["inicio"] is not None else 0,
                                           -(item["suma"] or 0), item["servicio"]))


def flow_duration(groups, flow, phase, plan):
    """(métrica, mediana) de lo que dura el flujo en una fase: su ventana, el arranque completo o la primera métrica
    principal en tiempo. (None, None) si no hay ninguna."""
    timed = ["ventana_ms", "ttfd_ms"] + [metric for metric in plan.get("principales") or []
                                         if (flow, metric) in groups and groups[(flow, metric)]["unidad"] == "ms"
                                         and not metric.startswith("red ") and " red" not in metric]
    return next(((metric, statistics.median(groups[(flow, metric)]["fases"][phase])) for metric in timed
                 if (flow, metric) in groups and groups[(flow, metric)]["fases"].get(phase)), (None, None))


def services_wait(rows, flow, phase, plan, items):
    """(espera, duración del flujo, cómo se midió la espera): el tiempo con al menos una llamada en curso
    (`red_en_curso_ms`) o, sin ese dato, la suma de las llamadas (que pueden solaparse)."""
    groups = group(rows)
    _, total = flow_duration(groups, flow, phase, plan)
    busy = groups.get((flow, "red_en_curso_ms"))
    if busy and busy["fases"].get(phase):
        return statistics.median(busy["fases"][phase]), total, "en_curso"
    sums = [item["suma"] for item in items if item["suma"] is not None]
    return (sum(sums) if sums else None), total, "suma"


def service_cells(item, has_segments, phase_label=None, count=None):
    def cell(key, unit="ms"):
        return "sin dato" if item[key] is None else nice(item[key], unit)

    app = "sin dato" if all(item[key] is None for key in ("cola", "conexion", "cliente")) else \
        "cola %s · conexión %s · lectura %s" % (cell("cola"), cell("conexion"), cell("cliente"))
    return ["`%s`" % item["servicio"]] + ([phase_label] if phase_label else []) + [
        nice(item["llamadas"] if count is None else count), cell("inicio"),
        "sin dato" if item["ms"] is None else "%s / %s" % (nice(item["ms"], "ms"), nice(item["p90"], "ms")),
        cell("ttfb"), app, cell("repetidas", ""), cell("solapadas", "")]


PHASE_WORDS = {"despues": "después"}
SERVICE_HEADERS = ["Servicio", "Veces por corrida", "Empieza (desde el inicio del flujo)", "Duración (mediana / P90)",
                   "Servidor (TTFB)", "En la app", "Repetidas (2 s)", "Solapadas"]


def services_md(rows, plan, phases=("antes",)):
    """La sección "Servicios del flujo" del reporte: todos los servicios que el flujo llama, en el orden en que se
    invocan y agrupados por tramo si el plan los tiene, con sus veces por corrida, su duración (mediana y P90), el
    servidor frente a la app y las repetidas y solapadas; el total de espera de servicios y qué parte del flujo es; y,
    con dos fases, antes contra después y si el servidor cambió (variación del backend). Con muchos servicios, la tabla
    va en un bloque desplegable abierto. '' si el CSV no trae red por servicio."""
    blocks = []
    flows = list((plan.get("flujos") or {}))
    flows += sorted({row["flujo"] for row in rows} - set(flows))
    for flow in flows:
        by_phase = {phase: flow_services(rows, flow, phase) for phase in phases}
        if not any(by_phase.values()):
            continue
        main = by_phase[phases[0]] or by_phase[phases[-1]]
        known = {item["servicio"] for items in by_phase.values() for item in items}
        order = [item["servicio"] for item in invocation_order(main)]
        order += [item["servicio"] for phase in phases for item in invocation_order(by_phase[phase])
                  if item["servicio"] not in order]
        order = list(dict.fromkeys(order))
        segments = [spec["nombre"] for spec in (plan.get("flujos") or {}).get(flow, {}).get("segmentos") or []]
        lines = ["**%s**" % flow] if len(flows) > 1 else []
        for phase in phases:
            wait, total, how = services_wait(rows, flow, phase, plan, by_phase[phase])
            calls = sum(item["llamadas"] for item in by_phase[phase])
            head = "en %s, " % PHASE_WORDS.get(phase, phase) if len(phases) > 1 else ""
            if wait is None:
                lines.append("- %s%d servicios y %s por corrida, sin datos de duración." % (
                    head.capitalize(), len(by_phase[phase]), nice(calls, "llamadas")))
                continue
            share = " de %s del flujo (%s %%)" % (nice(total, "ms"), trim(wait / total * 100, 0)) if total else ""
            lines.append("- %s%d servicios y %s por corrida. **Espera de servicios: %s%s**, %s." % (
                head.capitalize(), len(by_phase[phase]), nice(calls, "llamadas"), nice(wait, "ms"), share,
                "el tiempo con al menos una llamada en curso" if how == "en_curso" else
                "sumando las llamadas (si van en paralelo, se solapan: la espera real es menor)"))
        if all(item["inicio"] is None for item in main):
            lines.append("- Orden: por el tiempo que suman (estas corridas no traen el momento de cada llamada: se "
                         "midieron con una versión anterior).")
        else:
            lines.append("- En el orden en que se invocan (la mediana del momento en que empieza la primera llamada de "
                         "cada servicio)%s." % (", agrupados por tramo" if segments else ""))
        headers = SERVICE_HEADERS[:1] + (["Fase"] if len(phases) > 1 else []) + SERVICE_HEADERS[1:]
        groups_by = [(None, order)]
        if segments:
            groups_by = []
            for segment in segments:
                mine = [svc for svc in order if any(segment in item["por_tramo"] for item in
                                                    (next((x for x in by_phase[phase] if x["servicio"] == svc), None)
                                                     for phase in phases) if item)]
                if mine:
                    groups_by.append((segment, mine))
            rest = [svc for svc in order if not any(svc in mine for _, mine in groups_by)]
            if rest:
                groups_by.append(("fuera de los tramos", rest))
        tables = []
        for segment, services in groups_by:
            table = []
            for service in services:
                for phase in phases:
                    item = next((found for found in by_phase[phase] if found["servicio"] == service), None)
                    label = PHASE_WORDS.get(phase, phase) if len(phases) > 1 else None
                    if item is None:
                        measured = any(row["flujo"] == flow and row["fase"] == phase for row in rows)
                        table.append(["`%s`" % service] + ([label] if label else []) +
                                     ["no se llama" if measured else "sin dato"] + ["—"] * 7)
                        continue
                    count = item["por_tramo"].get(segment) if segment in segments else None
                    table.append(service_cells(item, bool(segments), label, count))
            title = "" if segment is None else "**Tramo `%s`**\n\n" % segment if segment in segments else \
                "**Fuera de los tramos**\n\n"
            tables.append(title + markdown_table(headers, table))
        body = "\n\n".join(tables)
        if len(order) > SERVICES_TOP:
            body = "<details open>\n<summary>Los %d servicios del flujo</summary>\n\n%s\n\n</details>" % (len(order), body)
        lines.append("")
        lines.append(body)
        if len(phases) > 1:
            shifts = []
            for service in order:
                found = [next((x for x in by_phase[phase] if x["servicio"] == service), None) for phase in phases]
                if any(item is None or item["ttfb"] is None for item in found):
                    continue
                first, last = found[0]["ttfb"], found[-1]["ttfb"]
                if abs(last - first) > max(BACKEND_SHIFT[0] * abs(first), BACKEND_SHIFT[1]):
                    shifts.append("`%s` (%s → %s)" % (service, nice(first, "ms"), nice(last, "ms")))
            if shifts:
                lines.append("")
                lines.append("El servidor cambió entre fases en %s: es variación del backend o de la red del momento, no "
                             "efecto de la mejora (un cambio solo de la app no mueve el tiempo del servidor)."
                             % ", ".join(shifts))
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return SERVICES_NOTE + "\n\n".join(blocks)


def services_chart(rows, plan, phase="antes"):
    """El gráfico de "Servicios del flujo": los que más tiempo suman por corrida, separados en servidor (TTFB) y app
    (el resto de la duración, con trama), con el valor escrito. Devuelve el HTML de las figuras ('' sin datos)."""
    out = []
    flows = list((plan.get("flujos") or {}))
    flows += sorted({row["flujo"] for row in rows} - set(flows))
    for flow in flows:
        items = [item for item in flow_services(rows, flow, phase) if item["suma"] is not None][:SERVICES_TOP]
        if not items:
            continue
        uid = chart_id()
        x0, width, row = 190, 260, 28
        top = max(item["suma"] for item in items)
        axis, scale = svg_axis(x0, width, 8 + row * len(items) + 4, top, "ms")
        parts = [hatch_defs(uid)]
        for index, item in enumerate(items):
            y = 8 + index * row
            server = item["llamadas"] * item["ttfb"] if item["ttfb"] is not None else None
            parts.append('<text x="0" y="%d" class="bar-label">%s</text>' % (
                y + 13, e(short_name(item["servicio"], 30) + (" ×%s" % trim(item["llamadas"], 1) if item["llamadas"] != 1 else ""))))
            if server is not None:
                parts.append('<rect x="%d" y="%d" width="%.1f" height="18" class="bar-server"><title>servidor</title></rect>'
                             % (x0, y, max(scale(min(server, item["suma"])) - x0, 1)))
                parts.append('<rect x="%.1f" y="%d" width="%.1f" height="18" fill="url(#%s-h)"><title>app</title></rect>'
                             % (scale(min(server, item["suma"])), y, max(scale(item["suma"]) - scale(min(server, item["suma"])), 0), uid))
                detail = "%s (servidor %s · app %s)" % (nice(item["suma"], "ms"), nice(server, "ms"),
                                                        nice(max(item["suma"] - server, 0), "ms"))
            else:
                parts.append('<rect x="%d" y="%d" width="%.1f" height="18" class="bar-before"><title>sin desglose</title></rect>'
                             % (x0, y, max(scale(item["suma"]) - x0, 1)))
                detail = "%s (sin desglose)" % nice(item["suma"], "ms")
            parts.append('<text x="%.1f" y="%d" class="bar-value">%s</text>' % (scale(item["suma"]) + 6, y + 13, e(detail)))
        parts += axis
        legend_y = 8 + row * len(items) + 48
        parts.append('<rect x="0" y="%d" width="12" height="12" class="bar-server"/><text x="18" y="%d" class="axis-label">'
                     'servidor (TTFB)</text>' % (legend_y - 10, legend_y))
        parts.append('<rect x="130" y="%d" width="12" height="12" fill="url(#%s-h)"/><text x="148" y="%d" class="axis-label">'
                     'app (cola, conexión y lectura)</text>' % (legend_y - 10, uid, legend_y))
        svg = '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (
            x0 + width + 210, legend_y + 8, e("Servicios que más tiempo suman en %s: %s" % (flow, ", ".join(
                "%s %s" % (item["servicio"], nice(item["suma"], "ms")) for item in items))), "".join(parts))
        lead = items[0]
        caption = ("Tiempo por corrida de los %d servicios que más suman%s (veces × duración mediana). `%s` es el que más "
                   "pesa: %s por corrida%s. Es informativo: el servidor depende del backend y de la red." % (
                       len(items), " en %s" % flow if len(flows) > 1 else "", lead["servicio"], nice(lead["suma"], "ms"),
                       ", %s de espera del servidor" % nice(lead["llamadas"] * lead["ttfb"], "ms")
                       if lead["ttfb"] is not None else ""))
        out.append(figure(svg, caption, "Servicios que más tiempo suman" + (" · %s" % e(flow) if len(flows) > 1 else "")))
    return "".join(out)


def short_name(text, size):
    """Un nombre largo acortado desde la izquierda (el final de una ruta es lo que la distingue)."""
    return text if len(text) <= size else "…" + text[-(size - 1):]


def representative_run(rows, flow, phase, plan, folder=None):
    """La corrida representativa de una fase: la de la duración del flujo más cercana a la mediana, entre las que traen
    el momento de sus llamadas (su línea de tiempo junto a la traza o, si no, las filas `inicio_ms`). None si ninguna
    lo trae."""
    groups = group(rows)
    metric, middle = flow_duration(groups, flow, phase, plan)
    runs = {row["corrida"] for row in rows if row["flujo"] == flow and row["fase"] == phase}
    timed = {run for run in runs if folder is not None and load_timeline(folder, phase, flow, run)}
    if not timed:
        timed = {row["corrida"] for row in rows if row["flujo"] == flow and row["fase"] == phase
                 and row["metrica"].startswith("red ") and row["metrica"].endswith(" inicio_ms")}
    if not timed:
        return None
    if metric is None:
        return sorted(timed, key=lambda run: to_int(run))[len(timed) // 2]
    values = {row["corrida"]: row["valor"] for row in rows if row["flujo"] == flow and row["fase"] == phase
              and row["metrica"] == metric and row["corrida"] in timed}
    if not values:
        return sorted(timed, key=lambda run: to_int(run))[len(timed) // 2]
    return min(values, key=lambda run: (abs(values[run] - middle), to_int(run)))


def mark_label(name):
    """El nombre de una marca para la línea de tiempo: sin el prefijo MARK y con SCREEN o NAV abreviados."""
    head, _, rest = name.partition(" ")
    return {"MARK": rest, "SCREEN": "pantalla " + rest, "NAV": "ir a " + rest}.get(head, name)


def timeline_chart(rows, plan, phase="antes", folder=None):
    """La línea de tiempo de una corrida representativa (la de duración mediana): cada llamada como una barra sobre el
    eje del flujo, en la fila de su servicio, con las marcas de pantalla (SCREEN, NAV, MARK) como líneas verticales.
    Sirve para ver qué se llama, cuándo y si hay llamadas en serie que podrían ir en paralelo. Con una corrida medida
    antes de esta versión (sin su línea de tiempo), una barra por servicio y el inicio de cada tramo. '' sin el dato."""
    out = []
    flows = list((plan.get("flujos") or {}))
    flows += sorted({row["flujo"] for row in rows} - set(flows))
    for flow in flows:
        run = representative_run(rows, flow, phase, plan, folder)
        if run is None:
            continue
        mine = {row["metrica"]: row["valor"] for row in rows
                if row["flujo"] == flow and row["fase"] == phase and row["corrida"] == run}
        data = load_timeline(folder, phase, flow, run) if folder is not None else None
        if data:
            calls = [(float(c[1]), float(c[2]), str(c[0])) for c in data["llamadas"]
                     if isinstance(c, list) and len(c) == 3]
            marks = [(mark_label(str(m[0])), float(m[1])) for m in data.get("marcas") or []
                     if isinstance(m, list) and len(m) == 2]
            per_call = True
        else:
            calls = []
            for metric, value in mine.items():
                found = re.fullmatch(r"red (.+) inicio_ms", metric)
                if found and mine.get("red %s llamadas" % found.group(1)):
                    calls.append((value, mine.get("red %s fin_ms" % found.group(1), value), found.group(1)))
            marks = [(spec["nombre"], mine["%s inicio_ms" % spec["nombre"]])
                     for spec in (plan.get("flujos") or {}).get(flow, {}).get("segmentos") or []
                     if mine.get("%s inicio_ms" % spec["nombre"]) is not None]
            per_call = False
        if not calls:
            continue
        calls.sort()
        lanes = list(dict.fromkeys(name for _, _, name in calls))
        total = mine.get("ventana_ms")
        top = max([end for _, end, _ in calls] + [total or 0] + [at for _, at in marks])
        uid = chart_id()
        x0, width, row = 190, 330, 22
        top_pad = 14 * min(len(marks), 6) + 6
        height = top_pad + row * len(lanes) + 44
        axis, scale = svg_axis(x0, width, top_pad + 4 + row * len(lanes), top, "ms")
        parts = [hatch_defs(uid)]
        for index, (name, at) in enumerate(marks):
            x = scale(at)
            y = 10 + 14 * (index % 6)
            parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="mark"><title>%s</title></line>' % (
                x, y + 2, x, top_pad + 4 + row * len(lanes), e(name)))
            parts.append('<text x="%.1f" y="%d" class="axis-label">%s</text>' % (x + 2, y, e(short_name(name, 22))))
        for lane, service in enumerate(lanes):
            y = top_pad + lane * row
            mine_calls = [(a, b) for a, b, name in calls if name == service]
            parts.append('<text x="0" y="%d" class="bar-label">%s</text>' % (y + 11, e(short_name(service, 30))))
            for start, end in mine_calls:
                parts.append('<rect x="%.1f" y="%d" width="%.1f" height="14" rx="2" class="bar-after"><title>%s · %s</title>'
                             '</rect>' % (scale(start), y, max(scale(end) - scale(start), 2), e(service), e(nice(end - start, "ms"))))
            label = nice(mine_calls[0][1] - mine_calls[0][0], "ms") if len(mine_calls) == 1 or not per_call else \
                "%d llamadas" % len(mine_calls)
            if not per_call and mine.get("red %s llamadas" % service, 1) > 1:
                label += " · %s llamadas" % trim(mine["red %s llamadas" % service], 0)
            parts.append('<text x="%.1f" y="%d" class="bar-value">%s</text>' % (
                scale(max(end for _, end in mine_calls)) + 5, y + 11, e(label)))
        parts += axis
        # En serie: una llamada que empieza cuando ya terminaron todas las anteriores (con al menos una antes).
        serial, finished = 0, None
        for start, end, _ in calls:
            if finished is not None and start >= finished - 1:
                serial += 1
            finished = end if finished is None else max(finished, end)
        svg = '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (
            x0 + width + 140, height, e("Línea de tiempo de la corrida %s de %s en %s" % (run, flow, phase)), "".join(parts))
        what = ("cada barra es una llamada, en la fila de su servicio, y las líneas verticales son las marcas de pantalla"
                if per_call else "medida con una versión anterior: cada barra va desde la primera llamada de un servicio "
                "hasta que termina la última%s" % ("; las líneas verticales marcan dónde empieza cada tramo" if marks else ""))
        caption = "Corrida %s (la de duración mediana): %s. %s" % (
            run, what, "%d %s empieza%s cuando ya terminaron todas las anteriores: si no dependen de ellas, podrían ir en "
            "paralelo." % (serial, "llamada" if serial == 1 else "llamadas", "" if serial == 1 else "n")
            if serial else "Las llamadas se solapan: no hay una cadena en serie evidente.")
        out.append(figure(svg, caption, "Línea de tiempo de los servicios" + (" · %s" % e(flow) if len(flows) > 1 else "")))
    return "".join(out)


def plain_time(value, unit="ms"):
    """Un valor para un lector no técnico: los tiempos en segundos (o en milisegundos si son muy cortos)."""
    if value is None:
        return "sin dato"
    if unit != "ms":
        return fmt(value, unit)
    if 0 < abs(value) < 1:
        return "menos de 1 milisegundo"
    return "%s s" % fmt(value / 1000) if abs(value) >= 100 else "%s milisegundos" % fmt(round(value))


def services_line(rows, plan, phase="antes"):
    """Para gerencia, una o dos frases por flujo: cuántos servicios llama, cuánto del recorrido es espera de servicios y
    cuál es el más lento. Dice si no hay datos de red: no medirla no es lo mismo que no llamar a ningún servicio."""
    groups = group(rows)
    lines = []
    flows = list((plan.get("flujos") or {}))
    flows += sorted({row["flujo"] for row in rows} - set(flows))
    for flow in flows:
        services = flow_services(rows, flow, phase)
        lead = "**%s:** " % flow if len(flows) > 1 else ""
        if not services:
            counted = groups[(flow, "red_llamadas")]["fases"].get(phase) if (flow, "red_llamadas") in groups else None
            calls = statistics.median(counted) if counted else None
            lines.append(lead + ("No hay datos de las llamadas a servicios (no se midieron)." if calls is None else
                                 "El recorrido no llama a ningún servicio." if not calls else
                                 "El recorrido hace %s a servicios; no hay datos de cada servicio."
                                 % ("1 llamada" if calls == 1 else "%s llamadas" % fmt(calls))))
            continue
        calls = sum(item["llamadas"] for item in services)
        count = "El recorrido llama a %s (%s en total)." % (
            "1 servicio" if len(services) == 1 else "%d servicios" % len(services),
            "1 llamada" if calls == 1 else "%s llamadas" % trim(calls, 1))
        timed = [item for item in services if item["ms"] is not None]
        wait, total, how = services_wait(rows, flow, phase, plan, services)
        slow = max(timed, key=lambda item: item["ms"], default=None)
        if wait is not None:
            if how == "en_curso":
                text = ("%s De los %s del recorrido, durante %s (%s %%) se está esperando a algún servicio" % (
                    count, plain_time(total), plain_time(wait), trim(wait / total * 100, 0)) if total else
                    "%s Se espera a algún servicio durante %s por recorrido" % (count, plain_time(wait)))
            else:
                text = ("%s De los %s del recorrido, las llamadas suman %s (si van en paralelo, parte se solapa)" % (
                    count, plain_time(total), plain_time(wait)) if total else
                    "%s Las llamadas suman %s por recorrido (si van en paralelo, parte se solapa)" % (count, plain_time(wait)))
            if len(timed) < len(services):
                text += " (sin contar %d sin dato de duración)" % (len(services) - len(timed))
        else:
            text = "%s No hay datos de cuánto tardan" % count
        if slow is not None:
            text += "; el más lento es `%s` (%s por llamada)" % (slow["servicio"], plain_time(slow["ms"]))
        lines.append(lead + text + ". Es orientativo: depende del servidor y de la red del momento.")
    return "\n\n".join(lines)


# Los reportes para gerencia no nombran métricas: cada una lleva un rótulo en palabras. `etiquetas` del plan lo cambia.
PLAIN_METRIC = {"ttid_ms": "Tiempo hasta que aparece la primera pantalla",
                "ttfd_ms": "Tiempo hasta que la pantalla queda completa",
                "ventana_ms": "Duración del recorrido", "hilo_max_ms": "Mayor congelamiento de la pantalla",
                "hilo_slices_100ms": "Congelamientos que se notan", "hilo_slices_sobre_presupuesto": "Tirones breves",
                "jank_app_pct": "Cuadros que se ven trabados", "jank_total_pct": "Cuadros trabados, contando los del sistema",
                "frame_p50_ms": "Fluidez habitual", "frame_p90_ms": "Fluidez en los momentos más lentos",
                "frame_p99_ms": "Fluidez en los peores momentos", "red_llamadas": "Llamadas a servicios",
                "red_repetidas_2s": "Llamadas a servicios repetidas", "red_solapadas": "Llamadas a servicios duplicadas",
                "red_ms": "Duración de las llamadas a servicios", "red_ttfb_ms": "Espera de los servicios",
                "inflate_cantidad": "Pantallas que se arman de nuevo", "inflate_ms": "Tiempo armando la pantalla",
                "pss_mb": "Memoria que usa la app", "java_heap_mb": "Memoria de la app (objetos)",
                "native_heap_mb": "Memoria de la app (nativa)", "gfx_jank_pct": "Cuadros que se ven trabados",
                "gfx_p90_ms": "Fluidez en los momentos más lentos", "bind_application_ms": "Tiempo de inicio de la app",
                "red_conexiones": "Conexiones nuevas a servicios", "red_conexion_ms": "Tiempo conectando con los servicios"}
# Una métrica de un servicio (`red <servicio> ms`, `<tramo> red <servicio> llamadas`) en palabras.
SERVICE_WORDS = {"llamadas": "Llamadas al servicio", "ms": "Duración del servicio", "ttfb_ms": "Espera del servicio",
                 "cola_ms": "Espera en la app antes de llamar al servicio", "cliente_ms": "Lectura de la respuesta del servicio",
                 "conexion_ms": "Conexión con el servicio", "repetidas_2s": "Llamadas repetidas al servicio",
                 "solapadas": "Llamadas duplicadas al servicio"}
PLAIN_SERVICE = re.compile(r"(?:(?P<tramo>[A-Za-z][\w-]*) )?red (?P<servicio>.+) (?P<que>%s)" % "|".join(SERVICE_WORDS))
PLAIN_VERDICT = {"mejora": "mejora clara", "regresión": "empeoró", "sin cambio": "sin cambio",
                 "dentro del ruido": "sin cambio: la diferencia es menor que la variación normal entre mediciones",
                 "no comparable": "no se puede comparar: se midió otra cosa antes y después",
                 "no confiable": "no confiable: el dispositivo de medición no representa uno real",
                 "informativa": "solo informativo"}
MANAGEMENT_SECTION = "resumen para gerencia"
MANAGEMENT_MISSING = ("_Sin completar: el resumen para este público todavía no se escribió. Lo que sigue sale de los "
                      "datos de la investigación._")


def plain_metric(metric, plan):
    """El rótulo de una métrica para un lector no técnico: el de `etiquetas` del plan, el de las métricas que la skill
    conoce o, para una métrica propia del proyecto, su nombre en palabras."""
    labels = plan.get("etiquetas") if isinstance(plan.get("etiquetas"), dict) else {}
    if labels.get(metric):
        return str(labels[metric])
    if metric in PLAIN_METRIC:
        return PLAIN_METRIC[metric]
    service = PLAIN_SERVICE.fullmatch(metric)
    if service:
        text = "%s `%s`" % (SERVICE_WORDS[service.group("que")], service.group("servicio"))
        return text + (", en la parte \"%s\"" % service.group("tramo").replace("_", " ").replace("-", " ")
                       if service.group("tramo") else "")
    head, _, rest = metric.partition(" ")
    if rest in PLAIN_METRIC:
        return "%s, en la parte \"%s\"" % (PLAIN_METRIC[rest], head.replace("_", " ").replace("-", " "))
    words = re.sub(r"_(?:ms|pct|mb)$", "", metric).replace("_", " ").replace("-", " ").strip()
    return "Tiempo de \"%s\"" % words if metric.endswith("_ms") else "\"%s\"" % words


def plain_verdict(result):
    """El veredicto de una comparación en palabras, con su confianza."""
    text = PLAIN_VERDICT.get(result["veredicto"], result["veredicto"])
    if result["veredicto"] in ("mejora", "regresión"):
        if "inestable" in result["avisos"]:
            return "orientativo: varía mucho entre corridas (%s)" % text
        if "pocas corridas" in result["avisos"]:
            return "orientativo: pocas mediciones (%s)" % text
        if result["familia"] == "e2e":
            return "%s (orientativo: depende también del servidor)" % text
    return text


def ficha_value(ficha, *names):
    """El valor de una fila de la Ficha de estado.md, o '' si falta o sigue con el texto de la plantilla."""
    for row in parse_table(ficha)[1]:
        if len(row) > 1 and row[0].strip().lower().startswith(names) and not has_placeholder(" | ".join(row[1:])):
            return row[1].strip()
    return ""


# Lo que un lector no técnico no entiende: el reporte de gerencia no publica un texto escrito por la IA (el resumen para
# gerencia, el síntoma de la ficha, el síntoma y la causa de los hallazgos y el título de las mejoras) que lo traiga.
# Es la única lista: la documentan diagnostico.md y cierre.md.
TECH_TERMS = re.compile(
    r"(?<![\w-])(?:slices?|CV|P\d{2}|percentil(?:es)?|TTFB|TTID|TTFD|jank|doFrame|Choreographer|RenderThread|Perfetto|"
    r"trace_processor|traza|ANR|GC|heap|OkHttp|Retrofit|corrutinas?|coroutines?|Dispatchers|Compose|LazyColumn|"
    r"RecyclerView|ViewModel|StateFlow|recomposici[oó]n(?:es)?|endpoints?|backend|frames?|hilo principal|main thread|"
    r"ms|mediana)(?![\w-])", re.I)
# Nombres con forma de código: entre acentos graves, con guion bajo (lista_ms), en CamelCase (ListaScreen), una llamada
# (cargar()), un nombre con punto (viewModel.cargar) o un archivo de código (Lista.kt).
CODE_TERMS = re.compile(r"`[^`]+`|\b\w+\.(?:kt|java|xml|gradle|kts)\b|\b\w+(?:\.\w+)*\(\)|\b[a-z]\w*\.[a-z]\w*\b|"
                        r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|\b[a-z]\w*[A-Z]\w*\b")


def jargon(text):
    """Los términos técnicos de un texto para gerencia (TECH_TERMS y CODE_TERMS), sin repetir y en orden."""
    found = [m.group(0) for m in TECH_TERMS.finditer(text or "")] + [m.group(0) for m in CODE_TERMS.finditer(text or "")]
    return list(dict.fromkeys(found))


def plain_or_unfilled(text, field, problems):
    """El texto si no trae términos técnicos; si los trae, "sin completar" y el aviso en `problems`."""
    found = jargon(text)
    if not found:
        return text
    problems.append((field, found))
    return "_%s_" % UNFILLED


def management_parts(folder, plan, rows, sections, results=None, problems=None):
    """Las secciones del reporte para gerencia (inicial si `results` es None; si no, final): una página corta, en
    palabras, sin nombres de métricas, percentiles ni términos de la traza. Todo sale de los mismos datos que el
    reporte técnico; lo único que escribe el modelo es el "Resumen para gerencia" de estado.md. Lo que la IA escribió
    con términos técnicos (TECH_TERMS, CODE_TERMS) no se publica: queda "sin completar" y va a `problems` como
    (campo, términos)."""
    final = results is not None
    principales = plan.get("principales") or []
    mejoras = plan.get("mejoras") or []
    problems = [] if problems is None else problems

    def pick(*names):
        return next((sections[k] for k in sections for n in names if k.startswith(n)), "")

    def title(item):
        return plain_or_unfilled(improvement_title(item), "el título de %s en plan.json" % item.get("id", "una mejora"),
                                 problems)

    summary = without_placeholders(pick(MANAGEMENT_SECTION))
    if summary:
        summary = plain_or_unfilled(summary, "\"Resumen para gerencia\" de estado.md", problems)
        if summary.startswith("_"):
            summary = MANAGEMENT_MISSING.replace("todavía no se escribió", "tiene términos técnicos y no se publica")
    symptom = ficha_value(pick("ficha"), "síntoma", "sintoma")
    if symptom:
        symptom = plain_or_unfilled(symptom, "el síntoma de la Ficha de estado.md", problems)
    headers, findings = parse_table(pick("hallazgos"))
    lower = [h.lower() for h in headers]

    def column(*prefixes):
        return next((i for i, h in enumerate(lower) if h.startswith(prefixes)), None)

    tipo_i, symptom_i, cause_i = column("tipo"), column("síntoma", "sintoma"), column("causa")

    def cell(row, index):
        value = row[index].strip() if index is not None and index < len(row) else ""
        return "" if value in ("", "—", "-") or has_placeholder(value) else value

    findings = [row for row in findings if row and row[0].strip()]
    kinds = [finding_kind(cell(row, tipo_i)) for row in findings]
    confirmed = [row for row, kind in zip(findings, kinds) if kind in ("bug", "mejorable")]
    found = ["- %s" % ": ".join(plain_or_unfilled(part, "%s de %s en Hallazgos de estado.md" % (what, row[0].strip()),
                                                  problems)
                                for what, part in (("el síntoma", cell(row, symptom_i)), ("la causa", cell(row, cause_i)))
                                if part)
             for row in confirmed if cell(row, symptom_i) or cell(row, cause_i)]
    other = [(one if count == 1 else many % count) for one, many, count in (
        ("1 se investigó y se descartó", "%d se investigaron y se descartaron", kinds.count("descartado")),
        ("1 quedó sin confirmar", "%d quedaron sin confirmar", kinds.count("sin confirmar"))) if count]
    found_md = "\n".join(found) if found else "Ningún problema confirmado." if findings else \
        "El diagnóstico no dejó hallazgos registrados."
    if other:
        found_md += "\n\nOtras causas posibles: %s." % " y ".join(other)

    applied = [m for m in mejoras if m.get("estado") == "aplicada"]
    if final:
        done_md = "\n".join("- %s" % title(m) for m in applied) if applied else "No se aplicó ningún cambio."
    else:
        done_md = "\n".join("- %s" % title(m) for m in mejoras) + \
            "\n\nQué se aplica lo decides tú; lo aprobado se implementa y se vuelve a medir." if mejoras else \
            "No se propone ningún cambio."

    lines = []
    many = len(plan.get("flujos") or {}) > 1

    def label(metric, flow):
        return plain_metric(metric, plan) + (" (%s)" % flow if many else "")

    main_results = sorted([r for r in results if r["metrica"] in principales],
                          key=lambda r: (principales.index(r["metrica"]), r["flujo"])) if final else []
    if final:
        for metric in principales:
            found = [r for r in main_results if r["metrica"] == metric]
            if not found:
                lines.append("- **%s:** sin medición de antes y después." % plain_metric(metric, plan))
            lines += ["- **%s:** pasó de %s a %s%s · %s." % (
                label(metric, r["flujo"]), plain_value(r["antes"]["mediana"], r["unidad"]),
                plain_value(r["despues"]["mediana"], r["unidad"]), plain_pct(r["antes"]["mediana"], r["despues"]["mediana"]),
                plain_verdict(r)) for r in found]
    else:
        groups = group(rows)
        for metric in principales:
            found = sorted((flow, data) for (flow, name), data in groups.items() if name == metric and "antes" in data["fases"])
            if not found:
                lines.append("- **%s:** sin medir todavía." % plain_metric(metric, plan))
            for flow, entry in found:
                stats = describe(entry["fases"]["antes"])
                trust = "orientativo: varía mucho entre corridas" if "inestable" in stats["avisos"] else \
                    "orientativo: pocas mediciones" if "pocas corridas" in stats["avisos"] else "estable entre mediciones"
                lines.append("- **%s:** %s · %s." % (label(metric, flow), plain_value(stats["mediana"], entry["unidad"]), trust))
    result_md = "\n".join(lines) if lines else "No se fijó ninguna medida principal para este recorrido."

    waiting = [m for m in mejoras if m.get("estado", "propuesta") != "aplicada"] if final else []
    state_words = {"propuesta": "sin decidir", "aprobada": "aprobado, sin aplicar", "descartada": "descartado",
                   "pendiente": "para más adelante"}
    pending = ["- %s (%s)" % (title(m), state_words.get(m.get("estado", "propuesta"), m.get("estado")))
               for m in waiting]
    open_points = [line for line in without_placeholders(pick("pendientes")).splitlines() if line.strip().startswith(("-", "*"))]
    if open_points:
        pending.append("- %d %s de la investigación sin cerrar; el detalle está en el reporte técnico." % (
            len(open_points), "punto" if len(open_points) == 1 else "puntos"))
    pending_md = "\n".join(pending) if pending else "Nada pendiente."

    risks = ["- %s: riesgo %s." % (title(m), m["riesgo"]) for m in (applied if final else mejoras)
             if str(m.get("riesgo") or "").strip() not in ("", "—", "-")]
    if final:
        # Solo las medidas principales: las demás (también los tiempos de cada servicio, que son orientativos) están
        # en el reporte técnico, con su nombre.
        risks += ["- %s: de %s a %s · %s." % (label(r["metrica"], r["flujo"]),
                                            plain_value(r["antes"]["mediana"], r["unidad"]),
                                            plain_value(r["despues"]["mediana"], r["unidad"]), plain_verdict(r))
                  for r in main_results if r["veredicto"] == "regresión"]
        others = sum(1 for r in results if r["veredicto"] == "regresión" and r["metrica"] not in principales)
        if others:
            risks.append("- %s que no %s: el detalle está en el reporte técnico." % (
                "Empeoró 1 medida" if others == 1 else "Empeoraron %d medidas" % others,
                "es principal" if others == 1 else "son principales"))
        by_metric = {r["metrica"]: r for r in results}
        risks += ["- %s: el cambio no dio el resultado esperado." % title(m) for m in applied
                  if improvement_result(m, by_metric.get(m.get("metrica"))).startswith("✖")]
    level, _ = frames_trust(folder)
    if level != "ok":
        risks.append("- La fluidez se midió en un dispositivo que no representa uno real: esos valores son %s."
                     % ("no confiables" if level == "no" else "orientativos"))
    risks_md = "\n".join(risks) if risks else "Sin riesgos señalados."

    services = services_line(rows, plan, "despues" if final and any(r["fase"] == "despues" for r in rows) else "antes")
    cost = "Sesiones de IA: %s. Las mediciones corren sin IA y no tienen costo de uso." % cost_total(folder, plan)
    kind = "final" if final else "inicial"
    return [("En resumen", summary or MANAGEMENT_MISSING),
            ("Qué notaba el usuario", symptom or "_%s_" % UNFILLED),
            ("Qué se encontró", found_md),
            ("Qué se hizo" if final else "Qué se propone", done_md),
            ("Resultado" if final else "Cómo está hoy", result_md),
            ("Servicios", services),
            ("Lo que queda pendiente", pending_md),
            ("Riesgos", risks_md),
            ("Costo", cost),
            ("Más detalle", "El reporte técnico, con las mediciones completas y cómo leerlas: `reporte-%s-dev`." % kind)]


def write_reports(folder, kind, title, date, parts, business, html_too, charts="", extras=None, business_extras=None,
                  dev_note=""):
    """Escribe las dos versiones de un reporte (`reporte-<tipo>-dev` y `reporte-<tipo>-gerencia`), en markdown y, con
    `html_too`, en HTML. Las dos salen de los mismos datos; cada una con sus gráficos (`extras`, `business_extras`)."""
    label = "inicial" if kind == "inicial" else "final"
    for audience, sections, text in (("dev", parts, "Reporte %s%s" % (label, dev_note)),
                                     ("gerencia", business, "Reporte %s para gerencia" % label)):
        name = "reporte-%s-%s" % (kind, audience)
        page = render_report(folder, name, title, "%s · %s · hb-performance %s" % (text, date, VERSION), sections,
                             charts if audience == "dev" else "", extras if audience == "dev" else business_extras,
                             plain=audience != "dev")
        print("✔ Reporte %s (%s): %s" % (label, audience, folder / ("%s.md" % name)))
        if html_too:
            (folder / ("%s.html" % name)).write_text(page, encoding="utf-8")
            print("✔ Reporte HTML (%s): %s" % (audience, folder / ("%s.html" % name)))
    old = [name for name in ("reporte-%s.html" % kind, "reporte-%s.md" % kind) if (folder / name).is_file()]
    if old:
        print("· %s %s de una versión anterior y no se actualiza: los reportes de ahora son reporte-%s-dev y "
              "reporte-%s-gerencia." % (", ".join(old), "es" if len(old) == 1 else "son", kind, kind))


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
            why = "%s: %s → %s (%s) · %s" % (m.get("metrica"), nice(r["antes"]["mediana"], r["unidad"]),
                                            nice(r["despues"]["mediana"], r["unidad"]),
                                            change_pct(r["antes"]["mediana"], r["despues"]["mediana"]) or "—",
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


TECH_FOOTER = "Los números son medianas de varias corridas; el detalle está en"
PLAIN_FOOTER = "Cada valor resume varias mediciones del mismo recorrido; el detalle técnico está en"


def render_report(folder, name, title, subtitle, parts, charts="", extras=None, plain=False):
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
    if plain:  # el reporte para gerencia no habla de medianas
        page = page.replace(TECH_FOOTER, PLAIN_FOOTER)
    return page.replace("{{TITLE}}", e(title)).replace("{{SUBTITLE}}", e(subtitle)).replace("{{BODY}}", body)


def verdict_words(r):
    """El veredicto en palabras para la tabla técnica: cuánto vale ("mejora clara", "orientativo: varía mucho entre
    corridas") y qué significa."""
    meaning = VERDICT_TEXT.get(r["veredicto"], "")
    if r["veredicto"] in ("no comparable", "no confiable", "informativa"):
        return meaning
    words = plain_verdict(r)
    return "%s · %s" % (words[0].upper() + words[1:], meaning)


def warn_jargon(problems):
    """Los textos que el reporte de gerencia no publicó por traer términos técnicos: qué pasó y qué hacer, uno por
    campo, con el comando para generar de nuevo."""
    seen = []
    for field, terms in problems:
        if field in [item[0] for item in seen]:
            continue
        seen.append((field, terms))
    for field, terms in seen:
        print("⚠ Gerencia: %s tiene términos técnicos (%s) y no se publicó: el reporte de gerencia dice \"%s\" en ese "
              "punto. Qué hacer: reescríbelo en palabras, sin nombres de métricas, de código ni términos de la traza (la "
              "lista está en cierre.md · Reporte), y genera de nuevo:" % (field, ", ".join(terms[:6]), UNFILLED))
        print("    %s" % same_command())


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
    if not any(key.startswith(MANAGEMENT_SECTION) for key in sections):
        print("· %s no tiene la sección \"## Resumen para gerencia\" (es de una versión anterior): el reporte para "
              "gerencia sale igual, con esa parte \"%s\". Para completarla, agrega la sección con 3 a 5 líneas sin "
              "términos técnicos y vuelve a generar." % (state_path, UNFILLED))
    pending_intro = ("> No son mejoras ni tareas obligatorias: es lo que esta investigación no pudo cerrar. De cada uno "
                     "importa el síntoma y qué tan estable es, qué falta para cerrarlo, cuánto cuesta y la acción "
                     "sugerida.\n\n")
    if args.inicial:
        plan_md = plan_table_md(plan, rows) if plan.get("mejoras") else ""
        if plan_md and update_block(folder, "mejoras", plan_md):
            print("✔ estado.md actualizado (Plan de mejoras)")
        plan_intro = ("> Lo que se propone cambiar, una mejora por hallazgo. **Tú decides** cuáles se aplican "
                      "en la terminal, con el comando `decidir` que imprime `perf.py siguiente` (sin chat); las aprobadas se "
                      "implementan en la fase siguiente y se vuelven a medir.\n\n")
        parts = [("Resultado", result_md(pick("hallazgos"), plan)),
                 ("Resumen", filled("resumen ejecutivo", "resumen")),
                 ("Estado inicial", initial_md(rows, plan, frames_trust(folder))),
                 ("Servicios del flujo", services_md(rows, plan)),
                 ("Red por tramo", segment_network_md(rows, plan)),
                 ("Hallazgos", findings_md(pick("hallazgos"), plan)),
                 ("Plan de mejoras", plan_intro + plan_md if plan_md else ""),
                 ("Ficha y condiciones", ficha_subset(pick("ficha"))),
                 ("Pendientes (no son mejoras)", pending_intro + filled("pendientes") if filled("pendientes") else ""),
                 ("Costo de la investigación", cost_md(folder, plan)),
                 ("Cómo leer este reporte", GLOSSARY)]
        problems = []
        business = management_parts(folder, plan, rows, sections, problems=problems)
        groups = group(rows)
        principal = [(flow, metric, entry) for (flow, metric), entry in sorted(
            groups.items(), key=lambda kv: (kv[0][0], priority(kv[0][1], plan)))
            if metric in (plan.get("principales") or []) and entry["fases"].get("antes")]
        figures = "".join(figure(*initial_chart(flow, metric, entry)) for flow, metric, entry in principal)
        extras = {"Estado inicial": '<div class="charts">%s</div>' % figures} if figures else {}
        services_html = services_chart(rows, plan) + timeline_chart(rows, plan, folder=folder)
        if services_html:
            extras["Servicios del flujo"] = services_html
        plain_figures = "".join(figure(*initial_chart(flow, metric, entry, plain=True, plan=plan))
                                for flow, metric, entry in principal[:3])
        write_reports(folder, "inicial", title, date, parts, business, args.html, extras=extras,
                      business_extras={"Cómo está hoy": '<div class="charts">%s</div>' % plain_figures}
                      if plain_figures else None)
        warn_jargon(problems)
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
        [r["flujo"], r["metrica"], FAMILY_LABEL.get(r["familia"], r["familia"]), nice(r["antes"]["mediana"], r["unidad"]),
         nice(r["despues"]["mediana"], r["unidad"]), "%s (%s)" % (nice_signed(r["delta"], r["unidad"]),
                                                                 change_pct(r["antes"]["mediana"], r["despues"]["mediana"]) or "—"),
         r["veredicto"], verdict_words(r) + (" · depende del backend" if r["familia"] == "e2e" else "")]
        for r in primary]) if primary else ""
    results_by_metric = {r["metrica"]: r for r in results}
    n_findings = len(parse_table(pick("hallazgos"))[1])
    logrado_md = markdown_table(LOGRADO_HEADERS, logrado_rows(plan, results, readable=True)) if plan.get("mejoras") else ""
    comparison_md = ("> La tabla técnica, igual a `comparacion.md`: todas las métricas medidas, con mediana y P90 por fase. "
                     "Familia `app` = solo la app, `e2e` = app + backend; Ruido (A/A) = antes contra control.\n\n"
                     + markdown_table(COMPARE_HEADERS, [compare_cells(r) for r in chosen])) if chosen else \
        "No hay métricas con antes y después."
    parts = [("Resumen ejecutivo", filled("resumen ejecutivo")),
             ("De los hallazgos al resultado", improvements_summary(plan, results, n_findings)),
             ("Métricas principales", primary_md),
             ("Servicios del flujo", services_md(rows, plan, ("antes", "despues") if any(
                 row["fase"] == "despues" for row in rows) else ("antes",))),
             ("Red por tramo", segment_network_md(rows, plan, ("antes", "despues"))),
             ("Mejoras: esperado contra logrado", logrado_md),
             ("Hallazgos", findings_md(pick("hallazgos"), plan, results_by_metric)),
             ("Mejoras aplicadas", filled("mejoras aplicadas")),
             ("Cambios de código (interno: contiene código)", changes_md(folder, plan, results, pick("hallazgos"))),
             ("Lectura de la comparación", filled("lectura de la comparación", "lectura de la comparacion")),
             ("Comparación completa", comparison_md), ("Ficha y condiciones", ficha_subset(pick("ficha"))),
             ("Pendientes (no son mejoras)", pending_intro + filled("pendientes") if filled("pendientes") else ""),
             ("Costo de la investigación", cost_md(folder, plan)),
             ("Cómo leer este reporte", GLOSSARY)]
    charts = "".join(figure(*final_chart(r, plan=plan), title='%s · %s <span class="verdict %s">%s</span>' % (
        e(r["metrica"]), e(r["flujo"]), VERDICT_CLASS[r["veredicto"]], e(r["veredicto"]))) for r in primary)
    summary_rows = parse_table(improvements_summary(plan, results, n_findings))[1]
    extras = {"De los hallazgos al resultado": flow_html(flow_counts(plan, summary_rows, n_findings))} if summary_rows else {}
    last = "despues" if any(row["fase"] == "despues" for row in rows) else "antes"
    services_html = services_chart(rows, plan, last) + timeline_chart(rows, plan, last, folder)
    if services_html:
        extras["Servicios del flujo"] = services_html
    problems = []
    business = management_parts(folder, plan, rows, sections, results, problems=problems)
    plain_figures = "".join(figure(*final_chart(r, plain=True, plan=plan)) for r in primary[:3])
    internal = any(name.startswith("Cambios de código") and body for name, body in parts)
    write_reports(folder, "final", title, date, parts, business, args.html, charts, extras,
                  {"Resultado": '<div class="charts">%s</div>' % plain_figures} if plain_figures else None,
                  " · interno: contiene código" if internal else "")
    warn_jargon(problems)
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


def keyboard_shown(adb):
    """True solo si `dumpsys input_method` dice que el teclado está a la vista (mInputShown=true)."""
    return bool(re.search(r"\bmInputShown=true\b", adb.shell("dumpsys input_method").stdout))


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
        if keyboard_shown(adb):
            print("⚠ El teclado estaba abierto al volcar: tapa parte de la pantalla y desplaza el contenido, así que estas "
                  "coordenadas solo valen con el teclado abierto. Tómalas con el teclado en el mismo estado que tendrá el "
                  "recorrido en ese paso (ficha.md · Teclado).")
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

# Teclado: ciérralo solo si está abierto (BACK con el teclado cerrado sale de la pantalla) y sin cortar el recorrido
# si ya estaba cerrado. ESC (keyevent 111) no cierra todos los teclados.
# teclado="$(adb -s "$SERIAL" shell dumpsys input_method | grep -c 'mInputShown=true' || true)"
# if [ "$teclado" != "0" ]; then adb -s "$SERIAL" shell input keyevent 4 && sleep 1; fi

# Punto de control (opcional): comprueba qué ventana está al frente con un comando barato y, si no es la esperada,
# termina con 1: la corrida se descarta y se repite sin esperar al final. Corre DENTRO de la traza: déjalo igual en
# todas las fases y no uses uiautomator aquí (tarda segundos). Mira la actividad, no la pantalla: en una app de una
# sola actividad solo detecta que saliste de la app (otra app, el launcher, un diálogo del sistema).
# en_pantalla() {
#   foco="$(adb -s "$SERIAL" shell dumpsys window | grep mCurrentFocus || true)"
#   case "$foco" in *"$1"*) ;; *) echo "punto de control: '$1' no está al frente ($foco)" >&2; exit 1 ;; esac
# }
# en_pantalla "<parte del nombre de la actividad>"

# Paso humano (autorizar en otra app, resolver un desafío, elegir con criterio): quita el # de la función y llámala
# donde la persona tiene que actuar. Muestra el texto en tu terminal, con un pitido, y espera Enter; con x + Enter la
# corrida se descarta y se repite. Sin una terminal (un agente) la captura se detiene enseguida, sin quedarse esperando.
# El tiempo de la pausa no se mide: declárala en "pausas" del plan (ficha.md · Flujos que pasan por otra app).
# pausa() { python3 -I "{{PERF}}" pausa "$1" || exit $?; }
# pausa "Autoriza la operación en la otra app, vuelve a esta y presiona Enter"
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
    """El texto del chat de la sesión 1: el de "flujo largo" si para llegar al tramo hay login u otras pantallas. Dice
    qué hay que pasar para llegar, no cómo recorrerlo: el modo de recorrido se elige en las preguntas de la sesión 1."""
    flow = request["flujo"].strip().rstrip(".")
    reach = (request.get("llegar") or "").strip().rstrip(".")
    if reach:
        # No fija cómo se recorre (adb, Maestro en preparar, deep link o manual): esa pregunta es de la sesión 1.
        return chat_text("Usa hb-performance: medir %s. Para llegar ahí hay que %s. Dispositivo %s." % (flow, reach, serial))
    return chat_text("Usa hb-performance: medir %s. Dispositivo %s." % (flow, serial))


def cmd_humo(args):
    """Prueba de humo del setup: una corrida de arranque en frío, sin crear una investigación."""
    folder = pathlib.Path(args.carpeta) if args.carpeta else default_folder("humo")[0]
    if not args.pedido:
        # El pedido del setup: en la carpeta de investigaciones del proyecto o, si se guardó antes de configurarla, en
        # la de siempre.
        candidates = [default_folder("setup")[0] / "pedido.json", pathlib.Path(DEFAULT_INVESTIGATIONS) / "setup" / "pedido.json"]
        args.pedido = str(next((path for path in candidates if path.is_file()), candidates[0]))
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
                                 corridas=1, sin_comprimir=False, red_obligatoria=True, sin_red=args.sin_red)
    root = project_root(folder).resolve()
    today = datetime.date.today().isoformat()
    try:
        cmd_capturar(capture, plan)
    except PerfError as error:
        # El bloque de AGENTS.md no puede seguir diciendo que el humo pasó (o que hay red) si esta corrida lo desmiente.
        # Una precondición que no es del setup (sin dispositivo, el dispositivo caliente) no es un humo fallido: no
        # llegó a correr, y lo anotado antes sigue valiendo.
        no_network = "RED SIN MEDIR" in str(error)
        note = ""
        if no_network or not isinstance(error, Precondicion):
            note = update_agents_state(root, humo="falló el %s" % today,
                                       http="sin medir: la prueba de humo del %s no trajo ninguna" % today if no_network
                                       else None)
        if note:
            print(note)
        raise
    result = getattr(capture, "resultado", None) or {}
    # Un humo que no vio la red (--sin-red, o sin instrumentación de red) no pisa un "sí" que ya anotó otra corrida.
    agents = read_agents(root)
    section = performance_section(agents) if agents is not None else None
    known = (agents_state(agents[section[0]:section[1]]).get("secciones HTTP") or "") if section else ""
    http = ("sí (prueba de humo, %s)" % today if result.get("http") else None if known.startswith("sí") else
            "no exigidas (humo --sin-red, %s)" % today if args.sin_red else None)
    note = update_agents_state(root, humo="pasó el %s" % today, http=http)
    if note:
        print(note)
    nuevo = ["nuevo", "--receta", "arranque-frio", "--paquete", args.paquete, "--serial", serial, "--carpeta",
             shlex.quote(shown_path(investigations_base(root) / "arranque-frio" / datetime.date.today().isoformat(),
                                    root))]
    if args.instalar:
        nuevo += ["--instalar", json.dumps(args.instalar, ensure_ascii=False)]
    recipe = "cd %s && python3 -I %s %s%s" % (q(root), q(HERE / "perf.py"), " ".join(nuevo),
                                              " [--red si la primera pantalla carga de la red]")
    request = read_request(args.pedido)
    chat_line = "Chat nuevo · Modelo: %s · Esfuerzo: medio" % model_name(plan, "intermedio")
    openers = ["Abrir (Terminal, %s): %s%s" % (tool, command, " · %s" % note if note else "")
               for tool, command, note in chat_openers(plan, root, "intermedio", "medio")]
    if missing_setup:
        print("⚠ Antes de seguir: %s" % missing_setup)
    if request:
        print("Siguiente · sesión 1 (ficha y plan) del flujo que pediste en el setup · %s" % chat_line)
        for line in openers:
            print("  " + line)
        print("  Texto: \"%s\"" % session1_prompt(request, serial))
        print("  Tú: %s (el flujo sale de %s; es un chat nuevo, no el del setup)." % (CHAT_YOU, args.pedido))
        print("Solo si lo que quieres medir es el arranque en frío (receta, sin sesión 1) · Terminal (sin chat):")
        print("  %s" % recipe)
        print("  Tú: nada más; arma el plan e imprime los comandos para medir.")
    else:
        print("Siguiente, según lo que se va a investigar:")
        print("  · Una pantalla o un flujo · %s" % chat_line)
        for line in openers:
            print("    " + line)
        print("    Texto: \"%s\"" % session1_prompt({"flujo": "<flujo: de dónde a dónde y qué debe verse al final>"}, serial))
        print("    Tú: completa el flujo entre <> y %s." % CHAT_YOU)
        print("  · Solo si lo que quieres medir es el arranque en frío (receta, sin sesión 1) · Terminal (sin chat):")
        print("    %s" % recipe)
        print("    Tú: nada más; arma el plan e imprime los comandos para medir.")


def default_folder(name):
    """(carpeta, de dónde sale) de una investigación sin --carpeta: `<carpeta de investigaciones>/<nombre>/<fecha>`,
    con la carpeta de investigaciones de AGENTS.md o, sin ella, reports/perf. Relativa a la carpeta actual si se puede."""
    root = project_root(pathlib.Path.cwd()).resolve()
    configured = perf_folders(root)["investigaciones"]
    folder = (configured or root / DEFAULT_INVESTIGATIONS) / name
    inside = under(lexical(folder), lexical(pathlib.Path.cwd()))
    if inside is None:
        inside = under(lexical(folder), pathlib.Path.cwd().resolve())
    return (inside if inside is not None else folder), \
        "la carpeta de investigaciones de AGENTS.md" if configured else "por defecto"


def cmd_nuevo(args):
    if args.carpeta:
        folder = pathlib.Path(args.carpeta)
        root = project_root(folder).resolve()
        configured = perf_folders(root)["investigaciones"]
        if configured and under(lexical(folder), lexical(configured)) is None \
                and under(folder.resolve(), configured.resolve()) is None:
            print("· AGENTS.md configura la carpeta de investigaciones en %s: esta investigación queda fuera de ella "
                  "(sin --carpeta, `nuevo` la crea ahí)" % shown_path(configured, root))
    else:
        folder, origin = default_folder(pathlib.Path(
            "arranque-frio" if args.receta == "arranque-frio" else slug(args.flujo)) / datetime.date.today().isoformat())
        print("✔ Carpeta de la investigación: %s (%s)" % (folder, origin))
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
                     "mejoras": [], "receta": "arranque-frio"})
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
                             .replace("{{CARPETA}}", str(folder)).replace("{{PERF}}", str(HERE / "perf.py")), encoding="utf-8")
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


FINGERPRINT = re.compile(r"^[ \t]*(?://|<!--) hb-performance fingerprint: ([0-9a-f]{16})(?: -->)?[ \t]*\n", re.M)


FINGERPRINT_TOKEN = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|//[^\n]*|\w+|[^\w\s]")


def fingerprint(text):
    """Huella de un archivo generado que no depende del formato: sus tokens en orden (cada literal entre comillas y
    cada comentario de línea es uno solo, con sus espacios), sin los espacios ni los saltos de línea que los separan,
    sin la coma final antes de un cierre y con los imports ordenados. Así el formateador del proyecto (saltos de línea, comas finales, orden de
    los imports) no la cambia, y una edición a mano sí, también si solo reordena código o cambia un literal. No cuenta
    la línea que guarda la huella."""
    lines = FINGERPRINT.sub("", text).split("\n")
    imports = sorted(line.strip() for line in lines if line.lstrip().startswith("import "))
    tokens = [token.rstrip() for token in FINGERPRINT_TOKEN.findall(
        "\n".join(line for line in lines if not line.lstrip().startswith("import ")))]
    kept = [token for index, token in enumerate(tokens)
            if not (token == "," and index + 1 < len(tokens) and tokens[index + 1] in (")", "]", "}", ">"))]
    return hashlib.sha256("\x00".join(imports + ["\x01"] + kept).encode("utf-8")).hexdigest()[:16]


def stamp(text):
    """El texto con su huella en la línea que sigue al encabezado "Generated by hb-performance" (reemplaza la que
    tenga). `instrumentar --actualizar` la compara para saber si alguien editó el archivo después de generarlo."""
    text = FINGERPRINT.sub("", text)
    lines = text.split("\n")
    index = next((i for i, line in enumerate(lines) if GENERATED in line), None)
    if index is None:
        return text
    xml = lines[index].lstrip().startswith("<!--")
    mark = "<!-- hb-performance fingerprint: %s -->" if xml else "// hb-performance fingerprint: %s"
    lines.insert(index + 1, mark % fingerprint(text))
    return "\n".join(lines)


def generated_state(current, rendered):
    """Cómo está un archivo generado frente a la plantilla de esta versión: 'igual' (mismo contenido, aunque cambie el
    formato), 'intacto' (otra versión de la plantilla, sin ediciones: su huella coincide), 'editado' (la huella no
    coincide: alguien lo cambió a mano) o 'sin huella' (lo generó una versión anterior a 0.8.0 y no se puede saber)."""
    if fingerprint(current) == fingerprint(rendered):
        return "igual"
    stored = FINGERPRINT.search(current)
    if not stored:
        return "sin huella"
    return "intacto" if stored.group(1) == fingerprint(current) else "editado"


def backup_path(target):
    """Dónde guardar la copia de un archivo generado antes de pisarlo: <archivo>.orig, o .orig2, .orig3… si ya hay una."""
    candidate, number = target.with_name(target.name + ".orig"), 1
    while candidate.exists():
        number += 1
        candidate = target.with_name("%s.orig%d" % (target.name, number))
    return candidate


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
    "red_hilt": """// En CADA lugar donde se arma un OkHttpClient (Hilt o Dagger): inyecta el set y llama al helper, una línea por
// builder. Con el set vacío (release) el helper no hace nada.
// Kotlin:
@Provides fun okHttp(@PerfEventListeners factories: Set<@JvmSuppressWildcards EventListener.Factory>): OkHttpClient =
    PerfHooks.applyEventListener(OkHttpClient.Builder(), factories)
        .build()
// Java (un módulo de DI escrito en Java):
@Provides OkHttpClient okHttp(@PerfEventListeners Set<EventListener.Factory> factories) {
    OkHttpClient.Builder builder = new OkHttpClient.Builder();
    PerfHooks.applyEventListener(builder, factories);
    return builder.build();
}
// El comodín entre Kotlin y Java: para Dagger, Set<EventListener.Factory> y Set<? extends EventListener.Factory> son
// tipos distintos. En Kotlin, la inyección lleva @JvmSuppressWildcards (como arriba); en Java se declara
// Set<EventListener.Factory> exacto. Si no coinciden, Dagger dice que falta el binding del set.
// imports: {{PAQUETE}}.PerfEventListeners, {{PAQUETE}}.PerfHooks, okhttp3.EventListener""",
    "red_sinhilt": """// En CADA OkHttpClient.Builder del proyecto, antes de build(), una línea:
PerfHooks.okHttp(builder) // Kotlin
PerfHooks.applyOkHttp(builder); // Java
// import {{PAQUETE}}.PerfHooks
// Si el cliente se arma con un set de factories de DI propio (Dagger sin Hilt): PerfHooks.applyEventListener(builder, factories).""",
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
TEST_SOURCE_SET = re.compile(r"(?:test|androidTest|testFixtures)[A-Z]\w*")  # testDebug, androidTestDemoDebug…
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
# Un cliente derivado de otro (`cliente.newBuilder()`): hereda el listener de su cliente base. Solo cuenta en archivos
# que nombran OkHttpClient y no en las líneas que derivan otra cosa (una Request, una URL, una Response, Retrofit).
OKHTTP_DERIVED = re.compile(r"\.\s*newBuilder\s*\(\s*\)")
NOT_A_CLIENT = re.compile(r"request|url|response|retrofit|headers|body", re.I)
# El builder pasa por el gancho de red: el helper de PerfHooks o, en un archivo que recibe el set de la skill
# (@PerfEventListeners) o nombra su listener, la factory puesta a mano. Otra factory del proyecto no cuenta.
OKHTTP_WIRED = re.compile(r"\bPerfHooks\b[^\n;]*?\b(?:okHttp|getOkHttp|applyOkHttp|applyEventListener)\b")
OKHTTP_FACTORY = re.compile(r"\beventListenerFactory\b")
OKHTTP_OWN_SET = re.compile(r"\bPerfEventListeners\b|\bTraceEventListener\b")
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
        dirs[:] = sorted(d for d in dirs if d not in SCAN_SKIP and not d.startswith(".") and not TEST_SOURCE_SET.fullmatch(d)
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
    Devuelve {"ganchos", "archivos", "okhttp", "cableado", "vistas", "buildconfig"}; "cableado" tiene, por archivo que
    arma un cliente, sus builders, los clientes derivados con `.newBuilder()` y cuántas veces llama al gancho de red."""
    hooks, multi, files, builders, wiring = [], set(), 0, [], []
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
        own = [text.count("\n", 0, builder.start()) + 1 for builder in OKHTTP_BUILDER.finditer(text)]
        builders += [(relative, number) for number in own]
        derived = []
        if "OkHttpClient" in text:
            for found in OKHTTP_DERIVED.finditer(text):
                line_start = text.rfind("\n", 0, found.start()) + 1
                if not NOT_A_CLIENT.search(text[line_start:found.start()]):
                    derived.append(text.count("\n", 0, found.start()) + 1)
        if own or derived:
            calls = len(OKHTTP_WIRED.findall(text)) \
                + (len(OKHTTP_FACTORY.findall(text)) if OKHTTP_OWN_SET.search(text) else 0)
            wiring.append({"archivo": relative, "builders": own, "derivados": derived, "llamadas": calls})
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
    return {"ganchos": hooks, "archivos": files, "okhttp": builders, "cableado": wiring, "vistas": views,
            "buildconfig": build_config}


def unwired_builders(wiring):
    """(builders que no pasan por el gancho de red, clientes derivados por revisar), como textos "archivo:línea". Un
    archivo cuenta como cableado si llama al gancho al menos tantas veces como builders tiene; si no, se listan todos
    los suyos. Es una búsqueda por texto: un builder cableado desde otro archivo se lista igual, y hay que mirarlo."""
    missing, derived = [], []
    for item in wiring:
        if len(item["builders"]) > item["llamadas"]:
            missing += ["%s:%d" % (item["archivo"], number) for number in item["builders"]]
        if not item["llamadas"]:
            derived += ["%s:%d" % (item["archivo"], number) for number in item["derivados"]]
    return missing, derived


def wiring_report(root, patterns=None):
    """El cableado de red del proyecto (scan_sources, con los módulos que settings.gradle incluye desde fuera), para
    decir qué builders no llaman al gancho."""
    patterns = read_no_leer(root) if patterns is None else patterns
    outside, _ = external_roots(root, patterns)
    return unwired_builders(scan_sources(root, patterns, outside)["cableado"])


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


def find_generated(root, name):
    """True si bajo la raíz del proyecto hay un archivo con ese nombre generado por `instrumentar`."""
    for current, dirs, files in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d not in ("build", "node_modules", "reports", "out") and not d.startswith(".")]
        if name in files and is_generated(os.path.join(current, name)):
            return True
    return False


def plan_expects_network(plan, flow):
    """True si el plan declara la red: una métrica `red…` entre las principales o las de las mejoras, una marca de red
    (HTTP, TTFB, QUEUE, CONN) en la ventana, una métrica de usuario o un tramo, o un tramo `solo_red`."""
    names = list(plan.get("principales") or []) + [str(m.get("metrica") or "") for m in plan.get("mejoras") or []]
    if any(name.startswith(("red_", "red ")) or " red_" in name for name in names):
        return True
    segments = [s for s in flow.get("segmentos") or [] if isinstance(s, dict)]
    if any(s.get("solo_red") for s in segments):
        return True
    specs = list(flow.get("metricas_usuario") or []) + segments + [flow.get("ventana") or {}]
    return any(str((spec.get(side) or {}).get("marca") or "").startswith(("HTTP", "TTFB", "QUEUE", "CONN"))
               for spec in specs if isinstance(spec, dict) for side in ("desde", "hasta"))


def network_gap(root, plan, flow, names, detail=False):
    """El aviso de "red sin medir": la corrida no trajo ninguna sección HTTP aunque el proyecto tiene la instrumentación
    de red generada o el plan declara la red. Dice la causa probable y qué builders no llaman al gancho. '' si no aplica.
    Con `detail`, (aviso, builders sin conectar como "archivo:línea")."""
    if any(name.startswith("HTTP ") for name in names):
        return ("", []) if detail else ""
    generated = find_generated(root, "TraceEventListener.kt")
    if not generated and not plan_expects_network(plan, flow):
        return ("", []) if detail else ""
    missing, derived = wiring_report(root)
    why = "el proyecto tiene la instrumentación de red generada" if generated else "el plan usa métricas o marcas de red"
    text = ("RED SIN MEDIR: la corrida no tiene ninguna sección HTTP y %s. Causa probable: el listener no está conectado a "
            "ningún OkHttpClient.Builder. " % why)
    if missing:
        text += "Builders que no llaman al gancho de PerfHooks (%d): %s%s. Conecta cada uno (setup.md · Red: conectar " \
                "cada builder), instala de nuevo y repite." % (len(missing), ", ".join(missing[:10]), " …" if len(missing) > 10 else "")
    else:
        text += ("No encontré builders sin conectar en el código que pude leer: revisa que el build instalado sea el de la "
                 "variante medida, que el cliente no se arme en una librería ya compilada (setup.md · OkHttp dentro de una "
                 "librería publicada) y que este recorrido de verdad haga alguna llamada.")
    if derived:
        text += " Clientes derivados con .newBuilder() por revisar (heredan el listener de su cliente base): %s%s." % (
            ", ".join(derived[:5]), " …" if len(derived) > 5 else "")
    return (text, missing) if detail else text


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
        tests += [("TraceEventListenerTest.kt", "TraceEventListenerTest.kt"), ("PerfHooksTest.kt", "PerfHooksTest.kt")]
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
    pending, blocked, created = [], [], []
    for source, target in plan:
        rendered = stamp(render_template(source.read_text(encoding="utf-8"), args.paquete, tags))
        if target.exists():
            if args.actualizar and is_generated(target):
                current = target.read_text(encoding="utf-8", errors="replace")
                state = generated_state(current, rendered)
                if state == "igual":
                    if not FINGERPRINT.search(current):  # la misma plantilla, generada antes de 0.8.0: solo gana su huella
                        target.write_text(stamp(current), encoding="utf-8")
                    print("= al día: %s" % target)
                elif state == "intacto":
                    target.write_text(rendered, encoding="utf-8")
                    print("~ actualizado: %s" % target)
                elif args.forzar:
                    copy = backup_path(target)
                    copy.write_text(current, encoding="utf-8")
                    target.write_text(rendered, encoding="utf-8")
                    print("~ actualizado con --forzar: %s (lo que había quedó en %s)" % (target, copy))
                else:
                    blocked.append(target)
                    print("✖ no se actualiza: %s (%s)" % (target, "lo editaron a mano después de generarlo" if state == "editado"
                                                          else "lo generó una versión anterior, sin huella: no se puede "
                                                               "saber si lo editaron"))
            elif target.suffix == ".xml":
                lacks = target.parent.name == variant and not in_gradle \
                    and "<profileable" not in target.read_text(encoding="utf-8", errors="ignore")
                print("= ya existe, no se toca: %s (agrega el <provider> de abajo%s)" % (
                    target, " y <profileable android:shell=\"true\" />" if lacks else ""))
                pending.append("manifest")
            else:
                print("= ya existe, no se toca: %s%s" % (target, "" if is_generated(target) else " (no lo generó la skill)"))
            continue
        if args.actualizar:  # los nuevos se escriben al final: pueden depender de uno que quedó sin actualizar
            created.append((target, rendered))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print("+ %s" % target)
    for target, rendered in created:
        if blocked:
            print("· sin crear todavía: %s (es nuevo en esta versión y puede usar lo que falta actualizar)" % target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print("+ %s" % target)
    if blocked:
        print("⚠ %d archivo%s no se actualiz%s: difiere%s de lo que generó la skill y --actualizar no pisa un cambio hecho a "
              "mano. Revisa cada uno (git diff, o contra su plantilla en assets/instrumentacion) y, si aceptas reemplazarlo, "
              "repite con --actualizar --forzar: pisa el archivo y deja lo que había en <archivo>.orig, para volver a "
              "aplicar lo tuyo. Bórralo después: no se commitea. Hasta entonces la instrumentación queda a medias: lo nuevo "
              "de esta versión (los archivos que no se crearon, o el helper que nombra el fragmento de red) puede faltar."
              % ((len(blocked), "", "ó", "") if len(blocked) == 1 else (len(blocked), "s", "aron", "n")))
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
        missing, derived = unwired_builders(scan["cableado"])
        found = ["// Builders que todavía no llaman al gancho (%d): %s%s" % (
            len(missing), ", ".join(missing[:12]), " …" if len(missing) > 12 else "")] if missing else \
            ["// No quedan builders sin cablear en el código que pude leer."]
        if derived:
            found.append("// Clientes derivados con .newBuilder() (heredan el listener de su cliente base: cablea el base): %s%s"
                         % (", ".join(derived[:8]), " …" if len(derived) > 8 else ""))
        found.append("// Lo aplicas tú en esta sesión, una edición por archivo, y lo compruebas con la búsqueda de setup.md · "
                     "Red: conectar cada builder: sin esto no sale ninguna sección HTTP y la prueba de humo falla.")
        snippets.append(("2. Red: cada OkHttpClient pasa por el gancho",
                         SNIPPETS["red_hilt" if hilt else "red_sinhilt"] + "\n" + "\n".join(found)))
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

MAPPING_HELP = ("mapping.txt de R8 de la variante medida, para desofuscar; si no, el 'mapping' del plan o el de la variante "
                "del comando 'instalar'. Pasado así se usa aunque no se pueda verificar contra el APK instalado")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Captura, métricas, diagnóstico, comparación y reporte de hb-performance.")
    parser.add_argument("--version", action="version", version="hb-performance %s" % VERSION)
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("nuevo", help="crea la carpeta de una investigación con plan.json y estado.md")
    p.add_argument("--carpeta", help="por ejemplo reports/perf/arranque-frio/AAAA-MM-DD; sin ella, <carpeta de "
                                     "investigaciones de AGENTS.md, o reports/perf>/<flujo>/<fecha>")
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
    p.add_argument("--carpeta", help="dónde queda la traza de prueba (por defecto, humo/ en la carpeta de "
                                     "investigaciones de AGENTS.md, o reports/perf/humo)")
    p.add_argument("--actividad", help="actividad de inicio (paquete/.Actividad); si no, la del launcher")
    p.add_argument("--espera", type=float, default=5)
    p.add_argument("--instalar", help="comando que compila e instala el build de profiling (se repite en el paso siguiente)")
    p.add_argument("--pedido",
                   help="el flujo que se pidió en el setup ({\"flujo\", \"llegar\"}): con él, el paso siguiente es el chat "
                        "de la sesión 1 ya escrito")
    p.add_argument("--hz", type=int)
    p.add_argument("--tp")
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--sin-red", dest="sin_red", action="store_true",
                   help="no exige secciones HTTP: para una app cuyo arranque no hace ninguna llamada de red")
    p.set_defaults(func=cmd_humo)

    p = sub.add_parser("siguiente", help="el paso que sigue, con sus comandos completos (también en estado.md)")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--flujo")
    p.set_defaults(func=cmd_siguiente)

    p = sub.add_parser("consumo", help="anota el costo de una sesión en la tabla Consumo de estado.md")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--sesion", required=True, help="por ejemplo '0 · setup' o '3 · M1'")
    p.add_argument("--costo", help="lo que muestre tu herramienta: '1.05 USD', '38k tokens' (solo un monto en USD o "
                                   "los AI Credits entran al total en USD)")
    p.add_argument("--creditos", help="AI Credits de GitHub Copilot (/usage); se suman al total como USD (1 AI Credit = "
                                      "%s USD)" % fmt(AI_CREDIT_USD))
    p.add_argument("--tokens-entrada", dest="tokens_entrada", help="tokens de entrada del chat (45000, 45k)")
    p.add_argument("--tokens-cache", dest="tokens_cache", help="tokens leídos de caché")
    p.add_argument("--tokens-salida", dest="tokens_salida", help="tokens de salida")
    p.add_argument("--modelo", help="modelo usado en ese chat")
    p.add_argument("--esfuerzo", help="esfuerzo de razonamiento del chat (bajo, medio, alto)")
    p.add_argument("--pasos", help="requests o pasos del agente, si tu herramienta los muestra")
    p.set_defaults(func=cmd_consumo)

    p = sub.add_parser("decidir", help="registra la decisión del usuario sobre las mejoras del plan")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--aprobar", help="ids separados por coma (- es ninguno)")
    p.add_argument("--descartar", help="ids separados por coma (- es ninguno)")
    p.add_argument("--pendiente", help="ids separados por coma (- es ninguno)")
    p.add_argument("--aplicada", help="ids que la sesión 3 ya aplicó (la usa el agente al terminar la mejora)")
    p.add_argument("--archivos", help="con --aplicada (un solo id): los archivos que cambió la mejora, separados por coma "
                                      "y relativos a --repo; perf.py guarda su diff en <carpeta>/cambios/ para el reporte")
    p.add_argument("--repo", help="con --archivos: el repo donde están esos archivos (por defecto, la raíz del proyecto); "
                                  "con varios repos, un --aplicada por repo")
    p.add_argument("--profundidad", choices=["riguroso", "triage"],
                   help="cambia la profundidad del plan sin editar plan.json: de triage a riguroso para aplicar una mejora "
                        "(el paso siguiente pide completar antes y medir control)")
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
    p.add_argument("--sin-compilar", action="store_true",
                   help="no fija la compilación de ART (con --prueba ya es así: no hace falta pasarlo)")
    p.add_argument("--compilar", action="store_true",
                   help="con --prueba: fija la compilación de ART igual que en una fase (por defecto la prueba no compila)")
    p.add_argument("--recompilar", action="store_true",
                   help="compila aunque la app ya tenga la compilación completa de esta misma instalación")
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
    p.add_argument("--mapping", help=MAPPING_HELP)
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
    p.add_argument("--mapping", help=MAPPING_HELP)
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
    p.add_argument("--mapping", help=MAPPING_HELP)
    p.set_defaults(func=cmd_consulta)

    p = sub.add_parser("salidas", help="por qué se cerró la app: sus últimas salidas según el sistema (Android 11 o superior)")
    p.add_argument("--paquete", help="applicationId; si no, el del plan de --carpeta")
    p.add_argument("--carpeta", help="carpeta de la investigación: toma de su plan el paquete, el serial y el mapping")
    p.add_argument("--serial", help="dispositivo (obligatorio con más de uno conectado)")
    p.add_argument("--desde", help="solo las salidas desde esa hora del dispositivo: 'AAAA-MM-DD' o 'AAAA-MM-DD HH:MM'")
    p.add_argument("--limite", type=int, default=10, help="cuántas salidas, de la más reciente hacia atrás (10)")
    p.add_argument("--mapping", help=MAPPING_HELP)
    p.set_defaults(func=cmd_salidas)

    p = sub.add_parser("resumen", help="estadísticas por fase y avisos; escribe resumen.md y la sección Métricas de "
                                       "estado.md en la carpeta del CSV",
                       description="Imprime las estadísticas por fase y los avisos de estabilidad. Además ESCRIBE dos "
                                   "archivos en la carpeta del CSV: resumen.md (todas las métricas) y, si hay un estado.md "
                                   "con su bloque, la sección Métricas de estado.md. Con --solo-imprimir no escribe nada.")
    p.add_argument("csv", help="metricas.csv de la investigación; resumen.md y estado.md se escriben en su misma carpeta")
    p.add_argument("--todo", action="store_true", help="todas las métricas, no solo las principales")
    p.add_argument("--solo-imprimir", dest="solo_imprimir", action="store_true",
                   help="solo imprime la tabla: no escribe resumen.md ni toca estado.md")
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

    p = sub.add_parser("pausa", help="desde un recorrido: muestra un texto en la terminal, con un pitido, y espera Enter "
                                     "(x + Enter descarta la corrida); sale con 1 si se descarta y con 3 si no hay terminal")
    p.add_argument("mensaje", nargs="*", help="lo que la persona tiene que hacer antes de presionar Enter")
    p.set_defaults(func=cmd_pausa)

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
                   help="sobrescribe los archivos que generó la skill (los que llevan su encabezado); nunca los del proyecto "
                        "ni, sin --forzar, uno generado que alguien editó a mano")
    p.add_argument("--forzar", action="store_true",
                   help="con --actualizar: pisa también los archivos generados que se editaron a mano (o que no tienen "
                        "huella) y deja lo que había en <archivo>.orig")
    p.set_defaults(func=cmd_instrumentar)

    args = parser.parse_args(argv)
    reset_guide(sys.argv[1:] if argv is None else argv)
    # El único lugar que cierra un fallo: qué pasó, qué quedó guardado y el comando para seguir (guide_lines).
    try:
        args.func(args)
    except PerfError as error:
        print("\n".join(["✖ %s" % error] + guide_lines(error)), file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        print("\n".join(["", "✖ interrumpido (Ctrl+C): el comando no terminó; lo que estaba a medias (una corrida, una "
                             "traza) no cuenta"] + guide_lines()), file=sys.stderr)
        return 130
    except subprocess.TimeoutExpired as error:
        tool = pathlib.Path(str(error.cmd[0] if isinstance(error.cmd, (list, tuple)) else error.cmd).split(" ")[0]).name
        print("\n".join(["✖ %s no respondió en %d s: si es adb, el dispositivo se desconectó, se bloqueó o quedó sin "
                         "responder. Revisa el cable y que `adb devices` lo liste como 'device'"
                         % (tool, error.timeout)] + guide_lines()), file=sys.stderr)
        return Precondicion.code
    except Exception as error:  # un fallo que perf.py no esperaba: igual termina con cómo seguir
        if os.environ.get("HB_PERF_DEBUG"):
            raise
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print("\n".join(["✖ error inesperado en perf.py (%s: %s; línea %d). Suele ser un archivo de la carpeta con un "
                         "formato que no esperaba; con HB_PERF_DEBUG=1 delante del comando sale la traza completa"
                         % (type(error).__name__, error, frame.lineno)] + guide_lines()), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
