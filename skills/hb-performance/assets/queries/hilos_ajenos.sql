-- CPU de los hilos de la app que no son el principal, dentro de la ventana del flujo, y cuánta cae dentro de cada llamada
-- HTTP. perf.py la corre solo si el plan declara hilos_ajenos, reemplaza {{PAQUETE}}, {{DESDE}} y {{HASTA}} (ns de la
-- traza) y aplica las expresiones regulares del plan a los nombres de hilo (aquí no se filtra por nombre).
-- tipo: hilo (una fila por nombre de hilo) | red (una fila por nombre de hilo y llamada con CPU dentro de la llamada)
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
run AS (SELECT t.utid, IFNULL(t.name, '?') AS nombre,
               MAX(ts.ts, MAX(app.t0, {{DESDE}})) AS s, MIN(ts.ts + ts.dur, {{HASTA}}) AS e
        FROM thread_state ts JOIN thread t ON t.utid = ts.utid JOIN app ON t.upid = app.upid
        WHERE ts.state = 'Running' AND t.tid != app.pid AND ts.ts < {{HASTA}}
          AND ts.ts + ts.dur > MAX(app.t0, {{DESDE}}))
SELECT 'hilo' AS tipo, nombre, '' AS llamada, COUNT(DISTINCT utid) AS hilos, ROUND(SUM(e - s) / 1e6, 3) AS cpu_ms
FROM run WHERE e > s GROUP BY nombre
UNION ALL
SELECT 'red', r.nombre, c.name, COUNT(DISTINCT r.utid), ROUND(SUM(MIN(r.e, c.ts + c.dur) - MAX(r.s, c.ts)) / 1e6, 3)
FROM run r JOIN slice c ON c.name GLOB 'HTTP *' AND c.dur > 0 AND r.s < c.ts + c.dur AND r.e > c.ts
WHERE r.e > r.s GROUP BY r.nombre, c.name;
