import os
DEMO_MODE = True
SOURCE_DB = {
    "host": os.environ.get("SRC_DB_HOST", "localhost"),
    "port": int(os.environ.get("SRC_DB_PORT", 3306)),
    "user": os.environ.get("SRC_DB_USER", "root"),
    "password": os.environ.get("SRC_DB_PASSWORD", "your_password_here"),
    "database": os.environ.get("SRC_DB_NAME", "old_company_db"),
}

TARGET_DB = {
    "host": os.environ.get("TGT_DB_HOST", "localhost"),
    "port": int(os.environ.get("TGT_DB_PORT", 3306)),
    "user": os.environ.get("TGT_DB_USER", "root"),
    "password": os.environ.get("TGT_DB_PASSWORD", "your_password_here"),
    "database": os.environ.get("TGT_DB_NAME", "new_company_db"),
}

TABLE_NAME = "customers"

ID_COLUMN = "id"

MATCH_COLUMNS = {
    "name": {"weight": 0.35},
    "phone": {"weight": 0.35},
    "email": {"weight": 0.30},
}

DUPLICATE_THRESHOLD = 0.75

MAX_SCAN_RECORDS = 4000

CLUSTER_EPS = 1 - DUPLICATE_THRESHOLD

SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
DEBUG = True
