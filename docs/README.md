# 📚 Technical Documentation & Reference Library

Welcome to the technical documentation library of the **Apache Lakehouse SIEM Anomaly Detection System**. This directory contains comprehensive blueprints, capacity models, indexing guides, and operations handbooks detailing the platform's distributed architecture.

---

## 📂 Documentation Catalog

Select a guide below to explore the architecture, operations, and caching tiers:

### ⚙️ Core Infrastructure Blueprints
*   📖 **[Distributed HDFS Data Lake Architecture](HDFS_SIEM_Data_Lake_Detailed_Review.md)** — Deep-dive into Hadoop NameNode & DataNode clustering, high-availability parameters, and write-once-read-many (WORM) storage safety.
*   📖 **[Hive Data Lakehouse Schema-on-Read Design](Hive_Data_Lake_Cybersecurity_Analysis.md)** — Relational mapping, PostgreSQL metastore architecture, partition keys, and optimized Parquet storage schemas.
*   📖 **[Kafka Ingestion Pipeline (KRaft Mode)](Kafka_SIEM_Deep_Architecture_Analysis.md)** — High-throughput broker configurations, thread allocations, network protocols, and sub-millisecond topic partition topologies.
*   📖 **[Spark Structured Streaming NDR Engine](Spark_SIEM_Pipeline_Detailed_Analysis.md)** — Real-time ETL stream transformations, dotted-key JSON parsing, and streaming online K-Means clustering mathematical modeling.

### 🗄️ Metadata & Caching Tiers
*   📖 **[Database & Caching Tiers (PostgreSQL & Redis) Optimization](Database_and_Caching_Tiers_Optimization.md)** — Unifying transaction ACID integrity, MVCC, B-Tree/GIN/BRIN indexing strategies, single-threaded Redis LFU caching, and multi-node HA cluster failovers.

### 📊 SOC Dashboards & Threat Hunting
*   📖 **[Superset SOC Visualization & Real-Time Alerts](superset-guide.md)** — Interactive dashboard widget mappings, geo-threat coordinate allocations, and SQL Lab integration via Spark Thrift.
*   📖 **[Forensic Query & Threat Hunting Playbook](EXAMPLE_QUERIES.md)** — Production-ready SQL/PySpark patterns for identifying active DDoS patterns, rapid port-scans, and data exfiltration beacons.

### 🚀 Operations & Deployment Guides
*   📖 **[Unified Operations, Sizing & Verification Guide](Operations_and_Verification_Guide.md)** — Sizing capacities, 13-container microservice resource footprints, active healthchecks, and step-by-step troubleshooting.

---

## 🔗 Navigation & Links
*   ⬅️ **[Back to Root README](../README.md)**
*   📂 **[Go to Data Integration Guide](../data/README.md)**
