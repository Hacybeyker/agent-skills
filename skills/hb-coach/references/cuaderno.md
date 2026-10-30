# Cuaderno: archivos, formato y herramienta

Todo lo que el coach escribe en `aprendizaje/` y cómo se convierte en `cuaderno.html`.

## Contenido

1. Estructura y propósito de cada archivo
2. Herramienta `coach`
3. Nota de lección
4. Diagramas Mermaid
5. Código, avisos, preguntas y tablas
6. METODO.md, GLOSARIO.md y DUDAS.md
7. Higiene del cuaderno (lo que revisa `check`)
8. Enlaces e imágenes
9. Sin scripts: modo manual
10. Sin conexión
11. Solución de problemas

## 1. Estructura y propósito de cada archivo

```text
aprendizaje/                      ← raíz (se excluye de git con .git/info/exclude)
├── README.md                     ← guía corta para el estudiante (la crea init)
├── METODO.md                     ← acuerdo de método: cómo quiere aprender
├── cuaderno.html                 ← generado: NO editar a mano
├── .vendor/                      ← opcional: librerías para usarlo sin conexión
└── <slug>/
    ├── PLAN.md                   ← plan, progreso, huecos abiertos y bitácora
    ├── GLOSARIO.md               ← conceptos del tema
    ├── DUDAS.md                  ← dudas resueltas durante implementaciones
    ├── lecciones/<id>-<slug>.md  ← una nota por lección
    ├── img/                      ← opcional: imágenes de las notas
    └── *.md                      ← opcional: otros documentos (cheatsheets, recursos)
```

El cuaderno lee **todos** los `.md` de la carpeta (menos los ocultos), así que cualquier documento extra del tema aparece automáticamente en su menú.

## 2. Herramienta `coach`

Ejecuta desde la raíz del proyecto `python3 <skill>/scripts/coach.py …` o `node <skill>/scripts/coach.mjs …` (salida idéntica).

| Comando | Efecto | Cuándo |
|---|---|---|
| `init <slug> --tema "…" [--area A] [--nivel-objetivo N]` | Crea la carpeta del tema con PLAN, GLOSARIO, DUDAS y `lecciones/`; crea `README.md` y `METODO.md`; añade `/aprendizaje/` a `.git/info/exclude`; regenera el cuaderno. | Al crear un plan. `--versionar` no excluye la carpeta de git; `--gitignore` usa `.gitignore`; `--force` reemplaza un PLAN.md existente. |
| `leccion <slug> <id>` | Crea `lecciones/<id>-<título>.md` desde la plantilla si no existe, fija `leccion_actual` y pone la nota en `estado: en-curso`. Si la lección ya estaba hecha, solo la abre para repaso. | Al empezar o retomar una lección. |
| `completar <slug> <id> [--convalidada]` | Marca `[x]` en PLAN.md, actualiza `actualizado` y `leccion_actual`, y pone `estado` y `fin` en la nota. Avisa si se completó el módulo o el plan. | Cuando se cumple el criterio de dominio o al convalidar. |
| `reabrir <slug> <id>` | Vuelve a `[ ]`, quita `(convalidada)` y deja la lección como actual. | Si se marcó por error o hay que reforzar. |
| `estado [slug] [--json]` | Resumen de los temas, lección actual, huecos abiertos y última sesión; con un slug, el detalle con todas las lecciones. | Al empezar una sesión o si preguntan cómo van. |
| `build` | Regenera `cuaderno.html` con todos los `.md`. | Tras editar Markdown a mano. |
| `check [slug]` | Formato del plan y de las notas, enlaces, anclas, diagramas y legibilidad (sección 7). | Antes de cerrar cada sesión; sustituye a revisar el cuaderno con capturas. |
| `vendor [--force]` | Descarga las librerías a `aprendizaje/.vendor/`. | Para usar el cuaderno sin internet. |

Opciones comunes: `--root <dir>` (otra carpeta de aprendizaje; también la variable `COACH_ROOT`), `--no-build`. Códigos de salida: 0 bien, 1 `check`/`vendor` con errores, 2 uso incorrecto.

**Agrupa las ediciones**: escribe o actualiza todos los archivos de un bloque y ejecuta **un** comando al final, en vez de encadenar decenas de llamadas. Antes de una tanda larga (builds, emulador, varias ediciones), escribe una línea de estado diciendo qué vas a hacer.

