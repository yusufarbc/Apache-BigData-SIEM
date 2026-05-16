"""
NDR Kafka Producer — Zeppelin / Manuel Kullanim icin
=====================================================
data/conn.log dosyasini (Zeek TSV formatinda) satirlik okuyup
Kafka real_network_logs topic'ine JSON olarak basar.

Calistirma (host makineden):
    python scripts/producer.py

Calistirma (container icinden):
    docker exec kafka-producer python /app/kafka_producer.py

Env degiskenleri:
    KAFKA_BOOTSTRAP   -> varsayilan: localhost:9092
    CONN_LOG_PATH     -> varsayilan: data/conn.log
    RPS               -> Saniyede kac satir (varsayilan: 50)
"""

import json
import os
import time
import sys

try:
    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable
except ImportError:
    print("[HATA] kafka-python yuklu degil. Calistir: pip install kafka-python")
    sys.exit(1)

# ── Konfigurasyon ──────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
CONN_LOG_PATH   = os.getenv("CONN_LOG_PATH",   "data/conn.log")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC",      "real_network_logs")
RPS             = int(os.getenv("RPS",          "50"))
LOOP            = os.getenv("LOOP", "false").lower() == "true"

INTERVAL = 1.0 / RPS

# ── Zeek TSV parser ────────────────────────────────────────────────────────────

NUMERIC_FIELDS = {
    "id.orig_p", "id.resp_p", "orig_bytes", "resp_bytes",
    "orig_pkts", "resp_pkts", "orig_ip_bytes", "resp_ip_bytes",
    "missed_bytes",
}
FLOAT_FIELDS = {"duration", "ts"}

def parse_zeek_tsv(path: str):
    """Zeek conn.log TSV dosyasini satirlik parse eder, dict uretir."""
    fields = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line or line.startswith("#separator"):
                continue
            if line.startswith("#fields"):
                fields = line.split("\t")[1:]
                continue
            if line.startswith("#"):
                continue
            if not fields:
                continue

            parts = line.split("\t")
            record = {}
            for key, val in zip(fields, parts):
                if val in ("-", "(empty)", ""):
                    record[key] = None
                elif key in FLOAT_FIELDS:
                    try:
                        record[key] = float(val)
                    except ValueError:
                        record[key] = None
                elif key in NUMERIC_FIELDS:
                    try:
                        record[key] = int(val)
                    except ValueError:
                        record[key] = None
                else:
                    record[key] = val

            # Streaming K-Means'in bekledigindeki alan adlarina normalize et
            record["dest_port"] = record.pop("id.resp_p", None)
            record["src_port"]  = record.pop("id.orig_p", None)
            record["src_ip"]    = record.pop("id.orig_h", None)
            record["dest_ip"]   = record.pop("id.resp_h", None)
            record["is_attack"] = False
            yield record


# ── Kafka baglantisi ───────────────────────────────────────────────────────────

def connect(retries: int = 15, delay: float = 3.0) -> KafkaProducer:
    for attempt in range(1, retries + 1):
        try:
            p = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                acks=1,
                linger_ms=5,
                batch_size=16_384,
            )
            print(f"[PRODUCER] Kafka'ya baglandi: {KAFKA_BOOTSTRAP}")
            return p
        except NoBrokersAvailable:
            print(f"[PRODUCER] Kafka hazir degil ({attempt}/{retries}), {delay}s bekleniyor...")
            time.sleep(delay)
    print("[PRODUCER] Kafka'ya baglanamadi. Cikiliyor.")
    sys.exit(1)


# ── Ana dongu ──────────────────────────────────────────────────────────────────

def main() -> None:
    if not os.path.isfile(CONN_LOG_PATH):
        print(f"[HATA] Dosya bulunamadi: {CONN_LOG_PATH}")
        sys.exit(1)

    producer = connect()
    print(f"[PRODUCER] Dosya: {CONN_LOG_PATH}")
    print(f"[PRODUCER] Topic: {KAFKA_TOPIC}  |  Hiz: {RPS} satir/sn")
    print("[PRODUCER] Veri akisi baslatildi... (Ctrl+C ile dur)")

    sent = 0
    t_start = time.time()

    while True:
        for record in parse_zeek_tsv(CONN_LOG_PATH):
            t0 = time.time()
            producer.send(KAFKA_TOPIC, value=record)
            sent += 1

            if sent % 5_000 == 0:
                elapsed = time.time() - t_start
                print(f"[PRODUCER] {sent:,} satir gonderildi | "
                      f"ort. {sent/elapsed:.0f} satir/sn")

            elapsed_send = time.time() - t0
            sleep_for = INTERVAL - elapsed_send
            if sleep_for > 0:
                time.sleep(sleep_for)

        if not LOOP:
            break
        print("[PRODUCER] Dosya bitti, basa donuluyor (LOOP=true)...")

    producer.flush()
    print(f"[PRODUCER] Tamamlandi. Toplam gonderilen: {sent:,} satir")


if __name__ == "__main__":
    main()
