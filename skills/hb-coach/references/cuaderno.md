# Cuaderno: archivos, formatos y herramienta

Todo lo que el coach escribe en `aprendizaje/` y cómo se convierte en `cuaderno.html`.

## Contenido

1. Estructura y propósito de cada archivo
2. Herramienta `coach`
3. Nota de lección
4. Retos y preguntas
5. Nota de examen
6. Diagramas Mermaid
7. Código, avisos y tablas
8. METODO, GLOSARIO, DUDAS y MAPA
9. Lo que revisa `check`
10. Enlaces e imágenes
11. Modo manual (sin ejecutar comandos)
12. Sin conexión
13. Desde hb-coach 3.0
14. Solución de problemas

## 1. Estructura y propósito de cada archivo

```text
aprendizaje/                      ← raíz (en un proyecto, excluida de git con .git/info/exclude)
├── README.md                     ← guía corta para el estudiante (la crea init)
├── METODO.md                     ← acuerdo de método
├── cuaderno.html                 ← generado: NO editar a mano
├── .vendor/                      ← opcional: librerías para usarlo sin conexión
├── .respaldos/                   ← copias que deja `coach migrar`
└── <slug>/
    ├── PLAN.md                   ← módulos con examen, progreso, huecos y bitácora
    ├── MAPA.md                   ← opcional: mapa del tema (init --mapa)
    ├── GLOSARIO.md · DUDAS.md
    ├── lecciones/<id>-<slug>.md  ← una nota por lección
    ├── examenes/m<n>-<slug>.md   ← una nota por examen de módulo
    ├── img/                      ← opcional: imágenes de las notas
    └── *.md                      ← opcional: otros documentos (chuletas, casos)
```

El cuaderno lee **todos** los `.md` (menos los ocultos), así que cualquier documento extra del tema aparece en su menú.

## 2. Herramienta `coach`

Ejecuta `python3 <skill>/scripts/coach.py <comando>` desde la raíz del proyecto o con `--root <carpeta>`. `coach ayuda` lista todo.

| Comando | Efecto |
|---|---|
| `siguiente [slug] [--json]` | Decide el paso: método pendiente → plan sin terminar → repasos vencidos → examen que toca → lección actual → proyecto final. Imprime la meta de hoy, los comandos exactos (con `--root` si hace falta) y qué leer. |
| `init <slug> --tema "…" [--area A] [--nivel-objetivo N] [--playground URL] [--mapa]` | Crea el tema desde las plantillas, `README.md` y `METODO.md` si faltan, y excluye la carpeta de git (`--versionar` no la excluye; `--gitignore` usa `.gitignore`; `--force` reemplaza un PLAN.md). |
| `metodo [--<clave> "valor" …] [--motivo "…"]` | Funciona antes de `init` (crea la carpeta y `METODO.md`, y la excluye de git). Sin claves, muestra el acuerdo. Con claves (`orden`, `pasos`, `preguntas`, `correccion`, `mensajes`, `ejemplos`, `practica`, `verificacion`, `ritmo`, `profundidad`, `calentamiento`, `repasos`, `idioma`), actualiza las filas y anota el cambio con su fecha. |
| `leccion <slug> <id>` | Crea `lecciones/<id>-<título>.md`, fija `leccion_actual` y pone la nota en `en-curso`. Se niega si la ruta aún tiene marcadores. Si la lección estaba hecha, la abre como repaso. |
| `nota <slug> <id\|Mn> …` | Inserta el Markdown (stdin o `--desde`) antes del cierre de la nota (Resumen con tus palabras, Fuentes, Historial; en un examen, antes de Tarea práctica). Las partes que empiezan por `## Objetivos`, `## Resumen con tus palabras`, `## Fuentes`, `## Tarea práctica` o `## Resultado` reemplazan esa sección. Con `--seccion objetivos\|resumen\|fuentes\|tarea`, el texto (sin encabezado) reemplaza esa sección. `--historial "texto"` añade una fila fechada. Avisa al momento de líneas de código largas y etiquetas Mermaid ilegibles. |
| `glosario <slug> "T" "Def" […] [--leccion id]` | Inserta cada término en orden alfabético (o actualiza su definición) con enlace a la nota de la lección (por defecto, la actual). |
| `duda <slug> "Pregunta" --respuesta "…" [--contexto] [--explicacion] [--leccion] [--fuente]` | Añade la duda arriba de `DUDAS.md`. |
| `hueco <slug> "Descripción" [--leccion id] [--intentos n]` | Abre un hueco (`H1`, `H2`…) con su primer repaso mañana. `Intentos` empieza en 2 (se abre tras el segundo fallo); usa `--intentos 1` si viene del diagnóstico o de un examen. |
| `hueco <slug> Hn --bien\|--mal\|--cerrar` | Reprograma el hueco según el calendario o lo cierra (`repaso <slug> Hn` hace lo mismo con `--bien` o `--mal`). |
| `completar <slug> <id> [--convalidada] [--forzar]` | Marca `[x]`, avanza `leccion_actual`, pone `estado`, `fin` y el primer repaso en la nota, y avisa si toca examen. Se niega si la nota tiene `[[COMPLETAR]]` o le faltan «Resumen con tus palabras» o «Fuentes» (`--forzar` lo salta). |
| `reabrir <slug> <id>` | Vuelve a `[ ]`, quita `(convalidada)` y anula el repaso programado. |
| `repaso <slug> [--json]` | Lo que vence hoy (huecos primero, luego lecciones, hasta 6), mezclado entre módulos, con las preguntas de cada nota. |
| `repaso <slug> <id\|Hn> --bien\|--mal` | Registra el repaso de una lección (o hueco) y lo reprograma; lo anota en el Historial de la nota. |
| `examen <slug> <n>` | Añade la línea del examen al plan si falta y crea `examenes/m<n>-….md` con lo que cubre. |
| `examen <slug> <n> --resultado a/t [--tarea si\|no]` | Marca el examen como aprobado (≥ 80 % y tarea no fallida) o «repetir», y escribe el resultado en la nota. |
| `sesion <slug> --logros "…" [--lecciones "…"] [--siguiente "…"]` | Añade la fila de bitácora (el próximo paso, por defecto, el de `siguiente`), regenera el cuaderno, ejecuta `check` y muestra el siguiente paso. |
| `estado [slug] [--json]` | Progreso, exámenes, repasos y huecos; con un slug, todas las lecciones. |
| `build` · `check [slug]` · `vendor [--force]` · `migrar [--dry-run]` · `version` | Regenerar; validar (§9); descargar librerías (§12); migrar desde 3.0 (§13). |

