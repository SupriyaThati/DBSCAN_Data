"""
file_ingest.py
===============
Lets the user upload their OWN dataset (CSV or Excel) instead of being
stuck with a fixed schema. Nothing about the column names is hardcoded —
we guess the mapping from common aliases, but the user always sees and
can override the guess before scanning.

Flow:
  1. parse_upload()      -> reads the file into a DataFrame, returns
                             its columns + a first-5-rows preview.
  2. guess_column_map()  -> best-effort guess of which column is
                             name / phone / email, using fuzzy matching
                             against common header names.
  3. build_records()     -> once the user confirms (or corrects) the
                             mapping, converts the DataFrame into the
                             plain {id, name, phone, email} dicts that
                             duplicate_detector.py and migration_engine.py
                             already know how to work with.
"""

import io
import pandas as pd
from rapidfuzz import process, fuzz

# Common header spellings people actually use — this is a starting
# point for the guess, not a requirement. Any column name works; if
# nothing matches well enough the user just picks it manually.
FIELD_ALIASES = {
    "name": ["name", "full name", "fullname", "customer name", "client name", "contact name"],
    "phone": ["phone", "mobile", "contact", "phone number", "mobile number", "contact number", "cell"],
    "email": ["email", "e-mail", "mail", "email address", "e mail"],
}


def parse_upload(file_storage):
    """
    file_storage: a Flask FileStorage object (request.files['file']).
    Returns (dataframe, error_message). error_message is None on success.
    """
    filename = (file_storage.filename or "").lower()
    raw = file_storage.read()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            return None, "Unsupported file type — upload a .csv or .xlsx file."
    except Exception as e:
        return None, f"Couldn't read that file: {e}"

    if df.empty:
        return None, "That file doesn't have any rows in it."

    # normalize column headers (strip whitespace) but keep original names
    df.columns = [str(c).strip() for c in df.columns]
    return df, None


def guess_column_map(columns: list[str]) -> dict:
    """
    Returns {"name": <col or None>, "phone": <col or None>, "email": <col or None>}
    by fuzzy-matching each real column header against known aliases.
    """
    mapping = {}
    used = set()

    for field, aliases in FIELD_ALIASES.items():
        best_col, best_score = None, 0
        for col in columns:
            if col in used:
                continue
            norm = col.lower().replace("_", " ").replace("-", " ").strip()
            match = process.extractOne(norm, aliases, scorer=fuzz.token_sort_ratio)
            if match and match[1] > best_score:
                best_col, best_score = col, match[1]

        mapping[field] = best_col if best_score >= 70 else None
        if mapping[field]:
            used.add(mapping[field])

    return mapping


def build_records(df: pd.DataFrame, mapping: dict) -> list[dict]:
    """
    mapping: {"name": "<real column name>", "phone": "...", "email": "..."}
    Returns list[dict] with keys: id, name, phone, email — the shape
    duplicate_detector.py and migration_engine.py expect.
    """
    records = []
    for idx, row in df.reset_index(drop=True).iterrows():
        records.append({
            "id": int(idx) + 1,
            "name": _safe_str(row.get(mapping.get("name"))),
            "phone": _safe_str(row.get(mapping.get("phone"))),
            "email": _safe_str(row.get(mapping.get("email"))),
        })
    return records


def _safe_str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()
