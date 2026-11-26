---
name: hb-implement
description: 'Implementa features, bugfixes, mejoras y refactors en proyectos con AGENTS.md: lee las reglas, el stack y el modelo de estructura del proyecto, carga su perfil hb-stack-*, implementa por capas con tests en cada unidad que toca (módulo, paquete o repo vecino), corre el DoD de cada unidad y genera un reporte HTML desde git. Úsala cuando el usuario pida crear o implementar una feature, corregir un bug o un issue, mejorar algo o refactorizar ("crea la feature X", "implementa Y", "corrige el bug Z", "resuelve el issue #N", "mejora X", "refactoriza Y", "/hb-implement").'
license: MIT
compatibility: "Requiere git y, para el reporte HTML, Python 3.8+ solo con su librería estándar (en macOS viene con las Command Line Tools). Opcional: la CLI android de Google para dibujar los previews de Compose, y conexión al abrir un reporte con diagramas."
metadata:
  author: hacybeyker
  version: "1.8.0"
  category: flow
  origin: "basada en feature-implementation (Android y KMP)"
---

# hb-implement

El flujo es el mismo para cualquier stack. La arquitectura, los comandos y las reglas salen del proyecto (`AGENTS.md`) y de su perfil `hb-stack-*`.

## 0. Contexto

1. Lee `AGENTS.md`. **Si no existe, no apliques este flujo**: avísalo y ofrece crearlo con `hb-setup`, o seguir sin él. En un `git worktree`, si falta porque en el worktree principal es un enlace o un archivo local, dilo y da el comando para recrearlo (`ln -s <ruta real> AGENTS.md`); no lo crees sin que el usuario o el proyecto lo pidan.
2. Toma de `AGENTS.md`:
   - `## Stack` y `## Arquitectura`: el perfil (`hb-stack-<familia>`), la variante y el stack **real** del proyecto; se implementa con ese stack. `## Modernización`: lo único que se puede migrar.
   - `## DoD`: los comandos de verificación, en orden.
   - Las reglas propias: quién commitea, changelog, idioma, prohibiciones, librerías y estilo de tests, `Carpeta de reportes` y la base contra la que se compara.
