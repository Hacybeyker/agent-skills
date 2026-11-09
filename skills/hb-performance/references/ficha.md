# Sesión 1 · Ficha y plan

Convierte el pedido en un plan de medición concreto. Termina con **una sola aprobación** (ficha y plan juntos) y con todo lo necesario para medir sin volver a preguntar.

**¿Es el arranque en frío?** Entonces esta sesión no hace falta: `perf.py nuevo --receta arranque-frio` arma `plan.json` y `estado.md` (ver [medicion.md](medicion.md)). Úsala para cualquier otro flujo.

## 1. Contexto mínimo

1. **`AGENTS.md`:** solo `## Stack`, `## DoD` y la sección de rendimiento. Sin `AGENTS.md`, avisa y ofrece `hb-setup`, o sigue con la detección.
2. **Setup:** si la sección de rendimiento no dice "setup listo" y el plan necesita secciones o el build de profiling, la siguiente sesión es la 0 ([setup.md](setup.md)).
3. **Verifica el stack** con una búsqueda en el catálogo y los archivos de build. Si no coincide con `AGENTS.md`, dilo y propone corregirlo.
   ```bash
   cd <raíz-del-proyecto> && grep -rhoE 'compose|rxjava[23]?|kotlinx-coroutines|livedata|okhttp|retrofit|ktor-client|apollo|coil|glide|picasso|epoxy|paging|navigation3|navigation-(compose|fragment)|hilt|koin|baselineprofile|benchmark-macro' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' . | sort | uniq -c
   ```
4. **Ubica el alcance:** módulos (`settings.gradle(.kts)`) y puntos de entrada. Si un módulo llega a la app como artefacto publicado y no como `project(":...")`, el código en disco puede no ser el que corre: dilo.

## 2. Mapa e hipótesis

- **Mapa del alcance:** pantallas, presentación y estado, navegación, llamadas de red esperadas en cada paso y dependencias compartidas. Si la plataforma tiene subagentes, delega el mapeo a uno económico y pide **como máximo 40 líneas**. Guarda en `estado.md` solo las rutas clave, una línea cada una.
- **Patrones:** carga solo los del stack detectado, desde [patrones/](patrones/): siempre [red.md](patrones/red.md) y [memoria.md](patrones/memoria.md); según el stack, [corrutinas-flow.md](patrones/corrutinas-flow.md), [rxjava.md](patrones/rxjava.md), [compose.md](patrones/compose.md) o [vistas.md](patrones/vistas.md); [arranque.md](patrones/arranque.md) si el flujo empieza en frío.
- **Hipótesis:** ordenadas por probabilidad, cada una con la métrica o la consulta que la confirma o la descarta.

## 3. Preguntas que evitan repetir mediciones

Pregúntalas todas juntas, en un solo mensaje, **con este texto**: cada opción dice lo que le va a tocar hacer al usuario. Recomienda la que corresponda al flujo y márcala.

1. **¿Cómo se recorre el flujo en cada corrida?**
   - **Comando adb** (recomendada siempre que el tramo medido sean uno o dos toques: "tocar el primer ítem", "abrir X desde Home"): el script toca por ti; 10 corridas por fase sin que hagas nada. Yo busco las coordenadas con `uiautomator dump` y las dejo en el plan.
   - **Comando adb, con Maestro/testigo para llegar al punto de partida** (recomendada si antes del tramo medido hay login, avisos, varias pantallas o un tab): un flow de Maestro deja la app lista antes de cada corrida (`preparar`, fuera de la traza) y el tramo medido sigue siendo uno o dos toques de `adb`. Ver "Flujos largos", abajo. Maestro **nunca** da los toques medidos: su driver vive en el dispositivo y, medido en un A/A, sumó un 14 % al tiempo de punta a punta y multiplicó por 3–10 la varianza del hilo principal.
   - **Deep link** (`am start -d ...`): abre la pantalla directo, sin el toque desde la anterior. Mide solo la pantalla.
   - **Manual** (gestos, elegir con criterio, OTP en cada corrida): tú recorres el flujo en el dispositivo y presionas Enter en cada corrida; 5 corridas por fase (más una de calentamiento), y algo más de variación.
