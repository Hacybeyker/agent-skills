# <Nombre del proyecto>

<Qué es y para quién, en una o dos oraciones.>

## Stack

Lo que el proyecto tiene hoy, literal y con versiones. Los agentes trabajan con este stack; ver `## Modernización`.

- Perfil: <hb-stack-mobile-kotlin | ninguno>
- Variante: <android | kmp | quita la línea si el perfil no tiene variantes>
- Lenguaje y runtime: <con versiones>
- UI: <Compose | Views con ViewBinding | Views con DataBinding | el framework web o de escritorio | mixto: dónde cada uno | no aplica>
- Presentación: <MVVM con UDF | MVVM con LiveData | MVP | MVI | el patrón del framework>
- Asincronía: <corrutinas y Flow | RxJava 2/3 | async/await | callbacks>
- DI: <Hilt | Dagger 2 | Koin | el contenedor del framework | manual>
- Navegación o rutas, red, persistencia, serialización, imágenes, tests: <librerías y versiones>
- Build: <herramienta y versiones: AGP, Kotlin, Gradle, KSP o kapt, minSdk/targetSdk | el gestor de paquetes y el bundler | el backend de build>
- Versiones de fuera del repo: <"las define <catálogo, BOM o plugin publicado> (<coordenada o URL>); copia local en `<ruta>`" | quita la línea si todas están en el repo>

## Comandos

| Para | Comando |
| --- | --- |
| Compilar | `<comando>` |
| Ejecutar | `<comando>` |
| Tests | `<comando>` |

## DoD

Antes de dar una tarea por terminada, en este orden:

1. Formato: `cd <ruta del proyecto> && <formateador, solo si está configurado>`
2. Checks, tests y build, en una sola invocación: `cd <ruta del proyecto> && <todos los checks, los tests y el build>`

<Fuera del DoD: lo que corre el CI y no puede hacer fallar un PR, con su motivo | quita la línea si no hay nada>
Origen: <los pasos de verificación del CI (<archivos>) | DoD derivado del build; el proyecto no tiene CI>.

## Arquitectura

<Cómo está organizado el proyecto hoy: módulos, capas, features principales, dónde viven los contratos de presentación. Si coincide con el perfil, "sigue el perfil" y las excepciones con su motivo; si no, descríbela tal cual y los agentes la respetan.>

## Estructura

Las unidades del proyecto y cómo se trabaja con cada una. Las skills lo leen antes de tocar código y lo corrigen si no coincide con lo que encuentran. Describe lo estable: nada de estados del momento.

### Unidades

| Unidad | Fuente | Cómo se consume | Pasar a fuente y volver | DoD de la unidad | Repo y rama principal | Publica y versiona |
| --- | --- | --- | --- | --- | --- | --- |
| `<identificador: ruta desde la raíz de su repo, o la carpeta del repo vecino>` | `<ruta relativa: . o app/ o ../core-lib>` | <Es la app / En fuente (módulo del build) / Publicada: `<coordenada>` <versión> en `<archivo>`> | <— / A fuente: <cambio exacto>; volver: <cambio exacto> / sin mecanismo> | `cd <ruta del proyecto> && <comando acotado a la unidad>` | <este repo / `<URL del remoto>`>, `<rama principal>` | <con la app / la persona, con `hb-release` / el workflow `<nombre>` al crear el tag> |

- El agente necesita **acceso a la carpeta** de cada unidad que está fuera del repo (cada agente tiene su forma de sumar directorios de trabajo). Si no puede leer una, lo dice y se detiene. <Quita la línea si todas están en el repo.>
- Repos vecinos: <clonar los que falten y crear ramas de trabajo | no clonar ni crear ramas>.

### Variantes y entornos

| Variante o entorno | Para qué sirve | Servicios funcionales | Para probar y medir |
| --- | --- | --- | --- |
| `<nombre>` | <desarrollo, QA, tienda…> | <Sí: <qué backend> / No: <mocks, sin red>> | <Sí / No> |

### Cliente HTTP

- <`<archivo desde la raíz del proyecto>` (unidad `<identificador>`): <qué construye y con qué librería> | Ninguno: el proyecto no hace llamadas HTTP>

### Configuración local modificada a propósito

<Quita esta subsección si no hay ninguna.>

- `<ruta>`: <para qué queda modificado>. No es un cambio de ninguna tarea y no se commitea.

### Documentos

| Documento | Léelo cuando… |
| --- | --- |
| `<docs/archivo.md o contexto/docs/archivo.md>` | <la situación en la que hace falta> |

### Mapas del módulo

- En `<docs | contexto>/modules/<identificador>.md`, <fuera de git (en `.git/info/exclude`) | versionados con el código>. Antes de tocar una unidad, lee su mapa; si no existe, créalo; si su `Commit analizado` quedó atrás, actualízalo solo con el diff desde ese commit.

## Modernización

- <ninguna decidida | lista de decisiones tomadas por el usuario, cada una con alcance y fecha: "las pantallas nuevas van en Compose (2026-11)", "Rx se reemplaza por corrutinas solo al tocar una clase">
- Los agentes no migran ni proponen migrar fuera de lo decidido aquí. Cuando una tarea toque una oportunidad clara, una línea al final del entregable, sin plan.

## Reglas del proyecto

- Contexto de IA: <versionado con el código | local, no se versiona: en `.git/info/exclude` | fuera del repo, en `<carpeta>`, con enlaces simbólicos excluidos en `.git/info/exclude`>. Lo extenso, en `<docs/ | contexto/docs/>`.
- Carpeta de reportes: `reports`
- <Reglas propias que el perfil no cubre, con su motivo.>

## Git

- Commits: Conventional Commits, en <español | inglés>, sin emoji.
- Rama principal: `<main>`. Se trabaja en ramas cortas y se integra por PR con squash.
- La IA <no commitea: deja los cambios y entrega el mensaje | commitea solo cuando se le pide>.
- Pide aprobación antes de `git push`, de crear un release y de publicar.

## Versionado y release

- SemVer. La versión vive en `<archivo>` y el código de build sube de 1 en 1.
- Tags `vX.Y.Z`, creados por <la persona | el workflow `<nombre>`>.
- `CHANGELOG.md` con Keep a Changelog: cada cambio entra en `[Unreleased]`.
- Notas de tienda: `<ruta>` (<idiomas>).

## Seguridad

- <Datos sensibles del proyecto y reglas específicas. Lo general está en el perfil.>
