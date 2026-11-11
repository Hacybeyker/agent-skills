# Sesión 1 · Ficha y plan

Convierte el pedido en un plan de medición concreto. Termina con **una sola aprobación** (ficha y plan juntos) y con todo lo necesario para medir sin volver a preguntar.

**¿Es el arranque en frío?** Entonces esta sesión no hace falta: `perf.py nuevo --receta arranque-frio` arma `plan.json` y `estado.md` (ver [medicion.md](medicion.md)). Úsala para cualquier otro flujo.

## 1. Contexto mínimo

1. **`AGENTS.md`:** solo `## Stack`, `## DoD` y la sección de rendimiento. Sin `AGENTS.md`, avisa y ofrece `hb-setup`, o sigue con la detección.
2. **Setup:** si la sección de rendimiento no dice "setup listo" y el plan necesita secciones o el build de profiling, la siguiente sesión es la 0 ([setup.md](setup.md)). Que lo diga no alcanza: el código tiene que estar. `perf.py nuevo` comprueba que la instrumentación exista en el repo (busca `PerfHooks.kt`, que deja `instrumentar` en el código principal) y avisa si falta, con la forma de reaplicarla que diga `AGENTS.md` (un setup guardado como parche, por ejemplo). Si avisa, detente y dile al usuario qué paso falta: sin la instrumentación no salen las marcas y la variante medida puede no compilar.
3. **Verifica el stack** con una búsqueda en el catálogo y los archivos de build. Si no coincide con `AGENTS.md`, dilo y propone corregirlo.
   ```bash
   cd <raíz-del-proyecto> && grep -rhoE 'compose|rxjava[23]?|kotlinx-coroutines|livedata|okhttp|retrofit|ktor-client|apollo|coil|glide|picasso|epoxy|paging|navigation3|navigation-(compose|fragment)|hilt|koin|baselineprofile|benchmark-macro' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' . | sort | uniq -c
   ```
4. **Ubica el alcance:** módulos (`settings.gradle(.kts)`) y puntos de entrada. Si un módulo llega a la app como artefacto publicado y no como `project(":...")`, el código en disco puede no ser el que corre: dilo.
5. **Cambios ajenos sin commitear, antes de medir.** Corre `git status --short` en cada repo del flujo (el de la app y los de los módulos que se incluyen desde otras carpetas) y separa lo que es de perf (el setup, las marcas del inventario de `estado.md`) de lo que no: logs de depuración que imprimen objetos con datos, código a medio hacer, archivos sueltos. Lista lo que no es de perf, con su archivo y qué es, y **pregunta si se quita antes de medir**: ensucia el log, puede sumar trabajo al camino medido (serializar un objeto para un log en el hilo principal) y deja en la evidencia datos que no hacen falta. No lo reviertas tú: es trabajo del usuario; si decide dejarlo, anótalo en "Precondiciones" para que esté igual en todas las fases.

## 2. Mapa e hipótesis

- **Mapa del alcance:** pantallas, presentación y estado, navegación, llamadas de red esperadas en cada paso y dependencias compartidas. Si la plataforma tiene subagentes, delega el mapeo a uno económico y pide **como máximo 40 líneas**. Guarda en `estado.md` solo las rutas clave, una línea cada una.
- **Patrones:** carga solo los del stack detectado, desde [patrones/](patrones/): siempre [red.md](patrones/red.md) y [memoria.md](patrones/memoria.md); según el stack, [corrutinas-flow.md](patrones/corrutinas-flow.md), [rxjava.md](patrones/rxjava.md), [compose.md](patrones/compose.md) o [vistas.md](patrones/vistas.md); [arranque.md](patrones/arranque.md) si el flujo empieza en frío.
- **Hipótesis:** ordenadas por probabilidad, cada una con la métrica o la consulta que la confirma o la descarta.

## 3. Preguntas que evitan repetir mediciones

Pregúntalas todas juntas, en un solo mensaje, **con este texto**: cada opción dice lo que le va a tocar hacer al usuario. Recomienda la que corresponda al flujo y márcala.

1. **¿Cómo se recorre el flujo en cada corrida?**
   - **Comando adb** (recomendada siempre que el tramo medido sean uno o dos toques: "tocar el primer ítem", "abrir X desde Home"): el script toca por ti; 10 corridas por fase sin que hagas nada. Yo busco las coordenadas con `perf.py nodos` y dejo los toques en `recorrido.sh`, comentados.
   - **Comando adb, con Maestro/testigo para llegar al punto de partida** (recomendada si antes del tramo medido hay login, avisos, varias pantallas o un tab): un flow de Maestro deja la app lista antes de cada corrida (`preparar`, fuera de la traza) y el tramo medido sigue siendo uno o dos toques de `adb`. Ver "Flujos largos", abajo. Maestro **nunca** da los toques medidos: su driver vive en el dispositivo y, medido en un A/A, sumó un 14 % al tiempo de punta a punta y multiplicó por 3–10 la varianza del hilo principal.
   - **Deep link** (`am start -d ...`): abre la pantalla directo, sin el toque desde la anterior. Mide solo la pantalla.
   - **Manual** (gestos, elegir con criterio, OTP en cada corrida): tú recorres el flujo en el dispositivo y presionas Enter en cada corrida; 5 corridas por fase (más una de calentamiento), y algo más de variación.