2. **¿Dónde empieza cada flujo y qué pantallas no deberían aparecer** (login, onboarding)? El script no graba si la app está en otra pantalla.
3. **¿Qué datos de prueba necesita el flujo** (un usuario con movimientos, una lista no vacía, "la primera película que aparezca")? Quedan fijos hasta el cierre.
4. **¿La sesión del ambiente expira? ¿Cada cuánto?** Si expira a mitad de una corrida, esa corrida no vale.
5. **Dispositivo:** modelo y tasa de refresco **fija** (sin modo adaptativo). Para frames hace falta Android 12 o superior.
6. **Profundidad:** *riguroso* (antes, control y después; recomendado si se van a aplicar mejoras) o *triage* (3 corridas y directo al diagnóstico; termina en el reporte inicial, sin línea base ni medición después). Con triage, `profundidad: "triage"` en el plan.

Con recorrido por comando, busca las coordenadas tú, **solo con `uiautomator dump` y `grep`**, nunca con capturas de pantalla (leer una imagen cuesta decenas de miles de tokens): `adb -s <serial> shell uiautomator dump /sdcard/ui.xml && adb -s <serial> pull /sdcard/ui.xml <carpeta>/logs/` y lee solo el nodo que importa (`grep -o '<node[^>]*text="Nombre"[^>]*>' | head -3`; el centro del `bounds` es el tap). Para confirmar que el tap llegó, otro `dump` y `grep` de un texto de la pantalla destino. El `recorrido` del plan queda como `adb -s <serial> shell input tap <x> <y> && sleep <s>`; las esperas se calibran con la corrida de prueba. **No corras tú una captura manual**: espera a alguien que toque el dispositivo, así que se la entregas al usuario como comando.

**`preparar` es obligatorio con recorrido automático en un flujo que no es el arranque:** un comando que deja la app en el punto de partida antes de **cada** corrida (y después de fijar la compilación de ART, que puede cerrar la app). Corre **antes de que arranque la traza**, así que lo que haga no entra en las métricas. En una app de una sola actividad, `inicio` no distingue pantallas: sin `preparar`, la segunda corrida tocaría sobre la pantalla donde terminó la primera. Opciones: `adb -s <serial> shell input keyevent KEYCODE_BACK && sleep 1` si el flujo es ida y vuelta; `adb -s <serial> shell am force-stop <paquete> && adb -s <serial> shell am start -n <paquete>/<actividad> && sleep <s>` para arrancar siempre igual; o un flow de Maestro (abajo) cuando hay que atravesar varias pantallas. Si `preparar` falla (código distinto de 0), esa corrida se descarta y se repite; tres fallos seguidos detienen la captura con el motivo. Sin `preparar`, el script avisa y, si la app no está al frente, la relanza.

### Flujos largos: login y varias pantallas antes de lo que se mide

El caso típico: abrir la app, iniciar sesión, aceptar términos, omitir la huella y dos avisos, llegar al Home, cambiar de tab… 30 o 40 segundos antes del tramo que importa (elegir una tarjeta de una lista, abrir su detalle, abrir el desglose), con algún microservicio que a veces falla. Se divide en dos partes y cada una usa la herramienta que le corresponde:

1. **Llegar al punto de partida es `preparar`**, con un flow de Maestro que termina con la lista a la vista. Maestro resuelve lo que `adb` no puede: elegir por texto o `id`, esperar a que algo aparezca (`extendedWaitUntil`) y **actuar según la pantalla** (`runFlow` con `when: visible`): si la sesión sigue abierta, solo vuelve a la lista; si expiró, hace el login; si sale el aviso de huella, lo omite. Así cada corrida parte del mismo lugar aunque la anterior haya fallado a la mitad. El estado no se limpia (`clearState`) salvo que el flujo sea el arranque. Patrón en el plan:
   ```json
   "preparar": "maestro --device <serial> test <carpeta>/preparar.yaml > /dev/null && sleep 2",
   "recorrido": "adb -s <serial> shell input tap <x1> <y1> && sleep 4 && adb -s <serial> shell input tap <x2> <y2> && sleep 4"
   ```
   El `sleep` final de `preparar` deja que el driver de Maestro termine antes de que arranque la traza. Con `testigo` instalado, Maestro ya está (`testigo setup`), y el flow puede vivir en la suite de testigo del equipo y servir también como prueba funcional.
