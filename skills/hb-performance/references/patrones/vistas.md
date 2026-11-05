# Patrones: Views (XML)

Aplica a layouts XML con o sin View Binding o Data Binding, `RecyclerView` y Epoxy. Cómo se ve en la evidencia → causa típica → arreglo.

## Inflado y layout

| Causa típica | Arreglo |
| --- | --- |
| `inflate` largo en `onCreateView` o `onCreate` (slice `inflate` grande en la traza) | Aplanar la jerarquía (`ConstraintLayout`), `ViewStub` para lo que no se ve al inicio, `<merge>` en includes |
| Muchas pasadas de `measure`/`layout` (slices `Choreographer#doFrame` con `measure` repetido) | Evitar `RelativeLayout` y `LinearLayout` con pesos anidados; tamaños fijos donde se pueda |
| Sobredibujado (capas de fondo apiladas) | Quitar fondos redundantes; revisarlo con "Debug GPU overdraw" en las opciones de desarrollador |

## Listas (`RecyclerView`, Epoxy)

| Causa típica | Arreglo |
| --- | --- |
| `notifyDataSetChanged()` en cada actualización | `ListAdapter` con `DiffUtil` (o `AsyncListDiffer`) |
| `onBindViewHolder` pesado (formateo, parseo, decodificar imágenes) | Precalcular en el modelo de UI; imágenes con la librería y su tamaño |
| `RecyclerView` anidados sin `RecycledViewPool` compartido | Compartir el pool; `setInitialPrefetchItemCount` en los horizontales |
| Epoxy sin IDs estables o con `requestModelBuild()` repetido en ráfaga | IDs estables; agrupar las actualizaciones; construir modelos fuera del hilo principal si el proyecto lo permite |
| Ráfaga de `inflate` al llegar cada respuesta (`inflate_tras_http.sql`) | El adapter, el listener o las vistas se configuran de nuevo en cada actualización; un `PagerAdapter` que no quita la vista en `destroyItem`. Configurarlos una vez por vista y actualizar solo los datos |
| `setHasFixedSize(false)` cuando el tamaño no cambia | `setHasFixedSize(true)` |

## Transiciones y animaciones

- Lottie o animaciones pesadas durante una transición de pantalla: compiten por el mismo frame. Medir con y sin la animación.
- `WebView` creado en el momento de mostrarlo: su primera creación es cara; precargarlo o mostrar un estado intermedio.

## Fragments

- Transacciones con `commitNow()` en cadena en el hilo principal: agruparlas.
- El fragment vuelve a cargar al volver atrás porque recrea su vista: el estado debe vivir fuera de la vista ([red.md](red.md)).
- View Binding guardado en un campo del fragment sin limpiarlo en `onDestroyView`: retiene toda la jerarquía ([memoria.md](memoria.md)).
