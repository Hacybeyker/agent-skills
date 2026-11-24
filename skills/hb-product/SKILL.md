---
name: hb-product
description: 'Lleva una idea de app (Android, iOS, web o multiplataforma) desde un texto general hasta un producto definido y sustentado con evidencia pública: investiga en paralelo competencia, voz del usuario, demanda, monetización y políticas; si la idea es nueva y no hay datos directos, investiga por analogía; si el mercado está saturado, busca cómo diferenciarse (usabilidad, rendimiento, precio, funcionalidades, idioma, privacidad o un segmento desatendido); arma la estrategia y el modelo de negocio; valida con abogado del diablo; escribe un PRD donde cada funcionalidad enlaza a su evidencia, y para en puertas donde el usuario decide seguir, ajustar o descartar. Úsala cuando el usuario quiera evaluar o definir una app nueva ("tengo una idea de app", "valida esta idea", "investiga el mercado de X", "cómo me diferencio de X", "arma el PRD de mi app", "sigue hb-product con estado.md", "/hb-product").'
license: MIT
compatibility: "Requiere un agente con búsqueda y lectura web, y Python 3.8+ (solo librería estándar). Opcional: herramientas de navegador para las páginas dinámicas. No instala ni configura nada en la máquina."
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

Cada paso del agente reenvía todo el chat. Por eso cada sesión vive en **su propio chat** y pasa el trabajo por `estado.md`; lo determinista lo hace `scripts/producto.py` (registro de fuentes, confianza, cobertura, puntaje, escenarios, trazabilidad, puertas y el paso siguiente), y cada línea de investigación tiene un presupuesto de búsquedas y lecturas. `siguiente` dice el modelo concreto y el esfuerzo de cada chat ([modelos.md](references/modelos.md)). Para el usuario, [prompts.md](references/prompts.md) tiene los textos listos para copiar.

## Reglas

