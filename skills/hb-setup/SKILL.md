---
name: hb-setup
description: 'Prepara un proyecto para trabajar con agentes: detecta el stack, los comandos, las convenciones de git y la estructura (unidades, repos vecinos, variantes), y crea o actualiza su AGENTS.md con la estructura estándar (Stack, Comandos, DoD, Arquitectura, Estructura, Reglas, Git, Versionado, Seguridad). Si el proyecto ya tiene contexto de IA (un AGENTS.md antiguo o renombrado, CLAUDE.md, reglas de otros agentes), lo migra con un inventario de traspaso: nada se pierde ni se inventa. El CLAUDE.md que lo importa solo se crea si el proyecto usa Claude Code, y el contexto de IA puede ir versionado, local o en una carpeta fuera del repo. Úsala al empezar un proyecto, cuando falte el AGENTS.md o para pasar uno existente al estándar ("crea el AGENTS.md", "configura el proyecto para los agentes", "actualiza el AGENTS.md", "migra el AGENTS.md al estándar", "/hb-setup").'
license: MIT
compatibility: "Requiere git. Para preparar el contexto de IA, Python 3.8+ solo con su librería estándar (en macOS viene con las Command Line Tools)."
metadata:
  author: hacybeyker
  version: "1.6.0"
  category: flow
---

# hb-setup

Deja el proyecto listo para `hb-implement`, `hb-review`, `hb-performance`, `hb-commit` y `hb-release`. El resultado es un `AGENTS.md` corto que contiene **solo lo propio del proyecto**: lo general vive en los perfiles `hb-stack-*`.

**El `AGENTS.md` describe el proyecto tal como es**, no como debería ser: su stack, su arquitectura y sus librerías reales, aunque sean anteriores a lo que recomienda el perfil (Views y XML, MVP, RxJava, Dagger 2, LiveData). Los agentes trabajan con ese stack. Modernizar es una decisión del usuario, que se toma después, por partes, y queda registrada en `## Modernización`; nunca la toma el setup ni una tarea cualquiera.

