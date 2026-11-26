# Investigación: las 5 líneas (sesiones 1a a 1e)

Cada línea es una sesión en su propio chat (o en su propio subagente) y pueden correr las cinco a la vez. Lee también [evidencia.md](evidencia.md); si la idea es nueva, [analogia.md](analogia.md).

## Presupuesto y lista de tareas

**Presupuesto por línea:** 15 búsquedas y 10 lecturas; 20 y 12 si la idea es nueva (`producto.py tipo` lo dice). **Cada reapertura** (un ajuste en una puerta) tiene su propio presupuesto, la mitad del original (8 y 5; 10 y 6 en una idea nueva): el texto para pegar lo dice, y `fuente` cuenta las lecturas de esa pasada. Es la única: si al cerrar lo que pidió la puerta sigue sin resolverse, la puerta no vuelve a recomendar esa línea para buscar más ([puertas.md](puertas.md)). Al llegar al 80 %, dilo en el chat y cierra con lo que tienes; si te pasas, `cerrar` lo avisa y la síntesis y la puerta que sigue lo muestran. Una lectura es una página abierta y resumida, no un resultado de búsqueda.

**Una lectura fallida no cuenta como lectura.** Una página que no se pudo leer (un 403, un muro, un PDF descargado sin una herramienta para extraer su texto) no se registra con `fuente`, porque no leíste nada, ni se suma a `--lecturas`. Si deja un hueco (lo que esa página tenía que cubrir queda sin fuentes), regístralo como vacío por límite de las herramientas, con lo que intentaste: `producto.py vacio --linea <l> --mercado|--idioma|--tienda <v>|--peldano <n> --motivo herramienta --texto "<qué no se pudo leer y por qué>"`. Así la puerta no lo cuenta como buscado y sin resultado, y no pide ajustar la línea con las mismas herramientas.

**Extractos de búsqueda (`fuente --extracto`).** A veces el dato está entero en el extracto que muestra el buscador y no hace falta abrir la página. Regístralo con `--extracto`: no cuenta como lectura (ya cuenta la búsqueda que lo trajo), así `--lecturas` y el aviso del 80 % miden páginas abiertas, y la fuente queda marcada en el registro, en `triangulacion` y en el reporte. En una reapertura, `fuente` cuenta solo los extractos de esta pasada, igual que las lecturas. Para la confianza y la triangulación cuenta como cualquier fuente, así que úsalo solo cuando:

- el dato es **puntual y verificable en el extracto**: una cifra con su fecha y su autor, el precio o la nota de una ficha, el título y la fecha de un artículo que dice lo que citas;
- y el extracto trae la **fecha de publicación** (si no, `--publicada desconocida`, que no cuenta para la confianza).

**Abre la página** (y regístrala sin `--extracto`) cuando el dato depende del contexto (una reseña, una opinión, un hilo), cuando el extracto está cortado o no muestra la fecha, cuando es una política (`--tipo oficial` no admite `--extracto`: la norma se lee en su página) o cuando el hallazgo es clave y es su única fuente de ese tipo. Si después abres una página que registraste como extracto, repite `fuente` con la misma URL y sin `--extracto`: pasa a contar como lectura en esa pasada, y el resumen que pases reemplaza al del extracto.

**Varias fuentes de una sola lectura (`fuente --misma-lectura S-…`).** Si una sola lectura trae varias fuentes (una API pública que devuelve la ficha de cada mercado, un listado con varias apps), registra la primera como siempre y las demás con `--misma-lectura <ID de la primera>`: todas cuentan como una lectura en el aviso de `fuente`, en `--lecturas` y en el presupuesto de la reapertura. Tiene que ser de tu misma línea y una lectura (no un extracto). No cambia la independencia ni la confianza: cada fuente sigue contando por su autor, su dominio o su editor. El aviso del 80 % de `fuente` solo salta cuando la fuente gasta una lectura: no con un extracto, con una de `--misma-lectura` ni al sumar cobertura a una ya registrada.

