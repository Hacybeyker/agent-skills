"""Tests de las mejoras de hb-product que salieron de la prueba de punta a punta: modelo concreto (#1), meta opcional
(#2), diferenciador triangulado (#4), cobertura por mercado, idioma y tienda (#5), consumo (#6), fuentes difíciles y
CSV de reseñas (#7), una sola regla de confianza y triangulación (#8), la puerta dentro de `siguiente` (#9), la fuente
oficial (#10), el sustituto más fuerte (#11), la tienda que bloquea la categoría (#12), la demanda con señales actuales
(#13) y la fecha de publicación real (#14). El reporte y el tablero (#15 y #16) están en test_product_reporte.py.

Los datos son inventados: la misma app de turnos de riego de test_product.py, con competidores y reseñas de ejemplo.
"""
import json
import os
import re
import unittest

import test_product as base
from helpers import write

HOY = base.HOY
SKILL = base.SKILL


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT"):
        os.environ.pop(variable, None)


RESENAS = """Review Submit Date and Time,Star Rating,Review Text,Reviewer Language,Reviewer Name
2026-10-02T10:00:00Z,1,"Se cierra cada vez que agrego un vecino",es,Persona Inventada Uno
2026-11-10T08:30:00Z,2,"Muy cara la suscripción para lo que hace",es,Persona Inventada Dos
2026-09-15T12:00:00Z,5,"Funciona bien",es,Persona Inventada Tres
2026-08-01T09:00:00Z,3,"Não tem lembrete por turno",pt-BR,Persona Inventada Cuatro
"""


class Base(base.Base):
    def csv(self, nombre="resenas.csv", texto=RESENAS):
        ruta = self.tmp / nombre
        write(ruta, texto)
        return ruta

    def principal_baja(self):
        """Hasta la sesión 1g, con un diferenciador principal que cumple los cuatro criterios por un vector medible,
        pero cuyo hallazgo tiene 2 fuentes y no está triangulado."""
        self.sesion0()
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--descargas", "1M",
               "--precio", "3,99 al mes")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[1], "--descargas", "500k",
               "--precio", "2,99 al mes")
        self.sustituto(fuentes[2])
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "Se buscó y no apareció")
        self.cerrar("1a", "01-investigacion/competencia.md")
        self.linea("1b", "voz-del-usuario", "usuario", 1, "--competidores", "RiegoFácil,PlantaPlus")
        for sesion, nombre in (("1c", "demanda"), ("1d", "monetizacion"), ("1e", "politicas")):
            self.linea(sesion, nombre)
        debil, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 2, "usuario"), "--critico",
                                 "--sin-contra", "Se buscó y no apareció")
        salida = self.p("diferenciador", "--vector", "precio", "--texto", "Pago único en vez de suscripción",
                        "--hallazgos", debil, "--se-ve", "ficha", "--copiable", "media", "--motivo",
                        "Cambiar de modelo les cuesta ingresos recurrentes", "--semanas", 2, "--principal")
        return debil, salida


# --- #1 · Modelo concreto y configurable ---------------------------------------------------------------------------

class ModelosTest(Base):
    def test_siguiente_nombra_el_modelo_concreto_y_su_esfuerzo(self):
        salida = self.nuevo()
        self.assertIn("1. Este chat · Sesión 0 · Idea · Modelo: Sonnet 5.5 · Esfuerzo: medio", salida)
        self.assertNotIn("modelo sugerido", salida)
        self.completar("criterios.md")
        salida = self.cerrar("0", "00-idea.md")
        self.assertIn("Sesión 1a · Competencia · Modelo: Sonnet 5.5 · Esfuerzo: medio", salida)
        self.assertIn("modelos --herramienta <claude|copilot>", salida)
        self.assertNotIn("Abrir:", salida)

    def test_con_claude_code_cada_chat_trae_el_comando_que_lo_abre(self):
        self.investigacion()
        salida = self.p("modelos", "--herramienta", "claude")
        self.assertIn("| 1a · Competencia | Sonnet 5.5 | medio | cd %s && claude --model claude-sonnet-5-5 --effort "
                      "medium |" % self.tmp, salida)
        salida = self.p("siguiente")
        self.assertIn("Sesión 1f · Síntesis · Modelo: Opus 5.5 · Esfuerzo: alto", salida)
        self.assertIn("   Abrir: cd %s && claude --model claude-opus-5-5 --effort high" % self.tmp, salida)
        self.assertNotIn("modelos --herramienta <claude|copilot>", salida)

    def test_los_nombres_se_cambian_y_copilot_usa_su_propio_id(self):
        self.sesion0()
        salida = self.p("modelos", "--intermedio", "GPT 5.3 Codex", "--alto", "claude-opus-5-5", "--herramienta",
                        "copilot")
        self.assertIn("| 1a · Competencia | GPT 5.3 Codex | medio |", salida)
        self.assertIn("copilot --model gpt-5.3-codex --effort medium", salida)
        self.assertIn("copilot --model claude-opus-5-5 --effort high", salida)  # un id va tal cual
        self.assertIn("Modelo: GPT 5.3 Codex · Esfuerzo: medio", self.p("siguiente"))
        self.assertEqual(self.datos()["modelos"], {"intermedio": "GPT 5.3 Codex", "alto": "claude-opus-5-5"})

    def test_otra_herramienta_necesita_su_comando_con_el_modelo(self):
        self.nuevo()
        self.assertIn("--comando", self.falla("modelos", "--herramienta", "otra"))
        self.assertIn("{modelo}", self.falla("modelos", "--herramienta", "otra", "--comando", "mi-cli"))
        self.assertIn("va con --herramienta", self.falla("modelos", "--comando", "mi-cli --model {modelo}"))
        salida = self.p("modelos", "--herramienta", "otra", "--comando", "mi-cli --model {modelo}")
        self.assertIn("mi-cli --model 'Sonnet 5.5'", salida)
        self.p("modelos", "--herramienta", "ninguna")
        self.assertIsNone(self.datos()["herramienta"])

    def test_la_referencia_dice_los_mismos_modelos_y_esfuerzos(self):
        texto = (SKILL / "references" / "modelos.md").read_text(encoding="utf-8")
        for nivel, nombre in base.producto.MODELOS.items():
            self.assertIn(nombre, texto, nivel)
        for sesion in base.producto.SESIONES:
            fila = re.search(r"^\| %s · [^|]+\| ([^|]+)\| ([^|]+)\|" % re.escape(sesion["id"]), texto, re.M)
            self.assertIsNotNone(fila, sesion["id"])
            self.assertIn(base.producto.MODELOS[sesion["modelo"]], fila.group(1))
            self.assertIn(base.producto.ESFUERZO[sesion["modelo"]], fila.group(2))
        self.assertIn("references/modelos.md", (SKILL / "SKILL.md").read_text(encoding="utf-8"))


class IdModeloTest(unittest.TestCase):
    def test_el_id_sale_del_nombre_segun_la_herramienta(self):
        id_modelo = base.producto.id_modelo
        self.assertEqual(id_modelo("Sonnet 5.5", "claude"), "claude-sonnet-5-5")
        self.assertEqual(id_modelo("Sonnet 5.5", "copilot"), "claude-sonnet-5.5")
        self.assertEqual(id_modelo("GPT 5.3 Codex", "copilot"), "gpt-5.3-codex")
        self.assertEqual(id_modelo("claude-haiku-5-5", "copilot"), "claude-haiku-5-5")


