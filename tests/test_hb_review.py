"""hb-review: el diff que revisa incluye los archivos nuevos que todavía no están en git."""
import pathlib
import re
import shlex
import tempfile
import unittest

from helpers import ROOT, commit_all, git, init_repo, run, write

SKILL = ROOT / "skills" / "hb-review" / "SKILL.md"
UNTRACKED = "git ls-files --others --exclude-standard"


def section(text, start, end=None):
    first = text.index(start)
    return text[first:text.index(end, first) if end else len(text)]


class UntrackedFilesTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_el_alcance_por_defecto_suma_los_archivos_sin_trackear(self):
        scope = section(self.text, "## 1. Alcance y contexto", "## 2. Qué revisar")
        self.assertIn("`%s`" % UNTRACKED, scope)
        self.assertIn("léelos completos", scope)

    def test_el_modo_rapido_suma_los_archivos_sin_trackear(self):
        quick = section(self.text, "## Modo rápido")
        self.assertIn("`%s`" % UNTRACKED, quick)
        self.assertIn("completos", quick[quick.index(UNTRACKED):])

    def test_el_comando_que_cita_lista_lo_que_git_diff_no_muestra(self):
        commands = set(re.findall(r"`(git ls-files [^`]+)`", self.text))
        self.assertEqual(commands, {UNTRACKED})
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(pathlib.Path(tmp))
            write(repo / "Viejo.kt", "class Viejo\n")
            write(repo / ".gitignore", "build/\n")
            commit_all(repo)
            write(repo / "Viejo.kt", "class Viejo { val x = 1 }\n")
            write(repo / "feature/Nuevo.kt", "class Nuevo\n")
            write(repo / "build/Generado.kt", "class Generado\n")
            diff = git(repo, "diff", "HEAD", "--name-only").split()
            untracked = run(shlex.split(UNTRACKED), repo).stdout.split()
        self.assertEqual(diff, ["Viejo.kt"])  # la clase nueva no aparece en el diff
        self.assertEqual(untracked, ["feature/Nuevo.kt"])  # y el comando sí la lista, sin lo ignorado


if __name__ == "__main__":
    unittest.main()
