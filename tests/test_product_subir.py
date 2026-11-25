"""Tests de las mejoras #69 y #70 de hb-product.

#69: las sesiones que la puerta recomienda ajustar a la vez (las que corren en paralelo, #65) salen de todos los ajustes
que considera, no solo de las razones que se muestran: una propuesta pendiente (con alcance o sin él) que queda fuera de
las tres razones entra en la recomendación, y «Qué cambiaría» dice por qué. El veredicto no cambia.
#70: (a) «Qué cambiaría» y `triangulacion` dicen lo que de verdad le falta a cada hallazgo para subir de confianza (no
«triangular» a uno ya triangulado): la evidencia en contra, el peldaño, fuentes que no sean solo opinión o una confianza
bajada a mano; (b) `triangulacion` marca con «…» los resúmenes cortados.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import unittest

import test_product as base
import test_product_autonomo as autonomo
import test_product_paralelo as paralelo

HOY = base.HOY
producto = base.producto
tabla = paralelo.tabla


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


# --- #69 · Las sesiones en paralelo salen de todos los ajustes --------------------------------------------------------

class TodosLosAjustesTest(paralelo.Base):
    def puerta_con_la_2_fuera(self, *alcance):
        """La puerta 2 con cuatro ajustes: la hipótesis débil del principal y dos propuestas de la sesión 3, y al final
        una propuesta de la sesión 2, que queda fuera de las tres razones que se muestran."""
        self.puerta2(tabla())
        self.p("propuesta", "--texto", "Releer una reseña inventada", "--ajustar", "3")
        self.p("propuesta", "--texto", "Buscar otra hipótesis inventada", "--ajustar", "3")
        self.p("propuesta", "--texto", "Revisar el precio inventado del pago único", "--ajustar", "2", *alcance)
        return self.p("puerta", "--n", 2)

    def resultado(self):
        datos = self.datos()
        registro = producto.Registro(self.carpeta, datos["criterios"])
        return producto.veredicto(2, self.carpeta, datos, registro)

    def test_una_propuesta_fuera_de_las_razones_entra_en_la_recomendacion(self):
        salida = self.puerta_con_la_2_fuera()
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 2 y 3", salida)
        resultado = self.resultado()
        self.assertEqual(len(resultado["razones"]), 3)
        self.assertFalse(any("PR-3" in razon for razon in resultado["razones"]))
        self.assertEqual((resultado["nivel"], resultado["sesion"], resultado["sesiones"]), ("reservas", "3", ["2", "3"]))
        self.assertIn("A la vez, la 2 (corre en paralelo con la 3; su ajuste no está entre las razones de arriba): "
                      "aplicar la propuesta PR-3 al ajustar la sesión 2", salida)
        self.assertIn("decidir --puerta 2 --ajustar 2 3 --carpeta", salida)
        self.assertEqual(self.json()["pasos"][0]["automatico"]["sesiones"], ["2", "3"])

    def test_con_alcance_tambien_y_lo_que_resuelve_va_a_la_reapertura(self):
        salida = self.puerta_con_la_2_fuera("--hallazgos", "H-MON-1")
        self.assertIn("la skill recomienda: AJUSTAR 2 y 3", salida)
        self.assertIn("aplicar la propuesta PR-3 al ajustar la sesión 2 (resuelve H-MON-1)", salida)
        self.p("decidir", "--puerta", 2, "--ajustar", "2", "3")
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual(decision["resolver_sesiones"]["2"],
                         ["Aplicar la propuesta PR-3 al ajustar la sesión 2 (resuelve H-MON-1)"])

    def test_con_las_dos_sesiones_entre_las_razones_no_agrega_la_linea(self):
        salida = self.puerta_2_y_3()
        self.assertIn("la skill recomienda: AJUSTAR 2 y 3", salida)
        self.assertNotIn("A la vez, la", salida)

    def test_una_sola_sesion_sigue_igual(self):
        self.puerta2(tabla())
        self.p("propuesta", "--texto", "Releer una reseña inventada", "--ajustar", "3")
        self.assertIn("la skill recomienda: AJUSTAR 3\n", self.p("puerta", "--n", 2))
        self.assertEqual(self.resultado()["sesiones"], ["3"])


# --- #70 · Lo que le falta a cada hallazgo para subir de confianza ----------------------------------------------------

class ParaSubirTest(base.Base):
    def setUp(self):
        super().setUp()
        self.sesion0()  # las líneas 1a a 1e quedan abiertas para registrar hallazgos

    def registro(self):
        return producto.Registro(self.carpeta, self.datos()["criterios"])

    def triangulado(self, linea="demanda"):
        """Un hallazgo clave triangulado y en confianza alta: dos fuentes de terceros y una medida, de peldaño 1."""
        fuentes = self.fuente(linea, 2) + self.fuente(linea, 1, "medido")
        return self.hallazgo(linea, fuentes, "--critico", "--sin-contra", "Se buscó")[0]

    def subir(self, identificador, objetivo=None):
        registro = self.registro()
        return registro.para_subir(registro.hallazgos[identificador], objetivo)

    def test_triangulado_en_el_peldano_5_y_con_evidencia_en_contra(self):
        en_contra = self.fuente("demanda", 1, "medido")[0]
        identificador = self.hallazgo("demanda", self.fuente("demanda", 3, "medido", 5), "--critico", "--en-contra",
                                      en_contra)[0]
        registro = self.registro()
        evaluacion = registro.evaluar(registro.hallazgos[identificador])
        self.assertEqual((evaluacion["triangulado"], evaluacion["confianza"]), (True, "baja"))
        faltan = self.subir(identificador)
        self.assertEqual([clase for clase, _ in faltan], ["contra", "peldano", "fuentes"])
        self.assertEqual(faltan[0][1], "1 fuente independiente en contra le baja un nivel, así que para media "
                                       "necesita confianza alta en las fuentes a favor")
        self.assertEqual(faltan[1][1], "el peldaño 5, necesidad de fondo, llega como mucho a confianza media: alta "
                                       "pide fuentes de peldaño 1 o 2")
        self.assertEqual(faltan[2][1], "faltan 3 fuentes independientes y vigentes de peldaño 1 o 2 (tiene 0 de 3), "
                                       "con una de tipo medido y al menos 2 en total que no sean solo opinión (tiene 0)")
        texto = producto.falta_confianza(registro, registro.hallazgos[identificador], "1c")
        self.assertTrue(texto.startswith("%s (ya triangulado, en confianza baja: 1 fuente independiente en contra"
                                         % identificador), texto)
        self.assertIn("faltan 3 fuentes independientes y vigentes de peldaño 1 o 2, tiene 0 de 3", texto)
        self.assertEqual(producto.subir_o_triangular(registro, [registro.hallazgos[identificador]]),
                         "Subir a confianza media")
        salida = self.p("triangulacion")
        self.assertIn("    ↑ triangulado, pero para subir a confianza media: 1 fuente independiente en contra", salida)

    def test_solo_opinion_pide_fuentes_que_no_lo_sean(self):
        identificador = self.hallazgo("competencia", self.fuente("competencia", 3, "opinion"), "--sin-contra",
                                      "Se buscó")[0]
        registro = self.registro()
        self.assertEqual(registro.evaluar(registro.hallazgos[identificador])["confianza"], "media")
        self.assertEqual(self.subir(identificador),
                         [("fuentes", "faltan 2 fuentes independientes que no sean solo opinión (tiene 0 de 2)")])

    def test_bajada_a_mano_lo_dice_y_no_pide_triangular(self):
        identificador = self.triangulado()
        self.p("confianza", "--hallazgo", identificador, "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        self.assertEqual(self.subir(identificador, 2), [("manual", "la confianza está bajada a mano a baja")])
        registro = self.registro()
        self.assertEqual(producto.falta_confianza(registro, registro.hallazgos[identificador]),
                         "%s (ya triangulado, en confianza baja: la confianza está bajada a mano a baja)" % identificador)

    def test_en_el_peldano_6_triangular_no_alcanza(self):
        identificador = self.hallazgo("monetizacion", self.fuente("monetizacion", 2, "medido", 6), "--critico",
                                      "--sin-contra", "Se buscó")[0]
        registro = self.registro()
        hallazgo = registro.hallazgos[identificador]
        detalle = producto.detalle_confianza(registro, hallazgo)
        self.assertEqual(detalle, ["falta 1 fuente independiente y vigente (tiene 2 de 3)",
                                   "el peldaño 6, hipótesis general, llega como mucho a confianza baja: media pide "
                                   "fuentes de peldaño 1 a 5"])
        self.assertIn("    ↑ además de triangular, para subir a confianza media: el peldaño 6, hipótesis general",
                      self.p("triangulacion"))

    def test_tantas_en_contra_como_a_favor_pide_mas_a_favor(self):
        en_contra = ",".join(self.fuente("demanda", 3, "medido"))
        identificador = self.hallazgo("demanda", self.fuente("demanda", 3, "medido"), "--en-contra", en_contra)[0]
        faltan = self.subir(identificador)
        self.assertIn(("contra", "más fuentes independientes a favor que en contra (tiene 3 a favor y 3 en contra)"),
                      faltan)

    def test_sin_triangular_y_sin_otro_motivo_solo_pide_triangular(self):
        identificador = self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--critico", "--sin-contra",
                                      "Se buscó")[0]
        registro = self.registro()
        hallazgo = registro.hallazgos[identificador]
        self.assertEqual(producto.detalle_confianza(registro, hallazgo, 2),
                         ["faltan 2 fuentes independientes y vigentes (tiene 1 de 3)"])
        self.assertEqual(producto.falta_confianza(registro, hallazgo),
                         "%s (faltan 2 fuentes independientes y vigentes, tiene 1 de 3)" % identificador)
        self.assertEqual(producto.subir_o_triangular(registro, [hallazgo]), "Triangular")
        self.assertIn("✖ %s" % identificador, self.p("triangulacion"))
        self.assertNotIn("↑", self.p("triangulacion"))

    def test_en_alta_no_le_falta_nada(self):
        identificador = self.triangulado()
        registro = self.registro()
        self.assertEqual(registro.evaluar(registro.hallazgos[identificador])["confianza"], "alta")
        self.assertEqual(registro.para_subir(registro.hallazgos[identificador]), [])

    def test_la_confianza_global_no_pide_3_fuentes_a_lo_ya_triangulado(self):
        identificador = self.triangulado()
        self.assertEqual(producto.confirmar_criterio(self.registro(), "demanda", [identificador]),
                         "Subir a confianza media los hallazgos de demanda que siguen en baja (%s): "
                         "`triangulacion` dice qué le falta a cada uno" % identificador)
        suelto = self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--sin-contra", "Se buscó")[0]
        self.assertEqual(producto.confirmar_criterio(self.registro(), "demanda", [suelto]),
                         "Confirmar con 3 fuentes recientes los hallazgos de demanda")

    def test_una_hipotesis_con_un_hallazgo_ya_triangulado_no_pide_triangularlo(self):
        identificador = self.triangulado()
        self.p("confianza", "--hallazgo", identificador, "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        impide = {"id": "D-1", "sin_hipotesis": False, "refutadas": [],
                  "fortalecer": [{"id": "HIP-01", "hallazgos": [identificador], "veredicto": "débil", "nivel": 1}]}
        texto, ids, solo = producto.que_fortalecer(self.registro(), impide)
        self.assertEqual(texto, "fortalecer las hipótesis de D-1: HIP-01, llevando a confianza media %s (de la 1c: ya "
                                "triangulado, en confianza baja: la confianza está bajada a mano a baja)" % identificador)
        self.assertEqual((ids, solo), ([identificador], True))


class PuertaConDemandaTrianguladaTest(autonomo.Base):
    def test_que_cambiaria_dice_lo_que_falta_y_no_triangular(self):
        # la demanda baja por un hallazgo ya triangulado, bajado a mano: antes pedía «Triangular H-DEM-1»
        self.hasta_1g()
        self.p("confianza", "--hallazgo", "H-DEM-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        media = self.comparacion_media()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("Subir a confianza media H-DEM-1 (ya triangulado, en confianza baja: la confianza está bajada a "
                      "mano a baja) en la 1c con una señal medida", salida)
        self.assertNotIn("Triangular H-DEM-1", salida)


# --- #70 (b) · Los resúmenes cortados llevan «…» ----------------------------------------------------------------------

class ResumenCortadoTest(base.Base):
    def test_triangulacion_marca_el_corte(self):
        self.sesion0()
        largo = "Un hallazgo inventado y largo " * 8
        self.p("hallazgo", "--linea", "competencia", "--texto", largo, "--fuentes",
               ",".join(self.fuente("competencia", 1)), "--critico", "--sin-contra", "Se buscó")
        self.p("hallazgo", "--linea", "competencia", "--texto", "Corto e inventado", "--fuentes",
               ",".join(self.fuente("competencia", 1)), "--critico", "--sin-contra", "Se buscó")
        lineas = self.p("triangulacion").split("\n")
        cortado = next(linea for linea in lineas if linea.startswith("    Un hallazgo inventado"))
        self.assertTrue(cortado.endswith("…"), cortado)
        self.assertEqual(len(cortado.strip()), 160)
        self.assertIn("    Corto e inventado", lineas)


if __name__ == "__main__":
    unittest.main()
