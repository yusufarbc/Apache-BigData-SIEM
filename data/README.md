# 📊 Data Lakehouse Dataset: Real-World Unified Security Logs

This directory is designated for the unified and merged security log datasets that drive the **Apache Big Data SIEM & Network Detection & Response (NDR)** platform. 

> [!IMPORTANT]
> **GitHub Exclusion Notice:** The dataset files in this directory contain over **34.4 Million real-world security events** totaling over **5.5 GB** in raw size. Due to GitHub's file size limitations, these files are ignored via `.gitignore` and are not committed to the repository. This document serves as a complete reference guide for the dataset structure, statistics, and integration.

> [!TIP]
> **Decompressed Ingestion Data:** You can download the pre-consolidated, highly compressed dataset archive `data.tar.gz` (750 MB, extracts to 5.5 GB raw connection and system logs) directly from our cloud storage share:
> 🔗 **[Download Pre-Consolidated Security Logs (750 MB)](https://www.mediafire.com/file/h1qu7pgwbslskal/data.tar.gz/file)**
> *(Simply extract the archive contents directly inside this `data/` folder, and the system orchestrator will automatically pick them up at startup).*

---

## 🏗️ Dataset Architecture & Sources

The testing and validation datasets are compiled and merged from two primary, high-fidelity real-world environments using automated log consolidation tools:

1. **`raw_data/` (Zeek Network Logs):** Active, high-throughput network monitoring records capturing real-world traffic flows, protocol-specific transactions (HTTP, DNS, SSL), and cryptographic handshakes.
2. **`log/` (Enterprise Linux Server Logs):** Exhaustive operating system and application audits extracted from cPanel & CloudLinux production environments (audits, daemon performance, WAF blocks).

These logs are automatically merged (appended) by our utility scripts to represent a unified forensic trail.

---

## 📊 Dataset Statistics & File Breakdown

Below is the complete analysis of the consolidated dataset files that are utilized by the Kafka streaming producer:

### Core Log Files (Top Volume & Forensic Value)

| Rank | File Name | Line Count | Size on Disk | Log Category / Description |
| :--- | :--- | :---: | :---: | :--- |
| 1 | **`conn.log`** | **23,270,813** | **2.6 GB** | **Zeek** — Complete network connection states |
| 2 | **`http.log`** | **2,752,802** | **1.5 GB** | **Zeek** — Full HTTP request/response transactions |
| 3 | **`loaded_scripts.log`** | **1,725,717** | **121 MB** | **Zeek** — Loaded scripting signatures & configurations |
| 4 | **`files.log`** | **1,456,514** | **299 MB** | **Zeek** — File transfers and hash identification records |
| 5 | **`chkservd.log`** | **1,503,731** | **103 MB** | **Linux** — Service status monitor daemon events |
| 6 | **`modsec_audit.log`** | **1,182,282** | **103 MB** | **Linux** — ModSecurity Web Application Firewall (WAF) audits |
| 7 | **`dns.log`** | **697,580** | **105 MB** | **Zeek** — Domain Name System (DNS) query/response details |
| 8 | **`traffic-apache.log`** | **542,269** | **44 MB** | **Linux** — Raw Apache web server access and error logs |
| 9 | **`agent.log`** | **426,964** | **107 MB** | **Linux** — CloudLinux background management agent audits |
| 10 | **`weird.log`** | **162,411** | **12 MB** | **Zeek** — Network protocol anomalies and non-standard flows |

### Dataset Aggregates

| Metric Category | Metric Value | Notes |
| :--- | :---: | :--- |
| **Total Log Files** | **102** | Entire security and network audit trail |
| **Active (Non-Empty) Files** | **58** | Files populated with security events |
| **Empty (Placeholder) Files** | **44** | Captured categories with zero passive events |
| **Total Events (Lines)** | **34,404,777** | Ready for high-performance ingestion testing |

### Volume Breakdown by Source

| Log Source Origin | File Count | Total Line Count | Forensic Focus |
| :--- | :---: | :---: | :--- |
| **Zeek Network Captures (`raw_data/`)** | 22 | **30,430,264** | Anomaly detection, ML threat hunting, clustering |
| **Linux Host Audits (`log/`)** | 80 | **3,906,699** | System integrity, failed logins, privilege abuse |
| **Grand Total** | **102** | **34,404,777** | **Unified SIEM & NDR Ecosystem** |

> [!NOTE]
> **Data Cleaning Notice:** The `mysqld.log` dataset has been pre-filtered. A total of **39,932,186 redundant lines** containing deprecated `mysql_native_password` warnings were safely removed to prevent log pollution and maximize storage compression without losing security audit value.

---

## 🚀 Log Integration & Platform Ingestion

These logs feed directly into the **Kafka Messaging Layer** to test real-time ingestion under load. You can configure and run ingestion in two ways:

### 1. Direct Volume Mounting (Recommended for Real-World Testing)
If you have local copies of these files (or want to use public security datasets from SecRepo or UNSW-NB15), you can mount them directly to the `kafka-producer` container within `docker-compose.yml`:

```yaml
kafka-producer:
  volumes:
    - ./data/conn.log:/data/conn.log:ro   # Mounts your local conn.log
  environment:
    LOG_FORMAT: auto                      # Options: auto | zeek_tsv | zeek_json | suricata
    RECORDS_PER_SECOND: "2000"            # Emits 2,000 events per second
```

### 2. Automated Synthetic Generation (Zero-Touch Cold Start)
If this directory is empty (or files are omitted), the `kafka-producer` automatically detects the absence of raw files and falls back to generating **synthetic, high-fidelity Zeek-compatible log streams** so that you can evaluate the Spark Streaming and K-Means anomaly detection pipelines instantly.

---

## 🌐 External Dataset Recommendations & Downloads

To replicate the scale of this dataset using public sources, we recommend the following professional resources:

1. **SecRepo Security Datasets**
   - **Focus:** High-fidelity Zeek `conn.log` streams.
   - **Download:** [SecRepo](https://www.secrepo.com/)
   - **Quick Command:**
     ```bash
     curl -O https://www.secrepo.com/maccdc2012/conn.log.gz
     gunzip conn.log.gz
     mv conn.log ./data/conn.log
     ```

2. **UNSW-NB15 Dataset**
   - **Focus:** Cyber attack categories and normal traffic mixes.
   - **Download:** [UNSW-NB15 Project Page](https://research.unsw.edu.au/projects/unsw-nb15-dataset)

3. **CIC-IDS-2017 Dataset**
   - **Focus:** Modern network threats in standard CSV/JSON format.
   - **Conversion:** Download from Kaggle and execute the conversion script: `python scripts/csv_to_zeek_json.py`.

---
*For a detailed operational analysis of how Spark parses these schemas, refer to the [Spark Streaming Pipeline Guide](../docs/Spark_SIEM_Pipeline_Detailed_Analysis.md).*

---

## 🔗 Navigation & Links
*   ⬅️ **[Back to Root README](../README.md)**
*   📂 **[Go to Technical Documentation Library](../docs/)**
