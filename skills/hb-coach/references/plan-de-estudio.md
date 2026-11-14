# Diseño del plan de estudio

Cómo crear y mantener `<slug>/PLAN.md`. El formato es estricto porque `coach` y el cuaderno lo leen para calcular el progreso, los exámenes y los repasos.

## Contenido

1. Método: diseño inverso
2. Diagnóstico adaptativo
3. Estructura del curso
4. Formato exacto de PLAN.md
5. Lista de control de un buen plan
6. Mantenimiento del plan

## 1. Método: diseño inverso

1. **Meta**: qué podrá hacer el estudiante al terminar, en una frase verificable. Mal: «saber Hilt», «saber estadística». Bien: «diseñar la DI de una app multimódulo con Hilt, con tests, y justificar cada scope»; «decidir si un test A/B es concluyente y explicar por qué a un equipo de producto».
2. **Evidencias**: qué demostrará que lo logró (proyecto final, exámenes, tareas reales).
3. **Ruta**: módulos y lecciones que llevan de su punto de partida a esas evidencias, en orden de dependencias conceptuales.

Adapta el plan a su realidad: en software, las prácticas se hacen en su proyecto y con sus versiones; en otros temas, con sus datos, su trabajo o su meta (la entrevista, el examen oficial, el viaje).

## 2. Diagnóstico adaptativo

Antes, acuerda el método (`coach metodo`). El diagnóstico mide lo que **ya** debería saber: nunca preguntes por lo que vas a enseñar.

**Preguntas de contexto** (3 o 4, con opciones cuando sea posible): experiencia con el tema y con temas vecinos; meta concreta (proyecto, trabajo, examen, entrevista, curiosidad); tiempo por semana y duración de las sesiones; dónde lo aplicará.

**Preguntas de nivel** (5 a 8, una por mensaje, escalonadas): 2 de básico, 2 o 3 de intermedio, 1 o 2 de avanzado y, si responde todo bien, 1 de experto. Preferentemente abiertas o de «explica por qué». En idiomas, incluye una tarea breve de producción (escribir o decir unas frases) además de las preguntas. Si falla dos seguidas, detén el escalado. No enseñes durante el diagnóstico; solo anota. Al final, un resumen honesto y breve de su punto de partida.

**Decisiones**:

- Pregunta básica bien respondida y con ejemplo propio → convalidar la lección correspondiente.
- Respuesta parcial → mantener la lección, en modo exprés.
- Nivel avanzado demostrado → convalidar solo lo conceptual; lo práctico avanzado exige evidencia práctica.
- Registra todo en `## Diagnóstico` y fija `nivel_actual`.

## 3. Estructura del curso

**Niveles** (encabezado de cada módulo):

| Nivel | Emoji | El estudiante… |
|---|---|---|
| Básico | 🟢 | entiende el problema y los conceptos y usa lo esencial con guía. |
| Intermedio | 🟡 | lo aplica de forma autónoma en casos reales y conoce las alternativas. |
| Avanzado | 🟠 | domina el funcionamiento interno, los casos límite y los trade-offs. |
| Experto | 🔴 | diseña soluciones completas, decide con criterio y puede enseñarlo (proyecto final). |

**Tamaño** (como un curso completo: unas 20 a 30 lecciones):

- 5 a 8 módulos; 3 a 5 lecciones por módulo; un examen al final de cada módulo (salvo el del proyecto final).
- Cada lección tiene un único resultado observable y dura entre 20 y 45 minutos.
- Estimación: lecciones × 30–40 minutos, en semanas según el ritmo acordado. Indícala al presentar el plan.
- Un plan corto (una entrevista la semana que viene) puede tener 2 o 3 módulos: el tamaño sigue a la meta.

**Contenido que casi siempre debe aparecer** (cuando aplique):

- el problema que resuelve y las alternativas;
- fundamentos antes que herramientas;
- práctica real en su contexto;
- errores y confusiones frecuentes;
- en software, testing, seguridad y rendimiento;
- integración con lo que ya hace o sabe;
- proyecto final que integre todo.

Los mapas `dominio-*.md` tienen rutas típicas; úsalos como punto de partida, no como plantilla rígida. Si el tema no tiene mapa, constrúyelo con [dominio-generico.md](dominio-generico.md) y, si lo guardas, en `<slug>/MAPA.md` (`coach init … --mapa`).

## 4. Formato exacto de PLAN.md

Parte de la plantilla que crea `coach init` y reemplaza todos los `[[COMPLETAR: …]]`. Como el archivo ya existe, léelo antes de reescribirlo.

### Frontmatter

```yaml
---
tema: "Estadística para entender tests A/B"   # título visible
slug: estadistica-ab                          # igual que la carpeta
area: estadistica                             # android, backend, idiomas, estadistica, finanzas…
nivel_actual: básico                          # según el diagnóstico
nivel_objetivo: intermedio
leccion_actual: "1.2"                         # la mantiene coach; entre comillas
playground: "https://…"                       # opcional: herramienta oficial para practicar
formato: 2                                    # lo pone coach; no lo cambies
creado: 2026-11-13
actualizado: 2026-11-13
---
```

