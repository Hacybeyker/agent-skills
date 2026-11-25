# Ideas nuevas: la escalera de analogía

Una idea totalmente nueva no tiene competidores ni reseñas propias. **Sin datos no es lo mismo que sin demanda:** nunca se descarta solo por eso. La investigación sube peldaño por peldaño hasta encontrar evidencia, y cada fuente registra de qué peldaño viene (`--peldano`).

## La escalera

El ejemplo es inventado: una app que organiza turnos para regar las plantas de un edificio.

| Peldaño | Qué se busca | Ejemplo | Confianza máxima |
| --- | --- | --- | --- |
| 1 · Directo | Apps que hacen lo mismo | Otras apps de turnos de riego entre vecinos | Alta |
| 2 · Variante | Lo mismo en otra plataforma, país o idioma, o una parte del problema | Apps de recordatorio de riego individuales | Alta |
| 3 · Análogo | El mismo mecanismo en otra categoría | Apps de turnos de limpieza entre compañeros de piso | Media |
| 4 · Sustituto | Cómo se resuelve hoy sin app: hojas de cálculo, grupos de chat, papel, servicios | Grupos de vecinos que se organizan por chat o con una lista en el ascensor | Media |
| 5 · Necesidad de fondo | El "trabajo" del usuario sin la solución: búsquedas y conversaciones sobre el problema | "Quién riega las plantas del edificio en vacaciones" | Media |
| 6 · Hipótesis general | Primeros principios: la población que tiene la necesidad, estimada desde arriba | Edificios con áreas verdes compartidas por mercado | Baja |

"Subir" es alejarse de lo directo: del 1 al 6. Se sube solo cuando el peldaño anterior no da evidencia, y se registra lo que se buscó en él aunque no haya aparecido nada.

## Clasificar la idea

**Antes de abrir las líneas.** Si las líneas arrancan sin saber que la idea es nueva, investigan como si hubiera competencia y nadie sube a los peldaños 4 y 5. Por eso la sesión 0 hace un triaje corto (en las tiendas del objetivo, 3 búsquedas como máximo: ¿hay apps que hagan lo mismo?) y registra un **tipo provisional** (`producto.py tipo --nueva --provisional --motivo "<lo que dio el triaje>"`); cada línea lo lee al empezar (viene en su texto para pegar) y la sesión 1a lo confirma con `producto.py tipo`, apenas lo sabe:

- **Existente:** hay competidores directos con tracción.
- **Variante:** hay directos, pero la idea cambia algo relevante.
- **Nueva:** no hay directos con tracción.

Las demás líneas consultan `producto.py tipo` antes de buscar y otra vez antes de cerrar. Si el tipo cambia cuando una línea ya cerró y esa línea no tiene fuentes de los peldaños que pide el tipo nuevo (en una idea nueva: 4 y 5 en la voz del usuario y la demanda, 2 y 3 en la monetización, 3 y 4 en la diferenciación), queda **a revisar por cambio de tipo**: `tipo`, `estado` y la puerta 1 lo dicen, y la puerta recomienda ajustarla. Lo ya registrado sirve; lo que falta se busca en los peldaños siguientes.

## Lo no buscado no es evidencia en contra

La puerta 1 no recomienda descartar por un criterio cuya evidencia no se buscó. Si ningún hallazgo ni ninguna búsqueda registrada toca los peldaños 4 y 5, el problema queda **no buscado** y la recomendación es ajustar la 1c (🟡); si se buscó y no apareció (`vacio --peldano 4 --motivo sin-resultados`), es evidencia y puede llevar a descartar. Lo mismo con una línea a revisar por cambio de tipo: lo que no buscó no cuenta en contra. `producto.py estado` (y la puerta 1 y el reporte de una idea nueva) cuenta los hallazgos por peldaño, vigentes y vencidos, y marca los peldaños no buscados.

## Cómo cambia cada sesión

