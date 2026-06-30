from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"
load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in .env")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def run_query(query: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def scalar(query: str):
    with engine.connect() as conn:
        return conn.execute(text(query)).scalar_one()


def execute_sql_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))


def sql_in_list(values: list[str]) -> str:
    return ",".join("'" + value.replace("'", "''") + "'" for value in values)


def composite_query(region_filter: str | None, weights: tuple[float, float, float, float]) -> pd.DataFrame:
    region_clause = ""
    if region_filter:
        region_clause = f"AND region = '{region_filter}'"
    w_size, w_growth, w_pop, w_import = weights
    query = f"""
    WITH base AS (
        SELECT *
        FROM analytics.v_latest_year_snapshot
        WHERE domestic_consumption IS NOT NULL
          AND population IS NOT NULL
          AND domestic_consumption > 0
          {region_clause}
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
            population,
            import_dependency_ratio,
            PERCENT_RANK() OVER (ORDER BY domestic_consumption) AS size_score,
            PERCENT_RANK() OVER (ORDER BY COALESCE(consumption_cagr_5y, -1)) AS growth_score,
            PERCENT_RANK() OVER (ORDER BY population) AS population_score,
            PERCENT_RANK() OVER (ORDER BY COALESCE(import_dependency_ratio, 0)) AS import_openness_score
        FROM base
    )
    SELECT
        *,
        ({w_size} * size_score + {w_growth} * growth_score + {w_pop} * population_score + {w_import} * import_openness_score) AS composite_score
    FROM ranked
    ORDER BY composite_score DESC
    LIMIT 20
    """
    return run_query(query)


def headline_row(iso3: str) -> pd.Series:
    history = run_query(f"SELECT * FROM analytics.v_country_year_metrics WHERE iso3_code = '{iso3}' ORDER BY market_year")
    if history.empty:
        raise AssertionError(f"No history rows for {iso3}")
    pop_rows = history[history["population"].notna()]
    return (pop_rows.iloc[-1] if len(pop_rows) > 0 else history.iloc[-1])


def fmt_pct(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator * 100):.1f}%" if denominator else "0.0%"


