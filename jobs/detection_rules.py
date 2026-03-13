"""
SIEM Detection Rules Engine
----------------------------
Defines security detection rules that run on each Spark Streaming
micro-batch. When a rule matches, alerts are written to the
siem.alerts Hive table.

Usage:
    from detection_rules import DETECTION_RULES, initialize_alerts_table, evaluate_rules
"""

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import lit, current_timestamp, to_date

# ══════════════════════════════════════════════════════════════
# Alerts Table Location
# ══════════════════════════════════════════════════════════════

ALERTS_TABLE_LOCATION = "hdfs://namenode:8020/user/hive/warehouse/siem.db/alerts"

# ══════════════════════════════════════════════════════════════
# Detection Rules (Sigma-style)
# ══════════════════════════════════════════════════════════════
#
# Each rule is a dict with:
#   - id:          Unique rule identifier
#   - name:        Human-readable name
#   - description: What this rule detects
#   - severity:    CRITICAL / HIGH / MEDIUM / LOW / INFO
#   - query:       SQL query against "batch_logs" temp view
#                  Must return: matched_field, matched_value, hit_count
#
# To add a new rule, simply append a new dict to this list.
# ══════════════════════════════════════════════════════════════

DETECTION_RULES = [
    {
        "id": "SIEM-001",
        "name": "Brute Force Detection (HTTP)",
        "description": "Single IP generating 50+ HTTP 401/403 errors in a micro-batch",
        "severity": "HIGH",
        "query": """
            SELECT
                'client_ip' AS matched_field,
                client_ip AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'web-logs'
              AND status_code IN ('401', '403')
              AND client_ip IS NOT NULL
              AND client_ip != ''
            GROUP BY client_ip
            HAVING COUNT(*) > 50
        """,
    },
    {
        "id": "SIEM-002",
        "name": "Path Traversal Attempt",
        "description": "URL containing ../ patterns indicating directory traversal attack",
        "severity": "CRITICAL",
        "query": """
            SELECT
                'request_path' AS matched_field,
                request_path AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'web-logs'
              AND request_path LIKE '%../%'
            GROUP BY request_path
        """,
    },
    {
        "id": "SIEM-003",
        "name": "Unusual High Volume from Single IP",
        "description": "Single IP generating 1000+ requests in a micro-batch (potential DDoS)",
        "severity": "MEDIUM",
        "query": """
            SELECT
                'client_ip' AS matched_field,
                client_ip AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'web-logs'
              AND client_ip IS NOT NULL
              AND client_ip != ''
            GROUP BY client_ip
            HAVING COUNT(*) > 1000
        """,
    },
    {
        "id": "SIEM-004",
        "name": "SSH Brute Force (Syslog)",
        "description": "Repeated 'Failed password' patterns in syslog indicating SSH brute force",
        "severity": "HIGH",
        "query": """
            SELECT
                'syslog_host' AS matched_field,
                syslog_host AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'syslogs'
              AND raw_log LIKE '%Failed password%'
              AND syslog_host IS NOT NULL
            GROUP BY syslog_host
            HAVING COUNT(*) > 10
        """,
    },
    {
        "id": "SIEM-005",
        "name": "SQL Injection Attempt",
        "description": "URL containing common SQL injection patterns",
        "severity": "CRITICAL",
        "query": """
            SELECT
                'request_path' AS matched_field,
                request_path AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'web-logs'
              AND (
                  request_path LIKE '%UNION%SELECT%'
                  OR request_path LIKE '%OR%1=1%'
                  OR request_path LIKE "%'%OR%'%"
                  OR request_path LIKE '%DROP%TABLE%'
              )
            GROUP BY request_path
        """,
    },
    {
        "id": "SIEM-006",
        "name": "Application Critical Error Spike",
        "description": "Multiple critical/error events from an application service",
        "severity": "HIGH",
        "query": """
            SELECT
                'app_service' AS matched_field,
                app_service AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'app-logs'
              AND app_event IN ('error', 'critical')
              AND app_service IS NOT NULL
            GROUP BY app_service
            HAVING COUNT(*) > 5
        """,
    },
    {
        "id": "SIEM-007",
        "name": "HTTP 5xx Server Error Spike",
        "description": "High volume of server errors indicating potential service degradation",
        "severity": "MEDIUM",
        "query": """
            SELECT
                'status_code' AS matched_field,
                status_code AS matched_value,
                COUNT(*) AS hit_count
            FROM batch_logs
            WHERE source_topic = 'web-logs'
              AND status_code LIKE '5%'
            GROUP BY status_code
            HAVING COUNT(*) > 20
        """,
    },
]


def initialize_alerts_table(spark: SparkSession) -> None:
    """
    Ensures the siem.alerts Hive table exists.
    Called once during ETL startup.
    """
    spark.sql("CREATE DATABASE IF NOT EXISTS siem")
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS siem.alerts (
            rule_id STRING,
            rule_name STRING,
            severity STRING,
            description STRING,
            matched_field STRING,
            matched_value STRING,
            hit_count BIGINT,
            detected_at TIMESTAMP,
            detect_date DATE
        )
        USING PARQUET
        PARTITIONED BY (detect_date)
        LOCATION '{ALERTS_TABLE_LOCATION}'
        """
    )


def evaluate_rules(spark: SparkSession, batch_df: DataFrame, batch_id: int) -> int:
    """
    Evaluate all detection rules against a micro-batch DataFrame.

    The batch_df must already be registered as a temp view named 'batch_logs'.
    Returns the total number of alerts generated.

    :param spark: Active SparkSession
    :param batch_df: The current micro-batch DataFrame
    :param batch_id: The batch ID (for logging)
    :return: Number of alerts generated
    """
    total_alerts = 0

    for rule in DETECTION_RULES:
        try:
            alerts_df = spark.sql(rule["query"])

            if alerts_df.rdd.isEmpty():
                continue

            # Enrich alerts with rule metadata
            enriched = (
                alerts_df
                .withColumn("rule_id", lit(rule["id"]))
                .withColumn("rule_name", lit(rule["name"]))
                .withColumn("severity", lit(rule["severity"]))
                .withColumn("description", lit(rule["description"]))
                .withColumn("detected_at", current_timestamp())
                .withColumn("detect_date", to_date(current_timestamp()))
            )

            # Select columns in table order
            output_cols = [
                "rule_id", "rule_name", "severity", "description",
                "matched_field", "matched_value", "hit_count",
                "detected_at", "detect_date",
            ]

            enriched.select(*output_cols).write.mode("append").insertInto(
                "siem.alerts", overwrite=False
            )

            alert_count = enriched.count()
            total_alerts += alert_count
            print(f"  [ALERT] Rule {rule['id']} ({rule['name']}): {alert_count} alert(s) — {rule['severity']}")

        except Exception as e:
            print(f"  [ERROR] Rule {rule['id']} failed: {e}")

    return total_alerts
