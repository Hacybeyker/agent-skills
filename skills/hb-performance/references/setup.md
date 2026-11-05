# Sesión 0 · Setup (una vez por proyecto)

Deja el proyecto listo para medir. Las investigaciones siguientes lo reutilizan sin pagarlo de nuevo. Con red y pantallas suele ser una decena de archivos: propón todo junto, con la lista de archivos y un resumen por archivo (no el diff entero en el chat), y espera aprobación.

## Qué hace falta

| Pieza | ¿Obligatoria? | Para qué |
| --- | --- | --- |
| Build type `profiling` (`profileable`, no `debuggable`, R8 como release) | Sí | Sin él solo valen los conteos de red y las fugas |
| `reportFullyDrawn` en la primera pantalla | Recomendada | TTFD: el arranque hasta el contenido visible, no solo hasta el primer frame. También lo usa Android vitals |
| Secciones `SCREEN` (ciclo de vida de actividades y fragments) | Recomendada | Cuánto dura cada `onCreate`/`onResume` y qué pantalla precede a cada llamada |
| Secciones `HTTP` y `TTFB` | Si la app usa OkHttp (Retrofit, Ktor con motor OkHttp, Apollo) | Tiempos por endpoint, duplicados y separar servidor de cliente |
| Marcas `NAV` | Si la navegación no cambia de actividad (Compose, Navigation 3) | Saber en qué pantalla está el flujo |

Detecta el stack con una búsqueda y sin recorrer el proyecto:

```bash
cd <raíz-del-proyecto> && grep -rhoE 'okhttp|retrofit|ktor-client|apollo|fragment|appcompat|compose|navigation3|navigation-compose|hilt|koin|chucker|kover|jacoco|sonar' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' . | sort | uniq -c
```

## Build de profiling

En el módulo de la app (Kotlin DSL; en Groovy es lo mismo con su sintaxis):

```kotlin
android {
    buildTypes {
        create("profiling") {
            initWith(getByName("release")) // o el build type de pruebas más parecido a release
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release") // solo si hay módulos de librería
        }
    }
    sourceSets {
        // AGP 9 o superior:
        getByName("debug").kotlin.directories += "src/perf/kotlin"
        getByName("profiling").kotlin.directories += "src/perf/kotlin"
        // AGP 8: getByName("debug").java.srcDir("src/perf/kotlin"), y lo mismo para profiling
    }
}
```

```xml
<!-- src/profiling/AndroidManifest.xml -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application>
        <profileable android:shell="true" />
    </application>
</manifest>
```

Revisa antes de proponerlo:

- **Firma:** la misma del build que ya está instalado en el dispositivo de pruebas (debug o el de QA). Con otra firma no se instala encima y se pierden los datos. Si no hay nada instalado, `install` es una instalación nueva y Android puede restaurar el backup de la nube: si la app se cae al abrir, revisa `firstInstallTime` y las exclusiones de backup.
- **Backend o mocks:** si el proyecto tiene un modo con datos simulados (un flag de `BuildConfig`, un interceptor de mocks), pregunta si el build de profiling lo usa: saca el backend de la medición y las métricas de usuario pasan a familia `app`. Sin mocks, con backend real, quedan en `e2e`.
- **Claves y secretos:** `initWith(release)` hereda los `buildConfigField` de release; confirma que las claves del ambiente estén en `local.properties` o en variables de entorno de esa máquina.
- **Firebase o Google Services:** si el plugin está aplicado, el build de profiling puede necesitar su propio `google-services.json` en `src/profiling/`.
- **CI:** si no quieres compilar `profiling` en CI, filtra la variante con `beforeVariants`.
- **R8:** los nombres salen ofuscados en CPU y heap. El mapping queda en `<módulo>/build/outputs/mapping/profiling/mapping.txt`.

## Instrumentación

`perf.py instrumentar` copia las piezas genéricas al source set `perf` (y sus tests a `testDebug`), sin pisar lo que exista. Detecta OkHttp, Retrofit y fragments; se puede forzar con `--red`, `--sin-red`, `--retrofit`, `--sin-retrofit`, `--fragments` y `--sin-fragments`. Sin red, no copia nada de OkHttp ni las secciones asíncronas.

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py instrumentar --modulo app --paquete <paquete.de.la.app>.perf
```

Después, **una vez**, el formateador del proyecto (`ktlintFormat`, `spotlessApply` o el que diga `## DoD`): las plantillas siguen un estilo común y el del proyecto puede ser otro. Recién entonces el DoD.

