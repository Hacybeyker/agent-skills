-- Los 15 slices más largos del hilo principal (primer nivel)
-- grupos: base peor
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT SUBSTR(s.name, 1, 60) AS slice, ROUND(s.dur / 1e6, 1) AS ms, ROUND((s.ts - app.t0) / 1e6) AS t_ms
FROM slice s JOIN main ON s.track_id = main.track, app
WHERE s.depth = 0
ORDER BY s.dur DESC LIMIT 15;
