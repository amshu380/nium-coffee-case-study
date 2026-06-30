# Nium Case Study — Global Coffee Market Entry Analysis

A data engineering and analysis project for ACME Baristas, an imagined coffee chain evaluating three global markets for launch. The analysis joins three open datasets (USDA PSD Coffee, World Bank Population, ISO Country Codes), models them in PostgreSQL, and surfaces market recommendations through a Streamlit dashboard.

## Recommendation Summary

Based on a composite score combining market size, growth rate, population scale, and import openness, the three recommended launch markets are:

1. **China** — 1.4B population, ~10.6% 5-year consumption CAGR, growing urban coffee culture, ~54% import dependency. The scale-and-trajectory market.
2. **Egypt** — 117M population, ~9.4% 5-year CAGR, 100% import dependency (zero local production), young urbanizing demographic. The high-growth import-friendly market.
3. **Vietnam** — 101M population, ~9.1% 5-year CAGR, established coffee culture, ~17% import dependency. The coffee-aware emerging market, though local incumbents present competitive friction.

The dashboard allows the panel to stress-test these recommendations by adjusting the composite score weights via sidebar sliders.

## Tech Stack

- **Python 3.13** with pandas, numpy, sqlalchemy, psycopg2
- **PostgreSQL** hosted on Neon
- **Streamlit + Plotly** for the dashboard
- **SQL** for all transformation logic (six numbered .sql files under sql/)

## Repository Structure
nium-coffee-case-study/

├── README.md

├── requirements.txt

├── .env.example

├── .gitignore

├── data/

│   ├── raw/                        # Downloaded source CSVs

│   └── processed/                  # Cleaned intermediate CSVs

├── notebooks/

│   └── 01_exploration.ipynb        # Initial data exploration

├── src/

│   ├── download_data.py            # Fetches the three source datasets

│   ├── country_mapping.py          # Country name to ISO3 reconciliation

│   ├── clean_data.py               # Cleans and joins source data

│   ├── db_loader.py                # Loads raw tables into Postgres

│   ├── build_analytics.py          # Builds analytics schema (dim + facts + views)

│   ├── audit.py                    # 33-check quality audit

│   ├── verify_dashboard.py         # Dashboard interaction matrix verification

│   └── dump_database.py            # Generates the Postgres .sql dump

├── sql/

│   ├── 01_schema.sql               # Schema and raw table definitions

│   ├── 02_dim_country.sql          # dim_country dimension table

│   ├── 03_fact_coffee.sql          # Pivoted fact_coffee (long to wide)

│   ├── 04_fact_population.sql      # fact_population from World Bank

│   ├── 05_analytical_views.sql     # v_country_year_metrics, snapshots, growth, global trends

│   └── 06_business_metrics.sql     # Composite scoring and market attractiveness

├── dashboard/

│   ├── app.py                      # Streamlit dashboard (5 tabs)

│   └── db_utils.py                 # DB connection and caching helpers

└── db_dump/

└── nium_coffee.sql             # PostgreSQL dump for offline restore

## Setup Instructions

### Prerequisites

- Python 3.11+ (tested on 3.13)
- A PostgreSQL instance (read-only Neon connection string provided separately, or restore the dump locally)
- Git

### Option A — Use the hosted Neon database (fastest)

The read-only connection string is provided to the evaluation team via email for security. To connect:

```bash
git clone https://github.com/amshu380/nium-coffee-case-study.git
cd nium-coffee-case-study

pip install --only-binary=:all: -r requirements.txt

cp .env.example .env
# Edit .env and paste the read-only connection string provided in the submission email

cd dashboard
streamlit run app.py
```

The dashboard opens at http://localhost:8501.

### Option B — Restore from the .sql dump locally

```bash
git clone https://github.com/amshu380/nium-coffee-case-study.git
cd nium-coffee-case-study

createdb nium_coffee
psql -d nium_coffee -f db_dump/nium_coffee.sql

# Set DATABASE_URL in .env to point to your local instance
# Example: DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/nium_coffee

pip install --only-binary=:all: -r requirements.txt
cd dashboard
streamlit run app.py
```

### Option C — Rebuild from raw sources

```bash
git clone https://github.com/amshu380/nium-coffee-case-study.git
cd nium-coffee-case-study

pip install --only-binary=:all: -r requirements.txt

# Configure .env with your own DATABASE_URL

python src/download_data.py
python src/country_mapping.py
python src/clean_data.py
python src/db_loader.py
python src/build_analytics.py
python src/audit.py
```