## Cableado (lo que el script no puede saber)

1. **Pantallas, sin tocar código principal:** declara `PerfInstaller` en los manifests de `debug` y `profiling`. Android lo crea antes de `Application.onCreate` y registra `ScreenTraceCallbacks`.
   ```xml
   <provider android:name="<paquete>.PerfInstaller" android:authorities="${applicationId}.perf-installer" android:exported="false" />
   ```
2. **Red:** el código principal arma el `OkHttpClient` y no puede ver el source set `perf`. Hace falta un gancho que en release quede vacío:
   - **Con Hilt:** en `main`, un `@Multibinds` de `Set<EventListener.Factory>` con un qualifier propio; en `perf`, un módulo que aporta `TraceEventListener.FACTORY` con `@IntoSet`. Al armar el cliente: `factories.firstOrNull()?.let(builder::eventListenerFactory)`. En release el set queda vacío.
   - **Sin Hilt:** en `main`, un objeto con un lambda vacío (`var okHttp: (OkHttpClient.Builder) -> Unit = {}`) que el cliente llama al armarse; `PerfInstaller.onCreate` lo reemplaza por `{ it.eventListenerFactory(TraceEventListener.FACTORY) }`.
   - **Todos los clientes:** busca cada `OkHttpClient.Builder()` del alcance. Un cliente propio de un módulo queda sin secciones si no pasa por el gancho. OkHttp admite un solo `eventListenerFactory`: si ya hay uno, combínalos.
3. **Navegación sin cambio de actividad:** el mismo tipo de gancho, `var navigation: (Any) -> Unit = {}`, llamado con el destino tal cual (la ruta o la clave), sin convertirlo a texto: así release no paga nada. `PerfInstaller` lo apunta a `NavigationTrace::mark`, que arma el nombre sin ids.
   - **Navigation Compose:** `navController.addOnDestinationChangedListener { _, destination, _ -> destination.route?.let(PerfHooks.navigation) }` (la ruta es la plantilla, `movie/{id}`).
   - **Navigation 3:** `LaunchedEffect(backStack) { snapshotFlow { backStack.lastOrNull() }.collect { it?.let(PerfHooks.navigation) } }`. Las claves conviene que sean `data object` o `data class`: su nombre sobrevive a R8.
4. **Contenido visible (TTFD):** en la primera pantalla, cuando el contenido real está a la vista (no el estado de carga). Va en el código principal: en release solo informa al sistema.
   - **Compose** (activity-compose 1.7+): `ReportDrawnWhen { !uiState.isLoading }`.
   - **Views:** `reportFullyDrawn()` (o `fullyDrawnReporter`) cuando el adapter recibe los datos.
5. **Cobertura:** si el proyecto mide cobertura (Kover, JaCoCo, Sonar), excluye `**/perf/**`: entra en la variante debug sin tests de instrumentación.
6. **DoD** con la salida acotada; los tests nuevos van en `testDebug`.

## Prueba de humo

Instala el build de profiling y usa la receta de arranque en frío, que valida todo de una vez (`SCREEN`, `NAV`, `HTTP`, TTID y TTFD):

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py nuevo --receta arranque-frio --paquete <applicationId> --carpeta reports/perf/setup
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan reports/perf/setup/plan.json --prueba
```

Si falta algo: el paquete instalado, Android 10 o superior, el manifest de `profiling` fusionado, que el código principal pase por los ganchos y, sin `ttfd_ms`, el `reportFullyDrawn`.

## Cierre del setup

- Agrega a `AGENTS.md` una sección con el encabezado en el idioma del archivo (`## Performance` o `## Rendimiento`), de 10 líneas como máximo: `applicationId`, cómo instalar el build de profiling, qué secciones hay, dónde está el `reportFullyDrawn` y "setup listo". Sin `AGENTS.md`, propón crearlo solo con esa sección (u ofrece `hb-setup`).
- Propón commitearlo en **su propio PR** (por ejemplo `build(perf): agregar el build de profiling y la instrumentación de rendimiento`). Si el equipo no acepta herramientas de medición en el repo, guárdalo como parche en una carpeta no versionada y aplícalo con `git apply` al investigar.
- **Siguiente paso** (en el chat, porque `estado.md` todavía no existe): para el arranque, el comando de `perf.py nuevo --receta arranque-frio`; para otro flujo, "Sigue hb-performance: <alcance>" en un chat nuevo.
