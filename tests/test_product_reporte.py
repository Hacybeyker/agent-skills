"""Tests del reporte de una idea (#15) y del tablero de ideas (#16) de hb-product: `producto.py reporte` y
`producto.py tablero`, con su regeneración al decidir cada puerta y al archivar.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import re
import unittest

import test_product as base
from helpers import write

HOY = base.HOY


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def reporte(self, carpeta=None):
        return ((carpeta or self.carpeta) / "reporte.html").read_text(encoding="utf-8")


class ReporteTest(Base):
    def test_un_solo_archivo_sin_red_con_svg_y_modo_oscuro(self):
        self.hasta_puerta1()
        salida = self.p("reporte")
        self.assertIn("✔ Reporte de \"Riego en turnos\": %s" % (self.carpeta / "reporte.html"), salida)
        html = self.reporte()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r'<link|src="|@import|url\(')  # nada se carga de la red
        self.assertIn("prefers-color-scheme:dark", html)
        self.assertIn("<svg", html)
        self.assertIn("<details", html)  # el detalle técnico, plegable

    def test_resumen_ejecutivo_arriba_y_tarjetas_con_titulo_debajo(self):
        self.hasta_puerta1()
        self.p("reporte")
        html = self.reporte()
        titulos = re.findall(r"<h2>([^<]+)</h2>", html)
        self.assertEqual(titulos[0], "Resumen ejecutivo")
        for titulo in ("Puntaje por criterio", "Puertas", "Diferenciadores", "Hallazgos clave",
                       "Competidores y sustitutos", "Cobertura por mercado, idioma y tienda",
                       "Escenarios de ingresos (solo referencia)", "Hipótesis más riesgosa", "Costo", "Glosario"):
            self.assertIn(titulo, titulos)
        self.assertIn("En curso", html)
        self.assertIn("Decidir la puerta 1 · Oportunidad", html)
        self.assertIn("19/25", html)
        self.assertIn("Pendiente de tu decisión", html)
        self.assertIn("Frente al sustituto", html)
        self.assertIn('href="https://sitio1.example/pagina-1"', html)  # las fuentes van enlazadas

    def test_decidir_lo_regenera_y_al_descartar_queda_en_el_archivo(self):
        self.hasta_puerta1()
        salida = self.p("decidir", "--puerta", 1, "--seguir")
        self.assertIn("· Reporte actualizado: %s" % (self.carpeta / "reporte.html"), salida)
        self.assertIn("Seguir", self.reporte())
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS)
        self.cerrar("3")
        salida = self.p("decidir", "--puerta", 2, "--descartar", "Los vecinos ya se organizan bien por chat",
                        "--motivo", "Un vecino me dijo que no la usaría")
        destino = self.carpeta / "archivo" / "riego-en-turnos"
        self.assertIn("· Reporte actualizado: %s" % (destino / "reporte.html"), salida)
        html = self.reporte(destino)
        self.assertIn("Descartada", html)
        self.assertIn("Los vecinos ya se organizan bien por chat", html)
        self.assertIn("descartada en la puerta 2", html)
        self.assertIn("HIP-01", html)  # la hipótesis más riesgosa
        self.assertIn("Ingresos netos al mes por escenario", html)
        # se regenera también dentro de la idea archivada, por su nombre o por su carpeta
        self.assertIn(str(destino / "reporte.html"), self.p("reporte", "--idea", "riego-en-turnos"))
        self.assertIn(str(destino / "reporte.html"), self.p("reporte"))  # la única archivada
        self.assertIn("No existe la idea archivada", self.falla("reporte", "--idea", "otra"))

    def test_archivar_lo_regenera_en_el_archivo(self):
        self.nuevo()
        salida = self.p("archivar", "--motivo", "La retomo después")
        destino = self.carpeta / "archivo" / "riego-en-turnos"
        self.assertIn("· Reporte actualizado: %s" % (destino / "reporte.html"), salida)
        html = self.reporte(destino)
        self.assertIn("Pausada", html)
        self.assertIn("La retomo después", html)
        self.assertIn("Todavía sin puntaje", html)

    def test_escapa_el_texto_y_no_muestra_comandos_en_lo_visible(self):
        self.p("nuevo", "--nombre", "Riego <b>en</b> \"turnos\"", "--semanas", 6)
        self.p("reporte")
        html = self.reporte()
        self.assertIn("Riego &lt;b&gt;en&lt;/b&gt; &quot;turnos&quot;", html)
        self.assertNotIn("<b>en</b>", html)
        self.assertIn("Sin objetivo de mercados", html)

    def test_una_carpeta_de_una_version_anterior_tambien_se_reporta(self):
        self.hasta_puerta2()
        producto = self.datos()
        for clave in ("objetivo", "propuestas", "consumo", "modelos", "herramienta"):
            producto.pop(clave, None)
        producto["escenarios"].pop("modelos")
        write(self.carpeta / "producto.json", json.dumps(producto))
        self.p("reporte")
        html = self.reporte()
        self.assertIn("Calculados con una versión anterior", html)
        self.assertIn("Sin objetivo de mercados", html)


class TableroTest(Base):
    def test_lista_las_ideas_en_curso_y_archivadas_con_su_reporte(self):
        raiz = self.tmp
        self.carpeta = raiz / "riego" / "product"
        self.hasta_puerta1()
        self.carpeta = raiz / "linterna" / "product"
        self.p("nuevo", "--nombre", "Linterna", "--semanas", 2)
        self.p("archivar", "--motivo", "La linterna del sistema ya resuelve la necesidad")
        write(raiz / ".oculta" / "product" / "producto.json", json.dumps({"nombre": "Oculta", "sesiones": {},
                                                                          "criterios": {}}))
        write(raiz / "rota" / "producto.json", "{no es json")
        salida = self.p("tablero", "--raiz", raiz)
        self.assertIn("✔ Tablero con 2 ideas: %s" % (raiz / "index.html"), salida)
        self.assertIn("⚠ No se pudo leer %s" % (raiz / "rota"), salida)
        html = (raiz / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("Oculta", html)  # las carpetas ocultas no se recorren
        self.assertIn('href="riego/product/reporte.html"', html)
        self.assertIn('href="linterna/product/archivo/linterna/reporte.html"', html)
        self.assertTrue((raiz / "linterna" / "product" / "archivo" / "linterna" / "reporte.html").is_file())
        self.assertTrue((raiz / "riego" / "product" / "reporte.html").is_file())
        self.assertLess(html.index("Riego en turnos"), html.index("Linterna"))  # primero las que están en curso
        self.assertIn("La linterna del sistema ya resuelve la necesidad", html)
        self.assertIn("Decidir la puerta 1", html)
        self.assertIn("19/25", html)
        self.assertIn("No se pudieron leer", html)
        self.assertIn("No existe la carpeta", self.falla("tablero", "--raiz", raiz / "nada"))

    def test_seguir_en_una_puerta_sigue_en_curso_y_la_puerta_3_la_deja_lista(self):
        raiz = self.tmp
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        self.p("tablero", "--raiz", raiz)
        html = (raiz / "index.html").read_text(encoding="utf-8")
        self.assertIn("En curso", html)
        self.assertIn("puerta 1 · seguir · %s" % HOY, html)
        self.assertIn("Tocan estas sesiones, en paralelo", html)
        self.p("decidir", "--puerta", 1, "--reabrir")
        self.carpeta = raiz / "otra" / "product"
        self.hasta_puerta3()
        self.p("decidir", "--puerta", 3, "--seguir")
        self.p("tablero", "--raiz", raiz)
        html = (raiz / "index.html").read_text(encoding="utf-8")
        self.assertIn("Lista para construir", html)
        self.assertIn("Puerta 3: seguir, con 5 de 5 criterios cumplidos.", html)

    def test_sin_ideas_lo_dice(self):
        self.assertIn("Tablero con 0 ideas", self.p("tablero", "--raiz", self.tmp))
        self.assertIn("No se encontró ninguna idea", (self.tmp / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
