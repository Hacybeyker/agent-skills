# Sesión 2 · Diagnóstico

Cruza la evidencia con el código para encontrar las causas y propone un plan de mejoras. Es la sesión donde vale la pena razonar: las consultas ya las corrió el script. Termina con el **reporte inicial** y el comando con el que el usuario decide, sin chat, qué mejoras se aplican.

## 1. Punto de partida

1. **Lee primero "Advertencias para el diagnóstico" de `estado.md`.** La escribe `perf.py` con lo que observó en los comandos de la terminal: los avisos de la última corrida de prueba, las corridas inválidas de cada fase y sus motivos (también los fallos de `preparar`), los avisos de las capturas (tasa de refresco, compilación, configuración distinta entre fases, emulador), lo que el diagnóstico no midió, el ruido entre antes y control de cada métrica principal con la mejora mínima que se podría demostrar, y los cambios temporales que alteran la app. Úsala así:
   - **Si una mejora que propones toca algo que una advertencia menciona, dilo en la mejora** (en su `titulo` o en su `hipotesis`, y en el hallazgo): un cambio temporal que altera la métrica de la mejora, una métrica cuyo ruido es mayor que lo que la mejora espera ganar, una consulta `no medido` de la que depende el hallazgo. Ejemplo: si la instrumentación agregó una espera antes de una búsqueda y propones un debounce, la mejora dice que la medición de antes ya incluía esa espera.
   - Una mejora cuyo `esperado` es menor que la "mejora mínima demostrable" de su métrica no se va a poder demostrar con esta línea base: dilo, y propón más corridas, otra métrica o una mejora a prueba.
   - Si la sección no existe (una investigación de una versión anterior), `perf.py siguiente --carpeta <carpeta>` la agrega.
2. Lee `estado.md` (ficha, mapa, hipótesis, "Métricas") y **`diagnostico.md` entero**: tiene las consultas listas sobre la corrida mediana y la peor. No vuelvas a correr esas consultas. Si no existe, el primer paso es `perf.py diagnostico --carpeta <carpeta>`.
3. Si no hay mapa (investigación creada con una receta), arma uno mínimo del camino medido, de 15 líneas como máximo. En el arranque: `Application`, content providers e inicializadores, la primera actividad, la primera pantalla, su ViewModel o presenter y su fuente de datos.
4. Carga solo los patrones del stack ([patrones/](patrones/)): en el arranque, [arranque.md](patrones/arranque.md); si hay métricas `red`, siempre [red.md](patrones/red.md).

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
| `bloqueo_hilo_principal` (solo en una captura con `--config completa`) | Por qué espera el hilo principal dentro de los frames más largos: en `D`, la función del kernel que lo bloquea y si es E/S; en `S`, el hilo que lo despertó |
| `jank_por_tipo` | Frames por tipo de jank |
| `linea_de_tiempo` | Marcas propias en orden: qué precede a cada llamada |
| `llamadas_solapadas`, `inflate_tras_http` | Cargas duplicadas y vistas recreadas con cada respuesta (si hay red) |
| Red por tramo (si el plan tiene `segmentos`) | Qué llamadas empiezan en cada tramo del flujo: cuántas, a qué endpoints, su duración y su TTFB medianos, las repetidas y las solapadas, y las que quedan fuera de todos los tramos |

### "No medido" no es "sin problema"

Cada consulta declara en su cabecera qué fuentes de la traza necesita (`-- requiere:`) y `perf.py` lo valida contra la configuración con la que se grabó **esa** traza (queda registrada junto a las trazas, en `configuracion.json`). Una consulta sin tabla sale al final de `diagnostico.md` de una de estas tres formas, y no se leen igual:

| Lo que dice | Qué quiere decir | Qué puedes afirmar |
| --- | --- | --- |
| `Medido y sin casos` | La configuración de la traza captura lo que la consulta necesita y no hubo filas | Que no ocurrió en esa corrida: sirve como evidencia para descartar (sección 8), salvo que ese dato no salga en **ninguna** corrida ni consulta de ese dispositivo (un kernel que no emite el evento): entonces compruébalo con `consulta --sql` antes de afirmarlo |
| `no medido: la configuración <nombre> no captura <fuente>` o `no medido: el dispositivo no entrega <fuente>` | La traza no tiene ese dato: la configuración no lo graba, o ese Android no lo tiene (FrameTimeline, antes de Android 12) | Nada. Si la pregunta importa, pide la captura con la configuración que sí lo trae (`cpu` o `completa`, con `--prueba`) |
| `configuración desconocida` | La traza es de una versión anterior de la skill y no se sabe qué capturó | Nada: no afirmes ausencia. Una corrida nueva lo resuelve |

