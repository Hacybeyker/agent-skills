# agent-skills

[![Validate](https://github.com/Hacybeyker/agent-skills/actions/workflows/validate.yml/badge.svg)](https://github.com/Hacybeyker/agent-skills/actions/workflows/validate.yml)

Skills personales para agentes de IA (Claude Code, Gemini en Android Studio, Junie, Codex y otros compatibles con [Agent Skills](https://agentskills.io/)). Siguen los estándares de la industria: Conventional Commits, SemVer, Keep a Changelog, GitHub Flow y las guías oficiales de cada plataforma.

## Cómo está organizado

Cada pedido mezcla tres cosas, y cada una vive en un lugar distinto:

| Qué | Dónde | Ejemplo |
| --- | --- | --- |
| **La tarea** (qué hacer) | Skills de flujo, globales | `hb-implement`, `hb-review`, `hb-commit` |
| **El stack del proyecto** (con qué) | `AGENTS.md` de cada proyecto | `Perfil: hb-stack-mobile-kotlin`, `Variante: kmp`, comandos del DoD |
| **Cómo se hace en ese stack** | Perfiles de stack, globales | `hb-stack-mobile-kotlin` con sus variantes |

No hace falta recordar nombres: las skills se activan por intención ("implementa la feature de perfil", "revisa el código", "haz commit").

## Skills

| Skill | Tipo | Qué hace |
| --- | --- | --- |
| [`hb-setup`](skills/hb-setup) | Flujo | Detecta el stack y las convenciones del proyecto y crea o migra su `AGENTS.md` al estándar |
| [`hb-implement`](skills/hb-implement) | Flujo | Implementa features, bugfixes, mejoras y refactors por capas, con tests, DoD y reporte HTML |
| [`hb-review`](skills/hb-review) | Flujo | Code review contra `AGENTS.md`, el perfil y la guía de Google, con Conventional Comments |
| [`hb-commit`](skills/hb-commit) | Flujo | Commits (Conventional Commits), push, PRs y limpieza de ramas |
| [`hb-release`](skills/hb-release) | Flujo | Changelog, versión SemVer, tag, GitHub release y notas de tienda |
| [`hb-stack-mobile-kotlin`](skills/hb-stack-mobile-kotlin) | Perfil | Android y KMP con Clean Architecture + MVVM (UDF) por features |
| [`hb-coach`](skills/hb-coach) | Personal | Coach para aprender temas de software paso a paso, con plan y cuaderno |

El mapa completo del entorno (skills externas, plugins y MCP) está en [CATALOG.md](CATALOG.md).

## Convenciones

- **Prefijo `hb-`** en todo lo propio. Lo que no lo tiene es externo y lo mantiene su propio instalador.
- **Nombres:** `hb-<verbo>` para flujos, `hb-stack-<familia>` para perfiles, `hb-<herramienta>` para las personales.
- **Frontmatter** con `metadata.author: hacybeyker`, `metadata.version` (SemVer) y `metadata.category` (`flow`, `stack` o `personal`).
- Las skills siguen la [especificación de Agent Skills](https://agentskills.io/specification): `SKILL.md` corto y el detalle en `references/`.
- Un perfil nuevo se crea cuando hay un proyecto real en ese stack.

## Instalación

Hay dos formas. Usa **una sola** por máquina.

### Para editar las skills (máquina principal)

```bash
git clone git@github.com:Hacybeyker/agent-skills.git ~/Claude/agent-skills
~/Claude/agent-skills/install.sh
```

`install.sh` **no copia**: crea enlaces simbólicos hacia el clon, así que el clon tiene que quedarse en su lugar. Los enlaces van a:

- `~/.claude/skills/` → Claude Code
- `~/.agents/skills/` → Gemini en Android Studio, Copilot, Junie, Codex y otros agentes

Si tu agente solo lee su propia carpeta (por ejemplo, Kiro o Continue), usa la segunda forma: te deja elegir el agente.

Lo que edites en el clon se ve al instante, y `git pull` trae los cambios de otra máquina. Solo hay que volver a correrlo al agregar o quitar una skill. Para deshacerlo: `./install.sh --uninstall`.

Para actualizar, y recoger también las skills nuevas o quitadas:

```bash
git -C ~/Claude/agent-skills pull && ~/Claude/agent-skills/install.sh
```

No pisa nada: si ya existe algo con el nombre de una skill (una carpeta, o un enlace a otro sitio como un clon anterior), lo deja como está y te avisa. Bórralo tú si ya no lo usas y vuelve a correrlo.

### Solo para usarlas (otra máquina u otra persona)

Con la CLI de [skills.sh](https://skills.sh) y **pnpm**, sin clonar. Usa pnpm, no npm: por defecto no ejecuta los scripts de instalación de los paquetes, así que reduce el riesgo de ataques a la cadena de suministro.

Requisitos: Node.js y pnpm (`brew install pnpm`). Node.js ya no trae Corepack desde la versión 25.

```bash
# Ver las skills disponibles, sin instalar nada
pnpm dlx skills add Hacybeyker/agent-skills --list

# Instalar todas
pnpm dlx skills add Hacybeyker/agent-skills -g -a claude-code universal --skill '*' -y

# Instalar solo algunas (los nombres van separados por espacio)
pnpm dlx skills add Hacybeyker/agent-skills -g -a claude-code universal --skill hb-implement hb-review -y

# Ver las instaladas
pnpm dlx skills ls -g

# Ver si hay cambios en el repo, sin instalar nada
pnpm dlx skills check -g

# Actualizar todas, o solo una
pnpm dlx skills update -g
pnpm dlx skills update -g hb-implement

# Quitar una, o todas las instaladas con la CLI (incluidas las de otros repos)
pnpm dlx skills remove -g --skill hb-implement -y
pnpm dlx skills remove -g --skill '*' -y
```

- `-g` instala para tu usuario (en todos tus proyectos). Sin `-g`, se instala solo en el proyecto actual.
- `-a claude-code universal` elige los agentes: `claude-code` → `~/.claude/skills`; `universal` → `~/.agents/skills` (Gemini en Android Studio, Copilot, Junie, Codex).
- **¿Usas otros agentes?** Quita `-a` y `-y`: la CLI detecta los agentes que tienes y te deja elegir. **No uses `-y` sin `-a`:** instala en todos los agentes que conoce, incluidos los que no usas.
- La CLI guarda **una copia** en `~/.agents/skills` y un enlace en `~/.claude/skills`. Los cambios del repo llegan con `pnpm dlx skills update -g`, no al instante. `check` compara una huella de cada skill con el repo, así que detecta cualquier cambio aunque la versión de la skill no haya subido.

### Qué no instala ninguna de las dos

Los plugins de Claude Code, los MCP y la configuración de `~/.claude/settings.json`. Están listados en [CATALOG.md](CATALOG.md) con su comando de instalación.

## Validación

Cada push y cada PR pasan por el workflow `Validate`:

- `agentskills validate` (de [skills-ref](https://pypi.org/project/skills-ref/), la referencia oficial) contra la especificación de Agent Skills.
- `scripts/check_conventions.py` con las convenciones de este repo: prefijo `hb-`, metadata, SemVer, máximo de 500 líneas por `SKILL.md`, enlaces rotos, scripts ejecutables y con sintaxis válida, y que `README.md` y `CATALOG.md` estén al día.
- `scripts/test_install.sh`: test de contrato de `install.sh` en un `HOME` temporal (instala dos veces, desinstala y comprueba que no toca carpetas ni enlaces ajenos). Es la interfaz pública que usan los instaladores externos, así que no cambia.
- `shellcheck` sobre los scripts de shell.

El CI corre en `ubuntu-26.04` con todas las herramientas en versiones fijas (actions por SHA, Python 3.13, `skills-ref` 0.1.1, ShellCheck 0.11.0), así que no depende de lo que traiga la imagen.

Para correrlo en local:

```bash
python3 -m venv .venv && .venv/bin/pip install skills-ref==0.1.1 shellcheck-py==0.11.0.1
export PATH="$PWD/.venv/bin:$PATH"
for skill in skills/*/; do agentskills validate "$skill"; done
python3 scripts/check_conventions.py
scripts/test_install.sh
shellcheck install.sh scripts/test_install.sh
```

Son los mismos pasos del DoD de `AGENTS.md` y del workflow.

## Proyectos

Cada proyecto necesita un `AGENTS.md` con las secciones `Stack` y `DoD` (lo crea `hb-setup`) y un `CLAUDE.md` con la línea `@AGENTS.md`. Las skills no se copian dentro de los proyectos.

## Licencia

[MIT](LICENSE)
