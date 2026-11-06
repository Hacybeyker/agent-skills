---
name: hb-setup
description: 'Prepara un proyecto para trabajar con agentes: detecta el stack, los comandos y las convenciones de git, y crea o actualiza su AGENTS.md con la estructura estándar (Stack, Comandos, DoD, Arquitectura, Reglas, Git, Versionado, Seguridad) más el CLAUDE.md que lo importa. Úsala al empezar un proyecto, cuando falte el AGENTS.md o para pasar uno existente al estándar ("crea el AGENTS.md", "configura el proyecto para los agentes", "actualiza el AGENTS.md", "migra el AGENTS.md al estándar", "/hb-setup").'
license: MIT
metadata:
  author: hacybeyker
  version: "1.1.0"
  category: flow
---

# hb-setup

Deja el proyecto listo para `hb-implement`, `hb-review`, `hb-commit` y `hb-release`. El resultado es un `AGENTS.md` corto que contiene **solo lo propio del proyecto**: lo general vive en los perfiles `hb-stack-*`.

**El `AGENTS.md` describe el proyecto tal como es**, no como debería ser: su stack, su arquitectura y sus librerías reales, aunque sean anteriores a lo que recomienda el perfil (Views y XML, MVP, RxJava, Dagger 2, LiveData). Los agentes trabajan con ese stack. Modernizar es una decisión del usuario, que se toma después, por partes, y queda registrada en `## Modernización`; nunca la toma el setup ni una tarea cualquiera.

