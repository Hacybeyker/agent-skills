-- Contención de locks en los hilos de la app: quién espera, cuánto y el inicio del mensaje (dueño y lugar)
-- grupos: base
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
c AS (SELECT CASE WHEN t.tid = app.pid THEN 'main' WHEN t.name = 'RenderThread' THEN 'RenderThread' ELSE RTRIM(IFNULL(t.name, '?'), '0123456789-_#: ') END AS hilo, s.name, s.dur
      FROM slice s JOIN thread_track tt ON s.track_id = tt.id JOIN thread t ON t.utid = tt.utid JOIN app ON t.upid = app.upid
      WHERE (s.name GLOB 'monitor contention*'
             OR (s.name GLOB 'Lock contention on*' AND s.name NOT GLOB 'Lock contention on a monitor lock*'))
        AND s.ts >= app.t0)
SELECT hilo, SUBSTR(name, 1, 80) AS espera, COUNT(*) AS veces, ROUND(SUM(dur) / 1e6, 1) AS total_ms,
       ROUND(MAX(dur) / 1e6, 1) AS max_ms
FROM c GROUP BY hilo, SUBSTR(name, 1, 80) HAVING SUM(dur) > 1000000 ORDER BY total_ms DESC LIMIT 10;
