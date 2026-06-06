"""
Mastercard ROI — Customer Analytics Raw Data Generator (10-Table Version)
=========================================================================
Generates 10 raw CSVs simulating 4 source systems for a generic retail brand
partnered with Mastercard. Designed for portfolio demonstration of:
  • Mastercard vs Non-Mastercard customer segment comparison
  • Spend patterns, loyalty engagement, and satisfaction by payment type
  • Data cleaning & staging pipeline skills

Source Systems & Table Map (10 tables):
  CRM      →  raw_01_customers
               raw_02_customer_addresses
  Payments →  raw_03_payment_accounts
               raw_04_card_applications
  POS      →  raw_05_transactions
               raw_06_transaction_items
               raw_07_products
  Stores   →  raw_08_store_directory
  Feedback →  raw_09_satisfaction_surveys
               raw_10_program_engagement

Staging Consolidation (10 raw → 4 dim + 2 fact):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  raw_01 + raw_02 + raw_03           →  dim_customer                     │
  │  raw_07                             →  dim_product                      │
  │  raw_08                             →  dim_store                        │
  │  raw_04                             →  dim_card_program                 │
  │  raw_05 + raw_06                    →  fact_transactions                │
  │  raw_09 + raw_10                    →  fact_customer_engagement         │
  └──────────────────────────────────────────────────────────────────────────┘

Data Quality Issues (ONLY in raw_05_transactions):
  ┌──────────────────────────────────────┬────────────┬──────────────────────┐
  │ Issue                                │ Count      │ Where                │
  ├──────────────────────────────────────┼────────────┼──────────────────────┤
  │ NULL revenue                         │ 5% (~400)  │ raw_05_transactions  │
  │ Duplicate rows (same txn_id)         │ 5% (~400)  │ raw_05_transactions  │
  │ Revenue as "CAD" format              │ ~150 rows  │ raw_05_transactions  │
  │ Date as MM-DD-YYYY instead of ISO    │ ~5%        │ raw_05_transactions  │
  ├──────────────────────────────────────┼────────────┼──────────────────────┤
  │ ALL OTHER TABLES                     │ 100% CLEAN │ No nulls, no issues  │
  └──────────────────────────────────────┴────────────┴──────────────────────┘

DQ INJECTION ORDER (CRITICAL):
  Duplicates are appended FIRST → 8,400-row file is built → THEN all DQ
  issues are injected across the full file. This guarantees the stated
  counts are exact in the final CSV, not inflated by dirty-row duplication.

Mastercard ROI Story (baked into data):
  • Mastercard holders: higher avg spend (+35-55%), more frequent txns
  • Non-MC customers: lower engagement, higher churn signal
  • Clear segment separation for cross-sectional comparison

Volume: ~1,000 customers | ~8,000 transactions (+400 dupes = 8,400 in file)
Output: ./raw_data_mc_roi/
"""

import os
import re
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# ── Reproducibility ──────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker("en_CA")

OUTPUT_DIR = "raw_data_mc_roi"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Volume Constants ─────────────────────────────────────────────────────────
N_CUSTOMERS    = 1_000
N_TXN_BASE     = 8_000    # clean base rows before DQ injection
N_SURVEYS      = 2_500
N_ENGAGEMENT   = 3_000
N_STORES       = 30
N_APPLICATIONS = 1_200

# ── DQ Targets (applied to full 8,400-row file after duplicates are added) ──
N_DUPLICATES   = 400   # 400 rows share an existing transaction_id → 400 dupe IDs
N_NULL_REVENUE = 400   # exactly 400 NULL amounts
N_CAD_FORMAT   = 150   # exactly 150 "123.45 CAD" formatted amounts
N_DATE_DIRTY   = 400   # exactly 400 MM-DD-YYYY dates

N_TXN_TOTAL    = N_TXN_BASE + N_DUPLICATES   # 8,400 rows in final file

# ── Date Window ──────────────────────────────────────────────────────────────
WIN_START = date(2022, 1, 1)
WIN_END   = date(2024, 12, 31)

def rand_date(start=WIN_START, end=WIN_END):
    return start + timedelta(days=random.randint(0, (end - start).days))

def iso(d):
    return d.strftime("%Y-%m-%d")

