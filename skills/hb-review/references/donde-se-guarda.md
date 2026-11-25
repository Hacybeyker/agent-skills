# Dónde se guarda el review

Lo que escribe `hb-review` al terminar: un `review.md` por revisión y su fila en el índice común de reportes. Son sus únicos archivos: no toca el código, el mapa del módulo ni los reportes de otras skills.

## Dónde

1. **La base**, la misma de `hb-implement` y `hb-performance`: el valor de la línea `Carpeta de reportes: <ruta>` de `AGENTS.md`, en cualquier parte del archivo (también `Carpeta de los reportes` o `Reports folder`); es lo primero entre acentos graves. Sin la línea, `reports`.
   - Con `{fecha}` o `{slug}`, la base es la parte fija antes del primer marcador (`contexto/reports/{fecha}/{slug}` → `contexto/reports`).
   - Relativa a la raíz del repo principal, o absoluta.
2. **La carpeta de la revisión:** `<base>/review/<fecha>-<slug>/`, con la fecha de hoy (`AAAA-MM-DD`). Si ya existe una con ese slug de otro día (una segunda ronda de la misma tarea: `find <base>/review -maxdepth 1 -type d -name '????-??-??-<slug>'`, que no falla en zsh si no hay ninguna), sigue en esa.
3. **El slug:** el de la convención de `AGENTS.md`; si no hay, el de la tarea que revisas (el mismo de su fila de `hb-implement` en el índice), `pr-<número>` para un PR, o el título del cambio en minúsculas con guiones. Sin `|` ni `/`.

## `review.md`

Corto: lo que hace falta para decidir. Una ronda nueva reemplaza el archivo y dice, arriba, qué ronda es y el veredicto de la anterior. La plantilla, con un ejemplo inventado:

```markdown
# Review: reintentos en el cobro

- Fecha: <AAAA-MM-DD> · Tipo: review · Ronda: 2 (la 1: cambios requeridos)
- Veredicto: 🔄 Cambios requeridos (1 issue (blocking), 1 issue, 1 suggestion)
- Revisado contra: `AGENTS.md` (con `## Estructura`), perfil `hb-stack-<familia>`, referencias de testing y seguridad

## Alcance

| Repo | Rama | Base de comparación | Archivos | Sin trackear | Unidades |
| --- | --- | --- | --- | --- | --- |
| `app-shell` (principal) | `feat/payments-retry` | merge-base con `origin/main` (`1a2b3c4`) | 4 | 1 | `app-shell` |
| `feature-payments` | `feat/payments-retry` | merge-base con `origin/main` (`5d6e7f8`) | 3 | 2 | `feature-payments` |

- Fuera a propósito: `local-modules.json` (configuración local modificada a propósito).
- Mapas del módulo: `feature-payments`, leído; `app-shell`, quedó atrás (lo actualiza `hb-implement`).
- Diferencias con el modelo: ninguna.

## DoD

| Unidad | Comando | Resultado |
| --- | --- | --- |
| `feature-payments` | `cd <ruta del proyecto>/../feature-payments && ./gradlew check` | pass |
| `app-shell` | `cd <ruta del proyecto> && ./gradlew :app:check` | fail: `RetryPolicyTest` |

## Hallazgos

feature-payments:src/main/kotlin/…/RetryPolicy.kt:42 — issue (blocking): reintenta también los errores 4xx.
Regla: alcance → "solo se reintentan los errores de red y los 5xx".
Sugerencia: filtrar por tipo de error antes de reintentar.

(los demás, en el formato de la sección 4 de la skill y ordenados por severidad)

## Veredicto

🔄 Cambios requeridos:
1. Filtrar los errores que se reintentan (`RetryPolicy.kt:42`).
2. …
```

- **Alcance:** una fila por repo revisado; "Unidades", las que toca el cambio en ese repo. Debajo, lo que quedó fuera a propósito (la configuración local y los temporales), el estado de los mapas del módulo y, si las hay, las diferencias con `## Estructura` con su corrección.
- **DoD:** una fila por comando, con la unidad; `skipped` con su motivo (modo rápido, revisión solo de lectura, un repo sin `## DoD`).
- **Hallazgos:** los mismos del chat, en Conventional Comments. En el modo rápido, sin `nitpick` ni `praise`.
- **Veredicto:** el de la skill, con la lista priorizada si hay cambios requeridos.

## La fila en `<base>/INDEX.md`

El índice es común a las skills. Si no existe, créalo con este encabezado exacto; tu fila va en la tabla:

```markdown
# Índice de reportes

Una fila por tarea. Cada skill agrega o actualiza solo sus filas (clave: Skill + Slug).

| Fecha | Skill | Slug | Tipo | Estado | Ruta |
| --- | --- | --- | --- | --- | --- |
| 2026-11-25 | hb-review | payments-retry | review | cambios requeridos | [review/2026-11-25-payments-retry/review.md](review/2026-11-25-payments-retry/review.md) |
```

- **Clave:** Skill (`hb-review`) + Slug, comparadas sin los espacios de alrededor. Si tu fila existe, reemplaza **solo esa línea**; si no, agrégala al final de la tabla. Nunca toques las filas de otras skills ni las demás líneas del archivo.
- **Fecha:** la de la carpeta (la de la primera ronda), no la de hoy.
- **Tipo:** `review`, o `review rápido` en el modo para orquestadores.
- **Estado:** el veredicto, `aprobado` o `cambios requeridos`.
- **Ruta:** enlace relativo a la carpeta de `INDEX.md`, `[review/<fecha>-<slug>/review.md](review/<fecha>-<slug>/review.md)`, calculado desde la base tal como está escrita (sin resolver enlaces), con los espacios del destino como `%20`.
- En las celdas, `|` se escribe `\|` y un salto de línea, como un espacio.
- Si el archivo existe pero no tiene esa cabecera exacta, agrega la tabla al final, sin borrar nada.

## Fuera de git

Los reportes nunca entran a un commit. Si la base está fuera del repo (una ruta absoluta), no hay nada que hacer. Si está dentro:

1. Si algún tramo de la base es un enlace simbólico (por ejemplo `contexto`, una carpeta de contexto fuera del repo), git no mira dentro del enlace: comprueba que ignore el enlace mismo (`git check-ignore -q contexto`). Si no lo ignora, no escribas la exclusión: avisa que hay que agregar `/contexto` (sin barra final) a `.git/info/exclude`.
2. Si no hay enlaces: `git check-ignore -q <base>/review/<fecha>-<slug>/review.md`. Si git no lo ignora, agrega `/<base>/` al archivo que imprime `git rev-parse --git-path info/exclude` (local, y vale también en un worktree). Nunca edites `.gitignore`.

## Enlaces simbólicos y worktrees

- Escribe `review.md` e `INDEX.md` sobre su ruta real (`realpath`): si la base pasa por un enlace simbólico, algunas herramientas reemplazan el enlace por un archivo al guardar.
- En un `git worktree`, `AGENTS.md` y la carpeta de contexto pueden faltar, porque sus enlaces no están en git. Si falta `AGENTS.md`, o la carpeta de contexto por la que pasa la base, no crees una carpeta de reportes nueva: entrega el review solo en el chat y di cómo recrear el enlace (lo dice `contexto.py estado` de `hb-setup`).
