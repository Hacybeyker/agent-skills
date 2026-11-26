# Reporte: carpeta, foto inicial, qué entra y datos de análisis

## Carpeta de reportes

`report.py` escribe en:

1. `--out`, si lo pasas.
2. La ruta de la línea `Carpeta de reportes: <ruta>` de `AGENTS.md`, con o sin acentos graves (en inglés, `Reports folder:`). Relativa a la raíz del repo, o absoluta.
3. `reports`, si no hay ninguna.

Esa ruta es la **base** común de las skills: `hb-implement` escribe en `<base>/implementation/`, `hb-performance` en `<base>/performance/` y `hb-review` en `<base>/review/`, y cada una deja su fila en `<base>/INDEX.md`.

| Línea | Carpeta de la tarea | Archivos |
| --- | --- | --- |
| `reports` (sin marcadores) | `reports/implementation/<fecha>-<slug>/` | `meta.json`, `report.html`, `snapshot.json`, `bitacora.md` y `previews/` |
| `contexto/reports/{fecha}/{slug}` (con marcadores) | `contexto/reports/<fecha>/<slug>/`: la línea tal cual; la base es la parte fija, `contexto/reports` | Los mismos |
| Una tarea vieja en formato plano | `reports/` (la base), sin cambiar nada | `<fecha>-<slug>.meta.json`, `<fecha>-<slug>.html`, `<fecha>-<slug>.bitacora.md` y `previews/` de la base; sin foto |

- `{fecha}` es la `date` del meta (`AAAA-MM-DD`) y `{slug}`, su `slug` o, sin él, el título en minúsculas con guiones. Con marcadores, `{slug}` es obligatorio y antes tiene que haber una carpeta fija: es la base, la que se deja fuera de git.
- **Qué carpeta toma**, en este orden: (1) si el meta ya vive en una carpeta de tarea, esa (un meta suelto en la base es del formato plano y sigue así); (2) si existe una carpeta con ese slug en **otra fecha**, la tarea sigue ahí; (3) sin marcadores, si existe `<base>/<fecha>-<slug>.meta.json` (o su `.html` o `.bitacora.md`) de cualquier fecha, la tarea sigue en formato plano; (4) si no, la carpeta nueva de hoy.
- `--folder <slug>` (con `--date`, opcional) crea la carpeta de la tarea y toma la foto inicial, sin generar el reporte, e imprime:
  ```
  📁 Carpeta de la tarea: <ruta>[ (la tarea ya existía: sigue ahí)]
     meta: <ruta>
     bitácora, si hace falta: <ruta>
     previews: <ruta>
     índice: <ruta de INDEX.md>
     foto inicial: <ruta de snapshot.json> (<cuántos repos: el principal, N unidades y N repos hermanos>)
  ```
  La carpeta `previews/` no se crea: la crea quien dibuja los previews.
- **Enlaces simbólicos.** Si la ruta pasa por un enlace (por ejemplo `contexto/`, que apunta a una carpeta fuera del repo), el script escribe en la ruta real (el enlace sigue siendo enlace) y git no mira más allá de él: comprueba que el enlace esté ignorado y, si no lo está, avisa sin escribir en `.git/info/exclude`. Una carpeta fuera del repo no necesita ignorarse.
- **Worktrees.** En un `git worktree` enlazado no existe lo que el worktree principal tiene fuera de git: `AGENTS.md` (enlace o archivo local) y el enlace de la carpeta de contexto. Si falta `AGENTS.md`, o el enlace por el que pasa la carpeta de reportes, el script se detiene sin escribir nada y da el comando para recrear cada uno (`cd <worktree> && ln -s <ruta real> <nombre>`): no escribe los reportes en otro lado. Una carpeta de reportes local (`reports/`, sin enlace) se crea en el worktree, como siempre. Con `--out`, no hace falta `AGENTS.md`.

## Foto inicial: `snapshot.json`

`--folder` la toma al empezar la tarea, antes de cambiar nada. Guarda, por repo, su ruta (relativa a la raíz del repo principal), su papel (`main`, `unit` o `sibling`), las unidades del modelo que viven en él, la rama, el `HEAD` y los archivos sin commit (modificados, borrados o sin rastrear) con su hash de contenido, el mismo que da `git hash-object --no-filters`.

