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
            
            # 3b. Force metadata sync (this populates Columns)
            print(f"Syncing metadata for {schema_name}.{table_name}...")
            dataset.fetch_metadata()
            db.session.commit()

            # 4. Create a Sample Chart (Events per Topic)
            chart_params = {
                "viz_type": "pie",
                "datasource": f"{dataset.id}__table",
                "metric": "count",
                "groupby": ["source_topic"],
                "row_limit": 10000,
                "show_legend": True,
            }
            chart_name = "SIEM: Event Distribution"
            print(f"Syncing chart: {chart_name}")
            chart = db.session.query(Slice).filter_by(slice_name=chart_name).first()
            if not chart:
                chart = Slice(slice_name=chart_name, viz_type="pie", datasource_type="table", datasource_id=dataset.id)
                db.session.add(chart)
            
            chart.params = json.dumps(chart_params)
            db.session.commit()
            db.session.refresh(chart)

            # 4b. Create another chart (Top Attacking IPs)
            chart_ip_params = {
                "viz_type": "dist_bar",
                "datasource": f"{dataset.id}__table",
                "metrics": ["count"],
                "groupby": ["client_ip"],
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": ["400", "401", "403", "404", "429"],
                        "expressionType": "SIMPLE",
                        "operator": "IN",
                        "subject": "status_code"
                    }
                ],
                "row_limit": 20,
                "show_legend": True,
            }
            chart_ip_name = "SIEM: Top Attacking IPs"
            print(f"Syncing chart: {chart_ip_name}")
            chart_ip = db.session.query(Slice).filter_by(slice_name=chart_ip_name).first()
            if not chart_ip:
                chart_ip = Slice(slice_name=chart_ip_name, viz_type="dist_bar", datasource_type="table", datasource_id=dataset.id)
                db.session.add(chart_ip)
            
            chart_ip.params = json.dumps(chart_ip_params)
            db.session.commit()
            db.session.refresh(chart_ip)

            # 4c. Create chart (Total Events Count)
            chart_total_params = {
                "viz_type": "big_number_total",
                "datasource": f"{dataset.id}__table",
                "metric": "count",
                "subheader": "Total processed logs",
            }
            chart_total_name = "SIEM: Total Event Volume"
            print(f"Syncing chart: {chart_total_name}")
            chart_total = db.session.query(Slice).filter_by(slice_name=chart_total_name).first()
            if not chart_total:
                chart_total = Slice(slice_name=chart_total_name, viz_type="big_number_total", datasource_type="table", datasource_id=dataset.id)
                db.session.add(chart_total)
            chart_total.params = json.dumps(chart_total_params)
            db.session.commit()
            db.session.refresh(chart_total)

            # 4d. Create chart (Recent Logs Table)
            chart_table_params = {
                "viz_type": "table",
                "datasource": f"{dataset.id}__table",
                "metrics": ["count"],
                "all_columns": ["ingest_ts", "source_topic", "client_ip", "status_code", "raw_log"],
                "query_mode": "raw",
                "row_limit": 50,
                "table_timestamp_format": "smart_date",
            }
            chart_table_name = "SIEM: Recent Log Samples"
            print(f"Syncing chart: {chart_table_name}")
            chart_table = db.session.query(Slice).filter_by(slice_name=chart_table_name).first()
            if not chart_table:
                chart_table = Slice(slice_name=chart_table_name, viz_type="table", datasource_type="table", datasource_id=dataset.id)
                db.session.add(chart_table)
            chart_table.params = json.dumps(chart_table_params)
            db.session.commit()
            db.session.refresh(chart_table)

            # 4e. Create chart (Events Over Time)
            chart_time_params = {
                "viz_type": "echarts_timeseries_line",
                "datasource": f"{dataset.id}__table",
                "granularity_sqla": "ingest_ts",
                "time_grain_sqla": "PT1M",
                "metrics": ["count"],
                "groupby": ["source_topic"],
                "seriesType": "line",
                "show_legend": True,
            }
            chart_time_name = "SIEM: Events Over Time"
            print(f"Syncing chart: {chart_time_name}")
            chart_time = db.session.query(Slice).filter_by(slice_name=chart_time_name).first()
            if not chart_time:
                chart_time = Slice(slice_name=chart_time_name, viz_type="echarts_timeseries_line", datasource_type="table", datasource_id=dataset.id)
                db.session.add(chart_time)
            chart_time.params = json.dumps(chart_time_params)
            db.session.commit()
            db.session.refresh(chart_time)

            # 4f. Create chart (Unique Attackers)
            chart_atk_params = {
                "viz_type": "big_number_total",
                "datasource": f"{dataset.id}__table",
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "client_ip"},
                    "aggregate": "COUNT_DISTINCT",
                    "label": "Unique Attackers"
                },
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": ["400", "401", "403", "404", "429"],
                        "expressionType": "SIMPLE",
                        "operator": "IN",
                        "subject": "status_code"
                    }
                ],
                "subheader": "Distinct attacking IP addresses",
            }
            chart_atk_name = "SIEM: Unique Attackers"
            print(f"Syncing chart: {chart_atk_name}")
            chart_atk = db.session.query(Slice).filter_by(slice_name=chart_atk_name).first()
            if not chart_atk:
                chart_atk = Slice(slice_name=chart_atk_name, viz_type="big_number_total", datasource_type="table", datasource_id=dataset.id)
                db.session.add(chart_atk)
            chart_atk.params = json.dumps(chart_atk_params)
            db.session.commit()
            db.session.refresh(chart_atk)

            # 5. Create Dashboard
            dash_name = "SIEM SOC Overview"
            print(f"Syncing dashboard: {dash_name}")
            dash = db.session.query(Dashboard).filter_by(dashboard_title=dash_name).first()
            
            # Ensure all IDs are fresh
            db.session.refresh(chart)
            db.session.refresh(chart_ip)
            db.session.refresh(chart_total)
            db.session.refresh(chart_table)
            db.session.refresh(chart_time)
            db.session.refresh(chart_atk)
            
            cids = [chart_total.id, chart_atk.id, chart_time.id, chart.id, chart_ip.id, chart_table.id]
            print(f"Chart IDs: {cids}")
            
            # Rebuild a valid layout
            pos_data = {
                "DASHBOARD_VERSION_KEY": "v2",
                "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
                "GRID_ID": {"children": ["ROW-0", "ROW-1", "ROW-2", "ROW-3"], "id": "GRID_ID", "type": "GRID"},
                "ROW-0": {"children": [f"CHART-{cids[0]}", f"CHART-{cids[1]}"], "id": "ROW-0", "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
                "ROW-1": {"children": [f"CHART-{cids[2]}"], "id": "ROW-1", "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
                "ROW-2": {"children": [f"CHART-{cids[3]}", f"CHART-{cids[4]}"], "id": "ROW-2", "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
                "ROW-3": {"children": [f"CHART-{cids[5]}"], "id": "ROW-3", "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            }
            
            # Add chart components
            for i, cid in enumerate(cids):
                # cids[0], cids[1] share ROW-0 (width 6 each)
                # cids[2] full ROW-1 (width 12)
                # cids[3], cids[4] share ROW-2 (width 6 each)
                # cids[5] full ROW-3 (width 12)
                width = 12 if i in [2, 5] else 6
                pos_data[f"CHART-{cid}"] = {
                    "children": [],
                    "id": f"CHART-{cid}",
                    "meta": {"chartId": cid, "width": width, "height": 50},
                    "type": "CHART"
                }

            if not dash:
                dash = Dashboard(dashboard_title=dash_name)
                db.session.add(dash)
            
            dash.published = True
            dash.slices = [chart_total, chart_atk, chart_time, chart, chart_ip, chart_table]
            dash.position_json = json.dumps(pos_data)
            db.session.commit()
            print("Dashboard sync completed.")
except Exception as e:
    print(f"FAILED to configure Superset: {e}")
    import traceback
    traceback.print_exc()
EOF

echo "Starting Superset Server..."
superset run -h 0.0.0.0 -p 8088 --with-threads --reload --debugger
