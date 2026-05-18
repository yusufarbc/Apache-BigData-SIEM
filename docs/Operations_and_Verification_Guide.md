# 🚀 Unified Operations, Sizing & Verification Guide

This document combines the sizing capacities, microservices footprints, and step-by-step verification procedures to manage, audit, and troubleshoot the 13 container distributed security data lakehouse stack.

---

## 1. Platform Sizing & Capacity Analysis

The architecture consists of a fully distributed Data Lakehouse environment containing **13 distinct microservices**:

### Ingestion Tier (2 Containers)
*   **`kafka-broker`** (x1): The messaging backbone running in KRaft mode.
*   **`kafka-producer`** (x1): High-speed log injector streaming real-world network and server events directly from the raw SecRepo and Linux datasets.

### Storage Tier (2 Containers)
*   **`namenode`** (x1): HDFS distributed namespace manager and file health dashboard.
*   **`datanode`** (x1): HDFS storage node holding raw data and Parquet files.

### Processing & ETL Tier (5 Containers)
*   **`spark-master`** (x1): Spark cluster manager and coordinator.
*   **`spark-worker`** (x2): Two clustered Spark worker instances executing streaming pipelines (2 cores, 2GB RAM per worker instance).
*   **`spark-thrift`** (x1): Distributed SQL Thrift JDBC/OBDC Server mapping SparkSQL datasets (Port 10000).
*   **`siem-engine`** (x1): Automated PySpark ETL and anomaly detector runner (`etl_process.py` and `streaming_kmeans.py`).

### Metadata & Catalog Tier (2 Containers)
*   **`postgres`** (x1): PostgreSQL backing database hosting metastore schemas for Hive and configurations for Superset.
*   **`hive-metastore`** (x1): Apache Hive metastore catalog mapping database tables and views.

### Analysis & Web GUI Tier (2 Containers)
*   **`superset`** (x1): BI metrics reporting and real-time security dashboard.
*   **`zeppelin`** (x1): Interactive Python/Spark research notebook and threat hunting playground.

---

## 2. Traffic and Throughput Capacity 🚀

The cluster operates using Spark Structured Streaming on a micro-batch architecture:

### Current Traffic (Real-World Ingestion Rate)
*   **Ingestion Rate**: Configured to stream up to **2,000 logs per second per dataset** to simulate enterprise loads.
*   **Sustained EPS (Events Per Second)**: **~6,000 EPS** sustained.

### Maximum Theoretical Limits (Local 4-Core Setup)
*   **HDFS**: Limited by disk/SSD I/O. For Parquet format, easily handles **15,000+ EPS**.
*   **Kafka**: A single broker in KRaft mode on a modern CPU can handle **~30,000+ EPS** (High throughput limit).
*   **Spark Processing**: The bottleneck logic is JSON/Regex parsing in Python. Using 2 Workers (4 Cores / 4GB total), the local cluster will peak around **5,000 to 8,000 EPS** before scheduling delays occur.

> [!TIP]
> **Horizontal Scalability:** To increase processing limits to Enterprise SIEM levels (e.g., **100,000+ EPS**), you can simply scale `spark-worker` instances to 10+ and add multiple load-balanced `kafka-broker` nodes entirely through Docker Compose.

---

## 3. Resource Footprint (Memory / CPU / Disk) 💻

Approximate consumptions of the local Docker network based on resting/low-load states:

| Component Category | CPU Utilization | Memory Size (RAM) | Notes |
| :--- | :---: | :---: | :--- |
| **Storage (Hadoop)** | ~11.5 % | ~2.2 GiB | NameNode & DataNode. Increases predictably with HDFS writes. |
| **Ingestion (Kafka)** | ~2.2 % | ~715 MiB | Broker & Producer. Stable. Memory is regulated by JVM Heap sizes. |
| **Compute (Spark)** | ~2.5 % | ~2.4 GiB | Master, Workers, Thrift & Engine. Active streaming tasks. |
| **Metadata (Hive & DB)**| ~0.2 % | ~720 MiB | PostgreSQL & Hive Metastore catalog databases. |
| **GUI (Superset & Zep)**| ~0.8 % | ~750 MiB | UI dashboard and notebook servers. Spikes during heavy queries. |
| **Total Allocation** | **~17.2 % CPU**| **~6.6 GiB (Total)**| Total footprint on the host Docker Engine. |

