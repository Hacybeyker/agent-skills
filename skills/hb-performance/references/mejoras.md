# Sesión 3 · Mejora

Aplica **una** mejora aprobada, en su propio chat. Lee de `estado.md` el hallazgo y la receta, y de `plan.json` la mejora con `estado: aprobada`; abre solo los archivos que toca.

## Antes de tocar código

- **Frescura de la línea base:** mira `antes` en `fases.json` (fecha y commit). Si pasaron más de 14 días, si `git merge-base --is-ancestor <commit> HEAD` falla o si entraron otros cambios al alcance desde entonces, la línea base ya no representa este código: vuelve a medir `antes` (y `control`) antes de aplicar la mejora.
- **Una mejora por sesión.** Si el usuario aprobó varias, esta sesión hace la primera y "Siguiente paso" apunta a la siguiente en un chat nuevo. Se pueden medir juntas en `despues`, pero cada una lleva su commit.
- **Mejora a prueba** (`a_prueba` en `plan.json`): la causa no está probada, así que el cambio pone a prueba una hipótesis. Aplícala igual que las demás, con su test y su commit propuesto, y **sola en su fase después** si puedes: medida junto con otras, no se sabe cuál movió la métrica. Anota en "Mejoras aplicadas" la hipótesis y qué resultado la refuta. Si la medición la refuta (`✖ hipótesis refutada`), el cambio se revierte salvo que el usuario quiera conservarlo por otro motivo, y el hallazgo vuelve a `sin confirmar` con lo aprendido.

## Reglas

- **Mínima y dentro del alcance.** Si exige tocar algo fuera, detente y pregunta.
- **Un test que fije la mejora**, además de los existentes en verde. Por ejemplo:
  - una carga duplicada: el servidor falso (o el fake del repositorio) recibe una sola llamada por recorrido;
  - trabajo pesado fuera del hilo principal: el dispatcher o el scheduler de prueba confirma dónde corre;
  - una vista que se recreaba: el adapter se configura una sola vez por vista;
  - una migración de datos: un test que parte del formato viejo y termina con los datos intactos.
- **Tests instrumentados solo en un emulador:** `connectedAndroidTest` desinstala la app del dispositivo y se pierden los datos de prueba.
- **Reglas del proyecto durante la investigación:** si la sección de rendimiento de `AGENTS.md` tiene una línea sobre cómo conviven las reglas del proyecto con hb-performance (por ejemplo, "durante una investigación de hb-performance, el reporte de cada cambio es el de la skill"), síguela: la aprobó el usuario en el setup para no duplicar trabajo en cada mejora. Sin esa línea, las reglas del proyecto valen tal cual.
- **Si `AGENTS.md` no tiene `## DoD`**, no adivines qué validar: `perf.py siguiente` lo avisa e imprime una plantilla mínima (los tests unitarios del módulo que cambie y la compilación de la variante medida). Propónsela al usuario y, con ella aprobada, corre esos comandos.
- **DoD con la salida acotada:** los comandos de `## DoD`, con Gradle en `-q`, primero los tests del módulo afectado y el log completo en `<carpeta>/logs/`. Al chat llegan solo el conteo de tests y los fallos:
  ```bash
  cd <raíz-del-proyecto> && ( ./gradlew -q :<modulo>:testDebugUnitTest > <carpeta>/logs/tests-m1.log 2>&1; code=$?; grep -E "tests completed|FAILED|BUILD" <carpeta>/logs/tests-m1.log | tail -20; echo "exit $code"; exit $code )
  ```
- **Lo temporal** (una sección agregada para confirmar una hipótesis) se quita antes de proponer el commit.
- No dejes una edición y el comando que depende de ella en paralelo. No vuelques el diff al chat: lista los archivos y qué cambió en cada uno.

## Entregable

En `estado.md` y `plan.json`:

- **Mejoras aplicadas:** archivos, el test que la fija, el resultado del DoD y el commit propuesto con `hb-commit` (por ejemplo `perf(home): evitar la doble carga del historial`).
- **Pendientes** actualizados.
- **`instalar` en `plan.json`:** si falta, agrégalo con el comando que compila e instala el build de profiling (el de `AGENTS.md`, por ejemplo `./gradlew :app:installProfiling`), para que la medición después no dependa de recordarlo. Si el plan tiene `serial`, `siguiente` le antepone `ANDROID_SERIAL=<serial>` solo.
- **Al final**, marca la mejora aplicada; el comando imprime el siguiente paso (la siguiente mejora aprobada en un chat nuevo, o instalar y medir después) y lo deja en `estado.md`:
  ```bash
  cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py decidir --carpeta <carpeta> --aplicada <id>
  ```
  Pégalos tal cual; si hubo migración de datos, dilo en una línea antes. Detente, sin pedir el costo ni que vuelva a este chat.
