"""Tests de las mejoras #71 y #72 de hb-product.

#71: las razones de la demanda baja y de la confianza global baja no dicen «sin confirmar» de un hallazgo ya
triangulado que sigue en confianza baja por otro motivo: dicen por qué (la lógica de `Registro.para_subir`, #70).
#72: (a) `decidir --ajustar 1a 1c` dice el orden real de las tandas; (b) el 🔴 por la demanda baja nombra el hallazgo
que la deja en baja; (c) `competidor --anuncios si|no`; (d) `fuente` con una URL ya registrada no pide --resumen ni lo
demás para sumar un mercado; (e) `propuesta --hallazgos` sin --ajustar, informativa; (f) `diferenciador --id` corrige
uno registrado; (g) `hallazgo --id --en-contra`; (h) `nuevo` da rutas absolutas y no pide otra vez el presupuesto de
semanas; (i) `cerrar --sesion 0 --busquedas --lecturas` anota el triaje. Ningún veredicto ni umbral cambia.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import unittest

import test_product as base
import test_product_demanda as demanda

HOY = base.HOY
producto = base.producto
SKILL = demanda.SKILL


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(demanda.Base):
    def demanda_triangulada(self):
        """Las sesiones 0 a 1g de una idea viable, más un hallazgo clave de demanda triangulado (3 fuentes medidas)
        pero en confianza baja: es del peldaño 5 y tiene una fuente en contra."""
        self.investigacion()
        identificador, _ = self.hallazgo("demanda", self.fuente("demanda", 3, "medido", 5), "--critico",
                                         "--en-contra", self.fuente("demanda", 1, "medido")[0])
        self.p("puntaje", "--valores", "3,4,4,4,3")
        self.cerrar("1f", "01-sintesis.md")
        return identificador

    def veredicto(self, numero=1):
        datos = self.datos()
        return producto.veredicto(numero, self.carpeta, datos, producto.Registro(self.carpeta, datos["criterios"]))


# --- #71 · Triangulado, pero en confianza baja ------------------------------------------------------------------------

class RazonesConfianzaBajaTest(Base):
    def test_la_razon_de_la_demanda_dice_por_que_sigue_en_baja(self):
        identificador = self.demanda_triangulada()
        registro = self.registro()
        evaluacion = registro.evaluar(registro.hallazgos[identificador])
        self.assertEqual((evaluacion["triangulado"], evaluacion["confianza"]), (True, "baja"))
        salida = self.p("puerta", "--n", 1)
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("La demanda actual tiene confianza baja en la primera pasada de la 1c: %s está triangulado, pero "
                      "en confianza baja por 1 fuente independiente en contra y el peldaño 5 (necesidad de fondo). "
                      "Ninguno está refutado" % identificador, salida)
        self.assertNotIn("ningún hallazgo de demanda está confirmado", salida)
        self.assertIn("La confianza global es baja: demanda se apoya en evidencia en confianza baja: %s está "
                      "triangulado" % identificador, salida)
        self.assertNotIn("evidencia sin confirmar", salida)

    def test_sin_triangular_conserva_el_texto_de_siempre(self):
        self.demanda_debil()
        salida = self.p("puerta", "--n", 1)
        self.assertIn("ningún hallazgo de demanda está confirmado con señales recientes, pero no hay evidencia en "
                      "contra", salida)
        self.assertIn("se apoya en evidencia sin confirmar", salida)

    def test_mezcla_de_triangulados_y_sin_confirmar(self):
        identificador = self.demanda_triangulada()
        suelto, _ = self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--critico", "--sin-contra",
                                  "Se buscó")
        registro = self.registro()
        texto = producto.estado_confianza_baja(registro, [registro.hallazgos[identificador],
                                                          registro.hallazgos[suelto]], "sin confirmar")
        self.assertEqual(texto, "%s está triangulado, pero en confianza baja por 1 fuente independiente en contra y el "
                                "peldaño 5 (necesidad de fondo); %s, sin confirmar" % (identificador, suelto))
        self.assertIsNone(producto.estado_confianza_baja(registro, [registro.hallazgos[suelto]], "sin confirmar"))

    def test_una_bajada_a_mano_se_nombra_con_su_motivo(self):
        self.sesion0()
        identificador = self.hallazgo("demanda", self.fuente("demanda", 2) + self.fuente("demanda", 1, "medido"),
                                      "--critico", "--sin-contra", "Se buscó")[0]
        self.p("confianza", "--hallazgo", identificador, "--bajar", "baja", "--motivo", "Las cifras no cuadran")
        registro = self.registro()
        self.assertEqual(producto.causas_baja(registro, registro.hallazgos[identificador]),
                         "una bajada a mano (Las cifras no cuadran)")

    def test_el_veredicto_y_la_recomendacion_no_cambian(self):
        self.demanda_triangulada()
        resultado = self.veredicto()
        self.assertEqual((resultado["nivel"], resultado["recomienda"], resultado["sesion"]),
                         ("reservas", "ajustar", "1c"))


class DemandaGastadaTest(Base):
    def test_el_rojo_nombra_el_hallazgo_que_la_deja_en_baja(self):
        identificador = self.demanda_triangulada()
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.p("cerrar", "--sesion", "1c", "--busquedas", 3, "--lecturas", 2)
        salida = self.cerrar("1f")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("ajustarla otra vez con las mismas herramientas no traería evidencia nueva. La deja en baja: %s "
                      "está triangulado, pero en confianza baja por 1 fuente independiente en contra y el peldaño 5"
                      % identificador, salida)

    def test_sin_triangular_tambien_lo_nombra(self):
        debil = self.demanda_debil()
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.cerrar("1c")
        salida = self.cerrar("1f")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("La deja en baja: %s, sin confirmar con señales recientes" % debil, salida)


# --- #72 (a) · El orden real de las tandas -----------------------------------------------------------------------------

class OrdenDeTandasTest(Base):
    def test_1a_y_1c_van_por_tandas_como_en_siguiente(self):
        self.demanda_debil()
        salida = self.p("decidir", "--puerta", 1, "--ajustar", "1a", "1c", "--motivo", "Una prueba inventada aquí")
        self.assertIn("corren por tandas, como las da `siguiente`: primero la 1a (confirma el tipo de idea) y, cuando "
                      "cierre, la 1c junto con la 1g", salida)
        self.assertNotIn("1a y 1c corren en paralelo", salida)
        datos = self.json()
        self.assertEqual([paso["sesion"] for paso in datos["pasos"]], ["1a"])
        self.assertIn("1c", datos["esperan"])

    def test_en_la_misma_tanda_corren_en_paralelo(self):
        self.assertEqual(producto.texto_orden_ajuste(["2", "3"], ["2", "3"]), "; 2 y 3 corren en paralelo")
        self.assertEqual(producto.texto_orden_ajuste(["1c", "1d"], ["1c", "1d", "1f"]), "; 1c y 1d corren en paralelo")
        self.assertEqual(producto.texto_orden_ajuste(["1c"], ["1c", "1f"]), "")
        self.assertEqual(producto.texto_orden_ajuste(["1b", "1e"], ["1b", "1e", "1g", "1f"]),
                         "; corren por tandas, como las da `siguiente`: primero la 1b y, cuando cierre, la 1e junto con "
                         "la 1g")
        self.assertEqual(producto.texto_orden_ajuste(["1a", "1b", "1d"], ["1a", "1b", "1d", "1f"]),
                         "; corren por tandas, como las da `siguiente`: primero la 1a y 1b (la 1a confirma el tipo de "
                         "idea) y, cuando cierren, la 1d")


# --- #72 (c), (d), (g), (h), (i) · Comandos de las sesiones -----------------------------------------------------------

class ComandosTest(Base):
    def fila(self, nombre):
        return next(f for f in self.datos("01-investigacion/competencia.json")["matriz"] if f["nombre"] == nombre)

    def test_anuncios_admite_si_y_no(self):
        self.sesion0()
        fuente = self.fuente("competencia")[0]
        self.p("competidor", "--nombre", "App inventada", "--peldano", 1, "--fuentes", fuente, "--anuncios", "sí")
        self.assertEqual(self.fila("App inventada")["anuncios"], "sí")
        self.p("competidor", "--nombre", "App inventada", "--peldano", 1, "--fuentes", fuente, "--anuncios", "pocos")
        self.assertEqual(self.fila("App inventada")["anuncios"], "pocos")  # un nivel posterior lo reemplaza
        self.p("competidor", "--nombre", "Otra inventada", "--peldano", 1, "--fuentes", fuente, "--anuncios", "no")
        self.assertEqual(self.fila("Otra inventada")["anuncios"], "ninguno")
        self.assertIn("ninguno, pocos, muchos, si o no", self.falla(
            "competidor", "--nombre", "Otra inventada", "--peldano", 1, "--fuentes", fuente, "--anuncios", "quizás"))

    def test_una_url_ya_registrada_suma_un_mercado_sin_resumen(self):
        self.sesion0()
        self.p("fuente", "--linea", "competencia", "--url", "https://tienda.example/app", "--publicada", "2026-06",
               "--tipo", "medido", "--peldano", 1, "--resumen", "Ficha inventada")
        salida = self.p("fuente", "--linea", "competencia", "--url", "https://tienda.example/app", "--mercados", "MX")
        self.assertIn("S-COM-1 ya estaba registrada con esa URL: no se duplica; se le agregó la cobertura MX", salida)
        self.assertEqual(self.datos("01-investigacion/competencia.json")["fuentes"][0]["mercados"], ["MX"])
        error = self.falla("fuente", "--linea", "competencia", "--url", "https://otra.example/app", "--mercados", "MX",
                           "--publicada", "2026-06", "--tipo", "medido")
        self.assertIn("Una fuente nueva lleva --publicada, --tipo, --peldano y --resumen: faltan --peldano y "
                      "--resumen", error)

    def test_en_contra_despues_recalcula_la_confianza(self):
        self.sesion0()
        identificador = self.hallazgo("demanda", self.fuente("demanda", 2) + self.fuente("demanda", 1, "medido"),
                                      "--critico", "--sin-contra", "Se buscó")[0]
        self.assertEqual(self.registro().evaluar(self.registro().hallazgos[identificador])["confianza"], "alta")
        contra = self.fuente("demanda", 1, "medido")[0]
        salida = self.p("hallazgo", "--id", identificador, "--en-contra", contra)
        self.assertIn("✔ %s suma %s en contra · mismo ID · confianza media · triangulado (antes: alta · triangulado)"
                      % (identificador, contra), salida)
        self.assertIn("· 1 en contra", salida)
        item = self.datos("01-investigacion/demanda.json")["hallazgos"][0]
        self.assertEqual(item["en_contra"], [contra])
        self.assertEqual(item["enlaces"][-1]["en_contra"], [contra])
        self.assertIn("· %s ya tenía en contra %s: nada que agregar." % (identificador, contra),
                      self.p("hallazgo", "--id", identificador, "--en-contra", contra))
        favor = item["fuentes"][0]
        self.assertIn("%s ya es evidencia a favor de %s" % (favor, identificador),
                      self.falla("hallazgo", "--id", identificador, "--en-contra", favor))
        self.cerrar("1c", "01-investigacion/demanda.md")
        otra = self.fuente("demanda", 1, "medido")[0]
        self.assertIn("Sumar evidencia en contra a %s cambia su confianza, y la sesión 1c" % identificador,
                      self.falla("hallazgo", "--id", identificador, "--en-contra", otra))

    def test_tantas_en_contra_como_a_favor_lo_avisa(self):
        self.sesion0()
        identificador = self.hallazgo("demanda", self.fuente("demanda", 1, "medido"), "--sin-contra", "Se buscó")[0]
        salida = self.p("hallazgo", "--id", identificador, "--en-contra", self.fuente("demanda", 1, "medido")[0])
        self.assertIn("⚠ Tiene tantas fuentes independientes en contra como a favor: queda refutado", salida)

    def test_nuevo_da_rutas_absolutas_y_no_pide_otra_vez_las_semanas(self):
        salida = self.nuevo()
        self.assertIn("Completa %s y %s" % (self.carpeta / "00-idea.md", self.carpeta / "criterios.md"), salida)
        self.assertIn("el presupuesto de semanas ya está registrado: 6 semanas, que se cambian con `criterio`", salida)
        self.assertNotIn("el presupuesto de semanas va con `criterio`", salida)
        self.assertIn("cerrar --sesion 0 --busquedas <n> --lecturas <n>", salida)
        otra = self.tmp / "otra"
        self.carpeta = otra
        self.assertIn("el presupuesto de semanas va con `criterio`", self.p("nuevo", "--nombre", "Sin semanas"))

    def test_cerrar_la_sesion_0_anota_el_triaje(self):
        self.nuevo()
        self.completar("criterios.md")
        self.p("tipo", "--existente", "--provisional", "--motivo", "Triaje inventado de la sesión 0")
        self.completar("00-idea.md")
        salida = self.p("cerrar", "--sesion", "0", "--busquedas", 2, "--lecturas", 4)
        self.assertIn("· Triaje del tipo de idea: 2 de 3 búsquedas y 4 lecturas.", salida)
        self.assertNotIn("se pasó", salida)
        sesion = self.datos()["sesiones"]["0"]
        self.assertEqual(sesion["uso"], {"busquedas": 2, "lecturas": 4})
        self.assertEqual(sesion["pasadas"][0]["presupuesto"], {"busquedas": 3})
        self.assertEqual(producto.estado_pasada(sesion["pasadas"][0]), "primera pasada dentro del presupuesto")

    def test_el_triaje_que_se_pasa_lo_avisa(self):
        self.nuevo()
        self.completar("criterios.md")
        self.p("tipo", "--nueva", "--provisional", "--motivo", "Triaje inventado de la sesión 0")
        self.completar("00-idea.md")
        salida = self.p("cerrar", "--sesion", "0", "--busquedas", 5, "--lecturas", 1)
        self.assertIn("5 de 3 búsquedas y 1 lectura", salida)
        self.assertIn("⚠ El triaje se pasó de sus 3 búsquedas: dilo en 00-idea.md", salida)
        self.assertIn("son de una sesión que busca", self.falla("cerrar", "--sesion", "1f", "--busquedas", "1"))


# --- #72 (e) · Una propuesta informativa ------------------------------------------------------------------------------

class PropuestaInformativaTest(Base):
    def test_sin_ajustar_nombra_sus_hallazgos_y_no_cuenta_como_ajuste(self):
        self.hasta_puerta1()
        antes = self.veredicto()
        salida = self.p("propuesta", "--texto", "Un navegador leería la tendencia inventada", "--hallazgos", "H-DEM-1")
        self.assertIn("✔ PR-1 registrada para la puerta 1: Un navegador leería la tendencia inventada; sobre H-DEM-1, "
                      "informativa: no cuenta como ajuste", salida)
        self.assertIn("· Sin --ajustar es informativa", salida)
        propuesta = self.datos()["propuestas"][0]
        self.assertEqual((propuesta["ajustar"], propuesta["hallazgos"]), ("", ["H-DEM-1"]))
        despues = self.veredicto()
        claves = ("nivel", "recomienda", "sesion", "sesiones", "razones", "cambiaria")
        self.assertEqual({c: despues[c] for c in claves}, {c: antes[c] for c in claves})
        self.assertIn("Un navegador leería la tendencia inventada (sobre H-DEM-1, informativa: no cuenta como ajuste)",
                      self.p("puerta", "--n", 1))
        self.assertIn("H-VOZ-99 no existe", self.falla("propuesta", "--texto", "x", "--hallazgos", "H-VOZ-99"))


# --- #72 (f) · Corregir un diferenciador ------------------------------------------------------------------------------

class CorregirDiferenciadorTest(Base):
    def test_corrige_y_recalcula_su_estado(self):
        self.hasta_1g()
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", self.comparacion_alta(), "--texto",
               "Turnos sin suscripción")
        self.assertEqual(self.registro().estado(self.registro().diferenciadores["D-1"]), "viable")
        salida = self.p("diferenciador", "--id", "D-1", "--semanas", 9, "--copiable", "baja", "--motivo",
                        "Una patente inventada")
        self.assertIn("✔ D-1 corregido · mismo ID: --motivo Les cuesta el ingreso recurrente → Una patente inventada; "
                      "--copiable media → baja; --semanas 2 → 9", salida)
        self.assertIn("· Su estado cambia: viable → no viable.", salida)
        self.assertIn("✖ Presupuesto: 9 de 6 semanas", salida)
        item = self.datos("01-investigacion/diferenciacion.json")["diferenciadores"][0]
        self.assertEqual((item["id"], item["copiable"], item["semanas"]), ("D-1", "baja", 9))
        self.assertEqual(item["correcciones"][0]["antes"], {"motivo": "Les cuesta el ingreso recurrente",
                                                            "copiable": "media", "semanas": 2})
        self.p("diferenciador", "--id", "D-1", "--semanas", 2)
        self.assertEqual(self.registro().estado(self.registro().diferenciadores["D-1"]), "viable")
        self.assertIn("nada que corregir", self.p("diferenciador", "--id", "D-1", "--semanas", 2))

    def test_valida_lo_que_corrige(self):
        self.hasta_1g()
        self.assertIn("--vector no va", self.falla("diferenciador", "--id", "D-1", "--vector", "precio"))
        self.assertIn("pasa lo que corriges", self.falla("diferenciador", "--id", "D-1"))
        self.assertIn("No existe el diferenciador D-9", self.falla("diferenciador", "--id", "D-9", "--semanas", 1))
        self.assertIn("faltan --texto", self.falla("diferenciador", "--vector", "precio"))
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", self.comparacion_alta(), "--texto",
               "Turnos sin suscripción")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("Corregir un diferenciador es trabajo de la sesión 1g, que ya cerró",
                      self.falla("diferenciador", "--id", "D-1", "--semanas", 3))


class DocumentacionTest(unittest.TestCase):
    def test_skill_md_lo_describe(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for texto in ("diferenciador --id D-…", "--en-contra S-…", "--anuncios", "cerrar --sesion 0 --busquedas"):
            self.assertIn(texto, skill)
        self.assertLessEqual(len(skill.splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
