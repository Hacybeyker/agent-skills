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

    def test_un_meta_invalido_termina_con_error(self):
        self.meta.write_text("{no es json", encoding="utf-8")
        result = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("✖", result.stderr)


if __name__ == "__main__":
    unittest.main()
