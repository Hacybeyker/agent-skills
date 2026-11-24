#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""producto.py — herramienta de hb-product (Python 3.8+, solo librería estándar).

Lleva el registro de una idea de app: fuentes, hallazgos, matriz de competidores, diferenciadores, puntaje,
escenarios de ingresos, puertas y decisiones. Todo lo que es una cuenta o un veredicto lo calcula este script;
el agente investiga, escribe los entregables e interpreta.

Ejemplos:
  python3 -I producto.py nuevo --nombre "Riego en turnos" --meta 300 --semanas 6
  python3 -I producto.py fuente --linea demanda --url https://ejemplo.com/a --publicada 2026-05 --tipo medido \
      --peldano 4 --resumen "Qué dice, en 3 líneas como máximo"
  python3 -I producto.py hallazgo --linea demanda --texto "…" --fuentes S-DEM-1,S-DEM-2,S-DEM-3 --critico
  python3 -I producto.py siguiente
Cada comando tiene `--help`. La carpeta del producto es `--carpeta`, la línea `Carpeta:` de la sección
`## Producto` de AGENTS.md o, si no hay ninguna, ./product.
"""
import argparse
import contextlib
import csv
import io
import json
import math
import os
import re
import shlex
import shutil
import sys
import time
import unicodedata
from datetime import date, datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.1.0"
FORMATO = 1
CARPETA_DEFECTO = "product"
GUION = os.path.abspath(__file__)
PLANTILLAS = Path(GUION).parent.parent / "assets" / "plantillas"
PENDIENTE = "<por completar"
CANDADO = ".producto.lock"
REPORTE = "reporte.html"
TABLERO = "index.html"

# línea de investigación → (código de sus IDs, sesión que la escribe)
LINEAS = {
    "competencia": ("COM", "1a"),
    "voz-del-usuario": ("VOZ", "1b"),
    "demanda": ("DEM", "1c"),
    "monetizacion": ("MON", "1d"),
    "politicas": ("POL", "1e"),
    "diferenciacion": ("DIF", "1g"),
    "estrategia": ("EST", "2"),
    "validacion": ("VAL", "3"),
}
EXIGEN_MEDIDO = ("demanda", "monetizacion")
# `oficial`: el texto primario de una norma (política de una tienda, ley, reglamento). Una sola basta para un hallazgo
# de la línea políticas, y cuenta como vigente si se consultó dentro de la ventana: rige mientras no la reemplacen.
TIPOS_FUENTE = ("medido", "usuario", "terceros", "opinion", "oficial")
BASTA_OFICIAL = ("politicas",)
SIN_FECHA = ("desconocida", "sin-fecha")  # `sin-fecha` es el nombre anterior de `desconocida`
# Sustitutos (peldaño 4): cómo se resuelve hoy la necesidad sin una app de este tipo
SUSTITUTOS = {"nativo": "viene con el sistema", "gratuito": "gratuito", "pago": "de pago"}
RESUELVE = {"si": "resuelve la necesidad", "parcial": "la resuelve en parte", "no": "no la resuelve"}
TIPOS_IDEA = ("existente", "variante", "nueva")
NIVELES = ("sin evidencia", "baja", "media", "alta")
# peldaño de la escalera de analogía → (nombre, confianza máxima)
PELDANOS = {1: ("directo", 3), 2: ("variante", 3), 3: ("análogo", 2), 4: ("sustituto", 2),
            5: ("necesidad de fondo", 2), 6: ("hipótesis general", 1)}
VECTORES = ("usabilidad", "rendimiento", "precio", "anuncios", "funcionalidades", "idioma", "privacidad",
            "sin-conexion", "accesibilidad", "diseno", "segmento", "plataforma")
# vector medible → columnas de la matriz que lo comprueban
VECTOR_COLUMNAS = {
    "rendimiento": ("tamano_mb",), "precio": ("precio", "modelo"), "anuncios": ("anuncios",),
    "idioma": ("idiomas",), "privacidad": ("permisos",), "sin-conexion": ("sin_conexion",),
    "accesibilidad": ("accesibilidad",), "diseno": ("actualizada",), "plataforma": ("plataformas",),
}
COLUMNAS_MATRIZ = ("descargas", "nota", "actualizada", "precio", "modelo", "anuncios", "tamano_mb", "idiomas",
                   "permisos", "sin_conexion", "accesibilidad", "plataformas", "funciones", "traccion")
CRITERIOS_PUNTAJE = ("demanda", "monetizacion", "facilidad", "riesgo", "diferenciacion")
CRITERIOS_DEFECTO = {
    "puntaje_minimo": 17,          # P1, idea existente o variante (de 25)
    "puntaje_minimo_nueva": 15,    # P1, idea nueva
    "vigencia_meses": 18,          # ventana en la que una fuente cuenta para triangular
    "fuentes_minimas": 3,          # fuentes independientes de un hallazgo clave
    "analogos_minimos": 2,         # análogos con tracción (peldaño 2 o 3) de una idea nueva
    "traccion_descargas": 100000,  # descargas desde las que un competidor o un análogo tiene tracción
    "meta_ingresos_mes": 0,        # meta de ingresos netos al mes (opcional; 0 = sin meta)
    "meta_obligatoria": "no",      # "si": la meta es criterio de la puerta 2; "no": solo referencia
    "moneda": "USD",
    "presupuesto_semanas": 0,      # semanas para construir el MVP (sesión 0)
}
PRESUPUESTO = {"busquedas": 15, "lecturas": 10}
PRESUPUESTO_NUEVA = {"busquedas": 20, "lecturas": 12}
AMPLITUD_ANALOGIA = 0.5  # un escenario por analogía abre el rango: pesimista × 0,5 y optimista × 1,5
RICE_CONFIANZA = {3: 100, 2: 80, 1: 50, 0: 0}  # confianza del hallazgo → porcentaje de RICE

# Modelo y esfuerzo de cada nivel (references/modelos.md). Los nombres se cambian con `modelos`.
MODELOS = {"intermedio": "Sonnet 5.5", "alto": "Opus 5.5"}
ESFUERZO = {"intermedio": "medio", "alto": "alto"}
# Herramientas que `siguiente` sabe abrir desde la terminal: (clave, nombre, comando). {modelo} es el id del modelo en
# esa herramienta y {esfuerzo}, el nivel en inglés (flags --model y --effort de cada CLI).
HERRAMIENTAS_CHAT = (("claude", "Claude Code", "claude --model {modelo} --effort {esfuerzo}"),
                     ("copilot", "GitHub Copilot CLI", "copilot --model {modelo} --effort {esfuerzo}"))
ESFUERZO_CLI = {"bajo": "low", "medio": "medium", "alto": "high"}
FAMILIAS_CLAUDE = ("haiku", "sonnet", "opus", "fable")
USD_POR_CREDITO = 0.01  # un AI Credit de GitHub Copilot (documentación de facturación de GitHub)

# Cobertura: qué dimensiones del objetivo (00-idea.md) necesita cada línea de investigación
DIMENSIONES = {"mercados": "mercado", "idiomas": "idioma", "tiendas": "tienda"}
COBERTURA_LINEAS = {
    "competencia": ("mercados", "tiendas"), "voz-del-usuario": ("idiomas", "tiendas"), "demanda": ("mercados",),
    "monetizacion": ("mercados",), "politicas": ("mercados", "tiendas"),
}
MOTIVOS_VACIO = {"herramienta": "límite de las herramientas", "sin-resultados": "se buscó y no hay",
                 "presupuesto": "sin presupuesto de búsquedas"}
# Encabezados de un CSV de reseñas (normalizados): fecha, estrellas, texto e idioma. Las columnas de autor nunca se leen.
COLUMNAS_CSV = {
    "fecha": ("fecha", "date", "reviewdate", "reviewsubmitdateandtime", "submitdate", "at", "createdat", "updated",
              "updatedat", "timestamp", "time", "fechadelaresena"),
    "estrellas": ("estrellas", "rating", "stars", "starrating", "score", "nota", "puntuacion", "valoracion"),
    "texto": ("texto", "text", "review", "reviewtext", "content", "body", "comentario", "resena", "opinion",
              "comment"),
    "idioma": ("idioma", "language", "lang", "reviewerlanguage", "locale"),
}

SESIONES = [
    {"id": "0", "nombre": "Idea", "modelo": "intermedio", "archivo": "00-idea.md", "lee": "SKILL.md · Sesión 0"},
    {"id": "1a", "nombre": "Competencia", "modelo": "intermedio", "archivo": "01-investigacion/competencia.md",
     "lee": "references/investigacion.md"},
    {"id": "1b", "nombre": "Voz del usuario", "modelo": "intermedio",
     "archivo": "01-investigacion/voz-del-usuario.md", "lee": "references/investigacion.md"},
    {"id": "1c", "nombre": "Demanda", "modelo": "intermedio", "archivo": "01-investigacion/demanda.md",
     "lee": "references/investigacion.md"},
    {"id": "1d", "nombre": "Monetización", "modelo": "intermedio", "archivo": "01-investigacion/monetizacion.md",
     "lee": "references/investigacion.md"},
    {"id": "1e", "nombre": "Políticas y riesgos", "modelo": "intermedio",
     "archivo": "01-investigacion/politicas.md", "lee": "references/investigacion.md"},
    {"id": "1g", "nombre": "Diferenciación", "modelo": "alto", "archivo": "01-investigacion/diferenciacion.md",
     "lee": "references/diferenciacion.md"},
    {"id": "1f", "nombre": "Síntesis", "modelo": "alto", "archivo": "01-sintesis.md",
     "lee": "references/puntaje.md y references/puertas.md"},
    {"id": "2", "nombre": "Estrategia", "modelo": "alto", "archivo": "02-estrategia.md",
     "lee": "references/estrategia.md"},
    {"id": "3", "nombre": "Validación documental", "modelo": "alto", "archivo": "03-validacion.md",
     "lee": "references/validacion.md"},
    {"id": "4", "nombre": "PRD", "modelo": "alto", "archivo": "04-prd.md", "lee": "references/prd.md"},
]
SESION = {s["id"]: s for s in SESIONES}
# de qué depende cada sesión y cada puerta (P1, P2, P3)
DEPENDE = {
    "0": [], "1a": ["0"], "1b": ["0"], "1c": ["0"], "1d": ["0"], "1e": ["0"], "1g": ["1a", "1b"],
    "1f": ["1a", "1b", "1c", "1d", "1e", "1g"], "P1": ["1f"], "2": ["P1"], "3": ["P1"], "P2": ["2", "3"],
    "4": ["P2"], "P3": ["4"],
}
PUERTAS = {1: "Oportunidad", 2: "Viabilidad", 3: "Alcance"}
ARCHIVOS_PLANTILLA = [
    ("estado.md", "estado.md"), ("criterios.md", "criterios.md"), ("00-idea.md", "00-idea.md"),
    ("competencia.md", "01-investigacion/competencia.md"),
    ("voz-del-usuario.md", "01-investigacion/voz-del-usuario.md"),
    ("demanda.md", "01-investigacion/demanda.md"), ("monetizacion.md", "01-investigacion/monetizacion.md"),
    ("politicas.md", "01-investigacion/politicas.md"),
    ("diferenciacion.md", "01-investigacion/diferenciacion.md"),
    ("01-sintesis.md", "01-sintesis.md"), ("02-estrategia.md", "02-estrategia.md"),
    ("03-validacion.md", "03-validacion.md"), ("04-prd.md", "04-prd.md"), ("escenarios.json", "escenarios.json"),
]
HEART = ("felicidad", "satisfaccion", "happiness", "interaccion", "compromiso", "engagement", "adopcion",
         "adoption", "retencion", "retention", "tarea", "task")


class Fallo(Exception):
    """Un error que se le explica al usuario, sin traza."""


# ---------------------------------------------------------------------------------------------------------------
# Utilidades

def hoy():
    """La fecha de hoy; `HB_PRODUCT_HOY=AAAA-MM-DD` la fija (para los tests y para reproducir un veredicto)."""
    texto = os.environ.get("HB_PRODUCT_HOY")
    if texto:
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            raise Fallo("HB_PRODUCT_HOY debe ser AAAA-MM-DD, no '%s'" % texto)
    return date.today()


def ahora():
    return "%sT%s" % (hoy().isoformat(), datetime.now().strftime("%H:%M"))


def origen():
    """Desde dónde se corrió el comando, solo si consta: Claude Code y otros agentes marcan los shells que abren."""
    if os.environ.get("CLAUDECODE") == "1":
        return "chat de Claude Code"
    agente = re.sub(r"[^\w.-]+", " ", os.environ.get("AI_AGENT") or "").strip()[:40]
    return "chat (%s)" % agente if agente else ""


def normal(texto):
    """Minúsculas, sin acentos y solo letras y números: para comparar encabezados y nombres."""
    plano = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", plano.lower())


def slug(texto):
    plano = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-") or "idea"


def numero(valor):
    """1234.5 → '1 234,50'; un entero, sin decimales."""
    if abs(valor - round(valor)) < 0.005:
        return "{:,.0f}".format(valor).replace(",", " ")
    return "{:,.2f}".format(valor).replace(",", " ").replace(".", ",")


def plural(cantidad, singular, plural_=None):
    """'1 hallazgo', '3 hallazgos', '0 semanas': la cantidad con la palabra en singular o en plural."""
    if plural_ is None:
        plural_ = singular + ("s" if singular[-1] in "aeiouáéíóú" else "es")
    valor = numero(cantidad) if isinstance(cantidad, float) else str(cantidad)
    return "%s %s" % (valor, singular if cantidad == 1 else plural_)


def lista(texto):
    return [parte.strip() for parte in str(texto or "").split(",") if parte.strip()]


def leer_json(ruta, defecto=None):
    try:
        with open(str(ruta), encoding="utf-8") as archivo:
            return json.load(archivo)
    except FileNotFoundError:
        return defecto
    except ValueError as error:
        raise Fallo("%s no es JSON válido (%s). Corrígelo o recupéralo antes de seguir." % (ruta, error))


def escribir(ruta, texto):
    """Escritura atómica: nunca deja un archivo a medias si el proceso se corta."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp%d" % os.getpid())
    temporal.write_text(texto, encoding="utf-8")
    os.replace(str(temporal), str(ruta))


def escribir_json(ruta, datos):
    escribir(ruta, json.dumps(datos, ensure_ascii=False, indent=2) + "\n")


