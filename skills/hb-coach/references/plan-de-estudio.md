# Diseño del plan de estudio

Cómo crear y mantener `aprendizaje/<tema>/PLAN.md`. El formato es estricto porque los scripts y el cuaderno lo leen para calcular el progreso.

## Contenido

1. Método: diseño inverso
2. Diagnóstico adaptativo
3. Estructura de la ruta
4. Formato exacto de PLAN.md
5. Lista de control de un buen plan
6. Mantenimiento del plan

## 1. Método: diseño inverso

1. **Meta**: qué podrá hacer el estudiante al terminar, en una frase verificable. Mal: «saber Hilt». Bien: «diseñar e implementar la DI de una app multimódulo con Hilt, con tests, y justificar cada scope».
2. **Evidencias**: qué demostrará que lo logró (proyecto final, preguntas de diseño, tests).
3. **Ruta**: módulos y lecciones que llevan de su punto de partida a esas evidencias, en orden de dependencias conceptuales.

Adapta el plan al proyecto real: las prácticas se hacen en su código siempre que sea posible, y las versiones del plan coinciden con las del proyecto (o se indica el cambio de versión como parte del plan).

## 2. Diagnóstico adaptativo

Antes del diagnóstico, acuerda el método con el estudiante y déjalo escrito en `aprendizaje/METODO.md` (ver SKILL.md). El diagnóstico mide lo que **ya** debería saber: nunca preguntes por el contenido que vas a enseñar en el plan.

**Preguntas de contexto** (3 o 4, con opciones cuando sea posible):

- Experiencia con el tema y con tecnologías vecinas.
- Meta concreta: proyecto, trabajo, entrevista, curiosidad.
- Tiempo disponible por semana y duración preferida de las sesiones.
- Proyecto donde aplicarlo (si no es el actual).

**Preguntas técnicas** (5 a 8, escalonadas):

- 2 de nivel básico, 2 o 3 de intermedio, 1 o 2 de avanzado y, si responde todo bien, 1 de experto.
- Preferentemente abiertas o de «explica por qué», no de memoria.
- Si falla dos seguidas, detén el escalado: ya sabes dónde empezar.
- No enseñes durante el diagnóstico; solo anota. Al final, da un resumen honesto y breve de su punto de partida.

**Decisiones**:

- Pregunta básica bien respondida y con ejemplo propio → convalidar la lección correspondiente.
- Respuesta parcial → mantener la lección, que puede ir en modo exprés.
- Nivel avanzado demostrado → convalidar solo lo conceptual; las prácticas avanzadas requieren evidencia práctica.
- Registra todo en la tabla `## Diagnóstico` y fija `nivel_actual` en el frontmatter.

## 3. Estructura de la ruta

**Niveles** (encabezado de cada módulo):

| Nivel | Emoji | El estudiante… |
|---|---|---|
| Básico | 🟢 | entiende el problema, los conceptos y usa lo esencial con guía. |
| Intermedio | 🟡 | aplica el tema de forma autónoma en casos reales y conoce las alternativas. |
| Avanzado | 🟠 | domina el funcionamiento interno, el rendimiento, el testing y los trade-offs. |
| Experto | 🔴 | diseña soluciones completas, resuelve casos límite y puede enseñarlo (proyecto final). |

**Tamaño**:

- 5 a 9 módulos; 2 a 6 lecciones por módulo.
- Cada lección tiene un único resultado observable y dura entre 20 y 45 minutos.
- Estimación total: número de lecciones × 30–40 minutos. Indícala al presentar el plan.

**Contenido que casi siempre debe aparecer** (cuando aplique al tema):

- el problema que resuelve y las alternativas;
- fundamentos antes que herramientas;
- configuración real en su stack y versiones;
- errores comunes y cómo depurarlos;
- testing;
- seguridad y rendimiento;
- integración con el resto de su arquitectura;
- comparativa o migración desde lo que usa hoy;
- proyecto final que integre todo.

Los mapas `dominio-*.md` tienen rutas típicas por tema; úsalas como punto de partida, no como plantilla rígida.

## 4. Formato exacto de PLAN.md

Parte de la plantilla que crea `coach init` y reemplaza todos los `[[COMPLETAR: …]]`.

### Frontmatter

```yaml
---
tema: "Hilt: inyección de dependencias en Android"   # título visible
slug: hilt                                            # igual que el nombre de la carpeta
area: android                                         # frontend, backend, seguridad, criptografia, bases-de-datos, arquitectura, android, ios, multiplataforma…
nivel_actual: básico                                  # según el diagnóstico
nivel_objetivo: avanzado
leccion_actual: "1.3"                                 # la mantienen los scripts; entre comillas
creado: 2026-09-15
actualizado: 2026-09-15
---
```

Valores con `:` u otros símbolos van entre comillas. No añadas comentarios `#` en tus archivos reales (arriba solo explican los campos).

### Secciones, en este orden

```markdown
# Plan de estudio · <tema>

## Resumen
## Diagnóstico
## Ruta de aprendizaje
### Módulo 1 · <nombre> 🟢 Básico
### Módulo 2 · <nombre> 🟡 Intermedio
...
## Proyecto final
## Recursos oficiales
## Huecos abiertos
## Bitácora
```

### Módulos

```markdown
### Módulo 3 · Componentes, scopes y qualifiers 🟡 Intermedio

> **Meta del módulo:** decidir cuánto vive cada objeto y distinguir implementaciones del mismo tipo.
```

