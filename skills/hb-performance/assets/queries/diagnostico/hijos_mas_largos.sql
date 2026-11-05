-- Qué hay adentro de los slices largos del hilo principal: los 30 slices hijos (cualquier nivel) que más duran.
SELECT s.name AS slice, s.depth AS nivel, ROUND(s.dur / 1e6, 1) AS ms,
       ROUND((s.ts - (SELECT start_ts FROM trace_bounds)) / 1e6, 0) AS t_ms
FROM slice s
JOIN thread_track tt ON s.track_id = tt.id
JOIN thread t USING (utid)
JOIN process p USING (upid)
WHERE p.name = '{{PAQUETE}}' AND t.tid = p.pid AND s.depth > 0 AND s.dur > 4000000
ORDER BY s.dur DESC LIMIT 30;