**Estándar:** [AGENTS.md](https://agents.md/), el formato abierto que leen Codex, Cursor, Copilot, Junie, Gemini CLI y otros. Es el único archivo que el setup siempre escribe. Claude Code lo lee a través de un `CLAUDE.md` que lo importa, que se crea solo si el proyecto lo usa (sección 3).

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

Con eso anota: UI (Compose, Views con ViewBinding, DataBinding o `findViewById`), patrón de presentación (MVVM, MVP, MVI), asincronía (corrutinas y Flow, RxJava, LiveData, callbacks), DI (Hilt, Dagger 2, Koin, manual), navegación, red, persistencia, serialización y tests. Si conviven dos (Compose y XML, Rx y corrutinas), di cuál domina y dónde está cada uno. El perfil se aplica **en lo que coincide** con el proyecto; lo demás lo describe `## Arquitectura` tal cual está. En otros stacks, la misma idea con sus archivos de dependencias (`package.json`, `pyproject.toml`, `go.mod`, `Package.swift`…).

**Versiones que no están en el repo.** Si el stack toma sus versiones de una fuente remota (un catálogo o BOM publicado, un plugin de convenciones), léelas de una copia local si la hay (por ejemplo, el repo del catálogo clonado al lado) y anota de dónde salen. Si no hay copia, anota la fuente remota sin inventar valores.

**Comandos y DoD.** El DoD es lo que de verdad hace fallar un PR. Lo arma el script de esta skill, sin inventar herramientas:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/dod.py
```

- **Con CI:** lee los workflows (`.github/workflows/*.yml`), las acciones compuestas locales que invocan (`uses: ./.github/actions/<nombre>`, su `action.yml`) y los workflows reutilizables (`uses: ./.github/workflows/<archivo>`, los de `workflow_call`), y junta todas las tareas de verificación que corren: lint, formato, análisis estático, tests, verificación de cobertura y el build. Cada una que pueda hacer fallar un PR entra en el DoD; las que no (una cobertura con mínimo 0, un análisis que necesita el token de un servicio externo, un reporte) van en la línea "Fuera del DoD" con su motivo.
- **Sin CI, el DoD nunca se omite ni queda vacío** (`perf.py cerrar --dod` de `hb-performance` y `hb-implement` cuentan con él): sale del build, en este orden: el formateador (si está configurado), los linters y el análisis estático configurados, los tests (si existen) y el build del artefacto principal. Sin nada de eso, compilar (o validar la sintaxis, si no hay build). Lleva una línea de origen ("Origen: DoD derivado del build; el proyecto no tiene CI ni tests"). **No agregues herramientas, tests ni CI para completarlo:** eso se decide en `## Modernización`.
- **La forma:** el formateador en su propia invocación y, después, **una sola invocación** con todos los checks, los tests y el build (`./gradlew a:check1 a:check2 a:test a:assemble`): así el formateo y los checks nunca corren en paralelo. Todos los comandos empiezan con `cd <ruta del proyecto> && …`. Es la forma que `perf.py cerrar --dod` corre paso por paso.
- Si el script no reconoce algo (tareas propias registradas con `tasks.register`, como `formatAndAnalyze`, un `Makefile`), complétalo a mano con la misma forma. En otros stacks, la misma idea: Node, los scripts de `package.json` con el gestor del lockfile; Python, `ruff`, `mypy` y `pytest` si están configurados; JVM, `./mvnw verify`.

**Git y versionado.**
- Rama principal: `git symbolic-ref refs/remotes/origin/HEAD`, o la que exista entre `main` y `master`.
- Idioma y formato de los commits: los últimos 30 (`git log -30 --format=%s`).
- Tags: `git tag --sort=-v:refname | head` (¿con `v` o sin `v`?).
- `CHANGELOG.md`: formato, secciones e idioma.
- Dónde vive la versión (la misma tabla de `hb-release`), si hay notas de tienda y si un workflow crea tags o publica.

**Contexto de IA.** El script de esta skill (la ruta es relativa a la carpeta de la skill) dice si `AGENTS.md` está versionado, excluido o enlazado a otra carpeta, si hay señales de Claude Code (`CLAUDE.md` o `.claude/`), los submódulos, los repos hermanos que el proyecto nombra como `../<nombre>` y, en un `git worktree`, los enlaces del contexto que faltan y cómo recrearlos:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py estado
```

**Fuentes previas de contexto de IA.** Antes de elegir el camino, busca todo el contexto de IA que el proyecto ya tiene, aunque no exista `AGENTS.md`: sus variantes renombradas (`AGENTS-old.md`, `AGENTS.bak.md`, `AGENTS.md.orig`), `CLAUDE.md`, `.github/copilot-instructions.md`, `.cursorrules` y `.cursor/rules`, y los `.md` de la carpeta de contexto (también si es un enlace, y las carpetas de la raíz enlazadas o en `.git/info/exclude`) que traen instrucciones para agentes. Con alguna, el camino es **migrar**; sin ninguna, **la plantilla**. El script solo lee (si la carpeta de contexto no se llama `contexto`, pásala con `--carpeta`):

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py fuentes [--carpeta <carpeta de contexto>]
```

Imprime las fuentes, los bloques y las secciones de otras skills que van tal cual, las skills locales que se solapan con una `hb-*` y el inventario de traspaso con un destino sugerido por sección: [migracion.md](references/migracion.md).

**Estructura.** El modelo de `## Estructura` responde seis preguntas: qué unidades tiene el proyecto, dónde está el fuente de cada una, cómo se consume y cómo se pasa a fuente y se vuelve, cómo se verifica, en qué repo vive y quién la publica, y qué variantes y entornos hay. Suma dónde se construye el cliente HTTP, la configuración local que queda modificada a propósito y el índice de documentos. **Solo lee y pregunta:** no compiles ni ejecutes nada para descubrirlo. Empieza con el inventario de solo lectura del script (unidades candidatas, repos vecinos clonados y sin clonar, archivos modificados que los nombran y lo que no coincide con el modelo actual; además, las entradas del archivo de sustitución cuya carpeta no sigue el patrón dominante, las dependencias del build que no están en él, los repos en otro host y los scripts que sincronizan el espacio de trabajo):

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py units
```

La evidencia de cada pregunta y qué preguntar si falta: [estructura.md](references/estructura.md). Para el mecanismo con el que el proyecto pasa una dependencia publicada a su código local: [repos-relacionados.md](references/repos-relacionados.md), sin asumir ninguno.

## 2. Pregunta solo lo que no se puede deducir

Haz todas las preguntas juntas y propone un valor por defecto:
- ¿La IA puede hacer commits? Por defecto: **no**; deja los cambios y entrega el mensaje.
- Si el historial mezcla idiomas: ¿en qué idioma van los commits y el changelog?
- ¿Usas Claude Code? Por defecto: **sí** si el proyecto tiene `CLAUDE.md` o `.claude/`; si no, **no**. Igual con el archivo propio de cualquier otro agente.
- ¿Se versiona el contexto de IA (`AGENTS.md`, sus docs y las salidas)? Por defecto: **sí**. Si no: **local** (en el repo, excluido de git) o en una **carpeta externa** que indicas ([contexto.md](references/contexto.md)).
- ¿Dónde van los reportes de las skills? Es una **base común**: `hb-implement` escribe en `<base>/implementation/<fecha>-<slug>/`, `hb-performance` en `<base>/performance/` y `hb-review` en `<base>/review/<fecha>-<slug>/`, y cada una deja su fila en `<base>/INDEX.md`. Por defecto: `reports`, o `contexto/reports` si el contexto no se versiona. ¿Cómo se arma el slug? Por defecto, el título en minúsculas con guiones (otra convención: `<ticket>-<descripción-corta>`). Una ruta con `{fecha}` y `{slug}` se sigue aceptando: `hb-implement` la usa tal cual.
- Si el contexto se versiona: ¿los mapas del módulo también? Por defecto: **no**, quedan en `.git/info/exclude`.
- ¿El agente puede clonar los repos vecinos que falten? Por defecto: **sí**. La rama de trabajo nunca la crea por su cuenta: al empezar cada tarea pregunta, una sola vez, si sigue en la rama actual de cada repo o crea una con el nombre que des, y sin respuesta sigue en la actual (`Repos vecinos: clonar los que falten y preguntar la rama de trabajo`). Si no quieres ni eso, la línea `Repos vecinos: no clonar ni crear ramas` lo apaga.
- Lo que el inventario de la estructura no resolvió ([estructura.md](references/estructura.md)): las unidades dudosas, la URL de cada repo vecino sin clonar, cómo pasar una unidad a fuente y volver, quién publica y versiona cada una, qué variante tiene servicios funcionales y cuál se usa para probar y medir, y si cada archivo modificado que nombra repos vecinos queda así a propósito.
- Si hay copias de `AGENTS.md` o `CLAUDE.md` (`AGENTS-old.md`, `AGENTS.md.orig`): ¿se conservan? Por defecto: **borrarlas después de migrar**, cuando `contexto.py verificar` pase. Los archivos de otros agentes (`GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`) no se borran: su contenido pasa al estándar y quedan como puntero a `AGENTS.md`, porque esa herramienta los sigue leyendo. "Documentos" nunca referencia ninguno.
- Lo que una fuente previa dice y contradice el código o el perfil: cuál vale. No lo decidas tú.
- ¿Hay reglas propias que quieras agregar (datos sensibles, restricciones del negocio)? Por defecto: **ninguna**; se escribe solo lo que digas, tal cual.

## 3. Escribe o actualiza

**Primero, el lugar del contexto.** Con las respuestas, prepara la estructura del modo elegido. El script no pisa ni borra nada: si algo lo impide (un `AGENTS.md` versionado o ya presente donde iría un enlace), no cambia nada y dice por qué.

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py preparar --modo <versionado|local|externo> [--externa <carpeta-fuera-del-repo>] [--reportes <ruta>] [--claude <si|no>] [--module-maps <local|versioned>]
```

Imprime dónde escribir `AGENTS.md` (en el modo externo, en la carpeta externa: escribe ahí, no sobre el enlace), dónde va lo extenso, las líneas `Contexto de IA` y `Carpeta de reportes` para `## Reglas del proyecto` y, para `## Estructura`, la línea de los mapas del módulo y un ejemplo de fila de "Documentos".

**Sin fuentes previas (camino plantilla):** crea `AGENTS.md` desde [assets/AGENTS.template.md](assets/AGENTS.template.md). Completa cada sección con lo detectado y las respuestas, quita las que no apliquen (por ejemplo, notas de tienda o `### Configuración local modificada a propósito`) y no dejes ningún `<placeholder>`: el resultado tiene que quedar completo y usable sin otra pasada. `## Stack` y `## Arquitectura` son una foto del proyecto: ni un patrón ni una librería que no estén en el código; las versiones que vienen de fuera del repo, con su fuente. `## Modernización` arranca en "ninguna decidida".

**Con fuentes previas (camino migrar), aunque no exista `AGENTS.md`:** el contenido de las fuentes pasa al estándar y nada se pierde en silencio. El detalle: [migracion.md](references/migracion.md).
1. **Inventario de traspaso.** Cada sección de cada fuente termina en uno de tres destinos: `AGENTS.md` (lo que se usa en casi todas las tareas, en su sección del estándar); un doc en la carpeta de docs del modo, con su fila en "Documentos" y un "Léelo cuando…" concreto (los errores del build con sus mensajes exactos, la publicación, la sincronización del espacio de trabajo, catálogos de rutas o deep links); o descartada con su motivo (obsoleta, contradice el código, ya la cubre un perfil `hb-stack-*` o una skill `hb-*`). Lo propio de una herramienta (por ejemplo, de Claude Code) puede quedarse en su archivo: el destino es su ruta. Parte de la tabla que imprime `contexto.py fuentes` y guárdala completa fuera del repo. Antes de reescribir una fuente en su lugar (`AGENTS.md`, `CLAUDE.md`, el archivo de otro agente), guarda una copia suya fuera del repo para `verificar --previo <ruta>=<copia>`; los punteros a `AGENTS.md`, mejor después de verificar.
2. **Lo de otras skills, tal cual.** Todo bloque entre `<!-- hb-<skill>:<nombre> -->` y `<!-- /hb-<skill>:<nombre> -->`, y las secciones propias de otras skills, se conservan **tal cual**, vengan del `AGENTS.md` o de una fuente renombrada. **Rendimiento:** corre `contexto.py rendimiento` (solo lee; también busca en las fuentes previas): el bloque `<!-- hb-performance:estado -->` lo mantiene `perf.py`, y las líneas de esa sección que traen un serial de dispositivo o contradicen el bloque ("Setup listo" con el setup en un parche) las señalas en tu resumen con el cambio propuesto: no reescribes esa sección por tu cuenta. **`## Producto` de `hb-product`:** corre `contexto.py producto` (solo lee; también en las fuentes previas): la sección va con su título y su contenido (de su línea `Carpeta:` lee `hb-product` su carpeta; sin ella, `product`), y la fila de `<carpeta>/04-prd.md` que imprime va en "Documentos", aunque el PRD todavía no exista. Sin esa sección no la creas.
3. **Nada inventado.** Nunca agregas por tu cuenta reglas propias del proyecto (migraciones de lenguaje o de librerías, convenciones de un equipo, excepciones): esas las escribe el usuario, a mano o pidiéndoselas a la IA. Solo conservas lo que ya está escrito en las fuentes previas de ese proyecto, tal cual y en la sección que corresponde del estándar. `## Modernización` sigue en "ninguna decidida" salvo que una fuente ya registre una decisión. Si una fuente contradice el código o el perfil, pregunta.
4. Conserva lo específico del proyecto (descripción del producto, excepciones, reglas de negocio, decisiones y sus motivos) y agrega las secciones que falten (sobre todo `## Stack`, `## DoD` y `## Estructura`). Lo genérico que ya cubre el perfil (explicaciones de arquitectura, SOLID, testing o seguridad general) se descarta con ese motivo en el inventario.
5. Señala lo que se aparta de los estándares y propone el cambio sin aplicarlo: secciones de changelog no estándar (como `Enhancement`), tags sin `v`, commits sin Conventional Commits. Lo que se aparta del **perfil** (Views en vez de Compose, MVP, RxJava) no es un desvío: es el stack del proyecto; va en `## Stack` y, solo si el usuario lo pide, en `## Modernización` como candidato, sin plan ni fecha.
6. **Una fuente que se reemplaza no se enlaza:** "Documentos" nunca la referencia, aunque se conserve.
7. **Skills locales que se solapan** con una `hb-*` (un protocolo de bugfix, una plantilla de reporte, una checklist de review): dilo en el resumen (qué cubre ya la skill, qué es propio del proyecto, que va a `AGENTS.md` o a docs) y propón retirarlas. No las borres.

En los dos casos:
- **`CLAUDE.md`, solo si corresponde:** si el proyecto ya tiene `CLAUDE.md` o `.claude/`, o el usuario confirmó que usa Claude Code. Una sola línea, `@AGENTS.md`, salvo que tenga instrucciones propias de Claude que haya que conservar. Si no corresponde, no se crea. El mismo criterio vale para el archivo propio de cualquier otro agente: si ya existe, queda como puntero a `AGENTS.md` (`@AGENTS.md` donde la herramienta importa archivos; si no, una línea que remita a él), nunca se borra por defecto.
- **`## Reglas del proyecto`** lleva siempre las líneas `Contexto de IA` y `Carpeta de reportes` que imprimió el script. `Carpeta de reportes` es la base común de `hb-implement`, `hb-performance` y `hb-review` (con `{fecha}` y `{slug}`, `hb-implement` la usa tal cual y las demás toman la parte fija como base).
- **`## Estructura`**, con el formato fijo de la plantilla ([estructura.md](references/estructura.md)): la tabla de unidades (también en un repo sin vecinos: sus módulos, o la carpeta de cada feature, o el repo entero), la línea de acceso a las carpetas de fuera del repo, la línea `Repos vecinos`, "Variantes y entornos", "Cliente HTTP", "Configuración local modificada a propósito" (ruta y motivo, nunca el contenido), "Documentos" (una fila por cada documento extenso, con su ruta y cuándo leerlo) y la línea de los mapas del módulo que imprimió el script. Si el `AGENTS.md` tenía `### Repos relacionados`, sus filas pasan a la tabla de unidades y esa subsección se quita.
- **Lo estable, no el momento:** `AGENTS.md` describe cómo es el proyecto. Nada de salidas de `git status`, ramas actuales, números de versión que cambian con cada release (el modelo nombra el archivo que fija la versión) ni fechas de "hoy". Un archivo que queda modificado a propósito va en su subsección, con el motivo.
- **La carpeta de reportes queda fuera de git:** el script la deja en `.git/info/exclude` (local). No edites `.gitignore` por tu cuenta: si el equipo lo prefiere ahí, inclúyelo en el diff que muestras para aprobar.
- **Archivos locales de las herramientas de IA:** si hay alguno sin versionar y sin ignorar (`.claude/settings.local.json`, `CLAUDE.local.md`, los de aider), `contexto.py preparar` lo agrega a `.git/info/exclude` (no toca `.gitignore`) y lo dice: nómbralo en tu resumen.
- **Nada de la máquina en `AGENTS.md`:** nunca escribas seriales de dispositivo (los comandos llevan `ANDROID_SERIAL=<serial>`) ni rutas de la máquina, salvo la ruta del proyecto en los `cd` de los comandos.
- **Sobre la ruta real:** si `AGENTS.md` o la carpeta de contexto son enlaces simbólicos, escribe en `realpath AGENTS.md` (y en la ruta real de cada archivo de la carpeta; para un archivo que todavía no existe, la ruta real de su carpeta): algunas herramientas reemplazan un enlace por un archivo al guardar. Si el enlace todavía no apunta a nada, escribe en la ruta que imprimió `contexto.py preparar`.
- Mantén el `AGENTS.md` por debajo de 150 líneas: los agentes lo cargan en cada sesión. Lo que no entra va a la carpeta de docs del modo (`docs/` si el contexto se versiona; `contexto/docs/` si no) y tiene su fila en "Documentos", con la ruta explícita del archivo (con la carpeta enlazada, `rg` y `find` sin `-L` no entran al enlace): nunca se omite.
- **Estructura más allá de la tabla:** las entradas del archivo de sustitución cuya carpeta no sigue el patrón dominante van como excepciones en `## Estructura`; una dependencia del build que no está en ese archivo o un repo en otro host es una unidad que se pregunta y, si lo es, va en la tabla ("sin mecanismo", con la URL de su host); un script de sincronización del espacio de trabajo se resume en un doc (qué hace, cuándo se corre, sus reglas y qué puede borrar o pisar) con su fila en "Documentos".

## 4. Verifica y entrega

1. Pregunta si quieres correr el DoD una vez para confirmar que los comandos funcionan (puede tardar). Si alguno falla, anótalo en la entrega.
2. **Con fuentes previas**, corre `contexto.py verificar --inventario <archivo>` (con `--previo <ruta>=<copia>` por cada fuente que reescribiste y no está en git, y `--fuente <archivo>` por cada una que pasaste a `fuentes`; los dos se repiten) hasta que no marque errores, y atiende sus avisos. Después deja como puntero a `AGENTS.md` los archivos de otros agentes y `CLAUDE.md`, con lo propio de esa herramienta. Muestra el inventario en el resumen, con las skills locales solapadas. Las fuentes que se reemplazan se borran solo si el usuario lo aprobó (la pregunta de la sección 2); las skills locales, nunca.
3. Corre `contexto.py estado` otra vez: el modo debe ser el elegido y, en local o externo, `git status` no debe mostrar `AGENTS.md`, `CLAUDE.md` ni la carpeta de contexto. Corre también `contexto.py units`: cada candidato está en `## Estructura` o lo descartaste con un motivo que dices en la entrega.
4. Muestra el `AGENTS.md` final, o el diff si lo actualizaste, y la lista de desvíos de estándar encontrados. Si el stack es anterior al perfil, dilo en una línea y nada más: la modernización se conversa cuando el usuario la pida.
5. No commitees: propone el commit con `hb-commit` (por ejemplo `docs: agregar AGENTS.md con el estándar de agentes`). En los modos local y externo no hay nada del contexto que commitear: dilo.
