# Espacio de aprendizaje

Esta carpeta la gestiona el **Software Coach** (creada el {{FECHA}}). Es tu material de estudio personal y no se sube a git.

## Qué hay aquí

| Ruta | Contenido |
|---|---|
| `cuaderno.html` | Tu cuaderno: ábrelo en el navegador. Muestra progreso, lecciones, diagramas, glosario y dudas. |
| `METODO.md` | El acuerdo de método: cómo quieres que el coach enseñe y corrija. Se puede cambiar cuando quieras. |
| `<tema>/PLAN.md` | Plan de estudio del tema, con checkboxes de progreso, huecos pendientes y bitácora de sesiones. |
| `<tema>/lecciones/` | Una nota por lección, escrita durante la sesión: bloques 📖 teoría, 🛠 práctica y ❓ preguntas, con diagramas y ejemplos. |
| `<tema>/GLOSARIO.md` | Conceptos del tema con su definición. |
| `<tema>/DUDAS.md` | Dudas que resolviste mientras implementabas. |

## Cómo pedirle cosas al coach

- «Quiero aprender *tema*»: crea un plan nuevo tras un diagnóstico corto.
- «Continuemos con *tema*»: retoma la lección actual.
- «Tengo una duda: …»: respuesta directa, que se guarda en `DUDAS.md`.
- «Hazme un repaso de *tema*» o «Evalúame»: preguntas sobre lo ya visto.
- «¿Cómo voy?»: resumen de tu progreso y de los huecos pendientes.
- «Prefiero que me preguntes de otra forma»: cambia el método y lo anota en `METODO.md`.

## Si el cuaderno no se actualiza

El coach lo regenera con `coach.py build` (o `coach.mjs build`). También puedes abrir `cuaderno.html` y pulsar **Abrir carpeta** para leer los archivos directamente.
Para usarlo sin conexión, pide al coach que ejecute `vendor`: descargará las librerías en `.vendor/`.