1. **Evidencia o nada.** Cada afirmación clave lleva fuentes registradas con `producto.py fuente` (URL, **fecha de publicación real** o `--publicada desconocida`, tipo, línea y peldaño). La fecha en que leíste una reseña o un artículo no es su fecha de publicación. Lo que no tiene fuente va como **⚠ Sin evidencia**.
2. **Triangulación.** Un hallazgo clave necesita **3 fuentes independientes** publicadas dentro de la **ventana de vigencia** (18 meses); si es de demanda o de monetización, al menos una de tipo *medido*. En **políticas, una fuente `oficial`** (la política de la tienda o la ley, con su versión o fecha) **basta sola**. En **demanda, las descargas acumuladas son contexto**, no una señal actual (`--acumulado`). En una idea nueva se triangula el peldaño más cercano a lo directo que tenga evidencia, no la solución exacta ([evidencia.md](references/evidencia.md)).
3. **La confianza la calcula el script** con la cantidad, el tipo, la fecha y el peldaño de las fuentes, con **la misma regla de vigencia que la triangulación**: una fuente sin fecha o fuera de la ventana no cuenta para ninguna de las dos, y solo un hallazgo triangulado llega a alta. Se lee siempre junta ("confianza media · sin triangular"). Puedes bajarla con un motivo (`producto.py confianza`), nunca subirla.
4. **Abogado del diablo obligatorio.** Por cada hipótesis crítica buscas evidencia en contra ("por qué fallaría", "quién lo intentó y cerró") y la registras, también cuando no aparece nada (`--en-contra`, `--sin-contra`, `producto.py intento`). En una idea nueva: ¿no existe porque nadie la pensó o porque alguien la probó y no funcionó? En una saturada: ¿por qué los competidores no lo hicieron ya, y cuánto tardarían en copiarlo?
5. **Ni la falta de datos ni la saturación son motivo de descarte.** Una idea solo se descarta con evidencia en contra, cuando ningún peldaño muestra el problema o, con competencia, cuando no aparece ningún diferenciador viable. Nunca recomiendes descartar por la cantidad de competidores.
6. **El rival más fuerte puede no ser una app.** La matriz registra siempre cómo se resuelve hoy la necesidad sin una app así (peldaño 4: una función del sistema, una hoja de cálculo, un grupo de chat). Si un sustituto **gratuito o nativo ya la resuelve**, cada diferenciador tiene que superarlo con evidencia (un hallazgo que lo nombre), y la puerta 1 lo exige ([diferenciacion.md](references/diferenciacion.md)).
7. **Criterios de descarte antes de investigar.** Se fijan en la sesión 0 (`criterios.md`). Cambiarlos después exige `producto.py criterio --motivo`, y cada puerta lo muestra.
8. **Los números los calcula `producto.py`:** confianza, cobertura, puntaje, escenarios de ingresos, RICE, conteos de triangulación, trazabilidad y veredictos de las puertas. Tú interpretas: nunca haces cuentas por tu lado ni editas a mano los `.json` del registro.
9. **La decisión es del usuario.** Nunca corras `producto.py decidir`, aunque el pedido parezca justificarlo: entrega el comando completo y detente.
10. **Dato medido o estimación.** Toda estimación dice cómo se calculó, con qué supuestos y, si viene de un análogo, de cuál.
11. **Una sesión por chat, y al terminar te detienes**, con el traspaso en `estado.md`. Lo que no depende de otra sesión corre en paralelo; lo que depende, después. No sigas con la sesión siguiente aunque te digan "sigue": explica que en este chat cuesta varias veces más.
12. **Agnóstica y con cobertura.** La plataforma, el stack, el modelo de negocio, los mercados, los idiomas y las tiendas salen de `00-idea.md` (`producto.py objetivo`). No asumas Android, anuncios ni ningún país. Cada línea de investigación trae fuentes de cada mercado, idioma y tienda que le toca, o registra el vacío con su motivo (`producto.py vacio`); una línea no cierra con huecos sin registrar.
13. **La meta de ingresos es opcional y referencial.** Se pregunta, pero no bloquea ninguna puerta ni cuenta como riesgo, salvo que el usuario la marque como obligatoria (`criterio --clave meta_obligatoria --valor si`). La puerta 2 pide, en su lugar, al menos un modelo de monetización viable con evidencia.
14. **Privacidad y legalidad.** Citas breves o parafraseadas, sin nombres de usuario ni datos personales de quienes escriben reseñas. Respeta los términos de uso: nada de scraping que los viole ni de saltar muros de pago. Diferenciarse no es copiar: nada de marcas, textos, íconos ni diseños de la competencia.
15. **Salidas acotadas.** Nunca vuelques páginas completas al chat ni a los archivos: cada fuente se resume en 3 líneas como máximo, en su registro, y las reseñas de un CSV se leen con `producto.py resenas`. No leas `producto.py`: usa `--help` y lo que imprime.
16. **Siguiente paso siempre explícito.** Tu último paso es `producto.py siguiente`: pega su salida tal cual, como último bloque de tu respuesta y dentro de un bloque de código. En una puerta ya trae el veredicto criterio por criterio: no pidas correr `puerta` aparte. Cuando no queda nada, dice que el proceso cerró.
17. **Lo cerrado se cambia en la puerta.** Si ves que hay que cambiar algo de una sesión ya cerrada (el diferenciador principal, un hallazgo de otra línea), no lo hagas ni des un comando suelto: regístralo con `producto.py propuesta --texto "…" [--ajustar <sesión>]`. La puerta lo muestra y el usuario decide.
18. **Comandos para el usuario:** uno por paso, en un bloque de código y empezando con `cd <ruta absoluta> && ...`. Los que imprime `producto.py` ya vienen así: cópialos sin reescribirlos.
19. **Primera línea de cada sesión:** `Sesión <n> · <nombre> (<motivo>)`, por ejemplo `Sesión 1c · Demanda (Siguiente paso de estado.md)`.
20. **Español neutro** (tú, no vos) en todo lo que escribas.
21. **Git:** no hagas commit ni push salvo que el usuario lo pida. Si la carpeta del producto queda dentro de un repo público, pregunta antes de versionarla: la estrategia puede ser sensible.