## Reflection

### Q1. Walk us through your key design choices

**Two-schema architecture (raw vs analytics).** Source data lives in a `raw` schema with minimal transformation, joined only on country codes and pivoted nowhere. All business logic lives in an `analytics` schema as documented SQL views. This separation lets future analysts inspect source data without untangling business assumptions, and lets us iterate on metric definitions without re-loading raw data.

**Country reconciliation as a first-class layer.** The three sources use different country naming conventions (USDA uses "Korea, South" and "Burma"; World Bank uses ISO-3; opendatasoft uses an English Name with variants). I built `country_mapping.py` with a manual override dictionary first, then case-insensitive matching, then an UNMAPPED flag for review. The dictionary is auditable and version-controllable. Only one country ("North Macedonia") fell through to UNMAPPED, with negligible coffee signal.

**Long-to-wide pivot in SQL, not Python.** USDA PSD ships in long format (one row per country-year-attribute). The pivot to wide happens in `sql/03_fact_coffee.sql` using `MAX(CASE WHEN attribute_description = ...)`. Doing this in SQL keeps the analytics schema reproducible from raw without re-running Python.

**Composite score with adjustable weights.** Rather than hardcoding a recommendation, I built a percentile-rank composite across four dimensions (size, growth, population, import openness) with a default 35/30/20/15 weighting, and exposed the weights as sidebar sliders. The panel can shift the strategic priority (for example, growth-only) and see the top 3 reshuffle in real time. This treats the panel as analysts, not consumers of a single answer.

**Single-file Streamlit with tabs.** Five tabs in one file: Recommendation, Global Overview, Market Comparison, Country Deep Dive, Methodology. Easier to demo than multi-page apps.

**Comprehensive automated audit.** `src/audit.py` runs 33 checks across six categories (data integrity, business logic, statistical sanity, SQL quality, dashboard robustness, submission readiness). The audit caught two real bugs during development that would have shipped otherwise: a kg-to-pounds unit conversion error in the per-capita formula, and a CROSS JOIN years pattern in `fact_coffee` that manufactured 25% null rows.

**Dashboard interaction verification.** `src/verify_dashboard.py` simulates every interactive control and asserts the dashboard responds correctly to year ranges, region filters, weight sliders, and country selection. Includes per-country per-capita sanity ranges. 9/9 PASS at submission time.

### Q2. What challenges did you face and how did you overcome them?

**Country name reconciliation.** USDA's idiosyncratic naming ("Korea, South", "Cote d'Ivoire", "Yemen (Sanaa)") does not match any ISO standard cleanly. Naive joins lose data silently. Solution: manual override dictionary with 30+ entries, plus case-insensitive fallback matching, plus explicit UNMAPPED flagging in the diagnostic print.

**Python 3.13 wheel availability.** Initial pinning to `pandas==2.2.2` failed because no prebuilt 3.13 wheel exists for that version and the source build needed Visual Studio tooling. Solution: bumped to `pandas==2.2.3` and pinned installs with `pip install --only-binary=:all:` to guarantee no source builds.

**Phantom country-year rows from over-eager joins.** The first `fact_coffee` used `CROSS JOIN (years) × (countries)` then `LEFT JOIN` to pivoted data. This created 6,006 rows but ~25% had null core measures (country-years that never existed in source). The audit caught it. Fix: pivot directly from `raw.coffee` with `GROUP BY iso3_code, market_year HAVING COUNT(value) > 0`. Row count dropped to 4,478 actual rows. Null density dropped to 0%.

**Per-capita formula unit bug.** The original SQL multiplied by 2.20462 (kg-to-pounds conversion factor), producing values 2.2x too low. The audit sanity check (USA expected ~4.5 kg/person, view returned 0.61) caught it. Rewrote using metric units. USDA PSD value unit is 1000 60kg bags; kg per person = (value × 60,000) / population.

**Forecast year population mismatch.** USDA market year extends to 2025 (forecast), World Bank population stops at 2024. The Country Deep Dive headline pulled the most recent row and got NULL population. Fixed by selecting the most recent row with non-null population for headline metrics, while keeping the full time-series chart through 2025.

**Bean balance equation false failures in the audit.** An early B1 check tested whether `production + bean_imports - bean_exports - consumption ≈ ending_stocks`. USA showed a 47% gap, Brazil 757%. The check was incomplete — USDA tracks three flow types (beans, roast & ground, soluble), and the US is a massive net importer of R&G and soluble. Rewrote to use the full USDA balance identity. All test countries now balance within 0% to 1%.

