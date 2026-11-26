"""Tests de hb-product (skills/hb-product/scripts/producto.py), comando por comando, en carpetas temporales.

Los datos son inventados: una app que organiza turnos para regar las plantas de un edificio y una app de linterna.
"""
import ast
import concurrent.futures
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ENV, ROOT, write

SKILL = ROOT / "skills" / "hb-product"
SCRIPT = SKILL / "scripts" / "producto.py"
HOY = "2026-11-23"

spec = importlib.util.spec_from_file_location("producto", str(SCRIPT))
producto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producto)

HIPOTESIS = """# Validación

| ID | Hipótesis | Hallazgos | En contra | Diferenciador | Veredicto | Más riesgosa | Métrica y umbral |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HIP-01 | Los vecinos quieren repartir el riego | H-DEM-1 | Se buscaron apps de riego cerradas: nada | — | sostenida | sí | 30 % vuelve a los 30 días |
| HIP-02 | El pago único atrae a quien no quiere suscripción | H-VOZ-1 | Se buscaron quejas por pagos únicos: nada | D-1 | sostenida | — | — |
"""

PRD = """# PRD

| ID | Funcionalidad | MVP | Hallazgos | Diferenciador | Métrica | Alcance | Impacto | Semanas | Hipótesis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | Turnos de riego con pago único | sí | H-VOZ-1 | D-1 | M-01 | 1000 | 2 | 3 | HIP-01 |
| F-02 | Recordatorios | sí | H-COM-1 | — | M-02 | 800 | 1 | 2 | — |
| F-03 | Temas de color | no | H-COM-1 | — | M-01 | 100 | 0,5 | 1 | — |

## Historias de usuario

### F-01

- **Historia:** como vecino, quiero ver a quién le toca regar, para no discutir por los turnos.
- **Criterios de aceptación:**
  - Dado un edificio con 4 vecinos, cuando abro la app, entonces veo el turno de esta semana.
  - Dado que marqué mi turno como hecho, cuando lo abre otro vecino, entonces lo ve hecho.
  - Dado que compré el pago único, cuando reinstalo la app, entonces sigue desbloqueada.

### F-02

- **Historia:** como vecino, quiero un recordatorio el día de mi turno, para no olvidarlo.
- **Criterios de aceptación:**
  - Dado que me toca hoy, cuando son las 9, entonces recibo un aviso.
  - Dado que ya marqué el turno, cuando son las 9, entonces no recibo el aviso.

## Métricas HEART

| ID | Dimensión | Métrica | Meta |
| --- | --- | --- | --- |
| M-01 | Retención | Usuarios que vuelven a los 30 días | 30 % en 90 días |
| M-02 | Tarea | Turnos completados sin ayuda | 80 % |

## Checklist de políticas

| Requisito | Estado | Nota |
| --- | --- | --- |
| Política de privacidad publicada | pendiente | antes de publicar |
"""


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT"):  # los tests dan lo mismo en una terminal, en un agente y en CI
        os.environ.pop(variable, None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hb-product-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.carpeta = self.tmp / "product"
        self.sitio = 0

    def p(self, *args, ok=True):
        """Corre un comando en el mismo proceso. Devuelve la salida; con ok=False, el error."""
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            try:
                codigo = producto.main([str(a) for a in args] + ["--carpeta", str(self.carpeta)])
            except SystemExit as fin:  # argparse
                codigo = fin.code
        if ok:
            self.assertEqual(codigo, 0, error.getvalue() + salida.getvalue())
            return salida.getvalue()
        self.assertNotEqual(codigo, 0, salida.getvalue())
        return error.getvalue()

    def falla(self, *args):
        return self.p(*args, ok=False)

    def nuevo(self, nombre="Riego en turnos", *extra):
        return self.p("nuevo", "--nombre", nombre, "--meta", "300", "--semanas", "6", "--mercados", "MX",
                      "--idiomas", "es", "--tiendas", "google-play", *extra)

    def fuente(self, linea, cantidad=1, tipo="terceros", peldano=1, publicada="2026-06", dominio=None, autor=None,
               cobertura=True):
        """Registra fuentes de dominios distintos (o del mismo, si se pasa) y devuelve sus IDs. Con cobertura, cada
        fuente cubre el objetivo de `nuevo` (MX, es y google-play)."""
        ids = []
        for _ in range(cantidad):
            self.sitio += 1
            args = ["fuente", "--linea", linea, "--url", "https://%s/pagina-%d" % (
                dominio or "sitio%d.example" % self.sitio, self.sitio), "--publicada", publicada, "--tipo", tipo,
                "--peldano", peldano, "--resumen", "Resumen inventado %d" % self.sitio]
            if autor:
                args += ["--autor", "%s %d" % (autor, self.sitio)]
            if cobertura:
                args += ["--mercados", "MX", "--idiomas", "es", "--tiendas", "google-play"]
            ids.append(re.search(r"S-[A-Z]{3}-\d+", self.p(*args)).group(0))
        return ids

    def sustituto(self, fuente, nombre="Grupo de chat del edificio", tipo="gratuito", resuelve="parcial"):
        """La fila de la matriz que dice cómo se resuelve hoy la necesidad sin una app así (la pide el cierre de 1a)."""
        return self.p("competidor", "--nombre", nombre, "--peldano", 4, "--fuentes", fuente, "--sustituto", tipo,
                      "--resuelve", resuelve)

    def hallazgo(self, linea, fuentes, *extra):
        salida = self.p("hallazgo", "--linea", linea, "--texto", "Hallazgo inventado", "--fuentes",
                        ",".join(fuentes), *extra)
        return re.search(r"H-[A-Z]{3}-\d+", salida).group(0), salida

    def completar(self, relativo):
        ruta = self.carpeta / relativo
        ruta.write_text(re.sub(r"<por completar[^>\n]*>?", "listo", ruta.read_text(encoding="utf-8")),
                        encoding="utf-8")

    def datos(self, relativo="producto.json"):
        return json.loads((self.carpeta / relativo).read_text(encoding="utf-8"))

    def cerrar(self, sesion, archivo=None):
        if archivo:
            self.completar(archivo)
        return self.p("cerrar", "--sesion", sesion)

    # --- una idea completa, por etapas -------------------------------------------------------------------------

    def sesion0(self, tipo="existente"):
        self.nuevo()
        self.completar("criterios.md")
        self.p("tipo", "--" + tipo, "--provisional", "--motivo", "Triaje inventado de la sesión 0")
        return self.cerrar("0", "00-idea.md")

    def linea(self, sesion, nombre, tipo="terceros", peldano=1, *extra):
        """Una línea de investigación con un hallazgo clave triangulado (la última fuente, de tipo medido)."""
        fuentes = self.fuente(nombre, 2, tipo, peldano) + self.fuente(nombre, 1, "medido", peldano)
        identificador, _ = self.hallazgo(nombre, fuentes, "--critico", "--sin-contra", "Se buscó y no apareció",
                                         *extra)
        self.cerrar(sesion, "01-investigacion/%s.md" % nombre)
        return identificador

    def investigacion(self, viable=True):
        """Sesiones 1a a 1g de una idea con competencia; con viable=False, sin ningún diferenciador."""
        self.sesion0()
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--descargas", "1M",
               "--precio", "3,99 al mes", "--modelo", "suscripción", "--tamano-mb", "80")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[1], "--descargas",
               "500k", "--precio", "gratis", "--modelo", "anuncios", "--tamano-mb", "120", "--rival")
        self.sustituto(fuentes[2])
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "Se buscó y no apareció")
        self.cerrar("1a", "01-investigacion/competencia.md")
        voz = self.linea("1b", "voz-del-usuario", "usuario", 1, "--competidores", "RiegoFácil,PlantaPlus")
        for sesion, nombre in (("1c", "demanda"), ("1d", "monetizacion"), ("1e", "politicas")):
            self.linea(sesion, nombre)
        if viable:
            self.p("diferenciador", "--vector", "precio", "--texto", "Pago único en vez de suscripción",
                   "--hallazgos", voz, "--se-ve", "ficha", "--copiable", "media", "--motivo",
                   "Cambiar de modelo les cuesta ingresos recurrentes", "--semanas", 2, "--principal")
            # la prueba de elección: un hallazgo de la comparación distinto del dolor (feedback #68)
            eleccion, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 3), "--critico",
                                        "--sin-contra", "Se buscó y no apareció")
            self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, eleccion), "--texto",
                   "PlantaPlus es gratis, pero con anuncios que sus usuarios piden quitar")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")

    def hasta_puerta1(self):
        self.investigacion()
        self.p("puntaje", "--valores", "4,4,4,4,3")
        return self.cerrar("1f", "01-sintesis.md")

    def escenarios(self, dau=2000, fuente="S-MON-3"):
        entrada = {"mercados": [{
            "mercado": "MX", "dau": {"pesimista": dau / 2, "base": dau, "optimista": dau * 2, "fuente": fuente},
            "instalaciones_mes": {"pesimista": dau * 2.5, "base": dau * 5, "optimista": dau * 10, "fuente": fuente},
            "anuncios": [{"formato": "banner",
                          "impresiones_por_dau": {"pesimista": 5, "base": 5, "optimista": 5, "fuente": fuente},
                          "ecpm": {"pesimista": 0.4, "base": 0.4, "optimista": 0.4, "fuente": fuente}}],
            "compras": [{"nombre": "Premium", "tipo": "pago-unico", "precio": 4, "comision": 0.15,
                         "conversion": {"pesimista": 0.02, "base": 0.02, "optimista": 0.02, "fuente": fuente}}]}]}
        write(self.carpeta / "escenarios.json", json.dumps(entrada))
        return self.p("escenarios", "--entrada", "escenarios.json")

    def hasta_puerta2(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", HIPOTESIS)
        return self.cerrar("3")

    def hasta_puerta3(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", PRD)
        return self.cerrar("4")


class GuionTest(unittest.TestCase):
    def test_es_ejecutable_y_su_sintaxis_sirve_en_python_38(self):
        self.assertTrue(os.access(str(SCRIPT), os.X_OK))
        ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 8))

    def test_solo_usa_la_libreria_estandar(self):
        modulos = set()
        for nodo in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                modulos.update(alias.name.split(".")[0] for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                modulos.add(nodo.module.split(".")[0])
        estandar = {"argparse", "contextlib", "csv", "io", "json", "math", "os", "re", "shlex", "shutil", "sys", "time",
                    "unicodedata", "datetime", "pathlib", "urllib", "html"}
        self.assertEqual(modulos - estandar, set())

    def test_las_plantillas_no_tienen_rutas_locales_ni_correos(self):
        for ruta in sorted((SKILL / "assets" / "plantillas").iterdir()):
            texto = ruta.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"/Users/|/home/|@[a-z0-9-]+\.[a-z]{2,}", texto), ruta.name)

    def test_cada_comando_tiene_ayuda(self):
        for comando in ("nuevo", "criterio", "tipo", "fuente", "hallazgo", "confianza", "competidor", "matriz",
                        "intento", "diferenciador", "anular", "triangulacion", "puntaje", "escenarios", "validacion",
                        "trazabilidad", "cerrar", "puerta", "decidir", "siguiente", "estado", "archivar", "reabrir",
                        "objetivo", "vacio", "cobertura", "resenas", "principal", "propuesta", "modelos", "consumo"):
            resultado = subprocess.run([sys.executable, "-I", str(SCRIPT), comando, "--help"], env=ENV,
                                       capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(resultado.returncode, 0, comando)
            self.assertIn("--carpeta", resultado.stdout, comando)


class NuevoTest(Base):
    def test_crea_la_estructura_desde_las_plantillas(self):
        salida = self.nuevo()
        for relativo in ("estado.md", "criterios.md", "00-idea.md", "01-sintesis.md", "02-estrategia.md",
                         "03-validacion.md", "04-prd.md", "decisiones.json", "producto.json", "escenarios.json",
                         "01-investigacion/competencia.md", "01-investigacion/competencia.json",
                         "01-investigacion/voz-del-usuario.md", "01-investigacion/demanda.json",
                         "01-investigacion/monetizacion.md", "01-investigacion/politicas.json",
                         "01-investigacion/diferenciacion.md", "01-investigacion/diferenciacion.json"):
            self.assertTrue((self.carpeta / relativo).is_file(), relativo)
        self.assertIn("Riego en turnos", (self.carpeta / "00-idea.md").read_text(encoding="utf-8"))
        self.assertNotIn("{{", (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        self.assertEqual(self.datos()["criterios"]["meta_ingresos_mes"], 300)
        self.assertEqual(self.datos("decisiones.json"), [])
        self.assertIn("Sesión 0 · Idea", salida)
        self.assertIn("cerrar --sesion 0", (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        self.assertIn("| `puntaje_minimo` | 17 |", (self.carpeta / "criterios.md").read_text(encoding="utf-8"))

    def test_los_umbrales_por_defecto_son_los_de_la_especificacion(self):
        self.nuevo()
        criterios = self.datos()["criterios"]
        self.assertEqual((criterios["puntaje_minimo"], criterios["puntaje_minimo_nueva"],
                          criterios["vigencia_meses"], criterios["fuentes_minimas"]), (17, 15, 18, 3))

    def test_no_pisa_lo_que_ya_existe_ni_una_idea_activa(self):
        write(self.carpeta / "00-idea.md", "mis notas")
        self.assertIn("no se tocaron: 00-idea.md", self.nuevo())
        self.assertEqual((self.carpeta / "00-idea.md").read_text(encoding="utf-8"), "mis notas")
        self.assertIn("Ya hay una idea activa", self.falla("nuevo", "--nombre", "Otra"))

    def test_un_nombre_con_comillas_no_rompe_el_json_de_escenarios(self):
        self.nuevo('La "mejor" idea')
        self.assertIn("mercados", self.datos("escenarios.json"))

    def test_la_carpeta_por_defecto_es_product_y_agents_la_cambia(self):
        argumentos = [sys.executable, "-I", str(SCRIPT), "nuevo", "--nombre", "Riego en turnos"]
        entorno = dict(ENV, HB_PRODUCT_HOY=HOY)
        subprocess.run(argumentos, cwd=str(self.tmp), env=entorno, check=True, capture_output=True)
        self.assertTrue((self.tmp / "product" / "producto.json").is_file())
        proyecto = self.tmp / "proyecto"
        write(proyecto / "AGENTS.md", "# App\n\n## Producto\n\n- Carpeta: `docs/producto`\n\n## Git\n\n- nada\n")
        subprocess.run(argumentos, cwd=str(proyecto), env=entorno, check=True, capture_output=True)
        self.assertTrue((proyecto / "docs" / "producto" / "producto.json").is_file())

    def test_sin_idea_siguiente_dice_como_empezar_y_los_demas_fallan(self):
        self.assertIn("nuevo --nombre", self.p("siguiente"))
        self.assertIn("No hay ninguna idea activa", self.falla("triangulacion"))
        self.assertFalse(self.carpeta.exists())


class CriterioTest(Base):
    def test_antes_de_cerrar_la_sesion_0_se_cambia_sin_motivo(self):
        self.nuevo()
        self.assertIn("17 → 18", self.p("criterio", "--clave", "puntaje_minimo", "--valor", 18))
        self.assertEqual(self.datos()["criterios_cambios"], [])
        self.assertIn("puntaje_minimo", self.p("criterio"))

    def test_despues_exige_motivo_y_la_puerta_lo_muestra(self):
        self.sesion0()
        self.assertIn("exige --motivo", self.falla("criterio", "--clave", "puntaje_minimo", "--valor", 15))
        self.p("criterio", "--clave", "puntaje_minimo", "--valor", 15, "--motivo", "El mercado es más chico")
        cambio = self.datos()["criterios_cambios"][0]
        self.assertEqual((cambio["antes"], cambio["despues"]), (17, 15))
        self.assertIn("El mercado es más chico", (self.carpeta / "criterios.md").read_text(encoding="utf-8"))
        self.p("tipo", "--existente", "--motivo", "Hay competencia directa")
        self.assertIn("Criterio cambiado después de la sesión 0: puntaje_minimo de 17 a 15", self.p("puerta", "--n", 1))

    def test_rechaza_claves_y_valores_invalidos(self):
        self.nuevo()
        self.assertIn("No existe el criterio", self.falla("criterio", "--clave", "otra", "--valor", 1))
        self.assertIn("5 a 25", self.falla("criterio", "--clave", "puntaje_minimo", "--valor", 30))
        self.assertIn("mayor que cero", self.falla("criterio", "--clave", "vigencia_meses", "--valor", 0))


class TipoTest(Base):
    def test_sin_registrar_lo_dice_y_da_el_presupuesto_normal(self):
        self.nuevo()
        salida = self.p("tipo")
        self.assertIn("sin registrar", salida)
        self.assertIn("15 búsquedas y 10 lecturas", salida)

    def test_registrar_exige_motivo_y_guarda_el_historial(self):
        self.nuevo()
        self.assertIn("exige --motivo", self.falla("tipo", "--nueva"))
        self.assertIn("20 búsquedas y 12 lecturas", self.p("tipo", "--nueva", "--motivo", "No hay apps directas"))
        self.assertIn("antes: nueva", self.p("tipo", "--variante", "--motivo", "Apareció una app en otro país"))
        guardado = self.datos()
        self.assertEqual(guardado["tipo"]["valor"], "variante")
        self.assertEqual(guardado["tipo_historial"][0]["valor"], "nueva")
        self.assertIn("variante (Apareció una app en otro país)", self.p("tipo"))

    def test_no_acepta_dos_tipos_a_la_vez(self):
        self.nuevo()
        self.falla("tipo", "--nueva", "--existente", "--motivo", "x")


class FuenteTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def test_cada_linea_numera_sus_ids(self):
        self.assertEqual(self.fuente("competencia", 2), ["S-COM-1", "S-COM-2"])
        self.assertEqual(self.fuente("demanda"), ["S-DEM-1"])
        self.assertEqual(self.fuente("validacion"), ["S-VAL-1"])
        fuente = self.datos("01-investigacion/competencia.json")["fuentes"][0]
        self.assertEqual((fuente["dominio"], fuente["consultada"], fuente["publicada"]),
                         ("sitio1.example", HOY, "2026-06-01"))

    def test_la_misma_url_no_se_duplica_en_la_linea(self):
        argumentos = ["fuente", "--linea", "demanda", "--publicada", "2026-06", "--tipo", "medido", "--peldano", 1,
                      "--resumen", "x", "--url"]
        self.p(*argumentos, "https://www.sitio.example/a/")
        self.assertIn("ya estaba registrada", self.p(*argumentos, "https://sitio.example/a#seccion"))
        self.assertEqual(len(self.datos("01-investigacion/demanda.json")["fuentes"]), 1)
        self.assertIn("cuentan como una sola", self.p(*(argumentos[:2] + ["monetizacion"] + argumentos[3:]),
                                                      "https://sitio.example/a"))

    def test_valida_la_url_la_fecha_el_resumen_y_el_autor(self):
        base = ["fuente", "--linea", "demanda", "--tipo", "medido", "--peldano", 1]
        bien = ["--url", "https://sitio.example/a", "--publicada", "2026-06", "--resumen", "x"]
        self.assertIn("http", self.falla(*base, "--url", "sitio.example", "--publicada", "2026-06", "--resumen", "x"))
        self.assertIn("futuro", self.falla(*base, "--url", "https://a.example", "--publicada", "2027-01",
                                           "--resumen", "x"))
        self.assertIn("AAAA-MM", self.falla(*base, "--url", "https://a.example", "--publicada", "junio",
                                            "--resumen", "x"))
        self.assertIn("3 líneas como máximo", self.falla(*base, "--url", "https://a.example", "--publicada",
                                                         "2026-06", "--resumen", "a\nb\nc\nd"))
        self.assertIn("nombre de usuario", self.falla(*base, *bien, "--autor", "@alguien"))
        self.assertIn("No existe la línea", self.falla("fuente", "--linea", "otra", "--tipo", "medido", "--peldano",
                                                       1, *bien))
        self.falla(*base, "--peldano", 7, *bien)

    def test_sin_fecha_o_vieja_no_cuenta_como_vigente(self):
        argumentos = ["fuente", "--linea", "demanda", "--tipo", "medido", "--peldano", 1, "--resumen", "x"]
        self.assertIn("no cuenta para la confianza ni para triangular", self.p(*argumentos, "--url", "https://a.example", "--publicada",
                                                          "sin-fecha"))
        self.assertIn("no cuenta para la confianza ni para triangular", self.p(*argumentos, "--url", "https://b.example", "--publicada",
                                                          "2025-05-22"))
        self.assertIn("· vigente)", self.p(*argumentos, "--url", "https://c.example", "--publicada", "2025-05-23"))

    def test_avisa_al_80_por_ciento_del_presupuesto_de_lecturas(self):
        self.fuente("demanda", 7)
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://ocho.example", "--publicada", "2026-06",
                        "--tipo", "medido", "--peldano", 1, "--resumen", "x")
        self.assertIn("8 (presupuesto de lecturas: 10)", salida)
        self.assertIn("80 %", salida)
        self.p("tipo", "--nueva", "--motivo", "No hay apps directas")
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://nueve.example", "--publicada", "2026-06",
                        "--tipo", "medido", "--peldano", 4, "--resumen", "x")
        self.assertIn("presupuesto de lecturas: 12", salida)
        self.assertNotIn("80 %", salida)


class ConfianzaTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def confianza(self, linea, fuentes, *extra):
        return re.search(r"confianza ([a-z ]+) · ", self.hallazgo(linea, fuentes, *extra)[1]).group(1)

    def test_tres_fuentes_independientes_y_vigentes_dan_alta(self):
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3)), "alta")
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 2)), "media")
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 1)), "baja")

    def test_demanda_y_monetizacion_exigen_una_fuente_medida(self):
        for linea in ("demanda", "monetizacion"):
            fuentes = self.fuente(linea, 3)
            self.assertEqual(self.confianza(linea, fuentes), "media")
            self.assertEqual(self.confianza(linea, fuentes + self.fuente(linea, 1, "medido")), "alta")

    def test_el_mismo_dominio_cuenta_una_vez_salvo_con_autores_distintos(self):
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3, dominio="tienda.example")),
                         "baja")
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3, dominio="tienda.example",
                                                                   autor="App")), "alta")

    def test_las_fuentes_vencidas_o_sin_fecha_no_cuentan(self):
        viejas = self.fuente("competencia", 2, publicada="2024-01") + self.fuente("competencia", 1,
                                                                                publicada="sin-fecha")
        self.assertEqual(self.confianza("competencia", viejas), "baja")
        self.assertEqual(self.confianza("competencia", viejas + self.fuente("competencia", 3)), "alta")

    def test_el_peldano_limita_la_confianza(self):
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3, peldano=2)), "alta")
        for peldano in (3, 4, 5):
            self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3, peldano=peldano)), "media")
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3, peldano=6)), "baja")

    def test_sumar_una_fuente_de_un_peldano_lejano_no_baja_la_confianza(self):
        fuentes = self.fuente("competencia", 3, peldano=1) + self.fuente("competencia", 1, peldano=6)
        identificador, salida = self.hallazgo("competencia", fuentes)
        self.assertIn("confianza alta · triangulado (peldaño 1, directo", salida)

    def test_solo_opiniones_nunca_dan_alta(self):
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 3, "opinion")), "media")
        self.assertEqual(self.confianza("competencia", self.fuente("competencia", 2, "opinion")), "baja")

    def test_la_evidencia_en_contra_baja_la_confianza(self):
        favor, contra = self.fuente("competencia", 3), self.fuente("competencia", 3)
        self.assertEqual(self.confianza("competencia", favor, "--en-contra", contra[0]), "media")
        self.assertEqual(self.confianza("competencia", favor, "--en-contra", ",".join(contra)), "baja")
        self.assertIn("a favor y en contra", self.falla("hallazgo", "--linea", "competencia", "--texto", "x",
                                                        "--fuentes", favor[0], "--en-contra", favor[0]))

    def test_el_modelo_puede_bajarla_con_motivo_pero_nunca_subirla(self):
        identificador, _ = self.hallazgo("competencia", self.fuente("competencia", 2), "--critico")
        self.assertIn("solo se puede bajar", self.falla("confianza", "--hallazgo", identificador, "--bajar", "media",
                                                        "--motivo", "x"))
        self.assertIn("media → baja", self.p("confianza", "--hallazgo", identificador, "--bajar", "baja", "--motivo",
                                             "Las dos fuentes citan el mismo informe"))
        self.assertIn("confianza baja", self.p("triangulacion"))
        self.assertIn("Las dos fuentes citan el mismo informe", self.p("triangulacion"))
        self.assertIn("No existe el hallazgo", self.falla("confianza", "--hallazgo", "H-COM-9", "--bajar", "baja",
                                                          "--motivo", "x"))

    def test_la_ventana_de_vigencia_sale_de_los_criterios(self):
        fuentes = self.fuente("competencia", 3, publicada="2026-01")
        self.p("criterio", "--clave", "vigencia_meses", "--valor", 6)
        self.assertEqual(self.confianza("competencia", fuentes), "baja")


class HallazgoTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def test_exige_fuentes_que_existan(self):
        self.assertIn("No existe esta fuente: S-COM-9", self.falla(
            "hallazgo", "--linea", "competencia", "--texto", "x", "--fuentes", "S-COM-9"))
        self.falla("hallazgo", "--linea", "competencia", "--texto", "x")

    def test_un_hallazgo_puede_citar_fuentes_de_otra_linea(self):
        identificador, _ = self.hallazgo("diferenciacion", self.fuente("voz-del-usuario", 3, "usuario"))
        self.assertEqual(identificador, "H-DIF-1")
        guardado = self.datos("01-investigacion/diferenciacion.json")["hallazgos"][0]
        self.assertEqual(guardado["fuentes"], ["S-VOZ-1", "S-VOZ-2", "S-VOZ-3"])

    def test_triangulacion_dice_que_le_falta_a_cada_hallazgo_clave(self):
        self.assertIn("No hay hallazgos clave", self.p("triangulacion"))
        self.hallazgo("demanda", self.fuente("demanda", 2), "--critico")
        completo, salida = self.hallazgo("competencia", self.fuente("competencia", 3), "--critico", "--sin-contra",
                                         "Se buscó «app de riego cerró»: nada")
        self.assertNotIn("⚠", salida)
        self.hallazgo("competencia", self.fuente("competencia", 1))  # no es clave: no aparece
        salida = self.p("triangulacion")
        self.assertIn("✖ H-DEM-1", salida)
        self.assertIn("falta 1 fuente independiente y vigente (tiene 2 de 3)", salida)
        self.assertIn("falta una fuente de tipo medido", salida)
        self.assertIn("falta registrar la búsqueda de evidencia en contra", salida)
        self.assertIn("✔ %s" % completo, salida)
        self.assertNotIn("H-COM-2", salida)
        self.assertIn("1 de 2 hallazgos clave", salida)

    def test_anular_una_fuente_la_saca_de_las_cuentas(self):
        fuentes = self.fuente("competencia", 3)
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "nada")
        self.assertIn("1 de 1 hallazgos clave", self.p("triangulacion"))
        self.assertIn("ya no cuenta", self.p("anular", "--id", fuentes[0], "--motivo", "Era una nota de prensa"))
        self.assertIn("tiene 2 de 3", self.p("triangulacion"))
        self.assertIn("ya estaba anulado", self.falla("anular", "--id", fuentes[0], "--motivo", "x"))
        self.assertEqual(self.fuente("competencia"), ["S-COM-4"])  # el ID anulado no se reutiliza


class MatrizTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()
        self.fuentes = self.fuente("competencia", 3, "medido")

    def test_una_fila_se_completa_por_partes(self):
        salida = self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", self.fuentes[0],
                        "--descargas", "1M", "--nota", "4,2")
        self.assertIn("C-1 registrado", salida)
        self.assertIn("con tracción", salida)
        self.assertIn("Columnas sin dato", salida)
        salida = self.p("competidor", "--nombre", "riegofacil", "--peldano", 1, "--fuentes", self.fuentes[1],
                        "--idiomas", "es,en", "--anuncios", "muchos", "--funciones", "turnos; recordatorios")
        self.assertIn("C-1 actualizado", salida)
        fila = self.datos("01-investigacion/competencia.json")["matriz"][0]
        self.assertEqual((fila["descargas"], fila["nota"], fila["idiomas"], fila["funciones"]),
                         (1000000, 4.2, ["es", "en"], ["turnos", "recordatorios"]))
        self.assertEqual(fila["fuentes"], self.fuentes[:2])
        self.assertIn("No existe esta fuente", self.falla("competidor", "--nombre", "Otra", "--peldano", 1,
                                                                 "--fuentes", "S-COM-9"))

    def test_la_traccion_sale_de_las_descargas_o_de_un_respaldo_institucional(self):
        salida = self.p("competidor", "--nombre", "Chica", "--peldano", 3, "--fuentes", self.fuentes[0], "--descargas",
                        "50k")
        self.assertIn("sin tracción: 50 000 descargas, bajo el umbral de 100 000", salida)
        # una nota de tracción es contexto: no cuenta (feedback #30)
        salida = self.p("competidor", "--nombre", "Servicio de jardineros", "--peldano", 4, "--fuentes",
                        self.fuentes[1], "--traccion", "2 000 clientes al mes")
        self.assertIn("sin tracción: sin descargas, valoraciones ni respaldo registrados", salida)
        self.assertIn("La nota de tracción («2 000 clientes al mes») es contexto y no cuenta", salida)
        salida = self.p("competidor", "--nombre", "Servicio de jardineros", "--peldano", 4, "--fuentes",
                        self.fuentes[1], "--respaldo", "Programa municipal de huertos")
        self.assertIn("con tracción: respaldo institucional: Programa municipal de huertos", salida)

    def test_matriz_enlaza_los_hallazgos_por_nombre_o_por_id(self):
        self.assertIn("La matriz está vacía", self.p("matriz"))
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", self.fuentes[0], "--descargas",
               "1M")
        _, salida = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 1, "usuario"), "--competidores",
                                  "riegofacil,Desconocida")
        self.assertIn("sin fila en la matriz todavía: Desconocida", salida)
        self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 1, "usuario"), "--competidores", "C-1")
        salida = self.p("matriz")
        self.assertIn("| C-1 | RiegoFácil ★ | 1 | 1 000 000 |", salida)
        self.assertIn("H-VOZ-1, H-VOZ-2", salida)
        self.assertIn("Competidor Desconocida: lo cita H-VOZ-1, pero no tiene fila en la matriz", salida)
        self.assertEqual(self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"][0]["competidores"],
                         ["C-1", "Desconocida"])  # el nombre que ya tiene fila se guarda por su ID


class DiferenciadorTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()
        fuentes = self.fuente("competencia", 2, "medido")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--tamano-mb", 80)
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[1], "--tamano-mb", 120)

    def diferenciador(self, vector, hallazgos, *extra, semanas=2):
        return self.p("diferenciador", "--vector", vector, "--texto", "Diferenciador inventado", "--hallazgos",
                      hallazgos, "--se-ve", "ficha", "--copiable", "alta", "--motivo", "Es un cambio de precio",
                      "--semanas", semanas, *extra)

    def test_viable_con_un_dolor_triangulado_en_dos_competidores(self):
        dolor, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 3, "usuario"), "--competidores",
                                 "RiegoFácil,PlantaPlus")
        salida = self.diferenciador("usabilidad", dolor)
        self.assertIn("✔ D-1 registrado: viable", salida)
        self.assertIn("triangulado en 2 competidores", salida)
        self.assertIn("fácil de copiar", salida)
        self.assertIn("falta el del uso", salida)

    def test_no_es_viable_con_un_solo_competidor_ni_sin_triangular(self):
        uno, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 3, "usuario"), "--competidores",
                               "RiegoFácil")
        dos, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 2, "usuario"), "--competidores",
                               "RiegoFácil,PlantaPlus")
        for hallazgo in (uno, dos):
            salida = self.diferenciador("usabilidad", hallazgo)
            self.assertIn("registrado: no viable", salida)
            self.assertIn("✖ Evidencia", salida)

    def test_viable_con_un_vector_medible_comprobado_en_la_matriz(self):
        hallazgo, _ = self.hallazgo("competencia", self.fuente("competencia", 1, "medido"))
        self.assertIn("vector medible comprobado en la matriz (C-1, C-2)", self.diferenciador("rendimiento", hallazgo))
        self.assertIn("registrado: no viable", self.diferenciador("idioma", hallazgo))  # la matriz no trae idiomas
        self.assertIn("registrado: no viable", self.diferenciador("segmento", hallazgo))  # no es un vector medible

    def test_no_es_viable_si_no_cabe_en_el_presupuesto(self):
        hallazgo, _ = self.hallazgo("competencia", self.fuente("competencia", 1, "medido"))
        salida = self.diferenciador("rendimiento", hallazgo, semanas=8)
        self.assertIn("registrado: no viable", salida)
        self.assertIn("✖ Presupuesto: 8 de 6 semanas", salida)

    def test_solo_hay_un_principal_y_exige_hallazgos(self):
        hallazgo, _ = self.hallazgo("competencia", self.fuente("competencia", 1, "medido"))
        self.diferenciador("rendimiento", hallazgo, "--principal")
        self.assertIn("D-1 deja de ser el diferenciador principal", self.diferenciador("rendimiento", hallazgo,
                                                                                    "--principal"))
        principales = [d["id"] for d in self.datos("01-investigacion/diferenciacion.json")["diferenciadores"]
                       if d["principal"]]
        self.assertEqual(principales, ["D-2"])
        self.assertIn("No existe este hallazgo", self.falla("diferenciador", "--vector", "precio", "--texto", "x", "--hallazgos",
                                                 "H-COM-9", "--se-ve", "uso", "--copiable", "baja", "--motivo", "x",
                                                 "--semanas", 1))
        self.falla("diferenciador", "--vector", "magia", "--texto", "x", "--hallazgos", hallazgo, "--se-ve", "uso",
                   "--copiable", "baja", "--motivo", "x", "--semanas", 1)


class PuntajeTest(Base):
    def test_exige_el_tipo_y_cinco_valores_de_1_a_5(self):
        self.nuevo()
        self.assertIn("Falta el tipo de idea", self.falla("puntaje", "--valores", "4,4,4,4,1"))
        self.p("tipo", "--existente", "--motivo", "Hay competencia directa")
        for valores in ("4,4,4,4", "4,4,4,4,6", "4,4,4,4,0", "a,b,c,d,e"):
            self.assertIn("cinco enteros de 1 a 5", self.falla("puntaje", "--valores", valores))

    def test_la_diferenciacion_respeta_su_ancla(self):
        self.investigacion(viable=False)
        self.assertIn("no hay ningún diferenciador viable", self.falla("puntaje", "--valores", "4,4,4,4,3"))
        self.p("puntaje", "--valores", "4,4,4,4,1")

    def test_con_un_diferenciador_viable_la_diferenciacion_no_puede_ser_1(self):
        self.investigacion()
        self.assertIn("Diferenciación = 1 no corresponde", self.falla("puntaje", "--valores", "4,4,4,4,1"))

    def test_total_confianza_global_y_comparacion_con_la_puerta_1(self):
        self.investigacion()
        salida = self.p("puntaje", "--valores", "4,4,4,4,3")
        self.assertIn("Total: 19/25 · confianza global: alta", salida)
        self.assertIn("el mínimo es 17/25 → lo alcanza", salida)
        self.assertIn("estimación, sin fuentes", salida)
        self.assertIn("confianza alta (H-DEM-1)", salida)
        self.assertIn("no lo alcanza", self.p("puntaje", "--valores", "3,3,3,3,3"))
        self.assertEqual(self.datos()["puntaje"]["total"], 15)

    def test_la_confianza_global_es_la_menor_y_marca_lo_que_no_tiene_evidencia(self):
        self.investigacion()
        self.p("confianza", "--hallazgo", "H-MON-1", "--bajar", "baja", "--motivo", "El dato es de otro mercado")
        self.assertIn("confianza global: baja", self.p("puntaje", "--valores", "4,4,4,4,3"))
        self.p("anular", "--id", "H-POL-1", "--motivo", "La política cambió")
        salida = self.p("puntaje", "--valores", "4,4,4,4,3")
        self.assertIn("⚠ Sin evidencia", salida)
        self.assertIn("confianza global: sin evidencia", salida)

    def test_el_riesgo_1_pide_una_mitigacion(self):
        self.investigacion()
        self.assertIn("pide una mitigación escrita", self.p("puntaje", "--valores", "5,5,5,1,3"))
        self.assertNotIn("pide una mitigación", self.p("puntaje", "--valores", "5,5,5,1,3", "--mitigacion",
                                                       "Sin anuncios en la versión para niños"))


