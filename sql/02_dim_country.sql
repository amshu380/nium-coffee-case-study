DROP TABLE IF EXISTS analytics.dim_country CASCADE;

CREATE TABLE analytics.dim_country AS
SELECT
    iso3_code,
    english_name AS country_name,
    iso2_code,
    NULLIF(region::text, '') AS region,
    NULLIF(sub_region::text, '') AS sub_region,
    NULLIF(continent::text, '') AS continent
FROM raw.country_codes
WHERE iso3_code IS NOT NULL;

CREATE INDEX idx_dim_country_iso3 ON analytics.dim_country (iso3_code);

ALTER TABLE analytics.dim_country ADD PRIMARY KEY (iso3_code);
