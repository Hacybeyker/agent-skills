# Dominio: patrones de diseño y arquitectura de software

Mapa para enseñar a diseñar código y sistemas mantenibles. Enseña siempre con ejemplos en el lenguaje y el proyecto del estudiante: un patrón se entiende por el problema que resuelve, no por su diagrama.

## Mapa de competencias

### 🟢 Básico
- **Principios**: SOLID, DRY, KISS, YAGNI, composición sobre herencia, alta cohesión y bajo acoplamiento.
- **Code smells** y refactorizaciones básicas.
- **Patrones más usados**: Factory, Builder, Adapter, Decorator, Facade, Observer, Strategy, State, Command, Repository; Singleton y sus riesgos.
- **Estilos de presentación**: MVC, MVP y MVVM a nivel conceptual.
- **Capas** y separación de responsabilidades.

### 🟡 Intermedio
- **Catálogo GoF** completo por familias (creacionales, estructurales y de comportamiento) y su versión idiomática moderna (por ejemplo, Strategy como función).
- **Inversión de dependencias** e inyección de dependencias.
- **Arquitecturas de aplicación**: limpia, hexagonal (puertos y adaptadores), cebolla; la regla de dependencias.
- **Móvil**: MVVM y MVI con flujo de datos unidireccional; capas de UI, dominio y datos.
- **Integración**: API Gateway, Backend for Frontend, anti-corruption layer.
- **Documentación**: diagramas C4 y Architecture Decision Records (ADR).
- **Diseño guiado por tests** (TDD) como herramienta de diseño.

### 🟠 Avanzado
- **DDD**: lenguaje ubicuo, bounded contexts, agregados, eventos de dominio, context mapping.
- **Estilos de sistema**: monolito modular, microservicios, arquitectura orientada a eventos.
- **Datos distribuidos**: CQRS, event sourcing, sagas, outbox.
- **Resiliencia**: circuit breaker, reintentos, bulkhead, timeouts.
- **Patrones de nube**: strangler fig, sidecar, colas de carga.
- **Atributos de calidad** y sus trade-offs: rendimiento, disponibilidad, mantenibilidad, seguridad, coste.
- **Arquitectura evolutiva**: fitness functions y decisiones reversibles.

### 🔴 Experto
- Diseño de sistemas de extremo a extremo (capacidad, particionado, consistencia).
- Gobierno de arquitectura, estructura de equipos y ley de Conway.
- Migraciones grandes (strangler fig) y modernización.
- Evaluación de arquitecturas y comunicación de decisiones a distintos públicos.

## Rutas típicas

- **SOLID y código limpio**: code smells → cada principio con un ejemplo roto y su refactor → tests como red de seguridad → refactor de un módulo real.
- **Patrones GoF en tu lenguaje**: por qué existen → creacionales → estructurales → de comportamiento → versión idiomática moderna → cuándo no usarlos → catálogo aplicado a tu proyecto.
- **Clean Architecture en móvil**: regla de dependencias → entidades y casos de uso → repositorios → capa de UI con UDF → DI → testing por capas → cuándo la capa de dominio sobra.
- **MVVM frente a MVI**: responsabilidades → estado único e inmutable → eventos e intents → efectos → testing → elección argumentada.
- **DDD práctico**: descubrir el dominio → lenguaje ubicuo → bounded contexts → agregados e invariantes → eventos de dominio → integración entre contextos.
- **Microservicios y eventos**: monolito modular primero → criterios para separar → comunicación síncrona y asíncrona → consistencia (sagas, outbox) → observabilidad → despliegue.
- **Diseño de sistemas**: requisitos y estimaciones → componentes → datos y particionado → caché → colas → escalabilidad → fiabilidad → práctica tipo entrevista.
- **Documentar arquitectura**: C4 (contexto, contenedores, componentes) → ADR → diagramas en Mermaid dentro del repositorio.

## Ideas erróneas frecuentes

- «Más capas, mejor arquitectura» → cada capa tiene un coste; aplica YAGNI.
- «Clean Architecture son las carpetas domain/data/presentation» → lo esencial es la dirección de las dependencias.
- «Singleton es el patrón para servicios compartidos» → introduce estado global; usa DI con un scope.
- «Aplicar un patrón es copiar el diagrama del libro» → se aplica para resolver fuerzas concretas; los lenguajes modernos simplifican muchos patrones.
- «Microservicios es la arquitectura moderna» → multiplican el coste operativo; empieza por un monolito modular.
- «DDD es poner entidades con un ORM» → empieza por el diseño estratégico (contextos y lenguaje).
- «MVVM y MVI son incompatibles» → MVI es flujo unidireccional con estado único; pueden combinarse.
- «Los casos de uso son obligatorios» → en la guía de Android la capa de dominio es opcional.

## Decisiones que el estudiante debe saber argumentar

- Herencia o composición.
- Capa de dominio sí o no.
- MVVM, MVI u otra variante.
- Monolito modular o microservicios.
- Comunicación síncrona o asíncrona entre componentes.
- Consistencia fuerte o eventual.
- Qué decisiones documentar en un ADR.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- La guía de arquitectura de Android recomienda capas de UI y de datos, con una capa de dominio opcional, flujo de datos unidireccional y una fuente única de verdad.
- C4 y los ADR son prácticas extendidas para documentar arquitectura junto al código.
- El monolito modular se usa cada vez más como punto de partida antes de dividir en servicios.

## Ideas de práctica

- Refactorizar una clase «dios» del proyecto aplicando SOLID con tests previos.
- Implementar Strategy y Decorator en una funcionalidad real y comparar con la versión con funciones.
- Diagrama C4 del proyecto y tres ADR de decisiones pasadas.
- Diseñar los bounded contexts de un dominio conocido (pedidos, pagos, envíos).
- Diseño de sistema tipo entrevista con estimaciones y trade-offs escritos.