3. **Modelo de estructura.** Lee `## Estructura` de `AGENTS.md` y, si no existe, `### Repos relacionados` de `## Arquitectura` (el formato anterior). De ahí salen las unidades (su identificador, dónde está su fuente, cómo se consume, cómo pasarla a fuente y volver, su DoD, su repo y rama principal, y quién la publica y versiona), las variantes y entornos, el cliente HTTP, la configuración local modificada a propósito (no es un cambio ajeno, no se revisa como hallazgo y nunca se propone para commit), la línea `Repos vecinos` y la tabla "Documentos": lee solo los documentos cuya fila "Léelo cuando…" corresponde a la tarea, por su ruta exacta. Si lo que encuentras no coincide con el modelo, dilo en la entrega con la corrección; `hb-implement` y `hb-performance` la aplican en `## Estructura`, sobre la ruta real de `AGENTS.md` (`realpath AGENTS.md`). Sin modelo, sigue con lo que haya y ofrece `hb-setup`.
4. **Mapa del módulo.** Antes de tocar o revisar una unidad, lee su mapa en la carpeta que dice la línea "Mapas del módulo" de `## Estructura` (`<carpeta de contexto>/modules/<identificador>.md`, con las subcarpetas del identificador). Si su `Commit analizado` no es el `HEAD` del repo de la unidad, mira solo `git -C <repo> diff <commit>..HEAD -- <ruta de la unidad>`. Si el mapa no existe o quedó atrás, créalo o actualízalo con lo que ya leíste, en su ruta real: arriba, `Commit analizado: <sha>` y la ruta de la unidad; después, Qué hace, Puntos de entrada, Flujos principales, Servicios que llama, Datos y persistencia, Patrones y convenciones, DoD de la unidad y Cuidado con. `hb-review` solo lo lee.
5. Carga el perfil y **solo** las referencias que la tarea necesita.
6. Clasifica la tarea: `feature`, `bugfix`, `enhancement` o `refactor`.
7. **Antes de cambiar nada**, pide la carpeta de la tarea: `report.py --folder <slug>` (sección 6). El slug no cambia después: si su convención lleva el código de la tarea (`<ticket>-<descripción>`) y todavía no lo tienes, pregúntalo antes de pedir la carpeta (puede ir en la misma pregunta que la rama de trabajo). La crea y toma la **foto inicial**: la rama, el `HEAD` y los archivos sin commit de cada repo (el principal, sus repos hermanos y las fuentes de las unidades del modelo). Con ella el reporte sabe, sin depender de tu memoria, qué cambió la tarea. Si la tarea ya tenía carpeta, se conserva la foto del inicio. Después revisa `git status` de cada repo que vas a tocar: los archivos de "Configuración local modificada a propósito" no son cambios ajenos y no avisas por ellos; si hay otros que no son de esta tarea (el script lista los que la foto ya encuentra), avísalo antes de empezar. El reporte compara cada repo contra el `merge-base` con su rama principal, o contra la base que fije `AGENTS.md` (sección 6).
8. **Unidades**, con el modelo (detalle en [unidades.md](references/unidades.md)). Antes del plan:
   - Decide qué unidades **cambia** la tarea, cuáles necesita en fuente sin cambiarlas y cuáles solo lee, y confirma que el código que vas a editar entra en el build: con el modelo y, si no alcanza, con la herramienta de build del proyecto.
   - Deja listo cada repo vecino que vas a tocar: si no está, clónalo con la URL del modelo; si está atrasado respecto de su remoto, dilo y sigue con lo que hay; **pregunta** solo si tiene cambios sin commit que no son de esta tarea. Si no puedes leer su carpeta, detente y di qué acceso falta.
   - Avisa si el fuente de una unidad publicada no coincide con la versión que fija la app.
   - **La rama de trabajo, en una sola pregunta** para todos los repos que vas a modificar: muestra la rama actual de cada uno y ofrece (a) seguir en esa rama o (b) crear una rama nueva con el nombre que dé el usuario. Los nombres suelen llevar el código de la tarea: no lo inventes; si elige (b) sin dar el nombre, pregúntaselo. **Si nadie responde** (modo autónomo o sin usuario), sigue en la rama actual de cada repo, sin crear ni cambiar ramas, y dilo en la entrega y en el reporte (`branch_note`). Nunca hagas `pull`, `merge` ni `rebase` para preparar la rama.

   Antes de editar cada repo:
   - Una unidad **publicada** que vas a cambiar se pasa a fuente **sin preguntar**, con el mecanismo del modelo; compila para comprobarlo y sigue. Ese cambio es temporal (`temporary` del meta). En cuanto la pasas a fuente, **regístrala**: `report.py --unit <su fuente> --folder <slug>` (sección 6). Si es `sin mecanismo`, trabaja solo en el repo de la unidad y avisa que el cambio llega a la app cuando se publique.

   Con `Repos vecinos: no clonar ni crear ramas`, o si `## Git` dice que la IA no cambia de rama, no clones ni crees ramas, ni hagas la pregunta de la rama: sigue en la rama actual de cada repo, propón los comandos y sigue.

## 1. Plan

- **Criterios de aceptación.** Si el pedido no los trae, escríbelos en formato Given / When / Then, y confírmalos si el pedido es ambiguo.
- Lista los archivos que vas a crear, modificar o eliminar, por capa, y los patrones de diseño que vas a aplicar y por qué (ver los principios del perfil: SOLID, GRASP, GoF, KISS, YAGNI, DRY).
- **Presenta el plan y espera confirmación** si la tarea toca más de una feature, cambia un contrato público (API, esquema de base de datos, navegación compartida), agrega dependencias o exige una decisión de arquitectura. Si no, sigue. La excepción es el alcance aprobado (abajo).

### Con el alcance aprobado (modo autónomo o subagente)

Si el pedido trae un alcance aprobado (un documento de alcance, un `PLAN.md` o un brief que dice "el plan ya está aprobado", "sin aprobaciones"), o corres como subagente de un orquestador, **no esperes la confirmación del plan**: el pedido ya la dio. El resto del flujo no cambia.

