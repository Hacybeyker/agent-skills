"""Tests de las mejoras #47 a #49 de hb-product: el veredicto Viable para probar con su criterio de descarte después
del lanzamiento (#47), el tablero siempre al día (#48) y el modo autónomo con `decidir --automatico` (#49).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest
from unittest import mock

import test_product as base
import test_product_rival as rival
from helpers import ROOT, write

HOY = base.HOY
producto = base.producto
SKILL = ROOT / "skills" / "hb-product"


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(rival.Base):
    def json(self):
        return json.loads(self.p("siguiente", "--json").strip().splitlines()[-1])

    def para_probar(self):
        """La puerta 1 de una idea cuyo principal (D-1) supera al rival con el dolor triangulado (H-VOZ-1), pero cuya
        comparación solo tiene un hallazgo en confianza media: falta la prueba de elección."""
        self.hasta_1g()
        media = self.comparacion_media()
        return self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción")

    def debil(self):
        """«Otra app de linterna»: sin diferenciador, con riesgo de políticas 1 y sin mitigación."""
        self.investigacion(viable=False)
        self.p("puntaje", "--valores", "5,2,5,1,1")
        self.cerrar("1f", "01-sintesis.md")

    def tablero(self, raiz=None):
        return ((raiz or self.tmp) / "index.html").read_text(encoding="utf-8")


# --- #47 · Viable para probar --------------------------------------------------------------------------------------

class ParaProbarTest(Base):
    def test_supera_con_el_dolor_triangulado_recomienda_seguir_con_un_criterio_de_descarte(self):
        salida = self.para_probar()
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("Construirlo cabe en el presupuesto (2 de 6 semanas), la demanda tiene confianza alta y no hay "
                      "bloqueo de políticas", salida)
        self.assertIn("Criterio de descarte después del lanzamiento (queda registrado al seguir):", salida)
        self.assertIn("La hipótesis más riesgosa es que la gente elige la app por D-1 frente al rival C-2 (PlantaPlus)",
                      salida)
        self.assertIn("a los 60 días del lanzamiento se miden las instalaciones orgánicas y la retención", salida)
        self.assertIn("(pasaría a Viable)", salida)
        salida = self.p("decidir", "--puerta", 1, "--seguir")  # es lo recomendado: no pide --motivo
        self.assertIn("· Coincide con la recomendación de la skill (veredicto: Viable para probar).", salida)
        self.assertIn("· Viable para probar: la prueba de elección queda para después del lanzamiento.", salida)
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual(decision["recomendacion"]["veredicto"], "probar")
        self.assertEqual(decision["criterio_descarte"]["diferenciador"], "D-1")
        self.assertEqual(decision["criterio_descarte"]["dias"], 60)
        self.assertIn("Viable para probar, criterio de descarte", (self.carpeta / "estado.md").read_text(
            encoding="utf-8"))
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("Viable para probar", html)
        self.assertIn("Criterio de descarte de la puerta 1", html)
        self.assertIn("P1 🟡 → seguir", self.tablero())

    def test_el_plazo_del_criterio_de_descarte_se_cambia_con_criterio(self):
        self.para_probar()
        self.p("criterio", "--clave", "dias_descarte", "--valor", 90, "--motivo", "La temporada de riego es larga")
        self.assertIn("a los 90 días del lanzamiento", self.p("puerta", "--n", 1))

    def test_el_dolor_es_lo_propio_del_diferenciador_y_lo_que_falta_es_la_eleccion(self):
        # D-1 supera con un hallazgo triangulado (H-VOZ-1) y otro suelto: es viable con confianza baja, pero el dolor
        # está triangulado, así que el puntaje no se topa en 2 y la puerta difiere los criterios al lanzamiento
        voz = self.hasta_1g()
        suelto = self.sin_triangular()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", "%s,%s" % (voz, suelto), "--texto", "Sin "
                              "suscripción", valores="4,4,4,4,4")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR", salida)
        self.assertIn("✔ Puntaje de 17/25 o más · tiene 20/25", salida)
        self.assertIn("◐ Al menos 1 diferenciador viable", salida)
        self.assertIn("· se prueba después del lanzamiento (criterio de descarte)", salida)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        d1 = registro.diferenciadores["D-1"]
        self.assertEqual(registro.estado(d1), "baja")
        self.assertTrue(registro.dolor_triangulado(d1))
        self.assertTrue(registro.para_probar(d1))
        self.p("decidir", "--puerta", 1, "--seguir")
        self.assertNotIn("Sigues con", self.p("estado"))
        criterios = self.datos("decisiones.json")[-1]["criterios"]
        self.assertEqual([c["texto"][:20] for c in criterios if c.get("diferido")],
                         ["Al menos 1 diferenci", "Los hallazgos del di"])

    def test_con_el_dolor_sin_triangular_no_es_para_probar(self):
        # D-2 se sostiene en un vector medible (el precio, en la matriz), pero su hallazgo propio no está triangulado
        voz = self.hasta_1g()
        self.p("frente", "--id", "D-1", "--resultado", "iguala", "--hallazgos", voz, "--texto", "Ya es gratis")
        suelto = self.sin_triangular()
        self.p("diferenciador", "--vector", "precio", "--texto", "Un solo pago por edificio", "--hallazgos", suelto,
               "--se-ve", "ficha", "--copiable", "media", "--motivo", "Cambia su modelo", "--semanas", 1)
        self.p("frente", "--id", "D-2", "--resultado", "supera", "--hallazgos", voz, "--texto", "Paga uno por todos")
        self.p("principal", "--id", "D-2")
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.assertFalse(registro.dolor_triangulado(registro.diferenciadores["D-2"]))
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "5,4,4,4,2")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertNotIn("PARA PROBAR", salida)
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)

    def test_con_la_demanda_baja_no_es_para_probar_y_pide_ajustar_1c(self):
        # sin evidencia en contra y en la primera pasada de la 1c, la demanda baja se ajusta (feedback #55)
        self.hasta_1g()
        self.p("confianza", "--hallazgo", "H-DEM-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        media = self.comparacion_media()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", media, "--texto", "Turnos sin suscripción")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1c", salida)
        self.assertNotIn("PARA PROBAR", salida)

    def test_con_un_principal_en_paridad_recomienda_elegir_el_que_se_puede_probar(self):
        voz = self.hasta_1g()
        self.p("frente", "--id", "D-1", "--resultado", "iguala", "--hallazgos", voz, "--texto", "Ya es gratis")
        self.p("diferenciador", "--vector", "funcionalidades", "--texto", "Turnos que se cambian solos",
               "--hallazgos", voz, "--se-ve", "uso", "--copiable", "media", "--motivo", "Pide su motor de turnos",
               "--semanas", 3)
        media = self.comparacion_media()
        self.p("frente", "--id", "D-2", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, media), "--texto",
               "PlantaPlus no reasigna turnos")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "5,4,4,4,3")
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("D-2 supera al rival C-2 (PlantaPlus) con el dolor triangulado (viable para probar), pero el "
                      "principal (D-1) solo lo iguala: no viable (paridad)", salida)
        self.assertIn("Elegir como principal D-2 en la 1g (no pide búsquedas): el veredicto pasaría a Viable para "
                      "probar", salida)
        self.p("decidir", "--puerta", 1, "--ajustar", "1g")
        self.p("principal", "--id", "D-2")
        self.cerrar("1g")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", self.cerrar("1f"))

    def test_las_puertas_2_y_3_piden_la_hipotesis_mas_riesgosa_y_no_la_prueba_de_eleccion(self):
        self.para_probar()
        self.p("decidir", "--puerta", 1, "--seguir")
        texto = [p["texto"] for p in self.json()["pasos"] if p["sesion"] == "3"][0]
        self.assertIn("La puerta 1 fue Viable para probar: registra como la hipótesis más riesgosa que la gente elige "
                      "la app por D-1 frente al rival C-2 (PlantaPlus)", texto)
        self.escenarios()
        self.cerrar("2", "02-estrategia.md")
        # la hipótesis de la elección queda débil (no hay prueba antes de lanzar) y es la más riesgosa, sin métrica
        tabla = base.HIPOTESIS.replace("| sostenida | sí | 30 % vuelve a los 30 días |", "| sostenida | — | — |")
        write(self.carpeta / "03-validacion.md", tabla.replace("| D-1 | sostenida | — | — |", "| D-1 | débil | sí | — |"))
        self.cerrar("3")
        salida = self.p("puerta", "--n", 2)
        self.assertIn("✖ La hipótesis más riesgosa, identificada y medible después del lanzamiento (el criterio de "
                      "descarte de la puerta 1)", salida)
        self.assertIn("✔ El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta · D-1: "
                      "HIP-02 débil (confianza alta; es la más riesgosa: se prueba después del lanzamiento)", salida)
        self.assertIn("· La puerta 1 fue Viable para probar: la prueba de elección se mide después del lanzamiento.",
                      salida)
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 3", salida)
        write(self.carpeta / "03-validacion.md", tabla.replace(
            "| D-1 | sostenida | — | — |", "| D-1 | débil | sí | 2 000 instalaciones orgánicas al mes y 15 % a 30 días, "
                                           "a los 60 días |"))
        self.assertIn("🟢  PUERTA 2 · VIABLE  →  la skill recomienda: SEGUIR", self.p("puerta", "--n", 2))
        self.p("decidir", "--puerta", 2, "--seguir")
        self.assertIn("el MVP pone a prueba la hipótesis más riesgosa (el criterio de descarte)",
                      [p["texto"] for p in self.json()["pasos"]][0])
        write(self.carpeta / "04-prd.md", base.PRD)
        self.cerrar("4")
        salida = self.p("puerta", "--n", 3)
        self.assertIn("✖ El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral", salida)
        write(self.carpeta / "04-prd.md", base.PRD.replace("| 3 | HIP-01 |", "| 3 | HIP-02 |"))
        salida = self.p("puerta", "--n", 3)
        self.assertIn("✔ El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral · HIP-02 en F-01",
                      salida)
        self.assertIn("🟢  PUERTA 3 · VIABLE", salida)

    def test_la_referencia_define_el_dolor_triangulado(self):
        puertas = (SKILL / "references" / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("Viable para probar", puertas)
        self.assertIn("**El dolor está triangulado**", puertas)
        self.assertIn("Viable para probar", (SKILL / "references" / "diferenciacion.md").read_text(encoding="utf-8"))
        self.assertIn("Viable para probar", (SKILL / "SKILL.md").read_text(encoding="utf-8"))


# --- #48 · Tablero siempre al día ----------------------------------------------------------------------------------

class TableroTest(Base):
    def test_nuevo_con_raiz_la_guarda_y_cada_comando_regenera_el_tablero(self):
        raiz = self.tmp / "ideas"
        raiz.mkdir()
        self.carpeta = raiz / "riego" / "product"
        salida = self.nuevo("Riego en turnos", "--raiz", raiz)
        self.assertIn("· Tablero actualizado: %s" % (raiz / "index.html"), salida)
        self.assertEqual(self.datos()["raiz"], os.path.join("..", ".."))
        html = self.tablero(raiz)
        self.assertIn(producto.MARCA_TABLERO, html)
        self.assertIn("Riego en turnos", html)
        self.assertFalse((self.carpeta / "reporte.html").exists())  # nuevo no escribe el reporte
        self.assertFalse((raiz / "riego" / "index.html").exists())
        self.completar("criterios.md")
        self.p("tipo", "--existente", "--provisional", "--motivo", "Triaje inventado")
        self.assertIn("· Tablero actualizado", self.cerrar("0", "00-idea.md"))
        self.assertIn("· Tablero actualizado", self.p("archivar", "--motivo", "La retomo en primavera"))
        self.assertIn("Pausada", self.tablero(raiz))
        salida = self.p("reabrir")
        self.assertIn("· Tablero actualizado", salida)
        self.assertIn("En curso", self.tablero(raiz))
        self.assertIn("--raiz: no existe la carpeta", self.falla("cerrar", "--sesion", "1a", "--raiz", raiz / "nada"))

    def test_sin_raiz_usa_el_tablero_mas_cercano_hacia_arriba(self):
        raiz = self.tmp / "ideas"
        raiz.mkdir()
        # un tablero anterior a la marca: se reconoce por su título y su pie
        write(raiz / "index.html", "<html><head><title>Tablero de ideas</title></head><body><footer>Generado por "
                                   "hb-product 0.1.0.</footer></body></html>")
        self.carpeta = raiz / "riego" / "product"
        self.assertIn("· Tablero actualizado: %s" % (raiz / "index.html"), self.nuevo())
        self.assertIn(producto.MARCA_TABLERO, self.tablero(raiz))
        self.assertFalse((raiz / "riego" / "index.html").exists())
        self.assertNotIn("raiz", self.datos())

    def test_sin_raiz_ni_tablero_usa_la_carpeta_que_contiene_la_idea(self):
        self.assertIn("· Tablero actualizado: %s" % (self.tmp / "index.html"), self.nuevo())
        self.assertIn("Riego en turnos", self.tablero())

    def test_nunca_pisa_un_index_html_que_no_genero_tablero(self):
        ajeno = "<html><body>Mi página</body></html>"
        write(self.tmp / "index.html", ajeno)
        salida = self.nuevo()
        self.assertIn("⚠ Tablero sin actualizar: %s no lo generó `tablero` y no se pisa" % (self.tmp / "index.html"),
                      salida)
        self.assertEqual(self.tablero(), ajeno)
        self.assertIn("no lo generó `tablero`: no se pisa", self.falla("tablero", "--raiz", self.tmp))
        self.assertEqual(self.tablero(), ajeno)

    def test_dentro_de_un_repositorio_sin_raiz_no_crea_un_index_html(self):
        (self.tmp / ".git").mkdir()
        salida = self.nuevo()
        self.assertIn("· Tablero: la carpeta está dentro de un repositorio y no tiene raíz fijada", salida)
        self.assertFalse((self.tmp / "index.html").exists())
        raiz = self.tmp / "ideas"
        raiz.mkdir()
        self.completar("criterios.md")
        self.completar("00-idea.md")
        self.p("tipo", "--existente", "--provisional", "--motivo", "Triaje inventado")
        self.assertIn("· Tablero actualizado: %s" % (raiz / "index.html"), self.p(
            "cerrar", "--sesion", "0", "--raiz", raiz))

    def test_un_fallo_del_tablero_no_hace_fallar_el_comando(self):
        self.debil()
        with mock.patch.object(producto, "escribir_tablero", side_effect=RuntimeError("disco lleno")):
            salida = self.p("decidir", "--puerta", 1, "--seguir", "--motivo", "Quiero probar igual el MVP")
        self.assertIn("⚠ No se pudo actualizar el tablero (RuntimeError: disco lleno); `tablero --raiz <carpeta>` lo "
                      "reintenta.", salida)
        self.assertEqual(self.datos("decisiones.json")[-1]["decision"], "seguir")

    def test_la_raiz_guardada_sobrevive_al_archivo(self):
        raiz = self.tmp / "ideas"
        raiz.mkdir()
        self.carpeta = raiz / "riego" / "product"
        self.nuevo("Riego en turnos", "--raiz", raiz)
        self.p("archivar", "--motivo", "La retomo en primavera")
        archivada = self.carpeta / "archivo" / "riego-en-turnos"
        datos = json.loads((archivada / "producto.json").read_text(encoding="utf-8"))
        self.assertEqual(producto.raiz_tablero(archivada, datos), (raiz, "guardada"))


# --- #49 · Modo autónomo -------------------------------------------------------------------------------------------

class AutonomoTest(Base):
    def test_automatico_aplica_la_recomendacion_y_la_marca_para_revisarla(self):
        self.hasta_puerta1()
        paso = self.json()["pasos"][0]
        self.assertEqual({k: paso["automatico"][k] for k in ("decision", "sesion", "detener", "ajustes_previos")},
                         {"decision": "seguir", "sesion": None, "detener": False, "ajustes_previos": 0})
        self.assertTrue(paso["automatico"]["comando"].endswith("decidir --puerta 1 --automatico --carpeta product"))
        salida = self.p("decidir", "--puerta", 1, "--automatico")
        self.assertIn("· Decisión automática (modo autónomo): la skill aplicó su recomendación, seguir (veredicto: "
                      "Viable;", salida)
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual((decision["decision"], decision["automatica"], decision["contra_recomendacion"]),
                         ("seguir", True, False))
        self.assertEqual(decision["por"], "decisión automática (modo autónomo)")
        self.assertIn("decisión automática (modo autónomo)", (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("Decisión automática: revísala", html)
        self.assertIn("P1 🟢 → seguir (automática)", html)
        self.assertIn("Decisión automática en P1: revísala", self.tablero())
        # reabrirla deshace la marca en el reporte y en el tablero (feedback #50)
        salida = self.p("decidir", "--puerta", 1, "--reabrir")
        self.assertIn("· Reporte actualizado", salida)
        self.assertNotIn("(automática)", (self.carpeta / "reporte.html").read_text(encoding="utf-8"))
        self.assertNotIn("Decisión automática en P1", self.tablero())

    def test_automatico_no_va_en_contra_de_la_recomendacion(self):
        self.debil()
        self.assertIn("--automatico solo aplica la recomendación de la skill: descartar (veredicto: No viable)",
                      self.falla("decidir", "--puerta", 1, "--automatico", "--seguir"))
        self.assertIn("no lleva --motivo", self.falla("decidir", "--puerta", 1, "--automatico", "--motivo",
                                                      "Porque sí, lo quiero"))
        self.assertIn("Elige una decisión", self.falla("decidir", "--puerta", 1))
        salida = self.p("decidir", "--puerta", 1, "--automatico")
        self.assertIn("idea descartada y archivada", salida)
        decision = json.loads((self.carpeta / "archivo" / "riego-en-turnos" / "decisiones.json").read_text(
            encoding="utf-8"))[-1]
        self.assertEqual((decision["decision"], decision["automatica"]), ("descartar", True))
        self.assertTrue(decision["motivo"].startswith("No viable: El puntaje es 14/25"))

    def test_el_tercer_ajuste_de_la_misma_sesion_se_detiene(self):
        self.investigacion()
        self.p("confianza", "--hallazgo", "H-MON-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        self.cerrar("1f", "01-sintesis.md")
        for vuelta in range(2):
            automatico = self.json()["pasos"][0]["automatico"]
            self.assertEqual((automatico["decision"], automatico["sesion"], automatico["ajustes_previos"],
                              automatico["detener"]), ("ajustar", "1d", vuelta, False))
            self.assertIn("ajustar la sesión 1d", self.p("decidir", "--puerta", 1, "--automatico"))
            self.cerrar("1d")
            self.cerrar("1f")
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["ajustes_previos"], automatico["detener"]), (2, True))
        self.assertIn("por tercera vez", automatico["motivo"])
        error = self.falla("decidir", "--puerta", 1, "--automatico")
        self.assertIn("Modo autónomo: aquí se detiene y le pregunta al usuario, porque la puerta 1 pide ajustar la "
                      "sesión 1d por tercera vez (ya se ajustó 2 veces)", error)
        self.p("decidir", "--puerta", 1, "--ajustar", "1d")  # el usuario sí puede decidirlo

    def test_un_vacio_de_herramienta_en_la_sesion_a_ajustar_se_detiene(self):
        self.investigacion()
        self.p("confianza", "--hallazgo", "H-MON-1", "--bajar", "baja", "--motivo", "Las fuentes se contradicen")
        self.p("objetivo", "--mercados", "MX,AR", "--motivo", "Sumamos Argentina")
        self.p("vacio", "--linea", "monetizacion", "--mercado", "AR", "--motivo", "herramienta", "--texto",
               "Página dinámica")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        self.cerrar("1f", "01-sintesis.md")
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertTrue(automatico["detener"])
        self.assertIn("un navegador en el agente o un CSV de reseñas que aporte el usuario", automatico["motivo"])

    def test_la_sesion_0_trae_el_texto_del_modo_autonomo(self):
        paso = self.json()["pasos"][0]
        self.assertIn("Usa hb-product en modo autónomo, sin preguntas:", paso["texto_autonomo"])
        self.assertIn("«Supuestos sin confirmar» de 00-idea.md", paso["texto_autonomo"])

    def test_la_referencia_los_prompts_y_la_skill_describen_el_modo_autonomo(self):
        orquestacion = (SKILL / "references" / "orquestacion.md").read_text(encoding="utf-8")
        for texto in ("## Modo autónomo", "decidir --automatico", "automatico.detener", "texto_autonomo"):
            self.assertIn(texto, orquestacion)
        self.assertIn("modo autónomo", (SKILL / "references" / "prompts.md").read_text(encoding="utf-8"))
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--automatico", skill)
        self.assertLessEqual(len(skill.splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
