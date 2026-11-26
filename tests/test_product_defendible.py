"""Tests de las decisiones #75 y #41 de hb-product (0.2.0).

#75 (a): el 5 de diferenciación mide lo defendible, no la cantidad. El script lo acepta solo con dos o más viables que
no son fáciles de copiar (copiabilidad baja o media) o con uno viable que se ve en la ficha y es difícil de copiar
(baja); con algún viable, en cualquier otro caso el máximo es 4. Los viables con confianza baja que se pueden probar
cuentan como viables con la misma regla. Un 5 registrado antes queda como «se registró» y el de hoy decide la puerta 1.

#75 (b): la confianza no es la dirección. Un hallazgo clave que confirma «la demanda es pequeña» con confianza alta deja
la demanda en confianza alta; la magnitud va al puntaje, y la puerta 1 falla por el puntaje, no por la confianza.

#41: la distribución (ASO) no es un vector de diferenciación: `diferenciador --vector distribucion` se rechaza y manda
a registrarla como hallazgo para la estrategia.

Los datos son inventados: la misma app de turnos de riego de test_product.py.
"""
import json
import os
import re
import unittest
from pathlib import Path

import test_product as base
from helpers import write

HOY = base.HOY


def setUpModule():
    os.environ["HB_PRODUCT_HOY"] = HOY
    for variable in ("CLAUDECODE", "AI_AGENT", "NO_COLOR"):
        os.environ.pop(variable, None)


class Base(base.Base):
    def con_diferenciadores(self, *specs):
        """Sesiones 1a a 1g con un diferenciador por cada (se_ve, copiable, probar). Todos citan el mismo dolor
        triangulado y superan al rival; con probar=True, la comparación cita además un hallazgo sin triangular: queda
        viable con confianza baja y se puede probar (le falta solo la prueba de elección)."""
        self.sesion0()
        fuentes = self.fuente("competencia", 3, "medido")
        self.p("tipo", "--existente", "--motivo", "Hay dos apps directas con más de 100k descargas")
        self.p("competidor", "--nombre", "RiegoFácil", "--peldano", 1, "--fuentes", fuentes[0], "--descargas", "1M",
               "--precio", "3,99 al mes", "--modelo", "suscripción", "--tamano-mb", "80")
        self.p("competidor", "--nombre", "PlantaPlus", "--peldano", 1, "--fuentes", fuentes[1], "--descargas",
               "500k", "--precio", "gratis", "--modelo", "anuncios", "--tamano-mb", "120", "--rival")
        self.sustituto(fuentes[2])
        self.hallazgo("competencia", fuentes, "--critico", "--sin-contra", "Se buscó y no apareció")
        self.cerrar("1a", "01-investigacion/competencia.md")
        voz = self.linea("1b", "voz-del-usuario", "usuario", 1, "--competidores", "RiegoFácil,PlantaPlus")
        for sesion, nombre in (("1c", "demanda"), ("1d", "monetizacion"), ("1e", "politicas")):
            self.linea(sesion, nombre)
        eleccion, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 3), "--critico", "--sin-contra",
                                    "Se buscó y no apareció")
        suelto, _ = self.hallazgo("diferenciacion", self.fuente("diferenciacion", 1))  # sin triangular
        for numero, (se_ve, copiable, probar) in enumerate(specs, 1):
            self.p("diferenciador", "--vector", "usabilidad", "--texto", "Diferenciador inventado %d" % numero,
                   "--hallazgos", voz, "--se-ve", se_ve, "--copiable", copiable, "--motivo", "Motivo inventado",
                   "--semanas", 2, *(["--principal"] if numero == 1 else []))
            self.p("frente", "--id", "D-%d" % numero, "--resultado", "supera", "--hallazgos",
                   "%s,%s" % (voz, suelto if probar else eleccion), "--texto", "Lo supera en algo inventado")
        self.cerrar("1g", "01-investigacion/diferenciacion.md")

    def estados(self):
        registro = base.producto.Registro(self.carpeta, self.datos()["criterios"])
        return [registro.estado(d) for d in registro.diferenciadores.values()]