class EscenariosTest(Base):
    def test_calcula_anuncios_y_compras_y_los_usuarios_para_la_meta(self):
        self.hasta_puerta1()
        salida = self.escenarios(dau=1000)
        # anuncios: 1000 × 5 × 30 × 0,4 / 1000 = 60; pago único: 5000 instalaciones × 0,02 × 4 × 0,85 = 340
        self.assertIn("| MX | 1 000 | 200 | 400 | 800 |", salida)
        self.assertIn("la alcanza (400)", salida)
        self.assertIn("hacen falta 750 usuarios activos diarios; el base supone 1 000", salida)
        self.assertNotIn("Estimación", salida)
        self.assertNotIn("Por analogía", salida)
        guardado = self.datos()["escenarios"]
        self.assertEqual((guardado["base"], guardado["dau_meta"], guardado["rotulos"]), (400.0, 750, []))

    def test_un_supuesto_sin_fuente_lo_vuelve_estimacion(self):
        self.hasta_puerta1()
        salida = self.escenarios(dau=100, fuente="")
        self.assertIn("⚠ Estimación: supuestos sin fuente: MX.dau", salida)
        self.assertIn("no la alcanza (40)", salida)
        self.assertEqual(self.datos()["escenarios"]["rotulos"], ["estimación"])

    def test_con_una_fuente_de_un_analogo_va_por_analogia_y_abre_el_rango(self):
        self.hasta_puerta1()
        analogo = self.fuente("monetizacion", 1, "medido", peldano=3)[0]
        salida = self.escenarios(dau=1000, fuente=analogo)
        self.assertIn("por analogía", salida)
        self.assertIn("| **Total** | 1 000 | 100 | 400 | 1 200 |", salida)
        self.assertIn("MX.dau (%s, peldaño 3)" % analogo, salida)

    def test_una_idea_nueva_siempre_va_por_analogia(self):
        self.hasta_puerta1()
        self.p("tipo", "--nueva", "--motivo", "Los directos resultaron no serlo")
        self.assertIn("por analogía", self.escenarios(dau=1000))

    def test_rechaza_entradas_invalidas(self):
        self.hasta_puerta1()
        self.assertIn("que no existe", self.falla_escenarios(fuente="S-MON-99"))
        self.assertIn("No existe", self.falla("escenarios", "--entrada", "no-esta.json"))
        write(self.carpeta / "mal.json", "{")
        self.assertIn("no es JSON válido", self.falla("escenarios", "--entrada", "mal.json"))
        write(self.carpeta / "mal.json", json.dumps({"mercados": [{"mercado": "MX", "dau": 10}]}))
        self.assertIn("no tiene `anuncios` ni `compras`", self.falla("escenarios", "--entrada", "mal.json"))
        compra = {"nombre": "x", "conversion": 0.01, "precio": 1, "comision": 30}
        write(self.carpeta / "mal.json", json.dumps({"mercados": [{"mercado": "MX", "dau": 10, "dau_mau": 0.2,
                                                                  "compras": [compra]}]}))
        self.assertIn("`MX.compras.x` necesita `tipo`: pago-unico",
                      self.falla("escenarios", "--entrada", "mal.json"))
        compra["tipo"] = "suscripcion"
        write(self.carpeta / "mal.json", json.dumps({"mercados": [{"mercado": "MX", "dau": 10, "dau_mau": 0.2,
                                                                  "compras": [compra]}]}))
        # la tasa no es siempre 0.15 o 0.30: la del programa y el mercado, con su fuente oficial (feedback #78 b)
        self.assertIn("la tasa de tu programa y mercado, con su fuente oficial",
                      self.falla("escenarios", "--entrada", "mal.json"))

    def falla_escenarios(self, fuente):
        entrada = {"mercados": [{"mercado": "MX", "dau": {"pesimista": 1, "base": 2, "optimista": 3,
                                                           "fuente": fuente},
                                 "anuncios": [{"formato": "banner", "impresiones_por_dau": 1, "ecpm": 1}]}]}
        write(self.carpeta / "mal.json", json.dumps(entrada))
        return self.falla("escenarios", "--entrada", "mal.json")

    def test_la_plantilla_de_escenarios_se_puede_calcular_tal_cual(self):
        self.nuevo()
        salida = self.p("escenarios", "--entrada", "escenarios.json")
        self.assertIn("⚠ Estimación", salida)
        self.assertIn("Mercado de ejemplo", salida)