- **Qué repos mira:** el principal; cada repo git hermano (las subcarpetas directas de la carpeta padre del principal, sin los otros worktrees del mismo repo); y el repo de cada fuente de la tabla de unidades de `## Estructura` (o de "Repos relacionados", el formato anterior). Una unidad sin clonar queda en `missing_units`.
- **Rápido con muchos repos:** un solo `git status` por repo (sin locks ni reescribir el índice), en paralelo; los hashes se calculan sin procesos. Con más de 50 repos hermanos tarda lo que el más lento.
- **Sin fallar:** una carpeta sin permiso o un repo que git no puede leer queda en `unreadable` (o con `error`), se avisa y la foto sigue.
- **Una sola vez:** si la carpeta ya tiene foto, se conserva la del inicio. Si la tarea ya tenía meta, reporte o bitácora sin foto (empezó antes de 1.7.0), no se toma tarde: contaría sus propios cambios como previos.
- Si la foto ya encuentra cambios sin commit en el principal o en una unidad (sin contar la configuración local modificada a propósito), el script los lista: si no son de la tarea, avísale al usuario antes de empezar.

## Registrar una unidad: `--unit`

```bash
python3 -I <carpeta-de-la-skill>/scripts/report.py --unit <ruta> --folder <slug>
```

En cuanto una unidad se pasa a fuente o se corre su DoD. `<ruta>` es la de su fuente, relativa a la raíz del repo principal (`../core-lib`), o su identificador de `## Estructura`. La anota en `repos` del meta (con su `main_branch` del modelo, si la hay; si el meta no existe, lo crea solo con eso) y en `registered` de la foto. No duplica, no toca el resto del meta, no toma la foto y no cambia el índice. Si el meta no es un JSON válido, no lo toca y lo dice. Una ruta del repo principal no hace falta registrarla.

## Qué entra al reporte

Al generar, el script compara cada repo con la foto (un `git status` por repo, otra vez en paralelo):

| Repo | Qué pasa |
| --- | --- |
| El principal, una unidad del modelo o una registrada (`--unit` o `repos`), que cambió después de la foto (otro `HEAD` u otros archivos sin commit) | Entra, aunque no esté en `repos` |
| El mismo, sin cambios después de la foto | No entra; sus archivos sin commit van a "Cambios no atribuidos" |
| Otro repo hermano que cambió durante la tarea | No entra: la salida lo lista con el comando `--unit` para registrarlo si el usuario dice que es de la tarea |
| Otro repo hermano sin cambios después de la foto | Nada |

Dentro de un repo que entra, cada archivo cambiado contra la base se compara con la foto:

- **Cambió después de la foto:** es de la tarea.
- **Ya estaba sin commit y no cambió**, o ya estaba commiteado en la rama antes de la foto: va a **"Cambios no atribuidos"**, una sección plegada que no entra en los conteos.
- **Ya estaba sin commit y además cambió:** entra con un aviso (su diff contra la base mezcla los dos cambios), en el archivo y en el resumen.

**Sin foto** (una tarea vieja, o `--ignore-snapshot`): entran el principal y `repos` del meta, como hasta 1.6.0; los repos hermanos y las unidades con cambios sin commit que no están en `repos` salen en "Cambios no atribuidos", y la salida avisa con el comando `--unit` de cada uno.

**Foto tomada tarde.** Si la carpeta se pidió después de empezar a cambiar, los cambios de la tarea quedan como previos. El script lo nota cuando el meta explica un archivo que ya estaba así en la foto, o cuando no queda ningún archivo de la tarea, y sugiere volver a generar con `--ignore-snapshot` (y registrar con `--unit` cada repo vecino que cambió).

## Sin reportes vacíos

Si no queda ningún archivo de la tarea, el script **no escribe el reporte** (ni toca el índice: la fila sigue "en curso") y termina con un error sin traceback que dice la causa probable y el siguiente paso: los cambios están en un repo que no es unidad (registrarlo con `--unit`), ya estaban antes de la foto (`--ignore-snapshot` si la foto se tomó tarde), son todos temporales, ningún repo cambió después de la foto, o ningún repo tiene cambios contra su base (pasar `--base`).

## Aviso de migración de lenguaje

Un archivo de código fuente **borrado, vaciado o reducido a comentarios** (con, a lo sumo, la declaración de paquete o los imports) cuyo equivalente del mismo repo, con el mismo nombre base, aparece con otra extensión de código (`LoginTest.java` vaciado y `LoginTest.kt` nuevo), o un renombre a otra extensión, sale como aviso en el resumen, en los dos archivos y en la salida: una migración de lenguaje que nadie pidió. No cuenta las cabeceras (`.h`, `.hpp`).

