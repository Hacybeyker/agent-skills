-- Llamadas binder síncronas desde el hilo principal que superan 5 ms (IPC que bloquea la UI).
SELECT s.name AS slice, COUNT(*) AS veces, ROUND(SUM(s.dur) / 1e6, 1) AS total_ms, ROUND(MAX(s.dur) / 1e6, 1) AS max_ms
FROM slice s
JOIN thread_track tt ON s.track_id = tt.id
JOIN thread t USING (utid)
JOIN process p USING (upid)
WHERE p.name = '{{PAQUETE}}' AND t.tid = p.pid AND s.name GLOB 'binder transaction*' AND s.dur > 5000000
GROUP BY s.name ORDER BY total_ms DESC;
