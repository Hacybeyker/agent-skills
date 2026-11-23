# Modo orquestado

Un solo chat recorre la investigación completa: el **orquestador** lanza cada sesión como un **subagente** con su propio contexto, corre las capturas con recorrido automático y solo se detiene donde hace falta una persona. El usuario no abre chats ni pega pasos, y el ahorro de "una sesión por chat" se mantiene: cada subagente empieza con unos pocos miles de tokens (la skill, su referencia y `estado.md`), igual que un chat nuevo, y el orquestador solo acumula salidas cortas de `perf.py` y resúmenes de 15 líneas.

**Presupuesto y tareas (orquestador).** No tiene tope de pasos: cada vuelta del ciclo es corta. En este orden, y nada más: (1) comprobar que hay subagentes; (2) el ciclo de abajo hasta que `siguiente --json` diga `"quien": "nadie"`; (3) el cierre con el costo. **No hagas:** leer trazas, `diagnostico.md` completo, el código de `perf.py`, el código del proyecto ni `estado.md` entero (los subagentes leen lo de su sesión); interpretar el texto de `siguiente` (decides con `siguiente --json`); correr `decidir` ni ninguna decisión del usuario; hacer commit o push. **Cuándo detenerte:** en las paradas de la tabla de abajo, y solo ahí.

## Cuándo se usa

- **Solo si el usuario lo pide** ("modo orquestado", "orquesta la investigación"). Sin ese pedido, el modo es el guiado de siempre, y el autónomo sigue como está ([SKILL.md](../SKILL.md) · Modos).
- **Hace falta un agente con subagentes** que acepten un modelo propio: Claude Code los tiene (la herramienta Agent, con su parámetro de modelo). Si tu herramienta no los tiene, dilo en una línea ("Esta herramienta no tiene subagentes: sigo en modo guiado") y sigue en modo guiado, con la sesión que corresponda.
- **Recorrido automático o manual.** Con recorrido automático (un comando con `adb`, `arranque-frio` o `preparar` con Maestro), el orquestador corre las capturas. Con recorrido manual o con una pausa humana, te las entrega y espera a que escribas "listo".
- **El chat del orquestador:** nivel económico, esfuerzo bajo (`cd <raíz> && claude --model claude-haiku-5-5 --effort low`): solo corre `perf.py`, lee su JSON y lanza subagentes. Cada sesión corre con el modelo de su nivel ([modelos.md](modelos.md) · Subagentes del modo orquestado). Si el orquestador se desordena (salta una parada, lee de más), ábrelo con el intermedio.

## El ciclo

1. **Pide el paso:** `cd <raíz> && python3 -I <skill>/scripts/perf.py siguiente --json --carpeta <carpeta>`. Antes de que exista la investigación, sin `--carpeta`: da el setup (sesión 0, reponer o elegir el parche) o la sesión 1, con el pedido que guardó la sesión 0. La salida es **una línea de JSON** (abajo) y además deja "Siguiente paso" en `estado.md`, como `siguiente`.
2. **Mira `quien`** (del primer paso; `pasos` trae todos, en orden):
   - `orquestador`: corre los comandos de `corre_ahora`, **uno a la vez, en orden y en primer plano**, cada uno con su salida en un log y al chat solo el final: `<comando> > <carpeta>/logs/orquestador-<n>.log 2>&1; echo "salida: $?"; tail -n 15 <carpeta>/logs/orquestador-<n>.log`. Si uno sale con un código distinto de 0, no sigas con los demás (abajo, "Cuando un comando falla"). Después, vuelve al paso 1.
   - `subagente`: lanza la sesión ("El subagente de cada sesión") y espera su resumen sin hacer nada más; después, vuelve al paso 1.
   - `usuario`: detente con el texto de "Paradas", según `clase` y `donde`.
   - `nadie`: la investigación terminó: "Al cerrar".
3. **Nunca dos cosas a la vez.** Ninguna captura, `diagnostico` ni `siguiente --json` mientras un subagente trabaja (escribe `estado.md` y el código), y ningún subagente mientras corre una captura. En Claude Code los subagentes corren en segundo plano: espera el aviso de que terminó.

