-- Pares de llamadas al mismo endpoint en vuelo a la vez: la señal más clara de una carga duplicada
-- grupos: red
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT a.name AS llamada, COUNT(*) AS pares_solapados, ROUND(MIN(b.ts - a.ts) / 1e6) AS separacion_min_ms
FROM slice a JOIN slice b ON a.name = b.name AND b.ts > a.ts AND b.ts < a.ts + a.dur, app
WHERE a.name GLOB 'HTTP *' AND a.ts >= app.t0
GROUP BY a.name ORDER BY pares_solapados DESC LIMIT 15;