class FlujoTest(Base):
    def test_cerrar_exige_el_entregable_completo(self):
        self.nuevo()
        salida = self.falla("cerrar", "--sesion", "0")
        self.assertIn("00-idea.md todavía tiene", salida)
        self.assertIn("criterios.md todavía tiene texto de plantilla", salida)
        self.assertIn("falta el tipo de idea provisional", salida)
        self.assertIn("No existe la sesión", self.falla("cerrar", "--sesion", "9"))
        self.completar("00-idea.md")
        self.completar("criterios.md")
        self.p("criterio", "--clave", "meta_ingresos_mes", "--valor", 300)
        self.p("tipo", "--existente", "--provisional", "--motivo", "Triaje inventado de la sesión 0")
        self.assertIn("Sesión 0 · Idea cerrada", self.p("cerrar", "--sesion", "0"))
        self.completar("01-investigacion/competencia.md")
        salida = self.falla("cerrar", "--sesion", "1a")
        self.assertIn("falta confirmar el tipo de idea", salida)
        self.assertIn("la matriz no tiene ninguna fila", salida)
        self.assertIn("no tiene ningún hallazgo", salida)
        self.assertIn("antes va la sesión 1a", self.falla("cerrar", "--sesion", "1g"))
        self.assertIn("antes va la puerta 1", self.falla("cerrar", "--sesion", "2"))

    def test_sin_presupuesto_ni_objetivo_la_sesion_0_no_cierra_y_la_meta_es_opcional(self):
        self.p("nuevo", "--nombre", "Riego en turnos")
        self.completar("00-idea.md")
        self.completar("criterios.md")
        salida = self.falla("cerrar", "--sesion", "0")
        self.assertNotIn("meta_ingresos_mes", salida)
        self.assertIn("falta el criterio `presupuesto_semanas`", salida)
        self.assertIn("falta el objetivo de la sesión 0", salida)
        self.p("criterio", "--clave", "presupuesto_semanas", "--valor", 6)
        self.p("objetivo", "--mercados", "MX", "--idiomas", "es", "--tiendas", "ninguna")
        self.p("tipo", "--existente", "--provisional", "--motivo", "Triaje inventado de la sesión 0")
        self.assertIn("✔ Sesión 0 · Idea cerrada", self.p("cerrar", "--sesion", "0"))

    def test_las_cinco_lineas_van_en_paralelo_y_1g_se_abre_con_1a_y_1b(self):
        salida = self.sesion0()
        self.assertIn("Puedes abrir estos chats en paralelo", salida)
        for sesion in ("1a · Competencia", "1b · Voz del usuario", "1c · Demanda", "1d · Monetización",
                       "1e · Políticas y riesgos"):
            self.assertIn("Chat nuevo · Sesión %s · Modelo: Sonnet 5.5 · Esfuerzo: medio" % sesion, salida)
        self.assertIn("Sigue hb-product con %s: sesión 1a · Competencia. Idea existente (provisional: la confirma "
                      "1a). No hagas commit ni push." % (self.carpeta / "estado.md"), salida)
        self.assertNotIn("Chat nuevo · Sesión 1g", salida)
        self.assertIn("1g · Diferenciación se abre apenas cierren 1a y 1b", salida)
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--variante", "--motivo", "Hay directos, pero ninguno reparte turnos")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0])
        self.sustituto(fuentes[1])
        self.p("competidor", "--sin-rival", "Las apps directas son de pago y el grupo de chat no resuelve")
        self.hallazgo("competencia", fuentes)
        self.assertNotIn("Sesión 1g", self.cerrar("1a", "01-investigacion/competencia.md").split("La sesión")[0])
        salida = self.linea("1b", "voz-del-usuario") and self.p("siguiente")
        self.assertIn("Chat nuevo · Sesión 1g · Diferenciación · Modelo: Opus 5.5 · Esfuerzo: alto", salida)
        self.assertIn("Chat nuevo · Sesión 1c · Demanda", salida)  # 1g no espera a 1c–1e
        self.assertIn("idea variante", salida)
        self.assertNotIn("Chat nuevo · Sesión 1f", salida)

    def test_de_la_idea_al_prd_con_las_tres_puertas(self):
        salida = self.hasta_puerta1()
        self.assertIn("Puerta 1 · Oportunidad · idea existente · cumple 5 de 5 criterios", salida)
        self.assertIn("✔ Los hallazgos del diferenciador principal están triangulados y supera al rival C-2 "
                      "(PlantaPlus) · D-1: H-VOZ-1", salida)
        self.assertNotIn("puerta --n", salida)  # el veredicto ya viene en siguiente: no hay paso aparte
        self.assertIn("el agente nunca corre este comando", salida)
        self.assertIn("decidir --puerta 1 --seguir --carpeta product", salida)
        self.assertIn("cd %s && python3 -I " % self.tmp, salida)
        salida = self.p("puerta", "--n", 1)
        self.assertIn("Puerta 1 · Oportunidad · idea existente", salida)
        self.assertIn("✔ Puntaje de 17/25 o más · tiene 19/25", salida)
        self.assertIn("✔ Demanda con confianza media o alta · es alta", salida)
        self.assertIn("✔ Al menos 1 diferenciador viable", salida)
        self.assertIn("Criterios: cumple 5 de 5.", salida)
        self.assertIn("La cantidad de competidores no es un criterio", salida)
        self.assertIn("Antes hay que decidir seguir en la puerta 1", self.falla("decidir", "--puerta", 2, "--seguir"))

        salida = self.p("decidir", "--puerta", 1, "--seguir")
        self.assertIn("Puedes abrir estos chats en paralelo", salida)
        self.assertIn("Sesión 2 · Estrategia · Modelo: Opus 5.5 · Esfuerzo: alto", salida)
        self.assertIn("Sesión 3 · Validación documental", salida)
        self.assertIn("Puerta 1: seguir, decidida el %s" % HOY, salida)
        self.assertIn("decidir --puerta 1 --reabrir", salida)
        self.escenarios()
        self.assertIn("Sesión 3", self.cerrar("2", "02-estrategia.md"))  # la puerta 2 espera a las dos
        write(self.carpeta / "03-validacion.md", HIPOTESIS)
        self.assertIn("Puerta 2 · Viabilidad · idea existente · cumple 3 de 3 criterios", self.cerrar("3"))
        salida = self.p("puerta", "--n", 2)
        self.assertIn("✔ Al menos un modelo de monetización viable con evidencia · Anuncios · banner: 120 USD al mes "
                      "en el caso base; Pago único · Premium: 680 USD al mes en el caso base", salida)
        self.assertIn("· Meta de ingresos (referencial, no es criterio): el caso base da 800 de 300 USD al mes", salida)
        self.assertIn("✔ Ninguna hipótesis crítica refutada", salida)
        self.assertIn("✔ El diferenciador principal sobrevive al abogado del diablo", salida)

        self.assertIn("Sesión 4 · PRD", self.p("decidir", "--puerta", 2, "--seguir"))
        write(self.carpeta / "04-prd.md", PRD)
        self.assertIn("Puerta 3 · Alcance · idea existente · cumple 6 de 6 criterios", self.cerrar("4"))
        salida = self.p("puerta", "--n", 3)
        for criterio in ("El MVP cabe en el presupuesto de semanas · 5 de 6 semanas",
                         "El diferenciador principal está en el MVP · D-1 en F-01",
                         "100 % de las funcionalidades del MVP con trazabilidad · 2 de 2",
                         "Métricas HEART definidas", "Checklist de políticas sin bloqueos"):
            self.assertIn("✔ " + criterio, salida)
        salida = self.p("decidir", "--puerta", 3, "--seguir")
        self.assertIn("Proceso cerrado", salida)
        self.assertIn("hb-implement", salida)
        guardadas = self.datos("decisiones.json")
        self.assertEqual([(d["puerta"], d["decision"], d["cumple"], d["total"]) for d in guardadas],
                         [(1, "seguir", 5, 5), (2, "seguir", 3, 3), (3, "seguir", 6, 6)])
        self.assertTrue(all(d["fecha"].startswith(HOY) and d["criterios"] for d in guardadas))
        estado = self.p("estado")
        self.assertIn("| P3 · Alcance | seguir el %s" % HOY, estado)
        self.assertIn("Puntaje: 19/25", estado)
        self.assertIn("Proceso cerrado", (self.carpeta / "estado.md").read_text(encoding="utf-8"))

    def test_seguir_con_criterios_sin_cumplir_queda_anotado(self):
        self.investigacion()
        self.p("puntaje", "--valores", "2,2,2,2,2")
        self.assertIn("antes cierra la sesión 1f", self.falla("decidir", "--puerta", 1, "--seguir"))
        self.cerrar("1f", "01-sintesis.md")
        self.assertIn("La skill recomienda descartar (veredicto: No viable; El puntaje es 10/25, bajo el mínimo de 17)",
                      self.falla("decidir", "--puerta", 1, "--seguir"))
        salida = self.p("decidir", "--puerta", 1, "--seguir", "--motivo", "Quiero probarlo igual con lo que hay")
        self.assertIn("cumplía 4 de 5 criterios", salida)
        self.assertIn("Sigues con 1 criterio sin cumplir", salida)

    def test_la_decision_registra_desde_donde_se_corrio(self):
        self.hasta_puerta1()
        os.environ["CLAUDECODE"] = "1"
        self.addCleanup(os.environ.pop, "CLAUDECODE", None)
        salida = self.p("decidir", "--puerta", 1, "--seguir")
        self.assertIn("(chat de Claude Code); si no fue tu decisión", salida)
        self.assertEqual(self.datos("decisiones.json")[0]["desde"], "chat de Claude Code")

    def test_reabrir_una_puerta_la_deja_pendiente(self):
        self.hasta_puerta1()
        self.assertIn("no tiene ninguna decisión vigente", self.falla("decidir", "--puerta", 1, "--reabrir"))
        self.p("decidir", "--puerta", 1, "--seguir")
        salida = self.p("decidir", "--puerta", 1, "--reabrir")
        self.assertIn("vuelve a quedar pendiente", salida)
        self.assertIn("Puerta 1 · Oportunidad · idea existente", salida)
        self.assertIn("| P1 · Oportunidad | pendiente |", self.p("estado"))

    def test_ajustar_reabre_la_sesion_y_lo_que_depende_de_ella(self):
        self.hasta_puerta2()
        self.assertIn("--ajustar lleva una sesión anterior a la puerta 2", self.falla(
            "decidir", "--puerta", 2, "--ajustar", "4"))
        salida = self.p("decidir", "--puerta", 2, "--ajustar", "3", "--motivo", "Quiero revisar las hipótesis")
        self.assertIn("Se reabren: 3.", salida)
        self.assertIn("Chat nuevo · Sesión 3", salida)
        self.assertNotIn("Chat nuevo · Sesión 2", salida)
        self.assertIn("La puerta 2 se ajustó (sesión 3)", self.cerrar("3"))
        salida = self.p("decidir", "--puerta", 2, "--ajustar", "1c", "--motivo", "Quiero más datos de demanda")
        self.assertIn("Se reabren: 1c, 1f, 2, 3.", salida)
        self.assertIn("Chat nuevo · Sesión 1c", salida)
        self.assertIn("| P1 · Oportunidad | pendiente |", self.p("estado"))
        self.cerrar("1c")
        self.assertIn("Puerta 1 · Oportunidad · idea existente", self.cerrar("1f"))

    def test_descartar_exige_el_motivo_y_archiva_la_idea(self):
        self.hasta_puerta1()
        self.assertIn("motivo completo", self.falla("decidir", "--puerta", 1, "--descartar", "no"))
        salida = self.p("decidir", "--puerta", 1, "--descartar", "Los tres líderes ya ofrecen pago único",
                        "--motivo", "Prefiero no competir con los líderes")
        destino = self.carpeta / "archivo" / "riego-en-turnos"
        self.assertIn("idea descartada y archivada en %s" % destino, salida)
        self.assertEqual(sorted(p.name for p in self.carpeta.iterdir()), ["archivo"])
        archivado = json.loads((destino / "producto.json").read_text(encoding="utf-8"))
        self.assertEqual(archivado["archivo"]["motivo"], "Los tres líderes ya ofrecen pago único")
        self.assertEqual(json.loads((destino / "decisiones.json").read_text(encoding="utf-8"))[-1]["decision"],
                         "descartar")
        salida = self.p("siguiente")
        self.assertIn("riego-en-turnos: Los tres líderes ya ofrecen pago único", salida)
        salida = self.p("reabrir")
        self.assertIn("reabierta", salida)
        self.assertIn("Puerta 1 · Oportunidad · idea existente", salida)
        self.assertFalse((self.carpeta / "archivo" / "riego-en-turnos").exists())


