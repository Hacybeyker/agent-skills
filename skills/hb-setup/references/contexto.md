# Contexto de IA: versionado, local o en una carpeta externa

`AGENTS.md`, sus docs y las salidas de las skills (reportes, bitácoras) son el **contexto de IA** del proyecto. Unos equipos lo versionan con el código; otros prefieren no subirlo (el repo es de otro equipo, o no todos usan agentes). El modo se pregunta en el setup y queda escrito en `## Reglas del proyecto`, en la línea `Contexto de IA`.

| Modo | Dónde vive | Qué entra a git | Lo extenso | Mapas del módulo | Reportes por defecto |
| --- | --- | --- | --- | --- | --- |
| **Versionado** (por defecto) | En el repo | `AGENTS.md` y sus docs, como cualquier archivo. Los reportes no: van en `.git/info/exclude` | `docs/` | `docs/modules/`, fuera de git salvo `--module-maps versioned` | `reports` |
| **Local** | En el repo | Nada: `AGENTS.md`, `CLAUDE.md` (si aplica) y `contexto/` van en `.git/info/exclude` | `contexto/docs/` | `contexto/modules/` | `contexto/reports` |
| **Externo** | En una carpeta fuera del repo, la que indica el usuario | Nada: en el repo quedan enlaces simbólicos (`AGENTS.md`, `CLAUDE.md` si aplica y `contexto`) excluidos en `.git/info/exclude` | `contexto/docs/` | `contexto/modules/` | `contexto/reports` |

- **Nunca se edita `.gitignore`.** `.git/info/exclude` es local, no se commitea y, en un worktree, se encuentra con `git rev-parse --git-path info/exclude`.
- La carpeta de contexto se llama `contexto` (con `--carpeta`, otro nombre). En el modo externo, la carpeta externa replica esa estructura: `<externa>/AGENTS.md`, `<externa>/CLAUDE.md` y `<externa>/contexto/`.
- Un enlace se excluye **sin barra final** (`/contexto`, no `/contexto/`): para git, un enlace simbólico es un archivo, y un patrón con barra solo cubre carpetas.
- La ruta de la carpeta externa es de esta máquina: va en `AGENTS.md`, que en este modo no se versiona.
- **Reportes:** la carpeta es la base común. `hb-implement` escribe en `<base>/implementation/<fecha>-<slug>/`, `hb-performance` en `<base>/performance/` y `hb-review` en `<base>/review/<fecha>-<slug>/`; cada una agrega o actualiza su fila en `<base>/INDEX.md`.
- **En un `git worktree`** no están los enlaces ni los archivos locales del contexto, porque no están en git (`.git/info/exclude` sí es común a todos los worktrees). `contexto.py estado` lo detecta y da el `ln -s` para recrearlos; no los crees sin que el usuario o el proyecto lo pidan.

## `contexto.py`

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py estado
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py preparar --modo externo --externa <carpeta-fuera-del-repo>
```

- `estado` no cambia nada: el modo actual, las señales de Claude Code, la carpeta de contexto, los submódulos, los repos hermanos que el proyecto nombra y, en un worktree enlazado, lo que falta del contexto.
- `units` tampoco cambia nada: el inventario para `## Estructura` ([estructura.md](estructura.md)).
- `preparar` revisa todo antes de cambiar algo. Con un conflicto, sale con error y no toca nada.
- **No pisa.** En el modo externo, si la carpeta externa ya tiene `AGENTS.md` o contenido en `contexto/`, lo usa tal cual y lo avisa. Si en el repo ya hay un `AGENTS.md` real, o uno versionado (en los modos local y externo), se detiene: moverlo o sacarlo de git es una decisión del usuario.
- **Escribe en el destino, no sobre el enlace.** Algunas herramientas reemplazan un enlace por un archivo al guardar: en el modo externo, escribe `AGENTS.md` en la ruta que imprime el script.
- `CLAUDE.md` con `@AGENTS.md`, solo si hay `CLAUDE.md` o `.claude/`, o con `--claude si`. Uno que ya existe no se toca: si no importa `@AGENTS.md`, el script lo dice.
- `--reportes` acepta `{fecha}` y `{slug}`; se excluye la parte fija (`contexto/reports/{fecha}/{slug}` → `contexto/reports`). Dentro de la carpeta de contexto ya está cubierta.
- `--module-maps versioned`, solo en el modo versionado, deja los mapas del módulo en git; por defecto (`local`) se agrega `/docs/modules/` a `.git/info/exclude`. Si ya hay mapas versionados y se piden locales, se detiene sin cambiar nada.

## Cambiar de modo

El script no migra. Para pasar de versionado a local o externo, el usuario saca los archivos de git (`git rm --cached AGENTS.md` y los de sus docs) en un commit propio y después se corre `preparar`. Para volver a versionar, reemplaza los enlaces por los archivos y quita sus líneas de `.git/info/exclude`. Confírmalo antes con el usuario: cambia lo que ve el resto del equipo.
