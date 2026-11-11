-- En qué estado pasó el tiempo el hilo principal: corriendo, esperando CPU o dormido
-- grupos: base peor
-- requiere: ftrace:sched/sched_switch
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT CASE ts.state WHEN 'Running' THEN 'corriendo' WHEN 'R' THEN 'esperando CPU (R)' WHEN 'R+' THEN 'esperando CPU (R+)'
         WHEN 'S' THEN 'dormido (S)' WHEN 'D' THEN 'bloqueado en E/S (D)' ELSE IFNULL(ts.state, 'otro') END AS estado,
       ROUND(SUM(ts.dur) / 1e6) AS ms, ROUND(100.0 * SUM(ts.dur) / SUM(SUM(ts.dur)) OVER (), 1) AS pct
FROM thread_state ts JOIN hilo ON ts.utid = hilo.utid, app
WHERE ts.ts >= app.t0
GROUP BY 1 ORDER BY ms DESC LIMIT 8;
