"""Tests de las mejoras #77 y #78 de hb-product.

#77: el 🟢 de las puertas 2 y 3 pide confianza media o alta en lo que sostiene el negocio, igual que el 🟢 de la puerta 1:
cada hipótesis crítica débil o en confianza baja lo impide, esté o no enlazada a un diferenciador (la única exenta es la
más riesgosa, que ya se mide después del lanzamiento), y también la confianza baja de la monetización que la puerta 1
dejó como riesgo a validar (#76). En la primera pasada, ajustar la sesión 3 una vez (#64); si otra búsqueda no la
subiría, Viable para probar con esa hipótesis como riesgo a medir; refutada, No viable, como siempre.

#78: varias fuentes por supuesto de los escenarios, la comisión de la tienda con otra tasa, la lectura fallida y el
aviso del umbral de descarte contra los escenarios.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_reapertura as reapertura
from helpers import write

HOY = base.HOY
producto = base.producto

# HIP-02 es la más riesgosa (el criterio de descarte, sobre D-1); HIP-03, la de pago, según la prueba
TABLA = """# Validación

| ID | Hipótesis | Hallazgos | En contra | Diferenciador | Veredicto | Más riesgosa | Métrica y umbral |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HIP-01 | Los vecinos quieren repartir el riego | H-DEM-1 | Se buscaron apps de riego cerradas: nada | — | sostenida | — | — |
| HIP-02 | La gente elige la app por D-1 frente a PlantaPlus | H-VOZ-1, H-DIF-1 | Una reseña inventada en contra | D-1 | débil | sí | {umbral} |
| HIP-03 | Bastantes vecinos pagan el pago único | {pago} | Una reseña inventada en contra | {diferenciador} | {veredicto} | — | {metrica} |
"""
UMBRAL = "A los 60 días: instalaciones orgánicas al mes. Confirma con 8 000 o más; descarta con menos de 6 000 al mes"


def tabla(veredicto="débil", pago="H-MON-1", diferenciador="—", metrica="—", umbral=UMBRAL):
    return TABLA.format(veredicto=veredicto, pago=pago, diferenciador=diferenciador, metrica=metrica, umbral=umbral)


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(reapertura.Base):
    def sesiones_2_y_3(self, texto):
        """Con la puerta 1 decidida como seguir: los escenarios (sesión 2) y la validación (sesión 3), y la puerta 2."""
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", texto)
        self.cerrar("3")
        return self.p("puerta", "--n", 2)

    def primera_pasada(self, texto):
        """Una idea Viable para probar en la puerta 1 (sin nada en baja), hasta la puerta 2 con esa validación."""
        self.para_probar()
        self.p("decidir", "--puerta", 1, "--seguir")
        return self.sesiones_2_y_3(texto)

    def monetizacion_gastada(self, texto):
        """La puerta 1 Viable para probar con la confianza de monetización en baja y la 1d ya reabierta (#76): pasó
        como aviso. Hasta la puerta 2 con esa validación."""
        self.debil_para_probar()
        self.reabrir("1d")
        self.p("decidir", "--puerta", 1, "--seguir")
        return self.sesiones_2_y_3(texto)


# --- #77 · Lo que sostiene el negocio -----------------------------------------------------------------------------

class PrimeraPasadaTest(Base):
    def test_el_pago_debil_sin_enlazar_pide_ajustar_3_una_vez(self):
        salida = self.primera_pasada(tabla())
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 3", salida)
        self.assertNotIn("🟢", salida)
        self.assertIn("Lo que sostiene el negocio no llega a confianza media o alta (HIP-03 débil (confianza alta; cita "
                      "monetización)): Viable lo pide en cada hipótesis crítica, esté o no enlazada a un diferenciador, y "
                      "falta evidencia, no hay evidencia en contra; la sesión 3 todavía no se reabrió para "
                      "fortalecerla.", salida)
        self.assertIn("Ajustar la sesión 3, una sola vez, para fortalecer HIP-03, con evidencia a favor nueva que la "
                      "sostenga frente a lo que tiene en contra (sus hallazgos ya están en confianza alta).", salida)
        self.assertIn("Con eso, el veredicto pasaría a Viable.", salida)
        # el criterio de «sobrevive» no cambia: la más riesgosa débil sigue exenta
        self.assertIn("✔ El diferenciador principal sobrevive al abogado del diablo", salida)
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["decision"], automatico["sesion"], automatico["detener"]), ("ajustar", "3", False))
        self.p("decidir", "--puerta", 2, "--automatico")
        decision = self.datos("decisiones.json")[-1]
        self.assertTrue(decision["resolver"][0].startswith("Ajustar la sesión 3, una sola vez, para fortalecer HIP-03"))

    def test_la_columna_diferenciador_no_decide_si_cuenta(self):
        salida = self.primera_pasada(tabla(diferenciador="D-2"))  # enlazada a otro diferenciador, que no es el principal
        self.assertIn("AJUSTAR 3", salida)
        self.assertIn("HIP-03 débil (confianza alta; cita monetización)", salida)

    def test_sostenida_da_viable(self):
        salida = self.primera_pasada(tabla(veredicto="sostenida"))
        self.assertIn("🟢  PUERTA 2 · VIABLE  →  la skill recomienda: SEGUIR", salida)
        self.assertNotIn("Lo que sostiene el negocio", salida)

    def test_despues_de_reabrir_la_3_queda_como_riesgo_a_medir(self):
        self.primera_pasada(tabla(metrica="Conversión al pago único de 2 % o más a los 60 días"))
        self.p("decidir", "--puerta", 2, "--ajustar", "3")
        self.p("cerrar", "--sesion", "3", "--busquedas", 4, "--lecturas", 3)
        salida = self.p("puerta", "--n", 2)
        self.assertIn("🟡  PUERTA 2 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("Otra búsqueda no lo subiría, y la sesión 3 ya se reabrió para fortalecerlas (4 de 8 búsquedas y "
                      "3 de 5 lecturas en la reapertura 1), así que la puerta no da Viable ni vuelve a pedir un ajuste: "
                      "queda como riesgo a medir después del lanzamiento (HIP-03, con «Conversión al pago único de 2 % "
                      "o más a los 60 días»)", salida)
        self.assertNotIn("AJUSTAR", salida.split("Puerta 2 ·")[0])


class LineaGastadaTest(Base):
    def test_el_pago_debil_de_una_linea_gastada_no_pide_otra_busqueda(self):
        salida = self.monetizacion_gastada(tabla())
        self.assertIn("🟡  PUERTA 2 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertNotIn("Ajustar la sesión 3", salida)
        self.assertIn("HIP-03 débil (confianza baja; cita monetización): H-MON-1 es de la 1d, que ya se reabrió (3 de 8 "
                      "búsquedas y 2 de 5 lecturas en la reapertura 1)", salida)
        self.assertIn("quedan como riesgos a medir después del lanzamiento (HIP-03 y la monetización, sin métrica ni "
                      "umbral: defínelos en el PRD, en la sesión 4)", salida)
        self.assertIn("⚠ No lo pases por alto: lo que sostiene el negocio no llega a confianza media o alta", salida)
        self.assertIn("Evidencia que sostenga HIP-03 y la monetización con confianza media o alta sin depender de otra "
                      "búsqueda sin salida", salida)
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["decision"], automatico["sesion"], automatico["detener"]), ("seguir", None, False))
        salida = self.p("decidir", "--puerta", 2, "--automatico")
        self.assertIn("· Viable para probar: HIP-03 y la monetización quedan como riesgos a medir después del "
                      "lanzamiento.", salida)
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual([r["id"] for r in decision["riesgos"]], ["HIP-03", "monetización"])
        self.assertIn("La puerta 2 fue Viable para probar: HIP-03 y la monetización quedan como riesgos a medir después "
                      "del lanzamiento", producto.texto_sesion(self.carpeta, self.datos(), "4"))

    def test_el_aviso_de_monetizacion_de_la_puerta_1_impide_el_verde(self):
        # ninguna hipótesis cita la monetización y todas, menos la más riesgosa (exenta), están sostenidas
        salida = self.monetizacion_gastada(tabla(veredicto="sostenida", pago="H-DEM-1"))
        self.assertNotIn("🟢", salida)
        self.assertIn("🟡  PUERTA 2 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("la confianza de monetización (baja, que la puerta 1 dejó como riesgo a validar en esta puerta): "
                      "la 1d ya se reabrió (3 de 8 búsquedas y 2 de 5 lecturas en la reapertura 1)", salida)
        self.assertIn("o un hallazgo clave de monetización refutado (pasaría a No viable)", salida)

    def test_la_puerta_3_no_hereda_el_falso_verde(self):
        self.monetizacion_gastada(tabla())
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", base.PRD.replace("| 3 | HIP-01 |", "| 3 | HIP-02 |"))
        self.cerrar("4")
        salida = self.p("puerta", "--n", 3)
        self.assertIn("🟡  PUERTA 3 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("Cumple los 7 criterios de la puerta 3", salida)
        self.assertIn("quedan como riesgos a medir después del lanzamiento (HIP-03 y la monetización", salida)


class ExentaYRefutadaTest(Base):
    def test_la_mas_riesgosa_debil_queda_exenta_solo_si_se_mide_despues(self):
        # con criterio de descarte (puerta 1 Viable para probar), HIP-02 débil no impide el verde
        self.assertIn("🟢  PUERTA 2 · VIABLE", self.primera_pasada(tabla(veredicto="sostenida")))
        fila = {"riesgosa": True, "veredicto": "débil"}
        self.assertTrue(producto.exenta(fila, {"texto": "x"}))
        self.assertFalse(producto.exenta(fila, None))
        self.assertFalse(producto.exenta(dict(fila, veredicto="refutada"), {"texto": "x"}))

    def test_sin_criterio_de_descarte_la_mas_riesgosa_debil_cuenta(self):
        self.hasta_puerta1()  # la puerta 1 da Viable: no hay nada que se mida después del lanzamiento
        self.p("decidir", "--puerta", 1, "--seguir")
        salida = self.sesiones_2_y_3(base.HIPOTESIS.replace("| sostenida | sí |", "| débil | sí |"))
        self.assertIn("AJUSTAR 3", salida)
        self.assertIn("HIP-01 débil (confianza alta)", salida)

    def test_una_refutada_sigue_siendo_no_viable(self):
        salida = self.primera_pasada(tabla(veredicto="refutada"))
        self.assertIn("🔴  PUERTA 2 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("Hay hipótesis críticas refutadas (HIP-03)", salida)
        self.assertNotIn("Lo que sostiene el negocio no llega", salida.split("Puerta 2 ·")[0])


# --- #78 · Los escenarios y la validación ---------------------------------------------------------------------------

class VariasFuentesTest(Base):
    def entrada(self, fuente):
        return {"mercados": [{"mercado": "MX", "dau": {"pesimista": 100, "base": 200, "optimista": 300,
                                                       "fuente": "S-MON-1"},
                              "instalaciones_mes": {"pesimista": 500, "base": 1000, "optimista": 2000,
                                                    "fuente": fuente},
                              "compras": [{"nombre": "Pro", "tipo": "pago-unico", "precio": 4, "comision": 0.25,
                                           "conversion": {"pesimista": 0.01, "base": 0.02, "optimista": 0.03,
                                                          "fuente": "S-MON-1"}}]}]}

    def correr(self, fuente):
        write(self.carpeta / "mal.json", json.dumps(self.entrada(fuente)))
        return self.p("escenarios", "--entrada", "mal.json")

    def test_un_supuesto_acepta_varias_fuentes_y_la_forma_de_siempre(self):
        self.hasta_puerta1()
        for fuente in ("S-MON-2", ["S-MON-2", "S-MON-3"], "S-MON-2, S-MON-3"):
            salida = self.correr(fuente)
            self.assertIn("✔ Pago único · Pro", salida)  # viable con evidencia: todos sus supuestos citan su fuente
            self.assertNotIn("Estimación", salida)
        write(self.carpeta / "mal.json", json.dumps(self.entrada(["S-MON-2", "S-MON-99"])))
        self.assertIn("cita la fuente S-MON-99, que no existe", self.falla("escenarios", "--entrada", "mal.json"))
        self.assertEqual(producto.fuentes_supuesto({"fuente": ["S-1", " S-2", "S-1"]}), ["S-1", "S-2"])
        self.assertEqual(producto.fuentes_supuesto({"fuente": "S-1, S-2"}), ["S-1", "S-2"])
        self.assertEqual(producto.fuentes_supuesto({"pesimista": 1}), [])

    def test_por_analogia_solo_si_ninguna_fuente_es_directa(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        analoga = self.fuente("estrategia", 1, "terceros", 3)[0]
        self.assertIn("Por analogía", self.correr(analoga))
        self.assertNotIn("Por analogía", self.correr([analoga, "S-MON-2"]))

    def test_la_comision_admite_otra_tasa(self):
        self.hasta_puerta1()
        self.assertIn("✔ Pago único · Pro", self.correr("S-MON-2"))  # 0.25: ni 0.15 ni 0.30
        plantilla = (base.SKILL / "assets" / "plantillas" / "escenarios.json").read_text(encoding="utf-8")
        self.assertIn("fuente oficial", plantilla)
        self.assertNotIn("(0.15 o 0.30)", plantilla)


class UmbralContraEscenariosTest(Base):
    def puerta2(self, umbral):
        return self.primera_pasada(tabla(veredicto="sostenida", umbral=umbral))  # instalaciones: 5 000 y 10 000

    def test_avisa_si_el_umbral_queda_bajo_el_pesimista(self):
        salida = self.puerta2("Descarta con menos de 1 000 al mes")
        self.assertIn("🟢  PUERTA 2 · VIABLE", salida)  # no cambia el veredicto; desde #79 f cita la fuente del caso
        self.assertIn("⚠ El umbral de descarte de HIP-02 contradice los escenarios: menos de 1 000 instalaciones al mes "
                      "queda por debajo del caso pesimista (5 000, según S-MON-3): un lanzamiento peor que el peor caso "
                      "no se "
                      "descartaría. No cambia el veredicto: revisa el umbral (sesión 3) o los escenarios (sesión 2).",
                      salida)

    def test_avisa_si_el_umbral_queda_sobre_el_base(self):
        salida = self.puerta2("Confirma con 15.000 al mes; descarta con menos de 12.000 instalaciones orgánicas al mes")
        # la fuente del caso, desde #79 f
        self.assertIn("menos de 12 000 instalaciones al mes queda por encima del caso base (10 000, según S-MON-3): el "
                      "resultado que "
                      "esperan los escenarios ya se descartaría", salida)

    def test_sin_aviso_entre_el_pesimista_y_el_base_o_si_no_se_puede_leer(self):
        self.assertNotIn("contradice los escenarios", self.puerta2(UMBRAL))
        self.assertNotIn("contradice los escenarios", self.p("puerta", "--n", 2).replace(UMBRAL, ""))
        write(self.carpeta / "03-validacion.md", tabla(veredicto="sostenida", umbral="Pocas instalaciones a los 60 "
                                                       "días"))
        self.assertNotIn("contradice los escenarios", self.p("puerta", "--n", 2))

    def test_lee_la_retencion_y_las_cifras_con_separador(self):
        self.assertEqual(producto.umbrales_descarte(
            "Confirma con 520 o más al mes y D30 de 4,8 % o más; descarta con menos de 260 al mes o D30 por debajo de "
            "2,4 %"), {"instalaciones_mes": 260.0, "d30": 0.024})
        self.assertEqual(producto.umbrales_descarte("Descarta: menos de 1.500 instalaciones al mes o retención a 7 "
                                                    "días menor a 10 %"), {"instalaciones_mes": 1500.0, "d7": 0.1})
        self.assertEqual(producto.umbrales_descarte("Confirma con 500 al mes"), {})
        supuestos = producto.supuestos_escenarios([
            {"instalaciones_mes": {"pesimista": 400, "base": 800}, "retencion": {"d30": {"pesimista": 0.03,
                                                                                       "base": 0.05}}},
            {"instalaciones_mes": 600, "retencion": {"d30": {"pesimista": 0.02, "base": 0.04}}}])
        self.assertEqual(supuestos["instalaciones_mes"], {"pesimista": 1000.0, "base": 1400.0})
        self.assertEqual(supuestos["retencion"]["d30"], {"pesimista": 0.02, "base": 0.05})


class DocumentacionTest(unittest.TestCase):
    def test_la_skill_lo_dice(self):
        referencias = base.SKILL / "references"
        puertas = (referencias / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("Lo que sostiene el negocio (P2 y P3)", puertas)
        self.assertIn("esté o no enlazada a un diferenciador", puertas)
        investigacion = (referencias / "investigacion.md").read_text(encoding="utf-8")
        self.assertIn("Una lectura fallida no cuenta como lectura", investigacion)
        estrategia = (referencias / "estrategia.md").read_text(encoding="utf-8")
        self.assertIn('"fuente": ["S-MON-3", "S-EST-2"]', estrategia)
        self.assertIn("fuente oficial", estrategia)
        validacion = (referencias / "validacion.md").read_text(encoding="utf-8")
        self.assertIn("descarta con menos de", validacion)


if __name__ == "__main__":
    unittest.main()
