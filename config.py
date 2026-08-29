"""
Smart Data Migration & Duplicate Detector — Configuration
============================================================
EDIT THIS FILE with your own database details before running for real.

Two modes are supported:

1. DEMO_MODE = True  (default)
   Uses local SQLite files (sample_data/old.db -> sample_data/new.db)
   pre-loaded with sample "dirty" customer data. No setup needed —
   just run the app and click "Scan for Duplicates".

2. DEMO_MODE = False
   Connects to your real MySQL servers using the credentials below.
   Requires a running MySQL server for both source (old) and
   target (new) databases.
"""

import os

# ---------------------------------------------------------------
# 1. Flip this to False once you're ready to point at real MySQL
# ---------------------------------------------------------------
DEMO_MODE = True

# ---------------------------------------------------------------
# 2. MySQL connection settings (only used when DEMO_MODE = False)
# ---------------------------------------------------------------
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

# ---------------------------------------------------------------
# 3. The table + columns you're migrating.
#    Change these to match your real schema.
# ---------------------------------------------------------------
TABLE_NAME = "customers"

# Column that uniquely identifies a row in the SOURCE table
ID_COLUMN = "id"

# Columns used to detect duplicates + how much each one counts
# (weights must add up to 1.0)
MATCH_COLUMNS = {
    "name": {"weight": 0.35},
    "phone": {"weight": 0.35},
    "email": {"weight": 0.30},
}

# Any similarity score >= this is flagged as a possible duplicate
DUPLICATE_THRESHOLD = 0.75

# Duplicate detection uses blocking (see duplicate_detector.py) so it
# no longer scores every possible pair of records - only records that
# share a normalized phone/email/name fragment get compared. That
# removed most of the CPU cost, which is why this cap could be raised
# from the original 500.
#
# The remaining limit is memory: the similarity matrix used for
# clustering is still a dense n x n array (~n^2 floats), regardless of
# how many pairs actually get scored. At 4,000 records that's roughly
# 128MB, which is comfortable on a normal machine. Raise it further if
# you have the RAM for it (rough guide: n^2 * 8 bytes), or split bigger
# files into smaller batches.
MAX_SCAN_RECORDS = 4000

# DBSCAN clustering sensitivity (lower = stricter clusters).
# eps is expressed in "distance" = 1 - similarity
CLUSTER_EPS = 1 - DUPLICATE_THRESHOLD

# ---------------------------------------------------------------
# 4. Flask settings
# ---------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
DEBUG = True
