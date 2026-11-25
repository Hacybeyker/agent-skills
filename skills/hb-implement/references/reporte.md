# Reporte: carpeta y campos opcionales

## Carpeta de reportes

`report.py` escribe en:

1. `--out`, si lo pasas.
2. La ruta de la línea `Carpeta de reportes: <ruta>` de `AGENTS.md`, con o sin acentos graves (en inglés, `Reports folder:`). Relativa a la raíz del repo, o absoluta.
3. `reports`, si no hay ninguna.

Esa ruta es la **base** común de las skills: `hb-implement` escribe en `<base>/implementation/`, `hb-performance` en `<base>/performance/` y `hb-review` en `<base>/review/`, y cada una deja su fila en `<base>/INDEX.md`.

| Línea | Carpeta de la tarea | Archivos |
| --- | --- | --- |
| `reports` (sin marcadores) | `reports/implementation/<fecha>-<slug>/` | `meta.json`, `report.html`, `bitacora.md` y `previews/` |
| `contexto/reports/{fecha}/{slug}` (con marcadores) | `contexto/reports/<fecha>/<slug>/`: la línea tal cual; la base es la parte fija, `contexto/reports` | Los mismos |
| Una tarea vieja en formato plano | `reports/` (la base), sin cambiar nada | `<fecha>-<slug>.meta.json`, `<fecha>-<slug>.html`, `<fecha>-<slug>.bitacora.md` y `previews/` de la base |

- `{fecha}` es la `date` del meta (`AAAA-MM-DD`) y `{slug}`, su `slug` o, sin él, el título en minúsculas con guiones. Con marcadores, `{slug}` es obligatorio y antes tiene que haber una carpeta fija: es la base, la que se deja fuera de git.
- **Qué carpeta toma**, en este orden: (1) si el meta ya vive en una carpeta de tarea, esa (un meta suelto en la base es del formato plano y sigue así); (2) si existe una carpeta con ese slug en **otra fecha**, la tarea sigue ahí; (3) sin marcadores, si existe `<base>/<fecha>-<slug>.meta.json` (o su `.html` o `.bitacora.md`) de cualquier fecha, la tarea sigue en formato plano; (4) si no, la carpeta nueva de hoy.
- `--folder <slug>` (con `--date`, opcional) crea la carpeta de la tarea, sin generar el reporte, e imprime:
  ```
  📁 Carpeta de la tarea: <ruta>[ (la tarea ya existía: sigue ahí)]
     meta: <ruta>
     bitácora, si hace falta: <ruta>
     previews: <ruta>
     índice: <ruta de INDEX.md>
  ```
  La carpeta `previews/` no se crea: la crea quien dibuja los previews.
- **Enlaces simbólicos.** Si la ruta pasa por un enlace (por ejemplo `contexto/`, que apunta a una carpeta fuera del repo), el script escribe en la ruta real (el enlace sigue siendo enlace) y git no mira más allá de él: comprueba que el enlace esté ignorado y, si no lo está, avisa sin escribir en `.git/info/exclude`. Una carpeta fuera del repo no necesita ignorarse.
- **Worktrees.** En un `git worktree` enlazado no existe lo que el worktree principal tiene fuera de git: `AGENTS.md` (enlace o archivo local) y el enlace de la carpeta de contexto. Si falta `AGENTS.md`, o el enlace por el que pasa la carpeta de reportes, el script se detiene sin escribir nada y da el comando para recrear cada uno (`cd <worktree> && ln -s <ruta real> <nombre>`): no escribe los reportes en otro lado. Una carpeta de reportes local (`reports/`, sin enlace) se crea en el worktree, como siempre. Con `--out`, no hace falta `AGENTS.md`.

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

El reporte dice la base usada: bajo la descripción con un solo repo, y en la tabla "Repositorios" con varios (por ejemplo, "merge-base con `origin/main` · `a1b2c3d`").

## Varios repos: versiones

En cada entrada de `repos`, opcionales: `"main_branch"` (arriba), `"pinned_version"`, la versión que fija la app, y `"source_version"`, lo que da `git -C <repo> describe --tags --always` en el fuente; sin ella, el script describe la base del repo (lo que había antes de la tarea). Si las dos no coinciden (sin contar una `v` delante), el reporte lo muestra como aviso y la tabla agrega la columna "Versión". Detalle del flujo: [unidades.md](unidades.md).

## Análisis del cambio

Todo es opcional y solo se muestra si viene en el meta. Úsalo cuando ayude a revisar, no por rellenar.

| Campo | Dónde | Qué es |
| --- | --- | --- |
| `risk` | Por archivo | Riesgo del cambio para el review: `critico`, `alto`, `medio` o `bajo`. Sale junto a la ruta. |
| `pros` | Por archivo | Lista de lo que gana el cambio. |
| `cons` | Por archivo | Lista de lo que cuesta. Vacía, el reporte dice "Sin contras identificados". |
| `severity` | Reporte | En un `bugfix`, la gravedad del bug, con la misma escala. |
| `impact` | Reporte | Lista de `{"label", "value"}`: a quién o a qué afecta, con datos (usuarios, pantallas, tiempos). |
| `root_cause` | Reporte | Texto: la causa raíz, no el síntoma. |
| `diagrams` | Reporte | Lista de `{"title", "mermaid", "description"}`: el código Mermaid de cada diagrama. |

**Escala** (para `risk` y `severity`): `critico`, puede romper datos, seguridad o un flujo principal; `alto`, cambia un contrato o lógica compartida; `medio`, lógica local cubierta por tests; `bajo`, cosmético, tests o documentación. Se acepta `crítico`.

```json
{
  "severity": "alto",
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
      "risk": "medio",
      "pros": ["Un solo lugar calcula el total"],
      "cons": []
    }
  }
}
```

- Un valor fuera de la escala o de otro tipo (una lista que no es lista, un diagrama sin `mermaid`) termina con un error claro y sin escribir el reporte.
- **Mermaid** se carga solo si hay `diagrams`: desde jsDelivr, con la versión exacta, integridad y `securityLevel: 'strict'`. El código va escapado en `<pre class="mermaid">`: sin conexión se lee como texto. Sin `diagrams`, el reporte no carga nada remoto.