2. **¿Dónde empieza cada flujo y qué pantallas no deberían aparecer** (login, onboarding)? El script no graba si la app está en otra pantalla.
3. **¿Qué pantallas salen solo la primera vez** (términos y condiciones, permisos, huella o biometría, onboarding, coach marks)? Se pasan una vez antes de medir y `preparar` las contempla por si vuelven (ver "Pantallas de una sola vez", abajo).
4. **¿Qué datos de prueba necesita el flujo** (un usuario con historial, una lista no vacía, "la primera película que aparezca")? Quedan fijos hasta el cierre.
5. **¿La sesión del ambiente expira? ¿Cada cuánto?** Si expira a mitad de una corrida, esa corrida no vale.
6. **Dispositivo:** modelo y tasa de refresco **fija** (sin modo adaptativo). No le pidas que la cambie a mano sin mirar antes: `perf.py nuevo` lee la que el dispositivo ya tiene fijada y la deja en el plan (ver "Tasa de refresco", abajo). Para frames hace falta Android 12 o superior.
7. **Profundidad:** *riguroso* (antes, control y después; recomendado si se van a aplicar mejoras) o *triage* (3 corridas y directo al diagnóstico; termina en el reporte inicial, sin línea base ni medición después). Con triage, `profundidad: "triage"` en el plan.

