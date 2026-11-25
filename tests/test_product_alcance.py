"""Tests de las mejoras #38 a #46 de hb-product: la puerta 3 sin diferenciador principal, los criterios de aceptación
contados por el script y los vacíos atribuidos a su línea (#44); el modo orquestado en primer plano y el recordatorio
de /cost (#38 y #46); el recorrido por las puertas, los hallazgos del motivo y el PRD en el reporte (#45); los usuarios
activos derivados de las instalaciones y la retención (#43); los competidores por su ID o por la URL de su ficha
(#39); el rival y el sustituto por separado (#40), y los plurales reales (#42).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import re
import shlex
import unittest

import test_product as base
from helpers import write

HOY = base.HOY
producto = base.producto
REFERENCIAS = base.SKILL / "references"

PRD_SIN_CRITERIOS = base.PRD.replace("""- **Criterios de aceptación:**
  - Dado que me toca hoy, cuando son las 9, entonces recibo un aviso.
  - Dado que ya marqué el turno, cuando son las 9, entonces no recibo el aviso.""", """- **Criterios de aceptación:**""")
PRD_SIN_PRINCIPAL_EN_EL_MVP = base.PRD.replace("| H-VOZ-1 | D-1 | M-01 |", "| H-VOZ-1 | — | M-01 |")


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def reporte(self, carpeta=None):
        return ((carpeta or self.carpeta) / "reporte.html").read_text(encoding="utf-8")

    def json(self):
        return json.loads(self.p("siguiente", "--json"))

    def recomendado(self, salida):
        linea = next(l for l in salida.splitlines() if "★ Recomendado" in l)
        partes = shlex.split(linea.split(" && ", 1)[1])
        return partes[partes.index("decidir"):partes.index("--carpeta")]

    def sin_principal_hasta_puerta3(self, cerrar_4=True):
        """Una idea sin ningún diferenciador que el usuario siguió hasta el PRD en contra de la recomendación."""
        self.investigacion(viable=False)
        self.p("puntaje", "--valores", "4,4,4,4,1")
        self.cerrar("1f", "01-sintesis.md")
        self.p("decidir", "--puerta", 1, "--seguir", "--motivo", "Lo sigo igual para ver hasta dónde llega")
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS)
        self.cerrar("3")
        self.p("decidir", "--puerta", 2, "--seguir", "--motivo", "Lo sigo igual para ver hasta dónde llega")
        write(self.carpeta / "04-prd.md", base.PRD)
        if cerrar_4:
            self.cerrar("4")

    def agotar_1g(self, busquedas=3, lecturas=8):
        """La última pasada de la 1g llegó al 80 % de sus lecturas (8 de 10)."""
        datos = self.datos()
        datos["sesiones"]["1g"]["pasadas"] = [{"reapertura": 0, "busquedas": busquedas, "lecturas": lecturas,
                                               "fecha": HOY + "T10:00",
                                               "presupuesto": {"busquedas": 15, "lecturas": 10}}]
        write(self.carpeta / "producto.json", json.dumps(datos))


# --- #44 · La puerta 3 sin principal, los criterios de aceptación y los vacíos de su línea ---------------------------

class PuertaTresTest(Base):
    def test_sin_principal_y_con_la_1g_agotada_recomienda_descartar_como_en_las_puertas_1_y_2(self):
        self.sin_principal_hasta_puerta3()
        self.agotar_1g()
        salida = self.p("puerta", "--n", 3)
        self.assertIn("🔴  PUERTA 3 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("No hay un diferenciador principal: ninguno es viable frente al rival C-2 (PlantaPlus), y la "
                      "1g ya usó su presupuesto (3 de 15 búsquedas y 8 de 10 lecturas en la primera pasada)", salida)
        self.assertNotIn("Completarlo en el PRD", salida)
        orden_ = self.recomendado(salida)
        self.assertEqual(orden_[:4], ["decidir", "--puerta", "3", "--descartar"])
        self.assertIn("No hay un diferenciador principal", orden_[4])
        # la misma falta, la misma regla en la puerta 2
        self.assertIn("No hay un diferenciador principal: ninguno es viable", self.p("puerta", "--n", 2))

    def test_sin_principal_y_con_presupuesto_en_la_1g_recomienda_ajustarla(self):
        self.sin_principal_hasta_puerta3()
        salida = self.p("puerta", "--n", 3)
        self.assertIn("🟡  PUERTA 3 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("y la 1g cerró sin usar su presupuesto", salida)
        self.assertNotIn("AJUSTAR 4", salida)

    def test_sin_principal_con_una_propuesta_para_la_1g_recomienda_ajustarla(self):
        self.sin_principal_hasta_puerta3(cerrar_4=False)
        self.p("propuesta", "--texto", "Buscar un segmento que PlantaPlus atiende mal", "--ajustar", "1g")
        self.cerrar("4")
        self.agotar_1g()
        salida = self.p("puerta", "--n", 3)
        self.assertIn("la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("pero PR-1 puede dar uno en la 1g", salida)

    def test_con_principal_fuera_del_mvp_recomienda_ajustar_el_prd(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", PRD_SIN_PRINCIPAL_EN_EL_MVP)
        salida = self.cerrar("4")
        self.assertIn("🟡  PUERTA 3 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 4", salida)
        self.assertIn("El diferenciador principal (D-1) no está en ninguna funcionalidad del MVP", salida)

    def test_el_script_cuenta_los_criterios_de_aceptacion(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", PRD_SIN_CRITERIOS)
        salida = self.cerrar("4")
        self.assertIn("✖ Cada funcionalidad del MVP tiene criterios de aceptación · 1 de 2 · sin criterios: F-02",
                      salida)
        self.assertIn("la skill recomienda: AJUSTAR 4", salida)
        self.assertIn("Faltan los criterios de aceptación de F-02", salida)
        self.assertIn("✖ Criterios de aceptación: 1 de 2 funcionalidades del MVP · sin criterios: F-02",
                      self.p("trazabilidad"))
        write(self.carpeta / "04-prd.md", base.PRD)
        self.assertIn("✔ Cada funcionalidad del MVP tiene criterios de aceptación · 2 de 2 · 5 criterios",
                      self.p("puerta", "--n", 3))

    def test_cuenta_las_vinetas_debajo_del_campo_y_no_la_plantilla(self):
        texto = """## Historias de usuario