- Encabezado de nivel 3: `### Módulo <n> · <nombre> <emoji> <Nivel>`.
- La cita con la meta del módulo va entre el encabezado y la primera lección.

### Lecciones

```markdown
- [ ] **3.2 Scopes: `@Singleton` y `@ViewModelScoped`** — Elegir el scope mínimo necesario y conocer su coste.
  - Objetivo: explicar qué componente retiene cada instancia y cuándo se destruye.
  - Práctica: revisar los scopes de `:core:data` y justificar cada uno.
  - Dominio: detecta un scope innecesario y mide su efecto.
```

Reglas:

- Línea de lección: `- [ ] **<id> <título>** — <resultado de aprendizaje>`. El id y el título van dentro de las negritas.
- Id `<módulo>.<lección>` (`3.2`). Para insertar entre lecciones existentes usa un subnivel (`3.2.1`); nunca renumeres lecciones ya hechas.
- Completada: `- [x]`. Convalidada: `- [x]` y ` (convalidada)` al final de la línea. Lo hacen los scripts.
- Los detalles (`Objetivo`, `Práctica`, `Dominio`) van como sublista con 2 espacios de sangría. Son obligatorios en los módulos básicos e intermedios y muy recomendables en el resto.
- No uses checkboxes con un id en negrita fuera de la ruta: se contarían como lecciones.
- No hace falta enlazar las notas: el cuaderno las asocia por el id del nombre de archivo.

### Diagnóstico

```markdown
| Pregunta | Resultado | Decisión |
|---|---|---|
| ¿Qué problema resuelve la inyección de dependencias? | Correcta, con ejemplo propio | Convalidar 1.1 |
```

### Proyecto final

Descripción del entregable, requisitos, tests esperados y criterios de evaluación. Suele corresponder al último módulo (🔴 Experto).

### Recursos oficiales

Lista de enlaces con una frase sobre para qué sirve cada uno. Solo fuentes verificadas (ver `fuentes-oficiales.md`).

### Huecos abiertos

Conceptos que fallaron y siguen pendientes de consolidar (protocolo en `pedagogia.md`). La sección existe desde el primer día, aunque esté vacía.

```markdown
| Hueco | Detectado | Intentos | Próximo repaso | Estado |
|---|---|---|---|---|
| Reutilizar un caso de uso en dos pantallas | 3.1 (2026-10-02) | 3 | 2026-10-09 | abierto |
| Diferencia entre `@Binds` y `@Provides` | 2.4 (2026-09-28) | 2 | — | cerrado 2026-10-05 |
```

- Una fila por hueco, con la lección donde se detectó y la fecha.
- `Estado`: `abierto` o `cerrado <fecha>`. Los cerrados se conservan como historia.
- `Próximo repaso`: la fecha en la que lo volverás a preguntar; repásalo en el calentamiento de esa sesión.

### Bitácora

```markdown
| Fecha | Lecciones | Logros | Próximo paso |
|---|---|---|---|
| 2026-09-15 | — | Plan creado tras un diagnóstico de 5 preguntas | Lección 1.2 |
| 2026-09-17 | 1.2 | Construyó `AppContainer` y un test con fake | Lección 1.3 |
```

- Una fila por sesión, añadida al final (la última fila es la más reciente).
- Logros concretos; el próximo paso debe permitir retomar sin contexto.
- Registra también repasos y exámenes: «Repaso M1: 4/5, falló scopes».

## 5. Lista de control de un buen plan

- [ ] La meta es verificable y está alineada con lo que el estudiante quiere.
- [ ] El diagnóstico está registrado y `nivel_actual` coincide con él.
- [ ] Los módulos progresan de 🟢 a 🔴 sin saltos de dependencias.
- [ ] Cada lección tiene un resultado observable y, en los primeros módulos, objetivo, práctica y dominio.
- [ ] Las prácticas usan el proyecto real siempre que es posible.
- [ ] Hay lecciones de errores comunes, testing y, si aplica, seguridad y rendimiento.
- [ ] El proyecto final integra lo aprendido y tiene criterios de evaluación.
- [ ] Los recursos son oficiales y están vigentes.
- [ ] Existen las secciones «Huecos abiertos» (aunque vacía) y «Bitácora».
- [ ] No quedan `[[COMPLETAR]]` y `coach check` no da errores.
- [ ] La presentación al estudiante incluye la duración estimada y el primer paso.

## 6. Mantenimiento del plan

- **Va más rápido de lo previsto**: convalida con evidencia, fusiona lecciones o sube `nivel_objetivo`.
- **Va más lento**: divide lecciones, añade refuerzos (`2.3.1 Refuerzo: …`) o baja el ritmo acordado.
- **Cambia la meta o el proyecto**: ajusta el resumen, los módulos pendientes y el proyecto final.
- **Cambia una versión** del framework: añade una lección de migración o actualiza las pendientes, y registra la fuente.
- **Hueco que se repite**: añade una lección de refuerzo (`3.1.1 Refuerzo: …`) en lugar de volver a preguntar lo mismo, y enlaza la fila de «Huecos abiertos» con ella.
- **Cambia la forma de trabajar** (orden de los bloques, tipo de preguntas, rigor de corrección): eso no va en el plan, va en `aprendizaje/METODO.md`.
- Cualquier ajuste queda anotado en la bitácora y, si afecta a la lección actual, se actualiza `leccion_actual` con `coach leccion`.
