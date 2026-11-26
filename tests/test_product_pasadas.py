"""Tests de las mejoras #58 y #59 de hb-product: la propuesta con alcance (`propuesta --hallazgos`), a la que la puerta
le aplica la regla de los vacíos de herramienta de #57 (#58), y el consumo anotado por pasada de cada sesión, la
primera y cada reapertura (#59).

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import unittest

import test_product as base
import test_product_demanda as demanda
import test_product_veredicto as veredicto

HOY = base.HOY
producto = base.producto


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


# --- #58 · La propuesta con alcance -----------------------------------------------------------------------------------

class PropuestaConAlcanceTest(veredicto.Base):
    def setUp(self):
        super().setUp()
        self.hasta_puerta2()
        registro = producto.Registro(self.carpeta, self.datos()["criterios"])
        self.voz = next(i for i in registro.hallazgos if i.startswith("H-VOZ"))  # sus fuentes: MX, es y google-play

    def vacio_tienda(self, tienda):
        self.p("vacio", "--linea", "voz-del-usuario", "--tienda", tienda, "--motivo", "herramienta", "--texto",
               "Página dinámica inventada")

    def test_sin_alcance_la_propuesta_con_un_vacio_sin_fuentes_no_cuenta_como_antes(self):
        self.p("objetivo", "--tiendas", "google-play,app-store", "--motivo", "Sumamos la otra tienda")
        self.vacio_tienda("app-store")
        self.p("propuesta", "--texto", "Releer las reseñas con un navegador", "--ajustar", "1b", "--sesion", "3")
        self.assertIn("🟢  PUERTA 2 · VIABLE  →  la skill recomienda: SEGUIR", self.p("puerta", "--n", 2))

    def test_con_alcance_fuera_del_vacio_cuenta_como_ajuste(self):
        self.p("objetivo", "--tiendas", "google-play,app-store", "--motivo", "Sumamos la otra tienda")
        self.vacio_tienda("app-store")
        salida = self.p("propuesta", "--texto", "Releer las reseñas con un navegador", "--ajustar", "1b", "--sesion",
                        "3", "--hallazgos", self.voz)
        self.assertIn("(se aplica con Ajustar 1b); resuelve %s" % self.voz, salida)
        self.assertEqual(self.datos()["propuestas"][-1]["hallazgos"], [self.voz])
        salida = self.p("puerta", "--n", 2)
        self.assertIn("🟡  PUERTA 2 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1b", salida)
        self.assertIn("Hay una propuesta pendiente (PR-1): Releer las reseñas con un navegador", salida)
        self.assertIn("Aplicar la propuesta PR-1 al ajustar la sesión 1b (resuelve %s)" % self.voz, salida)
        self.assertIn("→ se aplica con Ajustar 1b (resuelve %s)" % self.voz, salida)
        # el vacío queda como aviso: el ajuste no depende de él (la regla de #57)
        self.assertIn("pero el ajuste no depende de él (%s tiene fuentes de tienda google-play)" % self.voz, salida)
        self.assertNotIn("antes de ajustarla", salida)

    def test_con_alcance_dentro_del_vacio_no_cuenta(self):
        self.vacio_tienda("google-play")  # google-play tiene fuentes: un vacío parcial, y el hallazgo solo es de ahí
        self.p("propuesta", "--texto", "Releer las reseñas", "--ajustar", "1b", "--sesion", "3", "--hallazgos",
               self.voz)
        salida = self.p("puerta", "--n", 2)
        self.assertIn("🟢  PUERTA 2 · VIABLE  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("· Propuesta PR-1 (sesión 3): Releer las reseñas → se aplica con Ajustar 1b (resuelve %s)"
                      % self.voz, salida)

    def test_con_alcance_y_sin_vacios_cuenta_igual_que_sin_alcance(self):
        self.p("propuesta", "--texto", "Revisar los precios", "--ajustar", "1d", "--sesion", "3", "--hallazgos",
               self.voz)
        self.assertIn("AJUSTAR 1d", self.p("puerta", "--n", 2))

    def test_un_hallazgo_sin_etiquetas_no_se_sabe_y_conserva_lo_seguro(self):
        self.p("objetivo", "--tiendas", "google-play,app-store", "--motivo", "Sumamos la otra tienda")
        self.vacio_tienda("app-store")
        fuentes = self.fuente("voz-del-usuario", 1, "usuario", cobertura=False)
        sin_etiquetas, _ = self.hallazgo("voz-del-usuario", fuentes)
        self.p("propuesta", "--texto", "Releer", "--ajustar", "1b", "--sesion", "3", "--hallazgos", sin_etiquetas)
        self.assertIn("🟢  PUERTA 2 · VIABLE", self.p("puerta", "--n", 2))

    def test_valida_los_hallazgos(self):
        self.assertIn("H-VOZ-99 no existe", self.falla("propuesta", "--texto", "x", "--ajustar", "1b", "--hallazgos",
                                                       "H-VOZ-99"))
        self.assertEqual(self.datos()["propuestas"], [])

    def test_la_documentacion_lo_describe(self):
        skill = (demanda.SKILL / "SKILL.md").read_text(encoding="utf-8")
        puertas = (demanda.SKILL / "references" / "puertas.md").read_text(encoding="utf-8")
        self.assertIn("--hallazgos", skill)
        self.assertIn("propuesta --texto", puertas)
        self.assertIn("--hallazgos", puertas)


# --- #59 · El consumo por pasada --------------------------------------------------------------------------------------

class ConsumoPorPasadaTest(demanda.Base):
    def reabrir_1c(self):
        """La puerta 1 con la demanda débil, el consumo de la primera pasada de la 1c y la 1c reabierta y cerrada."""
        self.demanda_debil()
        self.p("consumo", "--sesion", "1c", "--tokens", "100k")
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.assertEqual(producto.pasada_vigente(self.datos(), "1c"), 1)
        self.assertNotIn("1c (reapertura 1)", producto.sin_consumo(self.datos()))  # abierta: todavía no
        self.p("cerrar", "--sesion", "1c", "--busquedas", 3, "--lecturas", 2)

    def json(self):
        return json.loads(self.p("siguiente", "--json").strip().splitlines()[-1])

    def test_cada_pasada_va_en_su_fila_y_el_total_las_suma(self):
        self.reabrir_1c()
        self.assertIn("1c (reapertura 1)", producto.sin_consumo(self.datos()))
        self.assertIn("1c (reapertura 1)", self.json()["costo"]["sin_anotar"])
        self.assertNotIn("1c", producto.sin_consumo(self.datos()))  # la primera pasada ya está anotada
        salida = self.p("consumo", "--sesion", "1c", "--tokens", "50k")
        self.assertIn("✔ Consumo de 1c (reapertura 1): 50 000 tokens · total anotado: sin dato en USD · 150 000 "
                      "tokens", salida)
        filas = [f for f in self.datos()["consumo"] if f["sesion"] == "1c"]
        self.assertEqual([(f["pasada"], f["tokens"]) for f in filas], [(0, 100000), (1, 50000)])
        # volver a anotar la misma pasada actualiza su fila
        self.p("consumo", "--sesion", "1c", "--tokens", "60k")
        filas = [f for f in self.datos()["consumo"] if f["sesion"] == "1c"]
        self.assertEqual([f["tokens"] for f in filas], [100000, 60000])
        self.assertNotIn("1c (reapertura 1)", producto.sin_consumo(self.datos()))
        listado = self.p("consumo")
        self.assertIn("1c (reapertura 1) 60 000 tokens", listado)
        self.assertIn("Total: sin dato en USD · 160 000 tokens", listado)
        self.assertIn("sesión 1c: 100 000 tokens · sesión 1c (reapertura 1): 60 000 tokens",
                      (self.carpeta / "estado.md").read_text(encoding="utf-8"))
        self.p("reporte")
        self.assertIn("<td>1c (reapertura 1)</td>", (self.carpeta / producto.REPORTE).read_text(encoding="utf-8"))

    def test_una_reapertura_cerrada_sin_consumo_cuenta_como_sin_anotar(self):
        self.reabrir_1c()
        self.assertIn("1b, 1c (reapertura 1), 1d", self.p("siguiente"))  # la 1f, reabierta: su primera pasada
        self.assertIn("1c (reapertura 1)", self.p("estado"))

    def test_una_fila_sin_pasada_cuenta_como_la_primera(self):
        self.demanda_debil()
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.p("cerrar", "--sesion", "1c", "--busquedas", 3, "--lecturas", 2)
        datos = self.datos()
        datos["consumo"] = [{"sesion": "1c", "tokens": 1000, "fecha": "2026-11-01T10:00"}]  # anotada antes de #59
        (self.carpeta / "producto.json").write_text(json.dumps(datos), encoding="utf-8")
        self.assertIn("1c (reapertura 1)", producto.sin_consumo(self.datos()))
        self.assertNotIn("1c", producto.sin_consumo(self.datos()))
        self.p("consumo", "--sesion", "1c", "--tokens", "2000")  # la reapertura no pisa la fila anterior
        self.assertEqual([f["tokens"] for f in self.datos()["consumo"]], [1000, 2000])
        # --pasada anota una pasada anterior: la fila sin pasada es la primera
        self.p("consumo", "--sesion", "1c", "--pasada", "0", "--costo", "0.10")
        self.assertEqual([(f.get("tokens"), f.get("costo")) for f in self.datos()["consumo"]],
                         [(1000, 0.1), (2000, None)])
        self.assertIn("--pasada es 0 (la primera) o el número de una reapertura, hasta 1",
                      self.falla("consumo", "--sesion", "1c", "--pasada", "2", "--tokens", "1"))
        self.assertIn("--pasada es 0 (la primera): la sesión 1a va en la primera pasada",
                      self.falla("consumo", "--sesion", "1a", "--pasada", "1", "--tokens", "1"))
        self.assertIn("--pasada va con una sesión", self.falla("consumo", "--sesion", "orquestador", "--pasada", "0",
                                                               "--costo", "1"))

    def test_el_orquestador_cubre_la_pasada_vigente_y_suma_las_de_su_fila(self):
        self.demanda_debil()
        sesiones = ",".join(producto.sin_orquestador(self.datos()))
        self.p("consumo", "--sesion", "orquestador", "--incluye", sesiones, "--costo", "2.00")
        self.p("decidir", "--puerta", 1, "--ajustar", "1c")
        self.p("cerrar", "--sesion", "1c", "--busquedas", 3, "--lecturas", 2)
        self.assertEqual(producto.sin_orquestador(self.datos()), ["1c"])  # su reapertura: ningún chat la anotó
        self.assertIn("--incluye 1c --costo", self.json()["costo"]["comando_orquestador"])
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1c", "--costo", "2.50")  # el mismo chat
        filas = [f for f in self.datos()["consumo"] if f["sesion"] == "orquestador"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["pasadas_incluye"], {"1c": [0, 1]})
        self.assertIn("1c, 1c (reapertura 1)", self.p("consumo"))
        self.assertEqual(producto.sin_orquestador(self.datos()), [])
        self.assertNotIn("1c (reapertura 1)", producto.sin_consumo(self.datos()))
        self.assertIn("Total: 2,50 USD", self.p("consumo"))

    def test_los_tokens_del_orquestador_no_cuentan_dos_veces_la_misma_pasada(self):
        self.reabrir_1c()
        self.p("consumo", "--sesion", "1c", "--tokens", "50k")
        self.p("consumo", "--sesion", "orquestador", "--incluye", "1c", "--tokens", "80k")  # cubre la reapertura
        # cuenta la primera pasada (100k) y el orquestador (80k), no la reapertura que ya incluye
        self.assertIn("180 000 tokens", producto.texto_total(self.datos()["consumo"]))


if __name__ == "__main__":
    unittest.main()
