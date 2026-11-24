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

Los nombres son los de fábrica (`intermedio` y `alto`). Las decisiones de las puertas no usan modelo: van en la terminal.

## Cambiar los nombres o la herramienta

`producto.py modelos` muestra la tabla de esta idea. Con opciones, la cambia una vez y `siguiente` la usa en adelante:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py modelos --intermedio "Sonnet 5.5" --alto "Opus 5.5" --herramienta claude --carpeta product
```

- **`--intermedio` y `--alto`:** el nombre del modelo de cada nivel. Un id (sin espacios ni mayúsculas, como `claude-opus-5-5`) va tal cual al comando.
- **`--herramienta`:** con `claude` o `copilot`, cada chat de `siguiente` trae su línea `Abrir:` con el comando completo; `ninguna` la quita.
- **`--herramienta otra --comando "<cli> --model {modelo}"`:** para otra CLI. `{modelo}` se reemplaza por el nombre del nivel y, si el comando lo lleva, `{esfuerzo}` por `low`, `medium` o `high`.

| Herramienta | Comando que imprime `siguiente` | Id del modelo | Esfuerzo |
| --- | --- | --- | --- |
| Claude Code | `cd <raíz> && claude --model <id> --effort <nivel>` | "Sonnet 5.5" → `claude-sonnet-5-5` | `medio` → `medium`, `alto` → `high` |
| GitHub Copilot CLI | `cd <raíz> && copilot --model <id> --effort <nivel>` | "Sonnet 5.5" → `claude-sonnet-5.5`; otro proveedor, en minúsculas y con guiones ("GPT 5.3 Codex" → `gpt-5.3-codex`) | Igual |

Sin herramienta anotada, eliges el modelo y el esfuerzo en el selector del chat antes de escribir. Dentro de una sesión, `/model` cambia los dos en ambas CLIs.

**Con subagentes** (un chat orquestador que lanza las sesiones): cada subagente usa el modelo de su sesión. En Claude Code, el parámetro `model` de cada subagente acepta el alias (`sonnet`, `opus`); con otra herramienta, lo que ofrezca.

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
| `--incluye 1a,1b,…` | En la fila del `orquestador`: las sesiones que corrieron como sus subagentes |

Repetir `consumo` con la misma `--sesion` actualiza su fila: lo nuevo reemplaza lo mismo y lo demás se conserva.

| Herramienta | Dónde se ve | Por sesión con subagentes |
| --- | --- | --- |
| Claude Code | `/cost` (USD del chat) | El resultado de cada subagente trae sus tokens y la cantidad de herramientas que usó: el orquestador anota cada uno con `consumo --sesion <id> --tokens <n> --pasos <n>` y, al cerrar, el total del chat con `consumo --sesion orquestador --incluye <sesiones> --costo '<USD de /cost>'`. Por verificar en cada versión: el formato no está documentado como estable |
| GitHub Copilot CLI | `/usage` (AI Credits y tokens) | Solo el total del chat: `consumo --sesion orquestador --incluye <sesiones> --creditos <n>` |
| Otra | Lo que muestre | Si no da el uso por subagente, el total con `--incluye` |

Nunca anotes un costo de memoria: si la herramienta no lo muestra, no se anota.
