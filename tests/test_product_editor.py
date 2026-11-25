"""Tests de las mejoras #73 y #74 de hb-product.

#73: (a) una `propuesta` registrada en la puerta, con todas las sesiones cerradas, queda como de la última sesión que
cerró antes de ella (no «sesión ?»); (b) «Qué cambiaría» dice el orden real de `siguiente` cuando recomienda otra
sesión de otra tanda (la 1a va antes que la 1c), no «a la vez».
#74: las fuentes que describen un producto desde su editor (su ficha en cualquier tienda o país, su etiqueta de
privacidad, su web, su nota de prensa) cuentan como un solo autor: por la app en la URL de la tienda, por la fila de la
matriz o por `fuente --editor`. Las reseñas de usuarios no se juntan con su ficha. El aviso del 80 % de lecturas no
salta al registrar una fuente que no gasta una lectura (un extracto).

Los datos son inventados: la misma app de turnos de riego de test_product.py, con fichas de tiendas de ejemplo.
"""
import json
import os
import unittest

import test_product as base
import test_product_fricciones as fricciones
from helpers import write

HOY = base.HOY
producto = base.producto
SKILL = base.SKILL

PLAY = "https://play.google.com/store/apps/details?id=com.ejemplo.riego"
PLAY_AR = "https://play.google.com/store/apps/details?id=com.ejemplo.riego&gl=AR&hl=es"
PLAY_DATOS = "https://play.google.com/store/apps/datasafety?id=com.ejemplo.riego"
IOS = "https://apps.apple.com/mx/app/riego-ejemplo/id1234567890"
IOS_ES = "https://apps.apple.com/es/app/riego-ejemplo/id1234567890"


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def setUp(self):
        super().setUp()
        self.sesion0()  # las líneas 1a a 1e quedan abiertas

    def registro(self):
        return producto.Registro(self.carpeta, self.datos()["criterios"])

    def url(self, url, autor, tipo="medido", linea="competencia", *extra):
        salida = self.p("fuente", "--linea", linea, "--url", url, "--publicada", "2026-06", "--tipo", tipo,
                        "--peldano", 1, "--resumen", "Resumen inventado", "--autor", autor, *extra)
        return base.re.search(r"S-[A-Z]{3}-\d+", salida).group(0), salida

    def evaluacion(self, identificador):
        registro = self.registro()
        return registro.evaluar(registro.hallazgos[identificador])


# --- #74 · Las fuentes de un mismo editor son un solo autor ------------------------------------------------------------

class AppDeTiendaTest(unittest.TestCase):
    def test_reconoce_la_app_de_cada_tienda(self):
        self.assertEqual(producto.app_de_tienda(PLAY), ("google-play", "com.ejemplo.riego"))
        self.assertEqual(producto.app_de_tienda(PLAY_AR), ("google-play", "com.ejemplo.riego"))
        self.assertEqual(producto.app_de_tienda(PLAY_DATOS), ("google-play", "com.ejemplo.riego"))
        self.assertEqual(producto.app_de_tienda(IOS), ("app-store", "1234567890"))
        self.assertEqual(producto.app_de_tienda("https://itunes.apple.com/us/app/x/id42?mt=8"), ("app-store", "42"))
        self.assertEqual(producto.app_de_tienda("https://itunes.apple.com/lookup?id=42&country=br"), ("app-store", "42"))

    def test_la_pagina_de_un_desarrollador_o_de_otro_sitio_no_es_una_app(self):
        for url in ("https://play.google.com/store/apps/dev?id=123456", "https://play.google.com/store/apps/developer"
                    "?id=Ejemplo+Apps", "https://apps.apple.com/us/developer/ejemplo-apps/id987",
                    "https://ejemplo.example/app?id=com.ejemplo.riego", "https://itunes.apple.com/lookup?id=42,43",
                    "archivo:/tmp/resenas.csv", "", None):
            self.assertIsNone(producto.app_de_tienda(url), url)


