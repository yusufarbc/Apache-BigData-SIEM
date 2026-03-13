# Apache-BigData-SIEM 🛡️🏛️

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)

**Apache-BigData-SIEM** is a high-performance, scalable security analytics platform designed to overcome the volume and cost limitations of traditional SIEM solutions. By leveraging a **Data Lakehouse** architecture, it provides both real-time stream processing and deep historical forensic capabilities.

Please check our [Contributing Guidelines](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) if you wish to help improve this project!

## 🚀 Architectural Overview
The project implements a modern Lakehouse pattern to ensure data is processed instantly and stored in an optimized format for long-term security analysis.

* **Ingestion:** **Apache Kafka** — Distributed message buffer handling high Events Per Second (EPS) bursts.
* **Processing:** **Apache Spark Streaming** — Real-time log parsing (Regex), normalization, and correlation.
* **Cataloging:** **Apache Hive** — Structured SQL interface over unstructured log data in HDFS.
* **Storage:** **Apache Hadoop (HDFS)** — Data Lake backbone, storing logs in **Apache Parquet** format.
* **Visualization:** **Apache Superset** & **Apache Zeppelin** — Dashboards, analytics, and interactive notebooks.

### Platform Architecture Diagram

<!-- ARCHITECTURE_DIAGRAM_START -->
```mermaid
graph TD
    subgraph FLOG["📡 Log Generators (Flog)"]
        FW["Flog Web<br/><i>web-logs</i>"]
        FS["Flog Syslog<br/><i>syslogs</i>"]
        FA["Flog App<br/><i>app-logs</i>"]
    end

    subgraph KAFKA["📨 Messaging Layer"]
        KB["Kafka Broker<br/><b>KRaft Mode</b><br/>:9092"]
    end

    subgraph SPARK["⚙️ Processing Layer (Spark)"]
        SM["Spark Master<br/>:8080 · :7077 · :10000"]
        SW1["Spark Worker 1<br/>2G RAM · 2 Cores<br/>:8081"]
        SW2["Spark Worker 2<br/>2G RAM · 2 Cores<br/>:8082"]
    end

    subgraph HIVE["🗂️ Data Cataloging (Hive)"]
        HM["Hive Metastore<br/>:9083"]
        HS2["Hive Server2<br/>:10001 · :10002"]
    end

    subgraph HDFS["💾 Distributed Storage (HDFS)"]
        NN["Namenode<br/>:9870 · :8020"]
        DN1["Datanode 1"]
        DN2["Datanode 2"]
    end

    subgraph DB["🗄️ Unified Database"]
        PG[("Postgres")]
    end

    subgraph VIZ["📊 Analytics & Visualization"]
        SRED["Superset Redis"]
        SUP["Superset<br/>:8088"]
        ZEP["Zeppelin<br/>:8090"]
    end

    FW -->|"web-logs"| KB
    FS -->|"syslogs"| KB
    FA -->|"app-logs"| KB
    KB -->|"Stream Consume"| SM
    SM --- SW1
    SM --- SW2
    SM -->|"Parquet Write"| NN
    NN --- DN1
    NN --- DN2
    HM -->|"Metadata"| PG
    HS2 -->|"Thrift"| HM
    SM -.->|"Schema Registry"| HM
    SUP -->|"Superset DB"| PG
    SUP -->|"SQL Query"| HS2
    SUP --- SRED
    ZEP -->|"Interactive Analysis"| SM

    style FLOG fill:#2d3436,stroke:#00b894,color:#dfe6e9
    style KAFKA fill:#2d3436,stroke:#e17055,color:#dfe6e9
    style SPARK fill:#2d3436,stroke:#fdcb6e,color:#dfe6e9
    style HIVE fill:#2d3436,stroke:#74b9ff,color:#dfe6e9
    style HDFS fill:#2d3436,stroke:#a29bfe,color:#dfe6e9
    style DB fill:#2d3436,stroke:#636e72,color:#dfe6e9
    style VIZ fill:#2d3436,stroke:#fd79a8,color:#dfe6e9
```
<!-- ARCHITECTURE_DIAGRAM_END -->

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

We provide a simple `Makefile` wrapper for all Docker and Spark commands. If you do not have `make` installed, you can look at the `Makefile` and run the raw `docker compose` and `docker exec` commands.

### 1) Start the Platform

```bash
make up
# or: docker compose up -d
```

This will deploy:

- Kafka (KRaft mode)
- Hadoop HDFS (1 NameNode + 2 DataNodes)
- Hive Metastore + HiveServer2 + PostgreSQL Metastore DB
- Spark (1 Master + 2 Workers)
- 3 distributed flog producers (`web-logs`, `syslogs`, `app-logs`)

### 2) Run the ETL Job

```bash
make run-job
# or: docker exec -it spark-master spark-submit ...
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