# ── Geography ─────────────────────────────────────────────────────────────────
PROVINCES    = ["ON", "BC", "AB", "QC", "MB", "SK", "NS", "NB"]
PROV_WEIGHTS = [0.38, 0.16, 0.13, 0.15, 0.05, 0.05, 0.04, 0.04]
CITIES_BY_PROV = {
    "ON": ["Toronto", "Ottawa", "Mississauga", "Brampton", "Hamilton", "London", "Markham"],
    "BC": ["Vancouver", "Surrey", "Burnaby", "Richmond", "Kelowna", "Victoria"],
    "AB": ["Calgary", "Edmonton", "Red Deer", "Lethbridge"],
    "QC": ["Montreal", "Quebec City", "Laval", "Gatineau"],
    "MB": ["Winnipeg", "Brandon"],
    "SK": ["Saskatoon", "Regina"],
    "NS": ["Halifax", "Dartmouth"],
    "NB": ["Moncton", "Fredericton", "Saint John"],
}
REGION_MAP = {
    "ON": "East", "QC": "East", "NS": "East", "NB": "East",
    "BC": "West", "AB": "West", "MB": "Central", "SK": "Central",
}

# ── Payment / Card Lookups ────────────────────────────────────────────────────
PAYMENT_METHODS  = ["Mastercard", "Visa", "Debit", "Cash", "Gift Card"]
PAYMENT_WEIGHTS  = [0.45, 0.20, 0.20, 0.10, 0.05]

CARD_TIERS       = ["Standard", "Gold", "Platinum", "World Elite"]
TIER_WEIGHTS     = [0.35, 0.30, 0.25, 0.10]

SPEND_BY_METHOD = {
    "Mastercard": (40.0, 650.0),
    "Visa":       (25.0, 400.0),
    "Debit":      (15.0, 250.0),
    "Cash":       (10.0, 150.0),
    "Gift Card":  (20.0, 100.0),
}

TXN_FREQ_BY_METHOD = {
    "Mastercard": (5, 18),
    "Visa":       (3, 12),
    "Debit":      (2, 8),
    "Cash":       (1, 5),
    "Gift Card":  (1, 3),
}

# ── Product Catalog ───────────────────────────────────────────────────────────
PRODUCTS = [
    ("PRD001", "Premium Drill Kit",        "Power Tools",      129.99),
    ("PRD002", "Toolbox Professional",     "Hand Tools",        59.99),
    ("PRD003", "Circular Saw 7.25in",      "Power Tools",      189.99),
    ("PRD004", "Engine Oil 5W-30 5L",      "Automotive",        34.99),
    ("PRD005", "Winter Tire Set",          "Automotive",       599.99),
    ("PRD006", "Wiper Blade Pair",         "Automotive",        29.99),
    ("PRD007", "Outdoor Grill Pro",        "Outdoor Living",   349.99),
    ("PRD008", "Patio Furniture Set",      "Outdoor Living",   499.99),
    ("PRD009", "Garden Hose 75ft",         "Garden",            54.99),
    ("PRD010", "Lawn Mower Electric",      "Garden",           279.99),
    ("PRD011", "Paint Interior 4L",        "Home Improvement",  44.99),
    ("PRD012", "LED Light Fixture",        "Home Improvement",  69.99),
    ("PRD013", "Smart Thermostat",         "Electronics",      149.99),
    ("PRD014", "Portable Speaker",         "Electronics",       89.99),
    ("PRD015", "Kitchen Mixer Stand",      "Kitchen",          249.99),
    ("PRD016", "Cookware Set 10pc",        "Kitchen",          179.99),
    ("PRD017", "Camping Tent 4-Person",    "Outdoor Living",   229.99),
    ("PRD018", "Fire Pit Steel",           "Outdoor Living",   159.99),
    ("PRD019", "Snow Blower 22in",         "Seasonal",         449.99),
    ("PRD020", "Holiday Lights 200ct",     "Seasonal",          24.99),
]

# ── Channels ──────────────────────────────────────────────────────────────────
CHANNELS  = ["In-Store", "Online", "Mobile App"]
CHANNEL_W = [0.55, 0.30, 0.15]

# ── Engagement Types ──────────────────────────────────────────────────────────
ENGAGEMENT_TYPES = ["Points Earn", "Points Redeem", "Promo Click", "App Login", "Referral"]
ENGAGEMENT_W     = [0.35, 0.20, 0.25, 0.15, 0.05]

# ── Email Domains ─────────────────────────────────────────────────────────────
EMAIL_DOMAINS  = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
                  "icloud.com", "rogers.com", "bell.net", "shaw.ca"]
