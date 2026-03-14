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

## 2. PostgreSQL Connection (Metadata & Auditing)

While the log data resides in Hive, the metadata and some state information are stored in PostgreSQL. You can connect to it for auditing or monitoring the platform's health.

### Steps

1. Go to **Settings → Database Connections → + Database**
2. Select **PostgreSQL**
3. Enter the connection URI:

```
postgresql://hive_user:hive_password@postgres:5432/metastore_db
```

4. Click **Test Connection** → **Save**

---

## 3. SQL Lab — Query Examples

Navigate to **SQL Lab → SQL Editor**, select the `siem` database.

### 3.1 Basic Visibility

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

### 3.2 Web Security (web-logs)

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

### 3.3 System Auditing (syslogs)

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

### 3.4 Application Monitoring (app-logs)

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

### 3.5 Time-Series Analysis

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

## 4. Dashboard Building

### 4.1 Creating Your First Dashboard

1. **New Dashboard**: Navigate to **Dashboards → + Dashboard**.
2. **Chart Integration**:
   - On the right sidebar, click **Charts**.
   - Drag and drop your saved charts (e.g., "Event Volume Trend") onto the canvas.
3. **Layout Customization**:
   - Use **Rows** and **Columns** to organize panels.
   - Use **Markdown** components to add headers like "Web Security Overview" or "System Health".
4. **Auto-Refresh**: Click the **...** (three dots) in the top-right corner → **Set auto-refresh interval** → Choose **10 seconds** or **1 minute** for real-time monitoring.

### 4.2 Key SIEM Visualization Patterns

| Security Goal | Recommended Chart | Config Detail |
|---------------|-------------------|---------------|
| **Brute Force Detection** | Bar Chart | `count` on Y-axis, `client_ip` on X-axis, filter by `status_code = 401`. |
| **System Health** | Indicator (Big Number) | `count(*)` of events in the last 5 minutes. |
| **Anomaly Detection** | Line Chart | Hourly event volume with a 7-day comparison (Advanced Analytics). |
| **DDoS Awareness** | Area Chart | Events per second (EPS) trend. |

---

## 5. Alerts & Reports (SIEM Rules)

Superset can act as a rudimentary alerting engine by running SQL queries on a schedule.

### 5.1 Prerequisites
Ensure the Superset Celery worker and beat are running (included in `docker-compose.yml`).

### 5.2 Setting up a SIEM Alert (e.g., High Error Threshold)

1. **Create Alert**: Go to **Settings → Alerts & Reports → + Alert**.
2. **Setup**:
   - **Name**: `CRITICAL: Web High Error Rate`
   - **Database**: `siem`
   - **SQL Query**: 
     ```sql
     SELECT COUNT(*) as err_count 
     FROM siem.logs_parsed 
     WHERE status_code >= '500' 
       AND ingest_ts > DATE_SUB(NOW(), INTERVAL 5 MINUTE)
     ```
   - **Alert Condition**: Trigger if `err_count > 50`.
3. **Delivery**: Choose **Slack** or **Email** and provide the destination.
4. **Schedule**: Set to run every **5 minutes**.

---

## 6. SOC Analyst Workflow (Example)

How to use these tools in a real incident response:

1. **Detection**: An alert triggers in Slack: `CRITICAL: Web High Error Rate`.
2. **Triage**: The analyst opens the **SIEM Main Dashboard** in Superset.
3. **Investigation**:
   - They see a spike in 4xx errors from a specific IP.
   - They jump to **SQL Lab** and run:
     ```sql
     SELECT request_path, user_agent 
     FROM siem.logs_parsed 
     WHERE client_ip = 'XYZ' AND status_code = '404'
     ```
   - They identify a directory traversal attack pattern (`../../etc/passwd`).
4. **Resolution**: The IP is blocked at the firewall, and the alert is cleared.

---

## 7. Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused on port 10000 | Ensure `spark-master` is healthy and the Thrift Server started: `docker logs spark-master \| grep ThriftServer` |
| `Table not found: siem.logs_parsed` | Run the ETL job first: The `spark-etl` service should handle this automatically. |
| Query timeout | Reduce date range or add `LIMIT` clause |
| Empty results | Verify Kafka producers are running: `docker compose ps` |
