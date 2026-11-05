-- El hilo principal en orden: slices de primer nivel de más de 16 ms y marcas propias (los primeros 30)
-- grupos: arranque
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT ROUND((s.ts - app.t0) / 1e6, 1) AS desde_ms, ROUND(s.dur / 1e6, 1) AS ms, SUBSTR(s.name, 1, 50) AS slice
FROM slice s, app
WHERE ((s.track_id IN (SELECT track FROM main) AND s.depth = 0 AND s.dur > 16000000)
       OR s.name GLOB 'NAV *' OR s.name GLOB 'SCREEN *' OR s.name GLOB 'reportFullyDrawn*') AND s.ts >= app.t0
ORDER BY s.ts LIMIT 30;
