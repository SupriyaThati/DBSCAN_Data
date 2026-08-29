"""
app.py
======
Flask backend for the Smart Data Migration & Duplicate Detector dashboard.

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import io
import csv

from flask import Flask, jsonify, request, render_template, send_file

import config
import migration_engine as engine
import duplicate_detector as detector
import file_ingest

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

# In-memory scan cache so /api/migrate can reuse the last scan's
# clusters without re-running the ML step. Fine for a single-user
# local tool; swap for a real session/store if you deploy this.
_last_scan = {"records": [], "clusters": []}

# Holds a user-uploaded dataset once confirmed, so /api/scan can use
# it instead of the configured source database. Cleared by
# /api/clear-upload to go back to DB mode.
_uploaded = {"active": False, "columns": [], "records": [], "filename": None}


@app.route("/")
def dashboard():
    return render_template("index.html", demo_mode=config.DEMO_MODE)


@app.route("/api/status")
def api_status():
    src_ok, src_msg = engine.test_connection("source")
    tgt_ok, tgt_msg = engine.test_connection("target")
    return jsonify({
        "demo_mode": config.DEMO_MODE,
        "source": {"connected": src_ok, "message": src_msg},
        "target": {"connected": tgt_ok, "message": tgt_msg},
        "table": config.TABLE_NAME,
        "threshold": config.DUPLICATE_THRESHOLD,
    })


@app.route("/api/seed-demo", methods=["POST"])
def api_seed_demo():
    if not config.DEMO_MODE:
        return jsonify({"error": "Not in demo mode"}), 400
    engine.seed_demo_data(reset=True)
    return jsonify({"ok": True})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Accepts a CSV or Excel file, parses it, and guesses which column
    is name/phone/email. Nothing is stored as 'active' data yet — the
    frontend shows the guessed mapping and the user confirms it via
    /api/confirm-mapping before anything is scanned."""
    if "file" not in request.files:
        return jsonify({"error": "No file was sent."}), 400

    df, err = file_ingest.parse_upload(request.files["file"])
    if err:
        return jsonify({"error": err}), 400

    columns = list(df.columns)
    guess = file_ingest.guess_column_map(columns)
    preview = df.head(5).fillna("").astype(str).to_dict(orient="records")

    # stash the raw dataframe in memory keyed by filename so
    # /api/confirm-mapping can rebuild records without re-uploading
    _uploaded["_pending_df"] = df
    _uploaded["filename"] = request.files["file"].filename

    return jsonify({
        "filename": _uploaded["filename"],
        "row_count": len(df),
        "columns": columns,
        "guessed_mapping": guess,
        "preview": preview,
    })


@app.route("/api/confirm-mapping", methods=["POST"])
def api_confirm_mapping():
    """Body: { "name": "<column>", "phone": "<column>", "email": "<column>" }
    Converts the pending uploaded dataframe into standard records using
    the mapping the user confirmed (or corrected) in the dashboard."""
    df = _uploaded.get("_pending_df")
    if df is None:
        return jsonify({"error": "Upload a file first."}), 400

    body = request.get_json(force=True, silent=True) or {}
    mapping = {
        "name": body.get("name"),
        "phone": body.get("phone"),
        "email": body.get("email"),
    }

    if not any(mapping.values()):
        return jsonify({"error": "Map at least one column before continuing."}), 400

    records = file_ingest.build_records(df, mapping)

    _uploaded["active"] = True
    _uploaded["columns"] = list(df.columns)
    _uploaded["records"] = records
    _uploaded["mapping"] = mapping

    return jsonify({"ok": True, "record_count": len(records)})


