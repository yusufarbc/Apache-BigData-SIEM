#!/usr/bin/env python3
"""
Generate a Mermaid architecture diagram from docker-compose.yml
and inject it into README.md automatically.

Usage:
    python scripts/generate_mermaid.py

Reads docker-compose.yml from the project root, generates a Mermaid diagram
showing services grouped by role, dependencies, networks, and ports,
then updates the README.md between the marker comments.
"""

import yaml
import re
import sys
import io
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── Service-to-Layer Mapping ──────────────────────────────────────────────
# Customize this mapping when adding new services to docker-compose.yml.
# The key is the service name in docker-compose.yml,
# the value is (layer_key, display_label, extra_info).

LAYER_DEFINITIONS = {
    "FLOG":  {"icon": "📡", "title": "Log Generators (Flog)",    "color": "#00b894"},
    "KAFKA": {"icon": "📨", "title": "Messaging Layer",          "color": "#e17055"},
    "SPARK": {"icon": "⚙️",  "title": "Processing Layer (Spark)", "color": "#fdcb6e"},
    "HIVE":  {"icon": "🗂️",  "title": "Data Cataloging (Hive)",   "color": "#74b9ff"},
    "HDFS":  {"icon": "💾", "title": "Distributed Storage (HDFS)","color": "#a29bfe"},
    "DB":    {"icon": "🗄️",  "title": "Unified Database",         "color": "#636e72"},
    "VIZ":   {"icon": "📊", "title": "Analytics & Visualization", "color": "#fd79a8"},
}

SERVICE_LAYER_MAP = {
    "namenode":         "HDFS",
    "datanode-1":       "HDFS",
    "datanode-2":       "HDFS",
    "postgres":         "DB",
    "hive-metastore":   "HIVE",
    "hive-server2":     "HIVE",
    "kafka-broker":     "KAFKA",
    "spark-master":     "SPARK",
    "spark-worker-1":   "SPARK",
    "spark-worker-2":   "SPARK",
    "flog-web":         "FLOG",
    "flog-syslog":      "FLOG",
    "flog-app":         "FLOG",
    "superset":         "VIZ",
    "superset-redis":   "VIZ",
}

# ── Custom Data Flow Edges ────────────────────────────────────────────────
# These represent the SEMANTIC data flow in the architecture,
# not just depends_on relationships. Update these when adding new services.

CUSTOM_EDGES = [
    ('FW',   'KB',  '-->',  'web-logs'),
    ('FS',   'KB',  '-->',  'syslogs'),
    ('FA',   'KB',  '-->',  'app-logs'),
    ('KB',   'SM',  '-->',  'Stream Consume'),
    ('SM',   'SW1', '---',  ''),
    ('SM',   'SW2', '---',  ''),
    ('SM',   'NN',  '-->',  'Parquet Write'),
    ('NN',   'DN1', '---',  ''),
    ('NN',   'DN2', '---',  ''),
    ('HM',   'PG',  '-->',  'Metadata'),
    ('HS2',  'HM',  '-->',  'Thrift'),
    ('SM',   'HM',  '-.->',  'Schema Registry'),
    ('SUP',  'PG',  '-->',  'Superset DB'),
    ('SUP',  'HS2', '-->',  'SQL Query'),
    ('SUP',  'SRED','---',  ''),
]


def safe_node_id(service_name: str) -> str:
    """Convert a service name to a short Mermaid-safe node ID."""
    mapping = {
        "namenode":         "NN",
        "datanode-1":       "DN1",
        "datanode-2":       "DN2",
        "postgres":         "PG",
        "hive-metastore":   "HM",
        "hive-server2":     "HS2",
        "kafka-broker":     "KB",
        "spark-master":     "SM",
        "spark-worker-1":   "SW1",
        "spark-worker-2":   "SW2",
        "flog-web":         "FW",
        "flog-syslog":      "FS",
        "flog-app":         "FA",
        "superset":         "SUP",
        "superset-redis":   "SRED",
    }
    return mapping.get(service_name, service_name.upper().replace("-", "_"))


def get_host_ports(service_cfg: dict) -> str:
    """Extract host-side ports from a service config."""
    ports = service_cfg.get("ports", [])
    host_ports = []
    for p in ports:
        p_str = str(p)
        if ":" in p_str:
            host_port = p_str.split(":")[0]
            host_ports.append(f":{host_port}")
        else:
            host_ports.append(f":{p_str}")
    return " · ".join(host_ports) if host_ports else ""


