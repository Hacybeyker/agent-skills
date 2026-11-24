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
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.1.0"
FORMATO = 1
CARPETA_DEFECTO = "product"
GUION = os.path.abspath(__file__)
PLANTILLAS = Path(GUION).parent.parent / "assets" / "plantillas"
PENDIENTE = "<por completar"
CANDADO = ".producto.lock"

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
TIPOS_FUENTE = ("medido", "usuario", "terceros", "opinion")
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
    "meta_ingresos_mes": 0,        # meta de ingresos netos al mes (sesión 0)
    "moneda": "USD",
    "presupuesto_semanas": 0,      # semanas para construir el MVP (sesión 0)
}
PRESUPUESTO = {"busquedas": 15, "lecturas": 10}
PRESUPUESTO_NUEVA = {"busquedas": 20, "lecturas": 12}
AMPLITUD_ANALOGIA = 0.5  # un escenario por analogía abre el rango: pesimista × 0,5 y optimista × 1,5
RICE_CONFIANZA = {3: 100, 2: 80, 1: 50, 0: 0}  # confianza del hallazgo → porcentaje de RICE

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
        for linea, datos in self.lineas.items():
            for campo, destino in (("fuentes", self.fuentes), ("hallazgos", self.hallazgos),
                                   ("matriz", self.competidores), ("diferenciadores", self.diferenciadores)):
                for item in datos.get(campo, []):
                    if not item.get("anulado"):
                        destino[item["id"]] = item

    def vigente(self, fuente):
        publicada = fuente.get("publicada")
        if not publicada:
            return False
        referencia, meses = hoy(), int(self.criterios["vigencia_meses"])
        limite = referencia.year * 12 + referencia.month - 1 - meses
        anio, mes, dia = (int(parte) for parte in publicada.split("-"))
        indice = anio * 12 + mes - 1
        return indice > limite or (indice == limite and dia >= referencia.day)

    def fuentes_de(self, ids):
        return [self.fuentes[i] for i in ids if i in self.fuentes]

    def evaluar(self, hallazgo):
        """La confianza de un hallazgo y el detalle de su triangulación (reglas 2 y 3)."""
        favor = self.fuentes_de(hallazgo.get("fuentes", []))
        minimo = int(self.criterios["fuentes_minimas"])
        exige = hallazgo.get("linea") in EXIGEN_MEDIDO
        mejor = None
        for peldano in range(1, 7):
            grupos = {}
            for fuente in favor:
                if fuente["peldano"] <= peldano and self.vigente(fuente):
                    grupos.setdefault(independencia(fuente), []).append(fuente)
            if not grupos:
                continue
            cantidad = len(grupos)
            fuertes = sum(1 for grupo in grupos.values() if any(f["tipo"] != "opinion" for f in grupo))
            medido = any(f["tipo"] == "medido" for grupo in grupos.values() for f in grupo)
            triangulado = cantidad >= minimo and (medido or not exige)
            if triangulado and fuertes >= 2:
                nivel = 3
            elif cantidad >= 2 and (fuertes >= 1 or cantidad >= minimo):
                nivel = 2
            else:
                nivel = 1
            nivel = min(nivel, PELDANOS[peldano][1])
            if mejor is None or (nivel, triangulado) > (mejor["nivel"], mejor["triangulado"]):
                mejor = {"nivel": nivel, "triangulado": triangulado, "peldano": peldano, "independientes": cantidad,
                         "medido": medido}
        vencidas = sum(1 for f in favor if not self.vigente(f))
        if mejor is None:
            mejor = {"nivel": 1 if favor else 0, "triangulado": False, "independientes": 0, "medido": False,
                     "peldano": min([f["peldano"] for f in favor] or [6])}
        contra = {independencia(f) for f in self.fuentes_de(hallazgo.get("en_contra", [])) if self.vigente(f)}
        calculada = mejor["nivel"]
        if contra and calculada:
            calculada = 1 if len(contra) >= mejor["independientes"] else max(1, calculada - 1)
        manual = hallazgo.get("confianza_manual")
        nivel = min(calculada, NIVELES.index(manual["nivel"])) if manual else calculada
        faltan = []
        if mejor["independientes"] < minimo:
            faltan.append("faltan %d fuente(s) independiente(s) y vigente(s) (tiene %d de %d)"
                          % (minimo - mejor["independientes"], mejor["independientes"], minimo))
        if exige and not mejor["medido"]:
            faltan.append("falta una fuente de tipo medido (línea %s)" % hallazgo["linea"])
        if vencidas:
            faltan.append("%d fuente(s) sin fecha o fuera de la ventana de %s meses"
                          % (vencidas, self.criterios["vigencia_meses"]))
        if not hallazgo.get("en_contra") and not hallazgo.get("sin_contra"):
            faltan.append("falta registrar la búsqueda de evidencia en contra (--en-contra o --sin-contra)")
        mejor.update(nivel=nivel, calculada=calculada, exige_medido=exige, contra=len(contra), vencidas=vencidas,
                     faltan=faltan, confianza=NIVELES[nivel])
        return mejor

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
            cabe = (0 < semanas <= presupuesto, "Presupuesto: %s semana(s) de %s" % (numero(semanas),
                                                                                    numero(presupuesto)))
        return [evidencia,
                (diferenciador.get("se_ve") in ("ficha", "uso"), "Se percibe: en %s" % (
                    "la ficha de la tienda" if diferenciador.get("se_ve") == "ficha" else "el uso")),
                (bool(diferenciador.get("copiable") and diferenciador.get("motivo")),
                 "Copiabilidad: %s (%s)" % (diferenciador.get("copiable"), diferenciador.get("motivo"))),
                cabe]

    def viable(self, diferenciador):
        return all(cumple for cumple, _ in self.viabilidad(diferenciador))

    def viables(self):
        return [d for d in self.diferenciadores.values() if self.viable(d)]

    def principal(self):
        return next((d for d in self.diferenciadores.values() if d.get("principal")), None)


