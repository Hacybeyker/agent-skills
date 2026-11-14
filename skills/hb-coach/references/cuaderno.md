# Cuaderno: archivos, formatos y herramienta

Todo lo que el coach escribe en `aprendizaje/` y cómo se convierte en `cuaderno.html`.

## Contenido

1. Estructura y propósito de cada archivo
2. Herramienta `coach`
3. Nota de lección
4. Retos y preguntas
5. Nota de examen y de repaso
6. Diagramas Mermaid
7. Código, avisos y tablas
8. METODO, GLOSARIO, DUDAS y MAPA
9. Lo que revisa `check`
10. Enlaces e imágenes
11. Modo manual (sin ejecutar comandos)
12. Sin conexión y refresco automático
13. Desde hb-coach 3.0
14. Solución de problemas

## 1. Estructura y propósito de cada archivo

```text
aprendizaje/                      ← raíz (en un proyecto, excluida de git con .git/info/exclude)
├── README.md                     ← guía corta para el estudiante (la crea init)
├── METODO.md                     ← acuerdo de método
├── cuaderno.html                 ← generado: NO editar a mano
├── .cuaderno-version.js          ← generado: el «latido» con el que la página se actualiza sola
├── .vendor/                      ← opcional: librerías para usarlo sin conexión
├── .respaldos/                   ← copias que deja `coach migrar`
└── <slug>/
    ├── PLAN.md                   ← módulos con examen, progreso, huecos y bitácora
    ├── MAPA.md                   ← opcional: mapa del tema (init --mapa)
    ├── GLOSARIO.md · DUDAS.md
    ├── lecciones/<id>-<slug>.md  ← una nota por lección
    ├── examenes/m<n>-<slug>.md   ← una nota por examen de módulo
    ├── repasos/<AAAA-MM-DD>.md   ← la nota de cada repaso guiado (la crea coach repaso)
    ├── practica/                 ← opcional: material de práctica (datos, scripts); no entra en el cuaderno
    ├── img/                      ← opcional: imágenes de las notas
    └── *.md                      ← opcional: otros documentos (chuletas, casos)
```

El cuaderno lee **todos** los `.md` (menos los ocultos y los de `practica/`, `node_modules/`, `build/` y carpetas de herramientas parecidas), así que cualquier documento extra del tema aparece en su menú.

## 2. Herramienta `coach`

Ejecuta `python3 <skill>/scripts/coach.py <comando>` desde la raíz del proyecto o con `--root <carpeta>`. `coach ayuda` lista todo.

