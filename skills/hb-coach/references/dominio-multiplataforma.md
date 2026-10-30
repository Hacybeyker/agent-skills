# Dominio: desarrollo multiplataforma (KMP/CMP, Flutter, React Native)

Mapa para diseñar planes y enseñar desarrollo móvil multiplataforma. Combínalo con `dominio-android.md` y `dominio-ios.md` cuando el tema toque código nativo.

## Mapa de competencias

### 🟢 Básico
- **Conceptos**: compartir lógica frente a compartir UI; renderizado propio frente a componentes nativos; cuándo conviene cada enfoque.
- **Opciones**: Kotlin Multiplatform (KMP) y Compose Multiplatform (CMP), Flutter (Dart), React Native con Expo (TypeScript), .NET MAUI (C#), web y PWA.
- **Estructura** de un proyecto de cada opción, hot reload, ejecución en emulador y simulador.
- **Lenguaje** de la opción elegida (Kotlin, Dart o TypeScript) a nivel básico.

### 🟡 Intermedio
- **KMP**: source sets (`commonMain`, `androidMain`, `iosMain`), `expect`/`actual`, librerías multiplataforma (Ktor, kotlinx.serialization, kotlinx.coroutines, SQLDelight o Room, DataStore), DI (Koin o manual), exposición de APIs a Swift y consumo de corrutinas desde iOS.
- **CMP**: UI compartida con Compose, recursos, navegación, interop con vistas nativas.
- **Flutter**: widgets, `StatelessWidget`/`StatefulWidget`, gestión de estado (Provider, Riverpod, Bloc), navegación (go_router), llamadas HTTP, platform channels, paquetes de pub.dev.
- **React Native**: componentes y hooks, navegación (React Navigation o Expo Router), estado y datos remotos, módulos nativos, Expo y EAS Build.
- **Testing** propio de cada opción.

### 🟠 Avanzado
- **Arquitectura compartida**: qué compartir y qué no, capas, límites con el código nativo.
- **Rendimiento**: memoria y tiempos de compilación de Kotlin/Native, Impeller en Flutter, Nueva Arquitectura de React Native (JSI, Fabric, Turbo Modules).
- **Interop con iOS**: Swift export (experimental), APIs amigables para Swift, integración con Xcode y SPM.
- **Integración gradual**: KMP dentro de apps nativas existentes, add-to-app en Flutter, brownfield en React Native.
- **Entrega**: CI para ambas plataformas, firma, publicación en ambas tiendas.
- **UX nativa**: accesibilidad, gestos, convenciones de cada plataforma.

### 🔴 Experto
- Estrategia de adopción en equipos y organizaciones.
- SDKs multiplataforma publicados como librerías.
- Migraciones entre tecnologías y mantenimiento a largo plazo.
- Evaluación de costes totales frente a dos apps nativas.

## Rutas típicas

- **KMP para compartir lógica**: por qué KMP → estructura y source sets → `expect`/`actual` frente a interfaces → red con Ktor → serialización → persistencia multiplataforma → DI → consumo desde Android → consumo desde iOS (Swift, corrutinas) → testing → integración en apps existentes → proyecto.
- **Compose Multiplatform**: Compose común → recursos → navegación → estado y ViewModel → interop con UIKit/SwiftUI → rendimiento en iOS → publicación.
- **Flutter desde cero**: Dart → widgets → layout → estado → navegación → red y JSON → persistencia → platform channels → testing → rendimiento → publicación.
- **React Native con Expo**: TypeScript y React → componentes nativos → navegación → datos remotos → almacenamiento → módulos nativos → Nueva Arquitectura → EAS Build → publicación.
- **Elegir tecnología**: requisitos → matriz de decisión (equipo, UI, rendimiento, acceso nativo, madurez) → prototipo comparativo → decisión documentada en un ADR.

## Ideas erróneas frecuentes

- «Multiplataforma significa escribir una vez y olvidarse» → siempre hay código, pruebas y UX específicos de cada plataforma.
- «KMP obliga a compartir la UI» → puede compartir solo la lógica y mantener UI nativa.
- «Flutter usa los componentes nativos» → dibuja su propia UI con su motor de renderizado.
- «React Native usa un bridge lento» → la Nueva Arquitectura comunica JavaScript y nativo mediante JSI.
- «`expect`/`actual` para todo» → suele ser mejor una interfaz en `commonMain` con implementaciones inyectadas.
- «Las corrutinas de Kotlin se usan igual desde Swift» → requieren adaptación a `async/await` o a flujos de Swift.

## Decisiones que el estudiante debe saber argumentar

- Compartir solo lógica (KMP) o también UI (CMP, Flutter, React Native).
- Room o SQLDelight en KMP; Riverpod o Bloc en Flutter; Expo gestionado o proyecto nativo en React Native.
- Qué parte de la app se queda nativa (pagos, cámara, widgets, accesibilidad avanzada).
- Coste de mantener dos apps nativas frente a una base compartida.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- Compose Multiplatform para iOS es estable desde la versión 1.8.0 (mayo de 2025).
- Google recomienda KMP para compartir lógica entre Android e iOS, y varias librerías de Jetpack (Room, DataStore, ViewModel, Lifecycle) tienen soporte multiplataforma.
- Swift export de Kotlin sigue marcado como experimental: verifica su estado.
- React Native 0.82 funciona solo con la Nueva Arquitectura; la arquitectura antigua ya no se puede activar.
- Impeller es el motor de renderizado por defecto de Flutter en iOS y Android.
- Xamarin dejó de tener soporte en mayo de 2024; su sucesor es .NET MAUI.
- CocoaPods trunk pasa a solo lectura el 2 de diciembre de 2026: las dependencias iOS de proyectos multiplataforma deben migrar a Swift Package Manager.

## Ideas de práctica

- Módulo KMP con cliente Ktor y caché local, consumido por una app Android y otra iOS.
- Pantalla compartida con CMP embebida en una app nativa.
- App Flutter con Riverpod, go_router y un platform channel propio.
- App Expo con un módulo nativo sencillo y build con EAS.
- ADR comparando dos tecnologías para un caso real.
