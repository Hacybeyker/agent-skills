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
# Vigencia por tipo de fuente (feedback #31): la estadística oficial (censos, encuestas nacionales) rige hasta que sale una
# edición más nueva, con un máximo de `vigencia_larga_meses`; un estudio académico, ese mismo máximo; todo lo demás
# (reseñas, tiendas, prensa, tráfico, precios), `vigencia_meses`. Un hallazgo clave necesita, además, una fuente reciente.
CLASES_VIGENCIA = {"estadistica": "estadística oficial", "academica": "estudio académico"}
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
    "vigencia_larga_meses": 60,    # estadística oficial y estudios académicos (`fuente --clase`)
    "fuentes_minimas": 3,          # fuentes independientes de un hallazgo clave
    "analogos_minimos": 2,         # análogos con tracción (peldaño 2 o 3) de una idea nueva
    "traccion_descargas": 100000,  # descargas desde las que un competidor o un análogo tiene tracción (o `--respaldo`)
    "traccion_valoraciones": 2000,  # sin descargas publicadas (App Store): valoraciones desde las que se estima tracción
    "meta_ingresos_mes": 0,        # meta de ingresos netos al mes (opcional; 0 = sin meta)
    "meta_obligatoria": "no",      # "si": la meta es criterio de la puerta 2; "no": solo referencia
    "moneda": "USD",
    "presupuesto_semanas": 0,      # semanas para construir el MVP (sesión 0)
    "dias_descarte": 60,           # Viable para probar: días después del lanzamiento para el criterio de descarte
}
PRESUPUESTO = {"busquedas": 15, "lecturas": 10}
PRESUPUESTO_NUEVA = {"busquedas": 20, "lecturas": 12}
REAPERTURA = 0.5  # cada reapertura de una línea tiene su propio presupuesto: la mitad del original (feedback #34)
AMPLITUD_ANALOGIA = 0.5  # un escenario por analogía abre el rango: pesimista × 0,5 y optimista × 1,5
RICE_CONFIANZA = {3: 100, 2: 80, 1: 50, 0: 0}  # confianza del hallazgo → porcentaje de RICE
# Compras de los escenarios: un pago único se cobra una vez, a las instalaciones nuevas del mes; una suscripción se
# cobra cada mes a la base de pagadores (los usuarios del mes que pagan). Los anuncios van sobre los usuarios activos.
TIPOS_COMPRA = {"pago-unico": "Pago único", "suscripcion": "Suscripción"}
PERIODOS = {"mes": 1, "anio": 12}  # precio de una suscripción → meses que cubre
CALCULO_ESCENARIOS = 2  # 2: el pago único sobre las instalaciones nuevas del mes (antes, sobre los usuarios del mes)

# Modelo y esfuerzo de cada nivel (references/modelos.md). Los nombres se cambian con `modelos`.
MODELOS = {"intermedio": "Sonnet 5.5", "alto": "Opus 5.5", "economico": "Haiku 5.5"}
ESFUERZO = {"intermedio": "medio", "alto": "alto", "economico": "bajo"}  # económico: el chat orquestador
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
INVESTIGACION = ("1a", "1b", "1c", "1d", "1e", "1g")  # las líneas de investigación, con su presupuesto
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
# Tipo de idea (feedback #28): qué peldaños muestran que una línea ya trabajó por analogía (idea nueva) o con
# competencia (existente o variante). Una línea que cerró con otro tipo y sin fuentes de esos peldaños queda "a revisar
# por cambio de tipo".
PELDANOS_POR_TIPO = {"1b": (4, 5), "1c": (4, 5), "1d": (2, 3), "1g": (3, 4)}
PELDANOS_CON_COMPETENCIA = (1, 2)

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


def instante():
    """La fecha y la hora con microsegundos: ordena lo que pasa en el mismo minuto (el rival y los sustitutos)."""
    return "%sT%s" % (hoy().isoformat(), datetime.now().strftime("%H:%M:%S.%f"))


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
        pista = (" Hay %s en archivo/: `reabrir` recupera una." % plural(len(archivadas), "idea")) if archivadas \
            else ""
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
    datos["vacios"] = []  # cualquier línea puede registrar un vacío de cobertura (`vacio`)
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
        # la sesión 1a dijo que no hay una alternativa gratis que resuelva la necesidad (`competidor --sin-rival`)
        self.sin_rival = self.lineas["competencia"].get("sin_rival")
        for linea, datos in self.lineas.items():
            for campo, destino in (("fuentes", self.fuentes), ("hallazgos", self.hallazgos),
                                   ("matriz", self.competidores), ("diferenciadores", self.diferenciadores),
                                   ("vacios", self.vacios)):
                for item in datos.get(campo, []):
                    if not item.get("anulado"):
                        destino[item["id"]] = item

    @staticmethod
    def dentro(fecha, meses):
        """True si la fecha (AAAA-MM-DD) cae dentro de los últimos `meses` meses."""
        referencia = hoy()
        limite = referencia.year * 12 + referencia.month - 1 - int(meses)
        anio, mes, dia = (int(parte) for parte in fecha.split("-"))
        indice = anio * 12 + mes - 1
        return indice > limite or (indice == limite and dia >= referencia.day)

    def reemplazada(self, fuente):
        """La fuente de estadística oficial que reemplaza a esta (una edición más nueva, `fuente --reemplaza`), o None."""
        return next((f for f in self.fuentes.values() if f.get("reemplaza") == fuente["id"]), None)

    def ventana(self, fuente):
        """Los meses de vigencia de una fuente según su clase (feedback #31): 60 para la estadística oficial y los
        estudios académicos (`--clase`), 18 para todo lo demás."""
        return int(self.criterios["vigencia_larga_meses" if fuente.get("clase") in CLASES_VIGENCIA
                                  else "vigencia_meses"])

    def vigente(self, fuente):
        """La regla de vigencia, la misma para la confianza y para la triangulación: una fuente sin fecha o publicada
        fuera de su ventana no es vigente y no cuenta en ninguna de las dos. Una fuente oficial (una política, una ley)
        rige mientras no la reemplacen: cuenta la fecha en que se consultó. La estadística oficial rige hasta que sale
        una edición más nueva, con el máximo de su ventana; un estudio académico, ese mismo máximo. Una fecha con solo
        el año cuenta desde el 1 de enero (la más antigua posible)."""
        fecha = fuente.get("publicada")
        if fuente.get("tipo") == "oficial":
            fecha = fuente.get("consultada") or fecha
        if not fecha or (fuente.get("clase") == "estadistica" and self.reemplazada(fuente)):
            return False
        return self.dentro(fecha, self.ventana(fuente))

    def reciente(self, fuente):
        """Vigente y de los últimos `vigencia_meses` meses: un hallazgo clave necesita al menos una así, aunque las
        demás sean estadística oficial o estudios académicos de vigencia larga."""
        fecha = fuente.get("publicada")
        if fuente.get("tipo") == "oficial":
            fecha = fuente.get("consultada") or fecha
        return bool(fecha) and self.vigente(fuente) and self.dentro(fecha, self.criterios["vigencia_meses"])

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
            reciente = any(self.reciente(f) for grupo in grupos.values() for f in grupo)
            oficiales = [f["id"] for grupo in grupos.values() for f in grupo if f["tipo"] == "oficial"]
            por_oficial = basta_oficial and bool(oficiales)
            triangulado = (cantidad >= minimo and (medido or not exige) and reciente) or por_oficial
            if (triangulado and fuertes >= 2) or por_oficial:
                nivel = 3
            elif cantidad >= 2 and (fuertes >= 1 or cantidad >= minimo):
                nivel = 2
            else:
                nivel = 1
            nivel = min(nivel, PELDANOS[peldano][1])
            if mejor is None or (nivel, triangulado) > (mejor["nivel"], mejor["triangulado"]):
                mejor = {"nivel": nivel, "triangulado": triangulado, "peldano": peldano, "independientes": cantidad,
                         "medido": medido, "reciente": reciente, "oficial": oficiales if por_oficial else []}
        no_vigentes = [f["id"] for f in favor if not self.vigente(f)]
        acumuladas = [f["id"] for f in favor if self.vigente(f) and self.acumulada(hallazgo, f)]
        if mejor is None:
            mejor = {"nivel": 1 if favor else 0, "triangulado": False, "independientes": 0, "medido": False,
                     "reciente": False, "peldano": min([f["peldano"] for f in favor] or [6]), "oficial": []}
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
            if mejor["independientes"] and not mejor["reciente"]:
                faltan.append("falta una fuente de los últimos %s meses: las de vigencia larga (estadística oficial o "
                              "estudio académico) cuentan, pero una tiene que ser reciente" % self.criterios[
                                  "vigencia_meses"])
            if no_vigentes:
                faltan.append("%s sin fecha o fuera de su ventana de vigencia: no %s" % (
                    ", ".join(no_vigentes), "cuenta" if len(no_vigentes) == 1 else "cuentan"))
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

    def fichas(self):
        """{URL normalizada: {C-…}}: las URL de las fuentes de cada fila de la matriz (la ficha de la tienda, casi
        siempre). Una URL que es de una sola fila la identifica (feedback #39)."""
        if getattr(self, "_fichas", None) is None:
            self._fichas = {}
            for fila in self.competidores.values():
                for fuente in self.fuentes_de(fila.get("fuentes", [])):
                    if fuente.get("url"):
                        self._fichas.setdefault(url_comparable(fuente["url"]), set()).add(fila["id"])
        return self._fichas

    def competidor(self, referencia):
        """Un competidor por su ID, por la URL de su ficha (si es de una sola fila) o por su nombre exacto; None si no
        tiene fila en la matriz."""
        referencia = str(referencia).strip()
        if referencia in self.competidores:
            return self.competidores[referencia]
        if referencia.startswith(("http://", "https://")):
            filas = self.fichas().get(url_comparable(referencia), set())
            return self.competidores[next(iter(filas))] if len(filas) == 1 else None
        buscado = normal(referencia)
        for item in self.competidores.values():
            if normal(item["nombre"]) == buscado:
                return item
        return None

    def referencias(self, hallazgo):
        """Las filas de la matriz que nombra un hallazgo y las referencias que no se pudieron enlazar: ([C-…], [texto]).
        Se enlaza por ID, por la URL de la ficha o por el nombre exacto; una referencia por un nombre que no coincide
        (la app citada con otro nombre) se enlaza por la URL de la ficha si una fuente del hallazgo es la ficha de una
        sola fila que el hallazgo no nombra ya (feedback #39)."""
        ids, sueltas = [], []
        for referencia in hallazgo.get("competidores", []):
            fila = self.competidor(referencia)
            if fila:
                ids.append(fila["id"])
            else:
                sueltas.append(referencia)
        if sueltas:
            por_url = []
            for fuente in self.fuentes_de(hallazgo.get("fuentes", [])):
                filas = self.fichas().get(url_comparable(fuente.get("url") or ""), set())
                if len(filas) == 1 and next(iter(filas)) not in ids + por_url:
                    por_url.append(next(iter(filas)))
            if len(por_url) == len(sueltas):  # una ficha por cada nombre que no coincide: se enlazan por la URL
                ids += por_url
                sueltas = []
        return list(dict.fromkeys(ids)), sueltas

    def con_traccion(self, competidor):
        """Tracción (feedback #30 y #37): descargas desde `traccion_descargas`, con la fuente de la fila, un respaldo
        institucional marcado (`competidor --respaldo`) o, si la fuente da valoraciones y no descargas (en App Store es
        la única señal pública), valoraciones desde `traccion_valoraciones`: tracción estimada. La nota de `--traccion`
        es contexto y no cuenta."""
        return bool(competidor.get("respaldo")) or (competidor.get("descargas") or 0) >= int(
            self.criterios["traccion_descargas"]) or self.por_valoraciones(competidor)

    def por_valoraciones(self, competidor):
        """True si la tracción se estima por valoraciones: la fila no tiene descargas y sus valoraciones llegan al
        umbral."""
        return not competidor.get("descargas") and (competidor.get("valoraciones") or 0) >= int(
            self.criterios["traccion_valoraciones"])

    def motivo_traccion(self, competidor):
        """Por qué una fila tiene tracción o no, en pocas palabras."""
        umbral = int(self.criterios["traccion_descargas"])
        descargas = competidor.get("descargas")
        if descargas and descargas >= umbral:
            return "%s descargas" % numero(descargas)
        if competidor.get("respaldo"):
            return "respaldo institucional: %s" % competidor["respaldo"]
        valoraciones, minimo = competidor.get("valoraciones"), int(self.criterios["traccion_valoraciones"])
        if self.por_valoraciones(competidor):
            return "tracción estimada por valoraciones: %s, sin descargas publicadas (umbral %s)" % (
                numero(valoraciones), numero(minimo))
        if descargas:
            return "%s descargas, bajo el umbral de %s" % (numero(descargas), numero(umbral))
        if valoraciones:
            return "%s valoraciones, bajo el umbral de %s" % (numero(valoraciones), numero(minimo))
        return "sin descargas, valoraciones ni respaldo registrados"

    def viabilidad(self, diferenciador):
        """Los cuatro criterios de viabilidad de un diferenciador: [(cumple, texto)]."""
        hallazgos = [self.hallazgos[i] for i in diferenciador.get("hallazgos", []) if i in self.hallazgos]
        dolor = None
        for hallazgo in hallazgos:
            filas = set(self.referencias(hallazgo)[0])
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
                cabe, self.frente_al_rival(diferenciador), self.triangulacion_de(diferenciador)]

    def sustitutos(self):
        """Las filas de la matriz que dicen cómo se resuelve hoy la necesidad sin una app de este tipo (peldaño 4)."""
        return [c for c in self.competidores.values() if c.get("peldano") == 4]

    def sustitutos_fuertes(self):
        """Los sustitutos gratuitos o nativos que ya resuelven la necesidad: cada diferenciador tiene que superarlos."""
        return [c for c in self.sustitutos() if c.get("sustituto") in ("nativo", "gratuito") and c.get("resuelve") == "si"]

    def rivales(self):
        """Lo que cada diferenciador tiene que superar: la alternativa gratis más fuerte que marcó la sesión 1a
        (`competidor --rival`, sea sustituto o competidor directo) y los sustitutos gratuitos o nativos que ya
        resuelven la necesidad."""
        marcados = [c for c in self.competidores.values() if c.get("rival")]
        return marcados + [c for c in self.sustitutos_fuertes() if c not in marcados]

    def rival_pendiente(self):
        """True si nadie marcó la alternativa gratis más fuerte ni dijo que no la hay (`competidor --sin-rival`)."""
        return not self.rivales() and not self.sin_rival

    def comparacion(self, diferenciador, rival):
        """Lo que la sesión 1g registró con `frente`: {resultado, hallazgos, texto} o None."""
        return (diferenciador.get("frente") or {}).get(rival["id"])

    def hallazgos_de(self, diferenciador):
        """Los hallazgos de un diferenciador y los de sus comparaciones con el rival, sin repetir."""
        ids = list(diferenciador.get("hallazgos", []))
        for comparacion in (diferenciador.get("frente") or {}).values():
            ids += [i for i in comparacion.get("hallazgos", []) if i not in ids]
        return ids

    def iguala(self, diferenciador):
        """Los rivales que el diferenciador solo iguala: paridad (básico en Kano), no una razón para elegir la app."""
        return [r for r in self.rivales() if (self.comparacion(diferenciador, r) or {}).get("resultado") == "iguala"]

    def frente_al_rival(self, diferenciador):
        """El quinto criterio de viabilidad: el diferenciador supera a cada rival (la alternativa gratis más fuerte y
        los sustitutos gratuitos o nativos que ya resuelven la necesidad), según lo registrado con `frente`, con al menos
        un hallazgo triangulado. Igualar es paridad y no cumple: (cumple, texto)."""
        rivales = self.rivales()
        sin_evaluar = [c for c in self.sustitutos() if c.get("sustituto") not in SUSTITUTOS
                       or c.get("resuelve") not in RESUELVE]
        if sin_evaluar and not rivales:
            return (False, "Frente al rival: %s sin evaluar: no se sabe si es gratuito o nativo ni si ya resuelve "
                           "la necesidad (`competidor … --peldano 4 --sustituto … --resuelve …`)" % "; ".join(
                               nombre_fila(c) for c in sin_evaluar))
        if not rivales:
            if self.sin_rival:
                return (True, "Frente al rival: no hay una alternativa gratis que resuelva la necesidad (%s)"
                        % self.sin_rival["motivo"])
            otros = self.sustitutos()
            return (True, "Frente al rival: %s" % ("ninguna alternativa gratis marcada y ningún sustituto gratuito o "
                                                   "nativo resuelve la necesidad (%s)" % ", ".join(
                "%s %s" % (c["id"], RESUELVE[c["resuelve"]]) for c in otros) if otros
                else "ninguna alternativa gratis marcada y la matriz no tiene sustitutos (peldaño 4)"))
        superados, faltan = [], []
        for rival in rivales:
            comparacion = self.comparacion(diferenciador, rival)
            if not comparacion:
                nombran = [i for i in self.hallazgos_de(diferenciador) if rival["id"] in self.filas_de(i)]
                faltan.append("sin comparar con %s (`frente --id %s --rival %s --resultado supera|iguala|no "
                              "--hallazgos …`%s)" % (nombre_fila(rival), diferenciador["id"], rival["id"],
                                                     "; lo nombran %s" % ", ".join(nombran) if nombran else ""))
            elif comparacion["resultado"] == "iguala":
                faltan.append("iguala a %s: no viable (paridad, básico en Kano), no es una razón para elegir la "
                              "app" % nombre_fila(rival))
            elif comparacion["resultado"] == "no":
                faltan.append("no supera a %s" % nombre_fila(rival))
            else:
                firmes = [i for i in comparacion["hallazgos"] if i in self.hallazgos
                          and self.evaluar(self.hallazgos[i])["triangulado"]]
                if firmes:
                    superados.append("%s con %s" % (nombre_fila(rival), ", ".join(comparacion["hallazgos"])))
                else:
                    faltan.append("supera a %s, pero ninguno de sus hallazgos (%s) está triangulado" % (
                        nombre_fila(rival), ", ".join(comparacion["hallazgos"])))
        if faltan:
            return False, "Frente al rival: %s" % "; ".join(faltan)
        return True, "Frente al rival: supera a %s" % "; ".join(superados)

    def filas_de(self, identificador):
        """Las filas de la matriz que nombra un hallazgo (`hallazgo --competidores`)."""
        hallazgo = self.hallazgos.get(identificador) or {}
        return set(self.referencias(hallazgo)[0])

    def eleccion(self, diferenciador, filas_hipotesis=None):
        """La prueba de que superar al rival hace elegir la app: el diferenciador supera a cada rival con todos los
        hallazgos de la comparación triangulados y en confianza alta, y ninguna hipótesis de 03-validacion.md sobre él
        quedó débil o refutada: (con_prueba, faltas, hallazgos débiles)."""
        faltas, debiles = [], []
        for rival in self.rivales():
            comparacion = self.comparacion(diferenciador, rival)
            if not comparacion or comparacion["resultado"] != "supera":
                return False, ["no supera a %s" % nombre_fila(rival)], []
            for identificador in comparacion["hallazgos"]:
                hallazgo = self.hallazgos.get(identificador)
                evaluacion = self.evaluar(hallazgo) if hallazgo else None
                if not evaluacion or not evaluacion["triangulado"]:
                    faltas.append("%s sin triangular" % identificador)
                    debiles.append(identificador)
                elif evaluacion["nivel"] < 3:
                    faltas.append("%s en confianza %s" % (identificador, evaluacion["confianza"]))
                    debiles.append(identificador)
        for fila in filas_hipotesis or []:
            if fila["diferenciador"] == diferenciador["id"] and fila["veredicto"] in ("débil", "refutada"):
                faltas.append("la hipótesis %s quedó %s" % (fila["id"], fila["veredicto"]))
        return not faltas, faltas, debiles

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
        """Los hallazgos del diferenciador (y los de sus comparaciones con el rival) que no cumplen la regla 2:
        [(id, lo que le falta)]."""
        resultado = []
        for identificador in self.hallazgos_de(diferenciador):
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
            return (True, "Hallazgos triangulados (regla 2): %s" % ", ".join(self.hallazgos_de(diferenciador)))
        return (False, "Hallazgos triangulados (regla 2): sin triangular %s" % "; ".join(
            "%s (%s)" % par for par in faltan))

    def estado(self, diferenciador):
        """'viable' (los cinco criterios y sus hallazgos triangulados), 'baja' (viable con confianza baja: cumple los
        cinco criterios, pero algún hallazgo no está triangulado), 'paridad' (iguala al rival: básico en Kano, no
        diferencia) o 'no'."""
        criterios = self.viabilidad(diferenciador)
        if not all(cumple for cumple, _ in criterios[:5]):
            return "paridad" if self.iguala(diferenciador) else "no"
        return "viable" if criterios[5][0] else "baja"

    def viable(self, diferenciador):
        return self.estado(diferenciador) == "viable"

    def viables(self):
        return [d for d in self.diferenciadores.values() if self.viable(d)]

    def con_confianza_baja(self):
        return [d for d in self.diferenciadores.values() if self.estado(d) == "baja"]

    def principal(self):
        return next((d for d in self.diferenciadores.values() if d.get("principal")), None)

    def dolor_triangulado(self, diferenciador):
        """«El dolor está triangulado» (feedback #47): los hallazgos propios del diferenciador (`diferenciador
        --hallazgos`: el dolor, el pedido o el vector medible que lo sostienen) cumplen la regla 2. Los de sus
        comparaciones con el rival (`frente`) no entran: lo que les falta es la prueba de elección."""
        propios = list(diferenciador.get("hallazgos", []))
        return bool(propios) and all(i in self.hallazgos and self.evaluar(self.hallazgos[i])["triangulado"]
                                     for i in propios)

    def para_probar(self, diferenciador):
        """Supera a cada rival con el dolor triangulado (feedback #47): hay rivales, cumple los criterios 1 a 5 de
        viabilidad (también superar a cada rival con al menos un hallazgo triangulado) y sus hallazgos propios están
        triangulados. Si algo le falta, es la prueba de elección, que se mide después del lanzamiento."""
        return bool(self.rivales()) and self.estado(diferenciador) in ("viable", "baja") \
            and self.dolor_triangulado(diferenciador)


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


def texto_rivales(rivales):
    """'C-2 (PlantaPlus)': los rivales a superar, por nombre."""
    return "; ".join(nombre_fila(c) for c in rivales)


def partes_rivales(rivales):
    """Los rivales por separado, cada uno con lo que es (feedback #40): [('el', 'rival C-2 (…)'), ('el', 'sustituto
    C-5 (…)')]. El rival es la alternativa gratis marcada en la 1a; los demás, sustitutos que ya resuelven."""
    marcados = [c for c in rivales if c.get("rival")]
    otros = [c for c in rivales if not c.get("rival")]
    partes = [("el", "rival %s" % nombre_fila(c)) for c in marcados]
    if len(otros) == 1:
        partes.append(("el", "sustituto %s" % nombre_fila(otros[0])))
    elif otros:
        partes.append(("los", "sustitutos %s" % y_lista(nombre_fila(c) for c in otros)))
    return partes


def unir(textos, conector):
    textos = list(textos)
    return textos[0] if len(textos) == 1 else "%s %s %s" % (", ".join(textos[:-1]), conector, textos[-1])


def a_los_rivales(rivales, conector="y"):
    """'al rival C-2 (…) y al sustituto C-5 (…)', o con 'ni': 'no supera al rival … ni al sustituto …'."""
    return unir((("al " if articulo == "el" else "a los ") + texto for articulo, texto in partes_rivales(rivales)),
                conector)


def los_rivales(rivales, conector="y"):
    """'el rival C-2 (…) y el sustituto C-5 (…)'."""
    return unir(("%s %s" % par for par in partes_rivales(rivales)), conector)


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


def tipo_provisional(producto):
    """True si el tipo es el provisional de la sesión 0, que la sesión 1a todavía no confirmó."""
    return bool((producto.get("tipo") or {}).get("provisional"))


def texto_tipo(producto):
    """'nueva', 'nueva (provisional: la confirma 1a)' o 'sin registrar'."""
    tipo = tipo_de(producto)
    if not tipo:
        return "sin registrar"
    return "%s (provisional: la confirma 1a)" % tipo if tipo_provisional(producto) else tipo


def presupuesto_de(producto):
    return PRESUPUESTO_NUEVA if tipo_de(producto) == "nueva" else PRESUPUESTO


def presupuesto_reapertura(producto):
    """El presupuesto propio de cada reapertura de una línea: la mitad del original, redondeada hacia arriba (#34)."""
    return {clave: int(math.ceil(valor * REAPERTURA)) for clave, valor in presupuesto_de(producto).items()}


def tipo_al_cerrar(producto, sesion):
    """El tipo de idea con el que trabajó una sesión cerrada: el que anotó `cerrar` o, en un registro anterior, el que
    estaba registrado antes de su cierre (None si no había ninguno)."""
    datos = producto["sesiones"].get(sesion) or {}
    if "tipo" in datos:
        return datos["tipo"]
    cierre = datos.get("cerrada") or ""
    vigente_ = None
    for tipo in list(producto.get("tipo_historial") or []) + [producto.get("tipo")]:
        if tipo and tipo.get("fecha", "") < cierre:
            vigente_ = tipo["valor"]
    return vigente_


def a_revisar_por_tipo(producto, registro):
    """Las líneas cerradas que trabajaron con otro tipo de idea (o sin ninguno) y no tienen fuentes de los peldaños
    que pide el tipo de hoy (feedback #28): [(sesión, tipo con el que trabajó, peldaños que faltan)]. Una que ya subió
    por la escalera (o que ya trabajó con competencia) no se marca: no hace falta repetirla."""
    tipo = tipo_de(producto)
    if not tipo:
        return []
    resultado = []
    for sesion, por_analogia in PELDANOS_POR_TIPO.items():
        if not cerrada(producto, sesion):
            continue
        antes = tipo_al_cerrar(producto, sesion)
        if (antes == "nueva") == (tipo == "nueva") and antes is not None:
            continue
        if antes is None and tipo != "nueva":
            continue  # sin tipo se investigaba como si hubiera competencia: es lo que pide una idea existente
        peldanos = por_analogia if tipo == "nueva" else PELDANOS_CON_COMPETENCIA
        linea = next(nombre for nombre, (_, de_sesion) in LINEAS.items() if de_sesion == sesion)
        if not any(f["linea"] == linea and f["peldano"] in peldanos for f in registro.fuentes.values()):
            resultado.append((sesion, antes, peldanos))
    return resultado


def texto_revisar(revisar):
    """'1c (cerró sin tipo registrado; le faltan los peldaños 4 y 5)'."""
    return "; ".join("%s (cerró %s y no tiene fuentes de los peldaños %s)" % (
        sesion, "como idea %s" % antes if antes else "sin tipo registrado", y_lista(str(n) for n in peldanos))
        for sesion, antes, peldanos in revisar)


# Los estados de un diferenciador, con las mismas palabras en el banner, los criterios, el reporte y el tablero
# (feedback #25): viable, viable con confianza baja y no viable (la paridad es una forma de no viable).
ESTADOS_DIFERENCIADOR = {"viable": "viable", "baja": "viable con confianza baja",
                         "paridad": "no viable (paridad: iguala al rival)", "no": "no viable"}


def texto_estados(registro, diferenciadores):
    """'D-1 y D-5 (viables con confianza baja)', 'D-4 (no viable: paridad)': los IDs con su estado, agrupados."""
    grupos = {}
    for diferenciador in diferenciadores:
        grupos.setdefault(registro.estado(diferenciador), []).append(diferenciador["id"])
    plurales = {"viable": ("viable", "viables"), "baja": ("viable con confianza baja", "viables con confianza baja"),
                "paridad": ("no viable: paridad", "no viables: paridad"), "no": ("no viable", "no viables")}
    return "; ".join("%s (%s)" % (y_lista(ids), plurales[estado][len(ids) > 1])
                     for estado, ids in sorted(grupos.items(), key=lambda par: list(plurales).index(par[0])))


def y_lista(elementos, conector="y"):
    """['D-1', 'D-5', 'D-6'] → 'D-1, D-5 y D-6' (o 'D-1, D-5 o D-6')."""
    elementos = list(elementos)
    if len(elementos) <= 1:
        return "".join(elementos)
    return "%s %s %s" % (", ".join(elementos[:-1]), conector, elementos[-1])


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
    # Un vacío también se registra en una línea o una dimensión que no lo pide (la tienda en monetización, por ejemplo):
    # queda a la vista junto con la cobertura que sí se pide, salvo que una fuente de esa línea ya lo cubra.
    for vacio in registro.vacios.values():
        linea, dimension = vacio["linea"], vacio["dimension"]
        if (solo and linea != solo) or dimension in COBERTURA_LINEAS.get(linea, ()) or dimension not in DIMENSIONES:
            continue  # un vacío por peldaño no es de cobertura: lo cuenta `conteo_peldanos`
        cubierto = any(f["linea"] == linea and normal(vacio["valor"]) in [normal(v) for v in f.get(dimension, [])]
                       for f in registro.fuentes.values())
        if not cubierto:
            resultado.setdefault(linea, []).append((dimension, vacio["valor"], "vacio", vacio))
    return resultado


def vacios_de_herramienta(producto, registro, lineas=None):
    """Los vacíos por límite de las herramientas que siguen sin fuentes, en las líneas pedidas (None: todas): ajustar
    la línea con las mismas herramientas no los resuelve."""
    mapa = cobertura(producto, registro) or {}
    return [detalle for linea, filas in mapa.items() for _, _, estado, detalle in filas
            if estado == "vacio" and detalle["motivo"] == "herramienta" and (lineas is None or linea in lineas)]


def fuentes_que_cubren(registro, linea, dimension, valor):
    """Los IDs de las fuentes de la línea que llevan ese mercado, idioma o tienda en sus etiquetas."""
    buscado = normal(valor)
    return [f["id"] for f in registro.fuentes.values() if f["linea"] == linea
            and buscado in [normal(v) for v in f.get(dimension, [])]]


def vacios_parciales(registro, lineas=None, motivo=None):
    """Los vacíos de un mercado, idioma o tienda que ya tiene fuentes en su línea (feedback #51): [(vacío, [S-…])].
    La cobertura los da por cubiertos (no son huecos ni cambian ningún veredicto), pero lo que dice el vacío (no se
    pudo leer Reddit en español, por ejemplo) sigue sin fuentes: se muestran junto a la cobertura para que no se
    pierdan. Con `lineas` o `motivo`, solo los de esas líneas o ese motivo."""
    parciales = []
    for vacio in registro.vacios.values():
        linea, dimension = vacio["linea"], vacio["dimension"]
        if dimension not in DIMENSIONES or (lineas is not None and linea not in lineas) or (
                motivo and vacio["motivo"] != motivo):
            continue  # un vacío por peldaño no es de cobertura
        fuentes = fuentes_que_cubren(registro, linea, dimension, vacio["valor"])
        if fuentes:
            parciales.append((vacio, fuentes))
    return parciales


def texto_corto(texto, maximo=80):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= maximo else texto[:maximo - 1].rstrip() + "…"


def texto_parcial(vacio):
    """'⚠ vacío parcial V-VOZ-1 (límite de las herramientas): no se pudo leer Reddit en español'."""
    return "⚠ vacío parcial %s (%s): %s" % (vacio["id"], MOTIVOS_VACIO[vacio["motivo"]], texto_corto(vacio["texto"]))


def texto_parciales(parciales):
    """'voz-del-usuario · idioma es (V-VOZ-1: no se pudo leer Reddit…)', para los avisos."""
    return "; ".join("%s · %s %s (%s: %s)" % (v["linea"], DIMENSIONES[v["dimension"]], v["valor"], v["id"],
                                              texto_corto(v["texto"], 60)) for v, _ in parciales)


def lineas_de(sesiones):
    """Las líneas de investigación que escriben esas sesiones (la 1d escribe monetizacion); [] si ninguna lo es."""
    return [linea for linea, (_, sesion) in LINEAS.items() if sesion in sesiones]


def vacios_de_sesion(producto, registro, sesion):
    """Los vacíos por límite de las herramientas de las líneas de esa sesión: solo esos afectan a ajustarla (feedback
    #44). Una sesión sin línea (la 1f, la 2, la 4) no tiene ninguno."""
    lineas = lineas_de([sesion])
    return vacios_de_herramienta(producto, registro, lineas) if lineas else []


def texto_vacios_sesion(sesion, vacios):
    """'La sesión 1d (monetización) tiene vacíos por límite de las herramientas (V-MON-4: tienda google-play)'."""
    lineas = sorted({v["linea"] for v in vacios})
    return "La sesión %s (%s) tiene %s por límite de las herramientas (%s)" % (
        sesion, ", ".join(LINEAS_LLANO.get(l, l).lower() for l in lineas),
        "un vacío" if len(vacios) == 1 else "vacíos", "; ".join(
            "%s: %s %s" % (v["id"], DIMENSIONES.get(v["dimension"], v["dimension"]), v["valor"]) for v in vacios))


