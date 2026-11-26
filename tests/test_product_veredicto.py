"""Tests del veredicto y la recomendación de la skill en cada puerta (#19), del pulido del reporte y del tablero (#17) y
del consumo sin costo en USD (#18) de hb-product.

La skill calcula con reglas fijas un veredicto (No viable, Viable con reservas o Viable) y una recomendación (descartar,
ajustar <sesión> o seguir); el usuario decide, y decidir en contra pide --motivo.

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


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def reporte(self, carpeta=None):
        return ((carpeta or self.carpeta) / "reporte.html").read_text(encoding="utf-8")

    def debil(self):
        """«Otra app de linterna»: sin diferenciador, con riesgo de políticas 1 y sin mitigación."""
        self.investigacion(viable=False)
        self.p("puntaje", "--valores", "5,2,5,1,1")
        self.cerrar("1f", "01-sintesis.md")

    def recomendado(self, salida):
        """El comando recomendado que imprime la puerta, sin el `cd … &&`, listo para pasarlo a self.p."""
        linea = next(l for l in salida.splitlines() if "★ Recomendado" in l)
        partes = shlex.split(linea.split(" && ", 1)[1])
        return partes[partes.index("decidir"):partes.index("--carpeta")]


# --- #19 · Veredicto y recomendación ------------------------------------------------------------------------------

class VeredictoTest(Base):
    def test_viable_recomienda_seguir_con_el_banner_primero(self):
        self.hasta_puerta1()
        salida = self.p("siguiente")
        lineas = salida.splitlines()
        self.assertTrue(lineas[2].startswith("━"))  # el banner va al inicio de la salida de la puerta
        self.assertEqual(lineas[3], "🟢  PUERTA 1 · VIABLE  →  la skill recomienda: SEGUIR")
        self.assertIn("  1. Cumple los 5 criterios de la puerta 1.", salida)
        self.assertIn("Qué cambiaría el veredicto:", salida)
        self.assertLess(salida.index("━"), salida.index("Puerta 1 · Oportunidad · idea existente · cumple 5 de 5"))
        comandos = [l for l in lineas if l.startswith("   ") and "decidir --puerta" in l]
        self.assertTrue(comandos[0].startswith("   ★ Recomendado · Seguir: cd "))
        self.assertNotIn("--motivo", comandos[0])
        self.assertTrue(all("--motivo" in c for c in comandos[1:]))  # lo que va en contra lleva --motivo
        salida = self.p("decidir", "--puerta", 1, "--seguir")
        self.assertIn("· Coincide con la recomendación de la skill (veredicto: Viable).", salida)
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual(decision["recomendacion"]["veredicto"], "viable")
        self.assertEqual(decision["recomendacion"]["recomienda"], "seguir")
        self.assertFalse(decision["contra_recomendacion"])
        self.assertNotIn("motivo_decision", decision)

    def test_no_viable_recomienda_descartar_con_el_motivo_listo(self):
        self.debil()
        salida = self.p("puerta", "--n", 1)
        self.assertIn("🔴  PUERTA 1 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("  1. El puntaje es 14/25, bajo el mínimo de 17.", salida)
        self.assertIn("Ningún diferenciador supera al rival C-2 (PlantaPlus) con hallazgos triangulados", salida)
        razones = re.findall(r"^  \d\. ", salida, re.M)
        self.assertLessEqual(len(razones), 3)
        self.assertIn("Criterios: cumple 1 de 5.", salida)
        orden_ = self.recomendado(salida)
        self.assertEqual(orden_[:4], ["decidir", "--puerta", "1", "--descartar"])
        self.assertTrue(orden_[4].startswith("No viable: El puntaje es 14/25"))
        salida = self.p(*orden_)  # el recomendado, copiado tal cual, no pide --motivo
        self.assertIn("idea descartada y archivada", salida)
        decision = json.loads((self.carpeta / "archivo" / "riego-en-turnos" / "decisiones.json").read_text(
            encoding="utf-8"))[-1]
        self.assertEqual((decision["decision"], decision["contra_recomendacion"]), ("descartar", False))

    def test_decidir_en_contra_pide_motivo_y_queda_registrado(self):
        self.debil()
        error = self.falla("decidir", "--puerta", 1, "--seguir")
        self.assertIn("La skill recomienda descartar (veredicto: No viable;", error)
        self.assertIn("agrega --motivo", error)
        self.assertIn("al menos 10 caracteres", self.falla("decidir", "--puerta", 1, "--seguir", "--motivo", "porque"))
        salida = self.p("decidir", "--puerta", 1, "--seguir", "--motivo", "Quiero probar el MVP en una semana")
        self.assertIn("⚠ Decisión contra la recomendación (la skill recomendaba descartar; veredicto: No viable): queda "
                      "registrada con tu motivo: «Quiero probar el MVP en una semana»", salida)
        decision = self.datos("decisiones.json")[-1]
        self.assertTrue(decision["contra_recomendacion"])
        self.assertEqual(decision["motivo_decision"], "Quiero probar el MVP en una semana")
        self.assertEqual(decision["recomendacion"]["recomienda"], "descartar")
        self.assertIn("**contra la recomendación**: Quiero probar el MVP en una semana",
                      (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        html = self.reporte()
        self.assertIn("Contra la recomendación", html)
        self.assertIn("La skill recomendaba descartar (no viable)", html)

    def test_confianza_global_baja_recomienda_ajustar_la_linea_debil(self):
        self.investigacion()
        self.p("confianza", "--hallazgo", "H-MON-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1d", salida)
        # H-MON-1 está triangulado y bajado a mano: la razón lo dice en vez de «sin confirmar» (feedback #71)
        self.assertIn("La confianza global es baja: monetización se apoya en evidencia en confianza baja: H-MON-1 está "
                      "triangulado, pero en confianza baja por una bajada a mano (Las fuentes se contradicen)", salida)
        self.assertIn("Con eso, el veredicto pasaría a Viable", salida)
        self.assertIn("   ★ Recomendado · Ajustar 1d: cd ", salida)
        self.assertIn("decidir --puerta 1 --ajustar 1d --carpeta product", salida)
        # ajustar otra sesión que la recomendada pide el motivo y queda como decisión en contra (feedback #26)
        self.assertIn("Para ajustar la sesión 1c en contra de la recomendación, agrega --motivo",
                      self.falla("decidir", "--puerta", 1, "--ajustar", "1c"))
        self.assertIn("⚠ Decisión contra la recomendación (la skill recomendaba ajustar la sesión 1d",
                      self.p("decidir", "--puerta", 1, "--ajustar", "1c", "--motivo", "La demanda me preocupa más"))
        self.assertTrue(producto.decisiones(self.carpeta)[-1]["contra_recomendacion"])

    def test_una_propuesta_que_no_se_cierra_con_las_herramientas_no_pide_ajustar(self):
        self.hasta_puerta2()
        self.p("objetivo", "--tiendas", "google-play,app-store", "--motivo", "Sumamos la otra tienda")
        self.p("vacio", "--linea", "voz-del-usuario", "--tienda", "app-store", "--motivo", "herramienta", "--texto",
               "Página dinámica")
        self.p("propuesta", "--texto", "Releer las reseñas de la otra tienda", "--ajustar", "1b", "--sesion", "3")
        self.assertIn("🟢  PUERTA 2 · VIABLE  →  la skill recomienda: SEGUIR", self.p("puerta", "--n", 2))
        self.p("propuesta", "--texto", "Revisar los precios", "--ajustar", "1d", "--sesion", "3")
        salida = self.p("puerta", "--n", 2)
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1d", salida)
        self.assertIn("Hay una propuesta pendiente (PR-2): Revisar los precios", salida)

    def test_puerta_2_con_una_hipotesis_refutada_no_es_viable(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS.replace("| sostenida | sí |", "| refutada | sí |"))
        salida = self.cerrar("3")
        self.assertIn("🔴  PUERTA 2 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("Hay hipótesis críticas refutadas (HIP-01)", salida)

    def test_puerta_3_fuera_del_presupuesto_ajusta_el_prd_y_un_bloqueo_no_es_viable(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--seguir")
        write(self.carpeta / "04-prd.md", base.PRD.replace("| 1000 | 2 | 3 |", "| 1000 | 2 | 5 |"))
        salida = self.cerrar("4")
        self.assertIn("🟡  PUERTA 3 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 4", salida)
        write(self.carpeta / "04-prd.md", base.PRD.replace("| pendiente | antes de publicar |",
                                                            "| bloqueo | la tienda no lo permite |"))
        self.assertIn("🔴  PUERTA 3 · NO VIABLE", self.p("puerta", "--n", 3))

    def test_idea_nueva_que_ya_fracaso_no_es_viable_y_sin_buscar_intentos_pide_ajustar_1a(self):
        prueba = base.IdeaNuevaTest("run")
        prueba.setUp()
        self.addCleanup(prueba.doCleanups)
        prueba.investigar(intento="fracaso-demanda")
        prueba.p("puntaje", "--valores", "3,3,4,4,1")
        salida = prueba.p("puerta", "--n", 1)
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("Alguien ya lo probó y fracasó por falta de demanda", salida)
        datos = prueba.datos()
        datos["intentos"] = []
        write(prueba.carpeta / "producto.json", json.dumps(datos))
        salida = prueba.p("puerta", "--n", 1)
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1a", salida)
        self.assertIn("Falta buscar si alguien ya lo intentó", salida)

    def test_el_color_solo_en_una_terminal(self):
        self.hasta_puerta1()
        texto = self.p("siguiente")
        self.assertNotIn("\033[", texto)  # en un chat o en un archivo, el color lo da la marca
        self.assertNotIn("\033[", (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        pintado = producto.con_color(texto, activo=True)
        lineas = pintado.splitlines()
        self.assertEqual(sum(1 for l in lineas if l.startswith("\033[1;32m")), 4)  # tres rayas y el título
        self.assertTrue(lineas[3].startswith("\033[1;32m🟢"))
        self.assertEqual(producto.con_color(texto, activo=False), texto)


class PuntajeDesactualizadoTest(Base):
    def registrar_con_reglas_viejas(self):
        """Una idea sin diferenciador viable con un puntaje de diferenciación 4: lo que dejaba registrar una versión
        anterior del script (hoy `puntaje` lo rechaza)."""
        self.investigacion(viable=False)
        self.p("puntaje", "--valores", "4,4,4,4,1")
        datos = self.datos()
        datos["puntaje"]["valores"]["diferenciacion"] = 4
        datos["puntaje"]["total"] = 20
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.cerrar("1f", "01-sintesis.md")

    def test_avisa_y_el_veredicto_usa_el_puntaje_con_las_reglas_de_hoy(self):
        self.registrar_con_reglas_viejas()
        salida = self.p("puerta", "--n", 1)
        self.assertIn("✔ Puntaje de 17/25 o más · tiene 17/25 (se registró 20/25) · con las reglas de hoy: "
                      "diferenciación 4, pero con las reglas de hoy el máximo es 1", salida)
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)  # por el diferenciador, no por el puntaje
        datos = self.datos()
        registro = producto.Registro(self.carpeta, datos["criterios"])
        vigente = producto.puntaje_vigente(datos, registro)
        self.assertEqual(vigente["total"], 17)
        self.assertEqual(vigente["incoherencias"], ["diferenciación 4, pero con las reglas de hoy el máximo es 1 "
                                                    "(ningún diferenciador es viable)"])
        self.p("reporte")
        html = self.reporte()
        self.assertIn("Puntaje recalculado", html)
        self.assertIn("Con las reglas de hoy el puntaje es <b>17/25</b>; se registró 20/25", html)
        self.assertIn("<b>17/25</b><span>puntaje (mínimo 17); se registró 20/25</span>", html)

    def test_bajo_el_minimo_con_las_reglas_de_hoy_es_no_viable(self):
        self.registrar_con_reglas_viejas()
        datos = self.datos()
        datos["puntaje"]["valores"].update(demanda=3, monetizacion=3, facilidad=3, riesgo=4, diferenciacion=4)
        datos["puntaje"]["total"] = 17
        datos["criterios"]["puntaje_minimo"] = 17
        write(self.carpeta / "producto.json", json.dumps(datos))
        salida = self.p("puerta", "--n", 1)
        self.assertIn("Con las reglas de hoy el puntaje es 14/25 (se registró 17/25), bajo el mínimo de 17", salida)

    def test_un_puntaje_que_acepta_puntaje_no_tiene_incoherencias(self):
        self.hasta_puerta1()
        datos = self.datos()
        self.assertEqual(producto.puntaje_vigente(datos, producto.Registro(self.carpeta, datos["criterios"]))[
            "incoherencias"], [])


# --- #19 y #17 · El veredicto en el reporte y en el tablero; pulido de los dos ----------------------------------

class ReporteVeredictoTest(Base):
    def test_el_banner_va_arriba_del_reporte_con_su_color(self):
        self.hasta_puerta1()
        self.p("reporte")
        html = self.reporte()
        self.assertLess(html.index('<section class="veredicto bien">'), html.index("Resumen ejecutivo"))
        self.assertIn("🟢 Viable</p>", html)
        self.assertIn("Puerta 1 · Oportunidad · la skill recomienda: seguir", html)
        self.assertIn("<h3>Por qué</h3>", html)
        self.assertIn("<h3>Qué cambiaría el veredicto</h3>", html)
        self.assertIn("Viable · recomienda seguir", html)  # también en la tarjeta de la puerta pendiente

    def test_sin_puerta_todavia_lo_dice(self):
        self.nuevo()
        self.p("reporte")
        self.assertIn("Todavía sin veredicto", self.reporte())

    def test_los_hallazgos_que_decidieron_van_abiertos_con_sus_fuentes(self):
        self.debil()
        self.p("decidir", "--puerta", 1, "--descartar", "Sin diferenciador frente a la linterna del sistema (H-DEM-1)")
        html = self.reporte(self.carpeta / "archivo" / "riego-en-turnos")
        resumen = html[html.index("Resumen ejecutivo"):html.index("Puntaje por criterio")]
        self.assertIn("Los hallazgos que decidieron", resumen)
        self.assertIn("ref. H-DEM-1", resumen)  # el que cita el motivo, primero
        self.assertIn('href="https://', resumen)  # con sus fuentes enlazadas
        self.assertIn("confianza alta", resumen)
        decisivos = resumen[resumen.index("Los hallazgos que decidieron"):]
        self.assertNotIn("<details", decisivos)  # abiertos, no plegados
        self.assertTrue(3 <= decisivos.count("<li>") - decisivos.count("<li><a") <= 5)
        self.assertIn("🔴 No viable", html)  # la puerta 1, recalculada hoy, como dato secundario
        banner = html[html.index('<section class="veredicto'):html.index("Resumen ejecutivo")]
        self.assertIn("✖ Descartada en la puerta 1</p>", banner)  # el estado final como titular (#45)
        self.assertIn("P1 🔴 → descartada", banner)

    def test_plurales_reales_y_competidores_con_conteo(self):
        self.hasta_puerta1()
        self.p("reporte")
        html = self.reporte()
        for palabra in ("hallazgo(s)", "confirmado(s)", "semana(s)", "idea(s)", "hueco(s)", "vacío(s)",
                        "viable(s)", "registrado(s)"):
            self.assertNotIn(palabra, html)
        self.assertIn("1 hallazgo, 1 confirmado", html)
        self.assertIn("2 semanas", html)
        competidores = html[html.index("Competidores y sustitutos"):html.index("Cobertura por mercado")]
        self.assertIn("<details><summary>1 hallazgo</summary><p class=\"ref\">H-VOZ-1</p></details>", competidores)

    def test_tablero_con_estados_que_no_se_cruzan_y_el_veredicto_de_cada_idea(self):
        raiz = self.tmp
        self.carpeta = raiz / "riego" / "product"
        self.debil()
        self.p("decidir", "--puerta", 1, "--descartar", "Sin diferenciador frente a la linterna del sistema")
        self.carpeta = raiz / "linterna" / "product"
        self.p("nuevo", "--nombre", "Linterna", "--semanas", 2)
        self.p("archivar", "--motivo", "La retomo cuando tenga tiempo")
        self.carpeta = raiz / "huerto" / "product"
        self.hasta_puerta1()
        salida = self.p("tablero", "--raiz", raiz)
        self.assertIn("✔ Tablero con 3 ideas", salida)
        self.assertIn("· Riego en turnos (carpeta riego/product/archivo/riego-en-turnos · creada el %s) · Descartada "
                      "en la puerta 1 · P1 🔴 → descartada · " % HOY, salida)  # dos ideas con el mismo nombre
        self.assertIn("· Linterna · Pausada (archivada a mano) · ", salida)
        html = (raiz / "index.html").read_text(encoding="utf-8")
        conteo = dict((etiqueta, int(n)) for n, etiqueta in re.findall(
            r'<div class="cifra"><b>(\d+)</b><span>([^<]+)</span>', html))
        self.assertEqual(conteo, {"en curso": 1, "lista para construir": 0, "descartada": 1, "pausada": 1})
        self.assertEqual(sum(conteo.values()), 3)  # cada idea en un solo estado
        self.assertNotIn("Archivada", html)
        self.assertIn("Cada idea está en un solo estado", html)
        self.assertIn('class="veredicto compacto mal"', html)
        self.assertIn('class="veredicto compacto bien"', html)
        self.assertIn("P1 🔴 → descartada", html)  # el recorrido, no el veredicto suelto de la última puerta
        self.assertIn("Pausada (archivada a mano)", html)


# --- #18 · Consumo sin costo en USD y el del orquestador -----------------------------------------------------------

class ConsumoSinCostoTest(Base):
    def test_sin_costo_dice_sin_dato_y_muestra_los_tokens(self):
        self.hasta_puerta1()
        self.p("consumo", "--sesion", "1a", "--tokens", "102800", "--modelo", "Sonnet 5.5")
        salida = self.p("consumo", "--sesion", "1b", "--tokens", "91k")
        self.assertIn("total anotado: sin dato en USD · 193 800 tokens", salida)
        self.assertNotIn("0 USD", salida)
        self.assertIn("Total: sin dato en USD · 193 800 tokens", self.p("consumo"))
        self.assertIn("total sin dato en USD · 193 800 tokens", self.p("estado"))
        self.p("reporte")
        html = self.reporte()
        self.assertIn("<b>Total anotado:</b> sin dato en USD · 193 800 tokens", html)
        self.assertNotIn("0 USD", html[html.index(">Costo<"):])
        self.p("consumo", "--sesion", "1c", "--costo", "0.40")
        self.assertIn("Total: 0,40 USD (sin dato en USD: 1a, 1b) · 193 800 tokens", self.p("consumo"))

    def test_siguiente_pide_el_consumo_del_orquestador_al_llegar_a_la_puerta(self):
        self.hasta_puerta1()
        self.assertNotIn("orquestador", self.p("siguiente"))  # sin consumo anotado, no se pide
        self.p("consumo", "--sesion", "1a", "--tokens", "45k")
        salida = self.p("siguiente")
        self.assertIn("Consumo del chat orquestador (si lo usaste): al terminar, anota lo que muestre /cost", salida)
        self.assertIn("producto.py consumo --sesion orquestador --incluye 0,1a,1b,1c,1d,1e,1g,1f --costo '<USD que "
                      "muestra /cost>' --chat orq-1 --carpeta product", salida)  # sin --tokens: no se cuentan dos veces
        self.assertIn("cd %s && python3 -I " % self.tmp, salida)
        self.p("consumo", "--sesion", "orquestador", "--costo", "1.20", "--incluye", "1a")
        # el orquestador solo dijo que corrió la 1a: las demás siguen sin un chat que las cubra (feedback #46)
        self.assertIn("--incluye 0,1b,1c,1d,1e,1g,1f --costo", self.p("siguiente"))
        self.p("consumo", "--sesion", "orquestador", "--costo", "1.80", "--incluye", "0,1a,1b,1c,1d,1e,1g,1f")
        self.assertNotIn("Consumo del chat orquestador", self.p("siguiente"))
        filas = [f for f in self.datos()["consumo"] if f["sesion"] == "orquestador"]
        self.assertEqual(len(filas), 1)  # el mismo chat (comparte la 1a): /cost es acumulado y actualiza su fila
        self.assertEqual(filas[0]["costo"], 1.8)

    def test_mientras_hay_sesiones_abiertas_no_lo_pide(self):
        self.sesion0()
        self.p("consumo", "--sesion", "0", "--tokens", "20k")
        self.assertNotIn("Consumo del chat orquestador", self.p("siguiente"))


class DocumentacionVeredictoTest(unittest.TestCase):
    """La regla cambió: la skill recomienda y el usuario decide. La documentación lo dice en todos lados."""

    def test_skill_y_referencias_dicen_que_la_skill_recomienda(self):
        skill = (base.SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("La skill recomienda; la decisión es del usuario", skill)
        self.assertIn("--motivo", skill)
        puertas = (base.SKILL / "references" / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("## Veredicto y recomendación", puertas)
        for texto in ("No viable", "Viable con reservas", "Viable"):
            self.assertIn(texto, puertas)
        puntaje = (base.SKILL / "references" / "puntaje.md").read_text(encoding="utf-8")
        self.assertNotIn("No recomiendes la decisión", puntaje)


if __name__ == "__main__":
    unittest.main()
