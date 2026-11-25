# Validación documental (sesión 3)

Pone a prueba la idea **antes de construir**, con documentos: por cada hipótesis crítica se busca evidencia en contra. No reemplaza la validación con usuarios reales, que llega después del lanzamiento. Corre en paralelo con la sesión 2.

## Presupuesto y lista de tareas

**Cuándo:** con la puerta 1 decidida como "seguir". **Presupuesto:** 15 búsquedas y 10 lecturas (20 y 12 en una idea nueva), casi todas en contra. Lo nuevo se registra en la línea `validacion`.

1. Primera línea: `Sesión 3 · Validación documental (<motivo>)`.
2. `producto.py estado`, `producto.py tipo` y `producto.py triangulacion`. Lee `00-idea.md`, `01-sintesis.md` y `diferenciacion.md`.
3. Lista las hipótesis críticas: de 4 a 8.
4. Por cada una, **busca en contra** y registra lo que aparezca (`producto.py fuente --linea validacion` y `hallazgo`), o qué buscaste si no apareció nada.
5. Completa la tabla de `03-validacion.md` y el apartado de abogado del diablo de cada hipótesis.
6. Marca la hipótesis más riesgosa, con su métrica y su umbral.
7. `producto.py validacion`: revisa la tabla y calcula la confianza de cada fila.
8. `producto.py cerrar --sesion 3 --busquedas <n> --lecturas <n>` (lo que usaste **en esta pasada**, contra el presupuesto de arriba) y pega la salida.

Tus notas van en "Para la puerta 2" de tu archivo, no en `estado.md`: la sesión 2 corre al mismo tiempo.

## Qué es una hipótesis crítica

Una afirmación que, si es falsa, tumba el producto. Salen de la síntesis; estas casi siempre están:

- **Problema:** el usuario tiene el problema con la frecuencia suficiente.
- **Solución:** la app lo resuelve mejor que lo que usa hoy.
- **Diferenciador:** una por cada diferenciador, y siempre la del principal: `cerrar --sesion 3` no cierra sin ella.
- **Canal:** hay una forma de que los usuarios lleguen a la app.
- **Pago:** alguien paga, o el volumen alcanza para los anuncios.
- **Políticas:** las tiendas la aceptan.

## La tabla

`producto.py validacion` y la puerta 2 leen esta tabla: respeta las columnas.

| ID | Hipótesis | Hallazgos | En contra | Diferenciador | Veredicto | Más riesgosa | Métrica y umbral |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HIP-01 | Los vecinos quieren repartir el riego | H-DEM-1, H-VOZ-2 | S-VAL-1 | — | sostenida | sí | 30 % de los grupos sigue activo a los 30 días |
| HIP-02 | El pago único atrae a quien no quiere suscripción | H-VOZ-3 | Busqué quejas por pagos únicos: nada | D-1 | débil | — | — |

- **Hallazgos:** los IDs a favor. La **confianza** de la fila es la menor de sus **hallazgos clave** (los registrados con `--critico`) y la calcula el script: no se escribe. Un hallazgo que solo complementa (contexto, evidencia a favor débil que no sostiene la hipótesis por sí sola) va sin `--critico` y no la baja; si la fila no cita ninguno clave, es la menor de todos.
- **En contra:** los IDs de las fuentes en contra o, si no apareció nada, qué buscaste. Nunca vacía.
- **Diferenciador:** el ID si la hipótesis lo pone a prueba. La de diferenciador siempre lo lleva. **Una de canal o de pago lo lleva cuando pone a prueba el valor de ese diferenciador**: si fuera falsa, el diferenciador dejaría de ser una razón para elegir la app o para pagar (por ejemplo, la de pago de un pago único cuando el diferenciador es el precio, o la de canal cuando lo que atrae las instalaciones es justo ese diferenciador). Si se sostiene o cae sin importar el diferenciador (las búsquedas de la categoría en la tienda, los anuncios que pagan la versión gratis), va con «—». Cada hipótesis con el ID cuenta para «sobrevive» (abajo).
- **Veredicto:**
  - *sostenida:* evidencia a favor con confianza media o alta, y lo que hay en contra no la contradice. Con confianza baja, el script no acepta "sostenida".
  - *débil:* poca evidencia a favor, o evidencia en contra que no alcanza para refutarla.
  - *refutada:* la evidencia en contra es más fuerte que la que hay a favor. La puerta 2 no se cumple con una hipótesis refutada.
- **Más riesgosa:** "sí" en una sola fila.
- **Métrica y umbral:** obligatoria en la más riesgosa.

## Abogado del diablo

Por cada hipótesis, búsquedas pensadas para **perder**: "por qué fallaría <idea>", "<categoría> no funciona", "<app parecida> cerró", "dejé de usar <tipo de app>". Y según el tipo de idea:

- **Idea nueva:** ¿no existe porque nadie la pensó, o porque alguien la probó y no funcionó? Revisa lo que 1a registró con `producto.py intento` y profundiza.
- **Idea con competencia:** ¿por qué los competidores no lo hicieron ya? ¿Cuánto tardarían en copiarlo? ¿Lo probó alguno y lo quitó? Se hace **también sobre cada diferenciador**.

Lo que aparece se registra y se enlaza: un hallazgo nuevo en la línea `validacion`, o `--en-contra` en un hallazgo propio. Si no aparece nada, se anota qué se buscó. "No busqué" no es lo mismo que "no hay".

El diferenciador principal **sobrevive** si todas sus hipótesis (las que lo llevan en la columna Diferenciador) quedan sostenidas, con confianza media o alta; sin ninguna, no sobrevive, porque nada lo puso a prueba. **Otro diferenciador viable pasa la misma regla con sus propias hipótesis**: la puerta 2 solo recomienda llevarlo a principal si sobrevive, así que pon a prueba también a los que podrían reemplazarlo. Si el principal queda débil o refutado, se dice, y si otro diferenciador lo sostendría mejor, se deja como propuesta, nunca como un comando suelto: `producto.py propuesta --texto "<qué cambiar y por qué>" --ajustar 1g`. La puerta 2 la muestra y el usuario decide si reabre 1g.

Débil o sin poner a prueba no es lo mismo que refutada: le falta evidencia, no tiene evidencia en contra. Si el principal (y cada otro viable) no sobrevive solo por eso, la puerta 2 recomienda reabrir esta sesión **una sola vez** y dice qué hipótesis fortalecer y con qué evidencia (qué hallazgo triangular, o evidencia a favor nueva si sus hallazgos ya están en confianza media o alta); el texto de la reapertura lo repite. En esa pasada, busca justo eso y vuelve a dar el veredicto de cada hipótesis con lo que aparezca: si al cerrar sigue sin sobrevivir, la puerta ya no recomienda reabrirla y el veredicto es No viable.

**Fortalecer un hallazgo de otra sesión.** Si lo que hay que triangular es un hallazgo de una sesión ya cerrada (H-DEM-5, de la 1c), no se le suman fuentes (`hallazgo --id --fuentes` pide su sesión abierta): registra un hallazgo nuevo en tu línea que lo reúna con lo que encontraste, `producto.py hallazgo --linea validacion --reune H-DEM-5 --fuentes <las nuevas> --texto "…" --critico`. Lleva las fuentes a favor y en contra del original (y su confianza bajada a mano, si la tenía) y sigue también sus reglas de triangulación (una fuente medida en demanda; los datos acumulados no cuentan). Después, en la columna Hallazgos de la hipótesis, **cita el nuevo en lugar del original**: si quedan los dos, la fila toma la confianza del más débil. "Qué cambiaría" de la puerta 2 y el texto de la reapertura ya dicen cuál es de otra sesión.

## La hipótesis más riesgosa

Es la que combina más impacto si es falsa con menos evidencia a favor. El MVP tiene que ponerla a prueba primero, así que lleva desde ahora:

- **Métrica:** qué se mide (por ejemplo, grupos que siguen activos a los 30 días).
- **Umbral:** el valor que la confirma y el que la descarta.
- **Plazo:** en cuánto tiempo después del lanzamiento.

En una idea nueva es un criterio de las puertas 2 y 3: sin métrica y umbral, la idea llegaría al lanzamiento sin saber qué mirar.

**Si la puerta 1 fue Viable para probar** (el texto de la sesión lo dice), la hipótesis más riesgosa es la del **criterio de descarte**: que la gente elige la app por el diferenciador principal frente al rival. Márcala como la más riesgosa, con el diferenciador en su columna, y escribe su métrica y su umbral con las **instalaciones orgánicas** (al mes) y la **retención** (por ejemplo, a 30 días), medidas a los días que dice el criterio (`dias_descarte`, 60 por defecto). El umbral sale de lo que ya está registrado (el caso pesimista de los escenarios, una referencia de retención de la línea `validacion`), con su fuente. Puede quedar **débil**: es justo lo que se prueba después del lanzamiento, y la puerta 2 no la cuenta contra el principal; **refutada**, sí. Las puertas 2 y 3 piden entonces lo mismo que en una idea nueva: la hipótesis más riesgosa con su métrica y su umbral, y el MVP que la pone a prueba.

## Lo que esta sesión no hace

No cambia el puntaje, los escenarios ni el diferenciador principal, no decide y no convierte "no encontré nada en contra" en "validado": deja escrito con qué confianza llega cada hipótesis a la construcción.
