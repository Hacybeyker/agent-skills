# Prompts listos para copiar

Para el usuario, no para el agente. Cada caso trae dónde va (un chat nuevo, con el **nivel de modelo y el esfuerzo** que conviene, o la terminal) y, en un bloque aparte, el texto para pegar: **copia solo el bloque**; lo que está fuera es la explicación. Las partes entre `<>` se completan.

- **Niveles de modelo:** económico, intermedio, diagnóstico y alto son los de `modelos` en `plan.json`: por defecto Haiku 5.5, Sonnet 5.5, Sonnet 5.5 (el diagnóstico toma el intermedio si el plan no lo nombra) y Opus 5.5. `perf.py siguiente` imprime los de tu plan; con otra herramienta, pones sus equivalentes una vez en el plan.
- **Cómo se abre cada chat:** cada caso trae el comando para abrirlo con su modelo y su esfuerzo en Claude Code y en GitHub Copilot CLI ([modelos.md](modelos.md) · Abrir el chat con el modelo y el esfuerzo). Con la línea `Herramienta de IA:` en la sección de rendimiento de `AGENTS.md`, `perf.py siguiente` imprime solo el de tu herramienta.
- **Cada paso dice dónde va:** **Terminal** (sin chat: el comando empieza con `cd <raíz> &&`) o **Chat nuevo** (el comando que lo abre y el texto para pegar). Si un paso necesita un dato que no se puede deducir (una variable de entorno, el serial con varios dispositivos), el primer paso es el comando para cargarlo.
- **El mismo texto sirve para empezar la primera vez y las siguientes.** La skill elige la sesión según el estado del proyecto: sin setup hace el setup (sesión 0); con el setup listo, la ficha y el plan (sesión 1); con un `estado.md`, la que diga su "Siguiente paso". No hace falta decirle cuál: el agente lo dice en su primera línea, con el motivo (`Sesión 1 · ficha (setup listo en AGENTS.md)`).
- **Lo que sigue a cada sesión no hace falta pedirlo:** cada comando de `perf.py` y cada sesión terminan imprimiendo el paso siguiente, listo para copiar, y lo dejan en "Siguiente paso" de `estado.md`.
- **Cada texto de chat termina con "No hagas commit ni push."** La skill ya dice que el agente solo propone el commit; la línea explícita evita que una herramienta o un modelo lo haga igual. `perf.py` la agrega sola en los textos que imprime (`siguiente`, `humo`, `decidir`, `reporte`).
- **El costo de un chat** es lo que muestre tu herramienta al cerrarlo (`/cost` en Claude Code; `/usage` en GitHub Copilot CLI, que informa AI Credits y tokens). Anotarlo es opcional.

## Empezar

### Mejorar el pedido antes de la sesión 1 (0 · pedido)

Antes de gastar en la sesión 1, la skill te devuelve tu pedido mejorado: tramos con su marca de inicio y de fin, la dirección de cada scroll, el caso con y sin datos, un flujo de repetición si el síntoma empeora con el uso, y las preguntas que no puede resolver sola. **No lee código, no toca el dispositivo ni crea la investigación** (las reglas están en [ficha.md](ficha.md) · Reglas para un buen pedido). Cuesta de 0,1 a 0,3 USD; anótalo como `0 · pedido` con el comando `perf.py consumo` que te da la sesión 1 al terminar (ya con su carpeta: solo pones el costo).

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Usa hb-performance: mejora este pedido: <el flujo en tus palabras: de dónde a dónde, qué tocas, qué debe verse y qué se nota>. No hagas commit ni push.
```

Te devuelve el pedido mejorado en un bloque de código (para pegar en la sesión 1), las preguntas que falten y el chat de la sesión 1.

### Una pantalla o un flujo (la primera vez en el proyecto, o con el setup listo)

**La primera vez en el proyecto, este pedido hace el setup (sesión 0)** y guarda tu flujo, tal cual lo escribes, para la sesión 1: por eso te pide el flujo aunque todavía no lo mida. Al terminar el setup, la prueba de humo te da el chat de la sesión 1 con tu pedido entero. "Empieza por el setup" también sirve: hace lo mismo.

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Usa hb-performance: quiero analizar el rendimiento de <pantalla o flujo: de dónde a dónde y qué debe verse al final; qué se nota: "tarda", "jank al hacer scroll">. Dispositivo <serial>. No hagas commit ni push.
```

