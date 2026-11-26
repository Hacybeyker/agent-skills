# Puntaje y síntesis (sesión 1f)

La síntesis une las seis líneas y termina en la puerta 1. El puntaje tiene anclas para que no dependa del humor del modelo: tú eliges el ancla que corresponde a la evidencia, y el total, la confianza y la comparación los calcula `producto.py`.

## Presupuesto y lista de tareas

**Cuándo:** con las seis líneas cerradas (1a a 1e y 1g). **Sin búsquedas nuevas:** si falta evidencia, se dice; el usuario puede ajustar una línea en la puerta.

1. Primera línea: `Sesión 1f · Síntesis (<motivo>)`.
2. `producto.py estado`, `producto.py tipo`, `producto.py triangulacion` y `producto.py cobertura`.
3. Lee los seis archivos de `01-investigacion/`, sobre todo "Para la síntesis" y "⚠ Sin evidencia".
4. Confirma el tipo de idea. Si la investigación lo cambió, regístralo de nuevo con su motivo.
5. Elige el valor de cada criterio con la tabla de anclas y escribe en `01-sintesis.md` qué ancla aplicaste y con qué hallazgos.
6. `producto.py puntaje --valores d,m,f,r,x [--mitigacion "<texto>"]`, en este orden: demanda, monetización, facilidad, riesgo de políticas y diferenciación. Si la sesión 0 registró más de un modelo de monetización, puntúa con el base y con cada alternativo: `--modelo "<base>" --alternativo "<otro modelo>=d,m,f,r,x"` (se repite por modelo).
7. Completa `01-sintesis.md`. En una idea nueva, separa la evidencia análoga de la pura hipótesis; en una con competencia, presenta el diferenciador principal.
8. `producto.py cerrar --sesion 1f` y pega la salida: es la puerta 1.

