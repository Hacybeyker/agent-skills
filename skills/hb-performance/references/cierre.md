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
| `no comparable` | Métrica de frames y la cantidad de frames cambió más de 50 %, o el percentil de un tramo que cambió de duración o de frames más de 30 % (un tramo que se achica deja pocos frames): el valor mide otra cosa |
| `variación del backend` | Las métricas del servidor (TTFB, del flujo, de un tramo o de un servicio): una mejora de la app no las mueve, así que no reciben mejora ni regresión |
| `informativa` | Además de las informativas de siempre, el jank de un tramo con menos de 10 frames (con 3 o 4, un solo frame lento da 25 % o 33 %; el mínimo se cambia con `min_frames` en el tramo o `min_frames_tramo` en el plan): el reporte muestra los frames |
| `sin cambio` | Cualquier otro caso |

Con avisos `dos grupos` (las corridas se separan en dos grupos con un hueco grande entre ellos: la mediana puede caer donde no hay ninguna y el ruido entre medianas subestima la variación) o `marca cambiada entre fases`, el veredicto es orientativo: dilo en la lectura.

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

Genera el reporte en **dos versiones**, con los mismos datos: `reporte-final-dev` (`.md` y `.html`: el técnico) y `reporte-final-gerencia` (una página corta en palabras: qué notaba el usuario, qué se encontró, qué se hizo, el resultado con un gráfico antes y después, el tiempo en segundos, el cambio en porcentaje y su veredicto en palabras, cuántos servicios llama el recorrido y cuánto es espera de servicios, lo pendiente, los riesgos y el costo total; sin nombres de métricas ni percentiles). El de gerencia lo arma `perf.py`; tú solo escribiste su resumen. Los HTML son autocontenidos (estilos y gráficos SVG en línea, sin scripts ni nada que se descargue): se abren sin conexión, se adjuntan a un correo y se imprimen o exportan a PDF en modo claro.

**Gerencia en palabras.** El de gerencia no nombra métricas ni tramos por su nombre interno: usa `etiquetas` del plan (`{"busqueda_ms": "buscar un cliente"}`) y el `titulo` de cada tramo (`{"nombre": "corto", "titulo": "la búsqueda de un nombre corto"}`); si una principal no lo tiene, `reporte` lo avisa con lo que hay que agregar. Los valores salen con la precisión que hace visible la diferencia (745 ms → 741 ms); si al redondear quedan iguales y el veredicto no afirma un cambio, dice "se mantuvo en X", sin porcentaje. Las cantidades por corrida no llevan decimales ("5 o 6 llamadas") y los servicios se nombran en palabras, sin rutas.

**Términos técnicos en el de gerencia.** `perf.py reporte` comprueba lo que escribe la IA y publica ese reporte ("Resumen para gerencia", el síntoma de la Ficha, el síntoma y la causa de los hallazgos confirmados y el título de las mejoras) contra una sola lista, `TECH_TERMS` y `CODE_TERMS` de `perf.py`: nombres de métricas y todo nombre con forma de código (entre acentos graves, con guion bajo, en CamelCase, una llamada `algo()`, un nombre con punto o un archivo `.kt`), `slice`, `CV`, `P90` y otros percentiles, `TTFB`, `TTID`, `TTFD`, `jank`, `doFrame`, `Choreographer`, `RenderThread`, `Perfetto`, traza, `ANR`, `GC`, heap, `OkHttp`, `Retrofit`, corrutinas, `Dispatchers`, `Compose`, `RecyclerView`, `ViewModel`, `StateFlow`, recomposición, endpoint, backend, frames, hilo principal, `ms` y mediana. Si un texto trae alguno, no se publica en la versión de gerencia: queda "sin completar" en ese punto y el comando avisa en qué campo está, qué hacer y el comando para generar de nuevo. Reescríbelo en palabras ("la lista se pedía dos veces", "tarda 2 s") y vuelve a generar. El técnico sí lo publica todo.

