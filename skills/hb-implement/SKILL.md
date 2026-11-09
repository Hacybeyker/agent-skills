---
name: hb-implement
description: 'Implementa features, bugfixes, mejoras y refactors en proyectos con AGENTS.md: lee las reglas y el stack del proyecto, carga su perfil hb-stack-*, implementa por capas con tests, corre el DoD del proyecto y genera un reporte HTML desde git. Úsala cuando el usuario pida crear o implementar una feature, corregir un bug o un issue, mejorar algo o refactorizar ("crea la feature X", "implementa Y", "corrige el bug Z", "resuelve el issue #N", "mejora X", "refactoriza Y", "/hb-implement").'
license: MIT
compatibility: "Requiere git y, para el reporte HTML, Python 3.8+ solo con su librería estándar (en macOS viene con las Command Line Tools). Opcional: la CLI android de Google para dibujar los previews de Compose."
metadata:
  author: hacybeyker
  version: "1.4.0"
  category: flow
  origin: "basada en feature-implementation (Android y KMP)"
---

# hb-implement

El flujo es el mismo para cualquier stack. La arquitectura, los comandos y las reglas salen del proyecto (`AGENTS.md`) y de su perfil `hb-stack-*`.

## 0. Contexto

1. Lee `AGENTS.md`. **Si no existe, no apliques este flujo**: avísalo y ofrece crearlo con `hb-setup`, o seguir sin él.
2. Toma de `AGENTS.md`:
   - `## Stack` y `## Arquitectura`: el perfil (`hb-stack-<familia>`), la variante y el stack **real** del proyecto; se implementa con ese stack. `## Modernización`: lo único que se puede migrar.
   - `## DoD`: los comandos de verificación, en orden.
   - Las reglas propias: quién commitea, changelog, idioma, prohibiciones.
3. Carga el perfil y **solo** las referencias que la tarea necesita.
4. Clasifica la tarea: `feature`, `bugfix`, `enhancement` o `refactor`.
5. Revisa `git status`. El reporte compara contra `HEAD`, así que si ya hay cambios sin commitear que no son de esta tarea, avísalo antes de empezar.

## 1. Plan

- **Criterios de aceptación.** Si el pedido no los trae, escríbelos en formato Given / When / Then, y confírmalos si el pedido es ambiguo.
- Lista los archivos que vas a crear, modificar o eliminar, por capa, y los patrones de diseño que vas a aplicar y por qué (ver los principios del perfil: SOLID, GRASP, GoF, KISS, YAGNI, DRY).
- **Presenta el plan y espera confirmación** si la tarea toca más de una feature, cambia un contrato público (API, esquema de base de datos, navegación compartida), agrega dependencias o exige una decisión de arquitectura. Si no, sigue. La excepción es el alcance aprobado (abajo).

### Con el alcance aprobado (modo autónomo o subagente)

Si el pedido trae un alcance aprobado (un documento de alcance, un `PLAN.md` o un brief que dice "el plan ya está aprobado", "sin aprobaciones"), o corres como subagente de un orquestador, **no esperes la confirmación del plan**: el pedido ya la dio. El resto del flujo no cambia.

- **Decide y anota.** Cuando el alcance sea ambiguo o se contradiga, o debas elegir algo que una persona querría revisar, elige la opción más conservadora y reversible, anótala y sigue. Cada decisión: qué, por qué, la alternativa descartada y dónde se aplicó.
- **Dónde se anota:** en el archivo que indique el pedido (por ejemplo `decisiones.md`). Si no indica ninguno, en "Decisiones" de la entrega. No inventes archivos.
- **Para revisar:** lo que cambia una regla del alcance para cumplir otra, un contrato, una dependencia o la configuración de un gate va además a "Para revisar" en la entrega, para que el orquestador o la persona lo vea sin leer todo.
- **Te detienes igual** si el mismo paso del DoD falla tres veces, si hace falta algo fuera del alcance (credenciales, push, publicar, borrar datos) o si dos reglas se contradicen y ninguna opción se puede deshacer.
- Sigue valiendo la regla de no commitear (sección 7), salvo que el pedido lo autorice por escrito.