Sin build de profiling, el agente hace el setup (sesión 0) y te deja el comando de la prueba de humo; esa prueba termina con el texto del chat siguiente, con tu flujo ya escrito. Con el setup listo, hace la sesión 1: te pregunta todo en un solo mensaje y arma el plan.

### Flujo largo (login, avisos y varias pantallas antes de lo que se mide)

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Usa hb-performance: medir <tramo: de qué lista a qué detalle>. Para llegar ahí hay que <login, aceptar términos, omitir huella, ir al tab X>. Dispositivo <serial>. No hagas commit ni push.
```

Sesión 1 con el patrón de flujos largos. El texto no fija cómo se recorre: el agente te lo pregunta y recomienda un flow de Maestro en `preparar` y `adb` para el tramo medido; si ya lo tienes decidido, agrégalo al pedido ("recorrido manual", "con deep link") y la pregunta sale igual, con tu elección marcada, para que puedas cambiarla. Si el flujo necesita credenciales, van en variables de entorno: cárgalas en la terminal **antes de abrir el agente** (solo ve las de la terminal desde la que se abrió) y, después, en la terminal donde midas, una por variable, con lectura oculta para las claves: `cd <raíz> && printf 'APP_CLAVE_PRUEBA: ' && read -r -s APP_CLAVE_PRUEBA && echo && export APP_CLAVE_PRUEBA` (y sin `-s` para un usuario: `cd <raíz> && printf 'APP_USUARIO_PRUEBA: ' && read -r APP_USUARIO_PRUEBA && export APP_USUARIO_PRUEBA`). Lo que escribes no queda en el historial ni en ningún archivo. `perf.py siguiente` imprime ese paso primero cuando el plan las necesita.

### Flujo con un paso que hace una persona (autorizar en otra app, completar un pago)

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Usa hb-performance en modo triage: medir <flujo: de qué pantalla a qué resultado>. En el medio hay un paso que hago yo (<autorizar en otra app, resolver un desafío>): déjalo como pausa del recorrido y no midas ese tiempo. Dispositivo <serial>. No hagas commit ni push.
```

Sesión 1 con el patrón de "Flujos que pasan por otra app": el recorrido se detiene en una pausa que atiendes en tu terminal (haces el paso y presionas Enter; con `x` + Enter esa corrida se descarta), y el plan mide a cada lado de la pausa, no a través de ella. Las capturas de este flujo las corres tú: un agente no tiene terminal donde atender la pausa. Si cada corrida es una operación real, cuenta cuántas son antes de aprobar (`estado.md` lo dice en "Cómo se recorre").

### Arranque en frío (setup listo)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py nuevo --receta arranque-frio --paquete <applicationId> --serial <serial> --carpeta reports/perf/arranque-frio/<AAAA-MM-DD> --instalar "<comando que instala el build de profiling>"
```

Arma el plan sin sesión 1 e imprime los comandos para medir. Agrega `--red` si la primera pantalla carga de la red.

### Solo el diagnóstico, sin cambiar código (triage)

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Usa hb-performance en modo triage: diagnostica <flujo> con 3 corridas, sin control ni mejoras. Dispositivo <serial>. No hagas commit ni push.
```

Termina en el reporte inicial.

### Qué herramientas hacen falta y cómo está el setup

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py setup --estado
```

Solo lectura. Lista las herramientas de la máquina (obligatorias: Python 3.8 o superior, git, `adb` y `trace_processor`; según el caso, Java 17 o superior; opcionales, `retrace`, Maestro, `ffmpeg` y `scrcpy`) con la ruta donde encontró cada una, también fuera del `PATH`. **La skill no instala ni configura nada:** si falta una, dice para qué sirve y dónde obtenerla, y la instalas tú o tu herramienta de entorno. Después dice el caso del setup del proyecto (versionado, en un parche o sin setup), el parche vigente con su ficha y el paso que sigue.

### Prueba de humo del setup

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py humo --paquete <applicationId> --serial <serial> --instalar "<comando de instalación>"
```