- **Decide y anota.** Cuando el alcance sea ambiguo o se contradiga, o debas elegir algo que una persona querría revisar, elige la opción más conservadora y reversible, anótala y sigue. Cada decisión: qué, por qué, la alternativa descartada y dónde se aplicó.
- **Dónde se anota:** en el archivo que indique el pedido (por ejemplo `decisiones.md`). Si no indica ninguno, en "Decisiones" de la entrega. No inventes archivos.
- **Para revisar:** lo que cambia una regla del alcance para cumplir otra, un contrato, una dependencia o la configuración de un gate va además a "Para revisar" en la entrega, para que el orquestador o la persona lo vea sin leer todo.
- **Te detienes igual** si el mismo paso del DoD falla tres veces, si hace falta algo fuera del alcance (credenciales, push, publicar, borrar datos) o si dos reglas se contradicen y ninguna opción se puede deshacer.
- Sigue valiendo la regla de no commitear (sección 7), salvo que el pedido lo autorice por escrito.

Para orquestar una construcción grande por bloques (un plan, un brief común y un subagente por bloque), la receta está en [orquestacion.md](references/orquestacion.md).

## 2. Implementación

### Feature o enhancement

De adentro hacia afuera, con la estructura del perfil:

1. **Dominio:** modelos, interfaces de repositorio y use cases, con sus tests.
2. **Datos:** fuentes, modelos de datos, mappers e implementación del repositorio, con sus tests.
3. **DI:** el módulo de la feature.
4. **Entrada:** UI (ViewModel, estado, pantallas), controller o comando, con sus tests.
5. **Navegación o rutas.**

Una tarea a la vez. No toques código que no tenga que ver con ella.

**Tests:** con las librerías y el estilo que fije `AGENTS.md`, que mandan sobre las preferencias del perfil `hb-stack-*` (por ejemplo, fakes o mocks). Si no fija nada, los del perfil.

**Pantallas con estado.** Si la pantalla guarda estado (un formulario, un campo con error, una lista con scroll, un paso de un flujo), el DoD verde no basta: los fallos de recreación y de arranque en frío solo aparecían al ejecutar la app. Escribe tests **en la JVM** de la **recreación de la vista** y de la **muerte del proceso**: en Compose, `StateRestorationTester`; en Views, `recreate()` de `ActivityScenario` o Robolectric, y la restauración desde `savedInstanceState`. Recetas en [ciclo-de-vida.md](references/ciclo-de-vida.md).

### Bugfix

1. **Reproduce:** pasos, comportamiento esperado y comportamiento actual. Si el bug depende de un entorno que no controlas (un dispositivo, un navegador, un backend, datos reales), no ejecutes la app por tu cuenta en ese entorno: escribe la **reproducción manual** (precondiciones, el entorno que indique `AGENTS.md`, pasos numerados, esperado y actual) y entrégasela al usuario.
2. **Escribe un test que falle** por el bug, antes de corregir.
3. **Busca la causa raíz**, no el síntoma: pregunta "por qué" hasta llegar al origen.
4. **Corrección mínima.** El test nuevo pasa y los existentes también.
5. Revisa si el mismo defecto existe en código parecido y repórtalo.

**Bug complejo.** Si toca varios módulos o repos, no se reproduce con un test o puede tomar más de una sesión (o `AGENTS.md` lo pide), lleva una **bitácora** en la carpeta del reporte (`report.py --folder <slug>` te dice dónde, sección 6) con la plantilla [assets/bitacora.md](assets/bitacora.md): clasificación, evidencia, reproducción, causa raíz, plan, estado y siguiente paso. Si ya existe, léela primero y sigue desde su estado; actualízala al cerrar cada paso. Presenta el plan y **espera confirmación antes de tocar código**, salvo con el alcance aprobado (sección 1).

### Refactor

1. Asegura tests que cubran el comportamiento actual. Si no existen, créalos primero (tests de caracterización).
2. Avanza en pasos pequeños que no cambian el comportamiento y corre los tests en cada paso.
3. No mezcles cambios de comportamiento con el refactor. Si encuentras un bug, anótalo y trátalo aparte.

## 3. Changelog

Si el proyecto lleva `CHANGELOG.md` con `[Unreleased]`, o `AGENTS.md` pide documentar, agrega la entrada con las reglas de `hb-commit` (secciones estándar de Keep a Changelog, idioma del archivo).

## 4. Autorrevisión y Definition of Done

### Autorrevisión (antes del DoD)

El DoD no ve los fallos de diseño. Antes de correrlo, relee tu diff contra el **documento de alcance completo** (la spec, el `PLAN.md` o el issue entero), no solo contra el prompt de esta tarea: las contradicciones y los casos que el prompt no repite viven ahí. Recorre esta lista fija y corrige lo que encuentres:

1. **Estado y persistencia frente a los requisitos.** ¿Qué sobrevive a un arranque en frío, a la muerte del proceso y a recrear la pantalla? Cada dato que el alcance exige conservar debe vivir donde sobrevive (base local, `SavedStateHandle`, backend), no solo en memoria. Si un requisito choca con otro ("se conserva" frente a "vive en memoria"), no lo resuelvas en silencio: con el alcance aprobado, decídelo y anótalo (sección 1); si no, pregúntalo.
2. **`catch` demasiado amplios.** Atrapa las excepciones concretas, no `Exception`, `Throwable` ni una genérica como `IllegalArgumentException`, y nunca la cancelación de corrutinas. El mapeo de errores cubre todas las combinaciones que el contrato permite (un 401 sin cuerpo, por ejemplo).
3. **Dependencias sin uso.** Cada dependencia que agregaste tiene al menos un import que la use; si no, quítala. Si el alcance pide declararla aunque nada la use todavía, anótalo.
4. **Casos que el alcance pide y no se hicieron.** Recorre el alcance línea por línea: cachés, estados vacíos y de error, caminos negativos alcanzables desde la UI, valores de referencia, identificadores de test. Lo que quede fuera se hace o se declara en la entrega como pendiente.
5. **Reglas del `AGENTS.md`.** Comentarios (¿solo el porqué?), palabras o temas prohibidos, nombres, una declaración por archivo, idioma del código, de la documentación y de los textos. Búscalas con `grep` sobre el diff, no de memoria.

### Definition of Done

- Antes de correr el DoD de una unidad de otro repo, regístrala si no lo hiciste al pasarla a fuente: `report.py --unit <su fuente> --folder <slug>` (no la duplica).
- Corre **el DoD de cada unidad que tocaste**: la columna "DoD de la unidad" del modelo, con su `cd`, y el `## DoD` del proyecto, que compila la app con todo, si cambiaste la app, pasaste unidades a fuente, cambiaste algo que no es de ninguna unidad o un contrato que otras consumen, o la unidad no tiene build propio (una carpeta de feature). Sin modelo, los comandos de `## DoD`, en orden. En un repo vecino sin DoD en el modelo, el `## DoD` de su `AGENTS.md` ([unidades.md](references/unidades.md)).
- Si un paso falla, corrige y repite desde ese paso. **Si el mismo paso falla tres veces, detente** y reporta el error con tu diagnóstico.
- Un paso que el entorno no permite (por ejemplo, compilar iOS sin macOS) se marca `skipped` con el motivo. Nunca cuenta como `pass`.
- **Nunca debilites un gate para que pase**: nada de desactivar reglas, bajar umbrales de cobertura, `ignoreFailures`, `abortOnError = false` ni `@Suppress` sin motivo. Arregla la causa.
- Si `AGENTS.md` no define DoD, usa las tareas estándar del stack (Gradle: lint, test y build; npm: `lint`, `test` y `build`; Python: `ruff` y `pytest`) y propón agregarlas a `AGENTS.md`.

## 5. Previews de UI (opcional)

**Aplica solo si** `## Stack` dice Android o KMP **y** el cambio toca UI de Compose (un `XContent.kt` o los composables que usa). Si no, **omite este paso entero, sin agregar ninguna fila al DoD del reporte**: en un proyecto de otro stack, o con un cambio que no toca esa UI, no hay nada que marcar. No reemplaza a los tests de screenshots del proyecto: esos siguen siendo la regresión.

1. Lista los `@Preview` del módulo y quédate con los de los archivos que cambiaste. Pasa la carpeta del módulo de la app (por ejemplo `app`): sin ella la CLI toma el proyecto raíz y falla.
   ```bash
   android preview list app --format json
   ```
   **En KMP** la CLI no reconoce el módulo compartido (`shared`, con `com.android.kotlin.multiplatform.library`): pasa el de la app Android (`androidApp`) con `--all`, que incluye los previews de sus dependencias, entre ellos los de `commonMain`. En `render` usa también `androidApp`.
   ```bash
   android preview list androidApp --all --format json
   ```
   Todo `@Preview` envuelve su contenido en `Surface` (o en el wrapper de tema del proyecto, si ya lo incluye): sin él, el tema no pinta el fondo y el render en modo oscuro sale con el fondo claro, inútil para revisar el contraste. Si falta en uno que escribiste o tocaste, agrégalo antes de dibujar.
