"""Tests de las mejoras #56 y #57 de hb-product: los vacíos por peldaño que se cuentan con su motivo (#56) y los vacíos
por límite de las herramientas que solo detienen el modo autónomo si el ajuste depende entero de ellos (#57).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import re
import unittest

import test_product as base
import test_product_demanda as demanda
import test_product_orquestado as orquestado

HOY = base.HOY
producto = base.producto


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


def vacio_id(salida):
    return re.search(r"V-[A-Z]{3}-\d+", salida).group(0)


# --- #56 · Vacíos por peldaño con su motivo -------------------------------------------------------------------------

class PeldanosPorMotivoTest(orquestado.Base):
    def vacio_peldano(self, peldano, motivo):
        return vacio_id(self.p("vacio", "--linea", "demanda", "--peldano", peldano, "--motivo", motivo, "--texto",
                               "Registro inventado del peldaño %s" % peldano, *(
                                   ["--buscadas", "foros y buscadores"] if motivo == "sin-resultados" else [])))

    def test_el_conteo_dice_el_motivo_de_cada_vacio_por_peldano(self):
        self.nueva_con_lineas(problema=False)
        sin_resultado = self.vacio_peldano(2, "sin-resultados")
        sin_leer = self.vacio_peldano(4, "herramienta")
        sin_buscar = self.vacio_peldano(5, "presupuesto")
        conteo = producto.conteo_peldanos(producto.Registro(self.carpeta, self.datos()["criterios"]))
        self.assertEqual((conteo[2]["sin_resultado"], conteo[4]["sin_leer"], conteo[5]["sin_buscar"]),
                         ([sin_resultado], [sin_leer], [sin_buscar]))
        self.assertEqual((conteo[4]["sin_resultado"], conteo[5]["sin_resultado"]), ([], []))
        # registrados: ninguno es «no buscado», así que el veredicto no cambia
        self.assertFalse(any(conteo[n]["no_buscado"] for n in (2, 4, 5)))
        salida = self.p("estado")
        self.assertIn("2 · variante: 0 (0 vigentes, 0 vencidos), buscado sin resultado (%s)" % sin_resultado, salida)
        self.assertIn("4 · sustituto: 0 (0 vigentes, 0 vencidos), sin leer por límite de las herramientas (%s)"
                      % sin_leer, salida)
        self.assertIn("5 · necesidad de fondo: 0 (0 vigentes, 0 vencidos), sin buscar por falta de presupuesto (%s)"
                      % sin_buscar, salida)
        self.assertEqual(salida.count("buscado sin resultado"), 1)
        self.p("reporte")
        html = (self.carpeta / producto.REPORTE).read_text(encoding="utf-8")
        self.assertIn("sin leer por límite de las herramientas (%s)" % sin_leer, html)
        self.assertIn("sin buscar por falta de presupuesto (%s)" % sin_buscar, html)

    def test_el_problema_sin_leer_no_se_da_por_buscado_y_el_veredicto_no_cambia(self):
        self.nueva_con_lineas(problema=False)
        cuatro, cinco = self.vacio_peldano(4, "herramienta"), self.vacio_peldano(5, "presupuesto")
        self.p("puntaje", "--valores", "3,3,4,4,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("sin buscar del todo (peldaño 4 sin leer por límite de las herramientas (%s); peldaño 5 sin "
                      "buscar por falta de presupuesto (%s)): ningún hallazgo reúne 3" % (cuatro, cinco), salida)
        self.assertIn("El problema en los peldaños 4 y 5 quedó sin buscar del todo", salida)
        self.assertNotIn("Se buscó el problema", salida)
        # con un vacío sin resultados en uno de los dos, sí se buscó
        self.vacio_peldano(5, "sin-resultados")
        self.assertIn("Se buscó el problema en los peldaños 4 y 5", self.p("puerta", "--n", 1))

    def test_buscar_en_peldanos_que_las_herramientas_no_leen_detiene_el_modo_autonomo(self):
        self.nueva_con_lineas(problema=False)
        self.vacio_peldano(4, "herramienta")
        self.p("puntaje", "--valores", "3,3,4,4,1")
        self.cerrar("1f", "01-sintesis.md")
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["sesion"], automatico["detener"]), ("1c", False))  # el peldaño 5 se puede buscar
        self.vacio_peldano(5, "herramienta")
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertTrue(automatico["detener"])
        self.assertIn("los peldaños 4 y 5 solo tienen vacíos por límite de las herramientas", automatico["motivo"])


# --- #57 · Vacíos de herramienta y ajustes -------------------------------------------------------------------------

class AjusteConVacioTest(demanda.Base):
    def setUp(self):
        super().setUp()
        self.debil = self.demanda_debil()  # sus fuentes son de MX, es y google-play

    def vacio(self, linea, opcion, valor):
        return vacio_id(self.p("vacio", "--linea", linea, opcion, valor, "--motivo", "herramienta", "--texto",
                               "Página dinámica inventada"))

    def bloqueo(self, por_resolver):
        return producto.bloqueo_herramienta(self.datos(), self.registro(), "1c", por_resolver)

    def test_si_el_hallazgo_a_triangular_solo_es_de_mercados_con_vacio_se_detiene(self):
        identificador = self.vacio("demanda", "--mercado", "MX")  # MX tiene fuentes: es un vacío parcial
        salida = self.p("puerta", "--n", 1)
        self.assertIn("AJUSTAR 1c", salida)  # el veredicto no cambia
        self.assertIn("La sesión 1c (demanda) tiene un vacío por límite de las herramientas (%s: mercado MX): antes de "
                      "ajustarla, dale al agente un navegador o aporta un CSV de reseñas (lo que el ajuste tiene que "
                      "resolver depende solo de ese vacío: %s solo tiene fuentes de mercado MX)" % (
                          identificador, self.debil), salida)
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertTrue(automatico["detener"])
        self.assertIn("Modo autónomo: aquí se detiene", self.falla("decidir", "--puerta", 1, "--automatico"))

    def test_si_el_ajuste_no_depende_del_vacio_decide_y_lo_deja_como_aviso(self):
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        identificador = self.vacio("demanda", "--mercado", "AR")
        salida = self.p("decidir", "--puerta", 1, "--automatico")
        self.assertIn("ajustar la sesión 1c", salida)
        self.assertIn("· La sesión 1c (demanda) tiene un vacío por límite de las herramientas (%s: mercado AR): el "
                      "vacío %s sigue: con las mismas herramientas no se resuelve, pero el ajuste no depende de él" % (
                          identificador, identificador), salida)
        self.assertNotIn("⚠ demanda tiene vacíos", salida)

    def test_el_idioma_y_la_tienda_tambien_cuentan(self):
        registro = self.registro()
        por = producto.vacios_herramienta_lineas(registro, ["demanda"])
        self.assertEqual(por, {})
        self.vacio("demanda", "--idioma", "es")
        estado, texto, vacios = producto.estado_hallazgo(
            self.registro(), self.debil, producto.vacios_herramienta_lineas(self.registro(), ["demanda"]))
        self.assertEqual((estado, texto), (True, "%s solo tiene fuentes de idioma es" % self.debil))
        self.assertEqual([v["valor"] for v in vacios], ["es"])

    def test_un_hallazgo_sin_etiquetas_no_se_sabe(self):
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        self.vacio("demanda", "--mercado", "AR")
        sin_etiquetas, _ = self.hallazgo("demanda", self.fuente("demanda", 1, "medido", cobertura=False), "--critico")
        registro = self.registro()
        por = producto.vacios_herramienta_lineas(registro, ["demanda"])
        self.assertIsNone(producto.estado_hallazgo(registro, sin_etiquetas, por)[0])
        self.assertIsNone(producto.estado_hallazgo(registro, "H-DEM-99", por)[0])
        # un hallazgo que no se sabe no basta para seguir: lo seguro, detenerse con los vacíos sin fuentes
        bloqueo = self.bloqueo([(True, {"hallazgos": [sin_etiquetas]}, "Triangular")])
        self.assertEqual((bloqueo["detener"], [v["valor"] for v in bloqueo["vacios"]]), (True, ["AR"]))
        # pero si otro hallazgo del ajuste tiene fuentes fuera del vacío, sigue
        bloqueo = self.bloqueo([(True, {"hallazgos": [sin_etiquetas, self.debil]}, "Triangular")])
        self.assertFalse(bloqueo["detener"])

    def test_sin_saber_que_resolver_conserva_lo_seguro(self):
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        self.vacio("demanda", "--mercado", "AR")
        bloqueo = self.bloqueo([(True, None, "Buscar algo")])
        self.assertEqual((bloqueo["detener"], bloqueo["motivo"]), (True, None))
        self.assertTrue(self.bloqueo([])["detener"])  # otra sesión que la recomendada: no se sabe
        # un ajuste que no pide búsquedas se puede hacer con las mismas herramientas
        bloqueo = self.bloqueo([(True, None, "Buscar algo"), (False, None, "Elegir el principal en la 1g")])
        self.assertEqual((bloqueo["detener"], bloqueo["motivo"]),
                         (False, "«Elegir el principal en la 1g» no pide búsquedas"))

    def test_un_vacio_parcial_sin_nada_que_dependa_de_el_no_dice_nada(self):
        self.vacio("demanda", "--idioma", "es")
        self.assertIsNone(self.bloqueo([(False, None, "Elegir")]))
        self.assertIsNone(self.bloqueo([(True, None, "Buscar algo")]))  # sin vacíos sin fuentes: como antes

    def test_un_hallazgo_nuevo_de_la_linea_se_detiene_solo_si_ningun_mercado_se_puede_leer(self):
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        self.vacio("demanda", "--mercado", "AR")
        datos, registro = self.datos(), self.registro()
        alcance = {"linea": "demanda"}
        estado = producto.estado_alcance(datos, registro, alcance,
                                         producto.vacios_herramienta_lineas(registro, ["demanda"]))
        self.assertEqual(estado[:2], (False, "se puede buscar en mercado MX"))
        self.vacio("demanda", "--mercado", "MX")
        registro = self.registro()
        estado = producto.estado_alcance(datos, registro, alcance,
                                         producto.vacios_herramienta_lineas(registro, ["demanda"]))
        self.assertEqual(estado[:2], (True, "cada mercado del objetivo (MX, AR) tiene un vacío por límite de las "
                                            "herramientas"))


if __name__ == "__main__":
    unittest.main()
