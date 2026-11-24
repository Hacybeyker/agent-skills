"""Tests de hb-performance 0.19.0, lo que destapó la primera prueba real del modo orquestado (P1–P9). Los datos son
inventados."""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest

from helpers import commit_all, init_repo, write
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



class DodPlanTest(unittest.TestCase):
    """P2: `cerrar --dod` lee todos los comandos de `## DoD`, en todas sus formas, y aplica (o avisa) los reemplazos de
    una tarea de rendimiento."""

    def plan(self, dod, perf_task=True):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(root), True)
        write(root / "AGENTS.md", "# Demo\n\n## DoD\n\n%s\n## Git\n\n- `git push` solo con aprobación\n" % dod)
        steps, skipped, applied, unresolved = perf.dod_plan(root, perf_task)
        return [step["comando"].split(" && ", 1)[1] for step in steps], skipped, applied, unresolved, steps

    def test_lista_numerada(self):
        commands = self.plan("Antes de dar una tarea por terminada, en este orden:\n\n1. `./gradlew ktlintFormat`\n"
                             "2. `./gradlew :app:detekt :app:lintDebug :app:testDebugUnitTest`\n"
                             "3. `./gradlew :app:assembleDebug`\n")[0]
        self.assertEqual(commands, ["./gradlew ktlintFormat", "./gradlew :app:detekt :app:lintDebug :app:testDebugUnitTest",
                                    "./gradlew :app:assembleDebug"])

    def test_vinetas(self):
        commands, _, _, _, steps = self.plan("- Formato: `./gradlew ktlintFormat`\n- Checks: `./gradlew ktlintCheck "
                                             "detekt`\n- Tests: `./gradlew test`\n- Build: `./gradlew assembleDebug`\n")
        self.assertEqual(commands, ["./gradlew ktlintFormat", "./gradlew ktlintCheck detekt", "./gradlew test",
                                    "./gradlew assembleDebug"])
        self.assertEqual([step["formato"] for step in steps], [True, False, False, False])

    def test_varios_comandos_con_y_logico_en_una_linea(self):
        commands = self.plan("1. `./gradlew ktlintFormat` && `./gradlew check`\n"
                             "2. `cd app && ./gradlew ktlintFormat && ./gradlew test assembleDebug`\n")[0]
        self.assertEqual(commands, ["./gradlew ktlintFormat", "./gradlew check", "cd app && ./gradlew ktlintFormat",
                                    "cd app && ./gradlew test assembleDebug"])
        self.assertEqual(perf.split_and("echo 'a && b'"), ["echo 'a && b'"])  # dentro de comillas va entero
        self.assertEqual(perf.split_and("make a || make b && make c"), ["make a || make b && make c"])

    def test_bloque_de_codigo(self):
        commands = self.plan("```bash\n./gradlew ktlintFormat\n./gradlew detekt \\\n  test assembleDebug\n```\n")[0]
        self.assertEqual(commands, ["./gradlew ktlintFormat", "./gradlew detekt test assembleDebug"])

    def test_reemplazo_condicional_por_numero_de_paso(self):
        commands, _, applied, unresolved, _ = self.plan(
            "1. `./gradlew ktlintFormat`\n2. `./gradlew detekt testDebugUnitTest assembleDebug`\n\n"
            "Si la tarea mide rendimiento, el paso 2 es `./gradlew detekt testDebugUnitTest assembleProfiling`.\n")
        self.assertEqual(commands, ["./gradlew ktlintFormat", "./gradlew detekt testDebugUnitTest assembleProfiling"])
        self.assertEqual(len(applied), 1)
        self.assertEqual(unresolved, [])
        # fuera de una tarea de rendimiento, el paso queda como está y la línea se dice, no se ignora
        commands, skipped, _, _, _ = self.plan("1. `./gradlew assembleDebug`\n\nSi la tarea mide rendimiento, el paso 1 "
                                               "es `./gradlew assembleProfiling`.\n", perf_task=False)
        self.assertEqual(commands, ["./gradlew assembleDebug"])
        self.assertIn("vale solo en una tarea de rendimiento", skipped[0][1])

    def test_reemplazo_condicional_en_lugar_de(self):
        commands, _, applied, _, _ = self.plan(
            "1. Formato: `./gradlew ktlintFormat`\n2. Checks, tests y build: `./gradlew detekt :app:lintDebug "
            ":app:assembleDebug :app:assembleDebugUnitTest`\n   - En una investigación de hb-performance, el paso 2 usa "
            "`assembleProfiling` en lugar de `assembleDebug`.\n")
        self.assertEqual(commands[1], "./gradlew detekt :app:lintDebug :app:assembleProfiling :app:assembleDebugUnitTest")
        self.assertIn("assembleProfiling en lugar de assembleDebug", applied[0])

    def test_condicional_sin_resolver_se_avisa(self):
        _, _, _, unresolved, _ = self.plan("1. `./gradlew test`\n\nSi la tarea mide rendimiento, revisa también "
                                           "`el panel`.\n")
        self.assertEqual(len(unresolved), 1)
        _, skipped, _, _, _ = self.plan("1. `./gradlew test`\n\nSi cambia la API pública, `./gradlew apiDump`.\n")
        self.assertTrue(any("apiDump" in line for line, _ in skipped))  # otra condición: no se corre, pero se dice