Un hallazgo `descartado` nunca se apoya en una consulta "no medida" ni en una de "configuración desconocida".

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

La corrida de prueba no fija la compilación de ART: si el build se acaba de instalar y todavía no se midió ninguna fase con él, agrega `--compilar`, o el muestreo va a mostrar al intérprete y al JIT en lugar del código de la app. Las librerías nativas sin símbolos muestran la librería y no la función. El código Java o Kotlin sale ofuscado por R8 y `consulta` lo desofusca sola con el mapping de la variante medida (`--mapping <ruta>` si no lo encuentra o no lo puede verificar): si en la salida dice `Sin desofuscar`, lee el motivo antes de atribuir nada a una función ([setup.md](setup.md) · Desofuscación automática). Un nombre con varios candidatos (`A.x o A.y`) no está resuelto: confírmalo en el código.

**Compose y R8: qué nombres trae la traza.** Sin composition tracing, la traza no nombra los composables: muestra los frames y cuánto duran, no qué función los ocupa. Con R8, las clases y los métodos de las muestras de CPU, las pilas y el heap salen ofuscados; las secciones propias (`MARK`, `NAV`, `HTTP`…) son texto y no cambian. Antes de atribuir un frame largo a un composable o a un método, consigue el nombre ([setup.md](setup.md) · Atribución en Compose y con R8); si no lo consigues, el hallazgo queda `sin confirmar` y, si el síntoma es estable, puede ir como mejora a prueba (abajo).

`android-profiler` queda para heap dumps y fugas, o el triage guiado de una traza anómala; su documentación es extensa: cárgala una vez, para esa pregunta. Para Compose, `jetpack-compose-performance`. Para ANR, `anr-audit-and-fix`.

## 5. Por qué espera el hilo principal

`dormido_en_frames_largos` dice **dónde** duerme el hilo principal dentro de los frames más largos, no **por qué**. Cuando esa espera pesa (25 % o más del tiempo de los 3 frames más largos en `S` o `D`, o una espera de 4 ms o más en `D`; son las constantes `BLOCKED_SHARE_MIN` y `BLOCKED_D_MIN_MS` de `perf.py`), `perf.py diagnostico` deja en `diagnostico.md` una "Captura pendiente" con el comando, y `siguiente` la ofrece como paso opcional antes del chat:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --prueba --config completa
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py consulta <carpeta>/prueba/<flujo>_1.perfetto-trace.gz bloqueo_hilo_principal
```

- **`D` (bloqueado sin poder interrumpirse):** `bloqueado_en` trae la función del kernel y si es E/S (lectura de disco, una falla de página, un lock del kernel). `no disponible en este dispositivo` quiere decir que el kernel no emite la razón de bloqueo: no es "sin bloqueos".
- **`S` (dormido):** `lo_desperto` trae el hilo y el proceso que lo despertaron: otro hilo de la app (espera un resultado: un `runBlocking`, un `Future.get`, un lock), un hilo de binder de otro proceso (IPC síncrono; crúzalo con `binder_hilo_principal`) o el sistema.
- La señal sale de los frames largos y no de `estado_hilo_principal`, que cubre toda la traza: el hilo principal duerme legítimamente cuando no tiene nada que hacer.
- `completa` pesa varias veces más que `base`: es para entender, con `--prueba`; no para medir fases.

## 6. Por qué se cerró la app

Si una corrida salió inválida con "la app salió: <motivo>", o el síntoma es que la app se cierra, se reinicia o pierde el estado, el sistema guarda el motivo de cada salida del proceso (Android 11 o superior):

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py salidas --carpeta <carpeta> --limite 10
```

