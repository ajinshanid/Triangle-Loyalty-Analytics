-- ============================================================
-- STG: dim_customer
-- Source : raw.raw_01_customers
--          raw.raw_02_customer_addresses
--          raw.raw_03_payment_accounts
-- Grain  : One row per customer_id
-- Notes  : Raw landing layer - NO cleaning applied here.
--          Power Query then casts types and derives `is_cardholder`
--          from `account_status`.
-- ============================================================
CREATE TABLE staging.dim_customer AS
SELECT
    d.customer_id,           -- grain / -> fact_transactions
    a.city,                  -- Top Cities visual
    a.province,              -- Province slicer
    a.region,                -- geographic rollup (optional cut)
    p.card_tier,             -- Card Tier slicer + tier scatter
    p.account_status         -- -> derive is_cardholder in Power Query
FROM raw.raw_01_customers d
LEFT JOIN raw.raw_02_customer_addresses a
    ON a.customer_id = d.customer_id
LEFT JOIN raw.raw_03_payment_accounts p
    ON p.customer_id = d.customer_id;

SELECT * FROM staging.dim_customer LIMIT 10;