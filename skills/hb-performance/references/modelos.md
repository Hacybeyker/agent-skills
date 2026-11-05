# Modelo, razonamiento y costo por sesión

La skill no puede elegir el modelo: lo recomienda en "Siguiente paso" de `estado.md`.

## Por qué se encarece

Cada paso del agente reenvía todo el chat. El costo de una sesión es, a grandes rasgos, **pasos × tamaño promedio del contexto × precio del modelo**. Lo que lo dispara:

1. **Encadenar sesiones en un chat.** El contexto crece en cada paso y nunca baja: con cuatro sesiones en un chat, el promedio llega a cientos de miles de tokens por paso. Un chat nuevo por sesión arranca con unos pocos miles (`SKILL.md`, la referencia y `estado.md`).
2. **Pasos de exploración.** Escribir y corregir consultas SQL una por una, leer scripts para entender cómo usarlos, volcar logs o diffs. `perf.py diagnostico` y `--help` reemplazan casi todo eso.
3. **El modelo superior en todas las sesiones**, o razonamiento máximo, o variantes de ventana de 1M: dejan crecer el contexto y cobran más por cada token.

## Recomendación

| Sesión | Modelo | Razonamiento | Pasos máx. |
| --- | --- | --- | --- |
| 0 · Setup | Intermedio | Medio | 40 |
| 1 · Ficha y plan (si no hay receta) | Intermedio | Medio | 15 |
| Mediciones | Ninguno en modo guiado (las corre el usuario); el más económico en modo autónomo | Bajo | — |
| 2 · Diagnóstico | Intermedio; el superior solo si el caso se complica | Alto | 25 |
| 3 · Mejora (una por chat) | Intermedio | Medio | 30 |
| 4 · Cierre | Económico o intermedio | Bajo | 10 |

Si una sesión llega a su tope de pasos, guarda el estado y se detiene: seguir en el mismo chat cuesta cada vez más por paso.

## Cómo aplicarlo

- **Sin configurar nada:** un chat nuevo por sesión, eligiendo el modelo y el razonamiento en el selector antes de escribir. El texto para el chat nuevo está en "Siguiente paso".
- **Con un agente por sesión:** un agente personalizado con su modelo, sus herramientas limitadas (por ejemplo, que el de mediciones no pueda editar código) y la instrucción de seguir esta skill en su sesión.
  - **Claude Code:** subagentes en `.claude/agents/*.md`, con `model` en el frontmatter.
  - **Copilot en VS Code:** archivos `.agent.md`, con `model` y `tools`. Verifica si el traspaso entre agentes conserva la conversación: si la conserva, ahorra menos que un chat nuevo.
  - Para que no entren al repo: en la carpeta de agentes del usuario, o con un enlace excluido en `.git/info/exclude`.
- **Subagentes:** si la plataforma los tiene, delega el mapeo del alcance a uno económico y pide que devuelva solo un resumen corto.

## Medir el costo

1. Al cerrar cada sesión, anota en "Consumo" de `estado.md` el modelo, el costo o los tokens que muestre la herramienta (`/cost` en Claude Code) y los pasos.
2. Para comparar versiones de la skill, repite el mismo caso (mismo alcance y mismos flujos) y separa los efectos: una corrida con el mismo modelo que la anterior (ahorro por diseño) y otra con los modelos de esta tabla (ahorro total).
3. Repite cada una al menos dos veces: el consumo de un agente varía de una corrida a otra.
4. Comprueba que las conclusiones y los veredictos se mantengan: ahorrar no puede costar rigor.
