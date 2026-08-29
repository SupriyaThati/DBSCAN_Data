"""
duplicate_detector.py
======================
The "small ML part" of the project.

Pipeline:
  1. Normalize each field (name / phone / email) so trivial formatting
     differences don't count against a match.
  2. BLOCKING: instead of scoring every possible pair of records
     (O(n^2)), group records into "blocks" that share a normalized
     phone, email, or name fragment, and only generate candidate
     pairs from records that land in the same block. This is the
     standard "blocking" technique used in real-world record-linkage
     / de-duplication systems to avoid comparing everything to
     everything.
  3. Score only the candidate pairs with the existing weighted
     fuzzy-string similarity (rapidfuzz) -> a sparse similarity matrix
     (all non-candidate pairs are simply assumed dissimilar, since
     they shared no blocking key).
  4. Convert similarity -> distance and run scikit-learn's DBSCAN to
     group records into duplicate "clusters" (this is the clustering
     piece — it also naturally handles groups of 3+ duplicates, not
     just pairs). This step is unchanged from before.
  5. Return clusters above the configured threshold, with a
     human-readable "reason" for each match (same phone / similar
     name / same email), same shape as the mock-up you sent.
"""

import re
import time
import numpy as np
from rapidfuzz import fuzz
from sklearn.cluster import DBSCAN

import config


# ---------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------

def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[.\-_]", " ", name)          # "R. Kumar" -> "r kumar"
    name = re.sub(r"\s+", " ", name)               # collapse double spaces
    return name.strip()


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)              # strip spaces/dashes/+91 etc
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_email(email: str) -> str:
    if not email:
        return ""
    return email.lower().strip()


NORMALIZERS = {
    "name": normalize_name,
    "phone": normalize_phone,
    "email": normalize_email,
}


# ---------------------------------------------------------------
# Pairwise similarity
# ---------------------------------------------------------------

