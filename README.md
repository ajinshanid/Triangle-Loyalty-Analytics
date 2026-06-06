# Triangle Loyalty Analytics
### Customer Loyalty & Cardholder Performance Dashboard - Python (Faker) | SQL | Power Query | DAX | Power BI


---

## Business Objective

A loyalty analytics dashboard built to help a retailer **quantify the incremental value of its rewards program** and decide where to direct acquisition and reward spend. It enables stakeholders to:

- Measure how enrolled cardholders perform against non-cardholders across seasons, cities, card tiers, and channels
- Isolate the true incremental spend the program drives - not just gross revenue
- Identify which card tiers and channels return the most revenue per reward dollar
- Target seasonal campaigns and acquisition at the segments and regions with the most upside

> *Fictional loyalty program on synthetic data (Python/Faker), with realistic data-quality defects intentionally seeded to demonstrate a production-style validation pipeline.*

---

## Target Audience & Value

**Audience**
- **Loyalty / CRM Managers** - set enrollment targets and reward budgets
- **Marketing** - aim seasonal campaigns at the segments that actually respond
- **Finance / Merchandising** - watch reward cost-to-revenue by tier for margin leaks

**Value**
- KPI cards give an immediate read on revenue, enrollment share, and basket size
- Cardholder-vs-non-cardholder splits make the program's incremental value visible at a glance
- Tier and channel views surface where reward spend is efficient and where it leaks

---

## Tech Stack

- **Python (Faker):** Generated a synthetic retail loyalty dataset (transactions, customers, stores) using Faker with an LLM-assisted setup
- **SQL (PostgreSQL):** Used PostgreSQL as the database to land the raw Faker output and extract the staging data for analysis, then modeled it into a **dimension & fact (star schema)** for clean, query-ready analysis
- **Power Query:** Cleaned, standardized, and shaped the source tables (types, nulls, deduplication, derived columns) before load
- **DAX:** Built the core measures that power the KPIs and visuals
- **Power BI:** Built the interactive report

**Pipeline:**
```
Python (Faker) -> Raw CSVs -> PostgreSQL (raw + staging + star-schema modeling) -> Power Query (clean: dedup + quarantine) -> Power BI (DAX)
```

Raw CSVs are loaded into **PostgreSQL** as staging tables and modeled into the dim/fact star schema; Power Query then runs the cleaning layer against those tables - collapsing the line-item rows to transaction grain (deduplicating on `transaction_id`), standardizing the `CAD`-formatted amounts and `MM-DD-YYYY` dates, and routing the missing-amount transactions to a quarantine query - so only validated rows reach the report. All data quality issues were isolated to `raw_05_transactions`; every other source table loaded clean.

---

## Data Model

A star schema centered on a single transaction fact with two dimensions. Keys shown as PK (primary) / FK (foreign):

- **`fact_transactions`** - one row per transaction: `transaction_id` (PK), `customer_id` (FK), `store_id` (FK), `transaction_date` (Date), `Total Amount`, `cashback_earned`, `channel`
- **`dim_customers`** - `customer_id` (PK), `Cardholder Status` (derived from `account_status`), `card_tier`, `city`, `province`
- **`dim_store`** - `store_id` (PK), `store_type`, `city`, `province`

**Data quality & quarantine:** All data quality issues were isolated to `raw_05_transactions` - every other source table (`dim_customers`, `dim_store`, and the remaining raw tables) loaded **100% clean**, with no nulls or formatting issues. Records failing validation were isolated into a quarantine set rather than silently dropped, keeping the load fully auditable:

- Staging held **9,644 raw rows** from `raw_05_transactions` at line-item grain (one row per `item_id`).
- Removed **duplicate line items** and collapsed to transaction grain on `transaction_id`, leaving **8,000 distinct transactions**.
- Standardized **~150 amount values** stored as `CAD` text (e.g. `"CAD 240.00"`) back to numeric, and reformatted **~5% of `transaction_date` values** from `MM-DD-YYYY` to ISO `YYYY-MM-DD` - both correct rows **in place** rather than dropping them.
- **377 transactions with a missing amount** (~5%) were quarantined and excluded from the model.
- The remaining **7,623 clean transactions** were loaded into `fact_transactions` - matching the Total Transactions KPI exactly.
- Confirmed zero orphaned rows: every `customer_id` and `store_id` in the fact resolves to its dimension.

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

