---
name: hb-product
description: 'Lleva una idea de app (Android, iOS, web o multiplataforma) desde un texto general hasta un producto definido y sustentado con evidencia pública: investiga en paralelo competencia, voz del usuario, demanda, monetización y políticas; si la idea es nueva y no hay datos directos, investiga por analogía; si el mercado está saturado, busca cómo diferenciarse (usabilidad, rendimiento, precio, funcionalidades, idioma, privacidad o un segmento desatendido); arma la estrategia y el modelo de negocio; valida con abogado del diablo; escribe un PRD donde cada funcionalidad enlaza a su evidencia, y para en puertas donde el usuario decide seguir, ajustar o descartar. Úsala cuando el usuario quiera evaluar o definir una app nueva ("tengo una idea de app", "valida esta idea", "investiga el mercado de X", "cómo me diferencio de X", "arma el PRD de mi app", "sigue hb-product con estado.md", "/hb-product").'
license: MIT
compatibility: "Requiere un agente con búsqueda y lectura web, y Python 3.8+ (solo librería estándar). No instala ni configura nada en la máquina."
metadata:
  author: hacybeyker
  version: "0.1.0"
  category: flow
---

# hb-product

Lleva una idea de app, escrita en términos generales, hasta un **producto definido y sustentado con evidencia pública**: investigación, diferenciación, estrategia, validación documental y PRD. El trabajo es de una persona y una IA, sin testers ni entrevistas: cada decisión se apoya en datos públicos verificables (tiendas, reseñas, redes, foros, blogs y reportes).

- **Investigar no es validar.** Todo hallazgo es una hipótesis con su confianza. La validación con usuarios reales llega después del lanzamiento, con métricas.
- **Descartar barato, pero solo con motivo.** Las puertas existen para descartar antes de programar, y una idea se descarta solo con evidencia en contra o sin un camino viable.
- **Sin datos no es lo mismo que sin demanda.** Una idea nueva no tiene competidores ni reseñas: la investigación sube por la escalera de analogía ([analogia.md](references/analogia.md)).
- **Saturado no es lo mismo que cerrado.** Con varias apps parecidas, la demanda está probada: la idea sigue si encuentra un diferenciador viable ([diferenciacion.md](references/diferenciacion.md)).
- **No es** un generador de ideas ni reemplaza a `hb-implement`. No garantiza el éxito: reduce el riesgo de construir algo sin demanda o sin razón para elegirlo.

## Lo que cuesta son los tokens

Cada paso del agente reenvía todo el chat. Por eso cada sesión vive en **su propio chat** y pasa el trabajo por `estado.md`; lo determinista lo hace `scripts/producto.py` (registro de fuentes, confianza, puntaje, escenarios, trazabilidad, puertas y el paso siguiente), y cada línea de investigación tiene un presupuesto de búsquedas y lecturas. Para el usuario, [prompts.md](references/prompts.md) tiene los textos listos para copiar.

## Reglas

