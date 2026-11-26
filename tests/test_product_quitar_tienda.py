"""Tests de la mejora #83 de hb-product.

(a) El aviso de `cerrar --sesion 1g` nombra, por tienda, solo a los rivales que cada diferenciador en paridad iguala o
no supera, no a los que supera.
(b) Si el rival de una tienda deja fuera a diferenciadores que sin ella serían viables, «Qué cambiaría» de la puerta 1
ofrece quitar esa tienda del objetivo (un cambio de criterio, nunca automático) también cuando el veredicto es 🔴: por
el puntaje, con cuánto quedaría («quedaría en N/25 si …», con el tope de diferenciación de #75), o porque ningún
diferenciador supera a los rivales. El rival de una tienda que sale del objetivo deja de contar.
(c) Las anclas 4 y 5 de demanda piden la señal en los mercados que pesan en el objetivo: si todas las fuentes que
cuentan de los hallazgos clave de demanda triangulados son de un solo mercado de un objetivo con varios, el script no
acepta más de 3 y el puntaje de hoy lo topa.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import re
import unittest

import test_product as base
import test_product_tiendas as tiendas

HOY = base.HOY


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(tiendas.Base):
    def dos_rivales(self):
        """Sesiones 0 a 1e con Google Play y App Store en el objetivo: C-2 (PlantaPlus) solo está en App Store y C-4
        (RiegoLibre) es el rival de Google Play. D-1 (precio, en la ficha, copia media) supera a C-2 y solo iguala a
        C-4. Devuelve (el dolor triangulado, la prueba de elección en confianza alta)."""
        voz = self.hasta_1g()
        self.dos_tiendas()
        self.plataformas("PlantaPlus", "S-COM-2", "ios")
        self.plataformas("RiegoLibre", "S-COM-1", "android", "--rival", "--tienda", "google-play")
        alta = self.comparacion_alta()
        self.p("frente", "--id", "D-1", "--rival", "C-2", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, alta),
               "--texto", "Sin suscripción")
        self.p("frente", "--id", "D-1", "--rival", "C-4", "--resultado", "iguala", "--hallazgos", voz, "--texto",
               "RiegoLibre también es de pago único")
        self.p("vacio", "--linea", "competencia", "--tienda", "app-store", "--motivo", "presupuesto", "--texto",
               "La tienda llegó al objetivo después")
        return voz, alta

    def con_principal_que_supera(self, voz, alta):
        """D-2 (usabilidad, en el uso, fácil de copiar) supera a los dos rivales y pasa a principal."""
        self.p("diferenciador", "--vector", "usabilidad", "--texto", "Turnos en dos toques", "--hallazgos", voz,
               "--se-ve", "uso", "--copiable", "alta", "--motivo", "Rediseñar el flujo es fácil", "--semanas", 2)
        for rival_ in ("C-2", "C-4"):
            self.p("frente", "--id", "D-2", "--rival", rival_, "--resultado", "supera", "--hallazgos",
                   "%s,%s" % (voz, alta), "--texto", "Lo supera en el flujo")
        self.p("principal", "--id", "D-2")

    def hasta_puerta(self, valores):
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", valores)
        self.cerrar("1f", "01-sintesis.md")
        return self.p("puerta", "--n", 1)


# --- (a) · El aviso de cerrar 1g nombra solo a los rivales que iguala o no supera ------------------------------------

class AvisoParidadTest(Base):
    def test_nombra_solo_al_rival_que_iguala_con_su_tienda(self):
        self.dos_rivales()
        salida = self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("⚠ D-1 solo iguala al rival C-4 (RiegoLibre) en Google Play: es paridad (básico en Kano), no "
                      "cuenta como viable ni puede ser el principal.", salida)
        aviso = next(linea for linea in salida.splitlines() if "es paridad" in linea)
        self.assertNotIn("C-2", aviso)  # a C-2 lo supera

    def test_con_un_rival_que_le_gana_lo_dice_aparte(self):
        voz, alta = self.dos_rivales()
        self.p("diferenciador", "--vector", "usabilidad", "--texto", "Turnos en dos toques", "--hallazgos", voz,
               "--se-ve", "uso", "--copiable", "media", "--motivo", "Rediseñar el flujo les cuesta", "--semanas", 2)
        self.p("frente", "--id", "D-2", "--rival", "C-2", "--resultado", "iguala", "--hallazgos", voz, "--texto", "x y z")
        self.p("frente", "--id", "D-2", "--rival", "C-4", "--resultado", "no", "--hallazgos", voz, "--texto", "x y z")
        salida = self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("⚠ D-1 solo iguala al rival C-4 (RiegoLibre) en Google Play; D-2 solo iguala al rival C-2 "
                      "(PlantaPlus) en App Store y no supera al rival C-4 (RiegoLibre) en Google Play: es paridad",
                      salida)

    def test_con_una_sola_tienda_no_nombra_tiendas(self):
        voz = self.hasta_1g()
        self.p("frente", "--id", "D-1", "--resultado", "iguala", "--hallazgos", voz, "--texto", "También es gratis")
        salida = self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("⚠ D-1 solo iguala al rival C-2 (PlantaPlus): es paridad", salida)


# --- (b) · Quitar la tienda que baja la diferenciación, también con el veredicto en 🔴 ---------------------------------

class QuitarTiendaTest(Base):
    def test_rojo_por_puntaje_dice_cuanto_quedaria_sin_esa_tienda(self):
        voz, alta = self.dos_rivales()
        self.con_principal_que_supera(voz, alta)
        salida = self.hasta_puerta("4,3,3,3,3")  # 16/25: D-2 es el único viable y es fácil de copiar
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Evidencia nueva que suba el puntaje a 17/25 o más; o quitar Google Play del objetivo (`objetivo "
                      "--tiendas app-store --motivo \"<por qué>\"`): es un cambio de criterio con su motivo, que la "
                      "puerta muestra, y nunca se hace solo. Quedaría en 17/25 si se quita Google Play y la "
                      "diferenciación se vuelve a puntuar en la 1f con su máximo, 4 (hoy 3): sin el rival C-4 "
                      "(RiegoLibre), el de Google Play, D-1 también sería viable.", salida)
        # el cambio de criterio no se hace solo: el objetivo sigue igual
        self.assertEqual(self.datos()["objetivo"]["tiendas"], ["google-play", "app-store"])

    def test_no_lo_ofrece_si_sin_esa_tienda_tampoco_alcanza_el_minimo(self):
        voz, alta = self.dos_rivales()
        self.con_principal_que_supera(voz, alta)
        salida = self.hasta_puerta("3,3,3,3,3")  # 15/25: sin Google Play quedaría en 16/25
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertNotIn("Quedaría en", salida)
        self.assertNotIn("quitar Google Play", salida)

    def test_quitarla_de_verdad_deja_de_contar_su_rival(self):
        voz, alta = self.dos_rivales()
        self.con_principal_que_supera(voz, alta)
        self.hasta_puerta("4,3,3,3,3")
        registro = self.registro()
        self.assertEqual([c["id"] for c in registro.rivales()], ["C-2", "C-4"])
        self.assertEqual(registro.estado(registro.diferenciadores["D-1"]), "paridad")
        self.p("objetivo", "--tiendas", "app-store", "--motivo", "Lanzamos primero en iPhone")
        registro = self.registro()
        self.assertEqual([c["id"] for c in registro.rivales()], ["C-2"])  # C-4 era solo de Google Play
        self.assertEqual(registro.estado(registro.diferenciadores["D-1"]), "viable")
        self.assertIn("Total: 17/25", self.p("puntaje", "--valores", "4,3,3,3,4"))

    def test_ningun_diferenciador_supera_y_sin_esa_tienda_uno_seria_viable(self):
        self.dos_rivales()
        salida = self.hasta_puerta("4,4,4,4,1")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Ningún diferenciador supera al rival C-2 (PlantaPlus) ni al rival C-4 (RiegoLibre)", salida)
        self.assertIn("o quitar Google Play del objetivo (`objetivo --tiendas app-store --motivo \"<por qué>\"`): es "
                      "un cambio de criterio con su motivo, que la puerta muestra, y nunca se hace solo (sin el rival "
                      "C-4 (RiegoLibre), el de Google Play, D-1 sería viable)", salida)

    def test_con_una_sola_tienda_no_cambia(self):
        voz = self.hasta_1g()
        salida = self.puerta1("--resultado", "iguala", "--hallazgos", voz, "--texto", "También es gratis",
                              valores="4,4,4,4,1")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertNotIn("quitar", salida)


# --- (c) · La señal de demanda de un solo mercado llega a 3 como máximo -----------------------------------------------

class DemandaUnMercadoTest(Base):
    def demanda(self):
        return self.datos("01-investigacion/demanda.json")["hallazgos"][0]

    def test_con_un_solo_mercado_en_el_objetivo_no_cambia(self):
        voz = self.hasta_1g()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", "%s,%s" % (voz, self.comparacion_alta()),
                              "--texto", "Sin suscripción", valores="5,4,4,4,4")
        self.assertIn("Total: 21/25", self.p("puntaje", "--valores", "5,4,4,4,4"))
        self.assertNotIn("es solo de", salida)

    def test_la_senal_de_un_solo_mercado_de_varios_no_pasa_de_3(self):
        voz = self.hasta_1g()
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, self.comparacion_alta()),
               "--texto", "Sin suscripción")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "4,4,4,4,4")  # con MX solo en el objetivo, 4 vale
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        demanda = self.demanda()["id"]
        error = self.falla("puntaje", "--valores", "4,4,4,4,4")
        self.assertIn("Demanda = 4 no corresponde: la señal actual de demanda (%s) es solo de MX: las anclas 4 y 5 la "
                      "piden en los mercados que pesan en el objetivo, y los demás siguen sin una señal triangulada, "
                      "así que el máximo es 3" % demanda, re.sub(r"\s+", " ", error))
        self.assertIn("`fuente --linea demanda --url <la misma> --mercados …`", re.sub(r"\s+", " ", error))
        # el registrado antes queda como «se registró» y el de hoy decide la puerta 1
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("se registró 20/25", salida)
        self.assertIn("demanda 4, pero con las reglas de hoy el máximo es 3 (la señal actual de demanda (%s) es solo "
                      "de MX" % demanda, salida)
        self.assertIn("Total: 19/25", self.p("puntaje", "--valores", "3,4,4,4,4"))

    def test_una_fuente_de_otro_mercado_o_sin_etiqueta_lo_levanta(self):
        self.hasta_1g()
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        hallazgo = self.demanda()
        self.assertIn("es solo de MX", self.falla("puntaje", "--valores", "4,4,4,4,1"))
        # la misma fuente medida también es de AR: la señal cubre dos mercados
        url = next(f["url"] for f in self.datos("01-investigacion/demanda.json")["fuentes"]
                   if f["id"] == hallazgo["fuentes"][-1])
        self.p("fuente", "--linea", "demanda", "--url", url, "--mercados", "AR")
        self.assertIn("Total: 17/25", self.p("puntaje", "--valores", "4,4,4,4,1"))

    def test_una_fuente_sin_etiqueta_de_mercado_no_lo_tapa(self):
        self.hasta_1g()
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        fuentes = self.fuente("demanda", 2, cobertura=False) + self.fuente("demanda", 1, "medido", cobertura=False)
        self.hallazgo("demanda", fuentes, "--critico", "--sin-contra", "Se buscó y no apareció")
        self.assertIn("Total: 17/25", self.p("puntaje", "--valores", "4,4,4,4,1"))


if __name__ == "__main__":
    unittest.main()