## 2. Implementación

### Feature o enhancement

De adentro hacia afuera, con la estructura del perfil:

1. **Dominio:** modelos, interfaces de repositorio y use cases, con sus tests.
2. **Datos:** fuentes, modelos de datos, mappers e implementación del repositorio, con sus tests.
3. **DI:** el módulo de la feature.
4. **Entrada:** UI (ViewModel, estado, pantallas), controller o comando, con sus tests.
5. **Navegación o rutas.**

Una tarea a la vez. No toques código que no tenga que ver con ella.

### Bugfix

1. **Reproduce:** pasos, comportamiento esperado y comportamiento actual.
2. **Escribe un test que falle** por el bug, antes de corregir.
3. **Busca la causa raíz**, no el síntoma: pregunta "por qué" hasta llegar al origen.
4. **Corrección mínima.** El test nuevo pasa y los existentes también.
5. Revisa si el mismo defecto existe en código parecido y repórtalo.

### Refactor

1. Asegura tests que cubran el comportamiento actual. Si no existen, créalos primero (tests de caracterización).
2. Avanza en pasos pequeños que no cambian el comportamiento y corre los tests en cada paso.
3. No mezcles cambios de comportamiento con el refactor. Si encuentras un bug, anótalo y trátalo aparte.

## 3. Changelog

Si el proyecto lleva `CHANGELOG.md` con `[Unreleased]`, o `AGENTS.md` pide documentar, agrega la entrada con las reglas de `hb-commit` (secciones estándar de Keep a Changelog, idioma del archivo).

## 4. Definition of Done

- Corre los comandos de `## DoD`, en orden.
- Si un paso falla, corrige y repite desde ese paso. **Si el mismo paso falla tres veces, detente** y reporta el error con tu diagnóstico.
- Un paso que el entorno no permite (por ejemplo, compilar iOS sin macOS) se marca `skipped` con el motivo. Nunca cuenta como `pass`.
- **Nunca debilites un gate para que pase**: nada de desactivar reglas, bajar umbrales de cobertura, `ignoreFailures`, `abortOnError = false` ni `@Suppress` sin motivo. Arregla la causa.
- Si `AGENTS.md` no define DoD, usa las tareas estándar del stack (Gradle: lint, test y build; npm: `lint`, `test` y `build`; Python: `ruff` y `pytest`) y propone agregarlas a `AGENTS.md`.

## 5. Previews de UI (opcional)

Solo si se cumplen las tres condiciones: el cambio toca UI de Compose (un `XContent.kt` o los composables que usa), el proyecto es Android o KMP con un módulo de app Android, y existe la CLI `android`. No reemplaza a los tests de screenshots del proyecto: esos siguen siendo la regresión.

1. Lista los `@Preview` del módulo y quédate con los de los archivos que cambiaste. Pasa la carpeta del módulo de la app (por ejemplo `app`): sin ella la CLI toma el proyecto raíz y falla.
   ```bash
   android preview list app --format json
   ```
   **En KMP** la CLI no reconoce el módulo compartido (`shared`, con `com.android.kotlin.multiplatform.library`): pasa el de la app Android (`androidApp`) con `--all`, que incluye los previews de sus dependencias, entre ellos los de `commonMain`. En `render` usa también `androidApp`.
   ```bash
   android preview list androidApp --all --format json
   ```
2. Dibújalos en `reports/previews` (cada `--fqn` es un nombre que devolvió `list`):
   ```bash
   android preview render app --fqn <fqn> --fqn <otro-fqn> --format json -o reports/previews
   ```
   La primera vez la CLI descarga su paquete de render (unos 300 MB). Con `--daemon`, los renders siguientes son más rápidos.