### Toda la investigación desde un solo chat (modo orquestado)

Un chat recorre la investigación entera: lanza cada sesión como un subagente con su modelo, corre las capturas con recorrido automático y se detiene solo donde haces falta (la decisión de las mejoras, la aprobación de la ficha, una clave, un recorrido manual, un error). No abres chats ni pegas pasos, y el ahorro de una sesión por chat se mantiene ([orquestacion.md](orquestacion.md)). Necesita una herramienta con subagentes (Claude Code los tiene); sin ellos, la skill lo dice y sigue en modo guiado. Sirve la primera vez en el proyecto (empieza por el setup) y con el setup listo.

**Dónde:** chat nuevo · Económico · bajo (es el orquestador: cada sesión usa el modelo de su nivel)

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-haiku-5-5 --effort low` en Claude Code. Si el flujo necesita credenciales, cárgalas antes en esa misma terminal (el caso "Flujo largo"). Después pega el bloque.

```text
Usa hb-performance en modo orquestado: quiero analizar el rendimiento de <pantalla o flujo: de dónde a dónde y qué debe verse al final; qué se nota>. Dispositivo <serial>. No hagas commit ni push.
```

Cuando se detiene, te dice qué hacer y dónde: en la terminal (con el comando completo) o en el mismo chat. Al terminar te da el comando `perf.py consumo` con la fila `orquestado`: solo pones lo que muestra `/cost` en ese chat.

## Seguir

### Retomar donde quedó (cualquier sesión)

**Dónde:** chat nuevo, con el modelo y el esfuerzo que diga "Siguiente paso"

**Ábrelo** con el comando que imprime `perf.py siguiente` (está en "Siguiente paso" de `estado.md`): ya trae el modelo y el esfuerzo de esa sesión para tu herramienta. Después pega el bloque.

```text
Sigue hb-performance con <ruta absoluta>/estado.md. No hagas commit ni push.
```

### Retomar un chat que se cortó a la mitad

**Dónde:** terminal, con el comando de tu herramienta que reabre una sesión eligiéndola de una lista

```bash
claude --resume
```

Ese es el de Claude Code; en Copilot CLI, `copilot --resume`. Evita el que continúa "la última" sin preguntar: puede tomar la de otra terminal. Si la sesión ya había terminado, no la reabras: usa el caso anterior en un chat nuevo.

### Se cortó a la mitad (la terminal se cerró en plena captura o en el reporte)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py siguiente --carpeta <carpeta>
```

Interrumpir es seguro. Si algo quedó a medias, `siguiente` lo dice y su primer paso es `perf.py recuperar --carpeta <carpeta>`, que detiene la traza que siguió grabando en el dispositivo, aparta la traza a medias y deja lista la carpeta para completar desde la corrida que falta (o repetir el reporte).

### Pausar una investigación para después

Un triage con mejoras termina con "Elige uno": aplicar ahora, pausar o cerrar; una investigación rigurosa sin decisión, con decidir, pausar o cerrar sin aplicar. Para pausar (quita las marcas guardándolas en su parche, deja el setup puesto y anota el commit de cada repo):

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py pausar --carpeta <carpeta>
```

### Reanudar una investigación en pausa

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py reanudar --carpeta <carpeta>
```

Repone el setup y las marcas, dice qué cambió en el código desde la pausa y si la línea base sirve, y te da el paso siguiente (con `--simular`, solo lo muestra).

### Archivar una investigación que no se va a retomar

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py archivar --carpeta <carpeta> --motivo "<por qué no se va a retomar>"
```

Para la que quedó en pausa (o sin marcas en el árbol) y no se va a retomar. No borra nada: la anota como archivada, con la fecha y el motivo, y deja de contar para el aviso de `setup --estado` que impide actualizar el parche del setup mientras haya investigaciones con mediciones. Si todavía tiene marcas en el árbol, se detiene y te da `pausar` primero. Si cambias de idea, `reanudar` la retoma y revisa si la línea base sigue sirviendo. La que terminó no se archiva: se cierra (`cerrar`).

### Ver todas las investigaciones del proyecto

**Dónde:** terminal, sin chat, en la raíz del proyecto

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py estado
```

