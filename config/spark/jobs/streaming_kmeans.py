import os
import sys
import json
import math
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, udf, current_timestamp, to_date, 
    window, count, avg, stddev, lit
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    DoubleType, LongType, FloatType, TimestampType
)
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans, KMeansModel
from pyspark.ml.linalg import Vectors, VectorUDT

# ── CONFIGURATION ────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker:9092")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC", "real_network_logs")
CHECKPOINT_PATH = "hdfs://namenode:8020/tmp/checkpoints/ndr_streaming_kmeans"
ANOMALIES_LOCATION = "hdfs://namenode:8020/user/hive/warehouse/siem.db/network_anomalies"
FLOWS_LOCATION     = "hdfs://namenode:8020/user/hive/warehouse/siem.db/network_flows"

FLOWS_TABLE        = "siem.network_flows"
ANOMALIES_TABLE    = "siem.network_anomalies"

# K-Means Parameters
K = int(os.getenv("KMEANS_K", "8"))
SEED = 42
COLD_START_ROWS = 100  # Minimum rows to train the first model
RETRAIN_EVERY_BATCHES = 50  # Frequency of model updates
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "3.0"))  # Significantly increased to reduce noise

# Features used for ML
# Removed dest_port because port numbers are not linear distances
# Added contextual IP flags to differentiate internal vs external, and client vs server behavior
FEATURE_COLS = ["duration_log", "orig_bytes_log", "resp_bytes_log", "is_dst_external", "is_src_server"]

from pyspark.sql.types import BooleanType

# ── SCHEMAS ──────────────────────────────────────────────────────────────────
# Note: Zeek logs use dots in keys (id.orig_h). 
# We define them here but will ALIAS them immediately after parsing.
NETWORK_SCHEMA = StructType([
    StructField("ts", StringType(), True),
    StructField("uid", StringType(), True),
    StructField("id.orig_h", StringType(), True),
    StructField("id.orig_p", StringType(), True),
    StructField("id.resp_h", StringType(), True),
    StructField("id.resp_p", StringType(), True),
    StructField("proto", StringType(), True),
    StructField("service", StringType(), True),
    StructField("duration", StringType(), True),
    StructField("orig_bytes", StringType(), True),
    StructField("resp_bytes", StringType(), True),
    StructField("conn_state", StringType(), True),
    StructField("orig_pkts", StringType(), True),
    StructField("resp_pkts", StringType(), True),
    StructField("is_attack", BooleanType(), True),
])

# ── HELPERS ──────────────────────────────────────────────────────────────────

def train_kmeans(feature_df):
    """Trains a KMeans model on the provided DataFrame."""
    print(f"[NDR] Training K-Means model on {feature_df.count()} rows...")
    
    # Feature Engineering for training
    from pyspark.sql.functions import log1p, when
    train_df = feature_df.na.fill(value=0.0, subset=["duration"]) \
                         .na.fill(value=0, subset=["orig_bytes", "resp_bytes"]) \
                         .withColumn("duration_log", log1p(col("duration"))) \
                         .withColumn("orig_bytes_log", log1p(col("orig_bytes"))) \
                         .withColumn("resp_bytes_log", log1p(col("resp_bytes"))) \
                         .withColumn("is_dst_external", when(col("dest_ip").rlike("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2[0-9]|3[0-1]))"), 0).otherwise(1)) \
                         .withColumn("is_src_server", when(col("src_ip").isin(["192.168.1.250", "192.168.1.100"]), 1).otherwise(0))

    assembler = VectorAssembler(
        inputCols=FEATURE_COLS, 
        outputCol="raw_features",
        handleInvalid="skip"
    )
    
    vectorized = assembler.transform(train_df)
    
    scaler = StandardScaler(
        inputCol="raw_features", 
        outputCol="features",
        withStd=True, withMean=True
    )
    scaler_model = scaler.fit(vectorized)
    scaled_data = scaler_model.transform(vectorized)
    
    kmeans = KMeans(k=K, seed=SEED, featuresCol="features", predictionCol="cluster_id")
    model = kmeans.fit(scaled_data)
    
    # Safely extract centroids
    centroids = [c.tolist() if hasattr(c, "tolist") else list(c) for c in model.clusterCenters()]
    
    print(f"[NDR] K-Means trained — {len(centroids)} clusters | WSSSE={model.summary.trainingCost:.4f}")
    return model, scaler_model, centroids

# ── STREAM PROCESSOR ──────────────────────────────────────────────────────────

