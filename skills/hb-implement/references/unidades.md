# Unidades: módulos, paquetes y repos vecinos

Una **unidad** es una parte del proyecto que se cambia, se verifica y a veces se publica por separado: un módulo del build, un paquete de un espacio de trabajo, la carpeta de una feature o un repo vecino. El **modelo** de `AGENTS.md` (`## Estructura`, que escribe `hb-setup`) dice qué unidades hay y cómo se trabaja con cada una: su identificador, su **fuente** (`.`, `app/`, `../core-lib`), cómo la consume la app, cómo pasarla a fuente y volver, su DoD, su repo y rama principal, y quién la publica y versiona.

Sin `## Estructura`, lee `### Repos relacionados` de `## Arquitectura` (el formato anterior): cada fila es una unidad cuya fuente es la columna "Ruta" y cuyo mecanismo es "Cómo se incluye en local" (con "pasar a código local con …; volver con …"). Ese formato no trae la URL del remoto ni la rama principal: si te hacen falta, pregúntalas. Sin ninguno de los dos, sigue con lo que veas en el proyecto y ofrece `hb-setup`.

Si lo que encuentras no coincide con el modelo (una unidad que no está, una ruta que cambió, un mecanismo distinto), corrígelo en `## Estructura`, sobre la ruta real de `AGENTS.md` (`realpath AGENTS.md`), y dilo en la entrega.

## 1. Qué unidades toca la tarea

Antes del plan, lista las unidades que la tarea **cambia** y las que solo **lee**, con su identificador. Para cada una que vas a cambiar, lee su mapa del módulo (sección 0 de `SKILL.md`).

**Confirma que el código entra en el build.** Antes de editar un archivo, comprueba que es el código que la app compila:

- Con el modelo: "Es la app" y "En fuente (módulo del build)" se compilan con la app; "Publicada" no: la app usa el artefacto de la versión fijada, y editar su fuente no cambia nada en la app hasta pasarla a fuente (sección 3) o publicarla.
- Si el modelo no alcanza (una carpeta que no figura, código generado, una variante que excluye archivos), pregúntaselo a la herramienta de build del proyecto: la declaración de módulos, el árbol de dependencias o la lista de fuentes de la variante. No lo deduzcas del nombre de la carpeta.

## 2. Deja listo el repo vecino

Para cada unidad que vas a tocar y cuya fuente está fuera del repo principal (`../core-lib`):

| Cómo está | Qué haces |
| --- | --- |
| La carpeta no existe y el modelo trae la URL ("Repo y rama principal") | `git clone <URL> <fuente>`, en la ruta de la columna "Fuente" |
| La carpeta no existe y no hay URL | Pregunta la URL; con el alcance aprobado, detente en ese punto y anótalo |
| Limpia, en su rama principal y atrasada | `git -C <fuente> fetch` y `git -C <fuente> pull --ff-only` |
| Con cambios sin commit, o en otra rama que no es la principal ni la de esta tarea | **Pregunta** antes de tocarla: pueden ser de otra tarea |
| El agente no puede leer la carpeta | **Detente** y di qué carpeta debe darte acceso: la ruta del modelo y la absoluta que resulta. Cada agente tiene su forma de sumar directorios de trabajo. No supongas su contenido |

- "Atrasada" es que `git -C <fuente> rev-list --count HEAD..@{u}` da más de 0 después del `fetch`. Si `pull --ff-only` falla, no fuerces nada: pregunta.
- Lo registrado en "Configuración local modificada a propósito" (también un archivo del repo vecino) no cuenta como cambio sin commit.
- **Con la línea `Repos vecinos: no clonar ni crear ramas`** en `## Estructura`, no clones, no actualices ni crees ramas en ningún repo de la tarea, tampoco en el principal: propón los comandos y sigue con lo que hay. Si sin el repo no puedes seguir, detente en ese punto. Sin la línea, vale `Repos vecinos: clonar los que falten y crear ramas de trabajo`.

## 3. Pasa a fuente sin preguntar

Si la tarea cambia una unidad **publicada** y el modelo trae su mecanismo (columna "Pasar a fuente y volver", "A fuente: …; volver: …"):

1. Aplica el cambio "A fuente" **sin preguntar**: es el mecanismo que el proyecto documenta.
2. Compila la app (o el comando del DoD del proyecto que compila) para comprobar que ahora usa el código local. Si no compila por el cambio de configuración, vuelve al estado anterior con "volver" y dilo; si compila, sigue.
3. Ese cambio de configuración es **temporal**: va en `temporary` del meta con su forma de volver (sección 7), nunca se propone para commit y la entrega dice cómo revertirlo. Si `AGENTS.md` pide revertirlo al terminar, hazlo después del DoD, deshaciendo solo ese cambio (nada de `git checkout` ni `git restore` sobre un archivo que tenga otros cambios).

- Si el archivo del mecanismo está en "Configuración local modificada a propósito", lo que ya tenía no es un cambio ajeno ni de esta tarea: no avises por él. Si la unidad ya estaba en fuente, no hay nada que hacer; si agregaste una, solo esa parte va en `temporary`.
- Los cambios en el **código** de la unidad sí son de la tarea: su repo va en `repos` del meta y sus commits se proponen aparte.
- Si solo necesitas **leer** una unidad publicada, lee su fuente en su repo; no hace falta pasarla a fuente. No deduzcas su comportamiento del artefacto compilado.

