DROP TABLE IF EXISTS analytics.fact_population CASCADE;

CREATE TABLE analytics.fact_population AS
SELECT
    iso3_code,
    year,
    population
FROM raw.population
WHERE iso3_code IS NOT NULL AND population IS NOT NULL;

CREATE INDEX idx_fact_pop_iso3 ON analytics.fact_population (iso3_code);
CREATE INDEX idx_fact_pop_year ON analytics.fact_population (year);
ALTER TABLE analytics.fact_population ADD PRIMARY KEY (iso3_code, year);

ALTER TABLE analytics.fact_population
    ADD CONSTRAINT fk_fact_pop_country
    FOREIGN KEY (iso3_code) REFERENCES analytics.dim_country (iso3_code);
