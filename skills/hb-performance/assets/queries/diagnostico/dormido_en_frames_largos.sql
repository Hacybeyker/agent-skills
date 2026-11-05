-- Dónde duerme el hilo principal dentro de los 3 doFrame más largos (esperas de más de 1 ms y el slice que las contiene)
-- grupos: base
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
fr AS (SELECT s.ts, s.dur FROM slice s JOIN main ON s.track_id = main.track
       WHERE s.depth = 0 AND s.name GLOB 'Choreographer#doFrame*' ORDER BY s.dur DESC LIMIT 3),
sl AS (SELECT fr.ts AS frame_ts, fr.dur AS frame_dur, ts.ts, ts.dur, ts.state
       FROM fr JOIN thread_state ts ON ts.utid IN (SELECT utid FROM hilo) AND ts.ts >= fr.ts AND ts.ts < fr.ts + fr.dur
       WHERE ts.state IN ('S', 'D') AND ts.dur > 1000000)
SELECT ROUND((sl.frame_ts - app.t0) / 1e6) AS frame_t_ms, ROUND(sl.frame_dur / 1e6, 1) AS frame_ms, sl.state AS estado,
       ROUND(sl.dur / 1e6, 1) AS ms,
       (SELECT SUBSTR(s.name, 1, 45) FROM slice s JOIN main ON s.track_id = main.track
        WHERE s.ts <= sl.ts AND s.ts + s.dur >= sl.ts + sl.dur ORDER BY s.depth DESC LIMIT 1) AS dentro_de
FROM sl, app
ORDER BY sl.dur DESC LIMIT 12;
