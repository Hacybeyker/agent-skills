---
name: hb-performance
description: 'Investiga problemas de rendimiento en apps Android (incluido el target Android de KMP), con cualquier arquitectura y stack: arranque en frío (TTID y TTFD), jank y frames perdidos, lags, hilo principal, red (llamadas duplicadas, lentas o en cascada) y memoria. Mide antes y después con scripts, arma el diagnóstico con consultas listas sobre las trazas, propone un plan de mejoras que el usuario decide, las aplica con tests y demuestra el resultado con estadística, en sesiones cortas para gastar pocos tokens. Úsala cuando el usuario pida analizar o mejorar el rendimiento de una pantalla, un flujo, una feature, un módulo o el arranque ("la app tarda en abrir", "la pantalla X va lenta", "hay jank al hacer scroll", "llama dos veces al servicio", "analiza el rendimiento de Y", "sigue hb-performance con estado.md", "/hb-performance").'
license: MIT
compatibility: "Requiere adb, un dispositivo con Android 10 o superior (12 o superior para los frames), trace_processor de Perfetto y Python 3.8+ (solo librería estándar). Opcional: android-profiler para heap dumps, testigo para automatizar recorridos."
metadata:
  author: hacybeyker
  version: "0.2.0"
  category: flow
---

# hb-performance

Investiga un problema de rendimiento acotado a **una pantalla, un flujo, una feature, un módulo o el arranque**: mide el estado inicial, diagnostica, propone un plan, aplica lo que el usuario elige y demuestra el resultado con números. Sirve con cualquier arquitectura, UI o asincronía porque **mide la plataforma, no el framework**; el stack solo decide qué patrones revisar.

## Lo que cuesta son los tokens

Cada paso del agente reenvía **todo** el chat. Un chat que encadena sesiones llega a cientos de miles de tokens por paso y multiplica el costo; uno nuevo por sesión arranca con unos pocos miles. Por eso:

- Todo lo determinista lo hace `scripts/perf.py`: crear la investigación, capturar, consultar las trazas, calcular, comparar y reportar. El modelo lee resúmenes cortos e interpreta.
- Las mediciones las corre el usuario en su terminal, sin chat: cuestan cero tokens.
- Cada sesión vive en **su propio chat** y se pasa el trabajo por `estado.md`.

## Reglas

1. **Alcance estricto.** Analiza y cambia solo lo indicado. Si la causa está fuera, repórtala con evidencia y pregunta.
2. **Medir antes de cambiar**, con las mismas condiciones antes y después ([medicion.md](references/medicion.md)).
3. **Evidencia o nada:** métrica + consulta o traza + `archivo:línea`. Lo que no se pueda confirmar va como **⚠ Por confirmar**.
4. **Los números con veredicto los calcula `perf.py`.** Nunca calcules medianas, porcentajes ni veredictos. Un valor que solo sale de una consulta se cita tal cual y rotulado "sin veredicto estadístico".
5. **Salidas acotadas.** Nunca vuelques al chat salidas completas (`dumpsys`, logcat, SQL, Gradle, tests, diffs). Logs a `<carpeta>/logs/` y al chat solo el resumen o `grep -m1 -A20`. No leas `perf.py`: usa `--help`. Lee archivos por rangos.
6. **Una sesión por chat, y al terminar te detienes.** Actualiza "Siguiente paso" en `estado.md`, da al usuario el texto para el chat nuevo y no sigas con la sesión siguiente aunque te diga "sigue": explícale que en este chat cuesta varias veces más.
7. **Presupuesto de pasos** por sesión (tabla de abajo). Si se acaba, guarda el estado en `estado.md`, dilo y detente.
8. **Lo que depende de una edición corre después de ella**, nunca en paralelo.
9. **Instrumentación permanente solo en debug y profiling**, sin efecto en release. Lo temporal se quita antes del commit.
10. **Git:** no hagas commit, push, merge, rebase ni cambies de rama salvo que el usuario lo pida y `AGENTS.md` lo permita. Propón un commit por mejora, con las reglas de `hb-commit`.
11. **Datos:** la evidencia cruda se usa sin enmascarar, salvo que `AGENTS.md` pida otra cosa. Vive en una carpeta ignorada por git y nunca va a commits, PRs ni al reporte.
12. **Comandos para el usuario:** uno por paso, que empiece con `cd <ruta absoluta> && ...`.

