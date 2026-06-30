# Nium Case Study Submission

The brief asked which three global markets ACME Baristas should launch in. My picks: **China, Egypt, and Vietnam**, in that order. Here is the reasoning.

---

## Why these three

**China** is the obvious size-and-trajectory call. 1.4 billion people, roughly 10.6% five-year CAGR in consumption, urban coffee culture growing fast, and 54% import dependency. Luckin proved the unit economics work at scale there.

**Egypt** surprised me. 117 million people, 9.4% CAGR, and 100% import dependency because there is essentially zero local coffee production. That last number matters. In a producer market like Brazil or Vietnam, a foreign chain fights both incumbents and a culture that already knows great coffee. Egypt has the demand growth without the production-side complications.

**Vietnam** is the tougher call. The numbers look great. 101 million people, 9.1% CAGR, an established coffee palate. But Highlands Coffee, Trung Nguyen, and Phuc Long already own the cultural space. I kept it in the top three because the demand depth is real and the model picked it consistently across different weight scenarios. If I were writing the actual investment memo for ACME I would flag the competitive risk loudly.

---

## How to look at the work

The dashboard runs locally. Clone the repo, run `pip install -r requirements.txt`, then `streamlit run dashboard/app.py`. It opens at localhost:8501. The read-only connection string is shared by email.

If you would rather restore the database locally instead of using the hosted one, `db_dump/nium_coffee.sql` is a full dump.

If you want to retrace my steps, the scripts in `src/` build everything from the three raw CSVs. The order to run them is documented at the top of `src/build_analytics.py`.

I also included audit and verification scripts in `src/` if useful.

---

## Reflection

### What I designed and why

The warehouse has two schemas. Raw stays close to source shape, analytics holds business logic in views. That split made debugging much easier and means the analytics layer rebuilds from raw at any time.

Country reconciliation took more time than I expected. USDA uses names like "Korea, South" and "Burma" that do not line up cleanly with ISO. Naive joins silently drop data. The final fix in `country_mapping.py` is a manual override dictionary, then case-insensitive matching, then explicit UNMAPPED flagging. Only North Macedonia remained unmapped, and it has negligible volume.

The coffee fact table pivots in SQL, not Python. USDA arrives in long format. The pivot uses `MAX(CASE WHEN attribute_description = ...)` in `sql/03_fact_coffee.sql`. Doing it in SQL means the analytics schema rebuilds from raw without re-running Python.

The recommendation is not hardcoded. The composite score is a percentile-rank blend of size, growth, population, and import openness with default weights 35/30/20/15. Those weights are sliders in the dashboard sidebar. Whoever is reviewing can change the emphasis and watch the ranking move. That felt more honest than reverse-engineering a justification.

### What broke and how I fixed it

Three real bugs, all caught by the audit script.

**First, the per-capita calculation was off.** An early version multiplied by 2.20462, which is the kg-to-pounds conversion factor. USDA values are already metric, so this just produced numbers 2.2x too low. USA was showing 0.6 kg per person per year, which is obviously wrong. Real value is around 4.6. Fixed by rewriting the formula in pure metric units. Once it was right, Brazil came out to 6.2 kg per person per year, which felt right too. Brazilians drink a lot of their own coffee. Good cross-check.

**Second, the fact_coffee table had phantom rows.** The first version used a CROSS JOIN of all years and all countries, then LEFT JOINed the actual data. That manufactured 6,006 rows but about 25% had null core measures because those country-years did not exist in the source. The audit caught the null density. Rebuilt the pivot to read directly from raw with `GROUP BY iso3, market_year HAVING COUNT(value) > 0`. Row count dropped to 4,478 real rows and null density went to zero.

**Third, the bean balance equation in the audit was checking the wrong identity.** USDA tracks three flow types separately: beans, roast and ground, and soluble. An early check only looked at bean flows and showed 47% imbalance on the US (a huge net importer of soluble and roast and ground) and 757% on Brazil. The data was fine. The check was incomplete. Rewrote it to use the full USDA balance with all three flow types, and gaps dropped to under 1% for every test country.

### Assumptions

- USDA market years run October to September. I joined them directly to World Bank calendar years. That is a six-month approximation. For population, which moves slowly, it is acceptable.
- Per-capita assumes uniform consumption within a country. There is no urban-rural split or demographic adjustment. For a chain that will live in cities, that is a real limit.
- Composite score weights are a starting point, not the answer. The dashboard exposes them.
- Regional groupings come from the UN M.49 file. Useful for comparison, not always how operators define competitive regions in practice.
- I dropped regional aggregates like EU, USSR, Yugoslavia, and Czechoslovakia entirely. They appear in USDA but cannot be cleanly attributed to modern countries.
- The global production-vs-consumption gap of about 26% is a dataset characteristic, not a model defect. USDA tracks roughly 94 countries, mostly major producers and major consumers. Coffee flowing to smaller untracked markets shows up in exports but not in anyone's imports.

### What I would do differently with more time

The thing missing most is income data. GDP per capita and disposable income would let me build a consumption-versus-purchasing-power view, which is closer to how chain economics actually work. Urbanization rate would help for the same reason.

A competitive landscape layer would matter for Vietnam specifically. The model has no way to know Highlands and Trung Nguyen exist.

I would add a forecast to 2030 using a simple Prophet model or even a CAGR projection. The current view is backward-looking.

On the technical side, I would parameterize the dashboard SQL with bound parameters instead of f-string interpolation. Safe for the current dropdown-only inputs, but cleaner. If this kept growing I would migrate the analytics layer to dbt for proper testing and lineage.

### What additional data would help

In rough order of how much I think they would move the recommendation: income (GDP per capita PPP, disposable income, retail prices), urbanization rate, café density, age distribution, import duties on roasted coffee, tourism inflows, digital payment penetration, and softer coffee culture signals like search interest or specialty certification counts.

---

**Amshu Deepak**
amshudeepak@gmail.com
+91 9880696123
[linkedin.com/in/amshudeepak](https://www.linkedin.com/in/amshudeepak)
