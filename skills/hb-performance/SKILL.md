---
name: hb-performance
description: 'Investiga problemas de rendimiento en apps Android (incluido el target Android de KMP), con cualquier arquitectura y stack: arranque en frío (TTID y TTFD), jank y frames perdidos, lags, hilo principal, red (llamadas duplicadas, lentas o en cascada) y memoria. Mide antes y después con scripts, arma el diagnóstico con consultas listas sobre las trazas, propone un plan de mejoras que el usuario decide, las aplica con tests y demuestra el resultado con estadística, en sesiones cortas para gastar pocos tokens. Úsala cuando el usuario pida analizar o mejorar el rendimiento de una pantalla, un flujo, una feature, un módulo o el arranque ("la app tarda en abrir", "la pantalla X va lenta", "hay jank al hacer scroll", "llama dos veces al servicio", "analiza el rendimiento de Y", "sigue hb-performance con estado.md", "/hb-performance").'
license: MIT
compatibility: "Requiere adb, un dispositivo con Android 10 o superior (12 o superior para los frames), trace_processor de Perfetto y Python 3.8+ (solo librería estándar). Opcional: android-profiler para heap dumps; Maestro (viene con testigo) para llevar la app al punto de partida en flujos largos."
metadata:
  author: hacybeyker
  version: "0.6.0"
  category: flow
---

# hb-performance

Investiga un problema de rendimiento acotado a **una pantalla, un flujo, una feature, un módulo o el arranque**: mide el estado inicial, diagnostica, propone un plan, aplica lo que el usuario elige y demuestra el resultado con números. Sirve con cualquier arquitectura, UI o asincronía porque **mide la plataforma, no el framework**; el stack solo decide qué patrones revisar.

## Lo que cuesta son los tokens

Cada paso del agente reenvía **todo** el chat. Un chat que encadena sesiones llega a cientos de miles de tokens por paso y multiplica el costo; uno nuevo por sesión arranca con unos pocos miles. Por eso:

- Todo lo determinista lo hace `scripts/perf.py`: crear la investigación, capturar, consultar las trazas, calcular, comparar y reportar. El modelo lee resúmenes cortos e interpreta.
- Las mediciones las corre el usuario en su terminal, sin chat: cuestan cero tokens.
- Cada sesión vive en **su propio chat** y se pasa el trabajo por `estado.md`.
- Para el usuario: [prompts.md](references/prompts.md) tiene el texto para empezar, retomar o pedir algo puntual, listo para copiar.

## Reglas