1. **Evidencia o nada.** Cada afirmación clave lleva fuentes registradas con `producto.py fuente` (URL, fecha de publicación, tipo, línea y peldaño). Lo que no tiene fuente va como **⚠ Sin evidencia**.
2. **Triangulación.** Un hallazgo clave necesita **3 fuentes independientes** publicadas dentro de la **ventana de vigencia** (18 meses); si es de demanda o de monetización, al menos una de tipo *medido*. En una idea nueva se triangula el peldaño más cercano a lo directo que tenga evidencia, no la solución exacta ([evidencia.md](references/evidencia.md)).
3. **La confianza la calcula el script** con la cantidad, el tipo, la fecha y el peldaño de las fuentes. Puedes bajarla con un motivo (`producto.py confianza`), nunca subirla.
4. **Abogado del diablo obligatorio.** Por cada hipótesis crítica buscas evidencia en contra ("por qué fallaría", "quién lo intentó y cerró") y la registras, también cuando no aparece nada (`--en-contra`, `--sin-contra`, `producto.py intento`). En una idea nueva: ¿no existe porque nadie la pensó o porque alguien la probó y no funcionó? En una saturada: ¿por qué los competidores no lo hicieron ya, y cuánto tardarían en copiarlo?
5. **Ni la falta de datos ni la saturación son motivo de descarte.** Una idea solo se descarta con evidencia en contra, cuando ningún peldaño muestra el problema o, con competencia, cuando no aparece ningún diferenciador viable. Nunca recomiendes descartar por la cantidad de competidores.
6. **Criterios de descarte antes de investigar.** Se fijan en la sesión 0 (`criterios.md`). Cambiarlos después exige `producto.py criterio --motivo`, y cada puerta lo muestra.
7. **Los números los calcula `producto.py`:** confianza, puntaje, escenarios de ingresos, RICE, conteos de triangulación, trazabilidad y veredictos de las puertas. Tú interpretas: nunca haces cuentas por tu lado ni editas a mano los `.json` del registro.
8. **La decisión es del usuario.** Nunca corras `producto.py decidir`, aunque el pedido parezca justificarlo: entrega el comando completo y detente.
9. **Dato medido o estimación.** Toda estimación dice cómo se calculó, con qué supuestos y, si viene de un análogo, de cuál.
10. **Una sesión por chat, y al terminar te detienes**, con el traspaso en `estado.md`. Lo que no depende de otra sesión corre en paralelo; lo que depende, después. No sigas con la sesión siguiente aunque te digan "sigue": explica que en este chat cuesta varias veces más.
11. **Agnóstica.** La plataforma, el stack, el modelo de negocio y los mercados salen de `00-idea.md`. No asumas Android, anuncios ni ningún país.
12. **Privacidad y legalidad.** Citas breves o parafraseadas, sin nombres de usuario ni datos personales de quienes escriben reseñas. Respeta los términos de uso: nada de scraping que los viole ni de saltar muros de pago. Diferenciarse no es copiar: nada de marcas, textos, íconos ni diseños de la competencia.
13. **Salidas acotadas.** Nunca vuelques páginas completas al chat ni a los archivos: cada fuente se resume en 3 líneas como máximo, en su registro. No leas `producto.py`: usa `--help` y lo que imprime.
14. **Siguiente paso siempre explícito.** Tu último paso es `producto.py siguiente`: pega su salida tal cual, como último bloque de tu respuesta y dentro de un bloque de código. Cuando no queda nada, dice que el proceso cerró.
15. **Comandos para el usuario:** uno por paso, en un bloque de código y empezando con `cd <ruta absoluta> && ...`. Los que imprime `producto.py` ya vienen así: cópialos sin reescribirlos.
16. **Primera línea de cada sesión:** `Sesión <n> · <nombre> (<motivo>)`, por ejemplo `Sesión 1c · Demanda (Siguiente paso de estado.md)`.
17. **Español neutro** (tú, no vos) en todo lo que escribas.
18. **Git:** no hagas commit ni push salvo que el usuario lo pida. Si la carpeta del producto queda dentro de un repo público, pregunta antes de versionarla: la estrategia puede ser sensible.

## Sesiones

