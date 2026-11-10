# Rendimiento · Detalle de un ítem · 2026-01-15

## Siguiente paso

- _Lo escribe `perf.py siguiente --carpeta <carpeta>` (y cada comando de perf.py al terminar)._

## Ficha

| Campo | Valor |
| --- | --- |
| Alcance | Detalle de un ítem |
| Síntoma | El detalle tarda en mostrar su contenido |
| Métricas principales y objetivo | las de `principales` en plan.json, y el objetivo |
| Flujos | pasos e invalidaciones en plan.json |
| Build y ambiente | build de profiling (R8, no debuggable, profileable) · backend real o mocks |
| Dispositivo | Pixel Test · Android 14 (API 34) · Hz fijos |
| Modos | guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage |
| Stack | UI · asincronía · listas · red |
| Precondiciones | estado de la app igual en todas las fases (sesión, datos, caché) · nunca desinstalar entre fases |
| No leer | ninguna |

## Mapa del alcance

- `app/src/main/kotlin/com/example/app/detalle/DetalleScreen.kt:40`: la pantalla del detalle.

## Hipótesis

1. Carga duplicada al entrar → se confirma con `red_solapadas`.

## Métricas

<!-- perf:metricas -->
(lo escribe perf.py capturar)
<!-- /perf:metricas -->

## Hallazgos

| # | Síntoma | Evidencia (métrica + consulta + archivo:línea) | Causa raíz | Tipo |
| --- | --- | --- | --- | --- |
| H1 | Dos cargas del detalle | `red_solapadas` = 1 · `llamadas_solapadas` · `DetalleViewModel.kt:31` | Se carga en `init` y en `onResume` | bug |
| H2 | Frame largo al entrar | 48 ms en la corrida mediana · `hilo_principal_top` | — | sin veredicto estadístico |
| H3 | Jank en la lista | `jank_app_pct` 2 % | — | descartado |

## Plan de mejoras

Las mejoras viven en `mejoras` de plan.json; perf.py dibuja la tabla (propuesta en `reporte --inicial`, propuesto contra logrado en `comparar`).

<!-- perf:mejoras -->
(lo escribe perf.py)
<!-- /perf:mejoras -->

## Decisiones

- <AAAA-MM-DD: lo escribe `perf.py decidir`; agrega aquí el porqué si el usuario lo dio>

## Mejoras aplicadas

- **M1** · `archivos` · test que la fija · DoD · commit propuesto: `perf(<scope>): ...`

## Comparación

<!-- perf:comparacion -->
(lo escribe perf.py comparar)
<!-- /perf:comparacion -->

## Lectura de la comparación

- <qué dice cada métrica principal, cada regresión y cada "no comparable"; la evidencia de consultas, rotulada "sin veredicto estadístico">

## Resumen ejecutivo

<3 a 5 líneas: estado inicial → estado final con las métricas principales, la causa en una frase y qué depende del backend>

## Pendientes

- **H2** · causa sin verificar · falta una captura con muestreo de CPU

## Consumo

| Sesión | Modelo | Costo o tokens | Pasos |
| --- | --- | --- | --- |