## Sesiones

| Paso | Quién | Lee | Hace | Termina con | Pasos máx. |
| --- | --- | --- | --- | --- | --- |
| 0 · Setup, una vez por proyecto | Agente | [setup.md](references/setup.md) | Build de profiling, `perf.py instrumentar`, cableado, `reportFullyDrawn` y prueba de humo | Aprobación del diff | 40 |
| 1 · Ficha y plan | Agente; con receta, `perf.py nuevo` sin chat | [ficha.md](references/ficha.md) | `plan.json`, `estado.md` y corrida de prueba | Aprobación de ficha y plan | 15 |
| Medición antes y control | Usuario, sin chat | [medicion.md](references/medicion.md) | `perf.py capturar` y `perf.py diagnostico` | — | — |
| 2 · Diagnóstico | Agente | [diagnostico.md](references/diagnostico.md) | Lee `diagnostico.md` y el código; hallazgos, plan de mejoras y reporte inicial | **Decisión del usuario:** qué mejoras se aplican | 25 |
| 3 · Mejora | Agente, un chat por mejora | [mejoras.md](references/mejoras.md) | Una mejora, su test y el DoD | Commit propuesto | 30 |
| Medición después | Usuario, sin chat | [medicion.md](references/medicion.md) | `perf.py capturar --fase despues` | — | — |
| 4 · Cierre | Agente | [cierre.md](references/cierre.md) | `perf.py comparar`, lectura, resumen ejecutivo y reporte final | Entrega | 10 |

- **Retomar:** si te pasan un `estado.md`, léelo y sigue la sesión de "Siguiente paso", y solo esa. Sin `estado.md`: la 0 si `AGENTS.md` no dice que el setup está listo; si no, la 1.
- **Recetas:** el arranque en frío no necesita la sesión 1. `perf.py nuevo --receta arranque-frio` arma `plan.json` y `estado.md` listos para medir (TTID, TTFD y el hilo principal).
- **Modos:** *guiado* por defecto: el agente corre en su terminal todo lo que no necesita el dispositivo en la mano (`perf.py` salvo `capturar`, Gradle, DoD, instalar) y el usuario corre las capturas. *Autónomo*: el agente también captura, con el modelo más económico y solo si el recorrido es automático (`arranque-frio`, un comando o testigo).
- **Profundidad:** *riguroso* por defecto (antes, control y después, 10 corridas con recorrido automático). *Triage*: una corrida de prueba y directo al diagnóstico; los hallazgos llevan "⚠ sin línea base".
- **Modelo y costo:** [modelos.md](references/modelos.md). Al cerrar cada sesión, pide al usuario el costo (`/cost` o lo que muestre su herramienta) y anótalo en "Consumo".

## Herramientas

- `python3 -I <carpeta-de-la-skill>/scripts/perf.py <comando>`: `nuevo`, `capturar`, `diagnostico`, `consulta`, `resumen`, `comparar`, `har`, `reporte` e `instrumentar` (cada uno con `--help`). Usa `adb` y `trace_processor`.
- Otras skills, por intención y sin depender de sus archivos: `android-profiler` (heap dumps y fugas), `jetpack-compose-performance`, `anr-audit-and-fix` y `r8-analyzer`.

## Checklist

- [ ] Cada sesión en su chat, con `estado.md` y solo su referencia; se detuvo al terminar.
- [ ] Setup listo y registrado en `AGENTS.md`; prueba de humo correcta.
- [ ] Métricas principales fijadas antes de medir, al menos una de punta a punta (TTFD o una métrica de usuario).
- [ ] Corrida de prueba antes de medir; al menos 5 corridas válidas por fase (10 con recorrido automático).
- [ ] Hallazgos con evidencia; mejoras en `plan.json` con su métrica y lo esperado; decisión del usuario registrada.
- [ ] Una mejora por chat y por commit propuesto, con su test y el DoD en verde.
- [ ] Veredictos de `perf.py`, lectura de la comparación escrita; e2e marcado como dependiente del backend.
- [ ] Nada de evidencia cruda en commits, PRs ni en el reporte.
