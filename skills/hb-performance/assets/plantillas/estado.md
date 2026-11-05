# Rendimiento · <alcance> · <AAAA-MM-DD>

## Siguiente paso

- **Sesión:** <1 · ficha | medición antes | 2 · diagnóstico | 3 · mejoras | medición después | 4 · cierre>
- **Qué hacer:** <una o dos líneas>
- **Comando o texto para el chat nuevo:** <el comando de perf.py, o "Sigue hb-performance con <ruta>/estado.md">
- **Modelo sugerido:** <intermedio · razonamiento medio>

## Ficha

| Campo | Valor |
| --- | --- |
| Alcance | |
| Síntoma | |
| Métricas principales y objetivo | (las de `principales` en plan.json) |
| Flujos | (pasos e invalidaciones en plan.json) |
| Build y ambiente | variante, debuggable o profileable, R8, ambiente |
| Dispositivo | modelo · Android · Hz |
| Modos | guiado o autónomo · manual, testigo o Macrobenchmark · riguroso o triage |
| Stack | UI · asincronía · listas · red |
| Precondiciones | sesión del ambiente (¿expira?), datos de prueba necesarios |

## Mapa del alcance

- `ruta/al/Archivo.kt`: qué es, en una línea.

## Hipótesis

1. <hipótesis> → se confirma o descarta con <métrica>.

## Métricas

<!-- perf:metricas -->
(lo escribe perf.py)
<!-- /perf:metricas -->

## Hallazgos

| # | Síntoma | Evidencia (métrica + traza + archivo:línea) | Causa raíz | Mejora | Impacto | Riesgo | Esfuerzo | Tipo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Decisiones

- <qué mejoras se aplican, cuáles no y por qué>

## Mejoras aplicadas

- **H1** · `archivos` · test que la fija · commit propuesto: `perf(<scope>): ...`

## Comparación

<!-- perf:comparacion -->
(lo escribe perf.py)
<!-- /perf:comparacion -->

## Resumen ejecutivo

<3 a 5 líneas: estado inicial → estado final con las métricas principales; qué depende del backend>

## Pendientes

- **H3** · causa verificada · `archivo:línea` · cambio propuesto · test · métrica que lo mide · commit sugerido
