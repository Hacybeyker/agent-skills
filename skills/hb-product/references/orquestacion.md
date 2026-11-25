# Modo orquestado

Un solo chat recorre la idea entera: el **orquestador** lanza cada sesión como un **subagente** con su propio contexto y el modelo de esa sesión, en paralelo lo que se puede, y se detiene en cada puerta, donde decide el usuario: el orquestador nunca corre `decidir` (salvo en el [modo autónomo](#modo-autónomo), si el usuario lo pide, y solo con `--automatico`). El usuario no abre chats ni pega pasos, y el ahorro de "una sesión por chat" se mantiene: cada subagente empieza con la skill, su referencia y `estado.md`, igual que un chat nuevo, y el orquestador solo acumula salidas cortas de `producto.py` y resúmenes de 10 líneas. Es el mismo diseño que el modo orquestado de `hb-performance`.

**Presupuesto y tareas (orquestador).** No tiene tope de pasos: cada vuelta del ciclo es corta. En este orden, y nada más: (1) comprobar que hay subagentes; (2) el ciclo de abajo hasta una puerta o hasta que `siguiente --json` diga `"quien": "nadie"`; (3) el cierre con el costo.

**Regla de oro: subagentes en primer plano.** Lanza **siempre en primer plano** los subagentes que corren juntos, **todos en un mismo mensaje** (una llamada por subagente), y **no cierres tu turno mientras uno corre**: así el turno sigue, el resultado de cada uno vuelve en ese mismo mensaje con su consumo y no hay avisos que esperar. **Nunca uses segundo plano** (en Claude Code, nada de `run_in_background`): un orquestador que cierra su turno "esperando el aviso de fin" se queda quieto cuando el aviso llega, sin anotar el consumo ni lanzar la sesión siguiente. La 1g es la que arranca antes que las demás terminen: por eso `siguiente --json` da las líneas en dos tandas (abajo), todas en primer plano. **No hagas:** investigar ni leer fuentes, leer los entregables completos, el código de `producto.py` ni `estado.md` entero (los subagentes leen lo de su sesión); interpretar el texto de `siguiente` (decides con `siguiente --json`); correr `decidir` (nunca: la decisión de una puerta la corre el usuario en su terminal; la única excepción es `decidir --automatico` en el modo autónomo que pidió el usuario); responder por tu cuenta una pregunta que es del usuario; hacer commit o push.

## Cuándo se usa

- **Solo si el usuario lo pide** ("en modo orquestado", "orquesta la idea"). Sin ese pedido, el modo es el de siempre: un chat por sesión, con el texto que imprime `siguiente`. El **modo autónomo** (sin preguntas ni paradas en las puertas) también es solo a pedido explícito ([abajo](#modo-autónomo)).
- **Hace falta un agente con subagentes** que acepten un modelo propio: Claude Code los tiene (la herramienta Agent, con su parámetro de modelo). Si tu herramienta no los tiene, dilo en una línea ("Esta herramienta no tiene subagentes: sigo con un chat por sesión") y sigue con el modo de siempre.
- **El chat del orquestador:** nivel económico y esfuerzo bajo (`cd <raíz> && claude --model claude-haiku-5-5 --effort low`; `siguiente --json` lo trae en `orquestador.abrir`): solo corre `producto.py`, lee su JSON y lanza subagentes. Si se desordena (salta una puerta, lee de más), ábrelo con el intermedio.

## El ciclo

1. **Pide el paso:** `cd <raíz> && python3 -I <skill>/scripts/producto.py siguiente --json --carpeta <carpeta>`. La salida es **una línea de JSON** (abajo) y además deja "Siguiente paso" en `estado.md`, como `siguiente`.
2. **Mira `quien`:**
   - `subagente`: lanza **un subagente por cada paso de `pasos`, todos a la vez, en un solo mensaje y en primer plano** (`plano: "primero"`), con el prompt de "El subagente de cada sesión". Las tandas: primero **1a ‖ 1b** (la 1a confirma el tipo de idea); al cerrar las dos, **1c ‖ 1d ‖ 1e ‖ 1g** (la 1g arranca sin esperar a las demás líneas); después la 1f, y la 2 ‖ 3.
   - `usuario`: una puerta (o la sesión 0, que pregunta): sigue "Paradas".
   - `nadie`: la idea cerró o está archivada: "Al cerrar".
3. **Espera a que terminen todos los subagentes que lanzaste**, sin cerrar tu turno: en primer plano, el mensaje vuelve cuando terminaron todos. Nunca resumas, nunca muestres una puerta y nunca vuelvas a pedir el paso mientras uno sigue corriendo. Un subagente puede haber cerrado su sesión con `cerrar` y seguir trabajando: el registro ya lo da por cerrado, pero su consumo y su resumen todavía no llegaron.
4. **Anota el consumo de cada subagente con lo que trae su resultado** (en Claude Code, el resultado de cada subagente en primer plano trae sus tokens y la cantidad de herramientas que usó): `costo.comando_sesion` con su sesión, `cd <raíz> && python3 -I <skill>/scripts/producto.py consumo --sesion <id> --tokens '<tokens>' --pasos '<pasos>' --modelo '<modelo>' --carpeta <carpeta>`. Si el resultado no trae nada, no lo inventes: anota solo el total del orquestador en la parada.
5. Cuando terminaron todos y anotaste su consumo, vuelve al paso 1 **en el mismo turno**. Lanza solo las sesiones nuevas que aparezcan en `pasos`.

**Si igual te detuviste** (cerraste el turno con un subagente corriendo, o el aviso de fin llegó y no seguiste), el usuario te reanuda escribiendo `Continúa en modo orquestado: anota el consumo de los subagentes que terminaron y sigue el ciclo. No hagas commit ni push.` Al leerlo, anota el consumo que falte con lo que trajo cada resultado o aviso, y vuelve al paso 1.

## `siguiente --json`

| Campo | Qué es |
| --- | --- |
| `tipo` | `sesion`, `puerta`, `fin` o `error` |
| `quien` | `subagente`, `usuario` o `nadie`; `requiere_persona` es `true` en una puerta y en la sesión 0 |
| `motivo` | Qué hacer o por qué se detiene, en una línea |
| `pasos` | Las sesiones para lanzar (cada una con `sesion`, `nombre`, `nivel`, `modelo`, `esfuerzo`, `subagente`, `referencia`, `texto` y `reapertura`; la sesión 0, también con `texto_autonomo`) o la puerta (con `veredicto`, `recomendacion`, `opciones`, `automatico` y `texto`) |
| `pasos[0].automatico` | En una puerta, para el modo autónomo: `comando` (`decidir --puerta <n> --automatico`, listo), `decision` y `sesion` (lo que recomienda la skill), `ajustes_previos` (cuántas veces se ajustó ya esa sesión en esa puerta), `detener` (`true` si hay que parar y preguntarle al usuario) y `motivo` (por qué) |
| `en_paralelo`, `esperan`, `plano` | Si hay que lanzar varias a la vez (en un solo mensaje), las sesiones que se abren después (1c a 1e, la 1g y la 1f) y `"primero"`: siempre en primer plano |
| `subagente` | `{"modelo": "haiku" \| "sonnet" \| "opus" \| "fable" \| null, "esfuerzo": "low" \| "medium" \| "high"}`: los valores para el subagente de Claude Code; `null` es un modelo de otro proveedor (usa el equivalente de tu herramienta para su `nivel`) |
| `avisos` | Lo que `siguiente` dice debajo de los pasos: el rival a revisar, las líneas a revisar por cambio de tipo, el consumo sin anotar |
| `costo` | `sin_anotar` (sesiones cerradas sin consumo), `comando_sesion`, `sin_orquestador` (sesiones cerradas que ningún chat orquestador anotó todavía), `comando_orquestador` (armado con ellas en `--incluye`), `recordatorio` (el texto de `/cost` para arriba de cada parada) y si el orquestador ya está anotado |
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

**Arriba de cada parada, el costo** (antes de la puerta y de los comandos de `decidir`): "Corre `/cost` en este chat ahora (el total incluye a los subagentes) y anótalo:" y, en un bloque de código, `costo.comando_orquestador` **armado**: en `--incluye`, solo las sesiones que lanzó **este** chat desde que empezó (`/cost` es acumulado); `costo.sin_orquestador` trae las candidatas, y quitas las que corrió otro chat. Si el usuario cierra el chat sin correr `/cost`, ese costo se pierde: por eso va arriba y no al final. El mismo chat que vuelve a anotar en otra parada actualiza su fila; otro chat orquestador queda en una fila aparte.

| Cuándo | Qué le dices al usuario | Dónde | Cómo sigues |
| --- | --- | --- | --- |
| Una puerta (`tipo: puerta`) | Primero el recordatorio de `/cost` con su comando armado; después el `texto` de la puerta tal cual, en un bloque de código (empieza con el banner del veredicto y la recomendación, sigue con los criterios y los avisos), y debajo los comandos de `opciones`, **el recomendado primero**; la ruta del reporte (`reporte`). Si quieres, una línea por sesión con lo que dijo su resumen | Terminal: el usuario corre `decidir`; tú **nunca** lo corres (en el modo autónomo, `automatico.comando`, salvo que `automatico.detener` sea `true`) | Al leer "continúa", paso 1 (en el modo autónomo, sin esperar) |
| La sesión 0 con preguntas | Las preguntas del subagente, en un solo mensaje | Chat | Continúas el subagente con las respuestas |
| Un error o una sesión bloqueada | Qué pasó y el comando que da `producto.py` para seguir | Terminal | Al leer "continúa", paso 1 |

## Al cerrar

Cuando `quien` es `nadie`, o en cada puerta antes de detenerte:

1. **El costo, arriba de tu mensaje** (en cada puerta y otra vez en el mensaje final, cuando la idea se cierra o se archiva): recuérdale correr `/cost` **en este chat** (incluye lo que gastaron los subagentes) y dale `costo.comando_orquestador` armado en un bloque de código (`consumo --sesion orquestador --incluye <las sesiones que lanzó este chat> --costo '<USD que muestra /cost>'`). Sin `--tokens`: los de los subagentes ya están anotados por sesión y no se cuentan dos veces. Con GitHub Copilot CLI, `--creditos` con lo que muestre `/usage`. Anotar es opcional y nunca detiene nada.
2. La ruta del reporte y, al final del proceso, la del PRD.

## Modo autónomo

Para no copiar ni aprobar entre chats: el usuario lo pide **explícitamente** ("en modo autónomo", "sin preguntas ni paradas") y entonces el orquestador corre la idea entera, decidiendo en cada puerta con la recomendación de la skill. Es el modo orquestado con tres cambios; todo lo demás (subagentes en primer plano, consumo, `/cost`) sigue igual.

1. **Sesión 0 sin preguntas.** El usuario da la descripción de la idea (en el pedido o en un archivo). Lanza el subagente de la sesión 0 con `pasos[0].texto_autonomo` en vez de `texto`, poniendo ahí la descripción tal cual o la ruta del archivo: no hace la entrevista, toma lo que dice la descripción y deja lo que falta (mercados, semanas, modelo de negocio…) en "Supuestos sin confirmar" de `00-idea.md`, con el valor que eligió y por qué. Si la descripción no alcanza ni para el problema y el usuario, detente y pregúntale: eso solo lo puede dar él.
2. **En cada puerta decides con `decidir --automatico`.** Corre `pasos[0].automatico.comando` tal cual, **salvo que `pasos[0].automatico.detener` sea `true`**. `--automatico` aplica **solo la recomendación de la skill** (seguir, ajustar la sesión que recomienda o descartar con su motivo), rechaza `--seguir`, `--ajustar` o `--descartar` que vayan en contra y `--motivo`, y la registra como **decisión automática (modo autónomo)** con las razones de la recomendación: el reporte, el tablero y `estado.md` la marcan para que el usuario la revise o la reabra (`decidir --puerta <n> --reabrir`). Después vuelves al paso 1 del ciclo, sin detenerte; en el mensaje de esa vuelta pon una línea por puerta decidida ("Puerta 1: 🟡 Viable para probar → seguir (automática)").
3. **Solo te detienes** (y le dices al usuario qué pasó y qué comando correr en su terminal, sin `--automatico`) si:
   - `automatico.detener` es `true`: la puerta pide ajustar **la misma sesión por tercera vez** (`ajustes_previos` ya es 2), o la sesión que recomienda ajustar tiene vacíos por límite de las herramientas (un navegador o un CSV de reseñas solo los da el usuario). Vale también para el ajuste de la 1c por la demanda en confianza baja: cuenta para el tope de tres como cualquier otro y, si la 1c tiene vacíos de herramienta, se detiene. `decidir --automatico` también se niega en esos casos;
   - falta algo que **solo el usuario puede dar** (la descripción de la idea, un CSV, una cuenta, una decisión de negocio que la skill no toma);
   - hay un **error** (`tipo: error`) o una sesión **bloqueada** dos veces.

Al cerrar (`quien: nadie`: el PRD aprobado o la idea descartada), el mensaje final lleva el recordatorio de `/cost`, el recorrido por las puertas con las decisiones automáticas, la ruta del reporte y la del tablero, y la frase "Las decisiones automáticas están marcadas: revísalas y reabre la que no compartas".

## Reglas que siguen valiendo

Todas las de [SKILL.md](../SKILL.md), para el orquestador y para cada subagente: evidencia o nada, los números de `producto.py`, una sesión por subagente, la skill recomienda y el usuario decide (nadie corre `decidir` por el usuario, salvo `decidir --automatico` en el modo autónomo que él pidió; ningún subagente lo corre nunca), lo cerrado se cambia en la puerta (`propuesta`), salidas acotadas, privacidad, comandos para el usuario que empiezan con `cd <ruta absoluta> && ...`, español neutro (tú) y nada de commit ni push. Lo único que cambia es quién abre cada sesión: el orquestador, con un subagente, en vez del usuario con un chat.
