-- Secciones propias en orden: qué pantalla o navegación precede a cada llamada y cuánto dura cada una.
SELECT ROUND((ts - (SELECT start_ts FROM trace_bounds)) / 1e6, 0) AS t_ms, ROUND(dur / 1e6, 1) AS ms, name
FROM slice
WHERE name GLOB 'HTTP *' OR name GLOB 'TTFB *' OR name GLOB 'SCREEN *' OR name GLOB 'NAV *'
ORDER BY ts;
