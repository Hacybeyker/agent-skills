"""Tests de las mejoras #3 y #25 a #36 de hb-product: el modo orquestado con `siguiente --json` (#3, #35), el tipo de
idea antes de las líneas y la evidencia no buscada (#28), los estados de los diferenciadores con las mismas palabras
(#25), el rival pendiente y el ajuste a otra sesión (#26), el puntaje de hoy como principal (#27), el puntaje por
modelo de monetización (#29), la tracción bien contada (#30), la vigencia por tipo de fuente (#31), el conteo por
peldaño (#32), las fechas con solo el año (#33), el presupuesto de cada reapertura (#34) y el rival del mismo segmento
(#36).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_rival as rival
from helpers import ROOT, write

HOY = base.HOY
producto = base.producto
REFERENCIAS = ROOT / "skills" / "hb-product" / "references"


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(rival.Base):
    def json(self, ok=True):
        salida = self.p("siguiente", "--json", ok=ok)
        return json.loads(salida.strip().splitlines()[-1]) if ok else salida

    def nueva_con_lineas(self, problema=True):
        """Una idea nueva cuya 1a confirmó el tipo antes de las demás líneas: dos análogos con tracción, un sustituto y
        la búsqueda de intentos. Con problema=False, ni 1b ni 1c subieron a los peldaños 4 y 5."""
        self.sesion0("nueva")
        self.p("tipo", "--nueva", "--motivo", "No hay apps de turnos de riego entre vecinos")
        fuentes = self.fuente("competencia", 3, "medido", peldano=3)
        for indice in range(2):
            self.p("competidor", "--nombre", "Turnos de limpieza %d" % indice, "--peldano", 3, "--fuentes",
                   fuentes[indice], "--descargas", "250k")
        self.p("competidor", "--nombre", "Lista en el ascensor", "--peldano", 4, "--fuentes", fuentes[2],
               "--sustituto", "gratuito", "--resuelve", "parcial")
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "nada")
        self.p("intento", "--resultado", "sin-rastro", "--texto", "Se buscaron apps cerradas y post-mortems")
        self.cerrar("1a", "01-investigacion/competencia.md")
        self.linea("1b", "voz-del-usuario", "usuario", 4 if problema else 1)
        self.linea("1c", "demanda", "usuario", 5 if problema else 1)
        self.linea("1d", "monetizacion", "terceros", 3)
        self.linea("1e", "politicas", "terceros", 1)
        self.cerrar("1g", "01-investigacion/diferenciacion.md")


# --- #3 y #35 · Modo orquestado ------------------------------------------------------------------------------------

class OrquestadoTest(Base):
    def test_sin_idea_da_la_sesion_0_para_un_subagente_y_el_modelo_del_orquestador(self):
        datos = self.json()
        self.assertEqual((datos["tipo"], datos["quien"], datos["requiere_persona"]), ("sesion", "subagente", True))
        paso = datos["pasos"][0]
        self.assertEqual((paso["sesion"], paso["subagente"]), ("0", {"modelo": "sonnet", "esfuerzo": "medium"}))
        self.assertIn("<pedido del usuario, tal cual>", paso["texto"])
        self.assertEqual(datos["orquestador"]["modelo"], "Haiku 5.5")
        self.assertIn("claude --model claude-haiku-5-5 --effort low", datos["orquestador"]["abrir"])

    def test_las_lineas_van_en_paralelo_en_primer_plano_y_por_tandas(self):
        """#38: en primer plano, en un solo mensaje; 1a y 1b primero y, al cerrar las dos, la 1g junto con 1c–1e."""
        self.sesion0()
        datos = self.json()
        self.assertEqual([p["sesion"] for p in datos["pasos"]], ["1a", "1b"])
        self.assertTrue(datos["en_paralelo"])
        self.assertEqual(datos["esperan"], ["1c", "1d", "1e", "1g", "1f"])
        self.assertEqual(datos["plano"], "primero")
        self.assertIn("en primer plano (nunca en segundo plano)", datos["motivo"])
        self.assertIn("espera a que terminen todos", datos["motivo"])
        for paso in datos["pasos"]:
            self.assertEqual(paso["subagente"], {"modelo": "sonnet", "esfuerzo": "medium"})
            self.assertEqual(paso["plano"], "primero")
            self.assertIn("Idea existente (provisional: la confirma 1a)", paso["texto"])
        self.assertIn("```text\nSiguiente paso", (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        # en modo manual siguen siendo cinco chats a la vez
        self.assertIn("5. Chat nuevo · Sesión 1e", self.p("siguiente"))
        self.assertIn("Puedes abrir estos chats en paralelo, uno por sesión (o un subagente por sesión en el modo "
                      "orquestado):", self.p("siguiente"))
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[0], "--descargas", "500k",
               "--rival")
        self.sustituto(fuentes[1])
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "Se buscó y no apareció")
        self.cerrar("1a", "01-investigacion/competencia.md")
        self.linea("1b", "voz-del-usuario", "usuario")
        datos = self.json()
        self.assertEqual([(p["sesion"], p["subagente"]["modelo"]) for p in datos["pasos"]],
                         [("1c", "sonnet"), ("1d", "sonnet"), ("1e", "sonnet"), ("1g", "opus")])
        self.assertEqual(datos["esperan"], ["1f"])

    def test_la_1g_se_lanza_con_su_modelo_apenas_cierran_1a_y_1b(self):
        self.hasta_1g()
        datos = self.json()
        self.assertEqual([(p["sesion"], p["subagente"]["modelo"], p["subagente"]["esfuerzo"]) for p in datos["pasos"]],
                         [("1g", "opus", "high")])

    def test_en_la_puerta_se_detiene_con_el_veredicto_y_los_comandos_del_usuario(self):
        self.hasta_puerta1()
        datos = self.json()
        self.assertEqual((datos["tipo"], datos["quien"], datos["donde"]), ("puerta", "usuario", "terminal"))
        self.assertIn("nunca corre decidir", datos["motivo"])
        paso = datos["pasos"][0]
        self.assertEqual(paso["veredicto"]["titulo"], "Viable")
        self.assertTrue(paso["opciones"][0]["recomendado"])
        self.assertIn("decidir --puerta 1 --seguir --carpeta product", paso["opciones"][0]["comando"])
        self.assertIn("PUERTA 1 · VIABLE", paso["texto"])
        self.assertIn("consumo --sesion orquestador --incluye 0,1a,1b,1c,1d,1e,1g,1f --costo",
                      datos["costo"]["comando_orquestador"])
        self.assertIn("consumo --sesion <id> --tokens '<tokens>' --pasos '<pasos>'", datos["costo"]["comando_sesion"])
        self.assertEqual(datos["costo"]["sin_anotar"], ["0", "1a", "1b", "1c", "1d", "1e", "1g", "1f"])

    def test_otro_proveedor_no_tiene_alias_y_un_error_sale_en_json(self):
        self.sesion0()
        self.p("modelos", "--intermedio", "GPT 5.3 Codex")
        self.assertIsNone(self.json()["pasos"][0]["subagente"]["modelo"])
        write(self.carpeta / "producto.json", "{roto")
        error = json.loads(self.ultimo_stdout())
        self.assertEqual((error["tipo"], error["quien"]), ("error", "usuario"))

    def ultimo_stdout(self):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            try:
                producto.main(["siguiente", "--json", "--carpeta", str(self.carpeta)])
            except SystemExit as fin:
                self.assertEqual(fin.code, 1)
        return salida.getvalue()

    def test_la_referencia_y_los_prompts_describen_el_modo_orquestado(self):
        texto = (REFERENCIAS / "orquestacion.md").read_text(encoding="utf-8")
        for frase in ("siguiente --json", "Espera a que terminen todos", "consumo --sesion <id>", "nunca corre `decidir`",
                      "en paralelo"):
            self.assertIn(frase, texto)
        prompts = (REFERENCIAS / "prompts.md").read_text(encoding="utf-8")
        self.assertIn("en modo orquestado", prompts)
        self.assertIn("claude --model claude-haiku-5-5 --effort low", prompts)

    def test_los_tokens_del_orquestador_no_se_cuentan_dos_veces(self):
        self.sesion0()
        self.p("consumo", "--sesion", "0", "--tokens", "20k")
        self.p("consumo", "--sesion", "orquestador", "--tokens", "50k", "--incluye", "0")
        self.assertIn("· 50 000 tokens", self.p("consumo"))


