#!/bin/bash
set -e

echo "Starting Superset Initializer (Clean & Optimized)..."

# Ensure the DB URI is recognized by the environment
export SQLALCHEMY_DATABASE_URI=${SQLALCHEMY_DATABASE_URI:-"postgresql+psycopg2://superset:superset123@siem-postgres:5432/superset"}
export SUPERSET_CONFIG_PATH=${SUPERSET_CONFIG_PATH:-"/app/config/superset_config.py"}
export SUPERSET_ENV=production

# 1. Wait for Postgres
echo "Waiting for Postgres (siem-postgres:5432)..."
until printf "" 2>>/dev/null >>/dev/tcp/siem-postgres/5432; do 
    sleep 2
done

# 1.1 Wait for Spark Thrift (Required for metadata setup)
echo "Waiting for Spark Thrift (spark-thrift:10000)..."
until printf "" 2>>/dev/null >>/dev/tcp/spark-thrift/10000; do 
    sleep 5
done

# 1b. Install missing drivers
echo "Installing Spark/Hive and Postgres drivers..."
pip install --no-cache-dir pyhive thrift thrift-sasl psycopg2-binary

# 2. Standard Superset Init (Must run before python script)
echo "Running Database Upgrade..."
superset db upgrade

echo "Creating Admin User..."
superset fab create-admin \
    --username admin \
    --firstname Superset \
    --lastname Admin \
    --email admin@siem.local \
    --password admin || true

echo "Initializing Superset..."
superset init

# 3. Dynamic Dashboard & Metadata Setup via Python
echo "Applying SIEM Dashboard & Table Metadata..."
python3 - <<EOF
import json
from superset.app import create_app
from superset import db

