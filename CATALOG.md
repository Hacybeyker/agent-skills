# Catálogo del entorno

Mapa de todo lo que usan los agentes: qué es, quién lo mantiene y por qué está. Actualízalo cuando agregues o quites algo.

## Skills propias (este repo)

Se instalan con `install.sh` en `~/.claude/skills` y `~/.agents/skills`.

| Skill | Tipo | Versión | Reemplaza a |
| --- | --- | --- | --- |
| `hb-setup` | Flujo | 1.0.0 | — (nueva) |
| `hb-implement` | Flujo | 1.0.0 | `feature-implementation` (Android y KMP) |
| `hb-review` | Flujo | 1.0.0 | `code-reviewer` |
| `hb-commit` | Flujo | 1.0.0 | `git-commit` y el plugin `commit-commands` |
| `hb-release` | Flujo | 1.0.0 | `changelog-generator` |
| `hb-stack-mobile-kotlin` | Perfil | 1.0.0 | `android-best-practices` y `kmp-best-practices` |
| `hb-coach` | Personal | 2.0.0 | `software-coach` |

## Skills externas

No llevan `hb-` y no se copian a este repo: cada una se actualiza con su propio instalador.

| Skill | Proveedor | Cómo se mantiene |
| --- | --- | --- |
| `testigo-flows` | Hacybeyker (publicada en [testigo](https://github.com/Hacybeyker/testigo)) | Enlace a tu clon de testigo; `testigo setup` la instala para otros usuarios |
| `android-cli` | Google | `android init` la instala y la actualiza |
| Skills oficiales de Android | Google ([android/skills](https://github.com/android/skills)) | `android skills add --skill=<nombre>`, solo si hacen falta |

## Plugins de Claude Code

| Plugin | Proveedor | Para qué |
| --- | --- | --- |
| `kotlin-lsp` | Anthropic (servidor de JetBrains) | Diagnósticos y navegación de código Kotlin. Está en alpha: Android experimental, KMP aún sin soporte |
| `context7` | Upstash | Documentación actualizada de librerías por versión (MCP) |
| `pr-review-toolkit` | Anthropic | Agentes de review especializados; segunda pasada después de `hb-review` |
| `security-guidance` | Anthropic | Avisos de seguridad al editar y revisión del diff al terminar cada turno (consume tokens) |
| `claude-md-management` | Anthropic | Auditar y mejorar `CLAUDE.md` / `AGENTS.md` |
| `feature-dev` | Anthropic | Flujo genérico de features para proyectos sin `AGENTS.md` |
| `warp` | Warp | Notificaciones de Warp cuando Claude Code necesita input |

**Quitados:** `code-review` (redundante con `pr-review-toolkit` y `hb-review`), `commit-commands` (chocaba con el commit propio; lo cubre `hb-commit`), `github` (lo cubre el CLI `gh`), `claude-code-setup` (de uso único), `swift-lsp` (casi no se escribe Swift).

**Cuando hagan falta:** `typescript-lsp` y `pyright-lsp` (web y backend), `jdtls-lsp` (Spring Boot en Java), `plugin-dev` (si se empaquetan skills como plugin).

**Descartado:** el MCP de Maestro, porque `testigo-flows` exige usar Maestro solo con su entorno local.

## Cuenta de Claude (claude.ai)

Se sincronizan a Claude Code. Para no cargarlas en Claude Code: `"syncClaudeAiSkills": false` o `"syncClaudeAiPlugins": false` en `~/.claude/settings.json`.

| Tipo | Elementos | Proveedor |
| --- | --- | --- |
| Skills | `docx`, `xlsx`, `pptx`, `pdf`, `docs`, `google-workspace`, `deep-research`, `skill-creator`, `computer-use`, `chrome-browser`, `built-in-browser`, `morning`, `import-memory` | Anthropic |
| Plugins | `engineering`, `cowork-plugin-management` (este solo sirve para crear plugins de Cowork) | Anthropic |

## Configuración

| Qué | Dónde | Valor |
| --- | --- | --- |
| Sin atribución de IA en commits y PRs | `~/.claude/settings.json` | `"attribution": { "commit": "", "pr": "", "sessionUrl": false }` |
| GitHub desde la terminal | CLI `gh` | Autenticado con token, protocolo SSH |

## Retirado

| Antes | Ahora |
| --- | --- |
| Copias de skills en `.agents/skills` de cada proyecto, con symlinks por editor | Instalación global con `install.sh` |
| `skill-linker` y los scripts `link-skill.sh` / `sync-skills.sh` | `install.sh` |
| Copias antiguas de `skill-creator` en los proyectos | `skill-creator` de la cuenta de Claude |
