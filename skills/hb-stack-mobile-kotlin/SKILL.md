---
name: hb-stack-mobile-kotlin
description: 'Perfil de stack para apps Android nativas y Kotlin Multiplatform (Compose Multiplatform) con Clean Architecture + MVVM (UDF), organizadas por features: capas, contrato de presentación, Compose y Material 3, testing, seguridad (OWASP MASVS) y rendimiento. Variantes: android (Hilt, Navigation 3, Room) y kmp (Koin, Navigation 3 de CMP, Room KMP, Ktor). Úsala al implementar, revisar o diseñar código Kotlin/Compose en un proyecto Android o KMP: features, pantallas, ViewModels, repositorios, use cases, DI, navegación, tests o seguridad.'
license: MIT
metadata:
  author: hacybeyker
  version: "1.2.0"
  category: stack
  origin: "fusiona android-best-practices y kmp-best-practices"
---

# hb-stack-mobile-kotlin

Cómo se construye una app Android o Kotlin Multiplatform. Se basa en las recomendaciones oficiales de arquitectura de Android, la app de referencia Now in Android, la documentación de Kotlin Multiplatform y OWASP MASVS.

## 1. Antes de escribir código

1. Lee `AGENTS.md`. **Lo que diga el proyecto prevalece** sobre este perfil: stack, excepciones y comandos del DoD.
2. Elige la variante: la que indique `AGENTS.md` (`Variante: android` o `kmp`). Si no lo indica, es `kmp` cuando algún `build.gradle.kts` aplica `org.jetbrains.kotlin.multiplatform`, y `android` en otro caso.
3. Lee **solo** las referencias que la tarea necesita (tabla de la sección 5).
4. Si el código existente de la feature sigue otro patrón (por ejemplo `Effect` por `Channel`), mantén la coherencia dentro de esa feature y propone la migración: no mezcles dos estilos en el mismo archivo.

### Precedencia frente a otras skills

| Tipo de conocimiento | Orden |
| --- | --- |
| **Decisiones:** arquitectura, convenciones, estrategia de testing, política de dependencias | `AGENTS.md` > este perfil > skills externas |
| **Hechos técnicos actuales:** APIs, pasos de migración, versiones, comandos del CLI `android` | Las skills oficiales de Android, siempre que no contradigan una decisión |

Si una skill oficial muestra que un dato técnico de este perfil quedó viejo, sigue la oficial y avisa para actualizar el perfil.

## 2. Arquitectura

**Clean Architecture + MVVM con flujo de datos unidireccional (UDF), organizada por features.**

```
feature/<nombre>/
├── domain/   model/ (Kotlin puro) · repository/ (interfaces) · usecase/
├── data/     repository/ (implementaciones) · source/ (local, remote) · model/ (Entity, DTO) · mapper/
├── ui/       <Nombre>Screen · <Nombre>Content · <Nombre>ViewModel · <Nombre>UiState · <Nombre>Action · <Nombre>Navigation
└── di/       módulo de DI de la feature
core/         solo lo que usan 2 o más features: designsystem, database, network, common, testing
```

- **Regla de dependencia:** `ui → domain ← data`. El dominio es Kotlin puro: no conoce Android, Compose, Room, Ktor ni el framework de DI.
- **La capa de dominio siempre existe**, en proyectos chicos y grandes. El ViewModel solo habla con use cases, nunca con repositorios.
- Cuando el proyecto crezca, se modulariza como Now in Android (`:feature:<x>:api`/`:impl`, `:core:<x>`). Ver [architecture.md](references/architecture.md).

## 3. Contrato de presentación

```kotlin
data class ProfileUiState(                      // o sealed interface si los estados se excluyen
    val isLoading: Boolean = true,
    val profile: Profile? = null,
    val userMessage: UserMessage? = null,       // mensajes transitorios: también son estado
)

sealed interface ProfileAction {
    data object Refresh : ProfileAction
    data class NameChanged(val name: String) : ProfileAction
    data object UserMessageShown : ProfileAction
}

class ProfileViewModel(observeProfile: ObserveProfileUseCase, ...) : ViewModel() {
    val uiState: StateFlow<ProfileUiState> = observeProfile()
        .map { ProfileUiState(isLoading = false, profile = it) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProfileUiState())

    fun onAction(action: ProfileAction) { when (action) { /* ... */ } }
}
```

