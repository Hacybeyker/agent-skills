# <Nombre del proyecto>

<Qué es y para quién, en una o dos oraciones.>

## Stack

Lo que el proyecto tiene hoy, literal y con versiones. Los agentes trabajan con este stack; ver `## Modernización`.

- Perfil: <hb-stack-mobile-kotlin | ninguno>
- Variante: <android | kmp>
- UI: <Compose | Views con ViewBinding | Views con DataBinding | mixto: dónde cada uno>
- Presentación: <MVVM con UDF | MVVM con LiveData | MVP | MVI>
- Asincronía: <corrutinas y Flow | RxJava 2/3 | callbacks>
- DI: <Hilt | Dagger 2 | Koin | manual>
- Navegación, red, persistencia, serialización, imágenes, tests: <librerías y versiones>
- Build: <AGP, Kotlin, Gradle, KSP o kapt, minSdk/targetSdk>

## Comandos

| Para | Comando |
| --- | --- |
| Compilar | `<comando>` |
| Ejecutar | `<comando>` |
| Tests | `<comando>` |

## DoD

Antes de dar una tarea por terminada, en este orden:

1. `<comando de calidad>`
2. `<comando de tests>`
3. `<comando de build>`

## Arquitectura

<Cómo está organizado el proyecto hoy: módulos, capas, features principales, dónde viven los contratos de presentación. Si coincide con el perfil, "sigue el perfil" y las excepciones con su motivo; si no, descríbela tal cual y los agentes la respetan.>

## Modernización

- <ninguna decidida | lista de decisiones tomadas por el usuario, cada una con alcance y fecha: "las pantallas nuevas van en Compose (2026-11)", "Rx se reemplaza por corrutinas solo al tocar una clase">
- Los agentes no migran ni proponen migrar fuera de lo decidido aquí. Cuando una tarea toque una oportunidad clara, una línea al final del entregable, sin plan.

## Reglas del proyecto

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