Cada una con su estado (abierta, en pausa, archivada o cerrada), las marcas puestas por repo, las mejoras y su paso siguiente. Con dos o más que ya tienen reporte, también imprime el comando del caso siguiente.

### Un solo reporte de gerencia de varias investigaciones

**Dónde:** terminal, sin chat, en la raíz del proyecto (opcional; no cambia nada en ninguna investigación)

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py reporte --gerencia-unificado --todas
```

Deja `reporte-gerencia-unificado.html` en la carpeta de las investigaciones; con `--carpetas <carpeta> <carpeta>` en lugar de `--todas`, solo esas.

### No sé cuál es el paso

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py siguiente --carpeta <carpeta>
```

Recalcula el paso y lo imprime.

### Aprobar el plan y seguir (al final de la sesión 1)

**Dónde:** el mismo chat de la sesión 1

```text
Apruebo la ficha y el plan. No hagas commit ni push.
```

Te deja los comandos de la medición.

### Decidir qué mejoras se aplican (después de la sesión 2)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py decidir --carpeta <carpeta> --aprobar M1,M3 --descartar M2 --pendiente -
```

Imprime el chat de la sesión 3. Las mejoras a prueba se aprueban igual. La decisión queda en "Decisiones" de `estado.md` con la fecha y la hora (y, si consta, el agente que la corrió desde un chat: Claude Code marca sus shells; sin esa marca queda solo la hora), y antes del chat de la sesión 3 `siguiente` dice cuándo se aprobó cada mejora. `--pendiente` es "para más adelante", no "sin decidir".

### Seguir en modo orquestado después de decidir

**Dónde:** el mismo chat del orquestador, después de correr `perf.py decidir` en tu terminal (el comando que te dio el orquestador)

```text
Continúa. No hagas commit ni push.
```

El orquestador vuelve a pedir el paso a `perf.py` y sigue con la sesión 3 de cada mejora aprobada, la medición después y el cierre. "listo" sirve igual después de una captura que corriste tú (recorrido manual).

### Retomar en modo orquestado (el chat del orquestador se cerró)

**Dónde:** chat nuevo · Económico · bajo

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-haiku-5-5 --effort low`, o reabre el mismo con `cd <raíz> && claude --resume` eligiéndolo de la lista. Después pega el bloque.

```text
Sigue hb-performance con <ruta absoluta>/estado.md en modo orquestado. No hagas commit ni push.
```

### Reabrir una decisión (no fue tuya, o cambiaste de idea)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py decidir --carpeta <carpeta> --reabrir M1
```

Vuelve a dejar como propuesta una mejora que quedó aprobada, pendiente o descartada, y lo anota con la fecha y la hora. Solo cambia el plan: no toca código. Una mejora ya aplicada no se reabre: se quita con `lineabase --quitar-mejoras`.

### Aplicar una mejora aprobada

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Sigue hb-performance con <ruta>/estado.md: sesión 3, aplica <id>. No hagas commit ni push.
```

### Cerrar la investigación (medición después lista)

**Dónde:** chat nuevo · Económico · bajo

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-haiku-5-5 --effort low` en Claude Code, o `cd <raíz> && copilot --model claude-haiku-5.5 --effort low` en GitHub Copilot CLI. Después pega el bloque.

```text
Sigue hb-performance con <ruta>/estado.md. No hagas commit ni push.
```

### Cerrar sin aplicar mejoras (no hubo, o quedaron descartadas o pendientes)

**Dónde:** chat nuevo · Económico · bajo

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-haiku-5-5 --effort low` en Claude Code, o `cd <raíz> && copilot --model claude-haiku-5.5 --effort low` en GitHub Copilot CLI. Después pega el bloque.

```text
Sigue hb-performance con <ruta>/estado.md: cierra la investigación sin fase después. No hagas commit ni push.
```

Al terminar, el agente te entrega `perf.py cerrar`: quita los cambios temporales con su parche, da el DoD (`--dod` lo corre) y, si el setup va en un parche, lo quita al final (`--sin-setup` lo deja puesto). Cuando ya no queda nada, `siguiente` lo dice: "Investigación cerrada: no queda ningún paso por ejecutar".

