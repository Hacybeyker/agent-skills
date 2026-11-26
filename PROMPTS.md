# Prompts listos para copiar

Las skills se activan por intención: no hace falta nombrarlas. Estos prompts sirven cuando no sabes por dónde empezar o quieres pedir algo puntual sin rodeos. Lo que va entre `<>` se completa; si tu herramienta tiene comandos, `/hb-<skill>` también las activa.

Una regla para todas: **un pedido por chat**. Al terminar una tarea, abre otro chat para la siguiente: cada paso del agente reenvía todo el chat, y uno largo cuesta varias veces más.

## hb-setup · preparar el proyecto

| Caso | Prompt |
| --- | --- |
| Proyecto sin `AGENTS.md` | `Usa hb-setup: configura este proyecto para los agentes.` |
| Ya tiene uno, pasarlo al estándar | `Usa hb-setup: migra el AGENTS.md al estándar sin perder lo propio del proyecto.` |
| Solo refrescar el stack o los comandos | `Usa hb-setup: actualiza la sección Stack (y Comandos) del AGENTS.md con lo que tiene el proyecto hoy.` |
| Sin subir el contexto de IA al repo | `Usa hb-setup: configura este proyecto para los agentes con el contexto fuera del repo, en <carpeta externa>.` |
| Documentar la estructura (unidades y repos vecinos) | `Usa hb-setup: documenta en ## Estructura del AGENTS.md las unidades del proyecto, los repos vecinos (<rutas>) y cómo pasar <dependencia> a fuente y volver.` |
| Decidir una modernización | `Agrega a ## Modernización del AGENTS.md: <qué se migra, con qué alcance: "las pantallas nuevas van en Compose">.` |

El `AGENTS.md` describe el proyecto tal como es (también si usa Views, MVP o RxJava). Nadie migra nada hasta que lo anotes en `## Modernización`.

## hb-implement · features, bugs, mejoras y refactors

| Caso | Prompt |
| --- | --- |
| Feature | `Implementa la feature <nombre>: <qué hace, para quién, criterios de aceptación si los tienes>.` |
| Bug | `Corrige el bug: <qué pasa, cómo reproducirlo, qué debería pasar>.` |
| Bug complejo, en varias sesiones | `Corrige el bug: <qué pasa>. Lleva la bitácora y muéstrame el plan antes de tocar código.` (para seguir otro día: `Sigue el bug <slug> desde su bitácora.`) |
| Cambio en varios repos | `Implementa <tarea> en este repo y en <../repo-relacionado>; un solo reporte con los dos.` |
| Issue de GitHub | `Resuelve el issue #<n>.` |
| Mejora acotada | `Mejora <qué> en <dónde>: <qué debe cambiar>. No toques nada más.` |
| Refactor | `Refactoriza <clase o módulo>: <objetivo>. Sin cambiar el comportamiento; los tests existentes deben seguir en verde.` |
| Solo el plan, sin tocar código | `Con hb-implement, dame solo el plan para <tarea>: archivos por capa, patrones y tests. No implementes todavía.` |
| Seguir un plan aprobado | `Apruebo el plan. Implementa.` |
| Con el alcance ya aprobado, sin esperar confirmación | `Con hb-implement, implementa <bloque> según <documento de alcance>. El alcance está aprobado: no esperes confirmación y anota tus decisiones en <archivo>.` |
| Construir por bloques con un subagente cada uno | Primera línea, para ti: `Modelo · Esfuerzo: <p. ej. intermedio · medio>`. Luego: `Ejecuta <carpeta>/PLAN.md como orquestador: lanza un subagente de hb-implement por bloque con <carpeta>/brief-comun.md, lee la lógica de cada bloque, corre el DoD, commitea y sigue con el siguiente.` (la receta está en `references/orquestacion.md` de hb-implement) |

## hb-review · code review

| Caso | Prompt |
| --- | --- |
| Lo que tengo sin commitear | `Revisa el código.` |
| Una rama | `Revisa la rama <nombre> contra <main>.` |
| Un PR | `Revisa el PR #<n>.` |
| Archivos concretos | `Revisa <ruta/Archivo.kt> y <ruta/Otro.kt>.` |
| Rápida, sin correr el DoD | `Haz una revisión rápida, solo de lectura, de <qué>.` |
| Un bloque delegado a un subagente (orquestadores) | `Con hb-review en modo rápido, revisa el diff del bloque <x> contra <documento de alcance>. No corras el DoD.` |
| Solo seguridad | `Revisa <qué> solo con el checklist de seguridad del perfil.` |

