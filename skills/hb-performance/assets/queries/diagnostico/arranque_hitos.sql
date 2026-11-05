-- Hitos del arranque en ms desde que nace el proceso: lanzamiento del sistema (TTID), bindApplication, actividad, primeros frames y reportFullyDrawn
-- grupos: arranque peor
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
h AS (
  SELECT 'lanzamiento (sistema)' AS hito, s.ts, s.dur FROM slice s WHERE s.name = 'launching: {{PAQUETE}}'
  UNION ALL
  SELECT s.name, s.ts, s.dur FROM slice s JOIN main ON s.track_id = main.track
  WHERE s.name IN ('bindApplication', 'activityStart', 'activityResume')
  UNION ALL
  SELECT * FROM (SELECT 'doFrame ' || ROW_NUMBER() OVER (ORDER BY s.ts), s.ts, s.dur FROM slice s
                 JOIN main ON s.track_id = main.track
                 WHERE s.depth = 0 AND s.name GLOB 'Choreographer#doFrame*' ORDER BY s.ts LIMIT 3)
  UNION ALL
  SELECT * FROM (SELECT s.name, s.ts, s.dur FROM slice s WHERE s.name GLOB 'NAV *' ORDER BY s.ts LIMIT 1)
  UNION ALL
  SELECT SUBSTR(s.name, 1, 40), s.ts, s.dur FROM slice s JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON t.utid = tt.utid JOIN app ON t.upid = app.upid WHERE s.name GLOB 'reportFullyDrawn*'
)
SELECT hito, ROUND((h.ts - app.t0) / 1e6) AS desde_ms, ROUND(h.dur / 1e6, 1) AS ms,
       ROUND((h.ts + h.dur - app.t0) / 1e6) AS hasta_ms
FROM h, app ORDER BY h.ts LIMIT 15;
