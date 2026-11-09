# Rendimiento · {{ALCANCE}} · {{FECHA}}

## Siguiente paso

- _Lo escribe `perf.py siguiente --carpeta <carpeta>` (y cada comando de perf.py al terminar)._

## Ficha

| Campo | Valor |
| --- | --- |
| Alcance | {{ALCANCE}} |
| Síntoma | <lo que nota el usuario, o "exploratoria"> |
| Métricas principales y objetivo | las de `principales` en plan.json, y el objetivo |
| Flujos | pasos e invalidaciones en plan.json |
| Build y ambiente | build de profiling (R8, no debuggable, profileable) · backend real o mocks |
| Dispositivo | {{DISPOSITIVO}} · Hz fijos |
| Modos | guiado o autónomo · recorrido manual, comando, arranque-frio o testigo · riguroso o triage |
| Stack | UI · asincronía · listas · red |
| Precondiciones | estado de la app igual en todas las fases (sesión, datos, caché) · nunca desinstalar entre fases |
| No leer | {{NO_LEER}} |

## Mapa del alcance

- `ruta/al/Archivo.kt:línea`: qué es, en una línea.

## Hipótesis

1. <hipótesis> → se confirma o se descarta con <métrica o consulta>.

## Métricas

<!-- perf:metricas -->
(lo escribe perf.py capturar)
<!-- /perf:metricas -->

## Hallazgos

| # | Síntoma | Evidencia (métrica + consulta + archivo:línea) | Causa raíz | Tipo |
| --- | --- | --- | --- | --- |

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

- **H3** · causa verificada · `archivo:línea` · cambio propuesto · test · métrica que lo mide · commit sugerido

## Consumo

| Sesión | Modelo | Costo o tokens | Pasos |
| --- | --- | --- | --- |
