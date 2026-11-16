# Espacio de aprendizaje

Esta carpeta la gestiona **hb-coach** (creada el {{FECHA}}). Es tu material de estudio personal: si está dentro de un proyecto, no se sube a git.

## Qué hay aquí

| Ruta | Contenido |
|---|---|
| `cuaderno.html` | Tu cuaderno y tu aula: ábrelo en el navegador. Curso con módulos, lecciones, retos, exámenes, progreso, repasos, glosario y dudas. Se actualiza solo cuando el coach escribe. |
| `METODO.md` | El acuerdo de método: cómo quieres que el coach enseñe y corrija. Se puede cambiar cuando quieras. |
| `<tema>/PLAN.md` | Plan del tema: módulos con su examen, progreso, huecos pendientes y bitácora de sesiones. |
| `<tema>/lecciones/` | Una nota por lección, escrita bloque a bloque: 📖 teoría, 🛠 retos y ❓ preguntas, con tus intentos y su corrección. |
| `<tema>/examenes/` | Las preguntas y el resultado de cada examen de módulo. |
| `<tema>/repasos/` | Las preguntas y la corrección de cada repaso con el coach. |
| `<tema>/GLOSARIO.md` | Conceptos del tema con su definición. |
| `<tema>/DUDAS.md` | Dudas que resolviste por el camino. |

## Cómo funciona una lección

El coach escribe cada bloque en el cuaderno (teoría, reto y preguntas) y en la terminal te dice qué leer, qué hacer y qué enviarle. Le respondes en la terminal y su corrección aparece en el mismo bloque; la solución, solo después de tu intento. Los bloques que aún no tocan se ven como «🔒 Pendiente».

## Cómo pedirle cosas al coach

- «Quiero aprender *tema*»: diagnóstico corto y un plan por módulos.
- «Sigamos con mi plan de *tema*»: retoma donde lo dejaste, con el repaso que toque.
- «Tengo una duda: …»: respuesta directa, que se guarda en `DUDAS.md`.
- «Repasemos *tema*» o «Evalúame»: preguntas sobre lo ya visto o el examen del módulo.
- «¿Cómo voy?»: progreso, huecos y próximos repasos.
- «Prefiero que me preguntes de otra forma»: cambia el método y queda en `METODO.md`.

## Si el cuaderno no se actualiza

El coach lo regenera solo y la página abierta se recarga sola en unos segundos; si tu navegador no lo permite, recárgala a mano. También puedes abrir `cuaderno.html` y pulsar **Abrir carpeta** para leer los archivos directamente. Para usarlo sin conexión, pide al coach que ejecute `vendor`: descargará las librerías en `.vendor/`.
