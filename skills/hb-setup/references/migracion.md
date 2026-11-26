# Migrar el contexto de IA que ya tiene el proyecto

Un proyecto puede llegar con contexto de IA escrito antes del estándar: un `AGENTS.md` largo, una copia renombrada (`AGENTS-old.md`), un `CLAUDE.md` con instrucciones, las reglas de otro agente o protocolos sueltos en la carpeta de contexto. Ese texto suele guardar conocimiento que no está en el código: errores del build con su mensaje exacto, qué versión se publica desde cada rama, unidades que no siguen el patrón, cómo se sincroniza el espacio de trabajo.

**Un `AGENTS.md` ligero no significa omitir.** Lo esencial va en `AGENTS.md`; el resto, a docs específicos referenciados en "Documentos"; lo que se descarta, con su motivo. Nada se pierde en silencio.

## 1. Encuentra las fuentes

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py fuentes [--carpeta <carpeta de contexto>] [--fuente <archivo>]
```

Solo lee. Busca, aunque no exista `AGENTS.md`:

| Fuente | Qué pasa con ella |
| --- | --- |
| `AGENTS.md` | Se reescribe en su lugar |
| Copias de `AGENTS.md` o `CLAUDE.md`: `AGENTS-old.md`, `AGENTS.bak.md`, `AGENTS.v1.md`, `AGENTS-<fecha>.md`, `AGENTS copy.md`, `AGENTS.md.orig`, `AGENTS.md~`, en la raíz, `docs/`, `.claude/` o la carpeta de contexto. Un nombre con otra palabra (`claude-api.md`, `AGENTS.override.md`) no es una copia | Se reemplaza: por defecto, se propone borrarla después de migrar |
| `CLAUDE.md` o `.claude/CLAUDE.md` con algo más que `@AGENTS.md` | Queda con `@AGENTS.md` y solo lo propio de Claude Code |
| `.github/copilot-instructions.md`, `.github/instructions/`, `.cursorrules`, `.cursor/rules/`, `GEMINI.md`, `.junie/guidelines.md`, `.windsurfrules`, `.clinerules` | Su contenido pasa al estándar y el archivo queda como puntero a `AGENTS.md`: esa herramienta lo sigue leyendo, así que no se borra |
| Los `.md` de la carpeta de contexto (también si es un enlace simbólico) que traen instrucciones para agentes | Se traspasa o se queda como doc, con su fila en "Documentos" |
| En las otras carpetas de la raíz enlazadas o en `.git/info/exclude` (sin contar repos vecinos ni worktrees): las copias de `AGENTS.md`; sus demás `.md` solo se nombran | Las copias se reemplazan; si otro `.md` es contexto, pásalo con `--fuente` o corre con `--carpeta <esa carpeta>` |

Con alguna fuente, el camino es **migrar**; sin ninguna, la plantilla. No son fuentes: lo que ya está en "Documentos", las salidas de las skills (`reports/`, `modules/`, `perf/` y las carpetas de las líneas `Carpeta de reportes:`, `Carpeta de investigaciones:` y la `Carpeta:` de `## Producto`; si una de esas es la carpeta de contexto misma, solo sus subcarpetas `{fecha}-{slug}` o los archivos de `hb-product`) ni un archivo que solo remite a `AGENTS.md`. Un `AGENTS.md` o `CLAUDE.md` dentro de la carpeta de contexto es una copia. Los `.md` de la carpeta de contexto que no parecen instrucciones solo se nombran: si alguno lo es, pásalo con `--fuente <archivo>` (a `fuentes` y a `verificar`).

**Antes de reescribir una fuente en su lugar** (`AGENTS.md`, `CLAUDE.md`, el archivo de otro agente), guarda una copia suya fuera del repo: `verificar` compara contra ella (`--previo <ruta>=<copia>`, una por fuente). Si la fuente está en git, sin `--previo` usa la de `HEAD`. Los punteros a `AGENTS.md`, mejor después de verificar.

## 2. El inventario de traspaso

`fuentes` imprime una tabla con una fila por sección de cada fuente (las largas, por subsección) y un destino sugerido. Tú decides el destino de cada fila; cada una termina en uno de tres:

| Destino | Qué va | Cómo se escribe en la columna Destino |
| --- | --- | --- |
| `AGENTS.md` | Lo que se usa en casi todas las tareas, en su sección del estándar: stack, comandos, DoD, unidades y sus excepciones, reglas, git, versionado (por ejemplo, qué versión se publica desde cada rama) | `AGENTS.md` (en Motivo, la sección: `## Versionado y release`) |
| Un doc | Lo extenso o de una situación concreta: los errores frecuentes del build con sus mensajes exactos (`troubleshooting.md`), la publicación paso a paso, la sincronización del espacio de trabajo, catálogos de rutas o deep links. Va en la carpeta de docs del modo, con su fila en "Documentos" y un "Léelo cuando…" concreto | la ruta del doc: `` `contexto/docs/troubleshooting.md` `` |
| Descartada | Lo obsoleto, lo que contradice el código (pregúntalo antes: no lo decidas tú), lo que ya cubre un perfil `hb-stack-*` (explicaciones de arquitectura, SOLID, testing o seguridad general) o una skill `hb-*` (un protocolo de bugfix, una plantilla de reporte) | `descartada`, con el motivo en su columna |