## 3. Nota de lección

`coach leccion` la crea desde la plantilla. Frontmatter:

```yaml
---
leccion: "2.4"
titulo: "Módulos: @Provides y @Binds"
tema: hilt
modulo: "M2 · Primeros pasos con Hilt"
estado: en-curso            # en-curso | completada | convalidada (lo mantienen los scripts)
inicio: 2026-10-02
fin: 2026-10-03             # lo añade completar
etiquetas: [di, kotlin]
---
```

Estructura fija (en este orden). Los bloques 📖 🛠 ❓ se repiten tantas veces como bloques tenga la lección, siempre en ese orden dentro de cada uno:

| Sección | Contenido |
|---|---|
| `## Resumen` | La idea central en una frase, el resultado esperado y el mapa de bloques de la lección. |
| `## 📖 Teoría · <subtítulo>` | Concepto, definición precisa, diagrama si aporta y los **tres ejemplos**: mínimo ejecutable, en su proyecto y «lo que sale mal» con el error real. |
| `## 🛠 Práctica · <subtítulo>` | Pasos numerados (ya verificados en una copia), criterio de éxito y qué observó al ejecutarlos. |
| `## ❓ Preguntas · <subtítulo>` | Las preguntas del bloque, la respuesta del estudiante, el veredicto (✔ / ✘) y el «Para ampliar». La respuesta modelo va dentro de `<details>`. |
| `## Resumen con tus palabras` | La explicación del estudiante, corregida si hacía falta. |
| `## Fuentes` | Enlaces oficiales con versión o fecha de consulta. |
| `## Historial` | Bitácora de la lección: fechas, en qué pista se resolvió cada atasco, errores del coach y correcciones, huecos abiertos o cerrados. |

Reglas:

- Escribe la nota **durante** la lección, bloque a bloque, en el mismo turno.
- Numera los bloques en los subtítulos (`📖 Teoría · 1. Por qué una interfaz no se inyecta sola`) para que el cuaderno se lea en orden.
- Marca los supuestos como tales: «**Supuesto** (no lo implementes): imagina que…».
- Elimina las secciones que no uses y los comentarios `<!-- coach: … -->` cuando ya no aporten.
- La primera línea `# <id> · <título>` se oculta en el cuaderno (el título ya está en la cabecera), pero mantenla para GitHub y los editores.
- Nombre de archivo: `<id>-<slug-del-título>.md`; debe empezar por el id para que el cuaderno lo asocie a la lección.

## 4. Diagramas Mermaid

Elige el tipo según lo que quieras enseñar:

| Concepto | Diagrama |
|---|---|
| Flujo, decisiones, capas, dependencias | `flowchart LR` o `flowchart TB` |
| Interacción entre componentes en el tiempo | `sequenceDiagram` |
| Estructura de clases, interfaces y relaciones | `classDiagram` |
| Ciclo de vida y estados | `stateDiagram-v2` |
| Modelo de datos | `erDiagram` |
| Mapa de conceptos | `mindmap` |
| Evolución o versiones | `timeline` |
| Arquitectura por niveles (estilo C4) | `flowchart` con `subgraph` por contenedor |
| Ramas de git | `gitGraph` |

Reglas para que renderice a la primera y se lea bien:

- Ids de nodo simples, sin espacios ni acentos (`repo`, `vm`, `api`); el texto visible va entre comillas: `repo["OrdersRepositoryImpl"]`.
- **Etiquetas de 24 caracteres como máximo**: si no cabe, corta con `<br/>` o acorta el texto. Las etiquetas largas estiran el diagrama y lo vuelven ilegible en el móvil (`check` lo avisa).
- Pon entre comillas cualquier etiqueta con paréntesis, dos puntos, `@`, `/`, `<` o `>`: `A["onCreate(savedState)"]`.
- No uses `end` en minúsculas como id ni como texto suelto.
- En `sequenceDiagram`, evita `;` y `#` en los mensajes; usa `autonumber` para numerar pasos.
- Máximo de 12 a 15 nodos por diagrama; si hay más, divide en dos.
- Nada de colores fijos: el cuaderno aplica los del tema claro u oscuro.

`check` detecta diagramas vacíos, tipos desconocidos y etiquetas largas. Los errores de sintaxis se ven en el cuaderno: el diagrama aparece en rojo con el mensaje y el código fuente.

