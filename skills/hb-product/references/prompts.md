# Prompts listos para copiar

Para el usuario, no para el agente. Cada caso dice dónde va (un chat nuevo, con el modelo que conviene, o la terminal) y trae, en un bloque aparte, el texto para pegar: **copia solo el bloque**. Lo que va entre `<>` se completa.

- **Después del primer pedido, solo pegas lo que imprime `producto.py siguiente`:** cada sesión termina con el paso que sigue, con el texto de cada chat o el comando completo. También queda en "Siguiente paso" de `estado.md`.
- **Cada sesión va en un chat nuevo.** Cada paso del agente reenvía todo el chat, y uno que encadena sesiones cuesta varias veces más. La excepción es el modo orquestado (abajo): un solo chat, pero cada sesión corre en un subagente con su propio contexto.
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

Las sesiones 1a a 1e se abren juntas, cada una con el tipo de idea que dejó la sesión 0 (la 1a lo confirma). La 1g aparece apenas cierran 1a y 1b; la 1f, cuando cierran las seis. Si una sesión se reabrió en una puerta, el texto trae el presupuesto de esa reapertura (la mitad del original).

### Toda la idea desde un solo chat (modo orquestado)

Un chat recorre la idea entera: lanza cada sesión como un subagente con el modelo de su sesión, **en primer plano y en un mismo mensaje los que corren juntos** (1a y 1b; después 1c, 1d, 1e y la 1g, que arranca sin esperar a las demás; la 2 y la 3 juntas), espera a que terminen todos sin cerrar su turno, anota el consumo de cada uno con lo que trae su resultado y se detiene en cada puerta, donde decides tú en tu terminal ([orquestacion.md](orquestacion.md)). La regla del primer plano va en el texto que pegas: sin ella, el chat puede dejar un subagente en segundo plano, cerrar su turno y quedarse quieto. No abres chats ni pegas pasos. Necesita una herramienta con subagentes (Claude Code los tiene); sin ellos, la skill lo dice y sigue con un chat por sesión.

**Dónde:** chat nuevo · Haiku 5.5, esfuerzo bajo (es el orquestador: cada sesión usa el modelo de su nivel)

**Ábrelo** (terminal, desde la carpeta donde vive `product/`): `cd <raíz> && claude --model claude-haiku-5-5 --effort low`. Después pega el bloque.

Una idea nueva:

```text
Usa hb-product en modo orquestado: tengo una idea de app. <La idea en tus palabras: qué problema resuelve, para quién, plataformas, países, idiomas, tiendas, cómo piensas ganar dinero y cuántas semanas tienes>. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.
```

Una idea que ya empezó (retomar en modo orquestado):

```text
Sigue hb-product con <ruta absoluta>/product/estado.md en modo orquestado. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.
```

La sesión 0 te hace sus preguntas en el mismo chat, en una sola tanda. En cada puerta, el orquestador te muestra el veredicto y los comandos de `decidir`, el recomendado primero, y se detiene: el orquestador nunca decide por ti. Corre el que elijas en tu terminal y después escribe en el mismo chat:

```text
Continúa. No hagas commit ni push.
```

**Arriba de cada parada** (cada puerta y el mensaje final) te recuerda correr `/cost` en ese chat y te da el comando armado `producto.py consumo --sesion orquestador --incluye <las sesiones que lanzó ese chat> --costo '<USD>' --chat <id>` (`--chat`: la fila de ese chat, que se actualiza en cada parada): el total del chat, que incluye a los subagentes (el consumo de cada subagente ya quedó anotado por sesión). Córrelo antes de decidir: si cierras el chat sin `/cost`, ese costo se pierde.

Si el chat se quedó quieto con un subagente que ya terminó (o tras su aviso de fin), escribe en el mismo chat:

```text
Continúa en modo orquestado: anota el consumo de los subagentes que terminaron y sigue el ciclo. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.
```

### Toda la idea sin preguntas ni paradas (modo autónomo)

