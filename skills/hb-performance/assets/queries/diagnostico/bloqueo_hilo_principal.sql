-- Por qué espera el hilo principal dentro de los 3 doFrame más largos: en D, la función del kernel que lo bloquea; en S, el hilo que lo despierta (esperas de más de 1 ms)
-- grupos: completa
-- requiere: ftrace:sched/sched_switch ftrace:sched/sched_waking ftrace:sched/sched_blocked_reason atrace:view
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
fr AS (SELECT s.ts, s.dur FROM slice s JOIN main ON s.track_id = main.track
       WHERE s.depth = 0 AND s.name GLOB 'Choreographer#doFrame*' ORDER BY s.dur DESC LIMIT 3),
sl AS (SELECT fr.ts AS frame_ts, fr.dur AS frame_dur, ts.id, ts.ts, ts.dur, ts.state, ts.io_wait, ts.blocked_function
       FROM fr JOIN thread_state ts ON ts.utid IN (SELECT utid FROM hilo) AND ts.ts >= fr.ts AND ts.ts < fr.ts + fr.dur
       WHERE ts.state IN ('S', 'D') AND ts.dur > 1000000),
razones AS (SELECT COUNT(*) AS n FROM thread_state WHERE blocked_function IS NOT NULL OR io_wait IS NOT NULL)
SELECT ROUND((sl.frame_ts - app.t0) / 1e6) AS frame_t_ms, ROUND(sl.frame_dur / 1e6, 1) AS frame_ms, sl.state AS estado,
       ROUND(sl.dur / 1e6, 1) AS ms,
       CASE WHEN sl.state != 'D' THEN '—'
            WHEN sl.blocked_function IS NOT NULL THEN SUBSTR(sl.blocked_function, 1, 40) || CASE WHEN sl.io_wait = 1 THEN ' (E/S)' ELSE '' END
            WHEN sl.io_wait IS NOT NULL THEN CASE WHEN sl.io_wait = 1 THEN 'E/S, sin símbolo del kernel' ELSE 'no es E/S, sin símbolo del kernel' END
            WHEN (SELECT n FROM razones) = 0 THEN 'no disponible en este dispositivo'
            ELSE 'sin dato en esta espera' END AS bloqueado_en,
       IFNULL((SELECT SUBSTR(IFNULL(w.name, '?'), 1, 30) || ' · ' || SUBSTR(IFNULL(p.name, '?'), 1, 30)
               FROM thread_state nx JOIN thread w ON w.utid = nx.waker_utid LEFT JOIN process p ON p.upid = w.upid
               WHERE nx.utid IN (SELECT utid FROM hilo) AND nx.ts = sl.ts + sl.dur AND nx.waker_utid IS NOT NULL LIMIT 1),
              'sin dato') AS lo_desperto,
       (SELECT SUBSTR(s.name, 1, 45) FROM slice s JOIN main ON s.track_id = main.track
        WHERE s.ts <= sl.ts AND s.ts + s.dur >= sl.ts + sl.dur ORDER BY s.depth DESC LIMIT 1) AS dentro_de
FROM sl, app
ORDER BY sl.dur DESC LIMIT 12;