# --- #28 · El tipo antes de las líneas y la evidencia que no se buscó -----------------------------------------------

class TipoProvisionalTest(Base):
    def test_1a_confirma_el_tipo_provisional_de_la_sesion_0(self):
        self.sesion0("nueva")
        self.assertIn("Idea nueva (provisional: la confirma 1a): trabaja por analogía desde el inicio",
                      self.p("siguiente"))
        self.assertIn("nueva (provisional: la confirma 1a)", self.p("tipo"))
        self.completar("01-investigacion/competencia.md")
        self.assertIn("falta confirmar el tipo de idea", self.falla("cerrar", "--sesion", "1a"))
        self.p("tipo", "--nueva", "--motivo", "Confirmado: no hay directos")
        self.assertNotIn("provisional", self.p("tipo"))

    def test_un_cambio_de_tipo_marca_las_lineas_que_no_buscaron_y_la_puerta_no_descarta(self):
        self.sesion0("existente")
        self.p("tipo", "--existente", "--motivo", "Parecía haber directos")
        fuentes = self.fuente("competencia", 3, "medido", peldano=3)
        for indice in range(2):
            self.p("competidor", "--nombre", "Turnos de limpieza %d" % indice, "--peldano", 3, "--fuentes",
                   fuentes[indice], "--descargas", "250k")
        self.p("competidor", "--nombre", "Lista en el ascensor", "--peldano", 4, "--fuentes", fuentes[2],
               "--sustituto", "gratuito", "--resuelve", "parcial")
        self.p("competidor", "--sin-rival", "Ninguna alternativa gratis resuelve la necesidad")
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "nada")
        self.p("intento", "--resultado", "sin-rastro", "--texto", "Se buscaron apps cerradas")
        self.cerrar("1a", "01-investigacion/competencia.md")
        self.linea("1b", "voz-del-usuario", "usuario", 4)  # ya subió por la escalera: no se marca
        self.linea("1c", "demanda", "usuario", 1)  # trabajó con competencia: no buscó el problema
        self.linea("1d", "monetizacion", "terceros", 3)
        self.linea("1e", "politicas", "terceros", 1)
        salida = self.p("tipo", "--nueva", "--motivo", "Los directos resultaron análogos")
        self.assertIn("⚠ A revisar por cambio de tipo: 1c (cerró como idea existente y no tiene fuentes de los "
                      "peldaños 4 y 5)", salida)
        self.assertIn("1c · Demanda | cerrada el 2026-11-23 · a revisar por cambio de tipo", self.p("estado"))
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "2,2,3,3,1")  # 11/25: bajo el mínimo de 15
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("La sesión 1c cerró como idea existente y la idea es nueva: no buscó en los peldaños 4 y 5",
                      salida)
        self.assertNotIn("★ Recomendado · Descartar", salida)
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.assertIn("Idea nueva: trabaja por analogía desde el inicio. Reapertura 1", self.p("siguiente"))
        self.linea("1c", "demanda", "usuario", 5)
        self.assertEqual(producto.a_revisar_por_tipo(self.datos(), producto.Registro(
            self.carpeta, self.datos()["criterios"])), [])

    def test_el_problema_no_buscado_pide_ajustar_1c_y_el_buscado_sin_resultado_tambien_una_vez(self):
        self.nueva_con_lineas(problema=False)
        self.p("puntaje", "--valores", "3,3,4,4,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✖ El problema o la necesidad de fondo, con 3 fuentes de peldaño 4 o 5 · no buscado", salida)
        self.assertIn("AJUSTAR 1c", salida)
        self.assertIn("Nadie buscó el problema en los peldaños 4 y 5: es evidencia no buscada", salida)
        datos = self.datos()
        datos["sesiones"]["1f"].pop("cerrada")
        write(self.carpeta / "producto.json", json.dumps(datos))
        for peldano in (4, 5):
            self.p("vacio", "--linea", "demanda", "--peldano", peldano, "--motivo", "sin-resultados", "--texto",
                   "Busqué foros y prensa sobre el problema: nada")
        self.assertIn("peldaño 4", self.p("vacio", "--linea", "demanda", "--peldano", 4, "--motivo", "presupuesto",
                                         "--texto", "x"))
        self.assertIn("un solo valor", self.falla("vacio", "--linea", "demanda", "--peldano", 4, "--mercado", "MX",
                                                  "--motivo", "presupuesto", "--texto", "x"))
        salida = self.cerrar("1f")
        self.assertIn("buscado: ningún hallazgo reúne 3 fuentes independientes y vigentes", salida)
        # buscado sin resultado en la primera pasada de la 1c: se ajusta una vez (feedback #55)
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertIn("Se buscó el problema en los peldaños 4 y 5 y ningún hallazgo reúne 3 fuentes independientes y "
                      "vigentes (una de los últimos 18 meses), pero no hay evidencia en contra: es la primera pasada",
                      salida)
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.cerrar("1c")
        salida = self.cerrar("1f")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Se buscó el problema en los peldaños 4 y 5, también al reabrir la 1c (reabierta una vez)",
                      salida)


