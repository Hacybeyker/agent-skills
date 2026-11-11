# Mediciones (antes, control y después)

En modo guiado las corre el usuario en su terminal, sin chat: **cero tokens**. En modo autónomo las corre un agente con el modelo más económico, que solo ejecuta `perf.py` y lee su resumen. La salida no se pega en ningún chat: queda en `metricas.csv`, `resumen.md` y `estado.md`.

## Receta: arranque en frío

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py nuevo --receta arranque-frio --paquete <applicationId> --carpeta reports/perf/arranque-frio/<AAAA-MM-DD> --instalar "<comando que instala el build de profiling>"
```

Arma `plan.json` (principales `ttid_ms`, `ttfd_ms` y `hilo_max_ms`; los frames como informativos) y `estado.md`, busca la actividad de inicio en el dispositivo e imprime los comandos que siguen. `--instalar` guarda el comando de instalación, que aparece en la medición después. Con `--red`, si la primera pantalla carga datos del backend, `ttfd_ms` pasa a `e2e`. En cada corrida, `perf.py` detiene la app **antes** de grabar, abre la actividad con `am start -W`, espera `espera_s` y exige `LaunchState: COLD`: si algo despertó la app antes (un widget, WorkManager, un push), la corrida no vale.

## El comando

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --fase antes --corridas 10
```

Qué hace, en orden:

1. **Controles previos:** un solo dispositivo (o `--serial`), Android 10 o superior, app instalada, aviso si el build es `debuggable`, temperatura (se detiene si está caliente), batería, espacio libre y `trace_processor`. En `despues`, se detiene si el build instalado es el mismo que midió `antes`, y avisa si la línea base es vieja o de otro commit.
2. **Compilación de ART igual en todas las fases** (`compilacion` del plan o `--compilacion`):
   - `completa` (por defecto): todo compilado antes de correr, como `CompilationMode.Full` de Macrobenchmark. No depende de perfiles ni de librerías: es la que sirve para comparar un cambio de código.
   - `perfil`: borra los perfiles, instala el Baseline Profile del APK con `profileinstaller` y compila con `speed-profile` (`CompilationMode.Partial`). Más parecida a una instalación de Play; para medir un Baseline Profile. Si el perfil no se instala, se detiene.

   Compilar tarda: en una app grande, varios minutos. `capturar` lo avisa antes de empezar ("… fijando la compilación de ART… no es un cuelgue") y al terminar dice cuánto tardó; lo mismo con cada traza que procesa ("… procesando la traza 2 de 10"). Con `completa`, si la app ya tiene el filtro `speed` en todo su código (lo lee de `dumpsys package dexopt`) y es la misma instalación en la que esta investigación la compiló la última vez (versión y fecha de instalación, guardadas en `<carpeta>/compilacion.json`), no recompila y lo dice; `--recompilar` la fuerza. Un build recién instalado, otro filtro o una salida que no se puede leer compilan como siempre.

   Sin esto, un build recién instalado corre con JIT y parece una regresión que no existe. Con `completa`, el TTID suele salir algo más alto que con `perfil` (un ejecutable más grande que cargar): sirve para comparar fases entre sí, no como el TTID que verá el usuario de Play. Cada corrida guarda `jit_ms` (informativa) y `comparar` avisa si la compilación o el JIT cambiaron entre fases. Después, el **calentamiento** (una corrida que no cuenta).
3. **Por cada corrida:** corre `preparar` (o relanza la app si no está al frente), valida la pantalla de inicio, inicia Perfetto, recorre el flujo (Enter, el comando o el arranque), cierra la traza, comprueba que la app siga viva (si se cayó, imprime el inicio del crash y cómo desofuscarlo), corre las consultas, agrega las filas a `metricas.csv`, comprime la traza e imprime **una línea**.
4. **Al final:** un resumen compacto, `resumen.md`, la sección "Métricas" de `estado.md` y `fases.json` (fecha, commit, versión, fecha de instalación y Hz de cada fase, la tasa de refresco que midió cada corrida en `hz_corridas`, los avisos y, en `flujos`, lo de cada flujo). Si el `hz` del plan difiere en más de un 6 % de la tasa que midió la traza, o si no hay `hz` y la tasa cambió entre corridas, lo avisa en la salida, en "Métricas" de `estado.md` y en `avisos` de `fases.json`; `comparar` lo repite. El presupuesto de frame se calculó con el `hz` del plan: corrígelo y repite lo medido así con `--rehacer`.

