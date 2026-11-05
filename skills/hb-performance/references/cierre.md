# Sesión 4 · Cierre

Compara, redacta lo que solo el modelo puede redactar y entrega. Es corta: los números, las tablas y el reporte los hace el script.

## 1. Comparación

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py comparar <carpeta>/metricas.csv
```

Imprime las métricas principales, las de usuario, las centrales y cualquier mejora o regresión; deja la tabla completa y los builds medidos en `comparacion.md`, y actualiza "Comparación" y "Plan de mejoras" (propuesto contra logrado) en `estado.md`.

| Veredicto | Cuándo |
| --- | --- |
| `mejora` | La mediana de después es mejor **y** queda fuera del rango [mín, máx] de antes |
| `regresión` | Lo mismo, en sentido contrario. Se reporta siempre |
| `dentro del ruido` | Hay bloque de control y la diferencia no supera la de antes contra control |
| `no comparable` | Métrica de frames y la cantidad de frames cambió más de 50 %: el porcentaje o el percentil mide otra cosa |
| `sin cambio` | Cualquier otro caso |

Sin mejoras aplicadas (todas descartadas o pendientes) no hay fase después: salta la comparación, escribe el resumen con el estado inicial y genera el reporte, que documenta el diagnóstico y los pendientes.

Con avisos (`pocas corridas`, `inestable`), el veredicto se presenta con el aviso, nunca como resultado firme. Los de familia `e2e` dependen del backend: son orientativos. Si `comparar` avisa que antes y después midieron el mismo build, o con distinta compilación de ART, la comparación no prueba nada: repite las fases afectadas con `--rehacer` antes de escribir la lectura.

## 2. Lectura de la comparación

Escribe en `estado.md` ("Lectura de la comparación") una línea por cada métrica principal, cada regresión y cada "no comparable": qué cambió y por qué, con la evidencia. Si lo que siente el usuario solo se ve en una consulta (por ejemplo, cuándo termina un spinner), cita los rangos por corrida rotulados "sin veredicto estadístico". Para explicar una regresión, `perf.py diagnostico --carpeta <carpeta> --fase despues` deja `diagnostico-despues.md` con las mismas consultas.

## 3. Resumen ejecutivo

De 3 a 5 líneas en "Resumen ejecutivo": estado inicial → estado final con las métricas principales, la causa en una frase y qué parte depende del backend.

## 4. Reporte

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py reporte --carpeta <carpeta> --html
```

Genera `reporte.md` y `reporte.html` (autocontenido, con gráficos antes y después): resumen ejecutivo, métricas principales, propuesto contra logrado, hallazgos, mejoras, lectura de la comparación, comparación, las filas de la ficha que sirven al lector y los pendientes. Lleva solo métricas agregadas: se puede compartir.

## 5. Guarda de regresión

Propón cómo proteger la mejora: el test de la sesión 3 y, si el flujo es crítico y el proyecto lo justifica, un Macrobenchmark del flujo en un PR aparte.

## Entrega

- El resumen ejecutivo y la ruta de `reporte.html`.
- Los commits propuestos y el texto del PR, solo con métricas agregadas.
- Pendientes y hallazgos fuera del alcance, para una próxima investigación.
- Cómo validarlo en campo después del release (Android vitals: TTID y TTFD si la app llama a `reportFullyDrawn`).
- Limpieza, cuando se mergee: las trazas (`antes/`, `control/`, `despues/`, `prueba/`) y los heap dumps se borran; `metricas.csv`, los `.md` y el reporte se pueden conservar.
- El costo de la investigación en "Consumo", con el de esta sesión.
- `perf.py reporte` deja "Siguiente paso" como investigación cerrada.