| Comando | Efecto |
|---|---|
| `siguiente [slug] [--json]` | Decide el paso: método pendiente → plan sin terminar → repasos vencidos (si hoy aún no se hicieron 6) → examen que toca (uno suspendido, cuando sus huecos llevan un repaso bien) → lección actual → proyecto final. En una lección dice el bloque (n de N), qué espera (el intento de un reto, unas respuestas, un segundo intento, la lectura) o qué bloque escribir, qué líneas de la nota leer y el enlace al bloque; si antes toca un repaso, lo de la lección va en «Después». Imprime la meta de hoy, los comandos exactos (con `--root` si hace falta), qué leer y, si no encuentra temas, si los hay en `~/aprendizaje`. |
| `init <slug> --tema "…" [--area A] [--nivel-objetivo N] [--playground URL] [--mapa]` | Crea el tema desde las plantillas, `README.md` y `METODO.md` si faltan, y excluye la carpeta de git (`--versionar` no la excluye; `--gitignore` usa `.gitignore`; `--force` reemplaza un PLAN.md). |
| `metodo [--<clave> "valor" …] [--motivo "…"]` | Sin claves, muestra el acuerdo y no escribe nada (si aún no existe, enseña los valores de partida). Con claves, lo guarda: si falta, crea la carpeta y `METODO.md` y la excluye de git, así que funciona antes de `init`. Claves: `orden`, `pasos`, `preguntas`, `prediccion`, `correccion`, `mensajes`, `ejemplos`, `practica`, `verificacion`, `ritmo`, `profundidad`, `calentamiento`, `repasos`, `idioma`; actualiza las filas y anota el cambio con su fecha. |
| `bloque <slug> <id> [n] [--forzar]` | Escribe el bloque n entero antes del cierre de la nota (§3) y, si trae `## Objetivos`, reemplaza esa sección. Crea la nota si falta (como `leccion`) y quita las secciones de la plantilla de la 3.0 sin rellenar. Pone el número del bloque (y su emoji) en los encabezados que no lo traen. Se niega si el bloque ya existe o no es el siguiente, si trae una sección `##` que no sea de bloque, un ❓ sin preguntas, una pregunta con un número ya usado, una solución o un intento, o si el anterior tiene algo pendiente (con `--forzar`, lo pendiente queda aplazado). Imprime el enlace al bloque y qué espera. |
| `corregir <slug> <id\|Mn\|repaso> [--reto k] [--historial "…"]` | Anota en su sitio lo que llega por stdin (§4): cada pieza que empieza por `**Pn.**` va a su pregunta (la respuesta, en la línea de la pregunta si es de una línea; si no, en un párrafo «Tu respuesta»; el resto, debajo); lo demás va al final del reto pendiente (`--reto k` elige otro) o, en un examen, a «Tarea práctica». Se niega a escribir una solución sin el intento. Imprime el estado del bloque y el siguiente paso (otro intento, las preguntas, el bloque siguiente o el cierre). |
| `leccion <slug> <id>` | Crea `lecciones/<id>-<título>.md`, fija `leccion_actual` y pone la nota en `en-curso`. Se niega si la ruta aún tiene marcadores. Si la lección estaba hecha, la abre como repaso. `bloque` ya lo hace. |
| `nota <slug> <id\|Mn\|repaso> …` | Inserta el Markdown (stdin o `--desde`) antes del cierre de la nota (Resumen con tus palabras, Fuentes, Historial; en un examen, antes de Tarea práctica). Las partes que empiezan por `## Objetivos`, `## Resumen con tus palabras`, `## Fuentes`, `## Tarea práctica` o `## Resultado` reemplazan esa sección. Con `--seccion objetivos\|resumen\|fuentes\|tarea`, el texto (sin encabezado) reemplaza esa sección. `--historial "texto"` añade una fila fechada. Se niega a escribir una solución o una respuesta completa sin el intento, y un bloque 📖/🛠/❓ en una lección (eso es `bloque`), salvo `--forzar`. Avisa al momento de líneas de código largas y etiquetas Mermaid ilegibles. |
| `glosario <slug> "T" "Def" […] [--leccion id]` | Inserta cada término en orden alfabético (o actualiza su definición) con enlace a la nota de la lección (por defecto, la actual). |
| `duda <slug> "Pregunta" --respuesta "…" [--contexto] [--explicacion] [--leccion] [--fuente]` | Añade la duda arriba de `DUDAS.md`. |
| `hueco <slug> "Descripción" [--leccion id \| --examen n] [--intentos n]` | Abre un hueco (`H1`, `H2`…) con su primer repaso mañana. `Intentos` empieza en 2 (se abre tras el segundo fallo); con `--examen n` queda atribuido al examen y empieza en 1. |
| `hueco <slug> Hn --bien\|--mal\|--cerrar` | Reprograma el hueco según el calendario o lo cierra (`repaso <slug> Hn` hace lo mismo con `--bien` o `--mal`). |
| `completar <slug> <id> [--convalidada] [--forzar]` | Marca `[x]`, avanza `leccion_actual`, pone `estado`, `fin` y el primer repaso en la nota, y avisa si toca examen. Se niega si la nota tiene `[[COMPLETAR]]`, si «Resumen con tus palabras» o «Fuentes» faltan o están vacías, si un bloque aún espera algo, si queda algo aplazado o si faltan bloques del mapa (`--forzar` lo salta). |
| `reabrir <slug> <id>` | Vuelve a `[ ]`, quita `(convalidada)` y anula el repaso programado. |
| `repaso <slug> [--json]` | Lo que vence hoy (huecos primero, luego lecciones), mezclado entre módulos, con las preguntas de cada nota, y crea la nota del repaso del día (`repasos/<fecha>.md`, §5). Como mucho 6 al día: el resto queda para otro día. |
| `repaso <slug> <id\|Hn> --bien\|--mal` | Registra el repaso de una lección (o hueco) y lo reprograma; lo anota en el Historial de la nota y en el de la nota del repaso del día. |
| `examen <slug> <n>` | Añade la línea del examen al plan si falta y crea `examenes/m<n>-….md` con lo que cubre. |
| `examen <slug> <n> --resultado a/t --tarea si\|no` | Marca el examen como aprobado (≥ 80 % y la tarea hecha) o «repetir», y escribe el resultado en la nota. `--tarea` es obligatorio. |
| `sesion <slug> --logros "…" [--lecciones "…"] [--siguiente "…"]` | Añade la fila de bitácora (el próximo paso, por defecto, el de `siguiente`), regenera el cuaderno, ejecuta `check` y muestra el siguiente paso. |
| `estado [slug] [--json]` | Progreso, exámenes, repasos y huecos; con un slug, todas las lecciones. |
| `build` · `check [slug]` · `vendor [--force]` · `migrar [--dry-run]` · `version` | Regenerar el cuaderno y su latido (§12); validar (§9); descargar librerías (§12); migrar desde 3.0 (§13). |