Los comandos que cambian algo regeneran el cuaderno (salvo con `--no-build`). Códigos de salida: 0 bien, 1 `check`/`vendor`/`sesion` con errores, 2 uso incorrecto (el mensaje dice cómo seguir).

**Contenido por stdin.** `nota` lee el Markdown de un heredoc (`<<'EOF'` … `EOF`, con comillas para que la shell no expanda nada) o de un archivo con `--desde`. Una llamada por bloque: la primera puede llevar `## Objetivos` y el primer bloque; la de cierre, `## Resumen con tus palabras` y `## Fuentes`. Los comandos de un mismo momento se encadenan con `&&`.

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
| `## Objetivos` | `> **En una frase:** …`, «Al terminar podrás:» con 2 o 3 objetivos observables y el mapa de bloques. (En notas de 3.0 se llama `## Resumen`.) |
| `## 📖 Teoría · <n>. <subtítulo>` | Explicación → ejemplo → desglose en viñetas → aviso; los tres ejemplos; diagrama si aporta. |
| `## 🛠 Práctica · <n>. <subtítulo>` | Uno o varios retos (§4) y lo que observó al hacerlos. |
| `## ❓ Preguntas · <n>. <subtítulo>` | Las preguntas con su respuesta, veredicto y respuesta completa (§4). |
| `## Resumen con tus palabras` | Su explicación, corregida si hacía falta. |
| `## Fuentes` | Enlaces con versión o fecha de consulta. |
| `## Historial` | Fechas, en qué pista se resolvió cada atasco, errores del coach y su corrección, huecos, repasos. |

Reglas: escribe la nota **durante** la lección, bloque a bloque (`coach nota`); numera los bloques en los subtítulos; marca los supuestos («**Supuesto** (no lo hagas): …»); mantén la línea `# <id> · <título>` (el cuaderno la oculta); nombre de archivo `<id>-<slug-del-título>.md`.

## 4. Retos y preguntas

**Reto** (dentro de un bloque 🛠). El cuaderno lo muestra como tarjeta «Reto n de N» con su estado, revela las pistas de una en una y pide confirmar que ya lo intentó antes de enseñar la solución.

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

<details>
<summary>Solución</summary>

```sql
SELECT title, year FROM videojuegos;
```

</details>

**Tu intento:** `SELECT title, year FROM videojuegos;` · **Veredicto:** ✔ resuelto sin pistas
````

- El reto va a la nota cuando termina, en una sola llamada: enunciado, resultado esperado, las pistas (escritas de antemano, de menos a más), la **Solución** (solo porque ya lo intentó) y su intento con el veredicto. Si se aplaza, sin solución.
- Un reto de refuerzo tras un segundo fallo puede ir dentro del bloque ❓ en curso.
- **Veredicto:** ✔ resuelto (en qué pista) o ✘ con la idea que falló. Sin veredicto, el reto cuenta como «sin resolver».
- Fuera del software, el resultado esperado es lo observable: una cifra, una frase correcta, una decisión justificada, los puntos de una rúbrica.

**Pregunta y respuesta** (bloque ❓ y examen). El cuaderno usa estas preguntas para el «Repaso de hoy»: la parte anterior a « — tu respuesta» es la pregunta y el `<details>`, la respuesta.

```markdown
**P2.** ¿Por qué `@Binds` exige una función abstracta? — tu respuesta: *«porque no crea el objeto»* ✔

<details>
<summary>Respuesta completa</summary>

`@Binds` no construye nada: solo le dice al grafo qué implementación usar para una interfaz.

</details>

**Para ampliar:** el método debe vivir en un módulo abstracto o en una interfaz.
```