### Anotar el costo de un chat

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py consumo --carpeta <carpeta> --sesion '<2 · diagnóstico>' --modelo '<modelo del chat>' --esfuerzo <alto> --costo '<0.80 USD>'
```

Es opcional. `perf.py siguiente` imprime este comando ya completo por cada sesión hecha sin anotar, con la opción de tu herramienta (la línea `Herramienta de IA:` de `AGENTS.md`): solo cambia el valor. El costo va **entre comillas simples**: entre dobles, el shell se come el `$` ("$0.40" llega como "-bash.40", o "zsh.40" en la terminal de un IDE) y `consumo` lo rechaza. Con GitHub Copilot CLI, lo que muestra `/usage` son AI Credits, no tokens: `--creditos <número>` (y, si quieres, `--tokens-entrada <↑> --tokens-cache <cached> --tokens-cache-escritura <written> --tokens-salida <↓>`). Con Claude Code, `--costo '<monto en USD>'` (lo que muestra `/cost`) o, justo al cerrar el chat y sin copiar nada, `--desde-transcript auto` (tokens y pasos del transcript local). Repetir el comando con la misma `--sesion` actualiza su fila: lo que vuelves a anotar reemplaza lo mismo y lo demás se conserva (por ejemplo, `--costo` después de `--desde-transcript`). El total de la investigación queda debajo de la tabla "Consumo" de `estado.md` y en los reportes ([modelos.md](modelos.md) · Consumo por herramienta).

## Pedidos puntuales

### Volver a medir una fase (cambió el build, hubo ruido)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --fase <antes|control|despues> --corridas <5|10> --rehacer
```

Con varios flujos, `--flujo <nombre>`: solo se rehace ese.

### Explicar un resultado

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Con hb-performance, lee <ruta>/comparacion.md y <ruta>/estado.md y explícame por qué <métrica> dio <veredicto>. No cambies nada. No hagas commit ni push.
```

### Mejorar el reporte

**Dónde:** chat nuevo · Económico · bajo

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-haiku-5-5 --effort low` en Claude Code, o `cd <raíz> && copilot --model claude-haiku-5.5 --effort low` en GitHub Copilot CLI. Después pega el bloque.

```text
Con hb-performance, mejora el resumen ejecutivo, el resumen para gerencia y la lectura de la comparación en <ruta>/estado.md (<qué falta o qué sobra>) y vuelve a generar el reporte con perf.py reporte --carpeta <carpeta> --html. No hagas commit ni push.
```

### Regenerar el reporte sin tocar el texto

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py reporte --carpeta <carpeta> --html
```

Deja las dos versiones: `reporte-final-dev.html` (técnico) y `reporte-final-gerencia.html` (en palabras, para un equipo no técnico). Con `--inicial`, las del reporte inicial. Si el reporte inicial que hay es de una versión anterior (otra estructura), `siguiente` ofrece este comando con `--inicial` en un aviso opcional, antes de los caminos de la decisión (no es un paso numerado); antes de sobrescribirlo, `reporte` guarda una copia (`reporte-inicial-dev.estructura-anterior.html`), sin pisar ninguna otra.

### Unir el video de la prueba (instalaste ffmpeg después de la prueba, o el video es de 0.17.0)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py video --carpeta <carpeta>
```

Arma de nuevo el video de evidencia de cada prueba desde `video/<flujo>/eventos.json`, sin repetirla: el visor `prueba-<flujo>.html` y, con `ffmpeg`, el video unido y rotulado `prueba-<flujo>.mp4` (`--flujo <flujo>` para uno solo). Los tramos originales quedan en `video/<flujo>/`. Si la prueba se hizo con 0.17.0, el video sale con los rótulos de ahora (cada parte dice si la traza graba y si se mide; cada marca, su papel), sin repetirla: `siguiente` lo ofrece en una línea opcional. Cómo instalar `ffmpeg` sin root: `perf.py setup --estado` o [setup.md](setup.md) · Requisitos de la máquina.

