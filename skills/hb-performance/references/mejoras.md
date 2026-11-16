# Sesión 3 · Mejora

Aplica **una** mejora aprobada, en su propio chat. Lee de `estado.md` el hallazgo y la receta, y de `plan.json` la mejora con `estado: aprobada`; abre solo los archivos que toca.

## Antes de tocar código

- **Frescura de la línea base:** mira `antes` en `fases.json` (fecha y commit). Si pasaron más de 14 días, si `git merge-base --is-ancestor <commit> HEAD` falla o si entraron otros cambios al alcance desde entonces, la línea base ya no representa este código: vuelve a medir `antes` (y `control`) antes de aplicar la mejora.
- **La decisión es del usuario.** Solo aplicas una mejora con `estado: aprobada`. Si la que te piden está `propuesta`, no corras `decidir --aprobar` por tu cuenta, aunque el pedido parezca justificarlo: entrega el comando `decidir` (lo imprime `perf.py siguiente`) y detente.
- **Las marcas del plan que toca el cambio.** Antes de editar, lista las marcas del plan (`plan.json`: ventana, métricas de usuario, tramos) cuyo código toca la mejora: por archivo y por ruta de ejecución. Cuenta también un cambio que no edita la línea de la marca pero cambia cuándo o en qué hilo corre (pasar un trabajo a otro hilo, cambiar el momento en que se entrega un resultado). Después de aplicarla, si alguna puede dejar de emitirse o moverse, ajústala **al mismo punto semántico** (el mismo momento para el usuario: no midas otra cosa), sin esperas ni condiciones, y anótala en "Cambios temporales por revertir" con qué cambió.
- **El recorrido no se toca a escondidas.** Después de medir antes, no cambies `preparar`, `recorrido` ni sus scripts (`preparar.sh`, `recorrido.sh`, los flows) aunque la mejora lo parezca pedir (una espera para que termine una precarga): `perf.py` guarda la huella de su contenido por fase y la comparación dejaría de ser igual contra igual. Si la mejora depende de un tiempo, proponlo como **escenario** del flujo ([medicion.md](medicion.md) · Escenarios de tiempo) o como línea base nueva (`lineabase`), y déjalo como paso en "Siguiente". No escribas en `estado.md` que algo fue "igual en todas las fases": esa condición la escribe `perf.py` en "Cómo se recorre".
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
- **El DoD son los comandos de `## DoD` de `AGENTS.md`, tal cual y todos:** la suite completa del módulo afectado (no solo la clase de test nueva) y lo demás que pida (la compilación de la variante medida, el formateador). Correr solo el test nuevo no es el DoD: no dice si la mejora rompió otro test del módulo. Si un comando no se puede correr (falta un dispositivo, tarda más que el presupuesto de pasos), dilo en el resumen; no lo des por corrido.
- **DoD con la salida acotada:** con Gradle en `-q`, primero los tests del módulo afectado y el log completo en `<carpeta>/logs/`. Al chat llegan solo el conteo de tests y los fallos:
  ```bash
  cd <raíz-del-proyecto> && ( ./gradlew -q :<modulo>:testDebugUnitTest > <carpeta>/logs/tests-m1.log 2>&1; code=$?; grep -E "tests completed|FAILED|BUILD" <carpeta>/logs/tests-m1.log | tail -20; echo "exit $code"; exit $code )
  ```
- **Lo temporal** (una sección agregada para confirmar una hipótesis) se quita antes de proponer el commit.
- No dejes una edición y el comando que depende de ella en paralelo. No vuelques el diff al chat: lista los archivos y qué cambió en cada uno.

## Entregable

En `estado.md` y `plan.json`:

- **Mejoras aplicadas:** archivos, el test que la fija, **los comandos del DoD que corriste y el resultado de cada uno** (por ejemplo `:lista:testDebugUnitTest`: 212 tests, 0 fallos; `:app:assembleProfiling`: ok) y el commit propuesto con `hb-commit` (por ejemplo `perf(home): evitar la doble carga del historial`).
- **Pendientes** actualizados.
- **`instalar` en `plan.json`:** si falta, agrégalo con el comando que compila e instala el build de profiling (el de `AGENTS.md`, por ejemplo `./gradlew :app:installProfiling`), para que la medición después no dependa de recordarlo. Si el plan tiene `serial`, `siguiente` le antepone `ANDROID_SERIAL=<serial>` solo.
- **Al final**, marca la mejora aplicada **con los archivos que cambió** (solo los de la mejora y su test: ni los cambios temporales ni los de otra mejora). `perf.py` guarda su diff contra el último commit en `<carpeta>/cambios/<id>.diff` (también los archivos nuevos, sin tocar el índice) y el reporte final dev lo muestra en "Cambios de código": antes y después, por qué y qué mejoró. Si cambió archivos de otro repo (un módulo incluido desde otra carpeta), repite el comando con `--repo <ruta-del-otro-repo>` y sus archivos. El comando imprime el siguiente paso (la siguiente mejora aprobada en un chat nuevo, o instalar y medir después) y lo deja en `estado.md`:
  ```bash
  cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py decidir --carpeta <carpeta> --aplicada <id> --archivos <ruta/Archivo.kt>,<ruta/ArchivoTest.kt>
  ```
- **Después, la corrida de prueba con la mejora**, para confirmar que salen todas las marcas del plan antes de medir después (va después de marcarla aplicada: `siguiente` solo cuenta una prueba posterior a la mejora). Si el dispositivo está conectado y el build se puede instalar, avisa en una línea, instala y córrela tú (`capturar --prueba`, como en la sesión 1); si falta una marca, ajústala en esta misma sesión, anótala en "Cambios temporales por revertir" y repite la prueba. Si no puedes correrla, `siguiente` la deja como primer paso, y no ofrece medir después sin ella.
- **Para terminar**, pega tal cual la salida del último comando de `perf.py` que corriste (`decidir` o la prueba: los dos imprimen el paso siguiente), **en un bloque de código** (fuera de él, el chat puede comerse los `*` de una ruta); antes, en tu resumen final, nombra los comandos del DoD que corriste y su resultado (y cuál no corriste, si hubo alguno), y si hubo migración de datos, dilo en una línea. Detente, sin pedir el costo ni que vuelva a este chat.