class IdeaNuevaTest(Base):
    def investigar(self, intento="sin-rastro", analogos=2):
        self.sesion0()
        self.p("tipo", "--nueva", "--motivo", "No hay apps de turnos de riego entre vecinos")
        fuentes = self.fuente("competencia", 3, "medido", peldano=3)
        for indice in range(analogos):
            self.p("competidor", "--nombre", "Turnos de limpieza %d" % indice, "--peldano", 3, "--fuentes",
                   fuentes[indice], "--descargas", "250k")
        self.p("competidor", "--nombre", "Lista en el ascensor", "--peldano", 4, "--fuentes", fuentes[2],
               "--sustituto", "gratuito", "--resuelve", "parcial")
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "nada")
        extra = ["--fuentes", fuentes[0]] if intento != "sin-rastro" else []
        self.p("intento", "--resultado", intento, "--texto", "Se buscaron apps cerradas y post-mortems", *extra)
        self.cerrar("1a", "01-investigacion/competencia.md")
        self.linea("1b", "voz-del-usuario", "usuario", 4)
        self.linea("1c", "demanda", "usuario", 5)
        self.linea("1d", "monetizacion", "terceros", 3)
        self.linea("1e", "politicas", "terceros", 1)
        self.cerrar("1g", "01-investigacion/diferenciacion.md")

    def test_no_se_descarta_por_falta_de_datos_usa_los_criterios_de_idea_nueva(self):
        self.investigar()
        salida = self.p("puntaje", "--valores", "3,3,4,4,1")
        self.assertIn("Total: 15/25 · confianza global: media", salida)
        self.assertIn("Puerta 1 (idea nueva): el mínimo es 15/25 → lo alcanza", salida)
        self.assertIn("Peldaño más cercano a lo directo con evidencia: 1", salida)
        self.cerrar("1f", "01-sintesis.md")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("idea nueva", salida)
        self.assertIn("✔ Puntaje de 15/25 o más", salida)
        self.assertIn("✔ El problema o la necesidad de fondo, con 3 fuentes de peldaño 4 o 5", salida)
        self.assertIn("✔ Al menos 2 análogos con tracción (peldaño 2 o 3) · 2 de 2: C-1 (250 000 descargas); C-2 (250 000 "
                      "descargas)", salida)
        self.assertIn("✔ Sin evidencia de que se probó y fracasó por falta de demanda · 1 búsqueda registrada", salida)
        self.assertNotIn("diferenciador viable", salida)
        self.assertIn("cumple 5 de 5", salida)

    def test_el_hallazgo_registra_su_peldano_y_la_confianza_queda_limitada(self):
        self.investigar()
        salida = self.p("triangulacion")
        self.assertIn("H-DEM-1 · confianza media · triangulado · peldaño 5 (necesidad de fondo)", salida)
        self.assertIn("H-VOZ-1 · confianza media · triangulado · peldaño 4 (sustituto)", salida)
        self.assertIn("H-POL-1 · confianza alta · triangulado · peldaño 1 (directo)", salida)

    def test_sin_registrar_la_busqueda_de_intentos_la_puerta_no_se_cumple(self):
        self.investigar()
        guardado = self.datos()
        guardado["intentos"] = []
        write(self.carpeta / "producto.json", json.dumps(guardado))
        self.p("puntaje", "--valores", "3,3,4,4,1")
        self.assertIn("✖ Sin evidencia de que se probó y fracasó por falta de demanda · la búsqueda no está "
                      "registrada", self.p("puerta", "--n", 1))

    def test_un_fracaso_por_demanda_y_pocos_analogos_se_marcan(self):
        self.investigar(intento="fracaso-demanda", analogos=1)
        self.p("puntaje", "--valores", "3,3,4,4,1")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("✖ Al menos 2 análogos con tracción (peldaño 2 o 3) · 1 de 2: C-1 (250 000 descargas)", salida)
        self.assertIn("✖ Sin evidencia de que se probó y fracasó por falta de demanda · 1 intento fallido por demanda",
                      salida)
        self.assertIn("necesita su fuente", self.falla("intento", "--resultado", "fracaso-otra-causa", "--texto",
                                                       "Cerró por falta de fondos"))

    def test_puertas_2_y_3_piden_la_hipotesis_mas_riesgosa(self):
        self.investigar()
        self.p("puntaje", "--valores", "3,3,4,4,1")
        self.cerrar("1f", "01-sintesis.md")
        self.p("decidir", "--puerta", 1, "--seguir")
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", HIPOTESIS.replace("| D-1 |", "| — |").replace(
            "30 % vuelve a los 30 días", "—"))
        self.cerrar("3")
        salida = self.p("puerta", "--n", 2)
        self.assertIn("✔ Al menos un modelo de monetización viable con evidencia (por analogía)", salida)
        self.assertNotIn("alcanza la meta", salida)
        self.assertIn("✖ La hipótesis más riesgosa, identificada y medible después del lanzamiento", salida)
        write(self.carpeta / "03-validacion.md", HIPOTESIS.replace("| D-1 |", "| — |"))
        self.assertIn("✔ La hipótesis más riesgosa, identificada y medible después del lanzamiento · HIP-01",
                      self.p("puerta", "--n", 2))
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", PRD)
        salida = self.p("puerta", "--n", 3)
        self.assertIn("✔ El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral · HIP-01 en "
                      "F-01", salida)
        self.assertIn("✖ El diferenciador principal está en el MVP · no hay un diferenciador principal", salida)
        write(self.carpeta / "04-prd.md", PRD.replace("| HIP-01 |", "| — |"))
        self.assertIn("✖ El MVP pone a prueba la hipótesis más riesgosa", self.p("puerta", "--n", 3))


class IdeaDebilTest(Base):
    """«Otra app de linterna»: muere en la puerta 1 por no tener diferenciador y por el riesgo, no por saturación."""

    def test_muere_en_la_puerta_1_por_el_diferenciador_y_el_riesgo(self):
        self.investigacion(viable=False)
        self.p("puntaje", "--valores", "5,2,5,1,1")
        self.assertIn("No hay ningún diferenciador viable", self.p("cerrar", "--sesion", "1g"))
        self.cerrar("1f", "01-sintesis.md")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("✖ Puntaje de 17/25 o más · tiene 14/25", salida)
        self.assertIn("✔ Demanda con confianza media o alta", salida)
        self.assertIn("✖ Al menos 1 diferenciador viable, con sus hallazgos triangulados y que supere al rival "
                      "C-2 (PlantaPlus) · 0 viables de 0 registrados", salida)
        self.assertIn("✖ Los hallazgos del diferenciador principal están triangulados y supera al rival C-2 "
                      "(PlantaPlus) · no hay un diferenciador principal registrado", salida)
        self.assertIn("✖ Riesgo de políticas distinto de 1, o con una mitigación escrita · es 1", salida)
        self.assertIn("ni la saturación ni la falta de datos descartan una idea", salida)
        motivo = "Sin diferenciador viable y con riesgo de políticas 1: el sistema ya trae la función"
        self.p("decidir", "--puerta", 1, "--descartar", motivo)
        archivada = self.carpeta / "archivo" / "riego-en-turnos"
        decision = json.loads((archivada / "decisiones.json").read_text(encoding="utf-8"))[-1]
        self.assertEqual((decision["decision"], decision["motivo"], decision["cumple"]), ("descartar", motivo, 1))
        fallidos = [c["texto"] for c in decision["criterios"] if not c["cumple"]]
        self.assertEqual(len(fallidos), 4)
        self.assertFalse(any("competidores" in texto for texto in fallidos))