def run_setup():
    app = create_app()
    with app.app_context():
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice
        from superset.connectors.sqla.models import SqlaTable, SqlMetric, Database
        from flask_appbuilder.security.sqla.models import User
        from sqlalchemy.exc import IntegrityError

        db.session.rollback()
        admin = db.session.query(User).filter_by(username='admin').first()
        
        # Ensure Spark/Hive DB Connection Exists and is Correct
        spark_db = db.session.query(Database).filter(Database.database_name.ilike('%spark%')).first()
        if not spark_db:
            print("Creating Spark Thrift connection...")
            spark_db = Database(database_name="Spark Thrift Server")
            db.session.add(spark_db)
        
        print(f"Updating Spark Thrift URI to hive://spark-thrift:10000/siem")
        spark_db.sqlalchemy_uri = "hive://spark-thrift:10000/siem"
        db.session.commit()

        def get_dataset(name, schema="siem", dttm="ingest_ts"):
            ds = db.session.query(SqlaTable).filter_by(table_name=name, schema=schema).first()
            if not ds:
                try:
                    ds = SqlaTable(table_name=name, schema=schema, database_id=spark_db.id)
                    db.session.add(ds)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    ds = db.session.query(SqlaTable).filter_by(table_name=name).first()
            if ds:
                ds.database_id = spark_db.id
                ds.fetch_metadata()
                m_names = [m.metric_name for m in ds.metrics]
                if 'count' not in m_names: db.session.add(SqlMetric(metric_name='count', expression='COUNT(*)', table_id=ds.id))
                if name == "network_anomalies" and 'avg__anomaly_score' not in m_names:
                    db.session.add(SqlMetric(metric_name='avg__anomaly_score', expression='AVG(anomaly_score)', table_id=ds.id))
                if name == "model_metrics" and 'avg__wssse' not in m_names:
                    db.session.add(SqlMetric(metric_name='avg__wssse', expression='AVG(wssse)', table_id=ds.id))
                for col in ds.columns:
                    if col.column_name in [dttm, 'ingest_ts', 'event_time']: col.is_dttm = True
                ds.main_dttm_col = dttm
                db.session.commit()
            return ds

        def get_chart(name, viz, ds, params):
            slc = db.session.query(Slice).filter_by(slice_name=name).first() or Slice(slice_name=name)
            slc.viz_type, slc.datasource_type, slc.datasource_id = viz, "table", ds.id
            slc.params = json.dumps(params)
            if admin and admin not in slc.owners: slc.owners.append(admin)
            db.session.add(slc)
            db.session.commit()
            return slc

        # Datasets & Charts
        t_anom = get_dataset("network_anomalies")
        t_flow = get_dataset("network_flows")
        t_metrics = get_dataset("model_metrics")

        charts = [
            get_chart("NDR: Anomaly Count", "big_number_total", t_anom, {"metric": "count"}),
            get_chart("NDR: Avg Anomaly Score", "big_number_total", t_anom, {"metric": "avg__anomaly_score"}),
            get_chart("SOC: Normal vs Anomaly", "pie", t_flow, {"groupby": ["is_anomaly"], "metric": "count"}),
            get_chart("NDR: Anomaly Timeline", "echarts_timeseries_line", t_anom, {"metrics": ["count"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "PT1M"}),
            get_chart("NDR: Model Stability", "echarts_timeseries_line", t_metrics, {"metrics": ["avg__wssse"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "P1D"}),
            get_chart("NDR: Top Malicious IPs", "dist_bar", t_anom, {"groupby": ["src_ip"], "metrics": ["count"]}),
            get_chart("NDR: Protocol Distribution", "pie", t_anom, {"groupby": ["proto"], "metric": "count"}),
            get_chart("NDR: Real-time Incident Feed", "table", t_anom, {"all_columns": ["ingest_ts", "src_ip", "dest_ip", "dest_port", "proto", "anomaly_score"], "order_by_cols": [["ingest_ts", False]]}),
            get_chart("SOC: Traffic Rate", "echarts_timeseries_line", t_flow, {"metrics": ["count"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "PT1M"})
        ]

        # Dashboard Layout Construction (Advanced v2 format)
        dash = db.session.query(Dashboard).filter_by(slug="soc_ndr").first() or Dashboard(dashboard_title="Unified SOC & NDR Command Center", slug="soc_ndr")
        if admin and admin not in dash.owners: dash.owners.append(admin)
        
        cids = [s.id for s in charts]
        # Robust grid structure with explicit parents
        pos = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
            "GRID_ID": {"children": ["R1", "R2", "R3", "R4"], "id": "GRID_ID", "parents": ["ROOT_ID"], "type": "GRID"},
            "R1": {"children": [f"CHART-{cids[0]}", f"CHART-{cids[1]}", f"CHART-{cids[2]}"], "id": "R1", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R2": {"children": [f"CHART-{cids[3]}", f"CHART-{cids[4]}"], "id": "R2", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R3": {"children": [f"CHART-{cids[5]}", f"CHART-{cids[6]}"], "id": "R3", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R4": {"children": [f"CHART-{cids[7]}", f"CHART-{cids[8]}"], "id": "R4", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        }

        # Add Chart Components
        parents_map = {"R1": cids[0:3], "R2": cids[3:5], "R3": cids[5:7], "R4": cids[7:9]}
        for row_id, chart_ids in parents_map.items():
            for i, cid in enumerate(chart_ids):
                pos[f"CHART-{cid}"] = {
                    "children": [],
                    "id": f"CHART-{cid}",
                    "parents": ["ROOT_ID", "GRID_ID", row_id],
                    "type": "CHART",
                    "meta": {
                        "chartId": cid,
                        "width": 4 if row_id == "R1" else 6,
                        "height": 50,
                        "sliceName": charts[cids.index(cid)].slice_name
                    }
                }

        dash.position_json, dash.published = json.dumps(pos), True
        for s in charts:
            if s not in dash.slices: dash.slices.append(s)
        db.session.add(dash)
        db.session.commit()
        print("DASHBOARD SETUP COMPLETE: slug=soc_ndr")

run_setup()
EOF

echo "Starting Superset Server..."
superset run -h 0.0.0.0 -p 8088 --with-threads --reload --debugger