# --- #32 · Conteo de hallazgos por peldaño -------------------------------------------------------------------------

class ConteoPeldanosTest(Base):
    def test_estado_puerta_y_reporte_cuentan_vigentes_y_vencidos(self):
        self.nueva_con_lineas()
        viejas = self.fuente("voz-del-usuario", 1, "usuario", 4, publicada="2020-03")
        self.hallazgo("voz-del-usuario", viejas, "--sin-contra", "nada")
        conteo = producto.conteo_peldanos(producto.Registro(self.carpeta, self.datos()["criterios"]))
        self.assertEqual((conteo[4]["vigentes"], conteo[4]["vencidos"]), (1, 1))
        self.assertTrue(conteo[2]["no_buscado"])
        salida = self.p("estado")
        self.assertIn("Hallazgos por peldaño: 1 · directo: 1 (1 vigente, 0 vencidos)", salida)
        self.assertIn("2 · variante: no buscado", salida)
        self.assertIn("4 · sustituto: 2 (1 vigente, 1 vencido)", salida)
        self.p("puntaje", "--valores", "3,3,4,4,1")
        self.assertIn("· Hallazgos por peldaño: 1 · directo", self.cerrar("1f", "01-sintesis.md"))
        self.p("reporte")
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("<h2>Hallazgos por peldaño</h2>", html)
        self.assertIn("1 vigente · 1 vencido", html)


