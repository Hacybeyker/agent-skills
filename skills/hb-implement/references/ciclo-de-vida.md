# Tests de ciclo de vida en la JVM

Para pantallas con estado (un formulario, un campo con error, un paso de un flujo, una lista con scroll). El DoD verde no ve lo que solo ocurre con el ciclo de vida real: el estado guardado de una vista que pisa un error recién fijado, un dato que vivía en memoria y se pierde al arrancar en frío. Estos tests lo atrapan sin dispositivo, con Robolectric.

Escribe uno por cada dato que el alcance exige conservar, y confirma que **falla sin la corrección** (rojo, verde): un test de recreación que pasa siempre no protege nada.

## Qué se simula

| Situación | Qué le pasa a la pantalla | Qué se prueba |
| --- | --- | --- |
| **Recreación de la vista** (rotar, cambiar el tema, volver por la pila) | La vista se destruye y se crea de nuevo; el ViewModel o el Presenter siguen vivos | Lo que el usuario ve tras recrearla es lo que debía ver: sin campos borrados, sin errores perdidos, con el scroll en su sitio |
| **Muerte del proceso** | Todo se destruye; solo queda lo que se guardó | El estado se guarda y se restaura desde cero, y lo que no cabe en el estado guardado se vuelve a pedir a su fuente |

## Compose

`StateRestorationTester` ejecuta el ciclo de guardar y restaurar sobre el contenido, y cubre `rememberSaveable`:

```kotlin
@get:Rule val composeRule = createComposeRule()

@Test
fun `lo escrito sobrevive a la recreacion`() {
    val tester = StateRestorationTester(composeRule)
    tester.setContent { FormScreenContent() }       // el composable con su estado real

    composeRule.onNodeWithTag("campo_nombre").performTextInput("Ana")
    tester.emulateSavedInstanceStateRestore()

    composeRule.onNodeWithTag("campo_nombre").assertTextContains("Ana")
}
```

El estado que vive en el ViewModel se prueba al nivel del ViewModel: se construye uno nuevo con lo que quedó en el `SavedStateHandle` del anterior.

```kotlin
@Test
fun `el borrador sobrevive a la muerte del proceso`() = runTest {
    val handle = SavedStateHandle()
    val first = EditProfileViewModel(/* fakes */, savedStateHandle = handle)
    first.onAction(EditProfileAction.NameChanged("Ana"))

    val restored = SavedStateHandle(handle.keys().associateWith { handle.get<Any?>(it) })
    val second = EditProfileViewModel(/* fakes */, savedStateHandle = restored)
    backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { second.uiState.collect() }

    assertEquals("Ana", second.uiState.value.name)
}
```

Solo sobrevive lo que cabe en un `Bundle` (primitivos, `String`, `Parcelable`, `Serializable`). Un modelo propio sin `@Parcelize` se pierde en la vida real aunque este test lo vea.

## Views (Activity y Fragment)

- **Activity:** `ActivityScenario.launch(...)`, escribir o fijar el estado en `onActivity`, `scenario.recreate()` y comprobar en un nuevo `onActivity`. `recreate()` guarda el estado de la instancia y lo restaura en una nueva, como una rotación o la muerte del proceso.
- **Fragment recreado por la pila:** un Fragment que se reemplaza (`replace` con `addToBackStack`) conserva su instancia pero destruye su vista; al volver con `popBackStack()` se crea de nuevo y Android le restaura el estado de las vistas. Eso borra un error que el Presenter fijó justo antes. Un test que solo lanza el Fragment suelto **no pasa por ahí**. Hay que reproducir el camino real: una Activity anfitriona, navegar a otro Fragment con `replace` y `addToBackStack`, volver con `popBackStack()` y comprobar lo que se ve.
- **Restauración desde `savedInstanceState`:** `recreate()` ya la ejerce de punta a punta. Si guardas estado propio en `onSaveInstanceState`, ponlo en una clase que reciba el `Bundle` (`save(bundle)` y `restore(bundle)`) y pruébala directamente: guarda, crea una instancia nueva y restaura.
- **Campos que maneja el Presenter:** la restauración automática de las vistas puede pisar lo que el Presenter fijó. Si el estado del campo lo gobierna el Presenter (ver `saveEnabled` en la referencia del stack), prueba el caso: el valor y el error tras recrear deben ser los del Presenter.

## Qué no cubren

No sustituyen la prueba en el dispositivo de lo que la plataforma decide (permisos de red, biometría, el comportamiento real del sistema al matar el proceso). Esos puntos van a la lista de verificación en el dispositivo de la entrega, marcados "sin test" si no hay forma de cubrirlos en la JVM.