### F-01 · Turnos

- **Historia:** como vecino, quiero ver el turno.
- **Criterios de aceptación:**
  - Dado …, cuando …, entonces …
  - Dado …, cuando …, entonces …
- **Notas:** no cuenta
  - tampoco esta

### F-02

- **Criterios de aceptación:** dado un turno, cuando lo marco, entonces queda hecho

### F-03

- **Criterios de aceptación:**
  - <por completar: dado …, cuando …, entonces …>

## Métricas HEART

- no es de ninguna historia
"""
        self.assertEqual(producto.criterios_aceptacion(texto), {"F-01": 2, "F-02": 1, "F-03": 0})

    def test_un_vacio_de_herramienta_se_atribuye_a_su_linea_y_no_a_la_sesion_4(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        self.p("objetivo", "--mercados", "MX,AR", "--idiomas", "es", "--tiendas", "google-play", "--motivo",
               "Sumamos Argentina como mercado")
        self.p("vacio", "--linea", "monetizacion", "--mercado", "AR", "--motivo", "herramienta", "--texto",
               "Los reportes de eCPM de AR piden cuenta")
        write(self.carpeta / "04-prd.md", PRD_SIN_PRINCIPAL_EN_EL_MVP)
        salida = self.cerrar("4")
        self.assertIn("la skill recomienda: AJUSTAR 4", salida)
        self.assertNotIn("La sesión 4 tiene", salida)
        self.assertNotIn("límite de las herramientas", salida[:salida.index("Puerta 3 · Alcance")])
        datos = producto.cargar(self.carpeta)
        registro = producto.Registro(self.carpeta, datos["criterios"])
        self.assertEqual(producto.vacios_de_sesion(datos, registro, "4"), [])
        vacios = producto.vacios_de_sesion(datos, registro, "1d")
        self.assertEqual(producto.texto_vacios_sesion("1d", vacios), "La sesión 1d (monetización) tiene un vacío "
                         "por límite de las herramientas (V-MON-1: mercado AR)")


# --- #40 · El rival y el sustituto, cada uno por su nombre -------------------------------------------------------------

class RivalYSustitutoTest(Base):
    def test_el_banner_los_nombra_por_separado(self):
        self.investigacion(viable=False)
        self.sustituto("S-COM-3", nombre="Lista en la puerta", tipo="gratuito", resuelve="si")
        self.p("puntaje", "--valores", "5,2,5,1,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("Ningún diferenciador supera al rival C-2 (PlantaPlus) ni al sustituto C-4 (Lista en la "
                      "puerta) con hallazgos triangulados", salida)
        self.assertIn("Un diferenciador con evidencia confirmada de algo que no dan ni el rival C-2 (PlantaPlus) ni "
                      "el sustituto C-4 (Lista en la puerta)", salida)
        self.assertNotIn("(PlantaPlus); C-4", salida)
        motivo = self.recomendado(salida)[4]  # el motivo que propone decidir --descartar, con las mismas palabras
        self.assertIn("supera al rival C-2 (PlantaPlus) ni al sustituto C-4 (Lista en la puerta)", motivo)


# --- #42 · Plurales reales ----------------------------------------------------------------------------------------

class PluralesTest(unittest.TestCase):
    def test_el_script_no_usa_plurales_entre_parentesis(self):
        import io
        import tokenize
        texto = base.SCRIPT.read_text(encoding="utf-8")
        textos = [t.string for t in tokenize.generate_tokens(io.StringIO(texto).readline) if t.type == tokenize.STRING]
        self.assertEqual([t for t in textos if re.search(r"[a-záéíóú]\((s|es|n)\)", t)], [])
        self.assertNotIn("el/los", texto)
        self.assertNotIn("(uno por sesión; con subagentes, uno por sesión)", texto)


# --- #43 · Usuarios activos desde las instalaciones y la retención ---------------------------------------------------

class RetencionTest(Base):
    ENTRADA = {"mercados": [{
        "mercado": "MX",
        "instalaciones_mes": {"pesimista": 3000, "base": 3000, "optimista": 3000, "fuente": "S-MON-1"},
        "retencion": {"d1": {"pesimista": 0.3, "base": 0.3, "optimista": 0.3, "fuente": "S-MON-1"},
                      "d7": {"pesimista": 0.1, "base": 0.1, "optimista": 0.1, "fuente": "S-MON-1"},
                      "d30": {"pesimista": 0.04, "base": 0.04, "optimista": 0.04, "fuente": "S-MON-1"}},
        "anuncios": [{"formato": "banner",
                      "impresiones_por_dau": {"pesimista": 4, "base": 4, "optimista": 4, "fuente": "S-MON-1"},
                      "ecpm": {"pesimista": 0.5, "base": 0.5, "optimista": 0.5, "fuente": "S-MON-1"}}]}]}

    def calcular(self, entrada, ok=True):
        write(self.carpeta / "escenarios.json", json.dumps(entrada))
        return self.p("escenarios", "--entrada", "escenarios.json", ok=ok)

    def entrada(self):
        return json.loads(json.dumps(self.ENTRADA))

    def test_deriva_los_usuarios_activos_de_las_instalaciones_y_la_retencion(self):
        self.hasta_puerta1()
        # días activos en los primeros 30: 1 + (D1 a D7: 1,4) + (D8 a D29: 1,54) = 3,94 → 3000 ÷ 30 × 3,94 = 394
        self.assertAlmostEqual(producto.dias_activos(0.3, 0.1, 0.04), 3.94)
        salida = self.calcular(self.entrada())
        self.assertIn("| MX | 394 (de instalaciones y retención) |", salida)
        # 394 × 4 × 30 × 0,5 ÷ 1000 = 23,64
        self.assertIn("✔ Anuncios · banner · 23,64 USD al mes en el caso base", salida)
        self.assertEqual(self.datos()["escenarios"]["dau_origen"], {"MX": "instalaciones"})
        self.assertNotIn("comparable", salida)

    def test_valida_la_retencion(self):
        self.hasta_puerta1()
        entrada = self.entrada()
        entrada["mercados"][0]["retencion"]["d7"]["base"] = 0.5
        self.assertIn("no sube con los días (D30 ≤ D7 ≤ D1)", self.calcular(entrada, ok=False))
        entrada = self.entrada()
        entrada["mercados"][0]["dau"] = 1000
        self.assertIn("trae `dau` y `retencion`: usa uno", self.calcular(entrada, ok=False))
        entrada = self.entrada()
        del entrada["mercados"][0]["instalaciones_mes"]
        self.assertIn("falta `MX.instalaciones_mes`", self.calcular(entrada, ok=False))
        entrada = self.entrada()
        del entrada["mercados"][0]["retencion"]
        self.assertIn("necesita `dau` (usuarios activos diarios, con fuente) o `instalaciones_mes` y `retencion`",
                      self.calcular(entrada, ok=False))
        entrada = self.entrada()
        entrada["mercados"][0]["retencion"]["d30"]["fuente"] = ""
        self.assertIn("✖ Anuncios · banner · 23,64 USD al mes en el caso base · estimación: sin fuente en "
                      "MX.retencion.d30", self.calcular(entrada))

    def test_avisa_cuando_los_usuarios_salen_de_un_comparable_maduro(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        salida = self.escenarios(fuente="S-COM-1")  # la fuente de la fila de RiegoFácil, con 1M de descargas
        self.assertIn("⚠ MX: los usuarios activos diarios salen de C-1 (RiegoFácil), una app que ya está en la "
                      "tienda. Una app nueva no tiene esa base instalada", salida)
        self.assertEqual(self.datos()["escenarios"]["dau_origen"], {"MX": "comparable"})
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS)
        self.assertIn("⚠ Usuarios activos de un comparable maduro: MX: los usuarios activos diarios salen de C-1",
                      self.cerrar("3"))
        self.p("reporte")
        self.assertIn("Usuarios activos de un comparable maduro", self.reporte())
        self.escenarios()  # con su propia fuente de monetización, no avisa
        self.assertEqual(self.datos()["escenarios"]["avisos"], [])

    def test_la_plantilla_deriva_los_usuarios_de_la_retencion(self):
        plantilla = json.loads((base.SKILL / "assets" / "plantillas" / "escenarios.json").read_text(encoding="utf-8"))
        mercado = plantilla["mercados"][0]
        self.assertEqual(set(mercado["retencion"]), {"d1", "d7", "d30"})
        self.assertNotIn("dau", mercado)


# --- #39 · Los competidores por su ID o por la URL de su ficha -------------------------------------------------------

class CompetidorPorIdTest(Base):
    def setUp(self):
        super().setUp()
        self.sesion0()
        self.ficha = self.p("fuente", "--linea", "competencia", "--url", "https://tienda.example/app/turnero",
                            "--publicada", "2026-06", "--tipo", "medido", "--peldano", 1, "--resumen", "Ficha inventada",
                            "--mercados", "MX", "--idiomas", "es", "--tiendas", "google-play")
        self.p("competidor", "--nombre", "Turnero (Estudio Inventado)", "--peldano", 1, "--fuentes", "S-COM-1",
               "--descargas", "200k")

    def voz_de_la_ficha(self):
        """Una fuente de la voz del usuario que es la misma ficha (sus reseñas)."""
        salida = self.p("fuente", "--linea", "voz-del-usuario", "--url", "https://www.tienda.example/app/turnero/",
                        "--publicada", "2026-06", "--tipo", "usuario", "--peldano", 1, "--resumen", "Reseñas",
                        "--mercados", "MX", "--idiomas", "es", "--tiendas", "google-play")
        return re.search(r"S-VOZ-\d+", salida).group(0)

    def test_por_id_y_un_nombre_con_fila_se_guarda_como_id(self):
        _, salida = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario"), "--competidor", "C-1")
        self.assertIn("· Cita a C-1 (por su ID en la matriz).", salida)
        self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario"), "--competidor", "turnero (estudio inventado)")
        self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario"), "--competidor",
                      "https://tienda.example/app/turnero")
        citados = [h["competidores"] for h in self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"]]
        self.assertEqual(citados, [["C-1"], ["C-1"], ["C-1"]])

    def test_un_nombre_distinto_se_enlaza_por_la_url_de_la_ficha(self):
        voz = self.voz_de_la_ficha()
        _, salida = self.hallazgo("voz-del-usuario", [voz], "--competidor", "Turnero: Turnos del Edificio")
        self.assertIn("· Cita a C-1 (por su ID en la matriz).", salida)  # enlazado por la ficha, no por el nombre
        matriz = self.p("matriz")
        self.assertIn("| H-VOZ-1 |", matriz)
        self.assertNotIn("no tiene fila en la matriz", matriz)
        _, salida = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario"), "--competidor", "Otra app")
        self.assertIn("· Competidor sin fila en la matriz todavía: Otra app. Cuando la 1a lo registre, cítalo por su "
                      "ID (`--competidor C-…`)", salida)
        self.assertIn("⚠ Competidor Otra app: lo cita H-VOZ-2, pero no tiene fila en la matriz", self.p("matriz"))


# --- #38 y #46 · Primer plano y el recordatorio de /cost --------------------------------------------------------------

class OrquestadoCostoTest(Base):
    def test_cada_parada_trae_el_recordatorio_con_el_comando_armado(self):
        self.hasta_puerta1()
        datos = self.json()
        self.assertEqual(datos["tipo"], "puerta")
        self.assertIn("arriba, el recordatorio de /cost", datos["motivo"])
        recordatorio = datos["costo"]["recordatorio"]
        self.assertTrue(recordatorio.startswith("Antes de decidir o de cerrar este chat: corre /cost aquí"))
        self.assertIn("consumo --sesion orquestador --incluye 0,1a,1b,1c,1d,1e,1g,1f --costo", recordatorio)
        self.assertEqual(datos["costo"]["sin_orquestador"], ["0", "1a", "1b", "1c", "1d", "1e", "1g", "1f"])

    def test_el_mismo_chat_actualiza_su_fila_y_otro_chat_va_aparte(self):
        self.hasta_puerta1()
        self.p("consumo", "--sesion", "orquestador", "--incluye", "0,1a,1b", "--costo", "0.90")
        self.p("consumo", "--sesion", "orquestador", "--incluye", "0,1a,1b,1c,1d", "--costo", "1.50")  # el mismo chat
        self.assertEqual(self.json()["costo"]["sin_orquestador"], ["1e", "1g", "1f"])
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1e,1g,1f", "--costo", "0.70")  # otro chat
        filas = [f for f in self.datos()["consumo"] if f["sesion"] == "orquestador"]
        self.assertEqual([(f["incluye"], f["costo"]) for f in filas],
                         [(["0", "1a", "1b", "1c", "1d"], 1.5), (["1e", "1g", "1f"], 0.7)])
        self.assertIn("Total: 2,20 USD", self.p("consumo"))
        self.assertEqual(self.json()["costo"]["sin_orquestador"], [])

    def test_una_sesion_con_su_propio_costo_no_la_pide_el_orquestador(self):
        self.hasta_puerta1()
        self.p("consumo", "--sesion", "0", "--costo", "0.20")
        self.assertNotIn("0", self.json()["costo"]["sin_orquestador"])

    def test_la_regla_esta_en_la_referencia_y_en_el_prompt(self):
        texto = (REFERENCIAS / "orquestacion.md").read_text(encoding="utf-8")
        for frase in ("siempre en primer plano", "todos en un mismo mensaje", "Nunca uses segundo plano",
                      "Continúa en modo orquestado", "Arriba de cada parada, el costo", "costo.sin_orquestador",
                      "1c ‖ 1d ‖ 1e ‖ 1g"):
            self.assertIn(frase, texto)
        prompts = (REFERENCIAS / "prompts.md").read_text(encoding="utf-8")
        bloques = re.findall(r"```text\n(.*?)\n```", prompts, re.S)
        orquestados = [b for b in bloques if "modo orquestado" in b]
        self.assertGreaterEqual(len(orquestados), 3)
        for bloque in orquestados:
            self.assertIn("en primer plano", bloque)
            self.assertIn("no cierres tu turno mientras corre uno", bloque)
        self.assertTrue(any("/cost" in b for b in orquestados))


# --- #45 · El recorrido por las puertas, los hallazgos del motivo y el PRD en el reporte -----------------------------

class ReporteRecorridoTest(Base):
    def descartar_en_la_puerta_3(self):
        self.hasta_puerta3()
        self.p("decidir", "--puerta", 3, "--descartar", "PlantaPlus (C-2) ya cubre lo esencial y gratis",
               "--motivo", "Prefiero no construirla todavía")
        return self.carpeta / "archivo" / "riego-en-turnos"

    def test_el_titular_es_el_estado_final_con_el_recorrido(self):
        html = self.reporte(self.descartar_en_la_puerta_3())
        banner = html[html.index('<section class="veredicto'):html.index("Resumen ejecutivo")]
        self.assertIn('<section class="veredicto mal">', banner)
        self.assertIn("✖ Descartada en la puerta 3</p>", banner)
        pasos = re.findall(r'<span class="chip (?:bien|aviso|mal|neutro)">([^<]*P\d[^<]*)</span>', banner)
        self.assertEqual(pasos, ["P1 🟢 → seguir", "P2 🟢 → seguir", "P3 🟢 → descartada contra la recomendación"])
        self.assertIn("La puerta 3, recalculada hoy con las reglas actuales", banner)
        self.assertNotIn('class="recomienda">Puerta 3', banner)  # el veredicto suelto ya no es el titular

    def test_en_curso_el_banner_tambien_muestra_el_recorrido(self):
        self.hasta_puerta2()
        self.p("reporte")
        banner = self.reporte()[self.reporte().index('<section class="veredicto'):]
        self.assertIn("Recorrido:", banner[:banner.index("Resumen ejecutivo")])
        self.assertIn("P1 🟢 → seguir", banner[:banner.index("Resumen ejecutivo")])

    def test_una_decision_reabierta_no_entra_en_el_recorrido(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        self.p("decidir", "--puerta", 1, "--reabrir")
        self.p("decidir", "--puerta", 1, "--seguir")
        self.assertEqual([p["texto"] for p in producto.recorrido(self.carpeta)], ["P1 🟢 → seguir"])

    def test_los_hallazgos_que_decidieron_salen_del_competidor_que_cita_el_motivo(self):
        html = self.reporte(self.descartar_en_la_puerta_3())
        resumen = html[html.index("Los hallazgos que decidieron"):html.index("Puntaje por criterio")]
        primero = re.search(r"ref\. (H-[A-Z]{3}-\d+)", resumen).group(1)
        self.assertEqual(primero, "H-VOZ-1")  # el de la comparación de D-1 con C-2, el competidor del motivo

    def test_la_seccion_del_prd(self):
        html = self.reporte(self.descartar_en_la_puerta_3())
        prd = html[html.index("PRD · el producto mínimo"):html.index(">Costo<")]
        for texto in ("<b>2</b><span>funcionalidades en el MVP</span>", "<b>5 de 6</b><span>semanas del presupuesto",
                      "<b>2 de 2</b><span>con trazabilidad", "<b>2 de 2</b><span>con criterios de aceptación",
                      "<b>2</b><span>métricas HEART", "El diferenciador principal está en el MVP (F-01)",
                      "Turnos de riego con pago único", "3 criterios de aceptación", "Fuera del MVP (1)",
                      "M-01</b> · Retención", "Requisitos de políticas (1)", "Política de privacidad publicada"):
            self.assertIn(texto, prd)

    def test_sin_prd_no_hay_seccion(self):
        self.hasta_puerta1()
        self.p("reporte")
        self.assertNotIn("PRD · el producto mínimo", self.reporte())


if __name__ == "__main__":
    unittest.main()
