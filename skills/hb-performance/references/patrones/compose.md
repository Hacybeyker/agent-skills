# Patrones: Jetpack Compose

Para el diagnóstico detallado de recomposiciones y fases, apóyate en la skill oficial `jetpack-compose-performance`. Esta lista sirve para formular hipótesis en la fase 2.

## Recomposiciones de más

| Causa típica | Arreglo |
| --- | --- |
| Parámetros inestables (clases mutables, `List` de otro módulo sin declarar, lambdas que capturan valores inestables): la función no se puede saltar | Modelos de UI inmutables; declarar las clases estables de otros módulos en el archivo de configuración de estabilidad del compilador |
| Leer en la función un estado que cambia en cada frame (posición de scroll, animación) | Pasarlo como lambda y leerlo en layout o dibujo: `Modifier.offset { }`, `graphicsLayer { }`, `drawBehind { }` |
| Derivar un valor del scroll en cada frame (por ejemplo, mostrar un botón según el índice visible) | `derivedStateOf` |
| Leer el estado demasiado arriba en el árbol: recompone todo lo de abajo | Leerlo lo más abajo posible |
| Cálculos costosos en la composición | `remember(claves)` o calcularlos en el ViewModel |

## Listas

- `LazyColumn`/`LazyRow` sin `key`: al cambiar la lista se recomponen y reubican ítems de más. Agregar `key` estable.
- Ítems de tipos distintos sin `contentType`: se reutilizan peor.
- Ítems pesados (imágenes sin tamaño, layouts anidados): medir el frame del scroll y simplificar el ítem.

## Trabajo fuera de lugar

- Efectos con claves que cambian en cada recomposición (`LaunchedEffect(objetoNuevo)`): se relanzan y pueden repetir cargas ([corrutinas-flow.md](corrutinas-flow.md)).
- Trabajo pesado en la composición o en el `init` de un objeto creado con `remember`: moverlo al ViewModel o a un dispatcher de fondo.

## Primera vez lento

- El primer render de una pantalla tarda más que los siguientes: suele ser código sin compilar. Revisa el estado de compilación ([medicion.md](../medicion.md)) y si el proyecto tiene un Baseline Profile que cubra ese flujo.
