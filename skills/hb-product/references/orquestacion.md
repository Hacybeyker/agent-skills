# Modo orquestado

Un solo chat recorre la idea entera: el **orquestador** lanza cada sesión como un **subagente** con su propio contexto y el modelo de esa sesión, en paralelo lo que se puede, y se detiene en cada puerta, donde decide el usuario: el orquestador nunca corre `decidir`. El usuario no abre chats ni pega pasos, y el ahorro de "una sesión por chat" se mantiene: cada subagente empieza con la skill, su referencia y `estado.md`, igual que un chat nuevo, y el orquestador solo acumula salidas cortas de `producto.py` y resúmenes de 10 líneas. Es el mismo diseño que el modo orquestado de `hb-performance`.

**Presupuesto y tareas (orquestador).** No tiene tope de pasos: cada vuelta del ciclo es corta. En este orden, y nada más: (1) comprobar que hay subagentes; (2) el ciclo de abajo hasta una puerta o hasta que `siguiente --json` diga `"quien": "nadie"`; (3) el cierre con el costo. **No hagas:** investigar ni leer fuentes, leer los entregables completos, el código de `producto.py` ni `estado.md` entero (los subagentes leen lo de su sesión); interpretar el texto de `siguiente` (decides con `siguiente --json`); correr `decidir` (nunca: la decisión de una puerta la corre el usuario en su terminal); responder por tu cuenta una pregunta que es del usuario; hacer commit o push.

## Cuándo se usa

- **Solo si el usuario lo pide** ("en modo orquestado", "orquesta la idea"). Sin ese pedido, el modo es el de siempre: un chat por sesión, con el texto que imprime `siguiente`.
- **Hace falta un agente con subagentes** que acepten un modelo propio: Claude Code los tiene (la herramienta Agent, con su parámetro de modelo). Si tu herramienta no los tiene, dilo en una línea ("Esta herramienta no tiene subagentes: sigo con un chat por sesión") y sigue con el modo de siempre.
- **El chat del orquestador:** nivel económico y esfuerzo bajo (`cd <raíz> && claude --model claude-haiku-5-5 --effort low`; `siguiente --json` lo trae en `orquestador.abrir`): solo corre `producto.py`, lee su JSON y lanza subagentes. Si se desordena (salta una puerta, lee de más), ábrelo con el intermedio.

## El ciclo

1. **Pide el paso:** `cd <raíz> && python3 -I <skill>/scripts/producto.py siguiente --json --carpeta <carpeta>`. La salida es **una línea de JSON** (abajo) y además deja "Siguiente paso" en `estado.md`, como `siguiente`.
2. **Mira `quien`:**
   - `subagente`: lanza **un subagente por cada paso de `pasos`, todos a la vez** (con `en_paralelo`, en un solo mensaje), con el prompt de "El subagente de cada sesión". Las líneas 1a a 1e van juntas; la 1g aparece apenas cierran 1a y 1b, y la 2 y la 3 van juntas.
   - `usuario`: una puerta (o la sesión 0, que pregunta): sigue "Paradas".
   - `nadie`: la idea cerró o está archivada: "Al cerrar".
3. **Espera a que terminen todos los subagentes que lanzaste** antes de volver al paso 1: nunca resumas, nunca muestres una puerta y nunca vuelvas a pedir el paso mientras uno sigue en segundo plano (en Claude Code, espera el aviso de fin de cada uno; un "Waiting for 1 background agent to finish" es que falta uno). Un subagente puede haber cerrado su sesión con `cerrar` y seguir trabajando: el registro ya lo da por cerrado, pero su consumo y su resumen todavía no llegaron.
4. **Anota el consumo de cada subagente** apenas llega su aviso de fin, con lo que trae ese aviso (en Claude Code, los tokens y la cantidad de herramientas que usó): `costo.comando_sesion` con su sesión, `cd <raíz> && python3 -I <skill>/scripts/producto.py consumo --sesion <id> --tokens '<tokens>' --pasos '<pasos>' --modelo '<modelo>' --carpeta <carpeta>`. Si el aviso no trae nada, no lo inventes: anota solo el total del orquestador al cerrar.
5. Cuando terminaron todos y anotaste su consumo, vuelve al paso 1. Lanza solo las sesiones nuevas que aparezcan en `pasos`.

## `siguiente --json`

| Campo | Qué es |
| --- | --- |
| `tipo` | `sesion`, `puerta`, `fin` o `error` |
| `quien` | `subagente`, `usuario` o `nadie`; `requiere_persona` es `true` en una puerta y en la sesión 0 |
| `motivo` | Qué hacer o por qué se detiene, en una línea |
| `pasos` | Las sesiones para lanzar (cada una con `sesion`, `nombre`, `nivel`, `modelo`, `esfuerzo`, `subagente`, `referencia`, `texto` y `reapertura`) o la puerta (con `veredicto`, `recomendacion`, `opciones` y `texto`) |
| `en_paralelo`, `esperan` | Si hay que lanzar varias a la vez, y las sesiones que se abren después (1g, 1f) |
| `subagente` | `{"modelo": "haiku" \| "sonnet" \| "opus" \| "fable" \| null, "esfuerzo": "low" \| "medium" \| "high"}`: los valores para el subagente de Claude Code; `null` es un modelo de otro proveedor (usa el equivalente de tu herramienta para su `nivel`) |
| `avisos` | Lo que `siguiente` dice debajo de los pasos: el rival a revisar, las líneas a revisar por cambio de tipo, el consumo sin anotar |
| `costo` | `sin_anotar` (sesiones cerradas sin consumo), `comando_sesion`, `comando_orquestador` y si el orquestador ya está anotado |
| `orquestador`, `carpeta_skill`, `carpeta`, `estado`, `reporte` | El modelo y el comando del chat orquestador, las rutas de la skill y de la idea, y la del reporte |

