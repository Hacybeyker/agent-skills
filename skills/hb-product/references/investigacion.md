# Investigación: las 5 líneas (sesiones 1a a 1e)

Cada línea es una sesión en su propio chat (o en su propio subagente) y pueden correr las cinco a la vez. Lee también [evidencia.md](evidencia.md); si la idea es nueva, [analogia.md](analogia.md).

## Presupuesto y lista de tareas

**Presupuesto por línea:** 15 búsquedas y 10 lecturas; 20 y 12 si la idea es nueva (`producto.py tipo` lo dice). Al llegar al 80 %, dilo en el chat y cierra con lo que tienes. Una lectura es una página abierta y resumida, no un resultado de búsqueda.

1. Primera línea: `Sesión 1c · Demanda (<motivo>)`.
2. Lee `00-idea.md` y `criterios.md`. No leas los archivos de las otras líneas: están a medias.
3. `producto.py tipo`: el tipo de idea y tu presupuesto. Si todavía no está registrado, investiga como si hubiera competencia y vuelve a consultarlo antes de cerrar.
4. Busca según la tabla de tu línea, en los mercados y los idiomas de `00-idea.md`.
5. Por cada página útil, `producto.py fuente`. Nunca copies la página: 3 líneas en `--resumen`.
6. Cuando una afirmación tiene sus fuentes, `producto.py hallazgo`; los que sostienen el puntaje o una puerta llevan `--critico`.
7. **Abogado del diablo:** por cada hallazgo clave, una búsqueda en contra, registrada con `--en-contra` o `--sin-contra`.
8. Completa tu `.md` con los IDs y tu lectura. Lo que no tiene fuente va en "⚠ Sin evidencia". Tus notas para las otras sesiones van en "Para la síntesis", no en `estado.md`.
9. `producto.py cerrar --sesion <id>` y pega la salida.

**No hagas:** escribir en archivos de otra línea, calcular puntajes o tamaños por tu cuenta, recomendar seguir o descartar, ni seguir con otra sesión en el mismo chat.

## 1a · Competencia

| Qué buscar | Dónde |
| --- | --- |
| Top 10 de la categoría por tienda y por mercado | Fichas públicas de las tiendas (Google Play, App Store) y sus listas |
| Apps que hacen lo mismo o una parte | Búsqueda en las tiendas con los términos del usuario, "alternativas a <app>", directorios y comparativas |
| Datos de cada competidor | Su ficha: descargas, nota, última actualización, precio, tamaño, idiomas, permisos y funcionalidades |
| Intentos anteriores | "<idea> cerró", "post-mortem", lanzamientos abandonados, fichas sin actualizar hace años |

- **Matriz de competidores.** Una fila por competidor con `producto.py competidor --nombre "<app>" --peldano <1-4> --fuentes S-COM-… [--descargas 1M] [--nota 4,2] [--actualizada 2026-03] [--precio "…"] [--modelo "…"] [--anuncios ninguno|pocos|muchos] [--tamano-mb 80] [--idiomas es,en] [--permisos ubicacion,camara] [--sin-conexion si|no|parcial] [--accesibilidad "…"] [--plataformas android,ios] [--funciones "a; b"] [--traccion "…"]`. Una fila se completa por partes: repetir el comando con el mismo nombre agrega columnas. El peldaño de la fila dice qué es: 1 directo, 2 variante, 3 análogo, 4 sustituto. `producto.py matriz` muestra la tabla; pégala en `competencia.md`.
- **Tracción.** Un competidor la tiene desde 100 000 descargas (`traccion_descargas`) o con `--traccion "<evidencia>"` cuando no es una app o no publica descargas.
- **Tipo de idea.** Regístralo apenas lo sepas, porque las otras líneas lo consultan: `producto.py tipo --existente | --variante | --nueva --motivo "<por qué>"`. *Existente:* hay competidores directos con tracción. *Variante:* hay directos, pero la idea cambia algo relevante (otra plataforma, otro país, otro segmento). *Nueva:* no hay directos con tracción. Si no hay directos, sube por la escalera y llena la matriz con análogos y sustitutos.
- **Intentos anteriores.** Regístralo siempre con `producto.py intento --resultado sin-rastro | fracaso-demanda | fracaso-otra-causa --texto "<qué buscaste y qué apareció>" [--fuentes S-…]`. En una idea nueva es un criterio de la puerta 1.
- **No es un criterio** cuántos competidores hay. Anota la saturación como un hecho, sin valorarla.

## 1b · Voz del usuario

| Qué buscar | Dónde |
| --- | --- |
| Dolores, pedidos y quejas de cada competidor | Reseñas de 1 a 3★ visibles en la ficha, ordenadas por recientes |
| Cómo habla del problema quien lo tiene | Foros, Reddit, comentarios de YouTube y TikTok, grupos públicos, blogs |
| En una idea nueva | Quejas sobre cómo se resuelve hoy (peldaño 4) y conversaciones sobre la necesidad de fondo (peldaño 5) |

- Cuenta la **frecuencia por competidor**: en cuántas fuentes independientes aparece cada tema. No midas el tamaño del dolor con reseñas: exageran.
- Enlaza cada hallazgo con sus competidores (`--competidores "App A,App B"`): la sesión 1g necesita saber qué queja es de quién, y un diferenciador pide un dolor triangulado en 2 competidores o más. Si 1a todavía no registró esa fila, usa el nombre tal como figura en la tienda.
- Busca también a los usuarios satisfechos: es la evidencia en contra de esta línea.

## 1c · Demanda

| Qué buscar | Dónde |
| --- | --- |
| Volumen y tendencia de búsqueda | Herramientas públicas de tendencias de búsqueda, autocompletado de buscadores y de tiendas |
| Estacionalidad por mercado | La serie de tendencias de 12 meses o más |
| Tamaño de la audiencia | Descargas de los competidores, estadísticas oficiales, reportes del sector |

- Un hallazgo clave de demanda necesita **al menos una fuente de tipo `medido`**.
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

- Lee la política **en su fuente oficial y con su fecha**; un blog que la resume no alcanza para un hallazgo clave.
- Propón el ancla de riesgo de políticas según [puntaje.md](puntaje.md) y, si es 1, la mitigación: la puerta 1 la pide escrita.
- Una categoría que la tienda considera saturada o duplicada es un riesgo de políticas, no un juicio sobre la competencia.
