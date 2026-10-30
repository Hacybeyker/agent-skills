# Dominio: Android (Kotlin, Jetpack, Compose)

Mapa para diseñar planes y enseñar desarrollo Android nativo. Antes de enseñar APIs concretas, revisa las versiones del proyecto (`libs.versions.toml`, `build.gradle.kts`) y las notas de versión oficiales.

## Mapa de competencias

### 🟢 Básico
- **Kotlin**: null safety, `val`/`var`, data classes, sealed classes e interfaces, `when`, extensiones, lambdas y funciones de orden superior, colecciones, scope functions.
- **Proyecto**: módulos, Gradle con Kotlin DSL, catálogo de versiones, manifest, recursos, build types y flavors.
- **Componentes**: Activity, Service, BroadcastReceiver, ContentProvider, Intents y permisos en tiempo de ejecución.
- **Ciclo de vida** de Activity y cambios de configuración; `ViewModel` y `SavedStateHandle`.
- **Compose**: composables, `remember`, `mutableStateOf`, recomposición, layouts, `Modifier`, Material 3, previews, listas con `LazyColumn`.
- **Red y datos**: Retrofit u OkHttp (o Ktor), `kotlinx.serialization`, DataStore, Room básico.
- **Herramientas**: Logcat, depurador, Layout Inspector, Android Studio y su Agent Mode.

### 🟡 Intermedio
- **Corrutinas y Flow**: `suspend`, scopes (`viewModelScope`, `lifecycleScope`), dispatchers, cancelación, excepciones, `Flow`, `StateFlow`, `SharedFlow`, `stateIn`, `collectAsStateWithLifecycle`.
- **Arquitectura recomendada**: capas de UI y datos (dominio opcional), flujo de datos unidireccional, `UiState` inmutable, repositorios, fuente única de verdad, offline-first.
- **Inyección de dependencias** con Hilt (o Koin) y scopes.
- **Compose intermedio**: state hoisting, efectos (`LaunchedEffect`, `DisposableEffect`, `rememberUpdatedState`), `rememberSaveable`, temas, animaciones, accesibilidad semántica.
- **Navegación** con rutas type-safe (Navigation Compose o Navigation 3).
- **Persistencia**: relaciones y migraciones de Room, Flow desde Room, Paging 3.
- **Trabajo en segundo plano** con WorkManager (restricciones, cadenas, trabajo único).
- **Testing**: JUnit, fakes, `kotlinx-coroutines-test`, Turbine, tests de UI de Compose, Robolectric, tests instrumentados.
- **Plataforma**: notificaciones y su permiso, edge-to-edge e insets, predictive back.

### 🟠 Avanzado
- **Build**: modularización (`:feature:*`, `:core:*`), convention plugins, configuration cache, KSP, R8 (reglas keep, full mode).
- **Rendimiento**: Baseline Profiles, Macrobenchmark, App Startup, jank y trazas (Perfetto), LeakCanary, estabilidad en Compose (informes del compilador, strong skipping), fases de Compose (composición, layout, dibujo).
- **Concurrencia avanzada**: concurrencia estructurada, `supervisorScope`, `callbackFlow`, canales, backpressure, `Mutex`, tiempo virtual en tests.
- **Seguridad**: Android Keystore, BiometricPrompt, Network Security Config, certificate pinning y sus riesgos, Play Integrity, Credential Manager (passkeys), ofuscación y hardening.
- **Restricciones del sistema**: tipos de foreground service, alarmas exactas, Doze y App Standby.
- **Entrega**: firma, App Bundles, tracks de Play Console, CI/CD con GitHub Actions o fastlane.

### 🔴 Experto
- Arquitectura de apps grandes: límites entre módulos, APIs públicas internas, sincronización offline-first con resolución de conflictos.
- Kotlin Multiplatform para compartir lógica con iOS.
- Rendimiento en producción (Android vitals), código nativo (NDK, páginas de 16 KB).
- Hardening avanzado, detección de manipulación, protección de propiedad intelectual.
- Diseño de librerías, procesadores KSP y plugins de compilador.

## Rutas típicas

