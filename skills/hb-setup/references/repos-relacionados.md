# Repos relacionados y dependencias con código local

Un proyecto puede depender de otros repos que se trabajan en local: un módulo compartido, una librería propia, un catálogo de versiones. `hb-implement` los lee (y a veces los cambia) en la misma tarea, así que `AGENTS.md` dice dónde están, cómo se incluyen y cómo pasar a su código. Cada uno es una **unidad** de `## Estructura` ([estructura.md](estructura.md)); este documento detalla las preguntas 2 y 3: dónde está el fuente y cómo se pasa a él.

## Detectar

No asumas ningún mecanismo: busca lo que el proyecto ya usa.

1. `contexto.py units`: los repos vecinos que nombra la configuración, **clonados o no** (un vecino sin clonar sale como "SIN CLONAR": pregunta la URL de su remoto), con su remoto y su rama principal. `contexto.py estado` suma los submódulos (`.gitmodules`).
2. Las rutas locales en la configuración del proyecto: `git grep -n -E '\.\./[A-Za-z0-9._-]+'` y los archivos de configuración local que el proyecto documenta, aunque git los ignore (suelen guardar rutas de cada máquina).
3. Las dependencias **publicadas** (un artifact compilado, un paquete, un catálogo o un BOM remoto) que el build puede reemplazar por su código local. Algunos lugares donde mirar:

   | Ecosistema | Señales |
   | --- | --- |
   | Gradle | `includeBuild(...)` en `settings.gradle(.kts)`, `dependencySubstitution`, una propiedad que activa la ruta local |
   | npm, pnpm, Yarn | `workspaces`, `pnpm-workspace.yaml`, dependencias `file:`, `link:` o `workspace:` |
   | Python | `pip install -e ../<repo>`, `-e ../<repo>` en `requirements*.txt`, rutas `path = ...` en `pyproject.toml` |
   | Go | `replace ... => ../<repo>` en `go.mod`, `go.work` |
   | Swift, CocoaPods | `.package(path:)` en `Package.swift`, `:path =>` en el `Podfile` |
   | Maven | módulos con `<relativePath>`, un perfil que apunta a una versión local |
   | Propio del proyecto | un archivo de configuración o una variable de entorno que el build lee para elegir entre local y publicado |

   Son ejemplos, no una lista cerrada: si el proyecto usa otra cosa, descríbela tal cual.
4. Si no se puede deducir, pregúntalo junto con las demás preguntas.

## Documentar

Cada repo vecino y cada dependencia publicada con código local es una fila de la tabla de unidades de `## Estructura`. Por ejemplo, para un repo principal que consume `core-lib` como paquete publicado y lo puede pasar a código local con un archivo de configuración propio:

```markdown
| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal | Publica y versiona |
| --- | --- | --- | --- | --- | --- | --- |
| `core-lib` | `../core-lib` | Publicada: `core-lib`, versión fijada en `dependencias.conf` | A fuente: `cp dependencias.local.ejemplo dependencias.local`; volver: `rm dependencias.local` | `cd <ruta del proyecto>/../core-lib && make check` | `https://git.example.com/team/core-lib.git`, `main` | la persona, con `hb-release` en ese repo |
```

- La ruta es **relativa** a la raíz del proyecto: nada de rutas absolutas de una máquina.
- "Cómo se consume" dice qué se publica (coordenada o nombre) y el archivo donde se fija su versión, sin el número: cambia con cada bump.
- "Pasar a fuente y volver" es el cambio exacto para cada sentido, con el archivo y la línea, o el comando. Si no hay ningún mecanismo, "sin mecanismo": `hb-implement` trabaja entonces solo en el repo de la unidad y avisa que el cambio llega a la app al publicarse.
- Si ese cambio toca un archivo versionado y queda hecho en la máquina, va también en "Configuración local modificada a propósito": las skills no lo cuentan como cambio ajeno ni lo proponen para commit. Si `AGENTS.md` pide revertirlo al terminar cada tarea, anótalo en la misma celda.
- Debajo de la tabla, la línea de acceso a las carpetas y la línea `Repos vecinos` (clonar y crear ramas, o no).

Un `AGENTS.md` anterior lo tiene en `### Repos relacionados` de `## Arquitectura`: las skills lo siguen leyendo como respaldo, y al migrar sus filas pasan a esta tabla.

## Versiones que vienen de fuera

Si el stack toma sus versiones de un catálogo, un BOM o un plugin de convenciones publicado, y su repo está clonado al lado (es un repo relacionado), lee las versiones de ahí y anota la fuente en `## Stack`: "las define `<coordenada>` (copia local en `../<repo>`)". Si no hay copia local, anota la fuente remota y deja las versiones sin valor inventado.
