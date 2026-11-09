# Capa de presentación: MVVM con UDF

El estado baja (ViewModel → UI) y las acciones suben (UI → ViewModel). Es la forma que recomienda Google, con la disciplina que usan los equipos grandes: un estado y un punto de entrada por pantalla.

## UiState

- Un `uiState: StateFlow<XUiState>` por pantalla. Si la pantalla muestra datos que no tienen relación entre sí, puede exponer más de uno.
- `data class` inmutable cuando los datos conviven (contenido + carga + mensaje). `sealed interface` cuando los estados se excluyen (`Loading`, `Success`, `Error`).
- Solo tipos inmutables: `List`, no `MutableList`.
- Desde flujos de otras capas: `stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), inicial)`. El margen de 5 s evita reiniciar el flujo al rotar la pantalla.
- Para estado que nace en la propia pantalla (lo que escribe el usuario): un `MutableStateFlow` privado expuesto como `StateFlow`, actualizado con `update { }`.

```kotlin
class EditProfileViewModel(
    observeProfile: ObserveProfileUseCase,
    private val updateName: UpdateNameUseCase,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val draftName = savedStateHandle.getStateFlow(KEY_NAME, "")
    private val transient = MutableStateFlow(Transient())

    val uiState: StateFlow<EditProfileUiState> =
        combine(observeProfile(), draftName, transient) { profile, name, t ->
            EditProfileUiState(profile = profile, name = name, isSaving = t.isSaving,
                isSaved = t.isSaved, userMessage = t.userMessage)
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), EditProfileUiState())

    fun onAction(action: EditProfileAction) {
        when (action) {
            is EditProfileAction.NameChanged -> savedStateHandle[KEY_NAME] = action.name
            EditProfileAction.Save -> save()
            EditProfileAction.UserMessageShown -> transient.update { it.copy(userMessage = null) }
        }
    }

    private fun save() = viewModelScope.launch {
        transient.update { it.copy(isSaving = true) }
        updateName(draftName.value)
            .onSuccess { transient.update { it.copy(isSaving = false, isSaved = true) } }
            .onFailure { transient.update { it.copy(isSaving = false, userMessage = UserMessage.SaveFailed) } }
    }

    private data class Transient(val isSaving: Boolean = false, val isSaved: Boolean = false,
        val userMessage: UserMessage? = null)

    private companion object { const val KEY_NAME = "name" }
}
```

## Acciones

- Un `sealed interface XAction` y un único `fun onAction(action: XAction)`. Es la llamada a método que pide Google, con un `when` exhaustivo y un solo lugar para logs y analytics.
- Nombra las acciones por lo que pasó, no por lo que debe hacer el ViewModel: `NameChanged`, `RetryClicked`, `UserMessageShown`.
- Las acciones que solo navegan no pasan por el ViewModel (ver Navegación).

## Eventos: siempre como estado

El ViewModel **no envía eventos a la UI**: nada de `Channel`, `SharedFlow` ni `Effect`. Google lo marca como muy recomendado, porque un evento puede perderse si la UI no está activa cuando se emite.

- Procesa el evento en el ViewModel y refleja el resultado en el estado.
- **Mensajes transitorios** (snackbar, toast): un campo `userMessage` en el estado. La UI lo muestra y confirma con una acción, y el ViewModel lo limpia.

```kotlin
uiState.userMessage?.let { message ->
    val text = stringResource(message.textRes)
    LaunchedEffect(message) {
        snackbarHostState.showSnackbar(text)
        onAction(EditProfileAction.UserMessageShown)
    }
}
```

- Representa los mensajes con un tipo propio (`sealed interface UserMessage`), no con textos: el ViewModel no resuelve recursos.

## Navegación

La navegación es responsabilidad de la UI.

- **La inicia el usuario** (un toque): el `Screen` recibe lambdas como `onOpenDetail: (String) -> Unit` y las llama directamente. No pasa por el ViewModel.
- **Depende de un resultado** (guardar, iniciar sesión): el ViewModel expone el resultado como estado (`isSaved = true`) y la UI navega al verlo.

