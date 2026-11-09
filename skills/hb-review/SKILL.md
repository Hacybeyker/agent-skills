---
name: hb-review
description: 'Revisa código contra las reglas del proyecto (AGENTS.md), su perfil hb-stack-* y las prácticas de code review de la industria (guía de Google, Conventional Comments). Revisa el diff actual, una rama, un PR o archivos concretos; corre el DoD y entrega hallazgos priorizados con veredicto. Tiene un modo rápido para orquestadores: revisa el diff de un bloque contra el alcance, sin volver a correr el DoD. No modifica código. Úsala cuando el usuario pida revisar código, hacer code review, revisar un PR o validar cambios antes de un commit ("revisa el código", "haz code review", "revisa el PR #12", "¿cumple con las reglas?", "revisión rápida del bloque", "/hb-review").'
license: MIT
metadata:
  author: hacybeyker
  version: "1.1.0"
  category: flow
  origin: "basada en code-reviewer"
---

# hb-review

Revisión de solo lectura. Cada hallazgo cita la regla o el estándar que incumple, no una preferencia personal.

**Estándares:** la guía de code review de Google (aprueba cuando el cambio mejora la salud del código aunque no sea perfecto) y [Conventional Comments](https://conventionalcomments.org/) para el formato de los comentarios.

## 1. Alcance y contexto

1. Define qué revisar:
   - Sin indicación: `git diff HEAD` (working tree y staged). Si está limpio, la rama actual contra la principal (`git diff <principal>...HEAD`).
   - Un PR: `gh pr diff <n>` y `gh pr view <n>` (descripción, checks).
   - Archivos o una feature: esos archivos completos.
2. Lee `AGENTS.md` y el perfil `hb-stack-*` del proyecto, y solo las referencias que el cambio toca (UI, testing, seguridad…). Sin `AGENTS.md`, revisa contra el perfil del stack detectado y los estándares generales, y dilo en el reporte.
3. Entiende el propósito: lee la descripción del PR o los commits antes de opinar sobre el código.

## 2. Qué revisar

| Área | Preguntas |
| --- | --- |
| **Diseño** | ¿Respeta la arquitectura y la regla de dependencias del proyecto (`AGENTS.md`; el perfil donde el proyecto lo sigue)? ¿Cada cosa está en su capa y en su feature? ¿Los patrones usados se justifican, o sobra abstracción (KISS, YAGNI)? Usar el stack del proyecto (Views, MVP, Rx) no es un hallazgo; migrar fuera de `## Modernización` sí |
| **Funcionalidad** | ¿Hace lo que promete? ¿Casos borde, errores, concurrencia, cancelación? ¿Qué ve el usuario? |
| **Complejidad** | ¿Se entiende rápido? ¿Funciones o clases demasiado grandes? ¿Duplicación real (DRY)? |
| **Tests** | ¿La lógica nueva tiene tests con fakes? ¿Un bugfix trae el test que reproduce el bug? ¿Los tests fallarían si el código se rompiera? |
| **Nombres y comentarios** | ¿Nombres claros y consistentes con el proyecto? ¿Los comentarios explican el porqué, no el qué? |
| **Estilo y consistencia** | ¿Sigue las reglas del proyecto y del linter? (lo automático lo marca el DoD, no lo repitas a mano) |
| **Seguridad** | ¿Secretos, datos sensibles en logs, validación de entradas, almacenamiento, red? Usa el checklist de seguridad del perfil |
| **Dependencias** | ¿Versiones estables y en el catálogo del proyecto? ¿Hacía falta la dependencia? |
| **Documentación y versionado** | ¿Changelog en `[Unreleased]` si el proyecto lo usa? ¿Commits en formato Conventional Commits? ¿El PR es pequeño y de un solo propósito? |

Reconoce también lo que está bien hecho: un buen review no es solo una lista de problemas.

## 3. Verificación automática

Corre el DoD de `AGENTS.md` y reporta cada paso (`pass`, `fail` o `skipped`). No corrijas nada. Si el usuario pidió una revisión rápida o solo de lectura, marca el DoD como `skipped`. El modo rápido para orquestadores (ver abajo) también lo salta siempre.

## 4. Reporte

Cada hallazgo con formato Conventional Comments y su ubicación:

```
archivo.kt:42 — issue (blocking): el ViewModel accede al repositorio directamente.
Regla: perfil, arquitectura → "El ViewModel solo habla con use cases".
Sugerencia: crear ObserveProfileUseCase e inyectarlo.
```

| Etiqueta | Uso | ¿Bloquea? |
| --- | --- | --- |
| `issue (blocking)` | Rompe una regla del proyecto, la arquitectura, la seguridad o la funcionalidad | Sí |
| `issue` | Incumple un estándar (tests faltantes, nombres, tokens, textos fijos) | Corregir antes de mergear |
| `suggestion` | Mejora concreta y opcional | No |
| `nitpick` | Detalle menor de estilo | No |
| `question` | Algo que no queda claro y necesita respuesta | Depende de la respuesta |
| `praise` | Algo bien resuelto | — |

Ordena por severidad. Agrupa los hallazgos repetidos en uno solo con todas sus ubicaciones.

**Veredicto:**
- ✅ **Aprobado:** sin `issue` y con el DoD en verde.
- 🔄 **Cambios requeridos:** lista priorizada de lo que hay que corregir.

## 5. Después del review

- Esta skill **no modifica código**. Si el usuario pide aplicar las correcciones, usa `hb-implement`.
- Para un PR, publica el review en GitHub (`gh pr review`) solo si el usuario lo pide.
- Si el proyecto tiene instalados plugins de review (por ejemplo `pr-review-toolkit`), puedes sugerirlos como segunda pasada para tests, errores silenciosos o diseño de tipos.

## Modo rápido (para orquestadores)

Para quien delegó un bloque a un subagente y debe revisarlo antes de commitear, sin repetir el DoD que ya corrió. Se activa cuando el pedido lo dice ("revisión rápida del bloque", "modo rápido") o cuando un plan lo invoca por cada bloque.

- **Qué revisas:** el diff del bloque (`git diff HEAD`, o `git diff <base>...<rama>` si ya está commiteado; el orquestador lo indica) **contra el documento de alcance** y el `AGENTS.md`. Lee completos los archivos con lógica (reglas de negocio, estado, persistencia, manejo de errores): la lista de archivos y el DoD en verde no bastan. Carga solo las referencias del perfil que toca el bloque.
- **No corres el DoD:** lo corre el orquestador. Márcalo `skipped` con el motivo "lo corre el orquestador".
- **Qué buscas** (lo que el DoD no ve): estado y persistencia frente a los requisitos; `catch` demasiado amplios; dependencias sin uso; casos que el alcance pide y no están; decisiones del agente que cambian una regla del alcance; reglas del `AGENTS.md` (comentarios, palabras prohibidas, idioma); tests que no fallarían si el código se rompiera.
- **Qué no haces:** no repites lo que el linter ya cubre, no propones migraciones, no tocas código.
- **Devuelves poco y priorizado:** el veredicto en una línea (✅ listo para commitear, o 🔄 corregir antes), los hallazgos `issue (blocking)` e `issue` con ubicación y la regla o el requisito que incumplen, y las `question` que el orquestador debe resolver. Sin `nitpick` ni `praise`. Si no hay hallazgos, dilo en una línea.
- El orquestador decide qué hacer con el resultado: reanudar al subagente con los hallazgos o corregirlos él. Esta skill no corrige.
