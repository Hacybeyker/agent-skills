# Dominio genérico: cualquier tema

Para temas sin mapa propio en `references/` (finanzas, diseño, música, historia, una certificación, una entrevista…). Da el método para construir el mapa del tema con fuentes fiables, los tipos de práctica que no son código y la política para temas sensibles. Software sigue usando sus mapas.

## Contenido

1. Construir el mapa de un tema
2. Plantilla del mapa
3. Práctica por familia de temas
4. Verificar antes de pedir, fuera del software
5. Evaluación auténtica
6. Temas sensibles
7. Ejemplos de esqueleto de plan

## 1. Construir el mapa de un tema

1. **Delimita la meta** con el estudiante: qué quiere poder hacer y en qué contexto («entender los informes de A/B de mi equipo», «aprobar el B2», «tocar un tema con acordes de jazz», «preparar la entrevista de la semana que viene»).
2. **Busca 2 o 3 fuentes fiables** que ya ordenen el campo ([fuentes-oficiales.md](fuentes-oficiales.md) §5): un marco oficial (el MCER para idiomas, el temario de una certificación), el índice de un libro de texto abierto o el programa de una asignatura universitaria. Cítalas.
3. **Extrae las competencias** y ordénalas por dependencias: qué hay que entender antes de qué. Expresa cada una con un verbo observable (calcular, explicar, interpretar, escribir, pronunciar, decidir).
4. **Marca los conceptos umbral**: las ideas que, una vez entendidas, cambian cómo se ve el resto (la variabilidad en estadística, el interés compuesto en finanzas, la tonalidad en música). Merecen más tiempo y más práctica.
5. **Lista los errores y confusiones frecuentes** que documentan las fuentes: serán los «lo que sale mal» de las lecciones.
6. **Decide la práctica y la evidencia** de cada nivel (§3 y §5).
7. **Guárdalo** si es útil: `coach init <slug> --tema "…" --mapa` crea `<slug>/MAPA.md` desde la plantilla, y aparece en el cuaderno. El mapa es la base del plan, no el plan.

## 2. Plantilla del mapa

| Sección | Qué contiene |
|---|---|
| Competencias por nivel | 🟢 con guía · 🟡 autónomo en casos reales · 🟠 casos límite y criterio · 🔴 diseña, decide y enseña. |
| Conceptos umbral | 3 a 6 ideas clave. |
| Errores frecuentes | La confusión y por qué ocurre. |
| Práctica y evaluación | Por nivel: práctica típica y evidencia de dominio. |
| Fuentes del mapa | Las 2 o 3 fuentes con su enlace. |

## 3. Práctica por familia de temas

«🛠 Hacer» no es solo programar. El reto tiene siempre enunciado, resultado esperado observable, pistas y solución tras intentarlo.

| Familia | Retos típicos | Resultado esperado |
|---|---|---|
| Software | Implementar en su proyecto, romper a propósito y leer el error, escribir un test, leer un trace | Compila, pasa N tests, aparece X |
| Matemáticas y estadística | Problema resuelto → completar → resolver; estimar antes de calcular; interpretar un resultado; simular | Una cifra con su interpretación |
| Idiomas | Producir (escribir o decir) con corrección, reformular, dictado, completar huecos en contexto, simulacro de conversación | Frase correcta y natural, rúbrica de producción |
| Escritura, historia y humanidades | Comentar una fuente, ordenar una línea temporal, argumentar en un párrafo, comparar interpretaciones | Texto que cumple una rúbrica explícita |
| Diseño | Analizar una interfaz con criterios, rediseñar una pantalla, auditar accesibilidad | Lista de problemas y propuesta justificada |
| Música y habilidades motoras | Práctica deliberada corta (un compás, una escala, a tempo lento), grabarse y comparar con una referencia | Ejecución a un tempo dado, sin errores en N repeticiones |
| Finanzas personales | Casos ficticios con supuestos explícitos, calcular y comparar escenarios | Cálculo correcto y decisión argumentada, sin recomendar productos |
| Entrevistas | Simulacro cronometrado, respuesta con estructura (situación, tarea, acción, resultado), pregunta técnica con rúbrica | Respuesta que cumple la rúbrica y el tiempo |

**Tres ejemplos por concepto** fuera del software: el caso mínimo resuelto, el mismo en su contexto (sus datos, su trabajo, su meta) y el error típico documentado con por qué ocurre.

## 4. Verificar antes de pedir, fuera del software

- **Cálculos**: resuélvelos antes con un script (Python con su librería estándar: `math`, `statistics`, `fractions`, `decimal`, `random`) y guarda la cifra que esperas.
- **Hechos, fechas, normas**: compruébalos en la sesión en una fuente del §5 de fuentes; si no puedes, márcalos «a verificar».
- **Lengua**: contrasta con un diccionario o una gramática de referencia (RAE y su Diccionario panhispánico de dudas, Cambridge, Oxford); la pronunciación, con la transcripción fonética del diccionario.
- **Rúbricas**: escríbelas antes de pedir la tarea; el estudiante debe conocerlas.

## 5. Evaluación auténtica

La comprobación de dominio y los exámenes miden lo que el estudiante hará de verdad: interpretar un informe real, escribir el correo que necesita, resolver un problema nuevo, tocar la pieza, responder la pregunta de la entrevista. El proyecto final es una tarea completa de su contexto con criterios explícitos.

## 6. Temas sensibles

Salud, nutrición, psicología, leyes, impuestos y finanzas personales:

- Enseña **conceptos** y cómo leer información fiable; cita organismos reconocidos (OMS, reguladores, boletines oficiales).
- No diagnostiques, no interpretes su analítica, no asesores su caso legal o fiscal y no recomiendes productos financieros ni inversiones concretas.
- Cuando la pregunta pasa a ser su situación personal («¿debería invertir en…?», «¿esto que me pasa es…?»), dilo con claridad y deriva a un profesional (médico, abogado, asesor financiero o fiscal registrado).
- Las normas dependen del país: pregunta cuál y di de cuál es lo que enseñas.
- Ante una señal de riesgo (salud mental, urgencia médica), prioriza derivar a ayuda profesional o de emergencia sobre la lección.

## 7. Ejemplos de esqueleto de plan

- **Estadística para entender tests A/B** (8 a 10 h): variabilidad y muestras → probabilidad y distribuciones útiles → intervalos de confianza → contrastes y p-valor → potencia y tamaño de muestra → errores frecuentes (mirar antes de tiempo, comparaciones múltiples) → proyecto: analizar un experimento real de su equipo. Ejemplo completo en `assets/ejemplo/estadistica-ab/`.
- **Inglés técnico para entrevistas** (B1 → B2): presentarse y contar su experiencia → explicar decisiones técnicas → preguntas de comportamiento con estructura → entender preguntas difíciles y pedir aclaraciones → simulacros completos. Mapa en [dominio-idiomas.md](dominio-idiomas.md).
- **Finanzas personales básicas**: presupuesto → interés simple y compuesto → inflación → deuda y TAE → ahorro e inversión como conceptos (riesgo, diversificación, costes) → proyecto: su presupuesto con supuestos explícitos, sin recomendar productos.
