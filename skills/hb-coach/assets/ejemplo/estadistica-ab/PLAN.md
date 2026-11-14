---
tema: "Estadística para entender tests A/B"
slug: estadistica-ab
area: estadistica
nivel_actual: básico
nivel_objetivo: intermedio
leccion_actual: "1.3"
playground: ""
formato: 2
creado: 2026-11-02
actualizado: 2026-11-04
---

# Plan de estudio · Estadística para entender tests A/B

> Ejemplo de referencia de hb-coach para un tema que no es de software: muestra que el formato, los retos y la verificación son los mismos. El contexto es ficticio.

## Resumen

- **Meta:** leer el informe de un experimento A/B del equipo, decidir si el resultado es concluyente y explicarlo a producto en tres frases.
- **Por qué importa:** hoy el equipo lanza variantes por diferencias que pueden ser azar, y nadie sabe cuánto esperar.
- **Punto de partida:** sabe calcular porcentajes y medias; no distingue la variabilidad de un efecto real.
- **Contexto:** sin proyecto de software; practica con los informes de experimentos de su equipo y con simulaciones en Python.
- **Ritmo acordado:** 3 sesiones de 45 min por semana.
- **Duración estimada:** 16 lecciones × 35 min ≈ 9 h, unas 4 semanas.

## Diagnóstico

| Pregunta | Resultado | Decisión |
|---|---|---|
| ¿Por qué se reparte a los usuarios al azar entre A y B? | Correcta, con ejemplo propio | Convalidar 1.1 |
| Si A convierte un 5,2 % y B un 5,8 %, ¿es mejor B? | «Sí, un 0,6 más» | Empezar en 1.2 (variabilidad) |
| ¿Qué indica una desviación típica? | Parcial: «lo que se aleja de la media» | Reforzar en 1.2 |
| ¿Qué es un p-valor? | No la sabía | Módulo 4 sin prisa |
| ¿Cuántos usuarios hacen falta para un experimento? | No la sabía | Lección 5.1 |

## Ruta de aprendizaje

### Módulo 1 · Variabilidad y muestras 🟢 Básico

> **Meta del módulo:** distinguir una diferencia que puede ser azar de una que probablemente no lo es.

- [x] **1.1 Qué es un experimento A/B y por qué aleatorizar** — Explicar qué controla el reparto al azar. (convalidada)
  - Objetivo: explicar por qué sin aleatorizar no se puede atribuir el efecto a la variante.
  - Práctica: señalar un sesgo en un experimento mal repartido.
  - Dominio: respondió bien en el diagnóstico con un ejemplo propio.
- [x] **1.2 Variabilidad: por qué dos grupos iguales dan tasas distintas** — Calcular cuánto varía una tasa de conversión por azar.
  - Objetivo: calcular el error estándar de una proporción y de una diferencia.
  - Práctica: simular tests A/A y comparar con la fórmula.
  - Dominio: dice si una diferencia observada cabe en lo que produce el azar.
- [ ] **1.3 La distribución muestral** — Ver con una simulación por qué las diferencias se reparten como una campana.
  - Objetivo: describir la distribución de las diferencias en tests A/A.
  - Práctica: histograma de 1 000 diferencias simuladas.
  - Dominio: explica qué representa cada punto del histograma.
- [ ] **Examen M1** — 6 a 10 preguntas y una tarea · aprueba con 80 %

### Módulo 2 · Probabilidad útil para experimentos 🟢 Básico

> **Meta del módulo:** usar las dos distribuciones que aparecen en todos los informes.

- [ ] **2.1 Probabilidad y tasas** — Pasar de conteos a probabilidades sin errores de base.
- [ ] **2.2 Binomial y normal para proporciones** — Saber cuándo la normal aproxima bien una tasa.
- [ ] **Examen M2** — 6 a 10 preguntas y una tarea · aprueba con 80 %

### Módulo 3 · Intervalos de confianza 🟡 Intermedio

