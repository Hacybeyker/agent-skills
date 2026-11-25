---
name: hb-release
description: 'Prepara y publica versiones: mantiene el CHANGELOG.md (Keep a Changelog), cierra [Unreleased] como una versión SemVer, sube la versión del proyecto (versionName/versionCode, package.json, pyproject, etc.), crea el tag, el GitHub release y las notas de tienda (Play Store, App Store). Con varias unidades, toma del modelo de estructura qué unidad se publica, dónde vive su versión y quién la publica, y al terminar propone el bump de la versión fijada en quien la consume. Úsala cuando el usuario pida cortar o preparar una versión, generar el changelog o las release notes, subir la versión o publicar ("corta la versión", "prepara el release", "genera el changelog", "notas de la versión 1.2.0", "release notes", "sube la versión", "/hb-release").'
license: MIT
allowed-tools: Bash
metadata:
  author: hacybeyker
  version: "1.1.0"
  category: flow
  origin: "inspirada en changelog-generator (comunidad)"
---

# hb-release

De `[Unreleased]` a una versión publicada. Lo que diga el proyecto manda sobre esta skill.

**Estándares:** [Semantic Versioning 2.0.0](https://semver.org/), [Keep a Changelog 1.1.0](https://keepachangelog.com/), tags `vX.Y.Z`, y el cálculo de versión desde Conventional Commits que usan herramientas como release-please y semantic-release.

## 1. Lee las reglas del proyecto

Busca en `AGENTS.md` las secciones de versionado, release o publicación. Prevalecen sobre todo lo de abajo. Fíjate en:

- **Cuándo y cuánto subir** la versión (por ejemplo, "PATCH por cada paso, MINOR por cada fase").
- **Dónde vive la versión** y si hay que subir también un código de build (`versionCode`, `VERSION_CODE`).
- **Quién crea el tag.** Si lo crea un workflow de CI, no lo crees tú.
- **Aprobaciones:** si hay que pedir permiso antes de hacer push, publicar o ejecutar un workflow de publicación.
- **Quién commitea.** Si la IA no commitea, prepara todo y entrega el mensaje.

**Modelo de estructura.** Lee `## Estructura` de `AGENTS.md` y, si no existe, `### Repos relacionados` de `## Arquitectura` (el formato anterior). De ahí salen las unidades (su identificador, dónde está su fuente, cómo se consume, cómo pasarla a fuente y volver, su DoD, su repo y rama principal, y quién la publica y versiona), las variantes y entornos, el cliente HTTP, la configuración local modificada a propósito (no es un cambio ajeno, no se revisa como hallazgo y nunca se propone para commit), la línea `Repos vecinos` y la tabla "Documentos": lee solo los documentos cuya fila "Léelo cuando…" corresponde a la tarea, por su ruta exacta. Si lo que encuentras no coincide con el modelo, dilo en la entrega con la corrección; `hb-implement` y `hb-performance` la aplican en `## Estructura`, sobre la ruta real de `AGENTS.md` (`realpath AGENTS.md`). Sin modelo, sigue con lo que haya y ofrece `hb-setup`.

### Qué unidad publicas

Con el modelo, decide primero qué unidad publicas y toma de su fila lo demás:

- **Cuál:** la que nombra el pedido ("release de `core-lib`"); si no nombra ninguna, la app (la fila `Es la app`) o la del repo donde estás.
- **Dónde se corta:** en su repo (la columna "Fuente", por ejemplo `../core-lib`), sobre su rama principal ("Repo y rama principal") al día y con el PR del módulo ya integrado. Comprueba la rama con `git -C <repo> fetch` y `git -C <repo> status -sb`; si estás en otra o atrasada, dilo y pregunta antes de cambiarla. Las secciones 2 a 8 se hacen en ese repo, con las reglas de su propio `AGENTS.md` si lo tiene.
- **Quién la publica y versiona** ("Publica y versiona"):
  - `con la app`: no tiene release propio, sale con el de la app. Dilo y propón el de la app.
  - `la persona, con hb-release`: esta skill completa.
  - `el workflow <nombre> al crear el tag`: preparas el changelog, la versión y el tag; publica el workflow. No lo reemplaces: no publiques a mano lo que él publica (el artefacto, ni el release si lo crea él) y pide permiso antes del push del tag, que es lo que lo dispara.
- **Dónde vive su versión:** lo que diga `## Versionado y release` del `AGENTS.md` de su repo; si no, búscala con la tabla de la sección 5 **dentro de la carpeta de la unidad**, no en la raíz de otra. Si un repo publica varias unidades con versión propia, cada una tiene su changelog y sus tags con prefijo (`core-lib/v2.4.0`, `core-lib-v2.4.0`): sigue el formato de sus tags anteriores.

Sin modelo, la unidad es el repo actual, como siempre.

## 2. Junta la información

```bash
git describe --tags --abbrev=0              # último tag
git tag --sort=-v:refname | head -5         # formato de los tags (¿con "v" o sin "v"?)
git log <último-tag>..HEAD --format='%h %s' # commits desde ese tag
```

Si el repo publica varias unidades, acota a la tuya: `git describe --tags --abbrev=0 --match '<prefijo>*'` y `git log <último-tag>..HEAD --format='%h %s' -- <ruta de la unidad>`.

Lee también la sección `## [Unreleased]` del `CHANGELOG.md` y la versión actual (sección 5).

## 3. Propón la versión

Calcula SemVer a partir de `[Unreleased]` y de los commits:

| Hay… | Sube |
| --- | --- |
| Algún cambio incompatible (`!`, `BREAKING CHANGE`, `Removed` que rompe) | MAJOR (en `0.y.z`, sube MINOR) |
| Alguna funcionalidad nueva (`feat`, `Added`) | MINOR |
| Solo correcciones o mejoras internas | PATCH |

- Pre-releases con identificadores SemVer: `1.3.0-alpha.1`, `1.3.0-beta.1`, `1.3.0-rc.1`.
- La primera versión pública es `1.0.0`. Antes de eso, el proyecto vive en `0.y.z`.

Si `AGENTS.md` define otra regla, usa esa. **Propón la versión y espera confirmación** antes de cambiar archivos.

## 4. Actualiza el CHANGELOG

- Usa las seis secciones estándar: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` y `Security`. Si el archivo usa otra (por ejemplo `Enhancement`), avisa y propone pasarla a `Changed`.
- Si `[Unreleased]` está vacío pero hay commits, arma las entradas desde los commits: `feat` → `Added`, `fix` → `Fixed`, mejoras → `Changed`, seguridad → `Security`. Omite `docs`, `test`, `build`, `ci` y `chore` salvo que importen.
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

1. Commit con las reglas de **hb-commit** (formato e idioma del proyecto). Por ejemplo, `chore(release): v1.2.0`. Lleva solo el changelog, los archivos de versión y las notas de tienda: nunca la configuración local modificada a propósito ni los cambios temporales de una tarea, aunque `git status` los muestre.
2. Tag anotado `vX.Y.Z`: `git tag -a v1.2.0 -m "v1.2.0"`. Si el proyecto ya tiene tags sin `v`, mantén su formato para no romper la secuencia, y avisa de que el estándar es `vX.Y.Z`. Si el tag lo crea CI, omite este paso.

## 7. Publica (solo con confirmación)

Pregunta antes de cada acción que salga de la máquina:

- `git push` y `git push origin <tag>`.
- GitHub release con la sección de esa versión del changelog:
  ```bash
  gh release create <tag> --title "<tag>" --notes-file <archivo-con-la-sección>
  ```
- Si el proyecto publica con un workflow (por ejemplo `publish`, o el que nombra "Publica y versiona"), no lo ejecutes ni lo reemplaces tú: indícalo o pide permiso explícito.

## 8. Notas de tienda

Si el proyecto tiene notas de tienda (por ejemplo `play-store/release-notes/<versión>.txt`), crea las de esta versión **con el mismo formato que las anteriores**: etiquetas de idioma como `<en-US>` y `<es-419>`, viñetas `•`, los mismos idiomas. Reglas:

- Están escritas para el usuario final: qué puede hacer ahora, sin jerga interna, sin refactors ni dependencias.
- Google Play acepta como máximo **500 caracteres por idioma**: cuéntalos.

Si el proyecto no tiene notas de tienda, créalas solo si el usuario las pide.

## 9. Bump en los consumidores

Si la unidad es **publicada** (en el modelo, su "Cómo se consume" empieza por `Publicada:` y nombra su coordenada y el archivo que fija su versión), al terminar el release **propón** subir la versión fijada en cada unidad que la consume: el archivo que nombra su "Cómo se consume" (casi siempre, el de la app) y cualquier otro que el modelo nombre con esa coordenada.

- **Cuándo:** cuando la versión ya está publicada (el workflow terminó, el paquete se puede descargar). Antes, el bump no compila.
- **Qué cambia:** solo la versión fijada en ese archivo (`2.3.1` → `2.4.0`). Nunca la configuración local de sustitución ni el cambio que pasa la unidad a fuente: si esta máquina la usa en fuente, eso queda como está.
- **Cómo:** en el repo del consumidor, una rama según `## Git` y la línea `Repos vecinos`, un commit con las reglas de `hb-commit` (por ejemplo `build(deps): subir core-lib a 2.4.0`) y un PR que enlaza el release. Los cambios de la app que esperaban esta versión van en ese mismo PR.
- **Verificación:** si el DoD local corre con la unidad en fuente (por la configuración local), dilo en el PR: lo publicado lo verifica el CI.
- **El modelo** no cambia: nombra el archivo que fija la versión, no el número.
- Por cada consumidor, propón el repo, el archivo, la versión vieja y la nueva, la rama, el mensaje y el texto del PR. Hazlo solo con confirmación.
- Los consumidores los nombra el modelo del proyecto que consume la unidad (la app), no el repo de la unidad. Si llegaste desde la app (la entrega de `hb-implement` o `hb-commit`), usa su `## Estructura`; si solo tienes el repo de la unidad, pregunta quién la consume o deja el bump como pendiente.

## Al terminar

Resume la versión, los archivos cambiados, el tag, lo que quedó pendiente (push, release o publicación en la tienda) y, si la unidad es publicada, el bump propuesto en cada consumidor.

## Seguridad

- Nunca borres ni muevas tags publicados sin pedirlo explícitamente.
- Nunca subas secretos de firma ni credenciales de las tiendas.
- **Nunca agregues atribución de IA** en commits, tags, releases ni notas.