## hb-commit · commits, push y PRs

| Caso | Prompt |
| --- | --- |
| Solo el mensaje | `Dame el mensaje del commit.` |
| Commit (si `AGENTS.md` lo permite) | `Haz commit.` |
| Varios commits lógicos | `Divide los cambios en commits por tema y dame los mensajes.` |
| Push y PR | `Sube los cambios y crea el PR.` |
| Limpieza | `Limpia las ramas ya mergeadas.` |

## hb-release · versiones y changelog

| Caso | Prompt |
| --- | --- |
| Cortar una versión | `Prepara el release.` → propone la versión según los cambios y pide confirmación |
| Versión fija | `Prepara el release <1.4.0>.` |
| Solo el changelog | `Genera la entrada del changelog para los cambios desde el último tag, sin subir la versión.` |
| Notas de tienda | `Escribe las notas de la versión <1.4.0> para la tienda, en <idiomas>.` |

## hb-product · de la idea al PRD

Tiene varias sesiones, y las de investigación corren en paralelo: su guía completa está en [skills/hb-product/references/prompts.md](skills/hb-product/references/prompts.md). **Después del primer pedido, solo pegas lo que imprime `producto.py siguiente`**: el texto de cada chat (uno por sesión, con el modelo y el esfuerzo que conviene) o el comando completo de la terminal; en una puerta, ya trae el veredicto. La skill trabaja con evidencia pública: no descarta una idea por tener muchos competidores ni por no tener datos, y en cada puerta decides tú.

| Caso | Prompt |
| --- | --- |
| Idea nueva (sesión 0) | `Usa hb-product: tengo una idea de app. <la idea: qué problema resuelve, para quién, plataformas, países, idiomas, tiendas, cómo gana dinero y semanas disponibles; si quieres, una meta de ingresos al mes>. No hagas commit ni push.` |
| Mercado con muchas apps | `Usa hb-product: quiero hacer <tipo de app> aunque ya hay muchas. Quiero saber cómo diferenciarme antes de construirla: <para quién, plataformas, países, idiomas, tiendas y semanas>. No hagas commit ni push.` |
| Idea que no existe todavía | `Usa hb-product: tengo una idea de app que no encontré en ninguna tienda: <la idea y cómo se resuelve hoy el problema>. <plataformas, países, idiomas, tiendas y semanas>. No hagas commit ni push.` |
| Abrir un carril o retomar | `Sigue hb-product con <ruta absoluta>/product/estado.md. No hagas commit ni push.` (para un carril, el texto que imprime `siguiente`, que nombra la sesión) |
| Toda la idea desde un solo chat (modo orquestado) | Abre el chat con `cd <raíz> && claude --model claude-haiku-5-5 --effort low` y pega `Usa hb-product en modo orquestado: tengo una idea de app. <la idea, como en la sesión 0>. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.` (para retomar: `Sigue hb-product con <ruta absoluta>/product/estado.md en modo orquestado. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.`). Lanza un subagente por sesión con su modelo, en primer plano, espera a que terminen todos y se detiene en cada puerta con el recordatorio de `/cost` arriba: corre `/cost` y el comando de `consumo` que te da, después `decidir` en tu terminal, y escribe `Continúa.` |
| Toda la idea sin preguntas ni paradas (modo autónomo) | Abre el chat como en el modo orquestado y pega `Usa hb-product en modo autónomo: <la idea en tus palabras, o "la descripción está en <ruta absoluta del archivo>">. Sin preguntas: lo que falte va a Supuestos sin confirmar. En cada puerta decide con decidir --automatico, salvo que siguiente --json diga detener. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.` Aplica la recomendación de la skill en cada puerta (nunca en contra) y la marca como decisión automática en el reporte y el tablero; revísalas al final y reabre con `decidir --puerta <n> --reabrir` la que no compartas |
| Reseñas que el agente no puede leer | `Te paso reseñas exportadas de <app> en <tienda>: <ruta absoluta del CSV>. Regístralas como fuente y léelas con producto.py resenas. No hagas commit ni push.` (en el chat de la sesión 1b) |
| Construir una funcionalidad del PRD | `Implementa F-01 de <ruta absoluta>/product/04-prd.md.` (lo hace `hb-implement`) |

