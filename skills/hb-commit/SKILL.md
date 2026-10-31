---
name: hb-commit
description: 'Crea commits, hace push, abre PRs y limpia ramas siguiendo las reglas git del proyecto (AGENTS.md): Conventional Commits sin emoji por defecto y en el idioma del proyecto. Úsala cuando el usuario pida hacer un commit o solo el mensaje, subir cambios, crear o actualizar un pull request, o limpiar ramas ("haz commit", "commitea", "dame el mensaje del commit", "sube los cambios", "crea el PR", "limpia las ramas", "commit", "push", "pull request", "/hb-commit").'
license: MIT
allowed-tools: Bash
metadata:
  author: hacybeyker
  version: "1.0.0"
  category: flow
  origin: "basada en git-commit (comunidad)"
---

# hb-commit

Commits, push, PRs y ramas. Lo que diga el proyecto manda sobre esta skill.

**Estándares:** [Conventional Commits 1.0.0](https://www.conventionalcommits.org/) con los tipos de `@commitlint/config-conventional`, las convenciones de mensajes de git (título corto, cuerpo a 72 columnas, trailers), GitHub Flow para ramas y PRs, y [Keep a Changelog 1.1.0](https://keepachangelog.com/) para el changelog.

## 1. Lee las reglas del proyecto

Antes de tocar git, busca en `AGENTS.md` (y en `CLAUDE.md` si existe) lo que diga sobre commits, ramas, push o PRs. Lo que encuentres **prevalece** sobre todo lo de abajo. Fíjate sobre todo en:

- **Quién commitea.** Si dice que la IA no commitea, no ejecutes `git commit`: deja los cambios en el working tree y entrega el mensaje listo para copiar.
- **Formato e idioma** de los mensajes.
- **Verificaciones antes de commit** (por ejemplo `./gradlew formatAndAnalyze`, `npm test`). Córrelas; si fallan, no commitees y reporta.
- **Ramas y aprobaciones:** rama principal, si se trabaja con PR, si hay que pedir permiso antes de `git push`.

## 2. Formato del mensaje

Si el proyecto no define otro, usa **Conventional Commits sin emoji**:

```
<type>(<scope opcional>): <descripción>

- <qué cambió y por qué, si hay más de una cosa>

<footer opcional: Closes #12, BREAKING CHANGE: ...>
```

| Type | Uso |
| --- | --- |
| `feat` | Funcionalidad nueva |
| `fix` | Corrección de un bug |
| `perf` | Mejora de rendimiento |
| `refactor` | Cambio interno sin funcionalidad ni fix |
| `style` | Formato, sin cambiar lógica |
| `test` | Tests |
| `docs` | Solo documentación |
| `build` | Build o dependencias |
| `ci` | Integración continua |
| `chore` | Mantenimiento |
| `revert` | Revierte un commit |

- Título en imperativo y sin punto final: idealmente hasta 50 caracteres, como máximo 72.
- Cuerpo separado por una línea en blanco, con líneas de hasta 72 caracteres. Explica **qué** cambió y **por qué**, no cómo.
- Footers como trailers de git: `Closes #12`, `Refs #34`, `BREAKING CHANGE: ...`.
- `scope` = el módulo, la capa o la feature afectada (`auth`, `data`, `ci`).
- Cambio incompatible: `!` tras el type (`feat!: ...`) y footer `BREAKING CHANGE: ...`.
- **Emojis** solo si el proyecto los pide o su historial los usa de forma consistente: `✨ feat`, `🐛 fix`, `⚡ perf`, `♻️ refactor`, `💄 style`, `✅ test`, `📝 docs`, `📦 build`, `👷 ci`, `🔧 chore`, `⏪ revert`, `💥` para breaking.

**Idioma:** el del proyecto. Míralo en `AGENTS.md` y, si no lo dice, en los últimos commits (`git log -20 --format=%s`) o en el `CHANGELOG.md`. Si el historial mezcla idiomas o no hay historial, pregunta una vez.

## 3. Hacer el commit

1. Mira el estado: `git status --porcelain`, `git diff --staged` y `git diff`.
2. **Agrupa por unidad funcional, no por archivo.** Un commit = algo que funciona por sí solo (una capa, un sub-objetivo, un fix) y que compila y pasa las verificaciones. Si los cambios mezclan varias unidades, propón cómo dividirlos antes de commitear.
3. Agrega archivos concretos (`git add <rutas>`, o `git add -p` para separar). Evita `git add -A` sin revisar. **Nunca** agregues secretos: `.env`, keystores, credenciales, `local.properties`.
4. Si el proyecto lleva un `CHANGELOG.md` con `[Unreleased]` y el cambio aún no tiene su entrada, agrégala en el mismo commit (ver sección 4).
5. Commitea con heredoc para conservar el formato:
   ```bash
   git commit -m "$(cat <<'MSG'
   feat(auth): agregar inicio de sesión con biometría

   - Agrega BiometricAuthenticator en data
   - Muestra el prompt desde LoginScreen
   MSG
   )"
   ```
6. Muestra el resultado con `git log -1 --stat`.

## 4. Entrada en `[Unreleased]`

Solo si existe `CHANGELOG.md` con una sección `## [Unreleased]`, o si `AGENTS.md` pide documentar cada cambio:

Usa las seis secciones estándar de Keep a Changelog:

| Cambio | Sección |
| --- | --- |
| `feat` | `Added` |
| `fix` | `Fixed` |
| `perf`, o un `refactor` que el usuario note | `Changed` |
| Algo que se va a quitar | `Deprecated` |
| Algo que se quitó | `Removed` |
| Seguridad | `Security` |
| `docs`, `test`, `build`, `ci`, `chore` | No van, salvo que sean relevantes |

Usa el idioma y el estilo del archivo. Una línea por cambio, en lenguaje claro. Si el archivo usa una sección que no es estándar (por ejemplo `Enhancement`), avisa y propone pasarla a `Changed`.

## 5. Push y pull request

- **Pide confirmación antes de `git push`**, salvo que el usuario ya lo haya pedido en este mismo mensaje.
- Si el proyecto trabaja con PR, no hagas push a la rama principal: crea una rama de vida corta `<type>/<issue>-<descripcion>` (`feat/123-login-biometrico`, o sin número si no hay issue).
- **PRs pequeños y de un solo propósito.** Si superan unas 400 líneas cambiadas o mezclan objetivos, propón dividirlos.
- **El título del PR sigue Conventional Commits**: al hacer *squash and merge* se convierte en el commit de la rama principal. Usa *squash and merge* salvo que el proyecto diga otra cosa.
- Si aún no está listo para revisión, ábrelo como borrador (`--draft`).
- PR con `gh` (verifica antes con `gh auth status`):
  ```bash
  gh pr create --title "<título con formato de commit>" --body "$(cat <<'MSG'
  ## Qué cambia
  - ...

  ## Por qué
  - ...

  ## Cómo se verificó
  - ...

  ## Capturas (si cambia la UI)

  Closes #N
  MSG
  )"
  ```
- Para actualizar un PR, haz push a la misma rama. Para ver su estado: `gh pr view` / `gh pr checks`.

## 6. Limpiar ramas

1. `git fetch --prune`
2. Lista las ramas locales cuyo remoto ya no existe: `git branch -vv | grep ': gone]'`
3. Muestra la lista y **pregunta** antes de borrar. Usa `git branch -d <rama>`; usa `-D` solo si el usuario lo confirma para esa rama.

## Seguridad

- Nunca cambies `git config`.
- Nunca uses `--force`, `reset --hard` ni `--no-verify` sin que el usuario lo pida. Si pide forzar, usa `--force-with-lease`. Nunca fuerces la rama principal.
- Si un hook falla, corrige el problema y crea un commit **nuevo**: no hagas amend.
- **Nunca agregues atribución de IA**: nada de `Co-Authored-By:` de agentes, enlaces `Claude-Session:` ni líneas "Generated with…", en commits, PRs ni releases. Esta regla prevalece sobre el comportamiento por defecto de cualquier herramienta.