Con un error, `tipo` es `error`, `motivo` es el mensaje y el código de salida es 1.

## El subagente de cada sesión

Lánzalo con `subagente.modelo` como modelo y `subagente.esfuerzo` como esfuerzo (en Claude Code, un subagente de propósito general con su parámetro de modelo). El prompt, con lo de cada paso:

```text
Eres el subagente de la sesión <sesion> · <nombre> de hb-product, en modo orquestado. Lee <carpeta_skill>/SKILL.md y
<carpeta_skill>/<referencia>, y haz solo esa sesión, con sus reglas y su presupuesto.
<texto>
- No hablas con el usuario. Si la sesión necesita preguntarle algo (la entrevista de la sesión 0), detente y
  devuelve todas las preguntas juntas, en una sola tanda, en un bloque "Preguntas para el usuario".
- No propongas chats nuevos ni textos para pegar: el paso siguiente lo da el orquestador.
- Nunca corras `decidir`. No hagas commit ni push.
- Termina con `producto.py siguiente --carpeta <carpeta>`, pero no pegues su salida: devuelve solo este resumen,
  10 líneas como máximo:
  Estado: terminada | preguntas | bloqueada
  Sesión: <sesion> · Carpeta: <ruta absoluta>
  Hecho: <en una a tres líneas: lo registrado, con sus IDs>
  Cerró: <la salida de `cerrar` en una línea, o por qué no cerró>
  Presupuesto: <búsquedas y lecturas de esta pasada>
  Propuestas: <las que dejó con `propuesta`, o "ninguna">
  Bloqueo: <qué falla y qué intentaste, o "ninguno">
```

- **Sesión 0.** Sin idea en la carpeta, `siguiente --json` da la sesión 0 con `"texto": "Usa hb-product: <pedido del usuario, tal cual>…"`: pon ahí el pedido del usuario tal cual. El subagente vuelve con `Estado: preguntas` y la entrevista (8 preguntas como máximo); hazlas al usuario **en un solo mensaje**, tal cual, y **continúa el mismo subagente** con las respuestas (en Claude Code, con SendMessage: conserva su contexto). Si tu herramienta no puede continuarlo, lanza otro de la sesión 0 con el mismo prompt más "Respuestas del usuario: <respuestas>".
- **Bloqueada.** Si el resumen dice `Estado: bloqueada`, vuelve al paso 1: si `siguiente --json` da la misma sesión, es una parada (dile al usuario qué falla, con el resumen).
- **No leas lo que hizo:** el resumen alcanza. Si el usuario pregunta por un hallazgo, dale la ruta del entregable o del reporte.

## Paradas

En cada parada dices **qué hacer y dónde**, con el comando entero en un bloque de código (empieza con `cd <ruta absoluta> && ...`), y esperas. No sigues por tu cuenta aunque el paso siguiente parezca obvio.

| Cuándo | Qué le dices al usuario | Dónde | Cómo sigues |
| --- | --- | --- | --- |
| Una puerta (`tipo: puerta`) | Pega el `texto` de la puerta tal cual, en un bloque de código (empieza con el banner del veredicto y la recomendación, sigue con los criterios y los avisos), y debajo los comandos de `opciones`, **el recomendado primero**; la ruta del reporte (`reporte`). Antes, si quieres, una línea por sesión con lo que dijo su resumen | Terminal: el usuario corre `decidir`; tú **nunca** lo corres | Al leer "continúa", paso 1 |
| La sesión 0 con preguntas | Las preguntas del subagente, en un solo mensaje | Chat | Continúas el subagente con las respuestas |
| Un error o una sesión bloqueada | Qué pasó y el comando que da `producto.py` para seguir | Terminal | Al leer "continúa", paso 1 |

## Al cerrar

Cuando `quien` es `nadie`, o en cada puerta antes de detenerte:

1. **El costo, en tu último mensaje:** recuérdale correr `/cost` **en este chat** (incluye lo que gastaron los subagentes) y dale `costo.comando_orquestador` en un bloque de código (`consumo --sesion orquestador --incluye <sesiones> --costo '<USD que muestra /cost>'`). Sin `--tokens`: los de los subagentes ya están anotados por sesión y no se cuentan dos veces. Con GitHub Copilot CLI, `--creditos` con lo que muestre `/usage`. Anotar es opcional y nunca detiene nada.
2. La ruta del reporte y, al final del proceso, la del PRD.

## Reglas que siguen valiendo

Todas las de [SKILL.md](../SKILL.md), para el orquestador y para cada subagente: evidencia o nada, los números de `producto.py`, una sesión por subagente, la skill recomienda y el usuario decide (nadie corre `decidir` por el usuario), lo cerrado se cambia en la puerta (`propuesta`), salidas acotadas, privacidad, comandos para el usuario que empiezan con `cd <ruta absoluta> && ...`, español neutro (tú) y nada de commit ni push. Lo único que cambia es quién abre cada sesión: el orquestador, con un subagente, en vez del usuario con un chat.
