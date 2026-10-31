# agent-skills

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
- `~/.agents/skills/` → Gemini en Android Studio, Junie, Codex y otros agentes

Lo que edites en el clon se ve al instante, y `git pull` trae los cambios de otra máquina. Solo hay que volver a correrlo al agregar o quitar una skill. Para deshacerlo: `./install.sh --uninstall`.

### Solo para usarlas (otra máquina u otra persona)

Con la CLI de [skills.sh](https://skills.sh), sin clonar:

```bash
# Todas, globales, para Claude Code y para los agentes que leen ~/.agents/skills
npx skills add Hacybeyker/agent-skills -g -a claude-code universal --skill '*' -y

# Solo una
npx skills add Hacybeyker/agent-skills -g -a claude-code universal --skill hb-implement

npx skills update -g                        # actualizar
npx skills remove -g --skill hb-implement   # quitar
```

La CLI **copia** las skills: los cambios llegan con `npx skills update`, no al instante.

### Qué no instala ninguna de las dos

Los plugins de Claude Code, los MCP y la configuración de `~/.claude/settings.json`. Están listados en [CATALOG.md](CATALOG.md) con su comando de instalación.

## Proyectos

Cada proyecto necesita un `AGENTS.md` con las secciones `Stack` y `DoD` (lo crea `hb-setup`) y un `CLAUDE.md` con la línea `@AGENTS.md`. Las skills no se copian dentro de los proyectos.

## Licencia

[MIT](LICENSE)
