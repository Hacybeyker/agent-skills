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

Sin mejoras aplicadas (el diagnóstico no propuso ninguna, o quedaron todas descartadas o pendientes) no hay fase después: es un cierre corto. Salta la comparación, escribe el resumen con el estado inicial y por qué no hay mejoras, y genera el reporte, que documenta el diagnóstico y los pendientes.

Si una mejora a prueba salió `✖ hipótesis refutada`, dilo en la lectura: qué se descartó como causa, que el cambio se revierte (salvo que el usuario lo quiera por otro motivo) y qué queda como pendiente.

Si `comparar` avisa que la **marca de fin de una métrica dejó de ser la última llamada de red** (`hasta_ultima_red_ms`), la métrica cambió de definición: su veredicto no prueba la mejora. Dilo en la lectura y usa la última llamada (o una marca de contenido visible, midiendo de nuevo) como evidencia.

Con avisos (`pocas corridas`, `inestable`), el veredicto se presenta con el aviso, nunca como resultado firme. Los de familia `e2e` dependen del backend: son orientativos. Si `comparar` avisa que antes y después midieron el mismo build, o con distinta compilación de ART, la comparación no prueba nada: repite las fases afectadas con `--rehacer` antes de escribir la lectura.

## 2. Lectura de la comparación

Escribe en `estado.md` ("Lectura de la comparación") una línea por cada métrica principal, cada regresión y cada "no comparable": qué cambió y por qué, con la evidencia. Si lo que siente el usuario solo se ve en una consulta (por ejemplo, cuándo termina un spinner), cita los rangos por corrida rotulados "sin veredicto estadístico". Para explicar una regresión, `perf.py diagnostico --carpeta <carpeta> --fase despues` deja `diagnostico-despues.md` con las mismas consultas.

## 3. Resumen ejecutivo

De 3 a 5 líneas en "Resumen ejecutivo": estado inicial → estado final con las métricas principales, la causa en una frase y qué parte depende del backend.

## 4. Reporte

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py reporte --carpeta <carpeta> --html
```

Genera `reporte-final.md` y `reporte-final.html` (autocontenido, con gráficos antes y después, pensado para alguien que no siguió la investigación): resumen ejecutivo; de los hallazgos al resultado (cuántos hallazgos, cuántas mejoras, cuántas aplicadas y cuáles funcionaron ✔ o no ✖; en una mejora a prueba, si su hipótesis quedó confirmada ✔ o refutada ✖); métricas principales con qué significa cada veredicto; esperado contra logrado; hallazgos con su resultado; mejoras aplicadas; lectura de la comparación; comparación completa; las filas de la ficha que sirven al lector; los pendientes ("no son mejoras"); y un glosario ("Cómo leer este reporte"). Lleva solo métricas agregadas: se puede compartir. Lo que en `estado.md` siga con el texto de la plantilla no se publica: el comando avisa qué falta, omite esa sección o pone "sin completar" en la fila; complétalo y vuelve a generar. El reporte inicial (`reporte-inicial.*`, sesión 2) no se toca.

## 5. Guarda de regresión

Propón cómo proteger la mejora: el test de la sesión 3 y, si el flujo es crítico y el proyecto lo justifica, un Macrobenchmark del flujo en un PR aparte.

## Entrega

- El resumen ejecutivo y la ruta de `reporte-final.html`.
- Los commits propuestos y el texto del PR, solo con métricas agregadas.
- Pendientes y hallazgos fuera del alcance, para una próxima investigación.
- Cómo validarlo en campo después del release (Android vitals: TTID y TTFD si la app llama a `reportFullyDrawn`).
- "Cambios temporales por revertir" de `estado.md`: comprueba que cada fila esté revertida (en su repo o módulo) y dilo; si queda alguna, es lo primero de la entrega.
- Limpieza, cuando se mergee: las trazas (`antes/`, `control/`, `despues/`, `prueba/`) y los heap dumps se borran; `metricas.csv`, los `.md` y el reporte se pueden conservar. `reports/` no está en git: si `recorrido.sh` o el flow de `preparar` se van a reutilizar, se archivan fuera antes de borrar.
- "Consumo" la completa el usuario con `perf.py consumo`; no se lo pidas. Si faltan filas, dilo en una línea con el comando.
- `perf.py reporte` deja "Siguiente paso" como investigación cerrada.
