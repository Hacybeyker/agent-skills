---
tema: "Hilt: inyección de dependencias en Android"
slug: hilt
area: android
nivel_actual: básico
nivel_objetivo: avanzado
leccion_actual: "1.3"
creado: 2026-09-15
actualizado: 2026-09-15
---

# Plan de estudio · Hilt: inyección de dependencias en Android

> Ejemplo de referencia del Software Coach: muestra el formato y el nivel de detalle esperados. El contexto del proyecto es ficticio.

## Resumen

- **Meta:** diseñar e implementar la inyección de dependencias de una app Android multimódulo con Hilt (scopes, qualifiers, ViewModels, WorkManager y tests) y justificar cada decisión.
- **Por qué importa:** desacopla capas, facilita los tests y hace explícito cuánto vive cada objeto. Hilt es la solución de DI recomendada en la guía de arquitectura de Android.
- **Punto de partida:** usa `@Inject` y `@HiltViewModel` copiando ejemplos, sin un modelo mental de componentes ni scopes.
- **Contexto del proyecto:** app en Kotlin con Jetpack Compose y KSP; módulos `:app`, `:core:data` y `:feature:orders`.
- **Ritmo acordado:** 3 sesiones de 45 minutos por semana.
- **Proyecto final:** migrar `:feature:orders` de DI manual a Hilt, con tests unitarios e instrumentados.

## Diagnóstico

| Pregunta | Resultado | Decisión |
|---|---|---|
| ¿Qué problema resuelve la inyección de dependencias? | Correcta, con ejemplo propio | Convalidar 1.1 |
| ¿En qué se diferencia la inyección por constructor de un service locator? | Parcial | Reforzar en 1.2 |
| ¿Qué indica `@InstallIn(SingletonComponent::class)`? | No la sabía | Módulo 2 sin prisa |
| ¿Cuándo conviene `@Binds` en lugar de `@Provides`? | No la sabía | Lección 2.4 |
| ¿Cuánto vive un objeto inyectado sin anotación de scope? | Incorrecta (respondió «es singleton») | Reforzar en 3.2 |

## Ruta de aprendizaje

### Módulo 1 · Fundamentos de la inyección de dependencias 🟢 Básico

> **Meta del módulo:** reconocer dependencias ocultas y construir un grafo a mano para entender qué automatiza Hilt.

- [x] **1.1 El problema: acoplamiento y dependencias ocultas** — Identificar por qué crear dependencias dentro de una clase dificulta cambiarla y probarla. (convalidada)
  - Objetivo: explicar con un ejemplo propio qué es una dependencia y qué es la inversión de control.
  - Práctica: localizar tres clases del proyecto que crean sus propias dependencias.
  - Dominio: respondió bien las preguntas del diagnóstico con ejemplos propios.
- [x] **1.2 DI manual: constructor, contenedor y fábricas** — Construir el grafo de dependencias a mano con un contenedor de aplicación.
  - Objetivo: implementar un `AppContainer` y distinguir DI de service locator.
  - Práctica: crear el contenedor manual de `OrdersRepository` en `:feature:orders`.
  - Dominio: el ViewModel recibe sus dependencias por constructor y existe un test con un fake.
- [ ] **1.3 De DI manual a Dagger: grafo y código generado** — Entender qué genera el compilador y por qué los errores aparecen al compilar.
  - Objetivo: describir binding, grafo y componente, y el papel de KSP.
  - Práctica: provocar y leer un error de binding faltante.
  - Dominio: explica un error `[Dagger/MissingBinding]` y cómo resolverlo.

### Módulo 2 · Primeros pasos con Hilt 🟢 Básico

> **Meta del módulo:** que Hilt construya el grafo de la app y de sus pantallas.

- [ ] **2.1 Configurar Hilt con KSP** — Añadir el plugin, las dependencias y `@HiltAndroidApp`.
  - Objetivo: configurar Hilt en el catálogo de versiones y solo en los módulos que lo necesitan.
  - Práctica: habilitar Hilt en `:app` y compilar.
  - Dominio: la app compila y arranca con `@HiltAndroidApp`.
- [ ] **2.2 Puntos de entrada con `@AndroidEntryPoint`** — Inyectar en Activities y Fragments y entender la jerarquía de componentes.
  - Objetivo: explicar por qué una clase de Android necesita ser punto de entrada.
  - Práctica: convertir `MainActivity` en punto de entrada.
  - Dominio: identifica qué componente atiende a cada punto de entrada.
- [ ] **2.3 Inyección por constructor con `@Inject`** — Dejar que Hilt construya las clases propias.
  - Objetivo: anotar constructores y seguir la cadena de dependencias.
  - Práctica: anotar `OrdersRepositoryImpl` y sus dependencias.
  - Dominio: el grafo compila sin el contenedor manual.
- [ ] **2.4 Módulos: `@Module`, `@InstallIn`, `@Provides` y `@Binds`** — Enseñar a Hilt a crear interfaces y tipos de terceros como Retrofit o Room.
  - Objetivo: elegir entre `@Provides` y `@Binds` con criterio.
  - Práctica: crear `NetworkModule` y `DataModule`.
  - Dominio: justifica cada binding y su componente.
- [ ] **2.5 ViewModels con `@HiltViewModel` y `hiltViewModel()`** — Inyectar ViewModels en Compose y usar `SavedStateHandle`.
  - Objetivo: obtener ViewModels inyectados desde un composable.
  - Práctica: migrar `OrdersViewModel` a `@HiltViewModel`.
  - Dominio: la pantalla funciona sin fábricas manuales.

