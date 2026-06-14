# Triangle Loyalty Analytics
### Customer Loyalty & Cardholder Performance Dashboard — Python (Faker) | SQL | Power Query | DAX | Power BI


---

## Business Objective

A loyalty analytics dashboard built to help a retailer **quantify the incremental value of its rewards program** and decide where to direct acquisition and reward spend. It enables stakeholders to:

- Measure how enrolled cardholders perform against non-cardholders across seasons, cities, card tiers, and channels
- Isolate the true incremental spend the program drives — not just gross revenue
- Identify which card tiers and channels return the most revenue per reward dollar
- Target seasonal campaigns and acquisition at the segments and regions with the most upside

> *Note:* This is a hypothetical loyalty program on synthetic data (Python/Faker), with realistic data-quality defects intentionally seeded to demonstrate a production-style validation pipeline.

---

## Target Audience & Value

**Audience**
- **Loyalty / CRM Managers:** Set enrollment targets and reward budgets
- **Marketing:** Aim seasonal campaigns at the segments that actually respond
- **Finance / Merchandising:** Watch reward cost-to-revenue by tier for margin leaks

**Value**
- KPI cards give an immediate read on revenue, enrollment share, and basket size
- Cardholder-vs-non-cardholder splits make the program's incremental value visible at a glance
- Tier and channel views surface where reward spend is efficient and where it leaks

---

## Tech Stack

The stack is listed in pipeline order — each stage's output feeds the next:

1. **Python (Faker)** — *Generate.* Produced the synthetic retail loyalty dataset (transactions, customers, stores) using Faker with an LLM-assisted setup.
2. **SQL (PostgreSQL)** — *Raw staging.* Landed the raw Faker CSV output into staging tables and ran SQL to profile and extract the data. PostgreSQL is the raw landing zone only — no cleaning or modeling happens here.
3. **Power Query** — *Clean + model.* Deduplicated line items to transaction grain, quarantined invalid rows, standardized types/dates/amounts, derived columns, and shaped the staging tables into the dimension & fact (star schema) tables.
4. **DAX** — *Measure.* The semantic layer — measures and calculated columns (revenue, cardholder %, cashback per customer, the season axis) that turn the model into reportable metrics.
5. **Power BI** — *Visualize.* The reporting environment that holds the star-schema relationships and renders the interactive dashboard (slicers, cross-filtering, and the four visuals).

**Pipeline:**
```
Python (Faker) ➔ Raw CSVs ➔ PostgreSQL (Raw Staging) ➔ Power Query (Clean + Model) ➔ Power BI (DAX)
```

Raw CSVs are loaded into **PostgreSQL** as untouched staging tables — the raw landing zone. **Power Query** then runs the full clean-and-model layer against those tables: collapsing the line-item rows to transaction grain (deduplicating on `transaction_id`), standardizing the CAD-suffixed amounts (e.g. `647.52 CAD`) and `MM-DD-YYYY` dates, routing transactions with no valid amount line to a quarantine query, and shaping the validated result into the dim/fact star schema — so only clean, modeled rows reach the report. The star-schema relationships are then wired up in the **Power BI** model. All data-quality defects were isolated to `raw_05_transactions`; every other source table loaded clean.

---

## Data Model

A star schema centered on a single transaction fact with two dimensions. Keys shown as PK (primary) / FK (foreign):

- **`fact_transactions`** — one row per transaction: `transaction_id` (PK), `customer_id` (FK), `store_id` (FK), `transaction_date` (Date), `Total Amount`, `cashback_earned`, `channel`
- **`dim_customers`** — `customer_id` (PK), `Cardholder Status` (derived from `account_status`), `card_tier`, `city`, `province`
- **`dim_store`** — `store_id` (PK), `store_type`, `city`, `province`

**Data quality & quarantine:** All data quality issues were isolated to `raw_05_transactions` — every other source table (`dim_customers`, `dim_store`, and the remaining raw tables) loaded **100% clean**, with no nulls or formatting issues. All cleaning, deduplication, and quarantine logic runs in **Power Query** against the PostgreSQL staging tables. Records failing validation were isolated into a quarantine set rather than silently dropped, keeping the load fully auditable:

- PostgreSQL staging held **9,644 raw rows** from `raw_05_transactions` at line-item grain (one row per `item_id`).
- Power Query removed **duplicate line items** and collapsed to transaction grain on `transaction_id`, leaving **8,000 distinct transactions**.
- Standardized **~180 amount values** stored as CAD text (e.g. `"647.52 CAD"`) back to numeric, and reformatted **~5% of `transaction_date` values** from `MM-DD-YYYY` to ISO `YYYY-MM-DD` — correcting rows **in place** rather than dropping them.
- **400 transactions carried at least one missing-amount line item** (~5%). The **377** with no salvageable line were **quarantined** and excluded from the model; the remaining **23** recovered a valid amount from another line item during the collapse to transaction grain, so the transaction was retained.
- The remaining **7,623 clean transactions** were loaded into `fact_transactions` — matching the Total Transactions KPI exactly (**8,000 distinct − 377 quarantined = 7,623**).
- Confirmed zero orphaned rows: every `transaction_id` in the fact resolves to a staging record, and every `customer_id` and `store_id` resolves to its dimension.

---

## Key DAX Measures