# --- #31 y #33 · Vigencia por tipo de fuente y fechas con solo el año ----------------------------------------------

class VigenciaTest(Base):
    def fuente_con(self, *extra, url="https://academia.example/estudio"):
        return self.p("fuente", "--linea", "demanda", "--url", url, "--tipo", "medido", "--peldano", 5, "--resumen",
                      "Estudio inventado", *extra)

    def test_solo_el_anio_cuenta_desde_el_1_de_enero_y_queda_aproximada(self):
        self.sesion0()
        salida = self.fuente_con("--publicada", "2025")
        self.assertIn("Solo el año: cuenta desde el 1 de enero de 2025", salida)
        self.assertIn("sin fecha o fuera de su ventana", salida)  # 2025-01-01 está fuera de 18 meses
        fuente = self.datos("01-investigacion/demanda.json")["fuentes"][0]
        self.assertEqual((fuente["publicada"], fuente["aproximada"]), ("2025-01-01", "anio"))
        self.assertIn("futuro", self.falla("fuente", "--linea", "demanda", "--url", "https://otra.example/a",
                                           "--publicada", "2027", "--tipo", "medido", "--peldano", 1, "--resumen",
                                           "x"))
        self.assertIn("AAAA (solo el año)", self.falla("fuente", "--linea", "demanda", "--url",
                                                       "https://otra.example/b", "--publicada", "25", "--tipo",
                                                       "medido", "--peldano", 1, "--resumen", "x"))

    def test_un_estudio_academico_vale_5_anios_pero_un_hallazgo_pide_una_fuente_reciente(self):
        self.sesion0()
        salida = self.fuente_con("--publicada", "2022", "--clase", "academica")
        self.assertIn("estudio académico · vigente", salida)
        viejas = [self.fuente_con("--publicada", "2023-0%d" % mes, "--clase", "academica",
                                  url="https://u%d.example/e" % mes) for mes in (2, 3)]
        ids = ["S-DEM-1", "S-DEM-2", "S-DEM-3"]
        self.assertTrue(all("vigente" in v for v in viejas))
        _, salida = self.hallazgo("demanda", ids, "--critico", "--sin-contra", "nada")
        self.assertIn("sin triangular", salida)
        self.assertIn("falta una fuente de los últimos 18 meses", salida)
        reciente = self.fuente("demanda", 1, "terceros", 5)
        _, salida = self.hallazgo("demanda", ids[:2] + reciente, "--critico", "--sin-contra", "nada")
        self.assertIn("triangulado", salida)
        self.assertNotIn("sin triangular", salida)

    def test_la_estadistica_oficial_rige_hasta_una_edicion_mas_nueva(self):
        self.sesion0()
        self.fuente_con("--publicada", "2023-05", "--clase", "estadistica", url="https://censo.example/2023")
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.assertTrue(registro.vigente(registro.fuentes["S-DEM-1"]))
        self.assertIn("--reemplaza es de una estadística oficial", self.falla(
            "fuente", "--linea", "demanda", "--url", "https://censo.example/2026", "--publicada", "2026-05", "--tipo",
            "medido", "--peldano", 5, "--resumen", "x", "--reemplaza", "S-DEM-1"))
        salida = self.fuente_con("--publicada", "2026-05", "--clase", "estadistica", "--reemplaza", "S-DEM-1",
                                 url="https://censo.example/2026")
        self.assertIn("S-DEM-2 reemplaza a S-DEM-1: la edición anterior deja de ser vigente", salida)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.assertFalse(registro.vigente(registro.fuentes["S-DEM-1"]))
        self.assertIn("una norma (--tipo oficial)", self.falla(
            "fuente", "--linea", "politicas", "--url", "https://tienda.example/politica", "--publicada", "2026-05",
            "--tipo", "oficial", "--peldano", 1, "--resumen", "x", "--clase", "academica"))

    def test_una_fuente_sin_fecha_se_completa_con_el_anio_y_la_clase(self):
        self.sesion0()
        self.fuente_con("--publicada", "desconocida")
        salida = self.fuente_con("--publicada", "2024", "--clase", "academica")
        self.assertIn("no se duplica; se completó: publicada en 2024 (fecha aproximada: solo el año), estudio "
                      "académico", salida)
        self.assertIn("S-DEM-1: vigente", salida)