| Sesión | Etapa | Lee | Hace | Entregable | En paralelo | Modelo | Termina con |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 · Idea | Descubrir | Esta página | Entrevista en una sola tanda, `producto.py nuevo`, la necesidad de fondo y los criterios | `00-idea.md`, `criterios.md`, `estado.md` | No | Intermedio | Las 5 líneas, listas para abrir |
| 1a · Competencia | Descubrir | [investigacion.md](references/investigacion.md) | Top 10 por tienda y mercado, matriz de competidores, **tipo de idea** e intentos anteriores | `01-investigacion/competencia.md` | Sí (1a–1e) | Intermedio | Fuentes, hallazgos y tipo registrados |
| 1b · Voz del usuario | Descubrir | [investigacion.md](references/investigacion.md) | Reseñas de 1 a 3★, foros, redes y blogs: dolores, pedidos y quejas por competidor | `01-investigacion/voz-del-usuario.md` | Sí | Intermedio | Ídem |
| 1c · Demanda | Descubrir | [investigacion.md](references/investigacion.md) | Búsquedas, tendencia, estacionalidad y tamaño de la audiencia | `01-investigacion/demanda.md` | Sí | Intermedio | Ídem |
| 1d · Monetización | Descubrir | [investigacion.md](references/investigacion.md) | Modelos, precios, eCPM, conversión y afiliados | `01-investigacion/monetizacion.md` | Sí | Intermedio | Ídem |
| 1e · Políticas y riesgos | Descubrir | [investigacion.md](references/investigacion.md) | Políticas de las tiendas, leyes, requisitos de cuenta y riesgos técnicos | `01-investigacion/politicas.md` | Sí | Intermedio | Ídem |
| 1g · Diferenciación | Descubrir | [diferenciacion.md](references/diferenciacion.md) | Huecos por vector, ERRC, Kano, posicionamiento y diferenciadores (`D-…`) | `01-investigacion/diferenciacion.md` | Sí, apenas cierran 1a y 1b | Alto | Diferenciadores registrados |
| 1f · Síntesis | Descubrir | [puntaje.md](references/puntaje.md) y [puertas.md](references/puertas.md) | Une las 6 líneas, `triangulacion` y `puntaje` | `01-sintesis.md` | No | Alto | **Puerta 1** |
| 2 · Estrategia | Validar | [estrategia.md](references/estrategia.md) | Jobs To Be Done, propuesta de valor, posicionamiento, Lean Canvas, PR/FAQ y `escenarios` | `02-estrategia.md` | Sí (con la 3) | Alto | Lista para la puerta 2 |
| 3 · Validación documental | Validar | [validacion.md](references/validacion.md) | Hipótesis críticas con evidencia a favor y en contra, veredicto e hipótesis más riesgosa | `03-validacion.md` | Sí (con la 2) | Alto | **Puerta 2**, cuando cierran la 2 y la 3 |
| 4 · PRD | Definir | [prd.md](references/prd.md) | MVP con RICE, historias, métricas HEART, eventos, monetización y checklist de políticas | `04-prd.md` | No | Alto | **Puerta 3** |

Cada sesión de investigación consulta primero `producto.py tipo` y lee también [evidencia.md](references/evidencia.md); si la idea es nueva, [analogia.md](references/analogia.md). Cada sesión se cierra con `producto.py cerrar --sesion <id>`, que comprueba que el entregable no tiene texto de plantilla y que lo mínimo está registrado. Las sesiones 5 a 10 (UX/UI, plan técnico, tienda, lanzamiento y medición) llegan en versiones siguientes; la construcción se delega a `hb-implement`, una funcionalidad del PRD a la vez citando su ID (`F-01`).

### Qué sesión te toca

- **Con un `estado.md`** ("sigue hb-product con …/estado.md"): corre primero `producto.py siguiente --carpeta <carpeta>`. Haces la sesión que nombra el pedido si `siguiente` la ofrece; si no la nombra y hay varias en paralelo, pregunta cuál. Si lo que sigue es una puerta, entrega los comandos y detente.
- **Sin `estado.md`:** es la sesión 0. Si `siguiente` dice que la idea está archivada, no hay nada que hacer salvo que el usuario la quiera reabrir.
- **Solo una consulta** ("cómo me diferencio de X", sin querer el proceso completo): dilo en la primera línea y ofrece empezar por la sesión 0; no investigues sin registro.

### Sesión 0 · Idea

1. Haz la entrevista en **una sola tanda**, con 8 preguntas como máximo y sin repetir lo que el pedido ya dice: problema, usuario, contexto de uso, plataformas, mercados e idiomas, modelo de negocio, **meta de ingresos al mes y presupuesto de semanas**, y lo que no debe ser.
2. Crea la carpeta: `producto.py nuevo --nombre "<nombre>" --meta <ingresos al mes> --semanas <presupuesto> [--moneda <ISO>] [--carpeta <ruta>]`. No pisa nada que ya exista.
3. Completa `00-idea.md` con lo que dijo el usuario; lo que no dijo va en "Supuestos sin confirmar". Escribe la **necesidad de fondo**: el "trabajo" del usuario sin nombrar la solución.
4. Completa `criterios.md`. Los umbrales por defecto (17/25, 15/25 si la idea es nueva, 18 meses y 3 fuentes) se cambian ahora con `producto.py criterio`; después hará falta un motivo.
5. `producto.py cerrar --sesion 0` y pega la salida: son los carriles de la investigación.

## Puertas

