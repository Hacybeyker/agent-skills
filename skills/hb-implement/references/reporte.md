# Reporte: carpeta y campos opcionales

## Carpeta de reportes

`report.py` escribe en:

1. `--out`, si lo pasas.
2. La ruta de la línea `Carpeta de reportes: <ruta>` de `AGENTS.md`, con o sin acentos graves (en inglés, `Reports folder:`). Relativa a la raíz del repo, o absoluta.
3. `reports/`, si no hay ninguna.

| Ruta | Meta | Reporte | Bitácora |
| --- | --- | --- | --- |
| `reports` | `reports/<fecha>-<slug>.meta.json` | `reports/<fecha>-<slug>.html` | `reports/<fecha>-<slug>.bitacora.md` |
| `contexto/reports/{fecha}/{slug}` | `<carpeta>/meta.json` | `<carpeta>/report.html` | `<carpeta>/bitacora.md` |

- `{fecha}` es la `date` del meta (`AAAA-MM-DD`) y `{slug}`, su `slug` o, sin él, el título en minúsculas con guiones. Con marcadores, `{slug}` es obligatorio y antes tiene que haber una carpeta fija: es la que se deja fuera de git.
- Si ya existe una carpeta con ese slug en **otra fecha**, la tarea sigue ahí: el meta, la bitácora y el reporte quedan juntos. Si el meta ya vive en una carpeta de tarea, el reporte se genera en esa misma carpeta.
- `--folder <slug>` (con `--date`, opcional) imprime y crea la carpeta de la tarea, sin generar el reporte.
- **Enlaces simbólicos.** Si la ruta pasa por un enlace (por ejemplo `contexto/`, que apunta a una carpeta fuera del repo), git no mira más allá de él: el script comprueba que el enlace esté ignorado y, si no lo está, avisa sin escribir en `.git/info/exclude`. Una carpeta fuera del repo no necesita ignorarse.

## Análisis del cambio

Todo es opcional y solo se muestra si viene en el meta. Úsalo cuando ayude a revisar, no por rellenar.

| Campo | Dónde | Qué es |
| --- | --- | --- |
| `risk` | Por archivo | Riesgo del cambio para el review: `critico`, `alto`, `medio` o `bajo`. Sale junto a la ruta. |
| `pros` | Por archivo | Lista de lo que gana el cambio. |
| `cons` | Por archivo | Lista de lo que cuesta. Vacía, el reporte dice "Sin contras identificados". |
| `severity` | Reporte | En un `bugfix`, la gravedad del bug, con la misma escala. |
| `impact` | Reporte | Lista de `{"label", "value"}`: a quién o a qué afecta, con datos (usuarios, pantallas, tiempos). |
| `root_cause` | Reporte | Texto: la causa raíz, no el síntoma. |
| `diagrams` | Reporte | Lista de `{"title", "mermaid", "description"}`: el código Mermaid de cada diagrama. |

**Escala** (para `risk` y `severity`): `critico`, puede romper datos, seguridad o un flujo principal; `alto`, cambia un contrato o lógica compartida; `medio`, lógica local cubierta por tests; `bajo`, cosmético, tests o documentación. Se acepta `crítico`.

```json
{
  "severity": "alto",
  "root_cause": "El total se calculaba antes de aplicar el descuento.",
  "impact": [{ "label": "Pagos afectados", "value": "Los que usan cupón" }],
  "diagrams": [
    {
      "title": "Cálculo del total",
      "mermaid": "flowchart LR\n  A[Carrito] --> B[Descuento] --> C[Total]",
      "description": "El descuento se aplica antes del total."
    }
  ],
  "files": {
    "pagos/total.py": {
      "before": "Sumaba sin descuento.",
      "after": "Aplica el descuento primero.",
      "risk": "medio",
      "pros": ["Un solo lugar calcula el total"],
      "cons": []
    }
  }
}
```

- Un valor fuera de la escala o de otro tipo (una lista que no es lista, un diagrama sin `mermaid`) termina con un error claro y sin escribir el reporte.
- **Mermaid** se carga solo si hay `diagrams`: desde jsDelivr, con la versión exacta, integridad y `securityLevel: 'strict'`. El código va escapado en `<pre class="mermaid">`: sin conexión se lee como texto. Sin `diagrams`, el reporte no carga nada remoto.
