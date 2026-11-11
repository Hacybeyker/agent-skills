# Rendimiento · {{ALCANCE}} · {{FECHA}}

## Siguiente paso

- _Lo escribe `perf.py siguiente --carpeta <carpeta>` (y cada comando de perf.py al terminar)._

## Ficha

| Campo | Valor |
| --- | --- |
| Alcance | {{ALCANCE}} |
| Síntoma | <lo que nota el usuario, o "exploratoria"> |
| Métricas principales y objetivo | <las de `principales` en plan.json, y el objetivo de cada una> |
| Flujos | pasos e invalidaciones en plan.json |
| Build y ambiente | <variante medida (R8, no depurable, profileable) · backend real o mocks> |
| Dispositivo | {{DISPOSITIVO}} |
| Modos | <guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage> |
| Stack | <UI · asincronía · listas · red> |
| Precondiciones | estado de la app igual en todas las fases (sesión, datos, caché) · nunca desinstalar ni borrar datos entre fases |
| No leer | {{NO_LEER}} |

## Cómo se recorre

<!-- perf:recorrido -->
(lo escribe perf.py: `preparar` y `recorrido` de cada flujo, y el comando para verlos correr a mano)
<!-- /perf:recorrido -->

## Cambios temporales por revertir

Marcas o código puestos solo para esta investigación (por ejemplo, una marca con `android.os.Trace` en un módulo que no ve `PerfHooks`) y las ediciones de cableado en código de `main` que no se van a commitear (el gancho de red donde se arma el cliente HTTP, por ejemplo). Se revierten antes de proponer un commit y, a más tardar, en el cierre.

| Archivo | Repo o módulo | Qué es | Altera | ¿Revertido? |
| --- | --- | --- | --- | --- |

"Altera": las métricas que el cambio afecta si modifica el comportamiento de la app mientras se mide (una espera, una condición, otro orden de llamadas); `—` si solo emite una marca. `perf.py` copia esas filas a "Advertencias para el diagnóstico".

Para quitarlos y volver a ponerlos sin perderlos, guárdalos como parche **fuera del repo**, uno por repo (`<parche>` es una ruta en una carpeta que ese repo no versiona):

- Guardar, y comprobar que revierte limpio: `cd <repo> && git diff --binary -- <archivos> > <parche> && git apply --check -R <parche>` (un archivo nuevo entra en el parche después de `git add -N <archivo>`)
- Quitar: `cd <repo> && git apply -R <parche>` (y `git reset -q -- <archivo>` por cada archivo nuevo que se agregó con `git add -N`) · Volver a aplicar: `cd <repo> && git apply <parche>`

## Mapa del alcance

- <`ruta/al/Archivo.kt:línea`: qué es, en una línea>

## Hipótesis

1. <hipótesis → se confirma o se descarta con una métrica o una consulta>

## Métricas

<!-- perf:metricas -->
(lo escribe perf.py capturar)
<!-- /perf:metricas -->

## Advertencias para el diagnóstico

Lo que `perf.py` observó en los comandos de la terminal y que la sesión 2 lee antes que las métricas. Si una mejora toca algo que una advertencia menciona, la mejora lo dice. Lo escribe y lo mantiene `perf.py`: no lo edites.

<!-- perf:advertencias -->
(lo escribe perf.py: avisos de la corrida de prueba, corridas inválidas, avisos de las capturas, lo no medido, el ruido entre antes y control y los cambios temporales que alteran la app)
<!-- /perf:advertencias -->

## Hallazgos

Tipo: `bug`, `mejorable`, `consecuencia de H#`, `descartado` (con evidencia de la traza) o `sin confirmar` (el síntoma puede ser estable; la causa no está probada). "Qué falta para decidir" va en los `sin confirmar`.

| # | Síntoma | Evidencia (métrica + consulta + archivo:línea) | Causa raíz | Tipo | Qué falta para decidir |
| --- | --- | --- | --- | --- | --- |

## Plan de mejoras

Las mejoras viven en `mejoras` de plan.json; perf.py dibuja la tabla (propuesta en `reporte --inicial`, propuesto contra logrado en `comparar`).

<!-- perf:mejoras -->
(lo escribe perf.py)
<!-- /perf:mejoras -->

## Decisiones

- <AAAA-MM-DD: lo escribe `perf.py decidir`; agrega aquí el porqué si el usuario lo dio>

## Mejoras aplicadas

- <M1 · archivos · test que la fija · DoD · commit propuesto: perf(alcance): ...>

## Comparación

<!-- perf:comparacion -->
(lo escribe perf.py comparar)
<!-- /perf:comparacion -->

## Lectura de la comparación

- <qué dice cada métrica principal, cada regresión y cada "no comparable"; la evidencia que solo sale de consultas, rotulada "sin veredicto estadístico">

## Resumen ejecutivo

<3 a 5 líneas. Para el reporte inicial (sesión 2): qué se midió, qué se encontró y qué se propone, o por qué no hay mejoras. Para el final (sesión 4): estado inicial → estado final con las métricas principales, la causa en una frase y qué depende del backend>

## Pendientes

- <no son mejoras, sino lo que la investigación no pudo cerrar; uno por línea: H3 · síntoma y qué tan estable es (en cuántas corridas, con qué métrica) · qué falta para cerrarlo · cuánto cuesta (una corrida, una captura con muestreo, una sesión) · acción sugerida; si lo que falta es una captura que se puede correr ya, agrégala como Captura pendiente, con su comando entre acentos graves>

## Consumo

| Sesión | Modelo | Costo o tokens | Pasos |
| --- | --- | --- | --- |