> Set `txn_season_year` to **Sort by column = `txn_season_year_sort`** so the axis runs 2022 Spring -> 2024 Winter instead of alphabetically.

> *Note:* season is folded directly into `txn_season_year` rather than a separate `Season` column; both sit on the fact table here for simplicity, but in a production model they would live in a dedicated `dim_date` (Calendar) table.

---

## KPIs

| KPI | Value |
|-----|-------|
| Total Revenue | 2.09M |
| Total Transactions | 7,623 |
| Cardholder % | 79.16% |
| Avg Transaction Value | $274.70 |

---

## Dashboard

Visuals are arranged to move from the overall trend down to the segments you can act on - the seasonal revenue trend sets context first, then the layout drills into *where* that revenue sits (cities, card tiers, channels).

- **Slicers:** Province | Store Type | Card Tier | Season
- **Seasonal Revenue by Cardholder Status** (line) - revenue trend, cardholder vs non-cardholder, 2022 Spring -> 2024 Winter
- **Top Cities by Revenue and Cardholder Status** (bar) - Quebec City, Halifax, Mississauga, Red Deer, Ottawa, Lethbridge
- **Loyalty Efficiency by Card Tier** (scatter) - Total Revenue vs Cashback per Customer across Standard, Gold, Platinum, World Elite
- **Revenue by Channel and Cardholder Status** (stacked bar) - In-Store, Online, Mobile App

---

## Key Insights & Recommended Actions

| Finding | Recommended Action |
|---------|--------------------|
| **Cardholders are the revenue engine** - they drive 79.16% of revenue and sit above non-cardholders in every season. | Make enrollment the top growth lever; track incremental spend per new cardholder. |
| **Seasonality lives in the cardholder base** - cardholder revenue spikes in winter while non-cardholder revenue stays flat. | Aim seasonal campaigns and stock build-up at cardholders ahead of winter peaks. |
| **Geographic penetration is uneven** - Quebec City leads on revenue; the cardholder gap is wide in Red Deer (mature) and tight in Mississauga (untapped). | Defend high-penetration cities; run acquisition where the non-cardholder base is large. |
| **Reward efficiency falls as tier rises** - Standard earns the most revenue at the lowest cashback per customer; World Elite costs the most per customer for less revenue. | Rebalance premium rewards or tie them to spend thresholds so cost scales with revenue (est. 2-5% margin recovery - illustrative, to validate against actuals). |
| **Digital is where loyalty compounds** - In-Store leads on volume, but cardholders concentrate in the under-scaled Online and Mobile App channels. | Invest in app/online experiences to scale high-value cardholder behavior at lower cost. |

---

## Summary

This project takes a loyalty dataset from raw, defect-laden CSVs through a validated PostgreSQL star schema and into an interactive Power BI report, with every row reconciled to the headline KPIs. The analysis centers on one question a loyalty team actually faces - *what is a cardholder worth, and where should we spend to get more of them* - and turns each finding into a concrete action across enrollment, seasonal campaigns, regional acquisition, reward-tier economics, and digital channels. The emphasis throughout is on an auditable pipeline and decision-ready insight rather than charts for their own sake.

---


## Project Structure

```
Triangle-Loyalty-Analytics/
|-- data/ <- Faker-generated dataset
|-- sql/ <- Star schema (dim & fact) scripts
|-- dashboard/ <- Triangle_Loyalty_Analytics.pbix
|-- assets/ <- Dashboard screenshot
\-- README.md
```

---

## Author

**[Your Name]** - [LinkedIn](#) | [Portfolio](#)