Deja una línea en blanco alrededor del contenido de cada `<details>`.

## 5. Nota de examen

`coach examen <slug> <n>` crea `examenes/m<n>-<módulo>.md` con «Qué cubre», `## Preguntas`, `## Tarea práctica`, `## Resultado` y `## Historial`. Cada pregunta entra con `coach nota <slug> M<n>` (formato del §4); la tarea, con `--seccion tarea`; el resultado lo escribe `coach examen … --resultado`. El frontmatter lleva `estado: pendiente | aprobado | repetir`, `resultado` y `fecha`.

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

**Código**: los mensajes de error exactos que no quepan en 80 caracteres se parten en varias líneas y se dice («una sola línea de la consola, repartida aquí para que quepa»). Siempre con lenguaje (`kotlin`, `swift`, `sql`, `python`, `bash`, `json`, `text`…), líneas de menos de 80 caracteres, un bloque por archivo con su ruta en la primera línea, ejemplos probados y `diff` para cambios sobre código existente. Nunca secretos ni datos personales reales.

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
- **Bloques, glosario, dudas**: edita los archivos con los formatos de este documento.
- **Completar**: `- [ ]` → `- [x]` (y ` (convalidada)` si corresponde), `leccion_actual` a la siguiente pendiente; en la nota, `estado: completada`, `fin: <hoy>`, `repaso: <hoy + 3 días>` y `repasos: 0`.
- **Repasos**: lección bien → `repasos + 1` y `repaso` = hoy + 7, 14, 30 o 60 días (según el nuevo `repasos`: 1, 2, 3, 4); al quinto, `repaso: ""`. Mal → `repasos: 0` y `repaso` = mañana.
- **Huecos**: nuevo → fila con `Intentos` 2 (1 si viene del diagnóstico o de un examen), `Próximo repaso` mañana y `Estado` `abierto`. Bien → añade una ✔ al estado y fija el repaso a hoy + 3, 7, 14 o 30 días según las ✔. Mal → `abierto` sin ✔, `Intentos + 1`, repaso mañana. Cerrar → `Próximo repaso` `—` y `cerrado <fecha>`.
- **Examen**: línea `- [ ] **Examen M<n>** — …` al final del módulo; al aprobar, `- [x] **Examen M<n>** — a/t (p %) · aprobado el <fecha>`.
- **Bitácora**: una fila por sesión al final de su tabla.
- **Ver el cuaderno**: el estudiante abre `<skill>/assets/cuaderno.html` y pulsa **Abrir carpeta** para elegir `aprendizaje/` (en Chrome y Edge se actualiza solo; en otros navegadores, **Recargar carpeta**). El visor calcula progreso, exámenes y repasos vencidos por sí mismo. Díselo en tu mensaje final.

## 12. Sin conexión

El cuaderno carga sus librerías (Markdown, sanitizado, resaltado y Mermaid) en este orden: `aprendizaje/.vendor/`, jsDelivr y cdnjs. Con `coach vendor` se descargan una vez y funciona sin internet. Sin librerías, muestra el texto sin formato y un aviso. Las fuentes tipográficas caen a las del sistema. Lo único que guarda el navegador es el tema claro u oscuro elegido; el resultado de un «Repaso de hoy» en el navegador no se guarda: para que cuente, se hace con el coach.

## 13. Desde hb-coach 3.0

Un espacio creado con hb-coach 3.0 funciona tal cual: el plan no tiene exámenes ni calendario, pero se lee, se completa y se ve en el cuaderno. Para añadirlos, `coach migrar` (prueba antes con `--dry-run`):

- guarda una copia de todos los `.md` en `aprendizaje/.respaldos/3.0-<fecha-hora>/`;
- añade `formato: 2` al plan, la línea de examen al final de cada módulo (salvo el del proyecto final) y el primer repaso (fin + 3 días) a las lecciones completadas con nota;
- añade a `METODO.md` las filas «Pasos» y «Repasos» si faltan.

Nunca borra ni reescribe lo que escribió el estudiante, y una segunda ejecución no hace nada. Para deshacerla, copia el respaldo encima.

## 14. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El cuaderno no refleja los cambios | No se regeneró o el navegador muestra la versión anterior | `coach build` y recargar la página. |
| Una lección no suma progreso | La línea no sigue el formato `- [ ] **1.2 Título** — …` | Corregir la línea; `coach check`. |
| Una nota no se asocia a su lección | El nombre no empieza por el id | Renombrar a `<id>-<slug>.md`. |
| `completar` se niega | Nota a medias | Completar las secciones o `--forzar` si de verdad está hecha. |
| `leccion` se niega | El plan conserva títulos de la plantilla | Terminar el plan. |
| `nota` dice «Falta el contenido» | El heredoc no llegó (shell sin heredocs) | Guardar el bloque en un archivo y usar `--desde`. |
| Diagrama en rojo | Error de sintaxis Mermaid | Revisar las reglas del §6. |
| Texto sin formato y aviso de librerías | Sin conexión y sin `.vendor` | `coach vendor` con conexión. |
