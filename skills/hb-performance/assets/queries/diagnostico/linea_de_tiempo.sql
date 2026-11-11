-- Marcas propias en orden (SCREEN, NAV, MARK, HTTP, QUEUE, CONN, TTFB, reportFullyDrawn): qué precede a cada llamada y cuánto dura
-- grupos: base
-- requiere: atrace_apps
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT ROUND((s.ts - app.t0) / 1e6) AS t_ms, ROUND(s.dur / 1e6, 1) AS ms, SUBSTR(s.name, 1, 70) AS marca
FROM slice s, app
WHERE (s.name GLOB 'HTTP *' OR s.name GLOB 'TTFB *' OR s.name GLOB 'QUEUE *' OR s.name GLOB 'CONN *' OR s.name GLOB 'SCREEN *' OR s.name GLOB 'NAV *' OR s.name GLOB 'MARK *'
       OR s.name GLOB 'reportFullyDrawn*') AND s.ts >= app.t0
ORDER BY s.ts LIMIT 40;
