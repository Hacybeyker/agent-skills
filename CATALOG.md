# Catálogo

Lo que complementa a las skills de este repo: skills externas, plugins de Claude Code y un ajuste recomendado. Todo es opcional: instala solo lo que uses.

## Skills propias (este repo)

Se instalan con `install.sh` o con la CLI `skills`, como explica el [README](README.md).

| Skill | Tipo | Versión |
| --- | --- | --- |
| `hb-setup` | Flujo | 1.0.0 |
| `hb-implement` | Flujo | 1.1.0 |
| `hb-review` | Flujo | 1.0.0 |
| `hb-commit` | Flujo | 1.0.0 |
| `hb-release` | Flujo | 1.0.0 |
| `hb-stack-mobile-kotlin` | Perfil | 1.2.0 |
| `hb-coach` | Personal | 2.0.1 |

## Skills externas

No llevan `hb-` y no se copian a este repo: cada una se actualiza con su propio instalador.

| Skill | Proveedor | Cómo se mantiene |
| --- | --- | --- |
| `testigo-flows` | Hacybeyker ([testigo](https://github.com/Hacybeyker/testigo)) | `testigo setup`, si usas testigo para pruebas E2E con Maestro |
| `android-cli` | Google | Igual que las oficiales (sección siguiente): `android skills add --agent=<agentes> android-cli`. Android Studio trae la suya. No uses `android init`: copia la skill a cada agente que detecta, incluidos los que no usas, y nadie actualiza esas copias. La de `~/.agents/skills` además duplica la que cada agente ya tiene en su carpeta |
| Skills oficiales de Android | Google ([android/skills](https://github.com/android/skills)) | Selección de la tabla siguiente |

### Skills oficiales de Android (selección)

Se instalan globales, solo para los agentes que uses:

```bash
android skills add --agent=<agentes> <skill>      # instalar
android skills update --agent=<agentes> <skill>   # actualizar
```

- **`<agentes>`:** los que uses; por ejemplo, `claude-code,github-copilot` para Claude Code y Copilot. Si empiezas a usar otro agente, agrégalo y vuelve a instalar la selección.
- **Nunca `android-studio`:** ya trae todas las oficiales en `~/.android-studio/skills`.
- **`common` (`~/.agents/skills`) solo si tu agente no tiene nombre propio en la CLI:** Android Studio también lee esa carpeta y vería las oficiales dos veces.
- La skill va como argumento posicional y `--agent` recibe una lista separada por comas. **Sin `--agent`, instala en todos los agentes que detecte.**
- `android skills list` muestra todas las disponibles y para qué agentes está instalada cada una, con el nombre que va en `--agent`.
- Precedencia: las reglas del proyecto (`AGENTS.md`) y el perfil `hb-stack-*` mandan en arquitectura, convenciones, testing y dependencias; las skills oficiales mandan en hechos técnicos actuales (APIs, migraciones, herramientas).

| Skill | Para qué |
| --- | --- |
| `navigation-3` | Navigation 3: migración, deep links, back stacks múltiples, scenes, Hilt y ViewModel |
| `edge-to-edge` | Edge-to-edge adaptativo, insets del IME y legibilidad de las barras del sistema |
| `adaptive` | UI adaptativa a teléfonos, tablets, plegables, escritorio, TV y XR |
| `jetpack-compose-performance` | Diagnosticar y reducir recomposiciones y frames perdidos |
| `android-profiler` | Grabar y analizar trazas (Perfetto): jank, ANR, arranque, memoria, batería |
| `anr-audit-and-fix` | Auditar riesgos de ANR y diagnosticar sus stack dumps |
| `r8-analyzer` | Detectar keep rules redundantes o demasiado amplias |
| `android-intent-security` | Seguridad de Intents y componentes del manifest |
| `android-permissions-security` | Permisos, componentes IPC y flujos de permisos en runtime |
| `play-policy-insights` | Auditar la app contra las políticas de Google Play |

**Se omite `testing-setup`:** choca con el perfil (fakes, Roborazzi, Kover).

## Plugins de Claude Code recomendados

Complementan a las skills `hb-*`. Se instalan con `claude plugin install <plugin>@claude-plugins-official`.

| Plugin | Proveedor | Para qué |
| --- | --- | --- |
| `kotlin-lsp` | Anthropic (servidor de JetBrains) | Diagnósticos y navegación de código Kotlin. Está en alpha: Android experimental, KMP aún sin soporte |
| `context7` | Upstash | Documentación actualizada de librerías por versión (MCP) |
| `pr-review-toolkit` | Anthropic | Agentes de review especializados; segunda pasada después de `hb-review` |
| `security-guidance` | Anthropic | Avisos de seguridad al editar y revisión del diff al terminar cada turno (consume tokens) |
| `claude-md-management` | Anthropic | Auditar y mejorar `CLAUDE.md` / `AGENTS.md` |
| `feature-dev` | Anthropic | Flujo genérico de features para proyectos sin `AGENTS.md` |

- **Según tu stack:** `typescript-lsp` y `pyright-lsp` (web y backend), `jdtls-lsp` (Java), `swift-lsp` (Swift).
- **Mejor no instalar:** `commit-commands` (choca con `hb-commit`) y `code-review` (lo cubren `hb-review` y `pr-review-toolkit`).

## Ajuste recomendado para Claude Code

Para que Claude Code lea las skills sin pedir permiso en cada proyecto, agrega a `permissions.additionalDirectories` de `~/.claude/settings.json` las carpetas `~/.claude/skills` y `~/.agents/skills`. Si instalaste con `install.sh`, agrega también la carpeta `skills/` de tu clon: los enlaces apuntan ahí.
