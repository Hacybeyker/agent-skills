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
from test_perf import GOOD, HEADER, PKG, CaptureCase, PerfBase, perf, rows
from test_perf_0190 import MEASURED, RIGUROSO, JsonBase
from test_perf_0140 import WIRING, SetupBase


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



class HumoBrokenInstallTest(CaptureCase):
    """P6: `humo` se recupera de una instalación que terminó bien pero quedó rota (el paquete está instalado y su
    actividad de inicio no se resuelve): desinstala solo el paquete medido, lo reinstala con --instalar y reintenta, una
    sola vez."""

    def adb_calls(self):
        return [json.loads(line) for line in (self.dir / "adb.log").read_text(encoding="utf-8").splitlines()]

    def test_reinstala_una_vez_y_sigue(self):
        self.tp_outputs(GOOD)
        self.env["FAKE_INSTALACION_ROTA"] = "1"
        marker = self.env["FAKE_LOG"] + ".reinstalada"
        out = self.ok("humo", "--paquete", PKG, "--instalar", "touch '%s'" % marker)
        self.assertIn("desinstalo solo %s, lo reinstalo con --instalar y reintento, una vez" % PKG, out)
        self.assertIn("✔ Reinstalé %s y su actividad de inicio ya arranca" % PKG, out)
        self.assertIn("TTID 456 ms", out)
        uninstalls = [args for args in self.adb_calls() if "uninstall" in args]
        self.assertEqual(len(uninstalls), 1)
        self.assertEqual(uninstalls[0][-2:], ["uninstall", PKG])  # solo el paquete medido

    def test_si_sigue_rota_se_detiene_con_el_diagnostico(self):
        self.env["FAKE_INSTALACION_ROTA"] = "siempre"
        result = self.perf("humo", "--paquete", PKG, "--actividad", ".MainActivity", "--instalar", "true")
        self.assertEqual(result.returncode, perf.Precondicion.code, result.stdout + result.stderr)
        text = result.stdout + result.stderr
        self.assertIn("sigue sin arrancar después de desinstalarlo y reinstalarlo", text)
        self.assertIn("does not exist", text)
        self.assertIn("actividad .MainActivity", text)
        self.assertEqual(len([args for args in self.adb_calls() if "uninstall" in args]), 1)
        self.assertFalse(any(path.suffix == ".apk" for path in self.dir.rglob("*")))  # no abre el APK en reports/

    def test_sin_instalar_dice_como_seguir(self):
        self.env["FAKE_INSTALACION_ROTA"] = "1"
        result = self.perf("humo", "--paquete", PKG)
        self.assertEqual(result.returncode, perf.Precondicion.code)
        self.assertIn("--instalar '<comando de instalación>'", result.stdout + result.stderr)
        self.assertFalse([args for args in self.adb_calls() if "uninstall" in args])