Las puertas se deciden en la terminal con el comando que imprime `producto.py siguiente` (`decidir --puerta <n> --seguir`, `--ajustar <sesión>` o `--descartar "<motivo>"`): el agente nunca lo corre (salvo `decidir --automatico` en el modo autónomo que pediste). La meta de ingresos es opcional y solo una referencia, salvo que digas que es obligatoria. El modelo de cada chat se cambia con `producto.py modelos` y el costo se anota, si quieres, con `producto.py consumo`. Descartar archiva la idea con su motivo y `producto.py reabrir` la recupera. Cada decisión regenera `reporte.html`, el reporte de la idea para leer en el navegador, y `producto.py tablero --raiz <carpeta>` reúne todas tus ideas en un `index.html`. La carpeta por defecto es `product/`; para cambiarla, una sección `## Producto` en `AGENTS.md` con la línea `Carpeta: <ruta>`.

## hb-performance · rendimiento en Android

Tiene varias sesiones y comandos de terminal: su guía completa está en [skills/hb-performance/references/prompts.md](skills/hb-performance/references/prompts.md). Copia solo el bloque de cada caso; la explicación va fuera. El mismo texto sirve la primera vez y las siguientes: la skill elige la sesión según el estado del proyecto (sin setup, lo hace; con setup, arma la ficha y el plan) y el agente lo dice en su primera línea.

**Después del primer pedido, solo pegas lo que imprime `perf.py siguiente`**: cada paso dice si va en la terminal o en un chat nuevo, con el comando completo o el texto para pegar; no hace falta ningún comando que no salga de la skill. Cada chat de hb-performance se abre nuevo, desde la terminal y en la raíz del proyecto, con el modelo y el esfuerzo de su sesión. Para empezar (modelo intermedio, esfuerzo medio): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después, `perf.py siguiente` imprime el comando de cada sesión y el texto para pegar.

**Analizar una pantalla o un flujo** (la primera vez en el proyecto, o con el setup listo). La primera vez, este pedido hace el setup (sesión 0) y guarda tu flujo, tal cual lo escribes, para la sesión 1: por eso te pide el flujo aunque todavía no lo mida.

```text
Usa hb-performance: quiero analizar el rendimiento de <pantalla o flujo, y qué se nota>. Dispositivo <serial>. No hagas commit ni push.
```

Para que la sesión 1 no se trabe, puedes pedir antes que la skill mejore tu pedido (sesión `0 · pedido`: sin código ni dispositivo, de 0,1 a 0,3 USD):

```text
Usa hb-performance: mejora este pedido: <el flujo en tus palabras: de dónde a dónde, qué tocas, qué debe verse y qué se nota>. No hagas commit ni push.
```

**Solo el diagnóstico, sin cambiar código** (triage):

```text
Usa hb-performance en modo triage: diagnostica <flujo> con 3 corridas, sin control ni mejoras. Dispositivo <serial>. No hagas commit ni push.
```

**Toda la investigación desde un solo chat** (modo orquestado, con una herramienta que tenga subagentes, como Claude Code). El chat es el orquestador (modelo económico, esfuerzo bajo: `cd <raíz> && claude --model claude-haiku-5-5 --effort low`): lanza cada sesión como un subagente con el modelo de su nivel, corre las capturas con recorrido automático y se detiene solo donde haces falta, diciéndote qué hacer y dónde. Al terminar, te da el comando `perf.py consumo` del total.

```text
Usa hb-performance en modo orquestado: quiero analizar el rendimiento de <pantalla o flujo, y qué se nota>. Dispositivo <serial>. No hagas commit ni push.
```

Cuando se detiene en la decisión de las mejoras, corre en tu terminal el `perf.py decidir` que te da y después escribe en el mismo chat:

```text
Continúa. No hagas commit ni push.
```

**Retomar** donde quedó, en un chat nuevo:

```text
Sigue hb-performance con <ruta absoluta>/estado.md. No hagas commit ni push.
```

Para retomar en modo orquestado, el mismo texto con "en modo orquestado" antes del punto.