### Agregar una métrica, un tramo o una marca

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Con hb-performance, agrega al plan de <carpeta> una métrica de usuario (o un tramo en segmentos) desde <marca> hasta <marca> (familia <app|e2e>) y dime si hace falta medir de nuevo. No hagas commit ni push.
```

### Medir una mejora en otro escenario de tiempo

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Con hb-performance, agrega al plan de <carpeta> un escenario del flujo <flujo> con <qué cambia: por ejemplo, abrir enseguida en vez de esperar 4 s> (escenario_de y variables; si recorrido.sh o preparar.sh todavía no leen esa variable, dime que cambiarlos pide rehacer la línea base) y dime qué hay que medir. No hagas commit ni push.
```

### Una pregunta sobre una traza

**Dónde:** chat nuevo · Diagnóstico · alto

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort high` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort high` en GitHub Copilot CLI. Después pega el bloque.

```text
Con hb-performance, en la traza <ruta>/antes/<flujo>_<n>.perfetto-trace.gz responde: <pregunta>. Usa perf.py consulta con LIMIT. No hagas commit ni push.
```

### Por qué se cerró la app

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py salidas --carpeta <carpeta>
```

Las últimas salidas del proceso según el sistema (Android 11 o superior), con el motivo en claro: crash, crash nativo, ANR, poca memoria, uso excesivo de recursos. Sin investigación, `--paquete <applicationId>` en vez de `--carpeta`. Para un crash trae el inicio de la pila, desofuscada si encuentra el mapping de la variante medida.

### Pasar un triage a riguroso para aplicar una mejora

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py decidir --carpeta <carpeta> --profundidad riguroso
```

Imprime, en orden, lo que falta: completar `antes`, medir `control` y la decisión.

### Actualizar la instrumentación tras actualizar la skill

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py instrumentar --modulo <el módulo que genera el APK, normalmente app> --paquete <paquete>.perf --actualizar
```

Con el setup en un parche, `perf.py setup --reponer` te da esta secuencia cuando la skill es más nueva que el parche: actualizar, instalar, la prueba de humo y `setup --guardar` (el parche nuevo pasa a ser el vigente; el anterior queda guardado como reemplazado). Hazlo **entre** investigaciones, no en medio de una: una plantilla nueva puede nombrar distinto las secciones (desde 0.10.0, los endpoints con rutas largas se acortan desde la izquierda), y antes y después tienen que nombrar igual. Después, el formateador y el DoD del proyecto. Si un archivo sale con `✖ no se actualiza`, alguien lo editó a mano (o es de una versión sin huella): mira la diferencia y, si aceptas reemplazarlo, repite con `--actualizar --forzar`, que deja lo que había en `<archivo>.orig`.

### Reponer el setup antes de medir (va en un parche y no está en el código)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py setup --reponer
```

No hace falta recordarlo: `siguiente`, `nuevo`, `humo` y `capturar` lo dan como primer paso cuando corresponde. Aplica el parche vigente solo si es de este repo y de esta app (lo dice su ficha), si no cambió desde que se guardó y si aplica limpio; si el proyecto cambió, prueba con `--3way` y lo aplica solo sin conflictos, avisándolo. **Si se detiene, no tocó nada** y dice qué falta: cambios tuyos sin commitear en esos archivos (haz el commit y repite), un parche de otro repo o de otra app, o conflictos (la sesión 0 genera el setup de nuevo). Con `--simular` solo muestra qué haría. No apliques el parche a mano.

### Guardar el setup como parche (el equipo no lo quiere en el repo)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py setup --guardar --quitar --archivos <archivos del proyecto que se editaron a mano para el setup>
```

Lo corre la sesión 0 al terminar, si eliges "en parche". `--archivos` lleva los archivos cableados a mano (el `build.gradle(.kts)`, cada archivo con un builder de red, la pantalla con `reportFullyDrawn`); los que generó la skill los reconoce sola. Guarda solo el setup, sin pisar ningún parche, con su ficha al lado (repo, `applicationId`, versión de la skill, commit base y SHA-256), deja la línea `Setup: en parche <ruta>` en `AGENTS.md` y lo quita del árbol. Sin `--quitar` lo guarda y lo deja puesto. Nunca se lleva trabajo tuyo dentro del parche: si un archivo tiene líneas del setup y otras tuyas, se detiene sin guardar nada y te da el comando; haz primero el commit de lo tuyo o, si todo el archivo es del setup, agrégalo a `--archivos`.

### Quitar el setup al terminar (va en un parche)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py setup --quitar
```

