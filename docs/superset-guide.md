# Apache Superset Guide — BigData SIEM

This guide covers how to connect, query, and build dashboards in Apache Superset for the Apache-BigData-SIEM platform.

## Access

| URL | Credentials |
|-----|-------------|
| `http://localhost:8088` | `admin` / `admin` |

---

## 1. Database Connection Setup

Superset connects to the Spark Thrift Server (HiveServer2-compatible) via SQLAlchemy.

### Steps

1. Go to **Settings → Database Connections → + Database**
2. Select **Apache Hive** (or use the generic SQLAlchemy form)
3. Enter the connection URI:

```
hive://spark-master:10000/siem
```

> **Note:** Port `10000` is the Spark Thrift Server endpoint exposed by `spark-master` (not HiveServer2). It provides HiveServer2-compatible JDBC/ODBC access.

4. Click **Test Connection** → **Save**

---

## 2. SQL Lab — Query Examples

Navigate to **SQL Lab → SQL Editor**, select the `siem` database.

### 2.1 Basic Visibility

```sql
-- Preview latest 20 logs
SELECT * FROM siem.logs_parsed
ORDER BY ingest_ts DESC
LIMIT 20;
```

```sql
-- Event count by source
SELECT source_topic, COUNT(*) AS event_count
FROM siem.logs_parsed
GROUP BY source_topic
ORDER BY event_count DESC;
```

### 2.2 Web Security (web-logs)

```sql
-- Top attacking IPs (4xx errors)
SELECT
  client_ip,
  COUNT(*) AS error_count
FROM siem.logs_parsed
WHERE source_topic = 'web-logs'
  AND status_code IN ('400', '401', '403', '404', '429')
GROUP BY client_ip
ORDER BY error_count DESC
LIMIT 25;
```

```sql
-- HTTP method distribution
SELECT
  http_method,
  COUNT(*) AS request_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM siem.logs_parsed
WHERE source_topic = 'web-logs'
GROUP BY http_method
ORDER BY request_count DESC;
```

```sql
-- Suspected brute-force: high-volume POST from single IP
SELECT
  client_ip,
  COUNT(*) AS post_count
FROM siem.logs_parsed
WHERE source_topic = 'web-logs'
  AND http_method = 'POST'
  AND ingest_date >= CURRENT_DATE - INTERVAL 1 DAYS
GROUP BY client_ip
HAVING COUNT(*) > 200
ORDER BY post_count DESC;
```

```sql
-- Top requested paths (useful for discovering enumeration)
SELECT
  request_path,
  COUNT(*) AS hit_count
FROM siem.logs_parsed
WHERE source_topic = 'web-logs'
GROUP BY request_path
ORDER BY hit_count DESC
LIMIT 20;
```

### 2.3 System Auditing (syslogs)

```sql
-- Failed authentication events per host
SELECT
  syslog_host,
  COUNT(*) AS failure_count
FROM siem.logs_parsed
WHERE source_topic = 'syslogs'
  AND (raw_log LIKE '%Failed password%'
    OR raw_log LIKE '%authentication failure%'
    OR raw_log LIKE '%Invalid user%')
GROUP BY syslog_host
ORDER BY failure_count DESC;
```

```sql
-- Active programs generating most syslog entries
SELECT
  syslog_program,
  COUNT(*) AS activity_count
FROM siem.logs_parsed
WHERE source_topic = 'syslogs'
  AND syslog_program IS NOT NULL
  AND syslog_program != ''
GROUP BY syslog_program
ORDER BY activity_count DESC
LIMIT 15;
```

### 2.4 Application Monitoring (app-logs)

```sql
-- HTTP status code distribution from app-logs JSON
SELECT
  app_event AS status_code,
  COUNT(*) AS count
FROM siem.logs_parsed
WHERE source_topic = 'app-logs'
  AND app_event IS NOT NULL
GROUP BY app_event
ORDER BY count DESC;
```

```sql
-- Top requested endpoints in app-logs
SELECT
  app_service AS endpoint,
  COUNT(*) AS hit_count
FROM siem.logs_parsed
WHERE source_topic = 'app-logs'
  AND app_service IS NOT NULL
GROUP BY app_service
ORDER BY hit_count DESC
LIMIT 20;
```

### 2.5 Time-Series Analysis

```sql
-- Hourly event volume (last 24h)
SELECT
  DATE_FORMAT(ingest_ts, 'yyyy-MM-dd HH:00') AS hour_bucket,
  source_topic,
  COUNT(*) AS event_count
FROM siem.logs_parsed
WHERE ingest_date >= CURRENT_DATE - INTERVAL 1 DAYS
GROUP BY DATE_FORMAT(ingest_ts, 'yyyy-MM-dd HH:00'), source_topic
ORDER BY hour_bucket ASC;
```

```sql
-- Daily volume trend (last 7 days)
SELECT
  ingest_date,
  COUNT(*) AS daily_total
FROM siem.logs_parsed
WHERE ingest_date >= CURRENT_DATE - INTERVAL 7 DAYS
GROUP BY ingest_date
ORDER BY ingest_date DESC;
```

---

## 3. Dashboard Building

### Recommended SOC Dashboard Panels

| Panel | Chart Type | Query Basis |
|-------|-----------|-------------|
| **Total Events (24h)** | Big Number | Count with `ingest_date >= CURRENT_DATE - 1` |
| **Events per Topic** | Pie Chart | `GROUP BY source_topic` |
| **Top Attacking IPs** | Bar Chart | 4xx errors `GROUP BY client_ip` |
| **Hourly Event Trend** | Line Chart | `GROUP BY hour_bucket, source_topic` |
| **HTTP Method Distribution** | Donut Chart | `GROUP BY http_method` |
| **Auth Failure by Host** | Bar Chart | syslog failed auth `GROUP BY syslog_host` |
| **Status Code Heatmap** | Heatmap | `GROUP BY status_code, ingest_date` |

### Creating a Chart

1. **SQL Lab** → Run your query → **Explore** button
2. Choose a chart type (e.g., **Bar Chart**, **Line Chart**)
3. Set **Metrics** and **Dimensions** from your query columns
4. **Save** and add to a dashboard

### Creating a Dashboard

1. **Dashboards → + Dashboard**
2. Click **Edit Dashboard** → drag saved charts onto the canvas
3. Set **Auto-refresh** (e.g., every 10 minutes) for live SOC monitoring
4. Save and share

---

## 4. Alerts & Reports (Optional)

Superset supports scheduled email/Slack alerts:

1. **Settings → Alerts & Reports**
2. Define a **SQL condition** (e.g., brute-force threshold exceeded)
3. Configure **schedule** and **notification channel**

---

## 5. Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused on port 10000 | Ensure `spark-master` is healthy and the Thrift Server started: `docker logs spark-master \| grep ThriftServer` |
| `Table not found: siem.logs_parsed` | Run the ETL job first: `make run-job` |
| Query timeout | Reduce date range or add `LIMIT` clause |
| Empty results | Verify Kafka producers are running: `docker compose ps flog-web flog-syslog flog-app` |
