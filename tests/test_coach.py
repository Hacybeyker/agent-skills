"""Tests de la herramienta de hb-coach (skills/hb-coach/scripts/coach.py) en un proyecto temporal."""
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

**P1.** ¿Qué hace `FROM`? — tu respuesta: *la tabla* ✔

<details>
<summary>Respuesta completa</summary>

Indica la tabla de origen de las filas.

</details>
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
        self.assertTrue(any(" leccion sql 1.1" in c for c in step["comandos"]))

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
        self.ok("examen", "sql", "M1", "--resultado", "4/6")
        self.assertRegex(self.lesson_line_exam(), r"^- \[ \] \*\*Examen M1\*\* — 4/6 \(66 %\) el 2026-11-13 · repetir$")
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
        self.assertIn("aciertos/total", self.fails("examen", "sql", "1", "--resultado", "7/6").stderr)

    def lesson_line_exam(self):
        return next(l for l in self.plan.read_text(encoding="utf-8").splitlines() if "**Examen M1**" in l)

    def test_examen_de_un_modulo_sin_linea_la_anade(self):
        self.init_topic()
        self.ok("examen", "sql", "2")
        lines = self.plan.read_text(encoding="utf-8").splitlines()
        i = next(i for i, l in enumerate(lines) if "**2.1 " in l)
        self.assertTrue(lines[i + 1].startswith("- [ ] **Examen M2**"))

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
        self.assertIn("Sin errores", self.ok("check", "hilt").stdout)
        self.assertNotIn("sin línea de examen", self.ok("check", "hilt").stdout)
        self.ok("build")

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
        self.assertIn("repaso: 2026-09-18", after["hilt/lecciones/1.2-di-manual-constructor-contenedor-y-fabricas.md"])
        self.assertIn("| Pasos |", after["METODO.md"])
        self.assertIn("no hay nada que migrar", self.ok("migrar").stdout)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(len(list((self.space / ".respaldos").iterdir())), 1)

    # ---------------------------------------------------------------- visor

    def test_el_javascript_del_cuaderno_es_valido(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node no está instalado")
        html = (SKILL / "assets" / "cuaderno.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(scripts)
        js = Path(self.tmp.name) / "cuaderno.js"
        js.write_text("\n;\n".join(scripts), encoding="utf-8")
        result = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