class OrchestratedTextsTest(JsonBase):
    """P7 y P8: con la investigación en modo orquestado, las salidas humanas no proponen chats nuevos ni textos para
    pegar, dicen quién corre el paso, y el costo es un solo total al final. El modo guiado queda igual."""

    def plan_mode(self, plan, mode=None):
        plan = dict(plan)
        if mode:
            plan["modo"] = mode
        self.plan_as(plan, MEASURED)

    def test_guiado_sigue_proponiendo_chats(self):
        self.plan_mode(dict(RIGUROSO, mejoras=[dict(RIGUROSO["mejoras"][0], estado="aprobada")]))
        out = self.run_in("siguiente", "--carpeta", self.rel).stdout
        self.assertIn("Chat nuevo · Modelo: Sonnet 5.5", out)
        self.assertIn("Texto: \"", out)
        self.assertIn("consumo --carpeta", out)  # el costo de cada sesión hecha, como siempre

    def test_orquestado_no_propone_chats_nuevos(self):
        self.plan_mode(dict(RIGUROSO, mejoras=[dict(RIGUROSO["mejoras"][0], estado="aprobada")]), "orquestado")
        out = self.run_in("siguiente", "--carpeta", self.rel).stdout
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        for text in (out, state.split("## Siguiente paso", 1)[1].split("\n## ", 1)[0]):
            self.assertNotIn("Chat nuevo", text)
            self.assertNotIn("Texto: \"", text)
            self.assertNotIn("pega el texto", text)
            self.assertIn("lo lanza el orquestador", text)
        self.assertNotIn("--sesion", out)  # ningún costo por sesión
        self.assertIn("una sola vez, al final", state)

    def test_aprobar_en_orquestado(self):
        self.plan_mode(dict(RIGUROSO, mejoras=[]), "orquestado")
        for name in ("diagnostico.md", "reporte-inicial-dev.md"):
            (self.folder / name).unlink()
        out = self.run_in("aprobar", "--carpeta", self.rel).stdout
        self.assertIn("Ficha y plan aprobados", out)
        self.assertNotIn("Chat nuevo", out)
        self.assertIn("Orquestador · ", out)
        self.assertIn("lo corre el orquestador", out)

    def test_siguiente_json_marca_el_modo(self):
        self.plan_mode(dict(RIGUROSO, mejoras=[]))
        self.next_json()
        self.assertEqual(json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["modo"], "orquestado")

    def test_un_solo_total_al_final(self):
        self.plan_mode(dict(RIGUROSO, mejoras=[]), "orquestado")
        out = self.run_in("consumo", "--carpeta", self.rel, "--total", "3.06 USD", "--modo", "orquestado",
                          "--desglose", "Haiku 5.5: 0.40 USD, Sonnet 5.5: 2.66 USD")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        state = (self.folder / "estado.md").read_text(encoding="utf-8")
        consumo = state.split("## Consumo", 1)[1].split("\n## ", 1)[0]
        rows = [line for line in consumo.splitlines() if line.startswith("| ") and "---" not in line][1:]
        self.assertEqual(len(rows), 1, consumo)  # una sola fila, sin filas vacías por sesión
        self.assertIn("| orquestado | orquestador y subagentes | 3.06 USD · desglose: Haiku 5.5: 0.40 USD, Sonnet 5.5: "
                      "2.66 USD |", consumo)
        self.assertIn("3.06 USD en 1 sesión anotada", consumo)
        self.assertNotIn("faltan anotar", consumo)
        self.assertEqual(perf.cost_of(rows[0].split("|")[3])["usd"], 3.06)  # el desglose no se suma dos veces
        bad = self.run_in("consumo", "--carpeta", self.rel, "--total", "1 USD", "--sesion", "2 · diagnóstico")
        self.assertEqual(bad.returncode, 2)

    def test_decidir_desde_el_orquestador_queda_anotado(self):
        self.plan_mode(dict(RIGUROSO), "orquestado")
        result = self.run_in("decidir", "--carpeta", self.rel, "--aprobar", "M1", "--descartar", "-", "--pendiente", "-",
                             "--desde-orquestador")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        item = json.loads((self.folder / "plan.json").read_text(encoding="utf-8"))["mejoras"][0]
        self.assertEqual(item["estado"], "aprobada")
        self.assertTrue(item["decidida_desde"].startswith("el usuario, a través del orquestador"))

    def test_el_total_se_pide_solo_al_cerrar(self):
        plan = dict(RIGUROSO, mejoras=[], modo="orquestado")
        self.assertEqual(perf.cost_lines(self.folder, plan), [])
        lines = perf.cost_lines(self.folder, plan, finished=True)
        self.assertIn("en el chat del orquestador, antes de cerrarlo, corre /cost", lines[0])
        self.assertIn("--total '<total en USD>' --modo orquestado", lines[1])



