# Patrones: RxJava

Aplica a RxJava 2 y 3. Cómo se ve en la evidencia → causa típica → arreglo.

## Hilo principal ocupado

| Causa típica | Arreglo |
| --- | --- |
| `blockingGet()`, `blockingFirst()` o `blockingSubscribe()` en código de la app | Componer la cadena y suscribirse, sin bloquear |
| Mapeo pesado **después** de `observeOn(AndroidSchedulers.mainThread())` | Hacer el trabajo antes del `observeOn`, en `Schedulers.computation()` |
| Falta `subscribeOn(Schedulers.io())` en una fuente que toca disco, red o criptografía | `subscribeOn` en la fuente (idealmente dentro del repositorio) |
| CPU intensivo en `Schedulers.io()` | `Schedulers.computation()` |

## Cargas repetidas

| Causa típica | Arreglo |
| --- | --- |
| Un `Observable` o `Single` frío suscrito más de una vez: cada suscripción repite el request | `share()`, `replay(1).refCount()` o `cache()` según si los datos pueden caducar |
| La suscripción se crea al crear la vista **y** al reanudarla | Una sola suscripción, ligada al estado |
| `CompositeDisposable` que no se limpia al destruir la vista: al volver, se suma una suscripción nueva a la vieja | `clear()` al destruir la vista o desvincular el presenter; revisar que el presenter no sobreviva duplicado |
| `BehaviorSubject` o `replay()` que reemite el último valor y dispara de nuevo un efecto (como una carga) | Separar el estado (se reemite) de los eventos (se consumen una vez) |
| `retry()` o `retryWhen` sin límite ni filtro de error | Reintentar solo errores transitorios, con límite y *backoff* |

## Concurrencia

- `concatMap` o `flatMap` encadenando llamadas independientes: `zip` o `merge` para lanzarlas en paralelo.
- `flatMap` sin límite sobre una lista grande: dispara todos los requests a la vez; `flatMap(..., maxConcurrency)` o `concatMapEager`.

## Fugas

- Suscripciones vivas que capturan la vista, la actividad o el fragment (lambdas que los referencian): se liberan solo al `dispose()`. Revisar [memoria.md](memoria.md).
