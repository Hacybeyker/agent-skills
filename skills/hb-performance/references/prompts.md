# Prompts listos para copiar

Para el usuario, no para el agente. Cada caso trae el **modelo y el esfuerzo** con los que conviene abrir el chat (nombres de Claude Code; con otra herramienta, sus equivalentes) y el texto para pegar. Las partes entre `<>` se completan. Lo que sigue a cada sesión no hace falta pedirlo: **cada comando de `perf.py` y cada sesión terminan imprimiendo el paso siguiente**, listo para copiar, y lo dejan en "Siguiente paso" de `estado.md`.

## Empezar

| Caso | Chat | Texto |
| --- | --- | --- |
| **Primera vez en el proyecto** (sin build de profiling) | Sonnet 5 · medio | `Usa hb-performance: quiero analizar el rendimiento de <pantalla o flujo, y qué se nota: "tarda", "jank al hacer scroll">. Dispositivo <serial>.` → el agente hace el setup (sesión 0) y te deja el comando de la prueba de humo |
| **Arranque en frío** (setup listo) | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py nuevo --receta arranque-frio --paquete <applicationId> --serial <serial> --carpeta reports/perf/arranque-frio/<AAAA-MM-DD> --instalar "<comando que instala el build de profiling>"` (`--red` si la primera pantalla carga de la red) → imprime los comandos para medir |
| **Otra pantalla o flujo** (setup listo) | Sonnet 5 · medio | `Usa hb-performance: medir <flujo: de dónde a dónde, qué debe verse al final>. Dispositivo <serial>.` → sesión 1: te hace las preguntas en un solo mensaje y arma el plan |
| **Flujo largo** (login, avisos y varias pantallas antes de lo que se mide) | Sonnet 5 · medio | `Usa hb-performance: medir <tramo: de qué lista a qué detalle>. Para llegar ahí hay que <login, aceptar términos, omitir huella, ir al tab X>: usa un flow de Maestro en preparar y adb para el tramo medido. Dispositivo <serial>.` → sesión 1 con el patrón de flujos largos |
| **Solo el diagnóstico, sin cambiar código** (triage) | Sonnet 5 · medio | `Usa hb-performance en modo triage: diagnostica <flujo> con 3 corridas, sin control ni mejoras. Dispositivo <serial>.` → termina en el reporte inicial |
| **Prueba de humo del setup** | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py humo --paquete <applicationId> --serial <serial> --instalar "<comando de instalación>"` |

## Seguir

| Caso | Chat | Texto |
| --- | --- | --- |
| **Retomar donde quedó** (cualquier sesión) | El que diga "Siguiente paso" | `Sigue hb-performance con <ruta absoluta>/estado.md` |
| **No sé cuál es el paso** | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py siguiente --carpeta <carpeta>` → recalcula el paso y lo imprime |
| **Aprobar el plan y seguir** (al final de la sesión 1) | El mismo chat | `Apruebo la ficha y el plan.` → te deja los comandos de la medición |
| **Decidir qué mejoras se aplican** (después de la sesión 2) | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py decidir --carpeta <carpeta> --aprobar M1,M3 --descartar M2 --pendiente -` → imprime el chat de la sesión 3 |
| **Aplicar una mejora aprobada** | Sonnet 5 · medio | `Sigue hb-performance con <ruta>/estado.md: sesión 3, aplica <id>` |
| **Cerrar la investigación** (medición después lista) | Haiku 5.5 · bajo | `Sigue hb-performance con <ruta>/estado.md` |
| **Cerrar sin aplicar mejoras** (todas descartadas o pendientes) | Haiku 5.5 · bajo | `Sigue hb-performance con <ruta>/estado.md: cierra la investigación sin fase después` |
| **Anotar el costo de un chat** | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py consumo --carpeta <carpeta> --sesion "<2 · diagnóstico>" --costo "<0.80 USD>" --modelo "<Sonnet 5>" --pasos <21>` |

## Pedidos puntuales

| Caso | Chat | Texto |
| --- | --- | --- |
| **Volver a medir una fase** (cambió el build, hubo ruido) | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --fase <antes\|control\|despues> --corridas <5\|10> --rehacer` |
| **Explicar un resultado** | Sonnet 5 · medio | `Con hb-performance, lee <ruta>/comparacion.md y <ruta>/estado.md y explícame por qué <métrica> dio <veredicto>. No cambies nada.` |
| **Mejorar el reporte** | Haiku 5.5 · bajo | `Con hb-performance, mejora el resumen ejecutivo y la lectura de la comparación en <ruta>/estado.md (<qué falta o qué sobra>) y vuelve a generar el reporte con perf.py reporte --carpeta <carpeta> --html.` |
| **Regenerar el reporte** sin tocar el texto | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py reporte --carpeta <carpeta> --html` |
| **Agregar una métrica o una marca** | Sonnet 5 · medio | `Con hb-performance, agrega al plan de <carpeta> una métrica de usuario desde <marca> hasta <marca> (familia <app\|e2e>) y dime si hace falta medir de nuevo.` |
| **Una pregunta sobre una traza** | Sonnet 5 · alto | `Con hb-performance, en la traza <ruta>/antes/<flujo>_<n>.perfetto-trace.gz responde: <pregunta>. Usa perf.py consulta con LIMIT.` |
| **Actualizar la instrumentación** tras actualizar la skill | Sin chat | `cd <raíz> && python3 -I <skill>/scripts/perf.py instrumentar --modulo <app> --paquete <paquete>.perf --actualizar` y después el formateador y el DoD |
| **Investigar algo que quedó en "Pendientes"** | Sonnet 5 · medio | `Usa hb-performance: nueva investigación sobre <pendiente, con el H# del estado.md anterior en <ruta>>. Dispositivo <serial>.` |

## Reglas que te ahorran dinero

- **Un chat por sesión.** Si el agente dice que terminó, abre otro: seguir en el mismo cuesta varias veces más por paso.
- **Si el paso siguiente es un comando, no abras un chat**: un chat que solo lee `estado.md` para decírtelo cuesta unos 0,2 USD.
- Las mediciones y la decisión van en tu terminal: cero tokens.
- Si el agente te pide el costo o que vuelvas a su chat, no hace falta: `perf.py consumo` lo anota desde la terminal.
