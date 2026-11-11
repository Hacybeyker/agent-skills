-- Frames por tipo de jank ('App Deadline Missed' es de la app; los Stuffing son de composición)
-- grupos: base
-- requiere: ds:android.surfaceflinger.frametimeline
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT IFNULL(a.jank_type, 'None') AS tipo, COUNT(*) AS frames, ROUND(AVG(a.dur) / 1e6, 1) AS prom_ms,
       ROUND(MAX(a.dur) / 1e6, 1) AS max_ms
FROM actual_frame_timeline_slice a JOIN app ON a.upid = app.upid
GROUP BY tipo ORDER BY frames DESC LIMIT 8;