`perf.py cerrar` ya lo hace como último paso; este comando es para quitarlo fuera de un cierre. Si el setup cambió desde que se guardó (por ejemplo, tras `instrumentar --actualizar`), primero guarda un parche nuevo; después guarda un respaldo, comprueba que revierte limpio y lo quita. Con el setup versionado no quita nada y lo dice.

### Decir cuál es el parche del setup (hay más de uno, o el setup se perdió)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py setup --vigente <parche>
```

`perf.py` nunca adivina: si hay dos parches de setup sin uno vigente, o `AGENTS.md` dice "setup listo" y el código no está, `siguiente` y `setup --estado` te dan este comando por cada parche que encontraron. Corre solo el del parche que corresponde: comprueba que es de este repo y lo deja escrito en `AGENTS.md`.

### Un módulo del alcance llega compilado (binario)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py setup --estado --carpeta <carpeta> --comprobar-modulos
```

La sesión 1 registra los módulos del alcance (`--modulos <módulo> …`) y `perf.py` le pregunta a Gradle si cada uno se compila desde código o llega como binario. **Un módulo binario no se edita**, aunque su código esté en disco: no llegaría al APK. `siguiente` te dice el archivo y la clave del proyecto que lo controlan; cámbialos tú (la skill no toca ese archivo), sincroniza Gradle y corre este comando para comprobarlo de nuevo. Si no puedes compilarlo desde código, `--confirmar <módulo>=binario` lo deja registrado: se mide desde el módulo app y la mejora es del lado de la app o un pedido al equipo dueño.