@contextlib.contextmanager
def bloqueo(carpeta):
    """Un candado por carpeta: varias sesiones en paralelo nunca escriben a la vez."""
    ruta = Path(carpeta) / CANDADO
    limite = time.time() + 20
    while True:
        try:
            descriptor = os.open(str(ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
            break
        except FileExistsError:
            try:
                if time.time() - ruta.stat().st_mtime > 60:  # lo dejó un proceso que se cortó
                    ruta.unlink()
                    continue
            except OSError:
                continue
            if time.time() > limite:
                raise Fallo("Otra sesión está escribiendo en %s. Vuelve a intentar en unos segundos; si nadie más "
                            "está trabajando, borra %s." % (carpeta, ruta))
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            ruta.unlink()


def carpeta_de_agents(inicio):
    """La carpeta que diga `Carpeta:` en la sección `## Producto` del AGENTS.md más cercano, o None."""
    for base in [inicio] + list(inicio.parents)[:5]:
        agents = base / "AGENTS.md"
        if agents.is_file():
            seccion = re.search(r"^## Producto[^\n]*\n(.*?)(?=^## |\Z)", agents.read_text(encoding="utf-8"),
                                re.M | re.S)
            linea = seccion and re.search(r"^[\s*-]*\**Carpeta:?\**:?\s*`?([^`\n]+?)`?\s*$", seccion.group(1), re.M)
            return (base / linea.group(1).strip()) if linea else None
        if (base / ".git").exists():
            break
    return None


def resolver_carpeta(args):
    if getattr(args, "carpeta", None):
        return Path(os.path.abspath(os.path.expanduser(args.carpeta)))
    return Path(os.path.abspath(str(carpeta_de_agents(Path.cwd()) or Path.cwd() / CARPETA_DEFECTO)))


def orden(resto, carpeta):
    """El comando completo para el usuario: empieza con `cd <ruta absoluta> &&` y sirve en cualquier terminal."""
    return "cd %s && python3 -I %s %s --carpeta %s" % (shlex.quote(str(carpeta.parent)), shlex.quote(GUION), resto,
                                                    shlex.quote(carpeta.name))


# ---------------------------------------------------------------------------------------------------------------
# El producto y su registro

def cargar(carpeta):
    producto = leer_json(carpeta / "producto.json")
    if producto is None:
        archivadas = ideas_archivadas(carpeta)
        pista = (" Hay %d idea(s) en archivo/: `reabrir` recupera una." % len(archivadas)) if archivadas else ""
        raise Fallo("No hay ninguna idea activa en %s.%s Para empezar: `producto.py nuevo --nombre \"<nombre>\"`."
                    % (carpeta, pista))
    if producto.get("formato", 1) > FORMATO:
        raise Fallo("Esta carpeta la escribió una versión más nueva de hb-product: actualiza la skill.")
    for clave, valor in CRITERIOS_DEFECTO.items():  # un criterio nuevo toma su valor por defecto
        producto["criterios"].setdefault(clave, valor)
    return producto


def guardar(carpeta, producto):
    escribir_json(carpeta / "producto.json", producto)


def ruta_linea(carpeta, linea):
    return carpeta / "01-investigacion" / (linea + ".json")


def linea_vacia(linea):
    datos = {"linea": linea, "fuentes": [], "hallazgos": []}
    if linea == "competencia":
        datos["matriz"] = []
    if linea == "diferenciacion":
        datos["diferenciadores"] = []
    if linea in COBERTURA_LINEAS:
        datos["vacios"] = []
    return datos


def cargar_linea(carpeta, linea):
    datos = leer_json(ruta_linea(carpeta, linea)) or linea_vacia(linea)
    for clave, valor in linea_vacia(linea).items():
        datos.setdefault(clave, valor)
    return datos


class Registro:
    """Las fuentes, los hallazgos, la matriz y los diferenciadores de todas las líneas, ya consolidados."""

    def __init__(self, carpeta, criterios):
        self.criterios = criterios
        self.lineas = {linea: cargar_linea(carpeta, linea) for linea in LINEAS}
        self.fuentes, self.hallazgos, self.competidores, self.diferenciadores = {}, {}, {}, {}
        self.vacios = {}
        for linea, datos in self.lineas.items():
            for campo, destino in (("fuentes", self.fuentes), ("hallazgos", self.hallazgos),
                                   ("matriz", self.competidores), ("diferenciadores", self.diferenciadores),
                                   ("vacios", self.vacios)):
                for item in datos.get(campo, []):
                    if not item.get("anulado"):
                        destino[item["id"]] = item

    def vigente(self, fuente):
        """La regla de vigencia, la misma para la confianza y para la triangulación: una fuente sin fecha o publicada
        fuera de la ventana no es vigente y no cuenta en ninguna de las dos. Una fuente oficial (una política, una ley)
        rige mientras no la reemplacen: cuenta la fecha en que se consultó."""
        fecha = fuente.get("publicada")
        if fuente.get("tipo") == "oficial":
            fecha = fuente.get("consultada") or fecha
        if not fecha:
            return False
        referencia, meses = hoy(), int(self.criterios["vigencia_meses"])
        limite = referencia.year * 12 + referencia.month - 1 - meses
        anio, mes, dia = (int(parte) for parte in fecha.split("-"))
        indice = anio * 12 + mes - 1
        return indice > limite or (indice == limite and dia >= referencia.day)

    def fuentes_de(self, ids):
        return [self.fuentes[i] for i in ids if i in self.fuentes]

    @staticmethod
    def acumulada(hallazgo, fuente):
        """En la demanda, un dato acumulado (descargas o valoraciones desde el lanzamiento) es contexto, no una señal
        actual: no cuenta para la confianza ni para triangular un hallazgo de esa línea."""
        return hallazgo.get("linea") == "demanda" and bool(fuente.get("acumulado"))

    def evaluar(self, hallazgo):
        """La confianza de un hallazgo y su triangulación (reglas 2 y 3), con una sola regla de vigencia: las fuentes
        sin fecha o fuera de la ventana no cuentan para ninguna de las dos. Un hallazgo que solo tiene fuentes así queda
        en baja (su peso menor declarado), y la confianza alta exige estar triangulado. En la línea políticas, una
        fuente oficial y vigente basta sola: es la norma misma."""
        favor = self.fuentes_de(hallazgo.get("fuentes", []))
        minimo = int(self.criterios["fuentes_minimas"])
        exige = hallazgo.get("linea") in EXIGEN_MEDIDO
        basta_oficial = hallazgo.get("linea") in BASTA_OFICIAL
        mejor = None
        for peldano in range(1, 7):
            grupos = {}
            for fuente in favor:
                if fuente["peldano"] <= peldano and self.vigente(fuente) and not self.acumulada(hallazgo, fuente):
                    grupos.setdefault(independencia(fuente), []).append(fuente)
            if not grupos:
                continue
            cantidad = len(grupos)
            fuertes = sum(1 for grupo in grupos.values() if any(f["tipo"] != "opinion" for f in grupo))
            medido = any(f["tipo"] == "medido" for grupo in grupos.values() for f in grupo)
            oficiales = [f["id"] for grupo in grupos.values() for f in grupo if f["tipo"] == "oficial"]
            por_oficial = basta_oficial and bool(oficiales)
            triangulado = (cantidad >= minimo and (medido or not exige)) or por_oficial
            if (triangulado and fuertes >= 2) or por_oficial:
                nivel = 3
            elif cantidad >= 2 and (fuertes >= 1 or cantidad >= minimo):
                nivel = 2
            else:
                nivel = 1
            nivel = min(nivel, PELDANOS[peldano][1])
            if mejor is None or (nivel, triangulado) > (mejor["nivel"], mejor["triangulado"]):
                mejor = {"nivel": nivel, "triangulado": triangulado, "peldano": peldano, "independientes": cantidad,
                         "medido": medido, "oficial": oficiales if por_oficial else []}
        no_vigentes = [f["id"] for f in favor if not self.vigente(f)]
        acumuladas = [f["id"] for f in favor if self.vigente(f) and self.acumulada(hallazgo, f)]
        if mejor is None:
            mejor = {"nivel": 1 if favor else 0, "triangulado": False, "independientes": 0, "medido": False,
                     "peldano": min([f["peldano"] for f in favor] or [6]), "oficial": []}
        contra = {independencia(f) for f in self.fuentes_de(hallazgo.get("en_contra", [])) if self.vigente(f)}
        calculada = mejor["nivel"]
        if contra and calculada:
            calculada = 1 if len(contra) >= mejor["independientes"] else max(1, calculada - 1)
        manual = hallazgo.get("confianza_manual")
        nivel = min(calculada, NIVELES.index(manual["nivel"])) if manual else calculada
        faltan = []  # lo que le falta para triangular (regla 2)
        if not mejor["triangulado"]:
            if mejor["independientes"] < minimo:
                faltante = minimo - mejor["independientes"]
                faltan.append("%s %s (tiene %d de %d)" % (
                    "falta" if faltante == 1 else "faltan", plural(faltante, "fuente independiente y vigente",
                                                                  "fuentes independientes y vigentes"),
                    mejor["independientes"], minimo))
            if exige and not mejor["medido"]:
                faltan.append("falta una fuente de tipo medido (línea %s)" % hallazgo["linea"])
            if no_vigentes:
                faltan.append("%s sin fecha o fuera de la ventana de %s meses: no %s" % (
                    ", ".join(no_vigentes), self.criterios["vigencia_meses"],
                    "cuenta" if len(no_vigentes) == 1 else "cuentan"))
            if acumuladas:
                faltan.append("%s: %s (descargas o valoraciones desde el lanzamiento), contexto y no señal actual de "
                              "demanda: no %s" % (", ".join(acumuladas), "dato acumulado" if len(acumuladas) == 1
                                                  else "datos acumulados",
                                                  "cuenta" if len(acumuladas) == 1 else "cuentan"))
            if basta_oficial:
                faltan.append("o una sola fuente oficial y vigente (la política o la ley misma, `--tipo oficial`)")
        sin_busqueda = not hallazgo.get("en_contra") and not hallazgo.get("sin_contra")
        mejor.update(nivel=nivel, calculada=calculada, exige_medido=exige, contra=len(contra), vencidas=len(no_vigentes),
                     no_vigentes=no_vigentes, acumuladas=acumuladas, faltan=faltan, sin_busqueda=sin_busqueda,
                     confianza=NIVELES[nivel])
        return mejor

    def etiqueta(self, hallazgo):
        """'confianza media · sin triangular': la confianza siempre con su triangulación, para que nunca se lean por
        separado."""
        evaluacion = self.evaluar(hallazgo)
        return "confianza %s · %s" % (evaluacion["confianza"], "triangulado" if evaluacion["triangulado"]
                                      else "sin triangular")

    def confianza_minima(self, ids):
        """La menor confianza de un grupo de hallazgos (0 = sin evidencia, si no hay ninguno)."""
        niveles = [self.evaluar(self.hallazgos[i])["nivel"] for i in ids if i in self.hallazgos]
        return min(niveles) if niveles else 0

    def competidor(self, referencia):
        """Un competidor por su ID o por su nombre; None si no tiene fila en la matriz."""
        if referencia in self.competidores:
            return self.competidores[referencia]
        buscado = normal(referencia)
        for item in self.competidores.values():
            if normal(item["nombre"]) == buscado:
                return item
        return None

    def con_traccion(self, competidor):
        return bool(competidor.get("traccion")) or (competidor.get("descargas") or 0) >= int(
            self.criterios["traccion_descargas"])

    def viabilidad(self, diferenciador):
        """Los cuatro criterios de viabilidad de un diferenciador: [(cumple, texto)]."""
        hallazgos = [self.hallazgos[i] for i in diferenciador.get("hallazgos", []) if i in self.hallazgos]
        dolor = None
        for hallazgo in hallazgos:
            filas = {c["id"] for c in (self.competidor(r) for r in hallazgo.get("competidores", [])) if c}
            if self.evaluar(hallazgo)["triangulado"] and len(filas) >= 2:
                dolor = "%s triangulado en %d competidores" % (hallazgo["id"], len(filas))
                break
        columnas = VECTOR_COLUMNAS.get(diferenciador["vector"], ())
        medidos = [c["id"] for c in self.competidores.values()
                   if any(c.get(col) not in (None, "", []) for col in columnas)]
        con_fuente = any(self.evaluar(h)["independientes"] >= 1 for h in hallazgos)
        if dolor:
            evidencia = (True, "Evidencia: %s" % dolor)
        elif columnas and len(medidos) >= 2 and con_fuente:
            evidencia = (True, "Evidencia: vector medible comprobado en la matriz (%s)" % ", ".join(medidos))
        else:
            evidencia = (False, "Evidencia: falta un dolor o un pedido triangulado en 2 competidores o más, o un "
                                "vector medible comprobado en la matriz en 2 competidores o más")
        presupuesto = float(self.criterios.get("presupuesto_semanas") or 0)
        semanas = float(diferenciador.get("semanas") or 0)
        if not presupuesto:
            cabe = (False, "Presupuesto: falta `presupuesto_semanas` en los criterios (sesión 0)")
        else:
            cabe = (0 < semanas <= presupuesto, "Presupuesto: %s de %s" % (numero(semanas),
                                                                          plural(presupuesto, "semana")))
        return [evidencia,
                (diferenciador.get("se_ve") in ("ficha", "uso"), "Se percibe: en %s" % (
                    "la ficha de la tienda" if diferenciador.get("se_ve") == "ficha" else "el uso")),
                (bool(diferenciador.get("copiable") and diferenciador.get("motivo")),
                 "Copiabilidad: %s (%s)" % (diferenciador.get("copiable"), diferenciador.get("motivo"))),
                cabe, self.frente_al_sustituto(diferenciador), self.triangulacion_de(diferenciador)]

    def sustitutos(self):
        """Las filas de la matriz que dicen cómo se resuelve hoy la necesidad sin una app de este tipo (peldaño 4)."""
        return [c for c in self.competidores.values() if c.get("peldano") == 4]

    def sustitutos_fuertes(self):
        """Los sustitutos gratuitos o nativos que ya resuelven la necesidad: cada diferenciador tiene que superarlos."""
        return [c for c in self.sustitutos() if c.get("sustituto") in ("nativo", "gratuito") and c.get("resuelve") == "si"]

    def supera(self, diferenciador, sustituto):
        """Los hallazgos del diferenciador que nombran al sustituto (`hallazgo --competidores C-…`): la evidencia de lo
        que el sustituto no resuelve y el diferenciador sí."""
        resultado = []
        for identificador in diferenciador.get("hallazgos", []):
            hallazgo = self.hallazgos.get(identificador)
            filas = {c["id"] for c in (self.competidor(r) for r in (hallazgo or {}).get("competidores", [])) if c}
            if sustituto["id"] in filas:
                resultado.append(identificador)
        return resultado

    def frente_al_sustituto(self, diferenciador):
        """El quinto criterio de viabilidad: si hay un sustituto gratuito o nativo que ya resuelve la necesidad, el
        diferenciador tiene que superarlo con evidencia: (cumple, texto)."""
        fuertes = self.sustitutos_fuertes()
        sin_evaluar = [c for c in self.sustitutos() if c.get("sustituto") not in SUSTITUTOS
                       or c.get("resuelve") not in RESUELVE]
        if sin_evaluar and not fuertes:
            return (False, "Frente al sustituto: %s sin evaluar: no se sabe si es gratuito o nativo ni si ya resuelve "
                           "la necesidad (`competidor … --peldano 4 --sustituto … --resuelve …`)" % "; ".join(
                               nombre_fila(c) for c in sin_evaluar))
        if not fuertes:
            otros = self.sustitutos()
            return (True, "Frente al sustituto: %s" % ("ninguno gratuito o nativo resuelve la necesidad (%s)" % ", ".join(
                "%s %s" % (c["id"], RESUELVE[c["resuelve"]]) for c in otros) if otros
                else "la matriz no tiene sustitutos (peldaño 4)"))
        superados, faltan = [], []
        for sustituto in fuertes:
            apoyo = self.supera(diferenciador, sustituto)
            if apoyo:
                superados.append("%s con %s" % (nombre_fila(sustituto), ", ".join(apoyo)))
            else:
                faltan.append(sustituto)
        if faltan:
            return (False, "Frente al sustituto: no supera a %s; falta un hallazgo que lo nombre (`hallazgo … "
                           "--competidores %s`) y muestre lo que el sustituto no resuelve" % (
                               "; ".join(texto_sustituto(c) for c in faltan), ",".join(c["id"] for c in faltan)))
        return (True, "Frente al sustituto: supera a %s" % "; ".join(superados))

    def bloqueos(self, objetivo=None):
        """{tienda: [hallazgos]}: las tiendas del objetivo que nombran la categoría o la rechazan (`hallazgo --bloquea`).
        En esa tienda el riesgo de políticas es 1, salvo una mitigación escrita."""
        tiendas = [normal(t) for t in (objetivo or {}).get("tiendas") or []]
        resultado = {}
        for hallazgo in self.hallazgos.values():
            for tienda in hallazgo.get("bloquea", []):
                if objetivo is None or normal(tienda) in tiendas:
                    resultado.setdefault(tienda, []).append(hallazgo["id"])
        return resultado

    def sin_triangular(self, diferenciador):
        """Los hallazgos del diferenciador que no cumplen la regla 2: [(id, lo que le falta)]."""
        resultado = []
        for identificador in diferenciador.get("hallazgos", []):
            hallazgo = self.hallazgos.get(identificador)
            if hallazgo is None:
                resultado.append((identificador, "anulado"))
                continue
            evaluacion = self.evaluar(hallazgo)
            if not evaluacion["triangulado"]:
                resultado.append((identificador, "; ".join(evaluacion["faltan"]) or "sin triangular"))
        return resultado

    def triangulacion_de(self, diferenciador):
        faltan = self.sin_triangular(diferenciador)
        if not faltan:
            return (True, "Hallazgos triangulados (regla 2): %s" % ", ".join(diferenciador.get("hallazgos", [])))
        return (False, "Hallazgos triangulados (regla 2): sin triangular %s" % "; ".join(
            "%s (%s)" % par for par in faltan))

    def estado(self, diferenciador):
        """'viable' (los cinco criterios y sus hallazgos triangulados), 'baja' (viable con confianza baja: cumple los
        cinco criterios, pero algún hallazgo no está triangulado) o 'no'."""
        criterios = self.viabilidad(diferenciador)
        if not all(cumple for cumple, _ in criterios[:5]):
            return "no"
        return "viable" if criterios[5][0] else "baja"

    def viable(self, diferenciador):
        return self.estado(diferenciador) == "viable"

    def viables(self):
        return [d for d in self.diferenciadores.values() if self.viable(d)]

    def con_confianza_baja(self):
        return [d for d in self.diferenciadores.values() if self.estado(d) == "baja"]

    def principal(self):
        return next((d for d in self.diferenciadores.values() if d.get("principal")), None)


def independencia(fuente):
    """Dos fuentes son independientes si son de autor distinto; sin autor, cuenta el dominio."""
    return normal(fuente.get("autor") or "") or fuente["dominio"]


def nombre_fila(fila):
    """'C-4 (Linterna del sistema)': una fila de la matriz con su nombre."""
    return "%s (%s)" % (fila["id"], fila.get("nombre", ""))


def texto_sustituto(fila):
    """'C-4 (Linterna del sistema), viene con el sistema y resuelve la necesidad'."""
    return "%s, %s y %s" % (nombre_fila(fila), SUSTITUTOS.get(fila.get("sustituto"), "sin evaluar"),
                            RESUELVE.get(fila.get("resuelve"), "sin evaluar si resuelve la necesidad"))


def texto_bloqueos(bloqueos):
    """'app-store nombra o rechaza la categoría (H-POL-2)'."""
    return "; ".join("%s nombra o rechaza la categoría (%s)" % (tienda, ", ".join(ids))
                     for tienda, ids in sorted(bloqueos.items()))


def abrir(args):
    carpeta = resolver_carpeta(args)
    producto = cargar(carpeta)
    return carpeta, producto, Registro(carpeta, producto["criterios"])


def tipo_de(producto):
    return (producto.get("tipo") or {}).get("valor")


def presupuesto_de(producto):
    return PRESUPUESTO_NUEVA if tipo_de(producto) == "nueva" else PRESUPUESTO


ESTADOS_DIFERENCIADOR = {"viable": "viable", "baja": "viable con confianza baja", "no": "todavía no es viable"}


def meta_obligatoria(producto):
    return normal(producto["criterios"].get("meta_obligatoria", "no")) == "si"


def texto_meta(producto):
    """'300 USD al mes (referencial)', '… (obligatoria)' o 'sin meta (opcional)'."""
    criterios = producto["criterios"]
    meta = float(criterios.get("meta_ingresos_mes") or 0)
    if not meta:
        return "sin meta de ingresos (opcional)%s" % (": falta, y es obligatoria" if meta_obligatoria(producto)
                                                      else "")
    return "meta de %s %s al mes (%s)" % (numero(meta), criterios["moneda"],
                                         "obligatoria" if meta_obligatoria(producto) else "referencial")


# ---------------------------------------------------------------------------------------------------------------
# Cobertura por mercado, idioma y tienda

def objetivo_de(producto):
    """{"mercados": [...], "idiomas": [...], "tiendas": [...]} de la sesión 0, o None si no está registrado."""
    objetivo = producto.get("objetivo")
    if not objetivo or any(objetivo.get(d) is None for d in DIMENSIONES):
        return None
    return objetivo


def cobertura(producto, registro, solo=None):
    """{línea: [(dimensión, valor, estado, detalle)]}, con estado 'fuentes' (ids), 'vacio' (el registro) o 'falta'.
    Una fuente cubre un valor si es de esa línea y lo lleva en sus etiquetas; un vacío registrado lo deja explicado."""
    objetivo = objetivo_de(producto)
    if objetivo is None:
        return None
    resultado = {}
    for linea, dimensiones in COBERTURA_LINEAS.items():
        if solo and linea != solo:
            continue
        filas = []
        for dimension in dimensiones:
            for valor in objetivo[dimension]:
                buscado = normal(valor)
                fuentes = [f["id"] for f in registro.fuentes.values() if f["linea"] == linea
                           and buscado in [normal(v) for v in f.get(dimension, [])]]
                vacio = next((v for v in registro.vacios.values() if v["linea"] == linea
                              and v["dimension"] == dimension and normal(v["valor"]) == buscado), None)
                if fuentes:
                    filas.append((dimension, valor, "fuentes", fuentes))
                elif vacio:
                    filas.append((dimension, valor, "vacio", vacio))
                else:
                    filas.append((dimension, valor, "falta", None))
        resultado[linea] = filas
    return resultado


def vacios_de_herramienta(producto, registro, lineas=None):
    """Los vacíos por límite de las herramientas que siguen sin fuentes, en las líneas pedidas: ajustar la línea con
    las mismas herramientas no los resuelve."""
    mapa = cobertura(producto, registro) or {}
    return [detalle for linea, filas in mapa.items() for _, _, estado, detalle in filas
            if estado == "vacio" and detalle["motivo"] == "herramienta" and (not lineas or linea in lineas)]


def texto_vacio(vacio):
    return "%s · %s %s (%s, %s): %s" % (vacio["linea"], DIMENSIONES[vacio["dimension"]], vacio["valor"],
                                        MOTIVOS_VACIO[vacio["motivo"]], vacio["id"], vacio["texto"])


# ---------------------------------------------------------------------------------------------------------------
# Modelos: el nombre concreto de cada nivel y el comando que abre el chat (references/modelos.md)

def modelo_de(producto, nivel):
    return str((producto.get("modelos") or {}).get(nivel) or MODELOS[nivel])


def id_modelo(nombre, herramienta):
    """El id de un modelo en una herramienta: "Sonnet 5.5" → claude-sonnet-5-5 en Claude Code y claude-sonnet-5.5 en
    GitHub Copilot CLI. Un nombre que ya es un id (sin espacios ni mayúsculas) va tal cual."""
    nombre = nombre.strip()
    if re.match(r"^[a-z0-9][\w.:\[\]-]*$", nombre):
        return nombre
    palabras = nombre.lower().split()
    if palabras and palabras[0] in FAMILIAS_CLAUDE:
        palabras = ["claude"] + palabras
    texto = "-".join(palabras)
    return texto.replace(".", "-") if herramienta == "claude" else texto


def abrir_chat(producto, carpeta, nivel):
    """El comando que abre un chat nuevo con el modelo y el esfuerzo del nivel, según la herramienta anotada con
    `modelos --herramienta`; None si no hay ninguna anotada."""
    herramienta = producto.get("herramienta") or {}
    clave, propio = herramienta.get("clave"), herramienta.get("comando")
    if not clave:
        return None
    esfuerzo = ESFUERZO_CLI[ESFUERZO[nivel]]
    if clave == "otra":
        if not propio:
            return None
        comando = propio.replace("{modelo}", shlex.quote(modelo_de(producto, nivel)))
    else:
        plantilla_cli = propio or dict((c, t) for c, _, t in HERRAMIENTAS_CHAT)[clave]
        comando = plantilla_cli.replace("{modelo}", shlex.quote(id_modelo(modelo_de(producto, nivel), clave)))
    return "cd %s && %s" % (shlex.quote(str(carpeta.parent)), comando.replace("{esfuerzo}", esfuerzo))


def texto_modelo(producto, nivel):
    return "Modelo: %s · Esfuerzo: %s" % (modelo_de(producto, nivel), ESFUERZO[nivel])


# ---------------------------------------------------------------------------------------------------------------
# Tablas de Markdown (03-validacion.md y 04-prd.md)

def tablas(texto):
    """Las tablas de un Markdown, fuera de los bloques de código y de los comentarios: [(encabezados, filas)]."""
    texto = re.sub(r"```.*?```", "", texto, flags=re.S)
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    resultado, actual = [], None
    for linea in texto.splitlines() + [""]:
        linea = linea.strip()
        if linea.startswith("|"):
            celdas = [celda.strip() for celda in linea.strip("|").split("|")]
            if actual is None:
                actual = [celdas, []]
            elif not all(re.match(r"^:?-{2,}:?$", celda) for celda in celdas):
                actual[1].append(celdas)
        elif actual is not None:
            resultado.append(actual)
            actual = None
    return resultado


def tabla(texto, *columnas):
    """Las filas de la primera tabla que tiene esas columnas, como diccionarios por encabezado normalizado."""
    for encabezados, filas in tablas(texto):
        claves = [normal(e) for e in encabezados]
        if all(any(clave.startswith(normal(col)) for clave in claves) for col in columnas):
            return [dict(zip(claves, fila + [""] * (len(claves) - len(fila)))) for fila in filas]
    return None


def celda(fila, columna):
    """El valor de una columna por el comienzo de su encabezado; '' si está vacía o es un guion."""
    buscada = normal(columna)
    valor = next((v for clave, v in fila.items() if clave.startswith(buscada)), "")
    return "" if valor.strip() in ("", "-", "—", "–") or PENDIENTE in valor else valor.strip()


def afirmativo(valor):
    return normal(valor) in ("si", "s", "x", "yes", "mvp")


def leer_md(carpeta, relativo):
    ruta = carpeta / relativo
    return ruta.read_text(encoding="utf-8") if ruta.is_file() else ""


def hipotesis(carpeta, registro):
    """La tabla de hipótesis críticas de 03-validacion.md, con la confianza que calcula el script."""
    filas = tabla(leer_md(carpeta, "03-validacion.md"), "id", "hipotesis", "hallazgos", "veredicto")
    if filas is None:
        return None
    resultado = []
    for fila in filas:
        identificador = (re.findall(r"HIP-\d+", celda(fila, "id")) or [""])[0]
        if not identificador:
            continue
        hallazgos = re.findall(r"H-[A-Z]{3}-\d+", celda(fila, "hallazgos"))
        veredicto = normal(celda(fila, "veredicto"))
        resultado.append({
            "id": identificador, "texto": celda(fila, "hipotesis"), "hallazgos": hallazgos,
            "desconocidos": [h for h in hallazgos if h not in registro.hallazgos],
            "nivel": registro.confianza_minima(hallazgos), "contra": celda(fila, "encontra"),
            "diferenciador": (re.findall(r"D-\d+", celda(fila, "diferenciador")) or [""])[0],
            "veredicto": {"sostenida": "sostenida", "debil": "débil", "refutada": "refutada"}.get(veredicto, ""),
            "riesgosa": afirmativo(celda(fila, "masriesgosa")), "metrica": celda(fila, "metrica"),
        })
    return resultado


def problemas_validacion(filas):
    """Lo que le falta a la tabla de hipótesis para poder cerrar la sesión 3."""
    if not filas:
        return ["03-validacion.md no tiene filas en la tabla de hipótesis (ID, Hipótesis, Hallazgos, En contra, "
                "Diferenciador, Veredicto, Más riesgosa, Métrica y umbral)"]
    problemas = []
    for fila in filas:
        if not fila["veredicto"]:
            problemas.append("%s: el veredicto debe ser sostenida, débil o refutada" % fila["id"])
        if not fila["hallazgos"]:
            problemas.append("%s: no cita ningún hallazgo (H-…)" % fila["id"])
        if fila["desconocidos"]:
            problemas.append("%s: cita hallazgos que no existen: %s" % (fila["id"], ", ".join(fila["desconocidos"])))
        if not fila["contra"]:
            problemas.append("%s: falta la evidencia en contra (o qué se buscó, si no apareció nada)" % fila["id"])
        if fila["veredicto"] == "sostenida" and fila["nivel"] < 2:
            problemas.append("%s: figura como sostenida, pero su confianza es %s: va como débil"
                             % (fila["id"], NIVELES[fila["nivel"]]))
    riesgosas = [fila["id"] for fila in filas if fila["riesgosa"]]
    if len(riesgosas) != 1:
        problemas.append("marca exactamente una hipótesis como la más riesgosa (hay %d)" % len(riesgosas))
    return problemas


def prd(carpeta, registro):
    """Las tablas de 04-prd.md: funcionalidades (con su RICE), métricas HEART y checklist de políticas."""
    texto = leer_md(carpeta, "04-prd.md")
    filas = tabla(texto, "id", "funcionalidad", "mvp", "hallazgos", "metrica")
    metricas = {}
    for fila in tabla(texto, "id", "dimension", "metrica", "meta") or []:
        for identificador in re.findall(r"M-\d+", celda(fila, "id")):
            completa = bool(celda(fila, "metrica") and celda(fila, "meta")) and any(
                palabra in normal(celda(fila, "dimension")) for palabra in HEART)
            metricas[identificador] = completa
    politicas = [(celda(fila, "requisito"), normal(celda(fila, "estado")))
                 for fila in tabla(texto, "requisito", "estado") or [] if celda(fila, "requisito")]
    funciones = []
    for fila in filas or []:
        identificador = (re.findall(r"F-\d+", celda(fila, "id")) or [""])[0]
        if not identificador:
            continue
        hallazgos = re.findall(r"H-[A-Z]{3}-\d+", celda(fila, "hallazgos"))
        usadas = re.findall(r"M-\d+", celda(fila, "metrica"))
        faltas = []
        if not hallazgos:
            faltas.append("sin hallazgo")
        desconocidos = [h for h in hallazgos if h not in registro.hallazgos]
        if desconocidos:
            faltas.append("hallazgos que no existen: %s" % ", ".join(desconocidos))
        if not usadas:
            faltas.append("sin métrica HEART (M-…)")
        sin_definir = [m for m in usadas if not metricas.get(m)]
        if sin_definir:
            faltas.append("métricas sin definir en la tabla HEART: %s" % ", ".join(sin_definir))
        alcance, impacto, semanas = (a_numero(celda(fila, c)) for c in ("alcance", "impacto", "semanas"))
        confianza = RICE_CONFIANZA[registro.confianza_minima(hallazgos)]
        rice = alcance * impacto * confianza / 100.0 / semanas if alcance and impacto and semanas else None
        funciones.append({
            "id": identificador, "nombre": celda(fila, "funcionalidad"), "mvp": afirmativo(celda(fila, "mvp")),
            "hallazgos": hallazgos, "diferenciadores": re.findall(r"D-\d+", celda(fila, "diferenciador")),
            "metricas": usadas, "semanas": semanas, "rice": rice, "faltas": faltas,
            "hipotesis": re.findall(r"HIP-\d+", celda(fila, "hipotesis")),
        })
    return {"existe": filas is not None, "funciones": funciones, "metricas": metricas, "politicas": politicas}


def a_numero(texto):
    """'1 500', '2,5', '100k' o '1M' → número; 0 si no se entiende."""
    limpio = str(texto or "").strip().lower().replace(" ", "")
    factor = 1
    if limpio.endswith("k"):
        factor, limpio = 1000, limpio[:-1]
    elif limpio.endswith("m"):
        factor, limpio = 1000000, limpio[:-1]
    limpio = re.sub(r"[^0-9.,]", "", limpio)
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    try:
        return float(limpio) * factor
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------------------------------------------
# Puntaje y puertas

def sustento(registro):
    """Los hallazgos clave que sostienen cada criterio del puntaje: {criterio: [ids] o None si no lleva fuentes}."""
    clave = lambda linea: [h["id"] for h in registro.hallazgos.values() if h["linea"] == linea and h.get("critico")]
    principal = registro.principal()
    viables = registro.viables() or registro.con_confianza_baja()
    if principal:
        diferenciacion = list(principal.get("hallazgos", []))
    elif viables:
        diferenciacion = [h for d in viables for h in d.get("hallazgos", [])]
    else:
        diferenciacion = None  # sin diferenciador no hay nada que sostener: el ancla es 1
    return {"demanda": clave("demanda"), "monetizacion": clave("monetizacion"), "facilidad": None,
            "riesgo": clave("politicas"), "diferenciacion": diferenciacion}


def confianzas(registro):
    """La confianza de cada criterio y la global (la menor de las que llevan fuentes)."""
    resultado = {}
    for criterio, ids in sustento(registro).items():
        resultado[criterio] = None if ids is None else registro.confianza_minima(ids)
    con_fuentes = [nivel for nivel in resultado.values() if nivel is not None]
    return resultado, (min(con_fuentes) if con_fuentes else 0)


def criterios_puerta(numero_puerta, carpeta, producto, registro):
    """Los criterios de una puerta para el tipo de idea: [(cumple, texto, detalle)]."""
    return [(c["cumple"], c["texto"], c["detalle"]) for c in evaluar_puerta(numero_puerta, carpeta, producto, registro)]


def evaluar_puerta(numero_puerta, carpeta, producto, registro):
    """Los criterios de una puerta con su clave (la usa el veredicto): [{clave, cumple, texto, detalle}]."""
    criterios = producto["criterios"]
    nueva = tipo_de(producto) == "nueva"
    resultado = []

    def agregar(clave, cumple, texto, detalle=""):
        resultado.append({"clave": clave, "cumple": bool(cumple), "texto": texto, "detalle": detalle})

    if numero_puerta == 1:
        puntaje = producto.get("puntaje")
        minimo = int(criterios["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
        texto = "Puntaje de %d/25 o más" % minimo
        if puntaje:
            vigente_ = puntaje_vigente(producto, registro)
            agregar("puntaje", puntaje["total"] >= minimo, texto, "tiene %d/25%s" % (
                puntaje["total"], " · ⚠ con las reglas de hoy serían %d/25" % vigente_["total"]
                if vigente_["incoherencias"] else ""))
        else:
            agregar("puntaje", False, texto, "sin registrar: corre `puntaje` en la sesión 1f")
        if nueva:
            minimas = int(criterios["fuentes_minimas"])
            documentado = None
            for hallazgo in registro.hallazgos.values():
                grupos = {independencia(f) for f in registro.fuentes_de(hallazgo["fuentes"])
                          if f["peldano"] in (4, 5) and registro.vigente(f)}
                if len(grupos) >= minimas:
                    documentado = hallazgo["id"]
                    break
            agregar("problema", documentado,
                    "El problema o la necesidad de fondo, con %d fuentes de peldaño 4 o 5" % minimas,
                    documentado or "ningún hallazgo reúne %d fuentes independientes y vigentes de esos peldaños"
                    % minimas)
            analogos = [c["id"] for c in registro.competidores.values()
                        if c["peldano"] in (2, 3) and registro.con_traccion(c)]
            pedidos = int(criterios["analogos_minimos"])
            agregar("analogos", len(analogos) >= pedidos,
                    "Al menos %d análogos con tracción (peldaño 2 o 3)" % pedidos,
                    "%d en la matriz%s" % (len(analogos), (": " + ", ".join(analogos)) if analogos else ""))
            intentos = producto.get("intentos", [])
            fracasos = [i for i in intentos if i["resultado"] == "fracaso-demanda"]
            texto = "Sin evidencia de que se probó y fracasó por falta de demanda"
            if not intentos:
                agregar("intentos", False, texto, "la búsqueda no está registrada: corre `intento`")
            else:
                agregar("intentos", not fracasos, texto,
                        "%s por demanda" % plural(len(fracasos), "intento fallido", "intentos fallidos") if fracasos
                        else plural(len(intentos), "búsqueda registrada", "búsquedas registradas"))
            fuertes = registro.sustitutos_fuertes()
            if fuertes:  # un sustituto gratuito o nativo que ya resuelve la necesidad: la idea tiene que superarlo
                viables = registro.viables()
                agregar("sustituto", viables, "Un diferenciador viable supera al sustituto gratuito o nativo que ya "
                        "resuelve la necesidad: %s" % "; ".join(nombre_fila(c) for c in fuertes),
                        ", ".join(d["id"] for d in viables) if viables else detalle_sustituto(registro, fuertes))
        else:
            nivel = confianzas(registro)[0]["demanda"]
            agregar("demanda", nivel >= 2, "Demanda con confianza media o alta", "es %s" % NIVELES[nivel])
            viables, bajas = registro.viables(), registro.con_confianza_baja()
            fuertes = registro.sustitutos_fuertes()
            detalle = "%s%s de %s" % (
                plural(len(viables), "viable"), ", %d con confianza baja" % len(bajas) if bajas else "",
                plural(len(registro.diferenciadores), "registrado"))
            if fuertes and not viables:
                detalle += " · " + detalle_sustituto(registro, fuertes)
            agregar("diferenciador", viables, "Al menos 1 diferenciador viable, con sus hallazgos triangulados%s" % (
                " y que supere al sustituto gratuito o nativo que ya resuelve la necesidad (%s)" % "; ".join(
                    nombre_fila(c) for c in fuertes) if fuertes else ""), detalle)
            principal = registro.principal()
            texto = "Los hallazgos del diferenciador principal están triangulados"
            if not principal:
                agregar("principal", False, texto, "no hay un diferenciador principal registrado")
            else:
                faltan = registro.sin_triangular(principal)
                agregar("principal", not faltan, texto, "%s: %s" % (principal["id"], "; ".join(
                    "%s sin triangular (%s)" % par for par in faltan) if faltan else ", ".join(
                    principal.get("hallazgos", []))))
        texto = "Riesgo de políticas distinto de 1, o con una mitigación escrita"
        bloqueos = registro.bloqueos(objetivo_de(producto))
        if not puntaje:
            agregar("riesgo", False, texto, "sin puntaje")
        else:
            riesgo, mitigacion = puntaje["valores"]["riesgo"], puntaje.get("mitigacion")
            if bloqueos and riesgo != 1:
                agregar("riesgo", False, texto, "el puntaje dice %d, pero %s: en esa tienda el riesgo es 1; vuelve a "
                        "correr `puntaje`" % (riesgo, texto_bloqueos(bloqueos)))
            else:
                agregar("riesgo", riesgo != 1 or mitigacion, texto, "es %d%s%s" % (
                    riesgo, " · bloqueante en %s" % texto_bloqueos(bloqueos) if bloqueos else "",
                    " · mitigación: «%s»" % mitigacion if mitigacion else ""))

    elif numero_puerta == 2:
        escenarios = producto.get("escenarios")
        texto = "Al menos un modelo de monetización viable con evidencia%s" % (" (por analogía)" if nueva else "")
        if not escenarios:
            agregar("monetizacion", False, texto, "sin calcular: corre `escenarios` en la sesión 2")
        elif "modelos" not in escenarios:
            agregar("monetizacion", False, texto,
                    "los escenarios son de una versión anterior: vuelve a correr `escenarios`")
        else:
            viables = [m for m in escenarios["modelos"] if m["viable"]]
            agregar("monetizacion", viables, texto, "; ".join(
                "%s: %s %s al mes en el caso base" % (m["nombre"], numero(m["base"]), escenarios["moneda"])
                for m in viables) if viables else "ninguno: " + "; ".join(
                "%s (%s)" % (m["nombre"], motivo_modelo(m)) for m in escenarios["modelos"]))
        if meta_obligatoria(producto):
            meta = float(criterios.get("meta_ingresos_mes") or 0)
            texto = "El escenario base%s alcanza la meta de ingresos (marcada como obligatoria)" % (
                " por analogía" if nueva else "")
            if not escenarios:
                agregar("meta", False, texto, "sin calcular: corre `escenarios` en la sesión 2")
            elif not meta:
                agregar("meta", False, texto, "falta `meta_ingresos_mes` en los criterios")
            else:
                agregar("meta", escenarios["base"] >= meta, texto, "%s de %s %s al mes" % (
                    numero(escenarios["base"]), numero(meta), criterios["moneda"]))
        filas = hipotesis(carpeta, registro)
        texto = "Ninguna hipótesis crítica refutada"
        if not filas:
            agregar("hipotesis", False, texto, "03-validacion.md no tiene la tabla de hipótesis")
        else:
            refutadas = [fila["id"] for fila in filas if fila["veredicto"] == "refutada"]
            agregar("hipotesis", not refutadas, texto,
                    "refutadas: %s" % ", ".join(refutadas) if refutadas else "%d hipótesis" % len(filas))
        if nueva:
            riesgosas = [fila for fila in filas or [] if fila["riesgosa"]]
            medible = len(riesgosas) == 1 and riesgosas[0]["metrica"]
            agregar("riesgosa", medible, "La hipótesis más riesgosa, identificada y medible después del lanzamiento",
                    "%s, con métrica y umbral" % riesgosas[0]["id"] if medible
                    else "falta marcar una sola hipótesis como la más riesgosa, con su métrica y su umbral")
        else:
            principal = registro.principal()
            texto = "El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta"
            if not principal:
                agregar("sobrevive", False, texto, "no hay un diferenciador principal registrado")
            else:
                suyas = [fila for fila in filas or [] if fila["diferenciador"] == principal["id"]]
                sobrevive = suyas and all(f["veredicto"] == "sostenida" and f["nivel"] >= 2 for f in suyas)
                agregar("sobrevive", sobrevive, texto, "%s: %s" % (principal["id"], ", ".join(
                    "%s %s (confianza %s)" % (f["id"], f["veredicto"] or "sin veredicto", NIVELES[f["nivel"]])
                    for f in suyas) or "ninguna hipótesis lo pone a prueba en 03-validacion.md"))

    else:
        datos = prd(carpeta, registro)
        mvp = [f for f in datos["funciones"] if f["mvp"]]
        presupuesto = float(criterios.get("presupuesto_semanas") or 0)
        semanas = sum(f["semanas"] for f in mvp)
        sin_semanas = [f["id"] for f in mvp if not f["semanas"]]
        agregar("presupuesto", mvp and presupuesto and not sin_semanas and semanas <= presupuesto,
                "El MVP cabe en el presupuesto de semanas",
                "sin estimación: %s" % ", ".join(sin_semanas) if sin_semanas
                else "%s de %s" % (numero(semanas), plural(presupuesto, "semana")) if mvp
                else "04-prd.md no tiene funcionalidades marcadas como MVP")
        principal = registro.principal()
        dentro = principal and [f["id"] for f in mvp if principal["id"] in f["diferenciadores"]]
        agregar("principal_mvp", dentro, "El diferenciador principal está en el MVP",
                "%s en %s" % (principal["id"], ", ".join(dentro)) if dentro
                else "ninguna funcionalidad del MVP lo cita" if principal
                else "no hay un diferenciador principal registrado")
        trazadas = [f for f in mvp if not f["faltas"]]
        agregar("trazabilidad", mvp and len(trazadas) == len(mvp),
                "100 % de las funcionalidades del MVP con trazabilidad", "%d de %d" % (len(trazadas), len(mvp)))
        definidas = datos["metricas"] and all(datos["metricas"].values())
        agregar("heart", definidas, "Métricas HEART definidas", "%s, %s" % (
            plural(len(datos["metricas"]), "métrica"),
            plural(sum(1 for completa in datos["metricas"].values() if not completa), "incompleta")))
        bloqueos = [requisito for requisito, estado in datos["politicas"] if estado == "bloqueo"]
        agregar("checklist", datos["politicas"] and not bloqueos, "Checklist de políticas sin bloqueos",
                "bloqueos: %s" % "; ".join(bloqueos) if bloqueos
                else plural(len(datos["politicas"]), "requisito") if datos["politicas"] else "el checklist está vacío")
        if nueva:
            riesgosas = [fila for fila in hipotesis(carpeta, registro) or [] if fila["riesgosa"]]
            riesgosa = riesgosas[0] if len(riesgosas) == 1 else None
            prueba = riesgosa and riesgosa["metrica"] and [f["id"] for f in mvp if riesgosa["id"] in f["hipotesis"]]
            agregar("riesgosa_mvp", prueba,
                    "El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral",
                    "%s en %s" % (riesgosa["id"], ", ".join(prueba)) if prueba
                    else "ninguna funcionalidad del MVP cita la hipótesis más riesgosa (columna Hipótesis), o le "
                         "falta su métrica y su umbral en 03-validacion.md")
    return resultado


def detalle_sustituto(registro, fuertes):
    """Por qué ningún diferenciador supera a los sustitutos fuertes."""
    candidatos = [d for d in registro.diferenciadores.values()
                  if all(registro.supera(d, s) for s in fuertes)]
    if candidatos:
        return "%s lo(s) supera(n) con evidencia, pero no es (son) viable(s)" % ", ".join(d["id"] for d in candidatos)
    return "ningún diferenciador supera a %s con evidencia" % "; ".join(texto_sustituto(c) for c in fuertes)


def motivo_modelo(modelo):
    """Por qué un modelo de monetización de los escenarios no es viable con evidencia."""
    if modelo["base"] <= 0:
        return "no genera ingresos en el caso base"
    return "estimación: sin fuente en %s" % ", ".join(modelo["sin_fuente"])


def avisos_puerta(numero_puerta, carpeta, producto, registro):
    """Lo que el usuario tiene que ver antes de decidir y no es un criterio: [línea]."""
    avisos = []
    for cambio in producto.get("criterios_cambios", []):
        avisos.append("· Criterio cambiado después de la sesión 0: %s de %s a %s el %s (%s)" % (
            cambio["clave"], cambio["antes"], cambio["despues"], cambio["fecha"][:10], cambio["motivo"]))
    if numero_puerta == 1:
        avisos.append("· La cantidad de competidores no es un criterio: ni la saturación ni la falta de datos "
                      "descartan una idea.")
        por_criterio, global_ = confianzas(registro)
        if producto.get("puntaje") and global_ < 2:
            debiles = [c for c, nivel in por_criterio.items() if nivel is not None and nivel < 2]
            avisos.append("⚠ No lo pases por alto: la confianza global es %s. Los criterios que se cumplen se apoyan "
                          "en evidencia débil (%s): `triangulacion` dice qué le falta a cada hallazgo." % (
                              NIVELES[global_], ", ".join(debiles)))
        principal = registro.principal()
        if principal and tipo_de(producto) == "nueva" and registro.sin_triangular(principal):
            avisos.append("⚠ No lo pases por alto: los hallazgos del diferenciador principal (%s) no están "
                          "triangulados." % principal["id"])
        mapa = cobertura(producto, registro)
        if mapa is None:
            avisos.append("⚠ Cobertura: no hay objetivo de mercados, idiomas y tiendas (`objetivo`), así que no se "
                          "sabe qué quedó sin investigar.")
        else:
            huecos = ["%s · %s %s" % (linea, DIMENSIONES[d], v) for linea, filas in mapa.items()
                      for d, v, estado, _ in filas if estado == "falta"]
            if huecos:
                avisos.append("⚠ Cobertura sin fuentes ni vacío registrado: %s." % "; ".join(huecos))
            herramienta = vacios_de_herramienta(producto, registro)
            if herramienta:
                avisos.append("· Vacíos por límite de las herramientas: %s. Ajustar esas líneas con las mismas "
                              "herramientas no los resuelve; sí un navegador en el agente o un CSV de reseñas que "
                              "aportes (references/investigacion.md · Fuentes difíciles)." % "; ".join(
                                  "%s · %s %s" % (v["linea"], DIMENSIONES[v["dimension"]], v["valor"])
                                  for v in herramienta))
    if numero_puerta == 2 and not meta_obligatoria(producto):
        escenarios, meta = producto.get("escenarios"), float(producto["criterios"].get("meta_ingresos_mes") or 0)
        if escenarios and meta:
            avisos.append("· Meta de ingresos (referencial, no es criterio): el caso base da %s de %s %s al mes; "
                          "hacen falta %s usuarios activos diarios para llegar." % (
                              numero(escenarios["base"]), numero(meta), producto["criterios"]["moneda"],
                              numero(escenarios["dau_meta"]) if escenarios.get("dau_meta") else "—"))
    for propuesta in propuestas_de(producto, numero_puerta):
        avisos.append("· Propuesta %s (sesión %s): %s%s" % (
            propuesta["id"], propuesta.get("sesion") or "?", propuesta["texto"],
            " → se aplica con Ajustar %s" % propuesta["ajustar"] if propuesta.get("ajustar") else ""))
    return avisos


def propuestas_de(producto, numero_puerta):
    return [p for p in producto.get("propuestas", []) if p["puerta"] == numero_puerta and p["estado"] == "pendiente"]


def bloque_puerta(numero_puerta, carpeta, producto, registro, resultado=None):
    """La puerta completa: el banner con el veredicto y la recomendación, y debajo los criterios uno por uno, con sus
    avisos: (líneas, cumplidos, total)."""
    evaluados = evaluar_puerta(numero_puerta, carpeta, producto, registro)
    resultado = resultado or veredicto(numero_puerta, carpeta, producto, registro, evaluados)
    cumplidos = sum(1 for c in evaluados if c["cumple"])
    lineas = lineas_banner(resultado) + ["", "Puerta %d · %s · idea %s · cumple %d de %d criterios" % (
        numero_puerta, PUERTAS[numero_puerta], tipo_de(producto), cumplidos, len(evaluados))]
    if resultado["provisional"]:
        lineas.append("⚠ Veredicto provisional: falta cerrar %s." % ", ".join(
            "la sesión %s" % s for s in resultado["provisional"]))
    for c in evaluados:
        lineas.append("  %s %s%s" % ("✔" if c["cumple"] else "✖", c["texto"], " · " + c["detalle"] if c["detalle"]
                                    else ""))
    lineas += ["  " + aviso for aviso in avisos_puerta(numero_puerta, carpeta, producto, registro)]
    return lineas, cumplidos, len(evaluados)


# ---------------------------------------------------------------------------------------------------------------
# Veredicto y recomendación de cada puerta: reglas fijas sobre los criterios y la confianza. La skill recomienda; la
# decisión es del usuario, y decidir en contra pide un motivo.

VEREDICTOS = {
    "no": {"titulo": "No viable", "recomienda": "descartar", "tono": "mal", "marca": "🔴", "color": "31"},
    "reservas": {"titulo": "Viable con reservas", "recomienda": "ajustar", "tono": "aviso", "marca": "🟡",
                 "color": "33"},
    "viable": {"titulo": "Viable", "recomienda": "seguir", "tono": "bien", "marca": "🟢", "color": "32"},
}
MAXIMO_RAZONES = 3
NOMBRES_CRITERIO = {"demanda": "demanda", "monetizacion": "monetización", "facilidad": "facilidad",
                    "riesgo": "riesgo de políticas", "diferenciacion": "diferenciación"}
SESION_CRITERIO = {"demanda": "1c", "monetizacion": "1d", "riesgo": "1e", "diferenciacion": "1g"}


def limites_puntaje(producto, registro):
    """Los topes que las reglas y la evidencia de hoy ponen al puntaje (los mismos que aplica `puntaje` al
    registrarlo): {criterio: (mínimo, máximo, motivo)}."""
    limites = {}
    viables, bajas = registro.viables(), registro.con_confianza_baja()
    if not viables and not bajas:
        limites["diferenciacion"] = (1, 1, "ningún diferenciador es viable")
    elif not viables:
        limites["diferenciacion"] = (1, 2, "solo hay diferenciadores viables con confianza baja")
    else:
        limites["diferenciacion"] = (2, 5, "hay %s" % plural(len(viables), "diferenciador viable",
                                                             "diferenciadores viables"))
    actuales = [h for h in registro.hallazgos.values() if h["linea"] == "demanda" and h.get("critico")
                and registro.evaluar(h)["triangulado"]]
    if not actuales:
        limites["demanda"] = (1, 3, "ningún hallazgo clave de demanda está triangulado con señales actuales")
    bloqueos = registro.bloqueos(objetivo_de(producto))
    if bloqueos:
        limites["riesgo"] = (1, 1, texto_bloqueos(bloqueos))
    return limites


def puntaje_vigente(producto, registro):
    """El puntaje registrado contra las reglas y la evidencia de hoy: {total, valores, incoherencias}. Una incoherencia
    aparece cuando el puntaje se registró con reglas anteriores o cuando la evidencia cambió después (una fuente que
    envejeció, un hallazgo anulado); el total ajustado lleva cada valor a su tope."""
    puntaje = producto.get("puntaje")
    if not puntaje:
        return None
    valores, incoherencias = dict(puntaje["valores"]), []
    for criterio, (minimo, maximo, motivo) in limites_puntaje(producto, registro).items():
        valor = valores[criterio]
        if not minimo <= valor <= maximo:
            ajustado = min(max(valor, minimo), maximo)
            incoherencias.append("%s %d, pero con las reglas de hoy %s %d (%s)" % (
                NOMBRES_CRITERIO[criterio], valor, "el máximo es" if valor > maximo else "el mínimo es", ajustado,
                motivo))
            valores[criterio] = ajustado
    return {"total": sum(valores.values()), "valores": valores, "incoherencias": incoherencias}


def sesion_de(registro, ids, defecto):
    """La sesión que escribió el primero de esos hallazgos: la que hay que ajustar para completarlo."""
    for identificador in ids:
        hallazgo = registro.hallazgos.get(identificador)
        if hallazgo and hallazgo["linea"] in LINEAS:
            return LINEAS[hallazgo["linea"]][1]
    return defecto


def nombrados(registro, filas):
    """Los hallazgos que nombran a esas filas de la matriz (por ejemplo, al sustituto que ya resuelve la necesidad)."""
    ids = {fila["id"] for fila in filas}
    return [h["id"] for h in registro.hallazgos.values() if ids & {
        c["id"] for c in (registro.competidor(r) for r in h.get("competidores", [])) if c}]


def motivos_criterio(numero_puerta, criterio, producto, registro):
    """Lo que un criterio que no se cumple dice del veredicto: (fatal, razón, qué lo cambiaría, sesión, hallazgos).
    Fatal es lo que lleva a No viable; lo demás se puede completar ajustando una sesión."""
    clave, detalle = criterio["clave"], llano(criterio["detalle"])
    criterios = producto["criterios"]
    puntaje = producto.get("puntaje")
    principal = registro.principal()
    viables, bajas = registro.viables(), registro.con_confianza_baja()
    fuertes = registro.sustitutos_fuertes()
    if clave == "puntaje":
        if not puntaje:
            return False, "Falta el puntaje de la síntesis", "Registrar el puntaje en la síntesis (sesión 1f)", "1f", []
        minimo = int(criterios["puntaje_minimo_nueva" if tipo_de(producto) == "nueva" else "puntaje_minimo"])
        return (True, "El puntaje es %d/25, bajo el mínimo de %d" % (puntaje["total"], minimo),
                "Evidencia nueva que suba el puntaje a %d/25 o más" % minimo, None, [])
    if clave == "demanda":
        ids = sustento(registro)["demanda"]
        return (True, "La demanda actual tiene confianza %s: ningún hallazgo de demanda está confirmado con señales "
                      "recientes" % NIVELES[confianzas(registro)[0]["demanda"]],
                "Un hallazgo de demanda confirmado con 3 fuentes recientes, una de ellas medida (confianza media o "
                "alta)", None, ids)
    if clave == "problema":
        return (True, "Ningún peldaño documenta el problema con %s fuentes independientes y recientes"
                % criterios["fuentes_minimas"],
                "El problema documentado con %s fuentes independientes y recientes de peldaño 4 o 5"
                % criterios["fuentes_minimas"], None, [])
    if clave == "analogos":
        return (False, "Faltan análogos con tracción (%s)" % detalle,
                "Análogos con tracción registrados en la matriz (sesión 1a)", "1a", [])
    if clave == "intentos":
        if not producto.get("intentos"):
            return (False, "Falta buscar si alguien ya lo intentó", "La búsqueda de intentos anteriores registrada",
                    "1a", [])
        return (True, "Alguien ya lo probó y fracasó por falta de demanda (%s)" % detalle,
                "Evidencia de que el intento anterior fracasó por otra razón que esta idea no repite", None, [])
    if clave in ("diferenciador", "sustituto"):
        ids = nombrados(registro, fuertes) + (principal or {}).get("hallazgos", [])
        if bajas:
            baja = bajas[0]
            faltan = [i for i, _ in registro.sin_triangular(baja)]
            return (False, "%s cumple los criterios de un diferenciador, pero su evidencia no está confirmada (%s)" % (
                baja["id"], ", ".join(faltan)), "Confirmar los hallazgos de %s con 3 fuentes recientes" % baja["id"],
                    sesion_de(registro, faltan, "1g"), faltan)
        if fuertes:
            nombres = "; ".join(nombre_fila(c) for c in fuertes)
            return (True, "Ningún diferenciador supera a %s, que ya resuelve la necesidad gratis" % nombres,
                    "Un diferenciador con evidencia confirmada de algo que %s no resuelve" % nombres, None, ids)
        return (True, "No hay ningún diferenciador viable: nada da una razón para elegir esta app",
                "Un diferenciador con un dolor o un pedido confirmado en 2 competidores o más", None, ids)
    if clave == "principal":
        if not principal:
            return (False, "No hay un diferenciador principal elegido", "Elegir el principal entre los viables (1g)",
                    "1g", [])
        faltan = [i for i, _ in registro.sin_triangular(principal)]
        otros = [d["id"] for d in viables if d["id"] != principal["id"]]
        if otros:
            return (False, "Los hallazgos del principal (%s) no están confirmados, pero %s sí es viable" % (
                principal["id"], ", ".join(otros)), "Elegir como principal un diferenciador viable (%s)"
                % ", ".join(otros), "1g", faltan)
        return (False, "Los hallazgos del principal (%s) no están confirmados (%s)" % (principal["id"], ", ".join(
            faltan)), "Confirmar esos hallazgos con 3 fuentes recientes", sesion_de(registro, faltan, "1g"), faltan)
    if clave == "riesgo":
        if not puntaje:
            return False, "Falta el puntaje de la síntesis", "Registrar el puntaje en la síntesis (sesión 1f)", "1f", []
        bloqueos = registro.bloqueos(objetivo_de(producto))
        ids = [i for lista_ids in bloqueos.values() for i in lista_ids]
        tiendas = ", ".join(sorted(bloqueos))
        if puntaje.get("mitigacion"):
            return (False, "El puntaje no refleja que %s nombra o rechaza la categoría" % tiendas,
                    "Volver a registrar el puntaje con riesgo 1 y la mitigación (1f)", "1f", ids)
        if bloqueos:
            return (True, "%s nombra o rechaza la categoría y no hay una mitigación escrita" % tiendas,
                    "Una mitigación escrita y creíble (por ejemplo, no lanzar en %s)" % tiendas, None, ids)
        return (True, "El riesgo de políticas es 1 y no hay una mitigación escrita",
                "Una mitigación escrita y creíble del riesgo de políticas", None, sustento(registro)["riesgo"])
    if clave == "monetizacion":
        modelos = (producto.get("escenarios") or {}).get("modelos")
        if modelos and not any(m["base"] > 0 for m in modelos):
            return (True, "Ningún modelo de monetización genera ingresos en el caso base",
                    "Un modelo de monetización que genere ingresos con supuestos con fuente", None, [])
        return (False, "Ningún modelo de monetización tiene todos sus supuestos con fuente (%s)" % detalle,
                "Las fuentes que faltan en los supuestos de los escenarios (sesión 2)", "2", [])
    if clave == "meta":
        if producto.get("escenarios") and float(criterios.get("meta_ingresos_mes") or 0):
            return (True, "El caso base no alcanza la meta de ingresos que marcaste como obligatoria (%s)" % detalle,
                    "Un caso base que llegue a la meta, o que la meta deje de ser obligatoria", None, [])
        return False, "Falta comparar el caso base con la meta obligatoria", "Los escenarios (sesión 2)", "2", []
    if clave == "hipotesis":
        if "refutadas" in detalle:
            return (True, "Hay hipótesis críticas refutadas (%s)" % detalle.replace("refutadas: ", ""),
                    "Evidencia nueva que las sostenga, o una idea que no dependa de ellas", None, [])
        return False, "Falta la tabla de hipótesis", "La validación documental (sesión 3)", "3", []
    if clave == "riesgosa":
        return (False, "Falta la hipótesis más riesgosa, con su métrica y su umbral",
                "Marcarla en la validación documental (sesión 3)", "3", [])
    if clave == "sobrevive":
        if not principal:
            return (False, "No hay un diferenciador principal elegido", "Elegir el principal entre los viables (1g)",
                    "1g", [])
        otros = [d["id"] for d in viables if d["id"] != principal["id"]]
        ids = list(principal.get("hallazgos", []))
        if otros:
            return (False, "El principal (%s) no sobrevive al abogado del diablo, pero %s sí es viable" % (
                principal["id"], ", ".join(otros)), "Llevar %s a principal (1g)" % ", ".join(otros), "1g", ids)
        return (True, "El diferenciador principal (%s) no sobrevive al abogado del diablo y no hay otro viable (%s)" % (
            principal["id"], detalle.split(": ", 1)[-1]),
                "Un diferenciador viable que quede sostenido con confianza media o alta", None, ids)
    if clave == "checklist" and "bloqueos" in detalle:
        return (True, "El checklist de políticas tiene bloqueos (%s)" % detalle.replace("bloqueos: ", ""),
                "Un MVP que evite esos bloqueos, con su requisito resuelto", None, [])
    return False, "%s: %s" % (criterio["texto"], detalle), "Completarlo en el PRD (sesión 4)", "4", []


def veredicto(numero_puerta, carpeta, producto, registro, evaluados=None):
    """El veredicto de la skill en una puerta, con reglas fijas: No viable (recomienda descartar), Viable con reservas
    (recomienda ajustar una sesión) o Viable (recomienda seguir), con 1 a 3 razones y qué lo cambiaría."""
    evaluados = evaluados if evaluados is not None else evaluar_puerta(numero_puerta, carpeta, producto, registro)
    fatales, ajustes, hallazgos = [], [], []
    for criterio in evaluados:
        if not criterio["cumple"]:
            fatal, razon, cambiaria, sesion, ids = motivos_criterio(numero_puerta, criterio, producto, registro)
            (fatales if fatal else ajustes).append((razon, cambiaria, sesion))
            hallazgos += ids
    vigente_ = puntaje_vigente(producto, registro) if numero_puerta == 1 else None
    if vigente_ and vigente_["incoherencias"]:
        nueva = tipo_de(producto) == "nueva"
        minimo = int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
        registrado = producto["puntaje"]["total"]
        if registrado >= minimo > vigente_["total"]:
            fatales.insert(0, ("Con las reglas de hoy el puntaje es %d/25 (se registró %d/25), bajo el mínimo de %d"
                               % (vigente_["total"], registrado, minimo),
                               "Evidencia nueva que suba el puntaje a %d/25 o más con las reglas de hoy" % minimo,
                               None))
    if numero_puerta == 1 and producto.get("puntaje") and not fatales:
        por_criterio, global_ = confianzas(registro)
        if global_ < 2:
            debiles = sorted((nivel, c) for c, nivel in por_criterio.items() if nivel is not None and nivel < 2)
            criterio = debiles[0][1]
            ids = sustento(registro)[criterio] or []
            sesion = SESION_CRITERIO[criterio]
            if criterio == "diferenciacion" and registro.principal():
                sesion = sesion_de(registro, [i for i, _ in registro.sin_triangular(registro.principal())], "1g")
            ajustes.append(("La confianza global es baja: %s se apoya%s en evidencia sin confirmar" % (
                ", ".join(NOMBRES_CRITERIO[c] for _, c in debiles), "n" if len(debiles) > 1 else ""),
                "Confirmar con 3 fuentes recientes los hallazgos de %s" % NOMBRES_CRITERIO[criterio], sesion))
            hallazgos += ids
    if not fatales:
        for propuesta in propuestas_de(producto, numero_puerta):
            sesion = propuesta.get("ajustar")
            lineas_sesion = [linea for linea, (_, de_sesion) in LINEAS.items() if de_sesion == sesion]
            if sesion and not vacios_de_herramienta(producto, registro, lineas_sesion):  # se puede cerrar
                ajustes.append(("Hay una propuesta pendiente (%s): %s" % (propuesta["id"], llano(propuesta["texto"])),
                                "Aplicarla al ajustar la sesión %s" % sesion, sesion))
    if fatales:
        nivel, elegidas, sesion = "no", fatales, None
    elif ajustes:
        nivel, elegidas, sesion = "reservas", ajustes, ajustes[0][2]
    else:
        nivel, sesion = "viable", None
        global_ = confianzas(registro)[1]
        elegidas = [("Cumple los %s de la puerta %d" % (plural(len(evaluados), "criterio"), numero_puerta),
                     {1: "Que un hallazgo clave pierda vigencia o aparezca evidencia en contra y la confianza global "
                         "baje a baja (pasaría a Viable con reservas)",
                      2: "Que la validación refute una hipótesis crítica (pasaría a No viable)",
                      3: "Que el MVP deje de caber en el presupuesto o pierda la trazabilidad (pasaría a Viable con "
                         "reservas)"}[numero_puerta], None)]
        if numero_puerta == 1:
            elegidas.append(("La evidencia que la sostiene tiene confianza %s" % NIVELES[global_], None, None))
        principal = registro.principal()
        if principal and numero_puerta in (1, 2):
            elegidas.append(("El diferenciador principal (%s) es viable" % principal["id"], None, None))
            hallazgos += principal.get("hallazgos", [])
        hallazgos += sustento(registro)["demanda"] or []
    razones = [r for r, _, _ in elegidas][:MAXIMO_RAZONES]
    cambiaria = list(dict.fromkeys(c for _, c, _ in elegidas if c))[:MAXIMO_RAZONES]
    if nivel == "reservas":
        cambiaria.append("Con eso, el veredicto pasaría a Viable")
        lineas_sesion = [linea for linea, (_, de_sesion) in LINEAS.items() if de_sesion == sesion]
        if vacios_de_herramienta(producto, registro, lineas_sesion):
            cambiaria.append("La sesión %s tiene vacíos por límite de las herramientas: antes de ajustarla, dale al "
                             "agente un navegador o aporta un CSV de reseñas" % sesion)
    abiertas = [s for s in DEPENDE["P%d" % numero_puerta] if not cerrada(producto, s)]
    return {"puerta": numero_puerta, "nivel": nivel, "titulo": VEREDICTOS[nivel]["titulo"],
            "recomienda": VEREDICTOS[nivel]["recomienda"], "sesion": sesion, "razones": razones,
            "cambiaria": cambiaria, "provisional": abiertas, "hallazgos": list(dict.fromkeys(hallazgos)),
            "incoherencias": (vigente_ or {}).get("incoherencias", [])}


def texto_recomendacion(resultado):
    """'descartar', 'ajustar la sesión 1c' o 'seguir'."""
    if resultado["recomienda"] == "ajustar":
        return "ajustar la sesión %s" % resultado["sesion"]
    return resultado["recomienda"]


def lineas_banner(resultado):
    """El banner de la puerta, para la terminal y para estado.md: el veredicto, la recomendación, las razones y qué
    cambiaría el veredicto. El color va en la marca (y, en una terminal, también en el texto)."""
    datos = VEREDICTOS[resultado["nivel"]]
    raya = "━" * 72
    recomienda = resultado["recomienda"].upper() + (" %s" % resultado["sesion"] if resultado["sesion"] else "")
    lineas = [raya, "%s  PUERTA %d · %s  →  la skill recomienda: %s" % (
        datos["marca"], resultado["puerta"], datos["titulo"].upper(), recomienda), raya]
    if resultado["provisional"]:
        lineas.append("⚠ Provisional: falta cerrar %s." % ", ".join(
            "la sesión %s" % s for s in resultado["provisional"]))
    lineas.append("Por qué:")
    lineas += ["  %d. %s." % (indice, razon) for indice, razon in enumerate(resultado["razones"], start=1)]
    lineas.append("Qué cambiaría el veredicto:")
    lineas += ["  · %s." % texto for texto in resultado["cambiaria"]]
    lineas += ["La decisión es tuya: el comando recomendado va primero. Decidir en contra de la recomendación pide "
               "--motivo.", raya]
    return lineas


def con_color(texto, activo=None):
    """El texto con el banner en color (ANSI) si la salida es una terminal y no hay NO_COLOR; si no, tal cual: en
    estado.md, en un chat o en un archivo, el color lo da la marca del veredicto."""
    if activo is None:
        activo = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    if not activo:
        return texto
    colores = {datos["marca"]: datos["color"] for datos in VEREDICTOS.values()}
    lineas = texto.split("\n")
    pintar = set()
    for indice, linea in enumerate(lineas):
        if linea[:1] in colores and 0 < indice < len(lineas) - 1 and lineas[indice - 1].startswith("━"):
            cierre = next((j for j in range(indice + 2, len(lineas)) if lineas[j].startswith("━")), indice + 1)
            pintar.update((j, colores[linea[:1]]) for j in (indice - 1, indice, indice + 1, cierre))
    for indice, color in pintar:
        lineas[indice] = "\033[1;%sm%s\033[0m" % (color, lineas[indice])
    return "\n".join(lineas)


def comandos_decision(numero_puerta, carpeta, producto, resultado):
    """Los comandos de la decisión, para la terminal del usuario: primero el recomendado; los que van en contra de la
    recomendación llevan --motivo. Una propuesta con sesión trae su Ajustar listo."""
    recomienda = resultado["recomienda"]
    contra = ' --motivo "<por qué decides distinto de la recomendación>"'

    def comando(tipo, resto):
        return orden("decidir --puerta %d %s%s" % (numero_puerta, resto, contra if tipo != recomienda else ""),
                     carpeta)

    motivo = "No viable: %s" % "; ".join(resultado["razones"])
    recomendado = {"seguir": ("Seguir", "--seguir"),
                   "ajustar": ("Ajustar %s" % resultado["sesion"], "--ajustar %s" % resultado["sesion"]),
                   "descartar": ("Descartar", "--descartar %s" % shlex.quote(motivo))}[recomienda]
    lineas = ["   ★ Recomendado · %s: %s" % (recomendado[0], comando(recomienda, recomendado[1]))]
    if recomienda != "seguir":
        lineas.append("   Seguir:    " + comando("seguir", "--seguir"))
    sesiones = [p["ajustar"] for p in propuestas_de(producto, numero_puerta) if p.get("ajustar")]
    for sesion in dict.fromkeys(sesiones):
        if not (recomienda == "ajustar" and sesion == resultado["sesion"]):
            lineas.append("   Ajustar %s: " % sesion + comando("ajustar", "--ajustar %s" % sesion))
    lineas.append("   Ajustar:   " + comando("ajustar", "--ajustar <sesión>"))
    if recomienda != "descartar":
        lineas.append("   Descartar: " + comando("descartar", "--descartar \"<motivo>\""))
    return lineas


# ---------------------------------------------------------------------------------------------------------------
# Flujo: sesiones, puertas y el paso siguiente

def decisiones(carpeta):
    return leer_json(carpeta / "decisiones.json", []) or []


def vigente(lista_decisiones, numero_puerta):
    """La última decisión vigente de una puerta, o None."""
    for decision in reversed(lista_decisiones):
        if decision["puerta"] == numero_puerta and decision.get("vigente"):
            return decision
    return None


def cerrada(producto, sesion):
    return bool(producto["sesiones"].get(sesion, {}).get("cerrada"))


def cumplido(producto, lista_decisiones, nodo):
    if nodo.startswith("P"):
        decision = vigente(lista_decisiones, int(nodo[1]))
        return bool(decision and decision["decision"] == "seguir")
    return cerrada(producto, nodo)


def disponible(producto, lista_decisiones, nodo):
    return all(cumplido(producto, lista_decisiones, previo) for previo in DEPENDE[nodo])


def dependientes(nodo):
    """Todo lo que depende, directa o indirectamente, de una sesión o de una puerta."""
    encontrados, cola = [], [nodo]
    while cola:
        actual = cola.pop()
        for otro, previos in DEPENDE.items():
            if actual in previos and otro not in encontrados:
                encontrados.append(otro)
                cola.append(otro)
    return encontrados


def pendientes_de(carpeta, producto, registro, sesion):
    """Lo que le falta a una sesión para cerrarse."""
    faltan = []
    datos = SESION[sesion]
    texto = leer_md(carpeta, datos["archivo"])
    if not texto:
        faltan.append("falta %s" % datos["archivo"])
    elif PENDIENTE in texto:
        faltan.append("%s todavía tiene %d texto(s) de plantilla (`%s…>`)" % (
            datos["archivo"], texto.count(PENDIENTE), PENDIENTE))
    lista_decisiones = decisiones(carpeta)
    for previo in DEPENDE[sesion]:
        if not cumplido(producto, lista_decisiones, previo):
            faltan.append("antes va %s" % ("la puerta %s, con la decisión de seguir" % previo[1]
                                           if previo.startswith("P") else "la sesión %s" % previo))
    criterios = producto["criterios"]
    linea = next((nombre for nombre, (_, de_sesion) in LINEAS.items() if de_sesion == sesion), None)
    if sesion == "0":
        if PENDIENTE in leer_md(carpeta, "criterios.md"):
            faltan.append("criterios.md todavía tiene texto de plantilla")
        claves = ("presupuesto_semanas", "meta_ingresos_mes") if meta_obligatoria(producto) else (
            "presupuesto_semanas",)
        for clave in claves:
            if not float(criterios.get(clave) or 0):
                faltan.append("falta el criterio `%s` (`criterio --clave %s --valor <n>`)" % (clave, clave))
    if sesion in ("0", "1a", "1b", "1c", "1d", "1e") and objetivo_de(producto) is None:
        faltan.append("falta el objetivo de la sesión 0: `objetivo --mercados <…> --idiomas <…> --tiendas <…|ninguna>`")
    elif linea in COBERTURA_LINEAS:
        huecos = ["%s %s" % (DIMENSIONES[d], v) for d, v, estado, _ in cobertura(producto, registro, linea)[linea]
                  if estado == "falta"]
        if huecos:
            faltan.append("cobertura de la línea %s sin fuentes ni vacío registrado: %s (`fuente … --%s <valor>` o "
                          "`vacio`; `cobertura` muestra el detalle)" % (linea, ", ".join(huecos), "|--".join(
                              COBERTURA_LINEAS[linea])))
    if sesion == "1a":
        if not tipo_de(producto):
            faltan.append("falta registrar el tipo de idea (`tipo --existente|--variante|--nueva --motivo …`)")
        if not registro.competidores:
            faltan.append("la matriz no tiene ninguna fila (`competidor`): si no hay directos, van los análogos "
                          "y los sustitutos")
        if not registro.sustitutos():
            faltan.append("la matriz no tiene ningún sustituto (peldaño 4): registra cómo se resuelve hoy la necesidad "
                          "sin una app así (una función del sistema, una hoja de cálculo, un grupo de chat, papel) con "
                          "`competidor --peldano 4 --sustituto nativo|gratuito|pago --resuelve si|parcial|no`")
        for fila in registro.sustitutos():
            if fila.get("sustituto") not in SUSTITUTOS or fila.get("resuelve") not in RESUELVE:
                faltan.append("%s es un sustituto: le falta `--sustituto nativo|gratuito|pago` o `--resuelve "
                              "si|parcial|no`" % nombre_fila(fila))
    if linea and sesion in ("1a", "1b", "1c", "1d", "1e") and not any(
            h["linea"] == linea for h in registro.hallazgos.values()):
        faltan.append("la línea %s no tiene ningún hallazgo registrado" % linea)
    if sesion == "1f" and not producto.get("puntaje"):
        faltan.append("falta el puntaje (`puntaje --valores d,m,f,r,x`)")
    if sesion == "2" and not producto.get("escenarios"):
        faltan.append("faltan los escenarios de ingresos (`escenarios --entrada escenarios.json`)")
    if sesion == "3":
        faltan.extend(problemas_validacion(hipotesis(carpeta, registro)))
    if sesion == "4":
        datos_prd = prd(carpeta, registro)
        if not any(f["mvp"] for f in datos_prd["funciones"]):
            faltan.append("la tabla de funcionalidades de 04-prd.md no tiene ninguna fila marcada como MVP")
    return faltan


def pasos(carpeta, producto, registro):
    """El paso siguiente: [líneas] según lo que hay en el disco."""
    lista_decisiones = decisiones(carpeta)
    estado_md = carpeta / "estado.md"
    abiertas = [s["id"] for s in SESIONES if not cerrada(producto, s["id"])
                and disponible(producto, lista_decisiones, s["id"])]
    lineas = []
    if abiertas == ["0"]:
        lineas += ["1. Este chat · Sesión 0 · Idea · %s" % texto_modelo(producto, "intermedio"),
                   "   Completa 00-idea.md y criterios.md (el presupuesto de semanas va con `criterio`; la meta de "
                   "ingresos es opcional), registra el objetivo (`objetivo --mercados … --idiomas … --tiendas …`) y "
                   "cierra la sesión:",
                   "   " + orden("cerrar --sesion 0", carpeta)]
        return lineas
    if abiertas:
        if len(abiertas) > 1:
            lineas.append("Puedes abrir estos chats en paralelo (uno por sesión; con subagentes, uno por sesión):")
            lineas.append("")
        sin_herramienta = False
        for indice, sesion in enumerate(abiertas, start=1):
            datos = SESION[sesion]
            lineas.append("%d. Chat nuevo · Sesión %s · %s · %s" % (
                indice, sesion, datos["nombre"], texto_modelo(producto, datos["modelo"])))
            comando = abrir_chat(producto, carpeta, datos["modelo"])
            if comando:
                lineas.append("   Abrir: %s" % comando)
            sin_herramienta = sin_herramienta or not comando
            lineas += ["   Lee: %s" % datos["lee"],
                       "   Texto para pegar:",
                       "     Sigue hb-product con %s: sesión %s · %s. No hagas commit ni push." % (
                           estado_md, sesion, datos["nombre"])]
        esperan = [s for s in ("1g", "1f") if not cerrada(producto, s) and s not in abiertas
                   and cerrada(producto, "0")]
        if "1g" in esperan:
            lineas += ["", "La sesión 1g · Diferenciación se abre apenas cierren 1a y 1b, sin esperar a las demás."]
        if "1f" in esperan:
            lineas += ["" if "1g" not in esperan else None,
                       "La sesión 1f · Síntesis se abre cuando cierren las seis líneas."]
        if sin_herramienta:
            lineas += ["", "Para que cada chat traiga el comando que lo abre con su modelo y su esfuerzo: `%s` "
                       "(una vez; references/modelos.md)." % orden("modelos --herramienta <claude|copilot>", carpeta)]
        return [linea for linea in lineas if linea is not None]
    for numero_puerta in (1, 2, 3):
        nodo = "P%d" % numero_puerta
        if disponible(producto, lista_decisiones, nodo) and not cumplido(producto, lista_decisiones, nodo):
            resultado = veredicto(numero_puerta, carpeta, producto, registro)
            bloque_, _, _ = bloque_puerta(numero_puerta, carpeta, producto, registro, resultado)
            lineas += bloque_
            previa = vigente(lista_decisiones, numero_puerta)
            if previa and previa["decision"] == "ajustar":
                lineas += ["", "La puerta %d se ajustó (sesión %s) y hay que volver a decidirla." % (
                    numero_puerta, previa.get("sesion"))]
            lineas += ["", "Terminal · La skill recomienda; la decisión es tuya (el agente nunca corre este comando). "
                           "Elige uno:"] + comandos_decision(numero_puerta, carpeta, producto, resultado)
            return lineas
    lineas += ["Proceso cerrado: el PRD está aprobado y no queda ningún paso de hb-product %s." % VERSION,
               "Para construir, pide una funcionalidad del PRD a la vez citando su ID (por ejemplo: \"Implementa "
               "F-01 de %s\"): eso lo hace hb-implement." % (carpeta / "04-prd.md")]
    return lineas


def sin_consumo(producto):
    """Las sesiones cerradas que no tienen su consumo anotado (ni lo cubre una fila con --incluye)."""
    anotadas = set()
    for fila in producto.get("consumo", []):
        anotadas.add(fila["sesion"])
        anotadas.update(fila.get("incluye", []))
    return [s["id"] for s in SESIONES if cerrada(producto, s["id"]) and s["id"] not in anotadas]


def texto_siguiente(carpeta, producto, registro=None):
    registro = registro or Registro(carpeta, producto["criterios"])
    tipo = tipo_de(producto)
    titulo = "Siguiente paso · %s (%s)" % (producto["nombre"], "idea %s" % tipo if tipo else "tipo de idea sin "
                                           "registrar")
    avisos = []
    for numero_puerta in (3, 2, 1):  # solo la última puerta decidida: es la que abrió el paso que sigue
        decision = vigente(decisiones(carpeta), numero_puerta)
        if decision and decision["decision"] == "seguir" and not avisos:
            avisos.append("Puerta %d: seguir, decidida el %s%s; si no fue tu decisión: `%s`" % (
                numero_puerta, decision["fecha"].replace("T", " "),
                " (%s)" % decision["desde"] if decision.get("desde") else "",
                orden("decidir --puerta %d --reabrir" % numero_puerta, carpeta)))
    pendientes = sin_consumo(producto) if producto.get("consumo") else []  # solo si ya se anotó alguno
    if pendientes:
        avisos.append("Consumo sin anotar (opcional): %s · al cerrar cada chat, `%s`" % (
            ", ".join(pendientes), orden("consumo --sesion <id> --costo '<USD>'", carpeta)))
    lista_decisiones = decisiones(carpeta)
    sin_sesiones = not any(not cerrada(producto, s["id"]) and disponible(producto, lista_decisiones, s["id"])
                           for s in SESIONES)
    filas = producto.get("consumo") or []
    if filas and sin_sesiones and not any(f["sesion"] == "orquestador" for f in filas):
        avisos.append("Consumo del chat orquestador (si lo usaste): al terminar, anota lo que muestre /cost (en "
                      "Copilot, /usage, con --creditos); si ese total ya incluye a los subagentes, agrega --incluye "
                      "con sus sesiones:")
        avisos.append("   " + orden("consumo --sesion orquestador --costo '<USD>' --tokens '<tokens>'", carpeta))
    return "\n".join([titulo, ""] + pasos(carpeta, producto, registro) + ([""] + avisos if avisos else []))


def texto_resumen(carpeta, producto, registro):
    criterios = producto["criterios"]
    tipo = producto.get("tipo")
    lista_decisiones = decisiones(carpeta)
    claves = [h for h in registro.hallazgos.values() if h.get("critico")]
    sin_triangular = [h["id"] for h in claves if not registro.evaluar(h)["triangulado"]]
    principal = registro.principal()
    lineas = [
        "- **Idea:** %s · creada el %s" % (producto["nombre"], producto["creado"]),
        "- **Tipo de idea:** %s" % ("%s (%s)" % (tipo["valor"], tipo["motivo"]) if tipo else "sin registrar (lo "
                                    "registra la sesión 1a)"),
        "- **Criterios:** puntaje mínimo %s/25 (%s si la idea es nueva) · vigencia de %s meses · %s fuentes "
        "independientes · %s · %s semanas" % (
            criterios["puntaje_minimo"], criterios["puntaje_minimo_nueva"], criterios["vigencia_meses"],
            criterios["fuentes_minimas"], texto_meta(producto), numero(float(criterios["presupuesto_semanas"] or 0))),
        "- **Evidencia:** %d fuentes · %d hallazgos (%d clave, %d sin triangular%s) · %d competidores en la matriz "
        "· %d diferenciadores (%d viables%s%s)" % (
            len(registro.fuentes), len(registro.hallazgos), len(claves), len(sin_triangular),
            (": " + ", ".join(sin_triangular)) if sin_triangular else "", len(registro.competidores),
            len(registro.diferenciadores), len(registro.viables()),
            ", %d con confianza baja" % len(registro.con_confianza_baja()) if registro.con_confianza_baja() else "",
            "; principal: %s" % principal["id"] if principal else ""),
    ]
    objetivo = objetivo_de(producto)
    if objetivo:
        mapa = cobertura(producto, registro)
        huecos = sum(1 for filas in mapa.values() for fila in filas if fila[2] == "falta")
        vacios = [fila[3] for filas in mapa.values() for fila in filas if fila[2] == "vacio"]
        lineas.append("- **Objetivo:** mercados %s · idiomas %s · tiendas %s · cobertura: %d hueco(s) sin registrar, "
                      "%d vacío(s)%s" % (
                          ", ".join(objetivo["mercados"]) or "—", ", ".join(objetivo["idiomas"]) or "—",
                          ", ".join(objetivo["tiendas"]) or "ninguna", huecos, len(vacios),
                          " (%d por límite de las herramientas)" % sum(1 for v in vacios if v["motivo"] == "herramienta")
                          if vacios else ""))
    else:
        lineas.append("- **Objetivo:** sin registrar (mercados, idiomas y tiendas: `objetivo`, en la sesión 0)")
    puntaje = producto.get("puntaje")
    if puntaje:
        lineas.append("- **Puntaje:** %d/25 · confianza global %s" % (
            puntaje["total"], NIVELES[confianzas(registro)[1]]))
    escenarios = producto.get("escenarios")
    if escenarios:
        lineas.append("- **Escenario base:** %s %s al mes%s" % (
            numero(escenarios["base"]), escenarios["moneda"],
            " · " + " · ".join(escenarios["rotulos"]) if escenarios["rotulos"] else ""))
    consumo = producto.get("consumo", [])
    if consumo:
        lineas.append("- **Consumo anotado:** %s · total %s%s" % (
            " · ".join("%s %s" % (fila["sesion"], texto_consumo(fila)) for fila in consumo),
            texto_total(consumo), " (sin anotar: %s)" % ", ".join(sin_consumo(producto))
            if sin_consumo(producto) else ""))
    cambios = producto.get("criterios_cambios", [])
    if cambios:
        lineas.append("- **Criterios cambiados después de la sesión 0:** %s" % "; ".join(
            "%s de %s a %s el %s (%s)" % (c["clave"], c["antes"], c["despues"], c["fecha"][:10], c["motivo"])
            for c in cambios))
    lineas += ["", "| Sesión | Estado |", "| --- | --- |"]
    for sesion in SESIONES:
        fecha = producto["sesiones"].get(sesion["id"], {}).get("cerrada")
        estado = "cerrada el %s" % fecha[:10] if fecha else (
            "abierta" if disponible(producto, lista_decisiones, sesion["id"]) else "en espera")
        lineas.append("| %s · %s | %s |" % (sesion["id"], sesion["nombre"], estado))
    lineas += ["", "| Puerta | Decisión |", "| --- | --- |"]
    for numero_puerta, nombre in PUERTAS.items():
        decision = vigente(lista_decisiones, numero_puerta)
        if decision:
            detalle = "%s el %s%s · cumplía %d de %d criterios" % (
                decision["decision"], decision["fecha"].replace("T", " "),
                " (%s)" % decision["desde"] if decision.get("desde") else "", decision["cumple"], decision["total"])
            if decision.get("sesion"):
                detalle += " · sesión %s" % decision["sesion"]
            recomendacion = decision.get("recomendacion")
            if recomendacion:
                detalle += " · la skill recomendaba %s" % texto_recomendacion(recomendacion)
            if decision.get("contra_recomendacion"):
                detalle += " · **contra la recomendación**: %s" % decision.get("motivo_decision", "")
        else:
            detalle = "pendiente"
        lineas.append("| P%d · %s | %s |" % (numero_puerta, nombre, detalle))
    return "\n".join(lineas)


def bloque(texto, nombre, contenido):
    """Reemplaza lo que hay entre <!-- producto:nombre --> y <!-- /producto:nombre -->."""
    patron = re.compile(r"(<!-- producto:%s -->\n).*?(<!-- /producto:%s -->)" % (nombre, nombre), re.S)
    if not patron.search(texto):
        return texto.rstrip("\n") + "\n\n<!-- producto:%s -->\n%s\n<!-- /producto:%s -->\n" % (
            nombre, contenido, nombre)
    return patron.sub(lambda m: m.group(1) + contenido + "\n" + m.group(2), texto)


def actualizar_estado(carpeta, producto):
    """Reescribe los bloques de estado.md que mantiene el script y devuelve el texto del paso siguiente."""
    registro = Registro(carpeta, producto["criterios"])  # siempre del disco: el comando pudo escribir después de abrir
    siguiente = texto_siguiente(carpeta, producto, registro)
    ruta = carpeta / "estado.md"
    if ruta.is_file():
        texto = ruta.read_text(encoding="utf-8")
    else:
        texto = plantilla("estado.md", producto)
    texto = bloque(texto, "siguiente", "```text\n%s\n```" % siguiente)
    texto = bloque(texto, "resumen", texto_resumen(carpeta, producto, registro))
    escribir(ruta, texto)
    return siguiente


def plantilla(nombre, producto):
    texto = (PLANTILLAS / nombre).read_text(encoding="utf-8")
    titulo = producto["nombre"]
    if nombre.endswith(".json"):
        titulo = json.dumps(titulo, ensure_ascii=False)[1:-1]  # un nombre con comillas no rompe el JSON
    return texto.replace("{{NOMBRE}}", titulo).replace("{{FECHA}}", producto["creado"])


def ideas_archivadas(carpeta):
    base = carpeta / "archivo"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if (p / "producto.json").is_file())


def mover_a_archivo(carpeta, producto, motivo, por):
    producto["archivo"] = {"fecha": ahora(), "motivo": motivo, "por": por}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    base = carpeta / "archivo"
    base.mkdir(exist_ok=True)
    destino, intento = base / producto["slug"], 2
    while destino.exists():
        destino = base / ("%s-%d" % (producto["slug"], intento))
        intento += 1
    destino.mkdir()
    for elemento in sorted(carpeta.iterdir()):
        if elemento.name not in ("archivo", CANDADO):
            shutil.move(str(elemento), str(destino / elemento.name))
    return destino


# ---------------------------------------------------------------------------------------------------------------
# Comandos

def cmd_nuevo(args):
    carpeta = resolver_carpeta(args)
    if (carpeta / "producto.json").exists():
        raise Fallo("Ya hay una idea activa en %s (%s). Para empezar otra, archívala antes: `archivar --motivo "
                    "\"<motivo>\"`." % (carpeta, cargar(carpeta)["nombre"]))
    carpeta.mkdir(parents=True, exist_ok=True)
    with bloqueo(carpeta):
        criterios = dict(CRITERIOS_DEFECTO)
        if args.meta is not None:
            criterios["meta_ingresos_mes"] = positivo(args.meta, "--meta")
        if args.semanas is not None:
            criterios["presupuesto_semanas"] = positivo(args.semanas, "--semanas")
        if args.moneda:
            criterios["moneda"] = args.moneda.upper()
        if args.meta_obligatoria:
            criterios["meta_obligatoria"] = "si"
        objetivo = {d: etiquetas(getattr(args, d), d) for d in DIMENSIONES}
        objetivo = {d: v for d, v in objetivo.items() if v is not None} or None  # se completa con `objetivo`
        producto = {"formato": FORMATO, "version": VERSION, "nombre": args.nombre.strip(), "slug": slug(args.nombre),
                    "creado": hoy().isoformat(), "tipo": None, "tipo_historial": [], "criterios": criterios,
                    "criterios_cambios": [], "sesiones": {}, "intentos": [], "puntaje": None, "escenarios": None,
                    "archivo": None, "objetivo": objetivo, "objetivo_cambios": [], "modelos": {}, "herramienta": None, "propuestas": [], "consumo": []}
        creados, existentes = [], []
        for origen_plantilla, destino in ARCHIVOS_PLANTILLA:
            ruta = carpeta / destino
            if ruta.exists():
                existentes.append(destino)  # nunca se pisa lo que ya está
                continue
            escribir(ruta, plantilla(origen_plantilla, producto))
            creados.append(destino)
        for linea in ("competencia", "voz-del-usuario", "demanda", "monetizacion", "politicas", "diferenciacion"):
            if not ruta_linea(carpeta, linea).exists():
                escribir_json(ruta_linea(carpeta, linea), linea_vacia(linea))
        if not (carpeta / "decisiones.json").exists():
            escribir_json(carpeta / "decisiones.json", [])
        guardar(carpeta, producto)
        escribir_criterios(carpeta, producto)
        siguiente = actualizar_estado(carpeta, producto)
    print("✔ Idea \"%s\" creada en %s (%d archivos)" % (producto["nombre"], carpeta, len(creados)))
    if existentes:
        print("· Ya existían y no se tocaron: %s" % ", ".join(existentes))
    print("\n" + siguiente)


def etiquetas(texto, dimension):
    """'MX, es-419' → ['MX', 'es-419'] (sin repetir); 'ninguna' en tiendas → []; None si no se pasó."""
    if texto is None:
        return None
    valores = list(dict.fromkeys(lista(texto)))
    if dimension == "tiendas" and [normal(v) for v in valores] in (["ninguna"], ["ninguno"]):
        return []
    if not valores:
        raise Fallo("--%s no puede ir vacío%s" % (dimension, " (sin tiendas: --tiendas ninguna)"
                                                  if dimension == "tiendas" else ""))
    return valores


def positivo(valor, nombre):
    try:
        numero_valor = float(valor)
    except (TypeError, ValueError):
        raise Fallo("%s debe ser un número, no '%s'" % (nombre, valor))
    if numero_valor <= 0:
        raise Fallo("%s debe ser mayor que cero" % nombre)
    return int(numero_valor) if numero_valor == int(numero_valor) else numero_valor


def escribir_criterios(carpeta, producto):
    """Pone en criterios.md la tabla de los criterios vigentes y los cambios hechos después de la sesión 0."""
    ruta = carpeta / "criterios.md"
    if not ruta.is_file():
        return
    criterios = producto["criterios"]
    lineas = ["| Criterio | Valor |", "| --- | --- |"]
    lineas += ["| `%s` | %s |" % (clave, criterios[clave]) for clave in CRITERIOS_DEFECTO]
    cambios = producto.get("criterios_cambios", [])
    if cambios:
        lineas += ["", "**Criterios cambiados después de la sesión 0:**", ""]
        lineas += ["- `%s`: de %s a %s el %s. Motivo: %s" % (c["clave"], c["antes"], c["despues"], c["fecha"][:10],
                                                           c["motivo"]) for c in cambios]
    escribir(ruta, bloque(ruta.read_text(encoding="utf-8"), "criterios", "\n".join(lineas)))


def cmd_criterio(args):
    carpeta, producto, registro = abrir(args)
    criterios = producto["criterios"]
    if not args.clave:
        for clave in CRITERIOS_DEFECTO:
            print("%-22s %s" % (clave, criterios[clave]))
        print("\nSiguiente paso: para cambiar uno, `criterio --clave <clave> --valor <valor>`; después de cerrar la "
              "sesión 0 hace falta `--motivo`.")
        return
    if args.clave not in CRITERIOS_DEFECTO:
        raise Fallo("No existe el criterio '%s'. Los que hay: %s" % (args.clave, ", ".join(CRITERIOS_DEFECTO)))
    if args.valor is None:
        raise Fallo("Falta --valor")
    if args.clave == "moneda":
        valor = args.valor.upper()
    elif args.clave == "meta_obligatoria":
        if normal(args.valor) not in ("si", "no"):
            raise Fallo("meta_obligatoria es si o no: con si, la meta de ingresos pasa a ser criterio de la puerta 2")
        valor = normal(args.valor)
    elif args.clave == "meta_ingresos_mes" and args.valor.strip() in ("0", "0.0"):
        valor = 0  # la meta es opcional: 0 la quita
    else:
        valor = positivo(args.valor, "--valor")
    if args.clave == "puntaje_minimo" or args.clave == "puntaje_minimo_nueva":
        if not 5 <= valor <= 25:
            raise Fallo("El puntaje mínimo va de 5 a 25")
    antes = criterios[args.clave]
    fijados = cerrada(producto, "0")
    if fijados and not args.motivo:
        raise Fallo("Los criterios se fijaron al cerrar la sesión 0. Cambiar `%s` exige --motivo \"<por qué>\": "
                    "queda registrado y las puertas lo muestran." % args.clave)
    criterios[args.clave] = valor
    if fijados and valor != antes:
        producto.setdefault("criterios_cambios", []).append(
            {"clave": args.clave, "antes": antes, "despues": valor, "motivo": args.motivo.strip(), "fecha": ahora(),
             "desde": origen()})
    guardar(carpeta, producto)
    escribir_criterios(carpeta, producto)
    actualizar_estado(carpeta, producto)
    print("✔ %s: %s → %s%s" % (args.clave, antes, valor, " (criterio cambiado, con su motivo)" if fijados else ""))
    if args.clave in ("meta_ingresos_mes", "meta_obligatoria"):
        print("· La meta de ingresos: %s. %s" % (texto_meta(producto), "Es criterio de la puerta 2." if
                                                  meta_obligatoria(producto) else "Solo es una referencia: no "
                                                  "bloquea ninguna puerta."))
    print("Siguiente paso: `siguiente` muestra por dónde seguir.")


def cmd_tipo(args):
    carpeta, producto, registro = abrir(args)
    elegido = next((t for t in TIPOS_IDEA if getattr(args, t)), None)
    if not elegido:
        tipo = producto.get("tipo")
        limites = presupuesto_de(producto)
        if tipo:
            print("Tipo de idea: %s (%s) · registrado el %s" % (tipo["valor"], tipo["motivo"], tipo["fecha"][:10]))
        else:
            print("Tipo de idea: sin registrar. Lo registra la sesión 1a; mientras tanto, investiga como si hubiera "
                  "competencia y vuelve a consultar antes de cerrar tu línea.")
        print("Presupuesto por línea: %d búsquedas y %d lecturas." % (limites["busquedas"], limites["lecturas"]))
        if tipo and tipo["valor"] == "nueva":
            print("Idea nueva: trabaja por analogía desde el inicio (references/analogia.md) y registra el peldaño "
                  "de cada fuente.")
        print("Siguiente paso: sigue con tu línea; `siguiente` muestra los carriles.")
        return
    if not args.motivo:
        raise Fallo("Registrar el tipo exige --motivo \"<qué competidores directos hay, o por qué no hay>\"")
    anterior = producto.get("tipo")
    if anterior:
        producto.setdefault("tipo_historial", []).append(anterior)
    producto["tipo"] = {"valor": elegido, "motivo": args.motivo.strip(), "fecha": ahora()}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    limites = presupuesto_de(producto)
    print("✔ Tipo de idea: %s%s" % (elegido, " (antes: %s)" % anterior["valor"] if anterior else ""))
    print("Presupuesto por línea: %d búsquedas y %d lecturas." % (limites["busquedas"], limites["lecturas"]))
    if elegido == "nueva":
        print("Siguiente paso: sube por la escalera de analogía (references/analogia.md), registra los análogos y "
              "los sustitutos en la matriz con su peldaño, y busca si alguien ya lo intentó (`intento`).")
    else:
        print("Siguiente paso: completa la matriz de competidores (`competidor`) y registra los hallazgos.")


def fecha_publicacion(texto):
    """AAAA-MM-DD o AAAA-MM (día 1) → AAAA-MM-DD; 'desconocida' (o 'sin-fecha') → None (no cuenta como vigente)."""
    if texto in SIN_FECHA:
        return None
    coincide = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$", texto)
    if not coincide:
        raise Fallo("--publicada debe ser AAAA-MM-DD, AAAA-MM o desconocida, no '%s'" % texto)
    try:
        fecha = date(int(coincide.group(1)), int(coincide.group(2)), int(coincide.group(3) or 1))
    except ValueError:
        raise Fallo("--publicada no es una fecha válida: '%s'" % texto)
    if fecha > hoy():
        raise Fallo("--publicada está en el futuro: '%s'" % texto)
    return fecha.isoformat()


def url_normal(url):
    partes = urlsplit(url.strip())
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise Fallo("--url debe empezar con http:// o https://, no '%s'" % url)
    dominio = partes.netloc.lower()
    dominio = dominio[4:] if dominio.startswith("www.") else dominio
    ruta = partes.path.rstrip("/")
    return dominio, "%s://%s%s%s" % (partes.scheme, dominio, ruta, ("?" + partes.query) if partes.query else "")


def linea_valida(nombre):
    if nombre not in LINEAS:
        raise Fallo("No existe la línea '%s'. Las que hay: %s" % (nombre, ", ".join(LINEAS)))
    return nombre


def columna_csv(encabezados, tipo):
    """El encabezado de un CSV que corresponde a fecha, estrellas, texto o idioma; None si no hay ninguno."""
    normales = [normal(e) for e in encabezados]
    for candidato in COLUMNAS_CSV[tipo]:
        if candidato in normales:
            return encabezados[normales.index(candidato)]
    return None


def fecha_csv(texto):
    """La fecha AAAA-MM-DD de una celda ('2026-05-03 10:12:00', '2026/05/03', '2026-05-03T10:12Z'); None si no hay."""
    coincide = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", texto or "")
    if not coincide:
        return None
    try:
        return date(int(coincide.group(1)), int(coincide.group(2)), int(coincide.group(3)))
    except ValueError:
        return None


def leer_csv(ruta):
    """Las reseñas de un CSV exportado: {"filas": [{fecha, estrellas, texto, idioma}], "columnas": {...}}. Nunca lee
    las columnas de autor: solo las cuatro que reconoce."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise Fallo("No existe el archivo %s" % ruta)
    try:
        contenido = ruta.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        contenido = ruta.read_text(encoding="latin-1")
    try:
        dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    encabezados = [e for e in (lector.fieldnames or []) if e is not None]
    columnas = {tipo: columna_csv(encabezados, tipo) for tipo in COLUMNAS_CSV}
    if not columnas["texto"] and not columnas["estrellas"]:
        raise Fallo("%s no tiene una columna de texto ni de estrellas reconocible (por ejemplo: review, text, "
                    "rating, stars, texto, estrellas). Encabezados: %s" % (ruta.name, ", ".join(encabezados)))
    filas = []
    for fila in lector:
        estrellas = re.search(r"\d+", fila.get(columnas["estrellas"]) or "") if columnas["estrellas"] else None
        idioma = (fila.get(columnas["idioma"]) or "").strip().lower() if columnas["idioma"] else ""
        filas.append({
            "fecha": fecha_csv(fila.get(columnas["fecha"])) if columnas["fecha"] else None,
            "estrellas": int(estrellas.group(0)) if estrellas and 1 <= int(estrellas.group(0)) <= 5 else None,
            "texto": " ".join((fila.get(columnas["texto"]) or "").split()) if columnas["texto"] else "",
            "idioma": re.split(r"[-_]", idioma)[0] if idioma else "",
        })
    return {"filas": filas, "columnas": columnas}


def resumen_csv(datos):
    """'240 filas · del 2026-01-03 al 2026-11-10 · 1–3★: 85 · idiomas: es (200), pt (40)'."""
    filas = datos["filas"]
    fechas = sorted(f["fecha"] for f in filas if f["fecha"])
    bajas = sum(1 for f in filas if f["estrellas"] and f["estrellas"] <= 3)
    idiomas = {}
    for fila in filas:
        if fila["idioma"]:
            idiomas[fila["idioma"]] = idiomas.get(fila["idioma"], 0) + 1
    partes = ["%d fila(s)" % len(filas)]
    if fechas:
        partes.append("del %s al %s" % (fechas[0].isoformat(), fechas[-1].isoformat()))
    if datos["columnas"]["estrellas"]:
        partes.append("1–3★: %d" % bajas)
    if idiomas:
        partes.append("idiomas: %s" % ", ".join("%s (%d)" % (i, n) for i, n in sorted(
            idiomas.items(), key=lambda par: -par[1])))
    return " · ".join(partes)


def cmd_fuente(args):
    carpeta, producto, registro = abrir(args)
    linea = linea_valida(args.linea)
    if bool(args.url) == bool(args.archivo):
        raise Fallo("Una fuente lleva --url (una página pública) o --archivo (un CSV de reseñas que aportó el "
                    "usuario), una de las dos")
    resumen = args.resumen.strip()
    if len(resumen.splitlines()) > 3 or len(resumen) > 400:
        raise Fallo("El resumen de una fuente tiene 3 líneas como máximo (400 caracteres): tiene %d líneas y %d "
                    "caracteres" % (len(resumen.splitlines()), len(resumen)))
    autor = (args.autor or "").strip()
    if re.match(r"^(@|u/|/u/)", autor):
        raise Fallo("--autor no puede ser un nombre de usuario: es la app, la empresa o el medio que publica")
    marcas = {d: etiquetas(getattr(args, d), d) or [] for d in DIMENSIONES}
    publicada, csv_datos = args.publicada, None
    if args.archivo:
        if not autor:
            raise Fallo("Un CSV necesita --autor: de qué app y de qué tienda son las reseñas (por ejemplo, \"App A · "
                        "Google Play\"). Dos CSV de la misma app cuentan como una sola fuente.")
        ruta_csv = Path(os.path.abspath(os.path.expanduser(args.archivo)))
        csv_datos = leer_csv(ruta_csv)
        if not csv_datos["filas"]:
            raise Fallo("%s no tiene filas" % ruta_csv)
        dominio, url = "archivo:%s" % slug(autor), "archivo:%s" % ruta_csv
        fechas = [f["fecha"] for f in csv_datos["filas"] if f["fecha"]]
        if publicada == "auto":
            if not fechas:
                raise Fallo("El CSV no tiene una columna de fecha reconocible: pasa --publicada AAAA-MM-DD (la de la "
                            "reseña más reciente)")
            pasadas = [f for f in fechas if f <= hoy()]
            if not pasadas:
                raise Fallo("Las fechas del CSV están en el futuro: pasa --publicada AAAA-MM-DD")
            publicada = max(pasadas).isoformat()
        if not marcas["idiomas"]:  # los idiomas que trae el CSV, si tiene esa columna
            marcas["idiomas"] = sorted({f["idioma"] for f in csv_datos["filas"] if f["idioma"]})
    else:
        if publicada == "auto":
            raise Fallo("--publicada auto solo sirve con --archivo (toma la fecha de la reseña más reciente)")
        dominio, url = url_normal(args.url)
    version = (args.version or "").strip()
    if args.tipo == "oficial":
        if args.archivo:
            raise Fallo("Una fuente oficial es la página pública de la norma (--url), no un archivo")
        if not version and publicada in SIN_FECHA:
            raise Fallo("Una fuente oficial lleva la versión o la fecha de la norma que leíste: --version \"<versión o "
                        "fecha de la última actualización>\" o --publicada AAAA-MM-DD")
    elif version:
        raise Fallo("--version es para una fuente oficial (--tipo oficial): la versión o la fecha de la norma")
    if args.acumulado and args.tipo != "medido":
        raise Fallo("--acumulado marca un dato medido (descargas o valoraciones desde el lanzamiento): va con "
                    "--tipo medido")
    consultada = fecha_publicacion(args.consultada) if args.consultada else hoy().isoformat()
    if args.consultada and consultada is None:
        raise Fallo("--consultada es la fecha en que leíste la fuente: AAAA-MM-DD")
    fecha = fecha_publicacion(publicada)
    if fecha and fecha > consultada:
        raise Fallo("--publicada (%s) es posterior a la fecha de consulta (%s): nada se lee antes de publicarse" % (
            fecha, consultada))
    datos = cargar_linea(carpeta, linea)
    existente = next((f for f in datos["fuentes"] if f["url"] == url and not f.get("anulado")), None)
    if existente:
        agregadas = []
        for dimension, valores in marcas.items():
            for valor in valores:
                if normal(valor) not in [normal(v) for v in existente.get(dimension, [])]:
                    existente.setdefault(dimension, []).append(valor)
                    agregadas.append(valor)
        if agregadas:
            escribir_json(ruta_linea(carpeta, linea), datos)
        print("· %s ya estaba registrada con %s: no se duplica%s." % (
            existente["id"], "ese archivo" if args.archivo else "esa URL",
            "; se le agregó la cobertura %s" % ", ".join(agregadas) if agregadas else ""))
        identificador = existente["id"]
    else:
        identificador = "S-%s-%d" % (LINEAS[linea][0], len(datos["fuentes"]) + 1)
        fuente = {"id": identificador, "linea": linea, "url": url, "dominio": dominio, "autor": autor,
                  "publicada": fecha, "consultada": consultada, "tipo": args.tipo, "peldano": args.peldano,
                  "resumen": resumen}
        fuente.update((d, v) for d, v in marcas.items() if v)
        if args.archivo:
            fuente["archivo"] = str(ruta_csv)
        if version:
            fuente["version"] = version
        if args.acumulado:
            fuente["acumulado"] = True
        datos["fuentes"].append(fuente)
        escribir_json(ruta_linea(carpeta, linea), datos)
        registro = Registro(carpeta, producto["criterios"])
        print("✔ %s registrada (%s · peldaño %d, %s · %s · %s)" % (
            identificador, linea, args.peldano, PELDANOS[args.peldano][0], args.tipo,
            "vigente" if registro.vigente(fuente) else "sin fecha o fuera de la ventana de vigencia: no cuenta para "
            "la confianza ni para triangular"))
        if fecha and fecha == consultada and not args.archivo:
            print("⚠ La fecha de publicación es la misma que la de consulta (%s). Si es un dato vivo (el contador de "
                  "una ficha, una tendencia de los últimos meses), está bien; si es una reseña, un artículo, un hilo o "
                  "una política, registra su fecha real o `--publicada desconocida` (`anular --id %s` y otra vez "
                  "`fuente`)." % (fecha, identificador))
        if args.tipo == "oficial" and linea in BASTA_OFICIAL:
            print("· Fuente oficial (%s): basta sola para un hallazgo de la línea %s y cuenta como vigente mientras "
                  "la hayas consultado dentro de la ventana." % (version or "publicada el %s" % fecha, linea))
        if args.acumulado:
            print("· Dato acumulado: en la línea demanda es contexto, no una señal actual; no cuenta para la confianza "
                  "ni para triangular la demanda (references/puntaje.md).")
        if csv_datos:
            print("· CSV de %s: %s. Lee las reseñas con `resenas --archivo …`, sin abrir el archivo entero." % (
                autor, resumen_csv(csv_datos)))
        cubre = ["%s %s" % (DIMENSIONES[d], ", ".join(v)) for d, v in marcas.items() if v]
        if cubre:
            print("· Cobertura: %s" % " · ".join(cubre))
        elif linea in COBERTURA_LINEAS:
            print("· Sin etiquetas de cobertura: agrega --%s si la fuente es de un mercado, un idioma o una tienda "
                  "del objetivo (`cobertura` muestra lo que falta)." % " / --".join(COBERTURA_LINEAS[linea]))
        otra = next((f for f in registro.fuentes.values() if f["url"] == url and f["id"] != identificador), None)
        if otra:
            print("· La misma %s ya es %s en la línea %s: al triangular cuentan como una sola." % (
                "fuente" if args.archivo else "URL", otra["id"], otra["linea"]))
    cantidad = sum(1 for f in datos["fuentes"] if not f.get("anulado"))
    limite = presupuesto_de(producto)["lecturas"]
    print("Fuentes de la línea %s: %d (presupuesto de lecturas: %d)" % (linea, cantidad, limite))
    if cantidad >= 0.8 * limite:
        print("⚠ Llegaste al 80 % del presupuesto de lecturas de esta línea: dilo y cierra con lo que tienes.")
    print("Siguiente paso: cuando un hallazgo tenga sus fuentes, `hallazgo --linea %s --texto \"…\" --fuentes %s,…`"
          % (linea, identificador))


def ids_existentes(ids, universo, que):
    faltan = [i for i in ids if i not in universo]
    if faltan:
        raise Fallo("No existe(n) %s: %s" % (que, ", ".join(faltan)))
    return ids


def cmd_hallazgo(args):
    carpeta, producto, registro = abrir(args)
    linea = linea_valida(args.linea)
    fuentes = ids_existentes(lista(args.fuentes), registro.fuentes, "la(s) fuente(s)")
    if not fuentes:
        raise Fallo("Un hallazgo necesita al menos una fuente (--fuentes S-…): sin fuente va como ⚠ Sin evidencia "
                    "en el texto, no en el registro")
    contra = ids_existentes(lista(args.en_contra), registro.fuentes, "la(s) fuente(s) en contra")
    repetidas = sorted(set(fuentes) & set(contra))
    if repetidas:
        raise Fallo("Una fuente no puede estar a favor y en contra a la vez: %s" % ", ".join(repetidas))
    bloquea = list(dict.fromkeys(lista(args.bloquea)))
    if bloquea:
        if linea != "politicas":
            raise Fallo("--bloquea es de la línea politicas: la tienda que nombra la categoría o la rechaza")
        objetivo = objetivo_de(producto)
        fuera = [t for t in bloquea if objetivo and normal(t) not in [normal(v) for v in objetivo["tiendas"]]]
        if fuera:
            raise Fallo("%s no está entre las tiendas del objetivo (%s)" % (
                ", ".join(fuera), ", ".join(objetivo["tiendas"]) or "ninguna"))
    datos = cargar_linea(carpeta, linea)
    identificador = "H-%s-%d" % (LINEAS[linea][0], len(datos["hallazgos"]) + 1)
    hallazgo = {"id": identificador, "linea": linea, "texto": args.texto.strip(), "fuentes": fuentes,
                "en_contra": contra, "sin_contra": (args.sin_contra or "").strip(), "critico": bool(args.critico),
                "competidores": lista(args.competidores), "fecha": ahora()}
    if bloquea:
        hallazgo["bloquea"] = bloquea
    datos["hallazgos"].append(hallazgo)
    escribir_json(ruta_linea(carpeta, linea), datos)
    evaluacion = registro.evaluar(hallazgo)
    print("✔ %s registrado%s · %s (peldaño %d, %s · %d fuente(s) independiente(s) y vigente(s)%s)" % (
        identificador, " como hallazgo clave" if args.critico else "", registro.etiqueta(hallazgo),
        evaluacion["peldano"], PELDANOS[evaluacion["peldano"]][0], evaluacion["independientes"],
        " · %d en contra" % evaluacion["contra"] if evaluacion["contra"] else ""))
    if evaluacion["no_vigentes"]:
        print("· %s sin fecha o fuera de la ventana de %s meses: no cuenta(n) para la confianza ni para triangular." % (
            ", ".join(evaluacion["no_vigentes"]), producto["criterios"]["vigencia_meses"]))
    sin_fila = [c for c in hallazgo["competidores"] if not registro.competidor(c)]
    if sin_fila:
        print("· Competidor(es) sin fila en la matriz todavía: %s (la matriz la registra la sesión 1a)" % ", ".join(
            sin_fila))
    if args.critico and evaluacion["faltan"]:
        print("⚠ Para cumplir la regla de triangulación: %s." % "; ".join(evaluacion["faltan"]))
    if args.critico and evaluacion["sin_busqueda"]:
        print("⚠ Falta registrar la búsqueda de evidencia en contra (regla 4): --en-contra o --sin-contra.")
    if evaluacion["oficial"]:
        print("· Triangulado por la fuente oficial %s: en la línea %s, la norma misma basta." % (
            ", ".join(evaluacion["oficial"]), linea))
    if bloquea:
        print("⚠ Bloqueante en %s: esa tienda nombra o rechaza la categoría, así que el riesgo de políticas es 1 en "
              "ella. La puerta 1 solo lo da por cumplido con una mitigación escrita y creíble (`puntaje … "
              "--mitigacion \"…\"`), por ejemplo, no lanzar en esa tienda." % ", ".join(bloquea))
    print("Siguiente paso: cítalo como %s en tu archivo; `triangulacion` lista lo que les falta a los hallazgos "
          "clave." % identificador)


def cmd_confianza(args):
    carpeta, producto, registro = abrir(args)
    hallazgo = registro.hallazgos.get(args.hallazgo)
    if not hallazgo:
        raise Fallo("No existe el hallazgo %s" % args.hallazgo)
    calculada = registro.evaluar(dict(hallazgo, confianza_manual=None))["calculada"]
    pedido = NIVELES.index(args.bajar)
    if pedido >= calculada:
        raise Fallo("La confianza calculada de %s es %s: solo se puede bajar, nunca subir ni dejar igual." % (
            args.hallazgo, NIVELES[calculada]))
    datos = cargar_linea(carpeta, hallazgo["linea"])
    for item in datos["hallazgos"]:
        if item["id"] == args.hallazgo:
            item["confianza_manual"] = {"nivel": args.bajar, "motivo": args.motivo.strip(), "fecha": ahora()}
    escribir_json(ruta_linea(carpeta, hallazgo["linea"]), datos)
    print("✔ %s: confianza %s → %s (%s)" % (args.hallazgo, NIVELES[calculada], args.bajar, args.motivo.strip()))
    print("Siguiente paso: si sostiene un criterio del puntaje o una puerta, vuelve a correr `puntaje` o `puerta`.")


def cmd_competidor(args):
    carpeta, producto, registro = abrir(args)
    fuentes = ids_existentes(lista(args.fuentes), registro.fuentes, "la(s) fuente(s)")
    if not fuentes:
        raise Fallo("Cada fila de la matriz necesita al menos una fuente (--fuentes S-…)")
    if (args.sustituto or args.resuelve) and args.peldano != 4:
        raise Fallo("--sustituto y --resuelve son de un sustituto (--peldano 4): cómo se resuelve hoy la necesidad "
                    "sin una app así")
    datos = cargar_linea(carpeta, "competencia")
    fila = registro.competidor(args.nombre)
    nueva = fila is None
    if nueva:
        fila = {"id": "C-%d" % (len(datos["matriz"]) + 1), "nombre": args.nombre.strip()}
        datos["matriz"].append(fila)
    else:
        fila = next(item for item in datos["matriz"] if item["id"] == fila["id"])
    fila.update(peldano=args.peldano, fuentes=sorted(set(fila.get("fuentes", [])) | set(fuentes)))
    valores = {
        "descargas": int(a_numero(args.descargas)) if args.descargas else None,
        "nota": a_numero(args.nota) if args.nota else None, "actualizada": args.actualizada,
        "precio": args.precio, "modelo": args.modelo, "anuncios": args.anuncios,
        "tamano_mb": a_numero(args.tamano_mb) if args.tamano_mb else None, "idiomas": lista(args.idiomas),
        "permisos": lista(args.permisos), "sin_conexion": args.sin_conexion, "accesibilidad": args.accesibilidad,
        "plataformas": lista(args.plataformas),
        "funciones": [f.strip() for f in (args.funciones or "").split(";") if f.strip()], "traccion": args.traccion,
        "sustituto": args.sustituto, "resuelve": args.resuelve,
    }
    for clave, valor in valores.items():
        if valor not in (None, "", []):
            fila[clave] = valor  # una fila se completa por partes: lo que no se pasa queda como estaba
    escribir_json(ruta_linea(carpeta, "competencia"), datos)
    registro = Registro(carpeta, producto["criterios"])
    vacias = [c for c in COLUMNAS_MATRIZ if c != "traccion" and fila.get(c) in (None, "", [])]
    print("✔ %s %s: %s (peldaño %d, %s%s)" % (fila["id"], "registrado" if nueva else "actualizado", fila["nombre"],
                                             args.peldano, PELDANOS[args.peldano][0],
                                             " · con tracción" if registro.con_traccion(fila) else ""))
    if vacias:
        print("· Columnas sin dato: %s" % ", ".join(vacias))
    if args.peldano == 4:
        print("· Sustituto: %s" % texto_sustituto(fila))
        if fila.get("sustituto") in ("nativo", "gratuito") and fila.get("resuelve") == "si":
            print("⚠ Es gratuito o nativo y ya resuelve la necesidad: cada diferenciador tendrá que superarlo con "
                  "evidencia, y la puerta 1 lo exige (references/diferenciacion.md).")
        elif not (fila.get("sustituto") and fila.get("resuelve")):
            print("· Para cerrar 1a, completa `--sustituto nativo|gratuito|pago` y `--resuelve si|parcial|no`.")
    print("Siguiente paso: `matriz` muestra la tabla completa, con las quejas que la voz del usuario enlazó a cada "
          "competidor.")


def cmd_matriz(args):
    carpeta, producto, registro = abrir(args)
    if not registro.competidores:
        print("La matriz está vacía.\nSiguiente paso: la sesión 1a registra cada fila con `competidor`.")
        return
    quejas = {}
    for hallazgo in registro.hallazgos.values():
        for referencia in hallazgo.get("competidores", []):
            fila = registro.competidor(referencia)
            quejas.setdefault(fila["id"] if fila else "sin fila: " + referencia, []).append(hallazgo["id"])
    encabezados = ["ID", "Competidor", "Peldaño", "Descargas", "Nota", "Actualizada", "Precio y modelo", "Anuncios",
                   "MB", "Idiomas", "Permisos", "Sin conexión", "Accesibilidad", "Plataformas", "Funcionalidades",
                   "Hallazgos"]
    print("| %s |" % " | ".join(encabezados))
    print("| %s |" % " | ".join("---" for _ in encabezados))

    def texto(valor):
        if valor in (None, "", []):
            return "—"
        if isinstance(valor, list):
            return ", ".join(str(v) for v in valor)
        return numero(valor) if isinstance(valor, (int, float)) else str(valor)

    for fila in registro.competidores.values():
        precio = " · ".join(str(v) for v in (fila.get("precio"), fila.get("modelo")) if v)
        peldano = str(fila["peldano"])
        if fila["peldano"] == 4:
            peldano += " · %s · %s" % (fila.get("sustituto") or "?", RESUELVE.get(fila.get("resuelve"), "?"))
        print("| %s |" % " | ".join([
            fila["id"], fila["nombre"] + (" ★" if registro.con_traccion(fila) else ""), peldano,
            texto(fila.get("descargas")), texto(fila.get("nota")), texto(fila.get("actualizada")), texto(precio),
            texto(fila.get("anuncios")), texto(fila.get("tamano_mb")), texto(fila.get("idiomas")),
            texto(fila.get("permisos")), texto(fila.get("sin_conexion")), texto(fila.get("accesibilidad")),
            texto(fila.get("plataformas")), texto(fila.get("funciones")), texto(quejas.get(fila["id"]))]))
    print("\n★ = con tracción (%s descargas o más, o tracción anotada)." % numero(
        float(producto["criterios"]["traccion_descargas"])))
    fuertes = registro.sustitutos_fuertes()
    if fuertes:
        print("⚠ Sustituto gratuito o nativo que ya resuelve la necesidad: %s. Cada diferenciador tiene que superarlo "
              "con evidencia (un hallazgo que lo nombre con `--competidores`)." % "; ".join(
                  nombre_fila(c) for c in fuertes))
    elif not registro.sustitutos():
        print("· Sin sustitutos (peldaño 4): ¿cómo se resuelve hoy la necesidad sin una app así? La sesión 1a lo "
              "registra antes de cerrar.")
    for clave, ids in quejas.items():
        if clave.startswith("sin fila: "):
            print("⚠ Competidor %s: lo citan %s, pero no tiene fila en la matriz." % (clave[10:], ", ".join(ids)))
    print("Siguiente paso: con la matriz y las quejas, la sesión 1g busca los huecos por vector "
          "(references/diferenciacion.md).")


def cmd_intento(args):
    carpeta, producto, registro = abrir(args)
    fuentes = ids_existentes(lista(args.fuentes), registro.fuentes, "la(s) fuente(s)")
    if args.resultado != "sin-rastro" and not fuentes:
        raise Fallo("Un intento fallido necesita su fuente (--fuentes S-…): un cierre, un post-mortem o un "
                    "lanzamiento abandonado")
    producto.setdefault("intentos", []).append(
        {"resultado": args.resultado, "texto": args.texto.strip(), "fuentes": fuentes, "fecha": ahora()})
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    print("✔ Búsqueda de intentos anteriores registrada: %s" % args.resultado)
    if args.resultado == "fracaso-demanda":
        print("⚠ Alguien lo probó y fracasó por falta de demanda: es evidencia en contra y la puerta 1 lo muestra.")
    print("Siguiente paso: explica en tu archivo en qué se parece y en qué no ese intento a la idea.")


def exigir_1g_abierta(producto, carpeta, que):
    """Los diferenciadores y el principal son de la sesión 1g: con 1g cerrada, un cambio pasa por la puerta."""
    if cerrada(producto, "1g"):
        puerta = proxima_puerta(carpeta, producto)
        raise Fallo("%s es trabajo de la sesión 1g, que ya cerró: no se hace con un comando suelto. Regístralo como "
                    "propuesta para la puerta %s (`propuesta --texto \"<qué cambiar y por qué>\" --ajustar 1g`): el "
                    "usuario la ve en la puerta y decide si reabre 1g." % (que, puerta or "siguiente"))


def cmd_diferenciador(args):
    carpeta, producto, registro = abrir(args)
    exigir_1g_abierta(producto, carpeta, "Registrar un diferenciador")
    hallazgos = ids_existentes(lista(args.hallazgos), registro.hallazgos, "el/los hallazgo(s)")
    if not hallazgos:
        raise Fallo("Un diferenciador necesita al menos un hallazgo (--hallazgos H-…): sin evidencia es un "
                    "diferenciador imaginario")
    datos = cargar_linea(carpeta, "diferenciacion")
    identificador = "D-%d" % (len(datos["diferenciadores"]) + 1)
    if args.principal:
        for item in datos["diferenciadores"]:
            if item.get("principal") and not item.get("anulado"):
                item["principal"] = False
                print("· %s deja de ser el diferenciador principal." % item["id"])
    diferenciador = {"id": identificador, "vector": args.vector, "texto": args.texto.strip(), "hallazgos": hallazgos,
                     "se_ve": args.se_ve, "copiable": args.copiable, "motivo": args.motivo.strip(),
                     "semanas": positivo(args.semanas, "--semanas"), "principal": bool(args.principal),
                     "fecha": ahora()}
    datos["diferenciadores"].append(diferenciador)
    escribir_json(ruta_linea(carpeta, "diferenciacion"), datos)
    registro = Registro(carpeta, producto["criterios"])
    imprimir_viabilidad(registro, registro.diferenciadores[identificador],
                        " registrado" + (" como principal" if args.principal else ""))


def imprimir_viabilidad(registro, diferenciador, como=""):
    estado = registro.estado(diferenciador)
    identificador = diferenciador["id"]
    print("%s %s%s: %s" % ({"viable": "✔", "baja": "⚠", "no": "✖"}[estado], identificador, como,
                                      ESTADOS_DIFERENCIADOR[estado]))
    for cumple, texto in registro.viabilidad(diferenciador):
        print("  %s %s" % ("✔" if cumple else "✖", texto))
    if estado == "baja":
        print("· Cumple los cinco criterios, pero no todos sus hallazgos están triangulados: no cuenta como viable "
              "para la puerta 1 hasta que lo estén.")
    if estado != "no" and diferenciador.get("copiable") == "alta":
        print("· Es fácil de copiar: sirve para entrar, pero no sostiene la posición.")
    en_ficha = any(d.get("se_ve") == "ficha" for d in registro.viables())
    en_uso = any(d.get("se_ve") == "uso" for d in registro.viables())
    if registro.viables() and not (en_ficha and en_uso):
        print("· Lo ideal es tener un diferenciador viable que se vea en la ficha (consigue descargas) y otro en el "
              "uso (consigue retención): falta el de %s." % ("la ficha" if not en_ficha else "el uso"))
    print("Siguiente paso: %s" % (
        "regístralo en diferenciacion.md con su ID; el más fuerte es el principal (`principal --id`)."
        if estado == "viable" else "triangula sus hallazgos (`triangulacion` dice qué les falta) o elige otro como "
        "principal." if estado == "baja" else "consigue lo que falta o descártalo con `anular --id %s --motivo …`."
        % identificador))


def cmd_principal(args):
    carpeta, producto, registro = abrir(args)
    exigir_1g_abierta(producto, carpeta, "Cambiar el diferenciador principal")
    if args.id not in registro.diferenciadores:
        raise Fallo("No existe el diferenciador %s (o está anulado)" % args.id)
    datos = cargar_linea(carpeta, "diferenciacion")
    anterior = None
    for item in datos["diferenciadores"]:
        if item.get("principal") and item["id"] != args.id:
            anterior = item["id"]
        item["principal"] = item["id"] == args.id and not item.get("anulado")
    escribir_json(ruta_linea(carpeta, "diferenciacion"), datos)
    registro = Registro(carpeta, producto["criterios"])
    print("✔ %s es el diferenciador principal%s." % (args.id, " (antes: %s)" % anterior if anterior else ""))
    imprimir_viabilidad(registro, registro.diferenciadores[args.id], " (principal)")


def cmd_anular(args):
    carpeta, producto, registro = abrir(args)
    campo = {"S": "fuentes", "H": "hallazgos", "C": "matriz", "D": "diferenciadores", "V": "vacios"}.get(args.id[:1])
    if campo == "diferenciadores":
        exigir_1g_abierta(producto, carpeta, "Anular un diferenciador")
    for linea in LINEAS if campo else ():
        datos = cargar_linea(carpeta, linea)
        for item in datos.get(campo, []):
            if item["id"] == args.id and not item.get("anulado"):
                item["anulado"] = {"motivo": args.motivo.strip(), "fecha": ahora()}
                escribir_json(ruta_linea(carpeta, linea), datos)
                print("✔ %s anulado (%s). Queda en el registro, pero ya no cuenta." % (args.id, args.motivo.strip()))
                print("Siguiente paso: si sostenía un hallazgo, un puntaje o una puerta, vuelve a correr "
                      "`triangulacion`.")
                return
    raise Fallo("No existe %s, o ya estaba anulado" % args.id)


def cmd_objetivo(args):
    carpeta, producto, registro = abrir(args)
    nuevos = {d: etiquetas(getattr(args, d), d) for d in DIMENSIONES}
    actual = dict(producto.get("objetivo") or {})
    if all(v is None for v in nuevos.values()):
        if objetivo_de(producto):
            print("Objetivo: mercados %s · idiomas %s · tiendas %s" % (
                ", ".join(actual["mercados"]), ", ".join(actual["idiomas"]), ", ".join(actual["tiendas"]) or "ninguna"))
        else:
            print("Objetivo sin completar: %s" % ", ".join(d for d in DIMENSIONES if actual.get(d) is None))
        print("Siguiente paso: `cobertura` muestra qué línea tiene fuentes de cada uno.")
        return
    fijado = cerrada(producto, "0")
    if fijado and not args.motivo:
        raise Fallo("El objetivo se fijó al cerrar la sesión 0: cambiarlo exige --motivo \"<por qué>\" (queda "
                    "registrado y la puerta 1 lo muestra)")
    antes = dict(actual)
    actual.update((d, v) for d, v in nuevos.items() if v is not None)
    producto["objetivo"] = actual
    if fijado:
        producto.setdefault("objetivo_cambios", []).append(
            {"antes": antes, "despues": actual, "motivo": args.motivo.strip(), "fecha": ahora(), "desde": origen()})
        producto.setdefault("criterios_cambios", []).append(
            {"clave": "objetivo", "antes": "; ".join("%s %s" % (d, ", ".join(antes.get(d) or [])) for d in DIMENSIONES),
             "despues": "; ".join("%s %s" % (d, ", ".join(actual.get(d) or [])) for d in DIMENSIONES),
             "motivo": args.motivo.strip(), "fecha": ahora(), "desde": origen()})
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    faltan = [d for d in DIMENSIONES if actual.get(d) is None]
    print("✔ Objetivo: %s" % " · ".join("%s %s" % (d, ", ".join(actual[d]) or "ninguna") for d in DIMENSIONES
                                         if actual.get(d) is not None))
    if faltan:
        print("· Falta: --%s" % ", --".join(faltan))
    print("Siguiente paso: cada línea de investigación necesita fuentes de cada mercado, idioma y tienda que le toca, "
          "o el vacío registrado (`vacio`). `cobertura` lo muestra.")


def cmd_vacio(args):
    carpeta, producto, registro = abrir(args)
    linea = linea_valida(args.linea)
    if linea not in COBERTURA_LINEAS:
        raise Fallo("La línea %s no tiene cobertura por mercado, idioma o tienda. Las que tienen: %s" % (
            linea, ", ".join(COBERTURA_LINEAS)))
    elegidas = [(d, getattr(args, DIMENSIONES[d])) for d in DIMENSIONES if getattr(args, DIMENSIONES[d])]
    if len(elegidas) != 1:
        raise Fallo("Un vacío es de un solo valor: --mercado, --idioma o --tienda, uno")
    dimension, valor = elegidas[0][0], elegidas[0][1].strip()
    if dimension not in COBERTURA_LINEAS[linea]:
        raise Fallo("La línea %s no pide cobertura por %s: pide %s" % (
            linea, DIMENSIONES[dimension], ", ".join(DIMENSIONES[d] for d in COBERTURA_LINEAS[linea])))
    objetivo = objetivo_de(producto)
    if objetivo and normal(valor) not in [normal(v) for v in objetivo[dimension]]:
        raise Fallo("%s no está en el objetivo (%s): `objetivo` lo muestra" % (valor, ", ".join(objetivo[dimension])))
    datos = cargar_linea(carpeta, linea)
    identificador = "V-%s-%d" % (LINEAS[linea][0], len(datos["vacios"]) + 1)
    vacio = {"id": identificador, "linea": linea, "dimension": dimension, "valor": valor, "motivo": args.motivo,
             "texto": args.texto.strip(), "fecha": ahora()}
    datos["vacios"].append(vacio)
    escribir_json(ruta_linea(carpeta, linea), datos)
    print("✔ %s registrado: %s" % (identificador, texto_vacio(vacio)))
    if args.motivo == "herramienta":
        print("· Es un límite de las herramientas, no de la evidencia: la puerta lo muestra así, y ajustar la línea "
              "con las mismas herramientas no lo resuelve. Lo resuelven un navegador en el agente o un CSV de reseñas "
              "que aporte el usuario (references/investigacion.md · Fuentes difíciles).")
    print("Siguiente paso: nómbralo en \"⚠ Sin evidencia\" de tu archivo; `cobertura` muestra lo que queda.")


def cmd_cobertura(args):
    carpeta, producto, registro = abrir(args)
    if args.linea:
        linea_valida(args.linea)
    mapa = cobertura(producto, registro, args.linea)
    if mapa is None:
        print("No hay objetivo registrado: la sesión 0 lo registra con `objetivo --mercados … --idiomas … --tiendas "
              "…`.")
        return
    objetivo = objetivo_de(producto)
    print("Cobertura · objetivo: mercados %s · idiomas %s · tiendas %s" % (
        ", ".join(objetivo["mercados"]), ", ".join(objetivo["idiomas"]), ", ".join(objetivo["tiendas"]) or "ninguna"))
    huecos = vacios = 0
    for linea, filas in mapa.items():
        print("\n%s (sesión %s)" % (linea, LINEAS[linea][1]))
        for dimension, valor, estado, detalle in filas:
            if estado == "fuentes":
                print("  ✔ %s %s · %s" % (DIMENSIONES[dimension], valor, ", ".join(detalle)))
            elif estado == "vacio":
                vacios += 1
                print("  ⚠ %s %s · vacío, %s (%s): %s" % (DIMENSIONES[dimension], valor, MOTIVOS_VACIO[detalle["motivo"]],
                                                          detalle["id"], detalle["texto"]))
            else:
                huecos += 1
                print("  ✖ %s %s · sin fuentes ni vacío registrado" % (DIMENSIONES[dimension], valor))
        if not filas:
            print("  (sin nada que cubrir en el objetivo)")
    print("\n%d hueco(s) sin registrar · %d vacío(s) registrado(s)." % (huecos, vacios))
    print("Siguiente paso: %s" % (
        "por cada ✖, una fuente con su etiqueta (`fuente … --mercados/--idiomas/--tiendas`) o el vacío con su motivo "
        "(`vacio`). Una línea no cierra con huecos sin registrar." if huecos else
        "nada que registrar; los vacíos van en \"⚠ Sin evidencia\" de su línea y la puerta 1 los muestra."))


def cmd_resenas(args):
    datos = leer_csv(Path(os.path.abspath(os.path.expanduser(args.archivo))))
    rango = re.match(r"^([1-5])(?:-([1-5]))?$", args.estrellas or "1-3")
    if not rango:
        raise Fallo("--estrellas es un número o un rango de 1 a 5, como 1-3")
    minimo, maximo = int(rango.group(1)), int(rango.group(2) or rango.group(1))
    desde = fecha_publicacion(args.desde) if args.desde else None
    filas = [f for f in datos["filas"] if f["texto"] and (f["estrellas"] is None or minimo <= f["estrellas"] <= maximo)
             and (not args.idioma or f["idioma"] == args.idioma.lower())
             and (not desde or (f["fecha"] and f["fecha"].isoformat() >= desde))]
    filas.sort(key=lambda f: f["fecha"] or date.min, reverse=True)
    print("%s · %s" % (Path(args.archivo).name, resumen_csv(datos)))
    print("Columnas usadas: %s (las de autor nunca se leen)\n" % ", ".join(
        "%s = %s" % (tipo, columna) for tipo, columna in datos["columnas"].items() if columna))
    for fila in filas[:args.limite]:
        texto = fila["texto"][:200] + ("…" if len(fila["texto"]) > 200 else "")
        print("- %s · %s · %s · %s" % (fila["fecha"].isoformat() if fila["fecha"] else "sin fecha",
                                       "%d★" % fila["estrellas"] if fila["estrellas"] else "—",
                                       fila["idioma"] or "—", texto))
    print("\n%d de %d reseña(s) con esos filtros%s." % (min(len(filas), args.limite), len(filas),
                                                        " (sube --limite para ver más)" if len(filas) > args.limite
                                                        else ""))
    print("Siguiente paso: parafrasea, sin nombres ni datos de quien escribe, y registra el CSV como fuente con "
          "`fuente --archivo … --autor \"<app> · <tienda>\" --publicada auto`.")


def proxima_puerta(carpeta, producto):
    """La primera puerta que todavía no tiene la decisión de seguir, o None si están todas."""
    lista_decisiones = decisiones(carpeta)
    return next((n for n in PUERTAS if not cumplido(producto, lista_decisiones, "P%d" % n)), None)


def cmd_propuesta(args):
    carpeta, producto, registro = abrir(args)
    puerta = proxima_puerta(carpeta, producto)
    if puerta is None:
        raise Fallo("No queda ninguna puerta por decidir: el proceso cerró")
    if args.ajustar and (args.ajustar not in SESION or "P%d" % puerta not in dependientes(args.ajustar)):
        raise Fallo("--ajustar lleva una sesión anterior a la puerta %d: %s" % (puerta, ", ".join(
            s["id"] for s in SESIONES if "P%d" % puerta in dependientes(s["id"]))))
    sesion = args.sesion or next((s["id"] for s in reversed(SESIONES) if not cerrada(producto, s["id"])
                                  and disponible(producto, decisiones(carpeta), s["id"])), "")
    propuesta = {"id": "PR-%d" % (len(producto.get("propuestas", [])) + 1), "puerta": puerta, "sesion": sesion,
                 "texto": args.texto.strip(), "ajustar": args.ajustar or "", "fecha": ahora(), "estado": "pendiente"}
    producto.setdefault("propuestas", []).append(propuesta)
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    print("✔ %s registrada para la puerta %d: %s%s" % (propuesta["id"], puerta, propuesta["texto"],
                                                       " (se aplica con Ajustar %s)" % args.ajustar
                                                       if args.ajustar else ""))
    print("Siguiente paso: no la apliques tú. La puerta %d la muestra junto a los comandos de la decisión, que corre "
          "el usuario." % puerta)


def cmd_modelos(args):
    carpeta, producto, registro = abrir(args)
    cambios = False
    for nivel in MODELOS:
        nombre = getattr(args, nivel)
        if nombre:
            producto.setdefault("modelos", {})[nivel] = nombre.strip()
            cambios = True
    if args.herramienta:
        if args.herramienta == "ninguna":
            producto["herramienta"] = None
        else:
            if args.herramienta == "otra" and not args.comando:
                raise Fallo("Con --herramienta otra, pasa --comando con {modelo} (y, si tu CLI lo admite, {esfuerzo}): "
                            "por ejemplo --comando \"mi-cli --model {modelo}\"")
            producto["herramienta"] = {"clave": args.herramienta, "comando": (args.comando or "").strip() or None}
        cambios = True
    elif args.comando:
        raise Fallo("--comando va con --herramienta")
    if args.comando and "{modelo}" not in args.comando:
        raise Fallo("--comando necesita {modelo}, que se reemplaza por el modelo de cada sesión")
    if cambios:
        guardar(carpeta, producto)
        actualizar_estado(carpeta, producto)
    herramienta = producto.get("herramienta") or {}
    print("| Sesión | Modelo | Esfuerzo | Abrir el chat |\n| --- | --- | --- | --- |")
    for sesion in SESIONES:
        nivel = sesion["modelo"]
        print("| %s · %s | %s | %s | %s |" % (sesion["id"], sesion["nombre"], modelo_de(producto, nivel),
                                             ESFUERZO[nivel], abrir_chat(producto, carpeta, nivel) or "—"))
    print("\nHerramienta: %s." % ({"claude": "Claude Code", "copilot": "GitHub Copilot CLI"}.get(
        herramienta.get("clave"), herramienta.get("clave")) if herramienta else "sin anotar (`modelos --herramienta "
        "claude|copilot|otra`)"))
    print("Siguiente paso: `siguiente` trae el modelo%s de cada chat." % (
        " y el comando que lo abre" if herramienta else ""))


def texto_consumo(fila):
    partes = []
    if fila.get("costo") is not None:
        partes.append("%s USD" % numero(fila["costo"]))
    if fila.get("creditos") is not None:
        partes.append("%s AI Credits" % numero(fila["creditos"]))
    if fila.get("tokens") is not None:
        partes.append("%s tokens" % numero(fila["tokens"]))
    if fila.get("pasos"):
        partes.append("%d pasos" % fila["pasos"])
    if fila.get("incluye"):
        partes.append("incluye %s" % ", ".join(fila["incluye"]))
    return ", ".join(partes) or "sin datos"


def total_usd(filas):
    return sum((f.get("costo") or 0) + (f.get("creditos") or 0) * USD_POR_CREDITO for f in filas)


def con_costo(fila):
    return fila.get("costo") is not None or fila.get("creditos") is not None


def texto_total(filas):
    """El total anotado: en USD solo si alguna fila trae costo (si no, "sin dato en USD", nunca 0), con las sesiones
    que no lo traen y los tokens sumados."""
    costeadas = [f for f in filas if con_costo(f)]
    if costeadas:
        texto = "%s USD" % numero(total_usd(costeadas))
        sin_dato = [f["sesion"] for f in filas if not con_costo(f)]
        if sin_dato:
            texto += " (sin dato en USD: %s)" % ", ".join(sin_dato)
    else:
        texto = "sin dato en USD"
    tokens = sum(f.get("tokens") or 0 for f in filas)
    return texto + (" · %s tokens" % numero(tokens) if tokens else "")


def monto(texto, opcion):
    """Un monto escrito por una persona ('0.40', '$0,40', '1.2 USD'); rechaza el que el shell mutiló con '$'."""
    limpio = str(texto).strip()
    if re.search(r"(bash|zsh|/bin/|->)", limpio) or re.match(r"^-", limpio):
        raise Fallo("%s llegó mutilado (%s): entre comillas dobles el shell expande `$`. Repite el comando con "
                    "comillas simples: %s '0.40'" % (opcion, limpio, opcion))
    sin_moneda = re.sub(r"(?i)(us\$|usd|\$|ai credits?|créditos?|creditos?)", "", limpio).strip()
    if not re.match(r"^\d[\d.,]*$", sin_moneda):
        raise Fallo("%s debe ser un número, no '%s'" % (opcion, limpio))
    return a_numero(sin_moneda)


def cantidad(texto, opcion):
    """Una cantidad entera escrita por una persona: '45000', '45k', '1.2M'."""
    if not re.match(r"^\d[\d.,]*\s*[kKmM]?$", str(texto).strip()):
        raise Fallo("%s debe ser un número (como 45000 o 45k), no '%s'" % (opcion, texto))
    return a_numero(texto)


def cmd_consumo(args):
    carpeta, producto, registro = abrir(args)
    filas = producto.setdefault("consumo", [])
    if not args.sesion:
        if not filas:
            print("Sin consumo anotado.")
        for fila in filas:
            print("%-12s %s%s" % (fila["sesion"], texto_consumo(fila), " · %s" % fila["modelo"] if fila.get("modelo")
                                  else ""))
        if filas:
            print("Total: %s (los AI Credits, a %s USD)" % (texto_total(filas), numero(USD_POR_CREDITO)))
        pendientes = sin_consumo(producto)
        print("Siguiente paso: %s" % ("anotar %s con `consumo --sesion <id> --costo '<USD>'` (opcional)" % ", ".join(
            pendientes) if pendientes else "nada pendiente."))
        return
    if args.sesion not in SESION and args.sesion != "orquestador":
        raise Fallo("--sesion es una de %s, u orquestador (el chat que lanzó los subagentes)" % ", ".join(SESION))
    incluye = lista(args.incluye)
    desconocidas = [s for s in incluye if s not in SESION]
    if desconocidas:
        raise Fallo("--incluye lleva sesiones: %s no existe(n)" % ", ".join(desconocidas))
    valores = {"costo": monto(args.costo, "--costo") if args.costo else None,
               "creditos": monto(args.creditos, "--creditos") if args.creditos else None,
               "tokens": int(cantidad(args.tokens, "--tokens")) if args.tokens else None,
               "pasos": int(cantidad(args.pasos, "--pasos")) if args.pasos else None,
               "modelo": (args.modelo or "").strip() or None,
               "incluye": incluye or None}
    if all(valores[c] is None for c in ("costo", "creditos", "tokens")):
        raise Fallo("Anota al menos --costo (USD), --creditos (AI Credits de GitHub Copilot) o --tokens")
    fila = next((f for f in filas if f["sesion"] == args.sesion), None)
    if fila is None:
        fila = {"sesion": args.sesion}
        filas.append(fila)
    fila.update((clave, valor) for clave, valor in valores.items() if valor is not None)
    fila["fecha"] = ahora()
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    print("✔ Consumo de %s: %s · total anotado: %s" % (args.sesion, texto_consumo(fila), texto_total(filas)))
    pendientes = sin_consumo(producto)
    print("Siguiente paso: %s" % ("falta anotar %s (opcional)." % ", ".join(pendientes) if pendientes
                                  else "`siguiente` muestra por dónde seguir."))


def cmd_triangulacion(args):
    carpeta, producto, registro = abrir(args)
    claves = [h for h in registro.hallazgos.values() if h.get("critico")]
    if not claves:
        print("No hay hallazgos clave registrados (los que llevan --critico).")
        print("Siguiente paso: marca con --critico los hallazgos de los que dependen el puntaje y las puertas.")
        return
    incompletos = sin_busqueda = 0
    for hallazgo in claves:
        evaluacion = registro.evaluar(hallazgo)
        incompletos += 0 if evaluacion["triangulado"] else 1
        sin_busqueda += 1 if evaluacion["sin_busqueda"] else 0
        print("%s %s · %s · peldaño %d (%s) · %d/%s fuentes independientes y vigentes%s" % (
            "✔" if evaluacion["triangulado"] else "✖", hallazgo["id"], registro.etiqueta(hallazgo),
            evaluacion["peldano"], PELDANOS[evaluacion["peldano"]][0], evaluacion["independientes"],
            producto["criterios"]["fuentes_minimas"], " · en contra: %d" % evaluacion["contra"]
            if evaluacion["contra"] else ""))
        print("    %s" % hallazgo["texto"][:160])
        for falta in evaluacion["faltan"]:
            print("    → %s" % falta)
        if evaluacion["oficial"]:
            print("    · triangulado por la fuente oficial %s: en políticas, la norma misma basta" % ", ".join(
                evaluacion["oficial"]))
        if hallazgo.get("bloquea"):
            print("    · bloqueante en %s: esa tienda nombra o rechaza la categoría (riesgo de políticas 1)" % ", ".join(
                hallazgo["bloquea"]))
        if evaluacion["triangulado"] and evaluacion["acumuladas"]:
            print("    · %s: dato(s) acumulado(s), solo contexto: no cuenta(n), y no hace falta" % ", ".join(
                evaluacion["acumuladas"]))
        if evaluacion["triangulado"] and evaluacion["no_vigentes"]:
            print("    · %s sin fecha o fuera de la ventana: no cuenta(n), y no hace falta" % ", ".join(
                evaluacion["no_vigentes"]))
        if evaluacion["sin_busqueda"]:
            print("    → regla 4: falta registrar la búsqueda de evidencia en contra (--en-contra o --sin-contra)")
        manual = hallazgo.get("confianza_manual")
        if manual:
            print("    · confianza bajada a %s: %s" % (manual["nivel"], manual["motivo"]))
    print("\n%d de %d hallazgos clave triangulados (regla 2)%s." % (
        len(claves) - incompletos, len(claves), " · %d sin la búsqueda en contra (regla 4)" % sin_busqueda
        if sin_busqueda else ""))
    print("La confianza y la triangulación usan la misma regla de vigencia: una fuente sin fecha o fuera de la ventana "
          "no cuenta para ninguna de las dos, y solo un hallazgo triangulado llega a confianza alta.")
    mapa = cobertura(producto, registro)
    if mapa is not None:
        huecos = sum(1 for filas in mapa.values() for fila in filas if fila[2] == "falta")
        vacios = sum(1 for filas in mapa.values() for fila in filas if fila[2] == "vacio")
        print("Cobertura: %d hueco(s) sin fuentes ni vacío registrado · %d vacío(s) registrado(s) (`cobertura`)." % (
            huecos, vacios))
    if incompletos or sin_busqueda:
        print("Siguiente paso: consigue lo que falta o deja el hallazgo con su confianza actual y dilo en la "
              "síntesis; nunca lo presentes como confirmado.")
    else:
        print("Siguiente paso: `puntaje --valores d,m,f,r,x` con las anclas de references/puntaje.md.")


def cmd_puntaje(args):
    carpeta, producto, registro = abrir(args)
    if not tipo_de(producto):
        raise Fallo("Falta el tipo de idea: la sesión 1a lo registra con `tipo`. El puntaje se compara con el "
                    "mínimo de ese tipo.")
    partes = lista(args.valores)
    if len(partes) != 5 or not all(parte.isdigit() and 1 <= int(parte) <= 5 for parte in partes):
        raise Fallo("--valores lleva cinco enteros de 1 a 5, en este orden: demanda, monetización, facilidad, "
                    "riesgo de políticas (5 = bajo) y diferenciación. Por ejemplo: 4,3,4,5,3")
    valores = dict(zip(CRITERIOS_PUNTAJE, (int(parte) for parte in partes)))
    viables, bajas = registro.viables(), registro.con_confianza_baja()
    if not viables and not bajas and valores["diferenciacion"] > 1:
        raise Fallo("Diferenciación = %d no corresponde: no hay ningún diferenciador viable registrado, y esa es "
                    "el ancla del 1 (references/puntaje.md)." % valores["diferenciacion"])
    if not viables and bajas and valores["diferenciacion"] > 2:
        raise Fallo("Diferenciación = %d no corresponde: %s es viable con confianza baja (sus hallazgos no están "
                    "triangulados), así que el máximo es 2 (references/puntaje.md)." % (
                        valores["diferenciacion"], ", ".join(d["id"] for d in bajas)))
    if viables and valores["diferenciacion"] == 1:
        raise Fallo("Diferenciación = 1 no corresponde: hay %d diferenciador(es) viable(s) registrado(s) (%s)." % (
            len(viables), ", ".join(d["id"] for d in viables)))
    actuales = [h["id"] for h in registro.hallazgos.values() if h["linea"] == "demanda" and h.get("critico")
                and registro.evaluar(h)["triangulado"]]
    if valores["demanda"] >= 4 and not actuales:
        raise Fallo("Demanda = %d no corresponde: las anclas 4 y 5 piden señales actuales comprobadas (de los últimos "
                    "12 a 18 meses), y ningún hallazgo clave de demanda está triangulado con fuentes vigentes y no "
                    "acumuladas. Las descargas acumuladas son contexto (references/puntaje.md); `triangulacion` dice "
                    "qué falta." % valores["demanda"])
    bloqueos = registro.bloqueos(objetivo_de(producto))
    if bloqueos and valores["riesgo"] != 1:
        raise Fallo("Riesgo de políticas = %d no corresponde: %s, y en esa tienda el riesgo es 1. Pasa 1 y, si hay "
                    "una mitigación creíble (por ejemplo, no lanzar en esa tienda), escríbela con --mitigacion." % (
                        valores["riesgo"], texto_bloqueos(bloqueos)))
    por_criterio, global_ = confianzas(registro)
    total = sum(valores.values())
    producto["puntaje"] = {"valores": valores, "total": total, "mitigacion": (args.mitigacion or "").strip(),
                           "fecha": ahora()}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    apoyo = sustento(registro)
    nombres = {"demanda": "Demanda", "monetizacion": "Monetización", "facilidad": "Facilidad",
               "riesgo": "Riesgo de políticas (5 = bajo)", "diferenciacion": "Diferenciación"}
    for criterio in CRITERIOS_PUNTAJE:
        nivel = por_criterio[criterio]
        if nivel is None:
            detalle = "estimación, sin fuentes" if criterio == "facilidad" else "sin diferenciador que sostener"
        elif not apoyo[criterio]:
            detalle = "⚠ Sin evidencia: ningún hallazgo clave lo sostiene"
        else:
            detalle = "confianza %s (%s)" % (NIVELES[nivel], ", ".join(apoyo[criterio]))
        print("%-32s %d · %s" % (nombres[criterio], valores[criterio], detalle))
    nueva = tipo_de(producto) == "nueva"
    minimo = int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
    print("\nTotal: %d/25 · confianza global: %s" % (total, NIVELES[global_]))
    cercano = min([registro.evaluar(h)["peldano"] for h in registro.hallazgos.values() if h.get("critico")] or [0])
    if cercano:
        print("Peldaño más cercano a lo directo con evidencia: %d (%s; confianza máxima %s)" % (
            cercano, PELDANOS[cercano][0], NIVELES[PELDANOS[cercano][1]]))
    print("Puerta 1 (idea %s): el mínimo es %d/25 → %s" % (
        tipo_de(producto), minimo, "lo alcanza" if total >= minimo else "no lo alcanza"))
    if bloqueos:
        print("⚠ Bloqueante: %s. La puerta 1 muestra la mitigación para que el usuario juzgue si es creíble." %
              texto_bloqueos(bloqueos))
    if valores["riesgo"] == 1 and not args.mitigacion:
        print("⚠ Riesgo de políticas = 1: la puerta 1 pide una mitigación escrita (`--mitigacion \"…\"`).")
    print("Siguiente paso: escribe la síntesis y cierra la sesión con `cerrar --sesion 1f`.")


def caso(valor, nombre, lleva_fuente, registro, sin_fuente, por_analogia):
    """Un supuesto como {pesimista, base, optimista}: acepta un número (igual en los tres) o un objeto."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if lleva_fuente:
            sin_fuente.append(nombre)
        return {"pesimista": float(valor), "base": float(valor), "optimista": float(valor)}
    if not isinstance(valor, dict) or not all(isinstance(valor.get(c), (int, float)) for c in
                                              ("pesimista", "base", "optimista")):
        raise Fallo("El supuesto `%s` debe ser un número o un objeto con pesimista, base y optimista" % nombre)
    if min(valor[c] for c in ("pesimista", "base", "optimista")) < 0:
        raise Fallo("El supuesto `%s` no puede ser negativo" % nombre)
    if lleva_fuente:
        fuente = str(valor.get("fuente") or "").strip()
        if not fuente:
            sin_fuente.append(nombre)
        elif fuente not in registro.fuentes:
            raise Fallo("El supuesto `%s` cita la fuente %s, que no existe" % (nombre, fuente))
        elif registro.fuentes[fuente]["peldano"] >= 3:
            por_analogia.append("%s (%s, peldaño %d)" % (nombre, fuente, registro.fuentes[fuente]["peldano"]))
    return {c: float(valor[c]) for c in ("pesimista", "base", "optimista")}


def cmd_escenarios(args):
    carpeta, producto, registro = abrir(args)
    ruta = Path(args.entrada)
    if not ruta.is_absolute():
        ruta = (carpeta / ruta) if (carpeta / ruta).is_file() else Path(os.path.abspath(str(ruta)))
    entrada = leer_json(ruta)
    if entrada is None:
        raise Fallo("No existe %s" % ruta)
    mercados = entrada.get("mercados") if isinstance(entrada, dict) else None
    if not mercados:
        raise Fallo("%s no tiene `mercados`: mira la plantilla escenarios.json" % ruta)
    casos = ("pesimista", "base", "optimista")
    sin_fuente, por_analogia = [], []
    totales = dict.fromkeys(casos, 0.0)
    usuarios = dict.fromkeys(casos, 0.0)
    filas = []
    modelos = {}  # modelo de monetización → {"base", "sin_fuente"}: la puerta 2 pide uno viable con evidencia

    def supuestos(valor, nombre, lleva_fuente=True):
        antes = len(sin_fuente)
        resultado = caso(valor, nombre, lleva_fuente, registro, sin_fuente, por_analogia)
        return resultado, sin_fuente[antes:]

    def sumar(modelo, base, faltan):
        datos = modelos.setdefault(modelo, {"base": 0.0, "sin_fuente": []})
        datos["base"] += base
        datos["sin_fuente"] += [f for f in faltan if f not in datos["sin_fuente"]]

    for mercado in mercados:
        nombre = str(mercado.get("mercado") or "?")
        dau, sin_dau = supuestos(mercado.get("dau"), "%s.dau" % nombre)
        ingresos = dict.fromkeys(casos, 0.0)
        for anuncio in mercado.get("anuncios", []):
            ruta_supuesto = "%s.anuncios.%s" % (nombre, anuncio.get("formato", "?"))
            impresiones, sin_impresiones = supuestos(anuncio.get("impresiones_por_dau"),
                                                     ruta_supuesto + ".impresiones_por_dau")
            ecpm, sin_ecpm = supuestos(anuncio.get("ecpm"), ruta_supuesto + ".ecpm")
            propios = dict((c, dau[c] * impresiones[c] * 30 * ecpm[c] / 1000.0) for c in casos)
            for c in casos:
                ingresos[c] += propios[c]
            sumar("Anuncios · %s" % anuncio.get("formato", "?"), propios["base"], sin_dau + sin_impresiones + sin_ecpm)
        compras = mercado.get("compras", [])
        sin_dau_mau = []
        if compras:
            dau_mau, sin_dau_mau = supuestos(mercado.get("dau_mau"), "%s.dau_mau" % nombre)
            if min(dau_mau.values()) <= 0 or max(dau_mau.values()) > 1:
                raise Fallo("`%s.dau_mau` es la proporción de usuarios del mes que entran cada día: va entre 0 y 1"
                            % nombre)
        for compra in compras:
            ruta_supuesto = "%s.compras.%s" % (nombre, compra.get("nombre", "?"))
            conversion, sin_conversion = supuestos(compra.get("conversion"), ruta_supuesto + ".conversion")
            precio, _ = supuestos(compra.get("precio"), ruta_supuesto + ".precio", False)
            comision = compra.get("comision")
            if not isinstance(comision, (int, float)) or not 0 <= comision < 1:
                raise Fallo("`%s.comision` es la comisión de la tienda como proporción: 0.15 o 0.30" % ruta_supuesto)
            if max(conversion.values()) > 1:
                raise Fallo("`%s.conversion` es una proporción entre 0 y 1 (1 % = 0.01)" % ruta_supuesto)
            propios = dict((c, dau[c] / dau_mau[c] * conversion[c] * precio[c] * (1 - comision)) for c in casos)
            for c in casos:
                ingresos[c] += propios[c]
            sumar("Compra · %s" % compra.get("nombre", "?"), propios["base"], sin_dau + sin_dau_mau + sin_conversion)
        if not mercado.get("anuncios") and not compras:
            raise Fallo("El mercado %s no tiene `anuncios` ni `compras`" % nombre)
        filas.append((nombre, dau, ingresos))
        for c in casos:
            totales[c] += ingresos[c]
            usuarios[c] += dau[c]
    analogia = bool(entrada.get("analogia")) or tipo_de(producto) == "nueva" or bool(por_analogia)
    if analogia:
        totales["pesimista"] *= 1 - AMPLITUD_ANALOGIA
        totales["optimista"] *= 1 + AMPLITUD_ANALOGIA
    rotulos = (["por analogía"] if analogia else []) + (["estimación"] if sin_fuente else [])
    criterios = producto["criterios"]
    moneda = str(entrada.get("moneda") or criterios["moneda"]).upper()
    meta = float(criterios.get("meta_ingresos_mes") or 0)
    necesarios = int(math.ceil(usuarios["base"] * meta / totales["base"])) if meta and totales["base"] > 0 else None
    lista_modelos = [{"nombre": nombre, "base": round(datos["base"], 2), "sin_fuente": datos["sin_fuente"],
                      "viable": datos["base"] > 0 and not datos["sin_fuente"]} for nombre, datos in modelos.items()]
    producto["escenarios"] = {"fecha": ahora(), "moneda": moneda, "pesimista": round(totales["pesimista"], 2),
                              "base": round(totales["base"], 2), "optimista": round(totales["optimista"], 2),
                              "rotulos": rotulos, "dau_base": usuarios["base"], "dau_meta": necesarios,
                              "entrada": str(ruta), "modelos": lista_modelos}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    print("Escenarios de ingresos netos al mes (%s)%s" % (moneda, " · " + " · ".join(rotulos) if rotulos else ""))
    print("\n| Mercado | DAU base | Pesimista | Base | Optimista |\n| --- | --- | --- | --- | --- |")
    for nombre, dau, ingresos in filas:
        print("| %s | %s | %s | %s | %s |" % (nombre, numero(dau["base"]), numero(ingresos["pesimista"]),
                                           numero(ingresos["base"]), numero(ingresos["optimista"])))
    print("| **Total** | %s | %s | %s | %s |" % (numero(usuarios["base"]), numero(totales["pesimista"]),
                                               numero(totales["base"]), numero(totales["optimista"])))
    if analogia:
        print("\nPor analogía: el rango se abre (pesimista × %s y optimista × %s sobre la suma de los mercados)%s."
              % (numero(1 - AMPLITUD_ANALOGIA), numero(1 + AMPLITUD_ANALOGIA),
                 "; supuestos de análogos: " + "; ".join(por_analogia) if por_analogia else ""))
    if sin_fuente:
        print("⚠ Estimación: supuestos sin fuente: %s" % ", ".join(sin_fuente))
    print("\nModelos de monetización (la puerta 2 pide al menos uno viable con evidencia: genera ingresos en el caso "
          "base y todos sus supuestos citan su fuente):")
    for modelo in lista_modelos:
        print("  %s %s · %s %s al mes en el caso base%s" % (
            "✔" if modelo["viable"] else "✖", modelo["nombre"], numero(modelo["base"]), moneda,
            "" if modelo["viable"] else " · " + motivo_modelo(modelo)))
    obligatoria = meta_obligatoria(producto)
    if not meta:
        print("\nSin meta de ingresos: es opcional%s." % (", pero está marcada como obligatoria: falta el valor"
                                                          if obligatoria else ""))
    elif necesarios is None:
        print("\nMeta (%s): el escenario base no genera ingresos, así que no se puede calcular cuántos usuarios hacen "
              "falta." % ("obligatoria" if obligatoria else "referencial"))
    else:
        print("\nMeta (%s): %s %s al mes → el escenario base %s (%s). Para llegar hacen falta %s usuarios activos "
              "diarios; el base supone %s." % (
                  "obligatoria, criterio de la puerta 2" if obligatoria else "referencial, no es criterio de "
                  "ninguna puerta", numero(meta), moneda, "la alcanza" if totales["base"] >= meta else
                  "no la alcanza", numero(totales["base"]), numero(necesarios), numero(usuarios["base"])))
    print("Siguiente paso: copia la tabla y los modelos a 02-estrategia.md con sus rótulos y cierra con "
          "`cerrar --sesion 2`.")


def cmd_validacion(args):
    carpeta, producto, registro = abrir(args)
    filas = hipotesis(carpeta, registro)
    for fila in filas or []:
        print("%s · %s · confianza %s%s%s" % (
            fila["id"], fila["veredicto"] or "sin veredicto", NIVELES[fila["nivel"]],
            " · " + fila["diferenciador"] if fila["diferenciador"] else "",
            " · la más riesgosa" + (" (%s)" % fila["metrica"] if fila["metrica"] else " (sin métrica ni umbral)")
            if fila["riesgosa"] else ""))
    problemas = problemas_validacion(filas)
    for problema in problemas:
        print("✖ %s" % problema)
    if problemas:
        print("Siguiente paso: corrige la tabla de 03-validacion.md y vuelve a correr `validacion`.")
    else:
        refutadas = [fila["id"] for fila in filas if fila["veredicto"] == "refutada"]
        print("✔ %d hipótesis, tabla completa%s." % (len(filas), "; refutadas: " + ", ".join(refutadas)
                                                     if refutadas else ""))
        print("Siguiente paso: `cerrar --sesion 3`.")


def cmd_trazabilidad(args):
    carpeta, producto, registro = abrir(args)
    datos = prd(carpeta, registro)
    if not datos["existe"] or not datos["funciones"]:
        raise Fallo("04-prd.md no tiene la tabla de funcionalidades (ID, Funcionalidad, MVP, Hallazgos, "
                    "Diferenciador, Métrica, Alcance, Impacto, Semanas, Hipótesis)")
    mvp = [f for f in datos["funciones"] if f["mvp"]]
    for funcion in sorted(datos["funciones"], key=lambda f: -(f["rice"] or 0)):
        rice = numero(funcion["rice"]) if funcion["rice"] is not None else "— (faltan alcance, impacto o semanas)"
        print("%s %s%s · RICE %s · %s semana(s) · %s" % (
            "✖" if funcion["faltas"] else "✔", funcion["id"], " (MVP)" if funcion["mvp"] else "", rice,
            numero(funcion["semanas"]), "; ".join(funcion["faltas"]) or ", ".join(
                funcion["hallazgos"] + funcion["diferenciadores"] + funcion["metricas"])))
    trazadas = [f for f in mvp if not f["faltas"]]
    principal = registro.principal()
    print("\nTrazabilidad del MVP: %d de %d funcionalidades (%d %%) · %s semana(s) de %s" % (
        len(trazadas), len(mvp), round(100.0 * len(trazadas) / len(mvp)) if mvp else 0,
        numero(sum(f["semanas"] for f in mvp)), numero(float(producto["criterios"]["presupuesto_semanas"] or 0))))
    if not principal:
        print("✖ No hay un diferenciador principal registrado (`diferenciador … --principal`).")
    elif not any(principal["id"] in f["diferenciadores"] for f in mvp):
        print("✖ El diferenciador principal (%s) no está en ninguna funcionalidad del MVP." % principal["id"])
    else:
        print("✔ El diferenciador principal (%s) está en el MVP." % principal["id"])
    print("El RICE lo calcula el script: alcance × impacto × confianza de los hallazgos (alta 100 %, media 80 %, "
          "baja 50 %) ÷ semanas.")
    print("Siguiente paso: %s" % ("`cerrar --sesion 4`." if mvp and len(trazadas) == len(mvp)
                                  else "completa lo que falta en 04-prd.md y vuelve a correr `trazabilidad`."))


def cmd_cerrar(args):
    carpeta, producto, registro = abrir(args)
    if args.sesion not in SESION:
        raise Fallo("No existe la sesión '%s'. Las que hay: %s" % (args.sesion, ", ".join(SESION)))
    faltan = pendientes_de(carpeta, producto, registro, args.sesion)
    if faltan:
        raise Fallo("La sesión %s · %s todavía no se puede cerrar:\n  - %s" % (
            args.sesion, SESION[args.sesion]["nombre"], "\n  - ".join(faltan)))
    producto["sesiones"].setdefault(args.sesion, {})["cerrada"] = ahora()
    guardar(carpeta, producto)
    siguiente = actualizar_estado(carpeta, producto)
    print("✔ Sesión %s · %s cerrada" % (args.sesion, SESION[args.sesion]["nombre"]))
    if args.sesion == "1g" and tipo_de(producto) != "nueva":
        principal = registro.principal()
        if not registro.viables():
            print("⚠ No hay ningún diferenciador viable%s: la puerta 1 lo va a marcar como criterio sin cumplir." % (
                " (%s, con confianza baja: sin triangular)" % ", ".join(d["id"] for d in registro.con_confianza_baja())
                if registro.con_confianza_baja() else ""))
        if principal and registro.sin_triangular(principal):
            print("⚠ Los hallazgos del diferenciador principal (%s) no están triangulados: la puerta 1 lo marca." % (
                principal["id"]))
    fuertes = registro.sustitutos_fuertes()
    if args.sesion == "1g" and fuertes and not any(registro.frente_al_sustituto(d)[0]
                                                   for d in registro.diferenciadores.values()):
        print("⚠ Ningún diferenciador supera a %s: la puerta 1 lo marca como criterio sin cumplir." % "; ".join(
            texto_sustituto(c) for c in fuertes))
    print("\n" + siguiente)


def cmd_puerta(args):
    carpeta, producto, registro = abrir(args)
    if not tipo_de(producto):
        raise Fallo("Falta el tipo de idea (`tipo`): cada puerta usa el juego de criterios de ese tipo.")
    resultado = veredicto(args.n, carpeta, producto, registro)
    lineas, cumplidos, total = bloque_puerta(args.n, carpeta, producto, registro, resultado)
    print(con_color("\n".join(lineas)))
    print("\nCriterios: cumple %d de %d." % (cumplidos, total))
    previa = vigente(decisiones(carpeta), args.n)
    if previa and previa["decision"] == "seguir":
        print("Esta puerta ya está decidida: seguir, el %s." % previa["fecha"].replace("T", " "))
    print("Siguiente paso: la skill recomienda y el usuario decide (el agente nunca corre `decidir`). Elige uno:")
    print("\n".join(comandos_decision(args.n, carpeta, producto, resultado)))


def cmd_decidir(args):
    carpeta, producto, registro = abrir(args)
    lista_decisiones = decisiones(carpeta)
    nodo = "P%d" % args.puerta
    if args.reabrir:
        previa = vigente(lista_decisiones, args.puerta)
        if not previa:
            raise Fallo("La puerta %d no tiene ninguna decisión vigente que reabrir." % args.puerta)
        previa["vigente"] = False
        afectadas = []
        for otro in dependientes(nodo):
            if otro.startswith("P"):
                posterior = vigente(lista_decisiones, int(otro[1]))
                if posterior:
                    posterior["vigente"] = False
            elif cerrada(producto, otro):
                afectadas.append(otro)
        lista_decisiones.append({"puerta": args.puerta, "decision": "reabierta", "fecha": ahora(), "desde": origen(),
                                 "vigente": False, "tipo": tipo_de(producto), "cumple": 0, "total": 0})
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        siguiente = actualizar_estado(carpeta, producto)
        print("✔ Puerta %d reabierta: vuelve a quedar pendiente de tu decisión." % args.puerta)
        if afectadas:
            print("· Las sesiones posteriores ya cerradas (%s) conservan su trabajo." % ", ".join(afectadas))
        print("\n" + siguiente)
        return
    if not tipo_de(producto):
        raise Fallo("Falta el tipo de idea (`tipo`): sin él no hay criterios que evaluar.")
    previas = [previo for previo in DEPENDE[nodo] if previo.startswith("P")] + [
        "P%d" % n for n in range(1, args.puerta)]
    sin_decidir = [p for p in previas if not cumplido(producto, lista_decisiones, p)]
    if sin_decidir:
        raise Fallo("Antes hay que decidir seguir en la puerta %s." % sin_decidir[0][1])
    criterios = criterios_puerta(args.puerta, carpeta, producto, registro)
    cumplidos = sum(1 for cumple, _, _ in criterios if cumple)
    registro_decision = {
        "puerta": args.puerta, "fecha": ahora(), "desde": origen(), "tipo": tipo_de(producto), "vigente": True,
        "cumple": cumplidos, "total": len(criterios),
        "criterios": [{"cumple": cumple, "texto": texto, "detalle": detalle} for cumple, texto, detalle in criterios],
        "criterios_cambiados": producto.get("criterios_cambios", []),
    }
    abiertas = [s for s in DEPENDE[nodo] if not cerrada(producto, s)]
    if args.seguir and abiertas:
        raise Fallo("Para seguir, antes cierra la(s) sesión(es) %s (`cerrar --sesion <id>`)." % ", ".join(abiertas))
    if args.ajustar and (args.ajustar not in SESION or nodo not in dependientes(args.ajustar)):
        raise Fallo("--ajustar lleva una sesión anterior a la puerta %d: %s" % (args.puerta, ", ".join(
            s["id"] for s in SESIONES if nodo in dependientes(s["id"]))))
    if args.descartar is not None and len(args.descartar.strip()) < 10:
        raise Fallo("--descartar lleva el motivo completo (qué evidencia en contra hay, o qué camino no "
                    "existe): es lo que queda como aprendizaje")
    resultado = veredicto(args.puerta, carpeta, producto, registro)
    tomada = "seguir" if args.seguir else "ajustar" if args.ajustar else "descartar"
    contra = tomada != resultado["recomienda"]
    motivo_usuario = (args.motivo or "").strip()
    if contra and len(motivo_usuario) < 10:
        raise Fallo("La skill recomienda %s (veredicto: %s; %s). Para %s en contra de la recomendación, agrega "
                    "--motivo \"<por qué decides distinto>\" (al menos 10 caracteres): queda registrado como decisión "
                    "contra la recomendación." % (texto_recomendacion(resultado), resultado["titulo"],
                                                  "; ".join(resultado["razones"]), tomada))
    registro_decision["recomendacion"] = {
        "veredicto": resultado["nivel"], "recomienda": resultado["recomienda"], "sesion": resultado["sesion"],
        "razones": resultado["razones"], "cambiaria": resultado["cambiaria"]}
    registro_decision["contra_recomendacion"] = contra
    if motivo_usuario:
        registro_decision["motivo_decision"] = motivo_usuario
    for decision in lista_decisiones:
        if decision["puerta"] == args.puerta:
            decision["vigente"] = False
    if contra:
        print("⚠ Decisión contra la recomendación (la skill recomendaba %s; veredicto: %s): queda registrada con tu "
              "motivo: «%s»" % (texto_recomendacion(resultado), resultado["titulo"], motivo_usuario))
    else:
        print("· Coincide con la recomendación de la skill (veredicto: %s)." % resultado["titulo"])
    resueltas = []
    for propuesta in propuestas_de(producto, args.puerta):  # la decisión de la puerta responde a sus propuestas
        propuesta.update(estado="seguir" if args.seguir else "ajustar %s" % args.ajustar if args.ajustar
                         else "descartar", resuelta=ahora())
        resueltas.append(propuesta["id"])
    if resueltas:
        registro_decision["propuestas"] = resueltas
        guardar(carpeta, producto)
    if args.seguir:
        registro_decision["decision"] = "seguir"
        lista_decisiones.append(registro_decision)
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        siguiente = actualizar_estado(carpeta, producto)
        print("✔ Puerta %d · %s: seguir (cumplía %d de %d criterios)" % (
            args.puerta, PUERTAS[args.puerta], cumplidos, len(criterios)))
        if cumplidos < len(criterios):
            print("⚠ Sigues con %d criterio(s) sin cumplir: queda anotado en decisiones.json." % (
                len(criterios) - cumplidos))
        regenerar_reporte(carpeta)
        print("\n" + con_color(siguiente))
    elif args.ajustar:
        sesion = args.ajustar
        reabiertas = [sesion] if cerrada(producto, sesion) else []
        for otro in dependientes(sesion):
            if otro.startswith("P"):
                for decision in lista_decisiones:
                    if decision["puerta"] == int(otro[1]):
                        decision["vigente"] = False
            elif cerrada(producto, otro):
                reabiertas.append(otro)
        for reabierta in reabiertas:
            producto["sesiones"][reabierta] = {"reabierta": ahora()}
        registro_decision.update(decision="ajustar", sesion=sesion)
        lista_decisiones.append(registro_decision)
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        guardar(carpeta, producto)
        siguiente = actualizar_estado(carpeta, producto)
        print("✔ Puerta %d · %s: ajustar la sesión %s" % (args.puerta, PUERTAS[args.puerta], sesion))
        print("· Se reabren: %s. Lo ya escrito se conserva: cada sesión corrige lo suyo y vuelve a cerrar." % (
            ", ".join(sorted(reabiertas, key=lambda s: [x["id"] for x in SESIONES].index(s))) or "ninguna"))
        lineas_sesion = [linea for linea, (_, de_sesion) in LINEAS.items() if de_sesion in reabiertas]
        herramienta = vacios_de_herramienta(producto, registro, lineas_sesion)
        if herramienta:
            print("⚠ %s tiene vacíos por límite de las herramientas (%s). Con las mismas herramientas, el ajuste da lo "
                  "mismo: antes, dale al agente un navegador o consigue un CSV de reseñas (references/investigacion.md "
                  "· Fuentes difíciles)." % (", ".join(sorted({v["linea"] for v in herramienta})), "; ".join(
                      "%s %s" % (DIMENSIONES[v["dimension"]], v["valor"]) for v in herramienta)))
        regenerar_reporte(carpeta)
        print("\n" + con_color(siguiente))
    else:
        motivo = args.descartar.strip()
        registro_decision.update(decision="descartar", motivo=motivo)
        lista_decisiones.append(registro_decision)
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        destino = mover_a_archivo(carpeta, producto, motivo, "descarte en la puerta %d" % args.puerta)
        print("✔ Puerta %d · %s: idea descartada y archivada en %s" % (args.puerta, PUERTAS[args.puerta], destino))
        print("· Motivo: %s" % motivo)
        regenerar_reporte(destino)
        print("Siguiente paso: no queda nada por hacer con esta idea. Para recuperarla: `%s`. Para evaluar otra: "
              "`nuevo --nombre \"<nombre>\"`." % orden("reabrir --idea %s" % destino.name, carpeta))


def cmd_siguiente(args):
    carpeta = resolver_carpeta(args)
    if not (carpeta / "producto.json").exists():
        archivadas = ideas_archivadas(carpeta)
        if archivadas:
            print("No hay ninguna idea activa en %s. Ideas archivadas:" % carpeta)
            for ruta in archivadas:
                archivo = (leer_json(ruta / "producto.json") or {}).get("archivo") or {}
                print("  - %s: %s" % (ruta.name, archivo.get("motivo", "sin motivo")))
            print("Siguiente paso: `reabrir --idea <nombre>` recupera una; `nuevo --nombre \"<nombre>\"` empieza "
                  "otra.")
        else:
            print("No hay ninguna idea en %s.\nSiguiente paso: la sesión 0 crea la carpeta con `nuevo --nombre "
                  "\"<nombre>\" --meta <ingresos al mes> --semanas <presupuesto>`." % carpeta)
        return
    with bloqueo(carpeta):
        producto = cargar(carpeta)
        print(con_color(actualizar_estado(carpeta, producto)))


def cmd_estado(args):
    carpeta = resolver_carpeta(args)
    with bloqueo(carpeta):
        producto = cargar(carpeta)
        registro = Registro(carpeta, producto["criterios"])
        siguiente = actualizar_estado(carpeta, producto)
    print(re.sub(r"\*\*", "", texto_resumen(carpeta, producto, registro)))
    print("\n" + con_color(siguiente))


def cmd_archivar(args):
    carpeta, producto, registro = abrir(args)
    destino = mover_a_archivo(carpeta, producto, args.motivo.strip(), "archivada a mano")
    print("✔ Idea \"%s\" archivada en %s (no se borra nada)" % (producto["nombre"], destino))
    regenerar_reporte(destino)
    print("Siguiente paso: `%s` la recupera; `nuevo --nombre \"<nombre>\"` empieza otra." % orden(
        "reabrir --idea %s" % destino.name, carpeta))


def cmd_reabrir(args):
    carpeta = resolver_carpeta(args)
    if (carpeta / "producto.json").exists():
        raise Fallo("Hay una idea activa en %s (%s): archívala antes de reabrir otra." % (
            carpeta, cargar(carpeta)["nombre"]))
    archivadas = ideas_archivadas(carpeta)
    if not archivadas:
        raise Fallo("No hay ideas archivadas en %s." % (carpeta / "archivo"))
    if args.idea:
        elegida = next((ruta for ruta in archivadas if ruta.name == args.idea), None)
    else:
        elegida = archivadas[0] if len(archivadas) == 1 else None
    if not elegida:
        raise Fallo("Elige cuál con --idea: %s" % ", ".join(ruta.name for ruta in archivadas))
    ocupados = [e.name for e in elegida.iterdir() if (carpeta / e.name).exists()]
    if ocupados:
        raise Fallo("No se puede reabrir sin pisar archivos que ya están en %s: %s" % (carpeta, ", ".join(ocupados)))
    for elemento in sorted(elegida.iterdir()):
        shutil.move(str(elemento), str(carpeta / elemento.name))
    elegida.rmdir()
    producto = cargar(carpeta)
    anterior = producto.get("archivo") or {}
    producto["archivo"] = None
    lista_decisiones = decisiones(carpeta)
    for decision in lista_decisiones:
        if decision["decision"] == "descartar":
            decision["vigente"] = False
    escribir_json(carpeta / "decisiones.json", lista_decisiones)
    guardar(carpeta, producto)
    siguiente = actualizar_estado(carpeta, producto)
    print("✔ Idea \"%s\" reabierta (estaba archivada: %s)" % (producto["nombre"], anterior.get("motivo", "")))
    regenerar_reporte(carpeta)
    print("\n" + siguiente)


# ---------------------------------------------------------------------------------------------------------------
# Reporte de una idea y tablero de ideas (HTML de un solo archivo, sin red: CSS y gráficos SVG en línea)

# Cada idea está en un solo estado: las descartadas y las pausadas viven en archivo/, pero "archivada" es un lugar, no
# un estado (antes se cruzaba con "descartada").
ESTADOS_IDEA = {"en-curso": ("En curso", "◐"), "lista": ("Lista para construir", "✔"),
                "descartada": ("Descartada", "✖"), "pausada": ("Pausada", "■")}
ORDEN_ESTADOS = ("en-curso", "lista", "descartada", "pausada")
TONO_ESTADO = {"en-curso": "neutro", "lista": "bien", "descartada": "mal", "pausada": "neutro"}
EXPLICACION_ESTADOS = ("Cada idea está en un solo estado: en curso (con sesiones o una puerta por delante), lista para "
                       "construir (la puerta 3 aprobó el PRD), descartada (en una puerta) o pausada (archivada a mano, "
                       "sin descartar). Las descartadas y las pausadas se guardan en archivo/ y se pueden reabrir.")
TIPOS_LLANO = {"existente": "Ya existen apps que hacen lo mismo y tienen usuarios.",
               "variante": "Ya existen apps parecidas, pero esta idea cambia algo importante.",
               "nueva": "No hay apps que hagan lo mismo: la evidencia sale de casos parecidos (por analogía)."}
CRITERIOS_LLANO = {
    "demanda": ("Demanda", "¿La gente lo necesita hoy?"),
    "monetizacion": ("Monetización", "¿Se puede ganar dinero con ella?"),
    "facilidad": ("Facilidad", "¿Se construye en poco tiempo? (estimación, sin fuentes)"),
    "riesgo": ("Riesgo de políticas", "¿Lo permiten las tiendas y las leyes? (5 = sin riesgo)"),
    "diferenciacion": ("Diferenciación", "¿Por qué la elegirían frente a lo que ya existe?"),
}
PUERTAS_LLANO = {1: "¿Hay una oportunidad real?", 2: "¿Puede sostenerse como negocio?",
                 3: "¿El primer producto está bien definido y cabe en el tiempo?"}
DECISIONES_LLANO = {"seguir": "Seguir", "ajustar": "Ajustar", "descartar": "Descartar"}
LINEAS_LLANO = {"competencia": "Competencia", "voz-del-usuario": "Voz del usuario", "demanda": "Demanda",
                "monetizacion": "Monetización", "politicas": "Políticas y riesgos", "diferenciacion": "Diferenciación",
                "estrategia": "Estrategia", "validacion": "Validación"}
PELDANOS_LLANO = {1: "Hace lo mismo", 2: "Variante", 3: "Mismo mecanismo en otra categoría",
                  4: "Cómo se resuelve hoy sin una app así", 5: "La necesidad de fondo", 6: "Hipótesis general"}
TIPOS_FUENTE_LLANO = {"medido": "dato medido", "usuario": "opinión de usuarios", "terceros": "análisis de terceros",
                      "opinion": "opinión sin datos", "oficial": "texto oficial"}
DIFERENCIADOR_LLANO = {"viable": ("Viable", "bien", "Tiene evidencia sólida y cumple todos los criterios."),
                       "baja": ("Prometedor, sin confirmar", "aviso",
                                "Cumple los criterios, pero su evidencia no está confirmada por 3 fuentes."),
                       "no": ("Todavía no es viable", "mal", "Le falta al menos un criterio.")}
COPIABLE_LLANO = {"baja": "Difícil de copiar", "media": "Copiable con esfuerzo", "alta": "Fácil de copiar"}
TONO_CONFIANZA = {3: "bien", 2: "aviso", 1: "mal", 0: "neutro"}

ESTILO = """
:root{color-scheme:light dark;--fondo:#f4f3ef;--tarjeta:#fcfcfb;--borde:#dcdad3;--texto:#0b0b0b;--texto-2:#52514e;
--suave:#ecebe6;--serie:#2a78d6;--pista:#e3e1da;--bien:#0a7d0a;--bien-f:#e3f4e3;--aviso:#8a5a00;--aviso-f:#fdf1d6;
--mal:#b42b2b;--mal-f:#fbe5e5;--neutro:#52514e;--neutro-f:#ecebe6;--enlace:#1f5fae}
@media (prefers-color-scheme:dark){:root{--fondo:#121211;--tarjeta:#1a1a19;--borde:#383835;--texto:#f0efec;
--texto-2:#c3c2b7;--suave:#242422;--serie:#3987e5;--pista:#383835;--bien:#5fd35f;--bien-f:#16301a;--aviso:#fab219;
--aviso-f:#33280f;--mal:#f08080;--mal-f:#3a1a1a;--neutro:#c3c2b7;--neutro-f:#2a2a28;--enlace:#7fb2f0}}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--texto);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,
sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.7rem;line-height:1.2;margin:0 0 4px}
h2{font-size:1.15rem;margin:0 0 12px}
h3{font-size:1rem;margin:0 0 4px}
p{margin:0 0 8px}
a{color:var(--enlace)}
.sub{color:var(--texto-2);margin:0 0 20px}
.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;padding:18px 20px;margin:0 0 16px}
.resumen{border-width:2px}
.fila{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.cifras{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.cifra{background:var(--suave);border-radius:10px;padding:10px 12px}
.cifra b{display:block;font-size:1.35rem;line-height:1.2}
.cifra span{color:var(--texto-2);font-size:.85rem}
.chip{display:inline-block;border-radius:999px;padding:2px 10px;font-size:.85rem;font-weight:600;white-space:nowrap}
.bien{color:var(--bien);background:var(--bien-f)}.aviso{color:var(--aviso);background:var(--aviso-f)}
.mal{color:var(--mal);background:var(--mal-f)}.neutro{color:var(--neutro);background:var(--neutro-f)}
.estado{font-size:1rem;padding:4px 14px}
.ref{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--texto-2);white-space:nowrap}
.nota{color:var(--texto-2);font-size:.9rem}
.dato{display:grid;grid-template-columns:minmax(150px,1.1fr) minmax(120px,1.4fr) auto;gap:6px 14px;align-items:center;
padding:8px 0;border-top:1px solid var(--borde)}
.dato:first-of-type{border-top:0}
.dato svg{width:100%;height:18px;display:block}
.lista{list-style:none;margin:0;padding:0}
.lista>li{padding:12px 0;border-top:1px solid var(--borde)}
.lista>li:first-child{border-top:0;padding-top:0}
details{margin-top:6px}
summary{cursor:pointer;color:var(--texto-2);font-size:.9rem}
details ul{margin:6px 0 0;padding-left:18px;font-size:.9rem}
details.grupo{border-top:1px solid var(--borde);padding:10px 0 0;margin:10px 0 0}
details.grupo>summary{color:var(--texto);font-size:1rem}
details.grupo>ul.lista{padding-left:0;font-size:1rem;margin-top:10px}
.tabla{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:8px 10px;border-top:1px solid var(--borde);vertical-align:top}
th{color:var(--texto-2);font-weight:600;border-top:0}
.grafico svg{width:100%;max-width:640px;height:auto;display:block}
.grafico text{fill:var(--texto);font:13px system-ui,-apple-system,sans-serif}
.grafico .t2{fill:var(--texto-2)}
.vacio{color:var(--texto-2);font-style:italic}
.veredicto{border:2px solid var(--borde);border-left-width:12px;border-radius:12px;padding:18px 20px;margin:0 0 16px}
.veredicto.mal{border-color:var(--mal);background:var(--mal-f);color:var(--texto)}
.veredicto.aviso{border-color:var(--aviso);background:var(--aviso-f);color:var(--texto)}
.veredicto.bien{border-color:var(--bien);background:var(--bien-f);color:var(--texto)}
.veredicto.neutro{background:var(--suave);color:var(--texto)}
.veredicto .titulo{font-size:1.6rem;font-weight:800;line-height:1.2;margin:0 0 4px}
.veredicto.mal .titulo{color:var(--mal)}.veredicto.aviso .titulo{color:var(--aviso)}
.veredicto.bien .titulo{color:var(--bien)}
.veredicto .recomienda{font-size:1.15rem;font-weight:700;margin:0 0 10px}
.veredicto ol,.veredicto ul{margin:4px 0 10px;padding-left:22px}
.veredicto h3{margin-top:8px}
.veredicto.compacto{padding:10px 14px;margin:8px 0 0;border-left-width:8px}
.veredicto.compacto .titulo{font-size:1.05rem}
.fuentes{font-size:.9rem;color:var(--texto-2)}
footer{color:var(--texto-2);font-size:.85rem;margin-top:24px}
@media (max-width:640px){.dato{grid-template-columns:1fr}h1{font-size:1.4rem}.tarjeta{padding:14px}}
"""


def llano(texto):
    """El texto sin los comandos entre comillas invertidas: lo visible del reporte no lleva sintaxis del script."""
    texto = re.sub(r"\s*\(`[^`]*`\)", "", str(texto))
    return re.sub(r"`([^`]*)`", r"\1", texto)


def chip(texto, tono, icono=""):
    return '<span class="chip %s">%s%s</span>' % (tono, (icono + " ") if icono else "", escape(texto))


def ref(*ids):
    ids = [i for i in ids if i]
    return ' <span class="ref" title="Referencia en el registro de la idea">ref. %s</span>' % escape(", ".join(ids)) \
        if ids else ""


def tarjeta(titulo, cuerpo, clase=""):
    return '<section class="tarjeta %s"><h2>%s</h2>%s</section>' % (clase, escape(titulo), cuerpo)


def pagina(titulo, cuerpo):
    return ("<!doctype html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>%s</title>\n"
            "<style>%s</style>\n</head>\n<body>\n<main>\n%s\n</main>\n</body>\n</html>\n" % (
                escape(titulo), ESTILO, cuerpo))


def enlace(fuente):
    """El enlace de una fuente; un CSV del usuario va como texto (es un archivo local)."""
    nombre = fuente.get("autor") or fuente.get("dominio") or fuente["id"]
    if str(fuente.get("url", "")).startswith(("http://", "https://")):
        return '<a href="%s" rel="noopener noreferrer">%s</a>' % (escape(fuente["url"], quote=True), escape(nombre))
    return "%s (reseñas que aportó el usuario)" % escape(nombre)


def barra(valor, maximo, titulo, marca=None, alto=18):
    """Una barra horizontal en SVG (una sola serie): la pista, el valor y, si hay, una marca vertical (el mínimo)."""
    ancho = 100.0 * max(0.0, min(valor, maximo)) / maximo if maximo else 0
    marca_svg = ""
    if marca is not None and maximo:
        x = 100.0 * marca / maximo
        marca_svg = '<line x1="%.2f" x2="%.2f" y1="0" y2="%d" stroke="currentColor" stroke-width="0.6" ' \
                    'stroke-dasharray="1.5 1"/>' % (x, x, alto)
    return ('<svg viewBox="0 0 100 %d" preserveAspectRatio="none" role="img" aria-label="%s"><title>%s</title>'
            '<rect x="0" y="4" width="100" height="%d" rx="2" fill="var(--pista)"/>'
            '<rect x="0" y="4" width="%.2f" height="%d" rx="2" fill="var(--serie)"/>%s</svg>' % (
                alto, escape(titulo, quote=True), escape(titulo), alto - 8, ancho, alto - 8, marca_svg))


def estado_idea(carpeta, producto):
    """El estado de una idea para el reporte y el tablero: {clave, etiqueta, motivo, ultima}."""
    lista_decisiones = decisiones(carpeta)
    hechas = [d for d in lista_decisiones if d.get("decision") in DECISIONES_LLANO]
    ultima = hechas[-1] if hechas else None
    archivo = producto.get("archivo")
    if archivo:
        clave = "descartada" if str(archivo.get("por", "")).startswith("descarte") else "pausada"
        motivo = archivo.get("motivo", "")
    else:
        final = vigente(lista_decisiones, 3)
        if final and final["decision"] == "seguir":
            clave = "lista"
            motivo = "Puerta 3: seguir, con %d de %d criterios cumplidos." % (final.get("cumple", 0),
                                                                              final.get("total", 0))
        else:
            clave = "en-curso"
            motivo = ""
    return {"clave": clave, "etiqueta": ESTADOS_IDEA[clave][0], "icono": ESTADOS_IDEA[clave][1], "motivo": motivo,
            "ultima": ultima, "archivo": archivo}


def paso_corto(carpeta, producto, registro):
    """El paso siguiente en una frase, sin comandos."""
    if producto.get("archivo"):
        return "Ninguno: la idea está archivada. Si aparece evidencia nueva, el comando reabrir la recupera."
    lista_decisiones = decisiones(carpeta)
    abiertas = [s for s in SESIONES if not cerrada(producto, s["id"])
                and disponible(producto, lista_decisiones, s["id"])]
    if abiertas:
        return "%s: %s." % ("Toca la sesión" if len(abiertas) == 1 else "Tocan estas sesiones, en paralelo",
                            ", ".join("%s · %s" % (s["id"], s["nombre"]) for s in abiertas))
    for numero_puerta in PUERTAS:
        nodo = "P%d" % numero_puerta
        if disponible(producto, lista_decisiones, nodo) and not cumplido(producto, lista_decisiones, nodo):
            criterios = criterios_puerta(numero_puerta, carpeta, producto, registro)
            return "Decidir la puerta %d · %s (%s): hoy cumple %d de %d criterios. La decisión es tuya." % (
                numero_puerta, PUERTAS[numero_puerta], PUERTAS_LLANO[numero_puerta].lower(),
                sum(1 for c in criterios if c[0]), len(criterios))
    return "Proceso cerrado: el PRD está aprobado. Lo siguiente es construir el MVP, una funcionalidad a la vez."


def fecha_corta(texto):
    return str(texto or "").replace("T", " ")[:16]


def veredicto_de_idea(carpeta, producto, registro):
    """El veredicto que encabeza el reporte y el tablero: el de la puerta pendiente o, si no hay, el de la última
    puerta decidida, calculado con las reglas y la evidencia de hoy: {resultado, decision} o None."""
    lista_decisiones = decisiones(carpeta)
    if not producto.get("archivo") and tipo_de(producto):
        for numero_puerta in PUERTAS:
            nodo = "P%d" % numero_puerta
            if disponible(producto, lista_decisiones, nodo) and not cumplido(producto, lista_decisiones, nodo):
                return {"resultado": veredicto(numero_puerta, carpeta, producto, registro), "decision": None}
    hechas = [d for d in lista_decisiones if d.get("decision") in DECISIONES_LLANO]
    if not hechas or not tipo_de(producto):
        return None
    ultima = hechas[-1]
    return {"resultado": veredicto(ultima["puerta"], carpeta, producto, registro), "decision": ultima}


def seccion_veredicto(info, compacto=False):
    """El banner grande y con color del veredicto de la skill: arriba del reporte y, compacto, en el tablero."""
    if not info:
        if compacto:
            return ""
        return ('<section class="veredicto neutro"><p class="titulo">Todavía sin veredicto</p><p>La skill calcula '
                'su veredicto y su recomendación al llegar a la puerta 1, cuando cierra la investigación.</p>'
                '</section>')
    resultado, decision = info["resultado"], info["decision"]
    datos = VEREDICTOS[resultado["nivel"]]
    cuando = ("hoy, pendiente de tu decisión" if decision is None else
              "recalculado hoy con las reglas actuales (la puerta se decidió el %s)" % fecha_corta(decision["fecha"]))
    titulo = '<p class="titulo">%s %s</p><p class="recomienda">Puerta %d · %s · la skill recomienda: %s</p>' % (
        datos["marca"], escape(datos["titulo"]), resultado["puerta"], escape(PUERTAS[resultado["puerta"]]),
        escape(texto_recomendacion(resultado)))
    if compacto:
        return '<div class="veredicto compacto %s">%s<p class="nota">%s</p></div>' % (
            datos["tono"], titulo, escape(resultado["razones"][0] + "." if resultado["razones"] else ""))
    partes = [titulo, '<p class="nota">Veredicto %s.%s</p>' % (escape(cuando), escape(
        " Provisional: falta cerrar %s." % ", ".join("la sesión %s" % s for s in resultado["provisional"]))
        if resultado["provisional"] else "")]
    partes.append("<h3>Por qué</h3><ol>%s</ol>" % "".join("<li>%s</li>" % escape(r) for r in resultado["razones"]))
    partes.append("<h3>Qué cambiaría el veredicto</h3><ul>%s</ul>" % "".join(
        "<li>%s</li>" % escape(c) for c in resultado["cambiaria"]))
    if decision:
        tomada = DECISIONES_LLANO[decision["decision"]].lower() + (
            " la sesión %s" % decision["sesion"] if decision.get("sesion") else "")
        if decision.get("contra_recomendacion"):
            partes.append("<p>%s Decidiste %s en contra de la recomendación. Tu motivo: «%s».</p>" % (
                chip("Decisión contra la recomendación", "aviso", "⚠"), escape(tomada),
                escape(decision.get("motivo_decision", ""))))
        elif decision.get("recomendacion"):
            partes.append("<p>Decidiste %s, como recomendaba la skill.</p>" % escape(tomada))
        else:
            partes.append('<p class="nota">Decidiste %s antes de que la skill diera recomendaciones.</p>' % escape(
                tomada))
    partes.append('<p class="nota">La skill recomienda con reglas fijas; la decisión es tuya.</p>')
    return '<section class="veredicto %s">%s</section>' % (datos["tono"], "".join(partes))


def hallazgos_decisivos(producto, registro, estado, info, maximo=5):
    """Los 3 a 5 hallazgos que decidieron: los que cita el motivo, los que sostienen el veredicto (los criterios que
    fallaron o lo que lo hace viable) y, si faltan, los clave de menor confianza."""
    textos = [estado.get("motivo") or ""]
    if info and info["decision"]:
        textos.append(info["decision"].get("motivo") or "")
        textos += [c.get("detalle", "") for c in info["decision"].get("criterios", []) if not c.get("cumple")]
    ids = [i for texto in textos for i in re.findall(r"\bH-[A-Z]{3}-\d+\b", texto)]
    ids += (info or {}).get("resultado", {}).get("hallazgos", [])
    elegidos = [i for i in dict.fromkeys(ids) if i in registro.hallazgos][:maximo]
    if len(elegidos) < 3:
        claves = sorted((h for h in registro.hallazgos.values() if h.get("critico") and h["id"] not in elegidos),
                        key=lambda h: (registro.evaluar(h)["nivel"], h["id"]))
        elegidos += [h["id"] for h in claves[:3 - len(elegidos)]]
    return [registro.hallazgos[i] for i in elegidos]


def lista_decisivos(registro, hallazgos):
    items = []
    for hallazgo in hallazgos:
        etiqueta, _ = etiqueta_llana(registro, hallazgo)
        fuentes = registro.fuentes_de(hallazgo.get("fuentes", []))
        items.append('<li><p>%s%s</p><div class="fila">%s<span class="nota">%s</span></div><p class="fuentes">'
                     '%s: %s</p></li>' % (
                         escape(hallazgo.get("texto", "")), ref(hallazgo["id"]), etiqueta,
                         escape(LINEAS_LLANO.get(hallazgo["linea"], hallazgo["linea"])),
                         "Fuente" if len(fuentes) == 1 else "Fuentes",
                         " · ".join(enlace(f) for f in fuentes) or "sin fuentes registradas"))
    return '<ul class="lista">%s</ul>' % "".join(items)


def seccion_resumen(carpeta, producto, registro, estado, info=None):
    tono = TONO_ESTADO[estado["clave"]]
    partes = ['<div class="fila">%s</div>' % chip(estado["etiqueta"], tono + " estado", estado["icono"])]
    ultima = estado["ultima"]
    if estado["archivo"]:
        partes.append("<p><b>Decisión:</b> %s el %s.</p>" % (
            escape("descartada en la puerta %d" % ultima["puerta"] if estado["clave"] == "descartada" and ultima
                   else "archivada a mano"), escape(fecha_corta(estado["archivo"].get("fecha")))))
        partes.append("<p><b>Motivo:</b> %s</p>" % escape(estado["motivo"] or "sin motivo registrado"))
    elif ultima:
        partes.append("<p><b>Última decisión:</b> puerta %d · %s, %s el %s (cumplía %d de %d criterios).</p>" % (
            ultima["puerta"], escape(PUERTAS[ultima["puerta"]]), escape(DECISIONES_LLANO[ultima["decision"]].lower()
                                                                       + (" la sesión %s" % ultima["sesion"]
                                                                          if ultima.get("sesion") else "")),
            escape(fecha_corta(ultima["fecha"])), ultima.get("cumple", 0), ultima.get("total", 0)))
    else:
        partes.append("<p><b>Decisión:</b> todavía ninguna puerta decidida.</p>")
    partes.append("<p><b>Siguiente paso:</b> %s</p>" % escape(paso_corto(carpeta, producto, registro)))
    puntaje = producto.get("puntaje")
    nueva = tipo_de(producto) == "nueva"
    minimo = int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
    global_ = confianzas(registro)[1]
    claves = [h for h in registro.hallazgos.values() if h.get("critico")]
    confirmados = sum(1 for h in claves if registro.evaluar(h)["triangulado"])
    cifras = [
        ("%d/25" % puntaje["total"] if puntaje else "—", "puntaje (mínimo %d)" % minimo),
        (NIVELES[global_].capitalize() if puntaje else "—", "confianza global"),
        ("%d de %d" % (len(registro.viables()), len(registro.diferenciadores)), "diferenciadores viables"),
        ("%d de %d" % (confirmados, len(claves)), "hallazgo clave confirmado" if len(claves) == 1
         else "hallazgos clave confirmados"),
        (str(len(registro.fuentes)), "fuentes registradas"),
    ]
    partes.append('<div class="cifras">%s</div>' % "".join(
        '<div class="cifra"><b>%s</b><span>%s</span></div>' % (escape(v), escape(t)) for v, t in cifras))
    vigente_ = puntaje_vigente(producto, registro)
    if vigente_ and vigente_["incoherencias"]:
        partes.append("<p>%s El puntaje se registró con reglas anteriores (o la evidencia cambió después): con las "
                      "de hoy sería %d/25. %s.</p>" % (chip("Puntaje desactualizado", "aviso", "⚠"),
                                                       vigente_["total"], escape("; ".join(
                                                           vigente_["incoherencias"]).capitalize())))
    decisivos = hallazgos_decisivos(producto, registro, estado, info)
    if decisivos:
        partes.append("<h3>Los hallazgos que decidieron</h3>" + lista_decisivos(registro, decisivos))
    return tarjeta("Resumen ejecutivo", "".join(partes), "resumen")


def seccion_puntaje(producto, registro):
    puntaje = producto.get("puntaje")
    if not puntaje:
        return tarjeta("Puntaje por criterio", '<p class="vacio">Todavía sin puntaje: lo calcula la síntesis de la '
                                               'investigación (sesión 1f).</p>')
    por_criterio, global_ = confianzas(registro)
    filas = []
    for criterio in CRITERIOS_PUNTAJE:
        nombre, pregunta = CRITERIOS_LLANO[criterio]
        valor, nivel = puntaje["valores"][criterio], por_criterio[criterio]
        if nivel is None:
            confianza = chip("estimación" if criterio == "facilidad" else "sin diferenciador", "neutro")
        else:
            confianza = chip("confianza " + NIVELES[nivel], TONO_CONFIANZA[nivel])
        filas.append('<div class="dato"><div><h3>%s · %d de 5</h3><span class="nota">%s</span></div>%s<div>%s</div>'
                     '</div>' % (escape(nombre), valor, escape(pregunta), barra(valor, 5, "%s: %d de 5" % (
                         nombre, valor)), confianza))
    nueva = tipo_de(producto) == "nueva"
    minimo = int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
    total = puntaje["total"]
    filas.append('<div class="dato"><div><h3>Total · %d de 25</h3><span class="nota">La línea punteada es el mínimo de '
                 'la puerta 1: %d.</span></div>%s<div>%s</div></div>' % (
                     total, minimo, barra(total, 25, "Total: %d de 25 (mínimo %d)" % (total, minimo), marca=minimo),
                     chip("alcanza el mínimo" if total >= minimo else "no alcanza el mínimo",
                          "bien" if total >= minimo else "mal", "✔" if total >= minimo else "✖")))
    texto = ('<p class="nota">Cada criterio va de 1 a 5 con anclas fijas. La confianza dice qué tan sólida es la '
             'evidencia detrás de cada número; la global es la más baja: <b>%s</b>.</p>' % escape(NIVELES[global_]))
    if puntaje.get("mitigacion"):
        texto += "<p><b>Mitigación del riesgo de políticas:</b> %s</p>" % escape(puntaje["mitigacion"])
    vigente_ = puntaje_vigente(producto, registro)
    if vigente_ and vigente_["incoherencias"]:
        texto += ("<p>%s Este puntaje se registró el %s con reglas anteriores, o la evidencia cambió después. Con las "
                  "reglas de hoy sería <b>%d/25</b>:</p><ul>%s</ul>" % (
                      chip("Registrado con reglas anteriores", "aviso", "⚠"), escape(fecha_corta(puntaje.get("fecha"))),
                      vigente_["total"], "".join("<li>%s</li>" % escape(i) for i in vigente_["incoherencias"])))
    return tarjeta("Puntaje por criterio", texto + "".join(filas))


def seccion_puertas(carpeta, producto, registro):
    lista_decisiones = decisiones(carpeta)
    items = []
    for numero_puerta, nombre in PUERTAS.items():
        decision = vigente(lista_decisiones, numero_puerta)
        historial = [d for d in lista_decisiones if d["puerta"] == numero_puerta and d.get("decision") in
                     DECISIONES_LLANO]
        nodo = "P%d" % numero_puerta
        criterios, cuando = None, ""
        if decision:
            tono = {"seguir": "bien", "ajustar": "aviso", "descartar": "mal"}[decision["decision"]]
            estado = chip(DECISIONES_LLANO[decision["decision"]] + (" la sesión %s" % decision["sesion"]
                                                                    if decision.get("sesion") else ""), tono)
            linea = "Decidida el %s · cumplía %d de %d criterios." % (
                fecha_corta(decision["fecha"]), decision.get("cumple", 0), decision.get("total", 0))
            recomendacion = decision.get("recomendacion")
            if recomendacion:
                linea += " La skill recomendaba %s (%s)." % (texto_recomendacion(recomendacion),
                                                             VEREDICTOS[recomendacion["veredicto"]]["titulo"].lower())
            if decision.get("contra_recomendacion"):
                estado += chip("Contra la recomendación", "aviso", "⚠")
                linea += " Tu motivo: «%s»." % decision.get("motivo_decision", "")
            criterios = [(c["cumple"], c["texto"], c.get("detalle", "")) for c in decision.get("criterios", [])]
            cuando = "al decidir"
        elif not producto.get("archivo") and disponible(producto, lista_decisiones, nodo):
            criterios = criterios_puerta(numero_puerta, carpeta, producto, registro)
            resultado = veredicto(numero_puerta, carpeta, producto, registro)
            datos = VEREDICTOS[resultado["nivel"]]
            estado = chip("Pendiente de tu decisión", "aviso", "◐") + chip(
                "%s · recomienda %s" % (datos["titulo"], texto_recomendacion(resultado)), datos["tono"], datos["marca"])
            linea = "Hoy cumple %d de %d criterios." % (sum(1 for c in criterios if c[0]), len(criterios))
            cuando = "evaluados hoy"
        else:
            estado = chip("Todavía no se llega", "neutro")
            linea = ""
        detalle = ""
        if criterios:
            detalle = "<details><summary>Criterios (%s)</summary><ul>%s</ul></details>" % (cuando, "".join(
                "<li>%s %s%s</li>" % ("✔" if c else "✖", escape(t), (" · <span class=\"nota\">%s</span>" % escape(d))
                                      if d else "") for c, t, d in criterios))
        if len(historial) > 1:
            detalle += "<details><summary>Historial (%d decisiones)</summary><ul>%s</ul></details>" % (
                len(historial), "".join("<li>%s · %s%s</li>" % (
                    escape(fecha_corta(d["fecha"])), escape(DECISIONES_LLANO[d["decision"]]),
                    escape(" la sesión %s" % d["sesion"]) if d.get("sesion") else "") for d in historial))
        items.append('<li><div class="fila"><h3>Puerta %d · %s</h3>%s</div><p class="nota">%s</p><p>%s</p>%s</li>' % (
            numero_puerta, escape(nombre), estado, escape(PUERTAS_LLANO[numero_puerta]), escape(linea), detalle))
    pendientes = [p for p in producto.get("propuestas", []) if p.get("estado") == "pendiente"]
    extra = ""
    if pendientes:
        extra = "<details><summary>Propuestas pendientes para la puerta (%d)</summary><ul>%s</ul></details>" % (
            len(pendientes), "".join("<li>%s%s</li>" % (escape(p["texto"]), ref(p["id"])) for p in pendientes))
    return tarjeta("Puertas", '<p class="nota">En cada puerta decides seguir, ajustar una parte o descartar. El script '
                              'evalúa los criterios y la skill recomienda; la decisión es tuya.</p>'
                              '<ul class="lista">%s</ul>%s' % (
                                  "".join(items), extra))


def seccion_diferenciadores(producto, registro):
    if not registro.diferenciadores:
        return tarjeta("Diferenciadores", '<p class="vacio">Sin diferenciadores registrados (los busca la sesión '
                                          '1g).</p>')
    fuertes = registro.sustitutos_fuertes()
    texto = ('<p class="nota">Un diferenciador es la razón para elegir esta app y no otra. Es viable si tiene '
             'evidencia confirmada, se percibe, cabe en el presupuesto y supera al sustituto gratuito o nativo, '
             'si hay uno.</p>')
    if fuertes:
        texto += "<p>%s <b>Sustituto que ya resuelve la necesidad:</b> %s.</p>" % (chip("Sustituto fuerte", "aviso", "⚠"),
                                                                                   escape("; ".join(texto_sustituto(c)
                                                                                                    for c in fuertes)))
    items = []
    orden_estado = {"viable": 0, "baja": 1, "no": 2}
    for diferenciador in sorted(registro.diferenciadores.values(),
                                key=lambda d: (not d.get("principal"), orden_estado[registro.estado(d)], d["id"])):
        estado = registro.estado(diferenciador)
        nombre, tono, explicacion = DIFERENCIADOR_LLANO[estado]
        criterios = registro.viabilidad(diferenciador)
        sustituto = criterios[4]
        se_ve = ("Se ve en la ficha de la tienda: atrae descargas." if diferenciador.get("se_ve") == "ficha"
                 else "Se nota al usarla: retiene usuarios.")
        items.append(
            '<li><div class="fila"><h3>%s</h3>%s%s</div><p>%s%s</p><p class="nota">%s · %s · %s · %s</p>'
            '<p class="nota">%s %s</p><details><summary>Detalle de los criterios</summary><ul>%s</ul></details></li>' % (
                escape(diferenciador.get("texto", "")), chip(nombre, tono, {"bien": "✔", "aviso": "⚠", "mal": "✖"}[tono]),
                chip("principal", "neutro", "★") if diferenciador.get("principal") else "",
                escape(explicacion), ref(diferenciador["id"]), escape(se_ve),
                escape(COPIABLE_LLANO.get(diferenciador.get("copiable"), "copiabilidad sin evaluar")),
                escape(diferenciador.get("motivo", "")), plural(float(diferenciador.get("semanas") or 0), "semana"),
                "✔" if sustituto[0] else "✖", escape(llano(sustituto[1])),
                "".join("<li>%s %s</li>" % ("✔" if c else "✖", escape(t)) for c, t in criterios)))
    return tarjeta("Diferenciadores", texto + '<ul class="lista">%s</ul>' % "".join(items))


def etiqueta_llana(registro, hallazgo):
    evaluacion = registro.evaluar(hallazgo)
    confirmado = ("confirmado por una fuente oficial" if evaluacion["oficial"] else
                  "confirmado por %s fuentes independientes" % registro.criterios["fuentes_minimas"]
                  if evaluacion["triangulado"] else "sin confirmar")
    return chip("confianza %s · %s" % (evaluacion["confianza"], confirmado), TONO_CONFIANZA[evaluacion["nivel"]]), \
        evaluacion


def seccion_hallazgos(registro):
    claves = [h for h in registro.hallazgos.values() if h.get("critico")]
    if not claves:
        return tarjeta("Hallazgos clave", '<p class="vacio">Sin hallazgos clave registrados.</p>')
    grupos = {}
    for hallazgo in sorted(claves, key=lambda h: (list(LINEAS).index(h["linea"]) if h["linea"] in LINEAS else 99,
                                                  h["id"])):
        etiqueta, evaluacion = etiqueta_llana(registro, hallazgo)
        items = grupos.setdefault(hallazgo["linea"], [[], 0])
        items[1] += 1 if evaluacion["triangulado"] else 0
        items = items[0]
        fuentes = registro.fuentes_de(hallazgo.get("fuentes", []))
        lista_fuentes = "".join("<li>%s · %s · %s%s%s</li>" % (
            enlace(f), escape(TIPOS_FUENTE_LLANO.get(f.get("tipo"), f.get("tipo", ""))),
            escape("publicada el %s" % f["publicada"] if f.get("publicada") else "fecha de publicación desconocida"),
            escape(" · versión %s" % f["version"] if f.get("version") else ""),
            "" if registro.vigente(f) and not registro.acumulada(hallazgo, f) else
            ' · <span class="nota">no cuenta (%s)</span>' % escape(
                "dato acumulado" if registro.vigente(f) else "sin fecha o antigua")) for f in fuentes)
        contra = registro.fuentes_de(hallazgo.get("en_contra", []))
        en_contra = ("<li>En contra: %s</li>" % ", ".join(enlace(f) for f in contra)) if contra else (
            "<li>Búsqueda en contra: %s</li>" % escape(hallazgo["sin_contra"]) if hallazgo.get("sin_contra") else "")
        faltan = "".join("<li>Le falta: %s</li>" % escape(f) for f in evaluacion["faltan"])
        extra = ""
        if hallazgo.get("bloquea"):
            extra = "<p>%s</p>" % chip("Bloqueante en %s" % ", ".join(hallazgo["bloquea"]), "mal", "✖")
        items.append('<li><p>%s%s</p><div class="fila">%s<span class="nota">%s</span></div>%s<details><summary>'
                     'Fuentes (%d) y lo que le falta</summary><ul>%s%s%s</ul></details></li>' % (
                         escape(hallazgo.get("texto", "")), ref(hallazgo["id"]), etiqueta,
                         escape(LINEAS_LLANO.get(hallazgo["linea"], hallazgo["linea"])), extra, len(fuentes),
                         lista_fuentes, en_contra, faltan))
    bloques = "".join(
        '<details class="grupo"><summary><b>%s</b> · %s, %s</summary><ul class="lista">%s'
        '</ul></details>' % (escape(LINEAS_LLANO.get(linea, linea)), plural(len(items), "hallazgo"),
                             plural(confirmados, "confirmado"), "".join(items))
        for linea, (items, confirmados) in grupos.items())
    return tarjeta("Hallazgos clave", '<p class="nota">Lo que sostiene el puntaje y las puertas, por línea de '
                                      'investigación. Un hallazgo está confirmado con 3 fuentes independientes y '
                                      'recientes (o, en políticas, con el texto oficial).</p>' + bloques)


def seccion_competidores(registro):
    if not registro.competidores:
        return tarjeta("Competidores y sustitutos", '<p class="vacio">La matriz está vacía.</p>')
    quejas = {}
    for hallazgo in registro.hallazgos.values():
        for referencia in hallazgo.get("competidores", []):
            fila = registro.competidor(referencia)
            if fila:
                quejas.setdefault(fila["id"], []).append(hallazgo["id"])
    filas = []
    for fila in sorted(registro.competidores.values(), key=lambda c: (c.get("peldano", 9), -(c.get("descargas")
                                                                                            or 0))):
        que = PELDANOS_LLANO.get(fila.get("peldano"), "")
        if fila.get("peldano") == 4:
            que += " · %s · %s" % (SUSTITUTOS.get(fila.get("sustituto"), "sin evaluar"),
                                   RESUELVE.get(fila.get("resuelve"), "sin evaluar"))
        precio = " · ".join(str(v) for v in (fila.get("precio"), fila.get("modelo")) if v)
        filas.append("<tr><td>%s%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            escape(fila.get("nombre", "")), " ★" if registro.con_traccion(fila) else "", ref(fila["id"]), escape(que),
            escape(numero(fila["descargas"]) if fila.get("descargas") else "—"),
            escape(numero(fila["nota"]) if fila.get("nota") else "—"), escape(precio or "—"),
            '<details><summary>%s</summary><p class="ref">%s</p></details>' % (
                plural(len(quejas[fila["id"]]), "hallazgo"), escape(", ".join(quejas[fila["id"]])))
            if quejas.get(fila["id"]) else "—"))
    return tarjeta("Competidores y sustitutos", '<p class="nota">★ = con tracción. Las descargas son acumuladas desde '
                   'el lanzamiento: sirven de contexto, no miden la demanda de hoy.</p><div class="tabla"><table>'
                   '<thead><tr><th>Nombre</th><th>Qué es</th><th>Descargas</th><th>Nota</th><th>Precio y modelo</th>'
                   '<th>Hallazgos que lo nombran</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(filas))


def seccion_cobertura(producto, registro):
    mapa = cobertura(producto, registro)
    if mapa is None:
        return tarjeta("Cobertura por mercado, idioma y tienda", '<p class="vacio">Sin objetivo de mercados, idiomas y '
                                                                 'tiendas registrado: no se sabe qué quedó sin '
                                                                 'investigar.</p>')
    objetivo = objetivo_de(producto)
    filas, huecos, vacios = [], 0, 0
    for linea, datos in mapa.items():
        celdas = []
        for dimension, valor, estado, detalle in datos:
            if estado == "fuentes":
                celdas.append(chip("%s ✔" % valor, "bien"))
            elif estado == "vacio":
                vacios += 1
                celdas.append('<span title="%s">%s</span>' % (escape(MOTIVOS_VACIO[detalle["motivo"]] + ": "
                                                                     + detalle["texto"], quote=True),
                                                              chip("%s ⚠ %s" % (valor, MOTIVOS_VACIO[detalle["motivo"]]),
                                                                   "aviso")))
            else:
                huecos += 1
                celdas.append(chip("%s ✖ sin fuentes" % valor, "mal"))
        filas.append("<tr><td>%s</td><td>%s</td></tr>" % (escape(LINEAS_LLANO[linea]), " ".join(celdas)
                                                          or '<span class="nota">nada que cubrir</span>'))
    return tarjeta("Cobertura por mercado, idioma y tienda", '<p class="nota">Objetivo: mercados %s · idiomas %s · '
                   'tiendas %s. %s sin explicar y %s con su motivo. Un vacío por límite de las '
                   'herramientas no es falta de evidencia.</p><div class="tabla"><table><thead><tr><th>Línea</th>'
                   '<th>Cobertura</th></tr></thead><tbody>%s</tbody></table></div>' % (
                       escape(", ".join(objetivo["mercados"]) or "—"), escape(", ".join(objetivo["idiomas"]) or "—"),
                       escape(", ".join(objetivo["tiendas"]) or "ninguna"), plural(huecos, "hueco"),
                       plural(vacios, "vacío"), "".join(filas)))


def seccion_escenarios(producto):
    escenarios = producto.get("escenarios")
    if not escenarios:
        return tarjeta("Escenarios de ingresos (solo referencia)", '<p class="vacio">Sin escenarios: los calcula la '
                                                                   'sesión 2 (estrategia).</p>')
    moneda = escenarios.get("moneda", "USD")
    meta = float(producto["criterios"].get("meta_ingresos_mes") or 0)
    casos = [("Pesimista", escenarios["pesimista"]), ("Base", escenarios["base"]), ("Optimista", escenarios["optimista"])]
    maximo = max([v for _, v in casos] + [meta]) * 1.08 or 1
    alto_fila, izquierda, ancho = 34, 90, 600
    barras = []
    for indice, (nombre, valor) in enumerate(casos):
        y = 10 + indice * alto_fila
        largo = (ancho - izquierda - 110) * valor / maximo
        barras.append('<g><title>%s: %s %s al mes</title><text x="0" y="%d" class="t2">%s</text>'
                      '<rect x="%d" y="%d" width="%.1f" height="16" rx="4" fill="var(--serie)"/>'
                      '<text x="%.1f" y="%d">%s %s</text></g>' % (
                          nombre, numero(valor), moneda, y + 13, nombre, izquierda, y, max(largo, 1),
                          izquierda + max(largo, 1) + 6, y + 13, escape(numero(valor)), escape(moneda)))
    alto = 10 + len(casos) * alto_fila
    if meta:
        x = izquierda + (ancho - izquierda - 110) * meta / maximo
        barras.append('<line x1="%.1f" x2="%.1f" y1="2" y2="%d" stroke="var(--texto-2)" stroke-dasharray="4 3"/>'
                      '<text x="%.1f" y="%d" class="t2">meta (referencia)</text>' % (x, x, alto, x + 4, alto + 14))
        alto += 20
    grafico = '<div class="grafico"><svg viewBox="0 0 %d %d" role="img" aria-label="Ingresos netos al mes por ' \
              'escenario">%s</svg></div>' % (ancho, alto, "".join(barras))
    texto = ('<p class="nota">Ingresos netos al mes. Son una referencia calculada con supuestos, no una promesa%s.</p>'
             % (": " + ", ".join(escenarios.get("rotulos") or []) if escenarios.get("rotulos") else ""))
    if meta:
        texto += "<p>Meta de ingresos (%s): %s %s al mes%s.</p>" % (
            "obligatoria" if meta_obligatoria(producto) else "referencial, no decide ninguna puerta", numero(meta),
            escape(producto["criterios"]["moneda"]), "; para llegar harían falta unos %s usuarios activos por día" %
            numero(escenarios["dau_meta"]) if escenarios.get("dau_meta") else "")
    modelos = escenarios.get("modelos")
    if modelos is None:
        texto += '<p class="nota">Calculados con una versión anterior: sin el detalle por modelo de monetización.</p>'
    else:
        texto += "<details><summary>Modelos de monetización (%d)</summary><ul>%s</ul></details>" % (
            len(modelos), "".join("<li>%s %s · %s %s al mes en el caso base%s</li>" % (
                "✔" if m["viable"] else "✖", escape(m["nombre"]), escape(numero(m["base"])), escape(moneda),
                "" if m["viable"] else " · " + escape(motivo_modelo(m))) for m in modelos))
    return tarjeta("Escenarios de ingresos (solo referencia)", texto + grafico)


def seccion_hipotesis(carpeta, registro):
    filas = hipotesis(carpeta, registro)
    if not filas:
        return tarjeta("Hipótesis más riesgosa", '<p class="vacio">Sin validación documental todavía (sesión 3).</p>')
    riesgosas = [f for f in filas if f["riesgosa"]]
    tono = {"sostenida": "bien", "débil": "aviso", "refutada": "mal"}
    cuerpo = ""
    if riesgosas:
        fila = riesgosas[0]
        cuerpo += "<p><b>%s</b>%s</p><p>%s %s</p>" % (
            escape(fila["texto"]), ref(fila["id"]), chip(fila["veredicto"] or "sin veredicto",
                                                         tono.get(fila["veredicto"], "neutro")),
            escape("Se mide después del lanzamiento con: %s" % fila["metrica"] if fila["metrica"] else
                   "Sin métrica ni umbral definidos."))
    else:
        cuerpo += '<p class="vacio">Ninguna hipótesis marcada como la más riesgosa.</p>'
    cuerpo += "<details><summary>Todas las hipótesis (%d)</summary><ul>%s</ul></details>" % (len(filas), "".join(
        "<li>%s %s%s</li>" % (chip(f["veredicto"] or "sin veredicto", tono.get(f["veredicto"], "neutro")),
                              escape(f["texto"]), ref(f["id"])) for f in filas))
    return tarjeta("Hipótesis más riesgosa", '<p class="nota">La que el primer producto tiene que poner a prueba '
                                             'antes que nada.</p>' + cuerpo)


def seccion_costo(producto):
    consumo = producto.get("consumo") or []
    if not consumo:
        return tarjeta("Costo", '<p class="vacio">Sin consumo anotado: es opcional, y se anota con el comando consumo.</p>')
    filas = "".join("<tr><td>%s</td><td>%s</td></tr>" % (escape(f["sesion"]), escape(texto_consumo(f)))
                    for f in consumo)
    return tarjeta("Costo", "<p><b>Total anotado:</b> %s%s</p><div class=\"tabla\"><table><thead><tr><th>Sesión"
                            "</th><th>Consumo</th></tr></thead><tbody>%s</tbody></table></div>" % (
                                escape(texto_total(consumo)),
                                escape(" (sin anotar: %s)" % ", ".join(sin_consumo(producto))
                                       if sin_consumo(producto) else ""), filas))


GLOSARIO = (
    ("Puerta", "Un punto de control donde decides seguir, ajustar una parte o descartar la idea."),
    ("Veredicto", "Lo que concluye la skill en cada puerta, con reglas fijas: No viable (recomienda descartar), Viable "
                  "con reservas (recomienda ajustar una parte) o Viable (recomienda seguir). La decisión es tuya; si "
                  "decides en contra, queda anotado con tu motivo."),
    ("Hallazgo clave", "Una afirmación con fuentes de la que dependen el puntaje o una puerta."),
    ("Confirmado", "Tiene 3 fuentes independientes publicadas en los últimos 18 meses (con un dato medido si es de "
                   "demanda o de ingresos); en políticas basta el texto oficial."),
    ("Confianza", "Qué tan sólida es la evidencia: alta, media, baja o sin evidencia. La calcula el script."),
    ("Sustituto", "Cómo se resuelve hoy la necesidad sin una app así: una función del sistema, una hoja de cálculo, "
                  "un grupo de chat."),
    ("Dato acumulado", "Descargas o valoraciones desde el lanzamiento: contexto, no la demanda de hoy."),
    ("Vacío", "Un mercado, idioma o tienda sin fuentes, con su motivo (límite de las herramientas, sin resultados o "
              "sin presupuesto)."),
    ("Referencias", "Los códigos como H-DEM-1 (hallazgo), S-COM-2 (fuente), D-1 (diferenciador) o C-3 (competidor) "
                    "son los identificadores del registro de la idea."),
)


def html_reporte(carpeta, producto, registro):
    estado = estado_idea(carpeta, producto)
    tipo = tipo_de(producto)
    cabecera = '<h1>%s</h1><p class="sub">%s Creada el %s · reporte generado el %s.</p>' % (
        escape(producto["nombre"]), escape(TIPOS_LLANO.get(tipo, "Tipo de idea sin registrar todavía.")),
        escape(producto.get("creado", "")), escape(fecha_corta(ahora())))
    info = veredicto_de_idea(carpeta, producto, registro)
    secciones = [
        cabecera, seccion_veredicto(info), seccion_resumen(carpeta, producto, registro, estado, info),
        seccion_puntaje(producto, registro),
        seccion_puertas(carpeta, producto, registro), seccion_diferenciadores(producto, registro),
        seccion_hallazgos(registro), seccion_competidores(registro), seccion_cobertura(producto, registro),
        seccion_escenarios(producto), seccion_hipotesis(carpeta, registro), seccion_costo(producto),
        tarjeta("Glosario", "<details><summary>Qué significa cada término</summary><ul>%s</ul></details>" % "".join(
            "<li><b>%s:</b> %s</li>" % (escape(t), escape(d)) for t, d in GLOSARIO)),
        "<footer>Generado por hb-product %s con los datos de esta carpeta. La confianza se calcula con la fecha del "
        "reporte. Se regenera solo al decidir cada puerta y al archivar; a mano, con <code>producto.py reporte</code>."
        "</footer>" % VERSION,
    ]
    return pagina("%s · reporte" % producto["nombre"], "\n".join(secciones))


def escribir_reporte(carpeta):
    """Genera <carpeta>/reporte.html con lo que hay en el disco y devuelve su ruta."""
    producto = cargar(carpeta)
    ruta = carpeta / REPORTE
    escribir(ruta, html_reporte(carpeta, producto, Registro(carpeta, producto["criterios"])))
    return ruta


def regenerar_reporte(carpeta):
    """Regenera el reporte después de una decisión o de archivar; si falla, lo dice sin deshacer nada."""
    try:
        print("· Reporte actualizado: %s" % escribir_reporte(carpeta))
    except Exception as error:  # el reporte nunca deshace una decisión ya registrada
        print("⚠ No se pudo regenerar el reporte (%s: %s). La decisión quedó registrada; `reporte` lo reintenta." % (
            type(error).__name__, error))


def carpeta_de_idea(args):
    """La carpeta de la idea del reporte: la activa o, con --idea, una archivada."""
    carpeta = resolver_carpeta(args)
    if args.idea:
        elegida = next((ruta for ruta in ideas_archivadas(carpeta) if ruta.name == args.idea), None)
        if not elegida:
            raise Fallo("No existe la idea archivada '%s'. Las que hay: %s" % (args.idea, ", ".join(
                ruta.name for ruta in ideas_archivadas(carpeta)) or "ninguna"))
        return elegida
    if not (carpeta / "producto.json").exists():
        archivadas = ideas_archivadas(carpeta)
        if len(archivadas) == 1:
            return archivadas[0]
        if archivadas:
            raise Fallo("No hay ninguna idea activa en %s. Elige una archivada con --idea: %s" % (
                carpeta, ", ".join(ruta.name for ruta in archivadas)))
    return carpeta


def cmd_reporte(args):
    carpeta = carpeta_de_idea(args)
    ruta = escribir_reporte(carpeta)
    print("✔ Reporte de \"%s\": %s" % (cargar(carpeta)["nombre"], ruta))
    print("Siguiente paso: ábrelo en el navegador (un solo archivo, sin red). Se regenera solo al decidir cada puerta "
          "y al archivar.")


SALTAR_CARPETAS = ("node_modules", "__pycache__", "build", "dist", "venv", "Pods", "DerivedData")


def buscar_ideas(raiz, profundidad=6):
    """Las carpetas con un producto.json de hb-product bajo la raíz (en curso y archivadas), sin seguir enlaces."""
    encontradas = []
    base = len(raiz.parts)
    for actual, carpetas, archivos in os.walk(str(raiz)):
        ruta = Path(actual)
        carpetas[:] = sorted(c for c in carpetas if not c.startswith(".") and c not in SALTAR_CARPETAS
                             and len(ruta.parts) - base < profundidad)
        if "producto.json" in archivos:
            try:
                datos = leer_json(ruta / "producto.json", {})
            except Fallo:  # JSON roto: va al tablero como "no se pudo leer"
                encontradas.append(ruta)
                continue
            if isinstance(datos, dict) and {"nombre", "sesiones", "criterios"} <= set(datos):
                encontradas.append(ruta)
    return encontradas


def html_tablero(raiz, filas, fallidas):
    conteo = {clave: sum(1 for f in filas if f["estado"]["clave"] == clave) for clave in ORDEN_ESTADOS}
    tonos = TONO_ESTADO
    cifras = '<div class="cifras">%s</div><p class="nota">%s</p>' % ("".join(
        '<div class="cifra"><b>%d</b><span>%s</span></div>' % (conteo[c], escape(ESTADOS_IDEA[c][0].lower()))
        for c in ORDEN_ESTADOS), escape(EXPLICACION_ESTADOS))
    renglones = []
    for fila in filas:
        estado, puntaje = fila["estado"], fila["puntaje"]
        ultima = estado["ultima"]
        renglones.append(
            '<li><div class="fila"><h3><a href="%s">%s</a></h3>%s<span class="nota">%s</span></div>'
            '<div class="dato"><div><b>Puntaje:</b> %s<br><span class="nota">mínimo de la puerta 1: %d</span></div>'
            '%s<div class="nota"><b>Última puerta:</b> %s</div></div>%s<p><b>%s</b> %s</p></li>' % (
                escape(fila["enlace"], quote=True), escape(fila["nombre"]),
                chip(estado["etiqueta"], tonos[estado["clave"]], estado["icono"]),
                escape("idea %s" % fila["tipo"] if fila["tipo"] else "tipo sin registrar"),
                "%d/25" % puntaje if puntaje is not None else "sin puntaje", fila["minimo"],
                barra(puntaje, 25, "%s: %d de 25" % (fila["nombre"], puntaje), marca=fila["minimo"])
                if puntaje is not None else "<span></span>",
                escape("puerta %d · %s · %s" % (ultima["puerta"], DECISIONES_LLANO[ultima["decision"]].lower(),
                                                 fecha_corta(ultima["fecha"])[:10]) if ultima else "ninguna"),
                seccion_veredicto(fila["veredicto"], compacto=True),
                "Motivo:" if estado["archivo"] or estado["clave"] == "lista" else "Siguiente paso:",
                escape(fila["motivo"])))
    tabla_html = ('<ul class="lista">%s</ul>' % "".join(renglones)) if filas else \
        '<p class="vacio">No se encontró ninguna idea.</p>'
    aviso = ""
    if fallidas:
        aviso = tarjeta("No se pudieron leer", "<ul>%s</ul>" % "".join(
            "<li>%s: %s</li>" % (escape(ruta), escape(motivo)) for ruta, motivo in fallidas))
    cuerpo = ('<h1>Tablero de ideas</h1><p class="sub">%s bajo esta carpeta · generado el %s. Cada nombre '
              'abre su reporte.</p>%s%s<footer>Generado por hb-product %s. Se regenera con <code>producto.py tablero '
              '--raiz &lt;carpeta&gt;</code>; la barra marca el mínimo de la puerta 1. El veredicto de cada idea lo '
              'calcula la skill con reglas fijas; la decisión es tuya.</footer>' % (
                  plural(len(filas), "idea"), escape(fecha_corta(ahora())), tarjeta("Resumen", cifras, "resumen"),
                  tarjeta("Ideas", tabla_html) + aviso, VERSION))
    return pagina("Tablero de ideas", cuerpo)


def cmd_tablero(args):
    raiz = Path(os.path.abspath(os.path.expanduser(args.raiz)))
    if not raiz.is_dir():
        raise Fallo("No existe la carpeta %s" % raiz)
    filas, fallidas = [], []
    for carpeta in buscar_ideas(raiz):
        try:
            producto = cargar(carpeta)
            registro = Registro(carpeta, producto["criterios"])
            ruta = carpeta / REPORTE
            escribir(ruta, html_reporte(carpeta, producto, registro))
            info = veredicto_de_idea(carpeta, producto, registro)
        except (Fallo, KeyError, TypeError, ValueError) as error:
            fallidas.append((str(carpeta), "%s" % error))
            continue
        estado = estado_idea(carpeta, producto)
        nueva = tipo_de(producto) == "nueva"
        puntaje = producto.get("puntaje")
        filas.append({
            "nombre": producto["nombre"], "tipo": tipo_de(producto) or "", "estado": estado,
            "puntaje": puntaje["total"] if puntaje else None,
            "minimo": int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"]),
            "motivo": estado["motivo"] or paso_corto(carpeta, producto, registro),
            "veredicto": info,
            "enlace": Path(os.path.relpath(str(ruta), str(raiz))).as_posix(),
            "fecha": max([producto.get("creado", "")] + [d.get("fecha", "") for d in decisiones(carpeta)]
                         + [(estado["archivo"] or {}).get("fecha", "")]),
        })
    filas.sort(key=lambda f: f["fecha"], reverse=True)
    filas.sort(key=lambda f: ORDEN_ESTADOS.index(f["estado"]["clave"]))
    destino = raiz / TABLERO
    escribir(destino, html_tablero(raiz, filas, fallidas))
    print("✔ Tablero con %s: %s" % (plural(len(filas), "idea"), destino))
    for fila in filas:
        info = fila["veredicto"]
        print("  · %s · %s%s · %s" % (fila["nombre"], fila["estado"]["etiqueta"], " · %s %s (puerta %d), recomienda %s"
                                      % (VEREDICTOS[info["resultado"]["nivel"]]["marca"], info["resultado"]["titulo"],
                                         info["resultado"]["puerta"], texto_recomendacion(info["resultado"]))
                                      if info else "", fila["enlace"]))
    for ruta, motivo in fallidas:
        print("⚠ No se pudo leer %s: %s" % (ruta, motivo))
    print("Siguiente paso: abre %s en el navegador; cada nombre lleva a su reporte (regenerado ahora)." % destino)


# ---------------------------------------------------------------------------------------------------------------
# Línea de comandos

SOLO_LECTURA = ("tipo", "matriz", "triangulacion", "validacion", "trazabilidad", "puerta", "cobertura", "resenas")
# reporte y tablero solo escriben su HTML, de forma atómica: no necesitan el candado de la carpeta
SIN_CANDADO = ("nuevo", "siguiente", "estado", "reabrir", "reporte", "tablero")


def agregar_objetivo(sub):
    sub.add_argument("--mercados", help="países o regiones del lanzamiento: MX,ES,BR")
    sub.add_argument("--idiomas", help="idiomas del lanzamiento: es,pt")
    sub.add_argument("--tiendas", help="google-play,app-store, o ninguna")


def parser():
    principal = argparse.ArgumentParser(prog="producto.py", description="Herramienta de hb-product %s" % VERSION)
    comandos = principal.add_subparsers(dest="comando", metavar="<comando>")
    comandos.required = True

    def comando(nombre, funcion, ayuda):
        sub = comandos.add_parser(nombre, help=ayuda, description=ayuda)
        sub.add_argument("--carpeta", help="carpeta del producto (por defecto, la de AGENTS.md o ./%s)"
                         % CARPETA_DEFECTO)
        sub.set_defaults(funcion=funcion)
        return sub

    sub = comando("nuevo", cmd_nuevo, "Crea la estructura desde las plantillas y escribe estado.md")
    sub.add_argument("--nombre", required=True)
    sub.add_argument("--meta", help="meta de ingresos netos al mes")
    sub.add_argument("--moneda", help="moneda de la meta (por defecto USD)")
    sub.add_argument("--semanas", help="presupuesto de semanas para el MVP")
    sub.add_argument("--meta-obligatoria", dest="meta_obligatoria", action="store_true",
                     help="la meta pasa a ser criterio de la puerta 2 (por defecto es solo una referencia)")
    agregar_objetivo(sub)

    sub = comando("criterio", cmd_criterio, "Muestra los criterios o cambia uno (después de la sesión 0, con motivo)")
    sub.add_argument("--clave")
    sub.add_argument("--valor")
    sub.add_argument("--motivo")

    sub = comando("tipo", cmd_tipo, "Muestra el tipo de idea o lo registra (lo hace la sesión 1a)")
    grupo = sub.add_mutually_exclusive_group()
    for tipo in TIPOS_IDEA:
        grupo.add_argument("--" + tipo, action="store_true")
    sub.add_argument("--motivo")

    sub = comando("fuente", cmd_fuente, "Registra una fuente y devuelve su ID (S-…)")
    sub.add_argument("--linea", required=True, help=", ".join(LINEAS))
    sub.add_argument("--url", help="la página pública")
    sub.add_argument("--archivo", help="un CSV de reseñas exportado por el usuario, en vez de --url")
    sub.add_argument("--publicada", required=True,
                     help="la fecha real de publicación (AAAA-MM-DD o AAAA-MM), desconocida o, con --archivo, auto")
    sub.add_argument("--consultada", help="AAAA-MM-DD (por defecto, hoy)")
    sub.add_argument("--tipo", required=True, choices=TIPOS_FUENTE,
                     help="oficial: el texto de una política de tienda o de una ley (con --version o --publicada)")
    sub.add_argument("--version", help="versión o fecha de la norma, para --tipo oficial")
    sub.add_argument("--acumulado", action="store_true",
                     help="dato medido acumulado (descargas o valoraciones desde el lanzamiento): contexto, no señal "
                          "actual de demanda")
    sub.add_argument("--peldano", required=True, type=int, choices=sorted(PELDANOS))
    sub.add_argument("--resumen", required=True, help="3 líneas como máximo")
    sub.add_argument("--autor", help="la app, la empresa o el medio que publica; nunca un nombre de usuario")
    sub.add_argument("--mercados", help="mercados del objetivo que cubre esta fuente (MX,ES)")
    sub.add_argument("--idiomas", help="idiomas del objetivo que cubre (es,pt)")
    sub.add_argument("--tiendas", help="tiendas del objetivo que cubre (google-play,app-store)")

    sub = comando("hallazgo", cmd_hallazgo, "Registra un hallazgo (H-…) y calcula su confianza")
    sub.add_argument("--linea", required=True, help=", ".join(LINEAS))
    sub.add_argument("--texto", required=True)
    sub.add_argument("--fuentes", required=True, help="S-…,S-…")
    sub.add_argument("--en-contra", dest="en_contra", help="fuentes con evidencia en contra")
    sub.add_argument("--sin-contra", dest="sin_contra", help="qué se buscó en contra cuando no apareció nada")
    sub.add_argument("--critico", action="store_true", help="hallazgo clave: sostiene el puntaje o una puerta")
    sub.add_argument("--competidores", help="competidores a los que se refiere, por ID (C-…) o por nombre")
    sub.add_argument("--bloquea", help="línea politicas: tiendas del objetivo que nombran la categoría o la rechazan "
                                       "(google-play,app-store)")

    sub = comando("confianza", cmd_confianza, "Baja la confianza de un hallazgo, con su motivo (nunca la sube)")
    sub.add_argument("--hallazgo", required=True)
    sub.add_argument("--bajar", required=True, choices=("baja", "media"))
    sub.add_argument("--motivo", required=True)

    sub = comando("competidor", cmd_competidor, "Registra o completa una fila de la matriz de competidores (C-…)")
    sub.add_argument("--nombre", required=True)
    sub.add_argument("--peldano", required=True, type=int, choices=(1, 2, 3, 4),
                     help="1 directo, 2 variante, 3 análogo, 4 sustituto")
    sub.add_argument("--fuentes", required=True, help="S-…,S-…")
    sub.add_argument("--descargas", help="número, 100k o 1M")
    sub.add_argument("--nota")
    sub.add_argument("--actualizada", help="fecha de la última actualización (AAAA-MM)")
    sub.add_argument("--precio")
    sub.add_argument("--modelo", help="gratis, anuncios, compra única, suscripción…")
    sub.add_argument("--anuncios", choices=("ninguno", "pocos", "muchos"))
    sub.add_argument("--tamano-mb", dest="tamano_mb")
    sub.add_argument("--idiomas", help="es,en")
    sub.add_argument("--permisos", help="ubicacion,camara o ninguno")
    sub.add_argument("--sin-conexion", dest="sin_conexion", choices=("si", "no", "parcial"))
    sub.add_argument("--accesibilidad")
    sub.add_argument("--plataformas", help="android,ios,web")
    sub.add_argument("--funciones", help="funcionalidades clave, separadas por ;")
    sub.add_argument("--traccion", help="evidencia de tracción cuando no hay descargas (ingresos, usuarios)")
    sub.add_argument("--sustituto", choices=sorted(SUSTITUTOS),
                     help="con --peldano 4: nativo (viene con el sistema), gratuito o pago")
    sub.add_argument("--resuelve", choices=sorted(RESUELVE),
                     help="con --peldano 4: si el sustituto ya resuelve la necesidad (si, parcial o no)")

    comando("matriz", cmd_matriz, "Muestra la matriz de competidores con los hallazgos enlazados a cada uno")

    sub = comando("intento", cmd_intento, "Registra la búsqueda de intentos anteriores de la misma idea")
    sub.add_argument("--resultado", required=True, choices=("sin-rastro", "fracaso-demanda", "fracaso-otra-causa"))
    sub.add_argument("--texto", required=True, help="qué se buscó y qué apareció")
    sub.add_argument("--fuentes", help="S-…,S-…")

    sub = comando("objetivo", cmd_objetivo, "Muestra o registra los mercados, idiomas y tiendas de la idea (sesión 0)")
    agregar_objetivo(sub)
    sub.add_argument("--motivo", help="obligatorio después de cerrar la sesión 0")

    sub = comando("vacio", cmd_vacio, "Registra un mercado, idioma o tienda del objetivo que quedó sin fuentes")
    sub.add_argument("--linea", required=True, help=", ".join(COBERTURA_LINEAS))
    sub.add_argument("--mercado")
    sub.add_argument("--idioma")
    sub.add_argument("--tienda")
    sub.add_argument("--motivo", required=True, choices=sorted(MOTIVOS_VACIO),
                     help="herramienta (página dinámica o bloqueada), sin-resultados o presupuesto")
    sub.add_argument("--texto", required=True, help="qué se intentó y qué pasó")

    sub = comando("cobertura", cmd_cobertura, "Lista por línea los mercados, idiomas y tiendas sin fuentes")
    sub.add_argument("--linea", help=", ".join(COBERTURA_LINEAS))

    sub = comando("resenas", cmd_resenas, "Muestra las reseñas de un CSV exportado, sin columnas de autor")
    sub.add_argument("--archivo", required=True)
    sub.add_argument("--estrellas", default="1-3", help="número o rango (por defecto 1-3)")
    sub.add_argument("--idioma")
    sub.add_argument("--desde", help="AAAA-MM-DD")
    sub.add_argument("--limite", type=int, default=30)

    sub = comando("diferenciador", cmd_diferenciador, "Registra un diferenciador (D-…) y dice si es viable")
    sub.add_argument("--vector", required=True, choices=VECTORES)
    sub.add_argument("--texto", required=True)
    sub.add_argument("--hallazgos", required=True, help="H-…,H-…")
    sub.add_argument("--se-ve", dest="se_ve", required=True, choices=("ficha", "uso"))
    sub.add_argument("--copiable", required=True, choices=("baja", "media", "alta"))
    sub.add_argument("--motivo", required=True, help="por qué es difícil o fácil de copiar")
    sub.add_argument("--semanas", required=True, help="semanas estimadas para construirlo")
    sub.add_argument("--principal", action="store_true")

    sub = comando("principal", cmd_principal, "Elige el diferenciador principal (con la sesión 1g abierta)")
    sub.add_argument("--id", required=True)

    sub = comando("propuesta", cmd_propuesta, "Deja un cambio a una sesión cerrada como propuesta para la puerta")
    sub.add_argument("--texto", required=True, help="qué cambiar y por qué")
    sub.add_argument("--ajustar", help="la sesión que habría que reabrir para aplicarla (por ejemplo, 1g)")
    sub.add_argument("--sesion", help="la sesión que la propone (por defecto, la abierta)")

    sub = comando("anular", cmd_anular, "Anula una fuente, un hallazgo, un competidor o un diferenciador")
    sub.add_argument("--id", required=True)
    sub.add_argument("--motivo", required=True)

    comando("triangulacion", cmd_triangulacion, "Lista los hallazgos clave y lo que les falta para triangular")

    sub = comando("puntaje", cmd_puntaje, "Total, confianza global y comparación con la puerta 1")
    sub.add_argument("--valores", required=True, help="demanda,monetización,facilidad,riesgo,diferenciación (1 a 5)")
    sub.add_argument("--mitigacion", help="mitigación escrita, si el riesgo de políticas es 1")

    sub = comando("escenarios", cmd_escenarios, "Casos pesimista, base y optimista, y usuarios para la meta")
    sub.add_argument("--entrada", required=True, help="JSON de supuestos (plantilla: escenarios.json)")

    comando("validacion", cmd_validacion, "Revisa la tabla de hipótesis de 03-validacion.md")
    comando("trazabilidad", cmd_trazabilidad, "Revisa la tabla de funcionalidades de 04-prd.md y calcula el RICE")

    sub = comando("cerrar", cmd_cerrar, "Cierra una sesión si su entregable está completo")
    sub.add_argument("--sesion", required=True, help=", ".join(SESION))

    sub = comando("puerta", cmd_puerta, "Veredicto de una puerta, criterio por criterio")
    sub.add_argument("--n", required=True, type=int, choices=(1, 2, 3))

    sub = comando("decidir", cmd_decidir, "Registra la decisión de una puerta. Solo lo corre el usuario")
    sub.add_argument("--puerta", required=True, type=int, choices=(1, 2, 3))
    grupo = sub.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--seguir", action="store_true")
    grupo.add_argument("--ajustar", metavar="SESIÓN")
    grupo.add_argument("--descartar", metavar="MOTIVO")
    grupo.add_argument("--reabrir", action="store_true", help="deshace la decisión vigente de la puerta")
    sub.add_argument("--motivo", help="por qué decides distinto de la recomendación de la skill (obligatorio en ese "
                                      "caso; queda registrado)")

    sub = comando("modelos", cmd_modelos, "Muestra o cambia el modelo de cada nivel y la herramienta que abre los chats")
    for nivel in MODELOS:
        sub.add_argument("--" + nivel, help="nombre del modelo (por defecto %s)" % MODELOS[nivel])
    sub.add_argument("--herramienta", choices=("claude", "copilot", "otra", "ninguna"))
    sub.add_argument("--comando", help="comando propio con {modelo} y, si se puede, {esfuerzo}")

    sub = comando("consumo", cmd_consumo, "Anota el costo de una sesión o del orquestador (opcional)")
    sub.add_argument("--sesion", help="%s u orquestador" % ", ".join(SESION))
    sub.add_argument("--costo", help="USD, entre comillas simples: '0.40'")
    sub.add_argument("--creditos", help="AI Credits de GitHub Copilot (/usage)")
    sub.add_argument("--tokens", help="tokens totales, como 45k")
    sub.add_argument("--pasos")
    sub.add_argument("--modelo")
    sub.add_argument("--incluye", help="sesiones que cubre una fila del orquestador: 1a,1b,…")

    comando("siguiente", cmd_siguiente, "El paso siguiente o los carriles paralelos, con el texto para cada chat")
    comando("estado", cmd_estado, "Resumen de la idea y el paso siguiente")

    sub = comando("reporte", cmd_reporte, "Genera reporte.html de la idea (un solo archivo, sin red)")
    sub.add_argument("--idea", help="una idea archivada: la carpeta dentro de archivo/")

    sub = comando("tablero", cmd_tablero, "Genera index.html con todas las ideas que encuentre bajo una carpeta")
    sub.add_argument("--raiz", required=True, help="la carpeta donde buscar las ideas (en curso y archivadas)")

    sub = comando("archivar", cmd_archivar, "Mueve la idea activa a archivo/ (no borra nada)")
    sub.add_argument("--motivo", required=True)

    sub = comando("reabrir", cmd_reabrir, "Recupera una idea archivada")
    sub.add_argument("--idea", help="la carpeta dentro de archivo/")
    return principal


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.comando in SOLO_LECTURA + SIN_CANDADO and not (
                args.comando == "tipo" and any(getattr(args, t) for t in TIPOS_IDEA)):
            args.funcion(args)
        else:
            carpeta = resolver_carpeta(args)
            cargar(carpeta)  # sin idea activa, falla antes de crear nada
            with bloqueo(carpeta):
                args.funcion(args)
    except Fallo as fallo:
        print("✖ %s" % fallo, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
