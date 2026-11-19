# Patrones: memoria en un flujo de repetición

Cómo leer un flujo de repetición para memoria (`"tipo": "repeticion"`, [ficha.md](../ficha.md) · Flujo de repetición para memoria): el mismo ciclo (abrir y cerrar un detalle, cambiar de pestaña) repetido N veces en una corrida, con una foto de la memoria (`dumpsys meminfo`) antes, después y entre ciclos (`perf.py ciclo`). Cada corrida deja `ciclos`, la memoria al final (`pss_mb`, `java_heap_mb`, `views`, `activities`) y cuánto creció desde el inicio (`pss_crecimiento_mb`, `java_heap_crecimiento_mb`, `views_crecimiento`, `activities_crecimiento`). `perf.py` aplica las reglas de abajo y dice "sin evidencia de fuga", "sospecha de fuga" o "ciclos insuficientes para decirlo", con su motivo; la sesión 2 cita esa línea y no la recalcula.

## Qué mirar entre ciclos

| Medida | Normal | Sospecha |
| --- | --- | --- |
| `activities` (actividades vivas) | Vuelve al mismo número al terminar cada ciclo | Sube con los ciclos: media actividad o más por ciclo (una que no se libera al cerrarla) |
| `views` (vistas vivas) | Sube y baja con la pantalla que está al frente | Crece en **cada** ciclo y suma más del 10 % sobre el inicio |
| `java_heap_mb` (objetos de la app) | Sube y baja con el GC; puede subir los primeros ciclos (cachés que se llenan) y estabilizarse | Crece en **cada** ciclo, sin bajar nunca, y suma más del 20 % |
| `pss_mb` (memoria total) | Crece los primeros ciclos (código compilado, cachés de imágenes) y se estabiliza | Crece de forma pareja hasta el final, junto con el heap o las vistas |

- **Una caché que se llena no es una fuga:** crece rápido al principio y se aplana. Una fuga crece de forma pareja, ciclo tras ciclo.
- **El GC mueve el heap:** un valor solo no dice nada; cuenta la tendencia de todos los ciclos.
- **El retraso que crece con los ciclos** (una acción que tarda más en el ciclo 10 que en el 1) se mira con la traza liviana: si el tiempo de los servicios no cambia y el de la app sí, es trabajo que se acumula en la app (listas que se rearman, observadores duplicados).

## Cuántos ciclos hacen falta

- **Al menos 5 ciclos entre fotos** para decir "sin evidencia" o "sospecha"; con menos, `perf.py` dice "ciclos insuficientes para decirlo".
- **3 corridas o más** con el mismo resultado: una sola corrida puede caer en un GC.
- Más ciclos no siempre es mejor: con traza, cada ciclo pesa (la corrida de prueba dice cuántos caben bajo el tope); sin traza (`"traza": "sin"`), los ciclos solo cuestan tiempo.

## Cuándo pasar a Android Studio Profiler

Con "sospecha de fuga", la causa no sale de estas medidas: hace falta un heap dump con las instancias retenidas y su camino a la raíz del GC. Eso es **fuera de la skill**: Android Studio Profiler (Memory) o `android-profiler`, sobre el mismo recorrido. El hallazgo queda "sin confirmar" hasta tener ese camino ([memoria.md](memoria.md) · Causas típicas).