`corre_ahora` corta solo después de una corrida de prueba (lo que sigue depende de sus avisos) o antes de una sesión o una parada: no lo extiendas con pasos de `pasos`.

## `siguiente --json`

| Campo | Qué es |
| --- | --- |
| `tipo` | `sesion`, `terminal`, `decision`, `humano` (una acción, una captura o una entrada que hace una persona), `fin` o `error` |
| `quien` | `orquestador`, `subagente`, `usuario` o `nadie`; `requiere_persona` es `true` si es `usuario` |
| `clase` | Qué es en concreto: `captura`, `diagnostico`, `instalar`, `perf`, `sesion`, `entorno`, `mejoras`, `aprobacion`, `profundidad`, `pausa`, `linea_base`, `parche`, `setup`, `investigacion`, `accion`, `comando` o `fin` |
| `donde` | Dónde actúa el usuario en una parada: `terminal` o `chat` |
| `motivo` | Por qué se detiene, en una línea |
| `sesion`, `nivel`, `modelo`, `esfuerzo` | La sesión (`2 · diagnóstico`, `3 · M1`), su nivel en `modelos` de `plan.json`, el nombre del modelo y el esfuerzo |
| `subagente` | `{"modelo": "haiku" \| "sonnet" \| "opus" \| "fable" \| null, "esfuerzo": "low" \| "medium" \| "high"}`: los valores para el subagente de Claude Code |
| `referencia`, `carpeta_skill` | La referencia de la sesión (relativa a la skill) y la carpeta de la skill |
| `texto` | El texto de la sesión, el mismo que el chat del modo guiado |
| `corre_ahora`, `comandos` | Lo que el orquestador corre ya, en orden; y todos los comandos de los pasos |
| `pasos`, `avisos`, `archivos`, `notas` | Todos los pasos clasificados (una decisión trae `opciones`, cada una con `nombre`, `cuando` y su paso); los avisos y los reportes; lo que `siguiente` habría impreso antes de los pasos |
| `costo` | `comando` (el `consumo` de la fila `orquestado`), `esperado_usd`, `sesiones`, `anotado` y `se_paso` |

Con un error, `tipo` es `error`, `motivo` es el mensaje, `seguir` trae los comandos que propone `perf.py` y el código de salida es el del error; el texto guiado de siempre va a stderr.

## El subagente de cada sesión

Lánzalo con `subagente.modelo` como modelo y `subagente.esfuerzo` como esfuerzo (en Claude Code, los parámetros de modelo y de esfuerzo de la herramienta Agent; un subagente de propósito general). Si `subagente.modelo` es `null` (un nivel con un modelo de otro proveedor), usa el equivalente de tu herramienta para `nivel`. Un subagente por sesión y una mejora por subagente: la sesión 3 de cada mejora es otro subagente. El prompt, con lo de `siguiente --json`:

```text
Eres el subagente de la sesión <sesion> de hb-performance, en modo orquestado. Lee <carpeta_skill>/SKILL.md y
<carpeta_skill>/<referencia>, y haz solo esa sesión, con sus reglas y su presupuesto de pasos.
<texto>
- No hablas con el usuario. Si la sesión necesita preguntarle algo (las preguntas de la sesión 1, si el setup se
  versiona o va en un parche, una decisión del alcance), detente y devuélvelas todas juntas, tal como se las harías.
  La aprobación de la ficha y el plan no la esperes: termina con `perf.py aprobar --carpeta <carpeta> --pendiente`.
- No corras capturas de fases (`capturar --fase`) ni `diagnostico`: las corre el orquestador. La corrida de prueba de
  tu sesión sí, como en modo guiado.
- Nunca corras `decidir --aprobar`, `--descartar` ni `--pendiente`. No hagas commit ni push.
- Termina con `perf.py siguiente --carpeta <carpeta>` (en la sesión 0, con el comando de la prueba de humo), pero no
  pegues su salida: devuelve solo el resumen, con este formato y 15 líneas como máximo:
  Estado: terminada | preguntas | bloqueada
  Sesión: <sesion> · Carpeta: <ruta absoluta, si ya existe>
  Hecho: <en una a cuatro líneas>
  Archivos: <los que cambiaste>
  DoD: <comandos y resultado, o "no aplica">
  Commit propuesto: <mensaje, o "ninguno">
  Siguiente: <el comando de humo en la sesión 0; si no, "perf.py siguiente">
  Bloqueo: <qué falla y qué intentaste, o "ninguno">
  Si el estado es "preguntas", después del resumen, un bloque "Preguntas para el usuario" con el texto exacto.
```