Sigue hasta juntar las corridas válidas pedidas (`--corridas`, por defecto 5), con intentos de reserva: 3 como mínimo y la mitad de las pedidas si son más (5 → 8 intentos, 10 → 15, 20 → 30), así que unas pocas inválidas sueltas no cortan una captura larga. Tres inválidas **seguidas** la detienen antes, sin gastar la reserva: algo falla de forma sistemática. Una corrida inválida se guarda como `_invalida_<motivo>` para auditoría y no entra al CSV.

| Opción | Para qué |
| --- | --- |
| `--fase antes \| control \| despues` | `control` es el bloque A/A del estado inicial (modo riguroso), justo después de `antes` y con el mismo build: mide el ruido |
| `--corridas 10` | Más potencia estadística, sin costo humano si el recorrido es automático |
| `--recorrido "<comando>"` | Recorre el flujo con un comando en vez de lo que diga el plan |
| `--preparar "<comando>"` | Deja la app en el punto de partida antes de cada corrida, en vez del `preparar` del plan. Sin ninguno, si la app no está al frente el script la relanza (la compilación de ART puede cerrarla) y avisa |
| (`ventana` del plan) | Frames, jank e hilo principal solo entre dos marcas del flujo (`ventana_ms` queda como informativa); sin ventana cubren toda la traza, lo que en un recorrido manual depende de cuánto tarda el usuario en presionar Enter |
| `--config cpu` | Una captura con muestreo de CPU, solo para el diagnóstico (con `--prueba`) |
| `--memoria` | `dumpsys meminfo` después de cada corrida: PSS, heaps, actividades y vistas vivas |
| `--prueba` | Una corrida que imprime las métricas y no escribe el CSV. **No fija la compilación de ART** (sus números no se guardan ni se comparan), así que tarda lo que el recorrido; `--compilar` la fija igual que en una fase. Al terminar dice qué marcas del plan salieron (✔) y cuáles no (✖), la última marca vista con su momento, cuánto dura la traza y cuántas secciones `HTTP` trae, también si la corrida se cortó a la mitad |
| `--sin-compilar` | No fija la compilación de ART (en una fase, solo para depurar el recorrido: esos números no se comparan con los de otra fase) |
| `--recompilar` | Compila aunque la app ya tenga la compilación completa de esta misma instalación |
| `--rehacer` | Descarta lo medido **de ese flujo** en esa fase (sus filas del CSV, sus trazas, que quedan aparte, y su registro en `fases.json`) y lo mide de nuevo. Lo de los otros flujos de la fase no se toca |
| `--compilacion completa \| perfil` | Cómo se compila la app antes de medir; la misma en todas las fases |
| `--serial`, `--hz`, `--tp`, `--forzar` | Dispositivo, tasa de refresco, ruta de `trace_processor` y seguir pese a un aviso que detiene |

**Cuánto dura la traza.** La corrida termina cuando termina el recorrido (`perf.py` detiene Perfetto); la configuración solo trae un tope, de 10 minutos (`duration_ms`). Un recorrido más largo (con pasos que hace una persona, por ejemplo) necesita un tope mayor: `"duracion_max_s": 1200` en el flujo del plan. Si la traza llega a su tope antes de que termine el recorrido, le falta el final: la corrida sale inválida con ese motivo ("la traza terminó antes que el recorrido") y hay que subir el tope. El archivo de la traza también tiene un máximo (1 GB en las configuraciones `base` y `cpu`; 2 GB en `completa`).

Códigos de salida: 2 uso o datos, 3 precondición (dispositivo, app, herramientas, pantalla de inicio, build repetido), 4 captura fallida, 5 sin las corridas válidas pedidas.

## El paso siguiente

Cada comando de `perf.py` termina con el paso siguiente, completo y en orden, y lo deja en "Siguiente paso" de `estado.md`: para cada paso, si es en la terminal o en un chat nuevo, qué hace, qué le toca hacer al usuario y, en los chats, el modelo y el esfuerzo (nombres de `modelos` en el plan). Si hace falta recalcularlo:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py siguiente --carpeta <carpeta>
```

## Después de medir antes (y control)

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py diagnostico --carpeta <carpeta>
```

Corre las consultas de diagnóstico sobre la corrida mediana y la peor de la primera métrica principal y deja `diagnostico.md`: el punto de partida de la sesión 2.

## Condiciones (iguales antes y después)

