# Sesión 0 · Setup (una vez por proyecto)

Deja el proyecto listo para medir. Las investigaciones siguientes lo reutilizan sin pagarlo de nuevo. Casi todo lo genera `perf.py instrumentar`; a ti te quedan los fragmentos que imprime. Propón todo junto, con la lista de archivos y una línea por archivo (no el diff entero en el chat), y espera aprobación. Presupuesto: 40 pasos; se gasta en leer archivos generados y en correr el DoD por partes, así que no lo hagas.

**Cuida el repo mientras trabajas.** Nunca uses `rm -rf` (ni borres carpetas enteras) dentro del repo: los archivos que `instrumentar` generó se quitan uno por uno, por su ruta, y lo que ya existía no se borra. Mira `git status --short` al empezar y otra vez antes del DoD: si aparece borrado o modificado algo que **tú** tocaste en esta sesión y no es parte del setup, restáuralo (`git restore <archivo>`) y dilo. Lo que ya estaba modificado al empezar es trabajo del usuario: no lo toques y, si estorba, pregunta.

**Primero, guarda el pedido.** El usuario llegó pidiendo medir algo, y esta sesión termina antes de medirlo. Escribe en `reports/perf/setup/pedido.json` lo que pidió, con sus palabras:

```json
{"flujo": "<de dónde a dónde y qué debe verse al final>", "llegar": "<lo que hay que pasar antes: login, términos, un tab; vacío si no hay nada>"}
```

`humo` lo lee al terminar e imprime el texto del chat de la sesión 1 con ese flujo ya escrito (el de flujo largo si `llegar` no está vacío). Sin ese archivo, el usuario tendría que escribir de nuevo lo que ya pidió. Si lo que pidió es el arranque en frío, no lo escribas: el arranque no necesita sesión 1 y `humo` ya ofrece su receta.

## Qué hace falta

| Pieza | ¿Obligatoria? | Para qué |
| --- | --- | --- |
| Variante `profileable`, no `debuggable`, con R8 como release (`profiling`, o una que el proyecto ya tenga) | Sí | Sin ella solo valen los conteos de red y las fugas |
| `reportFullyDrawn` en la primera pantalla | Recomendada | TTFD: el arranque hasta el contenido visible, no solo hasta el primer frame. También lo usa Android vitals |
| Secciones `SCREEN` (ciclo de vida de actividades y fragments) | Recomendada | Cuánto dura cada `onCreate`/`onResume` y qué pantalla precede a cada llamada |
| Secciones `HTTP`, `QUEUE`, `CONN` y `TTFB` | Si la app usa OkHttp (Retrofit, Ktor con motor OkHttp, Apollo) | Tiempos por endpoint, duplicados (con un hash de la query) y separar cola, conexión, servidor y cliente |
| Marcas `NAV` | Si la navegación no cambia de actividad (Compose, Navigation 3) | Saber en qué pantalla está el flujo |
| Marcas `MARK` (`PerfHooks.mark`) | En cada pantalla que se vaya a medir | Dónde termina lo que el usuario espera: el fin de las métricas de usuario y de la ventana del flujo |

Detecta el stack con una búsqueda y sin recorrer el proyecto:

```bash
cd <raíz-del-proyecto> && grep -rhoE 'okhttp|retrofit|ktor-client|apollo|fragment|appcompat|compose|navigation3|navigation-compose|hilt|koin|chucker|kover|jacoco|sonar' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' . | sort | uniq -c
```

## Build de profiling

**Reutiliza una variante que ya exista.** `perf.py instrumentar` busca las variantes profileable del módulo de dos maneras: los `src/<variante>/AndroidManifest.xml` con `<profileable>` (sin `android:enabled="false"`) y los build types que lo declaran en `build.gradle(.kts)` (`isProfileable = true`, o `profileable true` en Groovy), aunque su manifest no diga nada. Lee su build type: si no es depurable (no declara `isDebuggable = true` ni hereda de `debug`), la usa en lugar de crear `profiling` y lo dice en la línea `Variante: <nombre> (existente…)`. Entonces no se crea otro build type: solo el source set `perf` en `debug` y en esa variante, y el `<provider>` en su manifest. Con varias candidatas se detiene y pide `--variante <nombre>` (`--variante profiling` fuerza la propia); la que creó la skill gana. `release` y `debug` nunca son candidatas, aunque declaren `<profileable>`, **tampoco con sabores** (`demoRelease`, `freeDebug`: cualquier variante cuyo build type sea `release` o `debug`; un build type propio que el `build.gradle` del módulo declare con un nombre así, como `preRelease`, no cuenta; uno con ese nombre que no esté declarado ahí, por ejemplo porque lo genera un plugin, sí se rechaza), y `--variante` las rechaza igual: el source set `perf` y el `<provider>` en `release` instrumentarían el build que se publica. Las demás variantes con sabores, o con un build type que no se pueda leer, salen como "no pude verificar" y no se usan solas: revísalas tú y pásala con `--variante`: se usa como existente (sin `create(...)` de otro build type) y el script avisa que no pudo verificarla; si resulta depurable, `--variante` la rechaza. Donde esta guía dice `profiling` (`assembleProfiling`, `installProfiling`, `src/profiling/`, el mapping), léelo como la variante elegida; el `paquete` del plan es su `applicationId`, con su sufijo si lo tiene.

Si no hay ninguna, el comportamiento de siempre: el fragmento de `build.gradle.kts` lo imprime `perf.py instrumentar` (build type `profiling` con `initWith(release)` y firma de debug, el source set `perf` en `debug` y `profiling`, la exclusión de cobertura); en Groovy es lo mismo con su sintaxis. Los manifests de `debug` y `profiling` los genera el script. Revisa antes de proponerlo:

- **Firma e `applicationId`:** dos opciones. Sin sufijo, con la firma del build que ya está instalado en el dispositivo de pruebas, se instala encima y conserva los datos (sesión, base). Con `applicationIdSuffix = ".profiling"`, convive con los demás builds pero arranca sin datos: el `paquete` del plan es el id con el sufijo. Si no hay nada instalado, `install` es una instalación nueva y Android puede restaurar el backup de la nube: si la app se cae al abrir, revisa `firstInstallTime` y las exclusiones de backup.
- **Backend o mocks:** si el proyecto tiene un modo con datos simulados (un flag de `BuildConfig`, un interceptor de mocks), pregunta si el build de profiling lo usa: saca el backend de la medición y las métricas de usuario pasan a familia `app`. Sin mocks, con backend real, quedan en `e2e`.
- **Claves y secretos:** `initWith(release)` hereda los `buildConfigField` de release; confirma que las claves del ambiente estén en `local.properties` o en variables de entorno de esa máquina.
- **Firebase o Google Services:** si el plugin está aplicado, el build de profiling puede necesitar su propio `google-services.json` en `src/profiling/`.
- **CI:** si no quieres compilar `profiling` en CI, filtra la variante con `beforeVariants`.
- **R8:** los nombres salen ofuscados en CPU y heap. El mapping queda en `<módulo>/build/outputs/mapping/profiling/mapping.txt`.

### Atribución en Compose y con R8

La variante medida usa R8 y no trae nombres de composables por defecto. Sirve para medir; para saber **qué** función ocupa un frame largo hace falta algo más, y conviene saberlo antes del diagnóstico:

- **Con R8, las clases y los métodos salen ofuscados** en el muestreo de CPU (`--config cpu`), en las pilas de un crash y en los heap dumps. `perf.py` los desofusca solo (abajo, "Desofuscación automática"). Las secciones propias (`SCREEN`, `NAV`, `MARK`, `HTTP`) son texto y salen tal cual.
- **Sin composition tracing, la traza no nombra los composables:** se ve cuánto dura cada frame, no qué composable lo ocupa. La guía oficial de Android ([Composition tracing](https://developer.android.com/develop/ui/compose/tooling/tracing)) lo activa así:
  - la dependencia `androidx.compose.runtime:runtime-tracing` (pide Compose UI y compilador de Compose 1.3.0 o superior, y un dispositivo con API 30 o superior);
  - para capturar desde la terminal con Perfetto, además `androidx.tracing:tracing-perfetto` y `androidx.tracing:tracing-perfetto-binary`. Agrégalas **solo a la variante medida** (`"<variante>Implementation"`): la guía pide no publicar `tracing-perfetto-binary` con la app de producción por lo que pesa;
  - la fuente de datos `track_event` en la configuración de Perfetto: copia `assets/perfetto/base.pbtx` a la carpeta de la investigación y agrégale la fuente `track_event` tal como está en el ejemplo de la guía (`data_sources { config { name: "track_event" } }`, más lo que ese ejemplo traiga);
  - y, **con la app ya abierta** en la pantalla de partida, el broadcast que lo enciende en ese proceso: `adb -s <serial> shell am broadcast -a androidx.tracing.perfetto.action.ENABLE_TRACING <paquete>/androidx.tracing.perfetto.TracingReceiver`. Justo después, `capturar --prueba --config <archivo>`: la corrida de prueba no fija la compilación de ART, así que no detiene la app (con `--compilar` sí la detendría, y el proceso nuevo arrancaría sin el tracing encendido). Por lo mismo, que `preparar` no cierre ni relance la app en esa corrida (`--preparar true` lo reemplaza por un comando que no hace nada), y no sirve tal cual para un arranque en frío.

  Los nombres de los composables los escribe el compilador de Compose y, según esa guía, no se ofuscan; si la variante medida tiene la regla de R8 que la misma guía ofrece para quitarlos de producción (`-assumenosideeffects` sobre `androidx.compose.runtime.ComposerKt`), no van a salir. Es un cambio de dependencias: propónselo al usuario, úsalo en una corrida de diagnóstico y no lo mezcles a mitad de una investigación (si queda en el build, que esté igual en antes y en después). La skill no lo activa sola ni lo verificó en un dispositivo: si los nombres no aparecen, sigue la guía oficial.
- **Desofuscación automática.** Donde hay nombres de métodos (la tabla de `cpu_por_libreria`, la pila de un crash en `capturar` y en `salidas`), `perf.py` los pasa por `retrace` con el `mapping.txt` de la variante medida, y solo cuando aparece un nombre ofuscado:
  - **Qué mapping:** `--mapping <ruta>`; si no, `"mapping"` de `plan.json`; si no, el de la variante del comando `instalar` del plan (`:app:installProfiling` → `app/build/outputs/mapping/profiling/mapping.txt`; con R8 hay uno por variante, en el módulo de la app); si no hay `instalar`, el único del proyecto que no sea de `debug` ni de `release`. Si hay varios y no puede elegir, lo dice y no adivina.
  - **Que sea el del build medido.** Un mapping de otro build da nombres equivocados **sin ningún error**: por eso se verifica antes de usarlo. Si el mapping trae su identificador (`# pg_map_id:` en la cabecera) y el dispositivo todavía tiene instalado el build medido, se compara con el que R8 deja en el APK instalado (el marcador `pg-map-id` de sus `classes.dex`): si no coinciden, no se usa, tampoco con `--mapping`. Sin identificador comparable, se verifica por fechas y de forma conservadora: el mapping y el APK de salida de su variante no pueden ser posteriores a la instalación de la app. Si no se puede verificar, **avisa y no desofusca**, salvo que lo pases con `--mapping` (queda dicho en la salida que no se verificó).
  - **Herramienta:** `retrace`, de las Command-line Tools del SDK (necesita Java). Si falta, `perf.py` dice cómo instalarla y sigue sin desofuscar: Android Studio · SDK Manager · SDK Tools · "Android SDK Command-line Tools", o `sdkmanager "cmdline-tools;latest"`. La busca en el `PATH`, en `<sdk>/cmdline-tools/*/bin` y en `RETRACE=<ruta>`.
  - **Límites.** Un nombre suelto no trae número de línea, así que puede tener más de un candidato: salen separados por "o". Si después de aplicar el mapping siguen saliendo clases ofuscadas, o el archivo no tiene el formato de ProGuard/R8, el build usa otro ofuscador (ofuscadores comerciales con cifrado de clases) y el mapping no lo deshace: mide con una variante sin cifrado de clases. El código nativo sin símbolos se muestra como librería. Nunca falla por no tener mapping.
- **Si no se activa,** dilo en el diagnóstico: la causa dentro de Compose queda `sin confirmar`, y un síntoma estable puede ir como mejora a prueba ([diagnostico.md](diagnostico.md)). Para revisar el código de Compose sin la traza, `jetpack-compose-performance`.

### Proyectos que dependen del nombre del build type

Hay proyectos que eligen su configuración por el **nombre** del build type o del sabor: leen `BuildConfig.BUILD_TYPE` o `BuildConfig.FLAVOR` para buscar su ambiente, sus toggles o sus endpoints, o tienen lógica de Gradle por nombre (`name == "qa"`, `name.endsWith("Release")`, `name.contains(...)`). Un build type nuevo se llama distinto: esa configuración queda sin valor y la app puede no pasar del arranque o del login, sin que nada falle al compilar.

- **Antes de crear un build type, `instrumentar` lo busca** en el código y en los `build.gradle(.kts)`, y lo avisa con `archivo:línea`. Si no lo corriste todavía: `grep -rnE "BuildConfig\.(BUILD_TYPE|FLAVOR)" --include='*.kt' --include='*.java' .` y `grep -rnE "name *(==|\.(endsWith|startsWith|contains)\()" --include='*.gradle' --include='*.gradle.kts' .`.
- **Si aparece algo, y de verdad decide por un build type, un sabor o una variante** (la búsqueda es por texto: descarta lo que mire el nombre de otra cosa), **no crees otro build type:** mide sobre el que el proyecto ya usa para probar, activando la medición con una propiedad de Gradle. Con `-Pperf`, ese build type deja de ser depurable, pasa a profileable y suma el source set `perf` y el manifest con el `<provider>`; sin `-Pperf`, no cambia. `instrumentar` imprime el fragmento de ejemplo ("Alternativa recomendada"); como el build type solo es profileable con la propiedad, `instrumentar` no lo toma después por una variante existente (no le escribe manifest ni source set sin condición); se instala con `./gradlew :<módulo>:install<BuildType> -Pperf` y el `paquete` del plan es el de ese build type. Propónselo al usuario como la opción recomendada, con el motivo.
- **El botón de ejecutar del IDE no aplica la propiedad.** Android Studio compila e instala con sus propias tareas de Gradle y no pasa `-Pperf`, así que instala ese build type tal como es sin la propiedad: depurable y sin la medición activada (`capturar` avisa que el build es debuggable, y sus tiempos no valen; si el build type no es `debug`, tampoco trae el source set `perf` y las marcas no salen). La propiedad se puede agregar a mano en las opciones de línea de comandos del compilador del IDE (Settings · Build, Execution, Deployment · Compiler · Command-line Options), pero queda puesta para **todos** los builds que se lancen desde el IDE hasta que alguien la quite, también los que no son para medir: es fácil olvidarla. Recomendado: no tocar el IDE e instalar el build medido desde la terminal, con el comando de `instalar` del plan (`./gradlew :<módulo>:install<BuildType> -Pperf`), que es el que imprime `perf.py siguiente` antes de la medición después. Anótalo en la sección de rendimiento de `AGENTS.md`.
- **Si de todos modos se crea un build type,** revisa uno por uno los puntos que listó `instrumentar`, y ten presente que `initWith(...)` copia la configuración del build type pero **no su source set**: lo que haya en `src/<base>/` (su manifest, `res/`, archivos de configuración como un `google-services.json` o un JSON de ambiente) no llega al nuevo. `instrumentar` lista lo que encontró en `src/release/`: cópialo a `src/<variante>/` o haz que ese source set lo incluya, entero, no por partes.

### Lo que cambia al no ser depurable

La variante medida no es depurable, y hay comportamiento que depende de eso sin que se note hasta medir:

- **`<debug-overrides>` del `network_security_config` deja de aplicar.** Ese bloque solo vale en builds depurables: si ahí está la confianza en la CA de usuario de un proxy de pruebas (o un certificado propio del ambiente), la variante medida no confía en ella y las llamadas fallan. `instrumentar` busca `<debug-overrides>` en `res/xml` del módulo y lo avisa. Si las pruebas lo necesitan, propón una copia del archivo **solo para la variante medida** (`src/<variante>/res/xml/<archivo>`), con esas reglas en `<base-config>`; nunca en `main` ni en `release`. Lint puede pedir una excepción explícita para aceptar certificados de usuario: es esperable en esa copia, y no debe llegar a producción.
- **`BuildConfig.DEBUG` vale `false`,** y también el flag de depurable de la app (`ApplicationInfo.FLAG_DEBUGGABLE`). Revisa lo que cuelgue de ellos en el camino medido: logs, herramientas de depuración, endpoints o proxies de prueba, pantallas de configuración interna. `instrumentar` dice en cuántos lugares se lee `BuildConfig.DEBUG`.
- Lo mismo vale para la alternativa con `-Pperf`: el build type existente deja de ser depurable mientras se mide.

## Requisitos de la máquina

`perf.py` necesita `adb` (del SDK de Android) y `trace_processor` de Perfetto: el programa que abre una traza (`.perfetto-trace`) y permite consultarla con SQL; con él calcula frames, hilo principal, secciones de red y métricas. Si falta, cualquier comando que lo use se detiene con el comando de instalación, que no pide root (un script de Python en `~/.local/bin` que descarga el binario la primera vez). Si el entorno del usuario lo instala por su cuenta (un script de bootstrap), basta con que quede en el `PATH` o en `TRACE_PROCESSOR`. Compruébalo al empezar el setup, antes de tocar el proyecto:

```bash
cd ~ && (command -v trace_processor || echo "falta trace_processor") && adb version | head -1
```

Si falta, pásale al usuario este comando y espera a que lo corra:

```bash
cd ~ && mkdir -p ~/.local/bin && curl -fsSL https://get.perfetto.dev/trace_processor -o ~/.local/bin/trace_processor && chmod +x ~/.local/bin/trace_processor && { grep -qs '.local/bin' ~/.zshrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc; } && export PATH="$HOME/.local/bin:$PATH" && trace_processor --version
```

## Instrumentación y cableado

`perf.py instrumentar` copia las piezas genéricas al source set `perf` (y sus tests a `testDebug`) y **también el cableado**: `PerfHooks` en el código principal, los módulos de Hilt si detecta Hilt, los manifests de `debug` y `profiling` y `PerfInstaller` ya apuntando a los ganchos. No pisa nada que exista. Detecta OkHttp, Retrofit, fragments y Hilt; se fuerza con `--red`/`--sin-red`, `--retrofit`/`--sin-retrofit`, `--fragments`/`--sin-fragments`, `--hilt`/`--sin-hilt` y `--principal <src/main/...>`.

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py instrumentar --modulo app --paquete <paquete.de.la.app>.perf
```

Al final imprime, **con el paquete ya puesto**, los fragmentos que solo puedes pegar tú porque dependen del proyecto. No los reescribas ni leas los archivos generados: pega cada fragmento donde corresponde, con **una sola edición por archivo** (imports y código juntos; cada edición es un paso que reenvía el chat).

1. **`build.gradle.kts`:** el build type `profiling`, el source set `perf` en `debug` y `profiling`, la exclusión `**/perf/**` de la cobertura y, si una librería llega solo con `releaseImplementation` (una variante no-op, por ejemplo), su `"profilingImplementation"`: `initWith(release)` copia la configuración, no las dependencias.
2. **Red: el cableado lo aplicas tú en esta sesión, en todos los builders.** El código principal arma el `OkHttpClient` y no ve el source set `perf`; si nadie conecta el listener, no se mide la red y nada más lo delata hasta la prueba de humo. No se deja como pendiente ni como fragmento para que lo pegue el usuario: es parte del DoD del setup ([abajo](#red-conectar-cada-builder)).
3. **Navegación sin cambio de actividad:** `PerfHooks.navigation` con el destino tal cual (la ruta `movie/{id}` en Navigation Compose, la clave en Navigation 3), sin convertirlo a texto.
4. **Contenido visible:** si `instrumentar` imprimió candidatos ("el proyecto ya tiene un punto de extensión"), conecta las marcas ahí ([abajo](#contenido-visible-dónde-conectar-las-marcas)) y no edites pantallas. Si no, en la primera pantalla, `ReportDrawnWhen { !uiState.isLoading }` (Compose, activity-compose 1.7+) o `reportFullyDrawn()` (Views): es el TTFD y lo usa Android vitals. En **cualquier otra pantalla que se vaya a medir**, `PerfHooks.mark("<pantalla>")` una vez por carga, cuando el contenido real está a la vista: deja la marca `MARK <pantalla>`, donde terminan las métricas de usuario y la ventana del flujo. Sin ella, una métrica que termina en la última llamada de red deja afuera el render y cambia de significado si una mejora reordena las llamadas.
5. **Manifests existentes:** si `src/debug/AndroidManifest.xml` o `src/profiling/AndroidManifest.xml` ya existían, agrega el `<provider>` (y `<profileable>` en profiling) que imprime el script.
6. **Dependencias por variante, antes del DoD:** `grep -n "releaseImplementation\|debugImplementation" <módulo>/build.gradle*`; cada librería que solo llega en `release` (el no-op de Chucker, Flipper, LeakCanary) necesita su `"profilingImplementation"`, o `assembleProfiling` falla y el DoD se repite entero.
7. **Nada en `.gitignore`:** `reports/` queda fuera de git por `.git/info/exclude` (lo escriben `nuevo` y `humo`); si hace falta agregarlo, va ahí. El `.gitignore` es del proyecto y no se toca.

## Red: conectar cada builder

1. **Lista dónde se construyen los clientes**, en los módulos de la app y en los que `settings.gradle(.kts)` incluye desde otras carpetas (`instrumentar` ya imprime los que encontró, con `archivo:línea`, en el fragmento de red):
   ```bash
   cd <raíz-del-proyecto> && grep -rnE 'OkHttpClient\.Builder\(|OkHttpClient\(\)|\.newBuilder\(\)' --include='*.kt' --include='*.java' --exclude-dir=build --exclude-dir=test --exclude-dir='test[A-Z]*' --exclude-dir=androidTest --exclude-dir='androidTest[A-Z]*' --exclude-dir=testFixtures . | head -40
   ```
   `OkHttpClient.Builder(` y `OkHttpClient()` arman un cliente nuevo. `.newBuilder()` sobre un cliente deriva otro que **hereda** el listener del cliente base: basta con conectar el base (descarta los `.newBuilder()` de una `Request`, una URL o Retrofit).
2. **Una línea por builder, antes de `build()`**, con una sola edición por archivo (imports y código juntos):
   - **Con Hilt o Dagger:** inyecta el set `@PerfEventListeners` donde se arma el cliente y llama a `PerfHooks.applyEventListener(builder, factories)`. Es un helper estático de `PerfHooks` (`@JvmStatic`, en el código principal): aplica la primera factory del set solo si el set no está vacío, así que en release no hace nada. Sirve igual desde Kotlin y desde un módulo de DI escrito en Java.
   - **El comodín entre Kotlin y Java:** para Dagger, `Set<EventListener.Factory>` y `Set<? extends EventListener.Factory>` son tipos distintos. En Kotlin, la inyección se declara `Set<@JvmSuppressWildcards EventListener.Factory>`; en Java, `Set<EventListener.Factory>` exacto. Si no coinciden, Dagger falla al compilar diciendo que falta el binding del set.
   - **Sin Hilt:** `PerfHooks.okHttp(builder)` en Kotlin o `PerfHooks.applyOkHttp(builder);` en Java.
   - OkHttp admite un solo `eventListenerFactory`: si el builder ya tiene uno, combínalos en lugar de reemplazarlo.
3. **Compruébalo con una búsqueda, como parte del DoD:** cada archivo que arma un cliente tiene que llamar al gancho.
   ```bash
   cd <raíz-del-proyecto> && grep -rlE 'OkHttpClient\.Builder\(|OkHttpClient\(\)' --include='*.kt' --include='*.java' --exclude-dir=build --exclude-dir=test --exclude-dir='test[A-Z]*' --exclude-dir=androidTest --exclude-dir='androidTest[A-Z]*' --exclude-dir=testFixtures . | while read -r f; do grep -qE 'PerfHooks\.(okHttp|applyOkHttp|applyEventListener)' "$f" || echo "$f"; done
   ```
   La salida es la lista de archivos con un builder que **no** llama al helper (los source sets de test, también `src/testDebug`, donde la skill deja sus tests, quedan fuera): tiene que quedar vacía, salvo los que decidiste dejar fuera, anotados con su motivo. Un builder que ya tenía otro `eventListenerFactory` del proyecto no está conectado por eso: hay que combinarlos. Un archivo de un setup anterior que aplica la factory del set a mano (`factories.firstOrNull()?.let(::eventListenerFactory)`) también sale: está conectado, y conviene pasarlo al helper. `perf.py instrumentar` (al volver a correrlo), `humo` y la corrida de prueba hacen la misma comprobación: `humo` **falla** si la instrumentación de red está generada y el arranque no trae ninguna sección `HTTP`, y dice qué builders no llaman al gancho (si el arranque de la app de verdad no hace llamadas, `humo --sin-red`); `capturar --prueba` lo avisa.
4. **Nada se anota como hecho sin verificarlo.** Antes de escribir en `AGENTS.md` o en `estado.md` que el cliente HTTP "vive en una librería", "llega compilado" o "no es accesible", corre la búsqueda del punto 1 y cita su resultado (los `archivo:línea`, o que no devolvió nada en ninguna de las carpetas). Una conclusión así apaga la medición de red de todas las investigaciones que siguen: si no la comprobaste, no la escribas; déjala como "⚠ por confirmar", con lo que falta mirar.

## Contenido visible: dónde conectar las marcas

La marca `MARK <pantalla>` es donde terminan las métricas de usuario y la ventana del flujo. Elige dónde ponerla en este orden; el primero que exista gana, porque cada nivel inferior toca más archivos de producción:

1. **Un punto de extensión que el proyecto ya tiene** (lo detecta `instrumentar` en todos los módulos, sin leer lo que `No leer` prohíbe): una interfaz con nombre de contenido visible (`ScreenTracker`, `ContentReady`, `ScreenImpression`…) que recibe un multibinding de Hilt o Dagger, o un `CompositionLocal` equivalente. Con multibinding, **un solo archivo en el source set `perf`**: un módulo con `@Provides @IntoSet` cuya implementación llama a `PerfHooks.mark(<nombre que recibe>)`. `instrumentar` imprime ese override con la firma de la interfaz sin los valores por defecto (un override no puede repetirlos), con su tipo de retorno (y un `TODO` que debes reemplazar si no es `Unit`) y con `suspend` si lo lleva; con una interfaz Java, o una firma que no reconoce, imprime el esqueleto del módulo sin el método y dice que no pudo leerlo. El nombre de la marca es lo que reciba el gancho: el plan usa ese nombre (`MARK <nombre>`), y `humo` o la corrida de prueba lo muestran en "Secciones propias". Release no cambia: el multibinding ya existe en el código principal. Compruébalo antes (que `@Multibinds` o algún binding principal lo declare) y confirma que el gancho se llama **una vez por carga**, no por recomposición. Un gancho pensado para otra cosa (analítica de pantallas, por ejemplo) puede avisar varias veces por carga: entonces el binding de `perf` lleva la guarda, que recuerda la última pantalla marcada y no repite la marca hasta que cambie la pantalla o empiece una carga nueva. `humo` y la corrida de prueba lo detectan: avisan cuando una misma marca sale más de una vez sin una navegación en medio.
2. **Un punto común sin extensión:** una clase base de pantalla, el `Scaffold` o el contenedor del `NavHost` de la app, un `Fragment` base. Una sola llamada a `PerfHooks.mark` ahí, una vez por carga.
3. **Pantalla por pantalla**, como último recurso: `PerfHooks.mark("<pantalla>")` donde el contenido real ya está a la vista (una línea por pantalla medida; solo las que se miden).

Cuando no hay nada de esto, `PerfHooks` es el punto de extensión: vive en el código principal sin efecto en release y solo `PerfInstaller` (debug y la variante de profiling) lo apunta a la traza. No inventes una interfaz nueva en producción para esto salvo que el usuario lo pida.

### Proyectos de varios módulos

La instrumentación (`PerfHooks`, `PerfInstaller`, el source set `perf`, la variante) va **solo en el módulo que genera el APK** (el que aplica `com.android.application`; normalmente `app`: `--modulo app`), no en el módulo de la feature que se va a medir: es el único que se instala y el único que ve a todos. `instrumentar` lista los módulos que encuentra (aplicación y librerías) para que lo confirmes. Una pantalla de un módulo library no puede llamar a `PerfHooks` (el módulo app depende de ella, no al revés), así que emite la marca por una interfaz que sí ve:

- **Si el proyecto ya tiene un punto de extensión** (nivel 1 de arriba), no hace falta nada en las librerías: el binding vive en `app/perf` y recibe lo que ellas ya emiten.
- **Si no, y las pantallas medidas viven en una librería:** `instrumentar` imprime el puente: un `object ContentVisible` con un `onVisible` vacío en un módulo del que dependan las librerías, `ContentVisible.mark("<pantalla>")` en las pantallas y una línea en `Application.onCreate` del módulo app que lo apunta a `PerfHooks.mark`. Es código de producción sin efecto en release: propónselo al usuario antes de agregarlo, y solo para las pantallas que se miden.
- **Red:** el gancho de OkHttp también vive en el código principal de la app. Si el `OkHttpClient` se arma en un módulo library del proyecto (`instrumentar` lo avisa con `archivo:línea`), ese módulo no ve `PerfHooks` y esas llamadas salen sin secciones `HTTP`. Dilo en el plan, mide sin ellas o con `perf.py har` (Chucker, [medicion.md](medicion.md)), y no muevas el gancho a la librería sin que el usuario lo decida.
- Las variantes de las librerías se resuelven con `matchingFallbacks` (ver el fragmento de Gradle); el `paquete` del plan es el de la app.
- **Módulos fuera de la raíz** (cada módulo en su repo, un build incluido): `instrumentar` sigue lo que `settings.gradle(.kts)` incluye desde otras carpetas (`project(":x").projectDir = file("../x")`, `includeBuild("../x")`) y busca ahí también los puntos de extensión, los `OkHttpClient.Builder()` y la lógica por nombre; dice en qué carpetas buscó. Solo sigue rutas literales en esas tres formas (`file("…")`, `File(<dir>, "…")`, `includeBuild("…")`); una ruta armada con variables o de otra manera no la puede seguir: imprime esa línea para que busques a mano en esa carpeta (una interfaz de pantalla o de contenido con multibinding, y dónde se arma el cliente HTTP), sin recorrer el disco entero.

### OkHttp dentro de una librería publicada

Si el proyecto no arma el `OkHttpClient` (lo trae armado una librería o un SDK que llega compilado), `instrumentar` no encuentra ningún `OkHttpClient.Builder()` y lo avisa: no hay dónde llamar al gancho. Antes de darlo por cierto, corre la búsqueda de [Red: conectar cada builder](#red-conectar-cada-builder) también en los módulos de fuera de la raíz: que un módulo llegue publicado no quiere decir que el cliente se arme ahí.

- **Si la librería acepta piezas desde afuera** (un parámetro de su configuración, un multibinding que ella misma inyecta), pásale desde el source set `perf` un `EventListener.Factory` (el de la skill: da `HTTP`, `QUEUE`, `CONN` y `TTFB`) o, si solo acepta interceptores, un `Interceptor` propio que abra y cierre una sección `HTTP <método> <ruta>` por llamada: da la duración de cada llamada y los duplicados, sin separar la cola, la conexión y el servidor.
- **Si no acepta ninguna, no la fuerces** (ni reflexión ni reemplazar su cliente): dile al usuario, con claridad, que **las métricas de red serán solo de punta a punta**. Sin secciones `HTTP` no hay tiempos por endpoint ni conteo de llamadas: quedan las métricas de usuario (de la acción a la marca de contenido, en familia `e2e`) y, para contar llamadas y duplicados en un build depurable, `perf.py har` con Chucker ([medicion.md](medicion.md)). Anótalo en la ficha, para que el diagnóstico no busque lo que no está.

### Cambios temporales: marcas en módulos que no ven `PerfHooks`

Para una investigación local, cuando la pantalla vive en un módulo (o en otro repo) que no ve `PerfHooks`, no hay punto de extensión y no se justifica el puente, la marca puede ir directo con la API de la plataforma, como cambio **temporal**:

```kotlin
// TEMPORAL (hb-performance): quitar antes del commit
view.doOnPreDraw {
    android.os.Trace.beginSection("MARK <nombre>")
    android.os.Trace.endSection()
}
```

- El nombre lleva el formato `MARK <nombre>`, igual que `PerfHooks.mark`: el plan, la ventana y las consultas la tratan como cualquier otra marca. Va una vez por carga, donde el contenido real ya está a la vista.
- No tiene la guarda de `PerfHooks`: queda en cualquier build que se compile con ella. Por eso es temporal: no se commitea, y se revierte al cerrar la investigación.
- Anota cada uno en "Cambios temporales por revertir" de `estado.md`, con el archivo y el repo o el módulo: en un proyecto de varios repos, el `git status` de la raíz no los muestra todos, y es fácil dejar uno puesto.
- **El inventario incluye también las ediciones de cableado en código de `main`** que no se commitean con el setup: la línea del gancho de red en el módulo que arma el cliente HTTP, una llamada a `PerfHooks.mark` en una pantalla, el puente de contenido visible. Son las más fáciles de olvidar, porque no llevan el comentario `TEMPORAL` y parecen código del proyecto.
- **Guárdalos como parche fuera del repo, uno por repo,** para poder quitarlos antes de un commit y volver a ponerlos al seguir midiendo (`estado.md` trae los comandos en esa sección):
  ```bash
  cd <repo> && git diff --binary -- <archivos> > <carpeta-fuera-del-repo>/<nombre>.patch && git apply --check -R <carpeta-fuera-del-repo>/<nombre>.patch
  cd <repo> && git apply -R <carpeta-fuera-del-repo>/<nombre>.patch    # quitar
  cd <repo> && git apply <carpeta-fuera-del-repo>/<nombre>.patch       # volver a aplicar
  ```
  `git apply --check -R` confirma que el parche revierte limpio antes de confiar en él. Un archivo nuevo solo entra en `git diff` después de `git add -N <archivo>`; al quitar el parche, sácalo también del índice (`git reset -q -- <archivo>`), o `git status` lo sigue mostrando como borrado. Anota la ruta del parche en la fila del inventario.
- Lo mismo vale para una marca que se pone solo para distinguir dos caminos del código durante el diagnóstico, o para marcar el inicio de una acción que no navega ([ficha.md](ficha.md)).

#### Reglas para una marca puesta por un agente

Una marca mal puesta mide otra cosa sin que nada falle. Si la pone un agente (tú, o uno más económico al que se le delega), estas reglas van en el pedido, y la corrida de prueba las comprueba ("Marcas del plan" y el aviso de marcas repetidas):

- **Con RxJava, el inicio de una llamada va en `doOnSubscribe`,** no en el cuerpo del método que arma el `Single` (o el `Observable`): ese método solo construye la cadena y puede correr mucho antes de que alguien se suscriba, o una sola vez para varias suscripciones. El fin va en `doOnTerminate` (o `doFinally`, si también importa la cancelación), no en el `subscribe` de quien la consume. Con corrutinas, el equivalente es dentro de la función `suspend`, antes y después de la llamada, no donde se lanza la corrutina.
- **El regreso desde otra app sin callback de resultado** (se detecta en `onResume`, porque no hay `onActivityResult` ni `onNewIntent`) necesita un flag: se arma justo antes de lanzar la otra app y se consume **una sola vez** en el primer `onResume` que lo encuentra armado. Sin el flag, cualquier `onResume` (volver de un diálogo del sistema, de la pantalla apagada) emite la marca.
- **Un flag armado por una navegación es propio del flujo, no de cualquier navegación:** se arma en la acción que inicia el flujo medido (el toque que lo dispara), no en un punto por el que pasan otras navegaciones a la misma pantalla. Si no, la marca sale también cuando el usuario llega por otro camino, y `cual: primera` o `cual: ultima` terminan eligiendo la equivocada.
- **Una marca puede ir en cualquier hilo:** las secciones propias (`MARK`, `NAV`, `SCREEN`, `HTTP`…) se leen de todos los hilos del proceso, no solo del principal, así que no hay que saltar al hilo principal para marcar (hacerlo agregaría el retraso de ese salto a la métrica).
- Cada marca va **una vez por carga**, con un nombre que diga qué pasó (`operacion_inicio`, `autorizacion_salida`), y se anota en el inventario con su archivo.

### Pantallas con Views y RxJava

`ReportDrawnWhen` es de Compose. Con Views, la marca va donde el contenido real ya está a la vista, **una vez por carga** (no en cada navegación ni en cada bind), y nunca en la capa de red:

| Pantalla | Dónde va la marca |
| --- | --- |
| `WebView` | En `onPageFinished`, dentro de `postVisualStateCallback` (API 23+): cuando el DOM ya se pintó; `onPageFinished` solo dice que terminó de cargar |
| `RecyclerView` con `ListAdapter` | En el callback de `submitList(items) { ... }`, con `recyclerView.doOnPreDraw { PerfHooks.mark("<pantalla>") }` |
| `RecyclerView` con otro adapter | Después de `notifyDataSetChanged()`, con `doOnPreDraw` |
| Epoxy (armado asíncrono de modelos) | En el listener de fin de armado del controller (`addModelBuildListener`, que avisa en `onModelBuildFinished`), con `recyclerView.doOnPreDraw { PerfHooks.mark("<pantalla>") }` y la bandera de una vez por carga. No después de pedir el armado (`requestModelBuild()`, `setData(...)`) ni al ocultar el cargando: los modelos se arman en otro hilo y la marca saldría antes de que la lista esté completa |
| RxJava (o MVP con Presenter) | En el `onSuccess` o `onNext` que ya corre en el hilo principal (`observeOn(AndroidSchedulers.mainThread())`), después de entregar los datos a la vista o al adapter; una bandera `marked` que vuelve a `false` cuando empieza una carga nueva |
| Primera pantalla | `reportFullyDrawn()` cuando el adapter recibe los datos (TTFD) |

`instrumentar` imprime estas recetas con el código solo si el proyecto usa `WebView`, `RecyclerView` o RxJava. El diagnóstico de ese stack está en [patrones/vistas.md](patrones/vistas.md) y [patrones/rxjava.md](patrones/rxjava.md).

**Actualizar la instrumentación** cuando cambia la skill: `instrumentar --actualizar` sobrescribe solo los archivos que llevan su encabezado "Generated by hb-performance"; lo que escribió el proyecto no se toca. Cada archivo generado guarda una huella de su contenido en la línea que sigue al encabezado (`hb-performance fingerprint: …`; no depende del formato, así que el formateador del proyecto no la cambia). Con ella, `--actualizar` distingue tres casos: el archivo ya está al día (no lo reescribe), es de otra versión de la plantilla y nadie lo tocó (lo actualiza) o **alguien lo editó a mano** (no lo pisa: lo lista con `✖ no se actualiza` y sigue con los demás). Un archivo generado por una versión anterior a 0.8.0 no tiene huella: si no es igual a la plantilla actual, tampoco se pisa, porque no se puede saber si lo editaron (la primera actualización desde una versión anterior necesita `--forzar` para los archivos cuya plantilla cambió). Mientras quede alguno sin actualizar, los archivos nuevos de la versión no se crean (`· sin crear todavía`), porque pueden depender de él. Para reemplazarlos, revisa antes la diferencia (`git diff`) y repite con `--actualizar --forzar`: pisa el archivo y deja lo que había en `<archivo>.orig`, para volver a aplicar lo propio; esa copia se borra después y no se commitea. Si un archivo generado necesita un cambio que sirve a cualquier proyecto, no lo edites: dilo, para que entre en la plantilla. Actualiza la instrumentación **entre** investigaciones, no a mitad de una: la plantilla de red puede cambiar el nombre de un endpoint (por ejemplo, al normalizar más segmentos como `{id}`) y `antes` y `después` dejarían de llamarlo igual.

## DoD del setup

Dos invocaciones de Gradle, no una: el formateador primero y solo, porque Gradle corre las tareas en paralelo y `ktlintCheck` puede correr antes que `ktlintFormat`. Después, los comandos de `## DoD` más `assembleProfiling`, **en un solo comando** con el log en un archivo y al chat solo el resumen:

```bash
cd <raíz-del-proyecto> && ( ./gradlew -q <formateador, p. ej. app:ktlintFormat> > reports/perf/setup/logs/formato.log 2>&1; code=$?; echo "exit $code"; exit $code )
cd <raíz-del-proyecto> && ( ./gradlew -q <tareas del DoD> app:assembleProfiling > reports/perf/setup/logs/dod.log 2>&1; code=$?; grep -E "FAILED|e: |error:|BUILD|tests completed" reports/perf/setup/logs/dod.log | head -20; echo "exit $code"; exit $code )
```

Cada comando **termina con el código de salida de Gradle** (el `exit $code` del subshell): un `; echo` o un `| tee` al final lo taparían con un 0, y un DoD roto se leería como verde. Si lo armas con una tubería, pon antes `set -o pipefail`. El DoD pasó solo si el comando terminó en 0 y el log no tiene `FAILED`: no lo des por bueno por no ver errores en el resumen.

El DoD del setup incluye además la comprobación del cableado de red ([Red: conectar cada builder](#red-conectar-cada-builder), punto 3): la búsqueda no puede listar ningún builder sin conectar.

Si falla, arregla y repite el segundo comando entero: una sola pasada más. Las plantillas vienen con los imports en el orden por defecto de ktlint (`java.*` al final) y dentro de los límites por defecto de detekt; el formateador ajusta el resto (comas finales, saltos de línea).

## Prueba de humo

Valida de una vez `SCREEN`, `NAV`, `HTTP`, TTID y TTFD con una corrida de arranque en frío, sin crear una investigación. La corre el usuario, con el dispositivo conectado; tú solo le das los comandos:

```bash
cd <raíz-del-proyecto> && <comando que instala el build de profiling, con el serial> && python3 -I <carpeta-de-la-skill>/scripts/perf.py humo --paquete <applicationId-instalado> --serial <serial> --instalar "<ese mismo comando de instalación>"
```

Con más de un dispositivo (`adb devices`), el serial va en la instalación (`adb -s <serial> install -r <apk>` o `ANDROID_SERIAL=<serial> ./gradlew app:installProfiling`) y en `--serial`. `humo` no fija la compilación de ART (es una corrida de prueba: valida marcas, no compara tiempos) y falla si la red está instrumentada y no sale ninguna sección `HTTP` ([Red: conectar cada builder](#red-conectar-cada-builder)). `humo` imprime las métricas, las secciones agrupadas y el paso siguiente: el texto exacto del chat de la sesión 1 con el flujo de `reports/perf/setup/pedido.json` (el de flujo largo si hay login u otras pantallas antes), y la receta `nuevo --receta arranque-frio` solo como opción, rotulada "si lo que quieres medir es el arranque en frío". La prueba de humo usa un arranque porque es lo más corto que ejercita todas las secciones, no porque el arranque sea lo que se va a investigar. Si falla: el paquete instalado (con su sufijo), Android 10 o superior, el manifest de `profiling` fusionado, que el código principal pase por los ganchos y, sin `ttfd_ms`, el `reportFullyDrawn`.

## Cierre del setup

- Agrega a `AGENTS.md` una sección con el encabezado **en el idioma del archivo**: mira los demás encabezados (`## Comandos`, `## Reglas del proyecto` → `## Rendimiento`; `## Commands`, `## Rules` → `## Performance`) y no mezcles. De 10 líneas como máximo: `applicationId`, cómo instalar el build de profiling (con el serial como `ANDROID_SERIAL=<serial> ./gradlew ...`; Gradle no tiene `-s <serial>`), qué secciones hay, dónde está el `reportFullyDrawn` y "setup listo". Si el proyecto se usa como prueba a ciegas, una línea `No leer: <rutas o patrones separados por comas>` (por ejemplo `docs/ALCANCE-*, casos/`) o `No leer:` con una viñeta por ruta en las líneas siguientes, sin línea en blanco en medio: todas las sesiones la respetan ([SKILL.md](../SKILL.md) · regla 15). Los patrones se comparan con la ruta desde la raíz del proyecto: `ALCANCE-*` solo cubre la raíz, `docs/ALCANCE-*` esa carpeta y `**/ALCANCE-*` cualquiera. Sin `AGENTS.md`, propón crearlo solo con esa sección (u ofrece `hb-setup`).
- Propón commitearlo en **su propio PR** (por ejemplo `build(perf): agregar el build de profiling y la instrumentación de rendimiento`). Si el equipo no acepta herramientas de medición en el repo, guárdalo como parche en una carpeta no versionada y aplícalo con `git apply` al investigar. En ese caso, la línea de `AGENTS.md` no puede decir solo "setup listo": tiene que decir cómo reaplicarlo ("setup listo, en parche: `git apply <ruta>/perf-setup.patch` antes de medir"), porque el código no va a estar en el repo cuando otra sesión lo lea. `humo` y `nuevo` lo comprueban: si `AGENTS.md` dice "setup listo" y no encuentran `PerfHooks.kt` en el repo, lo avisan y citan esa línea.
- **Siguiente paso**, al final de tu respuesta y como último bloque: el comando de instalación y `perf.py humo`, completo y listo para copiar, y una línea que diga que `humo` imprime lo que sigue (el texto del chat de la sesión 1, con su flujo) y que **eso va en un chat nuevo**. La sesión 0 termina ahí: nunca cierres con "dime el resultado y seguimos" ni invites a volver a este chat, y no corras `perf.py siguiente`, porque el setup no tiene carpeta de investigación. Anota el costo de esta sesión con `perf.py consumo` cuando haya carpeta; si todavía no la hay, dile al usuario el comando para anotarlo después.
