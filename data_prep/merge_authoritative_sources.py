"""Append the hand-curated authoritative CBT documents to the vector source CSV.

Source docs live in data/raw/authoritative_cbt/docs.json (fetched from
Wikipedia's clinical / CBT articles, CC BY-SA). Run once; it backs up the
existing merged CSV before rewriting it, and is idempotent (re-running does
not duplicate the authoritative rows).
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed" / "vector_source_merged.csv"
BACKUP = ROOT / "data" / "processed" / "vector_source_merged_v1.csv"
DOCS = ROOT / "data" / "raw" / "authoritative_cbt" / "docs.json"

ORIGIN = "authoritative_cbt"

df = pd.read_csv(PROCESSED)
print(f"Existing rows: {len(df)}  ({df['origin'].value_counts().to_dict()})")

if not BACKUP.exists():
    df.to_csv(BACKUP, index=False)
    print(f"Backed up original to {BACKUP.name}")

# drop any previous run's authoritative rows so this stays idempotent
df = df[df["origin"] != ORIGIN].copy()

with open(DOCS) as f:
    docs = json.load(f)

new_rows = pd.DataFrame([
    {
        "source_title": d["source_title"],
        "section": d["section"],
        "text": d["text"],
        "origin": ORIGIN,
        "url": d["url"],
    }
    for d in docs
])

merged = pd.concat([df, new_rows], ignore_index=True)
merged.to_csv(PROCESSED, index=False)

print(f"Added {len(new_rows)} authoritative CBT documents")
print(f"New total: {len(merged)} rows  ({merged['origin'].value_counts().to_dict()})")
