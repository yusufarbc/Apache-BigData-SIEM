"""
Apache-BigData-SIEM ETL Process
-------------------------------
This module consumes raw logs from Kafka, applies schema-on-read parsing 
(Regex and JSON), and sinks the parsed structured data into an Apache Hive table 
stored in Parquet format.

It's designed to run on Apache Spark Streaming.
"""

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col,
    current_timestamp,
    from_json,
    regexp_extract,
    to_date,
    when,
)
from pyspark.sql.types import StringType, StructField, StructType

# Detection Rules Engine
from detection_rules import initialize_alerts_table, evaluate_rules

# Configuration Constants
KAFKA_BOOTSTRAP = "kafka-broker:9092"
KAFKA_TOPICS = "web-logs,syslogs,app-logs"
CHECKPOINT_PATH = "hdfs://namenode:8020/tmp/checkpoints/siem_logs_parsed"
HIVE_TABLE_LOCATION = "hdfs://namenode:8020/user/hive/warehouse/siem.db/logs_parsed"


def get_spark_session() -> SparkSession:
    """
    Initializes and returns the SparkSession with Hive support.
    """
    spark = (
        SparkSession.builder.appName("siem-kafka-to-hive-parquet")
        .config("spark.sql.catalogImplementation", "hive")
        .config("spark.hadoop.fs.defaultFS", "hdfs://namenode:8020")
        .config("spark.hadoop.hive.metastore.uris", "thrift://hive-metastore:9083")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def initialize_hive_table(spark: SparkSession) -> None:
    """
    Ensures the target Hive database and table exist.
    """
    spark.sql("CREATE DATABASE IF NOT EXISTS siem")
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS siem.logs_parsed (
          raw_log STRING,
          source_topic STRING,
          client_ip STRING,
          http_method STRING,
          request_path STRING,
          status_code STRING,
          bytes_sent STRING,
          syslog_host STRING,
          syslog_program STRING,
          app_event STRING,
          app_service STRING,
          ingest_ts TIMESTAMP,
          ingest_date DATE
        )
        USING PARQUET
        PARTITIONED BY (ingest_date)
        LOCATION '{HIVE_TABLE_LOCATION}'
        """
    )


def extract_attributes(logs_df: DataFrame) -> DataFrame:
    """
    Applies regex and JSON parsing to extract structured columns from the raw log stream.

    Log formats produced by flog:
      - web   (apache_common):   IP - - [timestamp] "METHOD path HTTP/1.x" STATUS BYTES
      - syslog (rfc5424):        MONTH DAY HH:MM:SS HOST PROG[PID]: MSG
      - json  (apache_combined): flog outputs apache_combined as JSON with field names:
                                  host, user-identifier, authuser, datetime,
                                  request, status, bytes, referer, agent

    :param logs_df: The raw streaming DataFrame from Kafka
    :return: A parsed DataFrame with expanded columns
    """
    # JSON schema matching flog's apache_combined JSON output
    json_schema = StructType(
        [
            StructField("host", StringType(), True),
            StructField("user-identifier", StringType(), True),
            StructField("authuser", StringType(), True),
            StructField("datetime", StringType(), True),
            StructField("request", StringType(), True),
            StructField("status", StringType(), True),
            StructField("bytes", StringType(), True),
            StructField("referer", StringType(), True),
            StructField("agent", StringType(), True),
        ]
    )

    json_parsed = from_json(col("raw_log"), json_schema)

    parsed_df = (
        logs_df
        # ── Web log fields (apache_common: IP - - [ts] "METHOD /path HTTP/x" STATUS BYTES) ──
        .withColumn("client_ip",    regexp_extract("raw_log", r'^(\S+)', 1))
        .withColumn("http_method",  regexp_extract("raw_log", r'"(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s', 1))
        .withColumn("request_path", regexp_extract("raw_log", r'"(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+(\S+)', 1))
        # status code sits right after the closing-quote + space
        .withColumn("status_code",  regexp_extract("raw_log", r'"\s+(\d{3})\s+', 1))
        # bytes can be a number or '-' (empty body) — capture only digits
        .withColumn("bytes_sent",   regexp_extract("raw_log", r'"\s+\d{3}\s+(\d+)', 1))

        # ── Syslog fields (rfc5424: "MMM D HH:MM:SS host prog[pid]: msg") ──
        .withColumn("syslog_host",    regexp_extract("raw_log", r'^\w{3}\s+\d+\s+\d+:\d+:\d+\s+(\S+)', 1))
        .withColumn("syslog_program", regexp_extract("raw_log", r'\s([A-Za-z0-9_.\-]+)(?:\[\d+\])?:', 1))

        # ── App-log fields (flog apache_combined JSON) ──
        .withColumn("app_event",   json_parsed.getField("status"))
        .withColumn("app_service", json_parsed.getField("request"))

        # ── Ingest timestamps ──
        .withColumn(
            "ingest_ts",
            when(col("kafka_ts").isNotNull(), col("kafka_ts")).otherwise(current_timestamp()),
        )
        .withColumn("ingest_date", to_date(col("ingest_ts")))
    )

    return parsed_df


def append_to_hive(batch_df: DataFrame, batch_id: int) -> None:
    """
    ForeachBatch function to write the micro-batch into the Hive table,
    then evaluate detection rules and write any alerts.
    
    :param batch_df: The DataFrame for the current micro-batch
    :param batch_id: The unique ID of the micro-batch
    """
    if batch_df.rdd.isEmpty():
        return

    output_cols = [
        "raw_log",
        "source_topic",
        "client_ip",
        "http_method",
        "request_path",
        "status_code",
        "bytes_sent",
        "syslog_host",
        "syslog_program",
        "app_event",
        "app_service",
        "ingest_ts",
        "ingest_date",
    ]

    # 1. Write parsed logs to Hive
    (
        batch_df.select(*output_cols)
        .write.mode("append")
        .format("parquet")
        .insertInto("siem.logs_parsed", overwrite=False)
    )

    # 2. Evaluate detection rules and generate alerts
    spark = batch_df.sparkSession
    batch_df.createOrReplaceTempView("batch_logs")
    alert_count = evaluate_rules(spark, batch_df, batch_id)
    if alert_count > 0:
        print(f"  Batch {batch_id}: Generated {alert_count} alert(s)")


def main() -> None:
    """
    Main entry point for the Spark Streaming job.
    """
    spark = get_spark_session()
    initialize_hive_table(spark)
    initialize_alerts_table(spark)

    # 1. Read raw stream from Kafka
    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPICS)
        .option("startingOffsets", "latest")
        .load()
    )

    # 2. Select base columns
    logs = raw_stream.select(
        col("topic").alias("source_topic"),
        col("timestamp").alias("kafka_ts"),
        col("value").cast("string").alias("raw_log"),
    )

    # 3. Apply parsing logic
    parsed_logs = extract_attributes(logs)

    # 4. Write stream to Hive via foreachBatch
    query = (
        parsed_logs.writeStream.outputMode("append")
        .option("checkpointLocation", CHECKPOINT_PATH)
        .foreachBatch(append_to_hive)
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    main()
