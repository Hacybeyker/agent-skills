# Estrategia (sesión 2)

Convierte la síntesis en una estrategia y en un modelo de negocio con números. Corre en paralelo con la sesión 3; la puerta 2 espera a las dos. Lo que la puerta 2 pide de esta sesión es **al menos un modelo de monetización viable con evidencia**; la meta de ingresos, si la hay, es una referencia.

## Presupuesto y lista de tareas

**Cuándo:** con la puerta 1 decidida como "seguir". **Presupuesto:** 15 búsquedas y 10 lecturas (20 y 12 en una idea nueva), para los supuestos que 1d no dejó con fuente. Lo nuevo se registra en la línea `estrategia`.

1. Primera línea: `Sesión 2 · Estrategia (<motivo>)`.
2. `producto.py estado` y `producto.py tipo`. Lee `00-idea.md`, `01-sintesis.md`, `monetizacion.md` y `diferenciacion.md`, y la sección Distribución de `competencia.md`.
3. Usuario objetivo y Jobs To Be Done.
4. Propuesta de valor y posicionamiento, construidos sobre el diferenciador principal.
5. Lean Canvas y PR/FAQ.
6. Completa `escenarios.json` y corre `producto.py escenarios --entrada escenarios.json`.
7. Completa `02-estrategia.md` con la tabla y los rótulos que imprime el script.
8. `producto.py cerrar --sesion 2 --busquedas <n> --lecturas <n>` (lo que usaste **en esta pasada**, contra el presupuesto de arriba) y pega la salida.

Tus notas van en "Para la puerta 2" de tu archivo, no en `estado.md`: la sesión 3 corre al mismo tiempo. Si la propuesta de valor pide otro diferenciador principal, no lo cambies ni des un comando para hacerlo: `producto.py propuesta --texto "…" --ajustar 1g` lo deja para la puerta.

## Usuario objetivo y Jobs To Be Done

Un "trabajo" es el progreso que una persona quiere lograr en una situación: "cuando <situación>, quiero <motivación>, para <resultado>". No nombra el producto. Anota el trabajo principal, los relacionados (funcionales, emocionales y sociales) y cómo se resuelve hoy, con los hallazgos que lo respaldan. El usuario objetivo es un segmento, nunca una persona real.

## Propuesta de valor y posicionamiento

Una frase: *para <usuario> que <necesidad>, <producto> es <categoría> que <beneficio>; a diferencia de <alternativa>, <diferenciador principal>*. La alternativa se nombra por su tipo ("las apps por suscripción", "la lista en papel"), no por su marca. El posicionamiento es el lugar libre del mapa de 1g y la frase con la que la app se presenta en la ficha.

En una idea nueva, la alternativa es el sustituto: por qué alguien dejaría lo que usa hoy.

## Lean Canvas

Nueve bloques en una tabla: problema, segmentos de clientes, propuesta única de valor, solución, canales, fuentes de ingresos, estructura de costos, métricas clave y ventaja injusta. Cada bloque cita su evidencia; el que no la tiene va como **⚠ Sin evidencia**. "Ventaja injusta" puede ser "ninguna todavía": es mejor que inventarla.