**Fuentes de un mismo editor (`fuente --editor`).** Lo que un producto publica sobre sí mismo (su ficha en cada tienda y país, su etiqueta de privacidad, su web, su nota de prensa) es **un solo autor**, su editor: tres fuentes así no triangulan un hallazgo ([evidencia.md](evidencia.md) · Triangulación). Las fichas de tienda se juntan solas por la app de la URL y por la fila de la matriz; pasa `--editor C-…` (o el nombre de la empresa) cuando registres la web, el blog, la nota de prensa o la página de ventas de una app, que el script no puede asociar a su ficha. No lo pases en una reseña de usuarios ni en un artículo de un medio que no es del editor (una comparativa, una reseña de prensa): esos son otros autores. Para triangular lo que dice un producto de sí mismo, busca voces que no sean la suya: sus usuarios, la prensa o un dato medido.

1. Primera línea: `Sesión 1c · Demanda (<motivo>)`.
2. Lee `00-idea.md` y `criterios.md`. No leas los archivos de las otras líneas: están a medias.
3. `producto.py tipo`: el tipo de idea y tu presupuesto. La sesión 0 deja un tipo provisional antes de abrir las líneas y la 1a lo confirma; trabaja con él desde el inicio (si es nueva, por analogía: [analogia.md](analogia.md)). Vuelve a consultarlo antes de cerrar: si cambió y tu línea no tiene fuentes de los peldaños que pide el tipo nuevo, la puerta la marca "a revisar por cambio de tipo" y recomienda ajustarla.
4. `producto.py cobertura --linea <tu línea>`: los mercados, idiomas y tiendas que te tocan. Busca según la tabla de tu línea **en cada uno**, no solo en el que más resultados da.
5. Por cada página útil, `producto.py fuente` con la cobertura que aporta (`--mercados`, `--idiomas`, `--tiendas`). Nunca copies la página: 3 líneas en `--resumen`.
6. Cuando una afirmación tiene sus fuentes, `producto.py hallazgo`; los que sostienen el puntaje o una puerta llevan `--critico`. Si después encuentras otra fuente para un hallazgo tuyo, súmala con `producto.py hallazgo --id H-… --fuentes S-…` (mismo ID, la confianza se recalcula; solo con tu sesión abierta); la evidencia en contra que aparezca después, con `--id H-… --en-contra S-…`, igual.
7. **Abogado del diablo:** por cada hallazgo clave, una búsqueda en contra, registrada con `--en-contra` o `--sin-contra`.
8. Lo que quedó sin fuentes, regístralo como vacío con su motivo (`producto.py vacio`, abajo). La línea no cierra con huecos sin registrar.
9. Completa tu `.md` con los IDs, tu lectura y la salida de `cobertura`. Lo que no tiene fuente va en "⚠ Sin evidencia". Tus notas para las otras sesiones van en "Para la síntesis", no en `estado.md`.
10. `producto.py cerrar --sesion <id> --busquedas <n> --lecturas <n>` (lo que usó la línea **en esta pasada**) y pega la salida.

**No hagas:** escribir en archivos de otra línea, calcular puntajes o tamaños por tu cuenta, recomendar seguir o descartar, ni seguir con otra sesión en el mismo chat.

## Cobertura por mercado, idioma y tienda

La sesión 0 registra el objetivo (`producto.py objetivo --mercados MX,ES --idiomas es,pt --tiendas google-play,app-store`). Cada línea cubre lo que le corresponde:

| Línea | Necesita fuentes de cada |
| --- | --- |
| Competencia | Mercado y tienda |
| Voz del usuario | Idioma y tienda |
| Demanda | Mercado |
| Monetización | Mercado |
| Políticas y riesgos | Mercado y tienda |

- Una fuente cubre lo que dicen sus etiquetas: `fuente … --mercados MX --idiomas es --tiendas google-play`. Usa las mismas etiquetas que el objetivo. Si ya registraste la URL, repetir `fuente` con etiquetas nuevas se las agrega sin duplicarla.
- Lo que no se pudo cubrir se registra como **vacío**, con un motivo: `producto.py vacio --linea voz-del-usuario --tienda google-play --motivo herramienta --texto "<qué intentaste y qué pasó>"`. **Cualquier línea** registra vacíos de cualquier mercado, idioma o tienda del objetivo, también los que la tabla no le pide (por ejemplo, la monetización sin la ficha de precios de Google Play): `cobertura` y la puerta 1 los muestran junto a los demás.

| `--motivo` | Cuándo |
| --- | --- |
| `herramienta` | La página existe, pero tus herramientas no la leen: dinámica, bloqueada o con inicio de sesión |
| `sin-resultados` | Buscaste en ese mercado o idioma y no hay nada sobre el tema. Es evidencia: dilo así en tu archivo |
| `presupuesto` | Se te acabaron las búsquedas antes de llegar |