## Sesiones

La columna "Modelo" es la de fábrica, con su esfuerzo; `producto.py modelos` la cambia ([modelos.md](references/modelos.md)).

| Sesión | Etapa | Lee | Hace | Entregable | En paralelo | Modelo | Termina con |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 · Idea | Descubrir | Esta página | Entrevista en una sola tanda, `producto.py nuevo`, la necesidad de fondo, el objetivo y los criterios | `00-idea.md`, `criterios.md`, `estado.md` | No | Sonnet 5.5 · medio | Las 5 líneas, listas para abrir |
| 1a · Competencia | Descubrir | [investigacion.md](references/investigacion.md) | Top 10 por tienda y mercado, matriz de competidores, **tipo de idea** e intentos anteriores | `01-investigacion/competencia.md` | Sí (1a–1e) | Sonnet 5.5 · medio | Fuentes, hallazgos, cobertura y tipo registrados |
| 1b · Voz del usuario | Descubrir | [investigacion.md](references/investigacion.md) | Reseñas de 1 a 3★ (también de un CSV del usuario), foros, redes y blogs: dolores, pedidos y quejas por competidor | `01-investigacion/voz-del-usuario.md` | Sí | Sonnet 5.5 · medio | Ídem |
| 1c · Demanda | Descubrir | [investigacion.md](references/investigacion.md) | Búsquedas, tendencia, estacionalidad y tamaño de la audiencia | `01-investigacion/demanda.md` | Sí | Sonnet 5.5 · medio | Ídem |
| 1d · Monetización | Descubrir | [investigacion.md](references/investigacion.md) | Modelos, precios, eCPM, conversión y afiliados | `01-investigacion/monetizacion.md` | Sí | Sonnet 5.5 · medio | Ídem |
| 1e · Políticas y riesgos | Descubrir | [investigacion.md](references/investigacion.md) | Políticas de las tiendas, leyes, requisitos de cuenta y riesgos técnicos | `01-investigacion/politicas.md` | Sí | Sonnet 5.5 · medio | Ídem |
| 1g · Diferenciación | Descubrir | [diferenciacion.md](references/diferenciacion.md) | Huecos por vector, ERRC, Kano, posicionamiento, diferenciadores (`D-…`) y el principal | `01-investigacion/diferenciacion.md` | Sí, apenas cierran 1a y 1b | Opus 5.5 · alto | Diferenciadores registrados |
| 1f · Síntesis | Descubrir | [puntaje.md](references/puntaje.md) y [puertas.md](references/puertas.md) | Une las 6 líneas, `triangulacion`, `cobertura` y `puntaje` | `01-sintesis.md` | No | Opus 5.5 · alto | **Puerta 1** |
| 2 · Estrategia | Validar | [estrategia.md](references/estrategia.md) | Jobs To Be Done, propuesta de valor, posicionamiento, Lean Canvas, PR/FAQ y `escenarios` | `02-estrategia.md` | Sí (con la 3) | Opus 5.5 · alto | Lista para la puerta 2 |
| 3 · Validación documental | Validar | [validacion.md](references/validacion.md) | Hipótesis críticas con evidencia a favor y en contra, veredicto e hipótesis más riesgosa | `03-validacion.md` | Sí (con la 2) | Opus 5.5 · alto | **Puerta 2**, cuando cierran la 2 y la 3 |
| 4 · PRD | Definir | [prd.md](references/prd.md) | MVP con RICE, historias, métricas HEART, eventos, monetización y checklist de políticas | `04-prd.md` | No | Opus 5.5 · alto | **Puerta 3** |

