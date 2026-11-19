# Patrones conocidos de Android

Una lista corta y genérica que la sesión 2 revisa **contra la evidencia que ya tiene** (`diagnostico.md`, las advertencias de `estado.md`, la red por tramo): no es una lista de cosas para buscar en todo el código. Para cada patrón, qué buscar en la traza y qué en el código para confirmarlo. Si la traza no muestra la señal, el patrón no aplica: no lo explores.

| Patrón | En la traza | En el código, para confirmarlo |
| --- | --- | --- |
| **Una lista dentro de un contenedor con scroll** (RecyclerView dentro de NestedScrollView, o un Column con scroll que arma todas sus filas con `forEach`): mide todas sus filas de una vez y no recicla | Un `measure` o `RV OnLayout` largo al cargar la lista (cientos de ms), que crece con la cantidad de filas; `inflate` de todas las filas juntas | El contenedor con scroll alrededor de la lista; `isNestedScrollingEnabled = false` o una altura fija; una sola lista en la pantalla resuelve |
| **La misma llamada en cada cambio de pestaña** | En la red por tramo, el mismo servicio una vez por pestaña, con la misma respuesta | Un `ViewModel` (o un `Fragment`) por pestaña que vuelve a pedir lo mismo al volver a ser visible, sin caché ni estado compartido |
| **Llamadas en serie que podrían ir en paralelo** | En la línea de tiempo, una llamada empieza cuando termina la anterior y no usa su respuesta | Dos `suspend` o dos `flatMap` encadenados donde el segundo no depende del primero |
| **Una respuesta ya recibida que se descarta y se vuelve a pedir** | El mismo servicio dos veces en un tramo, con la marca de pantalla anterior distinta, o al volver de una pantalla | Un repositorio sin caché en memoria, un `Flow` frío que se vuelve a coleccionar, una recreación de la pantalla |
| **Trabajo pesado en el hilo principal al llegar los datos** | `inflate_tras_http`, o un slice largo justo después de la respuesta en `hilo_principal_top` | Parseo, mapeo o diff de listas en el hilo principal (`observe`, `collect` sin `flowOn`) |
| **Imágenes decodificadas en el hilo principal o sin tamaño** | Slices de decodificación (`decodeBitmap`, `BitmapFactory`) en el hilo principal | Carga sin el tamaño del destino, o sin la librería de imágenes del proyecto |
| **Una pantalla que se arma dos veces** | Dos `inflate` o dos marcas de contenido visible en la misma carga | Un observador registrado dos veces, `notifyDataSetChanged` en vez de un diff, una recreación por configuración |

Cada uno se escribe como hallazgo solo si está **confirmado**: con la evidencia de la traza y `archivo:línea` ([diagnostico.md](../diagnostico.md) · Entregable). Lo que no se pudo confirmar va como "sin confirmar", y lo que la traza desmiente, como "descartado".
