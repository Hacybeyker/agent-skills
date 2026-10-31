# Rendimiento

Google marca como muy recomendados tres puntos: R8 en modo completo, Baseline/Startup Profiles y Macrobenchmark.

## R8

- Release con minificación y reducción de recursos (`isMinifyEnabled = true`, `isShrinkResources = true`, o el bloque equivalente del DSL de AGP que use el proyecto).
- Modo completo de R8 (es el predeterminado en las versiones actuales de AGP: no lo desactives).
- Reglas `-keep` mínimas y justificadas ([security.md](security.md)).
- **R8 Configuration Analyzer** (AGP 9.3 o superior): `./gradlew :app:analyzeReleaseR8Config` deja un informe en `app/build/reports/r8/` con el porcentaje de clases, campos y métodos que cada keep rule impide optimizar, incluidas las que traen las librerías. No genera el APK, así que el ciclo para ajustar reglas es corto. Para corregirlas, la skill oficial `r8-analyzer`.
- **`android analyze`** (CLI de Android) sobre el APK o AAB de release: ratios de reducción, optimización y ofuscación de R8. Sobre un AAR o JAR, detecta keep rules de paquete completo. Con `--format=json` sirve como control en CI.

## Baseline Profiles y Startup Profiles

- Precompilan los caminos críticos (arranque y pantallas principales): menos tiempo de arranque, menos *jank* y menos ANR.
- Se generan desde un módulo `:baselineprofile` con el plugin `androidx.baselineprofile` y un test que recorre los flujos clave. Se regeneran cuando cambian esos flujos.

## Macrobenchmark

- Un módulo `:benchmark` mide el arranque (TTID y TTFD) y el *jank* de los flujos principales (`StartupTimingMetric`, `FrameTimingMetric`).
- Se ejecuta contra un build parecido a release, en dispositivo físico, para detectar regresiones.

## Compose

- **Estabilidad:** modelos de UI inmutables (`data class` con `val` y colecciones de solo lectura). El compilador ya aplica *strong skipping*. Las clases estables de otros módulos o librerías se declaran en `compose_stability.conf`.
- Para investigar recomposiciones, usa los reportes y métricas del compilador de Compose y el Layout Inspector.
- Lee el estado lo más abajo posible. Para valores que cambian en cada frame (scroll, animaciones), pásalos como lambda (`Modifier.offset { }`, `graphicsLayer { }`), no como valor.
- Cálculos costosos con `remember(claves)`. En listas, `key` y `contentType` ([ui-compose-m3.md](ui-compose-m3.md)).

## Trazas y memoria

- **`androidx.tracing` 2.x** (estable): secciones de traza propias en los caminos críticos (arranque, carga de pantallas), con archivo, línea y argumentos, y trazas de corrutinas conectadas como flujos de Perfetto. Para grabarlas y analizarlas, la skill oficial `android-profiler`.
- **LeakCanary** como `debugImplementation` (versión en el catálogo) para detectar fugas de memoria durante el desarrollo. Nunca en release.

**En espera hasta que sean estables** (no los agregues antes): el tracing de recomposición de Compose 1.13 y Jetpack Keep.

## Arranque y hilo principal

- Nada de I/O ni trabajo pesado en el hilo principal: las funciones `suspend` de `data` cambian de dispatcher.
- Inicializa las librerías de forma diferida cuando no hacen falta al arrancar.
- `StrictMode` activado en debug para detectar accesos a disco o red en el hilo principal.
- En iOS (KMP), el trabajo pesado tampoco va en el hilo principal: usa los mismos dispatchers inyectados.