Cada sesión de investigación consulta primero `producto.py tipo` y lee también [evidencia.md](references/evidencia.md); si la idea es nueva, [analogia.md](references/analogia.md). Cada sesión se cierra con `producto.py cerrar --sesion <id>`, que comprueba que el entregable no tiene texto de plantilla y que lo mínimo está registrado. Las sesiones 5 a 10 (UX/UI, plan técnico, tienda, lanzamiento y medición) llegan en versiones siguientes; la construcción se delega a `hb-implement`, una funcionalidad del PRD a la vez citando su ID (`F-01`).

### Qué sesión te toca

- **Con un `estado.md`** ("sigue hb-product con …/estado.md"): corre primero `producto.py siguiente --carpeta <carpeta>`. Haces la sesión que nombra el pedido si `siguiente` la ofrece; si no la nombra y hay varias en paralelo, pregunta cuál. Si lo que sigue es una puerta, pega la salida (ya trae el veredicto y los comandos) y detente.
- **Sin `estado.md`:** es la sesión 0. Si `siguiente` dice que la idea está archivada, no hay nada que hacer salvo que el usuario la quiera reabrir.
- **Solo una consulta** ("cómo me diferencio de X", sin querer el proceso completo): dilo en la primera línea y ofrece empezar por la sesión 0; no investigues sin registro.

### Sesión 0 · Idea

1. Haz la entrevista en **una sola tanda**, con 8 preguntas como máximo y sin repetir lo que el pedido ya dice: problema, usuario, contexto de uso, plataformas, **mercados, idiomas y tiendas**, modelo de negocio, **presupuesto de semanas**, una **meta de ingresos al mes (opcional: solo referencia, salvo que el usuario quiera que sea obligatoria)** y lo que no debe ser.
2. Crea la carpeta: `producto.py nuevo --nombre "<nombre>" --semanas <presupuesto> --mercados <MX,ES> --idiomas <es> --tiendas <google-play,app-store|ninguna> [--meta <ingresos al mes> [--meta-obligatoria]] [--moneda <ISO>] [--carpeta <ruta>]`. No pisa nada que ya exista. El objetivo también se completa después con `producto.py objetivo`.
3. Completa `00-idea.md` con lo que dijo el usuario; lo que no dijo va en "Supuestos sin confirmar". Escribe la **necesidad de fondo**: el "trabajo" del usuario sin nombrar la solución.
4. Completa `criterios.md`. Los umbrales por defecto (17/25, 15/25 si la idea es nueva, 18 meses y 3 fuentes) se cambian ahora con `producto.py criterio`; después hará falta un motivo.
5. `producto.py cerrar --sesion 0` y pega la salida: son los carriles de la investigación, con el modelo de cada uno.

## Puertas

`producto.py puerta --n <1|2|3>` evalúa cada criterio con el juego que corresponde al tipo de idea; el usuario decide con `producto.py decidir --puerta <n> --seguir | --ajustar <sesión> | --descartar "<motivo>"`. La cantidad de competidores **no** es un criterio. El detalle, cómo cambiar un criterio y qué pasa al ajustar o descartar están en [puertas.md](references/puertas.md).

| Puerta | Idea existente o variante | Idea nueva |
| --- | --- | --- |
| P1 · Oportunidad | Puntaje de 17/25 o más · demanda con confianza media o alta · al menos 1 diferenciador viable (con sus hallazgos triangulados y, si hay un sustituto gratuito o nativo que resuelve la necesidad, **que lo supere**) · **los hallazgos del diferenciador principal triangulados** · riesgo de políticas distinto de 1, o con mitigación escrita (**1 si una tienda objetivo nombra o rechaza la categoría**) | Puntaje de 15/25 o más · el problema documentado con 3 fuentes de peldaño 4 o 5 · al menos 2 análogos con tracción · sin evidencia de que se probó y fracasó por falta de demanda · un diferenciador viable que supere al sustituto gratuito o nativo, si lo hay · el mismo criterio de riesgo |
| P2 · Viabilidad | **Al menos un modelo de monetización viable con evidencia** · ninguna hipótesis crítica refutada · el diferenciador principal sobrevive al abogado del diablo | Al menos un modelo de monetización viable con evidencia (por analogía) · ninguna refutada · la hipótesis más riesgosa, identificada y medible |
| P3 · Alcance | MVP dentro del presupuesto · el diferenciador principal en el MVP · 100 % de trazabilidad · métricas HEART definidas · checklist de políticas sin bloqueos | Lo mismo, y el MVP pone a prueba la hipótesis más riesgosa con una métrica y un umbral |