## 5. Código, avisos, preguntas y tablas

**Código**

- Siempre con lenguaje: `kotlin`, `swift`, `typescript`, `tsx`, `python`, `java`, `sql`, `bash`, `json`, `yaml`, `xml`, `gradle`, `dart`, `dockerfile`, `http`, `diff`, `text`…
- **Líneas de menos de 80 caracteres**: corta los parámetros en varias líneas. Las líneas largas obligan a desplazarse en horizontal y se cortan al imprimir (`check` lo avisa).
- Un bloque por archivo, con su ruta como comentario en la primera línea.
- Ejemplos completos y correctos, probados antes; comentarios solo donde aportan.
- Para cambios sobre código existente usa un bloque `diff`.
- Nunca incluyas secretos, tokens ni datos personales reales.

**Avisos** (estilo GitHub; el cuaderno los muestra con color e icono):

```markdown
> [!NOTE]
> Información complementaria.

> [!TIP]
> Consejo práctico o analogía.

> [!IMPORTANT]
> Algo imprescindible para que funcione.

> [!WARNING]
> Error común o práctica obsoleta.

> [!CAUTION]
> Riesgo de seguridad o de pérdida de datos.
```

**Preguntas y respuestas**: la pregunta y el veredicto van en texto normal; la respuesta modelo, dentro de `<details>` (deja líneas en blanco alrededor del contenido):

```markdown
**P2.** ¿Por qué `@Binds` exige una función abstracta? — tu respuesta: *«porque no crea el objeto»* ✔

<details>
<summary>Respuesta completa</summary>

`@Binds` no construye nada: solo le dice al grafo qué implementación usar para una interfaz…

</details>

**Para ampliar:** el método debe vivir en un módulo abstracto o en una interfaz.
```

**Tablas**: para comparar alternativas (criterio, opción A, opción B) y para el glosario. **Sin código largo dentro**: en una celda caben un nombre o una anotación; cualquier fragmento va a un bloque de código (`check` lo avisa).

## 6. METODO.md, GLOSARIO.md y DUDAS.md

**METODO.md** (en la raíz de `aprendizaje/`): el acuerdo de método con el estudiante. Se crea con `init`, se completa en la primera sesión y se revisa cuando pida un cambio. Tiene una tabla de acuerdos (orden de los bloques, tipos de pregunta, rigor de corrección, tamaño de los mensajes, práctica, verificación, ritmo e idioma) y una tabla de cambios con fecha y motivo. Léelo al empezar cada sesión. En el cuaderno aparece en el menú «Carpeta» como «Acuerdo de método», así que el estudiante puede releerlo cuando quiera.

La sección «Huecos abiertos» del PLAN.md también se muestra en la portada del tema, justo antes del proyecto final, y se oculta sola mientras la tabla no tenga filas: un hueco registrado es un hueco visible.

**GLOSARIO.md**: una tabla en orden alfabético.

```markdown
| Término | Definición | Lección |
|---|---|---|
| **Binding** | Regla que indica al grafo cómo obtener una instancia de un tipo. | [1.3](lecciones/1.3-de-di-manual-a-dagger-grafo-y-codigo-generado.md) |
```

- Definición precisa en 1 o 2 frases, sin usar el propio término.
- Añade el término cuando se enseña, no al final del plan.
- Si una lección se convalidó y no tiene nota, escribe solo el id (`1.1`) sin enlace.

**DUDAS.md**: la duda más reciente va arriba, justo después del comentario de la plantilla.

```markdown
## 2026-10-02 · ¿`by lazy` en el contenedor es seguro entre hilos?

- **Contexto:** dónde surgió (archivo, tarea, error).
- **Respuesta corta:** 1 o 2 frases.
- **Explicación:** el porqué, con un ejemplo mínimo si ayuda.
- **Relacionado:** lección 1.2 · término «Contenedor de dependencias»
- **Fuente:** [Título](https://…)
```

Borra la línea «Aún no hay dudas registradas» al añadir la primera.

## 7. Higiene del cuaderno (lo que revisa `check`)

Revisar el cuaderno con capturas de pantalla es lento y caro. `coach check` detecta por texto los problemas que de verdad aparecen al leerlo:

