"""
Attack Injector — NDR Demo & Presentation Tool
===============================================
Injects realistic synthetic attack patterns directly into the Kafka topic
`real_network_logs` to demonstrate anomaly detection during a live demo.

Usage (from host):
    docker exec -it <producer-container> python attack_injector.py [ATTACK_TYPE]

    ATTACK_TYPE: portscan | exfiltration | ddos | all  (default: all)

Or via spark-submit / docker run:
    docker run --rm --network siem-network \\
        -e KAFKA_BOOTSTRAP_SERVERS=kafka-broker:9092 \\
        ndr-producer python attack_injector.py all
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker:9092")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC",              "real_network_logs")


def _rand_ip() -> str:
    return f"{random.randint(10,192)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def connect(retries: int = 10) -> KafkaProducer:
    for i in range(1, retries + 1):
        try:
            p = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                acks=1,
            )
            print(f"[INJECTOR] Connected to {KAFKA_BOOTSTRAP}")
            return p
        except NoBrokersAvailable:
            print(f"[INJECTOR] Kafka not ready ({i}/{retries})…")
            time.sleep(3)
    sys.exit(1)


# ── Attack scenarios ──────────────────────────────────────────────────────────

def inject_portscan(producer: KafkaProducer, n: int = 500) -> None:
    """
    Simulates a fast Nmap-style horizontal port scan:
      - single source IP hitting many destination ports
      - tiny/zero bytes, REJ/S0 connection state
      - very short durations (< 10ms)
    This creates outlier vectors far from any normal centroid.
    """
    attacker = "192.168.100.1"
    target   = _rand_ip()
    print(f"\n[INJECTOR] ── PORT SCAN: {attacker} → {target} ({n} probes) ──")
    sent = 0
    for port in random.sample(range(1, 65536), min(n, 65535)):
        record = {
            "ts":        _now_ts(),
            "uid":       f"SCAN_{port:05d}",
            "id.orig_h": attacker,
            "id.orig_p": random.randint(49152, 65535),
            "id.resp_h": target,
            "id.resp_p": port,
            "proto":     "tcp",
            "service":   None,
            "duration":  round(random.uniform(0.0001, 0.005), 6),
            "orig_bytes": random.randint(40, 60),
            "resp_bytes": 0,
            "conn_state": random.choice(["REJ", "S0", "RSTOS0"]),
            "orig_pkts":  1,
            "resp_pkts":  0,
            "is_attack":  True,
        }
        producer.send(KAFKA_TOPIC, value=record)
        sent += 1
        if sent % 100 == 0:
            print(f"  [INJECTOR] Port scan: {sent}/{n} probes sent")
        time.sleep(0.005)          # 200 probes/sec — very fast
    producer.flush()
    print(f"  [INJECTOR] Port scan complete: {sent} records injected.")


def inject_exfiltration(producer: KafkaProducer, n: int = 50) -> None:
    """
    Simulates data exfiltration:
      - enormous orig_bytes (tens of MB)
      - long duration (minutes to hours)
      - unusual destination (external IP)
    """
    src = "10.0.0.50"
    print(f"\n[INJECTOR] ── DATA EXFILTRATION from {src} ({n} flows) ──")
    for i in range(n):
        record = {
            "ts":        _now_ts(),
            "uid":       f"EXFIL_{i:04d}",
            "id.orig_h": src,
            "id.orig_p": random.randint(49152, 65535),
            "id.resp_h": _rand_ip(),
            "id.resp_p": random.choice([443, 80, 8443, 4444, 1337]),
            "proto":     "tcp",
            "service":   "https",
            "duration":  round(random.uniform(300.0, 7200.0), 2),
            "orig_bytes": random.randint(5_000_000, 100_000_000),
            "resp_bytes": random.randint(100, 2_000),
            "conn_state": "SF",
            "orig_pkts":  random.randint(5000, 80000),
            "resp_pkts":  random.randint(5, 50),
            "is_attack":  True,
        }
        producer.send(KAFKA_TOPIC, value=record)
        print(f"  [INJECTOR] Exfil flow {i+1}/{n}: "
              f"{record['orig_bytes']:,} bytes → {record['id.resp_h']}:{record['id.resp_p']} "
              f"over {record['duration']:.0f}s")
        time.sleep(0.1)
    producer.flush()
    print(f"  [INJECTOR] Exfiltration complete: {n} anomalous flows injected.")


def inject_ddos(producer: KafkaProducer, n: int = 1000) -> None:
    """
    Simulates a volumetric DDoS from many sources to one target:
      - many source IPs, single destination
      - tiny bytes, S0/REJ state
    """
    target = "10.0.0.1"
    print(f"\n[INJECTOR] ── DDoS → {target} ({n} flows) ──")
    sent = 0
    for i in range(n):
        record = {
            "ts":        _now_ts(),
            "uid":       f"DDOS_{i:06d}",
            "id.orig_h": _rand_ip(),
            "id.orig_p": random.randint(49152, 65535),
            "id.resp_h": target,
            "id.resp_p": random.choice([80, 443, 53]),
            "proto":     random.choice(["tcp", "udp"]),
            "service":   None,
            "duration":  round(random.uniform(0.001, 0.3), 4),
            "orig_bytes": random.randint(60, 300),
            "resp_bytes": 0,
            "conn_state": random.choice(["S0", "REJ"]),
            "orig_pkts":  random.randint(1, 3),
            "resp_pkts":  0,
            "is_attack":  True,
        }
        producer.send(KAFKA_TOPIC, value=record)
        sent += 1
        if sent % 200 == 0:
            print(f"  [INJECTOR] DDoS: {sent}/{n} flows sent")
        time.sleep(0.002)          # 500 flows/sec
    producer.flush()
    print(f"  [INJECTOR] DDoS complete: {sent} records injected.")


def inject_c2_beacon(producer: KafkaProducer, n: int = 100) -> None:
    """
    Simulates C2 beaconing:
      - periodic, small, very regular connections to a single external IP
      - always same dest port, very consistent timing
    """
    c2_ip   = "185.220.101.42"
    bot_ip  = "10.10.5.100"
    c2_port = 4444
    print(f"\n[INJECTOR] ── C2 BEACON {bot_ip} ↔ {c2_ip}:{c2_port} ({n} beacons) ──")
    for i in range(n):
        record = {
            "ts":        _now_ts(),
            "uid":       f"C2_{i:04d}",
            "id.orig_h": bot_ip,
            "id.orig_p": random.randint(49152, 65535),
            "id.resp_h": c2_ip,
            "id.resp_p": c2_port,
            "proto":     "tcp",
            "service":   None,
            "duration":  round(random.uniform(0.05, 0.15), 4),  # very consistent
            "orig_bytes": random.randint(120, 180),              # very small, regular
            "resp_bytes": random.randint(80, 120),
            "conn_state": "SF",
            "orig_pkts":  2,
            "resp_pkts":  2,
            "is_attack":  True,
        }
        producer.send(KAFKA_TOPIC, value=record)
        if i % 20 == 0:
            print(f"  [INJECTOR] C2 beacon {i+1}/{n}")
        time.sleep(0.1)            # ~10 beacons/sec
    producer.flush()
    print(f"  [INJECTOR] C2 beacon complete: {n} records injected.")


# ── Entry point ───────────────────────────────────────────────────────────────

ATTACKS = {
    "portscan":     inject_portscan,
    "exfiltration": inject_exfiltration,
    "ddos":         inject_ddos,
    "c2":           inject_c2_beacon,
}


def main() -> None:
    attack_type = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()

    producer = connect()

    print("\n" + "═" * 60)
    print("  NDR Attack Injector — Live Demo Mode")
    print("═" * 60)

    if attack_type == "all":
        selected = list(ATTACKS.items())
    elif attack_type in ATTACKS:
        selected = [(attack_type, ATTACKS[attack_type])]
    else:
        print(f"[INJECTOR] Unknown attack type '{attack_type}'. "
              f"Choose from: {', '.join(ATTACKS)} or 'all'")
        sys.exit(1)

    for name, fn in selected:
        print(f"\n[INJECTOR] Starting attack: {name.upper()}")
        fn(producer)
        print(f"[INJECTOR] Attack '{name}' complete. "
              f"Watch Superset dashboard for anomalies!\n")
        time.sleep(2)

    print("\n[INJECTOR] All attacks injected. "
          "Check siem.network_anomalies in Hive / Superset.")


if __name__ == "__main__":
    main()
