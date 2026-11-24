# Puertas: criterios, decisiones y archivo

Las puertas existen para **descartar barato**: antes de programar, y solo con motivo. El script evalúa cada criterio; **la decisión es del usuario**.

## Cómo funciona una puerta

1. La sesión que la precede termina con `producto.py siguiente`, que imprime los comandos de la puerta.
2. `producto.py puerta --n <1|2|3>` muestra el veredicto criterio por criterio (✔ o ✖), con el juego de criterios del tipo de idea y los criterios que se cambiaron después de la sesión 0. No escribe nada.
3. El usuario decide en su terminal, con uno de estos:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --seguir --carpeta product
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --ajustar 1c --carpeta product
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --descartar "<motivo>" --carpeta product
```

El agente **nunca corre `decidir`**: entrega los comandos tal como los imprime el script y se detiene. Cada decisión queda en `decisiones.json` con la fecha, la hora, los criterios evaluados en ese momento y, si consta, desde dónde se corrió. Si una decisión no fue del usuario, `decidir --puerta <n> --reabrir` la deshace.

## Criterios por defecto

La cantidad de competidores **no** es un criterio: ni la saturación ni la falta de datos descartan una idea.

### P1 · Oportunidad (después de la sesión 1f)

| Idea existente o variante | Idea nueva |
| --- | --- |
| Puntaje de 17/25 o más | Puntaje de 15/25 o más |
| Demanda con confianza media o alta | El problema o la necesidad de fondo, con 3 fuentes independientes y vigentes de peldaño 4 o 5 |
| Al menos 1 diferenciador viable | Al menos 2 análogos con tracción (peldaño 2 o 3) en la matriz |
| Riesgo de políticas distinto de 1, o con una mitigación escrita | Sin evidencia de que se probó y fracasó por falta de demanda (con la búsqueda registrada) |
| | Riesgo de políticas distinto de 1, o con una mitigación escrita |

### P2 · Viabilidad (después de las sesiones 2 y 3)

| Idea existente o variante | Idea nueva |
| --- | --- |
| El escenario base alcanza la meta de ingresos | El escenario base por analogía alcanza la meta |
| Ninguna hipótesis crítica refutada | Ninguna hipótesis crítica refutada |
| El diferenciador principal sobrevive al abogado del diablo, con confianza media o alta | La hipótesis más riesgosa, identificada y medible después del lanzamiento |

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
| `meta_ingresos_mes` | (sesión 0) | Meta de ingresos netos al mes |
| `moneda` | USD | Moneda de la meta |
| `presupuesto_semanas` | (sesión 0) | Semanas para construir el MVP |

- **Durante la sesión 0:** `producto.py criterio --clave <clave> --valor <valor>`, las veces que haga falta.
- **Después de cerrar la sesión 0:** exige `--motivo "<por qué>"`. El cambio queda registrado con su fecha, aparece en `criterios.md` y **cada puerta lo muestra** ("Criterio cambiado después de la sesión 0…"). Los criterios se fijan antes de investigar justamente para que nadie los mueva al ver los resultados.
- Un criterio lo cambia el usuario, o el agente cuando el usuario se lo pide. Nunca lo cambies para que una puerta se cumpla.

## Seguir, ajustar o descartar

- **Seguir** abre las sesiones siguientes. Se puede seguir con criterios sin cumplir: es una decisión del usuario, y queda anotado cuántos cumplía.
- **Ajustar `<sesión>`** reabre esa sesión y todo lo que depende de ella; las puertas que estaban después vuelven a quedar pendientes. Lo ya escrito se conserva: cada sesión corrige lo suyo y vuelve a cerrar. Por ejemplo, ajustar `1c` en la puerta 1 reabre `1c` y `1f`; ajustar `1a` reabre también `1g`.
- **Descartar `"<motivo>"`** registra la decisión y **archiva** la idea. El motivo es lo que queda como aprendizaje: qué evidencia en contra hubo o qué camino no existía.

Una idea se descarta con evidencia en contra, cuando ningún peldaño muestra el problema o, con competencia, cuando no aparece ningún diferenciador viable. Si el usuario quiere descartar "porque hay muchos competidores" o "porque no hay datos", dile qué dice la puerta antes de que decida: la decisión sigue siendo suya.

## Archivo

- `producto.py archivar --motivo "<motivo>"` mueve la idea activa a `<carpeta>/archivo/<nombre>/`. No borra nada. Descartar en una puerta hace lo mismo.
- `producto.py reabrir [--idea <nombre>]` la recupera, si no hay otra idea activa. Una idea descartada vuelve con su puerta pendiente.
- Con la carpeta libre, `producto.py nuevo` empieza otra idea. `producto.py siguiente` lista las archivadas con su motivo.

## Cuando todo cierra

Con la puerta 3 decidida como "seguir", `siguiente` dice que el proceso cerró. La construcción se pide a `hb-implement`, una funcionalidad del PRD a la vez, citando su ID.
