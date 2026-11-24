# Evidencia: fuentes, triangulación, confianza y sesgos

Vale para todas las sesiones. La regla es **evidencia o nada**: lo que no tiene una fuente registrada va en el texto como **⚠ Sin evidencia**, y nunca entra al registro.

## Registrar una fuente

```bash
python3 -I <skill>/scripts/producto.py fuente --linea demanda --url https://ejemplo.example/informe \
  --publicada 2026-05 --tipo medido --peldano 1 --autor "Medio de ejemplo" \
  --resumen "Qué dice, en 3 líneas como máximo, con el dato y su unidad."
```

Devuelve el ID (`S-DEM-1`). Los códigos por línea: `COM` competencia, `VOZ` voz del usuario, `DEM` demanda, `MON` monetización, `POL` políticas, `DIF` diferenciación, `EST` estrategia y `VAL` validación. Cada sesión registra **solo en su línea**; puede citar fuentes de otra.

- **`--publicada`:** `AAAA-MM-DD`, `AAAA-MM` o `sin-fecha`. Una fuente sin fecha o fuera de la ventana no cuenta para triangular. Para un dato vivo (la ficha de una tienda, un contador), la fecha es la del día en que lo leíste.
- **`--tipo`:**

| Tipo | Qué es | Ejemplos |
| --- | --- | --- |
| `medido` | Un número que alguien midió y publicó | Descargas y nota de una ficha, volumen de búsqueda, estadísticas oficiales, un reporte con metodología |
| `usuario` | Lo que dice quien usa el producto o tiene el problema | Reseñas, hilos de foros, comentarios |
| `terceros` | Análisis de alguien que no es usuario ni dueño | Prensa, comparativas, documentación oficial de una plataforma |
| `opinion` | Una opinión sin datos | Una columna, un hilo de recomendaciones, la página de ventas de un competidor |

- **`--peldano`:** de 1 a 6, según la escalera de [analogia.md](analogia.md). En una idea con competencia casi todo es 1.
- **`--autor`:** la app, la empresa o el medio que publica. **Nunca un nombre de usuario** (el script lo rechaza si empieza con `@` o `u/`).
- **`--resumen`:** 3 líneas como máximo. Parafrasea; una cita textual va breve y sin quién la escribió.

La misma URL no se registra dos veces en una línea. Si un dato lo aporta el usuario desde una herramienta de pago suya, la fuente es la página pública de esa herramienta y el resumen dice que el dato lo aportó el usuario: 0.1.0 trabaja solo con la web pública.

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
- **Vigentes:** publicadas dentro de la ventana (`vigencia_meses`, 18 por defecto).
- **En una idea nueva** se triangula el peldaño más cercano a lo directo que tenga evidencia: el problema o el análogo, no la solución exacta.

`producto.py triangulacion` lista cada hallazgo clave y lo que le falta. Si no lo consigues dentro del presupuesto, el hallazgo se queda con su confianza real y la síntesis lo dice.

## Confianza

La calcula el script; tú no la escribes.

| Confianza | Cuándo |
| --- | --- |
| Alta | Triangulado, y al menos 2 de sus fuentes independientes no son `opinion` |
| Media | 2 fuentes independientes y vigentes (al menos una que no sea `opinion`), o 3 que no alcanzan lo anterior |
| Baja | 1 fuente, 2 que son solo opinión, o ninguna vigente |
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

- Nada de nombres de usuario, fotos, enlaces a perfiles ni datos personales de quienes opinan, ni en el registro ni en los entregables.
- Solo páginas públicas y dentro de sus términos de uso. Sin scraping masivo, sin saltar muros de pago ni inicios de sesión.
- De la competencia se registran hechos (precio, tamaño, idiomas, quejas), nunca sus textos, íconos ni capturas.
