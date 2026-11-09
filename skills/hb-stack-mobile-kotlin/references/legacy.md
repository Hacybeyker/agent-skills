# Proyectos con otro stack: Views, MVP, RxJava, LiveData, Dagger 2

El perfil describe el objetivo moderno. Muchos proyectos en producción usan otra cosa, y funcionan. Aquí va cómo aplicar las mismas reglas de calidad sin cambiar de stack, y cómo migrar cuando el usuario lo decide.

## Regla general

- `AGENTS.md` (`## Stack`, `## Arquitectura`) dice qué hay; `## Modernización` dice qué se cambia y hasta dónde. Todo lo demás se mantiene.
- Código nuevo dentro de una feature existente: en el estilo de esa feature. Una feature nueva: en el estilo del proyecto, salvo que `## Modernización` diga otra cosa para las features nuevas.
- Las reglas que no dependen del stack siguen valiendo: inyección por constructor, dominio sin frameworks (si hay capa de dominio), tests con fakes para la lógica nueva, nada de secretos en el código, dependencias estables en el catálogo.
- Sugerir una migración: una línea al final del entregable, solo si la oportunidad es clara ("esta pantalla nueva podría ir en Compose si se decide en Modernización"). Nunca un plan ni código migrado sin pedirlo.

## Equivalencias

| Perfil | En el proyecto | Qué cuidar |
| --- | --- | --- |
| `Screen` y `Content` en Compose | `Activity` o `Fragment` con XML y **ViewBinding** | Nada de `findViewById` repetido ni de synthetics; la vista solo pinta estado y reenvía eventos. Sin lógica de negocio en la vista |
| `UiState` + `onAction` (MVVM, UDF) | **MVP**: contrato `View`/`Presenter` | El `Presenter` no conoce Android (`Context`, `View` de Android): habla con la interfaz. Se desengancha en `onDestroy`/`onDestroyView`. Un estado explícito (`ViewState`) es mejor que muchos `showX()` |
| `UiState` + `onAction` | **MVVM con LiveData** | `LiveData` se observa con el `LifecycleOwner` correcto (`viewLifecycleOwner` en fragments). Eventos de una sola vez: estado que la UI confirma, no `SingleLiveEvent` nuevos |
| Corrutinas y `Flow` | **RxJava 2/3** | Los `Scheduler` se inyectan (para los tests); todo `Disposable` va a un `CompositeDisposable` que se limpia en el ciclo de vida; sin `subscribe()` sin manejo de error. No mezcles Rx y corrutinas en la misma clase; en la frontera, `kotlinx-coroutines-rx3` |
| Hilt | **Dagger 2** o DI manual | Scopes explícitos; nada de singletons estáticos nuevos; los módulos de test reemplazan dependencias con fakes |
| Navigation Compose o 3 | Fragments con `NavController` o `Intent` entre actividades | Argumentos tipados (`Safe Args` o `Parcelable`), sin `Serializable` nuevo; la navegación la decide la vista, no el presenter o el ViewModel |
| Room o DataStore | SQLite a mano, Realm, `SharedPreferences` | Acceso fuera del hilo principal; migraciones con test; sin datos sensibles sin cifrar |
| Material 3 | Material 2 o AppCompat | Colores, textos y tamaños en recursos; nada fijo en el XML |

## Tests en estos stacks

- MVP: el `Presenter` se prueba con una `View` falsa que registra llamadas; el contrato se verifica como estado, no como secuencia de métodos.
- RxJava: `TestScheduler` o `Schedulers.trampoline()` inyectados; `test()` sobre el observable y `assertValue`/`assertError`.
- LiveData: `InstantTaskExecutorRule` y un observador que recoge los valores; sin `Thread.sleep`.
- Dagger 2: componentes de test con módulos falsos, o construcción manual del objeto en el test (inyección por constructor).

## Módulo library con Views

Un módulo `library` que aloja pantallas de Views (por ejemplo `:legacy`, que la app de Compose abre) sigue las mismas reglas de calidad que la app.

- **Los mismos `buildTypes` que la app** (`debug`, `release` y los propios, como `demo`). Si la app tiene un tipo que la library no, Gradle no encuentra variante y falla al resolver el proyecto. Declara el tipo en la library (`create("demo") { initWith(getByName("release")) }`) o, si no puede ser igual, `matchingFallbacks += listOf("release")` en el tipo de la app.
- Robolectric necesita los recursos: `testOptions { unitTests { isIncludeAndroidResources = true } }`.
- Si la app tiene `lint { checkDependencies = true }`, su Lint ya analiza la library, que además corre el suyo: el trabajo se duplica. Decídelo una vez.

## Tests de Activities y Fragments con Hilt

- **Con `hilt-android-testing`:** `@HiltAndroidTest`, `HiltAndroidRule` y `@Config(application = HiltTestApplication::class)`, con `@RunWith(AndroidJUnit4::class)`.
- **Sin esa dependencia** (el proyecto no la admite o no está en el catálogo): una Activity o un Fragment con `@AndroidEntryPoint` no se lanza en Robolectric, porque la aplicación de test no tiene el grafo. No la fuerces ni agregues la dependencia por tu cuenta:
  1. La lógica va al Presenter y se prueba con una `View` falsa, como arriba.
  2. La vista se prueba con un **host de prueba sin Hilt**: una Activity o un Fragment de test, con el mismo layout, al que se le pasa el Presenter ya construido por constructor o setter.
  3. Que el grafo de Hilt resuelve lo que la pantalla pide queda sin test: se comprueba en el dispositivo o con una inyección temporal, y se anota "sin test" en la verificación.
