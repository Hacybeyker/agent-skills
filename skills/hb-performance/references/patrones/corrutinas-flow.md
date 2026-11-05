# Patrones: corrutinas y Flow

Cómo se ve en la evidencia → causa típica → arreglo.

## Hilo principal ocupado

| Causa típica | Arreglo |
| --- | --- |
| Trabajo pesado en `viewModelScope.launch { }` o `lifecycleScope.launch { }` sin cambiar de dispatcher (los dos arrancan en `Dispatchers.Main`) | `withContext(Dispatchers.Default)` para CPU, `Dispatchers.IO` para disco y red; mejor aún, que la capa de datos cambie de dispatcher por dentro |
| Mapeo o filtrado de listas grandes en un `map { }` de Flow que se colecta en Main | `flowOn(Dispatchers.Default)` después de los operadores pesados |
| `runBlocking` en código de la app | Volverlo `suspend` |
| Disco, criptografía o Keystore en Main (base de datos, `SharedPreferences.commit()`, cifrado) | Moverlo a `Dispatchers.IO`; en preferencias, `apply()` o DataStore |
| CPU intensivo en `Dispatchers.IO` | `Dispatchers.Default`: IO tiene más hilos, pensados para esperar, no para calcular |

## Cargas repetidas

| Causa típica | Arreglo |
| --- | --- |
| Un `flow { }` o un `callbackFlow` frío colectado por varios lugares: cada colector repite el trabajo | `stateIn` o `shareIn` en el ViewModel o el repositorio |
| `stateIn(scope, SharingStarted.WhileSubscribed(...))` con un timeout corto: al rotar o volver, se vuelve a suscribir y recarga | `WhileSubscribed(5_000)` (sobrevive a cambios de configuración) o `Lazily`, según el caso |
| La carga se dispara en `init` del ViewModel y también desde la vista | Un solo disparador |
| `LaunchedEffect(clave)` cuya clave cambia más de lo esperado (un objeto nuevo en cada recomposición) | Claves estables; la carga, en el ViewModel |
| `repeatOnLifecycle` o `collectAsStateWithLifecycle` sobre un flujo frío que hace red | Compartir la fuente con `stateIn`, para que volver a primer plano no repita el request |

## Trabajo que sigue después de salir

- Corrutinas lanzadas en un scope que no se cancela con la pantalla (`GlobalScope`, un scope propio sin cancelar): siguen consumiendo y pueden retener la pantalla ([memoria.md](memoria.md)).
- Flujos colectados con `collectAsState` o `launchWhenX` siguen activos en segundo plano: `collectAsStateWithLifecycle` o `repeatOnLifecycle`.

## Concurrencia

- Llamadas independientes en secuencia (`val a = repo.a(); val b = repo.b()`): `coroutineScope { val a = async { repo.a() }; val b = async { repo.b() }; ... }`.
- `Mutex` o `synchronized` que serializa lo que podría ir en paralelo: revisar en la traza los hilos bloqueados esperando el lock.
