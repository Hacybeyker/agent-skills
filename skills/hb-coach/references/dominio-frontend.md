# Dominio: front-end web

Mapa para diseñar planes y enseñar desarrollo web del lado del cliente. Revisa `package.json`, el lockfile (usa el gestor de paquetes del proyecto: pnpm, npm, yarn o bun) y la configuración del framework antes de enseñar APIs concretas.

## Mapa de competencias

### 🟢 Básico
- **HTML semántico**: estructura, formularios, landmarks, etiquetas y textos alternativos.
- **CSS**: cascada, especificidad, modelo de caja, flexbox, grid, unidades relativas, variables, diseño responsive.
- **JavaScript moderno**: módulos, `let`/`const`, funciones flecha, desestructuración, clases, promesas, `async/await`, `fetch`, manejo de errores.
- **Navegador**: DOM, eventos, DevTools, almacenamiento (`localStorage`, cookies) y sus límites.
- **Accesibilidad básica**: contraste, foco visible, navegación con teclado, labels.

### 🟡 Intermedio
- **TypeScript**: tipos, uniones, narrowing, genéricos, utility types, configuración estricta.
- **Un framework** (React, Vue, Angular o Svelte): componentes, props, estado, efectos, listas y keys, formularios, composición.
- **Routing** y layouts.
- **Estado**: local, compartido y de servidor (TanStack Query o equivalentes); cuándo usar cada uno.
- **Datos**: llamadas a APIs, estados de carga y error, cancelación, caché.
- **Estilos**: CSS Modules, Tailwind CSS, sistemas de diseño.
- **Herramientas**: Vite, ESLint (flat config), Prettier, variables de entorno.
- **Testing**: Vitest o Jest, Testing Library, mocks de red.
- **Accesibilidad**: ARIA solo cuando el HTML no basta, gestión del foco, anuncios dinámicos.

### 🟠 Avanzado
- **Estrategias de renderizado**: CSR, SSR, SSG, ISR, streaming, React Server Components e hidratación.
- **Meta-frameworks**: Next.js (App Router), Nuxt, Remix/React Router, SvelteKit, Angular SSR.
- **Rendimiento**: Core Web Vitals (LCP, INP, CLS), code splitting, carga diferida, imágenes y fuentes, caché HTTP, presupuestos de rendimiento.
- **React en profundidad**: reconciliación, renderizado concurrente, Suspense, transiciones, React Compiler.
- **Seguridad web**: XSS, CSP, CSRF, CORS, cookies `HttpOnly`/`Secure`/`SameSite`, sanitización, dependencias.
- **Plataforma**: Service Workers y PWA, Web Workers, internacionalización.
- **Testing E2E** con Playwright; tests visuales.
- **Monorepos** (pnpm workspaces, Turborepo) y librerías de componentes.

### 🔴 Experto
- Arquitectura front-end a escala, micro-frontends y sus costes.
- Rendimiento avanzado: hilo principal, perfiles, WebAssembly.
- Observabilidad en producción (RUM) y gestión de errores.
- Renderizado en el edge y SSR a gran escala.
- Auditorías de accesibilidad (WCAG 2.2 AA) y diseño de design systems.
- Estrategias de migración entre frameworks o versiones mayores.

## Rutas típicas

- **React moderno**: JSX y componentes → props y composición → estado → eventos y formularios → efectos (y cuándo no usarlos) → listas → contexto → datos remotos → rendimiento y React Compiler → Suspense y transiciones → testing → proyecto.
- **TypeScript**: tipos básicos → funciones y objetos → uniones y narrowing → genéricos → utility types → tipos en React → configuración estricta → tipado de APIs → proyecto.
- **Next.js (App Router)**: rutas y layouts → Server y Client Components → obtención de datos y caché → Server Actions → estados de carga y error → autenticación → despliegue → rendimiento.
- **Rendimiento web**: cómo carga una página → Core Web Vitals → medición (laboratorio y campo) → recursos críticos → JavaScript y code splitting → imágenes y fuentes → INP y el hilo principal → caché → presupuestos.
- **Accesibilidad**: por qué importa → HTML semántico → teclado y foco → ARIA → formularios → contenido dinámico → pruebas con lector de pantalla → auditoría WCAG.
- **CSS moderno**: cascada y capas → flexbox y grid → container queries → `:has()` → anidamiento → variables y temas → animaciones accesibles.
- **Testing front-end**: qué probar → Testing Library → mocks de red → estados asíncronos → accesibilidad en tests → E2E con Playwright → CI.

## Ideas erróneas frecuentes

- «`useEffect` sirve para derivar estado» → calcula durante el render; los efectos sincronizan con sistemas externos.
- «`useMemo` y `useCallback` en todas partes» → mide antes; React Compiler memoiza automáticamente.
- «SSR siempre es más rápido» → mejora el primer pintado, pero añade coste de servidor e hidratación.
- «CORS protege mi API» → lo aplica el navegador; no sustituye a la autenticación ni a la autorización.
- «Guardar tokens en `localStorage` es seguro» → cualquier XSS los expone; valora cookies `HttpOnly` con `SameSite`.
- «Más ARIA, más accesible» → primero HTML semántico; un ARIA incorrecto empeora la experiencia.
- «Create React App es el punto de partida» → está deprecado; usa un framework o Vite.
- «Los tests de snapshot bastan» → comprueba comportamiento visible para el usuario.

## Decisiones que el estudiante debe saber argumentar

- SPA, SSR o SSG para un caso concreto.
- Estado local, global o de servidor.
- Tailwind, CSS Modules o CSS-in-JS.
- Framework o librería, y cuándo un meta-framework.
- Dónde guardar la sesión en el navegador.
- Monorepo o repositorios separados.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- React 19 y React Compiler 1.0 (octubre de 2025) son estables.
- Create React App está deprecado desde febrero de 2025.
- INP sustituyó a FID como Core Web Vital en marzo de 2024.
- Baseline (web.dev) es la referencia para saber qué funciones web son seguras de usar.
- ESLint usa la configuración plana (`eslint.config.js`) por defecto.
- Node.js: usa la versión LTS activa que indique nodejs.org.

## Ideas de práctica

- Dashboard con datos remotos, filtros en la URL y estados de carga y error.
- Formulario accesible con validación en cliente y servidor.
- Migrar una SPA a Next.js App Router y medir Core Web Vitals antes y después.
- Librería de componentes con Storybook (o similar) y tests de accesibilidad.
- Suite E2E con Playwright en CI.
