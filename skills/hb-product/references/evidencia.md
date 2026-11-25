# Evidencia: fuentes, triangulación, confianza y sesgos

Vale para todas las sesiones. La regla es **evidencia o nada**: lo que no tiene una fuente registrada va en el texto como **⚠ Sin evidencia**, y nunca entra al registro.

## Registrar una fuente

```bash
python3 -I <skill>/scripts/producto.py fuente --linea demanda --url https://ejemplo.example/informe \
  --publicada 2026-05 --tipo medido --peldano 1 --autor "Medio de ejemplo" \
  --resumen "Qué dice, en 3 líneas como máximo, con el dato y su unidad."
```

Devuelve el ID (`S-DEM-1`). Los códigos por línea: `COM` competencia, `VOZ` voz del usuario, `DEM` demanda, `MON` monetización, `POL` políticas, `DIF` diferenciación, `EST` estrategia y `VAL` validación. Cada sesión registra **solo en su línea**; puede citar fuentes de otra.

- **`--publicada`:** la **fecha real de publicación**, `AAAA-MM-DD`, `AAAA-MM` o, si solo se sabe el año, `AAAA` (cuenta desde el 1 de enero, la fecha más antigua posible, y queda como fecha aproximada), o `desconocida` si de verdad no aparece (con `--archivo`, también `auto`; `sin-fecha` es el nombre anterior de `desconocida`). Una fuente sin fecha o fuera de la ventana no es vigente: no cuenta para triangular ni para la confianza (abajo).
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
- **`--editor "<nombre>"` o `--editor C-…`:** la fuente es lo que publica el editor de un producto sobre sí mismo: su web, su nota de prensa, su blog, su página de ventas o su ficha. Todas las fuentes de un mismo editor cuentan como **un solo autor** (abajo, Triangulación). Úsalo cuando el script no lo puede ver solo: la web o la nota de prensa de una app (pasa la fila de la matriz, `C-…`, o el nombre de la empresa, siempre escrito igual). La ficha de una tienda no lo necesita: la misma app en la URL (`id=` de Google Play, `/id<n>` de App Store) ya la junta con su ficha en otro país y con su etiqueta de privacidad, y la fila de la matriz junta su ficha de Google Play con la de App Store. No va con reseñas de usuarios (`--tipo usuario` o un CSV). En una fuente ya registrada, repite `fuente` con la misma URL y `--editor`; uno distinto no pisa el que tiene.
- **`--resumen`:** 3 líneas como máximo. Parafrasea; una cita textual va breve y sin quién la escribió.
- **`--mercados`, `--idiomas`, `--tiendas`:** la cobertura que aporta la fuente, con las etiquetas del objetivo ([investigacion.md](investigacion.md) · Cobertura).
- **`--tipo oficial`** lleva `--version "<versión o fecha de la última actualización>"` o una `--publicada` real: así se sabe qué versión leíste. Un blog o una nota de prensa que resume una política es `terceros`, no `oficial`.
- **`--clase estadistica|academica`:** la vigencia larga de los datos estructurales (abajo, Triangulación). `estadistica` es un censo o una encuesta nacional de un organismo oficial; `academica`, un estudio académico (un artículo, una tesis, un informe con metodología). Una edición nueva de una estadística lleva `--reemplaza <S-…>` con la anterior.
- **Completar una fuente.** Si registraste una fuente con `--publicada desconocida` y después encuentras su fecha (o solo el año), o le falta la clase, repite `fuente` con la misma URL: completa lo que falta, sin pisar lo que ya tiene. Para sumarle un mercado, un idioma o una tienda basta la URL y lo que agregas (`fuente --linea … --url <la misma> --mercados AR`): `--publicada`, `--tipo`, `--peldano` y `--resumen` solo son obligatorios en una fuente nueva.
- **`--acumulado`** (solo con `--tipo medido`): el dato es acumulado desde el lanzamiento (descargas totales, valoraciones históricas). En la línea demanda es **contexto, no una señal actual**: no cuenta para la confianza ni para triangular un hallazgo de demanda ([puntaje.md](puntaje.md)). En otras líneas cuenta como siempre.
- **`--extracto`:** lo viste solo en el extracto de un resultado de búsqueda, sin abrir la página. No cuenta como lectura del presupuesto y queda marcado ("extracto de búsqueda") en el registro, en `triangulacion` y en el reporte, pero para la confianza y la triangulación cuenta como cualquier fuente: vale para un dato puntual y verificable en el extracto (una cifra con su fecha, el precio de una ficha), no para una reseña, una opinión o una política; si hace falta el contexto, abre la página ([investigacion.md](investigacion.md) · Extractos de búsqueda). Repetir `fuente` con la misma URL y sin `--extracto` la pasa a leída, y su resumen pasa a ser el nuevo (lo que dice la página).
- **`--misma-lectura S-…`:** la fuente sale de la misma lectura que otra de tu línea (una API pública que devuelve las fichas de varios mercados de una vez, un listado con varias apps). Juntas cuentan como **una** lectura del presupuesto; para la independencia y la confianza, cada una sigue contando por su autor, su dominio o su editor, como siempre.
- **`--archivo` en vez de `--url`:** un CSV de reseñas que aportó el usuario. Lleva `--autor` (la app y la tienda de esas reseñas), que es lo que la hace independiente de otra.

