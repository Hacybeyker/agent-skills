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

De 3 a 5 líneas en "Resumen ejecutivo": estado inicial → estado final con las métricas principales, la causa en una frase y qué parte depende del backend. **Reemplaza el que dejó la sesión 2** para el reporte inicial: ya no es relleno de plantilla, así que nada avisa si se queda, y el reporte final publicaría el resumen del diagnóstico.

**Y el "Resumen para gerencia"**, en su sección de `estado.md`, que también reemplaza al de la sesión 2: de 3 a 5 líneas para un lector no técnico, sin nombres de métricas, percentiles ni términos de la traza. Qué cambió para el usuario, en segundos o en lo que se percibe ("abrir la lista pasó de unos 2 s a 1 s", "deja de congelarse al escribir"), qué no cambió y qué queda pendiente. Es lo único que escribes para el reporte de gerencia; si la sección no existe (un `estado.md` de una versión anterior), agrégala antes de "Pendientes".

## 4. Reporte

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py reporte --carpeta <carpeta> --html
```

Genera el reporte en **dos versiones**, con los mismos datos: `reporte-final-dev` (`.md` y `.html`: el técnico) y `reporte-final-gerencia` (una página corta en palabras: qué notaba el usuario, qué se encontró, qué se hizo, el resultado con el tiempo antes y después en segundos y su veredicto en palabras, cuánto del recorrido es espera de servicios, lo pendiente, los riesgos y el costo total; sin nombres de métricas ni percentiles). El de gerencia lo arma `perf.py`; tú solo escribiste su resumen. El técnico es autocontenido, con gráficos antes y después, pensado para alguien que no siguió la investigación: resumen ejecutivo; de los hallazgos al resultado (cuántos hallazgos, cuántas mejoras, cuántas aplicadas y cuáles funcionaron ✔ o no ✖; en una mejora a prueba, si su hipótesis quedó confirmada ✔ o refutada ✖); métricas principales con qué significa cada veredicto; "Servicios del flujo" (los 5 servicios que más tiempo suman, antes contra después; orientativa); esperado contra logrado; hallazgos con su resultado; mejoras aplicadas; lectura de la comparación; comparación completa; las filas de la ficha que sirven al lector; los pendientes ("no son mejoras"); y un glosario ("Cómo leer este reporte"). Lleva solo métricas agregadas: se puede compartir. Lo que en `estado.md` siga con el texto de la plantilla no se publica: el comando avisa qué falta, omite esa sección o pone "sin completar" en la fila; complétalo y vuelve a generar. El reporte inicial (`reporte-inicial-*`, sesión 2) no se toca. Una investigación anterior puede tener `reporte-inicial.*` o `reporte-final.*` con el nombre de antes: se siguen reconociendo, y no se actualizan ni se borran.

## 5. Guarda de regresión

Propón cómo proteger la mejora: el test de la sesión 3 y, si el flujo es crítico y el proyecto lo justifica, un Macrobenchmark del flujo en un PR aparte.

## Entrega

- El resumen ejecutivo y las rutas de `reporte-final-dev.html` y `reporte-final-gerencia.html`.
- Los commits propuestos y el texto del PR, solo con métricas agregadas.
- Pendientes y hallazgos fuera del alcance, para una próxima investigación.
- Cómo validarlo en campo después del release (Android vitals: TTID y TTFD si la app llama a `reportFullyDrawn`).
- "Cambios temporales por revertir" de `estado.md`: comprueba que cada fila esté revertida (en su repo o módulo) y dilo; si queda alguna, es lo primero de la entrega. Cuentan también las ediciones de cableado en código de `main` que no se commitean (el gancho de red, una marca en una pantalla). **Se quitan sin perderlos, siempre en este orden** (`perf.py siguiente` imprime los comandos con los archivos que siguen sin revertir y la ruta del parche):
  1. **Primero el parche, fuera del repo, y comprobado:** `cd <repo> && git diff --binary -- <archivos> > <parche> && git apply --check -R <parche>` (un archivo nuevo entra en el parche después de `git add -N <archivo>`). El parche va en la carpeta de parches de `AGENTS.md` si el proyecto la configuró ([setup.md](setup.md) · Una sola carpeta); si no, en una carpeta que el repo no versiona. **No vuelvas a guardar sobre un parche después de quitar:** con los cambios ya fuera, `git diff` sale vacío y pisaría la única copia (el comando de `siguiente` no pisa un parche que ya existe).
  2. **Después se quitan con el parche:** `cd <repo> && git apply -R <parche>` (más `git reset -q -- <archivo>` por cada archivo nuevo que entró con `git add -N`), y `git status --short` para confirmarlo.
  3. **Nunca `git checkout`, `git restore`, `git reset --hard` ni `git clean` sobre un archivo con cambios temporales**, ni como atajo ni "para dejarlo limpio": borran el archivo entero sin guardarlo, y el archivo puede tener cambios que no son de esta investigación. No los propongas ni los corras.
  4. **Si otra investigación abierta del mismo proyecto declara el mismo archivo** en sus cambios temporales, `siguiente` lo avisa: ese archivo va en un parche aparte y no se quita entero. Quita a mano solo lo de esta investigación, o déjalo hasta que cierre la otra, y dilo en la entrega.
- Limpieza, cuando se mergee: las trazas (`antes/`, `control/`, `despues/`, `prueba/`) y los heap dumps se borran; `metricas.csv`, los `.md` y el reporte se pueden conservar. `reports/` no está en git: si `recorrido.sh` o el flow de `preparar` se van a reutilizar, se archivan fuera antes de borrar.
- "Consumo" la completa el usuario con `perf.py consumo`, y es opcional: no se lo pidas ni lo repitas. `perf.py reporte` y `siguiente` listan las sesiones hechas que no tienen fila, con un comando listo por cada una (sesión, modelo y esfuerzo ya puestos; solo falta el costo), y el total de la investigación queda debajo de la tabla y en los reportes. Pega esas líneas tal cual.
- `perf.py reporte` deja "Siguiente paso" como investigación cerrada.