# --- #2 · Meta de ingresos opcional y referencial ------------------------------------------------------------------

class MetaTest(Base):
    def test_sin_meta_la_sesion_0_cierra_y_el_estado_lo_dice(self):
        self.p("nuevo", "--nombre", "Riego en turnos", "--semanas", 6, "--mercados", "MX", "--idiomas", "es",
               "--tiendas", "google-play")
        self.completar("criterios.md")
        self.assertIn("✔ Sesión 0 · Idea cerrada", self.cerrar("0", "00-idea.md"))
        self.assertIn("sin meta de ingresos (opcional)", self.p("estado"))

    def test_obligatoria_la_pide_al_cerrar_la_sesion_0(self):
        self.p("nuevo", "--nombre", "Riego en turnos", "--semanas", 6, "--meta-obligatoria", "--mercados", "MX",
               "--idiomas", "es", "--tiendas", "ninguna")
        self.assertEqual(self.datos()["criterios"]["meta_obligatoria"], "si")
        self.completar("criterios.md")
        self.completar("00-idea.md")
        self.assertIn("falta el criterio `meta_ingresos_mes`", self.falla("cerrar", "--sesion", "0"))
        self.p("criterio", "--clave", "meta_ingresos_mes", "--valor", 500)
        self.assertIn("meta de 500 USD al mes (obligatoria)", self.p("estado"))

    def test_criterio_acepta_quitar_la_meta_y_valida_si_es_obligatoria(self):
        self.nuevo()
        salida = self.p("criterio", "--clave", "meta_ingresos_mes", "--valor", 0)
        self.assertIn("sin meta de ingresos (opcional)", salida)
        self.assertIn("no bloquea ninguna puerta", salida)
        self.assertIn("si o no", self.falla("criterio", "--clave", "meta_obligatoria", "--valor", "quizá"))
        self.assertIn("Es criterio de la puerta 2", self.p("criterio", "--clave", "meta_obligatoria", "--valor", "Sí"))
        self.assertEqual(self.datos()["criterios"]["meta_obligatoria"], "si")

    def test_una_carpeta_anterior_toma_el_criterio_nuevo_por_defecto(self):
        self.nuevo()
        datos = self.datos()
        del datos["criterios"]["meta_obligatoria"]
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.assertIn("meta_obligatoria", self.p("criterio"))

    def test_la_puerta_2_pide_un_modelo_de_monetizacion_viable_con_evidencia(self):
        self.hasta_puerta2()
        entrada = {"mercados": [{
            "mercado": "MX", "dau": {"pesimista": 500, "base": 1000, "optimista": 2000, "fuente": "S-MON-3"},
            "dau_mau": {"pesimista": 0.2, "base": 0.2, "optimista": 0.2, "fuente": "S-MON-3"},
            "anuncios": [{"formato": "banner", "impresiones_por_dau": 5,
                          "ecpm": {"pesimista": 0.4, "base": 0.4, "optimista": 0.4, "fuente": "S-MON-3"}}],
            "compras": [{"nombre": "Pago único", "precio": 4, "comision": 0.15,
                         "conversion": {"pesimista": 0.02, "base": 0.02, "optimista": 0.02, "fuente": "S-MON-3"}}]}]}
        write(self.carpeta / "escenarios.json", json.dumps(entrada))
        salida = self.p("escenarios", "--entrada", "escenarios.json")
        self.assertIn("✖ Anuncios · banner · 60 USD al mes en el caso base · estimación: sin fuente en "
                      "MX.anuncios.banner.impresiones_por_dau", salida)
        self.assertIn("✔ Compra · Pago único · 340 USD al mes en el caso base", salida)
        self.assertIn("Meta (referencial, no es criterio de ninguna puerta): 300 USD al mes", salida)
        self.assertIn("✔ Al menos un modelo de monetización viable con evidencia · Compra · Pago único: 340 USD",
                      self.p("puerta", "--n", 2))
        entrada["mercados"][0]["compras"] = []
        write(self.carpeta / "escenarios.json", json.dumps(entrada))
        self.p("escenarios", "--entrada", "escenarios.json")
        self.assertIn("✖ Al menos un modelo de monetización viable con evidencia · ninguno: Anuncios · banner "
                      "(estimación: sin fuente en MX.anuncios.banner.impresiones_por_dau)", self.p("puerta", "--n", 2))

    def test_un_modelo_que_no_genera_ingresos_no_es_viable(self):
        self.hasta_puerta2()
        self.escenarios(dau=0)
        self.assertIn("no genera ingresos en el caso base", self.p("puerta", "--n", 2))

    def test_unos_escenarios_de_una_version_anterior_piden_recalcular(self):
        self.hasta_puerta2()
        datos = self.datos()
        del datos["escenarios"]["modelos"]
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.assertIn("los escenarios son de una versión anterior: vuelve a correr `escenarios`",
                      self.p("puerta", "--n", 2))

    def test_sin_meta_los_escenarios_no_avisan_ni_comparan(self):
        self.hasta_puerta2()
        self.p("criterio", "--clave", "meta_ingresos_mes", "--valor", 0, "--motivo", "El usuario no quiere meta")
        salida = self.escenarios()
        self.assertIn("Sin meta de ingresos: es opcional.", salida)
        self.assertNotIn("⚠ No hay meta", salida)
        self.assertNotIn("Meta de ingresos (referencial", self.p("puerta", "--n", 2))


# --- #8 · Una sola regla para la confianza y la triangulación ------------------------------------------------------

class ReglaUnicaTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def test_una_fuente_sin_fecha_no_cuenta_para_ninguna_de_las_dos(self):
        fuentes = self.fuente("voz-del-usuario", 2, "usuario") + self.fuente("voz-del-usuario", 1, "usuario",
                                                                             publicada="sin-fecha")
        hallazgo, salida = self.hallazgo("voz-del-usuario", fuentes, "--critico", "--sin-contra", "Nada")
        self.assertIn("confianza media · sin triangular", salida)
        self.assertIn("%s sin fecha o fuera de la ventana de 18 meses: no cuenta(n) para la confianza ni para "
                      "triangular" % fuentes[2], salida)
        salida = self.p("triangulacion")
        self.assertIn("✖ %s · confianza media · sin triangular" % hallazgo, salida)
        self.assertIn("→ %s sin fecha o fuera de la ventana de 18 meses: no cuenta(n)" % fuentes[2], salida)
        self.assertIn("0 de 1 hallazgos clave triangulados (regla 2)", salida)

    def test_con_tres_vigentes_una_sin_fecha_no_impide_triangular(self):
        fuentes = self.fuente("voz-del-usuario", 3, "usuario") + self.fuente("voz-del-usuario", 1, "usuario",
                                                                             publicada="sin-fecha")
        hallazgo, salida = self.hallazgo("voz-del-usuario", fuentes, "--critico", "--sin-contra", "Nada")
        self.assertIn("confianza alta · triangulado", salida)
        salida = self.p("triangulacion")
        self.assertIn("✔ %s · confianza alta · triangulado" % hallazgo, salida)
        self.assertIn("no cuenta(n), y no hace falta", salida)

    def test_solo_fuentes_sin_fecha_queda_en_baja(self):
        fuentes = self.fuente("voz-del-usuario", 3, "usuario", publicada="sin-fecha")
        self.assertIn("confianza baja · sin triangular", self.hallazgo("voz-del-usuario", fuentes)[1])

    def test_la_busqueda_en_contra_es_otra_regla_y_no_cambia_la_triangulacion(self):
        hallazgo, salida = self.hallazgo("competencia", self.fuente("competencia", 3), "--critico")
        self.assertIn("Falta registrar la búsqueda de evidencia en contra (regla 4)", salida)
        salida = self.p("triangulacion")
        self.assertIn("✔ %s · confianza alta · triangulado" % hallazgo, salida)
        self.assertIn("→ regla 4: falta registrar la búsqueda de evidencia en contra", salida)
        self.assertIn("1 de 1 hallazgos clave triangulados (regla 2) · 1 sin la búsqueda en contra (regla 4)", salida)

    def test_la_confianza_alta_siempre_viene_triangulada(self):
        registro_de = lambda: base.producto.Registro(self.carpeta, self.datos()["criterios"])
        combinaciones = []
        for linea in ("voz-del-usuario", "demanda"):
            for tipos in (("usuario",) * 3, ("opinion",) * 3, ("usuario", "medido", "opinion"), ("usuario",) * 2):
                for publicada in ("2026-06", "sin-fecha", "2020-01"):
                    fuentes = []
                    for tipo in tipos:
                        fuentes += self.fuente(linea, 1, tipo, publicada=publicada)
                    combinaciones.append(self.hallazgo(linea, fuentes)[0])
        registro = registro_de()
        for identificador in combinaciones:
            evaluacion = registro.evaluar(registro.hallazgos[identificador])
            if evaluacion["nivel"] == 3:
                self.assertTrue(evaluacion["triangulado"], identificador)
            if not evaluacion["independientes"]:
                self.assertLessEqual(evaluacion["nivel"], 1, identificador)


# --- #4 · El diferenciador es viable solo con sus hallazgos triangulados -------------------------------------------

class DiferenciadorTrianguladoTest(Base):
    def test_sin_triangular_es_viable_con_confianza_baja(self):
        debil, salida = self.principal_baja()
        self.assertIn("⚠ D-1 registrado como principal: viable con confianza baja", salida)
        self.assertIn("✔ Evidencia: vector medible comprobado en la matriz", salida)
        self.assertIn("✖ Hallazgos triangulados (regla 2): sin triangular %s" % debil, salida)
        self.assertIn("no cuenta como viable para la puerta 1", salida)
        self.assertIn("(0 viables, 1 con confianza baja; principal: D-1)", self.p("estado"))

    def test_la_puerta_1_exige_el_principal_triangulado(self):
        debil, _ = self.principal_baja()
        salida = self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.assertIn("⚠ No hay ningún diferenciador viable (D-1, con confianza baja: sin triangular)", salida)
        self.assertIn("⚠ Los hallazgos del diferenciador principal (D-1) no están triangulados", salida)
        self.assertIn("Diferenciación = 3 no corresponde", self.falla("puntaje", "--valores", "4,4,4,4,3"))
        self.p("puntaje", "--valores", "4,4,4,4,2")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✖ Al menos 1 diferenciador viable, con sus hallazgos triangulados · 0 viable(s), 1 con "
                      "confianza baja de 1 registrado(s)", salida)
        self.assertIn("✖ Los hallazgos del diferenciador principal están triangulados · D-1: %s sin triangular "
                      "(faltan 1 fuente(s) independiente(s) y vigente(s) (tiene 2 de 3))" % debil, salida)

    def test_otro_viable_no_reemplaza_al_principal_sin_triangular(self):
        self.principal_baja()
        voz = "H-VOZ-1"  # el de la línea 1b, triangulado en dos competidores
        self.p("diferenciador", "--vector", "usabilidad", "--texto", "Turnos en tres toques", "--hallazgos", voz,
               "--se-ve", "uso", "--copiable", "media", "--motivo", "Rehacer el flujo les cuesta", "--semanas", 2)
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("✔ Al menos 1 diferenciador viable, con sus hallazgos triangulados · 1 viable(s), 1 con "
                      "confianza baja de 2 registrado(s)", salida)
        self.assertIn("✖ Los hallazgos del diferenciador principal están triangulados · D-1", salida)

    def test_la_puerta_1_avisa_la_confianza_global_baja(self):
        self.principal_baja()
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("confianza", "--hallazgo", "H-DEM-1", "--bajar", "baja", "--motivo", "Solo un trimestre de datos")
        self.p("puntaje", "--valores", "4,4,4,4,2")
        self.assertIn("⚠ No lo pases por alto: la confianza global es baja", self.p("puerta", "--n", 1))


# --- #9 · La puerta dentro de `siguiente`, y los cambios a una sesión cerrada como propuesta ------------------------

class PuertaYPropuestaTest(Base):
    def test_siguiente_trae_el_veredicto_sin_un_paso_aparte(self):
        self.hasta_puerta1()
        salida = self.p("siguiente")
        self.assertIn("Puerta 1 · Oportunidad · idea existente · cumple 5 de 5 criterios", salida)
        self.assertIn("  ✔ Puntaje de 17/25 o más · tiene 19/25", salida)
        self.assertIn("Terminal · La decisión es tuya (el agente nunca corre este comando). Elige uno:", salida)
        self.assertNotIn("puerta --n", salida)
        estado = (self.carpeta / "estado.md").read_text(encoding="utf-8")
        self.assertIn("cumple 5 de 5 criterios", estado)

    def test_con_1g_cerrada_el_principal_no_se_cambia_con_un_comando_suelto(self):
        self.hasta_puerta1()
        error = self.falla("principal", "--id", "D-1")
        self.assertIn("es trabajo de la sesión 1g, que ya cerró", error)
        self.assertIn("propuesta --texto", error)
        self.assertIn("puerta 1", error)
        self.assertIn("ya cerró", self.falla("diferenciador", "--vector", "precio", "--texto", "Otro", "--hallazgos",
                                             "H-VOZ-1", "--se-ve", "ficha", "--copiable", "baja", "--motivo", "x",
                                             "--semanas", 1))
        self.assertIn("ya cerró", self.falla("anular", "--id", "D-1", "--motivo", "Ya no aplica"))

    def test_la_propuesta_se_ve_en_la_puerta_y_la_resuelve_la_decision(self):
        self.hasta_puerta2()
        self.assertIn("lleva una sesión anterior a la puerta 2", self.falla(
            "propuesta", "--texto", "x", "--ajustar", "4"))
        salida = self.p("propuesta", "--texto", "Cambiar el principal a uno de privacidad", "--ajustar", "1g",
                        "--sesion", "2")
        self.assertIn("✔ PR-1 registrada para la puerta 2", salida)
        salida = self.p("siguiente")
        self.assertIn("· Propuesta PR-1 (sesión 2): Cambiar el principal a uno de privacidad → se aplica con "
                      "Ajustar 1g", salida)
        self.assertIn("   Ajustar 1g: cd %s && python3 -I" % self.tmp, salida)
        self.assertIn("decidir --puerta 2 --ajustar 1g --carpeta product", salida)
        self.p("decidir", "--puerta", 2, "--ajustar", "1g")
        propuesta = self.datos()["propuestas"][0]
        self.assertEqual(propuesta["estado"], "ajustar 1g")
        self.assertEqual(self.datos("decisiones.json")[-1]["propuestas"], ["PR-1"])
        self.assertNotIn("Propuesta PR-1", self.p("siguiente"))
        self.assertIn("✔ D-1 es el diferenciador principal", self.p("principal", "--id", "D-1"))

    def test_principal_elige_otro_con_1g_abierta(self):
        self.principal_baja()
        self.p("diferenciador", "--vector", "usabilidad", "--texto", "Turnos en tres toques", "--hallazgos",
               "H-VOZ-1", "--se-ve", "uso", "--copiable", "media", "--motivo", "Rehacer el flujo les cuesta",
               "--semanas", 2)
        salida = self.p("principal", "--id", "D-2")
        self.assertIn("✔ D-2 es el diferenciador principal (antes: D-1)", salida)
        self.assertIn("✔ D-2 (principal): viable", salida)
        self.assertIn("No existe el diferenciador D-9", self.falla("principal", "--id", "D-9"))
        principales = [d["id"] for d in self.datos("01-investigacion/diferenciacion.json")["diferenciadores"]
                       if d["principal"]]
        self.assertEqual(principales, ["D-2"])