Imprime una tabla corta con la hora (del dispositivo), el pid, el motivo en claro (crash, crash nativo, ANR, poca memoria, uso excesivo de recursos, señal, detenida por el sistema o a pedido del usuario), la descripción y la memoria (PSS y RSS) al salir. Para un crash agrega el inicio de su pila, desofuscada si hay mapping. `--paquete` en vez de `--carpeta` si no hay investigación; `--desde "AAAA-MM-DD HH:MM"` acota.

- **Poca memoria** con un PSS alto apunta a la app; con un PSS normal, a la presión del dispositivo (otras apps): no es un hallazgo de la app sin más evidencia (`--memoria`, `android-profiler`).
- **Uso excesivo de recursos** y **ANR** traen la causa en la descripción; para la traza del ANR, `anr-audit-and-fix`.
- Los cierres **a pedido** (un `force-stop`, reinstalar) también quedan registrados y no son fallas: `capturar` no invalida corridas por ellos.
- **Límite:** esto es lo que pasó en el dispositivo de quien investiga. Lo que pasa en los teléfonos de los usuarios se mira con Android vitals (Play Console), con Crashlytics o con `ProfilingManager` ([medicion.md](medicion.md) · Salidas inesperadas de la app); la skill no los integra.
- En Android 10 dice `no disponible (Android 11 o superior)`: no quiere decir que la app no se haya cerrado.

## 7. Leer la red

- **Duplicados:** `red_solapadas` o `red_repetidas_2s` mayores que 0 (la misma plantilla **y** la misma query), o más llamadas que las esperadas en el mapa.
- **Dónde se va el tiempo de una llamada:** `ms` = `cola_ms` (cola del dispatcher e interceptores) + conexión nueva (`red_conexion_ms`: DNS, TCP y TLS) + `ttfb_ms` (servidor y red) + `cliente_ms` (envío, lectura del body y conversión). La lectura de cada una está en [red.md](patrones/red.md).
- **Huecos:** antes de la llamada, con el hilo principal ocupado, la app tarda en dispararla; después, antes de que cambie la UI, el parseo o el mapeo es pesado.
- **Por servicio:** las filas `red <servicio> …` de `resumen.md` dicen, de cada servicio, cuántas veces se llama por corrida, cuánto tarda, cuánto de eso es el servidor (`ttfb_ms`) y cuánto la app (`cola_ms`, `conexion_ms`, `cliente_ms`), y si se repite o se solapa. El reporte las resume en "Servicios del flujo"; no armes esa tabla a mano. Son orientativas: sirven para ver patrones y a quién reportar un servicio lento, no para proponer una mejora de la app por el tiempo del servidor.
- **Por tramo:** con `segmentos`, la tabla "Red por tramo" de `diagnostico.md` dice qué llamadas hace la app en cada parte del flujo (cada llamada va al tramo donde empieza) y las métricas `<tramo> red_*` lo miden en todas las corridas. En un tramo con polling (la app consulta un estado hasta que cambia), la cantidad de llamadas depende de cuánto tardó lo que se espera, sea el backend o una persona: explica el patrón (cuántas consultas y cada cuánto) y compara medianas, sin leer una o dos llamadas de diferencia como hallazgo.

## 8. Descartar exige evidencia de la traza

Un hallazgo `descartado` afirma que la causa **no** ocurrió, y eso también se prueba: con un slice o una marca que muestran que corrió otro camino, o con una ausencia medible (0 llamadas, ningún slice con ese nombre, 0 ms en ese tramo). El valor de una configuración estática no alcanza.

- **Lo que se resuelve al ejecutarse se comprueba en la traza.** Si un camino del código depende de remote config, de un toggle por ambiente o por build type, de una prueba A/B o de un dato del backend, el valor que se lee en el código (una constante, un valor por defecto) puede no ser el que corrió en la variante medida. Busca en la traza cuál camino se ejecutó: una sección o un slice propios de ese camino (`perf.py consulta` con un `GLOB` del nombre), una llamada de red que solo hace uno de los dos, o la duración del tramo donde debería notarse.
- **Si la traza no los distingue,** no descartes: pide una marca temporal en cada camino ([setup.md](setup.md) · Cambios temporales) y una corrida de prueba, o deja el hallazgo `sin confirmar` y di qué falta.
- **Cruza cada hipótesis de la ficha con los picos medidos.** Un pico estable en el tramo donde la hipótesis lo predice es evidencia a favor aunque el código parezca decir lo contrario: explica el pico antes de descartar la hipótesis.
- **Un pico de una sola pantalla se diluye en la ventana.** Si el síntoma vive en un tramo (entrar a una pantalla, un scroll) y el plan no tiene su métrica, propón un `segmentos` para ese tramo ([ficha.md](ficha.md)): sale en todas las corridas, con ruido y veredicto.

