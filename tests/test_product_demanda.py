"""Tests de las mejoras #53 a #55 de hb-product: los extractos de búsqueda que no cuentan como lectura y las fuentes que
se suman a un hallazgo ya registrado (#53), los textos al día con Viable para probar (#54) y la demanda en confianza
baja que no descarta en la primera pasada de la 1c (#55).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import unittest
from unittest import mock

import test_product as base
import test_product_autonomo as autonomo
import test_product_orquestado as orquestado
from helpers import ROOT

HOY = base.HOY
producto = base.producto
SKILL = ROOT / "skills" / "hb-product"


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(autonomo.Base):
    def registro(self):
        return producto.Registro(self.carpeta, self.datos()["criterios"])

    def demanda_debil(self, en_contra=False):
        """Las sesiones 0 a 1g de una idea viable, más un hallazgo clave de demanda con una sola fuente (confianza
        baja). Con en_contra, también una fuente que lo contradice: tantas en contra como a favor lo refutan."""
        self.investigacion()
        favor = self.fuente("demanda", 1, "medido")
        extra = ("--en-contra", self.fuente("demanda", 1, "medido")[0]) if en_contra else (
            "--sin-contra", "Se buscó y no apareció")
        identificador, _ = self.hallazgo("demanda", favor, "--critico", *extra)
        self.p("puntaje", "--valores", "3,4,4,4,3")
        self.cerrar("1f", "01-sintesis.md")
        return identificador


# --- #55 · La demanda en confianza baja ------------------------------------------------------------------------------

class DemandaBajaTest(Base):
    def test_en_la_primera_pasada_sin_evidencia_en_contra_pide_ajustar_1c_con_lo_que_falta(self):
        debil = self.demanda_debil()
        salida = self.p("puerta", "--n", 1)
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("La demanda actual tiene confianza baja en la primera pasada de la 1c", salida)
        self.assertIn("sin datos no es lo mismo que sin demanda", salida)
        self.assertIn("Triangular %s (faltan 2 fuentes independientes y vigentes, tiene 1 de 3) en la 1c con una señal "
                      "medida y reciente de demanda" % debil, salida)
        self.assertIn("✖ Demanda con confianza media o alta · es baja", salida)
        self.assertNotIn("★ Recomendado · Descartar", salida)
        self.assertEqual(self.json()["pasos"][0]["automatico"]["sesion"], "1c")

    def test_con_evidencia_en_contra_es_no_viable(self):
        debil = self.demanda_debil(en_contra=True)
        salida = self.p("puerta", "--n", 1)
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("La demanda tiene evidencia en contra: %s tiene tantas fuentes en contra como a favor" % debil,
                      salida)
        self.assertEqual(producto.refutados(self.registro(), [debil]), [debil])

    def test_menos_evidencia_en_contra_que_a_favor_no_la_refuta(self):
        self.investigacion()
        favor = self.fuente("demanda", 2, "medido")
        identificador, _ = self.hallazgo("demanda", favor, "--critico", "--en-contra",
                                         self.fuente("demanda", 1, "medido")[0])
        self.assertEqual(producto.refutados(self.registro(), [identificador]), [])

    def test_con_la_1c_ya_reabierta_no_la_recomienda_otra_vez(self):
        self.demanda_debil()
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        texto = self.p("siguiente")
        self.assertIn("Es la reapertura de la demanda: si al cerrar la demanda sigue en confianza baja", texto)
        self.assertIn("la puerta 1 no recomienda reabrirla otra vez", texto)
        self.assertIsNone(producto.reapertura_gastada(self.datos(), "1c"))  # abierta: todavía no la gastó
        self.p("cerrar", "--sesion", "1c", "--busquedas", 3, "--lecturas", 2)
        salida = self.cerrar("1f")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("La demanda sigue con confianza baja después de reabrir la 1c (3 de 8 búsquedas y 2 de 5 "
                      "lecturas en la reapertura 1): ajustarla otra vez con las mismas herramientas no traería "
                      "evidencia nueva", salida)
        self.assertIn("Evidencia de demanda que no dependa de más búsquedas en la 1c", salida)
        self.assertNotIn("AJUSTAR 1c", salida)

    def test_con_vacios_de_herramienta_en_la_1c_ajusta_y_el_modo_autonomo_se_detiene(self):
        self.demanda_debil()
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        self.p("vacio", "--linea", "demanda", "--mercado", "AR", "--motivo", "herramienta", "--texto",
               "La tendencia de búsqueda es un gráfico que no se lee como texto")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("AJUSTAR 1c", salida)
        self.assertIn("La sesión 1c (demanda) tiene un vacío por límite de las herramientas", salida)
        self.assertIn("antes de ajustarla, dale al agente un navegador", salida)
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["decision"], automatico["sesion"], automatico["detener"]), ("ajustar", "1c", True))

    def test_el_modo_autonomo_cuenta_el_ajuste_de_la_1c_para_el_tope(self):
        self.demanda_debil()
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["sesion"], automatico["ajustes_previos"], automatico["detener"]),
                         ("1c", 0, False))
        self.assertIn("ajustar la sesión 1c", self.p("decidir", "--puerta", 1, "--automatico"))
        self.assertEqual(producto.ajustes_previos(self.datos("decisiones.json"), 1, "1c"), 1)
        self.cerrar("1c")
        self.cerrar("1f")
        self.assertEqual(self.json()["pasos"][0]["automatico"]["decision"], "descartar")  # 1c ya reabierta

    def test_con_la_demanda_ajustada_pasaria_a_viable_para_probar(self):
        self.hasta_1g()
        self.p("confianza", "--hallazgo", "H-DEM-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        media = self.comparacion_media()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción")
        self.assertIn("AJUSTAR 1c", salida)
        self.assertIn("Con eso, el veredicto pasaría a Viable para probar.", salida)

    def test_otro_ajuste_que_pide_buscar_en_una_1c_reabierta_no_se_recomienda(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--ajustar", "1c", "--motivo", "Quiero más evidencia de demanda")
        self.cerrar("1c")
        self.cerrar("1f")
        datos = self.datos()
        registro = self.registro()
        ajuste = ("La confianza global es baja", "Confirmar", "1c", True)
        self.assertEqual(producto.reapertura_gastada(datos, "1c"), "reabierta una vez")
        with mock.patch.object(producto, "propuestas_de", return_value=[]):
            resultado = producto.veredicto(1, self.carpeta, datos, registro)
        self.assertEqual(resultado["nivel"], "viable")  # la base: nada que ajustar
        # un ajuste que pida buscar en la 1c reabierta, sin otro posible, lleva a No viable con esa razón
        original = producto.motivos_criterio

        def con_ajuste(numero, criterio, *resto):
            return (False,) + ajuste[:2] + (ajuste[2], [], True) if criterio["clave"] == "demanda" else original(
                numero, criterio, *resto)
        evaluados = [{"clave": "demanda", "cumple": False, "texto": "Demanda", "detalle": "es baja"}]
        with mock.patch.object(producto, "motivos_criterio", side_effect=con_ajuste):
            resultado = producto.veredicto(1, self.carpeta, datos, registro, evaluados)
        self.assertEqual(resultado["nivel"], "no")
        self.assertIn("La sesión 1c ya se reabrió (reabierta una vez): ajustarla otra vez no traería evidencia nueva",
                      resultado["razones"])


class ProblemaNuevaTest(orquestado.Base):
    def test_el_problema_con_evidencia_en_contra_es_no_viable(self):
        self.nueva_con_lineas(problema=False)
        favor = self.fuente("demanda", 1, "usuario", 5)
        contra = self.fuente("demanda", 1, "usuario", 5)
        identificador, _ = self.hallazgo("demanda", favor, "--en-contra", contra[0])
        self.p("puntaje", "--valores", "3,3,4,4,1", "--mitigacion", "Sin anuncios")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("El problema tiene evidencia en contra en los peldaños 4 y 5: %s" % identificador, salida)

    def test_el_problema_con_un_hallazgo_sin_triangular_pide_triangularlo(self):
        self.nueva_con_lineas(problema=False)
        identificador, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 1, "usuario", 4),
                                         "--sin-contra", "nada")
        self.p("puntaje", "--valores", "3,3,4,4,1", "--mitigacion", "Sin anuncios")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("AJUSTAR 1b", salida)  # la sesión del hallazgo más cercano
        self.assertIn("Triangular %s (faltan 2 fuentes independientes y vigentes, tiene 1 de 3) en la 1b con fuentes "
                      "de peldaño 4 o 5" % identificador, salida)


# --- #53 · Extractos de búsqueda y fuentes sumadas a un hallazgo -----------------------------------------------------

class ExtractoTest(Base):
    def extracto(self, url="https://buscador.example/resultado-1", *extra):
        return self.p("fuente", "--linea", "demanda", "--url", url, "--publicada", "2026-06", "--tipo", "medido",
                      "--peldano", 1, "--resumen", "Cifra de descargas vista en el extracto", "--mercados", "MX",
                      *extra)

    def test_no_cuenta_como_lectura_y_queda_marcado(self):
        self.sesion0()
        self.fuente("demanda", 1, "medido")
        salida = self.extracto("https://buscador.example/resultado-1", "--extracto")
        self.assertIn("Extracto de un resultado de búsqueda: no cuenta como lectura", salida)
        self.assertIn("Fuentes de la línea demanda: 1 (presupuesto de lecturas: 10) · más 1 extracto de búsqueda, que "
                      "no cuenta como lectura", salida)
        guardada = self.datos("01-investigacion/demanda.json")["fuentes"][-1]
        self.assertTrue(guardada["extracto"])
        # abrir la página después: la misma URL sin --extracto pasa a leída
        salida = self.extracto("https://buscador.example/resultado-1")
        self.assertIn("se abrió la página: ahora cuenta como lectura", salida)
        self.assertIn("Fuentes de la línea demanda: 2 (presupuesto de lecturas: 10)\n", salida)
        guardada = self.datos("01-investigacion/demanda.json")["fuentes"][-1]
        self.assertNotIn("extracto", guardada)
        self.assertIn("leida", guardada)

    def test_cuenta_para_la_confianza_como_cualquier_fuente(self):
        self.sesion0()
        ids = self.fuente("demanda", 2, "medido")
        salida = self.extracto("https://buscador.example/resultado-9", "--extracto")
        ids.append(salida.split("✔ ")[1].split(" ")[0])
        identificador, _ = self.hallazgo("demanda", ids, "--critico", "--sin-contra", "nada")
        registro = self.registro()
        con_extracto = registro.evaluar(registro.hallazgos[identificador])
        self.extracto("https://buscador.example/resultado-9")  # la misma fuente, ya leída
        registro = self.registro()
        leida = registro.evaluar(registro.hallazgos[identificador])
        self.assertEqual((con_extracto["nivel"], con_extracto["triangulado"]), (leida["nivel"], leida["triangulado"]))
        self.assertTrue(con_extracto["triangulado"])

    def test_triangulacion_y_reporte_lo_muestran(self):
        self.investigacion()
        salida = self.extracto("https://buscador.example/resultado-3", "--extracto")
        fuente = salida.split("✔ ")[1].split(" ")[0]
        otras = self.fuente("demanda", 2, "medido")
        identificador, _ = self.hallazgo("demanda", otras + [fuente], "--critico", "--sin-contra", "nada")
        salida = self.p("triangulacion")
        self.assertIn("%s: extracto de búsqueda (no se abrió la página)" % fuente, salida)
        self.assertIn("1 fuente de extracto de búsqueda", salida)
        self.p("reporte")
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("extracto de búsqueda: no se abrió la página", html)

    def test_no_vale_con_un_archivo_ni_con_una_fuente_oficial(self):
        self.sesion0()
        error = self.falla("fuente", "--linea", "politicas", "--url", "https://tienda.example/politica",
                           "--publicada", "2026-06", "--tipo", "oficial", "--peldano", 1, "--resumen", "x",
                           "--extracto")
        self.assertIn("se lee en su página", error)
        ruta = self.tmp / "resenas.csv"
        ruta.write_text("fecha,estrellas,texto\n2026-06-01,2,Muy lenta\n", encoding="utf-8")
        error = self.falla("fuente", "--linea", "voz-del-usuario", "--archivo", ruta, "--autor", "App · Play",
                           "--publicada", "auto", "--tipo", "usuario", "--peldano", 1, "--resumen", "x", "--extracto")
        self.assertIn("--extracto es lo visto en un resultado de búsqueda", error)

    def test_las_lecturas_estimadas_de_una_linea_no_cuentan_los_extractos(self):
        self.sesion0()
        for indice in range(9):
            self.extracto("https://buscador.example/r-%d" % indice, "--extracto")
        self.assertIsNone(producto.presupuesto_usado(self.datos(), self.registro(), "1c"))
        for indice in range(9):
            self.extracto("https://buscador.example/r-%d" % indice)  # abiertas: ahora sí son lecturas
        self.assertIn("9 de 10 lecturas", producto.presupuesto_usado(self.datos(), self.registro(), "1c"))


class SumarFuentesTest(Base):
    def setUp(self):
        super().setUp()
        self.sesion0()
        self.uno = self.fuente("demanda", 1, "medido")[0]
        self.id, _ = self.hallazgo("demanda", [self.uno], "--critico", "--sin-contra", "nada")

    def guardado(self):
        return next(h for h in self.datos("01-investigacion/demanda.json")["hallazgos"] if h["id"] == self.id)

    def test_suma_fuentes_sin_cambiar_el_id_y_recalcula_la_confianza(self):
        antes = self.guardado()
        nuevas = self.fuente("demanda", 2, "medido")
        salida = self.p("hallazgo", "--id", self.id, "--fuentes", ",".join(nuevas))
        self.assertIn("✔ %s suma %s · mismo ID · confianza alta · triangulado (antes: baja · sin triangular)" % (
            self.id, ", ".join(nuevas)), salida)
        despues = self.guardado()
        self.assertEqual(despues["fuentes"], [self.uno] + nuevas)
        for clave in ("id", "texto", "critico", "fecha", "sin_contra", "competidores"):
            self.assertEqual(antes[clave], despues[clave], clave)
        self.assertEqual(despues["enlaces"][-1]["fuentes"], nuevas)
        self.assertEqual(len(self.datos("01-investigacion/demanda.json")["hallazgos"]), 1)
        self.assertIn("ya tenía %s: nada que agregar" % nuevas[0], self.p("hallazgo", "--id", self.id, "--fuentes",
                                                                          nuevas[0]))

    def test_pide_la_sesion_duena_abierta(self):
        self.completar("01-investigacion/demanda.md")
        self.p("cerrar", "--sesion", "1c")
        nueva = self.fuente("demanda", 1, "medido")[0]
        error = self.falla("hallazgo", "--id", self.id, "--fuentes", nueva)
        self.assertIn("la sesión 1c (Demanda), dueña del hallazgo, ya cerró", error)
        self.assertIn("propuesta --texto", error)
        self.assertEqual(self.guardado()["fuentes"], [self.uno])

    def test_valida_las_fuentes(self):
        self.assertIn("No existe esta fuente: S-DEM-9", self.falla("hallazgo", "--id", self.id, "--fuentes",
                                                                   "S-DEM-9"))
        contra = self.fuente("demanda", 1, "medido")[0]
        otro, _ = self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--en-contra", contra)
        self.assertIn("a favor y en contra a la vez", self.falla("hallazgo", "--id", otro, "--fuentes", contra))
        self.assertIn("--texto no va", self.falla("hallazgo", "--id", self.id, "--fuentes", contra, "--texto", "x"))

    def test_la_ayuda_y_las_referencias_lo_explican(self):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit):
            producto.main(["hallazgo", "--help"])
        self.assertIn("--fuentes S-…, le suma fuentes", " ".join(salida.getvalue().split()))
        self.assertIn("--id H-… --fuentes S-…", (SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("Extractos de búsqueda", (SKILL / "references" / "investigacion.md").read_text(encoding="utf-8"))
        self.assertIn("`--extracto`", (SKILL / "references" / "evidencia.md").read_text(encoding="utf-8"))


# --- #54 · Textos al día con Viable para probar ----------------------------------------------------------------------

class TextosTest(Base):
    def test_frente_sin_prueba_de_eleccion_dice_si_se_puede_probar(self):
        self.hasta_1g()
        media = self.comparacion_media()
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", media, "--texto", "Sin "
                        "suscripción")
        self.assertNotIn("como mucho", salida)
        self.assertIn("con el dolor triangulado se puede probar. Si es el principal, la puerta 1 da Viable para "
                      "probar", salida)

    def test_frente_con_el_dolor_sin_triangular_queda_en_reservas(self):
        self.hasta_1g()
        suelto = self.sin_triangular()
        self.p("diferenciador", "--vector", "precio", "--texto", "Un solo pago", "--hallazgos", suelto, "--se-ve",
               "ficha", "--copiable", "media", "--motivo", "Cambia su modelo", "--semanas", 1)
        salida = self.p("frente", "--id", "D-2", "--resultado", "supera", "--hallazgos", self.comparacion_media(),
                        "--texto", "Paga uno")
        self.assertIn("el dolor no está triangulado", salida)
        self.assertIn("la puerta 1 queda en Viable con reservas", salida)

    def test_ningun_texto_dice_como_mucho_viable_con_reservas(self):
        texto = (SKILL / "scripts" / "producto.py").read_text(encoding="utf-8")
        self.assertNotIn("como mucho, Viable con reservas", texto)
        self.assertNotIn("la demanda queda en confianza baja u otro", (SKILL / "SKILL.md").read_text(
            encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
