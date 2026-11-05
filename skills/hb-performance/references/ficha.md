# Sesión 1 · Ficha y plan

Convierte el pedido en un plan de medición concreto. Termina con **una sola aprobación** (ficha y plan juntos) y con todo lo necesario para medir sin volver a preguntar.

## 1. Contexto mínimo

1. **`AGENTS.md`:** solo `## Stack`, `## DoD` y `## Rendimiento`. Sin `AGENTS.md`, avisa y ofrece `hb-setup`, o sigue con la detección.
2. **Setup:** si `## Rendimiento` no dice "setup listo" y el plan necesita secciones o el build de profiling, la siguiente sesión es la 0 ([setup.md](setup.md)).
3. **Verifica el stack** con una búsqueda en el catálogo y los archivos de build. Si no coincide con `AGENTS.md`, dilo y propone corregirlo.
   ```bash
   cd <raíz-del-proyecto> && grep -rhoE 'compose|rxjava[23]?|kotlinx-coroutines|livedata|okhttp|retrofit|ktor-client|apollo|coil|glide|picasso|epoxy|paging|navigation3|navigation-(compose|fragment)|hilt|koin|baselineprofile|benchmark-macro' --include='*.toml' --include='*.gradle' --include='*.gradle.kts' . | sort | uniq -c
   ```
4. **Ubica el alcance:** módulos (`settings.gradle(.kts)`) y puntos de entrada. Si un módulo llega a la app como artefacto publicado y no como `project(":...")`, el código en disco puede no ser el que corre: dilo.

## 2. Mapa e hipótesis

- **Mapa del alcance:** pantallas, presentación y estado, navegación, llamadas de red esperadas en cada paso y dependencias compartidas. Si la plataforma tiene subagentes, delega el mapeo a uno económico y pide **como máximo 40 líneas** de respuesta. Guarda en `estado.md` solo las rutas clave, una línea cada una: así las sesiones siguientes no vuelven a recorrer el código.
- **Patrones:** carga solo los del stack detectado, desde [patrones/](patrones/): siempre [red.md](patrones/red.md) y [memoria.md](patrones/memoria.md); según el stack, [corrutinas-flow.md](patrones/corrutinas-flow.md), [rxjava.md](patrones/rxjava.md), [compose.md](patrones/compose.md) o [vistas.md](patrones/vistas.md); [arranque.md](patrones/arranque.md) si el flujo empieza en frío.
- **Hipótesis:** ordenadas por probabilidad, cada una con la métrica que la confirma o la descarta.

## 3. Preguntas que evitan repetir mediciones

Pregúntalas todas juntas, en un solo mensaje:

- ¿La sesión del ambiente expira? ¿Cada cuánto? (Si expira a mitad de una corrida, esa corrida no vale.)
- ¿Qué datos de prueba necesita el flujo? (Por ejemplo, un usuario con movimientos o una lista no vacía.)
- ¿En qué pantalla empieza cada flujo, y qué pantallas no deberían aparecer (login, onboarding)?
- Dispositivo: modelo, versión de Android y tasa de refresco. Para frames hace falta Android 12 o superior.
- Modos: guiado o autónomo; manual o testigo; riguroso o triage.

## 4. Métricas principales (antes de medir)

Elige de 1 a 3 y fíjalas en `principales` de `plan.json`. Elegirlas después invita a quedarse con la que "mejoró".

- **Prefiere la familia `app`**, que no depende del backend: `jank_app_pct`, `hilo_slices_sobre_presupuesto`, `hilo_slices_100ms`, `inflate_cantidad`, `red_llamadas`, `red_solapadas`, `red <endpoint> cliente_ms`.
- **A 60 Hz**, los percentiles de frame quedan clavados en múltiplos del vsync (16,7 o 33 ms): úsalos como apoyo, no como métrica principal.
- **`jank_app_pct` (App Deadline Missed) es de la app;** `jank_total_pct` incluye tipos que no lo son, como Buffer Stuffing.
- **Métricas de usuario:** lo que el usuario siente ("volver a Home hasta ver los datos"), como tiempo entre dos marcas de la traza. Suelen ser `e2e`: incluyen el backend.

## 5. `plan.json` y `estado.md`

Crea la carpeta `<evidencias>/<alcance>/<AAAA-MM-DD>/` (por defecto `reports/perf/...`, o la de `## Rendimiento`) y confirma que git la ignora: `git check-ignore -q <carpeta>`. Copia las plantillas de `assets/plantillas/` de esta skill y complétalas.

`plan.json` es la entrada de `perf.py`:

| Campo | Qué es |
| --- | --- |
| `paquete` | `applicationId` instalado |
| `hz` | Tasa de refresco del dispositivo (fija el presupuesto de frame) |
| `config` | `base` (por defecto), `completa` (más pesada, para diagnóstico) o la ruta de una propia |
| `principales` | Las métricas principales |
| `flujos.<nombre>.pasos` | Los pasos exactos en el dispositivo |
| `flujos.<nombre>.inicio` | Parte del nombre de la actividad donde empieza: si es otra, no se graba |
| `flujos.<nombre>.invalidar_si` | Patrones (`fnmatch`) de secciones que invalidan la corrida, por ejemplo `SCREEN *Login*` |
| `flujos.<nombre>.recorrido` | `manual` o el comando que recorre el flujo (por ejemplo `testigo run ...`) |
| `flujos.<nombre>.metricas_usuario` | `nombre`, `desde` y `hasta` (cada una con `marca`, `punto`: `inicio` o `fin`, y `cual`: `primera` o `ultima`) y `familia` |

Las marcas se buscan entre las secciones `HTTP`, `TTFB`, `SCREEN` y `NAV`. `hasta` se busca después de `desde`.

## 6. Corrida de prueba

Antes de aprobar, una corrida que imprime las métricas y no escribe el CSV. Valida que las marcas existan y que los valores tengan sentido:

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py capturar --plan <carpeta>/plan.json --flujo <flujo> --prueba
```

## Entregable

`estado.md` con la ficha, el mapa, las hipótesis y "Siguiente paso" apuntando a la medición antes: el comando exacto de `perf.py capturar --fase antes` (en modo riguroso, también `--fase control`). Muestra la ficha y el plan, y espera **una** aprobación.
