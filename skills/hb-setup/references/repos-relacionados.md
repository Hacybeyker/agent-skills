# Repos relacionados y dependencias con código local

Un proyecto puede depender de otros repos que se trabajan en local: un módulo compartido, una librería propia, un catálogo de versiones. `hb-implement` los lee (y a veces los cambia) en la misma tarea, así que `AGENTS.md` dice dónde están, cómo se incluyen y cómo pasar a su código.

## Detectar

No asumas ningún mecanismo: busca lo que el proyecto ya usa.

1. `contexto.py estado`: los submódulos (`.gitmodules`) y los repos hermanos, en la carpeta padre, que algún archivo versionado nombra como `../<nombre>`.
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

En `## Arquitectura`, la subsección `### Repos relacionados` de la plantilla. Por ejemplo, para un repo principal que consume `modulo-a` como paquete publicado y lo puede pasar a código local con un archivo de configuración propio:

```markdown
### Repos relacionados

| Repo | Ruta | Qué contiene | Cómo se incluye en local |
| --- | --- | --- | --- |
| modulo-a | `../modulo-a` | Reglas de pagos compartidas; se publica como `modulo-a` 1.2.0 | `dependencias.local` (ignorado por git): `modulo-a=../modulo-a` |

- El agente necesita acceso a estas carpetas además de la del proyecto (cada agente tiene su forma de sumar directorios de trabajo). Si no puede leer una, lo dice y se detiene.
- **modulo-a** (publicado): pasar a código local con `cp dependencias.local.ejemplo dependencias.local`; volver con `rm dependencias.local`. Es un cambio local: no se commitea.
```

- La ruta es **relativa** a la raíz del proyecto: nada de rutas absolutas de una máquina.
- "Cómo se incluye en local" describe lo que el proyecto ya usa, con el archivo y la línea, o el comando.
- Por cada dependencia publicada con código local: qué se publica (coordenada o nombre), dónde está su repo, **cómo pasar a código local y cómo volver** (el comando o el cambio exacto) y que el cambio es local y no se commitea. Si ese cambio toca un archivo versionado, dilo: `hb-implement` lo trata como temporal.
- Si `AGENTS.md` pide revertir el cambio al terminar cada tarea, anótalo en la misma línea.

## Versiones que vienen de fuera

Si el stack toma sus versiones de un catálogo, un BOM o un plugin de convenciones publicado, y su repo está clonado al lado (es un repo relacionado), lee las versiones de ahí y anota la fuente en `## Stack`: "las define `<coordenada>` (copia local en `../<repo>`)". Si no hay copia local, anota la fuente remota y deja las versiones sin valor inventado.
