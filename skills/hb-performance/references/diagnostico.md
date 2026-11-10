# Sesión 2 · Diagnóstico

Cruza la evidencia con el código para encontrar las causas y propone un plan de mejoras. Es la sesión donde vale la pena razonar: las consultas ya las corrió el script. Termina con el **reporte inicial** y el comando con el que el usuario decide, sin chat, qué mejoras se aplican.

## 1. Punto de partida

1. Lee `estado.md` (ficha, mapa, hipótesis, "Métricas") y **`diagnostico.md` entero**: tiene las consultas listas sobre la corrida mediana y la peor. No vuelvas a correr esas consultas. Si no existe, el primer paso es `perf.py diagnostico --carpeta <carpeta>`.
2. Si no hay mapa (investigación creada con una receta), arma uno mínimo del camino medido, de 15 líneas como máximo. En el arranque: `Application`, content providers e inicializadores, la primera actividad, la primera pantalla, su ViewModel o presenter y su fuente de datos.
3. Carga solo los patrones del stack ([patrones/](patrones/)): en el arranque, [arranque.md](patrones/arranque.md); si hay métricas `red`, siempre [red.md](patrones/red.md).

## 2. Qué responde cada consulta de `diagnostico.md`

| Consulta | Responde |
| --- | --- |
| `arranque_hitos` | Lanzamiento del sistema (TTID), `bindApplication`, actividad, primeros frames, `NAV` y `reportFullyDrawn`, en ms desde que nace el proceso |
| `linea_hilo_principal` | El hilo principal en orden, con las marcas propias |
| `hilo_principal_top` | Los slices más largos del hilo principal |
| `estado_hilo_principal` | Si el hilo principal corre, espera CPU o duerme |
| `hijos_mas_largos` | Qué hay adentro de los slices largos |
| `dormido_en_frames_largos` | Dónde duerme el hilo principal dentro de los frames más largos (la plataforma o la app) |
| `estado_primeros_frames` | Los dos primeros frames: estado del hilo principal y qué otros hilos compiten por CPU |
| `frames_por_tramo` | Frames y jank por tramo: cuánto dura un spinner o una ráfaga |
| `cpu_por_tramo` | CPU por tramo del hilo principal, el RenderThread y el resto: qué trabaja mientras el usuario espera |
| `cpu_por_hilo` | CPU, espera y sueño por grupo de hilos (base de datos, red, dispatchers). Si el plan declara `hilos_ajenos`, los grupos que calzan con esas expresiones no son de la app: no los cuentes como trabajo de la app |
| `contencion_locks` | Hilos que esperan un lock, con su dueño y el lugar |
| `binder_hilo_principal` | IPC síncrono que bloquea el hilo principal |
| `jank_por_tipo` | Frames por tipo de jank |
| `linea_de_tiempo` | Marcas propias en orden: qué precede a cada llamada |
| `llamadas_solapadas`, `inflate_tras_http` | Cargas duplicadas y vistas recreadas con cada respuesta (si hay red) |

## 3. Una pregunta puntual

Solo para lo que `diagnostico.md` no responde, sobre una traza concreta y con `LIMIT`:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py consulta <carpeta>/antes/<flujo>_<n>.perfetto-trace.gz --sql "<consulta> LIMIT 20"
```

`consulta` toma el paquete del `plan.json` de la carpeta y acepta los nombres de las consultas de la skill y `--param CLAVE=valor`. Si escribes una consulta propia que vale la pena repetir, guárdala en `<carpeta>/diagnostico/` y, si mide algo por corrida, súmala a `metricas_sql` del plan.

## 4. Qué función gasta el CPU

Cuando un hilo gasta CPU y su slice no dice por qué (una base de datos, criptografía, parseo), una captura con muestreo:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --prueba --config cpu
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py consulta <carpeta>/prueba/<flujo>_1.perfetto-trace.gz cpu_por_libreria --param HILO='<prefijo-del-hilo>*'
```

Las librerías nativas sin símbolos muestran la librería y no la función; el código Java o Kotlin sale ofuscado por R8: desofúscalo con el mapping de profiling.

**Compose y R8: qué nombres trae la traza.** Sin composition tracing, la traza no nombra los composables: muestra los frames y cuánto duran, no qué función los ocupa. Con R8, las clases y los métodos de las muestras de CPU, las pilas y el heap salen ofuscados; las secciones propias (`MARK`, `NAV`, `HTTP`…) son texto y no cambian. Antes de atribuir un frame largo a un composable o a un método, consigue el nombre ([setup.md](setup.md) · Atribución en Compose y con R8); si no lo consigues, el hallazgo queda `sin confirmar` y, si el síntoma es estable, puede ir como mejora a prueba (abajo).

