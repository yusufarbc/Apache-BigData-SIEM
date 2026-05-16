"""
NDR Kafka Producer — Zeek conn.log / Suricata eve.json Simulator
=================================================================
Reads a real Zeek conn.log or Suricata eve.json dataset (or falls back to a
built-in synthetic generator when no dataset file is mounted) and streams
records to the Kafka topic `real_network_logs` at a configurable rate.

Environment Variables:
  KAFKA_BOOTSTRAP_SERVERS   default: kafka-broker:9092
  KAFKA_TOPIC               default: real_network_logs
  RECORDS_PER_SECOND        default: 100
  DATA_FILE                 default: /data/conn.log  (Zeek JSON or Suricata eve.json)
  LOG_FORMAT                auto-detected: zeek | suricata | synthetic
  LOOP                      default: true  (replay file in loop)
"""

import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Iterator

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# ── Configuration ─────────────────────────────────────────────────────────────

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker:9092")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC",              "real_network_logs")
RPS             = int(os.getenv("RECORDS_PER_SECOND",   "100"))
DATA_FILE       = os.getenv("DATA_FILE",                "/data/conn.log")
LOG_FORMAT      = os.getenv("LOG_FORMAT",               "auto")   # zeek|suricata|synthetic|auto
LOOP            = os.getenv("LOOP", "true").lower() == "true"

# ── Zeek conn.log field names (TSV header) ─────────────────────────────────────
# We support both TSV (#fields …) and JSON-Lines formats.
ZEEK_FIELDS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes",
    "conn_state", "local_orig", "local_resp", "missed_bytes",
    "history", "orig_pkts", "orig_ip_bytes", "resp_pkts", "resp_ip_bytes",
    "tunnel_parents",
]


# ── Synthetic data generator (fallback) ───────────────────────────────────────

SERVICES   = ["http", "https", "dns", "ssh", "ftp", "smtp", "rdp", None]
PROTOS     = ["tcp", "udp", "icmp"]
STATES     = ["SF", "S0", "REJ", "RSTO", "RSTOS0", "OTH"]
PRIV_PORTS = [22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 8080, 8443]

def _rand_ip() -> str:
    return f"{random.randint(10,192)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def _normal_record(ts: float) -> dict:
    port = random.choice(PRIV_PORTS + list(range(49152, 65535, 100)))
    return {
        "ts":          ts,
        "uid":         f"C{''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEF0123456789', k=12))}",
        "id.orig_h":   _rand_ip(),
        "id.orig_p":   random.randint(49152, 65535),
        "id.resp_h":   _rand_ip(),
        "id.resp_p":   port,
        "proto":       random.choice(PROTOS),
        "service":     random.choice(SERVICES),
        "duration":    round(random.expovariate(1 / 0.5), 4),
        "orig_bytes":  random.randint(40, 5_000),
        "resp_bytes":  random.randint(40, 20_000),
        "conn_state":  random.choice(STATES),
        "orig_pkts":   random.randint(1, 30),
        "resp_pkts":   random.randint(1, 50),
        "is_attack":   False,
    }

def _attack_record(ts: float, attack_type: str = "portscan") -> dict:
    """Generate a synthetic attack record that will be an outlier for K-Means."""
    if attack_type == "portscan":
        # Nmap-style: many connections, tiny bytes, short duration, many ports
        return {
            "ts":          ts,
            "uid":         f"ATTACK_{''.join(random.choices('ABCDEF0123456789', k=10))}",
            "id.orig_h":   "192.168.100.1",
            "id.orig_p":   random.randint(49152, 65535),
            "id.resp_h":   _rand_ip(),
            "id.resp_p":   random.randint(1, 1024),
            "proto":       "tcp",
            "service":     None,
            "duration":    round(random.uniform(0.0001, 0.01), 6),
            "orig_bytes":  random.randint(40, 60),
            "resp_bytes":  0,
            "conn_state":  "REJ",
            "orig_pkts":   1,
            "resp_pkts":   0,
            "is_attack":   True,
        }
    elif attack_type == "exfiltration":
        # Large data transfer: enormous resp_bytes, long duration
        return {
            "ts":          ts,
            "uid":         f"EXFIL_{''.join(random.choices('ABCDEF0123456789', k=10))}",
            "id.orig_h":   "10.0.0.50",
            "id.orig_p":   random.randint(49152, 65535),
            "id.resp_h":   _rand_ip(),
            "id.resp_p":   443,
            "proto":       "tcp",
            "service":     "https",
            "duration":    round(random.uniform(120.0, 3600.0), 2),
            "orig_bytes":  random.randint(5_000_000, 50_000_000),
            "resp_bytes":  random.randint(100, 1_000),
            "conn_state":  "SF",
            "orig_pkts":   random.randint(5000, 50000),
            "resp_pkts":   random.randint(10, 100),
            "is_attack":   True,
        }
    else:  # ddos
        return {
            "ts":          ts,
            "uid":         f"DDOS_{''.join(random.choices('ABCDEF0123456789', k=10))}",
            "id.orig_h":   _rand_ip(),
            "id.orig_p":   random.randint(49152, 65535),
            "id.resp_h":   "10.0.0.1",
            "id.resp_p":   80,
            "proto":       "tcp",
            "service":     "http",
            "duration":    round(random.uniform(0.001, 0.5), 4),
            "orig_bytes":  random.randint(60, 200),
            "resp_bytes":  random.randint(0, 100),
            "conn_state":  random.choice(["S0", "REJ"]),
            "orig_pkts":   1,
            "resp_pkts":   0,
            "is_attack":   True,
        }


