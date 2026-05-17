import json
import time
from superset.app import create_app
from superset import db

def run_setup():
    app = create_app()
    with app.app_context():
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice
        from superset.connectors.sqla.models import SqlaTable, SqlMetric, Database
        from flask_appbuilder.security.sqla.models import User
        from sqlalchemy import create_engine, inspect
        from sqlalchemy.exc import IntegrityError

        db.session.rollback()
        admin = db.session.query(User).filter_by(username='admin').first()
        
        # Ensure Spark/Hive DB Connection Exists and is Correct
        spark_db = db.session.query(Database).filter(Database.database_name.ilike('%spark%')).first()
        if not spark_db:
            print("Creating Spark Thrift connection...")
            spark_db = Database(database_name="Spark Thrift Server")
            db.session.add(spark_db)
        
        print("Updating Spark Thrift URI to hive://spark-thrift:10000/siem")
        spark_db.sqlalchemy_uri = "hive://spark-thrift:10000/siem"
        db.session.commit()

        # Robust waiting mechanism for Spark tables to be created
        engine = create_engine("hive://spark-thrift:10000/siem")
        required_tables = ["network_anomalies", "network_flows", "model_metrics", "logs_parsed", "alerts"]
        tables_exist = False
        print("Checking if all required Spark tables exist in Hive...")
        for i in range(5):
            try:
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                print(f"Current tables in Spark: {tables}")
                if all(t in tables for t in required_tables):
                    tables_exist = True
                    print("All 5 required Spark tables found!")
                    break
            except Exception as e:
                print(f"Waiting for Spark tables... ({e})")
        # Delete old slices starting with NDR: or SOC: from the database to avoid orphaned charts
        print("Cleaning up old NDR: and SOC: prefixed slices...")
        db.session.query(Slice).filter(
            (Slice.slice_name.like('NDR:%')) | (Slice.slice_name.like('SOC:%'))
        ).delete(synchronize_session=False)
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
                try:
                    ds.fetch_metadata()
                except Exception as e:
                    print(f"Metadata fetch failed for {name}: {e}")
                
                m_names = [m.metric_name for m in ds.metrics]
                if 'count' not in m_names: 
                    db.session.add(SqlMetric(metric_name='count', expression='COUNT(*)', table_id=ds.id))
                if name in ["network_anomalies", "network_flows"] and 'avg__anomaly_score' not in m_names:
                    db.session.add(SqlMetric(metric_name='avg__anomaly_score', expression='AVG(anomaly_score)', table_id=ds.id))
                if name == "model_metrics" and 'avg__wssse' not in m_names:
                    db.session.add(SqlMetric(metric_name='avg__wssse', expression='AVG(wssse)', table_id=ds.id))
                
                for col in ds.columns:
                    if col.column_name in [dttm, 'ingest_ts', 'event_time', 'detected_at']: 
                        col.is_dttm = True
                ds.main_dttm_col = dttm
                db.session.commit()
            return ds

        def get_chart(name, viz, ds, params):
            slc = db.session.query(Slice).filter_by(slice_name=name).first() or Slice(slice_name=name)
            slc.viz_type, slc.datasource_type, slc.datasource_id = viz, "table", ds.id
            slc.params = json.dumps(params)
            if admin and admin not in slc.owners: 
                slc.owners.append(admin)
            db.session.add(slc)
            db.session.commit()
            return slc

        # Datasets
        t_anom = get_dataset("network_anomalies", dttm="ingest_ts")
        t_flow = get_dataset("network_flows", dttm="ingest_ts")
        t_metrics = get_dataset("model_metrics", dttm="ingest_ts")
        t_logs = get_dataset("logs_parsed", dttm="ingest_ts")
        t_alerts = get_dataset("alerts", dttm="detected_at")

        # Charts
        charts = [
            # Row 1: KPIs
            get_chart("Anomaly Count", "big_number_total", t_anom, {"metric": "count"}),
            get_chart("Avg Anomaly Score", "big_number_total", t_anom, {"metric": "avg__anomaly_score"}),
            get_chart("Active Security Alerts", "big_number_total", t_alerts, {"metric": "count"}),
            get_chart("Total Log Volume", "big_number_total", t_logs, {"metric": "count"}),
            
            # Row 2: Timelines
            get_chart("Anomaly Timeline", "echarts_timeseries_line", t_anom, {"metrics": ["count"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "PT1M"}),
            get_chart("Log Volume Timeline (EPS)", "echarts_timeseries_line", t_logs, {"metrics": ["count"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "PT1S"}),
            get_chart("Model Stability", "echarts_timeseries_line", t_metrics, {"metrics": ["avg__wssse"], "granularity_sqla": "ingest_ts", "time_grain_sqla": "P1D"}),
            
            # Row 3: Pies / Distributions
            get_chart("Alert Severity", "pie", t_alerts, {"groupby": ["severity"], "metric": "count"}),
            get_chart("Log Distribution", "pie", t_logs, {"groupby": ["source_topic"], "metric": "count"}),
            get_chart("Protocol Distribution", "pie", t_anom, {"groupby": ["service"], "metric": "count"}),
            
            # Row 4: Bar / Distribution
            get_chart("Top Anomaly Source IPs", "dist_bar", t_anom, {"groupby": ["src_ip"], "metrics": ["count"]}),
            
            # Row 5: Tables / Feeds
            get_chart("Real-time Alert Feed", "table", t_alerts, {
                "all_columns": ["detected_at", "rule_name", "severity", "matched_field", "matched_value", "hit_count", "country"], 
                "order_by_cols": [["detected_at", False]]
            }),
            get_chart("Real-time Anomaly Feed", "table", t_anom, {
                "all_columns": ["ingest_ts", "src_ip", "src_port", "dest_ip", "dest_port", "proto", "service", "anomaly_score"], 
                "order_by_cols": [["ingest_ts", False]]
            })
        ]

        # Dashboard Layout Construction (Advanced v2 format)
        dash = db.session.query(Dashboard).filter_by(slug="soc_ndr").first()
        if not dash:
            dash = Dashboard(slug="soc_ndr")
        dash.dashboard_title = "Unified Security Operations & Anomaly Detection Dashboard"
        if admin and admin not in dash.owners: 
            dash.owners.append(admin)
        
        cids = [s.id for s in charts]
        # Robust grid structure with explicit parents
        pos = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
            "GRID_ID": {"children": ["R1", "R2", "R3", "R4", "R5", "R6"], "id": "GRID_ID", "parents": ["ROOT_ID"], "type": "GRID"},
            "R1": {"children": [f"CHART-{cids[0]}", f"CHART-{cids[1]}", f"CHART-{cids[2]}", f"CHART-{cids[3]}"], "id": "R1", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R2": {"children": [f"CHART-{cids[4]}", f"CHART-{cids[5]}", f"CHART-{cids[6]}"], "id": "R2", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R3": {"children": [f"CHART-{cids[7]}", f"CHART-{cids[8]}", f"CHART-{cids[9]}"], "id": "R3", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R4": {"children": [f"CHART-{cids[10]}"], "id": "R4", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R5": {"children": [f"CHART-{cids[11]}"], "id": "R5", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "R6": {"children": [f"CHART-{cids[12]}"], "id": "R6", "parents": ["GRID_ID"], "type": "ROW", "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        }

        # Add Chart Components
        parents_map = {
            "R1": (cids[0:4], 3),
            "R2": (cids[4:7], 4),
            "R3": (cids[7:10], 4),
            "R4": (cids[10:11], 12),
            "R5": (cids[11:12], 12),
            "R6": (cids[12:13], 12)
        }
        for row_id, (chart_ids, width) in parents_map.items():
            for cid in chart_ids:
                pos[f"CHART-{cid}"] = {
                    "children": [],
                    "id": f"CHART-{cid}",
                    "parents": ["ROOT_ID", "GRID_ID", row_id],
                    "type": "CHART",
                    "meta": {
                        "chartId": cid,
                        "width": width,
                        "height": 50,
                        "sliceName": charts[cids.index(cid)].slice_name
                    }
                }

        dash.position_json, dash.published = json.dumps(pos), True
        dash.slices = charts
        db.session.add(dash)
        db.session.commit()
        print("DASHBOARD SETUP COMPLETE: slug=soc_ndr")

if __name__ == "__main__":
    run_setup()
