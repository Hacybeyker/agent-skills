-- Métricas de una corrida, en una sola consulta (un solo resultado) para que funcione con cualquier versión
-- de trace_processor. perf.py reemplaza {{PAQUETE}} y calcula las métricas a partir de estas filas.
-- tipo: proceso | limites | frame (FrameTimeline) | hilo (hilo principal) | seccion (HTTP, TTFB, SCREEN, NAV)
SELECT 'proceso' AS tipo, 0 AS ts, 0 AS dur, 0 AS prof, name AS nombre
FROM process WHERE name = '{{PAQUETE}}'
UNION ALL
SELECT 'limites', start_ts, end_ts - start_ts, 0, '' FROM trace_bounds
UNION ALL
SELECT 'frame', a.ts, a.dur, 0, IFNULL(a.jank_type, 'None')
FROM actual_frame_timeline_slice a JOIN process p USING (upid)
WHERE p.name = '{{PAQUETE}}'
UNION ALL
SELECT 'hilo', s.ts, s.dur, s.depth, s.name
FROM slice s
JOIN thread_track tt ON s.track_id = tt.id
JOIN thread t USING (utid)
JOIN process p USING (upid)
WHERE p.name = '{{PAQUETE}}' AND t.tid = p.pid
  AND ((s.depth = 0 AND s.dur >= 5000000) OR s.name = 'inflate')
UNION ALL
SELECT 'seccion', ts, dur, depth, name
FROM slice
WHERE name GLOB 'HTTP *' OR name GLOB 'TTFB *' OR name GLOB 'SCREEN *' OR name GLOB 'NAV *';