def synthetic_stream() -> Iterator[dict]:
    """Infinite generator: 95% normal traffic, 5% attack traffic."""
    print("[PRODUCER] Running in SYNTHETIC mode (no dataset file found).")
    while True:
        ts = datetime.now(timezone.utc).timestamp()
        if random.random() < 0.05:
            attack = random.choice(["portscan", "exfiltration", "ddos"])
            yield _attack_record(ts, attack)
        else:
            yield _normal_record(ts)


# ── File-based stream readers ──────────────────────────────────────────────────

def _detect_format(path: str) -> str:
    """Detect whether the file is Zeek TSV, Zeek JSON-lines, or Suricata eve.json."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
                if "event_type" in obj:
                    return "suricata"
                return "zeek_json"
            except json.JSONDecodeError:
                return "zeek_tsv"
    return "zeek_tsv"


def zeek_tsv_stream(path: str) -> Iterator[dict]:
    """Parse Zeek conn.log in TSV format (with #fields header)."""
    fields = ZEEK_FIELDS
    while True:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#fields"):
                    fields = line.split("\t")[1:]
                    continue
                if line.startswith("#"):
                    continue
                parts = line.split("\t")
                record = dict(zip(fields, parts))
                # Normalize key names
                record["id.orig_h"] = record.pop("id.orig_h", record.get("id_orig_h", ""))
                record["id.resp_h"] = record.pop("id.resp_h", record.get("id_resp_h", ""))
                record["id.orig_p"] = record.pop("id.orig_p", record.get("id_orig_p", 0))
                record["id.resp_p"] = record.pop("id.resp_p", record.get("id_resp_p", 0))
                # Cast numeric fields
                for num_field in ("duration", "orig_bytes", "resp_bytes",
                                  "orig_pkts", "resp_pkts", "orig_ip_bytes", "resp_ip_bytes"):
                    v = record.get(num_field, "-")
                    try:
                        record[num_field] = float(v) if "." in str(v) else int(v)
                    except (ValueError, TypeError):
                        record[num_field] = 0
                record["is_attack"] = False
                yield record
        if not LOOP:
            break


def zeek_json_stream(path: str) -> Iterator[dict]:
    """Parse Zeek conn.log in JSON-Lines format."""
    while True:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    record = json.loads(line)
                    record["is_attack"] = False
                    yield record
                except json.JSONDecodeError:
                    continue
        if not LOOP:
            break


def suricata_stream(path: str) -> Iterator[dict]:
    """Parse Suricata eve.json — only 'flow' event types map to Zeek conn semantics."""
    while True:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    etype = ev.get("event_type", "")
                    if etype not in ("flow", "alert"):
                        continue
                    flow = ev.get("flow", {})
                    record = {
                        "ts":        ev.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        "uid":       ev.get("flow_id", ""),
                        "id.orig_h": ev.get("src_ip", ""),
                        "id.orig_p": ev.get("src_port", 0),
                        "id.resp_h": ev.get("dest_ip", ""),
                        "id.resp_p": ev.get("dest_port", 0),
                        "proto":     ev.get("proto", "").lower(),
                        "service":   ev.get("app_proto", None),
                        "duration":  flow.get("age", 0),
                        "orig_bytes": flow.get("bytes_toserver", 0),
                        "resp_bytes": flow.get("bytes_toclient", 0),
                        "orig_pkts":  flow.get("pkts_toserver", 0),
                        "resp_pkts":  flow.get("pkts_toclient", 0),
                        "conn_state": "SF" if etype == "flow" else "REJ",
                        "is_attack":  etype == "alert",
                        "alert_signature": ev.get("alert", {}).get("signature", ""),
                    }
                    yield record
                except json.JSONDecodeError:
                    continue
        if not LOOP:
            break


# ── Kafka helpers ──────────────────────────────────────────────────────────────

def connect_kafka(retries: int = 20, delay: float = 5.0) -> KafkaProducer:
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                acks="all",
                retries=5,
                linger_ms=10,
                batch_size=32_768,
                compression_type="gzip",
            )
            print(f"[PRODUCER] Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return producer
        except NoBrokersAvailable:
            print(f"[PRODUCER] Kafka not ready — attempt {attempt}/{retries}. Retrying in {delay}s…")
            time.sleep(delay)
    print("[PRODUCER] Could not connect to Kafka. Exiting.")
    sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    producer = connect_kafka()
    data_dir = os.path.dirname(DATA_FILE)
    
    # Get all .log files in the directory
    log_files = [f for f in os.listdir(data_dir) if f.endswith(".log")]
    print(f"[PRODUCER] Found {len(log_files)} log files in {data_dir}")

    # For simplicity in this version, we will process the main DATA_FILE and common extras
    # In a more advanced version, we'd use threading to stream all at once.
    # We will prioritize: conn.log, http.log, dns.log, ssl.log
    # Focus on the most important high-volume logs for SIEM
    priority_files = ["conn.log", "http.log", "dns.log", "ssl.log", "ssh.log", "files.log", "weird.log"]
    files_to_stream = [f for f in priority_files if f in log_files]
    print(f"[PRODUCER] Total files to stream: {len(files_to_stream)}")

    print(f"[PRODUCER] Streaming files: {files_to_stream}")

    sent_total = 0
    t_start = time.time()
    
    # We'll use a round-robin or sequential approach for simplicity
    # Real systems would use a process per file.
    streams = {}
    for fname in files_to_stream:
        fpath = os.path.join(data_dir, fname)
        fmt = _detect_format(fpath)
        # Determine topic: e.g. conn.log -> real_network_logs, http.log -> web-logs
        topic = KAFKA_TOPIC
        if "http" in fname: topic = "web-logs"
        elif "dns" in fname: topic = "dns-logs"
        elif "ssl" in fname: topic = "ssl-logs"
        elif "ssh" in fname: topic = "ssh-logs"
        elif "conn" in fname: topic = "real_network_logs"
        
        if fmt == "zeek_tsv":
            streams[fname] = (zeek_tsv_stream(fpath), topic)
        elif fmt == "zeek_json":
            streams[fname] = (zeek_json_stream(fpath), topic)
        elif fmt == "suricata":
            streams[fname] = (suricata_stream(fpath), topic)
        else:
            continue

    print(f"[PRODUCER] Starting multi-stream @ {RPS} records/sec total")

    interval = 1.0 / RPS
    while True:
        for fname, (stream, topic) in streams.items():
            try:
                record = next(stream)
                if not record: continue
                record["source_file"] = fname
                producer.send(topic, value=record)
                sent_total += 1
                
                if sent_total % 1000 == 0:
                    elapsed = time.time() - t_start
                    print(f"[PRODUCER] Sent {sent_total:,} records | Last file: {fname} | Topic: {topic} | Speed: {int(sent_total/max(1,elapsed))} eps")
                
                # Optimized sleep: adjust if RPS is very high
                if RPS < 1000:
                    time.sleep(interval / len(streams))
            except (StopIteration, Exception) as e:
                if isinstance(e, StopIteration):
                    if not LOOP:
                        print(f"[PRODUCER] Finished file: {fname}")
                        del streams[fname]
                        break
                else:
                    print(f"[PRODUCER] Error in {fname}: {str(e)}")
                    continue
            if not streams:
                break
        if not streams:
            break

    producer.flush()
    print(f"[PRODUCER] Done. Total records sent: {sent_total:,}")


if __name__ == "__main__":
    main()