def independencia(fuente):
    """Dos fuentes son independientes si son de autor distinto; sin autor, cuenta el dominio."""
    return normal(fuente.get("autor") or "") or fuente["dominio"]


def abrir(args):
    carpeta = resolver_carpeta(args)
    producto = cargar(carpeta)
    return carpeta, producto, Registro(carpeta, producto["criterios"])


def tipo_de(producto):
    return (producto.get("tipo") or {}).get("valor")


def presupuesto_de(producto):
    return PRESUPUESTO_NUEVA if tipo_de(producto) == "nueva" else PRESUPUESTO


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
    viables = registro.viables()
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
    criterios = producto["criterios"]
    nueva = tipo_de(producto) == "nueva"
    resultado = []

    def agregar(cumple, texto, detalle=""):
        resultado.append((bool(cumple), texto, detalle))

    if numero_puerta == 1:
        puntaje = producto.get("puntaje")
        minimo = int(criterios["puntaje_minimo_nueva" if nueva else "puntaje_minimo"])
        if puntaje:
            agregar(puntaje["total"] >= minimo, "Puntaje de %d/25 o más" % minimo, "tiene %d/25" % puntaje["total"])
        else:
            agregar(False, "Puntaje de %d/25 o más" % minimo, "sin registrar: corre `puntaje` en la sesión 1f")
        if nueva:
            minimas = int(criterios["fuentes_minimas"])
            documentado = None
            for hallazgo in registro.hallazgos.values():
                grupos = {independencia(f) for f in registro.fuentes_de(hallazgo["fuentes"])
                          if f["peldano"] in (4, 5) and registro.vigente(f)}
                if len(grupos) >= minimas:
                    documentado = hallazgo["id"]
                    break
            agregar(documentado, "El problema o la necesidad de fondo, con %d fuentes de peldaño 4 o 5" % minimas,
                    documentado or "ningún hallazgo reúne %d fuentes independientes y vigentes de esos peldaños"
                    % minimas)
            analogos = [c["id"] for c in registro.competidores.values()
                        if c["peldano"] in (2, 3) and registro.con_traccion(c)]
            pedidos = int(criterios["analogos_minimos"])
            agregar(len(analogos) >= pedidos, "Al menos %d análogos con tracción (peldaño 2 o 3)" % pedidos,
                    "%d en la matriz%s" % (len(analogos), (": " + ", ".join(analogos)) if analogos else ""))
            intentos = producto.get("intentos", [])
            fracasos = [i for i in intentos if i["resultado"] == "fracaso-demanda"]
            if not intentos:
                agregar(False, "Sin evidencia de que se probó y fracasó por falta de demanda",
                        "la búsqueda no está registrada: corre `intento`")
            else:
                agregar(not fracasos, "Sin evidencia de que se probó y fracasó por falta de demanda",
                        "%d intento(s) fallido(s) por demanda" % len(fracasos) if fracasos
                        else "%d búsqueda(s) registrada(s)" % len(intentos))
        else:
            nivel = confianzas(registro)[0]["demanda"]
            agregar(nivel >= 2, "Demanda con confianza media o alta", "es %s" % NIVELES[nivel])
            viables = registro.viables()
            agregar(viables, "Al menos 1 diferenciador viable",
                    "%d viable(s) de %d registrado(s)" % (len(viables), len(registro.diferenciadores)))
        if puntaje:
            riesgo = puntaje["valores"]["riesgo"]
            agregar(riesgo != 1 or puntaje.get("mitigacion"),
                    "Riesgo de políticas distinto de 1, o con una mitigación escrita",
                    "es %d%s" % (riesgo, " con mitigación" if puntaje.get("mitigacion") else ""))
        else:
            agregar(False, "Riesgo de políticas distinto de 1, o con una mitigación escrita", "sin puntaje")

    elif numero_puerta == 2:
        escenarios = producto.get("escenarios")
        meta = float(criterios.get("meta_ingresos_mes") or 0)
        texto = "El escenario base%s alcanza la meta de ingresos" % (" por analogía" if nueva else "")
        if not escenarios:
            agregar(False, texto, "sin calcular: corre `escenarios` en la sesión 2")
        elif not meta:
            agregar(False, texto, "falta `meta_ingresos_mes` en los criterios")
        else:
            agregar(escenarios["base"] >= meta, texto, "%s de %s %s al mes" % (
                numero(escenarios["base"]), numero(meta), criterios["moneda"]))
        filas = hipotesis(carpeta, registro)
        if not filas:
            agregar(False, "Ninguna hipótesis crítica refutada", "03-validacion.md no tiene la tabla de hipótesis")
        else:
            refutadas = [fila["id"] for fila in filas if fila["veredicto"] == "refutada"]
            agregar(not refutadas, "Ninguna hipótesis crítica refutada",
                    "refutadas: %s" % ", ".join(refutadas) if refutadas else "%d hipótesis" % len(filas))
        if nueva:
            riesgosas = [fila for fila in filas or [] if fila["riesgosa"]]
            medible = len(riesgosas) == 1 and riesgosas[0]["metrica"]
            agregar(medible, "La hipótesis más riesgosa, identificada y medible después del lanzamiento",
                    "%s, con métrica y umbral" % riesgosas[0]["id"] if medible
                    else "falta marcar una sola hipótesis como la más riesgosa, con su métrica y su umbral")
        else:
            principal = registro.principal()
            texto = "El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta"
            if not principal:
                agregar(False, texto, "no hay un diferenciador principal registrado")
            else:
                suyas = [fila for fila in filas or [] if fila["diferenciador"] == principal["id"]]
                sobrevive = suyas and all(f["veredicto"] == "sostenida" and f["nivel"] >= 2 for f in suyas)
                agregar(sobrevive, texto, "%s: %s" % (principal["id"], ", ".join(
                    "%s %s (confianza %s)" % (f["id"], f["veredicto"] or "sin veredicto", NIVELES[f["nivel"]])
                    for f in suyas) or "ninguna hipótesis lo pone a prueba en 03-validacion.md"))

    else:
        datos = prd(carpeta, registro)
        mvp = [f for f in datos["funciones"] if f["mvp"]]
        presupuesto = float(criterios.get("presupuesto_semanas") or 0)
        semanas = sum(f["semanas"] for f in mvp)
        sin_semanas = [f["id"] for f in mvp if not f["semanas"]]
        agregar(mvp and presupuesto and not sin_semanas and semanas <= presupuesto,
                "El MVP cabe en el presupuesto de semanas",
                "sin estimación: %s" % ", ".join(sin_semanas) if sin_semanas
                else "%s de %s semana(s)" % (numero(semanas), numero(presupuesto)) if mvp
                else "04-prd.md no tiene funcionalidades marcadas como MVP")
        principal = registro.principal()
        dentro = principal and [f["id"] for f in mvp if principal["id"] in f["diferenciadores"]]
        agregar(dentro, "El diferenciador principal está en el MVP",
                "%s en %s" % (principal["id"], ", ".join(dentro)) if dentro
                else "ninguna funcionalidad del MVP lo cita" if principal
                else "no hay un diferenciador principal registrado")
        trazadas = [f for f in mvp if not f["faltas"]]
        agregar(mvp and len(trazadas) == len(mvp), "100 % de las funcionalidades del MVP con trazabilidad",
                "%d de %d" % (len(trazadas), len(mvp)))
        definidas = datos["metricas"] and all(datos["metricas"].values())
        agregar(definidas, "Métricas HEART definidas", "%d métrica(s), %d incompleta(s)" % (
            len(datos["metricas"]), sum(1 for completa in datos["metricas"].values() if not completa)))
        bloqueos = [requisito for requisito, estado in datos["politicas"] if estado == "bloqueo"]
        agregar(datos["politicas"] and not bloqueos, "Checklist de políticas sin bloqueos",
                "bloqueos: %s" % "; ".join(bloqueos) if bloqueos
                else "%d requisito(s)" % len(datos["politicas"]) if datos["politicas"] else "el checklist está vacío")
        if nueva:
            riesgosas = [fila for fila in hipotesis(carpeta, registro) or [] if fila["riesgosa"]]
            riesgosa = riesgosas[0] if len(riesgosas) == 1 else None
            prueba = riesgosa and riesgosa["metrica"] and [f["id"] for f in mvp if riesgosa["id"] in f["hipotesis"]]
            agregar(prueba, "El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral",
                    "%s en %s" % (riesgosa["id"], ", ".join(prueba)) if prueba
                    else "ninguna funcionalidad del MVP cita la hipótesis más riesgosa (columna Hipótesis), o le "
                         "falta su métrica y su umbral en 03-validacion.md")
    return resultado


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
        for clave in ("meta_ingresos_mes", "presupuesto_semanas"):
            if not float(criterios.get(clave) or 0):
                faltan.append("falta el criterio `%s` (`criterio --clave %s --valor <n>`)" % (clave, clave))
    elif sesion == "1a":
        if not tipo_de(producto):
            faltan.append("falta registrar el tipo de idea (`tipo --existente|--variante|--nueva --motivo …`)")
        if not registro.competidores:
            faltan.append("la matriz no tiene ninguna fila (`competidor`): si no hay directos, van los análogos "
                          "y los sustitutos")
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


