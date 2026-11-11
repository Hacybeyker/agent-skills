-- Qué hay adentro de los slices largos del hilo principal: los 15 hijos más largos y su slice de primer nivel
-- grupos: base
-- requiere: atrace:view atrace_apps
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT SUBSTR(s.name, 1, 50) AS slice, s.depth AS nivel, ROUND(s.dur / 1e6, 1) AS ms, ROUND((s.ts - app.t0) / 1e6) AS t_ms,
       (SELECT SUBSTR(a.name, 1, 30) FROM ancestor_slice(s.id) a WHERE a.depth = 0) AS dentro_de
FROM slice s JOIN main ON s.track_id = main.track, app
WHERE s.depth > 0 AND s.dur > 4000000
ORDER BY s.dur DESC LIMIT 15;