class AnclaDefendibleTest(Base):
    def test_uno_viable_de_copia_media_llega_a_4_y_el_rechazo_dice_que_falta(self):
        self.con_diferenciadores(("ficha", "media", False))
        error = self.falla("puntaje", "--valores", "4,4,4,4,5")
        self.assertIn("Diferenciación = 5 no corresponde: ningún par de viables difíciles de copiar, con copiabilidad "
                      "baja o media, ni uno viable que se vea en la ficha con copiabilidad baja: D-1 copiable con "
                      "esfuerzo, se ve en la ficha. El máximo es 4", error)
        self.assertIn("Total: 20/25", self.p("puntaje", "--valores", "4,4,4,4,4"))

    def test_varios_viables_faciles_de_copiar_no_llegan_a_5(self):
        self.con_diferenciadores(("uso", "alta", False), ("ficha", "alta", False), ("uso", "alta", False))
        self.assertEqual(self.estados(), ["viable"] * 3)
        error = self.falla("puntaje", "--valores", "4,4,4,4,5")
        self.assertIn("D-1 fácil de copiar, se ve en el uso; D-2 fácil de copiar, se ve en la ficha; D-3 fácil de "
                      "copiar, se ve en el uso", error)
        self.p("puntaje", "--valores", "4,4,4,4,4")

    def test_uno_de_copia_media_y_otro_facil_tampoco(self):
        self.con_diferenciadores(("ficha", "media", False), ("uso", "alta", False))
        self.assertIn("ningún par de viables difíciles de copiar", self.falla("puntaje", "--valores", "4,4,4,4,5"))

    def test_dos_viables_que_no_son_faciles_de_copiar_llegan_a_5(self):
        self.con_diferenciadores(("ficha", "media", False), ("uso", "baja", False))
        self.assertIn("Total: 21/25", self.p("puntaje", "--valores", "4,4,4,4,5"))

    def test_uno_en_la_ficha_y_dificil_de_copiar_llega_a_5(self):
        self.con_diferenciadores(("ficha", "baja", False))
        self.assertIn("Total: 21/25", self.p("puntaje", "--valores", "4,4,4,4,5"))

    def test_uno_dificil_de_copiar_que_solo_se_ve_en_el_uso_no_llega_a_5(self):
        self.con_diferenciadores(("uso", "baja", False))
        self.assertIn("D-1 difícil de copiar, se ve en el uso", self.falla("puntaje", "--valores", "4,4,4,4,5"))

    def test_los_que_se_pueden_probar_cuentan_con_la_misma_regla(self):
        self.con_diferenciadores(("ficha", "media", False), ("uso", "media", True))
        self.assertEqual(self.estados(), ["viable", "baja"])
        self.p("puntaje", "--valores", "4,4,4,4,5")  # D-2 se puede probar: cuenta como el segundo viable

    def test_uno_que_se_puede_probar_solo_llega_a_4_si_no_es_defendible(self):
        self.con_diferenciadores(("ficha", "media", True))
        self.assertEqual(self.estados(), ["baja"])
        self.assertIn("D-1 copiable con esfuerzo, se ve en la ficha", self.falla("puntaje", "--valores", "4,4,4,4,5"))
        self.p("puntaje", "--valores", "4,4,4,4,4")  # sin la regla de #47, el máximo sería 2

    def test_un_5_registrado_antes_queda_como_se_registro_y_cambia_la_puerta_1(self):
        self.con_diferenciadores(("ficha", "media", False), ("uso", "alta", False))
        self.p("puntaje", "--valores", "3,3,3,4,4")
        datos = self.datos()  # como lo dejó la 0.1.0: 17/25 con diferenciación 5
        datos["puntaje"]["valores"].update(riesgo=3, diferenciacion=5)
        write(self.carpeta / "producto.json", json.dumps(datos, ensure_ascii=False, indent=2))
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE  →  la skill recomienda: DESCARTAR", salida)
        self.assertIn("Con las reglas de hoy el puntaje es 16/25 (se registró 17/25), bajo el mínimo de 17: "
                      "diferenciación 5, pero con las reglas de hoy el máximo es 4 (ningún par de viables difíciles de "
                      "copiar", salida)
        self.assertIn("✖ Puntaje de 17/25 o más · tiene 16/25 (se registró 17/25)", salida)
        guardado = self.datos()["puntaje"]
        self.assertEqual((guardado["valores"]["diferenciacion"], guardado["total"]), (5, 17))  # no reescribe datos

    def test_el_minimo_sigue_diciendo_su_propio_motivo(self):
        self.con_diferenciadores(("ficha", "media", False))
        self.p("puntaje", "--valores", "4,4,4,4,2")
        datos = self.datos()
        datos["puntaje"]["valores"]["diferenciacion"] = 1
        write(self.carpeta / "producto.json", json.dumps(datos, ensure_ascii=False, indent=2))
        salida = self.p("puerta", "--n", 1)
        self.assertIn("diferenciación 1, pero con las reglas de hoy el mínimo es 2 (hay 1 diferenciador viable)", salida)


