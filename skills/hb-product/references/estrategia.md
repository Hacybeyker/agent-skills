# Estrategia (sesión 2)

Convierte la síntesis en una estrategia y en un modelo de negocio con números. Corre en paralelo con la sesión 3; la puerta 2 espera a las dos.

## Presupuesto y lista de tareas

**Cuándo:** con la puerta 1 decidida como "seguir". **Presupuesto:** 15 búsquedas y 10 lecturas (20 y 12 en una idea nueva), para los supuestos que 1d no dejó con fuente. Lo nuevo se registra en la línea `estrategia`.

1. Primera línea: `Sesión 2 · Estrategia (<motivo>)`.
2. `producto.py estado` y `producto.py tipo`. Lee `00-idea.md`, `01-sintesis.md`, `monetizacion.md` y `diferenciacion.md`.
3. Usuario objetivo y Jobs To Be Done.
4. Propuesta de valor y posicionamiento, construidos sobre el diferenciador principal.
5. Lean Canvas y PR/FAQ.
6. Completa `escenarios.json` y corre `producto.py escenarios --entrada escenarios.json`.
7. Completa `02-estrategia.md` con la tabla y los rótulos que imprime el script.
8. `producto.py cerrar --sesion 2` y pega la salida.

Tus notas van en "Para la puerta 2" de tu archivo, no en `estado.md`: la sesión 3 corre al mismo tiempo.

## Usuario objetivo y Jobs To Be Done

Un "trabajo" es el progreso que una persona quiere lograr en una situación: "cuando <situación>, quiero <motivación>, para <resultado>". No nombra el producto. Anota el trabajo principal, los relacionados (funcionales, emocionales y sociales) y cómo se resuelve hoy, con los hallazgos que lo respaldan. El usuario objetivo es un segmento, nunca una persona real.

## Propuesta de valor y posicionamiento

Una frase: *para <usuario> que <necesidad>, <producto> es <categoría> que <beneficio>; a diferencia de <alternativa>, <diferenciador principal>*. La alternativa se nombra por su tipo ("las apps por suscripción", "la lista en papel"), no por su marca. El posicionamiento es el lugar libre del mapa de 1g y la frase con la que la app se presenta en la ficha.

En una idea nueva, la alternativa es el sustituto: por qué alguien dejaría lo que usa hoy.

## Lean Canvas

Nueve bloques en una tabla: problema, segmentos de clientes, propuesta única de valor, solución, canales, fuentes de ingresos, estructura de costos, métricas clave y ventaja injusta. Cada bloque cita su evidencia; el que no la tiene va como **⚠ Sin evidencia**. "Ventaja injusta" puede ser "ninguna todavía": es mejor que inventarla.

## PR/FAQ

El método de trabajar hacia atrás: se escribe primero el comunicado del lanzamiento, como si el producto ya existiera, y después las preguntas.

- **Comunicado:** media página con el título, a quién le sirve, qué problema resuelve, cómo, y una cita **inventada y rotulada como tal** de un usuario del segmento.
- **Preguntas de los usuarios:** las que haría quien lee la ficha (precio, datos, diferencias con lo que ya usa).
- **Preguntas internas:** las incómodas (por qué ahora, por qué no lo hizo un competidor, qué pasa si nadie paga), respondidas con evidencia.

Si el comunicado no se puede escribir sin exagerar, la propuesta de valor todavía no está clara.

## Escenarios de ingresos

Los calcula el script con los supuestos de `escenarios.json`; la plantilla trae un ejemplo inventado.

```json
{
  "moneda": "USD",
  "analogia": false,
  "mercados": [
    {
      "mercado": "MX",
      "dau": {"pesimista": 300, "base": 1000, "optimista": 3000, "fuente": "S-DEM-2"},
      "dau_mau": {"pesimista": 0.1, "base": 0.15, "optimista": 0.2, "fuente": "S-MON-4"},
      "anuncios": [
        {"formato": "banner",
         "impresiones_por_dau": {"pesimista": 3, "base": 5, "optimista": 8, "fuente": "S-MON-1"},
         "ecpm": {"pesimista": 0.2, "base": 0.4, "optimista": 0.8, "fuente": "S-MON-1"}}
      ],
      "compras": [
        {"nombre": "Sin anuncios",
         "conversion": {"pesimista": 0.005, "base": 0.01, "optimista": 0.02, "fuente": "S-MON-3"},
         "precio": 2.99, "comision": 0.15}
      ]
    }
  ]
}
```

| Supuesto | Qué es |
| --- | --- |
| `dau` | Usuarios activos diarios en ese mercado |
| `dau_mau` | Proporción de los usuarios del mes que entra cada día (entre 0 y 1). Solo hace falta si hay `compras` |
| `impresiones_por_dau` | Anuncios de ese formato que ve cada usuario activo por día |
| `ecpm` | Ingreso por cada 1 000 impresiones de ese formato en ese mercado |
| `conversion` | Proporción de los usuarios del mes que paga ese mes (1 % = `0.01`): suscriptores activos o compradores |
| `precio` | Lo que paga cada uno ese mes. Es tu decisión: no lleva fuente |
| `comision` | La comisión de la tienda: `0.15` o `0.30` |

- **Cómo se calcula.** Anuncios: `dau × impresiones_por_dau × 30 × ecpm ÷ 1000`. Compras: `dau ÷ dau_mau × conversion × precio × (1 − comision)`. Cada caso usa los valores de ese caso, y se suman los mercados. Son ingresos netos al mes.
- **Cada supuesto lleva su fuente** (`"fuente": "S-…"`). Sin fuente, el escenario sale rotulado *estimación*, con la lista de los supuestos sin respaldo. Un número suelto en vez del objeto vale igual en los tres casos y cuenta como sin fuente.
- **Por analogía.** Si la idea es nueva, si pones `"analogia": true` o si una fuente es de los peldaños 3 a 6, el escenario sale rotulado *por analogía* y el rango se abre: pesimista × 0,5 y optimista × 1,5.
- **Mercado saturado.** Los usuarios del caso base parten del lugar que ocuparía la app según su diferenciador (un competidor de media tabla, con su fuente), no del líder.
- **La meta.** La salida compara el caso base con `meta_ingresos_mes` y dice cuántos usuarios activos diarios hacen falta para llegar. Ese número va a `02-estrategia.md`: es la pregunta que el usuario tiene que poder responder antes de la puerta 2.

No ajustes los supuestos para que el caso base llegue a la meta: si no llega, se dice, y el usuario decide.
