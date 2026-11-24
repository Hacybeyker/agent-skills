# Prompts listos para copiar

Para el usuario, no para el agente. Cada caso dice dónde va (un chat nuevo, con el modelo que conviene, o la terminal) y trae, en un bloque aparte, el texto para pegar: **copia solo el bloque**. Lo que va entre `<>` se completa.

- **Después del primer pedido, solo pegas lo que imprime `producto.py siguiente`:** cada sesión termina con el paso que sigue, con el texto de cada chat o el comando completo. También queda en "Siguiente paso" de `estado.md`.
- **Cada sesión va en un chat nuevo.** Cada paso del agente reenvía todo el chat, y uno que encadena sesiones cuesta varias veces más.
- **Modelo:** `siguiente` dice el de cada chat, con su esfuerzo: Sonnet 5.5 (medio) para la sesión 0 y las cinco líneas de investigación; Opus 5.5 (alto) para la diferenciación, la síntesis, la estrategia, la validación y el PRD. Con otra herramienta, cámbialos una vez con `producto.py modelos`; con `--herramienta claude` o `copilot`, cada chat trae el comando que lo abre ([modelos.md](modelos.md)).
- **La carpeta** es `product/` dentro de la carpeta donde abres el chat. Para usar otra, agrégala al pedido ("en la carpeta `docs/producto`") o anótala en `AGENTS.md`: una sección `## Producto` con la línea `Carpeta: docs/producto`.
- **Cada texto termina con "No hagas commit ni push."** La skill ya lo dice; la línea explícita evita sorpresas.

## Empezar

### Una idea nueva (sesión 0)

**Dónde:** chat nuevo · Sonnet 5.5, esfuerzo medio

```text
Usa hb-product: tengo una idea de app. <La idea en tus palabras: qué problema resuelve, para quién, en qué plataformas, países, idiomas y tiendas, cómo piensas ganar dinero y cuántas semanas tienes para construirla; si quieres, una meta de ingresos al mes>. No hagas commit ni push.
```

No hace falta responder todo: el agente pregunta lo que falte en una sola tanda, crea la carpeta y termina con los cinco chats de la investigación. La meta de ingresos es opcional y solo una referencia; si quieres que sea un criterio de la puerta 2, dilo ("la meta es obligatoria").

### Una idea en un mercado con muchas apps

**Dónde:** chat nuevo · Sonnet 5.5, esfuerzo medio

```text
Usa hb-product: quiero hacer <tipo de app> aunque ya hay muchas. Quiero saber cómo diferenciarme antes de construirla: <para quién, plataformas, países, idiomas, tiendas y semanas disponibles>. No hagas commit ni push.
```

La cantidad de competidores no descarta la idea: la investigación busca un diferenciador con evidencia.

### Una idea que no existe todavía

**Dónde:** chat nuevo · Sonnet 5.5, esfuerzo medio

```text
Usa hb-product: tengo una idea de app que no encontré en ninguna tienda: <la idea, el problema que resuelve y cómo lo resuelve hoy la gente>. <Plataformas, países, idiomas, tiendas y semanas disponibles>. No hagas commit ni push.
```

La falta de datos tampoco la descarta: la investigación trabaja por analogía.

## Seguir

### Abrir un carril de la investigación

**Dónde:** un chat nuevo por carril, a la vez · el modelo y el esfuerzo que diga `siguiente`

Copia el texto que imprime `producto.py siguiente` para cada sesión. Tiene esta forma:

```text
Sigue hb-product con <ruta absoluta>/product/estado.md: sesión 1c · Demanda. No hagas commit ni push.
```

Las sesiones 1a a 1e se abren juntas. La 1g aparece apenas cierran 1a y 1b; la 1f, cuando cierran las seis.

### Los carriles con subagentes, en un solo chat

**Dónde:** chat nuevo · Sonnet 5.5, esfuerzo medio (cada subagente, con el modelo de su sesión)

```text
Sigue hb-product con <ruta absoluta>/product/estado.md como orquestador: lanza un subagente por cada sesión que ofrezca producto.py siguiente, con su texto para pegar y el modelo que indica; cuando cada uno termine, anota su uso con producto.py consumo si la herramienta lo muestra, vuelve a correr siguiente y lanza las que se abran, hasta llegar a la puerta. No investigues tú ni corras decidir. No hagas commit ni push.
```

Sirve si tu herramienta tiene subagentes. El chat orquestador no investiga: espera y lanza lo que se abre. Al cerrarlo, anota el total del chat (abajo, "Anotar el costo").

### Retomar donde quedó

**Dónde:** chat nuevo · el modelo y el esfuerzo que diga "Siguiente paso" de `estado.md`

```text
Sigue hb-product con <ruta absoluta>/product/estado.md. No hagas commit ni push.
```

### Ver por dónde va

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py estado --carpeta product
```

## Decidir en una puerta

**Dónde:** terminal, sin chat. `producto.py siguiente` (y la última respuesta de la sesión anterior) ya trae el veredicto criterio por criterio y los comandos completos; el agente nunca los corre. Uno de estos:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --seguir --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --ajustar <sesión> --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --descartar "<motivo>" --carpeta product
```

Si una sesión dejó una propuesta (por ejemplo, cambiar el diferenciador principal), la puerta la muestra con su `--ajustar` ya listo. Para volver a mirar el veredicto sin decidir:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py puerta --n 1 --carpeta product
```

Si una decisión quedó registrada y no fue tuya:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --reabrir --carpeta product
```

## Pedidos puntuales

### Cambiar un criterio después de la sesión 0

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py criterio --clave puntaje_minimo --valor 16 --motivo "<por qué>" --carpeta product
```

Queda registrado y cada puerta lo muestra.

### Aportar reseñas en CSV

**Dónde:** el chat de la sesión 1b (o el de un ajuste de 1b). Sirve cuando el agente no puede leer las reseñas de una tienda.

```text
Te paso reseñas exportadas de <app> en <tienda>: <ruta absoluta del CSV>. Regístralas como fuente y léelas con producto.py resenas. No hagas commit ni push.
```

El CSV necesita una columna de texto o de estrellas; la de fecha y la de idioma ayudan. Las columnas de autor nunca se leen.

### Elegir el modelo o la herramienta

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py modelos --herramienta claude --carpeta product
```

Con `--intermedio "<modelo>"` y `--alto "<modelo>"` cambias los nombres ([modelos.md](modelos.md)).

### Anotar el costo

**Dónde:** terminal, sin chat. Opcional, al cerrar cada chat:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py consumo --sesion <id> --costo '<USD>' --carpeta product
```

Con un orquestador: `--sesion orquestador --incluye 1a,1b,1c,1d,1e,1g` y el total del chat. Con GitHub Copilot CLI, `--creditos <AI Credits>` en vez de `--costo`.

### Guardar una idea para después, o recuperarla

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py archivar --motivo "<motivo>" --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py reabrir --idea <nombre> --carpeta product
```

### Construir una funcionalidad del PRD

**Dónde:** chat nuevo, en el repo de la app. Lo hace `hb-implement`, no hb-product.

```text
Implementa F-01 de <ruta absoluta>/product/04-prd.md: su historia y sus criterios de aceptación.
```

### Entender un concepto

**Dónde:** chat nuevo. Lo hace `hb-coach`.

```text
Explícame <RICE, Kano, HEART, Jobs To Be Done o Lean Canvas>: lo estoy usando en el PRD de mi app. Solo la duda, sin plan.
```