**Disk Scaling:** Log consumption scales linearly based on compression ratios. Storing data in Hive as `.parquet` drastically reduces storage footprints over standard `.csv` or `.json` (typically a 10x - 20x reduction).

---

## 4. Phase-by-Phase Verification Procedures

Follow these steps to verify that the 13 platform containers are healthy and communicating correctly.

### Step 1: Start the Full Stack
Launch the orchestrator stack using Docker Compose:
```bash
docker compose up -d --build
```

Check the health status of all container nodes:
```bash
docker compose ps
```
All 13 containers should display as `running (healthy)` or `running`.

### Step 2: Verify Hadoop HDFS Distribution
Check the HDFS NameNode Web Console:
*   [http://localhost:9870](http://localhost:9870)

Confirm the HDFS DataNode status from the command line (should register 1 live datanode container):
```bash
docker exec -it namenode hdfs dfsadmin -report
```
Look for:
*   `Live datanodes (1)`

Verify that the HDFS file path can be written to and read successfully:
```bash
docker exec -it namenode hdfs dfs -mkdir -p /tmp/healthcheck
docker exec -it namenode hdfs dfs -ls /
```

### Step 3: Verify Hive Metastore + Spark Thrift Server
Confirm the Hive Metastore is listening and reachable on the metadata port:
```bash
docker exec -it hive-metastore /opt/hive/bin/hive --service metatool -listFSRoot
```

Execute a test query against the Spark Thrift JDBC server (which maps SparkSQL tables to port `10000` on the `spark-thrift` container):
```bash
docker exec -it spark-thrift /opt/bitnami/spark/bin/beeline -u jdbc:hive2://localhost:10000 -e "SHOW DATABASES;"
```

### Step 4: Verify Kafka Broker + Ingested Topics
List the active Kafka topics inside the KRaft broker:
```bash
docker exec -it kafka-broker kafka-topics.sh --bootstrap-server localhost:9092 --list
```
You should see topics auto-created by the `kafka-producer` container as it streams network events:
*   `real_network_logs` (Zeek connection logs used for streaming K-Means)
*   `web-logs` (Zeek HTTP request logs)
*   `dns-logs` (Zeek DNS lookup logs)
*   `ssl-logs` (Zeek SSL/TLS handshake logs)
*   `ssh-logs` (Zeek SSH session logs)
*   `syslogs` (Host log signals)
*   `app-logs` (Application level logs)

Consume sample event packets from the Kafka broker:
```bash
docker exec -it kafka-broker kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic real_network_logs --from-beginning --max-messages 5
```

### Step 5: Verify Spark Cluster Distribution
Examine the Spark Master Web Console to monitor jobs, active streaming queries, and worker allocations:
*   [http://localhost:8080](http://localhost:8080)

In the Spark Master Web UI, confirm that both Spark Worker replicas (each allocated 2 Cores and 2GB RAM by the compose manifest) are fully registered and healthy.

### Step 6: Run and Verify the Streaming ETL & NDR Engines
The Spark streaming applications are automatically submitted at boot-up by the dedicated **`siem-engine`** container. Monitor the streaming loops and anomaly scoring metrics by reviewing the container logs:
```bash
# Monitor the PySpark Structured Streaming ETL and NDR K-Means logs
docker logs siem-engine --tail 100 -f
```

After logs have streamed for a few minutes, query the Hive warehouse table `siem.logs_parsed` through the Spark Thrift client to verify database insertion:
```bash
docker exec -it spark-thrift /opt/bitnami/spark/bin/beeline -u jdbc:hive2://localhost:10000 -e "SELECT source_topic, COUNT(*) FROM siem.logs_parsed GROUP BY source_topic;"
```

---

## 5. Failure Isolation & Troubleshooting Quick Checks

### If Kafka is not receiving log event streams:
```bash
# Check the Python Zeek/syslog streamer log output
docker logs kafka-producer --tail 100
```

### If the Spark Streaming engine cannot write Parquet files to the HDFS storage layer:
```bash
docker logs siem-engine --tail 100
docker logs spark-master --tail 100
docker logs hive-metastore --tail 100
```

### If the HDFS Distributed storage layer is reporting unhealthy states:
```bash
docker logs namenode --tail 100
docker logs datanode --tail 100
```

---

## 🔗 Navigation & Links
*   ⬅️ **[Back to Root README](../README.md)**
*   📂 **[Go to Technical Documentation Library](./)**