## Cómo se ve

- **Resumen global:** archivos nuevos, modificados y eliminados, unidades, resultado del DoD, la decisión de la rama (`branch_note`), los avisos (sin foto, migración de lenguaje, archivos con cambios previos, versiones) y la tabla de unidades (rama, base, versión, conteos y DoD de cada una).
- Después, causa raíz, impacto, diagramas y previews, si vienen.
- **Una sección por unidad** (el principal y cada vecino): su fuente, las unidades del modelo que viven en ese repo, la rama (y la del inicio, si cambió), la base, los conteos, el DoD de la unidad y sus archivos por estado; cada archivo con antes y después (o por qué), diff, riesgo, capa, pros y contras, y sus avisos. Los grupos (`groups`) salen dentro de su unidad.
- Al final, "Cambios no atribuidos" (plegado), "Cambios temporales" y el DoD del proyecto (los pasos que no son de una unidad).
- **Tema claro y oscuro:** el mismo sistema de `hb-performance` (sus tokens, copiados en `assets/report-template.html`): el del sistema por defecto, un botón para cambiarlo y la preferencia guardada en `localStorage` (dentro de `try`/`catch`: sin almacenamiento, se ve igual). Al imprimir, siempre claro. Es un HTML autónomo: las imágenes van incrustadas y solo se carga Mermaid si hay diagramas.

## Índice: `<base>/INDEX.md`

Una fila por tarea, con la clave Skill + Slug. Si no existe, el script lo crea con esta cabecera:

```markdown
# Índice de reportes

Una fila por tarea. Cada skill agrega o actualiza solo sus filas (clave: Skill + Slug).

| Fecha | Skill | Slug | Tipo | Estado | Ruta |
| --- | --- | --- | --- | --- | --- |
| 2026-11-25 | hb-implement | perfil-de-usuario | feature | DoD PASS | [implementation/2026-11-25-perfil-de-usuario/report.html](implementation/2026-11-25-perfil-de-usuario/report.html) |
```

- `--folder` deja la fila en `en curso` (con el `type` del meta si ya existe; si no, el de la fila o `—`). Al generar el reporte, el `type` del meta y `DoD PASS`, `DoD FAIL`, `DoD PARTIAL` o `sin DoD`. Volver a pedir la carpeta de una tarea terminada la deja otra vez `en curso`: se retomó.
- **Fecha**: la de la tarea (la de su carpeta), no la de la actualización.
- **Ruta**: enlace relativo a la carpeta del índice, calculado con las dos rutas bajo la base tal como se escribió, así sirve aunque la base pase por un enlace. Los espacios van como `%20`.
- Solo cambia su fila: si existe, la reemplaza en su lugar; si no, la agrega al final de la tabla. No toca otras filas ni otras líneas. Un `INDEX.md` sin esa cabecera recibe la tabla al final, sin borrar nada.
- Se escribe sobre la ruta real: un `INDEX.md` que es enlace sigue siendo enlace.

## Configuración local

Los archivos de "### Configuración local modificada a propósito" de `## Estructura` (rutas relativas a la raíz del proyecto, también `../<vecino>/…`) quedan fuera de los cambios del reporte aunque el meta no los nombre, y salen en "Cambios temporales" con ese motivo. Si la tarea además los cambió (por ejemplo, para pasar otra unidad a fuente), ponlos en `temporary` con cómo revertir ese cambio: manda esa entrada.

## Base de comparación

Cada repo se compara contra su base:

- La explícita, si la hay: `--base` (principal) o `"base"` en su entrada de `repos`.
- Si no, el `merge-base` de `HEAD` con su **rama principal**: `--main-branch` (principal) o `"main_branch"` en `repos`, la del modelo; si no, `origin/HEAD`, `origin/main`, `origin/master`, `main` o `master`. Con una rama principal de nombre `<rama>`, se prefiere `origin/<rama>` si existe.
- Sin ninguna, `HEAD`, con un aviso: lo ya commiteado en la rama no sale en el reporte.
- Un repo **sin commits** (recién creado) se compara contra el árbol vacío: todo lo que tiene es nuevo.
- El puntero de un **submódulo** que cambia cuenta como un archivo modificado, con su ruta.

