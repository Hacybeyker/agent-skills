-- Pares de llamadas al mismo endpoint en vuelo a la vez: la señal más clara de una carga duplicada.
SELECT a.name AS llamada, COUNT(*) AS pares_solapados,
       ROUND(MIN(b.ts - a.ts) / 1e6, 0) AS separacion_min_ms
FROM slice a
JOIN slice b ON a.name = b.name AND b.ts > a.ts AND b.ts < a.ts + a.dur
WHERE a.name GLOB 'HTTP *'
GROUP BY a.name ORDER BY pares_solapados DESC;