La meta de ingresos se muestra en la puerta 2 solo como referencia; si el usuario la marcó como obligatoria, se suma como criterio. Cada puerta muestra además los avisos que no se pueden pasar por alto (confianza global baja, huecos de cobertura, vacíos por límite de las herramientas) y las propuestas de las sesiones. Descartar archiva la idea en `archivo/` con su motivo: queda como aprendizaje y `producto.py reabrir` la recupera.

**Reporte y tablero.** Cada decisión de una puerta y cada archivo regeneran `reporte.html`, el reporte de la idea para leer sin terminal: resumen ejecutivo arriba y tarjetas debajo (puntaje, puertas, diferenciadores, hallazgos, competidores, cobertura, escenarios, hipótesis y costo). `producto.py reporte` lo genera a mano (`--idea <nombre>` para una archivada) y `producto.py tablero --raiz <carpeta>` arma un `index.html` con todas las ideas que encuentre bajo esa carpeta, en curso y archivadas, con su estado y el enlace a su reporte. Al terminar una puerta, nombra la ruta del reporte.

## Paralelismo

- **1a–1e a la vez.** Cada línea escribe solo su `.md` y su `.json` en `01-investigacion/`, y `producto.py` consolida: no hay dos sesiones escribiendo el mismo archivo. Las notas de una sesión en paralelo van en "Para la síntesis" de su archivo, no en `estado.md`.
- **1g** arranca apenas cierran 1a y 1b, sin esperar a 1c–1e. **2 y 3** van juntas; la puerta 2 espera a las dos.
- **Tipo de idea:** 1a lo registra apenas lo sabe (`producto.py tipo`). Las demás líneas lo consultan antes de buscar y otra vez antes de cerrar; si resulta nueva, trabajan por analogía sin repetir lo hecho.
- **Con subagentes** (si tu herramienta los tiene y el usuario lo pide): un chat orquestador lanza un subagente por carril con el texto que imprime `siguiente` y el modelo de esa sesión; cada subagente es una sesión completa y devuelve 3 líneas. El orquestador no investiga: espera, anota el uso de cada subagente con `producto.py consumo` si la herramienta lo muestra (o el total con `--sesion orquestador --incluye …`), corre `siguiente` y lanza lo que se abre. **Sin subagentes**, `siguiente` da un chat por carril para abrirlos a la vez.
- **Presupuesto por línea:** 15 búsquedas y 10 lecturas (20 y 12 si la idea es nueva). Al llegar al 80 %, dilo y cierra con lo que tienes; `producto.py fuente` avisa con las lecturas.
- **Fuentes difíciles:** las reseñas de las tiendas, los foros, Reddit, TikTok y YouTube suelen ser páginas dinámicas o bloqueadas. Si tienes herramientas de navegador, úsalas para esas; si el usuario aporta un CSV de reseñas, regístralo con `fuente --archivo` y léelo con `resenas`. Si aun así no se puede, registra el vacío con `vacio --motivo herramienta`: es un límite de las herramientas, no de la evidencia, y no se resuelve reabriendo la línea con las mismas herramientas ([investigacion.md](references/investigacion.md)).

## Archivos del producto

