# Modelo, esfuerzo y costo por sesión

La skill no elige el modelo: lo recomienda. `producto.py siguiente` imprime en cada chat el **nombre concreto** del modelo y el esfuerzo, y, si anotaste tu herramienta, el comando que abre el chat con los dos. Para el usuario y para el chat orquestador, no para leer en cada sesión.

## Por sesión

| Sesión | Modelo (nivel) | Esfuerzo | Por qué |
| --- | --- | --- | --- |
| 0 · Idea | Sonnet 5.5 (intermedio) | medio | Una entrevista y plantillas |
| 1a · Competencia | Sonnet 5.5 (intermedio) | medio | Buscar, leer y registrar con el script |
| 1b · Voz del usuario | Sonnet 5.5 (intermedio) | medio | Ídem |
| 1c · Demanda | Sonnet 5.5 (intermedio) | medio | Ídem |
| 1d · Monetización | Sonnet 5.5 (intermedio) | medio | Ídem |
| 1e · Políticas y riesgos | Sonnet 5.5 (intermedio) | medio | Ídem |
| 1g · Diferenciación | Opus 5.5 (alto) | alto | Cruza la matriz con las quejas y decide qué es un diferenciador |
| 1f · Síntesis | Opus 5.5 (alto) | alto | Elige las anclas del puntaje |
| 2 · Estrategia | Opus 5.5 (alto) | alto | Propuesta de valor, PR/FAQ y escenarios |
| 3 · Validación documental | Opus 5.5 (alto) | alto | Abogado del diablo |
| 4 · PRD | Opus 5.5 (alto) | alto | Priorización y trazabilidad |
| Orquestador (modo orquestado) | Haiku 5.5 (económico) | bajo | Solo corre `producto.py`, lee su JSON y lanza subagentes |

Los nombres son los de fábrica (`intermedio`, `alto` y `economico`). Las decisiones de las puertas no usan modelo: van en la terminal.

## Cambiar los nombres o la herramienta

`producto.py modelos` muestra la tabla de esta idea. Con opciones, la cambia una vez y `siguiente` la usa en adelante:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py modelos --intermedio "Sonnet 5.5" --alto "Opus 5.5" --herramienta claude --carpeta product
```

- **`--intermedio`, `--alto` y `--economico`:** el nombre del modelo de cada nivel (el económico es el del chat orquestador). Un id (sin espacios ni mayúsculas, como `claude-opus-5-5`) va tal cual al comando.
- **`--herramienta`:** con `claude` o `copilot`, cada chat de `siguiente` trae su línea `Abrir:` con el comando completo; `ninguna` la quita.
- **`--herramienta otra --comando "<cli> --model {modelo}"`:** para otra CLI. `{modelo}` se reemplaza por el nombre del nivel y, si el comando lo lleva, `{esfuerzo}` por `low`, `medium` o `high`.

| Herramienta | Comando que imprime `siguiente` | Id del modelo | Esfuerzo |
| --- | --- | --- | --- |
| Claude Code | `cd <raíz> && claude --model <id> --effort <nivel>` | "Sonnet 5.5" → `claude-sonnet-5-5` | `medio` → `medium`, `alto` → `high` |
| GitHub Copilot CLI | `cd <raíz> && copilot --model <id> --effort <nivel>` | "Sonnet 5.5" → `claude-sonnet-5.5`; otro proveedor, en minúsculas y con guiones ("GPT 5.3 Codex" → `gpt-5.3-codex`) | Igual |

Sin herramienta anotada, eliges el modelo y el esfuerzo en el selector del chat antes de escribir. Dentro de una sesión, `/model` cambia los dos en ambas CLIs.

## Subagentes del modo orquestado

En el modo orquestado ([orquestacion.md](orquestacion.md)) cada sesión es un subagente, con el modelo de su nivel: `producto.py siguiente --json` trae, por cada sesión, `nivel`, `modelo` y `subagente` con los valores que acepta la herramienta. En Claude Code, el parámetro de modelo de un subagente es un alias de familia (`haiku`, `sonnet`, `opus` o `fable`), que toma la versión más nueva de esa familia, y el de esfuerzo, `low`, `medium` o `high`.

| Sesión | Nivel | Subagente en Claude Code (por defecto) | Esfuerzo |
| --- | --- | --- | --- |
| 0 y 1a a 1e | `intermedio` | `sonnet` | `medium` |
| 1g, 1f, 2, 3 y 4 | `alto` | `opus` | `high` |
| El orquestador (el chat) | `economico` | — (es el chat: `claude --model claude-haiku-5-5 --effort low`) | `low` |

- **El alias sale del nombre:** "Opus 5.5" da `opus`. Si cambias un nivel con `modelos`, el subagente cambia con él. Un nombre de otro proveedor ("GPT 5.3 Codex") da `null`: el orquestador usa el equivalente de su herramienta para ese nivel.
- **Mismo ahorro que un chat por sesión:** un subagente arranca con su propio contexto (la skill, su referencia y `estado.md`), no con el del orquestador, y le devuelve un resumen de 10 líneas como máximo.

## Por qué se encarece

Cada paso del agente reenvía todo el chat. El costo de una sesión es, a grandes rasgos, **pasos × tamaño del contexto × precio del modelo**. Lo que lo dispara:

1. **Encadenar sesiones en un chat.** El contexto crece en cada paso y nunca baja. Un chat nuevo por sesión arranca con `SKILL.md`, su referencia y `estado.md`.
2. **Volcar páginas.** Una página leída entera queda en el contexto de todos los pasos siguientes. Por eso cada fuente se resume en 3 líneas, las reseñas de un CSV se leen con `resenas` (filtradas y cortas) y el agente no lee `producto.py`.
3. **El modelo alto en todo.** Las cinco líneas de investigación son mecánicas: el intermedio alcanza.

## Medir el costo (`consumo`)

Anotar es opcional y nunca detiene nada. Queda en `producto.json`, en el resumen de `estado.md` y, desde la primera anotación, `siguiente` recuerda las sesiones cerradas que faltan.

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py consumo --sesion 1a --costo '0.40' --carpeta product
```

