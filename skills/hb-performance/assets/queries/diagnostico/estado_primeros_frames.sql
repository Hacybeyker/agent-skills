-- Los dos primeros doFrame: estado del hilo principal y qué otros hilos de la app corrían a la vez (más de 3 ms)
-- grupos: arranque
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
fr AS (SELECT s.ts, s.dur, ROW_NUMBER() OVER (ORDER BY s.ts) AS n FROM slice s JOIN main ON s.track_id = main.track
       WHERE s.depth = 0 AND s.name GLOB 'Choreographer#doFrame*' ORDER BY s.ts LIMIT 2)
SELECT 'frame ' || fr.n AS frame, 'main ' || IFNULL(ts.state, 'otro') AS que, ROUND(SUM(ts.dur) / 1e6, 1) AS ms
FROM fr JOIN thread_state ts ON ts.utid IN (SELECT utid FROM hilo) AND ts.ts >= fr.ts AND ts.ts < fr.ts + fr.dur
GROUP BY fr.n, ts.state
UNION ALL
SELECT 'frame ' || fr.n, 'cpu ' || CASE WHEN t.tid = app.pid THEN 'main' WHEN t.name = 'RenderThread' THEN 'RenderThread' ELSE RTRIM(IFNULL(t.name, '?'), '0123456789-_#: ') END, ROUND(SUM(ts.dur) / 1e6, 1)
FROM fr JOIN thread_state ts ON ts.state = 'Running' AND ts.ts >= fr.ts AND ts.ts < fr.ts + fr.dur
JOIN thread t ON t.utid = ts.utid JOIN app ON t.upid = app.upid
WHERE t.utid NOT IN (SELECT utid FROM hilo)
GROUP BY fr.n, 2 HAVING SUM(ts.dur) > 3000000
ORDER BY 1, 3 DESC LIMIT 20;
