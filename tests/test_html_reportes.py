"""hb-performance 0.19.0 · P10: ningún texto cortado en los HTML de la skill. Genera cada reporte (inicial y final, dev y
gerencia) y la página de la prueba con fixtures, los abre en Chromium sin interfaz (Playwright) a 375, 768 y 1280 px,
en tema claro y oscuro, y falla si un elemento con texto tiene scrollWidth > clientWidth (salvo los que se desplazan a
propósito), si un texto sobresale de un contenedor que lo recorta o si la página tiene scroll horizontal. Guarda una
captura de cada caso en HB_CAPTURAS (por defecto, <tmp>/hb-performance-capturas) para revisarlas a ojo.

Sin Playwright, el test se salta con un aviso visible. Para correrlo: un entorno con `pip install playwright` y su
Chromium (`playwright install chromium`). Datos inventados."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import write
from test_perf import HEADER, PKG, perf, rows
from test_perf_0190_red import FASES, TRAZA, record

WIDTHS = (375, 768, 1280)
THEMES = ("light", "dark")
LONG_SERVICE = "GET api/v2/catalogo/destacados/{id}/recomendaciones-personalizadas-para-la-portada"
CHECK = r"""
() => {
  const bad = [], doc = document.documentElement;
  const say = (el, why) => bad.push(why + " · <" + el.tagName.toLowerCase() + (el.className && el.className.baseVal === undefined ? "." + String(el.className).trim().replace(/\s+/g, ".") : "") + "> «" + (el.textContent || "").trim().slice(0, 70) + "»");
  if (doc.scrollWidth > window.innerWidth + 1) bad.push("la página tiene scroll horizontal: " + doc.scrollWidth + " > " + window.innerWidth);
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
  const clippers = (el) => {
    const out = [];
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (/(auto|scroll)/.test(cs.overflowX + cs.overflowY)) break;  // se desplaza: el texto se alcanza
      if (/(hidden|clip)/.test(cs.overflowX + cs.overflowY)) out.push(p);
    }
    return out;
  };
  for (const el of document.querySelectorAll("body *")) {
    if (["SCRIPT", "STYLE", "TITLE"].includes(el.tagName) || el.closest("svg")) continue;
    const texts = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
    if (!texts.length || !visible(el)) continue;
    const cs = getComputedStyle(el);
    if (!/(auto|scroll)/.test(cs.overflowX) && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1 && cs.display !== "inline")
      say(el, "scrollWidth " + el.scrollWidth + " > clientWidth " + el.clientWidth);
    const boxes = clippers(el).map((p) => p.getBoundingClientRect());
    for (const node of texts) {
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) {
        if (!r.width) continue;
        for (const b of boxes) {
          if (r.left < b.left - 1 || r.right > b.right + 1 || r.top < b.top - 1 || r.bottom > b.bottom + 1) { say(el, "el texto sobresale de su contenedor"); break; }
        }
      }
    }
  }
  for (const t of document.querySelectorAll("svg text")) {
    const svg = t.ownerSVGElement, a = t.getBoundingClientRect(), b = svg.getBoundingClientRect();
    if (a.width && visible(svg) && (a.left < b.left - 1 || a.right > b.right + 1)) say(t, "el texto sobresale del gráfico");
  }
  return bad;
}
"""


def investigation(base):
    """Una investigación cerrada con todo lo que los reportes muestran, con textos largos a propósito: rutas largas,
    títulos largos y la barra "¿En qué se van los N s?" con un segmento angosto (el caso real: 0,03 s de la app)."""
    folder = base / "inv"
    plan = {"paquete": PKG, "principales": ["lista_ms"], "etiquetas": {"lista_ms": "Tiempo hasta ver la lista de destacados"},
            "flujos": {"lista": {"recorrido": "true", "titulo": "Abrir la portada y ver la lista de destacados completa",
                                 "ventana": {"desde": {"marca": "MARK inicio"}, "hasta": {"marca": "MARK lista"}},
                                 "metricas_usuario": [{"nombre": "lista_ms", "desde": {"marca": "MARK inicio"},
                                                       "hasta": {"marca": "MARK lista"}}]}},
            "hallazgos": [{"id": "H1", "titulo": "La portada espera una recomendación que podría cargarse después",
                           "titulo_gerencia": "La portada espera datos que podrían llegar después",
                           "causa_gerencia": "La pantalla no se muestra hasta recibir todas las recomendaciones"}],
            "mejoras": [{"id": "M1", "hallazgo": "H1", "titulo": "Mostrar la portada antes de recibir las recomendaciones "
                                                                  "personalizadas de la sección de destacados",
                         "metrica": "lista_ms", "estado": "aplicada", "riesgo": "medio: cambia el orden en que se "
                         "dibujan las secciones de la portada", "que_gana": "la portada aparece casi un segundo antes",
                         "costo": "una llamada más cuando el usuario vuelve a la portada"}]}
    write(folder / "plan.json", json.dumps(plan))
    write(folder / "metricas.csv", HEADER + rows("antes", "lista", "lista_ms", [3000, 2950, 3050, 3010, 2990]) +
          rows("control", "lista", "lista_ms", [3005, 2960, 3040, 3000, 2995]) +
          rows("despues", "lista", "lista_ms", [2100, 2080, 2120, 2090, 2110]) +
          rows("antes", "lista", "red %s ttfb_ms" % LONG_SERVICE, [2900] * 5, family="e2e") +
          rows("despues", "lista", "red %s ttfb_ms" % LONG_SERVICE, [2000] * 5, family="e2e"))
    write(folder / "fases.json", json.dumps({phase: {"corridas": 5, "fecha": "2026-03-02T10:0%d:00" % i}
                                             for i, phase in enumerate(("antes", "control", "despues"))}))
    timeline = {"llamadas": [[LONG_SERVICE, 30, 2950]], "marcas": [["MARK inicio", 0], ["MARK lista", 3000]]}
    for phase in ("antes", "control", "despues"):
        for run in range(1, 6):
            write(folder / phase / ("lista_%d%s" % (run, perf.TIMELINE_SUFFIX)), json.dumps(timeline))
    write(folder / "estado.md", (
        "# Rendimiento · Portada · 2026-03-02\n\n## Ficha\n\n| Campo | Valor |\n| --- | --- |\n"
        "| Síntoma | La portada tarda en mostrar la lista de destacados cuando se abre la app por la mañana |\n\n"
        "## Hallazgos\n\n| # | Síntoma | Evidencia | Causa raíz | Tipo |\n| --- | --- | --- | --- | --- |\n"
        "| H1 | La portada tarda | `lista_ms` | Espera la recomendación | mejorable |\n\n"
        "## Resumen ejecutivo\n\nLa portada tardaba 3 s y ahora tarda 2,1 s.\n\n"
        "## Resumen para gerencia\n\nLa portada tardaba unos 3 segundos y ahora unos 2.\n\n"
        "## Consumo\n\n| Sesión | Modelo | Costo o tokens | Pasos |\n| --- | --- | --- | --- |\n"))
    return folder


def test_page(base):
    """La página de la prueba con el panel de red: rutas largas con query y un cuerpo grande."""
    records = {"0001": record("0001", 101_310 * 10 ** 6, "page=1&orden=popularidad&idioma=es&region=XX&incluir="
                                                         "recomendaciones-personalizadas-de-la-portada", body="x" * 5000),
               "0002": record("0002", 102_002 * 10 ** 6, "page=2")}
    calls, summary = perf.network_panel(TRAZA, lambda ns: ns / 1e9 - 100.0, records, {"fases": FASES, "duracion": 5.0})
    events = {"version": 2, "flujo": "portada", "grabador": "screenrecord", "duracion": 5.0, "fases": FASES,
              "marcas": [{"t": 1.5, "nombre": "MARK lista_de_destacados_completa_y_visible", "papel":
                          "fin de Abrir la portada y ver la lista de destacados completa", "usada": True}],
              "tramos_video": [{"archivo": "video/portada/parte1.mp4", "inicio": 0.0}],
              "leyenda": ["Video: toda la prueba · Traza: desde el fin de la preparación",
                          "Métrica: solo cuenta lo marcado Medición"],
              "eventos_traza": perf.trace_events(TRAZA, lambda ns: ns / 1e9 - 100.0, 5.0), "red": calls,
              "red_resumen": summary, "sincronia": {"estado": "validada", "desfase_ms": 38, "marca": "MARK lista",
                                                    "tolerancia_ms": 100, "uptime_inicio_s": 100.0,
                                                    "metodo": "uptime del dispositivo"}}
    path = base / "prueba-portada.html"
    path.write_text(perf.video_page_html(events, "demo", "2026-11-23"), encoding="utf-8")
    return path


class HtmlTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            sys.stderr.write("\n⚠ test_html_reportes: Playwright no está instalado; no reviso los HTML en un navegador "
                             "(pip install playwright y playwright install chromium)\n")
            raise unittest.SkipTest("Playwright no está instalado: la revisión de los HTML en un navegador se saltó")
        cls.base = pathlib.Path(tempfile.mkdtemp())
        folder = investigation(cls.base)
        for extra in (["--inicial"], []):
            result = subprocess.run(
                [sys.executable, "-I", str(perf.HERE / "perf.py"), "reporte", "--carpeta", str(folder), "--html"] + extra,
                cwd=str(cls.base), capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                raise AssertionError(result.stdout + result.stderr)
        cls.pages = sorted(folder.glob("reporte-*.html")) + [test_page(folder)]
        cls.shots = pathlib.Path(os.environ.get("HB_CAPTURAS") or (pathlib.Path(tempfile.gettempdir()) /
                                                                   "hb-performance-capturas"))
        shutil.rmtree(str(cls.shots), ignore_errors=True)
        cls.shots.mkdir(parents=True)
        sys.stderr.write("\n· test_html_reportes: capturas en %s\n" % cls.shots)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(getattr(cls, "base", "")), ignore_errors=True)

    def test_ningun_texto_cortado(self):
        from playwright.sync_api import sync_playwright, Error
        problems = []
        with sync_playwright() as play:
            try:
                browser = play.chromium.launch()
            except Error as error:
                self.skipTest("Playwright sin Chromium (playwright install chromium): %s" % str(error).splitlines()[0])
            for page_path in self.pages:
                for theme in THEMES:
                    context = browser.new_context(color_scheme=theme, viewport={"width": WIDTHS[0], "height": 900})
                    page = context.new_page()
                    page.goto(page_path.as_uri())
                    for width in WIDTHS:
                        page.set_viewport_size({"width": width, "height": 900})
                        page.wait_for_timeout(50)
                        for issue in page.evaluate(CHECK):
                            problems.append("%s · %d px · %s: %s" % (page_path.name, width, theme, issue))
                        page.screenshot(path=str(self.shots / ("%s-%d-%s.png" % (page_path.stem, width, theme))),
                                        full_page=True)
                    context.close()
            browser.close()
        self.assertEqual(problems, [], "\n".join(problems[:40]))
        self.assertEqual(len(list(self.shots.glob("*.png"))), len(self.pages) * len(WIDTHS) * len(THEMES))

    def test_la_barra_no_corta_el_segmento_angosto(self):
        """El caso real: el segmento de 0,03 s no lleva un texto cortado; el ancho lleva el texto completo."""
        from playwright.sync_api import sync_playwright
        page_path = next(path for path in self.pages if path.name == "reporte-final-gerencia.html")
        with sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={"width": 375, "height": 900})
            page.goto(page_path.as_uri())
            segments = page.evaluate("() => [...document.querySelectorAll('.stack [data-full]')].map(s => [s.dataset.full, "
                                     "s.textContent, s.scrollWidth <= s.clientWidth])")
            browser.close()
        self.assertTrue(segments, "sin la barra ¿En qué se van los N s?")
        narrow = segments[0]
        self.assertIn(narrow[1], ("", narrow[0], narrow[0].split(" · ")[0]))
        self.assertNotEqual(narrow[1], narrow[0])  # 0,03 s de 3 s no entra completo a 375 px
        self.assertTrue(all(fits for _, _, fits in segments))
        wait = segments[1]
        self.assertEqual(wait[1], wait[0])  # la espera, ancha, lleva su texto completo


if __name__ == "__main__":
    unittest.main()