- **Hilt**: DI manual → Dagger y el grafo → configuración y puntos de entrada → módulos (`@Provides`, `@Binds`) → componentes y scopes → qualifiers → ViewModels y Compose → inyección asistida y WorkManager → testing → multimódulo y rendimiento → proyecto final. Ejemplo completo en `assets/ejemplo/hilt/PLAN.md`.
- **Corrutinas y Flow**: por qué concurrencia → `suspend` y scopes → cancelación y excepciones → dispatchers y main-safety → Flow frío → operadores → `StateFlow`/`SharedFlow` → UI y ciclo de vida → testing con Turbine → `callbackFlow` y canales → proyecto.
- **Jetpack Compose**: modelo declarativo → layout y `Modifier` → estado y recomposición → state hoisting y UDF → listas → navegación → Material 3 y temas → efectos → animaciones → testing → rendimiento y estabilidad → interop con Views → proyecto.
- **Persistencia offline-first**: DataStore → Room (entidades, DAO, relaciones) → migraciones → Room + Flow → repositorio como fuente única de verdad → sincronización con WorkManager → conflictos → tests.
- **Modularización y build**: por qué modularizar → tipos de módulos → catálogo de versiones → convention plugins → KSP y caché de configuración → navegación entre features → medir tiempos de build.
- **Seguridad en Android**: modelo de seguridad de la plataforma → almacenamiento seguro con Keystore → red segura → autenticación con Credential Manager y biometría → Play Integrity → R8 y hardening → OWASP MASVS.
- **Rendimiento**: métricas (startup, jank, memoria) → Macrobenchmark → Baseline Profiles → Compose (estabilidad, fases) → fugas de memoria → Android vitals.
- **Testing**: pirámide de tests → unitarios con fakes → corrutinas y Flow → ViewModel → UI de Compose → instrumentados y Hilt → screenshot tests → CI.

## Ideas erróneas frecuentes

- «`GlobalScope` sirve para tareas largas» → rompe la concurrencia estructurada; usa scopes con ciclo de vida o WorkManager.
- «El ViewModel decide el dispatcher de todo» → los repositorios y fuentes de datos deben ser *main-safe* y elegir su dispatcher.
- «`remember` sobrevive a la rotación» → no; usa `rememberSaveable` o el ViewModel.
- «Recomponer es redibujar toda la pantalla» → Compose salta composables cuyos parámetros no cambian; hay tres fases.
- «`runCatching` es inocuo en corrutinas» → también captura `CancellationException`; captura excepciones concretas o relanza la cancelación.
- «`@Singleton` en todo acelera la app» → retiene memoria toda la vida del proceso; usa el scope mínimo.
- «`EncryptedSharedPreferences` es lo recomendado» → está deprecado; usa Keystore (o Tink) con DataStore o archivos.
- «kapt y KSP son equivalentes» → KSP es más rápido y es el camino soportado.
- «R8 solo ofusca» → también optimiza y elimina código; la reflexión y la serialización necesitan reglas keep.
- «LiveData es obligatorio» → en Compose se recomienda `StateFlow` con `collectAsStateWithLifecycle`.
- «Los tests instrumentados son la base» → la mayoría deben ser unitarios, rápidos y con fakes.

## Decisiones que el estudiante debe saber argumentar

- Hilt, Koin o DI manual.
- Compose o Views, y cuándo mantener interop.
- Room o SQLDelight (si hay KMP); Retrofit o Ktor client.
- `StateFlow` o `SharedFlow` para eventos; eventos de UI como estado.
- WorkManager, foreground service o corrutina con ciclo de vida.
- Navigation Compose o Navigation 3.
- Certificate pinning: seguridad frente a riesgo operativo.
- Granularidad de módulos: velocidad de build frente a complejidad.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- Compose es el toolkit de UI recomendado.
- Kotlin 2.x con compilador K2; la versión estable más reciente es la 2.4.20.
- AGP 9 integra Kotlin (ya no se aplica `org.jetbrains.kotlin.android`) y usa el nuevo DSL; la opción de volver al DSL antiguo desaparece en AGP 10.
- KSP es el procesador recomendado; el soporte KSP de Dagger/Hilt es estable desde Dagger 2.60.
- `hiltViewModel()` para Compose está en `androidx.hilt:hilt-lifecycle-viewmodel-compose` desde androidx.hilt 1.3.0.
- `androidx.security:security-crypto` (EncryptedSharedPreferences, EncryptedFile, MasterKey) está deprecado desde la 1.1.0: usa APIs de la plataforma y Android Keystore.
- Navigation 3 es estable desde noviembre de 2025.
- Credential Manager es la API para passkeys, contraseñas e inicio de sesión federado.
- Las apps que apuntan a Android 15 (API 35) o superior son edge-to-edge.
- Google Play exige compatibilidad con páginas de memoria de 16 KB a las apps con código nativo que apuntan a Android 15 o superior.
- Android Studio (Agent Mode) y la Android CLI usan skills del estándar Agent Skills (`.agents/skills`).

## Ideas de práctica

- App de pedidos offline-first: Room + repositorio + WorkManager + Hilt.
- Pantalla con `StateFlow` y tests con Turbine.
- Migrar una pantalla de Views a Compose manteniendo el comportamiento.
- Medir el arranque con Macrobenchmark y aplicar un Baseline Profile.
- Guardar un token cifrado con una clave de Keystore y probar la rotación.
- Extraer una feature a su propio módulo con convention plugins.
