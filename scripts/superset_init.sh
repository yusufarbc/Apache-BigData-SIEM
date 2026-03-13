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

echo "Adding Spark SQL Database Connection..."
python - <<EOF
try:
    print("Starting app initialization...")
    from superset.app import create_app
    app = create_app()
    print("App created. Pushing context...")
    with app.app_context():
        print("Context pushed. Importing Model...")
        from superset import db
        from superset.models.core import Database
        
        uri = "hive://spark-master:10000/default"
        name = "Spark SIEM"
        
        print(f"Checking for existing database: {name}")
        existing = db.session.query(Database).filter_by(database_name=name).first()
        if not existing:
            print(f"Adding database {name}...")
            new_db = Database(database_name=name, sqlalchemy_uri=uri)
            db.session.add(new_db)
            db.session.commit()
            print("Database added successfully.")
        else:
            print(f"Database {name} already exists.")
except Exception as e:
    print(f"FAILED to add database: {e}")
    import traceback
    traceback.print_exc()
EOF

echo "Starting Superset Server..."
superset run -h 0.0.0.0 -p 8088 --with-threads --reload --debugger
