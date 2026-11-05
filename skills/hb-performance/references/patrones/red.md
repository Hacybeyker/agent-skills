# Patrones: red

Aplica a cualquier cliente (OkHttp, Retrofit, Ktor, Apollo, Volley) y a cualquier arquitectura. Cómo se ve en la evidencia → causa típica → arreglo.

## Llamadas duplicadas

`red_solapadas` (la misma plantilla y la misma query en vuelo a la vez) o `red_repetidas_2s` mayores que 0, o más llamadas que las esperadas según el mapa del alcance. Las solapadas son la señal más clara.

La instrumentación agrega al nombre un hash corto de la query (`GET discover/movie #1a2b`): dos llamadas a la misma plantilla con otros parámetros (otra página, otro filtro) no son duplicadas. Las métricas por endpoint lo quitan. Si la query lleva un valor que cambia en cada llamada (un timestamp, un nonce), las duplicadas no se ven por el hash: compáralas por tiempo en `llamadas_solapadas`.

| Causa típica | Arreglo |
| --- | --- |
| La carga se dispara en dos momentos del ciclo de vida (al crear la vista **y** al reanudarla) | Un solo disparador, ligado al estado y no al ciclo de vida de la vista |
| Al volver atrás, la vista se recrea y vuelve a cargar | El estado vive en una capa que sobrevive a la vista (ViewModel, presenter retenido, caché) y se recarga solo si caducó |
| Un cambio de configuración (rotación, tema, tamaño de ventana) recrea todo | Lo mismo: el estado sobrevive y no se vuelve a pedir |
| Un flujo de datos frío tiene varios suscriptores y cada uno dispara su request | Compartir la fuente (ver corrutinas-flow.md o rxjava.md) |
| Varias pantallas o componentes piden lo mismo por separado | Un repositorio con caché en memoria o *single-flight* (una sola llamada en vuelo por clave) |
| Reintentos automáticos (en el cliente, en un interceptor o en el operador de reintento) | Reintentar solo errores transitorios, con límite y *backoff* |
| Varios requests concurrentes renuevan el token a la vez | Renovación sincronizada: uno renueva y el resto espera |
| Doble toque en un botón | Ignorar toques mientras la acción está en curso |

## Llamadas en cascada

Una `HTTP` empieza recién cuando termina la anterior, aunque no necesita su resultado.

- Causa: llamadas independientes encadenadas una tras otra.
- Arreglo: lanzarlas en paralelo y combinar los resultados; o pedir al backend un endpoint que agregue lo que la pantalla necesita.

## Llamadas lentas

Con las secciones de la skill, una llamada se reparte en `cola_ms` + `red_conexion_ms` + `ttfb_ms` + `cliente_ms`:

| Evidencia | Lectura |
| --- | --- |
| `ttfb_ms` es casi todo `ms` | El tiempo es del servidor (o de la red): evidencia para el equipo de backend |
| `cola_ms` alto con varias llamadas al mismo host | El dispatcher de OkHttp admite 5 por host (`maxRequestsPerHost`): las demás esperan. Menos llamadas en el arranque (un endpoint que agregue, priorizar lo visible) o, si el servidor lo soporta, subir el límite |
| `red_conexiones` igual a la cantidad de llamadas, o `red_conexion_ms` alto en el arranque | Cada llamada abre su conexión (DNS, TCP y TLS): con HTTP/2 deberían compartir una. Un solo `OkHttpClient` para la app; precalentar la conexión si la primera pantalla la necesita |
| `cliente_ms` alto (`ms` mucho mayor que `ttfb_ms`) | Respuesta grande, lectura lenta del body o conversión pesada: revisar paginación, campos innecesarios, compresión (`gzip`) y el parser |
| `cliente_ms` alto en todas las llamadas, o CPU alto en los hilos de red | Un interceptor de logging en nivel `BODY` (o un inspector de tráfico) activo fuera de debug: lee, copia y escribe cada respuesta completa. Solo en debug; en release, `NONE` o `BASIC` |
| Hueco antes del `HTTP`, con el hilo principal ocupado | La app tarda en disparar el request: trabajo previo en el hilo principal |
| Hueco después del `HTTP`, antes de que cambie la UI | Parseo o mapeo pesado al recibir: moverlo fuera del hilo principal o reducirlo |

## Llamadas que sobran

- Endpoints que la pantalla no muestra, o datos que se piden en cada visita sin haber cambiado: caché con expiración, `ETag`/`If-None-Match`, o cargar recién cuando el usuario lo necesita.
- *Polling* que sigue activo con la pantalla en segundo plano: atarlo a la visibilidad.

## Imágenes

- Imágenes descargadas en una resolución mayor a la que se muestra: pedir el tamaño de la vista o usar las transformaciones de la librería de imágenes.
- Sin caché de disco: cada visita las vuelve a bajar.
