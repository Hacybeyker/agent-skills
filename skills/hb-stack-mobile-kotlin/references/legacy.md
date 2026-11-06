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

## Cuando el usuario decide modernizar

1. Queda escrito en `## Modernización` con alcance ("las pantallas nuevas", "la feature X", "al tocar una clase") y fecha.
2. Por partes y conviviendo: una pantalla en Compose dentro de un `ComposeView`, una clase de Rx a corrutinas con su puente, un módulo de Dagger a Hilt con `@InstallIn`. Cada parte con sus tests y el DoD en verde.
3. Sin mezclar en el mismo archivo lo viejo y lo nuevo, y sin tocar lo que la decisión no cubre.
4. Las migraciones concretas (APIs, pasos) salen de las skills oficiales de Android cuando estén instaladas (sección 6 del perfil); este perfil pone el orden y los límites.
