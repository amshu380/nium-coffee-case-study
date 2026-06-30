DROP VIEW IF EXISTS analytics.v_country_year_metrics CASCADE;

CREATE VIEW analytics.v_country_year_metrics AS
SELECT
    c.iso3_code,
    dc.country_name,
    dc.region,
    dc.sub_region,
    dc.continent,
    c.market_year,
    c.domestic_consumption,
    c.production,
    c.bean_imports,
    c.bean_exports,
    p.population,
    -- Per-capita: kg per person per year. USDA unit is 1000 60kg bags = 60000 kg.
    CASE
        WHEN p.population > 0 AND c.domestic_consumption IS NOT NULL
        THEN (c.domestic_consumption * 60000.0) / p.population
        ELSE NULL
    END AS per_capita_kg_per_person,
    -- Per-capita: bags per 1000 people. Equivalent metric, alternate scale.
    CASE
        WHEN p.population > 0 AND c.domestic_consumption IS NOT NULL
        THEN (c.domestic_consumption * 1000000.0) / p.population
        ELSE NULL
    END AS per_capita_bags_per_1000,
    CASE
        WHEN c.bean_imports IS NOT NULL AND c.bean_exports IS NOT NULL
        THEN c.bean_imports - c.bean_exports
        ELSE NULL
    END AS net_bean_imports,
    CASE
        WHEN c.domestic_consumption > 0 AND c.bean_imports IS NOT NULL
        THEN c.bean_imports::numeric / c.domestic_consumption
        ELSE NULL
    END AS import_dependency_ratio
FROM analytics.fact_coffee c
JOIN analytics.dim_country dc ON c.iso3_code = dc.iso3_code
LEFT JOIN analytics.fact_population p ON c.iso3_code = p.iso3_code AND c.market_year = p.year;

DROP VIEW IF EXISTS analytics.v_country_growth_metrics CASCADE;

CREATE VIEW analytics.v_country_growth_metrics AS
WITH consumption_history AS (
    SELECT
        iso3_code,
        market_year,
        domestic_consumption,
        LAG(domestic_consumption, 5) OVER (PARTITION BY iso3_code ORDER BY market_year) AS consumption_5y_ago,
        LAG(domestic_consumption, 10) OVER (PARTITION BY iso3_code ORDER BY market_year) AS consumption_10y_ago
    FROM analytics.fact_coffee
    WHERE domestic_consumption IS NOT NULL AND domestic_consumption > 0
)
SELECT
    iso3_code,
    market_year,
    domestic_consumption,
    consumption_5y_ago,
    consumption_10y_ago,
    CASE
        WHEN consumption_5y_ago > 0
        THEN POWER(domestic_consumption::numeric / consumption_5y_ago, 1.0/5.0) - 1
        ELSE NULL
    END AS consumption_cagr_5y,
    CASE
        WHEN consumption_10y_ago > 0
        THEN POWER(domestic_consumption::numeric / consumption_10y_ago, 1.0/10.0) - 1
        ELSE NULL
    END AS consumption_cagr_10y
FROM consumption_history;

DROP VIEW IF EXISTS analytics.v_latest_year_snapshot CASCADE;

CREATE VIEW analytics.v_latest_year_snapshot AS
WITH latest_year AS (
    SELECT iso3_code, MAX(market_year) AS latest_year
    FROM analytics.v_country_year_metrics
    WHERE domestic_consumption IS NOT NULL AND population IS NOT NULL
    GROUP BY iso3_code
)
SELECT
    m.iso3_code,
    m.country_name,
    m.region,
    m.continent,
    m.market_year,
    m.domestic_consumption,
    m.production,
    m.bean_imports,
    m.bean_exports,
    m.population,
    m.per_capita_kg_per_person,
    m.per_capita_bags_per_1000,
    m.net_bean_imports,
    m.import_dependency_ratio,
    g.consumption_cagr_5y,
    g.consumption_cagr_10y
FROM analytics.v_country_year_metrics m
JOIN latest_year ly ON m.iso3_code = ly.iso3_code AND m.market_year = ly.latest_year
LEFT JOIN analytics.v_country_growth_metrics g ON m.iso3_code = g.iso3_code AND m.market_year = g.market_year;

DROP VIEW IF EXISTS analytics.v_global_trends CASCADE;

CREATE VIEW analytics.v_global_trends AS
SELECT
    market_year,
    SUM(domestic_consumption) AS total_consumption,
    SUM(production) AS total_production,
    SUM(bean_imports) AS total_bean_imports,
    SUM(bean_exports) AS total_bean_exports,
    COUNT(DISTINCT iso3_code) AS reporting_countries
FROM analytics.fact_coffee
GROUP BY market_year
ORDER BY market_year;