- Mismo dispositivo, build de profiling, ambiente, usuario, datos, flags y red (la misma Wi-Fi). Tasa de refresco fija y la misma en todas las fases ([ficha.md](ficha.md) · Tasa de refresco).
- Batería sobre 50 % y sin ahorro de energía; el script avisa si el dispositivo está tibio y se detiene si está caliente.
- Mismo punto de partida y mismo modo de recorrido: no mezcles corridas manuales con automáticas entre fases.
- **Nunca desinstales** la app entre fases: se pierden los datos y una instalación nueva puede restaurar un backup. Los tests instrumentados (`connectedAndroidTest`) desinstalan la app: córrelos en un emulador.
- **Si la mejora migra datos** (una base, un formato de archivo), abre la app una vez después de instalarla y antes de medir: el costo único no es parte de la mejora.
- **Si la sesión del ambiente expira:** inicia sesión de nuevo, vuelve al punto de partida y repite el calentamiento. Las corridas afectadas quedan inválidas solas si el plan tiene `invalidar_si`.

## Qué vale en cada build

| Build | Vale para | No vale para |
| --- | --- | --- |
| `debuggable` | Conteos y orden de las llamadas, duplicados, fugas | Frames, CPU y tiempos: corre con chequeos extra |
| `profileable` (profiling) | Todo | — |
| Emulador | El comportamiento de la red (qué llamadas hace, cuántas y en qué orden), conteos y fugas | Tiempos de frames, de hilo principal y de carga: no representan un teléfono (con `-gpu host` son orientativos; con render por software, no valen) |

Frames con FrameTimeline: Android 12 o superior. En Android 10 y 11, el script usa `gfxinfo` (métricas `gfx_*`).

### Emulador y render por software

`capturar` (y `humo`) detecta el emulador (`ro.kernel.qemu`, `ro.hardware`, el modelo) y el renderer de GLES que reporta SurfaceFlinger, en una sola llamada a `adb`:

| Entorno | `frames` | Qué pasa |
| --- | --- | --- |
| Dispositivo físico con GPU | `ok` | Nada |
| Emulador con GPU del host (`-gpu host`) | `baja` | Aviso: sus tiempos de frames, de hilo principal y de carga no representan un teléfono (son orientativos, y los reportes lo anotan en los avisos de `jank_*`, `frame_*` y `gfx_*`); sí sirve para el comportamiento de la red (qué llamadas, cuántas y en qué orden), los conteos (inflates) y las fugas |
| Render por software (SwiftShader, llvmpipe), en emulador o no | `no` | Aviso, y `comparar` y el reporte dan `no confiable` a los frames en lugar de un veredicto; los conteos y los tiempos que no son de frame siguen con el suyo |

Un emulador es una buena herramienta para lo que no depende del hardware: comprobar que las marcas y la red del plan salen (la corrida de prueba), contar llamadas, ver duplicados y el orden en que se disparan. Para decidir con tiempos, mide en un dispositivo físico. Con `no`, relanza el emulador con `-gpu host` (AVD: Graphics = Hardware; `emulator -avd <nombre> -gpu host`) o mide en un dispositivo físico, y repite las fases con `--rehacer`. El entorno queda en `fases.json` (`entorno`; si una fase se mide en varias tandas, conserva el peor nivel: relanzar el emulador con `-gpu host` no la vuelve confiable, hay que repetirla con `--rehacer`) y en la línea "Dispositivo" de `estado.md` cuando el investigador se crea con `nuevo`. Si el recorrido es en un emulador, **no elijas `jank_app_pct` ni `frame_*` como métrica principal** ([ficha.md](ficha.md) · Métricas principales).

## Familias de métricas

| Familia | Métricas | Lectura |
| --- | --- | --- |
| `app` | `ttid_ms`, `ttfd_ms` sin red, `bind_application_ms`, slices del hilo principal, jank de la app, inflates, conteos de red, `cola_ms`, `cliente_ms` (= HTTP − cola − conexión − TTFB), memoria | Dependen de la app: comparables con 5 corridas |
| `e2e` | Duración `HTTP`, `ttfb_ms`, `red_conexion_ms`, métricas de usuario y `ttfd_ms` con red | Incluyen el backend: su veredicto es orientativo |
| `info` | `frames` (denominador), `jank_total_pct` (incluye el del sistema), `ventana_ms`, `<métrica> hasta_ultima_red_ms` y lo que el plan marque | Sin veredicto |

