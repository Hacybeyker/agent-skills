---
name: hb-release
description: 'Prepara y publica versiones: mantiene el CHANGELOG.md (Keep a Changelog), cierra [Unreleased] como una versión SemVer, sube la versión del proyecto (versionName/versionCode, package.json, pyproject, etc.), crea el tag, el GitHub release y las notas de tienda (Play Store, App Store). Úsala cuando el usuario pida cortar o preparar una versión, generar el changelog o las release notes, subir la versión o publicar ("corta la versión", "prepara el release", "genera el changelog", "notas de la versión 1.2.0", "release notes", "sube la versión", "/hb-release").'
license: MIT
allowed-tools: Bash
metadata:
  author: hacybeyker
  version: "1.0.0"
  category: flow
  origin: "inspirada en changelog-generator (comunidad)"
---

# hb-release

De `[Unreleased]` a una versión publicada. Lo que diga el proyecto manda sobre esta skill.

## 1. Lee las reglas del proyecto

Busca en `AGENTS.md` las secciones de versionado, release o publicación. Prevalecen sobre todo lo de abajo. Fíjate en:

- **Cuándo y cuánto subir** la versión (por ejemplo, "PATCH por cada paso, MINOR por cada fase").
- **Dónde vive la versión** y si hay que subir también un código de build (`versionCode`, `VERSION_CODE`).
- **Quién crea el tag.** Si lo crea un workflow de CI, no lo crees tú.
- **Aprobaciones:** si hay que pedir permiso antes de hacer push, publicar o ejecutar un workflow de publicación.
- **Quién commitea.** Si la IA no commitea, prepara todo y entrega el mensaje.

## 2. Junta la información

```bash
git describe --tags --abbrev=0              # último tag
git tag --sort=-v:refname | head -5         # formato de los tags (¿con "v" o sin "v"?)
git log <último-tag>..HEAD --format='%h %s' # commits desde ese tag
```

Lee también la sección `## [Unreleased]` del `CHANGELOG.md` y la versión actual (sección 4).

## 3. Propón la versión

Calcula SemVer a partir de `[Unreleased]` y de los commits:

| Hay… | Sube |
| --- | --- |
| Algún cambio incompatible (`!`, `BREAKING CHANGE`, `Removed` que rompe) | MAJOR (en `0.y.z`, sube MINOR) |
| Alguna funcionalidad nueva (`feat`, `Added`) | MINOR |
| Solo correcciones o mejoras internas | PATCH |

Si `AGENTS.md` define otra regla, usa esa. **Propón la versión y espera confirmación** antes de cambiar archivos.

## 4. Actualiza el CHANGELOG

- Si `[Unreleased]` está vacío pero hay commits, arma las entradas desde los commits: `feat` → `Added`, `fix` → `Fixed`, mejoras → `Changed` (o `Enhancement` si el proyecto la usa), seguridad → `Security`. Omite `docs`, `test`, `build`, `ci` y `chore` salvo que importen.
- Cambia `## [Unreleased]` por `## [x.y.z] - AAAA-MM-DD` y agrega uno nuevo y vacío encima. Copia el estilo de los encabezados que ya existen: el separador, el formato de fecha y si llevan emoji.
- Si las versiones anteriores abren con un párrafo de resumen, escribe uno.
- Si al final hay enlaces de comparación (`[1.2.0]: .../compare/v1.1.0...v1.2.0`), actualízalos.
- Usa el idioma del archivo. Si no existe `CHANGELOG.md`, ofrece crearlo con el encabezado de Keep a Changelog 1.1.0 y SemVer.
- Cada entrada debe describir el cambio con precisión y en lenguaje claro: qué cambió y qué efecto tiene.

## 5. Sube la versión

Busca dónde vive (en este orden) y muestra el diff:

| Stack | Dónde |
| --- | --- |
| Android / KMP | `gradle.properties` (`VERSION_NAME`, `VERSION_CODE`), `gradle/libs.versions.toml` (por ejemplo `appVersion`) o `build.gradle(.kts)` (`versionName`, `versionCode`) |
| iOS (`iosApp`) | `MARKETING_VERSION` y `CURRENT_PROJECT_VERSION` (`.xcconfig` o `project.pbxproj`) |
| Node / web | `package.json` → `npm version <x.y.z> --no-git-tag-version` |
| Python | `pyproject.toml` (`[project] version`) |
| JVM (Spring) | `build.gradle(.kts)` (`version`) o `pom.xml` (`<version>`) |

El código de build (`versionCode` y equivalentes) sube de 1 en 1 y nunca baja.

## 6. Commit y tag

1. Commit con las reglas de **hb-commit** (formato e idioma del proyecto). Por ejemplo, `chore(release): v1.2.0`.
2. Tag anotado con el **mismo formato que los tags existentes**: `git tag -a v1.2.0 -m "v1.2.0"`, o `1.2.0` si el proyecto no usa la `v`. Si el tag lo crea CI, omite este paso.

## 7. Publica (solo con confirmación)

Pregunta antes de cada acción que salga de la máquina:

- `git push` y `git push origin <tag>`.
- GitHub release con la sección de esa versión del changelog:
  ```bash
  gh release create <tag> --title "<tag>" --notes-file <archivo-con-la-sección>
  ```
- Si el proyecto publica con un workflow (por ejemplo "Android Publish"), no lo ejecutes tú: indícalo o pide permiso explícito.

## 8. Notas de tienda

Si el proyecto tiene notas de tienda (por ejemplo `play-store/release-notes/<versión>.txt`), crea las de esta versión **con el mismo formato que las anteriores**: etiquetas de idioma como `<en-US>` y `<es-419>`, viñetas `•`, los mismos idiomas. Reglas:

- Están escritas para el usuario final: qué puede hacer ahora, sin jerga interna, sin refactors ni dependencias.
- Google Play acepta como máximo **500 caracteres por idioma**: cuéntalos.

Si el proyecto no tiene notas de tienda, créalas solo si el usuario las pide.

## Al terminar

Resume la versión, los archivos cambiados, el tag y lo que quedó pendiente: push, release o publicación en la tienda.

## Seguridad

- Nunca borres ni muevas tags publicados sin pedirlo explícitamente.
- Nunca subas secretos de firma ni credenciales de las tiendas.
- **Nunca agregues atribución de IA** en commits, tags, releases ni notas.
