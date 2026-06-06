-- ============================================================
-- STG: dim_store
-- Source : raw.raw_08_store_directory
-- Grain  : One row per store_id
-- Notes  : Raw landing layer - NO cleaning applied here.
--          raw_08 is generated 100% clean (no DQ issues).
--          Power Query only casts types.
--          Dropped: store_name (label), open_date + sq_footage
--          (operational - no visual uses them).
-- ============================================================
CREATE TABLE staging.dim_store AS
SELECT
    s.store_id,              -- grain / -> fact_transactions
    s.store_type,            -- Store Type slicer
    s.city,                  -- store-location cut
    s.province               -- store-location cut
FROM raw.raw_08_store_directory s;

SELECT * FROM staging.dim_store LIMIT 10;