1. **Alcance estricto.** Analiza y cambia solo lo indicado. Si la causa está fuera, repórtala con evidencia y pregunta.
2. **Medir antes de cambiar**, con las mismas condiciones antes y después ([medicion.md](references/medicion.md)).
3. **Evidencia o nada:** métrica + consulta o traza + `archivo:línea`. Lo que no se pueda confirmar va como **⚠ Por confirmar**.
4. **Los números con veredicto los calcula `perf.py`.** Nunca calcules medianas, porcentajes ni veredictos. Un valor que solo sale de una consulta se cita tal cual y rotulado "sin veredicto estadístico".
5. **Salidas acotadas.** Nunca vuelques al chat salidas completas (`dumpsys`, logcat, SQL, Gradle, tests, diffs). Encadena los comandos de un mismo paso (el DoD entero) en **una** invocación, con el log en `<carpeta>/logs/` y al chat solo el resumen o `grep -m1 -A20`. No leas `perf.py` ni los archivos que genera: usa `--help` y lo que imprime. Lee archivos por rangos.
6. **Una sesión por chat, y al terminar te detienes.** Tu último paso es `perf.py siguiente --carpeta <carpeta>`: escribe "Siguiente paso" en `estado.md` e imprime cada paso con lo que hace, lo que le toca al usuario y, para los chats nuevos, el modelo y el esfuerzo exactos. **Pégalo tal cual**, sin resumirlo ni reescribirlo, como último bloque de tu respuesta; antes, si hay que hacer algo en el dispositivo, dilo en una línea. No sigas con la sesión siguiente aunque te diga "sigue": explícale que en este chat cuesta varias veces más, y no le pidas que vuelva a este chat.
7. **Presupuesto de pasos** por sesión (tabla de abajo). Si se acaba, guarda el estado en `estado.md`, dilo y detente.
8. **Lo que depende de una edición corre después de ella**, nunca en paralelo.
9. **Instrumentación permanente solo en debug y profiling**, sin efecto en release. Lo temporal se quita antes del commit.
10. **Git:** no hagas commit, push, merge, rebase ni cambies de rama salvo que el usuario lo pida y `AGENTS.md` lo permita. Propón un commit por mejora, con las reglas de `hb-commit`.
11. **Datos:** la evidencia cruda se usa sin enmascarar, salvo que `AGENTS.md` pida otra cosa. Vive en una carpeta ignorada por git y nunca va a commits, PRs ni al reporte.
12. **Comandos para el usuario:** uno por paso, que empiece con `cd <ruta absoluta> && ...`. Con más de un dispositivo conectado, el serial va en cada comando (`adb -s`, `ANDROID_SERIAL=<serial> ./gradlew ...`, `--serial`) o en el plan (`nuevo --serial`). Las capturas de las fases (`capturar --fase antes|control|despues`) y `diagnostico` las corre el usuario **aunque el recorrido sea automático**: tú se las entregas como comandos, nunca las ejecutas; la única que puedes correr es la corrida de prueba de la sesión 1, avisando antes. Solo si el usuario pide el modo autónomo capturas tú.
13. **Los comandos que siguen los da `perf.py`:** cada comando imprime el paso siguiente, completo y en orden, y lo deja en `estado.md`; `perf.py siguiente` lo recalcula. Cópialos tal cual, sin inventar ni reordenar.
14. **Español neutro** (tú, no vos) en todo lo que le escribas al usuario y en `estado.md`.
15. **Rutas que no se leen** (pruebas a ciegas): la línea `No leer:` de la sección Performance de `AGENTS.md` (rutas separadas por comas o una viñeta por ruta debajo; los patrones parten de la raíz del proyecto: `**/ALCANCE-*` cubre cualquier carpeta), `no_leer` de `plan.json` y la fila "No leer" de `estado.md` son una sola lista, y vale en todas las sesiones. No leas, no busques (grep, find, glob) ni cites esas rutas, ni para "confirmar" algo; si el trabajo las necesita, dilo y pregunta. `perf.py` también las omite.

## Sesiones

| Paso | Quién | Lee | Hace | Termina con | Pasos máx. |
| --- | --- | --- | --- | --- | --- |
| 0 · Setup, una vez por proyecto | Agente | [setup.md](references/setup.md) | Variante de profiling (la que el proyecto ya tenga, o `profiling`), `perf.py instrumentar` (genera también el cableado), los fragmentos que imprime, DoD en un comando y `perf.py humo` | Aprobación del diff | 40 |
| 1 · Ficha y plan | Agente; con receta, `perf.py nuevo` sin chat | [ficha.md](references/ficha.md) | Preguntas fijas, `plan.json` (marcas, ventana, métricas), `estado.md` y corrida de prueba | Aprobación de ficha y plan | 15 |
| Medición antes y control | Usuario, sin chat | [medicion.md](references/medicion.md) | `perf.py capturar` y `perf.py diagnostico` | — | — |
| 2 · Diagnóstico | Agente | [diagnostico.md](references/diagnostico.md) | Lee `diagnostico.md` y el código; hallazgos, plan de mejoras y reporte inicial | El comando de la decisión | 25 |
| Decisión | Usuario, sin chat | — | `perf.py decidir`: aprueba, descarta o deja pendiente cada mejora | — | — |
| 3 · Mejora | Agente, un chat por mejora | [mejoras.md](references/mejoras.md) | Una mejora, su test y el DoD | Commit propuesto y `perf.py decidir --aplicada` | 30 |
| Medición después | Usuario, sin chat | [medicion.md](references/medicion.md) | `instalar` del plan y `perf.py capturar --fase despues` | — | — |
| 4 · Cierre | Agente | [cierre.md](references/cierre.md) | `perf.py comparar`, lectura, resumen ejecutivo y reporte final | Entrega | 10 |