Para no copiar ni aprobar entre chats: es el modo orquestado, pero la sesión 0 no te pregunta (lo que falte en tu descripción queda como "Supuestos sin confirmar") y en cada puerta el orquestador aplica la recomendación de la skill con `decidir --automatico`, que nunca va en contra de ella y queda marcada como **decisión automática** en el reporte, el tablero y `estado.md` para que la revises o la reabras. Solo se detiene si una puerta pide ajustar la misma sesión por tercera vez, si falta algo que solo tú puedes dar (un CSV de reseñas, un navegador para el agente) o por un error ([orquestacion.md](orquestacion.md)).

**Dónde:** chat nuevo · Haiku 5.5, esfuerzo bajo (el orquestador), abierto desde la carpeta donde vive `product/`

```text
Usa hb-product en modo autónomo: <la idea en tus palabras, o "la descripción está en <ruta absoluta del archivo>">. Sin preguntas: lo que falte va a Supuestos sin confirmar. En cada puerta decide con decidir --automatico, salvo que siguiente --json diga detener. Lanza los subagentes siempre en primer plano, los que corren juntos en un mismo mensaje, y no cierres tu turno mientras corre uno. En cada parada, pon arriba el recordatorio de /cost con su comando armado. No hagas commit ni push.
```

Al terminar, revisa las decisiones automáticas en el reporte o en el tablero; para deshacer una:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta <n> --reabrir --carpeta product
```

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

**Dónde:** terminal, sin chat. `producto.py siguiente` (y la última respuesta de la sesión anterior) ya trae el banner con el veredicto y la recomendación de la skill, los criterios uno por uno y los comandos completos, **el recomendado primero**; el agente nunca los corre. Uno de estos:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --seguir --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --ajustar <sesión> --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --descartar "<motivo>" --carpeta product
```

Si decides distinto de lo que recomienda la skill (también si ajustas otra sesión que la recomendada), agrega por qué; queda registrado como decisión contra la recomendación:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --seguir --motivo "<por qué decides distinto>" --carpeta product
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

Con un orquestador: `--sesion orquestador --incluye <las sesiones que lanzó ese chat>` y el total del chat (lo que muestre `/cost`), sin `--tokens`: los de cada subagente ya van por sesión; el orquestador te lo recuerda arriba de cada parada, con el comando armado. Cada chat orquestador anota con su `--chat` (el comando armado ya lo trae): si ese mismo chat vuelve a anotar en otra parada, con el mismo `--chat` actualiza su fila (`/cost` es acumulado) y no la cuenta dos veces; otro chat orquestador usa uno nuevo y va en otra fila. Con GitHub Copilot CLI, `--creditos <AI Credits>` en vez de `--costo`. Si solo anotas tokens, el total dice "sin dato en USD", nunca 0.

### Guardar una idea para después, o recuperarla

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py archivar --motivo "<motivo>" --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py reabrir --idea <nombre> --carpeta product
```

### Ver el reporte de una idea o el tablero de todas

**Dónde:** terminal, sin chat. El reporte (`reporte.html`, en la carpeta de la idea) se regenera solo al decidir cada puerta y al archivar; para regenerarlo a mano, o el de una idea archivada:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py reporte --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py reporte --idea <nombre> --carpeta product
```

El tablero reúne todas las ideas que encuentre bajo una carpeta (en curso y archivadas) en `<carpeta>/index.html`, con el enlace a cada reporte. Se regenera solo con `nuevo`, `cerrar`, `decidir`, `archivar` y `reabrir`, en la carpeta que fijes con `--raiz` (por ejemplo, `nuevo --nombre "<nombre>" --raiz <carpeta con tus ideas> …`; queda guardada) o, sin ella, en la más cercana hacia arriba que ya tenga un tablero. Nunca pisa un `index.html` que no generó la skill. Para armarlo a mano:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py tablero --raiz <carpeta con tus ideas>
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