def texto_vacio(vacio):
    return "%s · %s %s (%s, %s): %s" % (vacio["linea"], DIMENSIONES.get(vacio["dimension"], "peldaño"),
                                        vacio["valor"], MOTIVOS_VACIO[vacio["motivo"]], vacio["id"], vacio["texto"])


def conteo_peldanos(registro):
    """Los hallazgos por peldaño de la escalera (feedback #32), vigentes (con al menos una fuente vigente) y vencidos,
    y lo que se buscó sin resultado (`vacio --peldano`): {peldaño: {"vigentes", "vencidos", "sin_resultado",
    "no_buscado"}}. Un peldaño sin hallazgos ni búsquedas registradas no se buscó (feedback #28)."""
    conteo = {n: {"vigentes": 0, "vencidos": 0, "sin_resultado": [], "no_buscado": False} for n in PELDANOS}
    for hallazgo in registro.hallazgos.values():
        evaluacion = registro.evaluar(hallazgo)
        conteo[evaluacion["peldano"]]["vigentes" if evaluacion["independientes"] else "vencidos"] += 1
    for vacio in registro.vacios.values():
        if vacio["dimension"] == "peldano":
            conteo[int(vacio["valor"])]["sin_resultado"].append(vacio["id"])
    for datos in conteo.values():
        datos["no_buscado"] = not (datos["vigentes"] or datos["vencidos"] or datos["sin_resultado"])
    return conteo


def texto_peldanos(conteo):
    """'1 · directo: 14 (12 vigentes, 2 vencidos) · 4 · sustituto: no buscado · …'."""
    partes = []
    for peldano, datos in sorted(conteo.items()):
        nombre = "%d · %s" % (peldano, PELDANOS[peldano][0])
        if datos["no_buscado"]:
            partes.append("%s: no buscado" % nombre)
            continue
        total = datos["vigentes"] + datos["vencidos"]
        texto = "%s: %d (%s, %s)" % (nombre, total, plural(datos["vigentes"], "vigente"),
                                     plural(datos["vencidos"], "vencido"))
        if datos["sin_resultado"]:
            texto += ", buscado sin resultado (%s)" % ", ".join(datos["sin_resultado"])
        partes.append(texto)
    return " · ".join(partes)


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


def criterios_aceptacion(texto):
    """Los criterios de aceptación de cada historia de 04-prd.md (feedback #44): {F-…: cantidad}. Una historia empieza
    en un título con su ID (`### F-01`); sus criterios son las viñetas que siguen a «Criterios de aceptación» hasta el
    campo siguiente (`- **…**`) o el título siguiente. El texto de plantilla no cuenta."""
    conteo, actual, dentro = {}, None, False
    for linea in (texto or "").splitlines():
        if re.match(r"^\s*#{1,6}\s", linea):
            encontrado = re.findall(r"F-\d+", linea)
            actual, dentro = (encontrado[0] if encontrado else None), False
            if actual:
                conteo.setdefault(actual, 0)
            continue
        if not actual:
            continue
        marca = re.match(r"^\s*[-*]?\s*\*{0,2}criterios de aceptaci[oó]n\*{0,2}\s*:?\s*\*{0,2}\s*(.*)$", linea, re.I)
        if marca:
            dentro = True
            resto = marca.group(1).strip()
            if resto and PENDIENTE not in resto:
                conteo[actual] += 1
            continue
        if dentro and re.match(r"^[-*]\s+\*\*", linea):  # el campo siguiente de la historia
            dentro = False
            continue
        vineta = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", linea)
        if dentro and vineta and PENDIENTE not in vineta.group(1):
            conteo[actual] += 1
    return conteo


