# <Nombre del proyecto>

<Qué es y para quién, en una o dos oraciones.>

## Stack

- Perfil: <hb-stack-mobile-kotlin | ninguno>
- Variante: <android | kmp>
- <Tecnologías clave que el perfil no indica.>

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

Sigue el perfil. Particularidades de este proyecto:

- <Módulos, features principales, excepciones al perfil con su motivo.>

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
