# agent-skills

Skills para agentes de IA (Claude Code, Copilot, Gemini en Android Studio, Junie, Codex y otros compatibles con [Agent Skills](https://agentskills.io/)). El repo es público y lo debe poder usar cualquier programador, de forma simple y sin que rompa ni modifique lo que ya funciona en su máquina.

## Stack

- Perfil: ninguno. No es una app: el producto son instrucciones en Markdown que otros agentes cargan.
- Markdown con frontmatter, según la [especificación de Agent Skills](https://agentskills.io/specification).
- Bash en `install.sh`, Python 3 en `scripts/check_conventions.py`, y Python o Node en los scripts de cada skill.
- CI con GitHub Actions (`.github/workflows/validate.yml`) y Dependabot para las actions.

## Comandos

| Para | Comando |
| --- | --- |
| Preparar las herramientas de validación | `python3 -m venv .venv && .venv/bin/pip install skills-ref==0.1.1 shellcheck-py==0.11.0.1` |
| Enlazar las skills en esta máquina | `./install.sh` |
| Quitar los enlaces | `./install.sh --uninstall` |
| Probar el contrato de `install.sh` (en un `HOME` temporal) | `scripts/test_install.sh` |

## DoD

Antes de dar una tarea por terminada, en este orden, con `.venv/bin` en el `PATH`, que trae `agentskills` y `shellcheck` con las mismas versiones del CI (son los pasos del workflow `Validate`):

1. `for skill in skills/*/; do agentskills validate "$skill"; done`
2. `python3 scripts/check_conventions.py`
3. `scripts/test_install.sh` (contrato de `install.sh`: es la interfaz pública que usan los instaladores externos)
4. `shellcheck install.sh scripts/test_install.sh`

## Arquitectura

- `skills/<nombre>/`: una carpeta por skill, con un `SKILL.md` corto y, si hacen falta, `references/`, `assets/`, `scripts/` y `agents/`.
- Tipos en `metadata.category`: `flow` (`hb-<verbo>`), `stack` (`hb-stack-<familia>`) y `personal` (`hb-<herramienta>`).
- `assets/` guarda plantillas y ejemplos: `check_conventions.py` no revisa sus enlaces porque son ilustrativos.
- `install.sh` crea enlaces simbólicos en `~/.claude/skills` y `~/.agents/skills`: lo que se edita en `skills/` queda activo al instante para los agentes de esta máquina.
- `README.md` documenta las convenciones y la instalación; `CATALOG.md`, las skills externas y los complementos recomendados. Lo propio de cada máquina (plugins elegidos, cuenta, configuración personal) no va en este repo.

## Reglas del proyecto

- Las skills se escriben en español.
- Nada invasivo: los instaladores nunca pisan ni borran lo que no crearon, y todo lo externo es opcional.
- Todo lo propio lleva el prefijo `hb-`. Una skill externa no se copia a este repo: se lista en `CATALOG.md`.
- Al cambiar una skill, sube su `metadata.version` (SemVer) y refleja la misma versión en `CATALOG.md`. El validador detecta si no coinciden, pero no si olvidaste subirla.
- Al agregar o quitar una skill, actualiza `README.md` y `CATALOG.md` y vuelve a correr `./install.sh`.
- Un `SKILL.md` tiene 500 líneas como máximo: el detalle va a `references/`.
- Los archivos de `skills/*/scripts/` deben ser ejecutables, porque el CI falla sin ese permiso.
- Un perfil `hb-stack-*` nuevo se crea solo cuando hay un proyecto real en ese stack.

## Git

- Commits: Conventional Commits, en español, sin emoji. Si el cambio toca una sola skill, va como scope (`fix(hb-coach): ...`).
- Rama principal: `main`. Se trabaja en ramas cortas y se integra por PR con squash.
- La IA commitea solo cuando se le pide.
- Pide aprobación antes de `git push`, de crear un release y de publicar.

## Versionado y release

- Cada skill tiene su propia versión SemVer en `metadata.version`. El repo no tiene versión global, tags ni `CHANGELOG.md`.
- Integrar a `main` equivale a publicar: de ahí toman los cambios `git pull` en las máquinas enlazadas y `pnpm dlx skills update -g` en las demás (con pnpm, nunca npm).

## Seguridad

- El repo es público: nada de datos personales, de clientes, rutas locales ni secretos en skills, plantillas o ejemplos.
