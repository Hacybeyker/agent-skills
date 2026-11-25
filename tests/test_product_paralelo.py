"""Tests de las mejoras #65 y #66 de hb-product.

#65: si una puerta pide ajustar varias sesiones que corren en paralelo (2 y 3; 1a a 1e), la recomendación las nombra
juntas y `decidir --ajustar 2 3` (o `--automatico`) las reabre a la vez; en el modo autónomo cada una cuenta para su
tope de tres ajustes.
#66: (a) fortalecer un hallazgo de otra sesión, ya cerrada, desde la que se reabre: el texto de la puerta dice el
camino y `hallazgo --reune` lo registra; (b) `fuente` no cuenta en «esta reapertura» los extractos de pasadas
anteriores; (c) la confianza de una fila de hipótesis es la de sus hallazgos clave.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_fortalecer as fortalecer
from helpers import write

HOY = base.HOY
producto = base.producto
tabla = fortalecer.tabla


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(fortalecer.Base):
    def puerta_2_y_3(self):
        """La puerta 2 con un ajuste de la sesión 3 (HIP-02, la del principal, débil) y otro de la sesión 2 (una
        propuesta pendiente para ella): dos sesiones que corren en paralelo."""
        self.puerta2(tabla())
        self.p("propuesta", "--texto", "Revisar el precio inventado del pago único", "--ajustar", "2")
        return self.p("puerta", "--n", 2)


# --- #65 · Las sesiones que corren en paralelo se ajustan juntas -------------------------------------------------

class ParaleloTest(Base):
    def test_la_recomendacion_las_nombra_juntas(self):
        salida = self.puerta_2_y_3()
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 2 y 3", salida)
        self.assertIn("Ajustar la sesión 3, una sola vez, para fortalecer las hipótesis de D-1", salida)
        self.assertIn("Aplicarla al ajustar la sesión 2", salida)
        self.assertIn("★ Recomendado · Ajustar 2 y 3: ", salida)
        self.assertIn("decidir --puerta 2 --ajustar 2 3 --carpeta", salida)
        paso = self.json()["pasos"][0]
        self.assertEqual(paso["veredicto"]["sesiones"], ["2", "3"])
        self.assertEqual(paso["veredicto"]["sesion"], "3")  # la primera por el orden de los criterios, la de siempre
        self.assertEqual(paso["recomendacion"], "ajustar las sesiones 2 y 3")
        self.assertEqual((paso["automatico"]["sesiones"], paso["automatico"]["detener"]), (["2", "3"], False))

    def test_una_sola_sesion_no_cambia(self):
        salida = self.puerta2(tabla())
        self.assertIn("la skill recomienda: AJUSTAR 3\n", salida)
        self.assertIn("decidir --puerta 2 --ajustar 3 --carpeta", salida)
        self.assertEqual(self.json()["pasos"][0]["veredicto"]["sesiones"], ["3"])

    def test_decidir_las_reabre_a_la_vez(self):
        self.puerta_2_y_3()
        salida = self.p("decidir", "--puerta", 2, "--ajustar", "2", "3")
        self.assertIn("· Coincide con la recomendación de la skill", salida)
        self.assertIn("✔ Puerta 2 · Viabilidad: ajustar las sesiones 2 y 3", salida)
        self.assertIn("· Se reabren: 2, 3.", salida)
        self.assertIn("2 y 3 corren en paralelo", salida)
        datos = self.datos()
        self.assertFalse(producto.cerrada(datos, "2") or producto.cerrada(datos, "3"))
        decision = self.datos("decisiones.json")[-1]
        self.assertEqual((decision["sesion"], decision["sesiones"]), ("2", ["2", "3"]))
        self.assertEqual(decision["recomendacion"]["sesiones"], ["2", "3"])
        # lo que tiene que conseguir cada una: la 3, solo lo suyo
        self.assertTrue(decision["resolver_sesiones"]["3"][0].startswith("Ajustar la sesión 3, una sola vez"))
        self.assertEqual(decision["resolver_sesiones"]["2"], ["Aplicarla al ajustar la sesión 2"])
        texto = producto.texto_sesion(self.carpeta, datos, "3")
        self.assertIn("Lo que tiene que conseguir, según la puerta: «Ajustar la sesión 3", texto)
        self.assertNotIn("Aplicarla", texto)
        self.assertIn("ajustar las sesiones 2 y 3", (self.carpeta / "estado.md").read_text(encoding="utf-8"))

    def test_con_comas_tambien(self):
        self.puerta_2_y_3()
        self.assertIn("Coincide con la recomendación", self.p("decidir", "--puerta", 2, "--ajustar", "3,2"))

    def test_solo_una_va_en_contra_de_la_recomendacion(self):
        self.puerta_2_y_3()
        error = self.falla("decidir", "--puerta", 2, "--ajustar", "3")
        self.assertIn("La skill recomienda ajustar las sesiones 2 y 3", error)
        self.assertIn("Para ajustar la sesión 3 en contra de la recomendación, agrega --motivo", error)
        salida = self.p("decidir", "--puerta", 2, "--ajustar", "3", "--motivo", "Primero la validación, luego el precio")
        self.assertIn("⚠ Decisión contra la recomendación", salida)
        self.assertTrue(producto.cerrada(self.datos(), "2"))

    def test_solo_se_reabren_juntas_las_que_corren_en_paralelo(self):
        self.puerta_2_y_3()
        error = self.falla("decidir", "--puerta", 2, "--ajustar", "1c", "3", "--motivo", "Una prueba inventada aquí")
        self.assertIn("Solo se reabren a la vez sesiones que corren en paralelo (1a, 1b, 1c, 1d y 1e; 2 y 3): 1c y 3 "
                      "no.", error)

    def test_automatico_las_reabre_y_cada_una_cuenta_para_su_tope(self):
        self.puerta_2_y_3()
        salida = self.p("decidir", "--puerta", 2, "--automatico")
        self.assertIn("la skill aplicó su recomendación, ajustar las sesiones 2 y 3", salida)
        lista = producto.decisiones(self.carpeta)
        self.assertEqual([producto.ajustes_previos(lista, 2, s) for s in ("2", "3")], [1, 1])
        self.assertFalse(producto.cerrada(self.datos(), "2") or producto.cerrada(self.datos(), "3"))

    def test_el_autonomo_se_detiene_si_una_llega_al_tope(self):
        self.puerta_2_y_3()
        lista = self.datos("decisiones.json")
        for _ in range(2):  # la sesión 2 ya se ajustó dos veces en esta puerta
            lista.append({"puerta": 2, "decision": "ajustar", "sesion": "2", "vigente": False, "fecha": HOY})
        write(self.carpeta / "decisiones.json", json.dumps(lista))
        automatico = self.json()["pasos"][0]["automatico"]
        self.assertEqual((automatico["detener"], automatico["ajustes_previos"]), (True, 2))
        self.assertIn("pide ajustar la sesión 2 por tercera vez", automatico["motivo"])
        self.assertIn("Modo autónomo: aquí se detiene", self.falla("decidir", "--puerta", 2, "--automatico"))

    def test_los_grupos(self):
        self.assertEqual(producto.grupo_paralelo("1c"), ("1a", "1b", "1c", "1d", "1e"))
        self.assertEqual(producto.grupo_paralelo("3"), ("2", "3"))
        self.assertEqual(producto.grupo_paralelo("1g"), ("1g",))  # lee la 1a y la 1b: va en cascada
        self.assertEqual(producto.sesiones_de({"sesion": "2", "sesiones": ["2", "3"]}), ["2", "3"])
        self.assertEqual(producto.sesiones_de({"sesion": "1c"}), ["1c"])
        self.assertEqual(producto.texto_ajuste({"sesion": None}), "")


# --- #66 (a) · Fortalecer un hallazgo de otra sesión ----------------------------------------------------------------

class ReunirTest(Base):
    def con_hallazgo_de_la_1b(self):
        """La puerta 2 con HIP-02 (la del principal) apoyada en un hallazgo débil de la 1b, ya cerrada."""
        self.hasta_puerta2()
        identificador, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 1, "usuario"),
                                         "--sin-contra", "Se buscó y no apareció", "--critico")
        write(self.carpeta / "03-validacion.md", tabla(hallazgos=identificador))
        return identificador

    def test_que_cambiaria_dice_el_camino(self):
        identificador = self.con_hallazgo_de_la_1b()
        salida = self.p("puerta", "--n", 2)
        self.assertIn("AJUSTAR 3", salida)
        self.assertIn("HIP-02, triangulando %s (de la 1b: faltan 2 fuentes independientes y vigentes" % identificador,
                      salida)
        self.assertIn("%s es de otra sesión, ya cerrada: en la sesión 3 se fortalece con un hallazgo nuevo de la línea "
                      "validacion que lo reúna con las fuentes nuevas (`hallazgo --linea validacion --reune %s --fuentes "
                      "S-… --texto \"…\"`); ese hallazgo nuevo se cita en su lugar (en la columna Hallazgos de su "
                      "hipótesis, en 03-validacion.md)" % (identificador, identificador), salida)
        # la reapertura de la 3 lo repite (sin el comando, que está en validacion.md)
        self.p("decidir", "--puerta", 2, "--ajustar", "3")
        self.assertIn("%s es de otra sesión, ya cerrada: en la sesión 3 se fortalece con un hallazgo nuevo" %
                      identificador, producto.texto_sesion(self.carpeta, self.datos(), "3"))

    def test_un_hallazgo_de_la_misma_sesion_no_lleva_el_camino(self):
        identificador = self.con_hallazgo_debil()
        salida = self.p("puerta", "--n", 2)
        self.assertIn("triangulando %s (faltan" % identificador, salida)
        self.assertNotIn("--reune", salida)

    def test_reune_lleva_las_fuentes_y_las_reglas_del_original(self):
        self.hasta_puerta2()
        favor = self.fuente("demanda", 1, "terceros")
        contra = self.fuente("demanda", 1, "terceros")
        original, _ = self.hallazgo("demanda", favor, "--en-contra", contra[0], "--critico")
        nuevas = self.fuente("validacion", 2, "usuario")
        identificador, salida = self.hallazgo("validacion", nuevas, "--reune", original)
        self.assertIn("· Reúne %s: sus fuentes a favor y en contra, con las reglas de triangulación de la línea "
                      "validacion y la línea demanda." % original, salida)
        self.assertIn("cita ahora %s en su lugar" % identificador, salida)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        hallazgo = registro.hallazgos[identificador]
        self.assertEqual(hallazgo["fuentes"], favor + nuevas)
        self.assertEqual(hallazgo["en_contra"], contra)
        self.assertEqual((hallazgo["reune"], hallazgo["reglas"], hallazgo["critico"]), ([original], ["demanda"], True))
        evaluacion = registro.evaluar(hallazgo)
        self.assertEqual(evaluacion["confianza"], "baja")
        # sigue la regla de la demanda: sin una fuente medida no se triangula
        self.assertIn("falta una fuente de tipo medido (línea demanda)", evaluacion["faltan"])
        self.assertIn(original, registro.hallazgos)  # el original sigue registrado

    def test_reune_sin_reglas_ajenas_no_cambia_la_evaluacion(self):
        self.hasta_puerta2()
        original, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 2, "usuario"), "--sin-contra",
                                    "nada")
        self.p("confianza", "--hallazgo", original, "--bajar", "baja", "--motivo", "Dos reseñas inventadas y viejas")
        identificador, salida = self.hallazgo("validacion", self.fuente("validacion", 2, "usuario"), "--reune",
                                              original)
        self.assertIn("sus fuentes a favor y en contra y su confianza bajada a mano", salida)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        evaluacion = registro.evaluar(registro.hallazgos[identificador])
        self.assertEqual((evaluacion["independientes"], evaluacion["exige_medido"]), (4, False))
        self.assertEqual(evaluacion["confianza"], "baja")  # la bajada a mano viaja con sus fuentes
        self.assertEqual(registro.hallazgos[identificador]["sin_contra"], "nada")

    def test_reune_pide_un_hallazgo_de_otra_linea(self):
        self.hasta_puerta2()
        propio, _ = self.hallazgo("validacion", self.fuente("validacion", 1), "--sin-contra", "nada")
        error = self.falla("hallazgo", "--linea", "validacion", "--texto", "x", "--fuentes",
                           ",".join(self.fuente("validacion", 1)), "--reune", propio)
        self.assertIn("%s ya es de la línea validacion: súmale las fuentes con `hallazgo --id %s --fuentes S-…`" % (
            propio, propio), error)
        self.assertIn("H-DEM-99 no existe", self.falla("hallazgo", "--linea", "validacion", "--texto", "x",
                                                       "--fuentes", "S-VAL-1", "--reune", "H-DEM-99"))
        self.assertIn("--reune no va", self.falla("hallazgo", "--id", propio, "--fuentes", "S-VAL-1", "--reune",
                                                  "H-DEM-1"))

    def test_la_guia_lo_dice(self):
        validacion = (base.SKILL / "references" / "validacion.md").read_text(encoding="utf-8")
        self.assertIn("**Fortalecer un hallazgo de otra sesión.**", validacion)
        self.assertIn("cita el nuevo en lugar del original", validacion)
        self.assertIn("--reune H-…", (base.SKILL / "SKILL.md").read_text(encoding="utf-8"))


# --- #66 (b) · Los extractos de pasadas anteriores no son de esta reapertura ---------------------------------------

class ExtractosReaperturaTest(Base):
    def extracto(self):
        self.sitio += 1
        return self.p("fuente", "--linea", "validacion", "--url", "https://extracto%d.example/x" % self.sitio,
                      "--publicada", "2026-06", "--tipo", "terceros", "--peldano", 1, "--resumen", "Dato inventado",
                      "--mercados", "MX", "--extracto")

    def test_solo_cuenta_los_de_esta_pasada(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--ajustar", "3", "--motivo", "Una reapertura inventada para probar")
        self.assertIn("más 1 extracto de búsqueda", self.extracto())
        self.cerrar("3")
        self.p("decidir", "--puerta", 2, "--ajustar", "3", "--motivo", "Otra reapertura inventada para probar")
        self.assertEqual(len(self.datos()["sesiones"]["3"]["extractos_base"]), 1)
        salida = self.extracto()
        self.assertIn("Fuentes de la línea validacion en esta reapertura: 0", salida)
        self.assertIn("más 1 extracto de búsqueda, que no cuenta como lectura", salida)
        self.assertNotIn("más 2 extractos", salida)

    def test_sin_el_dato_de_antes_cuenta_todos(self):
        self.hasta_puerta2()
        self.p("decidir", "--puerta", 2, "--ajustar", "3", "--motivo", "Una reapertura inventada para probar")
        self.extracto()
        datos = self.datos()
        del datos["sesiones"]["3"]["extractos_base"]  # una reapertura de antes de #66
        write(self.carpeta / "producto.json", json.dumps(datos))
        self.assertIn("más 2 extractos de búsqueda", self.extracto())


# --- #66 (c) · La confianza de una fila de hipótesis es la de sus hallazgos clave ------------------------------------

class ConfianzaFilaTest(Base):
    def filas(self, hallazgos):
        write(self.carpeta / "03-validacion.md", tabla(hallazgos=hallazgos))
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        return {f["id"]: f for f in producto.hipotesis(self.carpeta, registro)}

    def test_un_hallazgo_que_solo_complementa_no_baja_la_fila(self):
        self.hasta_puerta2()
        clave, _ = self.hallazgo("validacion", self.fuente("validacion", 3, "usuario"), "--sin-contra", "nada",
                                 "--critico")
        complemento, _ = self.hallazgo("validacion", self.fuente("validacion", 1), "--sin-contra", "nada")
        fila = self.filas("%s, %s" % (clave, complemento))["HIP-02"]
        self.assertEqual((fila["nivel"], fila["claves"]), (3, [clave]))
        # si el débil también es clave, la fila toma el menor
        debil, _ = self.hallazgo("validacion", self.fuente("validacion", 1), "--sin-contra", "nada", "--critico")
        self.assertEqual(self.filas("%s, %s" % (clave, debil))["HIP-02"]["nivel"], 1)
        # sin ninguno clave, el menor de todos
        self.assertEqual(self.filas(complemento)["HIP-02"]["nivel"], 1)

    def test_la_guia_lo_dice(self):
        validacion = (base.SKILL / "references" / "validacion.md").read_text(encoding="utf-8")
        self.assertIn("la menor de sus **hallazgos clave**", validacion)


class DocumentacionTest(unittest.TestCase):
    def test_las_referencias_dicen_la_regla(self):
        puertas = (base.SKILL / "references" / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("Las sesiones que corren en paralelo se ajustan juntas", puertas)
        self.assertIn("`sesiones`", (base.SKILL / "references" / "orquestacion.md").read_text(encoding="utf-8"))
        self.assertIn("`--ajustar 2 3`", (base.SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("cuenta solo los extractos de esta pasada",
                      (base.SKILL / "references" / "investigacion.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
