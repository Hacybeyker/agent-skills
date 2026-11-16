# Dominio: matemáticas y estadística

Mapa para diseñar planes y enseñar matemáticas aplicadas, probabilidad y estadística (incluido el análisis de experimentos como los tests A/B). Cada cifra que se enseñe o se pida se calcula antes con un script.

## Contenido

1. Mapa de competencias
2. Rutas típicas
3. Cómo se enseña con el coach
4. Ideas erróneas frecuentes
5. Decisiones que el estudiante debe saber argumentar
6. Ideas de práctica
7. Panorama actual

## 1. Mapa de competencias

### 🟢 Básico
- Aritmética con fracciones, porcentajes y potencias; orden de magnitud y estimación.
- Álgebra: ecuaciones lineales, despejar, funciones y sus gráficas.
- Estadística descriptiva: tipos de variables, media, mediana, moda, rango, desviación típica, gráficos adecuados.
- Probabilidad básica: espacio muestral, regla de la suma y del producto, probabilidad condicional.

### 🟡 Intermedio
- **Distribuciones**: binomial, Poisson, normal; esperanza y varianza; la ley de los grandes números.
- **Muestreo**: población y muestra, sesgo, error estándar, teorema central del límite.
- **Inferencia**: intervalos de confianza, contraste de hipótesis, p-valor, errores de tipo I y II.
- **Relación entre variables**: correlación, regresión lineal simple, correlación frente a causalidad.
- **Álgebra lineal y cálculo** según la meta: vectores y matrices; derivada como tasa de cambio.

### 🟠 Avanzado
- **Diseño de experimentos**: aleatorización, grupo de control, potencia y tamaño de muestra, efecto mínimo detectable.
- **Tests A/B**: métricas primarias y de control, duración, mirar antes de tiempo, comparaciones múltiples, efectos de novedad.
- **Modelos**: regresión múltiple, regresión logística, supuestos y diagnóstico de residuos.
- **Remuestreo y simulación**: bootstrap, tests de permutación.
- **Inferencia bayesiana** a nivel conceptual: a priori, verosimilitud, a posteriori.

### 🔴 Experto
- Elegir y justificar el análisis de un caso real y comunicar la incertidumbre a quien decide.
- Detectar fallos de diseño y de análisis en informes ajenos.
- Experimentos secuenciales, métodos de reducción de varianza y efectos heterogéneos, a nivel de criterio.

## 2. Rutas típicas

- **Estadística para entender tests A/B**: variabilidad y muestras → probabilidad y distribuciones útiles → intervalos de confianza → contrastes y p-valor → potencia y tamaño de muestra → errores frecuentes → proyecto con un experimento real.
- **Probabilidad desde cero**: conteo → probabilidad condicional y Bayes → variables aleatorias → distribuciones → simulación.
- **Matemáticas para machine learning**: vectores y matrices → derivadas y gradiente → probabilidad → estadística para evaluar modelos.
- **Estadística descriptiva para informes**: tipos de datos → resúmenes → gráficos honestos → comparar grupos.

## 3. Cómo se enseña con el coach

- **Ejemplo resuelto → completar → resolver**: un problema resuelto paso a paso con cada paso justificado; después el mismo tipo con un paso vacío; después uno nuevo sin ayuda.
- **Estimar antes de calcular**: pide un orden de magnitud antes de la cuenta («¿más o menos de 1 000 usuarios por grupo?»). Detecta errores y entrena la intuición.
- **Interpretar, no solo calcular**: todo resultado termina en una frase para quien decide («con estos datos no podemos distinguir B de A; necesitaríamos unas 3 semanas más»).
- **Simular para entender**: con Python y su librería estándar (`random`, `statistics`) se ve el teorema central del límite, qué significa un 95 % o cuántos «falsos ganadores» salen al mirar cada día.
- **Verifica antes de pedir**: calcula cada respuesta modelo con un script antes de proponer el reto. `statistics.NormalDist` (Python 3.8+) da probabilidades y cuantiles de la normal sin dependencias.
- **Notación**: define cada símbolo la primera vez y usa pocos; en la nota, las fórmulas en bloques de código `text` y explicadas en palabras.
- **Tres ejemplos**: el caso mínimo con números redondos, el mismo con sus datos, y el razonamiento que sale mal (la interpretación errónea típica) con por qué.

## 4. Ideas erróneas frecuentes

- «El p-valor es la probabilidad de que la hipótesis nula sea cierta» → es la probabilidad de datos tan extremos o más si la nula fuera cierta.
- «No significativo = no hay efecto» → puede faltar potencia; mira el intervalo.
- «Un 95 % de confianza = 95 % de probabilidad de que el valor esté en este intervalo» → se refiere al procedimiento a la larga.
- «Puedo mirar el test cada día y pararlo cuando salga significativo» → infla los falsos positivos.
- «Si pruebo 20 métricas, la que salga significativa es real» → comparaciones múltiples.
- «Correlación implica causalidad» → hacen falta diseño experimental o supuestos explícitos.
- «La media de las medias es la media total» → solo con grupos del mismo tamaño (y ojo a la paradoja de Simpson).
- «Más datos siempre arreglan un sesgo» → un sesgo no se corrige con tamaño.

## 5. Decisiones que el estudiante debe saber argumentar

- Media o mediana para resumir una métrica concreta.
- Qué métrica primaria elegir y cuáles de control.
- Cuánto debe durar un experimento y con qué tamaño de muestra.
- Lanzar, no lanzar o seguir midiendo, con un resultado dado.
- Frecuentista o bayesiano para comunicar un resultado a su equipo.

## 6. Ideas de práctica

- Calcular a mano y con un script el intervalo de confianza de una tasa de conversión.
- Simular 1 000 tests A/A y contar cuántos salen «significativos».
- Calcular el tamaño de muestra para detectar un efecto dado y discutir si es viable.
- Leer un informe de experimento real del equipo y encontrar sus debilidades.
- Explicar un resultado a una persona de producto en tres frases.

## 7. Panorama actual (revisar antes de enseñar)

- La declaración de la American Statistical Association sobre p-valores (Wasserstein y Lazar, 2016, *The American Statistician* 70(2)) es la referencia para enseñar qué significa y qué no un p-valor.
- Las plataformas de experimentación usan cada vez más métodos secuenciales y de reducción de varianza: enséñalos a nivel de criterio y con la documentación de la herramienta que use el estudiante.
