---
tema: "Hilt: inyección de dependencias en Android"
slug: hilt
---

# Dudas resueltas · Hilt: inyección de dependencias en Android

## 2026-09-15 · ¿`by lazy` en el contenedor es seguro entre hilos?

- **Contexto:** `AppContainer` en `:app`, durante la revisión de la práctica 1.2.
- **Respuesta corta:** Sí. Por defecto `lazy` usa `LazyThreadSafetyMode.SYNCHRONIZED`: el valor se calcula una sola vez aunque accedan varios hilos.
- **Explicación:** El comportamiento solo cambia si pasas otro modo. `PUBLICATION` permite que varios hilos calculen el valor, pero todos usan el primero que se publica; `NONE` elimina el bloqueo y solo es seguro si accede un único hilo.
- **Relacionado:** lección 1.2 · término «Contenedor de dependencias»
- **Fuente:** [Lazy properties — Kotlin](https://kotlinlang.org/docs/delegated-properties.html#lazy-properties)
