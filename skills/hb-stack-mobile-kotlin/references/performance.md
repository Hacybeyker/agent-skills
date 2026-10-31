# Rendimiento

Google marca como muy recomendados tres puntos: R8 en modo completo, Baseline/Startup Profiles y Macrobenchmark.

## R8

- Release con minificación y reducción de recursos (`isMinifyEnabled = true`, `isShrinkResources = true`, o el bloque equivalente del DSL de AGP que use el proyecto).
- Modo completo de R8 (es el predeterminado en las versiones actuales de AGP: no lo desactives).
- Reglas `-keep` mínimas y justificadas ([security.md](security.md)).

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

## Arranque y hilo principal

- Nada de I/O ni trabajo pesado en el hilo principal: las funciones `suspend` de `data` cambian de dispatcher.
- Inicializa las librerías de forma diferida cuando no hacen falta al arrancar.
- `StrictMode` activado en debug para detectar accesos a disco o red en el hilo principal.
- En iOS (KMP), el trabajo pesado tampoco va en el hilo principal: usa los mismos dispatchers inyectados.
