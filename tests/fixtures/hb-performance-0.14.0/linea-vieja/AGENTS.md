# Proyecto de ejemplo

## Comandos

- `./gradlew :app:assembleDebug`

## Rendimiento

- applicationId: com.example.app
- Instalar el build de profiling: `ANDROID_SERIAL=emulator-5554 ./gradlew :app:installProfiling`
- Secciones: SCREEN, NAV, HTTP, QUEUE, CONN y TTFB
- Herramienta de IA: Claude Code
- Setup listo, en parche: `git apply herramientas/perf-setup.patch` antes de medir

<!-- hb-performance:estado -->
- Estado del setup (lo mantiene `perf.py`: no lo edites): instrumentación en el repo: no (no encontré PerfHooks.kt) · prueba de humo: pasó el 2099-01-01 · secciones HTTP: sí (prueba de humo, 2099-01-01) · hb-performance 0.13.0
<!-- /hb-performance:estado -->

## DoD

1. `true`

## Git

- Conventional Commits