- **Un `uiState` (`StateFlow`) por pantalla y un único `onAction(Action)`.**
- **El ViewModel no envía eventos a la UI** (sin `Channel` ni `SharedFlow` de efectos). Los mensajes son estado que la UI confirma con una acción (`UserMessageShown`). La navegación la decide la UI mediante lambdas, y si depende de una validación, la UI reacciona a un estado.
- `Screen` es la versión con estado: obtiene el ViewModel y colecta con `collectAsStateWithLifecycle()`. `Content` no tiene estado: recibe `uiState` y `onAction`, y es el que usan los `@Preview` y los tests.

Detalle en [presentation.md](references/presentation.md).

## 4. Reglas que bloquean el merge

- Dependencias **solo en versiones estables** (sin `alpha`, `beta`, `rc` ni `snapshot`), declaradas en `gradle/libs.versions.toml` con `version.ref`. Ninguna versión literal en `build.gradle.kts` y ningún comentario en línea en el catálogo.
- El dominio no importa frameworks. Las entidades y DTO no salen de `data`: siempre se mapean a modelos de dominio.
- Una feature no importa el interior de otra: colaboran por `core/` o por contratos.
- Nada de lógica de negocio en composables. Nada de textos, colores, tamaños ni tipografías fijos: se usan recursos y tokens del design system.
- Inyección por constructor. El ViewModel no recibe `Context`, `Activity` ni `Resources`.
- Nada de `runCatching` en funciones `suspend`: atrapa la cancelación. Usa `suspendRunCatching` ([architecture.md](references/architecture.md)).
- Ningún secreto en el código ni en recursos ([security.md](references/security.md)).
- Toda lógica nueva llega con tests que usan fakes ([testing.md](references/testing.md)).

## 5. Referencias

| Necesitas… | Lee |
| --- | --- |
| Capas, estructura, modularización, errores, principios y patrones de diseño (SOLID, GRASP, GoF, KISS, YAGNI, DRY) | [architecture.md](references/architecture.md) |
| UiState, acciones, ViewModel, eventos, navegación, estado que sobrevive al proceso | [presentation.md](references/presentation.md) |
| Design system, Material 3, buenas prácticas de Compose, accesibilidad | [ui-compose-m3.md](references/ui-compose-m3.md) |
| Tests unitarios, de UI, de screenshots y benchmarks | [testing.md](references/testing.md) |
| Secretos, red, almacenamiento, ofuscación, endurecimiento | [security.md](references/security.md) |
| R8, Baseline Profiles, estabilidad de Compose, tiempo de arranque | [performance.md](references/performance.md) |
| Variante Android: Hilt, Navigation 3, Room, DataStore | [variants/android.md](references/variants/android.md) |
| Variante KMP: estructura, source sets, Koin, Navigation 3 de CMP, Room/DataStore KMP, Ktor | [variants/kmp.md](references/variants/kmp.md) |

## 6. Skills oficiales complementarias

Si están instaladas, úsalas para estas tareas (con la precedencia de la sección 1):

| Tarea | Skill |
| --- | --- |
| Navigation 3 avanzado: deep links, back stacks múltiples, scenes, devolver resultados | `navigation-3` |
| Edge-to-edge, insets del IME, legibilidad de las barras del sistema | `edge-to-edge` |
| Layouts adaptativos (tablets, plegables, escritorio, TV, XR) | `adaptive` |
| Recomposiciones y frames perdidos | `jetpack-compose-performance` |
| Trazas, jank, arranque, memoria, batería | `android-profiler` |
| Riesgos de ANR y stack dumps | `anr-audit-and-fix` |
| Keep rules redundantes o amplias | `r8-analyzer` |
| Seguridad de Intents y del manifest | `android-intent-security` |
| Permisos y componentes IPC | `android-permissions-security` |
| Políticas de Google Play | `play-policy-insights` |
| Uso del CLI `android` (proyectos, emuladores, SDK, documentación) | `android-cli` |

**No uses `testing-setup`:** su estrategia (mocks, otra herramienta de screenshots) choca con [testing.md](references/testing.md).

## 7. Checklist de calidad

- [ ] Pasa el DoD del proyecto (por ejemplo `./gradlew formatAndAnalyze` y `./gradlew test`).
- [ ] Cada use case, ViewModel, mapper y repositorio nuevo tiene sus tests con fakes.
- [ ] Cada `Content` nuevo o modificado tiene `@Preview` en claro y oscuro, y su screenshot test si es UI relevante.
- [ ] El dominio no importa frameworks.
- [ ] Se aplicaron los patrones que el problema pedía, sin agregar los que no (KISS, YAGNI).
- [ ] Toda dependencia nueva está en el catálogo y es estable.
- [ ] Se cumple el checklist de [security.md](references/security.md) si la tarea toca auth, red, almacenamiento o datos sensibles.