La misma URL (o el mismo archivo) no se registra dos veces en una línea. Si un dato lo aporta el usuario desde una herramienta de pago suya, la fuente es la página pública de esa herramienta, o el CSV que exportó, y el resumen dice que lo aportó el usuario.

## Registrar un hallazgo

```bash
python3 -I <skill>/scripts/producto.py hallazgo --linea demanda --texto "La gente busca cómo repartir el riego en vacaciones" \
  --fuentes S-DEM-1,S-DEM-2,S-DEM-3 --critico --sin-contra "Busqué «apps de riego compartido cerradas»: sin resultados"
```

- **`--critico`** marca un **hallazgo clave**: uno del que dependen el puntaje o una puerta. Solo los clave entran en `triangulacion` y en la confianza del puntaje, así que marca los que de verdad sostienen la decisión.
- **`--en-contra S-…`** registra las fuentes que lo contradicen; **`--sin-contra "<qué buscaste>"`**, que buscaste y no apareció nada. Un hallazgo clave necesita una de las dos.
- **`--competidor C-1,C-3`** (o `--competidores`) enlaza el hallazgo con filas de la matriz **por su ID**. Sin fila todavía, por la URL de su ficha; un nombre que ya tiene fila se guarda como su ID. Un nombre que no coincide con la matriz se enlaza por la URL de la ficha si una fuente del hallazgo es esa ficha; si no, `matriz` lo avisa. Sirve para las quejas por competidor y para la viabilidad de un diferenciador.

- **Sumar fuentes a un hallazgo ya registrado:** `producto.py hallazgo --id H-… --fuentes S-4,S-5` las agrega (nunca quita), conserva el ID, el texto y lo demás, y recalcula la confianza con la regla de siempre. Como cambia la confianza, pide la **sesión dueña del hallazgo abierta**: con ella cerrada, sumar evidencia cambiaría lo que la puerta evalúa sin pasar por ella, así que va como `propuesta --ajustar <sesión>`. Enlazar competidores (`--id H-… --competidor C-…`) no cambia la confianza y sí vale con la sesión cerrada.
- **Sumar evidencia en contra después:** `producto.py hallazgo --id H-… --en-contra S-…`, con la misma regla: mismo ID, la confianza se recalcula (la evidencia en contra le baja un nivel; tantas en contra como a favor lo refutan, y lo avisa), pide la sesión dueña abierta y una fuente no puede estar a favor y en contra a la vez.
- **Fortalecer un hallazgo de una sesión cerrada desde la que se reabrió:** `producto.py hallazgo --linea <tu línea> --reune H-… --fuentes <las nuevas> --texto "…"` registra uno nuevo que lleva las fuentes a favor y en contra del original y sigue también sus reglas de triangulación (las de su línea), y se cita en su lugar. Es el camino que da la puerta cuando pide triangular un hallazgo de otra sesión ([validacion.md](validacion.md)).
- **Citar a mano las fuentes de otra línea no esquiva sus reglas:** un hallazgo con la mitad o más de sus fuentes de la demanda, la monetización o las políticas sigue también las reglas de esa línea (una fuente medida; en la demanda, los datos acumulados no cuentan; en políticas, una oficial basta). Y si sus fuentes son las de un hallazgo ya registrado de otra línea (todas las de ese hallazgo, y al menos la mitad de las suyas), `hallazgo` lo reúne aunque no pases `--reune`: lleva lo que tiene en contra, su confianza bajada a mano, sus competidores y sus reglas, y lo dice al registrarlo.

Si te equivocas, `producto.py anular --id <ID> --motivo "<por qué>"` deja el registro sin borrarlo. No edites los `.json` a mano.

## Triangulación

Un hallazgo clave está triangulado cuando tiene **3 fuentes independientes y vigentes** y, si es de demanda o de monetización, al menos una de tipo `medido`.

- **Independientes:** de autor distinto. Sin `--autor`, cuenta el dominio: tres páginas del mismo sitio son una sola fuente. Dos páginas de un mismo dominio cuentan por separado solo si sus autores son distintos (las fichas de dos apps en la misma tienda, dos medios en la misma plataforma).
- **Un producto que habla de sí mismo es un solo autor: su editor.** Su ficha en cada tienda y en cada país, su etiqueta de privacidad (o de seguridad de los datos), su web, su blog y su nota de prensa repiten lo que dice el editor, aunque el `--autor` se escriba distinto o el dominio cambie. El script las junta cuando lo puede ver de forma determinista: la misma app en la URL de la tienda (`id=` de Google Play, `/id<n>` de App Store o el `id=` de una sola app en su API pública, `itunes.apple.com/lookup`, en cualquier país), la fila de la matriz que cita sus fichas (si es una sola app por tienda: una fila que agrupa varias apps no junta nada) y `fuente --editor`. Solo junta, nunca separa: dos fuentes que ya eran del mismo autor o dominio siguen siendo una. `hallazgo` y `triangulacion` dicen qué fuentes juntó y por qué editor.
- **Las reseñas de usuarios no son el editor.** Una fuente `--tipo usuario` (las reseñas de una ficha, un hilo, un CSV) no se junta con la ficha ni con lo que publica el editor, aunque se lea en la misma página: son la voz de sus usuarios y cuentan por su `--autor`, como siempre. Por eso las reseñas se registran aparte de la ficha y con `--tipo usuario`: una sola fuente que mezcla la ficha y sus reseñas con otro tipo cuenta como del editor.
- **Vigentes:** publicadas dentro de su ventana, según el tipo de fuente. Una fuente sin fecha o fuera de su ventana no cuenta, y se nombra en lo que le falta al hallazgo.

