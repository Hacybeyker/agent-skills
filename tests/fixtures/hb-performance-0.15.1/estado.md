# Rendimiento · Detalle de un ítem · 2026-04-14

## Siguiente paso

- **Paso:** investigación cerrada · faltan quitar los cambios temporales y el DoD
- **En orden, uno a la vez:**
  1. **Terminal** (sin chat) · quita el cambio temporal que sigue puesto (feature/detalle/src/main/kotlin/com/example/detalle/DetalleFragment.kt): por repo, guarda un parche que no pisa otro, comprueba que revierte limpio, lo quita, muestra git status y lo marca revertido en estado.md; las mejoras y lo que ya estaba modificado se quedan. Con --simular solo muestra qué haría
     `cd /home/dev/proyecto && python3 -I /home/dev/.agents/skills/hb-performance/scripts/perf.py cerrar --carpeta reports/perf/detalle/2026-03-02`
     Tú: córrelo una vez; si algo no revierte limpio, se detiene sin tocar nada y te dice por qué. Nunca quites un cambio temporal con git checkout, git restore, git reset --hard ni git clean.
  2. El reporte final técnico; se puede compartir: lleva solo métricas agregadas: /home/dev/proyecto/reports/perf/detalle/2026-03-02/reporte-final-dev.md
  3. El mismo reporte para un público no técnico (gerencia): /home/dev/proyecto/reports/perf/detalle/2026-03-02/reporte-final-gerencia.md
  4. **Con los cambios temporales quitados y el DoD en verde (`cerrar` lo da al terminar), la investigación queda cerrada: no quedará ningún paso por ejecutar.**
- **Costo (opcional, terminal):** faltan anotar 1 · ficha, 3 · M1, 4 · cierre. `perf.py siguiente` imprime un comando listo por cada una; solo falta el costo.
- _Lo escribe `perf.py siguiente`: si algo cambió, vuelve a correrlo._

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
**detalle**
- `preparar` (antes de cada corrida, fuera de la traza): `maestro --device emulator-5554 test -e APP_USUARIO_PRUEBA="$APP_USUARIO_PRUEBA" -e APP_CLAVE_PRUEBA="$APP_CLAVE_PRUEBA" reports/perf/detalle/preparar.yaml > /dev/null 2>&1 && sleep 2`
- `recorrido` (el tramo medido): `bash reports/perf/detalle/recorrido.sh`
- Para verlo correr a mano, sin medir: `cd /home/dev/proyecto && maestro --device emulator-5554 test -e APP_USUARIO_PRUEBA="$APP_USUARIO_PRUEBA" -e APP_CLAVE_PRUEBA="$APP_CLAVE_PRUEBA" reports/perf/detalle/preparar.yaml > /dev/null 2>&1 && sleep 2 && bash reports/perf/detalle/recorrido.sh`
- Variables de entorno que necesita: `APP_USUARIO_PRUEBA`, `APP_CLAVE_PRUEBA`. Cárgalas en la terminal donde mides, antes de medir (las claves, con lectura oculta; el valor no se guarda): `cd /home/dev/proyecto && printf 'APP_USUARIO_PRUEBA: ' && read -r APP_USUARIO_PRUEBA && export APP_USUARIO_PRUEBA`; `cd /home/dev/proyecto && printf 'APP_CLAVE_PRUEBA: ' && read -r -s APP_CLAVE_PRUEBA && echo && export APP_CLAVE_PRUEBA`
- Igual contra igual (lo calcula perf.py): sin la huella de los archivos del recorrido en antes, control, después (medida con una versión anterior a 0.12.0): no se puede afirmar que los scripts fueron los mismos
- Recorrido en palabras: Propósito: el flujo medido

Los archivos del recorrido (`recorrido.sh`, `preparar.sh`, `preparar.yaml`) viven en esta carpeta, que git ignora y que se borra al limpiar: si los vas a reutilizar, archívalos fuera de `reports/`.
<!-- /perf:recorrido -->

## Cambios temporales por revertir

Marcas o código puestos solo para esta investigación (por ejemplo, una marca con `android.os.Trace` en un módulo que no ve `PerfHooks`) y las ediciones de cableado en código de `main` que no se van a commitear (el gancho de red donde se arma el cliente HTTP, por ejemplo). Se revierten antes de proponer un commit y, a más tardar, en el cierre.

| Archivo | Repo o módulo | Qué es | Altera | ¿Revertido? |
| --- | --- | --- | --- | --- |
| `feature/detalle/src/main/kotlin/com/example/detalle/DetalleFragment.kt` | feature/detalle | `MARK detalle` con `android.os.Trace` | — | no |

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

## Advertencias para el diagnóstico

Lo que `perf.py` observó en los comandos de la terminal.

<!-- perf:advertencias -->
- Ruido de `lista_a_detalle_ms` (detalle): antes y control difieren en 1 ms (0.24 %) sin ningún cambio. Mejora mínima demostrable: la mediana de después tiene que quedar por debajo de 405 ms (más de 7 ms, 1.7 % respecto de la mediana de antes, 412 ms)
- Ruido de `detalle hilo_max_ms` (detalle): antes y control difieren en 0 ms (0 %) sin ningún cambio. Mejora mínima demostrable: la mediana de después tiene que quedar por debajo de 47 ms (más de 1 ms, 2.08 % respecto de la mediana de antes, 48 ms)
<!-- /perf:advertencias -->

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
| # | Mejora | Hallazgo | Métrica | Antes | Esperado | Prioridad | Esfuerzo | Riesgo | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | Una sola carga del detalle | H1 | red_solapadas | 1 llamada | 0 llamadas | alta | bajo | bajo | aplicada |
| M2 | Decodificar la imagen de cabecera fuera del hilo principal (a prueba) | H2 | detalle hilo_max_ms | 48 ms | ≤ 16 ms | media | bajo | bajo | pendiente |

**Mejoras a prueba** (la causa no está probada: el cambio se aplica y la medición de después confirma o refuta la hipótesis):

- **M2** · hipótesis: El slice largo al entrar al detalle es la decodificación de la imagen de cabecera: coincide con su primer frame · se confirma si `detalle hilo_max_ms` mejora (esperado: ≤ 16 ms)
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

## Resumen para gerencia

El detalle se pedía dos veces al abrirlo. Se propone pedirlo una sola vez.

## Pendientes

- <no son mejoras, sino lo que la investigación no pudo cerrar; uno por línea: H3 · síntoma y qué tan estable es (en cuántas corridas, con qué métrica) · qué falta para cerrarlo · cuánto cuesta (una corrida, una captura con muestreo, una sesión) · acción sugerida; si lo que falta es una captura que se puede correr ya, agrégala como Captura pendiente, con su comando entre acentos graves>

## Consumo

| Sesión | Modelo | Costo o tokens | Pasos |
| --- | --- | --- | --- |
| 2 · diagnóstico | Sonnet 5.5 · alto | 0.80 USD | — |

**Total de la investigación:** 0.80 USD en 1 sesión anotada · faltan anotar 3 sesiones hechas (1 · ficha, 3 · M1, 4 · cierre): el total es parcial