- **Por peldaño (idea nueva).** Lo que buscaste en un peldaño de la escalera sin encontrar nada se registra igual: `producto.py vacio --linea demanda --peldano 4 --motivo sin-resultados --texto "<qué buscaste>"`. Así la puerta distingue **lo buscado sin resultado** (evidencia: si ningún peldaño muestra el problema, es motivo de descarte) de **lo no buscado** (no lo es: recomienda ajustar la línea). `producto.py estado` cuenta los hallazgos por peldaño, vigentes y vencidos, y cada vacío por peldaño con lo que pasó: "buscado sin resultado" solo con `--motivo sin-resultados`; con `herramienta`, "sin leer por límite de las herramientas", y con `presupuesto`, "sin buscar por falta de presupuesto".

- `producto.py cobertura` lista por línea lo cubierto (✔), los vacíos (⚠) y los huecos sin registrar (✖). La síntesis y la puerta 1 los muestran. Un vacío de algo que ya tiene fuentes (las reseñas en español sí, Reddit en español no) es un **vacío parcial**: sale junto a su ✔ (`⚠ vacío parcial V-VOZ-1 (límite de las herramientas): …`), y la puerta 1, `siguiente` y el reporte lo muestran sin cambiar la cobertura ni el veredicto.

## Fuentes difíciles

Las reseñas de Google Play y de la App Store, Reddit, los foros, TikTok y YouTube son justo las fuentes de la voz del usuario, y casi siempre son páginas dinámicas o bloqueadas para una lectura web simple. En este orden:

1. **Herramientas de navegador.** Si las tienes (Claude in Chrome, el navegador integrado de tu herramienta u otro), úsalas para esas páginas: abrir la ficha, ordenar por recientes, filtrar de 1 a 3★ y leer lo visible. Las mismas reglas: solo lo público, sin iniciar sesión, sin saltar muros, sin automatizar más allá de leer, y cada página cuenta como una lectura del presupuesto. La fuente es la URL de la página.
2. **Un CSV que aporta el usuario.** Si el usuario exportó reseñas (de una herramienta suya o de su propia recolección), regístralo como fuente: `producto.py fuente --linea voz-del-usuario --archivo <ruta.csv> --autor "<app> · <tienda>" --publicada auto --tipo usuario --peldano 1 --resumen "…" --tiendas <tienda>`. `--publicada auto` toma la fecha de la reseña más reciente; los idiomas salen de su columna, si la tiene. Léelo con `producto.py resenas --archivo <ruta.csv> [--estrellas 1-3] [--idioma es] [--limite 30]`: muestra las recientes primero, cortas y **sin columnas de autor**. Nunca abras el CSV entero en el chat. Dos CSV de la misma app y tienda cuentan como una sola fuente.
3. **Si nada de eso alcanza**, registra el vacío con `--motivo herramienta`. No es falta de evidencia: es un límite de las herramientas, y la puerta 1 lo muestra así. **No sugieras reabrir la línea** para resolverlo: con las mismas herramientas da lo mismo. Lo que sí lo resuelve es un navegador o un CSV; dilo en "Para la síntesis".

## 1a · Competencia

| Qué buscar | Dónde |
| --- | --- |
| Top 10 de la categoría por tienda y por mercado | Fichas públicas de las tiendas (Google Play, App Store) y sus listas |
| Apps que hacen lo mismo o una parte | Búsqueda en las tiendas con los términos del usuario, "alternativas a <app>", directorios y comparativas |
| Datos de cada competidor | Su ficha: descargas, nota, última actualización, precio, tamaño, idiomas, permisos y funcionalidades |
| Intentos anteriores | "<idea> cerró", "post-mortem", lanzamientos abandonados, fichas sin actualizar hace años |