def pasos(carpeta, producto):
    """El paso siguiente: (título, [líneas]) según lo que hay en el disco."""
    lista_decisiones = decisiones(carpeta)
    estado_md = carpeta / "estado.md"
    abiertas = [s["id"] for s in SESIONES if not cerrada(producto, s["id"])
                and disponible(producto, lista_decisiones, s["id"])]
    lineas = []
    if abiertas == ["0"]:
        lineas += ["1. Este chat · Sesión 0 · Idea · modelo sugerido: intermedio",
                   "   Completa 00-idea.md y criterios.md (la meta de ingresos y el presupuesto de semanas van con "
                   "`criterio`) y cierra la sesión:",
                   "   " + orden("cerrar --sesion 0", carpeta)]
        return lineas
    if abiertas:
        if len(abiertas) > 1:
            lineas.append("Puedes abrir estos chats en paralelo (uno por sesión; con subagentes, uno por sesión):")
            lineas.append("")
        for indice, sesion in enumerate(abiertas, start=1):
            datos = SESION[sesion]
            lineas += ["%d. Chat nuevo · Sesión %s · %s · modelo sugerido: %s" % (
                indice, sesion, datos["nombre"], datos["modelo"]),
                "   Lee: %s" % datos["lee"],
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
        return [linea for linea in lineas if linea is not None]
    for numero_puerta in (1, 2, 3):
        nodo = "P%d" % numero_puerta
        if disponible(producto, lista_decisiones, nodo) and not cumplido(producto, lista_decisiones, nodo):
            previa = vigente(lista_decisiones, numero_puerta)
            if previa and previa["decision"] == "ajustar":
                lineas += ["La puerta %d se ajustó (sesión %s) y hay que volver a decidirla." % (
                    numero_puerta, previa.get("sesion")), ""]
            lineas += [
                "1. Terminal · Puerta %d · %s: el veredicto, criterio por criterio" % (
                    numero_puerta, PUERTAS[numero_puerta]),
                "   " + orden("puerta --n %d" % numero_puerta, carpeta),
                "2. Terminal · La decisión es tuya (el agente nunca corre este comando). Elige uno:",
                "   Seguir:    " + orden("decidir --puerta %d --seguir" % numero_puerta, carpeta),
                "   Ajustar:   " + orden("decidir --puerta %d --ajustar <sesión>" % numero_puerta, carpeta),
                "   Descartar: " + orden("decidir --puerta %d --descartar \"<motivo>\"" % numero_puerta, carpeta),
            ]
            return lineas
    lineas += ["Proceso cerrado: el PRD está aprobado y no queda ningún paso de hb-product %s." % VERSION,
               "Para construir, pide una funcionalidad del PRD a la vez citando su ID (por ejemplo: \"Implementa "
               "F-01 de %s\"): eso lo hace hb-implement." % (carpeta / "04-prd.md")]
    return lineas


def texto_siguiente(carpeta, producto):
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
    return "\n".join([titulo, ""] + pasos(carpeta, producto) + ([""] + avisos if avisos else []))


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
        "independientes · meta de %s %s al mes · %s semanas" % (
            criterios["puntaje_minimo"], criterios["puntaje_minimo_nueva"], criterios["vigencia_meses"],
            criterios["fuentes_minimas"], numero(float(criterios["meta_ingresos_mes"] or 0)), criterios["moneda"],
            numero(float(criterios["presupuesto_semanas"] or 0))),
        "- **Evidencia:** %d fuentes · %d hallazgos (%d clave, %d sin triangular%s) · %d competidores en la matriz "
        "· %d diferenciadores (%d viables%s)" % (
            len(registro.fuentes), len(registro.hallazgos), len(claves), len(sin_triangular),
            (": " + ", ".join(sin_triangular)) if sin_triangular else "", len(registro.competidores),
            len(registro.diferenciadores), len(registro.viables()),
            "; principal: %s" % principal["id"] if principal else ""),
    ]
    puntaje = producto.get("puntaje")
    if puntaje:
        lineas.append("- **Puntaje:** %d/25 · confianza global %s" % (
            puntaje["total"], NIVELES[confianzas(registro)[1]]))
    escenarios = producto.get("escenarios")
    if escenarios:
        lineas.append("- **Escenario base:** %s %s al mes%s" % (
            numero(escenarios["base"]), escenarios["moneda"],
            " · " + " · ".join(escenarios["rotulos"]) if escenarios["rotulos"] else ""))
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