class MismaAppTest(Base):
    def test_la_misma_app_en_dos_paises_y_su_etiqueta_de_privacidad_son_un_solo_autor(self):
        mx, _ = self.url(PLAY, "Riego Ejemplo")
        ar, _ = self.url(PLAY_AR, "Riego Ejemplo · Google Play AR")
        datos, salida = self.url(PLAY_DATOS, "Seguridad de los datos", "terceros")
        self.assertIn("· Editor: la app com.ejemplo.riego en Google Play. Lo que publica el mismo editor", salida)
        self.assertIn("cuenta como un solo autor: con %s y %s." % (mx, ar), salida)
        identificador, salida = self.hallazgo("competencia", [mx, ar, datos], "--critico", "--sin-contra", "nada")
        # antes de #74, tres autores distintos: triangulado y en alta
        self.assertIn("confianza baja · sin triangular", salida)
        self.assertIn("1 fuente independiente y vigente", salida)
        self.assertIn("· %s, %s y %s cuentan como un solo autor, su editor (la app com.ejemplo.riego en Google Play)"
                      % (mx, ar, datos), salida)
        evaluacion = self.evaluacion(identificador)
        self.assertEqual((evaluacion["independientes"], evaluacion["triangulado"]), (1, False))
        salida = self.p("triangulacion")
        self.assertIn("✖ %s" % identificador, salida)
        self.assertIn("    · %s, %s y %s cuentan como un solo autor, su editor" % (mx, ar, datos), salida)
        self.assertIn("· 1 hallazgo con fuentes de un mismo editor contadas como un solo autor.", salida)

    def test_con_dos_fuentes_de_otros_autores_triangula_con_el_editor_como_una(self):
        mx, _ = self.url(PLAY, "Riego Ejemplo")
        ios, _ = self.url(IOS, "Riego Ejemplo iOS")
        ios_es, _ = self.url(IOS_ES, "Riego Ejemplo iOS España")
        otras = self.fuente("competencia", 2)
        identificador, _ = self.hallazgo("competencia", [mx, ios, ios_es] + otras, "--critico", "--sin-contra", "x")
        evaluacion = self.evaluacion(identificador)
        # Google Play y App Store, sin fila que las una, son dos claves: com.ejemplo.riego y id1234567890
        self.assertEqual((evaluacion["independientes"], evaluacion["confianza"]), (4, "alta"))
        self.assertEqual(self.registro().juntas_por_editor([mx, ios, ios_es] + otras),
                         [([ios, ios_es], "la app 1234567890 en App Store")])

    def test_la_regla_de_siempre_se_mantiene(self):
        # el mismo autor o, sin autor, el mismo dominio siguen contando como uno; el editor solo junta, nunca separa
        mismo = self.fuente("competencia", 3, dominio="tienda.example")
        self.assertEqual(self.evaluacion(self.hallazgo("competencia", mismo)[0])["independientes"], 1)
        distintos = self.fuente("competencia", 3, dominio="tienda.example", autor="App")
        self.assertEqual(self.evaluacion(self.hallazgo("competencia", distintos)[0])["independientes"], 3)
        self.assertEqual(self.registro().juntas_por_editor(distintos), [])

    def test_dos_apps_distintas_en_la_misma_tienda_son_independientes(self):
        una, _ = self.url(PLAY, "Riego Ejemplo")
        otra, _ = self.url("https://play.google.com/store/apps/details?id=com.otra.plantas", "Plantas Otra")
        tercera, _ = self.url("https://play.google.com/store/apps/details?id=org.tercera.huerto", "Huerto Tercero")
        identificador, _ = self.hallazgo("competencia", [una, otra, tercera])
        self.assertEqual(self.evaluacion(identificador)["independientes"], 3)


