
"""
ingest_python.py
================
Loads all 10 raw CSVs produced by mc_roi_generator.py into PostgreSQL.
  Schema   : raw
  Strategy : All columns loaded as TEXT — preserves dirty data exactly as-is.
             Do NOT clean, cast, or transform anything in this file.

Source System → Table Map:
  CRM      →  raw_01_customers
               raw_02_customer_addresses
  Payments →  raw_03_payment_accounts
               raw_04_card_applications
  POS      →  raw_05_transactions          ← DQ issues live here only
               raw_06_transaction_items
               raw_07_products
  Stores   →  raw_08_store_directory
  Feedback →  raw_09_satisfaction_surveys
               raw_10_program_engagement

Staging Consolidation (10 raw → 4 dim + 2 fact):
  raw_01 + raw_02 + raw_03  →  dim_customer
  raw_07                    →  dim_product      (direct load)
  raw_08                    →  dim_store        (direct load)
  raw_04                    →  dim_card_program
  raw_05 + raw_06           →  fact_transactions
  raw_09 + raw_10           →  fact_customer_engagement

Usage:
  1. Create a .env file in the same folder with DB1_URL=<your connection string>
  2. Run the generator first: python mc_roi_generator.py
  3. Run: python ingest_python.py
"""

import os
import time

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv()
DB1_URL = os.getenv("DB1_URL")

if not DB1_URL:
    raise ValueError("❌ DB1_URL not found in .env — check your .env file")

engine = create_engine(DB1_URL)

# ── FILE MAP ──────────────────────────────────────────────────────────────────
# table_name → CSV path   (must match mc_roi_generator.py OUTPUT_DIR)
RAW_FILES = {
    # ── CRM ──────────────────────────────────────────────────────────────────
    "raw_01_customers":             "raw_data_mc_roi/raw_01_customers.csv",
    "raw_02_customer_addresses":    "raw_data_mc_roi/raw_02_customer_addresses.csv",
    # ── Payments ─────────────────────────────────────────────────────────────
    "raw_03_payment_accounts":      "raw_data_mc_roi/raw_03_payment_accounts.csv",
    "raw_04_card_applications":     "raw_data_mc_roi/raw_04_card_applications.csv",
    # ── POS ───────────────────────────────────────────────────────────────────
    "raw_05_transactions":          "raw_data_mc_roi/raw_05_transactions.csv",
    "raw_06_transaction_items":     "raw_data_mc_roi/raw_06_transaction_items.csv",
    "raw_07_products":              "raw_data_mc_roi/raw_07_products.csv",
    # ── Stores ───────────────────────────────────────────────────────────────
    "raw_08_store_directory":       "raw_data_mc_roi/raw_08_store_directory.csv",
    # ── Feedback ─────────────────────────────────────────────────────────────
    "raw_09_satisfaction_surveys":  "raw_data_mc_roi/raw_09_satisfaction_surveys.csv",
    "raw_10_program_engagement":    "raw_data_mc_roi/raw_10_program_engagement.csv",
}

# ── Source system display labels (for console grouping) ───────────────────────
SOURCE_LABELS = {
    "raw_01_customers":            "CRM",
    "raw_02_customer_addresses":   "CRM",
    "raw_03_payment_accounts":     "PAY",
    "raw_04_card_applications":    "PAY",
    "raw_05_transactions":         "POS",
    "raw_06_transaction_items":    "POS",
    "raw_07_products":             "POS",
    "raw_08_store_directory":      "STR",
    "raw_09_satisfaction_surveys": "FBK",
    "raw_10_program_engagement":   "FBK",
}

# ── Expected minimum row counts ───────────────────────────────────────────────
# raw_05_transactions: 8,000 base + 400 duplicate rows = 8,400 in file.
# The minimum is set to 8,400 so the verify step confirms dupes survived ingestion.
ROW_EXPECTATIONS = {
    "raw_01_customers":            1_000,
    "raw_02_customer_addresses":   1_000,
    "raw_03_payment_accounts":     1_000,
    "raw_04_card_applications":    1_200,
    "raw_05_transactions":         8_400,   # 8,000 base + 400 dupes — must survive as-is
    "raw_06_transaction_items":    9_000,
    "raw_07_products":                20,
    "raw_08_store_directory":         30,
    "raw_09_satisfaction_surveys": 2_500,
    "raw_10_program_engagement":   3_000,
}