| Aviso | Qué significa | Cómo se arregla |
|---|---|---|
| `enlace interno «#x» sin encabezado` | Un ancla que no lleva a ningún sitio. | Enlaza al archivo (`lecciones/2.4-….md`) o escribe el encabezado exacto. |
| `N línea(s) de código de más de 80 caracteres` | Desbordan en el cuaderno y al imprimir. | Parte la línea. |
| `etiqueta de Mermaid de más de 24 caracteres` | El diagrama se estira y no se lee en móvil. | Acorta o usa `<br/>`. |
| `celda de tabla con código largo` | Las tablas no hacen scroll bien con código. | Saca el código a un bloque. |
| `la nota está completada pero le faltan secciones` | Falta «Resumen con tus palabras» o «Fuentes». | Complétalas antes de marcar la lección. |
| `quedan N marcador(es) [[COMPLETAR]]` | Plantilla a medio rellenar. | Rellénalos o borra la sección. |
| `cuaderno.html desactualizado` | Hay Markdown más nuevo que el cuaderno. | `coach build`. |

Las capturas de pantalla se reservan para cambios de diseño del propio visor.

## 8. Enlaces e imágenes

- Enlaces entre archivos con rutas **relativas al archivo actual**: desde una nota, `../GLOSARIO.md` o `1.3-….md`; desde PLAN.md, `lecciones/1.2-….md`. El cuaderno los convierte en navegación interna y marca en rojo los rotos.
- Anclas dentro del mismo documento (`[ver arriba](#teoría--por-qué…)`): solo si existe un encabezado con ese texto. Si dudas, enlaza al archivo completo.
- Enlaces externos con URL completa (`https://…`): se abren en otra pestaña.
- Imágenes en `<slug>/img/` y enlazadas en relativo: `![Grafo](../img/grafo.png)` desde una nota. Se ven en el cuaderno porque `cuaderno.html` está en la raíz de `aprendizaje/`.

## 9. Sin scripts: modo manual

Si el entorno no permite ejecutar comandos:

- **Crear un tema**: crea los archivos copiando las plantillas de `assets/plantillas/` (sustituye los `{{…}}`), incluidos `METODO.md` y `README.md` en la raíz.
- **Empezar una lección**: crea la nota con la plantilla `LECCION.md`, pon `leccion_actual: "<id>"` y `actualizado` en PLAN.md.
- **Completar**: cambia `- [ ]` por `- [x]` en la línea de la lección (añade ` (convalidada)` si corresponde), actualiza `leccion_actual` a la siguiente pendiente y `actualizado`, y en la nota pon `estado: completada` y `fin: <fecha>`.
- **Ver el cuaderno**: el estudiante abre `<skill>/assets/cuaderno.html` en el navegador y pulsa **Abrir carpeta** para elegir `aprendizaje/`. En Chrome y Edge se actualiza solo mientras siga abierto; en otros navegadores hay que pulsar **Recargar carpeta**.
- Díselo al estudiante en tu mensaje final.

## 10. Sin conexión

El cuaderno carga sus librerías (Markdown, sanitizado, resaltado y Mermaid) en este orden: `aprendizaje/.vendor/`, jsDelivr y cdnjs. Con `coach vendor` se descargan una vez y el cuaderno funciona sin internet. Sin librerías, muestra el texto sin formato y un aviso. Las fuentes tipográficas caen a las del sistema sin conexión.

## 11. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El cuaderno no refleja los cambios | No se regeneró o el navegador muestra la versión anterior | `coach build` y recargar la página. |
| Una lección no aparece o no suma progreso | La línea no sigue el formato (`- [ ] **1.2 Título** — …`) | Corregir la línea; `coach check`. |
| Una nota no se asocia a su lección | El nombre del archivo no empieza por el id | Renombrar a `<id>-<slug>.md`. |
| Diagrama en rojo | Error de sintaxis Mermaid | Revisar las reglas de la sección 4. |
| Texto sin formato y aviso de librerías | Sin conexión y sin `.vendor` | `coach vendor` con conexión. |
| `check` avisa de `[[COMPLETAR]]` | Quedan marcadores de plantilla | Completar o borrar esas secciones. |
| Enlace rojo en el cuaderno | Ruta relativa incorrecta | Corregir la ruta respecto al archivo que enlaza. |
| Código que se sale de la caja | Líneas de más de 80 caracteres | Partir las líneas; `check` las cuenta. |