### Sin mecanismo

Si la columna dice `sin mecanismo` (o el modelo no trae ninguno), no inventes uno ni edites los archivos de build de la app para forzarlo:

- Trabaja **solo en el repo de la unidad**: el cambio, sus tests y su DoD.
- Avisa en la entrega que el cambio **llega a la app cuando se publique** la unidad y la app suba la versión fijada (sección 8).
- Si encuentras un mecanismo que el modelo no registra, propónlo como corrección del modelo.

## 4. Versión fijada frente al fuente

Para cada unidad publicada que pasaste a fuente, compara la versión que fija la app (columna "Cómo se consume") con lo que hay en su fuente: `git -C <fuente> describe --tags --always`. Si no coinciden (el fuente va por delante o por detrás del tag de esa versión), lo que pruebes puede no compilar o comportarse distinto con lo publicado: avísalo en la entrega y pon `pinned_version` en la entrada de `repos` (sección 7), para que el reporte lo muestre. No cambies de commit por tu cuenta para igualarlas: dilo y sigue.

## 5. Rama de trabajo en cada repo que modificas

Antes de editar un repo (el principal o un vecino), crea la rama de trabajo desde su rama principal al día:

- El nombre sigue `## Git`. Si no fija nada, `<tipo>/<slug>`: `feat` para feature y enhancement, `fix` para bugfix, `refactor` para refactor. **La misma rama** en cada repo que la tarea modifica.
- Si el repo ya está en una rama que no es la principal, sigue en ella.
- No crees ramas con la línea `Repos vecinos: no clonar ni crear ramas`, ni si `## Git` u otra regla dice que la IA no cambia de rama: propón el nombre y sigue en la rama actual.
- Commit y push siguen las reglas de `## Git` ("quién commitea"): crear la rama no autoriza a commitear.

## 6. DoD de cada unidad tocada

- Corre el **DoD de cada unidad que cambiaste**: la columna "DoD de la unidad", con su `cd`. Si dice `el ## DoD del proyecto`, ese.
- Si cambiaste la app o pasaste unidades a fuente, corre además el `## DoD` del proyecto: es el que compila la app con ellas.
- Una unidad sin DoD en el modelo: el `## DoD` del `AGENTS.md` de su repo. Si tampoco hay, dilo y propón agregarlo al modelo.
- Cada paso entra al DoD del reporte con el nombre de la unidad (por ejemplo, `core-lib · Tests`).

## 7. Un solo reporte con varios repos

El reporte compara cada repo contra su base: sin `base`, el `merge-base` de `HEAD` con su rama principal, así sale lo ya commiteado en la rama de trabajo. Si `AGENTS.md` fija otra base, pásala en `base` (y `--base` para el principal).

```json
{
  "repos": [
    { "path": "../core-lib", "name": "core-lib", "main_branch": "main", "pinned_version": "2.3.1" }
  ],
  "files": {
    "src/payment_screen.ts": { "before": "Qué limitación había.", "after": "Qué mejora el cambio." },
    "core-lib:payments/validator.py": { "why": "Qué aporta al diseño." }
  },
  "temporary": [
    { "path": "local-modules.json", "why": "Pasa core-lib a fuente.", "revert": "\"core-lib\": false en local-modules.json" }
  ]
}
```

- `path`: la fuente de la unidad, relativa a la raíz del repo principal (o absoluta). `name`: el prefijo de sus claves; por defecto, el nombre de la carpeta.
- `main_branch`: su rama principal, la de "Repo y rama principal" del modelo. Sin ella, el script prueba `origin/HEAD`, `origin/main`, `origin/master`, `main` y `master`; si no encuentra ninguna, compara contra `HEAD` y avisa. La del principal va en `--main-branch`.
- `base`: una base explícita, que manda sobre `main_branch`.
- `pinned_version`: la versión que fija la app. `source_version`, opcional: lo que dio `git describe --tags --always` en el fuente; sin ella, el script describe la base del repo. Si no coinciden, el reporte lo muestra como aviso.
- Las claves del principal no llevan prefijo; las de un vecino, `<name>:<ruta>`. `groups` y `temporary` usan las mismas claves.
- Una entrada con `"path": "."` solo le pone nombre, base o rama principal al principal (`--base` y `--main-branch` mandan sobre ella).
- Si un repo de `repos` no se puede leer, el script termina sin escribir nada y dice qué carpeta falta.

## 8. Orden de integración

En la entrega, por cada unidad **publicada** que cambiaste, en este orden:

1. **PR del módulo** en su repo, desde su rama de trabajo.
2. **Release del módulo** en su repo, con `hb-release` (o como diga "Publica y versiona": por ejemplo, el workflow que publica al crear el tag).
3. **PR de bump en la app**: sube la versión fijada al número nuevo y vuelve la unidad a publicada.

- La configuración que pasa a fuente **nunca se commitea**, en ningún paso.
- Las unidades "En fuente (módulo del build)" no tienen release propio: van en el PR del repo donde viven.
- Los commits propuestos van **por repo**, en ese orden, cada uno con la rama de trabajo de su repo.
- Cada cambio temporal con su forma de revertirlo, o "revertido".
