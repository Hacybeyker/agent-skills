"""Tests de la herramienta de hb-coach (skills/hb-coach/scripts/coach.py) en un proyecto temporal."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from helpers import ENV, ROOT, init_repo

SKILL = ROOT / "skills" / "hb-coach"
SCRIPT = SKILL / "scripts" / "coach.py"
FIXTURE_301 = ROOT / "tests" / "fixtures" / "hb-coach-3.0.1" / "aprendizaje"
DAY0 = date(2026, 11, 13)

PLAN_BODY = """## Resumen

- **Meta:** escribir consultas con filtros y uniones.
- **Punto de partida:** nunca escribió SQL.

## Diagnóstico

| Pregunta | Resultado | Decisión |
|---|---|---|
| ¿Qué es una tabla? | Correcta | Empezar en 1.1 |

## Ruta de aprendizaje

### Módulo 1 · Consultas básicas 🟢 Básico

> **Meta del módulo:** leer datos de una tabla.

- [ ] **1.1 Primera** — a
  - Objetivo: elegir columnas.
- [ ] **1.2 Segunda** — b
- [ ] **Examen M1** — 6 a 10 preguntas y una tarea · aprueba con 80 %

### Módulo 2 · Uniones 🟡 Intermedio

- [ ] **2.1 Tercera** — c

### Módulo 3 · Proyecto final 🔴 Experto

- [ ] **3.1 Informe** — d

## Proyecto final

Un informe.

## Recursos

