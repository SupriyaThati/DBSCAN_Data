# Merge — Smart Data Migration & Duplicate Detector

Migrates customer records from an old MySQL database into a new one, and
flags groups of records that are probably the same person (fuzzy name
match + same phone/email + clustering) before they land in the new
database. You review each group in the dashboard and choose **Merge into
one** or **Keep separate**.

---

## 1. What's in this folder

```
migration_tool/
├── app.py                 Flask backend + API routes
├── migration_engine.py    Reads/writes the source & target databases
├── duplicate_detector.py  The ML part — fuzzy matching + DBSCAN clustering
├── config.py               ← YOU EDIT THIS
├── schema.sql              SQL to create the customers table on real MySQL
├── requirements.txt
├── templates/index.html    Dashboard page
├── static/css/style.css    Styling
├── static/js/app.js        Dashboard behaviour
└── sample_data/            Auto-created demo SQLite files (demo mode only)
```

---

## 2. Run it right now (zero setup — demo mode)

The project ships with `DEMO_MODE = True`, so it runs immediately on
sample data — no MySQL server needed. This is the fastest way to see it
working.

```bash
cd migration_tool
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Open **http://127.0.0.1:5000**, click **Scan for duplicates**, review the
groups, click **Migrate to new database**. Click **Reload demo data** any
time to reset the sample records.

---

## 3. Changes you need to make to use YOUR real MySQL data

This is the part you asked about — here's exactly what to edit after you
unzip the project.

### Step 1 — Create the database & table on both MySQL servers

Edit `schema.sql` if your real table has different columns, then run it
against both your old and new database:

```bash
mysql -u root -p old_company_db < schema.sql
mysql -u root -p new_company_db < schema.sql
```

### Step 2 — Edit `config.py`

Open `config.py` and change two things:

**a) Turn off demo mode:**

```python
DEMO_MODE = False
```

**b) Fill in your real connection details:**

```python
SOURCE_DB = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_real_password",
    "database": "old_company_db",
}

TARGET_DB = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_real_password",
    "database": "new_company_db",
}
```

*(Tip: instead of hardcoding the password, you can set environment
variables `SRC_DB_PASSWORD` / `TGT_DB_PASSWORD` before running
`python3 app.py` — `config.py` already reads those if present.)*

### Step 3 — Match the table & columns to your real schema

Still in `config.py`:

```python
TABLE_NAME = "customers"        # change if your table is named differently
ID_COLUMN = "id"                 # your primary key column

MATCH_COLUMNS = {
    "name":  {"weight": 0.35},
    "phone": {"weight": 0.35},
    "email": {"weight": 0.30},
}
```

If your columns are called something else (e.g. `full_name`,
`mobile_number`), rename the keys in `MATCH_COLUMNS` to match — and
also update the column names referenced in `duplicate_detector.py`'s
`record_similarity()` function if you renamed a *key*, not just a
value (the keys are what everything else reads).

### Step 4 — Reinstall dependencies (adds the MySQL driver)

```bash
pip install -r requirements.txt
```

`PyMySQL` is already listed in `requirements.txt`, so this step is only
needed if you installed packages before this file was updated.

### Step 5 — Run it

```bash
python3 app.py
```

The status pills in the top-right of the dashboard will show
**source: connected** / **target: connected** once MySQL is reachable.
If you see **offline**, double check host/port/user/password and that
MySQL is actually running.

---

## 4. Tuning the duplicate detector

In `config.py`:

- `DUPLICATE_THRESHOLD` (default `0.75`) — raise it (e.g. `0.85`) to only
  flag very close matches; lower it to catch looser matches too.
- `MATCH_COLUMNS` weights — increase `phone`'s weight if phone numbers
  are your most trustworthy signal, for example.

The matching logic itself lives in `duplicate_detector.py`:
- `normalize_name` / `normalize_phone` / `normalize_email` clean up each
  field before comparing (strips extra spaces, punctuation, country
  codes, etc.) — edit these if your data has other quirks (e.g. Indian
  numbers sometimes include a `+91` prefix, already handled).
- `record_similarity()` computes the weighted score and the "reasons"
  shown in the UI.
- `find_duplicate_clusters()` runs scikit-learn's `DBSCAN` to group
  records — this is what lets three or more records (like the 101/102/103
  example) show up as one group instead of three separate pairs.

---

## 5. Safety notes

- **Nothing writes to the target database until you click "Migrate to new
  database."** Scanning is read-only.
- "Merge into one" keeps the *first* record in each group and skips the
  rest — it does not currently combine field values from multiple
  records into one. If you need smarter merging (e.g. keep whichever
  record has the most complete data), that logic goes in
  `app.py`'s `api_migrate()` function.
- This is a local development tool (Flask's built-in server). Don't
  expose it to the internet as-is — if you ever deploy it, put it behind
  a real WSGI server (gunicorn) and add authentication.

---

## 6. Stack

Python · MySQL (PyMySQL) · Pandas · Scikit-learn (DBSCAN) · RapidFuzz ·
Flask · vanilla HTML/CSS/JS
