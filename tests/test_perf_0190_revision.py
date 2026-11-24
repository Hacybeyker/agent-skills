"""Tests de hb-performance 0.19.0, lo que destapó la primera prueba real del modo orquestado (P1–P9). Los datos son
inventados."""
import hashlib
import json
import re
import unittest

from helpers import write
from test_perf import HEADER, PKG, PerfBase, perf, rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManagementTranslationTest(PerfBase):
    """P1: quien traduce para gerencia es el reporte. Un plan con "ms" y términos técnicos genera el reporte de gerencia
    sin avisos y sin tocar plan.json ni estado.md; lo que no tiene traducción pide un campo de gerencia."""

    def setUp(self):
        super().setUp()
        self.folder = self.dir / "inv"
        self.plan = {"paquete": PKG, "principales": ["lista_ms"], "flujos": {"lista": {"recorrido": "true"}},
                     "hallazgos": [{"id": "H1", "titulo": "Doble carga"}],
                     "mejoras": [{"id": "M1", "hallazgo": "H1", "titulo": "Sacar la lectura del hilo principal",
                                  "metrica": "lista_ms", "estado": "aplicada", "costo": "unos 90 ms más en el backend",
                                  "condicion": "cuando hay jank al abrir", "riesgo": "bajo: no cambia el TTFB",
                                  "que_gana": "la lista aparece antes"}]}
        write(self.folder / "plan.json", json.dumps(self.plan))
        write(self.folder / "metricas.csv", HEADER + rows("antes", "lista", "lista_ms", [1800] * 5)
              + rows("control", "lista", "lista_ms", [1790] * 5) + rows("despues", "lista", "lista_ms", [900] * 5))
        write(self.folder / "fases.json", json.dumps({phase: {"corridas": 5, "fecha": "2026-03-02T10:00:00"}
                                                      for phase in ("antes", "control", "despues")}))
        write(self.folder / "estado.md", (
            "# Rendimiento · Lista · 2026-11-09\n\n## Ficha\n\n| Campo | Valor |\n| --- | --- |\n"
            "| Síntoma | Lentitud y pérdida de frames al abrir la lista |\n\n"
            "## Hallazgos\n\n| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n"
            "| H1 | La lista tarda unos 300 ms más | 2 llamadas | El endpoint se llama dos veces en el hilo principal "
            "| bug |\n\n## Resumen para gerencia\n\nLa lista tardaba casi 2 s; ahora aparece en 1 s.\n\n"
            "## Consumo\n\n| Sesión | Modelo | Costo o tokens | Pasos |\n| --- | --- | --- | --- |\n"))

    def test_traduce_sin_avisos_y_sin_tocar_los_datos(self):
        # la primera vez, perf.py agrega sus bloques a estado.md (advertencias, total del costo); desde ahí, generar el
        # reporte no cambia ni un byte de plan.json ni de estado.md
        self.ok("reporte", "--carpeta", self.folder)
        before = (digest(self.folder / "plan.json"), digest(self.folder / "estado.md"))
        out = self.ok("reporte", "--carpeta", self.folder, "--html")
        self.assertNotIn("⚠ Gerencia: un texto", out)
        self.assertEqual((digest(self.folder / "plan.json"), digest(self.folder / "estado.md")), before)
        text = (self.folder / "reporte-final-gerencia.md").read_text(encoding="utf-8")
        page = re.sub(r"<(style|script)>.*?</\1>", "", (self.folder / "reporte-final-gerencia.html").read_text(
            encoding="utf-8"), flags=re.S)  # solo lo que se lee: el CSS no se publica
        for term in ("frames", " ms", "backend", "hilo principal", "endpoint", "jank", "TTFB"):
            self.assertNotIn(term, text)
            self.assertNotIn(term, page)
        self.assertIn("Lentitud y pérdida de cuadros al abrir la lista", text)
        self.assertIn("90 milisegundos", page)

    def test_lo_que_no_se_traduce_pide_un_campo_de_gerencia(self):
        plan = dict(self.plan, mejoras=[dict(self.plan["mejoras"][0], titulo="Mover `cargarClientes()` a otro lugar")])
        write(self.folder / "plan.json", json.dumps(plan))
        out = self.ok("reporte", "--carpeta", self.folder, "--html")
        self.assertIn("completa en palabras titulo_gerencia de M1 en plan.json", out)
        self.assertNotIn("Ficha de estado.md", out)
        self.assertNotIn("Hallazgos de estado.md", out)
        # con el campo de gerencia completo, se publica ese y no hay aviso
        plan["mejoras"][0]["titulo_gerencia"] = "Cargar los clientes una sola vez"
        write(self.folder / "plan.json", json.dumps(plan))
        out = self.ok("reporte", "--carpeta", self.folder, "--html")
        self.assertNotIn("⚠ Gerencia: un texto", out)
        self.assertIn("Cargar los clientes una sola vez",
                      (self.folder / "reporte-final-gerencia.md").read_text(encoding="utf-8"))

    def test_el_sintoma_de_gerencia_va_en_el_plan_no_en_la_ficha(self):
        plan = dict(self.plan, gerencia={"sintoma": "La lista tarda y se traba al abrirla"})
        write(self.folder / "plan.json", json.dumps(plan))
        self.ok("reporte", "--carpeta", self.folder)
        text = (self.folder / "reporte-final-gerencia.md").read_text(encoding="utf-8")
        self.assertIn("La lista tarda y se traba al abrirla", text)
        self.assertIn("pérdida de frames", (self.folder / "estado.md").read_text(encoding="utf-8"))

    def test_glosario(self):
        cases = {"Sacar del hilo principal la lectura": "Sacar de la parte de la app que atiende la pantalla la lectura",
                 "Jank al abrir": "Tirones al abrir", "El TTFB del backend bajó unos 90 ms":
                 "La espera de la respuesta del servidor bajó unos 90 milisegundos",
                 "el P90 tarda 1200 ms": "el 10 % más lento tarda 1.2 s", "TTID bajó": "El tiempo hasta ver la primera "
                 "pantalla bajó", "La mediana de la traza": "El valor típico del registro de la medición"}
        for text, expected in cases.items():
            self.assertEqual(perf.for_management(text), expected)
            self.assertEqual(perf.jargon(perf.for_management(text)), [])
        # los nombres de librerías y de código no se traducen: cambiaría lo que dicen
        self.assertEqual(perf.jargon(perf.for_management("Usar LazyColumn en vez de RecyclerView")),
                         ["LazyColumn", "RecyclerView"])


if __name__ == "__main__":
    unittest.main()