```DAX
Total Revenue = SUM ( fact_transactions[Total Amount] )
Total Transactions = COUNTROWS ( fact_transactions )
Avg Transaction Value = DIVIDE ( [Total Revenue], [Total Transactions] )

Cardholder % =
DIVIDE (
    CALCULATE ( [Total Revenue], dim_customers[Cardholder Status] = "Cardholder" ),
    [Total Revenue]
)

Cashback per Customer =
DIVIDE (
    SUM ( fact_transactions[cashback_earned] ),
    DISTINCTCOUNT ( dim_customers[customer_id] )
)
```

**Calculated columns.** `Cardholder Status` flags each customer as a cardholder when their account is active; the season/year columns build the line-chart axis from the transaction date.

```DAX
-- Cardholder flag (calculated column on dim_customers)
Cardholder Status =
IF ( dim_customers[account_status] = "Active", "Cardholder", "Non-Cardholder" )

-- Axis label, e.g. "2022 Spring" (season folded in via VAR)
txn_season_year =
VAR y = YEAR ( fact_transactions[transaction_date] )
VAR m = MONTH ( fact_transactions[transaction_date] )
VAR s =
    SWITCH ( TRUE (),
        m IN { 3, 4, 5 },   "Spring",
        m IN { 6, 7, 8 },   "Summer",
        m IN { 9, 10, 11 }, "Fall",
        "Winter"
    )
RETURN y & " " & s

-- Sort key so seasons order chronologically, not alphabetically
txn_season_year_sort =
VAR y = YEAR ( fact_transactions[transaction_date] )
VAR m = MONTH ( fact_transactions[transaction_date] )
VAR s =
    SWITCH ( TRUE (),
        m IN { 3, 4, 5 },   1,
        m IN { 6, 7, 8 },   2,
        m IN { 9, 10, 11 }, 3,
        4
    )
RETURN y * 10 + s
```

> Set `txn_season_year` to **Sort by column = `txn_season_year_sort`** so the axis runs 2022 Spring → 2024 Winter instead of alphabetically.

> *Note:* Season is folded directly into `txn_season_year` rather than a separate `Season` column; both sit on the fact table here for simplicity, but in a production model they would live in a dedicated `dim_date` (Calendar) table.

---

## KPIs

| KPI | Value |
|-----|-------|
| Total Revenue | $2.09M |
| Total Transactions | 7,623 |
| Cardholder % | 79.16% |
| Avg Transaction Value | $274.70 |

---

## Dashboard

Visuals are arranged to move from the overall trend down to the segments you can act on — the seasonal revenue trend sets context first, then the layout drills into *where* that revenue sits (cities, card tiers, channels).

- **Slicers:** Province | Store Type | Card Tier | Season
- **Seasonal Revenue by Cardholder Status** (line) — revenue trend, cardholder vs non-cardholder, 2022 Spring → 2024 Winter
- **Top Cities by Revenue and Cardholder Status** (bar) — Quebec City, Halifax, Mississauga, Red Deer, Ottawa, Lethbridge
- **Loyalty Efficiency by Card Tier** (scatter) — Total Revenue vs Cashback per Customer across Standard, Gold, Platinum, World Elite
- **Revenue by Channel and Cardholder Status** (stacked bar) — In-Store, Online, Mobile App

---

## Key Insights & Recommended Actions

| Finding | Recommended Action |
|---------|--------------------|
| **Cardholders are the revenue engine** — they drive 79.16% of revenue and sit above non-cardholders in every season. | Make enrollment the top growth lever; track incremental spend per new cardholder. |
| **Seasonality lives in the cardholder base** — cardholder revenue spikes in winter while non-cardholder revenue stays flat. | Aim seasonal campaigns and stock build-up at cardholders ahead of winter peaks. |
| **Geographic penetration is uneven** — Quebec City leads on revenue; the cardholder gap is wide in Red Deer (mature) and tight in Mississauga (untapped). | Defend high-penetration cities; run acquisition where the non-cardholder base is large. |
| **Reward efficiency falls as tier rises** — Standard earns the most revenue at the lowest cashback per customer; World Elite costs the most per customer for less revenue. | Rebalance premium rewards or tie them to spend thresholds so cost scales with revenue (est. 2–5% margin recovery — illustrative, to validate against actuals). |
| **Digital is where loyalty compounds** — In-Store leads on volume, but cardholders concentrate in the under-scaled Online and Mobile App channels. | Invest in app/online experiences to scale high-value cardholder behavior at lower cost. |

---

## Summary

This project delivers an end-to-end loyalty analytics solution, moving a synthetic dataset from raw, defect-laden source files to a decision-ready Power BI report. The data is landed as raw staging tables in **PostgreSQL**, then cleaned, standardized, and modeled into a dim/fact star schema in **Power Query**, and surfaced through **DAX** measures in **Power BI** — with every transaction reconciled to the reported KPIs to ensure accuracy and traceability. The analysis quantifies the value of enrolled cardholders relative to non-cardholders and identifies the most effective allocation of acquisition and reward spend across season, city, card tier, and channel. Each finding is paired with a specific, actionable recommendation, and every visual is tied to a defined business question, ensuring the report supports operational and strategic decisions rather than presentation alone.

---

## Project Structure

```
Triangle-Loyalty-Analytics/
├── data/        <- Faker-generated dataset
├── sql/         <- PostgreSQL raw-staging scripts
├── dashboard/   <- Triangle_Loyalty_Analytics.pbix
├── visuals/     <- Dashboard screenshot
└── README.md
```
