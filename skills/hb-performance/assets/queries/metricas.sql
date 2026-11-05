-- Métricas de una corrida, en una sola consulta (un solo resultado) para que funcione con cualquier versión
-- de trace_processor. perf.py reemplaza {{PAQUETE}} y calcula las métricas a partir de estas filas.
-- La app es la última instancia del proceso: en un arranque en frío, la que nace durante la traza.
-- tipo: proceso | limites | vsync (período esperado de frame) | frame (FrameTimeline) | hilo (hilo principal)
--       | seccion (HTTP, TTFB, SCREEN, NAV y reportFullyDrawn) | lanzamiento (launching: del sistema = TTID)
WITH app AS (SELECT upid, pid, name FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1)
SELECT 'proceso' AS tipo, 0 AS ts, 0 AS dur, 0 AS prof, name AS nombre FROM app
UNION ALL
SELECT 'limites', start_ts, end_ts - start_ts, 0, '' FROM trace_bounds
UNION ALL
SELECT 'vsync', 0, IFNULL((SELECT e.dur FROM expected_frame_timeline_slice e JOIN app ON e.upid = app.upid
                           GROUP BY e.dur ORDER BY COUNT(*) DESC LIMIT 1), 0), 0, ''
UNION ALL
SELECT 'frame', a.ts, a.dur, 0, IFNULL(a.jank_type, 'None')
FROM actual_frame_timeline_slice a JOIN app ON a.upid = app.upid
UNION ALL
SELECT 'hilo', s.ts, s.dur, s.depth, s.name
FROM slice s
JOIN thread_track tt ON s.track_id = tt.id
JOIN thread t ON t.utid = tt.utid
JOIN app ON t.upid = app.upid AND t.tid = app.pid
WHERE (s.depth = 0 AND s.dur >= 5000000) OR s.name = 'inflate'
UNION ALL
SELECT 'seccion', ts, dur, depth, name
FROM slice
WHERE name GLOB 'HTTP *' OR name GLOB 'TTFB *' OR name GLOB 'SCREEN *' OR name GLOB 'NAV *'
   OR name GLOB 'reportFullyDrawn*'
UNION ALL
SELECT 'lanzamiento', ts, dur, 0, name FROM slice WHERE name = 'launching: {{PAQUETE}}';
