# Modelo de estructura

`## Estructura` de `AGENTS.md` dice **qué unidades tiene el proyecto y cómo se trabaja con cada una**. Lo leen todas las skills antes de tocar código (`hb-implement`, `hb-review`, `hb-performance`, `hb-commit`, `hb-release`) y lo corrigen si no coincide con lo que encuentran. Sirve igual para un repo con un solo módulo, un multimódulo en un repo o varios repos con dependencias publicadas.

**Una unidad** es una parte del proyecto que se cambia, se verifica y, a veces, se publica por separado: un módulo del build, un paquete de un espacio de trabajo, la carpeta de una feature en un proyecto de un solo módulo o un repo vecino.

## Cómo se arma

**Completo, pero barato.** Solo se lee: no compiles, no ejecutes la app ni el build para descubrir unidades o variantes. Arranca con el inventario del script, que no cambia nada:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py units
```

Imprime las unidades candidatas de este repo (módulos de Gradle, Maven, Cargo o Go, paquetes de un espacio de trabajo de npm, pnpm o Yarn y carpetas de feature), los repos vecinos clonados y **sin clonar** que nombra la configuración, los archivos versionados que hoy están modificados y nombran repos vecinos (candidatos a "Configuración local modificada a propósito") y, si `AGENTS.md` ya tiene `## Estructura`, lo que no coincide. Además: los archivos que pasan unidades a fuente con su patrón dominante y las entradas que no lo siguen, las dependencias del build del mismo grupo que no están en ellos, los repos vecinos en otro host que el principal y los scripts que sincronizan el espacio de trabajo, con sus acciones. Completa lo demás con las preguntas de abajo. Lo que no se pueda deducir se pregunta, junto con las demás preguntas del setup, una sola vez.

## Las seis preguntas

| # | Pregunta | Dónde va | Evidencia | Si falta |
| --- | --- | --- | --- | --- |
| 1 | ¿Qué unidades tiene el proyecto? | Columna "Unidad" | `contexto.py units`; `settings.gradle(.kts)` (`include`, `includeBuild`), `pnpm-workspace.yaml`, `workspaces` de `package.json`, `go.work`, `[workspace]` de `Cargo.toml`, `<modules>` de `pom.xml`, `.gitmodules`; en un solo módulo, las carpetas de feature (`features/<nombre>`, `feature/<nombre>`) | Pregunta cuáles se trabajan por separado. En un repo sin módulos ni features, la unidad es el repo entero |
| 2 | ¿Dónde está el fuente de cada una? | "Fuente" | La ruta en este repo; para un repo vecino, la ruta relativa que nombra la configuración (`../core-lib`) | Un vecino sin clonar: pregunta la URL de su remoto (va en "Repo y rama principal") |
| 3 | ¿Cómo se consume y cómo se pasa a fuente y se vuelve? | "Cómo se consume" y "Pasar a fuente y volver" | La declaración de la dependencia (catálogo de versiones, `package.json`, `go.mod`) y el mecanismo de sustitución que el proyecto ya usa ([repos-relacionados.md](repos-relacionados.md)) | Pregunta el cambio exacto para pasar a fuente y para volver. Sin ningún mecanismo, escribe "sin mecanismo" |
| 4 | ¿Cómo se verifica cada una? | "DoD de la unidad" | Las tareas del build acotadas a la unidad (`./gradlew :<módulo>:check`, `pnpm --filter <paquete> test`, `go test ./<carpeta>/...`), los filtros por ruta del CI; para un repo vecino, su propio `AGENTS.md` o `dod.py --repo <ruta>` en esa carpeta | Si el build no permite acotarlo, el `## DoD` del proyecto entero |
| 5 | ¿En qué repo vive, cuál es su rama principal y quién la publica y versiona? | "Repo y rama principal" y "Publica y versiona" | `git -C <repo> symbolic-ref refs/remotes/origin/HEAD`, `git -C <repo> remote get-url origin`, tags, `CHANGELOG.md`, archivos de versión y los workflows que publican | Pregúntalo una vez para todas las unidades |
| 6 | ¿Qué variantes y entornos hay, y cuál tiene servicios funcionales? | `### Variantes y entornos` | `buildTypes` y `productFlavors`, archivos `.env.*`, configuraciones por entorno, las URL base de cada variante, el `README` y las matrices del CI | Pregunta cuál tiene servicios funcionales y cuál se usa para probar y medir |

