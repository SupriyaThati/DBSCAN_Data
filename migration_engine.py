import os
import sqlite3
import pandas as pd

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")
OLD_DB_PATH = os.path.join(SAMPLE_DIR, "old.db")
NEW_DB_PATH = os.path.join(SAMPLE_DIR, "new.db")

def _mysql_connect(db_cfg):
    import pymysql
    return pymysql.connect(
        host=db_cfg["host"],
        port=db_cfg["port"],
        user=db_cfg["user"],
        password=db_cfg["password"],
        database=db_cfg["database"],
        cursorclass=pymysql.cursors.DictCursor,
    )


def test_connection(which="source"):
    """which = 'source' or 'target'. Returns (ok: bool, message: str)."""
    if config.DEMO_MODE:
        path = OLD_DB_PATH if which == "source" else NEW_DB_PATH
        exists = os.path.exists(path)
        return exists, "Demo SQLite ready" if exists else "Demo DB not found — run seed_demo_data()"

    db_cfg = config.SOURCE_DB if which == "source" else config.TARGET_DB
    try:
        conn = _mysql_connect(db_cfg)
        conn.close()
        return True, f"Connected to {db_cfg['database']} @ {db_cfg['host']}"
    except Exception as e:
        return False, str(e)

def fetch_source_records():
    """Returns a list[dict] of every row in the source customers table."""
    if config.DEMO_MODE:
        conn = sqlite3.connect(OLD_DB_PATH)
        df = pd.read_sql_query(f"SELECT * FROM {config.TABLE_NAME}", conn)
        conn.close()
        return df.to_dict(orient="records")

    conn = _mysql_connect(config.SOURCE_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.TABLE_NAME}")
            rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def fetch_target_records():
    if config.DEMO_MODE:
        conn = sqlite3.connect(NEW_DB_PATH)
        try:
            df = pd.read_sql_query(f"SELECT * FROM {config.TABLE_NAME}", conn)
        except Exception:
            df = pd.DataFrame()
        conn.close()
        return df.to_dict(orient="records")

    conn = _mysql_connect(config.TARGET_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.TABLE_NAME}")
            rows = cur.fetchall()
        return rows
    finally:
        conn.close()

def migrate_records(records: list[dict], skip_ids: set | None = None):
    """
    Writes `records` into the target DB, skipping any whose ID_COLUMN
    is in skip_ids (i.e. records the user chose to drop as duplicates).

    Returns: number of rows written.
    """
    skip_ids = skip_ids or set()
    to_write = [r for r in records if r.get(config.ID_COLUMN) not in skip_ids]
    if not to_write:
        return 0

    df = pd.DataFrame(to_write)

    insert_df = df.drop(columns=[config.ID_COLUMN], errors="ignore")

    if config.DEMO_MODE:
        conn = sqlite3.connect(NEW_DB_PATH)
        insert_df.to_sql(config.TABLE_NAME, conn, if_exists="append", index=False)
        conn.close()
        return len(insert_df)

    conn = _mysql_connect(config.TARGET_DB)
    try:
        cols = list(insert_df.columns)
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO {config.TABLE_NAME} ({col_names}) VALUES ({placeholders})"
        with conn.cursor() as cur:
            for _, row in insert_df.iterrows():
                cur.execute(sql, tuple(row[c] for c in cols))
        conn.commit()
        return len(insert_df)
    finally:
        conn.close()

def seed_demo_data(reset=True):
    """Creates sample_data/old.db pre-loaded with messy sample records,
    and an empty sample_data/new.db as the migration target."""
    os.makedirs(SAMPLE_DIR, exist_ok=True)

    if reset:
        for path in (OLD_DB_PATH, NEW_DB_PATH):
            if os.path.exists(path):
                os.remove(path)

    sample_rows = [
        (101, "Rahul Kumar", "9876543210", "rahul@gmail.com"),
        (102, "Rahul  Kumar", "9876543210", "rahul@gmail.com"),
        (103, "R. Kumar", "9876543210", "rahul@gmail.com"),
        (104, "Priya Sharma", "9123456789", "priya.sharma@yahoo.com"),
        (105, "Priya S.", "9123456789", "priya.sharma@yahoo.com"),
        (106, "Amit Verma", "9988776655", "amit.verma@outlook.com"),
        (107, "Sunita Rao", "9012345678", "sunita.rao@gmail.com"),
        (108, "Sunita  Rao", "9012345670", "sunita.rao@gmail.com"),
        (109, "Karan Mehta", "9765432109", "karan.mehta@gmail.com"),
        (110, "Karan Mehta", "9765432109", "kmehta@gmail.com"),
        (111, "Deepak Nair", "9345678901", "deepak.nair@gmail.com"),
        (112, "Aisha Khan", "9556677889", "aisha.khan@gmail.com"),
        (113, "Aisha K.", "9556677889", "aisha.khan@gmail.com"),
        (114, "Vikram Singh", "9234567890", "vikram.singh@gmail.com"),
        (115, "Neha Gupta", "9445566778", "neha.gupta@gmail.com"),
    ]

    conn = sqlite3.connect(OLD_DB_PATH)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {config.TABLE_NAME} (
            id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT
        )
    """)
    conn.executemany(
        f"INSERT INTO {config.TABLE_NAME} (id, name, phone, email) VALUES (?, ?, ?, ?)",
        sample_rows,
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(NEW_DB_PATH)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {config.TABLE_NAME} (
            id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT
        )
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed_demo_data()
    print(f"Demo databases created at:\n  {OLD_DB_PATH}\n  {NEW_DB_PATH}")
