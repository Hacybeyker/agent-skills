#!/usr/bin/env python3
"""Arma la sección `## DoD` de AGENTS.md con lo que de verdad hace fallar un PR, sin inventar herramientas.

- Con CI: lee los workflows (.github/workflows/*.yml), las acciones compuestas locales que invocan
  (`uses: ./.github/actions/<nombre>`) y los workflows reutilizables (`uses: ./.github/workflows/<archivo>`, los de
  `workflow_call`), y junta las tareas de verificación que corren: lint, formato, análisis estático, tests, cobertura y el
  build. Las que no pueden hacer fallar un PR o no se pueden correr en local (una cobertura con mínimo 0, un análisis que
  necesita el token de un servicio externo, un reporte) van en una línea aparte, con el motivo.
- Sin CI: lo arma desde el build, en este orden: el formateador (si está configurado), los linters y el análisis
  estático configurados, los tests (si existen) y el build del artefacto principal. Sin nada de eso, compilar (o validar
  la sintaxis, si no hay build). Lleva una línea de origen ("DoD derivado del build; el proyecto no tiene CI").

La forma (S2): el formateador en su propia invocación y, después, una sola invocación con todos los checks, los tests y
el build (en Gradle, `./gradlew a:check b:test c:assemble`: así el formateo y los checks nunca corren en paralelo). Cada
comando empieza con `cd <ruta del proyecto> && …`. No agrega herramientas, tests ni CI: eso es de `## Modernización`.

Uso: python3 -I dod.py [--repo .]
Python 3.8 o superior, solo librería estándar.
"""
import argparse
import json
import pathlib
import re
import shlex
import sys

WORKFLOWS = (".github/workflows",)
YAML = ("*.yml", "*.yaml")
# Tareas de Gradle que no verifican nada (publican, suben, limpian o generan reportes)
GRADLE_SKIP = re.compile(r"(?:^|:)(?:clean|publish\w*|upload\w*|appDistribution\w*|firebase\w*|dependencyUpdates|"
                         r"dependencies|tasks|help|wrapper|properties|signingReport|bundle\w*Release\w*|"
                         r"assemble\w*Release\w*AndroidTest)$")
GRADLE_REPORT = re.compile(r"(?:^|:)(?:kover\w*Report\w*|jacoco\w*Report\w*|\w+HtmlReport|\w+XmlReport)$", re.I)
GRADLE_COVERAGE = re.compile(r"(?:^|:)(?:koverVerify\w*|jacoco\w*CoverageVerification\w*|\w*CoverageVerification)$",
                             re.I)
GRADLE_EXTERNAL = re.compile(r"(?:^|:)(?:sonar\w*|sonarqube\w*|codecov\w*|coveralls\w*|snyk\w*|dependencyCheck\w*)$",
                             re.I)
GRADLE_FORMATTERS = (("org.jlleitschuh.gradle.ktlint", "ktlintFormat"), ("ktlint", "ktlintFormat"),
                     ("com.diffplug.spotless", "spotlessApply"), ("spotless", "spotlessApply"),
                     ("com.ncorti.ktfmt", "ktfmtFormat"), ("ktfmt", "ktfmtFormat"))
EXTERNAL_TOOLS = re.compile(r"\b(sonar\w*|codecov|coveralls|snyk|deepsource|codacy|codeclimate)\b", re.I)
COVERAGE_ZERO = re.compile(r"minBound\s*\(\s*0\s*\)|minValue\s*=\s*0\b|minimum\s*=\s*(?:\"0(?:\.0+)?\"|0(?:\.0+)?)\b|"
                           r"minimum\s*=\s*BigDecimal\(\s*\"?0(?:\.0+)?\"?\s*\)", re.I)
NODE_VERIFY = ("format:check", "lint", "typecheck", "type-check", "check", "test", "build")
NODE_FORMAT = ("format", "fmt", "prettier")