- **Sesiones con preguntas (0 y 1).** Si el resumen dice `Estado: preguntas`, muéstrale al usuario el bloque de preguntas tal cual, en el chat, y espera su respuesta. Después **continúa el mismo subagente** con la respuesta tal cual (en Claude Code, con SendMessage al subagente: conserva su contexto); si tu herramienta no puede continuarlo, lanza otro de la misma sesión con el mismo prompt más "Respuestas del usuario: <respuesta>".
- **Sesión 0.** Al prompt agrégale el pedido del usuario tal cual ("Pedido del usuario: <texto>"): la sesión 0 lo guarda para la sesión 1. Cuando termine, corre tú la prueba de humo que devolvió en "Siguiente" (es una corrida de arranque en frío, automática) y vuelve al paso 1, sin `--carpeta`.
- **Sesión 1.** Si el pedido es tuyo (`siguiente --json` sin pedido guardado da "quiero medir un flujo de la app; pregúntame cuál"), agrégale el pedido del usuario tal cual.
- **Bloqueada.** Si el resumen dice `Estado: bloqueada`, vuelve al paso 1: si `siguiente --json` da el mismo paso, es una parada (un error que la salida no resuelve).
- **No leas lo que hizo:** el resumen alcanza. Si el usuario pregunta por un hallazgo o por un cambio, dale la ruta del reporte o del archivo.

## Paradas

En cada parada dices **qué hacer y dónde** (terminal o chat), con el comando entero en un bloque de código (empieza con `cd <ruta absoluta> && ...`), y esperas. No sigues por tu cuenta aunque el siguiente paso parezca obvio.

| Cuándo (`clase` o situación) | Qué le dices al usuario | Dónde | Cómo sigues |
| --- | --- | --- | --- |
| `mejoras`: la decisión de las mejoras | Las mejoras en una línea cada una (del resumen de la sesión 2), el reporte inicial (`archivos`) y el comando `decidir` de la primera opción, para que deje en cada lista los ids que correspondan; las otras opciones (pausar, cerrar sin aplicar) con su comando | Terminal; después escribe "continúa" en este chat | Al leer "continúa", paso 1 |
| `aprobacion`: la ficha y el plan | Lo que dicen `avisos` (la ficha, el plan, el recorrido en palabras y el video de la prueba) y el resumen de la sesión 1; que responda "apruebo" o qué hay que cambiar | Chat | Con "apruebo", corres el comando de la opción "Apruebo" (`perf.py aprobar`), como en el modo guiado; con un cambio, lanzas la sesión de la opción "Hay que cambiar algo" con su pedido |
| `captura` con recorrido manual o pausa humana | El comando de la captura: recorre el flujo en el dispositivo (o atiende la pausa) y presiona Enter en cada corrida | Terminal; después escribe "listo" en este chat | Al leer "listo", paso 1 |
| `entorno`: claves, usuarios u otras variables | Que salga del chat (`/exit`), cargue cada variable con el comando de `pasos` (las claves, con lectura oculta) en una terminal y vuelva a abrir este chat desde ella con `cd <raíz> && claude --resume` (eligiéndolo de la lista): el agente solo ve las variables de la terminal desde la que se abrió | Terminal | Al volver, paso 1 |
| Una pantalla de autorización o de pago, o un paso que hace una persona | Qué tiene que hacer en el dispositivo; nunca lo haces tú | Dispositivo; después "listo" en este chat | Paso 1 |
| `profundidad`, `pausa`, `linea_base`, `parche`, `setup`, `investigacion` u otra decisión | Las opciones con su `cuando` y su comando | Terminal, salvo `investigacion` (responde en el chat cuál sigue) | Al leer "continúa" (o la elección), paso 1, con la carpeta elegida |
| Un error de `perf.py` que su salida no resuelve | Qué pasó (el final del log), qué quedó guardado y el comando que da `perf.py` para seguir | Terminal | Al leer "continúa", paso 1 |
| 3 corridas inválidas seguidas (`capturar` sale con 5) | Que algo del entorno falla (el recorrido, `preparar`, el backend o el dispositivo), con el final del log | Terminal o dispositivo | Al leer "continúa", paso 1 |
| Falta un dispositivo o una herramienta (`capturar` o `humo` salen con 3, o `adb` no responde) | Lo que falta, según la salida de `perf.py` (la skill no instala nada) | Terminal | Al leer "continúa", paso 1 |
| `accion` o `comando`: un paso sin comando de `perf.py` | El `que` y el `tu` del paso | Terminal | Al leer "listo", paso 1 |

