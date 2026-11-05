-- IPC síncrono (binder) del hilo principal de más de 2 ms, agrupado por el slice que lo llama
-- grupos: base
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT IFNULL((SELECT SUBSTR(p.name, 1, 50) FROM slice p WHERE p.id = s.parent_id), '(primer nivel)') AS dentro_de,
       COUNT(*) AS veces, ROUND(SUM(s.dur) / 1e6, 1) AS total_ms, ROUND(MAX(s.dur) / 1e6, 1) AS max_ms
FROM slice s JOIN main ON s.track_id = main.track, app
WHERE s.name = 'binder transaction' AND s.dur > 2000000 AND s.ts >= app.t0
GROUP BY 1 ORDER BY total_ms DESC LIMIT 10;
