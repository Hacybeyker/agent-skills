# Dominio: bases de datos y persistencia

Mapa para diseñar planes y enseñar bases de datos en servidor y persistencia en móvil. Revisa el motor, la versión y la herramienta de migraciones del proyecto antes de enseñar detalles.

## Mapa de competencias

### 🟢 Básico
- Modelo relacional: tablas, filas, claves primarias y foráneas, tipos de datos.
- SQL: `SELECT`, `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY`, subconsultas, `INSERT`/`UPDATE`/`DELETE`.
- Normalización (1FN a 3FN) y cuándo desnormalizar.
- Índices: qué son y por qué aceleran lecturas.
- Consultas parametrizadas (prevención de inyección SQL).
- Visión general de NoSQL: documentos, clave-valor, columnas, grafos.
- Persistencia móvil básica: Room (Android), SwiftData (iOS), preferencias clave-valor.

### 🟡 Intermedio
- **Modelado**: diagramas entidad-relación, relaciones N:M, claves naturales frente a sustitutas.
- **Índices**: compuestos y orden de columnas, selectividad, índices parciales, `EXPLAIN`.
- **Transacciones**: ACID, niveles de aislamiento y sus anomalías, bloqueos.
- **Evolución**: migraciones versionadas (Flyway, Liquibase, Prisma, Room).
- **Acceso desde código**: ORM y problema N+1, pools de conexiones, paginación por offset frente a keyset.
- **Tipos avanzados**: JSON/JSONB, búsqueda de texto completo.
- **Caché**: Redis con cache-aside, TTL e invalidación.
- **Operación**: copias de seguridad y restauración.

### 🟠 Avanzado
- **Rendimiento**: planes de ejecución, estadísticas, particionado, MVCC y mantenimiento (vacuum).
- **Concurrencia**: deadlocks, bloqueo optimista frente a pesimista, `SELECT … FOR UPDATE SKIP LOCKED`.
- **Distribución**: replicación y retraso de réplicas, sharding, CAP y PACELC, consistencia eventual.
- **NoSQL por patrones de acceso**: diseño de documentos y claves en MongoDB o DynamoDB.
- **Integración**: CDC, patrón outbox, colas sobre base de datos.
- **Migraciones sin downtime**: expandir y contraer.
- **Móvil offline-first**: sincronización, resolución de conflictos, CRDT a nivel conceptual.

### 🔴 Experto
- Elegir motores con criterio para cada carga de trabajo.
- Alta disponibilidad y recuperación ante desastres (RPO y RTO).
- Multi-tenant: aislamiento por esquema, por base de datos o por filas (RLS).
- Seguridad de datos: cifrado, auditoría, enmascaramiento.
- Rendimiento a gran escala y planificación de capacidad.

## Rutas típicas

- **SQL con PostgreSQL**: modelo relacional → consultas básicas → joins → agregaciones → subconsultas y CTE → índices → transacciones → funciones de ventana → JSONB → rendimiento con `EXPLAIN` → proyecto.
- **Modelado de datos**: requisitos → entidades y relaciones → normalización → restricciones → casos de desnormalización → evolución del esquema.
- **Índices y rendimiento**: cómo lee el motor → tipos de índices → índices compuestos → planes de ejecución → consultas lentas → pools y N+1 → particionado.
- **Transacciones y concurrencia**: ACID → aislamiento y anomalías → bloqueos → MVCC → deadlocks → patrones de reintento.
- **Room (Android)**: entidades y DAO → consultas con Flow → relaciones → migraciones → tests → repositorio offline-first → Room en KMP.
- **SwiftData (iOS)**: modelos → contexto → consultas → relaciones → migraciones → concurrencia → sincronización.
- **Redis y caché**: estructuras de datos → patrones de caché → invalidación → expiración → colas y pub/sub → persistencia.
- **MongoDB**: documentos → modelado por patrones de acceso → índices → agregaciones → transacciones → réplicas y sharding.

## Ideas erróneas frecuentes

- «Un índice por columna acelera todo» → encarece las escrituras; importan la selectividad y el orden en índices compuestos.
- «NoSQL escala y SQL no» → los motores relacionales escalan mucho; lo decisivo es el modelado y la carga.
- «Con un ORM no hace falta saber SQL» → los problemas de rendimiento se diagnostican en SQL.
- «`OFFSET` sirve para paginar tablas grandes» → se degrada; usa paginación por keyset.
- «Serializable siempre, por seguridad» → tiene coste y obliga a reintentar.
- «UUID v4 como clave primaria no tiene coste» → fragmenta los índices; valora UUIDv7 o secuencias.
- «La caché soluciona el rendimiento» → añade problemas de invalidación y consistencia.
- «Tenemos backups» → solo si se ha probado la restauración.

## Decisiones que el estudiante debe saber argumentar

- Relacional, documental o clave-valor para un caso concreto.
- Normalizar o desnormalizar.
- ORM, query builder o SQL explícito.
- Room o SQLDelight en KMP; SwiftData o Core Data en iOS.
- Estrategia de migraciones y compatibilidad hacia atrás.
- Nivel de aislamiento y estrategia de concurrencia.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- PostgreSQL 18 (septiembre de 2025) añade E/S asíncrona y la función `uuidv7()`.
- Room tiene soporte para Kotlin Multiplatform.
- Room, SQLDelight, Core Data y SwiftData se apoyan en SQLite.
- Redis 8 ofrece la licencia AGPLv3 como opción; Valkey es un fork bajo la Linux Foundation.

## Ideas de práctica

- Diseñar el esquema de una app de pedidos con migraciones y datos de prueba.
- Detectar y corregir una consulta lenta con `EXPLAIN ANALYZE`.
- Reproducir una anomalía de concurrencia y resolverla con el nivel de aislamiento o bloqueo adecuado.
- Caché cache-aside con invalidación por eventos.
- Repositorio móvil offline-first con sincronización y resolución de conflictos.
