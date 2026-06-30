# Nium Case Study: Global Coffee Market Entry Analysis

This repository contains my submission for the Nium coffee case study. I used global coffee consumption and trade data to recommend three launch markets for ACME Baristas, an imagined coffee chain planning an international expansion.

The project combines USDA PSD Coffee, World Bank Population, and ISO Country Codes. I cleaned and reconciled the files, loaded them into PostgreSQL, built the analytics layer in SQL, and used Streamlit for the final dashboard.

Quick aside. This is a market-screening exercise, not a full rollout plan. It gets to a short list. It does not replace local consumer research, site selection, or competitor fieldwork.

## Recommendation Summary

Based on the analysis, my picks are China, Egypt, and Vietnam. Here's the short version of why.

1. **China** - 1.4B population, ~10.6% 5-year consumption CAGR, growing urban coffee culture, ~54% import dependency. Big enough to matter immediately, and still growing fast.
2. **Egypt** - 117M population, ~9.4% 5-year CAGR, 100% import dependency (zero local production), young urbanizing demographic. This one stood out because the import profile makes entry cleaner than in producer-heavy markets.
3. **Vietnam** - 101M population, ~9.1% 5-year CAGR, established coffee culture, ~17% import dependency. Not perfect because local incumbents are strong, but demand depth is real.

I also built the dashboard so the panel can change the composite score weights in the sidebar and see how the ranking moves.

## Tech Stack

- **Python 3.13** with pandas, numpy, sqlalchemy, psycopg2
- **PostgreSQL** hosted on Neon
- **Streamlit + Plotly** for the dashboard
- **SQL** for all transformation logic (six numbered .sql files under sql/)

## Repository Structure

```text
nium-coffee-case-study/
+-- README.md
+-- requirements.txt
+-- .env.example
+-- .gitignore
+-- data/
¦   +-- raw/                        # Downloaded source CSVs
¦   +-- processed/                  # Cleaned intermediate CSVs
+-- notebooks/
¦   +-- 01_exploration.ipynb        # Initial data exploration
+-- src/
¦   +-- download_data.py            # Fetches the three source datasets
¦   +-- country_mapping.py          # Country name to ISO3 reconciliation
¦   +-- clean_data.py               # Cleans and joins source data
¦   +-- db_loader.py                # Loads raw tables into Postgres
¦   +-- build_analytics.py          # Builds analytics schema (dim + facts + views)
¦   +-- audit.py                    # 33-check quality audit
¦   +-- verify_dashboard.py         # Dashboard interaction matrix verification
¦   +-- dump_database.py            # Generates the Postgres .sql dump
+-- sql/
¦   +-- 01_schema.sql               # Schema and raw table definitions
¦   +-- 02_dim_country.sql          # dim_country dimension table
¦   +-- 03_fact_coffee.sql          # Pivoted fact_coffee (long to wide)
¦   +-- 04_fact_population.sql      # fact_population from World Bank
¦   +-- 05_analytical_views.sql     # v_country_year_metrics, snapshots, growth, global trends
¦   +-- 06_business_metrics.sql     # Composite scoring and market attractiveness
+-- dashboard/
¦   +-- app.py                      # Streamlit dashboard (5 tabs)
¦   +-- db_utils.py                 # DB connection and caching helpers
+-- db_dump/
    +-- nium_coffee.sql             # PostgreSQL dump for offline restore
```

## Setup Instructions

### Prerequisites

- Python 3.11+ (tested on 3.13)
- A PostgreSQL instance (read-only Neon connection string provided separately, or restore the dump locally)
- Git

### Option A: Use the hosted Neon database (fastest)

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

### Option B: Restore from the .sql dump locally

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

### Option C: Rebuild from raw sources

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

I split the warehouse into `raw` and `analytics`. Raw tables stay close to source shape, while business logic lives in SQL models and views in `analytics`. That made debugging much easier.

Country reconciliation mattered a lot. The three sources do not agree on names, and the mismatches are not cosmetic. USDA uses names like "Korea, South" and "Burma" that do not line up cleanly with the other files. I went down a rabbit hole on this because naive joins silently drop data. The final approach in `country_mapping.py` uses a manual override dictionary first, then case-insensitive matching, then an explicit UNMAPPED flag. Only one country, "North Macedonia", remained unmapped, and it had negligible coffee signal.

I handled the long-to-wide coffee pivot in SQL rather than Python. USDA PSD arrives in long format, and the pivot happens in `sql/03_fact_coffee.sql` using `MAX(CASE WHEN attribute_description = ...)`. That keeps the analytics layer reproducible from the raw tables.

The recommendation is not hardcoded. I used a percentile-rank composite across size, growth, population, and import openness with a default 35/30/20/15 weighting. Those weights are exposed in the dashboard so someone reviewing the case can change the emphasis and see what moves.

I kept the app in a single Streamlit file with five tabs: Recommendation, Global Overview, Market Comparison, Country Deep Dive, and Methodology. Easy to run. Easy to demo.

I also put effort into QA. `src/audit.py` runs 33 checks across data integrity, business logic, statistical sanity, SQL quality, dashboard robustness, and submission readiness. `src/verify_dashboard.py` checks the dashboard controls. I tried a `CROSS JOIN` approach to build the country-year grid at one point. Bad idea. It created 25% null rows, and the audit script caught it before it shipped.

### Q2. What challenges did you face and how did you overcome them?