```text
<carpeta>/                     por defecto ./product/ (o la línea `Carpeta:` de `## Producto` en AGENTS.md)
├── estado.md                  traspaso entre sesiones (los bloques marcados los reescribe producto.py)
├── criterios.md               criterios de descarte (sesión 0)
├── 00-idea.md                 incluye la necesidad de fondo
├── 01-investigacion/          una línea por archivo: <línea>.md y <línea>.json (fuentes, hallazgos, matriz)
├── 01-sintesis.md · 02-estrategia.md · 03-validacion.md · 04-prd.md
├── escenarios.json            supuestos de los escenarios de ingresos (sesión 2)
├── producto.json              registro del script: tipo, criterios, objetivo, modelos, sesiones, puntaje, escenarios, propuestas y consumo
├── decisiones.json            decisiones de las puertas, con fecha y criterios
├── reporte.html               el reporte de la idea (lo regenera producto.py; no se edita)
└── archivo/                   ideas descartadas o archivadas, con su motivo
```

Si el proyecto todavía no existe, la carpeta vive sola; cuando se crea el repo, se mueve a su raíz y `hb-setup` la anota en `AGENTS.md`.

## Herramientas

`python3 -I <carpeta-de-la-skill>/scripts/producto.py <comando> [--carpeta <carpeta>]`, cada uno con `--help`. Lo que imprime cada comando termina con el paso siguiente.

| Comando | Qué hace |
| --- | --- |
| `nuevo` | Crea la estructura desde las plantillas y escribe `estado.md` |
| `criterio` | Muestra los criterios o cambia uno (después de la sesión 0, con `--motivo`) |
| `objetivo` | Muestra o registra los mercados, idiomas y tiendas (después de la sesión 0, con `--motivo`) |
| `modelos` | El modelo y el esfuerzo de cada sesión; `--intermedio`, `--alto` y `--herramienta` los cambian |
| `tipo` | Sin opciones, muestra el tipo de idea y el presupuesto; con `--existente`, `--variante` o `--nueva` y `--motivo`, lo registra |
| `fuente` | Registra una fuente y devuelve su ID (`S-COM-1`): `--linea --url\|--archivo --publicada <fecha real\|desconocida> --tipo --peldano --resumen [--autor] [--mercados] [--idiomas] [--tiendas] [--version] [--acumulado]`; avisa si la publicación coincide con la consulta |
| `resenas` | Muestra las reseñas de un CSV exportado (de 1 a 3★ por defecto, recientes primero, sin columnas de autor) |
| `vacio` · `cobertura` | Registra un mercado, idioma o tienda que quedó sin fuentes, con su motivo · lista la cobertura de cada línea |
| `hallazgo` | Registra un hallazgo (`H-DEM-1`) y calcula su confianza: `--linea --texto --fuentes [--en-contra] [--sin-contra] [--critico] [--competidores] [--bloquea <tienda>]` |
| `confianza` | Baja la confianza de un hallazgo, con su motivo |
| `competidor` · `matriz` | Registra o completa una fila de la matriz (`C-1`); un sustituto lleva `--peldano 4 --sustituto nativo\|gratuito\|pago --resuelve si\|parcial\|no` · la muestra con los hallazgos enlazados a cada competidor |
| `intento` | Registra la búsqueda de intentos anteriores de la misma idea y su resultado |
| `diferenciador` · `principal` | Registra un diferenciador (`D-1`) y dice si es viable, viable con confianza baja o no viable: `--vector --texto --hallazgos --se-ve --copiable --motivo --semanas [--principal]` · elige el principal. Los dos, solo con la sesión 1g abierta |
| `propuesta` | Deja un cambio a una sesión cerrada como propuesta para la puerta siguiente: `--texto [--ajustar <sesión>]` |
| `anular` | Anula una fuente, un hallazgo, un competidor o un diferenciador: deja de contar, sin borrarse |
| `triangulacion` | Lista los hallazgos clave y lo que le falta a cada uno |
| `puntaje` | Total, confianza global y comparación con la puerta 1: `--valores d,m,f,r,x [--mitigacion]` |
| `escenarios` | Casos pesimista, base y optimista, y usuarios activos diarios para la meta: `--entrada escenarios.json` |
| `validacion` · `trazabilidad` | Revisan las tablas de `03-validacion.md` y de `04-prd.md` (esta calcula el RICE) |
| `cerrar` | Cierra una sesión si su entregable está completo: `--sesion <id>` |
| `puerta` | Veredicto criterio por criterio: `--n <1\|2\|3>` (el mismo que trae `siguiente` en una puerta) |
| `decidir` | **Solo lo corre el usuario.** Registra la decisión con fecha; `--reabrir` la deshace |
| `siguiente` · `estado` | El paso siguiente o los carriles, con el texto para cada chat y el modelo sugerido · el resumen |
| `archivar` · `reabrir` | Mueve la idea a `archivo/` (no borra nada) o la recupera |
| `reporte` · `tablero` | Genera `reporte.html` de la idea (`--idea` para una archivada) · genera `index.html` con todas las ideas bajo `--raiz <carpeta>` |
| `consumo` | Anota el costo de una sesión o del orquestador (opcional): `--sesion --costo\|--creditos\|--tokens [--incluye]` |

Otras skills, por intención y sin depender de sus archivos: `hb-setup` (anota `## Producto` en `AGENTS.md`), `hb-implement` (construye cada `F-…`), `hb-review`, `hb-performance` (si el diferenciador es de rendimiento), `hb-commit`, `hb-release`, `play-policy-insights` y `hb-coach` (para aprender un concepto: RICE, Kano o HEART).