# --- #5 y #7 · Cobertura por mercado, idioma y tienda; vacíos de herramienta ----------------------------------------

class CoberturaTest(Base):
    def setUp(self):
        super().setUp()
        self.p("nuevo", "--nombre", "Riego en turnos", "--semanas", 6, "--mercados", "MX,ES", "--idiomas", "es,pt",
               "--tiendas", "google-play,app-store")
        self.completar("criterios.md")
        self.cerrar("0", "00-idea.md")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")

    def test_cobertura_lista_lo_que_falta_y_la_linea_no_cierra_sin_registrarlo(self):
        fuentes = [self.fuente("voz-del-usuario", 1, "usuario", cobertura=False)[0] for _ in range(3)]
        self.p("fuente", "--linea", "voz-del-usuario", "--url", "https://sitio1.example/pagina-1", "--publicada",
               "2026-06", "--tipo", "usuario", "--peldano", 1, "--resumen", "x", "--idiomas", "es",
               "--tiendas", "app-store")
        self.hallazgo("voz-del-usuario", fuentes)
        salida = self.p("cobertura", "--linea", "voz-del-usuario")
        self.assertIn("✔ idioma es · %s" % fuentes[0], salida)
        self.assertIn("✖ idioma pt · sin fuentes ni vacío registrado", salida)
        self.assertIn("✖ tienda google-play · sin fuentes ni vacío registrado", salida)
        self.assertIn("✔ tienda app-store", salida)
        error = self.falla("cerrar", "--sesion", "1b")
        self.assertIn("cobertura de la línea voz-del-usuario sin fuentes ni vacío registrado: idioma pt, tienda "
                      "google-play", error)
        salida = self.p("vacio", "--linea", "voz-del-usuario", "--tienda", "google-play", "--motivo", "herramienta",
                        "--texto", "Las reseñas se cargan con JavaScript y la lectura web no las ve")
        self.assertIn("✔ V-VOZ-1 registrado", salida)
        self.assertIn("ajustar la línea con las mismas herramientas no lo resuelve", salida)
        self.p("vacio", "--linea", "voz-del-usuario", "--idioma", "pt", "--motivo", "sin-resultados", "--texto",
               "Se buscó en portugués y no apareció nada del tema")
        self.completar("01-investigacion/voz-del-usuario.md")
        self.p("cerrar", "--sesion", "1b")
        salida = self.p("cobertura", "--linea", "voz-del-usuario")
        self.assertIn("⚠ tienda google-play · vacío, límite de las herramientas (V-VOZ-1)", salida)
        self.assertIn("vacío(s)", self.p("estado"))

    def test_volver_a_registrar_la_url_agrega_su_cobertura(self):
        args = ["fuente", "--linea", "demanda", "--url", "https://datos.example/informe", "--publicada", "2026-06",
                "--tipo", "medido", "--peldano", 1, "--resumen", "x"]
        self.assertIn("Sin etiquetas de cobertura", self.p(*args))
        self.assertIn("se le agregó la cobertura MX", self.p(*args, "--mercados", "MX"))
        self.assertEqual(self.datos("01-investigacion/demanda.json")["fuentes"][0]["mercados"], ["MX"])

    def test_el_vacio_se_valida_contra_el_objetivo_y_la_linea(self):
        self.assertIn("no está en el objetivo", self.falla("vacio", "--linea", "demanda", "--mercado", "AR",
                                                           "--motivo", "presupuesto", "--texto", "x"))
        self.assertIn("no pide cobertura por tienda", self.falla("vacio", "--linea", "demanda", "--tienda",
                                                                 "app-store", "--motivo", "presupuesto",
                                                                 "--texto", "x"))
        self.assertIn("un solo valor", self.falla("vacio", "--linea", "demanda", "--mercado", "MX", "--idioma", "es",
                                                  "--motivo", "presupuesto", "--texto", "x"))
        self.assertIn("no tiene cobertura", self.falla("vacio", "--linea", "diferenciacion", "--mercado", "MX",
                                                       "--motivo", "presupuesto", "--texto", "x"))
        self.p("vacio", "--linea", "demanda", "--mercado", "MX", "--motivo", "presupuesto", "--texto", "x")
        self.assertIn("V-DEM-1 anulado", self.p("anular", "--id", "V-DEM-1", "--motivo", "Ya hay fuente"))
        self.assertIn("✖ mercado MX", self.p("cobertura", "--linea", "demanda"))

    def test_el_objetivo_se_fija_en_la_sesion_0_y_su_cambio_queda_a_la_vista(self):
        self.assertIn("mercados MX, ES · idiomas es, pt · tiendas google-play, app-store", self.p("objetivo"))
        self.assertIn("exige --motivo", self.falla("objetivo", "--mercados", "MX"))
        self.p("objetivo", "--mercados", "MX", "--motivo", "España queda para después")
        self.assertEqual(self.datos()["objetivo"]["mercados"], ["MX"])
        self.assertIn("· Criterio cambiado después de la sesión 0: objetivo", self.p("puerta", "--n", 1))

    def test_sin_tiendas_ninguna_linea_pide_cobertura_por_tienda(self):
        self.p("objetivo", "--tiendas", "ninguna", "--motivo", "Es una app web")
        salida = self.p("cobertura")
        self.assertNotIn("tienda ", salida.split("\n", 1)[1])
        self.assertIn("tiendas ninguna", salida)

    def test_la_puerta_1_muestra_los_huecos_y_los_vacios_de_herramienta(self):
        self.p("vacio", "--linea", "voz-del-usuario", "--tienda", "google-play", "--motivo", "herramienta",
               "--texto", "Página dinámica")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("⚠ Cobertura sin fuentes ni vacío registrado: competencia · mercado MX", salida)
        self.assertIn("· Vacíos por límite de las herramientas: voz-del-usuario · tienda google-play. Ajustar esas "
                      "líneas con las mismas herramientas no los resuelve", salida)