Los comandos que cambian algo regeneran el cuaderno (salvo con `--no-build`). Un argumento que empiece por `--` (un término de glosario como `--force`) va después de `--`: `coach glosario sql -- --force "…"`. Códigos de salida: 0 bien, 1 `check`/`vendor`/`sesion` con errores, 2 uso incorrecto (el mensaje dice cómo seguir).

**Contenido por stdin.** `bloque`, `corregir` y `nota` leen el Markdown de un heredoc (`<<'EOF'` … `EOF`, con comillas para que la shell no expanda nada) o de un archivo con `--desde`. Una llamada por momento: `bloque` abre cada bloque (el primero, con `## Objetivos`); `corregir`, cada respuesta del estudiante; `nota`, el cierre (`## Resumen con tus palabras` y `## Fuentes`). Los comandos de un mismo momento se encadenan con `&&`.

## 3. Nota de lección

`coach leccion` la crea desde la plantilla. Frontmatter (lo mantiene `coach`):

```yaml
---
leccion: "2.4"
titulo: "Módulos: @Provides y @Binds"
tema: hilt
modulo: "M2 · Primeros pasos con Hilt"
estado: completada           # en-curso | completada | convalidada
inicio: 2026-10-02
fin: 2026-10-03              # lo añade completar
repaso: 2026-10-06           # próximo repaso espaciado (lo calcula coach)
repasos: 0                   # repasos bien hechos
etiquetas: [di, kotlin]
---
```

Estructura, en este orden:

| Sección | Contenido |
|---|---|
| `## Objetivos` | `> **En una frase:** …`, «Al terminar podrás:» con 2 o 3 objetivos observables y el mapa de bloques (abajo). (En notas de 3.0 se llama `## Resumen`.) La plantilla trae el objetivo del plan; el primer `coach bloque` la reemplaza. |
| `## 📖 Teoría · <n>. <subtítulo>` | Explicación → ejemplo → desglose en viñetas → aviso; los tres ejemplos; diagrama si aporta. |
| `## 🛠 Práctica · <n>. <subtítulo>` | Uno o varios retos (§4); después de cada uno, su intento, el veredicto, la corrección y, al cerrarlo, la solución. |
| `## ❓ Preguntas · <n>. <subtítulo>` | Las preguntas; después de cada una, su respuesta con el veredicto y, al cerrarla, la respuesta completa (§4). |
| `## Resumen con tus palabras` | Su explicación, corregida si hacía falta. |
| `## Fuentes` | Enlaces con versión o fecha de consulta. |
| `## Historial` | Fechas, en qué pista se resolvió cada atasco, errores del coach y su corrección, huecos, repasos. |