# --- #30 · Tracción bien contada -----------------------------------------------------------------------------------

class TraccionTest(Base):
    def test_el_criterio_cuenta_las_descargas_sobre_el_umbral_o_el_respaldo_y_los_nombra(self):
        self.nueva_con_lineas()
        fuente = self.fuente("competencia", 1, "medido", peldano=2)[0]
        self.p("competidor", "--nombre", "Turnos de limpieza 0", "--peldano", 3, "--fuentes", fuente, "--descargas",
               "40k", "--traccion", "40 mil descargas, bajo el umbral")
        self.p("competidor", "--nombre", "Programa de huertos", "--peldano", 2, "--fuentes", fuente, "--respaldo",
               "Ministerio de ejemplo")
        self.p("puntaje", "--valores", "3,3,4,4,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✔ Al menos 2 análogos con tracción (peldaño 2 o 3) · 2 de 2: C-2 (250 000 descargas); C-4 "
                      "(respaldo institucional: Ministerio de ejemplo) · sin tracción (bajo 100 000 descargas o 2 000 "
                      "valoraciones, y sin respaldo institucional): C-1", salida)


# --- #37 · Tracción estimada por valoraciones ---------------------------------------------------------------------

class TraccionValoracionesTest(Base):
    def test_sin_descargas_las_valoraciones_estiman_la_traccion_y_la_puerta_lo_dice(self):
        self.nueva_con_lineas()
        self.assertEqual(self.datos()["criterios"]["traccion_valoraciones"], 2000)
        fuente = self.fuente("competencia", 1, "medido", peldano=3)[0]
        salida = self.p("competidor", "--nombre", "Turnos de limpieza 0", "--peldano", 3, "--fuentes", fuente,
                        "--descargas", "40k", "--valoraciones", "9000")
        self.assertIn("sin tracción: 40 000 descargas, bajo el umbral", salida)
        self.assertIn("Con descargas registradas, las valoraciones no cuentan", salida)
        salida = self.p("competidor", "--nombre", "Turnos en tienda iOS", "--peldano", 3, "--fuentes", fuente,
                        "--valoraciones", "1500")
        self.assertIn("sin tracción: 1 500 valoraciones, bajo el umbral de 2 000", salida)
        salida = self.p("competidor", "--nombre", "Turnos en tienda iOS", "--peldano", 3, "--fuentes", fuente,
                        "--valoraciones", "3200")
        self.assertIn("con tracción: tracción estimada por valoraciones: 3 200, sin descargas publicadas (umbral "
                      "2 000)", salida)
        self.assertNotIn("descargas", salida.split("Columnas sin dato:")[-1].splitlines()[0])
        self.p("puntaje", "--valores", "3,3,4,4,1")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✔ Al menos 2 análogos con tracción (peldaño 2 o 3) · 2 de 2: C-2 (250 000 descargas); C-4 "
                      "(tracción estimada por valoraciones: 3 200, sin descargas publicadas (umbral 2 000)) · sin "
                      "tracción (bajo 100 000 descargas o 2 000 valoraciones, y sin respaldo institucional): C-1",
                      salida)

    def test_el_umbral_se_cambia_con_criterio(self):
        self.nuevo()
        self.p("criterio", "--clave", "traccion_valoraciones", "--valor", 5000)
        self.assertEqual(self.datos()["criterios"]["traccion_valoraciones"], 5000)
        self.assertIn("| `traccion_valoraciones` | 5000 |", (self.carpeta / "criterios.md").read_text(encoding="utf-8"))
        self.assertIn("tracción estimada por valoraciones",
                      (REFERENCIAS / "puertas.md").read_text(encoding="utf-8"))