El costo de cada sesión lo anota el usuario desde la terminal con `perf.py consumo` (el comando sale en "Siguiente paso"); no se lo pidas en el chat.

- **Retomar:** si te pasan un `estado.md`, léelo y sigue la sesión de "Siguiente paso", y solo esa; si no está escrito, `perf.py siguiente --carpeta <carpeta>` lo calcula. Sin `estado.md`: la 0 si `AGENTS.md` no dice que el setup está listo; si no, la 1.
- **Recetas:** el arranque en frío no necesita la sesión 1. `perf.py nuevo --receta arranque-frio` arma `plan.json` y `estado.md` listos para medir (TTID, TTFD y el hilo principal).
- **Modos:** *guiado* por defecto: el agente corre en su terminal lo que no mide (`perf.py` salvo `capturar` y `diagnostico`, Gradle, DoD, instalar) y **el usuario corre las mediciones desde su terminal, también cuando el recorrido es automático** (así ve correr el dispositivo y no paga tokens por esperar). *Autónomo*, solo si el usuario lo pide: el agente también captura, con el modelo más económico y solo con recorrido automático (`arranque-frio` o un comando).
- **Profundidad:** *riguroso* por defecto (antes, control y después, 10 corridas con recorrido automático). *Triage* (`profundidad: triage` en el plan, `nuevo --triage`): 3 corridas de antes, sin control, y termina en el diagnóstico y el reporte inicial; los hallazgos llevan "⚠ sin línea base".
- **Modelo y costo:** [modelos.md](references/modelos.md). Los nombres de los modelos que imprime `siguiente` salen de `modelos` en `plan.json` (niveles economico, intermedio, diagnostico y alto; por defecto Haiku, Sonnet, Sonnet y Opus); con otra herramienta, el usuario los cambia una vez.

## Herramientas

- `python3 -I <carpeta-de-la-skill>/scripts/perf.py <comando>`: `instrumentar`, `humo`, `nuevo`, `capturar`, `diagnostico`, `consulta`, `resumen`, `comparar`, `har`, `reporte`, `decidir`, `siguiente` y `consumo` (cada uno con `--help`). Usa `adb` y `trace_processor`.
- Permisos para auto mode (el clasificador puede denegar secuencias de `adb`): [prompts.md](references/prompts.md) · Permisos recomendados; los agrega el usuario, la skill no toca su configuración.
- Otras skills, por intención y sin depender de sus archivos: `android-profiler` (heap dumps y fugas), `jetpack-compose-performance`, `anr-audit-and-fix` y `r8-analyzer`.

## Checklist

- [ ] Cada sesión en su chat, con `estado.md` y solo su referencia; se detuvo al terminar y pegó tal cual la salida de `perf.py siguiente`.
- [ ] Setup listo y registrado en `AGENTS.md`; prueba de humo correcta.
- [ ] Métricas principales fijadas antes de medir, al menos una de punta a punta (TTFD o una métrica de usuario hasta una marca de contenido visible); en flujos que no son el arranque, la ventana del flujo en el plan.
- [ ] Corrida de prueba antes de medir; al menos 5 corridas válidas por fase (10 con recorrido automático). Si `capturar` avisa de emulador o de render por software, los frames no son principales ni valen para decidir.
- [ ] Hallazgos con evidencia; mejoras en `plan.json` con su métrica y lo esperado; decisión del usuario registrada con `perf.py decidir`.
- [ ] Una mejora por chat y por commit propuesto, con su test y el DoD en verde.
- [ ] Veredictos de `perf.py`, lectura de la comparación escrita; e2e marcado como dependiente del backend.
- [ ] Nada de evidencia cruda en commits, PRs ni en el reporte.
