# Ideas con competencia: la diferenciación (sesión 1g)

Si ya existen apps iguales o parecidas, la demanda está probada y la pregunta cambia: **¿por qué alguien elegiría la tuya?** **Saturado no es lo mismo que cerrado:** la idea sigue adelante si encuentra un valor extra con evidencia.

## Presupuesto y lista de tareas

**Cuándo:** apenas cierran 1a y 1b, sin esperar a 1c–1e. **Presupuesto:** 15 búsquedas y 10 lecturas (20 y 12 en una idea nueva); casi todo sale de lo ya registrado.

1. Primera línea: `Sesión 1g · Diferenciación (<motivo>)`.
2. `producto.py tipo` y `producto.py matriz`: la matriz de 1a con los hallazgos que 1b enlazó a cada competidor.
3. Lee `competencia.md` y `voz-del-usuario.md` (solo esos dos).
4. Mira primero **el rival a superar**: la alternativa gratis más fuerte que marcó 1a (`competidor --rival`, sea otra app o un sustituto) y los sustitutos gratuitos o nativos que ya resuelven la necesidad. Todo diferenciador tiene que superarlo (abajo).
5. Recorre los 12 vectores y anota el hueco de cada uno, o "sin hueco".
6. Arma el cuadro ERRC, la clasificación Kano y el mapa de posicionamiento.
7. Si a un hueco le falta evidencia, búscala y regístrala en la línea `diferenciacion` (`producto.py fuente` y `hallazgo`).
8. Registra cada diferenciador con `producto.py diferenciador` y su comparación con el rival con `producto.py frente` (supera, iguala o no, con sus hallazgos): el script dice si es viable y por qué. Elige el principal con `--principal` o, después, con `producto.py principal --id D-…`.
9. Abogado del diablo: por qué los competidores no lo hicieron ya y cuánto tardarían en copiarlo.
10. Completa `diferenciacion.md` y `producto.py cerrar --sesion 1g --busquedas <n> --lecturas <n>` (lo que usó la línea **en esta pasada**: en una reapertura, solo lo de la reapertura, contra su presupuesto). 1g no cierra con un diferenciador sin comparar con el rival.

**Si ningún diferenciador es viable, dilo tal cual.** Es un resultado válido: la puerta 1 lo muestra y el usuario decide. No inventes uno para salvar la idea.

## Matriz de competidores

La arma la sesión 1a: una fila por competidor y una columna por vector (descargas, nota, última actualización, precio y modelo, intensidad de anuncios, tamaño, idiomas, permisos, sin conexión, accesibilidad, plataformas y funcionalidades clave). `producto.py matriz` le suma a cada fila los hallazgos de 1b que la nombran: ahí está la queja principal de cada competidor.

En una idea nueva, las filas son los análogos y los sustitutos: la comparación es contra la hoja de cálculo o el grupo de chat.

## El rival a superar: la alternativa gratis más fuerte

Ganarle a las apps de pago no sirve si hay una alternativa gratis que ya da lo mismo. Ese rival puede ser **otra app** (una directa, gratis y completa) o **un sustituto**: la linterna que trae el teléfono, el recordatorio del sistema, una hoja de cálculo o el grupo de chat. La lección de dos pruebas: con Linterna, el diferenciador era viable frente a las apps, pero no frente a la linterna nativa; en otra, el principal (gratis y sin topes) solo **igualaba** a una app directa que ya era gratis y sin topes, y la puerta daba verde porque solo miraba los sustitutos.