- `ttid_ms`: del intent al primer frame, según el sistema (`launching: <paquete>`; sin él, el `TotalTime` de `am start -W`). `ttfd_ms`: hasta `reportFullyDrawn`. `bind_application_ms`: `Application.onCreate` y los content providers.
- `<métrica> hasta_ultima_red_ms`: para una métrica de usuario que termina en una llamada, cuánto hay desde su inicio hasta el fin de la última llamada de red. `comparar` avisa si se separan: la marca de fin dejó de ser la última llamada y la métrica cambió de definición.
- El presupuesto de frame sale de `hz` (del plan o de la traza): 16,7 ms a 60 Hz, 11,1 ms a 90 Hz, 8,3 ms a 120 Hz.

## Métricas por tramo (`segmentos`)

Las métricas de frames y del hilo principal cubren la ventana entera del flujo. Si el plan declara `segmentos` ([ficha.md](ficha.md)), cada corrida agrega, por tramo:

| Métrica | Qué es | Familia |
| --- | --- | --- |
| `<tramo> hilo_max_ms` | El slice de primer nivel más largo del hilo principal dentro del tramo (0 si no hay ninguno de 5 ms o más) | `app` |
| `<tramo> frame_p90_ms` | P90 de la duración de los frames del tramo | `app` |
| `<tramo> jank_app_pct` | Porcentaje de frames del tramo con App Deadline Missed | `app` |
| `<tramo> frames` | Cuántos frames tuvo el tramo: el denominador de las dos anteriores | `info` |
| `<tramo> red_llamadas` | Cuántas llamadas `HTTP` empiezan dentro del tramo | `app` |
| `<tramo> red_ms`, `<tramo> red_ttfb_ms` | Mediana de la duración y del TTFB de esas llamadas (no salen si el tramo no tuvo ninguna) | `e2e` |
| `<tramo> red_repetidas_2s`, `<tramo> red_solapadas` | Cuántas de esas llamadas son repetidas o solapadas, con el mismo criterio que `red_repetidas_2s` y `red_solapadas` | `app` |

- El tramo va de la marca `desde` a la marca `hasta` (más `margen_ms`, si lo tiene) y cuenta los slices y los frames que **se solapan** con él: el frame o el slice que ya estaba en curso cuando sale la marca de inicio también entra. Se calcula sobre toda la traza, así que un tramo puede quedar fuera de la ventana.
- Las métricas de la ventana (`hilo_max_ms`, `frame_p90_ms`, `jank_app_pct`) no cambian por declarar tramos.
- Si falta una marca del tramo, esa corrida no trae sus métricas y la salida lo dice (`sin marcas para: tramo <nombre>`); si una de ellas es principal, la corrida es inválida y se repite.
- Un tramo sin frames (muy corto, o en Android 11 o anterior, que no tiene FrameTimeline) solo trae `<tramo> hilo_max_ms`: ahí, esa es la que puede ser principal. Con `<tramo> frame_p90_ms` o `<tramo> jank_app_pct` como principal, la corrida sale inválida (`sin frames en el tramo`).
- Con pocos frames valen las mismas reservas que en la ventana: si `<tramo> frames` cambia más de un 50 % entre antes y después, el P90 y el porcentaje salen `no comparable`; con render por software, `no confiable`.
- Agregar un tramo después de medir `antes` deja esa métrica sin línea base: decláralos en la sesión 1, o repite `antes` (y `control`) con `--rehacer`.
- **Red por tramo.** Cada llamada `HTTP` se asigna al tramo donde **empieza** (si dos tramos se solapan, al primero del plan), aunque termine después; las que empiezan fuera de todos los tramos solo cuentan en las métricas de la corrida entera, que no cambian. Las `<tramo> red_*` salen cuando la corrida tiene red (alguna sección `HTTP`, o la investigación ya la medía); sin tramos, todo queda como siempre. No entran en el resumen compacto salvo que sean principales: se leen en la tabla "Red por tramo" de `diagnostico.md` (la corrida mediana y la peor, con los endpoints de cada tramo y las llamadas que quedan fuera) y del reporte (la mediana entre corridas, por fase).
- **`"solo_red": true`** en un tramo: no calcula frames, hilo ni jank; solo agrupa sus llamadas, y trae `<tramo> red_llamadas` aunque sea 0. Para los tramos donde la app espera o hace polling ([ficha.md](ficha.md) · Flujos que pasan por otra app).
- Una investigación que midió `antes` con una versión anterior de la skill no tiene las `<tramo> red_*` en esa fase: en `comparar` salen como métricas sin las dos fases, sin veredicto, hasta que se repita la fase.

