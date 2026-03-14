#!/bin/bash
set -e

echo "Installing system dependencies for sasl..."
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get install -y build-essential libsasl2-dev python3-dev libsasl2-modules-gssapi-mit netcat-openbsd

echo "Installing database drivers..."
pip install pyhive thrift sasl thrift_sasl 2>/dev/null || true

echo "Waiting for PostgreSQL to be ready..."
# Wait for unified postgres (hosts both metastore and superset DBs)
until nc -z postgres 5432; do
  echo "Postgres is unavailable - sleeping"
  sleep 1
done

echo "Setting up Superset metadata..."
superset db upgrade
superset fab create-admin \
              --username admin \
              --password admin123 \
              --firstname Admin \
              --lastname User \
              --email admin@example.com || true

superset init

echo "Configuring Superset Assets (Datasets, Charts, Dashboards)..."
python - <<EOF
try:
    from superset.app import create_app
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.models.core import Database
        from superset.connectors.sqla.models import SqlaTable, SqlMetric
        from superset.models.slice import Slice
        from superset.models.dashboard import Dashboard
        import json

        # 1. Spark Connection
        spark_uri = "hive://spark-master:10000/siem"
        spark_name = "Spark SIEM"
        
        # 2. Postgres Connection
        pg_uri = "postgresql://hive_user:hive_password@postgres:5432/metastore_db"
        pg_name = "Postgres Metadata"

        connections = [
            {"name": spark_name, "uri": spark_uri},
            {"name": pg_name, "uri": pg_uri}
        ]
        
        for conn in connections:
            existing = db.session.query(Database).filter_by(database_name=conn['name']).first()
            if not existing:
                print(f"Adding database {conn['name']}...")
                new_db = Database(database_name=conn['name'], sqlalchemy_uri=conn['uri'])
                db.session.add(new_db)
                db.session.commit()
        
        # 3. Create SIEM Dataset (siem.logs_parsed)
        spark_db = db.session.query(Database).filter_by(database_name=spark_name).first()
        if spark_db:
            table_name = "logs_parsed"
            schema_name = "siem"
            print(f"Checking for dataset: {schema_name}.{table_name}")
            dataset = db.session.query(SqlaTable).filter_by(table_name=table_name, schema=schema_name).first()
            if not dataset:
                print(f"Adding dataset {schema_name}.{table_name}...")
                dataset = SqlaTable(table_name=table_name, schema=schema_name, database=spark_db)
                db.session.add(dataset)
                db.session.commit()
                print("Dataset added.")

            # 4. Create a Sample Chart (Events per Topic)
            chart_name = "SIEM: Event Distribution"
            print(f"Checking for chart: {chart_name}")
            chart = db.session.query(Slice).filter_by(slice_name=chart_name).first()
            if not chart:
                print(f"Adding chart {chart_name}...")
                chart_params = {
                    "viz_type": "pie",
                    "groupby": ["source_topic"],
                    "metric": "count",
                    "adhoc_filters": [],
                    "row_limit": 10000
                }
                chart = Slice(
                    slice_name=chart_name,
                    viz_type="pie",
                    datasource_type="table",
                    datasource_id=dataset.id,
                    params=json.dumps(chart_params)
                )
                db.session.add(chart)
                db.session.commit()
                print("Chart added.")

            # 4b. Create another chart (Top Attacking IPs)
            chart_ip_name = "SIEM: Top Attacking IPs"
            print(f"Checking for chart: {chart_ip_name}")
            chart_ip = db.session.query(Slice).filter_by(slice_name=chart_ip_name).first()
            if not chart_ip:
                print(f"Adding chart {chart_ip_name}...")
                chart_ip_params = {
                    "viz_type": "dist_bar",
                    "groupby": ["client_ip"],
                    "metric": "count",
                    "adhoc_filters": [
                        {
                            "clause": "WHERE",
                            "comparator": ["400", "401", "403", "404", "429"],
                            "expressionType": "SIMPLE",
                            "operator": "IN",
                            "subject": "status_code"
                        }
                    ],
                    "row_limit": 20
                }
                chart_ip = Slice(
                    slice_name=chart_ip_name,
                    viz_type="dist_bar",
                    datasource_type="table",
                    datasource_id=dataset.id,
                    params=json.dumps(chart_ip_params)
                )
                db.session.add(chart_ip)
                db.session.commit()
                print("Chart added.")

            # 5. Create Dashboard
            dash_name = "SIEM SOC Overview"
            print(f"Checking for dashboard: {dash_name}")
            dash = db.session.query(Dashboard).filter_by(dashboard_title=dash_name).first()
            if not dash:
                print(f"Adding dashboard {dash_name}...")
                dash = Dashboard(
                    dashboard_title=dash_name,
                    published=True,
                    slices=[chart, chart_ip],
                    position_json=json.dumps({
                        "DASHBOARD_VERSION_KEY": "v2",
                        "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
                        "GRID_ID": {"children": ["ROW-1"], "id": "GRID_ID", "type": "GRID"},
                        "ROW-1": {"children": [f"CHART-{chart.id}", f"CHART-{chart_ip.id}"], "id": "ROW-1", "type": "ROW"},
                        f"CHART-{chart.id}": {
                            "children": [],
                            "id": f"CHART-{chart.id}",
                            "meta": {"chartId": chart.id, "width": 6, "height": 50},
                            "type": "CHART"
                        },
                        f"CHART-{chart_ip.id}": {
                            "children": [],
                            "id": f"CHART-{chart_ip.id}",
                            "meta": {"chartId": chart_ip.id, "width": 6, "height": 50},
                            "type": "CHART"
                        }
                    })
                )
                db.session.add(dash)
                db.session.commit()
                print("Dashboard created successfully.")
except Exception as e:
    print(f"FAILED to configure Superset: {e}")
    import traceback
    traceback.print_exc()
EOF

echo "Starting Superset Server..."
superset run -h 0.0.0.0 -p 8088 --with-threads --reload --debugger