# ── Consolidation reminder printed in the footer ──────────────────────────────
CONSOLIDATION_STORY = """
  Staging Consolidation (10 raw → 4 dim + 2 fact):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  DIMENSIONS                                                          │
  │  raw_01 + raw_02 + raw_03  →  dim_customer                          │
  │  raw_07                    →  dim_product      (direct load)         │
  │  raw_08                    →  dim_store        (direct load)         │
  │  raw_04                    →  dim_card_program                       │
  │                                                                      │
  │  FACTS                                                               │
  │  raw_05 + raw_06           →  fact_transactions                     │
  │    Cleaning tasks:                                                   │
  │    • Deduplicate 400 rows on transaction_id                          │
  │    • Standardize 400 dates MM-DD-YYYY → YYYY-MM-DD                  │
  │    • Strip " CAD" from 150 amounts, cast to numeric                  │
  │    • Quarantine or exclude 400 NULL amounts                          │
  │    • Join line items on transaction_id                               │
  │                                                                      │
  │  raw_09 + raw_10           →  fact_customer_engagement              │
  │    (union surveys + engagement — both clean)                         │
  └──────────────────────────────────────────────────────────────────────┘
"""


def verify_row_counts(conn) -> None:
    """Query raw schema after load and compare against expected minimums."""
    print("\n── Row Count Verification ───────────────────────────────────────────────")

    prev_system = None
    all_ok      = True

    for table, expected_min in ROW_EXPECTATIONS.items():
        system = SOURCE_LABELS[table]

        if system != prev_system:
            print(f"\n  [{system}]")
            prev_system = system

        result = conn.execute(text(f"SELECT COUNT(*) FROM raw.{table}"))
        actual = result.scalar()
        ok     = actual >= expected_min
        status = "✅" if ok else "⚠️ "
        if not ok:
            all_ok = False

        # Flag the transactions table specifically — dupes must survive ingestion
        note = "  ← includes 400 duplicate rows" if table == "raw_05_transactions" else ""
        print(f"    {status}  raw.{table:<38} {actual:>8,} rows"
              f"  (expected >= {expected_min:,}){note}")

    print()
    if all_ok:
        print("  ✅  All 10 tables loaded within expected range.")
    else:
        print("  ⚠️   One or more tables below expected row count — re-run generator.")


def main():
    print("=" * 68)
    print("  Mastercard ROI — Raw Ingestion (10-Table Version)")
    print("  Target  : raw schema   |   10 CSV files")
    print("  Strategy: All columns as TEXT — no casting, no cleaning")
    print("=" * 68)

    # ── Pre-flight: verify all CSV files exist before touching the DB ─────
    missing = [path for path in RAW_FILES.values() if not os.path.exists(path)]
    if missing:
        print("\n❌  Missing files — run mc_roi_generator.py first:\n")
        for f in missing:
            print(f"    {f}")
        return

    print(f"  ✅  All {len(RAW_FILES)} source files found\n")

    # ── Create raw schema if it doesn't exist ────────────────────────────
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.commit()
    print("  ✅  Schema 'raw' ready\n")

    # ── Load each table ───────────────────────────────────────────────────
    total_rows  = 0
    prev_system = None

    for table_name, filepath in RAW_FILES.items():
        system = SOURCE_LABELS[table_name]

        if system != prev_system:
            print(f"  [{system}]")
            prev_system = system

        start = time.time()

        # dtype=str preserves every value as written (no numeric coercion).
        # keep_default_na=False prevents pandas from silently converting
        # strings like "None", "NA", "null" into NaN — critical for
        # raw_05_transactions where NULL amounts must stay as empty strings
        # until the staging layer decides how to handle them.
        df = pd.read_csv(filepath, dtype=str, keep_default_na=False)

        df.to_sql(
            name      = table_name,
            con       = engine,
            schema    = "raw",
            if_exists = "replace",   # drops and reloads — safe to re-run
            index     = False,
            chunksize = 500,
            method    = "multi",
        )

        elapsed     = round(time.time() - start, 1)
        total_rows += len(df)
        print(f"    ✅  raw.{table_name:<38} {len(df):>8,} rows  ({elapsed}s)")

    # ── Post-load verification — queries DB directly to confirm ───────────
    with engine.connect() as conn:
        verify_row_counts(conn)

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print(f"  ✅  Done — {total_rows:,} total rows across 10 tables")
    print("=" * 68)
    print(CONSOLIDATION_STORY)
    print("  ⚠️   raw.* tables are the permanent source of truth.")
    print("       Never modify them after this point.")
    print("       All cleaning happens downstream in Power Query / staging.")
    print()


if __name__ == "__main__":
    main()