Lo propio de una herramienta (lo que solo sirve en Claude Code, por ejemplo) puede quedarse en su archivo: el destino es su propia ruta (`` `CLAUDE.md` ``), y `verificar` comprueba que ese archivo la sigue teniendo.

- **Decide cada fila:** una sugerencia que dice "decide" o que trae `<docs>` sin reemplazar no es un destino, y `verificar` la rechaza.
- **No copies a mano lo que el doc puede llevar tal cual:** una tabla de errores con sus mensajes exactos pasa entera al doc, sin resumirla.
- Una fila `(todo el archivo)` cubre una fuente entera (una fuente corta, o un protocolo que se descarta).
- Una sección larga puede ir entera o por partes (`Build › (inicio)`, `Build › Errores frecuentes`): cada parte con su destino.
- Guarda el inventario completo fuera del repo y muéstralo en el resumen final.

```markdown
| Fuente | Sección | Destino | Motivo o "Léelo cuando…" |
| --- | --- | --- | --- |
| `contexto/AGENTS-old.md` | Stack | AGENTS.md | ## Stack |
| `contexto/AGENTS-old.md` | Build › Errores frecuentes | `contexto/docs/troubleshooting.md` | El build falle: trae los mensajes exactos |
| `contexto/AGENTS-old.md` | Publicación | AGENTS.md | ## Versionado y release |
| `contexto/AGENTS-old.md` | Protocolo de bugfix | descartada | ya lo cubre hb-implement; la etiqueta de los tickets pasó a ## Git |
| `contexto/AGENTS-old.md` | Historial | descartada | obsoleta: describe una migración terminada |
```

## 3. Lo de otras skills, tal cual

Todo bloque entre `<!-- hb-<skill>:<nombre> -->` y `<!-- /hb-<skill>:<nombre> -->`, y las secciones propias de otras skills (`## Rendimiento` de `hb-performance`, `## Producto` de `hb-product`), pasan al `AGENTS.md` nuevo **tal cual**, con su título y su contenido, vengan del `AGENTS.md` o de una fuente renombrada. `contexto.py rendimiento` y `contexto.py producto` los buscan también en las fuentes previas y dicen de cuál vienen. Lo que convenga cambiar dentro de esas secciones (un serial de dispositivo, una línea que contradice el bloque) va en el resumen como propuesta: no lo reescribes.

## 4. Nada inventado

`hb-setup` nunca agrega por su cuenta reglas propias de un proyecto: migraciones de lenguaje o de librerías, convenciones de un equipo, excepciones. Esas las escribe el usuario, a mano o pidiéndoselas a la IA. El setup solo conserva lo que ya está escrito en las fuentes previas de ese mismo proyecto, **tal cual** y en la sección que corresponde del estándar. `## Modernización` arranca en "ninguna decidida" salvo que una fuente ya registre una decisión. Si algo de una fuente contradice el código o el perfil, pregunta cuál vale.

## 5. Skills locales que se solapan

Un protocolo, una plantilla o una skill del proyecto (en la carpeta de contexto, `.claude/skills/`, `.agents/skills/`, `.claude/commands/` o `.github/prompts/`) que cubre lo mismo que una skill `hb-*` (reporte de cambios, bugfix, review, commits, release) lo marca `fuentes` con la skill con la que se solapa. En el resumen di qué cubre ya la skill, qué es propio del proyecto (eso va a `AGENTS.md` o a un doc; puedes anotarlo con su fila en el inventario, aunque no es obligatoria) y propón retirarla. **No la borres:** retirarla es decisión del usuario.

## 6. Verifica

```bash
cd <raíz-del-proyecto> && python3 -I <carpeta-de-la-skill>/scripts/contexto.py verificar --inventario <archivo> [--previo <ruta>=<copia>]... [--fuente <archivo>]...
```

Solo lee. `--previo` y `--fuente` se repiten (una vez por fuente); `--inventario -` lo lee de la entrada. Sale con error si una sección de una fuente no tiene destino, si el inventario nombra una fuente que ya no encuentra (reescrita sin copia), si un doc no está escrito o no tiene su fila en "Documentos" con su "Léelo cuando…", si una descartada no tiene motivo, si un bloque o una sección de otra skill no quedó tal cual, o si `AGENTS.md` o "Documentos" referencian una fuente que se reemplaza. Avisa si una regla de `## Reglas del proyecto` o de `## Modernización` no viene de ninguna fuente previa (si no la pidió el usuario, sobra), si una regla de una fuente no quedó tal cual y si `AGENTS.md` pasa de 150 líneas (lo que no entra va a un doc; nunca se omite).

## 7. La fuente vieja

Una fuente que se reemplaza **no se enlaza**: "Documentos" nunca la referencia, aunque se conserve. Con `verificar` en verde:

- Las copias de `AGENTS.md` o `CLAUDE.md`: pregunta si se conservan; por defecto, propón borrarlas. Las borras solo con la aprobación del usuario; en el modo versionado, el borrado va en el diff que muestras.
- `CLAUDE.md` y los archivos de otros agentes: quedan como puntero a `AGENTS.md` (`@AGENTS.md` donde la herramienta importa archivos; si no, una línea que remita a él), con lo propio de esa herramienta. No se borran: esa herramienta los sigue leyendo.