class AjusteConVacioTest(Base):
    def test_ajustar_una_linea_con_vacios_de_herramienta_avisa(self):
        self.hasta_puerta1()
        for fuente in self.datos("01-investigacion/voz-del-usuario.json")["fuentes"]:  # sin google-play en 1b
            self.p("anular", "--id", fuente["id"], "--motivo", "Prueba sin la tienda")
        self.p("vacio", "--linea", "voz-del-usuario", "--tienda", "google-play", "--motivo", "herramienta",
               "--texto", "Página dinámica")
        salida = self.p("decidir", "--puerta", 1, "--ajustar", "1b")
        self.assertIn("⚠ voz-del-usuario tiene vacíos por límite de las herramientas (tienda google-play)", salida)
        self.assertIn("dale al agente un navegador o consigue un CSV de reseñas", salida)
        self.assertNotIn("vacíos por límite", self.p("decidir", "--puerta", 1, "--ajustar", "1c"))
        self.fuente("voz-del-usuario", 1, "usuario")  # una fuente de google-play lo cubre: el vacío ya no cuenta
        self.assertNotIn("Vacíos por límite", self.p("puerta", "--n", 1))


# --- #7 · CSV de reseñas que aporta el usuario ----------------------------------------------------------------------

class CsvTest(Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def registrar(self, ruta, *extra):
        return self.p("fuente", "--linea", "voz-del-usuario", "--archivo", ruta, "--tipo", "usuario", "--peldano", 1,
                      "--resumen", "Reseñas exportadas por el usuario", *extra)

    def test_un_csv_se_registra_como_fuente_con_su_fecha_y_sus_idiomas(self):
        ruta = self.csv()
        self.assertIn("necesita --autor", self.falla("fuente", "--linea", "voz-del-usuario", "--archivo", ruta,
                                                     "--publicada", "auto", "--tipo", "usuario", "--peldano", 1,
                                                     "--resumen", "x"))
        salida = self.registrar(ruta, "--autor", "RiegoFácil · Google Play", "--publicada", "auto", "--tiendas",
                                "google-play")
        self.assertIn("✔ S-VOZ-1 registrada", salida)
        self.assertIn("4 fila(s) · del 2026-08-01 al 2026-11-10 · 1–3★: 3 · idiomas: es (3), pt (1)", salida)
        self.assertIn("· Cobertura: idioma es, pt · tienda google-play", salida)
        fuente = self.datos("01-investigacion/voz-del-usuario.json")["fuentes"][0]
        self.assertEqual((fuente["publicada"], fuente["idiomas"], fuente["dominio"]),
                         ("2026-11-10", ["es", "pt"], "archivo:riegofacil-google-play"))
        self.assertNotIn("Persona Inventada", json.dumps(fuente, ensure_ascii=False))
        self.assertIn("no se duplica", self.registrar(ruta, "--autor", "RiegoFácil · Google Play", "--publicada",
                                                      "auto"))

    def test_dos_csv_de_la_misma_app_cuentan_como_una_fuente(self):
        uno = self.registrar(self.csv("a.csv"), "--autor", "RiegoFácil · Google Play", "--publicada", "auto")
        dos = self.registrar(self.csv("b.csv"), "--autor", "RiegoFácil · Google Play", "--publicada", "auto")
        tres = self.registrar(self.csv("c.csv"), "--autor", "PlantaPlus · Google Play", "--publicada", "auto")
        ids = [re.search(r"S-VOZ-\d+", texto).group(0) for texto in (uno, dos, tres)]
        _, salida = self.hallazgo("voz-del-usuario", ids)
        self.assertIn("2 fuente(s) independiente(s) y vigente(s)", salida)

    def test_valida_la_url_o_el_archivo_y_la_fecha_automatica(self):
        comun = ["fuente", "--linea", "voz-del-usuario", "--tipo", "usuario", "--peldano", 1, "--resumen", "x"]
        self.assertIn("una de las dos", self.falla(*comun, "--publicada", "2026-06"))
        self.assertIn("una de las dos", self.falla(*comun, "--publicada", "2026-06", "--url", "https://a.example",
                                                   "--archivo", self.csv(), "--autor", "A"))
        self.assertIn("solo sirve con --archivo", self.falla(*comun, "--publicada", "auto", "--url",
                                                             "https://a.example"))
        sin_fecha = self.csv("sin-fecha.csv", "rating,review\n2,Lenta\n")
        self.assertIn("no tiene una columna de fecha", self.falla(*comun, "--archivo", sin_fecha, "--autor", "A",
                                                                  "--publicada", "auto"))
        self.assertIn("✔ S-VOZ-1", self.p(*comun, "--archivo", sin_fecha, "--autor", "A", "--publicada", "2026-06"))
        raro = self.csv("raro.csv", "nombre,correo\nx,y\n")
        self.assertIn("no tiene una columna de texto ni de estrellas", self.falla(*comun, "--archivo", raro, "--autor",
                                                                                  "A", "--publicada", "2026-06"))
        self.assertIn("No existe el archivo", self.falla(*comun, "--archivo", self.tmp / "no.csv", "--autor", "A",
                                                         "--publicada", "2026-06"))

    def test_resenas_muestra_las_de_pocas_estrellas_sin_autores(self):
        ruta = self.csv()
        salida = self.p("resenas", "--archivo", ruta)
        self.assertNotIn("Persona Inventada", salida)
        self.assertNotIn("Funciona bien", salida)  # 5★
        lineas = [linea for linea in salida.splitlines() if linea.startswith("- ")]
        self.assertEqual(lineas, ["- 2026-11-10 · 2★ · es · Muy cara la suscripción para lo que hace",
                                  "- 2026-10-02 · 1★ · es · Se cierra cada vez que agrego un vecino",
                                  "- 2026-08-01 · 3★ · pt · Não tem lembrete por turno"])
        self.assertIn("Columnas usadas: fecha = Review Submit Date and Time", salida)
        salida = self.p("resenas", "--archivo", ruta, "--idioma", "pt", "--estrellas", "3")
        self.assertIn("1 de 1 reseña(s)", salida)
        self.assertIn("2 de 3 reseña(s) con esos filtros (sube --limite", self.p("resenas", "--archivo", ruta,
                                                                                  "--limite", 2))
        self.assertIn("1 de 1", self.p("resenas", "--archivo", ruta, "--desde", "2026-11-01"))
        self.assertIn("rango de 1 a 5", self.falla("resenas", "--archivo", ruta, "--estrellas", "0-9"))

    def test_lee_csv_con_punto_y_coma_bom_y_textos_largos(self):
        largo = "palabra " * 60
        ruta = self.csv("pc.csv", "﻿fecha;estrellas;texto\n2026/05/03;1;%s\n" % largo)
        salida = self.p("resenas", "--archivo", ruta)
        self.assertIn("- 2026-05-03 · 1★ · — · ", salida)
        self.assertIn("…", salida)
        self.assertLess(max(len(linea) for linea in salida.splitlines() if linea.startswith("- ")), 240)


# --- #6 · Consumo por sesión, también con subagentes ---------------------------------------------------------------

class ConsumoTest(Base):
    def setUp(self):
        super().setUp()
        self.sesion0()

    def test_anota_actualiza_y_suma_en_usd(self):
        self.assertNotIn("Consumo sin anotar", self.p("siguiente"))  # solo después de anotar el primero
        salida = self.p("consumo", "--sesion", "0", "--costo", "0.40", "--modelo", "Sonnet 5.5")
        self.assertIn("✔ Consumo de 0: 0,40 USD · total anotado: 0,40 USD", salida)
        self.p("consumo", "--sesion", "0", "--tokens", "45k", "--pasos", 20)
        self.p("consumo", "--sesion", "1a", "--creditos", "12.5")
        filas = self.datos()["consumo"]
        self.assertEqual(len(filas), 2)
        self.assertEqual((filas[0]["costo"], filas[0]["tokens"], filas[0]["pasos"]), (0.4, 45000, 20))
        salida = self.p("consumo")
        self.assertIn("Total: 0,53 USD", salida)
        self.assertIn("0,40 USD, 45 000 tokens, 20 pasos", salida)
        self.assertIn("Consumo anotado:** 0 0,40 USD", (self.carpeta / "estado.md").read_text(encoding="utf-8"))

    def test_el_orquestador_cubre_las_sesiones_de_sus_subagentes(self):
        self.p("consumo", "--sesion", "0", "--costo", "0.20")
        self.investigacion_parcial()
        self.assertIn("Consumo sin anotar (opcional): 1a, 1b", self.p("siguiente"))
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1a,1b", "--costo", "1.10", "--tokens", "300k")
        self.assertNotIn("Consumo sin anotar", self.p("siguiente"))
        self.assertIn("--incluye lleva sesiones", self.falla("consumo", "--sesion", "orquestador", "--incluye", "9",
                                                            "--costo", "1"))

    def investigacion_parcial(self):
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0])
        self.sustituto(fuentes[1])
        self.hallazgo("competencia", fuentes)
        self.cerrar("1a", "01-investigacion/competencia.md")
        self.linea("1b", "voz-del-usuario", "usuario")

    def test_rechaza_un_costo_mutilado_por_el_shell_y_lo_que_no_es_una_sesion(self):
        error = self.falla("consumo", "--sesion", "0", "--costo=-bash.40")
        self.assertIn("comillas simples", error)
        self.assertIn("comillas simples", self.falla("consumo", "--sesion", "0", "--costo", "zsh.40"))
        self.assertIn("debe ser un número", self.falla("consumo", "--sesion", "0", "--costo", "mucho"))
        self.assertIn("u orquestador", self.falla("consumo", "--sesion", "9z", "--costo", "1"))
        self.assertIn("Anota al menos", self.falla("consumo", "--sesion", "0"))
        self.assertIn("--tokens debe ser un número", self.falla("consumo", "--sesion", "0", "--tokens", "muchos"))
        self.assertIn("--pasos debe ser un número", self.falla("consumo", "--sesion", "0", "--costo", "1",
                                                               "--pasos", "veinte"))
        self.assertIn("0,40 USD", self.p("consumo", "--sesion", "0", "--costo", "$0,40"))


