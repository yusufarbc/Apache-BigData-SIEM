# Apache SIEM & NDR Unified Command Center 🛡️

**Apache-BigData-SIEM** is a state-of-the-art **Data Lakehouse** platform designed for high-throughput security analytics and AI-driven **Network Detection & Response (NDR)**. It integrates the power of Apache Spark's Machine Learning with the massive scalability of HDFS and Hive.

---

## 🏗️ Architecture & Core Components

The platform follows a modern **Lakehouse** architecture, ensuring real-time processing and long-term forensic storage:

### 1. Ingestion Layer (Kafka)
- **Kafka Producer:** A multi-threaded engine capable of capturing and streaming Zeek/Suricata logs in parallel.
- **Kafka Broker:** High-availability messaging backbone for all incoming network flows.

### 2. Processing & ML Engine (Spark Unified)
- **Real-time ETL:** Automated parsing, normalization, and HDFS sink for raw network logs.
- **NDR K-Means:** A streaming Machine Learning engine that scores every flow for anomalies in real-time.
- **Unified Master:** Centralized orchestration of all SIEM pipelines for maximum resource efficiency.

### 3. Storage Layer (HDFS & Hive)
- **HDFS Data Lake:** Distributed forensic storage for petabyte-scale log retention.
- **Hive Metastore:** Centralized schema management for unified access across Spark, Zeppelin, and Superset.

### 4. Command Center & Insights
- **Apache Superset:** The primary **SOC Command Center**. It provides a real-time, interactive dashboard for security analysts to monitor incident feeds, global threat maps, and anomalous traffic patterns.
- **Apache Zeppelin:** The **Cyber Research Lab**. A collaborative notebook environment for threat hunters and data scientists to perform forensic deep-dives, tune K-Means models, and query the HDFS Data Lake using SQL and Python.

---

## 📊 Platform Architecture Diagram

```mermaid
graph TD
<<<<<<< HEAD
    subgraph SOURCES["📡 Data Sources"]
        ZP["Zeek / Suricata Logs"]
    end

    subgraph KAFKA["📨 Ingestion Layer"]
        KP["Kafka Producer (High Speed)"]
        KB["Kafka Broker (Message Hub)"]
    end

    subgraph SPARK["⚙️ Unified Engine"]
        SM["Spark Master<br/><i>ETL + NDR ML</i>"]
        SW["Spark Workers"]
=======
    subgraph KAFKA["📨 Messaging Layer"]
        KB["Kafka Broker<br/><b>KRaft Mode</b><br/>:9092"]
    end

    subgraph SPARK["⚙️ Processing Layer (Spark)"]
        SM["Spark Master<br/>:8080 · :7077 · :10000"]
        SW1["Spark Worker 1<br/>16G RAM · 8 Cores<br/>:8081"]
        SW2["Spark Worker 2<br/>16G RAM · 8 Cores<br/>:8082"]
>>>>>>> eebf21c4a645bedf6eae334a95946c70ebfc2d6f
    end

    subgraph LAKE["💾 Lakehouse Layer"]
        NN["HDFS NameNode"]
        HM["Hive Metastore"]
        PG["PostgreSQL (Metadata)"]
    end

    subgraph VIZ["📊 SOC Command Center"]
        SUP["Superset Dashboard"]
        ZEP["Zeppelin Lab"]
    end

    ZP --> KP --> KB --> SM
    SM --- SW
    SM --> LAKE
    VIZ --> LAKE
    
    style SPARK fill:#f8fafc,stroke:#fdcb6e,stroke-width:2px
    style LAKE fill:#f8fafc,stroke:#74b9ff,stroke-width:2px
    style VIZ fill:#f8fafc,stroke:#fd79a8,stroke-width:2px
```

---

## 🚀 Quick Deployment

Spin up the entire SOC environment with a single command:

```powershell
docker compose up -d --build
```

### 🔗 Service Access Points

| Service | Endpoint | Description |
|:---|:---|:---|
| **SOC Dashboard** | [http://localhost:8088](http://localhost:8088) | Real-time security monitoring & alerts |
| **ML Notebooks** | [http://localhost:9090](http://localhost:9090) | Threat hunting & Data science lab |
| **Spark Master** | [http://localhost:8080](http://localhost:8080) | Cluster status & job monitoring |
| **HDFS NameNode** | [http://localhost:9870](http://localhost:9870) | Data lake explorer |

---

## 📂 Project Ecosystem
- **`config/`** — Unified service orchestration, build contexts, and ML jobs.
- **`docs/`** — Deep-dive research, capacity planning, and operational guides.
- **`data/`** — Sample datasets for immediate NDR testing.
- **`showcase/`** — Interactive presentation of the platform capabilities.

---
*Built for the next generation of Cyber Defense.*