def actualizar_estado(carpeta, producto, registro=None):
    """Reescribe los bloques de estado.md que mantiene el script y devuelve el texto del paso siguiente."""
    registro = registro or Registro(carpeta, producto["criterios"])
    siguiente = texto_siguiente(carpeta, producto)
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
        producto = {"formato": FORMATO, "version": VERSION, "nombre": args.nombre.strip(), "slug": slug(args.nombre),
                    "creado": hoy().isoformat(), "tipo": None, "tipo_historial": [], "criterios": criterios,
                    "criterios_cambios": [], "sesiones": {}, "intentos": [], "puntaje": None, "escenarios": None,
                    "archivo": None}
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
    valor = args.valor.upper() if args.clave == "moneda" else positivo(args.valor, "--valor")
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
    """AAAA-MM-DD o AAAA-MM (día 1) → AAAA-MM-DD; 'sin-fecha' → None (no cuenta como vigente)."""
    if texto == "sin-fecha":
        return None
    coincide = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$", texto)
    if not coincide:
        raise Fallo("--publicada debe ser AAAA-MM-DD, AAAA-MM o sin-fecha, no '%s'" % texto)
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


def cmd_fuente(args):
    carpeta, producto, registro = abrir(args)
    linea = linea_valida(args.linea)
    dominio, url = url_normal(args.url)
    resumen = args.resumen.strip()
    if len(resumen.splitlines()) > 3 or len(resumen) > 400:
        raise Fallo("El resumen de una fuente tiene 3 líneas como máximo (400 caracteres): tiene %d líneas y %d "
                    "caracteres" % (len(resumen.splitlines()), len(resumen)))
    autor = (args.autor or "").strip()
    if re.match(r"^(@|u/|/u/)", autor):
        raise Fallo("--autor no puede ser un nombre de usuario: es la app, la empresa o el medio que publica")
    datos = cargar_linea(carpeta, linea)
    existente = next((f for f in datos["fuentes"] if f["url"] == url and not f.get("anulado")), None)
    if existente:
        print("· %s ya estaba registrada con esa URL: no se duplica." % existente["id"])
        identificador = existente["id"]
    else:
        identificador = "S-%s-%d" % (LINEAS[linea][0], len(datos["fuentes"]) + 1)
        fuente = {"id": identificador, "linea": linea, "url": url, "dominio": dominio, "autor": autor,
                  "publicada": fecha_publicacion(args.publicada),
                  "consultada": fecha_publicacion(args.consultada) if args.consultada else hoy().isoformat(),
                  "tipo": args.tipo, "peldano": args.peldano, "resumen": resumen}
        datos["fuentes"].append(fuente)
        escribir_json(ruta_linea(carpeta, linea), datos)
        registro = Registro(carpeta, producto["criterios"])
        print("✔ %s registrada (%s · peldaño %d, %s · %s · %s)" % (
            identificador, linea, args.peldano, PELDANOS[args.peldano][0], args.tipo,
            "vigente" if registro.vigente(fuente) else "fuera de la ventana de vigencia o sin fecha: no cuenta "
            "para triangular"))
        otra = next((f for f in registro.fuentes.values() if f["url"] == url and f["id"] != identificador), None)
        if otra:
            print("· La misma URL ya es %s en la línea %s: al triangular cuentan como una sola." % (
                otra["id"], otra["linea"]))
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
    datos = cargar_linea(carpeta, linea)
    identificador = "H-%s-%d" % (LINEAS[linea][0], len(datos["hallazgos"]) + 1)
    hallazgo = {"id": identificador, "linea": linea, "texto": args.texto.strip(), "fuentes": fuentes,
                "en_contra": contra, "sin_contra": (args.sin_contra or "").strip(), "critico": bool(args.critico),
                "competidores": lista(args.competidores), "fecha": ahora()}
    datos["hallazgos"].append(hallazgo)
    escribir_json(ruta_linea(carpeta, linea), datos)
    evaluacion = registro.evaluar(hallazgo)
    print("✔ %s registrado%s · confianza %s (peldaño %d, %s · %d fuente(s) independiente(s) y vigente(s)%s)" % (
        identificador, " como hallazgo clave" if args.critico else "", evaluacion["confianza"],
        evaluacion["peldano"], PELDANOS[evaluacion["peldano"]][0], evaluacion["independientes"],
        " · %d en contra" % evaluacion["contra"] if evaluacion["contra"] else ""))
    sin_fila = [c for c in hallazgo["competidores"] if not registro.competidor(c)]
    if sin_fila:
        print("· Competidor(es) sin fila en la matriz todavía: %s (la matriz la registra la sesión 1a)" % ", ".join(
            sin_fila))
    if args.critico and evaluacion["faltan"]:
        print("⚠ Para cumplir la regla de triangulación: %s." % "; ".join(evaluacion["faltan"]))
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
        print("| %s |" % " | ".join([
            fila["id"], fila["nombre"] + (" ★" if registro.con_traccion(fila) else ""), str(fila["peldano"]),
            texto(fila.get("descargas")), texto(fila.get("nota")), texto(fila.get("actualizada")), texto(precio),
            texto(fila.get("anuncios")), texto(fila.get("tamano_mb")), texto(fila.get("idiomas")),
            texto(fila.get("permisos")), texto(fila.get("sin_conexion")), texto(fila.get("accesibilidad")),
            texto(fila.get("plataformas")), texto(fila.get("funciones")), texto(quejas.get(fila["id"]))]))
    print("\n★ = con tracción (%s descargas o más, o tracción anotada)." % numero(
        float(producto["criterios"]["traccion_descargas"])))
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