El técnico es autocontenido, con gráficos que se explican solos (debajo de cada uno, una frase dice qué muestra y qué significa), cada número con su unidad en la escala que se entiende (segundos o milisegundos) y el cambio en porcentaje, pensado para alguien que no siguió la investigación: resumen ejecutivo; de los hallazgos al resultado (cuántos hallazgos, cuántas mejoras, cuántas aplicadas y cuáles funcionaron ✔ o no ✖; en una mejora a prueba, si su hipótesis quedó confirmada ✔ o refutada ✖); métricas principales con un gráfico de antes, control y después (la mediana, el rango de las corridas y el ruido marcado) y el veredicto en palabras ("mejora clara"; con un reparo, "mejoró, aunque varía mucho entre mediciones: tómalo como orientativo"; "se mantuvo en X"); "Servicios del flujo" (todos los servicios en el orden en que se invocan, por tramo, antes contra después, la espera de servicios, el gráfico de los que más suman y la línea de tiempo de la corrida mediana; informativa); esperado contra logrado; hallazgos con su resultado; mejoras aplicadas; "Cambios de código" (por cada mejora aplicada: los archivos con su repo, un extracto del diff con lo agregado y lo quitado resaltado, por qué se cambió y qué mejoró; el diff completo queda en `cambios/`, lo guarda `decidir --aplicada --archivos` y, sin él, dice "sin diff guardado"; por eso el reporte dev se rotula "interno: contiene código" y esa sección nunca va al de gerencia); lectura de la comparación; comparación completa; las filas de la ficha que sirven al lector; los pendientes ("no son mejoras"); y un glosario ("Cómo leer este reporte"). Sin "Cambios de código" lleva solo métricas agregadas y se puede compartir; con esa sección es **interno** (el reporte lo dice en su subtítulo y `siguiente` también): fuera del equipo, comparte el de gerencia, que nunca lleva código. Lo que en `estado.md` siga con el texto de la plantilla no se publica: el comando avisa qué falta, omite esa sección o pone "sin completar" en la fila; complétalo y vuelve a generar. El reporte inicial (`reporte-inicial-*`, sesión 2) no se toca. Una investigación anterior puede tener `reporte-inicial.*` o `reporte-final.*` con el nombre de antes: se siguen reconociendo, y no se actualizan ni se borran.

## 5. Guarda de regresión

Propón cómo proteger la mejora: el test de la sesión 3 y, si el flujo es crítico y el proyecto lo justifica, un Macrobenchmark del flujo en un PR aparte.

## Entrega

- El resumen ejecutivo y las rutas de `reporte-final-dev.html` y `reporte-final-gerencia.html`.
- Los commits propuestos y el texto del PR, solo con métricas agregadas.
- Pendientes y hallazgos fuera del alcance, para una próxima investigación.
- Cómo validarlo en campo después del release (Android vitals: TTID y TTFD si la app llama a `reportFullyDrawn`).
- "Cambios temporales por revertir" de `estado.md`: se quitan con **un solo comando**, que la sesión termina entregando en un bloque de código (lo imprime `perf.py siguiente`, y es lo primero de la entrega si queda alguna fila sin revertir):
  ```bash
  cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/perf.py cerrar --carpeta <carpeta>
  ```
  Por cada repo de la tabla (la columna "Repo o módulo": una ruta o el nombre de un repo incluido desde fuera por `settings.gradle`) muestra qué archivos quita y cuáles quedan (las mejoras aplicadas y lo que ya estaba modificado al empezar), guarda el parche sin pisar ninguno (en la carpeta de parches de `AGENTS.md` o, sin ella, en `<carpeta>/parches/`), comprueba con `git apply --check -R` que revierte limpio, los quita, muestra `git status --short` y marca las filas como revertidas en `estado.md`, con la ruta del parche. Con `--simular` solo muestra qué haría. **Nunca** usa `git checkout`, `git restore`, `git reset --hard` ni `git clean` (borran el archivo entero sin guardarlo), y no los propongas ni los corras tú. Si algo no revierte limpio, o una fila no tiene la ruta completa del archivo (con `...` o varios archivos en una celda), se detiene sin tocar nada y dice por qué: corrige la fila y repite. Un archivo que también es de una mejora aplicada, o que otra investigación abierta declara, se queda, con el motivo, y se quita a mano solo lo temporal. Si una fila dice en "Qué es" que es el **setup** de medición, va en un parche aparte (`perf-setup-…`) y `AGENTS.md` queda con la línea "Setup listo, en parche: `git apply <parche>` antes de medir; `git apply -R` al terminar" y el bloque de estado al día.
- **Los reportes tienen que ser posteriores a la última medición.** Si una fase se midió (o se rehízo) después del reporte final, `siguiente` vuelve a ofrecer esta sesión con el motivo: compara de nuevo y genera los reportes con los datos de ahora.
- Limpieza, cuando se mergee: las trazas (`antes/`, `control/`, `despues/`, `prueba/`) y los heap dumps se borran; `metricas.csv`, los `.md` y el reporte se pueden conservar. `reports/` no está en git: si `recorrido.sh` o el flow de `preparar` se van a reutilizar, se archivan fuera antes de borrar.
- Los comandos y los textos para pegar van siempre en un bloque de código: fuera de él, el chat puede comerse los `*` de una ruta o un patrón. El texto confiable es el que imprime `perf.py siguiente`.
- "Consumo" la completa el usuario con `perf.py consumo`, y es opcional: no se lo pidas ni lo repitas. `perf.py reporte` y `siguiente` listan las sesiones hechas que no tienen fila, con un comando listo por cada una (sesión, modelo y esfuerzo ya puestos; solo falta el costo), y el total de la investigación queda debajo de la tabla y en los reportes. Pega esas líneas tal cual.
- `perf.py reporte` deja "Siguiente paso" como investigación cerrada.