Además de las seis:

- **Cliente HTTP:** dónde se construye (el archivo y su unidad), hallado con una búsqueda según el stack, por ejemplo `git grep -n -E 'OkHttpClient\.Builder|Retrofit\.Builder|HttpClient\(|axios\.create|ky\.create|URLSession\(|requests\.Session|httpx\.(Async)?Client|http\.Client\{|reqwest::Client'`. Si hay más de uno, todos. Si el proyecto no hace llamadas HTTP, "ninguno".
- **Configuración local modificada a propósito:** los archivos versionados que quedan modificados en la máquina sin ser parte de ninguna tarea (por ejemplo, el archivo que pasa unidades a fuente). `contexto.py units` lista los candidatos; confirma cada uno con el usuario. Se registra **la ruta y el motivo**, nunca el contenido del momento.
- **Documentos:** cada documento extenso de la carpeta de docs, con una frase de "léelo cuando…". Así una skill lee solo el que su tarea necesita, por su ruta.

## Formato fijo

Va entre `## Arquitectura` y `## Modernización`, con estas subsecciones y en este orden. Las skills dependen de los nombres de las columnas y de las líneas, así que no los cambies.

```markdown
## Estructura

### Unidades

| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal | Publica y versiona |
| --- | --- | --- | --- | --- | --- | --- |
| `app-shell` | `.` | Es la app | — | `cd <ruta del proyecto> && ./gradlew :app:check` | este repo, `main` | la persona, con `hb-release` |
| `feature-payments` | `../feature-payments` | Publicada: `com.example:feature-payments`, versión fijada en `gradle/libs.versions.toml` | A fuente: `"feature-payments": true` en `local-modules.json`; volver: `false` | `cd <ruta del proyecto>/../feature-payments && ./gradlew check` | `https://git.example.com/team/feature-payments.git`, `main` | su repo: el workflow `publish` al crear el tag `vX.Y.Z` |
| `core-lib` | `../core-lib` | Publicada: `com.example:core-lib`, versión fijada en `gradle/libs.versions.toml` | A fuente: `"core-lib": true` en `local-modules.json`; volver: `false` | `cd <ruta del proyecto>/../core-lib && ./gradlew check` | `https://git.example.com/team/core-lib.git`, `main` | su repo: el workflow `publish` al crear el tag `vX.Y.Z` |

- El agente necesita **acceso a la carpeta** de cada unidad que está fuera del repo (cada agente tiene su forma de sumar directorios de trabajo). Si no puede leer una, lo dice y se detiene.
- Repos vecinos: clonar los que falten y preguntar la rama de trabajo.

### Variantes y entornos

| Variante o entorno | Para qué sirve | Servicios funcionales | Para probar y medir |
| --- | --- | --- | --- |
| `debug` | Desarrollo | Sí: backend de pruebas | Sí |
| `mock` | Demos sin red | No: respuestas simuladas | No |
| `release` | Tienda | Sí: producción | No |

### Cliente HTTP

- `../core-lib/src/main/kotlin/com/example/network/HttpClientFactory.kt` (unidad `core-lib`): OkHttp con los interceptores de autenticación y de logs.

### Configuración local modificada a propósito

- `local-modules.json`: dice qué unidades se usan en fuente en esta máquina. No es un cambio de ninguna tarea y no se commitea.

### Documentos

| Documento | Léelo cuando… |
| --- | --- |
| `docs/arquitectura.md` | Vayas a crear una feature o un módulo nuevo |
| `docs/pagos.md` | La tarea toque cobros, reembolsos o la integración con la pasarela |

### Mapas del módulo

