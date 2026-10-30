# Dominio: back-end, APIs, cloud y DevOps

Mapa para diseñar planes y enseñar desarrollo del lado del servidor y su operación. Revisa el lenguaje, el framework, la versión del runtime y cómo se despliega el proyecto antes de enseñar detalles.

## Mapa de competencias

### 🟢 Básico
- **HTTP**: métodos, códigos de estado, cabeceras, idempotencia, cookies, caché.
- **APIs REST** básicas con JSON.
- **Un stack**: Node.js (Express o Fastify), Python (FastAPI), JVM (Spring Boot o Ktor) o Go.
- Rutas, controladores, validación de entrada, manejo de errores y logging.
- SQL básico y acceso a datos desde código.
- Configuración con variables de entorno; Git; Docker básico.

### 🟡 Intermedio
- **Diseño de APIs**: recursos, paginación, filtros, versionado, errores con Problem Details (RFC 9457), OpenAPI.
- **Autenticación y autorización**: sesiones, JWT bien usados, OAuth 2.0 y OpenID Connect con un proveedor, control de acceso por roles y por recurso.
- **Datos**: ORM, migraciones, transacciones, pools de conexiones, problema N+1.
- **Arquitectura**: capas, hexagonal (puertos y adaptadores), inyección de dependencias (Spring, NestJS).
- **Concurrencia del runtime**: event loop (Node), hilos virtuales (Java 21+), asyncio (Python), goroutines (Go).
- **Asincronía**: tareas en segundo plano y colas.
- **Caché** con Redis (cache-aside, TTL, invalidación).
- **Testing**: unitarios, integración con Testcontainers, tests de contrato.
- **Entrega**: Docker Compose, CI con GitHub Actions, despliegue en un PaaS (incluidos autoalojados como Dokploy).

### 🟠 Avanzado
- **Escalabilidad**: servicios sin estado, balanceo, réplicas, particionado.
- **Mensajería**: Kafka o RabbitMQ, garantías de entrega, idempotencia, patrón outbox, sagas.
- **Resiliencia**: timeouts, reintentos con backoff y jitter, circuit breaker, bulkheads, rate limiting.
- **Observabilidad**: OpenTelemetry (trazas, métricas y logs), SLI/SLO, alertas.
- **Rendimiento**: profiling, consultas lentas, colas de conexiones, backpressure.
- **Otros estilos de API**: gRPC, GraphQL, webhooks, WebSockets y SSE.
- **Seguridad**: OWASP API Security Top 10, gestión de secretos, mTLS, SSRF.
- **Operación**: Kubernetes básico, infraestructura como código, despliegues blue/green y canary, migraciones sin downtime.

### 🔴 Experto
- Sistemas distribuidos: CAP y PACELC, consistencia, consenso a alto nivel.
- Monolito modular frente a microservicios; event sourcing y CQRS.
- Arquitecturas multirregión, recuperación ante desastres.
- Plataformas internas, planificación de capacidad y costes.
- Gestión de incidentes y postmortems.

## Rutas típicas

- **Diseño de APIs REST**: HTTP a fondo → modelado de recursos → verbos e idempotencia → errores → paginación y filtros → versionado → OpenAPI → seguridad → caché → pruebas de contrato → proyecto.
- **Spring Boot**: Java/Kotlin moderno → arranque y configuración → controladores → validación → persistencia con JPA → transacciones → seguridad (Spring Security) → testing → observabilidad → contenedores → proyecto.
- **Node.js con NestJS o Fastify**: event loop → TypeScript en servidor → rutas y validación → capas y DI → base de datos y migraciones → autenticación → colas → testing → despliegue.
- **FastAPI**: tipado con Pydantic → rutas y dependencias → asincronía → base de datos → autenticación → tests → despliegue.
- **Autenticación en APIs**: sesiones frente a tokens → contraseñas → JWT (firma, expiración, rotación) → OAuth 2.0 y OIDC → PKCE → refresh tokens → autorización → passkeys → auditoría.
- **Mensajería y eventos**: comunicación síncrona frente a asíncrona → colas y topics → garantías de entrega → idempotencia → outbox → sagas → observabilidad de flujos.
- **Observabilidad**: logs estructurados → métricas → trazas distribuidas → OpenTelemetry → SLO y alertas → depuración de incidentes.
- **Docker y despliegue**: imágenes y capas → Dockerfile multi-stage → Compose → variables y secretos → CI → despliegue en PaaS o VPS → proxy inverso y TLS → backups → monitorización.

## Ideas erróneas frecuentes

- «REST es JSON sobre HTTP» → implica recursos, semántica de HTTP, idempotencia y caché.
- «JWT es una sesión segura sin estado» → revocarlo es difícil; a menudo una sesión con cookie es mejor opción.
- «Microservicios desde el primer día» → suele convenir un monolito modular y dividir cuando haya motivos.
- «Los reintentos siempre ayudan» → sin idempotencia y backoff con jitter pueden causar tormentas de reintentos.
- «Entrega exactly-once» → en la práctica, at-least-once más consumidores idempotentes.
- «Más hilos, más rendimiento» → depende de si la carga es de E/S o de CPU; hay contención.
- «Con logs basta» → sin métricas ni trazas no se ve el sistema completo.
- «La validación del front es suficiente» → el servidor valida siempre.

## Decisiones que el estudiante debe saber argumentar

- REST, GraphQL o gRPC.
- Sesiones o tokens; proveedor de identidad propio o gestionado.
- ORM o SQL explícito.
- Cola, stream o llamada síncrona.
- Monolito modular o microservicios.
- PaaS, VPS autoalojado, contenedores gestionados o Kubernetes.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- Spring Boot 4 y Spring Framework 7 (noviembre de 2025); Java 25 es la LTS más reciente y los hilos virtuales están disponibles desde Java 21.
- Python 3.14 (octubre de 2025) incluye el build sin GIL (free-threaded) como opción soportada.
- Las versiones actuales de Node.js pueden ejecutar TypeScript eliminando los tipos (type stripping), con limitaciones: verifica en la documentación de la versión usada.
- RFC 9457 sustituye a RFC 7807 para los errores Problem Details.
- OpenTelemetry es el estándar de facto de instrumentación.
- Express 5 es la versión estable actual de Express.

## Ideas de práctica

- API de pedidos con OpenAPI, validación, paginación, errores RFC 9457 y tests de integración con Testcontainers.
- Autenticación con OIDC y un proveedor gestionado, más autorización por recurso.
- Procesamiento asíncrono con cola, reintentos e idempotencia.
- Instrumentar un servicio con OpenTelemetry y definir un SLO.
- Pipeline de CI/CD que construye una imagen y la despliega en un PaaS autoalojado.
