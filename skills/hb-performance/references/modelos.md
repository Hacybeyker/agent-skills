# Modelo, razonamiento y costo por sesión

La skill no puede elegir el modelo: lo recomienda en "Siguiente paso" de `estado.md`, con el nombre exacto que haya en `modelos` de `plan.json` (`economico`, `intermedio`, `diagnostico`, `alto`; por defecto Haiku 5.5, Sonnet 5.5, Sonnet 5.5 y Opus 5.5). Con otra herramienta (Copilot, Cursor), cambia esos nombres una vez en el plan.

`diagnostico` es el modelo de la sesión 2 y es opcional: un plan sin `diagnostico` (por ejemplo, uno creado antes de que existiera) usa su `intermedio`, así que nada cambia si no lo tocas. Sirve para bajar el modelo de lo mecánico (setup, ficha y mejoras usan `intermedio`) sin bajar el del diagnóstico, o para subir solo el diagnóstico.

## Por qué se encarece

Cada paso del agente reenvía todo el chat. El costo de una sesión es, a grandes rasgos, **pasos × tamaño promedio del contexto × precio del modelo**. Lo que lo dispara:

1. **Encadenar sesiones en un chat.** El contexto crece en cada paso y nunca baja: con cuatro sesiones en un chat, el promedio llega a cientos de miles de tokens por paso. Un chat nuevo por sesión arranca con unos pocos miles (`SKILL.md`, la referencia y `estado.md`).
2. **Pasos de exploración.** Escribir y corregir consultas SQL una por una, leer scripts para entender cómo usarlos, volcar logs o diffs. `perf.py diagnostico` y `--help` reemplazan casi todo eso.
3. **El modelo superior en todas las sesiones**, o razonamiento máximo, o variantes de ventana de 1M: dejan crecer el contexto y cobran más por cada token.

## Recomendación

| Sesión | Modelo | Razonamiento | Pasos máx. |
| --- | --- | --- | --- |
| 0 · Setup | Intermedio | Medio | 40 |
| 1 · Ficha y plan (si no hay receta) | Intermedio | Medio | 15 (25 en flujos largos) |
| Mediciones | Ninguno en modo guiado (las corre el usuario); el más económico en modo autónomo | Bajo | — |
| 2 · Diagnóstico | Diagnóstico (por defecto el intermedio); el alto solo si el caso se complica | Alto | 25 |
| 3 · Mejora (una por chat) | Intermedio | Medio | 30 |
| 4 · Cierre | Económico o intermedio | Bajo | 10 |

Si una sesión llega a su tope de pasos, guarda el estado y se detiene: seguir en el mismo chat cuesta cada vez más por paso.

## Costos de referencia

Dos investigaciones reales en una app mediana con red (modelo intermedio salvo el cierre):

| Sesión | Arranque en frío (receta) | Pantalla de detalle (con sesión 1) |
| --- | --- | --- |
| 0 · Setup | 1,4 USD · 42 pasos | 2 USD · 66 pasos (cableado a mano y DoD por partes: lo que `instrumentar` genera ahora) |
| 1 · Ficha y plan | — | 1,1 USD · 35 pasos (preguntas sueltas y una captura manual intentada por el agente) |
| 2 · Diagnóstico (alto) | 0,8 USD · 21 pasos | ≈ 0,8 USD |
| 3 · Mejora (medio) | 1 USD · 40 pasos | 1 USD · 30 pasos |
| 4 · Cierre (económico, bajo) | 0,02 USD · 12 pasos | 0,02 USD · 7 pasos |
| Mediciones y decisión (terminal) | 0 | 0 |
| **Total** | **≈ 4,3 USD** | **≈ 5 USD** |

Con 0.5.0 (recorrido automático por `adb`, `preparar`, ventana entre marcas y reportes nuevos), dos investigaciones más en la misma app: una rigurosa de la pantalla de detalle, ≈ 5,9 USD (setup 1,65 · sesión 1 2,28 · sesión 2 0,69 · sesión 3 1,25 · cierre 0,02), y una de triage y luego rigurosa de favoritos, ≈ 4,6 USD (sesión 1 2,27 · sesión 2 1,15 · sesión 3 1,11 · cierre 0,02), con una mejora medida de −65 %. La sesión 1 es hoy la más cara: la mitad de sus pasos se van en encontrar y validar las coordenadas del recorrido.

Un chat abierto solo para leer `estado.md` cuando el paso era un comando costó 0,2 USD: por eso `siguiente` dice en cada paso si va en la terminal o en un chat. Una sesión que cuesta varias veces lo de la tabla suele estar explorando: SQL a mano, leyendo scripts o archivos generados, volcando logs, corriendo el DoD comando por comando o encadenada con otra en el mismo chat.

## Cómo aplicarlo

- **Retomar un chat cortado:** con el comando de tu herramienta que reabre una sesión eligiéndola de una lista (`claude --resume`, `copilot --resume`), no con el que continúa "la última".
- **Sin configurar nada:** un chat nuevo por sesión, eligiendo el modelo y el razonamiento en el selector antes de escribir. El texto y el modelo para el chat nuevo están en "Siguiente paso" (los escribe `perf.py siguiente`).
- **Con un agente por sesión:** un agente personalizado con su modelo, sus herramientas limitadas (por ejemplo, que el de mediciones no pueda editar código) y la instrucción de seguir esta skill en su sesión.
  - **Claude Code:** subagentes en `.claude/agents/*.md`, con `model` en el frontmatter.
  - **Copilot en VS Code:** archivos `.agent.md`, con `model` y `tools`. Verifica si el traspaso entre agentes conserva la conversación: si la conserva, ahorra menos que un chat nuevo.
  - Para que no entren al repo: en la carpeta de agentes del usuario, o con un enlace excluido en `.git/info/exclude`.
- **Subagentes:** si la plataforma los tiene, delega el mapeo del alcance a uno económico y pide que devuelva solo un resumen corto.

## Medir el costo

1. Al cerrar cada chat, el usuario anota el costo desde la terminal, sin volver al chat: `perf.py consumo --carpeta <carpeta> --sesion "3 · M1" --costo "1.05 USD" --modelo "Sonnet 5.5" --pasos 30` (lo que muestre su herramienta: `/cost` en Claude Code, créditos en Copilot).
2. Para comparar versiones de la skill, repite el mismo caso (mismo alcance y mismos flujos) y separa los efectos: una corrida con el mismo modelo que la anterior (ahorro por diseño) y otra con los modelos de esta tabla (ahorro total).
3. Repite cada una al menos dos veces: el consumo de un agente varía de una corrida a otra.
4. Comprueba que las conclusiones y los veredictos se mantengan: ahorrar no puede costar rigor.