- **El rival es la alternativa gratis más fuerte para el mismo usuario y la misma necesidad**: el mismo segmento (la edad, el nivel, el contexto de uso) y el mismo trabajo, no la alternativa gratis más grande de la categoría. Una app escolar para 12 años no es el rival de una idea para niños de 3 a 6, aunque sea gratis y tenga respaldo; lo es la escuela de nivel inicial gratuita que hoy atiende a esos niños. Antes de marcarlo, comprueba en sus fuentes para quién es.
- **La sesión 1a marca el rival** con `competidor --nombre "<la alternativa>" … --rival`: la alternativa gratis más fuerte, sea sustituto o competidor directo. Hay uno solo: marcar otro reemplaza al anterior. Si ninguna alternativa gratis resuelve la necesidad, lo dice con `competidor --sin-rival "<por qué>"`. En una idea existente o variante, 1a no cierra sin una de las dos. `competidor --rival` no pide la 1a abierta: si la puerta dice que falta el rival, se marca al ajustar la 1g, que es la que compara cada diferenciador con él (`frente`).
- **Un sustituto que llega después puede ser el rival.** Si otra línea agrega a la matriz un sustituto gratuito o nativo con tracción después de marcar el rival (por ejemplo, la 1c al investigar cómo se resuelve hoy la necesidad), `siguiente` y la puerta 1 piden revisarlo: si es la alternativa más fuerte para el mismo usuario, márcalo con `--rival` y compara de nuevo cada diferenciador en la 1g; si no, confirma el rival con `competidor --nombre "<rival>" … --rival`.
- **Los sustitutos fuertes también son rivales.** La sesión 1a registra siempre al menos un sustituto (peldaño 4) con `--sustituto nativo|gratuito|pago` y `--resuelve si|parcial|no`; sin eso, 1a no cierra. Sé honesto con `--resuelve si`: si la mayoría de quienes tienen la necesidad se arreglan con él, la resuelve. Uno nativo o gratuito que la resuelve se suma al rival marcado.
- **La sesión 1g compara cada diferenciador con cada rival**, con sus hallazgos:

```bash
python3 -I <skill>/scripts/producto.py frente --id D-1 --rival C-2 --resultado supera|iguala|no \
  --hallazgos H-VOZ-2,H-DIF-1 --texto "En qué lo supera o lo iguala, en una frase"
```

| Resultado | Qué significa | Para la viabilidad |
| --- | --- | --- |
| `supera` | Hace algo que el rival no da, con evidencia | Cumple si **al menos uno** de esos hallazgos está triangulado; todos entran al criterio de triangulación |
| `iguala` | Da lo mismo que el rival (por ejemplo, gratis frente a una app que ya es gratis) | **Paridad**: es básico en Kano. Sirve para competir, pero no es viable ni puede ser el principal |
| `no` | El rival lo hace mejor | No cumple |

- **Prueba de elección.** Superar al rival no alcanza si nada muestra que eso hace **elegir** la app. Hay prueba de elección cuando todos los hallazgos de la comparación están triangulados y en confianza **alta**, **al menos uno es distinto del dolor** (abajo) y ninguna hipótesis de 03-validacion.md sobre ese diferenciador quedó débil o refutada. Sin ella, la puerta 1 queda como mucho en 🟡: Viable para probar si el dolor está triangulado (abajo) y, si no, Viable con reservas ([puertas.md](puertas.md)).
- **El dolor y la elección, por separado.** Los hallazgos propios del diferenciador (`diferenciador --hallazgos`) son **el dolor**: el pedido, la queja o el vector medible que lo sostienen. Los de cada `frente` son **la comparación**: muestran que supera al rival (con uno triangulado basta) y, si todos están triangulados y en confianza alta y al menos uno es distinto del dolor, que eso hace elegir la app. **Un hallazgo del dolor no es prueba de elección**: "los avisos del rival fallan" muestra que el rival falla, no que la gente elija la app por eso. Puedes citarlo en `frente` (cuenta para "supera"), pero la prueba de elección pide al menos un hallazgo de la comparación que no sea del dolor (ni lo reúna con `--reune`, ni tenga solo sus mismas fuentes), triangulado y en confianza alta. `frente` y `diferenciador` avisan cuando una comparación solo cita el dolor. "**El dolor está triangulado**" quiere decir que todos los hallazgos propios cumplen la regla 2 y que cada `frente --resultado supera` tiene al menos un hallazgo triangulado; lo que falte en la comparación es la prueba de elección.
- **Viable para probar.** La prueba de elección casi nunca está en la web antes de lanzar: la evidencia muestra el dolor, no la elección. Un diferenciador que supera al rival con el dolor triangulado (los criterios 1 a 5 de abajo y sus hallazgos propios triangulados), sin ninguna hipótesis refutada sobre él, se puede **probar**: si es el principal, la idea no tiene un bloqueo de políticas y la demanda tiene confianza media o alta, la puerta 1 da 🟡 **Viable para probar** y recomienda seguir con un **criterio de descarte después del lanzamiento** ([puertas.md](puertas.md)). Con esas dos condiciones de la idea, para el puntaje cuenta como viable: su confianza baja es solo la de la elección.
- Si nada supera al rival, dilo así: con una alternativa gratis que ya da lo mismo, no hay oportunidad, por más que se le gane a las otras apps. La puerta 1 lo marca como No viable.