2. Dibújalos en la carpeta de previews de la tarea: la ruta `previews:` que imprimió `report.py --folder` (sección 6), tal cual, aunque pase por un enlace simbólico. No la escribas a mano. Cada `--fqn` es un nombre que devolvió `list`:
   ```bash
   android preview render app --fqn <fqn> --fqn <otro-fqn> --format json -o <la ruta previews: que imprimió report.py --folder>
   ```
   La primera vez la CLI descarga su paquete de render (unos 300 MB). Con `--daemon`, los renders siguientes son más rápidos.
3. **Mira cada imagen** y compárala con los criterios de aceptación: textos, orden, estados y tema. Si algo no coincide, corrige y vuelve a dibujar. Para datos exactos, agrega `--component-tree`: el JSON trae bounds, semántica y el archivo y la línea de cada componente.
4. Agrega cada imagen a `previews` en el meta de la tarea (sección 6), con la ruta que devolvió el render, lo que muestra y qué criterio verifica.
5. **Solo si aplica y no se pudo** (falta la CLI `android`, el proyecto no tiene un módulo de app Android que pasarle o el render falla), agrega al DoD del reporte un paso `Previews de UI` en `skipped` con el motivo, y sigue: no bloquea la entrega.

## 6. Reporte HTML

Se genera siempre, salvo que el usuario diga que no. El reporte es de esta skill: lo que git sabe (qué repos y qué archivos cambió la tarea, el antes, el después y el diff) lo calcula el script; el meta aporta lo que git no sabe.

1. **La carpeta de la tarea**, al empezar (sección 0). La línea `Carpeta de reportes: <ruta>` de `AGENTS.md` (o, si no la hay, `reports`) es la **base** común de las skills: esta tarea va en `<base>/implementation/<fecha>-<slug>/`, con `meta.json`, `report.html`, `snapshot.json`, `bitacora.md` y `previews/`. El script la crea y la deja fuera de git sin tocar el `.gitignore` del proyecto: la agrega a `.git/info/exclude` si git no la ignora (local; también en un worktree), deja la fila de la tarea "en curso" en `<base>/INDEX.md`, toma la foto inicial e imprime las rutas del meta, la bitácora, los previews, el índice y la foto. **Usa esas rutas tal cual.** La ruta del script es relativa a la carpeta de la skill:
   ```bash
   python3 -I <carpeta-de-la-skill>/scripts/report.py --folder <slug>
   ```
   - El slug sigue la convención de `AGENTS.md`; si no hay, el título en minúsculas con guiones.
   - Si ya existe una carpeta con ese slug de otro día, la tarea sigue ahí y conserva su foto. Una tarea vieja en el formato plano de antes (`<base>/<fecha>-<slug>.meta.json`) sigue plana, en la base. Con `{fecha}` y `{slug}` en la línea, la ruta se respeta tal cual. Una tarea empezada antes de 1.7.0 no tiene foto: el script no la toma tarde y el reporte usa `repos` del meta.
   - Si la ruta pasa por un enlace simbólico (una carpeta de contexto fuera del repo), el script escribe en la ruta real, solo comprueba que git ignore el enlace y avisa si no.
   - En un `git worktree` al que le faltan `AGENTS.md` o el enlace de la carpeta de contexto que el principal tiene fuera de git, el script se detiene sin escribir y da el `ln -s` para recrearlos: pásaselo al usuario; no los crees sin que él o el proyecto lo pidan.
   - Detalle: [reporte.md](references/reporte.md).
2. **Registra cada unidad en el momento**, en cuanto la pasas a fuente o corres su DoD: la ruta de su fuente (relativa a la raíz del repo principal) o su identificador del modelo. La anota en `repos` del meta (lo crea si falta) y en la foto; repetirlo no la duplica. El repo principal y las unidades del modelo entran solos si cambiaron.
   ```bash
   python3 -I <carpeta-de-la-skill>/scripts/report.py --unit <ruta> --folder <slug>
   ```
3. Escribe un meta **por tarea** en la ruta `meta:` que imprimió el script. Si ya existe (lo crea `--unit`), léelo y complétalo: **conserva `repos`**. Un `meta.json` compartido en la base lo pisa el siguiente bloque. Si el slug no es el título en minúsculas con guiones, ponlo en `slug`.

