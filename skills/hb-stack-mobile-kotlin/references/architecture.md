# Arquitectura

Clean Architecture con tres capas por feature, MVVM con UDF en la capa de UI y packaging por feature.

## Capas

| Capa | Contiene | Depende de |
| --- | --- | --- |
| `domain` | Modelos de negocio (`data class` inmutables), interfaces de repositorio, use cases. **Kotlin puro.** | Nada |
| `data` | Implementaciones de repositorio, fuentes de datos (Room, DataStore, red), Entity/DTO, mappers | `domain` |
| `ui` | ViewModel, `UiState`, `Action`, composables, navegación de la feature | `domain` |
| `di` | Módulo de la feature que une interfaces con implementaciones | todas las de la feature |

- La única anotación tolerada en `domain` es `@Inject` (`javax.inject`) cuando la variante usa Hilt.
- El dominio **siempre existe**. Aunque un use case solo delegue al repositorio, el ViewModel pasa por él: así la UI nunca depende de `data` y la lógica tiene un lugar fijo cuando crece.

## Estructura

```
feature/<nombre>/
├── domain/
│   ├── model/           Profile.kt
│   ├── repository/      ProfileRepository.kt          (interfaz)
│   └── usecase/         ObserveProfileUseCase.kt, UpdateNameUseCase.kt
├── data/
│   ├── repository/      OfflineFirstProfileRepository.kt
│   ├── source/          local/ProfileDao.kt, remote/ProfileApi.kt
│   ├── model/           ProfileEntity.kt, ProfileDto.kt   (internal)
│   └── mapper/          ProfileMappers.kt
├── ui/
│   ├── ProfileScreen.kt      (con estado: ViewModel + collect)
│   ├── ProfileContent.kt     (sin estado: @Preview y tests)
│   ├── ProfileViewModel.kt
│   ├── ProfileUiState.kt
│   ├── ProfileAction.kt
│   └── ProfileNavigation.kt  (NavKey + entry de navegación)
└── di/
    └── ProfileModule.kt
core/
├── designsystem/   tema, tokens y componentes reutilizables
├── database/       @Database (Room); cada feature aporta sus Entity y DAO
├── network/        cliente HTTP
├── common/         dispatchers, suspendRunCatching, utilidades
└── testing/        fakes compartidos, reglas de test
```

- **Promueve a `core/` solo cuando 2 o más features lo necesitan.** Antes de eso, la duplicación es más barata que el acoplamiento.
- En KMP la misma estructura vive en `shared/src/commonMain/kotlin/<paquete>/`, y el código de plataforma en `androidMain` e `iosMain` con los mismos paquetes ([variants/kmp.md](variants/kmp.md)).

### Cuándo modularizar

Empieza con un módulo y paquetes. Pasa a módulos Gradle cuando aparezca alguna de estas señales: varias personas trabajando en paralelo, builds lentos, features que se quieren aislar o reutilizar. Entonces sigue el esquema de Now in Android:

- `:feature:<x>:api`: lo que otras features necesitan (por ejemplo el `NavKey`). `:feature:<x>:impl`: todo lo demás.
- Un `impl` solo depende de `api` de otras features. Ningún `api` depende de otra feature.
- `:core:<x>` no depende de features ni de `:app`.
- La configuración común va en *convention plugins* (`build-logic/`).

## Modelos y mappers

- Un modelo por capa: Entity (Room) y DTO (red) en `data`, modelo de negocio en `domain`. El `UiState` puede usar modelos de dominio directamente o modelos de UI si necesita formato propio.
- Los mappers son funciones de extensión en `data/mapper/` (`fun ProfileDto.toDomain(): Profile`).
- Entity y DTO son `internal` a `data`.

## Repositorios

- Son la única puerta a los datos y la **fuente única de verdad** de su tipo de dato.
- Lecturas: `Flow<T>`. Escrituras: funciones `suspend`. Las funciones `suspend` son *main-safe*: el repositorio cambia de dispatcher, no quien lo llama.
- Offline-first cuando la app necesita funcionar sin red: la UI lee de la base local y la sincronización escribe en ella.
- Nombres: por lo que respalda la implementación (`OfflineFirstXRepository`, `RoomXRepository`, `InMemoryXRepository`), o `DefaultXRepository` si no hay un nombre mejor. **Nunca el sufijo `Impl`**: no dice nada de la implementación. Los dobles de test: `FakeXRepository`.

## Use cases

- Una acción de negocio por clase, con `operator fun invoke`.
- Nombre en forma de verbo: `ObserveProfileUseCase` (devuelve `Flow`), `GetProfileUseCase` (lectura puntual), `UpdateNameUseCase` (escritura).
- Si un use case supera unas 100 líneas, probablemente mezcla negocio con acceso a datos.

## Errores

`runCatching` atrapa `CancellationException` y rompe la cancelación estructurada. En código `suspend` usa este helper de `core/common`:

```kotlin
suspend fun <T> suspendRunCatching(block: suspend () -> T): Result<T> =
    try {
        Result.success(block())
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        Result.failure(e)
    }
```

