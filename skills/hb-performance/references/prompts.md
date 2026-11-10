# Prompts listos para copiar

Para el usuario, no para el agente. Cada caso trae dónde va (un chat nuevo, con el **nivel de modelo y el esfuerzo** que conviene, o la terminal) y, en un bloque aparte, el texto para pegar: **copia solo el bloque**; lo que está fuera es la explicación. Las partes entre `<>` se completan.

- **Niveles de modelo:** económico, intermedio, diagnóstico y alto son los de `modelos` en `plan.json`: por defecto Haiku 5.5, Sonnet 5.5, Sonnet 5.5 (el diagnóstico toma el intermedio si el plan no lo nombra) y Opus 5.5. `perf.py siguiente` imprime los de tu plan; con otra herramienta, pones sus equivalentes una vez en el plan.
- **El mismo texto sirve para empezar la primera vez y las siguientes.** La skill elige la sesión según el estado del proyecto: sin setup hace el setup (sesión 0); con el setup listo, la ficha y el plan (sesión 1); con un `estado.md`, la que diga su "Siguiente paso". No hace falta decirle cuál: el agente lo dice en su primera línea, con el motivo (`Sesión 1 · ficha (setup listo en AGENTS.md)`).
- **Lo que sigue a cada sesión no hace falta pedirlo:** cada comando de `perf.py` y cada sesión terminan imprimiendo el paso siguiente, listo para copiar, y lo dejan en "Siguiente paso" de `estado.md`.
- **El costo de un chat** es lo que muestre tu herramienta al cerrarlo (`/cost` en Claude Code, los créditos del chat en Copilot).

## Empezar

### Una pantalla o un flujo (la primera vez en el proyecto, o con el setup listo)

**Dónde:** chat nuevo · Intermedio · medio

```text
Usa hb-performance: quiero analizar el rendimiento de <pantalla o flujo: de dónde a dónde y qué debe verse al final; qué se nota: "tarda", "jank al hacer scroll">. Dispositivo <serial>.
```

Sin build de profiling, el agente hace el setup (sesión 0) y te deja el comando de la prueba de humo; esa prueba termina con el texto del chat siguiente, con tu flujo ya escrito. Con el setup listo, hace la sesión 1: te pregunta todo en un solo mensaje y arma el plan.

### Flujo largo (login, avisos y varias pantallas antes de lo que se mide)

**Dónde:** chat nuevo · Intermedio · medio

```text
Usa hb-performance: medir <tramo: de qué lista a qué detalle>. Para llegar ahí hay que <login, aceptar términos, omitir huella, ir al tab X>: usa un flow de Maestro en preparar y adb para el tramo medido. Dispositivo <serial>.
```

Sesión 1 con el patrón de flujos largos. Si el flujo necesita credenciales, van en variables de entorno: expórtalas en la terminal **antes de abrir el agente** (solo ve las de la terminal desde la que se abrió) y, después, en la terminal donde midas.

### Arranque en frío (setup listo)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py nuevo --receta arranque-frio --paquete <applicationId> --serial <serial> --carpeta reports/perf/arranque-frio/<AAAA-MM-DD> --instalar "<comando que instala el build de profiling>"
```

Arma el plan sin sesión 1 e imprime los comandos para medir. Agrega `--red` si la primera pantalla carga de la red.

### Solo el diagnóstico, sin cambiar código (triage)

**Dónde:** chat nuevo · Intermedio · medio

```text
Usa hb-performance en modo triage: diagnostica <flujo> con 3 corridas, sin control ni mejoras. Dispositivo <serial>.
```

Termina en el reporte inicial.

### Prueba de humo del setup

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py humo --paquete <applicationId> --serial <serial> --instalar "<comando de instalación>"
```

## Seguir

### Retomar donde quedó (cualquier sesión)

**Dónde:** chat nuevo, con el modelo y el esfuerzo que diga "Siguiente paso"

```text
Sigue hb-performance con <ruta absoluta>/estado.md
```

### Retomar un chat que se cortó a la mitad

**Dónde:** terminal, con el comando de tu herramienta que reabre una sesión eligiéndola de una lista