@app.route("/api/clear-upload", methods=["POST"])
def api_clear_upload():
    """Drops the uploaded dataset and goes back to scanning the
    configured source database (demo SQLite or real MySQL)."""
    _uploaded["active"] = False
    _uploaded["records"] = []
    _uploaded["_pending_df"] = None
    return jsonify({"ok": True})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Pulls every source record — from the uploaded file if one's been
    confirmed, otherwise from the configured source database — and runs
    the fuzzy-matching + clustering pipeline.

    NOTE: the matching step compares every record against every other
    record (an n^2 operation), so it's capped at MAX_SCAN_RECORDS to
    avoid exhausting memory/time on large uploads. Anything beyond the
    cap is left out of this scan — see README for how to raise it or
    split a bigger file into batches."""
    if _uploaded["active"]:
        records = _uploaded["records"]
        source_label = f"upload: {_uploaded['filename']}"
    else:
        records = engine.fetch_source_records()
        source_label = "database"

    total_available = len(records)
    capped = total_available > config.MAX_SCAN_RECORDS
    if capped:
        records = records[:config.MAX_SCAN_RECORDS]

    clusters = detector.find_duplicate_clusters(records)

    _last_scan["records"] = records
    _last_scan["clusters"] = clusters

    duplicate_ids = {
        r[config.ID_COLUMN] for c in clusters for r in c["records"]
    }

    return jsonify({
        "source": source_label,
        "total_records": len(records),
        "total_available": total_available,
        "capped": capped,
        "max_scan_records": config.MAX_SCAN_RECORDS,
        "clean_records": len(records) - len(duplicate_ids),
        "duplicate_records": len(duplicate_ids),
        "clusters": clusters,
    })


@app.route("/api/migrate", methods=["POST"])
def api_migrate():
    """
    Body: { "decisions": { "<cluster_id>": "merge" | "keep_separate", ... } }

    "merge"        -> keep only the first record in the cluster, drop the rest
    "keep_separate"-> migrate every record in the cluster as-is
    Any cluster not mentioned defaults to "keep_separate".
    Non-duplicate records always migrate.
    """
    body = request.get_json(force=True, silent=True) or {}
    decisions = body.get("decisions", {})

    records = _last_scan["records"] or engine.fetch_source_records()
    clusters = _last_scan["clusters"]

    skip_ids = set()
    merged_groups = 0
    for cluster in clusters:
        decision = decisions.get(str(cluster["cluster_id"]), "keep_separate")
        if decision == "merge":
            merged_groups += 1
            ids_in_cluster = [r[config.ID_COLUMN] for r in cluster["records"]]
            # keep the first record, drop the rest as duplicates
            skip_ids.update(ids_in_cluster[1:])

    written = engine.migrate_records(records, skip_ids=skip_ids)

    return jsonify({
        "migrated": written,
        "skipped_as_duplicates": len(skip_ids),
        "groups_merged": merged_groups,
    })


@app.route("/api/export-csv", methods=["POST"])
def api_export_csv():
    """Same decision logic as /api/migrate, but returns a downloadable
    CSV of the deduplicated records instead of writing to a database —
    handy when you just want a clean file, not a MySQL target."""
    body = request.get_json(force=True, silent=True) or {}
    decisions = body.get("decisions", {})

    records = _last_scan["records"]
    clusters = _last_scan["clusters"]
    if not records:
        return jsonify({"error": "Run a scan first."}), 400

    skip_ids = set()
    for cluster in clusters:
        decision = decisions.get(str(cluster["cluster_id"]), "keep_separate")
        if decision == "merge":
            ids_in_cluster = [r[config.ID_COLUMN] for r in cluster["records"]]
            skip_ids.update(ids_in_cluster[1:])

    clean_records = [r for r in records if r.get(config.ID_COLUMN) not in skip_ids]

    buffer = io.StringIO()
    fieldnames = list(clean_records[0].keys()) if clean_records else ["id", "name", "phone", "email"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(clean_records)

    mem = io.BytesIO(buffer.getvalue().encode("utf-8"))
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="cleaned_customers.csv",
    )


@app.route("/api/target-preview")
def api_target_preview():
    records = engine.fetch_target_records()
    return jsonify({"records": records, "count": len(records)})


if __name__ == "__main__":
    if config.DEMO_MODE:
        import os
        if not os.path.exists(engine.OLD_DB_PATH):
            engine.seed_demo_data()
    app.run(debug=config.DEBUG, port=5000)
