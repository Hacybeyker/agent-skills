# Sesión 0 · Setup (una vez por proyecto)

Deja el proyecto listo para medir. Las investigaciones siguientes lo reutilizan sin pagarlo de nuevo. No es un diff mínimo: con red y pantallas suele ser una decena de archivos. Propón todo junto, con su diff, y espera aprobación.

## Qué hace falta

| Pieza | ¿Obligatoria? | Para qué |
| --- | --- | --- |
| Build type `profiling` (`profileable`, no `debuggable`, R8 como release) | Sí | Sin él solo valen los conteos de red y las fugas |
| Secciones `SCREEN` (ciclo de vida de actividades y fragments) | Recomendada | Cuánto dura cada `onCreate`/`onResume` y qué pantalla precede a cada llamada |
| Secciones `HTTP` y `TTFB` | Si la app usa OkHttp (Retrofit, Ktor con motor OkHttp, Apollo) | Tiempos por endpoint, duplicados y separar servidor de cliente |
| Marcas `NAV` | Si la navegación no cambia de actividad (Compose, Navigation 3) | Saber en qué pantalla está el flujo |

Detecta el stack con una búsqueda y sin recorrer el proyecto:

```bash
cd <raíz-del-proyecto> && grep -rhoE 'okhttp|retrofit|ktor-client|apollo|fragment|appcompat|compose|navigation3|hilt|koin|chucker' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' . | sort | uniq -c
```

## Build de profiling

En el módulo de la app (Kotlin DSL; en Groovy es lo mismo con su sintaxis):

```kotlin
android {
    buildTypes {
        create("profiling") {
            initWith(getByName("release")) // o el build type de pruebas más parecido a release
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
    }
    sourceSets {
        getByName("debug").java.srcDir("src/perf/kotlin")
        getByName("profiling").java.srcDir("src/perf/kotlin")
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

- **Firma:** la misma del build que ya está instalado en el dispositivo de pruebas (debug o el de QA). Con otra firma no se instala encima y se pierde la sesión.
- **`matchingFallbacks`:** los módulos de librería no tienen `profiling`; usan el build type que indiques.
- **Firebase o Google Services:** si el plugin está aplicado, el build de profiling puede necesitar su propio `google-services.json` en `src/profiling/`. Verifica que tome el del ambiente correcto.
- **CI:** si no quieres compilar `profiling` en CI, filtra la variante con `beforeVariants`.
- **R8:** los nombres salen ofuscados en CPU y heap. El mapping queda en `build/outputs/mapping/profiling/mapping.txt`. Si el release pasa por otro ofuscador fuera de Gradle, el build de profiling no lo incluye: anótalo.

## Instrumentación

`perf.py instrumentar` copia las piezas genéricas al source set `perf` (y sus tests a `testDebug`), sin pisar lo que exista. Detecta OkHttp, Retrofit y fragments en el módulo; se puede forzar con `--red`, `--sin-red`, `--retrofit`, `--sin-retrofit`, `--fragments` y `--sin-fragments`.

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py instrumentar --modulo app --paquete <paquete.de.la.app>.perf
```

Copia `SectionTracer`, `ScreenTraceCallbacks`, `NavigationTrace`, `PerfInstaller` y, con red, `HttpSectionName` y `TraceEventListener` (llamada completa más TTFB; un interceptor no alcanza, porque termina antes de leer el body).

## Cableado (lo que el script no puede saber)

1. **Pantallas, sin tocar código principal:** declara `PerfInstaller` en los manifests de `debug` y `profiling`. Android lo crea antes de `Application.onCreate` y registra `ScreenTraceCallbacks`.
   ```xml
   <provider android:name="<paquete>.PerfInstaller" android:authorities="${applicationId}.perf-installer" android:exported="false" />
   ```
2. **Red:** el código principal arma el `OkHttpClient` y no puede ver el source set `perf`. Hace falta un gancho que en release quede vacío:
   - **Con Hilt:** en `main`, un `@Multibinds` de `Set<EventListener.Factory>` con un qualifier propio; en `perf`, un módulo que aporta `TraceEventListener.FACTORY` con `@IntoSet`. Al armar el cliente: `factories.firstOrNull()?.let(builder::eventListenerFactory)`. En release el set queda vacío.
   - **Sin Hilt:** en `main`, un objeto con un lambda vacío (`var okHttp: (OkHttpClient.Builder) -> Unit = {}`) que el cliente llama al armarse; `PerfInstaller.onCreate` lo reemplaza por `{ it.eventListenerFactory(TraceEventListener.FACTORY) }`.
   - **Todos los clientes:** busca cada `OkHttpClient.Builder()` del alcance. Un cliente propio de un módulo queda sin secciones si no pasa por el gancho.
   - OkHttp admite un solo `eventListenerFactory`: si el proyecto ya tiene uno, combínalos.
3. **Navegación sin cambio de actividad:** el mismo tipo de gancho (`var navigation: (String) -> Unit = {}`) llamado desde el punto único donde se navega. Con Navigation 3, observa el tope del back stack (`snapshotFlow { backStack.lastOrNull() }`) y pasa `key.toString().substringBefore('(')`, que sobrevive a R8. `PerfInstaller` lo apunta a `NavigationTrace::mark`.
4. Corre el DoD del proyecto con la salida acotada; los tests nuevos van en `testDebug`.

## Prueba de humo

Instala el build de profiling, deja la app en una pantalla con una llamada de red y corre una captura de prueba:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --prueba --paquete <applicationId> --carpeta reports/perf/setup
```

Imprime las métricas y las secciones propias que vio. Confirma que aparecen `SCREEN`, `HTTP`/`TTFB` (si hay red) y los endpoints esperados. Si no aparecen: el paquete en `atrace_apps`, Android 10 o superior, el manifest de `profiling` fusionado y que el código principal pase por los ganchos.

## Cierre del setup

- Agrega a `## Rendimiento` del `AGENTS.md` (máximo 10 líneas): `applicationId`, cómo instalar el build de profiling, qué secciones hay y "setup listo".
- Propón commitearlo en **su propio PR** (por ejemplo `build(perf): agregar el build de profiling y la instrumentación de rendimiento`). Si el equipo no acepta herramientas de medición en el repo, guárdalo como parche en una carpeta no versionada y aplícalo con `git apply` al investigar.
