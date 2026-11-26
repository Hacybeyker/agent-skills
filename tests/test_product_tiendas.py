"""Tests de las mejoras #80 a #82 de hb-product.

#80: el rival es por tienda del objetivo: la 1a marca la alternativa gratis más fuerte de cada tienda (`competidor
--rival --tienda`, o `--sin-rival --tienda`), la puerta 1 pide la de cada una y el principal tiene que superar a cada
una; si no supera a la de una tienda, «Qué cambiaría» ofrece compararlo con ella o quitar esa tienda del objetivo.
#81: un hallazgo de elección sin triangular citado en `frente` no baja el estado del diferenciador: es prueba de
elección pendiente.
#82: `--sin-contra` lleva un texto y la ayuda lo dice; una norma vista en un extracto se registra, pero no basta sola;
un peldaño buscado sin resultado dice dónde se buscó (`vacio --buscadas`); `hallazgo --id --texto` corrige el texto.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import contextlib
import io
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


class Base(rival.Base):
    def dos_tiendas(self):
        """El objetivo pasa a Google Play y App Store (después de la sesión 0, con su motivo)."""
        self.p("objetivo", "--tiendas", "google-play,app-store", "--motivo", "La idea también apunta a iPhone")

    def plataformas(self, nombre, fuente, plataformas, *extra):
        return self.p("competidor", "--nombre", nombre, "--peldano", 1, "--fuentes", fuente, "--plataformas",
                      plataformas, *extra)

    def registro(self):
        return producto.Registro(self.carpeta, self.datos()["criterios"])

    def rivales(self):
        return {c["id"]: c.get("rival_tiendas") for c in self.datos("01-investigacion/competencia.json")["matriz"]
                if c.get("rival")}


# --- #80 · El rival es por tienda del objetivo -----------------------------------------------------------------------

class RivalPorTiendaTest(Base):
    def test_un_solo_rival_sin_plataformas_o_en_todas_las_tiendas_no_cambia_nada(self):
        voz = self.hasta_1g()
        self.dos_tiendas()
        self.assertEqual(self.registro().tiendas_sin_rival(), [])  # sin plataformas: cuenta en todas
        self.plataformas("PlantaPlus", "S-COM-2", "android,ios")
        self.assertEqual(self.registro().tiendas_sin_rival(), [])
        salida = self.puerta1("--resultado", "supera", "--hallazgos", "%s,%s" % (voz, self.comparacion_alta()),
                              "--texto", "Sin suscripción")
        self.assertIn("✔ Al menos 1 diferenciador viable, con sus hallazgos triangulados y que supere al rival C-2 "
                      "(PlantaPlus) · 1 viable de 1 registrado", salida)
        self.assertNotIn("--tienda", salida)

    def test_un_rival_que_no_esta_en_una_tienda_es_una_falta_de_1a_y_de_la_puerta(self):
        voz = self.hasta_1g(rival=False)
        self.dos_tiendas()
        salida = self.plataformas("PlantaPlus", "S-COM-2", "ios", "--rival")
        self.assertIn("· Rival por tienda del objetivo: Google Play: falta (C-2 (PlantaPlus), el rival marcado, no "
                      "está en Google Play (plataformas: ios)) · App Store: C-2 (PlantaPlus).", salida)
        self.assertIn("⚠ Falta el rival de Google Play", salida)
        error = self.falla("cerrar", "--sesion", "1a")
        self.assertIn("falta el rival de Google Play, la alternativa gratis más fuerte en cada tienda del objetivo", error)
        self.assertIn("`competidor --nombre <…> … --rival --tienda google-play`", error)
        self.plataformas("PlantaPlus", "S-COM-2", "android,ios")  # en las dos tiendas: 1a cierra
        self.p("vacio", "--linea", "competencia", "--tienda", "app-store", "--motivo", "presupuesto", "--texto",
               "La tienda llegó al objetivo después")
        self.cerrar("1a")
        self.plataformas("PlantaPlus", "S-COM-2", "ios")  # la 1g descubre que solo está en App Store
        salida = self.puerta1("--resultado", "supera", "--hallazgos", "%s,%s" % (voz, self.sin_triangular()),
                              "--texto", "Sin suscripción")
        # D-1 se podría probar (Viable para probar), pero una tienda sin rival no se difiere: se completa en la 1g
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("Falta el rival de Google Play, la alternativa gratis más fuerte en esa tienda (C-2 (PlantaPlus), "
                      "el rival marcado, no está en Google Play (plataformas: ios))", salida)
        self.assertIn("✖ Al menos 1 diferenciador viable, con sus hallazgos triangulados y que supere al rival C-2 "
                      "(PlantaPlus) y al de Google Play (sin marcar)", salida)
        self.assertIn("o quitar Google Play del objetivo (`objetivo --tiendas app-store --motivo \"<por qué>\"`): es un "
                      "cambio de criterio con su motivo, que la puerta muestra, y nunca se hace solo", salida)
        self.assertIn("· Google Play sin rival marcado: se compara cuando lo esté (criterio anterior)", salida)

    def test_el_rival_de_una_tienda_reemplaza_solo_al_de_esa_tienda(self):
        self.hasta_1g()
        self.dos_tiendas()
        self.plataformas("PlantaPlus", "S-COM-2", "ios")
        salida = self.plataformas("RiegoLibre", "S-COM-1", "android", "--rival", "--tienda", "google-play")
        self.assertIn("⚠ Rival a superar: C-4 (RiegoLibre), la alternativa gratis más fuerte en Google Play.", salida)
        self.assertIn("Google Play: C-4 (RiegoLibre) · App Store: C-2 (PlantaPlus)", salida)
        self.assertEqual(self.rivales(), {"C-2": ["app-store"], "C-4": ["google-play"]})
        registro = self.registro()
        self.assertEqual([c["id"] for c in registro.rivales()], ["C-2", "C-4"])
        self.assertEqual(registro.tiendas_sin_rival(), [])
        # el de App Store, por su tienda: C-2 deja de serlo y C-4 lo es de las dos
        self.plataformas("RiegoLibre", "S-COM-1", "android,ios", "--rival", "--tienda", "app-store")
        self.assertEqual(self.rivales(), {"C-4": ["google-play", "app-store"]})
        # sin --tienda, vale para todas y reemplaza a los demás, como siempre
        self.plataformas("PlantaPlus", "S-COM-2", "ios", "--rival")
        self.assertEqual(self.rivales(), {"C-2": None})
        self.assertEqual(self.registro().tiendas_sin_rival(), ["google-play"])

    def test_sin_rival_en_una_tienda_y_sus_validaciones(self):
        self.hasta_1g()
        self.dos_tiendas()
        self.plataformas("PlantaPlus", "S-COM-2", "ios")
        self.assertEqual(self.registro().tiendas_sin_rival(), ["google-play"])
        salida = self.p("competidor", "--sin-rival", "En Google Play ninguna app gratis reparte turnos", "--tienda",
                        "google-play")
        self.assertIn("✔ Sin rival gratis en Google Play: En Google Play ninguna app gratis reparte turnos", salida)
        self.assertIn("Google Play: sin rival gratis (En Google Play ninguna app gratis reparte turnos) · App Store: "
                      "C-2 (PlantaPlus)", salida)
        self.assertEqual(self.registro().tiendas_sin_rival(), [])
        self.assertIn("huawei no está entre las tiendas del objetivo", self.falla(
            "competidor", "--sin-rival", "Ninguna gratis en esa tienda", "--tienda", "huawei"))
        self.assertIn("--tienda va con --rival", self.falla("competidor", "--nombre", "RiegoLibre", "--peldano", 1,
                                                             "--fuentes", "S-COM-1", "--tienda", "google-play"))
        self.sustituto("S-COM-3", "Planilla compartida", "gratuito", "si")  # un sustituto fuerte, en todas
        self.assertIn("En App Store ya hay un rival a superar", self.falla(
            "competidor", "--sin-rival", "Ninguna gratis en App Store", "--tienda", "app-store"))
        # marcar después el rival de esa tienda quita su «sin rival»
        self.plataformas("RiegoLibre", "S-COM-1", "android", "--rival", "--tienda", "google-play")
        self.assertNotIn("sin_rival_tiendas", self.datos("01-investigacion/competencia.json"))

    def test_un_rival_de_tienda_marcado_despues_de_la_1g_se_compara_no_descarta(self):
        voz = self.hasta_1g()
        self.dos_tiendas()
        self.plataformas("PlantaPlus", "S-COM-2", "ios")
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, self.comparacion_alta()),
               "--texto", "Sin suscripción")
        self.p("vacio", "--linea", "competencia", "--tienda", "app-store", "--motivo", "presupuesto", "--texto", "x y z")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")
        self.plataformas("RiegoLibre", "S-COM-1", "android", "--rival", "--tienda", "google-play")  # sin la 1g abierta
        self.p("puntaje", "--valores", "4,4,4,4,1")  # sin comparar con C-4, D-1 no es viable
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🟡  PUERTA 1 · VIABLE CON RESERVAS  →  la skill recomienda: AJUSTAR 1g", salida)
        self.assertIn("D-1 supera al rival C-2 (PlantaPlus), pero no se comparó con el rival C-4 (RiegoLibre), el de "
                      "Google Play: no se sabe si lo superan", salida)
        self.assertIn("Comparar D-1 con C-4 (RiegoLibre) en la 1g (`frente --id D-… --rival C-4 …`); o quitar Google "
                      "Play del objetivo", salida)
        self.assertIn("el veredicto depende de lo que muestre la comparación", salida)
        self.assertNotIn("🔴", salida)

    def test_el_principal_que_no_supera_al_rival_de_una_tienda(self):
        voz = self.hasta_1g()
        self.dos_tiendas()
        self.plataformas("PlantaPlus", "S-COM-2", "ios")
        self.plataformas("RiegoLibre", "S-COM-1", "android", "--rival", "--tienda", "google-play")
        alta = self.comparacion_alta()
        self.p("diferenciador", "--vector", "usabilidad", "--texto", "Turnos en dos toques", "--hallazgos", voz,
               "--se-ve", "uso", "--copiable", "media", "--motivo", "Rediseñar el flujo les cuesta", "--semanas", 2)
        for rival_ in ("C-2", "C-4"):
            self.p("frente", "--id", "D-2", "--rival", rival_, "--resultado", "supera", "--hallazgos",
                   "%s,%s" % (voz, alta), "--texto", "Lo supera en el flujo")
        self.p("frente", "--id", "D-1", "--rival", "C-4", "--resultado", "iguala", "--hallazgos", voz, "--texto",
               "RiegoLibre también es de pago único")
        salida = self.p("diferenciador")  # sin opciones: lista el estado, tienda por tienda
        self.assertIn("✖ D-1 (principal): no viable (paridad: iguala al rival)", salida)
        self.assertIn("· Por tienda del objetivo: Google Play ✖ iguala a C-4 (RiegoLibre)", salida)
        self.assertIn("✔ D-2: viable", salida)
        salida = self.puerta1("--rival", "C-2", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, alta),
                              "--texto", "Sin suscripción")
        self.assertIn("El principal (D-1) iguala al rival C-4 (RiegoLibre): no viable (paridad, básico en Kano), no "
                      "es una razón para elegir la app, en Google Play; en App Store sí lo supera", salida)
        self.assertIn("Elegir como principal un diferenciador viable que la supere (D-2); o que D-1 supere a C-4 "
                      "(RiegoLibre), el rival de Google Play, con un hallazgo triangulado (compararlo en la 1g: "
                      "`frente --id D-1 --rival C-4 …`); o quitar Google Play del objetivo (`objetivo --tiendas "
                      "app-store --motivo \"<por qué>\"`)", salida)
        self.assertNotIn("🟢", salida)


# --- #81 · Una prueba de elección pendiente no baja el estado --------------------------------------------------------

class EleccionPendienteTest(Base):
    def test_un_hallazgo_de_eleccion_sin_triangular_no_baja_el_estado(self):
        voz = self.hasta_1g()
        solo_dolor = self.registro()
        suelto = self.sin_triangular()
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, suelto),
                        "--texto", "Sin suscripción, y una reseña dice que se cambió por eso")
        self.assertIn("✔ D-1: viable", salida)  # antes de #81: viable con confianza baja
        self.assertIn("✔ Hallazgos triangulados (regla 2): %s · prueba de elección pendiente: %s (sin triangular: no "
                      "cuenta como prueba de elección ni baja su estado)" % (voz, suelto), salida)
        self.assertIn("· Prueba de elección pendiente frente a C-2 (PlantaPlus) (%s, sin triangular)" % suelto, salida)
        self.assertIn("Sin prueba de elección (prueba de elección pendiente (%s, sin triangular))" % suelto, salida)
        registro = self.registro()
        d1 = registro.diferenciadores["D-1"]
        self.assertEqual(registro.sin_triangular(d1), [])
        self.assertEqual(registro.eleccion_pendiente(d1)[0][1], [suelto])
        self.assertFalse(registro.eleccion(d1)[0])
        # citando solo el dolor el estado es el mismo: nunca peor
        self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", voz, "--texto", "Sin suscripción")
        self.assertEqual(self.registro().estado(self.registro().diferenciadores["D-1"]), registro.estado(d1))
        self.assertIsNotNone(solo_dolor)

    def test_la_puerta_1_da_viable_para_probar_y_lo_nombra(self):
        voz = self.hasta_1g()
        suelto = self.sin_triangular()
        salida = self.puerta1("--resultado", "supera", "--hallazgos", "%s,%s" % (voz, suelto), "--texto", "x y z",
                              valores="4,4,4,4,4")
        self.assertIn("🟡  PUERTA 1 · VIABLE PARA PROBAR  →  la skill recomienda: SEGUIR", salida)
        self.assertIn("prueba de elección pendiente (%s, sin triangular)" % suelto, salida)
        self.assertIn("✔ Los hallazgos del diferenciador principal están triangulados y supera al rival C-2 "
                      "(PlantaPlus) · D-1: %s · prueba de elección pendiente: %s (sin triangular)" % (voz, suelto),
                      salida)

    def test_solo_con_hallazgos_de_eleccion_sin_triangular_no_lo_supera_y_pide_citar_el_dolor(self):
        self.hasta_1g()
        suelto = self.sin_triangular()
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", suelto, "--texto", "x y z")
        self.assertIn("✖ D-1: no viable", salida)
        self.assertIn("pero ninguno de sus hallazgos (%s) está triangulado: cita también el dolor triangulado que "
                      "muestra que el rival falla (cuenta para superarlo; %s queda como prueba de elección "
                      "pendiente)" % (suelto, suelto), salida)

    def test_un_hallazgo_del_dolor_sin_triangular_si_cuenta_en_contra(self):
        voz = self.hasta_1g()
        fuentes = self.datos("01-investigacion/voz-del-usuario.json")["hallazgos"][0]["fuentes"]
        copia, _ = self.hallazgo("diferenciacion", fuentes[:1], "--sin-contra", "nada")  # sus mismas fuentes: dolor
        salida = self.p("frente", "--id", "D-1", "--resultado", "supera", "--hallazgos", "%s,%s" % (voz, copia),
                        "--texto", "x y z")
        self.assertIn("⚠ D-1: viable con confianza baja", salida)
        self.assertNotIn("prueba de elección pendiente", salida)


# --- #82 · Textos y fricciones de la 1a a la 1e ------------------------------------------------------------------------

class FriccionesTest(Base):
    def ayuda(self, comando):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit):
            producto.main([comando, "--help"])
        return re.sub(r"\s+", " ", salida.getvalue())

    def test_a_la_ayuda_dice_que_sin_contra_lleva_un_texto(self):
        ayuda = self.ayuda("hallazgo")
        self.assertIn('--sin-contra "<qué buscaste>"', ayuda)
        self.assertIn("lleva un texto", ayuda)
        self.sesion0()
        self.assertIn("expected one argument", self.falla("hallazgo", "--linea", "demanda", "--texto", "x",
                                                          "--fuentes", "S-DEM-1", "--sin-contra"))

    def test_b_una_norma_vista_en_un_extracto_se_registra_pero_no_basta_sola(self):
        self.sesion0()
        url = "https://tienda.example/politicas/ninos"
        salida = self.p("fuente", "--linea", "politicas", "--url", url, "--publicada", "2026-06", "--tipo", "oficial",
                        "--version", "junio de 2026", "--peldano", 1, "--resumen", "La norma de apps para niños",
                        "--extracto")
        self.assertIn("· Fuente oficial vista en un extracto (junio de 2026): cuenta como cualquier fuente, pero no "
                      "basta sola", salida)
        fuente = re.search(r"S-POL-\d+", salida).group(0)
        identificador, salida = self.hallazgo("politicas", [fuente], "--critico", "--sin-contra", "nada")
        evaluacion = self.registro().evaluar(self.registro().hallazgos[identificador])
        self.assertFalse(evaluacion["triangulado"])
        self.assertIn("%s es un extracto de un buscador, que no basta solo; abre la página y repite `fuente` con la "
                      "misma URL y sin --extracto" % fuente, self.p("triangulacion"))
        # al abrir la página, la misma URL sin --extracto: basta sola
        self.p("fuente", "--linea", "politicas", "--url", url)
        evaluacion = self.registro().evaluar(self.registro().hallazgos[identificador])
        self.assertTrue(evaluacion["triangulado"])
        self.assertEqual(evaluacion["oficial"], [fuente])

    def test_c_un_peldano_sin_resultados_dice_donde_se_busco(self):
        self.sesion0("nueva")
        error = self.falla("vacio", "--linea", "demanda", "--peldano", 5, "--motivo", "sin-resultados", "--texto",
                           "Nada sobre la necesidad")
        self.assertIn("dice dónde se buscó: --buscadas", error)
        self.assertIn("va con --motivo sin-resultados", self.falla(
            "vacio", "--linea", "demanda", "--peldano", 5, "--motivo", "presupuesto", "--texto", "x",
            "--buscadas", "foros"))
        salida = self.p("vacio", "--linea", "demanda", "--peldano", 5, "--motivo", "sin-resultados", "--texto",
                        "Nada sobre la necesidad; Reddit quedó sin buscar", "--buscadas", "foros y prensa local")
        self.assertIn("(se buscó en foros y prensa local y no hay, V-DEM-1)", salida)
        self.assertEqual(self.datos("01-investigacion/demanda.json")["vacios"][0]["buscadas"], "foros y prensa local")
        # en un mercado sigue siendo opcional
        self.assertIn("(se buscó y no hay, V-DEM-2)", self.p("vacio", "--linea", "demanda", "--mercado", "MX",
                                                             "--motivo", "sin-resultados", "--texto", "Nada en MX"))

    def test_d_hallazgo_id_texto_corrige_el_texto_sin_cambiar_el_id(self):
        self.sesion0()
        fuentes = self.fuente("demanda", 2, "medido")
        identificador, _ = self.hallazgo("demanda", fuentes, "--sin-contra", "nada")
        salida = self.p("hallazgo", "--id", identificador, "--texto", "Texto corregido del hallazgo")
        self.assertIn("✔ %s con el texto corregido · mismo ID, mismas fuentes y misma confianza" % identificador,
                      salida)
        guardado = self.datos("01-investigacion/demanda.json")["hallazgos"][0]
        self.assertEqual((guardado["id"], guardado["texto"], guardado["fuentes"]),
                         (identificador, "Texto corregido del hallazgo", fuentes))
        self.assertEqual(guardado["enlaces"][-1]["texto_anterior"], "Hallazgo inventado")
        self.assertIn("ya tenía ese texto", self.p("hallazgo", "--id", identificador, "--texto",
                                                   "Texto corregido del hallazgo"))
        self.assertIn("--texto va con el texto corregido", self.falla("hallazgo", "--id", identificador, "--texto",
                                                                      " "))
        self.completar("01-investigacion/demanda.md")
        self.p("cerrar", "--sesion", "1c")
        error = self.falla("hallazgo", "--id", identificador, "--texto", "Otro texto")
        self.assertIn("la sesión 1c (Demanda), dueña del hallazgo, ya cerró", error)


if __name__ == "__main__":
    unittest.main()