Valores con `:` u otros símbolos van entre comillas. No añadas comentarios `#` en tus archivos reales.

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
## Recursos
## Huecos abiertos
## Bitácora
```

`Recursos` también puede llamarse `Recursos oficiales` (planes de 3.0).

### Módulos, lecciones y examen

```markdown
### Módulo 3 · Componentes, scopes y qualifiers 🟡 Intermedio

> **Meta del módulo:** decidir cuánto vive cada objeto y distinguir implementaciones del mismo tipo.

- [ ] **3.1 Componentes y ciclo de vida** — Relacionar cada componente con el ciclo de vida de Android.
  - Objetivo: explicar qué componente retiene cada instancia y cuándo se destruye.
  - Práctica: dibujar el árbol de componentes de su app.
  - Dominio: predice correctamente cuánto vive un objeto con y sin scope.
- [ ] **3.2 Scopes** — Elegir el scope mínimo necesario y conocer su coste.
- [ ] **Examen M3** — 6 a 10 preguntas y una tarea · aprueba con 80 %
```

Reglas:

- Encabezado de módulo de nivel 3: `### Módulo <n> · <nombre> <emoji> <Nivel>`, con la cita de la meta debajo.
- Lección: `- [ ] **<id> <título>** — <resultado de aprendizaje>`, con el id y el título dentro de las negritas.
- Id `<módulo>.<lección>` (`3.2`). Para insertar entre lecciones usa un subnivel (`3.2.1`); nunca renumeres lecciones hechas.
- Detalles (`Objetivo`, `Práctica`, `Dominio`) en una sublista con 2 espacios. Obligatorios en los módulos básicos e intermedios; muy recomendables en el resto.
- **Examen**: `- [ ] **Examen M<n>** — …` como última línea de cada módulo, salvo en el del proyecto final. `coach examen` la añade si falta y la marca con el resultado.
- Completada `- [x]`; convalidada `- [x] … (convalidada)`. Lo hace `coach completar`.
- No uses checkboxes con un id en negrita fuera de la ruta: se contarían como lecciones.
- No enlaces las notas: el cuaderno las asocia por el id del nombre de archivo.

### Diagnóstico

```markdown
| Pregunta | Resultado | Decisión |
|---|---|---|
| ¿Qué problema resuelve la inyección de dependencias? | Correcta, con ejemplo propio | Convalidar 1.1 |
```

### Proyecto final

Descripción del entregable, requisitos, cómo se comprobará (tests, rúbrica, entrega real) y criterios de evaluación. Suele ser el último módulo (🔴 Experto), sin línea de examen: el proyecto es su examen.

### Recursos

Enlaces con una frase sobre para qué sirve cada uno. Solo fuentes oficiales o fiables y vigentes ([fuentes-oficiales.md](fuentes-oficiales.md)).

### Huecos abiertos

La sección existe desde el primer día, aunque esté vacía. La gestiona `coach hueco`: no calcules fechas a mano.

```markdown
| Hueco | Detectado | Intentos | Próximo repaso | Estado |
|---|---|---|---|---|
| Reutilizar un caso de uso en dos pantallas | 3.1 (2026-10-02) | 2 | 2026-10-09 | abierto ✔ |
| Diferencia entre `@Binds` y `@Provides` | 2.4 (2026-09-28) | 2 | — | cerrado 2026-10-05 |
```

`Estado`: `abierto` más una ✔ por cada repaso bien seguido, o `cerrado <fecha>`. Los cerrados se conservan.

### Bitácora

Una fila por sesión, al final (la añade `coach sesion`): fecha, lecciones, logros concretos y un próximo paso que permita retomar sin contexto. También repasos y exámenes: «Examen M1: 5/6».

## 5. Lista de control de un buen plan

- [ ] La meta es verificable y está alineada con lo que quiere.
- [ ] El diagnóstico está registrado y `nivel_actual` coincide con él.
- [ ] Los módulos progresan de 🟢 a 🔴 sin saltos de dependencias, y cada uno termina con su examen.
- [ ] Cada lección tiene un resultado observable y, en los primeros módulos, objetivo, práctica y dominio.
- [ ] Las prácticas usan su proyecto o su contexto real siempre que se puede.
- [ ] Hay lecciones de errores frecuentes y, si aplica, de testing, seguridad y rendimiento.
- [ ] El proyecto final integra lo aprendido y tiene criterios de evaluación.
- [ ] Los recursos son oficiales o fiables y están vigentes.
- [ ] No quedan `[[COMPLETAR]]` y `coach check` no da errores.
- [ ] La presentación incluye la duración estimada y el primer paso.

## 6. Mantenimiento del plan

- **Va más rápido**: convalida con evidencia, fusiona lecciones o sube `nivel_objetivo`.
- **Va más lento**: divide lecciones, añade refuerzos (`2.3.1 Refuerzo: …`) o baja el ritmo acordado.
- **Cambia la meta**: ajusta el resumen, los módulos pendientes y el proyecto final.
- **Cambia una versión** del framework o una norma: añade una lección de actualización o ajusta las pendientes, y registra la fuente.
- **Hueco que se repite**: una lección de refuerzo en lugar de volver a preguntar lo mismo.
- **Cambia la forma de trabajar**: eso no va en el plan, va en `METODO.md` (`coach metodo`).
- Cualquier ajuste queda en la bitácora (`coach sesion`) y, si afecta a la lección actual, se actualiza con `coach leccion`.
