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

## hb-review · code review

| Caso | Prompt |
| --- | --- |
| Lo que tengo sin commitear | `Revisa el código.` |
| Una rama | `Revisa la rama <nombre> contra <main>.` |
| Un PR | `Revisa el PR #<n>.` |
| Archivos concretos | `Revisa <ruta/Archivo.kt> y <ruta/Otro.kt>.` |
| Rápida, sin correr el DoD | `Haz una revisión rápida, solo de lectura, de <qué>.` |
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

Tiene varias sesiones y comandos de terminal: su guía completa está en [skills/hb-performance/references/prompts.md](skills/hb-performance/references/prompts.md). Para empezar:

| Caso | Prompt |
| --- | --- |
| Primera vez en el proyecto | `Usa hb-performance: quiero analizar el rendimiento de <pantalla o flujo, y qué se nota>. Dispositivo <serial>.` |
| Retomar | `Sigue hb-performance con <ruta absoluta>/estado.md` |

## hb-coach · aprender un tema

| Caso | Prompt |
| --- | --- |
| Plan de estudio | `Quiero aprender <tema>. Parto de <lo que ya sé>, tengo <tiempo por semana> y mi objetivo es <qué quiero poder hacer>.` |
| Seguir el plan | `Sigamos con mi plan de <tema>.` |
| Duda rápida mientras trabajas | `Explícame <concepto o error>: <contexto en una línea>. Solo la duda, sin plan.` |
| Evaluarte | `Evalúame sobre <tema o lección>.` |
| Ver el progreso | `¿Cómo voy con <tema>?` |
| Ajustar el método | `Ajusta el plan de <tema>: <qué cambiar: ritmo, profundidad, más práctica>.` |

## hb-stack-mobile-kotlin · el perfil

No se invoca: lo cargan `hb-implement` y `hb-review` según el `AGENTS.md`. Si quieres consultarlo: `Según el perfil hb-stack-mobile-kotlin, ¿cómo debería <diseñar X / estructurar Y>? Solo explica, no implementes.`