- En `contexto/modules/<identificador>.md`, fuera de git. Antes de tocar una unidad, lee su mapa; si no existe, créalo; si su `Commit analizado` quedó atrás, actualízalo solo con el diff desde ese commit.
```

En un proyecto de un solo paquete con features por carpetas (por ejemplo, un espacio de trabajo pnpm), las filas serían así:

```markdown
| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal | Publica y versiona |
| --- | --- | --- | --- | --- | --- | --- |
| `packages/web` | `packages/web` | Es la app | — | `cd <ruta del proyecto> && pnpm --filter web test` | este repo, `main` | la persona, con `hb-release` |
| `packages/web/src/features/payments` | `packages/web/src/features/payments` | En fuente (carpeta de `packages/web`) | — | `cd <ruta del proyecto> && pnpm --filter web test -- src/features/payments` | este repo, `main` | con la app |
```

### Unidades

- **Unidad:** el identificador, entre acentos graves. Es la ruta de la unidad desde la raíz de su repo, con sus subcarpetas (`features/payments/impl`, sin aplanar). Un repo vecino entero se identifica por el nombre de su carpeta (`core-lib`); un módulo dentro de él, por `<carpeta del repo>/<ruta>`. El repo principal entero, cuando es una sola unidad, por el nombre de su carpeta.
- **Unidades anidadas.** Una unidad puede vivir dentro de otra (las carpetas de feature dentro de un paquete, los módulos dentro del repo). Un archivo es de la unidad cuya "Fuente" es la ruta más larga que lo contiene, así que conviene una fila también para la unidad que contiene a las demás (el paquete o el módulo de la app): de ella es lo que no cae en ninguna feature, como el cliente HTTP compartido.
- **Fuente:** la ruta relativa a la raíz del proyecto (`.`, `app/`, `../core-lib`). Nunca absoluta.
- **Cómo se consume:** "Es la app" (el repo entero, o en un multimódulo el módulo o paquete que se ejecuta), "En fuente (módulo del build)" (otro módulo o paquete del build), "En fuente (carpeta de `<unidad que la contiene>`)" (una carpeta de feature), o "Publicada: `<coordenada>`, versión fijada en `<archivo>`". El número de la versión no se escribe: cambia con cada bump y se lee del archivo.
- **Pasar a fuente y volver:** el cambio exacto para cada sentido, o "—" si la unidad siempre está en fuente, o "sin mecanismo" si es publicada y el proyecto no tiene forma de usar su código local.
- **DoD de la unidad:** el comando acotado, con `cd` a su repo (`./gradlew :<módulo>:check`, `pnpm --filter web test -- src/features/payments`, `go test ./<carpeta>/...`). Si no se puede acotar, "el `## DoD` del proyecto". Las skills corren además el `## DoD` del proyecto cuando el cambio toca la app, algo de ninguna unidad, un contrato que otras consumen o una unidad sin build propio.
- **Repo y rama principal:** "este repo" o la URL del remoto (sirve para clonarlo), y la rama principal.
- **Publica y versiona:** quién y cómo: "con la app", "la persona, con `hb-release`", "el workflow `<nombre>` al crear el tag".
- **Excepciones al patrón.** Si el archivo de sustitución (el que pasa unidades a fuente) sigue un patrón para las carpetas (`../{clave}`) y alguna entrada no lo sigue, la Fuente de esa unidad dice su carpeta real y, debajo de la tabla, una línea `- Excepciones: `<unidad>` vive en `<carpeta>`, fuera del patrón `<patrón>` de `<archivo>`.` `contexto.py units` las lista. Una dependencia del build del mismo grupo que no está en ese archivo, o un repo en otro host, se pregunta: si es una unidad, va en la tabla ("sin mecanismo" si no se puede pasar a fuente; la URL de su host en "Repo y rama principal").
- Debajo de la tabla, la línea de acceso a las carpetas y la línea **Repos vecinos**: `Repos vecinos: clonar los que falten y preguntar la rama de trabajo` (por defecto) o `Repos vecinos: no clonar ni crear ramas`. Con la primera, ninguna skill crea una rama por su cuenta: al empezar, pregunta una sola vez, para todos los repos que va a modificar, si sigue en la rama actual de cada uno o crea una nueva con el nombre que dé el usuario; si nadie responde, sigue en la actual. Ninguna hace `pull`, `merge` ni `rebase` para preparar la rama. Con la segunda, ninguna skill clona un repo ni crea ramas en ningún repo de la tarea, tampoco en el principal: propone el comando y sigue. Commit y push siguen las reglas de `## Git`. Al actualizar un `AGENTS.md` con la línea de antes (`clonar los que falten y crear ramas de trabajo`), cámbiala por la primera: las skills ya la leen así.

### Las demás subsecciones

