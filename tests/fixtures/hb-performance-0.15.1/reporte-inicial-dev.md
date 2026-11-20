# Rendimiento · Detalle de un ítem · 2026-04-14

_Reporte inicial · 2026-11-19 · hb-performance 0.15.1_

## Resumen

Se midió la apertura del detalle desde la lista. El detalle se carga dos veces (H1) y hay un frame largo al entrar cuya causa no está probada (H2). Se propone una sola carga (M1) y, a prueba, decodificar la imagen fuera del hilo principal (M2).

## Métricas principales

| Medida | Hoy (lo típico) | Entre | Estable |
| --- | --- | --- | --- |
| Mayor congelamiento de la pantalla, en la parte "detalle" | 48 milisegundos | 47 milisegundos y 50 milisegundos | sí |
| Tiempo de "lista a detalle" | 0.41 s | 0.41 s y 0.42 s | sí |

## Mejoras propuestas

<details class="card">
<summary>M1 · Una sola carga del detalle · aplicada · implementada; se mide en la fase después · riesgo bajo</summary>

- **Por qué:** Dos cargas del detalle (H1). Causa: Se carga en `init` y en `onResume`. Evidencia: Llamadas a servicios duplicadas = 1 · `llamadas_solapadas` · `DetalleViewModel.kt:31`.
- **Qué se espera:** 0 llamadas.

- **Tests y DoD:** M1 · `DetalleViewModel.kt` · `DetalleViewModelTest` fija una sola carga · DoD en verde · commit propuesto: perf(detalle): cargar el detalle una sola vez

</details>

<details class="card">
<summary>M2 · Decodificar la imagen de cabecera fuera del hilo principal (a prueba) · pendiente · queda para más adelante · riesgo bajo</summary>

- **Por qué:** Frame largo al entrar al detalle, estable en las 5 corridas (H2). Causa: La causa no está probada. Evidencia: Mayor congelamiento de la pantalla, en la parte "detalle" 48 ms · `hilo_principal_top`.
- **Hipótesis (a prueba):** El slice largo al entrar al detalle es la decodificación de la imagen de cabecera: coincide con su primer frame.
- **Qué se espera:** ≤ 16 ms.

</details>

## Servicios

Las mediciones no traen datos por servicio (solo el total de llamadas): no se puede decir qué servicio cambió (la comparación completa, en el anexo, trae el total de llamadas).

## Anexo

### Red por tramo

> Las llamadas de red que empiezan dentro de cada tramo del flujo (mediana entre corridas). La duración y el TTFB incluyen el backend; las repetidas y las solapadas son de la app.

| Flujo | Tramo | Fase | Llamadas | Duración mediana | TTFB mediano | Repetidas (2 s) | Solapadas |
| --- | --- | --- | --- | --- | --- | --- | --- |
| detalle | detalle | antes | 2 llamadas | 303 ms | 183 ms | 1 llamada | 1 llamada |

Sin llamadas que empiecen dentro: espera (antes).

### Se revisó y se descartó

- H2 · sin confirmar · Frame largo al entrar al detalle, estable en las 5 corridas: Mayor congelamiento de la pantalla, en la parte "detalle" 48 ms · `hilo_principal_top`. Falta para decidir: una captura con muestreo de CPU o probar el cambio.
- H3 · descartado · Jank en la lista: La traza no muestra frames perdidos por la app. Cuadros que se ven trabados 2 % · `jank_por_tipo`.

### Ficha y condiciones

| Campo | Valor |
| --- | --- |
| Alcance | Detalle de un ítem |
| Síntoma | El detalle tarda en mostrar su contenido |
| Métricas principales y objetivo | sin completar |
| Build y ambiente | sin completar |
| Dispositivo | Pixel Test · Android 14 (API 34) · 60 Hz fijos |
| Modos | sin completar |

### Costo de la investigación

> Lo que costó cada sesión de IA, según lo anotó quien la corrió (`perf.py consumo`). Las mediciones corren en la terminal, sin chat, y no cuestan tokens.

| Sesión | Modelo | Costo o tokens |
| --- | --- | --- |
| 2 · diagnóstico | Sonnet 5.5 · alto | 0.80 USD |

**Total:** 0.80 USD en 1 sesión anotada · faltan anotar 2 sesiones hechas (1 · ficha, 3 · M1): el total es parcial

### Cómo leer este reporte

- **Valor típico (mediana):** el del medio de las mediciones de una fase; una medición rara no lo mueve. Es el que se compara.
- **Peores casos habituales (P90):** 9 de cada 10 mediciones quedaron por debajo.
- **Mediciones por fase:** cuántas veces se repitió el recorrido. Menos de 5 es poca evidencia.
- **Variación normal:** cuánto cambia una medida entre dos mediciones **sin ningún cambio** en la app (antes contra la repetición sin cambios). Una diferencia menor que eso no prueba nada.
- **Varía mucho:** las mediciones difieren entre sí más de un 10 %; suele ser el servidor, la red o el dispositivo. Si el cambio es mucho mayor que esa variación (al menos el doble de lo que varía cada fase y el triple de la variación normal, sin que los rangos se toquen), el resultado no se vuelve orientativo.
- **Depende de:** "solo la app" se puede mejorar desde el código; "app y servidor" incluye la red y el backend; "informativa" no tiene veredicto.
- **Etiquetas:** Mejora o Regresión solo cuando el valor de después sale del rango de antes y supera la variación normal; Sin cambio y Dentro del ruido, que no se puede afirmar nada; Orientativo, que cambió pero la comparación no es del todo igual contra igual o varía demasiado; Costo conocido, que sube a propósito por una mejora elegida; No comparable, que antes y después midieron cosas distintas; No confiable, que el dispositivo no representa uno real.
- **Hallazgos:** solo los confirmados (con evidencia de la traza y el archivo y la línea del código) pasan a ser mejoras. Lo descartado y lo sin confirmar está en "Se revisó y se descartó", para no investigarlo de nuevo.
- **Mejoras (M1, M2…):** cada una es un panel plegable con por qué se hizo, qué ganó, su costo y su condición, y cada archivo con su riesgo, antes, después, pros, contras y el diff completo.
- **Tramos:** partes del recorrido entre dos marcas (una pantalla, un salto). Cada pausa del hilo principal y cada cuadro cuentan en un solo tramo: aquel donde empiezan (regla del borde).
- **Servicios:** se muestran como su método y su ruta real (GET https://…). La línea de tiempo de cada acción va del toque a que se ve el contenido, con una barra por llamada; ×2 marca una llamada repetida.
- **Gráficos:** la barra es el valor típico y la línea fina va del caso más rápido al más lento; la franja punteada marca la variación normal alrededor de antes.
- **Unidades:** los tiempos de un segundo o más van en segundos (1.81 s) y los más cortos en milisegundos (450 ms); el cambio, en porcentaje respecto de antes.

### Regla del borde de los tramos

Cada slice del hilo principal y cada frame cuentan en un solo tramo: aquel donde empiezan.

- Antes: regla anterior a 0.15.0: un slice o un frame que cruzaba el borde contaba en los dos tramos.
- Control: regla anterior a 0.15.0: un slice o un frame que cruzaba el borde contaba en los dos tramos.
- Después: regla anterior a 0.15.0: un slice o un frame que cruzaba el borde contaba en los dos tramos.
