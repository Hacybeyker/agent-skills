-- CPU muestreado (config cpu) por hilo, librería y función hoja; filtra hilos con --param HILO='patrón*'
-- grupos: cpu
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT CASE WHEN t.tid = app.pid THEN 'main' WHEN t.name = 'RenderThread' THEN 'RenderThread' ELSE RTRIM(IFNULL(t.name, '?'), '0123456789-_#: ') END AS hilo, REPLACE(m.name, RTRIM(m.name, REPLACE(m.name, '/', '')), '') AS libreria,
       SUBSTR(IFNULL(f.name, '?'), 1, 50) AS funcion, COUNT(*) AS muestras
FROM perf_sample ps JOIN thread t ON t.utid = ps.utid JOIN app ON t.upid = app.upid
JOIN stack_profile_callsite c ON c.id = ps.callsite_id
JOIN stack_profile_frame f ON f.id = c.frame_id
JOIN stack_profile_mapping m ON m.id = f.mapping
WHERE IFNULL(t.name, '?') GLOB '{{HILO}}'
GROUP BY 1, 2, 3 ORDER BY muestras DESC LIMIT 20;