- **Variantes y entornos:** una fila por variante o entorno. "Para probar y medir" dice cuál usan `hb-implement` para verificar y `hb-performance` para medir.
- **Cliente HTTP:** una línea por cliente, con el archivo (ruta desde la raíz del proyecto), la unidad y qué construye. "Ninguno" si no hay.
- **Configuración local modificada a propósito:** una línea por archivo, con su motivo. Se quita la subsección si no hay ninguno. Las skills no lo cuentan como cambio ajeno, no lo revisan como hallazgo y nunca lo proponen para commit.
- **Scripts de sincronización del espacio de trabajo:** si el proyecto tiene uno (clona, actualiza o cambia de rama en los repos vecinos), se resume en un doc (qué hace, cuándo se corre, sus reglas y qué puede borrar o pisar, como un `reset --hard`) con su fila en "Documentos". `contexto.py units` lo detecta con sus acciones. Ninguna skill lo corre para preparar la rama de trabajo: hace `pull` o `rebase`, y eso lo decide la línea `Repos vecinos`.
- **Documentos:** rutas explícitas a archivos, no a carpetas, para que nadie dependa de una búsqueda (con la carpeta de contexto enlazada, `rg` y `find` sin `-L` no entran al enlace). Si `AGENTS.md` tiene `## Producto` (de `hb-product`), el PRD tiene su fila tal como la imprime `contexto.py producto`: `<carpeta>/04-prd.md`, con la carpeta de su línea `Carpeta:` (o `product`), para leerlo antes de implementar una funcionalidad `F-…` o de cambiar el alcance del producto. La fila va aunque el PRD todavía no exista: solo se usa cuando hay funcionalidades `F-…`.
- **Mapas del módulo:** la línea que imprime `contexto.py preparar`, con la carpeta real y si van fuera de git o versionados.

## Mapas del módulo

Un mapa por unidad, con lo que un agente necesita saber antes de tocarla: qué hace, flujos, servicios que llama, patrones, su DoD y con qué tener cuidado. Plantilla: [assets/module-map.md](../assets/module-map.md).

- **Ruta:** `<carpeta de contexto>/modules/<identificador>.md`, con las subcarpetas del identificador (`modules/features/payments/impl.md`; para un repo vecino, `modules/core-lib.md`). La carpeta de contexto es `contexto/` en los modos local y externo, y `docs/` en el versionado.
- **Fuera de git por defecto**, con `.git/info/exclude` (nunca `.gitignore`). En los modos local y externo ya lo están, dentro de `contexto/`. Si el contexto se versiona, el setup pregunta una vez si los mapas también (`contexto.py preparar --module-maps versioned`) y lo deja escrito en la línea.
- **Se crean al trabajar, no en el setup:** la primera skill que toca una unidad sin mapa lo crea, en la ruta real de la carpeta de mapas (un archivo nuevo todavía no tiene ruta real propia).
- **`Commit analizado`** en la cabecera: el commit del repo de la unidad cuyo código describe el mapa. Si el `HEAD` de ese repo avanzó, se actualiza solo con `git -C <repo> diff <commit>..HEAD -- <ruta de la unidad>`, sin releer todo. Si el mapa describe cambios todavía sin commitear, lleva el commit de la base con la nota "(incluye cambios sin commitear de `<slug>`)", y se corrige cuando se commitean.

## Lo estable, no el momento

`## Estructura` describe cómo es el proyecto. Nunca escribas:

- salidas de `git status`, ramas actuales ni "hoy está modificado";
- números de versión que cambian con cada release (de una unidad en fuente o de la versión fijada: el modelo nombra el archivo donde se fija, no el número);
- fechas de "hoy", seriales de dispositivos ni rutas de la máquina.

Un archivo que queda modificado a propósito va en su subsección, con el motivo.

## Compatibilidad

Un `AGENTS.md` anterior tiene `### Repos relacionados` en `## Arquitectura`. Las skills leen `## Estructura` y, si no existe, esa subsección como respaldo. Al migrar con el setup, cada fila de `### Repos relacionados` pasa a la tabla de unidades (la ruta va en "Fuente"; el mecanismo, en "Cómo se consume" y "Pasar a fuente y volver") y la subsección se quita.

## Escribir sobre enlaces

Si `AGENTS.md` o la carpeta de contexto son enlaces simbólicos (modo externo), escribe en la ruta real (`realpath AGENTS.md`): algunas herramientas reemplazan un enlace por un archivo al guardar. En un `git worktree` los enlaces no existen, porque no están en git: `contexto.py estado` lo detecta y dice cómo recrearlos. No los crees sin que el usuario o el proyecto lo pidan.
