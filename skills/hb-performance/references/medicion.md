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

   Sin esto, un build recién instalado corre con JIT y parece una regresión que no existe. Con `completa`, el TTID suele salir algo más alto que con `perfil` (un ejecutable más grande que cargar): sirve para comparar fases entre sí, no como el TTID que verá el usuario de Play. Cada corrida guarda `jit_ms` (informativa) y `comparar` avisa si la compilación o el JIT cambiaron entre fases. Después, el **calentamiento** (una corrida que no cuenta).
3. **Por cada corrida:** valida la pantalla de inicio, inicia Perfetto, recorre el flujo (Enter, el comando o el arranque), cierra la traza, comprueba que la app siga viva (si se cayó, imprime el inicio del crash y cómo desofuscarlo), corre las consultas, agrega las filas a `metricas.csv`, comprime la traza e imprime **una línea**.
4. **Al final:** un resumen compacto, `resumen.md`, la sección "Métricas" de `estado.md` y `fases.json` (fecha, commit, versión, fecha de instalación y Hz de cada fase).

Sigue hasta juntar las corridas válidas pedidas (`--corridas`, por defecto 5), con hasta 3 intentos de más. Una corrida inválida se guarda como `_invalida_<motivo>` para auditoría y no entra al CSV.

| Opción | Para qué |
| --- | --- |
| `--fase antes \| control \| despues` | `control` es el bloque A/A del estado inicial (modo riguroso), justo después de `antes` y con el mismo build: mide el ruido |
| `--corridas 10` | Más potencia estadística, sin costo humano si el recorrido es automático |
| `--recorrido "<comando>"` | Recorre el flujo con un comando en vez de lo que diga el plan |
| (`ventana` del plan) | Frames, jank e hilo principal solo entre dos marcas del flujo (`ventana_ms` queda como informativa); sin ventana cubren toda la traza, lo que en un recorrido manual depende de cuánto tarda el usuario en presionar Enter |
| `--config cpu` | Una captura con muestreo de CPU, solo para el diagnóstico (con `--prueba`) |
| `--memoria` | `dumpsys meminfo` después de cada corrida: PSS, heaps, actividades y vistas vivas |
| `--prueba` | Una corrida que imprime las métricas y no escribe el CSV |
| `--rehacer` | Descarta lo medido en esa fase (filas del CSV y trazas, que quedan aparte) y la mide de nuevo |
| `--compilacion completa \| perfil` | Cómo se compila la app antes de medir; la misma en todas las fases |
| `--serial`, `--hz`, `--tp`, `--forzar` | Dispositivo, tasa de refresco, ruta de `trace_processor` y seguir pese a un aviso que detiene |

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

- Mismo dispositivo, build de profiling, ambiente, usuario, datos, flags y red (la misma Wi-Fi). Tasa de refresco fija.
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
| Emulador | Conteos y fugas | Tiempos y frames |

Frames con FrameTimeline: Android 12 o superior. En Android 10 y 11, el script usa `gfxinfo` (métricas `gfx_*`).

## Familias de métricas

| Familia | Métricas | Lectura |
| --- | --- | --- |
| `app` | `ttid_ms`, `ttfd_ms` sin red, `bind_application_ms`, slices del hilo principal, jank de la app, inflates, conteos de red, `cola_ms`, `cliente_ms` (= HTTP − cola − conexión − TTFB), memoria | Dependen de la app: comparables con 5 corridas |
| `e2e` | Duración `HTTP`, `ttfb_ms`, `red_conexion_ms`, métricas de usuario y `ttfd_ms` con red | Incluyen el backend: su veredicto es orientativo |
| `info` | `frames` (denominador), `jank_total_pct` (incluye el del sistema), `ventana_ms`, `<métrica> hasta_ultima_red_ms` y lo que el plan marque | Sin veredicto |

- `ttid_ms`: del intent al primer frame, según el sistema (`launching: <paquete>`; sin él, el `TotalTime` de `am start -W`). `ttfd_ms`: hasta `reportFullyDrawn`. `bind_application_ms`: `Application.onCreate` y los content providers.
- `<métrica> hasta_ultima_red_ms`: para una métrica de usuario que termina en una llamada, cuánto hay desde su inicio hasta el fin de la última llamada de red. `comparar` avisa si se separan: la marca de fin dejó de ser la última llamada y la métrica cambió de definición.
- El presupuesto de frame sale de `hz` (del plan o de la traza): 16,7 ms a 60 Hz, 11,1 ms a 90 Hz, 8,3 ms a 120 Hz.

## Con testigo

- **Frames y CPU:** `recorrido` en el plan con el comando de testigo para un flujo, sin video ni red:
  `testigo run --app <apk-profiling> --flows <flujo.yaml> --network none --no-record --out <carpeta>/testigo`.
  testigo no reinstala un APK que no cambió, así que se conserva la compilación.
- **Red con Chucker (build `debuggable`):** conteos, duplicados y solapadas por endpoint, sin instrumentación:
  ```bash
  cd <raíz-del-proyecto> && testigo run --app <apk-debug> --flows <flujo.yaml> --repeat 5 --network chucker --network-format har --no-record --out <carpeta>/red-antes
  cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py har --fase antes --flujo <flujo> --csv <carpeta>/metricas.csv <carpeta>/red-antes/*/<flujo>/*/network.har
  ```
- Los flujos para medir no limpian el estado (`clearState`), salvo que se mida el arranque en frío.

## Con Macrobenchmark

Solo si el proyecto ya tiene un módulo de benchmark. Sus métricas traen los valores de cada iteración: pásalos a `metricas.csv` como corridas, con su fase y familia. Controla la compilación con `CompilationMode` y usa al menos 5 iteraciones.

## Disco

Con la configuración base, las trazas de un arranque pesan unos pocos MB comprimidas (`trace_processor` las lee igual). El script avisa si quedan menos de 3 GB libres. Al cerrar, las trazas se borran (ver [cierre.md](cierre.md)).
