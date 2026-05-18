# 📡 NDR (Network Detection & Response) — Zeek/Suricata Dataset Guide

This document outlines the recommended external security datasets, installation steps, online clustering hyperparameters, and cyber attack simulation scripts to feed real-world network traffic logs into the **Apache Big Data SIEM & NDR** pipeline.

---

## 🌐 Recommended Datasets for Scaling

For advanced cybersecurity benchmarking and scalability testing, we recommend integrating the following high-fidelity open-source datasets:

### 1. SecRepo — Zeek conn.log (Enables Quick Verification)

| Feature | Specification / Value |
| :--- | :--- |
| **Log Format** | Zeek TSV / JSON |
| **Event Focus** | Real-world HTTP, DNS, SSH, FTP connections |
| **Uncompressed Size** | ~50 MB to 2 GB |
| **Download Portal** | [SecRepo.com](https://www.secrepo.com/) |

```bash
# Example download for quick, small-scale validation:
curl -O https://www.secrepo.com/maccdc2012/conn.log.gz
gunzip conn.log.gz
mv conn.log ./data/conn.log
```

---

### 2. UNSW-NB15 (Standard Cyber Threat Benchmark)

| Feature | Specification / Value |
| :--- | :--- |
| **Log Format** | CSV (Convert to JSON/TSV) |
| **Event Focus** | 9 distinct cyber attack vectors mixed with normal traffic profiles |
| **Download Portal** | [UNSW-NB15 Dataset](https://research.unsw.edu.au/projects/unsw-nb15-dataset) |

*Conversion Tip:* Convert the CSV headers to matching Zeek JSON properties using `scripts/csv_to_zeek_json.py` to test parsing pathways.

---

### 3. CIC-IDS-2017 (Modern Intrusion Detection)

| Feature | Specification / Value |
| :--- | :--- |
| **Log Format** | Multi-Protocol CSV |
| **Download Portal** | [Kaggle CIC-IDS-2017](https://www.kaggle.com/datasets/cicdataset/cicids2017) |

---

### 4. MAWI Working Group (Active Real-World Internet Traffic)

| Feature | Specification / Value |
| :--- | :--- |
| **Log Format** | PCAP Capture (Preprocess using Zeek) |
| **Download Portal** | [MAWI WIDE Repository](https://mawi.wide.ad.jp/mawi/) |

```bash
# Parse raw PCAP files locally using the Zeek CLI:
zeek -r capture.pcap local
# → Instantly generates conn.log, dns.log, and http.log in your current folder
```

---

## 🔌 Mounting Datasets to Ingestion Layer

To pipe your downloaded log datasets directly into the Kafka broker, map the file location as a volume mount inside the `kafka-producer` container inside `docker-compose.yml`:

```yaml
kafka-producer:
  volumes:
    - /absolute/path/to/your/conn.log:/data/conn.log:ro   # Map host path to container
  environment:
    LOG_FORMAT: auto                                      # Supported: auto | zeek_tsv | zeek_json | suricata | synthetic
    RECORDS_PER_SECOND: "500"                            # Controls ingestion rate (EPS)
```

> [!NOTE]
> If no file is mounted or the file is missing, the `kafka-producer` falls back to **synthetic log generation**, creating realistic, normal Zeek connections dynamically to keep the analytics running.

---

## ⚙️ Streaming K-Means Hyperparameters

The real-time ML engine (`streaming_kmeans.py`) utilizes online scaling and clustering to identify anomalous records. We recommend the following base parameter values for optimal alert fidelity:

| Hyperparameter | Recommended Value | Operational Description |
| :--- | :---: | :--- |
| **`KMEANS_K`** | `8` | Number of clusters. For highly complex corporate backbones, test `10` or `12`. |
| **`COLD_START_ROWS`** | `5000` | Minimum baseline events required to train the initial cluster models before anomaly alerts trigger. |
| **`ANOMALY_THRESHOLD`** | `4.5` | Sensitivity threshold (in standard deviations from centroid). Lowering this triggers more alarms; raising it filters out false positives. |

---

## ⚔️ Cyber Attack Simulation & Verification (Demo Room)

To validate the real-time scoring and watch Superset alarm metrics trigger under pressure, you can execute the interactive `attack_injector.py` script. The script generates realistic attack vectors directly into the Kafka stream:

```bash
# Inject all simulated vectors (DDoS, Portscan, C2, Data Exfiltration)
docker exec kafka-producer python attack_injector.py all

# Inject Port Scan Simulation (rapid connections to randomized destination ports)
docker exec kafka-producer python attack_injector.py portscan

# Inject Data Exfiltration (large payloads over unusual connection ports)
docker exec kafka-producer python attack_injector.py exfiltration

# Inject Distributed Denial of Service (DDoS) flood patterns
docker exec kafka-producer python attack_injector.py ddos

# Inject Command & Control (C2) beacon signals (frequent periodic heartbeats)
docker exec kafka-producer python attack_injector.py c2
```

After running an injection, navigate to **Apache Superset** ([http://localhost:8088](http://localhost:8088)) and watch the threat dashboard visualize the real-time anomaly scores!
