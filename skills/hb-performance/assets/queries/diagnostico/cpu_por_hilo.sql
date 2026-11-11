-- CPU por grupo de hilos de la app (nombre sin números): corriendo, esperando CPU y dormido
-- grupos: base peor
-- requiere: ftrace:sched/sched_switch
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
st AS (SELECT CASE WHEN t.tid = app.pid THEN 'main' WHEN t.name = 'RenderThread' THEN 'RenderThread' ELSE RTRIM(IFNULL(t.name, '?'), '0123456789-_#: ') END AS grupo, t.utid, ts.state, ts.dur
       FROM thread_state ts JOIN thread t ON t.utid = ts.utid JOIN app ON t.upid = app.upid
       WHERE ts.ts >= app.t0)
SELECT grupo, COUNT(DISTINCT utid) AS hilos, ROUND(SUM(CASE WHEN state = 'Running' THEN dur END) / 1e6) AS cpu_ms,
       ROUND(SUM(CASE WHEN state IN ('R', 'R+') THEN dur END) / 1e6) AS espera_cpu_ms,
       ROUND(SUM(CASE WHEN state IN ('S', 'D') THEN dur END) / 1e6) AS dormido_ms
FROM st GROUP BY grupo ORDER BY cpu_ms DESC LIMIT 10;
