# Testing

## Qué se testea (mínimo)

| Qué | Cómo | Dónde |
| --- | --- | --- |
| ViewModels, incluidos sus flujos | Unitario con fakes | Android: `src/test`. KMP: `commonTest` |
| Use cases y mappers | Unitario, Kotlin puro | Igual |
| Repositorios y fuentes de datos | Unitario con fakes; Room con base en memoria | Igual (Room en `androidHostTest` o `src/test` con Robolectric) |
| UI de cada `Content` | Compose UI test sobre JVM (Robolectric) | `src/test` / `androidHostTest` |
| Regresión visual | Screenshot tests (Roborazzi) | Igual |
| Navegación principal | UI test de navegación | Igual o instrumentado si exige dispositivo |
| Rendimiento | Macrobenchmark y Baseline Profiles | Módulo `:benchmark` ([performance.md](performance.md)) |

Los tests instrumentados (`androidTest`) quedan solo para lo que de verdad exige un dispositivo.

## Fakes, no mocks

- Un fake implementa el contrato real con datos en memoria (`FakeProfileRepository`). Verifica comportamiento, no interacciones, y cumple el principio de Liskov.
- Los fakes compartidos viven en `core/testing`. En KMP, las librerías de mocks no funcionan en todos los targets, así que los fakes son la única opción.
- Un mock solo se justifica para una dependencia externa que no puedes falsear (y aun así, prefiere envolverla en una interfaz propia).

## Estructura

- Un comportamiento por test. Nombre que describe el caso: ``fun `save failure shows error message`()``.
- Given / When / Then.

```kotlin
@Test
fun `save failure shows error message`() = runTest {
    // Given
    val repository = FakeProfileRepository(failOnUpdate = true)
    val viewModel = EditProfileViewModel(
        observeProfile = ObserveProfileUseCase(repository),
        updateName = UpdateNameUseCase(repository),
        savedStateHandle = SavedStateHandle(),
    )
    backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { viewModel.uiState.collect() }

    // When
    viewModel.onAction(EditProfileAction.Save)

    // Then
    assertEquals(UserMessage.SaveFailed, viewModel.uiState.value.userMessage)
}
```

## Corrutinas y flujos

- `runTest` y `kotlinx-coroutines-test`. Inyecta dispatchers para poder pasar uno de test.
- Reemplaza `Dispatchers.Main` con una regla (`MainDispatcherRule` en Android) o con `Dispatchers.setMain` / `resetMain` en `commonTest`.
- **`StateFlow` con `WhileSubscribed`:** colecta en `backgroundScope` y comprueba `uiState.value`, como en el ejemplo. Es la forma que recomienda Google.
- **Secuencias de emisiones:** Turbine (`flow.test { awaitItem() }`).

## Tests de UI

- Siempre contra `Content`, con estados falsos y `onAction = {}` o un registro de acciones.
- Android: `createComposeRule()` con Robolectric. KMP: `runComposeUiTest { }`.
- Busca nodos por texto o por `testTag` estable, y comprueba lo que el usuario ve.

## Screenshot tests

- Roborazzi sobre Robolectric: sin emulador. Graba con `recordRoborazziDebug` y verifica con `verifyRoborazziDebug` en CI. Paparazzi es la alternativa si el proyecto no usa Robolectric.
- Un screenshot por estado clave (carga, contenido, vacío, error), en claro y oscuro, con datos deterministas y tamaño fijo.
- Las imágenes de referencia se versionan. Todo cambio visual debe ser intencional y revisado.

## Cobertura

- Kover para medir y, si el proyecto lo define, como *gate* en CI.
- Mide las clases con comportamiento (dominio, data y ViewModels). Excluye el código generado (Hilt, Room, Koin) y los adaptadores de framework.