**Estándar:** [AGENTS.md](https://agents.md/), el formato abierto que leen Codex, Cursor, Copilot, Junie, Gemini CLI y otros. Claude Code lo lee a través de un `CLAUDE.md` que lo importa.

## 1. Detecta

No preguntes lo que puedes averiguar.

**Stack y perfil.** Usa solo perfiles que existan (las skills `hb-stack-*` instaladas):

| Señal | Stack | Perfil / variante |
| --- | --- | --- |
| Algún `build.gradle.kts` aplica `org.jetbrains.kotlin.multiplatform` | KMP | `hb-stack-mobile-kotlin` / `kmp` |
| `com.android.application` sin KMP | Android | `hb-stack-mobile-kotlin` / `android` |
| `package.json` con `next`, `react`, `@angular/core` o `vue` | Web | Sin perfil todavía |
| `package.json` con `@nestjs/core`, `express` o `serverless` | Backend Node | Sin perfil todavía |
| `pom.xml` o Gradle con `org.springframework.boot` | Backend JVM | Sin perfil todavía |
| `pyproject.toml` o `requirements.txt` | Python | Sin perfil todavía |
| `Dockerfile`, `compose.yaml` | Contenedores | Se anota en Stack |

Si el stack no tiene perfil, escribe `Perfil: ninguno` y menciona que conviene crearlo cuando haya un segundo proyecto con ese stack.

**Stack real** (lo que va literal en `## Stack`, con versiones): una búsqueda en los catálogos y archivos de build, más un conteo de clases, sin recorrer el proyecto:

```bash
cd <raíz-del-proyecto> && grep -rhoE 'compose|viewbinding|databinding|appcompat|fragment|navigation-(compose|fragment)|navigation3|rxjava[23]?|rxandroid|kotlinx-coroutines|livedata|hilt|dagger|koin|retrofit|okhttp|ktor-client|volley|room|sqldelight|realm|datastore|coil|glide|picasso|epoxy|paging|moshi|gson|kotlinx-serialization|mockito|mockk|junit5|jupiter|robolectric|espresso|ksp|kapt' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' --include='gradle.properties' . | sort | uniq -c | sort -rn
cd <raíz-del-proyecto> && grep -rlE 'class \w+(Presenter|ViewModel|Interactor|Reducer|Store)\b' --include='*.kt' --include='*.java' . | sed -E 's/.*(Presenter|ViewModel|Interactor|Reducer|Store).*/\1/' | sort | uniq -c
```

Con eso anota: UI (Compose, Views con ViewBinding, DataBinding o `findViewById`), patrón de presentación (MVVM, MVP, MVI), asincronía (corrutinas y Flow, RxJava, LiveData, callbacks), DI (Hilt, Dagger 2, Koin, manual), navegación, red, persistencia, serialización y tests. Si conviven dos (Compose y XML, Rx y corrutinas), di cuál domina y dónde está cada uno. El perfil se aplica **en lo que coincide** con el proyecto; lo demás lo describe `## Arquitectura` tal cual está.

**Comandos y DoD.**
- Gradle: tareas propias del build (busca `tasks.register` en los `build.gradle.kts`, como `formatAndAnalyze`), o las estándar (`lint`, `test`, `assembleDebug`; `ktlintCheck` y `detekt` si sus plugins están aplicados).
- Node: los scripts de `package.json` (`lint`, `typecheck`, `test`, `build`) con el gestor que indique el lockfile (`pnpm`, `npm`, `yarn`).
- Python: `ruff`, `mypy` y `pytest` si están configurados en `pyproject.toml`.
- JVM: `./mvnw verify` o `./gradlew check build`.
- Si existe CI (`.github/workflows`), sus pasos de verificación confirman qué comandos usa el proyecto.

**Git y versionado.**
- Rama principal: `git symbolic-ref refs/remotes/origin/HEAD`, o la que exista entre `main` y `master`.
- Idioma y formato de los commits: los últimos 30 (`git log -30 --format=%s`).
- Tags: `git tag --sort=-v:refname | head` (¿con `v` o sin `v`?).
- `CHANGELOG.md`: formato, secciones e idioma.
- Dónde vive la versión (la misma tabla de `hb-release`), si hay notas de tienda y si un workflow crea tags o publica.

## 2. Pregunta solo lo que no se puede deducir

Haz todas las preguntas juntas y propone un valor por defecto:
- ¿La IA puede hacer commits? Por defecto: **no**; deja los cambios y entrega el mensaje.
- Si el historial mezcla idiomas: ¿en qué idioma van los commits y el changelog?
- Reglas propias que no aparecen en el código (datos sensibles, restricciones del negocio).

## 3. Escribe o actualiza

**Proyecto sin `AGENTS.md`:** créalo desde [assets/AGENTS.template.md](assets/AGENTS.template.md). Completa cada sección con lo detectado, quita las que no apliquen (por ejemplo, notas de tienda) y no dejes ningún `<placeholder>`. `## Stack` y `## Arquitectura` son una foto del proyecto: ni un patrón ni una librería que no estén en el código. `## Modernización` arranca en "ninguna decidida".

**Proyecto con `AGENTS.md`:** pásalo al estándar sin perder lo propio.
1. Conserva lo específico del proyecto: descripción del producto, excepciones, reglas de negocio, decisiones y sus motivos.
2. Reorganízalo en las secciones de la plantilla y agrega las que falten (sobre todo `## Stack` y `## DoD`).
3. Quita lo genérico que ya cubre el perfil (explicaciones de arquitectura, SOLID, testing o seguridad general). Antes de borrar bloques grandes, muestra qué sale y por qué.
4. Señala lo que se aparta de los estándares y propone el cambio sin aplicarlo: secciones de changelog no estándar (como `Enhancement`), tags sin `v`, commits sin Conventional Commits. Lo que se aparta del **perfil** (Views en vez de Compose, MVP, RxJava) no es un desvío: es el stack del proyecto; va en `## Stack` y, si el usuario quiere modernizarlo algún día, en `## Modernización` como candidato, sin plan ni fecha.

En los dos casos:
- **`CLAUDE.md`** con una sola línea, `@AGENTS.md`, salvo que tenga instrucciones propias de Claude que haya que conservar.
- **`reports/`** (lo usa `hb-implement`) debe estar ignorado por git. No edites `.gitignore` por tu cuenta: si falta, inclúyelo en el diff que muestras para aprobar, o deja la línea en `.git/info/exclude` (local).
- Mantén el `AGENTS.md` corto, idealmente por debajo de 150 líneas: los agentes lo cargan en cada sesión. Lo extenso va a `docs/` y se enlaza.

## 4. Verifica y entrega

1. Pregunta si quieres correr el DoD una vez para confirmar que los comandos funcionan (puede tardar). Si alguno falla, anótalo en la entrega.
2. Muestra el `AGENTS.md` final, o el diff si lo actualizaste, y la lista de desvíos de estándar encontrados. Si el stack es anterior al perfil, dilo en una línea y nada más: la modernización se conversa cuando el usuario la pida.
3. No commitees: propone el commit con `hb-commit` (por ejemplo `docs: agregar AGENTS.md con el estándar de agentes`).