def cmd_diferenciador(args):
    carpeta, producto, registro = abrir(args)
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
    criterios = registro.viabilidad(diferenciador)
    viable = all(cumple for cumple, _ in criterios)
    print("%s %s registrado%s: %s" % ("✔" if viable else "✖", identificador,
                                      " como principal" if args.principal else "",
                                      "viable" if viable else "todavía no es viable"))
    for cumple, texto in criterios:
        print("  %s %s" % ("✔" if cumple else "✖", texto))
    if viable and args.copiable == "alta":
        print("· Es fácil de copiar: sirve para entrar, pero no sostiene la posición.")
    en_ficha = any(d.get("se_ve") == "ficha" for d in registro.viables())
    en_uso = any(d.get("se_ve") == "uso" for d in registro.viables())
    if registro.viables() and not (en_ficha and en_uso):
        print("· Lo ideal es tener un diferenciador viable que se vea en la ficha (consigue descargas) y otro en el "
              "uso (consigue retención): falta el de %s." % ("la ficha" if not en_ficha else "el uso"))
    print("Siguiente paso: %s" % ("regístralo en diferenciacion.md con su ID; el más fuerte va con --principal."
                                  if viable else "consigue lo que falta o descártalo con `anular --id %s --motivo "
                                  "…`." % identificador))