## Hilos ajenos a la app

Si hay un servidor (o cualquier trabajo que no es de la app) en el mismo proceso, sus hilos suman CPU, memoria y tiempo de respuesta que no se arreglan en la app. Decláralos en `plan.json` con una expresión regular del nombre del hilo (`hilos_ajenos`, [ficha.md](ficha.md)); mira los nombres en `cpu_por_hilo`. Cuando hay `hilos_ajenos`, cada corrida hace una **segunda pasada** por la traza (unos segundos más) y agrega, por grupo declarado:

| Métrica | Qué es | Familia |
| --- | --- | --- |
| `hilos_<nombre>_cpu_ms` | CPU de los hilos del grupo dentro de la ventana del flujo (toda la traza si no hay ventana) | la del grupo (`e2e` por defecto) |
| `hilos_<nombre>_cantidad` | Cuántos hilos del grupo corrieron | `info` |
| `hilos_app_cpu_ms` | CPU del resto de los hilos de la app, sin el principal ni los de ningún grupo | `app` |
| `red <endpoint> <nombre>_cpu_ms` | **Mediana por llamada** de la CPU del grupo mientras esa llamada estaba en vuelo, sobre las mismas llamadas que `red <endpoint> ms` (las que no tuvieron CPU del grupo cuentan 0; si hay dos llamadas en vuelo a la vez, la CPU de ese momento cuenta en las dos). No es el total de la corrida: ese es `hilos_<nombre>_cpu_ms` | la del grupo |

Las métricas del hilo principal (`hilo_*`) no cambian: el hilo principal nunca es ajeno. Si un grupo es el backend, `red <endpoint> ms` y `ttfb_ms` ya incluyen su trabajo: compara con `red <endpoint> <nombre>_cpu_ms` (ambas son medianas por llamada) para ver cuánto de esa espera es CPU del servidor y cuánto es el propio tiempo del servidor (esperas, `delay`). Si un hilo calza con dos grupos, gana el primero de la lista.

## Con Maestro y testigo

- **Nunca como `recorrido`.** Medido en un A/A (misma app, mismo flujo, 10 corridas por lado), Maestro dando un solo toque sumó un 14 % al tiempo de punta a punta (284 → 325 ms, con un ruido adb-contra-adb del 0,4 %) y multiplicó por 3–10 la varianza del hilo principal; la traza creció seis veces. Su driver corre en el dispositivo y activa accesibilidad: trabajo extra para la app dentro de la ventana medida, y no depende del flow.
- **Sí como `preparar`:** corre antes de que arranque la traza. Un flow de Maestro lleva la app al punto de partida (login, avisos, tab) y el tramo medido queda en uno o dos toques de `adb` ([ficha.md](ficha.md) · Flujos largos). `maestro --device <serial> test <carpeta>/preparar.yaml > /dev/null 2>&1 && sleep 2` (con `-e VAR="$VAR"` por cada credencial); `testigo run` no, porque además instala la app si el artefacto cambió y arranca la evidencia.
- **Red con Chucker (build `debuggable`), aparte de la medición:** conteos, duplicados y solapadas por endpoint, sin instrumentación:
  ```bash
  cd <raíz-del-proyecto> && testigo run --app <apk-debug> --flows <flujo.yaml> --repeat 5 --network chucker --network-format har --no-record --out <carpeta>/red-antes
  cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py har --fase antes --flujo <flujo> --csv <carpeta>/metricas.csv <carpeta>/red-antes/*/<flujo>/*/network.har
  ```
- Los flujos para medir no limpian el estado (`clearState`): vuelven las pantallas de una sola vez y el estado deja de ser el mismo entre fases ([ficha.md](ficha.md) · Pantallas de una sola vez).

## Con Macrobenchmark

Solo si el proyecto ya tiene un módulo de benchmark. Sus métricas traen los valores de cada iteración: pásalos a `metricas.csv` como corridas, con su fase y familia. Controla la compilación con `CompilationMode` y usa al menos 5 iteraciones.

## Disco

Con la configuración base, las trazas de un arranque pesan unos pocos MB comprimidas (`trace_processor` las lee igual). El script avisa si quedan menos de 3 GB libres. Al cerrar, las trazas se borran (ver [cierre.md](cierre.md)).