- **Matriz de competidores.** Una fila por competidor con `producto.py competidor --nombre "<app>" --peldano <1-4> --fuentes S-COM-… [--descargas 1M] [--nota 4,2] [--actualizada 2026-03] [--precio "…"] [--modelo "…"] [--anuncios ninguno|pocos|muchos|si|no] [--tamano-mb 80] [--idiomas es,en] [--permisos ubicacion,camara] [--sin-conexion si|no|parcial] [--accesibilidad "…"] [--plataformas android,ios] [--funciones "a; b"] [--traccion "…"]`. Una fila se completa por partes: repetir el comando con el mismo nombre agrega columnas. Si la ficha solo dice «Contiene anuncios», `--anuncios si` (queda «sí», sin saber cuántos, hasta que un nivel lo reemplace); `no` equivale a `ninguno`. El peldaño de la fila dice qué es: 1 directo, 2 variante, 3 análogo, 4 sustituto. `producto.py matriz` muestra la tabla; pégala en `competencia.md`.
- **Sustitutos.** Registra siempre cómo se resuelve hoy la necesidad sin una app así (peldaño 4): la función que ya trae el sistema, una hoja de cálculo, un grupo de chat, papel. Cada uno con `--sustituto nativo|gratuito|pago` y `--resuelve si|parcial|no`; sin al menos uno evaluado, 1a no cierra. Si uno gratuito o nativo ya resuelve la necesidad, la sesión 1g tendrá que superarlo con evidencia ([diferenciacion.md](diferenciacion.md)), y la voz del usuario lo enlaza con `--competidores` cuando encuentra quejas sobre él.
- **El rival a superar.** Marca la alternativa gratis más fuerte, sea un sustituto o un competidor directo gratis y completo: `producto.py competidor --nombre "<app>" --peldano 1 --fuentes S-COM-… --rival`. Si ninguna alternativa gratis resuelve la necesidad, dilo con `producto.py competidor --sin-rival "<por qué>"`. En una idea existente o variante, 1a no cierra sin una de las dos: la sesión 1g compara cada diferenciador con ese rival ([diferenciacion.md](diferenciacion.md)).
- **Tracción.** Un competidor la tiene desde 100 000 descargas (`traccion_descargas`), con la fuente de su fila, o con un respaldo institucional documentado en esas fuentes (`--respaldo "<el ministerio, el organismo o el programa que lo respalda>"`). Si la fuente da valoraciones y no descargas (en App Store es la única señal pública), regístralas con `--valoraciones <n>`: desde 2 000 (`traccion_valoraciones`) es **tracción estimada por valoraciones**; con descargas registradas, las valoraciones no cuentan. `--traccion "<nota>"` queda como contexto y no cuenta: una fila con 10 000 descargas o sin datos no tiene tracción por lo que diga su nota. La puerta 1 de una idea nueva nombra los análogos que cuenta y los que no.
- **Tipo de idea.** La sesión 0 deja uno provisional; confírmalo apenas lo sepas, porque las otras líneas trabajan con él: `producto.py tipo --existente | --variante | --nueva --motivo "<por qué>"` (sin `--provisional`). 1a no cierra sin confirmarlo. *Existente:* hay competidores directos con tracción. *Variante:* hay directos, pero la idea cambia algo relevante (otra plataforma, otro país, otro segmento). *Nueva:* no hay directos con tracción. Si no hay directos, sube por la escalera y llena la matriz con análogos y sustitutos.
- **Intentos anteriores.** Regístralo siempre con `producto.py intento --resultado sin-rastro | fracaso-demanda | fracaso-otra-causa --texto "<qué buscaste y qué apareció>" [--fuentes S-…]`. En una idea nueva es un criterio de la puerta 1.
- **No es un criterio** cuántos competidores hay. Anota la saturación como un hecho, sin valorarla.

## 1b · Voz del usuario

| Qué buscar | Dónde |
| --- | --- |
| Dolores, pedidos y quejas de cada competidor | Reseñas de 1 a 3★ visibles en la ficha, ordenadas por recientes, en cada idioma y tienda del objetivo (ver "Fuentes difíciles") |
| Cómo habla del problema quien lo tiene | Foros, Reddit, comentarios de YouTube y TikTok, grupos públicos, blogs |
| En una idea nueva | Quejas sobre cómo se resuelve hoy (peldaño 4) y conversaciones sobre la necesidad de fondo (peldaño 5) |