- El repositorio devuelve `Result<T>` (o un `sealed interface` de errores de dominio si la UI necesita distinguirlos).
- En flujos, usa `catch { }` y conviértelo en estado de error. Nunca dejes que una excepción llegue a la UI.

## Concurrencia

- Inyecta los `CoroutineDispatcher`. Nada de `Dispatchers.IO` fijo dentro de las clases.
- `viewModelScope` en ViewModels; un `CoroutineScope` inyectado para trabajo que debe sobrevivir a la pantalla.
- `Flow` frío hacia arriba y `stateIn` en el ViewModel.

## Comentarios

Por defecto, ninguno: los nombres explican el qué. Comenta solo el porqué, una decisión o una advertencia. KDoc en las APIs públicas de módulos que otros consumen.

## Principios y patrones de diseño

Aplica un patrón cuando resuelve un problema presente. Agregar estructura "por si acaso" va contra KISS y YAGNI. En el code review, nombra el patrón que usaste y por qué.

### Principios generales

| Principio | En este stack |
| --- | --- |
| **KISS** | La solución más simple que cumple. Un `when` sobre un `sealed interface` suele bastar antes que una jerarquía de clases. |
| **YAGNI** | Nada de abstracciones, parámetros ni módulos para necesidades futuras supuestas. |
| **DRY** | Una sola fuente para cada conocimiento (reglas de negocio, tokens, versiones). Para código, aplica la regla de tres: duplica una vez, abstrae a la tercera. |
| **Separación de responsabilidades** | Cada capa y cada clase con un propósito. |
| **Ley de Deméter** | Una clase habla con sus colaboradores directos, no con los colaboradores de ellos (`a.b.c.doIt()` es una señal). |
| **Composición sobre herencia** | Interfaces y delegación (`by`), no jerarquías profundas. |

### SOLID

| Principio | Aplicación |
| --- | --- |
| **S** Responsabilidad única | Un use case = una acción. Un mapper = una transformación. Un ViewModel = una pantalla. |
| **O** Abierto/cerrado | Comportamiento nuevo con implementaciones nuevas de una interfaz, sin modificar las existentes. |
| **L** Sustitución de Liskov | Los fakes cumplen el mismo contrato que la implementación real. |
| **I** Segregación de interfaces | Repositorios pequeños y por feature, sin interfaces "Dios". |
| **D** Inversión de dependencias | El dominio define las interfaces, `data` las implementa y la DI las une. |

### GRASP

| Patrón | Dónde aparece |
| --- | --- |
| **Experto en información** | La lógica va donde están los datos que necesita (validar un `Profile` es un método del modelo o de su use case). |
| **Creador** | El contenedor de DI crea los objetos. Nadie hace `Repository()` a mano fuera de los tests. |
| **Controlador** | El ViewModel recibe las acciones de la UI y las delega en los use cases. |
| **Bajo acoplamiento / Alta cohesión** | Features aisladas, capas con dependencias en una sola dirección. |
| **Polimorfismo** | `sealed interface` + `when` exhaustivo, o interfaces con varias implementaciones. |
| **Fabricación pura** | Repositorios, mappers y use cases no son conceptos de negocio: existen para mantener cohesión y bajo acoplamiento. |
| **Indirección** | Las interfaces y la DI desacoplan la UI de los datos. |
| **Variaciones protegidas** | Interfaces en los bordes inestables: plataforma (`expect`/`actual`), red, SDKs externos. |

### GoF y patrones de arquitectura

| Patrón | Dónde aparece | Úsalo cuando… |
| --- | --- | --- |
| **Repository** (Fowler) | `data/repository` | Siempre: es la puerta a los datos |
| **Observer** | `Flow` / `StateFlow` | Siempre: es la base de UDF |
| **State** | `UiState` `sealed` | Los estados de la pantalla se excluyen entre sí |
| **Command** | `Action` `sealed` | Siempre: cada interacción es un objeto |
| **Adapter** | Mappers, envoltorios de SDKs y de APIs de plataforma | Un formato externo no encaja con el modelo de dominio |
| **Facade** | Repositorio que coordina varias fuentes; envoltorio de un SDK complejo | Hay que ocultar complejidad detrás de una API simple |
| **Factory / Abstract Factory** | Builders de `HttpClient` y de base de datos; `ViewModel` con parámetros (assisted injection) | La creación tiene lógica o depende de la plataforma |
| **Builder** | DSLs de configuración (`HttpClient { }`) | Un objeto tiene muchos parámetros opcionales |
| **Strategy** | Políticas intercambiables: ordenamiento, cálculo de precios, métodos de autenticación | Hay variantes de un algoritmo elegidas en runtime |
| **Decorator** | Repositorio con caché que envuelve a otro; interceptores de logging | Hay que sumar comportamiento sin tocar la clase original |
| **Chain of Responsibility** | Interceptores de OkHttp/Ktor; validaciones encadenadas | Una solicitud pasa por pasos independientes |
| **Composite** | Árbol de composables | La UI compone piezas pequeñas |
| **Singleton** | Solo vía scope de DI (`@Singleton`, `single { }`) | Nunca con `object` mutable ni a mano |
| **Template Method** | Evítalo: prefiere composición | — |
