# Rendimiento · Detalle de un ítem · 2026-04-14

## Siguiente paso

- _Lo escribe `perf.py siguiente --carpeta <carpeta>` (y cada comando de perf.py al terminar)._

## Ficha

| Campo | Valor |
| --- | --- |
| Alcance | Detalle de un ítem |
| Síntoma | El detalle tarda en mostrar su contenido |
| Métricas principales y objetivo | <las de `principales` en plan.json, y el objetivo de cada una> |
| Flujos | pasos e invalidaciones en plan.json |
| Build y ambiente | <variante medida (R8, no depurable, profileable) · backend real o mocks> |
| Dispositivo | Pixel Test · Android 14 (API 34) · 60 Hz fijos |
| Modos | <guiado o autónomo · recorrido manual, comando o arranque-frio · riguroso o triage> |
| Stack | Compose · corrutinas · LazyColumn · Retrofit |
| Precondiciones | estado de la app igual en todas las fases (sesión, datos, caché) · nunca desinstalar ni borrar datos entre fases |
| No leer | ninguna |

## Cómo se recorre

<!-- perf:recorrido -->
(lo escribe perf.py: `preparar` y `recorrido` de cada flujo, y el comando para verlos correr a mano)
<!-- /perf:recorrido -->

## Cambios temporales por revertir

Marcas o código puestos solo para esta investigación (por ejemplo, una marca con `android.os.Trace` en un módulo que no ve `PerfHooks`) y las ediciones de cableado en código de `main` que no se van a commitear (el gancho de red donde se arma el cliente HTTP, por ejemplo). Se revierten antes de proponer un commit y, a más tardar, en el cierre.

| Archivo | Repo o módulo | Qué es | ¿Revertido? |
| --- | --- | --- | --- |
| `feature/detalle/src/main/kotlin/com/example/detalle/DetalleFragment.kt` | feature/detalle | `MARK detalle` con `android.os.Trace` | no |

Para quitarlos y volver a ponerlos sin perderlos, guárdalos como parche **fuera del repo**, uno por repo (`<parche>` es una ruta en una carpeta que ese repo no versiona):

- Guardar, y comprobar que revierte limpio: `cd <repo> && git diff --binary -- <archivos> > <parche> && git apply --check -R <parche>` (un archivo nuevo entra en el parche después de `git add -N <archivo>`)
- Quitar: `cd <repo> && git apply -R <parche>` (y `git reset -q -- <archivo>` por cada archivo nuevo que se agregó con `git add -N`) · Volver a aplicar: `cd <repo> && git apply <parche>`

## Mapa del alcance

- `app/src/main/kotlin/com/example/app/detalle/DetalleScreen.kt:40`: la pantalla del detalle.

## Hipótesis

1. Carga duplicada al entrar → se confirma con `red_solapadas`.

## Métricas

<!-- perf:metricas -->
(lo escribe perf.py capturar)
<!-- /perf:metricas -->

## Hallazgos

Tipo: `bug`, `mejorable`, `consecuencia de H#`, `descartado` (con evidencia de la traza) o `sin confirmar` (el síntoma puede ser estable; la causa no está probada). "Qué falta para decidir" va en los `sin confirmar`.

| # | Síntoma | Evidencia (métrica + consulta + archivo:línea) | Causa raíz | Tipo | Qué falta para decidir |
| --- | --- | --- | --- | --- | --- |
| H1 | Dos cargas del detalle | `red_solapadas` = 1 · `llamadas_solapadas` · `DetalleViewModel.kt:31` | Se carga en `init` y en `onResume` | bug | — |
| H2 | Frame largo al entrar al detalle, estable en las 5 corridas | `detalle hilo_max_ms` 48 ms · `hilo_principal_top` | La causa no está probada | sin confirmar | Una captura con muestreo de CPU o probar el cambio |
| H3 | Jank en la lista | `jank_app_pct` 2 % · `jank_por_tipo` | La traza no muestra frames perdidos por la app | descartado | — |

## Plan de mejoras

Las mejoras viven en `mejoras` de plan.json; perf.py dibuja la tabla (propuesta en `reporte --inicial`, propuesto contra logrado en `comparar`).

<!-- perf:mejoras -->
(lo escribe perf.py)
<!-- /perf:mejoras -->

## Decisiones

- <AAAA-MM-DD: lo escribe `perf.py decidir`; agrega aquí el porqué si el usuario lo dio>

## Mejoras aplicadas

- M1 · `DetalleViewModel.kt` · `DetalleViewModelTest` fija una sola carga · DoD en verde · commit propuesto: perf(detalle): cargar el detalle una sola vez

## Comparación

<!-- perf:comparacion -->
(lo escribe perf.py comparar)
<!-- /perf:comparacion -->

## Lectura de la comparación

- <qué dice cada métrica principal, cada regresión y cada "no comparable"; la evidencia que solo sale de consultas, rotulada "sin veredicto estadístico">

## Resumen ejecutivo

Se midió la apertura del detalle desde la lista. El detalle se carga dos veces (H1) y hay un frame largo al entrar cuya causa no está probada (H2). Se propone una sola carga (M1) y, a prueba, decodificar la imagen fuera del hilo principal (M2).

## Pendientes

- <no son mejoras, sino lo que la investigación no pudo cerrar; uno por línea: H3 · síntoma y qué tan estable es (en cuántas corridas, con qué métrica) · qué falta para cerrarlo · cuánto cuesta (una corrida, una captura con muestreo, una sesión) · acción sugerida; si lo que falta es una captura que se puede correr ya, agrégala como Captura pendiente, con su comando entre acentos graves>

## Consumo

| Sesión | Modelo | Costo o tokens | Pasos |
| --- | --- | --- | --- |