### Fijar el parche de marcas vigente (rehiciste las marcas, o `cerrar` lo pide)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py marcas --carpeta <carpeta> --separar
```

Arma el parche con solo las marcas (de un archivo que también tiene una mejora, los hunks que no son de ella), sin pisar ninguno, y lo deja como el vigente de su repo en `estado.md`; el anterior queda como reemplazado. Si ya tienes el parche, `marcas --carpeta <carpeta> --vigente <parche>`. Sin opciones, muestra el vigente de cada repo. `cerrar` y `lineabase` usan solo el vigente: con dos sin decir cuál, se detienen y `siguiente` te pregunta.

### Pasar una investigación de una versión anterior a la actual

**Dónde:** chat nuevo, con el modelo intermedio y esfuerzo medio (el comando lo da `siguiente`)

```text
Sigue hb-performance con <ruta absoluta>/estado.md: pasa esta investigación a la versión actual para rehacer la línea base. No hagas commit ni push.
```

`siguiente` lo ofrece solo cuando una investigación medida con una versión anterior no puede afirmar "igual contra igual" (un archivo del recorrido cambió entre fases, según su fecha). El chat actualiza la instrumentación, repone las marcas con el parche vigente y deja el plan listo; después, `lineabase --quitar-mejoras` y la secuencia de siempre.

### Investigar algo que quedó en "Pendientes"

**Dónde:** chat nuevo · Intermedio · medio

**Ábrelo** (terminal, desde la raíz del proyecto): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después pega el bloque.

```text
Usa hb-performance: nueva investigación sobre <pendiente, con el H# del estado.md anterior en <ruta>>. Dispositivo <serial>. No hagas commit ni push.
```

## Qué más se puede capturar

Además de las fases, hay capturas que traen otros datos. Las de diagnóstico (`cpu`, `completa`) **alteran los tiempos**: van solas, con `--prueba`, y nunca se mezclan con las fases; `capturar --fase … --config <x>` distinta de la de las otras fases se detiene con ese motivo. Todas van en la terminal, sin chat.

| Captura | Para qué sirve | Dónde va | Comando |
| --- | --- | --- | --- |
| `base` (por defecto) | Tiempos, frames, hilo principal, red y marcas | Fases (antes, control, después) | `cd <raíz> && python3 -I <skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --fase antes --corridas 10` |
| `--memoria` | PSS, heaps, actividades y vistas vivas después de cada corrida (`dumpsys meminfo`, fuera de la traza) | En fases: **en todas o en ninguna** | El de la fase, con `--memoria` al final |
| `--config cpu` | Qué funciones ocupan el hilo principal (muestreo de CPU; con R8, desofuscadas) | Solo diagnóstico, una corrida | `cd <raíz> && python3 -I <skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --prueba --config cpu` |
| `--config completa` | Por qué espera o se bloquea el hilo principal (quién lo despierta, E/S, locks). **No trae muestreo de CPU**: para eso, `cpu` | Solo diagnóstico, una corrida | `cd <raíz> && python3 -I <skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --prueba --config completa` |
| `salidas` | Por qué se cerró la app (crash, ANR, poca memoria), según el sistema; Android 11 o superior | En cualquier momento, sin traza | `cd <raíz> && python3 -I <skill>/scripts/perf.py salidas --carpeta <carpeta>` |
| `hilos_ajenos` (en el plan) | CPU y red de hilos del proceso que no son de la app (un servidor embebido) | Todas las capturas, si el plan los declara | Se declara en `plan.json` ([ficha.md](ficha.md)); no es un comando aparte |

## Reglas que te ahorran dinero

- **Un chat por sesión.** Si el agente dice que terminó, abre otro: seguir en el mismo cuesta varias veces más por paso. La excepción es el modo orquestado: un solo chat, pero cada sesión corre en un subagente con su propio contexto.
- **Si el paso siguiente es un comando, no abras un chat**: un chat que solo lee `estado.md` para decírtelo cuesta unos 0,2 USD.
- Las mediciones y la decisión van en tu terminal: cero tokens.
- Si una corrida se va a otra pantalla, no esperes a que termine: `x` + Enter en la terminal de la captura la corta y sigue con la siguiente.
- Si el agente te pide el costo o que vuelvas a su chat, no hace falta: `perf.py consumo` lo anota desde la terminal, con lo que muestre tu herramienta.

## Permisos recomendados para auto mode

Esta sección es de Claude Code; con otra herramienta, aprueba lo equivalente con su propio mecanismo de permisos (en Copilot CLI, los permisos por comando). En auto mode el clasificador de permisos puede denegar una secuencia de `adb` (un `input swipe` seguido de `screencap`, por ejemplo) sin un criterio que se vea, y un chat que se detiene a pedir permiso se paga entero. Pre-aprueba lo que la skill usa, **antes de empezar**, con `/permissions` o en `.claude/settings.local.json` del proyecto (el local no se commitea). La skill no cambia tus permisos: los agregas tú, y con otra herramienta, el equivalente.

| Para qué | Regla (`permissions.allow`) |
| --- | --- |
| Todo `perf.py` (nuevo, capturar, diagnostico, comparar, reporte...) | `Bash(python3 -I <ruta-absoluta-de-la-skill>/scripts/perf.py *)` |
| Gradle: formateador, DoD, `assemble`/`install` de la variante | `Bash(./gradlew *)` y, si pasas el serial así, `Bash(ANDROID_SERIAL=* ./gradlew *)` |
| Lo que el agente escribe con `adb` en la ficha (buscar coordenadas, tocar, comprobar la pantalla) | `Bash(adb devices)`, `Bash(adb -s * shell uiautomator dump *)`, `Bash(adb -s * pull *)`, `Bash(adb -s * shell input *)`, `Bash(adb -s * shell dumpsys *)`, `Bash(adb -s * shell getprop *)` |
| Lo mismo sin pensarlo, en un dispositivo de pruebas | `Bash(adb *)`: incluye `uninstall` y `pm clear`, que la skill nunca usa |

- Las mediciones (`capturar`, `diagnostico`) las corres tú en tu terminal: no necesitan permisos. `perf.py` llama a `adb` por dentro, y esas llamadas no pasan por el clasificador; solo lo que el agente escribe en su terminal.
- Los comandos de la skill empiezan con `cd <ruta> && ...`: un comando compuesto se evalúa por partes. Si tu configuración pregunta por el `cd`, agrega `Bash(cd *)`.
- Con `Bash(adb *)` quedan fuera del criterio del clasificador `adb uninstall` y `pm clear`; si eso te incomoda, usa la lista acotada.