### Q3. What assumptions did you make?

1. **USDA market year approximated as calendar year for population join.** USDA's market year runs October to September. I joined `market_year` directly to `year`, a six-month approximation. For population (which moves slowly) and long-run analysis, impact is negligible.

2. **Per-capita assumes uniform consumption within a country.** Total national consumption divided by total population. Urban-rural and demographic splits are not modeled.

3. **Composite score weights are a baseline, not a fixed answer.** Default 35/30/20/15 (size/growth/population/import) reflects a balanced view weighted toward current scale. The dashboard exposes this trade-off via sliders.

4. **Regional and continental classifications come from the country codes file (UN M.49 groupings).** Markets like Turkey or Russia may belong to different competitive clusters in practice.

5. **Excluded regional aggregates (European Union, USSR, Yugoslavia, Czechoslovakia) entirely.** These appear in USDA data but cannot be cleanly attributed to modern political entities.

6. **North Macedonia dropped as UNMAPPED.** USDA uses both "Macedonia" and "North Macedonia" inconsistently. Volumes are negligible.

7. **Trade imbalance in the global aggregate is a known dataset characteristic, not a defect.** USDA PSD tracks ~94 countries, not every coffee-consuming country. Coffee exported FROM tracked producers TO smaller untracked consumer markets shows up asymmetrically. This produces a ~26% gap between global production and consumption and a ~49% gap between tracked imports and exports.

### Q4. If you had more time, what would you have done differently?

1. **Incorporate per-capita disposable income.** World Bank GNI per capita PPP would let me build a "consumption headroom" metric.
2. **Add urbanization rate.** Coffee chains live in urban economies; national per-capita masks urban-rural splits.
3. **Build a competitive landscape layer.** Vietnam scores high but Highlands Coffee, Trung Nguyen, Phuc Long dominate. A "has dominant local chain" override would refine the ranking.
4. **Time-series forecast to 2030.** A Prophet or linear extrapolation forecast would let me show forward-looking views, not just backward CAGRs.
5. **Parameterized queries throughout the dashboard.** The current dashboard interpolates region and country filters via f-strings. With dropdown-only inputs this is safe, but proper SQLAlchemy text() with bound params would be more defensible.
6. **Migrate the analytics layer to dbt.** Would give model lineage, testing, documentation as first-class features.
7. **Sensitivity analysis tab.** A grid of weight combinations showing how the top 5 reshuffles, to surface ranking robustness.

### Q5. What additional data would have strengthened your insights?

1. **GDP per capita and disposable income.** Purchasing power and addressable market sizing.
2. **Urbanization rate.** Coffee chain customers are urban.
3. **Café density data.** Competitive saturation and undersupplied markets.
4. **Coffee retail price by country.** Margin economics vary widely.
5. **Import duties on roasted coffee.** Affects unit economics for an import-led chain.
6. **Age distribution, particularly young-adult share.** Coffee chain customers skew 18-45.
7. **Tourism inflows.** Drives premium coffee demand in moderate-domestic markets.
8. **Internet and mobile payment penetration.** Modern coffee chains are app-driven.
9. **Coffee culture indicators.** Café search interest, Instagram coffee hashtag volume, specialty certification counts.

## Known Dataset Characteristics

- **USDA PSD tracks ~94 selective countries.** Major producers and consumers, not every coffee-drinking country. Flows to and from untracked countries show up asymmetrically.
- **2025 data is forecast year, not actual.** USDA's most recent year is a projection. Population data extends only through 2024 (World Bank).
- **Headline deep-dive metrics use the most recent year with population data** (typically 2024); time-series charts extend through 2025.
- **North Macedonia is excluded.** Negligible signal.

## Verification

Two scripts validate the project end to end:

- `python src/audit.py` — 33 checks across data integrity, business logic, statistical sanity, SQL quality, dashboard robustness, submission readiness. Latest result: 31 PASS, 4 WARN (documented), 0 FAIL.
- `python src/verify_dashboard.py` — interactive control matrix verifying year filter, region filter, weight sliders, country selector, time series, and edge cases. Latest result: 9/9 PASS.

## Contact

Amshu Deepak  
amshudeepak@gmail.com  
+91 9880696123  
www.linkedin.com/in/amshudeepak