def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def yaml_steps(text):
    """[(comando, bloque del paso)] de los `run:` de un workflow o de una acción compuesta, en orden, y [(referencia
    local, bloque)] de los `uses: ./…`. Lectura por líneas (sin PyYAML): run en una línea o en un bloque `|`/`>`."""
    lines = text.splitlines()
    runs, uses = [], []
    index = 0
    while index < len(lines):
        line = lines[index]
        step_start = index
        found = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
        used = re.match(r"^(\s*)(?:-\s+)?uses:\s*['\"]?(\./[^'\"\s#]+)", line)
        if used:
            uses.append((used.group(2).rstrip("/"), step_block(lines, step_start)))
        if not found:
            index += 1
            continue
        indent, value = len(found.group(1)), found.group(2).strip()
        if value[:1] in ("|", ">"):
            body, index = [], index + 1
            while index < len(lines) and (not lines[index].strip() or len(lines[index]) - len(lines[index].lstrip())
                                          > indent):
                body.append(lines[index].strip())
                index += 1
            command = "\n".join(part for part in body if part)
        else:
            command, index = value.strip("'\""), index + 1
        runs.append((command, step_block(lines, step_start)))
    return runs, uses


def step_block(lines, at):
    """El texto del paso de `lines[at]` (desde su `-` hasta el siguiente paso del mismo nivel): para ver su `env`."""
    start = at
    while start > 0 and not re.match(r"^\s*-\s", lines[start]):
        start -= 1
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
        end += 1
    return "\n".join(lines[start:end])


def ci_commands(repo):
    """([(comando, de dónde sale, bloque)], [archivos leídos]) de los workflows y de lo local que invocan."""
    files = []
    for folder in WORKFLOWS:
        for pattern in YAML:
            files += sorted((repo / folder).glob(pattern))
    seen, out, order = set(), [], list(files)
    while order:
        path = order.pop(0)
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        runs, uses = yaml_steps(read(path))
        relative = path.relative_to(repo).as_posix()
        for command, block in runs:
            out.append((command, relative, block))
        for ref, _ in uses:
            target = (repo / ref).resolve()
            candidates = [target] if target.suffix in (".yml", ".yaml") else \
                [target / "action.yml", target / "action.yaml"]
            for candidate in candidates:
                if candidate.is_file() and candidate not in seen:
                    order.append(candidate)
                    break
    return out, sorted(path.relative_to(repo).as_posix() for path in seen)


def gradle_tasks(command):
    """Las tareas de las invocaciones de Gradle de un comando (sin las opciones)."""
    tasks = []
    for line in command.replace("\\\n", " ").splitlines():
        for chunk in re.split(r"&&|;|\|\|", line):
            try:
                words = shlex.split(chunk)
            except ValueError:
                words = chunk.split()
            for position, word in enumerate(words):
                if re.search(r"(?:^|/)gradlew?$", word):
                    rest = words[position + 1:]
                    skip = False
                    for item in rest:
                        if skip:
                            skip = False
                            continue
                        if item.startswith("-"):
                            skip = item in ("-x", "--exclude-task", "-p", "--project-dir", "-c", "--settings-file")
                            continue
                        if re.fullmatch(r"[\w:.-]+", item):
                            tasks.append(item)
                    break
    return tasks


def build_files(repo):
    return [path for pattern in ("build.gradle", "build.gradle.kts", "*/build.gradle", "*/build.gradle.kts",
                                 "*/*/build.gradle", "*/*/build.gradle.kts", "gradle/libs.versions.toml",
                                 "settings.gradle", "settings.gradle.kts")
            for path in sorted(repo.glob(pattern))]


def gradle_formatter(repo):
    text = "\n".join(read(path) for path in build_files(repo))
    return next((task for plugin, task in GRADLE_FORMATTERS if plugin in text), None)


def coverage_zero(repo):
    return any(COVERAGE_ZERO.search(read(path)) for path in build_files(repo))


