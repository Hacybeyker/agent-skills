-- Ráfagas de inflate en el hilo principal en los 500 ms siguientes al fin de cada llamada de red:
-- vistas o adapters que se recrean con cada respuesta.
SELECT h.name AS llamada,
       ROUND((h.ts + h.dur - (SELECT start_ts FROM trace_bounds)) / 1e6, 0) AS fin_ms,
       (SELECT COUNT(*) FROM slice s
        JOIN thread_track tt ON s.track_id = tt.id
        JOIN thread t USING (utid)
        JOIN process p USING (upid)
        WHERE p.name = '{{PAQUETE}}' AND t.tid = p.pid AND s.name = 'inflate'
          AND s.ts BETWEEN h.ts + h.dur AND h.ts + h.dur + 500000000) AS inflates_500ms
FROM slice h
WHERE h.name GLOB 'HTTP *' AND h.dur > 0
ORDER BY inflates_500ms DESC LIMIT 20;
