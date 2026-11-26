"""Tests de la mejora #84 de hb-product.

(a) `fuente --vivo`: un dato vivo de una ficha o una búsqueda lleva la fecha de consulta, no avisa y es vigente.
(b) La puerta 1 en 🔴 por el puntaje con la demanda en confianza baja en la primera pasada de la 1c: si el ajuste
depende entero de vacíos de herramienta, la razón dice que reabrirla no lo resuelve; si no, y con la demanda en su
máximo el puntaje alcanzaría el mínimo, recomienda ajustar la 1c; si tampoco, dice por qué ajustarla no cambia nada.
(c) «Qué cambiaría» con el puntaje bajo el mínimo dice qué criterios podrían subir y cómo (la facilidad, solo
recortando el alcance del MVP).
#85: (a) una línea ya reabierta sin salida no se ofrece como camino para subir el puntaje: dice que ya se reabrió; (b)
el ajuste de la 1c por el puntaje va en una sola razón con la de la demanda.
La errata «falta el de el uso» (e) la cubre test_product.py.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import re
import unittest
from unittest import mock

import test_product as base
import test_product_demanda as demanda

HOY = base.HOY
SIN_DATOS = "sin datos no es lo mismo que sin demanda"


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


def llano(texto):
    return re.sub(r"\s+", " ", texto)


# --- (a) · fuente --vivo --------------------------------------------------------------------------------------------

class VivoTest(base.Base):
    def ficha(self, *extra):
        self.sitio += 1
        return self.p("fuente", "--linea", "competencia", "--url", "https://tienda.example/app-%d" % self.sitio,
                      "--tipo", "medido", "--peldano", 1, "--resumen", "Instalaciones y nota de la ficha", *extra)

    def test_lleva_la_fecha_de_consulta_no_avisa_y_es_vigente(self):
        self.nuevo()
        salida = self.ficha("--vivo")
        self.assertIn("vigente", salida)
        self.assertIn("Dato vivo de una ficha o una búsqueda: su fecha es la de consulta (%s)" % HOY, salida)
        self.assertNotIn("misma que la de consulta", salida)
        fuente = self.datos("01-investigacion/competencia.json")["fuentes"][0]
        self.assertEqual((fuente["publicada"], fuente["consultada"], fuente["vivo"]), (HOY, HOY, True))

    def test_con_otra_fecha_de_publicacion_o_un_archivo_falla(self):
        self.nuevo()
        self.assertIn("Con --vivo la fecha es la de consulta", self.falla(
            *self.args_ficha("--vivo", "--publicada", "2026-03")))
        self.assertIn("--vivo es para un dato vivo", self.falla(
            "fuente", "--linea", "voz-del-usuario", "--archivo", "/no/existe.csv", "--autor", "App A", "--tipo",
            "usuario", "--peldano", 1, "--resumen", "x", "--vivo"))

    def args_ficha(self, *extra):
        return ("fuente", "--linea", "competencia", "--url", "https://tienda.example/otra", "--tipo", "medido",
                "--peldano", 1, "--resumen", "x") + extra

    def test_sin_vivo_y_con_la_fecha_de_hoy_sugiere_vivo(self):
        self.nuevo()
        salida = llano(self.ficha("--publicada", HOY))
        self.assertIn("⚠ La fecha de publicación es la misma que la de consulta (%s). Si es un dato vivo de una ficha "
                      "o una búsqueda (instalaciones, precios, valoraciones, orden de resultados), regístralo con "
                      "`--vivo`" % HOY, salida)


# --- (b) · El 🔴 por puntaje con la demanda baja en la primera pasada ------------------------------------------------

class BajoMinimoTest(demanda.Base):
    def demanda_baja(self, valores):
        """Una idea viable con un hallazgo clave de demanda en confianza baja (una sola fuente) y el puntaje dado."""
        self.investigacion()
        debil, _ = self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--critico", "--sin-contra",
                                 "Se buscó y no apareció")
        self.p("puntaje", "--valores", valores)
        return debil

    def test_si_con_la_demanda_en_5_alcanza_el_minimo_ajusta_la_1c(self):
        self.demanda_baja("2,4,3,4,3")  # 16/25; con la demanda en 5, 19/25
        salida = llano(self.cerrar("1f", "01-sintesis.md"))
        self.assertIn("🟡 PUERTA 1 · VIABLE CON RESERVAS → la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("1. El puntaje es 16/25, bajo el mínimo de 17. La demanda actual tiene confianza baja en la "
                      "primera pasada de la 1c:", salida)
        self.assertIn("Confirmada, la demanda podría puntuar hasta 5 (hoy 2) y el puntaje llegaría hasta 19/25. 2.",
                      salida)
        self.assertIn("Triangular H-DEM-2 (faltan 2 fuentes independientes y vigentes, tiene 1 de 3) en la 1c con una "
                      "señal medida y reciente de demanda (tendencias de búsqueda, descargas o búsquedas de los "
                      "últimos 18 meses). Con la demanda confirmada, volver a puntuarla en la 1f: con 5 (hoy 2), el "
                      "puntaje llegaría hasta 19/25 (el mínimo es 17)", salida)
        self.assertNotIn("★ Recomendado · Descartar", salida)
        self.assertEqual(self.json()["pasos"][0]["automatico"]["sesion"], "1c")

    def test_la_demanda_baja_va_en_una_sola_razon_con_el_puntaje(self):
        """Feedback #85 b: la razón del puntaje y la de la demanda decían dos veces «confianza baja en la primera
        pasada, sin evidencia en contra»."""
        self.demanda_baja("2,4,3,4,3")
        salida = llano(self.cerrar("1f", "01-sintesis.md"))
        por_que = salida.split("Por qué:")[1].split("Qué cambiaría el veredicto:")[0]
        self.assertEqual(por_que.count("primera pasada de la 1c"), 1)
        self.assertEqual(por_que.count("evidencia en contra"), 1)
        self.assertNotIn("pero la demanda está en confianza baja", por_que)

    def test_si_ni_con_la_demanda_en_5_alcanza_sigue_en_rojo_sin_contradecirse(self):
        self.demanda_baja("1,3,2,3,3")  # 12/25; con la demanda en 5, 16/25
        salida = llano(self.cerrar("1f", "01-sintesis.md"))
        self.assertIn("🔴 PUERTA 1 · NO VIABLE", salida)
        self.assertIn("pero no hay evidencia en contra. Ajustar la 1c no cambiaría el veredicto: ni con la demanda en "
                      "5 (hoy 1) el puntaje llegaría al mínimo de 17 (quedaría en 16/25)", salida)
        self.assertNotIn(SIN_DATOS, salida)

    def test_si_el_ajuste_depende_de_vacios_de_herramienta_dice_que_reabrirla_no_lo_resuelve(self):
        self.demanda_baja("2,4,3,4,3")  # sus fuentes son de MX, el único mercado del objetivo
        self.p("vacio", "--linea", "demanda", "--mercado", "MX", "--motivo", "herramienta", "--texto",
               "La tendencia de búsqueda es un gráfico que no se lee como texto")
        salida = llano(self.cerrar("1f", "01-sintesis.md"))
        self.assertIn("🔴 PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Lo que falta depende de un vacío por límite de las herramientas (V-DEM-1: mercado MX): reabrir "
                      "la 1c con las mismas herramientas no lo resuelve", salida)
        self.assertNotIn(SIN_DATOS, salida)

    def test_con_otro_motivo_de_descarte_no_ajusta(self):
        debil = self.demanda_baja("2,4,3,4,3")  # con la demanda en 5 alcanzaría, pero hay otro motivo
        registro, datos = self.registro(), self.datos()
        fatales = [("El puntaje es 16/25, bajo el mínimo de 17", "x", None, True, None),
                   ("Otro motivo de descarte", "y", None, True, None)]
        ajustes = [("La demanda actual … (sin datos no es lo mismo que sin demanda)", "z", "1c", True,
                    {"hallazgos": [debil]})]
        motivo_de = {id(fatales[0]): "puntaje", id(fatales[1]): "intentos", id(ajustes[0]): "demanda"}
        nuevos, otros = demanda.producto.demanda_bajo_el_minimo(datos, registro, fatales, ajustes, motivo_de)
        self.assertEqual(nuevos, fatales)
        self.assertIn("lo demás que descarta la idea no depende de la demanda", otros[0][0])
        self.assertNotIn(SIN_DATOS, otros[0][0])


# --- (c) · Qué criterios podrían subir y cómo ------------------------------------------------------------------------

class SubirPuntajeTest(base.Base):
    def test_dice_por_criterio_como_subiria_y_la_facilidad_solo_recortando_el_alcance(self):
        self.investigacion()
        self.p("puntaje", "--valores", "5,3,3,3,2")  # 16/25; la demanda ya está en 5
        salida = llano(self.cerrar("1f", "01-sintesis.md"))
        self.assertIn("🔴 PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Subir el puntaje a 17/25 o más (falta 1 punto): monetización, hoy 3 (con evidencia nueva, 1d); "
                      "facilidad, hoy 3 (solo recortando el alcance del MVP: un cambio de alcance, con su motivo); "
                      "riesgo de políticas, hoy 3 (con evidencia nueva, 1e); diferenciación, hoy 2 (4 como máximo con "
                      "los viables de hoy: 5 pide dos viables que no se copien fácil o uno en la ficha difícil de "
                      "copiar)",
                      salida)
        self.assertNotIn("demanda, hoy", salida)
        self.assertNotIn("Evidencia nueva que suba el puntaje", salida)

    def test_la_demanda_sin_triangular_dice_el_tope(self):
        self.sesion0()
        self.p("tipo", "--existente", "--motivo", "Hay apps directas")
        registro_ = base.producto.Registro(self.carpeta, self.datos()["criterios"])
        datos = self.datos()
        datos["puntaje"] = {"valores": {"demanda": 3, "monetizacion": 3, "facilidad": 3, "riesgo": 5,
                                        "diferenciacion": 1}, "total": 15}
        modelo = base.producto.puntajes_por_modelo(datos, registro_)[0]
        texto = base.producto.texto_subir_puntaje(datos, registro_, modelo, 17)
        self.assertIn("faltan 2 puntos", texto)
        self.assertIn("demanda, hoy 3 (4 o 5 piden un hallazgo clave triangulado con señales actuales, 1c)", texto)
        self.assertIn("diferenciación, hoy 1 (pide un diferenciador viable, 1g)", texto)
        self.assertNotIn("riesgo de políticas", texto)



# --- #85 a · Una línea ya reabierta no se ofrece como camino para subir el puntaje -----------------------------------

class LineaReabiertaTest(demanda.Base):
    def test_con_la_1c_reabierta_la_demanda_no_se_ofrece_y_dice_que_ya_se_reabrio(self):
        self.investigacion()
        self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--critico", "--sin-contra",
                      "Se buscó y no apareció")
        self.p("puntaje", "--valores", "2,3,3,4,3")  # 15/25: ni con la demanda en 5 llega al mínimo
        self.cerrar("1f", "01-sintesis.md")
        self.p("decidir", "--puerta", 1, "--ajustar", "1c", "--motivo", "Quiero más evidencia de demanda")
        self.p("cerrar", "--sesion", "1c", "--busquedas", 3, "--lecturas", 2)
        salida = llano(self.cerrar("1f"))
        self.assertIn("🔴 PUERTA 1 · NO VIABLE", salida)
        self.assertIn("demanda, hoy 2 (no se vuelve a pedir: la 1c ya se reabrió, 3 de 8 búsquedas y 2 de 5 lecturas "
                      "en la reapertura 1)", salida)
        self.assertNotIn("señales actuales más fuertes, 1c", salida)
        self.assertNotIn("hallazgo clave triangulado con señales actuales, 1c", salida)
        self.assertIn("monetización, hoy 3 (con evidencia nueva, 1d)", salida)

    def test_cualquier_linea_sin_salida_dice_que_ya_se_reabrio(self):
        self.sesion0()
        self.p("tipo", "--existente", "--motivo", "Hay apps directas")
        registro_ = base.producto.Registro(self.carpeta, self.datos()["criterios"])
        datos = self.datos()
        datos["puntaje"] = {"valores": {"demanda": 3, "monetizacion": 3, "facilidad": 3, "riesgo": 3,
                                        "diferenciacion": 1}, "total": 13}
        modelo = base.producto.puntajes_por_modelo(datos, registro_)[0]
        sin_salida = {"1d": "reabierta una vez", "1g": "8 de 8 búsquedas y 5 de 5 lecturas en la reapertura 1"}
        with mock.patch.object(base.producto, "reaperturas_sin_salida", return_value=sin_salida):
            texto = base.producto.texto_subir_puntaje(datos, registro_, modelo, 17)
        self.assertIn("monetización, hoy 3 (no se vuelve a pedir: la 1d ya se reabrió)", texto)
        self.assertIn("diferenciación, hoy 1 (no se vuelve a pedir: la 1g ya se reabrió y usó su presupuesto, 8 de 8 "
                      "búsquedas y 5 de 5 lecturas en la reapertura 1)", texto)
        self.assertIn("riesgo de políticas, hoy 3 (con evidencia nueva, 1e)", texto)
        self.assertIn("facilidad, hoy 3 (solo recortando el alcance del MVP", texto)


if __name__ == "__main__":
    unittest.main()
