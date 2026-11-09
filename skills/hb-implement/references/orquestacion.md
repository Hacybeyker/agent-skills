# Orquestar una construcción autónoma por bloques

La receta con la que se construyó una app completa (decenas de miles de líneas, varias fases) sin intervención humana durante la construcción: un plan por escrito, un brief común y **un subagente de `hb-implement` por bloque**, con un orquestador que revisa, verifica y commitea. Úsala solo si el usuario pide construir mucho de una vez; para una tarea normal, el flujo de `SKILL.md` basta.

Los archivos del plan viven en una carpeta de trabajo que el proyecto ignora en git (por ejemplo `reports/<fase>/`).

## Las piezas

| Pieza | Para qué |
| --- | --- |
| `PLAN.md` | La única fuente de verdad de la sesión: reglas, bloques, decisiones, "Para revisar" y cambios de plan |
| `brief-comun.md` | Las reglas que todos los subagentes comparten, escritas una vez |
| Un subagente por bloque | Contexto limpio y barato por bloque: ninguno carga el contexto de los anteriores |
| `decisiones.md` | Lo que cada subagente y el orquestador decidieron solos, con su porqué |
| Una notificación | Avisa al terminar (o al detenerse) |

Una sola conversación larga sale más cara: cada paso reenvía todo el contexto acumulado. El subagente por bloque lo evita.

## Antes de aprobar el alcance

Cada contradicción del alcance termina en una decisión que toma la IA sola. Revisa el documento de alcance con esta lista **antes** de lanzar nada:

- Estado y persistencia coherentes: ningún requisito de conservar datos choca con "el estado vive en memoria".
- Los casos negativos que se piden se pueden alcanzar desde la UI o por un camino de prueba declarado.
- Los identificadores de test (`testTag` o equivalentes) están completos: nada que cada bloque tenga que inventar.
- El orden de la navegación y de las pestañas está fijado.
- Nada ambiguo en rutas, contratos o cuándo ocurre un evento (¿el aviso se abre solo o al confirmar?).

## `PLAN.md`

```markdown
# Plan: <objetivo>

## Reglas
- Autorizado en esta sesión, por escrito (commit, push, usar el emulador, descargar con npx…). Lo que el
  AGENTS.md prohíbe y este plan autoriza vale solo para esta sesión.
- Fuera de alcance: todo lo que no esté en el brief (validaciones, herramientas o dependencias nuevas).
- Quién commitea: el orquestador, no los subagentes.
- Tope: <reintentos por bloque>; si se supera, se detiene y se anota.

## Bloques
| Bloque | Qué | Depende de | Estado | Commit |
| --- | --- | --- | --- | --- |
| a | <entregable verificable> | — | pendiente | |

## Cierre
<verificación final, push, CI, resumen y notificación>

## Para revisar
<lo que una persona debería mirar: decisiones con impacto, cambios de una regla del alcance>

## Cambios de plan
- <AAAA-MM-DD>: <el cambio, completo>
```

Un bloque es algo que se puede construir, probar y commitear por sí solo. Si un bloque se queda grande, divídelo y anótalo en `decisiones.md`.

## `brief-comun.md`

```markdown
Eres el subagente de un bloque. Carga `hb-implement` y el perfil del proyecto.

- Alcance aprobado: no esperes confirmación del plan. Anota tus decisiones en <decisiones.md>
  (qué, por qué, alternativa) y lleva a "Para revisar" lo que cambia una regla del alcance.
- Lee completo el documento de alcance <ruta> y el bloque que te toca.
- No hagas commit ni push. No toques lo que el bloque no pide.
- Corre el DoD y la autorrevisión de `hb-implement` antes de entregar.
- Entrega en el idioma del proyecto: resumen, archivos, DoD, mensaje de commit propuesto, ítems de
  verificación en el dispositivo (priorizados, cada uno con su test o "sin test"), decisiones y riesgos.
```

El prompt de cada bloque lleva solo lo propio: el entregable, los archivos clave, los tests que se esperan y las aclaraciones del alcance que el orquestador ya resolvió.

## Qué hace el orquestador con cada bloque

1. **Lanza** al subagente con el brief común y la parte del bloque. Un subagente a la vez si comparten árbol de trabajo; en paralelo solo con un worktree por subagente. No corras Gradle, el emulador ni otro agente sobre el mismo árbol mientras alguien edita.
2. **Lee la lógica**, no solo la lista de archivos y el DoD: las clases nuevas con reglas de negocio, estado y persistencia. El DoD no ve los fallos de diseño, y uno de los que se escaparon estaba en una clase que nadie leyó. Para eso sirve la revisión rápida de `hb-review` sobre el diff del bloque.
3. **Corre el DoD él mismo.** Con la caché del build, repetirlo es barato.
4. **Commitea** con el mensaje que propuso el subagente, ajustado, en el entorno del proyecto: zona horaria local y hooks activos (nada de `--no-verify` salvo con el DoD probado). Para agrupar commits, hacer push o abrir un PR puede cargar `hb-commit`.
5. **Registra:** actualiza el estado y el commit en `PLAN.md`, y anota en `decisiones.md` sus propias decisiones (dividir un bloque, fijar algo que el alcance no fijaba) **antes** de delegar.
6. Si hay que corregir algo, reanuda al mismo subagente con un mensaje si la herramienta lo permite, en lugar de lanzar otro.

## Cambios de plan

Se escriben **completos** en la sección "Cambios de plan" de `PLAN.md` (o en el `/goal`), nunca por referencia ("como dije antes"): una sesión nueva o un hook no ve esa conversación, y se pierden vueltas buscándola.

## Al terminar

Una notificación, solo si el usuario la pidió. En macOS:

```bash
osascript -e 'display notification "Plan terminado" with title "Construcción" sound name "Glass"'
```

En otros sistemas, la que ofrezca la herramienta. Cierra con un resumen que lleve "Para revisar" arriba: es lo primero que una persona debe leer.

## Prompt para abrir el chat del orquestador

```text
Modelo · Esfuerzo: <p. ej. intermedio · medio>
Ejecuta <carpeta>/PLAN.md como orquestador: lanza un subagente de hb-implement por bloque con
<carpeta>/brief-comun.md, lee la lógica de cada bloque, corre el DoD, commitea y sigue con el
siguiente. Los cambios de plan van solo en PLAN.md.
```

La primera línea es para quien pega el prompt: dice con qué modelo y esfuerzo abrir el chat (con los nombres de su herramienta) y no se le pasa al agente. Cada chat nuevo que se proponga, por ejemplo el de la verificación en el dispositivo o el del siguiente bloque grande, lleva la suya. En la experiencia que originó esta receta, un modelo intermedio construyó los bloques con el DoD en verde y a menor costo que el superior.