`android-profiler` queda para heap dumps y fugas, o el triage guiado de una traza anómala; su documentación es extensa: cárgala una vez, para esa pregunta. Para Compose, `jetpack-compose-performance`. Para ANR, `anr-audit-and-fix`.

## 5. Leer la red

- **Duplicados:** `red_solapadas` o `red_repetidas_2s` mayores que 0 (la misma plantilla **y** la misma query), o más llamadas que las esperadas en el mapa.
- **Dónde se va el tiempo de una llamada:** `ms` = `cola_ms` (cola del dispatcher e interceptores) + conexión nueva (`red_conexion_ms`: DNS, TCP y TLS) + `ttfb_ms` (servidor y red) + `cliente_ms` (envío, lectura del body y conversión). La lectura de cada una está en [red.md](patrones/red.md).
- **Huecos:** antes de la llamada, con el hilo principal ocupado, la app tarda en dispararla; después, antes de que cambie la UI, el parseo o el mapeo es pesado.

## 6. Descartar exige evidencia de la traza

Un hallazgo `descartado` afirma que la causa **no** ocurrió, y eso también se prueba: con un slice o una marca que muestran que corrió otro camino, o con una ausencia medible (0 llamadas, ningún slice con ese nombre, 0 ms en ese tramo). El valor de una configuración estática no alcanza.

- **Lo que se resuelve al ejecutarse se comprueba en la traza.** Si un camino del código depende de remote config, de un toggle por ambiente o por build type, de una prueba A/B o de un dato del backend, el valor que se lee en el código (una constante, un valor por defecto) puede no ser el que corrió en la variante medida. Busca en la traza cuál camino se ejecutó: una sección o un slice propios de ese camino (`perf.py consulta` con un `GLOB` del nombre), una llamada de red que solo hace uno de los dos, o la duración del tramo donde debería notarse.
- **Si la traza no los distingue,** no descartes: pide una marca temporal en cada camino ([setup.md](setup.md) · Cambios temporales) y una corrida de prueba, o deja el hallazgo `sin confirmar` y di qué falta.
- **Cruza cada hipótesis de la ficha con los picos medidos.** Un pico estable en el tramo donde la hipótesis lo predice es evidencia a favor aunque el código parezca decir lo contrario: explica el pico antes de descartar la hipótesis.
- **Un pico de una sola pantalla se diluye en la ventana.** Si el síntoma vive en un tramo (entrar a una pantalla, un scroll) y el plan no tiene su métrica, propón un `segmentos` para ese tramo ([ficha.md](ficha.md)): sale en todas las corridas, con ruido y veredicto.

## 7. Entregable

1. **Resumen ejecutivo** en `estado.md`, de 3 a 5 líneas, **también para el reporte inicial**: qué se midió, qué se encontró y qué se propone, o por qué no hay mejoras. Reemplaza el texto de la plantilla: `perf.py reporte` avisa si sigue ahí y no lo publica.
2. **Hallazgos** en `estado.md`, ordenados por impacto, con evidencia (métrica, consulta y `archivo:línea`). En "Tipo" usa una de estas palabras, porque el reporte las explica al lector:
   - `bug` (hay que corregirlo) o `mejorable` (intencional, se decide con el negocio): dan lugar a una mejora.
   - `consecuencia de H#`: lo arregla otro hallazgo.
   - `descartado`: se investigó y la traza muestra que no es la causa (sección 6). No genera mejora.
   - `sin confirmar` (antes `sin veredicto estadístico`, que se sigue leyendo): no se pudo confirmar ni descartar. No quiere decir que falten trazas ni que la captura fallara. Separa siempre las dos cosas en la fila: en "Síntoma" y "Evidencia", **si el síntoma es estable** (tiene su métrica, en cuántas corridas, con qué ruido) o si salió de una consulta sobre una o dos trazas; en "Causa raíz", que **la causa no está probada**; y en la columna **"Qué falta para decidir"**, lo que lo cerraría: una métrica propia del tramo (`segmentos`), otra clase de captura (`--config cpu`, composition tracing) o probar un cambio. Repetir las mismas corridas no lo cierra. Si el síntoma es estable y está fuera de presupuesto, da lugar a una mejora a prueba (abajo).

   La columna "Qué falta para decidir" es opcional (una tabla sin ella se sigue leyendo) y va vacía (`—`) en los demás tipos.