> **Meta del módulo:** expresar un resultado con su incertidumbre.

- [ ] **3.1 Intervalo de una proporción** — Calcular e interpretar el intervalo de una tasa.
- [ ] **3.2 Intervalo de la diferencia** — Leer si el intervalo de B − A incluye el cero.
- [ ] **3.3 Qué significa (y qué no) un 95 %** — Evitar la interpretación errónea más común.
- [ ] **Examen M3** — 6 a 10 preguntas y una tarea · aprueba con 80 %

### Módulo 4 · Contrastes y p-valor 🟡 Intermedio

> **Meta del módulo:** leer el p-valor del informe sin sobreinterpretarlo.

- [ ] **4.1 Hipótesis nula y p-valor** — Calcular e interpretar el p-valor de una diferencia de tasas.
- [ ] **4.2 Errores de tipo I y II** — Relacionar falsos positivos, falsos negativos y el umbral.
- [ ] **4.3 Leer el informe de la herramienta** — Traducir cada cifra del informe a una frase.
- [ ] **Examen M4** — 6 a 10 preguntas y una tarea · aprueba con 80 %

### Módulo 5 · Diseñar un buen experimento 🟠 Avanzado

> **Meta del módulo:** que el experimento pueda responder la pregunta antes de lanzarlo.

- [ ] **5.1 Potencia y tamaño de muestra** — Calcular cuántos usuarios hacen falta para detectar un efecto.
- [ ] **5.2 Mirar antes de tiempo** — Ver con una simulación por qué parar al ver «significativo» engaña.
- [ ] **5.3 Comparaciones múltiples y métricas de control** — Elegir una métrica primaria y vigilar las demás.
- [ ] **Examen M5** — 6 a 10 preguntas y una tarea · aprueba con 80 %

### Módulo 6 · Proyecto final 🔴 Experto

> **Meta del módulo:** decidir con un experimento real.

- [ ] **6.1 Analizar un experimento real del equipo** — Revisar diseño, cifras e interpretación.
- [ ] **6.2 Presentar la decisión** — Explicar a producto qué se sabe, qué no y qué hacer.

## Proyecto final

Analizar el último experimento A/B del equipo.

- **Entregable:** un informe de una página con la métrica primaria, el intervalo de la diferencia, el p-valor, la potencia que tenía el experimento y una recomendación (lanzar, no lanzar o seguir midiendo).
- **Cómo se comprueba:** cada cifra recalculada con un script; la recomendación sostenida por las cifras.
- **Criterios:** sin errores de interpretación del p-valor ni del intervalo; explica en tres frases la decisión a alguien sin formación estadística.

## Recursos

- [NIST/SEMATECH e-Handbook of Statistical Methods](https://www.itl.nist.gov/div898/handbook/) — referencia de métodos y fórmulas.
- [Introductory Statistics (OpenStax)](https://openstax.org/details/books/introductory-statistics-2e) — libro abierto revisado, base de los módulos 1 a 4.
- [Declaración de la ASA sobre p-valores](https://doi.org/10.1080/00031305.2016.1154108) — qué significa y qué no un p-valor (Wasserstein y Lazar, 2016).
- [Documentación de `statistics` de Python](https://docs.python.org/3/library/statistics.html) — `NormalDist` y medidas para verificar los cálculos.

## Huecos abiertos

| Hueco | Detectado | Intentos | Próximo repaso | Estado |
|---|---|---|---|---|
| Confunde la desviación típica de los datos con el error estándar de la tasa | 1.2 (2026-11-04) | 2 | 2026-11-06 | abierto ✔ |

## Bitácora

| Fecha | Lecciones | Logros | Próximo paso |
|---|---|---|---|
| 2026-11-02 | — | Plan creado tras un diagnóstico de 5 preguntas; 1.1 convalidada | Lección 1.2 |
| 2026-11-04 | 1.2 | Calculó el error estándar a mano y lo comprobó simulando 1 000 tests A/A | Repaso del hueco H1 y lección 1.3 |