| Opción | Qué anota |
| --- | --- |
| `--sesion` | La sesión (`0`, `1a`… `4`) u `orquestador` |
| `--costo` | USD, **entre comillas simples**: entre dobles, el shell expande `$` y `"$0.40"` llega mutilado (`consumo` lo rechaza) |
| `--creditos` | AI Credits de GitHub Copilot (`/usage`); el total los suma a 0,01 USD cada uno |
| `--tokens`, `--pasos`, `--modelo` | Lo que informe la herramienta (`45k`, `1.2M`) |
| `--incluye 1a,1b,…` | En la fila del `orquestador`: las sesiones que corrieron como sus subagentes, cada una en su pasada vigente |
| `--pasada <n>` | Otra pasada de la sesión que la vigente: `0` es la primera y `n`, la reapertura `n` (para anotar una que quedó sin anotar) |
| `--chat <id>` | En la fila del `orquestador`: qué chat anota (`orq-1`). El mismo chat usa siempre el mismo y actualiza su fila (`/cost` es acumulado); un chat que no anotó antes usa uno nuevo (`siguiente --json`: `costo.chat_nuevo`). Una fila anotada sin `--chat` es `orq-<n>`, por su orden |

Cada pasada de una sesión (la primera y cada reapertura) va en su fila: `consumo --sesion 1c` anota la pasada vigente y el total, el reporte y `siguiente` las suman. Repetir `consumo` con la misma `--sesion` en la misma pasada actualiza su fila: lo nuevo reemplaza lo mismo y lo demás se conserva. Una fila anotada sin pasada (antes de que se anotaran) cuenta como la primera, y una reapertura cerrada sin consumo aparece como sin anotar (`1c (reapertura 1)`).

| Herramienta | Dónde se ve | Por sesión con subagentes |
| --- | --- | --- |
| Claude Code | `/cost` (USD del chat) | El resultado de cada subagente en primer plano trae sus tokens y la cantidad de herramientas que usó: el orquestador espera a que terminen todos y anota cada uno con `consumo --sesion <id> --tokens <n> --pasos <n>`; en cada parada, arriba, el total del chat con `consumo --sesion orquestador --incluye <las sesiones que lanzó ese chat> --costo '<USD de /cost>'`, sin `--tokens` (ya van por sesión: el total no los cuenta dos veces). El mismo chat actualiza su fila en cada parada con el mismo `--chat` (`/cost` es acumulado); otro chat orquestador va en otra fila, con otro `--chat`. Por verificar en cada versión: el formato no está documentado como estable |
| GitHub Copilot CLI | `/usage` (AI Credits y tokens) | Solo el total del chat: `consumo --sesion orquestador --incluye <sesiones> --creditos <n>` |
| Otra | Lo que muestre | Si no da el uso por subagente, el total con `--incluye` |

Nunca anotes un costo de memoria: si la herramienta no lo muestra, no se anota.