- [SQLite](https://sqlite.org/lang.html) — referencia.

"""

BLOCK = """## 📖 Teoría · 1. Qué devuelve SELECT

`SELECT` elige columnas.

### 🧩 Reto 1 · Dos columnas

Elige `title` y `year`.

**Resultado esperado**

```text
title | year
```

**Tu intento:** `SELECT title, year FROM juegos;` · **Veredicto:** ✔ resuelto sin pistas

**P1.** ¿Qué hace `FROM`? — tu respuesta: *la tabla* ✔

<details>
<summary>Respuesta completa</summary>

Indica la tabla de origen de las filas.

</details>
"""


FIXTURE_31 = ROOT / "tests" / "fixtures" / "hb-coach-3.1.0-a-medias" / "aprendizaje"

# Cabecera y primer bloque de una lección en el modelo «el cuaderno es el aula»: se escriben antes de que
# el estudiante lo intente (sin soluciones) y su intento y la corrección llegan después con `corregir`.
HEADER = """## Objetivos

> **En una frase:** SELECT elige columnas de una tabla.

Al terminar podrás:

- Elegir columnas con SELECT.

**Bloques:**

1. **Qué devuelve SELECT** — 📖 → 🛠 reto → ❓ 2 preguntas
2. **Filtrar con WHERE** — 📖 → 🛠
"""

BLOQUE_1 = """## 📖 Teoría · Qué devuelve SELECT

`SELECT` elige columnas.

## 🛠 Práctica

### 🧩 Reto 1 · Dos columnas

Elige `title` y `year`.

**Resultado esperado**

Dos columnas y todas las filas.

<details>
<summary>Pista 1</summary>

Separa las columnas con comas.

</details>

## ❓ Preguntas · 1. SELECT

**P1.** ¿Qué hace `FROM`?

**P2.** Con esta tabla:

| a | b |
|---|---|
| 1 | 2 |

¿qué devuelve `SELECT b`?
"""

DETALLE = "\n\n<details>\n<summary>Respuesta completa</summary>\n\n%s\n\n</details>\n\n"

# Ejecuta el formato del cuaderno (sin DOM) con Node: una entrada JSON por nota, una salida por entrada.
FORMATO_JS = r"""
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const m = /<script id="coach-formato">([\s\S]*?)<\/script>/.exec(html);
const ctx = {};
vm.createContext(ctx);
vm.runInContext(m[1], ctx);
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = input.map((x) => x.op === "limpiar" ? ctx.CoachFormato.limpiar(x.texto)
  : JSON.parse(JSON.stringify(ctx.CoachFormato.bloques(x.texto))));
process.stdout.write(JSON.stringify(out));
"""


def epoch(day):
    return str(int(datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).timestamp()))


class CoachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = init_repo(Path(self.tmp.name))
        self.space = self.project / "aprendizaje"
        self.plan = self.space / "sql" / "PLAN.md"
        self.day = DAY0

    def tearDown(self):
        self.tmp.cleanup()

    # ---------------------------------------------------------------- utilidades

    def coach(self, *args, stdin=None, cwd=None):
        env = dict(ENV, SOURCE_DATE_EPOCH=epoch(self.day))
        env.pop("COACH_ROOT", None)
        return subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args], cwd=str(cwd or self.project),
                              env=env, input=stdin if stdin is not None else "", capture_output=True, text=True,
                              encoding="utf-8")

    def ok(self, *args, stdin=None, cwd=None):
        result = self.coach(*args, stdin=stdin, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def fails(self, *args, stdin=None):
        result = self.coach(*args, stdin=stdin)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        return result

    def read(self, rel):
        return (self.space / rel).read_text(encoding="utf-8")

    def init_topic(self):
        """Tema 'sql' con método acordado y un plan de tres módulos (el último, de proyecto)."""
        self.ok("init", "sql", "--tema", "SQL desde cero", "--area", "bases-de-datos")
        text = self.plan.read_text(encoding="utf-8")
        start, end = text.index("## Resumen"), text.index("## Huecos abiertos")
        self.plan.write_text(text[:start] + PLAN_BODY + text[end:], encoding="utf-8")
        self.ok("metodo", "--preguntas", "Sin predicción", "--practica", "problemas", "--ritmo", "3 x 45 min",
                "--profundidad", "normal", "--calentamiento", "sí", "--idioma", "español")

    def lesson_with_note(self, lid="1.1"):
        self.ok("leccion", "sql", lid)
        self.ok("nota", "sql", lid, stdin=BLOCK)
        self.ok("nota", "sql", lid, "--seccion", "objetivos", stdin="> **En una frase:** columnas.\n\n- Elegir columnas.")
        self.ok("nota", "sql", lid, "--seccion", "resumen", stdin="«SELECT elige columnas.»")
        self.ok("nota", "sql", lid, "--seccion", "fuentes", stdin="- [SELECT](https://sqlite.org/lang_select.html)")

    def note_path(self, lid):
        return next((self.space / "sql" / "lecciones").glob(lid + "-*.md"))

    def estado(self):
        return json.loads(self.ok("estado", "sql", "--json").stdout)["temas"][0]

    def lesson_line(self, lid):
        return next(l for l in self.plan.read_text(encoding="utf-8").splitlines() if "**%s " % lid in l)

    def siguiente(self):
        return json.loads(self.ok("siguiente", "sql", "--json").stdout)

    # ---------------------------------------------------------------- básicos

    def test_la_version_coincide_con_la_de_la_skill(self):
        version = re.search(r'^\s+version:\s*"([^"]+)"', (SKILL / "SKILL.md").read_text(encoding="utf-8"), re.M).group(1)
        self.assertEqual(self.ok("version").stdout.strip(), "hb-coach %s" % version)

    def test_init_crea_el_espacio_y_lo_excluye_de_git(self):
        self.ok("init", "sql", "--tema", "SQL", "--playground", "https://sqlite.org/fiddle/")
        for name in ("sql/PLAN.md", "sql/GLOSARIO.md", "sql/DUDAS.md", "sql/lecciones", "METODO.md", "README.md"):
            self.assertTrue((self.space / name).exists(), name)
        self.assertIn("/aprendizaje/", (self.project / ".git/info/exclude").read_text(encoding="utf-8"))
        plan = self.plan.read_text(encoding="utf-8")
        self.assertIn("formato: 2", plan)
        self.assertIn("playground: \"https://sqlite.org/fiddle/\"", plan)
        self.assertIn("**Examen M1**", plan)

    def test_init_con_root_fuera_del_proyecto_no_toca_git(self):
        outside = Path(self.tmp.name) / "fuera"
        outside.mkdir()
        lugar = Path(tempfile.mkdtemp())
        try:
            self.ok("init", "ingles", "--tema", "Inglés", "--root", lugar / "aprendizaje", "--mapa", cwd=outside)
            self.assertTrue((lugar / "aprendizaje" / "ingles" / "MAPA.md").is_file())
            self.assertNotIn("aprendizaje", (self.project / ".git/info/exclude").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(str(lugar))

    def test_un_comando_desconocido_termina_con_codigo_2(self):
        result = self.coach("nada")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Comando desconocido", result.stderr)

    # ---------------------------------------------------------------- método y siguiente

    def test_metodo_guarda_los_acuerdos_y_su_cambio(self):
        self.ok("init", "sql", "--tema", "SQL")
        self.ok("metodo", "--ritmo", "2 x 30 min", "--motivo", "Primera sesión")
        metodo = self.read("METODO.md")
        self.assertIn("| Ritmo | 2 x 30 min |", metodo)
        self.assertRegex(metodo, r"\| 2026-11-13 \| Acuerdo inicial: Ritmo: 2 x 30 min \| Primera sesión \|")
        self.assertIn("ritmo", self.ok("metodo").stdout)
        self.assertIn("Clave(s) de método desconocida(s): color", self.fails("metodo", "--color", "azul").stderr)

    def test_siguiente_sigue_el_orden_metodo_plan_leccion(self):
        self.ok("init", "sql", "--tema", "SQL")
        self.assertEqual(self.siguiente()["tipo"], "metodo")
        self.ok("metodo", "--preguntas", "x", "--practica", "x", "--ritmo", "x", "--profundidad", "x",
                "--calentamiento", "x", "--idioma", "x")
        self.assertEqual(self.siguiente()["tipo"], "plan")
        text = self.plan.read_text(encoding="utf-8")
        start, end = text.index("## Resumen"), text.index("## Huecos abiertos")
        self.plan.write_text(text[:start] + PLAN_BODY + text[end:], encoding="utf-8")
        step = self.siguiente()
        self.assertEqual((step["tipo"], step["leccion"]), ("leccion", "1.1"))
        self.assertTrue(any(" bloque sql 1.1 1" in c and c.endswith("<<'EOF'") for c in step["comandos"]))

    def test_siguiente_propone_repaso_y_examen_cuando_tocan(self):
        self.init_topic()
        self.lesson_with_note("1.1")
        self.ok("completar", "sql", "1.1")
        self.ok("completar", "sql", "1.2", "--forzar")
        self.assertEqual(self.siguiente()["tipo"], "examen")
        self.day = DAY0 + timedelta(days=3)
        step = self.siguiente()
        self.assertEqual(step["tipo"], "repaso")
        self.assertTrue(any("Examen M1" in m for m in step["meta"]))

    def test_siguiente_imprime_root_si_no_es_el_de_por_defecto(self):
        lugar = Path(tempfile.mkdtemp())
        try:
            self.ok("init", "sql", "--tema", "SQL", "--root", lugar)
            out = self.ok("siguiente", "--root", lugar).stdout
            self.assertIn("--root %s" % lugar.resolve(), out)
        finally:
            shutil.rmtree(str(lugar))

    # ---------------------------------------------------------------- lecciones y notas

    def test_leccion_se_niega_con_el_plan_sin_terminar(self):
        self.ok("init", "sql", "--tema", "SQL")
        self.assertIn("título de la plantilla", self.fails("leccion", "sql", "1.1").stderr)
        self.assertFalse(list((self.space / "sql" / "lecciones").iterdir()))

    def test_leccion_crea_la_nota_y_la_marca_como_actual(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.2")
        self.assertTrue(self.note_path("1.2").is_file())
        self.assertEqual(self.estado()["actual"]["id"], "1.2")

    def test_nota_inserta_el_bloque_antes_del_cierre(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        out = self.ok("nota", "sql", "1.1", stdin=BLOCK).stdout
        self.assertIn("bloque añadido (📖 Teoría · 1. Qué devuelve SELECT)", out)
        text = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertLess(text.index("## 📖 Teoría"), text.index("## Resumen con tus palabras"))
        self.assertLess(text.index("## Objetivos"), text.index("## 📖 Teoría"))

    def test_nota_desde_archivo_reemplaza_seccion_y_anade_historial(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        src = Path(self.tmp.name) / "fuentes.md"
        src.write_text("- [SQLite](https://sqlite.org)\n", encoding="utf-8")
        self.ok("nota", "sql", "1.1", "--seccion", "fuentes", "--desde", src, "--historial", "Atasco en la pista 2")
        text = self.note_path("1.1").read_text(encoding="utf-8")
        fuentes = text[text.index("## Fuentes"):text.index("## Historial")]
        self.assertIn("sqlite.org", fuentes)
        self.assertNotIn("COMPLETAR", fuentes)
        self.assertIn("| 2026-11-13 | Atasco en la pista 2 |", text)

    def test_nota_avisa_al_momento_de_codigo_y_etiquetas_largas(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        block = "```mermaid\nflowchart LR\n  a[\"una etiqueta muchísimo más larga de la cuenta\"] --> b\n```\n"
        out = self.ok("nota", "sql", "1.1", stdin=block).stdout
        self.assertIn("etiqueta(s) de Mermaid de más de 24 caracteres", out)

    def test_nota_sin_contenido_termina_con_codigo_2(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        self.assertIn("Falta el contenido", self.fails("nota", "sql", "1.1").stderr)

    def test_completar_se_niega_con_la_nota_a_medias(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        self.assertIn("no está lista", self.fails("completar", "sql", "1.1").stderr)
        self.assertTrue(self.lesson_line("1.1").startswith("- [ ]"))
        self.ok("completar", "sql", "1.1", "--forzar")
        self.assertTrue(self.lesson_line("1.1").startswith("- [x]"))

    def test_completar_marca_avanza_y_programa_el_primer_repaso(self):
        self.init_topic()
        self.lesson_with_note("1.1")
        out = self.ok("completar", "sql", "1.1").stdout
        self.assertIn("Primer repaso: 2026-11-16", out)
        estado = self.estado()
        self.assertEqual((estado["hechas"], estado["total"], estado["actual"]["id"]), (1, 4, "1.2"))
        note = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertIn("repaso: 2026-11-16", note)
        self.assertIn("repasos: 0", note)

    def test_completar_el_modulo_avisa_del_examen(self):
        self.init_topic()
        self.ok("completar", "sql", "1.1", "--convalidada")
        out = self.ok("completar", "sql", "1.2", "--forzar").stdout
        self.assertIn("Toca el examen del módulo: coach examen sql 1", out)

    def test_convalidar_y_reabrir(self):
        self.init_topic()
        self.ok("completar", "sql", "1.2", "--convalidada")
        self.assertIn("(convalidada)", self.lesson_line("1.2"))
        self.ok("reabrir", "sql", "1.2")
        line = self.lesson_line("1.2")
        self.assertTrue(line.startswith("- [ ]"))
        self.assertNotIn("convalidada", line)
        self.assertEqual(self.estado()["actual"]["id"], "1.2")

    def test_una_leccion_inexistente_termina_con_codigo_2(self):
        self.init_topic()
        self.assertIn("La lección 9.9 no existe", self.fails("completar", "sql", "9.9").stderr)

    def test_nota_reemplaza_varias_secciones_en_una_llamada(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        out = self.ok("nota", "sql", "1.1", stdin="## Objetivos\n\n- Elegir columnas.\n\n" + BLOCK).stdout
        self.assertIn("sección «Objetivos» reemplazada", out)
        self.ok("nota", "sql", "1.1", stdin="## Resumen con tus palabras\n\n«Columnas.»\n\n## Fuentes\n\n- [SQLite](https://sqlite.org)")
        text = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertEqual(text.count("## Objetivos"), 1)
        self.assertEqual(text.count("## Fuentes"), 1)
        self.assertNotIn("COMPLETAR", text)
        self.assertLess(text.index("## Objetivos"), text.index("## 📖 Teoría"))
        self.assertLess(text.index("## 📖 Teoría"), text.index("## Resumen con tus palabras"))
        self.ok("completar", "sql", "1.1")

    def test_completar_no_marca_en_curso_la_siguiente(self):
        self.init_topic()
        self.ok("completar", "sql", "1.1", "--convalidada")
        estado = self.estado()
        self.assertEqual(estado["actual"]["id"], "1.2")
        self.assertEqual(estado["actual"]["estado"], "pendiente")

    def test_metodo_sin_claves_no_escribe_nada(self):
        out = self.ok("metodo").stdout
        self.assertIn("se crea al guardar la primera clave", out)
        self.assertFalse(self.space.exists())
        self.assertNotIn("aprendizaje", (self.project / ".git/info/exclude").read_text(encoding="utf-8"))

    def test_metodo_prediccion_no_borra_la_regla_de_las_preguntas(self):
        self.ok("metodo", "--prediccion", "sí")
        metodo = self.read("METODO.md")
        self.assertIn("| Preguntas | Solo sobre lo ya explicado o practicado |", metodo)
        self.assertIn("| Predicción | sí |", metodo)

    def test_metodo_antes_de_init_crea_la_carpeta(self):
        self.ok("metodo", "--ritmo", "2 x 45 min")
        self.assertIn("| Ritmo | 2 x 45 min |", self.read("METODO.md"))
        self.assertIn("/aprendizaje/", (self.project / ".git/info/exclude").read_text(encoding="utf-8"))
        self.ok("init", "sql", "--tema", "SQL")
        self.assertIn("| Ritmo | 2 x 45 min |", self.read("METODO.md"))

    def test_el_ultimo_modulo_experto_no_necesita_examen(self):
        self.init_topic()
        text = self.plan.read_text(encoding="utf-8").replace("Módulo 3 · Proyecto final", "Módulo 3 · Simulacros")
        self.plan.write_text(text, encoding="utf-8")
        self.assertEqual(self.estado()["modulos"][-1]["proyecto"], True)
        self.assertNotIn("sin línea de examen: 2, 3", self.ok("check", "sql").stdout)

    # ---------------------------------------------------------------- bloques: el cuaderno es el aula

    def test_la_plantilla_de_leccion_no_trae_marcadores_ni_comentarios(self):
        self.init_topic()
        out = self.ok("leccion", "sql", "1.1").stdout
        self.assertIn(" bloque sql 1.1 1", out)
        text = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertNotIn("[[", text)
        self.assertNotIn("<!--", text)
        self.assertIn("- a\n", text)
        err = self.fails("completar", "sql", "1.1").stderr
        self.assertIn("«Resumen con tus palabras» y «Fuentes» sin contenido", err)

    def test_bloque_crea_la_nota_con_la_cabecera_y_numera_el_bloque(self):
        self.init_topic()
        out = self.ok("bloque", "sql", "1.1", stdin=HEADER + "\n" + BLOQUE_1).stdout
        self.assertIn("bloque 1 de 2 en el cuaderno", out)
        self.assertIn("cuaderno.html#/t/sql/l/1.1/b1", out)
        self.assertIn("Espera: el intento del reto 1.", out)
        text = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertIn("## 📖 Teoría · 1. Qué devuelve SELECT", text)
        self.assertIn("## 🛠 Práctica · 1. Qué devuelve SELECT", text)
        self.assertEqual(text.count("## Objetivos"), 1)
        self.assertNotIn("Al terminar podrás:\n\n- a\n", text)
        self.assertLess(text.index("## Objetivos"), text.index("## 📖 Teoría"))
        self.assertLess(text.index("## ❓ Preguntas · 1."), text.index("## Resumen con tus palabras"))
        step = self.siguiente()
        self.assertEqual((step["bloque"]["n"], step["bloque"]["total"]), (1, 2))
        self.assertEqual(step["bloque"]["espera"], "el intento del reto 1")
        self.assertTrue(step["bloque"]["enlace"].endswith("cuaderno.html#/t/sql/l/1.1/b1"))
        self.assertTrue(any(" corregir sql 1.1" in c for c in step["comandos"]))
        self.assertEqual(self.estado()["actual"]["bloque"]["espera"], "el intento del reto 1")

    def test_bloque_no_escribe_soluciones_ni_se_salta_lo_pendiente(self):
        self.init_topic()
        sol = BLOQUE_1 + "\n<details>\n<summary>Solución</summary>\n\nSELECT title, year;\n\n</details>\n"
        self.assertIn("Solución", self.fails("bloque", "sql", "1.1", stdin=sol).stderr)
        self.assertFalse(list((self.space / "sql" / "lecciones").glob("1.1-*")))
        self.assertIn("coach corregir", self.fails("bloque", "sql", "1.1", stdin=BLOQUE_1 + "\n**Tu intento:** x").stderr)
        self.ok("bloque", "sql", "1.1", stdin=HEADER + BLOQUE_1)
        self.assertIn("ya está escrito", self.fails("bloque", "sql", "1.1", "1", stdin=BLOQUE_1).stderr)
        bloque_2 = "## 📖 Teoría · 2. WHERE\n\nFiltra filas.\n"
        self.assertIn("aún espera el intento del reto 1", self.fails("bloque", "sql", "1.1", stdin=bloque_2).stderr)
        self.assertIn("estás escribiendo el bloque 3", self.fails("bloque", "sql", "1.1", "3", "--forzar",
                                                                 stdin=bloque_2).stderr)
        self.ok("bloque", "sql", "1.1", "--forzar", stdin=bloque_2)
        self.assertIn("## 📖 Teoría · 2. WHERE", self.note_path("1.1").read_text(encoding="utf-8"))

    def test_corregir_un_reto_con_segundo_intento_y_la_solucion_al_cerrarlo(self):
        self.init_topic()
        self.ok("bloque", "sql", "1.1", stdin=HEADER + BLOQUE_1)
        solucion = "<details>\n<summary>Solución</summary>\n\n`SELECT title, year FROM juegos;`\n\n</details>"
        self.assertIn("después del intento", self.fails("corregir", "sql", "1.1", stdin=solucion).stderr)
        out = self.ok("corregir", "sql", "1.1",
                      stdin="**Tu intento:** `SELECT title year`\n\n**Veredicto:** ✘ falta la coma.").stdout
        self.assertIn("reto 1 intento registrado; queda el segundo intento", out)
        text = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertNotIn("<summary>Solución", text)
        self.assertLess(text.index("<summary>Pista 1"), text.index("**Tu intento:**"))
        self.assertLess(text.index("**Tu intento:**"), text.index("## ❓ Preguntas"))
        self.assertEqual(self.siguiente()["bloque"]["espera"], "el segundo intento del reto 1 (la solución, al cerrarlo)")
        out = self.ok("corregir", "sql", "1.1", stdin="**Segundo intento:** `SELECT title, year` · **Veredicto:** ✔ "
                                                       "con la pista 1\n\n" + solucion).stdout
        self.assertIn("reto 1 cerrado", out)
        self.assertIn("espera las respuestas a P1–P2", out)

    def test_corregir_cada_pregunta_en_su_sitio_y_pasar_al_bloque_siguiente(self):
        self.init_topic()
        self.ok("bloque", "sql", "1.1", stdin=HEADER + BLOQUE_1)
        self.ok("corregir", "sql", "1.1", stdin="**Tu intento:** ok · **Veredicto:** ✔")
        self.assertIn("No encuentro la pregunta P9", self.fails("corregir", "sql", "1.1",
                                                                stdin="**P9.** tu respuesta: x ✔").stderr)
        out = self.ok("corregir", "sql", "1.1", stdin="**P1.** tu respuesta: *«la tabla»* ✔" + DETALLE % "El origen."
                      + "**P2.** *«a»* ✘ Pista: mira la columna.").stdout
        self.assertIn("P1 corregida · P2 espera el segundo intento", out)
        text = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertIn("**P1.** ¿Qué hace `FROM`? — tu respuesta: *«la tabla»* ✔\n\n<details>", text)
        self.assertIn("**Tu respuesta:** *«a»* ✘ Pista: mira la columna.", text)
        self.assertLess(text.index("| 1 | 2 |"), text.index("**Tu respuesta:**"))
        self.assertEqual(text.count("**P2.**"), 1)
        out = self.ok("corregir", "sql", "1.1", stdin="**P2.** *«2»* ✔" + DETALLE % "La columna b.").stdout
        self.assertIn("**Segundo intento:** *«2»* ✔", self.note_path("1.1").read_text(encoding="utf-8"))
        self.assertIn("bloque 1 terminado: escribe el bloque 2 de 2 (Filtrar con WHERE)", out)
        self.assertTrue(any(" bloque sql 1.1 2" in c for c in self.siguiente()["comandos"]))
        self.ok("bloque", "sql", "1.1", stdin="## 📖 Teoría · WHERE\n\nFiltra filas.\n")
        self.assertIn("## 📖 Teoría · 2. WHERE", self.note_path("1.1").read_text(encoding="utf-8"))
        self.assertIn("bloques terminados", self.siguiente()["texto"])

    def test_completar_exige_el_cierre_con_contenido_y_nada_pendiente(self):
        self.init_topic()
        self.ok("bloque", "sql", "1.1", stdin=HEADER + BLOQUE_1)
        self.ok("nota", "sql", "1.1", stdin="## Resumen con tus palabras\n\n«Columnas.»\n\n## Fuentes\n\n"
                                              "- [SQLite](https://sqlite.org)")
        self.assertIn("el bloque 1 aún espera el intento del reto 1", self.fails("completar", "sql", "1.1").stderr)
        self.ok("corregir", "sql", "1.1", stdin="**Tu intento:** ok · **Veredicto:** ✔\n\n**P1.** tu respuesta: *a* ✔"
                                                  "\n\n**P2.** tu respuesta: *2* ✔")
        self.ok("completar", "sql", "1.1")

    def test_nota_no_escribe_una_solucion_sin_el_intento(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        reto = ("## 🛠 Práctica · 1. X\n\n### 🧩 Reto 1 · X\n\n**Resultado esperado**\n\nAlgo.\n\n"
                "<details>\n<summary>Solución</summary>\n\nY\n\n</details>")
        self.assertIn("sin el intento", self.fails("nota", "sql", "1.1", stdin=reto).stderr)
        self.ok("nota", "sql", "1.1", "--forzar", stdin=reto)
        self.assertIn("el reto 1 tiene la solución pero no el intento", self.ok("check", "sql").stdout)

    def test_el_repaso_se_hace_en_su_nota_del_dia(self):
        self.init_topic()
        self.lesson_with_note("1.1")
        self.ok("completar", "sql", "1.1")
        self.ok("hueco", "sql", "Confunde FROM con WHERE")
        self.assertIn("Aún no hay nota de repaso", self.fails("nota", "sql", "repaso", stdin="**P1.** x").stderr)
        self.day = DAY0 + timedelta(days=3)
        out = self.ok("repaso", "sql").stdout
        self.assertIn("repasos/2026-11-16.md", out)
        self.assertIn("cuaderno.html#/t/sql/repaso", out)
        nota = self.read("sql/repasos/2026-11-16.md")
        self.assertIn("- **1.1** Primera (lección)", nota)
        self.assertIn("- **H1** Confunde FROM con WHERE (hueco)", nota)
        self.ok("nota", "sql", "repaso", stdin="**P1.** (1.1) ¿Qué elige SELECT?\n\n**P2.** (H1) ¿Qué filtra WHERE?")
        self.assertIn("Respuesta completa", self.fails("nota", "sql", "repaso",
                                                       stdin="**P3.** x" + DETALLE % "y").stderr)
        out = self.ok("corregir", "sql", "repaso", stdin="**P1.** tu respuesta: *columnas* ✔\n\n"
                                                          "**P2.** tu respuesta: *columnas* ✘").stdout
        self.assertIn("Quedan por corregir: P2", out)
        self.assertIn("solo hay preguntas", self.fails("corregir", "sql", "repaso", stdin="algo").stderr)
        self.ok("repaso", "sql", "1.1", "--bien")
        self.ok("repaso", "sql", "H1", "--mal")
        nota = self.read("sql/repasos/2026-11-16.md")
        self.assertIn("**P2.** (H1) ¿Qué filtra WHERE? — tu respuesta: *columnas* ✘", nota)
        self.assertIn("| 2026-11-16 | Lección 1.1: bien |", nota)
        self.assertIn("| 2026-11-16 | Hueco H1: a reforzar |", nota)

    def test_el_examen_se_corrige_en_su_nota(self):
        self.init_topic()
        self.ok("examen", "sql", "1")
        exam = next((self.space / "sql" / "examenes").glob("m1-*.md"))
        self.assertNotIn("<!--", exam.read_text(encoding="utf-8"))
        self.assertNotIn("coach nota", exam.read_text(encoding="utf-8"))
        self.ok("nota", "sql", "M1", stdin="**P1.** ¿Qué hace WHERE?\n\n**P2.** ¿Y ORDER BY?")
        self.ok("nota", "sql", "M1", "--seccion", "tarea", stdin="Escribe una consulta con WHERE.")
        out = self.ok("corregir", "sql", "M1", stdin="**Tu intento:** `SELECT * FROM t WHERE a > 1;` · **Veredicto:** ✔"
                                                      "\n\n**P1.** tu respuesta: *filtra* ✔\n\n"
                                                      "**P2.** tu respuesta: *ordena* ✔").stdout
        self.assertIn("Todo corregido", out)
        self.assertIn(" examen sql 1 --resultado", out)
        text = exam.read_text(encoding="utf-8")
        self.assertIn("**Tu intento:**", text[text.index("## Tarea práctica"):text.index("## Resultado")])
        self.assertIn("**P1.** ¿Qué hace WHERE? — tu respuesta: *filtra* ✔", text)

    def test_build_escribe_el_latido_del_cuaderno(self):
        self.init_topic()
        self.ok("build")
        latido = (self.space / ".cuaderno-version.js").read_text(encoding="utf-8")
        huella = re.search(r'coachLatido\("([0-9a-f]{8})"\)', latido).group(1)
        self.assertIn('"huella":"%s"' % huella, (self.space / "cuaderno.html").read_text(encoding="utf-8"))
        self.ok("build")
        self.assertEqual((self.space / ".cuaderno-version.js").read_text(encoding="utf-8"), latido)
        self.ok("glosario", "sql", "Tabla", "Conjunto de filas.")
        self.assertNotEqual((self.space / ".cuaderno-version.js").read_text(encoding="utf-8"), latido)

    # ---------------------------------------------------------------- glosario y dudas

    def test_glosario_inserta_en_orden_y_actualiza(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        self.ok("glosario", "sql", "Tabla", "Conjunto de filas.", "Columna", "Atributo.")
        self.ok("glosario", "sql", "Índice", "Estructura que acelera búsquedas.", "--leccion", "1.2")
        self.ok("glosario", "sql", "Tabla", "Conjunto de filas con las mismas columnas.")
        rows = [l for l in self.read("sql/GLOSARIO.md").splitlines() if l.startswith("| **")]
        self.assertEqual([re.search(r"\*\*(.+?)\*\*", r).group(1) for r in rows], ["Columna", "Índice", "Tabla"])
        self.assertIn("mismas columnas", rows[2])
        self.assertIn("[1.1](lecciones/1.1-primera.md)", rows[0])
        self.assertTrue(rows[1].endswith("| 1.2 |"))

    def test_duda_va_arriba_debajo_del_comentario(self):
        self.init_topic()
        self.ok("duda", "sql", "¿Primera?", "--respuesta", "Sí.")
        self.ok("duda", "sql", "¿Segunda?", "--respuesta", "No.", "--contexto", "Reto 1", "--fuente",
                "[SQLite](https://sqlite.org)")
        text = self.read("sql/DUDAS.md")
        self.assertNotIn("Aún no hay dudas", text)
        self.assertLess(text.index("-->"), text.index("¿Segunda?"))
        self.assertLess(text.index("¿Segunda?"), text.index("¿Primera?"))
        self.assertIn("- **Fuente:** [SQLite](https://sqlite.org)", text)
        self.assertEqual(self.estado()["slug"], "sql")

    # ---------------------------------------------------------------- huecos y repasos

    def test_hueco_abre_repasa_y_cierra_con_su_calendario(self):
        self.init_topic()
        self.ok("hueco", "sql", "Confunde FROM con WHERE", "--leccion", "1.1")
        gap = self.estado()["huecos"][0]
        self.assertEqual((gap["id"], gap["proximo_repaso"], gap["estado"], gap["intentos"]),
                         ("H1", "2026-11-14", "abierto", "2"))
        self.day = DAY0 + timedelta(days=1)
        self.ok("hueco", "sql", "H1", "--bien")
        gap = self.estado()["huecos"][0]
        self.assertEqual((gap["proximo_repaso"], gap["racha"]), ("2026-11-17", 1))
        self.ok("hueco", "sql", "H1", "--mal")
        gap = self.estado()["huecos"][0]
        self.assertEqual((gap["proximo_repaso"], gap["racha"], gap["intentos"]), ("2026-11-15", 0, "3"))
        self.ok("hueco", "sql", "H1", "--cerrar")
        self.assertEqual(self.estado()["huecos_abiertos"], [])
        self.assertIn("Indica uno", self.fails("hueco", "sql", "H1", "--bien", "--mal").stderr)

    def test_hueco_crea_la_seccion_si_falta(self):
        self.init_topic()
        text = self.plan.read_text(encoding="utf-8")
        start, end = text.index("## Huecos abiertos"), text.index("## Bitácora")
        self.plan.write_text(text[:start] + text[end:], encoding="utf-8")
        self.ok("hueco", "sql", "Algo")
        text = self.plan.read_text(encoding="utf-8")
        self.assertLess(text.index("## Huecos abiertos"), text.index("## Bitácora"))

    def test_repaso_lista_lo_vencido_mezclado_y_reprograma(self):
        self.init_topic()
        self.lesson_with_note("1.1")
        self.ok("completar", "sql", "1.1")
        self.ok("hueco", "sql", "Confunde FROM con WHERE")
        self.assertIn("Nada vence hoy", self.ok("repaso", "sql").stdout)
        self.day = DAY0 + timedelta(days=3)
        data = json.loads(self.ok("repaso", "sql", "--json").stdout)
        self.assertEqual(sorted(e["id"] for e in data["elementos"]), ["1.1", "H1"])
        leccion = next(e for e in data["elementos"] if e["id"] == "1.1")
        self.assertEqual(leccion["preguntas"][0]["pregunta"], "¿Qué hace `FROM`?")
        self.assertIn("tabla de origen", leccion["preguntas"][0]["respuesta"])
        again = json.loads(self.ok("repaso", "sql", "--json").stdout)
        self.assertEqual([e["id"] for e in data["elementos"]], [e["id"] for e in again["elementos"]])
        self.ok("repaso", "sql", "1.1", "--bien")
        note = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertIn("repaso: 2026-11-23", note)
        self.assertIn("repasos: 1", note)
        self.ok("repaso", "sql", "1.1", "--mal")
        note = self.note_path("1.1").read_text(encoding="utf-8")
        self.assertIn("repaso: 2026-11-17", note)
        self.assertIn("Repaso espaciado: a reforzar", note)

    def test_una_leccion_se_consolida_tras_todos_sus_repasos(self):
        self.init_topic()
        self.lesson_with_note("1.1")
        self.ok("completar", "sql", "1.1")
        for _ in range(5):
            out = self.ok("repaso", "sql", "1.1", "--bien").stdout
        self.assertIn("consolidada", out)
        self.assertEqual(self.estado()["repasos"], {"vencidos": [], "proximo": None})

    # ---------------------------------------------------------------- exámenes y sesión

    def test_examen_prepara_la_nota_y_registra_el_resultado(self):
        self.init_topic()
        out = self.ok("examen", "sql", "1").stdout
        self.assertIn("cubre 1.1, 1.2", out)
        exam = next((self.space / "sql" / "examenes").glob("m1-*.md"))
        self.assertIn("- 1.1 Primera", exam.read_text(encoding="utf-8"))
        self.ok("nota", "sql", "M1", stdin="**P1.** ¿Qué hace WHERE? — tu respuesta: *filtra* ✔")
        self.ok("examen", "sql", "M1", "--resultado", "4/6", "--tarea", "si")
        self.assertRegex(self.lesson_line_exam(), r"^- \[ \] \*\*Examen M1\*\* — 4/6 \(66 %\) · tarea hecha el 2026-11-13 · repetir$")
        self.ok("examen", "sql", "1", "--resultado", "5/6", "--tarea", "si")
        self.assertRegex(self.lesson_line_exam(), r"^- \[x\] \*\*Examen M1\*\* — 5/6 \(83 %\) · tarea hecha · aprobado")
        exam_text = exam.read_text(encoding="utf-8")
        self.assertIn("estado: aprobado", exam_text)
        self.assertLess(exam_text.index("## Preguntas"), exam_text.index("**P1.**"))
        self.assertLess(exam_text.index("**P1.**"), exam_text.index("## Tarea práctica"))
        resultado = exam_text[exam_text.index("## Resultado"):exam_text.index("## Historial")]
        self.assertIn("**5/6 (83 %)** · tarea hecha · aprobado el 2026-11-13.", resultado)
        self.assertNotIn("Pendiente", resultado)
        self.assertTrue(self.estado()["examenes"][0]["hecho"])
        self.assertIn("aciertos/total", self.fails("examen", "sql", "1", "--resultado", "7/6", "--tarea", "si").stderr)

    def lesson_line_exam(self):
        return next(l for l in self.plan.read_text(encoding="utf-8").splitlines() if "**Examen M1**" in l)

    def test_examen_de_un_modulo_sin_linea_la_anade(self):
        self.init_topic()
        self.ok("examen", "sql", "2")
        lines = self.plan.read_text(encoding="utf-8").splitlines()
        i = next(i for i, l in enumerate(lines) if "**2.1 " in l)
        self.assertTrue(lines[i + 1].startswith("- [ ] **Examen M2**"))

    def test_el_examen_exige_la_tarea_y_se_repite_tras_repasar_sus_huecos(self):
        self.init_topic()
        self.ok("completar", "sql", "1.1", "--convalidada")
        self.ok("completar", "sql", "1.2", "--convalidada")
        self.assertIn("--tarea si", self.fails("examen", "sql", "1", "--resultado", "5/6").stderr)
        self.ok("examen", "sql", "1", "--resultado", "3/6", "--tarea", "si")
        self.ok("hueco", "sql", "Filtros con OR", "--examen", "1")
        gap = self.estado()["huecos"][0]
        self.assertEqual((gap["detectado"], gap["intentos"]), ("Examen M1 (2026-11-13)", "1"))
        self.assertNotEqual(self.siguiente()["tipo"], "examen")
        self.day = DAY0 + timedelta(days=1)
        self.ok("hueco", "sql", "H1", "--bien")
        self.assertEqual(self.siguiente()["tipo"], "examen")

    def test_el_repaso_tiene_un_limite_diario(self):
        self.init_topic()
        for i in range(8):
            self.ok("hueco", "sql", "Hueco %d" % i)
        self.day = DAY0 + timedelta(days=1)
        self.assertEqual(len(json.loads(self.ok("repaso", "sql", "--json").stdout)["elementos"]), 6)
        for i in range(1, 7):
            self.ok("hueco", "sql", "H%d" % i, "--bien")
        self.assertIn("Ya hiciste 6 repasos hoy", self.ok("repaso", "sql").stdout)
        self.assertEqual(self.siguiente()["tipo"], "leccion")

    def test_repaso_de_una_leccion_sin_completar_termina_con_codigo_2(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        self.assertIn("no está completada", self.fails("repaso", "sql", "1.1", "--bien").stderr)

    def test_siguiente_avisa_de_un_espacio_en_el_home(self):
        home = Path(self.tmp.name) / "home"
        (home / "aprendizaje" / "ingles").mkdir(parents=True)
        (home / "aprendizaje" / "ingles" / "PLAN.md").write_text("---\ntema: Inglés\n---\n", encoding="utf-8")
        env = dict(ENV, SOURCE_DATE_EPOCH=epoch(self.day), HOME=str(home))
        result = subprocess.run([sys.executable, str(SCRIPT), "siguiente"], cwd=str(self.project), env=env,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertIn("tiene: ingles", result.stdout)
        self.assertFalse(self.space.exists())

    def test_build_y_check_ignoran_el_material_de_practica(self):
        self.init_topic()
        junk = self.space / "sql" / "practica" / "node_modules" / "x"
        junk.mkdir(parents=True)
        (junk / "README.md").write_text("[roto](no.md)\n```\nsin cerrar\n", encoding="utf-8")
        self.ok("build")
        self.assertNotIn("practica/", (self.space / "cuaderno.html").read_text(encoding="utf-8"))
        self.assertNotIn("practica", self.ok("check", "sql").stdout)

    def test_check_entiende_vallas_anidadas(self):
        self.init_topic()
        with open(str(self.space / "sql/GLOSARIO.md"), "a", encoding="utf-8") as f:
            f.write("\n````markdown\n```sql\nSELECT 1;\n```\n````\n")
        self.assertNotIn("sin cerrar", self.ok("check", "sql").stdout)

    def test_doble_guion_termina_las_opciones(self):
        self.init_topic()
        self.ok("glosario", "sql", "--", "--force", "Opción que fuerza la operación.")
        self.assertIn("| **--force** |", self.read("sql/GLOSARIO.md"))

    def test_un_examen_suspendido_por_la_tarea_no_aprueba(self):
        self.init_topic()
        self.ok("examen", "sql", "1", "--resultado", "6/6", "--tarea", "no")
        self.assertTrue(self.lesson_line_exam().startswith("- [ ]"))

    def test_sesion_anade_la_bitacora_y_devuelve_el_siguiente_paso(self):
        self.init_topic()
        out = self.ok("sesion", "sql", "--logros", "Primeras consultas", "--lecciones", "1.1").stdout
        self.assertIn("check: sin errores", out)
        self.assertIn("Siguiente paso: Empezar la lección 1.1", out)
        last = [l for l in self.plan.read_text(encoding="utf-8").splitlines() if l.startswith("| 2026-")][-1]
        self.assertEqual(last, "| 2026-11-13 | 1.1 | Primeras consultas | Empezar la lección 1.1 · Primera. |")
        self.assertEqual(self.estado()["sesiones"], 1)

    # ---------------------------------------------------------------- estado, build y check

    def test_estado_json_resume_examenes_huecos_y_repasos(self):
        self.init_topic()
        estado = self.estado()
        self.assertEqual([e["modulo"] for e in estado["examenes"]], ["1"])
        self.assertEqual([m["proyecto"] for m in estado["modulos"]], [False, False, True])
        self.assertEqual(estado["formato"], 2)
        self.assertFalse(estado["pendiente"]["plan"])

    def test_build_genera_el_cuaderno(self):
        self.init_topic()
        self.ok("build")
        html = (self.space / "cuaderno.html").read_text(encoding="utf-8")
        self.assertIn("SQL desde cero", html)
        self.assertNotIn("\"__COACH_DATA__\"", html)

    def test_check_avisa_los_enlaces_rotos_sin_fallar(self):
        self.init_topic()
        with open(str(self.space / "sql/GLOSARIO.md"), "a", encoding="utf-8") as f:
            f.write("\n[roto](no-existe.md)\n")
        self.assertIn("enlace roto a no-existe.md", self.ok("check", "sql").stdout)

    def test_check_avisa_de_retos_sin_resultado_ni_intento(self):
        self.init_topic()
        self.ok("leccion", "sql", "1.1")
        self.ok("nota", "sql", "1.1", stdin="### 🧩 Reto 1 · Sin nada\n\nHaz algo.")
        self.ok("completar", "sql", "1.1", "--forzar")
        out = self.ok("check", "sql").stdout
        self.assertIn("no tiene **Resultado esperado**", out)
        self.assertIn("no registra el intento", out)

    def test_check_avisa_de_modulos_sin_examen(self):
        self.init_topic()
        self.assertIn("módulo(s) sin línea de examen: 2", self.ok("check", "sql").stdout)

    # ---------------------------------------------------------------- compatibilidad 3.0.1

    def copy_fixture(self):
        shutil.copytree(str(FIXTURE_301), str(self.space))

    def snapshot(self):
        return {p.relative_to(self.space).as_posix(): p.read_text(encoding="utf-8")
                for p in self.space.rglob("*.md") if ".respaldos" not in p.parts}

    def test_un_espacio_301_funciona_sin_migrar(self):
        self.copy_fixture()
        estado = json.loads(self.ok("estado", "hilt", "--json").stdout)["temas"][0]
        self.assertEqual((estado["hechas"], estado["total"], estado["formato"]), (2, 25, 1))
        self.assertEqual([g["id"] for g in estado["huecos_abiertos"]], ["H1", "H2"])
        self.assertEqual(estado["examenes"], [])
        check = self.ok("check", "hilt").stdout
        self.assertIn("Sin errores", check)
        self.assertNotIn("sin línea de examen", check)
        self.assertIn("coach migrar --dry-run", check)
        self.ok("build")

    def test_una_leccion_301_a_medias_espera_su_practica(self):
        self.copy_fixture()
        step = json.loads(self.ok("siguiente", "hilt", "--json").stdout)
        self.assertEqual(step["tipo"], "repaso")
        step = step["despues"]
        self.assertEqual((step["bloque"]["n"], step["bloque"]["total"]), (2, 2))
        self.assertEqual(step["bloque"]["espera"], "el intento de la práctica 2")
        out = self.ok("corregir", "hilt", "1.3",
                      stdin="**Tu intento:** el build falló con `MissingBinding` · **Veredicto:** ✔").stdout
        self.assertIn("práctica 2 cerrada", out)
        self.assertIn("bloques terminados", out)

    def test_una_leccion_31_a_medias_sigue_por_el_bloque_1(self):
        shutil.copytree(str(FIXTURE_31), str(self.space))
        step = json.loads(self.ok("siguiente", "algebra", "--json").stdout)
        self.assertIn("la nota aún no tiene bloques", step["texto"])
        self.assertTrue(any(" bloque algebra 1.3 1" in c for c in step["comandos"]))
        self.ok("bloque", "algebra", "1.3", stdin=HEADER + BLOQUE_1)
        text = next((self.space / "algebra" / "lecciones").glob("1.3-*.md")).read_text(encoding="utf-8")
        self.assertNotIn("<!--", text)
        self.assertNotIn("COMPLETAR", text[text.index("## Objetivos"):text.index("## 📖")])
        self.assertLess(text.index("## ❓ Preguntas · 1."), text.index("## Resumen con tus palabras"))
        step = json.loads(self.ok("siguiente", "algebra", "--json").stdout)
        self.assertEqual((step["bloque"]["n"], step["bloque"]["total"]), (1, 2))
        self.assertIn("Sin errores", self.ok("check", "algebra").stdout)

    def test_migrar_anade_sin_borrar_con_respaldo_e_idempotente(self):
        self.copy_fixture()
        before = self.snapshot()
        self.assertIn("simulación", self.ok("migrar", "--dry-run").stdout)
        self.assertEqual(self.snapshot(), before)
        out = self.ok("migrar").stdout
        self.assertIn("Copia de seguridad", out)
        backups = list((self.space / ".respaldos").iterdir())
        self.assertEqual(len(backups), 1)
        for rel, text in before.items():
            self.assertEqual((backups[0] / rel).read_text(encoding="utf-8"), text, rel)
        after = self.snapshot()
        for rel, text in before.items():
            new_lines = after[rel].splitlines()
            for line in text.splitlines():
                self.assertIn(line, new_lines, "%s perdió «%s»" % (rel, line))
        estado = json.loads(self.ok("estado", "hilt", "--json").stdout)["temas"][0]
        self.assertEqual(estado["formato"], 2)
        self.assertEqual([e["modulo"] for e in estado["examenes"]], ["1", "2", "3", "4", "5", "6"])
        self.assertIn("repaso: 2026-11-13", after["hilt/lecciones/1.2-di-manual-constructor-contenedor-y-fabricas.md"])
        self.assertIn("| Pasos |", after["METODO.md"])
        self.assertIn("no hay nada que migrar", self.ok("migrar").stdout)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(len(list((self.space / ".respaldos").iterdir())), 1)

    # ---------------------------------------------------------------- visor

    def formato(self, inputs):
        """Ejecuta CoachFormato (el <script id="coach-formato"> del cuaderno) con Node sobre cada entrada."""
        node = shutil.which("node")
        if not node:
            self.skipTest("Node no está instalado")
        harness = Path(self.tmp.name) / "formato.js"
        harness.write_text(FORMATO_JS, encoding="utf-8")
        result = subprocess.run([node, str(harness), str(SKILL / "assets" / "cuaderno.html")], input=json.dumps(inputs),
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_el_cuaderno_nunca_muestra_marcadores_ni_comentarios(self):
        carlos = next((FIXTURE_31 / "algebra" / "lecciones").glob("1.3-*.md")).read_text(encoding="utf-8")
        antigua = next((FIXTURE_301 / "hilt" / "lecciones").glob("1.3-*.md")).read_text(encoding="utf-8")
        codigo = "```html\n<!-- en el código se queda -->\n```\n\nTexto `<!-- en línea -->` y <!-- fuera --> fin."
        limpia, vieja, cod = self.formato([{"op": "limpiar", "texto": t.split("\n---\n", 1)[-1]}
                                           for t in (carlos, antigua)] + [{"op": "limpiar", "texto": codigo}])
        for text in (limpia, vieja):
            self.assertNotIn("[[", text)
            self.assertNotIn("<!--", text)
        self.assertNotIn("## Resumen con tus palabras", limpia)
        self.assertNotIn("## Fuentes", limpia)
        self.assertNotIn("**Bloques:**", limpia)
        self.assertIn("## Historial", limpia)
        self.assertIn("- Aplicar las leyes de los exponentes", limpia)
        self.assertIn("<!-- en el código se queda -->", cod)
        self.assertIn("`<!-- en línea -->`", cod)
        self.assertNotIn("fuera", cod)

    def test_el_cuaderno_y_el_script_ven_los_mismos_bloques(self):
        spec = importlib.util.spec_from_file_location("coach_mod", str(SCRIPT))
        coach = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(coach)
        self.init_topic()
        self.ok("bloque", "sql", "1.1", stdin=HEADER + BLOQUE_1)
        self.ok("corregir", "sql", "1.1", stdin="**Tu intento:** x · **Veredicto:** ✘ falta la coma")
        en_curso = self.note_path("1.1").read_text(encoding="utf-8")
        self.ok("corregir", "sql", "1.1", stdin="**Segundo intento:** y · **Veredicto:** ✔\n\n<details>\n<summary>"
                                                  "Solución</summary>\n\nz\n\n</details>\n\n**P1.** tu respuesta: *a* ✘")
        notas = [en_curso, self.note_path("1.1").read_text(encoding="utf-8")]
        for base in (FIXTURE_301 / "hilt", FIXTURE_31 / "algebra", SKILL / "assets" / "ejemplo" / "hilt",
                     SKILL / "assets" / "ejemplo" / "estadistica-ab"):
            notas += [p.read_text(encoding="utf-8") for p in sorted((base / "lecciones").glob("*.md"))]

        def resumen(info):
            return {"mapa": [[e["n"], e["titulo"]] for e in info["mapa"]],
                    "bloques": [[b["n"], b["titulo"], b["espera"]["texto"] if b["espera"] else None]
                                for b in info["bloques"]],
                    "retos": [[r["k"], r["estado"]] for r in info["retos"]],
                    "preguntas": [[q["k"], q["estado"]] for q in info["preguntas"]],
                    "actual": info["actual"]["n"] if info["actual"] else None,
                    "siguiente": info["siguiente"]["n"] if info["siguiente"] else None, "total": info["total"]}

        js = self.formato([{"op": "bloques", "texto": t.split("\n---\n", 1)[-1]} for t in notas])
        self.assertEqual(len(js), len(notas))
        for text, got in zip(notas, js):
            self.assertEqual(resumen(got), resumen(coach.note_blocks(text)), text[:120])

    def test_el_javascript_del_cuaderno_es_valido(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node no está instalado")
        html = (SKILL / "assets" / "cuaderno.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script(?: id=\"coach-formato\")?>(.*?)</script>", html, re.S)
        self.assertEqual(len(scripts), 3)
        js = Path(self.tmp.name) / "cuaderno.js"
        js.write_text("\n;\n".join(scripts), encoding="utf-8")
        result = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