Con recorrido por comando, busca las coordenadas tú con `perf.py nodos`, nunca con capturas de pantalla (leer una imagen cuesta decenas de miles de tokens) ni sacando el centro a mano de un `grep`:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py nodos <carpeta>/logs/ui.xml --volcar --serial <serial> --texto "<texto del elemento>"
```

Vuelca la pantalla (`uiautomator dump`), busca el nodo por `--texto`, por `--id` (`resource-id`) o por `--desc` (`content-desc`) e imprime el centro de sus bounds ya como comando `adb -s <serial> shell input tap <x> <y>`. Avisa de lo que hace fallar un toque: que la pantalla todavía muestre un cargando (espera y vuelve a volcar: el contenido y las coordenadas cambian), que el centro caiga también dentro de otro nodo clickeable (algo flotante o superpuesto: confírmalo o toca otro punto del nodo), que el nodo esté deshabilitado o que varios coincidan (`--exacto`). Sin `--volcar` lee un volcado que ya tienes. Para confirmar que el toque llegó, otro `nodos --volcar` con un texto de la pantalla destino. Cada toque va a `<carpeta>/recorrido.sh` como `adb -s "$SERIAL" shell input tap <x> <y> && sleep <s>`, con su comentario (sección 5); las esperas se calibran con la corrida de prueba. Dos límites de `nodos`, que son heurísticas: el cargando lo reconoce por la clase de las barras de progreso o por un id, un texto o una descripción con las palabras usuales (progress, loading, shimmer, "Cargando"), así que no ve uno hecho a mano y puede avisar por una barra de progreso que no es de carga; y el aviso de superposición no sabe cuál de los dos nodos está encima. **No corras tú una captura manual**: espera a alguien que toque el dispositivo, así que se la entregas al usuario como comando.

**Teclado.** Un campo de texto abre el teclado, y el teclado tapa y desplaza lo que hay debajo:

- **Las coordenadas se toman con el teclado en el mismo estado que tendrá el recorrido en ese paso.** `nodos --volcar` avisa si el teclado estaba abierto al volcar.
- **ESC (`input keyevent 111`) no cierra todos los teclados:** no dependas de él.
- **BACK (`input keyevent 4`) solo si el teclado está abierto:** con el teclado cerrado, BACK sale de la pantalla. Compruébalo antes con `dumpsys input_method` (`mInputShown=true`), y **nunca invalides la corrida porque el teclado ya estaba cerrado** (nada de `|| exit 1` en ese paso). `recorrido.sh` trae el bloque comentado:
  ```bash
  teclado="$(adb -s "$SERIAL" shell dumpsys input_method | grep -c 'mInputShown=true' || true)"
  if [ "$teclado" != "0" ]; then adb -s "$SERIAL" shell input keyevent 4 && sleep 1; fi
  ```
  Va con `grep -c` y un `if`, no con `grep -q … &&`: con `set -o pipefail`, `grep -q` puede cortar la tubería y dar el paso por fallido, y un `&&` en la última línea del script termina con error cuando el teclado estaba cerrado.

**Regla dura: nunca escribes claves ni autorizas transacciones o pagos.** No ingreses contraseñas, PIN ni códigos de un solo uso, y no toques un botón que confirme una transacción o un pago. Las credenciales las escribe `preparar` desde variables de entorno que carga el usuario ("Credenciales", abajo), no tú. Toca solo nodos que identificaste con `nodos`, nunca coordenadas estimadas: un toque mal dado puede abrir una operación real. Si aparece una pantalla de autorización, de pago o de confirmación de una operación, también por error, **detente**: no toques nada más, dile al usuario qué pantalla quedó abierta y espera a que la cierre.

**Objetivo determinista: el elemento que se toca es siempre el mismo.** En todas las corridas y en todas las fases, el toque medido cae sobre el mismo elemento, con el mismo contenido detrás. "El ítem que quede a media pantalla después del scroll" no lo es: el scroll no se detiene siempre en el mismo lugar, otro ítem abre otro detalle (otros datos, otro peso) y eso entra como ruido. Hazlo determinista: toca un elemento que está a la vista **sin scroll previo** (el primero de la lista); si el scroll es parte de lo que se mide, que el toque vaya antes del scroll o sobre un elemento fijo (un tab, un botón), o usa datos de prueba con un solo ítem posible. Si no hay forma, dilo en la ficha y no elijas como principal una métrica que dependa de qué ítem se abrió.

**Tasa de refresco: se lee, no se adivina.** `perf.py nuevo` consulta `settings get system min_refresh_rate` y `peak_refresh_rate` en el dispositivo. Si las dos están puestas y coinciden, la tasa ya está fija: la deja en `hz` del plan y en la fila "Dispositivo" de la ficha, y no hay que pedirle nada al usuario. Si no, imprime el comando que la fija (`adb -s <serial> shell settings put system min_refresh_rate <hz> && adb -s <serial> shell settings put system peak_refresh_rate <hz>`) y el que la restaura al cerrar (los valores que había, o `settings delete system ...` si no había ninguno): si la pantalla es adaptativa, dáselos al usuario, anota el de restaurar en "Precondiciones" y pon `hz` en el plan. Algunos fabricantes ignoran esos ajustes; la corrida de prueba imprime la tasa que midió la traza y avisa si no es la del plan, y `capturar` deja ese aviso en `estado.md` y en `fases.json`.

**`preparar` es obligatorio con recorrido automático en un flujo que no es el arranque:** un comando que deja la app en el punto de partida antes de **cada** corrida (y después de fijar la compilación de ART, que puede cerrar la app). Corre **antes de que arranque la traza**, así que lo que haga no entra en las métricas. En una app de una sola actividad, `inicio` no distingue pantallas: sin `preparar`, la segunda corrida tocaría sobre la pantalla donde terminó la primera. Opciones: `adb -s <serial> shell input keyevent KEYCODE_BACK && sleep 1` si el flujo es ida y vuelta; `adb -s <serial> shell am force-stop <paquete> && adb -s <serial> shell am start -n <paquete>/<actividad> && sleep <s>` para arrancar siempre igual; o un flow de Maestro (abajo) cuando hay que atravesar varias pantallas. Si `preparar` falla (código distinto de 0), esa corrida se descarta y se repite; tres fallos seguidos detienen la captura con el motivo. Sin `preparar`, el script avisa y, si la app no está al frente, la relanza.

### Flujos largos: login y varias pantallas antes de lo que se mide

El caso típico: login, pantallas de primera vez y varias pantallas más antes del tramo que importa (elegir un ítem de una lista, abrir su detalle, abrir una pantalla secundaria), con un backend que a veces falla. Se divide en dos partes y cada una usa la herramienta que le corresponde:

1. **Llegar al punto de partida es `preparar`**, con un flow de Maestro que termina con la lista a la vista. Maestro resuelve lo que `adb` no puede: elegir por texto o `id`, esperar a que algo aparezca (`extendedWaitUntil`) y **actuar según la pantalla** (`runFlow` con `when: visible`): si la sesión sigue abierta, solo vuelve a la lista; si expiró, hace el login; si sale el aviso de huella, lo omite. Así cada corrida parte del mismo lugar aunque la anterior haya fallado a la mitad. El estado no se limpia (`clearState`): borrar datos trae de vuelta las pantallas de una sola vez y cambia el estado entre fases. Patrón en el plan:
   ```json
   "preparar": "maestro --device <serial> test -e PERF_USUARIO=\"$PERF_USUARIO\" -e PERF_CLAVE=\"$PERF_CLAVE\" <carpeta>/preparar.yaml > /dev/null 2>&1 && sleep 2",
   "requiere_env": ["PERF_USUARIO", "PERF_CLAVE"],
   "recorrido": "bash <carpeta>/recorrido.sh"
   ```
   Los `-e` solo hacen falta si el flow usa credenciales: Maestro no lee las variables del entorno por su cuenta (salvo las que empiezan con `MAESTRO_`), así que hay que pasárselas. El `sleep` final de `preparar` deja que el driver de Maestro termine antes de que arranque la traza. Con `testigo` instalado, Maestro ya está (`testigo setup`), y el flow puede vivir en la suite de testigo del equipo y servir también como prueba funcional. Lo que hay que cuidar al llamar a Maestro desde `preparar` está en "Maestro en `preparar`", abajo.
2. **El tramo medido es `recorrido`, solo con `adb`:** uno o dos toques con esperas generosas (las esperas no afectan a las métricas: la `ventana` va de marca a marca). Una métrica de usuario por salto (`lista_a_detalle_ms`: del `NAV` del detalle a su `MARK`; `detalle_a_secundaria_ms`), y la ventana desde el primer `NAV` hasta el último `MARK`. Si el detalle o la pantalla secundaria no tienen `PerfHooks.mark`, se agregan en el setup antes de medir.
3. **Lo que falla, se descarta solo:** `invalidar_si` con las pantallas de error del proyecto (`SCREEN *Error*`, `MARK error_*`); una corrida sin la ventana o sin una métrica principal (el toque que no navegó, el backend que no respondió) se repite; tres inválidas seguidas detienen la captura y lo dicen, y el total de intentos tiene una reserva proporcional a las corridas ([medicion.md](medicion.md)), así que un backend que falla de vez en cuando no la corta.
4. **Tiempos:** la traza solo cubre el tramo medido (segundos, no minutos), así que pesa poco; el reloj lo pone `preparar`: con la sesión abierta, unos segundos por corrida; con login en cada corrida, lo que tarde el login. Diez corridas más el calentamiento suelen ir de 5 a 15 minutos por fase. Pregunta si la sesión expira (pregunta 5) para que el flow lo contemple.

### Maestro en `preparar`

- **El flow siempre en un archivo:** `<carpeta>/preparar.yaml`, y se corre con `maestro --device <serial> test <carpeta>/preparar.yaml`. Nunca por la entrada estándar (un heredoc, `maestro test -`): se queda esperando y la sesión se cuelga.
- **Sin analítica ni chequeo de versión:** `export MAESTRO_CLI_NO_ANALYTICS=1 MAESTRO_DISABLE_UPDATE_CHECK=true` antes de llamarlo (o al principio de `preparar`). `testigo` ya lo hace; llamado directo, no.
- **Su salida va a `/dev/null`** (`> /dev/null 2>&1`): Maestro imprime cada paso con su valor, así que la línea de un `inputText` trae lo que escribió, claves incluidas. No leas esa salida ni la filtres con `grep` (la línea del paso que falló puede ser justo la de la clave): si necesitas saber por qué falla, pídele al usuario que corra el flow en su terminal y te diga en qué paso se detuvo. Tampoco leas la carpeta donde Maestro guarda cada corrida (`~/.maestro/tests/`): ahí el valor sigue visible aunque el paso tenga `label`. En el flow, ponle `label` a cada `inputText` de una credencial: el `label` reemplaza la descripción del paso y el valor deja de imprimirse.
- **Tipeo:** el teclado puede poner en mayúscula la primera letra de un campo que no lo impide, y un usuario en minúsculas queda mal escrito sin que nada falle hasta el login. Después de escribir, comprueba lo escrito. En Maestro, `assertVisible` con el texto esperado detecta que no se escribió, pero compara como expresión regular y sin distinguir mayúsculas: para una comparación exacta, `copyTextFrom` sobre el campo y `assertTrue: ${maestro.copiedText == PERF_USUARIO}`. Con `adb`, `nodos --id <campo>` imprime el texto que quedó, y `nodos --texto "<esperado>" --exacto` solo lo encuentra si es idéntico. Si sale cambiado: escribe un carácter de sobra al principio y bórralo al final (con `adb`: `input keyevent KEYCODE_MOVE_HOME` y `KEYCODE_FORWARD_DEL`), o desactiva la mayúscula automática en el teclado del dispositivo de pruebas y anótalo en "Precondiciones". Nunca compruebes así un campo de clave.
- **No cambies el modo que eligió el usuario sin preguntar.** Si pidió Maestro para `preparar` y no funciona (no está instalado, el flow no pasa de una pantalla), no lo reemplaces por un script de `adb` por tu cuenta, ni al revés: pregunta antes, en una línea, con el motivo y la consecuencia ("Maestro no logra escribir el usuario: ¿paso `preparar` a un script de adb? Pierde la espera por texto y necesita coordenadas fijas").

### Pantallas de una sola vez

Términos, permisos, huella, onboarding y coach marks aparecen la primera vez y no vuelven… hasta que se borran los datos, se reinstala la app o se cambia de dispositivo. Si `preparar` no las contempla, ese día todas las corridas salen inválidas.

1. **Precondición "primer uso hecho".** Antes de medir, se pasan una vez todas esas pantallas, a mano o con un flow aparte, y se anota en la fila "Precondiciones" de la ficha: "primer uso hecho: términos, huella y coach marks ya pasados".
2. **`preparar` es idempotente:** mira qué hay en pantalla y actúa según eso, así que llega al mismo punto de partida aparezcan o no. Con Maestro, `runFlow` con `when: visible` para un bloque y `optional: true` para un toque suelto:
   ```yaml
   appId: com.example.app
   ---
   - launchApp:
       clearState: false            # nunca se borran datos entre corridas ni entre fases
   - runFlow:                        # términos: solo si aparecen
       when:
         visible: "Aceptar términos"
       commands:
         - tapOn: "Aceptar términos"
   - runFlow:                        # la sesión expiró: login con las variables del usuario
       when:
         visible:
           id: "campo_usuario"
       commands:
         - tapOn:
             id: "campo_usuario"
         - inputText:
             text: ${PERF_USUARIO}
             label: "Escribe el usuario"   # con label, el valor no sale en la salida de Maestro
         - assertVisible:
             text: ${PERF_USUARIO}
             label: "El usuario quedó escrito"
         - tapOn:
             id: "campo_clave"
         - inputText:
             text: ${PERF_CLAVE}
             label: "Escribe la clave"
         - tapOn: "Ingresar"
   - tapOn:                          # aviso de huella: si sale, se omite
       text: "Ahora no"
       optional: true
   - extendedWaitUntil:              # el punto de partida, a la vista
       visible: "Inicio"
       timeout: 20000
   ```
   Con `adb`, un `uiautomator dump` antes de cada toque:
   ```bash
   #!/usr/bin/env bash
   # preparar.sh: deja la app en el punto de partida, estén o no las pantallas de una sola vez.
   set -euo pipefail
   S="${ANDROID_SERIAL:-emulator-5554}"
   hay() {  # ¿ese texto está a la vista? Borra el volcado anterior: si el nuevo falla, no hay nada que leer
     adb -s "$S" shell rm -f /sdcard/ui.xml
     adb -s "$S" shell uiautomator dump /sdcard/ui.xml > /dev/null 2>&1 || true
     adb -s "$S" shell cat /sdcard/ui.xml 2> /dev/null | grep -q "text=\"$1\""
   }
   adb -s "$S" shell am start -n com.example.app/.MainActivity > /dev/null && sleep 3
   if hay "Aceptar términos"; then adb -s "$S" shell input tap 540 2100 && sleep 2; fi
   if hay "Ahora no"; then adb -s "$S" shell input tap 300 1900 && sleep 2; fi
   hay "Inicio"   # si no llegó al punto de partida, termina con error y la corrida no vale
   ```
   Las coordenadas de cada toque salen de `perf.py nodos`, con esa pantalla a la vista.
3. **Sus marcas van en `invalidar_si`** (`SCREEN *Terminos*`, `MARK onboarding`, `SCREEN *Login*`): si una de esas pantallas aparece dentro del tramo medido, la corrida no vale y se repite.
4. **Nunca se borran datos entre fases** (`pm clear`, `clearState`, desinstalar): vuelven las pantallas de primera vez y el estado de la app deja de ser el mismo en antes y en después.

### Credenciales en `preparar`

- **Nunca en el plan, en el flow ni en el chat:** van en variables de entorno que carga el usuario, y el flow las lee (`${PERF_CLAVE}` en Maestro, pasadas con `-e PERF_CLAVE="$PERF_CLAVE"`; `"$PERF_CLAVE"` en un script).
- **Decláralas en el flujo del plan, siempre:** `"requiere_env": ["PERF_USUARIO", "PERF_CLAVE"]` (los nombres, nunca los valores). `capturar` comprueba que existan **antes de empezar** (antes de compilar y de tocar el dispositivo) y, si falta alguna, se detiene y dice cuál, sin gastar el calentamiento ni tres corridas. Como red de seguridad, `perf.py` lee además el comando de `preparar` y el script o el flow que nombra (`$VAR`, `${VAR}`, `-e NOMBRE="$VAR"`; solo nombres en mayúsculas, y no cuentan las que tienen valor por defecto, `${VAR:-x}`, las que el script asigna o pregunta si están, lo que va entre comillas simples o en un comentario, las de las herramientas (`ANDROID_SERIAL`…) ni las `MAESTRO_*`): las que encuentre y el plan no declare las trata como requeridas y avisa con la línea de `requiere_env` que falta (mientras no estén declaradas, la salida estándar de `preparar` se sigue descartando). La búsqueda es conservadora: ante la duda no cuenta una variable (un script que incluye otro con `source`, o que carga un `.env`, no aporta ninguna), así que no reemplaza a declararlas. `perf.py siguiente` repite ese aviso: un plan no se aprueba con variables sin declarar. Si una detectada no hace falta de verdad, dale un valor por defecto en el script; `--forzar` deja seguir sin ella. Si `preparar` falla, muestra las últimas líneas de su salida con el valor de esas variables enmascarado (`***`) y deja esa cola en `<carpeta>/logs/preparar.log` (solo si falla); si el comando manda su salida a `/dev/null`, lo dice y hay que correrlo a mano para ver el error. Sin `requiere_env`, la salida estándar de `preparar` se descarta y solo se lee la de error: decláralas siempre que el flow escriba una credencial. La salida de `preparar` ya no se ve mientras corre, así que no puede ser un comando que pregunte algo.
- **Se exportan en la terminal antes de abrir el agente.** Un agente solo ve las variables de la terminal desde la que se abrió: si el usuario las exporta después, o en otra terminal, la corrida de prueba que corre el agente no las tiene. Díselo al pedirlas: "expórtalas (`export PERF_USUARIO=... PERF_CLAVE=...`) en la terminal donde vas a medir y, si quieres que yo corra la prueba, antes de abrir este chat". Tú no las lees, no las imprimes y no las pides por el chat.

### Flujos que pasan por otra app

Una autorización externa, un pago, un login con otra app o un navegador: el flujo sale de la app medida y vuelve.

- **La traza no se corta** al cambiar de app, pero el tiempo que pasa en la otra app no es de la app medida, y no se compara.
- **Dos marcas y dos métricas, una a cada lado:** una marca justo antes de lanzar la otra app (`MARK <paso>_salida`) y otra donde llega el resultado (`MARK <paso>_resultado`, en el callback o en el `onNewIntent` que lo recibe). Una métrica de usuario termina en la marca de salida (lo que tarda la app en llegar hasta ahí) y otra empieza en la de resultado (lo que tarda en mostrar lo que sigue). Nunca una métrica de un lado al otro: mediría a la otra app y a quien la opera.
- **La ventana, en uno de los lados,** no a través del salto: si importan los dos, son dos flujos (o dos `segmentos`).
- **Lo que pasa en la otra app lo hace el usuario:** a mano (`--recorrido manual`) o con un flow que corre él, con sus credenciales. El agente nunca opera la otra app ni autoriza nada (regla dura de arriba).
- **Si Android mata la app medida** mientras está en segundo plano, vuelve con un arranque en frío y esa corrida no se compara: pon en `invalidar_si` la marca que lo delata (el `SCREEN ... onCreate` de la actividad de inicio, por ejemplo) y, si pasa seguido, mide con más memoria libre o parte el flujo en dos.

**Pasos que hace una persona dentro del recorrido** (autorizar en la otra app, resolver un desafío, completar un pago):

- **La pausa se ve y se responde en la terminal: `perf.py pausa`.** El recorrido corre como un proceso aparte de `perf.py`: un `read -p` puesto a mano en el script puede no mostrarse ni recibir la respuesta, y la terminal parece colgada. El mecanismo de la skill escribe en la terminal de quien corre la captura (`/dev/tty`), con un pitido, y espera ahí la respuesta, aunque la salida del recorrido esté redirigida: Enter sigue; `x` + Enter dice que esa corrida no vale (el recorrido termina con código 1 y la corrida se repite). Funciona igual en `capturar` y en `--prueba`. Sin una terminal interactiva (la corre un agente o una tarea programada), la captura se detiene al empezar, antes de compilar y de tocar el dispositivo, con el motivo: un recorrido con un paso humano lo corre la persona, en su terminal. `nuevo` deja la función comentada en `recorrido.sh`:
  ```bash
  pausa() { python3 -I "<carpeta-de-la-skill>/scripts/perf.py" pausa "$1" || exit $?; }
  adb -s "$SERIAL" shell input tap <x> <y> && sleep 2   # toca "Continuar": la app lanza la otra app
  pausa "Autoriza la operación en la otra app, vuelve a esta y presiona Enter"
  sleep 8                                               # lo que tarda la app en terminar después del regreso
  ```
- **Declara la pausa en el plan:** `"pausas": [{"desde": {"marca": "MARK autorizacion_salida"}, "hasta": {"marca": "MARK autorizacion_resultado"}}]`. Entre esas dos marcas el tiempo lo pone la persona. `perf.py` rechaza la ventana, las métricas de usuario y los tramos que crucen una pausa, con el motivo: al cargar el plan, lo que empieza en la marca donde empieza la pausa o termina en la marca donde termina; y sobre cada traza (desde la corrida de prueba), cualquiera que se solape con ella. No es una corrida inválida que se repite: es un error del plan, y la captura se detiene. La pausa va del fin de su primera marca al inicio de la segunda: una métrica puede terminar en la marca de salida y otra empezar en la de resultado, y el `margen_ms` de una ventana no cuenta.
- **Qué métricas nunca se usan:** las que cruzan la pausa (de la acción antes de la otra app hasta el resultado final); las que llegan hasta que la persona pulsa la tecla (el fin del recorrido, o `ventana_ms` y los frames de una ventana que termina después de la pausa de la terminal); y los frames o el hilo principal de la traza entera. Lo que sí: una métrica hasta la marca de salida, otra desde la de resultado, y los tramos de cada lado.
- **Tramos solo para la red (`solo_red`).** En un tramo donde la app espera o hace polling (por ejemplo, desde que llega el resultado de la otra app hasta que la operación queda confirmada), los frames y el hilo principal no dicen nada: decláralo con `"solo_red": true` y solo agrupa sus llamadas (`<tramo> red_llamadas`, `<tramo> red_ms`, `<tramo> red_ttfb_ms`, `<tramo> red_repetidas_2s` y `<tramo> red_solapadas`). Con tramos, el diagnóstico y el reporte traen además la tabla "Red por tramo": qué llamadas hace la app en cada parte del flujo ([medicion.md](medicion.md) · Métricas por tramo).
- **Un tramo con polling depende de cuándo vuelve la persona:** si la app consulta el estado cada cierto tiempo hasta que la operación queda confirmada, la cantidad de llamadas cambia con lo que tarde la persona. No la elijas como principal: se compara con medianas y se explica en el diagnóstico (cuántas consultas por corrida y cada cuánto), sin leer una diferencia de una o dos llamadas como mejora o regresión.
- **Lo condicional lo resuelve la persona en la pausa.** Lo que aparece a veces sí y a veces no antes o después de la otra app (un modal de confirmación, un desafío de riesgo, un "reintentar") no se automatiza con toques a coordenadas fijas: el texto de la pausa le dice a la persona qué puede salir y dónde tiene que quedar la app antes de presionar Enter, y el recorrido sigue desde ahí.
- **Los sistemas antifraude de comportamiento pueden reaccionar distinto a los toques inyectados por `adb`** (más desafíos o más confirmaciones que con una persona). Anótalo en "Precondiciones" si el flujo pasa por uno, y deja que la persona dé los toques sensibles dentro de la pausa.
- **Cada corrida puede ser una operación real.** Con un ambiente que mueve datos de verdad (un pago, una orden), cuenta las operaciones antes de aprobar y muéstralas en la ficha: la corrida de prueba (1) + el calentamiento de cada fase (1) + las corridas de cada fase. En modo riguroso con recorrido manual son 1 + 3 × (1 + 5) = 19; en triage, 1 + (1 + 3) = 5. Recomienda **triage** salvo que se vayan a aplicar mejoras, y usa datos de prueba que alcancen para todas.
- **El tope de la traza:** con pausas humanas un recorrido puede pasar los 10 minutos que trae la configuración. Súbelo con `duracion_max_s` en el flujo; si la traza termina antes que el recorrido, la corrida sale inválida y lo dice.

## 4. Métricas principales (antes de medir)

Elige de 1 a 3 y fíjalas en `principales` de `plan.json`. Elegirlas después invita a quedarse con la que "mejoró".

- **Al menos una mide lo que siente el usuario de punta a punta:** TTFD, o una métrica de usuario desde la acción (`NAV`, un toque) hasta la marca de contenido visible (`MARK <pantalla>`, de `PerfHooks.mark`). Si la pantalla no tiene la marca, agrégala antes de medir antes (es una línea, ver [setup.md](setup.md) · Contenido visible). Una métrica que termina en la última llamada de red deja afuera el render, y si una mejora reordena las llamadas cambia de significado: `comparar` lo avisa, pero ya es tarde.
- **En un emulador o con render por software, ninguna principal de frames** (`jank_app_pct`, `frame_*`, `gfx_*`): `perf.py` las marca `no confiable` en los reportes ([medicion.md](medicion.md) · Emulador). Elige conteos (`red_*`, `inflate_cantidad`) o una métrica de usuario, o mide en un dispositivo físico.
- **Prefiere la familia `app`**, que no depende del backend: `jank_app_pct`, `hilo_slices_sobre_presupuesto`, `hilo_max_ms`, `inflate_cantidad`, `red_llamadas`, `red_solapadas`, `red <endpoint> cliente_ms`.
- **Percentiles y porcentajes de frame** solo en flujos de régimen estable (scroll, animaciones). En un arranque o una carga los dominan unos pocos frames, y si cambia la cantidad de frames `perf.py` los marca "no comparable". En una ventana corta (menos de unos 100 frames: abrir una pantalla) `jank_app_pct` no sirve como principal: con 50 frames, cada frame mueve un 2 % y el CV pasa del 30 % en un A/A sin cambios. Ahí, `hilo_max_ms`, `hilo_slices_sobre_presupuesto` o `frame_p90_ms` (CV 6–8 % en el mismo A/A) y la métrica de usuario.
- **`jank_app_pct` (App Deadline Missed) es de la app;** `jank_total_pct` suma el del sistema y es informativa.
- **Una métrica de usuario mide un solo salto:** de la marca de la acción (`NAV`, o la marca de inicio de abajo) a la marca de su contenido. Si entre sus dos marcas hay otros toques o swipes del recorrido, lo que mide son las esperas del script, no la app: la corrida de prueba lo avisa ("incluye pasos del recorrido"). Para el recorrido completo ya está `ventana_ms`, que es informativa.
- **Marca de inicio para una acción que no navega.** Una búsqueda, un filtro, un scroll o un pull-to-refresh no cambian de pantalla: no hay `NAV` donde empezar a medir, y `input text` o `input swipe` no dejan ninguna marca. Cuando el tramo empieza así, propón una marca en el inicio de la acción, en el código que la recibe (`PerfHooks.mark("busqueda_inicio")` donde llega el texto o se dispara la carga; en un módulo que no ve `PerfHooks`, la marca temporal de [setup.md](setup.md) · Cambios temporales) y úsala como `desde` de la métrica, del tramo o de la ventana. Sin ella, la métrica tendría que empezar en el `NAV` anterior y abarcaría el tipeo del script.
- **Métricas por tramo (`segmentos`), cuando un pico de una pantalla se diluye en la ventana.** Las métricas de frames y del hilo principal cubren toda la ventana: en un flujo de varias pantallas, un frame largo al entrar a una de ellas mueve poco el P90 del recorrido completo. Declara ese tramo en `segmentos` del flujo, con dos marcas, y `perf.py` calcula en **todas** las corridas `<tramo> hilo_max_ms`, `<tramo> frame_p90_ms` y `<tramo> jank_app_pct`, con ruido y veredicto como cualquier métrica; pueden ir en `principales`. Conviene cuando la hipótesis apunta a una pantalla o a un gesto concretos (entrar al detalle, un scroll, una búsqueda) y cuando el usuario pide "el jank de esta parte". En un tramo corto vale lo de arriba: prefiere `<tramo> hilo_max_ms` a un porcentaje sobre pocos frames.

## 5. `plan.json` y `estado.md`

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py nuevo --paquete <applicationId> --serial <serial> --carpeta <evidencias>/<alcance>/<AAAA-MM-DD> --flujo <nombre> --alcance "<alcance>" --instalar "<comando que instala el build de profiling>"
```

