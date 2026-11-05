-- Frames de la app por tipo de jank. 'App Deadline Missed' es de la app; 'Buffer Stuffing' suele ser composición.
SELECT IFNULL(a.jank_type, 'None') AS tipo, COUNT(*) AS frames, ROUND(AVG(a.dur) / 1e6, 1) AS prom_ms,
       ROUND(MAX(a.dur) / 1e6, 1) AS max_ms
FROM actual_frame_timeline_slice a JOIN process p USING (upid)
WHERE p.name = '{{PAQUETE}}'
GROUP BY tipo ORDER BY frames DESC;
