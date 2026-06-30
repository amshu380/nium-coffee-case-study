from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from discover_attributes import OUTPUT_PATH as DISCOVERY_OUTPUT_PATH, run_discovery


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"


def load_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(database_url)


def execute_sql_file(engine, path: Path) -> None:
    sql_text = path.read_text(encoding="utf-8")
    raw_conn = engine.raw_connection()
    try:
        raw_conn.autocommit = False
        cursor = raw_conn.cursor()
        cursor.execute(sql_text)
        raw_conn.commit()
    finally:
        raw_conn.close()


def sql_literal(value: str) -> str:
    return value.replace("'", "''")


def write_fact_coffee_sql(selected: dict[str, str]) -> dict[str, list[str]]:
    target_metrics = [
        ("domestic_consumption", "Domestic Consumption", [selected["consumption"]]),
        ("production", "Production", [selected["production"]]),
        ("bean_imports", "Bean Imports", [selected["imports"]]),
        ("bean_exports", "Bean Exports", [selected["exports"]]),
        ("ending_stocks", "Ending Stocks", ["Ending Stocks"]),
        ("beginning_stocks", "Beginning Stocks", ["Beginning Stocks"]),
        ("roast_ground_imports", "Roast & Ground Imports", ["Roast & Ground Imports"]),
        ("roast_ground_exports", "Roast & Ground Exports", ["Roast & Ground Exports"]),
        ("soluble_imports", "Soluble Imports", ["Soluble Imports"]),
        ("soluble_exports", "Soluble Exports", ["Soluble Exports"]),
    ]

    available_attributes = set(
        pd.read_csv(PROJECT_ROOT / "data" / "processed" / "coffee_clean.csv")["attribute_description"].dropna().astype(str)
    )
    kept = []
    dropped = []
    case_lines = []

    for alias, label, candidates in target_metrics:
        match = next((candidate for candidate in candidates if candidate in available_attributes), None)
        if match:
            kept.append(f"{alias} <- {match}")
            case_lines.append(
                f"    MAX(CASE WHEN attribute_description = '{sql_literal(match)}' THEN value END) AS {alias}"
            )
        else:
            dropped.append(label)

    sql_lines = [
        "-- Kept metric mappings:",
        *[f"--   {item}" for item in kept],
        "-- Dropped metrics:",
        *([f"--   {item}" for item in dropped] if dropped else ["--   None"]),
        "DROP TABLE IF EXISTS analytics.fact_coffee CASCADE;",
        "",
        "CREATE TABLE analytics.fact_coffee AS",
        "SELECT",
        "    iso3_code,",
        "    market_year,",
        ",\n".join(case_lines),
        "FROM raw.coffee",
        "WHERE iso3_code IS NOT NULL",
        "GROUP BY iso3_code, market_year",
        "HAVING COUNT(value) > 0;",
        "",
        "CREATE INDEX idx_fact_coffee_iso3 ON analytics.fact_coffee (iso3_code);",
        "CREATE INDEX idx_fact_coffee_year ON analytics.fact_coffee (market_year);",
        "ALTER TABLE analytics.fact_coffee ADD PRIMARY KEY (iso3_code, market_year);",
        "",
        "ALTER TABLE analytics.fact_coffee",
        "    ADD CONSTRAINT fk_fact_coffee_country",
        "    FOREIGN KEY (iso3_code) REFERENCES analytics.dim_country (iso3_code);",
        "",
    ]

    (SQL_DIR / "03_fact_coffee.sql").write_text("\n".join(sql_lines), encoding="utf-8")
    return {"kept": kept, "dropped": dropped}


def backfill_dim_country_regions(engine):
    continent_map = px.data.gapminder()[["iso_alpha", "continent"]].drop_duplicates().rename(columns={"iso_alpha": "iso3_code"})
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE analytics.dim_country ALTER COLUMN region TYPE TEXT USING region::text"))
        conn.execute(text("ALTER TABLE analytics.dim_country ALTER COLUMN sub_region TYPE TEXT USING sub_region::text"))
        conn.execute(text("ALTER TABLE analytics.dim_country ALTER COLUMN continent TYPE TEXT USING continent::text"))
        for row in continent_map.to_dict("records"):
            conn.execute(
                text("UPDATE analytics.dim_country SET region = :continent, continent = :continent WHERE iso3_code = :iso3_code AND (region IS NULL OR continent IS NULL)"),
                row,
            )