## Cuando un comando falla

Los códigos de salida de `perf.py`: 2, un error con salida guiada; 3, una precondición (sin dispositivo, falta una herramienta, el dispositivo no responde); 4, una captura fallida; 5, no se juntaron las corridas válidas (por ejemplo, 3 inválidas seguidas); 130, interrumpido.

- **3, 4, 5 o 130:** parada. Las corridas válidas quedan guardadas: después, `siguiente --json` da cómo completar la fase.
- **2:** vuelve al paso 1 una vez. Si `siguiente --json` da un paso nuevo (lo que el error pedía, por ejemplo `perf.py recuperar` o `setup --reponer`), síguelo; si da el mismo comando que falló, o si vuelve a fallar, es una parada.
- **Un comando de instalación o el DoD que falla:** parada, con el final del log. No corrijas código: eso es de una sesión.

## Al cerrar

Cuando `quien` es `nadie`:

1. Los reportes (`archivos`) y los commits propuestos por cada sesión 3, en una lista; el commit lo hace el usuario (o lo pide).
2. **El costo**, en un bloque de código: el `costo.comando` de la última salida, con `--modelo` ya completo (pasa `--modelo '<el modelo de este chat>'` a `siguiente --json` para que salga así), para que el usuario ponga lo que muestra `/cost` en este chat, que incluye lo que gastaron sus subagentes. Dile lo esperado (`costo.esperado_usd`, para las sesiones de `costo.sesiones` y el tamaño del proyecto) y que, si `/cost` muestra más, consumió más de lo esperado; `consumo` también lo avisa al anotarlo y lo deja en `estado.md`. **Nunca te detengas por costo:** solo avisa.
3. En modo orquestado se anota **una sola fila**, `orquestado`: con ella, `siguiente` deja de pedir el costo de cada sesión (sumarlas contaría dos veces lo mismo). Con el hook de fin de sesión de Claude Code ([modelos.md](modelos.md) · Consumo por herramienta), el chat del orquestador se anota solo como `orquestado` si su primer pedido dice "modo orquestado" y nombra el `estado.md`.

## Reglas que siguen valiendo

Todas las de [SKILL.md](../SKILL.md), para el orquestador y para cada subagente: alcance estricto, medir antes de cambiar, evidencia, los números de `perf.py`, salidas acotadas, git (nadie hace commit ni push; la decisión es del usuario), datos, comandos para el usuario que empiezan con `cd <ruta absoluta> && ...`, rutas que no se leen, nunca escribir claves ni autorizar pagos, no instalar ni configurar nada en la máquina, y español neutro (tú). Lo único que cambia es quién corre qué: las capturas con recorrido automático y `diagnostico` las corre el orquestador, en serie, como en el modo autónomo.
