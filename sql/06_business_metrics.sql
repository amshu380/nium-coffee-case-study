DROP VIEW IF EXISTS analytics.v_market_attractiveness CASCADE;

CREATE VIEW analytics.v_market_attractiveness AS
WITH base AS (
    SELECT * FROM analytics.v_latest_year_snapshot
    WHERE domestic_consumption IS NOT NULL
      AND population IS NOT NULL
      AND domestic_consumption > 0
),
ranked AS (
    SELECT
        iso3_code,
        country_name,
        region,
        continent,
        market_year,
        domestic_consumption,
        per_capita_kg_per_person,
        consumption_cagr_5y,
        consumption_cagr_10y,
        population,
        import_dependency_ratio,
        PERCENT_RANK() OVER (ORDER BY domestic_consumption) AS size_score,
        PERCENT_RANK() OVER (ORDER BY COALESCE(consumption_cagr_5y, -1)) AS growth_score,
        PERCENT_RANK() OVER (ORDER BY population) AS population_score,
        PERCENT_RANK() OVER (ORDER BY COALESCE(import_dependency_ratio, 0)) AS import_openness_score
    FROM base
)
SELECT
    iso3_code,
    country_name,
    region,
    continent,
    market_year,
    domestic_consumption,
    per_capita_kg_per_person,
    consumption_cagr_5y,
    population,
    import_dependency_ratio,
    size_score,
    growth_score,
    population_score,
    import_openness_score,
    (0.35 * size_score + 0.30 * growth_score + 0.20 * population_score + 0.15 * import_openness_score) AS composite_score
FROM ranked
ORDER BY composite_score DESC;

DROP VIEW IF EXISTS analytics.v_top_market_candidates CASCADE;

CREATE VIEW analytics.v_top_market_candidates AS
SELECT *
FROM analytics.v_market_attractiveness
ORDER BY composite_score DESC
LIMIT 20;
