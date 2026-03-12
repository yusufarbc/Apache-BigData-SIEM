from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    from_json,
    regexp_extract,
    to_date,
    when,
)
from pyspark.sql.types import StringType, StructField, StructType

KAFKA_BOOTSTRAP = "kafka-broker:9092"
KAFKA_TOPICS = "web-logs,syslogs,app-logs"
CHECKPOINT_PATH = "hdfs://namenode:8020/tmp/checkpoints/siem_logs_parsed"
HIVE_TABLE_LOCATION = "hdfs://namenode:8020/user/hive/warehouse/siem.db/logs_parsed"

spark = (
    SparkSession.builder.appName("siem-kafka-to-hive-parquet")
    .config("spark.sql.catalogImplementation", "hive")
    .config("spark.hadoop.fs.defaultFS", "hdfs://namenode:8020")
    .config("spark.hadoop.hive.metastore.uris", "thrift://hive-metastore:9083")
    .enableHiveSupport()
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

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

json_schema = StructType(
    [
        StructField("event", StringType(), True),
        StructField("service", StringType(), True),
        StructField("message", StringType(), True),
    ]
)

raw_stream = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
    .option("subscribe", KAFKA_TOPICS)
    .option("startingOffsets", "latest")
    .load()
)

logs = raw_stream.select(
    col("topic").alias("source_topic"),
    col("timestamp").alias("kafka_ts"),
    col("value").cast("string").alias("raw_log"),
)

json_parsed = from_json(col("raw_log"), json_schema)

parsed = (
    logs.withColumn("client_ip", regexp_extract("raw_log", r"^(\\S+)", 1))
    .withColumn("http_method", regexp_extract("raw_log", r'"(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)', 1))
    .withColumn("request_path", regexp_extract("raw_log", r'"(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\\s+([^\\s]+)', 1))
    .withColumn("status_code", regexp_extract("raw_log", r'"\\s(\\d{3})\\s', 1))
    .withColumn("bytes_sent", regexp_extract("raw_log", r'\\s(\\d+)$', 1))
    .withColumn("syslog_host", regexp_extract("raw_log", r"^\\w{3}\\s+\\d+\\s+\\d+:\\d+:\\d+\\s+(\\S+)", 1))
    .withColumn("syslog_program", regexp_extract("raw_log", r"\\s([A-Za-z0-9_.-]+)(?:\\[\\d+\\])?:", 1))
    .withColumn("app_event", json_parsed.getField("event"))
    .withColumn("app_service", json_parsed.getField("service"))
    .withColumn("ingest_ts", when(col("kafka_ts").isNotNull(), col("kafka_ts")).otherwise(current_timestamp()))
    .withColumn("ingest_date", to_date(col("ingest_ts")))
)

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


def append_to_hive(batch_df, batch_id):
    if batch_df.rdd.isEmpty():
        return

    (
        batch_df.select(*output_cols)
        .write.mode("append")
        .format("parquet")
        .insertInto("siem.logs_parsed", overwrite=False)
    )


query = (
    parsed.writeStream.outputMode("append")
    .option("checkpointLocation", CHECKPOINT_PATH)
    .foreachBatch(append_to_hive)
    .start()
)

query.awaitTermination()
