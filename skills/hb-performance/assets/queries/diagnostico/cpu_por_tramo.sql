-- CPU de la app en tramos de {{TRAMO_MS}} ms: hilo principal, RenderThread y el resto (con el grupo que más gasta)
-- grupos: base
WITH app AS (SELECT upid, pid, MAX(IFNULL(start_ts, 0), (SELECT start_ts FROM trace_bounds)) AS t0
             FROM process WHERE name = '{{PAQUETE}}' ORDER BY IFNULL(start_ts, 0) DESC LIMIT 1),
hilo AS (SELECT t.utid FROM thread t JOIN app ON t.upid = app.upid AND t.tid = app.pid),
main AS (SELECT tt.id AS track FROM thread_track tt JOIN hilo ON tt.utid = hilo.utid),
st AS (SELECT CAST((ts.ts - app.t0) / ({{TRAMO_MS}} * 1e6) AS INT) * {{TRAMO_MS}} AS desde_ms, CASE WHEN t.tid = app.pid THEN 'main' WHEN t.name = 'RenderThread' THEN 'RenderThread' ELSE RTRIM(IFNULL(t.name, '?'), '0123456789-_#: ') END AS grupo, ts.dur
       FROM thread_state ts JOIN thread t ON t.utid = ts.utid JOIN app ON t.upid = app.upid
       WHERE ts.state = 'Running' AND ts.ts >= app.t0),
g AS (SELECT desde_ms, grupo, SUM(dur) AS d FROM st GROUP BY 1, 2),
otro AS (SELECT desde_ms, grupo, d, ROW_NUMBER() OVER (PARTITION BY desde_ms ORDER BY d DESC) AS n
         FROM g WHERE grupo NOT IN ('main', 'RenderThread'))
SELECT g.desde_ms, ROUND(SUM(CASE WHEN g.grupo = 'main' THEN g.d END) / 1e6) AS main_ms,
       ROUND(SUM(CASE WHEN g.grupo = 'RenderThread' THEN g.d END) / 1e6) AS render_ms,
       ROUND(SUM(CASE WHEN g.grupo NOT IN ('main', 'RenderThread') THEN g.d END) / 1e6) AS resto_ms,
       (SELECT o.grupo || ' ' || CAST(ROUND(o.d / 1e6) AS INT) FROM otro o WHERE o.desde_ms = g.desde_ms AND o.n = 1)
         AS resto_top_ms
FROM g GROUP BY g.desde_ms ORDER BY g.desde_ms LIMIT 20;