def classify_gradle(tasks, repo, external):
    """([verificación en orden], [(tarea, motivo)] fuera del DoD)."""
    keep, out = [], []
    zero = coverage_zero(repo)
    for task in tasks:
        if task in keep or any(task == name for name, _ in out):
            continue
        if GRADLE_SKIP.search(task):
            continue
        if re.search(r"(?:^|:)(?:ktlintFormat|spotlessApply|ktfmtFormat|formatKotlin)$", task):
            continue  # el formateador va en su propia invocación
        if GRADLE_EXTERNAL.search(task) or (task in external):
            out.append((task, "necesita %s, el token de un servicio externo: no se corre en local" % external.get(
                task, "un token del CI")))
        elif GRADLE_REPORT.search(task):
            out.append((task, "genera un reporte: no puede hacer fallar un PR"))
        elif GRADLE_COVERAGE.search(task) and zero:
            out.append((task, "la cobertura mínima configurada es 0: no puede hacer fallar un PR"))
        else:
            keep.append(task)
    return sorted(keep, key=task_rank), out


def task_rank(task):
    """El orden de la invocación única: análisis (lint, formato verificado, estático), tests y cobertura, y el build.
    Dentro de cada grupo, el orden del CI (sorted es estable)."""
    name = task.rsplit(":", 1)[-1]
    if re.match(r"(?:assemble|build|bundle|package)", name, re.I):
        return 2
    if re.search(r"test|kover|jacoco|coverage", name, re.I):
        return 1
    return 0


def from_ci(repo, root_text):
    commands, files = ci_commands(repo)
    if not files:
        return None
    tasks, external, other, skipped = [], {}, [], []
    for command, _, block in commands:
        secret = re.search(r"secrets\.(\w+)", block)
        found = gradle_tasks(command)
        if found:
            if secret or EXTERNAL_TOOLS.search(command):
                for task in found:
                    if EXTERNAL_TOOLS.search(task) or (secret and EXTERNAL_TOOLS.search(block)):
                        external[task] = secret.group(1) if secret else "un token"
            tasks += found
            continue
        tool = EXTERNAL_TOOLS.search(command)
        if tool:
            skipped.append((one_line(command), "necesita el token de %s: no se corre en local" % tool.group(1)))
            continue
        for line in command.splitlines():
            if re.match(r"^(?:npm|pnpm|yarn|npx|ruff|mypy|pytest|flake8|black|swiftlint|xcodebuild|cargo|go|"
                        r"flutter|dart|make|tox|bundle)\b", line.strip()) and not re.search(
                            r"\b(?:install|ci|publish|deploy|login|setup)\b", line):
                other.append(line.strip())
    keep, out = classify_gradle(tasks, repo, external)
    return {"gradle": keep, "otros": list(dict.fromkeys(other)), "fuera": out + skipped,
            "origen": "los pasos de verificación del CI (%s)" % ", ".join(files)}


def one_line(text):
    return " ".join(text.split())[:100]


def android_app_modules(repo):
    out = []
    for path in build_files(repo):
        if path.name.startswith("build.gradle") and re.search(r"com\.android\.application|android\.application",
                                                              read(path)):
            module = path.parent.relative_to(repo).as_posix()
            out.append("" if module == "." else ":" + module.replace("/", ":"))
    return out


