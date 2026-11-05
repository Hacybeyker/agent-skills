-- Ráfagas de inflate en el hilo principal en los 500 ms que siguen a cada respuesta (vistas o adapters recreados)
-- grupos: red
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid)
SELECT h.name AS llamada, ROUND((h.ts + h.dur - app.t0) / 1e6) AS fin_ms,
       (SELECT COUNT(*) FROM slice s JOIN main ON s.track_id = main.track
        WHERE s.name = 'inflate' AND s.ts BETWEEN h.ts + h.dur AND h.ts + h.dur + 500000000) AS inflates_500ms
FROM slice h, app
WHERE h.name GLOB 'HTTP *' AND h.dur > 0 AND h.ts >= app.t0
ORDER BY inflates_500ms DESC LIMIT 15;