2. **El tramo medido es `recorrido`, solo con `adb`:** uno o dos toques con esperas generosas (las esperas no afectan a las métricas: la `ventana` va de marca a marca). Una métrica de usuario por salto (`lista_a_detalle_ms`: del `NAV` del detalle a su `MARK`; `detalle_a_desglose_ms`), y la ventana desde el primer `NAV` hasta el último `MARK`. Si el detalle o el desglose no tienen `PerfHooks.mark`, se agregan en el setup antes de medir.
3. **Lo que falla, se descarta solo:** `invalidar_si` con las pantallas de error del proyecto (`SCREEN *Error*`, `MARK error_*`); una corrida sin la ventana o sin una métrica principal (el toque que no navegó, el backend que no respondió) se repite; tres inválidas seguidas detienen la captura y lo dicen, y el total de intentos tiene una reserva proporcional a las corridas ([medicion.md](medicion.md)), así que un backend que falla de vez en cuando no la corta.
4. **Tiempos:** la traza solo cubre el tramo medido (segundos, no minutos), así que pesa poco; el reloj lo pone `preparar`: con la sesión abierta, unos segundos por corrida; con login en cada corrida, lo que tarde el login. Diez corridas más el calentamiento suelen ir de 5 a 15 minutos por fase. Pregunta si la sesión expira (pregunta 4) para que el flow lo contemple.

## 4. Métricas principales (antes de medir)

Elige de 1 a 3 y fíjalas en `principales` de `plan.json`. Elegirlas después invita a quedarse con la que "mejoró".

- **Al menos una mide lo que siente el usuario de punta a punta:** TTFD, o una métrica de usuario desde la acción (`NAV`, un toque) hasta la marca de contenido visible (`MARK <pantalla>`, de `PerfHooks.mark`). Si la pantalla no tiene la marca, agrégala antes de medir antes (es una línea, ver [setup.md](setup.md) · Contenido visible). Una métrica que termina en la última llamada de red deja afuera el render, y si una mejora reordena las llamadas cambia de significado: `comparar` lo avisa, pero ya es tarde.
- **En un emulador o con render por software, ninguna principal de frames** (`jank_app_pct`, `frame_*`, `gfx_*`): `perf.py` las marca `no confiable` en los reportes ([medicion.md](medicion.md) · Emulador). Elige conteos (`red_*`, `inflate_cantidad`) o una métrica de usuario, o mide en un dispositivo físico.
- **Prefiere la familia `app`**, que no depende del backend: `jank_app_pct`, `hilo_slices_sobre_presupuesto`, `hilo_max_ms`, `inflate_cantidad`, `red_llamadas`, `red_solapadas`, `red <endpoint> cliente_ms`.
- **Percentiles y porcentajes de frame** solo en flujos de régimen estable (scroll, animaciones). En un arranque o una carga los dominan unos pocos frames, y si cambia la cantidad de frames `perf.py` los marca "no comparable". En una ventana corta (menos de unos 100 frames: abrir una pantalla) `jank_app_pct` no sirve como principal: con 50 frames, cada frame mueve un 2 % y el CV pasa del 30 % en un A/A sin cambios. Ahí, `hilo_max_ms`, `hilo_slices_sobre_presupuesto` o `frame_p90_ms` (CV 6–8 % en el mismo A/A) y la métrica de usuario.
- **`jank_app_pct` (App Deadline Missed) es de la app;** `jank_total_pct` suma el del sistema y es informativa.