EMAIL_WEIGHTS  = [0.30, 0.18, 0.15, 0.12, 0.10, 0.07, 0.05, 0.03]

# ── Store Types ───────────────────────────────────────────────────────────────
STORE_TYPES  = ["Flagship", "Standard", "Express", "Outlet"]
STORE_TYPE_W = [0.10, 0.55, 0.25, 0.10]

# ── Helpers ───────────────────────────────────────────────────────────────────
def gen_clean_email(first, last, index, used):
    """Generate a valid unique email — NO DQ issues."""
    f = re.sub(r"[^a-z]", "", first.lower())
    l = re.sub(r"[^a-z]", "", last.lower())
    domain = random.choices(EMAIL_DOMAINS, weights=EMAIL_WEIGHTS)[0]
    for cand in [f"{f}.{l}@{domain}", f"{f[0]}{l}@{domain}",
                 f"{f}{l[0]}@{domain}", f"{f}.{l}{index % 100}@{domain}"]:
        if cand not in used:
            used.add(cand)
            return cand
    fb = f"cust{index}@{domain}"
    used.add(fb)
    return fb


def gen_clean_phone():
    """Generate phone in consistent format — NO DQ issues."""
    area = random.choice(["416", "905", "647", "604", "403", "514", "204", "306"])
    return f"{area}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"


def save(df, name):
    """Save DataFrame to CSV and print stats."""
    path = os.path.join(OUTPUT_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"  ✓ {name:<42} {len(df):>7,} rows  {df.shape[1]:>2} cols")