| Tipo de fuente | Vigente |
| --- | --- |
| Estadística oficial (`--clase estadistica`): censos, encuestas nacionales | Hasta que sale una edición más nueva (`--reemplaza`), con un máximo de 5 años (`vigencia_larga_meses`, 60) |
| Estudio académico (`--clase academica`) | 5 años desde su publicación |
| Norma (`--tipo oficial`): la política de una tienda, una ley | Mientras no la reemplacen: cuenta la fecha en que la consultaste |
| Todo lo demás: reseñas, tiendas, prensa, tráfico, precios | 18 meses (`vigencia_meses`) |

- **Una reciente.** De las 3 fuentes de un hallazgo clave, al menos una tiene que ser de los últimos 18 meses: los datos estructurales sostienen la necesidad de fondo, pero no muestran por sí solos que siga hoy.
- **En una idea nueva** se triangula el peldaño más cercano a lo directo que tenga evidencia: el problema o el análogo, no la solución exacta.
- **En políticas, la norma misma basta.** Un hallazgo de la línea `politicas` con una fuente `oficial` y vigente queda triangulado (y con confianza alta) aunque sea la única: es la fuente primaria. Una fuente oficial rige mientras no la reemplacen, así que cuenta como vigente si la **consultaste** dentro de la ventana, aunque se haya publicado antes. Fuera de políticas, una fuente oficial cuenta como cualquier otra.
- **En demanda, los datos acumulados no cuentan** (`--acumulado`): la triangulación pide señales actuales.

`producto.py triangulacion` lista cada hallazgo clave: ✔ si cumple esta regla, y lo que le falta si no. La búsqueda de evidencia en contra es otra regla (la del abogado del diablo) y se lista aparte, sin cambiar la marca. Si no lo consigues dentro del presupuesto, el hallazgo se queda con su confianza real y la síntesis lo dice.

## Confianza

La calcula el script; tú no la escribes. **Usa la misma regla de vigencia que la triangulación**: solo cuentan las fuentes vigentes. Una fuente sin fecha o fuera de la ventana tiene un peso menor declarado: no sube la confianza ni ayuda a triangular, y un hallazgo que solo tiene fuentes así queda en baja. Por eso la confianza se escribe siempre con su triangulación, como la imprime el script: "confianza media · sin triangular". Una confianza media nunca se presenta como si el hallazgo estuviera confirmado.

| Confianza | Cuándo |
| --- | --- |
| Alta | Triangulado (con una fuente reciente), y al menos 2 de sus fuentes independientes no son `opinion`; en políticas, también con una sola fuente `oficial`. Sin triangular nunca es alta |
| Media | 2 fuentes independientes y vigentes (al menos una que no sea `opinion`), o 3 que no alcanzan lo anterior |
| Baja | 1 fuente vigente, 2 que son solo opinión, o ninguna vigente |
| Sin evidencia | Ningún hallazgo sostiene la afirmación |

Después se aplican tres límites:

1. **El peldaño:** 1 y 2 llegan hasta alta; 3, 4 y 5, hasta media; 6, hasta baja. El script elige el grupo de fuentes que da la mejor confianza: sumar una fuente de un peldaño lejano nunca la baja.
2. **La evidencia en contra:** una fuente vigente en contra baja un nivel; si hay tantas en contra como a favor, queda en baja.
3. **Tu criterio, solo hacia abajo:** `producto.py confianza --hallazgo H-… --bajar <media|baja> --motivo "<por qué>"`. Subirla no existe.

Un hallazgo triangulado puede seguir en baja o en media por uno de esos límites, o por tener solo opinión. `triangulacion` lo dice debajo del hallazgo (`↑ triangulado, pero para subir a confianza media: …`), y a uno sin triangular le suma lo que triangular no resuelve (`↑ además de triangular, …`, por ejemplo un peldaño 6). «Qué cambiaría» de la puerta usa la misma regla: a un hallazgo ya triangulado no le pide triangular, sino lo que de verdad le falta (fuentes de un peldaño más cercano, fuentes que no sean solo opinión, más fuentes a favor que en contra). Los extractos de búsqueda cuentan para la confianza como cualquier fuente, así que no aparecen en esa lista.

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