class RunDodTest(unittest.TestCase):
    """P2: el DoD corre en orden, se detiene en el primero que falla (dice cuál y dónde está su log) y, si un
    formateador cambia archivos después de los checks, los vuelve a correr."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), True)
        init_repo(self.root)
        self.counter = self.root.parent / ("%s-contador" % self.root.name)
        self.addCleanup(lambda: self.counter.exists() and self.counter.unlink())
        for name, body in (("ok.sh", "exit 0"), ("falla.sh", "echo 'falló el check' >&2; exit 1"),
                           ("nunca.sh", "touch nunca-corrio"),
                           ("check.sh", "echo x >> '%s'" % self.counter), ("fmt.sh", "echo formateado >> codigo.txt")):
            write(self.root / name, "#!/bin/sh\n%s\n" % body)
            os.chmod(str(self.root / name), 0o755)
        write(self.root / "codigo.txt", "fun a() {}\n")
        commit_all(self.root)
        self.folder = self.root / "inv"
        self.folder.mkdir()

    def dod(self, steps):
        write(self.root / "AGENTS.md", "# Demo\n\n## DoD\n\n%s\n" % steps)

    def run_dod(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                perf.run_dod(self.folder, self.root)
                error = None
            except perf.PerfError as caught:
                error = caught
        return out.getvalue(), error

    def test_se_detiene_en_el_primero_que_falla(self):
        self.dod("1. `./ok.sh`\n2. `./falla.sh`\n3. `./nunca.sh`\n")
        out, error = self.run_dod()
        self.assertIsNotNone(error)
        self.assertIn("en `cd %s && ./falla.sh`" % perf.q(self.root), str(error))
        self.assertIn("quedó 1 paso sin correr", str(error).replace("quedaron 1 paso", "quedó 1 paso"))
        self.assertFalse((self.root / "nunca-corrio").exists())
        log = self.folder / "logs" / perf.DOD_LOG
        self.assertIn("Su salida está en %s" % log, out)
        self.assertIn("falló el check", log.read_text(encoding="utf-8"))
        record = perf.read_close(self.folder)
        self.assertEqual((record["dod"], record["dod_fallo"]), ("falló", "cd %s && ./falla.sh" % perf.q(self.root)))
        self.assertIn("DoD de AGENTS.md: 3 pasos", out)

    def test_todos_los_pasos_en_verde(self):
        self.dod("- Checks: `./ok.sh`\n- Tests: `./check.sh`\n- Build: `./ok.sh build && ./check.sh build`\n")
        out, error = self.run_dod()
        self.assertIsNone(error, out)
        self.assertEqual(self.counter.read_text().count("x"), 2)
        self.assertIn("✔ DoD en verde después de quitar los cambios temporales: 4 pasos", out)
        self.assertEqual(perf.read_close(self.folder)["dod"], "ok")

    def test_el_formateo_despues_de_los_checks_los_repite(self):
        self.dod("1. `./check.sh`\n2. `./fmt.sh`\n")
        out, error = self.run_dod()
        self.assertIsNone(error, out)
        self.assertIn("El formateo cambió archivos después de los checks: los vuelvo a correr", out)
        self.assertEqual(self.counter.read_text().count("x"), 2)
        # el formateo primero (el orden del estándar): no hace falta repetir nada
        self.counter.unlink()
        self.dod("1. `./fmt.sh`\n2. `./check.sh`\n")
        out, _ = self.run_dod()
        self.assertNotIn("los vuelvo a correr", out)
        self.assertEqual(self.counter.read_text().count("x"), 1)


if __name__ == "__main__":
    unittest.main()