**Mapa de bloques**, en `## Objetivos`: una línea `**Bloques:**` y una lista numerada con el título de cada bloque en negrita. El cuaderno lo usa para mostrar «🔒 Pendiente» los bloques aún sin escribir, y `siguiente`, para saber cuántos quedan (en las notas de la 3.1, el mapa en una sola línea también vale).

```markdown
**Bloques:**

1. **Exponente cero y negativos** — 📖 → 🛠 reto de 5 ejercicios → ❓ 2 preguntas
2. **Raíces como exponentes fraccionarios** — 📖 → 🛠 reto de la textura
3. **Notación científica** — 📖 → 🛠 → ❓ comprobación de dominio
```

**Estado de un bloque.** No se guarda aparte: se deduce de la nota, así que vale igual para el modo manual y para notas antiguas. Un reto está cerrado cuando tiene su «Solución» (o un intento con ✔ y sin ✘); una pregunta, cuando tiene su respuesta completa (o una respuesta con ✔ y sin ✘). Un bloque termina cuando todo lo suyo está cerrado; uno solo de teoría espera la lectura. Una práctica sin `### Reto` (las de la 3.0) se da por hecha cuando «Lo que observaste» tiene contenido.

Reglas: escribe la nota **durante** la lección, bloque a bloque (`coach bloque` y `coach corregir`); numera los bloques en los subtítulos (`· 1.`); marca los supuestos («**Supuesto** (no lo hagas): …»); mantén la línea `# <id> · <título>` (el cuaderno la oculta); nombre de archivo `<id>-<slug-del-título>.md`. Lo que no es para el estudiante (comentarios `<!-- -->`, marcadores `[[COMPLETAR]]`, secciones vacías) nunca se muestra en el cuaderno.

## 4. Retos y preguntas

**Reto** (dentro de un bloque 🛠). Se escribe en dos tiempos: el enunciado al abrir el bloque y su intento con la corrección después. El cuaderno lo muestra como tarjeta «Reto n de N» con su estado (sin resolver, segundo intento, resuelto, con solución o aplazado) y revela las pistas de una en una.

Al abrir el bloque (`coach bloque`), **sin solución**:

````markdown
### 🧩 Reto 1 · Dos columnas

Escribe una consulta que devuelva solo el título y el año de cada videojuego.

**Resultado esperado**

```text
title             | year
The Legend of Zed | 1986
```

<details>
<summary>Pista 1</summary>

Empieza por `SELECT` y separa las columnas con comas.

</details>
````

Cuando responde (`coach corregir`), su intento tal cual, el veredicto por ítem y la corrección; la solución, solo al cerrarlo (✔, o tras el segundo intento):

````markdown
**Tu intento:** `SELECT title year FROM videojuegos;`

**Veredicto:** ✘ falta la coma entre las columnas.

**Corrección:** sin la coma, SQL lee `year` como un alias de `title`. Abre la Pista 1 y vuelve a intentarlo.
````

````markdown
**Segundo intento:** `SELECT title, year FROM videojuegos;` · **Veredicto:** ✔ resuelto con la pista 1

<details>
<summary>Solución</summary>

```sql
SELECT title, year FROM videojuegos;
```

</details>

**Para ampliar:** el orden de las columnas en `SELECT` es el del resultado.
````