def prd(carpeta, registro):
    """Las tablas de 04-prd.md: funcionalidades (con su RICE y sus criterios de aceptación), métricas HEART y checklist
    de políticas."""
    texto = leer_md(carpeta, "04-prd.md")
    filas = tabla(texto, "id", "funcionalidad", "mvp", "hallazgos", "metrica")
    metricas, detalle_metricas = {}, []
    for fila in tabla(texto, "id", "dimension", "metrica", "meta") or []:
        for identificador in re.findall(r"M-\d+", celda(fila, "id")):
            completa = bool(celda(fila, "metrica") and celda(fila, "meta")) and any(
                palabra in normal(celda(fila, "dimension")) for palabra in HEART)
            metricas[identificador] = completa
            detalle_metricas.append({"id": identificador, "dimension": celda(fila, "dimension"),
                                     "metrica": celda(fila, "metrica"), "meta": celda(fila, "meta"),
                                     "completa": completa})
    politicas = [(celda(fila, "requisito"), normal(celda(fila, "estado")))
                 for fila in tabla(texto, "requisito", "estado") or [] if celda(fila, "requisito")]
    notas = {celda(fila, "requisito"): celda(fila, "nota") for fila in tabla(texto, "requisito", "estado") or []}
    aceptacion = criterios_aceptacion(texto)
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
            "aceptacion": aceptacion.get(identificador, 0),
        })
    return {"existe": filas is not None, "funciones": funciones, "metricas": metricas, "politicas": politicas,
            "detalle_metricas": detalle_metricas, "notas": notas}


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
            modelos = puntajes_por_modelo(producto, registro)
            mejor = max(modelos, key=lambda m: m["vigente"]["total"])
            agregar("puntaje", mejor["vigente"]["total"] >= minimo, texto, texto_puntajes(modelos, minimo))
        else:
            agregar("puntaje", False, texto, "sin registrar: corre `puntaje` en la sesión 1f")
        if nueva:
            minimas = int(criterios["fuentes_minimas"])
            documentado = problema_documentado(registro)
            conteo = conteo_peldanos(registro)
            no_buscado = conteo[4]["no_buscado"] and conteo[5]["no_buscado"]
            if documentado:
                detalle = documentado
            elif no_buscado:
                detalle = "no buscado: ningún hallazgo ni búsqueda sin resultado registrada en los peldaños 4 y 5"
            else:
                detalle = ("buscado: ningún hallazgo reúne %d fuentes independientes y vigentes de esos peldaños, una "
                           "de los últimos %s meses" % (minimas, criterios["vigencia_meses"]))
            agregar("problema", documentado,
                    "El problema o la necesidad de fondo, con %d fuentes de peldaño 4 o 5" % minimas, detalle)
            analogos = [c for c in registro.competidores.values() if c["peldano"] in (2, 3)]
            con = [c for c in analogos if registro.con_traccion(c)]
            sin = [c["id"] for c in analogos if not registro.con_traccion(c)]
            pedidos = int(criterios["analogos_minimos"])
            agregar("analogos", len(con) >= pedidos,
                    "Al menos %d análogos con tracción (peldaño 2 o 3)" % pedidos,
                    "%d de %d%s%s" % (len(con), pedidos, ": " + "; ".join(
                        "%s (%s)" % (c["id"], registro.motivo_traccion(c)) for c in con) if con else "",
                        " · sin tracción (bajo %s descargas o %s valoraciones, y sin respaldo institucional): %s" % (
                            numero(float(criterios["traccion_descargas"])),
                            numero(float(criterios["traccion_valoraciones"])), ", ".join(sin)) if sin else ""))
            intentos = producto.get("intentos", [])
            fracasos = [i for i in intentos if i["resultado"] == "fracaso-demanda"]
            texto = "Sin evidencia de que se probó y fracasó por falta de demanda"
            if not intentos:
                agregar("intentos", False, texto, "la búsqueda no está registrada: corre `intento`")
            else:
                agregar("intentos", not fracasos, texto,
                        "%s por demanda" % plural(len(fracasos), "intento fallido", "intentos fallidos") if fracasos
                        else plural(len(intentos), "búsqueda registrada", "búsquedas registradas"))
            rivales = registro.rivales()
            if rivales:  # la alternativa gratis más fuerte o un sustituto que ya resuelve: la idea tiene que superarlo
                viables = registro.viables()
                agregar("rival", viables, "Un diferenciador viable supera %s" % a_los_rivales(rivales),
                        ", ".join(d["id"] for d in viables) if viables else detalle_rival(registro, rivales))
        else:
            nivel = confianzas(registro)[0]["demanda"]
            agregar("demanda", nivel >= 2, "Demanda con confianza media o alta", "es %s" % NIVELES[nivel])
            viables = registro.viables()
            rivales, pendiente = registro.rivales(), registro.rival_pendiente()
            detalle = "%s de %s%s" % (plural(len(viables), "viable"), plural(len(registro.diferenciadores),
                                                                          "registrado"),
                                      ": " + texto_estados(registro, registro.diferenciadores.values())
                                      if registro.diferenciadores else "")
            if rivales and not viables:
                detalle += " · " + detalle_rival(registro, rivales, con_estados=False)
            if pendiente:
                detalle += " · falta marcar la alternativa gratis más fuerte (`competidor … --rival`) o decir que no " \
                           "la hay (`competidor --sin-rival`)"
            agregar("diferenciador", viables and not pendiente,
                    "Al menos 1 diferenciador viable, con sus hallazgos triangulados%s" % (
                        " y que supere %s" % a_los_rivales(rivales) if rivales
                        else " y que supere a la alternativa gratis más fuerte (sin marcar)" if pendiente else ""),
                    detalle)
            principal = registro.principal()
            texto = "Los hallazgos del diferenciador principal están triangulados%s" % (
                " y supera %s" % a_los_rivales(rivales) if rivales else "")
            if not principal:
                agregar("principal", False, texto, "no hay un diferenciador principal registrado")
            else:
                faltan = registro.sin_triangular(principal)
                frente = registro.frente_al_rival(principal) if rivales else (True, "")
                partes = ["%s sin triangular (%s)" % par for par in faltan]
                if not frente[0]:
                    partes.insert(0, frente[1].replace("Frente al rival: ", ""))
                agregar("principal", not faltan and frente[0], texto, "%s: %s" % (
                    principal["id"], "; ".join(partes) or ", ".join(registro.hallazgos_de(principal))))
        texto = "Riesgo de políticas distinto de 1, o con una mitigación escrita"
        bloqueos = registro.bloqueos(objetivo_de(producto))
        if not puntaje:
            agregar("riesgo", False, texto, "sin puntaje")
        else:
            riesgo, mitigacion = puntaje["valores"]["riesgo"], puntaje.get("mitigacion")
            otros = [m for m in puntaje.get("alternativos") or [] if m["valores"]["riesgo"] != 1]
            if riesgo == 1 and not mitigacion and otros and not bloqueos:
                agregar("riesgo", True, texto, "es 1 con %s y %s con %s: exige ese modelo (se decide en la sesión 2)"
                        % (nombre_modelo(puntaje), otros[0]["valores"]["riesgo"], "«%s»" % otros[0]["modelo"]))
            elif bloqueos and riesgo != 1:
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
        elif escenarios_anteriores(escenarios):
            agregar("monetizacion", False, texto,
                    "los escenarios son de una versión anterior que cobraba el pago único cada mes a los usuarios del "
                    "mes: vuelve a correr `escenarios` con `tipo` en cada compra e `instalaciones_mes`")
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
        # una idea que pasó la puerta 1 como Viable para probar (#47): la prueba de elección es la hipótesis más
        # riesgosa, que se mide después del lanzamiento; no se vuelve a pedir, pero sí su métrica y su umbral
        descarte = criterio_descarte_vigente(carpeta) if not nueva else None
        if nueva or descarte:
            riesgosas = [fila for fila in filas or [] if fila["riesgosa"]]
            medible = len(riesgosas) == 1 and riesgosas[0]["metrica"]
            agregar("riesgosa", medible, "La hipótesis más riesgosa, identificada y medible después del lanzamiento%s"
                    % (" (el criterio de descarte de la puerta 1)" if descarte else ""),
                    "%s, con métrica y umbral" % riesgosas[0]["id"] if medible
                    else "falta marcar una sola hipótesis como la más riesgosa, con su métrica y su umbral")
        if not nueva:
            principal = registro.principal()
            texto = "El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta"
            if not principal:
                agregar("sobrevive", False, texto, "no hay un diferenciador principal registrado")
            else:
                suyas = [fila for fila in filas or [] if fila["diferenciador"] == principal["id"]]
                # la hipótesis más riesgosa sobre él puede quedar débil: es la prueba de elección que se mide después
                diferidas = [f for f in suyas if descarte and f["riesgosa"] and f["veredicto"] == "débil"]
                sobrevive = suyas and all(f["veredicto"] == "sostenida" and f["nivel"] >= 2
                                          for f in suyas if f not in diferidas)
                agregar("sobrevive", sobrevive, texto, "%s: %s" % (principal["id"], ", ".join(
                    "%s %s (confianza %s%s)" % (f["id"], f["veredicto"] or "sin veredicto", NIVELES[f["nivel"]],
                                                "; es la más riesgosa: se prueba después del lanzamiento"
                                                if f in diferidas else "")
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
        sin_criterios = criterios_sin_aceptacion(mvp)  # lo cuenta el script, no la sesión (feedback #44)
        agregar("aceptacion", mvp and not sin_criterios, "Cada funcionalidad del MVP tiene criterios de aceptación",
                "%d de %d%s" % (len(mvp) - len(sin_criterios), len(mvp), " · sin criterios: %s" % ", ".join(
                    sin_criterios) if sin_criterios else " · %s" % plural(sum(f["aceptacion"] for f in mvp), "criterio")))
        definidas = datos["metricas"] and all(datos["metricas"].values())
        agregar("heart", definidas, "Métricas HEART definidas", "%s, %s" % (
            plural(len(datos["metricas"]), "métrica"),
            plural(sum(1 for completa in datos["metricas"].values() if not completa), "incompleta")))
        bloqueos = [requisito for requisito, estado in datos["politicas"] if estado == "bloqueo"]
        agregar("checklist", datos["politicas"] and not bloqueos, "Checklist de políticas sin bloqueos",
                "bloqueos: %s" % "; ".join(bloqueos) if bloqueos
                else plural(len(datos["politicas"]), "requisito") if datos["politicas"] else "el checklist está vacío")
        if nueva or criterio_descarte_vigente(carpeta):
            riesgosas = [fila for fila in hipotesis(carpeta, registro) or [] if fila["riesgosa"]]
            riesgosa = riesgosas[0] if len(riesgosas) == 1 else None
            prueba = riesgosa and riesgosa["metrica"] and [f["id"] for f in mvp if riesgosa["id"] in f["hipotesis"]]
            agregar("riesgosa_mvp", prueba,
                    "El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral",
                    "%s en %s" % (riesgosa["id"], ", ".join(prueba)) if prueba
                    else "ninguna funcionalidad del MVP cita la hipótesis más riesgosa (columna Hipótesis), o le "
                         "falta su métrica y su umbral en 03-validacion.md")
    return resultado


def detalle_rival(registro, rivales, con_estados=True):
    """Por qué ningún diferenciador viable supera a los rivales: quién lo supera sin ser viable (con su estado) y
    quién solo lo iguala."""
    candidatos = [d for d in registro.diferenciadores.values() if registro.frente_al_rival(d)[0]]
    paridad = [d["id"] for d in registro.diferenciadores.values() if registro.iguala(d)]
    partes = []
    if candidatos:
        verbo = "lo supera" if len(candidatos) == 1 else "lo superan"
        partes.append("%s con evidencia: %s" % (verbo, texto_estados(registro, candidatos)) if con_estados
                      else "%s %s con evidencia" % (y_lista(d["id"] for d in candidatos), verbo))
    else:
        partes.append("ningún diferenciador supera %s con un hallazgo triangulado" % a_los_rivales(rivales, "ni"))
    if paridad:
        partes.append("%s solo %s%s" % (y_lista(paridad), "lo iguala" if len(paridad) == 1 else "lo igualan",
                                        ": no viable (paridad)" if con_estados else ""))
    return "; ".join(partes)


def escenarios_anteriores(escenarios):
    """True si los escenarios tienen compras calculadas con la regla anterior (el pago único sobre los usuarios del
    mes, cada mes): inflaba el caso base y hay que recalcularlos."""
    return int(escenarios.get("calculo") or 1) < CALCULO_ESCENARIOS and any(
        m["nombre"].startswith("Compra · ") for m in escenarios.get("modelos") or [])


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
        revisar = a_revisar_por_tipo(producto, registro)
        if revisar:
            avisos.append("⚠ A revisar por cambio de tipo (la idea es %s): %s. Lo que no buscaron no cuenta como "
                          "evidencia en contra." % (tipo_de(producto), texto_revisar(revisar)))
        if tipo_de(producto) == "nueva":
            avisos.append("· Hallazgos por peldaño: %s." % texto_peldanos(conteo_peldanos(registro)))
        revisar_rival = rival_a_revisar(registro)
        if revisar_rival:
            avisos.append("⚠ Revisar el rival: %s." % texto_rival_a_revisar(registro, revisar_rival))
        excedidas = pasadas_excedidas(producto)
        if excedidas:
            avisos.append("⚠ Presupuesto excedido: %s. La síntesis lo dice." % "; ".join(
                "%s usó %s" % par for par in excedidas))
        exigido = modelo_exigido(producto, registro)
        if exigido:
            avisos.append("· El puntaje depende del modelo de monetización: alcanza el mínimo solo con %s, que se "
                          "decide en la sesión 2. Con el modelo base es %s." % (
                              exigido["modelo"], texto_puntaje(puntajes_por_modelo(producto, registro)[0])))
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
            parciales = vacios_parciales(registro, motivo="herramienta")
            if parciales:
                avisos.append("· Vacíos parciales por límite de las herramientas (esa cobertura ya tiene fuentes, pero "
                              "lo que dice el vacío sigue sin leerse): %s. No cambian la cobertura ni el veredicto; "
                              "con las mismas herramientas, ajustar esas líneas no los resuelve." % texto_parciales(
                                  parciales))
    descarte = criterio_descarte_vigente(carpeta) if numero_puerta in (2, 3) else None
    if descarte:
        avisos.append("· La puerta 1 fue Viable para probar: la prueba de elección se mide después del lanzamiento. "
                      "Criterio de descarte: %s." % descarte["texto"])
    if numero_puerta == 2:
        for aviso in (producto.get("escenarios") or {}).get("avisos") or []:
            avisos.append("⚠ Usuarios activos de un comparable maduro: %s." % aviso)
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
    diferidos = resultado.get("diferidos") or []
    for c in evaluados:
        diferido = not c["cumple"] and c["clave"] in diferidos
        lineas.append("  %s %s%s%s" % ("✔" if c["cumple"] else "◐" if diferido else "✖", c["texto"],
                                      " · " + c["detalle"] if c["detalle"] else "",
                                      " · se prueba después del lanzamiento (criterio de descarte)" if diferido
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
    # supera al rival con el dolor triangulado y falta la prueba de elección, que se mide después del lanzamiento
    "probar": {"titulo": "Viable para probar", "recomienda": "seguir", "tono": "aviso", "marca": "🟡", "color": "33"},
    "viable": {"titulo": "Viable", "recomienda": "seguir", "tono": "bien", "marca": "🟢", "color": "32"},
}
MAXIMO_RAZONES = 3
# las sesiones cuya evidencia decide cada criterio de la puerta 1: si una cerró con otro tipo de idea y quedó a revisar,
# el criterio no lleva a descartar (feedback #28)
DEPENDE_CRITERIO = {"puntaje": INVESTIGACION, "demanda": ("1c",), "problema": ("1b", "1c"), "analogos": ("1a",),
                    "diferenciador": ("1b", "1g"), "rival": ("1b", "1g"), "principal": ("1g",)}
NOMBRES_CRITERIO = {"demanda": "demanda", "monetizacion": "monetización", "facilidad": "facilidad",
                    "riesgo": "riesgo de políticas", "diferenciacion": "diferenciación"}
SESION_CRITERIO = {"demanda": "1c", "monetizacion": "1d", "riesgo": "1e", "diferenciacion": "1g"}


def limites_puntaje(producto, registro):
    """Los topes que las reglas y la evidencia de hoy ponen al puntaje (los mismos que aplica `puntaje` al
    registrarlo): {criterio: (mínimo, máximo, motivo)}."""
    limites = {}
    viables, bajas = registro.viables(), registro.con_confianza_baja()
    probar = [] if condiciones_probar(producto, registro) else [d for d in bajas if registro.para_probar(d)]
    if not viables and not bajas:
        limites["diferenciacion"] = (1, 1, "ningún diferenciador es viable")
    elif not viables and probar:  # su confianza baja es solo la prueba de elección, que no castiga el puntaje (#47)
        limites["diferenciacion"] = (2, 5, "%s %s al rival con el dolor triangulado: le falta solo la prueba de "
                                           "elección, que se mide después del lanzamiento" % (
                                               y_lista(d["id"] for d in probar),
                                               "supera" if len(probar) == 1 else "superan"))
    elif not viables:
        limites["diferenciacion"] = (1, 2, "solo hay diferenciadores viables con confianza baja: %s" % y_lista(
            d["id"] for d in bajas))
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


def puntaje_vigente(producto, registro, valores=None):
    """El puntaje registrado contra las reglas y la evidencia de hoy: {total, valores, incoherencias}. Una incoherencia
    aparece cuando el puntaje se registró con reglas anteriores o cuando la evidencia cambió después (una fuente que
    envejeció, un hallazgo anulado); el total ajustado lleva cada valor a su tope. Con `valores`, los de otro modelo
    de monetización registrado (`puntaje --alternativo`)."""
    puntaje = producto.get("puntaje")
    if not puntaje:
        return None
    valores, incoherencias = dict(valores or puntaje["valores"]), []
    for criterio, (minimo, maximo, motivo) in limites_puntaje(producto, registro).items():
        valor = valores[criterio]
        if not minimo <= valor <= maximo:
            ajustado = min(max(valor, minimo), maximo)
            incoherencias.append("%s %d, pero con las reglas de hoy %s %d (%s)" % (
                NOMBRES_CRITERIO[criterio], valor, "el máximo es" if valor > maximo else "el mínimo es", ajustado,
                motivo))
            valores[criterio] = ajustado
    return {"total": sum(valores.values()), "valores": valores, "incoherencias": incoherencias}


def nombre_modelo(puntaje):
    """'«Anuncios»' o 'el modelo base': el modelo de monetización con el que se registró el puntaje."""
    return "«%s»" % puntaje["modelo"] if puntaje.get("modelo") else "el modelo base"


def puntajes_por_modelo(producto, registro):
    """El puntaje con cada modelo de monetización registrado (feedback #29): el base primero y después los
    alternativos de `puntaje --alternativo`, cada uno con lo registrado y lo que da con las reglas de hoy:
    [{modelo, base, registrado, vigente}]."""
    puntaje = producto["puntaje"]
    modelos = [{"modelo": nombre_modelo(puntaje), "base": True, "registrado": puntaje["total"],
                "vigente": puntaje_vigente(producto, registro)}]
    for otro in puntaje.get("alternativos") or []:
        modelos.append({"modelo": "«%s»" % otro["modelo"], "base": False, "registrado": otro["total"],
                        "vigente": puntaje_vigente(producto, registro, otro["valores"])})
    return modelos


def texto_puntaje(modelo):
    """'15/25 (se registró 17/25)': el de hoy como principal y el registrado como dato secundario (feedback #27)."""
    hoy_ = modelo["vigente"]["total"]
    return "%d/25%s" % (hoy_, " (se registró %d/25)" % modelo["registrado"] if hoy_ != modelo["registrado"] else "")


def texto_puntajes(modelos, minimo):
    """El detalle del criterio de puntaje: el de hoy, el registrado si difiere y, con varios modelos, cuál exige."""
    base = modelos[0]
    texto = "tiene %s" % texto_puntaje(base)
    if base["vigente"]["incoherencias"]:
        texto += " · con las reglas de hoy: %s" % "; ".join(base["vigente"]["incoherencias"])
    if len(modelos) > 1:
        texto += " · por modelo de monetización: %s" % "; ".join(
            "%s %s" % (m["modelo"], texto_puntaje(m)) for m in modelos)
        exigido = next((m for m in modelos[1:] if m["vigente"]["total"] >= minimo), None)
        if base["vigente"]["total"] < minimo and exigido:
            texto += " · alcanza el mínimo solo con %s: exige ese modelo (se decide en la sesión 2)" % exigido["modelo"]
    return texto


def modelo_exigido(producto, registro):
    """El modelo alternativo que la puerta 1 exige porque solo con él alcanza el mínimo, o None (feedback #29)."""
    puntaje = producto.get("puntaje")
    if not puntaje or not puntaje.get("alternativos"):
        return None
    minimo = int(producto["criterios"]["puntaje_minimo_nueva" if tipo_de(producto) == "nueva" else "puntaje_minimo"])
    modelos = puntajes_por_modelo(producto, registro)
    base_pasa = modelos[0]["vigente"]["total"] >= minimo and (puntaje["valores"]["riesgo"] != 1
                                                              or puntaje.get("mitigacion"))
    if base_pasa:
        return None
    for modelo, otro in zip(modelos[1:], puntaje["alternativos"]):
        if modelo["vigente"]["total"] >= minimo and otro["valores"]["riesgo"] != 1:
            return modelo
    return None


def problema_documentado(registro):
    """El primer hallazgo que documenta el problema (idea nueva) con las fuentes mínimas, independientes y vigentes,
    de los peldaños 4 o 5, una de ellas de los últimos `vigencia_meses` meses; None si no hay."""
    minimas = int(registro.criterios["fuentes_minimas"])
    for hallazgo in registro.hallazgos.values():
        fuentes = [f for f in registro.fuentes_de(hallazgo["fuentes"]) if f["peldano"] in (4, 5) and registro.vigente(f)]
        if len({independencia(f) for f in fuentes}) >= minimas and any(registro.reciente(f) for f in fuentes):
            return hallazgo["id"]
    return None


def rival_a_revisar(registro):
    """Los sustitutos gratuitos o nativos con tracción que llegaron después de marcar el rival y no lo son (feedback
    #36): el rival es la alternativa gratis más fuerte para el mismo usuario y la misma necesidad, y uno nuevo puede
    serlo. En un registro anterior, sin fechas, los que agregó otra línea (sus fuentes no son de competencia)."""
    marcado = next((c for c in registro.competidores.values() if c.get("rival")), None)
    if not marcado:
        return []
    resultado = []
    for fila in registro.sustitutos():
        if fila is marcado or fila in registro.rivales() or fila.get("sustituto") not in ("nativo", "gratuito") \
                or not registro.con_traccion(fila):
            continue
        if marcado.get("rival_fecha") and fila.get("fecha"):
            despues = fila["fecha"] > marcado["rival_fecha"]
        elif marcado.get("rival_fecha"):
            despues = False  # el rival se volvió a marcar después: ya se revisó
        else:
            despues = all(not str(f).startswith("S-COM-") for f in fila.get("fuentes", []))
        if despues:
            resultado.append(fila)
    return resultado


def texto_rival_a_revisar(registro, filas):
    marcado = next(c for c in registro.competidores.values() if c.get("rival"))
    return ("%s llegó después de marcar el rival (%s): revisa cuál es la alternativa gratis más fuerte para el mismo "
            "usuario y la misma necesidad (segmento y edad). Para cambiarlo, `competidor --nombre … --rival` y "
            "comparar de nuevo cada diferenciador en la 1g (`frente`); para confirmarlo, vuelve a marcar %s con "
            "`--rival`" % ("; ".join("%s, sustituto %s con tracción (%s)" % (
                nombre_fila(f), SUSTITUTOS[f["sustituto"]], registro.motivo_traccion(f)) for f in filas),
                nombre_fila(marcado), marcado["id"]))


def sesion_de(registro, ids, defecto):
    """La sesión que escribió el primero de esos hallazgos: la que hay que ajustar para completarlo."""
    for identificador in ids:
        hallazgo = registro.hallazgos.get(identificador)
        if hallazgo and hallazgo["linea"] in LINEAS:
            return LINEAS[hallazgo["linea"]][1]
    return defecto


def sesion_ajustable(numero_puerta, sesion, defecto):
    """La sesión, si se puede ajustar desde esa puerta (es anterior a ella); si no, la de defecto. Un hallazgo de la
    validación (sesión 3) que cita un diferenciador se completa, en la puerta 1, desde la 1g."""
    return sesion if sesion in SESION and "P%d" % numero_puerta in dependientes(sesion) else defecto


def texto_pasada(pasada):
    """'13 de 8 búsquedas y 10 de 5 lecturas en la reapertura 1'."""
    limites = pasada["presupuesto"]
    return "%d de %d búsquedas y %d de %d lecturas %s" % (
        pasada.get("busquedas", 0), limites["busquedas"], pasada.get("lecturas", 0), limites["lecturas"],
        "en la reapertura %d" % pasada["reapertura"] if pasada["reapertura"] else "en la primera pasada")


def registrar_pasada(producto, sesion, uso):
    """Anota lo que usó una línea en esta pasada (`cerrar --busquedas --lecturas`) con el presupuesto de la pasada: el
    original la primera vez y la mitad en cada reapertura (feedback #34). `uso` queda como la suma de las pasadas."""
    datos = producto["sesiones"].setdefault(sesion, {})
    reapertura = int(datos.get("reaperturas") or (1 if datos.get("reabierta") else 0))
    pasadas = datos.setdefault("pasadas", [])
    if not pasadas and datos.get("uso") and reapertura:  # un registro anterior: el uso de la primera pasada
        pasadas.append(dict(datos["uso"], reapertura=0, presupuesto=presupuesto_de(producto)))
    pasada = {"reapertura": reapertura, "busquedas": int(uso.get("busquedas") or 0),
              "lecturas": int(uso.get("lecturas") or 0), "fecha": ahora(),
              "presupuesto": presupuesto_reapertura(producto) if reapertura else presupuesto_de(producto)}
    pasadas[:] = [p for p in pasadas if p["reapertura"] != reapertura] + [pasada]
    datos["uso"] = {clave: sum(int(p.get(clave) or 0) for p in pasadas) for clave in ("busquedas", "lecturas")}
    return pasada


def pasadas_excedidas(producto):
    """Las pasadas de las líneas que se pasaron de su presupuesto: [(sesión, texto)]. Un registro anterior, sin
    pasadas, compara el total con el presupuesto original."""
    resultado = []
    for sesion in ("1a", "1b", "1c", "1d", "1e", "1g"):
        datos = producto["sesiones"].get(sesion) or {}
        pasadas = datos.get("pasadas") or []
        for pasada in pasadas:
            if any(pasada.get(clave, 0) > pasada["presupuesto"][clave] for clave in ("busquedas", "lecturas")):
                resultado.append((sesion, texto_pasada(pasada)))
        uso, limites = datos.get("uso") or {}, presupuesto_de(producto)
        if not pasadas and any(int(uso.get(clave) or 0) > limites[clave] for clave in ("busquedas", "lecturas")):
            resultado.append((sesion, "%d de %d búsquedas y %d de %d lecturas en total" % (
                int(uso.get("busquedas") or 0), limites["busquedas"], int(uso.get("lecturas") or 0),
                limites["lecturas"])))
    return resultado


def presupuesto_agotado(producto, registro, sesion="1g"):
    """Si la sesión ya se reabrió y usó el presupuesto de su reapertura (el 80 %, el punto en el que
    references/investigacion.md pide cerrar con lo que hay), el texto de lo usado; si no, None. Las búsquedas y las
    lecturas de cada pasada las anota `cerrar --busquedas --lecturas`. En un registro anterior, sin pasadas, cuenta el
    total contra el presupuesto original y, sin ese dato, las lecturas son las fuentes de la línea."""
    datos = producto["sesiones"].get(sesion) or {}
    linea = next((nombre for nombre, (_, de_sesion) in LINEAS.items() if de_sesion == sesion), None)
    if not linea or not (datos.get("reabierta") or datos.get("reaperturas")):
        return None
    reaperturas = [p for p in datos.get("pasadas") or [] if p["reapertura"]]
    if reaperturas:
        ultima = reaperturas[-1]
        if any(ultima.get(clave, 0) >= 0.8 * ultima["presupuesto"][clave] for clave in ("busquedas", "lecturas")):
            return texto_pasada(ultima)
        return None
    limites, uso = presupuesto_de(producto), datos.get("uso") or {}
    busquedas = int(uso.get("busquedas") or 0)
    lecturas = max(int(uso.get("lecturas") or 0), sum(1 for f in registro.fuentes.values() if f["linea"] == linea
                                                       and not f.get("extracto")))
    if busquedas >= 0.8 * limites["busquedas"] or lecturas >= 0.8 * limites["lecturas"]:
        return "%d de %d búsquedas y %d de %d lecturas" % (busquedas, limites["busquedas"], lecturas,
                                                           limites["lecturas"])
    return None


def reapertura_gastada(producto, sesion):
    """Si la sesión ya se reabrió y volvió a cerrar (gastó su reapertura), el texto de esa pasada; si no, None
    (feedback #55). La skill recomienda reabrir la 1c una sola vez: es la línea de la demanda, y otra pasada con las
    mismas herramientas no trae evidencia nueva. Una reapertura todavía abierta no cuenta: la puerta es provisional."""
    datos = producto["sesiones"].get(sesion) or {}
    if not (datos.get("reabierta") or datos.get("reaperturas")) or not cerrada(producto, sesion):
        return None
    reaperturas = [p for p in datos.get("pasadas") or [] if p["reapertura"]]
    if reaperturas:
        return texto_pasada(reaperturas[-1])
    veces = int(datos.get("reaperturas") or 1)
    return "reabierta %s" % ("una vez" if veces == 1 else "%d veces" % veces)


def refutados(registro, ids):
    """Los hallazgos con evidencia en contra que los refuta (feedback #55): tantas fuentes independientes y vigentes
    en contra (`hallazgo --en-contra`) como a favor, lo que los deja en confianza baja. Menos en contra los debilita,
    pero no los refuta."""
    resultado = []
    for identificador in ids:
        hallazgo = registro.hallazgos.get(identificador)
        if hallazgo:
            evaluacion = registro.evaluar(hallazgo)
            if evaluacion["contra"] and evaluacion["contra"] >= evaluacion["independientes"]:
                resultado.append(identificador)
    return resultado


def mas_cercano(registro, ids):
    """El hallazgo de esos que está más cerca de triangular (más confianza y más fuentes independientes), o None."""
    candidatos = [registro.hallazgos[i] for i in ids if i in registro.hallazgos]
    if not candidatos:
        return None
    return max(candidatos, key=lambda h: (registro.evaluar(h)["nivel"], registro.evaluar(h)["independientes"]))


def falta_triangular(registro, hallazgo):
    """'H-DEM-4 (faltan 2 fuentes independientes y vigentes, tiene 1 de 3; falta una fuente de tipo medido)'."""
    faltan = [re.sub(r" \((tiene \d+ de \d+)\)", r", \1", f) for f in registro.evaluar(hallazgo)["faltan"]
              if not f.startswith("o una sola fuente oficial")]
    return "%s (%s)" % (hallazgo["id"], "; ".join(faltan)) if faltan else hallazgo["id"]


def motivo_demanda(numero_puerta, producto, registro):
    """La demanda con confianza baja en la puerta 1 de una idea existente o variante (feedback #55): sin datos no es
    lo mismo que sin demanda. Es No viable solo con evidencia en contra (un hallazgo clave de demanda refutado) o si
    la 1c ya se reabrió y la demanda sigue baja; si no, se ajusta la 1c una vez, diciendo qué hallazgo triangular y con
    qué señal medida."""
    ids = sustento(registro)["demanda"] or []
    nivel = NIVELES[confianzas(registro)[0]["demanda"]]
    contra = refutados(registro, ids)
    if contra:
        return (True, "La demanda tiene evidencia en contra: %s %s tantas fuentes en contra como a favor (confianza "
                      "%s)" % (y_lista(contra), "tiene" if len(contra) == 1 else "tienen", nivel),
                "Evidencia nueva de demanda, medida y reciente, que pese más que la que está en contra", None, ids)
    gastada = reapertura_gastada(producto, "1c")
    if gastada:
        return (True, "La demanda sigue con confianza %s después de reabrir la 1c (%s): ajustarla otra vez con las "
                      "mismas herramientas no traería evidencia nueva" % (nivel, gastada),
                "Evidencia de demanda que no dependa de más búsquedas en la 1c: un navegador en el agente para las "
                "señales medidas (tendencias de búsqueda, descargas recientes) o datos propios", None, ids)
    # la confianza de la demanda es la del hallazgo clave más débil: hay que subir los que están en baja
    bajos = [registro.hallazgos[i] for i in ids if i in registro.hallazgos
             and registro.evaluar(registro.hallazgos[i])["nivel"] < 2]
    meses = producto["criterios"]["vigencia_meses"]
    if bajos:
        falta = "Triangular %s en la 1c con una señal medida y reciente de demanda (tendencias de búsqueda, descargas " \
                "o búsquedas de los últimos %s meses)" % ("; ".join(falta_triangular(registro, h) for h in bajos[:3]),
                                                          meses)
    else:
        falta = "Registrar en la 1c un hallazgo clave de demanda (`hallazgo --linea demanda --critico`) con %s " \
                "fuentes independientes y recientes, una de ellas medida (tendencias de búsqueda, descargas o " \
                "búsquedas de los últimos %s meses)" % (producto["criterios"]["fuentes_minimas"], meses)
    return (False, "La demanda actual tiene confianza %s en la primera pasada de la 1c: ningún hallazgo de demanda está "
                   "confirmado con señales recientes, pero no hay evidencia en contra (sin datos no es lo mismo que sin "
                   "demanda)" % nivel, falta, "1c", ids, True)


def motivo_problema(numero_puerta, producto, registro):
    """El problema de una idea nueva buscado y sin documentar (feedback #55), con la misma regla que la demanda: No
    viable solo con evidencia en contra (un hallazgo de peldaño 4 o 5 refutado) o si la sesión que lo completa ya se
    reabrió; si no, se ajusta esa sesión (la 1c, salvo que el hallazgo más cercano sea de otra línea) una vez."""
    minimas = producto["criterios"]["fuentes_minimas"]
    ids = [h["id"] for h in registro.hallazgos.values()
           if any(f["peldano"] in (4, 5) for f in registro.fuentes_de(h["fuentes"]))]
    contra = refutados(registro, ids)
    if contra:
        return (True, "El problema tiene evidencia en contra en los peldaños 4 y 5: %s %s tantas fuentes en contra "
                      "como a favor" % (y_lista(contra), "tiene" if len(contra) == 1 else "tienen"),
                "Evidencia nueva del problema, de peldaño 4 o 5, que pese más que la que está en contra", None, contra)
    cercano = mas_cercano(registro, ids)
    sesion = sesion_ajustable(numero_puerta, sesion_de(registro, [cercano["id"]] if cercano else [], "1c"), "1c")
    gastada = reapertura_gastada(producto, sesion)
    if gastada:
        return (True, "Se buscó el problema en los peldaños 4 y 5, también al reabrir la %s (%s), y ningún hallazgo "
                      "reúne %s fuentes independientes y vigentes (una de los últimos %s meses)" % (
                          sesion, gastada, minimas, producto["criterios"]["vigencia_meses"]),
                "El problema documentado con %s fuentes independientes y vigentes de peldaño 4 o 5, con evidencia que "
                "no dependa de más búsquedas en la %s (un navegador en el agente o datos propios)" % (minimas, sesion),
                None, ids)
    return (False, "Se buscó el problema en los peldaños 4 y 5 y ningún hallazgo reúne %s fuentes independientes y "
                   "vigentes (una de los últimos %s meses), pero no hay evidencia en contra: es la primera pasada" % (
                       minimas, producto["criterios"]["vigencia_meses"]),
            "Triangular %s en la %s con fuentes de peldaño 4 o 5" % (falta_triangular(registro, cercano), sesion)
            if cercano else "Documentar el problema en la %s con %s fuentes independientes y vigentes de peldaño 4 o 5"
            % (sesion, minimas), sesion, ids, True)


def nombrados(registro, filas):
    """Los hallazgos que nombran a esas filas de la matriz (por ejemplo, al sustituto que ya resuelve la necesidad)."""
    ids = {fila["id"] for fila in filas}
    return [h["id"] for h in registro.hallazgos.values() if ids & set(registro.referencias(h)[0])]


def presupuesto_usado(producto, registro, sesion="1g"):
    """Si la última pasada de la línea (la primera o una reapertura) llegó al 80 % de sus búsquedas o de sus lecturas,
    el punto en que references/investigacion.md pide cerrar con lo que hay, el texto de lo usado; si no, None. Sin
    pasadas registradas, cuenta el total contra el presupuesto original y, sin ese dato, las lecturas son las fuentes
    de la línea."""
    datos = producto["sesiones"].get(sesion) or {}
    pasadas = datos.get("pasadas") or []
    if pasadas:
        ultima = pasadas[-1]
        if any(ultima.get(clave, 0) >= 0.8 * ultima["presupuesto"][clave] for clave in ("busquedas", "lecturas")):
            return texto_pasada(ultima)
        return None
    linea = (lineas_de([sesion]) or [None])[0]
    limites, uso = presupuesto_de(producto), datos.get("uso") or {}
    busquedas = int(uso.get("busquedas") or 0)
    lecturas = max(int(uso.get("lecturas") or 0), sum(1 for f in registro.fuentes.values() if f["linea"] == linea
                                                       and not f.get("extracto")))
    if busquedas >= 0.8 * limites["busquedas"] or lecturas >= 0.8 * limites["lecturas"]:
        return "%d de %d búsquedas y %d de %d lecturas" % (busquedas, limites["busquedas"], lecturas,
                                                           limites["lecturas"])
    return None


def hallazgos_frente(registro, rivales):
    """Los hallazgos de las comparaciones (`frente`) de cada diferenciador con esos rivales, los más citados primero:
    son los que muestran si alguno los supera."""
    cuenta = {}
    for diferenciador in registro.diferenciadores.values():
        for rival in rivales:
            for identificador in (registro.comparacion(diferenciador, rival) or {}).get("hallazgos", []):
                cuenta[identificador] = cuenta.get(identificador, 0) + 1
    return [i for i, _ in sorted(cuenta.items(), key=lambda par: -par[1]) if i in registro.hallazgos]


def motivo_sin_principal(numero_puerta, producto, registro):
    """Lo que dice del veredicto que no haya un diferenciador principal, igual en las tres puertas (feedback #44):
    con uno viable, elegirlo (ajustar 1g, sin búsquedas); con uno viable con confianza baja, confirmarlo en la 1g; sin
    ninguno, ajustar la 1g solo si tiene una propuesta pendiente o presupuesto para buscarlo, y si no, No viable."""
    viables, bajas, rivales = registro.viables(), registro.con_confianza_baja(), registro.rivales()
    ids = hallazgos_frente(registro, rivales) + [i for i in nombrados(registro, rivales)]
    ids = list(dict.fromkeys(ids))
    if viables:
        nombres = y_lista(d["id"] for d in viables)
        return (False, "No hay un diferenciador principal elegido, pero %s %s viable%s" % (
            nombres, "es" if len(viables) == 1 else "son", "" if len(viables) == 1 else "s"),
            "Elegir el principal entre los viables (%s) en la 1g" % nombres, "1g", [], False)
    if bajas:
        nombres = y_lista(d["id"] for d in bajas)
        return (False, "No hay un diferenciador principal: %s %s viable%s con confianza baja" % (
            nombres, "es" if len(bajas) == 1 else "son", "" if len(bajas) == 1 else "s"),
            "Confirmar los hallazgos de %s en la 1g y elegirlo como principal" % nombres, "1g", ids, True)
    frente = " frente %s" % a_los_rivales(rivales, "ni") if rivales else ""
    propuestas = [p["id"] for p in propuestas_de(producto, numero_puerta) if p.get("ajustar") == "1g"]
    if propuestas:
        return (False, "No hay un diferenciador principal: ninguno es viable%s, pero %s puede dar uno en la 1g" % (
            frente, y_lista(propuestas)), "Aplicar %s al ajustar la 1g y elegir un principal viable" % y_lista(
            propuestas), "1g", ids, True)
    usado = presupuesto_usado(producto, registro, "1g")
    if not usado:
        return (False, "No hay un diferenciador principal: ninguno es viable%s, y la 1g cerró sin usar su "
                       "presupuesto" % frente, "Buscar en la 1g un diferenciador que %s con hallazgos confirmados" % (
                           "supere %s" % a_los_rivales(rivales) if rivales else "dé una razón para elegir la app"),
                "1g", ids, True)
    return (True, "No hay un diferenciador principal: ninguno es viable%s, y la 1g ya usó su presupuesto (%s)" % (
        frente, usado), "Un diferenciador viable%s, con evidencia que no dependa de más búsquedas en la 1g (un "
                        "navegador en el agente, un CSV de reseñas que aportes o datos propios)" % (
                            " que supere %s" % a_los_rivales(rivales) if rivales else ""), None, ids)


def criterios_sin_aceptacion(mvp):
    """Las funcionalidades del MVP sin criterios de aceptación en sus historias (feedback #44)."""
    return [f["id"] for f in mvp if not f.get("aceptacion")]


# Viable para probar (feedback #47): la prueba de elección casi nunca está en la web antes de lanzar (la evidencia
# muestra el dolor, no la elección). Si un diferenciador supera al rival con el dolor triangulado, construirlo es
# barato, no hay bloqueo de políticas y la demanda tiene confianza media o alta, la puerta 1 recomienda seguir con un
# criterio de descarte después del lanzamiento, en vez de pedir una prueba que la investigación no puede dar.
CRITERIOS_ELECCION = ("diferenciador", "rival", "principal")  # los de la puerta 1 que la prueba de elección decide


def candidatos_para_probar(carpeta, producto, registro, filas=None, con_demanda=True):
    """Los diferenciadores para probar: superan a cada rival con el dolor triangulado (`Registro.para_probar`), no
    tienen prueba de elección y ninguna hipótesis de 03-validacion.md sobre ellos quedó refutada. Vacío si no hay
    rivales, si alguno viable ya tiene la prueba de elección (la puerta puede dar Viable) o si falta alguna de las
    condiciones de la idea: la demanda con confianza media o alta y ningún bloqueo de políticas. Con
    con_demanda=False, los que serían candidatos con la demanda en media o alta (lo que falta es ajustar la 1c)."""
    if not registro.rivales() or condiciones_probar(producto, registro, con_demanda):
        return []
    filas = (hipotesis(carpeta, registro) or []) if filas is None else filas
    if any(registro.eleccion(d, filas)[0] for d in registro.viables()):
        return []
    refutados = {f["diferenciador"] for f in filas if f["veredicto"] == "refutada"}
    return [d for d in registro.diferenciadores.values() if registro.para_probar(d) and d["id"] not in refutados]


def condiciones_probar(producto, registro, con_demanda=True):
    """Lo que le falta a la idea para que un diferenciador sin prueba de elección se pueda probar: [texto]. Construirlo
    barato ya lo pide el criterio 4 de viabilidad (sus semanas caben en el presupuesto)."""
    faltan = []
    demanda = confianzas(registro)[0]["demanda"] or 0
    if demanda < 2 and con_demanda:
        faltan.append("la demanda tiene confianza %s" % NIVELES[demanda])
    bloqueos = registro.bloqueos(objetivo_de(producto))
    if bloqueos:
        faltan.append("%s nombra o rechaza la categoría" % ", ".join(sorted(bloqueos)))
    return faltan


def criterio_descarte(producto, registro, diferenciador, filas=None):
    """El criterio de descarte después del lanzamiento de una idea Viable para probar: la hipótesis más riesgosa (la
    gente elige la app por ese diferenciador frente a los rivales) y cómo se mide. El umbral lo fija la sesión 3 en la
    hipótesis más riesgosa de 03-validacion.md, con su métrica: {diferenciador, rivales, hipotesis, dias, metricas,
    faltas, texto}."""
    rivales = registro.rivales()
    dias = int(float(producto["criterios"].get("dias_descarte") or CRITERIOS_DEFECTO["dias_descarte"]))
    faltas = registro.eleccion(diferenciador, filas or [])[1]
    hipotesis_ = "la gente elige la app por %s frente %s" % (diferenciador["id"], a_los_rivales(rivales))
    metricas = ["instalaciones orgánicas", "retención"]
    texto = ("la hipótesis más riesgosa es que %s. El MVP la pone a prueba: a los %s del lanzamiento se miden las %s y "
             "la %s; si no llegan al umbral que fija la sesión 3 (la hipótesis más riesgosa de 03-validacion.md, con "
             "su métrica y su umbral), se descarta la idea o se cambia el diferenciador" % (
                 hipotesis_, plural(dias, "día"), metricas[0], metricas[1]))
    return {"diferenciador": diferenciador["id"], "rivales": [r["id"] for r in rivales], "hipotesis": hipotesis_,
            "dias": dias, "metricas": metricas, "faltas": faltas, "texto": texto}


def criterio_descarte_vigente(carpeta):
    """El criterio de descarte de una idea que pasó la puerta 1 como Viable para probar: el de la decisión vigente de
    seguir en la puerta 1, o None. Las puertas 2 y 3 no vuelven a pedir la prueba de elección: piden la hipótesis
    más riesgosa con su métrica y su umbral, y que el MVP la ponga a prueba."""
    decision = vigente(decisiones(carpeta), 1)
    if decision and decision["decision"] == "seguir" and (
            decision.get("recomendacion") or {}).get("veredicto") == "probar":
        return decision.get("criterio_descarte") or {"texto": "la prueba de elección se mide después del lanzamiento"}
    return None


def motivos_criterio(numero_puerta, criterio, producto, registro):
    """Lo que un criterio que no se cumple dice del veredicto: (fatal, razón, qué lo cambiaría, sesión, hallazgos).
    Fatal es lo que lleva a No viable; lo demás se puede completar ajustando una sesión."""
    clave, detalle = criterio["clave"], llano(criterio["detalle"])
    criterios = producto["criterios"]
    puntaje = producto.get("puntaje")
    principal = registro.principal()
    viables, bajas = registro.viables(), registro.con_confianza_baja()
    rivales = registro.rivales()
    if clave == "puntaje":
        if not puntaje:
            return False, "Falta el puntaje de la síntesis", "Registrar el puntaje en la síntesis (sesión 1f)", "1f", []
        minimo = int(criterios["puntaje_minimo_nueva" if tipo_de(producto) == "nueva" else "puntaje_minimo"])
        modelos = puntajes_por_modelo(producto, registro)
        base = modelos[0]
        razon = "El puntaje es %d/25, bajo el mínimo de %d" % (base["vigente"]["total"], minimo)
        if base["vigente"]["incoherencias"]:
            razon = "Con las reglas de hoy el puntaje es %s, bajo el mínimo de %d: %s" % (
                texto_puntaje(base), minimo, "; ".join(base["vigente"]["incoherencias"]))
        if len(modelos) > 1:
            razon += " (con cada modelo de monetización: %s)" % "; ".join(
                "%s %s" % (m["modelo"], texto_puntaje(m)) for m in modelos)
        return (True, razon, "Evidencia nueva que suba el puntaje a %d/25 o más%s" % (
            minimo, " con las reglas de hoy" if base["vigente"]["incoherencias"] else ""), None, [])
    if clave == "demanda":
        return motivo_demanda(numero_puerta, producto, registro)
    if clave == "problema":
        conteo = conteo_peldanos(registro)
        if conteo[4]["no_buscado"] and conteo[5]["no_buscado"]:
            return (False, "Nadie buscó el problema en los peldaños 4 y 5: es evidencia no buscada, no evidencia "
                           "buscada y no encontrada", "Buscar el problema en los peldaños 4 y 5 (cómo se resuelve hoy "
                                                      "y la necesidad de fondo) y registrar también lo que no "
                                                      "aparezca (`vacio --peldano`)", "1c", [])
        return motivo_problema(numero_puerta, producto, registro)
    if clave == "analogos":
        return (False, "Faltan análogos con tracción (%s)" % detalle,
                "Análogos con tracción registrados en la matriz (sesión 1a)", "1a", [])
    if clave == "intentos":
        if not producto.get("intentos"):
            return (False, "Falta buscar si alguien ya lo intentó", "La búsqueda de intentos anteriores registrada",
                    "1a", [])
        return (True, "Alguien ya lo probó y fracasó por falta de demanda (%s)" % detalle,
                "Evidencia de que el intento anterior fracasó por otra razón que esta idea no repite", None, [])
    if clave in ("diferenciador", "rival"):
        ids = nombrados(registro, rivales) + (principal or {}).get("hallazgos", [])
        if bajas:  # todos los que deciden el veredicto, con su estado (feedback #25)
            faltan = list(dict.fromkeys(i for d in bajas for i, _ in registro.sin_triangular(d)))
            superan = [d for d in bajas if rivales and registro.frente_al_rival(d)[0]]
            nombres_bajas = y_lista(d["id"] for d in bajas)
            razon = "%s %s, pero %s con confianza baja: %s sin triangular" % (
                nombres_bajas, ("%s %s" % ("supera" if len(bajas) == 1 else "superan", a_los_rivales(rivales)))
                if len(superan) == len(bajas) else "cumple%s los criterios de un diferenciador" % (
                    "n" if len(bajas) > 1 else ""), "es viable" if len(bajas) == 1 else "son viables", y_lista(faltan))
            otros = [d for d in registro.diferenciadores.values() if d not in bajas and d is not principal
                     and registro.estado(d) in ("paridad", "no")]
            if otros:
                razon += "; %s" % texto_estados(registro, otros)
            return (False, razon, "Triangular los hallazgos de %s con 3 fuentes vigentes (una reciente)"
                    % nombres_bajas, sesion_ajustable(numero_puerta, sesion_de(registro, faltan, "1g"), "1g"), faltan)
        if viables and registro.rival_pendiente():  # `competidor --rival` no pide reabrir 1a: `frente` es de la 1g
            return (False, "Falta marcar la alternativa gratis más fuerte, el rival que cada diferenciador tiene que "
                           "superar", "Marcarla en la matriz (`competidor … --rival`, sin reabrir 1a) o decir que no "
                                      "la hay (`competidor --sin-rival`), y comparar cada diferenciador con ella en la "
                                      "1g (`frente`)", "1g", [])
        if rivales:  # el rival y el sustituto, cada uno por su nombre (feedback #40)
            return (True, "Ningún diferenciador supera %s con hallazgos triangulados%s" % (
                a_los_rivales(rivales, "ni"), ": %s" % texto_estados(registro, registro.diferenciadores.values())
                if registro.diferenciadores else ""),
                    "Un diferenciador con evidencia confirmada de algo que no %s %s" % (
                        "dan ni" if len(partes_rivales(rivales)) > 1 else "da", los_rivales(rivales, "ni")),
                    None, ids)
        return (True, "No hay ningún diferenciador viable: nada da una razón para elegir esta app",
                "Un diferenciador con un dolor o un pedido confirmado en 2 competidores o más", None, ids)
    if clave == "principal":
        if not principal:
            return motivo_sin_principal(numero_puerta, producto, registro)
        faltan = [i for i, _ in registro.sin_triangular(principal)]
        otros = [d["id"] for d in viables if d["id"] != principal["id"]]
        frente = registro.frente_al_rival(principal) if rivales else (True, "")
        if not frente[0]:
            if registro.iguala(principal):
                razon = "El principal (%s) iguala %s: no viable (paridad, básico en Kano), no es una razón para " \
                        "elegir la app" % (principal["id"], a_los_rivales(registro.iguala(principal)))
            else:
                razon = "El principal (%s) no supera a la alternativa gratis más fuerte (%s)" % (
                    principal["id"], llano(frente[1].replace("Frente al rival: ", "")))
            if otros:
                return (False, razon, "Elegir como principal un diferenciador viable que la supere (%s)" % ", ".join(
                    otros), "1g", list(principal.get("hallazgos", [])), False)
            candidatos = [d["id"] for d in registro.diferenciadores.values() if d["id"] != principal["id"]
                          and registro.frente_al_rival(d)[0]]
            return (False, razon, "Un principal que supere %s con hallazgos confirmados%s" % (
                a_los_rivales(rivales), " (%s lo supera%s, sin confirmar)" % (
                    ", ".join(candidatos), "n" if len(candidatos) > 1 else "") if candidatos else ""), "1g",
                    list(principal.get("hallazgos", [])))
        if otros:
            return (False, "Los hallazgos del principal (%s) no están confirmados, pero %s sí es viable" % (
                principal["id"], ", ".join(otros)), "Elegir como principal un diferenciador viable (%s)"
                % ", ".join(otros), "1g", faltan, False)
        return (False, "Los hallazgos del principal (%s) no están confirmados (%s)" % (principal["id"], ", ".join(
            faltan)), "Confirmar esos hallazgos con 3 fuentes recientes",
                sesion_ajustable(numero_puerta, sesion_de(registro, faltan, "1g"), "1g"), faltan)
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
        if "versión anterior" in detalle:
            return (False, "Los escenarios se calcularon con una regla anterior (%s)" % detalle,
                    "Volver a correr los escenarios (sesión 2)", "2", [])
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
            return motivo_sin_principal(numero_puerta, producto, registro)
        otros = [d["id"] for d in viables if d["id"] != principal["id"]]
        ids = list(principal.get("hallazgos", []))
        if otros:
            return (False, "El principal (%s) no sobrevive al abogado del diablo, pero %s sí es viable" % (
                principal["id"], ", ".join(otros)), "Llevar %s a principal (1g)" % ", ".join(otros), "1g", ids, False)
        return (True, "El diferenciador principal (%s) no sobrevive al abogado del diablo y no hay otro viable (%s)" % (
            principal["id"], detalle.split(": ", 1)[-1]),
                "Un diferenciador viable que quede sostenido con confianza media o alta", None, ids)
    if clave == "principal_mvp":  # sin principal, lo mismo que en las puertas 1 y 2; con él, se completa el PRD (#44)
        if not principal:
            return motivo_sin_principal(numero_puerta, producto, registro)
        return (False, "El diferenciador principal (%s) no está en ninguna funcionalidad del MVP" % principal["id"],
                "Llevar %s a una funcionalidad del MVP en el PRD (sesión 4)" % principal["id"], "4", [])
    if clave == "aceptacion":
        return (False, "Faltan los criterios de aceptación de %s" % detalle.split("sin criterios: ")[-1],
                "Escribir los criterios de aceptación (dado …, cuando …, entonces …) de cada funcionalidad del MVP en "
                "el PRD (sesión 4)", "4", [])
    if clave == "checklist" and "bloqueos" in detalle:
        return (True, "El checklist de políticas tiene bloqueos (%s)" % detalle.replace("bloqueos: ", ""),
                "Un MVP que evite esos bloqueos, con su requisito resuelto", None, [])
    return False, "%s: %s" % (criterio["texto"], detalle), "Completarlo en el PRD (sesión 4)", "4", []


def veredicto(numero_puerta, carpeta, producto, registro, evaluados=None):
    """El veredicto de la skill en una puerta, con reglas fijas: No viable (recomienda descartar), Viable con reservas
    (recomienda ajustar una sesión) o Viable (recomienda seguir), con 1 a 3 razones y qué lo cambiaría."""
    evaluados = evaluados if evaluados is not None else evaluar_puerta(numero_puerta, carpeta, producto, registro)
    # Líneas que cerraron con otro tipo de idea y no subieron (o bajaron) por la escalera: la puerta no recomienda
    # descartar por evidencia que no buscaron, sino ajustarlas (feedback #28).
    revisar = sorted(a_revisar_por_tipo(producto, registro) if numero_puerta == 1 else [],
                     key=lambda r: ("1c", "1b", "1d", "1g").index(r[0]))
    sin_buscar = [s for s, _, _ in revisar]
    # cada motivo: (razón, qué lo cambiaría, sesión que lo completa, si completarlo pide investigar más)
    fatales, ajustes, hallazgos = [], [], []
    # Viable para probar (feedback #47): los criterios que solo fallan por la prueba de elección se difieren al
    # lanzamiento si un diferenciador supera al rival con el dolor triangulado; si no es el principal, elegirlo en la 1g
    # no pide búsquedas.
    filas_hipotesis = hipotesis(carpeta, registro) or [] if numero_puerta == 1 else []
    probar = candidatos_para_probar(carpeta, producto, registro, filas_hipotesis) if numero_puerta == 1 else []
    principal_probar = registro.principal() if registro.principal() in probar else None
    diferidos = []
    for sesion, antes, peldanos in revisar:
        ajustes.append(("La sesión %s cerró %s y la idea es %s: no buscó en los peldaños %s, así que esa evidencia no "
                        "se buscó (no es evidencia en contra)" % (sesion, "como idea %s" % antes if antes else
                                                                  "sin tipo registrado", tipo_de(producto),
                                                                  y_lista(str(n) for n in peldanos)),
                        "Ajustar la sesión %s con el tipo de hoy (%s)" % (sesion, tipo_de(producto)), sesion, True))
    if probar and not principal_probar:
        principal = registro.principal()
        ajustes.append(("%s %s %s con el dolor triangulado (%s para probar), pero %s" % (
            y_lista(d["id"] for d in probar), "supera" if len(probar) == 1 else "superan", a_los_rivales(
                registro.rivales()), "viable" if len(probar) == 1 else "viables",
            ("el principal (%s) solo %s: no viable (paridad)" % (principal["id"], "lo iguala" if len(
                registro.rivales()) == 1 else "iguala a los rivales")) if principal and registro.iguala(principal)
            else "el principal (%s) no supera %s con el dolor triangulado" % (principal["id"], a_los_rivales(
                registro.rivales())) if principal else "no hay un diferenciador principal elegido"),
            "Elegir como principal %s en la 1g (no pide búsquedas): el veredicto pasaría a Viable para probar"
            % y_lista((d["id"] for d in probar), "o"), "1g", False))
        hallazgos += [i for d in probar for i in d.get("hallazgos", [])]
    for criterio in evaluados:
        if not criterio["cumple"] and probar and criterio["clave"] in CRITERIOS_ELECCION:
            if criterio["clave"] != "principal" or principal_probar:
                diferidos.append(criterio["clave"])  # se prueba después del lanzamiento: el criterio de descarte
            continue  # sin el principal entre los candidatos, el ajuste de arriba lo resuelve
        if not criterio["cumple"]:
            fatal, razon, cambiaria, sesion, ids, *resto = motivos_criterio(numero_puerta, criterio, producto,
                                                                            registro)
            depende = [s for s in sin_buscar if s in DEPENDE_CRITERIO.get(criterio["clave"], ())]
            if fatal and depende:  # no se descarta por un criterio cuya evidencia no se buscó
                fatal, sesion = False, depende[0]
            (fatales if fatal else ajustes).append((razon, cambiaria, sesion, resto[0] if resto else True))
            hallazgos += ids
    vigente_ = puntaje_vigente(producto, registro) if numero_puerta == 1 else None
    if numero_puerta == 1 and not fatales:
        revisar_rival = rival_a_revisar(registro)
        if revisar_rival:
            ajustes.append(("Revisar el rival: " + texto_rival_a_revisar(registro, revisar_rival),
                            "Confirmar o cambiar el rival y comparar cada diferenciador con él", "1g", False))
    rivales = registro.rivales() if numero_puerta == 1 else []
    if rivales and not fatales and not probar:  # superar al rival no alcanza si nada prueba que eso hace elegir la app
        filas = filas_hipotesis
        candidatos = [d for d in registro.diferenciadores.values() if registro.frente_al_rival(d)[0]]
        if candidatos and not any(registro.eleccion(d, filas)[0] for d in registro.viables()):
            principal = registro.principal()
            elegido = principal if principal in candidatos else candidatos[0]
            _, faltas, debiles = registro.eleccion(elegido, filas)
            ajustes.append(("%s supera %s, pero sin prueba de que eso haga elegir la app (%s)" % (
                elegido["id"], a_los_rivales(rivales), "; ".join(faltas)),
                "Un hallazgo triangulado y en confianza alta que muestre que la gente elige por %s frente %s, o "
                "un vector todavía sin investigar" % (elegido["id"], a_los_rivales(rivales)),
                sesion_ajustable(1, sesion_de(registro, debiles, "1g"), "1g"), True))
            hallazgos += debiles
    if numero_puerta == 1 and producto.get("puntaje") and not fatales:
        por_criterio, global_ = confianzas(registro)
        if global_ < 2:
            debiles = sorted((nivel, c) for c, nivel in por_criterio.items() if nivel is not None and nivel < 2)
            criterio = debiles[0][1]
            ids = sustento(registro)[criterio] or []
            sesion = SESION_CRITERIO[criterio]
            if criterio == "diferenciacion" and registro.principal():
                sesion = sesion_ajustable(1, sesion_de(registro, [i for i, _ in registro.sin_triangular(
                    registro.principal())], "1g"), "1g")
            ajustes.append(("La confianza global es baja: %s se apoya%s en evidencia sin confirmar" % (
                ", ".join(NOMBRES_CRITERIO[c] for _, c in debiles), "n" if len(debiles) > 1 else ""),
                "Confirmar con 3 fuentes recientes los hallazgos de %s" % NOMBRES_CRITERIO[criterio], sesion, True))
            hallazgos += ids
    if not fatales:
        for propuesta in propuestas_de(producto, numero_puerta):
            sesion = propuesta.get("ajustar")
            if sesion and not vacios_de_sesion(producto, registro, sesion):  # se puede cerrar
                ajustes.append(("Hay una propuesta pendiente (%s): %s" % (propuesta["id"], llano(propuesta["texto"])),
                                "Aplicarla al ajustar la sesión %s" % sesion, sesion, False))
    # La 1g que ya se reabrió y usó su presupuesto, y la 1c que ya se reabrió (feedback #55), no se recomiendan otra
    # vez para buscar más evidencia: si no queda ningún otro ajuste que lo resuelva, el veredicto es No viable.
    agotadas = {s: t for s, t in (("1g", presupuesto_agotado(producto, registro, "1g")),
                                  ("1c", reapertura_gastada(producto, "1c"))) if t}
    sin_salida = [a for a in ajustes if a[2] in agotadas and a[3]]
    if not fatales and sin_salida:
        posibles = [a for a in ajustes if a not in sin_salida]
        if posibles:
            ajustes = posibles + sin_salida
        else:
            sesiones_ = list(dict.fromkeys(a[2] for a in sin_salida))
            fatales = sin_salida[:MAXIMO_RAZONES - len(sesiones_)] + [(
                "La sesión %s ya se reabrió%s (%s): ajustarla otra vez no traería evidencia nueva" % (
                    s, " y usó su presupuesto" if s == "1g" else "", agotadas[s]),
                "Evidencia que no dependa de más búsquedas en la %s: un navegador en el agente, un CSV de reseñas que "
                "aportes o datos propios" % s, None, True) for s in sesiones_]
            ajustes = []
    descarte = None
    if fatales:
        nivel, elegidas, sesion = "no", fatales + ajustes, None
        cambios = fatales
    elif ajustes:
        nivel, elegidas, sesion = "reservas", ajustes, ajustes[0][2]
        cambios = ajustes
    elif principal_probar:
        nivel, sesion = "probar", None
        descarte = criterio_descarte(producto, registro, principal_probar, filas_hipotesis)
        global_ = confianzas(registro)[1]
        demanda = confianzas(registro)[0]["demanda"] or 0
        elegidas = [("%s supera %s con el dolor confirmado (%s), pero falta la prueba de que eso haga elegir la app "
                     "(%s): esa prueba casi nunca está en la web antes de lanzar, así que se mide después" % (
                         principal_probar["id"], a_los_rivales(rivales), y_lista(principal_probar.get("hallazgos", [])),
                         "; ".join(descarte["faltas"]) or "sin un hallazgo de elección"), None, None, False),
                    ("Construirlo cabe en el presupuesto (%s de %s), la demanda tiene confianza %s y no hay bloqueo de "
                     "políticas" % (numero(float(principal_probar.get("semanas") or 0)), plural(float(
                         producto["criterios"].get("presupuesto_semanas") or 0), "semana"), NIVELES[demanda]),
                     None, None, False),
                    ("La evidencia que la sostiene tiene confianza %s" % NIVELES[global_], None, None, False)]
        cambios = [(None, "Que a los %s del lanzamiento no se cumpla el criterio de descarte (se descarta la idea o se "
                          "cambia el diferenciador)" % plural(descarte["dias"], "día"), None, False),
                   (None, "Un hallazgo triangulado y en confianza alta de que la gente elige la app por %s frente %s "
                          "(pasaría a Viable)" % (principal_probar["id"], a_los_rivales(rivales)), None, False),
                   (None, "Evidencia en contra del dolor o una hipótesis sobre %s refutada (pasaría a No viable)"
                    % principal_probar["id"], None, False)]
        hallazgos += registro.hallazgos_de(principal_probar) + (sustento(registro)["demanda"] or [])
    else:
        nivel, sesion = "viable", None
        global_ = confianzas(registro)[1]
        elegidas = [("Cumple los %s de la puerta %d" % (plural(len(evaluados), "criterio"), numero_puerta),
                     {1: "Que un hallazgo clave pierda vigencia o aparezca evidencia en contra y la confianza global "
                         "baje a baja (pasaría a Viable con reservas)",
                      2: "Que la validación refute una hipótesis crítica (pasaría a No viable)",
                      3: "Que el MVP deje de caber en el presupuesto o pierda la trazabilidad (pasaría a Viable con "
                         "reservas)"}[numero_puerta], None, False)]
        if numero_puerta == 1:
            elegidas.append(("La evidencia que la sostiene tiene confianza %s" % NIVELES[global_], None, None, False))
        principal = registro.principal()
        if principal and numero_puerta in (1, 2):
            elegidas.append(("El diferenciador principal (%s) es viable%s" % (principal["id"], (
                " y supera %s, con prueba de elección" % a_los_rivales(rivales)) if rivales else ""),
                None, None, False))
            hallazgos += registro.hallazgos_de(principal)
        hallazgos += sustento(registro)["demanda"] or []
        cambios = elegidas
    exigido = modelo_exigido(producto, registro) if numero_puerta == 1 else None
    if exigido and nivel != "no":  # una decisión de modelo que todavía se puede cambiar no es un defecto (#29)
        elegidas.insert(0, ("El puntaje alcanza el mínimo solo con el modelo %s (%s; con %s, %s): la sesión 2 tiene que "
                            "elegirlo" % (exigido["modelo"], texto_puntaje(exigido),
                                          nombre_modelo(producto["puntaje"]), texto_puntaje(
                                              puntajes_por_modelo(producto, registro)[0])), None, None, False))
    razones = [r for r, _, _, _ in elegidas][:MAXIMO_RAZONES]
    cambiaria = list(dict.fromkeys(c for _, c, _, _ in cambios if c))[:MAXIMO_RAZONES]
    if nivel == "reservas":
        if not any("Viable para probar" in c for c in cambiaria):
            despues = probar or (numero_puerta == 1 and candidatos_para_probar(  # con la demanda ajustada (#55)
                carpeta, producto, registro, filas_hipotesis, con_demanda=False))
            cambiaria.append("Con eso, el veredicto pasaría a %s" % ("Viable para probar" if despues else "Viable"))
        herramienta = vacios_de_sesion(producto, registro, sesion)  # solo los de la línea dueña (feedback #44)
        if herramienta:
            cambiaria.append("%s: antes de ajustarla, dale al agente un navegador o aporta un CSV de reseñas" % (
                texto_vacios_sesion(sesion, herramienta)))
    abiertas = [s for s in DEPENDE["P%d" % numero_puerta] if not cerrada(producto, s)]
    return {"puerta": numero_puerta, "nivel": nivel, "titulo": VEREDICTOS[nivel]["titulo"],
            "recomienda": VEREDICTOS[nivel]["recomienda"], "sesion": sesion, "razones": razones,
            "cambiaria": cambiaria, "provisional": abiertas, "hallazgos": list(dict.fromkeys(hallazgos)),
            "incoherencias": (vigente_ or {}).get("incoherencias", []),
            "diferidos": diferidos if nivel in ("probar", "reservas") else [], "descarte": descarte}


def primera_mayuscula(texto):
    return texto[:1].upper() + texto[1:]


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
    if resultado.get("descarte"):
        lineas += ["Criterio de descarte después del lanzamiento (queda registrado al seguir):",
                   "  · %s." % primera_mayuscula(resultado["descarte"]["texto"])]
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


def opciones_decision(numero_puerta, carpeta, producto, resultado):
    """Los comandos de la decisión, para la terminal del usuario: primero el recomendado; los que van en contra de la
    recomendación (también ajustar otra sesión) llevan --motivo. Una propuesta con sesión trae su Ajustar listo:
    [{nombre, comando, recomendado}]."""
    recomienda = resultado["recomienda"]
    contra = ' --motivo "<por qué decides distinto de la recomendación>"'

    def comando(tipo, resto, sesion=None):
        distinta = tipo == "ajustar" and recomienda == "ajustar" and sesion != resultado["sesion"]
        return orden("decidir --puerta %d %s%s" % (numero_puerta, resto, contra if tipo != recomienda or distinta
                                                   else ""), carpeta)

    motivo = motivo_descarte(resultado)
    recomendado = {"seguir": ("Seguir", "--seguir"),
                   "ajustar": ("Ajustar %s" % resultado["sesion"], "--ajustar %s" % resultado["sesion"]),
                   "descartar": ("Descartar", "--descartar %s" % shlex.quote(motivo))}[recomienda]
    opciones = [{"nombre": recomendado[0], "recomendado": True,
                 "comando": comando(recomienda, recomendado[1], resultado["sesion"])}]
    if recomienda != "seguir":
        opciones.append({"nombre": "Seguir", "recomendado": False, "comando": comando("seguir", "--seguir")})
    sesiones = [p["ajustar"] for p in propuestas_de(producto, numero_puerta) if p.get("ajustar")]
    for sesion in dict.fromkeys(sesiones):
        if not (recomienda == "ajustar" and sesion == resultado["sesion"]):
            opciones.append({"nombre": "Ajustar %s" % sesion, "recomendado": False,
                             "comando": comando("ajustar", "--ajustar %s" % sesion, sesion)})
    opciones.append({"nombre": "Ajustar", "recomendado": False, "comando": comando("ajustar", "--ajustar <sesión>")})
    if recomienda != "descartar":
        opciones.append({"nombre": "Descartar", "recomendado": False,
                         "comando": comando("descartar", "--descartar \"<motivo>\"")})
    return opciones


def comandos_decision(numero_puerta, carpeta, producto, resultado):
    """Los comandos de la decisión, formateados para la salida de `puerta` y de `siguiente`."""
    lineas = []
    for opcion in opciones_decision(numero_puerta, carpeta, producto, resultado):
        if opcion["recomendado"]:
            lineas.append("   ★ Recomendado · %s: %s" % (opcion["nombre"], opcion["comando"]))
        else:
            lineas.append("   %s %s" % ((opcion["nombre"] + ":").ljust(10), opcion["comando"]))
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
        faltan.append("%s todavía tiene %s de plantilla (`%s…>`)" % (
            datos["archivo"], plural(texto.count(PENDIENTE), "texto"), PENDIENTE))
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
        if not tipo_de(producto):
            faltan.append("falta el tipo de idea provisional, para que cada línea sepa desde el inicio si trabaja por "
                          "analogía: `tipo --existente|--variante|--nueva --provisional --motivo \"<lo que dice el "
                          "triaje>\"` (la sesión 1a lo confirma)")
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
        if not tipo_de(producto) or tipo_provisional(producto):
            faltan.append("falta confirmar el tipo de idea (`tipo --existente|--variante|--nueva --motivo …`, sin "
                          "--provisional)%s" % (": el provisional de la sesión 0 es %s" % tipo_de(producto)
                                                if tipo_de(producto) else ""))
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
        if tipo_de(producto) in ("existente", "variante") and registro.rival_pendiente():
            faltan.append("falta marcar la alternativa gratis más fuerte, el rival que cada diferenciador tiene que "
                          "superar (sea sustituto o competidor directo): `competidor --nombre <…> … --rival`, o "
                          "`competidor --sin-rival \"<por qué no hay ninguna gratis que resuelva la necesidad>\"`")
    if sesion == "1g":
        for diferenciador in registro.diferenciadores.values():
            for rival in registro.rivales():
                if not registro.comparacion(diferenciador, rival):
                    faltan.append("%s sin comparar con %s, el rival a superar: `frente --id %s --rival %s --resultado "
                                  "supera|iguala|no --hallazgos H-… --texto \"…\"`" % (
                                      diferenciador["id"], nombre_fila(rival), diferenciador["id"], rival["id"]))
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


def texto_sesion(carpeta, producto, sesion):
    """El texto para pegar en el chat (o para el subagente) de una sesión: con el tipo de idea, para que cada línea
    sepa desde el inicio si trabaja por analogía (#28), y el presupuesto de la pasada si es una reapertura (#34)."""
    datos = SESION[sesion]
    partes = ["Sigue hb-product con %s: sesión %s · %s." % (carpeta / "estado.md", sesion, datos["nombre"])]
    if sesion in INVESTIGACION and tipo_de(producto):
        partes.append("Idea %s%s." % (texto_tipo(producto), ": trabaja por analogía desde el inicio"
                                      if tipo_de(producto) == "nueva" else ""))
    descarte = criterio_descarte_vigente(carpeta) if sesion in ("3", "4") else None
    if descarte:  # Viable para probar (#47): la sesión 3 y la 4 recogen el criterio de descarte
        partes.append("La puerta 1 fue Viable para probar: %s." % (
            "registra como la hipótesis más riesgosa que %s, con su métrica y su umbral (instalaciones orgánicas y "
            "retención a los %s del lanzamiento)" % (descarte.get("hipotesis") or "la gente elige la app por el "
                                                     "diferenciador principal", plural(int(
                                                         descarte.get("dias") or 60), "día"))
            if sesion == "3" else "el MVP pone a prueba la hipótesis más riesgosa (el criterio de descarte), con su "
                                  "métrica y su umbral, en la columna Hipótesis de su funcionalidad"))
    reapertura = int((producto["sesiones"].get(sesion) or {}).get("reaperturas") or 0)
    if sesion in INVESTIGACION and reapertura:
        limites = presupuesto_reapertura(producto)
        partes.append("Reapertura %d: el presupuesto de esta pasada es de %d búsquedas y %d lecturas." % (
            reapertura, limites["busquedas"], limites["lecturas"]))
        if sesion == "1c":  # la skill recomienda reabrir la 1c una sola vez (feedback #55)
            partes.append("Es la reapertura de la demanda: si al cerrar la demanda sigue en confianza baja (o el "
                          "problema sin documentar, en una idea nueva), la puerta 1 no recomienda reabrirla otra vez.")
    return " ".join(partes + ["No hagas commit ni push."])


def sesiones_abiertas(carpeta, producto):
    lista_decisiones = decisiones(carpeta)
    return [s["id"] for s in SESIONES if not cerrada(producto, s["id"])
            and disponible(producto, lista_decisiones, s["id"])]


def pasos(carpeta, producto, registro):
    """El paso siguiente: [líneas] según lo que hay en el disco."""
    lista_decisiones = decisiones(carpeta)
    abiertas = [s["id"] for s in SESIONES if not cerrada(producto, s["id"])
                and disponible(producto, lista_decisiones, s["id"])]
    lineas = []
    if abiertas == ["0"]:
        lineas += ["1. Este chat · Sesión 0 · Idea · %s" % texto_modelo(producto, "intermedio"),
                   "   Completa 00-idea.md y criterios.md (el presupuesto de semanas va con `criterio`; la meta de "
                   "ingresos es opcional), registra el objetivo (`objetivo --mercados … --idiomas … --tiendas …`) y "
                   "el tipo de idea provisional del triaje (`tipo --existente|--variante|--nueva --provisional "
                   "--motivo …`), y cierra la sesión:",
                   "   " + orden("cerrar --sesion 0", carpeta)]
        return lineas
    if abiertas:
        if len(abiertas) > 1:
            lineas.append("Puedes abrir estos chats en paralelo, uno por sesión (o un subagente por sesión en el modo "
                          "orquestado):")
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
                       "     " + texto_sesion(carpeta, producto, sesion)]
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


def texto_sesiones(sesiones):
    """'la sesión 0' o 'las sesiones 0, 1a y 1b': nunca un número suelto que se confunda con un costo."""
    if len(sesiones) == 1:
        return "la sesión %s" % sesiones[0]
    return "las sesiones %s y %s" % (", ".join(sesiones[:-1]), sesiones[-1])


def texto_siguiente(carpeta, producto, registro=None):
    registro = registro or Registro(carpeta, producto["criterios"])
    tipo = tipo_de(producto)
    titulo = "Siguiente paso · %s (%s)" % (producto["nombre"], "idea %s" % texto_tipo(producto) if tipo
                                           else "tipo de idea sin registrar")
    avisos = avisos_siguiente(carpeta, producto, registro)
    return "\n".join([titulo, ""] + pasos(carpeta, producto, registro) + ([""] + avisos if avisos else []))


def sin_orquestador(producto):
    """Las sesiones cerradas que ningún chat orquestador anotó todavía (`consumo --sesion orquestador --incluye`) y
    que no tienen su propio costo en USD: las que puede haber corrido el chat orquestador de ahora (feedback #46)."""
    cubiertas = {s for f in producto.get("consumo") or [] if f["sesion"] == "orquestador" for s in f.get("incluye") or []}
    con_usd = {f["sesion"] for f in producto.get("consumo") or [] if f["sesion"] != "orquestador" and con_costo(f)}
    return [s["id"] for s in SESIONES if cerrada(producto, s["id"]) and s["id"] not in cubiertas | con_usd]


def comando_orquestador(carpeta, producto, sesiones=None):
    """El `consumo` del chat orquestador, armado: el total de /cost (incluye a sus subagentes), sin tokens para no
    contarlos dos veces, con --incluye de las sesiones que corrió ese chat. Sin lista, las que ningún orquestador
    anotó todavía (`sin_orquestador`): el orquestador deja solo las que lanzó él."""
    hechas = sin_orquestador(producto) if sesiones is None else list(sesiones)
    return orden("consumo --sesion orquestador%s --costo '<USD que muestra /cost>'" % (
        " --incluye %s" % ",".join(hechas) if hechas else ""), carpeta)


def recordatorio_costo(carpeta, producto):
    """El recordatorio de /cost que el orquestador pone arriba en cada parada y en el mensaje final (feedback #46)."""
    return ("Antes de decidir o de cerrar este chat: corre /cost aquí (el total incluye a los subagentes) y anótalo "
            "con este comando, con --incluye solo de las sesiones que lanzó este chat: %s" % comando_orquestador(
                carpeta, producto))


def avisos_siguiente(carpeta, producto, registro):
    """Lo que `siguiente` dice debajo de los pasos: la puerta recién decidida, el rival a revisar, las líneas a revisar
    por cambio de tipo y el consumo sin anotar."""
    avisos = []
    for numero_puerta in (3, 2, 1):  # solo la última puerta decidida: es la que abrió el paso que sigue
        decision = vigente(decisiones(carpeta), numero_puerta)
        if decision and decision["decision"] == "seguir" and not avisos:
            avisos.append("Puerta %d: seguir, decidida el %s%s; si no fue tu decisión: `%s`" % (
                numero_puerta, decision["fecha"].replace("T", " "),
                " (%s)" % decision["desde"] if decision.get("desde") else "",
                orden("decidir --puerta %d --reabrir" % numero_puerta, carpeta)))
    if sesiones_abiertas(carpeta, producto) and cerrada(producto, "1a"):  # en una puerta, lo dicen sus avisos
        revisar_rival = rival_a_revisar(registro)
        if revisar_rival:
            avisos.append("⚠ Revisar el rival: %s." % texto_rival_a_revisar(registro, revisar_rival))
        revisar = a_revisar_por_tipo(producto, registro)
        if revisar:
            avisos.append("⚠ A revisar por cambio de tipo (la idea es %s): %s." % (tipo_de(producto),
                                                                                  texto_revisar(revisar)))
    pendientes = sin_consumo(producto) if producto.get("consumo") else []  # solo si ya se anotó alguno
    if pendientes:
        avisos.append("Consumo sin anotar (opcional) de %s: al cerrar cada chat, `%s`" % (
            texto_sesiones(pendientes), orden("consumo --sesion <id> --costo '<USD>'", carpeta)))
    lista_decisiones = decisiones(carpeta)
    sin_sesiones = not any(not cerrada(producto, s["id"]) and disponible(producto, lista_decisiones, s["id"])
                           for s in SESIONES)
    filas = producto.get("consumo") or []
    if filas and sin_sesiones and sin_orquestador(producto):
        avisos.append("Consumo del chat orquestador (si lo usaste): al terminar, anota lo que muestre /cost (en "
                      "Copilot, /usage, con --creditos en vez de --costo); ese total ya incluye a los subagentes. En "
                      "--incluye, solo las sesiones que corrió ese chat:")
        avisos.append("   " + comando_orquestador(carpeta, producto))
    return avisos


def texto_resumen(carpeta, producto, registro):
    criterios = producto["criterios"]
    tipo = producto.get("tipo")
    lista_decisiones = decisiones(carpeta)
    claves = [h for h in registro.hallazgos.values() if h.get("critico")]
    sin_triangular = [h["id"] for h in claves if not registro.evaluar(h)["triangulado"]]
    principal = registro.principal()
    lineas = [
        "- **Idea:** %s · creada el %s" % (producto["nombre"], producto["creado"]),
        "- **Tipo de idea:** %s" % ("%s (%s)" % (texto_tipo(producto), tipo["motivo"]) if tipo else "sin registrar (la "
                                    "sesión 0 registra uno provisional y la 1a lo confirma)"),
        "- **Criterios:** puntaje mínimo %s/25 (%s si la idea es nueva) · vigencia de %s meses (%s la estadística "
        "oficial y los estudios académicos) · %s fuentes independientes · %s · %s semanas" % (
            criterios["puntaje_minimo"], criterios["puntaje_minimo_nueva"], criterios["vigencia_meses"],
            criterios["vigencia_larga_meses"],
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
        parciales = [v for v, _ in vacios_parciales(registro)]
        lineas.append("- **Objetivo:** mercados %s · idiomas %s · tiendas %s · cobertura: %s sin registrar, %s%s%s" % (
                          ", ".join(objetivo["mercados"]) or "—", ", ".join(objetivo["idiomas"]) or "—",
                          ", ".join(objetivo["tiendas"]) or "ninguna", plural(huecos, "hueco"),
                          plural(len(vacios), "vacío"),
                          " (%d por límite de las herramientas)" % sum(1 for v in vacios if v["motivo"] == "herramienta")
                          if vacios else "",
                          ", %s (%s)" % (plural(len(parciales), "vacío parcial", "vacíos parciales"), ", ".join(
                              v["id"] for v in parciales)) if parciales else ""))
    else:
        lineas.append("- **Objetivo:** sin registrar (mercados, idiomas y tiendas: `objetivo`, en la sesión 0)")
    lineas.append("- **Hallazgos por peldaño:** %s" % texto_peldanos(conteo_peldanos(registro)))
    revisar = a_revisar_por_tipo(producto, registro)
    if revisar:
        lineas.append("- **A revisar por cambio de tipo:** %s" % texto_revisar(revisar))
    excedidas = pasadas_excedidas(producto)
    if excedidas:
        lineas.append("- **Presupuesto excedido:** %s" % "; ".join("%s usó %s" % par for par in excedidas))
    puntaje = producto.get("puntaje")
    if puntaje:
        modelos = puntajes_por_modelo(producto, registro)
        lineas.append("- **Puntaje:** %s · confianza global %s%s" % (
            texto_puntaje(modelos[0]), NIVELES[confianzas(registro)[1]], " · por modelo: %s" % "; ".join(
                "%s %s" % (m["modelo"], texto_puntaje(m)) for m in modelos) if len(modelos) > 1 else ""))
    escenarios = producto.get("escenarios")
    if escenarios:
        lineas.append("- **Escenario base:** %s %s al mes%s" % (
            numero(escenarios["base"]), escenarios["moneda"],
            " · " + " · ".join(escenarios["rotulos"]) if escenarios["rotulos"] else ""))
    consumo = producto.get("consumo", [])
    if consumo:
        lineas.append("- **Consumo anotado:** %s · total %s%s" % (
            " · ".join("%s: %s" % ("orquestador" if fila["sesion"] == "orquestador" else "sesión %s" % fila["sesion"],
                                   texto_consumo(fila)) for fila in consumo),
            texto_total(consumo), " (sin anotar: %s)" % texto_sesiones(sin_consumo(producto))
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
        if any(s == sesion["id"] for s, _, _ in revisar):
            estado += " · a revisar por cambio de tipo"
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
            if decision.get("automatica"):
                detalle += " · **decisión automática (modo autónomo)**: revísala o reábrela"
            if decision.get("criterio_descarte"):
                detalle += " · Viable para probar, criterio de descarte: %s" % decision["criterio_descarte"]["texto"]
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
    if args.raiz and not Path(os.path.abspath(os.path.expanduser(args.raiz))).is_dir():
        raise Fallo("--raiz: no existe la carpeta %s" % os.path.abspath(os.path.expanduser(args.raiz)))
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
        if args.raiz:
            fijar_raiz(carpeta, producto, args.raiz)
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
    actualizar_tablero(carpeta, producto, silencio=False)
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
            print("Tipo de idea: %s (%s) · registrado el %s" % (texto_tipo(producto), tipo["motivo"],
                                                              tipo["fecha"][:10]))
        else:
            print("Tipo de idea: sin registrar. La sesión 0 registra uno provisional (`tipo --<tipo> --provisional`) y "
                  "la 1a lo confirma; mientras tanto, investiga como si hubiera competencia y vuelve a consultar antes "
                  "de cerrar tu línea.")
        reabrir = presupuesto_reapertura(producto)
        print("Presupuesto por línea: %d búsquedas y %d lecturas; cada reapertura, %d y %d." % (
            limites["busquedas"], limites["lecturas"], reabrir["busquedas"], reabrir["lecturas"]))
        if tipo and tipo["valor"] == "nueva":
            print("Idea nueva: trabaja por analogía desde el inicio (references/analogia.md) y registra el peldaño "
                  "de cada fuente.")
        print("Siguiente paso: sigue con tu línea; `siguiente` muestra los carriles.")
        return
    if not args.motivo:
        raise Fallo("Registrar el tipo exige --motivo \"<qué competidores directos hay, o por qué no hay>\"")
    if args.provisional and cerrada(producto, "1a"):
        raise Fallo("La sesión 1a ya confirmó el tipo: un tipo provisional es el de la sesión 0, antes de las líneas")
    anterior = producto.get("tipo")
    if anterior:
        producto.setdefault("tipo_historial", []).append(anterior)
    producto["tipo"] = {"valor": elegido, "motivo": args.motivo.strip(), "fecha": ahora()}
    if args.provisional:
        producto["tipo"]["provisional"] = True
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    limites = presupuesto_de(producto)
    print("✔ Tipo de idea: %s%s%s" % (elegido, " (provisional: lo confirma la sesión 1a)" if args.provisional else "",
                                      " (antes: %s)" % anterior["valor"] if anterior else ""))
    print("Presupuesto por línea: %d búsquedas y %d lecturas." % (limites["busquedas"], limites["lecturas"]))
    revisar = a_revisar_por_tipo(producto, Registro(carpeta, producto["criterios"]))
    if revisar:
        print("⚠ A revisar por cambio de tipo: %s. La puerta 1 no recomienda descartar por evidencia que esas líneas "
              "no buscaron: recomienda ajustarlas." % texto_revisar(revisar))
    if elegido == "nueva":
        print("Siguiente paso: sube por la escalera de analogía (references/analogia.md), registra los análogos y "
              "los sustitutos en la matriz con su peldaño, y busca si alguien ya lo intentó (`intento`).")
    else:
        print("Siguiente paso: completa la matriz de competidores (`competidor`) y registra los hallazgos.")


def fecha_publicacion(texto, anio=False):
    """AAAA-MM-DD o AAAA-MM (día 1) → AAAA-MM-DD; 'desconocida' (o 'sin-fecha') → None (no cuenta como vigente). Con
    anio=True también acepta AAAA, que cuenta desde el 1 de enero: la fecha más antigua posible (feedback #33)."""
    if texto in SIN_FECHA:
        return None
    coincide = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", texto)
    if not coincide or (not anio and not coincide.group(2)):
        raise Fallo("--publicada debe ser AAAA-MM-DD, AAAA-MM, AAAA (solo el año) o desconocida, no '%s'" % texto)
    try:
        fecha = date(int(coincide.group(1)), int(coincide.group(2) or 1), int(coincide.group(3) or 1))
    except ValueError:
        raise Fallo("--publicada no es una fecha válida: '%s'" % texto)
    if fecha > hoy():
        raise Fallo("--publicada está en el futuro: '%s'" % texto)
    return fecha.isoformat()


def solo_anio(texto):
    return bool(re.match(r"^\d{4}$", str(texto or "")))


def texto_publicada(fuente):
    """'publicada el 2026-05-03', 'publicada en 2025 (fecha aproximada)' o 'fecha de publicación desconocida'."""
    if not fuente.get("publicada"):
        return "fecha de publicación desconocida"
    if fuente.get("aproximada"):
        return "publicada en %s (fecha aproximada: solo el año)" % fuente["publicada"][:4]
    return "publicada el %s" % fuente["publicada"]


def url_comparable(url):
    """La URL sin esquema, sin www y sin barra final, para comparar fichas; '' si no es una URL."""
    try:
        return url_normal(url)[1].split("://", 1)[1]
    except Fallo:
        return ""


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
    partes = [plural(len(filas), "fila")]
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
    if args.extracto and args.archivo:
        raise Fallo("--extracto es lo visto en un resultado de búsqueda (--url) sin abrir la página; un CSV de reseñas "
                    "ya se lee entero")
    if args.extracto and args.tipo == "oficial":
        raise Fallo("Una fuente oficial basta sola para un hallazgo de políticas: se lee en su página (la norma y su "
                    "versión), no en el extracto de un buscador. Abre la página y regístrala sin --extracto")
    if args.acumulado and args.tipo != "medido":
        raise Fallo("--acumulado marca un dato medido (descargas o valoraciones desde el lanzamiento): va con "
                    "--tipo medido")
    if args.clase and args.tipo == "oficial":
        raise Fallo("--clase es la vigencia larga de una estadística oficial o un estudio académico; una norma "
                    "(--tipo oficial) ya rige mientras no la reemplacen")
    reemplaza = (args.reemplaza or "").strip()
    if reemplaza:
        if args.clase != "estadistica":
            raise Fallo("--reemplaza es de una estadística oficial (--clase estadistica): la edición más nueva "
                        "reemplaza a la anterior")
        anterior = registro.fuentes.get(reemplaza)
        if not anterior or anterior.get("clase") != "estadistica":
            raise Fallo("%s no es una fuente de estadística oficial registrada (--clase estadistica)" % reemplaza)
    consultada = fecha_publicacion(args.consultada) if args.consultada else hoy().isoformat()
    if args.consultada and consultada is None:
        raise Fallo("--consultada es la fecha en que leíste la fuente: AAAA-MM-DD")
    fecha = fecha_publicacion(publicada, anio=True)
    aproximada = solo_anio(publicada)
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
        completado = []  # una fuente sin fecha o sin clase se completa; lo que ya tiene no se pisa
        if fecha and not existente.get("publicada"):
            existente["publicada"] = fecha
            if aproximada:
                existente["aproximada"] = "anio"
            completado.append(texto_publicada(existente))
        if args.clase and not existente.get("clase"):
            existente["clase"] = args.clase
            completado.append(CLASES_VIGENCIA[args.clase])
        if reemplaza and not existente.get("reemplaza"):
            existente["reemplaza"] = reemplaza
            completado.append("reemplaza a %s" % reemplaza)
        if existente.get("extracto") and not args.extracto:  # se abrió la página: ahora es una lectura (#53)
            existente.pop("extracto")
            existente["leida"] = ahora()
            completado.append("se abrió la página: ahora cuenta como lectura")
        if agregadas or completado:
            escribir_json(ruta_linea(carpeta, linea), datos)
        print("· %s ya estaba registrada con %s: no se duplica%s%s." % (
            existente["id"], "ese archivo" if args.archivo else "esa URL",
            "; se le agregó la cobertura %s" % ", ".join(agregadas) if agregadas else "",
            "; se completó: %s" % ", ".join(completado) if completado else ""))
        if completado:
            registro = Registro(carpeta, producto["criterios"])
            print("· %s: %s." % (existente["id"], "vigente" if registro.vigente(existente) else
                                 "sin fecha o fuera de su ventana de vigencia: no cuenta"))
        identificador = existente["id"]
    else:
        identificador = "S-%s-%d" % (LINEAS[linea][0], len(datos["fuentes"]) + 1)
        fuente = {"id": identificador, "linea": linea, "url": url, "dominio": dominio, "autor": autor,
                  "publicada": fecha, "consultada": consultada, "tipo": args.tipo, "peldano": args.peldano,
                  "resumen": resumen}
        fuente.update((d, v) for d, v in marcas.items() if v)
        if aproximada:
            fuente["aproximada"] = "anio"
        if args.clase:
            fuente["clase"] = args.clase
        if reemplaza:
            fuente["reemplaza"] = reemplaza
        if args.archivo:
            fuente["archivo"] = str(ruta_csv)
        if version:
            fuente["version"] = version
        if args.acumulado:
            fuente["acumulado"] = True
        if args.extracto:
            fuente["extracto"] = True
        datos["fuentes"].append(fuente)
        escribir_json(ruta_linea(carpeta, linea), datos)
        registro = Registro(carpeta, producto["criterios"])
        print("✔ %s registrada (%s · peldaño %d, %s · %s%s · %s)" % (
            identificador, linea, args.peldano, PELDANOS[args.peldano][0], args.tipo,
            " · %s" % CLASES_VIGENCIA[args.clase] if args.clase else "",
            "vigente" if registro.vigente(fuente) else "sin fecha o fuera de su ventana de vigencia: no cuenta para "
            "la confianza ni para triangular"))
        if aproximada:
            print("· Solo el año: cuenta desde el 1 de enero de %s (la fecha más antigua posible) y queda como fecha "
                  "aproximada." % publicada)
        if args.clase:
            print("· %s: vigente %d meses desde su publicación%s; un hallazgo clave necesita además una fuente de "
                  "los últimos %s meses." % (
                      CLASES_VIGENCIA[args.clase].capitalize(), registro.ventana(fuente),
                      ", o hasta que una edición más nueva la reemplace (`fuente … --clase estadistica --reemplaza %s`)"
                      % identificador if args.clase == "estadistica" else "",
                      producto["criterios"]["vigencia_meses"]))
        if reemplaza:
            print("· %s reemplaza a %s: la edición anterior deja de ser vigente." % (identificador, reemplaza))
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
        if args.extracto:
            print("· Extracto de un resultado de búsqueda: no cuenta como lectura (ya cuenta la búsqueda que lo trajo) "
                  "y queda marcado en `triangulacion` y en el reporte. Para la confianza cuenta como cualquier fuente: "
                  "vale solo para un dato puntual y verificable en el extracto (una cifra con su fecha, el precio de "
                  "una ficha); si hace falta el contexto, abre la página y vuelve a registrar la URL sin --extracto "
                  "(references/investigacion.md).")
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
    cantidad = sum(1 for f in datos["fuentes"] if not f.get("anulado") and not f.get("extracto"))
    extractos = sum(1 for f in datos["fuentes"] if not f.get("anulado") and f.get("extracto"))
    limite = presupuesto_de(producto)["lecturas"]
    sesion_linea = producto["sesiones"].get(LINEAS[linea][1]) or {}
    if sesion_linea.get("reaperturas") and not sesion_linea.get("cerrada"):  # una reapertura tiene su presupuesto
        cantidad -= int(sesion_linea.get("fuentes_base") or 0)
        limite = presupuesto_reapertura(producto)["lecturas"]
        print("Fuentes de la línea %s en esta reapertura: %d (presupuesto de lecturas de la reapertura: %d)%s"
              % (linea, cantidad, limite, texto_extractos(extractos)))
    else:
        print("Fuentes de la línea %s: %d (presupuesto de lecturas: %d)%s" % (
            linea, cantidad, limite, texto_extractos(extractos)))
    if cantidad >= 0.8 * limite:
        print("⚠ Llegaste al 80 % del presupuesto de lecturas de esta línea: dilo y cierra con lo que tienes.")
    print("Siguiente paso: cuando un hallazgo tenga sus fuentes, `hallazgo --linea %s --texto \"…\" --fuentes %s,…`"
          % (linea, identificador))


def texto_extractos(cantidad):
    """' · más 2 extractos de búsqueda, que no cuentan como lectura' (feedback #53)."""
    if not cantidad:
        return ""
    return " · más %s, que no %s como lectura" % (plural(cantidad, "extracto de búsqueda", "extractos de búsqueda"),
                                                  "cuenta" if cantidad == 1 else "cuentan")


def ids_existentes(ids, universo, que):
    faltan = [i for i in ids if i not in universo]
    if faltan:
        raise Fallo("%s %s: %s" % ("No existe" if len(faltan) == 1 else "No existen", que, ", ".join(faltan)))
    return ids


def competidores_anulados(carpeta):
    """Los IDs de las filas de la matriz que se anularon (no están en el Registro, que solo carga lo vigente)."""
    return {item["id"] for linea in LINEAS for item in cargar_linea(carpeta, linea).get("matriz", [])
            if item.get("anulado")}


def enlazar_hallazgo(carpeta, producto, registro, args):
    """`hallazgo --id H-… --competidor C-…` (feedback #52) y `hallazgo --id H-… --fuentes S-…` (feedback #53): completan
    un hallazgo ya registrado sin cambiar su ID, como `fuente` con una URL ya registrada completa la fecha. Solo
    agregan (nunca quitan), todo o nada.

    - Competidores: la 1b corre en paralelo con la 1a y puede registrar un hallazgo antes de que exista la fila de su
      competidor. Tienen que existir en la matriz y no estar anulados. Funciona con la sesión del hallazgo cerrada,
      porque no cambia su confianza ni lo que ya se investigó.
    - Fuentes: una fuente que llega después (la 1g que confirma H-DIF-1). La confianza se recalcula con la regla de
      siempre, así que pide la sesión dueña del hallazgo abierta: con ella cerrada, sumar evidencia cambiaría lo que la
      puerta evalúa sin pasar por ella (y fuera del presupuesto de la línea); va como propuesta para la puerta."""
    sobra = [opcion for opcion, valor in (("--linea", args.linea), ("--texto", args.texto),
                                         ("--en-contra", args.en_contra), ("--sin-contra", args.sin_contra),
                                         ("--critico", args.critico), ("--bloquea", args.bloquea)) if valor]
    if sobra:
        raise Fallo("Con --id solo se agregan competidores (--competidor C-…) o fuentes (--fuentes S-…): %s no va. Para "
                    "cambiar el texto o lo demás de un hallazgo, anúlalo y regístralo otra vez" % ", ".join(sobra))
    referencias, pedidas = lista(args.competidores), lista(args.fuentes)
    if not referencias and not pedidas:
        raise Fallo("Con --id, pasa los competidores a enlazar (--competidor C-1,C-3; `matriz` los lista) o las fuentes "
                    "a sumar (--fuentes S-…)")
    hallazgo = registro.hallazgos.get(args.id)
    if not hallazgo:
        raise Fallo("No existe el hallazgo %s, o está anulado" % args.id)
    fuentes_nuevas = []
    if pedidas:
        ids_existentes(pedidas, registro.fuentes, "esta fuente")
        sesion = LINEAS[hallazgo["linea"]][1]
        if cerrada(producto, sesion):
            raise Fallo("Sumar fuentes a %s cambia su confianza, y la sesión %s (%s), dueña del hallazgo, ya cerró: no "
                        "se hace con un comando suelto. Regístralo como propuesta para la puerta (`propuesta --texto "
                        "\"<qué fuente y por qué>\" --ajustar %s`) o, si es tu propia evidencia, registra un hallazgo "
                        "nuevo en tu línea. Enlazar competidores (--competidor) sí vale con la sesión cerrada" % (
                            args.id, sesion, SESION[sesion]["nombre"], sesion))
        repetidas = sorted(set(pedidas) & set(hallazgo.get("en_contra", [])))
        if repetidas:
            raise Fallo("Una fuente no puede estar a favor y en contra a la vez: %s ya es evidencia en contra de %s" % (
                ", ".join(repetidas), args.id))
        fuentes_nuevas = [f for f in dict.fromkeys(pedidas) if f not in hallazgo.get("fuentes", [])]
    agregados, nuevos = [], []
    if referencias:
        anulados = competidores_anulados(carpeta)
        malos = []
        for referencia in referencias:
            fila = registro.competidor(referencia)
            if fila:
                nuevos.append(fila["id"])
            elif referencia in anulados:
                malos.append("%s está anulado" % referencia)
            else:
                malos.append("%s no está en la matriz" % referencia)
        if malos:
            raise Fallo("%s: el enlace es a una fila vigente de la matriz, por su ID (`matriz` las lista)" % "; ".join(
                malos))
        ya = {registro.competidor(r)["id"] for r in hallazgo.get("competidores", []) if registro.competidor(r)}
        agregados = [c for c in dict.fromkeys(nuevos) if c not in ya and c not in hallazgo.get("competidores", [])]
    if not agregados and not fuentes_nuevas:
        partes = (["estaba enlazado a %s" % ", ".join(dict.fromkeys(nuevos))] if nuevos else []) + (
            ["tenía %s" % ", ".join(dict.fromkeys(pedidas))] if pedidas else [])
        print("· %s ya %s: nada que agregar." % (args.id, " y ".join(partes)))
        return
    antes = registro.etiqueta(hallazgo)
    datos = cargar_linea(carpeta, hallazgo["linea"])
    for item in datos["hallazgos"]:
        if item["id"] == args.id:
            traza = {"fecha": ahora()}
            if agregados:
                item["competidores"] = list(item.get("competidores", [])) + agregados
                traza["competidores"] = agregados
            if fuentes_nuevas:
                item["fuentes"] = list(item.get("fuentes", [])) + fuentes_nuevas
                traza["fuentes"] = fuentes_nuevas
            item.setdefault("enlaces", []).append(traza)
            hallazgo = item
    escribir_json(ruta_linea(carpeta, hallazgo["linea"]), datos)
    registro = Registro(carpeta, producto["criterios"])
    hallazgo = registro.hallazgos[args.id]
    if agregados:
        enlazados, sin_fila = registro.referencias(hallazgo)
        print("✔ %s enlazado a %s · mismo ID%s" % (args.id, ", ".join(agregados), "" if fuentes_nuevas else
                                                   ", mismas fuentes y misma confianza (%s)" % antes))
        print("· Cita a %s (por su ID en la matriz).%s" % (", ".join(enlazados), " Sin fila todavía: %s." % ", ".join(
            sin_fila) if sin_fila else ""))
    if fuentes_nuevas:
        evaluacion = registro.evaluar(hallazgo)
        despues = registro.etiqueta(hallazgo)
        print("✔ %s suma %s · mismo ID · %s%s (%s)" % (
            args.id, ", ".join(fuentes_nuevas), despues, "" if despues == antes else " (antes: %s)" % antes.replace(
                "confianza ", ""), plural(evaluacion["independientes"], "fuente independiente y vigente",
                                          "fuentes independientes y vigentes")))
        if hallazgo.get("critico") and evaluacion["faltan"]:
            print("⚠ Para cumplir la regla de triangulación: %s." % "; ".join(evaluacion["faltan"]))
        citan = [d["id"] for d in registro.diferenciadores.values() if args.id in registro.hallazgos_de(d)]
        if citan:
            print("· Lo citan %s: su estado se recalcula con esta confianza (`triangulacion`, y la puerta al "
                  "evaluarse)." % ", ".join(citan))
    print("Siguiente paso: %s; si una puerta ya se evaluó, vuelve a correrla." % (
        "`triangulacion` lista lo que les falta a los hallazgos clave" if fuentes_nuevas
        else "`matriz` muestra qué hallazgos tiene cada competidor"))


def cmd_hallazgo(args):
    carpeta, producto, registro = abrir(args)
    if args.id:
        return enlazar_hallazgo(carpeta, producto, registro, args)
    faltan = [opcion for opcion, valor in (("--linea", args.linea), ("--texto", args.texto),
                                           ("--fuentes", args.fuentes)) if not valor]
    if faltan:
        raise Fallo("Para registrar un hallazgo faltan %s (o --id H-… --competidor C-… / --fuentes S-… para completar "
                    "uno ya registrado)" % ", ".join(faltan))
    linea = linea_valida(args.linea)
    fuentes = ids_existentes(lista(args.fuentes), registro.fuentes, "esta fuente")
    if not fuentes:
        raise Fallo("Un hallazgo necesita al menos una fuente (--fuentes S-…): sin fuente va como ⚠ Sin evidencia "
                    "en el texto, no en el registro")
    contra = ids_existentes(lista(args.en_contra), registro.fuentes, "esta fuente en contra")
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
    citados = []  # por su ID (feedback #39): un nombre o la URL de la ficha que ya tienen fila se guardan como C-…
    for referencia in lista(args.competidores):
        fila = registro.competidor(referencia)
        citados.append(fila["id"] if fila else referencia)
    hallazgo = {"id": identificador, "linea": linea, "texto": args.texto.strip(), "fuentes": fuentes,
                "en_contra": contra, "sin_contra": (args.sin_contra or "").strip(), "critico": bool(args.critico),
                "competidores": list(dict.fromkeys(citados)), "fecha": ahora()}
    if bloquea:
        hallazgo["bloquea"] = bloquea
    datos["hallazgos"].append(hallazgo)
    escribir_json(ruta_linea(carpeta, linea), datos)
    evaluacion = registro.evaluar(hallazgo)
    print("✔ %s registrado%s · %s (peldaño %d, %s · %s%s)" % (
        identificador, " como hallazgo clave" if args.critico else "", registro.etiqueta(hallazgo),
        evaluacion["peldano"], PELDANOS[evaluacion["peldano"]][0], plural(
            evaluacion["independientes"], "fuente independiente y vigente", "fuentes independientes y vigentes"),
        " · %d en contra" % evaluacion["contra"] if evaluacion["contra"] else ""))
    if evaluacion["no_vigentes"]:
        print("· %s sin fecha o fuera de su ventana de vigencia: no %s para la confianza ni para triangular." % (
            ", ".join(evaluacion["no_vigentes"]), "cuenta" if len(evaluacion["no_vigentes"]) == 1 else "cuentan"))
    enlazados, sin_fila = registro.referencias(hallazgo)
    if enlazados:
        print("· Cita a %s (por su ID en la matriz)." % ", ".join(enlazados))
    if sin_fila:
        print("· %s sin fila en la matriz todavía: %s. Cuando la 1a lo registre, enlázalo por su ID sin volver a "
              "registrar el hallazgo (`hallazgo --id %s --competidor C-…`); mientras, se enlaza por la URL de su "
              "ficha si una de tus fuentes es esa ficha." % (
                  "Competidor" if len(sin_fila) == 1 else "Competidores", ", ".join(sin_fila), identificador))
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
    if args.sin_rival is not None:
        if args.nombre or args.rival:
            raise Fallo("--sin-rival va solo: dice que ninguna alternativa gratis resuelve la necesidad")
        if len(args.sin_rival.strip()) < 10:
            raise Fallo("--sin-rival lleva el motivo: por qué ninguna alternativa gratis (app o sustituto) resuelve "
                        "la necesidad")
        if registro.rivales():
            raise Fallo("Ya hay un rival a superar (%s): una alternativa gratis marcada o un sustituto gratuito o "
                        "nativo que resuelve la necesidad" % texto_rivales(registro.rivales()))
        datos = cargar_linea(carpeta, "competencia")
        datos["sin_rival"] = {"motivo": args.sin_rival.strip(), "fecha": ahora()}
        escribir_json(ruta_linea(carpeta, "competencia"), datos)
        print("✔ Sin rival gratis: %s" % args.sin_rival.strip())
        print("Siguiente paso: la puerta 1 lo muestra; si después aparece una alternativa gratis, márcala con "
              "`competidor --nombre … --rival`.")
        return
    faltan = [opcion for opcion, valor in (("--nombre", args.nombre), ("--peldano", args.peldano),
                                           ("--fuentes", args.fuentes)) if not valor]
    if faltan:
        raise Fallo("Falta %s: cada fila de la matriz lleva nombre, peldaño y fuentes" % ", ".join(faltan))
    fuentes = ids_existentes(lista(args.fuentes), registro.fuentes, "esta fuente")
    if not fuentes:
        raise Fallo("Cada fila de la matriz necesita al menos una fuente (--fuentes S-…)")
    if (args.sustituto or args.resuelve) and args.peldano != 4:
        raise Fallo("--sustituto y --resuelve son de un sustituto (--peldano 4): cómo se resuelve hoy la necesidad "
                    "sin una app así")
    datos = cargar_linea(carpeta, "competencia")
    fila = registro.competidor(args.nombre)
    nueva = fila is None
    if nueva:
        fila = {"id": "C-%d" % (len(datos["matriz"]) + 1), "nombre": args.nombre.strip(), "fecha": instante()}
        datos["matriz"].append(fila)
    else:
        fila = next(item for item in datos["matriz"] if item["id"] == fila["id"])
    fila.update(peldano=args.peldano, fuentes=sorted(set(fila.get("fuentes", [])) | set(fuentes)))
    valores = {
        "descargas": int(a_numero(args.descargas)) if args.descargas else None,
        "valoraciones": int(a_numero(args.valoraciones)) if args.valoraciones else None,
        "nota": a_numero(args.nota) if args.nota else None, "actualizada": args.actualizada,
        "precio": args.precio, "modelo": args.modelo, "anuncios": args.anuncios,
        "tamano_mb": a_numero(args.tamano_mb) if args.tamano_mb else None, "idiomas": lista(args.idiomas),
        "permisos": lista(args.permisos), "sin_conexion": args.sin_conexion, "accesibilidad": args.accesibilidad,
        "plataformas": lista(args.plataformas),
        "funciones": [f.strip() for f in (args.funciones or "").split(";") if f.strip()], "traccion": args.traccion,
        "sustituto": args.sustituto, "resuelve": args.resuelve, "respaldo": (args.respaldo or "").strip() or None,
    }
    for clave, valor in valores.items():
        if valor not in (None, "", []):
            fila[clave] = valor  # una fila se completa por partes: lo que no se pasa queda como estaba
    anterior = None
    if args.rival:
        if fila.get("peldano") == 4 and fila.get("sustituto") == "pago":
            raise Fallo("El rival a superar es la alternativa gratis más fuerte: %s es un sustituto de pago"
                        % nombre_fila(fila))
        for otra in datos["matriz"]:
            if otra.get("rival") and otra["id"] != fila["id"] and not otra.get("anulado"):
                otra["rival"] = False
                anterior = otra["id"]
        fila["rival"] = True
        fila["rival_fecha"] = instante()  # un sustituto con tracción que llegue después pide revisar el rival (#36)
        datos.pop("sin_rival", None)
    escribir_json(ruta_linea(carpeta, "competencia"), datos)
    registro = Registro(carpeta, producto["criterios"])
    vacias = [c for c in COLUMNAS_MATRIZ if c != "traccion" and fila.get(c) in (None, "", [])
              and not (c == "descargas" and fila.get("valoraciones"))]
    print("✔ %s %s: %s (peldaño %d, %s · %s)" % (fila["id"], "registrado" if nueva else "actualizado", fila["nombre"],
                                              args.peldano, PELDANOS[args.peldano][0], "con tracción: %s" %
                                              registro.motivo_traccion(fila) if registro.con_traccion(fila) else
                                              "sin tracción: %s" % registro.motivo_traccion(fila)))
    if fila.get("traccion") and not registro.con_traccion(fila):
        print("· La nota de tracción («%s») es contexto y no cuenta: cuenta --descargas desde %s (con su fuente), "
              "--valoraciones desde %s si la fuente no da descargas o --respaldo \"<institución que la respalda>\"." % (
                  fila["traccion"], numero(float(producto["criterios"]["traccion_descargas"])),
                  numero(float(producto["criterios"]["traccion_valoraciones"]))))
    if fila.get("valoraciones") and fila.get("descargas"):
        print("· Con descargas registradas, las valoraciones no cuentan para la tracción: solo se usan cuando la "
              "fuente no da descargas.")
    if vacias:
        print("· Columnas sin dato: %s" % ", ".join(vacias))
    if args.rival:
        print("⚠ Rival a superar: %s, la alternativa gratis más fuerte%s. La sesión 1g registra frente a él si cada "
              "diferenciador lo supera, lo iguala o no (`frente`); igualarlo es paridad y no hace viable a ninguno. La "
              "puerta 1 pide uno que lo supere: con prueba de elección es Viable, y con el dolor triangulado pero sin "
              "esa prueba, Viable para probar." % (
                  nombre_fila(fila), " (antes: %s)" % anterior if anterior else ""))
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
        ids, sueltas = registro.referencias(hallazgo)
        for clave in ids + ["sin fila: " + r for r in sueltas]:
            quejas.setdefault(clave, []).append(hallazgo["id"])
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
        if fila in registro.rivales():
            peldano += " · rival"
        print("| %s |" % " | ".join([
            fila["id"], fila["nombre"] + (" ★" if registro.con_traccion(fila) else ""), peldano,
            texto(fila.get("descargas")), texto(fila.get("nota")), texto(fila.get("actualizada")), texto(precio),
            texto(fila.get("anuncios")), texto(fila.get("tamano_mb")), texto(fila.get("idiomas")),
            texto(fila.get("permisos")), texto(fila.get("sin_conexion")), texto(fila.get("accesibilidad")),
            texto(fila.get("plataformas")), texto(fila.get("funciones")), texto(quejas.get(fila["id"]))]))
    print("\n★ = con tracción (%s descargas o más; sin descargas publicadas, %s valoraciones o más, tracción estimada; "
          "o respaldo institucional con --respaldo; una nota de --traccion es contexto y no cuenta)." % (
              numero(float(producto["criterios"]["traccion_descargas"])),
              numero(float(producto["criterios"]["traccion_valoraciones"]))))
    rivales = registro.rivales()
    if rivales:
        print("⚠ Rival a superar (la alternativa gratis más fuerte o un sustituto gratuito o nativo que ya resuelve la "
              "necesidad): %s. Cada diferenciador registra frente a él si lo supera, lo iguala o no (`frente`)."
              % texto_rivales(rivales))
    elif registro.sin_rival:
        print("· Sin rival gratis: %s" % registro.sin_rival["motivo"])
    elif tipo_de(producto) in ("existente", "variante"):
        print("· Falta marcar la alternativa gratis más fuerte (`competidor --nombre … --rival`) o decir que no la "
              "hay (`competidor --sin-rival \"…\"`): la sesión 1a no cierra sin eso.")
    if not registro.sustitutos():
        print("· Sin sustitutos (peldaño 4): ¿cómo se resuelve hoy la necesidad sin una app así? La sesión 1a lo "
              "registra antes de cerrar.")
    for clave, ids in quejas.items():
        if clave.startswith("sin fila: "):
            print("⚠ Competidor %s: lo %s %s, pero no tiene fila en la matriz ni una ficha en común. Cuando tenga "
                  "fila, enlázalo por su ID sin volver a registrar el hallazgo (`hallazgo --id %s --competidor C-…`)."
                  % (clave[10:], "cita" if len(ids) == 1 else "citan", ", ".join(ids), ids[0] if len(ids) == 1 else "H-…"))
    print("Siguiente paso: con la matriz y las quejas, la sesión 1g busca los huecos por vector "
          "(references/diferenciacion.md).")


def cmd_intento(args):
    carpeta, producto, registro = abrir(args)
    fuentes = ids_existentes(lista(args.fuentes), registro.fuentes, "esta fuente")
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
    hallazgos = ids_existentes(lista(args.hallazgos), registro.hallazgos, "este hallazgo")
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


COMPARACIONES = {"supera": "lo supera", "iguala": "lo iguala (paridad)", "no": "no lo supera"}


def cmd_frente(args):
    carpeta, producto, registro = abrir(args)
    exigir_1g_abierta(producto, carpeta, "Comparar un diferenciador con el rival")
    if args.id not in registro.diferenciadores:
        raise Fallo("No existe el diferenciador %s (o está anulado)" % args.id)
    rivales = registro.rivales()
    if args.rival:
        rival = registro.competidor(args.rival)
        if rival is None:
            raise Fallo("%s no tiene fila en la matriz" % args.rival)
        if rival not in rivales:
            raise Fallo("%s no es un rival a superar: márcalo como la alternativa gratis más fuerte "
                        "(`competidor --nombre … --rival`) o regístralo como un sustituto gratuito o nativo que ya "
                        "resuelve la necesidad" % nombre_fila(rival))
    elif len(rivales) == 1:
        rival = rivales[0]
    elif rivales:
        raise Fallo("Hay %d rivales (%s): elige uno con --rival C-…" % (len(rivales), texto_rivales(rivales)))
    else:
        raise Fallo("No hay un rival a superar: la sesión 1a marca la alternativa gratis más fuerte con `competidor "
                    "--nombre … --rival`")
    hallazgos = ids_existentes(lista(args.hallazgos), registro.hallazgos, "este hallazgo")
    if not hallazgos:
        raise Fallo("La comparación necesita sus hallazgos (--hallazgos H-…): sin evidencia es una opinión")
    datos = cargar_linea(carpeta, "diferenciacion")
    item = next(d for d in datos["diferenciadores"] if d["id"] == args.id and not d.get("anulado"))
    item.setdefault("frente", {})[rival["id"]] = {"resultado": args.resultado, "hallazgos": hallazgos,
                                                  "texto": args.texto.strip(), "fecha": ahora()}
    escribir_json(ruta_linea(carpeta, "diferenciacion"), datos)
    registro = Registro(carpeta, producto["criterios"])
    diferenciador = registro.diferenciadores[args.id]
    print("✔ %s frente a %s: %s" % (args.id, nombre_fila(rival), COMPARACIONES[args.resultado]))
    for identificador in hallazgos:
        print("  · %s · %s" % (identificador, registro.etiqueta(registro.hallazgos[identificador])))
    if args.resultado == "iguala":
        print("· Igualar es paridad (básico en Kano): entra al MVP si hace falta para competir, pero no es una razón "
              "para elegir la app, no cuenta como viable y no puede ser el principal.")
    elif args.resultado == "supera":
        con_prueba, faltas, _ = registro.eleccion(diferenciador, hipotesis(carpeta, registro))
        print("· %s" % texto_eleccion(producto, registro, diferenciador, con_prueba, faltas))
    imprimir_viabilidad(registro, diferenciador)


def texto_eleccion(producto, registro, diferenciador, con_prueba, faltas):
    """Lo que dice `frente --resultado supera` de la prueba de elección, con la regla de hoy (feedback #47 y #54): sin
    esa prueba, la puerta 1 puede dar Viable para probar si el dolor está triangulado."""
    if con_prueba:
        return "Con prueba de elección: todos sus hallazgos están triangulados y en confianza alta."
    texto = "Sin prueba de elección (%s)" % "; ".join(faltas)
    if not registro.para_probar(diferenciador):
        return texto + (": el dolor no está triangulado (sus hallazgos propios, `diferenciador --hallazgos`), así que "
                        "la puerta 1 queda en Viable con reservas; con el dolor triangulado se podría probar (Viable "
                        "para probar) aunque falte la elección.")
    condiciones = condiciones_probar(producto, registro)
    return texto + (": con el dolor triangulado se puede probar. Si es el principal, la puerta 1 da Viable para probar "
                    "(seguir, con un criterio de descarte después del lanzamiento)%s." % (
                        "; hoy falta además que %s" % y_lista(condiciones) if condiciones
                        else " si ningún otro criterio falla"))


def imprimir_viabilidad(registro, diferenciador, como=""):
    estado = registro.estado(diferenciador)
    identificador = diferenciador["id"]
    print("%s %s%s: %s" % ({"viable": "✔", "baja": "⚠", "paridad": "✖", "no": "✖"}[estado], identificador, como,
                           ESTADOS_DIFERENCIADOR[estado]))
    for cumple, texto in registro.viabilidad(diferenciador):
        print("  %s %s" % ("✔" if cumple else "✖", texto))
    if estado == "baja" and registro.para_probar(diferenciador):
        print("· Cumple los cinco criterios y su dolor está triangulado; lo que no lo está es la comparación con el "
              "rival (la prueba de elección). Se puede probar: si es el principal, la puerta 1 puede dar Viable para "
              "probar, con un criterio de descarte después del lanzamiento.")
    elif estado == "baja":
        print("· Cumple los cinco criterios, pero no todos sus hallazgos están triangulados: no cuenta como viable "
              "para la puerta 1 hasta que lo estén (con solo su dolor triangulado, se podría probar).")
    if estado == "paridad":
        print("· Iguala %s: es paridad (básico en Kano). Sirve para competir, pero no es viable ni puede ser el "
              "principal." % a_los_rivales(registro.iguala(diferenciador)))
    if estado != "no" and diferenciador.get("copiable") == "alta":
        print("· Es fácil de copiar: sirve para entrar, pero no sostiene la posición.")
    en_ficha = any(d.get("se_ve") == "ficha" for d in registro.viables())
    en_uso = any(d.get("se_ve") == "uso" for d in registro.viables())
    if registro.viables() and not (en_ficha and en_uso):
        print("· Lo ideal es tener un diferenciador viable que se vea en la ficha (consigue descargas) y otro en el "
              "uso (consigue retención): falta el de %s." % ("la ficha" if not en_ficha else "el uso"))
    print("Siguiente paso: %s" % (
        "regístralo en diferenciacion.md con su ID; el más fuerte es el principal (`principal --id`)."
        if estado == "viable" or (estado == "baja" and registro.para_probar(diferenciador)) else "triangula sus "
        "hallazgos (`triangulacion` dice qué les falta) o elige otro como principal." if estado == "baja" else "compáralo con el rival (`frente --id %s --resultado "
        "supera|iguala|no …`)." % identificador if registro.rivales() and not all(
            registro.comparacion(diferenciador, r) for r in registro.rivales())
        else "consigue lo que falta o descártalo con `anular --id %s --motivo …`." % identificador))


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
    linea = linea_valida(args.linea)  # cualquier línea: también la que no pide esa dimensión (la tienda en 1d)
    elegidas = [(d, getattr(args, DIMENSIONES[d])) for d in DIMENSIONES if getattr(args, DIMENSIONES[d])]
    if args.peldano:
        elegidas.append(("peldano", str(args.peldano)))
    if len(elegidas) != 1:
        raise Fallo("Un vacío es de un solo valor: --mercado, --idioma, --tienda o --peldano, uno")
    dimension, valor = elegidas[0][0], elegidas[0][1].strip()
    objetivo = objetivo_de(producto)
    if dimension != "peldano" and objetivo and normal(valor) not in [normal(v) for v in objetivo[dimension]]:
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
    # un vacío de algo que ya tiene fuentes va junto a su ✔ (feedback #51): si no, no aparecería en ninguna parte
    parciales = vacios_parciales(registro, [args.linea] if args.linea else None)
    for vacio, _ in parciales:
        mapa.setdefault(vacio["linea"], [])
    for linea, filas in mapa.items():
        print("\n%s (sesión %s)" % (linea, LINEAS[linea][1]))
        propios = [(v, f) for v, f in parciales if v["linea"] == linea]
        mostrados = set()
        for dimension, valor, estado, detalle in filas:
            if estado == "fuentes":
                suyos = [v for v, _ in propios if v["dimension"] == dimension and normal(v["valor"]) == normal(valor)]
                mostrados.update(v["id"] for v in suyos)
                print("  ✔ %s %s · %s%s" % (DIMENSIONES[dimension], valor, ", ".join(detalle),
                                           "".join(" · " + texto_parcial(v) for v in suyos)))
            elif estado == "vacio":
                vacios += 1
                print("  ⚠ %s %s · vacío, %s (%s): %s" % (DIMENSIONES[dimension], valor, MOTIVOS_VACIO[detalle["motivo"]],
                                                          detalle["id"], detalle["texto"]))
            else:
                huecos += 1
                print("  ✖ %s %s · sin fuentes ni vacío registrado" % (DIMENSIONES[dimension], valor))
        for vacio, fuentes in propios:  # de una dimensión que la línea no pide (la tienda en monetización)
            if vacio["id"] not in mostrados:
                print("  ✔ %s %s · %s · %s" % (DIMENSIONES[vacio["dimension"]], vacio["valor"], ", ".join(fuentes),
                                              texto_parcial(vacio)))
        if not filas and not propios:
            print("  (sin nada que cubrir en el objetivo)")
    print("\n%s sin registrar · %s%s." % (plural(huecos, "hueco"), plural(vacios, "vacío registrado",
                                                                         "vacíos registrados"),
                                        " · %s (la cobertura tiene fuentes, pero lo que dice el vacío sigue sin "
                                        "leerse)" % plural(len(parciales), "vacío parcial", "vacíos parciales")
                                        if parciales else ""))
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
    print("\n%d de %s con esos filtros%s." % (min(len(filas), args.limite), plural(len(filas), "reseña"),
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
    print("| Orquestador (modo orquestado) | %s | %s | %s |" % (
        modelo_de(producto, "economico"), ESFUERZO["economico"], abrir_chat(producto, carpeta, "economico") or "—"))
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
    cubiertas = {s for f in filas if f.get("tokens") for s in f.get("incluye") or []}
    tokens = sum(f.get("tokens") or 0 for f in filas if f["sesion"] not in cubiertas)  # sin contar dos veces
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
        raise Fallo("--incluye lleva sesiones: %s no %s" % (", ".join(desconocidas), "existe" if len(desconocidas) == 1
                                                             else "existen"))
    valores = {"costo": monto(args.costo, "--costo") if args.costo else None,
               "creditos": monto(args.creditos, "--creditos") if args.creditos else None,
               "tokens": int(cantidad(args.tokens, "--tokens")) if args.tokens else None,
               "pasos": int(cantidad(args.pasos, "--pasos")) if args.pasos else None,
               "modelo": (args.modelo or "").strip() or None,
               "incluye": incluye or None}
    if all(valores[c] is None for c in ("costo", "creditos", "tokens")):
        raise Fallo("Anota al menos --costo (USD), --creditos (AI Credits de GitHub Copilot) o --tokens")
    if args.sesion == "orquestador" and incluye:
        # /cost es acumulado: el mismo chat que vuelve a anotar (comparte alguna sesión) actualiza su fila y suma sus
        # sesiones nuevas; un chat orquestador nuevo, con otras sesiones, va en una fila aparte (feedback #46)
        fila = next((f for f in filas if f["sesion"] == "orquestador" and set(f.get("incluye") or []) & set(incluye)),
                    None)
        if fila is None and any(f["sesion"] == "orquestador" and not f.get("incluye") for f in filas):
            fila = next(f for f in filas if f["sesion"] == "orquestador" and not f.get("incluye"))
        if fila is not None:
            valores["incluye"] = list(dict.fromkeys((fila.get("incluye") or []) + incluye))
    else:
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
    extractos = set()
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
            uno = len(evaluacion["acumuladas"]) == 1
            print("    · %s: %s, solo contexto: no %s, y no hace falta" % (
                ", ".join(evaluacion["acumuladas"]), "dato acumulado" if uno else "datos acumulados",
                "cuenta" if uno else "cuentan"))
        if evaluacion["triangulado"] and evaluacion["no_vigentes"]:
            print("    · %s sin fecha o fuera de la ventana: no %s, y no hace falta" % (
                ", ".join(evaluacion["no_vigentes"]), "cuenta" if len(evaluacion["no_vigentes"]) == 1 else "cuentan"))
        if evaluacion["sin_busqueda"]:
            print("    → regla 4: falta registrar la búsqueda de evidencia en contra (--en-contra o --sin-contra)")
        de_extracto = [f["id"] for f in registro.fuentes_de(hallazgo.get("fuentes", []) + hallazgo.get(
            "en_contra", [])) if f.get("extracto")]
        if de_extracto:
            extractos.update(de_extracto)
            print("    · %s: %s (no se abrió la página): cuenta%s para la confianza como cualquier fuente; si el "
                  "dato no es puntual y verificable en el extracto, ábrela" % (
                      ", ".join(de_extracto), "extracto de búsqueda" if len(de_extracto) == 1 else
                      "extractos de búsqueda", "" if len(de_extracto) == 1 else "n"))
        manual = hallazgo.get("confianza_manual")
        if manual:
            print("    · confianza bajada a %s: %s" % (manual["nivel"], manual["motivo"]))
    print("\n%d de %d hallazgos clave triangulados (regla 2)%s%s." % (
        len(claves) - incompletos, len(claves), " · %d sin la búsqueda en contra (regla 4)" % sin_busqueda
        if sin_busqueda else "", " · %s" % plural(len(extractos), "fuente de extracto de búsqueda",
                                                  "fuentes de extracto de búsqueda") if extractos else ""))
    print("La confianza y la triangulación usan la misma regla de vigencia: una fuente sin fecha o fuera de la ventana "
          "no cuenta para ninguna de las dos, y solo un hallazgo triangulado llega a confianza alta.")
    mapa = cobertura(producto, registro)
    if mapa is not None:
        huecos = sum(1 for filas in mapa.values() for fila in filas if fila[2] == "falta")
        vacios = sum(1 for filas in mapa.values() for fila in filas if fila[2] == "vacio")
        parciales = len(vacios_parciales(registro))
        print("Cobertura: %s sin fuentes ni vacío registrado · %s%s (`cobertura`)." % (
            plural(huecos, "hueco"), plural(vacios, "vacío registrado", "vacíos registrados"),
            " · %s" % plural(parciales, "vacío parcial", "vacíos parciales") if parciales else ""))
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
    valores = leer_valores(args.valores, "--valores")
    validar_valores(valores, producto, registro, "")
    alternativos = []
    for texto in args.alternativo or []:
        nombre, _, numeros = texto.partition("=")
        if not nombre.strip() or not numeros:
            raise Fallo("--alternativo es \"<modelo>=d,m,f,r,x\": el nombre del otro modelo de monetización registrado "
                        "en la sesión 0 y el puntaje con él")
        otros = leer_valores(numeros, "--alternativo")
        validar_valores(otros, producto, registro, " con «%s»" % nombre.strip())
        alternativos.append({"modelo": nombre.strip(), "valores": otros, "total": sum(otros.values())})
    if alternativos and not (args.modelo or "").strip():
        raise Fallo("Con --alternativo, nombra también el modelo base con --modelo \"<modelo>\"")
    por_criterio, global_ = confianzas(registro)
    total = sum(valores.values())
    producto["puntaje"] = {"valores": valores, "total": total, "mitigacion": (args.mitigacion or "").strip(),
                           "fecha": ahora()}
    if (args.modelo or "").strip():
        producto["puntaje"]["modelo"] = args.modelo.strip()
    if alternativos:
        producto["puntaje"]["alternativos"] = alternativos
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    imprimir_puntaje(producto, registro, valores, por_criterio, global_, total, args)


def leer_valores(texto, opcion):
    partes = lista(texto)
    if len(partes) != 5 or not all(parte.isdigit() and 1 <= int(parte) <= 5 for parte in partes):
        raise Fallo("%s lleva cinco enteros de 1 a 5, en este orden: demanda, monetización, facilidad, riesgo de "
                    "políticas (5 = bajo) y diferenciación. Por ejemplo: 4,3,4,5,3" % opcion)
    return dict(zip(CRITERIOS_PUNTAJE, (int(parte) for parte in partes)))


def validar_valores(valores, producto, registro, con):
    """Las anclas atadas al registro (references/puntaje.md), para el modelo base y para cada alternativo."""
    viables, bajas = registro.viables(), registro.con_confianza_baja()
    probar = [] if condiciones_probar(producto, registro) else [  # solo les falta la prueba de elección (#47)
        d for d in bajas if registro.para_probar(d)]
    if not viables and not bajas and valores["diferenciacion"] > 1:
        raise Fallo("Diferenciación = %d%s no corresponde: no hay ningún diferenciador viable registrado, y esa es "
                    "el ancla del 1 (references/puntaje.md)." % (valores["diferenciacion"], con))
    if not viables and bajas and not probar and valores["diferenciacion"] > 2:
        raise Fallo("Diferenciación = %d%s no corresponde: %s, así que el máximo es 2 (references/puntaje.md)." % (
            valores["diferenciacion"], con, texto_estados(registro, bajas)))
    if (viables or probar) and valores["diferenciacion"] == 1:
        raise Fallo("Diferenciación = 1%s no corresponde: %s." % (con, texto_estados(registro, viables or probar)))
    actuales = [h["id"] for h in registro.hallazgos.values() if h["linea"] == "demanda" and h.get("critico")
                and registro.evaluar(h)["triangulado"]]
    if valores["demanda"] >= 4 and not actuales:
        raise Fallo("Demanda = %d%s no corresponde: las anclas 4 y 5 piden señales actuales comprobadas (de los últimos "
                    "12 a 18 meses), y ningún hallazgo clave de demanda está triangulado con fuentes vigentes y no "
                    "acumuladas. Las descargas acumuladas son contexto (references/puntaje.md); `triangulacion` dice "
                    "qué falta." % (valores["demanda"], con))
    bloqueos = registro.bloqueos(objetivo_de(producto))
    if bloqueos and valores["riesgo"] != 1:
        raise Fallo("Riesgo de políticas = %d%s no corresponde: %s, y en esa tienda el riesgo es 1. Pasa 1 y, si hay "
                    "una mitigación creíble (por ejemplo, no lanzar en esa tienda), escríbela con --mitigacion." % (
                        valores["riesgo"], con, texto_bloqueos(bloqueos)))


def imprimir_puntaje(producto, registro, valores, por_criterio, global_, total, args):
    bloqueos = registro.bloqueos(objetivo_de(producto))
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
    for otro in producto["puntaje"].get("alternativos") or []:
        print("Con «%s»: %d/25 (%s) → %s" % (otro["modelo"], otro["total"], ", ".join(
            "%s %d" % (NOMBRES_CRITERIO[c], v) for c, v in otro["valores"].items() if v != valores[c]) or "igual",
            "lo alcanza" if otro["total"] >= minimo else "no lo alcanza"))
    if producto["puntaje"].get("alternativos"):
        print("· La puerta 1 muestra el puntaje con cada modelo y cuál exige: el modelo se decide en la sesión 2.")
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


RETENCION = ("d1", "d7", "d30")


def dias_activos(d1, d7, d30):
    """Los días que entra, en promedio, alguien en sus primeros 30 días desde que instala (feedback #43): el día de la
    instalación más la retención de cada día, interpolada en línea recta entre D1, D7 y D30. Con instalaciones
    parejas, los usuarios activos diarios de una app nueva son instalaciones del mes ÷ 30 × estos días; no cuenta a los
    que siguen después del día 30, que una app nueva todavía no tiene."""
    total = 1.0
    for dia in range(1, 30):
        if dia <= 7:
            total += d1 + (d7 - d1) * (dia - 1) / 6.0
        else:
            total += d7 + (d30 - d7) * (dia - 7) / 23.0
    return total


def comparable_maduro(registro, valor):
    """Si los usuarios activos diarios (`dau`) se tomaron de una app que ya está en la tienda (su fila de la matriz
    cita esa fuente, el supuesto la nombra con `comparable` o la fuente es un dato acumulado), el texto que la nombra;
    si no, None (feedback #43)."""
    if not isinstance(valor, dict):
        return None
    filas = []
    if valor.get("comparable"):
        fila = registro.competidor(str(valor["comparable"]))
        if fila:
            filas.append(fila)
    fuente = str(valor.get("fuente") or "").strip()
    filas += [c for c in registro.competidores.values() if fuente and fuente in c.get("fuentes", [])
              and c.get("peldano", 1) <= 3 and c not in filas]
    if filas:
        return "%s, una app que ya está en la tienda" % y_lista(nombre_fila(c) for c in filas)
    if fuente in registro.fuentes and registro.fuentes[fuente].get("acumulado"):
        return "%s, un dato acumulado desde el lanzamiento" % fuente
    return None


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

    avisos, origen = [], {}
    for mercado in mercados:
        nombre = str(mercado.get("mercado") or "?")
        retencion = mercado.get("retencion")
        instalaciones, sin_instalaciones = None, []
        # las instalaciones nuevas solo cuentan (y piden fuente) si las usa un pago único o la retención
        usa_instalaciones = retencion is not None or any(
            isinstance(c, dict) and c.get("tipo") == "pago-unico" for c in mercado.get("compras", []))

        def leer_instalaciones():
            if usa_instalaciones and mercado.get("instalaciones_mes") is not None:
                return supuestos(mercado.get("instalaciones_mes"), "%s.instalaciones_mes" % nombre)
            return None, []

        if retencion is not None:  # los usuarios activos de una app nueva salen de sus instalaciones (feedback #43)
            instalaciones, sin_instalaciones = leer_instalaciones()
            if mercado.get("dau") is not None:
                raise Fallo("`%s` trae `dau` y `retencion`: usa uno. Con `retencion` (D1, D7 y D30) e "
                            "`instalaciones_mes`, el script deriva los usuarios activos diarios de una app nueva" % nombre)
            if instalaciones is None:
                raise Fallo("`%s.retencion` deriva los usuarios activos diarios de las instalaciones nuevas: falta "
                            "`%s.instalaciones_mes`" % (nombre, nombre))
            if not isinstance(retencion, dict):
                raise Fallo("`%s.retencion` es un objeto con d1, d7 y d30" % nombre)
            curva, sin_dau = {}, list(sin_instalaciones)
            for dia in RETENCION:
                if retencion.get(dia) is None:
                    raise Fallo("`%s.retencion.%s` hace falta: la proporción de los que instalan que vuelve ese día "
                                "(entre 0 y 1, con su fuente)" % (nombre, dia))
                curva[dia], faltan = supuestos(retencion[dia], "%s.retencion.%s" % (nombre, dia))
                sin_dau += faltan
            for c in casos:
                if not 0 <= curva["d30"][c] <= curva["d7"][c] <= curva["d1"][c] <= 1:
                    raise Fallo("`%s.retencion` va entre 0 y 1 y no sube con los días (D30 ≤ D7 ≤ D1): en el caso %s es "
                                "D1 %s, D7 %s y D30 %s" % (nombre, c, numero(curva["d1"][c]), numero(curva["d7"][c]),
                                                           numero(curva["d30"][c])))
            dau = {c: instalaciones[c] / 30.0 * dias_activos(curva["d1"][c], curva["d7"][c], curva["d30"][c])
                   for c in casos}
            origen[nombre] = "instalaciones"
        else:
            if mercado.get("dau") is None:
                raise Fallo("`%s` necesita `dau` (usuarios activos diarios, con fuente) o `instalaciones_mes` y "
                            "`retencion` (D1, D7 y D30) para derivarlos: en una app nueva, mejor lo segundo" % nombre)
            dau, sin_dau = supuestos(mercado.get("dau"), "%s.dau" % nombre)
            instalaciones, sin_instalaciones = leer_instalaciones()
            origen[nombre] = "dau"
            maduro = comparable_maduro(registro, mercado.get("dau"))
            if maduro:
                origen[nombre] = "comparable"
                avisos.append("%s: los usuarios activos diarios salen de %s. Una app nueva no tiene esa base "
                              "instalada y el caso base queda inflado: derívalos de `instalaciones_mes` y `retencion` "
                              "(D1, D7 y D30, con fuente)" % (nombre, maduro))
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
        for compra in compras:
            if compra.get("tipo") not in TIPOS_COMPRA:
                raise Fallo("`%s.compras.%s` necesita `tipo`: pago-unico (se cobra una vez: instalaciones nuevas del "
                            "mes × conversión × precio × (1 − comisión)) o suscripcion (se cobra cada mes a la base "
                            "de pagadores: usuarios del mes × conversión × precio al mes × (1 − comisión))"
                            % (nombre, compra.get("nombre", "?")))
        tipos = {compra["tipo"] for compra in compras}
        sin_dau_mau = []
        if "suscripcion" in tipos:
            if mercado.get("dau_mau") is None:
                raise Fallo("`%s.dau_mau` hace falta para una suscripción: la proporción de los usuarios del mes que "
                            "entra cada día (entre 0 y 1)" % nombre)
            dau_mau, sin_dau_mau = supuestos(mercado.get("dau_mau"), "%s.dau_mau" % nombre)
            if min(dau_mau.values()) <= 0 or max(dau_mau.values()) > 1:
                raise Fallo("`%s.dau_mau` es la proporción de usuarios del mes que entran cada día: va entre 0 y 1"
                            % nombre)
        if "pago-unico" in tipos and instalaciones is None:
            raise Fallo("`%s.instalaciones_mes` hace falta para un pago único: las instalaciones nuevas de cada "
                        "mes (un pago único se cobra una vez, no cada mes a los mismos usuarios)" % nombre)
        for compra in compras:
            ruta_supuesto = "%s.compras.%s" % (nombre, compra.get("nombre", "?"))
            conversion, sin_conversion = supuestos(compra.get("conversion"), ruta_supuesto + ".conversion")
            precio, _ = supuestos(compra.get("precio"), ruta_supuesto + ".precio", False)
            comision = compra.get("comision")
            if not isinstance(comision, (int, float)) or not 0 <= comision < 1:
                raise Fallo("`%s.comision` es la comisión de la tienda como proporción: 0.15 o 0.30" % ruta_supuesto)
            if max(conversion.values()) > 1:
                raise Fallo("`%s.conversion` es una proporción entre 0 y 1 (1 % = 0.01)" % ruta_supuesto)
            if compra["tipo"] == "suscripcion":
                periodo = compra.get("periodo", "mes")
                if periodo not in PERIODOS:
                    raise Fallo("`%s.periodo` es mes o anio: lo que cubre el precio de la suscripción" % ruta_supuesto)
                propios = dict((c, dau[c] / dau_mau[c] * conversion[c] * precio[c] / PERIODOS[periodo]
                                * (1 - comision)) for c in casos)
                faltan = sin_dau + sin_dau_mau + sin_conversion
            else:
                propios = dict((c, instalaciones[c] * conversion[c] * precio[c] * (1 - comision)) for c in casos)
                faltan = sin_instalaciones + sin_conversion
            for c in casos:
                ingresos[c] += propios[c]
            sumar("%s · %s" % (TIPOS_COMPRA[compra["tipo"]], compra.get("nombre", "?")), propios["base"], faltan)
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
                              "entrada": str(ruta), "modelos": lista_modelos, "calculo": CALCULO_ESCENARIOS,
                              "dau_origen": origen, "avisos": avisos}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto)
    print("Escenarios de ingresos netos al mes (%s)%s" % (moneda, " · " + " · ".join(rotulos) if rotulos else ""))
    print("\n| Mercado | DAU base | Pesimista | Base | Optimista |\n| --- | --- | --- | --- | --- |")
    for nombre, dau, ingresos in filas:
        print("| %s | %s%s | %s | %s | %s |" % (nombre, numero(round(dau["base"])), " (de instalaciones y retención)"
                                             if origen.get(nombre) == "instalaciones" else "",
                                             numero(ingresos["pesimista"]), numero(ingresos["base"]),
                                             numero(ingresos["optimista"])))
    print("| **Total** | %s | %s | %s | %s |" % (numero(usuarios["base"]), numero(totales["pesimista"]),
                                               numero(totales["base"]), numero(totales["optimista"])))
    if analogia:
        print("\nPor analogía: el rango se abre (pesimista × %s y optimista × %s sobre la suma de los mercados)%s."
              % (numero(1 - AMPLITUD_ANALOGIA), numero(1 + AMPLITUD_ANALOGIA),
                 "; supuestos de análogos: " + "; ".join(por_analogia) if por_analogia else ""))
    if sin_fuente:
        print("⚠ Estimación: supuestos sin fuente: %s" % ", ".join(sin_fuente))
    for aviso in avisos:
        print("⚠ %s." % aviso)
    if "instalaciones" in origen.values():
        print("· Usuarios activos diarios de una app nueva: instalaciones del mes ÷ 30 × los días que entra cada una en "
              "sus primeros 30 días (1 + la retención de cada día, entre D1, D7 y D30).")
    print("\nModelos de monetización (la puerta 2 pide al menos uno viable con evidencia: genera ingresos en el caso "
          "base y todos sus supuestos citan su fuente). Anuncios: usuarios activos diarios × impresiones × 30 × eCPM "
          "÷ 1000; pago único: instalaciones nuevas del mes × conversión × precio × (1 − comisión); suscripción: "
          "usuarios del mes × conversión × precio al mes × (1 − comisión):")
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
        print("%s %s%s · RICE %s · %s · %s · %s" % (
            "✖" if funcion["faltas"] else "✔", funcion["id"], " (MVP)" if funcion["mvp"] else "", rice,
            plural(funcion["semanas"], "semana"), plural(funcion["aceptacion"], "criterio de aceptación",
                                                       "criterios de aceptación"),
            "; ".join(funcion["faltas"]) or ", ".join(
                funcion["hallazgos"] + funcion["diferenciadores"] + funcion["metricas"])))
    trazadas = [f for f in mvp if not f["faltas"]]
    principal = registro.principal()
    print("\nTrazabilidad del MVP: %d de %d funcionalidades (%d %%) · %s de %s" % (
        len(trazadas), len(mvp), round(100.0 * len(trazadas) / len(mvp)) if mvp else 0,
        plural(sum(f["semanas"] for f in mvp), "semana"), numero(float(producto["criterios"]["presupuesto_semanas"]
                                                                       or 0))))
    sin_criterios = criterios_sin_aceptacion(mvp)
    print("%s Criterios de aceptación: %d de %d funcionalidades del MVP%s" % (
        "✖" if sin_criterios else "✔", len(mvp) - len(sin_criterios), len(mvp),
        " · sin criterios: %s (en «Historias de usuario», debajo de «Criterios de aceptación»)" % ", ".join(
            sin_criterios) if sin_criterios else " · %s" % plural(sum(f["aceptacion"] for f in mvp), "criterio")))
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
    linea = next((nombre for nombre, (_, de_sesion) in LINEAS.items() if de_sesion == args.sesion), None)
    uso = {}
    for clave in ("busquedas", "lecturas"):
        valor = getattr(args, clave)
        if valor is not None:
            if args.sesion not in ("1a", "1b", "1c", "1d", "1e", "1g"):
                raise Fallo("--busquedas y --lecturas son de una sesión de investigación (1a a 1e y 1g)")
            if not re.match(r"^\d+$", valor.strip()):
                raise Fallo("--%s es un número entero: lo que usó la línea en esta pasada (desde que se abrió o se "
                            "reabrió la sesión)" % clave)
            uso[clave] = int(valor)
    if args.raiz:
        fijar_raiz(carpeta, producto, args.raiz)  # solo queda guardada si la sesión cierra
    faltan = pendientes_de(carpeta, producto, registro, args.sesion)
    if faltan:
        raise Fallo("La sesión %s · %s todavía no se puede cerrar:\n  - %s" % (
            args.sesion, SESION[args.sesion]["nombre"], "\n  - ".join(faltan)))
    datos_sesion = producto["sesiones"].setdefault(args.sesion, {})
    datos_sesion["cerrada"] = ahora()
    datos_sesion["tipo"] = tipo_de(producto)  # con qué tipo de idea trabajó: si cambia después, queda a revisar
    pasada = None
    if uso:
        pasada = registrar_pasada(producto, args.sesion, uso)
    guardar(carpeta, producto)
    siguiente = actualizar_estado(carpeta, producto)
    print("✔ Sesión %s · %s cerrada" % (args.sesion, SESION[args.sesion]["nombre"]))
    if pasada:
        print("· Presupuesto usado por la línea %s: %s." % (linea, texto_pasada(pasada)))
        if any(pasada[clave] > pasada["presupuesto"][clave] for clave in ("busquedas", "lecturas")):
            print("⚠ Esta pasada se pasó de su presupuesto: la síntesis (1f) y la puerta 1 lo muestran; dilo en el "
                  "entregable.")
        if args.sesion == "1g" and presupuesto_agotado(producto, registro, "1g"):
            print("· La 1g ya se reabrió y usó su presupuesto: si la puerta pide más evidencia de diferenciación, la "
                  "skill no recomendará ajustar la 1g otra vez.")
    if args.sesion == "1g":
        principal = registro.principal()
        paridad = [d["id"] for d in registro.diferenciadores.values() if registro.estado(d) == "paridad"]
        probar = [d["id"] for d in registro.con_confianza_baja() if registro.para_probar(d)]
        if tipo_de(producto) != "nueva" and not registro.viables() and probar:
            print("· Ningún diferenciador es viable con prueba de elección, pero %s %s con el dolor triangulado: si "
                  "el principal es uno de ellos, la puerta 1 puede dar Viable para probar." % (
                      y_lista(probar), "se puede probar" if len(probar) == 1 else "se pueden probar"))
        elif tipo_de(producto) != "nueva" and not registro.viables():
            print("⚠ No hay ningún diferenciador viable%s: la puerta 1 lo va a marcar como criterio sin cumplir." % (
                " (%s, con confianza baja: sin triangular)" % ", ".join(d["id"] for d in registro.con_confianza_baja())
                if registro.con_confianza_baja() else ""))
        if paridad:
            print("⚠ %s solo %s %s: es paridad (básico en Kano), no cuenta como viable ni puede ser el principal." % (
                ", ".join(paridad), "iguala" if len(paridad) == 1 else "igualan", a_los_rivales(registro.rivales())))
        if tipo_de(producto) != "nueva" and principal and registro.sin_triangular(principal):
            print("⚠ Los hallazgos del diferenciador principal (%s) no están triangulados: la puerta 1 lo marca%s." % (
                principal["id"], ", pero su dolor sí lo está: lo que falta es la prueba de elección, y puede quedar "
                                 "en Viable para probar" if registro.para_probar(principal) else ""))
        rivales = registro.rivales()
        if rivales and not any(registro.frente_al_rival(d)[0] for d in registro.diferenciadores.values()):
            print("⚠ Ningún diferenciador supera %s con un hallazgo triangulado: la puerta 1 lo marca como criterio "
                  "sin cumplir." % a_los_rivales(rivales, "ni"))
    actualizar_tablero(carpeta, producto)
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


def ajustes_previos(lista_decisiones, numero_puerta, sesion):
    """Cuántas veces se decidió ajustar esa sesión en esa puerta (vigentes o no)."""
    return sum(1 for d in lista_decisiones if d["puerta"] == numero_puerta and d.get("decision") == "ajustar"
               and d.get("sesion") == sesion)


def parada_autonoma(numero_puerta, carpeta, producto, registro, resultado):
    """Por qué el modo autónomo se detiene en esta puerta y le pregunta al usuario, o None (feedback #49): la puerta
    pide ajustar la misma sesión por tercera vez, o la sesión que se recomienda ajustar tiene vacíos por límite de las
    herramientas (un navegador o un CSV de reseñas solo los puede dar el usuario: ajustarla otra vez da lo mismo)."""
    if resultado["recomienda"] != "ajustar":
        return None
    sesion = resultado["sesion"]
    previos = ajustes_previos(decisiones(carpeta), numero_puerta, sesion)
    if previos >= 2:
        return ("la puerta %d pide ajustar la sesión %s por tercera vez (ya se ajustó %s): otra vuelta automática no "
                "promete nada nuevo" % (numero_puerta, sesion, plural(previos, "vez", "veces")))
    herramienta = vacios_de_sesion(producto, registro, sesion)
    if herramienta:
        return "%s: antes de ajustarla hace falta un navegador en el agente o un CSV de reseñas que aporte el usuario" % (
            texto_vacios_sesion(sesion, herramienta))
    return None


def motivo_descarte(resultado):
    """El motivo que la skill propone al recomendar descartar: sus razones."""
    return "No viable: %s" % "; ".join(resultado["razones"])


def cmd_decidir(args):
    carpeta, producto, registro = abrir(args)
    lista_decisiones = decisiones(carpeta)
    nodo = "P%d" % args.puerta
    if not (args.seguir or args.ajustar or args.descartar is not None or args.reabrir or args.automatico):
        raise Fallo("Elige una decisión: --seguir, --ajustar <sesión>, --descartar \"<motivo>\", --reabrir o, solo en "
                    "el modo autónomo que pidió el usuario, --automatico (aplica la recomendación de la skill).")
    if args.automatico and (args.reabrir or args.motivo):
        raise Fallo("--automatico solo aplica la recomendación de la skill: no lleva --motivo ni --reabrir.")
    if args.raiz:
        fijar_raiz(carpeta, producto, args.raiz)
        guardar(carpeta, producto)
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
        regenerar_reporte(carpeta)  # el reporte ya no muestra la decisión deshecha (feedback #50)
        actualizar_tablero(carpeta, producto)
        print("\n" + siguiente)
        return
    if not tipo_de(producto):
        raise Fallo("Falta el tipo de idea (`tipo`): sin él no hay criterios que evaluar.")
    previas = [previo for previo in DEPENDE[nodo] if previo.startswith("P")] + [
        "P%d" % n for n in range(1, args.puerta)]
    sin_decidir = [p for p in previas if not cumplido(producto, lista_decisiones, p)]
    if sin_decidir:
        raise Fallo("Antes hay que decidir seguir en la puerta %s." % sin_decidir[0][1])
    evaluados = evaluar_puerta(args.puerta, carpeta, producto, registro)
    resultado = veredicto(args.puerta, carpeta, producto, registro, evaluados)
    if args.automatico:  # modo autónomo (feedback #49): solo la recomendación de la skill, nunca en contra
        recomendada = resultado["recomienda"]
        pedida = "seguir" if args.seguir else "ajustar" if args.ajustar else "descartar" if \
            args.descartar is not None else None
        if pedida and (pedida != recomendada or (pedida == "ajustar" and args.ajustar != resultado["sesion"])):
            raise Fallo("--automatico solo aplica la recomendación de la skill: %s (veredicto: %s). Decidir otra cosa "
                        "es una decisión del usuario, sin --automatico y con --motivo." % (
                            texto_recomendacion(resultado), resultado["titulo"]))
        parada = parada_autonoma(args.puerta, carpeta, producto, registro, resultado)
        if parada:
            raise Fallo("Modo autónomo: aquí se detiene y le pregunta al usuario, porque %s. La decisión la toma el "
                        "usuario en su terminal, sin --automatico." % parada)
        args.seguir = recomendada == "seguir"
        args.ajustar = resultado["sesion"] if recomendada == "ajustar" else None
        args.descartar = motivo_descarte(resultado) if recomendada == "descartar" else None
    diferidos = resultado.get("diferidos") or []
    cumplidos = sum(1 for c in evaluados if c["cumple"])
    registro_decision = {
        "puerta": args.puerta, "fecha": ahora(), "desde": origen(), "tipo": tipo_de(producto), "vigente": True,
        "cumple": cumplidos, "total": len(evaluados),
        "criterios": [dict({"cumple": c["cumple"], "texto": c["texto"], "detalle": c["detalle"]}, **(
            {"diferido": True} if not c["cumple"] and c["clave"] in diferidos else {})) for c in evaluados],
        "criterios_cambiados": producto.get("criterios_cambios", []),
    }
    abiertas = [s for s in DEPENDE[nodo] if not cerrada(producto, s)]
    if args.seguir and abiertas:
        raise Fallo("Para seguir, antes cierra %s (`cerrar --sesion <id>`)." % texto_sesiones(abiertas))
    if args.ajustar and (args.ajustar not in SESION or nodo not in dependientes(args.ajustar)):
        raise Fallo("--ajustar lleva una sesión anterior a la puerta %d: %s" % (args.puerta, ", ".join(
            s["id"] for s in SESIONES if nodo in dependientes(s["id"]))))
    if args.descartar is not None and len(args.descartar.strip()) < 10:
        raise Fallo("--descartar lleva el motivo completo (qué evidencia en contra hay, o qué camino no "
                    "existe): es lo que queda como aprendizaje")
    tomada = "seguir" if args.seguir else "ajustar" if args.ajustar else "descartar"
    # ajustar otra sesión que la recomendada también va en contra: el registro dice por qué (feedback #26)
    contra = tomada != resultado["recomienda"] or (tomada == "ajustar" and args.ajustar != resultado["sesion"])
    motivo_usuario = (args.motivo or "").strip()
    if contra and len(motivo_usuario) < 10:
        raise Fallo("La skill recomienda %s (veredicto: %s; %s). Para %s en contra de la recomendación, agrega "
                    "--motivo \"<por qué decides distinto>\" (al menos 10 caracteres): queda registrado como decisión "
                    "contra la recomendación." % (texto_recomendacion(resultado), resultado["titulo"],
                                                  "; ".join(resultado["razones"]), "ajustar la sesión %s" % args.ajustar
                                                  if tomada == "ajustar" else tomada))
    registro_decision["recomendacion"] = {
        "veredicto": resultado["nivel"], "recomienda": resultado["recomienda"], "sesion": resultado["sesion"],
        "razones": resultado["razones"], "cambiaria": resultado["cambiaria"]}
    registro_decision["contra_recomendacion"] = contra
    if motivo_usuario:
        registro_decision["motivo_decision"] = motivo_usuario
    if args.automatico:
        registro_decision.update(automatica=True, por="decisión automática (modo autónomo)")
    if tomada == "seguir" and resultado.get("descarte"):  # Viable para probar: la puerta 3 y la medición lo usan
        registro_decision["criterio_descarte"] = resultado["descarte"]
    for decision in lista_decisiones:
        if decision["puerta"] == args.puerta:
            decision["vigente"] = False
    if args.automatico:
        print("· Decisión automática (modo autónomo): la skill aplicó su recomendación, %s (veredicto: %s; %s). Queda "
              "marcada para que la revises; si no la compartes: `%s`." % (
                  texto_recomendacion(resultado), resultado["titulo"], "; ".join(resultado["razones"]),
                  orden("decidir --puerta %d --reabrir" % args.puerta, carpeta)))
    elif contra:
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
            args.puerta, PUERTAS[args.puerta], cumplidos, len(evaluados)))
        sin_cumplir = len(evaluados) - cumplidos - len(diferidos)
        if sin_cumplir > 0:
            print("⚠ Sigues con %s sin cumplir: queda anotado en decisiones.json." % plural(sin_cumplir, "criterio"))
        if registro_decision.get("criterio_descarte"):
            print("· Viable para probar: la prueba de elección queda para después del lanzamiento. Criterio de "
                  "descarte: %s. La sesión 3 la registra como la hipótesis más riesgosa, con su métrica y su umbral, y "
                  "la puerta 3 pide que el MVP la ponga a prueba." % registro_decision["criterio_descarte"]["texto"])
        regenerar_reporte(carpeta)
        actualizar_tablero(carpeta, producto)
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
            anterior = producto["sesiones"].get(reabierta) or {}
            producto["sesiones"][reabierta] = {"reabierta": ahora(), "reaperturas": int(anterior.get(
                "reaperturas") or (1 if anterior.get("reabierta") else 0)) + 1}
            for clave in ("uso", "pasadas"):  # cada reapertura tiene su presupuesto: se conservan las anteriores
                if anterior.get(clave):
                    producto["sesiones"][reabierta][clave] = anterior[clave]
            linea_reabierta = next((n for n, (_, s) in LINEAS.items() if s == reabierta), None)
            if linea_reabierta:  # las fuentes de antes no cuentan para las lecturas de esta pasada
                producto["sesiones"][reabierta]["fuentes_base"] = sum(
                    1 for f in registro.fuentes.values() if f["linea"] == linea_reabierta and not f.get("extracto"))
        registro_decision.update(decision="ajustar", sesion=sesion)
        lista_decisiones.append(registro_decision)
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        guardar(carpeta, producto)
        siguiente = actualizar_estado(carpeta, producto)
        print("✔ Puerta %d · %s: ajustar la sesión %s" % (args.puerta, PUERTAS[args.puerta], sesion))
        print("· Se reabren: %s. Lo ya escrito se conserva: cada sesión corrige lo suyo y vuelve a cerrar." % (
            ", ".join(sorted(reabiertas, key=lambda s: [x["id"] for x in SESIONES].index(s))) or "ninguna"))
        lineas_sesion = lineas_de(reabiertas)
        herramienta = vacios_de_herramienta(producto, registro, lineas_sesion) if lineas_sesion else []
        if herramienta:
            print("⚠ %s tiene vacíos por límite de las herramientas (%s). Con las mismas herramientas, el ajuste da lo "
                  "mismo: antes, dale al agente un navegador o consigue un CSV de reseñas (references/investigacion.md "
                  "· Fuentes difíciles)." % (", ".join(sorted({v["linea"] for v in herramienta})), "; ".join(
                      "%s %s" % (DIMENSIONES[v["dimension"]], v["valor"]) for v in herramienta)))
        parciales = vacios_parciales(registro, lineas_sesion, "herramienta") if lineas_sesion else []
        if parciales:
            print("· Vacíos parciales por límite de las herramientas en lo que se ajusta: %s. Con las mismas "
                  "herramientas, esa parte seguirá sin leerse." % texto_parciales(parciales))
        regenerar_reporte(carpeta)
        actualizar_tablero(carpeta, producto)
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
        actualizar_tablero(carpeta, producto)
        print("Siguiente paso: no queda nada por hacer con esta idea. Para recuperarla: `%s`. Para evaluar otra: "
              "`nuevo --nombre \"<nombre>\"`." % orden("reabrir --idea %s" % destino.name, carpeta))


# ---------------------------------------------------------------------------------------------------------------
# Modo orquestado (references/orquestacion.md): `siguiente --json` da el paso en una línea de JSON, para que el chat
# orquestador decida sin interpretar texto. El mismo diseño que hb-performance: un subagente por sesión con el modelo
# de su nivel, en paralelo lo que se puede, y una parada en cada puerta, donde decide el usuario en su terminal.

FORMATO_JSON = 1


def alias_subagente(producto, nivel):
    """El alias de familia para un subagente de Claude Code (haiku, sonnet, opus o fable), según el modelo del nivel;
    None si es de otro proveedor (el orquestador usa el equivalente de su herramienta)."""
    for palabra in re.split(r"[\s_.-]+", modelo_de(producto, nivel).lower()):
        if palabra in FAMILIAS_CLAUDE:
            return palabra
    return None


def paso_sesion(carpeta, producto, sesion):
    datos = SESION[sesion]
    nivel = datos["modelo"]
    return {"tipo": "sesion", "quien": "subagente", "requiere_persona": sesion == "0", "sesion": sesion,
            "nombre": datos["nombre"], "nivel": nivel, "modelo": modelo_de(producto, nivel), "esfuerzo": ESFUERZO[nivel],
            "subagente": {"modelo": alias_subagente(producto, nivel), "esfuerzo": ESFUERZO_CLI[ESFUERZO[nivel]]},
            "referencia": datos["lee"], "texto": texto_sesion(carpeta, producto, sesion),
            "reapertura": int((producto["sesiones"].get(sesion) or {}).get("reaperturas") or 0)}


def datos_orquestador(carpeta, producto=None):
    """El chat orquestador: el nivel económico, con esfuerzo bajo (solo corre producto.py y lanza subagentes)."""
    nivel = "economico"
    modelo = modelo_de(producto or {}, nivel)
    return {"modelo": modelo, "esfuerzo": ESFUERZO[nivel],
            "abrir": "cd %s && claude --model %s --effort %s" % (shlex.quote(str(carpeta.parent)), id_modelo(
                modelo, "claude"), ESFUERZO_CLI[ESFUERZO[nivel]])}


def datos_automatico(numero_puerta, carpeta, producto, registro, resultado):
    """Lo que necesita el modo autónomo en una puerta (feedback #49), determinista: el comando `decidir --automatico`
    listo (aplica la recomendación de la skill), la decisión que tomaría, cuántas veces se ajustó ya esa sesión en esa
    puerta y si hay que detenerse (el tercer ajuste de la misma sesión, o algo que solo el usuario puede dar)."""
    parada = parada_autonoma(numero_puerta, carpeta, producto, registro, resultado)
    sesion = resultado["sesion"] if resultado["recomienda"] == "ajustar" else None
    return {"comando": orden("decidir --puerta %d --automatico" % numero_puerta, carpeta),
            "decision": resultado["recomienda"], "sesion": sesion,
            "ajustes_previos": ajustes_previos(decisiones(carpeta), numero_puerta, sesion) if sesion else 0,
            "detener": bool(parada), "motivo": parada}


def siguiente_json(carpeta):
    """El paso siguiente como datos: {formato, tipo, quien, requiere_persona, motivo, pasos, en_paralelo, esperan,
    avisos, costo, …}. `quien` es subagente (lanzar `pasos` a la vez), usuario (una puerta: se detiene) o nadie."""
    base = {"formato": FORMATO_JSON, "skill": VERSION, "carpeta_skill": str(Path(GUION).parent.parent),
            "carpeta": str(carpeta), "estado": str(carpeta / "estado.md"), "orquestador": datos_orquestador(carpeta)}
    if not (carpeta / "producto.json").exists():
        archivadas = ideas_archivadas(carpeta)
        if archivadas:
            return dict(base, tipo="fin", quien="nadie", requiere_persona=False, pasos=[], titulo="sin idea activa",
                        motivo="No hay ninguna idea activa; archivadas: %s. Reabrir una o empezar otra lo decide el "
                               "usuario." % ", ".join(r.name for r in archivadas))
        producto = {"modelos": {}, "sesiones": {}}
        paso = paso_sesion(carpeta, producto, "0")
        paso["texto"] = "Usa hb-product: <pedido del usuario, tal cual>. Carpeta: %s. No hagas commit ni push." % carpeta
        # modo autónomo (#49): la sesión 0 no pregunta; lo que falta va a «Supuestos sin confirmar» de 00-idea.md
        paso["texto_autonomo"] = ("Usa hb-product en modo autónomo, sin preguntas: <la descripción del usuario, tal "
                                  "cual, o la ruta del archivo que la trae>. No hagas la entrevista: toma lo que diga "
                                  "la descripción y lo que falte va en «Supuestos sin confirmar» de 00-idea.md, con "
                                  "el valor que elegiste y por qué. Carpeta: %s. No hagas commit ni push." % carpeta)
        return dict(base, tipo="sesion", quien="subagente", requiere_persona=True, titulo="sesión 0 · idea",
                    motivo="la sesión 0 entrevista al usuario: el subagente devuelve sus preguntas y el orquestador "
                           "se las hace", pasos=[paso], en_paralelo=False, esperan=[], avisos=[], costo=None)
    with bloqueo(carpeta):
        producto = cargar(carpeta)
        registro = Registro(carpeta, producto["criterios"])
        actualizar_estado(carpeta, producto)
    avisos = avisos_siguiente(carpeta, producto, registro)
    costo = {"sin_anotar": sin_consumo(producto), "anotado": texto_total(producto.get("consumo") or [])
             if producto.get("consumo") else None,
             "comando_sesion": orden("consumo --sesion <id> --tokens '<tokens>' --pasos '<pasos>' --modelo "
                                     "'<modelo>'", carpeta),
             "sin_orquestador": sin_orquestador(producto),
             "comando_orquestador": comando_orquestador(carpeta, producto),
             "recordatorio": recordatorio_costo(carpeta, producto),
             "orquestador_anotado": any(f["sesion"] == "orquestador" for f in producto.get("consumo") or [])}
    base.update(titulo="%s (idea %s)" % (producto["nombre"], texto_tipo(producto)), avisos=avisos, costo=costo,
                reporte=str(carpeta / REPORTE), orquestador=datos_orquestador(carpeta, producto))
    if producto.get("archivo"):
        return dict(base, tipo="fin", quien="nadie", requiere_persona=False, pasos=[],
                    motivo="la idea está archivada. Repite el recordatorio de /cost (costo.recordatorio) en el mensaje "
                           "final")
    abiertas = sesiones_abiertas(carpeta, producto)
    if abiertas:
        # En primer plano y por tandas (feedback #38): 1a y 1b primero (la 1a confirma el tipo); al cerrar las dos, la
        # 1g arranca junto con 1c, 1d y 1e. Así ninguna tanda queda en segundo plano y la 1g no espera a las demás.
        tanda = abiertas
        primeras = [s for s in abiertas if s in ("1a", "1b")]
        if primeras and any(s in ("1c", "1d", "1e") for s in abiertas):
            tanda = primeras
        esperan = [s for s in ("1c", "1d", "1e", "1g", "1f") if not cerrada(producto, s) and s not in tanda
                   and cerrada(producto, "0")]
        pasos_ = [dict(paso_sesion(carpeta, producto, s), plano="primero") for s in tanda]
        return dict(base, tipo="sesion", quien="subagente", requiere_persona=tanda == ["0"], plano="primero",
                    motivo="lanza un subagente por sesión, todos en un solo mensaje y en primer plano (nunca en segundo "
                           "plano): tu turno sigue mientras corren; espera a que terminen todos, anota el consumo de "
                           "cada uno con lo que trae su resultado y vuelve a pedir el paso",
                    pasos=pasos_, en_paralelo=len(pasos_) > 1, esperan=esperan)
    lista_decisiones = decisiones(carpeta)
    for numero_puerta in PUERTAS:
        nodo = "P%d" % numero_puerta
        if disponible(producto, lista_decisiones, nodo) and not cumplido(producto, lista_decisiones, nodo):
            resultado = veredicto(numero_puerta, carpeta, producto, registro)
            lineas, cumplidos, total = bloque_puerta(numero_puerta, carpeta, producto, registro, resultado)
            paso = {"tipo": "puerta", "quien": "usuario", "requiere_persona": True, "donde": "terminal",
                    "puerta": numero_puerta, "nombre": PUERTAS[numero_puerta], "cumple": cumplidos, "total": total,
                    "veredicto": {clave: resultado[clave] for clave in ("nivel", "titulo", "recomienda", "sesion",
                                                                        "razones", "cambiaria", "provisional")},
                    "recomendacion": texto_recomendacion(resultado),
                    "opciones": opciones_decision(numero_puerta, carpeta, producto, resultado),
                    "automatico": datos_automatico(numero_puerta, carpeta, producto, registro, resultado),
                    "texto": "\n".join(lineas)}
            return dict(base, tipo="puerta", quien="usuario", requiere_persona=True, pasos=[paso], donde="terminal",
                        motivo="puerta %d: arriba, el recordatorio de /cost (costo.recordatorio); después, la puerta. La "
                               "decisión es del usuario: corre el comando en su terminal y escribe «continúa». El "
                               "orquestador nunca corre decidir, salvo en el modo autónomo que pidió el usuario: ahí "
                               "corre pasos[0].automatico.comando si pasos[0].automatico.detener es false" %
                               numero_puerta)
    return dict(base, tipo="fin", quien="nadie", requiere_persona=False, pasos=[],
                motivo="el proceso cerró: el PRD está aprobado; la construcción la hace hb-implement. Repite el "
                       "recordatorio de /cost (costo.recordatorio) en el mensaje final")


def cmd_siguiente(args):
    carpeta = resolver_carpeta(args)
    if args.json:
        try:
            datos = siguiente_json(carpeta)
        except Fallo as fallo:
            print(json.dumps({"formato": FORMATO_JSON, "skill": VERSION, "tipo": "error", "quien": "usuario",
                              "requiere_persona": True, "motivo": str(fallo), "pasos": []}, ensure_ascii=False))
            raise SystemExit(1)
        print(json.dumps(datos, ensure_ascii=False))
        return
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
    if args.raiz:
        fijar_raiz(carpeta, producto, args.raiz)
    destino = mover_a_archivo(carpeta, producto, args.motivo.strip(), "archivada a mano")
    print("✔ Idea \"%s\" archivada en %s (no se borra nada)" % (producto["nombre"], destino))
    regenerar_reporte(destino)
    actualizar_tablero(carpeta, producto)
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
    if args.raiz:
        fijar_raiz(carpeta, producto, args.raiz)
    lista_decisiones = decisiones(carpeta)
    for decision in lista_decisiones:
        if decision["decision"] == "descartar":
            decision["vigente"] = False
    escribir_json(carpeta / "decisiones.json", lista_decisiones)
    guardar(carpeta, producto)
    siguiente = actualizar_estado(carpeta, producto)
    print("✔ Idea \"%s\" reabierta (estaba archivada: %s)" % (producto["nombre"], anterior.get("motivo", "")))
    regenerar_reporte(carpeta)
    actualizar_tablero(carpeta, producto)
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
                       "baja": ("Viable con confianza baja", "aviso",
                                "Cumple los criterios, pero su evidencia no está confirmada por 3 fuentes."),
                       "paridad": ("No viable · paridad", "mal", "Iguala a la alternativa gratis más fuerte: es lo "
                                   "básico para competir, no una razón para elegir esta app."),
                       "no": ("No viable", "mal", "Le falta al menos un criterio.")}
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
main{max-width:980px;margin:0 auto;padding:24px 16px 48px;overflow-wrap:break-word}
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
.chip{display:inline-block;max-width:100%;border-radius:999px;padding:2px 10px;font-size:.85rem;font-weight:600;
white-space:normal;overflow-wrap:anywhere}
.bien{color:var(--bien);background:var(--bien-f)}.aviso{color:var(--aviso);background:var(--aviso-f)}
.mal{color:var(--mal);background:var(--mal-f)}.neutro{color:var(--neutro);background:var(--neutro-f)}
.estado{font-size:1rem;padding:4px 14px}
.ref{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--texto-2);overflow-wrap:anywhere}
.nota{color:var(--texto-2);font-size:.9rem}
.dato{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1.4fr) minmax(0,auto);gap:6px 14px;align-items:center;
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
.recorrido{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:2px 0 10px}
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


def pagina(titulo, cuerpo, cabeza=""):
    return ("<!doctype html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n%s<title>%s</title>\n"
            "<style>%s</style>\n</head>\n<body>\n<main>\n%s\n</main>\n</body>\n</html>\n" % (
                cabeza, escape(titulo), ESTILO, cuerpo))


def enlace(fuente):
    """El enlace de una fuente; un CSV del usuario va como texto (es un archivo local)."""
    nombre = fuente.get("autor") or fuente.get("dominio") or fuente["id"]
    if str(fuente.get("url", "")).startswith(("http://", "https://")):
        return '<a href="%s" rel="noopener noreferrer">%s</a>%s' % (
            escape(fuente["url"], quote=True), escape(nombre),
            ' <span class="nota">(extracto de búsqueda: no se abrió la página)</span>' if fuente.get("extracto")
            else "")
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


def recorrido(carpeta):
    """El recorrido por las puertas (feedback #45): cada decisión, en orden, con el veredicto que la skill dio en ese
    momento y lo que se decidió: [{puerta, nivel, texto, tono}]."""
    pasos = []
    for decision in decisiones(carpeta):
        if decision.get("decision") == "reabierta":  # `decidir --reabrir` deshace una decisión que no fue del usuario
            for indice in range(len(pasos) - 1, -1, -1):
                if pasos[indice]["puerta"] == decision["puerta"]:
                    del pasos[indice]
                    break
            continue
        if decision.get("decision") not in DECISIONES_LLANO:
            continue
        nivel = (decision.get("recomendacion") or {}).get("veredicto")
        hecho = {"seguir": "seguir", "ajustar": "ajustar %s" % (decision.get("sesion") or ""),
                 "descartar": "descartada"}[decision["decision"]]
        if decision.get("contra_recomendacion"):
            hecho += " contra la recomendación"
        if decision.get("automatica"):
            hecho += " (automática)"
        pasos.append({"puerta": decision["puerta"], "nivel": nivel, "tono": VEREDICTOS[nivel]["tono"]
                      if nivel in VEREDICTOS else "neutro",
                      "texto": "P%d%s → %s" % (decision["puerta"], " %s" % VEREDICTOS[nivel]["marca"]
                                               if nivel in VEREDICTOS else "", hecho)})
    return pasos


def titulo_final(estado):
    """'Descartada en la puerta 3', 'Pausada' o 'Lista para construir': el titular de una idea que ya no está en curso;
    None si sigue en curso."""
    if estado["clave"] == "descartada":
        ultima = estado.get("ultima")
        return "Descartada%s" % (" en la puerta %d" % ultima["puerta"] if ultima and ultima.get("decision") ==
                                 "descartar" else "")
    return {"pausada": "Pausada (archivada a mano)", "lista": "Lista para construir"}.get(estado["clave"])


def html_recorrido(pasos):
    return '<div class="recorrido"><b>Recorrido:</b> %s</div>' % " ".join(
        chip(p["texto"], p["tono"]) for p in pasos) if pasos else ""


def seccion_veredicto(info, compacto=False, estado=None, pasos=None):
    """El banner grande y con color del veredicto de la skill: arriba del reporte y, compacto, en el tablero. En una
    idea descartada, pausada o lista para construir, el titular es ese estado final, con el recorrido por las puertas
    debajo; el veredicto de la última puerta, recalculado hoy, queda como dato secundario (feedback #45)."""
    final = titulo_final(estado) if estado else None
    if final:
        tono = TONO_ESTADO[estado["clave"]]
        cabeza = '<p class="titulo">%s %s</p>' % (escape(ESTADOS_IDEA[estado["clave"]][1]), escape(final))
        motivo = '<p><b>Motivo:</b> %s</p>' % escape(estado["motivo"]) if estado.get("motivo") else ""
        if compacto:
            return '<div class="veredicto compacto %s">%s%s</div>' % (tono, cabeza, html_recorrido(pasos))
        partes = [cabeza, html_recorrido(pasos), motivo]
        if info:
            resultado = info["resultado"]
            datos = VEREDICTOS[resultado["nivel"]]
            partes.append('<h3>La puerta %d, recalculada hoy con las reglas actuales</h3><p>%s %s · la skill '
                          'recomienda: %s</p>' % (resultado["puerta"], datos["marca"], escape(datos["titulo"]),
                                                  escape(texto_recomendacion(resultado))))
            partes.append("<details><summary>Por qué y qué cambiaría el veredicto</summary><ol>%s</ol><ul>%s</ul>"
                          "</details>" % ("".join("<li>%s</li>" % escape(r) for r in resultado["razones"]),
                                          "".join("<li>%s</li>" % escape(c) for c in resultado["cambiaria"])))
        partes.append('<p class="nota">La skill recomienda con reglas fijas; la decisión es tuya.</p>')
        return '<section class="veredicto %s">%s</section>' % (tono, "".join(partes))
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
        return '<div class="veredicto compacto %s">%s<p class="nota">%s</p>%s</div>' % (
            datos["tono"], titulo, escape(resultado["razones"][0] + "." if resultado["razones"] else ""),
            html_recorrido(pasos))
    partes = [titulo, html_recorrido(pasos), '<p class="nota">Veredicto %s.%s</p>' % (escape(cuando), escape(
        " Provisional: falta cerrar %s." % ", ".join("la sesión %s" % s for s in resultado["provisional"]))
        if resultado["provisional"] else "")]
    partes.append("<h3>Por qué</h3><ol>%s</ol>" % "".join("<li>%s</li>" % escape(r) for r in resultado["razones"]))
    partes.append("<h3>Qué cambiaría el veredicto</h3><ul>%s</ul>" % "".join(
        "<li>%s</li>" % escape(c) for c in resultado["cambiaria"]))
    if resultado.get("descarte"):
        partes.append("<h3>Criterio de descarte después del lanzamiento</h3><p>%s.</p>" % escape(primera_mayuscula(
            resultado["descarte"]["texto"])))
    if decision:
        tomada = DECISIONES_LLANO[decision["decision"]].lower() + (
            " la sesión %s" % decision["sesion"] if decision.get("sesion") else "")
        if decision.get("automatica"):
            partes.append("<p>%s La skill decidió %s, su propia recomendación, en el modo autónomo que pediste. "
                          "Revísala: si no la compartes, reábrela y decide tú (<code>decidir --puerta %d --reabrir"
                          "</code>).</p>" % (chip("Decisión automática (modo autónomo)", "aviso", "⚙"), escape(tomada),
                                              decision["puerta"]))
        elif decision.get("contra_recomendacion"):
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


def hallazgos_citados(registro, texto):
    """Los hallazgos que sostienen un texto (un motivo): los que nombra (H-…) y, si nombra un competidor (C-…) o un
    diferenciador (D-…), los enlazados a ellos (feedback #45): de un competidor, primero los de las comparaciones
    (`frente`) con él y después los que lo nombran; de un diferenciador, los suyos y los de sus comparaciones."""
    ids = re.findall(r"\bH-[A-Z]{3}-\d+\b", texto or "")
    for competidor in dict.fromkeys(re.findall(r"\bC-\d+\b", texto or "")):
        fila = registro.competidores.get(competidor)
        if fila:
            ids += hallazgos_frente(registro, [fila]) + nombrados(registro, [fila])
    for identificador in dict.fromkeys(re.findall(r"\bD-\d+\b", texto or "")):
        if identificador in registro.diferenciadores:
            ids += registro.hallazgos_de(registro.diferenciadores[identificador])
    return list(dict.fromkeys(ids))


def hallazgos_decisivos(producto, registro, estado, info, maximo=5):
    """Los 3 a 5 hallazgos que decidieron: los que sostienen el motivo (los que cita y los enlazados a los competidores
    y diferenciadores que nombra), los de los criterios que fallaron, los que sostienen el veredicto y, si faltan, los
    clave de menor confianza."""
    motivos = [estado.get("motivo") or ""]
    textos = []
    if info and info["decision"]:
        motivos.append(info["decision"].get("motivo") or "")
        motivos.append(info["decision"].get("motivo_decision") or "")
        textos += [c.get("detalle", "") for c in info["decision"].get("criterios", []) if not c.get("cumple")]
    ids = [i for texto in motivos for i in hallazgos_citados(registro, texto)]
    ids += [i for texto in textos for i in re.findall(r"\bH-[A-Z]{3}-\d+\b", texto)]
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
    vigente_ = puntaje_vigente(producto, registro)
    cifras = [
        ("%d/25" % vigente_["total"] if puntaje else "—", "puntaje (mínimo %d)%s" % (
            minimo, "; se registró %d/25" % puntaje["total"] if puntaje and vigente_["total"] != puntaje["total"]
            else "")),
        (NIVELES[global_].capitalize() if puntaje else "—", "confianza global"),
        ("%d de %d" % (len(registro.viables()), len(registro.diferenciadores)), "diferenciadores viables"),
        ("%d de %d" % (confirmados, len(claves)), "hallazgo clave confirmado" if len(claves) == 1
         else "hallazgos clave confirmados"),
        (str(len(registro.fuentes)), "fuentes registradas"),
    ]
    partes.append('<div class="cifras">%s</div>' % "".join(
        '<div class="cifra"><b>%s</b><span>%s</span></div>' % (escape(v), escape(t)) for v, t in cifras))
    if vigente_ and vigente_["incoherencias"]:
        partes.append("<p>%s Con las reglas de hoy el puntaje es %d/25; se registró %d/25 con reglas anteriores (o la "
                      "evidencia cambió después). %s.</p>" % (chip("Puntaje recalculado", "aviso", "⚠"),
                                                              vigente_["total"], puntaje["total"], escape("; ".join(
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
    vigente_ = puntaje_vigente(producto, registro)
    filas = []
    for criterio in CRITERIOS_PUNTAJE:
        nombre, pregunta = CRITERIOS_LLANO[criterio]
        valor, nivel = vigente_["valores"][criterio], por_criterio[criterio]
        if valor != puntaje["valores"][criterio]:
            pregunta += " · se registró %d" % puntaje["valores"][criterio]
        if nivel is None:
            confianza = chip("estimación" if criterio == "facilidad" else "sin diferenciador", "neutro")
        else:
            confianza = chip("confianza " + NIVELES[nivel], TONO_CONFIANZA[nivel])
        filas.append('<div class="dato"><div><h3>%s · %d de 5</h3><span class="nota">%s</span></div>%s<div>%s</div>'
                     '</div>' % (escape(nombre), valor, escape(pregunta), barra(valor, 5, "%s: %d de 5" % (
                         nombre, valor)), confianza))
    nueva = tipo_de(producto) == "nueva"
    minimo = int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
    total = vigente_["total"]
    filas.append('<div class="dato"><div><h3>Total · %d de 25</h3><span class="nota">%sLa línea punteada es el mínimo '
                 'de la puerta 1: %d.</span></div>%s<div>%s</div></div>' % (
                     total, "Se registró %d/25. " % puntaje["total"] if total != puntaje["total"] else "", minimo,
                     barra(total, 25, "Total: %d de 25 (mínimo %d)" % (total, minimo), marca=minimo),
                     chip("alcanza el mínimo" if total >= minimo else "no alcanza el mínimo",
                          "bien" if total >= minimo else "mal", "✔" if total >= minimo else "✖")))
    texto = ('<p class="nota">Cada criterio va de 1 a 5 con anclas fijas. La confianza dice qué tan sólida es la '
             'evidencia detrás de cada número; la global es la más baja: <b>%s</b>.</p>' % escape(NIVELES[global_]))
    if puntaje.get("mitigacion"):
        texto += "<p><b>Mitigación del riesgo de políticas:</b> %s</p>" % escape(puntaje["mitigacion"])
    if vigente_["incoherencias"]:
        texto += ("<p>%s Con las reglas de hoy el puntaje es <b>%d/25</b>; se registró %d/25 el %s con reglas "
                  "anteriores, o la evidencia cambió después:</p><ul>%s</ul>" % (
                      chip("Puntaje recalculado", "aviso", "⚠"), vigente_["total"], puntaje["total"],
                      escape(fecha_corta(puntaje.get("fecha"))),
                      "".join("<li>%s</li>" % escape(i) for i in vigente_["incoherencias"])))
    if puntaje.get("alternativos"):
        modelos = puntajes_por_modelo(producto, registro)
        texto += "<p><b>Con cada modelo de monetización:</b> %s.%s</p>" % (escape("; ".join(
            "%s %s" % (m["modelo"], texto_puntaje(m)) for m in modelos)), escape(
            " Alcanza el mínimo solo con %s: la sesión 2 tiene que elegirlo." % modelo_exigido(producto, registro)[
                "modelo"]) if modelo_exigido(producto, registro) else "")
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
            if decision.get("automatica"):
                estado += chip("Decisión automática: revísala", "aviso", "⚙")
                linea += " La tomó la skill en el modo autónomo, con su recomendación: revísala o reábrela."
            if decision.get("criterio_descarte"):
                linea += " Criterio de descarte después del lanzamiento: %s." % decision["criterio_descarte"]["texto"]
            criterios = [(True if c["cumple"] else None if c.get("diferido") else False, c["texto"],
                          c.get("detalle", "")) for c in decision.get("criterios", [])]
            cuando = "al decidir"
        elif not producto.get("archivo") and disponible(producto, lista_decisiones, nodo):
            resultado = veredicto(numero_puerta, carpeta, producto, registro)
            criterios = [(True if c["cumple"] else None if c["clave"] in resultado["diferidos"] else False, c["texto"],
                          c["detalle"]) for c in evaluar_puerta(numero_puerta, carpeta, producto, registro)]
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
                "<li>%s %s%s%s</li>" % ("✔" if c else "◐" if c is None else "✖", escape(t),
                                        (" · <span class=\"nota\">%s</span>" % escape(d)) if d else "",
                                        " · <span class=\"nota\">se prueba después del lanzamiento</span>"
                                        if c is None else "") for c, t, d in criterios))
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
    rivales = registro.rivales()
    texto = ('<p class="nota">Un diferenciador es la razón para elegir esta app y no otra. Es viable si tiene '
             'evidencia confirmada, se percibe, cabe en el presupuesto y supera a la alternativa gratis más fuerte '
             '(otra app o un sustituto). Igualarla no alcanza: es lo básico para competir.</p>')
    if rivales:
        texto += "<p>%s <b>Rival a superar:</b> %s.</p>" % (chip("Alternativa gratis más fuerte", "aviso", "⚠"),
                                                            escape("; ".join(texto_sustituto(c) if c["peldano"] == 4
                                                                             else nombre_fila(c) for c in rivales)))
    elif registro.sin_rival:
        texto += "<p><b>Sin rival gratis:</b> %s.</p>" % escape(registro.sin_rival["motivo"])
    items = []
    orden_estado = {"viable": 0, "baja": 1, "paridad": 2, "no": 3}
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
            escape(texto_publicada(f) + (" · %s" % CLASES_VIGENCIA[f["clase"]] if f.get("clase") else "")),
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
                                      'vigentes, una de ellas reciente (o, en políticas, con el texto oficial).</p>'
                   + bloques)


def seccion_peldanos(producto, registro):
    """Los hallazgos por peldaño de la escalera de una idea nueva (feedback #32): vigentes, vencidos y lo no buscado."""
    if tipo_de(producto) != "nueva":
        return ""
    filas = []
    for peldano, datos in sorted(conteo_peldanos(registro).items()):
        if datos["no_buscado"]:
            estado = chip("no buscado", "neutro")
        else:
            estado = "%s · %s%s" % (plural(datos["vigentes"], "vigente"), plural(datos["vencidos"], "vencido"),
                                    " · buscado sin resultado (%s)" % ", ".join(datos["sin_resultado"])
                                    if datos["sin_resultado"] else "")
        filas.append("<tr><td>%d · %s</td><td>%s</td></tr>" % (peldano, escape(PELDANOS_LLANO[peldano]),
                                                               estado if datos["no_buscado"] else escape(estado)))
    return tarjeta("Hallazgos por peldaño", '<p class="nota">Una idea nueva se investiga por analogía: cada peldaño se '
                   'aleja un paso de lo directo. Un hallazgo vencido no tiene ninguna fuente vigente; un peldaño sin '
                   'hallazgos ni búsquedas registradas no se buscó, y eso no es evidencia en contra.</p><div '
                   'class="tabla"><table><thead><tr><th>Peldaño</th><th>Hallazgos</th></tr></thead><tbody>%s</tbody>'
                   '</table></div>' % "".join(filas))


def seccion_competidores(registro):
    if not registro.competidores:
        return tarjeta("Competidores y sustitutos", '<p class="vacio">La matriz está vacía.</p>')
    quejas = {}
    for hallazgo in registro.hallazgos.values():
        for identificador in registro.referencias(hallazgo)[0]:
            quejas.setdefault(identificador, []).append(hallazgo["id"])
    filas = []
    for fila in sorted(registro.competidores.values(), key=lambda c: (c.get("peldano", 9), -(c.get("descargas")
                                                                                            or 0))):
        que = PELDANOS_LLANO.get(fila.get("peldano"), "")
        if fila.get("peldano") == 4:
            que += " · %s · %s" % (SUSTITUTOS.get(fila.get("sustituto"), "sin evaluar"),
                                   RESUELVE.get(fila.get("resuelve"), "sin evaluar"))
        if fila in registro.rivales():
            que += " · rival a superar"
        precio = " · ".join(str(v) for v in (fila.get("precio"), fila.get("modelo")) if v)
        filas.append("<tr><td>%s%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            escape(fila.get("nombre", "")), " ★" if registro.con_traccion(fila) else "", ref(fila["id"]), escape(que),
            escape(numero(fila["descargas"]) if fila.get("descargas") else "—"),
            escape(numero(fila["nota"]) if fila.get("nota") else "—"), escape(precio or "—"),
            '<details><summary>%s</summary><p class="ref">%s</p></details>' % (
                plural(len(quejas[fila["id"]]), "hallazgo"), escape(", ".join(quejas[fila["id"]])))
            if quejas.get(fila["id"]) else "—"))
    return tarjeta("Competidores y sustitutos", '<p class="nota">★ = con tracción (descargas sobre el umbral, '
                   'valoraciones sobre el umbral cuando no hay descargas publicadas, o respaldo institucional). Las descargas son acumuladas desde el lanzamiento: sirven de contexto, no '
                   'miden la demanda de hoy.</p><div class="tabla"><table>'
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
    parciales = vacios_parciales(registro)  # el vacío de algo que ya tiene fuentes, a la vista (feedback #51)
    for vacio, _ in parciales:
        mapa.setdefault(vacio["linea"], [])

    def chip_parcial(valor, vacio):
        return '<span title="%s">%s</span>' % (escape("Vacío parcial %s, %s: %s" % (
            vacio["id"], MOTIVOS_VACIO[vacio["motivo"]], vacio["texto"]), quote=True),
            chip("%s ✔ · ⚠ vacío parcial (%s)" % (valor, MOTIVOS_VACIO[vacio["motivo"]]), "aviso"))

    for linea, datos in mapa.items():
        celdas, mostrados = [], set()
        propios = [v for v, _ in parciales if v["linea"] == linea]
        for dimension, valor, estado, detalle in datos:
            if estado == "fuentes":
                suyos = [v for v in propios if v["dimension"] == dimension and normal(v["valor"]) == normal(valor)]
                mostrados.update(v["id"] for v in suyos)
                celdas.append(" ".join(chip_parcial(valor, v) for v in suyos) if suyos else chip("%s ✔" % valor, "bien"))
            elif estado == "vacio":
                vacios += 1
                celdas.append('<span title="%s">%s</span>' % (escape(MOTIVOS_VACIO[detalle["motivo"]] + ": "
                                                                     + detalle["texto"], quote=True),
                                                              chip("%s ⚠ %s" % (valor, MOTIVOS_VACIO[detalle["motivo"]]),
                                                                   "aviso")))
            else:
                huecos += 1
                celdas.append(chip("%s ✖ sin fuentes" % valor, "mal"))
        celdas += [chip_parcial(v["valor"], v) for v in propios if v["id"] not in mostrados]
        filas.append("<tr><td>%s</td><td>%s</td></tr>" % (escape(LINEAS_LLANO[linea]), " ".join(celdas)
                                                          or '<span class="nota">nada que cubrir</span>'))
    return tarjeta("Cobertura por mercado, idioma y tienda", '<p class="nota">Objetivo: mercados %s · idiomas %s · '
                   'tiendas %s. %s sin explicar y %s con su motivo%s. Un vacío por límite de las '
                   'herramientas no es falta de evidencia.</p><div class="tabla"><table><thead><tr><th>Línea</th>'
                   '<th>Cobertura</th></tr></thead><tbody>%s</tbody></table></div>' % (
                       escape(", ".join(objetivo["mercados"]) or "—"), escape(", ".join(objetivo["idiomas"]) or "—"),
                       escape(", ".join(objetivo["tiendas"]) or "ninguna"), plural(huecos, "hueco"),
                       plural(vacios, "vacío"), "; %s: esa cobertura tiene fuentes, pero lo que dice el vacío "
                       "sigue sin leerse" % plural(len(parciales), "vacío parcial", "vacíos parciales")
                       if parciales else "", "".join(filas)))


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
    for aviso in escenarios.get("avisos") or []:  # el DAU de un comparable maduro infla el caso base (feedback #43)
        texto += "<p>%s %s.</p>" % (chip("Usuarios activos de un comparable maduro", "aviso", "⚠"), escape(llano(aviso)))
    derivados = [m for m, origen in (escenarios.get("dau_origen") or {}).items() if origen == "instalaciones"]
    if derivados:
        texto += ('<p class="nota">Usuarios activos de %s: derivados de las instalaciones nuevas y la retención (D1, D7 '
                  'y D30), como corresponde a una app nueva.</p>' % escape(y_lista(derivados)))
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
    descarte = criterio_descarte_vigente(carpeta)
    nota = ('<p>%s %s.</p>' % (chip("Criterio de descarte de la puerta 1", "aviso", "◐"), escape(primera_mayuscula(
        descarte["texto"]))) if descarte else "")
    if not filas:
        return tarjeta("Hipótesis más riesgosa", nota + '<p class="vacio">Sin validación documental todavía (sesión '
                                                        '3).</p>')
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
                                             'antes que nada.</p>' + nota + cuerpo)


TONO_POLITICA = {"cumple": "bien", "pendiente": "aviso", "bloqueo": "mal", "no aplica": "neutro"}


def seccion_prd(carpeta, producto, registro):
    """El resumen del PRD cuando la sesión 4 corrió (feedback #45): el MVP (dentro y fuera), las semanas contra el
    presupuesto, la trazabilidad, los criterios de aceptación, las métricas HEART y los requisitos de políticas."""
    if not producto["sesiones"].get("4"):  # la sesión 4 todavía no corrió: 04-prd.md es la plantilla
        return ""
    datos = prd(carpeta, registro)
    if not datos["existe"] or not datos["funciones"]:
        return ""
    mvp = [f for f in datos["funciones"] if f["mvp"]]
    fuera = [f for f in datos["funciones"] if not f["mvp"]]
    presupuesto = float(producto["criterios"].get("presupuesto_semanas") or 0)
    semanas = sum(f["semanas"] for f in mvp)
    trazadas = [f for f in mvp if not f["faltas"]]
    sin_criterios = criterios_sin_aceptacion(mvp)
    principal = registro.principal()
    cifras = [
        (str(len(mvp)), "funcionalidad en el MVP" if len(mvp) == 1 else "funcionalidades en el MVP"),
        ("%s de %s" % (numero(semanas), numero(presupuesto)), "semanas del presupuesto"),
        ("%d de %d" % (len(trazadas), len(mvp)), "con trazabilidad (evidencia y métrica)"),
        ("%d de %d" % (len(mvp) - len(sin_criterios), len(mvp)), "con criterios de aceptación"),
        (str(len(datos["metricas"])), "métrica HEART" if len(datos["metricas"]) == 1 else "métricas HEART"),
    ]
    partes = ['<p class="nota">El producto mínimo que se va a construir (sesión 4): cada funcionalidad enlaza a su '
              'evidencia y a la métrica que dirá si funciona. La construcción la hace hb-implement, una funcionalidad '
              'a la vez.</p>',
              '<div class="cifras">%s</div>' % "".join('<div class="cifra"><b>%s</b><span>%s</span></div>' % (
                  escape(v), escape(t)) for v, t in cifras)]
    if principal:
        dentro = [f["id"] for f in mvp if principal["id"] in f["diferenciadores"]]
        partes.append("<p>%s</p>" % (chip("El diferenciador principal está en el MVP (%s)" % ", ".join(dentro), "bien",
                                          "✔") if dentro else chip("El diferenciador principal no está en el MVP",
                                                                   "mal", "✖")))
    else:
        partes.append("<p>%s</p>" % chip("Sin diferenciador principal: el MVP no tiene una razón para elegir la app",
                                         "mal", "✖"))

    def item(funcion):
        estado_ = chip("con trazabilidad", "bien", "✔") if not funcion["faltas"] else chip(
            "falta: %s" % "; ".join(funcion["faltas"]), "mal", "✖")
        criterios = chip(plural(funcion["aceptacion"], "criterio de aceptación", "criterios de aceptación"),
                         "bien" if funcion["aceptacion"] else "mal") if funcion["mvp"] or funcion["aceptacion"] else ""
        return '<li><p><b>%s</b>%s</p><div class="fila">%s%s<span class="nota">%s · RICE %s%s</span></div></li>' % (
            escape(funcion["nombre"]), ref(funcion["id"]), estado_, criterios, escape(plural(funcion["semanas"],
                                                                                            "semana")),
            escape(numero(funcion["rice"]) if funcion["rice"] is not None else "—"),
            escape(" · materializa %s" % ", ".join(funcion["diferenciadores"]) if funcion["diferenciadores"] else ""))

    partes.append("<h3>Dentro del MVP</h3><ul class=\"lista\">%s</ul>" % "".join(item(f) for f in mvp) if mvp
                  else '<p class="vacio">Ninguna funcionalidad marcada como MVP.</p>')
    if fuera:
        partes.append("<details><summary>Fuera del MVP (%d)</summary><ul class=\"lista\">%s</ul></details>" % (
            len(fuera), "".join(item(f) for f in fuera)))
    if datos["detalle_metricas"]:
        partes.append("<details><summary>Métricas HEART (%d)</summary><ul>%s</ul></details>" % (
            len(datos["detalle_metricas"]), "".join("<li><b>%s</b> · %s: %s → %s%s</li>" % (
                escape(m["id"]), escape(m["dimension"]), escape(m["metrica"]), escape(m["meta"] or "sin meta"),
                "" if m["completa"] else " " + chip("incompleta", "mal")) for m in datos["detalle_metricas"])))
    if datos["politicas"]:
        partes.append("<details><summary>Requisitos de políticas (%d)</summary><ul>%s</ul></details>" % (
            len(datos["politicas"]), "".join("<li>%s %s%s</li>" % (
                chip(estado_ or "sin estado", TONO_POLITICA.get(estado_, "neutro")), escape(requisito),
                (' <span class="nota">· %s</span>' % escape(datos["notas"].get(requisito)))
                if datos["notas"].get(requisito) else "") for requisito, estado_ in datos["politicas"])))
    return tarjeta("PRD · el producto mínimo", "".join(partes))


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
                  "con reservas (recomienda ajustar una parte), Viable para probar o Viable (recomiendan seguir). La "
                  "decisión es tuya; si decides en contra, queda anotado con tu motivo."),
    ("Viable para probar", "Un diferenciador supera al rival con el dolor confirmado, pero falta la prueba de que eso "
                           "haga elegir la app, que casi nunca está en la web antes de lanzar. Se sigue con un criterio "
                           "de descarte: si a los días fijados después del lanzamiento las instalaciones orgánicas y la "
                           "retención no llegan al umbral, se descarta la idea o se cambia el diferenciador."),
    ("Decisión automática", "La tomó la skill en el modo autónomo que pediste, aplicando su propia recomendación. "
                            "Revísala: si no la compartes, reábrela y decide tú."),
    ("Hallazgo clave", "Una afirmación con fuentes de la que dependen el puntaje o una puerta."),
    ("Confirmado", "Tiene 3 fuentes independientes y vigentes (18 meses; 5 años para la estadística oficial y los "
                   "estudios académicos), una de ellas de los últimos 18 meses, y un dato medido si es de demanda o de "
                   "ingresos; en políticas basta el texto oficial."),
    ("Fecha aproximada", "Una fuente de la que solo se sabe el año cuenta desde el 1 de enero de ese año."),
    ("Confianza", "Qué tan sólida es la evidencia: alta, media, baja o sin evidencia. La calcula el script."),
    ("Sustituto", "Cómo se resuelve hoy la necesidad sin una app así: una función del sistema, una hoja de cálculo, "
                  "un grupo de chat."),
    ("Rival a superar", "La alternativa gratis más fuerte, sea otra app o un sustituto: cada diferenciador tiene que "
                        "superarla, y con prueba de que eso hace elegir la app."),
    ("Paridad", "Un diferenciador que solo iguala al rival: es lo básico para competir, no una razón para elegir la "
                "app."),
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
        cabecera, seccion_veredicto(info, estado=estado, pasos=recorrido(carpeta)),
        seccion_resumen(carpeta, producto, registro, estado, info),
        seccion_puntaje(producto, registro),
        seccion_puertas(carpeta, producto, registro), seccion_diferenciadores(producto, registro),
        seccion_hallazgos(registro), seccion_peldanos(producto, registro), seccion_competidores(registro),
        seccion_cobertura(producto, registro),
        seccion_escenarios(producto), seccion_hipotesis(carpeta, registro), seccion_prd(carpeta, producto, registro),
        seccion_costo(producto),
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
            '<li><div class="fila"><h3>%s</h3>%s%s<span class="nota">%s</span></div>'
            '<div class="dato"><div><b>Puntaje:</b> %s<br><span class="nota">%smínimo de la puerta 1: %d</span></div>'
            '%s<div class="nota"><b>Última puerta:</b> %s</div></div>%s<p><b>%s</b> %s</p></li>' % (
                '<a href="%s">%s</a>' % (escape(fila["enlace"], quote=True), escape(fila["nombre"]))
                if fila["enlace"] else escape(fila["nombre"]),
                '<span class="nota">%s</span>' % escape(fila["distingue"]) if fila.get("distingue") else "",
                chip(estado["etiqueta"], tonos[estado["clave"]], estado["icono"]) + (chip(
                    "Decisión automática en %s: revísala" % y_lista("P%d" % n for n in fila["automaticas"]), "aviso",
                    "⚙") if fila.get("automaticas") else ""),
                escape("idea %s" % fila["tipo"] if fila["tipo"] else "tipo sin registrar"),
                "%d/25" % puntaje if puntaje is not None else "sin puntaje",
                "se registró %d/25 · " % fila["registrado"] if fila.get("registrado") else "", fila["minimo"],
                barra(puntaje, 25, "%s: %d de 25" % (fila["nombre"], puntaje), marca=fila["minimo"])
                if puntaje is not None else "<span></span>",
                escape("puerta %d · %s · %s" % (ultima["puerta"], DECISIONES_LLANO[ultima["decision"]].lower(),
                                                 fecha_corta(ultima["fecha"])[:10]) if ultima else "ninguna"),
                seccion_veredicto(fila["veredicto"], compacto=True, estado=estado, pasos=fila["recorrido"]),
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
    return pagina("Tablero de ideas", cuerpo, MARCA_TABLERO + "\n")


# Tablero siempre al día (feedback #48): nuevo, cerrar, decidir, archivar y reabrir lo regeneran en la carpeta raíz de
# las ideas, sin pisar nunca un index.html que no generó `tablero`.
MARCA_TABLERO = '<meta name="generator" content="hb-product tablero">'


def es_tablero(ruta):
    """True si ese index.html lo generó `tablero`: con la marca de ahora o, uno anterior a la marca, con su título y su
    pie."""
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return MARCA_TABLERO in texto or ("<title>Tablero de ideas</title>" in texto and "Generado por hb-product" in texto)


def base_de_idea(carpeta):
    """La carpeta activa de una idea: la misma o, si está archivada (`<carpeta>/archivo/<nombre>/`), la de arriba."""
    carpeta = Path(os.path.abspath(str(carpeta)))
    return carpeta.parent.parent if carpeta.parent.name == "archivo" else carpeta


def en_repo(ruta):
    """True si la carpeta está dentro de un repositorio git (ella o alguna de arriba tiene `.git`)."""
    return any((r / ".git").exists() for r in [ruta] + list(ruta.parents))


def raiz_tablero(carpeta, producto):
    """La carpeta raíz de las ideas, donde vive el tablero: (ruta o None, de dónde sale). En este orden: la guardada en
    producto.json (`--raiz`, relativa a la carpeta de la idea, así sobrevive a archivarla o copiarla); si no, la carpeta
    más cercana hacia arriba que ya tiene un tablero (`<raíz>/<idea>/product/` y `<raíz>/<idea>/` funcionan igual); si
    no, la que contiene la carpeta de la idea, salvo dentro de un repositorio, donde un index.html nuevo puede servirse
    como página: ahí hace falta `--raiz`."""
    base = base_de_idea(carpeta)
    if producto.get("raiz"):
        return Path(os.path.normpath(str(base / producto["raiz"]))), "guardada"
    for ancestro in [base] + list(base.parents):
        if es_tablero(ancestro / TABLERO):
            return ancestro, "tablero"
    if en_repo(base.parent):
        return None, "repositorio"
    return base.parent, "carpeta de arriba"


def fijar_raiz(carpeta, producto, valor):
    """Guarda en producto.json la carpeta raíz de las ideas (`--raiz`), relativa a la carpeta de la idea."""
    raiz = Path(os.path.abspath(os.path.expanduser(valor)))
    if not raiz.is_dir():
        raise Fallo("--raiz: no existe la carpeta %s" % raiz)
    base = base_de_idea(carpeta)
    producto["raiz"] = os.path.relpath(str(raiz), str(base))
    if raiz != base and raiz not in base.parents:
        print("⚠ La idea no está dentro de %s: el tablero de esa carpeta no la va a listar." % raiz)
    return raiz


def actualizar_tablero(carpeta, producto, silencio=True):
    """Regenera el tablero de la carpeta raíz de las ideas después de un comando que cambia el estado de una idea.
    Nunca hace fallar el comando: si no puede, lo dice en una línea. No regenera ningún reporte (eso lo hacen las
    puertas, archivar, reabrir y `tablero`): una idea sin reporte todavía sale sin enlace."""
    try:
        raiz, motivo = raiz_tablero(carpeta, producto)
        if raiz is None:
            if not silencio:
                print("· Tablero: la carpeta está dentro de un repositorio y no tiene raíz fijada; para tenerlo al día, "
                      "fíjala con `--raiz <carpeta de tus ideas>` (por ejemplo, en `nuevo` o en `cerrar`).")
            return None
        destino = raiz / TABLERO
        if destino.exists() and not es_tablero(destino):
            print("⚠ Tablero sin actualizar: %s no lo generó `tablero` y no se pisa; fija otra raíz con `--raiz`." %
                  destino)
            return None
        destino, _, _ = escribir_tablero(raiz, reportes=False)
        print("· Tablero actualizado: %s" % destino)
        return destino
    except Exception as error:  # el tablero nunca deshace ni hace fallar el comando principal
        print("⚠ No se pudo actualizar el tablero (%s: %s); `tablero --raiz <carpeta>` lo reintenta." % (
            type(error).__name__, error))
        return None


def escribir_tablero(raiz, reportes=True):
    """Escribe <raíz>/index.html con las ideas que encuentra debajo: (destino, filas, fallidas). Con reportes, también
    regenera el reporte de cada idea. Nunca pisa un index.html que no generó `tablero`."""
    if not raiz.is_dir():
        raise Fallo("No existe la carpeta %s" % raiz)
    destino = raiz / TABLERO
    if destino.exists() and not es_tablero(destino):
        raise Fallo("%s no lo generó `tablero`: no se pisa. Muévelo o elige otra carpeta raíz." % destino)
    filas, fallidas = filas_tablero(raiz, reportes)
    escribir(destino, html_tablero(raiz, filas, fallidas))
    return destino, filas, fallidas


def filas_tablero(raiz, reportes=True):
    filas, fallidas = [], []
    for carpeta in buscar_ideas(raiz):
        try:
            producto = cargar(carpeta)
            registro = Registro(carpeta, producto["criterios"])
            ruta = carpeta / REPORTE
            if reportes:
                escribir(ruta, html_reporte(carpeta, producto, registro))
            info = veredicto_de_idea(carpeta, producto, registro)
        except (Fallo, KeyError, TypeError, ValueError) as error:
            fallidas.append((str(carpeta), "%s" % error))
            continue
        estado = estado_idea(carpeta, producto)
        nueva = tipo_de(producto) == "nueva"
        puntaje = producto.get("puntaje")
        vigente_ = puntaje_vigente(producto, registro)
        filas.append({
            "nombre": producto["nombre"], "tipo": tipo_de(producto) or "", "estado": estado,
            "puntaje": vigente_["total"] if puntaje else None,
            "registrado": puntaje["total"] if puntaje and puntaje["total"] != vigente_["total"] else None,
            "minimo": int(producto["criterios"]["puntaje_minimo_nueva" if nueva else "puntaje_minimo"]),
            "motivo": estado["motivo"] or paso_corto(carpeta, producto, registro),
            "veredicto": info, "recorrido": recorrido(carpeta),
            "automaticas": [d["puerta"] for d in decisiones(carpeta) if d.get("automatica") and d.get("vigente")],
            "enlace": Path(os.path.relpath(str(ruta), str(raiz))).as_posix() if ruta.exists() else None,
            "carpeta": Path(os.path.relpath(str(carpeta), str(raiz))).as_posix(), "creado": producto.get("creado", ""),
            "fecha": max([producto.get("creado", "")] + [d.get("fecha", "") for d in decisiones(carpeta)]
                         + [(estado["archivo"] or {}).get("fecha", "")]),
        })
    filas.sort(key=lambda f: f["fecha"], reverse=True)
    filas.sort(key=lambda f: ORDEN_ESTADOS.index(f["estado"]["clave"]))
    repetidos = {normal(f["nombre"]) for f in filas if sum(1 for g in filas if normal(g["nombre"]) == normal(
        f["nombre"])) > 1}
    for fila in filas:  # dos ideas con el mismo nombre se distinguen por su carpeta y su fecha de creación
        fila["distingue"] = "carpeta %s%s" % (fila["carpeta"], " · creada el %s" % fila["creado"] if fila["creado"]
                                              else "") if normal(fila["nombre"]) in repetidos else ""
    return filas, fallidas


def cmd_tablero(args):
    raiz = Path(os.path.abspath(os.path.expanduser(args.raiz)))
    destino, filas, fallidas = escribir_tablero(raiz)
    print("✔ Tablero con %s: %s" % (plural(len(filas), "idea"), destino))
    for fila in filas:
        info = fila["veredicto"]
        if titulo_final(fila["estado"]):  # el estado final con el recorrido por las puertas (feedback #45)
            detalle = " · %s" % " · ".join(p["texto"] for p in fila["recorrido"]) if fila["recorrido"] else ""
            print("  · %s · %s%s · %s" % (fila["nombre"] + (" (%s)" % fila["distingue"] if fila["distingue"] else ""),
                                          titulo_final(fila["estado"]), detalle, fila["enlace"]))
            continue
        print("  · %s · %s%s · %s" % (fila["nombre"] + (" (%s)" % fila["distingue"] if fila["distingue"] else ""),
                                      fila["estado"]["etiqueta"], " · %s %s (puerta %d), recomienda %s"
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


def agregar_raiz(sub):
    sub.add_argument("--raiz", help="la carpeta raíz de tus ideas, donde vive el tablero (index.html) que se regenera "
                                    "solo; queda guardada en producto.json")


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
    agregar_raiz(sub)

    sub = comando("criterio", cmd_criterio, "Muestra los criterios o cambia uno (después de la sesión 0, con motivo)")
    sub.add_argument("--clave")
    sub.add_argument("--valor")
    sub.add_argument("--motivo")

    sub = comando("tipo", cmd_tipo, "Muestra el tipo de idea o lo registra (provisional en la sesión 0; lo confirma 1a)")
    grupo = sub.add_mutually_exclusive_group()
    for tipo in TIPOS_IDEA:
        grupo.add_argument("--" + tipo, action="store_true")
    sub.add_argument("--motivo")
    sub.add_argument("--provisional", action="store_true",
                     help="sesión 0: el tipo del triaje, antes de lanzar las líneas; la sesión 1a lo confirma")

    sub = comando("fuente", cmd_fuente, "Registra una fuente y devuelve su ID (S-…)")
    sub.add_argument("--linea", required=True, help=", ".join(LINEAS))
    sub.add_argument("--url", help="la página pública")
    sub.add_argument("--archivo", help="un CSV de reseñas exportado por el usuario, en vez de --url")
    sub.add_argument("--publicada", required=True,
                     help="la fecha real de publicación (AAAA-MM-DD, AAAA-MM o AAAA si solo se sabe el año), "
                          "desconocida o, con --archivo, auto")
    sub.add_argument("--consultada", help="AAAA-MM-DD (por defecto, hoy)")
    sub.add_argument("--tipo", required=True, choices=TIPOS_FUENTE,
                     help="oficial: el texto de una política de tienda o de una ley (con --version o --publicada)")
    sub.add_argument("--version", help="versión o fecha de la norma, para --tipo oficial")
    sub.add_argument("--clase", choices=sorted(CLASES_VIGENCIA),
                     help="vigencia larga: estadistica (censo o encuesta nacional: hasta una edición más nueva, máximo "
                          "5 años) o academica (estudio académico: 5 años); sin ella, 18 meses")
    sub.add_argument("--reemplaza", metavar="S-…", help="con --clase estadistica: la edición anterior que reemplaza")
    sub.add_argument("--acumulado", action="store_true",
                     help="dato medido acumulado (descargas o valoraciones desde el lanzamiento): contexto, no señal "
                          "actual de demanda")
    sub.add_argument("--extracto", action="store_true",
                     help="lo visto solo en el extracto de un resultado de búsqueda, sin abrir la página: no cuenta "
                          "como lectura y queda marcado (cuenta para la confianza como cualquier fuente)")
    sub.add_argument("--peldano", required=True, type=int, choices=sorted(PELDANOS))
    sub.add_argument("--resumen", required=True, help="3 líneas como máximo")
    sub.add_argument("--autor", help="la app, la empresa o el medio que publica; nunca un nombre de usuario")
    sub.add_argument("--mercados", help="mercados del objetivo que cubre esta fuente (MX,ES)")
    sub.add_argument("--idiomas", help="idiomas del objetivo que cubre (es,pt)")
    sub.add_argument("--tiendas", help="tiendas del objetivo que cubre (google-play,app-store)")

    sub = comando("hallazgo", cmd_hallazgo, "Registra un hallazgo (H-…) y calcula su confianza. Con --id H-… "
                  "--competidor C-…, enlaza un hallazgo ya registrado a filas de la matriz (las que la 1a creó "
                  "después), sin cambiar su ID ni su confianza: solo agrega enlaces y sirve con la sesión ya cerrada. "
                  "Con --id H-… --fuentes S-…, le suma fuentes sin cambiar su ID y recalcula su confianza: pide la "
                  "sesión dueña del hallazgo abierta")
    sub.add_argument("--id", metavar="H-…", help="un hallazgo ya registrado: con --competidor, le agrega esos "
                                                  "competidores de la matriz; con --fuentes, le suma esas fuentes "
                                                  "(sin --linea ni --texto)")
    sub.add_argument("--linea", help="obligatorio sin --id: " + ", ".join(LINEAS))
    sub.add_argument("--texto", help="obligatorio sin --id")
    sub.add_argument("--fuentes", help="obligatorio sin --id: S-…,S-…")
    sub.add_argument("--en-contra", dest="en_contra", help="fuentes con evidencia en contra")
    sub.add_argument("--sin-contra", dest="sin_contra", help="qué se buscó en contra cuando no apareció nada")
    sub.add_argument("--critico", action="store_true", help="hallazgo clave: sostiene el puntaje o una puerta")
    sub.add_argument("--competidor", "--competidores", dest="competidores",
                     help="competidores a los que se refiere, por su ID en la matriz (C-3,C-5); sin fila todavía, por "
                          "la URL de su ficha o su nombre")
    sub.add_argument("--bloquea", help="línea politicas: tiendas del objetivo que nombran la categoría o la rechazan "
                                       "(google-play,app-store)")

    sub = comando("confianza", cmd_confianza, "Baja la confianza de un hallazgo, con su motivo (nunca la sube)")
    sub.add_argument("--hallazgo", required=True)
    sub.add_argument("--bajar", required=True, choices=("baja", "media"))
    sub.add_argument("--motivo", required=True)

    sub = comando("competidor", cmd_competidor, "Registra o completa una fila de la matriz de competidores (C-…)")
    sub.add_argument("--nombre", help="obligatorio, salvo con --sin-rival")
    sub.add_argument("--peldano", type=int, choices=(1, 2, 3, 4),
                     help="1 directo, 2 variante, 3 análogo, 4 sustituto (obligatorio, salvo con --sin-rival)")
    sub.add_argument("--fuentes", help="S-…,S-… (obligatorio, salvo con --sin-rival)")
    sub.add_argument("--rival", action="store_true",
                     help="la alternativa gratis más fuerte, sea sustituto o competidor directo: cada diferenciador "
                          "tiene que superarla (una sola; marcar otra reemplaza a la anterior)")
    sub.add_argument("--sin-rival", dest="sin_rival", metavar="MOTIVO",
                     help="en vez de una fila: por qué ninguna alternativa gratis resuelve la necesidad")
    sub.add_argument("--descargas", help="número, 100k o 1M")
    sub.add_argument("--valoraciones", help="cantidad de valoraciones, cuando la fuente no da descargas (App Store): "
                                            "tracción estimada desde `traccion_valoraciones`")
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
    sub.add_argument("--traccion", help="nota de tracción (contexto, no cuenta): cuentan --descargas desde el umbral "
                                        "o --respaldo")
    sub.add_argument("--respaldo", help="respaldo institucional que da tracción sin descargas (un ministerio, un "
                                        "organismo), documentado en las fuentes de la fila")
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

    sub = comando("vacio", cmd_vacio, "Registra un mercado, idioma o tienda del objetivo, o un peldaño, que quedó sin "
                                      "fuentes")
    sub.add_argument("--linea", required=True, help="cualquier línea: %s" % ", ".join(LINEAS))
    sub.add_argument("--mercado")
    sub.add_argument("--idioma")
    sub.add_argument("--tienda")
    sub.add_argument("--peldano", type=int, choices=sorted(PELDANOS),
                     help="un peldaño de la escalera que se buscó sin resultado (o no se pudo buscar), con su motivo")
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

    sub = comando("frente", cmd_frente, "Registra si un diferenciador supera, iguala o no al rival (sesión 1g)")
    sub.add_argument("--id", required=True, help="el diferenciador (D-…)")
    sub.add_argument("--rival", help="C-… (por defecto, el único rival)")
    sub.add_argument("--resultado", required=True, choices=sorted(COMPARACIONES),
                     help="supera, iguala (paridad: no cuenta como viable) o no")
    sub.add_argument("--hallazgos", required=True, help="H-…,H-…: la evidencia de la comparación")
    sub.add_argument("--texto", required=True, help="en qué lo supera o lo iguala, en una frase")

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
    sub.add_argument("--modelo", help="el modelo de monetización con el que puntúas (el base de la sesión 0)")
    sub.add_argument("--alternativo", action="append", metavar="MODELO=d,m,f,r,x",
                     help="el puntaje con otro modelo registrado en la sesión 0 (se repite por modelo)")

    sub = comando("escenarios", cmd_escenarios, "Casos pesimista, base y optimista, y usuarios para la meta")
    sub.add_argument("--entrada", required=True, help="JSON de supuestos (plantilla: escenarios.json)")

    comando("validacion", cmd_validacion, "Revisa la tabla de hipótesis de 03-validacion.md")
    comando("trazabilidad", cmd_trazabilidad, "Revisa la tabla de funcionalidades de 04-prd.md y calcula el RICE")

    sub = comando("cerrar", cmd_cerrar, "Cierra una sesión si su entregable está completo")
    sub.add_argument("--sesion", required=True, help=", ".join(SESION))
    sub.add_argument("--busquedas", help="sesiones de investigación: búsquedas usadas en esta pasada")
    sub.add_argument("--lecturas", help="sesiones de investigación: lecturas usadas en esta pasada")
    agregar_raiz(sub)

    sub = comando("puerta", cmd_puerta, "Veredicto de una puerta, criterio por criterio")
    sub.add_argument("--n", required=True, type=int, choices=(1, 2, 3))

    sub = comando("decidir", cmd_decidir, "Registra la decisión de una puerta. Solo lo corre el usuario")
    sub.add_argument("--puerta", required=True, type=int, choices=(1, 2, 3))
    grupo = sub.add_mutually_exclusive_group()
    grupo.add_argument("--seguir", action="store_true")
    grupo.add_argument("--ajustar", metavar="SESIÓN")
    grupo.add_argument("--descartar", metavar="MOTIVO")
    grupo.add_argument("--reabrir", action="store_true", help="deshace la decisión vigente de la puerta")
    sub.add_argument("--motivo", help="por qué decides distinto de la recomendación de la skill (obligatorio en ese "
                                      "caso; queda registrado)")
    sub.add_argument("--automatico", action="store_true",
                     help="solo en el modo autónomo que pidió el usuario: aplica la recomendación de la skill (rechaza "
                          "ir en contra) y la registra como decisión automática, para revisarla o reabrirla")
    agregar_raiz(sub)

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

    sub = comando("siguiente", cmd_siguiente, "El paso siguiente o los carriles paralelos, con el texto para cada chat")
    sub.add_argument("--json", action="store_true",
                     help="modo orquestado: el paso en una línea de JSON (references/orquestacion.md)")
    comando("estado", cmd_estado, "Resumen de la idea y el paso siguiente")

    sub = comando("reporte", cmd_reporte, "Genera reporte.html de la idea (un solo archivo, sin red)")
    sub.add_argument("--idea", help="una idea archivada: la carpeta dentro de archivo/")

    sub = comando("tablero", cmd_tablero, "Genera index.html con todas las ideas que encuentre bajo una carpeta")
    sub.add_argument("--raiz", required=True, help="la carpeta donde buscar las ideas (en curso y archivadas)")

    sub = comando("archivar", cmd_archivar, "Mueve la idea activa a archivo/ (no borra nada)")
    sub.add_argument("--motivo", required=True)
    agregar_raiz(sub)

    sub = comando("reabrir", cmd_reabrir, "Recupera una idea archivada")
    sub.add_argument("--idea", help="la carpeta dentro de archivo/")
    agregar_raiz(sub)
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