def verify_step2(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM analytics.dim_country")).scalar_one()
        assert count >= 200, f"analytics.dim_country row count too low: {count}"
        null_count = conn.execute(text("SELECT COUNT(*) FROM analytics.dim_country WHERE iso3_code IS NULL")).scalar_one()
        assert null_count == 0, f"analytics.dim_country has null iso3_code rows: {null_count}"
        sample = pd.read_sql(
            text("SELECT iso3_code, country_name, region, continent FROM analytics.dim_country WHERE iso3_code IN ('USA','IND','BRA','VNM','ETH') ORDER BY iso3_code"),
            conn,
        )
        print(sample.to_string(index=False))
        assert set(sample["iso3_code"]) == {"USA", "IND", "BRA", "VNM", "ETH"}, (
            f"Missing required dim_country rows: {set(['USA','IND','BRA','VNM','ETH']) - set(sample['iso3_code'])}"
        )
    print("STEP 2 VERIFICATION PASSED")
    return count


def verify_step3(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM analytics.fact_coffee")).scalar_one()
        assert 4000 <= count <= 5000, f"analytics.fact_coffee row count out of range: {count}"
        countries = conn.execute(text("SELECT COUNT(DISTINCT iso3_code) FROM analytics.fact_coffee")).scalar_one()
        assert countries >= 70, f"analytics.fact_coffee country count too low: {countries}"
        yr = conn.execute(text("SELECT MIN(market_year), MAX(market_year) FROM analytics.fact_coffee")).one()
        print(f"fact_coffee year range: {yr[0]} to {yr[1]}")
        usa = pd.read_sql(
            text("SELECT iso3_code, market_year, production, domestic_consumption, bean_imports FROM analytics.fact_coffee WHERE iso3_code = 'USA' ORDER BY market_year DESC LIMIT 5"),
            conn,
        )
        print(usa.to_string(index=False))
        assert usa["domestic_consumption"].notna().any(), "USA sample has no non-null domestic_consumption"
        bra = pd.read_sql(
            text("SELECT iso3_code, market_year, production FROM analytics.fact_coffee WHERE iso3_code = 'BRA' ORDER BY market_year DESC LIMIT 5"),
            conn,
        )
        print(bra.to_string(index=False))
        assert bra["production"].notna().any(), "Brazil sample has null production in recent years"
    print("STEP 3 VERIFICATION PASSED")
    return {"rows": count, "countries": countries, "min_year": int(yr[0]), "max_year": int(yr[1])}


def verify_step4(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM analytics.fact_population")).scalar_one()
        assert count >= 10000, f"analytics.fact_population row count too low: {count}"
        ind = pd.read_sql(text("SELECT iso3_code, year, population FROM analytics.fact_population WHERE iso3_code = 'IND' ORDER BY year DESC LIMIT 3"), conn)
        usa = pd.read_sql(text("SELECT iso3_code, year, population FROM analytics.fact_population WHERE iso3_code = 'USA' ORDER BY year DESC LIMIT 3"), conn)
        print(ind.to_string(index=False))
        print(usa.to_string(index=False))
        assert float(ind.iloc[0]["population"]) > 1_000_000_000, "India latest population sanity check failed"
        assert float(usa.iloc[0]["population"]) > 300_000_000, "USA latest population sanity check failed"
    print("STEP 4 VERIFICATION PASSED")
    return count


def verify_step5(engine):
    with engine.connect() as conn:
        count_year_metrics = conn.execute(text("SELECT COUNT(*) FROM analytics.v_country_year_metrics")).scalar_one()
        assert count_year_metrics >= 4000, f"analytics.v_country_year_metrics row count too low: {count_year_metrics}"
        latest_count = conn.execute(text("SELECT COUNT(*) FROM analytics.v_latest_year_snapshot")).scalar_one()
        assert latest_count >= 70, f"analytics.v_latest_year_snapshot row count too low: {latest_count}"
        snapshot = pd.read_sql(
            text("SELECT iso3_code, country_name, market_year, domestic_consumption, per_capita_kg_per_person, consumption_cagr_5y FROM analytics.v_latest_year_snapshot WHERE iso3_code IN ('USA','BRA','DEU','JPN','IND','VNM','ETH','IDN') ORDER BY iso3_code"),
            conn,
        )
        print(snapshot.to_string(index=False))
        usa_row = snapshot.loc[snapshot["iso3_code"] == "USA"]
        assert not usa_row.empty, "USA row missing from analytics.v_latest_year_snapshot"
        usa_pc = float(usa_row.iloc[0]["per_capita_kg_per_person"])
        assert 4 <= usa_pc <= 5, f"USA per_capita_kg_per_person out of expected range: {usa_pc}"
        global_trends = pd.read_sql(text("SELECT * FROM analytics.v_global_trends WHERE market_year >= 2015 ORDER BY market_year"), conn)
        print(global_trends.to_string(index=False))
        latest_val = float(global_trends.iloc[-1]["total_consumption"])
        prior_val = float(global_trends.iloc[-6]["total_consumption"])
        assert latest_val > prior_val, (
            f"Global consumption did not rise versus 5 years prior: latest={latest_val}, prior={prior_val}"
        )
    print("STEP 5 VERIFICATION PASSED")
    return latest_count


def verify_step6(engine):
    with engine.connect() as conn:
        top20 = pd.read_sql(
            text("SELECT iso3_code, country_name, domestic_consumption, consumption_cagr_5y, composite_score FROM analytics.v_top_market_candidates"),
            conn,
        )
        print(top20.to_string(index=False))
        expected = {"USA", "BRA", "DEU", "JPN"}
        assert set(top20["iso3_code"]).intersection(expected), "Top 20 missing all expected high-consumption markets"
        assert top20["composite_score"].notna().all(), "Top 20 contains NULL composite_score"
        top3 = pd.read_sql(
            text("SELECT country_name, composite_score FROM analytics.v_top_market_candidates ORDER BY composite_score DESC LIMIT 3"),
            conn,
        )
        print("Top 3 candidates:")
        print(top3.to_string(index=False))
    print("STEP 6 VERIFICATION PASSED")
    return top3


def main():
    discovery = run_discovery() if not DISCOVERY_OUTPUT_PATH.exists() else run_discovery()
    fact_coffee_info = write_fact_coffee_sql(discovery["selected_attributes"])
    print(f"Kept fact_coffee metrics: {fact_coffee_info['kept']}")
    print(f"Dropped fact_coffee metrics: {fact_coffee_info['dropped'] or ['None']}")

    engine = load_engine()
    execute_sql_file(engine, SQL_DIR / "02_dim_country.sql")
    backfill_dim_country_regions(engine)
    dim_country_rows = verify_step2(engine)

    for file_name in ["03_fact_coffee.sql", "04_fact_population.sql", "05_analytical_views.sql", "06_business_metrics.sql"]:
        execute_sql_file(engine, SQL_DIR / file_name)

    fact_coffee_stats = verify_step3(engine)
    fact_population_rows = verify_step4(engine)
    latest_snapshot_count = verify_step5(engine)
    top3 = verify_step6(engine)

    print("================================")
    print("PHASE 3 VERIFICATION SUMMARY")
    print("================================")
    print("Step 1 (Discovery)          : PASSED")
    print(f"  - Consumption attr name   : {discovery['selected_attributes']['consumption']}")
    print(f"  - Production attr name    : {discovery['selected_attributes']['production']}")
    print(f"  - Imports attr name       : {discovery['selected_attributes']['imports']}")
    print(f"  - Exports attr name       : {discovery['selected_attributes']['exports']}")
    print(f"  - Year range              : {discovery['year_range']['min']} to {discovery['year_range']['max']}")
    print("Step 2 (dim_country)        : PASSED")
    print(f"  - Rows                    : {dim_country_rows}")
    print("Step 3 (fact_coffee pivot)  : PASSED")
    print(f"  - Rows                    : {fact_coffee_stats['rows']}")
    print(f"  - Countries               : {fact_coffee_stats['countries']}")
    print(f"  - Year range              : {fact_coffee_stats['min_year']} to {fact_coffee_stats['max_year']}")
    print("Step 4 (fact_population)    : PASSED")
    print(f"  - Rows                    : {fact_population_rows}")
    print("Step 5 (analytical views)   : PASSED")
    print(f"  - Latest year snapshot    : {latest_snapshot_count} countries")
    print("Step 6 (business metrics)   : PASSED")
    print("")
    print("TOP 3 MARKET CANDIDATES (preliminary):")
    for idx, row in enumerate(top3.itertuples(index=False), start=1):
        print(f"{idx}. {row.country_name} (composite score: {row.composite_score:.2f})")
    print("")
    print("================================")


if __name__ == "__main__":
    main()
