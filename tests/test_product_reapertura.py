"""Tests de la mejora #76 de hb-product: ninguna línea de investigación ya reabierta y cerrada (de la 1a a la 1e, como
la 1c de #55, la 1g de #30 y la 3 de #64) se recomienda otra vez para buscar más; la confianza global baja de una línea
así pasa a un aviso y el veredicto sale de los criterios, salvo con evidencia en contra. Y el aviso de presupuesto
excedido de la puerta, solo si la última pasada se excedió.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest
from unittest import mock

import test_product as base
import test_product_demanda as demanda

HOY = base.HOY
producto = base.producto


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(demanda.Base):
    def debil_para_probar(self, hallazgo="H-MON-1"):
        """La puerta 1 de una idea Viable para probar (D-1 supera al rival con el dolor triangulado, sin prueba de
        elección), con un hallazgo clave de monetización (o de políticas) bajado a confianza baja: la confianza global
        es baja solo por esa línea."""
        self.hasta_1g()
        self.p("confianza", "--hallazgo", hallazgo, "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        media = self.comparacion_media()
        return self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción")

    def reabrir(self, sesion, busquedas=3, lecturas=2, antes_de_cerrar=None):
        """Ajusta la sesión desde la puerta 1, la cierra con ese uso (y la 1f) y devuelve la puerta 1."""
        self.p("decidir", "--puerta", 1, "--ajustar", sesion)
        if antes_de_cerrar:
            antes_de_cerrar()
        self.p("cerrar", "--sesion", sesion, "--busquedas", busquedas, "--lecturas", lecturas)
        self.cerrar("1f")
        return self.p("puerta", "--n", 1)


class LineaReabiertaTest(Base):
    def test_1d_no_reabierta_sigue_pidiendo_ajustar_1d(self):
        salida = self.debil_para_probar()
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1d", salida)
        self.assertIn("La confianza global es baja: monetización se apoya en evidencia", salida)
        self.assertIn("Con eso, el veredicto pasaría a Viable para probar.", salida)
        self.assertEqual(self.json()["pasos"][0]["automatico"]["sesion"], "1d")

    def test_1d_reabierta_y_cerrada_con_confianza_baja_no_se_repite(self):
        self.debil_para_probar()
        self.p("decidir", "--puerta", 1, "--ajustar", "1d")
        self.assertIn("Es la única reapertura de monetización: si al cerrar lo que pidió la puerta sigue sin "
                      "resolverse", self.p("siguiente"))
        self.p("cerrar", "--sesion", "1d", "--busquedas", 3, "--lecturas", 2)
        salida = self.cerrar("1f")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertNotIn("AJUSTAR 1d", salida)
        razon = ("La confianza global es baja por monetización, y la 1d ya se reabrió (3 de 8 búsquedas y 2 de 5 "
                 "lecturas en la reapertura 1): H-MON-1 está triangulado, pero en confianza baja por una bajada a mano "
                 "(Las fuentes se contradicen). Otra pasada con las mismas herramientas no la subiría, así que la "
                 "puerta no vuelve a pedir ese ajuste: queda como riesgo a validar, y la puerta 2 la vuelve a juzgar "
                 "y no da Viable mientras siga en baja")  # feedback #77: la puerta 2 la juzga de verdad
        self.assertIn("  3. %s." % razon, salida)  # la razón del banner
        self.assertIn("⚠ No lo pases por alto: %s. Si la idea sigue, queda como riesgo a validar: la puerta 2 la "
                      "vuelve a juzgar y no da Viable mientras siga en baja." % producto.primera_minuscula(
                          razon.split(": queda como riesgo")[0]), salida)  # y el aviso
        self.assertNotIn("Los criterios que se cumplen se apoyan en evidencia débil", salida)  # no lo repite
        self.assertIn("y la evidencia de monetización en confianza media, con datos que no dependan de más búsquedas "
                      "en la 1d (un navegador en el agente o datos propios) (pasaría a Viable)", salida)
        self.assertIn("o un hallazgo clave de monetización refutado (pasaría a No viable)", salida)
        self.assertIn("Criterio de descarte después del lanzamiento", salida)
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["decision"], automatico["sesion"], automatico["detener"]), ("seguir", None, False))
        self.assertIn("la skill aplicó su recomendación, seguir (veredicto: Viable para probar;",
                      self.p("decidir", "--puerta", 1, "--automatico"))

    def test_1e_no_reabierta_pide_ajustar_y_reabierta_no_se_repite(self):
        salida = self.debil_para_probar("H-POL-1")
        self.assertIn("AJUSTAR 1e", salida)
        self.assertIn("La confianza global es baja: riesgo de políticas se apoya en evidencia", salida)
        self.p("decidir", "--puerta", 1, "--ajustar", "1e")
        self.assertIn("Es la única reapertura de políticas y riesgos", self.p("siguiente"))
        self.p("cerrar", "--sesion", "1e", "--busquedas", 2, "--lecturas", 1)
        salida = self.cerrar("1f")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("La confianza global es baja por riesgo de políticas, y la 1e ya se reabrió (2 de 8 búsquedas y "
                      "1 de 5 lecturas en la reapertura 1)", salida)
        self.assertIn("la puerta 3 vuelve a revisar las políticas con el checklist", salida)
        self.assertNotIn("AJUSTAR 1e", salida)

    def test_con_evidencia_en_contra_sigue_siendo_no_viable(self):
        self.debil_para_probar()

        def refutado():  # un hallazgo clave de monetización con tantas fuentes en contra como a favor
            self.hallazgo("monetizacion", self.fuente("monetizacion", 1, "medido"), "--critico", "--en-contra",
                          self.fuente("monetizacion", 1, "medido")[0])

        salida = self.reabrir("1d", antes_de_cerrar=refutado)
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Monetización tiene evidencia en contra (H-MON-2 tiene tantas fuentes en contra como a favor) y "
                      "la 1d ya se reabrió (3 de 8 búsquedas y 2 de 5 lecturas en la reapertura 1): ajustarla otra "
                      "vez no traería evidencia nueva", salida)
        self.assertNotIn("queda como riesgo a validar", salida)
        self.assertEqual(self.json()["pasos"][0]["automatico"]["decision"], "descartar")

    def test_sin_la_prueba_de_eleccion_pendiente_tampoco_da_viable_con_confianza_baja(self):
        # la idea de hasta_puerta1 tiene prueba de elección (sería Viable); con la confianza baja en una 1d ya
        # reabierta, no es Viable (pide confianza media o alta) ni se ajusta otra vez: se prueba
        self.investigacion()
        self.p("confianza", "--hallazgo", "H-MON-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        self.assertIn("AJUSTAR 1d", self.cerrar("1f", "01-sintesis.md"))
        salida = self.reabrir("1d")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("  1. Cumple los 5 criterios de la puerta 1.", salida)
        self.assertIn("  2. El diferenciador principal (D-1) es viable y supera al rival C-2 (PlantaPlus), con prueba "
                      "de elección.", salida)
        self.assertIn("  3. La confianza global es baja por monetización, y la 1d ya se reabrió", salida)
        self.assertIn("La evidencia de monetización en confianza media, con datos que no dependan de más búsquedas en "
                      "la 1d (un navegador en el agente o datos propios) (pasaría a Viable)", salida)
        self.p("decidir", "--puerta", 1, "--seguir")
        self.assertEqual(self.datos("decisiones.json")[-1]["criterio_descarte"]["diferenciador"], "D-1")

    def test_las_lineas_de_1a_a_1e_reabiertas_y_cerradas_quedan_sin_salida(self):
        self.hasta_puerta1()
        self.assertEqual(producto.reaperturas_sin_salida(self.datos(), self.registro()), {})
        self.p("decidir", "--puerta", 1, "--ajustar", "1a", "1b", "--motivo", "Quiero revisar la competencia")
        self.assertEqual(producto.reaperturas_sin_salida(self.datos(), self.registro()), {})  # abiertas: no cuentan
        self.cerrar("1a")
        self.cerrar("1b")
        self.assertEqual(sorted(producto.reaperturas_sin_salida(self.datos(), self.registro())), ["1a", "1b"])
        # un ajuste que pide buscar en ellas, sin otro posible, lleva a No viable con esa razón (como la 1c)
        original = producto.motivos_criterio

        def con_ajuste(numero, criterio, *resto):
            if criterio["clave"] == "principal":
                return False, "Falta confirmar algo de la voz", "Confirmarlo", "1b", [], True
            return original(numero, criterio, *resto)

        evaluados = [dict(c, cumple=c["clave"] != "principal") for c in producto.evaluar_puerta(
            1, self.carpeta, self.datos(), self.registro())]
        with mock.patch.object(producto, "motivos_criterio", con_ajuste):
            resultado = producto.veredicto(1, self.carpeta, self.datos(), self.registro(), evaluados)
        self.assertEqual(resultado["nivel"], "no")
        self.assertIn("La sesión 1b ya se reabrió (reabierta una vez): ajustarla otra vez no traería evidencia nueva",
                      resultado["razones"])


class PresupuestoExcedidoTest(Base):
    def pasadas(self, primera, reapertura=None):
        datos = {"sesiones": {"1d": {"pasadas": [
            {"reapertura": 0, "busquedas": primera[0], "lecturas": primera[1],
             "presupuesto": {"busquedas": 15, "lecturas": 10}}]}}}
        if reapertura:
            datos["sesiones"]["1d"]["pasadas"].append(
                {"reapertura": 1, "busquedas": reapertura[0], "lecturas": reapertura[1],
                 "presupuesto": {"busquedas": 8, "lecturas": 5}})
        return datos

    def test_el_aviso_de_la_puerta_sale_solo_si_la_ultima_pasada_se_excedio(self):
        datos = self.pasadas((15, 11), (3, 4))
        self.assertEqual(producto.pasadas_excedidas(datos, vigente=True), [])  # la reapertura quedó dentro
        self.assertEqual(producto.pasadas_excedidas(datos), [  # la historia completa (estado)
            ("1d", "primera pasada con 11 de 10 lecturas; reapertura 1 dentro del presupuesto")])
        self.assertEqual(producto.pasadas_excedidas(self.pasadas((15, 11), (9, 4)), vigente=True), [
            ("1d", "primera pasada con 11 de 10 lecturas; reapertura 1 con 9 de 8 búsquedas")])
        self.assertEqual(producto.pasadas_excedidas(self.pasadas((15, 11)), vigente=True), [
            ("1d", "primera pasada con 11 de 10 lecturas")])
        self.assertEqual(producto.pasadas_excedidas(self.pasadas((15, 10), (8, 5)), vigente=True), [])

    def test_en_la_puerta_el_exceso_de_una_pasada_anterior_no_se_repite(self):
        self.debil_para_probar()
        self.assertIn("⚠ Presupuesto excedido: 1d: reapertura 1 con 6 de 5 lecturas",
                      self.reabrir("1d", lecturas=6))
        datos = self.datos()
        pasadas = datos["sesiones"]["1d"]["pasadas"]
        pasadas[-1]["lecturas"] = 4  # la reapertura, dentro del presupuesto; la primera pasada se excedió
        pasadas.insert(0, {"reapertura": 0, "busquedas": 15, "lecturas": 11,
                           "presupuesto": {"busquedas": 15, "lecturas": 10}})
        (self.carpeta / "producto.json").write_text(json.dumps(datos), encoding="utf-8")
        self.assertNotIn("Presupuesto excedido", self.p("puerta", "--n", 1))
        self.assertIn("- Presupuesto excedido: 1d: primera pasada con 11 de 10 lecturas; reapertura 1 dentro del "
                      "presupuesto", self.p("estado"))


if __name__ == "__main__":
    unittest.main()