3. **`mejoras` en `plan.json`**, una por cambio que se pueda commitear solo:
   ```json
   {"id": "M1", "hallazgo": "H1", "titulo": "...", "flujo": "<flujo>", "metrica": "<métrica que debería moverse>",
    "esperado": "<valor o rango, por ejemplo ≤ 500 ms o -30 %>", "prioridad": "alta", "esfuerzo": "bajo",
    "riesgo": "bajo", "estado": "propuesta"}
   ```
   - `metrica` tiene que medir **lo mismo** antes y después. Si la mejora mueve la marca en la que termina (adelanta `reportFullyDrawn`, cambia una marca de usuario), la métrica cambia de definición y su veredicto no prueba nada: elige otra o agrega antes la marca que la mida igual en las dos fases.
   - Si la métrica no es principal ni existe, dilo: puede hacer falta una marca o una métrica propia antes de medir después.
   - `estado` siempre `propuesta`; el resto lo escribe `perf.py decidir`: `aprobada`, `descartada` o `pendiente` (la decisión del usuario) y `aplicada` (al terminar la sesión 3).
   - Si una mejora **reordena o paraleliza llamadas** y la métrica termina en una de ellas, la marca de fin puede dejar de ser la última: propón antes la marca de contenido visible (`PerfHooks.mark`) como fin de la métrica, o la última llamada.
   - **Mejora a prueba**, para un síntoma con métrica estable (sale en todas las corridas, con poco ruido) y fuera de presupuesto cuya causa no pudiste probar. En vez de dejarlo sin acción, propón el cambio más probable y deja que la medición de después decida:
     ```json
     {"id": "M2", "hallazgo": "H4", "a_prueba": true, "titulo": "<cambio propuesto>",
      "hipotesis": "<causa probable, en una frase, y por qué: el pico coincide con X>", "flujo": "<flujo>",
      "metrica": "<la métrica estable del síntoma, por ejemplo 'detalle hilo_max_ms'>", "esperado": "<efecto esperado, ≤ 16 ms>",
      "prioridad": "media", "esfuerzo": "bajo", "riesgo": "bajo", "estado": "propuesta"}
     ```
     Con `a_prueba`, `hipotesis`, `metrica` y `esperado` son obligatorios. El usuario la aprueba con `perf.py decidir`, como cualquier otra, y el reporte final dice `✔ hipótesis confirmada` o `✖ hipótesis refutada` según el veredicto de su métrica. No la uses si el síntoma no tiene métrica propia en todas las corridas (primero un `segmentos` o una métrica de usuario) ni para un cambio grande o riesgoso: una hipótesis refutada se revierte.
4. **Pendientes** en `estado.md`: lo que esta investigación no pudo cerrar. **No son mejoras** (las mejoras, también las que el usuario deje para después, viven en `plan.json`), y el reporte los titula así. Uno por línea, con cuatro datos: el síntoma y qué tan estable es; qué falta para cerrarlo; cuánto cuesta (una corrida, una captura con muestreo, una sesión); y la acción sugerida. Si lo que falta es una captura que el usuario puede correr ya, deja en esa línea el texto "Captura pendiente:" seguido del comando entre acentos graves, con la ruta real del plan (por ejemplo, Captura pendiente: `capturar --plan reports/perf/detalle/plan.json --prueba --config cpu`): `siguiente` la ofrece como comando antes del cierre.
5. **Reporte inicial**, que también dibuja el plan en `estado.md` y abre con el recuadro "Resultado" (cuántas mejoras y cuáles, o "Sin mejoras aplicables" con la razón de cada hallazgo, tomada de la tabla):
   ```bash
   cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py reporte --carpeta <carpeta> --inicial --html
   ```
6. **Siguiente paso:** `reporte --inicial` imprime el comando `perf.py decidir` y lo deja en `estado.md`. Si avisa que `estado.md` tiene partes sin completar (el Resumen, filas de la Ficha, la tabla de Hallazgos), complétalas y vuelve a generarlo antes de entregar. Muéstrale al usuario las mejoras en una tabla corta (id, título, métrica y esperado) y pega tal cual la salida de `siguiente`, que ya dice que es en la terminal y sin chat. **Sin mejoras**, dilo en la primera línea de tu respuesta, con la razón en una frase: `siguiente` ofrece el cierre corto (y la captura pendiente, si dejaste una), no otra sesión 2. Detente: `decidir` le da el chat de la sesión 3. No le pidas que vuelva a este chat ni el costo: lo anota con `perf.py consumo`.