DUMP = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
<node index="0" text="" resource-id="com.ejemplo.app:id/carrusel" content-desc="" bounds="[0,300][1080,700]">
<node index="0" text="" resource-id="com.ejemplo.app:id/poster" content-desc="Marea alta" bounds="[0,300][300,700]" />
<node index="1" text="" resource-id="com.ejemplo.app:id/poster" content-desc="El último faro" bounds="[300,300][600,700]" />
</node>
<node index="1" text="El último faro" resource-id="com.ejemplo.app:id/titulo" bounds="[40,800][1040,900]" />
</node></hierarchy>"""


class OpenedElementTest(PerfBase):
    """P3: cada corrida anota qué elemento abrió (por su texto o su content-desc, con uiautomator, nunca con una captura
    de pantalla) y `comparar` avisa si difiere entre fases o entre corridas de una misma fase."""

    def test_lee_el_nodo_por_id_texto_o_posicion(self):
        nodes = perf.ui_nodes(DUMP)
        self.assertEqual(perf.opened_in(nodes, {"id": "titulo"}), "El último faro")
        self.assertEqual(perf.opened_in(nodes, {"en": [450, 500]}), "El último faro")  # el póster tocado en el carrusel
        self.assertEqual(perf.opened_in(nodes, {"en": [100, 500]}), "Marea alta")
        self.assertEqual(perf.opened_in(nodes, {"desc": "Marea*"}), "Marea alta")
        self.assertEqual(perf.opened_in(nodes, {"id": "no-existe"}), "")
        self.assertEqual(perf.element_moment({"elemento": {"en": [1, 2], "momento": "antes"}}), "antes")
        self.assertEqual(perf.element_moment({"elemento": {"id": "titulo"}}), "fin")
        self.assertIsNone(perf.element_moment({}))
        self.assertEqual(perf.section_invalidators({"invalidar_si": ["SCREEN *Login*", "elemento_distinto"]}),
                         ["SCREEN *Login*"])

    def summaries(self, phase, flow, elements):
        for run, element in enumerate(elements, start=1):
            write(self.dir / phase / ("%s_%d.resumen.json" % (flow, run)), json.dumps({"version": 1, "elemento": element}))

    def test_comparar_avisa_si_el_elemento_difiere_entre_fases(self):
        write(self.csv, HEADER + rows("antes", "lista", "abrir_ms", [900, 910, 905]) +
              rows("despues", "lista", "abrir_ms", [600, 610, 605]))
        self.summaries("antes", "lista", ["El último faro"] * 3)
        self.summaries("despues", "lista", ["Marea alta"] * 3)
        out = self.ok("comparar", self.csv)
        self.assertIn("⚠ lista: el elemento abierto difiere entre fases (antes 'El último faro' (3); despues 'Marea alta' "
                      "(3))", out)

    def test_comparar_avisa_si_cambia_dentro_de_una_fase(self):
        write(self.csv, HEADER + rows("antes", "lista", "abrir_ms", [900, 910, 905]) +
              rows("despues", "lista", "abrir_ms", [600, 610, 605]))
        self.summaries("antes", "lista", ["El último faro", "Marea alta", "El último faro"])
        self.summaries("despues", "lista", ["El último faro"] * 3)
        out = self.ok("comparar", self.csv)
        self.assertIn("lista, antes: el elemento abierto cambió entre corridas de la misma fase: 'El último faro' (2), "
                      "'Marea alta' (1)", out)
        self.assertNotIn("difiere entre fases", out)

    def test_sin_elemento_anotado_no_hay_aviso(self):
        write(self.csv, HEADER + rows("antes", "lista", "abrir_ms", [900, 910, 905]) +
              rows("despues", "lista", "abrir_ms", [600, 610, 605]))
        self.assertNotIn("elemento abierto", self.ok("comparar", self.csv))



class FramesOnEmulatorTest(ManagementTranslationTest):
    """P5: con un síntoma de frames, tirones o animaciones medido en un emulador, la parte de la queja que no se puede
    responder figura desde el principio (advertencias y reporte inicial) y en el final, en el técnico y en gerencia."""

    def on_emulator(self):
        write(self.folder / "plan.json", json.dumps(dict(self.plan, serial="emulator-5554")))

    def test_en_emulador_queda_sin_respuesta(self):
        self.on_emulator()
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertIn("sin respuesta: requiere dispositivo físico",
                      (self.folder / "estado.md").read_text(encoding="utf-8"))  # advertencias para el diagnóstico
        dev = (self.folder / "reporte-inicial-dev.html").read_text(encoding="utf-8")
        biz = (self.folder / "reporte-inicial-gerencia.html").read_text(encoding="utf-8")
        self.assertIn("sin respuesta: requiere dispositivo físico", dev)
        self.assertIn("requiere un teléfono físico; se midió en un emulador", biz)
        self.ok("reporte", "--carpeta", self.folder, "--html")
        self.assertIn("sin respuesta: requiere dispositivo físico",
                      (self.folder / "reporte-final-dev.html").read_text(encoding="utf-8"))

    def test_en_un_telefono_no_dice_nada(self):
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertNotIn("requiere dispositivo físico", (self.folder / "reporte-inicial-dev.html").read_text(
            encoding="utf-8"))

    def test_otro_sintoma_en_emulador_no_dice_nada(self):
        self.on_emulator()
        state = (self.folder / "estado.md").read_text(encoding="utf-8").replace(
            "Lentitud y pérdida de frames al abrir la lista", "La lista tarda en abrir")
        write(self.folder / "estado.md", state)
        self.ok("reporte", "--carpeta", self.folder, "--inicial", "--html")
        self.assertNotIn("requiere dispositivo físico", (self.folder / "reporte-inicial-dev.html").read_text(
            encoding="utf-8"))



class OpenedElementCaptureTest(CaptureCase):
    """P3 de punta a punta: la corrida de prueba dice qué elemento abrió (volcado de uiautomator con la traza detenida) y
    una fase con `invalidar_si: ["elemento_distinto"]` descarta las corridas que abrieron otro."""

    def plan_with(self, **element):
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["elemento"] = dict({"id": "titulo"}, **element)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.env["FAKE_PULL_ELEMENTO"] = DUMP  # lo que baja adb pull del volcado del elemento
        self.tp_outputs(GOOD)

    def test_la_prueba_muestra_el_elemento_abierto(self):
        self.plan_with()
        out = self.ok("capturar", "--plan", self.plan, "--flujo", "home", "--prueba", "--sin-video")
        self.assertIn("Elemento abierto: 'El último faro'", out)
        log = (self.dir / "adb.log").read_text(encoding="utf-8")
        self.assertIn("uiautomator dump %s" % perf.ELEMENT_REMOTE, log)
        self.assertNotIn("screencap", log)  # nunca una captura de pantalla

    def test_invalidar_si_elemento_distinto(self):
        self.plan_with(esperado="Marea alta")
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["flujos"]["home"]["invalidar_si"] = ["SCREEN *Login*", "elemento_distinto"]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        result = self.perf("capturar", "--plan", self.plan, "--flujo", "home", "--fase", "antes", "--corridas", "3",
                           "--calentamiento", "0", "--sin-compilar")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("abrió 'El último faro' y no 'Marea alta' (invalidar_si elemento_distinto)", result.stdout)



class PerformanceSectionTest(SetupBase):
    """P9: el bloque de estado es la única fuente del estado del setup. Después de `setup --guardar --quitar`, la sección
    de rendimiento no dice "Setup listo" fuera del bloque, el build type medido se aclara como presente con el parche
    repuesto y no queda ningún serial de dispositivo; `setup --reponer` tampoco deja seriales."""

    def agents_with_machine_lines(self):
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8").replace(
            "- setup listo\n", "- Setup listo.\n- Build type medido: `profiling`.\n"
            "- Instalar en el emulador: `ANDROID_SERIAL=emulator-5554 ./gradlew :app:installProfiling`\n"
            "- Ver el dispositivo: `adb -s R58N12ABCDE shell getprop ro.product.model`\n")
        write(self.root / "AGENTS.md", text)
        commit_all(self.root, "agents")

    def section(self):
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        start, end = perf.performance_section(text)
        body = text[start:end]
        block = re.search(r"<!-- hb-performance:estado -->.*?<!-- /hb-performance:estado -->", body, re.S)
        return body, (body[:block.start()] + body[block.end():]) if block else body

    def test_despues_de_quitar_no_hay_setup_listo_ni_seriales(self):
        self.agents_with_machine_lines()
        self.instrument()
        out = self.good("setup", "--guardar", "--quitar", *WIRING)
        body, outside = self.section()
        self.assertNotRegex(outside, r"(?i)setup\s+listo")
        self.assertNotIn("emulator-5554", body)
        self.assertNotIn("R58N12ABCDE", body)
        self.assertIn("ANDROID_SERIAL=<serial> ./gradlew :app:installProfiling", outside)
        self.assertIn("adb -s <serial> shell", outside)
        self.assertIn("Build type medido: `profiling` (presente cuando el parche del setup está repuesto).", outside)
        self.assertIn("Setup: en parche", body)  # el estado lo dice el bloque
        self.assertIn("✔ AGENTS.md (sección de rendimiento, fuera del bloque de estado)", out)
        # el caso se sigue leyendo del bloque, sin "setup listo"
        self.assertIn("en parche", self.good("setup", "--estado"))
        # reponer: no vuelve a poner seriales ni "setup listo"
        self.good("setup", "--reponer")
        body, outside = self.section()
        self.assertNotRegex(outside, r"(?i)setup\s+listo")
        self.assertNotIn("emulator-5554", body)


if __name__ == "__main__":
    unittest.main()
