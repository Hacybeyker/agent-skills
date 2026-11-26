"""Tests de las mejoras #51 y #52 de hb-product: el vacío parcial de una dimensión que ya tiene fuentes queda a la vista
en `cobertura`, la puerta 1, `siguiente` y el reporte, sin cambiar ningún veredicto (#51), y un hallazgo ya registrado
se enlaza después a competidores de la matriz sin cambiar su ID ni su confianza (#52).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import os
import unittest

import test_product as base

HOY = base.HOY
producto = base.producto
REDDIT = "No se pudo leer Reddit ni foros en español: piden iniciar sesión"


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def resultado(self, numero_puerta=1):
        datos = producto.cargar(self.carpeta)
        registro = producto.Registro(self.carpeta, datos["criterios"])
        return producto.veredicto(numero_puerta, self.carpeta, datos, registro), datos, registro

    def vacio_reddit(self):
        return self.p("vacio", "--linea", "voz-del-usuario", "--idioma", "es", "--motivo", "herramienta", "--texto",
                      REDDIT)


# --- #51 · El vacío parcial de una dimensión con fuentes ---------------------------------------------------------------

class VacioParcialTest(Base):
    def test_cobertura_muestra_el_vacio_junto_a_las_fuentes(self):
        self.sesion0()
        fuentes = self.fuente("voz-del-usuario", 2, "usuario")  # cubren MX, es y google-play
        self.vacio_reddit()
        salida = self.p("cobertura", "--linea", "voz-del-usuario")
        self.assertIn("✔ idioma es · %s · ⚠ vacío parcial V-VOZ-1 (límite de las herramientas): No se pudo leer "
                      "Reddit" % ", ".join(fuentes), salida)
        self.assertIn("✔ tienda google-play · %s\n" % ", ".join(fuentes), salida)  # sin vacío: igual que antes
        self.assertIn("0 huecos sin registrar · 0 vacíos registrados · 1 vacío parcial", salida)
        self.hallazgo("voz-del-usuario", fuentes, "--critico")
        self.assertIn("0 vacíos registrados · 1 vacío parcial (`cobertura`)", self.p("triangulacion"))
        self.assertIn("1 vacío parcial (V-VOZ-1)", self.p("estado"))

    def test_un_texto_largo_se_acorta(self):
        self.sesion0()
        self.fuente("voz-del-usuario", 1, "usuario")
        self.p("vacio", "--linea", "voz-del-usuario", "--idioma", "es", "--motivo", "sin-resultados", "--texto",
               "Se buscó " + "muy " * 40 + "lejos")
        linea = next(l for l in self.p("cobertura", "--linea", "voz-del-usuario").splitlines() if "V-VOZ-1" in l)
        self.assertIn("(se buscó y no hay): Se buscó muy", linea)
        self.assertTrue(linea.endswith("…"), linea)

    def test_un_vacio_de_una_dimension_que_la_linea_no_pide_tambien_se_ve(self):
        self.sesion0()
        fuentes = self.fuente("monetizacion")  # cubre la tienda, que monetización no pide
        self.p("vacio", "--linea", "monetizacion", "--tienda", "google-play", "--motivo", "herramienta", "--texto",
               "La ficha de precios es dinámica")
        salida = self.p("cobertura", "--linea", "monetizacion")
        self.assertIn("✔ tienda google-play · %s · ⚠ vacío parcial V-MON-1" % fuentes[0], salida)
        self.assertIn("0 vacíos registrados · 1 vacío parcial", salida)

    def test_la_puerta_siguiente_y_el_reporte_lo_muestran_sin_cambiar_el_veredicto(self):
        self.hasta_puerta1()
        antes, datos, registro = self.resultado()
        herramienta = producto.vacios_de_herramienta(datos, registro)
        texto_antes = self.p("puerta", "--n", 1)
        self.assertNotIn("parcial", texto_antes)
        self.vacio_reddit()
        despues, datos, registro = self.resultado()
        for clave in ("nivel", "titulo", "recomienda", "sesion", "razones", "cambiaria"):
            self.assertEqual(antes[clave], despues[clave], clave)
        self.assertEqual(producto.vacios_de_herramienta(datos, registro), herramienta)
        self.assertEqual(producto.vacios_de_sesion(datos, registro, "1b"), [])
        aviso = ("· Vacíos parciales por límite de las herramientas (esa cobertura ya tiene fuentes, pero lo que dice "
                 "el vacío sigue sin leerse): voz-del-usuario · idioma es (V-VOZ-1: No se pudo leer Reddit")
        salida = self.p("puerta", "--n", 1)
        self.assertIn(aviso, salida)
        self.assertEqual(texto_antes.count("criterio"), salida.count("criterio"))
        self.assertIn(aviso, self.p("siguiente"))
        self.p("reporte")
        html = (self.carpeta / "reporte.html").read_text(encoding="utf-8")
        self.assertIn("es ✔ · ⚠ vacío parcial (límite de las herramientas)", html)
        self.assertIn("1 vacío parcial", html)

    def test_solo_la_puerta_avisa_los_de_herramienta_y_un_vacio_sin_fuentes_sigue_igual(self):
        self.hasta_puerta1()
        self.p("vacio", "--linea", "voz-del-usuario", "--idioma", "es", "--motivo", "presupuesto", "--texto",
               "Sin búsquedas para foros")
        self.assertNotIn("Vacíos parciales", self.p("puerta", "--n", 1))
        self.assertIn("vacío parcial V-VOZ-1 (sin presupuesto de búsquedas)", self.p("cobertura"))
        datos = producto.cargar(self.carpeta)
        registro = producto.Registro(self.carpeta, datos["criterios"])
        self.assertEqual(producto.vacios_parciales(registro, motivo="herramienta"), [])
        self.assertEqual([v["id"] for v, _ in producto.vacios_parciales(registro)], ["V-VOZ-1"])

    def test_ajustar_la_linea_lo_avisa(self):
        self.hasta_puerta1()
        self.vacio_reddit()
        salida = self.p("decidir", "--puerta", 1, "--ajustar", "1b", "--motivo", "Antes de seguir, más voces")
        self.assertIn("· Vacíos parciales por límite de las herramientas en lo que se ajusta: voz-del-usuario · "
                      "idioma es (V-VOZ-1", salida)
        self.assertNotIn("⚠ voz-del-usuario tiene vacíos por límite", salida)


# --- #52 · Enlazar un hallazgo a un competidor después de registrarlo ------------------------------------------------

class EnlazarHallazgoTest(Base):
    def setUp(self):
        super().setUp()
        self.sesion0()
        # la 1b registra su hallazgo antes de que la 1a cree las filas de la matriz
        self.voz, salida = self.hallazgo("voz-del-usuario", self.fuente("voz-del-usuario", 3, "usuario"),
                                         "--competidor", "RiegoFácil")
        self.assertIn("hallazgo --id %s --competidor C-…" % self.voz, salida)
        self.cerrar("1b", "01-investigacion/voz-del-usuario.md")
        competencia = self.fuente("competencia", 3, "medido")
        self.p("competidor", "--nombre", "Riego Fácil Pro", "--peldano", 1, "--fuentes", competencia[0],
               "--descargas", "1M")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", competencia[1], "--descargas",
               "500k")
        self.p("competidor", "--nombre", "HojaVerde", "--peldano", 1, "--fuentes", competencia[2], "--descargas",
               "200k")

    def guardado(self):
        return next(h for h in self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"] if h["id"] == self.voz)

    def test_enlaza_con_la_sesion_cerrada_sin_cambiar_id_ni_confianza(self):
        self.assertTrue(self.datos()["sesiones"]["1b"].get("cerrada"))
        antes = self.guardado()
        datos = producto.cargar(self.carpeta)
        etiqueta = producto.Registro(self.carpeta, datos["criterios"]).etiqueta(antes)
        salida = self.p("hallazgo", "--id", self.voz, "--competidor", "C-1,C-2")
        self.assertIn("✔ %s enlazado a C-1, C-2 · mismo ID, mismas fuentes y misma confianza (%s)" % (
            self.voz, etiqueta), salida)
        despues = self.guardado()
        self.assertEqual(despues["competidores"], ["RiegoFácil", "C-1", "C-2"])  # solo agrega: no quita nada
        for clave in ("id", "texto", "fuentes", "critico", "fecha", "en_contra", "sin_contra"):
            self.assertEqual(antes[clave], despues[clave], clave)
        self.assertEqual(len(self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"]), 1)
        datos = producto.cargar(self.carpeta)
        registro = producto.Registro(self.carpeta, datos["criterios"])
        self.assertEqual(registro.etiqueta(despues), etiqueta)
        self.assertEqual(registro.referencias(despues), (["C-1", "C-2"], ["RiegoFácil"]))
        self.assertIn("ya estaba enlazado a C-2: nada que agregar", self.p("hallazgo", "--id", self.voz,
                                                                           "--competidor", "C-2,PlantaPlus"))
        self.assertEqual(self.guardado()["competidores"], ["RiegoFácil", "C-1", "C-2"])
        self.p("hallazgo", "--id", self.voz, "--competidor", "C-3")
        self.assertEqual(self.guardado()["competidores"], ["RiegoFácil", "C-1", "C-2", "C-3"])
        self.assertEqual([e["competidores"] for e in self.guardado()["enlaces"]], [["C-1", "C-2"], ["C-3"]])

    def test_valida_que_los_competidores_existan_y_esten_vigentes(self):
        self.p("anular", "--id", "C-2", "--motivo", "Fila repetida")
        error = self.falla("hallazgo", "--id", self.voz, "--competidor", "C-1,C-2,C-9")
        self.assertIn("C-2 está anulado; C-9 no está en la matriz", error)
        self.assertEqual(self.guardado()["competidores"], ["RiegoFácil"])  # nada a medias
        self.assertIn("--competidor C-1,C-3", self.falla("hallazgo", "--id", self.voz))
        self.assertIn("No existe el hallazgo H-VOZ-9", self.falla("hallazgo", "--id", "H-VOZ-9", "--competidor",
                                                                   "C-1"))

    def test_con_id_no_cambia_nada_mas_y_sin_id_sigue_pidiendo_lo_de_siempre(self):
        error = self.falla("hallazgo", "--id", self.voz, "--competidor", "C-1", "--texto", "Otro texto", "--critico")
        self.assertIn("--critico no va", error)  # --texto sí va: corrige el texto (feedback #82 d)
        self.assertIn("faltan --linea, --fuentes", self.falla("hallazgo", "--texto", "Sin línea"))
        self.p("anular", "--id", self.voz, "--motivo", "Prueba")
        self.assertIn("o está anulado", self.falla("hallazgo", "--id", self.voz, "--competidor", "C-1"))

    def test_la_ayuda_lo_explica(self):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit):
            producto.main(["hallazgo", "--help"])
        self.assertIn("--id H-…", salida.getvalue())
        texto = (base.SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--id H-… --competidor", texto)
        self.assertIn("--id", (base.SKILL / "references" / "investigacion.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