```json
{
  "project": "<nombre del proyecto>",
  "title": "Perfil de usuario",
  "type": "feature",
  "ticket": "<el código que dio el usuario o el del nombre de la rama>",
  "scope": "feature/profile",
  "description": "Una o dos oraciones sobre qué se hizo y por qué.",
  "date": "AAAA-MM-DD",
  "branch_note": "El usuario eligió seguir en la rama actual de cada repo.",
  "impact": [{ "label": "Pantallas afectadas", "value": "Perfil y edición del perfil" }],
  "diagrams": [{ "title": "Carga del perfil", "mermaid": "flowchart LR\n  A[Pantalla] --> B[ViewModel] --> C[Repositorio]", "description": "Qué muestra." }],
  "files": {
    "ruta/al/ArchivoNuevo.kt": { "why": "Qué aporta al diseño.", "layer": "dominio", "risk": "medio", "pros": ["Lo que gana"], "cons": ["Lo que cuesta"] },
    "ruta/al/modulo_modificado.py": { "before": "Qué limitación había.", "after": "Qué mejora el cambio.", "layer": "datos", "risk": "alto", "pros": ["…"], "cons": ["…"] },
    "ruta/al/componente-eliminado.ts": { "why": "Por qué se elimina.", "risk": "bajo", "pros": ["…"], "cons": ["…"] }
  },
  "groups": [
    { "match": "tests/screenshots/", "why": "Goldens regrabados de las pantallas del perfil." }
  ],
  "dod": [
    { "icon": "🧪", "name": "Tests", "command": "<comando de tests del DoD>", "status": "pass", "note": "", "output": "" }
  ],
  "previews": [
    { "name": "ProfileContentPreview", "image": "<la ruta previews: que imprimió report.py --folder>/ProfileContentPreview_0.png", "note": "Qué muestra y qué criterio verifica." }
  ]
}
```
   - `type`: `feature`, `bugfix`, `enhancement` o `refactor`. `status`: `pass`, `fail` o `skipped`. `date`: la fecha local.
   - Una explicación por archivo, sobre el impacto, no sobre el código. `output` solo en pasos que fallaron.
   - **Datos de análisis: complétalos siempre que puedas sostenerlos con lo que viste en el código.** Por archivo: `why` (o `before` y `after`), `risk` (`critico`, `alto`, `medio`, `bajo`), `pros` y `cons`, y `layer`, la capa según la arquitectura de `AGENTS.md`. Por reporte: al menos un diagrama Mermaid del flujo afectado en `diagrams`, `impact` y, en un bugfix, `severity` y `root_cause`; y `ticket`, el que dé el usuario o el que aparezca en el nombre de la rama. Lo que no puedas sostener, déjalo fuera: el script no muestra lo que falta ni lo vacío, ignora con un aviso un valor con formato inválido y nunca falla por ellos ([reporte.md](references/reporte.md)). Si analizaste un archivo y no tiene contras, escribe `"cons": []`: el reporte dice "Sin contras identificados"; sin el campo, no muestra nada. Si no tiene pros, `"pros": []`: no se muestra, pero cuenta como analizado; nunca inventes pros para completar el campo.
   - `branch_note`: qué se decidió con la rama (sección 0), sobre todo si nadie respondió y se siguió en la rama actual.
   - Los archivos masivos o generados (goldens, fixtures, snapshots) **no llevan una explicación cada uno**: se explican en grupo con `groups`. `match` es una carpeta (termina en `/`) o un patrón (`*.png`), y el grupo sale como una sola entrada con su lista de rutas. Un archivo con entrada propia en `files` se muestra aparte del grupo.
   - `previews` es opcional (sección 5). `image` es la ruta que devolvió `android preview render`: absoluta, relativa al repo o relativa a la carpeta de la tarea (`previews/<archivo>`). El script incrusta la imagen en el reporte.
   - **Varios repos:** las claves de un vecino son `<nombre>:<ruta>`. En `repos` puedes ponerle a cada unidad su `main_branch` y, si es publicada y está en fuente, su `pinned_version`. El cambio que pasa una unidad a fuente va en `temporary`, con cómo revertirlo: no cuenta como cambio. Los archivos de "Configuración local modificada a propósito" el script ya los deja fuera solo ([unidades.md](references/unidades.md)).
   - **DoD por unidad:** cada paso de una unidad lleva su nombre delante (`core-lib · Tests`) o `"unit": "<unidad>"`, y sale en la sección de esa unidad; los demás, en el DoD del proyecto.
