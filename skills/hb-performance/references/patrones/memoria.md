# Patrones: memoria

## Cómo detectar una fuga

1. Mide con `perf.py capturar --memoria`: deja `pss_mb`, `java_heap_mb`, `activities` y `views` después de cada corrida ([medicion.md](../medicion.md)).
2. El flujo tiene que terminar en el mismo punto donde empezó.
3. Si `activities`, `views` o el Java heap crecen corrida tras corrida, hay sospecha de fuga.
4. Pide a `android-profiler` un heap dump y las instancias retenidas de las pantallas del alcance, con su camino a la raíz del GC.
5. Si el proyecto usa LeakCanary en debug, sus reportes del mismo recorrido son evidencia válida.

Una sola medición no prueba nada: el heap sube y baja con el GC. Lo que cuenta es la tendencia entre repeticiones.

## Causas típicas

| Causa | Arreglo |
| --- | --- |
| Listeners, callbacks u observadores registrados y nunca desregistrados (sensores, ubicación, broadcast receivers, callbacks de SDKs) | Desregistrar en el evento simétrico del ciclo de vida |
| Un singleton, un objeto estático o un `companion object` que guarda un `Context` de actividad, una vista o un fragment | Guardar el `applicationContext`, o no guardar la referencia |
| Suscripciones o corrutinas vivas que capturan la pantalla ([rxjava.md](rxjava.md), [corrutinas-flow.md](corrutinas-flow.md)) | Cancelarlas con el ciclo de vida |
| `Handler` con mensajes diferidos que referencian la pantalla | `removeCallbacksAndMessages(null)` al destruir |
| Binding de un fragment sin limpiar en `onDestroyView` | Ponerlo en `null` en `onDestroyView` |
| Presenters o ViewModels retenidos que guardan la vista | Desvincular la vista al destruirla |

## Memoria alta sin fuga

- Bitmaps más grandes que lo que se muestra: decodificar al tamaño de la vista.
- Cachés en memoria sin límite: `LruCache` o el límite de la librería.
- Listas completas cargadas en memoria: paginación.
- `Graphics` alto en `meminfo`: texturas, imágenes y capas de hardware; revisar imágenes y animaciones del alcance.