def cmd_anular(args):
    carpeta, producto, registro = abrir(args)
    campo = {"S": "fuentes", "H": "hallazgos", "C": "matriz", "D": "diferenciadores"}.get(args.id[:1])
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


def cmd_triangulacion(args):
    carpeta, producto, registro = abrir(args)
    claves = [h for h in registro.hallazgos.values() if h.get("critico")]
    if not claves:
        print("No hay hallazgos clave registrados (los que llevan --critico).")
        print("Siguiente paso: marca con --critico los hallazgos de los que dependen el puntaje y las puertas.")
        return
    incompletos = 0
    for hallazgo in claves:
        evaluacion = registro.evaluar(hallazgo)
        completo = not evaluacion["faltan"]
        incompletos += 0 if completo else 1
        print("%s %s · confianza %s · peldaño %d (%s) · %d/%s fuentes independientes y vigentes%s" % (
            "✔" if completo else "✖", hallazgo["id"], evaluacion["confianza"], evaluacion["peldano"],
            PELDANOS[evaluacion["peldano"]][0], evaluacion["independientes"],
            producto["criterios"]["fuentes_minimas"], " · en contra: %d" % evaluacion["contra"]
            if evaluacion["contra"] else ""))
        print("    %s" % hallazgo["texto"][:160])
        for falta in evaluacion["faltan"]:
            print("    → %s" % falta)
        manual = hallazgo.get("confianza_manual")
        if manual:
            print("    · confianza bajada a %s: %s" % (manual["nivel"], manual["motivo"]))
    print("\n%d de %d hallazgos clave cumplen la regla de triangulación." % (len(claves) - incompletos, len(claves)))
    if incompletos:
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
    viables = registro.viables()
    if not viables and valores["diferenciacion"] > 1:
        raise Fallo("Diferenciación = %d no corresponde: no hay ningún diferenciador viable registrado, y esa es "
                    "el ancla del 1 (references/puntaje.md)." % valores["diferenciacion"])
    if viables and valores["diferenciacion"] == 1:
        raise Fallo("Diferenciación = 1 no corresponde: hay %d diferenciador(es) viable(s) registrado(s) (%s)." % (
            len(viables), ", ".join(d["id"] for d in viables)))
    por_criterio, global_ = confianzas(registro)
    total = sum(valores.values())
    producto["puntaje"] = {"valores": valores, "total": total, "mitigacion": (args.mitigacion or "").strip(),
                           "fecha": ahora()}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto, registro)
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
    for mercado in mercados:
        nombre = str(mercado.get("mercado") or "?")
        dau = caso(mercado.get("dau"), "%s.dau" % nombre, True, registro, sin_fuente, por_analogia)
        ingresos = dict.fromkeys(casos, 0.0)
        for anuncio in mercado.get("anuncios", []):
            ruta_supuesto = "%s.anuncios.%s" % (nombre, anuncio.get("formato", "?"))
            impresiones = caso(anuncio.get("impresiones_por_dau"), ruta_supuesto + ".impresiones_por_dau", True,
                               registro, sin_fuente, por_analogia)
            ecpm = caso(anuncio.get("ecpm"), ruta_supuesto + ".ecpm", True, registro, sin_fuente, por_analogia)
            for c in casos:
                ingresos[c] += dau[c] * impresiones[c] * 30 * ecpm[c] / 1000.0
        compras = mercado.get("compras", [])
        if compras:
            dau_mau = caso(mercado.get("dau_mau"), "%s.dau_mau" % nombre, True, registro, sin_fuente, por_analogia)
            if min(dau_mau.values()) <= 0 or max(dau_mau.values()) > 1:
                raise Fallo("`%s.dau_mau` es la proporción de usuarios del mes que entran cada día: va entre 0 y 1"
                            % nombre)
        for compra in compras:
            ruta_supuesto = "%s.compras.%s" % (nombre, compra.get("nombre", "?"))
            conversion = caso(compra.get("conversion"), ruta_supuesto + ".conversion", True, registro, sin_fuente,
                              por_analogia)
            precio = caso(compra.get("precio"), ruta_supuesto + ".precio", False, registro, sin_fuente, por_analogia)
            comision = compra.get("comision")
            if not isinstance(comision, (int, float)) or not 0 <= comision < 1:
                raise Fallo("`%s.comision` es la comisión de la tienda como proporción: 0.15 o 0.30" % ruta_supuesto)
            if max(conversion.values()) > 1:
                raise Fallo("`%s.conversion` es una proporción entre 0 y 1 (1 % = 0.01)" % ruta_supuesto)
            for c in casos:
                ingresos[c] += dau[c] / dau_mau[c] * conversion[c] * precio[c] * (1 - comision)
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
    producto["escenarios"] = {"fecha": ahora(), "moneda": moneda, "pesimista": round(totales["pesimista"], 2),
                              "base": round(totales["base"], 2), "optimista": round(totales["optimista"], 2),
                              "rotulos": rotulos, "dau_base": usuarios["base"], "dau_meta": necesarios,
                              "entrada": str(ruta)}
    guardar(carpeta, producto)
    actualizar_estado(carpeta, producto, registro)
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
    if not meta:
        print("⚠ No hay meta de ingresos (`criterio --clave meta_ingresos_mes --valor <n>`): no se puede comparar.")
    elif necesarios is None:
        print("El escenario base no genera ingresos: no se puede calcular cuántos usuarios hacen falta.")
    else:
        print("\nMeta: %s %s al mes → el escenario base %s (%s). Para llegar a la meta hacen falta %s usuarios "
              "activos diarios; el base supone %s." % (
                  numero(meta), moneda, "la alcanza" if totales["base"] >= meta else "no la alcanza",
                  numero(totales["base"]), numero(necesarios), numero(usuarios["base"])))
    print("Siguiente paso: copia la tabla a 02-estrategia.md con sus rótulos y cierra con `cerrar --sesion 2`.")


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
    siguiente = actualizar_estado(carpeta, producto, registro)
    print("✔ Sesión %s · %s cerrada" % (args.sesion, SESION[args.sesion]["nombre"]))
    if args.sesion == "1g" and not registro.viables() and tipo_de(producto) != "nueva":
        print("⚠ No hay ningún diferenciador viable: la puerta 1 lo va a marcar como criterio sin cumplir.")
    print("\n" + siguiente)


