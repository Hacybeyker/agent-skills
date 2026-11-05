# Sesión 2 · Diagnóstico

Cruza las métricas con el código para encontrar las causas. Es la sesión donde vale la pena gastar tokens: el resto ya lo resolvió el script. Termina con **una sola aprobación**: los hallazgos y la elección de mejoras, juntos.

## 1. Punto de partida

Lee `estado.md`: ficha, mapa, hipótesis y "Métricas". No vuelvas a recorrer el proyecto: abre solo los archivos del mapa que cada hipótesis necesita, por rangos.

## 2. Consultas acotadas

Elige una o dos trazas representativas del estado inicial (por ejemplo, la de la mediana y la peor) y consúltalas con `perf.py consulta`, que limita las filas y el ancho:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py consulta <carpeta>/antes/<flujo>_3.perfetto-trace.gz hilo_principal_top.sql --paquete <applicationId>
```

Consultas listas en `assets/queries/diagnostico/` de esta skill:

| Consulta | Responde |
| --- | --- |
| `hilo_principal_top.sql` | Los 20 slices más largos del hilo principal y cuándo ocurren |
| `hijos_mas_largos.sql` | Qué hay adentro de esos slices |
| `linea_de_tiempo.sql` | Orden de `SCREEN`, `NAV`, `HTTP` y `TTFB`: qué precede a cada llamada |
| `llamadas_solapadas.sql` | Pares de llamadas al mismo endpoint en vuelo a la vez (carga duplicada) |
| `inflate_tras_http.sql` | Ráfagas de inflate después de cada respuesta (vistas o adapters recreados) |
| `jank_por_tipo.sql` | Frames por tipo de jank |
| `binder_hilo_principal.sql` | IPC síncrono que bloquea el hilo principal |

Para una pregunta puntual, `--sql "<consulta>"` con `LIMIT`. Nunca pidas una tabla entera.

## 3. Cuándo usar `android-profiler`

Solo para lo que las consultas no responden, y sobre una traza concreta: heap dumps y fugas, muestreo de CPU (funciones calientes cuando un slice no tiene nombre suficiente) o el triage guiado de una traza anómala. Su documentación es extensa: cárgala una vez, para esa pregunta.

Para Compose, `jetpack-compose-performance`. Para ANR, `anr-audit-and-fix`.

## 4. Leer la red

- **Duplicados:** `red_solapadas` o `red_repetidas_2s` mayores que 0, o más llamadas que las esperadas en el mapa.
- **Servidor o cliente:** si `ttfb_ms` es casi todo `ms`, el tiempo es del servidor: es evidencia para el equipo de backend, no algo que se arregle en la app. Si `cliente_ms` es alto, la respuesta es grande o la lectura es lenta.
- **Huecos:** antes de la llamada, con el hilo principal ocupado, la app tarda en dispararla; después, antes de que cambie la UI, el parseo o el mapeo es pesado.

## 5. Patrones

Usa solo los del stack, ya identificados en la ficha ([patrones/](patrones/)). Si encuentras una causa que no está en ninguno, anótala en "Patrones conocidos" de `## Rendimiento`.

## Entregable

En `estado.md`:

- **Hallazgos**, ordenados por impacto, con evidencia (métrica, traza o consulta y `archivo:línea`). Separa los **bugs** de lo **mejorable pero intencional**: lo intencional se decide con el negocio.
- **Pendientes** con receta completa (causa, `archivo:línea`, cambio, test, métrica y commit sugerido), para aplicarlos después sin repetir el diagnóstico.
- **Siguiente paso:** sesión 3, con las mejoras que el usuario eligió.

Muestra los hallazgos y espera **una** aprobación con la elección de mejoras.