def from_build(repo):
    """Sin CI: el formateador, los linters y el análisis configurados, los tests y el build del artefacto principal."""
    if (repo / "gradlew").is_file() or build_files(repo):
        text = "\n".join(read(path) for path in build_files(repo))
        apps = android_app_modules(repo)
        tasks = []
        if re.search(r"ktlint", text):
            tasks.append("ktlintCheck")
        if re.search(r"detekt", text):
            tasks.append("detekt")
        if re.search(r"spotless", text):
            tasks.append("spotlessCheck")
        if apps and re.search(r"\blint(?:Options)?\s*\{", text):
            tasks += ["%s:lintDebug" % app for app in apps]
        has_tests = any(repo.glob("**/src/test")) or any(repo.glob("**/src/test*/**/*.kt")) or any(
            repo.glob("**/src/test*/**/*.java"))
        if has_tests:
            tasks.append("testDebugUnitTest" if apps else "test")
        tasks += ["%s:assembleDebug" % app for app in apps] if apps else ["assemble"]
        return {"gradle": tasks, "otros": [], "fuera": [], "tests": has_tests,
                "origen": "DoD derivado del build; el proyecto no tiene CI%s" % ("" if has_tests else " ni tests")}
    package = repo / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(read(package) or "{}").get("scripts") or {}
        except (ValueError, AttributeError):
            scripts = {}
        manager = "pnpm" if (repo / "pnpm-lock.yaml").is_file() else "yarn" if (repo / "yarn.lock").is_file() else "npm"
        run = (lambda name: "%s run %s" % (manager, name)) if manager == "npm" else (lambda name: "%s %s" % (manager, name))
        formatter = next((run(name) for name in NODE_FORMAT if name in scripts), None)
        verify = [run(name) for name in NODE_VERIFY if name in scripts]
        has_tests = "test" in scripts
        if not verify:
            verify = [run("build")] if "build" in scripts else ["node --check %s" % (
                "index.js" if (repo / "index.js").is_file() else "<archivo de entrada>")]
        return {"formato": formatter, "otros": [" && ".join(verify)], "gradle": [], "fuera": [], "tests": has_tests,
                "origen": "DoD derivado del build; el proyecto no tiene CI%s" % ("" if has_tests else " ni tests")}
    if (repo / "pyproject.toml").is_file() or any(repo.glob("*.py")):
        config = read(repo / "pyproject.toml")
        steps = []
        formatter = "ruff format ." if "ruff" in config else "black ." if "black" in config else None
        if "ruff" in config:
            steps.append("ruff check .")
        if "mypy" in config:
            steps.append("mypy .")
        has_tests = (repo / "tests").is_dir() or any(repo.glob("test_*.py"))
        if has_tests:
            steps.append("python3 -m pytest" if "pytest" in config else "python3 -m unittest discover -s tests")
        steps.append("python3 -m compileall -q .")
        return {"formato": formatter, "otros": [" && ".join(steps)], "gradle": [], "fuera": [], "tests": has_tests,
                "origen": "DoD derivado del build; el proyecto no tiene CI%s" % ("" if has_tests else " ni tests")}
    scripts = sorted(path.relative_to(repo).as_posix() for path in repo.glob("*.sh"))
    if scripts:
        return {"formato": None, "otros": [" && ".join("bash -n %s" % shlex.quote(name) for name in scripts)],
                "gradle": [], "fuera": [], "tests": False,
                "origen": "DoD derivado de los scripts; el proyecto no tiene CI, build ni tests: valida la sintaxis"}
    return {"formato": None, "otros": ["<comando que compila o ejecuta el proyecto>"], "gradle": [], "fuera": [],
            "tests": False, "origen": "el proyecto no tiene CI, build ni tests: completa el comando que lo compila"}


def dod(repo):
    """La sección `## DoD` como texto, lista para AGENTS.md."""
    repo = pathlib.Path(repo).resolve()
    data = from_ci(repo, None) or from_build(repo)
    cd = "cd %s && " % shlex.quote(str(repo))
    steps = []
    formatter = data.get("formato") if "formato" in data else (gradle_formatter(repo) if data["gradle"] else None)
    if formatter and data["gradle"] and not formatter.startswith(("./", "gradle")):
        formatter = "./gradlew %s" % formatter
    if formatter:
        steps.append(("Formato", formatter))
    checks = []
    if data["gradle"]:
        checks.append("./gradlew %s" % " ".join(data["gradle"]))
    checks += data["otros"]
    if checks:
        label = "Checks, tests y build, en una sola invocación" if data["gradle"] else "Checks, tests y build"
        steps.append((label, " && ".join(checks)))
    lines = ["## DoD", "", "Antes de dar una tarea por terminada, en este orden:", ""]
    lines += ["%d. %s: `%s%s`" % (number, label, cd, command) for number, (label, command) in enumerate(steps, 1)]
    lines.append("")
    if data["fuera"]:
        lines.append("Fuera del DoD: %s." % "; ".join("`%s` (%s)" % (name, why) for name, why in data["fuera"]))
    lines.append("Origen: %s." % data["origen"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="la raíz del proyecto (por defecto, la carpeta actual)")
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo)
    if not repo.is_dir():
        print("✖ %s no es una carpeta" % repo, file=sys.stderr)
        return 2
    sys.stdout.write(dod(repo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