## 5. `plan.json` y `estado.md`

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py nuevo --paquete <applicationId> --carpeta <evidencias>/<alcance>/<AAAA-MM-DD> --flujo <nombre> --alcance "<alcance>" --instalar "<comando que instala el build de profiling>"
```

Crea la carpeta (por defecto en `reports/perf/`, o la de `AGENTS.md`), la agrega a `.git/info/exclude` si git no la ignora (local: el repo no cambia; no toques `.gitignore`) y deja las plantillas. Complétalas:

| Campo | Qué es |
| --- | --- |
| `paquete` | `applicationId` instalado |
| `hz` | Opcional: tasa de refresco fija. Sin él, `perf.py` la lee de cada traza |
| `config` | `base` (por defecto), `completa` (más pesada, para entender una corrida) o la ruta de una propia |
| `compilacion` | `completa` (por defecto, para comparar cambios de código) o `perfil` (Baseline Profile; para medir uno) |
| `instalar` | Comando que compila e instala el build de profiling (`nuevo --instalar`): aparece en la medición después |
| `principales` | Las métricas principales |
| `flujos.<nombre>.pasos` | Los pasos exactos en el dispositivo |
| `flujos.<nombre>.inicio` | Parte del nombre de la actividad donde empieza: si es otra, no se graba |
| `flujos.<nombre>.invalidar_si` | Patrones (`fnmatch`) de secciones que invalidan la corrida, por ejemplo `SCREEN *Login*` |
| `flujos.<nombre>.recorrido` | `manual` (Enter), un comando con los toques medidos (`adb -s <serial> shell input tap ...`; nunca Maestro) o `{"tipo": "arranque-frio", "actividad", "espera_s"}` |
| `flujos.<nombre>.preparar` | Comando que deja la app en el punto de partida antes de cada corrida (obligatorio con recorrido automático fuera del arranque; ver arriba) |
| `flujos.<nombre>.ventana` | **Obligatoria si el flujo no es el arranque:** `desde` y `hasta` (marcas, como en las métricas de usuario) y `margen_ms`. Frames, jank e hilo principal se calculan solo dentro de ella; sin ventana dependen de cuánto tarda el usuario en presionar Enter |
| `flujos.<nombre>.metricas_usuario` | `nombre`, `desde` y `hasta` (cada una con `marca`, `punto`: `inicio` o `fin`, y `cual`: `primera` o `ultima`) y `familia` |
| `flujos.<nombre>.familias` | Cambia la familia de una métrica (nombre o patrón), por ejemplo `{"ttfd_ms": "e2e"}` |
| `flujos.<nombre>.metricas_sql` | Métricas propias por corrida: archivos `.sql` en la carpeta que devuelven `nombre`, `valor` y, opcionales, `unidad` y `familia` |
| `mejoras` | Vacío: lo completa la sesión 2; `estado` lo cambia `perf.py decidir` |
| `hilos_ajenos` | Hilos del proceso que no son de la app (un servidor embebido, por ejemplo): lista de `{"nombre": "servidor", "patron": "^(ktor\|nio)-", "familia": "e2e"}`; `patron` es una expresión regular de Python sobre el nombre del hilo y `familia` es opcional (`e2e` por defecto). Con ellos `capturar` agrega las métricas de hilo y de red de [medicion.md](medicion.md) · Hilos ajenos |
| `no_leer` | Rutas o patrones que el agente no debe leer ni buscar (prueba a ciegas): `docs/ALCANCE-*`, `casos/`, `~/otro/proyecto`. `nuevo --no-leer` (repetible) y la línea `No leer:` de `AGENTS.md` (en la misma línea, o una viñeta por ruta debajo) los suman; se comparan con la ruta desde la raíz del proyecto (`**/ALCANCE-*` cubre cualquier carpeta); `siguiente` los repite en cada chat nuevo |
| `profundidad` | `riguroso` (por defecto) o `triage`: 3 corridas de antes, sin control, termina en el reporte inicial |
| `modelos` | Nombres de los modelos `economico`, `intermedio` y `alto` que imprime `siguiente` (por defecto Haiku, Sonnet y Opus); cámbialos si el usuario usa otra herramienta |

Las marcas se buscan entre las secciones propias (`HTTP`, `QUEUE`, `CONN`, `TTFB`, `SCREEN`, `NAV`, `MARK`), `reportFullyDrawn`, el lanzamiento (`launching: <paquete>`) y los slices de primer nivel del hilo principal de más de 5 ms. `hasta` se busca después de `desde`.

**Recorrido por comando:** si el flujo se puede reproducir con adb (`input tap`, `input keyevent`, `am start` con un deep link), es mejor que el manual: 10 corridas sin costo humano y siempre iguales.

## 6. Corrida de prueba

Antes de aprobar, una corrida que imprime las métricas y no escribe el CSV. Valida que las marcas existan (las de la ventana y las de las métricas: si falta alguna, el script lo dice), que los valores tengan sentido y, con recorrido por comando, que las esperas alcancen. Si el recorrido es manual, se la entregas al usuario; si es automático, puedes correrla tú:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --flujo <flujo> --prueba
```

## Entregable

`estado.md` con la ficha, el mapa y las hipótesis. Muestra la ficha y el plan (pasos, métricas principales, ventana y recorrido) y espera **una** aprobación. Después, `perf.py siguiente --carpeta <carpeta>`: deja en "Siguiente paso" los comandos de la medición (`antes`, `control` en modo riguroso y `diagnostico`) y el chat de la sesión 2, con lo que le toca hacer al usuario en cada uno. Pégalo tal cual y detente. Presupuesto: 15 pasos; el mapa va a un subagente económico y las preguntas van todas en un mensaje.