| Sesión | En una idea nueva |
| --- | --- |
| 1a · Competencia | La matriz se llena con análogos (peldaño 3) y sustitutos (peldaño 4). Hacen falta al menos 2 análogos con tracción en los peldaños 2 o 3. Se registra la búsqueda de intentos anteriores (`producto.py intento`) |
| 1b · Voz del usuario | Quejas sobre cómo se resuelve hoy el problema (peldaño 4) y conversaciones sobre la necesidad de fondo (peldaño 5) |
| 1c · Demanda | Se busca el problema, no la solución. El tamaño se estima desde arriba (peldaño 6), como estimación |
| 1d · Monetización | Modelos y precios de los análogos más cercanos, diciendo de cuál sale cada dato |
| 1g · Diferenciación | Se compara contra los sustitutos y los análogos: por qué alguien dejaría la hoja de cálculo o el grupo de chat |
| 1f · Síntesis | Separa lo que tiene evidencia análoga de lo que todavía es pura hipótesis |
| 2 · Estrategia | Los escenarios van *por analogía*, con un rango más amplio |
| 3 · Validación | La hipótesis más riesgosa lleva su métrica y su umbral: es un criterio de la puerta 2 |
| 4 · PRD | Un MVP más chico, centrado en poner a prueba la hipótesis más riesgosa |

El presupuesto por línea sube a 20 búsquedas y 12 lecturas, porque subir de peldaño cuesta más.

## Un hueco no es una oportunidad por sí solo

Si no existe, hay dos explicaciones: nadie lo pensó, o alguien lo probó y no funcionó. La segunda se busca siempre: productos cerrados, post-mortems, lanzamientos abandonados, fichas sin actualizar hace años. El resultado se registra:

```bash
python3 -I <skill>/scripts/producto.py intento --resultado sin-rastro \
  --texto "Busqué «app turnos riego vecinos cerró» y post-mortems de apps de comunidades: sin resultados"
```

- `sin-rastro`: se buscó y no apareció nada.
- `fracaso-otra-causa`: alguien lo intentó y cerró por otra razón (fondos, equipo, ejecución). Lleva su fuente y dice en qué se parece.
- `fracaso-demanda`: alguien lo intentó y nadie lo quiso. Es evidencia en contra: la puerta 1 lo marca.

Sin ningún registro, la puerta 1 de una idea nueva no se cumple.

## Qué triangular

En una idea nueva se triangula **el peldaño más cercano a lo directo que tenga evidencia**, no la solución exacta: que el problema existe (peldaños 4 y 5) y que el mecanismo funciona en otra categoría (peldaño 3). La puerta 1 pide:

- el problema o la necesidad de fondo documentados con 3 fuentes independientes y vigentes de los peldaños 4 o 5, una de ellas de los últimos 18 meses (los censos, las encuestas nacionales y los estudios académicos valen 5 años: [evidencia.md](evidencia.md));
- al menos 2 análogos con tracción (peldaños 2 o 3) en la matriz: con 100 000 descargas o más o con un respaldo institucional (`--respaldo`), nunca por una nota;
- la búsqueda de intentos anteriores registrada, sin un fracaso por falta de demanda.

## Falsa analogía

Un análogo puede tener tracción por razones que la idea no comparte. Por eso cada analogía, en el entregable, dice **en qué se parece y en qué no**:

> Los turnos de limpieza entre compañeros de piso se parecen en el mecanismo (repartir una tarea recurrente y avisar a quien le toca). No se parecen en el vínculo: los compañeros de piso se ven a diario; los vecinos de un edificio, no.

## Puntaje y confianza

El puntaje de una idea nueva usa el peldaño más cercano a lo directo con evidencia, y `producto.py puntaje` lo muestra. Como la confianza de cada hallazgo ya está limitada por su peldaño, la confianza global de una idea nueva rara vez pasa de media: es lo esperado, y no un motivo de descarte. El mínimo de la puerta 1 baja a 15/25.

## La validación pesa más después

Una idea nueva llega al lanzamiento con más incertidumbre. Por eso el PRD define desde el inicio qué métrica, con qué umbral y en cuánto tiempo, confirma o descarta la hipótesis más riesgosa ([validacion.md](validacion.md) y [prd.md](prd.md)).