# --- Documentación ---------------------------------------------------------------------------------------------------

# --- #10 · Fuente oficial ------------------------------------------------------------------------------------------

class FuenteOficialTest(Base):
    def oficial(self, linea="politicas", *extra):
        self.sitio += 1
        salida = self.p("fuente", "--linea", linea, "--url", "https://tienda.example/politicas-%d" % self.sitio,
                        "--publicada", "2025-03", "--tipo", "oficial", "--peldano", 1, "--autor", "Tienda de ejemplo",
                        "--resumen", "Política inventada de la tienda", "--mercados", "MX", "--tiendas", "google-play",
                        *extra)
        return re.search(r"S-[A-Z]{3}-\d+", salida).group(0), salida

    def test_una_fuente_oficial_basta_para_un_hallazgo_de_politicas(self):
        self.nuevo()
        fuente, salida = self.oficial()
        self.assertIn("basta sola para un hallazgo de la línea politicas", salida)
        identificador, salida = self.hallazgo("politicas", [fuente], "--critico", "--sin-contra", "nada")
        self.assertIn("confianza alta · triangulado", salida)
        self.assertIn("Triangulado por la fuente oficial %s" % fuente, salida)
        salida = self.p("triangulacion")
        self.assertIn("✔ %s" % identificador, salida)
        self.assertIn("triangulado por la fuente oficial", salida)

    def test_rige_mientras_se_consulte_dentro_de_la_ventana(self):
        self.nuevo()
        fuente = re.search(r"S-POL-\d+", self.p(
            "fuente", "--linea", "politicas", "--url", "https://tienda.example/guia", "--publicada", "2019-06",
            "--tipo", "oficial", "--peldano", 1, "--resumen", "Guía inventada de 2019, todavía vigente")).group(0)
        self.assertIn("confianza alta · triangulado", self.hallazgo("politicas", [fuente])[1])
        vieja = re.search(r"S-POL-\d+", self.p(
            "fuente", "--linea", "politicas", "--url", "https://tienda.example/guia-vieja", "--publicada", "2019-06",
            "--consultada", "2020-01-10", "--tipo", "oficial", "--peldano", 1, "--resumen", "Leída hace años")).group(0)
        self.assertIn("sin triangular", self.hallazgo("politicas", [vieja])[1])

    def test_fuera_de_politicas_no_basta_y_lleva_version_o_fecha(self):
        self.nuevo()
        fuente, _ = self.oficial("demanda")
        self.assertIn("sin triangular", self.hallazgo("demanda", [fuente])[1])
        error = self.falla("fuente", "--linea", "politicas", "--url", "https://tienda.example/x", "--publicada",
                           "desconocida", "--tipo", "oficial", "--peldano", 1, "--resumen", "Sin versión")
        self.assertIn("--version", error)
        salida = self.p("fuente", "--linea", "politicas", "--url", "https://tienda.example/x", "--publicada",
                        "desconocida", "--version", "versión de junio de 2025", "--tipo", "oficial", "--peldano", 1,
                        "--resumen", "Con versión")
        self.assertIn("versión de junio de 2025", salida)
        self.assertIn("es para una fuente oficial", self.falla(
            "fuente", "--linea", "politicas", "--url", "https://tienda.example/y", "--publicada", "2025-01",
            "--version", "1.0", "--tipo", "terceros", "--peldano", 1, "--resumen", "x"))


# --- #11 · El sustituto más fuerte ---------------------------------------------------------------------------------