- **Etiquetas en español**, sea cual sea el idioma del curso: «Tu intento», «Segundo intento», «Veredicto», «Corrección», «Pista», «Solución», «tu respuesta», «Respuesta completa», «Para ampliar» y «Aplazado». El contenido va en el idioma del curso; el script y el cuaderno reconocen la estructura por esas etiquetas.
- Cualquier `<details>` cuyo resumen hable de solución o respuesta (también «Ver solución», «Answer») es una solución: `bloque` no lo deja pasar. Las pistas empiezan por «Pista».
- Las preguntas `**Pn.**` se numeran a lo largo de toda la lección (P1, P2 en el bloque 1; P3… en el 2): `bloque` rechaza un número repetido.
- Un ✘ en el primer intento lleva la pista, no la solución: `corregir` se niega (salvo `--forzar`, si de verdad ya no hay segundo intento).
- **Resultado esperado:** lo observable que dice que terminó (una salida, un número de tests, una frase, los puntos de una rúbrica). Si la respuesta es el propio cálculo, describe su forma («cinco fracciones irreducibles»), no los valores.
- **Veredicto:** ✔ resuelto (en qué pista) o ✘ con la idea que falló; en un reto de varios ítems, por ítem («4/5 ✔ · ✘ en el 3»). Sin veredicto, el reto cuenta como «sin resolver».
- Un reto de refuerzo tras un segundo fallo puede ir dentro del bloque ❓ en curso (`coach nota`).
- Si se aplaza, `coach bloque --forzar` abre el siguiente y marca lo pendiente con «**Aplazado:** fecha»: deja de bloquear el paso, pero `completar` lo recuerda. Para anotarlo más tarde, `coach corregir --reto k`.

**Pregunta y respuesta** (bloque ❓, examen y repaso). Al abrir el bloque, solo la pregunta:

```markdown
**P2.** ¿Por qué `@Binds` exige una función abstracta?
```

Cuando responde, una pieza por pregunta en `coach corregir`; la primera línea es su respuesta con el veredicto y lo demás va debajo:

```markdown
**P2.** tu respuesta: *«porque no crea el objeto»* ✔

<details>
<summary>Respuesta completa</summary>

`@Binds` no construye nada: solo le dice al grafo qué implementación usar para una interfaz.

</details>

**Para ampliar:** el método debe vivir en un módulo abstracto o en una interfaz.
```

En la nota queda `**P2.** ¿Por qué…? — tu respuesta: *«porque no crea el objeto»* ✔` y, debajo, la respuesta completa. Si la pregunta ocupa varias líneas (con código o una tabla), la respuesta va en un párrafo «**Tu respuesta:**» tras ella. Si falla: la pista, sin la respuesta completa; el segundo intento llega como `**P2.** segundo intento: *…* ✔` (queda `✘ → segundo intento: *…* ✔`) y entonces sí la respuesta completa. El cuaderno usa estas preguntas en el «Repaso de hoy»: lo anterior a « — tu respuesta» es la pregunta y el `<details>`, la respuesta. Deja una línea en blanco alrededor del contenido de cada `<details>`.

## 5. Nota de examen y de repaso

`coach examen <slug> <n>` crea `examenes/m<n>-<módulo>.md` con «Qué cubre», `## Preguntas`, `## Tarea práctica`, `## Resultado` y `## Historial`. Las preguntas entran juntas, sin respuestas, con `coach nota <slug> M<n>` (formato del §4); la tarea, con `--seccion tarea`. Sus respuestas se corrigen con `coach corregir <slug> M<n>` (lo que no empieza por `**Pn.**` va a la tarea) y el resultado lo escribe `coach examen … --resultado`. El frontmatter lleva `estado: pendiente | aprobado | repetir`, `resultado` y `fecha`.

**Nota de repaso.** `coach repaso <slug>` crea `repasos/<AAAA-MM-DD>.md` con «Qué toca hoy», `## Preguntas` y `## Historial`. Las preguntas nuevas entran con `coach nota <slug> repaso` (`**P1.** (1.2) …`, una por elemento), se corrigen con `coach corregir <slug> repaso` y cada `coach repaso <slug> <id|Hn> --bien|--mal` deja su fila en el Historial. El cuaderno la muestra en la vista **Repaso**, encima de la autoevaluación.

## 6. Diagramas Mermaid

