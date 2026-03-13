# Apache-BigData-SIEM: Capacity & Performance Report

This document outlines the hardware footprint, maximum theoretical throughput, and sizing capabilities of the localized SIEM cluster.

## 1. Container Details (Microservices)
The architecture consists of a fully distributed Data Lakehouse environment with **17 distinct containers**:

### Log Simulation (3 Containers) - *Test Environment Only*
- **`flog-web`, `flog-app`, `flog-syslog`** (x3): Generators simulating real-time log traffic. These act as dummy log sources and are explicitly for testing/demonstration.

### Ingestion Tier (1 Container)
- **`kafka-broker`** (x1): The messaging backbone running in KRaft mode.

### Storage Tier (3 Containers)
- **`namenode`** (x1): HDFS namespace manager.
- **`datanode-1`, `datanode-2`** (x2): HDFS storage nodes holding the raw data and Parquet files.

### Processing & ETL Tier (3 Containers)
- **`spark-master`** (x1): Spark cluster manager & distributed SQL Thrift Server (Port 10000).
- **`spark-worker-1`, `spark-worker-2`** (x2): Executors running PySpark Streaming tasks (4 cores, 4GB RAM combined).

### Metadata & Catalog Tier (4 Containers)
- **`hive-metastore-db`** (x1): PostgreSQL backend for schemas.
- **`hive-metastore`** (x1): Apache Hive catalog service.
- **`hive-server2`** (x1): Standard JDBC/ODBC Hive interface (Port 10001).

### Analysis & Web GUI Tier (3 Containers)
- **`zeppelin`** (x1): Interactive Spark SQL notebook.
- **`superset`** (x1): BI metrics dashboard.
- **`superset-postgres`, `superset-redis`** (x2): Underlying DB/Cache for Superset.

---

## 2. Traffic and Throughput Capacity 🚀

The cluster operates using Spark Structured Streaming on a micro-batch architecture. 

### Current Traffic (Simulated Load)
- **Configuration**: 2000 logs generated per second per simulator (`BATCH_SIZE="2000"`, `LOOP_DELAY="1"`).
- **Current EPS (Events Per Second)**: **~6000 EPS** sustained.

### Maximum Theoretical Limits (Local 4-Core Setup)
- **HDFS**: Limited by SATA/NVMe I/O. For Parquet format, easily handles **15,000+ EPS**.
- **Kafka**: A single broker in KRaft mode on a modern CPU can handle **~30,000+ EPS** (High throughput limit).
- **Spark Processing**: The bottleneck logic is JSON/Regex parsing in python. Using 2 Workers (4 Cores / 4GB total), the local cluster will peak around **5,000 to 8,000 EPS** before scheduling delays occur.

> 💡 **Horizontal Scalability:** To increase processing limits to Enterprise SIEM levels (e.g., **100,000+ EPS**), you can simply scale `spark-worker` instances to 10+ and add multiple load-balanced `kafka-broker` nodes entirely through Docker Compose.

---

## 3. Resource Footprint (Memory / CPU / Disk) 💻

Approximate consumptions of the local Docker network based on resting/low-load states:

| Component Category      | CPU Utilization | Memory Size (RAM) | Notes |
|-------------------------|-----------------|-------------------|-------|
| **Storage (Hadoop)**    | ~11.5 %         | ~2.2 GiB           | Increases predictably with HDFS writes. |
| **Load Gen. (Flog)**    | ~7.8 %          | ~4 MiB             | Dummy log generators. *Test Environment Only*. |
| **Ingestion (Kafka)**   | ~1.8 %          | ~711 MiB           | Stable. Memory is regulated by JVM Heap sizes. |
| **Compute (Spark)**     | ~1.0 %          | ~1.6 GiB           | Bursts occurring every 1 second during ETL micro-batches. |
| **Metadata (Hive)**     | ~0.1 %          | ~695 MiB           | Passive most of the time. |
| **GUI (Zeppelin/BI)**   | ~0.7 %          | ~600 MiB           | Spikes locally when rendering heavy Superset dashboards. |
| **Total Allocation**    | **~23 % CPU**   | **~5.8 GiB (Total)**| Total footprint on the host Docker Engine. |

**Disk Scaling:** Log consumption scales linearly based on compression ratios. Storing data in Hive as `.parquet` drastically reduces storage footprints over standard `.csv` or `.json` (typically a 10x - 20x reduction).