- Cuenta la **frecuencia por competidor**: en cuántas fuentes independientes aparece cada tema. No midas el tamaño del dolor con reseñas: exageran.
- Enlaza cada hallazgo con sus competidores **por su ID en la matriz** (`--competidor C-1,C-3`; `matriz` los lista): la sesión 1g necesita saber qué queja es de quién, y un diferenciador pide un dolor triangulado en 2 competidores o más. No los cites por nombre: la misma app aparece con nombres distintos según la tienda y el idioma ("Fakeit: Imposter Game" o "Fakeit"), y un nombre que no coincide queda sin enlazar. Si 1a todavía no registró esa fila, cita la URL de su ficha (o el nombre, como último recurso): el script la enlaza por la URL de la ficha cuando 1a la registra con esa misma fuente. Como 1a y 1b corren en paralelo, si la matriz de la 1a aún no tiene la fila, registra el hallazgo sin `--competidor` (o con la URL de la ficha) y enlázalo después, cuando la fila exista: `producto.py hallazgo --id H-VOZ-3 --competidor C-1,C-3`. Conserva el ID y la confianza, solo agrega enlaces, valida que los competidores existan y no estén anulados, y sirve aunque la 1b ya esté cerrada. No anules el hallazgo para volver a registrarlo: cambiaría su ID.
- Busca también a los usuarios satisfechos: es la evidencia en contra de esta línea.

## 1c · Demanda

| Qué buscar | Dónde |
| --- | --- |
| Volumen y tendencia de búsqueda | Herramientas públicas de tendencias de búsqueda, autocompletado de buscadores y de tiendas |
| Estacionalidad por mercado | La serie de tendencias de 12 meses o más |
| Tamaño de la audiencia | Descargas recientes de los competidores (de los últimos meses), estadísticas oficiales, reportes del sector |
| En una idea nueva: la necesidad de fondo | Censos, encuestas nacionales e investigación académica: datos estructurales que no caducan en 18 meses (`fuente --clase estadistica\|academica`, [evidencia.md](evidencia.md)) |

- Un hallazgo clave de demanda necesita **al menos una fuente de tipo `medido`** y **señales actuales**: tendencia y descargas de los últimos 12 a 18 meses. Las descargas acumuladas de una ficha (cientos de millones desde hace una década) son contexto: regístralas con `fuente --acumulado`, y no sostienen la demanda de hoy ni las anclas altas del puntaje.
- En una idea nueva se busca **el problema, no la solución**: lo que escribe la gente cuando tiene la necesidad. El tamaño se estima desde arriba con la población que la tiene (peldaño 6) y se dice que es una estimación, con sus supuestos.
- Si ningún peldaño muestra el problema, dilo tal cual: es el ancla 1 de demanda y un motivo real de descarte.

## 1d · Monetización

| Qué buscar | Dónde |
| --- | --- |
| Modelos y precios de la competencia o de los análogos | Fichas de las tiendas (compras dentro de la app), páginas de precios |
| eCPM por región y por formato | Reportes públicos de redes de anuncios y de mediación |
| Conversión a pago, DAU/MAU, retención | Reportes del sector, con su metodología |
| Afiliados y otros ingresos | Páginas públicas de los programas |

- Igual que en demanda, un hallazgo clave necesita una fuente `medido`.
- Deja en "Supuestos para los escenarios" cada valor con el ID de su fuente: la sesión 2 los pasa a `escenarios.json`.
- Si no hay competencia, usa los análogos más cercanos y di de cuál sale cada dato.

## 1e · Políticas y riesgos

| Qué buscar | Dónde |
| --- | --- |
| Políticas de las tiendas que tocan la idea | [Políticas para desarrolladores de Google Play](https://play.google.com/about/developer-content-policy/) y [App Store Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) |
| Leyes por mercado: niños, salud, finanzas, privacidad | Las páginas oficiales del regulador de cada mercado |
| Requisitos de cuenta y de publicación | La documentación oficial de cada tienda |
| Riesgos técnicos | Límites de las plataformas, dependencias de terceros, datos que hacen falta |

- Lee la política **en su fuente oficial**: regístrala con `--tipo oficial` y su `--version` (o la fecha de su última actualización). Una sola fuente oficial basta para un hallazgo de políticas; un blog que la resume es `terceros` y no alcanza.
- Si una tienda del objetivo **nombra la categoría o la rechaza** (por ejemplo, la cita como saturada o como funcionalidad mínima), registra el hallazgo con `--bloquea <tienda>`: el riesgo es 1 en esa tienda, salvo una mitigación escrita y creíble ([puntaje.md](puntaje.md)).
- Propón el ancla de riesgo de políticas según [puntaje.md](puntaje.md) y, si es 1, la mitigación: la puerta 1 la pide escrita.
- Una categoría que la tienda considera saturada o duplicada es un riesgo de políticas, no un juicio sobre la competencia.
