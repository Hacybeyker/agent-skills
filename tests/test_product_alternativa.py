"""Tests de las mejoras #60, #61 y #62 de hb-product: la fila del chat orquestador (`consumo --chat`), que el mismo chat
actualiza en cada parada sin contar dos veces su /cost acumulado (#60); la alternativa al principal que la puerta 2
recomienda, que pasa la misma regla de «sobrevive» con sus propias hipótesis (#61), y las fricciones menores de #62:
el presupuesto de las sesiones 2 y 3, el mensaje del resumen demasiado largo, el estado de cada pasada en el aviso de
presupuesto excedido y las opciones de `confianza` en SKILL.md.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_veredicto as veredicto
from helpers import write

HOY = base.HOY
producto = base.producto

# D-1 (el principal) débil; D-2, según la prueba: {d2} es la fila de su hipótesis (o nada)
HIPOTESIS = """# Validación

| ID | Hipótesis | Hallazgos | En contra | Diferenciador | Veredicto | Más riesgosa | Métrica y umbral |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HIP-01 | Los vecinos quieren repartir el riego | H-DEM-1 | Se buscaron apps de riego cerradas: nada | — | sostenida | sí | 30 % vuelve a los 30 días |
| HIP-02 | El pago único atrae a quien no quiere suscripción | H-VOZ-1 | Quejas inventadas por pagos únicos | D-1 | débil | — | — |
{d2}"""

D2_SOSTENIDA = ("| HIP-03 | El registro sin anuncios gana frente al rival | H-VOZ-1 | Se buscaron quejas: nada | D-2 | "
                "sostenida | — | — |\n")
D2_DEBIL = ("| HIP-03 | El registro sin anuncios gana frente al rival | H-VOZ-1 | Una reseña inventada en contra | D-2 | "
            "débil | — | — |\n")


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(veredicto.Base):
    def json(self):
        return json.loads(self.p("siguiente", "--json").strip().splitlines()[-1])


# --- #61 · La alternativa al principal también sobrevive ------------------------------------------------------------

class AlternativaTest(Base):
    def cerrar(self, sesion, archivo=None):
        if sesion == "1g" and not self.datos("01-investigacion/diferenciacion.json").get("diferenciadores", [])[1:]:
            # un segundo diferenciador viable, con el mismo dolor triangulado y que también supera al rival
            self.p("diferenciador", "--vector", "anuncios", "--texto", "Registro sin anuncios", "--hallazgos",
                   "H-VOZ-1", "--se-ve", "uso", "--copiable", "media", "--motivo", "El rival vive de sus anuncios",
                   "--semanas", 1)
            self.p("frente", "--id", "D-2", "--resultado", "supera", "--hallazgos", "H-VOZ-1", "--texto",
                   "PlantaPlus muestra anuncios al registrar")
        return super().cerrar(sesion, archivo)

    def puerta2(self, d2):
        self.hasta_puerta2()
        write(self.carpeta / "03-validacion.md", HIPOTESIS.format(d2=d2))
        return self.p("puerta", "--n", 2)

    def test_hay_dos_viables(self):
        self.hasta_puerta1()
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.assertEqual([d["id"] for d in registro.viables()], ["D-1", "D-2"])

    def test_la_alternativa_que_sobrevive_se_recomienda_como_principal(self):
        salida = self.puerta2(D2_SOSTENIDA)
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("El principal (D-1) no sobrevive al abogado del diablo, pero D-2 sí sobrevive", salida)
        self.assertIn("Llevar D-2 a principal (1g)", salida)
        self.assertIn("Con eso, el veredicto pasaría a Viable", salida)
        self.assertIn("· otros viables: D-2 sobrevive", salida)

    def test_la_alternativa_debil_no_se_recomienda_como_principal(self):
        salida = self.puerta2(D2_DEBIL)
        # débiles y sin refutar: falta evidencia, que se busca en la sesión 3 (feedback #64), no llevar D-2 a principal
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 3", salida)
        self.assertIn("El principal (D-1) no sobrevive al abogado del diablo y ningún otro viable sobrevive (D-1: "
                      "HIP-02 débil (confianza alta); D-2: HIP-03 débil (confianza alta))", salida)
        self.assertIn("· otros viables: D-2 no sobrevive: HIP-03 débil (confianza alta)", salida)
        self.assertNotIn("Llevar D-2", salida)

    def test_la_alternativa_sin_hipotesis_no_sobrevive(self):
        salida = self.puerta2("")
        self.assertIn("D-2 no sobrevive: ninguna hipótesis lo pone a prueba en 03-validacion.md", salida)
        self.assertIn("AJUSTAR 3", salida)  # sin poner a prueba no es evidencia en contra (feedback #63)
        self.assertIn("poner a prueba D-2 con una hipótesis (con D-2 en la columna Diferenciador), buscando evidencia "
                      "en contra, para llevarlo a principal en la 1g", salida)

    def test_la_regla_es_la_misma_funcion_para_los_dos(self):
        self.puerta2(D2_DEBIL)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        filas = producto.hipotesis(self.carpeta, registro)
        alternativas = producto.alternativas_validadas(filas, registro, registro.principal())
        self.assertEqual(alternativas["sobreviven"], [])
        self.assertEqual(alternativas["no"], [("D-2", "HIP-03 débil (confianza alta)")])
        # la más riesgosa débil no cuenta con un criterio de descarte vigente (la puerta 1 fue Viable para probar)
        filas = [dict(f, riesgosa=f["id"] == "HIP-03") for f in filas]
        self.assertTrue(producto.sobrevive_abogado(filas, registro.diferenciadores["D-2"], {"texto": "x"})[0])
        self.assertFalse(producto.sobrevive_abogado(filas, registro.diferenciadores["D-2"], None)[0])

    def sin_principal(self):
        ruta = self.carpeta / "01-investigacion" / "diferenciacion.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        for diferenciador in datos["diferenciadores"]:
            diferenciador["principal"] = False
        ruta.write_text(json.dumps(datos), encoding="utf-8")

    def test_sin_principal_solo_se_elige_uno_que_sobreviva(self):
        self.puerta2(D2_SOSTENIDA)
        self.sin_principal()
        salida = self.p("puerta", "--n", 2)
        self.assertIn("AJUSTAR 1g", salida)
        self.assertIn("No hay un diferenciador principal elegido, pero D-2 sobrevive al abogado del diablo", salida)
        self.assertIn("Elegir el principal entre los que sobreviven (D-2) en la 1g", salida)
        write(self.carpeta / "03-validacion.md", HIPOTESIS.format(d2=D2_DEBIL))
        salida = self.p("puerta", "--n", 2)
        self.assertIn("AJUSTAR 3", salida)  # a los dos les falta evidencia, no tienen evidencia en contra (#64)
        self.assertIn("No hay un diferenciador principal y ningún viable sobrevive al abogado del diablo (D-1: "
                      "HIP-02 débil (confianza alta); D-2: HIP-03 débil (confianza alta)), pero solo por hipótesis "
                      "débiles", salida)
        self.assertIn("fortalecer las hipótesis de D-1, para elegirlo como principal en la 1g: HIP-02", salida)

    def test_la_puerta_3_sin_principal_usa_la_misma_regla(self):
        self.puerta2(D2_SOSTENIDA)
        self.p("decidir", "--puerta", 2, "--seguir", "--motivo", "Quiero ver el PRD antes de cambiar el principal")
        write(self.carpeta / "04-prd.md", base.PRD)
        self.cerrar("4")
        self.sin_principal()
        salida = self.p("puerta", "--n", 3)
        self.assertIn("Elegir el principal entre los que sobreviven (D-2) en la 1g", salida)
        write(self.carpeta / "03-validacion.md", HIPOTESIS.format(d2=D2_DEBIL))
        self.assertIn("🟡  PUERTA 3 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 3", self.p("puerta", "--n", 3))

    def test_la_referencia_dice_cuando_una_de_canal_o_de_pago_lleva_el_diferenciador(self):
        texto = (base.SKILL / "references" / "validacion.md").read_text(encoding="utf-8")
        self.assertIn("Una de canal o de pago lo lleva cuando pone a prueba el valor de ese diferenciador", texto)
        self.assertIn("Otro diferenciador viable pasa la misma regla con sus propias hipótesis", texto)
        puertas = (base.SKILL / "references" / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("La alternativa al principal también sobrevive (P2)", puertas)


# --- #60 · La fila del chat orquestador -------------------------------------------------------------------------------

class ChatOrquestadorTest(Base):
    def orquestador(self, *args):
        return [f for f in self.datos()["consumo"] if f["sesion"] == "orquestador"]

    def test_el_mismo_chat_actualiza_su_fila_aunque_no_comparta_sesiones(self):
        self.hasta_puerta1()
        datos = self.json()
        self.assertEqual((datos["costo"]["chat"], datos["costo"]["chat_nuevo"]), ("orq-1", "orq-1"))
        self.assertIn("--costo '<USD que muestra /cost>' --chat orq-1", datos["costo"]["comando_orquestador"])
        self.p("consumo", "--sesion", "orquestador", "--incluye", "0,1a,1b,1c,1d,1e,1g,1f", "--costo", "3.00",
               "--chat", "orq-1")
        datos = self.json()
        self.assertEqual((datos["costo"]["chat"], datos["costo"]["chat_nuevo"]), ("orq-1", "orq-2"))
        self.assertIn("si este chat no anotó antes, usa --chat orq-2", datos["costo"]["recordatorio"])
        # la parada siguiente del mismo chat: otras sesiones, el /cost acumulado
        salida = self.p("consumo", "--sesion", "orquestador", "--incluye", "2", "--costo", "4.50", "--chat", "orq-1")
        self.assertIn("total anotado: 4,50 USD", salida)
        filas = self.orquestador()
        self.assertEqual(len(filas), 1)
        self.assertEqual((filas[0]["chat"], filas[0]["costo"], filas[0]["incluye"][-1]), ("orq-1", 4.5, "2"))
        self.assertIn("orquestador (orq-1)", self.p("consumo"))

    def test_otro_chat_va_en_otra_fila(self):
        self.hasta_puerta1()
        self.p("consumo", "--sesion", "orquestador", "--incluye", "0,1a", "--costo", "3.00", "--chat", "orq-1")
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1b", "--costo", "1.00", "--chat", "orq-2")
        self.assertEqual([(f["chat"], f["costo"]) for f in self.orquestador()], [("orq-1", 3.0), ("orq-2", 1.0)])
        self.assertIn("Total: 4 USD", self.p("consumo"))
        self.assertEqual(self.json()["costo"]["chat"], "orq-2")  # el último que anotó

    def test_una_fila_anotada_sin_chat_es_orq_1_y_se_actualiza(self):
        self.hasta_puerta1()
        self.p("consumo", "--sesion", "orquestador", "--incluye", "0,1a", "--costo", "3.00")
        datos = self.datos()
        for fila in datos["consumo"]:
            fila.pop("chat", None)  # como la anotó una versión anterior
        (self.carpeta / "producto.json").write_text(json.dumps(datos), encoding="utf-8")
        self.assertIn("--chat orq-1", self.json()["costo"]["comando_orquestador"])
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1b", "--costo", "4.50", "--chat", "orq-1")
        filas = self.orquestador()
        self.assertEqual([(f["chat"], f["costo"], f["incluye"]) for f in filas], [("orq-1", 4.5, ["0", "1a", "1b"])])

    def test_sin_chat_cada_fila_nueva_queda_con_el_suyo(self):
        self.hasta_puerta1()
        self.p("consumo", "--sesion", "orquestador", "--incluye", "0", "--costo", "1")
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1a", "--costo", "2")  # otro chat (como antes)
        self.assertEqual([f["chat"] for f in self.orquestador()], ["orq-1", "orq-2"])

    def test_chat_solo_va_con_el_orquestador_y_sin_espacios(self):
        self.hasta_puerta1()
        self.assertIn("--chat va con --sesion orquestador", self.falla("consumo", "--sesion", "1a", "--costo", "1",
                                                                       "--chat", "orq-1"))
        self.assertIn("--chat es un nombre corto", self.falla("consumo", "--sesion", "orquestador", "--costo", "1",
                                                              "--chat", "mi chat"))

    def test_la_regla_esta_en_la_referencia_y_en_el_prompt(self):
        for nombre in ("orquestacion.md", "prompts.md", "modelos.md"):
            texto = (base.SKILL / "references" / nombre).read_text(encoding="utf-8")
            self.assertIn("--chat", texto, nombre)
        texto = (base.SKILL / "references" / "orquestacion.md").read_text(encoding="utf-8")
        self.assertIn("Cada chat anota siempre con el mismo `--chat`", texto)
        self.assertIn("costo.chat_nuevo", texto)


# --- #62 · Fricciones menores -----------------------------------------------------------------------------------------

class FriccionesTest(Base):
    def test_las_sesiones_2_y_3_anotan_su_presupuesto_y_la_puerta_2_avisa(self):
        self.hasta_puerta1()
        self.p("decidir", "--puerta", 1, "--seguir")
        self.escenarios()
        self.completar("02-estrategia.md")
        salida = self.p("cerrar", "--sesion", "2", "--busquedas", 16, "--lecturas", 3)
        self.assertIn("· Presupuesto usado por la línea estrategia: 16 de 15 búsquedas y 3 de 10 lecturas en la "
                      "primera pasada.", salida)
        self.assertIn("⚠ Esta pasada se pasó de su presupuesto: la puerta 2 lo muestra; dilo en el entregable.", salida)
        write(self.carpeta / "03-validacion.md", base.HIPOTESIS)
        salida = self.p("cerrar", "--sesion", "3", "--busquedas", 4, "--lecturas", 2)
        self.assertIn("4 de 15 búsquedas y 2 de 10 lecturas en la primera pasada", salida)
        self.assertNotIn("se pasó", salida)
        self.assertEqual(self.datos()["sesiones"]["3"]["uso"], {"busquedas": 4, "lecturas": 2})
        salida = self.p("puerta", "--n", 2)
        self.assertIn("⚠ Presupuesto excedido: 2: primera pasada con 16 de 15 búsquedas. Dilo en la decisión.", salida)
        self.assertIn("🟢  PUERTA 2 · VIABLE", salida)  # es un aviso, no un criterio
        self.assertIn("Presupuesto excedido:** 2: primera pasada con 16 de 15 búsquedas",
                      (self.carpeta / "estado.md").read_text(encoding="utf-8"))

    def test_las_demas_sesiones_no_anotan_busquedas(self):
        self.hasta_puerta1()
        self.assertIn("1a a 1e, 1g, 2 y 3", self.falla("cerrar", "--sesion", "1f", "--busquedas", 1))

    def test_el_resumen_largo_dice_el_limite_real(self):
        self.nuevo()
        args = ["fuente", "--linea", "competencia", "--url", "https://sitio.example/a", "--publicada", "2026-06",
                "--tipo", "terceros", "--peldano", 1, "--resumen"]
        error = self.falla(*args, "x" * 450)
        self.assertIn("El resumen de una fuente tiene 400 caracteres como máximo (y 3 líneas): este tiene 450, "
                      "sobran 50", error)
        self.assertNotIn("1 líneas", error)
        self.assertIn("3 líneas como máximo: este tiene 4", self.falla(*args, "a\nb\nc\nd"))

    def test_el_aviso_de_presupuesto_dice_el_estado_de_cada_pasada(self):
        datos = {"tipo": {"valor": "existente"}, "sesiones": {"1d": {"pasadas": [
            {"reapertura": 1, "busquedas": 3, "lecturas": 4, "presupuesto": {"busquedas": 8, "lecturas": 5}},
            {"reapertura": 0, "busquedas": 15, "lecturas": 11, "presupuesto": {"busquedas": 15, "lecturas": 10}}]},
            "1c": {"pasadas": [
                {"reapertura": 0, "busquedas": 9, "lecturas": 4, "presupuesto": {"busquedas": 15, "lecturas": 10}}]}}}
        excedidas = producto.pasadas_excedidas(datos)
        self.assertEqual(excedidas, [("1d", "primera pasada con 11 de 10 lecturas; reapertura 1 dentro del "
                                            "presupuesto")])  # la 1c, dentro: no se nombra
        datos["sesiones"]["1d"]["pasadas"][0].update(busquedas=9, lecturas=6)
        self.assertEqual(producto.texto_excedidas(producto.pasadas_excedidas(datos)),
                         "1d: primera pasada con 11 de 10 lecturas; reapertura 1 con 9 de 8 búsquedas y 6 de 5 "
                         "lecturas")

    def test_skill_muestra_las_opciones_de_confianza(self):
        texto = (base.SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`--hallazgo H-… --bajar media|baja --motivo", texto)
        self.assertLessEqual(len(texto.splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
