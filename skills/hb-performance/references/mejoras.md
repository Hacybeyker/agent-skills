# Sesión 3 · Mejoras

Aplica las mejoras elegidas en la sesión 2. Lee de `estado.md` los hallazgos elegidos y su receta; abre solo los archivos que tocan.

## Reglas

- **Una mejora a la vez**, mínima y dentro del alcance. Si exige tocar algo fuera, detente y pregunta.
- **Un test que fije la mejora**, además de los existentes en verde. Por ejemplo:
  - una carga duplicada: el servidor falso (o el fake del repositorio) recibe una sola llamada por recorrido;
  - trabajo pesado fuera del hilo principal: el dispatcher o el scheduler de prueba confirma dónde corre;
  - una vista que se recreaba: el adapter se configura una sola vez por vista.
- **DoD con la salida acotada:** los comandos de `## DoD` del proyecto, con Gradle en `-q`, primero los tests del módulo afectado (`--tests`) y el log completo en `<carpeta>/logs/`. Al contexto llegan solo el conteo de tests y los fallos:
  ```bash
  cd <raíz-del-proyecto> && ./gradlew -q :<modulo>:testDebugUnitTest > <carpeta>/logs/tests-h1.log 2>&1; echo "exit $?"; grep -E "tests completed|FAILED|BUILD" <carpeta>/logs/tests-h1.log | tail -20
  ```
- **Secciones temporales** agregadas para confirmar una hipótesis: quítalas antes de proponer el commit.
- No dejes una edición y el comando que depende de ella en paralelo.

## Entregable

En `estado.md`:

- **Mejoras aplicadas:** por cada una, los archivos, el test que la fija, el resultado del DoD y el commit propuesto con `hb-commit` (por ejemplo `perf(home): evitar la doble carga del historial`).
- **Pendientes** actualizados.
- **Siguiente paso:** la medición después, con el comando exacto (el mismo de antes con `--fase despues`), después de instalar el build de profiling con los cambios.
