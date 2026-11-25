# Mapa del módulo: `<identificador>`

Commit analizado: `<sha completo>` (repo `<nombre de la carpeta del repo>`, <AAAA-MM-DD>)<, si describe cambios sin commitear: (incluye cambios sin commitear de `<slug>`)>
Ruta de la unidad: `<ruta desde la raíz de su repo, o . si es el repo entero>`

<!-- Cómo mantenerlo:
- Commit analizado: el commit cuyo código describe el mapa. Con cambios sin commitear, el de la base y la nota de
  arriba; cuando se commitean, ese commit y sin la nota.
- Antes de tocar la unidad, compara el commit analizado con el HEAD de su repo. Si avanzó, revisa solo
  `git -C <repo> diff <commit analizado>..HEAD -- <ruta de la unidad>`, corrige lo que cambió y actualiza el commit.
- Describe lo estable: nada de estados del momento (git status, ramas actuales, "hoy").
- Corto: lo que un agente necesita para no romper nada. El detalle va en el código y en los documentos del proyecto. -->

## Qué hace

<Una o dos oraciones: para qué existe y quién la usa.>

## Puntos de entrada

- `<archivo o símbolo>`: <la pantalla, el endpoint, el comando o la API pública que expone>

## Flujos principales

1. <Nombre del flujo>: <de dónde entra, qué pasos sigue y dónde termina, con los archivos clave>

## Servicios que llama

| Servicio o endpoint | Desde | Para qué |
| --- | --- | --- |
| `<método y ruta, o nombre del servicio>` | `<archivo>` | <qué datos trae o envía> |

## Datos y persistencia

<Qué guarda, dónde (base local, archivos, caché, preferencias) y qué sobrevive a reiniciar.>

## Patrones y convenciones

- <Arquitectura, inyección de dependencias, manejo de errores, estilo de tests: lo que la unidad hace distinto del resto del proyecto, o "sigue `## Arquitectura`".>

## DoD de la unidad

`cd <ruta del proyecto> && <comando de la columna "DoD de la unidad" de ## Estructura>`

## Cuidado con

- <Lo frágil o lo que no es obvio: contratos que consumen otras unidades, código generado, valores que no se deben cambiar.>