```kotlin
@Composable
fun EditProfileScreen(onSaved: () -> Unit, viewModel: EditProfileViewModel = /* hiltViewModel() o koinViewModel() */) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val currentOnSaved by rememberUpdatedState(onSaved)
    LaunchedEffect(uiState.isSaved) { if (uiState.isSaved) currentOnSaved() }
    EditProfileContent(uiState = uiState, onAction = viewModel::onAction)
}
```

- Si el destino queda en el back stack después de navegar, confirma ese estado con una acción (como con los mensajes) para que no se repita al volver.
- El `NavKey` de la feature vive en `ui/XNavKey.kt` y su entry builder en `ui/XNavigation.kt`. El shell de la app solo junta los entry builders ([variants/android.md](variants/android.md), [variants/kmp.md](variants/kmp.md)).

## Screen y Content

| | `XScreen` | `XContent` |
| --- | --- | --- |
| Estado | Con estado | Sin estado |
| Recibe | Lambdas de navegación | `uiState`, `onAction` y lambdas de navegación |
| Hace | Obtiene el ViewModel, colecta con `collectAsStateWithLifecycle()`, reacciona a estados de navegación | Dibuja el estado y emite acciones |
| Lo usan | El grafo de navegación | `@Preview`, tests de UI y screenshot tests |

## Paginación

- **La lógica no va en la UI.** Cuándo pedir la siguiente página, el cursor o el offset, evitar páginas duplicadas, el fin de la lista y el error por página viven en el **dominio** (un use case, o una clase de paginación en `domain`), o en un helper de una capa que la cobertura mida. Si queda en `ui/` junto a los composables, queda fuera del gate de Kover y sin tests, que es donde los defectos de paginación se esconden.
- **El `UiState` expone el resultado:** los ítems, `isLoadingMore`, `endReached` y `loadMoreError`. La UI solo emite `LoadMore` cuando el usuario se acerca al final, y el ViewModel lo ignora mientras `isLoadingMore` o `endReached` (así repetir la acción no cuesta nada).
- **Cuidado con `layoutInfo` antes del primer layout.** Antes de que la lista se mida, `layoutInfo.totalItemsCount` es 0 y `visibleItemsInfo` está vacío; "estar cerca del final" resulta cierto y se pide la página siguiente antes de mostrar la primera, o se encadenan páginas. Una guarda lo evita: sin ítem visible, no hay nada que pedir.

```kotlin
LaunchedEffect(listState) {
    snapshotFlow {
        val info = listState.layoutInfo
        val lastVisible = info.visibleItemsInfo.lastOrNull()?.index   // null hasta el primer layout
        lastVisible != null && lastVisible >= info.totalItemsCount - PREFETCH_DISTANCE
    }
        .distinctUntilChanged()
        .filter { it }
        .collect { onAction(MovementsAction.LoadMore) }
}
```

- Un test de UI compone la lista con la primera página y comprueba que **no** se pidió la siguiente antes del primer layout, y que sí se pide al llegar al final.
- En `RecyclerView`, la misma trampa: `findLastVisibleItemPosition()` devuelve `NO_POSITION` (-1) antes del primer layout, así que `-1 >= total - umbral` también puede dar cierto. Guarda ese caso.

## Estado que sobrevive

| Estado | Dónde |
| --- | --- |
| Datos de la app | Repositorios (base de datos o red); el ViewModel los vuelve a leer |
| Lo que el usuario escribió y no guardó | `SavedStateHandle` en el ViewModel |
| Estado visual efímero (scroll, campo expandido) | `rememberSaveable` en el composable |

## Reglas de ViewModel

- ViewModels solo a nivel de pantalla o destino de navegación. Los componentes reutilizables usan *state holders* simples (una clase con `remember`), con su estado elevado.
- Nunca `AndroidViewModel`, `Context`, `Activity` ni `Resources` en el ViewModel. Si algo necesita `Context`, pertenece a `data` o a la UI.
- El ViewModel orquesta use cases: no contiene reglas de negocio ni accede a repositorios.