```bash
claude --resume
```

Ese es el de Claude Code; en Copilot CLI, `copilot --resume`. Evita el que continúa "la última" sin preguntar: puede tomar la de otra terminal. Si la sesión ya había terminado, no la reabras: usa el caso anterior en un chat nuevo.

### No sé cuál es el paso

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py siguiente --carpeta <carpeta>
```

Recalcula el paso y lo imprime.

### Aprobar el plan y seguir (al final de la sesión 1)

**Dónde:** el mismo chat de la sesión 1

```text
Apruebo la ficha y el plan.
```

Te deja los comandos de la medición.

### Decidir qué mejoras se aplican (después de la sesión 2)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py decidir --carpeta <carpeta> --aprobar M1,M3 --descartar M2 --pendiente -
```

Imprime el chat de la sesión 3. Las mejoras a prueba se aprueban igual.

### Aplicar una mejora aprobada

**Dónde:** chat nuevo · Intermedio · medio

```text
Sigue hb-performance con <ruta>/estado.md: sesión 3, aplica <id>
```

### Cerrar la investigación (medición después lista)

**Dónde:** chat nuevo · Económico · bajo

```text
Sigue hb-performance con <ruta>/estado.md
```

### Cerrar sin aplicar mejoras (no hubo, o quedaron descartadas o pendientes)

**Dónde:** chat nuevo · Económico · bajo

```text
Sigue hb-performance con <ruta>/estado.md: cierra la investigación sin fase después
```

### Anotar el costo de un chat

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py consumo --carpeta <carpeta> --sesion "<2 · diagnóstico>" --costo "<lo que muestre tu herramienta: 0.80 USD, 12 créditos>" --modelo "<modelo del chat>" --pasos <21>
```

## Pedidos puntuales

### Volver a medir una fase (cambió el build, hubo ruido)

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --fase <antes|control|despues> --corridas <5|10> --rehacer
```

Con varios flujos, `--flujo <nombre>`: solo se rehace ese.

### Explicar un resultado

**Dónde:** chat nuevo · Intermedio · medio

```text
Con hb-performance, lee <ruta>/comparacion.md y <ruta>/estado.md y explícame por qué <métrica> dio <veredicto>. No cambies nada.
```

### Mejorar el reporte

**Dónde:** chat nuevo · Económico · bajo

```text
Con hb-performance, mejora el resumen ejecutivo y la lectura de la comparación en <ruta>/estado.md (<qué falta o qué sobra>) y vuelve a generar el reporte con perf.py reporte --carpeta <carpeta> --html.
```

### Regenerar el reporte sin tocar el texto

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py reporte --carpeta <carpeta> --html
```

### Agregar una métrica, un tramo o una marca

**Dónde:** chat nuevo · Intermedio · medio

```text
Con hb-performance, agrega al plan de <carpeta> una métrica de usuario (o un tramo en segmentos) desde <marca> hasta <marca> (familia <app|e2e>) y dime si hace falta medir de nuevo.
```

### Una pregunta sobre una traza

**Dónde:** chat nuevo · Diagnóstico · alto

```text
Con hb-performance, en la traza <ruta>/antes/<flujo>_<n>.perfetto-trace.gz responde: <pregunta>. Usa perf.py consulta con LIMIT.
```

### Actualizar la instrumentación tras actualizar la skill

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/perf.py instrumentar --modulo <el módulo que genera el APK, normalmente app> --paquete <paquete>.perf --actualizar
```

Después, el formateador y el DoD del proyecto.

### Investigar algo que quedó en "Pendientes"

**Dónde:** chat nuevo · Intermedio · medio

```text
Usa hb-performance: nueva investigación sobre <pendiente, con el H# del estado.md anterior en <ruta>>. Dispositivo <serial>.
```

## Reglas que te ahorran dinero

- **Un chat por sesión.** Si el agente dice que terminó, abre otro: seguir en el mismo cuesta varias veces más por paso.
- **Si el paso siguiente es un comando, no abras un chat**: un chat que solo lee `estado.md` para decírtelo cuesta unos 0,2 USD.
- Las mediciones y la decisión van en tu terminal: cero tokens.
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