**La recomendación la calcula el script.** La "Lectura" dice qué muestra la evidencia; el veredicto y la recomendación de la puerta 1 los da `producto.py` con reglas fijas ([puertas.md](puertas.md#veredicto-y-recomendación)): no des otra por tu lado. Seguir, ajustar o descartar lo decide el usuario.

## Anclas

Cinco criterios de 1 a 5. Los valores 2 y 4 son los intermedios entre dos anclas.

| Criterio | 1 | 3 | 5 |
| --- | --- | --- | --- |
| Demanda | Ningún peldaño muestra el problema | Señales actuales estables: búsquedas sin caída, descargas recientes de los competidores o el problema documentado en los peldaños 4 y 5, en los últimos 12 a 18 meses. También una señal que crece en un solo mercado del objetivo con los demás sin medir | Señales actuales que crecen en los mercados que pesan en el objetivo: tendencia de búsqueda al alza y descargas recientes altas en los últimos 12 a 18 meses, o análogos masivos con el problema bien documentado hoy |
| Monetización | Sin modelo viable (por ejemplo, anuncios a niños) | Competidores o análogos que monetizan con precios conocidos | Ingresos verificables y disposición a pagar documentada |
| Facilidad | Más de 3 meses o backend complejo | De 4 a 8 semanas | 2 semanas o menos, sin backend |
| Riesgo de políticas (5 = bajo) | Categoría regulada (salud médica, finanzas, niños con anuncios), o una tienda objetivo que nombra la categoría o la rechaza | Requisitos manejables (declaraciones, avisos) | Sin políticas especiales |
| Diferenciación | Ningún diferenciador viable | 1 diferenciador viable, fácil de copiar | Dos o más viables que no son fáciles de copiar (copiabilidad baja o media), o uno viable que se ve en la ficha y es difícil de copiar (baja). Con algún viable, en cualquier otro caso el máximo es 4 |

- **Demanda con señales actuales.** Las descargas acumuladas (las de una ficha que lleva años publicada) dicen que hubo demanda, no que la haya hoy: son contexto. Las anclas 4 y 5 piden un hallazgo clave de demanda **triangulado** con fuentes vigentes y no acumuladas; sin él, el script no acepta más de 3. Registra los datos acumulados con `fuente --acumulado`.
- **La señal de demanda, en los mercados que pesan.** Las anclas 4 y 5 piden la señal actual en los mercados que pesan en el objetivo: una señal que crece en un solo mercado, con los demás sin medir, llega a 3 como máximo (di en la síntesis cuáles pesan y por qué). El script lo aplica cuando el objetivo tiene dos mercados o más y todas las fuentes que cuentan de los hallazgos clave de demanda triangulados (vigentes y no acumuladas) llevan la etiqueta de un mismo mercado (`fuente --mercados`): no acepta más de 3 y dice qué falta (una señal triangulada de otro mercado o la etiqueta de la fuente que ya lo cubre). Una fuente sin etiqueta de mercado puede ser mundial: no lo tapa, y la regla la aplicas tú con el ancla.
- **Una tienda que nombra o rechaza la categoría** (por ejemplo, una guía de revisión que la cita como saturada) se registra en un hallazgo de políticas con `--bloquea <tienda>`. En esa tienda el riesgo es 1: el script no acepta otro valor, y la puerta 1 pide una mitigación escrita y creíble (`--mitigacion`, por ejemplo, no lanzar en esa tienda), que muestra para que el usuario la juzgue. Cambiar las tiendas del objetivo para evitarlo es un cambio de criterio, con su motivo.
- **La cantidad de competidores no baja ningún criterio.** Muchos competidores con tracción suben la demanda; lo que puede bajar es la diferenciación, y solo si no aparece un diferenciador viable.
- **Diferenciación** está atada al registro (y un diferenciador que no supera a la alternativa gratis más fuerte, o que solo la iguala, no es viable): sin ningún diferenciador viable, el script solo acepta 1; si solo hay viables con confianza baja (sus hallazgos sin triangular), acepta 1 o 2; con alguno viable, no acepta 1. Un viable con confianza baja que supera al rival con **el dolor triangulado** (sus hallazgos propios triangulados: solo le falta la prueba de elección, que se mide después del lanzamiento) cuenta como viable si la idea no tiene un bloqueo de políticas y la demanda tiene confianza media o alta: el puntaje no castiga dos veces lo que la puerta 1 deja como criterio de descarte ([diferenciacion.md](diferenciacion.md)).
- **El 5 de diferenciación mide lo defendible, no la cantidad.** El script solo lo acepta con dos o más viables que no son fáciles de copiar (`--copiable baja` o `media`) o con uno viable que se ve en la ficha (`--se-ve ficha`) y es difícil de copiar (`--copiable baja`); con algún viable, en cualquier otro caso el máximo es 4 (por ejemplo, varios viables fáciles de copiar, o uno solo de copia media). Los viables con confianza baja que cuentan como viables (arriba) siguen la misma regla de copiabilidad. Si rechaza el 5, dice qué falta y la copiabilidad de cada viable.
- **La distribución no es diferenciación.** Aparecer arriba en las búsquedas de las tiendas de un país o un idioma donde el rival no sale (ASO) no cuenta en este criterio ni en la puerta 1: el rival puede entrar a esas palabras en días y no cambia el producto. Es un hallazgo de la 1a que la sesión 2 usa para el canal de adquisición ([estrategia.md](estrategia.md)).
- **Un puntaje registrado con reglas anteriores** (o con evidencia que cambió después: una fuente que envejeció, un hallazgo anulado) puede quedar por encima de lo que las reglas de hoy aceptan. El criterio de la puerta 1, el veredicto, el reporte y el tablero muestran como principal el puntaje de hoy, con "se registró N/25" como dato secundario; se corrige volviendo a correr `puntaje` en la sesión 1f.
- **El modelo de monetización cambia el puntaje.** Los anuncios en una app para niños bajan el riesgo de políticas a 1; un pago único detrás de un control parental, no. Si hay un modelo alternativo registrado en la sesión 0, puntúa con cada uno (`--alternativo`): la puerta 1 muestra los dos totales y, si el mínimo solo se alcanza con el alternativo, dice que lo exige y que la sesión 2 tiene que elegirlo.
- **Facilidad** es una estimación tuya, sin fuentes: di con qué supuestos (stack, backend, integraciones). No sube con evidencia: solo recortando el alcance del MVP, que es un cambio de alcance con su motivo (la puerta 1 lo dice así en «Qué cambiaría»).
- **Riesgo de políticas = 1** pide una mitigación escrita (`--mitigacion`); sin ella, la puerta 1 no se cumple en ese criterio.

## Confianza global

Junto al total, `producto.py puntaje` muestra la confianza de cada criterio: la **menor** de las confianzas de los hallazgos clave que lo sostienen.

| Criterio | Lo sostienen |
| --- | --- |
| Demanda | Los hallazgos clave (`--critico`) de la línea `demanda` |
| Monetización | Los hallazgos clave de la línea `monetizacion` |
| Riesgo de políticas | Los hallazgos clave de la línea `politicas` |
| Diferenciación | Los hallazgos del diferenciador principal o, si no hay principal, los de los viables (o los de los viables con confianza baja) |
| Facilidad | Nada: es una estimación |

**La confianza no es la dirección.** La confianza dice qué tan seguro es un hallazgo, no si es favorable. Un hallazgo clave de demanda que confirma «la demanda es pequeña» con confianza alta sube la confianza de la demanda (y cumple ese criterio de la puerta 1), pero la magnitud va al ancla: la demanda puntúa bajo y, si el total queda bajo el mínimo, la puerta 1 falla por el puntaje, no por la confianza. Lo mismo en las demás líneas.

La **confianza global** es la menor de todas. Un criterio sin ningún hallazgo clave sale como **⚠ Sin evidencia** y deja la global en "sin evidencia": antes de cerrar, marca como clave el hallazgo que lo sostiene o dilo en la síntesis.

En una idea nueva, la confianza ya viene limitada por el peldaño de cada hallazgo ([analogia.md](analogia.md)), y el script muestra el peldaño más cercano a lo directo con evidencia.

## Qué va en la síntesis

- **Lo que se sabe:** solo hallazgos registrados, con su ID y su confianza.
- **Triangulación:** qué hallazgos clave cumplen y qué le falta a cada uno de los demás, siempre con su confianza ("media · sin triangular").
- **Cobertura:** los mercados, idiomas y tiendas sin fuentes y por qué (vacíos de herramienta, sin resultados o presupuesto). Un vacío de herramienta no es evidencia en contra: se resuelve con un navegador o un CSV, no ajustando la línea.
- **Evidencia en contra:** lo que encontró el abogado del diablo en cada línea, también cuando no encontró nada.
- **Puntaje:** el valor de cada criterio, el ancla que corresponde y sus hallazgos; el total y la confianza, copiados de la salida del script.
- **Lectura:** 5 líneas como máximo.
- **⚠ Sin evidencia:** lo que sigue sin fuente.

Una síntesis no repite las seis líneas: enlaza a ellas.
