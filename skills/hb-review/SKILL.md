---
name: hb-review
description: 'Revisa código contra las reglas del proyecto (AGENTS.md), su perfil hb-stack-* y las prácticas de code review de la industria (guía de Google, Conventional Comments). Revisa el diff actual, una rama, un PR o archivos concretos, en cada repo que tocó la tarea; corre el DoD de cada unidad tocada, entrega hallazgos priorizados con veredicto y guarda el reporte en la carpeta de reportes. Tiene un modo rápido para orquestadores: revisa el diff de un bloque contra el alcance, sin volver a correr el DoD. No modifica código. Úsala cuando el usuario pida revisar código, hacer code review, revisar un PR o validar cambios antes de un commit ("revisa el código", "haz code review", "revisa el PR #12", "¿cumple con las reglas?", "revisión rápida del bloque", "/hb-review").'
license: MIT
metadata:
  author: hacybeyker
  version: "1.3.0"
  category: flow
  origin: "basada en code-reviewer"
---

# hb-review

Revisión de solo lectura: **no modifica código**. Lo único que escribe es su propio reporte (sección 4). Cada hallazgo cita la regla o el estándar que incumple, no una preferencia personal.

**Estándares:** la guía de code review de Google (aprueba cuando el cambio mejora la salud del código aunque no sea perfecto) y [Conventional Comments](https://conventionalcomments.org/) para el formato de los comentarios.

## 1. Alcance y contexto

1. Lee `AGENTS.md` y el perfil `hb-stack-*` del proyecto, y solo las referencias que el cambio toca (UI, testing, seguridad…). Sin `AGENTS.md`, revisa contra el perfil del stack detectado y los estándares generales, y dilo en el reporte.

   **Modelo de estructura.** Lee `## Estructura` de `AGENTS.md` y, si no existe, `### Repos relacionados` de `## Arquitectura` (el formato anterior). De ahí salen las unidades (su identificador, dónde está su fuente, cómo se consume, cómo pasarla a fuente y volver, su DoD, su repo y rama principal, y quién la publica y versiona), las variantes y entornos, el cliente HTTP, la configuración local modificada a propósito (no es un cambio ajeno, no se revisa como hallazgo y nunca se propone para commit), la línea `Repos vecinos` y la tabla "Documentos": lee solo los documentos cuya fila "Léelo cuando…" corresponde a la tarea, por su ruta exacta. Si lo que encuentras no coincide con el modelo, dilo en la entrega con la corrección; `hb-implement` y `hb-performance` la aplican en `## Estructura`, sobre la ruta real de `AGENTS.md` (`realpath AGENTS.md`). Sin modelo, sigue con lo que haya y ofrece `hb-setup`.

   **Mapa del módulo.** Antes de tocar o revisar una unidad, lee su mapa en la carpeta que dice la línea "Mapas del módulo" de `## Estructura` (`<carpeta de contexto>/modules/<identificador>.md`, con las subcarpetas del identificador). Si su `Commit analizado` no es el `HEAD` del repo de la unidad, mira solo `git -C <repo> diff <commit>..HEAD -- <ruta de la unidad>`. Si el mapa no existe o quedó atrás, créalo o actualízalo con lo que ya leíste, en su ruta real: arriba, `Commit analizado: <sha>` y la ruta de la unidad; después, Qué hace, Puntos de entrada, Flujos principales, Servicios que llama, Datos y persistencia, Patrones y convenciones, DoD de la unidad y Cuidado con. `hb-review` solo lo lee.

   Aquí el mapa es de solo lectura: si el de una unidad revisada no existe o quedó atrás, no lo escribas; dilo en el alcance del reporte para que `hb-implement` lo cree o lo actualice.
2. Define qué revisar:
   - Sin indicación: **cada repo de la tarea**, con su diff contra su base de comparación **y sus archivos sin trackear** (`git ls-files --others --exclude-standard`, con `git -C <repo>` en un repo vecino), que `git diff` no muestra: las clases nuevas de un cambio que aún no se commitea viven ahí; léelos completos.
     - **Repos de la tarea:** el principal y cada repo vecino del modelo (las unidades cuya "Fuente" está fuera del repo, como `../core-lib`) que tenga cambios. Si revisas una tarea de `hb-implement`, los que dice su atribución (abajo). Sin modelo, el repo actual.
     - **Base de comparación de cada repo:** la que fije `AGENTS.md`; si no, `git -C <repo> merge-base HEAD <rama principal>`, con la rama de "Repo y rama principal" (su ref remota, `origin/<rama>`, si existe; sin modelo, la primera que exista de `origin/HEAD`, `origin/main`, `origin/master`, `main` y `master`, la misma lista de `hb-implement`; si no hay ninguna, `HEAD`). El diff es `git -C <repo> diff <base de comparación>`: lo ya commiteado en la rama de trabajo y lo que aún no. En la rama principal al día, la base es `HEAD` y quedan el working tree y lo staged. Si el usuario pide solo lo que no está commiteado, `git diff HEAD`.
   - **Una tarea de `hb-implement`:** cuando el usuario o el orquestador nombran la tarea (su slug o su carpeta), o cuando en `<base>/INDEX.md` hay una sola fila de `hb-implement` que corresponde a la rama actual o al slug de la tarea; con varias, pregunta cuál. Su carpeta es `<base>/` más la carpeta de la columna Ruta de esa fila (vale también con `{fecha}` o `{slug}` en la línea `Carpeta de reportes:`). Revisa lo que es de la tarea, no todo lo que hay en cada repo: el script de `hb-implement` (1.8.0 o posterior) lo dice con la misma lógica de su reporte, en JSON y sin escribir nada; el meta puede no existir todavía si la carpeta ya tiene su foto. Pásale la misma base que usa el reporte: `--base` si `AGENTS.md` fija una; si no, `--main-branch` con la rama principal del modelo:

     ```bash
     cd <raíz-del-proyecto> && python3 -I <carpeta de hb-implement>/scripts/report.py --meta <carpeta de la tarea>/meta.json --attribution [--base <ref> | --main-branch <rama>]
     ```

     `<carpeta de hb-implement>`: junto a esta skill (`<carpeta-de-esta-skill>/../hb-implement`); si no está ahí, en `~/.claude/skills/hb-implement`, `~/.agents/skills/hb-implement` o las carpetas de skills del proyecto (`.claude/skills`, `.agents/skills`). Detalle de cada campo: [atribucion.md](references/atribucion.md). En corto:
     - **Con foto** (`photo: true`):
       - `repos`: los repos de la tarea (también una unidad del modelo que cambió sin registrarse), cada uno con su `path` (el `<repo>` de `git -C`), su `base` y sus `files`, que incluyen los nuevos sin trackear. Revisa esos archivos contra esa base.
       - `attribution: "mixed"`: ya tenía cambios sin commit al empezar. Revísalo con una nota en el alcance: su diff mezcla lo de antes con lo de la tarea; no le atribuyas a la tarea lo que no puedes separar (pregúntalo con `question`).
       - `attribution: "mixed-committed"`: ya tenía commits de la rama de antes de la tarea. Lo de la tarea es `git -C <repo> diff -M <task_diff_from> -- <ruta>` (con `old`, agrega también `<old>`); con `task_diff_from: null` (la rama se rebasó o recibió un merge después de la foto), trátalo como `mixed`.
       - `claimed`: archivos que el meta explica pero ya estaban en la foto: la foto se tomó tarde; pregunta y, si son de la tarea, corre de nuevo con `--ignore-snapshot`.
       - `unattributed`: lo que ya estaba antes de la tarea. **No es hallazgo de la tarea:** va en el alcance, en dos grupos. Lo que estaba sin commit no entra con la tarea: avísalo para que no se commitee con ella. Lo commiteado en la rama antes de la tarea entra igual al PR: si revisas para un PR, revísalo también; si no, dilo ("entra al PR sin revisar").
     - `excluded` (temporales y configuración local): fuera, salvo lo que el archivo traiga además de la tarea (paso 3: revisa solo eso). `skipped`: en el alcance, no se pudieron revisar. `others`: repos que cambiaron y no son unidades del modelo: pregunta con `question` si son de la tarea y, si lo son, revísalos.
     - **Sin foto** (`photo: false`: una tarea anterior a `hb-implement` 1.7.0, una carpeta sin `snapshot.json` o `--ignore-snapshot`): `repos` y `unattributed` no separan nada. Revisa como sin tarea (cada repo del modelo con cambios, contra su base) y dilo en el alcance.
     - **`empty`:** no quedó ningún archivo de la tarea. Lleva al alcance su causa y su siguiente paso. Si hay `unattributed`, pregunta si son de la tarea: si la foto se tomó tarde, lo son; entonces corre de nuevo con `--ignore-snapshot` o revisa como sin tarea. Sin nada revisado no hay veredicto ✅.
     - Si el script falla, no está o es anterior a 1.8.0 (responde "unrecognized arguments"), sigue como sin tarea y dilo en el alcance.
   - Un PR: `gh pr diff <n>` y `gh pr view <n>` (descripción, checks). Si la tarea tiene PR en otros repos (los enlaza la descripción), revísalos juntos.
   - Archivos o una feature: esos archivos completos.
3. **Lo que no se revisa:** la configuración local modificada a propósito (su subsección del modelo) y los cambios temporales de la tarea: `temporary` del meta de `hb-implement` (`<base>/implementation/<fecha>-<slug>/meta.json`, con `<base>` la carpeta de reportes de la sección 4) o la lista "cambios temporales" de su entrega. No son hallazgo ni cambio ajeno: déjalos fuera del diff (`git diff <base de comparación> -- . ':(exclude)<ruta>'`) y nómbralos en una línea del alcance. Si el archivo trae además cambios de la tarea, revisa solo esos. Lo que sí es `issue (blocking)`: que el cambio que pasa a fuente, o un temporal, esté en staging o haya entrado en un commit de la rama, porque nunca se commitea.
4. Entiende el propósito: lee la descripción del PR o los commits antes de opinar sobre el código.

## 2. Qué revisar

| Área | Preguntas |
| --- | --- |
| **Diseño** | ¿Respeta la arquitectura y la regla de dependencias del proyecto (`AGENTS.md`; el perfil donde el proyecto lo sigue)? ¿Cada cosa está en su capa y en su feature? ¿Los patrones usados se justifican, o sobra abstracción (KISS, YAGNI)? Usar el stack del proyecto (Views, MVP, Rx) no es un hallazgo; migrar fuera de `## Modernización` sí |
| **Unidades y repos** | ¿Cada cambio está en la unidad que le corresponde (el modelo y su mapa)? Si cambió una unidad publicada que la app necesita, ¿la entrega o el PR dicen el orden de integración (PR del módulo → release → bump en la app)? |
| **Funcionalidad** | ¿Hace lo que promete? ¿Casos borde, errores, concurrencia, cancelación? ¿Qué ve el usuario? |
| **Complejidad** | ¿Se entiende rápido? ¿Funciones o clases demasiado grandes? ¿Duplicación real (DRY)? |
| **Tests** | ¿La lógica nueva tiene tests con fakes? ¿Un bugfix trae el test que reproduce el bug? ¿Los tests fallarían si el código se rompiera? |
| **Nombres y comentarios** | ¿Nombres claros y consistentes con el proyecto? ¿Los comentarios explican el porqué, no el qué? |
| **Estilo y consistencia** | ¿Sigue las reglas del proyecto y del linter? (lo automático lo marca el DoD, no lo repitas a mano) |
| **Seguridad** | ¿Secretos, datos sensibles en logs, validación de entradas, almacenamiento, red? Usa el checklist de seguridad del perfil |
| **Dependencias** | ¿Versiones estables y en el catálogo del proyecto? ¿Hacía falta la dependencia? |
| **Documentación y versionado** | ¿Changelog en `[Unreleased]` si el proyecto lo usa? ¿Commits en formato Conventional Commits? ¿El PR es pequeño y de un solo propósito? |

Reconoce también lo que está bien hecho: un buen review no es solo una lista de problemas.

## 3. Verificación automática

Corre el DoD de **cada unidad que toca el cambio** y reporta cada paso por unidad (`pass`, `fail` o `skipped`). No corrijas nada.

- **De qué unidad es cada archivo:** de la unidad cuya "Fuente" es la ruta más larga que lo contiene (`features/payments/impl/…` es de `features/payments/impl`, no de la app; `../core-lib/…`, de `core-lib`). Lo que no cae en ninguna es de la unidad que es la app o, si no hay, del repo.
- **Qué corres:** su columna "DoD de la unidad"; si dice "el `## DoD` del proyecto" o no hay, el `## DoD` del `AGENTS.md` del repo de la unidad (en un repo vecino, el suyo). Si ese repo no tiene `## DoD`, márcalo `skipped` con ese motivo. Un mismo comando, una sola vez.
- **Además, el `## DoD` del proyecto** (el que compila la app con todo) si el cambio toca la app, pasa unidades a fuente, cambia algo que no es de ninguna unidad o un contrato que otras unidades consumen (una API pública, una interfaz, un esquema), o una unidad sin build propio (una carpeta de feature, cuyo DoD solo filtra tests): la misma regla de `hb-implement`.
- Sin modelo, el `## DoD` de `AGENTS.md`.
- Si el usuario pidió una revisión rápida o solo de lectura, marca el DoD como `skipped`. El modo rápido para orquestadores (ver abajo) también lo salta siempre.

## 4. Reporte

Cada hallazgo con formato Conventional Comments y su ubicación (en un repo vecino, `<repo>:<ruta>`):

```
archivo.kt:42 — issue (blocking): el ViewModel accede al repositorio directamente.
Regla: perfil, arquitectura → "El ViewModel solo habla con use cases".
Sugerencia: crear ObserveProfileUseCase e inyectarlo.
```

| Etiqueta | Uso | ¿Bloquea? |
| --- | --- | --- |
| `issue (blocking)` | Rompe una regla del proyecto, la arquitectura, la seguridad o la funcionalidad | Sí |
| `issue` | Incumple un estándar (tests faltantes, nombres, tokens, textos fijos) | Corregir antes de mergear |
| `suggestion` | Mejora concreta y opcional | No |
| `nitpick` | Detalle menor de estilo | No |
| `question` | Algo que no queda claro y necesita respuesta | Depende de la respuesta |
| `praise` | Algo bien resuelto | — |

Ordena por severidad. Agrupa los hallazgos repetidos en uno solo con todas sus ubicaciones.

**Veredicto:**
- ✅ **Aprobado:** sin `issue` y con el DoD en verde. Sin ningún archivo revisado no hay aprobación: dilo y di por qué.
- 🔄 **Cambios requeridos:** lista priorizada de lo que hay que corregir.

### Dónde se guarda

Además de entregarlo en el chat, guarda el reporte en **`<base>/review/<fecha>-<slug>/review.md`**, con su fila en **`<base>/INDEX.md`**. Formato del archivo, slug, fila del índice y exclusión de git: [donde-se-guarda.md](references/donde-se-guarda.md).

- `<base>`: la línea `Carpeta de reportes:` de `AGENTS.md` (con `{fecha}` o `{slug}`, la parte fija antes del primer marcador); sin ella, `reports`. Relativa a la raíz del repo principal, o absoluta.
- `review.md` es corto: alcance y repos revisados, DoD por unidad, hallazgos y veredicto.
- Fila del índice: Skill `hb-review`, Tipo `review` (o `review rápido`), Estado `aprobado` o `cambios requeridos`, y el enlace relativo a `review.md`. Agrega o reemplaza solo tu fila (clave: Skill + Slug).
- Fuera de git, como los demás reportes: la base suele estar ya excluida; si no, agrégala a `.git/info/exclude`, nunca a `.gitignore`.
- Escribe sobre la ruta real (`realpath`): la carpeta puede ser un enlace simbólico.
- Si el usuario pide no escribir archivos, entrega solo en el chat.

## 5. Después del review

- Esta skill **no modifica código**: escribir su propio reporte (`review.md`, su fila en `INDEX.md` y, si hace falta, la exclusión en `.git/info/exclude`) no es modificar código. Si el usuario pide aplicar las correcciones, usa `hb-implement`.
- Para un PR, publica el review en GitHub (`gh pr review`) solo si el usuario lo pide.
- Si el proyecto tiene instalados plugins de review (por ejemplo `pr-review-toolkit`), puedes sugerirlos como segunda pasada para tests, errores silenciosos o diseño de tipos.

## Modo rápido (para orquestadores)

Para quien delegó un bloque a un subagente y debe revisarlo antes de commitear, sin repetir el DoD que ya corrió. Se activa cuando el pedido lo dice ("revisión rápida del bloque", "modo rápido") o cuando un plan lo invoca por cada bloque.

- **Qué revisas:** el diff del bloque (`git diff HEAD`, o `git diff <base de comparación>...<rama>` si ya está commiteado; el orquestador lo indica) **más los archivos sin trackear** (`git ls-files --others --exclude-standard`: el orquestador no commitea antes de revisar, así que las clases nuevas del bloque no salen en `git diff`), **contra el documento de alcance** y el `AGENTS.md`. Si el bloque tocó varios repos, el diff y los archivos sin trackear de cada uno (el orquestador los indica; si no, los repos del modelo con cambios). Lee completos los archivos nuevos y los que tienen lógica (reglas de negocio, estado, persistencia, manejo de errores): la lista de archivos y el DoD en verde no bastan. Carga solo las referencias del perfil que toca el bloque.
- **Fuera de la revisión**, igual que en el modo normal: la configuración local modificada a propósito y los cambios temporales de la tarea. Si el orquestador te pasa la carpeta de la tarea de `hb-implement`, usa su atribución (sección 1): lo que ya estaba antes de la tarea no es hallazgo del bloque.
- **No corres el DoD:** lo corre el orquestador. Márcalo `skipped` con el motivo "lo corre el orquestador".
- **Qué buscas** (lo que el DoD no ve): estado y persistencia frente a los requisitos; `catch` demasiado amplios; dependencias sin uso; casos que el alcance pide y no están; decisiones del agente que cambian una regla del alcance; reglas del `AGENTS.md` (comentarios, palabras prohibidas, idioma); tests que no fallarían si el código se rompiera.
- **Qué no haces:** no repites lo que el linter ya cubre, no propones migraciones, no tocas código.
- **Devuelves poco y priorizado:** el veredicto en una línea (✅ listo para commitear, o 🔄 corregir antes), los hallazgos `issue (blocking)` e `issue` con ubicación y la regla o el requisito que incumplen, y las `question` que el orquestador debe resolver. Sin `nitpick` ni `praise`. Si no hay hallazgos, dilo en una línea.
- **El archivo es opcional:** guarda `review.md` y su fila en el índice solo si el orquestador lo pide, con Tipo `review rápido` y el slug que te indique.
- El orquestador decide qué hacer con el resultado: reanudar al subagente con los hallazgos o corregirlos él. Esta skill no corrige.
