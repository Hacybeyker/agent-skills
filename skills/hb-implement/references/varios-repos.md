# Varios repos y dependencias con código local

Cuando el proyecto depende de otros repos que se trabajan en local, `AGENTS.md` los documenta en `## Arquitectura` → **Repos relacionados** (lo escribe `hb-setup`): la ruta relativa de cada uno, qué contiene, cómo se incluye en local y, para las dependencias publicadas, cómo pasar a su código y cómo volver.

## Antes de tocar un repo relacionado

1. Comprueba que puedes leerlo: `git -C <ruta> status --short` (o lista la carpeta).
2. Si no puedes (la carpeta no existe o el agente no tiene acceso), **detente en ese punto** y dile al usuario qué carpeta debe darte acceso: la ruta de `AGENTS.md` y la absoluta que resulta. Cada agente tiene su forma de sumar directorios de trabajo. No supongas su contenido ni lo deduzcas de nombres o de un artifact compilado.
3. Revisa su `git status` como el del principal: si ya tiene cambios que no son de la tarea, avísalo antes de empezar.

## Dependencias publicadas que tienen código local

Si la tarea necesita leer o cambiar el código de una dependencia que el proyecto solo consume publicada (un artifact compilado, un paquete, un catálogo o BOM remoto):

- Usa el mecanismo que documenta `AGENTS.md` para trabajar con su código local; no deduzcas el comportamiento del artifact compilado.
- Si `AGENTS.md` no dice cómo, dilo y pregunta. Con el alcance aprobado, detente en ese punto y anótalo: no inventes el mecanismo.
- **El cambio de configuración que pasa a local es temporal.** No es parte de la tarea: va en `temporary` del meta (abajo), no se propone para commit y la entrega dice cómo revertirlo. Si `AGENTS.md` pide revertirlo al terminar, hazlo después del DoD deshaciendo solo ese cambio (no `git checkout` ni `git restore` sobre un archivo que tenga otros cambios).
- Los cambios en el **código** de la dependencia sí son de la tarea: su repo va en `repos` del meta y sus commits se proponen aparte.

## Base de comparación

Por repo, la que pida `AGENTS.md` (por ejemplo, el `merge-base` con la rama destino del PR: `git merge-base origin/main HEAD`); si no dice nada, `HEAD`. La del principal va en `--base`; la de cada relacionado, en su `base`.

## Un solo reporte

```json
{
  "repos": [
    { "path": "../modulo-a", "base": "origin/main", "name": "modulo-a" }
  ],
  "files": {
    "src/pantalla_pago.ts": { "before": "Qué limitación había.", "after": "Qué mejora el cambio." },
    "modulo-a:pagos/validador.py": { "why": "Qué aporta al diseño." }
  },
  "temporary": [
    { "path": "dependencias.local", "why": "Usa el código local de modulo-a.", "revert": "rm dependencias.local" }
  ]
}
```

- `path`: relativa a la raíz del repo principal (o absoluta). `name`: el prefijo de sus claves; por defecto, el nombre de la carpeta. `base`: por defecto `HEAD`.
- Las claves del principal no llevan prefijo, como siempre; las de un relacionado, `<name>:<ruta>`. `groups` y `temporary` usan las mismas claves.
- Una entrada con `"path": "."` solo le pone nombre o base al principal (`--base` manda sobre ella).
- El reporte muestra una tabla con el nombre, la rama, la base y los conteos de cada repo, y suma los archivos sin rastrear de todos.
- Si un repo de `repos` no se puede leer, el script termina sin escribir nada y dice qué carpeta falta.

## Entrega

- Commits propuestos **por repo**, en el orden en que se integran (primero la dependencia).
- Cada cambio temporal con su forma de revertirlo, o "revertido".