class SustitutoTest(Base):
    def investigar(self, resuelve="si", supera=False):
        """Hasta 1g con un sustituto nativo (la función del sistema) y un diferenciador de precio. Con supera=True, el
        dolor triangulado de la voz del usuario nombra también al sustituto."""
        self.sesion0()
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--descargas", "1M",
               "--precio", "3,99 al mes")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[1], "--descargas", "500k",
               "--precio", "2,99 al mes")
        salida = self.sustituto(fuentes[2], "Recordatorio del sistema", "nativo", resuelve)
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "nada")
        self.cerrar("1a", "01-investigacion/competencia.md")
        nombres = "RiegoFácil,PlantaPlus" + (",Recordatorio del sistema" if supera else "")
        voz = self.linea("1b", "voz-del-usuario", "usuario", 1, "--competidores", nombres)
        for sesion, nombre in (("1c", "demanda"), ("1d", "monetizacion"), ("1e", "politicas")):
            self.linea(sesion, nombre)
        return salida, self.p("diferenciador", "--vector", "precio", "--texto", "Pago único", "--hallazgos", voz,
                              "--se-ve", "ficha", "--copiable", "media", "--motivo", "Les cuesta el ingreso recurrente",
                              "--semanas", 2, "--principal")

    def test_un_sustituto_nativo_que_resuelve_deja_al_diferenciador_sin_viabilidad(self):
        fila, salida = self.investigar()
        self.assertIn("Es gratuito o nativo y ya resuelve la necesidad", fila)
        self.assertIn("✖ D-1 registrado como principal: todavía no es viable", salida)
        self.assertIn("✖ Frente al sustituto: no supera a C-3 (Recordatorio del sistema), viene con el sistema y "
                      "resuelve la necesidad", salida)
        self.assertIn("Sustituto gratuito o nativo que ya resuelve la necesidad: C-3", self.p("matriz"))
        self.assertIn("Ningún diferenciador supera a C-3", self.cerrar("1g", "01-investigacion/diferenciacion.md"))
        self.assertIn("Diferenciación = 3 no corresponde", self.falla("puntaje", "--valores", "4,4,4,4,3"))
        self.p("puntaje", "--valores", "4,4,4,4,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✖ Al menos 1 diferenciador viable, con sus hallazgos triangulados y que supere al sustituto "
                      "gratuito o nativo que ya resuelve la necesidad (C-3 (Recordatorio del sistema))", salida)
        self.assertIn("ningún diferenciador supera a C-3", salida)

    def test_lo_supera_con_un_hallazgo_triangulado_que_lo_nombra(self):
        _, salida = self.investigar(supera=True)
        self.assertIn("✔ D-1 registrado como principal: viable", salida)
        self.assertIn("✔ Frente al sustituto: supera a C-3 (Recordatorio del sistema) con H-VOZ-1", salida)
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        self.assertIn("✔ Al menos 1 diferenciador viable", self.cerrar("1f", "01-sintesis.md"))

    def test_un_sustituto_que_resuelve_en_parte_no_obliga(self):
        _, salida = self.investigar(resuelve="parcial")
        self.assertIn("✔ D-1 registrado como principal: viable", salida)
        self.assertIn("ninguno gratuito o nativo resuelve la necesidad (C-3 la resuelve en parte)", salida)

    def test_1a_no_cierra_sin_un_sustituto_evaluado(self):
        self.sesion0()
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay apps directas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0])
        self.hallazgo("competencia", fuentes)
        self.completar("01-investigacion/competencia.md")
        self.assertIn("la matriz no tiene ningún sustituto (peldaño 4)", self.falla("cerrar", "--sesion", "1a"))
        self.assertIn("son de un sustituto (--peldano 4)", self.falla(
            "competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--sustituto", "nativo"))
        self.p("competidor", "--nombre", "Lista en papel", "--peldano", 4, "--fuentes", fuentes[1])
        self.assertIn("C-2 (Lista en papel) es un sustituto: le falta", self.falla("cerrar", "--sesion", "1a"))
        salida = self.p("competidor", "--nombre", "Lista en papel", "--peldano", 4, "--fuentes", fuentes[1],
                        "--sustituto", "gratuito", "--resuelve", "no")
        self.assertIn("· Sustituto: C-2 (Lista en papel), gratuito y no la resuelve", salida)
        self.assertIn("Sesión 1a · Competencia cerrada", self.p("cerrar", "--sesion", "1a"))
        self.assertIn("4 · gratuito · no la resuelve", self.p("matriz"))

    def test_un_sustituto_sin_evaluar_no_pasa_en_silencio(self):
        self.investigar(resuelve="parcial")
        datos = self.datos("01-investigacion/competencia.json")
        for fila in datos["matriz"]:
            fila.pop("resuelve", None)  # como una carpeta anterior a esta regla
        write(self.carpeta / "01-investigacion/competencia.json", json.dumps(datos))
        salida = self.p("principal", "--id", "D-1")
        self.assertIn("✖ Frente al sustituto: C-3 (Recordatorio del sistema) sin evaluar", salida)


# --- #12 · Una tienda que nombra o rechaza la categoría --------------------------------------------------------------

class BloqueoTiendaTest(Base):
    def bloqueo(self):
        self.investigacion()
        fuente = re.search(r"S-POL-\d+", self.p(
            "fuente", "--linea", "politicas", "--url", "https://tienda.example/categorias-saturadas", "--publicada",
            "2025-06", "--tipo", "oficial", "--peldano", 1, "--resumen", "La tienda inventada nombra la categoría",
            "--tiendas", "google-play")).group(0)
        identificador, salida = self.hallazgo("politicas", [fuente], "--critico", "--sin-contra", "nada",
                                              "--bloquea", "google-play")
        return identificador, salida

    def test_el_hallazgo_bloqueante_fija_el_riesgo_en_1(self):
        identificador, salida = self.bloqueo()
        self.assertIn("⚠ Bloqueante en google-play", salida)
        self.assertIn("bloqueante en google-play", self.p("triangulacion"))
        error = self.falla("puntaje", "--valores", "4,4,4,2,3")
        self.assertIn("Riesgo de políticas = 2 no corresponde: google-play nombra o rechaza la categoría (%s)"
                      % identificador, error)
        self.p("puntaje", "--valores", "4,4,4,1,3")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✖ Riesgo de políticas distinto de 1, o con una mitigación escrita · es 1 · bloqueante en "
                      "google-play nombra o rechaza la categoría", salida)
        self.p("puntaje", "--valores", "4,4,4,1,3", "--mitigacion", "Lanzar solo en la web hasta tener otra propuesta")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("✔ Riesgo de políticas distinto de 1", salida)
        self.assertIn("mitigación: «Lanzar solo en la web hasta tener otra propuesta»", salida)

    def test_un_puntaje_anterior_al_bloqueo_no_pasa_la_puerta(self):
        self.investigacion()
        self.p("puntaje", "--valores", "4,4,4,4,3")
        self.cerrar("1f", "01-sintesis.md")
        fuente = self.fuente("politicas", 1, "oficial")[0]
        self.hallazgo("politicas", [fuente], "--bloquea", "google-play")
        self.assertIn("el puntaje dice 4, pero google-play nombra o rechaza la categoría", self.p("puerta", "--n", 1))

    def test_bloquea_es_de_politicas_y_de_una_tienda_del_objetivo(self):
        self.nuevo()
        fuente = self.fuente("politicas")[0]
        self.assertIn("es de la línea politicas", self.falla(
            "hallazgo", "--linea", "demanda", "--texto", "x", "--fuentes", fuente, "--bloquea", "google-play"))
        self.assertIn("app-store no está entre las tiendas del objetivo", self.falla(
            "hallazgo", "--linea", "politicas", "--texto", "x", "--fuentes", fuente, "--bloquea", "app-store"))


