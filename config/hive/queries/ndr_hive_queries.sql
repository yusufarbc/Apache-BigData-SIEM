-- ═══════════════════════════════════════════════════════════════
-- NDR SIEM — Hive SQL Referans Sorguları
-- Hedef: siem.network_anomalies & siem.network_flows tabloları
-- ═══════════════════════════════════════════════════════════════

-- ── 1. Son 1 saatteki tüm anomaliler ────────────────────────────
SELECT
    ingest_ts,
    src_ip,
    dest_ip,
    dest_port,
    proto,
    ROUND(duration, 2)    AS duration_sec,
    orig_bytes,
    resp_bytes,
    ROUND(anomaly_score, 3) AS score,
    cluster_id,
    conn_state
FROM siem.network_anomalies
WHERE ingest_ts >= CURRENT_TIMESTAMP - INTERVAL 1 HOURS
ORDER BY anomaly_score DESC
LIMIT 100;


-- ── 2. En fazla anomali üreten kaynak IP'ler ─────────────────────
SELECT
    src_ip,
    COUNT(*)                    AS anomaly_count,
    ROUND(AVG(anomaly_score),3) AS avg_score,
    ROUND(MAX(anomaly_score),3) AS max_score,
    COUNT(DISTINCT dest_port)   AS unique_dest_ports
FROM siem.network_anomalies
GROUP BY src_ip
ORDER BY anomaly_count DESC
LIMIT 20;


-- ── 3. Zaman çizelgesinde anomali yoğunluğu (dakikaya göre) ──────
SELECT
    DATE_FORMAT(ingest_ts, 'yyyy-MM-dd HH:mm') AS minute_bucket,
    COUNT(*)                                    AS anomaly_count,
    ROUND(AVG(anomaly_score), 3)                AS avg_score,
    ROUND(MAX(anomaly_score), 3)                AS max_score
FROM siem.network_anomalies
WHERE ingest_ts >= CURRENT_TIMESTAMP - INTERVAL 6 HOURS
GROUP BY DATE_FORMAT(ingest_ts, 'yyyy-MM-dd HH:mm')
ORDER BY minute_bucket;


-- ── 4. Port tarama tespiti (çok fazla farklı port → tek kaynak) ──
SELECT
    src_ip,
    COUNT(DISTINCT dest_port) AS unique_ports_hit,
    COUNT(*)                  AS total_flows,
    ROUND(AVG(duration), 4)   AS avg_duration,
    ROUND(AVG(orig_bytes), 0) AS avg_orig_bytes
FROM siem.network_anomalies
WHERE conn_state IN ('REJ', 'S0', 'RSTOS0')
GROUP BY src_ip
HAVING COUNT(DISTINCT dest_port) > 20
ORDER BY unique_ports_hit DESC;


-- ── 5. Veri sızdırma şüphesi (devasa orig_bytes) ─────────────────
SELECT
    src_ip,
    dest_ip,
    dest_port,
    proto,
    ROUND(duration, 0)          AS duration_sec,
    orig_bytes,
    resp_bytes,
    ROUND(anomaly_score, 3)     AS score
FROM siem.network_anomalies
WHERE orig_bytes > 1000000      -- 1 MB üzeri
ORDER BY orig_bytes DESC
LIMIT 50;


-- ── 6. Protokole göre anomali dağılımı ───────────────────────────
SELECT
    proto,
    COUNT(*)                    AS anomaly_count,
    ROUND(AVG(anomaly_score),3) AS avg_score
FROM siem.network_anomalies
GROUP BY proto
ORDER BY anomaly_count DESC;


-- ── 7. K-Means küme istatistikleri ───────────────────────────────
SELECT
    cluster_id,
    COUNT(*)                    AS anomaly_count,
    ROUND(AVG(anomaly_score),3) AS avg_score,
    ROUND(MIN(anomaly_score),3) AS min_score,
    ROUND(MAX(anomaly_score),3) AS max_score
FROM siem.network_anomalies
GROUP BY cluster_id
ORDER BY avg_score DESC;


-- ── 8. Normal vs. anomali trafik oranı (son 1 saat) ─────────────
SELECT
    is_anomaly,
    COUNT(*)                     AS flow_count,
    ROUND(COUNT(*) * 100.0 /
          SUM(COUNT(*)) OVER (), 2) AS pct
FROM siem.network_flows
WHERE ingest_ts >= CURRENT_TIMESTAMP - INTERVAL 1 HOURS
GROUP BY is_anomaly;


-- ── 9. Hedef porta göre anomali sayısı ───────────────────────────
SELECT
    dest_port,
    proto,
    COUNT(*)                    AS anomaly_count,
    ROUND(AVG(anomaly_score),3) AS avg_score
FROM siem.network_anomalies
GROUP BY dest_port, proto
ORDER BY anomaly_count DESC
LIMIT 30;


-- ── 10. Günlük anomali özeti ──────────────────────────────────────
SELECT
    ingest_date,
    COUNT(*)                    AS total_anomalies,
    COUNT(DISTINCT src_ip)      AS unique_src_ips,
    COUNT(DISTINCT dest_ip)     AS unique_dest_ips,
    ROUND(AVG(anomaly_score),3) AS avg_score,
    ROUND(MAX(anomaly_score),3) AS max_score
FROM siem.network_anomalies
GROUP BY ingest_date
ORDER BY ingest_date DESC;