The biggest issue was country naming. USDA has labels like "Korea, South", "Cote d'Ivoire", and "Yemen (Sanaa)", and those do not map cleanly to ISO-based datasets. The fix was simple and auditable: a manual override dictionary with 30+ entries, fallback matching, and explicit UNMAPPED reporting.

Python 3.13 package support also got in the way. The initial pin to `pandas==2.2.2` failed because there was no 3.13 wheel and the source build needed Visual Studio tooling that was not available. I bumped to `pandas==2.2.3` and used `pip install --only-binary=:all:` so installs would not fall back to source builds.

Another issue came from over-eager joins in `fact_coffee`. The first version used `CROSS JOIN (years) x (countries)` followed by a `LEFT JOIN` to the pivoted data, which inflated the table to 6,006 rows and left about 25% of them with null core measures. The audit flagged that. I changed the build to pivot directly from `raw.coffee` with `GROUP BY iso3_code, market_year HAVING COUNT(value) > 0`. That brought the table down to 4,478 real rows and removed the null-density problem.

The per-capita formula needed a fix too. An early version multiplied by 2.20462, which pushed results way off. The audit sanity check made the problem obvious. USA should have been around 4.5 kg/person and the view was returning 0.61. I rewrote it in metric units. USDA PSD is in 1000 60kg bags, so kg per person = (value x 60,000) / population.

There was also a forecast-year mismatch. USDA goes through 2025, but World Bank population stops at 2024. The Country Deep Dive headline was grabbing the latest row and returning NULL population. I fixed that by pulling the most recent row with non-null population for the headline metrics while still letting the time-series chart run through 2025.

One more thing. An early B1 audit check treated the USDA balance equation too narrowly and produced false failures for countries like the USA and Brazil. USDA tracks beans, roast and ground, and soluble flows separately, so a bean-only check was incomplete. I rewrote the logic to use the full USDA balance identity. After that, the test countries balanced within 0% to 1%.

### Q3. What assumptions did you make?

Some assumptions were necessary to keep the case moving.

1. **USDA market year approximated as calendar year for population join.** USDA's market year runs October to September. I joined `market_year` directly to `year`, which is a rough six-month approximation. For population and longer-term trend work, I think that is acceptable.
2. **Per-capita assumes uniform consumption within a country.** National consumption divided by total population. No urban-rural or age split.
3. **Composite score weights are a baseline, not a fixed answer.** Default 35/30/20/15 (size/growth/population/import) reflects a balanced view weighted toward current scale.
4. **Regional and continental classifications come from the country codes file (UN M.49 groupings).** Useful for comparison, though not always how operators would define competitive regions.
5. **Excluded regional aggregates (European Union, USSR, Yugoslavia, Czechoslovakia) entirely.** They appear in USDA data but cannot be mapped cleanly to modern countries.
6. **North Macedonia dropped as UNMAPPED.** USDA uses both "Macedonia" and "North Macedonia" inconsistently. Volumes are negligible.
7. **Trade imbalance in the global aggregate is a known dataset characteristic, not a defect.** USDA PSD tracks ~94 countries, not every coffee-consuming country, so some global asymmetry is expected.

### Q4. If you had more time, what would you have done differently?

A few obvious upgrades would make this stronger:

- Per-capita disposable income or GNI per capita PPP
- Urbanization rate
- Competitive landscape data for markets like Vietnam
- A forecast layer to 2030

Also, I would tighten the dashboard query layer. Right now the filters are dropdown-constrained and the current implementation is safe for this use case, but parameterized SQLAlchemy `text()` queries with bound params would be cleaner.

If this were becoming a longer project, I would probably migrate the analytics layer to dbt and add a sensitivity-analysis tab so the ranking changes are easier to inspect.

### Q5. What additional data would have strengthened your insights?

This is where the analysis has real limits. I can tell a useful demand and trade story from the available data, but not the full market-entry story.

The biggest additions I would want are GDP per capita or disposable income, urbanization rate, café density, coffee retail prices, import duties on roasted coffee, age distribution, tourism inflows, internet and mobile payment penetration, and coffee culture indicators such as café search interest, Instagram coffee hashtag volume, or specialty certification counts.

Brazil's per-capita came out to 6.2 kg per person per year, which makes sense to me. Brazilians drink a lot of their own coffee. Helpful sanity check, but still only one layer of the story.

## Known Dataset Characteristics

- **USDA PSD tracks ~94 selective countries.** Major producers and consumers, not every coffee-drinking country. Flows to and from untracked countries show up asymmetrically.
- **2025 data is forecast year, not actual.** USDA's most recent year is a projection. Population data extends only through 2024 (World Bank).
- **Headline deep-dive metrics use the most recent year with population data** (typically 2024); time-series charts extend through 2025.
- **North Macedonia is excluded.** Negligible signal.

## Verification

Two scripts validate the project end to end:

- `python src/audit.py` checks data integrity, business logic, statistical sanity, SQL quality, dashboard robustness, and submission readiness. Latest result: 31 PASS, 4 WARN (documented), 0 FAIL.
- `python src/verify_dashboard.py` checks the interaction matrix for year filter, region filter, weight sliders, country selector, time series, and edge cases. Latest result: 9/9 PASS.

## Contact

Amshu Deepak  
amshudeepak@gmail.com  
+91 9880696123  
www.linkedin.com/in/amshudeepak