| Concepto | Diagrama |
|---|---|
| Flujo, decisiones, capas, dependencias | `flowchart LR` o `flowchart TB` |
| Interacción en el tiempo | `sequenceDiagram` |
| Estructura de clases | `classDiagram` |
| Ciclo de vida y estados | `stateDiagram-v2` |
| Modelo de datos | `erDiagram` |
| Mapa de conceptos | `mindmap` |
| Evolución, épocas o versiones | `timeline` |
| Proporciones o resultados | `pie`, `xychart-beta` |
| Arquitectura por niveles (estilo C4) | `flowchart` con `subgraph` |
| Ramas de git | `gitGraph` |

Reglas para que renderice a la primera y se lea bien:

- Ids de nodo simples, sin espacios ni acentos; el texto visible entre comillas: `repo["OrdersRepository"]`.
- **Etiquetas de 24 caracteres como máximo** por línea: corta con `<br/>` o acorta (`nota` y `check` lo avisan).
- Entre comillas cualquier etiqueta con paréntesis, dos puntos, `@`, `/`, `<` o `>`.
- No uses `end` en minúsculas como id. En `sequenceDiagram`, evita `;` y `#` en los mensajes.
- Máximo 12 a 15 nodos por diagrama. Nada de colores fijos: el cuaderno aplica los del tema claro u oscuro.

## 7. Código, avisos y tablas

