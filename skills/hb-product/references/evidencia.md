# Evidencia: fuentes, triangulación, confianza y sesgos

Vale para todas las sesiones. La regla es **evidencia o nada**: lo que no tiene una fuente registrada va en el texto como **⚠ Sin evidencia**, y nunca entra al registro.

## Registrar una fuente

```bash
python3 -I <skill>/scripts/producto.py fuente --linea demanda --url https://ejemplo.example/informe \
  --publicada 2026-05 --tipo medido --peldano 1 --autor "Medio de ejemplo" \
  --resumen "Qué dice, en 3 líneas como máximo, con el dato y su unidad."
```

Devuelve el ID (`S-DEM-1`). Los códigos por línea: `COM` competencia, `VOZ` voz del usuario, `DEM` demanda, `MON` monetización, `POL` políticas, `DIF` diferenciación, `EST` estrategia y `VAL` validación. Cada sesión registra **solo en su línea**; puede citar fuentes de otra.

- **`--publicada`:** la **fecha real de publicación**, `AAAA-MM-DD` o `AAAA-MM`, o `desconocida` si de verdad no aparece (con `--archivo`, también `auto`; `sin-fecha` es el nombre anterior de `desconocida`). Una fuente sin fecha o fuera de la ventana no es vigente: no cuenta para triangular ni para la confianza (abajo).
  - Una reseña, un hilo, un artículo o un video llevan **su** fecha, no la del día en que los leíste: una reseña de 2011 leída hoy es de 2011. Si la página no la muestra, `desconocida`; buscarla casi siempre vale más.
  - Un **dato vivo** (el contador de una ficha, una tendencia de los últimos 12 meses) sí lleva la fecha del día en que lo leíste.
  - Si la fecha de publicación coincide con la de consulta, `fuente` lo avisa: confirma que es un dato vivo o corrígela (`anular` y otra vez `fuente`). Nunca se acepta una publicación posterior a la consulta (`--consultada`, por defecto hoy).
- **`--tipo`:**

| Tipo | Qué es | Ejemplos |
| --- | --- | --- |
| `medido` | Un número que alguien midió y publicó | Descargas y nota de una ficha, volumen de búsqueda, estadísticas oficiales, un reporte con metodología |
| `usuario` | Lo que dice quien usa el producto o tiene el problema | Reseñas, hilos de foros, comentarios |
| `terceros` | Análisis de alguien que no es usuario ni dueño | Prensa, comparativas, documentación oficial de una plataforma |
| `opinion` | Una opinión sin datos | Una columna, un hilo de recomendaciones, la página de ventas de un competidor |
| `oficial` | El texto primario de una norma, en su página oficial | Las políticas para desarrolladores de una tienda, sus guías de revisión, el texto de una ley o de un reglamento |

- **`--peldano`:** de 1 a 6, según la escalera de [analogia.md](analogia.md). En una idea con competencia casi todo es 1.
- **`--autor`:** la app, la empresa o el medio que publica. **Nunca un nombre de usuario** (el script lo rechaza si empieza con `@` o `u/`).
- **`--resumen`:** 3 líneas como máximo. Parafrasea; una cita textual va breve y sin quién la escribió.
- **`--mercados`, `--idiomas`, `--tiendas`:** la cobertura que aporta la fuente, con las etiquetas del objetivo ([investigacion.md](investigacion.md) · Cobertura).
- **`--tipo oficial`** lleva `--version "<versión o fecha de la última actualización>"` o una `--publicada` real: así se sabe qué versión leíste. Un blog o una nota de prensa que resume una política es `terceros`, no `oficial`.
- **`--acumulado`** (solo con `--tipo medido`): el dato es acumulado desde el lanzamiento (descargas totales, valoraciones históricas). En la línea demanda es **contexto, no una señal actual**: no cuenta para la confianza ni para triangular un hallazgo de demanda ([puntaje.md](puntaje.md)). En otras líneas cuenta como siempre.
- **`--archivo` en vez de `--url`:** un CSV de reseñas que aportó el usuario. Lleva `--autor` (la app y la tienda de esas reseñas), que es lo que la hace independiente de otra.

La misma URL (o el mismo archivo) no se registra dos veces en una línea. Si un dato lo aporta el usuario desde una herramienta de pago suya, la fuente es la página pública de esa herramienta, o el CSV que exportó, y el resumen dice que lo aportó el usuario.

## Registrar un hallazgo

```bash
python3 -I <skill>/scripts/producto.py hallazgo --linea demanda --texto "La gente busca cómo repartir el riego en vacaciones" \
  --fuentes S-DEM-1,S-DEM-2,S-DEM-3 --critico --sin-contra "Busqué «apps de riego compartido cerradas»: sin resultados"
```

- **`--critico`** marca un **hallazgo clave**: uno del que dependen el puntaje o una puerta. Solo los clave entran en `triangulacion` y en la confianza del puntaje, así que marca los que de verdad sostienen la decisión.
- **`--en-contra S-…`** registra las fuentes que lo contradicen; **`--sin-contra "<qué buscaste>"`**, que buscaste y no apareció nada. Un hallazgo clave necesita una de las dos.
- **`--competidores`** enlaza el hallazgo con filas de la matriz, por ID (`C-1`) o por nombre. Sirve para las quejas por competidor y para la viabilidad de un diferenciador.