## Vectores de diferenciación

Los ejemplos son inventados.

| Vector (`--vector`) | Cómo se detecta un hueco | Ejemplo de diferenciador |
| --- | --- | --- |
| `usabilidad` | Quejas repetidas de flujos confusos, demasiados pasos o registro obligatorio | Funciona sin crear cuenta, en 3 toques |
| `rendimiento` | Quejas de lentitud, cierres o batería; descargas pesadas | La mitad del tamaño y abre en menos de 1 s |
| `precio` | Suscripción cara, muros de pago agresivos, quejas por cambios de precio | Pago único en vez de suscripción |
| `anuncios` | Quejas por anuncios invasivos | Anuncios solo en pausas naturales, o una versión sin anuncios barata |
| `funcionalidades` | Pedidos repetidos que nadie atiende | La función más pedida en las reseñas de 3 competidores |
| `idioma` | Competidores solo en inglés o sin contenido local | Contenido y fechas locales por país |
| `privacidad` | Permisos excesivos, quejas por datos | Sin permisos sensibles y todo en el dispositivo |
| `sin-conexion` | Quejas por depender de internet | Funciona completa sin conexión |
| `accesibilidad` | Sin soporte de lector de pantalla, textos pequeños | Cumple las pautas de accesibilidad de la plataforma |
| `diseno` | Apps abandonadas o con diseño anticuado (última actualización hace años) | Diseño actual y mantenimiento visible |
| `segmento` | Un grupo de usuarios mal atendido por los productos generales | La misma idea, pensada para un nicho concreto |
| `plataforma` | Solo existe en una plataforma | Disponible en Android y en iOS |

## Herramientas estándar

- **Cuadro ERRC** (estrategia del océano azul): qué **eliminar**, **reducir**, **aumentar** y **crear** respecto de la competencia. Obliga a decidir también qué no hacer.
- **Modelo Kano:** separa lo **básico** (sin eso la app no compite), lo que **suma** (más es mejor) y lo que **sorprende** (un diferenciador fuerte). Las funcionalidades básicas entran al MVP aunque no diferencien.
- **Mapa de posicionamiento:** dos ejes que le importan al usuario (por ejemplo, precio y simplicidad), los competidores ubicados y el lugar libre. Si no hay un lugar libre, se dice.

## Qué hace viable a un diferenciador

```bash
python3 -I <skill>/scripts/producto.py diferenciador --vector precio --texto "Pago único en vez de suscripción" \
  --hallazgos H-VOZ-2,H-COM-1 --se-ve ficha --copiable media \
  --motivo "Cambiar de modelo les cuesta ingresos recurrentes" --semanas 2 --principal
```

El script lo registra (`D-1`) y dice si es **viable**, **viable con confianza baja** o **no viable** (con la **paridad** como caso aparte). Tiene que cumplir los cinco criterios:

1. **Evidencia.** Una de dos: un dolor o un pedido **triangulado en 2 competidores o más** (un hallazgo con sus 3 fuentes y `--competidor` con dos filas de la matriz, por su ID), o un **vector medible comprobado en la matriz** en 2 competidores o más (`precio`, `rendimiento` por el tamaño, `anuncios`, `idioma`, `privacidad` por los permisos, `sin-conexion`, `accesibilidad`, `diseno` por la última actualización y `plataforma`). `usabilidad`, `funcionalidades` y `segmento` no se miden en la matriz: necesitan el dolor triangulado. Es el filtro del *diferenciador imaginario*.
2. **Se percibe** (`--se-ve`). En la **ficha** de la tienda (precio, idioma, sin anuncios, diseño), que es lo que consigue descargas, o en el **uso** (rendimiento, usabilidad), que es lo que consigue retención y buenas notas. Lo ideal es tener uno viable de cada tipo: el script avisa cuál falta.
3. **Copiabilidad** (`--copiable baja|media|alta`, con `--motivo`). Uno fácil de copiar sirve para entrar, pero no sostiene la posición.
4. **Cabe en el presupuesto** (`--semanas`): se construye dentro de las semanas de la sesión 0.
5. **Supera al rival**, si lo hay: `frente … --resultado supera` con al menos un hallazgo triangulado, frente a cada rival (arriba). Igualarlo es paridad y no cumple; un sustituto sin evaluar tampoco da el criterio por cumplido.

Y además, **sus hallazgos tienen que estar triangulados** (la regla de [evidencia.md](evidencia.md)), todos los que cita, también los de sus comparaciones con el rival:

| Estado | Cuándo | Cuenta para la puerta 1 |
| --- | --- | --- |
| Viable | Los cinco criterios y sus hallazgos triangulados | Sí |
| Viable con confianza baja | Los cinco criterios, pero algún hallazgo sin triangular | No: se muestra aparte, y el puntaje de diferenciación llega como máximo a 2, salvo que solo falte la prueba de elección (el dolor triangulado: se puede probar) |
| No viable (paridad) | Iguala al rival (`frente … --resultado iguala`) | No: es básico en Kano. Entra al MVP si hace falta para competir, pero no puede ser el principal |
| No viable | Falta alguno de los cinco criterios | No |

Son tres estados (viable, viable con confianza baja y no viable; la paridad es una forma de no viable) y se escriben con esas mismas palabras en el script, el banner de la puerta, los criterios, el reporte y el tablero. El banner nombra a todos los diferenciadores que deciden el veredicto, con su estado.

Un vector medible comprobado en la matriz cumple el criterio de evidencia, pero si el hallazgo que lo sostiene no está triangulado, el diferenciador queda con confianza baja. `producto.py triangulacion` dice qué le falta a cada hallazgo.

Un diferenciador que no es viable queda registrado igual, con lo que le falta. Si consigues la evidencia (por ejemplo, una tercera fuente vigente del mismo hallazgo), el estado se recalcula solo; si cambia el diferenciador, vuelve a registrarlo y anula el anterior (`producto.py anular --id D-1 --motivo "…"`).

## El diferenciador principal

Es el que sostiene la propuesta de valor (sesión 2), el que la sesión 3 pone a prueba con el abogado del diablo y el que el MVP incluye **siempre** (sesión 4). Elige el viable que mejor combine evidencia, que se vea en la ficha y que sea difícil de copiar. Solo hay uno: `producto.py principal --id D-2` (o un diferenciador nuevo con `--principal`) reemplaza al anterior. La puerta 1 exige que **sus hallazgos estén triangulados y que supere al rival**: un principal viable con confianza baja o que solo iguala al rival no la cumple, aunque haya otro viable.

**Se elige en la sesión 1g.** Con 1g cerrada, `diferenciador`, `principal` y `anular D-…` se niegan: cambiar el principal después (por ejemplo, porque la sesión 2 o la 3 encontró que no se sostiene) es una decisión del usuario. Regístralo como propuesta para la puerta siguiente, con la sesión que lo aplicaría:

```bash
python3 -I <skill>/scripts/producto.py propuesta --texto "Cambiar el principal a D-2: D-1 no sobrevive al abogado del diablo" --ajustar 1g
```

La puerta la muestra junto a los comandos de la decisión, con el `--ajustar 1g` ya listo. Si el usuario ajusta 1g, esa sesión elige el principal nuevo con `principal`.

## Diferenciarse no es copiar

Nada de marcas, nombres, textos, íconos, capturas ni diseños de la competencia, ni "como <app>, pero…" en la ficha. Se compite con un valor propio, no con el parecido.
