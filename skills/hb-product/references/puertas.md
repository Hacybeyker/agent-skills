# Puertas: criterios, decisiones y archivo

Las puertas existen para **descartar barato**: antes de programar, y solo con motivo. El script evalúa cada criterio y **la skill recomienda; la decisión es del usuario**.

## Cómo funciona una puerta

1. La sesión que la precede termina con `producto.py siguiente`, que empieza con **el banner del veredicto y la recomendación** (más abajo, cómo se calculan), sigue con **los criterios uno por uno** (✔ o ✖) con el juego del tipo de idea, los avisos y las propuestas, y termina con los comandos de la decisión, **el recomendado primero**. No hace falta correr `puerta` aparte: `producto.py puerta --n <1|2|3>` muestra lo mismo cuando quieras volver a mirarlo, y no escribe nada.
2. Los avisos no son criterios, pero no se pasan por alto: los criterios cambiados después de la sesión 0, la confianza global baja, los huecos de cobertura, los vacíos por límite de las herramientas y la meta de ingresos como referencia.
3. El usuario decide en su terminal, con uno de estos:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --seguir --carpeta product
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --ajustar 1c --carpeta product
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --descartar "<motivo>" --carpeta product
```

Los que van en contra de la recomendación llevan `--motivo "<por qué decides distinto>"`: sin él, `decidir` no registra nada. El agente **nunca corre `decidir`**: entrega los comandos tal como los imprime el script y se detiene. Cada decisión queda en `decisiones.json` con la fecha, la hora, los criterios evaluados en ese momento, la recomendación de la skill, si fue en contra (con el motivo) y, si consta, desde dónde se corrió. Si una decisión no fue del usuario, `decidir --puerta <n> --reabrir` la deshace.

## Veredicto y recomendación

En cada puerta, `producto.py` calcula un veredicto con **reglas fijas** sobre los criterios y la confianza, y lo muestra en un banner grande y con color: al inicio de la puerta en `siguiente` y en `puerta`, arriba del reporte y en el tablero. El banner trae 1 a 3 razones y **qué cambiaría el veredicto**. No lo cambies ni des otra recomendación por tu lado: la skill recomienda y el usuario decide.

| Veredicto | Recomienda | Cuándo |
| --- | --- | --- |
| 🔴 No viable | Descartar (el comando trae el motivo listo, con las razones) | Falla algo que ajustar una sesión no arregla. **P1:** el puntaje bajo el mínimo (también el recalculado con las reglas de hoy), la demanda con confianza baja (en una idea nueva, el problema sin documentar), ningún diferenciador viable (o **ninguno que supere a la alternativa gratis más fuerte con hallazgos triangulados**: igualarla es paridad), un bloqueo de políticas sin mitigación escrita o un intento anterior que fracasó por demanda. **P2:** ningún modelo genera ingresos en el caso base, una hipótesis crítica refutada, el principal no sobrevive y no hay otro viable, o el caso base no llega a la meta obligatoria. **P3:** el checklist de políticas con bloqueos. **También es No viable** lo que solo se arreglaría ajustando una 1g que ya se reabrió y usó su presupuesto (abajo) |
| 🟡 Viable con reservas | Ajustar `<sesión>` (la primera que lo completa) | No hay nada de lo anterior, pero falta algo que una sesión completa (el rival sin marcar, un diferenciador viable con confianza baja, el principal sin triangular o que solo iguala al rival, **un diferenciador que supera al rival sin prueba de elección**, los análogos o la búsqueda de intentos, los escenarios, la hipótesis más riesgosa, el PRD), **la confianza global es baja** (ajusta la línea más débil) o hay **propuestas pendientes que se pueden cerrar con las herramientas disponibles** (una propuesta para una línea con vacíos por límite de las herramientas no cuenta) |
| 🟢 Viable | Seguir | Cumple todos los criterios y, en la puerta 1, con confianza global media o alta y un diferenciador viable que supera al rival con prueba de elección |

- **Decidir en contra** es legítimo: el usuario puede saber algo que la evidencia pública no muestra. `decidir` pide `--motivo` (10 caracteres o más) cuando la decisión es de otro tipo que la recomendada **o ajusta otra sesión que la recomendada**, y la puerta queda como "decisión contra la recomendación", con ese motivo, en `decisiones.json`, en `estado.md` y en el reporte.
- **Lo no buscado no descarta (P1).** Si una línea cerró con otro tipo de idea y no tiene fuentes de los peldaños que pide el tipo de hoy ("a revisar por cambio de tipo"), o si nadie buscó el problema en los peldaños 4 y 5 de una idea nueva (ni hallazgos ni `vacio --peldano`), la skill no recomienda descartar por los criterios que dependen de esa evidencia (el puntaje, la demanda, el problema): recomienda 🟡 ajustar la línea que falta, empezando por la 1c ([analogia.md](analogia.md)).
- **El rival pendiente se completa en la 1g.** `competidor --rival` no pide la 1a abierta; lo que sí pide una sesión abierta es comparar cada diferenciador con él (`frente`), que es de la 1g. Por eso, si falta marcar el rival, la recomendación es ajustar la 1g, no la 1a. Si un sustituto con tracción llegó después de marcar el rival, la puerta pide revisarlo ([diferenciacion.md](diferenciacion.md)).
- **Los estados con las mismas palabras.** Un diferenciador es viable, viable con confianza baja o no viable (la paridad es una forma de no viable), con esas palabras en el banner, los criterios, el reporte y el tablero; el banner nombra a todos los que deciden el veredicto.
- **El puntaje registrado con reglas anteriores** se compara con las de hoy: si ya no cabe (por ejemplo, diferenciación 4 sin ningún diferenciador viable), el criterio, el veredicto, el reporte y el tablero muestran como principal el puntaje de hoy, con "se registró N/25" como dato secundario ([puntaje.md](puntaje.md)).
- **El puntaje según el modelo de monetización.** Si la sesión 0 registró más de un modelo y la síntesis puntuó con cada uno (`puntaje --modelo … --alternativo …`), la puerta 1 muestra el puntaje con cada modelo y cuál exige: una decisión de modelo que todavía se puede cambiar en la sesión 2 no se lee como un defecto de la oportunidad.
- **El rival y la prueba de elección (P1).** El rival es la alternativa gratis más fuerte, sea otra app o un sustituto ([diferenciacion.md](diferenciacion.md)). Si ningún diferenciador lo supera con un hallazgo triangulado, es 🔴. Si alguno lo supera, pero sin prueba de elección (algún hallazgo de la comparación en confianza media o sin triangular, o una hipótesis sobre ese diferenciador débil o refutada), es 🟡: ajustar la sesión que lo pruebe (la de esos hallazgos; desde la puerta 1, un hallazgo de la validación se completa en la 1g) o buscar un vector sin investigar.
- **La 1g agotada no se recomienda otra vez.** Si la 1g ya se reabrió y usó su presupuesto (el 80 % de las búsquedas o de las lecturas, que anota `cerrar --sesion 1g --busquedas <n> --lecturas <n>`; sin ese dato, las lecturas son las fuentes de la línea), la skill no recomienda ajustarla para buscar más evidencia: recomienda otro ajuste que lo resuelva y, si no queda ninguno, el veredicto es 🔴, con esa razón. Elegir otro principal entre los viables no pide búsquedas y sí se recomienda.
- La cantidad de competidores nunca entra en el veredicto.

## Criterios por defecto

La cantidad de competidores **no** es un criterio: ni la saturación ni la falta de datos descartan una idea.

### P1 · Oportunidad (después de la sesión 1f)

| Idea existente o variante | Idea nueva |
| --- | --- |
| Puntaje de 17/25 o más | Puntaje de 15/25 o más |
| Demanda con confianza media o alta | El problema o la necesidad de fondo, con 3 fuentes independientes y vigentes de peldaño 4 o 5 |
| Al menos 1 diferenciador viable, con sus hallazgos triangulados y que supere a la alternativa gratis más fuerte, marcada en 1a o dicho que no la hay ([diferenciacion.md](diferenciacion.md)) | Al menos 2 análogos con tracción (peldaño 2 o 3) en la matriz |
| Los hallazgos del diferenciador principal están triangulados y supera a la alternativa gratis más fuerte | Sin evidencia de que se probó y fracasó por falta de demanda (con la búsqueda registrada) |
| Riesgo de políticas distinto de 1, o con una mitigación escrita | Si hay una alternativa gratis marcada o un sustituto gratuito o nativo que ya resuelve la necesidad, un diferenciador viable que lo supere |
| | Riesgo de políticas distinto de 1, o con una mitigación escrita |

**El riesgo es 1 si una tienda objetivo nombra la categoría o la rechaza** (un hallazgo de políticas con `--bloquea <tienda>`): la puerta muestra en qué tienda es bloqueante y la mitigación escrita, para que juzgues si es creíble. **El rival** es la alternativa gratis más fuerte, sea otra app o un sustituto: si la función que ya trae el sistema o una app gratis y completa resuelven la necesidad, ganarle a las otras apps no alcanza, e **igualarlas es paridad**, no una razón para elegir la app. Un diferenciador viable con confianza baja no cumple ninguno de los dos criterios de diferenciación, y si el principal tiene hallazgos sin triangular, la puerta lo dice aunque haya otro viable: elegir otro principal es ajustar 1g. Si la confianza global es baja, la puerta avisa aunque los criterios se cumplan.

### P2 · Viabilidad (después de las sesiones 2 y 3)

| Idea existente o variante | Idea nueva |
| --- | --- |
| Al menos un modelo de monetización viable con evidencia | Al menos un modelo de monetización viable con evidencia (por analogía) |
| Ninguna hipótesis crítica refutada | Ninguna hipótesis crítica refutada |
| El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta | La hipótesis más riesgosa, identificada y medible después del lanzamiento |

Un modelo es viable con evidencia si genera ingresos en el caso base de `escenarios` y todos sus supuestos citan su fuente ([estrategia.md](estrategia.md)). **La meta de ingresos es opcional y referencial:** si existe, la puerta muestra cuánto da el caso base contra ella, como aviso. Solo si el usuario la marcó como obligatoria (`meta_obligatoria = si`) se suma un criterio: "El escenario base alcanza la meta de ingresos".

### P3 · Alcance (después de la sesión 4)

| Todas las ideas | Además, en una idea nueva |
| --- | --- |
| El MVP cabe en el presupuesto de semanas | El MVP pone a prueba la hipótesis más riesgosa, con una métrica y un umbral |
| El diferenciador principal está en el MVP | |
| 100 % de las funcionalidades del MVP con trazabilidad | |
| Métricas HEART definidas | |
| Checklist de políticas sin bloqueos | |

## Los criterios y cómo cambiarlos

`producto.py criterio` los lista; viven en `criterios.md`, en una tabla que mantiene el script.

| Clave | Por defecto | Qué es |
| --- | --- | --- |
| `puntaje_minimo` | 17 | Mínimo de la puerta 1, de 25, para una idea existente o variante |
| `puntaje_minimo_nueva` | 15 | Mínimo de la puerta 1 para una idea nueva |
| `vigencia_meses` | 18 | Ventana en la que una fuente cuenta para triangular |
| `fuentes_minimas` | 3 | Fuentes independientes de un hallazgo clave |
| `analogos_minimos` | 2 | Análogos con tracción que pide la puerta 1 de una idea nueva |
| `traccion_descargas` | 100000 | Descargas desde las que un competidor o un análogo tiene tracción |
| `traccion_valoraciones` | 2000 | Sin descargas publicadas (App Store), valoraciones desde las que la tracción se estima: la puerta dice "tracción estimada por valoraciones" |
| `meta_ingresos_mes` | 0 (sin meta) | Meta de ingresos netos al mes: opcional y referencial |
| `meta_obligatoria` | no | `si` la vuelve criterio de la puerta 2 |
| `moneda` | USD | Moneda de la meta |
| `presupuesto_semanas` | (sesión 0) | Semanas para construir el MVP |

- **Durante la sesión 0:** `producto.py criterio --clave <clave> --valor <valor>`, las veces que haga falta.
- **Después de cerrar la sesión 0:** exige `--motivo "<por qué>"`. El cambio queda registrado con su fecha, aparece en `criterios.md` y **cada puerta lo muestra** ("Criterio cambiado después de la sesión 0…"). Los criterios se fijan antes de investigar justamente para que nadie los mueva al ver los resultados.
- Un criterio lo cambia el usuario, o el agente cuando el usuario se lo pide. Nunca lo cambies para que una puerta se cumpla.
- El objetivo de mercados, idiomas y tiendas sigue la misma regla: `producto.py objetivo … --motivo "<por qué>"` después de la sesión 0, y la puerta lo muestra como un criterio cambiado.

## Propuestas

Lo que una sesión descubre y cambiaría algo ya cerrado (el diferenciador principal, una línea de investigación) **no se aplica con un comando suelto**: se registra con `producto.py propuesta --texto "<qué y por qué>" [--ajustar <sesión>]`. Queda para la puerta siguiente, que la muestra junto a los comandos de la decisión; con `--ajustar`, el comando de ajustar esa sesión ya viene listo. La decisión del usuario en esa puerta la resuelve (queda anotada en `decisiones.json`).

## Seguir, ajustar o descartar

- **Seguir** abre las sesiones siguientes. Se puede seguir con criterios sin cumplir: es una decisión del usuario, y queda anotado cuántos cumplía.
- **Ajustar `<sesión>`** reabre esa sesión y todo lo que depende de ella; las puertas que estaban después vuelven a quedar pendientes. Lo ya escrito se conserva: cada sesión corrige lo suyo y vuelve a cerrar. Por ejemplo, ajustar `1c` en la puerta 1 reabre `1c` y `1f`; ajustar `1a` reabre también `1g`.
- **Descartar `"<motivo>"`** registra la decisión y **archiva** la idea. El motivo es lo que queda como aprendizaje: qué evidencia en contra hubo o qué camino no existía.

Una idea se descarta con evidencia en contra, cuando ningún peldaño muestra el problema o, con competencia, cuando no aparece ningún diferenciador viable. Si el usuario quiere descartar "porque hay muchos competidores", "porque no hay datos" o "porque no llega a la meta" (sin haberla marcado como obligatoria), dile qué dice la puerta antes de que decida: la decisión sigue siendo suya.

**Vacíos por límite de las herramientas.** Si a una línea le faltan fuentes porque tus herramientas no leen esas páginas (reseñas dinámicas, foros bloqueados), no sugieras ajustarla: con las mismas herramientas da lo mismo. Sugiere lo que sí lo resuelve (un navegador en el agente o un CSV de reseñas que aporte el usuario) y, con eso, el ajuste. `decidir --ajustar` lo recuerda si la línea tiene vacíos así.

## Reporte y tablero

- **`reporte.html`** vive en la carpeta de la idea y se regenera solo cada vez que el usuario decide una puerta y al archivar (también al descartar: queda dentro de `archivo/<nombre>/`). Es un solo archivo, sin red, en claro y oscuro: arriba el banner del veredicto (el de la puerta pendiente o, si no hay, el de la última decidida, recalculado con las reglas de hoy), luego el resumen ejecutivo (estado, decisión con su motivo, siguiente paso y los 3 a 5 hallazgos que decidieron, abiertos y con sus fuentes) y debajo tarjetas con el puntaje, las puertas, los diferenciadores, los hallazgos clave, los competidores, la cobertura, los escenarios (solo referencia), la hipótesis más riesgosa y el costo. Lo técnico va plegado. `producto.py reporte` lo regenera a mano; `--idea <nombre>` para una idea archivada.
- **`producto.py tablero --raiz <carpeta>`** busca todas las ideas bajo esa carpeta (en curso y archivadas), regenera su reporte y escribe `<carpeta>/index.html`: el veredicto de cada una (en color), su estado, puntaje, última puerta, motivo o siguiente paso y el enlace a cada reporte. Cada idea está en **un solo estado**: en curso, lista para construir (la puerta 3 aprobó el PRD), descartada (en una puerta) o pausada (archivada a mano). Las descartadas y las pausadas viven en `archivo/`.
- La confianza del reporte se calcula con la fecha del día en que se genera: puede bajar si las fuentes envejecen. Los criterios de cada puerta ya decidida son los de ese momento.

## Archivo

- `producto.py archivar --motivo "<motivo>"` mueve la idea activa a `<carpeta>/archivo/<nombre>/`. No borra nada. Descartar en una puerta hace lo mismo.
- `producto.py reabrir [--idea <nombre>]` la recupera, si no hay otra idea activa. Una idea descartada vuelve con su puerta pendiente.
- Con la carpeta libre, `producto.py nuevo` empieza otra idea. `producto.py siguiente` lista las archivadas con su motivo.

## Cuando todo cierra

Con la puerta 3 decidida como "seguir", `siguiente` dice que el proceso cerró. La construcción se pide a `hb-implement`, una funcionalidad del PRD a la vez, citando su ID.
