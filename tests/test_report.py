"""Tests del reporte HTML de hb-implement (skills/hb-implement/scripts/report.py)."""
import base64
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, init_repo, run, write

SCRIPT = ROOT / "skills" / "hb-implement" / "scripts" / "report.py"
META = {
    "title": "Prueba <x>",
    "type": "bugfix",
    "date": "2026-01-02",
    "description": "Descripción",
    "files": {"a.txt": {"before": "antes", "after": "después"}},
    "dod": [
        {"name": "Tests", "command": "make test", "status": "pass"},
        {"name": "Lint", "command": "make lint", "status": "fail", "output": "error <1>"},
    ],
}


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "repo").mkdir()
        self.repo = init_repo(base / "repo")
        write(self.repo / "a.txt", "uno\n")
        write(self.repo / "c.txt", "borrar\n")
        commit_all(self.repo, "base")
        write(self.repo / "a.txt", "dos <b>\n")  # modificado
        write(self.repo / "b.txt", "nuevo\n")  # nuevo
        (self.repo / "bin.dat").write_bytes(b"\x00\x01\x02")  # nuevo y binario
        (self.repo / "c.txt").unlink()  # eliminado
        self.meta = base / "meta.json"  # fuera del repo, para que no cuente como cambio
        self.meta.write_text(json.dumps(META), encoding="utf-8")
        self.out = self.repo / "reports" / "2026-01-02-prueba-x.html"

    def tearDown(self):
        self.tmp.cleanup()

    def generate(self):
        return run([sys.executable, "-I", SCRIPT, "--meta", self.meta, "--repo", self.repo], self.repo)

    def html(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.out.read_text(encoding="utf-8")

    def stat(self, html, label):
        return re.search(r"%s</div><div class=\"stat-value[^\"]*\"[^>]*>([^<]+)<" % label, html).group(1)

    def test_genera_el_reporte_con_la_fecha_y_el_titulo_en_el_nombre(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.out.is_file())
        self.assertIn("reports/2026-01-02-prueba-x.html", result.stdout)

    def test_cuenta_los_archivos_por_estado(self):
        html = self.html()
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")
        self.assertEqual(self.stat(html, "Archivos Modificados"), "1")
        self.assertEqual(self.stat(html, "Archivos Eliminados"), "1")

    def test_escapa_el_html_del_titulo_y_del_codigo(self):
        html = self.html()
        self.assertIn("Prueba &lt;x&gt;", html)
        self.assertIn("dos &lt;b&gt;", html)
        self.assertNotIn("Prueba <x>", html)

    def test_muestra_el_tipo_y_las_explicaciones(self):
        html = self.html()
        self.assertIn("🐛 Bug Fix", html)
        self.assertIn("después", html)

    def test_un_paso_del_dod_fallido_deja_el_resultado_en_fail(self):
        html = self.html()
        self.assertEqual(self.stat(html, "DoD"), "FAIL")
        self.assertIn("✅ PASS", html)
        self.assertIn("error &lt;1&gt;", html)

    def test_no_muestra_el_contenido_de_un_binario(self):
        self.assertIn("Archivo binario", self.html())

    def test_avisa_los_archivos_sin_explicacion_y_la_carpeta_sin_ignorar(self):
        result = self.generate()
        self.assertIn("Archivos sin explicación en meta.json", result.stderr)
        self.assertIn("b.txt", result.stderr)
        self.assertIn("no está en .gitignore", result.stderr)

    def test_al_regenerar_no_se_incluye_a_si_mismo(self):
        self.html()
        self.assertEqual(self.stat(self.html(), "Archivos Nuevos"), "2")

    def with_previews(self, previews):
        self.meta.write_text(json.dumps(dict(META, previews=previews)), encoding="utf-8")

    def test_sin_previews_no_hay_seccion_de_previews(self):
        self.assertNotIn("Previews de UI", self.html())

    def test_incrusta_los_previews_y_no_los_cuenta_como_archivos(self):
        png = b"\x89PNG\r\n\x1a\nfalso"
        image = self.repo / "reports" / "previews" / "home.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(png)
        absolute = Path(self.tmp.name) / "fuera.png"
        absolute.write_bytes(png)
        self.with_previews([
            {"name": "HomeContentPreview", "image": "reports/previews/home.png", "note": "Saludo <inicial>"},
            {"name": "Otra", "image": str(absolute)},
        ])
        html = self.html()
        self.assertIn("Previews de UI", html)
        self.assertEqual(html.count("data:image/png;base64,%s" % base64.b64encode(png).decode("ascii")), 2)
        self.assertIn("Saludo &lt;inicial&gt;", html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")

    def test_un_preview_sin_imagen_avisa_sin_fallar(self):
        self.with_previews([{"name": "Falta", "image": "reports/previews/no-existe.png"}])
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preview sin imagen", result.stderr)
        self.assertIn("No se encontró la imagen", self.out.read_text(encoding="utf-8"))

    def with_meta(self, **extra):
        self.meta.write_text(json.dumps(dict(META, **extra)), encoding="utf-8")

    def add_shots(self, folder="shots", names=("g0.png", "g1.png", "g2.png")):
        for name in names:
            image = self.repo / folder / name
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"\x89PNG\x00" + name.encode("ascii"))

    def count(self, html, title):
        return re.search(r"%s</span><span class=\"section-count\">(\d+)<" % title, html).group(1)

    def test_agrupa_los_archivos_de_una_carpeta_sin_exigir_una_explicacion_cada_uno(self):
        self.add_shots()
        self.with_meta(groups=[{"match": "shots/", "why": "Goldens <nuevos>"}])
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = self.out.read_text(encoding="utf-8")
        self.assertIn("shots/ · 3 archivos", html)
        self.assertIn("Goldens &lt;nuevos&gt;", html)
        self.assertIn("shots/g1.png", html)  # la lista de rutas del grupo
        self.assertEqual(html.count('class="file-path">shots/g'), 0)  # y ninguna entrada propia
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "5")  # 2 de siempre + 3 del grupo
        self.assertEqual(self.count(html, "Archivos Nuevos"), "5")
        self.assertNotIn("g0.png", result.stderr)
        self.assertIn("b.txt", result.stderr)  # los demás siguen pidiendo su explicación

    def test_agrupa_por_patron(self):
        self.add_shots(folder="a/b", names=("x.png", "y.png"))
        self.add_shots(folder="otro", names=("z.png",))
        self.with_meta(groups=[{"match": "*.png", "why": "Imágenes"}])
        result = self.generate()
        html = self.out.read_text(encoding="utf-8")
        self.assertIn("*.png · 3 archivos", html)
        self.assertNotIn("x.png", result.stderr)

    def test_un_archivo_con_su_propia_entrada_se_muestra_aparte_del_grupo(self):
        self.add_shots()
        self.with_meta(groups=[{"match": "shots/", "why": "Goldens"}],
                       files={"a.txt": {"why": "x"}, "shots/g0.png": {"why": "El golden clave"}})
        html = self.html()
        self.assertIn("shots/ · 2 archivos", html)
        self.assertIn('class="file-path">shots/g0.png', html)
        self.assertIn("El golden clave", html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "5")

    def test_el_grupo_se_arma_por_estado_y_respeta_a_los_archivos_con_entrada_propia(self):
        self.with_meta(groups=[{"match": "*.txt", "why": "Textos"}])
        html = self.html()
        # b.txt (nuevo) y c.txt (eliminado) caen en el grupo, cada uno en su sección; a.txt tiene entrada propia.
        self.assertEqual(html.count("*.txt · 1 archivo<"), 2)
        self.assertIn('class="file-path">a.txt', html)
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")
        self.assertEqual(self.stat(html, "Archivos Modificados"), "1")
        self.assertEqual(self.stat(html, "Archivos Eliminados"), "1")

    def test_avisa_de_un_grupo_que_no_cubre_nada_y_sugiere_agrupar_si_faltan_muchos(self):
        self.add_shots(names=tuple("g%d.png" % i for i in range(8)))
        self.with_meta(groups=[{"match": "no-existe/", "why": "x"}])
        result = self.generate()
        self.assertIn('El grupo "no-existe/" no cubre ningún archivo', result.stderr)
        self.assertIn('"groups"', result.stderr)  # 8 goldens + b.txt + bin.dat sin explicación

    def test_el_meta_por_tarea_dentro_de_reports_no_cuenta_como_cambio_y_no_se_pisan(self):
        reports = self.repo / "reports"
        reports.mkdir()
        primero = reports / "2026-01-02-uno.meta.json"
        segundo = reports / "2026-01-02-dos.meta.json"
        primero.write_text(json.dumps(dict(META, title="Uno")), encoding="utf-8")
        segundo.write_text(json.dumps(dict(META, title="Dos")), encoding="utf-8")
        for meta in (primero, segundo):
            result = run([sys.executable, "-I", SCRIPT, "--meta", meta, "--repo", self.repo], self.repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("compartido", result.stderr)
            self.assertNotIn("reports/meta.json", result.stderr)
        self.assertTrue((reports / "2026-01-02-uno.html").is_file())
        self.assertTrue((reports / "2026-01-02-dos.html").is_file())
        html = (reports / "2026-01-02-dos.html").read_text(encoding="utf-8")
        self.assertEqual(self.stat(html, "Archivos Nuevos"), "2")  # los .meta.json de reports/ no cuentan

    def test_el_meta_compartido_de_antes_sigue_funcionando_y_avisa(self):
        reports = self.repo / "reports"
        reports.mkdir()
        shared = reports / "meta.json"
        shared.write_text(json.dumps(META), encoding="utf-8")
        result = run([sys.executable, "-I", SCRIPT, "--meta", shared, "--repo", self.repo], self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.out.is_file())
        self.assertIn("reports/<fecha>-<slug>.meta.json", result.stderr)

    def test_un_meta_invalido_termina_con_error(self):
        self.meta.write_text("{no es json", encoding="utf-8")
        result = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("✖", result.stderr)


if __name__ == "__main__":
    unittest.main()
