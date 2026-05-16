#!/bin/bash
set -e

echo "Starting Superset Initializer (Clean & Optimized)..."

# Run internal setup via python script for reliability
python3 - <<EOF
import json
from superset.app import create_app

def run_setup():
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice
        from superset.connectors.sqla.models import SqlaTable, SqlMetric, Database
        from flask_appbuilder.security.sqla.models import User
        from sqlalchemy.exc import IntegrityError

        db.session.rollback()
        admin = db.session.query(User).filter_by(username='admin').first()
        spark_db = db.session.query(Database).filter(Database.database_name.ilike('%spark%')).first() or db.session.query(Database).first()

        def get_dataset(name, schema="siem", dttm="ingest_ts"):
            ds = db.session.query(SqlaTable).filter_by(table_name=name, schema=schema).first()
            if not ds: ds = db.session.query(SqlaTable).filter_by(table_name=name).first()
            if not ds:
                try:
                    ds = SqlaTable(table_name=name, schema=schema, database_id=spark_db.id)
                    db.session.add(ds)
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    ds = db.session.query(SqlaTable).filter_by(table_name=name).first()
            if ds:
                ds.schema, ds.database_id = schema, spark_db.id
                ds.fetch_metadata()
                m_names = [m.metric_name for m in ds.metrics]
                if 'count' not in m_names: db.session.add(SqlMetric(metric_name='count', expression='COUNT(*)', table_id=ds.id))
                if name == "network_anomalies" and 'avg__anomaly_score' not in m_names:
                    db.session.add(SqlMetric(metric_name='avg__anomaly_score', expression='AVG(anomaly_score)', table_id=ds.id))
                for col in ds.columns:
                    if col.column_name in [dttm, 'ingest_ts', 'event_time', 'ts']: col.is_dttm = True
                    col.is_active = True
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
        t_anom = get_dataset("network_anomalies", "siem", "ingest_ts")
        t_flow = get_dataset("network_flows", "siem", "ingest_ts")
        t_metrics = get_dataset("model_metrics", "siem", "ingest_ts")

        charts = [
            get_chart("NDR: Anomaly Count", "big_number_total", t_anom, {"metric": "count"}),
            get_chart("NDR: Avg Anomaly Score", "big_number_total", t_anom, {"metric": "avg__anomaly_score"}),
            get_chart("SOC: Normal vs Anomaly", "pie", t_flow, {"groupby": ["is_anomaly"], "metric": "count"}),
            get_chart("NDR: Anomaly Timeline", "echarts_timeseries_line", t_anom, {"metrics": ["count"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "PT1M"}),
            get_chart("NDR: Model Stability", "echarts_timeseries_line", t_metrics, {"metrics": ["avg__wssse"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "P1D"}),
            get_chart("NDR: Top Malicious IPs", "dist_bar", t_anom, {"groupby": ["src_ip"], "metrics": ["count"]}),
            get_chart("NDR: Protocol Distribution", "pie", t_anom, {"groupby": ["proto"], "metric": "count", "donut": True}),
            get_chart("NDR: Global Threat Map", "world_map", t_anom, {"entity": "src_ip", "metric": "count"}),
            get_chart("NDR: Real-time Incident Feed", "table", t_anom, {"all_columns": ["ingest_ts", "src_ip", "dest_ip", "dest_port", "proto", "anomaly_score"], "order_by_cols": [["ingest_ts", False]]}),
            get_chart("SOC: Traffic Rate", "echarts_timeseries_line", t_flow, {"metrics": ["count"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "PT1M"})
        ]

        # Dashboard
        dash = db.session.query(Dashboard).filter_by(slug="soc_ndr").first() or Dashboard(dashboard_title="Unified SOC & NDR Command Center", slug="soc_ndr")
        if admin and admin not in dash.owners: dash.owners.append(admin)
        cids = [s.id for s in charts]
        pos = {"DASHBOARD_VERSION_KEY": "v2", "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"}, "GRID_ID": {"children": ["R1", "R2", "R3", "R4", "R5"], "id": "GRID_ID", "type": "GRID"}}
        pos["R1"] = {"children": [f"CHART-{cids[0]}", f"CHART-{cids[1]}", f"CHART-{cids[2]}"], "id": "R1", "type": "ROW"}
        pos["R2"] = {"children": [f"CHART-{cids[3]}", f"CHART-{cids[4]}"], "id": "R2", "type": "ROW"}
        pos["R3"] = {"children": [f"CHART-{cids[5]}", f"CHART-{cids[6]}"], "id": "R3", "type": "ROW"}
        pos["R4"] = {"children": [f"CHART-{cids[7]}"], "id": "R4", "type": "ROW"}
        pos["R5"] = {"children": [f"CHART-{cids[9]}", f"CHART-{cids[8]}"], "id": "R5", "type": "ROW"}

        for i, cid in enumerate(cids):
            w = 4 if i < 3 else (6 if i < 9 else 12)
            pos[f"CHART-{cid}"] = {"children": [], "id": f"CHART-{cid}", "type": "CHART", "meta": {"chartId": cid, "width": w, "height": 50}}

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