4. Genera el reporte con el script de esta skill:
   ```bash
   python3 -I <carpeta-de-la-skill>/scripts/report.py --meta <ruta-del-meta> [--main-branch <rama>] [--base <base>]
   ```
   - **Qué entra:** el script compara cada repo con la foto. Entran el principal, las unidades del modelo y las registradas, si cambiaron después de la foto; lo que ya estaba sin commit antes y no cambió va a "Cambios no atribuidos", fuera de los conteos. El reporte empieza con un resumen global y sigue con una sección por unidad.
   - **Otros repos que cambiaron:** si el script lista un repo hermano que cambió y no es unidad (la carpeta padre puede tener proyectos ajenos), pregúntale al usuario si es de la tarea; si dice que sí, regístralo con `--unit` y vuelve a generar el reporte.
   - **Para `hb-review`:** `report.py --meta <meta.json> --attribution` dice en JSON, sin escribir nada, qué es de la tarea, con la misma lógica del reporte ([reporte.md](references/reporte.md)).
   - **Sin archivos de la tarea no hay reporte:** el script no lo escribe y dice la causa probable y el siguiente paso (registrar una unidad, pasar la base o, si la foto se tomó después de empezar a cambiar, `--ignore-snapshot`). Síguelo; no entregues un reporte vacío.
   - **Base:** sin `--base`, compara contra el `merge-base` de `HEAD` con la rama principal, así entra lo ya commiteado en la rama de trabajo. Pásale la rama principal del modelo con `--main-branch`; sin ella, toma la de `## Estructura` o prueba `origin/HEAD`, `origin/main`, `origin/master`, `main` y `master`, y si no encuentra ninguna compara contra `HEAD` y avisa. Si `AGENTS.md` fija otra base, pásala con `--base`, que manda. El reporte muestra la base usada.
   - El script saca el antes, el después y el diff de git (contra la base, incluidos los archivos nuevos sin trackear): **no copies código en el meta**. Al terminar, deja en la fila del índice el resultado del DoD (`DoD PASS`, `DoD FAIL`, `DoD PARTIAL` o `sin DoD`).
5. Si el script avisa de archivos sin explicación o de datos de análisis que faltan, complétalos (o agrupa los archivos) y vuelve a generarlo. Si avisa de una **posible migración de lenguaje** (un archivo de código borrado o vaciado cuyo equivalente aparece en otro lenguaje), confirma con el usuario que se pidió; si no, pregúntale antes de deshacerla (el aviso compara archivos del mismo lugar y con el mismo nombre: puede ser un cambio legítimo).

## 7. Entrega

- **No hagas commit** salvo que el usuario lo pida y `AGENTS.md` lo permita.
- **Entrega en el idioma del proyecto**: el resumen, las explicaciones del reporte, los commits propuestos, el texto del PR y la verificación van en el idioma que fija `AGENTS.md` (si no lo dice, el del `README`, el `CHANGELOG` o los últimos commits), aunque el pedido o el brief estén en otro. Revisa el idioma de lo que escribiste, no solo el del código.
- Entrega:
  - Un resumen de dos o tres líneas.
  - Los archivos creados, modificados y eliminados.
  - El resultado del DoD por paso.
  - La ruta del reporte (con los previews de UI, si los hubo) y la de la bitácora, si la hubo.
  - La **rama de trabajo** de cada repo que modificaste: la que eligió el usuario o, si nadie respondió, la actual de cada uno, dicho así (o el comando propuesto, si el proyecto no deja crear ramas).
  - Los commits propuestos, agrupados por unidad funcional y con mensajes según `hb-commit`; con varios repos, por repo y en el orden en que se integran.
  - El **orden de integración** de cada unidad publicada que cambiaste: PR del módulo → release del módulo (con `hb-release` en su repo) → PR de bump de la versión fijada en la app. La configuración que pasa a fuente nunca se commitea. Sin mecanismo de paso a fuente: el cambio llega a la app cuando se publique ([unidades.md](references/unidades.md)).
  - Los **cambios temporales** (por ejemplo, pasar una unidad a fuente) y cómo revertirlos, o "revertido" si `AGENTS.md` pide revertirlos.
  - Si el fuente de una unidad no coincide con la versión que fija la app, el aviso con las dos versiones.
  - Las correcciones al modelo de `## Estructura` que aplicaste y los mapas del módulo que creaste o actualizaste.
  - La **reproducción manual**, si el bug depende de un entorno que no controlas (sección 2).
  - El texto para el PR: qué cambia, por qué y cómo se verificó.
  - **Riesgos:** lo que el DoD no cubre y no pudiste probar ("no probado en dispositivo", una dependencia de la plataforma, un caso del alcance que quedó fuera).
  - Los **ítems de verificación en el dispositivo**, si hay algo que el DoD no pueda ver (siguiente apartado).

