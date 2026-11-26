"""Tests de las mejoras #63 y #64 de hb-product: `cerrar --sesion 3` exige una hipótesis del diferenciador principal
(#63), y en las puertas 2 y 3 un principal (o cada otro viable) que no sobrevive al abogado del diablo solo por
hipótesis débiles o sin poner a prueba es 🟡 ajustar la sesión 3 una vez, no 🔴 (#64): falta evidencia, no hay evidencia
en contra. 🔴 con una hipótesis refutada o con la sesión 3 ya reabierta por eso.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_alternativa as alternativa
from helpers import write

HOY = base.HOY
producto = base.producto

# HIP-02, la del principal (D-1), según la prueba: {d1} es su veredicto; {extra}, más filas
TABLA = """# Validación

| ID | Hipótesis | Hallazgos | En contra | Diferenciador | Veredicto | Más riesgosa | Métrica y umbral |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HIP-01 | Los vecinos quieren repartir el riego | H-DEM-1 | Se buscaron apps de riego cerradas: nada | — | sostenida | sí | 30 % vuelve a los 30 días |
| HIP-02 | El pago único atrae a quien no quiere suscripción | {hallazgos} | Una reseña inventada en contra | {d1} | {veredicto} | — | — |
{extra}"""


def tabla(veredicto="débil", d1="D-1", hallazgos="H-VOZ-1", extra=""):
    return TABLA.format(veredicto=veredicto, d1=d1, hallazgos=hallazgos, extra=extra)


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(alternativa.Base):
    def cerrar(self, sesion, archivo=None):
        if sesion == "1g" and not self.datos("01-investigacion/diferenciacion.json").get("diferenciadores", [])[1:]:
            # un segundo diferenciador viable que también supera al rival, como en test_product_alternativa.py
            self.p("diferenciador", "--vector", "anuncios", "--texto", "Registro sin anuncios", "--hallazgos",
                   "H-VOZ-1", "--se-ve", "uso", "--copiable", "media", "--motivo", "El rival vive de sus anuncios",
                   "--semanas", 1)
            self.p("frente", "--id", "D-2", "--resultado", "supera", "--hallazgos", "H-VOZ-1", "--texto",
                   "PlantaPlus muestra anuncios al registrar")
        return super().cerrar(sesion, archivo)

    def puerta2(self, texto):
        self.hasta_puerta2()
        write(self.carpeta / "03-validacion.md", texto)
        return self.p("puerta", "--n", 2)

    def con_hallazgo_debil(self, vacio=False):
        """Hasta la puerta 2 con la sesión 3 abierta un momento para registrar H-VAL-1, con una sola fuente (de MX):
        HIP-02 lo cita y queda en confianza baja. Con vacio, la línea validación no pudo leer MX (herramienta)."""
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--ajustar", "3", "--motivo", "Agregar evidencia inventada a la validación")
        identificador, _ = self.hallazgo("validacion", self.fuente("validacion", 1, "usuario"), "--sin-contra",
                                         "Se buscó y no apareció")
        if vacio:
            self.p("vacio", "--linea", "validacion", "--mercado", "MX", "--motivo", "herramienta", "--texto",
                   "Foro dinámico que no se pudo leer")
        write(self.carpeta / "03-validacion.md", tabla(hallazgos=identificador, extra=(
            "| HIP-03 | El registro sin anuncios gana frente al rival | %s | Una reseña inventada en contra | D-2 | débil "
            "| — | — |\n" % identificador)))
        self.cerrar("3")
        # la reapertura de arriba es solo para registrar el hallazgo: no cuenta como la del ajuste (#64)
        lista = [d for d in self.datos("decisiones.json") if not (d.get("puerta") == 2 and d.get("decision") ==
                                                                 "ajustar")]
        write(self.carpeta / "decisiones.json", json.dumps(lista))
        return identificador


# --- #63 · La hipótesis del principal ---------------------------------------------------------------------------

class HipotesisDelPrincipalTest(Base):
    def test_cerrar_la_sesion_3_exige_una_hipotesis_del_principal(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        write(self.carpeta / "03-validacion.md", tabla(veredicto="sostenida", d1="—"))
        error = self.falla("cerrar", "--sesion", "3")
        self.assertIn("ninguna hipótesis pone a prueba el diferenciador principal (D-1): agrega la suya, con D-1 en la "
                      "columna Diferenciador (siempre va la del principal)", error)
        self.assertIn("✖ ninguna hipótesis pone a prueba el diferenciador principal (D-1)", self.p("validacion"))
        write(self.carpeta / "03-validacion.md", tabla(veredicto="sostenida"))
        self.assertIn("✔ Sesión 3", self.cerrar("3"))

    def test_el_principal_sin_poner_a_prueba_pide_ajustar_3_no_descartar(self):
        salida = self.puerta2(tabla(veredicto="sostenida", d1="—"))
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 3", salida)
        self.assertIn("El principal (D-1) no sobrevive al abogado del diablo y ningún otro viable sobrevive (D-1: "
                      "ninguna hipótesis lo pone a prueba; D-2: ninguna hipótesis lo pone a prueba), pero solo por "
                      "hipótesis débiles o sin poner a prueba (ninguna está refutada)", salida)
        self.assertIn("Ajustar la sesión 3, una sola vez, para poner a prueba D-1 con una hipótesis (con D-1 en la "
                      "columna Diferenciador), buscando evidencia en contra · o poner a prueba D-2", salida)
        self.assertNotIn("DESCARTAR", salida.split("Puerta 2 ·")[0])


# --- #64 · Las hipótesis débiles no descartan en la primera pasada -----------------------------------------------

class FortalecerTest(Base):
    def test_el_principal_debil_pide_ajustar_3_con_lo_que_falta(self):
        salida = self.puerta2(tabla())
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 3", salida)
        self.assertIn("El principal (D-1) no sobrevive al abogado del diablo y ningún otro viable sobrevive (D-1: HIP-02 "
                      "débil (confianza alta); D-2: ninguna hipótesis lo pone a prueba), pero solo por hipótesis débiles "
                      "o sin poner a prueba (ninguna está refutada): falta evidencia, no hay evidencia en contra, y la "
                      "sesión 3 todavía no se reabrió para fortalecerlas.", salida)
        self.assertIn("Ajustar la sesión 3, una sola vez, para fortalecer las hipótesis de D-1: HIP-02, con evidencia a "
                      "favor nueva que la sostenga frente a lo que tiene en contra (sus hallazgos ya están en confianza "
                      "alta) · o poner a prueba D-2 con una hipótesis", salida)
        self.assertIn("Con eso, el veredicto pasaría a Viable.", salida)

    def test_nombra_que_hallazgo_triangular(self):
        identificador = self.con_hallazgo_debil()
        salida = self.p("puerta", "--n", 2)
        self.assertIn("AJUSTAR 3", salida)
        self.assertIn("HIP-02 débil (confianza baja)", salida)
        self.assertIn("fortalecer las hipótesis de D-1: HIP-02, triangulando %s (faltan 2 fuentes independientes y "
                      "vigentes, tiene 1 de 3" % identificador, salida)

    def test_una_alternativa_que_sobrevive_sigue_primero(self):
        salida = self.puerta2(tabla(extra=alternativa.D2_SOSTENIDA))
        self.assertIn("AJUSTAR 1g", salida)  # llevarla a principal no pide búsquedas (#61)
        self.assertIn("Llevar D-2 a principal (1g)", salida)
        self.assertNotIn("Ajustar la sesión 3", salida)

    def test_una_refutada_sigue_siendo_no_viable(self):
        salida = self.puerta2(tabla(veredicto="refutada"))
        self.assertIn("🔴  PUERTA 2 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("Hay hipótesis críticas refutadas (HIP-02)", salida)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        filas = producto.hipotesis(self.carpeta, registro)
        impide = producto.lo_que_impide(filas, registro.principal())
        self.assertEqual((impide["refutadas"], impide["fortalecer"]), (["HIP-02"], []))
        self.assertIsNone(producto.motivo_fortalecer({}, registro, [impide]))

    def test_la_mas_riesgosa_debil_sigue_exenta_con_criterio_de_descarte(self):
        filas = [{"id": "HIP-02", "diferenciador": "D-1", "veredicto": "débil", "nivel": 3, "riesgosa": True,
                  "hallazgos": []}]
        impide = producto.lo_que_impide(filas, {"id": "D-1"}, {"texto": "x"})
        self.assertEqual((impide["fortalecer"], impide["sin_hipotesis"]), ([], False))
        self.assertEqual(len(producto.lo_que_impide(filas, {"id": "D-1"})["fortalecer"]), 1)


class ReaperturaTest(Base):
    def test_la_reapertura_dice_que_conseguir_y_es_la_unica_y_despues_es_no_viable(self):
        self.puerta2(tabla(extra=alternativa.D2_DEBIL))
        salida = self.p("decidir", "--puerta", 2, "--ajustar", "3")
        self.assertIn("ajustar la sesión 3", salida)
        decision = self.datos("decisiones.json")[-1]
        self.assertTrue(decision["resolver"][0].startswith("Ajustar la sesión 3, una sola vez, para fortalecer"))
        texto = producto.texto_sesion(self.carpeta, self.datos(), "3")
        self.assertIn("Reapertura 1: el presupuesto de esta pasada es de 8 búsquedas y 5 lecturas.", texto)
        self.assertIn("Es la reapertura de la validación. Lo que tiene que conseguir, según la puerta: «Ajustar la "
                      "sesión 3, una sola vez, para fortalecer las hipótesis de D-1: HIP-02", texto)
        self.assertIn("Es la única: si al cerrar el principal (y cada otro diferenciador viable) sigue sin sobrevivir "
                      "al abogado del diablo, la puerta no recomienda reabrirla otra vez.", texto)
        self.p("cerrar", "--sesion", "3", "--busquedas", 4, "--lecturas", 3)
        salida = self.p("puerta", "--n", 2)
        self.assertIn("🔴  PUERTA 2 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("también después de reabrir la sesión 3 para fortalecer sus hipótesis (4 de 8 búsquedas y 3 de 5 "
                      "lecturas en la reapertura 1): ajustarla otra vez con las mismas herramientas no traería evidencia "
                      "nueva", salida)
        self.assertIn("Evidencia que sostenga esas hipótesis sin depender de otra pasada de la sesión 3", salida)

    def test_una_reapertura_en_cascada_no_cuenta(self):
        self.puerta2(tabla())
        datos = self.datos()
        datos["sesiones"]["3"].update(reabierta=HOY + "T09:00", reaperturas=1)  # la reabrió un ajuste de la 1g
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.assertIsNone(producto.reapertura_validacion(self.carpeta, self.datos()))
        self.assertIn("AJUSTAR 3", self.p("puerta", "--n", 2))

    def test_la_puerta_3_sin_principal_tampoco_lo_recomienda_otra_vez(self):
        self.puerta2(tabla(extra=alternativa.D2_DEBIL))
        self.p("decidir", "--puerta", 2, "--ajustar", "3")
        self.cerrar("3")
        self.p("decidir", "--puerta", 2, "--seguir", "--motivo", "Quiero ver el PRD antes de descartar la idea")
        write(self.carpeta / "04-prd.md", base.PRD)
        self.cerrar("4")
        ruta = self.carpeta / "01-investigacion" / "diferenciacion.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        for diferenciador in datos["diferenciadores"]:
            diferenciador["principal"] = False
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        salida = self.p("puerta", "--n", 3)
        self.assertIn("🔴  PUERTA 3 · NO VIABLE", salida)
        self.assertIn("también después de reabrir la sesión 3", salida)


class AutonomoTest(Base):
    def test_cuenta_como_ajuste_y_no_se_detiene_sin_vacios(self):
        self.puerta2(tabla())
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["decision"], automatico["sesion"], automatico["detener"]), ("ajustar", "3", False))
        self.p("decidir", "--puerta", 2, "--automatico")
        self.assertEqual(producto.ajustes_previos(producto.decisiones(self.carpeta), 2, "3"), 1)

    def test_se_detiene_si_lo_que_falta_depende_entero_de_un_vacio_de_herramienta(self):
        self.con_hallazgo_debil(vacio=True)
        salida = self.p("puerta", "--n", 2)
        self.assertIn("AJUSTAR 3", salida)
        self.assertIn("antes de ajustarla, dale al agente un navegador o aporta un CSV de reseñas", salida)
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["sesion"], automatico["detener"]), ("3", True))
        self.assertIn("Modo autónomo: aquí se detiene", self.falla("decidir", "--puerta", 2, "--automatico"))


class DocumentacionTest(unittest.TestCase):
    def test_las_referencias_dicen_la_regla(self):
        puertas = (base.SKILL / "references" / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("Las hipótesis débiles no descartan en la primera pasada (P2 y P3)", puertas)
        validacion = (base.SKILL / "references" / "validacion.md").read_text(encoding="utf-8")
        self.assertIn("`cerrar --sesion 3` no cierra sin ella", validacion)
        self.assertIn("ajustar la sesión 3 una sola vez", (base.SKILL / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
