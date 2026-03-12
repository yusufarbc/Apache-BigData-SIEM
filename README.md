# Apache-BigData-SIEM 🛡️🏛️

**Apache-BigData-SIEM** is a high-performance, scalable security analytics platform designed to overcome the volume and cost limitations of traditional SIEM solutions. By leveraging a **Data Lakehouse** architecture, it provides both real-time stream processing and deep historical forensic capabilities.

## 🚀 Architectural Overview
The project implements a modern Lakehouse pattern to ensure data is processed instantly and stored in an optimized format for long-term security analysis.

* **Ingestion:** **Apache Kafka** - Serves as a distributed message buffer to handle high Events Per Second (EPS) bursts.
* **Processing:** **Apache Spark Streaming** - Performs real-time Log Parsing (Regex-based), normalization, and correlation.
* **Cataloging:** **Apache Hive** - Provides a structured SQL interface over unstructured log data stored in HDFS.
* **Storage:** **Apache Hadoop (HDFS)** - The backbone of the Data Lake, storing logs in **Apache Parquet** format for efficient columnar access.

## 💡 Key Features
- **Real-time Threat Detection:** Immediate anomaly detection and alerting using Spark's windowing functions.
- **Advanced Threat Hunting:** High-speed SQL queries over billions of rows using Spark SQL and Hive.
- **Lakehouse Efficiency:** Combines the flexibility of a Data Lake with the structural performance of a Data Warehouse.
- **Cost-Effective Scalability:** Built entirely on the open-source Apache ecosystem, eliminating expensive per-terabyte licensing.

## 🛠️ Technology Stack
- **Messaging:** Apache Kafka
- **Processing Engine:** Apache Spark (PySpark)
- **Data Warehouse:** Apache Hive
- **Distributed Storage:** Apache Hadoop (HDFS)
- **Environment:** Docker & Docker-Compose

## 📂 Quick Start

### 1) Start the Platform

```bash
docker compose up -d --build
```

This will deploy:

- Kafka (KRaft mode)
- Hadoop HDFS (1 NameNode + 2 DataNodes)
- Hive Metastore + HiveServer2 + PostgreSQL Metastore DB
- Spark (1 Master + 2 Workers)
- 3 distributed flog producers (`web-logs`, `syslogs`, `app-logs`)

### 2) Run the ETL Job

```bash
docker exec -it spark-master spark-submit \
	--master spark://spark-master:7077 \
	--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
	/opt/bitnami/spark/jobs/etl_process.py
```

### 3) Validate Distributed Health

Use the operational runbook in `docs/verification-guide.md` to verify:

- HDFS DataNode distribution
- Hive connectivity
- Kafka topic flow
- Spark worker registration
- Hive table population from Kafka stream

## 📁 Added Infrastructure Files

- `docker-compose.yml`
- `config/hadoop/core-site.xml`
- `config/hadoop/hdfs-site.xml`
- `config/hive/hive-site.xml`
- `config/spark/spark-defaults.conf`
- `flog/Dockerfile`
- `flog/publish_flog.sh`
- `jobs/etl_process.py`
- `docs/verification-guide.md`