"""Tests de las mejoras #67 y #68 de hb-product.

#67: un hallazgo que cita a mano (sin `--reune`) las fuentes de otra línea sigue sus reglas de triangulación: con la
mitad o más de sus fuentes de la demanda, la monetización o las políticas, las de esa línea; con las fuentes de un
hallazgo ya registrado de otra línea, lo reúne igual (lo que tiene en contra, su confianza bajada y sus reglas).
#68: un hallazgo del dolor de un diferenciador no es prueba de elección en su `frente` (sí cuenta para «supera»), y los
menores: el resumen de un extracto que pasa a leído, un `hallazgo` que falla no gasta su ID y `fuente --misma-lectura`.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import re
import unittest

import test_product as base
import test_product_rival as rival

HOY = base.HOY
producto = base.producto


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


# --- #68 · Un hallazgo del dolor no es prueba de elección ----------------------------------------------------------

class DolorTest(rival.Base):
    def test_una_comparacion_que_solo_cita_el_dolor_no_tiene_prueba_de_eleccion(self):
        voz = self.hasta_1g()
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", voz, "--texto",
                        "Las reseñas de PlantaPlus piden quitar la suscripción")
        self.assertIn("· Sin prueba de elección (la comparación con C-2 (PlantaPlus) solo cita el dolor, %s, que "
                      "muestra que el rival falla y no que la gente elija la app por eso)" % voz, salida)
        # para «supera» sí cuenta: sigue viable
        self.assertIn("✔ D-1: viable", salida)
        self.assertIn("✔ Frente al rival: supera a C-2 (PlantaPlus) con %s" % voz, salida)
        self.assertIn("· Frente a C-2 (PlantaPlus) solo cita el dolor (%s): cuenta para superarlo, pero no es prueba "
                      "de elección; falta un hallazgo de la comparación distinto del dolor" % voz, salida)
        # `diferenciador` (y `principal`) lo repiten al mostrar la viabilidad
        self.assertIn("solo cita el dolor (%s)" % voz, self.p("principal", "--id", "D-1"))
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.p("puntaje", "--valores", "4,4,4,4,3")
        self.cerrar("1f", "01-sintesis.md")
        salida = self.p("puerta", "--n", 1)
        # antes de #68 daba 🟢 Viable: ahora el dolor está triangulado y falta la elección, que se prueba después
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("solo cita el dolor, %s" % voz, salida)
        self.assertIn("Un hallazgo de la comparación, distinto del dolor, triangulado y en confianza alta, de que la "
                      "gente elige la app por D-1", salida)

    def test_con_un_hallazgo_propio_de_la_comparacion_hay_prueba(self):
        voz = self.hasta_1g()
        propio = self.comparacion_alta()
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, propio),
                        "--texto", "Sin suscripción, y quienes la dejaron lo dicen")
        self.assertIn("· %s es el dolor de D-1 (`diferenciador --hallazgos`, o sus mismas fuentes): cuenta para "
                      "superar al rival, no como prueba de elección" % voz, salida)
        self.assertIn("· Con prueba de elección: todos los hallazgos de la comparación están triangulados y en "
                      "confianza alta, y al menos uno es distinto del dolor.", salida)
        self.assertNotIn("solo cita el dolor", salida)

    def test_un_hallazgo_con_las_mismas_fuentes_del_dolor_tambien_es_el_dolor(self):
        voz = self.hasta_1g()
        fuentes = self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"][0]["fuentes"]
        # dos de las tres fuentes del dolor, con otro texto: es el mismo dolor dicho de otra forma
        copia, _ = self.hallazgo("diferenciacion", fuentes[:2], "--sin-contra", "nada")
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        d1 = registro.diferenciadores["D-1"]
        self.assertTrue(registro.del_dolor(d1, voz))
        self.assertTrue(registro.del_dolor(d1, copia))
        self.assertFalse(registro.del_dolor(d1, self.comparacion_alta()))
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", copia, "--texto", "x y z")
        self.assertIn("solo cita el dolor (%s)" % copia, salida)

    def test_uno_que_reune_el_dolor_es_el_dolor(self):
        voz = self.hasta_1g()
        nuevo, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 3), "--reune", voz)
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.assertTrue(registro.del_dolor(registro.diferenciadores["D-1"], nuevo))

    def test_la_eleccion_sigue_pidiendo_todo_lo_demas(self):
        voz = self.hasta_1g()
        media = self.comparacion_media()
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, media), "--texto",
               "Sin suscripción")
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        con, faltas, debiles = registro.eleccion(registro.diferenciadores["D-1"])
        self.assertFalse(con)
        self.assertEqual(faltas, ["%s en confianza media" % media])  # tiene uno distinto del dolor, pero en media
        self.assertEqual(debiles, [media])


# --- #67 · Las reglas de otra línea no se esquivan citando sus fuentes a mano ---------------------------------------

class ReglasTest(base.Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def evaluar(self, identificador):
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        return registro.evaluar(registro.hallazgos[identificador])

    def test_con_la_mayoria_de_fuentes_de_la_demanda_pide_una_medida(self):
        demanda = self.fuente("demanda", 3, "terceros")
        identificador, salida = self.hallazgo("validacion", demanda, "--critico", "--sin-contra", "nada")
        self.assertIn("· La mitad o más de sus fuentes son de la línea demanda: sigue también sus reglas de "
                      "triangulación (una fuente de tipo medido, y los datos acumulados no cuentan)", salida)
        evaluacion = self.evaluar(identificador)
        self.assertFalse(evaluacion["triangulado"])
        self.assertIn("falta una fuente de tipo medido (línea demanda)", evaluacion["faltan"])
        # la mitad también cuenta
        mitad, _ = self.hallazgo("validacion", demanda[:2] + self.fuente("validacion", 2), "--sin-contra", "nada")
        self.assertTrue(self.evaluar(mitad)["exige_medido"])
        # con una minoría de fuentes de la demanda, no: es evidencia de su propia línea
        minoria, salida = self.hallazgo("validacion", demanda[:1] + self.fuente("validacion", 2),
                                        "--sin-contra", "nada")
        self.assertNotIn("La mitad o más", salida)
        evaluacion = self.evaluar(minoria)
        self.assertTrue(evaluacion["triangulado"])
        self.assertFalse(evaluacion["exige_medido"])

    def test_los_datos_acumulados_de_la_demanda_no_cuentan(self):
        demanda = self.fuente("demanda", 2, "terceros")
        acumulada = re.search(r"S-DEM-\d+", self.p(
            "fuente", "--linea", "demanda", "--url", "https://tienda.example/acumulado", "--publicada", "2026-06",
            "--tipo", "medido", "--acumulado", "--peldano", 1, "--resumen", "1M de descargas desde 2019")).group(0)
        identificador, _ = self.hallazgo("validacion", demanda + [acumulada], "--sin-contra", "nada")
        evaluacion = self.evaluar(identificador)
        self.assertEqual(evaluacion["acumuladas"], [acumulada])
        self.assertFalse(evaluacion["triangulado"])

    def test_la_oficial_de_politicas_basta_como_con_reune(self):
        oficial = re.search(r"S-POL-\d+", self.p(
            "fuente", "--linea", "politicas", "--url", "https://tienda.example/politica", "--publicada", "2026-06",
            "--tipo", "oficial", "--version", "2026-06", "--peldano", 1, "--resumen", "La norma inventada")).group(0)
        identificador, _ = self.hallazgo("validacion", [oficial], "--sin-contra", "nada")
        self.assertTrue(self.evaluar(identificador)["triangulado"])

    def test_con_las_fuentes_de_un_hallazgo_de_otra_linea_lo_reune(self):
        favor = self.fuente("demanda", 3, "medido")
        contra = self.fuente("demanda", 1, "terceros")
        original, _ = self.hallazgo("demanda", favor, "--en-contra", contra[0], "--critico")
        self.p("confianza", "--hallazgo", original, "--bajar", "baja", "--motivo", "Dos notas inventadas")
        nuevas = self.fuente("validacion", 1)
        identificador, salida = self.hallazgo("validacion", favor + nuevas)
        self.assertIn("· Sus fuentes son las de %s, de otra línea: lo reúne aunque no pasaste --reune" % original,
                      salida)
        self.assertIn("· Reúne %s: sus fuentes a favor y en contra y su confianza bajada a mano" % original, salida)
        hallazgo = self.datos("01-investigacion/validacion.json")["hallazgos"][-1]
        self.assertEqual((hallazgo["reune"], hallazgo["reune_por_fuentes"], hallazgo["en_contra"]),
                         ([original], [original], contra))
        self.assertEqual(hallazgo["confianza_manual"]["nivel"], "baja")
        self.assertTrue(hallazgo["critico"])
        evaluacion = self.evaluar(identificador)
        self.assertEqual((evaluacion["contra"], evaluacion["confianza"]), (1, "baja"))
        self.assertEqual(producto.Registro(self.carpeta, self.datos()["criterios"]).reglas(hallazgo),
                         ["validacion", "demanda"])

    def test_no_reune_si_sus_fuentes_son_menos_de_la_mitad(self):
        original, _ = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 1, "usuario"),
                                    "--sin-contra", "nada")
        fuentes = self.datos("01-investigacion/voz-del-usuario.json")["fuentes"]
        _, salida = self.hallazgo("validacion", [fuentes[0]["id"]] + self.fuente("validacion", 2))
        self.assertNotIn("lo reúne", salida)
        self.assertNotIn("reune", self.datos("01-investigacion/validacion.json")["hallazgos"][-1])
        self.assertTrue(original)

    def test_una_fuente_en_contra_del_original_no_va_a_favor(self):
        favor = self.fuente("demanda", 2)
        contra = self.fuente("demanda", 1)
        self.hallazgo("demanda", favor, "--en-contra", contra[0])
        error = self.falla("hallazgo", "--linea", "validacion", "--texto", "x", "--fuentes",
                           ",".join(favor + contra))
        self.assertIn("Una fuente no puede estar a favor y en contra a la vez: %s (en contra de H-DEM-1, que este "
                      "hallazgo reúne)" % contra[0], error)


# --- #68 · Menores --------------------------------------------------------------------------------------------------

class MenoresTest(base.Base):
    def setUp(self):
        super().setUp()
        self.nuevo()

    def registrar(self, url, *extra, linea="competencia", resumen="Resumen inventado"):
        salida = self.p("fuente", "--linea", linea, "--url", url, "--publicada", "2026-06", "--tipo", "medido",
                        "--peldano", 1, "--resumen", resumen, *extra)
        return re.search(r"S-[A-Z]{3}-\d+", salida).group(0), salida

    def fuente_json(self, identificador, linea="competencia"):
        return next(f for f in self.datos("01-investigacion/%s.json" % linea)["fuentes"] if f["id"] == identificador)

    def test_el_extracto_que_pasa_a_leido_toma_el_resumen_nuevo(self):
        identificador, _ = self.registrar("https://a.example/1", "--extracto", resumen="Lo que decía el extracto")
        _, salida = self.registrar("https://a.example/1", resumen="Lo que dice la página entera")
        self.assertIn("se abrió la página: ahora cuenta como lectura, el resumen pasa a ser el de la página", salida)
        fuente = self.fuente_json(identificador)
        self.assertEqual((fuente["resumen"], fuente["resumen_extracto"]),
                         ("Lo que dice la página entera", "Lo que decía el extracto"))
        # una fuente ya leída no cambia su resumen
        _, salida = self.registrar("https://a.example/1", resumen="Otro resumen")
        self.assertIn("no se duplica.", salida)
        self.assertEqual(self.fuente_json(identificador)["resumen"], "Lo que dice la página entera")

    def test_un_hallazgo_que_falla_no_gasta_su_id(self):
        fuentes = self.fuente("voz-del-usuario", 1, "usuario")
        for extra in (["--fuentes", "S-VOZ-9"], ["--fuentes", fuentes[0], "--bloquea", "google-play"],
                      ["--fuentes", fuentes[0], "--en-contra", fuentes[0]], ["--fuentes", fuentes[0], "--reune",
                                                                            "H-VOZ-1"]):
            self.falla("hallazgo", "--linea", "voz-del-usuario", "--texto", "x", *extra)
        self.assertEqual(self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"], [])
        identificador, _ = self.hallazgo("voz-del-usuario", fuentes)
        self.assertEqual(identificador, "H-VOZ-1")

    def test_varias_fuentes_de_una_sola_lectura_cuentan_como_una(self):
        primera, _ = self.registrar("https://api.example/buscar?pais=mx")
        segunda, salida = self.registrar("https://api.example/buscar?pais=es", "--misma-lectura", primera,
                                         "--autor", "Tienda ES")
        self.assertIn("Fuentes de la línea competencia: 1 (presupuesto de lecturas: 10) · 1 fuente sale de una "
                      "lectura ya contada (--misma-lectura)", salida)
        # una que sale de otra que ya salía de la primera cuenta en la de origen
        tercera, salida = self.registrar("https://api.example/buscar?pais=ar", "--misma-lectura", segunda,
                                         "--autor", "Tienda AR")
        self.assertEqual(self.fuente_json(tercera)["lectura"], primera)
        self.assertIn("Fuentes de la línea competencia: 1 (presupuesto de lecturas: 10) · 2 fuentes salen", salida)
        # para la confianza no cambia nada: cada una cuenta por su autor
        identificador, _ = self.hallazgo("competencia", [primera, segunda, tercera])
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.assertEqual(registro.evaluar(registro.hallazgos[identificador])["independientes"], 3)
        self.assertEqual(producto.lecturas(registro.fuentes.values()), 1)

    def test_misma_lectura_valida_la_fuente(self):
        primera, _ = self.registrar("https://api.example/1")
        extracto, _ = self.registrar("https://b.example/1", "--extracto")
        otra, _ = self.registrar("https://c.example/1", linea="demanda")
        casos = (("S-COM-9", [], "no existe o está anulada"),
                 (otra, [], "es de la línea demanda"),
                 (extracto, [], "es un extracto de búsqueda, no una lectura"),
                 (primera, ["--extracto"], "no van juntos"))
        for base_, extra, error in casos:
            self.assertIn(error, self.falla("fuente", "--linea", "competencia", "--url", "https://api.example/2",
                                            "--publicada", "2026-06", "--tipo", "medido", "--peldano", 1,
                                            "--resumen", "x", "--misma-lectura", base_, *extra))
        self.assertIn("es esta misma fuente", self.falla(
            "fuente", "--linea", "competencia", "--url", "https://api.example/1", "--publicada", "2026-06", "--tipo",
            "medido", "--peldano", 1, "--resumen", "x", "--misma-lectura", primera))

    def test_una_url_ya_registrada_se_marca_como_de_la_misma_lectura(self):
        primera, _ = self.registrar("https://api.example/1")
        segunda, _ = self.registrar("https://api.example/2", "--extracto")
        _, salida = self.registrar("https://api.example/2", "--misma-lectura", primera, resumen="La ficha entera")
        self.assertIn("sale de la misma lectura que %s: no cuenta como otra lectura" % primera, salida)
        fuente = self.fuente_json(segunda)
        self.assertEqual((fuente.get("extracto"), fuente["lectura"], fuente["resumen"]),
                         (None, primera, "La ficha entera"))
        self.assertIn("Fuentes de la línea competencia: 1 (presupuesto de lecturas: 10) · 1 fuente sale", salida)

    def test_las_lecturas_de_un_grupo(self):
        fuentes = [{"id": "S-1"}, {"id": "S-2", "lectura": "S-1"}, {"id": "S-3", "extracto": True},
                   {"id": "S-4", "anulado": {"motivo": "x"}}, {"id": "S-5", "lectura": "S-9"}]
        self.assertEqual(producto.lecturas(fuentes), 2)  # S-1 (con S-2) y la lectura S-9 (con S-5)
        self.assertEqual(producto.de_misma_lectura(fuentes), 2)


if __name__ == "__main__":
    unittest.main()
