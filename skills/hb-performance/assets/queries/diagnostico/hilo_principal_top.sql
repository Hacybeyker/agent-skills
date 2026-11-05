-- Los 20 slices más largos del hilo principal (nivel superior), con su momento desde el inicio de la traza.
SELECT s.name AS slice, ROUND(s.dur / 1e6, 1) AS ms,
       ROUND((s.ts - (SELECT start_ts FROM trace_bounds)) / 1e6, 0) AS t_ms
FROM slice s
JOIN thread_track tt ON s.track_id = tt.id
JOIN thread t USING (utid)
JOIN process p USING (upid)
WHERE p.name = '{{PAQUETE}}' AND t.tid = p.pid AND s.depth = 0
ORDER BY s.dur DESC LIMIT 20;
