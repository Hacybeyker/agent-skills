"""El contrato común del modelo de estructura entre skills: el párrafo "Modelo de estructura" idéntico en las cinco
skills que leen el modelo, el de "Mapa del módulo" idéntico en las tres que trabajan sobre una unidad, y un mismo
INDEX.md que hb-implement (report.py) y hb-performance (perf.py) comparten sin pisarse las filas."""
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, commit_all, init_repo, run, write

SKILLS = ROOT / "skills"
REPORT = SKILLS / "hb-implement" / "scripts" / "report.py"
PERF = SKILLS / "hb-performance" / "scripts" / "perf.py"
INDEX_HEADER = "| Fecha | Skill | Slug | Tipo | Estado | Ruta |"


def paragraphs(skill, title):
    """Cada aparición del párrafo que empieza con el título en negrita, hasta el final de la línea, en los .md de la
    skill (sin la sangría, la viñeta o la cita que lo precedan)."""
    found = []
    for md in sorted((SKILLS / skill).rglob("*.md")):
        for line in md.read_text(encoding="utf-8").splitlines():
            index = line.find(title)
            if index != -1 and not line[:index].strip(" ->*0123456789."):
                found.append(line[index:].rstrip())
    return found


class SharedParagraphsTest(unittest.TestCase):
    def check(self, title, skills):
        texts = {}
        for skill in skills:
            found = paragraphs(skill, title)
            self.assertTrue(found, "%s no trae el párrafo %s" % (skill, title))
            texts.update({(skill, i): text for i, text in enumerate(found)})
        self.assertEqual(len(set(texts.values())), 1, "el párrafo %s difiere entre skills: %s"
                         % (title, sorted({k[0] for k in texts})))

    def test_modelo_de_estructura_identico_en_las_cinco_skills(self):
        self.check("**Modelo de estructura.**", ("hb-implement", "hb-performance", "hb-review", "hb-commit",
                                                  "hb-release"))

    def test_mapa_del_modulo_identico_en_las_tres_skills(self):
        self.check("**Mapa del módulo.**", ("hb-implement", "hb-performance", "hb-review"))

    def test_nadie_llama_ficha_al_mapa_del_modulo(self):
        for skill in ("hb-setup", "hb-implement", "hb-performance", "hb-review"):
            for md in (SKILLS / skill).rglob("*.md"):
                self.assertNotRegex(md.read_text(encoding="utf-8"), r"(?i)ficha (de|por) (la )?unidad|ficha del módulo",
                                    str(md))


class SharedIndexTest(unittest.TestCase):
    """report.py y perf.py escriben el mismo INDEX.md con la misma cabecera y solo tocan su fila."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name) / "app-shell"
        base.mkdir()
        self.repo = init_repo(base)
        write(self.repo / "AGENTS.md", "# App\n\n## Reglas del proyecto\n\n- Carpeta de reportes: `reports`\n")
        write(self.repo / "src" / "a.txt", "a\n")
        commit_all(self.repo, "base")
        spec = importlib.util.spec_from_file_location("perf_comun", str(PERF))
        self.perf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.perf)

    def tearDown(self):
        self.tmp.cleanup()

    def test_las_dos_skills_comparten_una_tabla_sin_pisarse(self):
        result = run([sys.executable, "-I", REPORT, "--folder", "pagos", "--date", "2026-11-25", "--repo", self.repo],
                     self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = self.repo / "reports" / "performance" / "inicio" / "2026-11-25"
        folder.mkdir(parents=True)
        self.perf.update_reports_index(self.repo, folder, {}, "en curso")
        text = (self.repo / "reports" / "INDEX.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(INDEX_HEADER), 1, text)
        self.assertEqual(text.count("# Índice de reportes"), 1, text)
        rows = [line for line in text.splitlines() if line.startswith("| 2026-")]
        self.assertEqual(len(rows), 2, text)
        self.assertIn("| hb-implement | pagos |", rows[0])
        self.assertIn("| hb-performance | inicio/2026-11-25 |", rows[1])
        # report.py vuelve a escribir su fila (al generar el reporte) y la de perf queda igual
        write(self.repo / "src" / "a.txt", "b\n")  # la tarea cambia algo después de la foto: sin cambios no hay reporte
        meta = self.repo / "reports" / "implementation" / "2026-11-25-pagos" / "meta.json"
        meta.write_text(json.dumps({"title": "Pagos", "slug": "pagos", "date": "2026-11-25", "type": "feature",
                                    "dod": [{"name": "Tests", "status": "pass"}]}), encoding="utf-8")
        result = run([sys.executable, "-I", REPORT, "--meta", meta, "--repo", self.repo], self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = (self.repo / "reports" / "INDEX.md").read_text(encoding="utf-8")
        rows_after = [line for line in after.splitlines() if line.startswith("| 2026-")]
        self.assertEqual(rows_after[1], rows[1])
        self.assertIn("DoD PASS", rows_after[0])
        self.assertTrue(re.search(r"\]\(implementation/2026-11-25-pagos/report\.html\)", rows_after[0]), rows_after[0])
        self.assertTrue(os.path.isfile(str(self.repo / "reports" / "implementation" / "2026-11-25-pagos" /
                                           "report.html")))


if __name__ == "__main__":
    unittest.main()
