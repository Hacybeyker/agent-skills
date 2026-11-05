-- Frames de la app en tramos de {{TRAMO_MS}} ms: cuántos, cuántos pierden su deadline y el doFrame más largo
-- grupos: base
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
f AS (SELECT CAST((a.ts - app.t0) / ({{TRAMO_MS}} * 1e6) AS INT) * {{TRAMO_MS}} AS desde_ms, a.dur,
             IFNULL(a.jank_type, 'None') AS jt
      FROM actual_frame_timeline_slice a JOIN app ON a.upid = app.upid),
d AS (SELECT CAST((s.ts - app.t0) / ({{TRAMO_MS}} * 1e6) AS INT) * {{TRAMO_MS}} AS desde_ms, MAX(s.dur) AS dmax
      FROM slice s JOIN main ON s.track_id = main.track, app
      WHERE s.depth = 0 AND s.name GLOB 'Choreographer#doFrame*' GROUP BY 1)
SELECT f.desde_ms, COUNT(*) AS frames, SUM(f.jt GLOB '*App Deadline Missed*') AS jank_app,
       ROUND(MAX(f.dur) / 1e6, 1) AS frame_max_ms,
       (SELECT ROUND(d.dmax / 1e6, 1) FROM d WHERE d.desde_ms = f.desde_ms) AS doframe_max_ms
FROM f GROUP BY f.desde_ms ORDER BY f.desde_ms LIMIT 20;