**Requisitos y setup.** La skill no instala ni configura nada en tu máquina: `perf.py setup --estado` lista en solo lectura las herramientas que hacen falta (Python 3.8 o superior, git, `adb` y `trace_processor`; según el caso, Java 17 o superior; opcionales, `ffmpeg` para unir y rotular el video de la prueba y `scrcpy` para grabarlo sin cortes) y dice cuál falta. El setup de medición lo maneja la skill: detecta si está versionado, guardado en un parche o no existe, lo repone antes de medir (`setup --reponer`, que `siguiente` da como primer paso) y lo quita al cerrar, comprobando antes que el parche es de ese repo; no hace falta aplicar ningún parche a mano. Y nunca edita un módulo que la app consume compilado: le pregunta a Gradle y te dice qué cambiar.

La corrida de prueba deja un video de evidencia con rótulos que distinguen tres cosas: el video (toda la prueba), la traza (lo que registra Perfetto) y la métrica (solo lo rotulado "Medición", de una marca a otra). Las decisiones quedan con la fecha y la hora, y `perf.py decidir --reabrir <id>` vuelve una mejora a propuesta si la decisión no fue tuya. Una investigación en pausa que no vas a retomar se archiva con `perf.py archivar` (no borra nada), y así deja de impedir que se actualice el setup. Si instalaste la skill con la CLI `skills`, actualízala con `pnpm dlx skills update -g`, no copiando la carpeta a mano.

El diagnóstico y el cierre dejan cada reporte en dos versiones con el mismo diseño: `-dev` (técnico) y `-gerencia` (en palabras, para un equipo no técnico). Con dos o más investigaciones con reporte, `perf.py estado` ofrece además uno solo de gerencia para todas (`reporte --gerencia-unificado --todas`). Los comandos y los textos para pegar van siempre en un bloque de código: el texto confiable es el que imprime `perf.py siguiente`. El cierre termina con un solo comando, `perf.py cerrar`, que quita los cambios temporales con su parche (de un archivo que también tiene una mejora, solo las marcas, con el parche de marcas vigente) y después da el DoD (`--dod` lo corre). Con escenarios o una línea base rehecha, el orden lo da `siguiente`: nunca se mide después sin las mejoras instaladas y probadas. El reporte final presenta cada mejora como una decisión: qué gana el usuario, qué cuesta y en qué condición se cumple. Anotar el costo es opcional: `perf.py siguiente` imprime el comando ya completo por cada sesión, con la opción de tu herramienta (`--costo` en USD con Claude Code, o `--desde-transcript auto` sin copiar nada; `--creditos` con GitHub Copilot CLI).

## hb-coach · aprender un tema

Sirve para cualquier tema: software (su punto fuerte) y también estadística, idiomas, finanzas, diseño o una entrevista. Dentro de un proyecto guarda el curso en `aprendizaje/`, fuera de git; sin proyecto, te pregunta dónde (por ejemplo, `~/aprendizaje`).

| Caso | Prompt |
| --- | --- |
| Curso nuevo | `Quiero aprender <tema>. Parto de <lo que ya sé>, tengo <tiempo por semana> y mi objetivo es <qué quiero poder hacer>.` |
| Curso nuevo sin proyecto | `Quiero aprender <tema> (no es para este proyecto). Guárdalo en ~/aprendizaje.` |
| Seguir el curso | `Sigamos con mi plan de <tema>.` |
| Seguir una lección a medias | `Sigamos con la lección <id> de <tema>.` |
| Duda rápida mientras trabajas | `Explícame <concepto o error>: <contexto en una línea>. Solo la duda, sin plan.` |
| Repasar lo que toca | `Repasemos <tema>.` |
| Examen de módulo | `Hazme el examen del módulo <n> de <tema>.` |
| Ver el progreso | `¿Cómo voy con <tema>?` |
| Ajustar el método | `Ajusta el plan de <tema>: <qué cambiar: ritmo, profundidad, más práctica>.` |
| Curso creado con la 3.0 | `Migra mi aprendizaje de <tema> al formato nuevo de hb-coach.` |

El cuaderno (`aprendizaje/cuaderno.html`) es el aula: el coach escribe ahí cada bloque de la lección (teoría, reto y preguntas) y su corrección, y en la terminal solo te dice qué leer, qué hacer y qué enviarle; la página se actualiza sola. También tiene la ruta con sus exámenes, tu progreso con el calendario de repasos y un «Repaso de hoy» con tarjetas.

## hb-stack-mobile-kotlin · el perfil

No se invoca: lo cargan `hb-implement` y `hb-review` según el `AGENTS.md`. Si quieres consultarlo: `Según el perfil hb-stack-mobile-kotlin, ¿cómo debería <diseñar X / estructurar Y>? Solo explica, no implementes.`
