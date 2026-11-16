---
tema: "Estadística para entender tests A/B"
slug: estadistica-ab
---

# Dudas resueltas · Estadística para entender tests A/B

## 2026-11-04 · ¿Por qué el ruido baja con la raíz de n y no con n?

- **Contexto:** reto 1 de la lección 1.2.
- **Respuesta corta:** porque los errores de cada usuario se compensan en parte entre sí: la varianza de una media baja con `n`, y el error estándar es su raíz.
- **Explicación:** si cada usuario aporta una varianza `v`, la media de `n` usuarios tiene varianza `v / n`; el error estándar es `raíz(v / n)`. Por eso cuadruplicar `n` solo divide el error entre dos.
- **Relacionado:** lección [1.2](lecciones/1.2-variabilidad-por-que-dos-grupos-iguales-dan-tasas-distintas.md) · término «Error estándar»
- **Fuente:** [Introductory Statistics (OpenStax)](https://openstax.org/details/books/introductory-statistics-2e)
