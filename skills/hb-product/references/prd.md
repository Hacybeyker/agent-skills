# PRD (sesión 4)

Define el producto mínimo que se va a construir, con cada funcionalidad enlazada a su evidencia. Termina en la puerta 3.

## Presupuesto y lista de tareas

**Cuándo:** con la puerta 2 decidida como "seguir". **Sin búsquedas nuevas:** el PRD se arma con lo registrado.

1. Primera línea: `Sesión 4 · PRD (<motivo>)`.
2. `producto.py estado` y `producto.py tipo`. Lee `00-idea.md`, `01-sintesis.md`, `diferenciacion.md`, `02-estrategia.md`, `03-validacion.md` y `politicas.md`.
3. Lista las funcionalidades candidatas: el diferenciador principal, las básicas (Kano) y lo que pone a prueba la hipótesis más riesgosa.
4. Define las métricas HEART (`M-01`…).
5. Completa la tabla de funcionalidades y corre `producto.py trazabilidad`: calcula el RICE y marca lo que falta.
6. Decide el MVP con el orden del RICE y el presupuesto de semanas, y vuelve a correr `trazabilidad`.
7. Historias con criterios de aceptación, plan de eventos, ubicación de la monetización, checklist de políticas y estimación.
8. `producto.py cerrar --sesion 4` y pega la salida: es la puerta 3.

## La tabla de funcionalidades

`producto.py trazabilidad` y la puerta 3 leen esta tabla: respeta las columnas.

| ID | Funcionalidad | MVP | Hallazgos | Diferenciador | Métrica | Alcance | Impacto | Semanas | Hipótesis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | Turnos de riego con pago único | sí | H-VOZ-3, H-DEM-1 | D-1 | M-01 | 1000 | 2 | 3 | HIP-01 |
| F-02 | Recordatorio a quien le toca | sí | H-COM-1 | — | M-02 | 800 | 1 | 2 | — |
| F-03 | Temas de color | no | H-VOZ-5 | — | M-03 | 100 | 0,5 | 1 | — |

- **MVP:** "sí" o "no".
- **Hallazgos:** los que la justifican. Una funcionalidad sin hallazgo no tiene trazabilidad: o se consigue la evidencia, o sale del MVP.
- **Diferenciador:** su ID, si la funcionalidad lo materializa.
- **Métrica:** el ID de la métrica HEART con la que se sabrá si funciona.
- **Alcance, Impacto y Semanas:** los datos del RICE.
- **Hipótesis:** el ID de la hipótesis que pone a prueba.

### Qué entra siempre al MVP

- **El diferenciador principal.** Sin él, el MVP es otra app más: es un criterio de la puerta 3.
- **Las funcionalidades básicas** (Kano), aunque no diferencien: sin ellas la app no compite.
- **En una idea nueva,** lo que pone a prueba la hipótesis más riesgosa, y poco más: un MVP más chico, centrado en aprender.
- **Si la puerta 1 fue Viable para probar,** la funcionalidad del diferenciador principal cita en su columna Hipótesis la más riesgosa (el criterio de descarte) y la mide con su métrica y su umbral: la puerta 3 lo pide, igual que en una idea nueva.
- **Si la puerta 2 fue Viable para probar** (lo que sostiene el negocio quedó débil o en baja y otra búsqueda no lo subía), cada riesgo que nombra (una hipótesis o la monetización) se mide después del lanzamiento: lleva su métrica y su umbral en las métricas HEART, los de su fila de `03-validacion.md` o, si no los tiene, los que defina esta sesión. El texto de la sesión los nombra.

## RICE

`RICE = alcance × impacto × confianza ÷ esfuerzo`. Lo calcula `producto.py trazabilidad`:

- **Alcance:** usuarios al mes a los que les llega la funcionalidad, con la base del escenario de la sesión 2. Escríbelo sin separador de miles.
- **Impacto:** 3 (enorme), 2 (alto), 1 (medio), 0,5 (bajo) o 0,25 (mínimo).
- **Confianza:** no se escribe. Sale de la menor confianza de sus hallazgos: alta 100 %, media 80 %, baja 50 %.
- **Esfuerzo:** las semanas de la columna `Semanas`.

El RICE ordena, no decide: el diferenciador principal y las básicas entran aunque otra funcionalidad tenga más puntaje.

## Métricas HEART

Cinco dimensiones para medir la experiencia: felicidad, interacción, adopción, retención y éxito de la tarea. No hacen falta las cinco: elige las que digan si el producto funciona.

| ID | Dimensión | Métrica | Meta |
| --- | --- | --- | --- |
| M-01 | Retención | Grupos que siguen activos a los 30 días | 30 % a los 90 días del lanzamiento |
| M-02 | Tarea | Turnos marcados como hechos sin recordatorio extra | 80 % |

Cada métrica necesita la dimensión, qué se mide y una meta con valor y plazo. La de la hipótesis más riesgosa usa la métrica y el umbral de `03-validacion.md`.

## Historias y criterios de aceptación

Una por funcionalidad del MVP: "como <usuario>, quiero <acción>, para <beneficio>", con criterios en formato "dado …, cuando …, entonces …". Son lo que `hb-implement` va a recibir: tienen que poder probarse.

**Los cuenta el script** (`trazabilidad` y la puerta 3: "Cada funcionalidad del MVP tiene criterios de aceptación", X de Y). Respeta la forma de la plantilla: un título con el ID (`### F-01`) y, debajo de `- **Criterios de aceptación:**`, una viñeta por criterio. Una funcionalidad del MVP sin criterios deja la puerta 3 en 🟡 (ajustar 4).

## Plan de eventos de analítica

Los eventos que alimentan cada métrica: nombre, cuándo se envía, parámetros y a qué métrica sirve. Sin datos personales en los parámetros. Si una métrica no tiene un evento que la alimente, no se va a poder medir.

## Ubicación de la monetización

Dónde aparece cada formato de anuncio, cada compra o el muro de pago dentro del flujo, y qué queda siempre gratis. Tiene que ser coherente con el diferenciador (si el diferenciador es "menos anuncios", el PRD dice cuántos y dónde) y con las políticas de 1e.

## Checklist de políticas

Cada requisito que encontró la sesión 1e, con su estado: **cumple**, **pendiente**, **no aplica** o **bloqueo**. Un pendiente se resuelve antes de publicar; con un bloqueo, la puerta 3 no se cumple.

## Estimación

Las semanas del MVP salen de la suma de la columna `Semanas` y se comparan con `presupuesto_semanas`. Di los supuestos (una persona, qué stack, qué queda fuera). Si no cabe, se recorta el MVP sin sacar el diferenciador principal, o se dice que no cabe.

## Después del PRD

La construcción no es parte de hb-product. Se pide a `hb-implement` una funcionalidad a la vez, citando su ID ("Implementa F-01 de product/04-prd.md"); las independientes pueden ir en paralelo, en ramas separadas.
