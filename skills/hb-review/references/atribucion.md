# Lo que es de la tarea: la atribución de `hb-implement`

`hb-implement` toma una **foto inicial** al empezar cada tarea (la rama, el `HEAD` y los archivos sin commit de cada repo). Con ella, su reporte separa lo que cambió la tarea de lo que ya estaba. `hb-review` usa la misma separación, para no marcar como hallazgo un cambio de otra persona ni dejar fuera una unidad que la tarea cambió sin registrarla.

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta de hb-implement>/scripts/report.py --meta <carpeta de la tarea>/meta.json --attribution [--base <ref> | --main-branch <rama>]
```

- Hace falta `hb-implement` 1.8.0 o posterior: una anterior responde "unrecognized arguments". Entonces, o si el script falla, revisa como sin tarea y dilo en el alcance.
- Solo lee: no escribe archivos (git solo refresca la caché de `.git/index`, como cualquier `git status`). Si el meta todavía no existe pero la carpeta tiene la foto (`snapshot.json`), igual responde; si la carpeta del meta tiene su foto, manda esa.
- La salida es JSON en ASCII: los acentos van escapados (`\u00f3`) y un nombre de archivo que no es UTF-8 sale con `\udcXX`; búscalo con `git -C <repo> status`.
- **La base:** la misma que usa el reporte. Si `AGENTS.md` fija una, pásala con `--base`; si no, la rama principal del modelo con `--main-branch` (sin ella, el script prueba `origin/HEAD`, `origin/main`, `origin/master`, `main` y `master`). `--ignore-snapshot` trata la tarea como si no tuviera foto.
- **La tarea:** la que nombran el usuario o el orquestador, o la única fila de `hb-implement` de `<base>/INDEX.md` que corresponde a la rama actual o al slug; con varias, pregunta. Su carpeta es `<base>/` más la carpeta de la columna Ruta de esa fila.

## Los campos

| Campo | Qué es | Qué hace `hb-review` |
| --- | --- | --- |
| `task` | `{slug, folder, meta}`: la tarea, con rutas relativas a la raíz del proyecto | En el alcance |
| `photo` | Si hubo foto inicial | Ver "Con foto y sin foto" |
| `repos[]` | Los repos con cambios de la tarea: el principal (si cambió después de la foto), las unidades del modelo que cambiaron (aunque no se registraran) y las registradas | Una fila por repo en el alcance |
| `repos[].name`, `main`, `units` | El nombre del repo, si es el principal y las unidades del modelo que viven en él | En el alcance |
| `repos[].path` | La ruta del repo desde la raíz del proyecto (`.` el principal, `../core-lib` un vecino): el `<repo>` de `git -C` | Para los comandos de git |
| `repos[].base`, `base_text` | La base de comparación que usa el reporte (la ref para git) y su descripción | La misma para el diff |
| `repos[].branch`, `branch_before`, `photo_head` | La rama de ahora, la del inicio si cambió (si no, `null`) y el `HEAD` del repo en la foto | En el alcance |
| `repos[].in_photo` | Si el repo estaba en la foto. Uno que no estaba cuenta entero como de la tarea (y `notes` lo dice) | Revísalo entero y dilo en el alcance |
| `repos[].files[]` | Los archivos de la tarea: `path`, `status` (`A`, `M` o `D`), `old` (la ruta anterior, si se renombró), `untracked` (si es nuevo y git todavía no lo sigue), `attribution`, `note` y `task_diff_from` | Se revisan |
| `unattributed[]` | Lo que ya estaba antes de la tarea: `repo` (el nombre o, sin foto, la ruta), `repo_path` (la ruta para `git -C`), `path`, `reason` y `claimed_by_meta` | Ver "Con foto y sin foto" |
| `claimed[]` | Archivos que el meta explica como de la tarea pero ya estaban así en la foto: la foto se tomó tarde | Pregunta si son de la tarea; si lo son, corre de nuevo con `--ignore-snapshot` |
| `excluded[]` | `{path, why}`: los cambios temporales del meta y la configuración local modificada a propósito. La ruta es relativa al repo principal; la de un vecino va como `<nombre>:<ruta>` | Fuera de la revisión, salvo lo que el archivo traiga además de la tarea |
| `unchanged[]` | Los nombres de los repos sin cambios desde la foto (también el principal, si no cambió) | Nada que revisar |
| `skipped[]` | `{name, reason}`: repos de la tarea que quedaron fuera (git no los leyó) | En el alcance: no se pudieron revisar |
| `others[]` | `{path, detail}`: otros repos que cambiaron y no son unidades del modelo (sin foto, los que tienen cambios sin commit) | Pregunta con `question` si son de la tarea; si lo son, revísalos |
| `notes[]` | Los avisos del script | Los que cambian el alcance, en el alcance |
| `empty` | Si no quedó ningún archivo de la tarea: por qué y el siguiente paso; si no, `null` | Ver "Sin nada de la tarea" |

## Con foto y sin foto

- **Con foto** (`photo: true`): `unattributed` es lo que ya estaba antes de la tarea y **no es hallazgo de la tarea**. Va en el alcance, en dos grupos:
  - **sin commit desde antes de la tarea:** de otra persona o de otro trabajo; no entra con la tarea, así que avisa para que no se commitee con ella;
  - **commiteado en la rama antes de la tarea:** entra al PR igual; si revisas para un PR, revísalo también, y si no, dilo ("entra al PR sin revisar").
- **Sin foto** (`photo: false`: una tarea anterior a `hb-implement` 1.7.0, una carpeta sin `snapshot.json` o `--ignore-snapshot`): no hay forma de separar lo de antes. `repos` son el principal y los registrados, y `unattributed` lista los cambios sin commit de las demás unidades ("sin foto inicial: no se sabe si es de la tarea"). Revisa como sin tarea: cada repo del modelo con cambios, contra su base, y dilo en el alcance.

## Archivos mezclados

- **`mixed`:** el archivo ya tenía cambios sin commit al empezar y la tarea lo cambió otra vez. La foto guarda su hash, no su contenido, así que su diff contra la base mezcla los dos cambios. Revísalo y dilo en el alcance; lo que no puedas atribuir a la tarea, pregúntalo con `question` en vez de marcarlo como `issue`.
- **`mixed-committed`:** el archivo ya tenía commits de la rama de antes de la tarea. Lo de la tarea es `git -C <path del repo> diff -M <task_diff_from> -- <ruta>` (`task_diff_from` es el `HEAD` de la foto; si el archivo se renombró, agrega también `<old>`). Revisa ese diff: el resto es de antes. Si `task_diff_from` es `null`, la rama se rebasó o recibió un merge después de la foto y ese diff traería cambios ajenos: trátalo como `mixed`.

## Sin nada de la tarea

Con `empty`, no quedó ningún archivo de la tarea. Lleva al alcance la causa y el siguiente paso que da el texto. Si hay `unattributed`, pregunta si son de la tarea: si la foto se tomó después de empezar a cambiar, lo son; entonces corre de nuevo con `--ignore-snapshot` o revisa como sin tarea. Sin ningún archivo revisado no hay veredicto ✅.

## En `review.md`

En "Alcance", debajo de la tabla de repos, una línea por cada grupo que no se revisó o se revisó con nota (los nombres son inventados):

```markdown
- Foto inicial: sí (tarea `fix-login`).
- Antes de la tarea, sin commit (no se revisa y no entra con la tarea): `shop-auth:src/main/kotlin/com/example/auth/Pago.kt`.
- Antes de la tarea, commiteado en la rama (entra al PR sin revisar): `shop-auth:src/main/kotlin/com/example/auth/Cupon.kt`.
- Mezclados: `shop-auth:src/main/kotlin/com/example/auth/Notas.kt` (ya tenía cambios sin commit: el diff incluye los de antes); `shop-auth:src/main/kotlin/com/example/auth/Sesion.kt` (revisado desde el HEAD de la foto, `1a2b3c4`).
- Otros repos que cambiaron y no son de la tarea: `../billing-tools` (pregunta abierta: ¿es de la tarea?).
```

La columna "Sin trackear" de la tabla del alcance cuenta los archivos con `untracked: true`.