`producto.py puerta --n <1|2|3>` evalúa cada criterio con el juego que corresponde al tipo de idea; el usuario decide con `producto.py decidir --puerta <n> --seguir | --ajustar <sesión> | --descartar "<motivo>"`. La cantidad de competidores **no** es un criterio. El detalle, cómo cambiar un criterio y qué pasa al ajustar o descartar están en [puertas.md](references/puertas.md).

| Puerta | Idea existente o variante | Idea nueva |
| --- | --- | --- |
| P1 · Oportunidad | Puntaje de 17/25 o más · demanda con confianza media o alta · al menos 1 diferenciador viable · riesgo de políticas distinto de 1, o con mitigación escrita | Puntaje de 15/25 o más · el problema documentado con 3 fuentes de peldaño 4 o 5 · al menos 2 análogos con tracción · sin evidencia de que se probó y fracasó por falta de demanda · el mismo criterio de riesgo |
| P2 · Viabilidad | El escenario base alcanza la meta · ninguna hipótesis crítica refutada · el diferenciador principal sobrevive al abogado del diablo | El escenario base por analogía alcanza la meta · ninguna refutada · la hipótesis más riesgosa, identificada y medible |
| P3 · Alcance | MVP dentro del presupuesto · el diferenciador principal en el MVP · 100 % de trazabilidad · métricas HEART definidas · checklist de políticas sin bloqueos | Lo mismo, y el MVP pone a prueba la hipótesis más riesgosa con una métrica y un umbral |

Descartar archiva la idea en `archivo/` con su motivo: queda como aprendizaje y `producto.py reabrir` la recupera.

## Paralelismo

- **1a–1e a la vez.** Cada línea escribe solo su `.md` y su `.json` en `01-investigacion/`, y `producto.py` consolida: no hay dos sesiones escribiendo el mismo archivo. Las notas de una sesión en paralelo van en "Para la síntesis" de su archivo, no en `estado.md`.
- **1g** arranca apenas cierran 1a y 1b, sin esperar a 1c–1e. **2 y 3** van juntas; la puerta 2 espera a las dos.
- **Tipo de idea:** 1a lo registra apenas lo sabe (`producto.py tipo`). Las demás líneas lo consultan antes de buscar y otra vez antes de cerrar; si resulta nueva, trabajan por analogía sin repetir lo hecho.
- **Con subagentes** (si tu herramienta los tiene y el usuario lo pide): un chat orquestador lanza un subagente por carril con el texto que imprime `siguiente`; cada subagente es una sesión completa y devuelve 3 líneas. El orquestador no investiga: espera, corre `siguiente` y lanza lo que se abre. **Sin subagentes**, `siguiente` da un chat por carril para abrirlos a la vez.
- **Presupuesto por línea:** 15 búsquedas y 10 lecturas (20 y 12 si la idea es nueva). Al llegar al 80 %, dilo y cierra con lo que tienes; `producto.py fuente` avisa con las lecturas.

## Archivos del producto