def cmd_puerta(args):
    carpeta, producto, registro = abrir(args)
    if not tipo_de(producto):
        raise Fallo("Falta el tipo de idea (`tipo`): cada puerta usa el juego de criterios de ese tipo.")
    lista_decisiones = decisiones(carpeta)
    criterios = criterios_puerta(args.n, carpeta, producto, registro)
    print("Puerta %d · %s · idea %s" % (args.n, PUERTAS[args.n], tipo_de(producto)))
    abiertas = [s for s in DEPENDE["P%d" % args.n] if not cerrada(producto, s)]
    if abiertas:
        print("⚠ Veredicto provisional: falta cerrar la(s) sesión(es) %s." % ", ".join(abiertas))
    for cumple, texto, detalle in criterios:
        print("%s %s%s" % ("✔" if cumple else "✖", texto, " · " + detalle if detalle else ""))
    for cambio in producto.get("criterios_cambios", []):
        print("· Criterio cambiado después de la sesión 0: %s de %s a %s el %s (%s)" % (
            cambio["clave"], cambio["antes"], cambio["despues"], cambio["fecha"][:10], cambio["motivo"]))
    if args.n == 1:
        print("· La cantidad de competidores no es un criterio: ni la saturación ni la falta de datos descartan "
              "una idea.")
    cumplidos = sum(1 for cumple, _, _ in criterios if cumple)
    print("\nVeredicto: cumple %d de %d criterios." % (cumplidos, len(criterios)))
    previa = vigente(lista_decisiones, args.n)
    if previa and previa["decision"] == "seguir":
        print("Esta puerta ya está decidida: seguir, el %s." % previa["fecha"].replace("T", " "))
    print("Siguiente paso: la decisión es del usuario (el agente nunca corre `decidir`). Elige uno:")
    print("  Seguir:    " + orden("decidir --puerta %d --seguir" % args.n, carpeta))
    print("  Ajustar:   " + orden("decidir --puerta %d --ajustar <sesión>" % args.n, carpeta))
    print("  Descartar: " + orden("decidir --puerta %d --descartar \"<motivo>\"" % args.n, carpeta))


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
        siguiente = actualizar_estado(carpeta, producto, registro)
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
    for decision in lista_decisiones:
        if decision["puerta"] == args.puerta:
            decision["vigente"] = False
    if args.seguir:
        if abiertas:
            raise Fallo("Para seguir, antes cierra la(s) sesión(es) %s (`cerrar --sesion <id>`)." % ", ".join(
                abiertas))
        registro_decision["decision"] = "seguir"
        lista_decisiones.append(registro_decision)
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        siguiente = actualizar_estado(carpeta, producto, registro)
        print("✔ Puerta %d · %s: seguir (cumplía %d de %d criterios)" % (
            args.puerta, PUERTAS[args.puerta], cumplidos, len(criterios)))
        if cumplidos < len(criterios):
            print("⚠ Sigues con %d criterio(s) sin cumplir: queda anotado en decisiones.json." % (
                len(criterios) - cumplidos))
        print("\n" + siguiente)
    elif args.ajustar:
        sesion = args.ajustar
        if sesion not in SESION or nodo not in dependientes(sesion):
            anteriores = [s["id"] for s in SESIONES if nodo in dependientes(s["id"])]
            raise Fallo("--ajustar lleva una sesión anterior a la puerta %d: %s" % (args.puerta, ", ".join(
                anteriores)))
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
        siguiente = actualizar_estado(carpeta, producto, registro)
        print("✔ Puerta %d · %s: ajustar la sesión %s" % (args.puerta, PUERTAS[args.puerta], sesion))
        print("· Se reabren: %s. Lo ya escrito se conserva: cada sesión corrige lo suyo y vuelve a cerrar." % (
            ", ".join(sorted(reabiertas, key=lambda s: [x["id"] for x in SESIONES].index(s))) or "ninguna"))
        print("\n" + siguiente)
    else:
        motivo = args.descartar.strip()
        if len(motivo) < 10:
            raise Fallo("--descartar lleva el motivo completo (qué evidencia en contra hay, o qué camino no "
                        "existe): es lo que queda como aprendizaje")
        registro_decision.update(decision="descartar", motivo=motivo)
        lista_decisiones.append(registro_decision)
        escribir_json(carpeta / "decisiones.json", lista_decisiones)
        destino = mover_a_archivo(carpeta, producto, motivo, "descarte en la puerta %d" % args.puerta)
        print("✔ Puerta %d · %s: idea descartada y archivada en %s" % (args.puerta, PUERTAS[args.puerta], destino))
        print("· Motivo: %s" % motivo)
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
        print(actualizar_estado(carpeta, producto))


