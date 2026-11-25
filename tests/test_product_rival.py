"""Tests de las mejoras #20 a #24 de hb-product: el rival a superar y la prueba de elección (#24), el pago único sobre
las instalaciones nuevas del mes (#22), los vacíos de cobertura en cualquier línea (#21), el consumo sin anotar con sus
sesiones (#23) y las ideas con el mismo nombre en el tablero (#20).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import re
import unittest

import test_product as base
from helpers import write

HOY = base.HOY


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def hasta_1g(self, rival=True, bloquea=False):
        """Sesiones 0 a 1e de una idea existente con un competidor gratis (PlantaPlus) y un diferenciador de precio
        (D-1) cuyo dolor triangulado y en confianza alta es H-VOZ-1. La sesión 1g queda abierta, sin la comparación con
        el rival. Con bloquea, la tienda del objetivo nombra la categoría (un bloqueo de políticas: no hay Viable para
        probar)."""
        self.sesion0()
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--descargas", "1M",
               "--precio", "3,99 al mes")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[1], "--descargas", "500k",
               "--precio", "gratis", "--modelo", "sin anuncios", *(["--rival"] if rival else []))
        self.sustituto(fuentes[2])
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "Se buscó y no apareció")
        self.completar("01-investigacion/competencia.md")
        if rival:
            self.cerrar("1a")
        voz = self.linea("1b", "voz-del-usuario", "usuario", 1, "--competidores", "RiegoFácil,PlantaPlus")
        for sesion, nombre in (("1c", "demanda"), ("1d", "monetizacion"), ("1e", "politicas")):
            self.linea(sesion, nombre, "terceros", 1, *(["--bloquea", "google-play"] if bloquea and
                                                        nombre == "politicas" else []))
        self.p("diferenciador", "--vector", "precio", "--texto", "Pago único en vez de suscripción", "--hallazgos",
               voz, "--se-ve", "ficha", "--copiable", "media", "--motivo", "Les cuesta el ingreso recurrente",
               "--semanas", 2, "--principal")
        return voz

    def comparacion_media(self):
        """Un hallazgo de diferenciación triangulado, pero en confianza media (3 opiniones independientes)."""
        identificador, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 3, "opinion"),
                                         "--competidores", "PlantaPlus", "--sin-contra", "Se buscó y no apareció")
        return identificador

    def sin_triangular(self):
        identificador, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 1, "usuario"),
                                         "--competidores", "PlantaPlus", "--sin-contra", "Se buscó y no apareció")
        return identificador

    def puerta1(self, *frente, valores="4,4,4,4,3", mitigacion=None):
        """Registra la comparación de D-1 con el rival, cierra 1g y 1f y devuelve la salida de la puerta 1."""
        self.p("frente", "--id", "D-1", *frente)
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", valores, *(["--mitigacion", mitigacion] if mitigacion else []))
        self.cerrar("1f", "01-sintesis.md")
        return self.p("puerta", "--n", 1)


# --- #24 · El rival a superar es la alternativa gratis más fuerte ----------------------------------------------------

class RivalTest(Base):
    def test_1a_no_cierra_sin_marcar_el_rival_o_decir_que_no_lo_hay(self):
        self.hasta_1g(rival=False)
        error = self.falla("cerrar", "--sesion", "1a")
        self.assertIn("falta marcar la alternativa gratis más fuerte, el rival que cada diferenciador tiene que "
                      "superar (sea sustituto o competidor directo)", error)
        self.assertIn("· Falta marcar la alternativa gratis más fuerte", self.p("matriz"))
        salida = self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", "S-COM-2", "--rival")
        self.assertIn("⚠ Rival a superar: C-2 (PlantaPlus), la alternativa gratis más fuerte.", salida)
        self.assertIn("1 · rival", self.p("matriz"))
        self.assertIn("Sesión 1a · Competencia cerrada", self.p("cerrar", "--sesion", "1a"))
        salida = self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", "S-COM-1", "--rival")
        self.assertIn("(antes: C-2)", salida)  # hay un solo rival: marcar otro reemplaza al anterior
        rivales = [c["id"] for c in self.datos("01-investigacion/competencia.json")["matriz"] if c.get("rival")]
        self.assertEqual(rivales, ["C-1"])

    def test_sin_rival_lleva_motivo_y_no_convive_con_un_rival(self):
        self.hasta_1g()
        self.assertIn("Ya hay un rival a superar (C-2 (PlantaPlus))",
                      self.falla("competidor", "--sin-rival", "Ninguna app gratis resuelve la necesidad"))
        self.assertIn("lleva el motivo", self.falla("competidor", "--sin-rival", "no"))
        self.assertIn("Falta --nombre, --peldano, --fuentes", self.falla("competidor"))
        self.assertIn("es un sustituto de pago", self.falla(
            "competidor", "--nombre", "Jardinero a domicilio", "--peldano", 4, "--fuentes", "S-COM-3", "--sustituto",
            "pago", "--resuelve", "si", "--rival"))

    def test_1g_no_cierra_sin_comparar_cada_diferenciador_con_el_rival(self):
        self.hasta_1g()
        self.completar("01-investigacion/diferenciacion.md")
        self.assertIn("D-1 sin comparar con C-2 (PlantaPlus), el rival a superar: `frente --id D-1 --rival C-2",
                      self.falla("cerrar", "--sesion", "1g"))
        self.assertIn("✖ Frente al rival: sin comparar con C-2 (PlantaPlus) (`frente --id D-1 --rival C-2 "
                      "--resultado supera|iguala|no --hallazgos …`; lo nombran H-VOZ-1)", self.p("principal", "--id",
                                                                                                "D-1"))

    def test_frente_valida_el_rival_los_hallazgos_y_la_sesion(self):
        voz = self.hasta_1g()
        self.assertIn("C-1 (RiegoFácil) no es un rival a superar", self.falla(
            "frente", "--id", "D-1", "--rival", "C-1", "--resultado", "supera", "--hallazgos", voz, "--texto", "x"))
        self.assertIn("No existe el diferenciador D-9", self.falla(
            "frente", "--id", "D-9", "--resultado", "supera", "--hallazgos", voz, "--texto", "x"))
        self.assertIn("No existe", self.falla(
            "frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "H-DIF-9", "--texto", "x"))
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", voz, "--texto", "Sin suscripción")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("es trabajo de la sesión 1g, que ya cerró", self.falla(
            "frente", "--id", "D-1", "--resultado", "iguala", "--hallazgos", voz, "--texto", "x"))

    def test_igualar_al_rival_es_paridad_no_viable_y_no_sirve_de_principal(self):
        voz = self.hasta_1g()
        salida = self.p("frente", "--id", "D-1", "--resultado", "iguala", "--hallazgos", voz, "--texto",
                        "PlantaPlus ya es gratis y sin anuncios")
        self.assertIn("✔ D-1 frente a C-2 (PlantaPlus): lo iguala (paridad)", salida)
        self.assertIn("· Igualar es paridad (básico en Kano)", salida)
        self.assertIn("✖ D-1: no viable (paridad: iguala al rival)", salida)
        self.assertIn("✖ Frente al rival: iguala a C-2 (PlantaPlus): no viable (paridad", salida)
        salida = self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("⚠ D-1 solo iguala al rival C-2 (PlantaPlus): es paridad", salida)
        self.p("puntaje", "--valores", "4,4,4,4,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("Ningún diferenciador supera al rival C-2 (PlantaPlus) con hallazgos "
                      "triangulados: D-1 (no viable: paridad)", salida)
        self.assertIn("El principal (D-1) iguala al rival C-2 (PlantaPlus): no viable (paridad, básico en Kano)",
                      salida)
        self.assertIn("✖ Los hallazgos del diferenciador principal están triangulados y supera al rival C-2 "
                      "(PlantaPlus) · D-1: iguala a C-2 (PlantaPlus)", salida)
        self.p("reporte")
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("No viable · paridad", html)
        self.assertIn("rival a superar", html)

    def test_supera_con_prueba_de_eleccion_es_viable(self):
        voz = self.hasta_1g()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", voz, "--texto", "Sin suscripción")
        self.assertIn("🟢  PUERTA 1 · VIABLE  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("El diferenciador principal (D-1) es viable y supera al rival C-2 (PlantaPlus), con prueba de "
                      "elección", salida)

    def test_supera_con_un_hallazgo_en_media_es_viable_para_probar(self):
        # sin la prueba de elección, pero con el dolor triangulado: se prueba después del lanzamiento (feedback #47)
        self.hasta_1g()
        media = self.comparacion_media()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("D-1 supera al rival C-2 (PlantaPlus) con el dolor confirmado (H-VOZ-1), pero falta la prueba de "
                      "que eso haga elegir la app (%s en confianza media)" % media, salida)
        self.assertIn("decidir --puerta 1 --seguir --carpeta product", salida)

    def test_con_un_bloqueo_de_politicas_supera_sin_prueba_de_eleccion_sigue_con_reservas(self):
        # sin cambios cuando hay un bloqueo de políticas, aunque tenga mitigación (feedback #47)
        self.hasta_1g(bloquea=True)
        media = self.comparacion_media()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción",
                              valores="5,4,4,1,3", mitigacion="Lanzar solo en la web")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("D-1 supera al rival C-2 (PlantaPlus), pero sin prueba de que eso haga elegir la app (%s en confianza "
                      "media)" % media, salida)
        self.assertIn("Un hallazgo triangulado y en confianza alta que muestre que la gente elige por D-1", salida)
        self.assertIn("decidir --puerta 1 --ajustar 1g --carpeta product", salida)

    def test_una_hipotesis_debil_sobre_el_diferenciador_quita_la_prueba_de_eleccion(self):
        voz = self.hasta_1g()
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS.replace("| D-1 | sostenida |", "| D-1 | débil |"))
        salida = self.puerta1("--resultado", "supera", "--hallazgos", voz, "--texto", "Sin suscripción")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR", salida)
        self.assertIn("(la hipótesis HIP-02 quedó débil)", salida)
        # una hipótesis refutada sobre él no es falta de prueba: es evidencia en contra
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS.replace("| D-1 | sostenida |", "| D-1 | refutada |"))
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS", self.p("puerta", "--n", 1))

    def test_supera_sin_ningun_hallazgo_triangulado_es_no_viable(self):
        self.hasta_1g()
        suelto = self.sin_triangular()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", suelto, "--texto", "Lo dice una reseña",
                              valores="4,4,4,4,1")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Ningún diferenciador supera al rival C-2 (PlantaPlus) con hallazgos "
                      "triangulados", salida)
        self.assertIn("Frente al rival: supera a C-2 (PlantaPlus), pero ninguno de sus hallazgos (%s) está "
                      "triangulado" % suelto, self.texto_viabilidad())

    def texto_viabilidad(self):
        """La viabilidad de D-1, leída del registro (la sesión 1g ya cerró y `principal` no corre)."""
        registro = base.producto.Registro(self.carpeta, self.datos()["criterios"])
        return "\n".join(texto for _, texto in registro.viabilidad(registro.diferenciadores["D-1"]))

    def test_con_la_1g_reabierta_y_sin_presupuesto_no_recomienda_ajustarla_otra_vez(self):
        self.hasta_1g(bloquea=True)  # con un bloqueo de políticas no hay Viable para probar
        media = self.comparacion_media()
        self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción",
                     valores="5,4,4,1,3", mitigacion="Lanzar solo en la web")
        self.p("decidir", "--puerta", 1, "--ajustar", "1g")
        self.assertEqual(self.datos()["sesiones"]["1g"]["reaperturas"], 1)
        self.assertIn("lo que usó la línea en esta pasada", self.falla("cerrar", "--sesion", "1g", "--busquedas",
                                                                       "muchas"))
        self.assertIn("son de una sesión que busca con presupuesto",
                      self.falla("cerrar", "--sesion", "1f", "--lecturas", "2"))
        salida = self.p("cerrar", "--sesion", "1g", "--busquedas", 7, "--lecturas", 4)
        # cada reapertura tiene su propio presupuesto: la mitad del original (feedback #34)
        self.assertIn("· Presupuesto usado por la línea diferenciacion: 7 de 8 búsquedas y 4 de 5 lecturas en la "
                      "reapertura 1.", salida)
        self.assertIn("la skill no recomendará ajustar la 1g otra vez", salida)
        salida = self.cerrar("1f")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("La sesión 1g ya se reabrió y usó su presupuesto (7 de 8 búsquedas y 4 de 5 lecturas en la "
                      "reapertura 1): "
                      "ajustarla otra vez no traería evidencia nueva", salida)
        self.assertIn("D-1 supera al rival C-2 (PlantaPlus), pero sin prueba de que eso haga elegir la app", salida)
        self.assertNotIn("★ Recomendado · Ajustar 1g", salida)
        self.p("decidir", "--puerta", 1, "--ajustar", "1g", "--motivo", "Quiero buscar en otro vector")
        sesion = self.datos()["sesiones"]["1g"]
        self.assertEqual(sesion["uso"], {"busquedas": 7, "lecturas": 4})  # se conserva
        self.assertEqual([p["reapertura"] for p in sesion["pasadas"]], [1])

    def test_con_presupuesto_de_sobra_sigue_recomendando_ajustar_la_1g(self):
        self.hasta_1g(bloquea=True)
        media = self.comparacion_media()
        self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción",
                     valores="5,4,4,1,3", mitigacion="Lanzar solo en la web")
        self.p("decidir", "--puerta", 1, "--ajustar", "1g")
        self.p("cerrar", "--sesion", "1g", "--busquedas", 5, "--lecturas", 3)
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", self.cerrar("1f"))

    def test_un_sustituto_que_resuelve_tambien_es_rival_y_suma_al_marcado(self):
        voz = self.hasta_1g()
        self.sustituto("S-COM-3", "Recordatorio del sistema", "nativo", "si")
        error = self.falla("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", voz, "--texto", "x")
        self.assertIn("Hay 2 rivales (C-2 (PlantaPlus); C-4 (Recordatorio del sistema)): elige uno con --rival", error)
        self.p("frente", "--id", "D-1", "--rival", "C-2", "--resultado", "supera", "--hallazgos", voz, "--texto", "x")
        self.assertIn("D-1 sin comparar con C-4", self.falla("cerrar", "--sesion", "1g"))


# --- #22 · El pago único se cobra a las instalaciones nuevas del mes -------------------------------------------------

class EscenariosPorTipoTest(Base):
    ENTRADA = {"mercados": [{
        "mercado": "MX",
        "dau": {"pesimista": 600, "base": 600, "optimista": 600, "fuente": "S-MON-1"},
        "dau_mau": {"pesimista": 0.3, "base": 0.3, "optimista": 0.3, "fuente": "S-MON-1"},
        "instalaciones_mes": {"pesimista": 1000, "base": 1000, "optimista": 1000, "fuente": "S-MON-1"},
        "anuncios": [{"formato": "banner",
                      "impresiones_por_dau": {"pesimista": 4, "base": 4, "optimista": 4, "fuente": "S-MON-1"},
                      "ecpm": {"pesimista": 0.5, "base": 0.5, "optimista": 0.5, "fuente": "S-MON-1"}}],
        "compras": [
            {"nombre": "Extras", "tipo": "pago-unico", "precio": 3, "comision": 0.15,
             "conversion": {"pesimista": 0.05, "base": 0.05, "optimista": 0.05, "fuente": "S-MON-1"}},
            {"nombre": "Pro", "tipo": "suscripcion", "precio": 2, "comision": 0.30,
             "conversion": {"pesimista": 0.02, "base": 0.02, "optimista": 0.02, "fuente": "S-MON-1"}},
            {"nombre": "Pro anual", "tipo": "suscripcion", "periodo": "anio", "precio": 24, "comision": 0.30,
             "conversion": {"pesimista": 0.02, "base": 0.02, "optimista": 0.02, "fuente": "S-MON-1"}}]}]}

    def calcular(self, entrada):
        write(self.carpeta / "escenarios.json", json.dumps(entrada))
        return self.p("escenarios", "--entrada", "escenarios.json")

    def entrada(self):
        return json.loads(json.dumps(self.ENTRADA))

    def test_casos_conocidos_de_anuncios_pago_unico_y_suscripcion(self):
        self.hasta_puerta1()
        salida = self.calcular(self.entrada())
        # anuncios: 600 × 4 × 30 × 0,5 / 1000 = 36
        self.assertIn("✔ Anuncios · banner · 36 USD al mes en el caso base", salida)
        # pago único: 1000 instalaciones nuevas × 0,05 × 3 × (1 − 0,15) = 127,50
        self.assertIn("✔ Pago único · Extras · 127,50 USD al mes en el caso base", salida)
        # suscripción: 600 / 0,3 = 2000 usuarios del mes × 0,02 × 2 × (1 − 0,30) = 56
        self.assertIn("✔ Suscripción · Pro · 56 USD al mes en el caso base", salida)
        # la anual: 24 / 12 = 2 al mes, lo mismo
        self.assertIn("✔ Suscripción · Pro anual · 56 USD al mes en el caso base", salida)
        self.assertIn("| MX | 600 | 275,50 | 275,50 | 275,50 |", salida)
        self.assertIn("pago único: instalaciones nuevas del mes × conversión × precio × (1 − comisión)", salida)
        self.assertEqual(self.datos()["escenarios"]["calculo"], 2)

    def test_el_pago_unico_no_crece_con_los_usuarios_activos(self):
        self.hasta_puerta1()
        entrada = self.entrada()
        entrada["mercados"][0]["anuncios"] = []
        entrada["mercados"][0]["compras"] = entrada["mercados"][0]["compras"][:1]
        del entrada["mercados"][0]["dau_mau"]  # sin suscripción no hace falta
        self.assertIn("✔ Pago único · Extras · 127,50 USD", self.calcular(entrada))
        entrada["mercados"][0]["dau"] = {"pesimista": 60000, "base": 60000, "optimista": 60000, "fuente": "S-MON-1"}
        self.assertIn("✔ Pago único · Extras · 127,50 USD", self.calcular(entrada))  # antes: × 100
        entrada["mercados"][0]["instalaciones_mes"]["base"] = 2000
        self.assertIn("✔ Pago único · Extras · 255 USD", self.calcular(entrada))

    def test_cada_tipo_pide_lo_suyo(self):
        self.hasta_puerta1()
        entrada = self.entrada()
        del entrada["mercados"][0]["instalaciones_mes"]
        self.assertIn("`MX.instalaciones_mes` hace falta para un pago único", self.falla_con(entrada))
        entrada = self.entrada()
        del entrada["mercados"][0]["dau_mau"]
        self.assertIn("`MX.dau_mau` hace falta para una suscripción", self.falla_con(entrada))
        entrada = self.entrada()
        entrada["mercados"][0]["compras"][2]["periodo"] = "semana"
        self.assertIn("`MX.compras.Pro anual.periodo` es mes o anio", self.falla_con(entrada))
        entrada = self.entrada()
        entrada["mercados"][0]["instalaciones_mes"]["fuente"] = ""
        salida = self.calcular(entrada)
        self.assertIn("✖ Pago único · Extras · 127,50 USD al mes en el caso base · estimación: sin fuente en "
                      "MX.instalaciones_mes", salida)
        self.assertIn("✔ Suscripción · Pro", salida)  # la suscripción no depende de las instalaciones

    def falla_con(self, entrada):
        write(self.carpeta / "escenarios.json", json.dumps(entrada))
        return self.falla("escenarios", "--entrada", "escenarios.json")

    def test_unos_escenarios_con_el_calculo_anterior_piden_recalcular(self):
        self.hasta_puerta2()
        datos = self.datos()
        datos["escenarios"].pop("calculo")
        for modelo in datos["escenarios"]["modelos"]:
            modelo["nombre"] = modelo["nombre"].replace("Pago único · ", "Compra · ")
        write(self.carpeta / "producto.json", json.dumps(datos))
        salida = self.p("puerta", "--n", 2)
        self.assertIn("los escenarios son de una versión anterior que cobraba el pago único cada mes", salida)
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 2", salida)

    def test_la_plantilla_trae_los_dos_tipos(self):
        plantilla = json.loads((base.SKILL / "assets" / "plantillas" / "escenarios.json").read_text(encoding="utf-8"))
        tipos = {c["tipo"] for c in plantilla["mercados"][0]["compras"]}
        self.assertEqual(tipos, {"pago-unico", "suscripcion"})
        self.assertIn("instalaciones_mes", plantilla["mercados"][0])


# --- #21 · Cualquier línea registra vacíos por mercado, idioma y tienda ----------------------------------------------

class VacioEnCualquierLineaTest(Base):
    def setUp(self):
        super().setUp()
        self.sesion0()
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")

    def test_monetizacion_registra_un_vacio_de_tienda_y_queda_a_la_vista(self):
        salida = self.p("vacio", "--linea", "monetizacion", "--tienda", "google-play", "--motivo", "herramienta",
                        "--texto", "La ficha de precios es dinámica")
        self.assertIn("✔ V-MON-1 registrado: monetizacion · tienda google-play", salida)
        salida = self.p("cobertura", "--linea", "monetizacion")
        self.assertIn("⚠ tienda google-play · vacío, límite de las herramientas (V-MON-1)", salida)
        self.assertIn("monetizacion · tienda google-play", self.p("puerta", "--n", 1))

    def test_diferenciacion_tambien_y_el_objetivo_se_sigue_validando(self):
        self.assertIn("✔ V-DIF-1 registrado", self.p("vacio", "--linea", "diferenciacion", "--idioma", "es",
                                                    "--motivo", "sin-resultados", "--texto", "Nada en español"))
        self.assertIn("no está en el objetivo", self.falla("vacio", "--linea", "demanda", "--tienda", "app-store",
                                                         "--motivo", "herramienta", "--texto", "x"))
        self.assertIn("idioma es · vacío", self.p("cobertura"))

    def test_una_fuente_de_la_linea_cubre_el_vacio(self):
        self.p("vacio", "--linea", "monetizacion", "--tienda", "google-play", "--motivo", "herramienta", "--texto",
               "Dinámica")
        self.fuente("monetizacion")  # cubre MX, es y google-play
        salida = self.p("cobertura", "--linea", "monetizacion")
        self.assertNotIn("google-play · vacío", salida)
        self.assertIn("0 vacíos registrados", salida)


# --- #23 · El consumo sin anotar dice qué sesiones faltan ------------------------------------------------------------

class ConsumoSinAnotarTest(Base):
    def test_dice_la_sesion_y_no_aparece_si_no_falta_ninguna(self):
        self.nuevo()
        self.p("consumo", "--sesion", "1a", "--tokens", "90k")
        self.completar("criterios.md")
        self.p("tipo", "--existente", "--provisional", "--motivo", "Triaje inventado de la sesión 0")
        self.cerrar("0", "00-idea.md")
        salida = self.p("siguiente")
        self.assertIn("Consumo sin anotar (opcional) de la sesión 0:", salida)
        self.assertNotIn("(opcional): 0", salida)
        self.assertIn("(sin anotar: la sesión 0)", (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        self.p("consumo", "--sesion", "0", "--tokens", "20k")
        self.assertNotIn("Consumo sin anotar", self.p("siguiente"))
        self.assertIn("Consumo anotado:** sesión 1a: 90 000 tokens · sesión 0: 20 000 tokens",
                      (self.carpeta / "estado.md").read_text(encoding="utf-8"))


# --- #20 · Ideas con el mismo nombre en el tablero -------------------------------------------------------------------

class TableroNombresRepetidosTest(Base):
    def test_las_ideas_con_el_mismo_nombre_muestran_su_carpeta_y_su_fecha(self):
        raiz = self.tmp
        for carpeta in ("linterna", "linterna-2"):
            self.carpeta = raiz / carpeta / "product"
            self.p("nuevo", "--nombre", "Linterna", "--semanas", 2)
        self.carpeta = raiz / "riego" / "product"
        self.p("nuevo", "--nombre", "Riego en turnos", "--semanas", 6)
        salida = self.p("tablero", "--raiz", raiz)
        self.assertIn("· Linterna (carpeta linterna/product · creada el %s) · En curso" % HOY, salida)
        self.assertIn("· Linterna (carpeta linterna-2/product · creada el %s) · En curso" % HOY, salida)
        self.assertIn("· Riego en turnos · En curso", salida)  # un nombre único no lleva la carpeta
        html = (raiz / "index.html").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'<span class="nota">carpeta linterna(-2)?/product', html)), 2)
        self.assertNotIn("carpeta riego/product", html)


# --- Documentación de #20 a #24 -------------------------------------------------------------------------------------

class DocumentacionTest(unittest.TestCase):
    def test_las_referencias_y_las_plantillas_explican_las_reglas_nuevas(self):
        leer = lambda nombre: (base.SKILL / "references" / nombre).read_text(encoding="utf-8")
        plantilla = lambda nombre: (base.SKILL / "assets" / "plantillas" / nombre).read_text(encoding="utf-8")
        skill = (base.SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill, r"`frente`")
        self.assertIn("--rival", skill)
        for texto in ("frente --id", "paridad", "Prueba de elección", "--sin-rival"):
            self.assertIn(texto, leer("diferenciacion.md"), texto)
        for texto in ("prueba de elección", "La 1g agotada no se recomienda otra vez", "--busquedas"):
            self.assertIn(texto, leer("puertas.md"), texto)
        self.assertIn("instalaciones_mes", leer("estrategia.md"))
        self.assertIn("El pago único no es recurrente", leer("estrategia.md"))
        self.assertIn("**Cualquier línea** registra vacíos", leer("investigacion.md"))
        self.assertIn("--rival", leer("investigacion.md"))
        self.assertIn("## Rival a superar", plantilla("competencia.md"))
        self.assertIn("¿Prueba de elección?", plantilla("diferenciacion.md"))


if __name__ == "__main__":
    unittest.main()