## 9. Entregable

1. **Resumen ejecutivo** en `estado.md`, de 3 a 5 líneas, **también para el reporte inicial**: qué se midió, qué se encontró y qué se propone, o por qué no hay mejoras. Reemplaza el texto de la plantilla: `perf.py reporte` avisa si sigue ahí y no lo publica.
   **Resumen para gerencia**, en su sección de `estado.md`: de 3 a 5 líneas para un lector no técnico, sin nombres de métricas ni términos de la traza (qué notaba el usuario, qué se encontró y qué se propone, con los tiempos en segundos o en lo que se percibe). Es lo único que escribes para el reporte de gerencia: el resto lo arma `perf.py` con los mismos datos. Si falta, ese reporte sale igual y lo marca "sin completar". Ese reporte también publica, tal cual, las celdas "Síntoma" y "Causa raíz" de los hallazgos `bug` y `mejorable` y el `titulo` de cada mejora: escríbelos como frases que se entiendan sin el código (la referencia `archivo:línea` va en "Evidencia", que no se publica ahí).
2. **Hallazgos** en `estado.md`, ordenados por impacto, con evidencia (métrica, consulta y `archivo:línea`). En "Tipo" usa una de estas palabras, porque el reporte las explica al lector:
   - `bug` (hay que corregirlo) o `mejorable` (intencional, se decide con el negocio): dan lugar a una mejora.
   - `consecuencia de H#`: lo arregla otro hallazgo.
   - `descartado`: se investigó y la traza muestra que no es la causa (sección 8). No genera mejora.
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
4. **Pendientes** en `estado.md`: lo que esta investigación no pudo cerrar. **No son mejoras** (las mejoras, también las que el usuario deje para después, viven en `plan.json`), y el reporte los titula así. Uno por línea, con cuatro datos: el síntoma y qué tan estable es; qué falta para cerrarlo; cuánto cuesta (una corrida, una captura con muestreo, una sesión); y la acción sugerida. Si lo que falta es una captura que el usuario puede correr ya, deja en esa línea el texto "Captura pendiente:" seguido del comando entre acentos graves, con la ruta real del plan (por ejemplo, Captura pendiente: `capturar --plan reports/perf/detalle/plan.json --prueba --config cpu`): en el cierre sin mejoras, `siguiente` la ofrece como comando antes del chat.
5. **Reporte inicial**, en dos versiones que salen del mismo comando: `reporte-inicial-dev` (el técnico, con "Servicios del flujo": qué servicios consume el flujo y cuánto tarda cada uno, orientativo) y `reporte-inicial-gerencia` (una página en palabras). También dibuja el plan en `estado.md` y abre con el recuadro "Resultado" (cuántas mejoras y cuáles, o "Sin mejoras aplicables" con la razón de cada hallazgo, tomada de la tabla):
   ```bash
   cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py reporte --carpeta <carpeta> --inicial --html
   ```
6. **Siguiente paso:** `reporte --inicial` imprime el comando `perf.py decidir` y lo deja en `estado.md`. Si avisa que `estado.md` tiene partes sin completar (el Resumen, el Resumen para gerencia, filas de la Ficha, la tabla de Hallazgos), complétalas y vuelve a generarlo antes de entregar. Muéstrale al usuario las mejoras en una tabla corta (id, título, métrica y esperado) y pega tal cual la salida de `siguiente`, que ya dice que es en la terminal y sin chat. **Sin mejoras**, dilo en la primera línea de tu respuesta, con la razón en una frase: `siguiente` ofrece el cierre corto (y la captura pendiente, si dejaste una), no otra sesión 2. Detente: `decidir` le da el chat de la sesión 3. No le pidas que vuelva a este chat ni el costo: lo anota con `perf.py consumo`.
