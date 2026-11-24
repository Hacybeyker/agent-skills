# Ideas con competencia: la diferenciación (sesión 1g)

Si ya existen apps iguales o parecidas, la demanda está probada y la pregunta cambia: **¿por qué alguien elegiría la tuya?** **Saturado no es lo mismo que cerrado:** la idea sigue adelante si encuentra un valor extra con evidencia.

## Presupuesto y lista de tareas

**Cuándo:** apenas cierran 1a y 1b, sin esperar a 1c–1e. **Presupuesto:** 15 búsquedas y 10 lecturas (20 y 12 en una idea nueva); casi todo sale de lo ya registrado.

1. Primera línea: `Sesión 1g · Diferenciación (<motivo>)`.
2. `producto.py tipo` y `producto.py matriz`: la matriz de 1a con los hallazgos que 1b enlazó a cada competidor.
3. Lee `competencia.md` y `voz-del-usuario.md` (solo esos dos).
4. Recorre los 12 vectores y anota el hueco de cada uno, o "sin hueco".
5. Arma el cuadro ERRC, la clasificación Kano y el mapa de posicionamiento.
6. Si a un hueco le falta evidencia, búscala y regístrala en la línea `diferenciacion` (`producto.py fuente` y `hallazgo`).
7. Registra cada diferenciador con `producto.py diferenciador`: dice si es viable y por qué. Elige el principal con `--principal` o, después, con `producto.py principal --id D-…`.
8. Abogado del diablo: por qué los competidores no lo hicieron ya y cuánto tardarían en copiarlo.
9. Completa `diferenciacion.md` y `producto.py cerrar --sesion 1g`.

**Si ningún diferenciador es viable, dilo tal cual.** Es un resultado válido: la puerta 1 lo muestra y el usuario decide. No inventes uno para salvar la idea.

## Matriz de competidores

La arma la sesión 1a: una fila por competidor y una columna por vector (descargas, nota, última actualización, precio y modelo, intensidad de anuncios, tamaño, idiomas, permisos, sin conexión, accesibilidad, plataformas y funcionalidades clave). `producto.py matriz` le suma a cada fila los hallazgos de 1b que la nombran: ahí está la queja principal de cada competidor.

En una idea nueva, las filas son los análogos y los sustitutos: la comparación es contra la hoja de cálculo o el grupo de chat.

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

El script lo registra (`D-1`) y dice si es **viable**, **viable con confianza baja** o **todavía no viable**. Tiene que cumplir los cuatro criterios:

1. **Evidencia.** Una de dos: un dolor o un pedido **triangulado en 2 competidores o más** (un hallazgo con sus 3 fuentes y `--competidores` con dos filas de la matriz), o un **vector medible comprobado en la matriz** en 2 competidores o más (`precio`, `rendimiento` por el tamaño, `anuncios`, `idioma`, `privacidad` por los permisos, `sin-conexion`, `accesibilidad`, `diseno` por la última actualización y `plataforma`). `usabilidad`, `funcionalidades` y `segmento` no se miden en la matriz: necesitan el dolor triangulado. Es el filtro del *diferenciador imaginario*.
2. **Se percibe** (`--se-ve`). En la **ficha** de la tienda (precio, idioma, sin anuncios, diseño), que es lo que consigue descargas, o en el **uso** (rendimiento, usabilidad), que es lo que consigue retención y buenas notas. Lo ideal es tener uno viable de cada tipo: el script avisa cuál falta.
3. **Copiabilidad** (`--copiable baja|media|alta`, con `--motivo`). Uno fácil de copiar sirve para entrar, pero no sostiene la posición.
4. **Cabe en el presupuesto** (`--semanas`): se construye dentro de las semanas de la sesión 0.

Y además, **sus hallazgos tienen que estar triangulados** (la regla de [evidencia.md](evidencia.md)), todos los que cita:

| Estado | Cuándo | Cuenta para la puerta 1 |
| --- | --- | --- |
| Viable | Los cuatro criterios y sus hallazgos triangulados | Sí |
| Viable con confianza baja | Los cuatro criterios, pero algún hallazgo sin triangular | No: se muestra aparte, y el puntaje de diferenciación llega como máximo a 2 |
| Todavía no viable | Falta alguno de los cuatro criterios | No |

Un vector medible comprobado en la matriz cumple el criterio de evidencia, pero si el hallazgo que lo sostiene no está triangulado, el diferenciador queda con confianza baja. `producto.py triangulacion` dice qué le falta a cada hallazgo.

Un diferenciador que no es viable queda registrado igual, con lo que le falta. Si consigues la evidencia (por ejemplo, una tercera fuente vigente del mismo hallazgo), el estado se recalcula solo; si cambia el diferenciador, vuelve a registrarlo y anula el anterior (`producto.py anular --id D-1 --motivo "…"`).

## El diferenciador principal

Es el que sostiene la propuesta de valor (sesión 2), el que la sesión 3 pone a prueba con el abogado del diablo y el que el MVP incluye **siempre** (sesión 4). Elige el viable que mejor combine evidencia, que se vea en la ficha y que sea difícil de copiar. Solo hay uno: `producto.py principal --id D-2` (o un diferenciador nuevo con `--principal`) reemplaza al anterior. La puerta 1 exige que **sus hallazgos estén triangulados**: un principal viable con confianza baja no la cumple, aunque haya otro viable.

**Se elige en la sesión 1g.** Con 1g cerrada, `diferenciador`, `principal` y `anular D-…` se niegan: cambiar el principal después (por ejemplo, porque la sesión 2 o la 3 encontró que no se sostiene) es una decisión del usuario. Regístralo como propuesta para la puerta siguiente, con la sesión que lo aplicaría:

```bash
python3 -I <skill>/scripts/producto.py propuesta --texto "Cambiar el principal a D-2: D-1 no sobrevive al abogado del diablo" --ajustar 1g
```

La puerta la muestra junto a los comandos de la decisión, con el `--ajustar 1g` ya listo. Si el usuario ajusta 1g, esa sesión elige el principal nuevo con `principal`.

## Diferenciarse no es copiar

Nada de marcas, nombres, textos, íconos, capturas ni diseños de la competencia, ni "como <app>, pero…" en la ficha. Se compite con un valor propio, no con el parecido.