# --- #29 · El puntaje según el modelo de monetización ---------------------------------------------------------------

class PuntajeModeloTest(Base):
    def test_la_puerta_muestra_el_puntaje_con_cada_modelo_y_cual_exige(self):
        self.nueva_con_lineas()
        self.assertIn("nombra también el modelo base", self.falla("puntaje", "--valores", "4,3,4,1,1",
                                                                 "--alternativo", "Pago único=4,4,4,3,1"))
        self.assertIn("--alternativo es", self.falla("puntaje", "--valores", "4,3,4,1,1", "--modelo", "Anuncios",
                                                     "--alternativo", "Pago único"))
        salida = self.p("puntaje", "--valores", "4,3,4,1,1", "--modelo", "Anuncios", "--alternativo",
                        "Pago único=4,4,4,3,1")
        self.assertIn("Con «Pago único»: 16/25 (monetización 4, riesgo de políticas 3) → lo alcanza", salida)
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("✔ Puntaje de 15/25 o más · tiene 13/25 · por modelo de monetización: «Anuncios» 13/25; «Pago "
                      "único» 16/25 · alcanza el mínimo solo con «Pago único»: exige ese modelo", salida)
        self.assertIn("✔ Riesgo de políticas distinto de 1, o con una mitigación escrita · es 1 con «Anuncios» y 3 con "
                      "«Pago único»: exige ese modelo", salida)
        self.assertIn("1. El puntaje alcanza el mínimo solo con el modelo «Pago único» (16/25; con «Anuncios», "
                      "13/25): la sesión 2 tiene que elegirlo.", salida)
        self.assertNotIn("NO VIABLE", salida)
        self.assertIn("«Anuncios» 13/25; «Pago único» 16/25", self.p("estado"))