**Canales y distribución.** La distribución es una palanca de esta sesión, no un diferenciador: salir arriba en las búsquedas de las tiendas de un país o un idioma donde el rival no aparece (ASO) ayuda a conseguir las primeras instalaciones, pero el rival puede entrar a esas palabras en días y no cambia el producto, así que no cuenta en el puntaje ni en la puerta 1. Su evidencia son los hallazgos de distribución de la 1a (`competencia.md`: resultados de búsqueda en las tiendas por país e idioma, con su fecha de consulta). Cítalos en el bloque Canales y en el posicionamiento; si falta un país o un idioma del objetivo, búscalo con el presupuesto de esta sesión y regístralo en la línea `estrategia` de la misma forma. En la puerta 2, esos hallazgos pueden sostener la hipótesis de canal de la sesión 3: su confianza cuenta como la de cualquier hallazgo enlazado ([validacion.md](validacion.md)).

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
      "instalaciones_mes": {"pesimista": 500, "base": 1500, "optimista": 4000, "fuente": "S-DEM-3"},
      "retencion": {
        "d1": {"pesimista": 0.2, "base": 0.3, "optimista": 0.4, "fuente": "S-MON-6"},
        "d7": {"pesimista": 0.06, "base": 0.1, "optimista": 0.15, "fuente": "S-MON-6"},
        "d30": {"pesimista": 0.02, "base": 0.04, "optimista": 0.06, "fuente": "S-MON-6"}
      },
      "dau_mau": {"pesimista": 0.1, "base": 0.15, "optimista": 0.2, "fuente": "S-MON-4"},
      "anuncios": [
        {"formato": "banner",
         "impresiones_por_dau": {"pesimista": 3, "base": 5, "optimista": 8, "fuente": "S-MON-1"},
         "ecpm": {"pesimista": 0.2, "base": 0.4, "optimista": 0.8, "fuente": "S-MON-1"}}
      ],
      "compras": [
        {"nombre": "Sin anuncios", "tipo": "pago-unico",
         "conversion": {"pesimista": 0.01, "base": 0.02, "optimista": 0.04, "fuente": "S-MON-3"},
         "precio": 2.99, "comision": 0.15},
        {"nombre": "Pro", "tipo": "suscripcion", "periodo": "mes",
         "conversion": {"pesimista": 0.005, "base": 0.01, "optimista": 0.02, "fuente": "S-MON-5"},
         "precio": 1.99, "comision": 0.15}
      ]
    }
  ]
}
```

| Supuesto | Qué es |
| --- | --- |
| `instalaciones_mes` | Instalaciones nuevas de cada mes. Hace falta si hay un pago único (se cobra una vez, a quien instala, no cada mes a los mismos usuarios) o si los usuarios activos se derivan de la retención |
| `retencion` | `d1`, `d7` y `d30`: la proporción de los que instalan que vuelve ese día (entre 0 y 1, y no sube con los días), cada una con su fuente. Con ella, el script deriva los usuarios activos diarios de una app nueva (abajo) |
| `dau` | Usuarios activos diarios medidos, en vez de `retencion` (uno o el otro). Sirve si son de esta app; tomados de un comparable que ya está en la tienda, inflan el caso base y `escenarios` lo avisa |
| `dau_mau` | Proporción de los usuarios del mes que entra cada día (entre 0 y 1). Solo hace falta si hay una suscripción |
| `impresiones_por_dau` | Anuncios de ese formato que ve cada usuario activo por día |
| `ecpm` | Ingreso por cada 1 000 impresiones de ese formato en ese mercado |
| `tipo` | De cada compra: `pago-unico` o `suscripcion`. Sin él, `escenarios` no calcula |
| `conversion` | En un pago único, la proporción de las instalaciones nuevas que compra; en una suscripción, la proporción de los usuarios del mes que paga (1 % = `0.01`) |
| `precio` | Lo que paga cada uno: una vez en un pago único; por `periodo` (`mes` por defecto, o `anio`) en una suscripción. Es tu decisión: no lleva fuente |
| `comision` | La comisión de la tienda, como proporción. No es siempre `0.15` o `0.30`: depende del programa de la tienda y del mercado. Usa la tasa que aplica, con su fuente oficial registrada (`fuente --tipo oficial`) y citada en `_leeme`; si aplican varias (por mercado o por tienda), la más alta, que deja el caso conservador |

- **Los usuarios activos de una app nueva (feedback #43).** Con `instalaciones_mes` y `retencion`, el script calcula `dau = instalaciones_mes ÷ 30 × días activos`, donde los días activos son lo que entra en promedio cada persona en sus primeros 30 días: 1 (el día que instala) más la retención de cada día, en línea recta entre D1, D7 y D30. No cuenta a los que siguen después del día 30, que una app nueva todavía no tiene. Si das `dau` y su fuente es la de un competidor de la matriz (o lo nombras con `"comparable": "C-4"`, o la fuente es un dato acumulado), `escenarios` avisa que viene de un comparable maduro y la puerta 2 lo muestra: una app con años en la tienda tiene una base instalada que una nueva no tiene.
- **Cómo se calcula.** Anuncios: `dau × impresiones_por_dau × 30 × ecpm ÷ 1000`. Pago único: `instalaciones_mes × conversion × precio × (1 − comision)`. Suscripción: `dau ÷ dau_mau × conversion × precio al mes × (1 − comision)` (un precio anual se divide por 12). Cada caso usa los valores de ese caso, y se suman los mercados. Son ingresos netos al mes.
- **El pago único no es recurrente.** Calcularlo sobre los usuarios del mes, como si cada mes pagara gente nueva, infla el caso base: lo que cuenta son las instalaciones nuevas. Unos escenarios calculados con esa regla anterior hacen que la puerta 2 pida volver a correr `escenarios`.
- **Cada supuesto lleva su fuente** (`"fuente": "S-…"`) o varias, si el valor sale de más de una: `"fuente": ["S-MON-3", "S-EST-2"]` (también `"S-MON-3, S-EST-2"`). Cada una tiene que estar registrada. Sin fuente, el escenario sale rotulado *estimación*, con la lista de los supuestos sin respaldo. Un número suelto en vez del objeto vale igual en los tres casos y cuenta como sin fuente.
- **Una fuente por caso.** Si cada caso sale de una fuente distinta (el pesimista de la app nueva más floja, el base de un competidor de media tabla), `fuente` es un objeto con la de cada uno: `"fuente": {"pesimista": "S-EST-8", "base": "S-EST-2", "optimista": ["S-EST-2", "S-MON-3"]}`. Las formas de arriba siguen valiendo y citan lo mismo en los tres casos. Un caso sin la suya deja el supuesto como *estimación* («sin fuente en el caso optimista»). `escenarios`, la puerta 2 y el reporte dicen qué fuente respalda cada caso, y el aviso del umbral de descarte cita la del caso con el que lo compara.
- **Por analogía.** Si la idea es nueva, si pones `"analogia": true` o si un caso de un supuesto solo tiene fuentes de los peldaños 3 a 6 (con una directa, de los peldaños 1 o 2, no), el escenario sale rotulado *por analogía* y el rango se abre: pesimista × 0,5 y optimista × 1,5.
- **El umbral de descarte.** La sesión 3 fija el umbral de descarte de la hipótesis más riesgosa (instalaciones orgánicas al mes y retención) con lo que hay registrado, y corre en paralelo: la puerta 2 lo compara con las instalaciones y la retención de tus casos pesimista y base, y avisa si lo contradicen ([validacion.md](validacion.md)).
- **Mercado saturado.** Las instalaciones del caso base parten del lugar que ocuparía la app según su diferenciador (un competidor de media tabla, con su fuente), no del líder; y los usuarios activos, de esas instalaciones y la retención, no de la base instalada de otra app.
- **Modelos de monetización.** La salida lista cada modelo (cada formato de anuncio y cada compra o suscripción, sumando los mercados) con lo que da en el caso base. Es **viable con evidencia** si genera ingresos en el caso base y todos sus supuestos citan su fuente (los usuarios, las instalaciones nuevas si es un pago único, la proporción diaria si es una suscripción, las impresiones, el eCPM o la conversión; el precio no, porque es una decisión). La puerta 2 pide al menos uno. Si ninguno lo es, se dice qué fuente falta: no se inventa.
- **La meta.** Es **opcional y referencial**: si existe, la salida compara el caso base con `meta_ingresos_mes` y dice cuántos usuarios activos diarios hacen falta para llegar, solo como referencia. Nunca bloquea la puerta ni cuenta como riesgo, salvo que el usuario la haya marcado como obligatoria (`meta_obligatoria`), y entonces es un criterio más de la puerta 2.

No ajustes los supuestos para que el caso base llegue a la meta ni para que un modelo parezca viable: si no llega, se dice, y el usuario decide.
