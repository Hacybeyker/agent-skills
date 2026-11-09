# Sesión 0 · Setup (una vez por proyecto)

Deja el proyecto listo para medir. Las investigaciones siguientes lo reutilizan sin pagarlo de nuevo. Casi todo lo genera `perf.py instrumentar`; a ti te quedan los fragmentos que imprime. Propón todo junto, con la lista de archivos y una línea por archivo (no el diff entero en el chat), y espera aprobación. Presupuesto: 40 pasos; se gasta en leer archivos generados y en correr el DoD por partes, así que no lo hagas.

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

**Reutiliza una variante que ya exista.** `perf.py instrumentar` busca en el módulo los `src/<variante>/AndroidManifest.xml` con `<profileable>` (sin `android:enabled="false"`) y lee su build type en `build.gradle(.kts)`: si no es depurable (no declara `isDebuggable = true` ni hereda de `debug`), la usa en lugar de crear `profiling` y lo dice en la línea `Variante: <nombre> (existente…)`. Entonces no se crea otro build type: solo el source set `perf` en `debug` y en esa variante, y el `<provider>` en su manifest. Con varias candidatas se detiene y pide `--variante <nombre>` (`--variante profiling` fuerza la propia); la que creó la skill gana. Las variantes con sabores o con un build type que no se pueda leer salen como "no pude verificar" y no se usan solas: revísalas tú y pásala con `--variante`. Donde esta guía dice `profiling` (`assembleProfiling`, `installProfiling`, `src/profiling/`, el mapping), léelo como la variante elegida; el `paquete` del plan es su `applicationId`, con su sufijo si lo tiene.

Si no hay ninguna, el comportamiento de siempre: el fragmento de `build.gradle.kts` lo imprime `perf.py instrumentar` (build type `profiling` con `initWith(release)` y firma de debug, el source set `perf` en `debug` y `profiling`, la exclusión de cobertura); en Groovy es lo mismo con su sintaxis. Los manifests de `debug` y `profiling` los genera el script. Revisa antes de proponerlo:

- **Firma e `applicationId`:** dos opciones. Sin sufijo, con la firma del build que ya está instalado en el dispositivo de pruebas, se instala encima y conserva los datos (sesión, base). Con `applicationIdSuffix = ".profiling"`, convive con los demás builds pero arranca sin datos: el `paquete` del plan es el id con el sufijo. Si no hay nada instalado, `install` es una instalación nueva y Android puede restaurar el backup de la nube: si la app se cae al abrir, revisa `firstInstallTime` y las exclusiones de backup.
- **Backend o mocks:** si el proyecto tiene un modo con datos simulados (un flag de `BuildConfig`, un interceptor de mocks), pregunta si el build de profiling lo usa: saca el backend de la medición y las métricas de usuario pasan a familia `app`. Sin mocks, con backend real, quedan en `e2e`.
- **Claves y secretos:** `initWith(release)` hereda los `buildConfigField` de release; confirma que las claves del ambiente estén en `local.properties` o en variables de entorno de esa máquina.
- **Firebase o Google Services:** si el plugin está aplicado, el build de profiling puede necesitar su propio `google-services.json` en `src/profiling/`.
- **CI:** si no quieres compilar `profiling` en CI, filtra la variante con `beforeVariants`.
- **R8:** los nombres salen ofuscados en CPU y heap. El mapping queda en `<módulo>/build/outputs/mapping/profiling/mapping.txt`.

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
2. **Red:** el código principal arma el `OkHttpClient` y no ve el source set `perf`. Con Hilt, inyecta `@PerfEventListeners Set<@JvmSuppressWildcards EventListener.Factory>` donde se arma el cliente y aplica la primera factory; sin Hilt, llama a `PerfHooks.okHttp(builder)` antes de `build()`. En release el set queda vacío y el lambda no hace nada. Busca **cada** `OkHttpClient.Builder()` del alcance: un cliente que no pasa por el gancho queda sin secciones. OkHttp admite un solo `eventListenerFactory`: si ya hay uno, combínalos.
3. **Navegación sin cambio de actividad:** `PerfHooks.navigation` con el destino tal cual (la ruta `movie/{id}` en Navigation Compose, la clave en Navigation 3), sin convertirlo a texto.
4. **Contenido visible:** si `instrumentar` imprimió candidatos ("el proyecto ya tiene un punto de extensión"), conecta las marcas ahí ([abajo](#contenido-visible-dónde-conectar-las-marcas)) y no edites pantallas. Si no, en la primera pantalla, `ReportDrawnWhen { !uiState.isLoading }` (Compose, activity-compose 1.7+) o `reportFullyDrawn()` (Views): es el TTFD y lo usa Android vitals. En **cualquier otra pantalla que se vaya a medir**, `PerfHooks.mark("<pantalla>")` una vez por carga, cuando el contenido real está a la vista: deja la marca `MARK <pantalla>`, donde terminan las métricas de usuario y la ventana del flujo. Sin ella, una métrica que termina en la última llamada de red deja afuera el render y cambia de significado si una mejora reordena las llamadas.
5. **Manifests existentes:** si `src/debug/AndroidManifest.xml` o `src/profiling/AndroidManifest.xml` ya existían, agrega el `<provider>` (y `<profileable>` en profiling) que imprime el script.
6. **Dependencias por variante, antes del DoD:** `grep -n "releaseImplementation\|debugImplementation" <módulo>/build.gradle*`; cada librería que solo llega en `release` (el no-op de Chucker, Flipper, LeakCanary) necesita su `"profilingImplementation"`, o `assembleProfiling` falla y el DoD se repite entero.
7. **Nada en `.gitignore`:** `reports/` queda fuera de git por `.git/info/exclude` (lo escriben `nuevo` y `humo`); si hace falta agregarlo, va ahí. El `.gitignore` es del proyecto y no se toca.

## Contenido visible: dónde conectar las marcas

La marca `MARK <pantalla>` es donde terminan las métricas de usuario y la ventana del flujo. Elige dónde ponerla en este orden; el primero que exista gana, porque cada nivel inferior toca más archivos de producción:

1. **Un punto de extensión que el proyecto ya tiene** (lo detecta `instrumentar` en todos los módulos, sin leer lo que `No leer` prohíbe): una interfaz con nombre de contenido visible (`ScreenTracker`, `ContentReady`, `ScreenImpression`…) que recibe un multibinding de Hilt o Dagger, o un `CompositionLocal` equivalente. Con multibinding, **un solo archivo en el source set `perf`**: un módulo con `@Provides @IntoSet` cuya implementación llama a `PerfHooks.mark(<nombre que recibe>)`. El nombre de la marca es lo que reciba el gancho: el plan usa ese nombre (`MARK <nombre>`), y `humo` o la corrida de prueba lo muestran en "Secciones propias". Release no cambia: el multibinding ya existe en el código principal. Compruébalo antes (que `@Multibinds` o algún binding principal lo declare) y confirma que el gancho se llama **una vez por carga**, no por recomposición.
2. **Un punto común sin extensión:** una clase base de pantalla, el `Scaffold` o el contenedor del `NavHost` de la app, un `Fragment` base. Una sola llamada a `PerfHooks.mark` ahí, una vez por carga.
3. **Pantalla por pantalla**, como último recurso: `PerfHooks.mark("<pantalla>")` donde el contenido real ya está a la vista (una línea por pantalla medida; solo las que se miden).

Cuando no hay nada de esto, `PerfHooks` es el punto de extensión: vive en el código principal sin efecto en release y solo `PerfInstaller` (debug y la variante de profiling) lo apunta a la traza. No inventes una interfaz nueva en producción para esto salvo que el usuario lo pida.

**Actualizar la instrumentación** cuando cambia la skill: `instrumentar --actualizar` sobrescribe solo los archivos que llevan su encabezado "Generated by hb-performance"; lo que escribió el proyecto no se toca.

## DoD del setup

Dos invocaciones de Gradle, no una: el formateador primero y solo, porque Gradle corre las tareas en paralelo y `ktlintCheck` puede correr antes que `ktlintFormat`. Después, los comandos de `## DoD` más `assembleProfiling`, **en un solo comando** con el log en un archivo y al chat solo el resumen:

```bash
cd <raíz-del-proyecto> && ./gradlew -q <formateador, p. ej. app:ktlintFormat> > reports/perf/setup/logs/formato.log 2>&1; echo "exit $?"
cd <raíz-del-proyecto> && ./gradlew -q <tareas del DoD> app:assembleProfiling > reports/perf/setup/logs/dod.log 2>&1; echo "exit $?"; grep -E "FAILED|e: |error:|BUILD|tests completed" reports/perf/setup/logs/dod.log | head -20
```

Si falla, arregla y repite el segundo comando entero: una sola pasada más. Las plantillas vienen con los imports en el orden por defecto de ktlint (`java.*` al final) y dentro de los límites por defecto de detekt; el formateador ajusta el resto (comas finales, saltos de línea).

## Prueba de humo

Valida de una vez `SCREEN`, `NAV`, `HTTP`, TTID y TTFD con una corrida de arranque en frío, sin crear una investigación. La corre el usuario, con el dispositivo conectado; tú solo le das los comandos:

```bash
cd <raíz-del-proyecto> && <comando que instala el build de profiling, con el serial> && python3 -I <carpeta-de-la-skill>/scripts/perf.py humo --paquete <applicationId-instalado> --serial <serial> --instalar "<ese mismo comando de instalación>"
```

Con más de un dispositivo (`adb devices`), el serial va en la instalación (`adb -s <serial> install -r <apk>` o `ANDROID_SERIAL=<serial> ./gradlew app:installProfiling`) y en `--serial`. `humo` imprime las métricas, las secciones agrupadas y el paso siguiente según lo que se vaya a investigar: el comando `nuevo --receta arranque-frio` para el arranque, o el texto del chat de la sesión 1 para otra pantalla o flujo. Si falla: el paquete instalado (con su sufijo), Android 10 o superior, el manifest de `profiling` fusionado, que el código principal pase por los ganchos y, sin `ttfd_ms`, el `reportFullyDrawn`.

## Cierre del setup

- Agrega a `AGENTS.md` una sección con el encabezado en el idioma del archivo (`## Performance` o `## Rendimiento`), de 10 líneas como máximo: `applicationId`, cómo instalar el build de profiling (con el serial como `ANDROID_SERIAL=<serial> ./gradlew ...`; Gradle no tiene `-s <serial>`), qué secciones hay, dónde está el `reportFullyDrawn` y "setup listo". Si el proyecto se usa como prueba a ciegas, una línea `No leer: <rutas o patrones separados por comas>` (por ejemplo `docs/ALCANCE-*, casos/`): todas las sesiones la respetan ([SKILL.md](../SKILL.md) · regla 15). Sin `AGENTS.md`, propón crearlo solo con esa sección (u ofrece `hb-setup`).
- Propón commitearlo en **su propio PR** (por ejemplo `build(perf): agregar el build de profiling y la instrumentación de rendimiento`). Si el equipo no acepta herramientas de medición en el repo, guárdalo como parche en una carpeta no versionada y aplícalo con `git apply` al investigar.
- **Siguiente paso**, al final de tu respuesta y como último bloque: el comando de instalación y `perf.py humo`, completo y listo para copiar, y una línea que diga que `humo` imprime lo que sigue (la receta del arranque o el chat de la sesión 1). Anota el costo de esta sesión con `perf.py consumo` cuando haya carpeta; si todavía no la hay, dile al usuario el comando para anotarlo después.
