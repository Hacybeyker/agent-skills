# Mediciones (antes, control y después)

En modo guiado las corre el usuario en su terminal, sin chat: **cero tokens**. En modo autónomo las corre un agente con el modelo más económico, que solo ejecuta `perf.py` y lee su resumen.

## El comando

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --flujo <flujo> --fase antes
```

Qué hace, en orden:

1. **Controles previos:** un solo dispositivo (o `--serial`), Android 10 o superior, app instalada, aviso si el build es `debuggable`, temperatura (se detiene si está caliente), batería, espacio libre y `trace_processor`.
2. **Compilación de ART fija** (`speed-profile`) y **calentamiento** (una corrida que no cuenta).
3. **Por cada corrida:** valida la pantalla de inicio, inicia Perfetto, espera el recorrido (Enter en modo manual, o el comando de `recorrido`), cierra la traza, la descarga, corre las consultas, valida la corrida, agrega las filas a `metricas.csv`, comprime la traza e imprime **una línea**.
4. **Al final:** un resumen compacto, `resumen.md` con el detalle y la sección "Métricas" de `estado.md` actualizada.

Sigue hasta juntar las corridas válidas pedidas (`--corridas`, por defecto 5), con hasta 3 intentos de más. Una corrida inválida se guarda como `_invalida_<motivo>` para auditoría y no entra al CSV.

| Opción | Para qué |
| --- | --- |
| `--fase antes \| control \| despues` | `control` es el bloque A/A del estado inicial (modo riguroso): mide el ruido |
| `--corridas 10` | Más potencia estadística, sin costo humano si el recorrido es automático |
| `--recorrido "<comando>"` | Recorre el flujo con un comando en vez de Enter (testigo) |
| `--memoria` | `dumpsys meminfo` después de cada corrida: PSS, heaps, actividades y vistas vivas |
| `--prueba` | Una corrida que imprime las métricas y no escribe el CSV |
| `--serial`, `--hz`, `--tp` | Dispositivo, tasa de refresco y ruta de `trace_processor` |

Códigos de salida: 2 uso o datos, 3 precondición (dispositivo, app, herramientas, pantalla de inicio), 4 captura fallida, 5 sin las corridas válidas pedidas.

## Condiciones (iguales antes y después)

- Mismo dispositivo, build, ambiente, usuario, datos, flags y red (la misma Wi-Fi).
- Batería sobre 50 % y sin ahorro de energía; el script avisa si el dispositivo está tibio y se detiene si está caliente.
- Mismo punto de partida y mismo modo de recorrido: no mezcles corridas manuales con corridas de testigo entre fases.
- **Si la sesión del ambiente expira:** inicia sesión de nuevo, vuelve al punto de partida y repite el calentamiento (`--calentamiento 1`). Las corridas afectadas quedan inválidas solas si el plan tiene `invalidar_si`.

## Qué vale en cada build

| Build | Vale para | No vale para |
| --- | --- | --- |
| `debuggable` | Conteos y orden de las llamadas, duplicados, fugas | Frames, CPU y tiempos: corre con chequeos extra; el logging de bodies, si lo hay, los infla todavía más |
| `profileable` (profiling) | Todo | — |
| Emulador | Conteos y fugas | Tiempos y frames |

Frames con FrameTimeline: Android 12 o superior. En Android 10 y 11, el script usa `gfxinfo` (métricas `gfx_*`).

## Familias de métricas

| Familia | Métricas | Lectura |
| --- | --- | --- |
| `app` | Jank de la app, slices del hilo principal, inflates, conteos de red, `cliente_ms` (= HTTP − TTFB), memoria | Dependen de la app: comparables con 5 corridas |
| `e2e` | Duración `HTTP`, `ttfb_ms`, métricas de usuario con red | Incluyen el backend: su veredicto es orientativo |
| `info` | `frames` (denominador) | Sin veredicto |

El presupuesto de frame sale de `hz`: 16,7 ms a 60 Hz, 11,1 ms a 90 Hz, 8,3 ms a 120 Hz.

## Con testigo

- **Frames y CPU:** `recorrido` en el plan (o `--recorrido`) con el comando de testigo para un flujo, sin video ni red:
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

Con la configuración base, las trazas pesan bastante menos que con la completa, y el script las comprime con gzip (`trace_processor` las lee igual). Avisa si quedan menos de 3 GB libres. Los heap dumps se borran al cerrar la investigación.