def cmd_estado(args):
    carpeta = resolver_carpeta(args)
    with bloqueo(carpeta):
        producto = cargar(carpeta)
        registro = Registro(carpeta, producto["criterios"])
        siguiente = actualizar_estado(carpeta, producto, registro)
    print(re.sub(r"\*\*", "", texto_resumen(carpeta, producto, registro)))
    print("\n" + siguiente)


def cmd_archivar(args):
    carpeta, producto, registro = abrir(args)
    destino = mover_a_archivo(carpeta, producto, args.motivo.strip(), "archivada a mano")
    print("✔ Idea \"%s\" archivada en %s (no se borra nada)" % (producto["nombre"], destino))
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
    print("\n" + siguiente)


# ---------------------------------------------------------------------------------------------------------------
# Línea de comandos

SOLO_LECTURA = ("tipo", "matriz", "triangulacion", "validacion", "trazabilidad", "puerta")
SIN_CANDADO = ("nuevo", "siguiente", "estado", "reabrir")


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
    sub.add_argument("--url", required=True)
    sub.add_argument("--publicada", required=True, help="AAAA-MM-DD, AAAA-MM o sin-fecha")
    sub.add_argument("--consultada", help="AAAA-MM-DD (por defecto, hoy)")
    sub.add_argument("--tipo", required=True, choices=TIPOS_FUENTE)
    sub.add_argument("--peldano", required=True, type=int, choices=sorted(PELDANOS))
    sub.add_argument("--resumen", required=True, help="3 líneas como máximo")
    sub.add_argument("--autor", help="la app, la empresa o el medio que publica; nunca un nombre de usuario")

    sub = comando("hallazgo", cmd_hallazgo, "Registra un hallazgo (H-…) y calcula su confianza")
    sub.add_argument("--linea", required=True, help=", ".join(LINEAS))
    sub.add_argument("--texto", required=True)
    sub.add_argument("--fuentes", required=True, help="S-…,S-…")
    sub.add_argument("--en-contra", dest="en_contra", help="fuentes con evidencia en contra")
    sub.add_argument("--sin-contra", dest="sin_contra", help="qué se buscó en contra cuando no apareció nada")
    sub.add_argument("--critico", action="store_true", help="hallazgo clave: sostiene el puntaje o una puerta")
    sub.add_argument("--competidores", help="competidores a los que se refiere, por ID (C-…) o por nombre")

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

    comando("matriz", cmd_matriz, "Muestra la matriz de competidores con los hallazgos enlazados a cada uno")

    sub = comando("intento", cmd_intento, "Registra la búsqueda de intentos anteriores de la misma idea")
    sub.add_argument("--resultado", required=True, choices=("sin-rastro", "fracaso-demanda", "fracaso-otra-causa"))
    sub.add_argument("--texto", required=True, help="qué se buscó y qué apareció")
    sub.add_argument("--fuentes", help="S-…,S-…")

    sub = comando("diferenciador", cmd_diferenciador, "Registra un diferenciador (D-…) y dice si es viable")
    sub.add_argument("--vector", required=True, choices=VECTORES)
    sub.add_argument("--texto", required=True)
    sub.add_argument("--hallazgos", required=True, help="H-…,H-…")
    sub.add_argument("--se-ve", dest="se_ve", required=True, choices=("ficha", "uso"))
    sub.add_argument("--copiable", required=True, choices=("baja", "media", "alta"))
    sub.add_argument("--motivo", required=True, help="por qué es difícil o fácil de copiar")
    sub.add_argument("--semanas", required=True, help="semanas estimadas para construirlo")
    sub.add_argument("--principal", action="store_true")

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

    comando("siguiente", cmd_siguiente, "El paso siguiente o los carriles paralelos, con el texto para cada chat")
    comando("estado", cmd_estado, "Resumen de la idea y el paso siguiente")

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