### Módulo 3 · Componentes, scopes y qualifiers 🟡 Intermedio

> **Meta del módulo:** decidir cuánto vive cada objeto y distinguir implementaciones del mismo tipo.

- [ ] **3.1 Componentes y ciclo de vida** — Relacionar cada componente de Hilt con el ciclo de vida de Android.
- [ ] **3.2 Scopes: `@Singleton`, `@ActivityRetainedScoped` y `@ViewModelScoped`** — Elegir el scope mínimo necesario y conocer su coste.
- [ ] **3.3 Qualifiers para varias implementaciones** — Distinguir dos instancias del mismo tipo con `@Qualifier`.
- [ ] **3.4 Creación diferida con `Provider` y `Lazy`** — Retrasar o repetir la creación de objetos.

### Módulo 4 · Integraciones con Jetpack 🟡 Intermedio

> **Meta del módulo:** inyectar dependencias en las piezas de Jetpack que no se crean con un constructor normal.

- [ ] **4.1 Inyección asistida con `@AssistedInject`** — Combinar parámetros de ejecución con dependencias del grafo.
- [ ] **4.2 WorkManager con `@HiltWorker`** — Inyectar dependencias en Workers.
- [ ] **4.3 Navigation Compose y ViewModels por destino** — Acotar ViewModels a destinos y grafos de navegación.
- [ ] **4.4 `@EntryPoint` para clases que Hilt no controla** — Obtener dependencias desde clases del sistema.

### Módulo 5 · Testing con Hilt 🟠 Avanzado

> **Meta del módulo:** probar con dependencias sustituibles sin perder velocidad.

- [ ] **5.1 Tests instrumentados con `@HiltAndroidTest`** — Configurar `HiltAndroidRule` y un runner de test propio.
- [ ] **5.2 Sustituir bindings: `@TestInstallIn`, `@UninstallModules` y `@BindValue`** — Reemplazar implementaciones reales por fakes.
- [ ] **5.3 Tests unitarios sin Hilt** — Probar clases con inyección por constructor sin levantar el grafo.

### Módulo 6 · Arquitectura y rendimiento 🟠 Avanzado

> **Meta del módulo:** usar Hilt con criterio en un proyecto grande.

- [ ] **6.1 Hilt en proyectos multimódulo** — Ubicar los módulos de Hilt por capa y controlar la visibilidad.
- [ ] **6.2 Coste en arranque y en compilación** — Medir el impacto de los scopes y del procesamiento con KSP.
- [ ] **6.3 Hilt frente a Koin y a la DI manual** — Comparar trade-offs y decidir con argumentos.

### Módulo 7 · Proyecto final 🔴 Experto

> **Meta del módulo:** demostrar dominio con una migración real.

- [ ] **7.1 Diseño de la DI de `:feature:orders`** — Diagrama de componentes, scopes y qualifiers, con cada decisión justificada.
- [ ] **7.2 Migración paso a paso** — Pasar el módulo de DI manual a Hilt sin romper la app.
- [ ] **7.3 Tests y defensa del diseño** — Cubrir el módulo con tests y explicar el grafo.

## Proyecto final

Migrar `:feature:orders` de DI manual a Hilt.

- **Requisitos:** repositorio enlazado con `@Binds`; dos `OkHttpClient` distinguidos con qualifiers; `OrdersViewModel` con `SavedStateHandle`; un Worker de sincronización con `@HiltWorker`.
- **Tests:** un test instrumentado que sustituya el repositorio por un fake con `@TestInstallIn` y tests unitarios del ViewModel sin Hilt.
- **Criterios de evaluación:** compila sin bindings sobrantes, cada scope está justificado por escrito y el estudiante explica el grafo con un diagrama.

## Recursos oficiales

- [Inyección de dependencias con Hilt](https://developer.android.com/training/dependency-injection/hilt-android) — guía principal de Android.
- [Inyección de dependencias manual](https://developer.android.com/training/dependency-injection/manual) — base del módulo 1.
- [Hilt y otras bibliotecas de Jetpack](https://developer.android.com/training/dependency-injection/hilt-jetpack) — ViewModel, Navigation, Compose y WorkManager.
- [Guía de testing con Hilt](https://developer.android.com/training/dependency-injection/hilt-testing) — tests instrumentados y con Robolectric.
- [Documentación de Hilt en dagger.dev](https://dagger.dev/hilt/) — referencia de anotaciones y componentes.
- [Notas de versión de androidx.hilt](https://developer.android.com/jetpack/androidx/releases/hilt) — cambios de API por versión.

## Huecos abiertos

| Hueco | Detectado | Intentos | Próximo repaso | Estado |
|---|---|---|---|---|
| Pasar el contenedor entero en lugar de la dependencia | 1.2 (2026-09-15) | 2 | 2026-09-17 | abierto |
| Cuánto vive un objeto inyectado sin scope | Diagnóstico (2026-09-15) | 1 | 2026-09-22 (refuerzo en 3.2) | abierto |
| Diferencia entre inyección por constructor y service locator | Diagnóstico (2026-09-15) | 2 | — | cerrado 2026-09-15 |

## Bitácora

| Fecha | Lecciones | Logros | Próximo paso |
|---|---|---|---|
| 2026-09-15 | — | Plan creado tras un diagnóstico de 5 preguntas | Lección 1.2 |
| 2026-09-15 | 1.1 (convalidada), 1.2 | Construyó `AppContainer` y un test con fake | Lección 1.3: qué genera Dagger |