## Checklist

- [ ] Primera línea con la sesión y el motivo; una sesión por chat; la última salida es la de `producto.py siguiente`, en un bloque de código.
- [ ] Criterios fijados en la sesión 0; ningún cambio posterior sin `--motivo`.
- [ ] Cada fuente registrada con su fecha, su tipo, su peldaño y la cobertura que aporta, y resumida en 3 líneas; ninguna página ni CSV volcados; ninguna cita con nombre de usuario.
- [ ] Hallazgos clave triangulados o presentados con su confianza real ("confianza media · sin triangular"); búsqueda de evidencia en contra registrada en cada uno, también cuando no apareció nada.
- [ ] Cada mercado, idioma y tienda del objetivo con fuentes o con su vacío registrado; ningún vacío de herramienta presentado como falta de evidencia, ni resuelto proponiendo reabrir la línea con las mismas herramientas.
- [ ] Tipo de idea registrado por 1a y respetado por las demás líneas; en una idea nueva, cada hallazgo con su peldaño y la búsqueda de intentos anteriores hecha.
- [ ] Con competencia: matriz completa, con el sustituto (peldaño 4) evaluado, y cada diferenciador con evidencia, dónde se ve, copiabilidad, semanas y cómo supera al sustituto gratuito o nativo. Uno viable con confianza baja no se presenta como viable. Si ninguno es viable, se dijo sin maquillarlo.
- [ ] Políticas leídas en su fuente oficial; si una tienda objetivo nombra o rechaza la categoría, el hallazgo lleva `--bloquea` y el riesgo es 1. Demanda puntuada con señales actuales, no con descargas acumuladas.
- [ ] La meta de ingresos, si existe, presentada como referencia (salvo que el usuario la marcó como obligatoria); nunca como riesgo ni como motivo de descarte.
- [ ] Nada de una sesión cerrada cambiado con un comando suelto: va como `propuesta` a la puerta.
- [ ] Ninguna recomendación de descartar por la cantidad de competidores ni por falta de datos.
- [ ] Ningún número calculado a mano: confianza, puntaje, escenarios, RICE y veredictos salen de `producto.py`.
- [ ] Cada estimación dice cómo se calculó; los escenarios llevan sus rótulos (*estimación*, *por analogía*).
- [ ] PRD con trazabilidad al 100 % en el MVP, el diferenciador principal dentro y, en una idea nueva, la hipótesis más riesgosa con su métrica y su umbral.
- [ ] Cada puerta decidida por el usuario: el agente nunca corrió `decidir`.
- [ ] Ningún entregable con texto de plantilla; nada de marcas ni contenido copiado de la competencia; sin commit ni push no pedidos.
