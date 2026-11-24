# Puntaje y síntesis (sesión 1f)

La síntesis une las seis líneas y termina en la puerta 1. El puntaje tiene anclas para que no dependa del humor del modelo: tú eliges el ancla que corresponde a la evidencia, y el total, la confianza y la comparación los calcula `producto.py`.

## Presupuesto y lista de tareas

**Cuándo:** con las seis líneas cerradas (1a a 1e y 1g). **Sin búsquedas nuevas:** si falta evidencia, se dice; el usuario puede ajustar una línea en la puerta.

1. Primera línea: `Sesión 1f · Síntesis (<motivo>)`.
2. `producto.py estado`, `producto.py tipo`, `producto.py triangulacion` y `producto.py cobertura`.
3. Lee los seis archivos de `01-investigacion/`, sobre todo "Para la síntesis" y "⚠ Sin evidencia".
4. Confirma el tipo de idea. Si la investigación lo cambió, regístralo de nuevo con su motivo.
5. Elige el valor de cada criterio con la tabla de anclas y escribe en `01-sintesis.md` qué ancla aplicaste y con qué hallazgos.
6. `producto.py puntaje --valores d,m,f,r,x [--mitigacion "<texto>"]`, en este orden: demanda, monetización, facilidad, riesgo de políticas y diferenciación.
7. Completa `01-sintesis.md`. En una idea nueva, separa la evidencia análoga de la pura hipótesis; en una con competencia, presenta el diferenciador principal.
8. `producto.py cerrar --sesion 1f` y pega la salida: es la puerta 1.

**No recomiendes la decisión.** La "Lectura" dice qué muestra la evidencia; seguir, ajustar o descartar lo decide el usuario.

## Anclas

Cinco criterios de 1 a 5. Los valores 2 y 4 son los intermedios entre dos anclas.

| Criterio | 1 | 3 | 5 |
| --- | --- | --- | --- |
| Demanda | Ningún peldaño muestra el problema | Señales actuales estables: búsquedas sin caída, descargas recientes de los competidores o el problema documentado en los peldaños 4 y 5, en los últimos 12 a 18 meses | Señales actuales que crecen: tendencia de búsqueda al alza y descargas recientes altas en los últimos 12 a 18 meses, o análogos masivos con el problema bien documentado hoy |
| Monetización | Sin modelo viable (por ejemplo, anuncios a niños) | Competidores o análogos que monetizan con precios conocidos | Ingresos verificables y disposición a pagar documentada |
| Facilidad | Más de 3 meses o backend complejo | De 4 a 8 semanas | 2 semanas o menos, sin backend |
| Riesgo de políticas (5 = bajo) | Categoría regulada (salud médica, finanzas, niños con anuncios), o una tienda objetivo que nombra la categoría o la rechaza | Requisitos manejables (declaraciones, avisos) | Sin políticas especiales |
| Diferenciación | Ningún diferenciador viable | 1 diferenciador viable, fácil de copiar | Varios diferenciadores viables, o uno que se ve en la ficha y es difícil de copiar |

- **Demanda con señales actuales.** Las descargas acumuladas (las de una ficha que lleva años publicada) dicen que hubo demanda, no que la haya hoy: son contexto. Las anclas 4 y 5 piden un hallazgo clave de demanda **triangulado** con fuentes vigentes y no acumuladas; sin él, el script no acepta más de 3. Registra los datos acumulados con `fuente --acumulado`.
- **Una tienda que nombra o rechaza la categoría** (por ejemplo, una guía de revisión que la cita como saturada) se registra en un hallazgo de políticas con `--bloquea <tienda>`. En esa tienda el riesgo es 1: el script no acepta otro valor, y la puerta 1 pide una mitigación escrita y creíble (`--mitigacion`, por ejemplo, no lanzar en esa tienda), que muestra para que el usuario la juzgue. Cambiar las tiendas del objetivo para evitarlo es un cambio de criterio, con su motivo.
- **La cantidad de competidores no baja ningún criterio.** Muchos competidores con tracción suben la demanda; lo que puede bajar es la diferenciación, y solo si no aparece un diferenciador viable.
- **Diferenciación** está atada al registro (y un diferenciador que no supera al sustituto gratuito o nativo que ya resuelve la necesidad no es viable): sin ningún diferenciador viable, el script solo acepta 1; si solo hay viables con confianza baja (sus hallazgos sin triangular), acepta 1 o 2; con alguno viable, no acepta 1.
- **Facilidad** es una estimación tuya, sin fuentes: di con qué supuestos (stack, backend, integraciones).
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
