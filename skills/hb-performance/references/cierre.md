# Sesión 4 · Cierre

Compara, redacta lo que solo el modelo puede redactar y entrega. Es corta: los números y las tablas los hace el script.

## 1. Comparación

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py comparar <carpeta>/metricas.csv
```

Imprime las métricas principales, las de usuario, las centrales y cualquier mejora o regresión; deja la tabla completa en `comparacion.md` y actualiza "Comparación" en `estado.md`.

| Veredicto | Cuándo |
| --- | --- |
| `mejora` | La mediana de después es mejor **y** queda fuera del rango [mín, máx] de antes |
| `regresión` | Lo mismo, en sentido contrario. Se reporta siempre |
| `dentro del ruido` | Hay bloque de control y la diferencia no supera la de antes contra control |
| `sin cambio` | Cualquier otro caso |

Con avisos (`pocas corridas`, `inestable`), el veredicto se presenta con el aviso, nunca como resultado firme. Los de familia `e2e` dependen del backend: son orientativos.

## 2. Resumen ejecutivo

Escribe en `estado.md` ("Resumen ejecutivo") de 3 a 5 líneas: estado inicial → estado final con las métricas principales, la causa en una frase y qué parte depende del backend. Es lo único que redacta el modelo en esta sesión.

## 3. Reporte

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py reporte --carpeta <carpeta>
```

Genera `reporte.md` con el resumen ejecutivo, las métricas principales, los hallazgos, las mejoras, la comparación, la ficha y los pendientes. Con `--html`, también `reporte.html` (autocontenido, con gráficos antes/después). Lleva solo métricas agregadas: se puede compartir.

## 4. Guarda de regresión

Propón cómo proteger la mejora: el test de la sesión 3 y, si el flujo es crítico y el proyecto lo justifica, un Macrobenchmark del flujo en un PR aparte.

## Entrega

- El resumen ejecutivo y la ruta de `reporte.md`.
- Los commits propuestos y el texto del PR, solo con métricas agregadas.
- Pendientes y hallazgos fuera del alcance, para una próxima investigación.
- Cómo validarlo en campo después del release (Android vitals o la herramienta que use el proyecto).
- Limpieza: borrar heap dumps y, si no se van a usar, las trazas inválidas.
