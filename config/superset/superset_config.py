import os

SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql+psycopg2://superset:superset123@siem-postgres:5432/superset')
SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY', 'f8d93a10-2b4a-4e2b-b893-ecf9e2b1029c')

# Performance & Security
WTF_CSRF_ENABLED = False
MAPBOX_API_KEY = ''
SUPERSET_WEBSERVER_TIMEOUT = 300
RESULTS_BACKEND = None
CACHE_CONFIG = {'CACHE_TYPE': 'null'}

# Features
FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,
    "ALERT_REPORTS": False
}
