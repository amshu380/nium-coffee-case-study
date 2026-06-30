CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Reference table of ISO country codes derived from the raw country codes CSV.
CREATE TABLE IF NOT EXISTS raw.country_codes (
    iso3_code TEXT,
    iso2_code TEXT,
    english_name TEXT,
    region DOUBLE PRECISION,
    sub_region DOUBLE PRECISION,
    continent DOUBLE PRECISION
);

-- Clean USDA PSD coffee records mapped to ISO3 country codes.
CREATE TABLE IF NOT EXISTS raw.coffee (
    iso3_code TEXT,
    country_name TEXT,
    market_year BIGINT,
    attribute_id BIGINT,
    attribute_description TEXT,
    value DOUBLE PRECISION,
    unit_description TEXT
);

-- Long-form World Bank population records filtered to valid ISO3 country codes.
CREATE TABLE IF NOT EXISTS raw.population (
    country_name TEXT,
    iso3_code TEXT,
    year BIGINT,
    population DOUBLE PRECISION
);
