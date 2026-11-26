"""Tests de la mejora #79 de hb-product: textos de la puerta y de las reaperturas que reflejan el estado.

(a) Después de la sesión 4, las puertas 2 y 3 y el reporte leen del PRD dónde quedó la métrica de cada riesgo a medir
(«HIP-03 en M-02») y piden definir solo los que siguen sin ella. (b) Los textos no se cortan a mitad de palabra.
(c) Toda reapertura recomendada dice lo que tiene que conseguir, también la de una propuesta. (d) La reapertura de la
sesión 3 dice lo que pasa según su motivo. (e) El texto de una propuesta que termina en punto no sale con dos.
(f) Una fuente por caso en los escenarios. (g) Un hallazgo mayormente en contra, en validacion.md y evidencia.md.
Ningún veredicto cambia: solo los textos.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_fortalecer as fortalecer
import test_product_negocio as negocio
import test_product_paralelo as paralelo
from helpers import write

HOY = base.HOY
producto = base.producto
tabla = negocio.tabla

# el PRD de test_product.py, con la más riesgosa (HIP-02) en el MVP, como pide la puerta 3 tras Viable para probar
PRD = base.PRD.replace("| 3 | HIP-01 |", "| 3 | HIP-02 |")
MIDE_PAGO = PRD.replace("| M-02 | Tarea | Turnos completados sin ayuda |",
                        "| M-02 | Tarea | Turnos completados sin ayuda. Mide HIP-03 |")
MIDE_TODO = MIDE_PAGO.replace(
    "| M-02 | Tarea | Turnos completados sin ayuda. Mide HIP-03 | 80 % |",
    "| M-02 | Tarea | Turnos completados sin ayuda. Mide HIP-03 | 80 % |\n"
    "| M-03 | Adopción | Ingresos netos al mes del pago único. Mide la monetización | El caso base a los 90 días |")
POR_CASO = {"pesimista": "S-MON-2", "base": "S-MON-3", "optimista": ["S-MON-3", "S-MON-4"]}


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(negocio.Base):
    def puerta3(self, prd):
        """Pago débil de una 1d ya reabierta (#77): la puerta 2 Viable para probar con HIP-03 y la monetización como
        riesgos a medir, la decisión de seguir y el PRD; devuelve la puerta 3."""
        self.monetizacion_gastada(tabla())
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", prd)
        self.cerrar("4")
        return self.p("puerta", "--n", 3)


# --- (a) · Dónde quedó cada riesgo en el PRD ------------------------------------------------------------------------

class RiesgosEnElPrdTest(Base):
    def test_la_puerta_3_dice_donde_quedo_cada_uno(self):
        salida = self.puerta3(MIDE_TODO)
        self.assertIn("🟡  PUERTA 3 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)  # no cambia
        self.assertIn("quedan como riesgos a medir después del lanzamiento (HIP-03 en M-02 y la monetización en M-03, "
                      "con su métrica y su umbral en el PRD).", salida)
        self.assertNotIn("defínelos", salida)
        self.p("reporte")
        reporte = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("HIP-03 en M-02 y la monetización en M-03", reporte)

    def test_pide_definir_solo_los_que_siguen_sin_metrica(self):
        salida = self.puerta3(MIDE_PAGO)
        self.assertIn("(HIP-03 en M-02, con su métrica y su umbral en el PRD; la monetización, sin métrica ni umbral en "
                      "el PRD: defínelos en las métricas HEART, con «Mide la monetización» en la columna Métrica "
                      "(sesión 4))", salida)
        self.assertIn("🟡  PUERTA 3 · VIABLE PARA PROBAR", salida)

    def test_la_funcionalidad_que_cita_la_hipotesis_no_basta(self):
        # la columna Hipótesis dice qué pone a prueba la funcionalidad, no que su métrica mida esa hipótesis
        prd = PRD.replace("| H-COM-1 | — | M-02 | 800 | 1 | 2 | — |", "| H-COM-1 | — | M-02 | 800 | 1 | 2 | HIP-03 |")
        salida = self.puerta3(prd)
        self.assertNotIn("HIP-03 en M-02", salida)
        self.assertIn("(HIP-03 y la monetización, sin métrica ni umbral en el PRD", salida)
        self.assertIn("🟡  PUERTA 3 · VIABLE PARA PROBAR", salida)

    def test_sin_ninguna_queda_el_texto_de_siempre_salvo_el_prd(self):
        salida = self.puerta3(PRD)
        self.assertIn("(HIP-03 y la monetización, sin métrica ni umbral en el PRD: defínelos en las métricas HEART, con "
                      "«Mide HIP-03» y «Mide la monetización» en la columna Métrica (sesión 4))", salida)

    def test_antes_de_la_sesion_4_el_texto_de_hoy(self):
        salida = self.monetizacion_gastada(tabla())
        self.assertIn("(HIP-03 y la monetización, sin métrica ni umbral: defínelos en el PRD, en la sesión 4)", salida)
        texto = producto.texto_sesion(self.carpeta, self.datos(), "4")  # todavía sin decidir: no hay riesgos
        self.assertNotIn("«Mide", texto)
        self.p("decidir", "--puerta", 2, "--seguir")
        self.assertIn("cada métrica nombra el riesgo que mide en su propia columna Métrica («Mide HIP-03» y «Mide la "
                      "monetización»; la columna Hipótesis de una funcionalidad no basta)",
                      producto.texto_sesion(self.carpeta, self.datos(), "4"))

    def test_como_lee_el_vinculo(self):
        datos = {"detalle_metricas": [
            {"id": "M-01", "metrica": "Instalaciones al mes. Mide HIP-03 (la más riesgosa) e HIP-06 (canal)",
             "completa": True},
            {"id": "M-02", "metrica": "Ingresos netos. Mide el riesgo de monetización que dejó la puerta 2",
             "completa": True},
            {"id": "M-03", "metrica": "Mide HIP-07", "completa": False},  # sin meta: no cuenta
            {"id": "M-04", "metrica": "Monetización: ingresos por anuncios", "completa": True}],  # no dice «mide»
            "funciones": [{"mvp": True, "hipotesis": ["HIP-04"], "metricas": ["M-04"]}]}  # no cuenta
        self.assertEqual(producto.metricas_de_riesgos(None, None, datos), {
            "HIP-03": ["M-01"], "HIP-06": ["M-01"], "monetización": ["M-02"]})
        self.assertIsNone(producto.metricas_de_riesgos(None, None, {"detalle_metricas": [], "funciones": []}))


# --- (b) · Sin cortes a mitad de palabra ----------------------------------------------------------------------------

class TextoCortoTest(Base):
    def test_corta_en_un_limite_de_palabra(self):
        texto = "A los 60 días del lanzamiento: instalaciones orgánicas al mes en las dos tiendas, sin campañas pagadas"
        corto = producto.texto_corto(texto, 90)
        self.assertEqual(corto, "A los 60 días del lanzamiento: instalaciones orgánicas al mes en las dos tiendas, "
                                "sin…")
        self.assertLessEqual(len(corto), 90)
        self.assertEqual(producto.texto_corto("corto", 90), "corto")
        self.assertEqual(producto.texto_corto("palabras sueltas, con coma", 18), "palabras sueltas…")
        self.assertEqual(producto.texto_corto("x" * 20, 10), "x" * 9 + "…")  # una sola palabra larga se corta igual

    def test_la_metrica_de_un_riesgo_no_sale_cortada(self):
        metrica = "Conversión al pago único sobre las instalaciones nuevas del mes, en las dos tiendas y sin campañas " \
                  "pagadas, a los 60 días"
        salida = self.monetizacion_gastada(tabla(metrica=metrica))
        corto = producto.texto_corto(metrica, 90)
        self.assertIn("(HIP-03, con «%s»; la monetización, sin métrica ni umbral" % corto, salida)
        self.assertTrue(metrica.startswith(corto[:-1] + " "), corto)


# --- (c) y (d) · Lo que tiene que conseguir cada reapertura y qué pasa al cerrar -------------------------------------

class ReaperturaPropuestaTest(paralelo.Base):
    def test_la_reapertura_de_la_2_por_una_propuesta_dice_que_conseguir(self):
        self.puerta_2_y_3()
        self.p("decidir", "--puerta", 2, "--ajustar", "2", "3")
        texto = producto.texto_sesion(self.carpeta, self.datos(), "2")
        self.assertIn("Lo que tiene que conseguir, según la puerta: «Aplicar la propuesta PR-1 al ajustar la sesión 2»; "
                      "la propuesta PR-1 dice: «Revisar el precio inventado del pago único».", texto)
        self.assertNotIn("Ajustar la sesión 3", texto)
        self.assertEqual(self.datos("decisiones.json")[-1]["motivos"], {"2": ["propuesta"], "3": ["sobrevive"]})


class ReaperturaValidacionTest(fortalecer.Base):
    def test_por_el_principal_queda_el_texto_de_64(self):
        self.puerta2(fortalecer.tabla())
        self.p("decidir", "--puerta", 2, "--ajustar", "3")
        texto = producto.texto_sesion(self.carpeta, self.datos(), "3")
        self.assertIn("Es la única: si al cerrar el principal (y cada otro diferenciador viable) sigue sin sobrevivir "
                      "al abogado del diablo, la puerta no recomienda reabrirla otra vez.", texto)
        self.assertNotIn("lo que sostiene el negocio", texto)


class ReaperturaNegocioTest(Base):
    def test_por_lo_que_sostiene_el_negocio_dice_lo_que_pasa(self):
        self.primera_pasada(tabla())
        self.p("decidir", "--puerta", 2, "--ajustar", "3")
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual(decision["motivos"], {"3": ["negocio"]})
        texto = producto.texto_sesion(self.carpeta, self.datos(), "3")
        self.assertIn("Es la reapertura de la validación. Lo que tiene que conseguir, según la puerta: «Ajustar la "
                      "sesión 3, una sola vez, para fortalecer HIP-03", texto)
        self.assertIn("Es la única: si al cerrar lo que sostiene el negocio sigue débil o en confianza baja, la puerta "
                      "no vuelve a pedir este ajuste: sin evidencia en contra, queda como riesgo a medir después del "
                      "lanzamiento (Viable para probar), y con una hipótesis refutada, No viable.", texto)
        self.assertNotIn("sigue sin sobrevivir", texto)

    def test_una_decision_anterior_se_lee_por_lo_que_tenia_que_conseguir(self):
        negocio_ = {"decision": "ajustar", "sesion": "3",
                    "resolver": ["Ajustar la sesión 3, una sola vez, para fortalecer HIP-04, con evidencia a favor"]}
        principal = {"decision": "ajustar", "sesion": "3", "resolver": [
            "Ajustar la sesión 3, una sola vez, para fortalecer las hipótesis de D-1: HIP-02, triangulando H-VOZ-1"]}
        ambos = {"decision": "ajustar", "sesion": "3", "resolver": principal["resolver"] + [
            "En esa misma reapertura de la sesión 3, fortalecer también HIP-07, con evidencia a favor nueva"]}
        self.assertEqual(producto.motivos_reapertura(negocio_, "3"), ["negocio"])
        self.assertEqual(producto.motivos_reapertura(principal, "3"), ["sobrevive"])
        self.assertEqual(producto.motivos_reapertura(ambos, "3"), ["sobrevive", "negocio"])
        self.assertEqual(producto.motivos_reapertura({"motivos": {"3": ["riesgosa"]}}, "3"), ["riesgosa"])
        texto = producto.texto_unica_validacion(["sobrevive", "negocio"])
        self.assertIn("sigue sin sobrevivir al abogado del diablo, la puerta no recomienda reabrirla otra vez; si al "
                      "cerrar lo que sostiene el negocio", texto)
        self.assertIn("Cuenta como la reapertura de la validación", producto.texto_unica_validacion(["propuesta"]))


# --- (e) · Sin doble punto ------------------------------------------------------------------------------------------

class PropuestaConPuntoTest(paralelo.Base):
    def test_la_propuesta_que_termina_en_punto_no_sale_con_dos(self):
        self.puerta2(fortalecer.tabla(veredicto="sostenida"))
        self.p("propuesta", "--texto", "Revisar el precio inventado del pago único.", "--ajustar", "2")
        salida = self.p("puerta", "--n", 2)
        self.assertIn("Hay una propuesta pendiente (PR-1): Revisar el precio inventado del pago único.\n", salida)
        self.assertNotIn("..", salida.replace("…", ""))
        self.assertEqual(producto.sin_punto("Con él."), "Con él")
        self.assertEqual(producto.sin_punto("Queda abierto..."), "Queda abierto...")
        self.assertEqual(producto.sin_punto("Sin punto"), "Sin punto")


# --- (f) · Una fuente por caso en los escenarios --------------------------------------------------------------------

class FuentePorCasoTest(Base):
    def escenarios(self, dau=2000, fuente=None):  # la puerta 2: con una fuente por caso en todos los supuestos
        return super().escenarios(dau, fuente or {"pesimista": "S-MON-2", "base": "S-MON-3", "optimista": "S-MON-3"})

    def entrada(self, fuente):
        return negocio.VariasFuentesTest.entrada(self, fuente)

    def correr(self, fuente):
        write(self.carpeta / "mal.json", json.dumps(self.entrada(fuente)))
        return self.p("escenarios", "--entrada", "mal.json")

    def test_acepta_una_fuente_por_caso_y_lo_dice(self):
        self.hasta_puerta1()
        self.fuente("monetizacion", 2, "medido")  # S-MON-4 y S-MON-5
        salida = self.correr(POR_CASO)
        self.assertIn("✔ Pago único · Pro", salida)
        self.assertNotIn("Estimación", salida)
        self.assertIn("· Fuentes por caso: MX.instalaciones_mes: pesimista S-MON-2 · base S-MON-3 · optimista "
                      "S-MON-3 y S-MON-4.", salida)
        citas = self.datos()["escenarios"]["fuentes"]
        self.assertIn({"supuesto": "MX.instalaciones_mes", "pesimista": ["S-MON-2"], "base": ["S-MON-3"],
                       "optimista": ["S-MON-3", "S-MON-4"]}, citas)
        html = producto.seccion_escenarios(self.datos())
        self.assertIn("Fuentes de cada caso (3 supuestos)", html)
        self.assertIn("<b>MX.dau</b> · S-MON-1 (los tres casos)", html)
        self.assertIn("<b>MX.instalaciones_mes</b> · pesimista S-MON-2 · base S-MON-3 · optimista S-MON-3 y S-MON-4",
                      html)

    def test_sigue_aceptando_la_fuente_unica_y_la_lista(self):
        self.hasta_puerta1()
        for fuente in ("S-MON-2", ["S-MON-2", "S-MON-3"], "S-MON-2, S-MON-3"):
            salida = self.correr(fuente)
            self.assertIn("✔ Pago único · Pro", salida)
            self.assertNotIn("Fuentes por caso", salida)
        self.assertEqual(producto.fuentes_por_caso({"fuente": "S-1, S-2"}),
                         {c: ["S-1", "S-2"] for c in ("pesimista", "base", "optimista")})
        self.assertEqual(producto.fuentes_supuesto({"fuente": POR_CASO}), ["S-MON-2", "S-MON-3", "S-MON-4"])

    def test_un_caso_sin_fuente_es_estimacion_y_un_caso_que_no_existe_falla(self):
        self.hasta_puerta1()
        salida = self.correr({"pesimista": "S-MON-2", "base": "S-MON-3"})
        self.assertIn("⚠ Estimación: supuestos sin fuente: MX.instalaciones_mes (sin fuente en el caso optimista)",
                      salida)
        self.assertIn("✖ Pago único · Pro", salida)
        write(self.carpeta / "mal.json", json.dumps(self.entrada({"pesimista": "S-MON-2", "medio": "S-MON-3"})))
        self.assertIn("`medio` no es un caso", self.falla("escenarios", "--entrada", "mal.json"))
        write(self.carpeta / "mal.json", json.dumps(self.entrada({"pesimista": "S-MON-99", "base": "S-MON-3",
                                                                  "optimista": "S-MON-3"})))
        self.assertIn("cita la fuente S-MON-99, que no existe", self.falla("escenarios", "--entrada", "mal.json"))

    def test_por_analogia_si_un_caso_solo_tiene_fuentes_lejanas(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        analoga = self.fuente("estrategia", 1, "terceros", 3)[0]
        self.assertIn("Por analogía", self.correr({"pesimista": analoga, "base": "S-MON-2", "optimista": "S-MON-2"}))
        self.assertNotIn("Por analogía", self.correr({"pesimista": [analoga, "S-MON-3"], "base": "S-MON-2",
                                                      "optimista": "S-MON-2"}))

    def test_la_puerta_2_cita_la_fuente_de_cada_caso(self):
        salida = self.primera_pasada(tabla(veredicto="sostenida", umbral="Descarta con menos de 1 000 al mes"))
        self.assertIn("🟢  PUERTA 2 · VIABLE", salida)  # no cambia el veredicto
        self.assertIn("queda por debajo del caso pesimista (5 000, según S-MON-2)", salida)
        self.assertIn("· Fuentes por caso de los escenarios: MX.dau: pesimista S-MON-2 · base S-MON-3 · optimista S-MON-3;",
                      salida)


# --- (g) y documentación ---------------------------------------------------------------------------------------------

class DocumentacionTest(unittest.TestCase):
    def test_la_skill_lo_dice(self):
        referencias = base.SKILL / "references"
        validacion = (referencias / "validacion.md").read_text(encoding="utf-8")
        self.assertIn("**Un hallazgo mayormente en contra**", validacion)
        self.assertIn("la confianza calculada no lee esa columna", validacion)
        evidencia = (referencias / "evidencia.md").read_text(encoding="utf-8")
        self.assertIn("no por hacia dónde apunta", evidencia)
        prd = (referencias / "prd.md").read_text(encoding="utf-8")
        self.assertIn("«Mide la monetización»", prd)
        self.assertIn("la columna Hipótesis de una funcionalidad dice qué pone a prueba esa funcionalidad", prd)
        plantilla = (base.SKILL / "assets" / "plantillas" / "04-prd.md").read_text(encoding="utf-8")
        self.assertIn("«Mide HIP-…» o «Mide la monetización»", plantilla)
        estrategia = (referencias / "estrategia.md").read_text(encoding="utf-8")
        self.assertIn('"fuente": {"pesimista": "S-EST-8"', estrategia)
        escenarios = json.loads((base.SKILL / "assets" / "plantillas" / "escenarios.json").read_text(encoding="utf-8"))
        self.assertIn('{"pesimista": "S-…"', escenarios["_leeme"])
        puertas = (referencias / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("**Después de la sesión 4**", puertas)


if __name__ == "__main__":
    unittest.main()
