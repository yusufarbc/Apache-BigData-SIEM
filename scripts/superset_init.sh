#!/bin/bash
set -e

echo "Installing system dependencies for sasl..."
# We need build-essential and libsasl2-dev for sasl python package
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get install -y build-essential libsasl2-dev python3-dev libsasl2-modules-gssapi-mit netcat-openbsd

echo "Installing database drivers..."
# The venv doesn't have pip, so we use system pip with --target
pip install --target /app/.venv/lib/python3.10/site-packages pyhive thrift sasl thrift_sasl

echo "Waiting for PostgreSQL to be ready..."
# Wait for superset-postgres
until nc -z superset-postgres 5432; do
  echo "Postgres is unavailable - sleeping"
  sleep 1
done

echo "Setting up Superset metadata..."
/app/.venv/bin/superset db upgrade
/app/.venv/bin/superset fab create-admin \
              --username admin \
              --password admin123 \
              --firstname Admin \
              --lastname User \
              --email admin@example.com || true

/app/.venv/bin/superset init

echo "Adding Spark SQL Database Connection..."
# Use venv's python to add the DB connection if not exists
/app/.venv/bin/python - <<EOF
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
/app/.venv/bin/superset run -h 0.0.0.0 -p 8088 --with-threads --reload --debugger
