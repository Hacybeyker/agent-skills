# Proyecto de ejemplo

## Comandos

- `./gradlew :app:assembleDebug`

## Rendimiento

- applicationId: com.example.app
- Instalar el build de profiling: `ANDROID_SERIAL=emulator-5554 ./gradlew :app:installProfiling`
- Secciones: SCREEN, NAV, HTTP, QUEUE, CONN y TTFB
- Herramienta de IA: Claude Code
- setup listo

<!-- hb-performance:estado -->
- Estado del setup (lo mantiene `perf.py`: no lo edites): instrumentación en el repo: no (está en el parche: `perf.py setup --reponer` la repone) · prueba de humo: pasó el 2099-01-01 · secciones HTTP: sí (prueba de humo, 2099-01-01) · hb-performance 0.14.0
- Setup: en parche `herramientas/perf-setup-0.14.0-20990101-1200.patch` (lo repone y lo quita `perf.py setup`; su ficha está junto al parche)
<!-- /hb-performance:estado -->

## DoD

1. `true`

## Git

- Conventional Commits