### Verificación en el dispositivo

Lista solo lo que el DoD y los tests no ven: el ciclo de vida real, los permisos de la plataforma, la red real, el hardware, la fluidez percibida. No es un recorrido de toda la feature.

- **Prioridad.** Primero los *imprescindibles* (si fallan, la entrega no sirve) y después los *opcionales*. Tope: 8 imprescindibles y 5 opcionales por entrega, salvo que el pedido fije otro. Si hay más, quédate con los de mayor riesgo y di cuántos dejaste fuera.
- **Respaldo.** Cada ítem cita el test que lo respalda (`Clase.nombre del test`) o queda marcado **sin test**. Dentro de su prioridad, los "sin test" van primero: ahí está el riesgo.
- **No prometas lo que el código no hace.** Escribe cada ítem desde un test o desde lo que leíste en el código, no desde la intención. Si afirma un comportamiento ("volver al inicio pide las cuentas otra vez"), el test o el código deben mostrarlo; si no, corrige el código o quita el ítem.
- **Formato:** qué hacer → qué debe verse → respaldo.

## Checklist

- [ ] `AGENTS.md`, modelo de estructura, perfil y referencias necesarias leídos; mapa del módulo de cada unidad que tocas, leído y al día.
- [ ] Carpeta de la tarea pedida antes de cambiar nada (`report.py --folder`, con su foto inicial).
- [ ] Unidades decididas y su código confirmado en el build; repos vecinos listos sin `pull`, `merge` ni `rebase` (o el acceso que falta, pedido); unidades publicadas en fuente con el mecanismo del modelo, como cambio temporal, y registradas con `--unit` al pasarlas a fuente o al correr su DoD.
- [ ] La rama de trabajo, en una sola pregunta (seguir en la actual o crear una con el nombre del usuario); sin respuesta, la actual de cada repo, dicho en la entrega y en el reporte (salvo que el proyecto no deje crear ramas).
- [ ] Criterios de aceptación claros; plan confirmado si hacía falta (también en un bug complejo, con su bitácora).
- [ ] Estructura y regla de dependencias del perfil respetadas.
- [ ] Tests nuevos con las librerías y el estilo de `AGENTS.md` (si no fija nada, los del perfil, con fakes); en un bugfix, el test que reproduce el bug o la reproducción manual.
- [ ] Pantallas con estado: tests en la JVM de recreación de la vista y de muerte del proceso.
- [ ] Patrones aplicados solo donde el problema los pedía.
- [ ] Changelog actualizado si el proyecto lo usa.
- [ ] Autorrevisión contra el alcance completo: estado y persistencia, `catch`, dependencias, casos pedidos y reglas del `AGENTS.md`.
- [ ] DoD de cada unidad tocada completo: cada paso en `pass` o `skipped` con motivo.
- [ ] Previews solo si `## Stack` es Android o KMP y el cambio toca UI de Compose: con `Surface`, dibujados en la ruta `previews:` del script, revisados e incluidos en el reporte. Si no aplica, sin fila en el DoD.
- [ ] Reporte generado en la carpeta de la tarea, con su fila en el índice, y ruta entregada; cambios temporales fuera del reporte y con cómo revertirlos; los otros repos que el script listó, preguntados; nunca un reporte vacío.
- [ ] Datos de análisis completos donde se pueden sostener con el código: por archivo, `why`, `risk`, `pros`, `cons` y `layer`; por reporte, un diagrama Mermaid del flujo afectado, `impact` y, en un bugfix, `severity` y `root_cause`.
- [ ] Orden de integración por unidad publicada (PR del módulo → release → bump) y aviso si el fuente no coincide con la versión fijada.
- [ ] Ítems de verificación en el dispositivo priorizados, con tope, y cada uno con su test o "sin test".
- [ ] Entrega en el idioma del proyecto.
- [ ] Sin commit automático.