**Código**: los mensajes de error exactos que no quepan en 80 caracteres se parten en varias líneas y se dice («una sola línea de la consola, repartida aquí para que quepa»). Siempre con lenguaje (`kotlin`, `swift`, `sql`, `python`, `bash`, `json`, `text`…), líneas de menos de 80 caracteres (un comando `cd <ruta completa> && …` más largo se parte con `\` al final de la línea), un bloque por archivo con su ruta en la primera línea, ejemplos probados y `diff` para cambios sobre código existente. Nunca secretos ni datos personales reales.

**Avisos** (estilo GitHub; el cuaderno los muestra con color e icono): `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]`.

**Tablas**: para comparar alternativas y para tablas de comandos o fórmulas. Sin código largo dentro: en una celda caben un nombre o una anotación.

## 8. METODO, GLOSARIO, DUDAS y MAPA

- **METODO.md** (raíz): tabla de acuerdos y tabla de cambios. Se gestiona con `coach metodo`. En el cuaderno aparece como «Acuerdo de método».
- **GLOSARIO.md**: tabla `| Término | Definición | Lección |` en orden alfabético (`coach glosario`). Definición precisa en 1 o 2 frases, sin usar el propio término. Si la lección no tiene nota, solo su id.
- **DUDAS.md**: la más reciente arriba (`coach duda`):

  ```markdown
  ## 2026-10-02 · ¿`by lazy` en el contenedor es seguro entre hilos?

  - **Contexto:** dónde surgió.
  - **Respuesta corta:** 1 o 2 frases.
  - **Explicación:** el porqué, con un ejemplo mínimo si ayuda.
  - **Relacionado:** lección 1.2 · término «Contenedor de dependencias»
  - **Fuente:** [Título](https://…)
  ```

- **MAPA.md** (opcional): mapa del tema construido con [dominio-generico.md](dominio-generico.md).

## 9. Lo que revisa `check`

| Aviso | Cómo se arregla |
|---|---|
| `enlace interno «#x» sin encabezado` / `enlace roto a …` | Enlaza al archivo o corrige la ruta relativa. |
| `línea(s) de código de más de 80 caracteres` | Parte la línea. |
| `etiqueta(s) de Mermaid de más de 24 caracteres` | Acorta o usa `<br/>`. |
| `celda(s) de tabla con código largo` | Saca el código a un bloque. |
| `quedan N marcador(es) [[COMPLETAR]]` | Rellénalos o borra la sección. |
| `la nota está completada pero le faltan secciones` | Completa «Resumen con tus palabras» y «Fuentes». |
| `«Reto …» no tiene **Resultado esperado**` / `no registra el intento ni el veredicto` | Añade lo que falta al reto. |
| `el reto n tiene la solución pero no el intento` / `Pn tiene la respuesta completa pero no la respuesta` | La solución se escribe después del intento: añade su intento (`coach corregir`). |
| `sin mapa de bloques` | Añade `**Bloques:**` con la lista numerada en `## Objetivos`. |
| `plan de hb-coach 3.0` | `coach migrar --dry-run` y, si te convence, `coach migrar` (§13). |
| `módulo(s) sin línea de examen` | `coach examen <slug> <n>` la añade (solo en planes de formato 2; el último módulo 🔴 o «Proyecto…» no la necesita). |
| `hueco Hn con «Próximo repaso» sin fecha` | Repásalo con `coach hueco <slug> Hn --bien\|--mal`. |
| `cuaderno.html desactualizado` | `coach build`. |

`sesion` ejecuta `check` al cerrar. Reserva las capturas de pantalla para cambios de diseño del visor.

## 10. Enlaces e imágenes

- Entre archivos, rutas **relativas al archivo actual**: desde una nota, `../GLOSARIO.md` o `1.3-….md`; desde PLAN.md, `lecciones/1.2-….md`. El cuaderno los convierte en navegación interna y marca en rojo los rotos.
- Anclas (`[ver arriba](#teoría--…)`) solo si existe ese encabezado; si dudas, enlaza al archivo.
- Externos con URL completa: se abren en otra pestaña.
- Imágenes en `<slug>/img/`, enlazadas en relativo: `![Grafo](../img/grafo.png)` desde una nota.

## 11. Modo manual (sin ejecutar comandos)

Si el entorno no permite ejecutar comandos, mantén los mismos archivos a mano:

- **Crear un tema**: copia las plantillas de `assets/plantillas/` (sustituye los `{{…}}`), incluidos `METODO.md` y `README.md` en la raíz.
- **Empezar una lección**: crea la nota con `LECCION.md`; en PLAN.md, `leccion_actual: "<id>"` y `actualizado`.
- **Bloques**: añade el bloque entero (sin soluciones) antes de «Resumen con tus palabras»; cuando responda, escribe su intento, el veredicto y la corrección debajo del reto o de la pregunta, y la solución solo al cerrarlo (§4). En el chat, el mismo mensaje corto de SKILL.md, con «1.3 › Bloque 1» en vez del enlace.
- **Glosario, dudas**: edita los archivos con los formatos de este documento.
- **Completar**: `- [ ]` → `- [x]` (y ` (convalidada)` si corresponde), `leccion_actual` a la siguiente pendiente; en la nota, `estado: completada`, `fin: <hoy>`, `repaso: <hoy + 3 días>` y `repasos: 0`.
- **Repasos**: lección bien → `repasos + 1` y `repaso` = hoy + 7, 14, 30 o 60 días (según el nuevo `repasos`: 1, 2, 3, 4); al quinto, `repaso: ""`. Mal → `repasos: 0` y `repaso` = mañana.
- **Huecos**: nuevo → fila con `Intentos` 2 (1 si viene del diagnóstico o de un examen), `Próximo repaso` mañana y `Estado` `abierto`. Bien → añade una ✔ al estado y fija el repaso a hoy + 3, 7, 14 o 30 días según las ✔. Mal → `abierto` sin ✔, `Intentos + 1`, repaso mañana. Cerrar → `Próximo repaso` `—` y `cerrado <fecha>`.
- **Examen**: línea `- [ ] **Examen M<n>** — …` al final del módulo; al aprobar, `- [x] **Examen M<n>** — a/t (p %) · aprobado el <fecha>`.
- **Bitácora**: una fila por sesión al final de su tabla.
- **Repasos y exámenes**: las preguntas en `repasos/<fecha>.md` o en la nota del examen, y la corrección debajo de cada una.
- **Ver el cuaderno**: el estudiante abre `<skill>/assets/cuaderno.html` y pulsa **Abrir carpeta** para elegir `aprendizaje/` (en Chrome y Edge se actualiza solo; en otros navegadores, **Recargar carpeta**). El visor calcula progreso, exámenes, repasos vencidos y el estado de cada bloque por sí mismo. Díselo en tu mensaje final.

## 12. Sin conexión y refresco automático

**Refresco automático.** `coach build` (y cada comando que cambia algo) escribe junto al cuaderno `.cuaderno-version.js`, con una huella del contenido. La página abierta lo vuelve a cargar cada 3 segundos con una etiqueta `<script>` (funciona con `file://`, sin servidor, sin red y sin procesos en segundo plano) y, si la huella cambió, se recarga en el mismo sitio y lo avisa con «Cuaderno actualizado · Ir a lo nuevo». En la autoevaluación del repaso no se recarga sola: ofrece un botón. Si el navegador no lo permite, no pasa nada: el estudiante recarga a mano (por eso el mensaje del coach lo recuerda). Se descartó un servidor local (`coach servir`): obliga a dejar un proceso abierto y a cambiar los enlaces `file://` por `http://localhost`.


El HTML de las notas pasa por DOMPurify sin estilos, formularios ni campos (salvo las casillas de las listas de tareas): el texto copiado de la web no puede cambiar el aspecto del cuaderno ni pedir datos. El cuaderno carga sus librerías (Markdown, sanitizado, resaltado y Mermaid) en este orden: `aprendizaje/.vendor/`, jsDelivr y cdnjs. Con `coach vendor` se descargan una vez y funciona sin internet. Sin librerías, muestra el texto sin formato y un aviso. Las fuentes tipográficas caen a las del sistema. El navegador solo guarda el tema claro u oscuro elegido y el resultado del último «Repaso de hoy» de cada tema (siempre con try/catch: en una ventana privada no guarda nada). Ese resultado es orientativo: para que cuente en el plan, el repaso se hace con el coach.

## 13. Desde hb-coach 3.0

Un espacio creado con hb-coach 3.0 funciona tal cual: el plan no tiene exámenes ni calendario, pero se lee, se completa y se ve en el cuaderno. Para añadirlos, `coach migrar` (prueba antes con `--dry-run`):

- guarda una copia de todos los `.md` en `aprendizaje/.respaldos/3.0-<fecha-hora>/`;
- añade `formato: 2` al plan, la línea de examen al final de cada módulo (salvo el del proyecto final) y el primer repaso (fin + 3 días) a las lecciones completadas con nota;
- añade a `METODO.md` las filas «Pasos» y «Repasos» si faltan.

Nunca borra ni reescribe lo que escribió el estudiante, y una segunda ejecución no hace nada. Para deshacerla, copia el respaldo encima.

## 14. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El cuaderno no refleja los cambios | No se regeneró, o el navegador no permite el refresco automático | `coach build` y recargar la página. |
| `bloque` se niega: «aún espera…» | El bloque anterior tiene un reto o una pregunta sin cerrar | `coach corregir` con su intento; si de verdad quiere saltarlo, `--forzar`. |
| `bloque` o `nota` se niegan por una «Solución» | La solución iba antes del intento | Quítala del bloque y escríbela con `coach corregir` después de su intento. |
| Una lección no suma progreso | La línea no sigue el formato `- [ ] **1.2 Título** — …` | Corregir la línea; `coach check`. |
| Una nota no se asocia a su lección | El nombre no empieza por el id | Renombrar a `<id>-<slug>.md`. |
| `completar` se niega | Nota a medias | Completar las secciones o `--forzar` si de verdad está hecha. |
| `leccion` se niega | El plan conserva títulos de la plantilla | Terminar el plan. |
| `nota` dice «Falta el contenido» | El heredoc no llegó (shell sin heredocs) | Guardar el bloque en un archivo y usar `--desde`. |
| Diagrama en rojo | Error de sintaxis Mermaid | Revisar las reglas del §6. |
| Texto sin formato y aviso de librerías | Sin conexión y sin `.vendor` | `coach vendor` con conexión. |