# --- #25 · Los estados de los diferenciadores con las mismas palabras -----------------------------------------------

class EstadosTest(Base):
    def test_el_banner_nombra_a_todos_los_que_deciden_con_su_estado(self):
        voz = self.hasta_1g()
        for vector, texto in (("usabilidad", "Turnos en tres toques"), ("idioma", "Avisos en lengua local")):
            suelto = self.sin_triangular()
            self.p("diferenciador", "--vector", vector, "--texto", texto, "--hallazgos", "%s,%s" % (voz, suelto),
                   "--se-ve", "uso", "--copiable", "media", "--motivo", "Les cuesta rehacerlo", "--semanas", 2)
        self.p("frente", "--id", "D-1", "--resultado", "iguala", "--hallazgos", voz, "--texto", "Ya es gratis")
        for identificador in ("D-2", "D-3"):
            self.p("frente", "--id", identificador, "--resultado", "supera", "--hallazgos", voz, "--texto", "x")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "4,4,4,4,2")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("D-2 y D-3 superan al rival C-2 (PlantaPlus), pero son viables con confianza baja: H-DIF-1 y H-DIF-2 "
                      "sin triangular", salida)
        self.assertIn("El principal (D-1) iguala al rival C-2 (PlantaPlus): no viable (paridad", salida)
        self.assertIn("0 viables de 3 registrados: D-2 y D-3 (viables con confianza baja); D-1 (no viable: paridad)",
                      salida)
        self.assertNotIn("no son viables", salida)
        self.p("reporte")
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("Viable con confianza baja", html)
        self.assertIn("No viable · paridad", html)
        self.assertNotIn("Prometedor", html)


# --- #26 · El rival pendiente se completa en la 1g; ajustar otra sesión pide el motivo ------------------------------

class RivalPendienteTest(Base):
    def test_con_el_rival_sin_marcar_recomienda_ajustar_1g(self):
        voz = self.hasta_1g(rival=False)
        datos = self.datos()  # un registro anterior: la 1a cerró sin marcar el rival
        datos["sesiones"]["1a"] = {"cerrada": "2026-11-20T10:00", "tipo": "existente"}
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.assertTrue(voz)
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("★ Recomendado · Ajustar 1g", salida)
        self.assertIn("sin reabrir 1a", salida)
        self.assertIn('decidir --puerta 1 --ajustar <sesión> --motivo "<por qué decides distinto de la '
                      'recomendación>"', salida)


# --- #27 · El puntaje de hoy como principal, y etiquetas que hacen salto de línea -----------------------------------