def field_similarity(a: str, b: str) -> float:
    """0-1 fuzzy similarity between two normalized strings."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return fuzz.token_sort_ratio(a, b) / 100.0


def record_similarity(rec_a: dict, rec_b: dict) -> tuple[float, list[str]]:
    """
    Weighted similarity between two records + list of human-readable
    reasons the two records look alike (for the UI's "Reason" panel).
    """
    total = 0.0
    reasons = []

    for field, cfg in config.MATCH_COLUMNS.items():
        norm = NORMALIZERS.get(field, lambda x: (x or "").lower().strip())
        a_val = norm(rec_a.get(field, ""))
        b_val = norm(rec_b.get(field, ""))
        sim = field_similarity(a_val, b_val)
        total += sim * cfg["weight"]

        if sim >= 0.98:
            reasons.append(f"Same {field}")
        elif sim >= 0.6:
            reasons.append(f"Similar {field}")

    return total, reasons


# ---------------------------------------------------------------
# Blocking / candidate generation
# ---------------------------------------------------------------
#
# Comparing every record against every other record is O(n^2) - at
# config.MAX_SCAN_RECORDS that can be tens of thousands of pairwise
# similarity calculations for a single scan. In practice the vast
# majority of those pairs are obviously not duplicates (different
# name, different phone, different email), so we never need to score
# them at all.
#
# "Blocking" fixes this: records are bucketed into small groups
# ("blocks") that share some normalized value that real duplicates are
# very likely to share (same phone, same email, same first name,
# same first few letters of the full name). Only records that land in
# the same block are compared to each other. This trades a small
# amount of recall (two duplicates that share *nothing* normalizable
# would be missed) for a large drop in the number of comparisons,
# which is the standard approach used by real record-linkage tools.
#
# A record can - and usually does - belong to several blocks, and a
# candidate pair only needs to show up in one block to get compared.
# Blank/near-blank values are never used as a block key, otherwise
# every record missing a phone (say) would land in one giant block and
# defeat the whole point (see MIN_BLOCK_KEY_LENGTH below).

MIN_BLOCK_KEY_LENGTH = 3  # keys shorter than this are too common to be useful


def _record_blocking_keys(record: dict) -> set[tuple[str, str]]:
    """
    Returns a set of (block_type, key) tuples for one record, built
    from the SAME normalization functions used for similarity scoring
    above, so a record ends up in blocks consistent with how it will
    actually be compared.

    Deliberately generous (not "unnecessarily strict"): a phone/email
    match is a strong signal on its own, and the name-based keys exist
    as a safety net for records where phone/email were also mistyped.
    """
    name_norm = normalize_name(record.get("name", ""))
    phone_norm = normalize_phone(record.get("phone", ""))
    email_norm = normalize_email(record.get("email", ""))

    keys = set()

    # Phone-based blocks. Guard against short/blank numbers turning
    # into one enormous block.
    if len(phone_norm) >= 6:
        keys.add(("phone", phone_norm))
        keys.add(("phone_suffix", phone_norm[-6:]))

    # Email-based blocks (full address, and just the username part so
    # "rahul@gmail.com" and "rahul@yahoo.com" still land together).
    if "@" in email_norm:
        local, _, domain = email_norm.partition("@")
        keys.add(("email", email_norm))
        if len(local) >= MIN_BLOCK_KEY_LENGTH:
            keys.add(("email_user", local))

    # Name-based blocks: first token ("rahul" from "rahul kumar") and
    # a prefix of the whole name with spaces stripped, so "Rahul
    # Kumar" and "R. Kumar" can still meet in the "kuma../rahu.." style
    # buckets even when phone/email were both mistyped.
    if name_norm:
        tokens = name_norm.split()
        first_token = tokens[0] if tokens else ""
        if len(first_token) >= MIN_BLOCK_KEY_LENGTH:
            keys.add(("name_first", first_token))
        compact = name_norm.replace(" ", "")
        if len(compact) >= MIN_BLOCK_KEY_LENGTH:
            keys.add(("name_prefix", compact[:MIN_BLOCK_KEY_LENGTH + 1]))

    return keys


def _generate_candidate_pairs(records: list[dict]) -> set[tuple[int, int]]:
    """
    Buckets every record's index into blocks, then returns the set of
    (i, j) index pairs (i < j) that share at least one block. This
    replaces the old "compare index i against every index j" loop.
    """
    blocks: dict[tuple[str, str], list[int]] = {}
    for idx, record in enumerate(records):
        for key in _record_blocking_keys(record):
            blocks.setdefault(key, []).append(idx)

    candidate_pairs: set[tuple[int, int]] = set()
    for member_idxs in blocks.values():
        if len(member_idxs) < 2:
            continue  # nobody else in this block - no candidates from it
        for x, i in enumerate(member_idxs):
            for j in member_idxs[x + 1:]:
                candidate_pairs.add((i, j) if i < j else (j, i))

    return candidate_pairs


# Stats from the most recent find_duplicate_clusters() call, so the
# app can report real (never fabricated) numbers about how much work
# blocking actually saved. Purely informational - nothing else reads
# or depends on this.
_last_stats = {}


def get_last_scan_stats() -> dict:
    """Returns a copy of the stats captured during the last
    find_duplicate_clusters() call (empty dict if it hasn't run yet)."""
    return dict(_last_stats)


# ---------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------

def find_duplicate_clusters(records: list[dict]):
    """
    records: list of dicts, each must contain config.ID_COLUMN plus the
             fields listed in config.MATCH_COLUMNS.

    Returns: list of cluster dicts:
        {
          "cluster_id": int,
          "records": [ {..original record.., "similarity_to_group": float}, ...],
          "avg_similarity": float,
          "reasons": [str, ...]
        }
    """
    n = len(records)
    if n < 2:
        _last_stats.clear()
        return []

    start = time.perf_counter()

    # BLOCKING: only generate candidate pairs from records that share
    # a normalized phone/email/name fragment, instead of every
    # possible pair (the old `for i ... for j in range(i+1, n)` loop).
    candidate_pairs = _generate_candidate_pairs(records)

    # Build similarity matrix - but only fill in scores for candidate
    # pairs. Every pair that never shared a block is left at 0
    # similarity (i.e. assumed not a duplicate), which is the
    # trade-off blocking makes in exchange for skipping the comparison.
    sim_matrix = np.eye(n)
    reason_lookup = {}
    for i, j in candidate_pairs:
        sim, reasons = record_similarity(records[i], records[j])
        sim_matrix[i, j] = sim
        sim_matrix[j, i] = sim
        if sim >= config.DUPLICATE_THRESHOLD:
            reason_lookup[(i, j)] = reasons

    # Convert to distance matrix for DBSCAN (precomputed metric)
    distance_matrix = 1 - sim_matrix
    np.fill_diagonal(distance_matrix, 0)

    clustering = DBSCAN(
        eps=config.CLUSTER_EPS,
        min_samples=2,
        metric="precomputed",
    ).fit(distance_matrix)

    labels = clustering.labels_  # -1 = not a duplicate of anything

    clusters = []
    for cluster_id in sorted(set(labels)):
        if cluster_id == -1:
            continue
        member_idxs = [i for i, lbl in enumerate(labels) if lbl == cluster_id]
        if len(member_idxs) < 2:
            continue

        # avg pairwise similarity within the cluster
        pair_sims = [
            sim_matrix[a, b]
            for x, a in enumerate(member_idxs)
            for b in member_idxs[x + 1:]
        ]
        avg_sim = float(np.mean(pair_sims)) if pair_sims else 0.0

        # union of reasons across all pairs in the cluster
        all_reasons = set()
        for x, a in enumerate(member_idxs):
            for b in member_idxs[x + 1:]:
                key = (a, b) if a < b else (b, a)
                all_reasons.update(reason_lookup.get(key, []))

        cluster_records = []
        for idx in member_idxs:
            rec = dict(records[idx])
            others = [j for j in member_idxs if j != idx]
            own_sim = float(np.mean([sim_matrix[idx, j] for j in others])) if others else 0.0
            rec["similarity_to_group"] = round(own_sim * 100, 1)
            cluster_records.append(rec)

        clusters.append({
            "cluster_id": int(cluster_id),
            "records": cluster_records,
            "avg_similarity": round(avg_sim * 100, 1),
            "reasons": sorted(all_reasons),
        })

    # Highest-confidence groups first
    clusters.sort(key=lambda c: c["avg_similarity"], reverse=True)

    duplicate_record_count = sum(len(c["records"]) for c in clusters)
    max_possible_pairs = n * (n - 1) // 2
    _last_stats.clear()
    _last_stats.update({
        "records_scanned": n,
        "max_possible_pairs": max_possible_pairs,
        "candidate_pairs_generated": len(candidate_pairs),
        "similarity_comparisons_performed": len(candidate_pairs),
        "comparisons_skipped": max_possible_pairs - len(candidate_pairs),
        "duplicate_records": duplicate_record_count,
        "duplicate_groups": len(clusters),
        "processing_time_seconds": round(time.perf_counter() - start, 4),
    })

    return clusters
