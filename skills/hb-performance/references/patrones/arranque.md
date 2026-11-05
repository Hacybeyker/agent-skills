# Patrones: arranque

Solo si el flujo empieza en frío. Métricas: TTID (primer frame) y TTFD (contenido completo, si la app llama a `reportFullyDrawn()`).

| Evidencia | Causa típica | Arreglo |
| --- | --- | --- |
| `Application.onCreate` largo en la traza (`bindApplication`) | SDKs inicializados al arrancar aunque no se usen en la primera pantalla | Inicialización diferida, o en segundo plano si el SDK lo permite |
| Muchos `ContentProvider` antes de `onCreate` | Librerías que se inicializan solas con un provider | App Startup (`androidx.startup`) para controlarlos, o desactivar la inicialización automática |
| Disco, base de datos o criptografía en el hilo principal durante el arranque | Leer preferencias, abrir la base de datos o derivar claves antes del primer frame | Hacerlo en segundo plano y mostrar un estado intermedio |
| Grafo de DI construido entero al arrancar | Dependencias creadas antes de necesitarlas | Inyección diferida (`Lazy`, `Provider`, `by lazy`) en lo que no usa la primera pantalla |
| El primer arranque es mucho más lento que los siguientes | Código sin compilar | Baseline Profile que cubra el arranque; medir siempre con el mismo estado de compilación (`perf.py capturar` la fija; ver [medicion.md](../medicion.md)) |
| TTID bueno pero TTFD malo | La primera pantalla espera red o datos para mostrarse | Mostrar lo que hay en caché primero y actualizar después |