```text
<carpeta>/                     por defecto ./product/ (o la línea `Carpeta:` de `## Producto` en AGENTS.md)
├── estado.md                  traspaso entre sesiones (los bloques marcados los reescribe producto.py)
├── criterios.md               criterios de descarte (sesión 0)
├── 00-idea.md                 incluye la necesidad de fondo
├── 01-investigacion/          una línea por archivo: <línea>.md y <línea>.json (fuentes, hallazgos, matriz)
├── 01-sintesis.md · 02-estrategia.md · 03-validacion.md · 04-prd.md
├── escenarios.json            supuestos de los escenarios de ingresos (sesión 2)
├── producto.json              registro del script: tipo, criterios, sesiones, puntaje y escenarios
├── decisiones.json            decisiones de las puertas, con fecha y criterios
└── archivo/                   ideas descartadas o archivadas, con su motivo
```

Si el proyecto todavía no existe, la carpeta vive sola; cuando se crea el repo, se mueve a su raíz y `hb-setup` la anota en `AGENTS.md`.

## Herramientas

`python3 -I <carpeta-de-la-skill>/scripts/producto.py <comando> [--carpeta <carpeta>]`, cada uno con `--help`. Lo que imprime cada comando termina con el paso siguiente.

| Comando | Qué hace |
| --- | --- |
| `nuevo` | Crea la estructura desde las plantillas y escribe `estado.md` |
| `criterio` | Muestra los criterios o cambia uno (después de la sesión 0, con `--motivo`) |
| `tipo` | Sin opciones, muestra el tipo de idea y el presupuesto; con `--existente`, `--variante` o `--nueva` y `--motivo`, lo registra |
| `fuente` | Registra una fuente y devuelve su ID (`S-COM-1`): `--linea --url --publicada --tipo --peldano --resumen [--autor]` |
| `hallazgo` | Registra un hallazgo (`H-DEM-1`) y calcula su confianza: `--linea --texto --fuentes [--en-contra] [--sin-contra] [--critico] [--competidores]` |
| `confianza` | Baja la confianza de un hallazgo, con su motivo |
| `competidor` · `matriz` | Registra o completa una fila de la matriz (`C-1`) · la muestra con los hallazgos enlazados a cada competidor |
| `intento` | Registra la búsqueda de intentos anteriores de la misma idea y su resultado |
| `diferenciador` | Registra un diferenciador (`D-1`) y dice si es viable: `--vector --texto --hallazgos --se-ve --copiable --motivo --semanas [--principal]` |
| `anular` | Anula una fuente, un hallazgo, un competidor o un diferenciador: deja de contar, sin borrarse |
| `triangulacion` | Lista los hallazgos clave y lo que le falta a cada uno |
| `puntaje` | Total, confianza global y comparación con la puerta 1: `--valores d,m,f,r,x [--mitigacion]` |
| `escenarios` | Casos pesimista, base y optimista, y usuarios activos diarios para la meta: `--entrada escenarios.json` |
| `validacion` · `trazabilidad` | Revisan las tablas de `03-validacion.md` y de `04-prd.md` (esta calcula el RICE) |
| `cerrar` | Cierra una sesión si su entregable está completo: `--sesion <id>` |
| `puerta` | Veredicto criterio por criterio: `--n <1\|2\|3>` |
| `decidir` | **Solo lo corre el usuario.** Registra la decisión con fecha; `--reabrir` la deshace |
| `siguiente` · `estado` | El paso siguiente o los carriles, con el texto para cada chat y el modelo sugerido · el resumen |
| `archivar` · `reabrir` | Mueve la idea a `archivo/` (no borra nada) o la recupera |

Otras skills, por intención y sin depender de sus archivos: `hb-setup` (anota `## Producto` en `AGENTS.md`), `hb-implement` (construye cada `F-…`), `hb-review`, `hb-performance` (si el diferenciador es de rendimiento), `hb-commit`, `hb-release`, `play-policy-insights` y `hb-coach` (para aprender un concepto: RICE, Kano o HEART).

## Checklist

- [ ] Primera línea con la sesión y el motivo; una sesión por chat; la última salida es la de `producto.py siguiente`, en un bloque de código.
- [ ] Criterios fijados en la sesión 0; ningún cambio posterior sin `--motivo`.
- [ ] Cada fuente registrada con su fecha, su tipo y su peldaño, y resumida en 3 líneas; ninguna página volcada; ninguna cita con nombre de usuario.
- [ ] Hallazgos clave triangulados o presentados con su confianza real; búsqueda de evidencia en contra registrada en cada uno, también cuando no apareció nada.
- [ ] Tipo de idea registrado por 1a y respetado por las demás líneas; en una idea nueva, cada hallazgo con su peldaño y la búsqueda de intentos anteriores hecha.
- [ ] Con competencia: matriz completa y cada diferenciador con evidencia, dónde se ve, copiabilidad y semanas. Si ninguno es viable, se dijo sin maquillarlo.
- [ ] Ninguna recomendación de descartar por la cantidad de competidores ni por falta de datos.
- [ ] Ningún número calculado a mano: confianza, puntaje, escenarios, RICE y veredictos salen de `producto.py`.
- [ ] Cada estimación dice cómo se calculó; los escenarios llevan sus rótulos (*estimación*, *por analogía*).
- [ ] PRD con trazabilidad al 100 % en el MVP, el diferenciador principal dentro y, en una idea nueva, la hipótesis más riesgosa con su métrica y su umbral.
- [ ] Cada puerta decidida por el usuario: el agente nunca corrió `decidir`.
- [ ] Ningún entregable con texto de plantilla; nada de marcas ni contenido copiado de la competencia; sin commit ni push no pedidos.