# ════════════════════════════════════════════════════════════════════════════════
# GENERATE
# ════════════════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "=" * 70)
    print("  Mastercard ROI — Customer Analytics Raw Data Generator")
    print("  10 Tables | ~1K Customers | ~8K Transactions (+400 dupes)")
    print("  DQ Issues ONLY in raw_05_transactions")
    print("=" * 70)

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 1: raw_01_customers (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n[CRM] Customer Master — CLEAN")
    used_emails = set()
    customers = []

    for i in range(N_CUSTOMERS):
        first = fake.first_name()
        last  = fake.last_name()
        prov  = random.choices(PROVINCES, weights=PROV_WEIGHTS)[0]
        dob   = rand_date(date(1958, 1, 1), date(2002, 12, 31))
        join  = rand_date(date(2019, 1, 1), date(2024, 6, 30))
        primary_payment = random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS)[0]

        customers.append({
            "customer_id":     f"CUST{i+1:05d}",
            "first_name":      first,
            "last_name":       last,
            "date_of_birth":   iso(dob),
            "gender":          random.choices(["M", "F", "NB"], weights=[0.47, 0.47, 0.06])[0],
            "join_date":       iso(join),
            "primary_payment": primary_payment,
            "income_bracket":  random.choices(["Low", "Mid", "High"], weights=[0.25, 0.45, 0.30])[0],
            "is_active":       random.choices([1, 0], weights=[0.82, 0.18])[0],
        })

    cust_df = pd.DataFrame(customers)
    save(cust_df, "raw_01_customers")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 2: raw_02_customer_addresses (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("[CRM] Customer Addresses — CLEAN")
    addresses = []
    for i, row in enumerate(customers):
        prov = random.choices(PROVINCES, weights=PROV_WEIGHTS)[0]
        city = random.choice(CITIES_BY_PROV[prov])
        addresses.append({
            "customer_id":  row["customer_id"],
            "email":        gen_clean_email(row["first_name"], row["last_name"], i + 1, used_emails),
            "phone":        gen_clean_phone(),
            "street":       fake.street_address(),
            "city":         city,
            "province":     prov,
            "postal_code":  fake.postcode(),
            "region":       REGION_MAP[prov],
        })
    addr_df = pd.DataFrame(addresses)
    save(addr_df, "raw_02_customer_addresses")

    # Build lookup maps
    payment_map = dict(zip(cust_df["customer_id"], cust_df["primary_payment"]))
    active_map  = dict(zip(cust_df["customer_id"], cust_df["is_active"]))

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 3: raw_03_payment_accounts (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n[PAYMENTS] Payment Accounts — CLEAN")
    payment_accts = []
    for i, row in enumerate(customers):
        pm = row["primary_payment"]
        if pm == "Mastercard":
            tier         = random.choices(CARD_TIERS, weights=TIER_WEIGHTS)[0]
            rewards_rate = round(random.uniform(0.01, 0.04), 3)
            credit_limit = random.choice([5000, 7500, 10000, 15000, 20000, 25000])
        else:
            tier         = "N/A"
            rewards_rate = 0.0
            credit_limit = 0

        payment_accts.append({
            "account_id":        f"ACC{i+1:05d}",
            "customer_id":       row["customer_id"],
            "payment_type":      pm,
            "card_tier":         tier,
            "rewards_rate":      rewards_rate,
            "credit_limit":      credit_limit,
            "account_open_date": iso(rand_date(date(2019, 1, 1), date(2024, 3, 31))),
            "account_status":    random.choices(
                                     ["Active", "Inactive", "Suspended"],
                                     weights=[0.80, 0.15, 0.05]
                                 )[0],
        })
    pay_df = pd.DataFrame(payment_accts)
    save(pay_df, "raw_03_payment_accounts")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 4: raw_04_card_applications (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("[PAYMENTS] Card Applications — CLEAN")
    applications = []
    cids = cust_df["customer_id"].tolist()

    for i in range(N_APPLICATIONS):
        cid = random.choice(cids)
        app_date      = rand_date(date(2020, 1, 1), date(2024, 11, 30))
        is_mc_holder  = payment_map.get(cid) == "Mastercard"
        if is_mc_holder:
            status = random.choices(["Approved", "Declined", "Pending"], weights=[0.85, 0.10, 0.05])[0]
        else:
            status = random.choices(["Approved", "Declined", "Pending"], weights=[0.40, 0.45, 0.15])[0]

        applications.append({
            "application_id":    f"APP{i+1:06d}",
            "customer_id":       cid,
            "application_date":  iso(app_date),
            "card_tier_applied": random.choices(CARD_TIERS, weights=TIER_WEIGHTS)[0],
            "decision":          status,
            "decision_date":     iso(app_date + timedelta(days=random.randint(1, 14))),
            "annual_income":     random.choice([30000, 45000, 60000, 75000, 90000, 110000, 150000]),
            "credit_score":      random.randint(580, 850),
            "channel":           random.choices(CHANNELS, weights=CHANNEL_W)[0],
        })
    app_df = pd.DataFrame(applications)
    save(app_df, "raw_04_card_applications")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 5: raw_05_transactions — ALL DQ ISSUES LIVE HERE
    #
    # INJECTION ORDER (guarantees exact counts in final 8,400-row file):
    #   Step 1: Generate 8,000 clean base rows
    #   Step 2: Append 400 duplicate rows (same transaction_id + data)
    #           → file is now 8,400 rows, all amounts numeric, all dates ISO
    #   Step 3: NULL injection    — pick 400 random indices from 0..8399
    #   Step 4: CAD injection     — pick 150 from non-NULL indices
    #   Step 5: Date injection    — pick 400 from all indices
    #   Step 6: Serialize amounts as strings (NaN stays NaN)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n[POS] Transactions — DQ ISSUES HERE")
    store_ids   = [f"STR{i+1:03d}" for i in range(N_STORES)]
    txns        = []
    txn_counter = 0

    # ── Step 1: Generate 8,000 clean base rows ──────────────────────────────
    for cid in cids:
        pm       = payment_map.get(cid, "Cash")
        is_act   = active_map.get(cid, 1)
        lo, hi   = TXN_FREQ_BY_METHOD.get(pm, (1, 5))
        sl, sh   = SPEND_BY_METHOD.get(pm, (10, 150))
        n_txns   = random.randint(lo, hi)

        for _ in range(n_txns):
            if txn_counter >= N_TXN_BASE:
                break
            txn_counter += 1

            txn_date = (rand_date(WIN_START, date(2023, 6, 30))
                        if is_act == 0 else rand_date())

            # Seasonal spending peaks for Mastercard holders
            if pm == "Mastercard" and random.random() < 0.25:
                peak = random.choice([
                    (date(2022, 11, 20), date(2022, 12, 24)),
                    (date(2023, 11, 20), date(2023, 12, 24)),
                    (date(2024, 11, 20), date(2024, 12, 24)),
                ])
                txn_date = rand_date(peak[0], peak[1])

            amount = round(random.uniform(sl, sh), 2)
            txns.append({
                "transaction_id":   f"TXN{txn_counter:06d}",
                "customer_id":      cid,
                "store_id":         random.choice(store_ids),
                "transaction_date": iso(txn_date),          # clean ISO date
                "payment_method":   pm,
                "amount":           amount,                 # clean numeric float
                "channel":          random.choices(CHANNELS, weights=CHANNEL_W)[0],
                "return_flag":      random.choices([0, 1], weights=[0.94, 0.06])[0],
                "cashback_earned":  (round(amount * random.uniform(0.01, 0.04), 2)
                                     if pm == "Mastercard" else 0.00),
            })
        if txn_counter >= N_TXN_BASE:
            break

    # Fill if under target (edge case guard)
    while txn_counter < N_TXN_BASE:
        txn_counter += 1
        cid    = random.choice(cids)
        pm     = payment_map.get(cid, "Cash")
        sl, sh = SPEND_BY_METHOD.get(pm, (10, 150))
        amount = round(random.uniform(sl, sh), 2)
        txns.append({
            "transaction_id":   f"TXN{txn_counter:06d}",
            "customer_id":      cid,
            "store_id":         random.choice(store_ids),
            "transaction_date": iso(rand_date()),
            "payment_method":   pm,
            "amount":           amount,
            "channel":          random.choices(CHANNELS, weights=CHANNEL_W)[0],
            "return_flag":      random.choices([0, 1], weights=[0.94, 0.06])[0],
            "cashback_earned":  (round(amount * random.uniform(0.01, 0.04), 2)
                                 if pm == "Mastercard" else 0.00),
        })

    # ── Step 2: Append 400 duplicate rows (same txn_id + all fields) ───────
    # Duplicates are created from the clean base BEFORE any DQ injection.
    # This means the final 8,400-row list starts 100% clean, and every
    # DQ count injected below is exact in the final file.
    dupe_source_indices = random.sample(range(N_TXN_BASE), N_DUPLICATES)
    duplicates          = [txns[idx].copy() for idx in dupe_source_indices]
    all_txns            = txns + duplicates          # 8,400 rows, all clean
    random.shuffle(all_txns)                         # shuffle so dupes aren't bunched at end

    N_TOTAL = len(all_txns)   # 8,400

    # ── Step 3: Inject NULL amounts — exactly 400 rows ──────────────────────
    null_indices = random.sample(range(N_TOTAL), N_NULL_REVENUE)
    for idx in null_indices:
        all_txns[idx]["amount"] = None

    # ── Step 4: Inject "CAD" format — exactly 150 non-NULL rows ─────────────
    non_null_pool = [i for i in range(N_TOTAL) if i not in set(null_indices)]
    cad_indices   = random.sample(non_null_pool, N_CAD_FORMAT)
    for idx in cad_indices:
        all_txns[idx]["amount"] = f"{all_txns[idx]['amount']} CAD"

    # ── Step 5: Inject MM-DD-YYYY dates — exactly 400 rows ──────────────────
    date_dirty_indices = random.sample(range(N_TOTAL), N_DATE_DIRTY)
    for idx in date_dirty_indices:
        original = all_txns[idx]["transaction_date"]   # "YYYY-MM-DD"
        y, m, d  = original.split("-")
        all_txns[idx]["transaction_date"] = f"{m}-{d}-{y}"   # → "MM-DD-YYYY"

    # ── Step 6: Serialize amounts — numeric float → "123.45" string ─────────
    # NULL stays None (→ NaN in pandas). CAD strings already serialized.
    # All other amounts get stringified for a uniform column type in the CSV.
    for row in all_txns:
        if row["amount"] is not None and not isinstance(row["amount"], str):
            row["amount"] = f"{row['amount']:.2f}"

    txn_df = pd.DataFrame(all_txns)
    save(txn_df, "raw_05_transactions")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 6: raw_06_transaction_items (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("[POS] Transaction Items — CLEAN")
    items   = []
    item_id = 0

    # Build items only for the 8,000 canonical transaction IDs (not dupes)
    for tid in [f"TXN{i+1:06d}" for i in range(N_TXN_BASE)]:
        n_items = random.choices([1, 2, 3], weights=[0.88, 0.09, 0.03])[0]
        for _ in range(n_items):
            item_id    += 1
            prod        = random.choice(PRODUCTS)
            qty         = random.choices([1, 2, 3], weights=[0.75, 0.18, 0.07])[0]
            unit_price  = round(prod[3] * random.uniform(0.85, 1.10), 2)
            discount    = round(random.uniform(0.05, 0.25), 2) if random.random() < 0.20 else 0.00
            items.append({
                "item_id":        f"ITM{item_id:07d}",
                "transaction_id": tid,
                "product_id":     prod[0],
                "quantity":       qty,
                "unit_price":     unit_price,
                "discount_pct":   discount,
                "line_total":     round(qty * unit_price * (1 - discount), 2),
            })

    items_df = pd.DataFrame(items)
    save(items_df, "raw_06_transaction_items")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 7: raw_07_products (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("[POS] Product Catalog — CLEAN")
    prod_df = pd.DataFrame(PRODUCTS, columns=["product_id", "product_name", "category", "base_price"])
    prod_df["supplier"]    = [fake.company() for _ in range(len(PRODUCTS))]
    prod_df["launch_date"] = [iso(rand_date(date(2018, 1, 1), date(2023, 6, 30))) for _ in range(len(PRODUCTS))]
    save(prod_df, "raw_07_products")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 8: raw_08_store_directory (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n[STORES] Store Directory — CLEAN")
    stores = []
    for i in range(N_STORES):
        prov = random.choices(PROVINCES, weights=PROV_WEIGHTS)[0]
        city = random.choice(CITIES_BY_PROV[prov])
        stores.append({
            "store_id":   f"STR{i+1:03d}",
            "store_name": f"RetailCo {city} {random.choice(['North','South','East','West','Central','Mall','Square'])}",
            "city":       city,
            "province":   prov,
            "region":     REGION_MAP[prov],
            "store_type": random.choices(STORE_TYPES, weights=STORE_TYPE_W)[0],
            "open_date":  iso(rand_date(date(2008, 1, 1), date(2022, 12, 31))),
            "sq_footage": random.randint(5000, 55000),
        })
    store_df = pd.DataFrame(stores)
    save(store_df, "raw_08_store_directory")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 9: raw_09_satisfaction_surveys (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n[FEEDBACK] Satisfaction Surveys — CLEAN")
    survey_types   = ["NPS", "Post-Purchase", "Annual"]
    survey_type_w  = [0.40, 0.45, 0.15]
    surveys        = []

    for i in range(N_SURVEYS):
        cid   = random.choice(cids)
        pm    = payment_map.get(cid, "Cash")
        stype = random.choices(survey_types, weights=survey_type_w)[0]

        # ROI signal: MC holders rate experience higher
        if pm == "Mastercard":
            nps          = random.choices(range(0, 11), weights=[1,1,1,2,3,5,8,12,15,18,20])[0]
            satisfaction = random.choices([1,2,3,4,5], weights=[2,5,12,35,46])[0]
        else:
            nps          = random.choices(range(0, 11), weights=[3,4,5,6,8,10,12,14,15,13,10])[0]
            satisfaction = random.choices([1,2,3,4,5], weights=[5,10,25,35,25])[0]

        surveys.append({
            "survey_id":           f"SRV{i+1:06d}",
            "customer_id":         cid,
            "survey_date":         iso(rand_date()),
            "survey_type":         stype,
            "nps_score":           nps if stype == "NPS" else None,  # intentional design null
            "satisfaction_score":  satisfaction,
            "ease_of_use":         random.randint(1, 5),
            "would_recommend":     random.choices(["Yes", "No", "Maybe"], weights=[0.55, 0.25, 0.20])[0],
            "payment_method_used": pm,
        })

    survey_df = pd.DataFrame(surveys)
    save(survey_df, "raw_09_satisfaction_surveys")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 10: raw_10_program_engagement (CLEAN)
    # ══════════════════════════════════════════════════════════════════════════
    print("[FEEDBACK] Program Engagement — CLEAN")
    mc_customers     = [c for c in cids if payment_map.get(c) == "Mastercard"]
    non_mc_customers = [c for c in cids if payment_map.get(c) != "Mastercard"]
    engagements      = []

    for i in range(N_ENGAGEMENT):
        # 65% of engagement from MC holders (ROI signal)
        if random.random() < 0.65:
            cid = random.choice(mc_customers) if mc_customers else random.choice(cids)
        else:
            cid = random.choice(non_mc_customers) if non_mc_customers else random.choice(cids)

        etype = random.choices(ENGAGEMENT_TYPES, weights=ENGAGEMENT_W)[0]
        if payment_map.get(cid) == "Mastercard":
            points = random.randint(50, 800) if etype in ("Points Earn", "Points Redeem") else 0
        else:
            points = random.randint(10, 200) if etype in ("Points Earn", "Points Redeem") else 0

        engagements.append({
            "engagement_id":       f"ENG{i+1:06d}",
            "customer_id":         cid,
            "engagement_date":     iso(rand_date()),
            "engagement_type":     etype,
            "points_value":        points,
            "channel":             random.choices(CHANNELS, weights=CHANNEL_W)[0],
            "session_duration_sec": (random.randint(30, 1800)
                                     if etype in ("App Login", "Promo Click") else 0),
            "conversion_flag":     (random.choices([1, 0], weights=[0.35, 0.65])[0]
                                    if etype == "Promo Click" else 0),
        })
    eng_df = pd.DataFrame(engagements)
    save(eng_df, "raw_10_program_engagement")

    # ══════════════════════════════════════════════════════════════════════════
    # DQ AUDIT — raw_05_transactions
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  DATA QUALITY AUDIT — raw_05_transactions")
    print("=" * 70)
    print(f"\n  Total rows in file:              {len(txn_df):>6,}  (8,000 base + 400 dupes)")

    # 1. Duplicates (exact: 400 rows share an existing transaction_id)
    dup_count = txn_df.duplicated("transaction_id").sum()
    dup_ok    = "✅" if dup_count == N_DUPLICATES else "⚠️ "
    print(f"\n  1. Duplicate transaction_ids:    {dup_count:>5,}  {dup_ok}  (target: {N_DUPLICATES})")

    # 2. NULL amounts (exact: 400)
    null_count = txn_df["amount"].isna().sum()
    null_ok    = "✅" if null_count == N_NULL_REVENUE else "⚠️ "
    print(f"  2. NULL amounts:                 {null_count:>5,}  {null_ok}  (target: {N_NULL_REVENUE})")

    # 3. CAD-formatted amounts (exact: 150)
    cad_count  = txn_df["amount"].dropna().astype(str).str.contains("CAD", na=False).sum()
    cad_ok     = "✅" if cad_count == N_CAD_FORMAT else "⚠️ "
    print(f"  3. 'CAD' formatted amounts:      {cad_count:>5,}  {cad_ok}  (target: {N_CAD_FORMAT})")

    # 4. Non-ISO dates MM-DD-YYYY (exact: 400)
    iso_mask    = txn_df["transaction_date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")
    dirty_dates = (~iso_mask).sum()
    date_ok     = "✅" if dirty_dates == N_DATE_DIRTY else "⚠️ "
    print(f"  4. Non-ISO dates (MM-DD-YYYY):   {dirty_dates:>5,}  {date_ok}  (target: {N_DATE_DIRTY})")

    # 5. Clean rows (numeric string, non-null, non-CAD, ISO date)
    clean_mask = (
        txn_df["amount"].notna() &
        ~txn_df["amount"].astype(str).str.contains("CAD", na=False) &
        txn_df["transaction_date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")
    )
    clean_count = clean_mask.sum()
    expected_clean = N_TOTAL - N_NULL_REVENUE - N_CAD_FORMAT - N_DATE_DIRTY
    print(f"\n  5. Fully clean rows (no issue):  {clean_count:>5,}  "
          f"(≈ {N_TOTAL} - {N_NULL_REVENUE} NULL - {N_CAD_FORMAT} CAD - {N_DATE_DIRTY} dirty-date)")

    # ── Cleanliness check on all other tables ─────────────────────────────
    print("\n" + "-" * 70)
    print("  CLEANLINESS CHECK — All other tables (should be 100% clean)")
    print("-" * 70)
    checks = [
        ("raw_01_customers",          cust_df,   None),
        ("raw_02_customer_addresses", addr_df,   None),
        ("raw_03_payment_accounts",   pay_df,    None),
        ("raw_04_card_applications",  app_df,    None),
        ("raw_06_transaction_items",  items_df,  None),
        ("raw_07_products",           prod_df,   None),
        ("raw_08_store_directory",    store_df,  None),
        ("raw_09_satisfaction_surveys", survey_df, ["nps_score"]),  # design nulls
        ("raw_10_program_engagement", eng_df,    None),
    ]
    all_pass = True
    for name, df, exclude_cols in checks:
        check_df  = df.drop(columns=exclude_cols) if exclude_cols else df
        null_total = check_df.isnull().sum().sum()
        ok         = null_total == 0
        icon       = "✅" if ok else "❌"
        note       = f"  (excl. {exclude_cols})" if exclude_cols else ""
        print(f"  {icon} {name:<40} {null_total} nulls{note}")
        if not ok:
            all_pass = False

    print(f"\n  {'All 9 other tables are fully clean ✅' if all_pass else 'Some tables have unexpected nulls ❌'}")

    # ══════════════════════════════════════════════════════════════════════════
    # MASTERCARD ROI SIGNAL CHECK
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  MASTERCARD ROI SIGNAL VERIFICATION")
    print("=" * 70)

    mc_cids     = set(cust_df[cust_df["primary_payment"] == "Mastercard"]["customer_id"])
    non_mc_cids = set(cust_df[cust_df["primary_payment"] != "Mastercard"]["customer_id"])

    print(f"\n  Customer Split:")
    print(f"    Mastercard holders:      {len(mc_cids):>5,}  ({len(mc_cids)/N_CUSTOMERS*100:.0f}%)")
    print(f"    Non-Mastercard:          {len(non_mc_cids):>5,}  ({len(non_mc_cids)/N_CUSTOMERS*100:.0f}%)")

    mc_txn_count     = txn_df[txn_df["customer_id"].isin(mc_cids)].shape[0]
    non_mc_txn_count = txn_df[txn_df["customer_id"].isin(non_mc_cids)].shape[0]
    print(f"\n  Transaction Volume (incl. dupes):")
    print(f"    MC avg txns/customer:    {mc_txn_count / max(len(mc_cids), 1):.1f}")
    print(f"    Non-MC avg txns/cust:    {non_mc_txn_count / max(len(non_mc_cids), 1):.1f}")

    # Avg spend on clean numeric rows only
    clean_txn = txn_df[
        txn_df["amount"].notna() &
        ~txn_df["amount"].astype(str).str.contains("CAD", na=False)
    ].copy()
    clean_txn["amount_num"] = pd.to_numeric(clean_txn["amount"], errors="coerce")
    clean_txn = clean_txn[clean_txn["amount_num"].notna()]

    mc_avg     = clean_txn[clean_txn["customer_id"].isin(mc_cids)]["amount_num"].mean()
    non_mc_avg = clean_txn[clean_txn["customer_id"].isin(non_mc_cids)]["amount_num"].mean()
    print(f"\n  Average Spend (clean records only):")
    print(f"    MC avg spend:            ${mc_avg:.2f}")
    print(f"    Non-MC avg spend:        ${non_mc_avg:.2f}")
    print(f"    MC spend uplift:         +{((mc_avg / non_mc_avg) - 1) * 100:.0f}%")

    mc_eng     = eng_df[eng_df["customer_id"].isin(mc_cids)].shape[0]
    non_mc_eng = eng_df[eng_df["customer_id"].isin(non_mc_cids)].shape[0]
    print(f"\n  Program Engagement:")
    print(f"    MC engagement share:     {mc_eng/len(eng_df)*100:.0f}%")
    print(f"    Non-MC engagement:       {non_mc_eng/len(eng_df)*100:.0f}%")

    # ══════════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    total_rows = sum([
        len(cust_df), len(addr_df), len(pay_df), len(app_df),
        len(txn_df), len(items_df), len(prod_df), len(store_df),
        len(survey_df), len(eng_df),
    ])

    print("\n" + "=" * 70)
    print(f"  ✅  Done — {total_rows:,} total rows across 10 tables")
    print(f"       raw_05_transactions: {len(txn_df):,} rows "
          f"({N_TXN_BASE:,} base + {N_DUPLICATES} dupes)")
    print("=" * 70)

    print("""
  Staging Consolidation Map (10 raw → 4 dim + 2 fact):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  DIMENSIONS                                                              │
  │  raw_01 + raw_02 + raw_03     →  dim_customer                           │
  │  raw_07                       →  dim_product   (direct load)            │
  │  raw_08                       →  dim_store     (direct load)            │
  │  raw_04                       →  dim_card_program                       │
  │                                                                          │
  │  FACTS                                                                   │
  │  raw_05 + raw_06              →  fact_transactions                      │
  │    Cleaning tasks:                                                       │
  │    • Deduplicate 400 rows on transaction_id                              │
  │    • Standardize 400 dates MM-DD-YYYY → YYYY-MM-DD                      │
  │    • Strip " CAD" from 150 amounts, cast to numeric                      │
  │    • Quarantine or exclude 400 NULL amounts                              │
  │    • Join line items on transaction_id                                   │
  │                                                                          │
  │  raw_09 + raw_10              →  fact_customer_engagement                │
  │    (union surveys + engagement — both clean)                             │
  └──────────────────────────────────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()