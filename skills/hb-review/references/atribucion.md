# Lo que es de la tarea: la atribución de `hb-implement`

`hb-implement` toma una **foto inicial** al empezar cada tarea (la rama, el `HEAD` y los archivos sin commit de cada repo). Con ella, su reporte separa lo que cambió la tarea de lo que ya estaba. `hb-review` usa la misma separación, para no marcar como hallazgo un cambio de otra persona ni dejar fuera una unidad que la tarea cambió sin registrarla.

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-esta-skill>/../hb-implement/scripts/report.py --meta <carpeta de la tarea>/meta.json --attribution
```

Solo lee: no escribe el reporte, ni el índice, ni el meta. Acepta `--base`, `--main-branch` e `--ignore-snapshot`, como el reporte. Si el meta todavía no existe pero la carpeta tiene la foto (`snapshot.json`), igual responde.

## Los campos

| Campo | Qué es | Qué hace `hb-review` |
| --- | --- | --- |
| `photo` | Si la tarea tiene foto inicial | Sin foto, revisa todo el diff de los repos de la tarea y lo dice en el alcance |
| `repos[]` | Los repos de la tarea: el principal, las unidades del modelo que cambiaron después de la foto (aunque no se registraran) y las registradas | Uno por fila en el alcance |
| `repos[].base`, `base_text` | La base de comparación que usa el reporte | La misma para el diff |
| `repos[].branch`, `photo_head` | La rama de ahora y el `HEAD` del repo en la foto | En el alcance |
| `repos[].files[]` | Los archivos de la tarea (`path`, `status` A/M/D, `old` si se renombró), también los nuevos sin trackear | Se revisan |
| `files[].attribution` | `task`, `mixed` o `mixed-committed` | Ver abajo |
| `unattributed[]` | Lo que ya estaba antes de la tarea (`repo`, `path`, `reason`) | No es hallazgo: una línea en el alcance |
| `excluded[]` | Cambios temporales del meta y la configuración local modificada a propósito | Fuera de la revisión, nombrados en el alcance |
| `unchanged[]` | Unidades sin cambios desde la foto | Nada que revisar |
| `skipped[]` | Unidades que quedaron fuera (git no las leyó), con su causa | En el alcance: no se pudieron revisar |
| `others[]` | Otros repos que cambiaron y no son de la tarea | En el alcance, sin revisarlos |
| `notes[]` | Los avisos del script | Los que cambian el alcance, en el alcance |
| `empty` | Si no hay ningún archivo de la tarea, por qué | Dilo y no inventes alcance |

## Archivos mezclados

- **`mixed`:** el archivo ya tenía cambios sin commit al empezar y la tarea lo cambió otra vez. La foto guarda su hash, no su contenido, así que su diff contra la base mezcla los dos cambios. Revísalo y dilo en el alcance; lo que no puedas atribuir a la tarea, pregúntalo con `question` en vez de marcarlo como `issue`.
- **`mixed-committed`:** el archivo ya tenía commits de la rama de antes de la tarea. Lo de la tarea es `git -C <repo> diff <task_diff_from> -- <ruta>` (`task_diff_from` es el `HEAD` de la foto). Revisa ese diff; el resto es de antes.

## En `review.md`

En "Alcance", una línea por cada grupo que no se revisó, con su motivo:

```markdown
- Antes de la tarea (no se revisa): `shop-auth:src/main/kotlin/com/example/auth/Pago.kt` (sin commit desde antes de la tarea).
- Mezclados: `shop-auth:src/main/kotlin/com/example/auth/Notas.kt` (ya tenía cambios sin commit: el diff incluye los de antes).
- Otros repos que cambiaron y no son de la tarea: `../billing-tools`.
```
