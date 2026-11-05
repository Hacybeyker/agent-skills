# Modelo y razonamiento por sesión

La skill no puede elegir el modelo: lo recomienda en "Siguiente paso" de `estado.md`. Lo que más encarece una investigación es un modelo caro con razonamiento muy alto, en un chat largo que nunca se reinicia.

| Sesión | Modelo | Razonamiento |
| --- | --- | --- |
| 0 · Setup | Intermedio | Medio |
| 1 · Ficha y plan | Intermedio | Medio |
| Mediciones | Ninguno en modo guiado (las corre el usuario); el más económico en modo autónomo | Bajo |
| 2 · Diagnóstico | Intermedio; el superior solo si el caso se complica | Alto |
| 3 · Mejoras | Intermedio | Medio |
| 4 · Cierre | Económico o intermedio | Bajo |

No uses razonamiento máximo ni variantes de ventana de 1M para este trabajo: dejan crecer el contexto y cada paso lo reenvía entero.

## Cómo aplicarlo

- **Sin configurar nada:** un chat nuevo por sesión, eligiendo el modelo y el razonamiento en el selector antes de escribir.
- **Con un agente por sesión:** un agente personalizado con su modelo, sus herramientas limitadas (por ejemplo, que el de mediciones no pueda editar código) y la instrucción de seguir esta skill en su sesión.
  - **Claude Code:** subagentes en `.claude/agents/*.md`, con `model` en el frontmatter.
  - **Copilot en VS Code:** archivos `.agent.md`, con `model` y `tools`. Verifica en su documentación qué campos respeta cada motor (por ejemplo, el esfuerzo de razonamiento) y si el traspaso entre agentes conserva la conversación: si la conserva, ahorra menos que un chat nuevo.
  - Para que no entren al repo: en la carpeta de agentes del usuario, o con un enlace excluido en `.git/info/exclude`.
- **Subagentes:** si la plataforma los tiene, delega el mapeo del alcance (sesión 1) o una corrida autónoma a uno económico, y pide que devuelva solo un resumen corto.

## Verificar el costo

1. Repite el mismo caso (mismo alcance y mismos flujos) y anota los créditos o tokens de cada sesión en "Decisiones" de `estado.md`.
2. Separa los efectos: una corrida con la misma configuración de modelo que la anterior (ahorro por diseño) y otra con los modelos de esta tabla (ahorro total).
3. Repite cada una al menos dos veces: el consumo de un agente varía de una corrida a otra.
4. Comprueba que las conclusiones y los veredictos se mantengan: ahorrar no puede costar rigor.