class ConfianzaNoEsDireccionTest(Base):
    def test_demanda_pequena_en_alta_falla_por_el_puntaje_no_por_la_confianza(self):
        self.con_diferenciadores(("ficha", "media", False))
        ruta = self.carpeta / "01-investigacion" / "demanda.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["hallazgos"][0]["texto"] = "La demanda es pequeña: las búsquedas de la categoría son pocas y estables"
        write(ruta, json.dumps(datos, ensure_ascii=False, indent=2))
        salida = self.p("puntaje", "--valores", "1,4,4,4,3")
        self.assertIn("confianza alta (H-DEM-1)", salida)  # confirmar que es pequeña sube la confianza
        self.assertIn("Total: 16/25", salida)
        salida = self.cerrar("1f", "01-sintesis.md")
        self.assertIn("🔴  PUERTA 1 · NO VIABLE", salida)
        self.assertIn("El puntaje es 16/25, bajo el mínimo de 17.", salida)
        self.assertIn("✔ Demanda con confianza media o alta · es alta", salida)
        self.assertIn("✖ Puntaje de 17/25 o más · tiene 16/25", salida)
        self.assertNotIn("la demanda tiene confianza", salida)


class DistribucionTest(Base):
    def test_la_distribucion_no_es_un_vector_y_manda_a_la_estrategia(self):
        self.assertNotIn("distribucion", base.producto.VECTORES)
        self.nuevo()
        hallazgo, _ = self.hallazgo("competencia", self.fuente("competencia", 1, "medido"))
        for vector in ("distribucion", "distribución", "aso"):
            error = self.falla("diferenciador", "--vector", vector, "--texto", "Sale arriba en otro país",
                               "--hallazgos", hallazgo, "--se-ve", "ficha", "--copiable", "alta", "--motivo", "x",
                               "--semanas", 1)
            self.assertIn("La distribución no es un vector de diferenciación ni cuenta en la puerta 1", error)
            self.assertIn("Regístrala como hallazgo de la línea competencia", error)
            self.assertIn("la sesión 2 la usa para el canal de adquisición", error)
        self.assertIn("--vector magia no existe: usa uno de usabilidad", self.falla(
            "diferenciador", "--vector", "magia", "--texto", "x", "--hallazgos", hallazgo, "--se-ve", "uso",
            "--copiable", "baja", "--motivo", "x", "--semanas", 1))
        self.assertEqual(self.datos("01-investigacion/diferenciacion.json")["diferenciadores"], [])


class VersionTest(unittest.TestCase):
    """La versión que muestra el script es la de metadata.version del SKILL.md."""

    def test_version_del_script_igual_a_la_del_skill(self):
        raiz = Path(__file__).resolve().parent.parent / "skills" / "hb-product"
        skill = (raiz / "SKILL.md").read_text(encoding="utf-8")
        guion = (raiz / "scripts" / "producto.py").read_text(encoding="utf-8")
        en_skill = re.search(r'^\s*version:\s*"([^"]+)"', skill, re.M).group(1)
        en_guion = re.search(r'^VERSION = "([^"]+)"', guion, re.M).group(1)
        self.assertEqual(en_skill, en_guion)


if __name__ == "__main__":
    unittest.main()