# --- #13 · Demanda con señales actuales ------------------------------------------------------------------------------

class DemandaActualTest(Base):
    def test_un_dato_acumulado_no_triangula_la_demanda(self):
        self.nuevo()
        fuentes = self.fuente("demanda", 2, "usuario")
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://tienda.example/ficha", "--publicada",
                        "2026-06", "--tipo", "medido", "--acumulado", "--peldano", 1, "--resumen",
                        "Mil millones de descargas desde 2011", "--mercados", "MX")
        self.assertIn("Dato acumulado", salida)
        acumulada = re.search(r"S-DEM-\d+", salida).group(0)
        identificador, salida = self.hallazgo("demanda", fuentes + [acumulada], "--critico", "--sin-contra", "nada")
        self.assertIn("sin triangular", salida)
        salida = self.p("triangulacion")
        self.assertIn("%s: dato(s) acumulado(s)" % acumulada, salida)
        self.assertIn("falta una fuente de tipo medido", salida)
        # en otra línea, el mismo dato acumulado sí cuenta: es contexto de la competencia
        self.assertIn("triangulado", self.hallazgo("competencia", self.fuente("competencia", 2) + [acumulada])[1])

    def test_las_anclas_altas_de_demanda_piden_un_hallazgo_triangulado(self):
        self.sesion0()
        self.p("tipo", "--existente", "--motivo", "Hay apps directas")
        self.hallazgo("demanda", self.fuente("demanda", 2, "usuario"), "--critico", "--sin-contra", "nada")
        error = self.falla("puntaje", "--valores", "4,3,3,3,1")
        self.assertIn("Demanda = 4 no corresponde: las anclas 4 y 5 piden señales actuales", error)
        self.assertIn("Total: 13/25", self.p("puntaje", "--valores", "3,3,3,3,1"))

    def test_acumulado_es_un_dato_medido(self):
        self.nuevo()
        self.assertIn("va con --tipo medido", self.falla(
            "fuente", "--linea", "demanda", "--url", "https://a.example/x", "--publicada", "2026-06", "--tipo",
            "terceros", "--acumulado", "--peldano", 1, "--resumen", "x"))


# --- #14 · La fecha de publicación real ----------------------------------------------------------------------------

class FechaPublicacionTest(Base):
    def fuente_con(self, publicada, *extra):
        self.sitio += 1
        return self.p("fuente", "--linea", "voz-del-usuario", "--url", "https://foro.example/hilo-%d" % self.sitio,
                      "--publicada", publicada, "--tipo", "usuario", "--peldano", 1, "--resumen", "Hilo inventado",
                      *extra)

    def test_avisa_cuando_la_publicacion_coincide_con_la_consulta(self):
        self.nuevo()
        salida = self.fuente_con(HOY)
        self.assertIn("⚠ La fecha de publicación es la misma que la de consulta (%s)" % HOY, salida)
        self.assertIn("--publicada desconocida", salida)
        self.assertNotIn("misma que la de consulta", self.fuente_con("2026-06"))

    def test_desconocida_no_cuenta_y_sin_fecha_sigue_valiendo(self):
        self.nuevo()
        for valor in ("desconocida", "sin-fecha"):
            self.assertIn("sin fecha o fuera de la ventana", self.fuente_con(valor))
        self.assertIn("AAAA-MM-DD, AAAA-MM o desconocida", self.falla(
            "fuente", "--linea", "demanda", "--url", "https://a.example/z", "--publicada", "ayer", "--tipo",
            "usuario", "--peldano", 1, "--resumen", "x"))

    def test_no_se_publica_despues_de_leerse(self):
        self.nuevo()
        error = self.falla("fuente", "--linea", "demanda", "--url", "https://a.example/y", "--publicada", "2026-11-20",
                           "--consultada", "2026-11-10", "--tipo", "usuario", "--peldano", 1, "--resumen", "x")
        self.assertIn("es posterior a la fecha de consulta", error)


class DocumentacionTest(unittest.TestCase):
    def test_skill_md_nombra_cada_comando_nuevo(self):
        texto = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for comando in ("objetivo", "vacio", "cobertura", "resenas", "principal", "propuesta", "modelos", "consumo"):
            self.assertRegex(texto, r"`%s`" % comando, comando)

    def test_las_referencias_explican_las_reglas_nuevas(self):
        leer = lambda nombre: (SKILL / "references" / nombre).read_text(encoding="utf-8")
        self.assertIn("Fuentes difíciles", leer("investigacion.md"))
        self.assertIn("navegador", leer("investigacion.md"))
        self.assertIn("viable con confianza baja", leer("diferenciacion.md"))
        self.assertIn("misma regla", leer("evidencia.md"))
        self.assertIn("modelo de monetización viable con evidencia", leer("puertas.md"))
        self.assertIn("propuesta", leer("puertas.md"))
        self.assertIn("consumo", leer("modelos.md"))

    def test_la_documentacion_explica_las_mejoras_10_a_16(self):
        leer = lambda nombre: (SKILL / "references" / nombre).read_text(encoding="utf-8")
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for comando in ("reporte", "tablero"):
            self.assertRegex(skill, r"`%s`" % comando, comando)
        self.assertIn("`oficial`", leer("evidencia.md"))
        self.assertIn("desconocida", leer("evidencia.md"))
        self.assertIn("--acumulado", leer("puntaje.md"))
        self.assertIn("--bloquea", leer("puntaje.md"))
        self.assertIn("El sustituto más fuerte", leer("diferenciacion.md"))
        self.assertIn("--resuelve", leer("investigacion.md"))
        self.assertIn("tablero --raiz", leer("puertas.md"))
        self.assertIn("tablero --raiz", leer("prompts.md"))
        plantillas = SKILL / "assets" / "plantillas"
        self.assertIn("## Sustitutos", (plantillas / "competencia.md").read_text(encoding="utf-8"))
        self.assertIn("## Frente al sustituto más fuerte", (plantillas / "diferenciacion.md").read_text(encoding="utf-8"))
        self.assertIn("--bloquea", (plantillas / "politicas.md").read_text(encoding="utf-8"))

    def test_las_plantillas_traen_la_cobertura_y_la_meta_opcional(self):
        plantillas = SKILL / "assets" / "plantillas"
        for linea in base.producto.COBERTURA_LINEAS:
            self.assertIn("## Cobertura", (plantillas / (linea + ".md")).read_text(encoding="utf-8"), linea)
        idea = (plantillas / "00-idea.md").read_text(encoding="utf-8")
        self.assertIn("opcional", idea)
        self.assertIn("Tiendas", idea)


if __name__ == "__main__":
    unittest.main()
