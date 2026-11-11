-- Cuánto del tiempo de los 3 doFrame más largos del hilo principal se va dormido (S) o bloqueado (D), y la espera más
-- larga en D. perf.py diagnostico la corre para decidir si pide una captura con --config completa (umbrales:
-- BLOCKED_SHARE_MIN y BLOCKED_D_MIN_MS). Mira solo los frames largos: fuera de ellos, el hilo principal duerme
-- legítimamente cuando no tiene nada que hacer.
-- requiere: ftrace:sched/sched_switch atrace:view
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
fr AS (SELECT s.ts, s.dur FROM slice s JOIN main ON s.track_id = main.track
       WHERE s.depth = 0 AND s.name GLOB 'Choreographer#doFrame*' ORDER BY s.dur DESC LIMIT 3),
sl AS (SELECT ts.state, MIN(ts.ts + ts.dur, fr.ts + fr.dur) - MAX(ts.ts, fr.ts) AS d
       FROM fr JOIN thread_state ts ON ts.utid IN (SELECT utid FROM hilo) AND ts.ts < fr.ts + fr.dur AND ts.ts + ts.dur > fr.ts
       WHERE ts.state IN ('S', 'D'))
SELECT (SELECT COUNT(*) FROM fr) AS frames, ROUND(IFNULL((SELECT SUM(dur) FROM fr), 0) / 1e6, 1) AS frames_ms,
       ROUND(IFNULL((SELECT SUM(d) FROM sl), 0) / 1e6, 1) AS espera_ms,
       ROUND(IFNULL((SELECT MAX(d) FROM sl WHERE state = 'D'), 0) / 1e6, 1) AS max_d_ms;