class PuntajeHoyTest(Base):
    def test_tablero_y_reporte_muestran_el_de_hoy_con_el_registrado_aparte(self):
        self.investigacion(viable=False)
        self.p("puntaje", "--valores", "4,4,4,4,1")
        datos = self.datos()
        datos["puntaje"]["valores"]["diferenciacion"] = 4
        datos["puntaje"]["total"] = 20
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.cerrar("1f", "01-sintesis.md")
        self.p("tablero", "--raiz", str(self.tmp))
        html = (self.tmp / "index.html").read_text(encoding="utf-8")
        self.assertIn("<b>Puntaje:</b> 17/25<br><span class=\"nota\">se registró 20/25 · mínimo", html)
        self.assertIn("Riego en turnos: 17 de 25", html)
        reporte = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("<h3>Total · 17 de 25</h3><span class=\"nota\">Se registró 20/25.", reporte)
        self.assertIn("17/25 (se registró 20/25)", self.p("estado"))

    def test_las_etiquetas_largas_hacen_salto_de_linea_en_el_telefono(self):
        self.assertNotIn("white-space:nowrap", producto.ESTILO)
        self.assertIn("white-space:normal;overflow-wrap:anywhere", producto.ESTILO)


# --- #34 · Cada reapertura tiene su propio presupuesto -------------------------------------------------------------

class PresupuestoReaperturaTest(Base):
    def test_la_reapertura_tiene_la_mitad_y_avisa_si_se_pasa(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--ajustar", "1c", "--motivo", "Quiero más evidencia de demanda")
        salida = self.p("siguiente")
        self.assertIn("Reapertura 1: el presupuesto de esta pasada es de 8 búsquedas y 5 lecturas.", salida)
        self.assertIn("cada reapertura, 8 y 5", self.p("tipo"))
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://nueva.example/a", "--publicada", "2026-06",
                        "--tipo", "medido", "--peldano", 1, "--resumen", "x", "--mercados", "MX")
        self.assertIn("Fuentes de la línea demanda en esta reapertura: 1 (presupuesto de lecturas de la reapertura: 5)",
                      salida)
        salida = self.p("cerrar", "--sesion", "1c", "--busquedas", 9, "--lecturas", 3)
        self.assertIn("9 de 8 búsquedas y 3 de 5 lecturas en la reapertura 1", salida)
        self.assertIn("⚠ Esta pasada se pasó de su presupuesto", salida)
        self.assertIn("Presupuesto excedido: 1c usó 9 de 8 búsquedas", self.p("estado"))
        self.assertIn("⚠ Presupuesto excedido: 1c usó 9 de 8 búsquedas", self.cerrar("1f"))


# --- #36 · El rival es el del mismo usuario y la misma necesidad ----------------------------------------------------

class RivalRevisarTest(Base):
    def test_un_sustituto_con_traccion_que_llega_despues_pide_revisar_el_rival(self):
        self.hasta_1g()
        fuente = self.fuente("demanda", 1, "medido", 4)[0]
        self.p("competidor", "--nombre", "Huerto escolar municipal", "--peldano", 4, "--fuentes", fuente,
               "--sustituto", "gratuito", "--resuelve", "parcial", "--respaldo", "Municipio de ejemplo")
        salida = self.p("siguiente")
        self.assertIn("⚠ Revisar el rival: C-4 (Huerto escolar municipal), sustituto gratuito con tracción "
                      "(respaldo institucional: Municipio de ejemplo) llegó después de marcar el rival (C-2 "
                      "(PlantaPlus))", salida)
        self.assertIn("para el mismo usuario y la misma necesidad", salida)
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", "S-COM-2", "--rival")
        self.assertNotIn("Revisar el rival", self.p("siguiente"))

    def test_la_referencia_pide_el_rival_del_mismo_segmento(self):
        texto = (REFERENCIAS / "diferenciacion.md").read_text(encoding="utf-8")
        self.assertIn("para el mismo usuario y la misma necesidad", texto)


if __name__ == "__main__":
    unittest.main()
