# Dominio: iOS (Swift, SwiftUI, UIKit)

Mapa para diseñar planes y enseñar desarrollo iOS nativo. Revisa el `deployment target`, la versión de Swift y de Xcode del proyecto antes de enseñar APIs concretas: muchas dependen de la versión de iOS.

## Mapa de competencias

### 🟢 Básico
- **Swift**: tipos de valor y de referencia (`struct`/`class`), opcionales, `enum` con valores asociados, protocolos, extensiones, closures, genéricos básicos, errores (`throws`, `do/catch`, `Result`), colecciones.
- **Xcode**: proyectos, targets, schemes, simulador, depurador (LLDB), previews.
- **SwiftUI**: vistas y modificadores, stacks, `List`, formularios, `@State`, `@Binding`, `NavigationStack`.
- **App**: ciclo de vida (`App`, `Scene`), Info.plist, textos de permisos.
- **Red y datos**: `URLSession` con `async/await`, `Codable`, `UserDefaults`/`@AppStorage`, archivos.

### 🟡 Intermedio
- **Concurrencia**: `async/await`, `Task` y el modificador `.task`, `TaskGroup`, cancelación, actores, `@MainActor`, `Sendable`, `AsyncSequence`/`AsyncStream`.
- **Flujo de datos**: Observation (`@Observable`, `@Bindable`), `@Environment`, propiedad del estado.
- **Arquitectura**: MVVM con SwiftUI, capas, repositorios, inyección de dependencias por inicializador o entorno, navegación basada en estado.
- **Persistencia**: SwiftData (modelos, relaciones, consultas) y Core Data.
- **UIKit**: Auto Layout, ciclo de vida de `UIViewController`, interop (`UIViewRepresentable`, `UIHostingController`).
- **Paquetes**: Swift Package Manager y modularización con paquetes locales.
- **Testing**: Swift Testing (`@Test`, `#expect`), XCTest, UI tests, dobles de prueba con protocolos.
- **Calidad**: accesibilidad (VoiceOver, Dynamic Type), localización con String Catalogs, Keychain para secretos.

### 🟠 Avanzado
- **Swift 6**: concurrencia estricta, aislamiento, migración por módulos, *approachable concurrency*.
- **Rendimiento**: Instruments (Time Profiler, Allocations, Leaks, SwiftUI), identidad y dependencias en SwiftUI, vistas perezosas.
- **Memoria**: ARC, ciclos de retención, `weak`/`unowned`, capturas en closures.
- **Seguridad**: CryptoKit, control de acceso del Keychain, App Transport Security, App Attest y DeviceCheck, Data Protection.
- **Sistema**: BackgroundTasks, notificaciones push (APNs), WidgetKit, App Intents, Live Activities.
- **Lenguaje avanzado**: `some` y `any`, genéricos avanzados, macros, result builders, property wrappers.
- **Entrega**: firma y aprovisionamiento, TestFlight, App Store Connect, Xcode Cloud o fastlane.
- **Alternativas de arquitectura**: The Composable Architecture (comunitaria).

### 🔴 Experto
- Arquitectura modular a escala y tiempos de compilación.
- Diseño de frameworks y APIs públicas, library evolution.
- Rendimiento en producción (MetricKit, hitches).
- Interoperabilidad Swift/C++ y consumo de módulos Kotlin Multiplatform.
- Aprendizaje automático en el dispositivo (Core ML, Foundation Models).

## Rutas típicas

- **Swift Concurrency**: problemas de los callbacks → `async/await` → `Task` y cancelación → concurrencia estructurada → actores y aislamiento → `@MainActor` y UI → `Sendable` → `AsyncSequence` → migración a Swift 6 → testing → proyecto.
- **SwiftUI desde cero**: declarativo frente a imperativo → vistas y modificadores → estado y bindings → listas y navegación → Observation → entorno → animaciones → accesibilidad → rendimiento → interop con UIKit → proyecto.
- **Persistencia con SwiftData**: modelado → contenedor y contexto → consultas → relaciones → migraciones → concurrencia → tests → sincronización con iCloud.
- **Arquitectura iOS**: responsabilidades de una vista → MVVM con Observation → repositorios y DI → navegación basada en estado → módulos con SPM → testing por capas → comparativa con TCA.
- **Testing**: Swift Testing → parametrización → asincronía → dobles de prueba → UI tests → snapshots (comunitario) → CI.
- **Seguridad en iOS**: modelo de seguridad → Keychain → CryptoKit → ATS y red → autenticación (passkeys con AuthenticationServices, biometría) → App Attest → OWASP MASVS.

## Ideas erróneas frecuentes

- «`ObservableObject` y `@StateObject` son lo moderno» → desde iOS 17 se usa `@Observable`, y la vista que posee el modelo lo guarda con `@State`.
- «`async` significa otro hilo» → el aislamiento decide dónde se ejecuta; `await` marca puntos de suspensión.
- «`Task { }` en cualquier sitio está bien» → no es estructurado; en vistas usa `.task`, que se cancela solo.
- «`DispatchQueue.main.async` equivale a `@MainActor`» → `@MainActor` lo comprueba el compilador.
- «Copiar structs es caro» → las colecciones usan copy-on-write.
- «`unowned` es más seguro que `weak`» → si el objeto se liberó, la app se cierra.
- «`UserDefaults` sirve para tokens» → los secretos van al Keychain.
- «`NavigationView` sigue siendo la opción» → `NavigationStack` y `NavigationSplitView`.
- «SwiftUI sustituye por completo a UIKit» → la interop sigue siendo necesaria en muchos casos.

## Decisiones que el estudiante debe saber argumentar

- SwiftUI o UIKit (y cuándo combinarlos).
- SwiftData o Core Data (o SQLite con una librería).
- MVVM, TCA o una arquitectura propia.
- Swift Package Manager frente a otros gestores.
- Nivel de concurrencia estricta y estrategia de migración a Swift 6.
- Qué va en el Keychain, qué en archivos protegidos y qué en `UserDefaults`.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- Swift 6 con modo de lenguaje Swift 6 y concurrencia estricta; existe una guía oficial de migración.
- Observation (`@Observable`) y SwiftData requieren iOS 17 o superior.
- Swift Testing viene incluido desde Xcode 16.
- CryptoKit incorpora algoritmos poscuánticos (ML-KEM y ML-DSA) desde iOS 26.
- CocoaPods trunk pasa a solo lectura el 2 de diciembre de 2026: prefiere Swift Package Manager.
- Xcode 26.3 o superior integra agentes (Claude Agent y Codex) que pueden usar skills.
- Consulta las novedades de la WWDC más reciente antes de enseñar APIs de la última versión de iOS.

## Ideas de práctica

- Lista con búsqueda y detalle usando `@Observable`, `NavigationStack` y una API real.
- Migrar un módulo con callbacks a `async/await` y activar la concurrencia estricta.
- Persistencia offline con SwiftData y tests con Swift Testing.
- Guardar credenciales en el Keychain con control de acceso biométrico.
- Widget con WidgetKit que comparta datos con la app.
- Perfilar una lista lenta con Instruments y corregirla.
