# Example SIEM Queries

This document provides example SQL queries for the Apache BigData SIEM environment. These queries can be executed in **Apache Zeppelin** (using the `%jdbc` or `%spark.sql` interpreters) or in **Apache Superset** SQL Lab.

The primary table for analysis is `siem.logs_parsed`.

## 1. Basic Visibility

### Peek at Data
```sql
SELECT * FROM siem.logs_parsed LIMIT 10;
```

### Count Logs by Topic
```sql
SELECT source_topic, count(*) as event_count 
FROM siem.logs_parsed 
GROUP BY source_topic 
ORDER BY event_count DESC;
```

## 2. Web Security (web-logs)

### Top 10 Attacking IPs (by 404/403 errors)
Find IPs that are scanning for non-existent pages or hitting forbidden areas.
```sql
SELECT client_ip, count(*) as error_count 
FROM siem.logs_parsed 
WHERE status_code IN ('404', '403') 
GROUP BY client_ip 
ORDER BY error_count DESC 
LIMIT 10;
```

### Detect Potential Brute Force or Scraping
High volume of POST requests from a single IP.
```sql
SELECT client_ip, count(*) as post_count 
FROM siem.logs_parsed 
WHERE http_method = 'POST' 
GROUP BY client_ip 
HAVING post_count > 100 
ORDER BY post_count DESC;
```

## 3. System Auditing (syslogs)

### Monitor Failed Login Attempts
```sql
SELECT syslog_host, count(*) as failure_count 
FROM siem.logs_parsed 
WHERE raw_log LIKE '%Failed password%' OR raw_log LIKE '%authentication failure%'
GROUP BY syslog_host 
ORDER BY failure_count DESC;
```

### Activity by System Program
```sql
SELECT syslog_program, count(*) as activity_count 
FROM siem.logs_parsed 
WHERE syslog_program IS NOT NULL 
GROUP BY syslog_program 
ORDER BY activity_count DESC;
```

## 4. Application Monitoring (app-logs)

### Error Events per Service
```sql
SELECT app_service, app_event, count(*) as event_count 
FROM siem.logs_parsed 
WHERE app_event = 'error' OR app_event = 'critical'
GROUP BY app_service, app_event 
ORDER BY event_count DESC;
```

## 5. Time-Series Analysis

### Hourly Event Trend (Last 24 Hours)
```sql
SELECT window(ingest_ts, '1 hour') as time_window, count(*) as event_count 
FROM siem.logs_parsed 
GROUP BY time_window 
ORDER BY time_window ASC;
```

### Daily Traffic Volume
```sql
SELECT ingest_date, count(*) as daily_total 
FROM siem.logs_parsed 
GROUP BY ingest_date 
ORDER BY ingest_date DESC;
```
