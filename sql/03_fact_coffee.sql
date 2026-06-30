-- Kept metric mappings:
--   domestic_consumption <- Domestic Consumption
--   production <- Production
--   bean_imports <- Bean Imports
--   bean_exports <- Bean Exports
--   ending_stocks <- Ending Stocks
--   beginning_stocks <- Beginning Stocks
--   roast_ground_imports <- Roast & Ground Imports
--   roast_ground_exports <- Roast & Ground Exports
--   soluble_imports <- Soluble Imports
--   soluble_exports <- Soluble Exports
-- Dropped metrics:
--   None
DROP TABLE IF EXISTS analytics.fact_coffee CASCADE;

CREATE TABLE analytics.fact_coffee AS
SELECT
    iso3_code,
    market_year,
    MAX(CASE WHEN attribute_description = 'Domestic Consumption' THEN value END) AS domestic_consumption,
    MAX(CASE WHEN attribute_description = 'Production' THEN value END) AS production,
    MAX(CASE WHEN attribute_description = 'Bean Imports' THEN value END) AS bean_imports,
    MAX(CASE WHEN attribute_description = 'Bean Exports' THEN value END) AS bean_exports,
    MAX(CASE WHEN attribute_description = 'Ending Stocks' THEN value END) AS ending_stocks,
    MAX(CASE WHEN attribute_description = 'Beginning Stocks' THEN value END) AS beginning_stocks,
    MAX(CASE WHEN attribute_description = 'Roast & Ground Imports' THEN value END) AS roast_ground_imports,
    MAX(CASE WHEN attribute_description = 'Roast & Ground Exports' THEN value END) AS roast_ground_exports,
    MAX(CASE WHEN attribute_description = 'Soluble Imports' THEN value END) AS soluble_imports,
    MAX(CASE WHEN attribute_description = 'Soluble Exports' THEN value END) AS soluble_exports
FROM raw.coffee
WHERE iso3_code IS NOT NULL
GROUP BY iso3_code, market_year
HAVING COUNT(value) > 0;

CREATE INDEX idx_fact_coffee_iso3 ON analytics.fact_coffee (iso3_code);
CREATE INDEX idx_fact_coffee_year ON analytics.fact_coffee (market_year);
ALTER TABLE analytics.fact_coffee ADD PRIMARY KEY (iso3_code, market_year);

ALTER TABLE analytics.fact_coffee
    ADD CONSTRAINT fk_fact_coffee_country
    FOREIGN KEY (iso3_code) REFERENCES analytics.dim_country (iso3_code);
