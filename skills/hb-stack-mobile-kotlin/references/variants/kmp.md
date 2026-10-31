# Variante: Kotlin Multiplatform (Compose Multiplatform)

## Stack

| Área | Elección |
| --- | --- |
| UI | Compose Multiplatform + Material 3 (UI compartida) |
| ViewModel y lifecycle | AndroidX multiplataforma (`ViewModel`, `collectAsStateWithLifecycle`, `SavedStateHandle`) |
| DI | Koin. Para proyectos grandes que necesiten validación del grafo en compilación: Metro |
| Navegación | Navigation 3 de Compose Multiplatform |
| Base de datos | Room KMP (`BundledSQLiteDriver`) |
| Preferencias | DataStore KMP |
| Red | Ktor (motor OkHttp en Android, Darwin en iOS) + kotlinx.serialization |
| Textos y recursos | Compose Resources (`Res.string.*`, `Res.drawable.*`) |
| Configuración y secretos | BuildKonfig |
| Imágenes | Coil 3 |
| Tests | kotlin-test, Turbine, coroutines-test, Compose UI test, Roborazzi (en el host Android), Kover |

## Estructura del proyecto

Es la estructura actual de JetBrains, obligatoria con AGP 9 cuando un módulo mezcla KMP con la app Android:

```
shared/      librería KMP: org.jetbrains.kotlin.multiplatform + com.android.kotlin.multiplatform.library
  src/commonMain/kotlin/<paquete>/   core/, feature/<nombre>/{domain,data,ui,di}, navigation/
  src/androidMain/kotlin/<paquete>/  implementaciones Android (mismos paquetes)
  src/iosMain/kotlin/<paquete>/      implementaciones iOS
  src/commonTest/                    tests compartidos
  src/androidHostTest/               tests JVM del lado Android (Robolectric, Roborazzi)
androidApp/  com.android.application: solo el punto de entrada (Application, Activity)
iosApp/      proyecto Xcode: solo el punto de entrada
```

Si la UI de iOS es nativa (SwiftUI), `shared` se divide en `sharedLogic` y `sharedUI`.

## Código de plataforma

- Primero busca una librería multiplataforma. Solo si no existe, escribe código de plataforma.
- **Prefiere una interfaz en `commonMain` con una implementación por plataforma, inyectada por DI.** Es más testeable que `expect class`.
- `expect`/`actual` para funciones pequeñas o factories (`expect fun platformModule(): Module`). Las clases `expect`/`actual` siguen en Beta.

```kotlin
// commonMain
interface SecureStorage {
    suspend fun save(key: String, value: String)
    suspend fun read(key: String): String?
    suspend fun delete(key: String)
}
// androidMain: Keystore + Tink · iosMain: Keychain
```

## Koin

```kotlin
// feature/profile/di/ProfileModule.kt
val profileModule = module {
    singleOf(::OfflineFirstProfileRepository) bind ProfileRepository::class
    factoryOf(::ObserveProfileUseCase)
    viewModelOf(::ProfileViewModel)
}
```

- Un módulo por feature, más `coreModule` y un `platformModule()` por plataforma.
- Se inicia una sola vez desde el punto de entrada (`KoinApplication` o `startKoin`).
- Argumentos de navegación: `koinViewModel { parametersOf(key.userId) }`.
- Un test con `verify()` de `koin-test` valida que el grafo se pueda resolver.

## Navigation 3

Igual que en Android, pero en iOS no hay serialización por reflexión: cada `NavKey` se registra.

```kotlin
// feature/profile/ui/ProfileNavigation.kt
@Serializable
data class ProfileNavKey(val userId: String) : NavKey

fun EntryProviderScope<NavKey>.profileEntry(onBack: () -> Unit) {
    entry<ProfileNavKey> { key ->
        ProfileScreen(onBack = onBack, viewModel = koinViewModel { parametersOf(key.userId) })
    }
}

// navigation/AppNavDisplay.kt
private val navConfig = SavedStateConfiguration {
    serializersModule = SerializersModule {
        polymorphic(NavKey::class) {
            subclass(HomeNavKey::class, HomeNavKey.serializer())
            subclass(ProfileNavKey::class, ProfileNavKey.serializer())
        }
    }
}

@Composable
fun AppNavDisplay() {
    val backStack = rememberNavBackStack(navConfig, HomeNavKey)
    NavDisplay(
        backStack = backStack,
        onBack = { backStack.removeLastOrNull() },
        entryDecorators = listOf(
            rememberSaveableStateHolderNavEntryDecorator(),
            rememberViewModelStoreNavEntryDecorator(),
        ),
        entryProvider = entryProvider {
            homeEntry(onOpenProfile = { id -> backStack.add(ProfileNavKey(id)) })
            profileEntry(onBack = { backStack.removeLastOrNull() })
        },
    )
}
```

## Room KMP

```kotlin
// commonMain — core/database
@Database(entities = [ProfileEntity::class], version = 1, exportSchema = true)
@ConstructedBy(AppDatabaseConstructor::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun profileDao(): ProfileDao
}

@Suppress("KotlinNoActualForExpect")
expect object AppDatabaseConstructor : RoomDatabaseConstructor<AppDatabase> {
    override fun initialize(): AppDatabase
}
```

- Cada plataforma crea el builder con su ruta (Android: `context.getDatabasePath(...)`; iOS: el directorio de documentos) y comparte la configuración: `setDriver(BundledSQLiteDriver())` y `setQueryCoroutineContext(Dispatchers.IO)`.
- Mismas reglas de migraciones que en Android ([android.md](android.md)).

## DataStore KMP

```kotlin
fun createDataStore(producePath: () -> String): DataStore<Preferences> =
    PreferenceDataStoreFactory.createWithPath(produceFile = { producePath().toPath() })
```

Cada plataforma provee la ruta (Android: `filesDir`; iOS: el directorio de documentos) desde su `platformModule`. Solo se accede desde `data`.

## Ktor

```kotlin
// core/network
fun createHttpClient(engine: HttpClientEngine, isDebug: Boolean) = HttpClient(engine) {
    install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
    if (isDebug) install(Logging) { level = LogLevel.HEADERS }
}
```

- El motor llega por DI: OkHttp en Android, Darwin en iOS.
- Nada de `LogLevel.ALL` ni logging en release: expone tokens y datos ([security.md](../security.md)).

## Recursos y configuración

- Textos en `composeResources/values/strings.xml` y sus traducciones; en código, `stringResource(Res.string.x)`.
- Valores de build y claves con BuildKonfig, leídos de `local.properties` o de variables de CI.
- Fechas con `kotlinx-datetime` y archivos con Okio.
- Permisos: una interfaz en `commonMain` con implementación por plataforma (o una librería multiplataforma como moko-permissions). En iOS, declara los `UsageDescription` en `Info.plist`.