- Los tests de recreación de la vista y de muerte del proceso se escriben sobre ese mismo host: `ActivityScenario.recreate()`, y para un Fragment que vuelve por la pila, `replace` con `addToBackStack` y `popBackStack()`.

## Screenshot tests de Views con Roborazzi

Funcionan sobre Robolectric (`Robolectric.buildActivity(...).setup()` y `decorView.captureRoboImage(ruta)`), con tres cuidados:

- **Un test por modo** (claro y oscuro), no dos capturas en el mismo test: con dos, `verify` falló en goldens distintos de una corrida a otra. Dos métodos, o un test parametrizado, con `RuntimeEnvironment.setQualifiers("+night")` para el oscuro.
- **Animaciones apagadas:** `ValueAnimator.setDurationScale(0f)` no es API pública, así que se invoca por reflexión (`ValueAnimator::class.java.getMethod("setDurationScale", Float::class.java).invoke(null, 0f)`) antes de lanzar la Activity.
- **Tamaño de ventana fijo** (`@Config(qualifiers = "w411dp-h891dp")`) y el mismo al grabar y al verificar: el tamaño cambia qué cabe en pantalla, por ejemplo si una lista se desplaza o no, y con él el golden.
- Si la captura falla con `NoSuchMethodException` de Espresso, la `espresso-core` transitiva es vieja: declara una estable más reciente en el catálogo.

## RxJava con Retrofit

`RxJava3CallAdapterFactory.create()` crea observables **asíncronos** que ya corren en un hilo de fondo: `subscribeOn` no tiene efecto sobre ellos. Para que el `Scheduler` que inyectas mande (y se pueda sustituir en los tests), usa `RxJava3CallAdapterFactory.createSynchronous()`, o `createWithScheduler(scheduler)` si quieres uno fijo.

## Campos que maneja el Presenter

Al recrearse la vista (volver a un Fragment por la pila, rotar), Android restaura el estado guardado de cada vista, y puede pisar lo que el Presenter acaba de fijar: el error de un `TextInputLayout` tras un 404 desaparece porque la restauración reescribe el estado anterior.

- En los campos cuyo contenido y errores gobierna el Presenter, `saveEnabled = false` (o `android:saveEnabled="false"`): el framework no los guarda ni los restaura.
- A cambio, el estado ya no se recupera solo: el Presenter (o su `ViewState`) conserva el texto y el error, y la vista los vuelve a pintar al crearse (`onViewCreated`).
- Se prueba con la recreación por la pila descrita arriba; un test que solo lanza el Fragment suelto no reproduce el fallo.

## Edge-to-edge con AppCompat

Con `targetSdk` 35 o más, Android 15 dibuja de borde a borde aunque no lo pidas, y el contenido de una Activity de AppCompat queda bajo las barras del sistema. La skill oficial `edge-to-edge` cubre Compose; en Views:

- `enableEdgeToEdge()` (de `androidx.activity`) en `onCreate`, antes de `super.onCreate`.
- Los insets (`systemBars`, `displayCutout` y `ime` donde haya campos de texto) se aplican como padding con `ViewCompat.setOnApplyWindowInsetsListener` y devolviendo los `WindowInsetsCompat`. Decide en qué nivel se aplican (la raíz de la Activity o el contenedor de cada pantalla) y no en ambos.
- Revísalo en un dispositivo con Android 15 o más, con navegación por gestos y por botones.

## Convivir con un host Compose

Cuando una app de Compose abre pantallas de este módulo:

- **La dependencia va en un solo sentido:** `app → :legacy`. El módulo legacy no conoce a la app. Lo que necesita de ella (sesión, navegación, datos nuevos) lo declara como **interfaces en el propio módulo legacy**; la app las implementa con adaptadores y las entrega por DI en un módulo puente.
- **Resultados:** el host Compose abre la Activity legacy con `rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult())`, o con un contrato tipado definido en el módulo legacy, y la Activity responde con `setResult`. Sin `startActivityForResult` ni `onActivityResult` nuevos.
- **Prueba el puente:** un test del grafo de DI que resuelva esas interfaces. Sin `hilt-android-testing` (ver arriba), queda "sin test" y se comprueba en el dispositivo la primera vez que un Presenter las pide.
- Sin lógica de negocio en los adaptadores: solo traducen entre el contrato legacy y los casos de uso de la app.

## Cuando el usuario decide modernizar

1. Queda escrito en `## Modernización` con alcance ("las pantallas nuevas", "la feature X", "al tocar una clase") y fecha.
2. Por partes y conviviendo: una pantalla en Compose dentro de un `ComposeView`, una clase de Rx a corrutinas con su puente, un módulo de Dagger a Hilt con `@InstallIn`. Cada parte con sus tests y el DoD en verde.
3. Sin mezclar en el mismo archivo lo viejo y lo nuevo, y sin tocar lo que la decisión no cubre.
4. Las migraciones concretas (APIs, pasos) salen de las skills oficiales de Android cuando estén instaladas (sección 6 del perfil); este perfil pone el orden y los límites.