class ValidacionTest(Base):
    def test_lee_la_tabla_y_calcula_la_confianza(self):
        self.hasta_puerta1()
        write(self.carpeta / "03-validacion.md", HIPOTESIS)
        salida = self.p("validacion")
        self.assertIn("HIP-01 · sostenida · confianza alta · la más riesgosa (30 % vuelve a los 30 días)", salida)
        self.assertIn("HIP-02 · sostenida · confianza alta · D-1", salida)
        self.assertIn("✔ 2 hipótesis, tabla completa", salida)

    def test_marca_lo_que_le_falta_a_la_tabla(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        self.assertIn("03-validacion.md todavía tiene 10 textos de plantilla", self.falla("cerrar", "--sesion", "3"))
        write(self.carpeta / "03-validacion.md", "# Validación\n\nSin tabla todavía.\n")
        self.assertIn("no tiene filas", self.falla("cerrar", "--sesion", "3"))
        self.p("confianza", "--hallazgo", "H-VOZ-1", "--bajar", "baja", "--motivo", "Las reseñas son de un solo mes")
        tabla = HIPOTESIS.replace("| sostenida | sí |", "| quizá | — |").replace(
            "Se buscaron quejas por pagos únicos: nada", "—").replace("H-DEM-1", "H-DEM-7")
        write(self.carpeta / "03-validacion.md", tabla)
        salida = self.p("validacion")
        for problema in ("HIP-01: el veredicto debe ser sostenida, débil o refutada",
                         "HIP-01: cita hallazgos que no existen: H-DEM-7",
                         "HIP-02: falta la evidencia en contra",
                         "HIP-02: figura como sostenida, pero su confianza es baja",
                         "marca exactamente una hipótesis como la más riesgosa (hay 0)"):
            self.assertIn("✖ " + problema, salida)
        self.assertIn("HIP-02: falta la evidencia en contra", self.falla("cerrar", "--sesion", "3"))

    def test_una_hipotesis_refutada_o_un_diferenciador_debil_no_pasan_la_puerta_2(self):
        self.hasta_puerta2()
        write(self.carpeta / "03-validacion.md", HIPOTESIS.replace("| sostenida | sí |", "| refutada | sí |"))
        salida = self.p("puerta", "--n", 2)
        self.assertIn("✖ Ninguna hipótesis crítica refutada · refutadas: HIP-01", salida)
        write(self.carpeta / "03-validacion.md", HIPOTESIS.replace("| D-1 | sostenida |", "| D-1 | débil |"))
        self.assertIn("✖ El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta · "
                      "D-1: HIP-02 débil", self.p("puerta", "--n", 2))
        write(self.carpeta / "03-validacion.md", HIPOTESIS.replace("| D-1 |", "| — |"))
        self.assertIn("ninguna hipótesis lo pone a prueba", self.p("puerta", "--n", 2))

    def test_el_escenario_base_por_debajo_de_la_meta_solo_bloquea_si_es_obligatoria(self):
        self.hasta_puerta2()
        self.escenarios(dau=100)
        salida = self.p("puerta", "--n", 2)
        self.assertIn("cumple 3 de 3 criterios", salida)
        self.assertIn("· Meta de ingresos (referencial, no es criterio): el caso base da 40 de 300 USD al mes",
                      salida)
        self.p("criterio", "--clave", "meta_obligatoria", "--valor", "si", "--motivo", "El usuario la exige")
        salida = self.p("puerta", "--n", 2)
        self.assertIn("✖ El escenario base alcanza la meta de ingresos (marcada como obligatoria) · 40 de 300 USD al "
                      "mes", salida)
        self.assertIn("cumple 3 de 4 criterios", salida)


class TrazabilidadTest(Base):
    def test_calcula_el_rice_y_la_trazabilidad_del_mvp(self):
        self.hasta_puerta2()
        salida = self.p("trazabilidad")  # la plantilla sin completar: la fila existe, pero no traza nada
        self.assertIn("✖ F-01 · RICE — (faltan alcance, impacto o semanas)", salida)
        self.assertIn("Trazabilidad del MVP: 0 de 0 funcionalidades", salida)
        write(self.carpeta / "04-prd.md", PRD)
        salida = self.p("trazabilidad")
        # F-01: 1000 × 2 × 100 % / 3; F-02: 800 × 1 × 100 % / 2; F-03: 100 × 0,5 × 100 % / 1
        self.assertIn("✔ F-01 (MVP) · RICE 666,67 · 3 semanas · 3 criterios de aceptación", salida)
        self.assertIn("✔ F-02 (MVP) · RICE 400 · 2 semanas · 2 criterios de aceptación", salida)
        self.assertIn("✔ F-03 · RICE 50 · 1 semana · 0 criterios de aceptación", salida)
        self.assertLess(salida.index("F-01"), salida.index("F-02"))
        self.assertIn("Trazabilidad del MVP: 2 de 2 funcionalidades (100 %) · 5 semanas de 6", salida)
        self.assertIn("✔ El diferenciador principal (D-1) está en el MVP", salida)
        self.assertIn("✔ Criterios de aceptación: 2 de 2 funcionalidades del MVP · 5 criterios", salida)
        self.assertIn("`cerrar --sesion 4`", salida)

    def test_la_confianza_del_hallazgo_entra_en_el_rice(self):
        self.hasta_puerta2()
        self.p("confianza", "--hallazgo", "H-COM-1", "--bajar", "media", "--motivo", "Datos de un solo mercado")
        write(self.carpeta / "04-prd.md", PRD)
        self.assertIn("F-02 (MVP) · RICE 320 ·", self.p("trazabilidad"))

    def test_marca_lo_que_no_tiene_hallazgo_metrica_o_diferenciador(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        roto = PRD.replace("| sí | H-COM-1 | — | M-02 |", "| sí | — | — | M-09 |").replace("| D-1 | M-01 |",
                                                                                         "| — | M-01 |")
        write(self.carpeta / "04-prd.md", roto + "| Datos de niños | bloqueo | falta el consentimiento |\n")
        salida = self.p("trazabilidad")
        self.assertIn("✖ F-02 (MVP)", salida)
        self.assertIn("sin hallazgo; métricas sin definir en la tabla HEART: M-09", salida)
        self.assertIn("Trazabilidad del MVP: 1 de 2 funcionalidades (50 %)", salida)
        self.assertIn("✖ El diferenciador principal (D-1) no está en ninguna funcionalidad del MVP", salida)
        salida = self.p("puerta", "--n", 3)
        self.assertIn("✖ 100 % de las funcionalidades del MVP con trazabilidad · 1 de 2", salida)
        self.assertIn("✖ El diferenciador principal está en el MVP", salida)
        self.assertIn("✖ Checklist de políticas sin bloqueos · bloqueos: Datos de niños", salida)

    def test_el_mvp_fuera_del_presupuesto_o_sin_metricas_no_pasa_la_puerta_3(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        self.assertIn("ninguna fila marcada como MVP", self.falla("cerrar", "--sesion", "4"))
        write(self.carpeta / "04-prd.md", PRD.replace("| 1000 | 2 | 3 |", "| 1000 | 2 | 5 |").replace(
            "| M-02 | Tarea | Turnos completados sin ayuda | 80 % |", "| M-02 | Tarea | Turnos completados | — |"))
        salida = self.p("puerta", "--n", 3)
        self.assertIn("✖ El MVP cabe en el presupuesto de semanas · 7 de 6 semanas", salida)
        self.assertIn("✖ Métricas HEART definidas · 2 métricas, 1 incompleta", salida)

    def test_las_tablas_dentro_de_un_bloque_de_codigo_no_cuentan(self):
        self.hasta_puerta2()
        write(self.carpeta / "04-prd.md", "```text\n%s\n```\n" % PRD)
        self.assertIn("no tiene la tabla de funcionalidades", self.falla("trazabilidad"))


class ArchivoTest(Base):
    def test_archivar_y_reabrir_no_pierden_nada(self):
        self.nuevo()
        self.fuente("demanda", 2)
        antes = sorted(str(p.relative_to(self.carpeta)) for p in self.carpeta.rglob("*") if p.is_file())
        self.falla("archivar")
        salida = self.p("archivar", "--motivo", "La retomo después del verano")
        self.assertIn("archivada en %s" % (self.carpeta / "archivo" / "riego-en-turnos"), salida)
        self.assertIn("No hay ninguna idea activa", self.falla("estado"))
        self.nuevo("Linterna")
        self.assertIn("Hay una idea activa", self.falla("reabrir"))
        self.p("archivar", "--motivo", "Era solo una prueba de la carpeta")
        self.assertIn("Elige cuál con --idea: linterna, riego-en-turnos", self.falla("reabrir"))
        self.assertIn("reabierta (estaba archivada: La retomo después del verano)", self.p(
            "reabrir", "--idea", "riego-en-turnos"))
        despues = sorted(str(p.relative_to(self.carpeta)) for p in self.carpeta.rglob("*") if p.is_file()
                         and "archivo" not in p.relative_to(self.carpeta).parts)
        self.assertEqual(sorted(antes + ["reporte.html"]), despues)  # archivar y reabrir regeneran el reporte
        self.assertIsNone(self.datos()["archivo"])
        self.assertEqual(len(self.datos("01-investigacion/demanda.json")["fuentes"]), 2)

    def test_dos_ideas_con_el_mismo_nombre_no_se_pisan_en_el_archivo(self):
        for _ in range(2):
            self.nuevo()
            self.p("archivar", "--motivo", "Prueba de nombres repetidos")
        self.assertEqual(sorted(p.name for p in (self.carpeta / "archivo").iterdir()),
                         ["riego-en-turnos", "riego-en-turnos-2"])


class ParaleloTest(Base):
    def test_varias_sesiones_a_la_vez_no_pierden_ni_duplican_fuentes(self):
        self.nuevo()
        entorno = dict(ENV, HB_PRODUCT_HOY=HOY)

        def registrar(caso):
            linea, indice = caso
            return subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "fuente", "--linea", linea, "--url",
                 "https://%s-%d.example/a" % (linea, indice), "--publicada", "2026-06", "--tipo", "terceros",
                 "--peldano", "1", "--resumen", "x", "--carpeta", str(self.carpeta)],
                env=entorno, capture_output=True, text=True, encoding="utf-8")

        lineas = ("competencia", "voz-del-usuario", "demanda", "monetizacion", "politicas")
        casos = [(linea, indice) for linea in lineas for indice in range(4)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as grupo:
            resultados = list(grupo.map(registrar, casos))
        self.assertEqual([r.returncode for r in resultados], [0] * len(casos), resultados[0].stderr)
        for linea in lineas:
            fuentes = self.datos("01-investigacion/%s.json" % linea)["fuentes"]
            self.assertEqual(sorted(f["id"] for f in fuentes),
                             ["S-%s-%d" % (producto.LINEAS[linea][0], n) for n in range(1, 5)])
            self.assertEqual(len({f["url"] for f in fuentes}), 4)
        self.assertFalse((self.carpeta / producto.CANDADO).exists())
        self.assertIn("20 fuentes", self.p("estado"))

    def test_un_candado_abandonado_no_bloquea_para_siempre(self):
        self.nuevo()
        candado = self.carpeta / producto.CANDADO
        candado.write_text("", encoding="utf-8")
        viejo = os.path.getmtime(str(candado)) - 120
        os.utime(str(candado), (viejo, viejo))
        self.assertEqual(self.fuente("demanda"), ["S-DEM-1"])


class UtilidadesTest(unittest.TestCase):
    def test_a_numero_entiende_sufijos_y_comas(self):
        casos = {"1M": 1000000, "500k": 500000, "1 500": 1500, "2,5": 2.5, "0.25": 0.25, "1.234,5": 1234.5,
                 "": 0, "muchos": 0}
        for texto, esperado in casos.items():
            self.assertEqual(producto.a_numero(texto), esperado, texto)

    def test_numero_usa_espacios_y_coma_decimal(self):
        self.assertEqual(producto.numero(1234567), "1 234 567")
        self.assertEqual(producto.numero(1234.5), "1 234,50")
        self.assertEqual(producto.numero(0.5), "0,50")

    def test_tabla_busca_por_encabezados_sin_acentos(self):
        texto = "| Métrica | Dimensión | ID | Meta |\n|:---|---:|---|---|\n| a | Retención | M-01 | 5 |\n\ntexto\n"
        filas = producto.tabla(texto, "id", "dimension", "metrica", "meta")
        self.assertEqual(producto.celda(filas[0], "dimension"), "Retención")
        self.assertIsNone(producto.tabla(texto, "id", "funcionalidad"))
        self.assertEqual(producto.celda({"hallazgos": " — "}, "hallazgos"), "")

    def test_la_carpeta_de_agents_acepta_la_linea_con_y_sin_vineta(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for linea in ("Carpeta: docs/producto", "- **Carpeta:** `docs/producto`", "* Carpeta: docs/producto"):
                write(base / "AGENTS.md", "## Stack\n\n- x\n\n## Producto\n\n%s\n\n## Git\n" % linea)
                self.assertEqual(producto.carpeta_de_agents(base), base / "docs/producto", linea)
            write(base / "AGENTS.md", "## Stack\n\n- Carpeta: otra\n")
            self.assertIsNone(producto.carpeta_de_agents(base))


if __name__ == "__main__":
    unittest.main()