def get_display_label(service_name: str, service_cfg: dict) -> str:
    """Build a rich display label for a service node."""
    # Build a nice name
    nice_name = service_name.replace("-", " ").title()

    # Get container name if different
    container = service_cfg.get("container_name", "")

    # Get port info
    ports = get_host_ports(service_cfg)

    # Get special info from environment
    env = service_cfg.get("environment", {})
    extra_lines = []

    if isinstance(env, dict):
        # Kafka: show mode
        if env.get("KAFKA_CFG_PROCESS_ROLES"):
            extra_lines.append("<b>KRaft Mode</b>")
        # Spark worker: show resources
        if env.get("SPARK_WORKER_MEMORY"):
            mem = env["SPARK_WORKER_MEMORY"]
            cores = env.get("SPARK_WORKER_CORES", "?")
            extra_lines.append(f"{mem} RAM · {cores} Cores")
        # Flog: show topic
        if env.get("KAFKA_TOPIC"):
            extra_lines.append(f"<i>{env['KAFKA_TOPIC']}</i>")
    elif isinstance(env, list):
        for item in env:
            if "SPARK_MASTER=" in str(item):
                pass  # handled by layer grouping

    # Build label
    parts = [nice_name]
    parts.extend(extra_lines)
    if ports:
        parts.append(ports)

    label = "<br/>".join(parts)

    # Use cylinder shape for databases
    is_db = ("postgres" in service_name.lower()) or ("metastore-db" in container.lower() if container else False)
    node_id = safe_node_id(service_name)

    if is_db:
        return f'{node_id}[("{label}")]'
    else:
        return f'{node_id}["{label}"]'


def generate_mermaid(compose_path: str) -> str:
    """Parse docker-compose.yml and generate a Mermaid diagram string."""
    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})

    # Group services by layer
    layers = {}
    for layer_key in LAYER_DEFINITIONS:
        layers[layer_key] = []

    for svc_name, svc_cfg in services.items():
        layer = SERVICE_LAYER_MAP.get(svc_name)
        if layer and layer in layers:
            layers[layer].append((svc_name, svc_cfg))

    # Build mermaid lines
    lines = ["graph TD"]

    # Subgraphs for each layer
    for layer_key, layer_def in LAYER_DEFINITIONS.items():
        svc_list = layers.get(layer_key, [])
        if not svc_list:
            continue

        icon = layer_def["icon"]
        title = layer_def["title"]
        lines.append(f'    subgraph {layer_key}["{icon} {title}"]')

        for svc_name, svc_cfg in svc_list:
            label = get_display_label(svc_name, svc_cfg)
            lines.append(f"        {label}")

        lines.append("    end")
        lines.append("")

    # Edges (semantic data flow)
    for src, dst, arrow, label_text in CUSTOM_EDGES:
        if label_text:
            lines.append(f'    {src} {arrow}|"{label_text}"| {dst}')
        else:
            lines.append(f"    {src} {arrow} {dst}")

    lines.append("")

    # Style each subgraph
    for layer_key, layer_def in LAYER_DEFINITIONS.items():
        color = layer_def["color"]
        lines.append(f"    style {layer_key} fill:#f8fafc,stroke:{color},color:#0f172a")

    return "\n".join(lines)


def update_readme(readme_path: str, mermaid_code: str) -> bool:
    """
    Inject mermaid_code into README.md between marker comments.

    Markers:
        <!-- ARCHITECTURE_DIAGRAM_START -->
        <!-- ARCHITECTURE_DIAGRAM_END -->

    Returns True if the file was updated, False if markers were not found.
    """
    readme = Path(readme_path)
    content = readme.read_text(encoding="utf-8")

    start_marker = "<!-- ARCHITECTURE_DIAGRAM_START -->"
    end_marker = "<!-- ARCHITECTURE_DIAGRAM_END -->"

    if start_marker not in content or end_marker not in content:
        return False

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )

    replacement = (
        f"{start_marker}\n"
        f"```mermaid\n"
        f"{mermaid_code}\n"
        f"```\n"
        f"{end_marker}"
    )

    new_content = pattern.sub(replacement, content)
    readme.write_text(new_content, encoding="utf-8")
    return True


def main():
    project_root = Path(__file__).resolve().parent.parent
    compose_path = project_root / "docker-compose.yml"
    readme_path = project_root / "README.md"

    if not compose_path.exists():
        print(f"ERROR: {compose_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Reading {compose_path.name}...")
    mermaid_code = generate_mermaid(str(compose_path))

    print("[+] Generated Mermaid diagram:")
    print(mermaid_code)

    if readme_path.exists():
        updated = update_readme(str(readme_path), mermaid_code)
        if updated:
            print(f"\n✅ {readme_path.name} updated successfully!")
        else:
            print(f"\n⚠️  Markers not found in {readme_path.name}.")
            print(f"   Add these markers where you want the diagram:")
            print(f"   <!-- ARCHITECTURE_DIAGRAM_START -->")
            print(f"   <!-- ARCHITECTURE_DIAGRAM_END -->")
    else:
        print(f"\n⚠️  {readme_path} not found. Printing diagram to stdout only.")


if __name__ == "__main__":
    main()
