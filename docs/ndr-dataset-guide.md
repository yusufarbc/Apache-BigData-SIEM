# NDR (Network Detection & Response) — Zeek/Suricata Veri Seti Kılavuzu

Bu dosya, gerçek ağ verisiyle sistemi beslemek için önerilen kaynakları ve
indirme adımlarını açıklar.

---

## Önerilen Veri Setleri

### 1. SecRepo — Zeek conn.log (En Hızlı Başlangıç)

| Özellik       | Değer |
|---------------|-------|
| Format        | Zeek TSV / JSON |
| İçerik        | HTTP, DNS, SSH, FTP bağlantıları |
| Boyut         | ~50 MB – 2 GB |
| URL           | https://www.secrepo.com/ |

```bash
# Örnek (küçük örnek veri seti):
curl -O https://www.secrepo.com/maccdc2012/conn.log.gz
gunzip conn.log.gz
# → /path/to/conn.log
```

---

### 2. UNSW-NB15 (Suricata/Zeek formatında hazır)

| Özellik       | Değer |
|---------------|-------|
| Format        | CSV → JSON'a dönüştürülmeli |
| İçerik        | 9 farklı saldırı türü + normal trafik |
| URL           | https://research.unsw.edu.au/projects/unsw-nb15-dataset |

---

### 3. CIC-IDS-2017 (Kaggle)

| Özellik       | Değer |
|---------------|-------|
| Format        | CSV (Zeek benzeri sütunlar) |
| URL           | https://www.kaggle.com/datasets/cicdataset/cicids2017 |

CSV'yi Zeek JSON formatına dönüştürmek için `scripts/csv_to_zeek_json.py` kullan.

---

### 4. MAWI Working Group (Gerçek İnternet Trafiği)

| Özellik       | Değer |
|---------------|-------|
| Format        | PCAP → Zeek ile işle |
| URL           | https://mawi.wide.ad.jp/mawi/ |

```bash
zeek -r capture.pcap local
# → conn.log otomatik üretilir
```

---

## Veriyi Sisteme Bağlama

`docker-compose.yml` içindeki `kafka-producer` servisine volume mount ekle:

```yaml
kafka-producer:
  volumes:
    - /host/path/to/conn.log:/data/conn.log:ro   # ← buraya kendi yolunu yaz
  environment:
    LOG_FORMAT: auto      # zeek_tsv | zeek_json | suricata | synthetic
    RECORDS_PER_SECOND: "200"
```

Mount yoksa sistem otomatik olarak **sentetik** Zeek-uyumlu veri üretir.

---

## K-Means Parametre Önerisi

| Parametre           | Değer   | Açıklama |
|---------------------|---------|----------|
| `KMEANS_K`          | 8       | Küme sayısı — karmaşık trafik için 10-12 dene |
| `COLD_START_ROWS`   | 5000    | Baseline eğitimi için gereken min. kayıt |
| `ANOMALY_THRESHOLD` | 4.5     | Düşürürsen daha fazla alarm, artırırsan daha az |

---

## Saldırı Simülasyonu (Demo)

```bash
# Tüm saldırı tiplerini enjekte et:
docker exec kafka-producer python attack_injector.py all

# Sadece port tarama:
docker exec kafka-producer python attack_injector.py portscan

# Sadece veri sızdırma:
docker exec kafka-producer python attack_injector.py exfiltration

# DDoS simülasyonu:
docker exec kafka-producer python attack_injector.py ddos

# C2 beacon:
docker exec kafka-producer python attack_injector.py c2
```

Enjeksiyondan sonra Superset → **"NDR: SOC Analyst — Anomaly Monitor"** dashboard'unda
kırmızı alertlerin düşmesini izle.