Si te equivocas, `producto.py anular --id <ID> --motivo "<por qué>"` deja el registro sin borrarlo. No edites los `.json` a mano.

## Triangulación

Un hallazgo clave está triangulado cuando tiene **3 fuentes independientes y vigentes** y, si es de demanda o de monetización, al menos una de tipo `medido`.

- **Independientes:** de autor distinto. Sin `--autor`, cuenta el dominio: tres páginas del mismo sitio son una sola fuente. Dos páginas de un mismo dominio cuentan por separado solo si sus autores son distintos (las fichas de dos apps en la misma tienda, dos medios en la misma plataforma).
- **Vigentes:** publicadas dentro de la ventana (`vigencia_meses`, 18 por defecto). Una fuente sin fecha o fuera de la ventana no cuenta, y se nombra en lo que le falta al hallazgo.
- **En una idea nueva** se triangula el peldaño más cercano a lo directo que tenga evidencia: el problema o el análogo, no la solución exacta.
- **En políticas, la norma misma basta.** Un hallazgo de la línea `politicas` con una fuente `oficial` y vigente queda triangulado (y con confianza alta) aunque sea la única: es la fuente primaria. Una fuente oficial rige mientras no la reemplacen, así que cuenta como vigente si la **consultaste** dentro de la ventana, aunque se haya publicado antes. Fuera de políticas, una fuente oficial cuenta como cualquier otra.
- **En demanda, los datos acumulados no cuentan** (`--acumulado`): la triangulación pide señales actuales.

`producto.py triangulacion` lista cada hallazgo clave: ✔ si cumple esta regla, y lo que le falta si no. La búsqueda de evidencia en contra es otra regla (la del abogado del diablo) y se lista aparte, sin cambiar la marca. Si no lo consigues dentro del presupuesto, el hallazgo se queda con su confianza real y la síntesis lo dice.

## Confianza

La calcula el script; tú no la escribes. **Usa la misma regla de vigencia que la triangulación**: solo cuentan las fuentes vigentes. Una fuente sin fecha o fuera de la ventana tiene un peso menor declarado: no sube la confianza ni ayuda a triangular, y un hallazgo que solo tiene fuentes así queda en baja. Por eso la confianza se escribe siempre con su triangulación, como la imprime el script: "confianza media · sin triangular". Una confianza media nunca se presenta como si el hallazgo estuviera confirmado.

| Confianza | Cuándo |
| --- | --- |
| Alta | Triangulado, y al menos 2 de sus fuentes independientes no son `opinion`; en políticas, también con una sola fuente `oficial`. Sin triangular nunca es alta |
| Media | 2 fuentes independientes y vigentes (al menos una que no sea `opinion`), o 3 que no alcanzan lo anterior |
| Baja | 1 fuente vigente, 2 que son solo opinión, o ninguna vigente |
| Sin evidencia | Ningún hallazgo sostiene la afirmación |

Después se aplican tres límites:

1. **El peldaño:** 1 y 2 llegan hasta alta; 3, 4 y 5, hasta media; 6, hasta baja. El script elige el grupo de fuentes que da la mejor confianza: sumar una fuente de un peldaño lejano nunca la baja.
2. **La evidencia en contra:** una fuente vigente en contra baja un nivel; si hay tantas en contra como a favor, queda en baja.
3. **Tu criterio, solo hacia abajo:** `producto.py confianza --hallazgo H-… --bajar <media|baja> --motivo "<por qué>"`. Subirla no existe.

## Sesgos que hay que nombrar

Cuando uno aplica, se escribe en el entregable junto al hallazgo.

- **Supervivencia:** solo se ven las apps que sobrevivieron. Las que cerraron no tienen ficha ni reseñas: hay que buscarlas aparte.
- **Negatividad de las reseñas:** las de 1 a 3★ exageran los dolores. Sirven para encontrarlos, no para medir su tamaño.
- **Geografía e idioma:** lo que vale en un mercado no vale en otro. Cada dato dice de qué mercado es.
- **Confirmación:** buscar solo lo que da la razón a la idea. Lo contrarresta la regla del abogado del diablo.
- **Falsa analogía:** un análogo puede tener tracción por razones que la idea no comparte. Cada analogía dice en qué se parece y en qué no.
- **Diferenciador imaginario:** algo que le importa a quien crea la app, pero que ningún usuario pidió. Lo filtra el primer criterio de viabilidad de [diferenciacion.md](diferenciacion.md).

## Privacidad y legalidad

- Nada de nombres de usuario, fotos, enlaces a perfiles ni datos personales de quienes opinan, ni en el registro ni en los entregables. Un CSV de reseñas se lee con `producto.py resenas`, que nunca muestra las columnas de autor.
- Solo páginas públicas y dentro de sus términos de uso. Sin scraping masivo, sin saltar muros de pago ni inicios de sesión.
- De la competencia se registran hechos (precio, tamaño, idiomas, quejas), nunca sus textos, íconos ni capturas.
