# Variante: Android nativo

## Stack

| Área | Elección |
| --- | --- |
| UI | Jetpack Compose + Material 3, una sola Activity |
| DI | Hilt |
| Navegación | Navigation 3 |
| Base de datos | Room |
| Preferencias | DataStore |
| Red | Retrofit o Ktor (motor OkHttp) + kotlinx.serialization |
| Imágenes | Coil 3 |
| Tests | JUnit 4, Turbine, coroutines-test, Robolectric, Roborazzi, Kover |

## Estructura

```
app/src/main/kotlin/<paquete>/
├── App.kt                 @HiltAndroidApp
├── MainActivity.kt        @AndroidEntryPoint, setContent { AppTheme { AppNavDisplay() } }
├── navigation/            AppNavDisplay: back stack y registro de las entries
├── core/                  designsystem, database, network, common, testing
└── feature/<nombre>/      domain, data, ui, di   (architecture.md)
```

## Hilt

```kotlin
// feature/profile/di/ProfileModule.kt
@Module
@InstallIn(SingletonComponent::class)
internal abstract class ProfileModule {
    @Binds
    abstract fun bindProfileRepository(impl: OfflineFirstProfileRepository): ProfileRepository
}

// feature/profile/domain/usecase/ObserveProfileUseCase.kt
class ObserveProfileUseCase @Inject constructor(private val repository: ProfileRepository) {
    operator fun invoke(userId: String): Flow<Profile> = repository.observeProfile(userId)
}
```

- Use cases, repositorios y fuentes con `@Inject constructor`. `@Binds` para unir interfaz e implementación.
- Lo transversal (base de datos, cliente HTTP, dispatchers) se provee desde módulos en `core/`.
- ViewModel con argumentos de navegación: *assisted injection*.

```kotlin
@HiltViewModel(assistedFactory = ProfileViewModel.Factory::class)
class ProfileViewModel @AssistedInject constructor(
    @Assisted private val userId: String,
    observeProfile: ObserveProfileUseCase,
) : ViewModel() {
    @AssistedFactory
    interface Factory { fun create(userId: String): ProfileViewModel }
    // uiState y onAction (presentation.md)
}
```

## Navigation 3

Cada feature declara su `NavKey` y su entry. El shell de la app solo arma el back stack y las junta.

```kotlin
// feature/profile/ui/ProfileNavigation.kt
@Serializable
data class ProfileNavKey(val userId: String) : NavKey

fun EntryProviderScope<NavKey>.profileEntry(onBack: () -> Unit) {
    entry<ProfileNavKey> { key ->
        ProfileScreen(
            onBack = onBack,
            viewModel = hiltViewModel<ProfileViewModel, ProfileViewModel.Factory>(
                creationCallback = { factory -> factory.create(key.userId) },
            ),
        )
    }
}

// navigation/AppNavDisplay.kt
@Composable
fun AppNavDisplay() {
    val backStack = rememberNavBackStack(HomeNavKey)
    NavDisplay(
        backStack = backStack,
        onBack = { backStack.removeLastOrNull() },
        entryDecorators = listOf(
            rememberSaveableStateHolderNavEntryDecorator(),
            rememberViewModelStoreNavEntryDecorator(),   // un ViewModel por entry
        ),
        entryProvider = entryProvider {
            homeEntry(onOpenProfile = { id -> backStack.add(ProfileNavKey(id)) })
            profileEntry(onBack = { backStack.removeLastOrNull() })
        },
    )
}
```

- Las pantallas no conocen el back stack: reciben lambdas.
- Deep links: se traducen a `NavKey` en el shell, después de validarlos ([security.md](../security.md)).

## Room

- La clase `@Database` vive en `core/database/`. Cada feature aporta sus `@Entity` y DAO.
- `exportSchema = true`, con el esquema versionado (`room { schemaDirectory("$projectDir/schemas") }`).
- Migraciones explícitas o `AutoMigration`, con tests. **Nunca** `fallbackToDestructiveMigration` en producción.
- DAO: lecturas como `Flow`, escrituras `suspend`.

## DataStore

- Una fuente en `data/source/local/` por feature, expuesta al dominio a través del repositorio.
- Preferences DataStore para pares clave-valor. Proto DataStore cuando el esquema tiene estructura.

## Recursos

- Textos en `res/values/strings.xml` y sus traducciones (`values-es/`, `values-b+es+419/`, etc.).
- Íconos vectoriales en `res/drawable`. Los colores salen del tema, no de `colors.xml`.