Crea la carpeta (por defecto en `reports/perf/`, o la de `AGENTS.md`), la agrega a `.git/info/exclude` si git no la ignora (local: el repo no cambia; no toques `.gitignore`) y deja las plantillas. Complétalas:

| Campo | Qué es |
| --- | --- |
| `paquete` | `applicationId` instalado |
| `hz` | Opcional: tasa de refresco fija; `nuevo` lo pone si el dispositivo ya la tiene fijada. Sin él, `perf.py` la lee de cada traza. Si no coincide con la que mide la traza (más de un 6 %), la prueba y `capturar` lo avisan |
| `input_slices` | Opcional: patrón `GLOB` de los slices con los que Android entrega un toque a la app (por defecto `deliverInputEvent*`). Con ellos, la corrida de prueba avisa si una métrica de usuario abarca pasos del recorrido. El nombre depende de la versión de Android: si la prueba dice que no encontró ninguno, búscalo en la traza y ponlo aquí |
| `config` | `base` (por defecto), `completa` (más pesada, para entender una corrida) o la ruta de una propia |
| `compilacion` | `completa` (por defecto, para comparar cambios de código) o `perfil` (Baseline Profile; para medir uno) |
| `instalar` | Comando que compila e instala el build de profiling (`nuevo --instalar`): aparece en la medición después |
| `principales` | Las métricas principales |
| `flujos.<nombre>.pasos` | Los pasos exactos en el dispositivo |
| `flujos.<nombre>.inicio` | Parte del nombre de la actividad donde empieza: si es otra, no se graba |
| `flujos.<nombre>.invalidar_si` | Patrones (`fnmatch`) de secciones que invalidan la corrida, por ejemplo `SCREEN *Login*` |
| `flujos.<nombre>.recorrido` | `manual` (Enter), un comando con los toques medidos (`bash <carpeta>/recorrido.sh`, o `adb -s <serial> shell input tap ...` en línea; nunca Maestro) o `{"tipo": "arranque-frio", "actividad", "espera_s"}` |
| `flujos.<nombre>.preparar` | Comando que deja la app en el punto de partida antes de cada corrida (obligatorio con recorrido automático fuera del arranque; ver arriba) |
| `flujos.<nombre>.requiere_env` | Nombres de las variables de entorno que `preparar` o el recorrido necesitan (credenciales): `["PERF_USUARIO", "PERF_CLAVE"]`. Obligatorio si `preparar` usa alguna. `capturar` comprueba que existan antes de empezar y enmascara sus valores en la salida de `preparar`; las que `preparar` usa sin que estén aquí las exige igual si las detecta, con un aviso |
| `flujos.<nombre>.duracion_max_s` | Opcional: tope de la traza en segundos (por defecto 600). Súbelo si el recorrido dura más (pasos que hace una persona, [Flujos que pasan por otra app](#flujos-que-pasan-por-otra-app)); si la traza termina antes que el recorrido, la corrida es inválida y lo dice |
| `flujos.<nombre>.ventana` | **Obligatoria si el flujo no es el arranque:** `desde` y `hasta` (marcas, como en las métricas de usuario) y `margen_ms`. Frames, jank e hilo principal se calculan solo dentro de ella; sin ventana dependen de cuánto tarda el usuario en presionar Enter |
| `flujos.<nombre>.metricas_usuario` | `nombre`, `desde` y `hasta` (cada una con `marca`, `punto`: `inicio` o `fin`, y `cual`: `primera` o `ultima`) y `familia` |
| `flujos.<nombre>.segmentos` | Opcional: tramos del flujo con sus propias métricas, `[{"nombre": "detalle", "desde": {"marca": "NAV detalle"}, "hasta": {"marca": "MARK detalle"}}]`; `nombre` sin espacios, y `desde` y `hasta` como en `metricas_usuario` (más `margen_ms`, opcional). Agrega `<nombre> hilo_max_ms`, `<nombre> frame_p90_ms` y `<nombre> jank_app_pct` y, si la corrida tiene red, las llamadas que empiezan en el tramo (`<nombre> red_llamadas` y las demás `<nombre> red_*`). Con `"solo_red": true`, el tramo solo agrupa llamadas, sin frames ni hilo ([medicion.md](medicion.md) · Métricas por tramo) |
| `flujos.<nombre>.pausas` | Opcional: tiempo de una persona dentro del recorrido, `[{"desde": {"marca": "MARK autorizacion_salida"}, "hasta": {"marca": "MARK autorizacion_resultado"}}]`. La ventana, las métricas de usuario y los tramos no pueden cruzarla: `perf.py` lo rechaza con el motivo ([Flujos que pasan por otra app](#flujos-que-pasan-por-otra-app)) |
| `flujos.<nombre>.familias` | Cambia la familia de una métrica (nombre o patrón), por ejemplo `{"ttfd_ms": "e2e"}` |
| `flujos.<nombre>.metricas_sql` | Métricas propias por corrida: archivos `.sql` en la carpeta que devuelven `nombre`, `valor` y, opcionales, `unidad` y `familia` |
| `mejoras` | Vacío: lo completa la sesión 2 (también las mejoras a prueba, con `a_prueba` e `hipotesis`); `estado` lo cambia `perf.py decidir` |
| `hilos_ajenos` | Hilos del proceso que no son de la app (un servidor embebido, por ejemplo): lista de `{"nombre": "servidor", "patron": "^(ktor\|nio)-", "familia": "e2e"}`; `patron` es una expresión regular de Python sobre el nombre del hilo y `familia` es opcional (`e2e` por defecto). Con ellos `capturar` agrega las métricas de hilo y de red de [medicion.md](medicion.md) · Hilos ajenos |
| `no_leer` | Rutas o patrones que el agente no debe leer ni buscar (prueba a ciegas): `docs/ALCANCE-*`, `casos/`, `~/otro/proyecto`. `nuevo --no-leer` (repetible) y la línea `No leer:` de `AGENTS.md` (en la misma línea, o una viñeta por ruta debajo) los suman; se comparan con la ruta desde la raíz del proyecto (`**/ALCANCE-*` cubre cualquier carpeta); `siguiente` los repite en cada chat nuevo |
| `profundidad` | `riguroso` (por defecto) o `triage`: 3 corridas de antes, sin control, termina en el reporte inicial |
| `modelos` | Nombres de los modelos `economico`, `intermedio`, `diagnostico` (la sesión 2; opcional, sin él usa `intermedio`) y `alto` que imprime `siguiente` (por defecto Haiku, Sonnet, Sonnet y Opus); cámbialos si el usuario usa otra herramienta |

Las marcas se buscan entre las secciones propias (`HTTP`, `QUEUE`, `CONN`, `TTFB`, `SCREEN`, `NAV`, `MARK`), `reportFullyDrawn`, el lanzamiento (`launching: <paquete>`) y los slices de primer nivel del hilo principal de más de 5 ms. `hasta` se busca después de `desde`.

**Recorrido por comando:** si el flujo se puede reproducir con adb (`input tap`, `input keyevent`, `am start` con un deep link), es mejor que el manual: 10 corridas sin costo humano y siempre iguales.

**El recorrido va en un archivo.** `nuevo` deja `<carpeta>/recorrido.sh` con el esqueleto: escribe ahí los toques del tramo medido, **con un comentario por paso** que diga qué elemento toca y qué debe abrirse, y apunta el plan a él: `"recorrido": "bash <carpeta>/recorrido.sh"` (un comando en línea se sigue aceptando, pero una línea de coordenadas dentro de un JSON no se puede leer ni revisar). Lo mismo con `preparar`: `<carpeta>/preparar.sh` o `<carpeta>/preparar.yaml`. `perf.py` escribe en "Cómo se recorre" de `estado.md` el `preparar` y el `recorrido` de cada flujo y el comando para verlos correr a mano, sin medir: dáselo al usuario antes de aprobar, para que vea en el dispositivo lo que se va a medir. La carpeta de la investigación está fuera de git y se borra al limpiar: si el recorrido o el flow se van a reutilizar (otra investigación, otra persona), díselo al usuario para que los archive fuera de `reports/`.

## 6. Corrida de prueba

Antes de aprobar, una corrida que imprime las métricas y no escribe el CSV. No fija la compilación de ART (sus números no se guardan ni se comparan), así que tarda lo que el recorrido. Valida que las marcas existan, que los valores tengan sentido y, con recorrido por comando, que las esperas alcancen. Termina con "Marcas del plan": cada marca de la ventana, de las métricas de usuario, de los tramos y de `invalidar_si`, con ✔ o ✖, y una línea "Recorrido" con la última marca vista y su momento, cuánto dura la traza y cuántas secciones `HTTP` trae. Si el recorrido se corta a la mitad, esa línea dice hasta dónde llegó: no hace falta abrir la traza para saberlo. Si el plan espera red y no sale ninguna sección `HTTP`, lo avisa con los builders que no llaman al gancho ([setup.md](setup.md) · Red: conectar cada builder). Corrige el plan antes de seguir si avisa algo de esto: la tasa de refresco del plan no es la de la traza; una métrica de usuario incluye pasos del recorrido (el gesto que la dispara no cuenta, aunque sea un swipe largo; lo que cuenta es otro toque después); o una marca salió más de una vez en una misma carga (el gancho no es "una vez por carga": [setup.md](setup.md) · Contenido visible). Ese último aviso es una heurística: mira si entre dos apariciones de la misma marca hubo una navegación, otra pantalla, otra marca o una llamada de red, así que una recarga legítima de la misma pantalla no lo dispara, y un duplicado con una llamada en medio se le puede pasar. Si el recorrido es manual, se la entregas al usuario; si es automático, puedes correrla tú:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --flujo <flujo> --prueba
```

## Entregable

`estado.md` con la ficha, el mapa y las hipótesis. **Llena la tabla "Ficha" que ya trae `estado.md`**, fila por fila, reemplazando cada texto entre `<>` (Síntoma, Métricas principales, Build y ambiente, Modos, Stack; en Precondiciones, "primer uso hecho" y lo que haya que restaurar): no escribas una sección de ficha aparte, porque el reporte publica esa tabla y una fila con el texto de la plantilla sale como "sin completar". `perf.py siguiente` avisa de las filas que falten. Muestra la ficha y el plan (pasos, métricas principales, ventana y recorrido) y espera **una** aprobación. Después, `perf.py siguiente --carpeta <carpeta>`: deja en "Siguiente paso" los comandos de la medición (`antes`, `control` en modo riguroso y `diagnostico`) y el chat de la sesión 2, con lo que le toca hacer al usuario en cada uno. Pégalo tal cual y detente. Presupuesto: 15 pasos, o 25 en un flujo largo (login, pantallas de una sola vez o `preparar` con varias pantallas); el mapa va a un subagente económico, las preguntas van todas en un mensaje y las coordenadas salen de `perf.py nodos`, un paso por elemento.
