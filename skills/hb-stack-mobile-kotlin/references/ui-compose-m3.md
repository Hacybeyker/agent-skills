# UI: Compose y Material 3

## Design system (obligatorio)

Los tokens viven en `core/designsystem/` (`Color.kt`, `Type.kt`, `Shape.kt`, `Spacing.kt`, `Theme.kt`) junto con los componentes reutilizables. En un composable **nunca** se escribe `Color(0x…)`, un `.dp` o `.sp` sueltos, ni `FontFamily.Default`.

| Token | Acceso |
| --- | --- |
| Colores | `MaterialTheme.colorScheme.*` |
| Tipografía | `MaterialTheme.typography.*` |
| Formas | `MaterialTheme.shapes.*` |
| Espaciado | `MaterialTheme.spacing.*` (escala de 4 dp definida en `Spacing.kt`) |
| Textos | Android: `stringResource(R.string.x)`. KMP: `stringResource(Res.string.x)` (Compose Resources) |

### Tema

- Paletas propias en claro y oscuro. En Android 12+ puede usar color dinámico (`dynamicLightColorScheme` / `dynamicDarkColorScheme`). Si la marca exige colores fijos, el color dinámico se apaga.
- En KMP, el color dinámico solo existe en Android: decide la paleta con una función `expect`/`actual` o recibiéndola como parámetro.
- Toda pantalla funciona en claro y en oscuro.

## Composables

- **Screen / Content**: el primero tiene estado y el segundo no ([presentation.md](presentation.md)).
- **Elevación del estado** al ancestro común más cercano. El estado de negocio vive en el ViewModel; el estado visual efímero puede vivir en el composable con `rememberSaveable`.
- El primer parámetro opcional de un composable es `modifier: Modifier = Modifier`, y se aplica al elemento raíz.
- Componentes pequeños y reutilizables en `core/designsystem` cuando 2 o más features los usan.

### Efectos

| Necesitas | Usa |
| --- | --- |
| Reaccionar a un cambio de estado (mostrar un mensaje, navegar tras guardar) | `LaunchedEffect(clave)` |
| Lanzar una corrutina desde un clic | `rememberCoroutineScope()` |
| Trabajo al entrar o salir de primer plano | `LifecycleStartEffect` / `LifecycleResumeEffect` (nunca sobrescribir `onResume` de la Activity) |
| Liberar un recurso | `DisposableEffect` |
| Usar el valor más reciente de una lambda dentro de un efecto largo | `rememberUpdatedState` |
| Colectar un `Flow` del ViewModel | `collectAsStateWithLifecycle()` |

### Listas y recomposición

- `LazyColumn` / `LazyRow` con `key` estable en `items`, y `contentType` si hay varios tipos de ítem.
- `derivedStateOf` para valores que dependen de un estado que cambia muy rápido (por ejemplo, el scroll).
- Modelos de UI inmutables. El compilador de Compose ya usa *strong skipping*; las clases de otros módulos o librerías que sean estables se declaran en el archivo de configuración de estabilidad (`compose_stability.conf`). Detalle en [performance.md](performance.md).

### Previews

- `@Preview` siempre sobre `Content`, con estados falsos. Usa `@PreviewLightDark`, y agrega escalas de fuente grandes en pantallas con mucho texto.
- Un preview por estado relevante: carga, contenido, vacío, error.

## Layouts adaptativos y edge-to-edge

- La app dibuja de borde a borde: respeta el `innerPadding` del `Scaffold` y usa `Modifier.safeDrawingPadding()` o los `WindowInsets` donde haga falta (en iOS, la Dynamic Island y el indicador de inicio).
- Para tablets, plegables o escritorio, adapta el layout con `WindowSizeClass` y los componentes adaptativos de Material 3.

## Imágenes

Coil 3 con `AsyncImage` (funciona en Android y KMP): placeholder, imagen de error y tamaño definido.

## Accesibilidad

- `contentDescription` en todo ícono o imagen con significado, y `null` explícito en los decorativos.
- Área táctil mínima de **48 dp**.
- El significado nunca depende solo del color: acompáñalo con ícono o texto.
- Agrupa los elementos que se leen juntos con `Modifier.semantics(mergeDescendants = true)` y declara el rol de los elementos clicables personalizados.
- La UI no se rompe con texto al 200%.
