# Prompts listos para copiar

Para el usuario, no para el agente. Cada caso dice dónde va (un chat nuevo, con el nivel de modelo que conviene, o la terminal) y trae, en un bloque aparte, el texto para pegar: **copia solo el bloque**. Lo que va entre `<>` se completa.

- **Después del primer pedido, solo pegas lo que imprime `producto.py siguiente`:** cada sesión termina con el paso que sigue, con el texto de cada chat o el comando completo. También queda en "Siguiente paso" de `estado.md`.
- **Cada sesión va en un chat nuevo.** Cada paso del agente reenvía todo el chat, y uno que encadena sesiones cuesta varias veces más.
- **Niveles de modelo:** *intermedio* para la sesión 0 y las cinco líneas de investigación; *alto* para la diferenciación, la síntesis, la estrategia, la validación y el PRD. En Claude Code, por ejemplo, Sonnet y Opus; con otra herramienta, sus equivalentes.
- **La carpeta** es `product/` dentro de la carpeta donde abres el chat. Para usar otra, agrégala al pedido ("en la carpeta `docs/producto`") o anótala en `AGENTS.md`: una sección `## Producto` con la línea `Carpeta: docs/producto`.
- **Cada texto termina con "No hagas commit ni push."** La skill ya lo dice; la línea explícita evita sorpresas.

## Empezar

### Una idea nueva (sesión 0)

**Dónde:** chat nuevo · modelo intermedio

```text
Usa hb-product: tengo una idea de app. <La idea en tus palabras: qué problema resuelve, para quién, en qué plataformas y países, cómo piensas ganar dinero, cuánto quieres ganar al mes y cuántas semanas tienes para construirla>. No hagas commit ni push.
```

No hace falta responder todo: el agente pregunta lo que falte en una sola tanda, crea la carpeta y termina con los cinco chats de la investigación.

### Una idea en un mercado con muchas apps

**Dónde:** chat nuevo · modelo intermedio

```text
Usa hb-product: quiero hacer <tipo de app> aunque ya hay muchas. Quiero saber cómo diferenciarme antes de construirla: <para quién, plataformas, países, meta de ingresos al mes y semanas disponibles>. No hagas commit ni push.
```

La cantidad de competidores no descarta la idea: la investigación busca un diferenciador con evidencia.

### Una idea que no existe todavía

**Dónde:** chat nuevo · modelo intermedio

```text
Usa hb-product: tengo una idea de app que no encontré en ninguna tienda: <la idea, el problema que resuelve y cómo lo resuelve hoy la gente>. <Plataformas, países, meta de ingresos al mes y semanas disponibles>. No hagas commit ni push.
```

La falta de datos tampoco la descarta: la investigación trabaja por analogía.

## Seguir

### Abrir un carril de la investigación

**Dónde:** un chat nuevo por carril, a la vez · el modelo que diga `siguiente`

Copia el texto que imprime `producto.py siguiente` para cada sesión. Tiene esta forma:

```text
Sigue hb-product con <ruta absoluta>/product/estado.md: sesión 1c · Demanda. No hagas commit ni push.
```

Las sesiones 1a a 1e se abren juntas. La 1g aparece apenas cierran 1a y 1b; la 1f, cuando cierran las seis.

### Los carriles con subagentes, en un solo chat

**Dónde:** chat nuevo · modelo intermedio (los subagentes de 1g y 1f, alto)

```text
Sigue hb-product con <ruta absoluta>/product/estado.md como orquestador: lanza un subagente por cada sesión que ofrezca producto.py siguiente, con su texto para pegar; cuando terminen, vuelve a correr siguiente y lanza las que se abran, hasta llegar a la puerta. No investigues tú ni corras decidir. No hagas commit ni push.
```

Sirve si tu herramienta tiene subagentes. El chat orquestador no investiga: espera y lanza lo que se abre.

### Retomar donde quedó

**Dónde:** chat nuevo · el modelo que diga "Siguiente paso" de `estado.md`

```text
Sigue hb-product con <ruta absoluta>/product/estado.md. No hagas commit ni push.
```

### Ver por dónde va

**Dónde:** terminal, sin chat

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py estado --carpeta product
```

## Decidir en una puerta

**Dónde:** terminal, sin chat. Los comandos completos los imprime `producto.py siguiente`; el agente nunca los corre.

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py puerta --n 1 --carpeta product
```

Y después, uno de estos:

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --seguir --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --ajustar <sesión> --carpeta product
```

```bash
cd <raíz> && python3 -I <skill>/scripts/producto.py decidir --puerta 1 --descartar "<motivo>" --carpeta product
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
