---
name: hb-performance
description: 'Investiga problemas de rendimiento en apps Android (incluido el target Android de KMP), con cualquier arquitectura y stack: jank y frames perdidos, lags, hilo principal, red (llamadas duplicadas, lentas o en cascada), memoria y fugas, y arranque. Mide antes y después con scripts, diagnostica con trazas y código, aplica mejoras con tests y demuestra la mejora con estadística, en sesiones cortas para gastar pocos tokens. Úsala cuando el usuario pida analizar o mejorar el rendimiento de una pantalla, un flujo, una feature o un módulo ("la pantalla X va lenta", "hay jank al hacer scroll", "llama dos veces al servicio", "analiza el rendimiento de Y", "sigue hb-performance con estado.md", "/hb-performance").'
license: MIT
compatibility: "Requiere adb, un dispositivo con Android 10 o superior (12 o superior para los frames), trace_processor de Perfetto y Python 3.8+ (solo librería estándar). Usa la skill oficial android-profiler en el diagnóstico. Opcional: testigo para automatizar los recorridos."
metadata:
  author: hacybeyker
  version: "0.1.0"
  category: flow
---

# hb-performance

Investiga un problema de rendimiento acotado a **una pantalla, un flujo, una feature o un módulo**: mide el estado inicial, diagnostica, aplica mejoras y demuestra el resultado con números. Sirve con cualquier arquitectura, UI o asincronía porque **mide la plataforma, no el framework**; el stack solo decide qué patrones revisar.

**Lo que cuesta son los tokens:** cada paso reenvía todo el contexto. Por eso la investigación va en **sesiones cortas** que se pasan el trabajo por `estado.md`, y todo lo determinista (capturar, consultar, calcular, comparar, reportar) lo hace `scripts/perf.py`. El modelo lee resúmenes e interpreta.

## Reglas

1. **Alcance estricto.** Analiza y cambia solo lo indicado. Si la causa está fuera, repórtala con evidencia y pregunta.
2. **Medir antes de cambiar**, con las mismas condiciones antes y después ([medicion.md](references/medicion.md)).
3. **Evidencia o nada:** métrica + traza + `archivo:línea`. Lo que no se pueda confirmar va como **⚠ Por confirmar**.
4. **Los números los calcula `perf.py`.** Nunca calcules ni transcribas medianas, porcentajes o veredictos.
5. **Salidas acotadas.** Nunca vuelques al contexto salidas completas (`dumpsys`, SQL, Gradle, tests). Gradle con `-q`, tests solo del módulo, logs a `<carpeta>/logs/` y al contexto solo el resumen. Lee archivos por rangos y con `grep`.
6. **Lo que depende de una edición corre después de ella**, nunca en paralelo.
7. **Instrumentación permanente solo en debug y profiling**, sin efecto en release. Las secciones temporales se quitan antes del commit.
8. **Git:** no hagas commit, push, merge, rebase ni cambies de rama salvo que el usuario lo pida y `AGENTS.md` lo permita. Propón un commit por mejora, con las reglas de `hb-commit`.
9. **Datos:** la evidencia cruda se usa sin enmascarar, salvo que `## Rendimiento` pida otra cosa. Vive en una carpeta ignorada por git y nunca va a commits, PRs ni al reporte.
10. **Comandos para el usuario:** uno por paso, que empiece con `cd <ruta absoluta> && ...`.

## Sesiones

Cada sesión es **un chat nuevo** que lee `estado.md` (si existe) y **solo** la referencia de su sesión. Al terminar, actualiza "Siguiente paso" en `estado.md` con el comando o el texto para el chat siguiente y el modelo sugerido ([modelos.md](references/modelos.md)).

| Sesión | Lee | Hace | Aprobación |
| --- | --- | --- | --- |
| 0 · Setup, una vez por proyecto | [setup.md](references/setup.md) | Build de profiling, `perf.py instrumentar`, cableado y prueba de humo | El diff del setup |
| 1 · Ficha y plan | [ficha.md](references/ficha.md) | Contexto, stack, mapa, hipótesis, `plan.json`, `estado.md` y corrida de prueba | Ficha y plan, juntos |
| Medición antes | [medicion.md](references/medicion.md), solo si la corre el agente | `perf.py capturar --fase antes` | — |
| 2 · Diagnóstico | [diagnostico.md](references/diagnostico.md) | Métricas, código y consultas acotadas; `android-profiler` solo si hace falta | Hallazgos y mejoras elegidas, juntos |
| 3 · Mejoras | [mejoras.md](references/mejoras.md) | Una mejora a la vez, con su test y el DoD | Cada commit propuesto |
| Medición después | [medicion.md](references/medicion.md) | `perf.py capturar --fase despues` | — |
| 4 · Cierre | [cierre.md](references/cierre.md) | `perf.py comparar` y `reporte`; el modelo redacta el resumen ejecutivo | — |

- **Retomar:** si te pasan un `estado.md`, léelo y sigue la sesión de "Siguiente paso". Sin `estado.md`, empieza por la 1; por la 0 si `## Rendimiento` del `AGENTS.md` no dice que el setup está listo.
- **Modos:** *guiado* por defecto (el usuario corre los comandos y las mediciones no gastan tokens) o *autónomo* (el agente corre `perf.py`, con el modelo más económico). El recorrido es manual (Enter entre corridas), con testigo o con Macrobenchmark.
- **Profundidad:** *riguroso* por defecto. *Triage*: sesión 1 con una corrida de prueba y directo al diagnóstico; los hallazgos llevan "⚠ sin línea base".

## Herramientas

- `python3 -I <carpeta-de-la-skill>/scripts/perf.py <comando>`: `capturar`, `consulta`, `resumen`, `comparar`, `har`, `reporte` e `instrumentar` (cada uno con `--help`). Usa `adb` y `trace_processor`.
- Otras skills, por intención y sin depender de sus archivos: `android-profiler` (diagnóstico profundo: heap dumps, CPU, triage de una traza), `jetpack-compose-performance`, `anr-audit-and-fix` y `r8-analyzer`.

## Checklist

- [ ] Cada sesión en un chat nuevo, con `estado.md` y solo su referencia.
- [ ] Setup listo y registrado en `## Rendimiento`; prueba de humo correcta.
- [ ] Ficha y plan aprobados juntos, con las métricas principales fijadas antes de medir.
- [ ] Corrida de prueba antes de medir; al menos 5 corridas válidas por fase.
- [ ] Hallazgos con evidencia, bugs separados de lo intencional; pendientes con receta.
- [ ] Una mejora por commit propuesto, con su test y el DoD en verde.
- [ ] Veredictos de `perf.py`; e2e marcado como dependiente del backend.
- [ ] Nada de evidencia cruda en commits, PRs ni en el reporte.