class ResenasTest(Base):
    def test_las_resenas_de_la_ficha_no_se_juntan_con_la_ficha(self):
        ficha, _ = self.url(PLAY, "Riego Ejemplo")
        resenas, salida = self.url(PLAY + "&showAllReviews=true", "Reseñas de Riego Ejemplo en Google Play", "usuario",
                                   "voz-del-usuario")
        self.assertIn("· Reseñas de usuarios en la ficha de la app com.ejemplo.riego (Google Play): son la voz de sus "
                      "usuarios, no la del editor", salida)
        datos, _ = self.url(PLAY_DATOS, "Seguridad de los datos", "terceros")
        identificador, _ = self.hallazgo("competencia", [ficha, resenas, datos])
        # la ficha y su etiqueta de privacidad son el editor; las reseñas, otra voz
        self.assertEqual(self.evaluacion(identificador)["independientes"], 2)
        registro = self.registro()
        self.assertEqual(registro.independencia(registro.fuentes[ficha]), registro.independencia(registro.fuentes[datos]))
        self.assertNotEqual(registro.independencia(registro.fuentes[ficha]),
                            registro.independencia(registro.fuentes[resenas]))

    def test_editor_no_va_con_resenas(self):
        error = self.falla("fuente", "--linea", "voz-del-usuario", "--url", "https://foro.example/hilo", "--publicada",
                           "2026-06", "--tipo", "usuario", "--peldano", 1, "--resumen", "x", "--editor", "Riego SA")
        self.assertIn("Las reseñas de usuarios (--tipo usuario o un CSV) son la voz de sus usuarios", error)


class EditorExplicitoTest(Base):
    def test_la_web_y_la_nota_de_prensa_del_editor_cuentan_como_uno(self):
        web, salida = self.url("https://riego-ejemplo.example/funciones", "Riego Ejemplo (web)", "opinion",
                               "competencia", "--editor", "Riego Ejemplo SA")
        self.assertIn("· Editor: «Riego Ejemplo SA».", salida)
        prensa, salida = self.url("https://noticias.example/comunicado", "Comunicado de prensa", "terceros",
                                  "competencia", "--editor", "riego ejemplo s.a.")
        self.assertIn("cuenta como un solo autor: con %s." % web, salida)
        otra = self.fuente("competencia", 1)
        identificador, salida = self.hallazgo("competencia", [web, prensa] + otra)
        self.assertEqual(self.evaluacion(identificador)["independientes"], 2)
        self.assertIn("%s y %s cuentan como un solo autor, su editor («Riego Ejemplo SA»)" % (web, prensa), salida)

    def test_editor_con_la_fila_de_la_matriz_junta_la_ficha_y_la_web(self):
        ficha, _ = self.url(PLAY, "Riego Ejemplo")
        self.p("competidor", "--nombre", "Riego Ejemplo", "--peldano", 1, "--fuentes", ficha)
        web, salida = self.url("https://riego-ejemplo.example", "Riego Ejemplo (web)", "opinion", "competencia",
                               "--editor", "c-1")
        self.assertIn("· Editor: C-1 (Riego Ejemplo).", salida)
        self.assertIn("con %s." % ficha, salida)
        self.assertEqual(self.registro().fuentes[web]["editor"], "C-1")
        # el nombre de la fila también la encuentra
        nombre, _ = self.url("https://blog.example/riego", "Blog del editor", "opinion", "competencia", "--editor",
                             "Riego Ejemplo")
        registro = self.registro()
        self.assertEqual(len({registro.independencia(registro.fuentes[i]) for i in (ficha, web, nombre)}), 1)

    def test_valida_la_fila_y_no_pisa_otro_editor(self):
        self.assertIn("no es una fila vigente de la matriz", self.falla(
            "fuente", "--linea", "competencia", "--url", "https://a.example", "--publicada", "2026-06", "--tipo",
            "opinion", "--peldano", 1, "--resumen", "x", "--editor", "C-9"))
        web, _ = self.url("https://riego-ejemplo.example", "Riego Ejemplo (web)", "opinion")
        salida = self.p("fuente", "--linea", "competencia", "--url", "https://riego-ejemplo.example", "--editor",
                        "Riego Ejemplo SA")
        self.assertIn("se completó: su editor es «Riego Ejemplo SA»", salida)
        self.assertIn("· Editor: «Riego Ejemplo SA».", salida)
        error = self.falla("fuente", "--linea", "competencia", "--url", "https://riego-ejemplo.example", "--editor",
                           "Otra Empresa")
        self.assertIn("%s ya tiene el editor Riego Ejemplo SA: no se pisa" % web, error)