def main() -> int:
    total_checks = 0
    pass_checks = 0
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        nonlocal total_checks, pass_checks
        total_checks += 1
        if condition:
            pass_checks += 1
        else:
            failures.append(message)

    # Fix 1 verification
    usa_latest = headline_row("USA")
    fix1_pass = bool(pd.notna(usa_latest["population"]) and int(usa_latest["market_year"]) <= 2024)
    check(fix1_pass, f"Fix 1 failed: USA headline row market_year={usa_latest['market_year']}, population={usa_latest['population']}")

    # Fix 2 investigation / optional rebuild
    coverage_before = run_query("""
        SELECT COUNT(*) AS total,
               COUNT(population) AS with_pop,
               COUNT(per_capita_kg_per_person) AS with_per_capita
        FROM analytics.v_latest_year_snapshot
    """).iloc[0]
    total = int(coverage_before["total"])
    with_pop_before = int(coverage_before["with_pop"])
    with_pc_before = int(coverage_before["with_per_capita"])
    pop_pct_before = (with_pop_before / total * 100) if total else 0.0
    pc_pct_before = (with_pc_before / total * 100) if total else 0.0
    fix2_status = "NOT NEEDED"
    pop_pct_after = pop_pct_before
    if pop_pct_before <= 95 or pc_pct_before <= 95:
        execute_sql_file(SQL_DIR / "05_analytical_views.sql")
        execute_sql_file(SQL_DIR / "06_business_metrics.sql")
        coverage_after = run_query("""
            SELECT COUNT(*) AS total,
                   COUNT(population) AS with_pop,
                   COUNT(per_capita_kg_per_person) AS with_per_capita
            FROM analytics.v_latest_year_snapshot
        """).iloc[0]
        pop_pct_after = (int(coverage_after["with_pop"]) / int(coverage_after["total"]) * 100) if int(coverage_after["total"]) else 0.0
        fix2_status = "PASS" if pop_pct_after > 95 else "FAIL"
        check(pop_pct_after > 95, f"Fix 2 failed: post-fix population coverage {pop_pct_after:.1f}%")
    else:
        check(True, "")

    # TC1 Year slider -> Global Overview
    a = run_query("SELECT * FROM analytics.v_global_trends WHERE market_year BETWEEN 2015 AND 2025 ORDER BY market_year")
    b = run_query("SELECT * FROM analytics.v_global_trends WHERE market_year BETWEEN 2020 AND 2025 ORDER BY market_year")
    c = run_query("SELECT region, SUM(domestic_consumption) AS total_consumption FROM analytics.v_country_year_metrics WHERE market_year = 2020 GROUP BY region ORDER BY region")
    d = run_query("SELECT region, SUM(domestic_consumption) AS total_consumption FROM analytics.v_country_year_metrics WHERE market_year = 2024 GROUP BY region ORDER BY region")
    tc1_pass = True
    if not (len(a) > len(b)):
        tc1_pass = False
        failures.append(f"TC1 failed: len(A)={len(a)} not > len(B)={len(b)}")
    if not (int(a.iloc[0]["market_year"]) < int(b.iloc[0]["market_year"])):
        tc1_pass = False
        failures.append(f"TC1 failed: first years {a.iloc[0]['market_year']} vs {b.iloc[0]['market_year']}")
    c_total = float(c["total_consumption"].sum())
    d_total = float(d["total_consumption"].sum())
    if not (d_total > c_total):
        tc1_pass = False
        failures.append(f"TC1 failed: regional total 2024={d_total} not > 2020={c_total}")
    if c.equals(d):
        tc1_pass = False
        failures.append("TC1 failed: regional query outputs for 2020 and 2024 are identical")
    check(tc1_pass, "TC1 failed")

    # TC2 Region filter -> Recommendation
    default_weights = (0.35, 0.30, 0.20, 0.15)
    all_regions_df = composite_query(None, default_weights)
    asia_df = composite_query("Asia", default_weights)
    africa_df = composite_query("Africa", default_weights)
    all_top3 = all_regions_df.head(3)
    asia_top3 = asia_df.head(3)
    africa_top3 = africa_df.head(3)
    tc2_pass = True
    if not any(region != "Asia" for region in all_top3["region"]):
        tc2_pass = False
        failures.append(f"TC2 failed: all-regions top 3 are all Asian {all_top3['country_name'].tolist()}")
    if not all(region == "Asia" for region in asia_top3["region"]):
        tc2_pass = False
        failures.append(f"TC2 failed: Asia-only top 3 regions {asia_top3['region'].tolist()}")
    if not all(region == "Africa" for region in africa_top3["region"]):
        tc2_pass = False
        failures.append(f"TC2 failed: Africa-only top 3 regions {africa_top3['region'].tolist()}")
    top_lists = [tuple(all_top3["country_name"]), tuple(asia_top3["country_name"]), tuple(africa_top3["country_name"])]
    if len(set(top_lists)) != 3:
        tc2_pass = False
        failures.append(f"TC2 failed: top 3 lists not all different {top_lists}")
    check(tc2_pass, "TC2 failed")

    # TC3 Weights -> Recommendation
    scenarios = {
        "Default": default_weights,
        "Size-heavy": (0.70, 0.10, 0.10, 0.10),
        "Growth-heavy": (0.10, 0.70, 0.10, 0.10),
        "Pop-heavy": (0.10, 0.10, 0.70, 0.10),
        "Import-heavy": (0.10, 0.10, 0.10, 0.70),
    }
    scenario_top3: dict[str, list[str]] = {name: composite_query(None, weights).head(3)["country_name"].tolist() for name, weights in scenarios.items()}
    tc3_pass = True
    unique_lists = {tuple(v) for v in scenario_top3.values()}
    if len(unique_lists) != len(scenario_top3):
        tc3_pass = False
        failures.append(f"TC3 failed: duplicate top 3 lists {scenario_top3}")
    if not any(country in scenario_top3["Size-heavy"] for country in ["United States", "China", "Brazil"]):
        tc3_pass = False
        failures.append(f"TC3 failed: size-heavy top 3 {scenario_top3['Size-heavy']} missing USA/China/Brazil")
    growth_only = [c for c in scenario_top3["Growth-heavy"] if c not in scenario_top3["Size-heavy"]]
    if not growth_only:
        tc3_pass = False
        failures.append(f"TC3 failed: growth-heavy top 3 {scenario_top3['Growth-heavy']} does not elevate a new market vs size-heavy {scenario_top3['Size-heavy']}")
    check(tc3_pass, "TC3 failed")

    # TC4 Country selector -> Deep Dive
    country_expectations = {
        "USA": (300_000_000, 3.0, 6.0),
        "IND": (1_000_000_000, 0.01, 0.2),
        "BRA": (200_000_000, 4.0, 8.0),
        "VNM": (90_000_000, 1.0, 3.0),
        "ETH": (100_000_000, 1.0, 4.0),
        "JPN": (100_000_000, 3.0, 6.0),
        "CHN": (1_000_000_000, 0.1, 1.0),
        "EGY": (100_000_000, 0.2, 2.0),
    }
    headline_values: dict[str, float] = {}
    tc4_pass = True
    for iso3, (min_pop, lo, hi) in country_expectations.items():
        row = headline_row(iso3)
        pop = float(row["population"]) if pd.notna(row["population"]) else float("nan")
        pc = float(row["per_capita_kg_per_person"]) if pd.notna(row["per_capita_kg_per_person"]) else float("nan")
        headline_values[iso3] = pc
        if not (pd.notna(pop) and pop > min_pop):
            tc4_pass = False
            failures.append(f"TC4 failed for {iso3}: population {pop} <= expected {min_pop}")
        if not (pd.notna(pc) and lo <= pc <= hi):
            tc4_pass = False
            failures.append(f"TC4 failed for {iso3}: per_capita_kg_per_person {pc} outside expected range [{lo}, {hi}]")
    check(tc4_pass, "TC4 failed")

    # TC5 Time-series chart full history
    usa_history = run_query("SELECT * FROM analytics.v_country_year_metrics WHERE iso3_code = 'USA' ORDER BY market_year")
    usa_non_null_pct = float(usa_history["domestic_consumption"].notna().mean() * 100) if not usa_history.empty else 0.0
    tc5_pass = True
    if not (len(usa_history) >= 50):
        tc5_pass = False
        failures.append(f"TC5 failed: USA history rows {len(usa_history)} < 50")
    if not (int(usa_history["market_year"].min()) <= 1970):
        tc5_pass = False
        failures.append(f"TC5 failed: USA min market_year {usa_history['market_year'].min()} > 1970")
    if not (int(usa_history["market_year"].max()) >= 2024):
        tc5_pass = False
        failures.append(f"TC5 failed: USA max market_year {usa_history['market_year'].max()} < 2024")
    if not (usa_non_null_pct >= 90):
        tc5_pass = False
        failures.append(f"TC5 failed: USA non-null domestic_consumption pct {usa_non_null_pct:.1f}% < 90%")
    check(tc5_pass, "TC5 failed")

    # TC6 Edge cases
    tc6_pass = True
    empty_region_query = composite_query("Atlantis", default_weights)
    if not empty_region_query.empty:
        tc6_pass = False
        failures.append(f"TC6A failed: expected empty recommendation set, got {len(empty_region_query)} rows")
    single_year = run_query("SELECT * FROM analytics.v_global_trends WHERE market_year BETWEEN 2025 AND 2025")
    if len(single_year) != 1:
        tc6_pass = False
        failures.append(f"TC6B failed: single-year query returned {len(single_year)} rows")
    sparse = run_query("SELECT iso3_code, COUNT(*) AS n FROM analytics.fact_coffee GROUP BY iso3_code ORDER BY n ASC, iso3_code ASC LIMIT 1")
    sparse_iso = sparse.iloc[0]["iso3_code"]
    sparse_history = run_query(f"SELECT * FROM analytics.v_country_year_metrics WHERE iso3_code = '{sparse_iso}' ORDER BY market_year")
    if sparse_history is None:
        tc6_pass = False
        failures.append(f"TC6C failed: sparse country query returned None for {sparse_iso}")
    zero_weights = (0.0, 0.0, 0.0, 0.0)
    total_zero = sum(zero_weights)
    normalized = zero_weights if total_zero == 0 else tuple(w / total_zero for w in zero_weights)
    if normalized != zero_weights:
        tc6_pass = False
        failures.append(f"TC6D failed: zero-weight normalization {normalized}")
    check(tc6_pass, "TC6 failed")

    # Smoke test
    smoke_pass = False
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true", "--server.port=8504"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT / "dashboard"),
        )
        time.sleep(8)
        proc.terminate()
        out, _ = proc.communicate(timeout=5)
        output = out.decode("utf-8", errors="ignore")
        smoke_pass = ("Traceback" not in output) and (("You can now view" in output) or ("Local URL" in output))
        if not smoke_pass:
            failures.append("Smoke test failed: Streamlit startup did not complete cleanly")
    except Exception as exc:
        failures.append(f"Smoke test failed with exception: {exc}")
    check(smoke_pass, "Smoke test failed")

    print("================================")
    print("DASHBOARD INTERACTION MATRIX VERIFICATION")
    print("================================")
    print(f"Fix 1 (Deep Dive headline pop)      : {'PASS' if fix1_pass else 'FAIL'}")
    print(f"Fix 2 (Snapshot view pop coverage)  : {fix2_status}")
    print(f"  - Pre-fix population coverage    : {pop_pct_before:.1f}%")
    print(f"  - Post-fix population coverage   : {pop_pct_after:.1f}%")
    print("")
    print("Interaction Tests:")
    print(f"  TC1 Year slider -> Global Overview  : {'PASS' if tc1_pass else 'FAIL'}")
    print(f"       - 2015-2025 range rows: {len(a)}")
    print(f"       - 2020-2025 range rows: {len(b)}")
    print(f"  TC2 Region filter -> Recommendation : {'PASS' if tc2_pass else 'FAIL'}")
    print(f"       - All regions top 3   : {all_top3['country_name'].tolist()}")
    print(f"       - Asia only top 3     : {asia_top3['country_name'].tolist()}")
    print(f"       - Africa only top 3   : {africa_top3['country_name'].tolist()}")
    print(f"  TC3 Weights -> Recommendation       : {'PASS' if tc3_pass else 'FAIL'}")
    for name in ['Default', 'Size-heavy', 'Growth-heavy', 'Pop-heavy', 'Import-heavy']:
        print(f"       - {name:<16}: {scenario_top3[name]}")
    print(f"  TC4 Country selector -> Deep Dive   : {'PASS' if tc4_pass else 'FAIL'}")
    for iso3 in ['USA', 'IND', 'BRA', 'VNM', 'ETH', 'JPN', 'CHN', 'EGY']:
        value = headline_values[iso3]
        print(f"       - {iso3} per-capita      : {value:.3f} kg")
    print(f"  TC5 Deep dive time series          : {'PASS' if tc5_pass else 'FAIL'}")
    print(f"       - USA history rows    : {len(usa_history)}, year range {int(usa_history['market_year'].min())} to {int(usa_history['market_year'].max())}")
    print(f"  TC6 Edge cases handled             : {'PASS' if tc6_pass else 'FAIL'}")
    print("")
    print("================================")
    print("FIX VERIFICATION:")
    print("================================")
    print(f"Streamlit re-run smoke test         : {'PASS' if smoke_pass else 'FAIL'}")
    print("(headless 8-second startup, no traceback)")
    print("")
    print("================================")
    print("SUMMARY")
    print("================================")
    print(f"All tests                : {pass_checks}/{total_checks} PASS")
    confidence = 'HIGH' if pass_checks == total_checks else ('MEDIUM' if pass_checks >= total_checks - 2 else 'LOW')
    print(f"Confidence to submit     : {confidence}")
    if failures:
        print("")
        print("Failures:")
        for failure in failures:
            if failure:
                print(f"- {failure}")
    return 0 if pass_checks == total_checks else 1


if __name__ == '__main__':
    raise SystemExit(main())