El reporte dice la base usada: bajo la descripción con un solo repo, y en la tabla "Repositorios" con varios (por ejemplo, "merge-base con `origin/main` · `a1b2c3d`").

## Varios repos: versiones

En cada entrada de `repos`, opcionales: `"main_branch"` (arriba), `"pinned_version"`, la versión que fija la app, y `"source_version"`, lo que da `git -C <repo> describe --tags --always` en el fuente; sin ella, el script describe la base del repo (lo que había antes de la tarea). Si las dos no coinciden (sin contar una `v` delante), el reporte lo muestra como aviso y la tabla agrega la columna "Versión". Detalle del flujo: [unidades.md](unidades.md).

## Análisis del cambio

El flujo **los completa siempre que pueda sostenerlos con lo que vio en el código**; el script nunca falla por ellos. Todo campo ausente o vacío (un texto vacío, una lista vacía) simplemente no se muestra, sin sección vacía; un valor con formato inválido se ignora con un aviso en la salida y el reporte sale igual. Al terminar, la salida dice qué datos de análisis faltan.

| Campo | Dónde | Qué es |
| --- | --- | --- |
| `why`, `before`, `after` | Por archivo | Por qué se crea o se elimina; qué limitación había y qué mejora el cambio. |
| `risk` | Por archivo | Riesgo del cambio para el review: `critico`, `alto`, `medio` o `bajo`. Sale junto a la ruta. |
| `pros` | Por archivo | Lista de lo que gana el cambio. |
| `cons` | Por archivo | Lista de lo que cuesta. |
| `layer` | Por archivo | La capa según la arquitectura del `AGENTS.md` (`dominio`, `datos`, `presentación`…). Sale junto a la ruta. |
| `severity` | Reporte | En un `bugfix`, la gravedad del bug, con la misma escala. |
| `impact` | Reporte | Lista de `{"label", "value"}`: a quién o a qué afecta, con datos (usuarios, pantallas, tiempos). |
| `root_cause` | Reporte | Texto: la causa raíz, no el síntoma. |
| `diagrams` | Reporte | Lista de `{"title", "mermaid", "description"}`: al menos uno, del flujo afectado. |
| `ticket` | Reporte | El código de la tarea: el que dé el usuario o el que aparezca en el nombre de la rama. |
| `branch_note` | Reporte | Qué se decidió con la rama de trabajo (por ejemplo, que nadie respondió y se siguió en la actual). |

Lo que el flujo completa siempre que puede: por archivo, `why` (o `before` y `after`), `risk`, `pros` y `cons`; por reporte, al menos un diagrama, `impact` y, en un bugfix, `severity` y `root_cause`. `layer` y `ticket` son opcionales.

**Escala** (para `risk` y `severity`): `critico`, puede romper datos, seguridad o un flujo principal; `alto`, cambia un contrato o lógica compartida; `medio`, lógica local cubierta por tests; `bajo`, cosmético, tests o documentación. Se acepta `crítico`.

```json
{
  "severity": "alto",
  "ticket": "SHOP-1234",
  "root_cause": "El total se calculaba antes de aplicar el descuento.",
  "impact": [{ "label": "Pagos afectados", "value": "Los que usan cupón" }],
  "diagrams": [
    {
      "title": "Cálculo del total",
      "mermaid": "flowchart LR\n  A[Carrito] --> B[Descuento] --> C[Total]",
      "description": "El descuento se aplica antes del total."
    }
  ],
  "files": {
    "pagos/total.py": {
      "before": "Sumaba sin descuento.",
      "after": "Aplica el descuento primero.",
      "layer": "dominio",
      "risk": "medio",
      "pros": ["Un solo lugar calcula el total"],
      "cons": ["Cambia el orden de dos llamadas que otros módulos observan"]
    }
  }
}
```

- Lo que decide qué entra al reporte sí se valida antes de escribir: `repos` y `temporary` (listas de objetos con `path`), `slug` y `date`. Si no sirven, el script termina con un error claro y sin escribir nada.
- **Mermaid** se carga solo si hay `diagrams`: desde jsDelivr, con la versión exacta, integridad y `securityLevel: 'strict'`. Cada diagrama se dibuja en claro y en oscuro, y el tema elige cuál se ve (al imprimir, el claro). El código va escapado en `<pre class="mermaid">`: sin conexión se lee como texto. Sin `diagrams`, el reporte no carga nada remoto.