class FilaDeLaMatrizTest(Base):
    def test_la_fila_junta_la_app_de_google_play_y_la_de_app_store(self):
        play, _ = self.url(PLAY, "Riego Ejemplo")
        ios, _ = self.url(IOS, "Riego Ejemplo para iPhone")
        prensa = self.fuente("competencia", 1)
        identificador, _ = self.hallazgo("competencia", [play, ios] + prensa, "--critico", "--sin-contra", "nada")
        self.assertEqual(self.evaluacion(identificador)["independientes"], 3)  # sin fila, dos apps distintas
        self.p("competidor", "--nombre", "Riego Ejemplo", "--peldano", 1, "--fuentes", "%s,%s" % (play, ios))
        self.assertEqual(self.evaluacion(identificador)["independientes"], 2)
        self.assertIn("%s y %s cuentan como un solo autor, su editor (C-1 (Riego Ejemplo))" % (play, ios),
                      self.p("triangulacion"))

    def test_una_fila_con_varias_apps_de_una_tienda_no_las_junta(self):
        una, _ = self.url(PLAY, "Riego Ejemplo")
        otra, _ = self.url("https://play.google.com/store/apps/details?id=com.otra.plantas", "Plantas Otra")
        ios, _ = self.url(IOS, "Riego Ejemplo para iPhone")
        # una fila que agrupa varias apps (un tipo de sustituto, una categoría) no es un solo producto
        self.p("competidor", "--nombre", "Apps de riego", "--peldano", 1, "--fuentes", "%s,%s,%s" % (una, otra, ios))
        identificador, _ = self.hallazgo("competencia", [una, otra, ios])
        self.assertEqual(self.evaluacion(identificador)["independientes"], 3)


class AvisoDeLecturasTest(Base):
    def test_el_80_por_ciento_no_salta_con_un_extracto(self):
        self.fuente("demanda", 8)
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://extracto.example", "--publicada", "2026-06",
                        "--tipo", "medido", "--peldano", 1, "--resumen", "x", "--extracto")
        self.assertIn("Fuentes de la línea demanda: 8 (presupuesto de lecturas: 10) · más 1 extracto", salida)
        self.assertNotIn("80 %", salida)
        # una fuente de una lectura ya contada tampoco gasta una lectura
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://api.example/mx", "--publicada", "2026-06",
                        "--tipo", "medido", "--peldano", 1, "--resumen", "x", "--misma-lectura", "S-DEM-1")
        self.assertNotIn("80 %", salida)
        # sumar cobertura a una fuente ya registrada tampoco
        self.assertNotIn("80 %", self.p("fuente", "--linea", "demanda", "--url", "https://api.example/mx",
                                        "--mercados", "MX"))
        # abrir la página del extracto sí: ahora cuenta como lectura
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://extracto.example", "--resumen", "y")
        self.assertIn("Fuentes de la línea demanda: 9", salida)
        self.assertIn("80 %", salida)
        salida = self.p("fuente", "--linea", "demanda", "--url", "https://diez.example", "--publicada", "2026-06",
                        "--tipo", "medido", "--peldano", 1, "--resumen", "x")
        self.assertIn("80 %", salida)


