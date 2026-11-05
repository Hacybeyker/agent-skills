# Patrones: arranque

Métricas: `ttid_ms` (del intent al primer frame), `ttfd_ms` (hasta `reportFullyDrawn`: el contenido visible) y `bind_application_ms` (`Application.onCreate` y los content providers). Consultas: `arranque_hitos`, `linea_hilo_principal`, `estado_primeros_frames`, `cpu_por_tramo`, `contencion_locks`.

## Leer el arranque

- **Lanzamiento → nace el proceso:** del sistema (fork del zygote). Negativo en `arranque_hitos` porque empieza antes que el proceso.
- **`bindApplication`:** content providers, inicializadores y `Application.onCreate`. Es de la app.
- **`activityStart` / `activityResume`:** `onCreate`, `onStart` y `onResume` de la primera actividad (en `setContent` o el `inflate`).
- **Primer `doFrame`:** la primera composición o el primer layout. Parte del tiempo es de la plataforma: en una ventana nueva, `relayoutWindow` y el primer `draw` esperan al sistema. Si `dormido_en_frames_largos` muestra que el hilo duerme ahí, no es de la app: no lo persigas.
- **TTID → TTFD:** lo que la primera pantalla espera para mostrar contenido real (base de datos, red, un spinner). Suele ser el tramo más largo y el que siente el usuario.
- **Qué marca el TTFD:** `reportFullyDrawn` cuando el contenido principal está visible. Si la mejora es mostrar contenido antes (render progresivo, caché), no muevas la marca: el TTFD mide lo mismo antes y después y la mejora se ve en una métrica de usuario hasta la primera marca visible. Mover la marca cambia la definición y el veredicto no prueba nada.

## Causas típicas

| Evidencia | Causa típica | Arreglo |
| --- | --- | --- |
| `bind_application_ms` alto | SDKs inicializados al arrancar aunque no se usen en la primera pantalla | Inicialización diferida, o en segundo plano si el SDK lo permite |
| Muchos `ContentProvider` antes de `onCreate` | Librerías que se inicializan solas con un provider | App Startup (`androidx.startup`) para controlarlos, o desactivar la inicialización automática |
| Disco, base de datos o criptografía en el hilo principal antes del primer frame | Leer preferencias, abrir la base o derivar claves en el hilo principal | Hacerlo en segundo plano y mostrar un estado intermedio |
| TTID bueno, TTFD malo, y `cpu_por_tramo` con un hilo de base de datos o de E/S ocupado durante el spinner | Apertura cara de la base (cifrado con derivación de clave por conexión, migraciones), consultas pesadas | Abrir la base una vez y en segundo plano desde el arranque; con cifrado, clave ya derivada (raw) en vez de passphrase |
| `contencion_locks` con hilos de la app esperando al mismo dueño | Varias consultas o inicializaciones compiten por un singleton o un pool | Un solo punto de inicialización; menos conexiones concurrentes al arrancar |
| Varias llamadas de red al mismo tiempo antes del primer contenido | La primera pantalla pide todo junto y compite con el render | Priorizar lo que se ve primero; caché para el resto |
| `cola_ms` o `red_conexion_ms` altos en las primeras llamadas | Conexiones en frío y el límite por host de OkHttp: las llamadas esperan turno o abren cada una su conexión | Menos llamadas al arrancar (un endpoint que agregue); un solo `OkHttpClient`; ver [red.md](red.md) |
| Grafo de DI construido entero al arrancar | Dependencias creadas antes de necesitarlas | Inyección diferida (`Lazy`, `Provider`, `by lazy`) en lo que no usa la primera pantalla |
| El primer arranque es mucho más lento que los siguientes, o mucho JIT en el hilo principal | Código sin compilar | Baseline Profile que cubra el arranque; medir siempre con el mismo estado de compilación (`perf.py capturar` lo fija) |
| Trabajo que antes esperaba a algo lento ahora compite con los primeros frames | Efecto secundario de una mejora: la cola se adelantó | Diferir lo que no es de la primera pantalla hasta después del primer frame |