class BatchProcessor:
    def __init__(self):
        self._model = None
        self._scaler = None
        self._centroids = None
        self._buffer = None  # To hold initial data for cold start
        self._batch_count = 0
        self._training_count = 0
        
    def _train_on_buffer(self, spark, batch_id):
        if self._buffer is None or self._buffer.count() < COLD_START_ROWS:
            return
        
        try:
            start_time = datetime.now()
            row_count = self._buffer.count()
            
            # Train model
            self._model, self._scaler, self._centroids = train_kmeans(self._buffer)
            self._training_count += 1
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            wssse = self._model.summary.trainingCost

            # Record metrics to Hive
            metrics_data = [(
                int(self._training_count),
                datetime.now(),
                float(wssse),
                float(duration),
                int(row_count)
            )]
            metrics_df = spark.createDataFrame(metrics_data, ["batch_id", "ingest_ts", "wssse", "training_duration_sec", "training_rows"])
            metrics_df.write.mode("append").parquet("hdfs://namenode:8020/user/hive/warehouse/siem.db/model_metrics")
            
            print(f"[NDR] Model metrics recorded for training #{self._training_count}")
            self._buffer = None # Clear buffer after training
        except Exception as e:
            print(f"[NDR] Error during training: {str(e)}")

    def process(self, batch_df, batch_id):
        spark = batch_df.sparkSession
        row_count = batch_df.count()
        
        if row_count == 0:
            return

        # 1. Cold Start Logic
        if self._model is None:
            print(f"[NDR] Cold-start buffer: {row_count} new rows. Need {COLD_START_ROWS} total.")
            if self._buffer is None:
                self._buffer = batch_df
            else:
                self._buffer = self._buffer.union(batch_df)
            
            if self._buffer.count() >= COLD_START_ROWS:
                self._train_on_buffer(spark, batch_id)
            else:
                return # Still in training phase
        
        # 1b. Periodic Retraining Logic
        self._batch_count += 1
        if self._batch_count % RETRAIN_EVERY_BATCHES == 0:
            print(f"[NDR] Batch {batch_id}: Triggering periodic model update...")
            self._buffer = batch_df # Use current batch to refresh the model
            self._train_on_buffer(spark, batch_id)
        
        # 2. Inference Logic
        try:
            # Feature Engineering: Contextualize IP addresses and scale bytes/duration
            # We use log1p(x) = log(1+x) to avoid log(0) issues
            from pyspark.sql.functions import log1p, when
            
            fe_df = batch_df.na.fill(value=0.0, subset=["duration"]) \
                           .na.fill(value=0, subset=["orig_bytes", "resp_bytes"]) \
                           .withColumn("duration_log", log1p(col("duration"))) \
                           .withColumn("orig_bytes_log", log1p(col("orig_bytes"))) \
                           .withColumn("resp_bytes_log", log1p(col("resp_bytes"))) \
                           .withColumn("is_dst_external", when(col("dest_ip").rlike("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2[0-9]|3[0-1]))"), 0).otherwise(1)) \
                           .withColumn("is_src_server", when(col("src_ip").isin(["192.168.1.250", "192.168.1.100"]), 1).otherwise(0))
            
            # Prepare features
            assembler = VectorAssembler(inputCols=FEATURE_COLS, outputCol="raw_features", handleInvalid="skip")
            vectorized = assembler.transform(fe_df)
            scaled = self._scaler.transform(vectorized)
            
            # Predict clusters
            predictions = self._model.transform(scaled)
            
            # Distance UDF to calculate anomaly score
            # Centroids are passed as a broadcast-like list via closure
            local_centroids = self._centroids
            @udf(FloatType())
            def calc_distance(features, cluster_id):
                if cluster_id >= len(local_centroids): return 0.0
                c = local_centroids[cluster_id]
                f = features.toArray() if hasattr(features, "toArray") else list(features)
                return float(math.sqrt(sum((a - b)**2 for a, b in zip(f, c))))

            scored = predictions.withColumn("anomaly_score", calc_distance(col("features"), col("cluster_id")))
            # Calculate max score for debugging
            max_score = scored.agg({"anomaly_score": "max"}).collect()[0][0] or 0.0
            print(f"[NDR] Batch {batch_id}: Max Anomaly Score in this batch = {max_score:.4f}")

            scored = scored.withColumn("is_anomaly", col("anomaly_score") > ANOMALY_THRESHOLD)
            scored = scored.withColumn("ingest_date", to_date(current_timestamp()))
            
            # 3. Write all flows directly to HDFS as Parquet (partitioned by date)
            output_df = scored.select(
                col("kafka_ts"),
                col("kafka_ts").alias("ingest_ts"),  # Alias for Superset compatibility
                "ts", "uid", "src_ip", "src_port", "dest_ip", "dest_port",
                "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
                "is_dst_external", "is_src_server",
                "cluster_id", "anomaly_score", "is_anomaly", "ingest_date"
            )

            print(f"[NDR] Batch {batch_id}: Writing {output_df.count()} flows to {FLOWS_LOCATION}...")
            (
                output_df.write
                .mode("append")
                .partitionBy("ingest_date")
                .parquet(FLOWS_LOCATION)
            )

            # 4. Write anomalies to separate HDFS path
            anomalies = output_df.filter(col("is_anomaly") == True)
            anom_count = anomalies.count()
            if anom_count > 0:
                print(f"[NDR] Batch {batch_id}: Detected {anom_count} anomalies! Writing to {ANOMALIES_LOCATION}...")
                (
                    anomalies.write
                    .mode("append")
                    .partitionBy("ingest_date")
                    .parquet(ANOMALIES_LOCATION)
                )
            # 5. Sync metadata with Hive so Superset sees the new partitions
            try:
                spark.sql(f"MSCK REPAIR TABLE {FLOWS_TABLE}")
                spark.sql(f"MSCK REPAIR TABLE {ANOMALIES_TABLE}")
                print(f"[NDR] Batch {batch_id}: Hive metadata repaired.")
            except Exception as e:
                print(f"[NDR] Batch {batch_id}: Hive repair failed: {str(e)}")

            print(f"[NDR] Batch {batch_id}: Processed successfully.")

        except Exception as e:
            print(f"[NDR] Error processing batch {batch_id}: {str(e)}")
            import traceback
            traceback.print_exc()

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    spark = SparkSession.builder \
        .appName("ndr-streaming-kmeans") \
        .config("spark.sql.catalogImplementation", "hive") \
        .config("spark.hadoop.hive.metastore.uris", "thrift://hive-metastore:9083") \
        .enableHiveSupport() \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    # Initialize Hive Tables
    spark.sql("CREATE DATABASE IF NOT EXISTS siem")
    
    # We drop and recreate to ensure schema consistency during development
    # In production, you would use ALTER TABLE or migrations.
    
    spark.sql(f"DROP TABLE IF EXISTS {FLOWS_TABLE}")
    spark.sql(f"DROP TABLE IF EXISTS {ANOMALIES_TABLE}")
    spark.sql(f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {FLOWS_TABLE} (
            kafka_ts TIMESTAMP,
            ingest_ts TIMESTAMP,
            ts DOUBLE,
            uid STRING,
            src_ip STRING,
            src_port INT,
            dest_ip STRING,
            dest_port INT,
            proto STRING,
            service STRING,
            duration DOUBLE,
            orig_bytes LONG,
            resp_bytes LONG,
            conn_state STRING,
            is_dst_external INT,
            is_src_server INT,
            cluster_id INT,
            anomaly_score FLOAT,
            is_anomaly BOOLEAN
        )
        PARTITIONED BY (ingest_date DATE)
        STORED AS PARQUET
        LOCATION '{FLOWS_LOCATION}'
    """)

    spark.sql(f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {ANOMALIES_TABLE} (
            kafka_ts TIMESTAMP,
            ingest_ts TIMESTAMP,
            ts DOUBLE,
            uid STRING,
            src_ip STRING,
            src_port INT,
            dest_ip STRING,
            dest_port INT,
            proto STRING,
            service STRING,
            duration DOUBLE,
            orig_bytes LONG,
            resp_bytes LONG,
            conn_state STRING,
            is_dst_external INT,
            is_src_server INT,
            cluster_id INT,
            anomaly_score FLOAT,
            is_anomaly BOOLEAN
        )
        PARTITIONED BY (ingest_date DATE)
        STORED AS PARQUET
        LOCATION '{ANOMALIES_LOCATION}'
    """)

    spark.sql("""
        CREATE TABLE IF NOT EXISTS siem.model_metrics (
            batch_id LONG,
            ingest_ts TIMESTAMP,
            wssse DOUBLE,
            training_duration_sec DOUBLE,
            training_rows LONG
        )
        STORED AS PARQUET
    """)

    print("[NDR] Hive tables initialized and cleaned.")

    # ── Kafka Stream ──────────────────────────────────────────────────────────
    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribePattern",        KAFKA_TOPIC)
        .option("startingOffsets",         os.getenv("KAFKA_STARTING_OFFSETS", "earliest"))
        .option("failOnDataLoss",          "false")
        .load()
    )

    parsed = (
        raw_stream
        .select(
            col("timestamp").alias("kafka_ts"),
            from_json(col("value").cast("string"), NETWORK_SCHEMA).alias("d"),
        )
        .select(
            col("kafka_ts"),
            col("d").getField("ts").alias("ts"),
            col("d").getField("uid").alias("uid"),
            col("d").getField("id.orig_h").alias("src_ip"),
            col("d").getField("id.orig_p").cast("integer").alias("src_port"),
            col("d").getField("id.resp_h").alias("dest_ip"),
            col("d").getField("id.resp_p").cast("integer").alias("dest_port"),
            col("d").getField("proto").alias("proto"),
            col("d").getField("service").alias("service"),
            col("d").getField("duration").cast("double").alias("duration"),
            col("d").getField("orig_bytes").cast("long").alias("orig_bytes"),
            col("d").getField("resp_bytes").cast("long").alias("resp_bytes"),
            col("d").getField("conn_state").alias("conn_state")
        )
        .na.drop(subset=["src_ip", "dest_ip", "dest_port"])
        .filter((col("src_ip") != "") & (col("src_ip").isNotNull()) & (col("src_ip") != "-"))
    )

    processor = BatchProcessor()

    query = (
        parsed.writeStream
        .outputMode("append")
        .option("checkpointLocation", CHECKPOINT_PATH)
        .trigger(processingTime="10 seconds")
        .foreachBatch(processor.process)
        .start()
    )

    print(f"[NDR] Streaming K-Means detector started. Topic: {KAFKA_TOPIC}")
    query.awaitTermination()

if __name__ == "__main__":
    main()
