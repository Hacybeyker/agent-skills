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

Pregúntalas todas juntas, en un solo mensaje:

- ¿La sesión del ambiente expira? ¿Cada cuánto? (Si expira a mitad de una corrida, esa corrida no vale.)
- ¿Qué datos de prueba necesita el flujo? (Por ejemplo, un usuario con movimientos o una lista no vacía.) Quedan fijos hasta el cierre.
- ¿En qué pantalla empieza cada flujo, y qué pantallas no deberían aparecer (login, onboarding)?
- Dispositivo: modelo y tasa de refresco **fija** (sin modo adaptativo). Para frames hace falta Android 12 o superior.
- Modos: guiado o autónomo; recorrido manual, por comando adb o con testigo; riguroso o triage.

## 4. Métricas principales (antes de medir)

Elige de 1 a 3 y fíjalas en `principales` de `plan.json`. Elegirlas después invita a quedarse con la que "mejoró".

- **Al menos una mide lo que siente el usuario de punta a punta:** TTFD, o una métrica de usuario hasta el contenido visible. Si falta la marca, agrégala antes de medir antes: una métrica que termina antes del spinner deja afuera justo lo que el usuario espera.
- **Prefiere la familia `app`**, que no depende del backend: `jank_app_pct`, `hilo_slices_sobre_presupuesto`, `hilo_max_ms`, `inflate_cantidad`, `red_llamadas`, `red_solapadas`, `red <endpoint> cliente_ms`.
- **Percentiles y porcentajes de frame** solo en flujos de régimen estable (scroll, animaciones). En un arranque o una carga los dominan unos pocos frames, y si cambia la cantidad de frames `perf.py` los marca "no comparable".
- **`jank_app_pct` (App Deadline Missed) es de la app;** `jank_total_pct` suma el del sistema y es informativa.

## 5. `plan.json` y `estado.md`

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py nuevo --paquete <applicationId> --carpeta <evidencias>/<alcance>/<AAAA-MM-DD> --flujo <nombre> --alcance "<alcance>" --instalar "<comando que instala el build de profiling>"
```

Crea la carpeta (por defecto en `reports/perf/`, o la de `AGENTS.md`), avisa si git no la ignora y deja las plantillas. Complétalas:

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
| `flujos.<nombre>.recorrido` | `manual` (Enter), un comando que recorre el flujo (`adb shell input ...`, testigo) o `{"tipo": "arranque-frio", "actividad", "espera_s"}` |
| `flujos.<nombre>.metricas_usuario` | `nombre`, `desde` y `hasta` (cada una con `marca`, `punto`: `inicio` o `fin`, y `cual`: `primera` o `ultima`) y `familia` |
| `flujos.<nombre>.familias` | Cambia la familia de una métrica (nombre o patrón), por ejemplo `{"ttfd_ms": "e2e"}` |
| `flujos.<nombre>.metricas_sql` | Métricas propias por corrida: archivos `.sql` en la carpeta que devuelven `nombre`, `valor` y, opcionales, `unidad` y `familia` |
| `mejoras` | Vacío: lo completa la sesión 2; `estado` lo cambia `perf.py decidir` |

Las marcas se buscan entre las secciones propias (`HTTP`, `QUEUE`, `CONN`, `TTFB`, `SCREEN`, `NAV`), `reportFullyDrawn`, el lanzamiento (`launching: <paquete>`) y los slices de primer nivel del hilo principal de más de 5 ms. `hasta` se busca después de `desde`.

**Recorrido por comando:** si el flujo se puede reproducir con adb (`input tap`, `input keyevent`, `am start` con un deep link), es mejor que el manual: 10 corridas sin costo humano y siempre iguales.

## 6. Corrida de prueba

Antes de aprobar, una corrida que imprime las métricas y no escribe el CSV. Valida que las marcas existan y que los valores tengan sentido:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --flujo <flujo> --prueba
```

## Entregable

`estado.md` con la ficha, el mapa y las hipótesis. Muestra la ficha y el plan y espera **una** aprobación. Después, `perf.py siguiente --carpeta <carpeta>`: deja en "Siguiente paso" los comandos de la medición (`antes`, `control` en modo riguroso y `diagnostico`) y el chat de la sesión 2. Pásaselos al usuario tal cual y detente.
