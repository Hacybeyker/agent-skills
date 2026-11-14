# Prompts listos para copiar

Las skills se activan por intención: no hace falta nombrarlas. Estos prompts sirven cuando no sabes por dónde empezar o quieres pedir algo puntual sin rodeos. Lo que va entre `<>` se completa; si tu herramienta tiene comandos, `/hb-<skill>` también las activa.

Una regla para todas: **un pedido por chat**. Al terminar una tarea, abre otro chat para la siguiente: cada paso del agente reenvía todo el chat, y uno largo cuesta varias veces más.

## hb-setup · preparar el proyecto

| Caso | Prompt |
| --- | --- |
| Proyecto sin `AGENTS.md` | `Usa hb-setup: configura este proyecto para los agentes.` |
| Ya tiene uno, pasarlo al estándar | `Usa hb-setup: migra el AGENTS.md al estándar sin perder lo propio del proyecto.` |
| Solo refrescar el stack o los comandos | `Usa hb-setup: actualiza la sección Stack (y Comandos) del AGENTS.md con lo que tiene el proyecto hoy.` |
| Decidir una modernización | `Agrega a ## Modernización del AGENTS.md: <qué se migra, con qué alcance: "las pantallas nuevas van en Compose">.` |

El `AGENTS.md` describe el proyecto tal como es (también si usa Views, MVP o RxJava). Nadie migra nada hasta que lo anotes en `## Modernización`.

## hb-implement · features, bugs, mejoras y refactors

| Caso | Prompt |
| --- | --- |
| Feature | `Implementa la feature <nombre>: <qué hace, para quién, criterios de aceptación si los tienes>.` |
| Bug | `Corrige el bug: <qué pasa, cómo reproducirlo, qué debería pasar>.` |
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

## hb-performance · rendimiento en Android

Tiene varias sesiones y comandos de terminal: su guía completa está en [skills/hb-performance/references/prompts.md](skills/hb-performance/references/prompts.md). Copia solo el bloque de cada caso; la explicación va fuera. El mismo texto sirve la primera vez y las siguientes: la skill elige la sesión según el estado del proyecto (sin setup, lo hace; con setup, arma la ficha y el plan) y el agente lo dice en su primera línea.

Cada chat de hb-performance se abre nuevo, desde la terminal y en la raíz del proyecto, con el modelo y el esfuerzo de su sesión. Para empezar (modelo intermedio, esfuerzo medio): `cd <raíz> && claude --model claude-sonnet-5-5 --effort medium` en Claude Code, o `cd <raíz> && copilot --model claude-sonnet-5.5 --effort medium` en GitHub Copilot CLI. Después, `perf.py siguiente` imprime el comando de cada sesión y el texto para pegar.

**Analizar una pantalla o un flujo** (la primera vez en el proyecto, o con el setup listo):

```text
Usa hb-performance: quiero analizar el rendimiento de <pantalla o flujo, y qué se nota>. Dispositivo <serial>. No hagas commit ni push.
```

**Solo el diagnóstico, sin cambiar código** (triage):

```text
Usa hb-performance en modo triage: diagnostica <flujo> con 3 corridas, sin control ni mejoras. Dispositivo <serial>. No hagas commit ni push.
```

**Retomar** donde quedó, en un chat nuevo:

```text
Sigue hb-performance con <ruta absoluta>/estado.md. No hagas commit ni push.
```

El diagnóstico y el cierre dejan cada reporte en dos versiones: `-dev` (técnico) y `-gerencia` (una página en palabras, para un equipo no técnico). Anotar el costo es opcional: `perf.py siguiente` imprime el comando ya completo por cada sesión.

## hb-coach · aprender un tema

Sirve para cualquier tema: software (su punto fuerte) y también estadística, idiomas, finanzas, diseño o una entrevista. Dentro de un proyecto guarda el curso en `aprendizaje/`, fuera de git; sin proyecto, te pregunta dónde (por ejemplo, `~/aprendizaje`).

| Caso | Prompt |
| --- | --- |
| Curso nuevo | `Quiero aprender <tema>. Parto de <lo que ya sé>, tengo <tiempo por semana> y mi objetivo es <qué quiero poder hacer>.` |
| Curso nuevo sin proyecto | `Quiero aprender <tema> (no es para este proyecto). Guárdalo en ~/aprendizaje.` |
| Seguir el curso | `Sigamos con mi plan de <tema>.` |
| Duda rápida mientras trabajas | `Explícame <concepto o error>: <contexto en una línea>. Solo la duda, sin plan.` |
| Repasar lo que toca | `Repasemos <tema>.` |
| Examen de módulo | `Hazme el examen del módulo <n> de <tema>.` |
| Ver el progreso | `¿Cómo voy con <tema>?` |
| Ajustar el método | `Ajusta el plan de <tema>: <qué cambiar: ritmo, profundidad, más práctica>.` |
| Curso creado con la 3.0 | `Migra mi aprendizaje de <tema> al formato nuevo de hb-coach.` |

El cuaderno (`aprendizaje/cuaderno.html`) tiene la ruta con sus exámenes, cada lección con sus retos, tu progreso con el calendario de repasos y un «Repaso de hoy» con tarjetas.

## hb-stack-mobile-kotlin · el perfil

No se invoca: lo cargan `hb-implement` y `hb-review` según el `AGENTS.md`. Si quieres consultarlo: `Según el perfil hb-stack-mobile-kotlin, ¿cómo debería <diseñar X / estructurar Y>? Solo explica, no implementes.`