class DocumentacionEditorTest(unittest.TestCase):
    def test_las_referencias_dicen_cuando_usar_editor(self):
        evidencia = (SKILL / "references" / "evidencia.md").read_text(encoding="utf-8")
        investigacion = (SKILL / "references" / "investigacion.md").read_text(encoding="utf-8")
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for texto in (evidencia, investigacion, skill):
            self.assertIn("--editor", texto)
        self.assertIn("un solo autor", evidencia)
        self.assertIn("reseñas de usuarios", evidencia)


# --- #73 · La sesión de una propuesta y el orden de las tandas en «Qué cambiaría» ------------------------------------

class PropuestaEnLaPuertaTest(fricciones.Base):
    def test_toma_la_ultima_sesion_cerrada(self):
        self.hasta_puerta1()
        salida = self.p("propuesta", "--texto", "Revisar una ficha inventada", "--ajustar", "1a")
        self.assertIn("· Sin una sesión abierta: queda como propuesta de la 1f, la última que cerró antes de la "
                      "puerta 1", salida)
        self.assertEqual(self.datos()["propuestas"][-1]["sesion"], "1f")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("· Propuesta PR-1 (sesión 1f): Revisar una ficha inventada", salida)
        self.assertNotIn("sesión ?", salida)

    def test_con_sesion_la_respeta_y_la_valida(self):
        self.hasta_puerta1()
        self.p("propuesta", "--texto", "Otra propuesta inventada", "--sesion", "1g")
        self.assertEqual(self.datos()["propuestas"][-1]["sesion"], "1g")
        self.assertIn("--sesion lleva una sesión", self.falla("propuesta", "--texto", "x", "--sesion", "9z"))

    def test_una_propuesta_vieja_sin_sesion_no_dice_sesion_interrogacion(self):
        self.hasta_puerta1()
        self.p("propuesta", "--texto", "Propuesta inventada de antes")
        datos = self.datos()
        datos["propuestas"][-1]["sesion"] = ""
        write(self.carpeta / "producto.json", json.dumps(datos))
        salida = self.p("puerta", "--n", 1)
        self.assertIn("· Propuesta PR-1 (registrada en la puerta): Propuesta inventada de antes", salida)
        self.assertNotIn("sesión ?", salida)


class TandasEnQueCambiariaTest(fricciones.Base):
    def test_la_1a_va_antes_que_la_1c(self):
        self.demanda_debil()
        for texto in ("Releer la demanda inventada", "Buscar otra tendencia inventada"):
            self.p("propuesta", "--texto", texto, "--ajustar", "1c")
        self.p("propuesta", "--texto", "Revisar el tipo de idea inventado", "--ajustar", "1a")
        salida = self.p("puerta", "--n", 1)
        self.assertIn("la skill recomienda: AJUSTAR 1a y 1c", salida)
        self.assertIn("Antes, la 1a (se ajusta junto con la 1c, pero por tandas, como las da `siguiente`: primero la "
                      "1a, que confirma el tipo de idea y, cuando cierre, la 1c; su ajuste no está entre las razones "
                      "de arriba): aplicar la propuesta PR-3 al ajustar la sesión 1a", salida)
        self.assertNotIn("A la vez, la 1a", salida)
        self.assertNotIn("corre en paralelo con la 1c", salida)

    def test_el_texto_sigue_el_orden_de_siguiente(self):
        self.assertEqual(producto.texto_a_la_vez("2", "3"), "A la vez, la 2 (corre en paralelo con la 3")
        self.assertEqual(producto.texto_a_la_vez("1d", "1c"), "A la vez, la 1d (corre en paralelo con la 1c")
        self.assertEqual(producto.texto_a_la_vez("1b", "1a"), "A la vez, la 1b (corre en paralelo con la 1a")
        self.assertEqual(producto.texto_a_la_vez("1c", "1b"),
                         "Después, la 1c (se ajusta junto con la 1b, pero por tandas, como las da `siguiente`: primero "
                         "la 1b y, cuando cierre, la 1c")


if __name__ == "__main__":
    unittest.main()