3. **Mira cada imagen** y compárala con los criterios de aceptación: textos, orden, estados y tema. Si algo no coincide, corrige y vuelve a dibujar. Para datos exactos, agrega `--component-tree`: el JSON trae bounds, semántica y el archivo y la línea de cada componente.
4. Agrega cada imagen a `previews` en `meta.json`, con lo que muestra y qué criterio verifica.
5. Si falta la CLI, el proyecto no tiene un módulo de app Android o el render falla, agrega al DoD del reporte un paso `Previews de UI` en `skipped` con el motivo, y sigue: no bloquea la entrega.

## 6. Reporte HTML

Se genera siempre, salvo que el usuario diga que no.

1. Asegura que `reports/` esté en `.gitignore`. Si no está, agrégalo.
2. Escribe `reports/meta.json` con lo que git no sabe:

```json
{
  "project": "SnapDoc",
  "title": "Perfil de usuario",
  "type": "feature",
  "scope": "feature/profile",
  "description": "Una o dos oraciones sobre qué se hizo y por qué.",
  "date": "AAAA-MM-DD",
  "files": {
    "ruta/al/ArchivoNuevo.kt": { "why": "Qué aporta al diseño." },
    "ruta/al/ArchivoModificado.kt": { "before": "Qué limitación había.", "after": "Qué mejora el cambio." },
    "ruta/al/ArchivoEliminado.kt": { "why": "Por qué se elimina." }
  },
  "dod": [
    { "icon": "🧪", "name": "Tests", "command": "./gradlew test", "status": "pass", "note": "", "output": "" }
  ],
  "previews": [
    { "name": "ProfileContentPreview", "image": "reports/previews/…/ProfileContentPreview_0.png", "note": "Qué muestra y qué criterio verifica." }
  ]
}
```
   - `type`: `feature`, `bugfix`, `enhancement` o `refactor`. `status`: `pass`, `fail` o `skipped`. `date`: la fecha local.
   - Una explicación por archivo, sobre el impacto, no sobre el código. `output` solo en pasos que fallaron.
   - `previews` es opcional (sección 5). `image` es la ruta que devolvió `android preview render`, absoluta o relativa al repo: el script incrusta la imagen en el reporte.
3. Genera el reporte con el script de esta skill (la ruta es relativa a la carpeta de la skill):
   ```bash
   python3 -I <carpeta-de-la-skill>/scripts/report.py --meta reports/meta.json
   ```
   El script saca el antes, el después y el diff de git (contra `HEAD`, incluidos los archivos nuevos sin trackear): **no copies código en el meta**.
4. Si el script avisa de archivos sin explicación, complétalos y vuelve a generarlo.

## 7. Entrega

- **No hagas commit** salvo que el usuario lo pida y `AGENTS.md` lo permita.
- Entrega:
  - Un resumen de dos o tres líneas.
  - Los archivos creados, modificados y eliminados.
  - El resultado del DoD por paso.
  - La ruta del reporte (con los previews de UI, si los hubo).
  - Los commits propuestos, agrupados por unidad funcional y con mensajes según `hb-commit`.
  - El texto para el PR: qué cambia, por qué y cómo se verificó.

## Checklist

- [ ] `AGENTS.md`, perfil y referencias necesarias leídos.
- [ ] Criterios de aceptación claros; plan confirmado si hacía falta.
- [ ] Estructura y regla de dependencias del perfil respetadas.
- [ ] Tests nuevos con fakes; en un bugfix, el test que reproduce el bug.
- [ ] Patrones aplicados solo donde el problema los pedía.
- [ ] Changelog actualizado si el proyecto lo usa.
- [ ] DoD completo: cada paso en `pass` o `skipped` con motivo.
- [ ] Si el cambio toca UI de Compose en Android y existe la CLI `android`: previews dibujados, revisados e incluidos en el reporte.
- [ ] Reporte generado y ruta entregada.
- [ ] Sin commit automático.
